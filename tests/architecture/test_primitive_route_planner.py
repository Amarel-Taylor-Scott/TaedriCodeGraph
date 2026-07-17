from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from tools.benchmark_primitive_route_planner import run


ROOT = Path(__file__).resolve().parents[2]
COHORT = ROOT / "eval/results/data-primitive-cohort-2026-07-17"
RESULTS = ROOT / "eval/results/primitive-route-planner-2026-07-17"


class PrimitiveRoutePlannerArchitectureTests(unittest.TestCase):
    def test_checked_search_execution_abstention_and_reuse_metrics_reconcile(self) -> None:
        record = json.loads((RESULTS / "run.json").read_bytes())
        with (RESULTS / "tasks.csv").open(encoding="utf-8", newline="") as stream:
            tasks = list(csv.DictReader(stream))
        retrievals = [
            json.loads(line)
            for line in (RESULTS / "retrieval-executions.jsonl")
            .read_text("utf-8")
            .splitlines()
        ]
        searches = [
            json.loads(line)
            for line in (RESULTS / "route-searches.jsonl")
            .read_text("utf-8")
            .splitlines()
        ]
        recipes = [
            json.loads(line)
            for line in (RESULTS / "verified-recipes.jsonl")
            .read_text("utf-8")
            .splitlines()
        ]
        self.assertEqual(record["status"], "passed")
        self.assertEqual(record["catalog_primitive_count"], 23)
        self.assertEqual(record["positive_task_count"], 7)
        self.assertEqual(record["successful_task_count"], 7)
        self.assertEqual(record["negative_task_count"], 3)
        self.assertEqual(record["negative_abstention_count"], 3)
        self.assertEqual(record["requested_stage_count"], 20)
        self.assertEqual(record["retrieval_execution_count"], 20)
        self.assertEqual(record["retrieved_candidate_count"], 64)
        self.assertEqual(record["retrieval_cost_units"], 127)
        self.assertEqual(record["route_search_considered_candidate_count"], 24)
        self.assertEqual(record["route_search_wire_assessment_count"], 16)
        self.assertEqual(record["verified_recipe_count"], 7)
        self.assertEqual(record["verified_recipe_cache_hit_count"], 7)
        self.assertEqual(record["cache_hit_considered_candidate_count"], 0)
        self.assertEqual(record["cache_hit_wire_assessment_count"], 0)
        self.assertEqual(record["model_calls"], 0)
        self.assertEqual(record["semantic_calls"], 0)
        self.assertEqual(record["generated_route_code_bytes"], 0)
        self.assertEqual(len(tasks), 7)
        self.assertEqual(len(retrievals), 20)
        self.assertEqual(len(searches), 7)
        self.assertEqual(len(recipes), 7)
        self.assertTrue(all(item["reuse_source"] == "verified_recipe" for item in tasks))
        self.assertTrue(
            all(item["route_count"] == 0 for item in record["negative_cases"])
        )

    def test_benchmark_artifacts_are_exactly_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "results"
            generated = run(cohort=COHORT, output=destination)
            checked = json.loads((RESULTS / "run.json").read_bytes())
            self.assertEqual(generated, checked)
            for name in (
                "run.json",
                "tasks.csv",
                "retrieval-executions.jsonl",
                "route-searches.jsonl",
                "verified-recipes.jsonl",
                "README.md",
            ):
                self.assertEqual(
                    (destination / name).read_bytes(),
                    (RESULTS / name).read_bytes(),
                    name,
                )


if __name__ == "__main__":
    unittest.main()
