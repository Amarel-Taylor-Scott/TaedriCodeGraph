from __future__ import annotations

import json
import re
import unittest
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "eval" / "results" / "benchmark-worker-2026-07-16"


class BenchmarkProductArchitectureTests(unittest.TestCase):
    def test_benchmark_schemas_and_worker_kind_are_exported(self) -> None:
        for name in (
            "benchmark-task.v1.schema.json",
            "benchmark-experiment.v1.schema.json",
            "benchmark-run-receipt.v1.schema.json",
        ):
            schema = json.loads((ROOT / "schemas" / name).read_text("utf-8"))
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertIn("v1", schema["$id"])
        worker_schema = json.loads((ROOT / "schemas" / "worker-job.v1.schema.json").read_text("utf-8"))
        self.assertIn("benchmark", worker_schema["properties"]["kind"]["enum"])

    def test_conformance_bundle_reconciles_without_becoming_an_efficacy_claim(self) -> None:
        report = json.loads((RESULTS / "conformance-report.json").read_text("utf-8"))
        experiment = json.loads((RESULTS / "conformance-experiment.json").read_text("utf-8"))
        tasks = (RESULTS / "conformance-tasks.jsonl").read_text("utf-8").splitlines()
        specs = [json.loads(line) for line in (RESULTS / "conformance-run-specs.jsonl").read_text("utf-8").splitlines()]
        receipts = [json.loads(line) for line in (RESULTS / "conformance-run-receipts.jsonl").read_text("utf-8").splitlines()]
        jobs = [json.loads(line) for line in (RESULTS / "worker-jobs.jsonl").read_text("utf-8").splitlines()]
        expected = len(tasks) * len(experiment["lanes"]) * len(experiment["seeds"])
        self.assertEqual(expected, 16)
        self.assertEqual(len(specs), expected)
        self.assertEqual(len(receipts), expected)
        self.assertEqual(len(jobs), expected)
        self.assertEqual(report["scheduled_run_count"], expected)
        self.assertEqual(report["completed_run_count"], expected)
        self.assertTrue(report["is_complete"])
        self.assertFalse(report["efficacy_claimable"])
        self.assertEqual(report["evidence_class"], "conformance_fixture")
        self.assertIn("cannot support", report["claim_warning"])
        self.assertEqual(experiment["model_id"], "not-a-model")
        self.assertTrue(all(receipt["model_usage_receipt_ref"] is None for receipt in receipts))
        self.assertEqual({job["kind"] for job in jobs}, {"benchmark"})
        self.assertEqual(
            Counter(receipt["lane"] for receipt in receipts),
            Counter({lane: 4 for lane in experiment["lanes"]}),
        )
        self.assertEqual(len({receipt["run_spec_id"] for receipt in receipts}), expected)
        forbidden = {
            ref
            for line in tasks
            for ref in json.loads(line)["forbidden_retrieval_refs"]
        }
        exposed = {
            ref
            for receipt in receipts
            for ref in receipt["retrieved_refs"] + receipt["materialized_refs"]
        }
        self.assertFalse(forbidden & exposed)

    def test_campaign_and_business_model_do_not_invent_roi(self) -> None:
        campaign = json.loads((RESULTS / "campaign-plan.json").read_text("utf-8"))
        model = json.loads((ROOT / "architecture" / "business-model.v1.json").read_text("utf-8"))
        self.assertIn("benchmark-and-assurance-pilot", {offer["id"] for offer in model["offers"]})
        self.assertIn("isolated-benchmark-attempt", {meter["id"] for meter in model["meters"]})
        self.assertIn("fixture or replay data presented as model efficacy", campaign["promotion_gate"]["forbidden_claims"])
        self.assertEqual(len(campaign["lanes"]), 4)
        self.assertGreaterEqual(len(campaign["evaluation_tracks"]), 4)
        self.assertIsNone(re.search(r"\$[0-9]|USD|EUR|GBP", json.dumps(campaign)))

    def test_console_is_self_contained_and_visual_is_valid(self) -> None:
        console = (ROOT / "apps" / "explorer" / "benchmark-console.html").read_text("utf-8")
        self.assertIn("CONFORMANCE FIXTURE — NOT MODEL EFFICACY", console)
        self.assertNotIn("fetch(", console)
        self.assertNotIn("XMLHttpRequest", console)
        match = re.search(
            r'<script id="dataset" type="application/json">(.*?)</script>',
            console,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        assert match is not None
        data = json.loads(match.group(1))
        self.assertFalse(data["report"]["efficacy_claimable"])
        self.assertEqual(len(data["campaign"]["lanes"]), 4)
        ElementTree.parse(
            ROOT / "docs" / "visuals" / "assets" / "benchmark-worker-evidence-boundary.svg"
        )


if __name__ == "__main__":
    unittest.main()
