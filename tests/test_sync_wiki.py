import unittest
from pathlib import Path

from scripts.sync_wiki import render_article, rewrite_asset_urls


class SyncWikiTest(unittest.TestCase):
    def test_relative_article_assets_are_rewritten_for_wiki(self) -> None:
        markdown = "![结构图](images/04/memory.png)"

        rewritten = rewrite_asset_urls(markdown, "https://example.test/repo/main")

        self.assertEqual(
            rewritten,
            "![结构图](https://example.test/repo/main/content/articles/images/04/memory.png)",
        )

    def test_render_article_uses_public_asset_url(self) -> None:
        article = {
            "path": Path.cwd() / "content/articles/example.md",
            "body": "# 示例\n\n![结构图](images/example.png)\n",
        }

        rendered = render_article(article, "https://example.test/repo/main")

        self.assertIn(
            "![结构图](https://example.test/repo/main/content/articles/images/example.png)",
            rendered,
        )


if __name__ == "__main__":
    unittest.main()
