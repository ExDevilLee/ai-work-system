from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from validate_fixtures import ROOT, contains_lifecycle_vocabulary, validate


CONDITIONS = ("source-only", "flat-index", "state-projection")
TASKS = (
    "active-decision",
    "superseded-rule",
    "unresolved-conflict",
    "scope-boundary",
    "pending-observation",
)
FLAT_INDEX_HEADING = "# Flat Record Index"
FLAT_INDEX_HEADER = "| Title | Source | Summary | Updated At |"
FLAT_INDEX_SEPARATOR = "| --- | --- | --- | --- |"
PROTOCOL_PATHS = (
    "prompts/active-decision.md",
    "prompts/superseded-rule.md",
    "prompts/unresolved-conflict.md",
    "prompts/scope-boundary.md",
    "prompts/pending-observation.md",
    "fixtures/pilot-01/conditions/source-only/AGENTS.md",
    "fixtures/pilot-01/conditions/flat-index/AGENTS.md",
    "fixtures/pilot-01/conditions/state-projection/AGENTS.md",
)


class FixtureValidationTest(unittest.TestCase):
    def write_json(self, path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def load_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def copy_committed_fixture(self, destination: Path) -> None:
        for name in ("expected", "fixtures", "prompts"):
            shutil.copytree(ROOT / name, destination / name)

    def load_manifest(self, root: Path) -> dict:
        return self.load_json(root / "fixtures" / "pilot-01" / "manifest.json")

    def write_valid_generated(self, root: Path) -> None:
        fixture_root = root / "fixtures" / "pilot-01"
        generated = fixture_root / "generated"
        generated.mkdir(parents=True, exist_ok=True)
        manifest = self.load_manifest(root)

        rows = [FLAT_INDEX_HEADING, "", FLAT_INDEX_HEADER, FLAT_INDEX_SEPARATOR]
        for record in sorted(manifest["records"], key=lambda item: item["id"]):
            rows.append(
                f"| {record['title']} | `{record['source']}` | "
                f"{record['summary']} | {record['updated_at']} |"
            )
        (generated / "flat-index.md").write_text(
            "\n".join(rows) + "\n", encoding="utf-8"
        )

        projection_records = []
        for record in manifest["records"]:
            projection_records.append(
                {
                    "id": record["id"],
                    "status": record["status"],
                    "scope": record["scope"],
                    "source": record["source"],
                    "relations": record.get("relations", []),
                    "action_boundary": "Verify the referenced evidence before acting.",
                }
            )
        self.write_json(
            generated / "state-projection.json",
            {"schema_version": 1, "records": projection_records},
        )

    def write_valid_protocol_lock(self, root: Path) -> None:
        hashes = {
            path: hashlib.sha256((root / path).read_bytes()).hexdigest()
            for path in PROTOCOL_PATHS
        }
        self.write_json(
            root / "fixtures" / "pilot-01" / "protocol-lock.json", hashes
        )

    def validate_copy(
        self,
        mutation=None,
        *,
        require_generated: bool = False,
        with_generated: bool = False,
        with_protocol_lock: bool = False,
    ) -> list[str]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "fixture-copy"
            root.mkdir()
            self.copy_committed_fixture(root)
            if with_generated:
                self.write_valid_generated(root)
            if with_protocol_lock:
                self.write_valid_protocol_lock(root)
            if mutation is not None:
                mutation(root)
            return validate(root, require_generated=require_generated)

    def test_real_committed_fixture_validates(self) -> None:
        self.assertEqual(validate(ROOT), [])

    def test_copied_committed_fixture_validates(self) -> None:
        self.assertEqual(self.validate_copy(), [])

    def test_committed_filenames_titles_and_summaries_are_neutral(self) -> None:
        manifest = self.load_manifest(ROOT)
        for record in manifest["records"]:
            values = (
                Path(record["source"]).stem,
                record.get("title", ""),
                record.get("summary", ""),
            )
            for value in values:
                self.assertFalse(
                    contains_lifecycle_vocabulary(value),
                    f"answer-bearing lifecycle word in {value!r}",
                )

    def test_lifecycle_neutrality_uses_token_boundaries(self) -> None:
        self.assertTrue(contains_lifecycle_vocabulary("the old instruction"))
        self.assertTrue(contains_lifecycle_vocabulary("pending-validation"))
        self.assertTrue(contains_lifecycle_vocabulary("incompatible observations"))
        self.assertFalse(contains_lifecycle_vocabulary("Folder routing"))
        self.assertFalse(contains_lifecycle_vocabulary("scaffold action"))

    def test_committed_prompts_are_lifecycle_neutral(self) -> None:
        for task in TASKS:
            with self.subTest(task=task):
                text = (ROOT / "prompts" / f"{task}.md").read_text(encoding="utf-8")
                self.assertFalse(contains_lifecycle_vocabulary(text))

    def test_prompt_byte_change_breaks_protocol_lock(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "prompts" / "superseded-rule.md"
            path.write_text(
                path.read_text(encoding="utf-8") + "\nUse 30 days.\n",
                encoding="utf-8",
            )

        errors = self.validate_copy(mutate, with_protocol_lock=True)
        self.assertTrue(any("protocol hash mismatch" in error for error in errors))

    def test_agents_byte_change_breaks_protocol_lock(self) -> None:
        def mutate(root: Path) -> None:
            path = (
                root
                / "fixtures"
                / "pilot-01"
                / "conditions"
                / "source-only"
                / "AGENTS.md"
            )
            path.write_text(
                path.read_text(encoding="utf-8") + "\nPrefer one retry.\n",
                encoding="utf-8",
            )

        errors = self.validate_copy(mutate, with_protocol_lock=True)
        self.assertTrue(any("protocol hash mismatch" in error for error in errors))

    def test_rejects_malformed_protocol_hash_without_throwing(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "fixtures" / "pilot-01" / "protocol-lock.json"
            protocol_lock = self.load_json(path)
            protocol_lock[PROTOCOL_PATHS[0]] = "ABC123"
            self.write_json(path, protocol_lock)

        errors = self.validate_copy(mutate, with_protocol_lock=True)
        self.assertTrue(any("has invalid hash" in error for error in errors))

    def test_rejects_missing_and_extra_protocol_entries_without_throwing(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "fixtures" / "pilot-01" / "protocol-lock.json"
            protocol_lock = self.load_json(path)
            del protocol_lock[PROTOCOL_PATHS[0]]
            protocol_lock["../outside.md"] = "0" * 64
            self.write_json(path, protocol_lock)

        errors = self.validate_copy(mutate, with_protocol_lock=True)
        self.assertTrue(any("exact protocol file set" in error for error in errors))
        self.assertTrue(any("has unsafe path" in error for error in errors))

    def test_rejects_malformed_hash_on_extra_protocol_entry(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "fixtures" / "pilot-01" / "protocol-lock.json"
            protocol_lock = self.load_json(path)
            protocol_lock["prompts/extra.md"] = "ABC123"
            self.write_json(path, protocol_lock)

        errors = self.validate_copy(mutate, with_protocol_lock=True)
        self.assertTrue(any("has invalid hash" in error for error in errors))

    def test_rejects_missing_protocol_lock(self) -> None:
        def mutate(root: Path) -> None:
            (root / "fixtures" / "pilot-01" / "protocol-lock.json").unlink()

        errors = self.validate_copy(mutate, with_protocol_lock=True)
        self.assertTrue(any("missing protocol lock" in error for error in errors))

    def test_protocol_lock_is_privacy_scanned(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "fixtures" / "pilot-01" / "protocol-lock.json"
            protocol_lock = self.load_json(path)
            protocol_lock[PROTOCOL_PATHS[0]] = "/Users/example/private"
            self.write_json(path, protocol_lock)

        errors = self.validate_copy(mutate, with_protocol_lock=True)
        self.assertTrue(any("private-data marker" in error for error in errors))

    def test_protocol_errors_redact_untrusted_keys_and_values(self) -> None:
        private_path = "/Users/private-operator/secret-input.md"
        secret_key = "api_key=LOCK_KEY_SHOULD_NOT_LEAK"
        secret_value = "sk-LOCK_VALUE_SHOULD_NOT_LEAK"

        def mutate(root: Path) -> None:
            path = root / "fixtures" / "pilot-01" / "protocol-lock.json"
            protocol_lock = self.load_json(path)
            protocol_lock[private_path] = "not-a-hash"
            protocol_lock[secret_key] = secret_value
            self.write_json(path, protocol_lock)

        errors = self.validate_copy(mutate, with_protocol_lock=True)
        rendered = "\n".join(errors)
        self.assertTrue(errors)
        self.assertNotIn(private_path, rendered)
        self.assertNotIn(secret_key, rendered)
        self.assertNotIn(secret_value, rendered)

    def test_rejects_prompt_condition_leak(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "prompts" / "active-decision.md"
            path.write_text(
                path.read_text(encoding="utf-8") + "\nUse the flat-index condition.\n",
                encoding="utf-8",
            )

        errors = self.validate_copy(mutate)
        self.assertTrue(any("prompt leaks condition name" in error for error in errors))

    def test_require_generated_reports_both_missing_files(self) -> None:
        errors = self.validate_copy(require_generated=True)
        self.assertIn("missing generated flat index: generated/flat-index.md", errors)
        self.assertIn(
            "missing generated state projection: generated/state-projection.json",
            errors,
        )

    def test_fully_valid_generated_views_pass(self) -> None:
        self.assertEqual(
            self.validate_copy(require_generated=True, with_generated=True), []
        )

    def test_rejects_flat_index_status_leak(self) -> None:
        def mutate(root: Path) -> None:
            path = (
                root
                / "fixtures"
                / "pilot-01"
                / "generated"
                / "flat-index.md"
            )
            path.write_text(
                path.read_text(encoding="utf-8") + "\nstatus: superseded\n",
                encoding="utf-8",
            )

        errors = self.validate_copy(
            mutate, require_generated=True, with_generated=True
        )
        self.assertIn("flat index leaks status", errors)

    def test_rejects_flat_index_extra_or_missing_rows(self) -> None:
        def mutate(root: Path) -> None:
            path = (
                root
                / "fixtures"
                / "pilot-01"
                / "generated"
                / "flat-index.md"
            )
            lines = path.read_text(encoding="utf-8").splitlines()
            path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")

        errors = self.validate_copy(
            mutate, require_generated=True, with_generated=True
        )
        self.assertIn("flat index does not match required format", errors)

    def test_rejects_projection_shape_and_record_field_changes(self) -> None:
        def mutate(root: Path) -> None:
            path = (
                root
                / "fixtures"
                / "pilot-01"
                / "generated"
                / "state-projection.json"
            )
            projection = self.load_json(path)
            projection["records"][0]["extra"] = "not allowed"
            projection["records"].pop()
            self.write_json(path, projection)

        errors = self.validate_copy(
            mutate, require_generated=True, with_generated=True
        )
        self.assertTrue(any("projection record fields" in error for error in errors))
        self.assertTrue(
            any("projection records do not match manifest" in error for error in errors)
        )

    def test_rejects_projection_fact_or_relation_drift(self) -> None:
        def mutate(root: Path) -> None:
            path = (
                root
                / "fixtures"
                / "pilot-01"
                / "generated"
                / "state-projection.json"
            )
            projection = self.load_json(path)
            projection["records"][0]["scope"] = "global"
            projection["records"][1]["relations"] = [
                {"type": "supersedes", "target": "AD-101"}
            ]
            self.write_json(path, projection)

        errors = self.validate_copy(
            mutate, require_generated=True, with_generated=True
        )
        self.assertTrue(any("projection facts do not match manifest" in error for error in errors))
        self.assertTrue(any("projection relations do not match manifest" in error for error in errors))

    def test_malformed_projection_fact_types_return_errors_without_throwing(self) -> None:
        def mutate(root: Path) -> None:
            path = (
                root
                / "fixtures"
                / "pilot-01"
                / "generated"
                / "state-projection.json"
            )
            projection = self.load_json(path)
            projection["records"][0]["status"] = []
            projection["records"][0]["scope"] = {}
            self.write_json(path, projection)

        errors = self.validate_copy(
            mutate, require_generated=True, with_generated=True
        )
        self.assertTrue(any("projection facts do not match manifest" in error for error in errors))

    def test_rejects_projection_body_copy(self) -> None:
        def mutate(root: Path) -> None:
            fixture_root = root / "fixtures" / "pilot-01"
            manifest = self.load_manifest(root)
            body = (fixture_root / manifest["records"][0]["source"]).read_text(
                encoding="utf-8"
            )
            path = fixture_root / "generated" / "state-projection.json"
            projection = self.load_json(path)
            projection["records"][0]["action_boundary"] = body
            self.write_json(path, projection)

        errors = self.validate_copy(
            mutate, require_generated=True, with_generated=True
        )
        self.assertIn("projection copies body", errors)

    def test_rejects_projection_partial_body_copy(self) -> None:
        def mutate(root: Path) -> None:
            fixture_root = root / "fixtures" / "pilot-01"
            manifest = self.load_manifest(root)
            body = (fixture_root / manifest["records"][0]["source"]).read_text(
                encoding="utf-8"
            )
            copied = " ".join(body.split())[20:80]
            self.assertGreaterEqual(len(copied.encode("utf-8")), 32)
            path = fixture_root / "generated" / "state-projection.json"
            projection = self.load_json(path)
            projection["records"][0]["action_boundary"] = f"Boundary: {copied}"
            self.write_json(path, projection)

        errors = self.validate_copy(
            mutate, require_generated=True, with_generated=True
        )
        self.assertIn("projection copies body", errors)

    def test_rejects_missing_expected_source(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "expected" / "answers.json"
            answers = self.load_json(path)
            answers["active-decision"]["expected_sources"][0] = "records/missing.md"
            self.write_json(path, answers)

        errors = self.validate_copy(mutate)
        self.assertTrue(any("expected source does not exist" in error for error in errors))

    def test_rejects_missing_answer_field(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "expected" / "answers.json"
            answers = self.load_json(path)
            del answers["active-decision"]["boundary"]
            self.write_json(path, answers)

        errors = self.validate_copy(mutate)
        self.assertTrue(any("exact answer keys" in error for error in errors))

    def test_rejects_duplicate_expected_sources(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "expected" / "answers.json"
            answers = self.load_json(path)
            source = answers["active-decision"]["expected_sources"][0]
            answers["active-decision"]["expected_sources"] = [source, source]
            self.write_json(path, answers)

        errors = self.validate_copy(mutate)
        self.assertTrue(any("exactly the two task sources" in error for error in errors))

    def test_rejects_private_marker(self) -> None:
        def mutate(root: Path) -> None:
            manifest = self.load_manifest(root)
            path = root / "fixtures" / "pilot-01" / manifest["records"][0]["source"]
            path.write_text(
                path.read_text(encoding="utf-8") + "\n/Users/example/private\n",
                encoding="utf-8",
            )

        errors = self.validate_copy(mutate)
        self.assertTrue(any("private-data marker" in error for error in errors))

    def test_rejects_generated_private_marker(self) -> None:
        def mutate(root: Path) -> None:
            path = (
                root
                / "fixtures"
                / "pilot-01"
                / "generated"
                / "state-projection.json"
            )
            projection = self.load_json(path)
            projection["records"][0]["action_boundary"] = "/Users/example/private"
            self.write_json(path, projection)

        errors = self.validate_copy(
            mutate, require_generated=True, with_generated=True
        )
        self.assertTrue(any("private-data marker" in error for error in errors))

    def test_rejects_missing_task_and_condition(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "fixtures" / "pilot-01" / "manifest.json"
            manifest = self.load_json(path)
            manifest["task_ids"].pop()
            manifest["condition_ids"].pop()
            self.write_json(path, manifest)

        errors = self.validate_copy(mutate)
        self.assertTrue(any("exactly 5 task IDs" in error for error in errors))
        self.assertTrue(any("exactly 3 condition IDs" in error for error in errors))

    def test_malformed_list_members_return_errors_without_throwing(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "fixtures" / "pilot-01" / "manifest.json"
            manifest = self.load_json(path)
            manifest["condition_ids"][0] = []
            manifest["task_ids"][0] = {}
            self.write_json(path, manifest)

        errors = self.validate_copy(mutate)
        self.assertTrue(any("condition IDs must be strings" in error for error in errors))
        self.assertTrue(any("task IDs must be strings" in error for error in errors))

    def test_invalid_utf8_inputs_return_errors_without_throwing(self) -> None:
        def path_for(root: Path, label: str) -> Path:
            manifest = self.load_manifest(root)
            if label == "record":
                return root / "fixtures" / "pilot-01" / manifest["records"][0]["source"]
            if label == "agents":
                return (
                    root
                    / "fixtures"
                    / "pilot-01"
                    / "conditions"
                    / "source-only"
                    / "AGENTS.md"
                )
            return root / "prompts" / "active-decision.md"

        for label in ("record", "agents", "prompt"):
            with self.subTest(label=label):
                def mutate(root: Path, current_label=label) -> None:
                    path_for(root, current_label).write_bytes(b"\xff\xfe\x00")

                errors = self.validate_copy(mutate)
                self.assertTrue(any("UTF-8" in error for error in errors))

    def test_invalid_utf8_generated_inputs_return_errors_without_throwing(self) -> None:
        for name in ("flat-index.md", "state-projection.json"):
            with self.subTest(name=name):
                def mutate(root: Path, current_name=name) -> None:
                    path = (
                        root
                        / "fixtures"
                        / "pilot-01"
                        / "generated"
                        / current_name
                    )
                    path.write_bytes(b"\xff\xfe\x00")

                errors = self.validate_copy(
                    mutate, require_generated=True, with_generated=True
                )
                self.assertTrue(any("UTF-8" in error for error in errors))

    def test_nul_source_returns_error_without_throwing(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "fixtures" / "pilot-01" / "manifest.json"
            manifest = self.load_json(path)
            manifest["records"][0]["source"] = "records/ad-101\x00.md"
            self.write_json(path, manifest)

        errors = self.validate_copy(mutate)
        self.assertTrue(
            any("canonical POSIX-relative source" in error for error in errors)
        )

    def test_rejects_filename_or_title_lifecycle_leak(self) -> None:
        def title_mutation(root: Path) -> None:
            path = root / "fixtures" / "pilot-01" / "manifest.json"
            manifest = self.load_json(path)
            manifest["records"][0]["title"] = "Current approved rule"
            self.write_json(path, manifest)

        title_errors = self.validate_copy(title_mutation)
        self.assertTrue(
            any("answer-bearing lifecycle vocabulary" in error for error in title_errors)
        )

        def filename_mutation(root: Path) -> None:
            fixture_root = root / "fixtures" / "pilot-01"
            manifest_path = fixture_root / "manifest.json"
            manifest = self.load_json(manifest_path)
            record = manifest["records"][0]
            old_source = record["source"]
            new_source = "records/current-rule.md"
            (fixture_root / old_source).rename(fixture_root / new_source)
            record["source"] = new_source
            self.write_json(manifest_path, manifest)
            answers_path = root / "expected" / "answers.json"
            answers = self.load_json(answers_path)
            sources = answers[record["task_id"]]["expected_sources"]
            sources[sources.index(old_source)] = new_source
            self.write_json(answers_path, answers)

        filename_errors = self.validate_copy(filename_mutation)
        self.assertTrue(
            any("answer-bearing lifecycle vocabulary" in error for error in filename_errors)
        )

    def test_rejects_record_symlink_escape_without_leaking_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            root = base / "fixture-copy"
            root.mkdir()
            self.copy_committed_fixture(root)
            manifest = self.load_manifest(root)
            source = root / "fixtures" / "pilot-01" / manifest["records"][0]["source"]
            external = base / "outside-secret.md"
            external.write_text("DO_NOT_LEAK_EXTERNAL_CONTENT", encoding="utf-8")
            source.unlink()
            source.symlink_to(external)

            errors = validate(root)

            self.assertTrue(any("symlinked fixture file" in error for error in errors))
            rendered = "\n".join(errors)
            self.assertNotIn("DO_NOT_LEAK_EXTERNAL_CONTENT", rendered)
            self.assertNotIn(str(external), rendered)

    def test_rejects_rubric_total_mismatch(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "expected" / "rubric.json"
            rubric = self.load_json(path)
            rubric["formal_max_score"] = 74
            self.write_json(path, rubric)

        errors = self.validate_copy(mutate)
        self.assertTrue(any("rubric totals are inconsistent" in error for error in errors))

    def test_rejects_wrong_rubric_criterion_set(self) -> None:
        def mutate(root: Path) -> None:
            path = root / "expected" / "rubric.json"
            rubric = self.load_json(path)
            rubric["tasks"]["active-decision"]["criteria"][0]["id"] = "extra-style"
            self.write_json(path, rubric)

        errors = self.validate_copy(mutate)
        self.assertTrue(any("five frozen criterion IDs" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
