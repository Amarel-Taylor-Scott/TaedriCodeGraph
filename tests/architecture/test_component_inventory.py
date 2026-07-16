from __future__ import annotations

import csv
import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "eval/results/component-capability-inventory-2026-07-16"


class ComponentInventoryArchitectureTests(unittest.TestCase):
    def test_all_components_and_evidence_counts_reconcile(self) -> None:
        inventory = json.loads((RESULTS / "components.json").read_text("utf-8"))
        architecture = json.loads(
            (ROOT / "architecture/components.json").read_text("utf-8")
        )
        with (RESULTS / "components.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(inventory["component_count"], 32)
        self.assertEqual(len(inventory["components"]), 32)
        self.assertEqual(len(rows), 32)
        self.assertEqual(
            {item["id"]: item["status"] for item in inventory["components"]},
            {item["id"]: item["status"] for item in architecture["components"]},
        )
        self.assertEqual(inventory["postgres_table_count"], 44)
        self.assertEqual(inventory["api_operation_count"], 41)
        self.assertEqual(inventory["api_path_count"], 37)
        primitive = next(
            item for item in inventory["components"] if item["id"] == "primitive-capsules"
        )
        self.assertIn("1 public release", primitive["measured_records"])
        self.assertIn("deterministic route: 2 releases", primitive["measured_records"])
        factory = next(
            item for item in inventory["components"] if item["id"] == "primitive-factory"
        )
        self.assertIn("0 released by factory", factory["measured_records"])

    def test_inventory_visuals_are_self_contained_and_valid(self) -> None:
        page = (ROOT / "docs/visuals/component-capability-inventory.html").read_text(
            "utf-8"
        )
        self.assertIn("Taedri component inventory", page)
        self.assertIn("const data=", page)
        self.assertNotIn("<script src=", page)
        ET.parse(ROOT / "docs/visuals/assets/component-readiness-status.svg")


if __name__ == "__main__":
    unittest.main()
