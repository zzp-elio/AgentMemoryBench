"""LoCoMo 官方 QA F1 evaluator。

本模块复刻 LoCoMo 官方仓库 `task_eval/evaluation.py` 的 QA F1 逻辑，只计算
answer-level 分数，不实现检索召回或 LLM judge。category 1 使用多答案 F1，
category 2/3/4 使用普通 token F1，category 3 会先去掉 gold answer 分号后的
解释，category 5 使用 adversarial 拒答规则。
"""

from __future__ import annotations

import re
import string
from collections import Counter
from typing import Any

import numpy as np
from nltk.stem import PorterStemmer

from memory_benchmark.core.entities import (
    AnswerResult,
    GoldAnswerInfo,
    MetricResult,
    Question,
)


_ARTICLE_PATTERN = re.compile(r"\b(a|an|the|and)\b")
_PUNCTUATION_TRANSLATION = str.maketrans("", "", string.punctuation)
_PORTER_STEMMER = PorterStemmer()


class LoCoMoF1Evaluator:
    """计算 LoCoMo 官方 answer-level QA F1。

    输入:
        Question、AnswerResult、GoldAnswerInfo 三个 conversation-QA v2 对象。

    输出:
        MetricResult，其中 score 是单题 F1，details 包含 category、normalized 文本、
        stemmed tokens、precision/recall 等调试字段。
    """

    metric_name = "locomo_f1"

    def evaluate(
        self,
        question: Question,
        answer: AnswerResult,
        gold: GoldAnswerInfo,
    ) -> MetricResult:
        """评估单个问题的预测答案。

        输入:
            question: method 可见的公开问题，仅用于记录 question/conversation id。
            answer: method 返回的公开答案。
            gold: evaluator 私有标准答案。

        输出:
            MetricResult: 单题 F1 分数和调试细节。
        """

        category = _normalize_category(question.category)
        if category == "5":
            score = _adversarial_score(answer.answer)
            precision = score
            recall = score
            normalized_prediction = normalize_qa_answer(answer.answer)
            normalized_gold = normalize_qa_answer(gold.answer)
            prediction_tokens = _stemmed_tokens(normalized_prediction)
            gold_tokens = _stemmed_tokens(normalized_gold)
            common_tokens: Counter[str] = Counter()
            strategy = "adversarial_no_information"
        elif category == "1":
            score, precision, recall, common_tokens, prediction_tokens, gold_tokens = (
                _multi_answer_f1(answer.answer, gold.answer)
            )
            normalized_prediction = normalize_qa_answer(answer.answer)
            normalized_gold = normalize_qa_answer(gold.answer)
            strategy = "multi_answer_f1"
        else:
            scoring_gold_answer = _gold_answer_for_category(gold.answer, category)
            normalized_prediction = normalize_qa_answer(answer.answer)
            normalized_gold = normalize_qa_answer(scoring_gold_answer)
            prediction_tokens = _stemmed_tokens(normalized_prediction)
            gold_tokens = _stemmed_tokens(normalized_gold)
            score, precision, recall, common_tokens = _token_f1(
                prediction_tokens,
                gold_tokens,
            )
            strategy = "single_answer_f1"

        return MetricResult(
            metric_name=self.metric_name,
            score=score,
            is_correct=score == 1.0,
            details={
                "question_id": question.question_id,
                "conversation_id": question.conversation_id,
                "answer_question_id": answer.question_id,
                "gold_question_id": gold.question_id,
                "category": category,
                "strategy": strategy,
                "normalized_prediction": normalized_prediction,
                "normalized_gold": normalized_gold,
                "prediction_tokens": prediction_tokens,
                "gold_tokens": gold_tokens,
                "common_tokens": dict(common_tokens),
                "common_token_count": sum(common_tokens.values()),
                "precision": precision,
                "recall": recall,
            },
        )


def normalize_qa_answer(text: Any) -> str:
    """执行 LoCoMo 官方 QA F1 normalization。

    输入:
        text: prediction 或 gold answer。None 会按空字符串处理，其他类型会转为
        字符串以避免 evaluator 因边界数据崩溃。

    输出:
        str: 小写、去逗号、去标点、去 `a/an/the/and` 并压缩空白后的文本。
    """

    if text is None:
        value = ""
    else:
        value = str(text)

    without_commas = value.replace(",", "")
    lowered = without_commas.lower()
    without_punctuation = lowered.translate(_PUNCTUATION_TRANSLATION)
    without_articles = _ARTICLE_PATTERN.sub(" ", without_punctuation)
    return " ".join(without_articles.split())


