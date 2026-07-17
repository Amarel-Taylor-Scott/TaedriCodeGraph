from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from tools.benchmark_primitive_retrieval_program import run


ROOT = Path(__file__).resolve().parents[2]
COHORT = ROOT / "eval/results/data-primitive-cohort-2026-07-16"
FIXTURE = ROOT / "fixtures/primitive-retrieval/retrieval-cases.json"
RESULTS = ROOT / "eval/results/primitive-retrieval-program-2026-07-17"


class PrimitiveRetrievalBenchmarkArchitectureTests(unittest.TestCase):
    def test_checked_metrics_reconcile_with_case_receipts(self) -> None:
        record = json.loads((RESULTS / "run.json").read_bytes())
        with (RESULTS / "cases.csv").open(
            encoding="utf-8", newline=""
        ) as stream:
            cases = list(csv.DictReader(stream))
        executions = [
            json.loads(line)
            for line in (RESULTS / "executions.jsonl").read_text("utf-8").splitlines()
        ]
        self.assertEqual(record["status"], "passed")
        self.assertEqual(record["catalog_primitive_count"], 13)
        self.assertEqual(record["fixture_case_count"], 31)
        self.assertEqual(record["positive_case_count"], 26)
        self.assertEqual(record["negative_case_count"], 5)
        self.assertEqual(len(cases), 31)
        self.assertEqual(len(executions), 31)
        self.assertEqual(record["legacy_metrics"]["positive_hits_at_1"], 25)
        self.assertEqual(record["program_metrics"]["positive_hits_at_1"], 26)
        self.assertEqual(record["legacy_metrics"]["negative_abstentions"], 3)
        self.assertEqual(record["program_metrics"]["negative_abstentions"], 5)
        self.assertEqual(record["legacy_metrics"]["returned_candidate_count"], 83)
        self.assertEqual(record["program_metrics"]["returned_candidate_count"], 34)
        self.assertEqual(record["comparison"]["candidate_count_reduction"], 49)
        self.assertEqual(record["model_calls"], 0)
        self.assertEqual(record["semantic_calls"], 0)
        self.assertTrue(
            all(
                item["execution"]["program_digest"] == record["program_digest"]
                for item in executions
            )
        )

    def test_benchmark_artifacts_are_exactly_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "results"
            generated = run(cohort=COHORT, fixture=FIXTURE, output=destination)
            checked = json.loads((RESULTS / "run.json").read_bytes())
            self.assertEqual(generated, checked)
            for name in ("run.json", "cases.csv", "executions.jsonl", "README.md"):
                self.assertEqual(
                    (destination / name).read_bytes(),
                    (RESULTS / name).read_bytes(),
                    name,
                )


if __name__ == "__main__":
    unittest.main()
