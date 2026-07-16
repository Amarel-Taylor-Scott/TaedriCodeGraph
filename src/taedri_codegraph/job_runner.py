"""Executable worker handlers for safe, source-mounted graph jobs."""

from __future__ import annotations

import secrets
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .acquisition import (
    AcquisitionTransport,
    BoundedHTTPTransport,
    GitHubArchiveAcquirer,
    NetworkAcquisitionPolicy,
    PyPIAcquirer,
    RetryableAcquisitionError,
    attach_acquisition_receipt,
)
from .analyzers import PythonSyntaxAnalyzer
from .artifacts import analyze_wheel
from .candidate_repository import SQLiteCandidateRepository
from .canonical import canonical_digest
from .contracts import ProducerRef, RecordMixin
from .intake import (
    CandidateIntakeLedger,
    CandidateVisibility,
    LicenseEvidenceState,
)
from .primitive_capsules import PrimitiveRegistry, RefKind
from .primitive_factory import PrimitiveFactory
from .primitive_repository import SQLitePrimitiveRepository
from .primitives.acceptance import (
    LocalPythonPrimitiveVerifier,
    PrimitiveVerifierRegistry,
)
from .primitives.release import AssuranceLevel
from .pipelines import platform_pipeline_catalog
from .saas import LeasedJob, SQLiteControlPlane, SQLiteWorkerQueue, utc_now
from .sources import PolyglotInventoryAnalyzer
from .storage import GraphStore
from .workers import JobKind, WorkerEvent, WorkerQueueError


class JobRunnerError(ValueError):
    """Raised when an executable job payload is invalid or unsupported."""


@dataclass(frozen=True, slots=True)
class JobRunResult(RecordMixin):
    claimed: bool
    tenant_id: str | None
    job_id: str | None
    event: WorkerEvent | None


class _LeaseKeeper:
    """Renews one lease while a synchronous handler is running."""

    def __init__(
        self,
        queue: SQLiteWorkerQueue,
        leased: LeasedJob,
        *,
        lease_seconds: int,
        heartbeat_seconds: float,
    ) -> None:
        self.queue = queue
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self._leased = leased
        self._error: WorkerQueueError | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"taedri-heartbeat-{leased.job.identity.id[-12:]}",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> tuple[LeasedJob, WorkerQueueError | None]:
        self._stop.set()
        self._thread.join()
        with self._lock:
            return self._leased, self._error

    def _run(self) -> None:
        while not self._stop.wait(self.heartbeat_seconds):
            now = datetime.now(timezone.utc)
            with self._lock:
                active = self._leased
            try:
                renewed = self.queue.heartbeat(
                    active,
                    occurred_at=JobRunner._format_time(now),
                    expires_at=JobRunner._format_time(
                        now + timedelta(seconds=self.lease_seconds)
                    ),
                    lease_nonce=secrets.token_hex(24),
                )
            except WorkerQueueError as exc:
                with self._lock:
                    self._error = exc
                return
            with self._lock:
                self._leased = renewed


