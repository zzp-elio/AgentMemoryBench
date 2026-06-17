"""成本与效率 observation 实体测试。

本模块验证模型清单和四类原始 observation 的强约束。测试只检查纯数据结构，
不访问网络、第三方 method 或真实实验目录。
"""

from __future__ import annotations

import math

import pytest

from memory_benchmark.core import ConfigurationError
from memory_benchmark.observability.efficiency import (
    ConversationEfficiencyObservation,
    EfficiencyStage,
    EmbeddingCallObservation,
    LLMCallObservation,
    MeasurementSource,
    ModelDescriptor,
    QuestionEfficiencyObservation,
    RetrievalObservationContract,
)


def test_model_descriptor_serializes_reproducible_identity() -> None:
    """模型清单应保留名称、角色、执行方式和 tokenizer 身份。"""

    descriptor = ModelDescriptor(
        model_id="answer-llm",
        model_name="gpt-4o-mini",
        model_role="answer_llm",
        execution_mode="api",
        tokenizer_name="gpt-4o-mini",
    )

    assert descriptor.to_dict() == {
        "model_id": "answer-llm",
        "model_name": "gpt-4o-mini",
        "model_role": "answer_llm",
        "execution_mode": "api",
        "revision_or_path": None,
        "embedding_dimension": None,
        "tokenizer_name": "gpt-4o-mini",
    }


def test_model_descriptor_rejects_unknown_execution_mode() -> None:
    """模型执行方式只能是本地或 API，不能接受任意字符串。"""

    with pytest.raises(ConfigurationError, match="execution_mode"):
        ModelDescriptor(
            model_id="bad-model",
            model_name="model",
            model_role="answer_llm",
            execution_mode="remote",
        )


def test_conversation_efficiency_rejects_non_finite_latency() -> None:
    """记忆构建总耗时必须是有限的非负数。"""

    with pytest.raises(ConfigurationError, match="memory_build_total_latency_ms"):
        ConversationEfficiencyObservation(
            observation_id="build-1",
            conversation_id="conv-1",
            memory_build_total_latency_ms=math.inf,
        )


def test_question_efficiency_requires_reason_for_unsupported_retrieval() -> None:
    """检索耗时为空时必须解释为何无法精确拆分。"""

    with pytest.raises(ConfigurationError, match="unsupported_reason"):
        QuestionEfficiencyObservation(
            observation_id="question-1",
            conversation_id="conv-1",
            question_id="q-1",
            retrieval_latency_ms=None,
            unsupported_reason=None,
            injected_memory_context_tokens=12,
            answer_generation_latency_ms=4.5,
        )


def test_question_efficiency_rejects_reason_for_supported_retrieval() -> None:
    """已有精确检索耗时时不应同时声称该指标不受支持。"""

    with pytest.raises(ConfigurationError, match="unsupported_reason"):
        QuestionEfficiencyObservation(
            observation_id="question-1",
            conversation_id="conv-1",
            question_id="q-1",
            retrieval_latency_ms=2.0,
            unsupported_reason="opaque method",
            injected_memory_context_tokens=12,
            answer_generation_latency_ms=4.5,
        )


def test_question_efficiency_accepts_explicit_unsupported_retrieval() -> None:
    """无法拆分检索边界时应保存 null 和具体原因，而不是估算。"""

    observation = QuestionEfficiencyObservation(
        observation_id="question-1",
        conversation_id="conv-1",
        question_id="q-1",
        retrieval_latency_ms=None,
        unsupported_reason="method does not expose a separable retrieval boundary",
        injected_memory_context_tokens=None,
        answer_generation_latency_ms=4.5,
    )

    assert observation.to_dict()["retrieval_latency_ms"] is None
    assert observation.to_dict()["unsupported_reason"].startswith("method")


def test_retrieval_contract_rejects_required_but_unsupported_method() -> None:
    """profile 要求精确 retrieval 时，method 不支持必须在运行前报错。"""

    with pytest.raises(ConfigurationError, match="requires separable retrieval"):
        RetrievalObservationContract(
            required_by_profile=True,
            supported_by_method=False,
            unsupported_reason="opaque end-to-end method",
        )


def test_retrieval_contract_requires_reason_for_allowed_unsupported() -> None:
    """允许 unsupported 时仍必须记录稳定、可审计的具体原因。"""

    with pytest.raises(ConfigurationError, match="unsupported_reason"):
        RetrievalObservationContract(
            required_by_profile=False,
            supported_by_method=False,
            unsupported_reason=None,
        )


def test_retrieval_contract_serializes_explicit_supported_identity() -> None:
    """精确 retrieval 能力声明应进入 manifest 可序列化身份。"""

    contract = RetrievalObservationContract(
        required_by_profile=True,
        supported_by_method=True,
    )

    assert contract.to_dict() == {
        "required_by_profile": True,
        "supported_by_method": True,
        "unsupported_reason": None,
    }


