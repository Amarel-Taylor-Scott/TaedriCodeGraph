"""Versioned, receipt-producing mechanism waterfalls.

Domain packages use this small kernel to compose exact, heuristic, model-backed, and
external mechanisms without giving any one provider canonical authority.
"""

from .waterfall import (
    FailurePolicy,
    MechanismBudget,
    MechanismDefinition,
    MechanismInvocation,
    MechanismMode,
    MechanismRegistry,
    MechanismResult,
    RunStatus,
    StageDefinition,
    StepStatus,
    WaterfallExecutor,
    WaterfallPlan,
    WaterfallRun,
)

__all__ = [
    "FailurePolicy",
    "MechanismBudget",
    "MechanismDefinition",
    "MechanismInvocation",
    "MechanismMode",
    "MechanismRegistry",
    "MechanismResult",
    "RunStatus",
    "StageDefinition",
    "StepStatus",
    "WaterfallExecutor",
    "WaterfallPlan",
    "WaterfallRun",
]
