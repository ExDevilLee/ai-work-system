from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from generate_views import build_state_projection, load_manifest, render_coverage_governance
from score_probe import score_answer, score_run
from validate_fixtures import validate


class CoverageGovernancePOCTest(unittest.TestCase):
    def test_frozen_fixture_validates(self) -> None:
        self.assertEqual(validate(), [])

    def test_projection_reports_gap_and_governance_signals(self) -> None:
        output = render_coverage_governance(load_manifest())
        self.assertIn("incident-handling | win11 | no-active-record | coverage-gap", output)
        self.assertIn("release-readiness | global | active-record | review-due", output)
        self.assertIn("cache-policy | project | no-active-record | coverage-gap, unresolved-conflict, owner-missing", output)

    def test_state_projection_keeps_source_links(self) -> None:
        projection = build_state_projection(load_manifest())
        records = projection["records"]
        self.assertEqual(len(records), 6)
        self.assertTrue(all(str(record["source"]).startswith("records/") for record in records))

    def test_coverage_gap_score_requires_human_only_boundary(self) -> None:
        good = "incident-handling / win11 has no current record. manifest.json and records/RR-101.md were used. 人工复核，本次不创建新规则。"
        self.assertTrue(all(score_answer(good).values()))
        human_owner = "incident-handling / win11 has no current record. manifest.json and records/RR-101.md were used. 人类负责人复核，本次不新增规则。"
        self.assertTrue(all(score_answer(human_owner).values()))
        self.assertFalse(score_answer("incident-handling win11 manifest.json records/RR-101.md 自动创建新规则")["human_only_next_step"])

    def test_score_run_rejects_unsuccessful_process(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            (run_dir / "metadata.json").write_text('{"condition":"source-only","exit_code":1,"final_answer_present":true}', encoding="utf-8")
            (run_dir / "final.md").write_text("incident-handling win11 no current manifest.json records/RR-101.md 人工不创建新规则", encoding="utf-8")
            self.assertFalse(score_run(run_dir)["passed"])


if __name__ == "__main__":
    unittest.main()
