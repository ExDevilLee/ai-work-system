#!/usr/bin/env python3
"""Generate deterministic Agent and human views from frozen fixture facts."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from fixture_model import VALID_STATUSES, canonical_json, load_manifest, validate_manifest


ROOT = Path(__file__).resolve().parent
_PACK_IDS = ("pack-a", "pack-b")
_PACK_FIELDS = frozenset({"schema_version", "pack_id", "records", "questions"})
_RECORD_FIELDS = frozenset(
    {"id", "title", "status", "scope", "source", "relations", "detail"}
)
_QUESTION_FIELDS = frozenset(
    {"id", "prompt", "choices", "correct_choice", "explanation"}
)
_CHOICE_FIELDS = frozenset({"id", "label"})
_RELATION_FIELDS = frozenset({"type", "target"})
_VALID_SCOPES = frozenset({"global", "project", "macos", "win11"})
_VALID_RELATIONS = frozenset({"supersedes", "conflicts-with"})
_EXPECTED_STATUS_COUNTS = Counter(
    {"active": 2, "superseded": 1, "conflict": 1, "pending-validation": 1}
)
_JUDGMENT_SUFFIXES = frozenset(
    {
        "current-active",
        "replacement-relation",
        "unresolved-conflict",
        "scope-boundary",
        "pending-observation",
    }
)
_PRIVATE_PATTERNS = (
    re.compile(r"/(?:Users|home)/[^/\s]+/", re.I),
    re.compile(r"[A-Za-z]:\\Users\\", re.I),
    re.compile(r"\b(?:provider|api[_ -]?key|access[_ -]?token|password)\b", re.I),
    re.compile(r"\b(?:thread|session)[_ -]?(?:id|identifier)\b", re.I),
)


def _manifest_or_raise(manifest: dict[str, object]) -> dict[str, object]:
    errors = validate_manifest(manifest)
    if errors:
        raise ValueError(
            "invalid manifest:\n" + "\n".join(f"- {error}" for error in errors)
        )
    return manifest


def render_flat_index(manifest: dict[str, object]) -> str:
    """Render the frozen answer-neutral Markdown navigation index."""
    _manifest_or_raise(manifest)
    records = manifest["records"]
    rows = [
        "# Flat Record Index",
        "",
        "| Title | Source | Summary | Updated At |",
        "| --- | --- | --- | --- |",
    ]
    for record in sorted(records, key=lambda item: item["id"]):
        rows.append(
            f"| {record['title']} | `{record['source']}` | "
            f"{record['summary']} | {record['updated_at']} |"
        )
    return "\n".join(rows) + "\n"


def _action_boundary(record: dict[str, object]) -> str:
    status = record["status"]
    relations = record.get("relations", [])
    if any(relation.get("type") == "supersedes" for relation in relations):
        return "Use the replacement in scope; retain its target only as history."
    if status == "active":
        return "Apply this item only within its declared scope."
    if status == "superseded":
        return "Keep for historical context only; do not use it for action."
    if status == "conflict":
        return "Pause selection until the competing evidence is resolved."
    return "Keep as an observation until review confirms a change."


def build_state_projection(manifest: dict[str, object]) -> dict[str, object]:
    """Build the exact frozen state projection without source body text."""
    _manifest_or_raise(manifest)
    records = []
    for record in sorted(manifest["records"], key=lambda item: item["id"]):
        records.append(
            {
                "id": record["id"],
                "status": record["status"],
                "scope": record["scope"],
                "source": record["source"],
                "relations": [
                    {"type": relation["type"], "target": relation["target"]}
                    for relation in record.get("relations", [])
                ],
                "action_boundary": _action_boundary(record),
            }
        )
    return {"schema_version": 1, "records": records}


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _all_strings(value: object):
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


def validate_human_pack(pack: dict[str, object]) -> list[str]:
    """Return all structural and governance errors in a human fixture pack."""
    errors: list[str] = []
    if not isinstance(pack, dict):
        return ["human pack must be an object"]
    if set(pack) != _PACK_FIELDS:
        errors.append("human pack fields must match the frozen schema")
    if type(pack.get("schema_version")) is not int or pack.get("schema_version") != 1:
        errors.append("human pack schema_version must be integer 1")
    pack_id = pack.get("pack_id")
    if pack_id not in _PACK_IDS:
        errors.append("human pack_id must be 'pack-a' or 'pack-b'")

    records = pack.get("records")
    if not isinstance(records, list) or len(records) != 5:
        errors.append("human pack records must contain exactly 5 records")
        records = records if isinstance(records, list) else []

    record_ids: list[str] = []
    status_counts: Counter[str] = Counter()
    relations: list[tuple[str, str, str]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"human record[{index}] must be an object")
            continue
        if set(record) != _RECORD_FIELDS:
            errors.append(f"human record[{index}] fields must match the frozen schema")
        for field in ("id", "title", "status", "scope", "source", "detail"):
            if not _nonempty_string(record.get(field)):
                errors.append(f"human record[{index}] {field} must be a nonempty string")
        record_id = record.get("id")
        if isinstance(record_id, str):
            record_ids.append(record_id)
        status = record.get("status")
        if not isinstance(status, str) or status not in VALID_STATUSES:
            errors.append(f"human record[{index}] has unsupported status")
        else:
            status_counts[status] += 1
        scope = record.get("scope")
        if not isinstance(scope, str) or scope not in _VALID_SCOPES:
            errors.append(f"human record[{index}] has unsupported scope")
        record_relations = record.get("relations")
        if not isinstance(record_relations, list):
            errors.append(f"human record[{index}] relations must be a list")
            continue
        for relation_index, relation in enumerate(record_relations):
            if not isinstance(relation, dict) or set(relation) != _RELATION_FIELDS:
                errors.append(
                    f"human record[{index}] relation[{relation_index}] fields are invalid"
                )
                continue
            relation_type = relation.get("type")
            target = relation.get("target")
            if (
                not isinstance(relation_type, str)
                or relation_type not in _VALID_RELATIONS
                or not _nonempty_string(target)
            ):
                errors.append(
                    f"human record[{index}] relation[{relation_index}] is invalid"
                )
            elif isinstance(record_id, str) and isinstance(target, str):
                relations.append((record_id, relation_type, target))

    if len(record_ids) != len(set(record_ids)):
        errors.append("human record IDs must be unique")
    if status_counts != _EXPECTED_STATUS_COUNTS:
        errors.append("human pack must use the frozen status counts")
    known_ids = set(record_ids)
    if any(target not in known_ids for _, _, target in relations):
        errors.append("human pack relation target must reference a record ID")
    supersedes = [relation for relation in relations if relation[1] == "supersedes"]
    by_id = {
        record["id"]: record
        for record in records
        if isinstance(record, dict) and isinstance(record.get("id"), str)
    }
    valid_supersedes = [
        relation
        for relation in supersedes
        if by_id.get(relation[0], {}).get("status") == "active"
        and by_id.get(relation[2], {}).get("status") == "superseded"
    ]
    if len(supersedes) != 1 or len(valid_supersedes) != 1:
        errors.append("exactly one active record must supersede the superseded record")
    if len(relations) != 1:
        errors.append("human pack must contain exactly one replacement relation")
    platform_active = [
        record
        for record in records
        if isinstance(record, dict)
        and record.get("status") == "active"
        and record.get("scope") in {"macos", "win11"}
    ]
    if len(platform_active) != 1:
        errors.append("exactly one active record must be platform-scoped")
    conflict_records = [
        record
        for record in records
        if isinstance(record, dict) and record.get("status") == "conflict"
    ]
    if len(conflict_records) == 1:
        detail = conflict_records[0].get("detail")
        values = (
            set(re.findall(r"\b\d+(?:\.\d+)?\b", detail))
            if isinstance(detail, str)
            else set()
        )
        if len(values) < 2:
            errors.append("conflict record detail must contain two distinct values")

    questions = pack.get("questions")
    if not isinstance(questions, list) or len(questions) != 5:
        errors.append("human pack questions must contain exactly 5 questions")
        questions = questions if isinstance(questions, list) else []
    question_ids: list[str] = []
    for index, question in enumerate(questions):
        if not isinstance(question, dict):
            errors.append(f"human question[{index}] must be an object")
            continue
        if set(question) != _QUESTION_FIELDS:
            errors.append(f"human question[{index}] fields must match the frozen schema")
        for field in ("id", "prompt", "correct_choice", "explanation"):
            if not _nonempty_string(question.get(field)):
                errors.append(f"human question[{index}] {field} must be a nonempty string")
        question_id = question.get("id")
        if isinstance(question_id, str):
            question_ids.append(question_id)
        choices = question.get("choices")
        if not isinstance(choices, list) or len(choices) != 3:
            errors.append(f"human question[{index}] choices must contain exactly 3 objects")
            continue
        choice_ids: list[str] = []
        for choice_index, choice in enumerate(choices):
            if not isinstance(choice, dict) or set(choice) != _CHOICE_FIELDS:
                errors.append(
                    f"human question[{index}] choice[{choice_index}] fields are invalid"
                )
                continue
            if not _nonempty_string(choice.get("id")) or not _nonempty_string(
                choice.get("label")
            ):
                errors.append(
                    f"human question[{index}] choice[{choice_index}] values must be nonempty"
                )
            if isinstance(choice.get("id"), str):
                choice_ids.append(choice["id"])
        if len(choice_ids) != len(set(choice_ids)):
            errors.append(f"human question[{index}] choice IDs must be unique")
        if question.get("correct_choice") not in choice_ids:
            errors.append(f"human question[{index}] correct_choice must reference a choice ID")
    if len(question_ids) != len(set(question_ids)):
        errors.append("human question IDs must be unique")
    judgment_suffixes = {
        question_id.split("-", 1)[1]
        for question_id in question_ids
        if "-" in question_id
    }
    if judgment_suffixes != _JUDGMENT_SUFFIXES:
        errors.append("human questions must cover the five governance judgments")

    if any(pattern.search(value) for value in _all_strings(pack) for pattern in _PRIVATE_PATTERNS):
        errors.append("human pack contains identity, private, provider, session, or path data")
    return errors


def _validated_pack(pack: dict[str, object]) -> dict[str, object]:
    errors = validate_human_pack(pack)
    if errors:
        raise ValueError(
            "invalid human pack:\n" + "\n".join(f"- {error}" for error in errors)
        )
    return pack


def _copy_relations(relations: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {"type": relation["type"], "target": relation["target"]}
        for relation in relations
    ]


def _copy_human_record(record: dict[str, object]) -> dict[str, object]:
    return {
        "id": record["id"],
        "title": record["title"],
        "status": record["status"],
        "scope": record["scope"],
        "source": record["source"],
        "relations": _copy_relations(record["relations"]),
        "detail": record["detail"],
    }


def _public_questions(pack: dict[str, object]) -> list[dict[str, object]]:
    return [
        {
            "id": question["id"],
            "prompt": question["prompt"],
            "choices": [
                {"id": choice["id"], "label": choice["label"]}
                for choice in question["choices"]
            ],
        }
        for question in pack["questions"]
    ]


def build_state_table(pack: dict[str, object]) -> dict[str, object]:
    """Build the answer-free tabular human view with all record facts intact."""
    _validated_pack(pack)
    return {
        "schema_version": 1,
        "pack_id": pack["pack_id"],
        "view_type": "state-table",
        "records": [_copy_human_record(record) for record in pack["records"]],
        "questions": _public_questions(pack),
    }


def build_visual_map(pack: dict[str, object]) -> dict[str, object]:
    """Build the answer-free map view with presentation-only additions."""
    _validated_pack(pack)
    group_by_status = {
        "active": "current",
        "superseded": "history",
        "conflict": "review",
        "pending-validation": "evidence",
    }
    tone_by_status = {
        "active": "positive",
        "superseded": "muted",
        "conflict": "critical",
        "pending-validation": "caution",
    }
    records = []
    for source_record in pack["records"]:
        record = _copy_human_record(source_record)
        record.update(
            {
                "group": group_by_status[record["status"]],
                "tone": tone_by_status[record["status"]],
                "edge_direction": "outbound" if record["relations"] else "none",
            }
        )
        records.append(record)
    return {
        "schema_version": 1,
        "pack_id": pack["pack_id"],
        "view_type": "visual-map",
        "records": records,
        "questions": _public_questions(pack),
    }


def human_fact_set(view: dict[str, object]) -> set[tuple[str, str, str, str]]:
    """Return the common identity/status/scope/source facts from a pack or view."""
    records = view.get("records") if isinstance(view, dict) else None
    if not isinstance(records, list):
        raise ValueError("human view records must be a list")
    facts: set[tuple[str, str, str, str]] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"human view record[{index}] must be an object")
        values = tuple(record.get(field) for field in ("id", "status", "scope", "source"))
        if not all(isinstance(value, str) and value for value in values):
            raise ValueError(f"human view record[{index}] has invalid fact fields")
        facts.add(values)
    return facts


def _load_pack(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot load human pack {path.name}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"cannot load human pack {path.name}: root must be an object")
    _validated_pack(value)
    return value


def _validate_pack_pair(pack_a: dict[str, object], pack_b: dict[str, object]) -> None:
    def record_shape(pack: dict[str, object]) -> tuple[Counter[str], Counter[str]]:
        return (
            Counter(record["scope"] for record in pack["records"]),
            Counter(
                relation["type"]
                for record in pack["records"]
                for relation in record["relations"]
            ),
        )

    errors = []
    if record_shape(pack_a) != record_shape(pack_b):
        errors.append("human packs must have equal scope and relation shapes")

    def distinct_values(pack: dict[str, object]) -> set[str]:
        values = set()
        for record in pack["records"]:
            values.update(
                str(record[field]) for field in ("id", "title", "source", "detail")
            )
        for question in pack["questions"]:
            values.update(
                str(question[field])
                for field in ("id", "prompt", "correct_choice", "explanation")
            )
            for choice in question["choices"]:
                values.update(str(choice[field]) for field in ("id", "label"))
        return values

    if distinct_values(pack_a) & distinct_values(pack_b):
        errors.append("human packs must use distinct IDs, titles, details, and content")
    if errors:
        raise ValueError(
            "invalid human pack pair:\n"
            + "\n".join(f"- {error}" for error in errors)
        )


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def generate_all(root: Path, fixture_set: str = "pilot-01") -> None:
    """Validate all sources, then atomically write the four generated views."""
    root = Path(root)
    fixture_root = root / "fixtures" / fixture_set
    manifest = load_manifest(fixture_root / "manifest.json")
    pack_a = _load_pack(root / "human-fixtures" / "pack-a.json")
    pack_b = _load_pack(root / "human-fixtures" / "pack-b.json")
    _validate_pack_pair(pack_a, pack_b)

    outputs = {
        "flat-index.md": render_flat_index(manifest).encode("utf-8"),
        "state-projection.json": canonical_json(build_state_projection(manifest)),
        "state-table.json": canonical_json(build_state_table(pack_a)),
        "visual-map.json": canonical_json(build_visual_map(pack_b)),
    }
    generated = fixture_root / "generated"
    for name, content in outputs.items():
        _atomic_write(generated / name, content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--fixture-set", default="pilot-01")
    arguments = parser.parse_args()
    generate_all(arguments.root, arguments.fixture_set)


if __name__ == "__main__":
    main()
