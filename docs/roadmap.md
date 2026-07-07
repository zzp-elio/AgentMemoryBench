# 项目路线图

更新日期：2026-07-05。本文件是唯一方向文档：Phase 1 目标、workstream 索引与
全局约束。逐任务状态见各 workstream README；2026-06 的历史阶段记录（Phase E-S）
已归档到 `archive/status/2026-07-04-current-roadmap.md` 与
`archive/status/2026-07-04-task-ledger.md`。

## Phase 1 目标（2026-07-04 锁定范围；里程碑 2026-07-20）

- **Benchmark（5）**：LoCoMo、LongMemEval、HaluMem、BEAM、MemBench。
- **Method（10）**：学术型 A-Mem、MemoryOS、MemOS、LightMem、SimpleMem；
  工程型 Mem0、Letta/MemGPT、Cognee、LangMem、Supermemory（仅 self-host/local OSS）。

**Phase 1 的完成判据不是全量实验，而是 5×10 smoke 矩阵**（2026-07-05 与用户
重新对齐）：每个可行组合跑通极小规模真实测试并写出成本 observation；汇总为
全矩阵成本估算表（ohmygpt 实价），作为与导师讨论全量预算的申请材料；不可行
组合记录 gap 与原因，不强行接入。全量实验在预算获批后另启，前置条件是失败
恢复/防 API 空烧兜底工程通过验证；已有 LoCoMo full 结果届时在完成后的 5×10
架构下用新 run_id 重跑。

已实现基线（截至 2026-07-05）：LoCoMo、LongMemEval 两个 adapter；Mem0、
MemoryOS、A-Mem、LightMem 四个 method 已按 retrieve-first 主协议接入并通过
真实极小 smoke（LoCoMo 4-method full 已有历史结果；LongMemEval 1-conv cost
pilot 已完成）；效率观测、conversation 级并行/resume、CLI v2、自定义 method
轻量接入均已落地。缺口：3 个新 benchmark adapter、6 个新 method adapter。

## Workstream 索引

| ID | 名称 | 状态 | 优先级 | 说明 |
| --- | --- | --- | --- | --- |
| [ws01](workstreams/ws01-docs-governance/README.md) | docs-governance | done | P0 | 文档治理与任务树重构（2026-07-05 终验通过） |
| [ws02](workstreams/ws02-phase1-matrix/README.md) | phase1-matrix | open | P0 | 5×10 smoke 矩阵（里程碑 7.20）：method 审计、新 adapter、极小 smoke（主线） |
| [ws02.1](workstreams/ws02.1-membench/README.md) | membench-adapter | in-progress | P0 | MemBench 接入，spec 已批准、plan 已备（含首条 unified prompt 链路） |
| [ws02.4](workstreams/ws02.4-simplemem/README.md) | simplemem-adapter | in-progress | P0 | SimpleMem 接入（Track C 首个新 method），已批准待施工 |
| [ws03](workstreams/ws03-architecture-slimming/README.md) | architecture-slimming | open | P1 | registry/capability/legacy 接口与 CLI 减重、LLMRuntimeConfig |
| [ws04](workstreams/ws04-terminal-observability/README.md) | terminal-observability | open | P2 | isolated 进度心跳、第三方 stdout/tqdm 治理 |
| [ws05](workstreams/ws05-experiment-reporting/README.md) | experiment-reporting | open | P1 | 全量实验申请材料：成本估算表 + 结果汇总 + 兜底验证清单（依赖 ws02） |
| [ws06](workstreams/ws06-tests-restructure/README.md) | tests-restructure | open | P2 | tests 分组重组、大文件拆分、过时断言排查 |

新 workstream 的建立与命名规则见 `AGENTS.md` "文档规则"。

## 全局约束（长期有效，硬规则全文见 AGENTS.md）

- **预算强约束**：全量实验必须先有成本估算表并经导师/用户批准；当前阶段一切
  真实 run 均为极小规模。任何真实 run 需用户确认预算、规模与 run_id。
- smoke 使用官方 method 参数；成本控制只通过数据规模裁剪，不降 `top_k` 等参数。
- 不合并不同 dataset variant 的 run；不创建 method × benchmark 专用 runner。
- 真实费用按实际 API 服务商（ohmygpt）价格离线计算，不绑定 OpenAI 官方价。
- `outputs/memoryos-locomo-full-20260603/` 是受保护实验资产。

## 恢复流程（新窗口 / 新上下文）

1. 读 `AGENTS.md` → `docs/README.md` → 本文件。
2. 进入目标 workstream 的 README，从"当前断点"继续。
3. 涉及真实实验时，先查 `outputs/<run_id>/checkpoints/progress.json`、
   `conversation_status.json` 和 `summaries/summary.json`。
4. 不要依据 archive 内旧文档的"待办"直接开工，先核对 workstream 状态页。
