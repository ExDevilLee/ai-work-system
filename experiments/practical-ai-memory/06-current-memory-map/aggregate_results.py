#!/usr/bin/env python3
"""Aggregate reviewed current-map runs without leaking private run data."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import stat
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
RUBRIC_PATH = ROOT / "expected" / "rubric.json"
CONDITIONS = ("source-only", "flat-index", "state-projection")
REPEATS = range(1, 4)
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SAFE_CODEX_VERSION = re.compile(r"^codex-cli [A-Za-z0-9][A-Za-z0-9._-]*$")
CSV_FIELDS = (
    "run_name",
    "task",
    "condition",
    "platform",
    "model",
    "reasoning_effort",
    "codex_version",
    "score",
    "max_score",
    "protocol_valid",
    "unsupported_claims",
    "irrelevant_facts",
    "manual_review_minutes",
    "review_time_method",
    "review_batch_size",
    "resident_instruction_bytes",
    "project_context_bytes",
    "workspace_command_calls",
    "workspace_output_bytes",
    "workspace_metric_coverage_complete",
    "workspace_output_bytes_reliable",
    "elapsed_seconds",
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", default="formal-")
    parser.add_argument("--platform-tag", choices=("macos", "win11"), default="macos")
    parser.add_argument("--output-stem", required=True)
    return parser.parse_args()


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot read valid JSON: {path.name}") from error
    if not isinstance(value, dict):
        raise SystemExit(f"JSON root must be an object: {path.name}")
    return value


def summarize(values: list[float]) -> dict[str, float]:
    if not values:
        raise ValueError("cannot summarize an empty sample")
    return {
        "min": min(values),
        "median": statistics.median(values),
        "mean": round(statistics.mean(values), 3),
        "max": max(values),
    }


def require_identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not SAFE_IDENTIFIER.fullmatch(value):
        raise SystemExit(f"private or invalid value rejected from public aggregate: {name}")
    return value


def require_number(name: str, value: object, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SystemExit(f"numeric field is missing or invalid: {name}")
    if not math.isfinite(float(value)):
        raise SystemExit(f"numeric field must be finite: {name}")
    if positive and value <= 0:
        raise SystemExit(f"numeric field must be positive: {name}")
    if not positive and value < 0:
        raise SystemExit(f"numeric field must not be negative: {name}")
    return float(value)


def require_nonnegative_integer(name: str, value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SystemExit(f"integer field is missing or invalid: {name}")
    return value


def require_regular_file(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except OSError as error:
        raise SystemExit(f"required evidence file is missing: {path.name}") from error
    if not stat.S_ISREG(mode):
        raise SystemExit(f"required evidence must be a regular file: {path.name}")


def frozen_tasks() -> dict[str, list[tuple[str, int]]]:
    rubric = load_object(RUBRIC_PATH)
    raw_tasks = rubric.get("tasks")
    if not isinstance(raw_tasks, dict) or len(raw_tasks) != 5:
        raise SystemExit("frozen rubric must define exactly five tasks")
    tasks: dict[str, list[tuple[str, int]]] = {}
    for task, raw in raw_tasks.items():
        task = require_identifier("task", task)
        if not isinstance(raw, dict):
            raise SystemExit("frozen task rubric is malformed")
        maximum = raw.get("max_score")
        if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum <= 0:
            raise SystemExit("frozen task maximum is invalid")
        raw_criteria = raw.get("criteria")
        if not isinstance(raw_criteria, list) or not raw_criteria:
            raise SystemExit("frozen task criteria are malformed")
        criteria: list[tuple[str, int]] = []
        for criterion in raw_criteria:
            if not isinstance(criterion, dict):
                raise SystemExit("frozen task criterion is malformed")
            criterion_id = criterion.get("id")
            points = criterion.get("points")
            if (
                not isinstance(criterion_id, str)
                or not SAFE_IDENTIFIER.fullmatch(criterion_id)
                or not isinstance(points, int)
                or isinstance(points, bool)
                or points <= 0
            ):
                raise SystemExit("frozen task criterion is malformed")
            criteria.append((criterion_id, points))
        ids = [criterion_id for criterion_id, _ in criteria]
        if len(set(ids)) != len(ids) or sum(points for _, points in criteria) != maximum:
            raise SystemExit("frozen task criteria do not match the task maximum")
        tasks[task] = criteria
    return tasks


def validate_saved_rubric_items(
    score: dict[str, Any],
    criteria: list[tuple[str, int]],
    correctness_score: int,
    correctness_max: int,
) -> None:
    raw_items = score.get("rubric_items")
    if not isinstance(raw_items, list):
        raise SystemExit("score rubric_items must be an ordered list")
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
        raise SystemExit("score rubric IDs do not match the frozen order and uniqueness")

    item_score_sum = 0
    item_max_sum = 0
    for item, (criterion_id, maximum) in zip(raw_items, criteria):
        if not isinstance(item, dict) or set(item) != {
            "criterion_id",
            "score",
            "max_score",
            "passed",
        }:
            raise SystemExit("score rubric item shape is invalid")
        item_score = item.get("score")
        item_max = item.get("max_score")
        passed = item.get("passed")
        if (
            item.get("criterion_id") != criterion_id
            or item_max != maximum
            or not isinstance(item_score, int)
            or isinstance(item_score, bool)
            or not 0 <= item_score <= maximum
            or not isinstance(passed, bool)
            or passed != (item_score == maximum)
        ):
            raise SystemExit("score rubric item disagrees with the frozen rubric")
        item_score_sum += item_score
        item_max_sum += maximum
    if item_score_sum != correctness_score or item_max_sum != correctness_max:
        raise SystemExit("score rubric item totals disagree with correctness totals")


def expected_run_names(prefix: str, tasks: Iterable[str]) -> set[str]:
    if prefix != "formal-":
        raise SystemExit("current-map formal aggregation requires prefix formal-")
    return {
        f"formal-{repeat:02d}-{task}-{condition}"
        for repeat in REPEATS
        for task in tasks
        for condition in CONDITIONS
    }


def _validated_row(
    metadata: dict[str, Any],
    score: dict[str, Any],
    *,
    expected_name: str,
    platform_tag: str,
    task_rubrics: dict[str, list[tuple[str, int]]],
) -> dict[str, object]:
    run_name = require_identifier("run_name", metadata.get("run_name"))
    task = require_identifier("task", metadata.get("task"))
    condition = require_identifier("condition", metadata.get("condition"))
    if run_name != expected_name or task not in task_rubrics or condition not in CONDITIONS:
        raise SystemExit("formal run identity does not match the frozen matrix")
    if metadata.get("purpose") != "formal run":
        raise SystemExit("non-formal run found in formal aggregation")
    platform = require_identifier("platform_tag", metadata.get("platform_tag"))
    if platform != platform_tag:
        raise SystemExit("platform metadata does not match the selected platform")
    model = require_identifier("requested_model", metadata.get("requested_model"))
    effort = require_identifier("reasoning_effort", metadata.get("reasoning_effort"))
    cli = metadata.get("codex_version")
    if not isinstance(cli, str) or not SAFE_CODEX_VERSION.fullmatch(cli):
        raise SystemExit("private or invalid codex version rejected from public aggregate")

    for key, expected in (("run_name", run_name), ("task", task), ("condition", condition)):
        if score.get(key) != expected:
            raise SystemExit("score identity does not match metadata")
    correctness = score.get("correctness_score")
    correctness_max = score.get("correctness_max")
    task_maximum = sum(points for _, points in task_rubrics[task])
    if (
        not isinstance(correctness, int)
        or isinstance(correctness, bool)
        or not 0 <= correctness <= task_maximum
        or correctness_max != task_maximum
    ):
        raise SystemExit("score exceeds or disagrees with the frozen task maximum")
    validate_saved_rubric_items(
        score, task_rubrics[task], correctness, correctness_max
    )
    if score.get("protocol_valid") is not True:
        raise SystemExit("formal aggregate requires protocol_valid=true for all 45 runs")
    unsupported = require_nonnegative_integer(
        "unsupported_claims", score.get("unsupported_claims")
    )
    irrelevant = require_nonnegative_integer(
        "irrelevant_facts", score.get("irrelevant_facts")
    )
    review_minutes = require_number(
        "manual_review_minutes", score.get("manual_review_minutes"), positive=True
    )
    review_method = require_identifier("review_time_method", score.get("review_time_method"))
    review_batch_size = score.get("review_batch_size")
    if review_method == "batch_average":
        if not isinstance(review_batch_size, int) or isinstance(review_batch_size, bool) or review_batch_size < 2:
            raise SystemExit("batch_average score requires review_batch_size >= 2")
    elif review_method == "individual":
        if review_batch_size is not None:
            raise SystemExit("individual review must not set review_batch_size")
    else:
        raise SystemExit("unsupported review_time_method")

    coverage = metadata.get("workspace_metric_coverage_complete")
    reliable = metadata.get("workspace_output_bytes_reliable")
    if not isinstance(coverage, bool) or not isinstance(reliable, bool):
        raise SystemExit("workspace metric reliability fields must be booleans")
    usage = metadata.get("usage")
    if not isinstance(usage, dict):
        raise SystemExit("formal run usage is missing")

    row: dict[str, object] = {
        "run_name": run_name,
        "task": task,
        "condition": condition,
        "platform": platform,
        "model": model,
        "reasoning_effort": effort,
        "codex_version": cli,
        "score": correctness,
        "max_score": correctness_max,
        "protocol_valid": True,
        "unsupported_claims": unsupported,
        "irrelevant_facts": irrelevant,
        "manual_review_minutes": review_minutes,
        "review_time_method": review_method,
        "review_batch_size": review_batch_size,
        "resident_instruction_bytes": require_number(
            "resident_instruction_bytes", metadata.get("resident_instruction_bytes")
        ),
        "project_context_bytes": None,
        "workspace_command_calls": None,
        "workspace_output_bytes": None,
        "workspace_metric_coverage_complete": coverage,
        "workspace_output_bytes_reliable": reliable,
        "elapsed_seconds": require_number("elapsed_seconds", metadata.get("elapsed_seconds")),
        "input_tokens": require_number("input_tokens", usage.get("input_tokens")),
        "cached_input_tokens": require_number(
            "cached_input_tokens", usage.get("cached_input_tokens")
        ),
        "output_tokens": require_number("output_tokens", usage.get("output_tokens")),
        "reasoning_output_tokens": require_number(
            "reasoning_output_tokens", usage.get("reasoning_output_tokens")
        ),
    }
    if coverage and reliable:
        row["project_context_bytes"] = require_number(
            "project_context_bytes", metadata.get("project_context_bytes")
        )
        row["workspace_command_calls"] = require_number(
            "workspace_command_calls", metadata.get("workspace_command_calls")
        )
        row["workspace_output_bytes"] = require_number(
            "workspace_output_bytes", metadata.get("workspace_output_bytes")
        )
    return row


def _group_summary(group: list[dict[str, object]]) -> dict[str, object]:
    complete = [
        row
        for row in group
        if row["workspace_metric_coverage_complete"] is True
        and row["workspace_output_bytes_reliable"] is True
    ]
    return {
        "n": len(group),
        "correctness": {
            "score": sum(int(row["score"]) for row in group),
            "max_score": sum(int(row["max_score"]) for row in group),
        },
        "unsupported_claims": sum(int(row["unsupported_claims"]) for row in group),
        "irrelevant_facts": sum(int(row["irrelevant_facts"]) for row in group),
        "workspace_metrics_n": len(complete),
        "resident_instruction_bytes": summarize(
            [float(row["resident_instruction_bytes"]) for row in group]
        ),
        "project_context_bytes": summarize(
            [float(row["project_context_bytes"]) for row in complete]
        ) if complete else None,
        "workspace_command_calls": summarize(
            [float(row["workspace_command_calls"]) for row in complete]
        ) if complete else None,
        "workspace_output_bytes": summarize(
            [float(row["workspace_output_bytes"]) for row in complete]
        ) if complete else None,
        "elapsed_seconds": summarize([float(row["elapsed_seconds"]) for row in group]),
        "input_tokens": summarize([float(row["input_tokens"]) for row in group]),
        "output_tokens": summarize([float(row["output_tokens"]) for row in group]),
        "reasoning_output_tokens": summarize(
            [float(row["reasoning_output_tokens"]) for row in group]
        ),
        "manual_review_minutes_per_run": summarize(
            [float(row["manual_review_minutes"]) for row in group]
        ),
    }


def aggregate_runs(
    *, root: Path, prefix: str, platform_tag: str, output_stem: str
) -> tuple[Path, Path]:
    require_identifier("output_stem", output_stem)
    if platform_tag not in ("macos", "win11"):
        raise SystemExit("unsupported platform")
    tasks = frozen_tasks()
    expected = expected_run_names(prefix, tasks)
    private = root / "runs" / "private" / platform_tag
    if private.is_symlink():
        raise SystemExit("private evidence root must not be a symlink")
    candidate_paths = list(private.glob(f"{prefix}*"))
    if any(path.is_symlink() or not path.is_dir() for path in candidate_paths):
        raise SystemExit("formal evidence directories must be real directories")
    actual = {path.name for path in candidate_paths}
    if actual != expected:
        raise SystemExit(
            f"formal matrix must contain exactly 45 frozen runs; missing={len(expected - actual)}, extra={len(actual - expected)}"
        )

    rows: list[dict[str, object]] = []
    for run_name in sorted(expected):
        run_dir = private / run_name
        metadata_path = run_dir / "metadata.json"
        score_path = run_dir / "score.json"
        require_regular_file(metadata_path)
        require_regular_file(score_path)
        metadata = load_object(metadata_path)
        score = load_object(score_path)
        rows.append(
            _validated_row(
                metadata,
                score,
                expected_name=run_name,
                platform_tag=platform_tag,
                task_rubrics=tasks,
            )
        )

    configurations = {
        (row["platform"], row["model"], row["reasoning_effort"], row["codex_version"])
        for row in rows
    }
    if len(configurations) != 1:
        raise SystemExit("refusing mixed batch: platform/model/effort/CLI differ")

    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    conditioned: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["task"]), str(row["condition"]))].append(row)
        conditioned[str(row["condition"])].append(row)
    if len(grouped) != 15 or any(len(group) != 3 for group in grouped.values()):
        raise SystemExit("formal matrix must aggregate to 15 groups with n=3")

    platform, model, effort, cli = next(iter(configurations))
    summary = {
        "selection_prefix": prefix,
        "platform_tag": platform,
        "run_count": len(rows),
        "review_time_note": (
            "manual_review_minutes is a positive measured per-run value or a "
            "per-run allocation from a timed batch"
        ),
        "model_configuration": {
            "model": model,
            "reasoning_effort": effort,
            "codex_version": cli,
        },
        "conditions": {
            condition: _group_summary(group)
            for condition, group in sorted(conditioned.items())
        },
        "groups": {
            f"{task}:{condition}": _group_summary(group)
            for (task, condition), group in sorted(grouped.items())
        },
    }

    data_dir = root / "data"
    if data_dir.is_symlink():
        raise SystemExit("public data directory must not be a symlink")
    data_dir.mkdir(exist_ok=True)
    csv_path = data_dir / f"{output_stem}.csv"
    json_path = data_dir / f"{output_stem}.json"
    csv_staging = csv_path.with_suffix(".csv.tmp")
    json_staging = json_path.with_suffix(".json.tmp")
    try:
        with csv_staging.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=CSV_FIELDS, lineterminator="\n", extrasaction="raise"
            )
            writer.writeheader()
            writer.writerows(rows)
        json_staging.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        csv_staging.replace(csv_path)
        json_staging.replace(json_path)
    finally:
        csv_staging.unlink(missing_ok=True)
        json_staging.unlink(missing_ok=True)
    return csv_path, json_path


def main() -> int:
    args = parse_args()
    csv_path, json_path = aggregate_runs(
        root=ROOT,
        prefix=args.prefix,
        platform_tag=args.platform_tag,
        output_stem=args.output_stem,
    )
    print(csv_path)
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
