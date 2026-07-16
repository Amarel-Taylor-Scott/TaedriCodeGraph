from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from taedri_codegraph.analyzers import PythonSyntaxAnalyzer
from taedri_codegraph.contracts import CompletenessState, EvidenceLevel

from tests.helpers import GOLDEN


class PythonGoldenCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.analyzer = PythonSyntaxAnalyzer()
        cls.bundle = cls.analyzer.analyze(GOLDEN, package_name="pkg", release="1.0.0")

    def entities(self, native_name: str):
        return [
            entity
            for entity in self.bundle.entities.values()
            if entity.native_name == native_name
        ]

    def test_declared_entities_and_binding_forms_are_inventoryed(self) -> None:
        for name in (
            "Widget",
            "helper",
            "scale",
            "self",
            "factor",
            "MODULE_VALUE",
            "item",
            "error",
            "captured",
            "rest",
            "normalized",
            "handle",
            "name",
        ):
            self.assertTrue(self.entities(name), name)
        self.assertTrue(
            any(
                entity.entity_kind_key == "uceg.entity.python.lambda"
                for entity in self.bundle.entities.values()
            )
        )

    def test_instance_field_is_separate_sidecar_entity(self) -> None:
        name_entities = self.entities("name")
        kinds = {entity.entity_kind_key for entity in name_entities}
        self.assertIn("uceg.entity.python.parameter", kinds)
        self.assertIn("uceg.entity.python.instance_field", kinds)

    def test_import_and_call_edges_are_first_class_and_evidenced(self) -> None:
        imports = [
            edge for edge in self.bundle.relations.values()
            if edge.predicate_key == "uceg.predicate.imports"
        ]
        calls = [
            edge for edge in self.bundle.relations.values()
            if edge.predicate_key == "uceg.predicate.calls_may"
        ]
        self.assertGreaterEqual(len(imports), 3)
        self.assertGreaterEqual(len(calls), 6)
        for edge in [*imports, *calls]:
            self.assertTrue(edge.evidence_ids)
            self.assertTrue(all(item in self.bundle.evidence for item in edge.evidence_ids))

    def test_unresolved_targets_remain_candidates(self) -> None:
        client = [
            entity
            for entity in self.bundle.entities.values()
            if entity.qualified_name == "client.get"
        ]
        self.assertTrue(client)
        self.assertTrue(all(item.lifecycle is EvidenceLevel.CANDIDATE for item in client))

    def test_occurrence_byte_ranges_are_valid_utf8_slices(self) -> None:
        files = self.bundle.files
        for occurrence in self.bundle.occurrences.values():
            record = files[occurrence.source_file_id]
            self.assertEqual(occurrence.file_content_id, record.content_identity.id)
            content = self.bundle.source_blobs[record.content_digest]
            start, end = occurrence.byte_range
            self.assertLessEqual(start, end)
            content[start:end].decode("utf-8")

    def test_coverage_states_supported_syntax_explicitly(self) -> None:
        ledger = next(iter(self.bundle.coverage.values()))
        self.assertEqual(
            ledger.completeness_state,
            CompletenessState.COMPLETE_FOR_DECLARED_SYNTAX,
        )
        self.assertEqual(ledger.attempted_inputs, 2)
        self.assertEqual(ledger.successful_inputs, 2)

    def test_same_bytes_in_different_directories_have_same_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            for root in (Path(first), Path(second)):
                (root / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
            one = self.analyzer.analyze(first, package_name="same", release="1")
            two = self.analyzer.analyze(second, package_name="same", release="1")
            self.assertEqual(one.snapshot.identity.id, two.snapshot.identity.id)
            self.assertEqual(set(one.entities), set(two.entities))
            self.assertEqual(set(one.relations), set(two.relations))

    def test_distinct_paths_with_identical_bytes_are_not_collapsed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = "VALUE = 1\n"
            (root / "first.py").write_text(content, encoding="utf-8")
            (root / "second.py").write_text(content, encoding="utf-8")
            bundle = self.analyzer.analyze(root, package_name="duplicates")
            self.assertEqual(len(bundle.files), 2)
            source_ids = {record.identity.id for record in bundle.files.values()}
            content_ids = {
                record.content_identity.id for record in bundle.files.values()
            }
            self.assertEqual(len(source_ids), 2)
            self.assertEqual(len(content_ids), 1)
            ledger = next(iter(bundle.coverage.values()))
            self.assertEqual(ledger.attempted_inputs, 2)
            self.assertEqual(ledger.successful_inputs, 2)

    def test_parse_gaps_are_visible_not_silent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "good.py").write_text("value = 1\n", encoding="utf-8")
            (root / "bad.py").write_text("def broken(:\n", encoding="utf-8")
            bundle = self.analyzer.analyze(root, package_name="partial")
            ledger = next(iter(bundle.coverage.values()))
            self.assertEqual(ledger.completeness_state, CompletenessState.ATTEMPTED_PARTIAL)
            self.assertEqual(ledger.unresolved_inputs, 1)
            self.assertIn("bad.py:SyntaxError", ledger.unsupported_constructs)


if __name__ == "__main__":
    unittest.main()
