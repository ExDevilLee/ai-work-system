#!/usr/bin/env python3
"""Generate deterministic Agent and human views from frozen fixture facts."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import tempfile
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath

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
    ("provider", re.compile(r"\bprovider\b", re.I)),
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
    ("storage address", re.compile(r"\b(?:s3|gs|az|file|https?)://[^\s]+", re.I)),
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
    if any(relation.get("type") == "conflicts-with" for relation in relations):
        return "Pause selection until the competing evidence is resolved."
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
        source = record.get("source")
        expected_source = (
            f"synthetic/{pack_id}/{record_id.casefold()}.md"
            if isinstance(pack_id, str) and isinstance(record_id, str)
            else None
        )
        if (
            not isinstance(source, str)
            or source != expected_source
            or "\\" in source
            or PurePosixPath(source).is_absolute()
            or PureWindowsPath(source).drive
            or PureWindowsPath(source).anchor
            or any(
                component in {"", ".", ".."} for component in source.split("/")
            )
            or any(ord(character) < 32 or ord(character) == 127 for character in source)
        ):
            errors.append(
                f"human record[{index}] must use its frozen synthetic source"
            )
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
        and by_id.get(relation[0], {}).get("scope")
        == by_id.get(relation[2], {}).get("scope")
    ]
    if len(supersedes) != 1 or len(valid_supersedes) != 1:
        errors.append("exactly one active record must supersede the superseded record")
    if len(relations) != 1:
        errors.append("human pack must contain exactly one replacement relation")
    if len(supersedes) == 1 and (
        by_id.get(supersedes[0][0], {}).get("scope")
        != by_id.get(supersedes[0][2], {}).get("scope")
    ):
        errors.append("human supersedes records must have the same scope")
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

    private_labels = {
        label
        for value in _all_strings(pack)
        for label, pattern in _PRIVATE_PATTERNS
        if pattern.search(value)
    }
    for label in sorted(private_labels):
        errors.append(f"human pack contains private-data marker ({label})")
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
        "records": [
            _copy_human_record(record)
            for record in sorted(pack["records"], key=lambda item: item["id"])
        ],
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
    for source_record in sorted(pack["records"], key=lambda item: item["id"]):
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


def _load_pack(path: Path, *, validate: bool = True) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot load human pack {path.name}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"cannot load human pack {path.name}: root must be an object")
    if validate:
        _validated_pack(value)
    return value


def _is_safe_fixture_set(value: object) -> bool:
    if not isinstance(value, str) or not value or value in {".", ".."}:
        return False
    windows_path = PureWindowsPath(value)
    return (
        "/" not in value
        and "\\" not in value
        and not windows_path.drive
        and not windows_path.anchor
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def _is_within(path: Path, boundary: Path) -> bool:
    try:
        return os.path.commonpath((str(path.resolve()), str(boundary.resolve()))) == str(
            boundary.resolve()
        )
    except (OSError, ValueError):
        return False


def _has_symlink_component(path: Path, boundary: Path) -> bool:
    try:
        relative = path.relative_to(boundary)
    except ValueError:
        return True
    current = boundary
    if current.is_symlink():
        return True
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            return True
    return False


def _generation_paths(
    root: Path, fixture_set: str
) -> tuple[Path, Path, Path, dict[str, Path]]:
    if not _is_safe_fixture_set(fixture_set):
        raise ValueError("fixture_set must be one safe path component")
    root = Path(root).absolute()
    if not root.is_dir() or root.is_symlink():
        raise ValueError("generation root must be a real directory, not a symlink")
    fixture_root = root / "fixtures" / fixture_set
    manifest_path = fixture_root / "manifest.json"
    pack_a_path = root / "human-fixtures" / "pack-a.json"
    pack_b_path = root / "human-fixtures" / "pack-b.json"
    generated = fixture_root / "generated"
    outputs = {
        name: generated / name
        for name in (
            "flat-index.md",
            "state-projection.json",
            "state-table.json",
            "visual-map.json",
        )
    }
    checks = (
        (fixture_root, "fixture root"),
        (manifest_path, "manifest"),
        (pack_a_path, "human pack-a"),
        (pack_b_path, "human pack-b"),
        (generated, "generated parent"),
        *((path, f"generated output {name}") for name, path in outputs.items()),
    )
    for path, label in checks:
        if _has_symlink_component(path, root):
            raise ValueError(f"{label} must not contain a symlink component")
        if not _is_within(path, root):
            raise ValueError(f"{label} must remain under generation root")
    return manifest_path, pack_a_path, pack_b_path, outputs


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
    if pack_a.get("pack_id") != "pack-a":
        errors.append("first human pack must have pack_id 'pack-a'")
    if pack_b.get("pack_id") != "pack-b":
        errors.append("second human pack must have pack_id 'pack-b'")
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


def _validate_pack_bindings(
    pack_a: dict[str, object], pack_b: dict[str, object]
) -> None:
    errors = []
    if pack_a.get("pack_id") != "pack-a":
        errors.append("first human pack must have pack_id 'pack-a'")
    if pack_b.get("pack_id") != "pack-b":
        errors.append("second human pack must have pack_id 'pack-b'")
    if errors:
        raise ValueError(
            "invalid human pack pair:\n"
            + "\n".join(f"- {error}" for error in errors)
        )


def _open_staged_file(directory: Path, name: str):
    return tempfile.NamedTemporaryFile(
        mode="wb",
        dir=directory,
        prefix=f".{name}.",
        suffix=".tmp",
        delete=False,
    )


def _write_staged_file(temporary, content: bytes) -> None:
    temporary.write(content)


def _flush_staged_file(temporary) -> None:
    temporary.flush()


def _supports_posix_file_modes() -> bool:
    """Whether this platform can preserve POSIX permission bits."""
    return os.name != "nt"


def _set_staged_mode(path: Path, mode: int) -> None:
    if _supports_posix_file_modes():
        os.chmod(path, mode)


def _fsync_staged_file(temporary) -> None:
    os.fsync(temporary.fileno())


def _replace_staged_file(staged: Path, output: Path) -> None:
    os.replace(staged, output)


def _validate_output_bytes(outputs: dict[str, bytes]) -> None:
    expected_names = {
        "flat-index.md",
        "state-projection.json",
        "state-table.json",
        "visual-map.json",
    }
    if set(outputs) != expected_names:
        raise ValueError("generation must prepare exactly four output files")
    for name, content in outputs.items():
        if not isinstance(content, bytes) or not content.endswith(b"\n") or b"\r" in content:
            raise ValueError(f"prepared {name} must be UTF-8 with LF endings")
        try:
            text = content.decode("utf-8")
        except UnicodeError as error:
            raise ValueError(f"prepared {name} must be UTF-8") from error
        if name.endswith(".json"):
            try:
                value = json.loads(text)
            except json.JSONDecodeError as error:
                raise ValueError(f"prepared {name} must be valid JSON") from error
            if canonical_json(value) != content:
                raise ValueError(f"prepared {name} must be canonical JSON")


def _restore_outputs(
    output_paths: dict[str, Path], originals: dict[str, tuple[bytes, int] | None]
) -> None:
    first_error: BaseException | None = None
    for name, output in output_paths.items():
        original = originals[name]
        if original is None:
            try:
                output.unlink(missing_ok=True)
            except BaseException as error:
                if first_error is None:
                    first_error = error
            continue
        original_bytes, original_mode = original
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=output.parent,
                prefix=f".{output.name}.restore.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(original_bytes)
                temporary.flush()
                _set_staged_mode(temporary_path, original_mode)
                os.fsync(temporary.fileno())
            os.replace(temporary_path, output)
            temporary_path = None
        except BaseException as error:
            if first_error is None:
                first_error = error
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except BaseException as error:
                    if first_error is None:
                        first_error = error
    if first_error is not None:
        raise first_error


def _safe_failure_detail(error: BaseException) -> str:
    category = type(error).__name__
    if isinstance(error, OSError) and error.errno is not None:
        return f"{category} errno {error.errno}"
    return category


def _write_output_transaction(
    output_paths: dict[str, Path], outputs: dict[str, bytes]
) -> None:
    _validate_output_bytes(outputs)
    generated = next(iter(output_paths.values())).parent
    generated_existed = generated.exists()
    originals: dict[str, tuple[bytes, int] | None] = {}
    staged: dict[str, Path] = {}
    replace_started = False
    original_error: BaseException | None = None
    rollback_error: BaseException | None = None
    try:
        originals = {
            name: (
                path.read_bytes(),
                stat.S_IMODE(path.stat().st_mode),
            )
            if path.exists()
            else None
            for name, path in output_paths.items()
        }
        generated.mkdir(parents=True, exist_ok=True)
        for name, content in outputs.items():
            temporary = _open_staged_file(generated, name)
            temporary_path = Path(temporary.name)
            staged[name] = temporary_path
            try:
                _write_staged_file(temporary, content)
                _flush_staged_file(temporary)
                target_mode = originals[name][1] if originals[name] is not None else 0o644
                _set_staged_mode(temporary_path, target_mode)
                _fsync_staged_file(temporary)
            finally:
                temporary.close()
        replace_started = True
        for name in outputs:
            _replace_staged_file(staged[name], output_paths[name])
            staged.pop(name)
    except BaseException as error:
        original_error = error
        if replace_started:
            try:
                _restore_outputs(output_paths, originals)
            except BaseException as error:
                rollback_error = error
    finally:
        for temporary_path in staged.values():
            try:
                temporary_path.unlink(missing_ok=True)
            except BaseException as error:
                if rollback_error is None:
                    rollback_error = error
        if original_error is not None and not generated_existed:
            try:
                generated.rmdir()
            except FileNotFoundError:
                pass
            except BaseException as error:
                if rollback_error is None:
                    rollback_error = error
    if original_error is not None:
        message = "generation failed (" + _safe_failure_detail(original_error) + ")"
        if rollback_error is not None:
            message += "; rollback failed (" + _safe_failure_detail(rollback_error) + ")"
        raise RuntimeError(message) from original_error


def generate_all(root: Path, fixture_set: str = "pilot-01") -> None:
    """Validate all sources, then atomically write the four generated views."""
    manifest_path, pack_a_path, pack_b_path, output_paths = _generation_paths(
        Path(root), fixture_set
    )
    manifest = load_manifest(manifest_path)
    pack_a = _load_pack(pack_a_path, validate=False)
    pack_b = _load_pack(pack_b_path, validate=False)
    _validate_pack_bindings(pack_a, pack_b)
    _validated_pack(pack_a)
    _validated_pack(pack_b)
    _validate_pack_pair(pack_a, pack_b)

    outputs = {
        "flat-index.md": render_flat_index(manifest).encode("utf-8"),
        "state-projection.json": canonical_json(build_state_projection(manifest)),
        "state-table.json": canonical_json(build_state_table(pack_a)),
        "visual-map.json": canonical_json(build_visual_map(pack_b)),
    }
    _write_output_transaction(output_paths, outputs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--fixture-set", default="pilot-01")
    arguments = parser.parse_args()
    generate_all(arguments.root, arguments.fixture_set)


if __name__ == "__main__":
    main()
