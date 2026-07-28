#!/usr/bin/env python3
"""Run one isolated current-memory-map session and preserve raw evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import ntpath
import os
import platform
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from validate_fixtures import validate


ROOT = Path(__file__).resolve().parent
CONDITIONS = ("source-only", "flat-index", "state-projection")
TASKS = (
    "active-decision",
    "superseded-rule",
    "unresolved-conflict",
    "scope-boundary",
    "pending-observation",
)
CONDITION_VIEW = {
    "source-only": None,
    "flat-index": "flat-index.md",
    "state-projection": "state-projection.json",
}
MIN_FIXTURE_FRAGMENT_BYTES = 32
NODE_REPL_FILE_MARKERS = (
    "fs.",
    "glob",
    "path.join",
    "process.cwd",
    "readdir",
    "readfile",
    "readtextfile",
    "stat(",
)
RUNTIME_PATH_PATTERN = re.compile(
    r"((?:[A-Za-z]:[\\/]|/)[^\s\"']*[\\/]\.codex[\\/][^\s\"']+)"
)
SAFE_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
ABSOLUTE_PATH_PATTERN = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s\"';|,)]+|(?<![A-Za-z0-9_.-])/(?:[^\s\"';|,)]+))"
)
COMMAND_FILE_MARKERS = (
    "cat ",
    "type ",
    "get-content",
    "get-childitem",
    "dir ",
    "find ",
    "grep ",
    "rg ",
    "sed ",
    "stat ",
    "head ",
    "tail ",
    "wc ",
    "readalltext",
    "readallbytes",
    "read_text",
    "read_bytes",
    "readfile",
    "readdir",
    "open(",
    "fs.",
)
COMMAND_NON_FILE_PREFIXES = ("pwd", "echo ", "printf ", "whoami", "date", "get-location")
DANGEROUS_PATH_MARKERS = (
    "..",
    "~",
    "$home",
    "$env:",
    "%userprofile%",
    "process.chdir",
    "os.chdir",
    "set-location",
)
ENVIRONMENT_PATH_MARKERS = (
    "process.env",
    "getenv(",
    "os.getenv",
    "os.environ",
    "expanduser",
    "homedir(",
    "path.home(",
    "environment.getfolderpath",
    "userprofile",
    "$home",
    "${",
    "$env",
    "$env:",
    "%home%",
    "%homepath%",
    "%userprofile%",
)
NESTED_INTERPRETER_PATTERN = re.compile(
    r"(?:^|[;&|]\s*)(?:python(?:3)?|node|(?:ba|z)?sh|cmd|powershell|pwsh)"
    r"(?:\.exe)?\s+(?:-[A-Za-z]*[ce]\b|/c\b|-command\b)",
    flags=re.IGNORECASE,
)
NODE_FILE_CALL_PATTERN = re.compile(
    r"(?:fs\s*\.\s*)?(?:readfilesync|readfile|readdir|readtextfile|stat)\s*\(",
    flags=re.IGNORECASE,
)
POWERSHELL_PROVIDER_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9.-]*):(.*)$")


def validate_path_identifier(value: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or ".." in value
        or not SAFE_IDENTIFIER_PATTERN.fullmatch(value)
    ):
        raise ValueError("unsafe path identifier")
    return value


def argparse_path_identifier(value: str) -> str:
    try:
        return validate_path_identifier(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def ensure_contained_path(
    path: Path, boundary: Path, *, allow_missing: bool = True
) -> Path:
    """Reject lexical escapes and symlink ancestors without exposing paths."""
    path = Path(os.path.abspath(path))
    boundary = Path(os.path.abspath(boundary))
    try:
        relative = path.relative_to(boundary)
    except ValueError as error:
        raise ValueError("path escapes boundary") from error
    current = boundary
    for part in relative.parts:
        if current.is_symlink():
            raise ValueError("path contains symlink ancestor")
        current = current / part
    if current.is_symlink():
        raise ValueError("path contains symlink ancestor")
    try:
        boundary_resolved = boundary.resolve(strict=True)
        resolved = path.resolve(strict=not allow_missing)
        resolved.relative_to(boundary_resolved)
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        if allow_missing and isinstance(error, FileNotFoundError):
            resolved = path.resolve(strict=False)
            try:
                resolved.relative_to(boundary_resolved)
            except ValueError as nested:
                raise ValueError("path escapes boundary") from nested
        else:
            raise ValueError("path escapes boundary") from error
    return path


def _absolute_paths(value: str) -> tuple[str, ...]:
    paths = []
    for match in ABSOLUTE_PATH_PATTERN.finditer(value):
        prefix = value[: match.start()].rstrip()
        if prefix.endswith(("+'", '+"', "+ '", '+ "')):
            continue
        paths.append(match.group(0))
    return tuple(paths)


def _absolute_path_is_within(path_text: str, workspace: Path) -> bool:
    if re.match(r"^[A-Za-z]:[\\/]", path_text):
        workspace_text = str(workspace).replace("/", "\\")
        try:
            return ntpath.commonpath((workspace_text, path_text)).casefold() == ntpath.normpath(
                workspace_text
            ).casefold()
        except ValueError:
            return False
    try:
        Path(path_text).resolve(strict=False).relative_to(
            workspace.resolve(strict=False)
        )
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def _has_dangerous_relative_path(value: str) -> bool:
    lowered = value.casefold()
    return any(marker in lowered for marker in DANGEROUS_PATH_MARKERS)


def _path_target_classification(path_text: str, workspace: Path) -> str:
    path_text = path_text.strip()
    if not path_text or _has_dangerous_relative_path(path_text):
        return "unknown"
    if re.match(r"^[A-Za-z]:[\\/]", path_text) or path_text.startswith("/"):
        return (
            "workspace"
            if _absolute_path_is_within(path_text, workspace)
            else "external"
        )
    if any(character in path_text for character in ("\0", "\n", "\r")):
        return "unknown"
    try:
        (workspace / path_text).resolve(strict=False).relative_to(
            workspace.resolve(strict=False)
        )
    except (OSError, RuntimeError, ValueError):
        return "external"
    return "workspace"


def _content_command_targets(
    executable: str, tokens: Sequence[str]
) -> Optional[tuple[str, ...]]:
    targets: list[str] = []
    index = 1
    while index < len(tokens):
        token = tokens[index]
        lowered = token.casefold()
        if token.startswith("-"):
            if executable == "get-content" and lowered in {
                "-path",
                "-literalpath",
            }:
                index += 1
                if index >= len(tokens):
                    return None
                targets.append(tokens[index])
            elif executable == "get-content" and lowered != "-raw":
                return None
            index += 1
            continue
        targets.append(token)
        index += 1
    return tuple(targets) if targets else None


def _rg_command_targets(tokens: Sequence[str]) -> Optional[tuple[str, ...]]:
    files_mode = "--files" in tokens[1:]
    positional: list[str] = []
    index = 1
    while index < len(tokens):
        token = tokens[index]
        lowered = token.casefold()
        if lowered in {"--files", "--hidden", "--no-ignore", "-n", "-i"}:
            index += 1
            continue
        if lowered in {"-g", "--glob"}:
            index += 2
            if index > len(tokens):
                return None
            continue
        if lowered.startswith("--glob="):
            index += 1
            continue
        if token.startswith("-"):
            return None
        positional.append(token)
        index += 1
    if files_mode:
        return tuple(positional) if positional else (".",)
    if len(positional) == 1:
        return (".",)
    if len(positional) < 2:
        return None
    return tuple(positional[1:])


def _find_command_targets(tokens: Sequence[str]) -> Optional[tuple[str, ...]]:
    expression_index = next(
        (index for index, token in enumerate(tokens[1:], start=1) if token.startswith("-")),
        len(tokens),
    )
    targets = tuple(tokens[1:expression_index])
    expression = tuple(token.casefold() for token in tokens[expression_index:])
    if not targets or expression != ("-type", "f"):
        return None
    return targets


def _sed_command_targets(tokens: Sequence[str]) -> Optional[tuple[str, ...]]:
    index = 1
    if index < len(tokens) and tokens[index] == "-n":
        index += 1
    if index >= len(tokens) or re.fullmatch(r"\d+(?:,\d+)?p", tokens[index]) is None:
        return None
    targets = tuple(tokens[index + 1 :])
    return targets if targets else None


def _get_child_item_targets(tokens: Sequence[str]) -> Optional[tuple[str, ...]]:
    targets: list[str] = []
    index = 1
    while index < len(tokens):
        token = tokens[index]
        lowered = token.casefold()
        if lowered in {"-recurse", "-file"}:
            index += 1
            continue
        if lowered in {"-path", "-literalpath"}:
            index += 1
            if index >= len(tokens):
                return None
            targets.append(tokens[index])
            index += 1
            continue
        if token.startswith("-"):
            return None
        targets.append(token)
        index += 1
    return tuple(targets) if targets else None


def _simple_command_targets(command: str) -> Optional[tuple[str, ...]]:
    """Return all path targets for a strict, read-only command allowlist."""
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return None
    if not tokens:
        return None
    executable = Path(tokens[0]).name.casefold().removesuffix(".exe")
    if re.search(r"[;&<>`]", command):
        return None
    if "|" in command and (executable != "rg" or "|" in tokens):
        return None
    if executable in {"cat", "type", "get-content", "nl"}:
        return _content_command_targets(executable, tokens)
    if executable == "rg":
        return _rg_command_targets(tokens)
    if executable == "find":
        return _find_command_targets(tokens)
    if executable == "sed":
        return _sed_command_targets(tokens)
    if executable == "get-childitem":
        return _get_child_item_targets(tokens)
    return None


def _uses_powershell_provider(command: str) -> bool:
    try:
        tokens = shlex.split(command, posix=False)
    except ValueError:
        return False
    if not tokens:
        return False
    executable = Path(tokens[0].strip("\"'")).name.casefold().removesuffix(".exe")
    if executable not in {"get-content", "get-childitem"}:
        return False
    for token in tokens[1:]:
        target = token.strip("\"'")
        match = POWERSHELL_PROVIDER_PATTERN.fullmatch(target)
        if match is None:
            continue
        provider_name, remainder = match.groups()
        if len(provider_name) == 1 and remainder.startswith(("\\", "/")):
            continue
        return True
    return False


def command_output_bytes(item: object) -> int:
    if not isinstance(item, dict):
        return 0
    return len(str(item.get("aggregated_output", "")).encode("utf-8"))


def _unwrap_read_only_shell(command: str) -> Optional[str]:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return None
    if len(tokens) != 3 or Path(tokens[0]).name.casefold() not in {"sh", "bash", "zsh"}:
        return None
    if tokens[1] not in {"-c", "-lc"} or re.search(r"[;&|]", tokens[2]):
        return None
    return tokens[2]


def classify_command_execution(item: object, workspace: Path) -> str:
    if not isinstance(item, dict):
        return "unknown"
    command = str(item.get("command", ""))
    inner_command = _unwrap_read_only_shell(command)
    if inner_command is not None:
        return classify_command_execution({"command": inner_command}, workspace)
    lowered = command.casefold()
    if NESTED_INTERPRETER_PATTERN.search(command):
        return "unknown"
    if any(marker in lowered for marker in ENVIRONMENT_PATH_MARKERS):
        return "unknown"
    if re.search(r"(?:\$[A-Za-z_]\w*|%[A-Za-z_]\w*%|\$\(|`)", command):
        return "unknown"
    if _uses_powershell_provider(command):
        return "external"
    absolute_paths = _absolute_paths(command)
    if any(not _absolute_path_is_within(path, workspace) for path in absolute_paths):
        return "external"
    targets = _simple_command_targets(command)
    if targets is not None:
        classifications = {
            _path_target_classification(target, workspace) for target in targets
        }
        if "external" in classifications:
            return "external"
        if classifications == {"workspace"}:
            return "workspace"
        return "unknown"
    if not any(marker in lowered for marker in COMMAND_FILE_MARKERS):
        stripped = lowered.strip()
        if any(stripped == prefix or stripped.startswith(prefix) for prefix in COMMAND_NON_FILE_PREFIXES):
            return "non_workspace"
        return "unknown"
    return "unknown"


def is_runtime_path(value: object) -> bool:
    normalized = str(value).replace("\\", "/")
    return "/.codex/" in normalized


def runtime_tool_access_count(
    events: Sequence[dict[str, object]], workspace: Path, fixture: Path
) -> int:
    """Count external or unprovable completed file-access events."""
    unsafe = 0
    for event in events:
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if item.get("type") == "command_execution":
            classification = classify_command_execution(item, workspace)
        elif item.get("type") == "mcp_tool_call":
            classification = classify_mcp_tool_call(item, fixture, workspace)[0]
        else:
            continue
        if classification in {"external", "unknown"}:
            unsafe += 1
    return unsafe


def has_unmeasured_mcp_tool_calls(
    events: Sequence[dict[str, object]], fixture: Optional[Path] = None,
    workspace: Optional[Path] = None,
) -> bool:
    if fixture is None:
        return any(
            event.get("type") == "item.completed"
            and isinstance(event.get("item"), dict)
            and event["item"].get("type") == "mcp_tool_call"
            for event in events
        )
    return any(
        classify_mcp_tool_call(event.get("item"), fixture, workspace or fixture)[0]
        in {"unknown", "external"}
        for event in events
        if event.get("type") == "item.completed"
    )


def mcp_result_text(item: object) -> Optional[str]:
    if not isinstance(item, dict):
        return None
    result = item.get("result")
    if not isinstance(result, dict):
        return None
    content = result.get("content")
    if not isinstance(content, list):
        return None
    texts = [
        entry.get("text")
        for entry in content
        if isinstance(entry, dict) and isinstance(entry.get("text"), str)
    ]
    return "".join(texts) if texts else None


def structured_string_leaves(value: object) -> Iterable[str]:
    """Yield strings from JSON-shaped MCP output, including encoded JSON strings."""
    if isinstance(value, str):
        yield value
        try:
            decoded = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return
        if decoded != value:
            yield from structured_string_leaves(decoded)
    elif isinstance(value, dict):
        for child in value.values():
            yield from structured_string_leaves(child)
    elif isinstance(value, list):
        for child in value:
            yield from structured_string_leaves(child)


def fixture_texts(fixture: Optional[Path]) -> Iterable[str]:
    if fixture is None or not fixture.is_dir():
        return ()
    texts = []
    for path in fixture.rglob("*"):
        if not path.is_file():
            continue
        try:
            texts.append(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            continue
    return texts


def result_contains_fixture_content(
    result_candidates: Sequence[str], fixture_contents: Iterable[str]
) -> bool:
    for fixture_text in fixture_contents:
        if not fixture_text:
            continue
        for candidate in result_candidates:
            if fixture_text in candidate:
                return True
            fragment = candidate.strip()
            if (
                len(fragment.encode("utf-8")) >= MIN_FIXTURE_FRAGMENT_BYTES
                and fragment in fixture_text
            ):
                return True
            for start in range(len(fixture_text)):
                end = start
                fragment_bytes = 0
                while (
                    end < len(fixture_text)
                    and fragment_bytes < MIN_FIXTURE_FRAGMENT_BYTES
                ):
                    fragment_bytes += len(fixture_text[end].encode("utf-8"))
                    end += 1
                if (
                    fragment_bytes >= MIN_FIXTURE_FRAGMENT_BYTES
                    and fixture_text[start:end] in candidate
                ):
                    return True
    return False


def mcp_arguments_text(item: object) -> str:
    if not isinstance(item, dict):
        return ""
    arguments = item.get("arguments")
    if isinstance(arguments, dict):
        return json.dumps(arguments, ensure_ascii=False)
    return str(arguments or "")


def mcp_argument_strings(item: object) -> tuple[str, ...]:
    if not isinstance(item, dict):
        return ()
    arguments = item.get("arguments")
    if isinstance(arguments, (dict, list, str)):
        return tuple(structured_string_leaves(arguments))
    return ()


def _first_call_argument(value: str, opening_parenthesis: int) -> Optional[str]:
    depth = 0
    quote: Optional[str] = None
    escaped = False
    start = opening_parenthesis + 1
    for index in range(start, len(value)):
        character = value[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character == "(":
            depth += 1
        elif character == ")":
            if depth == 0:
                return value[start:index].strip()
            depth -= 1
        elif character == "," and depth == 0:
            return value[start:index].strip()
    return None


def _node_file_targets(code: str) -> Optional[tuple[str, ...]]:
    targets: list[str] = []
    for match in NODE_FILE_CALL_PATTERN.finditer(code):
        target = _first_call_argument(code, match.end() - 1)
        if target is None:
            return None
        targets.append(target)
    return tuple(targets) if targets else None


def _literal_string(expression: str) -> Optional[str]:
    match = re.fullmatch(r"\s*(['\"])(.*?)\1\s*", expression, flags=re.DOTALL)
    if match is None:
        return None
    return match.group(2)


def _cwd_variable_is_bound(code: str, variable: str) -> bool:
    binding = re.search(
        rf"(?:const|let|var)\s+{re.escape(variable)}\s*=\s*process\.cwd\(\)\s*;?",
        code,
    )
    assignments = re.findall(
        rf"\b{re.escape(variable)}\s*(?:[+\-*/])?=(?!=)", code
    )
    return binding is not None and len(assignments) == 1


def _split_expression_arguments(value: str) -> Optional[tuple[str, ...]]:
    arguments: list[str] = []
    quote: Optional[str] = None
    escaped = False
    start = 0
    for index, character in enumerate(value):
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character in "()":
            return None
        elif character == ",":
            arguments.append(value[start:index].strip())
            start = index + 1
    if quote is not None:
        return None
    arguments.append(value[start:].strip())
    return tuple(arguments) if all(arguments) else None


def _literal_path_join(expression: str, workspace: Path) -> Optional[str]:
    match = re.fullmatch(r"\s*path\.join\s*\((.*)\)\s*", expression, re.DOTALL)
    if match is None:
        return None
    arguments = _split_expression_arguments(match.group(1))
    if arguments is None:
        return None
    fragments: list[str] = []
    for argument in arguments:
        fragment = _literal_string(argument)
        if fragment is None:
            return None
        if _path_target_classification(fragment, workspace) != "workspace":
            return None
        fragments.append(fragment.strip("/\\"))
    return "/".join(fragment for fragment in fragments if fragment)


def _node_target_classification(
    expression: str, code: str, workspace: Path
) -> str:
    literal = _literal_string(expression)
    if literal is not None:
        return _path_target_classification(literal, workspace)

    literal_join = _literal_path_join(expression, workspace)
    if literal_join is not None:
        return _path_target_classification(literal_join, workspace)

    if re.fullmatch(r"\s*process\.cwd\(\)\s*", expression):
        return "workspace"
    variable_match = re.fullmatch(r"\s*([A-Za-z_$][A-Za-z0-9_$]*)\s*", expression)
    if variable_match and _cwd_variable_is_bound(code, variable_match.group(1)):
        return "workspace"

    cwd_suffix = re.fullmatch(
        r"\s*(process\.cwd\(\)|[A-Za-z_$][A-Za-z0-9_$]*)\s*\+\s*"
        r"(['\"])(.*?)\2\s*",
        expression,
        flags=re.DOTALL,
    )
    if cwd_suffix is not None:
        root = cwd_suffix.group(1)
        if root != "process.cwd()" and not _cwd_variable_is_bound(code, root):
            return "unknown"
        suffix = cwd_suffix.group(3).lstrip("/\\")
        return _path_target_classification(suffix, workspace)

    scoped_entry = re.fullmatch(
        r"\s*(['\"])([^'\"]*[/\\])\1\s*\+\s*"
        r"([A-Za-z_$][A-Za-z0-9_$]*)\s*",
        expression,
    )
    if scoped_entry is not None:
        prefix = scoped_entry.group(2).rstrip("/\\")
        variable = scoped_entry.group(3)
        escaped_prefix = re.escape(prefix)
        listing_pattern = re.compile(
            rf"(?:fs\s*\.\s*)?readdir\s*\(\s*(['\"])"
            rf"{escaped_prefix}\1\s*\).*?\b{re.escape(variable)}\s*=>",
            flags=re.IGNORECASE | re.DOTALL,
        )
        if listing_pattern.search(code):
            return _path_target_classification(prefix, workspace)
    return "unknown"


def fixture_path_markers(fixture: Optional[Path]) -> set[str]:
    if fixture is None or not fixture.is_dir():
        return set()
    return {
        path.relative_to(fixture).as_posix()
        for path in fixture.rglob("*")
    }


def result_matches_fixture_paths(
    result_candidates: Sequence[str], fixture: Optional[Path]
) -> bool:
    markers = fixture_path_markers(fixture)
    file_paths = {marker for marker in markers if "/" in marker}
    if any(
        marker in candidate.replace("\\", "/")
        for marker in file_paths
        for candidate in result_candidates
    ):
        return True

    if fixture is None or not fixture.is_dir():
        return False
    directories = [fixture]
    directories.extend(path for path in fixture.rglob("*") if path.is_dir())
    for directory in directories:
        entries = [child.name for child in directory.iterdir()]
        if len(entries) < 2:
            continue
        if any(all(entry in candidate for entry in entries) for candidate in result_candidates):
            return True
    return False


def classify_mcp_tool_call(
    item: object, fixture: Optional[Path], workspace: Optional[Path] = None
) -> tuple[str, Optional[int]]:
    """Classify MCP output without persisting tool arguments or absolute paths."""
    if not isinstance(item, dict):
        return "unknown", None
    server = item.get("server")
    tool = item.get("tool")
    if server == "codex" and tool in {
        "list_mcp_resources",
        "list_mcp_resource_templates",
    }:
        return "non_workspace", None

    argument_values = mcp_argument_strings(item)
    args_text = "\n".join(argument_values).replace("\\", "/")
    lowered_args = args_text.casefold()
    tool_text = str(tool or "").casefold()
    absolute_paths = _absolute_paths(args_text)
    has_file_operation = (
        server == "node_repl"
        and any(marker in args_text.casefold() for marker in NODE_REPL_FILE_MARKERS)
    ) or any(
        marker in tool_text
        for marker in ("read_file", "readfile", "readdir", "list_directory", "stat")
    )
    if not has_file_operation:
        if absolute_paths:
            if workspace is not None and all(
                _absolute_path_is_within(path, workspace)
                for path in absolute_paths
            ):
                return "unknown", None
            return "external", None
        if any(
            marker in args_text
            for marker in fixture_path_markers(fixture)
        ):
            return "unknown", None
        return "non_workspace", None
    if workspace is None:
        return "unknown", None
    if any(marker in lowered_args for marker in ENVIRONMENT_PATH_MARKERS):
        return "unknown", None
    if re.search(r"(?:\$\(|`|\$[A-Za-z_]\w*|%[A-Za-z_]\w*%)", args_text):
        return "unknown", None
    if any(not _absolute_path_is_within(path, workspace) for path in absolute_paths):
        return "external", None
    if _has_dangerous_relative_path(args_text):
        return "unknown", None

    if server == "node_repl":
        targets = _node_file_targets(args_text)
        if targets is None:
            return "unknown", None
        classifications = {
            _node_target_classification(target, args_text, workspace)
            for target in targets
        }
        if "external" in classifications:
            return "external", None
        if classifications != {"workspace"}:
            return "unknown", None
    else:
        if len(argument_values) != 1:
            return "unknown", None
        classification = _path_target_classification(argument_values[0], workspace)
        if classification != "workspace":
            return classification, None

    result_text = mcp_result_text(item)
    if result_text is None:
        return "unknown", None
    return "workspace", len(result_text.encode("utf-8"))


def mcp_workspace_metrics(
    events: Sequence[dict[str, object]], fixture: Path, workspace: Optional[Path] = None
) -> tuple[int, int, int]:
    workspace_calls = 0
    workspace_output_bytes = 0
    unmeasured_calls = 0
    for event in events:
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "mcp_tool_call":
            continue
        classification, output_bytes = classify_mcp_tool_call(
            item, fixture, workspace or fixture
        )
        if classification == "workspace" and output_bytes is not None:
            workspace_calls += 1
            workspace_output_bytes += output_bytes
        elif classification in {"unknown", "external"}:
            unmeasured_calls += 1
    return workspace_calls, workspace_output_bytes, unmeasured_calls


def tree_checksum(root: Path) -> str:
    digest = hashlib.sha256()
    files = (item for item in root.rglob("*") if item.is_file())
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def resident_instruction_bytes(fixture: Path) -> int:
    return len((fixture / "AGENTS.md").read_bytes())


def assemble_fixture(fixture_root: Path, condition: str, destination: Path) -> None:
    """Build one condition snapshot without exposing unassigned generated views."""
    if condition not in CONDITION_VIEW:
        raise ValueError(f"unsupported condition: {condition}")
    fixture_root = ensure_contained_path(
        fixture_root, fixture_root, allow_missing=False
    )
    destination = ensure_contained_path(destination, destination.parent)
    if destination.exists():
        raise FileExistsError(f"fixture destination already exists: {destination}")

    records = fixture_root / "records"
    instructions = fixture_root / "conditions" / condition / "AGENTS.md"
    selected_view = CONDITION_VIEW[condition]
    required = [records, instructions]
    if selected_view is not None:
        required.append(fixture_root / "generated" / selected_view)
    for path in required:
        ensure_contained_path(path, fixture_root, allow_missing=False)
    missing = [path.name for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("missing fixture input: " + ", ".join(missing))

    staging = destination.with_name(destination.name + ".staging")
    if staging.exists():
        raise FileExistsError(f"fixture staging directory already exists: {staging}")
    try:
        staging.mkdir(parents=True)
        shutil.copytree(records, staging / "records")
        shutil.copy2(instructions, staging / "AGENTS.md")
        if selected_view is not None:
            generated = staging / "generated"
            generated.mkdir()
            shutil.copy2(
                fixture_root / "generated" / selected_view,
                generated / selected_view,
            )
        staging.replace(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def resolve_codex_executable() -> str:
    executable = shutil.which("codex")
    if executable is None:
        raise SystemExit("codex executable was not found on PATH")
    return executable


def run_utf8_command(
    command: Sequence[str], *, check: bool = False, input_text: Optional[str] = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        input=input_text,
    )


def command_output(*args: str) -> str:
    result = run_utf8_command(args, check=True)
    return result.stdout.strip()


def build_codex_command(
    codex_executable: str,
    workspace: Path,
    final_path: Path,
    *,
    model: Optional[str],
    reasoning_effort: Optional[str],
) -> list[str]:
    command = [
        codex_executable,
        "exec",
        "-C",
        str(workspace),
        "--skip-git-repo-check",
        "--ignore-rules",
        "--sandbox",
        "read-only",
        "--ephemeral",
        "--json",
        "--config",
        "features.plugins=false",
        "--config",
        "mcp_servers={}",
        "--output-last-message",
        str(final_path),
    ]
    if model:
        command.extend(["--model", model])
    if reasoning_effort:
        command.extend(
            ["--config", f'model_reasoning_effort="{reasoning_effort}"']
        )
    command.append("-")
    return command


def adjusted_mixed_workspace_bytes(item: dict[str, object]) -> Optional[int]:
    """Remove known global file prefixes from one mixed-scope command output."""
    command = str(item.get("command", ""))
    output = str(item.get("aggregated_output", ""))
    runtime_paths = list(dict.fromkeys(RUNTIME_PATH_PATTERN.findall(command)))
    if not runtime_paths:
        return None
    for raw_path in runtime_paths:
        path = Path(raw_path)
        if not path.is_file():
            return None
        prefix = path.read_text(encoding="utf-8")
        if not output.startswith(prefix):
            return None
        output = output[len(prefix) :]
    return len(output.encode("utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "condition", type=argparse_path_identifier, choices=CONDITIONS
    )
    parser.add_argument("--label", type=argparse_path_identifier, default="pilot-01")
    parser.add_argument(
        "--fixture-set", type=argparse_path_identifier, default="pilot-01"
    )
    parser.add_argument(
        "--task",
        type=argparse_path_identifier,
        choices=TASKS,
        default="active-decision",
    )
    parser.add_argument("--model", help="Lock the model for formal repeated runs")
    parser.add_argument("--reasoning-effort", choices=("low", "medium", "high", "xhigh"))
    parser.add_argument(
        "--platform-tag",
        type=argparse_path_identifier,
        choices=("macos", "win11"),
        default="macos",
        help="Keep evidence separated by execution platform",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.label.startswith("pilot"):
        missing = [
            name
            for name, value in (
                ("--model", args.model),
                ("--reasoning-effort", args.reasoning_effort),
            )
            if not value
        ]
        if missing:
            raise SystemExit("formal runs must set " + ", ".join(missing))

    try:
        fixture_root = ensure_contained_path(
            ROOT / "fixtures" / args.fixture_set, ROOT, allow_missing=False
        )
        condition_fixture = ensure_contained_path(
            fixture_root / "conditions" / args.condition,
            fixture_root,
            allow_missing=False,
        )
        prompt_path = ensure_contained_path(
            ROOT / "prompts" / f"{args.task}.md", ROOT, allow_missing=False
        )
    except ValueError as error:
        raise SystemExit(f"path containment failed: {type(error).__name__}") from error
    fixture_errors = validate(ROOT, args.fixture_set, require_generated=True)
    if fixture_errors:
        raise SystemExit("fixture validation failed:\n" + "\n".join(fixture_errors))
    if not condition_fixture.is_dir():
        raise SystemExit("condition fixture directory does not exist")
    if not prompt_path.is_file():
        raise SystemExit("prompt does not exist")

    codex_executable = resolve_codex_executable()
    started_at = datetime.now(timezone.utc)
    run_name = f"{args.label}-{args.task}-{args.condition}"
    try:
        run_dir = ensure_contained_path(
            ROOT / "runs" / "private" / args.platform_tag / run_name, ROOT
        )
    except ValueError as error:
        raise SystemExit(f"run path containment failed: {type(error).__name__}") from error

    if run_dir.exists():
        raise SystemExit("run directory already exists")
    run_dir.mkdir(parents=True)
    try:
        ensure_contained_path(run_dir, ROOT, allow_missing=False)
    except ValueError as error:
        raise SystemExit("run path containment failed after creation") from error
    fixture = run_dir / "fixture-snapshot"
    try:
        assemble_fixture(fixture_root, args.condition, fixture)
        shutil.copy2(prompt_path, run_dir / "prompt.md")
    except (OSError, ValueError) as error:
        raise SystemExit(f"fixture assembly failed: {type(error).__name__}") from error

    with tempfile.TemporaryDirectory(prefix=f"current-map-poc-{args.condition}-") as temp:
        workspace = Path(temp) / "workspace"
        shutil.copytree(fixture, workspace)
        command = build_codex_command(
            codex_executable,
            workspace,
            run_dir / "final.md",
            model=args.model,
            reasoning_effort=args.reasoning_effort,
        )
        prompt_text = prompt_path.read_text(encoding="utf-8")

        started = time.monotonic()
        result = run_utf8_command(command, input_text=prompt_text)
        elapsed_seconds = round(time.monotonic() - started, 3)

    (run_dir / "raw.jsonl").write_text(result.stdout, encoding="utf-8")
    (run_dir / "stderr.log").write_text(result.stderr, encoding="utf-8")

    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    completed_commands = [
        event["item"]
        for event in events
        if event.get("type") == "item.completed"
        and isinstance(event.get("item"), dict)
        and event["item"].get("type") == "command_execution"
    ]
    classified_commands = [
        (item, classify_command_execution(item, workspace))
        for item in completed_commands
    ]
    workspace_commands = [
        item for item, classification in classified_commands if classification == "workspace"
    ]
    unsafe_command_calls = [
        item
        for item, classification in classified_commands
        if classification in {"external", "unknown"}
    ]
    external_command_calls = [
        item
        for item, classification in classified_commands
        if classification == "external"
    ]
    usage_events = [event["usage"] for event in events if event.get("type") == "turn.completed"]
    mcp_workspace_calls, mcp_workspace_bytes, unmeasured_mcp_tool_calls = (
        mcp_workspace_metrics(events, fixture, workspace)
    )
    runtime_access_calls = runtime_tool_access_count(events, workspace, fixture)
    workspace_metric_coverage_complete = (
        unmeasured_mcp_tool_calls == 0 and not unsafe_command_calls
    )

    metadata = {
        "run_name": run_name,
        "condition": args.condition,
        "fixture_set": args.fixture_set,
        "task": args.task,
        "purpose": (
            "protocol pilot"
            if args.label.startswith("pilot")
            else "model sensitivity"
            if args.label.startswith("model-")
            else "formal run"
        ),
        "started_at_utc": started_at.isoformat(),
        "platform": platform.platform(),
        "platform_tag": args.platform_tag,
        "python_version": platform.python_version(),
        "codex_version": command_output(codex_executable, "--version"),
        "requested_model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "model_record_status": "explicit" if args.model else "implicit default; model not emitted in JSONL",
        "fixture_sha256": tree_checksum(fixture),
        "prompt_sha256": hashlib.sha256(prompt_path.read_bytes()).hexdigest(),
        "sandbox": "read-only",
        "ephemeral": True,
        "plugins_enabled": False,
        "command_execution_policy": "codex-no-mcp-and-no-rules",
        "runtime_tool_access_calls": runtime_access_calls,
        "protocol_environment_isolated": runtime_access_calls == 0,
        "exit_code": result.returncode,
        "elapsed_seconds": elapsed_seconds,
        "usage": usage_events[-1] if usage_events else None,
        "completed_command_calls": len(completed_commands),
        "workspace_command_calls": (
            len(workspace_commands) + mcp_workspace_calls
        ),
        "mixed_scope_command_calls": len(external_command_calls),
        "workspace_mcp_tool_calls": mcp_workspace_calls,
        "workspace_mcp_output_bytes": mcp_workspace_bytes,
        "workspace_metric_coverage_complete": workspace_metric_coverage_complete,
        "workspace_metric_unmeasured_command_calls": len(unsafe_command_calls),
        "workspace_metric_unmeasured_tool_calls": (
            len(unsafe_command_calls) + unmeasured_mcp_tool_calls
        ),
        "workspace_output_bytes_reliable": workspace_metric_coverage_complete,
        "mixed_scope_adjusted_bytes": 0,
        "workspace_output_bytes": sum(
            command_output_bytes(item) for item in workspace_commands
        )
        + mcp_workspace_bytes,
        "resident_instruction_bytes": resident_instruction_bytes(fixture),
        "command_shape": "codex exec -C <isolated-workspace> --skip-git-repo-check --ignore-rules --sandbox read-only --ephemeral --json --config features.plugins=false --config mcp_servers={} --output-last-message <file> [--model <model>] [--config model_reasoning_effort=<effort>] -; prompt transport: UTF-8 stdin",
    }
    metadata["project_context_bytes_reliable"] = metadata[
        "workspace_output_bytes_reliable"
    ]
    metadata["project_context_bytes"] = (
        metadata["resident_instruction_bytes"] + metadata["workspace_output_bytes"]
        if metadata["project_context_bytes_reliable"]
        else None
    )
    (run_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    if result.returncode == 0 and runtime_access_calls:
        return 2
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
