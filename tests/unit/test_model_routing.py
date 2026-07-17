from __future__ import annotations

import json
import unittest
from dataclasses import replace

from taedri_codegraph.model_routing import (
    ModelArm,
    ModelRouteDecisionReceipt,
    ModelRouter,
    ModelRoutingError,
    ModelTaskDemand,
    ModelTier,
    PrivacyMode,
)


def _demand(**overrides):
    values = {
        "task_key": "taedri.task.code",
        "input_digest": "sha256:" + "a" * 64,
        "required_capabilities": ("chat", "code"),
        "privacy_mode": PrivacyMode.HOSTED_ALLOWED,
        "network_allowed": True,
        "maximum_cost_microunits": 5_000,
        "maximum_latency_ms": 5_000,
    }
    values.update(overrides)
    return ModelTaskDemand(**values)


def _arm(
    arm_id: str,
    tier: ModelTier,
    cost: int,
    *,
    capabilities=("chat", "code"),
    privacy_modes=(PrivacyMode.HOSTED_ALLOWED,),
    network_required=False,
    latency=100,
    healthy=True,
):
    return ModelArm(
        arm_id=arm_id,
        provider_id=arm_id.split(".")[0],
        model_id=arm_id + "/model",
        tier=tier,
        capabilities=capabilities,
        privacy_modes=privacy_modes,
        network_required=network_required,
        estimated_cost_microunits=cost,
        estimated_latency_ms=latency,
        healthy=healthy,
    )


class ModelRoutingTests(unittest.TestCase):
    def test_prefers_local_escalation_tier_and_cheapest_arm_within_it(self) -> None:
        decision = ModelRouter().decide(
            _demand(),
            (
                _arm("hosted.cheap", ModelTier.HOSTED_SMALL, 1),
                _arm("local.expensive", ModelTier.LOCAL_SLM, 50),
                _arm("local.cheap", ModelTier.LOCAL_SLM, 10),
            ),
        )
        self.assertEqual(decision.selected_arm_id, "local.cheap")
        self.assertEqual(
            decision.attempt_order,
            ("local.cheap", "local.expensive", "hosted.cheap"),
        )
        self.assertTrue(decision.identity.id.startswith("uceg:v1:model_route_decision:"))

    def test_hard_gates_retain_every_rejection_reason(self) -> None:
        blocked = _arm(
            "hosted.blocked",
            ModelTier.HOSTED_STRONG,
            9_000,
            capabilities=("chat",),
            privacy_modes=(PrivacyMode.HOSTED_ALLOWED,),
            network_required=True,
            latency=9_000,
            healthy=False,
        )
        decision = ModelRouter().decide(
            _demand(
                privacy_mode=PrivacyMode.LOCAL_ONLY,
                network_allowed=False,
                maximum_cost_microunits=100,
                maximum_latency_ms=50,
            ),
            (blocked,),
        )
        self.assertIsNone(decision.selected_arm_id)
        self.assertEqual(decision.stop_reason, "no_eligible_arm")
        evaluation = decision.arms[0]
        self.assertFalse(evaluation.eligible)
        self.assertEqual(evaluation.missing_capabilities, ("code",))
        self.assertEqual(
            set(evaluation.reason_codes),
            {
                "missing_capability",
                "privacy_denied",
                "network_denied",
                "cost_budget_exceeded",
                "latency_budget_exceeded",
                "unhealthy",
            },
        )

    def test_unhealthy_local_arm_falls_through_to_next_capable_arm(self) -> None:
        decision = ModelRouter().decide(
            _demand(),
            (
                _arm("local.down", ModelTier.LOCAL_SLM, 0, healthy=False),
                _arm("local.general", ModelTier.LOCAL_GENERAL, 20),
                _arm(
                    "hosted.strong",
                    ModelTier.HOSTED_STRONG,
                    100,
                    network_required=True,
                ),
            ),
        )
        self.assertEqual(
            decision.attempt_order, ("local.general", "hosted.strong")
        )
        down = next(item for item in decision.arms if item.arm_id == "local.down")
        self.assertEqual(down.reason_codes, ("unhealthy",))

    def test_impossible_selection_is_rejected(self) -> None:
        down = _arm("local.down", ModelTier.LOCAL_SLM, 0, healthy=False)
        with self.assertRaisesRegex(ModelRoutingError, "absent or ineligible"):
            ModelRouter().decide(_demand(), (down,), selected_arm_id="local.down")

        cheap = _arm("local.cheap", ModelTier.LOCAL_SLM, 1)
        expensive = _arm("local.expensive", ModelTier.LOCAL_SLM, 2)
        with self.assertRaisesRegex(ModelRoutingError, "deterministic routing order"):
            ModelRouter().decide(
                _demand(),
                (cheap, expensive),
                selected_arm_id="local.expensive",
            )

        decision = ModelRouter().decide(_demand(), (down,))
        with self.assertRaisesRegex(ModelRoutingError, "absent or ineligible"):
            ModelRouteDecisionReceipt.create(
                router_key=decision.router_key,
                router_version=decision.router_version,
                demand=decision.demand,
                selected_arm_id="local.down",
                fallback_arm_ids=(),
                registry_arms=(down,),
                arms=decision.arms,
            )

    def test_fallback_path_is_reserved_within_cumulative_budgets(self) -> None:
        decision = ModelRouter().decide(
            _demand(maximum_cost_microunits=100, maximum_latency_ms=100),
            (
                _arm("hosted.first", ModelTier.HOSTED_SMALL, 60, latency=60),
                _arm("hosted.second", ModelTier.HOSTED_SMALL, 60, latency=60),
                _arm("hosted.third", ModelTier.HOSTED_STRONG, 1, latency=1),
            ),
        )
        self.assertEqual(decision.attempt_order, ("hosted.first",))
        self.assertEqual(decision.reserved_cost_microunits, 60)
        self.assertEqual(decision.reserved_latency_ms, 60)

    def test_receipt_binds_full_registry_metadata_and_digest(self) -> None:
        arm = _arm("local.bound", ModelTier.LOCAL_GENERAL, 3)
        decision = ModelRouter().decide(_demand(), (arm,))
        self.assertEqual(decision.registry_arms, (arm,))
        self.assertRegex(decision.registry_digest, r"^sha256:[0-9a-f]{64}$")
        payload = decision.to_dict()
        self.assertEqual(payload["registry_arms"][0]["capabilities"], ["chat", "code"])
        decision.identity.validate()
        forged = replace(
            decision.arms[0], eligible=False, reason_codes=("unhealthy",)
        )
        with self.assertRaisesRegex(ModelRoutingError, "gate results"):
            ModelRouteDecisionReceipt.create(
                router_key=decision.router_key,
                router_version=decision.router_version,
                demand=decision.demand,
                selected_arm_id=None,
                fallback_arm_ids=(),
                registry_arms=(arm,),
                arms=(forged,),
            )

    def test_decision_is_stable_and_has_no_credential_surface(self) -> None:
        arms = (
            _arm("local.slm", ModelTier.LOCAL_SLM, 0),
            _arm(
                "hosted.small",
                ModelTier.HOSTED_SMALL,
                20,
                network_required=True,
            ),
        )
        first = ModelRouter().decide(_demand(), arms)
        second = ModelRouter().decide(_demand(), reversed(arms))
        self.assertEqual(first.identity.id, second.identity.id)
        payload = json.dumps(first.to_dict(), sort_keys=True).casefold()
        self.assertNotIn("authorization", payload)
        self.assertNotIn("api_token", payload)
        self.assertNotIn("bearer", payload)


if __name__ == "__main__":
    unittest.main()
