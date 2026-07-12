"""基于真实价格的离线成本计算。

本模块只把已记录的 API usage observation 换算成费用。价格必须由用户在实验后传入，
因此 prediction/evaluation artifact 不会绑定任何服务商价格。注入记忆上下文 token 是诊断
指标，已经包含在回答 LLM 的 input usage 中，不能在这里额外计费。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
import tomllib
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


def load_pricing(path: str | Path) -> Mapping[str, APIPrice]:
    """从严格 TOML 配置加载 API 价格，忽略显式标记的本地模型。

    每个 ``models`` 条目必须声明 ``model_id``、``kind`` 和 ``execution_mode``。
    API 条目还必须提供对应价格字段与币种；local 条目不得携带价格字段，后续由
    ``calculate_cost`` 的模型清单语义将其列入零成本模型。
    """

    pricing_path = Path(path)
    try:
        payload = tomllib.loads(pricing_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"Pricing TOML is invalid: {pricing_path}") from exc
    if set(payload) != {"models"} or not isinstance(payload["models"], list):
        raise ConfigurationError("Pricing TOML must contain only a models array")

    prices: dict[str, APIPrice] = {}
    seen_model_ids: set[str] = set()
    for index, record in enumerate(payload["models"]):
        if not isinstance(record, dict):
            raise ConfigurationError(f"Pricing models[{index}] must be a table")
        model_id = record.get("model_id")
        kind = record.get("kind")
        execution_mode = record.get("execution_mode")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ConfigurationError(f"Pricing models[{index}].model_id is required")
        if model_id in seen_model_ids:
            raise ConfigurationError(f"Pricing has duplicate model_id: {model_id}")
        seen_model_ids.add(model_id)

        if execution_mode == "local":
            if set(record) != {"model_id", "kind", "execution_mode"}:
                raise ConfigurationError(
                    f"Local pricing model {model_id} must not contain price fields"
                )
            if kind not in {"llm", "embedding"}:
                raise ConfigurationError(f"Pricing model {model_id} has invalid kind")
            continue
        if execution_mode != "api":
            raise ConfigurationError(
                f"Pricing model {model_id} has invalid execution_mode"
            )

        if kind == "llm":
            expected = {
                "model_id",
                "kind",
                "execution_mode",
                "input_cost_per_million_tokens",
                "output_cost_per_million_tokens",
                "currency",
            }
            if set(record) != expected:
                _raise_pricing_field_error(model_id, record, expected)
            prices[model_id] = APILLMPrice(
                input_cost_per_million_tokens=_decimal_from_toml(
                    record["input_cost_per_million_tokens"], model_id
                ),
                output_cost_per_million_tokens=_decimal_from_toml(
                    record["output_cost_per_million_tokens"], model_id
                ),
                currency=record["currency"],
            )
            continue
        if kind == "embedding":
            expected = {
                "model_id",
                "kind",
                "execution_mode",
                "input_cost_per_million_tokens",
                "currency",
            }
            if set(record) != expected:
                _raise_pricing_field_error(model_id, record, expected)
            prices[model_id] = APIEmbeddingPrice(
                input_cost_per_million_tokens=_decimal_from_toml(
                    record["input_cost_per_million_tokens"], model_id
                ),
                currency=record["currency"],
            )
            continue
        raise ConfigurationError(f"Pricing model {model_id} has invalid kind")

    return prices


def _raise_pricing_field_error(
    model_id: str,
    record: Mapping[str, object],
    expected: set[str],
) -> None:
    """报告价格条目的缺失与多余字段。"""

    raise ConfigurationError(
        f"Pricing model {model_id} fields do not match schema: "
        f"missing={sorted(expected - set(record))}, "
        f"extra={sorted(set(record) - expected)}"
    )


def _decimal_from_toml(value: object, model_id: str) -> Decimal:
    """把 TOML 数值无损转换为 Decimal，并拒绝布尔值等伪数值。"""

    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigurationError(f"Pricing model {model_id} price must be numeric")
    return Decimal(str(value))


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
    "load_pricing",
]
