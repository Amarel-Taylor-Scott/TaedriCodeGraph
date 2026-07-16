"""Registry-native primitive capsules with Git-like history and thin downloads.

Capsules are immutable content containers.  A capsule is not a released primitive
until the independent release gate records executable acceptance evidence.
"""

from __future__ import annotations

import gzip
import io
import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Iterable, Mapping

from .canonical import canonical_json_bytes, sha256_digest
from .contracts import ProducerRef, RecordMixin
from .identity import IdentityRecord

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_HANDLE_PART = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?$")
_MEDIA_TYPE = re.compile(
    r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+(?:\+[A-Za-z0-9._-]+)?$"
)
_FORBIDDEN_REF_CHARACTERS = frozenset(" ~^:?*[\\")
_PACK_MAGIC = b"TCGPACK1"


class PrimitiveRegistryError(ValueError):
    """Raised when a capsule, history operation, or pack violates the contract."""


class CapsuleRole(str, Enum):
    SOURCE = "source"
    CONTRACT = "contract"
    DESCRIPTOR = "descriptor"
    TEST = "test"
    VERIFIER = "verifier"
    DEPENDENCY_LOCK = "dependency_lock"
    GRAPH_DELTA = "graph_delta"
    DOCUMENTATION = "documentation"
    RUNTIME = "runtime"
    EXAMPLE = "example"
    LICENSE = "license"
    PROVENANCE = "provenance"


class RefKind(str, Enum):
    BRANCH = "branch"
    TAG = "tag"


def _require_digest(value: str, field_name: str) -> None:
    if not _DIGEST.fullmatch(value):
        raise PrimitiveRegistryError(f"{field_name} must be a lowercase sha256 digest")


def _validate_tree_path(value: str) -> None:
    path = PurePosixPath(value)
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise PrimitiveRegistryError(f"unsafe capsule path: {value!r}")


