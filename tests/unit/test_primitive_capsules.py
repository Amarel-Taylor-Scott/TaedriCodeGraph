from __future__ import annotations

import unittest

from taedri_codegraph.canonical import sha256_digest
from taedri_codegraph.contracts import ProducerRef
from taedri_codegraph.primitive_capsules import (
    CapsuleRole,
    PrimitiveRegistry,
    PrimitiveRegistryError,
    PrimitiveTreeEntry,
    RefKind,
    decode_primitive_pack,
    encode_primitive_pack,
)


class PrimitiveCapsuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = PrimitiveRegistry()
        self.producer = ProducerRef("taedri.test.publisher", "1.0.0", "sha256:" + "1" * 64)
        self.handle = self.registry.register_handle("taedri.core", "normalize-text")
        self.source = self.registry.put_blob(
            b"def normalize_text(value: str) -> str:\n    return ' '.join(value.split())\n",
            "text/x-python",
        )
        self.contract = self.registry.put_blob(
            b'{"input":"str","output":"str","effects":[]}',
            "application/vnd.taedri.primitive.contract.v1+json",
        )
        self.tests = self.registry.put_blob(
            b"assert normalize_text(' a  b ') == 'a b'\n",
            "text/x-python",
        )
        self.edges = self.registry.put_blob(
            b'{"edges":[["normalize_text","str.split"],["normalize_text","str.join"]]}',
            "application/vnd.taedri.codegraph.edges.v1+json",
        )
        self.tree = self.registry.create_tree(
            (
                PrimitiveTreeEntry("src/normalize.py", CapsuleRole.SOURCE, self.source),
                PrimitiveTreeEntry("contract.json", CapsuleRole.CONTRACT, self.contract),
                PrimitiveTreeEntry("tests/test_normalize.py", CapsuleRole.TEST, self.tests),
                PrimitiveTreeEntry("graph/edges.json", CapsuleRole.GRAPH_DELTA, self.edges),
            )
        )
        self.initial = self.registry.commit(
            primitive=self.handle,
            tree_id=self.tree.identity.id,
            contract_digest=self.contract.digest,
            graph_epoch_id="uceg:v1:graph_epoch:fixture",
            producer=self.producer,
            generation_run_id="run-fixture-1",
            evidence_ids=("test-fixture-1",),
            author="test-suite",
            created_at="2026-07-16T12:00:00Z",
            message="Publish tested normalization primitive",
        )
        self.registry.update_ref(
            primitive=self.handle,
            ref_kind=RefKind.BRANCH,
            ref_name="main",
            new_revision_id=self.initial.identity.id,
            expected_revision_id=None,
            actor="test-suite",
            updated_at="2026-07-16T12:00:00Z",
        )

    def test_tree_identity_is_order_independent_and_blobs_deduplicate(self) -> None:
        repeated_source = self.registry.put_blob(
            self.registry.blobs[self.source.digest], self.source.media_type
        )
        self.assertEqual(repeated_source, self.source)
        reordered = self.registry.create_tree(reversed(self.tree.entries))
        self.assertEqual(reordered.identity.id, self.tree.identity.id)
        self.assertEqual(len(self.registry.blobs), 4)

    def test_branch_updates_are_compare_and_swap_and_fast_forward_only(self) -> None:
        revised_source = self.registry.put_blob(
            b"def normalize_text(value: str) -> str:\n    return ' '.join(value.strip().split())\n",
            "text/x-python",
        )
        revised_tree = self.registry.create_tree(
            PrimitiveTreeEntry(
                entry.path,
                entry.role,
                revised_source if entry.role is CapsuleRole.SOURCE else entry.blob,
                entry.mode,
            )
            for entry in self.tree.entries
        )
        revision = self.registry.commit(
            primitive=self.handle,
            tree_id=revised_tree.identity.id,
            contract_digest=self.contract.digest,
            parent_revision_ids=(self.initial.identity.id,),
            producer=self.producer,
            author="test-suite",
            created_at="2026-07-16T12:01:00Z",
            message="Trim explicitly before normalization",
        )
        with self.assertRaises(PrimitiveRegistryError):
            self.registry.update_ref(
                primitive=self.handle,
                ref_kind=RefKind.BRANCH,
                ref_name="main",
                new_revision_id=revision.identity.id,
                expected_revision_id=None,
                actor="test-suite",
                updated_at="2026-07-16T12:01:00Z",
            )
        update = self.registry.update_ref(
            primitive=self.handle,
            ref_kind=RefKind.BRANCH,
            ref_name="main",
            new_revision_id=revision.identity.id,
            expected_revision_id=self.initial.identity.id,
            actor="test-suite",
            updated_at="2026-07-16T12:01:00Z",
        )
        self.assertEqual(update.old_revision_id, self.initial.identity.id)
        self.assertEqual(
            self.registry.resolve_ref(self.handle, RefKind.BRANCH, "main").identity.id,
            revision.identity.id,
        )

    def test_release_tags_are_immutable(self) -> None:
        self.registry.update_ref(
            primitive=self.handle,
            ref_kind=RefKind.TAG,
            ref_name="v1.0.0",
            new_revision_id=self.initial.identity.id,
            expected_revision_id=None,
            actor="release-bot",
            updated_at="2026-07-16T12:02:00Z",
        )
        with self.assertRaises(PrimitiveRegistryError):
            self.registry.update_ref(
                primitive=self.handle,
                ref_kind=RefKind.TAG,
                ref_name="v1.0.0",
                new_revision_id=self.initial.identity.id,
                expected_revision_id=self.initial.identity.id,
                actor="release-bot",
                updated_at="2026-07-16T12:03:00Z",
            )

    def test_fork_and_merge_retain_cross_namespace_revision_lineage(self) -> None:
        fork = self.registry.fork(
            source_revision_id=self.initial.identity.id,
            target_namespace="customer.team",
            target_name="normalize-text",
            branch_name="main",
            producer=self.producer,
            author="customer-team",
            created_at="2026-07-16T12:04:00Z",
            message="Fork Taedri normalization primitive",
        )
        self.assertEqual(fork.upstream_revision_id, self.initial.identity.id)
        self.assertEqual(fork.parent_revision_ids, (self.initial.identity.id,))
        merged = self.registry.merge(
            primitive=self.handle,
            branch_name="main",
            current_revision_id=self.initial.identity.id,
            merged_revision_id=fork.identity.id,
            result_tree_id=self.tree.identity.id,
            contract_digest=self.contract.digest,
            graph_epoch_id="uceg:v1:graph_epoch:fixture",
            producer=self.producer,
            author="test-suite",
            created_at="2026-07-16T12:05:00Z",
            message="Merge customer lineage after review",
        )
        self.assertEqual(
            merged.parent_revision_ids, (self.initial.identity.id, fork.identity.id)
        )

    def test_thin_pack_omits_cached_blobs_and_unrequested_roles(self) -> None:
        pack = self.registry.build_pack(
            self.initial.identity.id,
            include_roles=(CapsuleRole.SOURCE, CapsuleRole.CONTRACT, CapsuleRole.GRAPH_DELTA),
            have_digests=(self.source.digest,),
        )
        self.assertEqual(pack.assumed_present_digests, (self.source.digest,))
        self.assertEqual(
            {blob.digest for blob in pack.included_blobs},
            {self.contract.digest, self.edges.digest},
        )
        self.assertNotIn(self.tests.digest, {entry.blob.digest for entry in pack.entries})
        self.assertEqual(pack.graph_epoch_ids, ("uceg:v1:graph_epoch:fixture",))

    def test_pack_encoding_is_deterministic_and_validates_payloads(self) -> None:
        pack = self.registry.build_pack(self.initial.identity.id)
        payloads = self.registry.payloads_for(pack)
        first = encode_primitive_pack(pack, payloads)
        second = encode_primitive_pack(pack, payloads)
        self.assertEqual(first, second)
        manifest, decoded = decode_primitive_pack(first)
        self.assertEqual(manifest["identity"]["id"], pack.identity.id)
        self.assertEqual(decoded, payloads)
        corrupted = dict(payloads)
        corrupted[self.source.digest] += b"# mutation\n"
        with self.assertRaises(PrimitiveRegistryError):
            encode_primitive_pack(pack, corrupted)

    def test_contract_must_be_bound_as_a_contract_role(self) -> None:
        with self.assertRaises(PrimitiveRegistryError):
            self.registry.commit(
                primitive=self.handle,
                tree_id=self.tree.identity.id,
                contract_digest=sha256_digest(b"not in the tree"),
                producer=self.producer,
                author="test-suite",
                created_at="2026-07-16T12:06:00Z",
                message="Invalid contract binding",
            )


if __name__ == "__main__":
    unittest.main()
