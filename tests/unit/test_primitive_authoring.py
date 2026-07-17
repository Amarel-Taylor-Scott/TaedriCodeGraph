from __future__ import annotations

import dataclasses
import tempfile
import unittest
from pathlib import Path

from taedri_codegraph.primitive_capsules import CapsuleRole
from taedri_codegraph.primitives.authoring import (
    PrimitiveAuthoringError,
    build_primitive_files,
    render_primitive_directory,
)
from tools.generate_data_primitive_capsules import COHORT, check, generate


ROOT = Path(__file__).resolve().parents[2]


class PrimitiveAuthoringTests(unittest.TestCase):
    def test_checked_in_data_cohort_is_exactly_reproducible(self) -> None:
        self.assertEqual(len(COHORT), 21)
        for spec in COHORT:
            expected = build_primitive_files(spec)
            directory = ROOT / "examples/primitives" / spec.category / spec.name
            actual_paths = {
                path.relative_to(directory).as_posix()
                for path in directory.rglob("*")
                if path.is_file()
            }
            self.assertEqual(actual_paths, set(expected), spec.name)
            for relative, content in expected.items():
                self.assertEqual((directory / relative).read_bytes(), content, relative)

    def test_compiler_emits_every_role_and_passes_independent_inspection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            inspected = render_primitive_directory(COHORT[0], Path(temporary) / "primitive")
        self.assertEqual(len(inspected.bundle.files), 13)
        self.assertEqual({item.role for item in inspected.bundle.files}, set(CapsuleRole))
        self.assertEqual(inspected.artifacts.interface.edge_count, 6)
        self.assertEqual(len(inspected.artifacts.interface.ports), 2)

    def test_placeholder_forms_are_rejected_before_files_exist(self) -> None:
        sources = (
            "def collapse_whitespace(value):\n    pass\n",
            "def collapse_whitespace(value):\n    ...\n",
            "def collapse_whitespace(value):\n    raise NotImplementedError\n",
            "def collapse_whitespace(value):\n    raise NotImplementedError()\n",
            "def collapse_whitespace(value):\n    return 'TODO'\n",
        )
        for source in sources:
            with self.subTest(source=source):
                spec = dataclasses.replace(COHORT[0], source_code=source)
                with self.assertRaises(PrimitiveAuthoringError):
                    build_primitive_files(spec)

    def test_generator_check_detects_byte_drift_without_rewriting_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "primitives"
            generated = generate(destination)
            checked = check(destination)
            self.assertEqual(generated, checked)
            source = (
                destination
                / COHORT[0].category
                / COHORT[0].name
                / COHORT[0].source_path
            )
            source.write_bytes(source.read_bytes() + b"\n")
            with self.assertRaisesRegex(
                PrimitiveAuthoringError, "generated primitive content drift"
            ):
                check(destination)
            self.assertTrue(source.read_bytes().endswith(b"\n\n"))


if __name__ == "__main__":
    unittest.main()
