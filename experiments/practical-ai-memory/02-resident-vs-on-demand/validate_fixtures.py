#!/usr/bin/env python3
"""Validate shared fixture facts and condition-specific residency boundaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
CONDITIONS = ("all-resident", "selective-resident", "index-only")


def load_facts(root: Path = ROOT) -> list[dict[str, object]]:
    payload = json.loads(
        (root / "expected" / "facts.json").read_text(encoding="utf-8")
    )
    facts = payload.get("facts")
    if not isinstance(facts, list):
        raise ValueError("expected/facts.json must contain a facts list")
    return facts


def text_files(root: Path) -> Iterable[Path]:
    return sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def validate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    fixture_root = root / "fixtures" / "pilot-01"
    common = fixture_root / "common"
    conditions = fixture_root / "conditions"
    prompts = root / "prompts"
    facts = load_facts(root)

    common_contents = {
        path.relative_to(common).as_posix(): path.read_text(encoding="utf-8")
        for path in text_files(common)
    }
    prompt_text = "\n".join(
        path.read_text(encoding="utf-8") for path in text_files(prompts)
    )

    ids = [fact.get("id") for fact in facts]
    if len(ids) != len(set(ids)):
        errors.append("fact ids must be unique")

    agent_text = {}
    for condition in CONDITIONS:
        path = conditions / condition / "AGENTS.md"
        if not path.is_file():
            errors.append(f"missing condition instructions: {condition}/AGENTS.md")
            continue
        agent_text[condition] = path.read_text(encoding="utf-8")

    for fact in facts:
        fact_id = fact.get("id")
        text = fact.get("text")
        source = fact.get("source")
        resident = fact.get("resident")
        if not isinstance(fact_id, str) or not isinstance(text, str):
            errors.append("every fact must have string id and text")
            continue
        if not isinstance(source, str) or source not in common_contents:
            errors.append(f"{fact_id}: missing common source {source!r}")
            continue
        if resident not in (True, False):
            errors.append(f"{fact_id}: resident must be boolean")

        total_occurrences = sum(content.count(text) for content in common_contents.values())
        if total_occurrences != 1:
            errors.append(
                f"{fact_id}: expected exactly one common occurrence, got {total_occurrences}"
            )
        if text not in common_contents[source]:
            errors.append(f"{fact_id}: fact is not present in declared source {source}")
        if text in prompt_text and fact.get("prompt_exposed") is not True:
            errors.append(f"{fact_id}: answer fact leaked into a prompt")

        expected_presence = {
            "all-resident": True,
            "selective-resident": resident is True,
            "index-only": False,
        }
        for condition, should_exist in expected_presence.items():
            if condition not in agent_text:
                continue
            exists = text in agent_text[condition]
            if exists != should_exist:
                errors.append(
                    f"{fact_id}: {condition} presence={exists}, expected={should_exist}"
                )

    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        return 1
    print(
        f"fixture validation passed: conditions={len(CONDITIONS)}, "
        f"facts={len(load_facts())}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
