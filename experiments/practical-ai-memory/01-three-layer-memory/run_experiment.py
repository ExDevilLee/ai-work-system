#!/usr/bin/env python3
"""Run an isolated Codex session and preserve the raw experiment evidence."""

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


ROOT = Path(__file__).resolve().parent
CONDITIONS = ("baseline", "layered")
RUNTIME_PATH_PATTERN = re.compile(
    r"((?:[A-Za-z]:[\\/]|/)[^\s\"']*[\\/]\.codex[\\/][^\s\"']+)"
)


def is_runtime_path(value: object) -> bool:
    normalized = str(value).replace("\\", "/")
    return "/.codex/" in normalized


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


def mcp_arguments_text(item: object) -> str:
    if not isinstance(item, dict):
        return ""
    arguments = item.get("arguments")
    if isinstance(arguments, dict):
        return json.dumps(arguments, ensure_ascii=False)
    return str(arguments or "")


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
    if result_text and any(
        text and text in result_text for text in fixture_texts(fixture)
    ):
        return "workspace", len(result_text.encode("utf-8"))

    # A node_repl call that does not mention a fixture path is treated as
    # external/non-workspace; a fixture reference without matching content is
    # incomplete because the returned representation cannot be measured safely.
    args_text = mcp_arguments_text(item).replace("\\", "/")
    markers = set()
    if fixture is not None and fixture.is_dir():
        markers = {
            path.relative_to(fixture).as_posix()
            for path in fixture.rglob("*")
            if path.is_file()
        }
    if markers and any(marker in args_text for marker in markers):
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
    parser.add_argument("--task", default="recovery-task")
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

    fixture_root = ROOT / "fixtures"
    if args.fixture_set != "pilot-01":
        fixture_root = fixture_root / args.fixture_set
    fixture = fixture_root / args.condition
    prompt_path = ROOT / "prompts" / f"{args.task}.md"
    if not fixture.is_dir():
        raise SystemExit(f"fixture directory does not exist: {fixture}")
    if not prompt_path.is_file():
        raise SystemExit(f"prompt does not exist: {prompt_path}")

    codex_executable = resolve_codex_executable()
    started_at = datetime.now(timezone.utc)
    run_name = f"{args.label}-{args.task}-{args.condition}"
    run_dir = ROOT / "runs" / "private" / args.platform_tag / run_name

    if run_dir.exists():
        raise SystemExit(f"run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    shutil.copytree(fixture, run_dir / "fixture-snapshot")
    shutil.copy2(prompt_path, run_dir / "prompt.md")

    with tempfile.TemporaryDirectory(prefix=f"memory-poc-{args.condition}-") as temp:
        workspace = Path(temp) / "workspace"
        shutil.copytree(fixture, workspace)

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
            "--output-last-message",
            str(run_dir / "final.md"),
        ]
        if args.model:
            command.extend(["--model", args.model])
        if args.reasoning_effort:
            command.extend(
                ["--config", f'model_reasoning_effort="{args.reasoning_effort}"']
            )
        prompt_text = prompt_path.read_text(encoding="utf-8")
        command.append("-")

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
        "command_shape": "codex exec -C <isolated-workspace> --skip-git-repo-check --sandbox read-only --ephemeral --json --output-last-message <file> [--model <model>] [--config model_reasoning_effort=<effort>] -; prompt transport: UTF-8 stdin",
    }
    (run_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
