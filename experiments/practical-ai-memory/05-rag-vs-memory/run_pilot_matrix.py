#!/usr/bin/env python3
"""Run the frozen 5 x 3 RAG-vs-memory Pilot 01 matrix."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from matrix_support import is_complete_successful_run


ROOT = Path(__file__).resolve().parent
MODEL = "gpt-5.6-sol"
REASONING_EFFORT = "medium"
SCHEDULE = (
    ("static-reference", ("rag-only", "rag-with-recency", "memory-governed")),
    ("approved-decision", ("rag-with-recency", "memory-governed", "rag-only")),
    ("unresolved-conflict", ("memory-governed", "rag-only", "rag-with-recency")),
    ("scope-bound-rule", ("rag-only", "memory-governed", "rag-with-recency")),
    ("historical-trace", ("rag-with-recency", "rag-only", "memory-governed")),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="pilot-01")
    parser.add_argument("--fixture-set", default="pilot-01")
    parser.add_argument("--platform-tag", choices=("macos", "win11"), default="macos")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--reasoning-effort", default=REASONING_EFFORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.label.startswith("pilot-"):
        raise SystemExit("pilot label must start with 'pilot-'")
    completed = 0
    skipped = 0
    for task, conditions in SCHEDULE:
        for condition in conditions:
            run_name = f"{args.label}-{task}-{condition}"
            run_dir = ROOT / "runs" / "private" / args.platform_tag / run_name
            if is_complete_successful_run(run_dir):
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
                args.label,
                "--fixture-set",
                args.fixture_set,
                "--task",
                task,
                "--model",
                args.model,
                "--reasoning-effort",
                args.reasoning_effort,
                "--platform-tag",
                args.platform_tag,
            ]
            print(f"RUN  {run_name}", flush=True)
            result = subprocess.run(command)
            if result.returncode != 0:
                print(f"STOP failed run: {run_name}", file=sys.stderr)
                return result.returncode
            completed += 1
    print(f"pilot matrix complete: completed={completed}, skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
