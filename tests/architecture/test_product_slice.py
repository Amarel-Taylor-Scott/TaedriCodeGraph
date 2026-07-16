from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "eval" / "results" / "primitive-factory-2026-07-16"


class ProductSliceArchitectureTests(unittest.TestCase):
    def test_business_model_is_measurable_and_does_not_invent_prices(self) -> None:
        model = json.loads((ROOT / "architecture" / "business-model.v1.json").read_text("utf-8"))
        self.assertEqual(
            model["core_value_unit"]["name"],
            "independently-accepted-policy-compliant-outcome",
        )
        self.assertIn("never counted", model["core_value_unit"]["billing_rule"])
        self.assertEqual(
            model["claim_policy"]["currency_prices"],
            "unset-until-customer-discovery-and-cost-measurement",
        )
        self.assertGreaterEqual(len(model["offers"]), 4)
        self.assertEqual(len({offer["id"] for offer in model["offers"]}), len(model["offers"]))
        self.assertEqual(len({meter["id"] for meter in model["meters"]}), len(model["meters"]))
        for meter in model["meters"]:
            self.assertTrue(meter["unit"])
            self.assertTrue(meter["anti_abuse_rule"])
        serialized = json.dumps(model)
        self.assertIsNone(re.search(r"\$[0-9]|USD|EUR|GBP", serialized))

    def test_operational_schemas_are_parseable_and_versioned(self) -> None:
        for name in (
            "candidate-submission.v1.schema.json",
            "worker-job.v1.schema.json",
            "prompt-session-event.v1.schema.json",
        ):
            schema = json.loads((ROOT / "schemas" / name).read_text("utf-8"))
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertIn("v1", schema["$id"])

    def test_real_candidate_artifacts_reconcile_and_retain_non_promotion(self) -> None:
        manifest = json.loads((RESULTS / "candidate-manifest.json").read_text("utf-8"))
        candidate_lines = (RESULTS / "candidates.jsonl").read_text("utf-8").splitlines()
        search_lines = (RESULTS / "search-index.jsonl").read_text("utf-8").splitlines()
        expected = manifest["factory"]["candidate_count"]
        self.assertEqual(len(candidate_lines), expected)
        self.assertEqual(len(search_lines), expected)
        self.assertEqual(manifest["intake"]["submission_count"], expected)
        self.assertEqual(manifest["intake"]["event_count"], expected * 4)
        self.assertEqual(manifest["intake"]["promoted_count"], 0)
        self.assertEqual(manifest["factory"]["diagnostic_count"], 0)
        self.assertEqual(manifest["harness_session"]["terminal_outcome"], "abstained")
        self.assertEqual(manifest["harness_session"]["model_calls"], 0)
        pack = (RESULTS / "selected-candidate.tcgpack").read_bytes()
        self.assertEqual(
            "sha256:" + hashlib.sha256(pack).hexdigest(),
            manifest["selected_pack"]["digest"],
        )

    def test_console_is_self_contained_and_visual_assets_are_valid_xml(self) -> None:
        console = (ROOT / "apps" / "explorer" / "registry-console.html").read_text("utf-8")
        self.assertIn('id="candidate-list"', console)
        self.assertIn('data-tab="business"', console)
        self.assertNotIn("fetch(", console)
        self.assertNotIn("XMLHttpRequest", console)
        match = re.search(
            r'<script id="dataset" type="application/json">(.*?)</script>',
            console,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        data = json.loads(match.group(1))
        self.assertEqual(len(data["candidates"]), data["summary"]["candidate_count"])
        for name in ("primitive-candidate-kinds.svg", "product-operating-model.svg"):
            ElementTree.parse(ROOT / "docs" / "visuals" / "assets" / name)


if __name__ == "__main__":
    unittest.main()

