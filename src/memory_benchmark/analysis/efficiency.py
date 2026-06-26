"""离线效率 observation 聚合。

本模块把原始 observation 聚合为便于报告展示的统计对象，不读取配置、不调用模型、
不计算真实费用。百分位采用线性插值：先排序，令 rank=(n-1)*p，再在相邻两个值之间
按小数部分插值；该定义固定在代码和测试中，避免不同报告端各自实现出不同结果。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from memory_benchmark.observability.efficiency import (
    ConversationEfficiencyObservation,
    EfficiencyObservation,
    EfficiencyStage,
    EmbeddingCallObservation,
    LLMCallObservation,
    QuestionEfficiencyObservation,
)

StageModelKey = tuple[EfficiencyStage, str]


@dataclass(frozen=True)
class NumericStats:
    """一组数值的基础统计。

    字段:
        count: 有效样本数。
        total: 样本总和；无样本时为 0.0。
        mean: 样本均值；无样本时为 None。
        p50: 线性插值中位数；无样本时为 None。
        p95: 线性插值 95 分位；无样本时为 None。
    """

    count: int
    total: float
    mean: float | None
    p50: float | None
    p95: float | None


@dataclass(frozen=True)
class LLMTokenSummary:
    """同一 stage/model 下的 LLM 调用 token 汇总。"""

    call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class EmbeddingTokenSummary:
    """同一 stage/model 下的 embedding token 和 latency 汇总。"""

    call_count: int
    input_tokens: int
    latency_ms: NumericStats


@dataclass(frozen=True)
class EfficiencySummary:
    """一组 efficiency observation 的离线聚合结果。

    字段:
        memory_build_latency_ms: conversation 级记忆构建总耗时统计。
        retrieval_latency_ms: 可精确拆分 retrieval 的问题耗时统计。
        answer_generation_latency_ms: 问题回答生成总耗时统计。
        injected_memory_context_tokens: 实际注入回答 prompt 的记忆上下文 token 统计。
        retrieval_supported_count: 有精确 retrieval latency 的问题数。
        retrieval_unsupported_count: retrieval latency 为 None 且带原因的问题数。
        llm_tokens: 按 `(stage, model_id)` 汇总的 LLM input/output token。
        embedding_tokens: 按 `(stage, model_id)` 汇总的 embedding input token 和 latency。
    """

    memory_build_latency_ms: NumericStats
    retrieval_latency_ms: NumericStats
    answer_generation_latency_ms: NumericStats
    injected_memory_context_tokens: NumericStats
    retrieval_supported_count: int
    retrieval_unsupported_count: int
    llm_tokens: dict[StageModelKey, LLMTokenSummary] = field(default_factory=dict)
    embedding_tokens: dict[StageModelKey, EmbeddingTokenSummary] = field(
        default_factory=dict
    )


def aggregate_efficiency(
    observations: Sequence[EfficiencyObservation],
) -> EfficiencySummary:
    """聚合一组原始 efficiency observation。

    输入:
        observations: prediction 或 evaluator artifact 中读取出的强类型 observation。

    输出:
        EfficiencySummary。该对象只包含派生统计，不包含价格，也不会估算缺失指标。
    """

    memory_build_latencies: list[float] = []
    retrieval_latencies: list[float] = []
    answer_latencies: list[float] = []
    injected_context_tokens: list[float] = []
    retrieval_supported_count = 0
    retrieval_unsupported_count = 0

    llm_accumulator: dict[StageModelKey, list[int]] = {}
    embedding_token_accumulator: dict[StageModelKey, int] = {}
    embedding_latency_accumulator: dict[StageModelKey, list[float]] = {}

    for observation in observations:
        if isinstance(observation, ConversationEfficiencyObservation):
            memory_build_latencies.append(
                float(observation.memory_build_total_latency_ms)
            )
            continue

        if isinstance(observation, QuestionEfficiencyObservation):
            answer_latencies.append(float(observation.answer_generation_latency_ms))
            if observation.retrieval_latency_ms is None:
                retrieval_unsupported_count += 1
            else:
                retrieval_supported_count += 1
                retrieval_latencies.append(float(observation.retrieval_latency_ms))
            if observation.injected_memory_context_tokens is not None:
                injected_context_tokens.append(
                    float(observation.injected_memory_context_tokens)
                )
            continue

        if isinstance(observation, LLMCallObservation):
            key = (observation.stage, observation.model_id)
            call_count, input_tokens, output_tokens = llm_accumulator.get(
                key,
                [0, 0, 0],
            )
            llm_accumulator[key] = [
                call_count + 1,
                input_tokens + observation.input_tokens,
                output_tokens + observation.output_tokens,
            ]
            continue

        if isinstance(observation, EmbeddingCallObservation):
            key = (observation.stage, observation.model_id)
            embedding_token_accumulator[key] = (
                embedding_token_accumulator.get(key, 0) + observation.input_tokens
            )
            embedding_latency_accumulator.setdefault(key, []).append(
                float(observation.latency_ms)
            )

    return EfficiencySummary(
        memory_build_latency_ms=_stats(memory_build_latencies),
        retrieval_latency_ms=_stats(retrieval_latencies),
        answer_generation_latency_ms=_stats(answer_latencies),
        injected_memory_context_tokens=_stats(injected_context_tokens),
        retrieval_supported_count=retrieval_supported_count,
        retrieval_unsupported_count=retrieval_unsupported_count,
        llm_tokens={
            key: LLMTokenSummary(
                call_count=values[0],
                input_tokens=values[1],
                output_tokens=values[2],
            )
            for key, values in sorted(
                llm_accumulator.items(),
                key=lambda item: (item[0][0].value, item[0][1]),
            )
        },
        embedding_tokens={
            key: EmbeddingTokenSummary(
                call_count=len(embedding_latency_accumulator[key]),
                input_tokens=embedding_token_accumulator[key],
                latency_ms=_stats(embedding_latency_accumulator[key]),
            )
            for key in sorted(
                embedding_latency_accumulator,
                key=lambda item: (item[0].value, item[1]),
            )
        },
    )


def build_efficiency_report_payloads(
    observations: Sequence[EfficiencyObservation],
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """构造 prediction/evaluator 可直接写入 JSON 的效率报告 payload。

    输入:
        observations: 已通过 `EfficiencyArtifactStore` 读取出的强类型 observation。

    输出:
        三个 JSON payload，顺序为 overall、by_conversation、by_question。该函数只
        聚合原始观测，不补齐缺失观测，也不计算真实费用。
    """

    conversation_records: dict[str, dict[str, Any]] = {}
    question_records: dict[tuple[str, str], dict[str, Any]] = {}

    for observation in observations:
        if isinstance(observation, ConversationEfficiencyObservation):
            record = _conversation_record(
                conversation_records,
                observation.conversation_id,
            )
            record["memory_build_total_latency_ms"] += (
                observation.memory_build_total_latency_ms
            )
            continue

        if isinstance(observation, QuestionEfficiencyObservation):
            conv_record = _conversation_record(
                conversation_records,
                observation.conversation_id,
            )
            conv_record["question_count"] += 1
            conv_record["answer_generation_latency_ms_total"] += (
                observation.answer_generation_latency_ms
            )
            if observation.retrieval_latency_ms is None:
                conv_record["retrieval_unsupported_count"] += 1
            else:
                conv_record["retrieval_supported_count"] += 1
                conv_record["retrieval_latency_ms_total"] += (
                    observation.retrieval_latency_ms
                )
            if observation.injected_memory_context_tokens is not None:
                conv_record["injected_memory_context_tokens_total"] += (
                    observation.injected_memory_context_tokens
                )

            key = (observation.conversation_id, observation.question_id)
            existing = question_records.get(key)
            question_records[key] = {
                "conversation_id": observation.conversation_id,
                "question_id": observation.question_id,
                "retrieval_latency_ms": observation.retrieval_latency_ms,
                "unsupported_reason": observation.unsupported_reason,
                "answer_generation_latency_ms": (
                    observation.answer_generation_latency_ms
                ),
                "injected_memory_context_tokens": (
                    observation.injected_memory_context_tokens
                ),
                "llm_call_count": (
                    0 if existing is None else existing["llm_call_count"]
                ),
                "llm_input_tokens": (
                    0 if existing is None else existing["llm_input_tokens"]
                ),
                "llm_output_tokens": (
                    0 if existing is None else existing["llm_output_tokens"]
                ),
                "embedding_call_count": (
                    0 if existing is None else existing["embedding_call_count"]
                ),
                "embedding_input_tokens": (
                    0
                    if existing is None
                    else existing["embedding_input_tokens"]
                ),
                "embedding_latency_ms_total": (
                    0.0
                    if existing is None
                    else existing["embedding_latency_ms_total"]
                ),
            }
            continue

        if isinstance(observation, LLMCallObservation):
            if observation.conversation_id is not None:
                conv_record = _conversation_record(
                    conversation_records,
                    observation.conversation_id,
                )
                conv_record["llm_call_count"] += 1
                conv_record["llm_input_tokens"] += observation.input_tokens
                conv_record["llm_output_tokens"] += observation.output_tokens
            if (
                observation.conversation_id is not None
                and observation.question_id is not None
            ):
                question_record = _question_record_if_present(
                    question_records,
                    observation.conversation_id,
                    observation.question_id,
                )
                question_record["llm_call_count"] += 1
                question_record["llm_input_tokens"] += observation.input_tokens
                question_record["llm_output_tokens"] += observation.output_tokens
            continue

        if isinstance(observation, EmbeddingCallObservation):
            if observation.conversation_id is not None:
                conv_record = _conversation_record(
                    conversation_records,
                    observation.conversation_id,
                )
                conv_record["embedding_call_count"] += 1
                conv_record["embedding_input_tokens"] += observation.input_tokens
                conv_record["embedding_latency_ms_total"] += observation.latency_ms
            if (
                observation.conversation_id is not None
                and observation.question_id is not None
            ):
                question_record = _question_record_if_present(
                    question_records,
                    observation.conversation_id,
                    observation.question_id,
                )
                question_record["embedding_call_count"] += 1
                question_record["embedding_input_tokens"] += observation.input_tokens
                question_record["embedding_latency_ms_total"] += observation.latency_ms

    return (
        {
            "schema_version": 1,
            "summary": _efficiency_summary_to_dict(
                aggregate_efficiency(observations)
            ),
        },
        {
            "schema_version": 1,
            "records": [
                conversation_records[conversation_id]
                for conversation_id in sorted(conversation_records)
            ],
        },
        {
            "schema_version": 1,
            "records": [
                question_records[key]
                for key in sorted(question_records)
            ],
        },
    )


def _conversation_record(
    records: dict[str, dict[str, Any]],
    conversation_id: str,
) -> dict[str, Any]:
    """返回或创建一个 conversation 级可读汇总记录。"""

    if conversation_id not in records:
        records[conversation_id] = {
            "conversation_id": conversation_id,
            "memory_build_total_latency_ms": 0.0,
            "question_count": 0,
            "retrieval_supported_count": 0,
            "retrieval_unsupported_count": 0,
            "retrieval_latency_ms_total": 0.0,
            "answer_generation_latency_ms_total": 0.0,
            "injected_memory_context_tokens_total": 0,
            "llm_call_count": 0,
            "llm_input_tokens": 0,
            "llm_output_tokens": 0,
            "embedding_call_count": 0,
            "embedding_input_tokens": 0,
            "embedding_latency_ms_total": 0.0,
        }
    return records[conversation_id]


def _question_record_if_present(
    records: dict[tuple[str, str], dict[str, Any]],
    conversation_id: str,
    question_id: str,
) -> dict[str, Any]:
    """返回已有 question 记录；模型调用早于 question 观测时创建轻量占位。"""

    key = (conversation_id, question_id)
    if key not in records:
        records[key] = {
            "conversation_id": conversation_id,
            "question_id": question_id,
            "retrieval_latency_ms": None,
            "unsupported_reason": "question_efficiency_observation_missing",
            "answer_generation_latency_ms": 0.0,
            "injected_memory_context_tokens": None,
            "llm_call_count": 0,
            "llm_input_tokens": 0,
            "llm_output_tokens": 0,
            "embedding_call_count": 0,
            "embedding_input_tokens": 0,
            "embedding_latency_ms_total": 0.0,
        }
    return records[key]


def _efficiency_summary_to_dict(summary: EfficiencySummary) -> dict[str, Any]:
    """把 EfficiencySummary 转成稳定 JSON 对象。"""

    return {
        "memory_build_latency_ms": _numeric_stats_to_dict(
            summary.memory_build_latency_ms
        ),
        "retrieval_latency_ms": _numeric_stats_to_dict(summary.retrieval_latency_ms),
        "answer_generation_latency_ms": _numeric_stats_to_dict(
            summary.answer_generation_latency_ms
        ),
        "injected_memory_context_tokens": _numeric_stats_to_dict(
            summary.injected_memory_context_tokens
        ),
        "retrieval_supported_count": summary.retrieval_supported_count,
        "retrieval_unsupported_count": summary.retrieval_unsupported_count,
        "llm_tokens": {
            _stage_model_key(stage, model_id): {
                "call_count": token_summary.call_count,
                "input_tokens": token_summary.input_tokens,
                "output_tokens": token_summary.output_tokens,
            }
            for (stage, model_id), token_summary in summary.llm_tokens.items()
        },
        "embedding_tokens": {
            _stage_model_key(stage, model_id): {
                "call_count": token_summary.call_count,
                "input_tokens": token_summary.input_tokens,
                "latency_ms": _numeric_stats_to_dict(token_summary.latency_ms),
            }
            for (stage, model_id), token_summary in summary.embedding_tokens.items()
        },
    }


def _numeric_stats_to_dict(stats: NumericStats) -> dict[str, float | int | None]:
    """把 NumericStats 转成稳定 JSON 对象。"""

    return {
        "count": stats.count,
        "total": stats.total,
        "mean": stats.mean,
        "p50": stats.p50,
        "p95": stats.p95,
    }


def _stage_model_key(stage: EfficiencyStage, model_id: str) -> str:
    """构造报告中易读且稳定的 stage/model key。"""

    return f"{stage.value}:{model_id}"


def _stats(values: Sequence[float]) -> NumericStats:
    """计算基础统计；空列表返回零计数和 None 分位数。"""

    if not values:
        return NumericStats(
            count=0,
            total=0.0,
            mean=None,
            p50=None,
            p95=None,
        )
    sorted_values = sorted(float(value) for value in values)
    total = sum(sorted_values)
    count = len(sorted_values)
    return NumericStats(
        count=count,
        total=total,
        mean=total / count,
        p50=_percentile(sorted_values, 0.5),
        p95=_percentile(sorted_values, 0.95),
    )


def _percentile(sorted_values: Sequence[float], percentile: float) -> float:
    """在线性插值定义下计算百分位，输入必须已升序排序。"""

    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * percentile
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    fraction = rank - lower_index
    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    return lower_value + (upper_value - lower_value) * fraction


__all__ = [
    "EfficiencySummary",
    "EmbeddingTokenSummary",
    "LLMTokenSummary",
    "NumericStats",
    "aggregate_efficiency",
    "build_efficiency_report_payloads",
]
