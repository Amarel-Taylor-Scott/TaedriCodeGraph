from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from taedri_codegraph.sources import (
    PolyglotInventoryAnalyzer,
    SourceAdapterRegistry,
)


class PolyglotSourceTests(unittest.TestCase):
    def test_inventory_accepts_multiple_languages_without_kernel_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "api.ts").write_text("export function parseAddress(x: string) { return x }\n")
            (root / "core.rs").write_text("pub fn normalize(s: &str) -> &str { s }\n")
            (root / "ignored.bin").write_bytes(b"\x00\x01")
            bundle = PolyglotInventoryAnalyzer().analyze(root, package_name="polyglot")
        self.assertEqual(bundle.snapshot.language_key, "uceg.language.polyglot")
        self.assertEqual(len(bundle.files), 2)
        self.assertEqual(
            {entity.language_key for entity in bundle.entities.values() if entity.entity_kind_key == "uceg.entity.file"},
            {"uceg.language.typescript", "uceg.language.rust"},
        )

    def test_third_party_adapter_can_register_without_schema_migration(self) -> None:
        class Adapter:
            adapter_key = "example.source.scip"
            adapter_version = "1.0.0"

            def analyze(self, source: Path, *, package_name: str | None = None):
                raise NotImplementedError

        registry = SourceAdapterRegistry()
        registry.register(Adapter())
        self.assertIsInstance(registry.resolve("example.source.scip", "1.0.0"), Adapter)


if __name__ == "__main__":
    unittest.main()
