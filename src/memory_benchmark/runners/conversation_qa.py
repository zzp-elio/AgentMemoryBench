"""conversation-QA v2 同步答题 runner。

本模块只负责 answer-level 评测闭环：校验 Dataset、把公开 conversation
写入 method、逐题取 answer，并在 runner 内部把私有 GoldAnswerInfo 交给 evaluator。
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from typing import Protocol

from memory_benchmark.core import (
    AnswerResult,
    Conversation,
    Dataset,
    EvaluationResult,
    GoldAnswerInfo,
    ImageRef,
    MetricResult,
    Question,
    Session,
    Turn,
)
from memory_benchmark.core.interfaces import BaseMemorySystem
from memory_benchmark.core.validators import validate_dataset, validate_no_private_keys


class BaseAnswerEvaluator(Protocol):
    """answer-level evaluator 的最小协议。

    evaluator 只在 runner/evaluator 侧接收 GoldAnswerInfo，method 永远看不到该对象。
    """

    def evaluate(
        self,
        question: Question,
        prediction: AnswerResult,
        gold_answer: GoldAnswerInfo,
    ) -> MetricResult:
        """评分单个问题。

        输入:
            question: method 可见的公开问题。
            prediction: method 返回的预测答案。
            gold_answer: runner 内部读取的私有标准答案。

        输出:
            MetricResult: 单个 metric 的评分结果。
        """


def run_conversation_qa(
    dataset: Dataset,
    system: BaseMemorySystem,
    evaluators: Sequence[BaseAnswerEvaluator] | None = None,
) -> EvaluationResult:
    """运行同步 conversation-QA answer-level 评测。

    输入:
        dataset: 已由 adapter 转换出的 conversation-QA Dataset。
        system: 实现 BaseMemorySystem 的被测 method。
        evaluators: 可选 answer-level scorer 列表，每个 scorer 返回一个 MetricResult。

    输出:
        EvaluationResult: 数据集名、总题数、单题明细和可选聚合指标。
    """

    validate_dataset(dataset)
    evaluator_list = list(evaluators or [])
    detailed_results: list[dict[str, object]] = []
    metric_results_by_name: dict[str, list[MetricResult]] = {}

    for conversation in dataset.conversations:
        public_conversation = _make_public_conversation(conversation)
        validate_no_private_keys(public_conversation.to_public_dict())
        system.add([public_conversation])

        for source_question in conversation.questions:
            public_question = _make_public_question(source_question)
            validate_no_private_keys(public_question.to_dict())
            prediction = system.get_answer(public_question)
            gold_answer = conversation.gold_answers[public_question.question_id]
            per_question_metrics = _evaluate_question(
                evaluators=evaluator_list,
                question=public_question,
                prediction=prediction,
                gold_answer=gold_answer,
                metric_results_by_name=metric_results_by_name,
            )
            detailed_results.append(
                {
                    "conversation_id": conversation.conversation_id,
                    "question_id": public_question.question_id,
                    "question_text": public_question.text,
                    "prediction_answer": prediction.answer,
                    "metrics": per_question_metrics,
                }
            )

    return EvaluationResult(
        dataset_name=dataset.dataset_name,
        total_questions=len(detailed_results),
        metrics=_aggregate_metrics(metric_results_by_name),
        detailed_results=detailed_results,
    )


def _make_public_conversation(conversation: Conversation) -> Conversation:
    """重建 method 可见的 Conversation，并清空私有 gold_answers。

    输入:
        conversation: 原始完整 Conversation。

    输出:
        Conversation: 只包含 dataclass 声明公开字段的副本。
    """

    return Conversation(
        conversation_id=conversation.conversation_id,
        sessions=[_make_public_session(session) for session in conversation.sessions],
        questions=[_make_public_question(question) for question in conversation.questions],
        gold_answers={},
        metadata=copy.deepcopy(conversation.metadata),
    )


def _make_public_session(session: Session) -> Session:
    """重建 method 可见的 Session，丢弃运行时动态属性。

    输入:
        session: 原始 session。

    输出:
        Session: 只包含公开声明字段的副本。
    """

    return Session(
        session_id=session.session_id,
        turns=[_make_public_turn(turn) for turn in session.turns],
        session_time=session.session_time,
        start_time=session.start_time,
        end_time=session.end_time,
        metadata=copy.deepcopy(session.metadata),
    )


def _make_public_turn(turn: Turn) -> Turn:
    """重建 method 可见的 Turn，保留公开图片引用并丢弃动态私有属性。

    输入:
        turn: 原始发言。

    输出:
        Turn: 只包含公开声明字段的副本。
    """

    return Turn(
        turn_id=turn.turn_id,
        speaker=turn.speaker,
        content=turn.content,
        normalized_role=turn.normalized_role,
        turn_time=turn.turn_time,
        images=[_make_public_image(image) for image in turn.images],
        metadata=copy.deepcopy(turn.metadata),
    )


def _make_public_image(image: ImageRef) -> ImageRef:
    """重建 method 可见的 ImageRef，丢弃动态私有属性。

    输入:
        image: 原始图片引用。

    输出:
        ImageRef: 只包含公开声明字段的副本。
    """

    return ImageRef(
        image_id=image.image_id,
        path=image.path,
        caption=image.caption,
        metadata=copy.deepcopy(image.metadata),
    )


def _make_public_question(question: Question) -> Question:
    """复制 method 可见的 Question，避免携带动态私有属性。

    输入:
        question: 原始公开 Question。

    输出:
        Question: 只包含 dataclass 声明字段的副本。
    """

    return Question(
        question_id=question.question_id,
        conversation_id=question.conversation_id,
        text=question.text,
        question_time=question.question_time,
        category=question.category,
        options=copy.deepcopy(question.options),
        metadata=copy.deepcopy(question.metadata),
    )


def _evaluate_question(
    evaluators: Sequence[BaseAnswerEvaluator],
    question: Question,
    prediction: AnswerResult,
    gold_answer: GoldAnswerInfo,
    metric_results_by_name: dict[str, list[MetricResult]],
) -> dict[str, dict[str, object]]:
    """执行单题 evaluator 并收集明细 metric。

    输入:
        evaluators: 本次运行启用的 evaluator。
        question: 公开问题。
        prediction: method 预测结果。
        gold_answer: 私有标准答案。
        metric_results_by_name: 聚合用 metric 桶，会被原地追加。

    输出:
        dict[str, dict[str, object]]: metric_name 到序列化 MetricResult 的映射。
    """

    per_question_metrics: dict[str, dict[str, object]] = {}
    for evaluator in evaluators:
        metric_result = evaluator.evaluate(question, prediction, gold_answer)
        metric_results_by_name.setdefault(metric_result.metric_name, []).append(metric_result)
        per_question_metrics[metric_result.metric_name] = metric_result.to_dict()
    return per_question_metrics


def _aggregate_metrics(
    metric_results_by_name: dict[str, list[MetricResult]],
) -> dict[str, dict[str, float | int]]:
    """按 metric_name 聚合平均分和 correct 数量。

    输入:
        metric_results_by_name: runner 收集的所有单题 MetricResult。

    输出:
        dict[str, dict[str, float | int]]: 每个 metric 的平均 score、样本数和可选正确数。
    """

    aggregated: dict[str, dict[str, float | int]] = {}
    for metric_name, metric_results in metric_results_by_name.items():
        score_sum = sum(metric_result.score for metric_result in metric_results)
        metric_payload: dict[str, float | int] = {
            "score": score_sum / len(metric_results),
            "count": len(metric_results),
        }
        correct_values = [
            metric_result.is_correct
            for metric_result in metric_results
            if metric_result.is_correct is not None
        ]
        if correct_values:
            metric_payload["correct_count"] = sum(1 for value in correct_values if value)
        aggregated[metric_name] = metric_payload
    return aggregated


__all__ = ["BaseAnswerEvaluator", "run_conversation_qa"]
