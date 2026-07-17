#!/usr/bin/env python3
"""Run the frozen 3 x 2 x 3 formal experiment matrix with resume support."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MODEL = "gpt-5.6-sol"
REASONING_EFFORT = "medium"

SCHEDULE = (
    (
        "formal-01",
        (
            ("current-task", "baseline"),
            ("current-task", "layered"),
            ("stable-rules", "layered"),
            ("stable-rules", "baseline"),
            ("reference-retrieval", "baseline"),
            ("reference-retrieval", "layered"),
        ),
    ),
    (
        "formal-02",
        (
            ("stable-rules", "baseline"),
            ("stable-rules", "layered"),
            ("reference-retrieval", "layered"),
            ("reference-retrieval", "baseline"),
            ("current-task", "layered"),
            ("current-task", "baseline"),
        ),
    ),
    (
        "formal-03",
        (
            ("reference-retrieval", "baseline"),
            ("reference-retrieval", "layered"),
            ("current-task", "baseline"),
            ("current-task", "layered"),
            ("stable-rules", "layered"),
            ("stable-rules", "baseline"),
        ),
    ),
)


def main() -> int:
    completed = 0
    skipped = 0
    for label, runs in SCHEDULE:
        for task, condition in runs:
            run_name = f"{label}-{task}-{condition}"
            run_dir = ROOT / "runs" / "private" / "macos" / run_name
            metadata = run_dir / "metadata.json"
            if metadata.is_file():
                print(f"SKIP {run_name}", flush=True)
                skipped += 1
                continue
            if run_dir.exists():
                print(f"STOP incomplete run directory: {run_dir}", file=sys.stderr)
                return 1

            command = [
                sys.executable,
                str(ROOT / "run_experiment.py"),
                condition,
                "--label",
                label,
                "--fixture-set",
                "pilot-02",
                "--task",
                task,
                "--model",
                MODEL,
                "--reasoning-effort",
                REASONING_EFFORT,
            ]
            print(f"RUN  {run_name}", flush=True)
            result = subprocess.run(command)
            if result.returncode != 0:
                print(f"STOP failed run: {run_name}", file=sys.stderr)
                return result.returncode
            completed += 1

    print(f"matrix complete: completed={completed}, skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