def _stemmed_tokens(normalized_text: str) -> list[str]:
    """将已 normalized 的答案切成 token 并做 Porter stemming。

    输入:
        normalized_text: normalize_qa_answer 的输出。

    输出:
        list[str]: LoCoMo 官方 F1 使用的 stemmed token 列表。
    """

    if not normalized_text:
        return []
    return [_PORTER_STEMMER.stem(word) for word in normalized_text.split()]


def _token_f1(
    prediction_tokens: list[str],
    gold_tokens: list[str],
) -> tuple[float, float, float, Counter[str]]:
    """根据 token overlap 计算 F1、precision 和 recall。

    输入:
        prediction_tokens: 预测答案 token。
        gold_tokens: 标准答案 token。

    输出:
        tuple: F1、precision、recall 和重叠 token 计数。与 LoCoMo 官方代码保持
        一致，只要没有 token overlap 就返回 0，包括两侧都为空的情况。
    """

    common_tokens = Counter(prediction_tokens) & Counter(gold_tokens)
    common_token_count = sum(common_tokens.values())
    if common_token_count == 0:
        return 0.0, 0.0, 0.0, common_tokens

    precision = common_token_count / len(prediction_tokens)
    recall = common_token_count / len(gold_tokens)
    f1 = (2 * precision * recall) / (precision + recall)
    return f1, precision, recall, common_tokens


def _multi_answer_f1(
    prediction: Any,
    gold_answer: Any,
) -> tuple[float, float, float, Counter[str], list[str], list[str]]:
    """计算 LoCoMo category 1 的多答案 F1。

    输入:
        prediction: method 输出答案，按英文逗号拆为多个候选子答案。
        gold_answer: 标准答案，按英文逗号拆为多个 gold 子答案。

    输出:
        tuple: 平均 F1、用于调试的平均 precision/recall、合并 overlap、
        normalized 后的 prediction/gold stemmed tokens。
    """

    predictions = [part.strip() for part in str(prediction or "").split(",")]
    gold_parts = [part.strip() for part in str(gold_answer or "").split(",")]
    best_scores: list[float] = []
    best_precisions: list[float] = []
    best_recalls: list[float] = []
    merged_common_tokens: Counter[str] = Counter()

    for gold_part in gold_parts:
        gold_tokens = _stemmed_tokens(normalize_qa_answer(gold_part))
        candidate_results = []
        for prediction_part in predictions:
            prediction_tokens = _stemmed_tokens(normalize_qa_answer(prediction_part))
            candidate_results.append(_token_f1(prediction_tokens, gold_tokens))
        best_f1, best_precision, best_recall, best_common = max(
            candidate_results,
            key=lambda result: result[0],
        )
        best_scores.append(best_f1)
        best_precisions.append(best_precision)
        best_recalls.append(best_recall)
        merged_common_tokens.update(best_common)

    all_prediction_tokens = _stemmed_tokens(normalize_qa_answer(prediction))
    all_gold_tokens = _stemmed_tokens(normalize_qa_answer(gold_answer))
    return (
        float(np.mean(best_scores)) if best_scores else 0.0,
        float(np.mean(best_precisions)) if best_precisions else 0.0,
        float(np.mean(best_recalls)) if best_recalls else 0.0,
        merged_common_tokens,
        all_prediction_tokens,
        all_gold_tokens,
    )


def _adversarial_score(prediction: Any) -> float:
    """计算 LoCoMo category 5 adversarial 分数。

    输入:
        prediction: method 输出答案。

    输出:
        float: 包含官方拒答短语时为 1，否则为 0。
    """

    lowered = str(prediction or "").lower()
    if "no information available" in lowered or "not mentioned" in lowered:
        return 1.0
    return 0.0


def _gold_answer_for_category(gold_answer: Any, category: str | None) -> str:
    """按 LoCoMo 官方 category 规则返回实际参与评分的 gold answer。

    输入:
        gold_answer: 原始标准答案。
        category: LoCoMo category 字符串。

    输出:
        str: category 3 会截断分号后的解释，其余 category 原样转字符串。
    """

    answer_text = str(gold_answer or "")
    if category == "3":
        return answer_text.split(";")[0].strip()
    return answer_text


def _normalize_category(category: Any) -> str | None:
    """把 Question.category 转成统一字符串。

    输入:
        category: adapter 中可能保存为 str、int 或 None。

    输出:
        str | None: 去空白后的 category；缺失时返回 None。
    """

    if category is None:
        return None
    category_text = str(category).strip()
    return category_text or None
