"""method 双轨运行配置解析。

unified 轨用 ``None`` 表示完全沿用既有框架默认；native 轨只解析已经一手锁定的
method × benchmark 配置资产。
"""

from __future__ import annotations

from dataclasses import dataclass

from memory_benchmark.config.settings import AnswerLLMSettings, DEFAULT_OPENAI_MODEL
from memory_benchmark.core import ConfigurationError
from memory_benchmark.methods.lightmem_native_prompts import (
    LIGHTMEM_NATIVE_ANSWER_PROFILES,
    LIGHTMEM_NATIVE_JUDGE_PROFILES,
    LightMemNativeJudgeProfile,
)
from memory_benchmark.methods.mem0_native_prompts import (
    MEM0_NATIVE_ANSWER_PROFILES,
    MEM0_NATIVE_JUDGE_PROFILES,
    Mem0NativeJudgeProfile,
)
from memory_benchmark.methods.memoryos_native_prompts import (
    MEMORYOS_NATIVE_ANSWER_PROFILES,
)


@dataclass(frozen=True)
class ConfigTrackBundle:
    """一个已批准 native 格的运行时配置覆盖。"""

    answer_prompt_source: str
    answer_llm_settings: AnswerLLMSettings
    judge_profile: LightMemNativeJudgeProfile | Mem0NativeJudgeProfile | None
    embedding_ref: str
    hyperparam_ref: str


def _lightmem_bundle(benchmark: str) -> ConfigTrackBundle:
    """由已验收的 LightMem 静态 profile 构造 native bundle。"""

    settings = LIGHTMEM_NATIVE_ANSWER_PROFILES[benchmark].settings
    return ConfigTrackBundle(
        answer_prompt_source="provider_prompt_messages",
        answer_llm_settings=AnswerLLMSettings(
            model=DEFAULT_OPENAI_MODEL,
            message_role="user",
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            top_p=settings.top_p,
        ),
        judge_profile=LIGHTMEM_NATIVE_JUDGE_PROFILES[benchmark],
        embedding_ref="lightmem.repo_default.all-MiniLM-L6-v2",
        hyperparam_ref="lightmem.repo_default",
    )


def _mem0_bundle(benchmark: str) -> ConfigTrackBundle:
    """由 Mem0 memory-benchmarks 静态 profile 构造 native bundle。"""

    settings = MEM0_NATIVE_ANSWER_PROFILES[benchmark].settings
    return ConfigTrackBundle(
        answer_prompt_source="provider_prompt_messages",
        answer_llm_settings=AnswerLLMSettings(
            model=DEFAULT_OPENAI_MODEL,
            message_role="user",
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            top_p=settings.top_p,
        ),
        judge_profile=MEM0_NATIVE_JUDGE_PROFILES[benchmark],
        embedding_ref="mem0.repo_default.openai.text-embedding-3-small",
        hyperparam_ref="mem0.memory-benchmarks.repo_default",
    )


def _memoryos_bundle(benchmark: str) -> ConfigTrackBundle:
    """由 MemoryOS eval readout profile 构造 LoCoMo native bundle。"""

    settings = MEMORYOS_NATIVE_ANSWER_PROFILES[benchmark].settings
    return ConfigTrackBundle(
        answer_prompt_source="provider_prompt_messages",
        answer_llm_settings=settings,
        # 官方评测只有本地 token-set F1；无 method-native LLM judge 资产。
        judge_profile=None,
        embedding_ref="memoryos.readout-native.build-profile-not-yet-wired",
        hyperparam_ref="memoryos.paper.locomo.disputed-build-profile-v1",
    )


_NATIVE_CONFIG_TRACK_BUNDLES = {
    ("lightmem", benchmark): _lightmem_bundle(benchmark)
    for benchmark in ("locomo", "longmemeval")
}
_NATIVE_CONFIG_TRACK_BUNDLES.update(
    {
        ("mem0", benchmark): _mem0_bundle(benchmark)
        for benchmark in ("locomo", "longmemeval", "beam")
    }
)
_NATIVE_CONFIG_TRACK_BUNDLES[("memoryos", "locomo")] = _memoryos_bundle("locomo")


def resolve_config_track(
    method: str,
    benchmark: str,
    config_track: str,
) -> ConfigTrackBundle | None:
    """解析 run 级配置轨；unified 不产生任何覆盖。"""

    normalized_track = config_track.strip().lower()
    if normalized_track == "unified":
        return None
    if normalized_track != "native":
        raise ConfigurationError(
            "config_track must be one of ['native', 'unified']"
        )
    key = (method.strip().lower(), benchmark.strip().lower())
    try:
        return _NATIVE_CONFIG_TRACK_BUNDLES[key]
    except KeyError as exc:
        raise ConfigurationError(
            "No native config-track bundle is registered for "
            f"method='{method}', benchmark='{benchmark}'"
        ) from exc


__all__ = ["ConfigTrackBundle", "resolve_config_track"]
