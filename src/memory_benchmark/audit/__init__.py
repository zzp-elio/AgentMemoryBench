"""B0 method-neutral benchmark probe 包。

本包只提供用于校验 benchmark/runner/registry 是否忠实调用 v3 协议
（`MemoryProvider`）的中性探针 provider。探针不包含任何真实记忆算法，不
访问网络、文件或数据库，也不能通过构造参数注入任何 benchmark 专用答案或
私有标签。它只证明协议调用本身正确，不代表任何 Phase 1 method 的实际效果
或效率。
"""

from __future__ import annotations

from .benchmark_probe import (
    BenchmarkProbeProvider,
    FailureHook,
    ProbeControlledFailure,
    ProbeFailureTrigger,
)

__all__ = [
    "BenchmarkProbeProvider",
    "FailureHook",
    "ProbeControlledFailure",
    "ProbeFailureTrigger",
]
