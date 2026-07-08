#!/usr/bin/env python3
"""Sync ready articles from the main repository into the GitHub Wiki repo."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTICLES_DIR = REPO_ROOT / "content" / "articles"
DEFAULT_WIKI_DIR = REPO_ROOT / ".wiki" / "ai-work-system.wiki"
DEFAULT_REMOTE = "https://github.com/ExDevilLee/ai-work-system.wiki.git"
DEFAULT_SITE_NAME = "GitHub Wiki"
DEFAULT_WIKI_BASE_URL = "https://github.com/ExDevilLee/ai-work-system/wiki"


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text

    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text

    raw = text[4:end]
    body = text[end + len("\n---\n") :]
    metadata: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line or line.startswith(" "):
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")
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


def ready_articles() -> list[dict[str, str | Path]]:
    rows: list[tuple[Path, dict[str, str], str]] = []
    for path in sorted(ARTICLES_DIR.glob("*.md")):
        metadata, body = parse_frontmatter(path)
        if metadata.get("status") != "ready":
            continue
        rows.append((path, metadata, body))

    articles: list[dict[str, str | Path]] = []
    for index, (path, metadata, body) in enumerate(rows, start=1):
        title = metadata.get("title") or path.stem
        articles.append(
            {
                "path": path,
                "title": title,
                "summary": metadata.get("summary", ""),
                "body": body,
                "page": wiki_page_name(title, index),
            }
        )
    return articles


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


def render_article(article: dict[str, str | Path]) -> str:
    source = Path(article["path"]).relative_to(REPO_ROOT)
    return (
        f"{article['body'].rstrip()}\n\n"
        "---\n\n"
        f"Source: `{source}`\n"
    )


def write_wiki(
    wiki_dir: Path,
    articles: list[dict[str, str | Path]],
    site_name: str,
    wiki_base_url: str,
) -> list[Path]:
    written: list[Path] = []

    home_lines = [
        "# AI Work System",
        "",
        f"这里是 `ai-work-system` 的 {site_name} 展示层。",
        "",
        "内容源头在主仓库 `content/articles/`；Wiki 只同步 `status: ready` 的文章。",
        "",
        "## 文章",
        "",
    ]

    sidebar_lines = ["# 文章", ""]

    for index, article in enumerate(articles, start=1):
        page = str(article["page"])
        title = str(article["title"])
        summary = str(article["summary"])
        url = wiki_page_url(page, wiki_base_url)
        filename = wiki_dir / f"{page}.md"
        filename.write_text(render_article(article), encoding="utf-8")
        written.append(filename)

        home_lines.append(f"{index}. [{title}]({url})")
        if summary:
            home_lines.append(f"   {summary}")
        home_lines.append("")
        sidebar_lines.append(f"- [{title}]({url})")

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
        if "Source: `content/articles/" not in path.read_text(encoding="utf-8"):
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
    written = write_wiki(args.wiki_dir, articles, args.site_name, args.wiki_base_url)
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
