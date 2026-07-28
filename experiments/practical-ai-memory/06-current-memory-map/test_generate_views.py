from __future__ import annotations

import json
import re
import shutil
import tempfile
import unicodedata
import unittest
from collections import Counter
from pathlib import Path

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


class GenerateViewsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = load_manifest(ROOT / "fixtures" / "pilot-01" / "manifest.json")

    def load_pack(self, pack_id: str) -> dict[str, object]:
        return json.loads(
            (ROOT / "human-fixtures" / f"{pack_id}.json").read_text(
                encoding="utf-8"
            )
        )

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

    def test_table_and_map_preserve_equal_fact_sets_for_each_pack(self) -> None:
        for pack_id in ("pack-a", "pack-b"):
            with self.subTest(pack_id=pack_id):
                pack = self.load_pack(pack_id)
                expected = human_fact_set(pack)
                self.assertEqual(human_fact_set(build_state_table(pack)), expected)
                self.assertEqual(human_fact_set(build_visual_map(pack)), expected)

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
            return (
                Counter(record["status"] for record in records),
                Counter(
                    relation["type"]
                    for record in records
                    for relation in record["relations"]
                ),
                Counter(record["scope"] for record in records),
                len(pack["questions"]),
                len(pack["questions"]),
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

    def test_real_generator_rerun_leaves_committed_artifacts_unchanged(self) -> None:
        generated = ROOT / "fixtures" / "pilot-01" / "generated"
        before = {name: (generated / name).read_bytes() for name in GENERATED_NAMES}
        generate_all(ROOT)
        after = {name: (generated / name).read_bytes() for name in GENERATED_NAMES}
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
