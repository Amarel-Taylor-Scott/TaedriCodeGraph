from __future__ import annotations

import unittest

from taedri_codegraph.canonical import sha256_digest
from taedri_codegraph.workers import (
    JobKind,
    JobState,
    WorkerJob,
    WorkerQueue,
    WorkerQueueError,
)


class WorkerQueueTests(unittest.TestCase):
    def job(self, *, max_attempts: int = 2) -> WorkerJob:
        return WorkerJob.create(
            queue="indexing",
            kind=JobKind.EXTRACT,
            subject_id="repository:fixture",
            payload_ref=sha256_digest(b"source-tree"),
            idempotency_key="extract:fixture:abc123",
            priority=80,
            max_attempts=max_attempts,
            created_at="2026-07-16T12:00:00Z",
            required_capabilities=("python-ast",),
        )

    def test_idempotent_job_lease_and_success_receipt(self) -> None:
        queue = WorkerQueue()
        job = self.job()
        self.assertEqual(queue.enqueue(job), queue.enqueue(job))
        self.assertEqual(len(queue.jobs), 1)
        self.assertIsNone(
            queue.claim(
                queue="indexing",
                worker_id="worker-without-parser",
                leased_at="2026-07-16T12:00:01Z",
                expires_at="2026-07-16T12:05:01Z",
                lease_nonce="nonce-0",
            )
        )
        lease = queue.claim(
            queue="indexing",
            worker_id="worker-1",
            leased_at="2026-07-16T12:00:01Z",
            expires_at="2026-07-16T12:05:01Z",
            lease_nonce="nonce-1",
            capabilities=("python-ast",),
        )
        self.assertIsNotNone(lease)
        assert lease is not None
        event = queue.complete(
            lease,
            occurred_at="2026-07-16T12:00:03Z",
            output_refs=("uceg:v1:primitive_factory_result:fixture",),
            metrics={"candidate_count": 4, "duration_ms": 2},
        )
        self.assertEqual(queue.state(job.identity.id), JobState.SUCCEEDED)
        self.assertEqual(event.output_refs, ("uceg:v1:primitive_factory_result:fixture",))
        with self.assertRaises(WorkerQueueError):
            queue.complete(
                lease,
                occurred_at="2026-07-16T12:00:04Z",
                output_refs=("receipt:duplicate",),
            )

    def test_retry_then_dead_letter_at_attempt_limit(self) -> None:
        queue = WorkerQueue()
        job = queue.enqueue(self.job(max_attempts=2))
        first = queue.claim(
            queue="indexing",
            worker_id="worker-1",
            leased_at="2026-07-16T12:00:01Z",
            expires_at="2026-07-16T12:05:01Z",
            lease_nonce="nonce-1",
            capabilities=("python-ast",),
        )
        assert first is not None
        queue.fail(
            first,
            occurred_at="2026-07-16T12:00:02Z",
            detail="transient object-store failure",
            retryable=True,
        )
        self.assertEqual(queue.state(job.identity.id), JobState.PENDING)
        second = queue.claim(
            queue="indexing",
            worker_id="worker-2",
            leased_at="2026-07-16T12:00:03Z",
            expires_at="2026-07-16T12:05:03Z",
            lease_nonce="nonce-2",
            capabilities=("python-ast",),
        )
        assert second is not None
        queue.fail(
            second,
            occurred_at="2026-07-16T12:00:04Z",
            detail="invalid analyzer output",
            retryable=True,
        )
        self.assertEqual(queue.state(job.identity.id), JobState.DEAD_LETTER)

    def test_expired_lease_is_requeued_and_cannot_complete(self) -> None:
        queue = WorkerQueue()
        job = queue.enqueue(self.job())
        lease = queue.claim(
            queue="indexing",
            worker_id="worker-1",
            leased_at="2026-07-16T12:00:01Z",
            expires_at="2026-07-16T12:00:02Z",
            lease_nonce="nonce-1",
            capabilities=("python-ast",),
        )
        assert lease is not None
        events = queue.requeue_expired(
            occurred_at="2026-07-16T12:00:03Z", actor="queue-reaper"
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(queue.state(job.identity.id), JobState.PENDING)
        with self.assertRaises(WorkerQueueError):
            queue.complete(
                lease,
                occurred_at="2026-07-16T12:00:03Z",
                output_refs=("receipt:late",),
            )


if __name__ == "__main__":
    unittest.main()

