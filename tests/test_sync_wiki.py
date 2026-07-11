import tempfile
import unittest
from pathlib import Path

from scripts.sync_wiki import render_article, rewrite_asset_urls, write_wiki


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

    def test_render_article_links_previous_home_and_next_pages(self) -> None:
        article = {
            "path": Path.cwd() / "content/articles/example.md",
            "body": "# 示例\n\n正文\n",
        }

        rendered = render_article(
            article,
            wiki_base_url="https://github.com/example/repo/wiki",
            previous_page="01-上一篇",
            next_page="03-下一篇",
        )

        self.assertIn(
            "| [上一篇](https://github.com/example/repo/wiki/01-%E4%B8%8A%E4%B8%80%E7%AF%87) "
            "| [目录](https://github.com/example/repo/wiki/Home) "
            "| [下一篇](https://github.com/example/repo/wiki/03-%E4%B8%8B%E4%B8%80%E7%AF%87) |",
            rendered,
        )

    def test_render_article_marks_missing_neighbors_as_none(self) -> None:
        article = {
            "path": Path.cwd() / "content/articles/example.md",
            "body": "# 示例\n",
        }

        rendered = render_article(
            article,
            wiki_base_url="https://gitee.com/example/repo/wikis",
        )

        self.assertIn(
            "| 上一篇：无 | [目录](https://gitee.com/example/repo/wikis/Home) | 下一篇：无 |",
            rendered,
        )

    def test_full_rebuild_updates_former_last_article_navigation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wiki_dir = Path(tmp)
            first = {
                "path": Path.cwd() / "content/articles/first.md",
                "title": "第一篇",
                "summary": "",
                "body": "# 第一篇\n",
                "page": "01-第一篇",
            }
            second = {
                "path": Path.cwd() / "content/articles/second.md",
                "title": "第二篇",
                "summary": "",
                "body": "# 第二篇\n",
                "page": "02-第二篇",
            }

            write_wiki(
                wiki_dir,
                [first],
                "Test Wiki",
                "https://example.test/wiki",
            )
            self.assertIn(
                "下一篇：无",
                (wiki_dir / "01-第一篇.md").read_text(encoding="utf-8"),
            )

            write_wiki(
                wiki_dir,
                [first, second],
                "Test Wiki",
                "https://example.test/wiki",
            )
            rebuilt = (wiki_dir / "01-第一篇.md").read_text(encoding="utf-8")

            self.assertIn(
                "[下一篇](https://example.test/wiki/02-%E7%AC%AC%E4%BA%8C%E7%AF%87)",
                rebuilt,
            )


if __name__ == "__main__":
    unittest.main()
