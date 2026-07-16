from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import update_readme_index


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
                        "mowen_directory_url": "https://example.test/mowen/one",
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
                        "mowen_directory_url": "https://example.test/mowen/two",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def write_article(root: Path, filename: str, title: str, series: str) -> None:
    path = root / "content" / "articles" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""---
title: {title}
title_en: {title} EN
status: ready
series: {series}
---

# {title}
""",
        encoding="utf-8",
    )


class UpdateReadmeIndexTest(unittest.TestCase):
    def test_rows_keep_global_wiki_pages_and_reset_series_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_series_catalog(root)
            write_article(root, "2026-07-01-one.md", "第一篇", "series-one")
            write_article(root, "2026-07-02-two.md", "第二篇", "series-one")
            write_article(root, "2026-07-03-three.md", "第三篇", "series-two")

            rows = update_readme_index.article_rows(root)

            self.assertEqual(
                [row["github_wiki"].rsplit("/", 1)[-1] for row in rows],
                ["01-%E7%AC%AC%E4%B8%80%E7%AF%87", "02-%E7%AC%AC%E4%BA%8C%E7%AF%87", "03-%E7%AC%AC%E4%B8%89%E7%AF%87"],
            )
            self.assertEqual(
                [(row["series_id"], row["series_sequence"]) for row in rows],
                [("series-one", 1), ("series-one", 2), ("series-two", 1)],
            )

    def test_index_lines_group_articles_and_use_series_directory_urls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_series_catalog(root)
            write_article(root, "2026-07-01-one.md", "第一篇", "series-one")
            write_article(root, "2026-07-02-two.md", "第二篇", "series-two")
            rows = update_readme_index.article_rows(root)

            zh_lines, en_lines = update_readme_index.build_index_lines(rows, root)

            zh = "\n".join(zh_lines)
            en = "\n".join(en_lines)
            self.assertIn("### 系列一（已完成，共 1 篇）", zh)
            self.assertIn("[墨问系列目录](https://example.test/mowen/one)", zh)
            self.assertIn("### 系列二（更新中，共 1 篇）", zh)
            self.assertIn("### Series One (Complete, 1 article)", en)
            self.assertIn("[MoWen series collection](https://example.test/mowen/two)", en)

    def test_unknown_series_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_series_catalog(root)
            write_article(root, "2026-07-01-one.md", "第一篇", "missing-series")

            with self.assertRaisesRegex(ValueError, "Unknown article series"):
                update_readme_index.article_rows(root)


if __name__ == "__main__":
    unittest.main()
