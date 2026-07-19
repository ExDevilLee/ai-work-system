#!/usr/bin/env python3
"""Cross-platform regression tests for the experiment runner."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from run_experiment import (
    has_unmeasured_mcp_tool_calls,
    mcp_workspace_metrics,
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

    def test_counts_fixture_mcp_result_as_workspace_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = Path(temporary_directory)
            (fixture / "PROJECT_NOTES.md").write_text(
                "fixture notes\n", encoding="utf-8"
            )
            events = [
                {
                    "type": "item.completed",
                    "item": {
                        "type": "mcp_tool_call",
                        "server": "node_repl",
                        "tool": "js",
                        "arguments": {"code": "read PROJECT_NOTES.md"},
                        "result": {
                            "content": [{"type": "text", "text": "fixture notes\n"}]
                        },
                    },
                }
            ]
            self.assertEqual(mcp_workspace_metrics(events, fixture), (1, 14, 0))

    def test_counts_json_wrapped_multifile_mcp_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = Path(temporary_directory)
            first = "第一项：检查图片。\n第二项：检查链接。\n"
            second = "平台策略：先验证，再发布。\n"
            (fixture / "references").mkdir()
            (fixture / "references" / "checklist.md").write_text(
                first, encoding="utf-8"
            )
            (fixture / "references" / "policy.md").write_text(
                second, encoding="utf-8"
            )
            result_text = json.dumps(
                json.dumps(
                    {
                        "files": [
                            {"name": "checklist", "content": first},
                            {"name": "policy", "content": second},
                        ]
                    },
                    ensure_ascii=False,
                ),
                ensure_ascii=False,
            )
            events = [
                {
                    "type": "item.completed",
                    "item": {
                        "type": "mcp_tool_call",
                        "server": "node_repl",
                        "tool": "js",
                        "arguments": {
                            "code": "read(root + '/references/' + fileName)"
                        },
                        "result": {
                            "content": [{"type": "text", "text": result_text}]
                        },
                    },
                }
            ]

            self.assertEqual(
                mcp_workspace_metrics(events, fixture),
                (1, len(result_text.encode("utf-8")), 0),
            )


if __name__ == "__main__":
    unittest.main()
