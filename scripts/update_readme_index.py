#!/usr/bin/env python3
"""Update README article indexes from article frontmatter."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTICLES_DIR = REPO_ROOT / "content" / "articles"
GITHUB_WIKI_BASE = "https://github.com/ExDevilLee/ai-work-system/wiki"
GITEE_WIKI_BASE = "https://gitee.com/ExDevilLee/ai-work-system/wikis"


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}

    end = text.find("\n---\n", 4)
    if end == -1:
        return {}

    metadata: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line or line.startswith(" "):
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")
    return metadata


def wiki_page_name(title: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|#\[\]]+", "-", title).strip()
    name = re.sub(r"\s+", " ", name)
    return name or "Untitled"


def article_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(ARTICLES_DIR.glob("*.md")):
        metadata = parse_frontmatter(path)
        if metadata.get("status") != "ready":
            continue
        title = metadata.get("title") or path.stem
        page = wiki_page_name(title)
        rows.append(
            {
                "title": title,
                "title_en": metadata.get("title_en") or title,
                "source": str(path.relative_to(REPO_ROOT)),
                "github_wiki": f"{GITHUB_WIKI_BASE}/{quote(page.replace(' ', '-'))}",
                "gitee_wiki": f"{GITEE_WIKI_BASE}/{quote(page)}",
            }
        )
    return rows


def replace_block(path: Path, start: str, end: str, lines: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"({re.escape(start)}\n)(.*?)(\n{re.escape(end)})",
        re.DOTALL,
    )
    replacement = r"\1" + "\n".join(lines) + r"\3"
    new_text, count = pattern.subn(replacement, text)
    if count != 1:
        raise SystemExit(f"Expected one generated block in {path.relative_to(REPO_ROOT)}")
    path.write_text(new_text, encoding="utf-8")


def main() -> int:
    rows = article_rows()

    zh_lines = [
        f"- [{row['title']}]({row['github_wiki']})"
        for row in rows
    ]
    en_lines = [
        f"- [{row['title_en']}]({row['github_wiki']})"
        for row in rows
    ]

    if rows:
        zh_lines.extend(
            [
                "",
                "文章标题默认链接到 GitHub Wiki 阅读页；Gitee Wiki 保持同步展示，源码 Markdown 可从 Wiki 页面底部的来源入口进入。",
            ]
        )
        en_lines.extend(
            [
                "",
                "Article titles link to the GitHub Wiki reading pages by default; Gitee Wiki stays in sync, and source Markdown is available from each Wiki page's source link.",
            ]
        )

    replace_block(
        REPO_ROOT / "README.md",
        "<!-- articles:index:start -->",
        "<!-- articles:index:end -->",
        zh_lines,
    )
    replace_block(
        REPO_ROOT / "README-EN.md",
        "<!-- articles:index:start -->",
        "<!-- articles:index:end -->",
        en_lines,
    )
    print(f"Updated README article indexes: {len(rows)} published article(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
