from __future__ import annotations

import unittest

from taedri_codegraph.canonical import sha256_digest
from taedri_codegraph.contracts import ProducerRef
from taedri_codegraph.intake import (
    CandidateIntakeError,
    CandidateIntakeLedger,
    CandidateOrigin,
    CandidateState,
    CandidateSubmission,
    CandidateVisibility,
    LicenseEvidenceState,
)


class CandidateIntakeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.producer = ProducerRef(
            "taedri.factory", "1.0.0", sha256_digest(b"factory-config")
        )

    def submission(
        self,
        *,
        origin: CandidateOrigin = CandidateOrigin.GENERATED,
        visibility: CandidateVisibility = CandidateVisibility.PRIVATE,
        license_state: LicenseEvidenceState = LicenseEvidenceState.UNKNOWN,
        license_expression: str | None = None,
    ) -> CandidateSubmission:
        return CandidateSubmission.create(
            primitive_id="uceg:v1:primitive:fixture",
            revision_id="uceg:v1:primitive_revision:fixture",
            origin=origin,
            producer=self.producer,
            submitted_by="taedri.factory",
            submitted_at="2026-07-16T12:00:00Z",
            source_uri="git+https://example.invalid/repository",
            source_revision="abc123",
            license_expression=license_expression,
            license_evidence_state=license_state,
            visibility=visibility,
            production_run_id="uceg:v1:generation_run:fixture",
            evidence_ids=(sha256_digest(b"source"),),
        )

    def advance_to_indexed(
        self, ledger: CandidateIntakeLedger, submission: CandidateSubmission
    ) -> None:
        ledger.submit(submission)
        ledger.transition(
            submission.identity.id,
            CandidateState.QUARANTINED,
            actor="taedri.factory",
            occurred_at="2026-07-16T12:00:01Z",
            reason="safe static intake",
        )
        ledger.transition(
            submission.identity.id,
            CandidateState.STRUCTURALLY_VALID,
            actor="taedri.factory",
            occurred_at="2026-07-16T12:00:02Z",
            reason="schema and digest validation passed",
        )
        ledger.transition(
            submission.identity.id,
            CandidateState.INDEXED_CANDIDATE,
            actor="taedri.factory",
            occurred_at="2026-07-16T12:00:03Z",
            reason="candidate projections built",
        )

    def test_submission_is_idempotent_and_events_are_append_only(self) -> None:
        ledger = CandidateIntakeLedger()
        submission = self.submission(origin=CandidateOrigin.EXTRACTED)
        first = ledger.submit(submission)
        repeated = ledger.submit(submission)
        self.assertEqual(first, repeated)
        self.assertEqual(len(ledger.events), 1)
        self.advance_to_indexed(ledger, submission)
        self.assertEqual(
            [event.sequence for event in ledger.history(submission.identity.id)],
            [1, 2, 3, 4],
        )

    def test_generated_candidate_cannot_self_curate(self) -> None:
        ledger = CandidateIntakeLedger()
        submission = self.submission()
        self.advance_to_indexed(ledger, submission)
        with self.assertRaises(CandidateIntakeError):
            ledger.transition(
                submission.identity.id,
                CandidateState.CURATED_CANDIDATE,
                actor="taedri.factory",
                occurred_at="2026-07-16T12:00:04Z",
                reason="self approval",
                evidence_ids=("verify:fixture",),
                policy_decision_id="policy:fixture",
            )
        curated = ledger.transition(
            submission.identity.id,
            CandidateState.CURATED_CANDIDATE,
            actor="independent-verifier",
            occurred_at="2026-07-16T12:00:05Z",
            reason="independent tests and policy passed",
            evidence_ids=("verify:fixture",),
            policy_decision_id="policy:fixture",
        )
        self.assertEqual(curated.to_state, CandidateState.CURATED_CANDIDATE)

    def test_public_candidate_curation_requires_verified_license(self) -> None:
        ledger = CandidateIntakeLedger()
        submission = self.submission(visibility=CandidateVisibility.PUBLIC)
        self.advance_to_indexed(ledger, submission)
        with self.assertRaises(CandidateIntakeError):
            ledger.transition(
                submission.identity.id,
                CandidateState.CURATED_CANDIDATE,
                actor="independent-verifier",
                occurred_at="2026-07-16T12:00:04Z",
                reason="license still unknown",
                evidence_ids=("verify:fixture",),
                policy_decision_id="policy:fixture",
            )

    def test_verified_license_requires_an_expression(self) -> None:
        with self.assertRaises(CandidateIntakeError):
            self.submission(license_state=LicenseEvidenceState.VERIFIED)


if __name__ == "__main__":
    unittest.main()
