#!/usr/bin/env python3
"""Session-execution runner for POC 08.

Provides ``prepare_run`` and ``finalize_session_run`` so that the pilot matrix
can create isolated run directories, and the session agent can write ``final.md``
for each cell.

This runner does NOT spawn a subprocess.  The model runs inside the current
session; isolation comes from the session boundary.  Metadata records the
execution path as ``session`` and leaves observed model/effort as ``unknown``
when they cannot be independently verified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
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
