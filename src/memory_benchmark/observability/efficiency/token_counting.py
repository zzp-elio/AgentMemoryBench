"""LLM token usage 的来源解析与 tokenizer 回退。

本模块不选择具体 tokenizer；调用方必须传入与实际模型匹配的 TokenCounter。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from memory_benchmark.core import ConfigurationError
from memory_benchmark.observability.efficiency.entities import MeasurementSource


class TokenCounter(Protocol):
    """任意模型 tokenizer 的最小计数协议。"""

    def count_tokens(self, text: str) -> int:
        """返回文本对应的 token 数。"""


@dataclass(frozen=True)
class ResolvedTokenUsage:
    """一次 LLM 调用最终采用的 input/output token 与来源。"""

    input_tokens: int
    output_tokens: int
    source: MeasurementSource


def resolve_token_usage(
    *,
    api_input_tokens: int | None,
    api_output_tokens: int | None,
    prompt_text: str,
    output_text: str,
    tokenizer: TokenCounter | None,
) -> ResolvedTokenUsage:
    """优先采用完整 API usage，否则使用匹配 tokenizer 估算两侧 token。

    API usage 只要任一侧缺失，就统一回退 tokenizer，避免一条 observation 混合两种来源。
    """

    if api_input_tokens is not None:
        _validate_token_count(api_input_tokens, "api_input_tokens")
    if api_output_tokens is not None:
        _validate_token_count(api_output_tokens, "api_output_tokens")
    if api_input_tokens is not None and api_output_tokens is not None:
        return ResolvedTokenUsage(
            input_tokens=api_input_tokens,
            output_tokens=api_output_tokens,
            source=MeasurementSource.API_USAGE,
        )

    if tokenizer is None:
        raise ConfigurationError(
            "A matching tokenizer is required when API token usage is incomplete"
        )
    input_tokens = tokenizer.count_tokens(prompt_text)
    output_tokens = tokenizer.count_tokens(output_text)
    _validate_token_count(input_tokens, "tokenizer input_tokens")
    _validate_token_count(output_tokens, "tokenizer output_tokens")
    return ResolvedTokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        source=MeasurementSource.TOKENIZER_ESTIMATE,
    )


def _validate_token_count(value: int, field_name: str) -> None:
    """校验 token 数为非负整数。"""

    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ConfigurationError(f"{field_name} must be a non-negative integer")


__all__ = ["ResolvedTokenUsage", "TokenCounter", "resolve_token_usage"]
