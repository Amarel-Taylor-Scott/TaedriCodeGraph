from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class DeploymentTopologyTests(unittest.TestCase):
    def setUp(self) -> None:
        components = json.loads(
            (ROOT / "architecture" / "components.json").read_text("utf-8")
        )["components"]
        self.component_ids = {component["id"] for component in components}
        self.topology = json.loads((ROOT / "deploy" / "topology.v1.json").read_text("utf-8"))

    def test_processes_reference_declared_components(self) -> None:
        for stage in self.topology["stages"]:
            for process in stage["processes"]:
                self.assertTrue(process["component_ids"])
                for component_id in process["component_ids"]:
                    self.assertIn(component_id, self.component_ids)

    def test_stages_preserve_modular_monolith_before_service_split(self) -> None:
        stage_ids = [stage["id"] for stage in self.topology["stages"]]
        self.assertEqual(
            stage_ids,
            [
                "S0-local-vertical-slice",
                "S1-fly-modular-service",
                "S2-independent-services",
            ],
        )
        self.assertIn("process groups", self.topology["stages"][1]["deployment_unit"])

    def test_production_truth_never_depends_on_ephemeral_storage(self) -> None:
        for stage in self.topology["stages"]:
            for storage in stage.get("storage", []):
                if storage["port"] == "ephemeral-filesystem":
                    self.assertFalse(storage["source_of_truth"])
        production_ports = {
            storage["port"]
            for stage in self.topology["stages"][1:]
            for storage in stage.get("storage", [])
            if storage["source_of_truth"]
        }
        self.assertEqual(
            production_ports,
            {"postgresql", "s3-compatible-object-storage"},
        )

    def test_every_service_split_gate_requires_evidence(self) -> None:
        gates = self.topology["split_gates"]
        self.assertGreaterEqual(len(gates), 5)
        self.assertEqual(len({gate["id"] for gate in gates}), len(gates))
        for gate in gates:
            self.assertTrue(gate["question"].endswith("?"))
            self.assertTrue(gate["evidence_required"])

    def test_primitive_schemas_are_parseable_and_versioned(self) -> None:
        for name in ("primitive-revision.v1.schema.json", "primitive-pack.v1.schema.json"):
            schema = json.loads((ROOT / "schemas" / name).read_text("utf-8"))
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertIn("1.0.0", json.dumps(schema))


if __name__ == "__main__":
    unittest.main()
