#!/usr/bin/env python3
"""Run the local checks that must pass before publishing ready articles."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GITHUB_WIKI_BASE = "https://github.com/ExDevilLee/ai-work-system/wiki"
GITHUB_ASSET_BASE = "https://raw.githubusercontent.com/ExDevilLee/ai-work-system/main"
GITEE_WIKI_BASE = "https://gitee.com/ExDevilLee/ai-work-system/wikis"
GITEE_ASSET_BASE = "https://gitee.com/ExDevilLee/ai-work-system/raw/main"
SENSITIVE_PATTERNS = (
    ("macOS user path", re.compile(r"/Users/[^/\s]+/")),
    ("macOS temporary path", re.compile(r"(?:/private)?/var/folders/")),
    ("Windows user path", re.compile(r"[A-Za-z]:[\\/]+Users[\\/]")),
    ("thread identifier", re.compile(r'"thread_id"\s*:')),
    ("API key", re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}")),
    ("model provider label", re.compile(r"provider_label", re.IGNORECASE)),
    ("private model provider", re.compile("msu" + "tools", re.IGNORECASE)),
)


def run(command: list[str]) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def git_common_dir() -> Path:
    value = subprocess.check_output(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=REPO_ROOT,
        text=True,
    ).strip()
    path = Path(value)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def supports_wiki_dependencies(candidate: Path) -> bool:
    if not candidate.is_file():
        return False
    result = subprocess.run(
        [str(candidate), "-c", "import yaml"],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def resolve_wiki_python() -> Path:
    candidates = []
    configured = os.environ.get("AI_WORK_SYSTEM_WIKI_PYTHON")
    if configured:
        configured_path = Path(configured).expanduser()
        if not configured_path.is_absolute():
            configured_path = REPO_ROOT / configured_path
        candidates.append(configured_path)
    candidates.append(venv_python(git_common_dir() / "ai-work-system-publish-checks"))
    candidates.append(Path(sys.executable))

    for candidate in candidates:
        if supports_wiki_dependencies(candidate):
            # Keep a virtualenv launcher path intact; resolving its symlink would
            # silently switch back to the base interpreter and lose site-packages.
            return candidate.absolute()

    raise RuntimeError(
        "Wiki publishing dependencies are missing. Run: "
        "python3 scripts/setup_local_publish_checks.py"
    )


def public_markdown_files() -> list[Path]:
    files = sorted(REPO_ROOT.glob("README*.md"))
    files.extend(sorted((REPO_ROOT / "content" / "articles").rglob("*.md")))
    return files


def validate_sensitive_content(paths: list[Path]) -> None:
    failures = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for label, pattern in SENSITIVE_PATTERNS:
            if pattern.search(text):
                failures.append(f"{path.relative_to(REPO_ROOT)}: {label}")
    if failures:
        raise RuntimeError("Sensitive content check failed:\n" + "\n".join(failures))


def main() -> int:
    try:
        python = resolve_wiki_python()
        npm = shutil.which("npm")
        if npm is None or not (REPO_ROOT / "node_modules" / ".bin" / "markdownlint-cli2").is_file():
            raise RuntimeError(
                "Markdown dependencies are missing. Run: "
                "python3 scripts/setup_local_publish_checks.py"
            )

        run([str(python), "scripts/update_readme_index.py", "--check"])
        run(
            [
                str(python),
                "-m",
                "unittest",
                "tests.test_update_readme_index",
                "tests.test_sync_wiki",
                "tests.test_verify_wiki",
                "tests.test_check_before_publish",
                "-v",
            ]
        )
        for site_name, wiki_base, asset_base in (
            ("GitHub Wiki", GITHUB_WIKI_BASE, GITHUB_ASSET_BASE),
            ("Gitee Wiki", GITEE_WIKI_BASE, GITEE_ASSET_BASE),
        ):
            run(
                [
                    str(python),
                    "scripts/verify_wiki.py",
                    "--phase",
                    "pre",
                    "--site-name",
                    site_name,
                    "--wiki-base-url",
                    wiki_base,
                    "--asset-base-url",
                    asset_base,
                ]
            )

        markdown_files = public_markdown_files()
        run([npm, "run", "lint:md", "--", *[str(path.relative_to(REPO_ROOT)) for path in markdown_files]])
        validate_sensitive_content(markdown_files)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Pre-publish check failed: {exc}", file=sys.stderr)
        return 1

    print("Pre-publish check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
