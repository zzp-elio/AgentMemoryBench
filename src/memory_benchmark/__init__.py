"""Agent Memory Benchmark 框架包入口。

本模块只放框架级元信息。业务实体在 `core/`，benchmark 适配逻辑在
`benchmark_adapters/`，运行入口在 `cli/` 或未来的 `runners/`。
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
