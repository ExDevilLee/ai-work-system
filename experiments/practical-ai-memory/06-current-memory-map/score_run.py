#!/usr/bin/env python3
"""Attach one human-reviewed score to a preserved current-map run."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
RUBRIC_PATH = ROOT / "expected" / "rubric.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--score", type=int, required=True)
    parser.add_argument("--protocol-valid", choices=("yes", "no"), required=True)
    parser.add_argument("--review-minutes", type=float)
    parser.add_argument(
        "--review-time-method",
        choices=("individual", "batch_average"),
        default="individual",
    )
    parser.add_argument("--review-batch-size", type=int)
    parser.add_argument("--irrelevant-facts", type=int, default=0)
    parser.add_argument("--unsupported-claims", type=int, default=0)
    parser.add_argument("--notes", required=True)
    return parser.parse_args()


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot read valid JSON: {path.name}") from error
    if not isinstance(value, dict):
        raise SystemExit(f"JSON root must be an object: {path.name}")
    return value


def task_max_score(task: object) -> int:
    rubric = load_object(RUBRIC_PATH)
    tasks = rubric.get("tasks")
    if not isinstance(task, str) or not isinstance(tasks, dict) or task not in tasks:
        raise SystemExit("run task is not present in the frozen rubric")
    task_rubric = tasks[task]
    if not isinstance(task_rubric, dict):
        raise SystemExit("frozen task rubric is malformed")
    maximum = task_rubric.get("max_score")
    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum <= 0:
        raise SystemExit("frozen task maximum is invalid")
    return maximum


def main() -> int:
    args = parse_args()
    if (
        args.review_minutes is None
        or not math.isfinite(args.review_minutes)
        or args.review_minutes <= 0
    ):
        raise SystemExit("scoring requires positive review-minutes")
    if args.review_time_method == "batch_average":
        if not args.review_batch_size or args.review_batch_size < 2:
            raise SystemExit("batch_average requires review-batch-size >= 2")
    elif args.review_batch_size is not None:
        raise SystemExit("review-batch-size requires batch_average")
    if args.irrelevant_facts < 0 or args.unsupported_claims < 0:
        raise SystemExit("claim counts must not be negative")

    metadata = load_object(args.run_dir / "metadata.json")
    maximum = task_max_score(metadata.get("task"))
    if not 0 <= args.score <= maximum:
        raise SystemExit("score must be between zero and the frozen task maximum")
    for key in ("run_name", "task", "condition"):
        if not isinstance(metadata.get(key), str) or not metadata[key]:
            raise SystemExit(f"metadata field is missing or invalid: {key}")

    score = {
        "run_name": metadata["run_name"],
        "task": metadata["task"],
        "condition": metadata["condition"],
        "correctness_score": args.score,
        "correctness_max": maximum,
        "protocol_valid": args.protocol_valid == "yes",
        "unsupported_claims": args.unsupported_claims,
        "irrelevant_facts": args.irrelevant_facts,
        "manual_review_minutes": args.review_minutes,
        "review_time_status": (
            "measured"
            if args.review_time_method == "individual"
            else "batch average allocation"
        ),
        "review_time_method": args.review_time_method,
        "review_batch_size": args.review_batch_size,
        "manual_review_status": "reviewed",
        "notes": args.notes,
    }
    output = args.run_dir / "score.json"
    output.write_text(
        json.dumps(score, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
