#!/usr/bin/env python3
"""Validate the frozen POC 07 synthetic fixture and generated projections."""

from __future__ import annotations

import json
import re
from pathlib import Path

from generate_views import build_state_projection, load_manifest, render_coverage_governance, render_flat_index


ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "pilot-01"
TASKS = ("coverage-gap", "review-due", "governance-queue", "scope-slice", "source-trace")
CONDITIONS = ("source-only", "state-projection", "coverage-governance-projection")
PRIVATE = re.compile(r"(?:/Users/|[A-Za-z]:\\|api[_ -]?key|secret|password|provider|session[_ -]?id)", re.I)


def validate() -> list[str]:
    errors: list[str] = []
    manifest = load_manifest()
    records = manifest.get("records")
    domains = manifest.get("domains")
    if not isinstance(records, list) or not isinstance(domains, list):
        return ["manifest records and domains must be lists"]
    ids = [record.get("id") for record in records if isinstance(record, dict)]
    if len(ids) != len(set(ids)):
        errors.append("record IDs must be unique")
    source_paths = set()
    for record in records:
        if not isinstance(record, dict):
            errors.append("record must be an object")
            continue
        source = record.get("source")
        if not isinstance(source, str) or not source.startswith("records/") or ".." in source:
            errors.append("record source must be a safe records-relative path")
            continue
        source_paths.add(source)
        if not (FIXTURE / source).is_file():
            errors.append(f"missing record source: {source}")
        if record.get("status") not in {"active", "superseded", "conflict", "pending-validation"}:
            errors.append("record has invalid status")
    domain_ids = {domain.get("id") for domain in domains if isinstance(domain, dict)}
    if "incident-handling" not in domain_ids:
        errors.append("fixture must include incident-handling coverage gap")
    if any(record.get("domain") == "incident-handling" for record in records if isinstance(record, dict)):
        errors.append("incident-handling must have no record")
    for task in TASKS:
        if not (ROOT / "prompts" / f"{task}.md").is_file():
            errors.append(f"missing prompt: {task}")
    flat = render_flat_index(manifest)
    projection = json.dumps(build_state_projection(manifest), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    coverage = render_coverage_governance(manifest)
    generated = FIXTURE / "generated"
    expected = {"flat-index.md": flat, "state-projection.json": projection, "coverage-governance.md": coverage}
    for name, text in expected.items():
        path = generated / name
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            errors.append(f"generated artifact drift: {name}")
    for path in list(FIXTURE.rglob("*")) + list((ROOT / "prompts").glob("*.md")):
        if path.is_file() and PRIVATE.search(path.read_text(encoding="utf-8")):
            errors.append(f"private marker in {path.relative_to(ROOT)}")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        raise SystemExit("fixture validation failed:\n" + "\n".join(f"- {error}" for error in errors))
    print(f"fixture validation passed: conditions={len(CONDITIONS)}, tasks={len(TASKS)}, records=6")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
