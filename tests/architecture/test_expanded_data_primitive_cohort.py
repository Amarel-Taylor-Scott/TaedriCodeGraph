from __future__ import annotations

import csv
import json
import sqlite3
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "eval/results/data-primitive-cohort-2026-07-17"


class ExpandedDataPrimitiveCohortArchitectureTests(unittest.TestCase):
    def test_release_execution_search_and_composition_counts_reconcile(self) -> None:
        run = json.loads((RESULTS / "run.json").read_bytes())
        with (RESULTS / "primitive-catalog.csv").open(
            encoding="utf-8", newline=""
        ) as stream:
            catalog = list(csv.DictReader(stream))
        with (RESULTS / "compatibility-edges.csv").open(
            encoding="utf-8", newline=""
        ) as stream:
            compatibility = list(csv.DictReader(stream))
        self.assertEqual(run["status"], "passed")
        self.assertEqual(run["primitive_count"], 23)
        self.assertEqual(run["new_data_primitive_count"], 21)
        self.assertEqual(
            run["categories"],
            {
                "data-cleaning": 7,
                "data-engineering": 8,
                "data-science": 6,
                "text-core": 2,
            },
        )
        self.assertEqual(len(catalog), 23)
        self.assertEqual(run["executed_case_count"], 138)
        self.assertEqual(run["capsule_payload_count"], 299)
        self.assertEqual(run["evidence_edge_count"], 138)
        self.assertEqual(run["typed_port_count"], 46)
        self.assertEqual(run["unique_capability_group_count"], 21)
        self.assertEqual(run["search_exact_selection_count"], 23)
        self.assertEqual(run["digested_pack_count"], 23)
        self.assertEqual(run["digested_file_count"], 276)
        self.assertEqual(len(compatibility), 111)
        self.assertEqual(run["compatibility_edge_count"], 111)
        self.assertEqual(run["deterministic_route_count"], 6)
        self.assertEqual(run["model_calls"], 0)
        self.assertEqual(run["generated_route_code_bytes"], 0)
        self.assertEqual(
            run["json_route"]["output"],
            '{"user.age":37,"user.name":"Ada"}',
        )
        self.assertEqual(run["number_adapter_route"]["output"], "1.25")
        self.assertEqual(
            run["json_route"]["receipt"]["executed_stage_count"], 5
        )
        self.assertEqual(
            run["number_adapter_route"]["receipt"]["executed_stage_count"], 3
        )

    def test_persistent_registry_packs_and_visuals_are_real(self) -> None:
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
                23,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM primitive_blob").fetchone()[0],
                225,
            )
        finally:
            connection.close()
        packs = sorted((RESULTS / "packs").glob("*.tcgpack"))
        self.assertEqual(len(packs), 23)
        self.assertTrue(all(path.stat().st_size > 3_000 for path in packs))
        ET.parse(RESULTS / "primitive-cohort.graphml")
        ET.parse(RESULTS / "primitive-cohort-summary.svg")
        page = (RESULTS / "index.html").read_text("utf-8")
        self.assertIn("JSON adapter route", page)
        self.assertIn("Number adapter route", page)
        self.assertIn('id="dataset" type="application/json"', page)


if __name__ == "__main__":
    unittest.main()
