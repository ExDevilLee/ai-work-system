#!/usr/bin/env python3
"""Tests for fixture model, manifest consistency and generated artifacts."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fixture_model import (
    CONDITIONS,
    FIXTURE,
    TASKS,
    ensure_contained_path,
    file_sha256,
    json_canonical,
    load_backup_manifest,
    load_source_manifest,
    load_target_state,
    load_verification_receipts,
)
from generate_backup_bundle import (
    build_file_listing,
    build_integrity_report,
    build_version_summary,
    generate_all,
)


class TestSourceManifest(unittest.TestCase):
    def test_records_exist_and_hashes_match(self) -> None:
        manifest = load_source_manifest()
        for record in manifest["records"]:
            path = FIXTURE / record["path"]
            self.assertTrue(path.is_file(), f"missing record file: {record['path']}")
            self.assertEqual(
                file_sha256(path),
                record["content_sha256"],
                f"hash mismatch for {record['id']}",
            )

    def test_record_ids_unique(self) -> None:
        manifest = load_source_manifest()
        ids = [r["id"] for r in manifest["records"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_records_are_source_not_derived(self) -> None:
        manifest = load_source_manifest()
        for record in manifest["records"]:
            self.assertFalse(record["is_derived"], f"{record['id']} must be source")

    def test_six_records_cover_all_tasks(self) -> None:
        manifest = load_source_manifest()
        self.assertEqual(len(manifest["records"]), 6)

    def test_derived_artifact_has_valid_parent(self) -> None:
        manifest = load_source_manifest()
        source_ids = {r["id"] for r in manifest["records"]}
        for art in manifest.get("derived_artifacts", []):
            self.assertTrue(art["is_derived"])
            self.assertIn(art["derived_from"], source_ids)

    def test_derived_artifact_file_exists_and_hash_matches(self) -> None:
        manifest = load_source_manifest()
        for art in manifest.get("derived_artifacts", []):
            path = FIXTURE / art["path"]
            self.assertTrue(path.is_file(), f"missing derived file: {art['path']}")
            self.assertEqual(file_sha256(path), art["content_sha256"])


class TestBackupManifest(unittest.TestCase):
    def test_source_manifest_hash_reference(self) -> None:
        backup = load_backup_manifest()
        actual = file_sha256(FIXTURE / "source-manifest.json")
        self.assertEqual(backup["source_manifest_sha256"], actual)

    def test_bk_802_is_missing(self) -> None:
        """partial-backup scenario: BK-802 must NOT be in backup files."""
        backup = load_backup_manifest()
        file_ids = {f["id"] for f in backup["files"]}
        self.assertNotIn("BK-802", file_ids)

    def test_ig_803_has_mismatched_hash(self) -> None:
        """integrity-mismatch scenario: IG-803 stored hash differs from source."""
        source = load_source_manifest()
        backup = load_backup_manifest()
        source_ig803 = {r["id"]: r for r in source["records"]}["IG-803"]
        backup_ig803 = {f["id"]: f for f in backup["files"]}["IG-803"]
        self.assertNotEqual(
            backup_ig803["stored_sha256"],
            source_ig803["content_sha256"],
        )

    def test_derived_artifact_excluded(self) -> None:
        backup = load_backup_manifest()
        excluded_paths = {e["path"] for e in backup["excluded"]}
        self.assertIn("derived/retention-index.md", excluded_paths)

    def test_rr_801_is_clean(self) -> None:
        """clean-restore scenario: RR-801 hash matches."""
        source = load_source_manifest()
        backup = load_backup_manifest()
        source_rr = {r["id"]: r for r in source["records"]}["RR-801"]
        backup_rr = {f["id"]: f for f in backup["files"]}["RR-801"]
        self.assertEqual(backup_rr["stored_sha256"], source_rr["content_sha256"])


class TestTargetState(unittest.TestCase):
    def test_td_804_has_diverged(self) -> None:
        """target-divergence scenario: target has version 3."""
        source = load_source_manifest()
        target = load_target_state()
        td_target = {t["id"]: t for t in target["inventory"]}["TD-804"]
        td_source = {r["id"]: r for r in source["records"]}["TD-804"]
        self.assertGreater(td_target["current_version"], td_source["logical_version"])

    def test_rr_801_matches_target(self) -> None:
        target = load_target_state()
        rr_target = {t["id"]: t for t in target["inventory"]}["RR-801"]
        self.assertEqual(rr_target["current_version"], 2)


class TestVerificationReceipts(unittest.TestCase):
    def test_rb_806_receipt_failed(self) -> None:
        """rollback-receipt scenario: RB-806 post-restore verification FAILED."""
        receipts = load_verification_receipts()
        rb_receipt = [r for r in receipts if r["record_id"] == "RB-806"][0]
        self.assertEqual(rb_receipt["verification_status"], "FAILED")
        self.assertNotEqual(
            rb_receipt["post_restore_sha256"],
            rb_receipt["backup_stored_sha256"],
        )


class TestGeneratedArtifacts(unittest.TestCase):
    def test_generation_is_deterministic(self) -> None:
        """Re-generating must produce byte-identical output."""
        first = generate_all()
        second = generate_all()
        self.assertEqual(first, second)

    def test_generated_files_match_output(self) -> None:
        artifacts = generate_all()
        for rel, text in artifacts.items():
            path = FIXTURE / rel
            self.assertTrue(path.is_file(), f"missing generated file: {rel}")
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                text,
                f"generated file drift: {rel}",
            )

    def test_integrity_report_covers_all_failures(self) -> None:
        source = load_source_manifest()
        backup = load_backup_manifest()
        target = load_target_state()
        receipts = load_verification_receipts()
        report = build_integrity_report(source, backup, target, receipts)
        overalls = {c["record_id"]: c["overall"] for c in report["checks"]}
        self.assertEqual(overalls["RR-801"], "pass")
        self.assertEqual(overalls["BK-802"], "fail-missing")
        self.assertEqual(overalls["IG-803"], "fail-hash-mismatch")
        self.assertEqual(overalls["TD-804"], "warn-target-divergence")
        self.assertEqual(overalls["DI-805"], "pass")
        self.assertEqual(overalls["RB-806"], "fail-post-restore")

    def test_integrity_report_references_source_manifest_file_hash(self) -> None:
        source = load_source_manifest()
        backup = load_backup_manifest()
        target = load_target_state()
        receipts = load_verification_receipts()
        report = build_integrity_report(source, backup, target, receipts)
        from fixture_model import FIXTURE, file_sha256
        self.assertEqual(
            report["source_manifest_sha256"],
            file_sha256(FIXTURE / "source-manifest.json"),
        )

    def test_file_listing_excludes_hashes(self) -> None:
        """backup-inventory condition: file listing must NOT contain hash fields."""
        source = load_source_manifest()
        backup = load_backup_manifest()
        listing = build_file_listing(source, backup)
        listing_text = json_canonical(listing)
        self.assertNotIn("sha256", listing_text)
        self.assertNotIn("hash", listing_text.lower())

    def test_version_summary_shows_bk_802_null(self) -> None:
        source = load_source_manifest()
        backup = load_backup_manifest()
        summary = build_version_summary(source, backup)
        bk = {r["id"]: r for r in summary["records"]}["BK-802"]
        self.assertIsNone(bk["backup_version"])


class TestPathSafety(unittest.TestCase):
    def test_contained_path_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            inner = base / "sub" / "file.txt"
            inner.parent.mkdir(parents=True)
            inner.touch()
            result = ensure_contained_path(inner, base)
            # ensure_contained_path returns abspath; compare via resolved paths.
            self.assertTrue(
                Path(str(result)).resolve().__str__().startswith(str(base.resolve())),
                f"result {result} not within base {base}",
            )

    def test_escaping_path_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "boundary"
            base.mkdir()
            outside = Path(tmp) / "outside.txt"
            outside.touch()
            with self.assertRaises(ValueError):
                ensure_contained_path(outside, base)


class TestTaskConditionCoverage(unittest.TestCase):
    def test_six_tasks_defined(self) -> None:
        expected = {
            "clean-restore", "partial-backup", "integrity-mismatch",
            "target-divergence", "derived-index", "rollback-receipt",
        }
        self.assertEqual(set(TASKS), expected)

    def test_three_conditions_defined(self) -> None:
        expected = {"source-only", "backup-inventory", "recovery-gated-bundle"}
        self.assertEqual(set(CONDITIONS), expected)

    def test_prompts_exist(self) -> None:
        from fixture_model import ROOT
        for task in TASKS:
            self.assertTrue(
                (ROOT / "prompts" / f"{task}.md").is_file(),
                f"missing prompt for {task}",
            )


if __name__ == "__main__":
    unittest.main()
