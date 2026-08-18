#!/usr/bin/env python3
"""Session and isolated CLI runners for POC 08.

Provides ``prepare_run`` and ``finalize_session_run`` so that the pilot matrix
can create isolated run directories, and the session agent can write ``final.md``
for each cell.

Pilot helpers keep their historical session execution contract.  Formal runs
use ``execute_cli_run``: the frozen fixture is serialized into the prompt and
OMP is launched without tools, session persistence, skills, or rules.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fixture_model import ROOT, ensure_contained_path, tree_checksum
from matrix_support import assemble_fixture
from validate_fixtures import validate

FIXTURE_SET = "pilot-01"
CONDITIONS = ("source-only", "backup-inventory", "recovery-gated-bundle")
TASKS = (
    "clean-restore",
    "partial-backup",
    "integrity-mismatch",
    "target-divergence",
    "derived-index",
    "rollback-receipt",
)


TASK_RECORD_IDS = {
    "clean-restore": "RR-801",
    "partial-backup": "BK-802",
    "integrity-mismatch": "IG-803",
    "target-divergence": "TD-804",
    "derived-index": "DI-805",
    "rollback-receipt": "RB-806",
}


def _project_json(value: Any, record_id: str, keep_all_records: bool) -> Any:
    """Return a task-scoped projection while retaining document metadata."""
    if isinstance(value, list):
        projected = []
        for item in value:
            if not isinstance(item, dict) or keep_all_records:
                projected.append(_project_json(item, record_id, keep_all_records))
                continue
            identity = item.get("id", item.get("record_id"))
            derived_from = item.get("derived_from")
            if identity in {record_id, f"{record_id}-index"} or derived_from == record_id:
                projected.append(_project_json(item, record_id, keep_all_records))
        return projected
    if isinstance(value, dict):
        return {
            key: _project_json(item, record_id, keep_all_records)
            for key, item in value.items()
        }
    return value


def serialize_fixture(snapshot: Path, task: str | None = None) -> str:
    """Serialize a fixture snapshot deterministically for a no-tools model call.

    Formal calls receive a task-scoped projection of the complete frozen
    snapshot. The complete snapshot hash remains the run identity. Partial
    backup keeps every inventory row because completeness is its subject.
    """
    record_id = TASK_RECORD_IDS.get(task or "")
    keep_all_records = task == "partial-backup"
    sections: list[str] = []
    for path in sorted(p for p in snapshot.rglob("*") if p.is_file()):
        relative = path.relative_to(snapshot).as_posix()
        if record_id and relative.startswith("records/") and path.stem != record_id:
            continue
        text = path.read_text(encoding="utf-8")
        if record_id and path.suffix == ".json":
            value = json.loads(text)
            text = json.dumps(
                _project_json(value, record_id, keep_all_records),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        sections.append(f"<file path=\"{relative}\">\n{text}\n</file>")
    return "\n\n".join(sections)


def build_cli_prompt(run_dir: Path, task: str | None = None) -> str:
    """Build the complete formal prompt from frozen task and fixture bytes."""
    task_prompt = (run_dir / "prompt.md").read_text(encoding="utf-8")
    fixture_text = serialize_fixture(run_dir / "fixture-snapshot", task)
    return (
        "You are evaluating a synthetic, read-only backup/recovery scenario.\n"
        "Use only the files embedded below. Do not infer unavailable condition "
        "artifacts, do not perform any action, and answer the task in English. "
        "Distinguish source, backup, target, and receipt evidence precisely. If "
        "the current condition lacks evidence needed for a requested comparison, "
        "state that limitation and make the decision conditional; never relabel "
        "source or target data as backup evidence. Keep the answer under 350 "
        "words while retaining every section requested by the task.\n\n"
        f"<task>\n{task_prompt}\n</task>\n\n"
        f"<fixture>\n{fixture_text}\n</fixture>\n"
    )


def prepare_run(
    *,
    label: str,
    task: str,
    condition: str,
    platform_tag: str = "macos",
    requested_model: str = "glm-5.2",
    requested_effort: str = "unknown",
) -> Path:
    """Create the run directory, assemble the fixture snapshot, and copy the prompt.

    Returns the run directory path.  Caller must write ``final.md`` and then
    call ``finalize_session_run`` to record metadata.
    """
    fixture_errors = validate()
    if fixture_errors:
        raise SystemExit("fixture validation failed:\n" + "\n".join(fixture_errors))

    fixture_root = ensure_contained_path(
        ROOT / "fixtures" / FIXTURE_SET, ROOT, allow_missing=False
    )
    prompt_path = ensure_contained_path(
        ROOT / "prompts" / f"{task}.md", ROOT, allow_missing=False
    )

    run_name = f"{label}-{task}-{condition}"
    run_dir = ensure_contained_path(
        ROOT / "runs" / "private" / platform_tag / run_name, ROOT
    )
    if run_dir.exists():
        raise SystemExit(f"run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)

    fixture_snapshot = run_dir / "fixture-snapshot"
    try:
        assemble_fixture(fixture_root, condition, fixture_snapshot)
        shutil.copy2(prompt_path, run_dir / "prompt.md")
    except (OSError, ValueError) as error:
        raise SystemExit(f"fixture assembly failed: {type(error).__name__}") from error

    return run_dir


def finalize_session_run(
    run_dir: Path,
    *,
    label: str,
    task: str,
    condition: str,
    platform_tag: str = "macos",
    requested_model: str = "glm-5.2",
    requested_effort: str = "unknown",
    observed_model: str = "unknown",
    observed_effort: str = "unknown",
    final_text: str = "",
    started_at: datetime | None = None,
) -> dict[str, Any]:
    """Write ``final.md`` (if provided) and ``metadata.json`` for one cell."""
    if started_at is None:
        started_at = datetime.now(timezone.utc)

    run_name = f"{label}-{task}-{condition}"
    fixture_snapshot = run_dir / "fixture-snapshot"
    prompt_path = run_dir / "prompt.md"

    if final_text:
        (run_dir / "final.md").write_text(final_text, encoding="utf-8")

    fixture_sha = tree_checksum(fixture_snapshot)
    prompt_sha = hashlib.sha256(prompt_path.read_bytes()).hexdigest()

    metadata: dict[str, Any] = {
        "run_name": run_name,
        "condition": condition,
        "fixture_set": FIXTURE_SET,
        "task": task,
        "purpose": "protocol pilot" if label.startswith("pilot") else "formal run",
        "started_at_utc": started_at.isoformat(),
        "platform": platform.platform(),
        "platform_tag": platform_tag,
        "python_version": platform.python_version(),
        "requested_model": requested_model,
        "requested_effort": requested_effort,
        "observed_model": observed_model,
        "observed_effort": observed_effort,
        "execution_path": "session",
        "model_record_status": "requested; observed unknown",
        "fixture_sha256": fixture_sha,
        "prompt_sha256": prompt_sha,
        "sandbox": "session-boundary",
        "ephemeral": True,
        "plugins_enabled": False,
        "protocol_environment_isolated": True,
        "exit_code": 0 if (run_dir / "final.md").exists() else 1,
        "final_answer_present": (run_dir / "final.md").is_file()
        and bool((run_dir / "final.md").read_text(encoding="utf-8").strip()),
        "usage": {},
        "command_shape": (
            "session execution; fixture materials presented as context; "
            "final.md written by session agent; isolation from session boundary"
        ),
    }
    (run_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return metadata


def execute_cli_run(
    *,
    label: str,
    task: str,
    condition: str,
    cli_model: str,
    requested_model: str,
    requested_effort: str,
    platform_tag: str = "macos",
    max_time_seconds: int = 180,
) -> Path:
    """Execute one isolated formal cell through OMP and persist private evidence."""
    started_at = datetime.now(timezone.utc)
    run_dir = prepare_run(
        label=label,
        task=task,
        condition=condition,
        platform_tag=platform_tag,
        requested_model=requested_model,
        requested_effort=requested_effort,
    )
    fixture_snapshot = run_dir / "fixture-snapshot"
    effective_prompt = build_cli_prompt(run_dir, task)
    effective_prompt_sha = hashlib.sha256(effective_prompt.encode("utf-8")).hexdigest()
    command = [
        "omp",
        "-p",
        "--model",
        cli_model,
        "--thinking",
        requested_effort,
        "--no-session",
        "--no-skills",
        "--no-rules",
        "--no-tools",
        "--max-time",
        str(max_time_seconds),
        effective_prompt,
    ]
    before = time.monotonic()
    try:
        result = subprocess.run(
            command,
            cwd=fixture_snapshot,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=max_time_seconds + 30,
            check=False,
        )
        exit_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired as error:
        exit_code = 124
        stdout = error.stdout or ""
        stderr = error.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        stderr += "\nrunner timeout\n"
    elapsed = time.monotonic() - before

    final_text = stdout.strip()
    (run_dir / "final.md").write_text(
        final_text + ("\n" if final_text else ""), encoding="utf-8"
    )
    (run_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
    fixture_sha = tree_checksum(fixture_snapshot)
    prompt_sha = hashlib.sha256((run_dir / "prompt.md").read_bytes()).hexdigest()
    try:
        version_result = subprocess.run(
            ["omp", "--version"],
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=10,
            check=False,
        )
        executor_version = version_result.stdout.strip() or "unknown"
    except (OSError, subprocess.TimeoutExpired):
        executor_version = "unknown"

    metadata: dict[str, Any] = {
        "run_name": f"{label}-{task}-{condition}",
        "condition": condition,
        "fixture_set": FIXTURE_SET,
        "task": task,
        "purpose": "formal run",
        "started_at_utc": started_at.isoformat(),
        "elapsed_seconds": round(elapsed, 6),
        "platform": platform.platform(),
        "platform_tag": platform_tag,
        "python_version": platform.python_version(),
        "requested_model": requested_model,
        "requested_effort": requested_effort,
        "reasoning_effort": requested_effort,
        "observed_model": "unknown",
        "observed_effort": "unknown",
        "execution_path": "omp-cli",
        "executor_version": executor_version,
        "model_record_status": (
            "requested through exact CLI selector; response-side observation unavailable"
        ),
        "fixture_sha256": fixture_sha,
        "prompt_sha256": prompt_sha,
        "effective_prompt_sha256": effective_prompt_sha,
        "fixture_projection": "task-scoped-r2",
        "protocol_revision": "formal-r4-manifest-hash-aligned",
        "sandbox": "embedded-fixture-no-tools",
        "ephemeral": True,
        "plugins_enabled": False,
        "protocol_environment_isolated": True,
        "exit_code": exit_code,
        "final_answer_present": bool(final_text),
        "usage": {},
        "command_shape": (
            "omp -p --model <private-route> --thinking <effort> --no-session "
            "--no-skills --no-rules --no-tools --max-time <seconds> <embedded-prompt>"
        ),
    }
    (run_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return run_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a POC 08 session run directory.")
    parser.add_argument("--label", required=True)
    parser.add_argument("--task", required=True, choices=TASKS)
    parser.add_argument("--condition", required=True, choices=CONDITIONS)
    parser.add_argument("--platform-tag", default="macos")
    parser.add_argument("--model", default="glm-5.2")
    parser.add_argument("--effort", default="unknown")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = prepare_run(
        label=args.label,
        task=args.task,
        condition=args.condition,
        platform_tag=args.platform_tag,
        requested_model=args.model,
        requested_effort=args.effort,
    )
    print(str(run_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
