"""benchmark 无关的 answer-level 补充精确匹配指标（answer-text-v1）。

两个 evaluator 都只读取标准 prediction/private-label artifact，经统一
`run_artifact_evaluation()` 的 answer-level 路径重建实体后逐题计分，不构造
method、不 retrieve、不读取 `.env`：

- `NormalizedExactMatchEvaluator`（CLI `normalized-em`，metric `normalized_em`）：
  预测与 gold 都经 answer-text-v1 归一化后精确相等记 1，否则 0；归一化后 gold
  为空固定记 0，绝不产生空对空的虚假满分。
- `SubstringExactMatchEvaluator`（CLI `substring-em`，metric `substring_em`）：
  方向固定为「归一化 gold 是归一化预测的**连续 token 子序列**」；用 token 而非
  裸字符匹配，避免 `cat` 命中 `concatenate` 之类误判；归一化 gold 为空固定记 0。

两者实现类不读取 benchmark 名，适用面由 registry 决定。
"""

from __future__ import annotations

from memory_benchmark.core import AnswerResult, GoldAnswerInfo, MetricResult, Question

from .answer_text import ANSWER_TEXT_PACK_VERSION, normalize_answer, normalized_tokens


def _is_contiguous_token_subsequence(
    needle: list[str], haystack: list[str]
) -> bool:
    """判断 `needle` 是否为 `haystack` 的连续 token 子序列。

    输入:
        needle: 待匹配的归一化 token 序列（gold）。
        haystack: 被搜索的归一化 token 序列（prediction）。

    输出:
        bool: `needle` 非空且作为一段连续 token 出现在 `haystack` 中返回 True；
        `needle` 为空返回 False（空 gold 的满分由调用方另行拒绝）。
    """

    needle_length = len(needle)
    haystack_length = len(haystack)
    if needle_length == 0 or needle_length > haystack_length:
        return False
    for start in range(haystack_length - needle_length + 1):
        if haystack[start : start + needle_length] == needle:
            return True
    return False


class NormalizedExactMatchEvaluator:
    """归一化精确匹配：answer-text-v1 归一化后两侧完全相等记 1。"""

    metric_name = "normalized_em"

    def evaluate(
        self,
        question: Question,
        answer: AnswerResult,
        gold: GoldAnswerInfo,
    ) -> MetricResult:
        """归一化预测与 gold，精确相等记 1，归一化 gold 为空固定记 0。"""

        normalized_prediction = normalize_answer(answer.answer)
        normalized_gold = normalize_answer(gold.answer)
        empty_normalized_gold = normalized_gold == ""
        if empty_normalized_gold:
            score = 0.0
        else:
            score = 1.0 if normalized_prediction == normalized_gold else 0.0

        return MetricResult(
            metric_name=self.metric_name,
            score=score,
            is_correct=score == 1.0,
            details={
                "question_id": question.question_id,
                "conversation_id": question.conversation_id,
                "answer_question_id": answer.question_id,
                "gold_question_id": gold.question_id,
                "category": question.category,
                "metric_tier": "framework_supplementary",
                "metric_pack_version": ANSWER_TEXT_PACK_VERSION,
                "strategy": "normalized_exact_match",
                "normalized_prediction": normalized_prediction,
                "normalized_gold": normalized_gold,
                "empty_normalized_gold": empty_normalized_gold,
                "framework_supplementary": True,
                "abstention": "_abs" in question.question_id,
            },
        )


class SubstringExactMatchEvaluator:
    """方向固定的子串匹配：归一化 gold 是归一化预测的连续 token 子序列记 1。"""

    metric_name = "substring_em"

    def evaluate(
        self,
        question: Question,
        answer: AnswerResult,
        gold: GoldAnswerInfo,
    ) -> MetricResult:
        """判断归一化 gold 是否为归一化预测的连续 token 子序列。

        方向固定为 `gold_in_prediction`：gold=`Seattle`、
        prediction=`Alice moved to Seattle in 2023` 记 1；反方向记 0；用 token
        边界避免 `cat` 命中 `concatenate`；归一化 gold 为空固定记 0。
        """

        prediction_tokens = normalized_tokens(answer.answer)
        gold_tokens = normalized_tokens(gold.answer)
        empty_normalized_gold = len(gold_tokens) == 0
        if empty_normalized_gold:
            score = 0.0
        else:
            matched = _is_contiguous_token_subsequence(gold_tokens, prediction_tokens)
            score = 1.0 if matched else 0.0

        return MetricResult(
            metric_name=self.metric_name,
            score=score,
            is_correct=score == 1.0,
            details={
                "question_id": question.question_id,
                "conversation_id": question.conversation_id,
                "answer_question_id": answer.question_id,
                "gold_question_id": gold.question_id,
                "category": question.category,
                "metric_tier": "framework_supplementary",
                "metric_pack_version": ANSWER_TEXT_PACK_VERSION,
                "strategy": "gold_in_prediction_substring_em",
                "direction": "gold_in_prediction",
                "prediction_tokens": prediction_tokens,
                "gold_tokens": gold_tokens,
                "empty_normalized_gold": empty_normalized_gold,
                "framework_supplementary": True,
                "abstention": "_abs" in question.question_id,
            },
        )


__all__ = [
    "NormalizedExactMatchEvaluator",
    "SubstringExactMatchEvaluator",
]
