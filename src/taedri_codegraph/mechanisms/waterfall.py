"""Deterministic orchestration for extensible, evidence-bearing mechanism waterfalls."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Protocol

from ..canonical import canonical_json_bytes, sha256_digest, to_primitive
from ..contracts import RecordMixin

_KEY = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)+$")
_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+){0,2}(?:[-+][A-Za-z0-9.-]+)?$")


class MechanismMode(str, Enum):
    """How mechanisms inside one ordered stage are evaluated."""

    ALL = "all"
    FIRST_SUCCESS = "first_success"
    UNTIL_CONFIDENCE = "until_confidence"


class FailurePolicy(str, Enum):
    """What a stage does when a mechanism fails or cannot satisfy its minimum."""

    FAIL_CLOSED = "fail_closed"
    CONTINUE = "continue"
    ABSTAIN = "abstain"


class StepStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED_CAPABILITY = "skipped_capability"
    SKIPPED_BUDGET = "skipped_budget"


class RunStatus(str, Enum):
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    ABSTAINED = "abstained"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class MechanismDefinition(RecordMixin):
    key: str
    version: str
    phase: str
    deterministic: bool
    cost_units: int = 1
    required_capabilities: tuple[str, ...] = ()
    output_facets: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _KEY.fullmatch(self.key) or not _KEY.fullmatch(self.phase):
            raise ValueError("mechanism key and phase must be namespaced keys")
        if not _VERSION.fullmatch(self.version):
            raise ValueError("mechanism version is invalid")
        if self.cost_units <= 0:
            raise ValueError("mechanism cost must be positive")
        capabilities = tuple(sorted(set(self.required_capabilities)))
        facets = tuple(sorted(set(self.output_facets)))
        if any(not item for item in capabilities + facets):
            raise ValueError("mechanism capability and facet names cannot be empty")
        object.__setattr__(self, "required_capabilities", capabilities)
        object.__setattr__(self, "output_facets", facets)

    @property
    def ref(self) -> str:
        return f"{self.key}@{self.version}"

    @property
    def digest(self) -> str:
        return _payload_digest(self)


@dataclass(frozen=True, slots=True)
class MechanismResult(RecordMixin):
    output: Mapping[str, Any] = field(default_factory=dict)
    confidence_ppm: int | None = None
    evidence_refs: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        primitive = to_primitive(dict(self.output))
        if not isinstance(primitive, dict):  # pragma: no cover - defensive
            raise TypeError("mechanism output must be a mapping")
        if self.confidence_ppm is not None and not 0 <= self.confidence_ppm <= 1_000_000:
            raise ValueError("confidence must be 0..1,000,000 parts per million")
        if any(not value for value in self.evidence_refs):
            raise ValueError("evidence references cannot be empty")
        object.__setattr__(self, "output", MappingProxyType(primitive))
        object.__setattr__(self, "evidence_refs", tuple(sorted(set(self.evidence_refs))))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


@dataclass(frozen=True, slots=True)
class MechanismInvocation:
    request: Mapping[str, Any]
    prior_outputs: Mapping[str, tuple[Mapping[str, Any], ...]]
    correlation_id: str


class MechanismHandler(Protocol):
    def __call__(self, invocation: MechanismInvocation) -> MechanismResult: ...


@dataclass(frozen=True, slots=True)
class StageDefinition(RecordMixin):
    key: str
    mechanism_refs: tuple[str, ...]
    mode: MechanismMode = MechanismMode.ALL
    failure_policy: FailurePolicy = FailurePolicy.FAIL_CLOSED
    minimum_successes: int = 1
    confidence_threshold_ppm: int | None = None

    def __post_init__(self) -> None:
        if not _KEY.fullmatch(self.key):
            raise ValueError("stage key must be namespaced")
        if not self.mechanism_refs or len(set(self.mechanism_refs)) != len(
            self.mechanism_refs
        ):
            raise ValueError("stage mechanism references must be non-empty and unique")
        if not 0 <= self.minimum_successes <= len(self.mechanism_refs):
            raise ValueError("stage minimum successes is invalid")
        if self.mode is MechanismMode.UNTIL_CONFIDENCE:
            if self.confidence_threshold_ppm is None:
                raise ValueError("confidence mode requires a threshold")
        if self.confidence_threshold_ppm is not None and not (
            0 <= self.confidence_threshold_ppm <= 1_000_000
        ):
            raise ValueError("stage confidence threshold is invalid")


@dataclass(frozen=True, slots=True)
class WaterfallPlan(RecordMixin):
    key: str
    version: str
    stages: tuple[StageDefinition, ...]

    def __post_init__(self) -> None:
        if not _KEY.fullmatch(self.key) or not _VERSION.fullmatch(self.version):
            raise ValueError("waterfall plan key or version is invalid")
        if not self.stages or len({stage.key for stage in self.stages}) != len(self.stages):
            raise ValueError("waterfall stages must be non-empty and uniquely named")

    @property
    def digest(self) -> str:
        return _payload_digest(self)


@dataclass(frozen=True, slots=True)
class MechanismBudget(RecordMixin):
    maximum_steps: int = 64
    maximum_cost_units: int = 256

    def __post_init__(self) -> None:
        if self.maximum_steps <= 0 or self.maximum_cost_units <= 0:
            raise ValueError("mechanism budgets must be positive")


@dataclass(frozen=True, slots=True)
class StepReceipt(RecordMixin):
    sequence: int
    stage_key: str
    mechanism_ref: str
    definition_digest: str
    status: StepStatus
    request_digest: str
    output_digest: str | None
    confidence_ppm: int | None
    evidence_refs: tuple[str, ...]
    error_code: str | None
    cost_units: int
    duration_ms: int
    started_at: str
    finished_at: str


@dataclass(frozen=True, slots=True)
class WaterfallRun(RecordMixin):
    run_id: str
    plan_key: str
    plan_version: str
    plan_digest: str
    request_digest: str
    correlation_id: str
    status: RunStatus
    outputs: Mapping[str, tuple[Mapping[str, Any], ...]]
    receipts: tuple[StepReceipt, ...]
    consumed_cost_units: int
    stop_reason: str


class MechanismRegistry:
    """Additive registry; one mechanism reference can never be silently replaced."""

    def __init__(self) -> None:
        self._items: dict[str, tuple[MechanismDefinition, MechanismHandler]] = {}

    def register(
        self, definition: MechanismDefinition, handler: MechanismHandler
    ) -> None:
        if definition.ref in self._items:
            raise ValueError(f"mechanism already registered: {definition.ref}")
        self._items[definition.ref] = (definition, handler)

    def resolve(self, reference: str) -> tuple[MechanismDefinition, MechanismHandler]:
        try:
            return self._items[reference]
        except KeyError as exc:
            raise LookupError(f"unknown mechanism: {reference}") from exc

    def definitions(self) -> tuple[MechanismDefinition, ...]:
        return tuple(self._items[key][0] for key in sorted(self._items))


class WaterfallExecutor:
    """Executes a frozen plan while retaining every attempt and explicit abstention."""

    def __init__(
        self,
        registry: MechanismRegistry,
        *,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.registry = registry
        self.clock = clock or _utc_now

    def execute(
        self,
        plan: WaterfallPlan,
        request: Mapping[str, Any],
        *,
        capabilities: Iterable[str] = (),
        budget: MechanismBudget | None = None,
        correlation_id: str = "",
    ) -> WaterfallRun:
        effective_budget = budget or MechanismBudget()
        available = frozenset(capabilities)
        request_value = to_primitive(dict(request))
        if not isinstance(request_value, dict):  # pragma: no cover - defensive
            raise TypeError("waterfall request must be a mapping")
        request_digest = _payload_digest(request_value)
        outputs: dict[str, list[Mapping[str, Any]]] = {}
        receipts: list[StepReceipt] = []
        consumed = 0
        any_success = False
        terminal_status: RunStatus | None = None
        stop_reason = "plan_complete"

        for stage in plan.stages:
            successes = 0
            for reference in stage.mechanism_refs:
                definition, handler = self.registry.resolve(reference)
                if definition.phase != stage.key:
                    raise ValueError(
                        f"mechanism {reference} belongs to {definition.phase}, not {stage.key}"
                    )
                sequence = len(receipts) + 1
                started_at = self.clock()
                start_ns = time.monotonic_ns()
                missing = set(definition.required_capabilities) - available
                if missing:
                    receipts.append(
                        self._receipt(
                            sequence,
                            stage,
                            definition,
                            StepStatus.SKIPPED_CAPABILITY,
                            request_digest,
                            started_at,
                            start_ns,
                            error_code="missing_capability",
                        )
                    )
                    continue
                if (
                    len(receipts) >= effective_budget.maximum_steps
                    or consumed + definition.cost_units
                    > effective_budget.maximum_cost_units
                ):
                    receipts.append(
                        self._receipt(
                            sequence,
                            stage,
                            definition,
                            StepStatus.SKIPPED_BUDGET,
                            request_digest,
                            started_at,
                            start_ns,
                            error_code="budget_exhausted",
                        )
                    )
                    if stage.failure_policy is FailurePolicy.FAIL_CLOSED:
                        terminal_status = RunStatus.FAILED
                        stop_reason = "budget_exhausted"
                        break
                    if stage.failure_policy is FailurePolicy.ABSTAIN:
                        terminal_status = RunStatus.ABSTAINED
                        stop_reason = "budget_exhausted"
                        break
                    continue
                consumed += definition.cost_units
                try:
                    result = handler(
                        MechanismInvocation(
                            MappingProxyType(request_value),
                            MappingProxyType(
                                {key: tuple(values) for key, values in outputs.items()}
                            ),
                            correlation_id,
                        )
                    )
                except Exception as exc:
                    receipts.append(
                        self._receipt(
                            sequence,
                            stage,
                            definition,
                            StepStatus.FAILED,
                            request_digest,
                            started_at,
                            start_ns,
                            error_code=type(exc).__name__,
                            cost_units=definition.cost_units,
                        )
                    )
                    if stage.failure_policy is FailurePolicy.FAIL_CLOSED:
                        terminal_status = RunStatus.FAILED
                        stop_reason = f"mechanism_failed:{reference}"
                        break
                    if stage.failure_policy is FailurePolicy.ABSTAIN:
                        terminal_status = RunStatus.ABSTAINED
                        stop_reason = f"mechanism_failed:{reference}"
                        break
                    continue
                primitive_output = to_primitive(dict(result.output))
                outputs.setdefault(reference, []).append(MappingProxyType(primitive_output))
                receipts.append(
                    self._receipt(
                        sequence,
                        stage,
                        definition,
                        StepStatus.SUCCEEDED,
                        request_digest,
                        started_at,
                        start_ns,
                        output_digest=_payload_digest(primitive_output),
                        confidence_ppm=result.confidence_ppm,
                        evidence_refs=result.evidence_refs,
                        cost_units=definition.cost_units,
                    )
                )
                successes += 1
                any_success = True
                if stage.mode is MechanismMode.FIRST_SUCCESS:
                    break
                if (
                    stage.mode is MechanismMode.UNTIL_CONFIDENCE
                    and result.confidence_ppm is not None
                    and result.confidence_ppm >= (stage.confidence_threshold_ppm or 0)
                ):
                    break
            if terminal_status is not None:
                break
            if successes < stage.minimum_successes:
                if stage.failure_policy is FailurePolicy.FAIL_CLOSED:
                    terminal_status = RunStatus.FAILED
                    stop_reason = f"stage_minimum_not_met:{stage.key}"
                    break
                if stage.failure_policy is FailurePolicy.ABSTAIN:
                    terminal_status = RunStatus.ABSTAINED
                    stop_reason = f"stage_minimum_not_met:{stage.key}"
                    break

        if terminal_status is None:
            skipped_or_failed = any(
                item.status is not StepStatus.SUCCEEDED for item in receipts
            )
            terminal_status = (
                RunStatus.PARTIAL if skipped_or_failed and any_success else RunStatus.SUCCEEDED
            )
        frozen_outputs = MappingProxyType(
            {key: tuple(values) for key, values in sorted(outputs.items())}
        )
        run_key = {
            "plan_digest": plan.digest,
            "request_digest": request_digest,
            "correlation_id": correlation_id,
            "status": terminal_status.value,
            "receipts": [
                {
                    "sequence": item.sequence,
                    "stage_key": item.stage_key,
                    "mechanism_ref": item.mechanism_ref,
                    "status": item.status.value,
                    "output_digest": item.output_digest,
                    "error_code": item.error_code,
                }
                for item in receipts
            ],
        }
        return WaterfallRun(
            "uceg:v1:waterfall_run:" + _payload_digest(run_key).removeprefix("sha256:"),
            plan.key,
            plan.version,
            plan.digest,
            request_digest,
            correlation_id,
            terminal_status,
            frozen_outputs,
            tuple(receipts),
            consumed,
            stop_reason,
        )

    def _receipt(
        self,
        sequence: int,
        stage: StageDefinition,
        definition: MechanismDefinition,
        status: StepStatus,
        request_digest: str,
        started_at: str,
        start_ns: int,
        *,
        output_digest: str | None = None,
        confidence_ppm: int | None = None,
        evidence_refs: tuple[str, ...] = (),
        error_code: str | None = None,
        cost_units: int = 0,
    ) -> StepReceipt:
        return StepReceipt(
            sequence,
            stage.key,
            definition.ref,
            definition.digest,
            status,
            request_digest,
            output_digest,
            confidence_ppm,
            evidence_refs,
            error_code,
            cost_units,
            max(0, (time.monotonic_ns() - start_ns) // 1_000_000),
            started_at,
            self.clock(),
        )


def _payload_digest(value: Any) -> str:
    return sha256_digest(canonical_json_bytes(value))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )
