#!/usr/bin/env python3
"""Sync ready articles from the main repository into the GitHub Wiki repo."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

try:
    from scripts.series_catalog import load_series_catalog
except ModuleNotFoundError:
    from series_catalog import load_series_catalog


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTICLES_DIR = REPO_ROOT / "content" / "articles"
DEFAULT_WIKI_DIR = REPO_ROOT / ".wiki" / "ai-work-system.wiki"
DEFAULT_REMOTE = "https://github.com/ExDevilLee/ai-work-system.wiki.git"
DEFAULT_SITE_NAME = "GitHub Wiki"
DEFAULT_WIKI_BASE_URL = "https://github.com/ExDevilLee/ai-work-system/wiki"
DEFAULT_ASSET_BASE_URL = "https://raw.githubusercontent.com/ExDevilLee/ai-work-system/main"


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def parse_frontmatter(path: Path) -> tuple[dict[str, object], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text

    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text

    raw = text[4:end]
    body = text[end + len("\n---\n") :]
    try:
        metadata = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML frontmatter: {path}") from exc
    if not isinstance(metadata, dict):
        raise ValueError(f"YAML frontmatter must be a mapping: {path}")
    return metadata, body.lstrip()


def wiki_page_name(title: str, index: int | None = None) -> str:
    name = re.sub(r"[\\/:*?\"<>|#\[\]]+", "-", title).strip()
    name = re.sub(r"\s+", " ", name)
    name = name or "Untitled"
    if index is None:
        return name
    return f"{index:02d}-{name}"


def wiki_page_url(page: str, base_url: str) -> str:
    url_page = page.replace(" ", "-") if "github.com" in base_url else page
    return f"{base_url.rstrip('/')}/{quote(url_page)}"


def ready_articles(repo_root: Path = REPO_ROOT) -> list[dict[str, Any]]:
    catalog = load_series_catalog(repo_root)
    catalog_by_id = {entry["id"]: entry for entry in catalog}
    rows: list[tuple[Path, dict[str, object], str]] = []
    for path in sorted((repo_root / "content" / "articles").glob("*.md")):
        metadata, body = parse_frontmatter(path)
        if metadata.get("status") != "ready":
            continue
        series_id = str(metadata.get("series") or "")
        if series_id not in catalog_by_id:
            raise ValueError(f"Unknown article series '{series_id}' in {path.name}")
        rows.append((path, metadata, body))

    series_counts: dict[str, int] = {}
    articles: list[dict[str, Any]] = []
    for index, (path, metadata, body) in enumerate(rows, start=1):
        title = str(metadata.get("title") or path.stem)
        series_id = str(metadata["series"])
        series = catalog_by_id[series_id]
        series_counts[series_id] = series_counts.get(series_id, 0) + 1
        articles.append(
            {
                "path": path,
                "title": title,
                "summary": str(metadata.get("summary") or ""),
                "body": body,
                "page": wiki_page_name(title, index),
                "series_id": series_id,
                "series_sequence": series_counts[series_id],
                "series_order": series["order"],
                "series_title": series["title"],
                "series_description": series["description"],
                "series_wiki_page": series["wiki_page"],
            }
        )
    return articles


def group_articles(
    articles: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    groups: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
    for article in articles:
        series_id = str(article.get("series_id") or "__legacy__")
        if series_id not in groups:
            groups[series_id] = (
                {
                    "id": series_id,
                    "order": int(article.get("series_order") or 1),
                    "title": str(article.get("series_title") or "文章"),
                    "description": str(article.get("series_description") or ""),
                    "wiki_page": str(article.get("series_wiki_page") or "Home"),
                },
                [],
            )
        groups[series_id][1].append(article)
    return sorted(groups.values(), key=lambda group: group[0]["order"])


def ensure_wiki_repo(wiki_dir: Path, remote: str) -> None:
    if (wiki_dir / ".git").exists():
        return

    wiki_dir.parent.mkdir(parents=True, exist_ok=True)
    clone = run(["git", "clone", remote, str(wiki_dir)], check=False)
    if clone.returncode == 0:
        return

    wiki_dir.mkdir(parents=True, exist_ok=True)
    run(["git", "init"], cwd=wiki_dir)
    run(["git", "branch", "-M", "master"], cwd=wiki_dir)
    run(["git", "remote", "add", "origin", remote], cwd=wiki_dir)


def align_wiki_repo_with_remote(wiki_dir: Path) -> None:
    fetch = run(["git", "fetch", "origin", "master"], cwd=wiki_dir, check=False)
    if fetch.returncode != 0:
        if "Repository not found" in fetch.stderr:
            return
        sys.stderr.write(fetch.stderr)
        raise SystemExit(fetch.returncode)

    remote_head = run(["git", "rev-parse", "--verify", "origin/master"], cwd=wiki_dir, check=False)
    if remote_head.returncode == 0:
        run(["git", "reset", "--hard", "origin/master"], cwd=wiki_dir)


def rewrite_asset_urls(markdown: str, asset_base_url: str) -> str:
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


def render_article_navigation(
    wiki_base_url: str,
    previous_page: str | None,
    next_page: str | None,
    directory_page: str = "Home",
) -> str:
    previous = (
        f"[上一篇]({wiki_page_url(previous_page, wiki_base_url)})"
        if previous_page
        else "无"
    )
    directory = f"[目录]({wiki_page_url(directory_page, wiki_base_url)})"
    following = (
        f"[下一篇]({wiki_page_url(next_page, wiki_base_url)})"
        if next_page
        else "无"
    )
    return (
        "| 上一篇 | 目录 | 下一篇 |\n"
        "| --- | --- | --- |\n"
        f"| {previous} | {directory} | {following} |"
    )


def render_article(
    article: dict[str, Any],
    asset_base_url: str = DEFAULT_ASSET_BASE_URL,
    wiki_base_url: str = DEFAULT_WIKI_BASE_URL,
    previous_page: str | None = None,
    next_page: str | None = None,
    directory_page: str = "Home",
    repo_root: Path = REPO_ROOT,
) -> str:
    source = Path(article["path"]).relative_to(repo_root)
    body = rewrite_asset_urls(str(article["body"]), asset_base_url)
    navigation = render_article_navigation(
        wiki_base_url,
        previous_page,
        next_page,
        directory_page,
    )
    return (
        f"{body.rstrip()}\n\n"
        "---\n\n"
        f"{navigation}\n\n"
        f"Source: `{source}`\n"
    )


def write_wiki(
    wiki_dir: Path,
    articles: list[dict[str, Any]],
    site_name: str,
    wiki_base_url: str,
    asset_base_url: str = DEFAULT_ASSET_BASE_URL,
    repo_root: Path = REPO_ROOT,
) -> list[Path]:
    written: list[Path] = []

    home_lines = [
        "# AI Work System",
        "",
        f"这里是 `ai-work-system` 的 {site_name} 展示层。",
        "",
        "内容源头在主仓库 `content/articles/`；Wiki 只同步 `status: ready` 的文章。",
        "",
        "## 系列文章",
        "",
    ]

    sidebar_lines = ["# 系列文章", ""]
    groups = group_articles(articles)

    for series, series_articles in groups:
        directory_page = str(series["wiki_page"])
        directory_url = wiki_page_url(directory_page, wiki_base_url)
        home_lines.append(f"### [{series['title']}]({directory_url})")
        if series["description"]:
            home_lines.extend(["", str(series["description"])])
        home_lines.append("")
        sidebar_lines.append(f"- [{series['title']}]({directory_url})")

        directory_lines = [
            "<!-- generated:series-index -->",
            f"# {series['title']}",
            "",
        ]
        if series["description"]:
            directory_lines.extend([str(series["description"]), ""])

        for series_index, article in enumerate(series_articles):
            page = str(article["page"])
            title = str(article["title"])
            summary = str(article["summary"])
            previous_page = (
                str(series_articles[series_index - 1]["page"])
                if series_index > 0
                else None
            )
            next_page = (
                str(series_articles[series_index + 1]["page"])
                if series_index + 1 < len(series_articles)
                else None
            )
            url = wiki_page_url(page, wiki_base_url)
            filename = wiki_dir / f"{page}.md"
            filename.write_text(
                render_article(
                    article,
                    asset_base_url=asset_base_url,
                    wiki_base_url=wiki_base_url,
                    previous_page=previous_page,
                    next_page=next_page,
                    directory_page=directory_page,
                    repo_root=repo_root,
                ),
                encoding="utf-8",
            )
            written.append(filename)

            item_number = int(article.get("series_sequence") or series_index + 1)
            home_lines.append(f"{item_number}. [{title}]({url})")
            directory_lines.append(f"{item_number}. [{title}]({url})")
            if summary:
                home_lines.append(f"   {summary}")
                directory_lines.append(f"   {summary}")
            home_lines.append("")
            directory_lines.append("")
            sidebar_lines.append(f"  - [{title}]({url})")

        if directory_page != "Home":
            directory_path = wiki_dir / f"{directory_page}.md"
            directory_path.write_text(
                "\n".join(directory_lines).rstrip() + "\n",
                encoding="utf-8",
            )
            written.append(directory_path)

    home_path = wiki_dir / "Home.md"
    sidebar_path = wiki_dir / "_Sidebar.md"
    home_path.write_text("\n".join(home_lines).rstrip() + "\n", encoding="utf-8")
    sidebar_path.write_text("\n".join(sidebar_lines).rstrip() + "\n", encoding="utf-8")
    written.extend([home_path, sidebar_path])
    remove_stale_wiki_pages(wiki_dir, written)
    return written


def remove_stale_wiki_pages(wiki_dir: Path, written: list[Path]) -> None:
    written_paths = {path.resolve() for path in written}
    for path in wiki_dir.glob("*.md"):
        if path.resolve() in written_paths:
            continue
        text = path.read_text(encoding="utf-8")
        if (
            "Source: `content/articles/" not in text
            and "<!-- generated:series-index -->" not in text
        ):
            continue
        path.unlink()


def commit_and_push(wiki_dir: Path) -> None:
    run(["git", "add", "."], cwd=wiki_dir)
    status = run(["git", "status", "--short"], cwd=wiki_dir).stdout.strip()
    if status:
        run(["git", "commit", "-m", "Sync ready articles"], cwd=wiki_dir)
    else:
        print("No local wiki file changes.")

    push = run(["git", "push", "origin", "HEAD:master"], cwd=wiki_dir, check=False)
    if push.returncode != 0:
        sys.stderr.write(push.stderr)
        if "Repository not found" in push.stderr:
            sys.stderr.write(
                "\nGitHub Wiki repo was not found. If this is the first sync, "
                "create the first Wiki page in the GitHub web UI, then run this script again.\n"
            )
        raise SystemExit(push.returncode)
    if push.stdout:
        print(push.stdout, end="")
    if push.stderr:
        print(push.stderr, end="", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync ready articles to GitHub Wiki.")
    parser.add_argument("--wiki-dir", type=Path, default=DEFAULT_WIKI_DIR)
    parser.add_argument("--remote", default=DEFAULT_REMOTE)
    parser.add_argument("--site-name", default=DEFAULT_SITE_NAME, help="Display name used in generated wiki pages.")
    parser.add_argument(
        "--wiki-base-url",
        default=DEFAULT_WIKI_BASE_URL,
        help="Base URL used for generated Markdown links.",
    )
    parser.add_argument(
        "--asset-base-url",
        default=DEFAULT_ASSET_BASE_URL,
        help="Public repository base URL used to rewrite relative article assets.",
    )
    parser.add_argument("--push", action="store_true", help="Commit and push wiki changes.")
    parser.add_argument("--dry-run", action="store_true", help="Print ready articles without writing wiki files.")
    args = parser.parse_args()

    articles = ready_articles()
    if args.dry_run:
        for article in articles:
            print(f"{article['page']}: {article['path']}")
        print(f"Ready articles: {len(articles)}")
        return 0

    ensure_wiki_repo(args.wiki_dir, args.remote)
    if args.push:
        align_wiki_repo_with_remote(args.wiki_dir)
    written = write_wiki(
        args.wiki_dir,
        articles,
        args.site_name,
        args.wiki_base_url,
        args.asset_base_url,
    )
    print(f"Synced ready articles: {len(articles)}")
    for path in written:
        print(path.relative_to(args.wiki_dir))

    if args.push:
        commit_and_push(args.wiki_dir)
    else:
        print("Local wiki files updated. Re-run with --push to publish.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
