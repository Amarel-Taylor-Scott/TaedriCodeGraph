from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from taedri_codegraph.readiness import ReadinessError, load_component_readiness


ROOT = Path(__file__).resolve().parents[2]


class ComponentReadinessTests(unittest.TestCase):
    def test_every_declared_component_has_truthful_readiness_and_paths(self) -> None:
        report = load_component_readiness(ROOT)
        self.assertEqual(report["component_count"], 32)
        self.assertEqual(sum(report["status_counts"].values()), 32)
        self.assertGreaterEqual(len(report["definition_of_done"]), 7)
        self.assertTrue(report["external_gates"])
        architecture = json.loads(
            (ROOT / "architecture/components.json").read_text("utf-8")
        )
        manifest_statuses = {
            item["id"]: item["status"] for item in architecture["components"]
        }
        evidence_statuses = {
            item["id"]: item["status"] for item in report["components"]
        }
        self.assertEqual(manifest_statuses, evidence_statuses)
        self.assertNotIn("scaffolded", report["status_counts"])

    def test_manifest_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "architecture").mkdir()
            components = json.loads((ROOT / "architecture/components.json").read_text("utf-8"))
            readiness = json.loads(
                (ROOT / "architecture/component-readiness.v1.json").read_text("utf-8")
            )
            readiness["components"] = readiness["components"][:-1]
            (root / "architecture/components.json").write_text(json.dumps(components), "utf-8")
            (root / "architecture/component-readiness.v1.json").write_text(
                json.dumps(readiness), "utf-8"
            )
            with self.assertRaisesRegex(ReadinessError, "manifest mismatch"):
                load_component_readiness(root)


if __name__ == "__main__":
    unittest.main()
