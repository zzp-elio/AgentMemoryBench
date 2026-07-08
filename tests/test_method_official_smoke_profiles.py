"""method smoke profile 的官方参数约束测试。

本文件不调用真实 API，也不加载第三方模型。测试目标是锁定项目约定：
smoke 只缩小 benchmark 数据规模，不降低 method 内部的官方检索/回答参数。
"""

from __future__ import annotations

from pathlib import Path

from memory_benchmark.methods.amem_adapter import AMemConfig
from memory_benchmark.methods.lightmem_adapter import LightMemConfig
from memory_benchmark.methods.mem0_adapter import Mem0Config
from memory_benchmark.methods.memoryos_adapter import MemoryOSPaperConfig
from memory_benchmark.methods.registry import load_method_profile


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_smoke_profiles_keep_official_method_parameters() -> None:
    """smoke profile 必须保留官方 method 参数，成本控制交给数据规模裁剪。

    输入:
        无；测试直接从 `configs/methods/*.toml` 读取各 method 的 smoke profile。

    输出:
        无返回值；断言关键参数与官方复现设置一致。
    """

    amem = load_method_profile("amem", "smoke", PROJECT_ROOT)
    lightmem = load_method_profile("lightmem", "smoke", PROJECT_ROOT)
    mem0 = load_method_profile("mem0", "smoke", PROJECT_ROOT)
    memoryos = load_method_profile("memoryos", "smoke", PROJECT_ROOT)

    assert isinstance(amem, AMemConfig)
    assert amem.retrieve_k == 10

    assert isinstance(lightmem, LightMemConfig)
    assert lightmem.retrieve_limit == 60

    assert isinstance(mem0, Mem0Config)
    assert mem0.top_k == 200

    assert isinstance(memoryos, MemoryOSPaperConfig)
    assert memoryos.short_term_capacity == 10
    assert memoryos.mid_term_capacity == 2000
    assert memoryos.long_term_knowledge_capacity == 100
    assert memoryos.mid_term_heat_threshold == 5.0
    assert memoryos.top_k_sessions == 5
    assert memoryos.retrieval_queue_capacity == 7
