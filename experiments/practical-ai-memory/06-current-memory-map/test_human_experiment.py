import json
import tempfile
import unittest
from pathlib import Path

from human_experiment import HumanExperimentStore, SubmissionError, validate_saved_result


def complete_condition(condition, pack_id, questions):
    return {
        "condition": condition,
        "pack_id": pack_id,
        "elapsed_ms": 120_000,
        "correct": 5,
        "total": 5,
        "detail_opens": 2,
        "answer_changes": 1,
        "confidence": 4,
        "events": [
            {
                "question_id": question["id"],
                "selected_choice": question["choices"][0]["id"],
                "elapsed_ms": 10_000,
            }
            for question in questions
        ],
    }


class HumanExperimentStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.store = HumanExperimentStore(Path(self.temp_dir.name))
        self.session = self.store.create_session()

    def valid_submission(self):
        assignments = {item["condition"]: item for item in self.session["conditions"]}
        return {
            "session_id": self.session["session_id"],
            "condition_order": self.session["condition_order"],
            "conditions": [
                complete_condition(
                    "state-table",
                    assignments["state-table"]["pack_id"],
                    assignments["state-table"]["pack"]["questions"],
                ),
                complete_condition(
                    "visual-map",
                    assignments["visual-map"]["pack_id"],
                    assignments["visual-map"]["pack"]["questions"],
                ),
            ],
        }

    def test_accepts_complete_synthetic_result(self):
        result = self.store.complete(self.valid_submission())

        self.assertEqual(result["status"], "complete")
        self.assertTrue((Path(self.temp_dir.name) / f"{self.session['session_id']}.json").is_file())

    def test_validates_saved_result_without_session_identity(self):
        self.store.complete(self.valid_submission())
        result_path = Path(self.temp_dir.name) / f"{self.session['session_id']}.json"

        self.assertEqual(validate_saved_result(result_path, Path(self.temp_dir.name)), (2, 10))

    def test_saved_result_validation_rejects_outside_path(self):
        outside = Path(self.temp_dir.name).parent / "outside.json"
        outside.write_text('{"conditions": []}', encoding="utf-8")

        with self.assertRaises(SubmissionError):
            validate_saved_result(outside, Path(self.temp_dir.name))

    def test_rejects_missing_timer_or_answers(self):
        payload = self.valid_submission()
        del payload["conditions"][0]["elapsed_ms"]
        with self.assertRaises(SubmissionError):
            self.store.complete(payload)

        payload = self.valid_submission()
        payload["conditions"][1]["events"] = payload["conditions"][1]["events"][:4]
        with self.assertRaises(SubmissionError):
            self.store.complete(payload)

    def test_rejects_absolute_paths_and_identity_fields(self):
        for field, value in {
            "name": "Lee",
            "email": "lee@example.test",
            "username": "lee",
            "provider": "hidden",
            "thread_id": "thread-123",
            "note": "/private/tmp/result",
        }.items():
            with self.subTest(field=field):
                payload = self.valid_submission()
                payload[field] = value
                with self.assertRaises(SubmissionError):
                    self.store.complete(payload)

    def test_rejects_duplicate_condition(self):
        payload = self.valid_submission()
        payload["conditions"][1]["condition"] = "state-table"
        with self.assertRaises(SubmissionError):
            self.store.complete(payload)

    def test_rejects_malformed_event_types(self):
        payload = self.valid_submission()
        payload["conditions"][0]["events"][0]["question_id"] = ["not", "a", "string"]
        with self.assertRaises(SubmissionError):
            self.store.complete(payload)

    def test_summary_contains_only_aggregate_fields(self):
        self.store.complete(self.valid_submission())
        summary = self.store.summary(self.session["session_id"])
        encoded = json.dumps(summary, sort_keys=True)

        self.assertEqual(set(summary), {"conditions"})
        self.assertEqual(len(summary["conditions"]), 2)
        self.assertNotIn(self.session["session_id"], encoded)
        self.assertNotIn("events", encoded)
        self.assertNotIn("path", encoded)

    def test_browser_smoke_mode_never_serves_formal_packs(self):
        smoke_store = HumanExperimentStore(Path(self.temp_dir.name) / "browser-smoke", mode="browser-smoke")
        session = smoke_store.create_session()

        self.assertEqual({item["pack_id"] for item in session["conditions"]}, {"browser-smoke-a", "browser-smoke-b"})
        self.assertNotIn("pack-a", json.dumps(session))
        self.assertNotIn("pack-b", json.dumps(session))


if __name__ == "__main__":
    unittest.main()
