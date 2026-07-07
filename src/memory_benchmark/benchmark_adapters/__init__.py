"""benchmark adapter 注册入口。

本入口暴露已迁移的 concrete adapter 和稳定 registry API。
"""

from .base import BenchmarkAdapter
from .contracts import (
    BenchmarkLoadRequest,
    BenchmarkVariantSpec,
    PreparedBenchmarkRun,
    RunScope,
)
from .locomo import LoCoMoAdapter
from .longmemeval import LongMemEvalAdapter
from .halumem import HaluMemAdapter
from .registry import (
    BenchmarkRegistration,
    BenchmarkRegistry,
    get_adapter,
    get_benchmark_registration,
    list_benchmarks,
    list_prediction_benchmarks,
    resolve_variant_selector,
)

__all__ = [
    "BenchmarkAdapter",
    "BenchmarkLoadRequest",
    "BenchmarkRegistration",
    "BenchmarkRegistry",
    "BenchmarkVariantSpec",
    "PreparedBenchmarkRun",
    "HaluMemAdapter",
    "LoCoMoAdapter",
    "LongMemEvalAdapter",
    "RunScope",
    "get_adapter",
    "get_benchmark_registration",
    "list_benchmarks",
    "list_prediction_benchmarks",
    "resolve_variant_selector",
]
