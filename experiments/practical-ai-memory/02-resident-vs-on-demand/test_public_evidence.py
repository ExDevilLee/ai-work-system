from __future__ import annotations

import unittest

from build_public_evidence import sanitize_final
from validate_public_evidence import validate_score


class PublicEvidenceTest(unittest.TestCase):
    def test_sanitize_final_rewrites_workspace_link(self) -> None:
        source = "[source](/var/folders/example/workspace/memory/CURRENT.md:3)"
        self.assertEqual(
            sanitize_final(source, "index-only"),
            "# 模型最终回答\n\n"
            "[source](../../fixtures/index-only/memory/CURRENT.md)\n",
        )

    def test_sanitize_final_redacts_user_path(self) -> None:
        self.assertEqual(
            sanitize_final("/Users/example/private.txt", "index-only"),
            "# 模型最终回答\n\n<redacted-user-path>\n",
        )

    def test_sanitize_final_removes_trailing_whitespace(self) -> None:
        self.assertEqual(
            sanitize_final("line  \nnext", "index-only"),
            "# 模型最终回答\n\nline\nnext\n",
        )

    def test_accepts_protocol_valid_non_full_score(self) -> None:
        record = {
            "run_name": "formal-01-critical-boundary-index-only",
            "score": {
                "correctness_score": 5,
                "correctness_max": 6,
                "protocol_valid": True,
                "unsupported_claims": 0,
                "irrelevant_project_facts": 0,
            },
        }

        self.assertEqual(validate_score(record), [])


if __name__ == "__main__":
    unittest.main()
