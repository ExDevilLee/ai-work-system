#!/usr/bin/env python3
"""Publish ready articles and their directory note to MoWen."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

import yaml

try:
    from scripts.series_catalog import load_series_catalog
except ModuleNotFoundError:
    from series_catalog import load_series_catalog


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTICLES_DIR = REPO_ROOT / "content" / "articles"
MAPPING_PATH = REPO_ROOT / "publishing" / "mowen-notes.json"
COVER_PATH = REPO_ROOT / "assets" / "mowen" / "ai-work-system-cover.jpg"
MOWEN_MCP_ENDPOINT = "https://open.mowen.cn/api/open/mcp/v1/note"
ARTICLE_ASSET_BASE_URL = "https://gitee.com/ExDevilLee/ai-work-system/raw/main"
MOWEN_FREE_DAILY_QUOTA = 10
FIRST_SERIES_ID = "long-term-ai-work-system"
DEFAULT_DIRECTORY_INTRODUCTION = (
    "这里记录我如何把 AI 从一次性聊天工具，逐步放进一个有记忆、有流程、有证据、有复盘的长期工作系统。",
    "文章按发布时间倒序排列，最新内容在最上方；第一次阅读时，也可以从最早的一篇开始。",
)


@dataclass(frozen=True)
class Article:
    path: Path
    source: str
    title: str
    date: str
    summary: str
    tags: list[str]
    body: str
    sequence: int | None = None
    series: str = FIRST_SERIES_ID


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
        series=str(metadata.get("series") or ""),
    )


def discover_ready_articles(repo_root: Path = REPO_ROOT) -> list[Article]:
    catalog = load_series_catalog(repo_root)
    known_series = {entry["id"] for entry in catalog}
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
        article = parse_article(path, repo_root)
        if article.series not in known_series:
            raise ValueError(f"Unknown article series '{article.series}' in {path.name}")
        articles.append(article)
    ordered = sorted(articles, key=lambda item: (item.date, item.source), reverse=True)
    series_counts: dict[str, int] = {}
    sequence_by_source: dict[str, int] = {}
    for article in reversed(ordered):
        series_counts[article.series] = series_counts.get(article.series, 0) + 1
        sequence_by_source[article.source] = series_counts[article.series]
    return [
        replace(article, sequence=sequence_by_source[article.source])
        for article in ordered
    ]


def build_numbered_article_body(article: Article) -> str:
    if article.sequence is None:
        raise ValueError(f"Missing MoWen article sequence: {article.source}")
    numbered_title = f"{article.sequence:02d}-{article.title}"
    lines = article.body.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith("# "):
            newline = "\n" if line.endswith("\n") else ""
            lines[index] = f"# {numbered_title}{newline}"
            return "".join(lines)
    return f"# {numbered_title}\n\n{article.body}"


def rewrite_article_asset_urls(
    markdown: str,
    asset_base_url: str = ARTICLE_ASSET_BASE_URL,
) -> str:
    pattern = re.compile(
        r"(?P<prefix>\]\()(?P<path>(?:(?:\.\./)+assets/|images/)[^)\s]+)"
    )

    def replace(match: re.Match[str]) -> str:
        path = match.group("path")
        asset_path = (
            f"content/articles/{path}"
            if path.startswith("images/")
            else path[path.index("assets/") :]
        )
        return f"{match.group('prefix')}{asset_base_url.rstrip('/')}/{asset_path}"

    return pattern.sub(replace, markdown)


def discover_article_images(article: Article) -> list[tuple[str, Path, str]]:
    pattern = re.compile(r"!\[[^\]]*\]\((?P<path>images/[^)\s]+)\)")
    images: list[tuple[str, Path, str]] = []
    for match in pattern.finditer(article.body):
        relative_path = match.group("path")
        local_path = article.path.parent / relative_path
        public_path = (Path(article.source).parent / relative_path).as_posix()
        public_url = f"{ARTICLE_ASSET_BASE_URL}/{public_path}"
        images.append((relative_path, local_path, public_url))
    return images


def replace_document_image_uuids(document: dict, image_uuids: list[str]) -> None:
    image_nodes: list[dict] = []

    def walk(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "image":
                image_nodes.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(document)
    if len(image_nodes) != len(image_uuids):
        raise ValueError(
            "Converted image count does not match uploaded article image count"
        )
    for node, uuid in zip(image_nodes, image_uuids):
        node.setdefault("attrs", {})["uuid"] = uuid


def text_paragraph(text: str, bold: bool = False) -> dict:
    node: dict = {"type": "text", "text": text}
    if bold:
        node["marks"] = [{"type": "bold"}]
    return {"type": "paragraph", "content": [node]}


def text_paragraph_from_parts(parts: list[str]) -> dict:
    return {
        "type": "paragraph",
        "content": [{"type": "text", "text": part} for part in parts],
    }


def link_paragraph(label: str, url: str) -> dict:
    content: list[dict] = []
    if label:
        content.append({"type": "text", "text": label})
    content.append(
        {
            "type": "text",
            "text": url,
            "marks": [{"type": "link", "attrs": {"href": url}}],
        }
    )
    return {
        "type": "paragraph",
        "content": content,
    }


def build_directory_document(
    articles: list[Article],
    mapping: dict,
    cover_uuid: str | None = None,
    title: str = "AI 长期工作系统",
    introduction: str | list[str] | tuple[str, ...] = DEFAULT_DIRECTORY_INTRODUCTION,
) -> dict:
    content: list[dict] = [
        text_paragraph(title, bold=True),
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
                        "alt": title,
                    },
                },
                {"type": "paragraph"},
            ]
        )
    content.extend(
        [
            text_paragraph_from_parts(
                [introduction] if isinstance(introduction, str) else list(introduction)
            ),
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
                {"type": "note", "attrs": {"uuid": note_id}},
                {"type": "paragraph"},
            ]
        )
    content.extend(
        [
            text_paragraph("首发地址："),
            link_paragraph("", "https://github.com/ExDevilLee/ai-work-system/wiki"),
        ]
    )
    return {"type": "doc", "content": content}


def load_mapping(path: Path = MAPPING_PATH) -> dict:
    if not path.exists():
        return {"version": 2, "directories": {}, "articles": {}}
    mapping = json.loads(path.read_text(encoding="utf-8"))
    if mapping.get("version") == 1 or "directory" in mapping:
        legacy_directory = mapping.pop("directory", {})
        directories = mapping.setdefault("directories", {})
        directories.setdefault(FIRST_SERIES_ID, legacy_directory)
        mapping["version"] = 2
    else:
        mapping.setdefault("directories", {})
        mapping.setdefault("articles", {})
    return mapping


def directory_mapping(mapping: dict, series_id: str) -> dict:
    directories = mapping.get("directories")
    if isinstance(directories, dict):
        return directories.setdefault(series_id, {})
    if series_id == FIRST_SERIES_ID and "directory" in mapping:
        return mapping.setdefault("directory", {})
    mapping["version"] = 2
    return mapping.setdefault("directories", {}).setdefault(series_id, {})


def validate_registered_directories(
    articles_by_series: dict[str, list[Article]],
    mapping: dict,
) -> None:
    missing = [
        series_id
        for series_id in articles_by_series
        if not directory_mapping(mapping, series_id).get("note_id")
    ]
    if missing:
        raise ValueError(
            "Register MoWen directory note IDs before publishing: "
            + ", ".join(sorted(missing))
        )


def save_mapping(path: Path, mapping: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(str(temporary), str(path))


def document_sha256(document: dict) -> str:
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
        converted_body = rewrite_article_asset_urls(
            build_numbered_article_body(article)
        )
        input_path.write_text(converted_body, encoding="utf-8")
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
        self.attempted_calls = 0
        self.successful_calls = 0

    def log_successful_call(self, name: str) -> None:
        self.successful_calls += 1
        estimated_remaining = max(
            MOWEN_FREE_DAILY_QUOTA - self.successful_calls,
            0,
        )
        print(
            f"MoWen API call succeeded: api={name}, "
            f"run_successful={self.successful_calls}, "
            f"estimated free quota remaining: at most "
            f"{estimated_remaining}/{MOWEN_FREE_DAILY_QUOTA}."
        )
        print("Quota estimate excludes calls made outside this run.")

    def call(self, name: str, arguments: dict) -> str:
        self.request_id += 1
        self.attempted_calls += 1
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
            message = str(result["error"].get("message", "unknown error"))
            if "QUOTA" in message.upper() or "quota exceed" in message.lower():
                print(
                    f"MoWen server quota exhausted: api={name}, "
                    f"run_attempted={self.attempted_calls}, "
                    f"run_successful={self.successful_calls}.",
                    file=sys.stderr,
                )
            raise RuntimeError(f"MoWen MCP error: {message}")
        blocks = result.get("result", {}).get("content", [])
        if not blocks or blocks[0].get("type") != "text":
            raise RuntimeError("MoWen MCP returned no text result")
        self.log_successful_call(name)
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
    fetcher: Callable[[str], bytes] | None = None,
    attempts: int = 6,
    series_id: str = FIRST_SERIES_ID,
) -> str:
    if not cover_path.exists():
        raise ValueError(f"Cover file does not exist: {cover_path}")
    if not cover_url.startswith("https://"):
        raise ValueError("Cover URL must use HTTPS")
    digest = hashlib.sha256(cover_path.read_bytes()).hexdigest()
    directory = directory_mapping(mapping, series_id)
    if (
        directory.get("cover_uuid")
        and directory.get("cover_sha256") == digest
        and directory.get("cover_source_url") == cover_url
    ):
        return str(directory["cover_uuid"])
    fetch = fetcher or download_url
    wait_for_remote_asset(
        cover_url,
        digest,
        fetch,
        attempts,
        "Remote cover content does not match the repository asset",
    )
    uuid = client.upload_via_url(cover_url, cover_path.name)
    directory.update(
        {
            "cover_uuid": uuid,
            "cover_sha256": digest,
            "cover_source_url": cover_url,
        }
    )
    return uuid


def ensure_article_images_uploaded(
    article: Article,
    mapping: dict,
    client: MowenClient,
    fetcher: Callable[[str], bytes] | None = None,
    attempts: int = 6,
) -> list[str]:
    entry = mapping.setdefault("articles", {}).setdefault(article.source, {})
    asset_mapping = entry.setdefault("assets", {})
    fetch = fetcher or download_url
    image_uuids: list[str] = []

    for relative_path, local_path, public_url in discover_article_images(article):
        if not local_path.exists():
            raise ValueError(f"Article image does not exist: {local_path}")
        digest = hashlib.sha256(local_path.read_bytes()).hexdigest()
        cached = asset_mapping.get(relative_path, {})
        if (
            cached.get("uuid")
            and cached.get("sha256") == digest
            and cached.get("source_url") == public_url
        ):
            image_uuids.append(str(cached["uuid"]))
            continue

        wait_for_remote_asset(
            public_url,
            digest,
            fetch,
            attempts,
            "Remote article image does not match the repository asset",
        )

        uuid = client.upload_via_url(public_url, local_path.name)
        asset_mapping[relative_path] = {
            "uuid": uuid,
            "sha256": digest,
            "source_url": public_url,
        }
        image_uuids.append(uuid)

    return image_uuids


def wait_for_remote_asset(
    url: str,
    expected_digest: str,
    fetcher: Callable[[str], bytes],
    attempts: int,
    mismatch_message: str,
) -> None:
    for attempt in range(attempts):
        try:
            remote_digest = hashlib.sha256(fetcher(url)).hexdigest()
        except RuntimeError as exc:
            if "HTTP 404" not in str(exc) or attempt + 1 == attempts:
                raise
        else:
            if remote_digest == expected_digest:
                return
            if attempt + 1 == attempts:
                raise RuntimeError(mismatch_message)
        time.sleep(10)
    raise RuntimeError(mismatch_message)


def download_url(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ai-work-system-mowen-sync/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Asset download failed with HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Asset download failed before receiving a response") from exc


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
        digest = document_sha256(document)
        if entry and entry.get("note_id") and entry.get("content_sha256") == digest:
            if publish and not entry.get("published"):
                client.set_public(str(entry["note_id"]))
                entry["published"] = True
            continue
        if entry and entry.get("note_id"):
            note_id = str(entry["note_id"])
            client.edit_rich_note(note_id, document)
            entry["content_sha256"] = digest
        else:
            note_id = client.create_rich_note(document, article.tags)
            entry = article_mapping.setdefault(article.source, {})
            entry.update(
                {
                    "note_id": note_id,
                    "url": f"https://note.mowen.cn/detail/{note_id}",
                    "content_sha256": digest,
                    "published": False,
                }
            )
        if publish and not entry.get("published"):
            client.set_public(note_id)
            entry["published"] = True


def sync_directory(
    articles: list[Article],
    mapping: dict,
    client: MowenClient,
    publish: bool,
    cover_uuid: str | None,
    update_existing: bool = True,
    series_id: str = FIRST_SERIES_ID,
    title: str = "AI 长期工作系统",
    introduction: str | list[str] | tuple[str, ...] = DEFAULT_DIRECTORY_INTRODUCTION,
) -> None:
    directory = directory_mapping(mapping, series_id)
    note_id = directory.get("note_id")
    if note_id and not update_existing:
        return
    document = build_directory_document(
        articles,
        mapping,
        cover_uuid=cover_uuid,
        title=title,
        introduction=introduction,
    )
    digest = document_sha256(document)
    if note_id and directory.get("content_sha256") == digest:
        if publish and not directory.get("published"):
            client.set_public(str(note_id))
            directory["published"] = True
        return
    if note_id:
        client.edit_rich_note(str(note_id), document)
        directory["content_sha256"] = digest
    else:
        note_id = client.create_rich_note(
            document,
            ["AI Work System", "长期 AI 协作"],
        )
        directory.update(
            {
                "note_id": note_id,
                "url": f"https://note.mowen.cn/detail/{note_id}",
                "content_sha256": digest,
                "published": False,
            }
        )
    if publish and not directory.get("published"):
        client.set_public(str(note_id))
        directory["published"] = True


def split_articles_by_mapping(
    articles: list[Article],
    mapping: dict,
) -> tuple[list[Article], list[Article]]:
    article_mapping = mapping.get("articles", {})
    missing: list[Article] = []
    existing: list[Article] = []
    for article in articles:
        entry = article_mapping.get(article.source) or {}
        target = existing if entry.get("note_id") else missing
        target.append(article)
    return missing, existing


def sync_article_batch(
    articles: list[Article],
    mapping: dict,
    mapping_path: Path,
    client: MowenClient,
    publish: bool,
    update_existing: bool,
) -> None:
    for article in articles:
        document = convert_article(article)
        image_uuids = ensure_article_images_uploaded(
            article,
            mapping,
            client,
        )
        replace_document_image_uuids(document, image_uuids)
        save_mapping(mapping_path, mapping)
        sync_articles(
            [article],
            mapping,
            client,
            converter=lambda _article, prepared=document: prepared,
            publish=publish,
            update_existing=update_existing,
        )
        save_mapping(mapping_path, mapping)


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
    catalog = load_series_catalog(REPO_ROOT)
    catalog_by_id = {entry["id"]: entry for entry in catalog}
    articles_by_series: dict[str, list[Article]] = {}
    for article in articles:
        articles_by_series.setdefault(article.series, []).append(article)
    validate_conversions(articles)
    if not args.register_private and not args.publish:
        print(f"Dry run complete: {len(articles)} ready article(s).")
        return 0

    client = MowenClient(
        api_key=os.environ.get("MOWEN_API_KEY"),
        mcp_url=os.environ.get("MOWEN_MCP_URL"),
    )
    mapping = load_mapping(args.mapping)
    validate_registered_directories(articles_by_series, mapping)
    update_existing = args.publish
    missing_articles, existing_articles = split_articles_by_mapping(articles, mapping)
    sync_article_batch(
        missing_articles,
        mapping,
        args.mapping,
        client,
        publish=args.publish,
        update_existing=update_existing,
    )
    first_directory = directory_mapping(mapping, FIRST_SERIES_ID)
    cover_uuid = first_directory.get("cover_uuid")
    if args.cover_url:
        cover_uuid = ensure_cover_uploaded(
            args.cover_path,
            args.cover_url,
            mapping,
            client,
        )
        save_mapping(args.mapping, mapping)
    missing_series = {article.series for article in missing_articles}
    for series_id in missing_series:
        series = catalog_by_id[series_id]
        sync_directory(
            articles_by_series[series_id],
            mapping,
            client,
            publish=args.publish,
            cover_uuid=cover_uuid if series_id == FIRST_SERIES_ID else None,
            update_existing=update_existing,
            series_id=series_id,
            title=str(series["mowen_directory_title"]),
            introduction=series.get("mowen_directory_introduction")
            or str(series["description"]),
        )
        save_mapping(args.mapping, mapping)
    sync_article_batch(
        existing_articles,
        mapping,
        args.mapping,
        client,
        publish=args.publish,
        update_existing=update_existing,
    )
    for series in catalog:
        series_id = str(series["id"])
        series_articles = articles_by_series.get(series_id, [])
        if not series_articles:
            continue
        sync_directory(
            series_articles,
            mapping,
            client,
            publish=args.publish,
            cover_uuid=cover_uuid if series_id == FIRST_SERIES_ID else None,
            update_existing=update_existing,
            series_id=series_id,
            title=str(series["mowen_directory_title"]),
            introduction=series.get("mowen_directory_introduction")
            or str(series["description"]),
        )
    save_mapping(args.mapping, mapping)
    action = "Published" if args.publish else "Registered privately"
    print(f"{action}: {len(articles)} article(s) and directory mapping.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
