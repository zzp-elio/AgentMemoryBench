"""标准词袋 Token-Level F1 评估器 (`F1Evaluator`)。"""

from __future__ import annotations

from collections import Counter

from memory_benchmark.core import (
    AnswerResult,
    GoldAnswerInfo,
    MetricResult,
    Question,
)

from .exact_match import normalize_answer


def normalized_tokens(text: str) -> list[str]:
    """返回归一化后的 Token 列表。"""
    norm = normalize_answer(text)
    return norm.split() if norm else []


class F1Evaluator:
    """标准词袋 Token-Level F1 评估器（零 API 成本离线基线）。"""

    metric_name = "f1"

    def evaluate(
        self,
        question: Question,
        answer: AnswerResult,
        gold: GoldAnswerInfo,
    ) -> MetricResult:
        pred_tokens = normalized_tokens(answer.answer)
        gold_tokens = normalized_tokens(gold.answer)
        common = Counter(pred_tokens) & Counter(gold_tokens)
        num_same = sum(common.values())

        if not pred_tokens and not gold_tokens:
            score, precision, recall = 1.0, 1.0, 1.0
        elif num_same == 0:
            score, precision, recall = 0.0, 0.0, 0.0
        else:
            precision = num_same / len(pred_tokens)
            recall = num_same / len(gold_tokens)
            score = (2 * precision * recall) / (precision + recall)

        return MetricResult(
            metric_name=self.metric_name,
            score=score,
            is_correct=score == 1.0,
            details={
                "question_id": question.question_id,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
            },
        )


__all__ = [
    "F1Evaluator",
    "normalized_tokens",
]
