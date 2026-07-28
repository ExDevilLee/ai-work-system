from __future__ import annotations

import json
import re
import shutil
import tempfile
import unicodedata
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

import generate_views as generate_views_module
from fixture_model import VALID_STATUSES, canonical_json, load_manifest
from generate_views import (
    build_state_projection,
    build_state_table,
    build_visual_map,
    generate_all,
    human_fact_set,
    render_flat_index,
    validate_human_pack,
)
from validate_fixtures import ROOT, validate


GENERATED_NAMES = (
    "flat-index.md",
    "state-projection.json",
    "state-table.json",
    "visual-map.json",
)
RELATION_TYPES = ("supersedes", "conflicts-with")
ANSWER_FIELDS = {"correct_choice", "answer", "explanation"}


def normalized_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def all_strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from all_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from all_strings(item)


def has_common_utf8_window(first: str, second: str, size: int = 32) -> bool:
    first_bytes = normalized_text(first).encode("utf-8")
    second_bytes = normalized_text(second).encode("utf-8")
    shorter, longer = sorted((first_bytes, second_bytes), key=len)
    return len(shorter) >= size and any(
        shorter[index : index + size] in longer
        for index in range(len(shorter) - size + 1)
    )


def full_human_fact_set(view: dict[str, object]) -> set[tuple[object, ...]]:
    return {
        (
            record["id"],
            record["title"],
            record["status"],
            record["scope"],
            record["source"],
            tuple(
                sorted(
                    (relation["type"], relation["target"])
                    for relation in record["relations"]
                )
            ),
            record["detail"],
        )
        for record in view["records"]
    }


class GenerateViewsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = load_manifest(ROOT / "fixtures" / "pilot-01" / "manifest.json")

    def load_pack(self, pack_id: str) -> dict[str, object]:
        return json.loads(
            (ROOT / "human-fixtures" / f"{pack_id}.json").read_text(
                encoding="utf-8"
            )
        )

    def copy_generation_root(self, destination: Path) -> None:
        shutil.copytree(ROOT / "fixtures", destination / "fixtures")
        shutil.copytree(ROOT / "human-fixtures", destination / "human-fixtures")

    def test_generation_is_byte_stable_and_uses_lf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            shutil.copytree(ROOT / "fixtures", root / "fixtures")
            shutil.copytree(ROOT / "human-fixtures", root / "human-fixtures")

            generate_all(root)
            generated = root / "fixtures" / "pilot-01" / "generated"
            first = {name: (generated / name).read_bytes() for name in GENERATED_NAMES}
            generate_all(root)
            second = {name: (generated / name).read_bytes() for name in GENERATED_NAMES}

            self.assertEqual(first, second)
            for name, content in second.items():
                with self.subTest(name=name):
                    self.assertTrue(content.endswith(b"\n"))
                    self.assertNotIn(b"\r", content)

    def test_committed_agent_views_pass_frozen_validator(self) -> None:
        self.assertEqual(validate(ROOT, require_generated=True), [])

    def test_flat_index_contains_only_neutral_navigation_fields(self) -> None:
        text = render_flat_index(self.manifest)
        rows = [
            "# Flat Record Index",
            "",
            "| Title | Source | Summary | Updated At |",
            "| --- | --- | --- | --- |",
        ]
        for record in sorted(self.manifest["records"], key=lambda item: item["id"]):
            rows.append(
                f"| {record['title']} | `{record['source']}` | "
                f"{record['summary']} | {record['updated_at']} |"
            )
        self.assertEqual(text, "\n".join(rows) + "\n")
        for forbidden in (*VALID_STATUSES, *RELATION_TYPES, "action_boundary"):
            self.assertIsNone(
                re.search(rf"(?<![\w-]){re.escape(forbidden)}(?![\w-])", text, re.I)
            )

    def test_projection_preserves_manifest_facts_without_body_copy(self) -> None:
        projection = build_state_projection(self.manifest)
        self.assertEqual(set(projection), {"schema_version", "records"})
        self.assertEqual(projection["schema_version"], 1)
        self.assertIs(type(projection["schema_version"]), int)
        records = projection["records"]
        self.assertEqual(
            [record["id"] for record in records],
            sorted(record["id"] for record in self.manifest["records"]),
        )
        manifest_by_id = {record["id"]: record for record in self.manifest["records"]}
        for record in records:
            self.assertEqual(
                set(record),
                {"id", "status", "scope", "source", "relations", "action_boundary"},
            )
            expected = manifest_by_id[record["id"]]
            for field in ("status", "scope", "source", "relations"):
                self.assertEqual(record[field], expected[field])
            self.assertIsInstance(record["action_boundary"], str)
            self.assertTrue(record["action_boundary"].strip())

        projection_strings = tuple(all_strings(projection["records"]))
        fixture_root = ROOT / "fixtures" / "pilot-01"
        for manifest_record in self.manifest["records"]:
            body = (fixture_root / manifest_record["source"]).read_text(encoding="utf-8")
            self.assertFalse(
                any(has_common_utf8_window(body, value) for value in projection_strings),
                manifest_record["id"],
            )

    def test_conflict_relations_always_render_pause_boundary(self) -> None:
        projection = build_state_projection(self.manifest)
        by_id = {record["id"]: record for record in projection["records"]}
        for record in self.manifest["records"]:
            if any(
                relation["type"] == "conflicts-with"
                for relation in record.get("relations", [])
            ):
                self.assertIn("Pause", by_id[record["id"]]["action_boundary"])

    def test_invalid_governance_fails_without_modifying_generated_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.copy_generation_root(root)
            generated = root / "fixtures" / "pilot-01" / "generated"
            before = {name: (generated / name).read_bytes() for name in GENERATED_NAMES}
            manifest_path = root / "fixtures" / "pilot-01" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            conflict = next(record for record in manifest["records"] if record["id"] == "UC-302")
            conflict["relations"] = []
            manifest_path.write_bytes(canonical_json(manifest))

            with self.assertRaisesRegex(ValueError, "conflicts-with must be symmetric"):
                generate_all(root)

            self.assertEqual(
                {name: (generated / name).read_bytes() for name in GENERATED_NAMES},
                before,
            )
            self.assertEqual(list(root.rglob("*.tmp")), [])

    def test_table_and_map_preserve_equal_fact_sets_for_each_pack(self) -> None:
        for pack_id in ("pack-a", "pack-b"):
            with self.subTest(pack_id=pack_id):
                pack = self.load_pack(pack_id)
                expected = human_fact_set(pack)
                self.assertEqual(human_fact_set(build_state_table(pack)), expected)
                self.assertEqual(human_fact_set(build_visual_map(pack)), expected)
                full_expected = full_human_fact_set(pack)
                self.assertEqual(
                    full_human_fact_set(build_state_table(pack)), full_expected
                )
                self.assertEqual(
                    full_human_fact_set(build_visual_map(pack)), full_expected
                )

    def test_human_packs_are_structurally_equal_but_distinct(self) -> None:
        pack_a = self.load_pack("pack-a")
        pack_b = self.load_pack("pack-b")
        self.assertEqual(validate_human_pack(pack_a), [])
        self.assertEqual(validate_human_pack(pack_b), [])
        expected_statuses = Counter(
            {"active": 2, "superseded": 1, "conflict": 1, "pending-validation": 1}
        )

        def shape(pack: dict[str, object]) -> tuple[Counter, Counter, Counter, int, int]:
            records = pack["records"]
            question_count = len(pack["questions"])
            max_score = sum(1 for _question in pack["questions"])
            return (
                Counter(record["status"] for record in records),
                Counter(
                    relation["type"]
                    for record in records
                    for relation in record["relations"]
                ),
                Counter(record["scope"] for record in records),
                question_count,
                max_score,
            )

        self.assertEqual(shape(pack_a), shape(pack_b))
        self.assertEqual(shape(pack_a)[0], expected_statuses)
        self.assertEqual(shape(pack_a)[3:], (5, 5))
        self.assertEqual(
            {record["id"] for record in pack_a["records"]}
            & {record["id"] for record in pack_b["records"]},
            set(),
        )
        for field in ("title", "detail", "source"):
            self.assertEqual(
                {record[field] for record in pack_a["records"]}
                & {record[field] for record in pack_b["records"]},
                set(),
            )
        self.assertNotEqual(
            {question["prompt"] for question in pack_a["questions"]},
            {question["prompt"] for question in pack_b["questions"]},
        )

    def test_human_pack_sources_match_frozen_synthetic_format(self) -> None:
        for pack_id in ("pack-a", "pack-b"):
            pack = self.load_pack(pack_id)
            for record in pack["records"]:
                self.assertEqual(
                    record["source"],
                    f"synthetic/{pack_id}/{record['id'].casefold()}.md",
                )
            self.assertEqual(validate_human_pack(pack), [])

    def test_human_pack_rejects_unsafe_source_forms(self) -> None:
        unsafe_sources = (
            "../outside.md",
            "/synthetic/pack-a/a-orbit-11.md",
            "synthetic/pack-a/../a-orbit-11.md",
            "synthetic\\pack-a\\a-orbit-11.md",
            r"C:\synthetic\pack-a\a-orbit-11.md",
            r"\\server\share\a-orbit-11.md",
            "synthetic/pack-a/a-orbit-11\x00.md",
        )
        for source in unsafe_sources:
            with self.subTest(source=repr(source)):
                pack = self.load_pack("pack-a")
                pack["records"][0]["source"] = source
                errors = validate_human_pack(pack)
                self.assertTrue(any("synthetic source" in error for error in errors))

    def test_human_pack_privacy_errors_redact_sensitive_content(self) -> None:
        sensitive_values = (
            "sk-SECRET123456789",
            "123e4567-e89b-42d3-a456-426614174000",
            "provider=PrivateVendor",
            "thread_id=private-thread",
            "/Users/private-user/repository/file.md",
            "username=private-operator",
            "s3://private-bucket/private-object",
        )
        for sensitive in sensitive_values:
            with self.subTest(sensitive=sensitive):
                pack = self.load_pack("pack-a")
                pack["records"][0]["detail"] = sensitive
                rendered = "\n".join(validate_human_pack(pack))
                self.assertIn("private-data marker", rendered)
                self.assertNotIn(sensitive, rendered)

        pack = self.load_pack("pack-a")
        secret = "sk-FIELD_SECRET_12345"
        pack["api_key"] = secret
        rendered = "\n".join(validate_human_pack(pack))
        self.assertIn("private-data marker", rendered)
        self.assertNotIn(secret, rendered)

    def test_human_supersedes_records_must_share_scope(self) -> None:
        pack = self.load_pack("pack-a")
        superseded = next(
            record for record in pack["records"] if record["status"] == "superseded"
        )
        superseded["scope"] = "global"
        errors = validate_human_pack(pack)
        self.assertTrue(any("same scope" in error for error in errors))
        with self.assertRaisesRegex(ValueError, "same scope"):
            build_state_table(pack)

    def test_generated_human_views_omit_answers_and_explanations(self) -> None:
        for pack_id in ("pack-a", "pack-b"):
            pack = self.load_pack(pack_id)
            for view in (build_state_table(pack), build_visual_map(pack)):
                self.assertEqual(
                    set(view),
                    {"schema_version", "pack_id", "view_type", "records", "questions"},
                )
                for question in view["questions"]:
                    self.assertTrue(ANSWER_FIELDS.isdisjoint(question))
                    self.assertEqual(set(question), {"id", "prompt", "choices"})

    def test_committed_files_are_exact_canonical_outputs(self) -> None:
        generated = ROOT / "fixtures" / "pilot-01" / "generated"
        pack_a = self.load_pack("pack-a")
        pack_b = self.load_pack("pack-b")
        expected = {
            "flat-index.md": render_flat_index(self.manifest).encode("utf-8"),
            "state-projection.json": canonical_json(build_state_projection(self.manifest)),
            "state-table.json": canonical_json(build_state_table(pack_a)),
            "visual-map.json": canonical_json(build_visual_map(pack_b)),
        }
        self.assertEqual(
            {name: (generated / name).read_bytes() for name in GENERATED_NAMES},
            expected,
        )

    def test_generated_json_files_are_raw_canonical_utf8_with_one_lf(self) -> None:
        generated = ROOT / "fixtures" / "pilot-01" / "generated"
        for name in (
            "state-projection.json",
            "state-table.json",
            "visual-map.json",
        ):
            with self.subTest(name=name):
                raw = (generated / name).read_bytes()
                self.assertEqual(raw, canonical_json(json.loads(raw.decode("utf-8"))))
                self.assertTrue(raw.endswith(b"\n"))
                self.assertFalse(raw.endswith(b"\n\n"))
                self.assertNotIn(b"\r", raw)

    def test_shuffled_inputs_render_records_sorted_by_id(self) -> None:
        manifest = json.loads(json.dumps(self.manifest))
        manifest["records"] = list(reversed(manifest["records"]))
        self.assertEqual(
            [record["id"] for record in build_state_projection(manifest)["records"]],
            sorted(record["id"] for record in manifest["records"]),
        )
        for pack_id in ("pack-a", "pack-b"):
            pack = self.load_pack(pack_id)
            pack["records"] = list(reversed(pack["records"]))
            expected_ids = sorted(record["id"] for record in pack["records"])
            self.assertEqual(
                [record["id"] for record in build_state_table(pack)["records"]],
                expected_ids,
            )
            self.assertEqual(
                [record["id"] for record in build_visual_map(pack)["records"]],
                expected_ids,
            )

    def test_malformed_human_pack_fails_before_writing_any_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            shutil.copytree(ROOT / "fixtures", root / "fixtures")
            shutil.copytree(ROOT / "human-fixtures", root / "human-fixtures")
            shutil.rmtree(root / "fixtures" / "pilot-01" / "generated")
            malformed_path = root / "human-fixtures" / "pack-b.json"
            malformed = json.loads(malformed_path.read_text(encoding="utf-8"))
            malformed["questions"][0]["correct_choice"] = "missing-choice"
            malformed_path.write_bytes(canonical_json(malformed))

            with self.assertRaisesRegex(ValueError, "correct_choice.*choice ID"):
                generate_all(root)

            generated = root / "fixtures" / "pilot-01" / "generated"
            self.assertFalse(generated.exists())
            self.assertEqual(list(root.rglob("*.tmp")), [])

    def test_malformed_human_pack_types_raise_clear_value_error(self) -> None:
        malformed = self.load_pack("pack-a")
        malformed["records"][0]["id"] = []
        malformed["records"][0]["status"] = []
        malformed["records"][3]["detail"] = []

        errors = validate_human_pack(malformed)
        self.assertTrue(any("status" in error for error in errors))
        with self.assertRaisesRegex(ValueError, "invalid human pack"):
            build_state_table(malformed)

    def assert_pack_binding_failure_preserves_generated(
        self, pack_a_id: str, pack_b_id: str, message: str
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            shutil.copytree(ROOT / "fixtures", root / "fixtures")
            shutil.copytree(ROOT / "human-fixtures", root / "human-fixtures")
            generated = root / "fixtures" / "pilot-01" / "generated"
            before = {name: (generated / name).read_bytes() for name in GENERATED_NAMES}

            for filename, pack_id in (("pack-a.json", pack_a_id), ("pack-b.json", pack_b_id)):
                path = root / "human-fixtures" / filename
                pack = json.loads(path.read_text(encoding="utf-8"))
                pack["pack_id"] = pack_id
                path.write_bytes(canonical_json(pack))

            with self.assertRaisesRegex(ValueError, message):
                generate_all(root)

            after = {name: (generated / name).read_bytes() for name in GENERATED_NAMES}
            self.assertEqual(after, before)
            self.assertEqual(list(root.rglob("*.tmp")), [])

    def test_swapped_pack_ids_fail_without_modifying_generated_files(self) -> None:
        self.assert_pack_binding_failure_preserves_generated(
            "pack-b", "pack-a", "first human pack.*pack-a"
        )

    def test_duplicate_pack_ids_fail_without_modifying_generated_files(self) -> None:
        self.assert_pack_binding_failure_preserves_generated(
            "pack-a", "pack-a", "second human pack.*pack-b"
        )

    def test_wrong_pack_id_fails_without_modifying_generated_files(self) -> None:
        self.assert_pack_binding_failure_preserves_generated(
            "wrong-pack", "pack-b", "first human pack.*pack-a"
        )

    def test_generate_all_rejects_unsafe_fixture_set_before_writes(self) -> None:
        unsafe_values = (
            "",
            ".",
            "..",
            "../pilot-01",
            "pilot-01/child",
            r"pilot-01\child",
            r"C:pilot-01",
            "pilot-01\x00",
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.copy_generation_root(root)
            generated = root / "fixtures" / "pilot-01" / "generated"
            before = {name: (generated / name).read_bytes() for name in GENERATED_NAMES}
            for fixture_set in unsafe_values:
                with self.subTest(fixture_set=repr(fixture_set)):
                    with self.assertRaisesRegex(ValueError, "fixture_set"):
                        generate_all(root, fixture_set)
                    self.assertEqual(
                        {name: (generated / name).read_bytes() for name in GENERATED_NAMES},
                        before,
                    )

    def test_generate_all_rejects_symlinked_inputs_and_outputs(self) -> None:
        for target_kind in ("pack", "manifest", "generated", "output"):
            with self.subTest(target_kind=target_kind):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    base = Path(temporary_directory)
                    root = base / "root"
                    root.mkdir()
                    self.copy_generation_root(root)
                    generated = root / "fixtures" / "pilot-01" / "generated"
                    before = {
                        name: (generated / name).read_bytes() for name in GENERATED_NAMES
                    }
                    external = base / "external"
                    if target_kind == "pack":
                        external.write_bytes(
                            (root / "human-fixtures" / "pack-a.json").read_bytes()
                        )
                        path = root / "human-fixtures" / "pack-a.json"
                        path.unlink()
                        path.symlink_to(external)
                    elif target_kind == "manifest":
                        external.write_bytes(
                            (root / "fixtures" / "pilot-01" / "manifest.json").read_bytes()
                        )
                        path = root / "fixtures" / "pilot-01" / "manifest.json"
                        path.unlink()
                        path.symlink_to(external)
                    elif target_kind == "generated":
                        shutil.move(str(generated), str(external))
                        generated.symlink_to(external, target_is_directory=True)
                    else:
                        external.write_bytes(b"EXTERNAL_SENTINEL")
                        path = generated / "state-table.json"
                        path.unlink()
                        path.symlink_to(external)
                    external_before = (
                        {path.name: path.read_bytes() for path in external.iterdir()}
                        if external.is_dir()
                        else external.read_bytes()
                    )

                    with self.assertRaisesRegex(ValueError, "symlink"):
                        generate_all(root)

                    external_after = (
                        {path.name: path.read_bytes() for path in external.iterdir()}
                        if external.is_dir()
                        else external.read_bytes()
                    )
                    self.assertEqual(external_after, external_before)
                    if target_kind not in {"generated", "output"}:
                        self.assertEqual(
                            {
                                name: (generated / name).read_bytes()
                                for name in GENERATED_NAMES
                            },
                            before,
                        )
                    self.assertEqual(list(root.rglob("*.tmp")), [])

    def test_transaction_failures_restore_every_output_or_original_absence(self) -> None:
        operations = (
            "_open_staged_file",
            "_write_staged_file",
            "_flush_staged_file",
            "_fsync_staged_file",
            "_replace_staged_file",
        )
        for existing in (True, False):
            for operation in operations:
                for fail_at in range(1, len(GENERATED_NAMES) + 1):
                    with self.subTest(
                        existing=existing, operation=operation, fail_at=fail_at
                    ):
                        with tempfile.TemporaryDirectory() as temporary_directory:
                            root = Path(temporary_directory)
                            self.copy_generation_root(root)
                            generated = root / "fixtures" / "pilot-01" / "generated"
                            if not existing:
                                shutil.rmtree(generated)
                            before = {
                                name: (generated / name).read_bytes()
                                if (generated / name).exists()
                                else None
                                for name in GENERATED_NAMES
                            }
                            original = getattr(generate_views_module, operation)
                            calls = 0

                            def injected(*args, **kwargs):
                                nonlocal calls
                                calls += 1
                                if calls == fail_at:
                                    raise OSError(
                                        f"injected {operation} failure {fail_at}"
                                    )
                                return original(*args, **kwargs)

                            with mock.patch.object(
                                generate_views_module, operation, side_effect=injected
                            ):
                                with self.assertRaisesRegex(OSError, "injected"):
                                    generate_all(root)

                            after = {
                                name: (generated / name).read_bytes()
                                if (generated / name).exists()
                                else None
                                for name in GENERATED_NAMES
                            }
                            self.assertEqual(after, before)
                            self.assertEqual(list(root.rglob("*.tmp")), [])
                            self.assertEqual(list(root.rglob("*.bak")), [])

    def test_rollback_failure_reports_both_causes_without_sensitive_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.copy_generation_root(root)
            real_replace = generate_views_module.os.replace
            calls = 0

            def injected_replace(source, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("commit exploded at /Users/private-operator/secret")
                if calls == 3:
                    raise OSError(r"rollback exploded at C:\Users\private-operator\secret")
                return real_replace(source, destination)

            with mock.patch.object(
                generate_views_module.os, "replace", side_effect=injected_replace
            ):
                with self.assertRaises(RuntimeError) as raised:
                    generate_all(root)

            rendered = str(raised.exception)
            self.assertIn("generation failed", rendered)
            self.assertIn("rollback failed", rendered)
            self.assertIn("commit exploded", rendered)
            self.assertIn("rollback exploded", rendered)
            self.assertNotIn("private-operator", rendered)
            self.assertEqual(list(root.rglob("*.tmp")), [])

    def test_real_generator_rerun_leaves_committed_artifacts_unchanged(self) -> None:
        generated = ROOT / "fixtures" / "pilot-01" / "generated"
        before = {name: (generated / name).read_bytes() for name in GENERATED_NAMES}
        generate_all(ROOT)
        after = {name: (generated / name).read_bytes() for name in GENERATED_NAMES}
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
