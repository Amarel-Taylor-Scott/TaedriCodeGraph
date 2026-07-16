from __future__ import annotations

import unittest

from taedri_codegraph.canonical import sha256_digest
from taedri_codegraph.sessions import (
    HarnessRef,
    PromptPrivacyMode,
    PromptSession,
    PromptSessionError,
    PromptSessionLedger,
    SessionEventKind,
)


class PromptSessionLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = PromptSessionLedger()
        self.session = PromptSession.create(
            tenant_id="tenant-fixture",
            workspace_id="workspace-fixture",
            repository_snapshot_id="uceg:v1:package_snapshot:fixture",
            harness=HarnessRef(
                "taedri.codex-hook",
                "1.0.0",
                sha256_digest(b"harness-config"),
                "mcp",
            ),
            policy_digest=sha256_digest(b"tenant-policy"),
            privacy_mode=PromptPrivacyMode.DIGEST_ONLY,
            started_at="2026-07-16T12:00:00Z",
        )
        self.ledger.start(self.session, actor="coding-harness")

    def test_digest_only_mode_rejects_raw_prompt_content(self) -> None:
        with self.assertRaises(PromptSessionError):
            self.ledger.record(
                self.session.identity.id,
                SessionEventKind.REQUEST_CAPTURED,
                actor="coding-harness",
                occurred_at="2026-07-16T12:00:01Z",
                attributes={"raw_prompt": "copy this secret"},
            )

    def test_search_materialization_abstention_and_close_are_ordered(self) -> None:
        prompt_digest = sha256_digest(b"find a canonical encoder")
        self.ledger.record(
            self.session.identity.id,
            SessionEventKind.REQUEST_CAPTURED,
            actor="coding-harness",
            occurred_at="2026-07-16T12:00:01Z",
            input_refs=(prompt_digest,),
            attributes={"capture": "digest_only", "intent": "reuse_search"},
        )
        self.ledger.record(
            self.session.identity.id,
            SessionEventKind.SEARCH_RECEIPT,
            actor="taedri-query-api",
            occurred_at="2026-07-16T12:00:02Z",
            input_refs=(prompt_digest,),
            output_refs=("receipt:search-1",),
            attributes={"candidate_count": 3, "disclosure_depth": "D1"},
        )
        self.ledger.record(
            self.session.identity.id,
            SessionEventKind.CANDIDATE_SELECTED,
            actor="coding-harness",
            occurred_at="2026-07-16T12:00:03Z",
            input_refs=("receipt:search-1",),
            output_refs=("uceg:v1:primitive_revision:fixture",),
        )
        self.ledger.record(
            self.session.identity.id,
            SessionEventKind.MATERIALIZATION_RECEIPT,
            actor="taedri-registry-api",
            occurred_at="2026-07-16T12:00:04Z",
            output_refs=("sha256:" + "a" * 64,),
            attributes={"roles": ["contract", "source"], "disclosure_depth": "D4"},
        )
        self.ledger.record(
            self.session.identity.id,
            SessionEventKind.ABSTAINED,
            actor="coding-harness",
            occurred_at="2026-07-16T12:00:05Z",
            attributes={"reason_code": "model_execution_not_configured"},
        )
        closed = self.ledger.record(
            self.session.identity.id,
            SessionEventKind.SESSION_CLOSED,
            actor="coding-harness",
            occurred_at="2026-07-16T12:00:06Z",
        )
        self.assertEqual(closed.sequence, 7)
        with self.assertRaises(PromptSessionError):
            self.ledger.record(
                self.session.identity.id,
                SessionEventKind.REQUEST_CAPTURED,
                actor="coding-harness",
                occurred_at="2026-07-16T12:00:07Z",
            )

    def test_result_acceptance_requires_model_and_verification_receipts(self) -> None:
        self.ledger.record(
            self.session.identity.id,
            SessionEventKind.REQUEST_CAPTURED,
            actor="coding-harness",
            occurred_at="2026-07-16T12:00:01Z",
            input_refs=(sha256_digest(b"request"),),
        )
        with self.assertRaises(PromptSessionError):
            self.ledger.record(
                self.session.identity.id,
                SessionEventKind.RESULT_ACCEPTED,
                actor="coding-harness",
                occurred_at="2026-07-16T12:00:02Z",
                output_refs=("receipt:result",),
            )
        self.ledger.record(
            self.session.identity.id,
            SessionEventKind.MODEL_ATTEMPT,
            actor="model-router",
            occurred_at="2026-07-16T12:00:03Z",
            output_refs=("receipt:model-attempt",),
            attributes={"provider": "fixture", "cost_microunits": 0},
        )
        self.ledger.record(
            self.session.identity.id,
            SessionEventKind.VERIFICATION_RECEIPT,
            actor="isolated-verifier",
            occurred_at="2026-07-16T12:00:04Z",
            input_refs=("receipt:model-attempt",),
            output_refs=("receipt:verification",),
            attributes={"outcome": "passed"},
        )
        accepted = self.ledger.record(
            self.session.identity.id,
            SessionEventKind.RESULT_ACCEPTED,
            actor="coding-harness",
            occurred_at="2026-07-16T12:00:05Z",
            input_refs=("receipt:verification",),
            output_refs=("receipt:result",),
            attributes={"policy_decision_ref": "receipt:policy-decision"},
        )
        self.assertEqual(accepted.event_kind, SessionEventKind.RESULT_ACCEPTED)

    def test_failed_verification_cannot_be_accepted(self) -> None:
        self.ledger.record(
            self.session.identity.id,
            SessionEventKind.REQUEST_CAPTURED,
            actor="coding-harness",
            occurred_at="2026-07-16T12:00:01Z",
            input_refs=(sha256_digest(b"request"),),
        )
        self.ledger.record(
            self.session.identity.id,
            SessionEventKind.MODEL_ATTEMPT,
            actor="model-router",
            occurred_at="2026-07-16T12:00:02Z",
            output_refs=("receipt:model-attempt",),
        )
        self.ledger.record(
            self.session.identity.id,
            SessionEventKind.VERIFICATION_RECEIPT,
            actor="isolated-verifier",
            occurred_at="2026-07-16T12:00:03Z",
            output_refs=("receipt:verification",),
            attributes={"outcome": "failed"},
        )
        with self.assertRaises(PromptSessionError):
            self.ledger.record(
                self.session.identity.id,
                SessionEventKind.RESULT_ACCEPTED,
                actor="coding-harness",
                occurred_at="2026-07-16T12:00:04Z",
                output_refs=("receipt:result",),
                attributes={"policy_decision_ref": "receipt:policy-decision"},
            )


if __name__ == "__main__":
    unittest.main()
