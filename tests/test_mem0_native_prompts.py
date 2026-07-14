"""Mem0 memory-benchmarks native prompt 的离线逐字 parity 测试。"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from memory_benchmark.methods.mem0_native_prompts import (
    MEM0_BEAM_NATIVE_ANSWER_PROMPT,
    MEM0_BEAM_NATIVE_JUDGE_PROMPT,
    MEM0_BEAM_NATIVE_JUDGE_SYSTEM_PROMPT,
    MEM0_LOCOMO_NATIVE_ANSWER_PROMPT,
    MEM0_LOCOMO_NATIVE_JUDGE_PROMPT,
    MEM0_LOCOMO_NATIVE_JUDGE_SYSTEM_PROMPT,
    MEM0_LONGMEMEVAL_NATIVE_ANSWER_PROMPT,
    MEM0_LONGMEMEVAL_NATIVE_JUDGE_PROMPT,
    MEM0_NATIVE_ANSWER_PROFILES,
    MEM0_NATIVE_JUDGE_PROFILES,
)


pytestmark = pytest.mark.unit


def _load_official_prompt_module(benchmark: str) -> ModuleType:
    """从 vendored Mem0 memory-benchmarks 现场加载指定 prompt 模块。"""

    prompt_path = (
        Path(__file__).resolve().parents[1]
        / "third_party"
        / "methods"
        / "mem0-main"
        / "memory-benchmarks"
        / "benchmarks"
        / benchmark
        / "prompts.py"
    )
    spec = importlib.util.spec_from_file_location(
        f"_test_mem0_native_{benchmark}_prompts",
        prompt_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mem0_native_answer_prompts_match_official_constants_byte_for_byte() -> None:
    """三格 answer 模板必须与官方模块常量逐字一致。"""

    locomo = _load_official_prompt_module("locomo")
    longmemeval = _load_official_prompt_module("longmemeval")
    beam = _load_official_prompt_module("beam")

    assert MEM0_LOCOMO_NATIVE_ANSWER_PROMPT == locomo.ANSWER_GENERATION_PROMPT
    assert (
        MEM0_LONGMEMEVAL_NATIVE_ANSWER_PROMPT
        == longmemeval.ANSWER_GENERATION_PROMPT
    )
    assert MEM0_BEAM_NATIVE_ANSWER_PROMPT == beam.ANSWER_GENERATION_PROMPT


def test_mem0_native_judge_prompts_match_actual_official_builders() -> None:
    """三格 judge 模板必须跟随实际调用 builder，而非未调用的近似常量。"""

    locomo = _load_official_prompt_module("locomo")
    longmemeval = _load_official_prompt_module("longmemeval")
    beam = _load_official_prompt_module("beam")

    assert MEM0_LOCOMO_NATIVE_JUDGE_PROMPT == locomo.JUDGE_PROMPT
    assert MEM0_LOCOMO_NATIVE_JUDGE_SYSTEM_PROMPT == locomo.JUDGE_SYSTEM_PROMPT
    assert MEM0_LONGMEMEVAL_NATIVE_JUDGE_PROMPT == longmemeval.JUDGE_PROMPT
    assert MEM0_BEAM_NATIVE_JUDGE_SYSTEM_PROMPT == beam.BEAM_JUDGE_SYSTEM_PROMPT
    assert MEM0_BEAM_NATIVE_JUDGE_PROMPT.format(
        question="Question sentinel",
        answer="Rubric sentinel",
        response="Response sentinel",
    ) == beam.get_beam_nugget_judge_prompt(
        "Question sentinel",
        "Rubric sentinel",
        "Response sentinel",
    )


def test_mem0_native_profiles_cover_only_three_official_harness_grids() -> None:
    """profile 注册面只能包含架构师批准的三个官方 harness。"""

    expected = {"locomo", "longmemeval", "beam"}

    assert set(MEM0_NATIVE_ANSWER_PROFILES) == expected
    assert set(MEM0_NATIVE_JUDGE_PROFILES) == expected
    assert all(
        profile.settings.temperature == 0.0
        and profile.settings.max_tokens == 4096
        and profile.settings.top_p is None
        for profile in MEM0_NATIVE_ANSWER_PROFILES.values()
    )
