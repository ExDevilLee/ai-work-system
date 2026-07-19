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
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parent
CONDITIONS = ("baseline", "layered")
RUNTIME_PATH_PATTERN = re.compile(
    r"((?:[A-Za-z]:[\\/]|/)[^\s\"']*[\\/]\.codex[\\/][^\s\"']+)"
)


def is_runtime_path(value: object) -> bool:
    normalized = str(value).replace("\\", "/")
    return "/.codex/" in normalized


def tree_checksum(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def command_output(*args: str) -> str:
    result = subprocess.run(args, check=True, capture_output=True, text=True)
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
            "codex",
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
        command.append(prompt_path.read_text(encoding="utf-8"))

        started = time.monotonic()
        result = subprocess.run(command, capture_output=True, text=True)
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
        "codex_version": command_output("codex", "--version"),
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
        "workspace_command_calls": len(workspace_commands) + len(mixed_scope_commands),
        "mixed_scope_command_calls": len(mixed_scope_commands),
        "workspace_output_bytes_reliable": all(
            value is not None for value in mixed_adjustments
        ),
        "mixed_scope_adjusted_bytes": sum(
            value for value in mixed_adjustments if value is not None
        ),
        "workspace_output_bytes": sum(
            len(item.get("aggregated_output", "").encode("utf-8"))
            for item in workspace_commands
        )
        + sum(value for value in mixed_adjustments if value is not None),
        "command_shape": "codex exec -C <isolated-workspace> --skip-git-repo-check --sandbox read-only --ephemeral --json --output-last-message <file> [--model <model>] [--config model_reasoning_effort=<effort>] <prompt>",
    }
    (run_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
