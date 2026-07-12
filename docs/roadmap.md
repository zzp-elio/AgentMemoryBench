# 项目路线图

更新日期：2026-07-08。本文件是唯一方向文档：Phase 1 目标、workstream 索引与
全局约束。逐任务状态见各 workstream README；2026-06 的历史阶段记录（Phase E-S）
已归档到 `archive/status/2026-07-04-current-roadmap.md` 与
`archive/status/2026-07-04-task-ledger.md`。

## Phase 1 目标（2026-07-04 锁定范围；里程碑 2026-07-20）

- **Benchmark（5）**：LoCoMo、LongMemEval、HaluMem、BEAM、MemBench。
- **Method（10）**：学术型 A-Mem、MemoryOS、MemOS、LightMem、SimpleMem；
  工程型 Mem0、Letta/MemGPT、EverOS、LangMem、Supermemory（仅 self-host/local
  OSS）。（2026-07-11 用户拍板：去 Cognee 换 EverOS，`third_party/methods/
  EverOS` 已 vendored，上游活跃故排接入序列最后。）

**Phase 1 的完成判据不是全量实验，而是 5×10 smoke 矩阵**（2026-07-05 与用户
重新对齐）：每个可行组合跑通极小规模真实测试并写出成本 observation；汇总为
全矩阵成本估算表（ohmygpt 实价），作为与导师讨论全量预算的申请材料；不可行
组合记录 gap 与原因，不强行接入。全量实验在预算获批后另启，前置条件是失败
恢复/防 API 空烧兜底工程通过验证；已有 LoCoMo full 结果届时在完成后的 5×10
架构下用新 run_id 重跑。

已实现基线（截至 2026-07-08）：**5 个 benchmark adapter 全部落地**——LoCoMo、
LongMemEval（原有）+ MemBench、HaluMem、BEAM（2026-07-08 架构师验收通过，均过
fake 全链路）；**5 个 method adapter**——Mem0、MemoryOS、A-Mem、LightMem、
SimpleMem；效率观测、conversation 级并行/resume、CLI v2、自定义 method 轻量接入
均已落地。**重要口径澄清（2026-07-08 用户）**：既有 LoCoMo 4-method full 结果是
**旧协议 V2** 跑的、且未记效率指标，**不算 v3 架构下的极小 smoke**——所以 v3
真实 smoke 目前一格都没跑。

未跑真实 smoke，计划（2026-07-08 与用户对齐）：先填满当前 **5 method × 5
benchmark = 25 格**的极小 v3 smoke（LoCoMo 列 5 格都要重跑，旧 V2 full 不进表），
再以后每接一个新 method 只跑它 × 5 benchmark。**前置门 = ws02.5 method 接口
保真审计**（确保用通用产品接口 + formatted_memory 完整，否则 smoke 数字不可信）。

缺口：5 个 method adapter（MemOS、Letta、Cognee、LangMem、Supermemory）；ws02.5
接口审计；真实 5×5 smoke（待预算 + 审计）。

## Workstream 索引

| ID | 名称 | 状态 | 优先级 | 说明 |
| --- | --- | --- | --- | --- |
| [ws01](workstreams/ws01-docs-governance/README.md) | docs-governance | done | P0 | 文档治理与任务树重构（2026-07-05 终验通过） |
| [ws02](workstreams/ws02-phase1-matrix/README.md) | phase1-matrix | open | P0 | 5×10 smoke 矩阵（里程碑 7.20）：method 审计、新 adapter、极小 smoke（主线） |
| [ws02.1](workstreams/ws02.1-membench/README.md) | membench-adapter | accepted | P0 | MemBench T1-T6 架构师验收通过（2026-07-07）；剩极小真实 smoke 待预算 |
| [ws02.2](workstreams/ws02.2-halumem/README.md) | halumem-adapter | accepted | P0 | HaluMem operation-level 架构师验收通过（2026-07-08，843 passed + 口径第一手核对）；剩极小真实 smoke 待预算 |
| [ws02.3](workstreams/ws02.3-beam/README.md) | beam-adapter | accepted | P0 | BEAM（conversation-QA + rubric judge）架构师验收通过（2026-07-08，891 passed 干净复跑 + 关键交付第一手抽查）；剩极小真实 smoke 待预算 |
| [ws02.4](workstreams/ws02.4-simplemem/README.md) | simplemem-adapter | accepted | P0 | SimpleMem T1-T6 架构师验收通过（2026-07-07）；剩极小真实 smoke 待预算 |
| [ws02.5](workstreams/ws02.5-method-interface-audit/README.md) | method-interface-audit | done | P0 | 2026-07-09 关闭：5 method 接口审计 + MemoryOS 迁移 + config 归一化（repo 默认/embedder 统一/LLM 只统一模型名）+ 接口文档全清；**5×5 smoke 前置门已开**，只待预算 |
| [ws02.6](workstreams/ws02.6-first-smoke-hardening/README.md) | first-smoke-hardening | in-progress | P0 | 实验可信度门：**五 benchmark 全部 frozen-v1 + B6 横向总验收完成（2026-07-12）**；method 侧已解冻，下一步 Method Track M0（待用户拍板启动，EverOS 排最后）；基线 1069 passed |
| [ws03](workstreams/ws03-architecture-slimming/README.md) | architecture-slimming | open | P1 | registry/capability/legacy 接口与 CLI 减重、LLMRuntimeConfig |
| [ws04](workstreams/ws04-terminal-observability/README.md) | terminal-observability | open | P2 | isolated 进度心跳、第三方 stdout/tqdm 治理 |
| [ws05](workstreams/ws05-experiment-reporting/README.md) | experiment-reporting | open | P1 | 全量实验申请材料：成本估算表 + 结果汇总 + 兜底验证清单（依赖 ws02） |
| [ws06](workstreams/ws06-tests-restructure/README.md) | tests-restructure | open | P2 | tests 分组重组、大文件拆分、过时断言排查 |

新 workstream 的建立与命名规则见 `AGENTS.md` "文档规则"。

## 全局约束（长期有效，硬规则全文见 AGENTS.md）

- **预算强约束**：全量实验必须先有成本估算表并经导师/用户批准；当前阶段一切
  真实 run 均为极小规模。任何真实 run 需用户确认预算、规模与 run_id。
- smoke 使用官方 method 参数；成本控制只通过数据规模裁剪，不降 `top_k` 等参数。
  超参数一律用 method 官方【repo/产品默认】（非 benchmark 专用调参），跨全部
  benchmark 同一套、不 per-benchmark 调优；**paper 声明 ≠ repo 默认时优先 repo
  默认 + 显式记录差异**（政策全文与理由见
  `workstreams/ws02.5-method-interface-audit/README.md` "超参数政策"）。
- 不合并不同 dataset variant 的 run；不创建 method × benchmark 专用 runner。
- 真实费用按实际 API 服务商（ohmygpt）价格离线计算，不绑定 OpenAI 官方价。
- `outputs/memoryos-locomo-full-20260603/` 是受保护实验资产。

## 恢复流程（新窗口 / 新上下文）

1. 读 `AGENTS.md` → `docs/README.md` → 本文件。
2. 进入目标 workstream 的 README，从"当前断点"继续。
3. 涉及真实实验时，先查 `outputs/<run_id>/checkpoints/progress.json`、
   `conversation_status.json` 和 `summaries/summary.json`。
4. 不要依据 archive 内旧文档的"待办"直接开工，先核对 workstream 状态页。
