#!/usr/bin/env python3
"""Publish ready articles and their directory note to MoWen."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTICLES_DIR = REPO_ROOT / "content" / "articles"
MAPPING_PATH = REPO_ROOT / "publishing" / "mowen-notes.json"
COVER_PATH = REPO_ROOT / "assets" / "mowen" / "ai-work-system-cover.jpg"
MOWEN_MCP_ENDPOINT = "https://open.mowen.cn/api/open/mcp/v1/note"


@dataclass(frozen=True)
class Article:
    path: Path
    source: str
    title: str
    date: str
    summary: str
    tags: list[str]
    body: str


def parse_article(path: Path, repo_root: Path) -> Article:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"Missing YAML frontmatter: {path}")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError(f"Unclosed YAML frontmatter: {path}")
    metadata = yaml.safe_load(text[4:end]) or {}
    if not isinstance(metadata, dict):
        raise ValueError(f"YAML frontmatter must be a mapping: {path}")
    tags = metadata.get("tags") or []
    if not isinstance(tags, list):
        raise ValueError(f"Frontmatter tags must be a list: {path}")
    return Article(
        path=path,
        source=str(path.relative_to(repo_root)),
        title=str(metadata.get("title") or path.stem),
        date=str(metadata.get("date") or ""),
        summary=str(metadata.get("summary") or ""),
        tags=[str(tag) for tag in tags],
        body=text[end + len("\n---\n") :].lstrip(),
    )


def discover_ready_articles(repo_root: Path = REPO_ROOT) -> list[Article]:
    articles: list[Article] = []
    for path in (repo_root / "content" / "articles").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            continue
        end = text.find("\n---\n", 4)
        if end == -1:
            continue
        metadata = yaml.safe_load(text[4:end]) or {}
        if metadata.get("status") != "ready":
            continue
        articles.append(parse_article(path, repo_root))
    return sorted(articles, key=lambda item: (item.date, item.source), reverse=True)


def text_paragraph(text: str, bold: bool = False) -> dict:
    node: dict = {"type": "text", "text": text}
    if bold:
        node["marks"] = [{"type": "bold"}]
    return {"type": "paragraph", "content": [node]}


def build_directory_document(
    articles: list[Article], mapping: dict, cover_uuid: str | None = None
) -> dict:
    content: list[dict] = [
        text_paragraph("AI 长期工作系统", bold=True),
        {"type": "paragraph"},
    ]
    if cover_uuid:
        content.extend(
            [
                {
                    "type": "image",
                    "attrs": {
                        "uuid": cover_uuid,
                        "align": "center",
                        "alt": "AI 长期工作系统",
                    },
                },
                {"type": "paragraph"},
            ]
        )
    content.extend(
        [
            text_paragraph(
                "这里记录我如何把 AI 从一次性聊天工具，逐步放进一个有记忆、有流程、有证据、有复盘的长期工作系统。"
            ),
            {"type": "paragraph"},
            text_paragraph(
                "文章按发布时间倒序排列，最新内容在最上方；第一次阅读时，也可以从最早的一篇开始。"
            ),
            {"type": "paragraph"},
            text_paragraph("文章时间线", bold=True),
            {"type": "paragraph"},
        ]
    )
    article_mapping = mapping.get("articles", {})
    for article in articles:
        entry = article_mapping.get(article.source) or {}
        note_id = entry.get("note_id")
        if not note_id:
            raise ValueError(f"Missing MoWen note mapping: {article.source}")
        content.extend(
            [
                text_paragraph(article.date, bold=True),
                {"type": "note", "attrs": {"uuid": note_id}},
                {"type": "paragraph"},
            ]
        )
    return {"type": "doc", "content": content}


def load_mapping(path: Path = MAPPING_PATH) -> dict:
    if not path.exists():
        return {"version": 1, "directory": {}, "articles": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_mapping(path: Path, mapping: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(str(temporary), str(path))


def run_converter(command: list[str]) -> None:
    result = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown converter error"
        raise RuntimeError(f"Markdown conversion failed: {detail}")


def convert_article(
    article: Article,
    runner: Callable[[list[str]], None] = run_converter,
) -> dict:
    with tempfile.TemporaryDirectory(prefix="mowen-convert-") as tmp:
        temporary = Path(tmp)
        input_path = temporary / "article.md"
        cache_path = temporary / "cache"
        input_path.write_text(article.body, encoding="utf-8")
        command = [
            "npx",
            "--no-install",
            "md-to-mowen",
            "publish",
            "--input",
            str(input_path),
            "--dry-run",
            "--cache-dir",
            str(cache_path),
            "--quiet",
        ]
        runner(command)
        output = cache_path / "04-noteatom.json"
        if not output.exists():
            raise RuntimeError("Markdown converter did not produce 04-noteatom.json")
        document = json.loads(output.read_text(encoding="utf-8"))
        if document.get("type") != "doc" or not isinstance(document.get("content"), list):
            raise RuntimeError("Markdown converter returned invalid NoteAtom JSON")
        return document


class MowenClient:
    def __init__(self, api_key: str | None = None, mcp_url: str | None = None) -> None:
        if mcp_url:
            self.url = mcp_url
        elif api_key:
            self.url = f"{MOWEN_MCP_ENDPOINT}?key={api_key}"
        else:
            raise ValueError("Set MOWEN_API_KEY or MOWEN_MCP_URL")
        self.request_id = 0

    def call(self, name: str, arguments: dict) -> str:
        self.request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"MoWen MCP request failed with HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("MoWen MCP request failed before receiving a response") from exc
        if "error" in result:
            raise RuntimeError(f"MoWen MCP error: {result['error'].get('message', 'unknown error')}")
        blocks = result.get("result", {}).get("content", [])
        if not blocks or blocks[0].get("type") != "text":
            raise RuntimeError("MoWen MCP returned no text result")
        return str(blocks[0]["text"])

    def create_rich_note(self, document: dict, tags: list[str]) -> str:
        return self.call(
            "CreateRichNote",
            {
                "body": json.dumps(document, ensure_ascii=False, separators=(",", ":")),
                "settings": json.dumps(
                    {"auto_publish": False, "tags": tags},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        )

    def edit_rich_note(self, note_id: str, document: dict) -> None:
        self.call(
            "EditRichNote",
            {
                "note_id": note_id,
                "body": json.dumps(document, ensure_ascii=False, separators=(",", ":")),
            },
        )

    def set_public(self, note_id: str) -> None:
        self.call(
            "ChangeNoteSettings",
            {
                "note_id": note_id,
                "section": 1,
                "settings": json.dumps(
                    {"privacy": {"type": "public"}}, separators=(",", ":")
                ),
            },
        )

    def upload_via_url(self, url: str, file_name: str) -> str:
        return self.call(
            "UploadViaURL",
            {"file_type": 1, "url": url, "file_name": file_name},
        )


def ensure_cover_uploaded(
    cover_path: Path,
    cover_url: str,
    mapping: dict,
    client: MowenClient,
) -> str:
    if not cover_path.exists():
        raise ValueError(f"Cover file does not exist: {cover_path}")
    if not cover_url.startswith("https://"):
        raise ValueError("Cover URL must use HTTPS")
    digest = hashlib.sha256(cover_path.read_bytes()).hexdigest()
    directory = mapping.setdefault("directory", {})
    if (
        directory.get("cover_uuid")
        and directory.get("cover_sha256") == digest
        and directory.get("cover_source_url") == cover_url
    ):
        return str(directory["cover_uuid"])
    uuid = client.upload_via_url(cover_url, cover_path.name)
    directory.update(
        {
            "cover_uuid": uuid,
            "cover_sha256": digest,
            "cover_source_url": cover_url,
        }
    )
    return uuid


def sync_articles(
    articles: list[Article],
    mapping: dict,
    client: MowenClient,
    converter: Callable[[Article], dict],
    publish: bool,
    update_existing: bool = True,
) -> None:
    article_mapping = mapping.setdefault("articles", {})
    for article in articles:
        entry = article_mapping.get(article.source)
        if entry and entry.get("note_id") and not update_existing:
            continue
        document = converter(article)
        if entry and entry.get("note_id"):
            note_id = str(entry["note_id"])
            client.edit_rich_note(note_id, document)
        else:
            note_id = client.create_rich_note(document, article.tags)
            article_mapping[article.source] = {
                "note_id": note_id,
                "url": f"https://note.mowen.cn/detail/{note_id}",
            }
        if publish:
            client.set_public(note_id)


def sync_directory(
    articles: list[Article],
    mapping: dict,
    client: MowenClient,
    publish: bool,
    cover_uuid: str | None,
    update_existing: bool = True,
) -> None:
    directory = mapping.setdefault("directory", {})
    note_id = directory.get("note_id")
    if note_id and not update_existing:
        return
    document = build_directory_document(articles, mapping, cover_uuid=cover_uuid)
    if note_id:
        client.edit_rich_note(str(note_id), document)
    else:
        note_id = client.create_rich_note(
            document,
            ["AI Work System", "长期 AI 协作"],
        )
        directory.update(
            {
                "note_id": note_id,
                "url": f"https://note.mowen.cn/detail/{note_id}",
            }
        )
    if publish:
        client.set_public(str(note_id))


def validate_conversions(articles: list[Article]) -> None:
    for article in articles:
        document = convert_article(article)
        block_count = len(document["content"])
        print(f"OK {article.source}: {block_count} NoteAtom blocks")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync ready articles and their directory to MoWen."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--register-private",
        action="store_true",
        help="Create only missing notes as private drafts and persist their IDs.",
    )
    mode.add_argument(
        "--publish",
        action="store_true",
        help="Create or update all ready notes, publish them, then publish the directory.",
    )
    parser.add_argument("--mapping", type=Path, default=MAPPING_PATH)
    parser.add_argument("--cover-path", type=Path, default=COVER_PATH)
    parser.add_argument(
        "--cover-url",
        help="Public HTTPS URL for the repository-managed directory cover.",
    )
    args = parser.parse_args()

    articles = discover_ready_articles()
    validate_conversions(articles)
    if not args.register_private and not args.publish:
        print(f"Dry run complete: {len(articles)} ready article(s).")
        return 0

    client = MowenClient(
        api_key=os.environ.get("MOWEN_API_KEY"),
        mcp_url=os.environ.get("MOWEN_MCP_URL"),
    )
    mapping = load_mapping(args.mapping)
    update_existing = args.publish
    for article in articles:
        sync_articles(
            [article],
            mapping,
            client,
            converter=convert_article,
            publish=args.publish,
            update_existing=update_existing,
        )
        save_mapping(args.mapping, mapping)
    cover_uuid = mapping.get("directory", {}).get("cover_uuid")
    if args.cover_url:
        cover_uuid = ensure_cover_uploaded(
            args.cover_path,
            args.cover_url,
            mapping,
            client,
        )
        save_mapping(args.mapping, mapping)
    sync_directory(
        articles,
        mapping,
        client,
        publish=args.publish,
        cover_uuid=cover_uuid,
        update_existing=update_existing,
    )
    save_mapping(args.mapping, mapping)
    action = "Published" if args.publish else "Registered privately"
    print(f"{action}: {len(articles)} article(s) and directory mapping.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
