#!/usr/bin/env python3
"""Validate the frozen POC 08 synthetic fixtures and generated artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from fixture_model import (
    CONDITIONS,
    FIXTURE,
    PRIVATE_PATTERN,
    ROOT,
    TASKS,
    VALID_SCOPES,
    VALID_STATUSES,
    file_sha256,
    load_backup_manifest,
    load_source_manifest,
)
from generate_backup_bundle import generate_all

PRIVATE_RE = re.compile(PRIVATE_PATTERN, re.I)
ABSOLUTE_PATH_RE = re.compile(r"(?:^|[\"'\s,])(?:/[A-Za-z0-9]|[A-Za-z]:[\\/])")


def _check_no_private(errors: list[str], path: Path) -> None:
    if path.is_file() and PRIVATE_RE.search(path.read_text(encoding="utf-8")):
        errors.append(f"private marker in {path.relative_to(ROOT)}")


def _check_no_absolute_path(errors: list[str], path: Path) -> None:
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        match = ABSOLUTE_PATH_RE.search(text)
        if match:
            context = text[max(0, match.start() - 5):match.end() + 15]
            errors.append(
                f"possible absolute path in {path.relative_to(ROOT)}: …{context}…"
            )


def validate_source_manifest(errors: list[str]) -> dict[str, Any]:
    source = load_source_manifest()
    records = source.get("records")
    if not isinstance(records, list) or not records:
        errors.append("source-manifest records must be a non-empty list")
        return source

    ids = [r.get("id") for r in records if isinstance(r, dict)]
    if len(ids) != len(set(ids)):
        errors.append("source-manifest record IDs must be unique")

    id_set = set(ids)
    for record in records:
        if not isinstance(record, dict):
            errors.append("source-manifest record must be an object")
            continue
        rid = record.get("id", "?")
        path_str = record.get("path", "")
        if not isinstance(path_str, str) or ".." in path_str or path_str.startswith("/"):
            errors.append(f"record {rid}: path must be safe and relative")
        record_file = FIXTURE / path_str
        if not record_file.is_file():
            errors.append(f"record {rid}: missing source file {path_str}")
        elif file_sha256(record_file) != record.get("content_sha256"):
            errors.append(f"record {rid}: content_sha256 does not match file content")
        if record.get("status") not in VALID_STATUSES:
            errors.append(f"record {rid}: invalid status '{record.get('status')}'")
        if record.get("scope") not in VALID_SCOPES:
            errors.append(f"record {rid}: invalid scope '{record.get('scope')}'")
        if not isinstance(record.get("logical_version"), int) or record["logical_version"] < 1:
            errors.append(f"record {rid}: logical_version must be a positive integer")
        if not isinstance(record.get("is_derived"), bool):
            errors.append(f"record {rid}: is_derived must be boolean")

    derived = source.get("derived_artifacts", [])
    if not isinstance(derived, list):
        errors.append("derived_artifacts must be a list")
    else:
        for art in derived:
            if not isinstance(art, dict):
                errors.append("derived artifact must be an object")
                continue
            if not art.get("is_derived"):
                errors.append(f"derived artifact {art.get('id')}: is_derived must be true")
            parent = art.get("derived_from")
            if parent not in id_set:
                errors.append(f"derived artifact {art.get('id')}: derived_from '{parent}' not found")
            art_file = FIXTURE / art.get("path", "")
            if not art_file.is_file():
                errors.append(f"derived artifact {art.get('id')}: missing file")
            elif file_sha256(art_file) != art.get("content_sha256"):
                errors.append(f"derived artifact {art.get('id')}: hash mismatch")

    return source


def validate_backup_manifest(errors: list[str], source: dict[str, Any]) -> dict[str, Any]:
    backup = load_backup_manifest()
    source_ids = {r["id"] for r in source["records"]}

    files = backup.get("files", [])
    if not isinstance(files, list):
        errors.append("backup-manifest files must be a list")
        return backup

    file_ids = [f.get("id") for f in files if isinstance(f, dict)]
    if len(file_ids) != len(set(file_ids)):
        errors.append("backup-manifest file IDs must be unique")

    for entry in files:
        if not isinstance(entry, dict):
            errors.append("backup file entry must be an object")
            continue
        fid = entry.get("id", "?")
        if fid not in source_ids:
            errors.append(f"backup file {fid}: not a known source record")
        if not isinstance(entry.get("stored_sha256"), str) or len(entry["stored_sha256"]) != 64:
            errors.append(f"backup file {fid}: stored_sha256 must be a 64-char hex string")

    # Derived artifacts must NOT appear in backup files.
    derived_ids = {a["id"] for a in source.get("derived_artifacts", [])}
    for fid in file_ids:
        if fid in derived_ids:
            errors.append(f"derived artifact {fid} must not appear in backup files")

    # Derived artifacts must appear in excluded with a reason.
    excluded = backup.get("excluded", [])
    excluded_paths = {e.get("path") for e in excluded if isinstance(e, dict)}
    for art in source.get("derived_artifacts", []):
        if art["path"] not in excluded_paths:
            errors.append(f"derived artifact {art['id']} must be in backup excluded list")

    # Verify source_manifest_sha256 reference (hash of the actual file on disk).
    expected_hash = file_sha256(FIXTURE / "source-manifest.json")
    if backup.get("source_manifest_sha256") != expected_hash:
        errors.append("backup-manifest source_manifest_sha256 does not match source-manifest")

    return backup


def validate_generated_artifacts(errors: list[str]) -> None:
    """Check that generated files exist and match deterministic output."""
    expected = generate_all()
    for rel, text in expected.items():
        path = FIXTURE / rel
        if not path.is_file():
            errors.append(f"missing generated artifact: {rel}")
        elif path.read_text(encoding="utf-8") != text:
            errors.append(f"generated artifact drift: {rel}")


def validate_prompts_and_rubrics(errors: list[str]) -> None:
    for task in TASKS:
        prompt_path = ROOT / "prompts" / f"{task}.md"
        if not prompt_path.is_file():
            errors.append(f"missing prompt: {task}.md")
    rubric_path = ROOT / "rubrics" / "pilot-01.json"
    if not rubric_path.is_file():
        errors.append("missing rubric: rubrics/pilot-01.json")
        return
    rubric = json.loads(rubric_path.read_text(encoding="utf-8"))
    if set(rubric) != set(TASKS):
        errors.append("rubric must define exactly one entry per task")

    answers_path = ROOT / "expected" / "answers.json"
    if not answers_path.is_file():
        errors.append("missing expected/answers.json")
        return
    answers = json.loads(answers_path.read_text(encoding="utf-8"))
    if set(answers) != set(TASKS):
        errors.append("answers must define exactly one entry per task")


def validate_conditions(errors: list[str]) -> None:
    for condition in CONDITIONS:
        agents_path = FIXTURE / "conditions" / condition / "AGENTS.md"
        if not agents_path.is_file():
            errors.append(f"missing condition AGENTS.md: {condition}")


def validate_no_leakage(errors: list[str]) -> None:
    """Ensure prompts and conditions do not leak expected answers or rubric criteria."""
    answer_text = ""
    answers_path = ROOT / "expected" / "answers.json"
    if answers_path.is_file():
        answer_text = answers_path.read_text(encoding="utf-8")
    # Extract distinctive answer phrases that must not appear in prompts/conditions.
    if answer_text:
        answers = json.loads(answer_text)
        for task, ans in answers.items():
            for key in ("expected_overall", "forbidden_actions"):
                phrases = ans.get(key, []) if isinstance(ans, dict) else []
                if isinstance(phrases, str):
                    phrases = [phrases]
                for phrase in phrases:
                    if not isinstance(phrase, str) or len(phrase) < 8:
                        continue
                    for search_root in (ROOT / "prompts", FIXTURE / "conditions"):
                        for path in search_root.rglob("*.md"):
                            if phrase.lower() in path.read_text(encoding="utf-8").lower():
                                errors.append(
                                    f"answer phrase leakage in {path.relative_to(ROOT)}: '{phrase[:40]}'"
                                )


def validate_privacy(errors: list[str]) -> None:
    """Scan every fixture, prompt, condition and generated file for private markers."""
    scan_paths: list[Path] = []
    for pattern in ("fixtures/**/*.json", "fixtures/**/*.md", "prompts/*.md", "rubrics/*.json"):
        scan_paths.extend(ROOT.glob(pattern))
    for path in scan_paths:
        _check_no_private(errors, path)
        _check_no_absolute_path(errors, path)


def validate() -> list[str]:
    errors: list[str] = []
    source = validate_source_manifest(errors)
    validate_backup_manifest(errors, source)
    validate_generated_artifacts(errors)
    validate_prompts_and_rubrics(errors)
    validate_conditions(errors)
    validate_no_leakage(errors)
    validate_privacy(errors)
    return errors


def main() -> int:
    errors = validate()
    if errors:
        raise SystemExit("fixture validation failed:\n" + "\n".join(f"- {e}" for e in errors))
    print(
        f"fixture validation passed: conditions={len(CONDITIONS)}, "
        f"tasks={len(TASKS)}, records=6, derived=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
