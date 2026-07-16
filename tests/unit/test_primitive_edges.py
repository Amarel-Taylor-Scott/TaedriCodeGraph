from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from taedri_codegraph.canonical import sha256_digest
from taedri_codegraph.primitive_capsules import CapsuleRole
from taedri_codegraph.primitives.bundle import inspect_primitive_directory
from taedri_codegraph.primitives.edges import (
    PrimitiveGraphError,
    validate_primitive_graph,
)


ROOT = Path(__file__).resolve().parents[2]


class PrimitiveInterfaceGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inspected = inspect_primitive_directory(
            ROOT / "examples/primitives/normalize-text"
        )
        self.files = {item.path: item for item in self.inspected.bundle.files}
        self.capsule_paths = {
            path: (item.content, sha256_digest(item.content))
            for path, item in self.files.items()
        }
        self.graph = json.loads(self.files["graph.json"].content)
        self.contract = json.loads(self.files["contract.json"].content)
        self.runtime = json.loads(self.files["runtime.json"].content)

    def validate(self, graph, *, contract_path="contract.json", capsule_paths=None):
        return validate_primitive_graph(
            graph,
            capsule_paths=capsule_paths or self.capsule_paths,
            contract=self.contract,
            contract_path=contract_path,
            language=self.runtime["language"],
            runtime_version=self.runtime["runtime_version"],
            entrypoint_path=self.runtime["entrypoint_path"],
            entrypoint=self.runtime["entrypoint"],
        )

    def test_real_interface_has_evidence_edges_ports_groups_and_dimensions(self) -> None:
        interface = self.inspected.artifacts.interface
        self.assertEqual(interface.edge_count, 6)
        self.assertEqual(len(interface.input_ports), 1)
        self.assertEqual(len(interface.output_ports), 1)
        self.assertEqual(len(interface.groups), 1)
        self.assertEqual(interface.purity, "pure")
        self.assertTrue(interface.deterministic)
        self.assertIn("taedri.compatibility.call_style", interface.required_dimensions)

    def test_stale_edge_evidence_digest_fails_closed(self) -> None:
        graph = copy.deepcopy(self.graph)
        graph["edges"][0]["evidence"][0]["digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(PrimitiveGraphError, "evidence digest"):
            self.validate(graph)

    def test_contract_port_references_follow_the_declared_capsule_path(self) -> None:
        graph = copy.deepcopy(self.graph)
        replacement = "specs/contract.v1.json"
        for node in graph["nodes"]:
            if node["path"] == "contract.json":
                node["path"] = replacement
        for port in graph["ports"]:
            port["schema_ref"] = port["schema_ref"].replace(
                "contract.json", replacement
            )
        for edge in graph["edges"]:
            for evidence in edge["evidence"]:
                if evidence["path"] == "contract.json":
                    evidence["path"] = replacement
        for group in graph["groups"]:
            for evidence in group["evidence"]:
                if evidence["path"] == "contract.json":
                    evidence["path"] = replacement
        capsule_paths = dict(self.capsule_paths)
        capsule_paths[replacement] = capsule_paths.pop("contract.json")
        interface = self.validate(
            graph,
            contract_path=replacement,
            capsule_paths=capsule_paths,
        )
        self.assertEqual(interface.input_ports[0].schema_ref, f"{replacement}#/inputs/0/schema")

    def test_unbound_contract_port_and_dangling_endpoint_fail_closed(self) -> None:
        missing_port = copy.deepcopy(self.graph)
        missing_port["ports"] = missing_port["ports"][1:]
        with self.assertRaisesRegex(PrimitiveGraphError, "every contract input"):
            self.validate(missing_port)
        dangling = copy.deepcopy(self.graph)
        dangling["edges"][0]["target"] = "contract.missing"
        with self.assertRaisesRegex(PrimitiveGraphError, "endpoints"):
            self.validate(dangling)


if __name__ == "__main__":
    unittest.main()
