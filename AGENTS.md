# Agent Memory Benchmark Framework 入口

本文件是静态入口：只放项目定位、硬规则、协作模式和导航。任务进展一律看
`docs/roadmap.md` 和对应 workstream README；本文件不记录逐任务状态。
历史版本（2026-06 流水账）在 `docs/archive/status/2026-07-04-agents-log.md`。

## 项目定位

- 长期目标：可复现、可扩展、可审计的多 task-family Agent Memory Benchmark 框架。
- Phase 1 固定范围（2026-07-04 锁定，2026-07-11 名单修订）：5 benchmark
  （LoCoMo、LongMemEval、HaluMem、BEAM、MemBench）× 10 method（学术型 A-Mem、
  MemoryOS、MemOS、LightMem、SimpleMem；工程型 Mem0、Letta/MemGPT、EverOS、
  LangMem、Supermemory）× 尽可能多 metric。
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

- **架构师 = 写 spec/plan、裁定断点冲突、审查验收、把控方向与结构**（跨模型轮换：
  Claude → GPT-5.6 → …）。**新架构师冷启动第一入口：
  `docs/reference/architect-onboarding.md`**（唯一交接文档：角色、读序、铁律、
  决策、陷阱;**在途状态一律看活跃 ws README 断点区**,该文不双写;原
  handover-to-next-architect.md 已于 2026-07-14 并入并删除），再配
  `docs/reference/architect-playbook.md`
  （历任踩坑与纪律，供"上任自检"，也是不可用时的备份机制）。
- **执行者（actor）= 跨产品轮换池**（2026-07-07 起）：Codex /
  OpenCode+DeepSeek / WorkBuddy(GLM-5.2) / Claude Sonnet / MiniMax 等，可能随时
  换人、新开会话，**不等于当前 Codex 可启动的 subagent**，一律视为
  "刚进公司的新人"**。**actor 写交接记录时须核实自己会话的实际模型（看系统提示），
  别顺手套用本池里的名字**（2026-07-08 判例：一个 WorkBuddy/GLM-5.2 会话把自己
  误标成"Claude Sonnet"，架构师又照搬未核实——身份自标也要验证，同"验证 actor
  断言"一理）。actor
  规矩全文在 `docs/reference/actor-handbook.md`（上工流程、红线、停工条件、报告
  格式）。**每张 actor 卡本身就是可直接复制发送的自包含 prompt**，禁止在卡尾再套
  一份内容重复的“可转发 prompt”；并把工作量限制在单个 5h 窗口内。卡内列出本批
  要读的最少文件（`AGENTS.md` → 目标
  workstream README → plan 当前批次 → `actor-handbook.md`）和明确停点，不能只丢一份
  大 plan。任务卡仍须自包含、把裁定与口径写全；
  **禁用"纪律照旧""规矩同上"这类只有老搭档才懂的暗语**（新人看不懂，等于没写）。
  **卡内只写给 actor 的执行指令，不写“待选择 actor / 待用户派发 / 暂勿派发”这类
  仓库编制状态**；这些状态只放支线 README 和架构师给用户的交接。卡首必须明确：
  “本卡被发送到当前 actor 会话即代表用户已完成选择与授权，直接执行；不要再选择、
  派发或等待另一个 actor。”不得让同一段文字同时扮演调度台和施工 prompt。
  **默认派发权在用户**：架构师负责写好可直接复制的自包含任务卡并交给用户，由
  用户按跨模型额度和能力选择 actor；只有用户明确要求在当前 Codex 内派 subagent
  时，架构师才可自行启动。不得把"合理下放"误解成默认消耗 Codex 同一额度。
  **任务卡写入仓库不等于已经交给用户派发**：架构师在回复中必须用醒目标识明确写
  “需要派发”或“暂勿派发”，给出卡的可点击路径，并用通俗语言说明这张卡解决什么、
  为什么现在做、它依赖/阻塞哪一步；不能只在长汇报里顺带留一个文件名。
  actor 严格按本批任务卡/plan 施工，只跑一次直接相关的最小自检并报告真实输出；
  **不得默认要求 actor 再开 reviewer subagent、重复一手审计、跑全量回归或自行做最终
  验收**；也不得反向一刀切禁止 actor 自行组织 subagent。架构师约束的是交付物、允许
  文件、预算/API、证据与停工边界，不替 actor 规定内部执行拓扑；subagent 不得扩大
  scope 或替代主 actor 对最终报告负责，发生实质性使用时须在回报中说明。plan 未覆盖
  的情况停工写断点，交回架构师，不自行发散。
