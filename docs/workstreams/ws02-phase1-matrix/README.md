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

- 2026-07-06（最新）：**最终协议 spec v3 已产出，待用户批准**：
  [spec-protocol-v3.md](spec-protocol-v3.md)。整合了矩阵 §4 结论 + 用户全部
  定案（三层数据模型、声明消费粒度、三层钩子、并置隔离 R5、RetrievalQuery、
  检索输出三件套、双口径×双 profile、R1-R6、占位规范、M-A/B/C 迁移方案）。
  §7 留三个决策点（unified prompt 来源 / MemBench prompt 口径 / BEAM scorer
  口径）随批准一并裁定。**批准后：架构师写 M-A 实施 plan 交 Codex，
  Track B/C 解冻。**
- 2026-07-06（已完成）：接口能力双向矩阵完成（任务清单 Track 0 对应项），
  15 张卡片交叉复核同步完成（Codex A2/B0 交付质量高，无需返工）。
- 2026-07-05 23:35 CST（Codex）：Track B0 benchmark 调研卡片补全已完成并逐卡
  commit。新增 [LoCoMo.md](../../survey/benchmarks/LoCoMo.md)、
  [LongMemEval.md](../../survey/benchmarks/LongMemEval.md)；增补
  [HaluMem.md](../../survey/benchmarks/HaluMem.md)、
  [BEAM.md](../../survey/benchmarks/BEAM.md)、
  [MemBench.md](../../survey/benchmarks/MemBench.md) 的"原生粒度与喂入方式"
  与"成本画像"。未调用真实 LLM/embedding API；隔离数据统计使用 `uv run`；
  主环境依赖文件无修改。下一步交回架构师产出粒度需求双向矩阵。
- 2026-07-05 21:55 CST（Codex）：Track A2 全部 10 method 机制卡已完成并逐卡
  commit；`audits/summary.md` 已追加"原生粒度一览"覆盖 10/10 method。
  未调用真实 LLM/embedding API，隔离试装均使用 `uv`，未修改主环境依赖文件。
  下一步按用户指令继续执行 Track B0：
  [plan-track-b0-benchmark-cards.md](plan-track-b0-benchmark-cards.md)。
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
- [x] **全部 10 个** method 机制深读（Codex，plan 见
  [plan-track-a2-method-mechanism.md](plan-track-a2-method-mechanism.md)，
  2026-07-06 扩编）：4 个已接入 method 补机制卡片（含"现有 adapter 形变记录"
  第 7 节）+ 6 个新 method；统一格式统一深度。
- [x] benchmark 调研卡片补全至 5/5（Codex，plan 见
  [plan-track-b0-benchmark-cards.md](plan-track-b0-benchmark-cards.md)）：
  LoCoMo、LongMemEval 新做卡片；HaluMem/BEAM/MemBench 增补"原生粒度 +
  成本画像"两节。背景：已接入的 2 benchmark 调研知识从未卡片化。
- [x] 架构师产出**接口能力双向矩阵**（2026-07-06）：
  [track0-interface-capability-matrix.md](track0-interface-capability-matrix.md)。
  六个决定性发现：细粒度事件流为 canonical（方向确认）；多粒度并存 = method
  声明消费粒度 + 框架聚合（用户猜想被证实）；end_session 必须能交回新增记忆
  （HaluMem 要求）；隔离单位有三种、不能硬编码 conversation；retrieve 输入
  泛化为 RetrievalQuery、输出三件套（formatted_memory/prompt_messages/items）；
  检索非只读（MemoryOS heat）。§4 是最终协议 spec 的结论清单。
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

- 2026-07-06 用户（定案轮）：
  (a) **official profile 定义修正**：official 锚定 **method 论文**的超参数与
  基座模型配置（非 benchmark 论文的 eval 配置）；method 论文自身跑了多组配置的
  （如 LightMem），允许多个 official 变体（official-<variant> 命名）。
  (b) **LoCoMo category 5（Adversarial）定案：不跑**——该类别 dataset 本身
  疑似有问题；结果表按占位口径处理并脚注。
  (c) **LoCoMo 图片口径定案**：不下载图片、不调视觉模型，`blip_caption`
  直接拼进文本（`原文 (image description: ...)`），与 MemoryOS/A-Mem/LightMem
  官方处理一致——作为 TurnEvent content 的标准构造规则。
  (d) **HaluMem persona_info 定案：不给 method**。
  (e) 检索副作用口径获用户认同（接受为官方行为 + 文档注明 + resume 不重检
  已答问题）；服务型 method 并置规模压力留待 Track C 实测。
