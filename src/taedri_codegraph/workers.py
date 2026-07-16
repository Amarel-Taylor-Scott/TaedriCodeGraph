"""Lease-based worker contracts with idempotent jobs and append-only receipts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Iterable, Mapping

from .canonical import canonical_json_bytes, sha256_digest, to_primitive
from .contracts import RecordMixin
from .identity import IdentityRecord


class WorkerQueueError(ValueError):
    """Raised when a job, lease, or attempt violates the worker contract."""


class JobKind(str, Enum):
    ACQUIRE = "acquire"
    EXTRACT = "extract"
    DESCRIBE = "describe"
    EMBED = "embed"
    INDEX = "index"
    VERIFY = "verify"
    MATERIALIZE = "materialize"
    RENDER = "render"
    BENCHMARK = "benchmark"


class JobState(str, Enum):
    PENDING = "pending"
    LEASED = "leased"
    SUCCEEDED = "succeeded"
    DEAD_LETTER = "dead_letter"


class WorkerEventKind(str, Enum):
    ENQUEUED = "enqueued"
    LEASED = "leased"
    SUCCEEDED = "succeeded"
    FAILED_RETRYABLE = "failed_retryable"
    DEAD_LETTERED = "dead_lettered"
    LEASE_EXPIRED = "lease_expired"


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WorkerQueueError(f"invalid timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise WorkerQueueError("worker timestamps must include a UTC offset")
    return parsed


@dataclass(frozen=True, slots=True)
class WorkerJob(RecordMixin):
    identity: IdentityRecord
    format_version: str
    queue: str
    kind: JobKind
    subject_id: str
    payload_ref: str
    idempotency_key: str
    priority: int
    max_attempts: int
    created_at: str
    required_capabilities: tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        queue: str,
        kind: JobKind,
        subject_id: str,
        payload_ref: str,
        idempotency_key: str,
        created_at: str,
        priority: int = 50,
        max_attempts: int = 3,
        required_capabilities: Iterable[str] = (),
    ) -> "WorkerJob":
        if not all((queue, subject_id, payload_ref, idempotency_key, created_at)):
            raise WorkerQueueError("job queue, subject, payload, key, and time are required")
        if not payload_ref.startswith(("sha256:", "uceg:v1:")):
            raise WorkerQueueError("job payload_ref must be content or graph addressed")
        if not 0 <= priority <= 100 or max_attempts <= 0:
            raise WorkerQueueError("priority must be 0..100 and max_attempts must be positive")
        _timestamp(created_at)
        capabilities = tuple(sorted(set(required_capabilities)))
        key = {
            "format_version": "1.0.0",
            "queue": queue,
            "kind": kind.value,
            "subject_id": subject_id,
            "payload_ref": payload_ref,
            "idempotency_key": idempotency_key,
            "priority": priority,
            "max_attempts": max_attempts,
            "created_at": created_at,
            "required_capabilities": capabilities,
        }
        return cls(
            IdentityRecord.create("worker_job", key),
            "1.0.0",
            queue,
            kind,
            subject_id,
            payload_ref,
            idempotency_key,
            priority,
            max_attempts,
            created_at,
            capabilities,
        )


@dataclass(frozen=True, slots=True)
class WorkerLease(RecordMixin):
    identity: IdentityRecord
    job_id: str
    attempt: int
    worker_id: str
    lease_token: str
    leased_at: str
    expires_at: str

    @classmethod
    def create(
        cls,
        *,
        job_id: str,
        attempt: int,
        worker_id: str,
        leased_at: str,
        expires_at: str,
        lease_nonce: str,
    ) -> "WorkerLease":
        if attempt <= 0 or not all((job_id, worker_id, leased_at, expires_at, lease_nonce)):
            raise WorkerQueueError("lease fields and a caller-supplied nonce are required")
        if _timestamp(expires_at) <= _timestamp(leased_at):
            raise WorkerQueueError("lease expiry must be after lease acquisition")
        token = sha256_digest(
            canonical_json_bytes(
                {
                    "job_id": job_id,
                    "attempt": attempt,
                    "worker_id": worker_id,
                    "leased_at": leased_at,
                    "expires_at": expires_at,
                    "lease_nonce": lease_nonce,
                }
            )
        )
        key = {
            "job_id": job_id,
            "attempt": attempt,
            "worker_id": worker_id,
            "lease_token_digest": token,
            "leased_at": leased_at,
            "expires_at": expires_at,
        }
        return cls(
            IdentityRecord.create("worker_lease", key),
            job_id,
            attempt,
            worker_id,
            token,
            leased_at,
            expires_at,
        )


@dataclass(frozen=True, slots=True)
class WorkerEvent(RecordMixin):
    identity: IdentityRecord
    sequence: int
    job_id: str
    attempt: int
    event_kind: WorkerEventKind
    worker_id: str | None
    occurred_at: str
    lease_id: str | None
    output_refs: tuple[str, ...]
    metrics: Mapping[str, Any]
    detail: str

    @classmethod
    def create(
        cls,
        *,
        sequence: int,
        job_id: str,
        attempt: int,
        event_kind: WorkerEventKind,
        occurred_at: str,
        detail: str,
        worker_id: str | None = None,
        lease_id: str | None = None,
        output_refs: Iterable[str] = (),
        metrics: Mapping[str, Any] | None = None,
    ) -> "WorkerEvent":
        if sequence <= 0 or attempt < 0 or not all((job_id, occurred_at, detail)):
            raise WorkerQueueError("worker event identity and provenance are required")
        _timestamp(occurred_at)
        outputs = tuple(sorted(set(output_refs)))
        metric_values = to_primitive(dict(metrics or {}))
        if not isinstance(metric_values, dict):  # pragma: no cover - defensive
            raise WorkerQueueError("worker metrics must be a mapping")
        key = {
            "sequence": sequence,
            "job_id": job_id,
            "attempt": attempt,
            "event_kind": event_kind.value,
            "worker_id": worker_id,
            "occurred_at": occurred_at,
            "lease_id": lease_id,
            "output_refs": outputs,
            "metrics": metric_values,
            "detail": detail,
        }
        return cls(
            IdentityRecord.create("worker_event", key),
            sequence,
            job_id,
            attempt,
            event_kind,
            worker_id,
            occurred_at,
            lease_id,
            outputs,
            metric_values,
            detail,
        )


class WorkerQueue:
    """Reference queue; production adapters map the same rules to PostgreSQL/SQS/etc."""

    def __init__(self) -> None:
        self.jobs: dict[str, WorkerJob] = {}
        self.events: list[WorkerEvent] = []
        self._idempotency: dict[tuple[str, str], str] = {}
        self._states: dict[str, JobState] = {}
        self._attempts: dict[str, int] = {}
        self._leases: dict[str, WorkerLease] = {}

    def enqueue(self, job: WorkerJob) -> WorkerJob:
        key = (job.queue, job.idempotency_key)
        existing_id = self._idempotency.get(key)
        if existing_id is not None:
            existing = self.jobs[existing_id]
            if existing != job:
                raise WorkerQueueError("an idempotency key cannot describe two jobs")
            return existing
        self.jobs[job.identity.id] = job
        self._idempotency[key] = job.identity.id
        self._states[job.identity.id] = JobState.PENDING
        self._attempts[job.identity.id] = 0
        self._append(
            job,
            WorkerEventKind.ENQUEUED,
            occurred_at=job.created_at,
            detail="job accepted under its queue-scoped idempotency key",
        )
        return job

    def state(self, job_id: str) -> JobState:
        try:
            return self._states[job_id]
        except KeyError as exc:
            raise WorkerQueueError(f"unknown job: {job_id}") from exc

    def claim(
        self,
        *,
        queue: str,
        worker_id: str,
        leased_at: str,
        expires_at: str,
        lease_nonce: str,
        capabilities: Iterable[str] = (),
        kinds: Iterable[JobKind] | None = None,
    ) -> WorkerLease | None:
        worker_capabilities = set(capabilities)
        allowed_kinds = set(kinds) if kinds is not None else set(JobKind)
        eligible = [
            job
            for job in self.jobs.values()
            if job.queue == queue
            and self._states[job.identity.id] is JobState.PENDING
            and job.kind in allowed_kinds
            and set(job.required_capabilities).issubset(worker_capabilities)
        ]
        if not eligible:
            return None
        eligible.sort(key=lambda job: (-job.priority, job.created_at, job.identity.id))
        job = eligible[0]
        attempt = self._attempts[job.identity.id] + 1
        lease = WorkerLease.create(
            job_id=job.identity.id,
            attempt=attempt,
            worker_id=worker_id,
            leased_at=leased_at,
            expires_at=expires_at,
            lease_nonce=lease_nonce,
        )
        self._attempts[job.identity.id] = attempt
        self._states[job.identity.id] = JobState.LEASED
        self._leases[job.identity.id] = lease
        self._append(
            job,
            WorkerEventKind.LEASED,
            occurred_at=leased_at,
            detail="worker acquired an exclusive time-bounded lease",
            worker_id=worker_id,
            lease=lease,
        )
        return lease

    def complete(
        self,
        lease: WorkerLease,
        *,
        occurred_at: str,
        output_refs: Iterable[str],
        metrics: Mapping[str, Any] | None = None,
    ) -> WorkerEvent:
        job = self._validate_active_lease(lease, occurred_at)
        outputs = tuple(output_refs)
        if not outputs:
            raise WorkerQueueError("successful attempts must name at least one output receipt")
        self._states[job.identity.id] = JobState.SUCCEEDED
        del self._leases[job.identity.id]
        return self._append(
            job,
            WorkerEventKind.SUCCEEDED,
            occurred_at=occurred_at,
            detail="worker completed the leased job",
            worker_id=lease.worker_id,
            lease=lease,
            output_refs=outputs,
            metrics=metrics,
        )

    def fail(
        self,
        lease: WorkerLease,
        *,
        occurred_at: str,
        detail: str,
        retryable: bool,
        output_refs: Iterable[str] = (),
        metrics: Mapping[str, Any] | None = None,
    ) -> WorkerEvent:
        job = self._validate_active_lease(lease, occurred_at)
        can_retry = retryable and lease.attempt < job.max_attempts
        self._states[job.identity.id] = (
            JobState.PENDING if can_retry else JobState.DEAD_LETTER
        )
        del self._leases[job.identity.id]
        return self._append(
            job,
            (
                WorkerEventKind.FAILED_RETRYABLE
                if can_retry
                else WorkerEventKind.DEAD_LETTERED
            ),
            occurred_at=occurred_at,
            detail=detail,
            worker_id=lease.worker_id,
            lease=lease,
            output_refs=output_refs,
            metrics=metrics,
        )

    def requeue_expired(self, *, occurred_at: str, actor: str) -> tuple[WorkerEvent, ...]:
        now = _timestamp(occurred_at)
        expired = [
            lease
            for lease in self._leases.values()
            if _timestamp(lease.expires_at) < now
        ]
        events: list[WorkerEvent] = []
        for lease in sorted(expired, key=lambda item: item.job_id):
            job = self.jobs[lease.job_id]
            can_retry = lease.attempt < job.max_attempts
            self._states[job.identity.id] = (
                JobState.PENDING if can_retry else JobState.DEAD_LETTER
            )
            del self._leases[job.identity.id]
            events.append(
                self._append(
                    job,
                    (
                        WorkerEventKind.LEASE_EXPIRED
                        if can_retry
                        else WorkerEventKind.DEAD_LETTERED
                    ),
                    occurred_at=occurred_at,
                    detail=f"{actor} reclaimed an expired worker lease",
                    worker_id=lease.worker_id,
                    lease=lease,
                )
            )
        return tuple(events)

    def _validate_active_lease(
        self, lease: WorkerLease, occurred_at: str
    ) -> WorkerJob:
        job = self.jobs.get(lease.job_id)
        active = self._leases.get(lease.job_id)
        if job is None or active != lease or self._states.get(lease.job_id) is not JobState.LEASED:
            raise WorkerQueueError("stale or unknown worker lease")
        if _timestamp(occurred_at) > _timestamp(lease.expires_at):
            raise WorkerQueueError("worker lease expired before completion")
        return job

    def _append(
        self,
        job: WorkerJob,
        kind: WorkerEventKind,
        *,
        occurred_at: str,
        detail: str,
        worker_id: str | None = None,
        lease: WorkerLease | None = None,
        output_refs: Iterable[str] = (),
        metrics: Mapping[str, Any] | None = None,
    ) -> WorkerEvent:
        event = WorkerEvent.create(
            sequence=len(self.events) + 1,
            job_id=job.identity.id,
            attempt=lease.attempt if lease is not None else self._attempts[job.identity.id],
            event_kind=kind,
            worker_id=worker_id,
            occurred_at=occurred_at,
            lease_id=lease.identity.id if lease is not None else None,
            output_refs=output_refs,
            metrics=metrics,
            detail=detail,
        )
        self.events.append(event)
        return event
