"""离线真实费用计算测试。

本模块验证费用只从已记录的真实 API 调用 observation 计算，价格由用户在实验后提供。
注入到回答 prompt 的记忆上下文 token 只作为诊断指标，不能被重复计费。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from memory_benchmark.analysis.cost import (
    APIEmbeddingPrice,
    APILLMPrice,
    calculate_cost,
)
from memory_benchmark.core import ConfigurationError
from memory_benchmark.observability.efficiency import (
    EfficiencyStage,
    EmbeddingCallObservation,
    LLMCallObservation,
    MeasurementSource,
    ModelDescriptor,
    QuestionEfficiencyObservation,
)


def _api_llm_call(
    *,
    model_id: str = "answer-llm",
    input_tokens: int = 100,
    output_tokens: int = 10,
) -> LLMCallObservation:
    """构造测试用 API LLM 调用 observation。"""

    return LLMCallObservation(
        observation_id=f"llm-{model_id}",
        stage=EfficiencyStage.ANSWER,
        model_id=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        token_measurement_source=MeasurementSource.API_USAGE,
        conversation_id="conv-1",
        question_id="q-1",
    )


def _question_efficiency(
    *,
    injected_memory_context_tokens: int | None,
) -> QuestionEfficiencyObservation:
    """构造测试用 question 级效率 observation。"""

    return QuestionEfficiencyObservation(
        observation_id="question-efficiency-1",
        conversation_id="conv-1",
        question_id="q-1",
        retrieval_latency_ms=5.0,
        unsupported_reason=None,
        injected_memory_context_tokens=injected_memory_context_tokens,
        answer_generation_latency_ms=30.0,
    )


def test_cost_does_not_charge_injected_context_twice() -> None:
    """费用只应按真实 LLM usage 计费，不能额外叠加 memory context token。

    输入:
        answer LLM 实际 usage 为 100 input / 10 output，另有 40 个注入记忆 token。
    输出:
        总费用为 100*1e-6 + 10*2e-6 = 0.00012，40 个诊断 token 不重复计费。
    """

    report = calculate_cost(
        observations=[
            _api_llm_call(input_tokens=100, output_tokens=10),
            _question_efficiency(injected_memory_context_tokens=40),
        ],
        prices={
            "answer-llm": APILLMPrice(
                input_cost_per_million_tokens=Decimal("1"),
                output_cost_per_million_tokens=Decimal("2"),
                currency="USD",
            )
        },
    )

    assert report.complete is True
    assert report.currency == "USD"
    assert report.total_cost == Decimal("0.00012")
    assert report.cost_by_model_id == {"answer-llm": Decimal("0.00012")}


def test_missing_api_price_is_reported_not_silently_zero() -> None:
    """API 模型缺价格时必须报告 incomplete，不能静默当成零成本。"""

    report = calculate_cost(
        observations=[_api_llm_call(model_id="unknown")],
        prices={},
    )

    assert report.complete is False
    assert report.total_cost == Decimal("0")
    assert report.missing_price_model_ids == ("unknown",)


def test_local_model_cost_is_zero_without_price() -> None:
    """模型清单标记为 local 的模型不需要价格，费用固定为零。"""

    report = calculate_cost(
        observations=[_api_llm_call(model_id="local-answer")],
        prices={},
        model_inventory=[
            ModelDescriptor(
                model_id="local-answer",
                model_name="local-test-model",
                model_role="answer_llm",
                execution_mode="local",
            )
        ],
    )

    assert report.complete is True
    assert report.total_cost == Decimal("0")
    assert report.skipped_local_model_ids == ("local-answer",)


def test_embedding_api_price_uses_input_tokens_only() -> None:
    """embedding API 成本只按 input token 计费，并可和同币种 LLM 成本相加。"""

    report = calculate_cost(
        observations=[
            _api_llm_call(input_tokens=100, output_tokens=10),
            EmbeddingCallObservation(
                observation_id="embedding-1",
                stage=EfficiencyStage.RETRIEVAL,
                model_id="embedding-model",
                input_tokens=1000,
                latency_ms=4.0,
                token_measurement_source=MeasurementSource.API_USAGE,
                latency_measurement_source=MeasurementSource.FRAMEWORK_TIMER,
                conversation_id="conv-1",
                question_id="q-1",
            ),
        ],
        prices={
            "answer-llm": APILLMPrice(
                input_cost_per_million_tokens=Decimal("1"),
                output_cost_per_million_tokens=Decimal("2"),
                currency="USD",
            ),
            "embedding-model": APIEmbeddingPrice(
                input_cost_per_million_tokens=Decimal("0.1"),
                currency="USD",
            ),
        },
    )

    assert report.complete is True
    assert report.total_cost == Decimal("0.00022")
    assert report.cost_by_model_id["embedding-model"] == Decimal("0.0001")


def test_different_currencies_are_rejected() -> None:
    """不同币种不能直接相加，必须由用户先统一价格口径。"""

    with pytest.raises(ConfigurationError, match="currency"):
        calculate_cost(
            observations=[
                _api_llm_call(model_id="usd-model"),
                _api_llm_call(model_id="cny-model"),
            ],
            prices={
                "usd-model": APILLMPrice(
                    input_cost_per_million_tokens=Decimal("1"),
                    output_cost_per_million_tokens=Decimal("1"),
                    currency="USD",
                ),
                "cny-model": APILLMPrice(
                    input_cost_per_million_tokens=Decimal("1"),
                    output_cost_per_million_tokens=Decimal("1"),
                    currency="CNY",
                ),
            },
        )
