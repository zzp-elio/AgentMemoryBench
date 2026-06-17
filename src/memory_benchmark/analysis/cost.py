"""基于真实价格的离线成本计算。

本模块只把已记录的 API usage observation 换算成费用。价格必须由用户在实验后传入，
因此 prediction/evaluation artifact 不会绑定任何服务商价格。注入记忆上下文 token 是诊断
指标，已经包含在回答 LLM 的 input usage 中，不能在这里额外计费。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping, Sequence

from memory_benchmark.core import ConfigurationError
from memory_benchmark.observability.efficiency import (
    EfficiencyObservation,
    EmbeddingCallObservation,
    LLMCallObservation,
    ModelDescriptor,
)

TOKENS_PER_MILLION = Decimal("1000000")


@dataclass(frozen=True)
class APILLMPrice:
    """API LLM 每百万 token 的 input/output 价格。

    字段:
        input_cost_per_million_tokens: 每百万 input token 成本。
        output_cost_per_million_tokens: 每百万 output token 成本。
        currency: 价格币种，例如 USD 或 CNY。
    """

    input_cost_per_million_tokens: Decimal
    output_cost_per_million_tokens: Decimal
    currency: str

    def __post_init__(self) -> None:
        """校验价格非负且币种可读。"""

        _require_decimal_cost(
            self.input_cost_per_million_tokens,
            "input_cost_per_million_tokens",
        )
        _require_decimal_cost(
            self.output_cost_per_million_tokens,
            "output_cost_per_million_tokens",
        )
        _require_currency(self.currency)


@dataclass(frozen=True)
class APIEmbeddingPrice:
    """API embedding 每百万 input token 的价格。"""

    input_cost_per_million_tokens: Decimal
    currency: str

    def __post_init__(self) -> None:
        """校验价格非负且币种可读。"""

        _require_decimal_cost(
            self.input_cost_per_million_tokens,
            "input_cost_per_million_tokens",
        )
        _require_currency(self.currency)


@dataclass(frozen=True)
class CostReport:
    """离线费用计算结果。

    字段:
        total_cost: 已能计算的总费用；如果 complete=False，只代表已提供价格部分。
        currency: 总费用币种；没有任何付费模型时为 None。
        complete: 是否所有 API 模型都找到了对应价格。
        missing_price_model_ids: 缺少价格的 API 模型 id，稳定排序。
        cost_by_model_id: 已计算费用按模型汇总。
        skipped_local_model_ids: 模型清单标记为 local 因而固定零成本的模型 id。
    """

    total_cost: Decimal
    currency: str | None
    complete: bool
    missing_price_model_ids: tuple[str, ...] = ()
    cost_by_model_id: dict[str, Decimal] = field(default_factory=dict)
    skipped_local_model_ids: tuple[str, ...] = ()


APIPrice = APILLMPrice | APIEmbeddingPrice


def calculate_cost(
    observations: Sequence[EfficiencyObservation],
    prices: Mapping[str, APIPrice],
    *,
    model_inventory: Sequence[ModelDescriptor] = (),
) -> CostReport:
    """根据真实 API usage 和用户价格计算费用。

    输入:
        observations: 已落盘或已读取的 efficiency observation。
        prices: 按 model_id 提供的真实服务商价格。
        model_inventory: 可选模型清单；execution_mode 为 local 的模型不需要价格。

    输出:
        CostReport。缺少 API 价格时返回 complete=False，而不是把成本静默记为 0。
    """

    inventory_by_id = {model.model_id: model for model in model_inventory}
    cost_by_model_id: dict[str, Decimal] = {}
    missing_price_model_ids: set[str] = set()
    skipped_local_model_ids: set[str] = set()
    currency: str | None = None

    for observation in observations:
        if not isinstance(observation, LLMCallObservation | EmbeddingCallObservation):
            continue

        descriptor = inventory_by_id.get(observation.model_id)
        if descriptor is not None and descriptor.execution_mode == "local":
            skipped_local_model_ids.add(observation.model_id)
            continue

        price = prices.get(observation.model_id)
        if price is None:
            missing_price_model_ids.add(observation.model_id)
            continue

        _ensure_currency_compatible(currency, price.currency)
        currency = price.currency if currency is None else currency
        cost = _calculate_observation_cost(observation, price)
        cost_by_model_id[observation.model_id] = (
            cost_by_model_id.get(observation.model_id, Decimal("0")) + cost
        )

    return CostReport(
        total_cost=sum(cost_by_model_id.values(), Decimal("0")),
        currency=currency,
        complete=not missing_price_model_ids,
        missing_price_model_ids=tuple(sorted(missing_price_model_ids)),
        cost_by_model_id=dict(sorted(cost_by_model_id.items())),
        skipped_local_model_ids=tuple(sorted(skipped_local_model_ids)),
    )


def _calculate_observation_cost(
    observation: LLMCallObservation | EmbeddingCallObservation,
    price: APIPrice,
) -> Decimal:
    """按 observation 类型选择对应价格公式。"""

    if isinstance(observation, LLMCallObservation):
        if not isinstance(price, APILLMPrice):
            raise ConfigurationError(
                f"LLM model {observation.model_id} requires APILLMPrice"
            )
        return (
            Decimal(observation.input_tokens) * price.input_cost_per_million_tokens
            + Decimal(observation.output_tokens) * price.output_cost_per_million_tokens
        ) / TOKENS_PER_MILLION

    if not isinstance(price, APIEmbeddingPrice):
        raise ConfigurationError(
            f"Embedding model {observation.model_id} requires APIEmbeddingPrice"
        )
    return (
        Decimal(observation.input_tokens) * price.input_cost_per_million_tokens
    ) / TOKENS_PER_MILLION


def _ensure_currency_compatible(
    existing_currency: str | None,
    next_currency: str,
) -> None:
    """拒绝把不同币种的费用直接相加。"""

    if existing_currency is not None and existing_currency != next_currency:
        raise ConfigurationError(
            "Cost calculation cannot mix different currency values"
        )


def _require_decimal_cost(value: Decimal, field_name: str) -> None:
    """要求价格字段为非负 Decimal。"""

    if not isinstance(value, Decimal):
        raise ConfigurationError(f"{field_name} must be Decimal")
    if value < 0:
        raise ConfigurationError(f"{field_name} must be non-negative")


def _require_currency(value: str) -> None:
    """要求币种为非空字符串。"""

    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError("currency must be a non-empty string")


__all__ = [
    "APIEmbeddingPrice",
    "APILLMPrice",
    "CostReport",
    "calculate_cost",
]
