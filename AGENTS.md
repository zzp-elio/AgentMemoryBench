# Agent Memory Benchmark Framework 入口

本文件是静态入口：只放项目定位、硬规则、协作模式和导航。任务进展一律看
`docs/roadmap.md` 和对应 workstream README；本文件不记录逐任务状态。
历史版本（2026-06 流水账）在 `docs/archive/status/2026-07-04-agents-log.md`。

## 项目定位

- 长期目标：可复现、可扩展、可审计的多 task-family Agent Memory Benchmark 框架。
- Phase 1 固定范围（2026-07-04 锁定）：5 benchmark（LoCoMo、LongMemEval、HaluMem、
  BEAM、MemBench）× 10 method（学术型 A-Mem、MemoryOS、MemOS、LightMem、SimpleMem；
  工程型 Mem0、Letta/MemGPT、Cognee、LangMem、Supermemory）× 尽可能多 metric。
  Supermemory 只按 self-host/local OSS 口径接入；Zep 与 Graphiti 不进 Phase 1。
- 主协议 retrieve-first：`BaseMemoryProvider.add(conversation)` +
  `retrieve(question) -> AnswerPromptResult.prompt_messages`，framework reader 统一
  执行 answer LLM。旧 `BaseMemorySystem.add + get_answer` 仅为兼容路径。
- 当前所有真实 LLM 调用统一 `gpt-4o-mini`；未经用户改口不得切换模型。

## 协作模式

- **Claude Code = 架构师**：写 spec/plan、裁定断点冲突、审查验收、把控方向与结构。
- **Codex = 执行者**：严格按 plan 施工，逐 task 勾选并附验收命令的实际输出；
  遇到 plan 未覆盖的情况停止当前 task，写入 workstream README 的"当前断点"，
  交回架构师，不自行发散。
- **OpenCode = 后备力量（2026-07-05 起待命）**：暂不参与项目推进；如需启用由
  用户明确指派，入口仍为 `opencode/opencode_result.md`。
- 执行者报告完成不等于任务完成；验收以架构师复跑命令的输出为准。

## 硬规则

- 禁止修改 `third_party/` 第三方核心算法；仅允许经记录、可关闭、行为等价的
  纯观测插桩。
- 私有数据（gold answers、evidence、judge labels）绝不可达 method。
- 未经用户显式确认（预算、规模、run_id），不得调用真实 API；smoke 必须使用
  官方 method 参数，成本控制只通过 conversation/question/turn 规模裁剪。
- 不创建 method × benchmark 专用 runner；不合并不同 dataset variant 的 run。
- `outputs/` 是实验资产，`outputs/memoryos-locomo-full-20260603/` 受保护；
  `data/`、`models/`、`outputs/`、`third_party/benchmarks/` 不入 git。
- 所有 Python 文件必须有中文模块 docstring；类/函数需要中文 docstring。
- 未经用户要求不自动 commit / push。
- resume 逻辑、隐私边界、metric 正确性、公开协议变更必须经架构师 review。

## 文档规则

- 新任务先判断规模：一次会话内能完成的小修，记入当前 workstream 的任务清单；
  需要独立 spec/plan 的，新建 `docs/workstreams/ws<ID>-<name>/`，ID 挂在父任务下
  （如 ws02.1），目录内含 README.md（状态页）、spec.md、plan.md、notes/。
- 状态只写两处：本 workstream README（勾选 + 断点 + 验收证据）+
  `docs/roadmap.md` 索引表对应行（仅整体状态变化时）。
- 历史文档在 `docs/archive/`，只读；与现状冲突时以 workstream README 为准。

## 导航

1. `docs/README.md` — 文档地图与本地目录说明。
2. `docs/roadmap.md` — Phase 1 目标、workstream 索引、全局约束、恢复流程。
3. `docs/workstreams/<ws>/README.md` — 各任务线的状态页与当前断点。
4. 常用参考：`docs/reference/`（架构、数据模型、method 接口清单、接入指南）、
   `docs/survey/`（benchmark 调研卡片）、`CLAUDE.md`（命令与代码结构速查）。
