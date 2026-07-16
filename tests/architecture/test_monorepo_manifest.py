from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class MonorepoManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads((ROOT / "architecture" / "components.json").read_text("utf-8"))
        self.components = self.manifest["components"]
        self.by_id = {component["id"]: component for component in self.components}

    def test_component_ids_paths_and_dependencies_are_valid(self) -> None:
        self.assertEqual(len(self.by_id), len(self.components))
        for component in self.components:
            self.assertTrue((ROOT / component["path"]).exists(), component["path"])
            self.assertIn(
                component["status"],
                {"working", "partial", "conformance_only", "poc_only"},
            )
            for dependency in component["depends_on"]:
                self.assertIn(dependency, self.by_id)

    def test_component_graph_is_acyclic(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(component_id: str) -> None:
            if component_id in visited:
                return
            self.assertNotIn(component_id, visiting, f"component dependency cycle at {component_id}")
            visiting.add(component_id)
            for dependency in self.by_id[component_id]["depends_on"]:
                visit(dependency)
            visiting.remove(component_id)
            visited.add(component_id)

        for component_id in self.by_id:
            visit(component_id)

    def test_foundational_components_do_not_depend_on_outer_layers(self) -> None:
        forbidden_kinds = {"service", "integration", "application", "operations", "evaluation"}
        for component_id in ("shared-kernel", "shared-schemas"):
            for dependency in self.by_id[component_id]["depends_on"]:
                self.assertNotIn(self.by_id[dependency]["kind"], forbidden_kinds)


if __name__ == "__main__":
    unittest.main()
