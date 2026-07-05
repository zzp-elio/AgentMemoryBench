# 项目路线图

更新日期：2026-07-05。本文件是唯一方向文档：Phase 1 目标、workstream 索引与
全局约束。逐任务状态见各 workstream README；2026-06 的历史阶段记录（Phase E-S）
已归档到 `archive/status/2026-07-04-current-roadmap.md` 与
`archive/status/2026-07-04-task-ledger.md`。

## Phase 1 目标（2026-07-04 锁定）

围绕固定范围建立可复现、可审计的评测矩阵：

- **Benchmark（5）**：LoCoMo、LongMemEval、HaluMem、BEAM、MemBench。
- **Method（10）**：学术型 A-Mem、MemoryOS、MemOS、LightMem、SimpleMem；
  工程型 Mem0、Letta/MemGPT、Cognee、LangMem、Supermemory（仅 self-host/local OSS）。
- **Metric**：每个 benchmark 尽可能多地覆盖官方 metric。

已实现基线（截至 2026-07-05）：LoCoMo、LongMemEval 两个 adapter；
Mem0、MemoryOS、A-Mem、LightMem 四个 method 已按 retrieve-first 主协议接入并通过
真实 API smoke；效率观测、conversation 级并行/resume、CLI v2、自定义 method
轻量接入（`--method-class`）均已落地。范围锁定不等于已实现——其余 3 benchmark
与 6 method 的接入由 ws02 规划派生。

## Workstream 索引

| ID | 名称 | 状态 | 优先级 | 说明 |
| --- | --- | --- | --- | --- |
| [ws01](workstreams/ws01-docs-governance/README.md) | docs-governance | done | P0 | 文档治理与任务树重构（2026-07-05 终验通过） |
| [ws02](workstreams/ws02-phase1-matrix/README.md) | phase1-matrix | open | P0 | 5×10 矩阵调研收尾、接入规划与 adapter 派生（主线） |
| [ws03](workstreams/ws03-architecture-slimming/README.md) | architecture-slimming | open | P1 | registry/capability/legacy 接口与 CLI 减重、LLMRuntimeConfig |
| [ws04](workstreams/ws04-terminal-observability/README.md) | terminal-observability | open | P2 | isolated 进度心跳、第三方 stdout/tqdm 治理 |
| [ws05](workstreams/ws05-experiment-reporting/README.md) | experiment-reporting | open | P1 | 成本估算（ohmygpt 实价）、结果汇总、full 实验决策 |
| [ws06](workstreams/ws06-tests-restructure/README.md) | tests-restructure | open | P2 | tests 分组重组、大文件拆分、过时断言排查 |

新 workstream 的建立与命名规则见 `AGENTS.md` "文档规则"。

## 全局约束（长期有效，硬规则全文见 AGENTS.md）

- 不启动全量付费 API 实验；任何真实 run 需用户确认预算、规模与 run_id。
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
