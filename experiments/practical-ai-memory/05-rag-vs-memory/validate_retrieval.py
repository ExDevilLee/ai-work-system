#!/usr/bin/env python3
import json
import sqlite3
from pathlib import Path


def search(rows: list[tuple[str, str]], query: str, top_k: int) -> list[str]:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE corpus USING fts5(path UNINDEXED, body)")
        connection.executemany("INSERT INTO corpus(path, body) VALUES (?, ?)", rows)
        matches = connection.execute(
            "SELECT path, bm25(corpus) AS score FROM corpus "
            "WHERE corpus MATCH ? ORDER BY score, path LIMIT ?",
            (query, top_k),
        ).fetchall()
    finally:
        connection.close()
    return [row[0] for row in matches]


def validate(root: Path, fixture_set: str = "pilot-01") -> list[str]:
    root = Path(root)
    corpus_root = root / "fixtures" / fixture_set / "corpus"
    manifest_path = root / "fixtures" / fixture_set / "retrieval-packets" / "manifest.json"
    errors: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        rows = [
            (path.relative_to(corpus_root).as_posix(), path.read_text(encoding="utf-8"))
            for path in sorted(
                corpus_root.rglob("*.md"),
                key=lambda item: item.relative_to(corpus_root).as_posix(),
            )
        ]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"cannot load retrieval fixture: {exc}"]

    for task, entry in manifest.get("tasks", {}).items():
        try:
            matches = search(rows, entry["query"], int(entry["top_k"]))
        except sqlite3.OperationalError as exc:
            if "fts5" in str(exc).casefold() or "no such module" in str(exc).casefold():
                return [f"FTS5 unavailable: {exc}"]
            errors.append(f"{task}: retrieval query failed: {exc}")
            continue
        for source in entry.get("required_sources", []):
            if source not in matches:
                errors.append(
                    f"{task}: missing required source {source} from Top-{entry['top_k']} "
                    f"results {matches}"
                )
    return errors


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-set", default="pilot-01")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    errors = validate(root, args.fixture_set)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    task_count = len(
        json.loads(
            (root / "fixtures" / args.fixture_set / "retrieval-packets/manifest.json").read_text(encoding="utf-8")
        )["tasks"]
    )
    print(f"retrieval validation passed: tasks={task_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
