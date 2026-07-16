"""Durable tenant-scoped primitive registry over the SQLite control-plane adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .canonical import canonical_digest, canonical_json_bytes
from .contracts import ProducerRef, RecordMixin
from .identity import IdentityRecord
from .primitive_capsules import (
    BlobDescriptor,
    CapsuleRole,
    PrimitiveHandle,
    PrimitivePack,
    PrimitiveRefUpdate,
    PrimitiveRegistry,
    PrimitiveRegistryError,
    PrimitiveRevision,
    PrimitiveTree,
    PrimitiveTreeEntry,
    RefKind,
    encode_primitive_pack,
)
from .saas import SQLiteControlPlane
from .primitives.release import (
    PrimitiveAcceptanceReceipt,
    PrimitiveReleaseAuthorization,
    PrimitiveReleaseError,
    PrimitiveReleaseRecord,
    PrimitiveReleaseRevocation,
    inspect_release_artifacts,
)


class PrimitiveRepositoryError(ValueError):
    """Raised for durable registry input, consistency, or quota failures."""


class PrimitiveRepositoryConflict(PrimitiveRepositoryError):
    """Raised when compare-and-swap or immutable-tag state conflicts."""


@dataclass(frozen=True, slots=True)
class PrimitiveFileInput(RecordMixin):
    path: str
    role: CapsuleRole
    media_type: str
    content: bytes
    mode: str = "100644"


@dataclass(frozen=True, slots=True)
class StagedPrimitive(RecordMixin):
    handle: PrimitiveHandle
    tree: PrimitiveTree
    revision: PrimitiveRevision
    ref_update: PrimitiveRefUpdate


@dataclass(frozen=True, slots=True)
class ReleasedPrimitive(RecordMixin):
    staged: StagedPrimitive
    release: PrimitiveReleaseRecord


@dataclass(frozen=True, slots=True)
class StagedPrimitiveContent(RecordMixin):
    revision: PrimitiveRevision
    tree: PrimitiveTree
    blobs: Mapping[str, bytes]


@dataclass(frozen=True, slots=True)
class ImportedPrimitiveRegistry(RecordMixin):
    handles: int
    blobs: int
    trees: int
    revisions: int
    refs_created: int
    refs_unchanged: int
    revision_ids: tuple[str, ...]


class SQLitePrimitiveRepository:
    """Transactional reference adapter preserving primitive capsule identities."""

    def __init__(
        self,
        control: SQLiteControlPlane,
        *,
        max_files: int = 256,
        max_file_bytes: int = 2 * 1024 * 1024,
        max_total_bytes: int = 16 * 1024 * 1024,
        max_pack_bytes: int = 32 * 1024 * 1024,
    ):
        if min(max_files, max_file_bytes, max_total_bytes, max_pack_bytes) <= 0:
            raise PrimitiveRepositoryError("primitive repository limits must be positive")
        self.control = control
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes
        self.max_pack_bytes = max_pack_bytes

    def import_registry(
        self,
        tenant_id: str,
        source: PrimitiveRegistry,
        *,
        actor: str,
        imported_at: str,
        resource_id: str,
        conflict_ref_suffix: str | None = None,
    ) -> ImportedPrimitiveRegistry:
        """Atomically merge generated immutable objects into a tenant registry."""

        self.control.tenant(tenant_id)
        if not actor or not imported_at or not resource_id:
            raise PrimitiveRepositoryError("registry import provenance is required")
        for tree in source.trees.values():
            self._validate_files(
                tuple(
                    PrimitiveFileInput(
                        entry.path,
                        entry.role,
                        entry.blob.media_type,
                        source.blobs[entry.blob.digest],
                        entry.mode,
                    )
                    for entry in tree.entries
                )
            )
        with self.control._transaction() as connection:
            registry = self._load(tenant_id, connection)
            before = (
                len(registry.handles),
                len(registry.blobs),
                len(registry.trees),
                len(registry.revisions),
            )
            self._merge_immutable(registry.handles, source.handles, "primitive handle")
            self._merge_immutable(registry.blobs, source.blobs, "primitive blob")
            self._merge_immutable(
                registry.blob_descriptors,
                source.blob_descriptors,
                "primitive blob descriptor",
            )
            self._merge_immutable(registry.trees, source.trees, "primitive tree")
            self._merge_immutable(
                registry.revisions, source.revisions, "primitive revision"
            )
            source_updates = {
                (update.primitive_id, update.ref_kind, update.ref_name): update
                for update in source.ref_updates
            }
            created = 0
            unchanged = 0
            for key, revision_id in sorted(
                source.refs.items(),
                key=lambda item: (item[0][0], item[0][1].value, item[0][2]),
            ):
                original = source_updates[key]
                existing = registry.refs.get(key)
                if existing == revision_id:
                    unchanged += 1
                    continue
                if existing is not None:
                    if conflict_ref_suffix is None:
                        raise PrimitiveRepositoryConflict(
                            f"generated ref conflicts with existing {key[1].value}/{key[2]}"
                        )
                    versioned_key = (key[0], key[1], f"{key[2]}/{conflict_ref_suffix}")
                    versioned_existing = registry.refs.get(versioned_key)
                    if versioned_existing == revision_id:
                        unchanged += 1
                        continue
                    if versioned_existing is not None:
                        raise PrimitiveRepositoryConflict(
                            "generated version ref already points to another revision"
                        )
                    key = versioned_key
                registry.update_ref(
                    primitive=registry.handles[key[0]],
                    ref_kind=key[1],
                    ref_name=key[2],
                    new_revision_id=revision_id,
                    expected_revision_id=None,
                    actor=original.actor,
                    updated_at=original.updated_at,
                )
                created += 1
            self._persist(tenant_id, connection, registry)
            after = (
                len(registry.handles),
                len(registry.blobs),
                len(registry.trees),
                len(registry.revisions),
            )
            result = ImportedPrimitiveRegistry(
                after[0] - before[0],
                after[1] - before[1],
                after[2] - before[2],
                after[3] - before[3],
                created,
                unchanged,
                tuple(sorted(source.revisions)),
            )
            self.control._append_audit(
                connection,
                tenant_id=tenant_id,
                actor=actor,
                action="primitive.registry.imported",
                resource_id=resource_id,
                occurred_at=imported_at,
                detail=result.to_dict(),
            )
        return result

    def stage(
        self,
        tenant_id: str,
        *,
        namespace: str,
        name: str,
        files: Iterable[PrimitiveFileInput],
        contract_path: str,
        ref_kind: RefKind,
        ref_name: str,
        expected_revision_id: str | None,
        actor: str,
        created_at: str,
        message: str,
        graph_epoch_id: str | None = None,
        parent_revision_ids: Iterable[str] | None = None,
        generation_run_id: str | None = None,
        evidence_ids: Iterable[str] = (),
    ) -> StagedPrimitive:
        self.control.tenant(tenant_id)
        prepared = tuple(files)
        self._validate_files(prepared)
        if not actor or not message:
            raise PrimitiveRepositoryError("primitive author and message are required")
        producer = ProducerRef(
            "taedri.registry-api",
            "0.1.0",
            canonical_digest(
                {
                    "content_addressed": True,
                    "branch_compare_and_swap": True,
                    "immutable_tags": True,
                    "max_files": self.max_files,
                    "max_file_bytes": self.max_file_bytes,
                    "max_total_bytes": self.max_total_bytes,
                }
            ),
        )
        with self.control._transaction() as connection:
            registry = self._load(tenant_id, connection)
            handle = registry.register_handle(namespace, name)
            current = registry.refs.get((handle.identity.id, ref_kind, ref_name))
            if current != expected_revision_id:
                raise PrimitiveRepositoryConflict(
                    f"ref compare-and-swap failed: expected {expected_revision_id!r}, found {current!r}"
                )
            entries = []
            contract_digest = None
            for value in prepared:
                blob = registry.put_blob(value.content, value.media_type)
                entry = PrimitiveTreeEntry(value.path, value.role, blob, value.mode)
                entries.append(entry)
                if value.path == contract_path:
                    if value.role is not CapsuleRole.CONTRACT:
                        raise PrimitiveRepositoryError(
                            "contract_path must identify a contract-role file"
                        )
                    contract_digest = blob.digest
            if contract_digest is None:
                raise PrimitiveRepositoryError("contract_path is absent from primitive files")
            tree = registry.create_tree(entries)
            if parent_revision_ids is None:
                parents = (current,) if current is not None else ()
            else:
                parents = tuple(parent_revision_ids)
            revision = registry.commit(
                primitive=handle,
                tree_id=tree.identity.id,
                contract_digest=contract_digest,
                graph_epoch_id=graph_epoch_id,
                parent_revision_ids=parents,
                producer=producer,
                generation_run_id=generation_run_id,
                evidence_ids=evidence_ids,
                author=actor,
                created_at=created_at,
                message=message,
            )
            try:
                update = registry.update_ref(
                    primitive=handle,
                    ref_kind=ref_kind,
                    ref_name=ref_name,
                    new_revision_id=revision.identity.id,
                    expected_revision_id=expected_revision_id,
                    actor=actor,
                    updated_at=created_at,
                )
            except PrimitiveRegistryError as exc:
                if "compare-and-swap" in str(exc) or "immutable" in str(exc):
                    raise PrimitiveRepositoryConflict(str(exc)) from exc
                raise
            self._persist(tenant_id, connection, registry)
            self.control._append_audit(
                connection,
                tenant_id=tenant_id,
                actor=actor,
                action="primitive.revision.staged",
                resource_id=revision.identity.id,
                occurred_at=created_at,
                detail={
                    "primitive_id": handle.identity.id,
                    "tree_id": tree.identity.id,
                    "ref_kind": ref_kind.value,
                    "ref_name": ref_name,
                    "ref_update_id": update.identity.id,
                },
            )
        return StagedPrimitive(handle, tree, revision, update)

    def release(
        self,
        tenant_id: str,
        *,
        revision_id: str,
        ref_kind: RefKind,
        ref_name: str,
        acceptance_receipt_ref: str,
        authorization: PrimitiveReleaseAuthorization,
    ) -> ReleasedPrimitive:
        """Expose one staged revision only after complete executable acceptance."""

        self.control.tenant(tenant_id)
        try:
            acceptance = PrimitiveAcceptanceReceipt.from_mapping(
                self.control.job_payload(tenant_id, acceptance_receipt_ref)
            )
        except (PrimitiveReleaseError, ValueError) as exc:
            raise PrimitiveRepositoryError(
                "release requires a valid tenant-scoped acceptance receipt"
            ) from exc
        with self.control._transaction() as connection:
            registry = self._load(tenant_id, connection)
            try:
                revision = registry.revisions[revision_id]
                tree = registry.trees[revision.tree_id]
            except KeyError as exc:
                raise PrimitiveRepositoryError("unknown staged primitive revision") from exc
            current = registry.refs.get(
                (revision.primitive.identity.id, ref_kind, ref_name)
            )
            if current != revision_id:
                raise PrimitiveRepositoryConflict(
                    "release ref no longer points to the accepted revision"
                )
            artifacts = inspect_release_artifacts(tree, registry.blobs)
            duplicate = connection.execute(
                "SELECT primitive_id, revision_id FROM primitive_release "
                "WHERE tenant_id=? AND source_digest=? AND primitive_id<>? LIMIT 1",
                (tenant_id, artifacts.source_digest, revision.primitive.identity.id),
            ).fetchone()
            if duplicate is not None:
                raise PrimitiveRepositoryConflict(
                    "source implementation is already released under another primitive: "
                    + str(duplicate["revision_id"])
                )
            record = PrimitiveReleaseRecord.create(
                revision=revision,
                artifacts=artifacts,
                acceptance=acceptance,
                acceptance_receipt_ref=acceptance_receipt_ref,
                authorization=authorization,
                ref_kind=ref_kind,
                ref_name=ref_name,
            )
            existing = connection.execute(
                "SELECT record_json FROM primitive_release WHERE tenant_id=? AND release_id=?",
                (tenant_id, record.identity.id),
            ).fetchone()
            encoded = canonical_json_bytes(record).decode("utf-8")
            if existing is not None:
                if str(existing["record_json"]) != encoded:
                    raise PrimitiveRepositoryConflict("release identity collision")
            else:
                connection.execute(
                    "INSERT INTO primitive_release(tenant_id, release_id, primitive_id, "
                    "revision_id, tree_id, ref_kind, ref_name, source_digest, language, "
                    "runtime_version, search_document, released_at, record_json) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        tenant_id,
                        record.identity.id,
                        record.primitive_id,
                        record.revision_id,
                        record.tree_id,
                        record.ref_kind.value,
                        record.ref_name,
                        record.source_digest,
                        record.language,
                        record.runtime_version,
                        record.search_text,
                        record.released_at,
                        encoded,
                    ),
                )
            query_hit = connection.execute(
                "SELECT release_id FROM primitive_release WHERE tenant_id=? "
                "AND release_id=? AND lower(search_document) LIKE ?",
                (
                    tenant_id,
                    record.identity.id,
                    "%" + revision.primitive.name.lower() + "%",
                ),
            ).fetchone()
            if query_hit is None:
                raise PrimitiveRepositoryError(
                    "released primitive failed its mandatory queryability check"
                )
            self.control._append_audit(
                connection,
                tenant_id=tenant_id,
                actor=authorization.authorizer_id,
                action="primitive.revision.released",
                resource_id=record.identity.id,
                occurred_at=authorization.authorized_at,
                detail={
                    "primitive_id": record.primitive_id,
                    "revision_id": record.revision_id,
                    "acceptance_receipt_ref": record.acceptance_receipt_ref,
                    "assurance_level": record.assurance_level.value,
                },
            )
            ref_update = next(
                update
                for update in reversed(registry.ref_updates)
                if update.primitive_id == revision.primitive.identity.id
                and update.ref_kind is ref_kind
                and update.ref_name == ref_name
                and update.new_revision_id == revision_id
            )
        return ReleasedPrimitive(
            StagedPrimitive(revision.primitive, tree, revision, ref_update), record
        )

    def revoke(
        self,
        tenant_id: str,
        *,
        release_id: str,
        actor: str,
        policy_decision_id: str,
        reason: str,
        revoked_at: str,
    ) -> PrimitiveReleaseRevocation:
        """Append a release revocation and remove it atomically from serving queries."""

        self.control.tenant(tenant_id)
        with self.control._transaction() as connection:
            release = connection.execute(
                "SELECT primitive_id, revision_id FROM primitive_release "
                "WHERE tenant_id=? AND release_id=?",
                (tenant_id, release_id),
            ).fetchone()
            if release is None:
                raise LookupError(f"unknown primitive release: {release_id}")
            record = PrimitiveReleaseRevocation.create(
                release_id=release_id,
                primitive_id=str(release["primitive_id"]),
                revision_id=str(release["revision_id"]),
                actor=actor,
                policy_decision_id=policy_decision_id,
                reason=reason,
                revoked_at=revoked_at,
            )
            existing = connection.execute(
                "SELECT record_json FROM primitive_release_revocation "
                "WHERE tenant_id=? AND release_id=?",
                (tenant_id, release_id),
            ).fetchone()
            encoded = canonical_json_bytes(record).decode("utf-8")
            if existing is not None:
                if str(existing["record_json"]) != encoded:
                    raise PrimitiveRepositoryConflict(
                        "release is already revoked by another immutable decision"
                    )
                return record
            connection.execute(
                "INSERT INTO primitive_release_revocation(tenant_id, revocation_id, "
                "release_id, primitive_id, revision_id, revoked_at, record_json) "
                "VALUES(?, ?, ?, ?, ?, ?, ?)",
                (
                    tenant_id,
                    record.identity.id,
                    record.release_id,
                    record.primitive_id,
                    record.revision_id,
                    record.revoked_at,
                    encoded,
                ),
            )
            self.control._append_audit(
                connection,
                tenant_id=tenant_id,
                actor=actor,
                action="primitive.release.revoked",
                resource_id=record.identity.id,
                occurred_at=revoked_at,
                detail={
                    "release_id": release_id,
                    "primitive_id": record.primitive_id,
                    "revision_id": record.revision_id,
                    "policy_decision_id": policy_decision_id,
                    "reason": reason,
                },
            )
        return record

    def fork(
        self,
        tenant_id: str,
        *,
        source_revision_id: str,
        target_namespace: str,
        target_name: str,
        branch_name: str,
        actor: str,
        created_at: str,
        message: str,
    ) -> StagedPrimitive:
        self.control.tenant(tenant_id)
        producer = ProducerRef(
            "taedri.registry-api.fork",
            "0.1.0",
            canonical_digest({"cross_namespace_lineage": True, "copy_blobs": False}),
        )
        with self.control._transaction() as connection:
            registry = self._load(tenant_id, connection)
            try:
                revision = registry.fork(
                    source_revision_id=source_revision_id,
                    target_namespace=target_namespace,
                    target_name=target_name,
                    branch_name=branch_name,
                    producer=producer,
                    author=actor,
                    created_at=created_at,
                    message=message,
                )
            except PrimitiveRegistryError as exc:
                if "compare-and-swap" in str(exc):
                    raise PrimitiveRepositoryConflict(str(exc)) from exc
                raise
            handle = registry.handles[revision.primitive.identity.id]
            tree = registry.trees[revision.tree_id]
            update = registry.ref_updates[-1]
            self._persist(tenant_id, connection, registry)
            self.control._append_audit(
                connection,
                tenant_id=tenant_id,
                actor=actor,
                action="primitive.forked",
                resource_id=revision.identity.id,
                occurred_at=created_at,
                detail={
                    "source_revision_id": source_revision_id,
                    "target_primitive_id": handle.identity.id,
                    "ref_update_id": update.identity.id,
                },
            )
        return StagedPrimitive(handle, tree, revision, update)

    def get(
        self,
        tenant_id: str,
        namespace: str,
        name: str,
        *,
        ref_kind: RefKind = RefKind.BRANCH,
        ref_name: str = "main",
    ) -> dict[str, Any]:
        with self.control._connect() as connection:
            registry = self._load(tenant_id, connection)
            handle = PrimitiveHandle.create(namespace, name)
            release_row = connection.execute(
                "SELECT r.record_json, r.revision_id FROM primitive_release r "
                "WHERE r.tenant_id=? AND r.primitive_id=? AND r.ref_kind=? AND r.ref_name=? "
                "AND NOT EXISTS (SELECT 1 FROM primitive_release_revocation v "
                "WHERE v.tenant_id=r.tenant_id AND v.release_id=r.release_id) "
                "ORDER BY r.released_at DESC, r.release_id DESC LIMIT 1",
                (tenant_id, handle.identity.id, ref_kind.value, ref_name),
            ).fetchone()
        stored = registry.handles.get(handle.identity.id)
        if stored is None or release_row is None:
            raise LookupError(f"unknown primitive: {namespace}/{name}")
        revision = registry.revisions[str(release_row["revision_id"])]
        tree = registry.trees[revision.tree_id]
        with self.control._connect() as connection:
            released_rows = connection.execute(
                "SELECT r.record_json, r.ref_kind, r.ref_name, r.revision_id, r.released_at "
                "FROM primitive_release r WHERE r.tenant_id=? AND r.primitive_id=? "
                "AND NOT EXISTS (SELECT 1 FROM primitive_release_revocation v "
                "WHERE v.tenant_id=r.tenant_id AND v.release_id=r.release_id) "
                "ORDER BY r.released_at DESC, r.release_id DESC",
                (tenant_id, stored.identity.id),
            ).fetchall()
        refs_by_key: dict[tuple[str, str], dict[str, str]] = {}
        for row in released_rows:
            key = (str(row["ref_kind"]), str(row["ref_name"]))
            refs_by_key.setdefault(
                key,
                {
                    "ref_kind": key[0],
                    "ref_name": key[1],
                    "revision_id": str(row["revision_id"]),
                    "released_at": str(row["released_at"]),
                },
            )
        released_revision_ids = {str(row["revision_id"]) for row in released_rows}
        history = [
            item.to_dict()
            for item in sorted(
                (
                    item
                    for item in registry.revisions.values()
                    if item.primitive.identity.id == stored.identity.id
                    and item.identity.id in released_revision_ids
                ),
                key=lambda item: (item.created_at, item.identity.id),
            )
        ]
        return {
            "handle": stored,
            "resolved_ref": {
                "ref_kind": ref_kind.value,
                "ref_name": ref_name,
                "revision_id": revision.identity.id,
            },
            "revision": revision,
            "tree": tree,
            "release": json.loads(str(release_row["record_json"])),
            "refs": tuple(refs_by_key[key] for key in sorted(refs_by_key)),
            "history": history,
        }

    def list(
        self, tenant_id: str, *, query: str | None = None, limit: int = 100
    ) -> tuple[dict[str, Any], ...]:
        if not 1 <= limit <= 1000:
            raise PrimitiveRepositoryError("primitive list limit must be 1..1000")
        with self.control._connect() as connection:
            released = (
                "EXISTS (SELECT 1 FROM primitive_release r WHERE r.tenant_id=h.tenant_id "
                "AND r.primitive_id=h.primitive_id AND NOT EXISTS "
                "(SELECT 1 FROM primitive_release_revocation v WHERE "
                "v.tenant_id=r.tenant_id AND v.release_id=r.release_id))"
            )
            if query:
                escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                rows = connection.execute(
                    "SELECT h.record_json FROM primitive_handle h WHERE h.tenant_id=? AND "
                    + released
                    + " AND (h.namespace LIKE ? ESCAPE '\\' OR h.name LIKE ? ESCAPE '\\' "
                    "OR EXISTS (SELECT 1 FROM primitive_release r WHERE r.tenant_id=h.tenant_id "
                    "AND r.primitive_id=h.primitive_id AND r.search_document LIKE ? ESCAPE '\\' "
                    "AND NOT EXISTS (SELECT 1 FROM primitive_release_revocation v WHERE "
                    "v.tenant_id=r.tenant_id AND v.release_id=r.release_id))) "
                    "ORDER BY h.namespace, h.name LIMIT ?",
                    (
                        tenant_id,
                        f"%{escaped}%",
                        f"%{escaped}%",
                        f"%{escaped}%",
                        limit,
                    ),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT h.record_json FROM primitive_handle h WHERE h.tenant_id=? AND "
                    + released
                    + " ORDER BY h.namespace, h.name LIMIT ?",
                    (tenant_id, limit),
                ).fetchall()
            result = []
            for row in rows:
                handle = _handle(json.loads(str(row["record_json"])))
                refs = connection.execute(
                    "SELECT r.ref_kind, r.ref_name, r.revision_id, r.released_at "
                    "FROM primitive_release r WHERE r.tenant_id=? AND r.primitive_id=? "
                    "AND NOT EXISTS (SELECT 1 FROM primitive_release_revocation v "
                    "WHERE v.tenant_id=r.tenant_id AND v.release_id=r.release_id) "
                    "ORDER BY r.ref_kind, r.ref_name",
                    (tenant_id, handle.identity.id),
                ).fetchall()
                result.append(
                    {
                        "handle": handle.to_dict(),
                        "refs": [dict(item) for item in refs],
                    }
                )
        return tuple(result)

    def pack(
        self,
        tenant_id: str,
        namespace: str,
        name: str,
        *,
        ref_kind: RefKind = RefKind.BRANCH,
        ref_name: str = "main",
        include_roles: Iterable[CapsuleRole] | None = None,
        have_digests: Iterable[str] = (),
        include_history: bool = False,
    ) -> tuple[PrimitivePack, bytes]:
        released = self.get(
            tenant_id, namespace, name, ref_kind=ref_kind, ref_name=ref_name
        )
        revision = released["revision"]
        with self.control._connect() as connection:
            registry = self._load(tenant_id, connection)
        pack = registry.build_pack(
            revision.identity.id,
            include_roles=include_roles,
            have_digests=have_digests,
            include_history=include_history,
        )
        encoded = encode_primitive_pack(pack, registry.payloads_for(pack))
        if len(encoded) > self.max_pack_bytes:
            raise PrimitiveRepositoryError("encoded primitive pack exceeds delivery limit")
        return pack, encoded

    def pack_revision(
        self,
        tenant_id: str,
        revision_id: str,
        *,
        include_roles: Iterable[CapsuleRole] | None = None,
        have_digests: Iterable[str] = (),
        include_history: bool = False,
    ) -> tuple[PrimitivePack, bytes]:
        with self.control._connect() as connection:
            registry = self._load(tenant_id, connection)
        if revision_id not in registry.revisions:
            raise LookupError(f"unknown primitive revision: {revision_id}")
        pack = registry.build_pack(
            revision_id,
            include_roles=include_roles,
            have_digests=have_digests,
            include_history=include_history,
        )
        encoded = encode_primitive_pack(pack, registry.payloads_for(pack))
        if len(encoded) > self.max_pack_bytes:
            raise PrimitiveRepositoryError("encoded primitive pack exceeds delivery limit")
        return pack, encoded

    def staged_revision(
        self, tenant_id: str, revision_id: str
    ) -> StagedPrimitiveContent:
        """Return immutable candidate content for an internal acceptance worker."""

        self.control.tenant(tenant_id)
        with self.control._connect() as connection:
            registry = self._load(tenant_id, connection)
        try:
            revision = registry.revisions[revision_id]
            tree = registry.trees[revision.tree_id]
        except KeyError as exc:
            raise LookupError(f"unknown staged primitive revision: {revision_id}") from exc
        needed = {entry.blob.digest for entry in tree.entries}
        return StagedPrimitiveContent(
            revision,
            tree,
            {digest: registry.blobs[digest] for digest in sorted(needed)},
        )

    def _validate_files(self, files: tuple[PrimitiveFileInput, ...]) -> None:
        if not files or len(files) > self.max_files:
            raise PrimitiveRepositoryError("primitive file count is outside the configured limit")
        total = 0
        for value in files:
            if len(value.content) > self.max_file_bytes:
                raise PrimitiveRepositoryError(f"primitive file exceeds limit: {value.path}")
            total += len(value.content)
        if total > self.max_total_bytes:
            raise PrimitiveRepositoryError("primitive content exceeds the total byte limit")

    @staticmethod
    def _merge_immutable(
        target: dict[str, Any], source: Mapping[str, Any], label: str
    ) -> None:
        for identity, value in source.items():
            existing = target.get(identity)
            if existing is not None and existing != value:
                raise PrimitiveRepositoryConflict(f"{label} identity collision: {identity}")
            target.setdefault(identity, value)

    def _load(self, tenant_id: str, connection: Any) -> PrimitiveRegistry:
        registry = PrimitiveRegistry()
        for row in connection.execute(
            "SELECT record_json FROM primitive_handle WHERE tenant_id=? ORDER BY primitive_id",
            (tenant_id,),
        ):
            handle = _handle(json.loads(str(row["record_json"])))
            registry.handles[handle.identity.id] = handle
        for row in connection.execute(
            "SELECT digest, size_bytes, media_type, content FROM primitive_blob "
            "WHERE tenant_id=? ORDER BY digest",
            (tenant_id,),
        ):
            descriptor = BlobDescriptor(
                str(row["digest"]), int(row["size_bytes"]), str(row["media_type"])
            )
            content = bytes(row["content"])
            descriptor.validate(content)
            registry.blobs[descriptor.digest] = content
            registry.blob_descriptors[descriptor.digest] = descriptor
        for row in connection.execute(
            "SELECT record_json FROM primitive_tree WHERE tenant_id=? ORDER BY tree_id",
            (tenant_id,),
        ):
            tree = _tree(json.loads(str(row["record_json"])))
            registry.trees[tree.identity.id] = tree
        for row in connection.execute(
            "SELECT record_json FROM primitive_revision WHERE tenant_id=? ORDER BY created_at, revision_id",
            (tenant_id,),
        ):
            revision = _revision(json.loads(str(row["record_json"])), registry.handles)
            registry.revisions[revision.identity.id] = revision
        for row in connection.execute(
            "SELECT primitive_id, ref_kind, ref_name, revision_id FROM primitive_ref "
            "WHERE tenant_id=? ORDER BY primitive_id, ref_kind, ref_name",
            (tenant_id,),
        ):
            registry.refs[
                (str(row["primitive_id"]), RefKind(str(row["ref_kind"])), str(row["ref_name"]))
            ] = str(row["revision_id"])
        for row in connection.execute(
            "SELECT record_json FROM primitive_ref_update WHERE tenant_id=? ORDER BY sequence",
            (tenant_id,),
        ):
            registry.ref_updates.append(_ref_update(json.loads(str(row["record_json"]))))
        return registry

    def _persist(self, tenant_id: str, connection: Any, registry: PrimitiveRegistry) -> None:
        for handle in registry.handles.values():
            connection.execute(
                "INSERT OR IGNORE INTO primitive_handle(tenant_id, primitive_id, namespace, "
                "name, record_json) VALUES(?, ?, ?, ?, ?)",
                (
                    tenant_id,
                    handle.identity.id,
                    handle.namespace,
                    handle.name,
                    canonical_json_bytes(handle).decode("utf-8"),
                ),
            )
        for digest, content in registry.blobs.items():
            descriptor = registry.blob_descriptors[digest]
            connection.execute(
                "INSERT OR IGNORE INTO primitive_blob(tenant_id, digest, size_bytes, "
                "media_type, content) VALUES(?, ?, ?, ?, ?)",
                (tenant_id, digest, descriptor.size_bytes, descriptor.media_type, content),
            )
        for tree in registry.trees.values():
            connection.execute(
                "INSERT OR IGNORE INTO primitive_tree(tenant_id, tree_id, record_json) "
                "VALUES(?, ?, ?)",
                (tenant_id, tree.identity.id, canonical_json_bytes(tree).decode("utf-8")),
            )
        for revision in registry.revisions.values():
            connection.execute(
                "INSERT OR IGNORE INTO primitive_revision(tenant_id, revision_id, primitive_id, "
                "tree_id, created_at, record_json) VALUES(?, ?, ?, ?, ?, ?)",
                (
                    tenant_id,
                    revision.identity.id,
                    revision.primitive.identity.id,
                    revision.tree_id,
                    revision.created_at,
                    canonical_json_bytes(revision).decode("utf-8"),
                ),
            )
        sequence_by_key = {
            (update.primitive_id, update.ref_kind, update.ref_name): update.sequence
            for update in registry.ref_updates
        }
        for (primitive_id, kind, name), revision_id in registry.refs.items():
            connection.execute(
                "INSERT INTO primitive_ref(tenant_id, primitive_id, ref_kind, ref_name, "
                "revision_id, updated_sequence) VALUES(?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(tenant_id, primitive_id, ref_kind, ref_name) DO UPDATE SET "
                "revision_id=excluded.revision_id, updated_sequence=excluded.updated_sequence",
                (
                    tenant_id,
                    primitive_id,
                    kind.value,
                    name,
                    revision_id,
                    sequence_by_key[(primitive_id, kind, name)],
                ),
            )
        for update in registry.ref_updates:
            connection.execute(
                "INSERT OR IGNORE INTO primitive_ref_update(tenant_id, sequence, update_id, "
                "primitive_id, ref_kind, ref_name, record_json) VALUES(?, ?, ?, ?, ?, ?, ?)",
                (
                    tenant_id,
                    update.sequence,
                    update.identity.id,
                    update.primitive_id,
                    update.ref_kind.value,
                    update.ref_name,
                    canonical_json_bytes(update).decode("utf-8"),
                ),
            )


def _identity(value: Mapping[str, Any]) -> IdentityRecord:
    identity = IdentityRecord(
        str(value.get("id", "")), str(value.get("kind", "")), value.get("canonical_key")
    )
    identity.validate()
    return identity


def _handle(value: Mapping[str, Any]) -> PrimitiveHandle:
    decoded = PrimitiveHandle(
        _identity(_mapping(value.get("identity"), "handle identity")),
        str(value.get("namespace", "")),
        str(value.get("name", "")),
    )
    if PrimitiveHandle.create(decoded.namespace, decoded.name) != decoded:
        raise PrimitiveRepositoryError("stored primitive handle is invalid")
    return decoded


def _blob(value: Mapping[str, Any]) -> BlobDescriptor:
    return BlobDescriptor(
        str(value.get("digest", "")),
        int(value.get("size_bytes", -1)),
        str(value.get("media_type", "")),
    )


def _tree(value: Mapping[str, Any]) -> PrimitiveTree:
    entries_value = value.get("entries")
    if not isinstance(entries_value, list):
        raise PrimitiveRepositoryError("stored primitive tree entries are invalid")
    entries = tuple(
        PrimitiveTreeEntry(
            str(item.get("path", "")),
            CapsuleRole(str(item.get("role", ""))),
            _blob(_mapping(item.get("blob"), "tree blob")),
            str(item.get("mode", "")),
        )
        for item in (_mapping(entry, "tree entry") for entry in entries_value)
    )
    decoded = PrimitiveTree(
        _identity(_mapping(value.get("identity"), "tree identity")),
        str(value.get("format_version", "")),
        entries,
    )
    if PrimitiveTree.create(entries) != decoded:
        raise PrimitiveRepositoryError("stored primitive tree is invalid")
    return decoded


def _revision(
    value: Mapping[str, Any], handles: Mapping[str, PrimitiveHandle]
) -> PrimitiveRevision:
    primitive_value = _mapping(value.get("primitive"), "revision primitive")
    primitive_id = str(_mapping(primitive_value.get("identity"), "primitive identity").get("id", ""))
    try:
        primitive = handles[primitive_id]
    except KeyError as exc:
        raise PrimitiveRepositoryError("stored revision references an unknown primitive") from exc
    producer_value = _mapping(value.get("producer"), "revision producer")
    producer = ProducerRef(
        str(producer_value.get("id", "")),
        str(producer_value.get("version", "")),
        str(producer_value.get("config_digest", "")),
    )
    decoded = PrimitiveRevision(
        _identity(_mapping(value.get("identity"), "revision identity")),
        str(value.get("format_version", "")),
        primitive,
        str(value.get("tree_id", "")),
        str(value.get("contract_digest", "")),
        str(value["graph_epoch_id"]) if value.get("graph_epoch_id") is not None else None,
        tuple(str(item) for item in value.get("parent_revision_ids", [])),
        str(value["upstream_revision_id"]) if value.get("upstream_revision_id") is not None else None,
        producer,
        str(value["generation_run_id"]) if value.get("generation_run_id") is not None else None,
        tuple(str(item) for item in value.get("evidence_ids", [])),
        str(value.get("author", "")),
        str(value.get("created_at", "")),
        str(value.get("message", "")),
    )
    expected = PrimitiveRevision.create(
        primitive=primitive,
        tree_id=decoded.tree_id,
        contract_digest=decoded.contract_digest,
        graph_epoch_id=decoded.graph_epoch_id,
        parent_revision_ids=decoded.parent_revision_ids,
        upstream_revision_id=decoded.upstream_revision_id,
        producer=producer,
        generation_run_id=decoded.generation_run_id,
        evidence_ids=decoded.evidence_ids,
        author=decoded.author,
        created_at=decoded.created_at,
        message=decoded.message,
    )
    if expected != decoded:
        raise PrimitiveRepositoryError("stored primitive revision is invalid")
    return decoded


def _ref_update(value: Mapping[str, Any]) -> PrimitiveRefUpdate:
    decoded = PrimitiveRefUpdate(
        _identity(_mapping(value.get("identity"), "ref update identity")),
        str(value.get("primitive_id", "")),
        RefKind(str(value.get("ref_kind", ""))),
        str(value.get("ref_name", "")),
        int(value.get("sequence", 0)),
        str(value["old_revision_id"]) if value.get("old_revision_id") is not None else None,
        str(value.get("new_revision_id", "")),
        str(value.get("actor", "")),
        str(value.get("updated_at", "")),
        bool(value.get("forced", False)),
    )
    expected = PrimitiveRefUpdate.create(
        primitive_id=decoded.primitive_id,
        ref_kind=decoded.ref_kind,
        ref_name=decoded.ref_name,
        sequence=decoded.sequence,
        old_revision_id=decoded.old_revision_id,
        new_revision_id=decoded.new_revision_id,
        actor=decoded.actor,
        updated_at=decoded.updated_at,
        forced=decoded.forced,
    )
    if expected != decoded:
        raise PrimitiveRepositoryError("stored primitive ref update is invalid")
    return decoded


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PrimitiveRepositoryError(f"{name} must be an object")
    return value
