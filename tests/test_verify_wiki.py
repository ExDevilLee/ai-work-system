from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.verify_wiki import (
    compare_wiki_files,
    retry_verification,
    verify_pre_publish,
    verify_remote_images,
)


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"test-image"
JPEG_BYTES = b"\xff\xd8\xff" + b"test-image"


def write_article(
    repo_root: Path,
    filename: str,
    title: str,
    body: str,
) -> Path:
    path = repo_root / "content" / "articles" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ntitle: {title}\nstatus: ready\nsummary: 摘要\n---\n\n# {title}\n\n{body}\n",
        encoding="utf-8",
    )
    return path


class VerifyWikiTest(unittest.TestCase):
    def test_pre_publish_rejects_missing_article_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_article(root, "2026-07-01-first.md", "第一篇", "![图](images/01/missing.png)")

            with self.assertRaisesRegex(ValueError, "image does not exist"):
                verify_pre_publish(
                    root,
                    "Test Wiki",
                    "https://example.test/wiki",
                    "https://example.test/raw/main",
                )

    def test_pre_publish_rejects_non_numbered_image_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            article = write_article(root, "2026-07-01-first.md", "第一篇", "![图](images/1/diagram.png)")
            image = article.parent / "images" / "1" / "diagram.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(PNG_BYTES)

            with self.assertRaisesRegex(ValueError, "images/<two-digit-number>"):
                verify_pre_publish(
                    root,
                    "Test Wiki",
                    "https://example.test/wiki",
                    "https://example.test/raw/main",
                )

    def test_pre_publish_rejects_other_relative_image_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_article(root, "2026-07-01-first.md", "第一篇", "![图](diagram.png)")

            with self.assertRaisesRegex(ValueError, "images/<two-digit-number>"):
                verify_pre_publish(
                    root,
                    "Test Wiki",
                    "https://example.test/wiki",
                    "https://example.test/raw/main",
                )

    def test_pre_publish_rejects_image_extension_signature_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            article = write_article(root, "2026-07-01-first.md", "第一篇", "![图](images/01/diagram.png)")
            image = article.parent / "images" / "01" / "diagram.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(JPEG_BYTES)

            with self.assertRaisesRegex(ValueError, "format does not match"):
                verify_pre_publish(
                    root,
                    "Test Wiki",
                    "https://example.test/wiki",
                    "https://example.test/raw/main",
                )

    def test_pre_publish_accepts_valid_pages_images_and_navigation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = write_article(root, "2026-07-01-first.md", "第一篇", "![图](images/01/diagram.png)")
            image = first.parent / "images" / "01" / "diagram.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(PNG_BYTES)
            write_article(root, "2026-07-02-second.md", "第二篇", "正文")

            report = verify_pre_publish(
                root,
                "Test Wiki",
                "https://example.test/wiki",
                "https://example.test/raw/main",
            )

            self.assertEqual(report.article_count, 2)
            self.assertEqual(report.image_count, 1)

    def test_post_publish_rejects_stale_remote_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = root / "expected"
            remote = root / "remote"
            expected.mkdir()
            remote.mkdir()
            (expected / "Home.md").write_text("new\n", encoding="utf-8")
            (remote / "Home.md").write_text("old\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "remote Wiki page differs"):
                compare_wiki_files(expected, remote)

    def test_post_publish_rejects_stale_remote_image_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "diagram.png"
            image.write_bytes(PNG_BYTES)

            with self.assertRaisesRegex(RuntimeError, "remote image hash mismatch"):
                verify_remote_images(
                    [("https://example.test/diagram.png", image)],
                    fetcher=lambda _: PNG_BYTES + b"stale",
                )

    def test_post_publish_retries_transient_failure_then_succeeds(self) -> None:
        attempts = 0
        sleeps: list[float] = []

        def operation() -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("remote Wiki page differs")

        retry_verification(
            operation,
            attempts=3,
            delay=0.5,
            sleeper=sleeps.append,
        )

        self.assertEqual(attempts, 2)
        self.assertEqual(sleeps, [0.5])


if __name__ == "__main__":
    unittest.main()
