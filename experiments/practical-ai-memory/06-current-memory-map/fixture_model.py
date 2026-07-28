import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


VALID_STATUSES = frozenset(
    {"active", "superseded", "conflict", "pending-validation"}
)
SUPPORTED_SCHEMA_VERSION = 1

_VALID_SCOPES = frozenset({"global", "project", "macos", "win11"})
_VALID_RELATIONS = frozenset({"supersedes", "conflicts-with"})


def is_canonical_source(source: str) -> bool:
    if not isinstance(source, str) or any(
        ord(character) < 32 or ord(character) == 127 for character in source
    ):
        return False
    windows_path = PureWindowsPath(source)
    components = source.split("/")
    return (
        "\\" not in source
        and not PurePosixPath(source).is_absolute()
        and not windows_path.drive
        and not windows_path.anchor
        and len(components) > 1
        and components[0] == "records"
        and PurePosixPath(source).suffix == ".md"
        and all(component not in {"", ".", ".."} for component in components)
    )


def validate_manifest(manifest: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest must be an object"]

    schema_version = manifest.get("schema_version")
    if (
        type(schema_version) is not int
        or schema_version != SUPPORTED_SCHEMA_VERSION
    ):
        errors.append(
            f"schema_version must be integer {SUPPORTED_SCHEMA_VERSION}"
        )

    records = manifest.get("records")
    if not isinstance(records, list):
        errors.append("manifest records must be a list")
        return errors

    seen_ids: set[str] = set()
    known_ids: set[str] = set()
    relation_pairs: set[tuple[str, str, str]] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"record[{index}] must be an object")
            continue

        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id.strip():
            errors.append(f"record[{index}] must have a non-empty id")
        elif record_id in seen_ids:
            errors.append(f"record[{index}] has duplicate id '{record_id}'")
        else:
            seen_ids.add(record_id)
            known_ids.add(record_id)

        status = record.get("status")
        if not isinstance(status, str) or status not in VALID_STATUSES:
            errors.append(f"record[{index}] has unsupported status '{status}'")

        scope = record.get("scope")
        if not isinstance(scope, str) or scope not in _VALID_SCOPES:
            errors.append(f"record[{index}] has invalid scope '{scope}'")

        source = record.get("source")
        if not isinstance(source, str) or not source.strip():
            errors.append(f"record[{index}] must have a non-empty source")
        elif not is_canonical_source(source):
            errors.append(
                f"record[{index}] must use a canonical POSIX-relative source "
                "under records/"
            )

    for index, record in enumerate(records):
        if not isinstance(record, dict) or "relations" not in record:
            continue

        relations = record["relations"]
        if not isinstance(relations, list):
            errors.append(f"record[{index}] has malformed relations; expected a list")
            continue

        for relation_index, relation in enumerate(relations):
            prefix = f"record[{index}] relation[{relation_index}]"
            if not isinstance(relation, dict):
                errors.append(f"{prefix} is a malformed relation")
                continue

            relation_type = relation.get("type")
            target = relation.get("target")
            if (
                not isinstance(relation_type, str)
                or relation_type not in _VALID_RELATIONS
            ):
                errors.append(f"{prefix} is a malformed relation: unsupported type")
            if not isinstance(target, str) or not target.strip():
                errors.append(f"{prefix} is a malformed relation: missing target")
            elif target not in known_ids:
                errors.append(f"{prefix} has unknown relation target '{target}'")
            if (
                isinstance(record.get("id"), str)
                and isinstance(relation_type, str)
                and relation_type in _VALID_RELATIONS
                and isinstance(target, str)
                and target in known_ids
            ):
                relation_pairs.add((record["id"], relation_type, target))

    records_by_id = {
        record["id"]: record
        for record in records
        if isinstance(record, dict) and isinstance(record.get("id"), str)
    }
    relation_types_by_pair: dict[tuple[str, str], set[str]] = {}
    for source_id, relation_type, target_id in relation_pairs:
        relation_types_by_pair.setdefault((source_id, target_id), set()).add(
            relation_type
        )
        source = records_by_id[source_id]
        target = records_by_id[target_id]
        if source_id == target_id:
            errors.append(f"relation from '{source_id}' cannot target itself")
        if relation_type == "conflicts-with":
            if source.get("status") != "conflict" or target.get("status") != "conflict":
                errors.append("conflicts-with endpoints must have conflict status")
            if (target_id, "conflicts-with", source_id) not in relation_pairs:
                errors.append("conflicts-with must be symmetric")
        elif relation_type == "supersedes":
            if source.get("status") != "active" or target.get("status") != "superseded":
                errors.append("supersedes must point from active to superseded")
            if source.get("scope") != target.get("scope"):
                errors.append("supersedes records must have the same scope")
            source_task = source.get("task_id")
            target_task = target.get("task_id")
            if (
                isinstance(source_task, str)
                and isinstance(target_task, str)
                and source_task != target_task
            ):
                errors.append("supersedes records must have the same task")
            if (target_id, "supersedes", source_id) in relation_pairs:
                errors.append("supersedes target must not supersede its source")

    if any(len(types) > 1 for types in relation_types_by_pair.values()):
        errors.append("relation pair has contradictory relation types")

    return errors


def load_manifest(path: Path) -> dict:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot load manifest: {error}") from error

    errors = validate_manifest(manifest)
    if errors:
        raise ValueError("invalid manifest:\n" + "\n".join(f"- {error}" for error in errors))
    return manifest


def fact_set(manifest: dict) -> set[tuple[str, str, str, str]]:
    errors = validate_manifest(manifest)
    if errors:
        raise ValueError("invalid manifest:\n" + "\n".join(f"- {error}" for error in errors))

    return {
        (record["id"], record["status"], record["scope"], record["source"])
        for record in manifest["records"]
    }


def canonical_json(value: Any) -> bytes:
    text = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return (text + "\n").encode("utf-8")
