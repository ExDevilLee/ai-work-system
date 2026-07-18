from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import sync_mowen
from scripts.sync_mowen import (
    Article,
    MowenClient,
    build_numbered_article_body,
    build_directory_document,
    convert_article,
    discover_ready_articles,
    directory_mapping,
    document_sha256,
    ensure_cover_uploaded,
    ensure_article_images_uploaded,
    load_mapping,
    replace_document_image_uuids,
    rewrite_article_asset_urls,
    rewrite_markdown_tables_as_lists,
    save_mapping,
    split_articles_by_mapping,
    sync_articles,
    sync_directory,
    wait_for_remote_asset,
)


def article_text(
    title: str,
    date: str,
    status: str = "ready",
    series: str = "series-one",
) -> str:
    return f"""---
title: {title}
date: {date}
status: {status}
series: {series}
summary: {title}摘要
tags:
  - AI Work System
---

# {title}

正文
"""


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
                        "description": "第一组介绍",
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
                        "description": "第二组介绍",
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
    def test_created_note_id_is_checkpointed_before_publication_failure(self) -> None:
        article = Article(
            Path("article.md"),
            "content/articles/article.md",
            "文章",
            "2026-07-10",
            "",
            ["AI"],
            "# 文章",
        )
        mapping = {"version": 2, "directories": {}, "articles": {}}
        snapshots: list[dict] = []

        class FailingPublicClient(FakeMowenClient):
            def set_public(self, note_id: str) -> None:
                raise RuntimeError("network failed while publishing")

        with self.assertRaisesRegex(RuntimeError, "network failed"):
            sync_articles(
                [article],
                mapping,
                FailingPublicClient(),
                converter=lambda _: {"type": "doc", "content": []},
                publish=True,
                checkpoint=lambda: snapshots.append(
                    json.loads(json.dumps(mapping))
                ),
            )

        self.assertEqual(
            snapshots[-1]["articles"][article.source]["note_id"],
            "new-note-1",
        )

    def test_risky_publication_is_recorded_without_recreating_note(self) -> None:
        article = Article(
            Path("article.md"),
            "content/articles/article.md",
            "文章",
            "2026-07-10",
            "",
            ["AI"],
            "# 文章",
        )
        mapping = {"version": 2, "directories": {}, "articles": {}}

        class RiskyPublicClient(FakeMowenClient):
            def set_public(self, note_id: str) -> None:
                self.calls.append(("public", note_id))
                raise RuntimeError("MoWen MCP error: code = 403 reason = RISKY")

        first_client = RiskyPublicClient()
        sync_articles(
            [article],
            mapping,
            first_client,
            converter=lambda _: {"type": "doc", "content": []},
            publish=True,
            checkpoint=lambda: None,
        )
        second_client = RiskyPublicClient()
        with mock.patch("builtins.print") as printer:
            sync_articles(
                [article],
                mapping,
                second_client,
                converter=lambda _: {"type": "doc", "content": []},
                publish=True,
                checkpoint=lambda: None,
            )

        entry = mapping["articles"][article.source]
        self.assertEqual(entry["note_id"], "new-note-1")
        self.assertFalse(entry["published"])
        self.assertEqual(entry["publication_blocked"]["reason"], "RISKY")
        self.assertEqual([call[0] for call in first_client.calls], ["create", "public"])
        self.assertEqual(second_client.calls, [])
        self.assertIn(entry["url"], str(printer.call_args))

    def test_directory_uses_only_published_articles(self) -> None:
        published = Article(
            Path("published.md"),
            "content/articles/published.md",
            "已发布",
            "2026-07-09",
            "",
            ["AI"],
            "# 已发布",
        )
        private = Article(
            Path("private.md"),
            "content/articles/private.md",
            "私密",
            "2026-07-10",
            "",
            ["AI"],
            "# 私密",
        )
        mapping = {
            "articles": {
                published.source: {"note_id": "published-id", "published": True},
                private.source: {"note_id": "private-id", "published": False},
            }
        }

        selected = sync_mowen.published_articles_for_directory(
            [private, published],
            mapping,
        )

        self.assertEqual(selected, [published])

    def test_load_mapping_migrates_legacy_directory_without_losing_fields(self) -> None:
        legacy_directory = {
            "note_id": "directory-id",
            "url": "https://example.test/directory-id",
            "cover_uuid": "cover-id",
            "cover_sha256": "cover-digest",
            "content_sha256": "content-digest",
            "published": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mowen-notes.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "directory": legacy_directory,
                        "articles": {},
                    }
                ),
                encoding="utf-8",
            )

            mapping = load_mapping(path)

            self.assertEqual(mapping["version"], 2)
            self.assertNotIn("directory", mapping)
            self.assertEqual(
                mapping["directories"]["long-term-ai-work-system"],
                legacy_directory,
            )

    def test_directory_mapping_keeps_series_state_separate(self) -> None:
        mapping = {"version": 2, "directories": {}, "articles": {}}

        first = directory_mapping(mapping, "series-one")
        second = directory_mapping(mapping, "series-two")
        first["note_id"] = "first-directory"

        self.assertEqual(second, {})
        self.assertNotIn("note_id", second)

    @mock.patch("scripts.sync_mowen.urllib.request.urlopen")
    def test_client_logs_successful_call_count_without_quota_limit(self, urlopen: mock.Mock) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {"result": {"content": [{"type": "text", "text": "note-id"}]}}
        ).encode("utf-8")
        urlopen.return_value = response
        client = MowenClient(api_key="test-key")

        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            result = client.call("CreateRichNote", {})

        self.assertEqual(result, "note-id")
        self.assertEqual(client.attempted_calls, 1)
        self.assertEqual(client.successful_calls, 1)
        self.assertIn("run_successful=1", stdout.getvalue())
        self.assertIn("remaining quota is determined by the server", stdout.getvalue())
        self.assertNotRegex(stdout.getvalue(), r"\b\d+/\d+\b")

    @mock.patch("scripts.sync_mowen.urllib.request.urlopen")
    def test_client_logs_explicit_quota_exhaustion(self, urlopen: mock.Mock) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {
                "error": {
                    "message": "error: code = 403 reason = QUOTA quota exceed"
                }
            }
        ).encode("utf-8")
        urlopen.return_value = response
        client = MowenClient(api_key="test-key")

        with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            with self.assertRaisesRegex(RuntimeError, "quota exceed"):
                client.call("EditRichNote", {})

        self.assertEqual(client.attempted_calls, 1)
        self.assertEqual(client.successful_calls, 0)
        self.assertIn("server quota exhausted", stderr.getvalue())
        self.assertNotIn("remaining", stderr.getvalue())

    def test_unmapped_articles_are_prioritized_before_existing_updates(self) -> None:
        new = Article(Path("new.md"), "content/articles/new.md", "新文章", "2026-07-12", "", ["AI"], "# 新文章")
        old = Article(Path("old.md"), "content/articles/old.md", "旧文章", "2026-07-11", "", ["AI"], "# 旧文章")
        mapping = {
            "articles": {
                old.source: {"note_id": "old-id", "published": True},
            }
        }

        missing, existing = split_articles_by_mapping([new, old], mapping)

        self.assertEqual(missing, [new])
        self.assertEqual(existing, [old])

    def test_relative_article_assets_are_rewritten_for_mowen(self) -> None:
        markdown = "![结构图](images/04/memory.png)"

        rewritten = rewrite_article_asset_urls(
            markdown,
            article_source_dir="content/articles/series-one",
        )

        self.assertEqual(
            rewritten,
            "![结构图](https://gitee.com/ExDevilLee/ai-work-system/raw/main/content/articles/series-one/images/04/memory.png)",
        )

    def test_rewrite_markdown_tables_as_lists_preserves_table_data(self) -> None:
        markdown = """实验结果：

| 任务 | Baseline | Layered | 减少比例 |
| --- | ---: | ---: | ---: |
| 恢复当前任务 | 3,628 B | 575 B | 84.2% |
| 识别稳定规则 | 3,628 B | 1,595 B | 56.0% |

后续说明。
"""

        rewritten = rewrite_markdown_tables_as_lists(markdown)

        self.assertNotIn("| ---", rewritten)
        self.assertIn(
            "- 任务：恢复当前任务；Baseline：3,628 B；Layered：575 B；减少比例：84.2%",
            rewritten,
        )
        self.assertIn(
            "- 任务：识别稳定规则；Baseline：3,628 B；Layered：1,595 B；减少比例：56.0%",
            rewritten,
        )
        self.assertIn("后续说明。", rewritten)

    def test_article_images_are_uploaded_cached_and_applied_to_document(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            article_path = Path(tmp) / "content" / "articles" / "series-one" / "article.md"
            image_path = article_path.parent / "images" / "04" / "memory.png"
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(b"article-image")
            article = Article(
                article_path,
                "content/articles/series-one/article.md",
                "文章",
                "2026-07-11",
                "",
                ["AI"],
                "# 文章\n\n![结构图](images/04/memory.png)\n",
                series="series-one",
            )
            mapping = {"version": 1, "directory": {}, "articles": {}}
            client = FakeMowenClient()

            first = ensure_article_images_uploaded(
                article,
                mapping,
                client,
                fetcher=lambda _: b"article-image",
                attempts=1,
            )
            second = ensure_article_images_uploaded(
                article,
                mapping,
                client,
                fetcher=lambda _: b"stale-image",
                attempts=1,
            )
            document = {
                "type": "doc",
                "content": [{"type": "image", "attrs": {"uuid": "dry-run"}}],
            }
            replace_document_image_uuids(document, first)

            self.assertEqual(first, ["cover-uuid"])
            self.assertEqual(second, ["cover-uuid"])
            self.assertEqual(document["content"][0]["attrs"]["uuid"], "cover-uuid")
            self.assertEqual(
                [call[0] for call in client.calls],
                ["upload"],
            )

    def test_moved_image_reuses_cached_uuid_by_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            article_path = Path(tmp) / "content" / "articles" / "series-one" / "article.md"
            image_path = article_path.parent / "images" / "04" / "memory.png"
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(b"article-image")
            article = Article(
                article_path,
                "content/articles/series-one/article.md",
                "文章",
                "2026-07-11",
                "",
                ["AI"],
                "# 文章\n\n![结构图](images/04/memory.png)\n",
                series="series-one",
            )
            digest = hashlib.sha256(b"article-image").hexdigest()
            mapping = {
                "version": 1,
                "articles": {
                    article.source: {
                        "assets": {
                            "series-one/images/04/memory.png": {
                                "uuid": "existing-uuid",
                                "sha256": digest,
                                "source_url": "https://example.test/old.png",
                            }
                        }
                    }
                },
            }
            client = FakeMowenClient()

            uuids = ensure_article_images_uploaded(
                article,
                mapping,
                client,
                fetcher=lambda _: b"stale-image",
                attempts=1,
            )

            assets = mapping["articles"][article.source]["assets"]
            self.assertEqual(uuids, ["existing-uuid"])
            self.assertNotIn("series-one/images/04/memory.png", assets)
            self.assertEqual(
                assets["images/04/memory.png"]["uuid"],
                "existing-uuid",
            )
            self.assertEqual(client.calls, [])

    @mock.patch("scripts.sync_mowen.time.sleep")
    def test_remote_asset_retries_404_then_succeeds(self, sleep: mock.Mock) -> None:
        responses: list[bytes | RuntimeError] = [
            RuntimeError("Asset download failed with HTTP 404"),
            RuntimeError("Asset download failed with HTTP 404"),
            b"current-image",
        ]

        def fetch(_: str) -> bytes:
            response = responses.pop(0)
            if isinstance(response, RuntimeError):
                raise response
            return response

        wait_for_remote_asset(
            "https://example.test/image.png",
            hashlib.sha256(b"current-image").hexdigest(),
            fetch,
            attempts=6,
            mismatch_message="Remote image does not match",
        )

        self.assertEqual(sleep.call_count, 2)

    @mock.patch("scripts.sync_mowen.time.sleep")
    def test_remote_asset_does_not_retry_non_404_errors(self, sleep: mock.Mock) -> None:
        with self.assertRaisesRegex(RuntimeError, "HTTP 500"):
            wait_for_remote_asset(
                "https://example.test/image.png",
                "unused",
                lambda _: (_ for _ in ()).throw(
                    RuntimeError("Asset download failed with HTTP 500")
                ),
                attempts=6,
                mismatch_message="Remote image does not match",
            )

        sleep.assert_not_called()

    def test_document_image_count_must_match_uploaded_images(self) -> None:
        document = {
            "type": "doc",
            "content": [{"type": "image", "attrs": {"uuid": "dry-run"}}],
        }

        with self.assertRaisesRegex(ValueError, "image count"):
            replace_document_image_uuids(document, [])

    def test_discovers_only_ready_articles_in_reverse_chronological_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_series_catalog(root)
            articles_dir = root / "content" / "articles" / "series-one"
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
            self.assertEqual(
                articles[0].source,
                "content/articles/series-one/2026-07-10-zulu.md",
            )
            self.assertEqual([item.sequence for item in articles], [3, 2, 1])

    def test_discovery_resets_sequence_for_each_series(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_series_catalog(root)
            articles_dir = root / "content" / "articles"
            series_one_dir = articles_dir / "series-one"
            series_two_dir = articles_dir / "series-two"
            series_one_dir.mkdir(parents=True, exist_ok=True)
            series_two_dir.mkdir(parents=True, exist_ok=True)
            (series_one_dir / "2026-07-01-one.md").write_text(
                article_text("一之一", "2026-07-01", series="series-one"),
                encoding="utf-8",
            )
            (series_one_dir / "2026-07-02-two.md").write_text(
                article_text("一之二", "2026-07-02", series="series-one"),
                encoding="utf-8",
            )
            (series_two_dir / "2026-07-03-three.md").write_text(
                article_text("二之一", "2026-07-03", series="series-two"),
                encoding="utf-8",
            )

            articles = discover_ready_articles(root)

            self.assertEqual(
                [(item.title, item.series, item.sequence) for item in articles],
                [("二之一", "series-two", 1), ("一之二", "series-one", 2), ("一之一", "series-one", 1)],
            )

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
            [node["text"] for node in document["content"][4]["content"]],
            [
                "这里记录我如何把 AI 从一次性聊天工具，逐步放进一个有记忆、有流程、有证据、有复盘的长期工作系统。",
                "文章按发布时间倒序排列，最新内容在最上方；第一次阅读时，也可以从最早的一篇开始。",
            ],
        )
        self.assertEqual(
            document["content"][-2]["content"][0],
            {"type": "text", "text": "首发地址："},
        )

    def test_directory_document_uses_selected_series_title_and_introduction(self) -> None:
        article = Article(
            Path("article.md"),
            "content/articles/article.md",
            "文章",
            "2026-07-10",
            "摘要",
            ["AI"],
            "# 文章",
            series="series-two",
        )
        mapping = {"articles": {article.source: {"note_id": "article-id"}}}

        document = build_directory_document(
            [article],
            mapping,
            title="系列二目录",
            introduction="第二组介绍",
        )

        texts = [
            node.get("text")
            for atom in document["content"]
            for node in atom.get("content", [])
            if node.get("type") == "text"
        ]
        self.assertEqual(texts[0], "系列二目录")
        self.assertIn("第二组介绍", texts)
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
            expected = {
                "version": 2,
                "directories": {
                    "long-term-ai-work-system": {"note_id": "directory-id"}
                },
                "articles": {},
            }

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

    def test_sync_edits_changed_published_article_without_republishing(self) -> None:
        article = Article(Path("article.md"), "content/articles/article.md", "文章", "2026-07-10", "", ["AI"], "# 文章")
        document = {"type": "doc", "content": [{"type": "paragraph"}]}
        mapping = {
            "version": 1,
            "directory": {},
            "articles": {
                article.source: {
                    "note_id": "article-id",
                    "content_sha256": "old-digest",
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

        self.assertEqual([call[0] for call in client.calls], ["edit"])

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

    def test_missing_series_directory_is_created_during_publish(self) -> None:
        article = Article(
            Path("new.md"),
            "content/articles/series-two/new.md",
            "新文章",
            "2026-07-10",
            "",
            ["AI"],
            "# 新文章",
            series="series-two",
        )
        mapping = {
            "version": 2,
            "directories": {"series-one": {"note_id": "first-directory"}},
            "articles": {article.source: {"note_id": "article-id"}},
        }
        client = FakeMowenClient()

        sync_directory(
            [article],
            mapping,
            client,
            publish=True,
            cover_uuid=None,
            series_id="series-two",
            title="系列二目录",
        )

        self.assertEqual(
            mapping["directories"]["series-two"]["note_id"],
            "new-note-1",
        )
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

    def test_changed_published_directory_is_edited_without_republishing(self) -> None:
        article = Article(Path("new.md"), "content/articles/new.md", "新文章", "2026-07-10", "", ["AI"], "# 新文章")
        mapping = {
            "version": 1,
            "directory": {
                "note_id": "directory-id",
                "content_sha256": "old-digest",
                "published": True,
            },
            "articles": {"content/articles/new.md": {"note_id": "article-id"}},
        }
        client = FakeMowenClient()

        sync_directory([article], mapping, client, publish=True, cover_uuid=None)

        self.assertEqual([call[0] for call in client.calls], ["edit"])

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
