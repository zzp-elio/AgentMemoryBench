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

- 2026-07-06（最新）：用户指出已接入的 4 method + 2 benchmark 的调研知识从未
  卡片化（蒸发在旧会话里）。裁定：不从零重调研，**补缺 + 统一口径**——
  Track A2 扩编为全部 10 method 机制卡（plan 已改），新增 Track B0 补全
  benchmark 卡片至 5/5（plan 已备）。两个 plan 都可立即派给 Codex，可先 A2
  后 B0 顺序执行。全部完成后：架构师做粒度需求双向矩阵 → 最终协议 spec。
  教训已吸取：**调研成果必须以卡片入库，不允许只留在会话里**。
- 2026-07-06：用户决定**协议粒度决策缓行**——先充分了解 10 method 机制
  与 5 benchmark 测评方式再定接口；v2 spec 降级为候选方案 A。新增设计约束：
  1-2 个中间层统一形态、多模态与 agentic task family 可扩展性、多粒度并存可能。
  PyPI SSL 问题已解决：改用 `uv venv` + `uv pip install`（架构师实测通过）。
- 2026-07-06（已缓行）：协议 v2 spec 已产出：
  [spec-protocol-v2.md](spec-protocol-v2.md)。输入：五框架对比 + Track A 审计 +
  用户三项决策（双视角不内建 / 显式隔离键 / 并发维持现状 + "并行结果必须等于
  串行"不变量）。spec 内已裁定 Track A 三个未决问题（R1 检索纯度 / R2
  agent-native 走 memory API / R3 异步写入完成判据）。**用户批准后：架构师拆
  P1 实施 plan 交 Codex。** 另：Track A 发现本机 /tmp venv PyPI SSL 证书问题，
  需用户在 Track C smoke 前解决。Track A 审计已由架构师复核通过并入库。
- 2026-07-05 17:55 CST：（已复核）Track A 六个新 method 可行性审计完成，产物位于
  `docs/workstreams/ws02-phase1-matrix/audits/`：MemOS、SimpleMem、LangMem、
  Cognee、Letta、Supermemory 各一张卡片，另有 `summary.md` 汇总表。审计全程
  未调用真实 LLM/embedding API，未修改主环境依赖；安装验证均为 `/tmp` venv
  或 npm dry-run。当前交回架构师复核审计结论与建议接入顺序，尤其是
  LangMem/Letta 是否允许绕过 agent 决策层、Supermemory local OSS 与 Enterprise
  差异是否需要联网核对。
- 2026-07-06：Track 0 第一步完成——五框架对比卡片已产出（见任务清单第 1 条），
  v2 协议草案在卡片 §4，含三个待用户讨论的问题（双视角写入、显式隔离键、
  并发声明位置）。下一步：用户对 §4 草案和三个问题表态后，架构师写正式协议
  重评估 spec（含 4 个现有 adapter 迁移影响面）。Track A 仍可随时开工。
- 2026-07-05 晚：用户叫停 Track B 动工——**先完成 Track 0 协议重评估，再写任何
  adapter 代码**。担忧：当前 `BaseMemoryProvider.add(conversation)` 等核心协议
  是基于 LoCoMo+LongMemEval+4 method 写出来的，可能过拟合；候选方向如
  `add_turn(role, content, time, metadata)`（降低 adapter 负担、贴近 streaming
  ingest）。Track A（method 审计）不受影响可先行，但审计卡片第 4 节按协议中立
  口径写。下一个架构师会话从 Track 0 开工（额度原因本会话未展开）。

## 任务分解（Track 0 前置 + 三条 track）

### Track 0：集成框架调研与核心协议重评估（前置，阻塞 Track B/C 编码）

- [x] 调研 5 个集成框架的接口设计（2026-07-06，Claude 源码实读）：产出
  [track0-framework-comparison.md](track0-framework-comparison.md)。核心发现：
  五框架全部由框架层拆小单元喂 method（chunk/message/document 级），
  无一个直接传整段 Conversation；边界钩子（finalize/awaitIndexing）普遍存在；
  用户的过拟合担忧被证实。卡片 §4 已给出 v2 协议草案（add_turn + 分层钩子 +
  保留 prompt_messages 长板）。附带收获：MemoryData 已集成我们全部 10 个
  method，是 Track A 审计的第一参考；memorybench 是 Supermemory 官方评测框架。
- [x] 首轮协议重评估产出候选方案 A：[spec-protocol-v2.md](spec-protocol-v2.md)
  （2026-07-06 用户决定**缓行**，降级为候选；其中用户三决策与 R1-R3 行为规则
  继续有效，粒度选择推迟）。
- [ ] **全部 10 个** method 机制深读（Codex，plan 见
  [plan-track-a2-method-mechanism.md](plan-track-a2-method-mechanism.md)，
  2026-07-06 扩编）：4 个已接入 method 补机制卡片（含"现有 adapter 形变记录"
  第 7 节）+ 6 个新 method；统一格式统一深度。
- [ ] benchmark 调研卡片补全至 5/5（Codex，plan 见
  [plan-track-b0-benchmark-cards.md](plan-track-b0-benchmark-cards.md)）：
  LoCoMo、LongMemEval 新做卡片；HaluMem/BEAM/MemBench 增补"原生粒度 +
  成本画像"两节。背景：已接入的 2 benchmark 调研知识从未卡片化。
- [ ] 架构师产出**粒度需求双向矩阵**：5 benchmark 的数据自然粒度与喂入方式
  （从 7 张调研卡片萃取）× 10 method 的原生 ingest 形态（4 张 interface
  inventory + 6 张机制卡片）；矩阵完成后重开最终协议设计（候选：单粒度、
  add_session、多粒度并存 + 中间层聚合）。
- [ ] 最终协议 spec（含中间层设计、多模态与 agentic task family 扩展性论证），
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
