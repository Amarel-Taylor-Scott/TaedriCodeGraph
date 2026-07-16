from __future__ import annotations

import csv
import json
import sqlite3
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "eval/results/data-primitive-cohort-2026-07-16"


class DataPrimitiveCohortArchitectureTests(unittest.TestCase):
    def test_measured_registry_search_and_composition_counts_reconcile(self) -> None:
        run = json.loads((RESULTS / "run.json").read_text("utf-8"))
        with (RESULTS / "primitive-catalog.csv").open(
            encoding="utf-8", newline=""
        ) as stream:
            catalog = list(csv.DictReader(stream))
        with (RESULTS / "compatibility-edges.csv").open(
            encoding="utf-8", newline=""
        ) as stream:
            compatibility = list(csv.DictReader(stream))
        self.assertEqual(run["status"], "passed")
        self.assertEqual(run["primitive_count"], 11)
        self.assertEqual(run["new_data_primitive_count"], 9)
        self.assertEqual(len(catalog), 11)
        self.assertEqual(run["executed_case_count"], 66)
        self.assertEqual(run["capsule_payload_count"], 143)
        self.assertEqual(run["evidence_edge_count"], 66)
        self.assertEqual(run["typed_port_count"], 22)
        self.assertEqual(run["search_exact_selection_count"], 11)
        self.assertEqual(run["digested_pack_count"], 11)
        self.assertEqual(run["digested_file_count"], 132)
        self.assertTrue(
            all(
                item["digestion_omitted_roles"] == ["verifier"]
                for item in run["records"]
            )
        )
        self.assertEqual(len(compatibility), run["compatibility_edge_count"])
        self.assertEqual(run["compatibility_edge_count"], 18)
        self.assertEqual(run["model_calls"], 0)
        self.assertEqual(run["generated_route_code_bytes"], 0)
        self.assertEqual(run["text_route"]["output"], "customer_strasse")
        self.assertEqual(run["numeric_route"]["output"], 0.5)
        self.assertEqual(run["text_route"]["receipt"]["executed_stage_count"], 4)
        self.assertEqual(run["numeric_route"]["receipt"]["executed_stage_count"], 2)

    def test_persistent_registry_and_download_packs_are_real(self) -> None:
        database = RESULTS / "data-primitive-registry.sqlite"
        connection = sqlite3.connect(
            f"file:{database}?mode=ro&immutable=1", uri=True
        )
        try:
            self.assertEqual(
                connection.execute("PRAGMA integrity_check").fetchone()[0], "ok"
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM primitive_release").fetchone()[0],
                11,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM primitive_blob").fetchone()[0],
                109,
            )
        finally:
            connection.close()
        packs = sorted((RESULTS / "packs").glob("*.tcgpack"))
        self.assertEqual(len(packs), 11)
        self.assertTrue(all(path.stat().st_size > 3_000 for path in packs))

    def test_graph_chart_and_console_are_self_contained(self) -> None:
        ET.parse(RESULTS / "primitive-cohort.graphml")
        ET.parse(RESULTS / "primitive-cohort-summary.svg")
        page = (RESULTS / "index.html").read_text("utf-8")
        self.assertIn("Taedri data primitive cohort", page)
        self.assertIn('id="dataset" type="application/json"', page)
        self.assertNotIn("<script src=", page)


if __name__ == "__main__":
    unittest.main()
