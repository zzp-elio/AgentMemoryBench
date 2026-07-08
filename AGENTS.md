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
- 主协议 **v3 provider**：`MemoryProvider.ingest(unit) + retrieve(query) ->
  RetrievalResult`，粒度由实例级 `consume_granularity`（turn/pair/session/
  conversation）声明、框架事件流聚合投递；framework reader 统一执行 answer
  LLM（双口径 native/unified）。协议全文：
  `docs/workstreams/ws02-phase1-matrix/spec-protocol-v3.md`。旧
  `BaseMemorySystem` / `BaseMemoryProvider(add+retrieve)` 仅为兼容桥路径。
- **运行主线（4 步，2026-07-08 与用户对齐）**：① 给 method 注入记忆（ingest）；
  ② 用 query 检索记忆（retrieve → `formatted_memory`）——**每个 method 一律用
  通用产品接口，不用 benchmark 专用评测实现**（公平/可比/代表性，见 ws02.5 审计）；
  ③ 用检索回的记忆 + **框架自带的 answer LLM 配置与 answer prompt** 回答问题
  （unified 口径，非 method 原生答题——这样只有"记忆质量"在变，隔离出可比性）；
  ④ 从实验结果算 metric，涉及 LLM judge 时用**框架自带的 judge LLM 配置与
  prompt**。
- **prompt 来源政策**：answer/judge prompt **benchmark 官方仓库有就先用它的**，
  没有才自研（可参考 method 仓库里的 benchmark 评测代码作**格式**参考）。**红线：
  answer/judge prompt 必须 per-benchmark、method 无关**（同一 benchmark 上所有
  method 用同一 prompt），参考 method 代码只借格式、不得引入某 method 的专属优势。
- **native 口径保留作 sanity 交叉核对**：主线用 unified，但框架仍支持 native
  （method 原生 prompt_messages）；对 retrieve 与答题耦合的 method（如
  MemoryOS `get_response`），"忠实抽出 formatted_memory"是难点，正是 ws02.5
  审计要钉死的，native 数可作旁证。
- 当前所有真实 LLM 调用统一 `gpt-4o-mini`；未经用户改口不得切换模型。

## 协作模式

- **Claude Code = 架构师**：写 spec/plan、裁定断点冲突、审查验收、把控方向与结构。
  角色完整交接文档：`docs/reference/architect-playbook.md`（任何 agent 可按其
  "上任自检"接任架构师，作为不可用时的备份机制）。
- **执行者（actor）= 轮换池**（2026-07-07 起）：Codex / OpenCode+DeepSeek /
  WorkBuddy(GLM-5.2) / Claude Sonnet 等，可能随时换人、新开会话，**一律视为
  "刚进公司的新人"**。**actor 写交接记录时须核实自己会话的实际模型（看系统提示），
  别顺手套用本池里的名字**（2026-07-08 判例：一个 WorkBuddy/GLM-5.2 会话把自己
  误标成"Claude Sonnet"，架构师又照搬未核实——身份自标也要验证，同"验证 actor
  断言"一理）。actor
  规矩全文在 `docs/reference/actor-handbook.md`（上工流程、红线、停工条件、报告
  格式）。**每张任务卡必须自包含**：列出要读的文件清单（`AGENTS.md` → 目标
  workstream README → spec/plan → `actor-handbook.md`）、把裁定与口径写全；
  **禁用"纪律照旧""规矩同上"这类只有老搭档才懂的暗语**（新人看不懂，等于没写）。
  严格按 plan 施工，逐 task 勾选并附验收命令的实际输出；plan 未覆盖的情况停工
  写断点，交回架构师，不自行发散。
- 执行者报告完成不等于任务完成；验收以架构师复跑命令的输出为准，**完成度
  以 git log 为准，不以 actor 最后一条消息为准**（额度耗尽时消息可能错乱）。
- **两本经验手册必须持续更新，不是只读不写**（2026-07-08 用户强调）：
  `architect-playbook.md`（架构师经验，知错能改：裁定、被纠正的失误、第一手核查
  手艺）+ `actor-handbook.md`（actor 经验：好/坏行为判例）。**接任的架构师/actor
  的义务不止"读手册"，还包括"用本会话的新经验更新手册"**——每被用户纠正一次、
  每踩一个坑、每发现一个更好的做法，都要落回对应手册，供下一任继承（这是把
  "新项目"变"可快速上手"的关键）。
- **跨模型事实源：仓库内文档（`AGENTS.md` / 两本手册 / workstream 文档）是唯一、
  模型无关的事实源**。Claude 专属的 `~/.claude/projects/.../memory/` 只是 Claude
  的便利缓存，**不得存放仅此一处的项目真相**——下一任架构师可能是 GPT/其他模型，
  读不到该目录。凡继任者必须知道的（用户画像、协作约束、经验教训），仓库内文档
  都要有落点，Claude memory 至多作镜像。

## 硬规则

- `third_party/` 第三方代码**允许修改**（2026-07-05 用户放宽），但**不得改变
  算法核心流程**；用途限于 benchmark 拓展适配（如 MemoryOS 原生只适配 LoCoMo）
  和纯观测插桩。每处改动必须在对应 workstream 记录文件、位置和理由，可回溯。
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
