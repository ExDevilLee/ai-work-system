#!/usr/bin/env python3
import hashlib
import json
import re
from pathlib import Path


TASKS = (
    "static-reference",
    "approved-decision",
    "unresolved-conflict",
    "scope-bound-rule",
    "historical-trace",
)
CONDITIONS = ("rag-only", "rag-with-recency", "memory-governed")
PACKET_SEPARATOR = b"\n---\n\n"
PRIVATE_PATTERNS = (
    re.compile(r"(?i)provider\s*[=:]"),
    re.compile(r"(?i)(api[_ -]?key|access[_ -]?token|secret)\s*[=:]"),
    re.compile(r"(?i)thread[_ -]?id\s*[=:]"),
    re.compile(r"/Users/[^/\s]+/"),
    re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+\\"),
)
PROMPT_LEAK_MARKERS = (
    "rag-only",
    "rag-with-recency",
    "memory-governed",
    "仅检索结果机制",
    "检索加时间优先机制",
    "检索加当前记忆治理机制",
    "mark the record active",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def assemble_packet(sources: list[bytes]) -> bytes:
    normalized = []
    for index, source in enumerate(sources):
        if index and source.startswith(b"# "):
            source = b"## " + source[2:]
        normalized.append(source)
    return PACKET_SEPARATOR.join(normalized)


def load_json(path: Path, errors: list[str]) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read JSON {path.name}: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"JSON root must be an object: {path.name}")
        return {}
    return value


def validate(root: Path, fixture_set: str = "pilot-01") -> list[str]:
    root = Path(root)
    errors: list[str] = []
    fixture = root / "fixtures" / fixture_set
    corpus = fixture / "corpus"
    packets = fixture / "retrieval-packets"
    conditions = fixture / "conditions"
    manifest = load_json(packets / "manifest.json", errors)
    answers = load_json(root / "expected" / "answers.json", errors)
    rubric = load_json(root / "expected" / "rubric.json", errors)
    manifest_tasks = manifest.get("tasks", {})

    if set(manifest_tasks) != set(TASKS):
        errors.append("manifest tasks must match the five frozen tasks")
    if set(answers) != set(TASKS):
        errors.append("expected answers must match the five frozen tasks")
    if set(rubric) != set(TASKS):
        errors.append("rubric tasks must match the five frozen tasks")

    for task in TASKS:
        entry = manifest_tasks.get(task)
        if not isinstance(entry, dict):
            continue
        source_entries = entry.get("sources", [])
        source_bytes: list[bytes] = []
        source_paths: list[str] = []
        for source_entry in source_entries:
            if not isinstance(source_entry, dict) or not source_entry.get("path"):
                errors.append(f"{task}: malformed source entry")
                continue
            relative_path = source_entry["path"]
            source_paths.append(relative_path)
            source_path = corpus / relative_path
            try:
                data = source_path.read_bytes()
            except OSError as exc:
                errors.append(f"{task}: missing corpus source {relative_path}: {exc}")
                continue
            source_bytes.append(data)
            if source_entry.get("bytes") != len(data):
                errors.append(f"{task}: source byte count mismatch for {relative_path}")
            if source_entry.get("sha256") != sha256(data):
                errors.append(f"{task}: source SHA256 mismatch for {relative_path}")

        required = entry.get("required_sources", [])
        if not set(required).issubset(source_paths):
            errors.append(f"{task}: required sources are absent from packet sources")
        packet_name = entry.get("packet")
        if not packet_name:
            errors.append(f"{task}: packet path is missing")
            continue
        packet_path = packets / packet_name
        try:
            packet_data = packet_path.read_bytes()
        except OSError as exc:
            errors.append(f"{task}: missing packet: {exc}")
            continue
        if entry.get("packet_bytes") != len(packet_data):
            errors.append(f"{task}: packet byte count mismatch")
        if entry.get("packet_sha256") != sha256(packet_data):
            errors.append(f"{task}: packet SHA256 mismatch")
        if len(source_bytes) == len(source_entries):
            expected_packet = assemble_packet(source_bytes)
            if packet_data != expected_packet:
                errors.append(f"{task}: packet is not assembled from declared corpus sources")

        prompt_path = root / "prompts" / f"{task}.md"
        try:
            prompt = prompt_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"{task}: cannot read prompt: {exc}")
        else:
            lowered = prompt.casefold()
            if any(marker.casefold() in lowered for marker in PROMPT_LEAK_MARKERS):
                errors.append(f"{task}: prompt leaks condition or expected answer")

    expected_condition_files = {
        "rag-only": {"AGENTS.md"},
        "rag-with-recency": {"AGENTS.md"},
        "memory-governed": {"AGENTS.md", "memory/CURRENT.md"},
    }
    for condition in CONDITIONS:
        condition_root = conditions / condition
        actual_files = {
            path.relative_to(condition_root).as_posix()
            for path in condition_root.rglob("*")
            if path.is_file()
        } if condition_root.exists() else set()
        if actual_files != expected_condition_files[condition]:
            errors.append(f"{condition}: unexpected condition file set")

    current_path = conditions / "memory-governed" / "memory" / "CURRENT.md"
    try:
        current = current_path.read_bytes().strip()
    except OSError:
        current = b""
    for source_path in corpus.rglob("*.md") if corpus.exists() else ():
        body = source_path.read_bytes().strip()
        if body and body == current:
            errors.append("CURRENT.md copies corpus body instead of projecting state")
            break

    markdown_and_json = [
        *root.glob("expected/*.json"),
        *root.glob("prompts/*.md"),
        *fixture.rglob("*.md"),
        *fixture.rglob("*.json"),
    ]
    for path in markdown_and_json:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if any(pattern.search(text) for pattern in PRIVATE_PATTERNS):
            errors.append(f"private-data marker found in {path.relative_to(root).as_posix()}")

    total = sum(
        entry.get("max_score", 0)
        for entry in rubric.values()
        if isinstance(entry, dict)
    )
    if total != 28:
        errors.append(f"rubric total must equal 28, got {total}")
    for task, entry in rubric.items():
        if isinstance(entry, dict) and len(entry.get("items", [])) != entry.get("max_score"):
            errors.append(f"{task}: rubric item count must equal max score")

    return errors


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-set", default="pilot-01")
    args = parser.parse_args()
    errors = validate(Path(__file__).resolve().parent, args.fixture_set)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("fixture validation passed: conditions=3, tasks=5, packets=5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
