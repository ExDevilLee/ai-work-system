#!/usr/bin/env python3
"""Run one isolated memory-promotion session and preserve raw evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from validate_fixtures import validate


ROOT = Path(__file__).resolve().parent
CONDITIONS = ("direct-promotion", "rule-gated", "staged-human-gate")
MIN_FIXTURE_FRAGMENT_BYTES = 32
NODE_REPL_FILE_MARKERS = (
    "fs.",
    "glob",
    "path.join",
    "process.cwd",
    "readdir",
    "readfile",
    "readtextfile",
    "stat(",
)
RUNTIME_PATH_PATTERN = re.compile(
    r"((?:[A-Za-z]:[\\/]|/)[^\s\"']*[\\/]\.codex[\\/][^\s\"']+)"
)


def is_runtime_path(value: object) -> bool:
    normalized = str(value).replace("\\", "/")
    return "/.codex/" in normalized


def runtime_tool_access_count(events: Sequence[dict[str, object]]) -> int:
    """Count completed tool events that expose user-level Codex runtime paths."""
    return sum(
        1
        for event in events
        if event.get("type") == "item.completed"
        and isinstance(event.get("item"), dict)
        and event["item"].get("type") in {"command_execution", "mcp_tool_call"}
        and is_runtime_path(json.dumps(event["item"], ensure_ascii=False))
    )


def has_unmeasured_mcp_tool_calls(
    events: Sequence[dict[str, object]], fixture: Optional[Path] = None
) -> bool:
    if fixture is None:
        return any(
            event.get("type") == "item.completed"
            and isinstance(event.get("item"), dict)
            and event["item"].get("type") == "mcp_tool_call"
            for event in events
        )
    return any(
        classify_mcp_tool_call(event.get("item"), fixture)[0] == "unknown"
        for event in events
        if event.get("type") == "item.completed"
    )


def mcp_result_text(item: object) -> Optional[str]:
    if not isinstance(item, dict):
        return None
    result = item.get("result")
    if not isinstance(result, dict):
        return None
    content = result.get("content")
    if not isinstance(content, list):
        return None
    texts = [
        entry.get("text")
        for entry in content
        if isinstance(entry, dict) and isinstance(entry.get("text"), str)
    ]
    return "".join(texts) if texts else None


def structured_string_leaves(value: object) -> Iterable[str]:
    """Yield strings from JSON-shaped MCP output, including encoded JSON strings."""
    if isinstance(value, str):
        yield value
        try:
            decoded = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return
        if decoded != value:
            yield from structured_string_leaves(decoded)
    elif isinstance(value, dict):
        for child in value.values():
            yield from structured_string_leaves(child)
    elif isinstance(value, list):
        for child in value:
            yield from structured_string_leaves(child)


def fixture_texts(fixture: Optional[Path]) -> Iterable[str]:
    if fixture is None or not fixture.is_dir():
        return ()
    texts = []
    for path in fixture.rglob("*"):
        if not path.is_file():
            continue
        try:
            texts.append(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            continue
    return texts


def result_contains_fixture_content(
    result_candidates: Sequence[str], fixture_contents: Iterable[str]
) -> bool:
    for fixture_text in fixture_contents:
        if not fixture_text:
            continue
        for candidate in result_candidates:
            if fixture_text in candidate:
                return True
            fragment = candidate.strip()
            if (
                len(fragment.encode("utf-8")) >= MIN_FIXTURE_FRAGMENT_BYTES
                and fragment in fixture_text
            ):
                return True
            for start in range(len(fixture_text)):
                end = start
                fragment_bytes = 0
                while (
                    end < len(fixture_text)
                    and fragment_bytes < MIN_FIXTURE_FRAGMENT_BYTES
                ):
                    fragment_bytes += len(fixture_text[end].encode("utf-8"))
                    end += 1
                if (
                    fragment_bytes >= MIN_FIXTURE_FRAGMENT_BYTES
                    and fixture_text[start:end] in candidate
                ):
                    return True
    return False


def mcp_arguments_text(item: object) -> str:
    if not isinstance(item, dict):
        return ""
    arguments = item.get("arguments")
    if isinstance(arguments, dict):
        return json.dumps(arguments, ensure_ascii=False)
    return str(arguments or "")


def fixture_path_markers(fixture: Optional[Path]) -> set[str]:
    if fixture is None or not fixture.is_dir():
        return set()
    return {
        path.relative_to(fixture).as_posix()
        for path in fixture.rglob("*")
    }


def result_matches_fixture_paths(
    result_candidates: Sequence[str], fixture: Optional[Path]
) -> bool:
    markers = fixture_path_markers(fixture)
    file_paths = {marker for marker in markers if "/" in marker}
    if any(
        marker in candidate.replace("\\", "/")
        for marker in file_paths
        for candidate in result_candidates
    ):
        return True

    if fixture is None or not fixture.is_dir():
        return False
    directories = [fixture]
    directories.extend(path for path in fixture.rglob("*") if path.is_dir())
    for directory in directories:
        entries = [child.name for child in directory.iterdir()]
        if len(entries) < 2:
            continue
        if any(all(entry in candidate for entry in entries) for candidate in result_candidates):
            return True
    return False


def classify_mcp_tool_call(
    item: object, fixture: Optional[Path]
) -> tuple[str, Optional[int]]:
    """Classify MCP output without persisting tool arguments or absolute paths."""
    if not isinstance(item, dict):
        return "unknown", None
    server = item.get("server")
    tool = item.get("tool")
    if server == "codex" and tool in {
        "list_mcp_resources",
        "list_mcp_resource_templates",
    }:
        return "non_workspace", None

    result_text = mcp_result_text(item)
    result_candidates = tuple(structured_string_leaves(result_text or ""))
    if result_text and result_contains_fixture_content(
        result_candidates, fixture_texts(fixture)
    ):
        return "workspace", len(result_text.encode("utf-8"))
    if result_text and result_matches_fixture_paths(result_candidates, fixture):
        return "workspace", len(result_text.encode("utf-8"))

    # A node_repl call that does not mention a fixture path is treated as
    # external/non-workspace; a fixture reference without matching content is
    # incomplete because the returned representation cannot be measured safely.
    args_text = mcp_arguments_text(item).replace("\\", "/")
    markers = fixture_path_markers(fixture)
    has_file_operation = server == "node_repl" and any(
        marker in args_text.lower() for marker in NODE_REPL_FILE_MARKERS
    )
    if (
        result_text
        and has_file_operation
        and markers
        and any(marker in args_text for marker in markers)
    ):
        return "workspace", len(result_text.encode("utf-8"))
    if markers and any(marker in args_text for marker in markers):
        return "unknown", None
    if has_file_operation:
        return "unknown", None
    return "non_workspace", None


def mcp_workspace_metrics(
    events: Sequence[dict[str, object]], fixture: Path
) -> tuple[int, int, int]:
    workspace_calls = 0
    workspace_output_bytes = 0
    unmeasured_calls = 0
    for event in events:
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "mcp_tool_call":
            continue
        classification, output_bytes = classify_mcp_tool_call(item, fixture)
        if classification == "workspace" and output_bytes is not None:
            workspace_calls += 1
            workspace_output_bytes += output_bytes
        elif classification == "unknown":
            unmeasured_calls += 1
    return workspace_calls, workspace_output_bytes, unmeasured_calls


def tree_checksum(root: Path) -> str:
    digest = hashlib.sha256()
    files = (item for item in root.rglob("*") if item.is_file())
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def resident_instruction_bytes(fixture: Path) -> int:
    return len((fixture / "AGENTS.md").read_bytes())


def resolve_codex_executable() -> str:
    executable = shutil.which("codex")
    if executable is None:
        raise SystemExit("codex executable was not found on PATH")
    return executable


def run_utf8_command(
    command: Sequence[str], *, check: bool = False, input_text: Optional[str] = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        input=input_text,
    )


def command_output(*args: str) -> str:
    result = run_utf8_command(args, check=True)
    return result.stdout.strip()


def build_codex_command(
    codex_executable: str,
    workspace: Path,
    final_path: Path,
    *,
    model: Optional[str],
    reasoning_effort: Optional[str],
) -> list[str]:
    command = [
        codex_executable,
        "exec",
        "-C",
        str(workspace),
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--ephemeral",
        "--json",
        "--config",
        "features.plugins=false",
        "--output-last-message",
        str(final_path),
    ]
    if model:
        command.extend(["--model", model])
    if reasoning_effort:
        command.extend(
            ["--config", f'model_reasoning_effort="{reasoning_effort}"']
        )
    command.append("-")
    return command


def adjusted_mixed_workspace_bytes(item: dict[str, object]) -> Optional[int]:
    """Remove known global file prefixes from one mixed-scope command output."""
    command = str(item.get("command", ""))
    output = str(item.get("aggregated_output", ""))
    runtime_paths = list(dict.fromkeys(RUNTIME_PATH_PATTERN.findall(command)))
    if not runtime_paths:
        return None
    for raw_path in runtime_paths:
        path = Path(raw_path)
        if not path.is_file():
            return None
        prefix = path.read_text(encoding="utf-8")
        if not output.startswith(prefix):
            return None
        output = output[len(prefix) :]
    return len(output.encode("utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("condition", choices=CONDITIONS)
    parser.add_argument("--label", default="pilot-01")
    parser.add_argument("--fixture-set", default="pilot-01")
    parser.add_argument("--task", default="repeated-evidence")
    parser.add_argument("--model", help="Lock the model for formal repeated runs")
    parser.add_argument("--reasoning-effort", choices=("low", "medium", "high", "xhigh"))
    parser.add_argument(
        "--platform-tag",
        choices=("macos", "win11"),
        default="macos",
        help="Keep evidence separated by execution platform",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fixture_errors = validate()
    if fixture_errors:
        raise SystemExit("fixture validation failed:\n" + "\n".join(fixture_errors))
    if not args.label.startswith("pilot"):
        missing = [
            name
            for name, value in (
                ("--model", args.model),
                ("--reasoning-effort", args.reasoning_effort),
            )
            if not value
        ]
        if missing:
            raise SystemExit("formal runs must set " + ", ".join(missing))

    fixture_root = ROOT / "fixtures" / args.fixture_set
    common_fixture = fixture_root / "common"
    condition_fixture = fixture_root / "conditions" / args.condition
    prompt_path = ROOT / "prompts" / f"{args.task}.md"
    if not common_fixture.is_dir():
        raise SystemExit(f"common fixture directory does not exist: {common_fixture}")
    if not condition_fixture.is_dir():
        raise SystemExit(f"condition fixture directory does not exist: {condition_fixture}")
    if not prompt_path.is_file():
        raise SystemExit(f"prompt does not exist: {prompt_path}")

    codex_executable = resolve_codex_executable()
    started_at = datetime.now(timezone.utc)
    run_name = f"{args.label}-{args.task}-{args.condition}"
    run_dir = ROOT / "runs" / "private" / args.platform_tag / run_name

    if run_dir.exists():
        raise SystemExit(f"run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    fixture = run_dir / "fixture-snapshot"
    shutil.copytree(common_fixture, fixture)
    shutil.copytree(condition_fixture, fixture, dirs_exist_ok=True)
    shutil.copy2(prompt_path, run_dir / "prompt.md")

    with tempfile.TemporaryDirectory(prefix=f"promotion-poc-{args.condition}-") as temp:
        workspace = Path(temp) / "workspace"
        shutil.copytree(fixture, workspace)

        command = build_codex_command(
            codex_executable,
            workspace,
            run_dir / "final.md",
            model=args.model,
            reasoning_effort=args.reasoning_effort,
        )
        prompt_text = prompt_path.read_text(encoding="utf-8")

        started = time.monotonic()
        result = run_utf8_command(command, input_text=prompt_text)
        elapsed_seconds = round(time.monotonic() - started, 3)

    (run_dir / "raw.jsonl").write_text(result.stdout, encoding="utf-8")
    (run_dir / "stderr.log").write_text(result.stderr, encoding="utf-8")

    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    completed_commands = [
        event["item"]
        for event in events
        if event.get("type") == "item.completed"
        and event.get("item", {}).get("type") == "command_execution"
    ]
    fixture_markers = {
        path.relative_to(fixture).as_posix()
        for path in fixture.rglob("*")
        if path.is_file()
    }
    fixture_markers.update(path.name for path in fixture.rglob("*") if path.is_file())
    mixed_scope_commands = [
        item
        for item in completed_commands
        if is_runtime_path(item.get("command", ""))
        and any(marker in item.get("command", "") for marker in fixture_markers)
    ]
    workspace_commands = [
        item for item in completed_commands if not is_runtime_path(item.get("command", ""))
    ]
    mixed_adjustments = [
        adjusted_mixed_workspace_bytes(item) for item in mixed_scope_commands
    ]
    usage_events = [event["usage"] for event in events if event.get("type") == "turn.completed"]
    mcp_workspace_calls, mcp_workspace_bytes, unmeasured_mcp_tool_calls = (
        mcp_workspace_metrics(events, fixture)
    )
    runtime_access_calls = runtime_tool_access_count(events)
    workspace_metric_coverage_complete = unmeasured_mcp_tool_calls == 0

    metadata = {
        "run_name": run_name,
        "condition": args.condition,
        "fixture_set": args.fixture_set,
        "task": args.task,
        "purpose": (
            "protocol pilot"
            if args.label.startswith("pilot")
            else "model sensitivity"
            if args.label.startswith("model-")
            else "formal run"
        ),
        "started_at_utc": started_at.isoformat(),
        "platform": platform.platform(),
        "platform_tag": args.platform_tag,
        "python_version": platform.python_version(),
        "codex_version": command_output(codex_executable, "--version"),
        "requested_model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "model_record_status": "explicit" if args.model else "implicit default; model not emitted in JSONL",
        "fixture_sha256": tree_checksum(fixture),
        "prompt_sha256": hashlib.sha256(prompt_path.read_bytes()).hexdigest(),
        "sandbox": "read-only",
        "ephemeral": True,
        "plugins_enabled": False,
        "runtime_tool_access_calls": runtime_access_calls,
        "protocol_environment_isolated": runtime_access_calls == 0,
        "exit_code": result.returncode,
        "elapsed_seconds": elapsed_seconds,
        "usage": usage_events[-1] if usage_events else None,
        "completed_command_calls": len(completed_commands),
        "workspace_command_calls": (
            len(workspace_commands) + len(mixed_scope_commands) + mcp_workspace_calls
        ),
        "mixed_scope_command_calls": len(mixed_scope_commands),
        "workspace_mcp_tool_calls": mcp_workspace_calls,
        "workspace_mcp_output_bytes": mcp_workspace_bytes,
        "workspace_metric_coverage_complete": workspace_metric_coverage_complete,
        "workspace_metric_unmeasured_tool_calls": unmeasured_mcp_tool_calls,
        "workspace_output_bytes_reliable": workspace_metric_coverage_complete
        and all(value is not None for value in mixed_adjustments),
        "mixed_scope_adjusted_bytes": sum(
            value for value in mixed_adjustments if value is not None
        ),
        "workspace_output_bytes": sum(
            len(item.get("aggregated_output", "").encode("utf-8"))
            for item in workspace_commands
        )
        + sum(value for value in mixed_adjustments if value is not None)
        + mcp_workspace_bytes,
        "resident_instruction_bytes": resident_instruction_bytes(fixture),
        "command_shape": "codex exec -C <isolated-workspace> --skip-git-repo-check --sandbox read-only --ephemeral --json --config features.plugins=false --output-last-message <file> [--model <model>] [--config model_reasoning_effort=<effort>] -; prompt transport: UTF-8 stdin",
    }
    metadata["project_context_bytes_reliable"] = metadata[
        "workspace_output_bytes_reliable"
    ]
    metadata["project_context_bytes"] = (
        metadata["resident_instruction_bytes"] + metadata["workspace_output_bytes"]
        if metadata["project_context_bytes_reliable"]
        else None
    )
    (run_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    if result.returncode == 0 and runtime_access_calls:
        return 2
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
