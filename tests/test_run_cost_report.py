"""每次运行成本报告的纯离线测试。"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from memory_benchmark.analysis.cost import APILLMPrice, load_pricing
from memory_benchmark.core import ConfigurationError


def test_load_ohmygpt_pricing_parses_api_and_skips_local_model() -> None:
    """加载器应强类型解析占位 API 价格，并把本地模型留给 inventory 处理。"""

    prices = load_pricing(Path("configs/pricing/ohmygpt.toml"))

    assert prices == {
        "gpt-4o-mini": APILLMPrice(
            input_cost_per_million_tokens=Decimal("0.0"),
            output_cost_per_million_tokens=Decimal("0.0"),
            currency="USD",
        )
    }
    assert "all-MiniLM-L6-v2" not in prices


def test_load_pricing_fails_fast_on_missing_field(tmp_path: Path) -> None:
    """API 价格缺字段时应立即失败，不能生成不完整价格对象。"""

    path = tmp_path / "broken.toml"
    path.write_text(
        """
[[models]]
model_id = "model"
kind = "llm"
execution_mode = "api"
input_cost_per_million_tokens = 1.0
currency = "USD"
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="output_cost_per_million_tokens"):
        load_pricing(path)
