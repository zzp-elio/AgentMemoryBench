"""MemBench 选择题准确率 evaluator。

本模块只执行离线 deterministic exact match：prediction 必须是 A/B/C/D，
并与 `GoldAnswerInfo.metadata["ground_truth"]` 一致才记 1 分。
"""

from __future__ import annotations

from typing import Any

from memory_benchmark.core import AnswerResult, GoldAnswerInfo, MetricResult, Question


class MemBenchChoiceAccuracyEvaluator:
    """计算 MemBench 单题 choice accuracy。"""

    metric_name = "membench_choice_accuracy"

    def evaluate(
        self,
        question: Question,
        answer: AnswerResult,
        gold: GoldAnswerInfo,
    ) -> MetricResult:
        """评估单个 MemBench 选择题答案。

        输入:
            question: 公开问题，用于读取 category/question_type。
            answer: prediction artifact 中的公开答案，应已由 T3 parser 规整。
            gold: evaluator 私有标签，包含 ground_truth。

        输出:
            MetricResult: score 为 0/1，details 包含分类与 normalized label。
        """

        prediction = _normalize_choice(answer.answer)
        ground_truth = _gold_choice(gold)
        is_valid_prediction = prediction in {"A", "B", "C", "D"}
        is_correct = is_valid_prediction and prediction == ground_truth
        # 官方判定（third_party/benchmarks/Membench-main/benchmark/MembenchAgent.py:93-113）
        # 用 json_schema enum A-D 强约束 + `json.loads(res)['choice']` 与 ground_truth
        # 精确比较。本 evaluator 在统一管线里用自由文本 + 健壮 parser 替代（见
        # parse_membench_choice / normalize_membench_choice_prediction）。审计时两类
        # 口径分开统计：解析成功 → 字母精确比较；解析失败（invalid_choice）→ 记
        # parse_failed=true 供后续官方 parity 复核。
        parse_failed = prediction == "invalid_choice" or not is_valid_prediction
        return MetricResult(
            metric_name=self.metric_name,
            score=1.0 if is_correct else 0.0,
            is_correct=is_correct,
            details={
                "question_id": question.question_id,
                "conversation_id": question.conversation_id,
                "answer_question_id": answer.question_id,
                "gold_question_id": gold.question_id,
                "category": question.category,
                "prediction": prediction,
                "ground_truth": ground_truth,
                "valid_prediction": is_valid_prediction,
                "parse_failed": parse_failed,
            },
        )


def _gold_choice(gold: GoldAnswerInfo) -> str:
    """读取 MemBench 私有 ground_truth choice。"""

    raw_choice: Any = gold.metadata.get("ground_truth", gold.answer)
    return _normalize_choice(raw_choice)


def _normalize_choice(value: Any) -> str:
    """把任意输入规整为大写 choice 文本；空值返回空字符串。"""

    return str(value or "").strip().upper()
