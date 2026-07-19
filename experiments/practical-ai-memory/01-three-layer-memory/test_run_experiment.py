#!/usr/bin/env python3
"""Cross-platform regression tests for the experiment runner."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from run_experiment import resolve_codex_executable, tree_checksum


class TreeChecksumTest(unittest.TestCase):
    def test_uses_posix_relative_path_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            files = {
                "references/INDEX.md": b"index\n",
                "references/checklist.md": b"checklist\n",
                "memory/CURRENT.md": b"current\n",
            }
            for relative_path, content in files.items():
                path = root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)

            expected = hashlib.sha256()
            for relative_path in sorted(files):
                expected.update(relative_path.encode("utf-8"))
                expected.update(b"\0")
                expected.update(files[relative_path])
                expected.update(b"\0")

            self.assertEqual(tree_checksum(root), expected.hexdigest())


class CodexExecutableTest(unittest.TestCase):
    @patch("run_experiment.shutil.which", return_value=r"C:\npm\codex.cmd")
    def test_resolves_platform_launcher_once(self, which: object) -> None:
        self.assertEqual(resolve_codex_executable(), r"C:\npm\codex.cmd")
        which.assert_called_once_with("codex")


if __name__ == "__main__":
    unittest.main()
