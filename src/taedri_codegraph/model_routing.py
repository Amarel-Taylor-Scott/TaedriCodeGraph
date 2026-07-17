"""Deterministic policy routing across local and hosted model arms.

This registry is intentionally separate from :mod:`taedri_codegraph.providers`, whose
providers materialize graph representations.  Routing decisions contain model metadata
and gate results only; provider credentials never enter these contracts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .canonical import canonical_json_bytes, sha256_digest
from .contracts import RecordMixin
from .identity import IdentityRecord

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_KEY = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+){0,2}(?:[-+][A-Za-z0-9.-]+)?$")


class ModelRoutingError(ValueError):
    """Raised when model-arm metadata or a requested selection is invalid."""


class ModelTier(str, Enum):
    DETERMINISTIC = "deterministic"
    LOCAL_SLM = "local_slm"
    LOCAL_GENERAL = "local_general"
    HOSTED_SMALL = "hosted_small"
    HOSTED_STRONG = "hosted_strong"
    FRONTIER = "frontier"


class PrivacyMode(str, Enum):
    LOCAL_ONLY = "local_only"
    RESTRICTED = "restricted"
    HOSTED_ALLOWED = "hosted_allowed"


_TIER_ORDER = {
    ModelTier.DETERMINISTIC: 0,
    ModelTier.LOCAL_SLM: 1,
    ModelTier.LOCAL_GENERAL: 2,
    ModelTier.HOSTED_SMALL: 3,
    ModelTier.HOSTED_STRONG: 4,
    ModelTier.FRONTIER: 5,
}


@dataclass(frozen=True, slots=True)
class ModelTaskDemand(RecordMixin):
    task_key: str
    input_digest: str
    required_capabilities: tuple[str, ...]
    privacy_mode: PrivacyMode
    network_allowed: bool
    maximum_cost_microunits: int
    maximum_latency_ms: int | None = None

    def __post_init__(self) -> None:
        if not _KEY.fullmatch(self.task_key):
            raise ModelRoutingError("task key is invalid")
        if not _DIGEST.fullmatch(self.input_digest):
            raise ModelRoutingError("task input must be represented by a sha256 digest")
        if not isinstance(self.privacy_mode, PrivacyMode):
            raise ModelRoutingError("task privacy mode is invalid")
        if not isinstance(self.network_allowed, bool):
            raise ModelRoutingError("task network policy must be Boolean")
        capabilities = tuple(sorted(set(self.required_capabilities)))
        if any(not _KEY.fullmatch(item) for item in capabilities):
            raise ModelRoutingError("task capabilities must be non-empty stable keys")
        if (
            isinstance(self.maximum_cost_microunits, bool)
            or not isinstance(self.maximum_cost_microunits, int)
            or self.maximum_cost_microunits < 0
        ):
            raise ModelRoutingError("task cost budget must be a non-negative integer")
        if self.maximum_latency_ms is not None and (
            isinstance(self.maximum_latency_ms, bool)
            or not isinstance(self.maximum_latency_ms, int)
            or self.maximum_latency_ms <= 0
        ):
            raise ModelRoutingError("task latency budget must be positive when supplied")
        object.__setattr__(self, "required_capabilities", capabilities)


@dataclass(frozen=True, slots=True)
class ModelArm(RecordMixin):
    arm_id: str
    provider_id: str
    model_id: str
    tier: ModelTier
    capabilities: tuple[str, ...]
    privacy_modes: tuple[PrivacyMode, ...]
    network_required: bool
    estimated_cost_microunits: int
    estimated_latency_ms: int
    healthy: bool = True

    def __post_init__(self) -> None:
        if not _KEY.fullmatch(self.arm_id) or not _KEY.fullmatch(self.provider_id):
            raise ModelRoutingError("model arm and provider identifiers are invalid")
        if not self.model_id:
            raise ModelRoutingError("model arm requires a model identifier")
        if not isinstance(self.tier, ModelTier):
            raise ModelRoutingError("model arm tier is invalid")
        if not isinstance(self.network_required, bool) or not isinstance(
            self.healthy, bool
        ):
            raise ModelRoutingError("arm network and health fields must be Boolean")
        capabilities = tuple(sorted(set(self.capabilities)))
        if any(not _KEY.fullmatch(item) for item in capabilities):
            raise ModelRoutingError("arm capabilities must be non-empty stable keys")
        if not self.privacy_modes or any(
            not isinstance(item, PrivacyMode) for item in self.privacy_modes
        ):
            raise ModelRoutingError("model arm requires at least one privacy mode")
        privacy_modes = tuple(
            sorted(set(self.privacy_modes), key=lambda item: item.value)
        )
        if (
            isinstance(self.estimated_cost_microunits, bool)
            or not isinstance(self.estimated_cost_microunits, int)
            or self.estimated_cost_microunits < 0
        ):
            raise ModelRoutingError("arm cost estimate must be a non-negative integer")
        if (
            isinstance(self.estimated_latency_ms, bool)
            or not isinstance(self.estimated_latency_ms, int)
            or self.estimated_latency_ms < 0
        ):
            raise ModelRoutingError("arm latency estimate must be a non-negative integer")
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "privacy_modes", privacy_modes)


@dataclass(frozen=True, slots=True)
class ModelArmEvaluation(RecordMixin):
    arm_id: str
    provider_id: str
    model_id: str
    tier: ModelTier
    eligible: bool
    reason_codes: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    estimated_cost_microunits: int
    estimated_latency_ms: int

    def __post_init__(self) -> None:
        if (
            not _KEY.fullmatch(self.arm_id)
            or not _KEY.fullmatch(self.provider_id)
            or not self.model_id
            or not isinstance(self.tier, ModelTier)
        ):
            raise ModelRoutingError("arm evaluation metadata is invalid")
        if not self.reason_codes:
            raise ModelRoutingError("arm evaluation requires at least one reason code")
        if self.eligible != (self.reason_codes == ("eligible",)):
            raise ModelRoutingError("arm eligibility and reason codes disagree")
        if any(not value for value in self.reason_codes + self.missing_capabilities):
            raise ModelRoutingError("arm evaluation reason values cannot be empty")
        if min(self.estimated_cost_microunits, self.estimated_latency_ms) < 0:
            raise ModelRoutingError("arm evaluation estimates cannot be negative")


@dataclass(frozen=True, slots=True)
class ModelRouteDecisionReceipt(RecordMixin):
    identity: IdentityRecord
    format_version: str
    router_key: str
    router_version: str
    demand: ModelTaskDemand
    selected_arm_id: str | None
    fallback_arm_ids: tuple[str, ...]
    registry_digest: str
    registry_arms: tuple[ModelArm, ...]
    arms: tuple[ModelArmEvaluation, ...]
    reserved_cost_microunits: int
    reserved_latency_ms: int
    stop_reason: str

    @property
    def attempt_order(self) -> tuple[str, ...]:
        if self.selected_arm_id is None:
            return ()
        return (self.selected_arm_id, *self.fallback_arm_ids)

    @classmethod
    def create(
        cls,
        *,
        router_key: str,
        router_version: str,
        demand: ModelTaskDemand,
        selected_arm_id: str | None,
        fallback_arm_ids: Iterable[str],
        registry_arms: Iterable[ModelArm],
        arms: Iterable[ModelArmEvaluation],
    ) -> "ModelRouteDecisionReceipt":
        if not _KEY.fullmatch(router_key) or not _VERSION.fullmatch(router_version):
            raise ModelRoutingError("router key or version is invalid")
        registry = tuple(sorted(registry_arms, key=lambda item: item.arm_id))
        evaluations = tuple(sorted(arms, key=lambda item: item.arm_id))
        if len({item.arm_id for item in registry}) != len(registry):
            raise ModelRoutingError("route registry contains duplicate model arms")
        if len({item.arm_id for item in evaluations}) != len(evaluations):
            raise ModelRoutingError("route decision contains duplicate model arms")
        registry_by_id = {item.arm_id: item for item in registry}
        if set(registry_by_id) != {item.arm_id for item in evaluations}:
            raise ModelRoutingError("route evaluations do not cover the full arm registry")
        for evaluation in evaluations:
            arm = registry_by_id[evaluation.arm_id]
            if (
                evaluation.provider_id != arm.provider_id
                or evaluation.model_id != arm.model_id
                or evaluation.tier is not arm.tier
                or evaluation.estimated_cost_microunits
                != arm.estimated_cost_microunits
                or evaluation.estimated_latency_ms != arm.estimated_latency_ms
            ):
                raise ModelRoutingError("route evaluation does not bind its registry arm")
            if evaluation != _evaluate_model_arm(demand, arm):
                raise ModelRoutingError("route evaluation gate results do not validate")
        eligible_arms = sorted(
            (item for item in evaluations if item.eligible),
            key=lambda item: (
                _TIER_ORDER[item.tier],
                item.estimated_cost_microunits,
                item.estimated_latency_ms,
                item.arm_id,
            ),
        )
        eligible = {item.arm_id for item in eligible_arms}
        expected_selected = eligible_arms[0].arm_id if eligible_arms else None
        fallbacks = tuple(fallback_arm_ids)
        if len(set(fallbacks)) != len(fallbacks):
            raise ModelRoutingError("route fallback arms must be unique")
        if selected_arm_id is not None and selected_arm_id not in eligible:
            raise ModelRoutingError("selected model arm is absent or ineligible")
        if selected_arm_id != expected_selected:
            raise ModelRoutingError(
                "selected model arm does not match deterministic routing order"
            )
        if any(item not in eligible or item == selected_arm_id for item in fallbacks):
            raise ModelRoutingError("fallback model arm is absent, ineligible, or selected")
        reserved_cost = 0
        reserved_latency = 0
        expected_order: list[str] = []
        for item in eligible_arms:
            next_cost = reserved_cost + item.estimated_cost_microunits
            next_latency = reserved_latency + item.estimated_latency_ms
            if next_cost > demand.maximum_cost_microunits:
                break
            if (
                demand.maximum_latency_ms is not None
                and next_latency > demand.maximum_latency_ms
            ):
                break
            expected_order.append(item.arm_id)
            reserved_cost = next_cost
            reserved_latency = next_latency
        expected_selected = expected_order[0] if expected_order else None
        if selected_arm_id != expected_selected:
            raise ModelRoutingError(
                "selected model arm does not match cumulative deterministic routing order"
            )
        expected_fallbacks = tuple(expected_order[1:])
        if fallbacks != expected_fallbacks:
            raise ModelRoutingError(
                "route fallbacks do not match the cumulative budget reservation"
            )
        registry_digest = sha256_digest(
            canonical_json_bytes([item.to_dict() for item in registry])
        )
        stop_reason = "selected" if selected_arm_id is not None else "no_eligible_arm"
        key = {
            "format_version": "1.0.0",
            "router_key": router_key,
            "router_version": router_version,
            "demand": demand.to_dict(),
            "selected_arm_id": selected_arm_id,
            "fallback_arm_ids": fallbacks,
            "registry_digest": registry_digest,
            "registry_arms": [item.to_dict() for item in registry],
            "arms": [item.to_dict() for item in evaluations],
            "reserved_cost_microunits": reserved_cost,
            "reserved_latency_ms": reserved_latency,
            "stop_reason": stop_reason,
        }
        return cls(
            IdentityRecord.create("model_route_decision", key),
            "1.0.0",
            router_key,
            router_version,
            demand,
            selected_arm_id,
            fallbacks,
            registry_digest,
            registry,
            evaluations,
            reserved_cost,
            reserved_latency,
            stop_reason,
        )


class ModelRouter:
    """Choose the cheapest arm in the earliest capable escalation tier.

    The same stable ordering is retained as the fallback order within cumulative cost
    and sequential-latency reservations. Runtime failures are
    handled by the caller by advancing through :attr:`ModelRouteDecisionReceipt.attempt_order`;
    they do not rewrite the original eligibility decision.
    """

    def __init__(
        self,
        *,
        router_key: str = "taedri.model-router.cheapest-capable",
        router_version: str = "1.0.0",
    ) -> None:
        if not _KEY.fullmatch(router_key) or not _VERSION.fullmatch(router_version):
            raise ModelRoutingError("router key or version is invalid")
        self.router_key = router_key
        self.router_version = router_version

    def decide(
        self,
        demand: ModelTaskDemand,
        arms: Iterable[ModelArm],
        *,
        selected_arm_id: str | None = None,
    ) -> ModelRouteDecisionReceipt:
        values = tuple(arms)
        if len({item.arm_id for item in values}) != len(values):
            raise ModelRoutingError("model arm identifiers must be unique")
        by_id = {item.arm_id: item for item in values}
        evaluations = tuple(self._evaluate(demand, item) for item in values)
        evaluations_by_id = {item.arm_id: item for item in evaluations}
        eligible = [item for item in values if evaluations_by_id[item.arm_id].eligible]
        eligible.sort(key=self._selection_key)
        selected = eligible[0].arm_id if eligible else None
        if selected_arm_id is not None:
            if selected_arm_id not in by_id or not evaluations_by_id[
                selected_arm_id
            ].eligible:
                raise ModelRoutingError("selected model arm is absent or ineligible")
            if selected_arm_id != selected:
                raise ModelRoutingError(
                    "selected model arm does not match deterministic routing order"
                )
        reserved_cost = 0
        reserved_latency = 0
        attempt_order: list[str] = []
        for arm in eligible:
            next_cost = reserved_cost + arm.estimated_cost_microunits
            next_latency = reserved_latency + arm.estimated_latency_ms
            if next_cost > demand.maximum_cost_microunits:
                break
            if (
                demand.maximum_latency_ms is not None
                and next_latency > demand.maximum_latency_ms
            ):
                break
            attempt_order.append(arm.arm_id)
            reserved_cost = next_cost
            reserved_latency = next_latency
        selected = attempt_order[0] if attempt_order else None
        fallback_ids = tuple(attempt_order[1:])
        ordered_evaluations = tuple(
            evaluations_by_id[key] for key in sorted(evaluations_by_id)
        )
        return ModelRouteDecisionReceipt.create(
            router_key=self.router_key,
            router_version=self.router_version,
            demand=demand,
            selected_arm_id=selected,
            fallback_arm_ids=fallback_ids,
            registry_arms=values,
            arms=ordered_evaluations,
        )

    @staticmethod
    def _selection_key(arm: ModelArm) -> tuple[int, int, int, str]:
        return (
            _TIER_ORDER[arm.tier],
            arm.estimated_cost_microunits,
            arm.estimated_latency_ms,
            arm.arm_id,
        )

    @staticmethod
    def _evaluate(demand: ModelTaskDemand, arm: ModelArm) -> ModelArmEvaluation:
        return _evaluate_model_arm(demand, arm)


def _evaluate_model_arm(
    demand: ModelTaskDemand, arm: ModelArm
) -> ModelArmEvaluation:
    reasons: list[str] = []
    missing = tuple(sorted(set(demand.required_capabilities) - set(arm.capabilities)))
    if missing:
        reasons.append("missing_capability")
    if demand.privacy_mode not in arm.privacy_modes:
        reasons.append("privacy_denied")
    if arm.network_required and not demand.network_allowed:
        reasons.append("network_denied")
    if arm.estimated_cost_microunits > demand.maximum_cost_microunits:
        reasons.append("cost_budget_exceeded")
    if (
        demand.maximum_latency_ms is not None
        and arm.estimated_latency_ms > demand.maximum_latency_ms
    ):
        reasons.append("latency_budget_exceeded")
    if not arm.healthy:
        reasons.append("unhealthy")
    reason_codes = tuple(reasons) if reasons else ("eligible",)
    return ModelArmEvaluation(
        arm.arm_id,
        arm.provider_id,
        arm.model_id,
        arm.tier,
        not reasons,
        reason_codes,
        missing,
        arm.estimated_cost_microunits,
        arm.estimated_latency_ms,
    )


__all__ = [
    "ModelArm",
    "ModelArmEvaluation",
    "ModelRouteDecisionReceipt",
    "ModelRouter",
    "ModelRoutingError",
    "ModelTaskDemand",
    "ModelTier",
    "PrivacyMode",
]
