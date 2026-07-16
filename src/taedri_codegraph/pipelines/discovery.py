"""Replay-safe source discovery events that compile into executable worker jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from ..canonical import canonical_digest, to_primitive
from ..contracts import RecordMixin
from ..identity import IdentityRecord
from ..saas import SQLiteControlPlane, SQLiteWorkerQueue
from ..workers import JobKind, WorkerJob
from .catalog import PipelineCatalog, platform_pipeline_catalog


class DiscoveryKind(str, Enum):
    PYPI_RELEASE = "pypi_release"
    GITHUB_COMMIT = "github_commit"


@dataclass(frozen=True, slots=True)
class SourceDiscoveryEvent(RecordMixin):
    identity: IdentityRecord
    source: str
    source_event_id: str
    kind: DiscoveryKind
    subject: str
    occurred_at: str
    data: Mapping[str, Any]
    data_digest: str

    @classmethod
    def create(
        cls,
        *,
        source: str,
        source_event_id: str,
        kind: DiscoveryKind,
        subject: str,
        occurred_at: str,
        data: Mapping[str, Any],
    ) -> "SourceDiscoveryEvent":
        if not all((source, source_event_id, subject, occurred_at)):
            raise ValueError("discovery source, event, subject, and time are required")
        primitive = to_primitive(dict(data))
        if not isinstance(primitive, dict):  # pragma: no cover - defensive
            raise ValueError("discovery data must be an object")
        data_digest = canonical_digest(primitive)
        identity = IdentityRecord.create(
            "source_discovery_event",
            {
                "source": source,
                "source_event_id": source_event_id,
                "kind": kind.value,
                "subject": subject,
                "occurred_at": occurred_at,
                "data_digest": data_digest,
            },
        )
        return cls(
            identity,
            source,
            source_event_id,
            kind,
            subject,
            occurred_at,
            MappingProxyType(primitive),
            data_digest,
        )


@dataclass(frozen=True, slots=True)
class DiscoveryPolicy(RecordMixin):
    allowed_sources: tuple[str, ...]
    allowed_kinds: tuple[DiscoveryKind, ...] = (
        DiscoveryKind.PYPI_RELEASE,
        DiscoveryKind.GITHUB_COMMIT,
    )
    queue: str = "default"
    graph: str = "default"
    priority: int = 40
    max_attempts: int = 3
    publish: bool = True

    def __post_init__(self) -> None:
        sources = tuple(sorted(set(self.allowed_sources)))
        kinds = tuple(sorted(set(self.allowed_kinds), key=lambda item: item.value))
        if not sources or any(not value for value in sources) or not kinds:
            raise ValueError("discovery policy requires explicit sources and kinds")
        if not self.queue or not self.graph or not 0 <= self.priority <= 100:
            raise ValueError("discovery queue, graph, and priority are invalid")
        if self.max_attempts <= 0:
            raise ValueError("discovery max attempts must be positive")
        object.__setattr__(self, "allowed_sources", sources)
        object.__setattr__(self, "allowed_kinds", kinds)


@dataclass(frozen=True, slots=True)
class DiscoveryEnqueueReceipt(RecordMixin):
    event_id: str
    data_digest: str
    tenant_id: str
    job_id: str
    payload_ref: str
    operation: str
    pipeline_catalog_digest: str
    replayed: bool


class SourceDiscoveryRouter:
    """Compile allowlisted source events into the same job contracts as the API."""

    def __init__(
        self,
        control: SQLiteControlPlane,
        policy: DiscoveryPolicy,
        *,
        catalog: PipelineCatalog | None = None,
    ) -> None:
        self.control = control
        self.jobs = SQLiteWorkerQueue(control)
        self.policy = policy
        self.catalog = catalog or platform_pipeline_catalog()

    def enqueue(
        self,
        tenant_id: str,
        event: SourceDiscoveryEvent,
    ) -> DiscoveryEnqueueReceipt:
        if event.source not in self.policy.allowed_sources:
            raise ValueError("discovery event source is not allowlisted")
        if event.kind not in self.policy.allowed_kinds:
            raise ValueError("discovery event kind is not allowlisted")
        operation, payload = self._payload(event)
        contract = self.catalog.operation(operation)
        capabilities = contract.capabilities_for(payload)
        self.catalog.validate_operation(
            operation,
            kind=JobKind.ACQUIRE,
            supplied_capabilities=capabilities,
            payload=payload,
        )
        payload_ref = self.control.put_job_payload(
            tenant_id, payload, created_at=event.occurred_at
        )
        idempotency_key = f"discovery:{event.source}:{event.source_event_id}"
        previous = self.jobs.find_by_idempotency(
            tenant_id, queue=self.policy.queue, idempotency_key=idempotency_key
        )
        job = WorkerJob.create(
            queue=self.policy.queue,
            kind=JobKind.ACQUIRE,
            subject_id=event.subject,
            payload_ref=payload_ref,
            idempotency_key=idempotency_key,
            created_at=event.occurred_at,
            priority=self.policy.priority,
            max_attempts=self.policy.max_attempts,
            required_capabilities=capabilities,
        )
        accepted = self.jobs.enqueue(tenant_id, job)
        return DiscoveryEnqueueReceipt(
            event.identity.id,
            event.data_digest,
            tenant_id,
            accepted.identity.id,
            payload_ref,
            operation,
            self.catalog.digest,
            previous is not None,
        )

    def _payload(self, event: SourceDiscoveryEvent) -> tuple[str, dict[str, Any]]:
        lineage = {
            "event_id": event.identity.id,
            "source": event.source,
            "source_event_id": event.source_event_id,
            "data_digest": event.data_digest,
        }
        if event.kind is DiscoveryKind.PYPI_RELEASE:
            package = _required(event.data, "package")
            version = _required(event.data, "version")
            payload: dict[str, Any] = {
                "operation": "ingest_pypi_wheel",
                "package": package,
                "version": version,
                "graph": self.policy.graph,
                "publish": self.policy.publish,
                "discovery": lineage,
            }
            filename = event.data.get("filename")
            if filename is not None:
                if not isinstance(filename, str) or not filename:
                    raise ValueError("discovery filename must be a non-empty string")
                payload["filename"] = filename
            return "ingest_pypi_wheel", payload
        if event.kind is DiscoveryKind.GITHUB_COMMIT:
            analysis = str(event.data.get("analysis") or "python")
            payload = {
                "operation": "ingest_github_commit",
                "repository": _required(event.data, "repository"),
                "commit_sha": _required(event.data, "commit_sha"),
                "analysis": analysis,
                "graph": self.policy.graph,
                "publish": self.policy.publish,
                "discovery": lineage,
            }
            return "ingest_github_commit", payload
        raise ValueError("unsupported discovery kind")  # pragma: no cover


def _required(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"discovery {key} is required")
    return value
