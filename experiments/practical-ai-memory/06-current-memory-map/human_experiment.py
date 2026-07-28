#!/usr/bin/env python3
"""Local-only service for the synthetic current-memory-map human trial."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import secrets
from collections import defaultdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
HUMAN_DIR = ROOT / "human"
PACKS_DIR = ROOT / "human-fixtures"
DEFAULT_RESULTS_DIR = ROOT / "human-results" / "private"
CONDITIONS = ("state-table", "visual-map")
PRIVATE_FIELDS = {"name", "email", "username", "provider", "thread_id"}
ABSOLUTE_PATH = re.compile(r"(?:^~[\\/]|^/[\\S]*|^[A-Za-z]:[\\/])")


class SubmissionError(ValueError):
    """Raised when a browser submission crosses the frozen protocol boundary."""


def _read_pack(name: str) -> dict[str, Any]:
    return json.loads((PACKS_DIR / name).read_text(encoding="utf-8"))


def _sanitize_pack(pack: dict[str, Any]) -> dict[str, Any]:
    return {
        "pack_id": pack["pack_id"],
        "records": pack["records"],
        "questions": [
            {
                "id": question["id"],
                "prompt": question["prompt"],
                "choices": question["choices"],
            }
            for question in pack["questions"]
        ],
    }


def _reject_private_values(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in PRIVATE_FIELDS:
                raise SubmissionError("private identity fields are not accepted")
            _reject_private_values(child)
    elif isinstance(value, list):
        for child in value:
            _reject_private_values(child)
    elif isinstance(value, str) and ABSOLUTE_PATH.search(value):
        raise SubmissionError("absolute paths are not accepted")


def _require_exact_keys(value: dict[str, Any], allowed: set[str], context: str) -> None:
    if set(value) != allowed:
        raise SubmissionError(f"incomplete or unexpected {context} fields")


class HumanExperimentStore:
    def __init__(self, results_dir: Path = DEFAULT_RESULTS_DIR):
        self.results_dir = results_dir.resolve()
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self._packs = {pack["pack_id"]: pack for pack in (_read_pack("pack-a.json"), _read_pack("pack-b.json"))}
        self._sessions: dict[str, dict[str, Any]] = {}

    def create_session(self) -> dict[str, Any]:
        order = list(CONDITIONS)
        random.SystemRandom().shuffle(order)
        pack_ids = list(self._packs)
        random.SystemRandom().shuffle(pack_ids)
        session_id = secrets.token_urlsafe(24)
        assignments = [
            {
                "condition": condition,
                "pack_id": pack_id,
                "pack": _sanitize_pack(self._packs[pack_id]),
            }
            for condition, pack_id in zip(order, pack_ids)
        ]
        session = {"session_id": session_id, "condition_order": order, "conditions": assignments}
        self._sessions[session_id] = session
        return session

    def _validated_conditions(self, payload: dict[str, Any], session: dict[str, Any]) -> list[dict[str, Any]]:
        conditions = payload.get("conditions")
        if not isinstance(conditions, list) or len(conditions) != len(CONDITIONS):
            raise SubmissionError("exactly two completed conditions are required")
        if any(not isinstance(item, dict) or not isinstance(item.get("condition"), str) for item in conditions):
            raise SubmissionError("condition entries must have string identifiers")
        by_name = {item["condition"]: item for item in conditions}
        if len(by_name) != len(CONDITIONS) or set(by_name) != set(CONDITIONS):
            raise SubmissionError("each condition must be submitted exactly once")

        expected = {item["condition"]: item for item in session["conditions"]}
        normalized = []
        condition_fields = {
            "condition", "pack_id", "elapsed_ms", "correct", "total", "detail_opens", "answer_changes", "confidence", "events"
        }
        event_fields = {"question_id", "selected_choice", "elapsed_ms"}
        for condition_name in CONDITIONS:
            item = by_name[condition_name]
            _require_exact_keys(item, condition_fields, "condition")
            assignment = expected[condition_name]
            if item["pack_id"] != assignment["pack_id"]:
                raise SubmissionError("condition pack assignment does not match this session")
            for field in ("elapsed_ms", "correct", "total", "detail_opens", "answer_changes", "confidence"):
                if not isinstance(item[field], int) or isinstance(item[field], bool) or item[field] < 0:
                    raise SubmissionError("condition metrics must be non-negative integers")
            if item["elapsed_ms"] == 0 or item["total"] != 5 or not 1 <= item["confidence"] <= 5:
                raise SubmissionError("condition timer, total, or confidence is incomplete")
            events = item["events"]
            questions = assignment["pack"]["questions"]
            if not isinstance(events, list) or len(events) != len(questions):
                raise SubmissionError("all five question events are required")
            if any(
                not isinstance(event, dict)
                or not isinstance(event.get("question_id"), str)
                or not isinstance(event.get("selected_choice"), str)
                for event in events
            ):
                raise SubmissionError("question events must use string identifiers")
            expected_choices = {question["id"]: {choice["id"] for choice in question["choices"]} for question in questions}
            if {event["question_id"] for event in events} != set(expected_choices):
                raise SubmissionError("question events do not match this condition")
            answer_map: dict[str, str] = {}
            for event in events:
                _require_exact_keys(event, event_fields, "event")
                if event["selected_choice"] not in expected_choices[event["question_id"]]:
                    raise SubmissionError("selected choice is not valid for this question")
                if not isinstance(event["elapsed_ms"], int) or isinstance(event["elapsed_ms"], bool) or event["elapsed_ms"] < 0:
                    raise SubmissionError("event timer is invalid")
                answer_map[event["question_id"]] = event["selected_choice"]
            answers = {question["id"]: question["correct_choice"] for question in self._packs[item["pack_id"]]["questions"]}
            normalized.append({**item, "correct": sum(answer_map[key] == answer for key, answer in answers.items())})
        return normalized

    def _private_result_path(self, session_id: str) -> Path:
        path = (self.results_dir / f"{session_id}.json").resolve()
        if path.parent != self.results_dir:
            raise SubmissionError("invalid session identifier")
        return path

    def complete(self, payload: Any) -> dict[str, str]:
        if not isinstance(payload, dict):
            raise SubmissionError("submission must be a JSON object")
        _reject_private_values(payload)
        _require_exact_keys(payload, {"session_id", "condition_order", "conditions"}, "submission")
        session_id = payload.get("session_id")
        session = self._sessions.get(session_id) if isinstance(session_id, str) else None
        if session is None:
            raise SubmissionError("unknown or expired session")
        if payload["condition_order"] != session["condition_order"]:
            raise SubmissionError("condition order does not match this session")
        conditions = self._validated_conditions(payload, session)
        path = self._private_result_path(session_id)
        if path.exists():
            raise SubmissionError("session has already been completed")
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
        data = json.dumps({"conditions": conditions}, ensure_ascii=True, separators=(",", ":"))
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError as error:
                raise SubmissionError("session has already been completed") from error
            temporary.unlink()
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return {"status": "complete"}

    def summary(self, session_id: str) -> dict[str, list[dict[str, Any]]]:
        path = self._private_result_path(session_id)
        if not path.is_file():
            raise SubmissionError("completed session was not found")
        result = json.loads(path.read_text(encoding="utf-8"))
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for condition in result["conditions"]:
            groups[condition["condition"]].append(condition)
        return {
            "conditions": [
                {
                    "condition": name,
                    "runs": len(items),
                    "correct": sum(item["correct"] for item in items),
                    "total": sum(item["total"] for item in items),
                    "elapsed_ms": sum(item["elapsed_ms"] for item in items),
                    "detail_opens": sum(item["detail_opens"] for item in items),
                    "answer_changes": sum(item["answer_changes"] for item in items),
                    "confidence": sum(item["confidence"] for item in items),
                }
                for name, items in sorted(groups.items())
            ]
        }


class HumanExperimentHandler(BaseHTTPRequestHandler):
    store: HumanExperimentStore

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _json(self, status: HTTPStatus, body: Any) -> None:
        encoded = json.dumps(body, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path == "/":
            page = (HUMAN_DIR / "index.html").read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
        elif self.path == "/human/app.js":
            self._static("app.js", "text/javascript; charset=utf-8")
        elif self.path == "/human/styles.css":
            self._static("styles.css", "text/css; charset=utf-8")
        elif self.path == "/api/session":
            self._json(HTTPStatus.OK, self.store.create_session())
        elif self.path.startswith("/api/summary/"):
            self._handle_summary(self.path.removeprefix("/api/summary/"))
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def _static(self, name: str, content_type: str) -> None:
        content = (HUMAN_DIR / name).read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _handle_summary(self, session_id: str) -> None:
        try:
            self._json(HTTPStatus.OK, self.store.summary(session_id))
        except SubmissionError as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def do_POST(self) -> None:
        if self.path != "/api/complete":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0 or content_length > 64_000:
                raise SubmissionError("submission size is invalid")
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            self._json(HTTPStatus.OK, self.store.complete(payload))
        except (UnicodeDecodeError, json.JSONDecodeError, SubmissionError) as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})


def serve(port: int, results_dir: Path = DEFAULT_RESULTS_DIR) -> None:
    handler = type("ConfiguredHumanExperimentHandler", (HumanExperimentHandler,), {"store": HumanExperimentStore(results_dir)})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"human experiment listening on http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the local synthetic human experiment.")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    serve(args.port)
