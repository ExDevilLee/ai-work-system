#!/usr/bin/env python3
"""Update README article indexes from article frontmatter."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

try:
    from scripts.series_catalog import load_series_catalog
except ModuleNotFoundError:
    from series_catalog import load_series_catalog


REPO_ROOT = Path(__file__).resolve().parents[1]
GITHUB_WIKI_BASE = "https://github.com/ExDevilLee/ai-work-system/wiki"
GITEE_WIKI_BASE = "https://gitee.com/ExDevilLee/ai-work-system/wikis"
GITEE_WIKI_HOME = f"{GITEE_WIKI_BASE}/Home"

STATUS_ZH = {"planned": "计划中", "active": "更新中", "complete": "已完成"}
STATUS_EN = {"planned": "Planned", "active": "In Progress", "complete": "Complete"}


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


def wiki_page_name(title: str, index: int | None = None) -> str:
    name = re.sub(r"[\\/:*?\"<>|#\[\]]+", "-", title).strip()
    name = re.sub(r"\s+", " ", name)
    name = name or "Untitled"
    if index is None:
        return name
    return f"{index:02d}-{name}"


def article_rows(repo_root: Path = REPO_ROOT) -> list[dict[str, Any]]:
    articles_dir = repo_root / "content" / "articles"
    catalog = load_series_catalog(repo_root)
    catalog_by_id = {entry["id"]: entry for entry in catalog}
    ready_paths: list[tuple[Path, dict[str, str]]] = []
    for path in articles_dir.rglob("*.md"):
        metadata = parse_frontmatter(path)
        if metadata.get("status") != "ready":
            continue
        series_id = metadata.get("series", "")
        if series_id not in catalog_by_id:
            raise ValueError(f"Unknown article series '{series_id}' in {path.name}")
        if path.parent != articles_dir / series_id:
            raise ValueError(
                f"Article must be stored under content/articles/{series_id}: {path}"
            )
        ready_paths.append((path, metadata))

    ready_paths.sort(
        key=lambda item: (
            int(catalog_by_id[item[1]["series"]]["order"]),
            item[0].name,
            item[0].as_posix(),
        )
    )

    series_counts: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for index, (path, metadata) in enumerate(ready_paths, start=1):
        title = metadata.get("title") or path.stem
        page = wiki_page_name(title, index)
        series_id = metadata["series"]
        series_counts[series_id] = series_counts.get(series_id, 0) + 1
        rows.append(
            {
                "title": title,
                "title_en": metadata.get("title_en") or title,
                "source": str(path.relative_to(repo_root)),
                "series_id": series_id,
                "series_sequence": series_counts[series_id],
                "github_wiki": f"{GITHUB_WIKI_BASE}/{quote(page.replace(' ', '-'))}",
                "gitee_wiki": f"{GITEE_WIKI_BASE}/{quote(page)}",
            }
        )
    return rows


def build_index_lines(
    rows: list[dict[str, Any]], repo_root: Path = REPO_ROOT
) -> tuple[list[str], list[str]]:
    catalog = load_series_catalog(repo_root)
    rows_by_series: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        rows_by_series.setdefault(row["series_id"], []).append(row)

    zh_lines: list[str] = []
    en_lines: list[str] = []
    for series in catalog:
        series_rows = rows_by_series.get(series["id"], [])
        if not series_rows:
            continue
        count = len(series_rows)
        zh_lines.extend(
            [
                f"### {series['title']}（{STATUS_ZH[series['status']]}，共 {count} 篇）",
                "",
                series["description"],
                "",
            ]
        )
        en_lines.extend(
            [
                f"### {series['title_en']} ({STATUS_EN[series['status']]}, {count} "
                f"{'article' if count == 1 else 'articles'})",
                "",
                series["description_en"],
                "",
            ]
        )
        zh_lines.extend(f"- [{row['title']}]({row['github_wiki']})" for row in series_rows)
        en_lines.extend(f"- [{row['title_en']}]({row['github_wiki']})" for row in series_rows)
        mowen_url = series.get("mowen_directory_url", "")
        if mowen_url:
            zh_lines.extend(["", f"[墨问系列目录]({mowen_url})"])
            en_lines.extend(["", f"[MoWen series collection]({mowen_url})"])
        zh_lines.append("")
        en_lines.append("")

    if rows:
        zh_lines.extend(
            [
                f"文章标题默认链接到 GitHub Wiki 阅读页；[Gitee Wiki]({GITEE_WIKI_HOME}) 保持同步展示。源码 Markdown 可从 Wiki 页面底部的来源入口进入。",
            ]
        )
        en_lines.extend(
            [
                f"Article titles link to the GitHub Wiki reading pages by default; [Gitee Wiki]({GITEE_WIKI_HOME}) stays in sync. Source Markdown is available from each Wiki page's source link.",
                "",
                "Article bodies are currently written in Chinese first. English titles are provided for navigation; full English translations may be added selectively.",
            ]
        )
    return zh_lines, en_lines


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
    zh_lines, en_lines = build_index_lines(rows)

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
