from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from taedri_codegraph.prompt_interception import (
    ReleasedPrimitiveCatalog,
    load_natural_primitive_tasks,
    run_prompt_interception_campaign,
)
from taedri_codegraph.token_savings import (
    TokenSavingsError,
    measure_prompt_interception_campaign,
    measure_prompt_interception_campaign_file,
)
from tests.primitive_fixtures import requires_checked_campaign_runtime
from tests.prompt_interception_fakes import SemanticFakeChatProvider


ROOT = Path(__file__).resolve().parents[2]
COHORT = ROOT / "eval/results/data-primitive-cohort-2026-07-16"
TASKS = ROOT / "fixtures/prompt-interception/natural-tasks.json"
LEGACY_LIVE = (
    ROOT
    / "eval/results/prompt-interception-live-pilot-2026-07-16"
    / "mistral-small-2603-k4-seed0.campaign.json"
)


class TokenSavingsCampaignAdapterTests(unittest.TestCase):
    @requires_checked_campaign_runtime
    def test_serialized_campaign_is_measured_without_self_promotion(self) -> None:
        catalog = ReleasedPrimitiveCatalog.load_checked_cohort(COHORT)
        task = load_natural_primitive_tasks(TASKS)[0]
        campaign = run_prompt_interception_campaign(
            catalog=catalog,
            tasks=(task,),
            provider=SemanticFakeChatProvider(),
            provider_id="fake",
            model="fake-model",
            seeds=(17,),
            max_completion_tokens=64,
            shortlist_limit=4,
        )
        measurement = measure_prompt_interception_campaign(campaign.to_dict())
        pair = campaign.matched_pairs[0]
        assert pair.full_catalog_usage is not None
        assert pair.shortlist_usage is not None
        self.assertEqual(measurement.pair_count, 1)
        self.assertEqual(measurement.accepted_pair_count, 1)
        self.assertEqual(
            measurement.baseline_total_tokens,
            pair.full_catalog_usage.prompt_tokens
            + pair.full_catalog_usage.completion_tokens,
        )
        self.assertEqual(
            measurement.reuse_total_tokens,
            pair.shortlist_usage.prompt_tokens
            + pair.shortlist_usage.completion_tokens,
        )
        output = measurement.to_dict()
        validation = output["campaign_validation"]
        self.assertFalse(validation["legacy"])
        self.assertTrue(validation["manifest_complete"])
        self.assertTrue(validation["arm_matrix_complete"])
        self.assertTrue(validation["pair_matrix_complete"])
        self.assertTrue(validation["verification_occurrences_bound"])
        self.assertEqual(len(measurement.source_verifier_refs), 2)
        self.assertTrue(output["receipt_integrity_resolved"])
        self.assertFalse(output["evidence_integrity_verified"])
        self.assertFalse(output["correctness_preserving"])
        self.assertFalse(output["savings_claimable"])
        self.assertIn("trusted runtime attestation", output["claim_reason"])
        tampered = campaign.to_dict()
        tampered["matched_pairs"][0]["full_catalog_usage"]["prompt_tokens"] += 1
        with self.assertRaisesRegex(TokenSavingsError, "content-addressed identity"):
            measure_prompt_interception_campaign(tampered)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "campaign.json"
            path.write_text(json.dumps(campaign.to_dict()), "utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "prove_token_savings.py"),
                    "--campaign",
                    str(path),
                    "--compact",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            cli_output = json.loads(completed.stdout)
            self.assertEqual(
                cli_output["measurement_digest"], measurement.measurement_digest
            )
            self.assertFalse(cli_output["savings_claimable"])

    def test_legacy_live_campaign_remains_readable_but_completeness_unresolved(self) -> None:
        measurement = measure_prompt_interception_campaign_file(LEGACY_LIVE)
        output = measurement.to_dict()
        validation = output["campaign_validation"]
        self.assertTrue(validation["legacy"])
        self.assertFalse(validation["manifest_complete"])
        self.assertFalse(validation["verification_occurrences_bound"])
        self.assertTrue(validation["limitations"])
        self.assertFalse(output["receipt_integrity_resolved"])
        self.assertFalse(output["evidence_integrity_verified"])
        self.assertFalse(output["savings_claimable"])


if __name__ == "__main__":
    unittest.main()
