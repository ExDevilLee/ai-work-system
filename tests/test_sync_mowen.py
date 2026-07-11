from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.sync_mowen import (
    Article,
    build_numbered_article_body,
    build_directory_document,
    convert_article,
    discover_ready_articles,
    document_sha256,
    ensure_cover_uploaded,
    load_mapping,
    rewrite_article_asset_urls,
    save_mapping,
    sync_articles,
    sync_directory,
)


def article_text(title: str, date: str, status: str = "ready") -> str:
    return f"""---
title: {title}
date: {date}
status: {status}
summary: {title}摘要
tags:
  - AI Work System
---

# {title}

正文
"""


class FakeMowenClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.next_id = 1

    def create_rich_note(self, document: dict, tags: list[str]) -> str:
        note_id = f"new-note-{self.next_id}"
        self.next_id += 1
        self.calls.append(("create", document, tags))
        return note_id

    def edit_rich_note(self, note_id: str, document: dict) -> None:
        self.calls.append(("edit", note_id, document))

    def set_public(self, note_id: str) -> None:
        self.calls.append(("public", note_id))

    def upload_via_url(self, url: str, file_name: str) -> str:
        self.calls.append(("upload", url, file_name))
        return "cover-uuid"


class SyncMowenTest(unittest.TestCase):
    def test_relative_article_assets_are_rewritten_for_mowen(self) -> None:
        markdown = "![结构图](images/04/memory.png)"

        rewritten = rewrite_article_asset_urls(markdown)

        self.assertEqual(
            rewritten,
            "![结构图](https://gitee.com/ExDevilLee/ai-work-system/raw/main/content/articles/images/04/memory.png)",
        )

    def test_discovers_only_ready_articles_in_reverse_chronological_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            articles_dir = root / "content" / "articles"
            articles_dir.mkdir(parents=True)
            (articles_dir / "2026-07-09-old.md").write_text(
                article_text("旧文章", "2026-07-09"), encoding="utf-8"
            )
            (articles_dir / "2026-07-10-alpha.md").write_text(
                article_text("同日较早", "2026-07-10"), encoding="utf-8"
            )
            (articles_dir / "2026-07-10-zulu.md").write_text(
                article_text("同日较新", "2026-07-10"), encoding="utf-8"
            )
            (articles_dir / "2026-07-11-draft.md").write_text(
                article_text("草稿", "2026-07-11", status="draft"), encoding="utf-8"
            )

            articles = discover_ready_articles(root)

            self.assertEqual([item.title for item in articles], ["同日较新", "同日较早", "旧文章"])
            self.assertEqual(articles[0].source, "content/articles/2026-07-10-zulu.md")
            self.assertEqual([item.sequence for item in articles], [3, 2, 1])

    def test_numbered_article_body_uses_series_order_without_changing_source(self) -> None:
        article = Article(
            Path("article.md"),
            "content/articles/article.md",
            "文章标题",
            "2026-07-10",
            "摘要",
            ["AI"],
            "引言\n\n# 旧标题\n\n正文\n",
            sequence=7,
        )

        numbered = build_numbered_article_body(article)

        self.assertEqual(numbered, "引言\n\n# 07-文章标题\n\n正文\n")
        self.assertEqual(article.body, "引言\n\n# 旧标题\n\n正文\n")

    def test_directory_document_embeds_notes_newest_first(self) -> None:
        articles = [
            Article(Path("new.md"), "content/articles/new.md", "新文章", "2026-07-10", "新摘要", ["AI"], "# 新文章"),
            Article(Path("old.md"), "content/articles/old.md", "旧文章", "2026-07-09", "旧摘要", ["AI"], "# 旧文章"),
        ]
        mapping = {
            "articles": {
                "content/articles/new.md": {"note_id": "new-id"},
                "content/articles/old.md": {"note_id": "old-id"},
            }
        }

        document = build_directory_document(articles, mapping, cover_uuid="cover-id")

        self.assertEqual(document["type"], "doc")
        self.assertEqual(document["content"][0]["content"][0]["text"], "AI 长期工作系统")
        self.assertEqual(document["content"][2], {"type": "image", "attrs": {"uuid": "cover-id", "align": "center", "alt": "AI 长期工作系统"}})
        note_ids = [
            atom["attrs"]["uuid"]
            for atom in document["content"]
            if atom.get("type") == "note"
        ]
        self.assertEqual(note_ids, ["new-id", "old-id"])
        self.assertEqual(
            document["content"][-2]["content"][0],
            {"type": "text", "text": "首发地址："},
        )
        self.assertEqual(
            document["content"][-1]["content"][0],
            {
                "type": "text",
                "text": "https://github.com/ExDevilLee/ai-work-system/wiki",
                "marks": [
                    {
                        "type": "link",
                        "attrs": {"href": "https://github.com/ExDevilLee/ai-work-system/wiki"},
                    }
                ],
            },
        )

    def test_mapping_is_written_atomically_and_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "publishing" / "mowen-notes.json"
            expected = {"version": 1, "directory": {"note_id": "directory-id"}, "articles": {}}

            save_mapping(path, expected)

            self.assertEqual(load_mapping(path), expected)
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_sync_creates_missing_notes_edits_mapped_notes_and_publishes(self) -> None:
        articles = [
            Article(Path("new.md"), "content/articles/new.md", "新文章", "2026-07-10", "", ["AI"], "# 新文章"),
            Article(Path("old.md"), "content/articles/old.md", "旧文章", "2026-07-09", "", ["AI"], "# 旧文章"),
        ]
        mapping = {
            "version": 1,
            "directory": {},
            "articles": {"content/articles/old.md": {"note_id": "old-id"}},
        }
        client = FakeMowenClient()

        sync_articles(
            articles,
            mapping,
            client,
            converter=lambda article: {"type": "doc", "content": [{"type": "title", "text": article.title}]},
            publish=True,
        )

        self.assertEqual(mapping["articles"]["content/articles/new.md"]["note_id"], "new-note-1")
        self.assertEqual([call[0] for call in client.calls], ["create", "public", "edit", "public"])

    def test_sync_skips_unchanged_published_article(self) -> None:
        article = Article(Path("article.md"), "content/articles/article.md", "文章", "2026-07-10", "", ["AI"], "# 文章")
        document = {"type": "doc", "content": [{"type": "paragraph"}]}
        mapping = {
            "version": 1,
            "directory": {},
            "articles": {
                article.source: {
                    "note_id": "article-id",
                    "content_sha256": document_sha256(document),
                    "published": True,
                }
            },
        }
        client = FakeMowenClient()

        sync_articles(
            [article],
            mapping,
            client,
            converter=lambda _: document,
            publish=True,
        )

        self.assertEqual(client.calls, [])

    def test_sync_only_publishes_unchanged_private_article(self) -> None:
        article = Article(Path("article.md"), "content/articles/article.md", "文章", "2026-07-10", "", ["AI"], "# 文章")
        document = {"type": "doc", "content": [{"type": "paragraph"}]}
        mapping = {
            "version": 1,
            "directory": {},
            "articles": {
                article.source: {
                    "note_id": "article-id",
                    "content_sha256": document_sha256(document),
                    "published": False,
                }
            },
        }
        client = FakeMowenClient()

        sync_articles(
            [article],
            mapping,
            client,
            converter=lambda _: document,
            publish=True,
        )

        self.assertEqual(client.calls, [("public", "article-id")])
        self.assertTrue(mapping["articles"][article.source]["published"])

    def test_register_mode_does_not_edit_existing_public_notes(self) -> None:
        articles = [
            Article(Path("new.md"), "content/articles/new.md", "新文章", "2026-07-10", "", ["AI"], "# 新文章"),
            Article(Path("old.md"), "content/articles/old.md", "旧文章", "2026-07-09", "", ["AI"], "# 旧文章"),
        ]
        mapping = {
            "version": 1,
            "directory": {},
            "articles": {"content/articles/old.md": {"note_id": "old-id"}},
        }
        client = FakeMowenClient()

        sync_articles(
            articles,
            mapping,
            client,
            converter=lambda article: {"type": "doc", "content": []},
            publish=False,
            update_existing=False,
        )

        self.assertEqual([call[0] for call in client.calls], ["create"])

    def test_converter_uses_body_without_frontmatter_and_reads_noteatom(self) -> None:
        article = Article(
            Path("article.md"),
            "content/articles/article.md",
            "文章标题",
            "2026-07-10",
            "摘要",
            ["AI"],
            "# 文章标题\n\n正文\n",
            sequence=4,
        )
        observed: dict[str, object] = {}

        def fake_runner(command: list[str]) -> None:
            input_path = Path(command[command.index("--input") + 1])
            cache_path = Path(command[command.index("--cache-dir") + 1])
            observed["command"] = command
            observed["input"] = input_path.read_text(encoding="utf-8")
            cache_path.mkdir(parents=True)
            (cache_path / "04-noteatom.json").write_text(
                json.dumps({"type": "doc", "content": [{"type": "paragraph"}]}),
                encoding="utf-8",
            )

        document = convert_article(article, runner=fake_runner)

        self.assertEqual(observed["input"], "# 04-文章标题\n\n正文\n")
        self.assertNotIn("title:", str(observed["input"]))
        self.assertIn("--dry-run", observed["command"])
        self.assertEqual(document["type"], "doc")

    def test_directory_is_created_privately_then_published(self) -> None:
        article = Article(Path("new.md"), "content/articles/new.md", "新文章", "2026-07-10", "", ["AI"], "# 新文章")
        mapping = {
            "version": 1,
            "directory": {},
            "articles": {"content/articles/new.md": {"note_id": "article-id"}},
        }
        client = FakeMowenClient()

        sync_directory([article], mapping, client, publish=True, cover_uuid=None)

        self.assertEqual(mapping["directory"]["note_id"], "new-note-1")
        self.assertEqual([call[0] for call in client.calls], ["create", "public"])

    def test_existing_directory_is_not_changed_during_register_mode(self) -> None:
        article = Article(Path("new.md"), "content/articles/new.md", "新文章", "2026-07-10", "", ["AI"], "# 新文章")
        mapping = {
            "version": 1,
            "directory": {"note_id": "directory-id"},
            "articles": {"content/articles/new.md": {"note_id": "article-id"}},
        }
        client = FakeMowenClient()

        sync_directory(
            [article],
            mapping,
            client,
            publish=False,
            cover_uuid=None,
            update_existing=False,
        )

        self.assertEqual(client.calls, [])

    def test_unchanged_published_directory_is_not_edited(self) -> None:
        article = Article(Path("new.md"), "content/articles/new.md", "新文章", "2026-07-10", "", ["AI"], "# 新文章")
        mapping = {
            "version": 1,
            "directory": {"note_id": "directory-id"},
            "articles": {"content/articles/new.md": {"note_id": "article-id"}},
        }
        document = build_directory_document([article], mapping)
        mapping["directory"].update(
            {"content_sha256": document_sha256(document), "published": True}
        )
        client = FakeMowenClient()

        sync_directory([article], mapping, client, publish=True, cover_uuid=None)

        self.assertEqual(client.calls, [])

    def test_cover_upload_is_reused_until_file_content_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cover = Path(tmp) / "cover.jpg"
            cover.write_bytes(b"cover-v1")
            mapping = {"directory": {}, "articles": {}}
            client = FakeMowenClient()

            first = ensure_cover_uploaded(
                cover,
                "https://example.test/cover.jpg",
                mapping,
                client,
                fetcher=lambda _: b"cover-v1",
            )
            second = ensure_cover_uploaded(
                cover,
                "https://example.test/cover.jpg",
                mapping,
                client,
                fetcher=lambda _: b"cover-v1",
            )

            self.assertEqual(first, "cover-uuid")
            self.assertEqual(second, "cover-uuid")
            self.assertEqual([call[0] for call in client.calls], ["upload"])
            self.assertEqual(mapping["directory"]["cover_source_url"], "https://example.test/cover.jpg")
            self.assertEqual(len(mapping["directory"]["cover_sha256"]), 64)

    def test_cover_upload_rejects_stale_remote_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cover = Path(tmp) / "cover.jpg"
            cover.write_bytes(b"new-cover")
            client = FakeMowenClient()

            with self.assertRaisesRegex(RuntimeError, "does not match"):
                ensure_cover_uploaded(
                    cover,
                    "https://example.test/cover.jpg",
                    {"directory": {}, "articles": {}},
                    client,
                    fetcher=lambda _: b"old-cover",
                    attempts=1,
                )

            self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
