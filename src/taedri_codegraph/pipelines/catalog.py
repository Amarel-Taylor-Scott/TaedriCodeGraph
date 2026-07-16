"""Immutable catalogs containing executable operations only.

Future gates belong in architecture decisions and readiness manifests until an
acceptance path exists.  They are deliberately absent from worker routing so a
catalog entry can never be mistaken for an implemented capability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from ..canonical import canonical_digest
from ..contracts import RecordMixin
from ..workers import JobKind

_KEY = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)+$")
_OPERATION = re.compile(r"^[a-z][a-z0-9_]+$")


class ExecutionState(str, Enum):
    WORKING = "working"
    CONTRACT = "contract"
    PLANNED = "planned"


class StageMode(str, Enum):
    SEQUENTIAL = "sequential"
    WATERFALL = "waterfall"
    FAN_OUT = "fan_out"
    GATE = "gate"


@dataclass(frozen=True, slots=True)
class ConditionalCapability(RecordMixin):
    payload_field: str
    value_capabilities: Mapping[str, tuple[str, ...]]
    default_value: str

    def __post_init__(self) -> None:
        if not self.payload_field or not self.value_capabilities:
            raise ValueError("conditional capability requires a field and mappings")
        normalized = {
            key: tuple(sorted(set(values)))
            for key, values in sorted(self.value_capabilities.items())
        }
        if self.default_value not in normalized:
            raise ValueError("conditional capability default must be mapped")
        if any(not key or not values or any(not item for item in values) for key, values in normalized.items()):
            raise ValueError("conditional capability values cannot be empty")
        object.__setattr__(self, "value_capabilities", normalized)

    def resolve(self, payload: Mapping[str, Any]) -> tuple[str, ...]:
        value = str(payload.get(self.payload_field) or self.default_value)
        try:
            return self.value_capabilities[value]
        except KeyError as exc:
            choices = ", ".join(sorted(self.value_capabilities))
            raise ValueError(
                f"{self.payload_field} must be one of: {choices}"
            ) from exc


@dataclass(frozen=True, slots=True)
class OperationContract(RecordMixin):
    operation: str
    version: str
    pipeline_key: str
    allowed_kinds: tuple[JobKind, ...]
    required_capabilities: tuple[str, ...]
    execution_state: ExecutionState
    network_access: bool
    source_execution_allowed: bool
    output_components: tuple[str, ...]
    conditional_capabilities: tuple[ConditionalCapability, ...] = ()

    def __post_init__(self) -> None:
        if not _OPERATION.fullmatch(self.operation):
            raise ValueError("operation name is invalid")
        if not _KEY.fullmatch(self.pipeline_key) or not self.version:
            raise ValueError("operation pipeline key and version are required")
        kinds = tuple(sorted(set(self.allowed_kinds), key=lambda item: item.value))
        capabilities = tuple(sorted(set(self.required_capabilities)))
        outputs = tuple(sorted(set(self.output_components)))
        if not kinds or not outputs or any(not item for item in capabilities + outputs):
            raise ValueError("operation kinds, capabilities, and outputs must be explicit")
        object.__setattr__(self, "allowed_kinds", kinds)
        object.__setattr__(self, "required_capabilities", capabilities)
        object.__setattr__(self, "output_components", outputs)

    @property
    def ref(self) -> str:
        return f"{self.operation}@{self.version}"

    def capabilities_for(self, payload: Mapping[str, Any]) -> tuple[str, ...]:
        values = set(self.required_capabilities)
        for conditional in self.conditional_capabilities:
            values.update(conditional.resolve(payload))
        return tuple(sorted(values))


@dataclass(frozen=True, slots=True)
class PipelineStage(RecordMixin):
    key: str
    ordinal: int
    mode: StageMode
    execution_state: ExecutionState
    operation_refs: tuple[str, ...]
    consumes: tuple[str, ...]
    produces: tuple[str, ...]
    failure_policy: str
    optional: bool = False

    def __post_init__(self) -> None:
        if not _KEY.fullmatch(self.key) or self.ordinal <= 0:
            raise ValueError("pipeline stage key and positive ordinal are required")
        if self.failure_policy not in {"fail_closed", "continue", "abstain", "quarantine"}:
            raise ValueError("pipeline stage failure policy is invalid")
        if not self.produces:
            raise ValueError("pipeline stage outputs must be explicit")


@dataclass(frozen=True, slots=True)
class PipelineDefinition(RecordMixin):
    key: str
    version: str
    purpose: str
    trigger_sources: tuple[str, ...]
    stages: tuple[PipelineStage, ...]
    tenant_isolated: bool = True

    def __post_init__(self) -> None:
        if not _KEY.fullmatch(self.key) or not self.version or not self.purpose:
            raise ValueError("pipeline identity, version, and purpose are required")
        ordinals = [stage.ordinal for stage in self.stages]
        if not self.stages or ordinals != sorted(ordinals) or len(ordinals) != len(set(ordinals)):
            raise ValueError("pipeline stages must have unique increasing ordinals")
        if not self.trigger_sources:
            raise ValueError("pipeline triggers must be explicit")

    @property
    def digest(self) -> str:
        return canonical_digest(self)


class PipelineCatalog:
    """Add-only pipeline and executable-operation registry."""

    def __init__(self) -> None:
        self._pipelines: dict[str, PipelineDefinition] = {}
        self._operations: dict[str, OperationContract] = {}

    def register_pipeline(self, definition: PipelineDefinition) -> PipelineDefinition:
        ref = f"{definition.key}@{definition.version}"
        if ref in self._pipelines:
            raise ValueError(f"pipeline is already registered: {ref}")
        self._pipelines[ref] = definition
        return definition

    def register_operation(self, contract: OperationContract) -> OperationContract:
        if contract.operation in self._operations:
            raise ValueError(f"operation is already registered: {contract.operation}")
        pipeline_ref = f"{contract.pipeline_key}@{contract.version}"
        if pipeline_ref not in self._pipelines:
            raise ValueError(f"operation references an unknown pipeline: {pipeline_ref}")
        self._operations[contract.operation] = contract
        return contract

    def operation(self, name: object) -> OperationContract:
        if not isinstance(name, str):
            raise ValueError("operation must be a string")
        try:
            return self._operations[name]
        except KeyError as exc:
            raise ValueError(f"unsupported worker operation: {name!r}") from exc

    def validate_operation(
        self,
        name: object,
        *,
        kind: JobKind,
        supplied_capabilities: Iterable[str],
        payload: Mapping[str, Any],
    ) -> OperationContract:
        contract = self.operation(name)
        if contract.execution_state is not ExecutionState.WORKING:
            raise ValueError(f"worker operation is not executable: {contract.operation}")
        if kind not in contract.allowed_kinds:
            raise ValueError("job kind does not match its operation")
        required = set(contract.capabilities_for(payload))
        missing = sorted(required - set(supplied_capabilities))
        if missing:
            raise ValueError("required_capabilities must include: " + ", ".join(missing))
        return contract

    def pipelines(self) -> tuple[PipelineDefinition, ...]:
        return tuple(self._pipelines[key] for key in sorted(self._pipelines))

    def operations(self) -> tuple[OperationContract, ...]:
        return tuple(self._operations[key] for key in sorted(self._operations))

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "pipelines": self.pipelines(),
                "operations": self.operations(),
            }
        )


def _stage(
    key: str,
    ordinal: int,
    mode: StageMode,
    state: ExecutionState,
    operations: tuple[str, ...],
    consumes: tuple[str, ...],
    produces: tuple[str, ...],
    failure: str,
    optional: bool = False,
) -> PipelineStage:
    return PipelineStage(
        key, ordinal, mode, state, operations, consumes, produces, failure, optional
    )


def platform_pipeline_catalog() -> PipelineCatalog:
    """Return the frozen v1 catalog used by API admission and worker execution."""

    catalog = PipelineCatalog()
    pipelines = (
        PipelineDefinition(
            "taedri.pipeline.source_to_graph",
            "1.0.0",
            "Safely extract an immutable graph epoch from operator-mounted source.",
            ("api_job", "cli", "scheduled_refresh"),
            (
                _stage("taedri.stage.acquire", 1, StageMode.WATERFALL, ExecutionState.WORKING, ("analyze_python_path@1.0.0", "inventory_source_path@1.0.0"), ("mounted_source_ref",), ("bounded_source_inventory",), "fail_closed"),
                _stage("taedri.stage.extract", 2, StageMode.SEQUENTIAL, ExecutionState.WORKING, ("analyze_python_path@1.0.0", "inventory_source_path@1.0.0"), ("bounded_source_inventory",), ("exact_facts", "relations", "descriptor_variants"), "quarantine"),
                _stage("taedri.stage.project", 3, StageMode.FAN_OUT, ExecutionState.WORKING, ("analyze_python_path@1.0.0", "inventory_source_path@1.0.0"), ("exact_facts",), ("sparse_index", "fingerprint_index", "graph_index"), "continue"),
                _stage("taedri.stage.publish", 4, StageMode.GATE, ExecutionState.WORKING, ("analyze_python_path@1.0.0", "inventory_source_path@1.0.0"), ("validated_epoch",), ("atomic_graph_epoch", "run_receipt"), "fail_closed"),
            ),
        ),
        PipelineDefinition(
            "taedri.pipeline.remote_to_graph",
            "1.0.0",
            "Acquire immutable public artifacts and publish safely extracted graph epochs.",
            ("api_job", "registry_poll", "verified_webhook", "operator_import"),
            (
                _stage("taedri.stage.remote_acquire", 1, StageMode.WATERFALL, ExecutionState.WORKING, ("ingest_pypi_wheel@1.0.0", "ingest_github_commit@1.0.0"), ("immutable_source_locator",), ("artifact_digest", "acquisition_receipt"), "quarantine"),
                _stage("taedri.stage.safe_extract", 2, StageMode.SEQUENTIAL, ExecutionState.WORKING, ("ingest_pypi_wheel@1.0.0", "ingest_github_commit@1.0.0"), ("verified_artifact",), ("exact_facts", "relations", "descriptor_variants"), "quarantine"),
                _stage("taedri.stage.remote_publish", 3, StageMode.GATE, ExecutionState.WORKING, ("ingest_pypi_wheel@1.0.0", "ingest_github_commit@1.0.0"), ("validated_epoch",), ("atomic_graph_epoch", "run_receipt"), "fail_closed"),
            ),
        ),
        PipelineDefinition(
            "taedri.pipeline.primitive_factory",
            "1.0.0",
            "Generate reviewable primitive candidates without claiming behavioral correctness.",
            ("api_job", "search_gap", "usage_signal", "operator_request"),
            (
                _stage("taedri.stage.candidate_extract", 1, StageMode.SEQUENTIAL, ExecutionState.WORKING, ("generate_primitive_candidates@1.0.0",), ("mounted_source_ref",), ("source_capsule", "contract", "candidate_lineage"), "quarantine"),
                _stage("taedri.stage.candidate_describe", 2, StageMode.WATERFALL, ExecutionState.WORKING, ("generate_primitive_candidates@1.0.0",), ("source_capsule", "contract"), ("lexical_descriptors", "fingerprints", "graph_neighborhood"), "continue"),
            ),
        ),
        PipelineDefinition(
            "taedri.pipeline.primitive_release",
            "1.0.0",
            "Materialize, execute, independently check, authorize, index, and expose one complete primitive capsule.",
            ("registry_stage", "operator_release"),
            (
                _stage("taedri.stage.release_validate", 1, StageMode.GATE, ExecutionState.WORKING, ("verify_primitive_release@1.0.0",), ("staged_revision", "policy_decision"), ("artifact_assessment",), "quarantine"),
                _stage("taedri.stage.release_execute", 2, StageMode.SEQUENTIAL, ExecutionState.WORKING, ("verify_primitive_release@1.0.0",), ("artifact_assessment", "examples", "tests", "runtime_lock"), ("acceptance_receipt", "materialization_receipt"), "fail_closed"),
                _stage("taedri.stage.release_publish", 3, StageMode.GATE, ExecutionState.WORKING, ("verify_primitive_release@1.0.0",), ("acceptance_receipt", "authorization"), ("primitive_release", "search_projection", "downloadable_pack"), "fail_closed"),
            ),
        ),
    )
    for definition in pipelines:
        catalog.register_pipeline(definition)

    operations = (
        OperationContract("analyze_python_path", "1.0.0", "taedri.pipeline.source_to_graph", (JobKind.EXTRACT,), ("python-ast",), ExecutionState.WORKING, False, False, ("graph_epoch", "job_receipt")),
        OperationContract("inventory_source_path", "1.0.0", "taedri.pipeline.source_to_graph", (JobKind.EXTRACT, JobKind.INDEX), ("polyglot-inventory",), ExecutionState.WORKING, False, False, ("graph_epoch", "job_receipt")),
        OperationContract("ingest_pypi_wheel", "1.0.0", "taedri.pipeline.remote_to_graph", (JobKind.ACQUIRE,), ("pypi-acquire", "python-ast"), ExecutionState.WORKING, True, False, ("artifact", "graph_epoch", "acquisition_receipt", "job_receipt")),
        OperationContract(
            "ingest_github_commit", "1.0.0", "taedri.pipeline.remote_to_graph", (JobKind.ACQUIRE,), ("github-acquire",), ExecutionState.WORKING, True, False, ("artifact", "graph_epoch", "acquisition_receipt", "job_receipt"),
            (ConditionalCapability("analysis", {"python": ("python-ast",), "inventory": ("polyglot-inventory",)}, "python"),),
        ),
        OperationContract("generate_primitive_candidates", "1.0.0", "taedri.pipeline.primitive_factory", (JobKind.EXTRACT,), ("python-ast", "primitive-factory-v1"), ExecutionState.WORKING, False, False, ("primitive_revisions", "candidate_submissions", "lineage", "job_receipt")),
        OperationContract("verify_primitive_release", "1.0.0", "taedri.pipeline.primitive_release", (JobKind.VERIFY,), ("primitive-release-v1",), ExecutionState.WORKING, False, True, ("primitive_release", "acceptance_receipt", "materialization_receipt", "search_projection", "downloadable_pack", "job_receipt")),
    )
    for contract in operations:
        catalog.register_operation(contract)
    return catalog


def benchmark_pipeline_catalog() -> PipelineCatalog:
    """Catalog only the receipt-validation work that BenchmarkWorker executes today."""

    catalog = PipelineCatalog()
    catalog.register_pipeline(
        PipelineDefinition(
            "taedri.pipeline.matched_benchmark",
            "1.0.0",
            "Freeze matched run specs, validate supplied terminal receipts, and compare evidence without claiming to execute model or sandbox adapters.",
            ("operator_evidence_import", "conformance_bundle"),
            (
                _stage("taedri.stage.freeze_experiment", 1, StageMode.GATE, ExecutionState.WORKING, (), ("task_manifest", "model_config", "policy"), ("frozen_run_specs",), "fail_closed"),
                _stage("taedri.stage.validate_receipts", 2, StageMode.GATE, ExecutionState.WORKING, (), ("frozen_run_specs", "terminal_run_receipts"), ("validated_run_receipts", "contamination_strata"), "fail_closed"),
                _stage("taedri.stage.compare", 3, StageMode.SEQUENTIAL, ExecutionState.WORKING, (), ("validated_run_receipts",), ("matched_metrics", "claim_eligibility", "benchmark_report"), "fail_closed"),
            ),
        )
    )
    return catalog
