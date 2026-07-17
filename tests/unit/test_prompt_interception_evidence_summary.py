from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from typing import Iterable

from taedri_codegraph.model_providers import ChatMessage
from taedri_codegraph.prompt_interception import (
    ReleasedPrimitiveCatalog,
    load_natural_primitive_tasks,
    run_prompt_interception_campaign,
)
from tests.prompt_interception_fakes import SemanticFakeChatProvider


ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools" / "summarize_prompt_interception_evidence.py"
SPEC = importlib.util.spec_from_file_location("evidence_summary_tool", TOOL_PATH)
assert SPEC is not None and SPEC.loader is not None
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)
COHORT = ROOT / "eval/results/data-primitive-cohort-2026-07-16"
TASKS = ROOT / "fixtures/prompt-interception/natural-tasks.json"


class FullCatalogAbstainProvider:
    def chat(
        self,
        model: str,
        messages: Iterable[ChatMessage],
        **kwargs: object,
    ) -> object:
        prepared = tuple(messages)
        payload = json.loads(prepared[-1].content)
        forced = None
        if len(payload["primitive_cards"]) == 11:
            forced = (
                '{"reason_code":"no_suitable_candidate",'
                '"selected_route_handle":null}'
            )
        return SemanticFakeChatProvider(forced_content=forced).chat(
            model, prepared, **kwargs
        )


class FailingProvider:
    def chat(self, *_args: object, **_kwargs: object) -> object:
        raise RuntimeError("bounded test provider failure")


class EvidenceSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = ReleasedPrimitiveCatalog.load_checked_cohort(COHORT)
        cls.task = load_natural_primitive_tasks(TASKS)[0]

    def campaign(self) -> dict[str, object]:
        return run_prompt_interception_campaign(
            catalog=self.catalog,
            tasks=(self.task,),
            provider=FullCatalogAbstainProvider(),
            provider_id="fake",
            model="fake-model",
            seeds=(0,),
            max_completion_tokens=64,
            shortlist_limit=1,
        ).to_dict()

    def test_summary_preserves_failures_and_provider_native_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "campaign.json"
            raw = json.dumps(self.campaign(), sort_keys=True).encode("utf-8")
            path.write_bytes(raw)
            summary = TOOL.build_summary([path])

        campaign = summary["campaigns"][0]
        self.assertEqual(
            campaign["campaign_file_sha256"],
            f"sha256:{hashlib.sha256(raw).hexdigest()}",
        )
        self.assertEqual(campaign["failure_count"], 1)
        self.assertEqual(
            campaign["failures"][0]["error_code"],
            "teacher_abstained_no_suitable_candidate",
        )
        self.assertGreater(
            campaign["provider_native_token_observation"]["observed_delta_tokens"],
            0,
        )
        self.assertFalse(summary["claimable_token_savings"])
        self.assertFalse(campaign["strict_validation"]["legacy"])
        self.assertTrue(campaign["strict_validation"]["manifest_complete"])
        self.assertEqual(
            campaign["verification"]["checked_tcgpack_execution_receipt_count"],
            1,
        )
        self.assertEqual(
            campaign["failures"][0]["condition"], "all_descriptions"
        )

    def test_output_files_are_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "campaign.json"
            path.write_text(json.dumps(self.campaign()), encoding="utf-8")
            summary_path = root / "summary.json"
            csv_path = root / "summary.csv"
            result = TOOL.main(
                [
                    str(path),
                    "--summary",
                    str(summary_path),
                    "--csv",
                    str(csv_path),
                ]
            )
            loaded = json.loads(summary_path.read_text(encoding="utf-8"))
            with csv_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(result, 0)
        self.assertEqual(loaded["campaign_observation_totals"]["failure_count"], 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["failure_count"], "1")

    def test_missing_provider_usage_is_not_reported_as_zero_delta(self) -> None:
        document = run_prompt_interception_campaign(
            catalog=self.catalog,
            tasks=(self.task,),
            provider=FailingProvider(),
            provider_id="fake",
            model="fake-model",
            seeds=(0,),
            max_completion_tokens=64,
            shortlist_limit=1,
        ).to_dict()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "failed-campaign.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            campaign = TOOL.build_summary([path])["campaigns"][0]

        observation = campaign["provider_native_token_observation"]
        self.assertFalse(observation["comparison_available"])
        self.assertIsNone(observation["observed_delta_tokens"])
        self.assertIsNone(observation["observed_delta_ppm_of_all_descriptions"])

    def test_stale_identity_token_mutation_is_rejected_before_summary(self) -> None:
        document = self.campaign()
        document["arms"][0]["interception"]["model_usage"]["prompt_tokens"] += 1
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "tampered-campaign.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(TOOL.EvidenceSummaryError):
                TOOL.build_summary([path])


if __name__ == "__main__":
    unittest.main()
