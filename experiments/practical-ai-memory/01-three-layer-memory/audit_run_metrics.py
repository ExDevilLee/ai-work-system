#!/usr/bin/env python3
"""Audit command scopes and annotate whether workspace byte metrics are reliable."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_experiment import (
    adjusted_mixed_workspace_bytes,
    has_unmeasured_mcp_tool_calls,
    is_runtime_path,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dirs", nargs="+", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    unreliable = 0
    for run_dir in args.run_dirs:
        metadata_path = run_dir / "metadata.json"
        snapshot = run_dir / "fixture-snapshot"
        events = [
            json.loads(line)
            for line in (run_dir / "raw.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        commands = [
            event["item"]
            for event in events
            if event.get("type") == "item.completed"
            and event.get("item", {}).get("type") == "command_execution"
        ]
        markers = {
            path.relative_to(snapshot).as_posix()
            for path in snapshot.rglob("*")
            if path.is_file()
        }
        markers.update(path.name for path in snapshot.rglob("*") if path.is_file())
        mixed = [
            item
            for item in commands
            if is_runtime_path(item.get("command", ""))
            and any(marker in item.get("command", "") for marker in markers)
        ]
        workspace = [
            item for item in commands if not is_runtime_path(item.get("command", ""))
        ]
        adjustments = [adjusted_mixed_workspace_bytes(item) for item in mixed]
        unmeasured_mcp_tool_calls = sum(
            1
            for event in events
            if event.get("type") == "item.completed"
            and event.get("item", {}).get("type") == "mcp_tool_call"
        )
        coverage_complete = not has_unmeasured_mcp_tool_calls(events)

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["workspace_command_calls"] = len(workspace) + len(mixed)
        metadata["mixed_scope_command_calls"] = len(mixed)
        metadata["workspace_metric_coverage_complete"] = coverage_complete
        metadata["workspace_metric_unmeasured_tool_calls"] = (
            unmeasured_mcp_tool_calls
        )
        metadata["workspace_output_bytes_reliable"] = coverage_complete and all(
            value is not None for value in adjustments
        )
        metadata["mixed_scope_adjusted_bytes"] = sum(
            value for value in adjustments if value is not None
        )
        metadata["workspace_output_bytes"] = sum(
            len(item.get("aggregated_output", "").encode("utf-8"))
            for item in workspace
        ) + sum(value for value in adjustments if value is not None)
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if not coverage_complete:
            unreliable += 1
            print(
                f"INCOMPLETE {metadata['run_name']}: "
                f"unmeasured_mcp_tool_calls={unmeasured_mcp_tool_calls}"
            )
        elif mixed and not metadata["workspace_output_bytes_reliable"]:
            unreliable += 1
            print(f"UNRELIABLE {metadata['run_name']}: mixed_scope_commands={len(mixed)}")
        elif mixed:
            print(
                f"ADJUSTED {metadata['run_name']}: "
                f"mixed_scope_bytes={metadata['mixed_scope_adjusted_bytes']}"
            )
        else:
            print(f"OK {metadata['run_name']}")

    print(f"audited={len(args.run_dirs)}, unreliable={unreliable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
