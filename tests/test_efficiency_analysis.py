"""离线效率 observation 聚合测试。

本模块只验证已经写入 artifact 的原始 observation 如何被聚合成报告数据。
测试不访问网络，也不调用 benchmark adapter 或 method adapter。
"""

from __future__ import annotations

from memory_benchmark.analysis.efficiency import aggregate_efficiency
from memory_benchmark.observability.efficiency import (
    ConversationEfficiencyObservation,
    EfficiencyStage,
    EmbeddingCallObservation,
    LLMCallObservation,
    MeasurementSource,
    QuestionEfficiencyObservation,
)


def test_aggregate_efficiency_summarizes_latency_tokens_and_unsupported_retrieval() -> None:
    """聚合报告应覆盖构建耗时、检索耗时、注入上下文 token 和模型调用 token。

    输入:
        一组混合 observation，包含 conversation 级构建耗时、question 级耗时、
        LLM 调用和 embedding 调用。
    输出:
        一个只读聚合对象；其中百分位使用线性插值，缺失检索耗时计入 unsupported。
    """

    summary = aggregate_efficiency(
        [
            ConversationEfficiencyObservation(
                observation_id="build-1",
                conversation_id="conv-1",
                memory_build_total_latency_ms=10.0,
            ),
            ConversationEfficiencyObservation(
                observation_id="build-2",
                conversation_id="conv-2",
                memory_build_total_latency_ms=20.0,
            ),
            QuestionEfficiencyObservation(
                observation_id="q-1",
                conversation_id="conv-1",
                question_id="question-1",
                retrieval_latency_ms=5.0,
                unsupported_reason=None,
                injected_memory_context_tokens=100,
                answer_generation_latency_ms=30.0,
            ),
            QuestionEfficiencyObservation(
                observation_id="q-2",
                conversation_id="conv-1",
                question_id="question-2",
                retrieval_latency_ms=None,
                unsupported_reason="method does not expose retrieval boundary",
                injected_memory_context_tokens=None,
                answer_generation_latency_ms=50.0,
            ),
            QuestionEfficiencyObservation(
                observation_id="q-3",
                conversation_id="conv-2",
                question_id="question-3",
                retrieval_latency_ms=15.0,
                unsupported_reason=None,
                injected_memory_context_tokens=300,
                answer_generation_latency_ms=70.0,
            ),
            LLMCallObservation(
                observation_id="llm-answer-1",
                stage=EfficiencyStage.ANSWER,
                model_id="answer-llm",
                input_tokens=100,
                output_tokens=10,
                token_measurement_source=MeasurementSource.API_USAGE,
                conversation_id="conv-1",
                question_id="question-1",
            ),
            LLMCallObservation(
                observation_id="llm-answer-2",
                stage=EfficiencyStage.ANSWER,
                model_id="answer-llm",
                input_tokens=50,
                output_tokens=5,
                token_measurement_source=MeasurementSource.API_USAGE,
                conversation_id="conv-2",
                question_id="question-3",
            ),
            LLMCallObservation(
                observation_id="llm-judge-1",
                stage=EfficiencyStage.JUDGE,
                model_id="judge-llm",
                input_tokens=80,
                output_tokens=2,
                token_measurement_source=MeasurementSource.API_USAGE,
                conversation_id="conv-1",
                question_id="question-1",
            ),
            EmbeddingCallObservation(
                observation_id="embedding-build-1",
                stage=EfficiencyStage.MEMORY_BUILD,
                model_id="embedding-model",
                input_tokens=40,
                latency_ms=8.0,
                token_measurement_source=MeasurementSource.TOKENIZER_ESTIMATE,
                latency_measurement_source=MeasurementSource.FRAMEWORK_TIMER,
                conversation_id="conv-1",
            ),
            EmbeddingCallObservation(
                observation_id="embedding-retrieval-1",
                stage=EfficiencyStage.RETRIEVAL,
                model_id="embedding-model",
                input_tokens=12,
                latency_ms=2.0,
                token_measurement_source=MeasurementSource.TOKENIZER_ESTIMATE,
                latency_measurement_source=MeasurementSource.FRAMEWORK_TIMER,
                conversation_id="conv-1",
                question_id="question-1",
            ),
        ]
    )

    assert summary.memory_build_latency_ms.count == 2
    assert summary.memory_build_latency_ms.total == 30.0
    assert summary.memory_build_latency_ms.mean == 15.0
    assert summary.memory_build_latency_ms.p50 == 15.0
    assert summary.memory_build_latency_ms.p95 == 19.5

    assert summary.retrieval_supported_count == 2
    assert summary.retrieval_unsupported_count == 1
    assert summary.retrieval_latency_ms.total == 20.0
    assert summary.answer_generation_latency_ms.p50 == 50.0
    assert summary.injected_memory_context_tokens.total == 400.0

    answer_tokens = summary.llm_tokens[(EfficiencyStage.ANSWER, "answer-llm")]
    assert answer_tokens.call_count == 2
    assert answer_tokens.input_tokens == 150
    assert answer_tokens.output_tokens == 15

    judge_tokens = summary.llm_tokens[(EfficiencyStage.JUDGE, "judge-llm")]
    assert judge_tokens.call_count == 1
    assert judge_tokens.input_tokens == 80
    assert judge_tokens.output_tokens == 2

    build_embedding = summary.embedding_tokens[
        (EfficiencyStage.MEMORY_BUILD, "embedding-model")
    ]
    assert build_embedding.call_count == 1
    assert build_embedding.input_tokens == 40
    assert build_embedding.latency_ms.total == 8.0


def test_aggregate_efficiency_empty_input_returns_zero_counts() -> None:
    """空 observation 列表应返回零计数报告，而不是抛异常或返回 None。"""

    summary = aggregate_efficiency([])

    assert summary.memory_build_latency_ms.count == 0
    assert summary.memory_build_latency_ms.mean is None
    assert summary.retrieval_supported_count == 0
    assert summary.llm_tokens == {}
