from __future__ import annotations

import unittest

from build_public_evidence import sanitize_final


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


if __name__ == "__main__":
    unittest.main()
