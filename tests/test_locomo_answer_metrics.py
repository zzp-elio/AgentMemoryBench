"""测试 LoCoMo 官方 QA F1 evaluator。

本文件验证 `memory_benchmark.evaluators.locomo_f1.LoCoMoF1Evaluator` 是否
复刻 LoCoMo 官方 `task_eval/evaluation.py` 中的 QA F1 逻辑。测试重点包括
normalization、Porter stemming、category 1 多答案拆分，以及 category 5
adversarial 的特殊判断。
"""

import unittest

import pytest

from memory_benchmark.core.entities import AnswerResult, GoldAnswerInfo, Question
from memory_benchmark.evaluators.locomo_f1 import LoCoMoF1Evaluator


pytestmark = pytest.mark.unit


def make_inputs(
    prediction: str,
    gold_answer: str,
    category: str | None = "2",
) -> tuple[Question, AnswerResult, GoldAnswerInfo]:
    """构造单题 evaluator 输入。

    输入:
        prediction: method 生成的答案文本。
        gold_answer: evaluator 私有标准答案文本。
        category: LoCoMo QA category；`1` 是 multi-hop 多答案，`2/3/4` 是普通
            QA F1，`5` 是 adversarial。

    输出:
        tuple: 公开 Question、method AnswerResult 和私有 GoldAnswerInfo。
    """

    question = Question(
        question_id="q-1",
        conversation_id="conversation-1",
        text="Where did Alice move?",
        category=category,
    )
    answer = AnswerResult(
        question_id=question.question_id,
        conversation_id=question.conversation_id,
        answer=prediction,
    )
    gold = GoldAnswerInfo(question_id=question.question_id, answer=gold_answer)
    return question, answer, gold


class LoCoMoF1EvaluatorTests(unittest.TestCase):
    """验证 LoCoMo 官方答案级 F1 的核心行为。"""

    def setUp(self):
        """为每个测试创建独立 evaluator。"""

        self.evaluator = LoCoMoF1Evaluator()

    def evaluate_score(self, prediction: str, gold_answer: str) -> float:
        """返回单题 F1 分数，减少测试样板代码。

        输入:
            prediction: method 生成的答案文本。
            gold_answer: evaluator 私有标准答案文本。

        输出:
            float: evaluator 返回的 metric score。
        """

        question, answer, gold = make_inputs(prediction, gold_answer)
        return self.evaluator.evaluate(question, answer, gold).score

    def test_exact_match_gets_full_score(self):
        """完全匹配时 F1 应为 1.0。"""

        score = self.evaluate_score("Seattle", "Seattle")

        self.assertEqual(score, 1.0)

    def test_partial_overlap_gets_between_zero_and_one(self):
        """部分 token 重叠时 F1 应大于 0 且小于 1。"""

        score = self.evaluate_score("Alice moved to Seattle", "Seattle in 2023")

        self.assertGreater(score, 0.0)
        self.assertLess(score, 1.0)

    def test_no_overlap_gets_zero(self):
        """没有 token 重叠时 F1 应为 0。"""

        score = self.evaluate_score("Paris", "Seattle")

        self.assertEqual(score, 0.0)

    def test_normalization_ignores_case_punctuation_articles_and_and_whitespace(self):
        """normalization 应忽略大小写、标点、英文冠词、and 和多余空白。"""

        result = self.evaluator.evaluate(*make_inputs("  THE Seattle, and apartment!  ", "seattle apartment"))

        self.assertEqual(result.score, 1.0)
        self.assertEqual(result.details["normalized_prediction"], "seattle apartment")
        self.assertEqual(result.details["normalized_gold"], "seattle apartment")

    def test_porter_stemming_matches_official_locomo_f1(self):
        """LoCoMo 官方 F1 会对 token 做 Porter stemming。"""

        result = self.evaluator.evaluate(*make_inputs("running", "runs"))

        self.assertEqual(result.score, 1.0)
        self.assertEqual(result.details["prediction_tokens"], ["run"])
        self.assertEqual(result.details["gold_tokens"], ["run"])

    def test_category_one_splits_multi_answer_phrases_by_comma(self):
        """category 1 应按逗号拆多答案，并对每个 gold 子答案取最佳匹配。"""

        result = self.evaluator.evaluate(
            *make_inputs(
                prediction="Seattle, Portland",
                gold_answer="Portland, Seattle",
                category="1",
            )
        )

        self.assertEqual(result.score, 1.0)
        self.assertEqual(result.details["category"], "1")
        self.assertEqual(result.details["strategy"], "multi_answer_f1")

    def test_category_five_adversarial_uses_no_information_rule(self):
        """category 5 adversarial 按 LoCoMo 官方规则判断是否拒答。"""

        accepted = self.evaluator.evaluate(
            *make_inputs(
                prediction="No information available in the conversation.",
                gold_answer="irrelevant",
                category="5",
            )
        )
        rejected = self.evaluator.evaluate(
            *make_inputs(
                prediction="Alice moved to Seattle.",
                gold_answer="irrelevant",
                category="5",
            )
        )

        self.assertEqual(accepted.score, 1.0)
        self.assertEqual(rejected.score, 0.0)

    def test_category_three_strips_gold_rationale_after_semicolon(self):
        """category 3 应按官方逻辑去掉 gold answer 分号后的解释再评分。"""

        result = self.evaluator.evaluate(
            *make_inputs(
                prediction="Likely no",
                gold_answer="Likely no; although Alice sounded uncertain in the dialogue",
                category="3",
            )
        )

        self.assertEqual(result.score, 1.0)
        self.assertEqual(result.details["normalized_gold"], "likely no")

    def test_empty_prediction_and_gold_behavior_follows_official_code(self):
        """官方 F1 中空预测或空标准答案都返回 0。"""

        both_empty = self.evaluator.evaluate(*make_inputs("", ""))
        empty_prediction = self.evaluator.evaluate(*make_inputs("", "Seattle"))
        empty_gold = self.evaluator.evaluate(*make_inputs("Seattle", ""))

        self.assertEqual(both_empty.score, 0.0)
        self.assertEqual(both_empty.details["precision"], 0.0)
        self.assertEqual(both_empty.details["recall"], 0.0)
        self.assertEqual(empty_prediction.score, 0.0)
        self.assertEqual(empty_gold.score, 0.0)

    def test_metric_details_include_debug_fields(self):
        """details 应包含排查单题分数所需的基础信息。"""

        result = self.evaluator.evaluate(*make_inputs("Seattle apartment", "Seattle home"))

        self.assertEqual(result.metric_name, "locomo_f1")
        self.assertIn("normalized_prediction", result.details)
        self.assertIn("normalized_gold", result.details)
        self.assertIn("precision", result.details)
        self.assertIn("recall", result.details)


if __name__ == "__main__":
    unittest.main()
