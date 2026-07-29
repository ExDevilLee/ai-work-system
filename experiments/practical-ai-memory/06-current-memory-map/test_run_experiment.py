#!/usr/bin/env python3
"""Cross-platform regression tests for the experiment runner."""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from run_experiment import (
    adjusted_mixed_workspace_bytes,
    assemble_fixture,
    build_codex_command,
    classify_command_execution,
    command_audit_shape,
    classify_mcp_tool_call,
    command_output_bytes,
    ensure_contained_path,
    has_unmeasured_mcp_tool_calls,
    mcp_workspace_metrics,
    main,
    parse_args,
    resident_instruction_bytes,
    resolve_codex_executable,
    runtime_tool_access_count,
    run_utf8_command,
    tree_checksum,
    validate_path_identifier,
    write_minimal_codex_home,
)


class FixtureAssemblyTest(unittest.TestCase):
    def test_conditions_expose_only_the_frozen_navigation_view(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture_root = Path(temporary_directory) / "fixture"
            (fixture_root / "records").mkdir(parents=True)
            (fixture_root / "records" / "record.md").write_text(
                "synthetic record\n", encoding="utf-8"
            )
            (fixture_root / "generated").mkdir()
            (fixture_root / "generated" / "flat-index.md").write_text(
                "flat index\n", encoding="utf-8"
            )
            (fixture_root / "generated" / "state-projection.json").write_text(
                "{}\n", encoding="utf-8"
            )
            (fixture_root / "generated" / "state-table.json").write_text(
                "{}\n", encoding="utf-8"
            )
            (fixture_root / "generated" / "visual-map.json").write_text(
                "{}\n", encoding="utf-8"
            )
            for condition in ("source-only", "flat-index", "state-projection"):
                condition_root = fixture_root / "conditions" / condition
                condition_root.mkdir(parents=True)
                (condition_root / "AGENTS.md").write_text(
                    f"# {condition}\n", encoding="utf-8"
                )

            snapshots = {}
            for condition in ("source-only", "flat-index", "state-projection"):
                destination = Path(temporary_directory) / condition
                assemble_fixture(fixture_root, condition, destination)
                snapshots[condition] = {
                    path.relative_to(destination).as_posix()
                    for path in destination.rglob("*")
                    if path.is_file()
                }

            source_only_files = snapshots["source-only"]
            flat_index_files = snapshots["flat-index"]
            projection_files = snapshots["state-projection"]
            self.assertNotIn("generated/flat-index.md", source_only_files)
            self.assertNotIn("generated/state-projection.json", source_only_files)
            self.assertIn("generated/flat-index.md", flat_index_files)
            self.assertNotIn("generated/state-projection.json", flat_index_files)
            self.assertIn("generated/state-projection.json", projection_files)
            self.assertNotIn("generated/flat-index.md", projection_files)
            for files in snapshots.values():
                self.assertIn("records/record.md", files)
                self.assertIn("AGENTS.md", files)
                self.assertNotIn("manifest.json", files)
                self.assertNotIn("generated/state-table.json", files)
                self.assertNotIn("generated/visual-map.json", files)

    def test_rejects_unknown_condition_without_partial_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture_root = Path(temporary_directory) / "fixture"
            fixture_root.mkdir()
            destination = Path(temporary_directory) / "snapshot"
            with self.assertRaisesRegex(ValueError, "unsupported condition"):
                assemble_fixture(fixture_root, "unknown", destination)
            self.assertFalse(destination.exists())


class PathContainmentTest(unittest.TestCase):
    def test_rejects_unsafe_path_identifiers(self) -> None:
        for value in (
            "",
            "../pilot",
            "pilot/one",
            r"pilot\one",
            "/absolute",
            "C:\\absolute",
            "pilot one",
            " pilot",
            "pilot ",
            "pilot\nnext",
        ):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                validate_path_identifier(value)

    def test_accepts_frozen_identifier_shape(self) -> None:
        self.assertEqual(validate_path_identifier("pilot-01_v2"), "pilot-01_v2")

    def test_rejects_symlink_ancestor_and_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "root"
            external = Path(temporary_directory) / "external"
            root.mkdir()
            external.mkdir()
            (root / "linked").symlink_to(external, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                ensure_contained_path(root / "linked" / "item.md", root)
            with self.assertRaisesRegex(ValueError, "escapes"):
                ensure_contained_path(root.parent / "outside.md", root)

    def test_cli_rejects_fixture_and_label_escape(self) -> None:
        cases = (
            ["run_experiment.py", "../condition"],
            ["run_experiment.py", "source-only", "--fixture-set", "../pilot"],
            ["run_experiment.py", "source-only", "--label", "pilot/escape"],
            ["run_experiment.py", "source-only", "--task", "../prompt"],
        )
        for argv in cases:
            with self.subTest(argv=argv), patch.object(sys, "argv", argv):
                with self.assertRaises(SystemExit):
                    parse_args()


class MetadataPrivacyTest(unittest.TestCase):
    def test_emitted_metadata_has_no_provider_field(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fixture_root = root / "fixtures" / "pilot-01"
            (fixture_root / "records").mkdir(parents=True)
            (fixture_root / "records" / "record.md").write_text(
                "synthetic record\n", encoding="utf-8"
            )
            condition_root = fixture_root / "conditions" / "source-only"
            condition_root.mkdir(parents=True)
            (condition_root / "AGENTS.md").write_text(
                "# Synthetic instructions\n", encoding="utf-8"
            )
            (root / "prompts").mkdir()
            (root / "prompts" / "active-decision.md").write_text(
                "Answer the frozen task.\n", encoding="utf-8"
            )
            external = root / "outside.md"
            external.write_text("outside\n", encoding="utf-8")
            args = Namespace(
                condition="source-only",
                label="pilot-privacy",
                fixture_set="pilot-01",
                task="active-decision",
                model="synthetic-model",
                reasoning_effort="medium",
                platform_tag="macos",
            )

            def fake_codex_run(
                command: list[str], *, check: bool = False, input_text: str | None = None,
                cwd: Path | None = None,
                env: dict[str, str] | None = None,
            ) -> CompletedProcess[str]:
                self.assertIsNotNone(cwd)
                self.assertIsNotNone(env)
                output_path = Path(command[command.index("--output-last-message") + 1])
                output_path.write_text("synthetic answer\n", encoding="utf-8")
                stdout = "\n".join(
                    (
                        json.dumps(
                            {
                                "type": "item.completed",
                                "item": {
                                    "type": "command_execution",
                                    "command": (
                                        "cat records/record.md; "
                                        "python -c \"import os; "
                                        "open(os.path.join(os.getenv('HOME'), "
                                        "'outside.md'))\""
                                    ),
                                    "aggregated_output": "outside\n",
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "type": "turn.completed",
                                "usage": {"input_tokens": 1, "output_tokens": 1},
                            }
                        ),
                    )
                ) + "\n"
                return CompletedProcess(command, 0, stdout=stdout, stderr="")

            with (
                patch("run_experiment.ROOT", root),
                patch("run_experiment.parse_args", return_value=args),
                patch("run_experiment.validate", return_value=[]),
                patch("run_experiment.resolve_codex_executable", return_value="codex"),
                patch("run_experiment.command_output", return_value="codex-cli test"),
                patch("run_experiment.run_utf8_command", side_effect=fake_codex_run),
                patch("run_experiment.platform.system", return_value="Linux"),
                patch("run_experiment.write_minimal_codex_home"),
            ):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(main(), 2)

            metadata_path = (
                root
                / "runs/private/macos/pilot-privacy-active-decision-source-only"
                / "metadata.json"
            )
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertFalse(any("provider" in key.lower() for key in metadata))
            self.assertFalse(metadata["protocol_environment_isolated"])
            self.assertFalse(metadata["workspace_metric_coverage_complete"])
            self.assertFalse(metadata["workspace_output_bytes_reliable"])
            self.assertEqual(metadata["runtime_tool_access_calls"], 1)
            self.assertEqual(metadata["workspace_metric_unmeasured_tool_calls"], 1)
            self.assertNotIn(str(external), json.dumps(metadata))


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

    def test_counts_resident_instruction_utf8_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            content = "# Rules\n\n- 中文规则。\n"
            (root / "AGENTS.md").write_bytes(content.encode("utf-8"))

            self.assertEqual(
                resident_instruction_bytes(root), len(content.encode("utf-8"))
            )


class CodexExecutableTest(unittest.TestCase):
    @patch("run_experiment.shutil.which", return_value=r"C:\npm\codex.cmd")
    def test_resolves_platform_launcher_once(self, which: object) -> None:
        self.assertEqual(resolve_codex_executable(), r"C:\npm\codex.cmd")
        which.assert_called_once_with("codex")

    def test_build_command_disables_plugins(self) -> None:
        command = build_codex_command(
            "codex.cmd",
            Path("workspace"),
            Path("final.md"),
            model="gpt-5.6-sol",
            reasoning_effort="medium",
        )

        self.assertIn("features.plugins=false", command)
        self.assertIn("--ignore-rules", command)
        self.assertIn("mcp_servers={}", command)
        self.assertEqual(command[-1], "-")

    def test_minimal_codex_home_copies_only_allowed_connection_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / ".codex"
            source.mkdir()
            (source / "auth.json").write_text("{}\n", encoding="utf-8")
            (source / "config.toml").write_text(
                "model_provider = \"test\"\n"
                "[model_providers.test]\n"
                "name = \"custom\"\nwire_api = \"responses\"\n"
                "base_url = \"https://example.invalid\"\n"
                "requires_openai_auth = false\n"
                "[mcp_servers.unwanted]\ncommand = \"node\"\n",
                encoding="utf-8",
            )
            with patch("run_experiment.Path.home", return_value=root):
                home = root / "minimal"
                write_minimal_codex_home(home)
            text = (home / "config.toml").read_text(encoding="utf-8")
            self.assertIn("model_provider", text)
            self.assertNotIn("mcp_servers", text)
            self.assertTrue((home / "auth.json").is_file())
            if os.name != "nt":
                self.assertEqual((home / "auth.json").stat().st_mode & 0o777, 0o600)

    def test_minimal_codex_home_skips_unenforceable_posix_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / ".codex"
            source.mkdir()
            (source / "auth.json").write_text("{}\n", encoding="utf-8")
            (source / "config.toml").write_text(
                "model_provider = \"test\"\n"
                "[model_providers.test]\n"
                "name = \"custom\"\nwire_api = \"responses\"\n"
                "base_url = \"https://example.invalid\"\n"
                "requires_openai_auth = false\n",
                encoding="utf-8",
            )
            with (
                patch("run_experiment.Path.home", return_value=root),
                patch("run_experiment._supports_posix_file_modes", return_value=False),
                patch("run_experiment.os.chmod") as chmod,
            ):
                write_minimal_codex_home(root / "minimal")
            chmod.assert_not_called()


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
    def test_classifies_resource_enumeration_as_non_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = Path(temporary_directory)
            events = [
                {
                    "type": "item.completed",
                    "item": {
                        "type": "mcp_tool_call",
                        "server": "codex",
                        "tool": "list_mcp_resources",
                        "result": {"content": [{"type": "text", "text": "[]"}]},
                    },
                }
            ]

            self.assertEqual(mcp_workspace_metrics(events, fixture), (0, 0, 0))

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
            (fixture / "PROJECT_NOTES.md").write_bytes(b"fixture notes\n")
            events = [
                {
                    "type": "item.completed",
                    "item": {
                        "type": "mcp_tool_call",
                        "server": "node_repl",
                        "tool": "js",
                        "arguments": {"code": "fs.readFile('PROJECT_NOTES.md')"},
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
            (fixture / "references" / "checklist.md").write_bytes(
                first.encode("utf-8")
            )
            (fixture / "references" / "policy.md").write_bytes(
                second.encode("utf-8")
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
                            "code": (
                                "const root = process.cwd(); "
                                "fs.readFile(root + '/references/checklist.md'); "
                                "fs.readFile(root + '/references/policy.md')"
                            )
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

    def test_counts_partial_fixture_mcp_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = Path(temporary_directory)
            fixture_text = (
                "# 观察记录\n\n"
                "第一次发布检查发现导航链接失效。\n"
                "第二次独立检查再次发现同类问题。\n"
                "第三次检查确认修复前问题仍可复现。\n"
            )
            (fixture / "observation.md").write_text(
                fixture_text, encoding="utf-8"
            )
            fragment = "第二次独立检查再次发现同类问题。\n第三次检查确认修复前问题仍可复现。"
            result_text = json.dumps(
                {"content": fragment}, ensure_ascii=False
            )
            events = [
                {
                    "type": "item.completed",
                    "item": {
                        "type": "mcp_tool_call",
                        "server": "node_repl",
                        "tool": "js",
                        "arguments": {"code": "fs.readFile('observation.md')"},
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

    def test_counts_wrapped_fixture_fragment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = Path(temporary_directory)
            fixture_text = (
                "# 决策记录\n\n"
                "候选经验已经通过三次独立发布检查。\n"
                "批准范围仅限当前 Wiki 发布脚本。\n"
            )
            (fixture / "decision.md").write_text(
                fixture_text, encoding="utf-8"
            )
            result_text = (
                "Tool result:\n"
                "selected evidence follows\n"
                "候选经验已经通过三次独立发布检查。\n"
                "批准范围仅限当前 Wiki 发布脚本。\n"
                "end of result"
            )
            events = [
                {
                    "type": "item.completed",
                    "item": {
                        "type": "mcp_tool_call",
                        "server": "node_repl",
                        "tool": "js",
                        "arguments": {"code": "fs.readFile('decision.md')"},
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

    def test_counts_complete_fixture_directory_listing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = Path(temporary_directory)
            records = fixture / "records"
            records.mkdir()
            for index, name in enumerate(
                ("INDEX.md", "time-expiry.md", "explicit-supersession.md")
            ):
                (records / name).write_text(
                    f"synthetic body {index}", encoding="utf-8"
                )
            result_text = (
                "directory entries: INDEX.md, time-expiry.md, "
                "explicit-supersession.md"
            )
            events = [
                {
                    "type": "item.completed",
                    "item": {
                        "type": "mcp_tool_call",
                        "server": "node_repl",
                        "tool": "js",
                        "arguments": {"code": "fs.readdir('records')"},
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

    def test_counts_scoped_fixture_subdirectory_operation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = Path(temporary_directory)
            records = fixture / "records"
            records.mkdir()
            (records / "time-expiry.md").write_text(
                "synthetic lifecycle record", encoding="utf-8"
            )
            result_text = '["time-expiry.md"]'
            events = [
                {
                    "type": "item.completed",
                    "item": {
                        "type": "mcp_tool_call",
                        "server": "node_repl",
                        "tool": "js",
                        "arguments": {
                            "code": (
                                "fs.readdir('records').filter(name => "
                                "fs.readFile('records/' + name))"
                            )
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

    def test_does_not_count_short_fixture_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = Path(temporary_directory)
            (fixture / "observation.md").write_text(
                "状态：待验证观察。\n", encoding="utf-8"
            )
            events = [
                {
                    "type": "item.completed",
                    "item": {
                        "type": "mcp_tool_call",
                        "server": "node_repl",
                        "tool": "js",
                        "arguments": {"code": "format status"},
                        "result": {
                            "content": [{"type": "text", "text": "待验证观察"}]
                        },
                    },
                }
            ]

            self.assertEqual(mcp_workspace_metrics(events, fixture), (0, 0, 0))

    def test_marks_unmatched_node_repl_file_read_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = Path(temporary_directory)
            (fixture / "observation.md").write_text(
                "稳定且可追溯的夹具内容。\n", encoding="utf-8"
            )
            events = [
                {
                    "type": "item.completed",
                    "item": {
                        "type": "mcp_tool_call",
                        "server": "node_repl",
                        "tool": "js",
                        "arguments": {"code": "fs.readFile(unknownPath)"},
                        "result": {
                            "content": [{"type": "text", "text": "unmatched"}]
                        },
                    },
                }
            ]

            self.assertEqual(mcp_workspace_metrics(events, fixture), (0, 0, 1))

    def test_command_external_absolute_path_is_not_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workspace = root / "workspace"
            workspace.mkdir()
            external = root / "outside.md"
            external.write_text("outside", encoding="utf-8")
            item = {"type": "command_execution", "command": f'cat "{external}"'}

            self.assertEqual(classify_command_execution(item, workspace), "external")

    def test_command_relative_read_is_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            (workspace / "records").mkdir(parents=True)
            item = {"type": "command_execution", "command": "cat records/item.md"}

            self.assertEqual(classify_command_execution(item, workspace), "workspace")

    def test_read_only_zsh_wrapper_preserves_workspace_classification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            (workspace / "records").mkdir(parents=True)
            wrapped = {"type": "command_execution", "command": "/bin/zsh -lc 'cat records/item.md'"}
            chained = {"type": "command_execution", "command": "/bin/zsh -lc 'cat records/item.md; pwd'"}

            self.assertEqual(classify_command_execution(wrapped, workspace), "workspace")
            self.assertEqual(classify_command_execution(chained, workspace), "external")
            self.assertEqual(
                command_audit_shape(wrapped, workspace), "shell-wrapper-cat:workspace"
            )
            self.assertEqual(command_audit_shape(chained, workspace), "shell-chain:external")

    def test_zsh_wrapper_allows_quoted_rg_pattern_alternatives_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            (workspace / "records").mkdir(parents=True)
            quoted_pattern = {
                "type": "command_execution",
                "command": "/bin/zsh -lc 'rg -g \"*.md\" \"active|pending\" records'",
            }
            pipeline = {
                "type": "command_execution",
                "command": "/bin/zsh -lc 'rg pattern records | head -n 1'",
            }

            self.assertEqual(
                classify_command_execution(quoted_pattern, workspace), "workspace"
            )
            self.assertEqual(
                command_audit_shape(quoted_pattern, workspace),
                "shell-wrapper-rg:workspace",
            )
            self.assertEqual(classify_command_execution(pipeline, workspace), "external")
            self.assertEqual(command_audit_shape(pipeline, workspace), "shell-chain:external")

    def test_rg_listing_with_case_insensitive_filter_is_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            (workspace / "records").mkdir(parents=True)
            item = {
                "type": "command_execution",
                "command": "/bin/zsh -lc 'rg -l -i \"superseded\" records'",
            }

            self.assertEqual(classify_command_execution(item, workspace), "workspace")
            self.assertEqual(
                command_audit_shape(item, workspace), "shell-wrapper-rg:workspace"
            )

    def test_simple_cross_platform_relative_reads_are_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            (workspace / "records").mkdir(parents=True)
            for command in (
                "type records/item.md",
                "Get-Content records/item.md",
            ):
                with self.subTest(command=command):
                    item = {"type": "command_execution", "command": command}
                    self.assertEqual(
                        classify_command_execution(item, workspace), "workspace"
                    )

    def test_powershell_provider_paths_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            workspace.mkdir()
            commands = (
                "Get-ChildItem Env:",
                "Get-Content Env:HOME",
                "Get-Content Variable:HOME",
                r"Get-ChildItem HKCU:\Software",
                r"Get-Content Cert:\CurrentUser\My",
            )
            events = []
            for command in commands:
                with self.subTest(command=command):
                    item = {"type": "command_execution", "command": command}
                    self.assertEqual(
                        classify_command_execution(item, workspace), "external"
                    )
                    events.append({"type": "item.completed", "item": item})
            self.assertEqual(
                runtime_tool_access_count(events, workspace, workspace),
                len(commands),
            )

    def test_powershell_drive_paths_use_windows_containment(self) -> None:
        workspace = Path(r"C:\workspace")
        inside = {
            "type": "command_execution",
            "command": r"Get-Content C:\workspace\records\item.md",
        }
        outside = {
            "type": "command_execution",
            "command": r"Get-Content C:\outside\item.md",
        }
        relative = {
            "type": "command_execution",
            "command": r"Get-ChildItem -Recurse -File records",
        }

        self.assertEqual(classify_command_execution(inside, workspace), "workspace")
        self.assertEqual(classify_command_execution(outside, workspace), "external")
        self.assertEqual(classify_command_execution(relative, workspace), "workspace")

    def test_proven_read_only_discovery_commands_are_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            (workspace / "records").mkdir(parents=True)
            commands = (
                "rg --files .",
                "rg --files",
                "rg pattern",
                "rg 'active|pending' records",
                "rg pattern records",
                "rg -g '*.md' pattern records generated",
                "find records -type f",
                "sed -n 1,40p records/item.md",
                "Get-ChildItem -Recurse -File records",
            )
            for command in commands:
                with self.subTest(command=command):
                    item = {"type": "command_execution", "command": command}
                    self.assertEqual(
                        classify_command_execution(item, workspace), "workspace"
                    )

    def test_discovery_command_bytes_use_actual_tool_output(self) -> None:
        output = "records/alpha.md\nrecords/中文.md\n"
        item = {
            "type": "command_execution",
            "command": "rg --files .",
            "aggregated_output": output,
        }

        self.assertEqual(command_output_bytes(item), len(output.encode("utf-8")))

    def test_non_file_command_remains_non_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            workspace.mkdir()
            item = {"type": "command_execution", "command": "pwd"}

            self.assertEqual(
                classify_command_execution(item, workspace), "non_workspace"
            )

    def test_nested_interpreter_environment_read_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            (workspace / "records").mkdir(parents=True)
            item = {
                "type": "command_execution",
                "command": (
                    "cat records/alpha.md; "
                    "python -c \"import os; "
                    "open(os.path.join(os.getenv('HOME'),'outside.md'))\""
                ),
            }

            self.assertEqual(
                classify_command_execution(item, workspace), "unknown"
            )

    def test_dynamic_or_nested_command_targets_are_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            workspace.mkdir()
            commands = (
                "cat $HOME/outside.md",
                "cat $(pwd)/records/item.md",
                "node -e \"require('fs').readFileSync('records/item.md')\"",
                "rg pattern $HOME",
                "find $(pwd) -type f",
                "sed -n 1,40p $USERPROFILE/outside.md",
                "Get-ChildItem -Recurse -File $env:USERPROFILE",
            )
            for command in commands:
                with self.subTest(command=command):
                    item = {"type": "command_execution", "command": command}
                    self.assertEqual(
                        classify_command_execution(item, workspace), "unknown"
                    )

    def test_command_mixed_workspace_and_external_read_is_external(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workspace = root / "workspace"
            workspace.mkdir()
            external = root / "outside.md"
            for command in (
                f'cat records/item.md "{external}"',
                f'rg pattern records "{external}"',
            ):
                with self.subTest(command=command):
                    item = {"type": "command_execution", "command": command}
                    self.assertEqual(
                        classify_command_execution(item, workspace), "external"
                    )

    def test_mcp_mixed_workspace_and_external_read_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workspace = root / "workspace"
            fixture = workspace
            (fixture / "records").mkdir(parents=True)
            body = "frozen fixture body with enough bytes for matching\n"
            (fixture / "records/item.md").write_text(body, encoding="utf-8")
            external = root / "outside.md"
            external.write_text("outside", encoding="utf-8")
            item = {
                "type": "mcp_tool_call",
                "server": "node_repl",
                "tool": "js",
                "arguments": {
                    "code": (
                        "fs.readFile('records/item.md'); "
                        f"fs.readFile('{external.as_posix()}')"
                    )
                },
                "result": {"content": [{"type": "text", "text": body}]},
            }

            self.assertEqual(
                classify_mcp_tool_call(item, fixture, workspace),
                ("external", None),
            )

    def test_unknown_mcp_tool_with_external_path_is_external(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workspace = root / "workspace"
            workspace.mkdir()
            external = root / "outside.md"
            item = {
                "type": "mcp_tool_call",
                "server": "unrecognized",
                "tool": "custom",
                "arguments": {"target": external.as_posix()},
                "result": {"content": [{"type": "text", "text": "outside"}]},
            }

            self.assertEqual(
                classify_mcp_tool_call(item, workspace, workspace),
                ("external", None),
            )

    def test_mcp_safe_read_plus_unbound_target_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            (workspace / "records").mkdir(parents=True)
            body = "frozen fixture body with enough bytes for matching\n"
            (workspace / "records/item.md").write_text(body, encoding="utf-8")
            item = {
                "type": "mcp_tool_call",
                "server": "node_repl",
                "tool": "js",
                "arguments": {
                    "code": (
                        "fs.readFile('records/item.md'); "
                        "fs.readFile(unknownTarget)"
                    )
                },
                "result": {"content": [{"type": "text", "text": body}]},
            }

            self.assertEqual(
                classify_mcp_tool_call(item, workspace, workspace),
                ("unknown", None),
            )

    def test_mcp_safe_read_plus_environment_target_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            (workspace / "records").mkdir(parents=True)
            body = "frozen fixture body with enough bytes for matching\n"
            (workspace / "records/item.md").write_text(body, encoding="utf-8")
            item = {
                "type": "mcp_tool_call",
                "server": "node_repl",
                "tool": "js",
                "arguments": {
                    "code": (
                        "fs.readFile('records/item.md'); "
                        "fs.readFile(process.env.HOME + '/outside.md')"
                    )
                },
                "result": {"content": [{"type": "text", "text": body}]},
            }

            self.assertEqual(
                classify_mcp_tool_call(item, workspace, workspace),
                ("unknown", None),
            )

    def test_mcp_literal_path_join_and_sync_read_are_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            (workspace / "records").mkdir(parents=True)
            output = "fixture result 中文\n"
            for code in (
                "fs.readFileSync('records/item.md')",
                "fs.readFileSync(path.join('records', 'item.md'))",
            ):
                with self.subTest(code=code):
                    item = {
                        "type": "mcp_tool_call",
                        "server": "node_repl",
                        "tool": "js",
                        "arguments": {"code": code},
                        "result": {
                            "content": [{"type": "text", "text": output}]
                        },
                    }
                    self.assertEqual(
                        classify_mcp_tool_call(item, workspace, workspace),
                        ("workspace", len(output.encode("utf-8"))),
                    )

    def test_mcp_dynamic_path_join_remains_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            (workspace / "records").mkdir(parents=True)
            for code in (
                "fs.readFile(path.join('records', selectedName))",
                "fs.readFile('records/' + selectedName)",
                "fs.readFileSync(path.join(process.env.HOME, 'outside.md'))",
            ):
                with self.subTest(code=code):
                    item = {
                        "type": "mcp_tool_call",
                        "server": "node_repl",
                        "tool": "js",
                        "arguments": {"code": code},
                        "result": {
                            "content": [{"type": "text", "text": "untrusted"}]
                        },
                    }
                    self.assertEqual(
                        classify_mcp_tool_call(item, workspace, workspace),
                        ("unknown", None),
                    )

    def test_mcp_relative_read_is_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            (workspace / "records").mkdir(parents=True)
            body = "frozen fixture body with enough bytes for matching\n"
            (workspace / "records/item.md").write_text(body, encoding="utf-8")
            item = {
                "type": "mcp_tool_call",
                "server": "node_repl",
                "tool": "js",
                "arguments": {"code": "fs.readFile('records/item.md')"},
                "result": {"content": [{"type": "text", "text": body}]},
            }

            self.assertEqual(
                classify_mcp_tool_call(item, workspace, workspace),
                ("workspace", len(body.encode("utf-8"))),
            )

    def test_runtime_audit_rejects_external_and_accepts_relative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workspace = root / "workspace"
            workspace.mkdir()
            external = root / "outside.md"
            events = [
                {
                    "type": "item.completed",
                    "item": {
                        "type": "command_execution",
                        "command": f'cat "{external}"',
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "type": "command_execution",
                        "command": "cat records/item.md",
                    },
                },
            ]

            self.assertEqual(runtime_tool_access_count(events, workspace, workspace), 1)


class ReliableOutputBytesTest(unittest.TestCase):
    def test_removes_exact_runtime_prefix_from_mixed_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            runtime_file = Path(temporary_directory) / ".codex" / "rules.md"
            runtime_file.parent.mkdir()
            runtime_file.write_text("global prefix\n", encoding="utf-8")
            workspace_output = "工作区输出\n"
            item = {
                "command": f'cat "{runtime_file}" records/item.md',
                "aggregated_output": "global prefix\n" + workspace_output,
            }

            self.assertEqual(
                adjusted_mixed_workspace_bytes(item),
                len(workspace_output.encode("utf-8")),
            )

    def test_rejects_mixed_output_when_runtime_prefix_does_not_match(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            runtime_file = Path(temporary_directory) / ".codex" / "rules.md"
            runtime_file.parent.mkdir()
            runtime_file.write_text("expected prefix\n", encoding="utf-8")
            item = {
                "command": f'cat "{runtime_file}" records/item.md',
                "aggregated_output": "different output\n",
            }

            self.assertIsNone(adjusted_mixed_workspace_bytes(item))


if __name__ == "__main__":
    unittest.main()