class JobRunner:
    """Claims persistent jobs and executes explicitly registered safe operations.

    Source jobs can only name a relative path beneath an operator-mounted source root.
    They retain the syntax analyzers' no-import/no-execution guarantee.
    """

    def __init__(
        self,
        control: SQLiteControlPlane,
        *,
        source_root: str | Path,
        worker_id: str,
        queue: str = "default",
        capabilities: Iterable[str] | None = None,
        lease_seconds: int = 900,
        heartbeat_seconds: float | None = None,
        allow_network_acquisition: bool = False,
        acquisition_transport: AcquisitionTransport | None = None,
        acquisition_policy: NetworkAcquisitionPolicy | None = None,
        github_token: str | None = None,
    ):
        root = Path(source_root).expanduser().resolve()
        if not root.is_dir():
            raise JobRunnerError(f"worker source root is not a directory: {root}")
        if not worker_id or not queue:
            raise JobRunnerError("worker ID and queue are required")
        if not 30 <= lease_seconds <= 86_400:
            raise JobRunnerError("worker lease must be between 30 seconds and one day")
        effective_heartbeat = (
            min(60.0, lease_seconds / 3)
            if heartbeat_seconds is None
            else heartbeat_seconds
        )
        if not 0.01 <= effective_heartbeat < lease_seconds:
            raise JobRunnerError(
                "worker heartbeat must be at least 0.01 seconds and shorter than its lease"
            )
        self.control = control
        self.queue_store = SQLiteWorkerQueue(control)
        self.source_root = root
        self.worker_id = worker_id
        self.queue = queue
        default_capabilities = {
            "python-ast",
            "polyglot-inventory",
            "primitive-factory-v1",
        }
        if allow_network_acquisition:
            default_capabilities.update({"pypi-acquire", "github-acquire"})
        self.capabilities = tuple(
            sorted(set(default_capabilities if capabilities is None else capabilities))
        )
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = effective_heartbeat
        self.allow_network_acquisition = allow_network_acquisition
        self.acquisition_policy = acquisition_policy or NetworkAcquisitionPolicy()
        self.acquisition_transport = acquisition_transport
        self.github_token = github_token
        self.pipeline_catalog = platform_pipeline_catalog()

    def run_once(self) -> JobRunResult:
        leased_at = datetime.now(timezone.utc)
        expires_at = leased_at + timedelta(seconds=self.lease_seconds)
        leased = self.queue_store.claim(
            queue=self.queue,
            worker_id=self.worker_id,
            leased_at=self._format_time(leased_at),
            expires_at=self._format_time(expires_at),
            lease_nonce=secrets.token_hex(24),
            capabilities=self.capabilities,
            kinds=(JobKind.ACQUIRE, JobKind.EXTRACT, JobKind.INDEX, JobKind.VERIFY),
        )
        if leased is None:
            return JobRunResult(False, None, None, None)
        keeper = _LeaseKeeper(
            self.queue_store,
            leased,
            lease_seconds=self.lease_seconds,
            heartbeat_seconds=self.heartbeat_seconds,
        )
        keeper.start()
        try:
            output_refs, metrics = self._execute(leased)
            active, heartbeat_error = keeper.stop()
            if self.queue_store.cancellation_requested(active):
                event = self.queue_store.acknowledge_cancel(
                    active, occurred_at=utc_now()
                )
            elif heartbeat_error is not None:
                event = self.queue_store.fail(
                    active,
                    occurred_at=utc_now(),
                    detail=f"lease heartbeat failed: {heartbeat_error}"[:1000],
                    retryable=True,
                )
            else:
                event = self.queue_store.complete(
                    active,
                    occurred_at=utc_now(),
                    output_refs=output_refs,
                    metrics=metrics,
                )
        except Exception as exc:
            active, _ = keeper.stop()
            if self.queue_store.cancellation_requested(active):
                event = self.queue_store.acknowledge_cancel(
                    active, occurred_at=utc_now()
                )
            else:
                retryable = isinstance(exc, RetryableAcquisitionError) or (
                    isinstance(exc, OSError)
                    and not isinstance(exc, (FileNotFoundError, PermissionError))
                )
                detail = f"{type(exc).__name__}: {exc}"
                event = self.queue_store.fail(
                    active,
                    occurred_at=utc_now(),
                    detail=detail[:1000],
                    retryable=retryable,
                )
        return JobRunResult(True, leased.tenant_id, leased.job.identity.id, event)

    def run_forever(self, *, poll_seconds: float = 2.0) -> None:
        if not 0.1 <= poll_seconds <= 60:
            raise JobRunnerError("poll interval must be between 0.1 and 60 seconds")
        while True:
            result = self.run_once()
            if not result.claimed:
                time.sleep(poll_seconds)

    def _execute(self, leased: LeasedJob) -> tuple[tuple[str, ...], Mapping[str, Any]]:
        payload = self.control.job_payload(leased.tenant_id, leased.job.payload_ref)
        operation = payload.get("operation")
        try:
            self.pipeline_catalog.validate_operation(
                operation,
                kind=leased.job.kind,
                supplied_capabilities=leased.job.required_capabilities,
                payload=payload,
            )
        except ValueError as exc:
            raise JobRunnerError(str(exc)) from exc
        if operation == "analyze_python_path":
            return self._analyze_python_path(leased, payload)
        if operation == "inventory_source_path":
            return self._inventory_source_path(leased, payload)
        if operation == "ingest_pypi_wheel":
            return self._ingest_pypi_wheel(leased, payload)
        if operation == "ingest_github_commit":
            return self._ingest_github_commit(leased, payload)
        if operation == "generate_primitive_candidates":
            return self._generate_primitive_candidates(leased, payload)
        if operation == "verify_primitive_release":
            return self._verify_primitive_release(leased, payload)
        raise JobRunnerError(f"unsupported worker operation: {operation!r}")

    def _verify_primitive_release(
        self, leased: LeasedJob, payload: Mapping[str, Any]
    ) -> tuple[tuple[str, ...], Mapping[str, Any]]:
        revision_id = self._required_string(payload, "revision_id")
        authorizer_id = self._required_string(payload, "authorizer_id")
        policy_decision_id = self._required_string(payload, "policy_decision_id")
        try:
            ref_kind = RefKind(str(payload.get("ref_kind") or "branch"))
            assurance = AssuranceLevel(
                str(payload.get("assurance_level") or "bootstrap")
            )
        except ValueError as exc:
            raise JobRunnerError("release ref kind or assurance level is invalid") from exc
        ref_name = self._optional_string(payload, "ref_name") or "main"
        repository = SQLitePrimitiveRepository(self.control)
        verifiers = PrimitiveVerifierRegistry(repository)
        verifiers.register(LocalPythonPrimitiveVerifier(
            repository,
            verifier_id=f"worker:{self.worker_id}:local-python-v1",
        ))
        result = verifiers.verify_and_release(
            leased.tenant_id,
            revision_id,
            ref_kind=ref_kind,
            ref_name=ref_name,
            authorizer_id=authorizer_id,
            policy_decision_id=policy_decision_id,
            verified_at=utc_now(),
            assurance_level=assurance,
        )
        return (
            (
                result.released.release.identity.id,
                result.acceptance_receipt_ref,
                result.released.release.revision_id,
            ),
            {
                "released_primitives": 1,
                "executed_cases": result.executed_case_count,
                "materialized_files": len(result.digestion.files),
                "materialized_bytes": result.digestion.materialized_bytes,
            },
        )

    def _generate_primitive_candidates(
        self, leased: LeasedJob, payload: Mapping[str, Any]
    ) -> tuple[tuple[str, ...], Mapping[str, Any]]:
        source = self._source_path(payload)
        namespace = self._required_string(payload, "namespace")
        package_name = self._optional_string(payload, "package_name") or source.name
        source_uri = self._optional_string(payload, "source_uri") or (
            "mounted:" + source.relative_to(self.source_root).as_posix()
        )
        candidate_limit = payload.get("candidate_limit", 1000)
        if (
            isinstance(candidate_limit, bool)
            or not isinstance(candidate_limit, int)
            or not 1 <= candidate_limit <= 5000
        ):
            raise JobRunnerError("candidate_limit must be an integer between 1 and 5000")
        try:
            visibility = CandidateVisibility(str(payload.get("visibility") or "private"))
            license_state = LicenseEvidenceState(
                str(payload.get("license_evidence_state") or "unknown")
            )
        except ValueError as exc:
            raise JobRunnerError("candidate visibility or license evidence state is invalid") from exc
        registry = PrimitiveRegistry()
        intake = CandidateIntakeLedger()
        producer = ProducerRef(
            "taedri.worker.primitive-factory",
            "1.0.0",
            canonical_digest(
                {
                    "contract": "python-function-candidates-v1",
                    "ast_only": True,
                    "candidate_limit": candidate_limit,
                }
            ),
        )
        result = PrimitiveFactory().generate(
            source,
            registry=registry,
            intake=intake,
            producer=producer,
            package_name=package_name,
            namespace=namespace,
            source_uri=source_uri,
            source_revision=self._optional_string(payload, "source_revision"),
            created_at=leased.job.created_at,
            license_expression=self._optional_string(payload, "license_expression"),
            license_evidence_state=license_state,
            visibility=visibility,
            max_candidates=candidate_limit,
        )
        actor = f"worker:{self.worker_id}"
        run_suffix = result.generation_run_id.rsplit(":", 1)[-1][:16]
        primitive_import = SQLitePrimitiveRepository(self.control).import_registry(
            leased.tenant_id,
            registry,
            actor=actor,
            imported_at=utc_now(),
            resource_id=result.identity.id,
            conflict_ref_suffix=run_suffix,
        )
        candidate_import = SQLiteCandidateRepository(self.control).import_ledger(
            leased.tenant_id,
            intake,
            actor=actor,
            imported_at=utc_now(),
            resource_id=result.identity.id,
        )
        receipt = {
            "format_version": "1.0.0",
            "operation": "generate_primitive_candidates",
            "tenant_id": leased.tenant_id,
            "job_id": leased.job.identity.id,
            "source_relative_path": str(source.relative_to(self.source_root)),
            "source_uri": source_uri,
            "factory_result": result.to_dict(),
            "primitive_import": primitive_import.to_dict(),
            "candidate_import": candidate_import.to_dict(),
            "execution_policy": "AST-only; source was not imported or executed",
            "completed_at": utc_now(),
        }
        receipt_ref = self.control.put_job_payload(leased.tenant_id, receipt)
        return (result.identity.id, result.generation_run_id, receipt_ref), {
            "source_files": result.source_file_count,
            "source_bytes": result.scanned_source_bytes,
            "candidate_count": len(result.candidates),
            "diagnostic_count": len(result.diagnostics),
            "unique_blob_count": result.unique_blob_count,
            "unique_blob_bytes": result.unique_blob_bytes,
        }

    def _transport(self) -> AcquisitionTransport:
        if not self.allow_network_acquisition:
            raise JobRunnerError("network acquisition is disabled for this worker")
        return self.acquisition_transport or BoundedHTTPTransport(self.acquisition_policy)

    def _ingest_pypi_wheel(
        self, leased: LeasedJob, payload: Mapping[str, Any]
    ) -> tuple[tuple[str, ...], Mapping[str, Any]]:
        package = self._required_string(payload, "package")
        version = self._required_string(payload, "version")
        filename = self._optional_string(payload, "filename")
        with tempfile.TemporaryDirectory(prefix="taedri-pypi-") as temporary:
            artifact, acquisition = PyPIAcquirer(
                self._transport(), self.acquisition_policy
            ).acquire_wheel(
                package,
                version,
                Path(temporary),
                acquired_at=utc_now(),
                filename=filename,
                allow_yanked=bool(payload.get("allow_yanked", False)),
            )
            analyzer = PythonSyntaxAnalyzer()
            bundle, inspection = analyze_wheel(artifact.path, analyzer)
            attach_acquisition_receipt(bundle, acquisition, artifact.path)
            store = self._graph_store(leased, payload)
            epoch_id = store.write_candidate(bundle, analyzer.registry)
            published = bool(payload.get("publish", True))
            if published:
                store.publish_epoch(epoch_id)
            receipt = {
                "format_version": "1.0.0",
                "operation": "ingest_pypi_wheel",
                "graph": str(payload.get("graph") or "default"),
                "tenant_id": leased.tenant_id,
                "job_id": leased.job.identity.id,
                "acquisition": acquisition.to_dict(),
                "inspection": inspection.to_dict(),
                "epoch_id": epoch_id,
                "published": published,
                "summary": bundle.summary(),
                "completed_at": utc_now(),
            }
            receipt_ref = self.control.put_job_payload(leased.tenant_id, receipt)
        return (epoch_id, receipt_ref, acquisition.artifact_digest), {
            "artifact_bytes": acquisition.artifact_size_bytes,
            "files": len(bundle.files),
            "entities": len(bundle.entities),
            "relations": len(bundle.relations),
        }

    def _ingest_github_commit(
        self, leased: LeasedJob, payload: Mapping[str, Any]
    ) -> tuple[tuple[str, ...], Mapping[str, Any]]:
        repository = self._required_string(payload, "repository")
        commit_sha = self._required_string(payload, "commit_sha")
        analysis_mode = str(payload.get("analysis") or "python")
        if analysis_mode not in {"python", "inventory"}:
            raise JobRunnerError("GitHub analysis must be 'python' or 'inventory'")
        with tempfile.TemporaryDirectory(prefix="taedri-github-") as temporary:
            root = Path(temporary)
            acquirer = GitHubArchiveAcquirer(
                self._transport(),
                self.acquisition_policy,
                token=self.github_token,
            )
            artifact, acquisition = acquirer.acquire_commit(
                repository,
                commit_sha,
                root / "artifacts",
                acquired_at=utc_now(),
            )
            source = acquirer.extract_commit_archive(artifact.path, root / "source")
            package_name = self._optional_string(payload, "package_name") or repository.split("/", 1)[1]
            release = str(acquisition.metadata["commit_sha"])
            source_uri = f"github:{repository}@{release}"
            if analysis_mode == "python":
                analyzer = PythonSyntaxAnalyzer()
                bundle = analyzer.analyze(
                    source,
                    package_name=package_name,
                    release=release,
                    source_kind="github_commit_archive",
                    source_uri=source_uri,
                )
                registry = analyzer.registry
            else:
                inventory = PolyglotInventoryAnalyzer()
                bundle = inventory.analyze(
                    source,
                    package_name=package_name,
                    release=release,
                    source_uri=source_uri,
                )
                registry = None
            attach_acquisition_receipt(bundle, acquisition, artifact.path)
            store = self._graph_store(leased, payload)
            epoch_id = store.write_candidate(bundle, registry)
            published = bool(payload.get("publish", True))
            if published:
                store.publish_epoch(epoch_id)
            receipt = {
                "format_version": "1.0.0",
                "operation": "ingest_github_commit",
                "graph": str(payload.get("graph") or "default"),
                "tenant_id": leased.tenant_id,
                "job_id": leased.job.identity.id,
                "analysis": analysis_mode,
                "acquisition": acquisition.to_dict(),
                "epoch_id": epoch_id,
                "published": published,
                "summary": bundle.summary(),
                "completed_at": utc_now(),
            }
            receipt_ref = self.control.put_job_payload(leased.tenant_id, receipt)
        return (epoch_id, receipt_ref, acquisition.artifact_digest), {
            "artifact_bytes": acquisition.artifact_size_bytes,
            "files": len(bundle.files),
            "entities": len(bundle.entities),
            "relations": len(bundle.relations),
        }

    def _analyze_python_path(
        self, leased: LeasedJob, payload: Mapping[str, Any]
    ) -> tuple[tuple[str, ...], Mapping[str, Any]]:
        source = self._source_path(payload)
        analyzer = PythonSyntaxAnalyzer()
        bundle = analyzer.analyze(
            source,
            package_name=self._optional_string(payload, "package_name"),
            release=self._optional_string(payload, "release"),
        )
        store = self._graph_store(leased, payload)
        epoch_id = store.write_candidate(bundle, analyzer.registry)
        published = bool(payload.get("publish", True))
        if published:
            store.publish_epoch(epoch_id)
        receipt = {
            "format_version": "1.0.0",
            "operation": "analyze_python_path",
            "graph": str(payload.get("graph") or "default"),
            "tenant_id": leased.tenant_id,
            "job_id": leased.job.identity.id,
            "source_relative_path": str(source.relative_to(self.source_root)),
            "epoch_id": epoch_id,
            "published": published,
            "summary": bundle.summary(),
            "completed_at": utc_now(),
        }
        receipt_ref = self.control.put_job_payload(leased.tenant_id, receipt)
        return (epoch_id, receipt_ref), {
            "files": len(bundle.files),
            "entities": len(bundle.entities),
            "relations": len(bundle.relations),
        }

    def _inventory_source_path(
        self, leased: LeasedJob, payload: Mapping[str, Any]
    ) -> tuple[tuple[str, ...], Mapping[str, Any]]:
        source = self._source_path(payload)
        analyzer = PolyglotInventoryAnalyzer()
        bundle = analyzer.analyze(
            source,
            package_name=self._optional_string(payload, "package_name"),
            release=self._optional_string(payload, "release"),
            source_uri=self._optional_string(payload, "source_uri"),
        )
        store = self._graph_store(leased, payload)
        epoch_id = store.write_candidate(bundle)
        published = bool(payload.get("publish", True))
        if published:
            store.publish_epoch(epoch_id)
        receipt = {
            "format_version": "1.0.0",
            "operation": "inventory_source_path",
            "graph": str(payload.get("graph") or "default"),
            "tenant_id": leased.tenant_id,
            "job_id": leased.job.identity.id,
            "source_relative_path": str(source.relative_to(self.source_root)),
            "epoch_id": epoch_id,
            "published": published,
            "summary": bundle.summary(),
            "completed_at": utc_now(),
        }
        receipt_ref = self.control.put_job_payload(leased.tenant_id, receipt)
        return (epoch_id, receipt_ref), {
            "files": len(bundle.files),
            "entities": len(bundle.entities),
            "relations": len(bundle.relations),
        }

    def _source_path(self, payload: Mapping[str, Any]) -> Path:
        value = payload.get("relative_path")
        if not isinstance(value, str) or not value or "\x00" in value:
            raise JobRunnerError("source job requires a relative_path string")
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise JobRunnerError("source path must stay beneath the configured source root")
        source = (self.source_root / relative).resolve()
        if not source.is_relative_to(self.source_root):
            raise JobRunnerError("source path escaped the configured source root")
        if not source.is_dir():
            raise JobRunnerError(f"source path is not a directory: {value}")
        return source

    def _graph_store(self, leased: LeasedJob, payload: Mapping[str, Any]) -> GraphStore:
        name = str(payload.get("graph") or "default")
        if not name or len(name) > 63:
            raise JobRunnerError("graph mount name is invalid")
        return GraphStore(self.control.graph_mount(leased.tenant_id, name).store_root)

    @staticmethod
    def _optional_string(payload: Mapping[str, Any], name: str) -> str | None:
        value = payload.get(name)
        if value is None:
            return None
        if not isinstance(value, str) or not value:
            raise JobRunnerError(f"{name} must be a non-empty string when supplied")
        return value

    @staticmethod
    def _required_string(payload: Mapping[str, Any], name: str) -> str:
        value = JobRunner._optional_string(payload, name)
        if value is None:
            raise JobRunnerError(f"{name} is required")
        return value

    @staticmethod
    def _format_time(value: datetime) -> str:
        return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")
