---
id: ws02
parent: null
status: open
created: 2026-07-05
---
# ws02 Phase 1 评测矩阵（主线）

## 目标

完成 5 benchmark × 10 method 评测矩阵的调研收尾与接入规划，并按规划顺序派生
各 benchmark / method 的接入子 workstream。完成判据：5 个 benchmark 的 adapter
需求清单与 10 个 method 的可行性审计齐全，接入顺序获用户确认，首批子 workstream
建立并开工。

## 当前断点

- 2026-07-05：调研阶段（原 Phase S）主体已完成——7 份 benchmark 调研卡片位于
  `../../survey/benchmarks/`（BEAM、MemoryAgentBench、MemoryBench、HaluMem、
  MemBench、PersonaMem、MemoryArena），横向简报为其中的
  `meeting-brief-5-benchmarks.md`（名称沿用旧 5-benchmark 命名，内容已覆盖 7 个）。
  5×10 范围已于 2026-07-04 锁定。下一步从下方任务清单第 1 条开始。

## 任务清单

- [ ] 10 个 method 的开源状态、官方实验 benchmark、本地可运行方式、internal
  LLM/embedding 配置、可插桩性审计；Supermemory 单独确认 local OSS API 是否覆盖
  写入、检索、provenance 和效率观测需求（不满足时记录 gap 回用户讨论）。
- [ ] 围绕 5 个锁定 benchmark 整理 adapter feasibility、dataset/resource readiness、
  metric coverage、public/private 字段边界，明确各自第一版接入需要新增的
  runner/evaluator 能力（HaluMem/BEAM/MemBench 卡片中已有初步结论，需收敛成清单）。
- [ ] 汇总 Phase 1 task-family taxonomy：哪些沿用 conversation-QA / retrieve-first
  路径，哪些需要新 runner 或额外接口；决定是否调整 `BaseMemoryProvider`。
- [ ] 制定接入顺序（含预算与依赖），交用户确认后逐项派生 ws02.x 子 workstream。

## 子任务

（待接入顺序确认后建立，如 ws02.1-halumem-adapter 等。）

## 决策记录

- 2026-06-26 用户：暂停工程推进，优先系统性调研 agent memory benchmarks，
  防止框架过拟合 LoCoMo / LongMemEval。
- 2026-07-04 用户与 Codex：锁定 5×10 范围；Supermemory 仅 self-host/local OSS；
  Zep 因 Cloud-first/黑盒不可插桩排除，Graphiti 属 Zep 体系亦不作替代。
- 调研判断标准：输出必须能回答"该 benchmark 需要 method 侧提供哪些能力"，
  而不仅是"这个 benchmark 怎么运行"。
- MemoryBench / MemoryArena / PersonaMem 等未进 Phase 1 的调研结论保留在
  `../../survey/benchmarks/` 供后续 phase 使用。
