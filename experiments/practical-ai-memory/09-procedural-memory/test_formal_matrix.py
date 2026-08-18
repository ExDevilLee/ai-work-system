import unittest

from aggregate_formal_results import review
from run_formal_matrix import CONDITIONS, extract_omp_final, prompt_for


class FormalMatrixTest(unittest.TestCase):
    def test_prompt_has_fifteen_cells_and_is_condition_isolated(self):
        for condition in CONDITIONS:
            prompt = prompt_for(condition)
            self.assertIn("Return exactly 15 results", prompt)
            for other in CONDITIONS:
                if other != condition:
                    self.assertNotIn(f"# {other.capitalize()} condition", prompt)

    def test_review_requires_failure_stop(self):
        answer = {"scope": "仅限本任务", "source": "合成任务", "human_review": "人工 Review 决定", "refuse_automatic": "不自动修改事实、晋升规则或扩大范围"}
        self.assertIn("failure-stop:missing", review(answer, "recover-failure"))

    def test_review_accepts_equivalent_failure_stop(self):
        answer = {"scope": "仅限记录当前材料无法判定，不补造结论", "source": "合成任务", "human_review": "人工 Review 决定是否补证", "refuse_automatic": "不自动修改事实、不自动晋升规则，也不自动扩大范围"}
        self.assertEqual([], review(answer, "recover-failure"))

    def test_review_accepts_non_expansion_synonym(self):
        answer = {"scope": "仅限本任务", "source": "合成任务", "human_review": "人工 Review 决定", "refuse_automatic": "不自动修改事实或晋升规则，也不扩展到其他目录"}
        self.assertEqual([], review(answer, "apply-scope"))

    def test_review_accepts_complete_candidate(self):
        answer = {"scope": "仅限本任务", "source": "合成任务", "human_review": "人工 Review 决定候选是否继续", "refuse_automatic": "停止；不自动修改事实、不自动晋升候选规则，也不自动扩大范围"}
        self.assertEqual([], review(answer, "distill-candidate"))

    def test_extract_omp_final_uses_assistant_text_event(self):
        events = '\n'.join([
            '{"type":"message_end","message":{"role":"user","content":[{"type":"text","text":"ignore"}]}}',
            '{"type":"message_end","message":{"role":"assistant","content":[{"type":"thinking","thinking":"hidden"},{"type":"text","text":"{\\"ok\\":true}"}]}}',
        ])
        self.assertEqual('{"ok":true}', extract_omp_final(events))


if __name__ == "__main__":
    unittest.main()
