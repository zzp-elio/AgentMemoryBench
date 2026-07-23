"""Prompt 资产所有权与旧 import 兼容的架构回归门。"""

from __future__ import annotations

import ast
from pathlib import Path

from memory_benchmark.benchmark_adapters import locomo_prompt, longmemeval_prompt
from memory_benchmark.evaluators import (
    beam_rubric_judge,
    halumem_prompts,
    locomo_judge,
    longmemeval_judge,
)
from memory_benchmark.methods import (
    lightmem_native_prompts,
    mem0_native_prompts,
    memoryos_native_prompts,
)
from memory_benchmark.prompts.author import lightmem, mem0, memoryos
from memory_benchmark.prompts.benchmarks import beam, halumem_judge, locomo, longmemeval


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_BENCHMARK_PROMPT_ROOT = (
    _PROJECT_ROOT / "src" / "memory_benchmark" / "prompts" / "benchmarks"
)
_ADAPTER_ROOT = _PROJECT_ROOT / "src" / "memory_benchmark" / "benchmark_adapters"
_UNIFIED_BUILDERS = {
    "build_beam_unified_answer_prompt",
    "build_halumem_unified_answer_prompt",
    "build_locomo_unified_answer_prompt",
    "build_longmemeval_unified_answer_prompt",
    "build_membench_unified_answer_prompt",
}


def test_benchmark_prompt_layer_does_not_depend_on_methods() -> None:
    """主表 prompt 不得反向依赖任何 method 实现或作者校准资产。"""

    violations: list[str] = []
    for path in sorted(_BENCHMARK_PROMPT_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name.startswith("memory_benchmark.methods") or name.startswith(
                    "memory_benchmark.prompts.author"
                ):
                    violations.append(f"{path.name}:{node.lineno}: {name}")
    assert violations == []


def test_unified_answer_builders_have_single_canonical_owner() -> None:
    """五家主配置 builder 只能定义在 prompts/benchmarks，adapter 只可转发。"""

    definitions: dict[str, list[str]] = {name: [] for name in _UNIFIED_BUILDERS}
    roots = (_BENCHMARK_PROMPT_ROOT, _ADAPTER_ROOT)
    for root in roots:
        for path in sorted(root.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name in definitions:
                        definitions[node.name].append(str(path.relative_to(_PROJECT_ROOT)))
    assert all(
        locations
        == [f"src/memory_benchmark/prompts/benchmarks/{name.removeprefix('build_').removesuffix('_unified_answer_prompt')}.py"]
        for name, locations in definitions.items()
    )


def test_legacy_prompt_import_paths_reexport_canonical_objects() -> None:
    """旧路径仍可用，但必须转发同一对象而不是复制第二份 prompt。"""

    assert (
        locomo_prompt.build_locomo_unified_answer_prompt
        is locomo.build_locomo_unified_answer_prompt
    )
    assert (
        longmemeval_prompt.build_longmemeval_unified_answer_prompt
        is longmemeval.build_longmemeval_unified_answer_prompt
    )
    assert (
        lightmem_native_prompts.LIGHTMEM_NATIVE_ANSWER_PROFILES
        is lightmem.LIGHTMEM_NATIVE_ANSWER_PROFILES
    )
    assert (
        mem0_native_prompts.MEM0_NATIVE_ANSWER_PROFILES
        is mem0.MEM0_NATIVE_ANSWER_PROFILES
    )
    assert (
        memoryos_native_prompts.MEMORYOS_NATIVE_ANSWER_PROFILES
        is memoryos.MEMORYOS_NATIVE_ANSWER_PROFILES
    )
    assert (
        halumem_prompts.EVALUATION_PROMPT_FOR_QUESTION
        is halumem_judge.EVALUATION_PROMPT_FOR_QUESTION
    )
    assert beam_rubric_judge.BEAM_JUDGE_PROMPT is beam.BEAM_JUDGE_PROMPT
    assert locomo_judge._LOC0MO_JUDGE_PROMPT is locomo.LOCOMO_JUDGE_PROMPT
    assert (
        longmemeval_judge._build_official_longmemeval_judge_prompt
        is longmemeval.build_longmemeval_official_judge_prompt
    )