def test_llm_call_rejects_negative_tokens() -> None:
    """LLM input/output token 都必须是非负整数。"""

    with pytest.raises(ConfigurationError, match="input_tokens"):
        LLMCallObservation(
            observation_id="llm-1",
            stage=EfficiencyStage.ANSWER,
            model_id="answer-llm",
            input_tokens=-1,
            output_tokens=3,
            token_measurement_source=MeasurementSource.API_USAGE,
            conversation_id="conv-1",
            question_id="q-1",
        )


def test_llm_call_accepts_retrieval_stage_for_query_understanding() -> None:
    """部分 method 会在检索阶段调用 LLM 做 query 理解，应真实记录。"""

    observation = LLMCallObservation(
        observation_id="llm-1",
        stage=EfficiencyStage.RETRIEVAL,
        model_id="memoryos-chat-llm",
        input_tokens=8,
        output_tokens=3,
        token_measurement_source=MeasurementSource.API_USAGE,
        conversation_id="conv-1",
        question_id="q-1",
    )

    assert observation.to_dict()["stage"] == "retrieval"


def test_llm_call_rejects_plain_string_stage() -> None:
    """运行时必须传入强类型 stage，不能依赖宽松字符串比较。"""

    with pytest.raises(ConfigurationError, match="stage"):
        LLMCallObservation(
            observation_id="llm-1",
            stage="answer",  # type: ignore[arg-type]
            model_id="answer-llm",
            input_tokens=8,
            output_tokens=3,
            token_measurement_source=MeasurementSource.API_USAGE,
            conversation_id="conv-1",
            question_id="q-1",
        )


def test_llm_call_rejects_invalid_token_measurement_source() -> None:
    """LLM token 来源必须是稳定枚举，不能写入任意字符串。"""

    with pytest.raises(ConfigurationError, match="token_measurement_source"):
        LLMCallObservation(
            observation_id="llm-1",
            stage=EfficiencyStage.ANSWER,
            model_id="answer-llm",
            input_tokens=8,
            output_tokens=3,
            token_measurement_source="bogus",  # type: ignore[arg-type]
            conversation_id="conv-1",
            question_id="q-1",
        )


def test_llm_call_rejects_framework_timer_as_token_source() -> None:
    """计时器不能被误标为 token 计量来源。"""

    with pytest.raises(ConfigurationError, match="token_measurement_source"):
        LLMCallObservation(
            observation_id="llm-1",
            stage=EfficiencyStage.ANSWER,
            model_id="answer-llm",
            input_tokens=8,
            output_tokens=3,
            token_measurement_source=MeasurementSource.FRAMEWORK_TIMER,
            conversation_id="conv-1",
            question_id="q-1",
        )


def test_embedding_call_serializes_both_measurement_sources() -> None:
    """Embedding token 和 latency 来源必须分别记录。"""

    observation = EmbeddingCallObservation(
        observation_id="embedding-1",
        stage=EfficiencyStage.RETRIEVAL,
        model_id="embedding",
        input_tokens=9,
        latency_ms=1.25,
        token_measurement_source=MeasurementSource.TOKENIZER_ESTIMATE,
        latency_measurement_source=MeasurementSource.FRAMEWORK_TIMER,
        conversation_id="conv-1",
        question_id="q-1",
    )

    payload = observation.to_dict()
    assert payload["observation_type"] == "embedding_call"
    assert payload["stage"] == "retrieval"
    assert payload["token_measurement_source"] == "tokenizer_estimate"
    assert payload["latency_measurement_source"] == "framework_timer"


def test_embedding_call_rejects_judge_stage() -> None:
    """Embedding 调用只允许出现在记忆构建或检索阶段。"""

    with pytest.raises(ConfigurationError, match="stage"):
        EmbeddingCallObservation(
            observation_id="embedding-1",
            stage=EfficiencyStage.JUDGE,
            model_id="embedding",
            input_tokens=9,
            latency_ms=1.25,
            token_measurement_source=MeasurementSource.TOKENIZER_ESTIMATE,
            latency_measurement_source=MeasurementSource.FRAMEWORK_TIMER,
        )


def test_embedding_call_rejects_invalid_measurement_source_combinations() -> None:
    """Embedding token 与 latency 来源必须分别属于各自允许集合。"""

    with pytest.raises(ConfigurationError, match="token_measurement_source"):
        EmbeddingCallObservation(
            observation_id="embedding-1",
            stage=EfficiencyStage.RETRIEVAL,
            model_id="embedding",
            input_tokens=9,
            latency_ms=1.25,
            token_measurement_source=MeasurementSource.FRAMEWORK_TIMER,
            latency_measurement_source=MeasurementSource.FRAMEWORK_TIMER,
        )

    with pytest.raises(ConfigurationError, match="latency_measurement_source"):
        EmbeddingCallObservation(
            observation_id="embedding-1",
            stage=EfficiencyStage.RETRIEVAL,
            model_id="embedding",
            input_tokens=9,
            latency_ms=1.25,
            token_measurement_source=MeasurementSource.TOKENIZER_ESTIMATE,
            latency_measurement_source=MeasurementSource.TOKENIZER_ESTIMATE,
        )