- 2026-07-06 用户（矩阵讨论轮）：
  (a) **数据结构统一观**：五 benchmark 本质同构——隔离空间（conversation/
  sample/uuid）→ 多个带 time 的 session → 多个 turn；MemBench 第三人称只是
  单角色消息流的退化形态，不破坏该模型。
  (b) **evidence recall（recall@k 类）不强求**：method 能返回 dataset 标记就实现，
  不能就在结果表用占位符（N/A）标注，不硬造。
  (c) **隔离采用"并置持久化"模型，不做逐边界 reset**：每个隔离空间的记忆状态
  必须留存（如 LongMemEval 500 instance 各自保留），reset 仅用于失败 unit 的
  clean retry。架构师细化分工：框架负责隔离政策（显式 isolation_key + 状态根），
  method adapter 负责把键映射到原生隔离机制（namespace/containerTag/collection/
  agent_id）。
  (d) **session 为一等写入边界**；HaluMem 的 session 级新增记忆通过
  add_session/end_session 返回值获取（**特定 session 的新增记忆**，非全局），
  该能力为可选声明，method 不支持则 extraction 指标占位。
  (e) **工程优化专项延后**：并行并发、resume 机制、异常兜底、日志、终端进度等
  由未来独立 workstream 统一优化（架构师写文档、Codex 实现）；当前 conversation
  级 resume 维持现状，本轮协议 spec 不动 resume 设计。
  (f) 背景补记：A-Mem 官方仓库无持久化，现有 conversation 级持久化是 Codex
  补写的 wrapper 层能力（属合理形变，保留）。
- 2026-07-06 用户：answer 侧确立**双 prompt 口径**，是协议设计的核心输入：
  (a) **method-native 口径**：保留各 method 论文原生 answer prompt（即当前
  `prompt_messages` 路径）。用途 = 复现论文结果、论证框架正确性、官方对标。
  (b) **unified 口径**：框架按 benchmark 设计统一 answer prompt（跨 method
  统一、跨 benchmark 不必统一），method 只返回"有助于回答当前 query 的规范化
  记忆"（formatted_memory，如 `<memory>...</memory>` 包裹）。用途 = 公平横向
  比较——memory module 的本职是检索记忆，prompt 工程不应成为比较混杂变量。
  最终实验报告**两种口径都展示**。协议含义：`retrieve()` 返回需同时承载
  `formatted_memory`（必需）与 `prompt_messages`（native 口径需要时提供）；
  现有 `metadata["answer_context"]` 是 formatted_memory 的雏形。
- 2026-07-06 用户确认：框架必须支持自由调整已集成 method 的超参数与基座
  LLM → **official / custom 双 profile**：official 锁死论文口径用于对标引用，
  custom 用于受控探索；manifest 强制标注，artifact 永不混淆。
- 2026-07-06 架构师评估"可复现工程是否过重"（用户提问）：核心机制保留——
  公私数据边界、conversation 级 resume、failed 隔离、连续失败熔断、manifest
  兼容校验，均有真实事故救场记录（Mem0 full-v2/v3 SSL 断连烧钱事故等）；
  迁移期赘肉承认存在——turn-level resume 状态机（从未实际使用）、过重
  capability 推理、部分 fingerprint 粒度，已在 ws03 记账清理。评判标准：
  **机制没救过场且无前瞻用途即砍**。
- 2026-07-05 用户：Phase 1 完成判据 = smoke 矩阵而非全量实验；全量需先
  拿成本表向导师申请预算；LongMemEval 全量 4 method 约 $500，超出当前预算。
- 2026-07-05 用户：已有 LoCoMo full 结果在 5×10 架构完成后需用新 run_id 重跑。
- 2026-07-04 用户：5×10 范围锁定；Supermemory 仅 self-host/local OSS；
  Zep/Graphiti 排除。
- 调研判断标准：先回答"该 benchmark 需要 method 提供什么能力"再动代码。
