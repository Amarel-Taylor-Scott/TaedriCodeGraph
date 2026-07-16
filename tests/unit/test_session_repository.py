from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from taedri_codegraph.canonical import sha256_digest
from taedri_codegraph.saas import SQLiteControlPlane, Tenant
from taedri_codegraph.session_repository import SQLitePromptSessionRepository
from taedri_codegraph.sessions import (
    HarnessRef,
    PromptPrivacyMode,
    PromptSession,
    PromptSessionError,
    SessionEventKind,
)


class PromptSessionRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "control.sqlite"
        self.control = SQLiteControlPlane(self.database)
        self.tenant = self.control.create_tenant(
            Tenant.create(
                slug="session-test",
                display_name="Session test",
                created_at="2026-07-16T16:00:00Z",
            )
        )
        self.session = PromptSession.create(
            tenant_id=self.tenant.identity.id,
            workspace_id="workspace-1",
            repository_snapshot_id="uceg:v1:package_snapshot:fixture",
            harness=HarnessRef(
                "taedri.test-harness",
                "1.0.0",
                sha256_digest(b"harness-config"),
                "mcp",
            ),
            policy_digest=sha256_digest(b"tenant-policy"),
            privacy_mode=PromptPrivacyMode.DIGEST_ONLY,
            started_at="2026-07-16T16:01:00Z",
        )
        self.repository = SQLitePromptSessionRepository(self.control)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_history_survives_restart_and_closes_append_only(self) -> None:
        first = self.repository.start(self.session, actor="harness:test")
        self.assertEqual(first.sequence, 1)
        request_ref = sha256_digest(b"reuse an address parser")
        self.repository.record(
            self.tenant.identity.id,
            self.session.identity.id,
            SessionEventKind.REQUEST_CAPTURED,
            actor="harness:test",
            occurred_at="2026-07-16T16:01:01Z",
            input_refs=(request_ref,),
            attributes={"capture": "digest_only"},
        )
        self.repository.record(
            self.tenant.identity.id,
            self.session.identity.id,
            SessionEventKind.ABSTAINED,
            actor="harness:test",
            occurred_at="2026-07-16T16:01:02Z",
            attributes={"reason_code": "no_verified_candidate"},
        )
        self.repository.record(
            self.tenant.identity.id,
            self.session.identity.id,
            SessionEventKind.SESSION_CLOSED,
            actor="harness:test",
            occurred_at="2026-07-16T16:01:03Z",
        )
        restarted = SQLitePromptSessionRepository(SQLiteControlPlane(self.database))
        record = restarted.get(self.tenant.identity.id, self.session.identity.id)
        self.assertEqual(record["event_count"], 4)
        self.assertEqual(record["closed_at"], "2026-07-16T16:01:03Z")
        with self.assertRaises(PromptSessionError):
            restarted.record(
                self.tenant.identity.id,
                self.session.identity.id,
                SessionEventKind.REQUEST_CAPTURED,
                actor="harness:test",
                occurred_at="2026-07-16T16:02:00Z",
                input_refs=(request_ref,),
            )

    def test_digest_only_privacy_rejects_nested_raw_content_transactionally(self) -> None:
        self.repository.start(self.session, actor="harness:test")
        with self.assertRaisesRegex(PromptSessionError, "digest-only"):
            self.repository.record(
                self.tenant.identity.id,
                self.session.identity.id,
                SessionEventKind.REQUEST_CAPTURED,
                actor="harness:test",
                occurred_at="2026-07-16T16:01:01Z",
                input_refs=(sha256_digest(b"prompt"),),
                attributes={"nested": {"raw_prompt": "must not persist"}},
            )
        self.assertEqual(
            self.repository.get(self.tenant.identity.id, self.session.identity.id)[
                "event_count"
            ],
            1,
        )

    def test_sessions_are_tenant_isolated(self) -> None:
        self.repository.start(self.session, actor="harness:test")
        other = self.control.create_tenant(
            Tenant.create(
                slug="session-other",
                display_name="Other",
                created_at="2026-07-16T16:10:00Z",
            )
        )
        self.assertEqual(self.repository.list(other.identity.id), ())
        with self.assertRaises(LookupError):
            self.repository.get(other.identity.id, self.session.identity.id)


if __name__ == "__main__":
    unittest.main()
