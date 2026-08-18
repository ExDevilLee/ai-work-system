#!/usr/bin/env python3
"""Deterministically generate backup-inventory and recovery-gate views from manifests.

All output goes to ``fixtures/pilot-01/generated/``.  Re-running this script must
produce byte-identical files.
"""

from __future__ import annotations

from typing import Any

from fixture_model import (
    FIXTURE,
    file_sha256,
    json_canonical,
    load_backup_manifest,
    load_source_manifest,
    load_target_state,
    load_verification_receipts,
)

GENERATED = FIXTURE / "generated"


# --------------------------------------------------------------------------- #
#  backup-inventory views (no hash results)                                    #
# --------------------------------------------------------------------------- #

def build_file_listing(
    source: dict[str, Any], backup: dict[str, Any]
) -> dict[str, Any]:
    """File listing showing presence and version but NOT hash verification."""
    backup_files = {f["id"]: f for f in backup.get("files", [])}
    present: list[dict[str, Any]] = []
    for record in sorted(source["records"], key=lambda r: r["id"]):
        entry = backup_files.get(record["id"])
        if entry is not None:
            present.append(
                {
                    "id": record["id"],
                    "path": record["path"],
                    "logical_version": entry["logical_version"],
                }
            )
    return {
        "schema_version": 1,
        "backup_batch_id": backup["backup_batch_id"],
        "files_present": present,
    }


def build_version_summary(
    source: dict[str, Any], backup: dict[str, Any]
) -> dict[str, Any]:
    """Version summary comparing source versions to backup versions (no hashes)."""
    backup_files = {f["id"]: f for f in backup.get("files", [])}
    rows: list[dict[str, Any]] = []
    for record in sorted(source["records"], key=lambda r: r["id"]):
        entry = backup_files.get(record["id"])
        rows.append(
            {
                "id": record["id"],
                "source_version": record["logical_version"],
                "backup_version": entry["logical_version"] if entry else None,
                "status": record["status"],
            }
        )
    return {
        "schema_version": 1,
        "as_of": source["as_of"],
        "records": rows,
    }


# --------------------------------------------------------------------------- #
#  recovery-gated-bundle views (full integrity + gates)                        #
# --------------------------------------------------------------------------- #

def build_integrity_report(
    source: dict[str, Any],
    backup: dict[str, Any],
    target: dict[str, Any],
    receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Pre-computed integrity comparison: backup vs source vs target vs receipts."""
    backup_files = {f["id"]: f for f in backup.get("files", [])}
    target_items = {t["id"]: t for t in target.get("inventory", [])}
    receipt_by_id = {r["record_id"]: r for r in receipts}

    checks: list[dict[str, Any]] = []
    for record in sorted(source["records"], key=lambda r: r["id"]):
        rid = record["id"]
        entry = backup_files.get(rid)
        tgt = target_items.get(rid)
        rcp = receipt_by_id.get(rid)

        in_backup = entry is not None
        hash_match: bool | None = None
        if entry is not None:
            hash_match = entry["stored_sha256"] == record["content_sha256"]

        version_match: bool | None = None
        if entry is not None:
            version_match = entry["logical_version"] == record["logical_version"]

        target_divergence = False
        if tgt is not None:
            target_divergence = (
                tgt["current_version"] != record["logical_version"]
                or tgt["current_sha256"] != record["content_sha256"]
            )

        post_restore_status = rcp["verification_status"] if rcp else None

        if not in_backup:
            overall = "fail-missing"
        elif hash_match is False:
            overall = "fail-hash-mismatch"
        elif target_divergence:
            overall = "warn-target-divergence"
        elif post_restore_status == "FAILED":
            overall = "fail-post-restore"
        else:
            overall = "pass"

        checks.append(
            {
                "record_id": rid,
                "in_backup": in_backup,
                "hash_match": hash_match,
                "version_match": version_match,
                "target_divergence": target_divergence,
                "post_restore_status": post_restore_status,
                "overall": overall,
            }
        )

    derived: list[dict[str, Any]] = []
    for art in sorted(source.get("derived_artifacts", []), key=lambda a: a["id"]):
        derived.append(
            {
                "id": art["id"],
                "path": art["path"],
                "in_backup": any(
                    f["id"] == art["id"] for f in backup.get("files", [])
                ),
                "excluded_reason": art.get("exclusion_reason", ""),
            }
        )

    return {
        "schema_version": 1,
        "source_manifest_sha256": file_sha256(FIXTURE / "source-manifest.json"),
        "backup_batch_id": backup["backup_batch_id"],
        "checks": checks,
        "derived_artifacts": derived,
    }


RECOVERY_GATES_TEXT = """\
# Recovery Gate Rules

These gates must be checked before any file is considered eligible for restoration.

## Gate 1: Completeness
Every active source record listed in source-manifest.json must be present in the
backup batch. A missing active source record blocks restoration.

## Gate 2: Hash integrity
Every backed-up file must pass a content-hash check against its source-manifest
hash. A hash mismatch blocks the affected file from restoration.

## Gate 3: Target divergence
If the target device holds a different active version of a record, restoration
must stop and request a human decision. Automatic overwrite, version selection,
or merge is forbidden.

## Gate 4: Post-restore verification
After restoration, a post-restore checksum must match the backup checksum. If
verification fails, the restore must be rolled back and marked as failed.

## Gate 5: Derived artifacts
Derived indexes are not authoritative sources. They must be rebuilt from verified
source records after restore and must not be copied across devices.

## Human approval
Even when all gates pass, restoration requires explicit human approval. No
automatic restore, overwrite, merge, or delete is permitted.
"""


# --------------------------------------------------------------------------- #
#  Main                                                                        #
# --------------------------------------------------------------------------- #

def generate_all() -> dict[str, str]:
    """Return ``{relative_path: canonical_text}`` for every generated artifact."""
    source = load_source_manifest()
    backup = load_backup_manifest()
    target = load_target_state()
    receipts = load_verification_receipts()

    file_listing = build_file_listing(source, backup)
    version_summary = build_version_summary(source, backup)
    integrity_report = build_integrity_report(source, backup, target, receipts)

    return {
        "generated/file-listing.json": json_canonical(file_listing),
        "generated/version-summary.json": json_canonical(version_summary),
        "generated/integrity-report.json": json_canonical(integrity_report),
        "generated/recovery-gates.md": RECOVERY_GATES_TEXT,
    }


def main() -> int:
    GENERATED.mkdir(parents=True, exist_ok=True)
    artifacts = generate_all()
    for rel, text in artifacts.items():
        path = FIXTURE / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(f"generated: {', '.join(sorted(artifacts))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
