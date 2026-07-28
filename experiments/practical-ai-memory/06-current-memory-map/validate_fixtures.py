#!/usr/bin/env python3
"""Validate the frozen Agent fixtures and cross-file experiment contract."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable

from fixture_model import VALID_STATUSES, load_manifest


ROOT = Path(__file__).resolve().parent
CONDITION_IDS = ("source-only", "flat-index", "state-projection")
TASK_IDS = (
    "active-decision",
    "superseded-rule",
    "unresolved-conflict",
    "scope-boundary",
    "pending-observation",
)
RELATION_KEYS = ("supersedes", "conflicts-with")
CRITERION_IDS = frozenset(
    {
        "correct-fact-state",
        "correct-current-action",
        "correct-boundary",
        "no-prohibited-conclusion",
        "correct-source-citation",
    }
)

_PRIVATE_PATTERNS = (
    ("POSIX user path", re.compile(r"/(?:Users|home)/[^/\s]+/")),
    ("Windows user path", re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+", re.I)),
    (
        "credential or API key",
        re.compile(
            r"\b(?:api[_ -]?key|access[_ -]?token|client[_ -]?secret|password|"
            r"bearer)\b|\bsk-[A-Za-z0-9_-]{8,}",
            re.I,
        ),
    ),
    ("provider field or name", re.compile(r"\bprovider\b", re.I)),
    (
        "thread or session identifier",
        re.compile(r"\b(?:thread|session)[_ -]?(?:id|identifier)\b", re.I),
    ),
    (
        "thread or session identifier",
        re.compile(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
            r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
            re.I,
        ),
    ),
    (
        "real repository path",
        re.compile(r"\b(?:CodexClawProj|ai-work-system|codex-external-repos)\b"),
    ),
)


def _read_text(path: Path, label: str, errors: list[str]) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        errors.append(f"missing {label}: {path.name}")
    except (OSError, UnicodeError) as error:
        errors.append(f"cannot read {label} as UTF-8: {path.name}: {error}")
    return None


def _load_json(path: Path, label: str, errors: list[str]) -> Any | None:
    text = _read_text(path, label, errors)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        errors.append(f"invalid {label} JSON: {error}")
        return None


def _is_relative_record_source(source: object) -> bool:
    if not isinstance(source, str):
        return False
    path = PurePosixPath(source)
    windows_path = PureWindowsPath(source)
    return (
        "\\" not in source
        and not path.is_absolute()
        and not windows_path.drive
        and len(path.parts) > 1
        and path.parts[0] == "records"
        and path.suffix == ".md"
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _all_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                yield key
            yield from _all_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _all_strings(item)


def validate_flat_index(path: Path) -> list[str]:
    """Reject answer-bearing lifecycle fields in the generated flat index."""
    errors: list[str] = []
    text = _read_text(path, "generated flat index", errors)
    if text is None:
        return errors
    frozen_terms = tuple(VALID_STATUSES) + RELATION_KEYS
    if any(re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", text, re.I) for term in frozen_terms):
        errors.append("flat index leaks status")
    return errors


def validate_state_projection(path: Path, record_bodies: Iterable[str]) -> list[str]:
    """Reject generated projections that copy a complete source body."""
    errors: list[str] = []
    projection = _load_json(path, "generated state projection", errors)
    if projection is None:
        return errors
    projection_strings = tuple(_all_strings(projection))
    for body in record_bodies:
        normalized = body.strip()
        if normalized and any(normalized in value for value in projection_strings):
            errors.append("projection copies body")
            break
    return errors


def _expected_answer_phrases(answers: dict[str, Any]) -> set[str]:
    phrases: set[str] = set()
    for answer in answers.values():
        if not isinstance(answer, dict):
            continue
        for key, value in answer.items():
            if key == "expected_sources":
                continue
            for phrase in _all_strings(value):
                if len(phrase) >= 12 and any(character.isspace() for character in phrase):
                    phrases.add(phrase.casefold())
    return phrases


def _validate_prompts(
    root: Path,
    answers: dict[str, Any],
    rubric_tasks: dict[str, Any],
    errors: list[str],
) -> None:
    expected_phrases = _expected_answer_phrases(answers)
    rubric_terms: set[str] = set()
    for task_rubric in rubric_tasks.values():
        if not isinstance(task_rubric, dict):
            continue
        criteria = task_rubric.get("criteria", [])
        if not isinstance(criteria, list):
            continue
        for criterion in criteria:
            if not isinstance(criterion, dict):
                continue
            for field in ("id", "description"):
                value = criterion.get(field)
                if isinstance(value, str):
                    rubric_terms.add(value.casefold())

    prompt_dir = root / "prompts"
    actual_prompts = {path.stem for path in prompt_dir.glob("*.md")}
    if actual_prompts != set(TASK_IDS):
        errors.append("prompts must cover exactly the five frozen tasks")

    for task_id in TASK_IDS:
        path = prompt_dir / f"{task_id}.md"
        text = _read_text(path, f"prompt for {task_id}", errors)
        if text is None:
            continue
        lowered = text.casefold()
        if any(condition.casefold() in lowered for condition in CONDITION_IDS):
            errors.append(f"prompt leaks condition name: {task_id}")
        if re.search(
            r"(?:fixtures/|records/[A-Za-z0-9_.-]+\.md|"
            r"generated/(?:flat-index\.md|state-projection\.json))",
            text,
            re.I,
        ):
            errors.append(f"prompt leaks direct fixture path: {task_id}")
        if any(
            re.search(rf"(?<![\w-]){re.escape(status)}(?![\w-])", text, re.I)
            for status in VALID_STATUSES
        ):
            errors.append(f"prompt leaks status enum value: {task_id}")
        if any(phrase in lowered for phrase in expected_phrases):
            errors.append(f"prompt leaks expected answer term: {task_id}")
        if any(term in lowered for term in rubric_terms):
            errors.append(f"prompt leaks rubric ID or wording: {task_id}")
        numbered_questions = re.findall(r"(?m)^\s*\d+\.\s+", text)
        if not numbered_questions:
            errors.append(f"prompt must ask numbered questions: {task_id}")
        if "relative" not in lowered or "source" not in lowered or "actually" not in lowered:
            errors.append(f"prompt must require relative sources actually used: {task_id}")


def _validate_answers(
    answers: Any,
    fixture_root: Path,
    manifest_sources: set[str],
    task_sources: dict[str, set[str]],
    errors: list[str],
) -> dict[str, Any]:
    if not isinstance(answers, dict):
        errors.append("expected answers must be an object")
        return {}
    if set(answers) != set(TASK_IDS):
        errors.append("expected answers must cover exactly the five frozen tasks")
    for task_id in TASK_IDS:
        answer = answers.get(task_id)
        if not isinstance(answer, dict):
            errors.append(f"expected answer must be an object: {task_id}")
            continue
        sources = answer.get("expected_sources")
        if not isinstance(sources, list) or not sources:
            errors.append(f"expected sources must be a non-empty list: {task_id}")
            continue
        for source in sources:
            if not _is_relative_record_source(source):
                errors.append(f"invalid relative expected source: {task_id}")
                continue
            if source not in manifest_sources or not (fixture_root / source).is_file():
                errors.append(f"expected source does not exist: {task_id}: {source}")
            elif source not in task_sources.get(task_id, set()):
                errors.append(f"expected source belongs to another task: {task_id}: {source}")
    return answers


def _validate_rubric(rubric: Any, errors: list[str]) -> dict[str, Any]:
    if not isinstance(rubric, dict):
        errors.append("rubric must be an object")
        return {}
    task_rubrics = rubric.get("tasks")
    if not isinstance(task_rubrics, dict) or set(task_rubrics) != set(TASK_IDS):
        errors.append("rubric must cover exactly the five frozen tasks")
        task_rubrics = task_rubrics if isinstance(task_rubrics, dict) else {}

    task_score_total = 0
    for task_id in TASK_IDS:
        task_rubric = task_rubrics.get(task_id)
        if not isinstance(task_rubric, dict):
            errors.append(f"missing task rubric: {task_id}")
            continue
        criteria = task_rubric.get("criteria")
        if not isinstance(criteria, list) or len(criteria) != 5:
            errors.append(f"rubric must contain exactly five criteria: {task_id}")
            continue
        criterion_ids = []
        points_total = 0
        for criterion in criteria:
            if not isinstance(criterion, dict):
                errors.append(f"rubric criterion must be an object: {task_id}")
                continue
            criterion_id = criterion.get("id")
            if not isinstance(criterion_id, str) or not criterion_id:
                errors.append(f"rubric criterion must have an ID: {task_id}")
            else:
                criterion_ids.append(criterion_id)
            if criterion.get("points") != 1 or type(criterion.get("points")) is not int:
                errors.append(f"rubric criteria must be worth one point: {task_id}")
            else:
                points_total += 1
            if not isinstance(criterion.get("description"), str) or not criterion["description"].strip():
                errors.append(f"rubric criterion must have wording: {task_id}")
        if len(set(criterion_ids)) != len(criterion_ids):
            errors.append(f"rubric criterion IDs must be unique: {task_id}")
        if set(criterion_ids) != CRITERION_IDS:
            errors.append(
                f"rubric must use the five frozen criterion IDs: {task_id}"
            )
        if task_rubric.get("max_score") != 5 or points_total != 5:
            errors.append(f"rubric max_score must equal five points: {task_id}")
        task_score_total += points_total

    totals_valid = (
        rubric.get("per_task_max_score") == 5
        and rubric.get("single_round_max_score") == 25
        and rubric.get("formal_repeats") == 3
        and rubric.get("formal_max_score") == 75
        and task_score_total == 25
        and rubric.get("single_round_max_score") == task_score_total
        and rubric.get("formal_max_score")
        == rubric.get("single_round_max_score", 0) * rubric.get("formal_repeats", 0)
    )
    if not totals_valid:
        errors.append("rubric totals are inconsistent")
    return task_rubrics


def _scan_private_markers(paths: Iterable[Path], root: Path, errors: list[str]) -> None:
    for path in sorted(set(paths), key=lambda item: item.as_posix()):
        if not path.is_file():
            continue
        text = _read_text(path, "privacy-scanned fixture file", errors)
        if text is None:
            continue
        for label, pattern in _PRIVATE_PATTERNS:
            if pattern.search(text):
                relative = path.relative_to(root).as_posix()
                errors.append(f"private-data marker ({label}): {relative}")


def validate(
    root: Path,
    fixture_set: str = "pilot-01",
    require_generated: bool = False,
) -> list[str]:
    errors: list[str] = []
    root = Path(root)
    fixture_root = root / "fixtures" / fixture_set
    manifest_path = fixture_root / "manifest.json"
    try:
        manifest = load_manifest(manifest_path)
    except ValueError as error:
        errors.append(str(error))
        manifest = {}

    condition_ids = manifest.get("condition_ids") if isinstance(manifest, dict) else None
    task_ids = manifest.get("task_ids") if isinstance(manifest, dict) else None
    if not isinstance(condition_ids, list) or set(condition_ids) != set(CONDITION_IDS) or len(condition_ids) != 3:
        errors.append("manifest must contain exactly 3 condition IDs")
    if not isinstance(task_ids, list) or set(task_ids) != set(TASK_IDS) or len(task_ids) != 5:
        errors.append("manifest must contain exactly 5 task IDs")

    records = manifest.get("records", []) if isinstance(manifest, dict) else []
    if not isinstance(records, list) or len(records) != 10:
        errors.append("manifest must contain exactly 10 records")
        records = records if isinstance(records, list) else []

    manifest_sources: set[str] = set()
    task_sources = {task_id: set() for task_id in TASK_IDS}
    source_counts: Counter[str] = Counter()
    record_bodies: list[str] = []
    record_tasks: dict[str, str] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        record_id = record.get("id")
        task_id = record.get("task_id")
        source = record.get("source")
        if not isinstance(task_id, str) or task_id not in TASK_IDS:
            errors.append(f"record has missing or invalid task ID: {record_id}")
        elif isinstance(record_id, str):
            record_tasks[record_id] = task_id
        if not _is_relative_record_source(source):
            errors.append(f"record has invalid Markdown source: {record_id}")
            continue
        source_counts[source] += 1
        manifest_sources.add(source)
        if isinstance(task_id, str) and task_id in task_sources:
            task_sources[task_id].add(source)
        source_path = fixture_root / source
        body = _read_text(source_path, f"record source for {record_id}", errors)
        if body is not None:
            record_bodies.append(body)

    for source, count in source_counts.items():
        if count != 1:
            errors.append(f"record source must belong to exactly one task: {source}")
    for task_id in TASK_IDS:
        if len(task_sources[task_id]) != 2:
            errors.append(f"task must contain exactly two source records: {task_id}")
    for record in records:
        if not isinstance(record, dict):
            continue
        source_task = record.get("task_id")
        relations = record.get("relations", [])
        if not isinstance(relations, list):
            continue
        for relation in relations:
            if not isinstance(relation, dict):
                continue
            target_task = record_tasks.get(relation.get("target"))
            if target_task is not None and target_task != source_task:
                errors.append(f"relation crosses task boundary: {record.get('id')}")

    records_dir = fixture_root / "records"
    actual_records = set(records_dir.rglob("*.md")) if records_dir.is_dir() else set()
    if len(actual_records) != 10:
        errors.append("fixture must contain exactly 10 Markdown records")
    expected_record_paths = {fixture_root / source for source in manifest_sources}
    if actual_records != expected_record_paths:
        errors.append("manifest sources and Markdown records must match exactly")

    conditions_root = fixture_root / "conditions"
    actual_conditions = {path.name for path in conditions_root.iterdir() if path.is_dir()} if conditions_root.is_dir() else set()
    if actual_conditions != set(CONDITION_IDS):
        errors.append("fixture must contain exactly the three frozen condition directories")
    for condition_id in CONDITION_IDS:
        condition_root = conditions_root / condition_id
        agents_path = condition_root / "AGENTS.md"
        _read_text(agents_path, f"condition instructions for {condition_id}", errors)
        if condition_root.is_dir():
            for path in condition_root.rglob("*"):
                if not path.is_file() or path == agents_path:
                    continue
                if path.name in {"flat-index.md", "state-projection.json"}:
                    errors.append(f"generated artifact exists under condition directory: {condition_id}")
                else:
                    errors.append(f"condition directory contains copied records: {condition_id}")
            agents_text = agents_path.read_text(encoding="utf-8") if agents_path.is_file() else ""
            if any(body.strip() and body.strip() in agents_text for body in record_bodies):
                errors.append(f"condition directory contains copied records: {condition_id}")

    answers_raw = _load_json(root / "expected" / "answers.json", "expected answers", errors)
    answers = _validate_answers(
        answers_raw, fixture_root, manifest_sources, task_sources, errors
    )
    rubric_raw = _load_json(root / "expected" / "rubric.json", "rubric", errors)
    rubric_tasks = _validate_rubric(rubric_raw, errors)
    _validate_prompts(root, answers, rubric_tasks, errors)

    privacy_paths = [manifest_path]
    privacy_paths.extend(actual_records)
    privacy_paths.extend(conditions_root.rglob("*.md") if conditions_root.is_dir() else [])
    privacy_paths.extend((root / "prompts").glob("*.md"))
    privacy_paths.extend((root / "expected").glob("*.json"))
    _scan_private_markers(privacy_paths, root, errors)

    if require_generated:
        generated_root = fixture_root / "generated"
        flat_index = generated_root / "flat-index.md"
        projection = generated_root / "state-projection.json"
        if not flat_index.is_file():
            errors.append("missing generated flat index: generated/flat-index.md")
        else:
            errors.extend(validate_flat_index(flat_index))
        if not projection.is_file():
            errors.append(
                "missing generated state projection: generated/state-projection.json"
            )
        else:
            errors.extend(validate_state_projection(projection, record_bodies))

    return errors


def main() -> int:
    errors = validate(ROOT)
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        return 1
    print("fixture validation passed: conditions=3, tasks=5, records=10")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
