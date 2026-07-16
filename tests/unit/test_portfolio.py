from __future__ import annotations

import unittest

from taedri_codegraph.contracts import SubjectRef, ValueKind
from taedri_codegraph.portfolio import (
    DecisionAction,
    EnrichmentDepth,
    MaterializationArm,
    MaterializationState,
    PortfolioDemand,
    PortfolioPolicy,
    ResourceCost,
    materialization_plan_seed,
    materialization_state_seed,
    plan_portfolio_materialization,
)


class AdaptivePortfolioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.subject = SubjectRef("entity", "ceid:function:standalone-utility")
        self.policy = PortfolioPolicy("uceg.policy.adaptive_portfolio", "1.0.0")
        self.budget = ResourceCost(
            storage_bytes=100_000,
            latency_ms=1_000,
            compute_microunits=100_000,
            model_tokens=2_000,
            money_microunits=10_000,
        )
        self.arms = (
            MaterializationArm(
                "uceg.name.qualified",
                "1.0.0",
                EnrichmentDepth.EXACT,
                900_000,
                0,
                ResourceCost(storage_bytes=100, latency_ms=1),
                baseline=True,
            ),
            MaterializationArm(
                "uceg.fingerprint.multiresolution_lsh",
                "1.0.0",
                EnrichmentDepth.STRUCTURAL,
                700_000,
                100_000,
                ResourceCost(storage_bytes=3_000, latency_ms=20, compute_microunits=500),
                prerequisites=("uceg.name.qualified",),
            ),
            MaterializationArm(
                "uceg.embedding.function.behavior",
                "1.0.0",
                EnrichmentDepth.SEMANTIC,
                800_000,
                200_000,
                ResourceCost(
                    storage_bytes=10_000,
                    latency_ms=300,
                    compute_microunits=20_000,
                    model_tokens=800,
                    money_microunits=2_000,
                ),
                prerequisites=("uceg.fingerprint.multiresolution_lsh",),
            ),
        )

    def test_high_subject_local_demand_reaches_semantic_depth(self) -> None:
        demand = PortfolioDemand(
            self.subject,
            query_demand_ppm=900_000,
            candidate_confusion_ppm=950_000,
            reuse_potential_ppm=1_000_000,
            graph_centrality_ppm=700_000,
            evidence_gap_ppm=800_000,
        )
        plan = plan_portfolio_materialization(
            demand,
            self.arms,
            budget=self.budget,
            policy=self.policy,
        )
        self.assertGreaterEqual(plan.recommended_depth, EnrichmentDepth.SEMANTIC)
        self.assertEqual(
            [decision.action for decision in plan.decisions],
            [DecisionAction.QUEUE, DecisionAction.QUEUE, DecisionAction.QUEUE],
        )
        self.assertNotIn("package", plan.to_dict())

    def test_low_differentiation_need_defers_expensive_variants(self) -> None:
        demand = PortfolioDemand(
            self.subject,
            query_demand_ppm=50_000,
            candidate_confusion_ppm=20_000,
            reuse_potential_ppm=100_000,
            graph_centrality_ppm=20_000,
            evidence_gap_ppm=20_000,
        )
        plan = plan_portfolio_materialization(
            demand,
            self.arms,
            budget=self.budget,
            policy=self.policy,
        )
        self.assertEqual(plan.decisions[0].action, DecisionAction.QUEUE)
        self.assertEqual(plan.decisions[1].action, DecisionAction.DEFER)
        self.assertEqual(plan.decisions[2].action, DecisionAction.DEFER)

    def test_budget_and_explicit_states_fail_visible(self) -> None:
        demand = PortfolioDemand(
            self.subject, 1_000_000, 1_000_000, 1_000_000, 1_000_000, 1_000_000
        )
        plan = plan_portfolio_materialization(
            demand,
            self.arms,
            budget=ResourceCost(storage_bytes=100, latency_ms=1),
            policy=self.policy,
            existing_states={
                "uceg.embedding.function.behavior": MaterializationState.WITHHELD,
            },
        )
        self.assertEqual(plan.decisions[0].action, DecisionAction.QUEUE)
        self.assertEqual(plan.decisions[1].reason, "explicit resource budget exhausted")
        self.assertEqual(plan.decisions[2].action, DecisionAction.BLOCKED)

    def test_selector_receipts_are_typed_long_table_variants(self) -> None:
        state = materialization_state_seed(
            self.subject,
            descriptor_key="uceg.embedding.function.behavior",
            descriptor_version="1.0.0",
            state=MaterializationState.NOT_COMPUTED,
            reason="awaiting differentiation pressure",
            policy_key=self.policy.policy_key,
            policy_version=self.policy.policy_version,
        )
        self.assertEqual(state.typed_value.kind, ValueKind.JSON)
        self.assertEqual(state.typed_value.value["state"], "not_computed")

        demand = PortfolioDemand(
            self.subject, 900_000, 900_000, 900_000, 900_000, 900_000
        )
        plan = plan_portfolio_materialization(
            demand,
            self.arms,
            budget=self.budget,
            policy=self.policy,
        )
        receipt = materialization_plan_seed(plan)
        self.assertEqual(receipt.typed_value.kind, ValueKind.JSON)
        self.assertEqual(receipt.representation_key, "uceg.portfolio.materialization_plan")

    def test_multiple_provider_or_parameter_arms_can_share_one_descriptor(self) -> None:
        demand = PortfolioDemand(
            self.subject,
            query_demand_ppm=900_000,
            candidate_confusion_ppm=1_000_000,
            reuse_potential_ppm=800_000,
            graph_centrality_ppm=500_000,
            evidence_gap_ppm=500_000,
        )
        arms = (
            MaterializationArm(
                "uceg.block.fingerprint_lsh",
                "1.0.0",
                EnrichmentDepth.STRUCTURAL,
                700_000,
                100_000,
                ResourceCost(storage_bytes=500, latency_ms=5),
                arm_key="uceg.arm.lsh.minhash16_narrow",
            ),
            MaterializationArm(
                "uceg.block.fingerprint_lsh",
                "1.0.0",
                EnrichmentDepth.STRUCTURAL,
                500_000,
                300_000,
                ResourceCost(storage_bytes=200, latency_ms=3),
                arm_key="uceg.arm.lsh.minhash16_wide",
            ),
        )
        plan = plan_portfolio_materialization(
            demand,
            arms,
            budget=self.budget,
            policy=self.policy,
        )
        self.assertEqual(
            [item.action for item in plan.decisions], [DecisionAction.QUEUE] * 2
        )
        self.assertEqual(len({item.arm_key for item in plan.decisions}), 2)
        self.assertEqual(len({item.descriptor_key for item in plan.decisions}), 1)


if __name__ == "__main__":
    unittest.main()
