"""效率观测 token 计量来源与回退规则测试。"""

from __future__ import annotations

import pytest

from memory_benchmark.core import ConfigurationError
from memory_benchmark.observability.efficiency import MeasurementSource
from memory_benchmark.observability.efficiency.token_counting import (
    resolve_token_usage,
)


class _FixedTokenCounter:
    """返回固定 token 数的测试 tokenizer。"""

    def count_tokens(self, text: str) -> int:
        """按输入文本类型返回稳定测试值。"""

        return 13 if text == "prompt" else 3


def test_api_usage_tokens_override_tokenizer_estimate() -> None:
    """API usage 完整时不得再次调用 tokenizer 估算。"""

    class _FailingCounter:
        """若被调用就让测试失败的 tokenizer。"""

        def count_tokens(self, text: str) -> int:
            """证明 API usage 分支不会触发估算。"""

            raise AssertionError("tokenizer should not be called")

    result = resolve_token_usage(
        api_input_tokens=11,
        api_output_tokens=2,
        prompt_text="prompt",
        output_text="output",
        tokenizer=_FailingCounter(),
    )

    assert result.input_tokens == 11
    assert result.output_tokens == 2
    assert result.source is MeasurementSource.API_USAGE


def test_tokenizer_is_used_when_api_usage_is_missing() -> None:
    """API 不返回 usage 时使用匹配 tokenizer，并明确标记为估算。"""

    result = resolve_token_usage(
        api_input_tokens=None,
        api_output_tokens=None,
        prompt_text="prompt",
        output_text="output",
        tokenizer=_FixedTokenCounter(),
    )

    assert result.input_tokens == 13
    assert result.output_tokens == 3
    assert result.source is MeasurementSource.TOKENIZER_ESTIMATE


def test_partial_api_usage_falls_back_for_both_sides() -> None:
    """API usage 不完整时不能混合真实 input 和估算 output。"""

    result = resolve_token_usage(
        api_input_tokens=99,
        api_output_tokens=None,
        prompt_text="prompt",
        output_text="output",
        tokenizer=_FixedTokenCounter(),
    )

    assert result.input_tokens == 13
    assert result.output_tokens == 3
    assert result.source is MeasurementSource.TOKENIZER_ESTIMATE


def test_missing_usage_and_tokenizer_is_rejected() -> None:
    """既没有 API usage 又没有 tokenizer 时不能伪造 token。"""

    with pytest.raises(ConfigurationError, match="tokenizer"):
        resolve_token_usage(
            api_input_tokens=None,
            api_output_tokens=None,
            prompt_text="prompt",
            output_text="output",
            tokenizer=None,
        )


def test_negative_api_usage_is_rejected() -> None:
    """API 返回的非法负 token 必须报错。"""

    with pytest.raises(ConfigurationError, match="api_input_tokens"):
        resolve_token_usage(
            api_input_tokens=-1,
            api_output_tokens=2,
            prompt_text="prompt",
            output_text="output",
            tokenizer=_FixedTokenCounter(),
        )
