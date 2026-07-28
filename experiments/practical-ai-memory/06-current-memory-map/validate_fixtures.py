#!/usr/bin/env python3
"""Validate the frozen Agent fixtures and cross-file experiment contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable

from fixture_model import VALID_STATUSES, is_canonical_source, load_manifest


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
ANSWER_KEYS = frozenset(
    {"fact_state", "current_action", "boundary", "prohibited", "expected_sources"}
)
ANSWER_STRING_KEYS = ("fact_state", "current_action", "boundary", "prohibited")
PROJECTION_RECORD_FIELDS = frozenset(
    {"id", "status", "scope", "source", "relations", "action_boundary"}
)
HUMAN_VIEW_FIELDS = frozenset(
    {"schema_version", "pack_id", "view_type", "records", "questions"}
)
HUMAN_FACT_FIELDS = frozenset(
    {"id", "title", "status", "scope", "source", "relations", "detail"}
)
HUMAN_MAP_FIELDS = HUMAN_FACT_FIELDS | {"group", "tone", "edge_direction"}
HUMAN_PACK_FIELDS = frozenset({"schema_version", "pack_id", "records", "questions"})
HUMAN_QUESTION_FIELDS = frozenset(
    {"id", "prompt", "choices", "correct_choice", "explanation"}
)
HUMAN_RELATION_FIELDS = frozenset({"type", "target"})
PUBLIC_QUESTION_FIELDS = frozenset({"id", "prompt", "choices"})
PUBLIC_CHOICE_FIELDS = frozenset({"id", "label"})
HUMAN_SCOPES = frozenset({"global", "project", "macos", "win11"})
HUMAN_STATUS_COUNTS = Counter(
    {"active": 2, "superseded": 1, "conflict": 1, "pending-validation": 1}
)
HUMAN_JUDGMENTS = frozenset(
    {
        "current-active",
        "replacement-relation",
        "unresolved-conflict",
        "scope-boundary",
        "pending-observation",
    }
)
MAP_PRESENTATION = {
    "active": ("current", "positive"),
    "superseded": ("history", "muted"),
    "conflict": ("review", "critical"),
    "pending-validation": ("evidence", "caution"),
}
LIFECYCLE_WORDS = (
    "active",
    "approved",
    "approval",
    "authorized",
    "current",
    "currently",
    "disagreement",
    "historical",
    "incompatible",
    "old",
    "isolated",
    "replacement",
    "replaced",
    "replaces",
    "stable",
    "one-off",
    "superseded",
    "supersedes",
    "supersession",
    "conflict",
    "conflicts-with",
    "pending",
    "unapproved",
    "uncertain",
    "unresolved",
    "uncertainty",
)
FLAT_INDEX_HEADING = "# Flat Record Index"
FLAT_INDEX_HEADER = "| Title | Source | Summary | Updated At |"
FLAT_INDEX_SEPARATOR = "| --- | --- | --- | --- |"
PROTOCOL_PATHS = (
    "prompts/active-decision.md",
    "prompts/superseded-rule.md",
    "prompts/unresolved-conflict.md",
    "prompts/scope-boundary.md",
    "prompts/pending-observation.md",
    "fixtures/pilot-01/conditions/source-only/AGENTS.md",
    "fixtures/pilot-01/conditions/flat-index/AGENTS.md",
    "fixtures/pilot-01/conditions/state-projection/AGENTS.md",
)

_PRIVATE_PATTERNS = (
    (
        "POSIX absolute path",
        re.compile(r"(?<![:A-Za-z0-9_.-])/(?:[^/\s]+/)*[^/\s]+"),
    ),
    ("Windows drive path", re.compile(r"\b[A-Za-z]:[\\/][^\s]+")),
    ("Windows UNC path", re.compile(r"\\\\[^\\\s]+\\[^\s]+")),
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
        "user identity",
        re.compile(r"\b(?:username|user[_ -]?id|account[_ -]?id|email)\b", re.I),
    ),
    (
        "thread or session identifier",
        re.compile(r"\b(?:thread|session)[_ -]?(?:id|identifier)\b", re.I),
    ),
    (
        "UUID",
        re.compile(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
            r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
            re.I,
        ),
    ),
    (
        "real repository path",
        re.compile(r"\b(?:CodexClawProj|ai-work-system|codex-external-repos)\b"),
    ),
    (
        "storage address",
        re.compile(r"\b(?:s3|gs|az|file|https?)://[^\s]+", re.I),
    ),
)


def _has_control_characters(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _is_safe_protocol_path(value: object) -> bool:
    if not isinstance(value, str) or _has_control_characters(value):
        return False
    path = PurePosixPath(value)
    windows_path = PureWindowsPath(value)
    return (
        bool(path.parts)
        and "\\" not in value
        and not path.is_absolute()
        and not windows_path.drive
        and not windows_path.anchor
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _has_symlink_component(path: Path, boundary: Path) -> bool:
    try:
        relative = path.relative_to(boundary)
    except ValueError:
        return True
    current = boundary
    if current.is_symlink():
        return True
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _read_text(
    path: Path,
    label: str,
    errors: list[str],
    *,
    symlink_boundary: Path | None = None,
) -> str | None:
    try:
        if path.is_symlink() or (
            symlink_boundary is not None
            and _has_symlink_component(path, symlink_boundary)
        ):
            errors.append(f"symlinked fixture file is not allowed: {label}")
            return None
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        errors.append(f"missing {label}: {path.name}")
    except UnicodeError:
        errors.append(f"cannot read {label} as UTF-8: {path.name}")
    except (OSError, ValueError) as error:
        errors.append(f"cannot read {label}: {path.name}: {type(error).__name__}")
    return None


def _load_json(
    path: Path,
    label: str,
    errors: list[str],
    *,
    symlink_boundary: Path | None = None,
) -> Any | None:
    text = _read_text(
        path, label, errors, symlink_boundary=symlink_boundary
    )
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        errors.append(f"invalid {label} JSON: line {error.lineno}")
        return None


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _load_canonical_json(
    path: Path,
    label: str,
    errors: list[str],
    *,
    symlink_boundary: Path,
) -> Any | None:
    if path.is_symlink() or _has_symlink_component(path, symlink_boundary):
        errors.append(f"symlinked fixture file is not allowed: {label}")
        return None
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        errors.append(f"missing {label}: {path.name}")
        return None
    except OSError as error:
        errors.append(f"cannot read {label}: {path.name}: {type(error).__name__}")
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        errors.append(f"cannot read {label} as UTF-8: {path.name}")
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        errors.append(f"invalid {label} JSON: line {error.lineno}")
        return None
    try:
        canonical = _canonical_json_bytes(value)
    except (TypeError, ValueError):
        errors.append(f"invalid {label} JSON value")
        return value
    if raw != canonical:
        errors.append(f"{label} must use canonical JSON with one LF")
    return value


def _contains_answer_like_field(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z]", "", key.casefold()) if isinstance(key, str) else ""
            if (
                normalized in {"answer", "answers", "answerkey", "correctchoice", "explanation"}
                or normalized.startswith("correctanswer")
                or normalized in {"correct", "iscorrect", "solution", "rationale"}
                or "answer" in normalized
            ):
                return True
            if _contains_answer_like_field(item):
                return True
    elif isinstance(value, list):
        return any(_contains_answer_like_field(item) for item in value)
    return False


def _public_pack_questions(pack: Any) -> list[dict[str, Any]] | None:
    if not isinstance(pack, dict) or not isinstance(pack.get("questions"), list):
        return None
    public = []
    for question in pack["questions"]:
        if not isinstance(question, dict) or not isinstance(question.get("choices"), list):
            return None
        choices = []
        for choice in question["choices"]:
            if not isinstance(choice, dict):
                return None
            choices.append({"id": choice.get("id"), "label": choice.get("label")})
        public.append(
            {
                "id": question.get("id"),
                "prompt": question.get("prompt"),
                "choices": choices,
            }
        )
    return public


def _expected_human_records(pack: Any) -> list[dict[str, Any]] | None:
    if not isinstance(pack, dict) or not isinstance(pack.get("records"), list):
        return None
    records = []
    for record in pack["records"]:
        if not isinstance(record, dict):
            return None
        records.append({field: record.get(field) for field in HUMAN_FACT_FIELDS})
    return sorted(records, key=lambda record: record.get("id", ""))


def _validate_human_pack_sources(
    pack: Any, pack_id: str, errors: list[str]
) -> None:
    if not isinstance(pack, dict) or not isinstance(pack.get("records"), list):
        errors.append(f"human fixture {pack_id} records must be an array")
        return
    for index, record in enumerate(pack["records"]):
        if not isinstance(record, dict):
            continue
        record_id = record.get("id")
        source = record.get("source")
        expected = (
            f"synthetic/{pack_id}/{record_id.casefold()}.md"
            if isinstance(record_id, str)
            else None
        )
        windows_path = PureWindowsPath(source) if isinstance(source, str) else None
        if (
            not isinstance(source, str)
            or source != expected
            or "\\" in source
            or PurePosixPath(source).is_absolute()
            or (windows_path is not None and (windows_path.drive or windows_path.anchor))
            or any(part in {"", ".", ".."} for part in source.split("/"))
            or _has_control_characters(source)
        ):
            errors.append(
                f"human fixture {pack_id} record[{index}] must use its frozen synthetic source"
            )


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not _has_control_characters(value)


def _validate_raw_human_pack(
    path: Path, pack_id: str
) -> tuple[dict[str, Any] | None, list[str]]:
    """Validate one frozen human pack without using generator code."""
    errors: list[str] = []
    label = f"human fixture {pack_id}"
    pack = _load_canonical_json(
        path, label, errors, symlink_boundary=path.parent
    )
    if pack is None:
        return None, errors
    if not isinstance(pack, dict):
        return None, [*errors, f"{label} must be a JSON object"]
    if set(pack) != HUMAN_PACK_FIELDS:
        errors.append(f"{label} top-level fields must match contract")
    if type(pack.get("schema_version")) is not int or pack.get("schema_version") != 1:
        errors.append(f"{label} schema_version must be integer 1")
    if pack.get("pack_id") != pack_id or not isinstance(pack.get("pack_id"), str):
        errors.append(f"{label} pack_id must be {pack_id}")

    records = pack.get("records")
    if not isinstance(records, list) or len(records) != 5:
        errors.append(f"{label} must contain exactly 5 records")
        records = records if isinstance(records, list) else []
    record_ids: list[str] = []
    statuses: Counter[str] = Counter()
    relations: list[tuple[str, str]] = []
    records_by_id: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"{label} record[{index}] must be an object")
            continue
        if set(record) != HUMAN_FACT_FIELDS:
            errors.append(f"{label} record fields must match contract: index {index}")
        for field in ("id", "title", "status", "scope", "source", "detail"):
            if not _nonempty_text(record.get(field)):
                errors.append(f"{label} record {field} must be nonempty text: index {index}")
        record_id = record.get("id")
        if isinstance(record_id, str) and record_id:
            record_ids.append(record_id)
            records_by_id.setdefault(record_id, record)
        status = record.get("status")
        if isinstance(status, str) and status in VALID_STATUSES:
            statuses[status] += 1
        else:
            errors.append(f"{label} record status is invalid: index {index}")
        if record.get("scope") not in HUMAN_SCOPES:
            errors.append(f"{label} record scope is invalid: index {index}")
        record_relations = record.get("relations")
        if not isinstance(record_relations, list):
            errors.append(f"{label} record relations must be an array: index {index}")
            continue
        for relation_index, relation in enumerate(record_relations):
            if not isinstance(relation, dict) or set(relation) != HUMAN_RELATION_FIELDS:
                errors.append(
                    f"{label} relation fields must match contract: "
                    f"record {index} relation {relation_index}"
                )
                continue
            relation_type = relation.get("type")
            target = relation.get("target")
            if relation_type != "supersedes" or not _nonempty_text(target):
                errors.append(
                    f"{label} relation fields must contain supersedes and a text target: "
                    f"record {index} relation {relation_index}"
                )
                continue
            if isinstance(record_id, str) and isinstance(target, str):
                relations.append((record_id, target))

    if len(record_ids) != len(set(record_ids)):
        errors.append(f"{label} must use unique record IDs")
    if statuses != HUMAN_STATUS_COUNTS:
        errors.append(f"{label} must use the frozen status distribution")
    if len(relations) != 1:
        errors.append(f"{label} must contain exactly one supersedes relation")
    elif len(set(record_ids)) == len(record_ids):
        source_id, target_id = relations[0]
        source = records_by_id.get(source_id, {})
        target = records_by_id.get(target_id, {})
        if (
            source_id == target_id
            or source.get("status") != "active"
            or target.get("status") != "superseded"
            or source.get("scope") != target.get("scope")
        ):
            errors.append(f"{label} supersedes relation violates status or scope invariants")
    platform_active = [
        record
        for record in records
        if isinstance(record, dict)
        and record.get("status") == "active"
        and record.get("scope") in {"macos", "win11"}
    ]
    if len(platform_active) != 1:
        errors.append(f"{label} must contain exactly one platform-scoped active record")
    conflict_records = [
        record
        for record in records
        if isinstance(record, dict) and record.get("status") == "conflict"
    ]
    if len(conflict_records) == 1:
        detail = conflict_records[0].get("detail")
        values = set(re.findall(r"\b\d+(?:\.\d+)?\b", detail)) if isinstance(detail, str) else set()
        if len(values) < 2:
            errors.append(f"{label} conflict detail must contain two distinct values")
    _validate_human_pack_sources(pack, pack_id, errors)

    questions = pack.get("questions")
    if not isinstance(questions, list) or len(questions) != 5:
        errors.append(f"{label} must contain exactly 5 questions")
        questions = questions if isinstance(questions, list) else []
    question_ids: list[str] = []
    for index, question in enumerate(questions):
        if not isinstance(question, dict):
            errors.append(f"{label} question[{index}] must be an object")
            continue
        if set(question) != HUMAN_QUESTION_FIELDS:
            errors.append(f"{label} question fields must match contract: index {index}")
        for field in ("id", "prompt", "correct_choice", "explanation"):
            if not _nonempty_text(question.get(field)):
                errors.append(f"{label} question {field} must be nonempty text: index {index}")
        question_id = question.get("id")
        if isinstance(question_id, str) and question_id:
            question_ids.append(question_id)
        choices = question.get("choices")
        if not isinstance(choices, list) or len(choices) != 3:
            errors.append(f"{label} question[{index}] must contain exactly 3 choices")
            choices = choices if isinstance(choices, list) else []
        choice_ids: list[str] = []
        for choice_index, choice in enumerate(choices):
            if not isinstance(choice, dict) or set(choice) != PUBLIC_CHOICE_FIELDS:
                errors.append(
                    f"{label} choice fields must match contract: "
                    f"question {index} choice {choice_index}"
                )
                continue
            if not _nonempty_text(choice.get("id")) or not _nonempty_text(choice.get("label")):
                errors.append(
                    f"{label} choice values must be nonempty text: "
                    f"question {index} choice {choice_index}"
                )
            if isinstance(choice.get("id"), str) and choice["id"]:
                choice_ids.append(choice["id"])
        if len(choice_ids) != len(set(choice_ids)):
            errors.append(f"{label} question[{index}] must use unique choice IDs")
        if question.get("correct_choice") not in choice_ids:
            errors.append(f"{label} question[{index}] correct_choice must reference a choice ID")
    if len(question_ids) != len(set(question_ids)):
        errors.append(f"{label} must use unique question IDs")
    judgment_suffixes = {
        question_id.split("-", 1)[1]
        for question_id in question_ids
        if "-" in question_id
    }
    if judgment_suffixes != HUMAN_JUDGMENTS:
        errors.append(f"{label} questions must cover the five governance judgments")

    private_labels = {
        private_label
        for value in _all_strings(pack)
        for private_label, pattern in _PRIVATE_PATTERNS
        if pattern.search(value)
    }
    for private_label in sorted(private_labels):
        errors.append(f"{label} contains private-data marker ({private_label})")
    return pack, errors


def validate_human_view(
    path: Path,
    pack_path: Path,
    *,
    view_type: str,
    pack_id: str,
    validated_pack: dict[str, Any] | None = None,
) -> list[str]:
    """Independently validate one generated human view against its source pack."""
    errors: list[str] = []
    label = "generated state table" if view_type == "state-table" else "generated visual map"
    view = _load_canonical_json(
        path, label, errors, symlink_boundary=path.parent
    )
    pack = validated_pack
    if pack is None:
        pack, pack_errors = _validate_raw_human_pack(pack_path, pack_id)
        errors.extend(pack_errors)
    if view is None or pack is None:
        return errors
    short_label = "state table" if view_type == "state-table" else "visual map"
    if not isinstance(view, dict):
        return [*errors, f"{short_label} must be a JSON object"]
    if set(view) != HUMAN_VIEW_FIELDS:
        errors.append(f"{short_label} top-level fields must match contract")
    if type(view.get("schema_version")) is not int or view.get("schema_version") != 1:
        errors.append(f"{short_label} schema_version must be integer 1")
    if view.get("view_type") != view_type:
        errors.append(f"{short_label} view_type must be {view_type}")
    if view.get("pack_id") != pack_id or not isinstance(view.get("pack_id"), str):
        errors.append(f"{short_label} pack_id must be {pack_id}")
    if not isinstance(pack, dict) or pack.get("pack_id") != pack_id:
        errors.append(f"human fixture must have pack_id {pack_id}")

    questions = view.get("questions")
    expected_questions = _public_pack_questions(pack)
    if not isinstance(questions, list):
        errors.append(f"{short_label} questions must be an array")
    else:
        for index, question in enumerate(questions):
            if not isinstance(question, dict) or set(question) != PUBLIC_QUESTION_FIELDS:
                errors.append(f"{short_label} question fields must match contract: index {index}")
                continue
            choices = question.get("choices")
            if not isinstance(choices, list):
                errors.append(f"{short_label} choices must be an array: index {index}")
                continue
            for choice_index, choice in enumerate(choices):
                if not isinstance(choice, dict) or set(choice) != PUBLIC_CHOICE_FIELDS:
                    errors.append(
                        f"{short_label} choice fields must match contract: "
                        f"question {index} choice {choice_index}"
                    )
        if questions != expected_questions:
            errors.append(f"{short_label} questions do not match human pack")
    if _contains_answer_like_field(view):
        errors.append(f"{short_label} contains an answer-like field")

    records = view.get("records")
    expected_records = _expected_human_records(pack)
    allowed_fields = HUMAN_FACT_FIELDS if view_type == "state-table" else HUMAN_MAP_FIELDS
    comparable_records = []
    if not isinstance(records, list):
        errors.append(f"{short_label} records must be an array")
    else:
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                errors.append(f"{short_label} record[{index}] must be an object")
                continue
            if set(record) != allowed_fields:
                errors.append(f"{short_label} record fields must match contract: index {index}")
            comparable_records.append(
                {field: record.get(field) for field in HUMAN_FACT_FIELDS}
            )
            if view_type == "visual-map":
                status = record.get("status")
                expected_presentation = MAP_PRESENTATION.get(status)
                if not isinstance(status, str):
                    errors.append(f"visual map status must remain text: index {index}")
                if (
                    expected_presentation is None
                    or (record.get("group"), record.get("tone")) != expected_presentation
                    or record.get("edge_direction")
                    != ("outbound" if record.get("relations") else "none")
                ):
                    errors.append(f"visual map presentation fields are invalid: index {index}")
        if comparable_records != expected_records:
            errors.append(f"{short_label} facts do not match human pack")
    return errors


def _load_fixture_manifest(
    path: Path, fixture_root: Path, errors: list[str]
) -> dict[str, Any]:
    if _has_symlink_component(path, fixture_root):
        errors.append("symlinked fixture file is not allowed: manifest")
        return {}
    try:
        return load_manifest(path)
    except ValueError as error:
        errors.append(str(error))
    return {}


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


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


def contains_lifecycle_vocabulary(value: str) -> bool:
    normalized = _normalize_text(value)
    for word in LIFECYCLE_WORDS:
        pattern = re.escape(word).replace(r"\-", r"[-_ ]")
        if re.search(rf"(?<![a-z]){pattern}(?![a-z])", normalized):
            return True
    return False


def _contains_common_utf8_window(first: str, second: str, size: int = 32) -> bool:
    first_bytes = _normalize_text(first).encode("utf-8")
    second_bytes = _normalize_text(second).encode("utf-8")
    shorter, longer = sorted((first_bytes, second_bytes), key=len)
    if len(shorter) < size:
        return False
    return any(
        shorter[index : index + size] in longer
        for index in range(len(shorter) - size + 1)
    )


def _complete_paragraphs(body: str) -> tuple[str, ...]:
    paragraphs = []
    for paragraph in re.split(r"\n\s*\n", body):
        normalized = _normalize_text(paragraph)
        if normalized:
            paragraphs.append(normalized)
    return tuple(paragraphs)


def _flat_index_text(manifest: dict[str, Any]) -> str | None:
    records = manifest.get("records")
    if not isinstance(records, list):
        return None
    rows = [FLAT_INDEX_HEADING, "", FLAT_INDEX_HEADER, FLAT_INDEX_SEPARATOR]
    sortable_records = []
    for record in records:
        if not isinstance(record, dict):
            return None
        values = tuple(
            record.get(field) for field in ("id", "title", "source", "summary", "updated_at")
        )
        if not all(isinstance(value, str) for value in values):
            return None
        sortable_records.append(record)
    for record in sorted(sortable_records, key=lambda item: item["id"]):
        rows.append(
            f"| {record['title']} | `{record['source']}` | "
            f"{record['summary']} | {record['updated_at']} |"
        )
    return "\n".join(rows) + "\n"


def validate_flat_index(
    path: Path, manifest: dict[str, Any] | None = None
) -> list[str]:
    """Validate the deterministic, answer-neutral flat index contract.

    Required format is a single ``# Flat Record Index`` heading followed by a
    four-column Markdown table: Title, Source, Summary, Updated At. Rows are
    sorted by record ID and contain only manifest navigation fields.
    """
    errors: list[str] = []
    if path.is_symlink() or _has_symlink_component(path, path.parent):
        return ["symlinked fixture file is not allowed: generated flat index"]
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return [f"missing generated flat index: {path.name}"]
    except OSError as error:
        return [f"cannot read generated flat index: {path.name}: {type(error).__name__}"]
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        return [f"cannot read generated flat index as UTF-8: {path.name}"]
    if not raw.endswith(b"\n") or b"\r" in raw:
        errors.append("flat index does not match required UTF-8 bytes")
    if manifest is not None:
        expected = _flat_index_text(manifest)
        if expected is None or raw != expected.encode("utf-8"):
            if "flat index does not match required UTF-8 bytes" not in errors:
                errors.append("flat index does not match required UTF-8 bytes")
    if not text:
        return errors
    frozen_terms = tuple(VALID_STATUSES) + RELATION_KEYS
    if any(
        re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", text, re.I)
        for term in frozen_terms
    ):
        errors.append("flat index leaks status")
    if "action_boundary" in text.casefold() or "action boundary" in text.casefold():
        errors.append("flat index leaks action boundary")
    if contains_lifecycle_vocabulary(text):
        errors.append("flat index leaks answer-bearing lifecycle vocabulary")
    if manifest is not None and raw != (_flat_index_text(manifest) or "").encode("utf-8"):
        errors.append("flat index does not match required format")
    return errors


def validate_state_projection(
    path: Path,
    manifest: dict[str, Any],
    record_bodies: Iterable[str],
) -> list[str]:
    """Validate projection schema, manifest equivalence, and body separation."""
    errors: list[str] = []
    projection = _load_canonical_json(
        path,
        "generated state projection",
        errors,
        symlink_boundary=path.parent,
    )
    if projection is None:
        return errors
    if not isinstance(projection, dict):
        return [*errors, "state projection must be a JSON object"]
    if set(projection) != {"schema_version", "records"}:
        errors.append("state projection must contain only schema_version and records")
    if projection.get("schema_version") != 1 or type(projection.get("schema_version")) is not int:
        errors.append("state projection schema_version must be integer 1")
    projection_records = projection.get("records")
    if not isinstance(projection_records, list):
        errors.append("state projection records must be an array")
        return errors

    manifest_records = manifest.get("records", [])
    manifest_by_id = {
        record["id"]: record
        for record in manifest_records
        if isinstance(record, dict) and isinstance(record.get("id"), str)
    }
    projection_by_id: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(projection_records):
        if not isinstance(record, dict):
            errors.append(f"projection record[{index}] must be an object")
            continue
        if set(record) != PROJECTION_RECORD_FIELDS:
            errors.append(f"projection record fields must match contract: index {index}")
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id or record_id in projection_by_id:
            errors.append(f"projection record ID is missing or duplicated: index {index}")
        else:
            projection_by_id[record_id] = record
        action_boundary = record.get("action_boundary")
        if not isinstance(action_boundary, str) or not action_boundary.strip():
            errors.append(f"projection action_boundary must be nonempty: index {index}")

    if set(projection_by_id) != set(manifest_by_id) or len(projection_records) != len(manifest_by_id):
        errors.append("projection records do not match manifest")

    facts_match = set(projection_by_id) == set(manifest_by_id) and all(
        all(
            projection_by_id[record_id].get(field)
            == manifest_by_id[record_id].get(field)
            for field in ("status", "scope", "source")
        )
        for record_id in set(projection_by_id) & set(manifest_by_id)
    )
    if not facts_match:
        errors.append("projection facts do not match manifest")

    for record_id in set(projection_by_id) & set(manifest_by_id):
        if projection_by_id[record_id].get("relations") != manifest_by_id[record_id].get(
            "relations", []
        ):
            errors.append("projection relations do not match manifest")
            break

    projection_strings = tuple(_all_strings(projection_records))
    normalized_projection_strings = tuple(
        _normalize_text(value) for value in projection_strings
    )
    for body in record_bodies:
        paragraphs = _complete_paragraphs(body)
        copied_paragraph = any(
            paragraph in projection_value
            for paragraph in paragraphs
            for projection_value in normalized_projection_strings
        )
        copied_window = any(
            _contains_common_utf8_window(body, projection_value)
            for projection_value in projection_strings
        )
        if copied_paragraph or copied_window:
            errors.append("projection copies body")
            break
    return errors


def _expected_answer_phrases(answers: dict[str, Any]) -> set[str]:
    phrases: set[str] = set()
    for answer in answers.values():
        if not isinstance(answer, dict):
            continue
        for key in ANSWER_STRING_KEYS:
            phrase = answer.get(key)
            if isinstance(phrase, str) and len(phrase) >= 12:
                phrases.add(phrase.casefold())
    return phrases


def _validate_prompts(
    root: Path,
    answers: dict[str, Any],
    rubric_tasks: dict[str, Any],
    errors: list[str],
) -> list[Path]:
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
    prompt_paths = list(prompt_dir.glob("*.md")) if prompt_dir.is_dir() else []
    actual_prompts = {path.stem for path in prompt_paths}
    if actual_prompts != set(TASK_IDS):
        errors.append("prompts must cover exactly the five frozen tasks")

    for task_id in TASK_IDS:
        path = prompt_dir / f"{task_id}.md"
        text = _read_text(path, f"prompt for {task_id}", errors, symlink_boundary=prompt_dir)
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
        if contains_lifecycle_vocabulary(text):
            errors.append(f"prompt leaks answer-bearing lifecycle vocabulary: {task_id}")
        if not re.findall(r"(?m)^\s*\d+\.\s+", text):
            errors.append(f"prompt must ask numbered questions: {task_id}")
        if "relative" not in lowered or "source" not in lowered or "actually" not in lowered:
            errors.append(f"prompt must require relative sources actually used: {task_id}")
    return prompt_paths


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
        if set(answer) != ANSWER_KEYS:
            errors.append(f"expected answer must use exact answer keys: {task_id}")
        for key in ANSWER_STRING_KEYS:
            value = answer.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"expected answer field must be a nonempty string: {task_id}: {key}")
        sources = answer.get("expected_sources")
        if not isinstance(sources, list):
            errors.append(f"expected sources must be a list: {task_id}")
            continue
        strings_only = all(isinstance(source, str) for source in sources)
        if (
            not strings_only
            or len(sources) != 2
            or len(set(sources)) != 2
            or set(sources) != task_sources.get(task_id, set())
        ):
            errors.append(f"expected sources must be exactly the two task sources: {task_id}")
        for source in sources:
            if not isinstance(source, str) or not is_canonical_source(source):
                errors.append(f"invalid relative expected source: {task_id}")
                continue
            if source not in manifest_sources or not (fixture_root / source).is_file():
                errors.append(f"expected source does not exist: {task_id}: {source}")
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
            points = criterion.get("points")
            if points != 1 or type(points) is not int:
                errors.append(f"rubric criteria must be worth one point: {task_id}")
            else:
                points_total += 1
            description = criterion.get("description")
            if not isinstance(description, str) or not description.strip():
                errors.append(f"rubric criterion must have wording: {task_id}")
        if len(set(criterion_ids)) != len(criterion_ids):
            errors.append(f"rubric criterion IDs must be unique: {task_id}")
        if set(criterion_ids) != CRITERION_IDS:
            errors.append(f"rubric must use the five frozen criterion IDs: {task_id}")
        if task_rubric.get("max_score") != 5 or points_total != 5:
            errors.append(f"rubric max_score must equal five points: {task_id}")
        task_score_total += points_total

    totals = (
        rubric.get("per_task_max_score"),
        rubric.get("single_round_max_score"),
        rubric.get("formal_repeats"),
        rubric.get("formal_max_score"),
    )
    totals_valid = all(type(value) is int for value in totals)
    if totals_valid:
        per_task, single_round, repeats, formal = totals
        totals_valid = (
            per_task == 5
            and single_round == 25
            and repeats == 3
            and formal == 75
            and task_score_total == 25
            and single_round == task_score_total
            and formal == single_round * repeats
        )
    if not totals_valid:
        errors.append("rubric totals are inconsistent")
    return task_rubrics


def _scan_private_markers(
    paths: Iterable[Path], root: Path, errors: list[str]
) -> None:
    for path in sorted(set(paths), key=lambda item: item.as_posix()):
        if not path.is_file() and not path.is_symlink():
            continue
        text = _read_text(path, "privacy-scanned fixture file", errors, symlink_boundary=root)
        if text is None:
            continue
        for label, pattern in _PRIVATE_PATTERNS:
            if pattern.search(text):
                try:
                    relative = path.relative_to(root).as_posix()
                except ValueError:
                    relative = path.name
                errors.append(f"private-data marker ({label}): {relative}")


def _validate_frozen_ids(
    value: Any,
    expected: tuple[str, ...],
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(value, list):
        errors.append(f"manifest must contain exactly {len(expected)} {label} IDs")
        return
    if not all(isinstance(item, str) for item in value):
        errors.append(f"manifest {label} IDs must be strings")
        return
    if len(value) != len(expected) or set(value) != set(expected):
        errors.append(f"manifest must contain exactly {len(expected)} {label} IDs")


def _validate_protocol_lock(
    root: Path, fixture_root: Path, errors: list[str]
) -> Path:
    lock_path = fixture_root / "protocol-lock.json"
    protocol_lock = _load_json(
        lock_path,
        "protocol lock",
        errors,
        symlink_boundary=fixture_root,
    )
    if protocol_lock is None:
        return lock_path
    if not isinstance(protocol_lock, dict):
        errors.append("protocol lock must be a JSON object")
        return lock_path

    paths = tuple(protocol_lock)
    valid_hash_paths: set[str] = set()
    for entry_index, (path, expected_hash) in enumerate(
        protocol_lock.items(), start=1
    ):
        if not _is_safe_protocol_path(path):
            errors.append(f"protocol lock entry {entry_index} has unsafe path")
        if not isinstance(expected_hash, str) or not re.fullmatch(
            r"[0-9a-f]{64}", expected_hash
        ):
            errors.append(f"protocol lock entry {entry_index} has invalid hash")
        else:
            valid_hash_paths.add(path)
    if set(paths) != set(PROTOCOL_PATHS) or len(paths) != len(PROTOCOL_PATHS):
        errors.append("protocol lock must contain the exact protocol file set")

    for relative_path in PROTOCOL_PATHS:
        if relative_path not in valid_hash_paths:
            continue
        expected_hash = protocol_lock[relative_path]

        target = root / relative_path
        if _has_symlink_component(target, root):
            errors.append(
                f"symlinked fixture file is not allowed: protocol input {relative_path}"
            )
            continue
        try:
            if not target.is_file():
                errors.append(f"missing protocol input: {relative_path}")
                continue
            actual_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        except (OSError, ValueError) as error:
            errors.append(
                f"cannot hash protocol input: {relative_path}: {type(error).__name__}"
            )
            continue
        if actual_hash != expected_hash:
            errors.append(f"protocol hash mismatch: {relative_path}")
    return lock_path


def _resolved_within(path: Path, boundary: Path) -> bool:
    try:
        return os.path.commonpath((str(path.resolve()), str(boundary.resolve()))) == str(
            boundary.resolve()
        )
    except (OSError, ValueError):
        return False


def validate(
    root: Path,
    fixture_set: str = "pilot-01",
    require_generated: bool = False,
) -> list[str]:
    errors: list[str] = []
    root = Path(root)
    fixture_root = root / "fixtures" / fixture_set
    manifest_path = fixture_root / "manifest.json"
    manifest = _load_fixture_manifest(manifest_path, fixture_root, errors)

    _validate_frozen_ids(manifest.get("condition_ids"), CONDITION_IDS, "condition", errors)
    _validate_frozen_ids(manifest.get("task_ids"), TASK_IDS, "task", errors)

    records = manifest.get("records", [])
    if not isinstance(records, list) or len(records) != 10:
        errors.append("manifest must contain exactly 10 records")
        records = records if isinstance(records, list) else []

    manifest_sources: set[str] = set()
    task_sources = {task_id: set() for task_id in TASK_IDS}
    source_counts: Counter[str] = Counter()
    record_bodies: list[str] = []
    record_tasks: dict[str, str] = {}
    records_dir = fixture_root / "records"
    if records_dir.is_symlink():
        errors.append("symlinked fixture directory is not allowed: records")

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
        if not is_canonical_source(source):
            errors.append(f"record has invalid Markdown source: {record_id}")
            continue

        source_counts[source] += 1
        manifest_sources.add(source)
        if isinstance(task_id, str) and task_id in task_sources:
            task_sources[task_id].add(source)

        source_path = fixture_root / source
        if _has_symlink_component(source_path, records_dir):
            errors.append(f"symlinked fixture file is not allowed: record {record_id}")
            continue
        if not _resolved_within(source_path, records_dir):
            errors.append(f"record source resolves outside records directory: {record_id}")
            continue
        body = _read_text(
            source_path,
            f"record source for {record_id}",
            errors,
            symlink_boundary=records_dir,
        )
        if body is not None:
            record_bodies.append(body)

        title = record.get("title")
        summary = record.get("summary")
        updated_at = record.get("updated_at")
        navigation_values = (title, summary, updated_at)
        if not all(
            isinstance(value, str)
            and value.strip()
            and not _has_control_characters(value)
            and "|" not in value
            for value in navigation_values
        ):
            errors.append(f"record must have safe title, summary, and updated_at: {record_id}")
        if not isinstance(updated_at, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", updated_at):
            errors.append(f"record updated_at must use YYYY-MM-DD: {record_id}")
        filename = Path(source).stem
        if any(
            isinstance(value, str) and contains_lifecycle_vocabulary(value)
            for value in (filename, title, summary)
        ):
            errors.append(
                f"record metadata contains answer-bearing lifecycle vocabulary: {record_id}"
            )

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

    actual_records = (
        {path for path in records_dir.rglob("*.md") if path.is_file() or path.is_symlink()}
        if records_dir.is_dir()
        else set()
    )
    if len(actual_records) != 10:
        errors.append("fixture must contain exactly 10 Markdown records")
    expected_record_paths = {fixture_root / source for source in manifest_sources}
    if actual_records != expected_record_paths:
        errors.append("manifest sources and Markdown records must match exactly")

    conditions_root = fixture_root / "conditions"
    actual_conditions = (
        {path.name for path in conditions_root.iterdir() if path.is_dir()}
        if conditions_root.is_dir()
        else set()
    )
    if actual_conditions != set(CONDITION_IDS):
        errors.append("fixture must contain exactly the three frozen condition directories")
    condition_paths: list[Path] = []
    for condition_id in CONDITION_IDS:
        condition_root = conditions_root / condition_id
        agents_path = condition_root / "AGENTS.md"
        condition_paths.append(agents_path)
        if condition_root.is_symlink():
            errors.append(f"symlinked fixture directory is not allowed: {condition_id}")
            continue
        agents_text = _read_text(
            agents_path,
            f"condition instructions for {condition_id}",
            errors,
            symlink_boundary=conditions_root,
        )
        if condition_root.is_dir():
            for path in condition_root.rglob("*"):
                if not path.is_file() or path == agents_path:
                    continue
                if path.name in {"flat-index.md", "state-projection.json"}:
                    errors.append(f"generated artifact exists under condition directory: {condition_id}")
                else:
                    errors.append(f"condition directory contains copied records: {condition_id}")
        if agents_text is not None and any(
            body.strip() and body.strip() in agents_text for body in record_bodies
        ):
            errors.append(f"condition directory contains copied records: {condition_id}")

    answers_path = root / "expected" / "answers.json"
    rubric_path = root / "expected" / "rubric.json"
    answers_raw = _load_json(
        answers_path, "expected answers", errors, symlink_boundary=root / "expected"
    )
    answers = _validate_answers(
        answers_raw, fixture_root, manifest_sources, task_sources, errors
    )
    rubric_raw = _load_json(
        rubric_path, "rubric", errors, symlink_boundary=root / "expected"
    )
    rubric_tasks = _validate_rubric(rubric_raw, errors)
    prompt_paths = _validate_prompts(root, answers, rubric_tasks, errors)
    protocol_lock_path = _validate_protocol_lock(root, fixture_root, errors)

    generated_root = fixture_root / "generated"
    flat_index = generated_root / "flat-index.md"
    projection = generated_root / "state-projection.json"
    state_table = generated_root / "state-table.json"
    visual_map = generated_root / "visual-map.json"
    pack_a_path = root / "human-fixtures" / "pack-a.json"
    pack_b_path = root / "human-fixtures" / "pack-b.json"
    if require_generated:
        pack_a, pack_a_errors = _validate_raw_human_pack(pack_a_path, "pack-a")
        pack_b, pack_b_errors = _validate_raw_human_pack(pack_b_path, "pack-b")
        errors.extend(pack_a_errors)
        errors.extend(pack_b_errors)
        if not flat_index.exists() and not flat_index.is_symlink():
            errors.append("missing generated flat index: generated/flat-index.md")
        else:
            errors.extend(validate_flat_index(flat_index, manifest))
        if not projection.exists() and not projection.is_symlink():
            errors.append(
                "missing generated state projection: generated/state-projection.json"
            )
        else:
            errors.extend(validate_state_projection(projection, manifest, record_bodies))
        if not state_table.exists() and not state_table.is_symlink():
            errors.append("missing generated state table: generated/state-table.json")
        elif pack_a is not None and not pack_a_errors:
            errors.extend(
                validate_human_view(
                    state_table,
                    pack_a_path,
                    view_type="state-table",
                    pack_id="pack-a",
                    validated_pack=pack_a,
                )
            )
        if not visual_map.exists() and not visual_map.is_symlink():
            errors.append("missing generated visual map: generated/visual-map.json")
        elif pack_b is not None and not pack_b_errors:
            errors.extend(
                validate_human_view(
                    visual_map,
                    pack_b_path,
                    view_type="visual-map",
                    pack_id="pack-b",
                    validated_pack=pack_b,
                )
            )

    privacy_paths = [
        manifest_path,
        protocol_lock_path,
        answers_path,
        rubric_path,
        pack_a_path,
        pack_b_path,
    ]
    privacy_paths.extend(actual_records)
    privacy_paths.extend(condition_paths)
    privacy_paths.extend(prompt_paths)
    if generated_root.is_dir():
        privacy_paths.extend(generated_root.rglob("*"))
    _scan_private_markers(privacy_paths, root, errors)

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--fixture-set", default="pilot-01")
    parser.add_argument("--require-generated", action="store_true")
    arguments = parser.parse_args(argv)
    errors = validate(
        arguments.root,
        fixture_set=arguments.fixture_set,
        require_generated=arguments.require_generated,
    )
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        return 1
    print("fixture validation passed: conditions=3, tasks=5, records=10")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
