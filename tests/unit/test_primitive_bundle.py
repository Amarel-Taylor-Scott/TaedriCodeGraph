from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from taedri_codegraph.primitive_capsules import CapsuleRole
from taedri_codegraph.primitives.bundle import (
    PrimitiveBundleError,
    load_primitive_directory,
)


class PrimitiveDirectoryBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = (
            Path(__file__).resolve().parents[2]
            / "examples/primitives/normalize-text"
        )

    def test_checked_in_bundle_declares_every_file_and_release_role(self) -> None:
        bundle = load_primitive_directory(self.source)
        self.assertEqual((bundle.namespace, bundle.name), ("taedri.core", "normalize-text"))
        self.assertEqual(len(bundle.files), 13)
        self.assertEqual({item.role for item in bundle.files}, set(CapsuleRole))

    def test_undeclared_content_is_rejected_instead_of_silently_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "primitive"
            shutil.copytree(self.source, target)
            (target / "unreviewed.py").write_text("raise SystemExit\n", "utf-8")
            with self.assertRaisesRegex(PrimitiveBundleError, "undeclared files"):
                load_primitive_directory(target)

    def test_symlinked_declared_source_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "primitive"
            shutil.copytree(self.source, target)
            source = target / "src/normalize.py"
            source.unlink()
            source.symlink_to(Path(temporary) / "outside.py")
            with self.assertRaisesRegex(PrimitiveBundleError, "missing or unsafe"):
                load_primitive_directory(target)


if __name__ == "__main__":
    unittest.main()
