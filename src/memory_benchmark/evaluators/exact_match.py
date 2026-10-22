"""通用精确匹配评估器 (`ExactMatchEvaluator`)。

同时支持：
1. 常规问答文本归一化精确匹配（转小写、去标点、去冠词 `a/an/the`、合并空白）；
2. 单字母选择题（如 MemBench `A/B/C/D`）选项提取与精准判分。
"""

from __future__ import annotations

import re
import string

from memory_benchmark.core import (
    AnswerResult,
    GoldAnswerInfo,
    MetricResult,
    Question,
)

_ARTICLES_RE = re.compile(r"\b(a|an|the)\b", re.IGNORECASE)
_PUNCT_TABLE = str.maketrans("", "", string.punctuation)
_CHOICE_LETTER_RE = re.compile(r"^\s*[\(\[]?([A-Da-d])[\)\]\.\s:,-]*$")


def normalize_answer(text: str) -> str:
    """标准 QA 文本归一化：转小写、去标点、去冠词 (`a/an/the`)、合并多余空白。"""
    lowered = (text or "").lower()
    no_punct = lowered.translate(_PUNCT_TABLE)
    no_articles = _ARTICLES_RE.sub(" ", no_punct)
    return " ".join(no_articles.split())


class ExactMatchEvaluator:
    """通用精确匹配评估器（同时支持常规问答与 MemBench 单字母选择题判分）。"""

    metric_name = "exact_match"

    def evaluate(
        self,
        question: Question,
        answer: AnswerResult,
        gold: GoldAnswerInfo,
    ) -> MetricResult:
        pred_raw = (answer.answer or "").strip()
        gold_choice = str(gold.metadata.get("ground_truth") or "").strip().upper()
        if gold_choice in {"A", "B", "C", "D"}:
            m = _CHOICE_LETTER_RE.match(pred_raw)
            pred_choice = m.group(1).upper() if m else pred_raw[:1].upper()
            matched = pred_choice == gold_choice
            return MetricResult(
                metric_name=self.metric_name,
                score=1.0 if matched else 0.0,
                is_correct=matched,
                details={
                    "question_id": question.question_id,
                    "mode": "multiple_choice",
                    "predicted_choice": pred_choice,
                    "gold_choice": gold_choice,
                },
            )

        norm_pred = normalize_answer(pred_raw)
        norm_gold = normalize_answer(gold.answer)
        matched = bool(norm_gold) and (norm_pred == norm_gold)
        return MetricResult(
            metric_name=self.metric_name,
            score=1.0 if matched else 0.0,
            is_correct=matched,
            details={
                "question_id": question.question_id,
                "mode": "normalized_text",
                "normalized_prediction": norm_pred,
                "normalized_gold": norm_gold,
            },
        )


__all__ = [
    "ExactMatchEvaluator",
    "normalize_answer",
]
