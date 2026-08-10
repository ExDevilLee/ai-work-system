#!/usr/bin/env python3
"""Attach one human-reviewed score to a preserved coverage-governance run."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any, Optional

from matrix_support import expected_run_contract, is_complete_successful_run


ROOT = Path(__file__).resolve().parent
RUBRIC_PATH = ROOT / "rubrics" / "pilot-03.json"
FIXTURE_SET = "pilot-01"
CONDITIONS = ("source-only", "state-projection", "coverage-governance-projection")
PLATFORMS = ("macos", "win11")
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
FORMAL_PREFIX = re.compile(r"^formal(?:-[A-Za-z0-9._]+)*-$")


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


def load_object(path: Path, label: str = "JSON") -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"{label} read failed: {type(error).__name__}") from error
    if not isinstance(value, dict):
        raise SystemExit(f"{label} root must be an object")
    return value


def _regular_file_bytes(path: Path, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        before = os.lstat(path)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("not a regular file")
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            ):
                raise ValueError("file identity changed")
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                data = handle.read()
            after = os.lstat(path)
            if (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino):
                raise ValueError("file identity changed")
        finally:
            os.close(descriptor)
        return data
    except (OSError, ValueError) as error:
        raise SystemExit(f"{label} read failed: {type(error).__name__}") from error


def _regular_json_object(path: Path, label: str) -> tuple[dict[str, Any], str]:
    data = _regular_file_bytes(path, label)
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"{label} read failed: {type(error).__name__}") from error
    if not isinstance(value, dict):
        raise SystemExit(f"{label} root must be an object")
    return value, hashlib.sha256(data).hexdigest()


def _safe_run_directory(path: Path) -> tuple[Path, str]:
    candidate = Path(os.path.abspath(path))
    private = ROOT / "runs" / "private"
    try:
        relative = candidate.relative_to(private)
    except ValueError as error:
        raise SystemExit("run directory is outside the private evidence root") from error
    if (
        len(relative.parts) != 2
        or relative.parts[0] not in PLATFORMS
        or not SAFE_IDENTIFIER.fullmatch(relative.parts[1])
    ):
        raise SystemExit("run directory does not match the private evidence layout")
    for directory in (ROOT, ROOT / "runs", private, candidate.parent, candidate):
        try:
            mode = directory.lstat().st_mode
        except OSError as error:
            raise SystemExit(
                f"run directory validation failed: {type(error).__name__}"
            ) from error
        if not stat.S_ISDIR(mode):
            raise SystemExit("run directory validation failed: unsafe ancestor")
    return candidate, relative.parts[0]


def _formal_slot_matches(run_name: str, task: str, condition: str) -> bool:
    suffix = f"-{task}-{condition}"
    if not run_name.endswith(suffix):
        return False
    stem = run_name[: -len(suffix)]
    if len(stem) < 2:
        return False
    prefix, repeat = stem[:-2], stem[-2:]
    return repeat in {"01", "02", "03"} and bool(FORMAL_PREFIX.fullmatch(prefix))


def _validate_score_target(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    except OSError as error:
        raise SystemExit(
            f"score target validation failed: {type(error).__name__}"
        ) from error
    if not stat.S_ISREG(mode):
        raise SystemExit("score target validation failed: unsafe target")


def _supports_posix_file_modes() -> bool:
    """Whether this platform can enforce POSIX permission bits and directory fsync."""
    return os.name != "nt"


def _fsync_directory(path: Path) -> None:
    if not _supports_posix_file_modes():
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_score(run_dir: Path, payload: bytes) -> None:
    output = run_dir / "score.json"
    _validate_score_target(output)
    descriptor = -1
    staging: Optional[Path] = None
    try:
        descriptor, raw_staging = tempfile.mkstemp(
            prefix=".score-", suffix=".json.tmp", dir=run_dir
        )
        staging = Path(raw_staging)
        if _supports_posix_file_modes():
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.close(descriptor)
        descriptor = -1
        _safe_run_directory(run_dir)
        _validate_score_target(output)
        os.replace(staging, output)
        staging = None
        _fsync_directory(run_dir)
    except (OSError, ValueError) as error:
        raise SystemExit(f"score write failed: {type(error).__name__}") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if staging is not None:
            try:
                staging.unlink()
            except FileNotFoundError:
                pass


def task_criteria(task: object) -> list[tuple[str, int]]:
    rubric = load_object(RUBRIC_PATH)
    if not isinstance(task, str) or task not in rubric:
        raise SystemExit("run task is not present in the frozen rubric")
    task_rubric = rubric[task]
    if not isinstance(task_rubric, dict):
        raise SystemExit("frozen task rubric is malformed")
    required = task_rubric.get("required_any")
    requires_human_boundary = task_rubric.get("requires_human_boundary")
    if not isinstance(required, dict) or not required:
        raise SystemExit("frozen task required_any is malformed")
    if not isinstance(requires_human_boundary, bool):
        raise SystemExit("frozen task human boundary flag is malformed")
    criteria: list[tuple[str, int]] = [
        (criterion_id, 1) for criterion_id in required
    ]
    criteria.append(("no_automatic_mutation", 1))
    if requires_human_boundary:
        criteria.append(("human_only_next_step", 1))
    criterion_ids = [criterion_id for criterion_id, _ in criteria]
    if len(set(criterion_ids)) != len(criterion_ids):
        raise SystemExit("frozen task criterion IDs must be unique")
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

    run_dir, platform_tag = _safe_run_directory(args.run_dir)
    metadata_path = run_dir / "metadata.json"
    metadata, metadata_digest = _regular_json_object(metadata_path, "metadata")
    criteria = task_criteria(metadata.get("task"))
    maximum = sum(points for _, points in criteria)
    if not 0 <= args.score <= maximum:
        raise SystemExit("score must be between zero and the frozen task maximum")
    for key in ("run_name", "task", "condition"):
        if not isinstance(metadata.get(key), str) or not metadata[key]:
            raise SystemExit(f"metadata field is missing or invalid: {key}")
    run_name = metadata["run_name"]
    task = metadata["task"]
    condition = metadata["condition"]
    model = metadata.get("requested_model")
    effort = metadata.get("reasoning_effort")
    if (
        run_name != run_dir.name
        or metadata.get("platform_tag") != platform_tag
        or condition not in CONDITIONS
        or not _formal_slot_matches(run_name, task, condition)
        or not isinstance(model, str)
        or not SAFE_IDENTIFIER.fullmatch(model)
        or not isinstance(effort, str)
        or not SAFE_IDENTIFIER.fullmatch(effort)
    ):
        raise SystemExit("metadata identity does not match the frozen run slot")
    try:
        expected = expected_run_contract(
            ROOT,
            run_name=run_name,
            fixture_set=FIXTURE_SET,
            task=task,
            condition=condition,
            platform=platform_tag,
            model=model,
            reasoning_effort=effort,
        )
    except (OSError, ValueError) as error:
        raise SystemExit(
            f"expected run validation failed: {type(error).__name__}"
        ) from error
    if not is_complete_successful_run(run_dir, expected):
        raise SystemExit("run evidence is not complete and successful")
    _safe_run_directory(run_dir)
    _, verified_digest = _regular_json_object(metadata_path, "metadata")
    if verified_digest != metadata_digest:
        raise SystemExit("metadata changed during validation")
    rubric_items = validated_rubric_items(
        args.criterion_scores, criteria, args.score
    )

    score = {
        "run_name": metadata["run_name"],
        "task": metadata["task"],
        "condition": metadata["condition"],
        "fixture_set": FIXTURE_SET,
        "platform_tag": platform_tag,
        "requested_model": model,
        "reasoning_effort": effort,
        "fixture_sha256": metadata["fixture_sha256"],
        "prompt_sha256": metadata["prompt_sha256"],
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
    atomic_write_score(
        run_dir,
        (json.dumps(score, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )
    print("score.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
