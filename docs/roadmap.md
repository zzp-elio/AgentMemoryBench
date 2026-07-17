# 项目路线图

更新日期：2026-07-16。本文件是唯一方向文档：Phase 1 目标、workstream 索引与
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

当前基线（2026-07-17）：5 个 benchmark adapter 全部 frozen-v1；已有 5 个 method
adapter（Mem0、MemoryOS、A-Mem、LightMem、SimpleMem）。Mem0 的既有 13 格证据保留，
source-time renderer 已完成单次 effective-time 离线修复，MemBench/BEAM/HaluMem 的内容
抽查并入后续 product-default B11，LoCoMo/LongMemEval 不受影响；MemoryOS M2 离线实现门
通过，Track identity M0 R1/R2 已强验收，当前主树全量基线
`1500 passed, 3 deselected, 2 warnings, 29 subtests passed`；MemoryOS 排在 LightMem/Mem0
重认证之后再进入五格真实 smoke。LightMem 曾 frozen-v1，但 2026-07-15 发现 LoCoMo post-update 无法提供
semantic source mapping，B5/B11 已重开，既有 LoCoMo Recall@10 撤销并应改为 N/A，
其他 answer/成本证据不受影响。逐题 RetrievalEvidence M0/M1 已强验收；LightMem caption v6
也已关闭 B2/B4，当前只待最新 build 的 B11 五格 smoke。Mem0 ADD-only 审计已验收，mutation
结论不受 B4 文本去重影响，
但 provenance 收紧为 LoCoMo/MemBench=turn、LongMemEval=session、BEAM Recall=N/A；
LongMemEval rank 另发现无目标题分母与 k30/50 depth 缺口。旧协议 V2 的 LoCoMo full
仍不计入 v3 矩阵。旧 `unified/native` 双轨硬编码已由
`docs/reference/method-toml-and-answer-builder-policy.md` 取代：每家一个 TOML，主 smoke/full
section 跨五格固定，作者确有一手配置时才加稀疏 `author_<benchmark>`；embedding 也是普通
TOML 字段，效果实验前再裁共同模型或产品默认，当前 smoke 沿用已验收 MiniLM。旧 TrackIdentity
仅作产物兼容，eval fork 不得藏进配置名字。Mem0/LightMem/MemoryOS 的 product default、
generic/eval/build-axis 与 MemoryOS PyPI/ChromaDB 关系已完成审计和架构裁决；truthful track
identity M0 已经 R1/R2、严格 resume/evaluate 和全量回归关闭。现按 LightMem → Mem0 → MemoryOS →
A-Mem → SimpleMem 串行重认证 B1-B11，不靠历史 frozen 惯性，也不盲目重烧未变资产。

缺口：5 个尚无 adapter 的 method（MemOS、Letta/MemGPT、EverOS、LangMem、
Supermemory）；A-Mem/SimpleMem 尚未逐项冻结；MemoryOS 待真实 smoke；LightMem 待最新 v6
build 的 B11 五格 smoke，不再为 N/A 指标强做 lineage 或付费 smoke。真实 API 一律继续由用户
确认预算、规模与 run_id。

## Workstream 索引

| ID | 名称 | 状态 | 优先级 | 说明 |
| --- | --- | --- | --- | --- |
| [ws01](workstreams/ws01-docs-governance/README.md) | docs-governance | done | P0 | 文档治理与任务树重构（2026-07-05 终验通过） |
| [ws02](workstreams/ws02-phase1-matrix/README.md) | phase1-matrix | open | P0 | 5×10 smoke 矩阵（里程碑 7.20）：method 审计、新 adapter、极小 smoke（主线） |
| [ws02.1](workstreams/ws02.1-membench/README.md) | membench-adapter | accepted | P0 | 100k message 时间 Phase A 已由 ws02.7 强验收合入 `2e6b4d7`，frozen-v1 恢复；LightMem preserve-none 属 method 侧 Phase B；真实 smoke 待预算 |
| [ws02.2](workstreams/ws02.2-halumem/README.md) | halumem-adapter | accepted | P0 | HaluMem operation-level 架构师验收通过（2026-07-08，843 passed + 口径第一手核对）；剩极小真实 smoke 待预算 |
| [ws02.3](workstreams/ws02.3-beam/README.md) | beam-adapter | accepted | P0 | BEAM（conversation-QA + rubric judge）架构师验收通过（2026-07-08，891 passed 干净复跑 + 关键交付第一手抽查）；剩极小真实 smoke 待预算 |
| [ws02.4](workstreams/ws02.4-simplemem/README.md) | simplemem-adapter | accepted | P0 | SimpleMem T1-T6 架构师验收通过（2026-07-07）；剩极小真实 smoke 待预算 |
| [ws02.5](workstreams/ws02.5-method-interface-audit/README.md) | method-interface-audit | done | P0 | 2026-07-09 关闭：5 method 接口审计 + MemoryOS 迁移 + 当时配置归一化；shared embedder 资产保留为 controlled，ws02.7 现审计 product-default 精确身份与迁移/复证面 |
| [ws02.6](workstreams/ws02.6-first-smoke-hardening/README.md) | first-smoke-hardening | done | P0 | 五 benchmark 全部 frozen-v1 + B6 横向总验收完成（2026-07-12）；method 侧已转 ws02.7 |
| [ws02.7](workstreams/ws02.7-method-track/README.md) | method-track-m0 | in-progress | P0 | RetrievalEvidence M1 与 LightMem caption v6 B2/B4 已关闭；当前待 LightMem 最新 build B11，随后按 Mem0 → MemoryOS → A-Mem → SimpleMem 串行；EverOS 最后 |
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
  benchmark 同一套、不 per-benchmark 调优；embedding 同样按每个 method 的 vendored
  product default 锁 provider/model/revision/dimension/normalization/instruction/distance，shared
  backbone 只作兼容 method 的 controlled 补充轨；**paper 声明 ≠ repo 默认时优先 repo
  默认 + 显式记录差异**（政策全文与理由见
  `workstreams/ws02.5-method-interface-audit/README.md` "超参数政策"）。
- 不合并不同 dataset variant 的 run；不创建 method × benchmark 专用 runner。
- 真实费用按实际 API 服务商（ohmygpt）价格离线计算，不绑定 OpenAI 官方价。
- `outputs/memoryos-locomo-full-20260603/` 是受保护实验资产。

## 恢复流程（冷启动与 compaction 分开）

1. **同一架构师 compaction/resume**：由受信任的 Codex hook 自举；只看
   `git status --short`、`git log -5 --oneline`、本表唯一 `in-progress + P0` 行所指
   README 顶部恢复胶囊，以及当前动作的一份判据。不要重读全仓文档。
2. **全新架构师冷启动**：读 `AGENTS.md` → `architect-onboarding.md` 的首次上岗读序；
   不把冷启动读序套到每次压缩。
3. 涉及真实实验时，先查 `outputs/<run_id>/checkpoints/progress.json`、
   `conversation_status.json` 和 `summaries/summary.json`。
4. 不要依据 archive 内旧文档的"待办"直接开工，先核对 workstream 状态页。
