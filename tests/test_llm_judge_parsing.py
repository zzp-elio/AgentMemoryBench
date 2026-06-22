"""LLM judge 输出解析和 prompt 构造测试。

这些测试只覆盖本地解析与 prompt 文本，不发起真实 OpenAI API 请求。
"""

from __future__ import annotations

import unittest

import pytest

from memory_benchmark.core import AnswerResult, GoldAnswerInfo, Question
from memory_benchmark.core.exceptions import JudgeOutputError
from memory_benchmark.evaluators.llm_judge import JudgeDecision, parse_judge_response
from memory_benchmark.evaluators.locomo_judge import LoCoMoJudgeEvaluator
from memory_benchmark.evaluators.longmemeval_judge import LongMemEvalJudgeEvaluator


pytestmark = pytest.mark.unit


class JudgeResponseParsingTest(unittest.TestCase):
    """验证 judge 原始输出能被严格解析为统一决策。"""

    def test_parse_compact_true_and_false(self) -> None:
        """compact 模式只接受去空白、忽略大小写后的 true/false。"""

        self.assertEqual(
            parse_judge_response(" TRUE \n", mode="compact"),
            JudgeDecision(is_correct=True),
        )
        self.assertEqual(
            parse_judge_response("\tfalse ", mode="compact"),
            JudgeDecision(is_correct=False),
        )

    def test_parse_detailed_json_with_reason(self) -> None:
        """detailed 模式读取 JSON 对象里的 is_correct 和可选 reason。"""

        decision = parse_judge_response(
            '{"is_correct": true, "reason": "预测答案覆盖了标准答案。"}',
            mode="detailed",
        )

        self.assertEqual(
            decision,
            JudgeDecision(is_correct=True, reason="预测答案覆盖了标准答案。"),
        )

    def test_invalid_compact_output_raises(self) -> None:
        """compact 模式遇到 true/false 之外的文本应抛 judge 输出错误。"""

        with self.assertRaises(JudgeOutputError):
            parse_judge_response("yes", mode="compact")

    def test_invalid_detailed_json_raises(self) -> None:
        """detailed 模式遇到非法 JSON 应抛 judge 输出错误。"""

        with self.assertRaises(JudgeOutputError):
            parse_judge_response("not-json", mode="detailed")

    def test_non_bool_is_correct_raises(self) -> None:
        """detailed 模式要求 is_correct 必须是布尔值。"""

        with self.assertRaises(JudgeOutputError):
            parse_judge_response('{"is_correct": "true", "reason": "bad type"}', mode="detailed")

    def test_null_reason_raises_when_reason_field_is_present(self) -> None:
        """detailed 模式中 reason 如果出现，就必须是字符串，不能是 null。"""

        with self.assertRaises(JudgeOutputError):
            parse_judge_response('{"is_correct": true, "reason": null}', mode="detailed")


