import json
import tempfile
import unittest
from pathlib import Path

from scripts.sync_wiki import (
    parse_frontmatter,
    ready_articles,
    render_article,
    rewrite_asset_urls,
    write_wiki,
)


def write_series_catalog(root: Path) -> None:
    path = root / "content" / "series.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "series": [
                    {
                        "id": "series-one",
                        "order": 1,
                        "title": "系列一",
                        "title_en": "Series One",
                        "description": "第一组",
                        "description_en": "First group",
                        "status": "complete",
                        "wiki_page": "Series-01-Series-One",
                        "mowen_directory_title": "系列一目录",
                        "mowen_directory_url": "",
                    },
                    {
                        "id": "series-two",
                        "order": 2,
                        "title": "系列二",
                        "title_en": "Series Two",
                        "description": "第二组",
                        "description_en": "Second group",
                        "status": "active",
                        "wiki_page": "Series-02-Series-Two",
                        "mowen_directory_title": "系列二目录",
                        "mowen_directory_url": "",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def write_ready_article(root: Path, filename: str, title: str, series: str) -> None:
    path = root / "content" / "articles" / series / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ntitle: {title}\nstatus: ready\nseries: {series}\nsummary: 摘要\n---\n\n# {title}\n",
        encoding="utf-8",
    )


class SyncWikiTest(unittest.TestCase):
    def test_ready_articles_keep_global_pages_and_reset_series_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_series_catalog(root)
            write_ready_article(root, "2026-07-01-one.md", "第一篇", "series-one")
            write_ready_article(root, "2026-07-02-two.md", "第二篇", "series-one")
            write_ready_article(root, "2026-07-03-three.md", "第三篇", "series-two")

            articles = ready_articles(root)

            self.assertEqual(
                [article["page"] for article in articles],
                ["01-第一篇", "02-第二篇", "03-第三篇"],
            )
            self.assertEqual(
                [(article["series_id"], article["series_sequence"]) for article in articles],
                [("series-one", 1), ("series-one", 2), ("series-two", 1)],
            )

    def test_wiki_groups_series_and_bounds_article_navigation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wiki_dir = root / "wiki"
            wiki_dir.mkdir()
            write_series_catalog(root)
            write_ready_article(root, "2026-07-01-one.md", "第一篇", "series-one")
            write_ready_article(root, "2026-07-02-two.md", "第二篇", "series-one")
            write_ready_article(root, "2026-07-03-three.md", "第三篇", "series-two")
            articles = ready_articles(root)

            write_wiki(
                wiki_dir,
                articles,
                "Test Wiki",
                "https://example.test/wiki",
                repo_root=root,
            )

            self.assertTrue((wiki_dir / "Series-01-Series-One.md").exists())
            self.assertTrue((wiki_dir / "Series-02-Series-Two.md").exists())
            home = (wiki_dir / "Home.md").read_text(encoding="utf-8")
            sidebar = (wiki_dir / "_Sidebar.md").read_text(encoding="utf-8")
            self.assertIn("### [系列一](https://example.test/wiki/Series-01-Series-One)", home)
            self.assertIn("### [系列二](https://example.test/wiki/Series-02-Series-Two)", home)
            self.assertIn("  - [第三篇](https://example.test/wiki/03-%E7%AC%AC%E4%B8%89%E7%AF%87)", sidebar)

            series_one_last = (wiki_dir / "02-第二篇.md").read_text(encoding="utf-8")
            series_two_first = (wiki_dir / "03-第三篇.md").read_text(encoding="utf-8")
            self.assertIn(
                "| [上一篇](https://example.test/wiki/01-%E7%AC%AC%E4%B8%80%E7%AF%87) "
                "| [目录](https://example.test/wiki/Series-01-Series-One) | 无 |",
                series_one_last,
            )
            self.assertIn(
                "| 无 | [目录](https://example.test/wiki/Series-02-Series-Two) | 无 |",
                series_two_first,
            )

    def test_frontmatter_parses_quoted_colon(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            article = Path(tmp) / "article.md"
            article.write_text(
                '---\ntitle: "规则: 自动化"\nstatus: ready\n---\n正文\n',
                encoding="utf-8",
            )

            metadata, body = parse_frontmatter(article)

            self.assertEqual(metadata["title"], "规则: 自动化")
            self.assertEqual(body, "正文\n")

    def test_frontmatter_rejects_invalid_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            article = Path(tmp) / "article.md"
            article.write_text(
                "---\ntitle: [未闭合\nstatus: ready\n---\n正文\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Invalid YAML frontmatter"):
                parse_frontmatter(article)

    def test_relative_article_assets_are_rewritten_for_wiki(self) -> None:
        markdown = "![结构图](images/04/memory.png)"

        rewritten = rewrite_asset_urls(
            markdown,
            "https://example.test/repo/main",
            "content/articles/series-one",
        )

        self.assertEqual(
            rewritten,
            "![结构图](https://example.test/repo/main/content/articles/series-one/images/04/memory.png)",
        )

    def test_render_article_uses_public_asset_url(self) -> None:
        article = {
            "path": Path.cwd() / "content/articles/series-one/example.md",
            "body": "# 示例\n\n![结构图](images/01/example.png)\n",
        }

        rendered = render_article(article, "https://example.test/repo/main")

        self.assertIn(
            "![结构图](https://example.test/repo/main/content/articles/series-one/images/01/example.png)",
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
            "| 无 | [目录](https://gitee.com/example/repo/wikis/Home) | 无 |",
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
                "| 无 | [目录](https://example.test/wiki/Home) | 无 |",
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
