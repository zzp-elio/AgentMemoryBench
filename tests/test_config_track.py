"""method 双轨运行配置 resolver 的离线测试。"""

from __future__ import annotations

import pytest

from memory_benchmark.core import ConfigurationError
from memory_benchmark.evaluators.longmemeval_judge import LongMemEvalJudgeEvaluator
from memory_benchmark.methods.config_track import resolve_config_track
from memory_benchmark.methods.lightmem_native_prompts import (
    LIGHTMEM_LOCOMO_NATIVE_JUDGE_PROMPT,
)


def test_unified_config_track_returns_no_overrides() -> None:
    """unified 轨必须以 None 哨兵保持既有路径。"""

    assert resolve_config_track("lightmem", "locomo", "unified") is None


@pytest.mark.parametrize("benchmark", ("locomo", "longmemeval"))
def test_lightmem_native_config_track_resolves_registered_bundle(
    benchmark: str,
) -> None:
    """LightMem 两个官方实验格应解析为完整 native bundle。"""

    bundle = resolve_config_track("lightmem", benchmark, "native")

    assert bundle is not None
    assert bundle.answer_prompt_source == "provider_prompt_messages"
    assert bundle.answer_llm_settings.model == "gpt-4o-mini"
    assert bundle.answer_llm_settings.to_manifest_dict() == {
        "message_role": "user",
        "temperature": 0.0,
        "max_tokens": 2000,
        "top_p": 0.8,
        "timeout_seconds": 60.0,
        "max_retries": 8,
    }
    if benchmark == "locomo":
        assert bundle.judge_profile.prompt_template == LIGHTMEM_LOCOMO_NATIVE_JUDGE_PROMPT
    else:
        assert bundle.judge_profile.evaluator_type is LongMemEvalJudgeEvaluator


def test_native_config_track_rejects_unregistered_grid_cell() -> None:
    """single-track 格不得伪造 native bundle。"""

    with pytest.raises(ConfigurationError, match="No native config-track bundle"):
        resolve_config_track("lightmem", "beam", "native")


def test_config_track_rejects_unknown_track() -> None:
    """配置轨名称只接受政策定义的两个值。"""

    with pytest.raises(ConfigurationError, match="config_track"):
        resolve_config_track("lightmem", "locomo", "paper")
