"""benchmark adapter 统一入口与工厂函数。"""

from __future__ import annotations

from pathlib import Path

from memory_benchmark.core.exceptions import ConfigurationError

from .base import BenchmarkAdapter
from .beam import BeamAdapter
from .halumem import HaluMemAdapter
from .locomo import LoCoMoAdapter
from .longmemeval import LongMemEvalAdapter
from .membench import MemBenchAdapter


SUPPORTED_BENCHMARKS = ("locomo", "longmemeval", "halumem", "beam", "membench")


def list_benchmarks() -> list[str]:
    """返回支持的 benchmark 名称列表。"""
    return list(SUPPORTED_BENCHMARKS)


def get_adapter(
    name: str,
    project_root: str | Path = ".",
    *,
    variant: str | None = None,
) -> BenchmarkAdapter:
    """根据 benchmark 名称与可选 variant 实例化对应的 BenchmarkAdapter。"""
    normalized = name.strip().lower()
    if normalized == "locomo":
        return LoCoMoAdapter(project_root)
    if normalized == "longmemeval":
        return LongMemEvalAdapter(project_root, variant=variant or "s_cleaned")
    if normalized == "halumem":
        return HaluMemAdapter(project_root, variant=variant or "medium")
    if normalized == "beam":
        return BeamAdapter(project_root, variant=variant or "100k")
    if normalized == "membench":
        return MemBenchAdapter(project_root, variant=variant or "0_10k")
    raise ConfigurationError(
        f"Unknown benchmark '{name}'. Supported: {', '.join(SUPPORTED_BENCHMARKS)}"
    )


__all__ = [
    "BeamAdapter",
    "BenchmarkAdapter",
    "HaluMemAdapter",
    "LoCoMoAdapter",
    "LongMemEvalAdapter",
    "MemBenchAdapter",
    "SUPPORTED_BENCHMARKS",
    "get_adapter",
    "list_benchmarks",
]
