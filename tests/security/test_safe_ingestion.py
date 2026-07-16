from __future__ import annotations

import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from taedri_codegraph.analyzers import PythonSyntaxAnalyzer
from taedri_codegraph.analyzers.python_syntax import UnsafeSourceTreeError
from taedri_codegraph.artifacts import UnsafeArtifactError, inspect_wheel


class SafeIngestionTests(unittest.TestCase):
    def test_target_module_is_never_executed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sentinel = root / "executed.txt"
            (root / "malicious.py").write_text(
                "from pathlib import Path\n"
                f"Path({str(sentinel)!r}).write_text('executed')\n"
                "raise RuntimeError('must not execute')\n",
                encoding="utf-8",
            )
            bundle = PythonSyntaxAnalyzer().analyze(root, package_name="malicious")
            self.assertFalse(sentinel.exists())
            self.assertGreater(len(bundle.entities), 0)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlinked_python_file_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside.txt"
            outside.write_text("value = 1\n", encoding="utf-8")
            os.symlink(outside, root / "linked.py")
            with self.assertRaises(UnsafeSourceTreeError):
                PythonSyntaxAnalyzer().analyze(root, package_name="linked")

    def test_wheel_path_traversal_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "poison-1.0-py3-none-any.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("../escape.py", "value = 1\n")
            with self.assertRaises(UnsafeArtifactError):
                inspect_wheel(wheel)

    def test_wheel_record_hash_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "poison-1.0-py3-none-any.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("poison.py", "value = 1\n")
                archive.writestr(
                    "poison-1.0.dist-info/METADATA",
                    "Metadata-Version: 2.4\nName: poison\nVersion: 1.0\n",
                )
                archive.writestr(
                    "poison-1.0.dist-info/RECORD",
                    "poison.py,sha256=definitely-wrong,10\n"
                    "poison-1.0.dist-info/METADATA,,\n"
                    "poison-1.0.dist-info/RECORD,,\n",
                )
            with self.assertRaises(UnsafeArtifactError):
                inspect_wheel(wheel)


if __name__ == "__main__":
    unittest.main()
