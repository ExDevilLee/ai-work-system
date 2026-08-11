#!/usr/bin/env python3
"""Schema constants, loaders and path-safety helpers for POC 08 fixtures."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "pilot-01"

TASKS = (
    "clean-restore",
    "partial-backup",
    "integrity-mismatch",
    "target-divergence",
    "derived-index",
    "rollback-receipt",
)

CONDITIONS = ("source-only", "backup-inventory", "recovery-gated-bundle")

VALID_STATUSES = frozenset({"active", "superseded", "conflict", "pending-validation"})
VALID_SCOPES = frozenset({"global", "project", "win11"})

# Maps each condition to the generated view files it may see (relative to FIXTURE).
CONDITION_VIEW_FILES: dict[str, tuple[str, ...]] = {
    "source-only": (),
    "backup-inventory": (
        "generated/file-listing.json",
        "generated/version-summary.json",
    ),
    "recovery-gated-bundle": (
        "generated/integrity-report.json",
        "generated/recovery-gates.md",
    ),
}

# Additional fixture files each condition may see (beyond records + source-manifest).
CONDITION_EXTRA_FILES: dict[str, tuple[str, ...]] = {
    "source-only": ("target-state/inventory.json",),
    "backup-inventory": (),
    "recovery-gated-bundle": (
        "backup-manifest.json",
        "target-state/inventory.json",
        "verification-receipts/rb-806-receipt.json",
    ),
}

# Privacy marker regex — must not appear in any committed fixture or prompt.
PRIVATE_PATTERN = (
    r"(?:/Users/|[A-Za-z]:\\|api[_-]?key|secret|password|provider|"
    r"session[_-]?id|token|credential|\.codex/)"
)


# --------------------------------------------------------------------------- #
#  Path safety                                                                 #
# --------------------------------------------------------------------------- #

def ensure_contained_path(
    path: Path, boundary: Path, *, allow_missing: bool = True
) -> Path:
    """Reject lexical escapes and symlink ancestors without exposing paths."""
    path = Path(os.path.abspath(path))
    boundary = Path(os.path.abspath(boundary))
    if allow_missing and not boundary.exists():
        raise FileNotFoundError(f"boundary does not exist: {boundary.name}")
    try:
        path.relative_to(boundary)
    except ValueError:
        resolved = path.resolve()
        boundary_resolved = boundary.resolve()
        try:
            resolved.relative_to(boundary_resolved)
        except ValueError as exc:
            raise ValueError("path escapes boundary") from exc
    return path


# --------------------------------------------------------------------------- #
#  Hashing                                                                     #
# --------------------------------------------------------------------------- #

def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def tree_checksum(root: Path) -> str:
    """Deterministic SHA-256 over the sorted file-tree of *root*."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            digest.update(rel.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
#  Loaders                                                                     #
# --------------------------------------------------------------------------- #

def load_source_manifest() -> dict[str, Any]:
    return json.loads((FIXTURE / "source-manifest.json").read_text(encoding="utf-8"))


def load_backup_manifest() -> dict[str, Any]:
    return json.loads((FIXTURE / "backup-manifest.json").read_text(encoding="utf-8"))


def load_target_state() -> dict[str, Any]:
    return json.loads(
        (FIXTURE / "target-state" / "inventory.json").read_text(encoding="utf-8")
    )


def load_verification_receipts() -> list[dict[str, Any]]:
    receipts_dir = FIXTURE / "verification-receipts"
    if not receipts_dir.is_dir():
        return []
    receipts: list[dict[str, Any]] = []
    for path in sorted(receipts_dir.glob("*.json")):
        receipts.append(json.loads(path.read_text(encoding="utf-8")))
    return receipts
