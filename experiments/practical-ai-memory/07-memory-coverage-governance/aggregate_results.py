#!/usr/bin/env python3
"""Aggregate reviewed coverage-governance runs without leaking private run data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import secrets
import stat
import statistics
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from matrix_support import expected_run_contract, is_complete_successful_run


ROOT = Path(__file__).resolve().parent
RUBRIC_PATH = ROOT / "rubrics" / "pilot-03.json"
CONDITIONS = ("source-only", "state-projection", "coverage-governance-projection")
REPEATS = range(1, 4)
FIXTURE_SET = "pilot-01"
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SAFE_CODEX_VERSION = re.compile(r"^codex-cli [A-Za-z0-9][A-Za-z0-9._-]*$")
FORMAL_PREFIX = re.compile(r"^formal(?:-[A-Za-z0-9._]+)*-$")
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
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--reasoning-effort", choices=("low", "medium", "high", "xhigh", "max"), required=True
    )
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
    if len(rubric) != 5:
        raise SystemExit("frozen rubric must define exactly five tasks")
    tasks: dict[str, list[tuple[str, int]]] = {}
    for task, raw in rubric.items():
        task = require_identifier("task", task)
        if not isinstance(raw, dict):
            raise SystemExit("frozen task rubric is malformed")
        required = raw.get("required_any")
        requires_human_boundary = raw.get("requires_human_boundary")
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
        ids = [criterion_id for criterion_id, _ in criteria]
        if len(set(ids)) != len(ids):
            raise SystemExit("frozen task criterion IDs are not unique")
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


def require_formal_prefix(prefix: str) -> str:
    if not isinstance(prefix, str) or not FORMAL_PREFIX.fullmatch(prefix):
        raise SystemExit("formal aggregation prefix must start with formal- and end with -")
    return prefix


def expected_run_names(prefix: str, tasks: Iterable[str]) -> set[str]:
    prefix = require_formal_prefix(prefix)
    return {
        f"{prefix}{repeat:02d}-{task}-{condition}"
        for repeat in REPEATS
        for task in tasks
        for condition in CONDITIONS
    }


def expected_run_slots(
    prefix: str, tasks: Iterable[str]
) -> dict[str, tuple[str, str]]:
    prefix = require_formal_prefix(prefix)
    return {
        f"{prefix}{repeat:02d}-{task}-{condition}": (task, condition)
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
    expected_model: str,
    expected_effort: str,
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
    if model != expected_model or effort != expected_effort:
        raise SystemExit("metadata model or effort does not match the requested batch")
    cli = metadata.get("codex_version")
    if not isinstance(cli, str) or not SAFE_CODEX_VERSION.fullmatch(cli):
        raise SystemExit("private or invalid codex version rejected from public aggregate")

    identity_fields = (
        ("run_name", run_name),
        ("task", task),
        ("condition", condition),
        ("fixture_set", metadata.get("fixture_set")),
        ("platform_tag", platform),
        ("requested_model", model),
        ("reasoning_effort", effort),
        ("fixture_sha256", metadata.get("fixture_sha256")),
        ("prompt_sha256", metadata.get("prompt_sha256")),
    )
    for key, expected in identity_fields:
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
        "resident_instruction_bytes": require_nonnegative_integer(
            "resident_instruction_bytes", metadata.get("resident_instruction_bytes")
        ),
        "project_context_bytes": None,
        "workspace_command_calls": None,
        "workspace_output_bytes": None,
        "workspace_metric_coverage_complete": coverage,
        "workspace_output_bytes_reliable": reliable,
        "elapsed_seconds": require_number("elapsed_seconds", metadata.get("elapsed_seconds")),
        "input_tokens": require_nonnegative_integer(
            "input_tokens", usage.get("input_tokens")
        ),
        "cached_input_tokens": require_nonnegative_integer(
            "cached_input_tokens", usage.get("cached_input_tokens")
        ),
        "output_tokens": require_nonnegative_integer(
            "output_tokens", usage.get("output_tokens")
        ),
        "reasoning_output_tokens": require_nonnegative_integer(
            "reasoning_output_tokens", usage.get("reasoning_output_tokens")
        ),
    }
    if coverage and reliable:
        row["project_context_bytes"] = require_nonnegative_integer(
            "project_context_bytes", metadata.get("project_context_bytes")
        )
        row["workspace_command_calls"] = require_nonnegative_integer(
            "workspace_command_calls", metadata.get("workspace_command_calls")
        )
        row["workspace_output_bytes"] = require_nonnegative_integer(
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


def _fsync_directory(path: Path) -> None:
    if not _supports_posix_file_modes():
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _supports_posix_file_modes() -> bool:
    """Whether this platform can enforce POSIX permission bits and directory fsync."""
    return os.name != "nt"


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int


@dataclass(frozen=True)
class PublicationLock:
    path: Path
    owner_token: str
    identity: FileIdentity


def _regular_identity(path: Path) -> Optional[FileIdentity]:
    try:
        status = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(status.st_mode):
        raise ValueError("transaction path is not a regular file")
    return FileIdentity(status.st_dev, status.st_ino)


def _identity_matches(path: Path, identity: FileIdentity) -> bool:
    try:
        return _regular_identity(path) == identity
    except ValueError:
        return False


def _unlink_owned(path: Path, identity: FileIdentity) -> bool:
    if not _identity_matches(path, identity):
        return False
    path.unlink()
    return True


def _lock_path(csv_path: Path, json_path: Path) -> Path:
    pair = f"{csv_path.name}\0{json_path.name}".encode("utf-8")
    suffix = hashlib.sha256(pair).hexdigest()[:20]
    return csv_path.parent / f".aggregate-lock-{suffix}.lock"


def acquire_publication_lock(csv_path: Path, json_path: Path) -> PublicationLock:
    if csv_path.parent != json_path.parent:
        raise RuntimeError("aggregate lock requires one output directory")
    directory = csv_path.parent
    lock_path = _lock_path(csv_path, json_path)
    owner_token = secrets.token_hex(16)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    identity: Optional[FileIdentity] = None
    try:
        descriptor = os.open(lock_path, flags, 0o600)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError("lock is not a regular file")
        identity = FileIdentity(opened.st_dev, opened.st_ino)
        payload = (owner_token + "\n").encode("ascii")
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("short lock write")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        if not _identity_matches(lock_path, identity):
            raise ValueError("lock identity changed")
        _fsync_directory(directory)
        return PublicationLock(lock_path, owner_token, identity)
    except FileExistsError as error:
        try:
            existing = lock_path.lstat()
        except OSError as inspect_error:
            raise RuntimeError(
                f"aggregate publication lock inspection failed: {type(inspect_error).__name__}"
            ) from inspect_error
        if not stat.S_ISREG(existing.st_mode):
            raise RuntimeError("aggregate publication lock is unsafe") from error
        raise RuntimeError("aggregate publication is already locked") from error
    except (OSError, ValueError) as error:
        if descriptor >= 0:
            os.close(descriptor)
        if identity is not None:
            try:
                _unlink_owned(lock_path, identity)
                _fsync_directory(directory)
            except OSError:
                pass
        raise RuntimeError(
            f"aggregate publication lock failed: {type(error).__name__}"
        ) from error


def _verify_publication_lock(ownership: PublicationLock) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        if not _identity_matches(ownership.path, ownership.identity):
            raise ValueError("lock identity changed")
        descriptor = os.open(ownership.path, flags)
        opened = os.fstat(descriptor)
        if FileIdentity(opened.st_dev, opened.st_ino) != ownership.identity:
            raise ValueError("lock identity changed")
        expected_payload = (ownership.owner_token + "\n").encode("ascii")
        payload = os.read(descriptor, len(expected_payload) + 1)
        os.close(descriptor)
        descriptor = -1
        if payload != expected_payload:
            raise ValueError("lock owner changed")
    except (OSError, ValueError) as error:
        if descriptor >= 0:
            os.close(descriptor)
        raise RuntimeError(
            f"aggregate publication lock ownership failed: {type(error).__name__}"
        ) from error


def release_publication_lock(ownership: PublicationLock) -> None:
    try:
        _verify_publication_lock(ownership)
        if not _unlink_owned(ownership.path, ownership.identity):
            raise ValueError("lock identity changed")
        _fsync_directory(ownership.path.parent)
    except (OSError, ValueError, RuntimeError) as error:
        raise RuntimeError(
            f"aggregate publication lock release failed: {type(error).__name__}"
        ) from error


def _write_fsynced_staging(
    directory: Path, prefix: str, payload: bytes
) -> tuple[Path, FileIdentity]:
    descriptor = -1
    staging: Optional[Path] = None
    try:
        descriptor, raw_staging = tempfile.mkstemp(
            prefix=prefix, suffix=".tmp", dir=directory
        )
        staging = Path(raw_staging)
        if _supports_posix_file_modes():
            os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.close(descriptor)
        descriptor = -1
        identity = _regular_identity(staging)
        if identity is None:
            raise OSError("staging file disappeared")
        return staging, identity
    except OSError:
        if descriptor >= 0:
            os.close(descriptor)
        if staging is not None:
            try:
                staging.unlink()
            except FileNotFoundError:
                pass
        raise


def _reserve_backup_path(directory: Path, prefix: str) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        prefix=prefix, suffix=".backup", dir=directory
    )
    os.close(descriptor)
    path = Path(raw_path)
    path.unlink()
    return path


def _validate_public_target(path: Path) -> bool:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(mode):
        raise ValueError("unsafe public aggregate target")
    return True


def _replace_aggregate_pair_locked(
    csv_path: Path,
    csv_payload: bytes,
    json_path: Path,
    json_payload: bytes,
    ownership: PublicationLock,
) -> None:
    directory = csv_path.parent
    if json_path.parent != directory:
        raise ValueError("aggregate outputs must share one directory")
    if ownership.path != _lock_path(csv_path, json_path):
        raise RuntimeError("aggregate publication lock does not match output pair")
    csv_staging: Optional[Path] = None
    json_staging: Optional[Path] = None
    staging_identities: dict[Path, FileIdentity] = {}
    backups: dict[Path, Optional[tuple[Path, FileIdentity]]] = {
        csv_path: None,
        json_path: None,
    }
    original_identities: dict[Path, Optional[FileIdentity]] = {}
    installed_identities: dict[Path, FileIdentity] = {}
    committed = False
    rollback_failed = False
    try:
        _verify_publication_lock(ownership)
        for destination in (csv_path, json_path):
            _validate_public_target(destination)
            original_identities[destination] = _regular_identity(destination)
        csv_staging, csv_staging_identity = _write_fsynced_staging(
            directory, ".aggregate-csv-", csv_payload
        )
        staging_identities[csv_staging] = csv_staging_identity
        json_staging, json_staging_identity = _write_fsynced_staging(
            directory, ".aggregate-json-", json_payload
        )
        staging_identities[json_staging] = json_staging_identity
        for destination in (csv_path, json_path):
            _verify_publication_lock(ownership)
            if _regular_identity(destination) != original_identities[destination]:
                raise ValueError("public aggregate target changed during transaction")
            if original_identities[destination] is not None:
                backup = _reserve_backup_path(directory, ".aggregate-old-")
                os.replace(destination, backup)
                backup_identity = _regular_identity(backup)
                if backup_identity is not None:
                    backups[destination] = (backup, backup_identity)
                if backup_identity != original_identities[destination]:
                    raise ValueError("aggregate backup identity changed")
        _verify_publication_lock(ownership)
        os.replace(csv_staging, csv_path)
        installed_identity = _regular_identity(csv_path)
        if installed_identity != csv_staging_identity:
            raise ValueError("installed CSV identity changed")
        installed_identities[csv_path] = installed_identity
        csv_staging = None
        _verify_publication_lock(ownership)
        os.replace(json_staging, json_path)
        installed_identity = _regular_identity(json_path)
        if installed_identity != json_staging_identity:
            raise ValueError("installed JSON identity changed")
        installed_identities[json_path] = installed_identity
        json_staging = None
        _fsync_directory(directory)
        _verify_publication_lock(ownership)
        committed = True
    except RuntimeError:
        rollback_failed = True
        raise
    except (OSError, ValueError) as error:
        try:
            _verify_publication_lock(ownership)
        except RuntimeError as lock_error:
            rollback_failed = True
            raise RuntimeError("aggregate transaction lock ownership lost") from lock_error
        rollback_errors: list[str] = []
        for destination in (csv_path, json_path):
            backup_entry = backups[destination]
            try:
                installed_identity = installed_identities.get(destination)
                current_identity = _regular_identity(destination)
                if backup_entry is not None:
                    backup, backup_identity = backup_entry
                    if (
                        current_identity is not None
                        and current_identity != installed_identity
                    ):
                        raise OSError("foreign output appeared during rollback")
                    if not _identity_matches(backup, backup_identity):
                        raise OSError("backup identity changed")
                    os.replace(backup, destination)
                    backups[destination] = None
                elif original_identities[destination] is None and installed_identity is not None:
                    if not _unlink_owned(destination, installed_identity):
                        raise OSError("installed output identity changed")
                elif original_identities[destination] is None:
                    if current_identity is not None:
                        raise OSError("foreign output appeared during rollback")
                elif installed_identity is not None:
                    raise OSError("original backup is unavailable")
                elif current_identity != original_identities[destination]:
                    raise OSError("original output identity changed")
            except OSError as rollback_error:
                rollback_errors.append(type(rollback_error).__name__)
        try:
            _fsync_directory(directory)
        except OSError as rollback_error:
            rollback_errors.append(type(rollback_error).__name__)
        if rollback_errors:
            rollback_failed = True
            raise RuntimeError("aggregate transaction rollback failed") from error
        raise RuntimeError(
            f"aggregate transaction failed: {type(error).__name__}"
        ) from error
    finally:
        cleanup_entries = [
            (csv_staging, staging_identities.get(csv_staging) if csv_staging else None),
            (
                json_staging,
                staging_identities.get(json_staging) if json_staging else None,
            ),
        ]
        if not rollback_failed:
            for backup_entry in (backups[csv_path], backups[json_path]):
                if backup_entry is not None:
                    cleanup_entries.append(backup_entry)
        for temporary_path, temporary_identity in cleanup_entries:
            if temporary_path is not None and temporary_identity is not None:
                try:
                    _unlink_owned(temporary_path, temporary_identity)
                except OSError:
                    pass
        if committed:
            try:
                _fsync_directory(directory)
            except OSError:
                pass


def replace_aggregate_pair(
    csv_path: Path, csv_payload: bytes, json_path: Path, json_payload: bytes
) -> None:
    ownership = acquire_publication_lock(csv_path, json_path)
    transaction_error: Optional[BaseException] = None
    try:
        _replace_aggregate_pair_locked(
            csv_path, csv_payload, json_path, json_payload, ownership
        )
    except BaseException as error:
        transaction_error = error
        raise
    finally:
        try:
            release_publication_lock(ownership)
        except RuntimeError as release_error:
            if transaction_error is not None:
                raise RuntimeError(
                    "aggregate transaction and lock release failed"
                ) from transaction_error
            raise release_error


def render_csv(rows: list[dict[str, object]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=CSV_FIELDS, lineterminator="\n", extrasaction="raise"
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def aggregate_runs(
    *,
    root: Path,
    prefix: str,
    platform_tag: str,
    model: str,
    reasoning_effort: str,
    output_stem: str,
) -> tuple[Path, Path]:
    require_identifier("output_stem", output_stem)
    require_identifier("model", model)
    require_identifier("reasoning_effort", reasoning_effort)
    if platform_tag not in ("macos", "win11"):
        raise SystemExit("unsupported platform")
    tasks = frozen_tasks()
    slots = expected_run_slots(prefix, tasks)
    expected = set(slots)
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
        task, condition = slots[run_name]
        try:
            expected_run = expected_run_contract(
                root,
                run_name=run_name,
                fixture_set=FIXTURE_SET,
                task=task,
                condition=condition,
                platform=platform_tag,
                model=model,
                reasoning_effort=reasoning_effort,
            )
        except (OSError, ValueError) as error:
            raise SystemExit(
                f"expected run validation failed: {type(error).__name__}"
            ) from error
        if not is_complete_successful_run(run_dir, expected_run):
            raise SystemExit("formal run evidence is not complete and successful")
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
                expected_model=model,
                expected_effort=reasoning_effort,
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
    try:
        replace_aggregate_pair(
            csv_path,
            render_csv(rows),
            json_path,
            (json.dumps(summary, ensure_ascii=False, indent=2) + "\n").encode(
                "utf-8"
            ),
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise SystemExit(str(error)) from error
    return csv_path, json_path


def main() -> int:
    args = parse_args()
    csv_path, json_path = aggregate_runs(
        root=ROOT,
        prefix=args.prefix,
        platform_tag=args.platform_tag,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        output_stem=args.output_stem,
    )
    print(csv_path)
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
