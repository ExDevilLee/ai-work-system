#!/usr/bin/env python3
"""Load and validate the article-series catalog."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


KNOWN_STATUSES = {"planned", "active", "complete"}
REQUIRED_TEXT_FIELDS = {
    "id",
    "title",
    "title_en",
    "description",
    "description_en",
    "wiki_page",
    "mowen_directory_title",
}


def load_series_catalog(repo_root: Path) -> list[dict[str, Any]]:
    path = repo_root / "content" / "series.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Missing series catalog: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid series catalog JSON: {path}: {exc}") from exc

    if payload.get("version") != 1:
        raise ValueError("Series catalog version must be 1")
    series = payload.get("series")
    if not isinstance(series, list) or not series:
        raise ValueError("Series catalog must contain a non-empty series list")

    ids: set[str] = set()
    orders: set[int] = set()
    wiki_pages: set[str] = set()
    validated: list[dict[str, Any]] = []
    for entry in series:
        if not isinstance(entry, dict):
            raise ValueError("Each series catalog entry must be an object")
        for field in REQUIRED_TEXT_FIELDS:
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(f"Series field '{field}' must be a non-empty string")
        if not isinstance(entry.get("mowen_directory_url", ""), str):
            raise ValueError("Series field 'mowen_directory_url' must be a string")
        cover_path = entry.get("mowen_cover_path")
        cover_url = entry.get("mowen_cover_url")
        if bool(cover_path) != bool(cover_url):
            raise ValueError(
                "Series fields 'mowen_cover_path' and 'mowen_cover_url' must be configured together"
            )
        if cover_path:
            if not isinstance(cover_path, str):
                raise ValueError("Series field 'mowen_cover_path' must be a string")
            relative_cover = Path(cover_path)
            if relative_cover.is_absolute() or ".." in relative_cover.parts:
                raise ValueError("Series field 'mowen_cover_path' must stay inside the repository")
            if not isinstance(cover_url, str) or not cover_url.startswith("https://"):
                raise ValueError("Series field 'mowen_cover_url' must use HTTPS")
        introduction = entry.get("mowen_directory_introduction")
        if introduction is not None and (
            not isinstance(introduction, list)
            or not introduction
            or not all(isinstance(part, str) and part.strip() for part in introduction)
        ):
            raise ValueError(
                "Series field 'mowen_directory_introduction' must be a non-empty string list"
            )
        if entry.get("status") not in KNOWN_STATUSES:
            raise ValueError(f"Unknown series status: {entry.get('status')}")
        order = entry.get("order")
        if not isinstance(order, int) or isinstance(order, bool) or order <= 0:
            raise ValueError("Series order must be a positive integer")
        if entry["id"] in ids:
            raise ValueError(f"Duplicate series id: {entry['id']}")
        if order in orders:
            raise ValueError(f"Duplicate series order: {order}")
        if entry["wiki_page"] in wiki_pages:
            raise ValueError(f"Duplicate series wiki page: {entry['wiki_page']}")
        ids.add(entry["id"])
        orders.add(order)
        wiki_pages.add(entry["wiki_page"])
        validated.append(dict(entry))

    return sorted(validated, key=lambda item: item["order"])


def series_by_id(repo_root: Path) -> dict[str, dict[str, Any]]:
    return {entry["id"]: entry for entry in load_series_catalog(repo_root)}
