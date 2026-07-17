from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Iterable

from taedri_codegraph.identity import IdentityRecord
from taedri_codegraph.model_providers import ChatMessage, ChatResult, ModelUsageReceipt
from taedri_codegraph.prompt_interception import (
    PromptInterceptionError,
    PromptInterceptor,
    ReleasedPrimitiveCatalog,
    RetrievalArm,
    load_natural_primitive_tasks,
    run_prompt_interception_campaign,
    validate_prompt_interception_campaign_document,
)
from tests.primitive_fixtures import requires_checked_campaign_runtime
from tests.prompt_interception_fakes import SemanticFakeChatProvider

ROOT = Path(__file__).resolve().parents[2]
COHORT = ROOT / "eval/results/data-primitive-cohort-2026-07-16"
TASKS = ROOT / "fixtures/prompt-interception/natural-tasks.json"
LEGACY_CAMPAIGN = (
    ROOT
    / "eval/results/prompt-interception-live-pilot-2026-07-16"
    / "mistral-small-2603-k4-seed0.campaign.json"
)


def _remint_body(record: dict[str, object], kind: str) -> None:
    key = {name: value for name, value in record.items() if name != "identity"}
    record["identity"] = IdentityRecord.create(kind, key).to_dict()


def _remint_campaign_identity(campaign: dict[str, object]) -> None:
    key = {
        name: value
        for name, value in campaign.items()
        if name not in {"identity", "arms", "matched_pairs"}
    }
    key["arm_ids"] = [item["identity"]["id"] for item in campaign["arms"]]
    key["matched_pair_ids"] = [
        item["identity"]["id"] for item in campaign["matched_pairs"]
    ]
    campaign["identity"] = IdentityRecord.create(
        "prompt_interception_campaign_receipt", key
    ).to_dict()


def _remint_mutated_verification_ancestors(campaign: dict[str, object]) -> None:
    arm_id_updates: dict[str, str] = {}
    for arm in campaign["arms"]:
        old_arm_id = arm["identity"]["id"]
        verification = arm["verification"]
        if verification is not None:
            _remint_body(
                verification, "independent_primitive_verification_receipt"
            )
        _remint_body(arm, "prompt_interception_campaign_arm_receipt")
        arm_id_updates[old_arm_id] = arm["identity"]["id"]
    arms_by_id = {item["identity"]["id"]: item for item in campaign["arms"]}
    for pair in campaign["matched_pairs"]:
        pair["full_catalog_arm_id"] = arm_id_updates[pair["full_catalog_arm_id"]]
        pair["shortlist_arm_id"] = arm_id_updates[pair["shortlist_arm_id"]]
        full = arms_by_id[pair["full_catalog_arm_id"]]
        shortlist = arms_by_id[pair["shortlist_arm_id"]]
        for prefix, arm in (("full_catalog", full), ("shortlist", shortlist)):
            verification = arm["verification"]
            pair[f"{prefix}_verifier_id"] = (
                verification["identity"]["id"] if verification else None
            )
            pair[f"{prefix}_verification_occurrence_id"] = (
                verification["occurrence"]["identity"]["id"]
                if verification
                else None
            )
        _remint_body(pair, "matched_prompt_interception_pair")
    _remint_campaign_identity(campaign)


class DifferingReportedModelProvider:
    def chat(
        self,
        model: str,
        messages: Iterable[ChatMessage],
        **kwargs: object,
    ) -> ChatResult:
        prepared = tuple(messages)
        result = SemanticFakeChatProvider().chat(model, prepared, **kwargs)
        payload = json.loads(prepared[-1].content)
        reported = (
            "deployment-full"
            if len(payload["primitive_cards"]) == 13
            else "deployment-local"
        )
        receipt = result.receipt
        changed = ModelUsageReceipt.create(
            provider_id=receipt.provider_id,
            provider_api=receipt.provider_api,
            usage_source=receipt.usage_source,
            endpoint_origin=receipt.endpoint_origin,
            model_requested=receipt.model_requested,
            model_reported=reported,
            request_digest=receipt.request_digest,
            response_digest=receipt.response_digest,
            content_digest=receipt.content_digest,
            started_at=receipt.started_at,
            completed_at=receipt.completed_at,
            wall_ms=receipt.wall_ms,
            prompt_tokens=receipt.prompt_tokens,
            completion_tokens=receipt.completion_tokens,
            total_duration_ns=receipt.total_duration_ns,
            load_duration_ns=receipt.load_duration_ns,
            prompt_eval_duration_ns=receipt.prompt_eval_duration_ns,
            eval_duration_ns=receipt.eval_duration_ns,
            finish_reason=receipt.finish_reason,
        )
        return ChatResult(result.content, changed)


class PromptInterceptionCampaignIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = ReleasedPrimitiveCatalog.load_checked_cohort(COHORT)
        cls.tasks = load_natural_primitive_tasks(TASKS)

    @requires_checked_campaign_runtime
    def test_matched_arms_execute_selected_checked_packs(self) -> None:
        provider = SemanticFakeChatProvider()
        selected_tasks = (self.tasks[0], self.tasks[5])
        campaign = run_prompt_interception_campaign(
            catalog=self.catalog,
            tasks=selected_tasks,
            provider=provider,
            provider_id="fake",
            model="fake-model",
            seeds=(17,),
            max_completion_tokens=64,
            shortlist_limit=4,
        )
        self.assertEqual(len(campaign.arms), 4)
        self.assertEqual(len(campaign.matched_pairs), 2)
        self.assertEqual(campaign.format_version, "2.0.0")
        self.assertEqual(campaign.expected_counts.task_count, 2)
        self.assertEqual(len(campaign.task_manifest), 2)
        self.assertTrue(all(item.status == "accepted" for item in campaign.arms))
        for arm in campaign.arms:
            self.assertEqual(arm.attempt_index, 1)
            self.assertIsNotNone(arm.verification)
            verification = arm.verification
            assert verification is not None
            self.assertTrue(verification.accepted)
            self.assertEqual(verification.executed_case_count, 2)
            self.assertEqual(verification.passed_case_count, 2)
            self.assertEqual(
                verification.occurrence.interception_receipt_id,
                arm.interception.identity.id,
            )
            self.assertGreaterEqual(arm.wall_ms, 0)
            self.assertTrue(arm.started_at.endswith("Z"))
            self.assertTrue(arm.completed_at.endswith("Z"))
            self.assertTrue(
                all(item.pipeline_receipt_id is not None for item in verification.cases)
            )
            verification.identity.validate()
        for pair in campaign.matched_pairs:
            self.assertTrue(pair.full_catalog_accepted)
            self.assertTrue(pair.shortlist_accepted)
            assert pair.full_catalog_usage is not None
            assert pair.shortlist_usage is not None
            self.assertGreater(
                pair.full_catalog_usage.prompt_tokens,
                pair.shortlist_usage.prompt_tokens,
            )
            self.assertNotEqual(
                pair.full_catalog_verification_occurrence_id,
                pair.shortlist_verification_occurrence_id,
            )
            self.assertIsNotNone(pair.provider_deployment_digest)
        campaign.identity.validate()
        validation = validate_prompt_interception_campaign_document(campaign.to_dict())
        self.assertTrue(validation.claimable_independent_execution)
        self.assertTrue(validation.manifest_complete)
        output = json.dumps(campaign.to_dict(), sort_keys=True)
        for task in selected_tasks:
            self.assertNotIn(task.request, output)
            for case in task.hidden_cases:
                self.assertNotIn(json.dumps(case.input_value), output)

    @requires_checked_campaign_runtime
    def test_wrong_teacher_selection_fails_only_after_real_pack_execution(self) -> None:
        task = self.tasks[0]
        provider = SemanticFakeChatProvider(forced_name="normalize-text")
        interceptor = PromptInterceptor(self.catalog, provider, shortlist_limit=4)
        interception = interceptor.intercept(
            task,
            RetrievalArm.DETERMINISTIC_SHORTLIST,
            model="fake-model",
            seed=1,
            max_completion_tokens=64,
        )
        self.assertEqual(interception.status, "selected")
        selected = self.catalog.card(str(interception.selected_primitive_id))
        self.assertEqual(selected.name, "normalize-text")
        campaign = run_prompt_interception_campaign(
            catalog=self.catalog,
            tasks=(task,),
            provider=SemanticFakeChatProvider(forced_name="normalize-text"),
            provider_id="fake",
            model="fake-model",
            seeds=(1,),
            max_completion_tokens=64,
            shortlist_limit=4,
        )
        verification = campaign.arms[0].verification
        assert verification is not None
        self.assertFalse(verification.accepted)
        self.assertEqual(verification.executed_case_count, 2)
        self.assertTrue(
            all(item.pipeline_receipt_id is not None for item in verification.cases)
        )
        self.assertTrue(all(item.error_code == "output_mismatch" for item in verification.cases))

    @requires_checked_campaign_runtime
    def test_arm_order_is_counterbalanced_across_seed_attempts(self) -> None:
        campaign = run_prompt_interception_campaign(
            catalog=self.catalog,
            tasks=(self.tasks[0],),
            provider=SemanticFakeChatProvider(),
            provider_id="fake",
            model="fake-model",
            seeds=(1, 2),
            max_completion_tokens=64,
            shortlist_limit=4,
        )
        by_attempt = {
            attempt: sorted(
                (item for item in campaign.arms if item.attempt_index == attempt),
                key=lambda item: item.pair_order,
            )
            for attempt in (1, 2)
        }
        self.assertNotEqual(
            by_attempt[1][0].retrieval_arm,
            by_attempt[2][0].retrieval_arm,
        )

    @requires_checked_campaign_runtime
    def test_strict_parser_rejects_verifier_transplant_and_cloned_pair_ref(self) -> None:
        campaign = run_prompt_interception_campaign(
            catalog=self.catalog,
            tasks=(self.tasks[0],),
            provider=SemanticFakeChatProvider(),
            provider_id="fake",
            model="fake-model",
            seeds=(7,),
            max_completion_tokens=64,
            shortlist_limit=4,
        ).to_dict()
        full = next(
            item for item in campaign["arms"] if item["retrieval_arm"] == "full_catalog"
        )
        shortlist = next(
            item
            for item in campaign["arms"]
            if item["retrieval_arm"] == "deterministic_shortlist"
        )
        shortlist["verification"] = copy.deepcopy(full["verification"])
        _remint_mutated_verification_ancestors(campaign)
        with self.assertRaisesRegex(
            PromptInterceptionError, "occurrence.*arm|arm.*occurrence"
        ):
            validate_prompt_interception_campaign_document(campaign)

        cloned_ref = run_prompt_interception_campaign(
            catalog=self.catalog,
            tasks=(self.tasks[0],),
            provider=SemanticFakeChatProvider(),
            provider_id="fake",
            model="fake-model",
            seeds=(7,),
            max_completion_tokens=64,
            shortlist_limit=4,
        ).to_dict()
        pair = cloned_ref["matched_pairs"][0]
        pair["shortlist_verification_occurrence_id"] = pair[
            "full_catalog_verification_occurrence_id"
        ]
        _remint_body(pair, "matched_prompt_interception_pair")
        _remint_campaign_identity(cloned_ref)
        with self.assertRaisesRegex(PromptInterceptionError, "occurrence"):
            validate_prompt_interception_campaign_document(cloned_ref)

    @requires_checked_campaign_runtime
    def test_strict_parser_rejects_omitted_task_and_pair(self) -> None:
        campaign = run_prompt_interception_campaign(
            catalog=self.catalog,
            tasks=(self.tasks[0], self.tasks[1]),
            provider=SemanticFakeChatProvider(),
            provider_id="fake",
            model="fake-model",
            seeds=(3,),
            max_completion_tokens=64,
            shortlist_limit=4,
        ).to_dict()
        omitted_task = copy.deepcopy(campaign)
        task_id = omitted_task["task_manifest"][1]["task_id"]
        omitted_task["arms"] = [
            item for item in omitted_task["arms"] if item["task_id"] != task_id
        ]
        omitted_task["matched_pairs"] = [
            item
            for item in omitted_task["matched_pairs"]
            if item["task_id"] != task_id
        ]
        _remint_campaign_identity(omitted_task)
        with self.assertRaisesRegex(PromptInterceptionError, "arm matrix"):
            validate_prompt_interception_campaign_document(omitted_task)

        omitted_pair = copy.deepcopy(campaign)
        omitted_pair["matched_pairs"].pop()
        _remint_campaign_identity(omitted_pair)
        with self.assertRaisesRegex(PromptInterceptionError, "matched-pair matrix"):
            validate_prompt_interception_campaign_document(omitted_pair)

    @requires_checked_campaign_runtime
    def test_strict_parser_rejects_wrong_task_case_and_pack_binding(self) -> None:
        original = run_prompt_interception_campaign(
            catalog=self.catalog,
            tasks=(self.tasks[0],),
            provider=SemanticFakeChatProvider(),
            provider_id="fake",
            model="fake-model",
            seeds=(5,),
            max_completion_tokens=64,
            shortlist_limit=4,
        ).to_dict()
        mutations = {
            "task": lambda verification: verification.__setitem__(
                "task_id", "transplanted.task"
            ),
            "case": lambda verification: verification["cases"][0].__setitem__(
                "input_digest", f"sha256:{'0' * 64}"
            ),
            "pack": lambda verification: verification.__setitem__(
                "pack_id", self.catalog.cards[-1].pack_id
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                campaign = copy.deepcopy(original)
                verification = campaign["arms"][0]["verification"]
                mutate(verification)
                _remint_mutated_verification_ancestors(campaign)
                with self.assertRaises(PromptInterceptionError):
                    validate_prompt_interception_campaign_document(campaign)

    @requires_checked_campaign_runtime
    def test_pair_rejects_different_reported_provider_deployments(self) -> None:
        with self.assertRaisesRegex(
            PromptInterceptionError, "concrete provider deployment differs"
        ):
            run_prompt_interception_campaign(
                catalog=self.catalog,
                tasks=(self.tasks[0],),
                provider=DifferingReportedModelProvider(),
                provider_id="fake",
                model="requested-alias",
                seeds=(0,),
                max_completion_tokens=64,
                shortlist_limit=4,
            )

    def test_checked_legacy_campaign_is_validation_only_and_nonclaimable(self) -> None:
        validation = validate_prompt_interception_campaign_document(
            json.loads(LEGACY_CAMPAIGN.read_text("utf-8"))
        )
        self.assertTrue(validation.legacy)
        self.assertFalse(validation.manifest_complete)
        self.assertFalse(validation.verification_occurrences_bound)
        self.assertFalse(validation.claimable_independent_execution)
        self.assertGreaterEqual(len(validation.limitations), 3)

    def test_cli_defaults_to_bounded_dry_run_without_a_credential(self) -> None:
        environment = dict(os.environ)
        environment.pop("TAEDRI_LIVE_MODEL_CAMPAIGN", None)
        completed = subprocess.run(
            (
                sys.executable,
                str(ROOT / "tools/run_prompt_interception_campaign.py"),
                "--provider",
                "openrouter",
                "--model",
                "provider/model",
                "--locally-selected-description-limit",
                "3",
                "--task-id",
                self.tasks[0].task_id,
                "--compact",
            ),
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        schedule = json.loads(completed.stdout)
        self.assertEqual(schedule["mode"], "dry_run")
        self.assertEqual(schedule["provider_calls_planned"], 2)
        self.assertEqual(schedule["max_response_bytes"], 1_048_576)
        self.assertEqual(schedule["timeout_seconds"], "60.0")
        self.assertEqual(schedule["shortlist_limit"], 3)

        invalid = subprocess.run(
            (
                sys.executable,
                str(ROOT / "tools/run_prompt_interception_campaign.py"),
                "--provider",
                "openrouter",
                "--model",
                "provider/model",
                "--shortlist-limit",
                str(len(self.catalog.cards)),
            ),
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("smaller than the checked catalog", invalid.stderr)


if __name__ == "__main__":
    unittest.main()
