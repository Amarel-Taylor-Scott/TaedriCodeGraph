from __future__ import annotations

import unittest

from taedri_codegraph.primitives.release import (
    PrimitiveAcceptanceReceipt,
    PrimitiveReleaseError,
    REQUIRED_ACCEPTANCE_PROOFS,
    REQUIRED_RELEASE_PROOFS,
    ReleaseProofKind,
)


class PrimitiveReleaseContractTests(unittest.TestCase):
    def receipt(self) -> PrimitiveAcceptanceReceipt:
        return PrimitiveAcceptanceReceipt.create(
            revision_id="uceg:v1:primitive_revision:fixture",
            tree_id="uceg:v1:primitive_tree:fixture",
            source_digest="sha256:" + "1" * 64,
            verifier_id="verifier:test",
            implementation_producer_id="producer:test",
            oracle_producer_id="oracle:test",
            verified_at="2026-07-16T12:00:00Z",
            proofs=tuple(REQUIRED_ACCEPTANCE_PROOFS),
            executed_case_count=3,
            language="python",
            runtime_version="3.12",
            output_digest="sha256:" + "2" * 64,
        )

    def test_acceptance_and_release_proof_boundaries_are_explicit(self) -> None:
        self.assertEqual(
            REQUIRED_RELEASE_PROOFS - REQUIRED_ACCEPTANCE_PROOFS,
            {
                ReleaseProofKind.DEDUPLICATION_CHECKED,
                ReleaseProofKind.QUERY_PASSED,
            },
        )
        with self.assertRaisesRegex(PrimitiveReleaseError, "proof set is invalid"):
            PrimitiveAcceptanceReceipt.create(
                revision_id="revision",
                tree_id="tree",
                source_digest="sha256:" + "1" * 64,
                verifier_id="verifier",
                implementation_producer_id="producer",
                oracle_producer_id="oracle",
                verified_at="2026-07-16T12:00:00Z",
                proofs=tuple(
                    item
                    for item in REQUIRED_ACCEPTANCE_PROOFS
                    if item is not ReleaseProofKind.TESTS_PASSED
                ),
                executed_case_count=3,
                language="python",
                runtime_version="3.12",
                output_digest="sha256:" + "2" * 64,
            )

    def test_full_canonical_identity_is_checked_on_receipt_reload(self) -> None:
        value = self.receipt().to_dict()
        value["identity"]["canonical_key"]["runtime_version"] = "9.99"
        with self.assertRaisesRegex(PrimitiveReleaseError, "identity does not validate"):
            PrimitiveAcceptanceReceipt.from_mapping(value)


if __name__ == "__main__":
    unittest.main()
