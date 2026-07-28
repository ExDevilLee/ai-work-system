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
