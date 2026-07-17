"""跨 benchmark 的标准 answer-level token F1 evaluator。

归一化复用 `answer_text.py::normalize_answer`（answer-text-v1 唯一实现）；
本模块继续 re-export `normalize_answer` 以兼容旧 import 路径。F1 的计分数字
不因收敛归一化器而改变，score details 额外携带 metric pack 稳定身份。
"""

from __future__ import annotations

from collections import Counter

from memory_benchmark.core import AnswerResult, GoldAnswerInfo, MetricResult, Question

from .answer_text import ANSWER_TEXT_PACK_VERSION, normalize_answer


class F1Evaluator:
    """计算无 benchmark/category 特判的标准 token F1。"""

    metric_name = "f1"

    def evaluate(
        self,
        question: Question,
        answer: AnswerResult,
        gold: GoldAnswerInfo,
    ) -> MetricResult:
        """归一化预测与 gold，按 token 重叠计算 precision/recall/F1。"""

        normalized_prediction = normalize_answer(answer.answer)
        normalized_gold = normalize_answer(gold.answer)
        prediction_tokens = normalized_prediction.split()
        gold_tokens = normalized_gold.split()
        common_tokens = Counter(prediction_tokens) & Counter(gold_tokens)
        common_count = sum(common_tokens.values())

        if common_count == 0:
            precision = recall = score = 0.0
        else:
            precision = common_count / len(prediction_tokens)
            recall = common_count / len(gold_tokens)
            score = 2 * precision * recall / (precision + recall)

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
                "strategy": "standard_token_f1",
                "normalized_prediction": normalized_prediction,
                "normalized_gold": normalized_gold,
                "prediction_tokens": prediction_tokens,
                "gold_tokens": gold_tokens,
                "common_tokens": dict(common_tokens),
                "common_token_count": common_count,
                "precision": precision,
                "recall": recall,
                "framework_supplementary": True,
                "abstention": "_abs" in question.question_id,
            },
        )


__all__ = ["F1Evaluator", "normalize_answer"]
