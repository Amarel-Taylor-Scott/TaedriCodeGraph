"""Budgeted, evidence-producing materialization plans for description portfolios.

The logical schema is open ended; physical generation is deliberately selective.
This module decides *which registered variant to compute next* without treating a
parent package's stated purpose as a ceiling on the usefulness of one function,
method, class, relation, or other subject.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Any, Iterable, Mapping

from .contracts import EvidenceLevel, Modality, SubjectRef, TypedValue, ValueKind
from .representations import RepresentationSeed

PPM = 1_000_000


def _validate_ppm(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= PPM:
        raise ValueError(f"{name} must be an integer within [0, 1000000]")


class MaterializationState(str, Enum):
    PRESENT = "present"
    NOT_COMPUTED = "not_computed"
    QUEUED = "queued"
    STALE = "stale"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"
    WITHHELD = "withheld"
    REDACTED = "redacted"
    CONTRADICTORY = "contradictory"
    SUPERSEDED = "superseded"
    TOMBSTONED = "tombstoned"


class EnrichmentDepth(IntEnum):
    """Materialization depth, intentionally distinct from D0-D6 disclosure."""

    EXACT = 0
    LEXICAL = 1
    STRUCTURAL = 2
    CONTRACT = 3
    SEMANTIC = 4
    BEHAVIORAL = 5
    VERIFICATION = 6


class DecisionAction(str, Enum):
    RETAIN = "retain"
    QUEUE = "queue"
    DEFER = "defer"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ResourceCost:
    storage_bytes: int = 0
    latency_ms: int = 0
    compute_microunits: int = 0
    model_tokens: int = 0
    money_microunits: int = 0

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in self.as_tuple()
        ):
            raise ValueError("resource costs must be non-negative integers")

    def as_tuple(self) -> tuple[int, int, int, int, int]:
        return (
            self.storage_bytes,
            self.latency_ms,
            self.compute_microunits,
            self.model_tokens,
            self.money_microunits,
        )

    def add(self, other: "ResourceCost") -> "ResourceCost":
        return ResourceCost(
            *(
                left + right
                for left, right in zip(
                    self.as_tuple(), other.as_tuple(), strict=True
                )
            )
        )

    def fits_within(self, budget: "ResourceCost") -> bool:
        return all(
            value <= ceiling
            for value, ceiling in zip(self.as_tuple(), budget.as_tuple(), strict=True)
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "storage_bytes": self.storage_bytes,
            "latency_ms": self.latency_ms,
            "compute_microunits": self.compute_microunits,
            "model_tokens": self.model_tokens,
            "money_microunits": self.money_microunits,
        }


@dataclass(frozen=True, slots=True)
class PortfolioDemand:
    """Subject-local demand signals; none is inherited from package purpose."""

    subject: SubjectRef
    query_demand_ppm: int
    candidate_confusion_ppm: int
    reuse_potential_ppm: int
    graph_centrality_ppm: int
    evidence_gap_ppm: int
    freshness_pressure_ppm: int = 0

    def __post_init__(self) -> None:
        for name in (
            "query_demand_ppm",
            "candidate_confusion_ppm",
            "reuse_potential_ppm",
            "graph_centrality_ppm",
            "evidence_gap_ppm",
            "freshness_pressure_ppm",
        ):
            _validate_ppm(name, getattr(self, name))

    @property
    def need_ppm(self) -> int:
        weighted = (
            self.query_demand_ppm * 25
            + self.candidate_confusion_ppm * 30
            + self.reuse_potential_ppm * 15
            + self.graph_centrality_ppm * 10
            + self.evidence_gap_ppm * 15
            + self.freshness_pressure_ppm * 5
        )
        return weighted // 100

    @property
    def recommended_depth(self) -> EnrichmentDepth:
        need = self.need_ppm
        thresholds = (100_000, 225_000, 375_000, 550_000, 725_000, 875_000)
        return EnrichmentDepth(sum(need >= threshold for threshold in thresholds))


@dataclass(frozen=True, slots=True)
class MaterializationArm:
    descriptor_key: str
    descriptor_version: str
    depth: EnrichmentDepth
    expected_marginal_utility_ppm: int
    redundancy_ppm: int
    cost: ResourceCost
    prerequisites: tuple[str, ...] = ()
    baseline: bool = False
    arm_key: str | None = None

    def __post_init__(self) -> None:
        if "." not in self.descriptor_key or not self.descriptor_version:
            raise ValueError("materialization arms require namespaced keys and versions")
        _validate_ppm("expected_marginal_utility_ppm", self.expected_marginal_utility_ppm)
        _validate_ppm("redundancy_ppm", self.redundancy_ppm)
        if self.identity_key in self.prerequisites:
            raise ValueError("a materialization arm cannot depend on itself")

    @property
    def identity_key(self) -> str:
        """Policy-local recipe identity; several arms may share one descriptor."""

        return self.arm_key or self.descriptor_key


@dataclass(frozen=True, slots=True)
class PortfolioPolicy:
    policy_key: str
    policy_version: str
    minimum_priority_ppm: int = 125_000
    baseline_need_floor_ppm: int = 350_000

    def __post_init__(self) -> None:
        if "." not in self.policy_key or not self.policy_version:
            raise ValueError("portfolio policy requires a namespaced key and version")
        _validate_ppm("minimum_priority_ppm", self.minimum_priority_ppm)
        _validate_ppm("baseline_need_floor_ppm", self.baseline_need_floor_ppm)


@dataclass(frozen=True, slots=True)
class MaterializationDecision:
    arm_key: str
    descriptor_key: str
    descriptor_version: str
    depth: EnrichmentDepth
    action: DecisionAction
    prior_state: MaterializationState
    need_ppm: int
    marginal_benefit_ppm: int
    priority_ppm: int
    reason: str
    cost: ResourceCost

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm_key": self.arm_key,
            "descriptor_key": self.descriptor_key,
            "descriptor_version": self.descriptor_version,
            "depth": {"level": int(self.depth), "name": self.depth.name.lower()},
            "action": self.action.value,
            "prior_state": self.prior_state.value,
            "need_ppm": self.need_ppm,
            "marginal_benefit_ppm": self.marginal_benefit_ppm,
            "priority_ppm": self.priority_ppm,
            "reason": self.reason,
            "cost": self.cost.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class PortfolioPlan:
    subject: SubjectRef
    policy_key: str
    policy_version: str
    need_ppm: int
    recommended_depth: EnrichmentDepth
    budget: ResourceCost
    budget_used: ResourceCost
    decisions: tuple[MaterializationDecision, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject.to_dict(),
            "policy_key": self.policy_key,
            "policy_version": self.policy_version,
            "need_ppm": self.need_ppm,
            "recommended_depth": {
                "level": int(self.recommended_depth),
                "name": self.recommended_depth.name.lower(),
            },
            "budget": self.budget.to_dict(),
            "budget_used": self.budget_used.to_dict(),
            "decisions": [decision.to_dict() for decision in self.decisions],
        }


_BLOCKED_STATES = {
    MaterializationState.UNSUPPORTED,
    MaterializationState.NOT_APPLICABLE,
    MaterializationState.WITHHELD,
    MaterializationState.TOMBSTONED,
}
_RETAINED_STATES = {
    MaterializationState.PRESENT,
    MaterializationState.QUEUED,
    MaterializationState.REDACTED,
    MaterializationState.CONTRADICTORY,
}


def _score_arm(
    arm: MaterializationArm,
    demand: PortfolioDemand,
    budget: ResourceCost,
    policy: PortfolioPolicy,
) -> tuple[int, int]:
    need = (
        max(demand.need_ppm, policy.baseline_need_floor_ppm)
        if arm.baseline
        else demand.need_ppm
    )
    marginal = arm.expected_marginal_utility_ppm * need // PPM
    marginal = marginal * (PPM - arm.redundancy_ppm) // PPM
    active_ratios: list[int] = []
    for cost, ceiling in zip(arm.cost.as_tuple(), budget.as_tuple(), strict=True):
        if cost == 0:
            continue
        active_ratios.append(PPM * cost // ceiling if ceiling else PPM * 10)
    cost_pressure = sum(active_ratios) // len(active_ratios) if active_ratios else 0
    priority = min(PPM, marginal * PPM // (250_000 + cost_pressure))
    return marginal, priority


def plan_portfolio_materialization(
    demand: PortfolioDemand,
    arms: Iterable[MaterializationArm],
    *,
    budget: ResourceCost,
    policy: PortfolioPolicy,
    existing_states: Mapping[str, MaterializationState] | None = None,
) -> PortfolioPlan:
    """Greedily queue marginally useful variants under explicit resource budgets.

    The plan is deterministic and auditable.  It never deletes variants, silently
    coerces missing states, or infers an entity's usefulness from package purpose.
    """

    states = dict(existing_states or {})
    arm_list = tuple(arms)
    if len({arm.identity_key for arm in arm_list}) != len(arm_list):
        raise ValueError("materialization arm identities must be unique within a plan")

    scored: dict[str, tuple[MaterializationArm, int, int]] = {}
    final: dict[str, MaterializationDecision] = {}
    for arm in arm_list:
        state = states.get(arm.identity_key, MaterializationState.NOT_COMPUTED)
        marginal, priority = _score_arm(arm, demand, budget, policy)
        common = dict(
            arm_key=arm.identity_key,
            descriptor_key=arm.descriptor_key,
            descriptor_version=arm.descriptor_version,
            depth=arm.depth,
            prior_state=state,
            need_ppm=demand.need_ppm,
            marginal_benefit_ppm=marginal,
            priority_ppm=priority,
            cost=arm.cost,
        )
        if state in _BLOCKED_STATES:
            final[arm.identity_key] = MaterializationDecision(
                action=DecisionAction.BLOCKED,
                reason=f"explicit materialization state is {state.value}",
                **common,
            )
        elif state in _RETAINED_STATES:
            final[arm.identity_key] = MaterializationDecision(
                action=DecisionAction.RETAIN,
                reason=f"existing materialization state is {state.value}",
                **common,
            )
        elif not arm.baseline and arm.depth > demand.recommended_depth:
            final[arm.identity_key] = MaterializationDecision(
                action=DecisionAction.DEFER,
                reason="depth exceeds current subject-local differentiation need",
                **common,
            )
        elif not arm.cost.fits_within(budget):
            final[arm.identity_key] = MaterializationDecision(
                action=DecisionAction.DEFER,
                reason="explicit resource budget exhausted",
                **common,
            )
        elif not arm.baseline and priority < policy.minimum_priority_ppm:
            final[arm.identity_key] = MaterializationDecision(
                action=DecisionAction.DEFER,
                reason="measured marginal utility does not clear policy threshold",
                **common,
            )
        else:
            scored[arm.identity_key] = (arm, marginal, priority)

    used = ResourceCost()
    queued: set[str] = {
        key
        for key, state in states.items()
        if state in {MaterializationState.PRESENT, MaterializationState.QUEUED}
    }
    pending = sorted(
        scored.values(),
        key=lambda item: (
            not item[0].baseline,
            -item[2],
            int(item[0].depth),
            item[0].identity_key,
        ),
    )
    while pending:
        progressed = False
        next_pending: list[tuple[MaterializationArm, int, int]] = []
        for arm, marginal, priority in pending:
            unresolved = tuple(key for key in arm.prerequisites if key not in queued)
            if unresolved and any(key in scored for key in unresolved):
                next_pending.append((arm, marginal, priority))
                continue
            common = dict(
                arm_key=arm.identity_key,
                descriptor_key=arm.descriptor_key,
                descriptor_version=arm.descriptor_version,
                depth=arm.depth,
                prior_state=states.get(arm.identity_key, MaterializationState.NOT_COMPUTED),
                need_ppm=demand.need_ppm,
                marginal_benefit_ppm=marginal,
                priority_ppm=priority,
                cost=arm.cost,
            )
            if unresolved:
                final[arm.identity_key] = MaterializationDecision(
                    action=DecisionAction.DEFER,
                    reason="missing prerequisite variants: " + ", ".join(unresolved),
                    **common,
                )
            else:
                candidate_used = used.add(arm.cost)
                if candidate_used.fits_within(budget):
                    used = candidate_used
                    queued.add(arm.identity_key)
                    final[arm.identity_key] = MaterializationDecision(
                        action=DecisionAction.QUEUE,
                        reason=(
                            "baseline portfolio requirement"
                            if arm.baseline
                            else "marginal utility clears depth, redundancy, and budget gates"
                        ),
                        **common,
                    )
                else:
                    final[arm.identity_key] = MaterializationDecision(
                        action=DecisionAction.DEFER,
                        reason="explicit resource budget exhausted",
                        **common,
                    )
            progressed = True
        if not progressed:
            for arm, marginal, priority in next_pending:
                final[arm.identity_key] = MaterializationDecision(
                    arm_key=arm.identity_key,
                    descriptor_key=arm.descriptor_key,
                    descriptor_version=arm.descriptor_version,
                    depth=arm.depth,
                    action=DecisionAction.DEFER,
                    prior_state=states.get(
                        arm.identity_key, MaterializationState.NOT_COMPUTED
                    ),
                    need_ppm=demand.need_ppm,
                    marginal_benefit_ppm=marginal,
                    priority_ppm=priority,
                    reason="cyclic or unresolved materialization prerequisites",
                    cost=arm.cost,
                )
            break
        pending = next_pending

    ordered = tuple(final[arm.identity_key] for arm in arm_list)
    return PortfolioPlan(
        demand.subject,
        policy.policy_key,
        policy.policy_version,
        demand.need_ppm,
        demand.recommended_depth,
        budget,
        used,
        ordered,
    )


def materialization_state_seed(
    subject: SubjectRef,
    *,
    descriptor_key: str,
    descriptor_version: str,
    state: MaterializationState,
    reason: str,
    policy_key: str,
    policy_version: str,
    arm_key: str | None = None,
) -> RepresentationSeed:
    """Encode one explicit state row without overloading absence or empty values."""

    return RepresentationSeed(
        subject,
        "uceg.family.portfolio",
        "uceg.portfolio.materialization_state",
        TypedValue(
            ValueKind.JSON,
            {
                "descriptor_key": descriptor_key,
                "descriptor_version": descriptor_version,
                "arm_key": arm_key or descriptor_key,
                "state": state.value,
                "reason": reason,
                "policy_key": policy_key,
                "policy_version": policy_version,
            },
        ),
        modality=Modality.ASSERTED,
        lifecycle=EvidenceLevel.STRUCTURED,
    )


def materialization_plan_seed(plan: PortfolioPlan) -> RepresentationSeed:
    """Persist the full selector receipt as a versioned representation."""

    return RepresentationSeed(
        plan.subject,
        "uceg.family.portfolio",
        "uceg.portfolio.materialization_plan",
        TypedValue(ValueKind.JSON, plan.to_dict()),
        modality=Modality.ASSERTED,
        lifecycle=EvidenceLevel.CANDIDATE,
    )
