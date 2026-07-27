import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from validate_fixtures import CONDITIONS, TASKS, validate


class ValidateFixturesTest(unittest.TestCase):
    def make_fixture(self, root: Path) -> None:
        fixture = root / "fixtures" / "pilot-01"
        corpus = fixture / "corpus"
        packets = fixture / "retrieval-packets"
        conditions = fixture / "conditions"
        expected = root / "expected"
        prompts = root / "prompts"
        for path in (corpus, packets, conditions, expected, prompts):
            path.mkdir(parents=True, exist_ok=True)

        manifest_tasks = {}
        answers = {}
        rubric = {}
        scores = {
            "static-reference": 4,
            "approved-decision": 6,
            "unresolved-conflict": 6,
            "scope-bound-rule": 6,
            "historical-trace": 6,
        }
        for task in TASKS:
            source = corpus / f"{task}.md"
            source.write_text(
                f"# {task}\n\nEvidence for {task}.\n",
                encoding="utf-8",
            )
            packet = packets / f"{task}.md"
            packet.write_bytes(source.read_bytes())
            manifest_tasks[task] = {
                "query": task.replace("-", " "),
                "top_k": 1,
                "required_sources": [f"{task}.md"],
                "packet": f"{task}.md",
                "packet_bytes": len(packet.read_bytes()),
                "packet_sha256": hashlib.sha256(packet.read_bytes()).hexdigest(),
                "sources": [
                    {
                        "path": f"{task}.md",
                        "bytes": len(source.read_bytes()),
                        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    }
                ],
            }
            (prompts / f"{task}.md").write_text(
                f"请回答编号问题：{task}。\n",
                encoding="utf-8",
            )
            answers[task] = {"sources": [f"{task}.md"]}
            rubric[task] = {
                "max_score": scores[task],
                "items": [f"item-{index}" for index in range(scores[task])],
            }

        (packets / "manifest.json").write_text(
            json.dumps({"tasks": manifest_tasks}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (expected / "answers.json").write_text(
            json.dumps(answers, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (expected / "rubric.json").write_text(
            json.dumps(rubric, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        markers = {
            "rag-only": "当前采用仅检索结果机制",
            "rag-with-recency": "当前采用检索加时间优先机制",
            "memory-governed": "当前采用检索加当前记忆治理机制",
        }
        for condition in CONDITIONS:
            condition_root = conditions / condition
            condition_root.mkdir(parents=True)
            (condition_root / "AGENTS.md").write_text(
                f"# Condition\n\n{markers[condition]}。\n",
                encoding="utf-8",
            )
        current = conditions / "memory-governed" / "memory" / "CURRENT.md"
        current.parent.mkdir()
        current.write_text(
            "# Current memory\n\n| Topic | Status | Source |\n"
            "| --- | --- | --- |\n| demo | active | decision-1 |\n",
            encoding="utf-8",
        )

    def test_accepts_minimal_valid_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.make_fixture(root)
            self.assertEqual(validate(root), [])

    def test_accepts_explicit_fixture_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.make_fixture(root)
            source = root / "fixtures/pilot-01"
            target = root / "fixtures/pilot-02"
            source.rename(target)
            self.assertEqual(validate(root, "pilot-02"), [])

    def test_rejects_manifest_packet_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.make_fixture(root)
            packet = root / "fixtures/pilot-01/retrieval-packets/static-reference.md"
            packet.write_text("changed\n", encoding="utf-8")
            self.assertTrue(any("packet SHA256" in error for error in validate(root)))

    def test_rejects_packet_content_not_assembled_from_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.make_fixture(root)
            packet = root / "fixtures/pilot-01/retrieval-packets/static-reference.md"
            content = packet.read_text(encoding="utf-8") + "invented answer\n"
            packet.write_text(content, encoding="utf-8")
            manifest_path = root / "fixtures/pilot-01/retrieval-packets/manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            entry = manifest["tasks"]["static-reference"]
            entry["packet_bytes"] = len(packet.read_bytes())
            entry["packet_sha256"] = hashlib.sha256(packet.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertTrue(any("corpus sources" in error for error in validate(root)))

    def test_rejects_evidence_copied_into_condition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.make_fixture(root)
            copied = root / "fixtures/pilot-01/conditions/rag-only/evidence.md"
            copied.write_text("copied evidence\n", encoding="utf-8")
            self.assertTrue(any("condition file" in error for error in validate(root)))

    def test_rejects_prompt_leaking_condition_or_expected_answer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.make_fixture(root)
            prompt = root / "prompts/static-reference.md"
            prompt.write_text(
                "Use memory-governed and mark the record active.\n",
                encoding="utf-8",
            )
            errors = validate(root)
            self.assertTrue(any("prompt leaks" in error for error in errors))

    def test_rejects_private_markers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.make_fixture(root)
            source = root / "fixtures/pilot-01/corpus/private.md"
            source.write_text("provider=hidden\n", encoding="utf-8")
            self.assertTrue(any("private-data marker" in error for error in validate(root)))

    def test_rejects_current_memory_copying_corpus_body(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.make_fixture(root)
            source = root / "fixtures/pilot-01/corpus/static-reference.md"
            current = root / "fixtures/pilot-01/conditions/memory-governed/memory/CURRENT.md"
            current.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            self.assertTrue(any("CURRENT.md copies corpus" in error for error in validate(root)))

    def test_rejects_rubric_total_other_than_twenty_eight(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.make_fixture(root)
            path = root / "expected/rubric.json"
            rubric = json.loads(path.read_text(encoding="utf-8"))
            rubric["static-reference"]["max_score"] = 5
            path.write_text(json.dumps(rubric), encoding="utf-8")
            self.assertTrue(any("rubric total" in error for error in validate(root)))


if __name__ == "__main__":
    unittest.main()
