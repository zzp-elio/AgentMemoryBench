# 2026-06-21 Parallel Scope Alignment

## 用户裁定

当前阶段只做 conversation 级并行，不做更复杂的 full parallel 调度。

具体含义：

- prediction / full run 层只支持单个 method × 单个 benchmark 内部的
  conversation-level parallel / resume。
- 不继续推进 shared method instance、method execution policy 矩阵或
  method×benchmark full parallel orchestrator。
- 多个 method 或多个 benchmark 同时跑实验时，当前可以开多个终端分别运行，并使用不同
  `run_id`。
- `calibrate-smoke` 可以继续保留为极小成本校准和批量 smoke 的便利入口，但不作为 full
  实验调度主线。

## 原因

method×benchmark 外层并行的近期收益主要是减少终端数量和统一展示，但会引入额外复杂度：

- 外层 run 调度和内层 conversation worker 叠加后更难控制 API 并发规模。
- 失败恢复、日志、Rich 展示和资源限制会变复杂。
- 当前项目更需要可 debug、小步快跑和可恢复，而不是调度系统复杂度。

## method×benchmark 外层并行的潜在收益

这些收益存在，但当前不足以进入主线：

- 可以把一组实验统一成一个命令，减少用户开多个终端和手动管理 run 的负担。
- 可以集中展示 progress、失败原因和最终矩阵结果。
- 可以在一个调度器里统一限制 API 并发、失败熔断和预算。
- 如果多个 method 使用同一个 benchmark / variant，理论上可以只执行一次 dataset
  load / normalization，然后把只读 dataset 对象复用给多个 child run。

需要注意：dataset 只读一次不是天然成立。如果每个 child run 仍独立进程、独立 loader 或
重新构造 adapter，就不会自动省 IO；必须显式设计 dataset cache / prepared dataset reuse。
并且当前实验主要瓶颈是 LLM/API 调用和第三方 method state，而不是 dataset JSON 读取。

## 已更新文档

- `docs/current-roadmap.md`
- `AGENTS.md`
- `docs/task-ledger.md`
- `README.md`

## 后续条件

只有当真实用户场景明确需要统一排队、统一展示、排行榜批处理或自动批量矩阵实验时，才重新
设计 method×benchmark 外层调度。