class JudgePromptBuilderTest(unittest.TestCase):
    """验证 benchmark-specific shell 只构造 prompt，不读取或泄漏 API key。"""

    def setUp(self) -> None:
        """准备公开问题、method 预测和 evaluator 私有标准答案。"""

        self.question = Question(
            question_id="q1",
            conversation_id="conv1",
            text="What tea does Alice prefer?",
        )
        self.prediction = AnswerResult(
            question_id="q1",
            conversation_id="conv1",
            answer="Alice prefers green tea.",
        )
        self.gold = GoldAnswerInfo(question_id="q1", answer="green tea")

    def test_locomo_prompt_includes_inputs_without_api_key(self) -> None:
        """LoCoMo judge prompt 应包含题目、预测和标准答案，但不包含 API key。"""

        prompt = LoCoMoJudgeEvaluator().build_prompt(
            self.question,
            self.prediction,
            self.gold,
        )

        self.assertIn("label an answer", prompt)
        self.assertIn(self.question.text, prompt)
        self.assertIn(self.prediction.answer, prompt)
        self.assertIn(self.gold.answer, prompt)
        self.assertNotIn("sk-test-secret", prompt)
        self.assertNotIn("OPENAI", prompt.upper())

    def test_longmemeval_prompt_includes_inputs_without_api_key(self) -> None:
        """LongMemEval prompt 应包含官方 common QA 规则和三类输入。"""

        prompt = LongMemEvalJudgeEvaluator().build_prompt(
            self.question,
            self.prediction,
            self.gold,
        )

        self.assertIn("If the response only contains a subset", prompt)
        self.assertIn(self.question.text, prompt)
        self.assertIn(self.prediction.answer, prompt)
        self.assertIn(self.gold.answer, prompt)
        self.assertNotIn("sk-test-secret", prompt)
        self.assertNotIn("OPENAI", prompt.upper())

    def test_locomo_compact_prompt_requests_true_false_not_json(self) -> None:
        """LoCoMo compact 模式的 prompt 必须和 CORRECT/WRONG parser 对齐。"""

        prompt = LoCoMoJudgeEvaluator(mode="compact").build_prompt(
            self.question,
            self.prediction,
            self.gold,
        )

        self.assertIn("CORRECT", prompt)
        self.assertIn("WRONG", prompt)
        self.assertNotIn("Return JSON", prompt)
        self.assertNotIn("is_correct", prompt)

    def test_longmemeval_compact_prompt_requests_true_false_not_json(self) -> None:
        """LongMemEval compact 模式的 prompt 必须和 true/false parser 对齐。"""

        prompt = LongMemEvalJudgeEvaluator(mode="compact").build_prompt(
            self.question,
            self.prediction,
            self.gold,
        )

        self.assertIn("true", prompt.lower())
        self.assertIn("false", prompt.lower())
        self.assertNotIn("Return JSON", prompt)
        self.assertNotIn("is_correct", prompt)

    def test_longmemeval_temporal_prompt_allows_off_by_one_errors(self) -> None:
        """temporal-reasoning 分支应迁移官方 off-by-one 容错规则。"""

        temporal_question = Question(
            question_id="q-temporal",
            conversation_id="conv1",
            text="How many days passed?",
            category="temporal-reasoning",
        )

        prompt = LongMemEvalJudgeEvaluator(mode="compact").build_prompt(
            temporal_question,
            self.prediction,
            self.gold,
        )

        self.assertIn("do not penalize off-by-one errors", prompt)
        self.assertIn("19 days when the answer is 18", prompt)
        self.assertIn("Return exactly one lowercase word: true or false.", prompt)

    def test_longmemeval_knowledge_update_prompt_allows_previous_information(
        self,
    ) -> None:
        """knowledge-update 分支应迁移官方“旧信息+更新答案”规则。"""

        update_question = Question(
            question_id="q-update",
            conversation_id="conv1",
            text="Where does Alice live now?",
            category="knowledge-update",
        )

        prompt = LongMemEvalJudgeEvaluator(mode="compact").build_prompt(
            update_question,
            self.prediction,
            self.gold,
        )

        self.assertIn("previous information along with an updated answer", prompt)
        self.assertIn("updated answer is the required answer", prompt)

    def test_longmemeval_preference_prompt_uses_rubric_wording(self) -> None:
        """single-session-preference 分支应把 gold answer 当作 personalized rubric。"""

        preference_question = Question(
            question_id="q-preference",
            conversation_id="conv1",
            text="Recommend a drink for Alice.",
            category="single-session-preference",
        )

        prompt = LongMemEvalJudgeEvaluator(mode="compact").build_prompt(
            preference_question,
            self.prediction,
            self.gold,
        )

        self.assertIn("rubric for desired personalized response", prompt)
        self.assertIn("Rubric: green tea", prompt)
        self.assertIn("utilizes the user's personal information correctly", prompt)

    def test_longmemeval_abstention_prompt_uses_unanswerable_rule(self) -> None:
        """question_id 含 `_abs` 时应走官方不可回答题判分规则。"""

        abstention_question = Question(
            question_id="q_abs_1",
            conversation_id="conv1",
            text="What is Alice's passport number?",
            category="single-session-user",
        )
        gold = GoldAnswerInfo(
            question_id="q_abs_1",
            answer="The conversation never mentions Alice's passport number.",
        )

        prompt = LongMemEvalJudgeEvaluator(mode="compact").build_prompt(
            abstention_question,
            self.prediction,
            gold,
        )

        self.assertIn("unanswerable question", prompt)
        self.assertIn("Explanation:", prompt)
        self.assertIn("correctly identify the question as unanswerable", prompt)


if __name__ == "__main__":
    unittest.main()
