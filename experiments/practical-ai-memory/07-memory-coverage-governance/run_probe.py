#!/usr/bin/env python3
"""Run one isolated POC 07 Pilot probe with an explicitly locked model."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from validate_fixtures import CONDITIONS, FIXTURE, ROOT, TASKS, validate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=TASKS, required=True)
    parser.add_argument("--condition", choices=CONDITIONS, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--reasoning-effort", choices=("low", "medium", "high", "xhigh"), required=True)
    parser.add_argument("--label", default="pilot-01")
    return parser.parse_args()


def copy_fixture(workspace: Path, condition: str) -> None:
    shutil.copytree(FIXTURE / "records", workspace / "records")
    shutil.copy2(FIXTURE / "manifest.json", workspace / "manifest.json")
    shutil.copytree(FIXTURE / "conditions" / condition, workspace, dirs_exist_ok=True)
    generated = FIXTURE / "generated"
    if condition == "state-projection":
        shutil.copy2(generated / "state-projection.json", workspace / "state-projection.json")
    if condition == "coverage-governance-projection":
        shutil.copy2(generated / "coverage-governance.md", workspace / "coverage-governance.md")
    if condition == "source-only":
        return
    if condition == "state-projection":
        return
    if condition == "coverage-governance-projection":
        return
    raise ValueError("unknown condition")


def main() -> int:
    args = parse_args()
    errors = validate()
    if errors:
        raise SystemExit("fixture validation failed:\n" + "\n".join(errors))
    prompt = (ROOT / "prompts" / f"{args.task}.md").read_text(encoding="utf-8")
    run_name = f"{args.label}-{args.task}-{args.condition}"
    run_dir = ROOT / "runs" / "private" / "macos" / run_name
    if run_dir.exists():
        raise SystemExit(f"refusing to overwrite existing run: {run_name}")
    run_dir.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="coverage-governance-") as temporary:
        workspace = Path(temporary) / "workspace"
        workspace.mkdir()
        copy_fixture(workspace, args.condition)
        command = [
            shutil.which("codex") or "codex", "exec", "-C", str(workspace),
            "--skip-git-repo-check", "--ignore-rules", "--sandbox", "read-only", "--ephemeral", "--json",
            "--config", "features.plugins=false", "--config", "mcp_servers={}",
            "--model", args.model, "--config", f'model_reasoning_effort="{args.reasoning_effort}"',
            "--output-last-message", str(run_dir / "final.md"), "-",
        ]
        started = time.monotonic()
        result = subprocess.run(command, input=prompt, text=True, encoding="utf-8", capture_output=True, cwd=workspace, env=os.environ.copy(), check=False)
        elapsed = round(time.monotonic() - started, 3)
    (run_dir / "raw.jsonl").write_text(result.stdout, encoding="utf-8")
    (run_dir / "stderr.log").write_text(result.stderr, encoding="utf-8")
    final = run_dir / "final.md"
    metadata = {
        "run_name": run_name,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "task": args.task,
        "condition": args.condition,
        "requested_model": args.model,
        "requested_reasoning_effort": args.reasoning_effort,
        "codex_version": subprocess.check_output([command[0], "--version"], text=True, encoding="utf-8").strip(),
        "sandbox": "read-only",
        "ephemeral": True,
        "plugins_enabled": False,
        "exit_code": result.returncode,
        "elapsed_seconds": elapsed,
        "final_answer_present": final.is_file() and bool(final.read_text(encoding="utf-8").strip()),
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if result.returncode != 0 or not metadata["final_answer_present"]:
        raise SystemExit(f"probe failed: exit={result.returncode}, final={metadata['final_answer_present']}")
    print(json.dumps({key: metadata[key] for key in ("run_name", "requested_model", "requested_reasoning_effort", "exit_code", "elapsed_seconds", "final_answer_present")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
