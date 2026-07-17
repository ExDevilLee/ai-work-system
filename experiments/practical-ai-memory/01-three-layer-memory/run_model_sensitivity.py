#!/usr/bin/env python3
"""Run one exploratory matrix for a second model configuration."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LABEL = "model-terra-01"
MODEL = "gpt-5.6-terra"
REASONING_EFFORT = "medium"
RUNS = (
    ("current-task", "baseline"),
    ("current-task", "layered"),
    ("stable-rules", "layered"),
    ("stable-rules", "baseline"),
    ("reference-retrieval", "baseline"),
    ("reference-retrieval", "layered"),
)


def main() -> int:
    completed = 0
    skipped = 0
    for task, condition in RUNS:
        run_name = f"{LABEL}-{task}-{condition}"
        run_dir = ROOT / "runs" / "private" / "macos" / run_name
        if (run_dir / "metadata.json").is_file():
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
            LABEL,
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

    print(f"model sensitivity complete: completed={completed}, skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
