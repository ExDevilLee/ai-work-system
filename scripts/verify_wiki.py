#!/usr/bin/env python3
"""Verify Wiki source content before publishing and remote content afterward."""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

try:
    from scripts.sync_wiki import group_articles, ready_articles, render_article_navigation, write_wiki
except ModuleNotFoundError:
    from sync_wiki import group_articles, ready_articles, render_article_navigation, write_wiki


ARTICLE_IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\((?P<path>[^)\s]+)\)")
NUMBERED_IMAGE_PATTERN = re.compile(
    r"images/(?P<number>\d{2})/(?P<filename>[^/\s)]+)$"
)


@dataclass(frozen=True)
class VerificationReport:
    article_count: int
    image_count: int


ImageReference = tuple[str, Path]


def detect_image_format(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    return None


def expected_image_format(path: Path) -> str | None:
    extension = path.suffix.lower()
    return {
        ".png": "png",
        ".jpg": "jpeg",
        ".jpeg": "jpeg",
        ".gif": "gif",
        ".webp": "webp",
    }.get(extension)


def article_images(
    article: dict[str, str | Path],
    sequence: int,
) -> list[tuple[str, Path]]:
    images: list[tuple[str, Path]] = []
    for match in ARTICLE_IMAGE_PATTERN.finditer(str(article["body"])):
        relative_path = match.group("path")
        if relative_path.startswith(("https://", "http://")):
            continue
        numbered = NUMBERED_IMAGE_PATTERN.fullmatch(relative_path)
        if not numbered:
            raise ValueError(
                "[pre-publish] article image path must use "
                f"images/<two-digit-number>/<filename>: {relative_path}"
            )
        if numbered.group("number") != f"{sequence:02d}":
            raise ValueError(
                f"[pre-publish] article image number does not match article sequence: {relative_path}"
            )
        local_path = Path(article["path"]).parent / relative_path
        if not local_path.exists():
            raise ValueError(f"[pre-publish] article image does not exist: {local_path}")
        if local_path.stat().st_size == 0:
            raise ValueError(f"[pre-publish] article image is empty: {local_path}")
        expected = expected_image_format(local_path)
        actual = detect_image_format(local_path.read_bytes())
        if expected is None or actual != expected:
            raise ValueError(
                f"[pre-publish] article image format does not match extension: {local_path}"
            )
        images.append((relative_path, local_path))
    return images


def validate_generated_wiki(
    wiki_dir: Path,
    articles: list[dict[str, str | Path]],
    wiki_base_url: str,
    asset_base_url: str,
    images_by_source: dict[str, list[tuple[str, Path]]],
    repo_root: Path,
) -> None:
    expected_names = {"Home.md", "_Sidebar.md"}
    expected_names.update(f"{article['page']}.md" for article in articles)
    expected_names.update(
        f"{series['wiki_page']}.md"
        for series, _ in group_articles(articles)
        if series["wiki_page"] != "Home"
    )
    actual_names = {path.name for path in wiki_dir.glob("*.md")}
    if actual_names != expected_names:
        raise ValueError(
            f"[pre-publish] generated Wiki page inventory mismatch: {sorted(actual_names)}"
        )

    for series, series_articles in group_articles(articles):
        for index, article in enumerate(series_articles):
            previous_page = str(series_articles[index - 1]["page"]) if index > 0 else None
            next_page = (
                str(series_articles[index + 1]["page"])
                if index + 1 < len(series_articles)
                else None
            )
            expected_navigation = render_article_navigation(
                wiki_base_url,
                previous_page,
                next_page,
                str(series["wiki_page"]),
            )
            page_path = wiki_dir / f"{article['page']}.md"
            page = page_path.read_text(encoding="utf-8")
            if expected_navigation not in page:
                raise ValueError(f"[pre-publish] generated navigation mismatch: {page_path}")
            source = str(Path(article["path"]).relative_to(repo_root))
            for relative_path, _ in images_by_source[source]:
                expected_url = (
                    f"{asset_base_url.rstrip('/')}/content/articles/{relative_path}"
                )
                if expected_url not in page:
                    raise ValueError(
                        f"[pre-publish] generated article image URL mismatch: {page_path}"
                    )


def verify_pre_publish(
    repo_root: Path,
    site_name: str,
    wiki_base_url: str,
    asset_base_url: str,
) -> VerificationReport:
    articles = ready_articles(repo_root)
    images_by_source: dict[str, list[tuple[str, Path]]] = {}
    image_count = 0
    for sequence, article in enumerate(articles, start=1):
        source = str(Path(article["path"]).relative_to(repo_root))
        images = article_images(article, sequence)
        images_by_source[source] = images
        image_count += len(images)

    with tempfile.TemporaryDirectory(prefix="wiki-verify-pre-") as tmp:
        wiki_dir = Path(tmp)
        write_wiki(
            wiki_dir,
            articles,
            site_name,
            wiki_base_url,
            asset_base_url,
            repo_root=repo_root,
        )
        validate_generated_wiki(
            wiki_dir,
            articles,
            wiki_base_url,
            asset_base_url,
            images_by_source,
            repo_root,
        )

    return VerificationReport(len(articles), image_count)


def compare_wiki_files(expected_dir: Path, remote_dir: Path) -> None:
    for expected_path in expected_dir.glob("*.md"):
        remote_path = remote_dir / expected_path.name
        if not remote_path.exists():
            raise RuntimeError(
                f"[post-publish] remote Wiki page is missing: {remote_path.name}"
            )
        if remote_path.read_bytes() != expected_path.read_bytes():
            raise RuntimeError(
                f"[post-publish] remote Wiki page differs: {remote_path.name}"
            )


def download_url(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ai-work-system-wiki-verifier/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise RuntimeError(
                    f"[post-publish] remote image returned HTTP {response.status}: {url}"
                )
            return response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"[post-publish] remote image returned HTTP {exc.code}: {url}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"[post-publish] remote image request failed: {url}"
        ) from exc


def verify_remote_images(
    images: list[ImageReference],
    fetcher: Callable[[str], bytes] = download_url,
) -> None:
    for url, local_path in images:
        local_digest = hashlib.sha256(local_path.read_bytes()).hexdigest()
        remote_digest = hashlib.sha256(fetcher(url)).hexdigest()
        if remote_digest != local_digest:
            raise RuntimeError(
                f"[post-publish] remote image hash mismatch: {url}"
            )


def retry_verification(
    operation: Callable[[], None],
    attempts: int,
    delay: float,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    if attempts < 1:
        raise ValueError("Verification attempts must be at least 1")
    for attempt in range(attempts):
        try:
            operation()
            return
        except RuntimeError:
            if attempt + 1 == attempts:
                raise
            sleeper(delay)


def clone_wiki(remote: str, destination: Path) -> None:
    result = subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", "master", remote, str(destination)],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"[post-publish] remote Wiki clone failed: {detail}")


def collect_image_references(
    articles: list[dict[str, str | Path]],
    repo_root: Path,
    asset_base_url: str,
) -> tuple[dict[str, list[tuple[str, Path]]], list[ImageReference]]:
    images_by_source: dict[str, list[tuple[str, Path]]] = {}
    remote_images: list[ImageReference] = []
    for sequence, article in enumerate(articles, start=1):
        source = str(Path(article["path"]).relative_to(repo_root))
        images = article_images(article, sequence)
        images_by_source[source] = images
        for relative_path, local_path in images:
            public_path = (Path(source).parent / relative_path).as_posix()
            remote_images.append(
                (f"{asset_base_url.rstrip('/')}/{public_path}", local_path)
            )
    return images_by_source, remote_images


def verify_post_publish(
    repo_root: Path,
    site_name: str,
    wiki_base_url: str,
    asset_base_url: str,
    remote: str,
    attempts: int = 6,
    delay: float = 10,
    fetcher: Callable[[str], bytes] = download_url,
    loader: Callable[[str, Path], None] = clone_wiki,
) -> VerificationReport:
    articles = ready_articles(repo_root)
    images_by_source, remote_images = collect_image_references(
        articles,
        repo_root,
        asset_base_url,
    )

    with tempfile.TemporaryDirectory(prefix="wiki-verify-post-") as tmp:
        temporary = Path(tmp)
        expected_dir = temporary / "expected"
        remote_dir = temporary / "remote"
        expected_dir.mkdir()
        write_wiki(
            expected_dir,
            articles,
            site_name,
            wiki_base_url,
            asset_base_url,
            repo_root=repo_root,
        )
        validate_generated_wiki(
            expected_dir,
            articles,
            wiki_base_url,
            asset_base_url,
            images_by_source,
            repo_root,
        )

        def verify_remote_state() -> None:
            if remote_dir.exists():
                shutil.rmtree(remote_dir)
            loader(remote, remote_dir)
            compare_wiki_files(expected_dir, remote_dir)
            verify_remote_images(remote_images, fetcher=fetcher)

        retry_verification(verify_remote_state, attempts, delay)

    return VerificationReport(len(articles), len(remote_images))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Wiki sources before publishing and remote state afterward."
    )
    parser.add_argument("--phase", choices=("pre", "post"), required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--site-name", required=True)
    parser.add_argument("--wiki-base-url", required=True)
    parser.add_argument("--asset-base-url", required=True)
    parser.add_argument("--remote")
    parser.add_argument("--attempts", type=int, default=6)
    parser.add_argument("--delay", type=float, default=10)
    args = parser.parse_args()

    try:
        if args.phase == "pre":
            report = verify_pre_publish(
                args.repo_root,
                args.site_name,
                args.wiki_base_url,
                args.asset_base_url,
            )
        else:
            if not args.remote:
                parser.error("--remote is required for post-publish verification")
            report = verify_post_publish(
                args.repo_root,
                args.site_name,
                args.wiki_base_url,
                args.asset_base_url,
                args.remote,
                attempts=args.attempts,
                delay=args.delay,
            )
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(
        f"Wiki {args.phase}-publish verification passed: "
        f"{report.article_count} article(s), {report.image_count} image(s)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
