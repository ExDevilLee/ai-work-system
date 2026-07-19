#!/usr/bin/env python3
"""Cross-platform regression tests for the experiment runner."""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from run_experiment import (
    has_unmeasured_mcp_tool_calls,
    resolve_codex_executable,
    run_utf8_command,
    tree_checksum,
)


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


class Utf8CommandTest(unittest.TestCase):
    def test_decodes_utf8_stdout_and_stderr(self) -> None:
        script = (
            "import sys; "
            "sys.stdout.buffer.write('标准输出'.encode('utf-8')); "
            "sys.stderr.buffer.write('错误输出'.encode('utf-8'))"
        )
        result = run_utf8_command([sys.executable, "-c", script])
        self.assertEqual(result.stdout, "标准输出")
        self.assertEqual(result.stderr, "错误输出")

    def test_forwards_multiline_utf8_stdin(self) -> None:
        prompt = "第一行：恢复当前任务\n第二行：查找稳定规则\n第三行：给出来源"
        script = "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"
        result = run_utf8_command(
            [sys.executable, "-c", script], input_text=prompt
        )
        self.assertEqual(result.stdout, prompt)


class WorkspaceMetricCoverageTest(unittest.TestCase):
    def test_marks_completed_mcp_calls_as_unmeasured(self) -> None:
        events = [
            {
                "type": "item.completed",
                "item": {"type": "mcp_tool_call", "status": "completed"},
            }
        ]
        self.assertTrue(has_unmeasured_mcp_tool_calls(events))

    def test_accepts_command_only_events(self) -> None:
        events = [
            {
                "type": "item.completed",
                "item": {"type": "command_execution", "exit_code": 0},
            }
        ]
        self.assertFalse(has_unmeasured_mcp_tool_calls(events))


if __name__ == "__main__":
    unittest.main()