def _validate_ref_name(value: str) -> None:
    path = PurePosixPath(value)
    if (
        not value
        or value.startswith(("/", "."))
        or value.endswith(("/", ".", ".lock"))
        or ".." in value
        or "@{" in value
        or path.as_posix() != value
        or any(character in _FORBIDDEN_REF_CHARACTERS for character in value)
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise PrimitiveRegistryError(f"invalid ref name: {value!r}")


@dataclass(frozen=True, slots=True)
class BlobDescriptor(RecordMixin):
    digest: str
    size_bytes: int
    media_type: str

    def __post_init__(self) -> None:
        _require_digest(self.digest, "blob digest")
        if self.size_bytes < 0:
            raise PrimitiveRegistryError("blob size cannot be negative")
        if not _MEDIA_TYPE.fullmatch(self.media_type):
            raise PrimitiveRegistryError(f"invalid media type: {self.media_type!r}")

    @classmethod
    def create(cls, content: bytes, media_type: str) -> "BlobDescriptor":
        return cls(sha256_digest(content), len(content), media_type)

    def validate(self, content: bytes) -> None:
        if len(content) != self.size_bytes or sha256_digest(content) != self.digest:
            raise PrimitiveRegistryError(f"blob content does not match {self.digest}")


@dataclass(frozen=True, slots=True)
class PrimitiveHandle(RecordMixin):
    identity: IdentityRecord
    namespace: str
    name: str

    @classmethod
    def create(cls, namespace: str, name: str) -> "PrimitiveHandle":
        if not _HANDLE_PART.fullmatch(namespace) or not _HANDLE_PART.fullmatch(name):
            raise PrimitiveRegistryError("primitive namespace and name must be normalized")
        key = {"namespace": namespace, "name": name}
        return cls(IdentityRecord.create("primitive", key), namespace, name)


@dataclass(frozen=True, slots=True)
class PrimitiveTreeEntry(RecordMixin):
    path: str
    role: CapsuleRole
    blob: BlobDescriptor
    mode: str = "100644"

    def __post_init__(self) -> None:
        _validate_tree_path(self.path)
        if self.mode not in {"100644", "100755"}:
            raise PrimitiveRegistryError("capsule entry mode must be 100644 or 100755")


@dataclass(frozen=True, slots=True)
class PrimitiveTree(RecordMixin):
    identity: IdentityRecord
    format_version: str
    entries: tuple[PrimitiveTreeEntry, ...]

    @classmethod
    def create(cls, entries: Iterable[PrimitiveTreeEntry]) -> "PrimitiveTree":
        ordered = tuple(sorted(entries, key=lambda entry: entry.path))
        if not ordered:
            raise PrimitiveRegistryError("a primitive tree cannot be empty")
        paths = [entry.path for entry in ordered]
        if len(paths) != len(set(paths)):
            raise PrimitiveRegistryError("primitive tree paths must be unique")
        key = {
            "format_version": "1.0.0",
            "entries": [entry.to_dict() for entry in ordered],
        }
        return cls(IdentityRecord.create("primitive_tree", key), "1.0.0", ordered)


@dataclass(frozen=True, slots=True)
class PrimitiveRevision(RecordMixin):
    identity: IdentityRecord
    format_version: str
    primitive: PrimitiveHandle
    tree_id: str
    contract_digest: str
    graph_epoch_id: str | None
    parent_revision_ids: tuple[str, ...]
    upstream_revision_id: str | None
    producer: ProducerRef
    generation_run_id: str | None
    evidence_ids: tuple[str, ...]
    author: str
    created_at: str
    message: str

    @classmethod
    def create(
        cls,
        *,
        primitive: PrimitiveHandle,
        tree_id: str,
        contract_digest: str,
        producer: ProducerRef,
        author: str,
        created_at: str,
        message: str,
        graph_epoch_id: str | None = None,
        parent_revision_ids: Iterable[str] = (),
        upstream_revision_id: str | None = None,
        generation_run_id: str | None = None,
        evidence_ids: Iterable[str] = (),
    ) -> "PrimitiveRevision":
        _require_digest(contract_digest, "contract digest")
        parents = tuple(parent_revision_ids)
        if len(parents) != len(set(parents)):
            raise PrimitiveRegistryError("revision parents must be unique")
        if upstream_revision_id is not None and upstream_revision_id not in parents:
            raise PrimitiveRegistryError("a fork's upstream revision must also be a parent")
        if not author or not created_at or not message:
            raise PrimitiveRegistryError("revision author, created_at, and message are required")
        evidence = tuple(sorted(set(evidence_ids)))
        key = {
            "format_version": "1.0.0",
            "primitive_id": primitive.identity.id,
            "tree_id": tree_id,
            "contract_digest": contract_digest,
            "graph_epoch_id": graph_epoch_id,
            "parent_revision_ids": parents,
            "upstream_revision_id": upstream_revision_id,
            "producer": producer.to_dict(),
            "generation_run_id": generation_run_id,
            "evidence_ids": evidence,
            "author": author,
            "created_at": created_at,
            "message": message,
        }
        return cls(
            IdentityRecord.create("primitive_revision", key),
            "1.0.0",
            primitive,
            tree_id,
            contract_digest,
            graph_epoch_id,
            parents,
            upstream_revision_id,
            producer,
            generation_run_id,
            evidence,
            author,
            created_at,
            message,
        )


@dataclass(frozen=True, slots=True)
class PrimitiveRefUpdate(RecordMixin):
    identity: IdentityRecord
    primitive_id: str
    ref_kind: RefKind
    ref_name: str
    sequence: int
    old_revision_id: str | None
    new_revision_id: str
    actor: str
    updated_at: str
    forced: bool

    @classmethod
    def create(
        cls,
        *,
        primitive_id: str,
        ref_kind: RefKind,
        ref_name: str,
        sequence: int,
        old_revision_id: str | None,
        new_revision_id: str,
        actor: str,
        updated_at: str,
        forced: bool,
    ) -> "PrimitiveRefUpdate":
        _validate_ref_name(ref_name)
        if sequence <= 0 or not actor or not updated_at:
            raise PrimitiveRegistryError("ref sequence, actor, and updated_at are required")
        key = {
            "primitive_id": primitive_id,
            "ref_kind": ref_kind.value,
            "ref_name": ref_name,
            "sequence": sequence,
            "old_revision_id": old_revision_id,
            "new_revision_id": new_revision_id,
            "actor": actor,
            "updated_at": updated_at,
            "forced": forced,
        }
        return cls(
            IdentityRecord.create("primitive_ref_update", key),
            primitive_id,
            ref_kind,
            ref_name,
            sequence,
            old_revision_id,
            new_revision_id,
            actor,
            updated_at,
            forced,
        )


@dataclass(frozen=True, slots=True)
class PrimitivePackEntry(RecordMixin):
    revision_id: str
    tree_id: str
    path: str
    role: CapsuleRole
    blob: BlobDescriptor
    mode: str


@dataclass(frozen=True, slots=True)
class PrimitivePack(RecordMixin):
    identity: IdentityRecord
    format_version: str
    revision_ids: tuple[str, ...]
    tree_ids: tuple[str, ...]
    entries: tuple[PrimitivePackEntry, ...]
    included_blobs: tuple[BlobDescriptor, ...]
    assumed_present_digests: tuple[str, ...]
    graph_epoch_ids: tuple[str, ...]
    raw_payload_bytes: int

    @classmethod
    def create(
        cls,
        *,
        revision_ids: Iterable[str],
        tree_ids: Iterable[str],
        entries: Iterable[PrimitivePackEntry],
        included_blobs: Iterable[BlobDescriptor],
        assumed_present_digests: Iterable[str],
        graph_epoch_ids: Iterable[str],
    ) -> "PrimitivePack":
        revisions = tuple(sorted(set(revision_ids)))
        trees = tuple(sorted(set(tree_ids)))
        if not revisions or not trees:
            raise PrimitiveRegistryError("a pack requires at least one revision and tree")
        ordered_entries = tuple(
            sorted(entries, key=lambda entry: (entry.revision_id, entry.path))
        )
        included_by_digest: dict[str, BlobDescriptor] = {}
        for blob in sorted(included_blobs, key=lambda item: (item.digest, item.media_type)):
            existing = included_by_digest.setdefault(blob.digest, blob)
            if existing.size_bytes != blob.size_bytes:  # pragma: no cover - digest guard
                raise PrimitiveRegistryError("one digest cannot declare several sizes")
        included = tuple(included_by_digest[key] for key in sorted(included_by_digest))
        assumed = tuple(sorted(set(assumed_present_digests)))
        if set(included_by_digest).intersection(assumed):
            raise PrimitiveRegistryError("a pack cannot include and assume the same blob")
        entry_digests = {entry.blob.digest for entry in ordered_entries}
        if entry_digests != set(included_by_digest).union(assumed):
            raise PrimitiveRegistryError("every pack entry blob must be included or assumed")
        graph_epochs = tuple(sorted(set(graph_epoch_ids)))
        raw_payload_bytes = sum(blob.size_bytes for blob in included)
        key = {
            "format_version": "1.0.0",
            "revision_ids": revisions,
            "tree_ids": trees,
            "entries": [entry.to_dict() for entry in ordered_entries],
            "included_blobs": [blob.to_dict() for blob in included],
            "assumed_present_digests": assumed,
            "graph_epoch_ids": graph_epochs,
            "raw_payload_bytes": raw_payload_bytes,
        }
        return cls(
            IdentityRecord.create("primitive_pack", key),
            "1.0.0",
            revisions,
            trees,
            ordered_entries,
            included,
            assumed,
            graph_epochs,
            raw_payload_bytes,
        )


class PrimitiveRegistry:
    """In-memory reference implementation of the registry contract."""

    def __init__(self) -> None:
        self.handles: dict[str, PrimitiveHandle] = {}
        self.blobs: dict[str, bytes] = {}
        self.blob_descriptors: dict[str, BlobDescriptor] = {}
        self.trees: dict[str, PrimitiveTree] = {}
        self.revisions: dict[str, PrimitiveRevision] = {}
        self.refs: dict[tuple[str, RefKind, str], str] = {}
        self.ref_updates: list[PrimitiveRefUpdate] = []

    def put_blob(self, content: bytes, media_type: str) -> BlobDescriptor:
        descriptor = BlobDescriptor.create(content, media_type)
        existing = self.blobs.get(descriptor.digest)
        if existing is not None and existing != content:  # pragma: no cover - SHA-256 guard
            raise PrimitiveRegistryError(f"digest collision at {descriptor.digest}")
        self.blobs[descriptor.digest] = content
        self.blob_descriptors.setdefault(descriptor.digest, descriptor)
        return descriptor

    def register_handle(self, namespace: str, name: str) -> PrimitiveHandle:
        handle = PrimitiveHandle.create(namespace, name)
        self.handles.setdefault(handle.identity.id, handle)
        return self.handles[handle.identity.id]

    def create_tree(self, entries: Iterable[PrimitiveTreeEntry]) -> PrimitiveTree:
        tree = PrimitiveTree.create(entries)
        for entry in tree.entries:
            content = self.blobs.get(entry.blob.digest)
            if content is None:
                raise PrimitiveRegistryError(
                    f"tree references an unknown blob: {entry.blob.digest}"
                )
            entry.blob.validate(content)
        self.trees.setdefault(tree.identity.id, tree)
        return self.trees[tree.identity.id]

    def commit(
        self,
        *,
        primitive: PrimitiveHandle,
        tree_id: str,
        contract_digest: str,
        producer: ProducerRef,
        author: str,
        created_at: str,
        message: str,
        graph_epoch_id: str | None = None,
        parent_revision_ids: Iterable[str] = (),
        upstream_revision_id: str | None = None,
        generation_run_id: str | None = None,
        evidence_ids: Iterable[str] = (),
    ) -> PrimitiveRevision:
        if primitive.identity.id not in self.handles:
            raise PrimitiveRegistryError("primitive handle is not registered")
        tree = self.trees.get(tree_id)
        if tree is None:
            raise PrimitiveRegistryError(f"unknown primitive tree: {tree_id}")
        contract_entries = [
            entry for entry in tree.entries if entry.role is CapsuleRole.CONTRACT
        ]
        if contract_digest not in {entry.blob.digest for entry in contract_entries}:
            raise PrimitiveRegistryError("revision contract must be a contract-role tree blob")
        parents = tuple(parent_revision_ids)
        for parent in parents:
            if parent not in self.revisions:
                raise PrimitiveRegistryError(f"unknown parent revision: {parent}")
        revision = PrimitiveRevision.create(
            primitive=primitive,
            tree_id=tree_id,
            contract_digest=contract_digest,
            graph_epoch_id=graph_epoch_id,
            parent_revision_ids=parents,
            upstream_revision_id=upstream_revision_id,
            producer=producer,
            generation_run_id=generation_run_id,
            evidence_ids=evidence_ids,
            author=author,
            created_at=created_at,
            message=message,
        )
        self.revisions.setdefault(revision.identity.id, revision)
        return self.revisions[revision.identity.id]

    def resolve_ref(
        self, primitive: PrimitiveHandle, ref_kind: RefKind, ref_name: str
    ) -> PrimitiveRevision:
        _validate_ref_name(ref_name)
        revision_id = self.refs.get((primitive.identity.id, ref_kind, ref_name))
        if revision_id is None:
            raise KeyError(f"unknown primitive ref: {ref_kind.value}/{ref_name}")
        return self.revisions[revision_id]

    def update_ref(
        self,
        *,
        primitive: PrimitiveHandle,
        ref_kind: RefKind,
        ref_name: str,
        new_revision_id: str,
        expected_revision_id: str | None,
        actor: str,
        updated_at: str,
        force: bool = False,
    ) -> PrimitiveRefUpdate:
        _validate_ref_name(ref_name)
        revision = self.revisions.get(new_revision_id)
        if revision is None:
            raise PrimitiveRegistryError(f"unknown new revision: {new_revision_id}")
        if revision.primitive.identity.id != primitive.identity.id:
            raise PrimitiveRegistryError("a ref cannot point at another primitive's revision")
        key = (primitive.identity.id, ref_kind, ref_name)
        current = self.refs.get(key)
        if current != expected_revision_id:
            raise PrimitiveRegistryError(
                f"ref compare-and-swap failed: expected {expected_revision_id!r}, found {current!r}"
            )
        if ref_kind is RefKind.TAG and current is not None:
            raise PrimitiveRegistryError("release tags are immutable")
        if current is not None and not force and not self._is_ancestor(current, new_revision_id):
            raise PrimitiveRegistryError("branch update is not a fast-forward")
        update = PrimitiveRefUpdate.create(
            primitive_id=primitive.identity.id,
            ref_kind=ref_kind,
            ref_name=ref_name,
            sequence=len(self.ref_updates) + 1,
            old_revision_id=current,
            new_revision_id=new_revision_id,
            actor=actor,
            updated_at=updated_at,
            forced=force,
        )
        self.refs[key] = new_revision_id
        self.ref_updates.append(update)
        return update

    def fork(
        self,
        *,
        source_revision_id: str,
        target_namespace: str,
        target_name: str,
        branch_name: str,
        producer: ProducerRef,
        author: str,
        created_at: str,
        message: str,
    ) -> PrimitiveRevision:
        source = self.revisions.get(source_revision_id)
        if source is None:
            raise PrimitiveRegistryError(f"unknown source revision: {source_revision_id}")
        target = self.register_handle(target_namespace, target_name)
        revision = self.commit(
            primitive=target,
            tree_id=source.tree_id,
            contract_digest=source.contract_digest,
            graph_epoch_id=source.graph_epoch_id,
            parent_revision_ids=(source_revision_id,),
            upstream_revision_id=source_revision_id,
            producer=producer,
            author=author,
            created_at=created_at,
            message=message,
        )
        self.update_ref(
            primitive=target,
            ref_kind=RefKind.BRANCH,
            ref_name=branch_name,
            new_revision_id=revision.identity.id,
            expected_revision_id=None,
            actor=author,
            updated_at=created_at,
        )
        return revision

    def merge(
        self,
        *,
        primitive: PrimitiveHandle,
        branch_name: str,
        current_revision_id: str,
        merged_revision_id: str,
        result_tree_id: str,
        contract_digest: str,
        producer: ProducerRef,
        author: str,
        created_at: str,
        message: str,
        graph_epoch_id: str | None = None,
    ) -> PrimitiveRevision:
        revision = self.commit(
            primitive=primitive,
            tree_id=result_tree_id,
            contract_digest=contract_digest,
            graph_epoch_id=graph_epoch_id,
            parent_revision_ids=(current_revision_id, merged_revision_id),
            producer=producer,
            author=author,
            created_at=created_at,
            message=message,
        )
        self.update_ref(
            primitive=primitive,
            ref_kind=RefKind.BRANCH,
            ref_name=branch_name,
            new_revision_id=revision.identity.id,
            expected_revision_id=current_revision_id,
            actor=author,
            updated_at=created_at,
        )
        return revision

    def build_pack(
        self,
        revision_id: str,
        *,
        include_roles: Iterable[CapsuleRole] | None = None,
        have_digests: Iterable[str] = (),
        include_history: bool = False,
    ) -> PrimitivePack:
        if revision_id not in self.revisions:
            raise PrimitiveRegistryError(f"unknown revision: {revision_id}")
        roles = set(include_roles) if include_roles is not None else set(CapsuleRole)
        have = set(have_digests)
        for digest in have:
            _require_digest(digest, "have digest")
        revision_ids = self._revision_closure(revision_id) if include_history else {revision_id}
        tree_ids: set[str] = set()
        entries: list[PrimitivePackEntry] = []
        graph_epoch_ids: set[str] = set()
        selected_blobs: dict[str, BlobDescriptor] = {}
        for selected_revision_id in sorted(revision_ids):
            revision = self.revisions[selected_revision_id]
            tree = self.trees[revision.tree_id]
            tree_ids.add(tree.identity.id)
            if revision.graph_epoch_id is not None:
                graph_epoch_ids.add(revision.graph_epoch_id)
            for entry in tree.entries:
                if entry.role not in roles:
                    continue
                entries.append(
                    PrimitivePackEntry(
                        selected_revision_id,
                        tree.identity.id,
                        entry.path,
                        entry.role,
                        entry.blob,
                        entry.mode,
                    )
                )
                existing = selected_blobs.get(entry.blob.digest)
                if existing is None or entry.blob.media_type < existing.media_type:
                    selected_blobs[entry.blob.digest] = entry.blob
        selected_digests = set(selected_blobs)
        assumed = selected_digests.intersection(have)
        included = [
            selected_blobs[digest]
            for digest in sorted(selected_digests.difference(assumed))
        ]
        return PrimitivePack.create(
            revision_ids=revision_ids,
            tree_ids=tree_ids,
            entries=entries,
            included_blobs=included,
            assumed_present_digests=assumed,
            graph_epoch_ids=graph_epoch_ids,
        )

    def payloads_for(self, pack: PrimitivePack) -> dict[str, bytes]:
        return {blob.digest: self.blobs[blob.digest] for blob in pack.included_blobs}

    def _revision_closure(self, revision_id: str) -> set[str]:
        pending = [revision_id]
        result: set[str] = set()
        while pending:
            current = pending.pop()
            if current in result:
                continue
            result.add(current)
            pending.extend(self.revisions[current].parent_revision_ids)
        return result

    def _is_ancestor(self, ancestor_id: str, descendant_id: str) -> bool:
        return ancestor_id in self._revision_closure(descendant_id)


def encode_primitive_pack(
    pack: PrimitivePack, payloads: Mapping[str, bytes]
) -> bytes:
    expected = {blob.digest: blob for blob in pack.included_blobs}
    if set(payloads) != set(expected):
        raise PrimitiveRegistryError("pack payload set does not match its manifest")
    for digest, descriptor in expected.items():
        descriptor.validate(payloads[digest])
    manifest = canonical_json_bytes(pack)
    framed = bytearray(_PACK_MAGIC)
    framed.extend(len(manifest).to_bytes(8, "big"))
    framed.extend(manifest)
    for descriptor in pack.included_blobs:
        content = payloads[descriptor.digest]
        framed.extend(len(content).to_bytes(8, "big"))
        framed.extend(content)
    return gzip.compress(bytes(framed), compresslevel=9, mtime=0)


def decode_primitive_pack(
    encoded: bytes, *, max_uncompressed_bytes: int = 128 * 1024 * 1024
) -> tuple[dict[str, object], dict[str, bytes]]:
    with gzip.GzipFile(fileobj=io.BytesIO(encoded), mode="rb") as handle:
        framed = handle.read(max_uncompressed_bytes + 1)
    if len(framed) > max_uncompressed_bytes:
        raise PrimitiveRegistryError("primitive pack exceeds the uncompressed size limit")
    if not framed.startswith(_PACK_MAGIC) or len(framed) < len(_PACK_MAGIC) + 8:
        raise PrimitiveRegistryError("invalid primitive pack header")
    cursor = len(_PACK_MAGIC)
    manifest_size = int.from_bytes(framed[cursor : cursor + 8], "big")
    cursor += 8
    manifest_end = cursor + manifest_size
    try:
        manifest = json.loads(framed[cursor:manifest_end].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PrimitiveRegistryError("invalid primitive pack manifest") from exc
    cursor = manifest_end
    identity_data = manifest.get("identity", {})
    if not isinstance(identity_data, dict):
        raise PrimitiveRegistryError("primitive pack identity is missing")
    identity = IdentityRecord(
        str(identity_data.get("id", "")),
        str(identity_data.get("kind", "")),
        identity_data.get("canonical_key"),
    )
    try:
        identity.validate()
    except Exception as exc:
        raise PrimitiveRegistryError("primitive pack identity does not validate") from exc
    descriptors = manifest.get("included_blobs", [])
    if not isinstance(descriptors, list):
        raise PrimitiveRegistryError("primitive pack blob manifest is invalid")
    payloads: dict[str, bytes] = {}
    for item in descriptors:
        if not isinstance(item, dict):
            raise PrimitiveRegistryError("primitive pack blob descriptor is invalid")
        descriptor = BlobDescriptor(
            str(item.get("digest", "")),
            int(item.get("size_bytes", -1)),
            str(item.get("media_type", "")),
        )
        if cursor + 8 > len(framed):
            raise PrimitiveRegistryError("primitive pack is truncated")
        payload_size = int.from_bytes(framed[cursor : cursor + 8], "big")
        cursor += 8
        end = cursor + payload_size
        if end > len(framed):
            raise PrimitiveRegistryError("primitive pack payload is truncated")
        payload = bytes(framed[cursor:end])
        cursor = end
        descriptor.validate(payload)
        payloads[descriptor.digest] = payload
    if cursor != len(framed):
        raise PrimitiveRegistryError("primitive pack contains trailing bytes")
    return manifest, payloads