- 执行者报告完成不等于任务完成；验收以架构师复跑命令的输出为准，**完成度
  以 git log 为准，不以 actor 最后一条消息为准**（额度耗尽时消息可能错乱）。
  架构师负责关键 diff 审读、定向复跑、最终全量回归和状态冻结；“放慢”是 benchmark/
  method 严格逐个推进，不是让 actor 与架构师重复生产同一份验收证据。
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
- **上下文不是持久记忆**：Codex 上下文窗口有限且会压缩；对话里已经裁定但未落盘的
  内容等同于尚未交接。每次用户拍板、验收阻断、派卡/回卡和架构裁决都应先写入活跃
  workstream README 或对应 spec/note/手册，再依 `git log` 恢复。冷启动才读
  `architect-onboarding.md`；同一会话压缩后只走下条四步恢复门，禁止把冷启动全文读序
  搬进 compact 恢复，也禁止凭残余摘要装作记得。
- **压缩恢复必须可自举**：项目 `.codex/hooks.json` 用
  `SessionStart(source=compact)` 重新注入四步恢复门；hook 首次/变更后须由用户在
  `/hooks` 审核信任。若 hook 未加载，本文就是兜底触发器：只读 `git status --short`、
  `git log -5 --oneline`、活跃 README 顶部恢复胶囊和当前动作的一份判据，禁止全文扫
  docs。hook 只提醒/注入 context，不自动总结或修改项目文档。
- **指标资格不是 method 的义务**：每个 method × benchmark × metric 独立判
  valid/N/A/pending；不能为了填满矩阵而伪造能力。变换输入 lineage 只证明“参与过
  生成”，不等于当前 memory 仍语义承载每个 source fact，禁止直接拿它计算
  Recall/NDCG；N/A 是诚实结果，不是接入失败。

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
- 未经用户要求不自动 commit / push（架构师验收后 commit+push 是既定例外
  模式）。**commit 只 add 显式路径,禁 `-A`/`.`**,commit 前
  `git status --short` 过目（2026-07-14 事故:`add -A` 把用户私人文件推进
  公开 repo,force-with-lease 整改；Claude 本机与受信任的 Codex 项目层各有 advisory
  hook 提醒，但 Git/IDE、未信任项目及其他入口不受保护，**纪律仍以本行为准**）。
  Co-Authored-By 用当前
  模型真名。
- resume 逻辑、隐私边界、metric 正确性、公开协议变更必须经架构师 review。

## 文档规则

- 新任务先判断规模：一次会话内能完成的小修，记入当前 workstream 的任务清单；
  需要独立 spec/plan 的，新建 `docs/workstreams/ws<ID>-<name>/`，ID 挂在父任务下
  （如 ws02.1），目录内含 README.md（状态页）、spec.md、plan.md、notes/。
- 同一 workstream 内的支线一旦同时出现“取证/裁决 + actor 卡”，或预期还会有下一批，
  必须收进 `branches/<slug>/`，由支线 `README.md` 管范围、文档索引与稳定依赖顺序，
  任务卡放
  `cards/`、证据和裁决放 `notes/`；一次性单文档仍可留在 workstream 原层。禁止为整理
  旧历史而无边界地全仓搬家，但活跃支线不得继续把卡和 note 平铺到根目录。权威状态、
  commit/test 快照与当前动作仍只写父 workstream README，不在支线 README 复制。
- 状态只写两处：本 workstream README（勾选 + 断点 + 验收证据）+
  `docs/roadmap.md` 索引表对应行（仅整体状态变化时）。
- 历史文档在 `docs/archive/`，只读；与现状冲突时以 workstream README 为准。

## 导航

1. `docs/README.md` — 文档地图与本地目录说明。
2. `docs/roadmap.md` — Phase 1 目标、workstream 索引、全局约束、恢复流程。
3. `docs/workstreams/<ws>/README.md` — 各任务线的状态页与当前断点。
4. 常用参考：`docs/reference/`——**新架构师上岗先读 `architect-onboarding.md`**；
   另有架构、数据模型、method 接口清单、接入指南；`docs/survey/`（benchmark 调研
   卡片）、`CLAUDE.md`（命令与代码结构速查）。
