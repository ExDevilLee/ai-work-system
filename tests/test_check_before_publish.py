from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.check_before_publish import resolve_wiki_python, validate_sensitive_content


class CheckBeforePublishTest(unittest.TestCase):
    def test_wiki_python_keeps_virtualenv_launcher_path(self) -> None:
        configured = Path.cwd() / "relative-venv" / "bin" / "python"
        with patch.dict(
            "os.environ",
            {"AI_WORK_SYSTEM_WIKI_PYTHON": str(configured)},
        ):
            with patch(
                "scripts.check_before_publish.supports_wiki_dependencies",
                return_value=True,
            ):
                selected = resolve_wiki_python()

        self.assertEqual(selected, configured.absolute())

    def test_sensitive_content_rejects_private_user_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "article.md"
            path.write_text("本机路径：/Users/example/private.md\n", encoding="utf-8")

            with patch("scripts.check_before_publish.REPO_ROOT", Path(tmp)):
                with self.assertRaisesRegex(RuntimeError, "macOS user path"):
                    validate_sensitive_content([path])

    def test_sensitive_content_accepts_public_article(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "article.md"
            path.write_text(
                "公开图片：images/14/task-systemization-matrix.png\n",
                encoding="utf-8",
            )

            with patch("scripts.check_before_publish.REPO_ROOT", Path(tmp)):
                validate_sensitive_content([path])

    def test_sensitive_content_rejects_api_key_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "article.md"
            path.write_text("token: sk-1234567890abcdefghijklmnop\n", encoding="utf-8")

            with patch("scripts.check_before_publish.REPO_ROOT", Path(tmp)):
                with self.assertRaisesRegex(RuntimeError, "API key"):
                    validate_sensitive_content([path])


if __name__ == "__main__":
    unittest.main()
