"""通用 answer-level token F1 evaluator 测试。"""

from __future__ import annotations

import pytest

from memory_benchmark.core import AnswerResult, GoldAnswerInfo, MetricResult, Question
from memory_benchmark.evaluators.f1 import F1Evaluator, normalize_answer


pytestmark = pytest.mark.unit


def _evaluate(
    prediction: str,
    gold: str,
    *,
    question_id: str = "q1",
    category: str | None = None,
) -> MetricResult:
    """构造同 id 的实体并执行通用 F1。"""

    question = Question(
        question_id=question_id,
        conversation_id="c1",
        text="Question?",
        category=category,
    )
    answer = AnswerResult(
        question_id=question_id,
        conversation_id="c1",
        answer=prediction,
    )
    gold_answer = GoldAnswerInfo(question_id=question_id, answer=gold)
    return F1Evaluator().evaluate(question, answer, gold_answer)


def test_normalize_answer_lowercases_and_removes_punctuation_articles() -> None:
    """normalize 应只做小写、去标点/冠词和空白压缩。"""

    assert normalize_answer("  The Tea, and an APPLE!  ") == "tea apple"


def test_generic_f1_uses_unstemmed_tokens() -> None:
    """通用 F1 不得把 running 与 run 通过 stemming 视为同 token。"""

    result = _evaluate("running", "run")

    assert result.score == 0.0
    assert result.details["prediction_tokens"] == ["running"]
    assert result.details["gold_tokens"] == ["run"]


def test_generic_f1_has_no_multi_answer_or_category_special_case() -> None:
    """逗号答案与任意 category 都应走同一标准 token-F1。"""

    result = _evaluate("tea", "tea, coffee", category="1")

    assert result.score == pytest.approx(2 / 3)
    assert result.details["strategy"] == "standard_token_f1"


def test_generic_f1_has_no_adversarial_refusal_rule() -> None:
    """拒答短语不得因 LoCoMo category 规则被特殊判为正确。"""

    result = _evaluate("not mentioned", "passport number", category="5")

    assert result.score == 0.0


def test_generic_f1_marks_abstention_as_framework_supplementary() -> None:
    """LongMemEval abstention 题照常评分并在 details 明确标记。"""

    result = _evaluate(
        "The information is unavailable.",
        "The information is unavailable.",
        question_id="q_abs_1",
    )

    assert result.metric_name == "f1"
    assert result.score == 1.0
    assert result.details["framework_supplementary"] is True
    assert result.details["abstention"] is True
