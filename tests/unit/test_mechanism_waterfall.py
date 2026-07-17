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

    def test_until_confidence_also_satisfies_minimum_successes(self) -> None:
        calls: list[str] = []

        def handler(name: str, confidence: int):
            def invoke(_invocation):
                calls.append(name)
                return MechanismResult({"candidate": name}, confidence)

            return invoke

        for name, confidence in (("high", 900_000), ("low", 100_000)):
            self.registry.register(
                MechanismDefinition(
                    f"taedri.test.{name}",
                    "1.0.0",
                    "taedri.phase.minimum",
                    True,
                ),
                handler(name, confidence),
            )
        self.registry.register(
            MechanismDefinition(
                "taedri.test.unexpected",
                "1.0.0",
                "taedri.phase.minimum",
                True,
            ),
            lambda _invocation: (_ for _ in ()).throw(
                AssertionError("waterfall did not stop after satisfying both gates")
            ),
        )
        plan = WaterfallPlan(
            "taedri.plan.minimum",
            "1.0.0",
            (
                StageDefinition(
                    "taedri.phase.minimum",
                    (
                        "taedri.test.high@1.0.0",
                        "taedri.test.low@1.0.0",
                        "taedri.test.unexpected@1.0.0",
                    ),
                    MechanismMode.UNTIL_CONFIDENCE,
                    FailurePolicy.FAIL_CLOSED,
                    minimum_successes=2,
                    confidence_threshold_ppm=800_000,
                ),
            ),
        )
        run = WaterfallExecutor(self.registry).execute(plan, {"query": "x"})
        self.assertEqual(run.status, RunStatus.SUCCEEDED)
        self.assertEqual(calls, ["high", "low"])
        self.assertEqual(len(run.receipts), 2)

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

    def test_continue_with_no_success_abstains_for_every_non_success_outcome(self) -> None:
        self.registry.register(
            MechanismDefinition(
                "taedri.test.failure", "1.0.0", "taedri.phase.retrieve", True
            ),
            lambda _invocation: (_ for _ in ()).throw(RuntimeError("fixture failure")),
        )
        cases = (
            (
                "skipped_capability",
                "taedri.test.semantic@1.0.0",
                (),
                MechanismBudget(),
                StepStatus.SKIPPED_CAPABILITY,
            ),
            (
                "skipped_budget",
                "taedri.test.semantic@1.0.0",
                ("embedding",),
                MechanismBudget(maximum_cost_units=1),
                StepStatus.SKIPPED_BUDGET,
            ),
            (
                "failed",
                "taedri.test.failure@1.0.0",
                (),
                MechanismBudget(),
                StepStatus.FAILED,
            ),
        )
        for name, reference, capabilities, budget, expected_step_status in cases:
            with self.subTest(name=name):
                plan = WaterfallPlan(
                    "taedri.plan.search",
                    "1.0.0",
                    (
                        StageDefinition(
                            "taedri.phase.retrieve",
                            (reference,),
                            MechanismMode.ALL,
                            FailurePolicy.CONTINUE,
                        ),
                    ),
                )
                run = WaterfallExecutor(self.registry).execute(
                    plan,
                    {"query": "x"},
                    capabilities=capabilities,
                    budget=budget,
                )
                self.assertEqual(run.status, RunStatus.ABSTAINED)
                self.assertEqual(run.stop_reason, "no_mechanism_succeeded")
                self.assertEqual(run.outputs, {})
                self.assertEqual(run.receipts[0].status, expected_step_status)

    def test_until_confidence_unmet_applies_every_failure_policy(self) -> None:
        expected = {
            FailurePolicy.FAIL_CLOSED: RunStatus.FAILED,
            FailurePolicy.CONTINUE: RunStatus.PARTIAL,
            FailurePolicy.ABSTAIN: RunStatus.ABSTAINED,
        }
        for policy, expected_status in expected.items():
            with self.subTest(policy=policy.value):
                plan = WaterfallPlan(
                    "taedri.plan.search",
                    "1.0.0",
                    (
                        StageDefinition(
                            "taedri.phase.retrieve",
                            ("taedri.test.exact@1.0.0",),
                            MechanismMode.UNTIL_CONFIDENCE,
                            policy,
                            confidence_threshold_ppm=800_000,
                        ),
                    ),
                )
                run = WaterfallExecutor(self.registry).execute(plan, {"query": "x"})
                self.assertEqual(run.status, expected_status)
                self.assertEqual(run.receipts[0].status, StepStatus.SUCCEEDED)
                self.assertEqual(run.receipts[0].confidence_ppm, 500_000)
                self.assertEqual(len(run.outputs), 1)
                if policy is FailurePolicy.CONTINUE:
                    self.assertEqual(run.stop_reason, "plan_complete")
                else:
                    self.assertEqual(
                        run.stop_reason,
                        "stage_confidence_not_met:taedri.phase.retrieve",
                    )

    def test_until_confidence_requires_reported_confidence(self) -> None:
        self.registry.register(
            MechanismDefinition(
                "taedri.test.no-confidence",
                "1.0.0",
                "taedri.phase.retrieve",
                True,
            ),
            lambda _invocation: MechanismResult({"candidate": "unscored"}),
        )
        plan = WaterfallPlan(
            "taedri.plan.search",
            "1.0.0",
            (
                StageDefinition(
                    "taedri.phase.retrieve",
                    ("taedri.test.no-confidence@1.0.0",),
                    MechanismMode.UNTIL_CONFIDENCE,
                    FailurePolicy.FAIL_CLOSED,
                    confidence_threshold_ppm=0,
                ),
            ),
        )
        run = WaterfallExecutor(self.registry).execute(plan, {"query": "x"})
        self.assertEqual(run.status, RunStatus.FAILED)
        self.assertEqual(
            run.stop_reason, "stage_confidence_not_met:taedri.phase.retrieve"
        )

    def test_later_success_cannot_erase_continued_unmet_confidence(self) -> None:
        self.registry.register(
            MechanismDefinition(
                "taedri.test.finalize", "1.0.0", "taedri.phase.finalize", True
            ),
            lambda _invocation: MechanismResult({"final": True}),
        )
        plan = WaterfallPlan(
            "taedri.plan.search",
            "1.0.0",
            (
                StageDefinition(
                    "taedri.phase.retrieve",
                    ("taedri.test.exact@1.0.0",),
                    MechanismMode.UNTIL_CONFIDENCE,
                    FailurePolicy.CONTINUE,
                    confidence_threshold_ppm=800_000,
                ),
                StageDefinition(
                    "taedri.phase.finalize",
                    ("taedri.test.finalize@1.0.0",),
                    MechanismMode.ALL,
                    FailurePolicy.FAIL_CLOSED,
                ),
            ),
        )
        run = WaterfallExecutor(self.registry).execute(plan, {"query": "x"})
        self.assertEqual(run.status, RunStatus.PARTIAL)
        self.assertEqual(
            [receipt.status for receipt in run.receipts],
            [StepStatus.SUCCEEDED, StepStatus.SUCCEEDED],
        )
        self.assertEqual(len(run.outputs), 2)

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
