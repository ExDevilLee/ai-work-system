import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from validate_retrieval import search, validate


class ValidateRetrievalTest(unittest.TestCase):
    def make_fixture(self, root: Path) -> None:
        corpus = root / "fixtures/pilot-01/corpus"
        packets = root / "fixtures/pilot-01/retrieval-packets"
        corpus.mkdir(parents=True)
        packets.mkdir(parents=True)
        (corpus / "alpha.md").write_text(
            "approved release decision rebuild navigation",
            encoding="utf-8",
        )
        (corpus / "beta.md").write_text(
            "unrelated archival note",
            encoding="utf-8",
        )
        (packets / "manifest.json").write_text(
            json.dumps(
                {
                    "tasks": {
                        "approved-decision": {
                            "query": "approved release decision",
                            "top_k": 1,
                            "required_sources": ["alpha.md"],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

    def test_search_orders_matching_document_first(self) -> None:
        rows = [
            ("alpha.md", "approved release decision rebuild navigation"),
            ("beta.md", "unrelated archival note"),
        ]
        self.assertEqual(search(rows, "approved release decision", 1), ["alpha.md"])

    def test_accepts_explicit_fixture_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.make_fixture(root)
            source = root / "fixtures/pilot-01"
            target = root / "fixtures/pilot-02"
            source.rename(target)
            self.assertEqual(validate(root, "pilot-02"), [])

    def test_validate_rejects_missing_required_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.make_fixture(root)
            manifest_path = root / "fixtures/pilot-01/retrieval-packets/manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["tasks"]["approved-decision"]["required_sources"] = ["beta.md"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            errors = validate(root)
            self.assertTrue(any("missing required source" in error for error in errors))

    def test_validate_fails_closed_without_fts5(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.make_fixture(root)
            with mock.patch("validate_retrieval.sqlite3.connect") as connect:
                connection = connect.return_value
                connection.execute.side_effect = sqlite3.OperationalError("no such module: fts5")
                errors = validate(root)
            self.assertTrue(any("FTS5 unavailable" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
