from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from taedri_codegraph.canonical import sha256_digest
from taedri_codegraph.primitive_capsules import (
    CapsuleRole,
    RefKind,
    decode_primitive_pack,
)
from taedri_codegraph.primitive_repository import (
    PrimitiveFileInput,
    PrimitiveRepositoryConflict,
    SQLitePrimitiveRepository,
)
from taedri_codegraph.primitives.acceptance import (
    LocalPythonPrimitiveVerifier,
    PrimitiveVerifierRegistry,
)
from taedri_codegraph.primitives.bundle import load_primitive_directory
from taedri_codegraph.primitives.release import AssuranceLevel, PrimitiveReleaseError
from taedri_codegraph.saas import SQLiteControlPlane, Tenant


class PrimitiveRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "control.sqlite"
        self.control = SQLiteControlPlane(self.path)
        self.tenant = self.control.create_tenant(
            Tenant.create(
                slug="registry-test",
                display_name="Registry test",
                created_at="2026-07-16T12:00:00Z",
            )
        )
        self.repository = SQLitePrimitiveRepository(self.control)
        root = Path(__file__).resolve().parents[2]
        self.bundle = load_primitive_directory(
            root / "examples/primitives/normalize-text"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def stage(
        self,
        *,
        expected: str | None = None,
        created: str = "2026-07-16T12:01:00Z",
        namespace: str = "acme",
        name: str = "normalize-text",
        files: tuple[PrimitiveFileInput, ...] | None = None,
        ref_kind: RefKind = RefKind.BRANCH,
        ref_name: str = "main",
        parents: tuple[str, ...] | None = None,
    ):
        return self.repository.stage(
            self.tenant.identity.id,
            namespace=namespace,
            name=name,
            files=files or self.bundle.files,
            contract_path="contract.json",
            ref_kind=ref_kind,
            ref_name=ref_name,
            expected_revision_id=expected,
            actor="taedri.example.author.normalize-text-v1",
            created_at=created,
            message="stage complete normalizer",
            parent_revision_ids=parents,
        )

    def release(self, staged, *, assurance=AssuranceLevel.STANDARD):
        return LocalPythonPrimitiveVerifier(
            self.repository,
            verifier_id="taedri.verifier.unit-test-v1",
        ).verify_and_release(
            self.tenant.identity.id,
            staged.revision.identity.id,
            ref_kind=staged.ref_update.ref_kind,
            ref_name=staged.ref_update.ref_name,
            authorizer_id="taedri.release-manager.unit-test-v1",
            policy_decision_id="policy:unit-release-v1",
            verified_at="2026-07-16T12:01:30Z",
            assurance_level=assurance,
        )

    def test_staged_content_is_hidden_until_executable_release_and_survives_restart(self) -> None:
        staged = self.stage()
        self.assertEqual(self.repository.list(self.tenant.identity.id), ())
        with self.assertRaises(LookupError):
            self.repository.get(self.tenant.identity.id, "acme", "normalize-text")
        with self.assertRaises(LookupError):
            self.repository.pack(self.tenant.identity.id, "acme", "normalize-text")

        accepted = self.release(staged)
        restarted = SQLitePrimitiveRepository(SQLiteControlPlane(self.path))
        record = restarted.get(self.tenant.identity.id, "acme", "normalize-text")
        self.assertEqual(
            record["revision"].identity.id, accepted.released.release.revision_id
        )
        self.assertEqual(record["release"]["assurance_level"], "standard")
        pack, encoded = restarted.pack(
            self.tenant.identity.id,
            "acme",
            "normalize-text",
            include_roles=(CapsuleRole.SOURCE,),
        )
        manifest, payloads = decode_primitive_pack(encoded)
        self.assertEqual(manifest["identity"]["id"], pack.identity.id)
        self.assertEqual(len(payloads), 1)
        self.assertIn(b"def normalize_text", next(iter(payloads.values())))

    def test_branch_compare_and_swap_and_tags_fail_closed(self) -> None:
        first = self.stage()
        with self.assertRaisesRegex(PrimitiveRepositoryConflict, "compare-and-swap"):
            self.stage(expected=None, created="2026-07-16T12:02:00Z")
        second = self.stage(
            expected=first.revision.identity.id, created="2026-07-16T12:03:00Z"
        )
        self.assertEqual(
            second.revision.parent_revision_ids, (first.revision.identity.id,)
        )
        tag = self.stage(
            ref_kind=RefKind.TAG,
            ref_name="v1.0.0",
            created="2026-07-16T12:04:00Z",
            parents=(second.revision.identity.id,),
        )
        with self.assertRaisesRegex(PrimitiveRepositoryConflict, "immutable"):
            self.stage(
                expected=tag.revision.identity.id,
                ref_kind=RefKind.TAG,
                ref_name="v1.0.0",
                created="2026-07-16T12:05:00Z",
                parents=(tag.revision.identity.id,),
            )

    def test_fork_retains_lineage_but_is_not_public_without_its_own_release(self) -> None:
        source = self.stage()
        self.release(source)
        fork = self.repository.fork(
            self.tenant.identity.id,
            source_revision_id=source.revision.identity.id,
            target_namespace="research",
            target_name="normalize-text",
            branch_name="main",
            actor="api-key:forker",
            created_at="2026-07-16T12:06:00Z",
            message="fork for experimentation",
        )
        self.assertEqual(fork.revision.tree_id, source.revision.tree_id)
        self.assertEqual(fork.revision.upstream_revision_id, source.revision.identity.id)
        self.assertIn(source.revision.identity.id, fork.revision.parent_revision_ids)
        self.assertEqual(len(self.repository.list(self.tenant.identity.id)), 1)
        with self.assertRaises(LookupError):
            self.repository.get(
                self.tenant.identity.id, "research", "normalize-text"
            )
        with self.control._connect() as connection:
            blobs = connection.execute(
                "SELECT COUNT(*) FROM primitive_blob WHERE tenant_id=?",
                (self.tenant.identity.id,),
            ).fetchone()[0]
        self.assertEqual(blobs, 13)

    def test_incomplete_capsule_can_be_staged_but_never_released_or_queried(self) -> None:
        incomplete = tuple(
            item
            for item in self.bundle.files
            if item.role in {CapsuleRole.SOURCE, CapsuleRole.CONTRACT}
        )
        staged = self.stage(name="incomplete", files=incomplete)
        with self.assertRaisesRegex(PrimitiveReleaseError, "missing required roles"):
            self.release(staged, assurance=AssuranceLevel.BOOTSTRAP)
        self.assertEqual(self.repository.list(self.tenant.identity.id), ())

    def test_duplicate_source_body_cannot_masquerade_as_another_primitive(self) -> None:
        first = self.stage(name="normalize-text")
        self.release(first)
        duplicate = self.stage(
            name="different-description-same-body",
            created="2026-07-16T12:02:00Z",
        )
        with self.assertRaisesRegex(PrimitiveRepositoryConflict, "already released"):
            self.release(duplicate)
        self.assertEqual(len(self.repository.list(self.tenant.identity.id)), 1)

    def test_bootstrap_relaxes_identity_separation_but_not_functional_proofs(self) -> None:
        staged = self.stage()
        producer = "taedri.example.author.normalize-text-v1"
        verifier = LocalPythonPrimitiveVerifier(
            self.repository, verifier_id=producer
        )
        with self.assertRaisesRegex(PrimitiveReleaseError, "standard assurance"):
            verifier.verify_and_release(
                self.tenant.identity.id,
                staged.revision.identity.id,
                ref_kind=RefKind.BRANCH,
                ref_name="main",
                authorizer_id=producer,
                policy_decision_id="policy:standard-separation-v1",
                verified_at="2026-07-16T12:01:20Z",
                assurance_level=AssuranceLevel.STANDARD,
            )
        accepted = verifier.verify_and_release(
            self.tenant.identity.id,
            staged.revision.identity.id,
            ref_kind=RefKind.BRANCH,
            ref_name="main",
            authorizer_id=producer,
            policy_decision_id="policy:bootstrap-v1",
            verified_at="2026-07-16T12:01:30Z",
            assurance_level=AssuranceLevel.BOOTSTRAP,
        )
        self.assertEqual(accepted.executed_case_count, 6)
        self.assertEqual(accepted.released.release.assurance_level, AssuranceLevel.BOOTSTRAP)

    def test_unregistered_language_verifier_fails_closed_and_stays_hidden(self) -> None:
        runtime = json.loads(
            next(
                item.content
                for item in self.bundle.files
                if item.role is CapsuleRole.RUNTIME
            )
        )
        runtime["language"] = "javascript"
        runtime["runtime_version"] = "22"
        runtime_content = json.dumps(runtime, sort_keys=True).encode("utf-8")
        runtime_digest = sha256_digest(runtime_content)
        files: list[PrimitiveFileInput] = []
        for item in self.bundle.files:
            if item.role is CapsuleRole.RUNTIME:
                files.append(
                    PrimitiveFileInput(
                        item.path,
                        item.role,
                        item.media_type,
                        runtime_content,
                        item.mode,
                    )
                )
            elif item.role is CapsuleRole.GRAPH_DELTA:
                graph = json.loads(item.content)
                graph["compatibility"]["language"] = "javascript"
                graph["compatibility"]["runtime_version"] = "22"
                graph["compatibility"]["dimensions"][
                    "taedri.compatibility.language"
                ] = "javascript"
                graph["compatibility"]["dimensions"][
                    "taedri.compatibility.runtime_major_minor"
                ] = "22"
                for edge in graph["edges"]:
                    for evidence in edge["evidence"]:
                        if evidence["path"] == "runtime.json":
                            evidence["digest"] = runtime_digest
                files.append(
                    PrimitiveFileInput(
                        item.path,
                        item.role,
                        item.media_type,
                        json.dumps(graph, sort_keys=True).encode("utf-8"),
                        item.mode,
                    )
                )
            else:
                files.append(item)
        staged = self.stage(name="javascript-shaped", files=tuple(files))
        verifiers = PrimitiveVerifierRegistry(self.repository)
        verifiers.register(LocalPythonPrimitiveVerifier(self.repository))
        self.assertEqual(verifiers.languages, ("python",))
        with self.assertRaisesRegex(PrimitiveReleaseError, "no executable verifier"):
            verifiers.verify_and_release(
                self.tenant.identity.id,
                staged.revision.identity.id,
                ref_kind=RefKind.BRANCH,
                ref_name="main",
                authorizer_id="test-authorizer",
                policy_decision_id="policy:no-javascript-verifier",
                verified_at="2026-07-16T12:02:00Z",
            )
        self.assertEqual(self.repository.list(self.tenant.identity.id), ())

    def test_release_revocation_immediately_removes_search_resolve_and_download(self) -> None:
        accepted = self.release(self.stage())
        release_id = accepted.released.release.identity.id
        revoked = self.repository.revoke(
            self.tenant.identity.id,
            release_id=release_id,
            actor="taedri.release-manager.unit-test-v1",
            policy_decision_id="policy:security-revoke-v1",
            reason="reference revocation exercise",
            revoked_at="2026-07-16T12:02:00Z",
        )
        self.assertEqual(revoked.release_id, release_id)
        self.assertEqual(self.repository.list(self.tenant.identity.id), ())
        with self.assertRaises(LookupError):
            self.repository.get(self.tenant.identity.id, "acme", "normalize-text")
        with self.assertRaises(LookupError):
            self.repository.pack(self.tenant.identity.id, "acme", "normalize-text")
        with self.assertRaisesRegex(PrimitiveRepositoryConflict, "already revoked"):
            self.repository.revoke(
                self.tenant.identity.id,
                release_id=release_id,
                actor="another-manager",
                policy_decision_id="policy:other",
                reason="competing history",
                revoked_at="2026-07-16T12:03:00Z",
            )

    def test_tenant_queries_cannot_resolve_another_tenants_primitive(self) -> None:
        self.release(self.stage())
        other = self.control.create_tenant(
            Tenant.create(
                slug="other-tenant",
                display_name="Other",
                created_at="2026-07-16T12:10:00Z",
            )
        )
        with self.assertRaises(LookupError):
            self.repository.get(other.identity.id, "acme", "normalize-text")
        self.assertEqual(self.repository.list(other.identity.id), ())


if __name__ == "__main__":
    unittest.main()
