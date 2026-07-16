from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from taedri_codegraph.analyzers import PythonSyntaxAnalyzer
from taedri_codegraph.analyzers.python_syntax import UnsafeSourceTreeError


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


if __name__ == "__main__":
    unittest.main()
