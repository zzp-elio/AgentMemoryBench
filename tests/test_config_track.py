"""method 双轨运行配置 resolver 的离线测试。"""

from __future__ import annotations

import pytest

from memory_benchmark.core import ConfigurationError
from memory_benchmark.evaluators.longmemeval_judge import LongMemEvalJudgeEvaluator
from memory_benchmark.evaluators.locomo_judge import LoCoMoJudgeEvaluator
from memory_benchmark.core import AnswerResult, GoldAnswerInfo, Question
from memory_benchmark.methods.config_track import resolve_config_track
from memory_benchmark.methods.lightmem_native_prompts import (
    LIGHTMEM_LOCOMO_NATIVE_JUDGE_PROMPT,
)
from memory_benchmark.cli.run_prediction import _build_method_manifest


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


@pytest.mark.parametrize("benchmark", ("locomo", "longmemeval", "beam"))
def test_mem0_native_config_track_resolves_registered_bundle(benchmark: str) -> None:
    """Mem0 三个官方 harness 格应解析为完整 native bundle。"""

    bundle = resolve_config_track("mem0", benchmark, "native")

    assert bundle is not None
    assert bundle.answer_prompt_source == "provider_prompt_messages"
    assert bundle.answer_llm_settings.model == "gpt-4o-mini"
    assert bundle.answer_llm_settings.to_manifest_dict() == {
        "message_role": "user",
        "temperature": 0.0,
        "max_tokens": 4096,
        "top_p": None,
        "timeout_seconds": 60.0,
        "max_retries": 8,
    }
    assert bundle.judge_profile.profile_name.startswith(f"mem0_{benchmark}")
    assert bundle.judge_profile.prompt_template
    assert bundle.embedding_ref == "mem0.repo_default.openai.text-embedding-3-small"
    assert bundle.hyperparam_ref == "mem0.memory-benchmarks.repo_default"


@pytest.mark.parametrize("benchmark", ("membench", "halumem"))
def test_mem0_native_config_track_rejects_single_track_grid(
    benchmark: str,
) -> None:
    """Mem0 无官方 harness 的两格必须继续 fail-fast。"""

    with pytest.raises(ConfigurationError, match="No native config-track bundle"):
        resolve_config_track("mem0", benchmark, "native")


def test_config_track_rejects_unknown_track() -> None:
    """配置轨名称只接受政策定义的两个值。"""

    with pytest.raises(ConfigurationError, match="config_track"):
        resolve_config_track("lightmem", "locomo", "paper")


def test_unified_manifest_is_byte_shape_compatible_and_native_adds_identity() -> None:
    """unified 缺省不得新增字段，native 必须进入 resume 身份。"""

    kwargs = {
        "config_manifest": {"profile_name": "smoke"},
        "source_identity": {"source_sha256": "abc"},
        "workload_estimate": None,
        "answer_reader_manifest": {"answer_protocol": "retrieve_first_v1"},
        "prompt_track": "unified",
    }
    expected_unified = {
        "config": {"profile_name": "smoke"},
        "source": {"source_sha256": "abc"},
        "answer_reader": {"answer_protocol": "retrieve_first_v1"},
        "prompt_track": "unified",
    }

    assert _build_method_manifest(**kwargs) == expected_unified
    assert _build_method_manifest(
        **{**kwargs, "prompt_track": "native"}, config_track="native"
    ) == {
        **expected_unified,
        "prompt_track": "native",
        "config_track": "native",
    }


def test_lightmem_native_locomo_judge_uses_exact_prompt_and_category_skip() -> None:
    """native LoCoMo judge 应使用逐字 profile，并按官方跳过 category 5。"""

    bundle = resolve_config_track("lightmem", "locomo", "native")
    assert bundle is not None
    profile = bundle.judge_profile
    evaluator = LoCoMoJudgeEvaluator(
        mode="compact",
        prompt_template_override=profile.prompt_template,
        skipped_categories=profile.skipped_categories,
        prompt_profile_override=profile.profile_name,
    )
    question = Question("q1", "c1", "What happened?", category="1")

    assert evaluator.build_prompt(
        question,
        AnswerResult("q1", "c1", "generated"),
        GoldAnswerInfo("q1", "gold"),
    ) == LIGHTMEM_LOCOMO_NATIVE_JUDGE_PROMPT.format(
        question="What happened?",
        gold_answer="gold",
        generated_answer="generated",
    )
    assert evaluator.should_skip_category(5) is True
    assert evaluator.should_skip_category("5") is True
    assert evaluator.should_skip_category(4) is False
