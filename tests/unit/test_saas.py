from __future__ import annotations

import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from taedri_codegraph.job_runner import JobRunner
from taedri_codegraph.saas import (
    AuthenticationError,
    AuthorizationError,
    GraphMount,
    SQLiteControlPlane,
    SQLiteWorkerQueue,
    Tenant,
    utc_now,
)
from taedri_codegraph.workers import (
    JobKind,
    JobState,
    WorkerEventKind,
    WorkerJob,
    WorkerQueueError,
)


NOW = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)


def timestamp(offset: int = 0) -> str:
    return (NOW + timedelta(seconds=offset)).isoformat().replace("+00:00", "Z")


class SaaSControlPlaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.control_path = self.root / "control.sqlite"
        self.control = SQLiteControlPlane(self.control_path)
        self.tenant = self.control.create_tenant(
            Tenant.create(slug="acme", display_name="Acme", created_at=timestamp())
        )
        self.mount = self.control.mount_graph(
            GraphMount.create(
                tenant_id=self.tenant.identity.id,
                name="default",
                store_root=(self.root / "graph").resolve(),
                created_at=timestamp(),
            )
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_tenant_and_mount_are_idempotent_and_paths_are_not_identity(self) -> None:
        self.assertEqual(
            self.control.create_tenant(
                Tenant.create(
                    slug="acme",
                    display_name="Acme",
                    created_at=timestamp(1),
                )
            ),
            self.tenant,
        )
        replacement = GraphMount.create(
            tenant_id=self.tenant.identity.id,
            name="default",
            store_root=(self.root / "replacement").resolve(),
            created_at=timestamp(1),
            updated_at=timestamp(2),
        )
        updated = self.control.mount_graph(replacement)
        self.assertEqual(updated.identity.id, self.mount.identity.id)
        self.assertEqual(updated.created_at, self.mount.created_at)
        self.assertEqual(
            self.control.graph_mount(self.tenant.identity.id).store_root,
            str((self.root / "replacement").resolve()),
        )

    def test_api_keys_are_hashed_scoped_and_revocable(self) -> None:
        issued = self.control.issue_api_key(
            self.tenant.identity.id,
            scopes=("graph:read", "jobs:*"),
            created_at=timestamp(1),
        )
        self.assertNotIn(issued.token.encode("utf-8"), self.control_path.read_bytes())
        principal = self.control.authenticate(issued.token, used_at=timestamp(2))
        self.control.require(principal, "graph:read")
        self.control.require(principal, "jobs:write")
        with self.assertRaises(AuthorizationError):
            self.control.require(principal, "audit:read")

        self.control.revoke_api_key(
            issued.key_id, actor="operator", revoked_at=timestamp(3)
        )
        with self.assertRaises(AuthenticationError):
            self.control.authenticate(issued.token, used_at=timestamp(4))

    def test_payloads_are_content_addressed_and_tenant_scoped(self) -> None:
        payload = {"operation": "analyze_python_path", "relative_path": "package"}
        first = self.control.put_job_payload(
            self.tenant.identity.id, payload, created_at=timestamp(1)
        )
        second = self.control.put_job_payload(
            self.tenant.identity.id, dict(reversed(tuple(payload.items()))), created_at=timestamp(2)
        )
        self.assertEqual(first, second)
        self.assertEqual(self.control.job_payload(self.tenant.identity.id, first), payload)

        other = self.control.create_tenant(
            Tenant.create(slug="other", display_name="Other", created_at=timestamp(3))
        )
        with self.assertRaisesRegex(ValueError, "tenant-scoped"):
            self.control.job_payload(other.identity.id, first)

    def test_audit_events_form_an_append_only_tenant_chain(self) -> None:
        issued = self.control.issue_api_key(
            self.tenant.identity.id,
            scopes=("graph:read",),
            created_at=timestamp(1),
        )
        self.control.revoke_api_key(
            issued.key_id, actor="operator", revoked_at=timestamp(2)
        )
        events = tuple(reversed(self.control.audit_events(self.tenant.identity.id)))
        self.assertGreaterEqual(len(events), 4)
        for previous, current in zip(events, events[1:]):
            self.assertEqual(current["previous_event_id"], previous["event_id"])

    def test_tenant_metrics_are_bounded_and_tenant_isolated(self) -> None:
        snapshot = self.control.tenant_metrics(self.tenant.identity.id)
        self.assertEqual(snapshot["tenant_id"], self.tenant.identity.id)
        self.assertEqual(snapshot["counts"]["graph_mounts"], 1)
        self.assertGreaterEqual(snapshot["counts"]["audit_events"], 2)
        self.assertEqual(snapshot["jobs_by_state"]["pending"], 0)
        other = self.control.create_tenant(
            Tenant.create(slug="metrics-other", display_name="Other", created_at=timestamp(5))
        )
        isolated = self.control.tenant_metrics(other.identity.id)
        self.assertEqual(isolated["counts"]["graph_mounts"], 0)
        self.assertEqual(isolated["counts"]["usage_receipts"], 0)


class PersistentWorkerQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.control = SQLiteControlPlane(self.root / "control.sqlite")
        self.tenant = self.control.create_tenant(
            Tenant.create(slug="worker", display_name="Worker", created_at=timestamp())
        )
        self.payload_ref = self.control.put_job_payload(
            self.tenant.identity.id,
            {"operation": "analyze_python_path", "relative_path": "package"},
            created_at=timestamp(),
        )
        self.job = WorkerJob.create(
            queue="default",
            kind=JobKind.EXTRACT,
            subject_id="package",
            payload_ref=self.payload_ref,
            idempotency_key="package@1",
            created_at=timestamp(),
            required_capabilities=("python-ast",),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_jobs_and_leases_survive_adapter_recreation(self) -> None:
        queue = SQLiteWorkerQueue(self.control)
        self.assertEqual(queue.enqueue(self.tenant.identity.id, self.job), self.job)
        reopened = SQLiteWorkerQueue(SQLiteControlPlane(self.root / "control.sqlite"))
        leased = reopened.claim(
            queue="default",
            worker_id="worker-a",
            leased_at=timestamp(1),
            expires_at=timestamp(60),
            lease_nonce="nonce-a",
            capabilities=("python-ast",),
        )
        self.assertIsNotNone(leased)
        assert leased is not None
        event = reopened.complete(
            leased,
            occurred_at=timestamp(2),
            output_refs=("sha256:" + "a" * 64,),
            metrics={"entities": 12},
        )
        self.assertEqual(event.event_kind, WorkerEventKind.SUCCEEDED)
        self.assertEqual(
            reopened.get(self.tenant.identity.id, self.job.identity.id).state,
            JobState.SUCCEEDED,
        )
        self.assertEqual(len(reopened.events(self.tenant.identity.id, self.job.identity.id)), 3)

    def test_capability_filter_and_expired_lease_requeue(self) -> None:
        queue = SQLiteWorkerQueue(self.control)
        queue.enqueue(self.tenant.identity.id, self.job)
        self.assertIsNone(
            queue.claim(
                queue="default",
                worker_id="wrong",
                leased_at=timestamp(1),
                expires_at=timestamp(60),
                lease_nonce="wrong",
                capabilities=(),
            )
        )
        leased = queue.claim(
            queue="default",
            worker_id="right",
            leased_at=timestamp(1),
            expires_at=timestamp(2),
            lease_nonce="right",
            capabilities=("python-ast",),
        )
        self.assertIsNotNone(leased)
        events = queue.requeue_expired(occurred_at=timestamp(3), actor="reaper")
        self.assertEqual(events[0].event_kind, WorkerEventKind.LEASE_EXPIRED)
        self.assertEqual(
            queue.get(self.tenant.identity.id, self.job.identity.id).state,
            JobState.PENDING,
        )

    def test_lease_heartbeat_and_cooperative_cancellation_survive_restart(self) -> None:
        queue = SQLiteWorkerQueue(self.control)
        queue.enqueue(self.tenant.identity.id, self.job)
        leased = queue.claim(
            queue="default",
            worker_id="worker-a",
            leased_at=timestamp(1),
            expires_at=timestamp(31),
            lease_nonce="nonce-a",
            capabilities=("python-ast",),
        )
        assert leased is not None
        renewed = queue.heartbeat(
            leased,
            occurred_at=timestamp(10),
            expires_at=timestamp(40),
            lease_nonce="nonce-b",
        )
        self.assertNotEqual(renewed.lease.identity.id, leased.lease.identity.id)
        with self.assertRaisesRegex(WorkerQueueError, "stale"):
            queue.complete(
                leased,
                occurred_at=timestamp(11),
                output_refs=("sha256:" + "a" * 64,),
            )
        request = queue.request_cancel(
            self.tenant.identity.id,
            self.job.identity.id,
            occurred_at=timestamp(12),
            actor="api-key:test",
        )
        self.assertEqual(request.event_kind, WorkerEventKind.CANCELLATION_REQUESTED)

        reopened = SQLiteWorkerQueue(SQLiteControlPlane(self.root / "control.sqlite"))
        stored = reopened.get(self.tenant.identity.id, self.job.identity.id)
        self.assertEqual(stored.cancellation_requested_at, timestamp(12))
        self.assertTrue(reopened.cancellation_requested(renewed))
        with self.assertRaisesRegex(WorkerQueueError, "cancellation"):
            reopened.complete(
                renewed,
                occurred_at=timestamp(13),
                output_refs=("sha256:" + "b" * 64,),
            )
        event = reopened.acknowledge_cancel(renewed, occurred_at=timestamp(14))
        self.assertEqual(event.event_kind, WorkerEventKind.CANCELLED)
        self.assertEqual(
            reopened.get(self.tenant.identity.id, self.job.identity.id).state,
            JobState.CANCELLED,
        )

    def test_pending_cancel_is_immediate_and_not_claimable(self) -> None:
        queue = SQLiteWorkerQueue(self.control)
        queue.enqueue(self.tenant.identity.id, self.job)
        first = queue.request_cancel(
            self.tenant.identity.id,
            self.job.identity.id,
            occurred_at=timestamp(1),
            actor="api-key:test",
        )
        second = queue.request_cancel(
            self.tenant.identity.id,
            self.job.identity.id,
            occurred_at=timestamp(2),
            actor="api-key:test",
        )
        self.assertEqual(first, second)
        self.assertEqual(
            queue.get(self.tenant.identity.id, self.job.identity.id).state,
            JobState.CANCELLED,
        )
        self.assertIsNone(
            queue.claim(
                queue="default",
                worker_id="worker-a",
                leased_at=timestamp(3),
                expires_at=timestamp(33),
                lease_nonce="nonce",
                capabilities=("python-ast",),
            )
        )

    def test_job_runner_renews_lease_while_handler_is_running(self) -> None:
        queue = SQLiteWorkerQueue(self.control)
        queue.enqueue(self.tenant.identity.id, self.job)

        class SlowRunner(JobRunner):
            def _execute(self, leased: Any) -> tuple[tuple[str, ...], Mapping[str, Any]]:
                time.sleep(0.12)
                return ("sha256:" + "c" * 64,), {"duration_ms": 120}

        result = SlowRunner(
            self.control,
            source_root=self.root,
            worker_id="slow-worker",
            lease_seconds=30,
            heartbeat_seconds=0.03,
        ).run_once()
        self.assertTrue(result.claimed)
        assert result.event is not None
        self.assertEqual(result.event.event_kind, WorkerEventKind.SUCCEEDED)
        kinds = [
            event.event_kind
            for event in queue.events(self.tenant.identity.id, self.job.identity.id)
        ]
        self.assertGreaterEqual(kinds.count(WorkerEventKind.HEARTBEAT), 2)

    def test_job_runner_acknowledges_cancellation_requested_during_handler(self) -> None:
        queue = SQLiteWorkerQueue(self.control)
        queue.enqueue(self.tenant.identity.id, self.job)
        started = threading.Event()
        release = threading.Event()
        result: list[Any] = []

        class BlockingRunner(JobRunner):
            def _execute(self, leased: Any) -> tuple[tuple[str, ...], Mapping[str, Any]]:
                started.set()
                if not release.wait(2):  # pragma: no cover - deadlock guard
                    raise RuntimeError("test did not release handler")
                return ("sha256:" + "d" * 64,), {}

        runner = BlockingRunner(
            self.control,
            source_root=self.root,
            worker_id="cancel-aware-worker",
            lease_seconds=30,
            heartbeat_seconds=0.03,
        )
        thread = threading.Thread(target=lambda: result.append(runner.run_once()))
        thread.start()
        self.assertTrue(started.wait(2))
        queue.request_cancel(
            self.tenant.identity.id,
            self.job.identity.id,
            occurred_at=utc_now(),
            actor="api-key:test",
        )
        release.set()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result[0].event.event_kind, WorkerEventKind.CANCELLED)
        self.assertEqual(
            queue.get(self.tenant.identity.id, self.job.identity.id).state,
            JobState.CANCELLED,
        )


if __name__ == "__main__":
    unittest.main()
