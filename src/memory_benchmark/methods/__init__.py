"""method adapter 对外导出入口。

本模块只导出本项目维护的 method 适配类，runner 后续应从这里或明确的
`memory_benchmark.methods.<name>_adapter` 模块导入，而不是直接依赖第三方源码。
"""

from .amem_adapter import AMem, AMemConfig, build_amem_source_identity
from .lightmem_adapter import LightMem, LightMemConfig, build_lightmem_source_identity
from .mem0_adapter import Mem0
from .memoryos_adapter import (
    MemoryOS,
    MemoryOSAddEstimate,
    MemoryOSPaperConfig,
    build_memoryos_source_identity,
)
from .simplemem_adapter import (
    SimpleMem,
    SimpleMemConfig,
    build_simplemem_source_identity,
)
from .registry import (
    MethodBuildContext,
    MethodRegistration,
    get_method_registration,
    list_methods,
    load_method_profile,
)

__all__ = [
    "AMem",
    "AMemConfig",
    "build_amem_source_identity",
    "LightMem",
    "LightMemConfig",
    "build_lightmem_source_identity",
    "Mem0",
    "MemoryOS",
    "MemoryOSAddEstimate",
    "MemoryOSPaperConfig",
    "build_memoryos_source_identity",
    "SimpleMem",
    "SimpleMemConfig",
    "build_simplemem_source_identity",
    "MethodBuildContext",
    "MethodRegistration",
    "get_method_registration",
    "list_methods",
    "load_method_profile",
]
