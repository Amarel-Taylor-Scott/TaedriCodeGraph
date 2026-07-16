from __future__ import annotations

import csv
import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class PrimitivePlatformWaterfallArchitectureTests(unittest.TestCase):
    def test_seven_waterfalls_have_ordered_stages_and_existing_code_paths(self) -> None:
        artifact = json.loads(
            (ROOT / "architecture/primitive-platform-waterfalls.v1.json").read_text(
                "utf-8"
            )
        )
        self.assertEqual(len(artifact["waterfalls"]), 7)
        self.assertEqual(
            len({item["id"] for item in artifact["waterfalls"]}), 7
        )
        for waterfall in artifact["waterfalls"]:
            ordinals = [stage["ordinal"] for stage in waterfall["stages"]]
            self.assertEqual(ordinals, list(range(1, len(ordinals) + 1)))
            for path in waterfall["code"]:
                self.assertTrue((ROOT / path).exists(), path)

    def test_storage_sql_keeps_facts_separate_from_rebuildable_projections(self) -> None:
        sql = (
            ROOT / "deploy/postgres/002_representation_ledger.sql"
        ).read_text("utf-8")
        fact_tables = (
            "descriptor_definition",
            "representation_content",
            "generation_run",
            "representation_assertion",
            "evidence_link",
            "lineage_assertion",
        )
        projection_tables = (
            "exact_projection",
            "lexical_projection",
            "scalar_projection",
            "blocking_projection",
            "embedding_projection",
            "graph_projection",
        )
        for table in fact_tables + projection_tables:
            self.assertIn(f"CREATE TABLE IF NOT EXISTS taedri.{table}", sql)
        self.assertIn("DROP/REBUILD", sql.upper())
        self.assertIn("content_id", sql)
        self.assertIn("run_id", sql)
        self.assertIn("assertion_id", sql)

    def test_document_preserves_similarity_and_external_gate_boundaries(self) -> None:
        document = (
            ROOT / "docs/architecture/PRIMITIVE_PLATFORM_WATERFALLS.md"
        ).read_text("utf-8")
        self.assertIn("Similarity scores never become compatibility proof", document)
        self.assertIn("OIDC", document)
        self.assertIn("SWE-bench", document)
        self.assertIn("OCI Distribution Specification", document)
        self.assertGreaterEqual(document.count("```mermaid"), 3)

    def test_acceptance_data_and_chart_reconcile_with_architecture_manifests(self) -> None:
        result_root = (
            ROOT / "eval/results/primitive-platform-waterfalls-2026-07-16"
        )
        acceptance = json.loads(
            (result_root / "acceptance.json").read_text("utf-8")
        )
        waterfalls = json.loads(
            (ROOT / "architecture/primitive-platform-waterfalls.v1.json").read_text(
                "utf-8"
            )
        )["waterfalls"]
        readiness = json.loads(
            (ROOT / "architecture/component-readiness.v1.json").read_text("utf-8")
        )["components"]
        with (result_root / "waterfalls.csv").open(
            "r", encoding="utf-8", newline=""
        ) as stream:
            waterfall_rows = list(csv.DictReader(stream))
        with (result_root / "component-readiness.csv").open(
            "r", encoding="utf-8", newline=""
        ) as stream:
            component_rows = list(csv.DictReader(stream))
        self.assertEqual(
            {row["waterfall"] for row in waterfall_rows},
            {item["id"] for item in waterfalls},
        )
        self.assertEqual(
            {row["waterfall"]: int(row["stage_count"]) for row in waterfall_rows},
            {item["id"]: len(item["stages"]) for item in waterfalls},
        )
        self.assertEqual(
            {row["component_id"] for row in component_rows},
            {item["id"] for item in readiness},
        )
        self.assertEqual(
            {
                row["component_id"]: (row["status"], row["scope"])
                for row in component_rows
            },
            {item["id"]: (item["status"], item["scope"]) for item in readiness},
        )
        self.assertEqual(acceptance["waterfalls"]["total"], len(waterfalls))
        self.assertEqual(acceptance["component_readiness"]["total"], len(readiness))
        chart = ET.parse(result_root / "waterfall-readiness.svg")
        self.assertEqual(chart.getroot().tag, "{http://www.w3.org/2000/svg}svg")


if __name__ == "__main__":
    unittest.main()
