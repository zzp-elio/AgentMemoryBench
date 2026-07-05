---
id: ws02
parent: null
status: in-progress
created: 2026-07-05
---
# ws02 Phase 1：5×10 Smoke 矩阵（主线，里程碑 2026-07-20）

## 目标

在 2026-07-20 前后完成 5 benchmark × 10 method 的 smoke 矩阵：每个可行组合
跑通极小规模真实测试并写出成本 observation；不可行组合记录 gap 与原因。
完成判据：矩阵覆盖表 + 全矩阵成本估算表（ohmygpt 实价）可交给导师讨论
全量预算。**本 workstream 不做任何全量实验。**

矩阵现状（2026-07-05）：

| | LoCoMo | LongMemEval | HaluMem | BEAM | MemBench |
| --- | --- | --- | --- | --- | --- |
| Mem0 / MemoryOS / A-Mem / LightMem | ✅ smoke+full(历史) | ✅ 1-conv pilot | ⬜ | ⬜ | ⬜ |
| MemOS / SimpleMem / Letta / Cognee / LangMem / Supermemory | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |

## 当前断点

- 2026-07-05 晚：用户叫停 Track B 动工——**先完成 Track 0 协议重评估，再写任何
  adapter 代码**。担忧：当前 `BaseMemoryProvider.add(conversation)` 等核心协议
  是基于 LoCoMo+LongMemEval+4 method 写出来的，可能过拟合；候选方向如
  `add_turn(role, content, time, metadata)`（降低 adapter 负担、贴近 streaming
  ingest）。Track A（method 审计）不受影响可先行，但审计卡片第 4 节按协议中立
  口径写。下一个架构师会话从 Track 0 开工（额度原因本会话未展开）。

## 任务分解（Track 0 前置 + 三条 track）

### Track 0：集成框架调研与核心协议重评估（前置，阻塞 Track B/C 编码）

- [ ] 调研 `第三方框架参考/` 下 5 个集成框架的 method 接口设计、ingest 粒度、
  benchmark 组织方式和第三方代码引入方式（全仓 vendor vs 裁剪/pip）：
  EverOS（评测框架藏在
  `第三方框架参考/EverOS-29d555c6e94de3630f314c1f594fc1801377ff5a/methods/EverCore/evaluation`）、
  MemEval、MemoryData、agent-memory-benchmark、memorybench；另有
  `EVALUATION_ARCHITECTURE.md` 和 supermemoryai 两份笔记。产出对比卡片。
- [ ] 结合 5 benchmark 调研卡片 + 框架对比，重评估核心协议。关键判据：
  ingest 粒度（turn / session / conversation / chunk-stream 哪个是最大公约数）、
  adapter 负担、method 原生批量操作（如 LightMem offline update 需要
  session/conversation 边界信号）、resume 粒度、HaluMem 类 operation 级评测
  的接口压力。候选：保持 `add(conversation)`、改 `add_turn(...)`、或分层
  （`add_turn` 主协议 + 可选 `on_conversation_end()` 边界钩子）。
- [ ] 产出协议重评估 spec（含迁移影响面：4 个现有 adapter、runner、resume），
  用户批准后才恢复 Track B。
- [ ] 顺带评估 third_party 全仓 vendor 是否改为裁剪式引入（参考框架做法）。

### Track A：6 个新 method 可行性审计（无 API 成本，Codex 可先行）

### Track A：6 个新 method 可行性审计（无 API 成本，Codex 可先行）

- [ ] MemOS、SimpleMem、Letta、Cognee、LangMem、Supermemory 逐个审计：
  本地可运行性、内部 LLM/embedding 配置能否指向 ohmygpt/gpt-4o-mini、
  写入/检索接口与 `BaseMemoryProvider.add + retrieve` 的映射、可插桩性、
  依赖冲突风险；Supermemory 单独确认 local OSS API 能力边界。
- [ ] 产出每 method 一份审计卡片 + 接入难度分级，决定接入顺序。

### Track B：3 个新 benchmark adapter（smoke 口径优先）

- [ ] 确定各 benchmark 的 Phase 1 smoke 口径（依据 `../../survey/benchmarks/`
  调研卡片，QA 子集优先，暂缓重型 metric）：MemBench（multiple-choice
  accuracy 先行，tid 隔离保留、evidence recall 缓）、HaluMem（QA 子任务先行，
  operation-level 诊断缓）、BEAM（probing-QA + 基础 judge 先行，
  event-ordering/rubric-nugget 缓）。
- [ ] 每个 benchmark 一份 adapter spec（架构师）→ plan → Codex 施工 →
  离线 fake smoke → 极小真实 smoke。派生子 workstream：ws02.1-membench、
  ws02.2-halumem、ws02.3-beam（建立时更新此处链接）。

### Track C：矩阵填格与成本表

- [ ] 新 method × 已有 benchmark（LoCoMo/LongMemEval）极小 smoke。
- [ ] 已有 4 method × 新 benchmark 极小 smoke。
- [ ] 新 method × 新 benchmark 极小 smoke。
- [ ] 汇总矩阵覆盖表 + 按 ohmygpt 实价的全矩阵成本估算表（交 ws05 组装
  申请材料）。

## 决策记录

- 2026-07-05 用户：Phase 1 完成判据 = smoke 矩阵而非全量实验；全量需先
  拿成本表向导师申请预算；LongMemEval 全量 4 method 约 $500，超出当前预算。
- 2026-07-05 用户：已有 LoCoMo full 结果在 5×10 架构完成后需用新 run_id 重跑。
- 2026-07-04 用户：5×10 范围锁定；Supermemory 仅 self-host/local OSS；
  Zep/Graphiti 排除。
- 调研判断标准：先回答"该 benchmark 需要 method 提供什么能力"再动代码。
