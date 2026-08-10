#!/usr/bin/env python3
"""Generate deterministic navigation and coverage-governance projections."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "pilot-01"


def load_manifest() -> dict[str, object]:
    return json.loads((FIXTURE / "manifest.json").read_text(encoding="utf-8"))


def review_due(record: dict[str, object], as_of: date) -> bool:
    if record["status"] != "active":
        return False
    reviewed = date.fromisoformat(str(record["last_review"]))
    interval = timedelta(days=int(record["review_interval_days"]))
    return reviewed + interval < as_of


def render_flat_index(manifest: dict[str, object]) -> str:
    rows = ["# Flat Record Index", "", "| ID | Domain | Source | Summary |", "| --- | --- | --- | --- |"]
    for record in sorted(manifest["records"], key=lambda item: item["id"]):
        rows.append(f"| {record['id']} | {record['domain']} | `{record['source']}` | {record['summary']} |")
    return "\n".join(rows) + "\n"


def build_state_projection(manifest: dict[str, object]) -> dict[str, object]:
    records = []
    for record in sorted(manifest["records"], key=lambda item: item["id"]):
        records.append({key: record.get(key) for key in ("id", "domain", "scope", "status", "owner", "last_review", "review_interval_days", "source", "superseded_by", "conflicts_with") if key in record})
    return {"schema_version": 1, "as_of": manifest["as_of"], "records": records}


def render_coverage_governance(manifest: dict[str, object]) -> str:
    as_of = date.fromisoformat(str(manifest["as_of"]))
    by_domain: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in manifest["records"]:
        by_domain[str(record["domain"])].append(record)
    rows = ["# Coverage Governance Projection", "", f"As of: {as_of.isoformat()}", "", "| Domain | Scope | Current coverage | Governance signal | Sources |", "| --- | --- | --- | --- | --- |"]
    for domain in sorted(manifest["domains"], key=lambda item: item["id"]):
        records = by_domain[str(domain["id"])]
        active = [record for record in records if record["status"] == "active"]
        signals: list[str] = []
        if not active:
            signals.append("coverage-gap")
        if any(review_due(record, as_of) for record in records):
            signals.append("review-due")
        if any(record["status"] == "conflict" for record in records):
            signals.append("unresolved-conflict")
        if any(record["status"] == "pending-validation" for record in records):
            signals.append("pending-validation")
        if any(record.get("owner") is None for record in records):
            signals.append("owner-missing")
        coverage = "active-record" if active else "no-active-record"
        sources = ", ".join(f"{record['id']} (`{record['source']}`)" for record in records) or "none"
        rows.append(f"| {domain['id']} | {domain['scope']} | {coverage} | {', '.join(signals) or 'none'} | {sources} |")
    return "\n".join(rows) + "\n"


def main() -> int:
    manifest = load_manifest()
    generated = FIXTURE / "generated"
    generated.mkdir(exist_ok=True)
    (generated / "flat-index.md").write_text(render_flat_index(manifest), encoding="utf-8")
    (generated / "state-projection.json").write_text(json.dumps(build_state_projection(manifest), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    (generated / "coverage-governance.md").write_text(render_coverage_governance(manifest), encoding="utf-8")
    print("generated: flat-index, state-projection, coverage-governance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
