#!/usr/bin/env python3
"""Install local publishing checks and enable the repository Git hooks."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


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


def venv_python(venv_path: Path) -> Path:
    if os.name == "nt":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def main() -> int:
    runtime = git_common_dir() / "ai-work-system-publish-checks"
    print(f"Preparing local publishing runtime: {runtime}")
    venv.EnvBuilder(with_pip=True).create(runtime)
    python = venv_python(runtime)
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm is required to install Markdown dependencies")
    run([str(python), "-m", "pip", "install", "--requirement", "requirements-wiki.txt"])
    run([npm, "ci", "--ignore-scripts"])
    run(["git", "config", "core.hooksPath", ".githooks"])
    run([str(python), "scripts/check_before_publish.py"])
    print("Local pre-push publishing checks are enabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
