import json
import tempfile
import unittest
from pathlib import Path

from fixture_model import (
    VALID_STATUSES,
    canonical_json,
    fact_set,
    load_manifest,
    validate_manifest,
)


def valid_manifest() -> dict:
    return {
        "schema_version": 1,
        "records": [
            {
                "id": "MEM-001",
                "status": "active",
                "scope": "project",
                "source": "records/decisions/current.md",
                "relations": [
                    {"type": "supersedes", "target": "MEM-002"}
                ],
            },
            {
                "id": "MEM-002",
                "status": "superseded",
                "scope": "project",
                "source": "records/decisions/old.md",
            },
            {
                "id": "MEM-003",
                "status": "conflict",
                "scope": "global",
                "source": "records/observations/conflict.md",
                "relations": [
                    {"type": "conflicts-with", "target": "MEM-001"}
                ],
            },
            {
                "id": "MEM-004",
                "status": "pending-validation",
                "scope": "global",
                "source": "records/observations/pending.md",
            },
            {
                "id": "MEM-005",
                "status": "active",
                "scope": "macos",
                "source": "records/rules/scoped.md",
            },
        ],
    }


class FixtureModelTest(unittest.TestCase):
    def write_manifest(self, manifest: dict) -> Path:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        path = Path(temporary_directory.name) / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def test_valid_manifest_covers_all_statuses_and_scope_boundary(self) -> None:
        model = load_manifest(self.write_manifest(valid_manifest()))

        self.assertEqual(
            VALID_STATUSES,
            frozenset(
                {"active", "superseded", "conflict", "pending-validation"}
            ),
        )
        self.assertEqual(validate_manifest(model), [])
        self.assertEqual(len(model["records"]), 5)
        self.assertEqual(model["records"][4]["scope"], "macos")

    def test_missing_or_empty_source_is_rejected(self) -> None:
        for source in (None, "", "   "):
            with self.subTest(source=source):
                manifest = valid_manifest()
                if source is None:
                    del manifest["records"][0]["source"]
                else:
                    manifest["records"][0]["source"] = source

                errors = validate_manifest(manifest)

                self.assertTrue(any("non-empty source" in error for error in errors))

    def test_absolute_source_is_rejected_for_posix_and_windows(self) -> None:
        for source in (
            "/private/example.md",
            r"C:\Users\Example\record.md",
            r"\records\record.md",
            r"\\server\share\record.md",
        ):
            with self.subTest(source=source):
                manifest = valid_manifest()
                manifest["records"][0]["source"] = source

                errors = validate_manifest(manifest)

                self.assertTrue(any("relative source" in error for error in errors))

    def test_duplicate_ids_are_rejected(self) -> None:
        manifest = valid_manifest()
        manifest["records"][1]["id"] = "MEM-001"

        self.assertTrue(
            any("duplicate id 'MEM-001'" in error for error in validate_manifest(manifest))
        )

    def test_unsupported_status_is_rejected(self) -> None:
        manifest = valid_manifest()
        manifest["records"][0]["status"] = "archived"

        self.assertTrue(
            any("unsupported status" in error for error in validate_manifest(manifest))
        )

    def test_invalid_scope_is_rejected(self) -> None:
        manifest = valid_manifest()
        manifest["records"][0]["scope"] = "everywhere"

        self.assertTrue(
            any("invalid scope" in error for error in validate_manifest(manifest))
        )

    def test_malformed_relations_are_rejected(self) -> None:
        malformed_relations = (
            "MEM-001",
            ["MEM-001"],
            [{"type": "depends-on", "target": "MEM-001"}],
            [{"type": "supersedes"}],
            [{"type": "conflicts-with", "target": ""}],
        )
        for relations in malformed_relations:
            with self.subTest(relations=relations):
                manifest = valid_manifest()
                manifest["records"][1]["relations"] = relations

                errors = validate_manifest(manifest)

                self.assertTrue(any("malformed relation" in error for error in errors))

    def test_unknown_relation_target_is_rejected(self) -> None:
        manifest = valid_manifest()
        manifest["records"][0]["relations"][0]["target"] = "MEM-999"

        self.assertTrue(
            any("unknown relation target 'MEM-999'" in error for error in validate_manifest(manifest))
        )

    def test_validate_manifest_returns_errors_without_raising(self) -> None:
        errors = validate_manifest({"records": "not-a-list"})

        self.assertIsInstance(errors, list)
        self.assertTrue(errors)

    def test_validate_manifest_handles_unhashable_field_values(self) -> None:
        manifest = valid_manifest()
        manifest["records"][0]["status"] = []
        manifest["records"][0]["scope"] = {}
        manifest["records"][0]["relations"][0]["type"] = []

        errors = validate_manifest(manifest)

        self.assertTrue(any("unsupported status" in error for error in errors))
        self.assertTrue(any("invalid scope" in error for error in errors))
        self.assertTrue(any("malformed relation" in error for error in errors))

    def test_load_manifest_aggregates_validation_errors(self) -> None:
        manifest = valid_manifest()
        manifest["records"][0]["source"] = ""
        manifest["records"][1]["status"] = "archived"

        with self.assertRaises(ValueError) as raised:
            load_manifest(self.write_manifest(manifest))

        self.assertIn("non-empty source", str(raised.exception))
        self.assertIn("unsupported status", str(raised.exception))

    def test_fact_set_is_stable(self) -> None:
        model = load_manifest(self.write_manifest(valid_manifest()))

        self.assertEqual(
            fact_set(model),
            {
                ("MEM-001", "active", "project", "records/decisions/current.md"),
                ("MEM-002", "superseded", "project", "records/decisions/old.md"),
                ("MEM-003", "conflict", "global", "records/observations/conflict.md"),
                ("MEM-004", "pending-validation", "global", "records/observations/pending.md"),
                ("MEM-005", "active", "macos", "records/rules/scoped.md"),
            },
        )

    def test_fact_set_rejects_invalid_input(self) -> None:
        manifest = valid_manifest()
        manifest["records"][0]["source"] = ""

        with self.assertRaisesRegex(ValueError, "non-empty source"):
            fact_set(manifest)

    def test_canonical_json_is_deterministic_utf8_with_one_lf(self) -> None:
        value = {"z": [2, 1], "message": "当前"}

        encoded = canonical_json(value)

        self.assertEqual(encoded, b'{"message":"\xe5\xbd\x93\xe5\x89\x8d","z":[2,1]}\n')
        self.assertFalse(encoded.endswith(b"\n\n"))
        self.assertEqual(canonical_json({"message": "当前", "z": [2, 1]}), encoded)

    def test_canonical_json_rejects_non_serializable_objects(self) -> None:
        with self.assertRaises(TypeError):
            canonical_json({"value": object()})


if __name__ == "__main__":
    unittest.main()
