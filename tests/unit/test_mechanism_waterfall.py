from __future__ import annotations

import unittest

from taedri_codegraph.mechanisms import (
    FailurePolicy,
    MechanismBudget,
    MechanismDefinition,
    MechanismMode,
    MechanismRegistry,
    MechanismResult,
    RunStatus,
    StageDefinition,
    StepStatus,
    WaterfallExecutor,
    WaterfallPlan,
)


class MechanismWaterfallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = MechanismRegistry()
        self.registry.register(
            MechanismDefinition(
                "taedri.test.exact", "1.0.0", "taedri.phase.retrieve", True
            ),
            lambda invocation: MechanismResult(
                {"candidate": invocation.request["query"]}, 500_000, ("evidence:exact",)
            ),
        )
        self.registry.register(
            MechanismDefinition(
                "taedri.test.semantic",
                "1.0.0",
                "taedri.phase.retrieve",
                False,
                cost_units=7,
                required_capabilities=("embedding",),
            ),
            lambda _invocation: MechanismResult(
                {"candidate": "semantic"}, 900_000, ("evidence:vector",)
            ),
        )

    def test_until_confidence_falls_through_and_retains_receipts(self) -> None:
        plan = WaterfallPlan(
            "taedri.plan.search",
            "1.0.0",
            (
                StageDefinition(
                    "taedri.phase.retrieve",
                    (
                        "taedri.test.exact@1.0.0",
                        "taedri.test.semantic@1.0.0",
                    ),
                    MechanismMode.UNTIL_CONFIDENCE,
                    FailurePolicy.FAIL_CLOSED,
                    confidence_threshold_ppm=800_000,
                ),
            ),
        )
        run = WaterfallExecutor(self.registry).execute(
            plan, {"query": "parse address"}, capabilities=("embedding",)
        )
        self.assertEqual(run.status, RunStatus.SUCCEEDED)
        self.assertEqual(len(run.receipts), 2)
        self.assertEqual(run.consumed_cost_units, 8)
        self.assertEqual(run.receipts[-1].confidence_ppm, 900_000)
        self.assertTrue(run.run_id.startswith("uceg:v1:waterfall_run:"))
        self.assertNotIn("parse address", str(run.receipts))

    def test_missing_optional_capability_is_explicit_partial(self) -> None:
        plan = WaterfallPlan(
            "taedri.plan.search",
            "1.0.0",
            (
                StageDefinition(
                    "taedri.phase.retrieve",
                    (
                        "taedri.test.exact@1.0.0",
                        "taedri.test.semantic@1.0.0",
                    ),
                    MechanismMode.ALL,
                    FailurePolicy.CONTINUE,
                ),
            ),
        )
        run = WaterfallExecutor(self.registry).execute(plan, {"query": "x"})
        self.assertEqual(run.status, RunStatus.PARTIAL)
        self.assertEqual(run.receipts[-1].status, StepStatus.SKIPPED_CAPABILITY)
        self.assertEqual(run.receipts[-1].error_code, "missing_capability")

    def test_budget_fails_closed_without_calling_expensive_handler(self) -> None:
        plan = WaterfallPlan(
            "taedri.plan.search",
            "1.0.0",
            (
                StageDefinition(
                    "taedri.phase.retrieve",
                    ("taedri.test.semantic@1.0.0",),
                ),
            ),
        )
        run = WaterfallExecutor(self.registry).execute(
            plan,
            {"query": "x"},
            capabilities=("embedding",),
            budget=MechanismBudget(maximum_cost_units=1),
        )
        self.assertEqual(run.status, RunStatus.FAILED)
        self.assertEqual(run.stop_reason, "budget_exhausted")
        self.assertEqual(run.consumed_cost_units, 0)

    def test_duplicate_registration_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.registry.register(
                MechanismDefinition(
                    "taedri.test.exact", "1.0.0", "taedri.phase.retrieve", True
                ),
                lambda _invocation: MechanismResult(),
            )


if __name__ == "__main__":
    unittest.main()
