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
    parser.add_argument(
        "--criterion-scores",
        type=Path,
        required=True,
        help="JSON file containing ordered criterion_id and score items",
    )
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


def task_criteria(task: object) -> list[tuple[str, int]]:
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
    raw_criteria = task_rubric.get("criteria")
    if not isinstance(raw_criteria, list) or not raw_criteria:
        raise SystemExit("frozen task criteria are malformed")
    criteria: list[tuple[str, int]] = []
    for raw in raw_criteria:
        if not isinstance(raw, dict):
            raise SystemExit("frozen task criterion is malformed")
        criterion_id = raw.get("id")
        points = raw.get("points")
        if (
            not isinstance(criterion_id, str)
            or not criterion_id
            or not isinstance(points, int)
            or isinstance(points, bool)
            or points <= 0
        ):
            raise SystemExit("frozen task criterion is malformed")
        criteria.append((criterion_id, points))
    criterion_ids = [criterion_id for criterion_id, _ in criteria]
    if len(set(criterion_ids)) != len(criterion_ids):
        raise SystemExit("frozen task criterion IDs must be unique")
    if sum(points for _, points in criteria) != maximum:
        raise SystemExit("frozen task criterion points do not match task maximum")
    return criteria


def validated_rubric_items(
    path: Path, criteria: list[tuple[str, int]], correctness_score: int
) -> list[dict[str, object]]:
    try:
        raw_items = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemExit("criterion-scores must be a readable JSON file") from error
    if not isinstance(raw_items, list):
        raise SystemExit("criterion-scores JSON root must be an ordered list")
    expected_ids = [criterion_id for criterion_id, _ in criteria]
    actual_ids = [
        item.get("criterion_id") if isinstance(item, dict) else None
        for item in raw_items
    ]
    if (
        not all(isinstance(criterion_id, str) for criterion_id in actual_ids)
        or actual_ids != expected_ids
        or len(set(actual_ids)) != len(actual_ids)
    ):
        raise SystemExit(
            "criterion IDs must exactly match frozen rubric order and uniqueness"
        )

    rubric_items: list[dict[str, object]] = []
    for raw, (criterion_id, maximum) in zip(raw_items, criteria):
        if not isinstance(raw, dict) or set(raw) != {"criterion_id", "score"}:
            raise SystemExit("each criterion score must contain only criterion_id and score")
        score = raw.get("score")
        if (
            not isinstance(score, int)
            or isinstance(score, bool)
            or not 0 <= score <= maximum
        ):
            raise SystemExit("criterion score must be within its frozen range")
        rubric_items.append(
            {
                "criterion_id": criterion_id,
                "score": score,
                "max_score": maximum,
                "passed": score == maximum,
            }
        )
    if sum(int(item["score"]) for item in rubric_items) != correctness_score:
        raise SystemExit("criterion score sum must equal correctness_score")
    return rubric_items


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
    criteria = task_criteria(metadata.get("task"))
    maximum = sum(points for _, points in criteria)
    if not 0 <= args.score <= maximum:
        raise SystemExit("score must be between zero and the frozen task maximum")
    for key in ("run_name", "task", "condition"):
        if not isinstance(metadata.get(key), str) or not metadata[key]:
            raise SystemExit(f"metadata field is missing or invalid: {key}")
    rubric_items = validated_rubric_items(
        args.criterion_scores, criteria, args.score
    )

    score = {
        "run_name": metadata["run_name"],
        "task": metadata["task"],
        "condition": metadata["condition"],
        "correctness_score": args.score,
        "correctness_max": maximum,
        "rubric_items": rubric_items,
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
