---
id: ws02.2
parent: ws02
doc: spec（大型 benchmark，spec 与 plan 分离）
status: approved (2026-07-08 用户批准；D1 接受官方做法；S6 改接口即契约)
created: 2026-07-08
author: Claude Opus 4.8（第二任架构师）
---
# ws02.2 HaluMem Adapter 设计（Full Operation-level）

依据（每条设计可回溯）：
[HaluMem 调研卡](../../survey/benchmarks/HaluMem.md)、
协议 v3（`spec-protocol-v3.md`）、官方 eval wrapper
`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py`、官方 prompt
`third_party/benchmarks/HaluMem-main/eval/prompts.py` 与
`eval/eval_tools.py`、本地数据 `data/halumem/HaluMem-Medium.jsonl`。

用户 2026-07-08 定范围：**Full operation-level**（抽取 + 更新 + QA 三段全做）。

## S0 一句话与关键发现

HaluMem 是三个新 benchmark 里唯一的 **operation-level 记忆幻觉诊断**基准：不
只看最终 QA，而是把记忆系统拆成 **Memory Extraction / Memory Updating /
Memory QA** 三段分别打分，用来定位幻觉来自抽取、更新、检索还是生成。它是本
项目北极星"**能力维度**轴"分辨率最高的基准。

**关键发现（决定工作量）**：协议 v3 **无需改动**即可表达 HaluMem 三段——首任
架构师设计 v3 时已埋好扩展位（`core/provider_protocol.py`）：
- `RetrievalPurpose` 已含 `"extraction_probe"`、`"memory_update_probe"`
  （protocol.py:18,230）；
- `SessionMemoryReport` + `end_session() -> SessionMemoryReport | None`
  （protocol.py:199-204,289）= 调研卡所说的 "Get Dialogue Memory API"；
- `session_memory_report: bool` 能力标志（protocol.py:275）供 method 声明
  是否支持 session 级抽取导出。

因此本 workstream 的真实工作量 = **HaluMem adapter + operation-level runner +
3 个 judge evaluator + 能力门控接线**，协议实体零改动。

## S1 范围与形态

### S1.1 三段任务（全做）

| 阶段 | 官方契约（eval_memzero.py） | 协议 v3 映射 |
| --- | --- | --- |
| Memory Extraction | 每 session `add` 后取 `result["results"]` 的 memory 文本（:189-207） | `end_session(ref) -> SessionMemoryReport.memories` |
| Memory Updating | 对 `is_update!="False" 且 original_memories` 的 gold memory，用其 `memory_content` 作 query，`search top_k=10`（:210-222） | `retrieve(purpose="memory_update_probe", query_text=gold_memory_content, top_k=10)` |
| Memory QA | 每 question `search top_k=20` → `PROMPT_MEMZERO(context, question)` → answer LLM（:224-253） | `retrieve(purpose="qa", top_k=20)` + framework unified reader |

### S1.2 目标格子与 variant

- 目标格子（本 workstream 点亮范围）：HaluMem × 已接入的 5 个 method
  （Mem0/MemoryOS/A-Mem/LightMem/SimpleMem）。其余 5 个未接入 method 的
  HaluMem 格子随各自 method 接入时点亮，不在本 workstream。
- variant：`medium`（`data/halumem/HaluMem-Medium.jsonl`，20 users）+
  `long`（`HaluMem-Long.jsonl`，同 QA/memory-point 数但 session 更多更长）。
  两者共享 adapter，仅源文件不同（对齐 MemBench 双 variant 先例）。

### S1.3 prompt 口径

HaluMem 官方提供 QA prompt（`PROMPT_MEMZERO`，prompts.py:1-40），属 prompt
三级来源第 1 级（benchmark 官方）。因此 QA 段是 **unified 口径**
（`prompt_track="unified"`，与 MemBench 一致）：framework reader 用
PROMPT_MEMZERO 模板，输入各 method 的 `formatted_memory`。抽取/更新段不产生
answer LLM 调用（是检索探针 + judge），无 prompt 口径问题。

## S2 数据模型映射

### S2.1 层级映射

```text
HaluMem user (uuid)      → 一个 Conversation（隔离单元；isolation_key 按 uuid）
  session                → 一个 Session（time = start_time/end_time）
    dialogue turn        → 一个 TurnEvent（role/content/timestamp）
    memory_points        → 私有 gold（不进 method 公开输入）
    questions            → question 公开 / answer,evidence,difficulty,type 私有
```

- 官方按 user 做 `delete_all(user_id)` 重置命名空间（eval_memzero.py:158），
  对齐协议 R5：一 uuid 一 isolation_key，同 uuid 下 sessions 连续累积。
- session `start_time` 为写入时间锚点（官方 :185-194 用 session start_time，
  不用 turn 级 timestamp）；时间格式 `%b %d, %Y, %H:%M:%S`（如
  `Sep 04, 2025, 21:12:18`）→ ISO 转换器 + 单测（对齐 LoCoMo 时间转换先例）。

### S2.2 隐私边界（四层保护严格执行）

进入 method 公开输入的**仅**：`uuid`、session `start_time/end_time`、dialogue
`role/content/timestamp`、`questions[].question`。

严格隔离到 `GoldAnswerInfo`（evaluator-only）：`memory_points`（全部字段）、
`questions[].answer/evidence/difficulty/question_type`、`persona_info`。校验：
`to_public_dict()` 排除 gold + `validate_no_private_keys()` 递归扫描
（沿用既有四层机制）。

### S2.3 特殊 session：`is_generated_qa_session`

官方对 `session.get("is_generated_qa_session")==True` 的 session **只 add
dialogue，跳过全部三段**（extraction + update + QA）——代码在该分支直接
`continue`，越过 extraction、update 探针和 questions 循环，且删除
`dialogue/memory_points` 输出键（eval_memzero.py:196-202）。adapter 必须保留
该标志到私有 metadata，runner 据此对这类 session **只跑 ingest**，不发抽取
报告断言、不发 update 探针、不跑 QA（名字有误导性：它不是"QA session"，是
只提供上下文的合成 session）。

> 勘误（2026-07-08，用户"注意三种触发时机"点出）：本节初稿曾写"QA 仍按需
> 触发"，与官方 `continue` 语义不符——官方跳过全部三段。已修正。

## S3 协议 v3 映射（零实体改动）

### S3.1 Extraction = `end_session` 报告（session-**增量**）

- method 覆写 `end_session(SessionRef)` 返回
  `SessionMemoryReport(memories=[本 session **新抽取**记忆文本])` 时，runner 收
  报告并落 `session_memory_reports.jsonl`（已有管线 prediction.py:1519-1523,
  1935-1943，M-A 建）——无需新 artifact schema。未覆写/返回 None → N/A（S6）。
- **关键：抽取报告是 session-增量，不是全局 dump**（调研卡 §6.2：must be
  session-specific）。官方从**本 session 的 `add` 返回值**取 extracted
  memories（eval_memzero.py:204-207），即这一 session 新产生的记忆，不含历史。
  能提供增量返回的 method（Mem0 `add().results`）可给报告；只能 dump 全局
  state 的 method → 无法准确评 extraction → N/A。
- **触发时机**：extraction 在本 session ingest 完成的**那一刻**取（session
  边界 = 该 session 单次 add 完成点），与下面 update/QA 的"累积状态检索"是
  两种不同语义（见 S4.2 增量 vs 累积）。

### S3.2 Updating = `memory_update_probe` 检索

- runner 对每个符合条件的 gold memory point，发
  `RetrievalQuery(query_text=gold.memory_content, purpose="memory_update_probe",
  top_k=10)`，把 `RetrievalResult`（formatted_memory / items）作为
  `memories_from_system` 落 `update_probe_results.jsonl`（新 artifact）。
- **注意**：query_text 是 gold 派生文本 → 见决策点 **D1**（隐私政策）。

### S3.3 QA = `qa` 检索 + unified reader

- runner 对每个 question 发 `RetrievalQuery(purpose="qa", top_k=20)`，取
  `formatted_memory` 喂 framework reader 的 PROMPT_MEMZERO 模板，产
  `system_response` 落既有 `method_predictions.jsonl`。

## S4 Operation-level Runner 契约（唯一新 runner 能力）

### S4.1 为什么必须新增（不是"专用 runner"）

现有 `run_predictions` 是"**全 ingest → 全 retrieve**"：所有 conversation 先
写完，再统一回答所有 question。HaluMem 的 QA/更新探针必须在**每个 session
边界、针对增量记忆状态**触发（调研卡 §3.1：问题挂在哪个 session 就在该 session
写入后触发）——因为后续 session 可能更新/覆盖记忆，"最终状态"与"session N 时
状态"对被更新的记忆答案不同。用现 runner 会把每题都对**最终状态**作答，语义
错误。

这是**按 benchmark 分派的 runner**（operation-level），对 HaluMem 下所有 method
共享，未来其他 operation-level benchmark 复用——**不是 method×benchmark 专用
runner**，不违反硬规则（AGENTS.md）。分派键 = benchmark registration 上的一个
runner 声明字段（benchmark 自报用哪个 runner），**不是**旧的
`MethodCapability`/`validate_compatibility` 方法侧兼容矩阵（见 S6）。实现建议：
新增 `run_operation_level_predictions()`，复用既有 primitives（隔离键派生、
artifact 原子写、SessionMemoryReport 捕获、efficiency 观测、resume 状态机），
只重写"驱动顺序"。

### S4.2 单 user 驱动序列 —— 三段触发时机与"增量 vs 累积"

**三段全部在同一 session 边界触发**（本 session ingest 完成后、进入下一 session
前），顺序 = extraction → update → QA，但检索的记忆状态语义不同：

- **extraction**：session-**增量**（本 session 新抽取的记忆，S3.1）。
- **update 探针 / QA**：**累积**状态（截至含本 session 的全局记忆）——因为官方
  在每个 session 后就地检索当前全局 state（eval_memzero.py:210-253），后续
  session 的更新会改变早先问题的答案，这正是 operation-level 必须逐 session
  就地跑、不能"全 ingest 再全 retrieve"的原因。

```text
for user in dataset:                       # isolation_key = run_id + uuid
    provider = build(user)                 # 每 user 独立命名空间（R5）
    for session in user.sessions (时序):
        for turn in session: provider.ingest(turn_event)     # 按声明粒度聚合
        report = provider.end_session(SessionRef)            # ① extraction（增量）
        if session.is_generated_qa_session:                  # 只提供上下文
            continue                                         # 跳过 ②③（S2.3）
        for gold_mp in 本 session 的 update memory points:    # ② update（累积）
            provider.retrieve(purpose="memory_update_probe", query=gold_mp.content, top_k=10)
        for q in session.questions:                          # ③ QA（累积）
            r = provider.retrieve(purpose="qa", top_k=20)
            reader(PROMPT_MEMZERO, r.formatted_memory) → system_response
    provider.end_conversation(UnitRef); provider.cleanup()
```

- extraction 契约由接口决定（S6）：provider 未提供报告 → 该段 N/A，不 assert
  失败；提供了 → 落盘评分。
- `is_generated_qa_session` 在 extraction 之后、update 之前 `continue`——严格
  对齐官方（这类 session 连 extraction 报告也不进 scorer，只 ingest 建上下文）。
  实现上：这类 session 仍 ingest + end_session 让 provider 内部状态推进，但其
  抽取报告/更新/QA **不落 eval artifact**。

### S4.3 私有 gold → update 探针的受控通道

update 探针的 query 来自私有 gold `memory_content`。这打破"gold 绝不达
method"的默认边界，是 HaluMem 设计本身要求的探针（官方 :210-222）。**D1 已由
用户 2026-07-08 批准：遵循 HaluMem 官方做法，接受此受控例外**。约束：
- 该通道**只在 operation-level runner 内、只对 `purpose="memory_update_probe"`
  开放**，由私有 `GoldAnswerInfo` 侧显式注入，不经公开 Conversation；
- query 文本进入 `RetrievalQuery.query_text`，不进入任何会流回 QA 的路径
  （QA 检索用 question 文本，互不污染）；
- **无写副作用契约（D1 风险兜底）**：update 探针的 `retrieve` 不得触发 method
  的记忆写入——否则 gold 文本会污染后续 QA 的记忆状态。plan 需加契约测试：
  update 探针前后 provider 的记忆条数/状态不变（对 fake provider 断言）。

### S4.4 artifact 与 resume

- 新 artifact：`update_probe_results.jsonl`（每条：session_ref + gold memory
  index + memories_from_system + duration）；抽取复用
  `session_memory_reports.jsonl`；QA 复用 `method_predictions.jsonl`。
- resume 单元 = user（conversation 级），沿用既有 conversation checkpoint
  状态机；session 内的抽取/更新/QA 作为该 user 的子步骤整体重放（不做
  session 级断点，避免半 user 状态歧义）。

## S5 三个 Evaluator（全 LLM judge，requires_api=True）

均对齐官方 `eval/eval_tools.py` + `eval/evaluation.py` 的 judge prompt 与聚合
口径（**第一手源码为准，逐行口径见 plan T4 补充块**）。evaluator 模板：现有
`longmemeval_judge.py` / `locomo_judge.py`。

> 更正（2026-07-08，架构师读 `evaluation.py` 第一手）：下表把三段列为并列，
> 易误读为"独立评分"。实际 **integrity 与 update 对 gold memory point 是互斥
> 路由**（`evaluation.py:58-70`）——`is_update=="True" 且检索非空`的点进 update、
> **从 recall 分母剔除**，其余进 integrity。T4 以 plan 补充块的逐行口径为准。

| metric_name | 官方 prompt | judge 输出 | 主聚合指标 |
| --- | --- | --- | --- |
| `halumem_extraction` | `EVALUATION_PROMPT_FOR_MEMORY_INTEGRITY` + `..._ACCURACY` | integrity∈{2,1,0}；accuracy∈{2,1,0}+included | recall/weighted_recall/target_accuracy/FMR/**F1** |
| `halumem_update` | `EVALUATION_PROMPT_FOR_UPDATE_MEMORY` | Correct/Hallucination/Omission/Other | correct_update_ratio（+ 三项错误率） |
| `halumem_qa` | `EVALUATION_PROMPT_FOR_QUESTION` | Correct/Hallucination/Omission | correct_qa_ratio（+ hallucination/omission 率） |

- 三个 evaluator 各自 `supported_benchmarks={"halumem"}`、`requires_api=True`、
  gpt-4o-mini judge（见 D2）；prompt 从官方源码摘录并注行号，冻结进 profile。
- extraction judge 需 gold `memory_points` + method `extracted_memories`；
  update judge 需 gold + `memories_from_system`；QA judge 需
  question/answer/evidence + `system_response`——全部只在 evaluator 私有侧。
- category_breakdown：extraction 按 `memory_type`、QA 按 `question_type`
  分组（对齐 MemBench category_breakdown 先例）。

## S6 能力契约：接口即契约（弃用 enum 门控）

用户 2026-07-08 定调："接口本身就是契约。一个 method 没 override `end_session()`
→ benchmark 要它的 session memory report → runner 自然拿不到，要么占位要么
报错。" 架构师采纳，理由链：协议 v3 下每个 method 都实现 `ingest+retrieve`，
抽取只是**可选能力**，缺失时优雅降级（N/A），不存在旧那种硬"不兼容"——
`TaskFamily + MethodCapability + validate_compatibility` 这套方法侧兼容矩阵
早于 v3、在 v3 下已冗余。

- **不新增** `MethodCapability.SESSION_MEMORY_EXTRACTION` /
  `TaskFamily.OPERATION_LEVEL_MEMORY`，**不用** `validate_compatibility()` 做
  method×benchmark 门控。
- **契约检测 = 接口本身**：runner 判断 provider 是否覆写 `end_session` 并返回
  非 None `SessionMemoryReport`：
  - 提供报告 → extraction 正常评分；
  - 未提供（`end_session` 未覆写 / 返回 None）→ 该 method 的 extraction 段记
    **N/A 占位**（不硬造 0 分，占位规范），update + QA 照常。
- **预算安全的 preflight（架构师加的一条工程约束，检测时机）**：run 启动前用
  introspection 检查 `type(provider).end_session is not MemoryProvider.end_session`
  决定 extraction 段 N/A-or-run，**不必先花 API 钱 ingest 才发现全 N/A**。这是
  对用户"要么占位要么报错"的时机细化——把决定提前到花钱之前，匹配预算强约束；
  纯运行时检测（跑完才知道）在有真实 API 成本时不可取。preflight 从 method
  factory 得到真实 provider 类做内省（与 protocol_version 声明同一路径），
  **不依赖 `_UnusedRootSystem` 占位**（workers>1 时根实例是占位）。
- **分派机制**：operation-level runner 由 **benchmark registration 的 runner
  声明字段**触发（benchmark 自报用哪个 runner），这是 benchmark 侧的自我声明，
  不是被弃用的方法侧兼容矩阵。plan 定字段名。
- **软契约方向已是 v3 现状**（印证用户判断）：v3 ABC 只强制 `ingest+retrieve`
  两个抽象方法，其余钩子全 no-op 默认——用户只跑某 benchmark 时本就无需实现
  用不到的钩子；"假装实现又跑了真需要它的 benchmark → 后果自负" 在 v3 下自然
  成立（runner N/A 或 preflight 报错），无需额外造软契约机制。
- **遗留清理（不在本 workstream，标 ws03）**：旧 `capabilities.py`（TaskFamily/
  MethodCapability/validate_compatibility）+ 现协议冗余的
  `session_memory_report: bool` 属性 → ws03 架构减重候选。本 workstream 不动它
  们（scope 纪律），HaluMem 直接走接口内省，不新增也不依赖 enum。

## S7 决策点（用户/架构师分界见 playbook §6）

- **D1（用户 2026-07-08 已批准）gold-as-query 隐私政策**：update 探针用 gold
  `memory_content` 作检索 query。**裁定：接受此受控例外，遵循 HaluMem 官方
  做法。** 兜底：plan 加"update 探针 retrieve 无写副作用"契约测试（S4.3）。
- **D2（架构师定，标注）judge 模型**：官方论文用 gpt-4o；项目硬规则统一
  gpt-4o-mini。**裁定：用 gpt-4o-mini**，profile 明确标注"非论文严格复现"，
  与 LoCoMo/LongMemEval judge 一致口径。
- **D3（架构师定）smoke variant**：默认 `medium`（更小），`long` 作第二
  variant 备用。
- **D4（架构师定，plan 展开）extraction 能力 = 是否覆写 `end_session` 返回
  增量报告**（接口即契约，S6，不再是 enum 声明）。逐 method 按机制卡裁定是否
  实现该覆写。初判（待 plan 核实机制卡）：Mem0 `add` 返回 incremental memories
  → 可实现；SimpleMem finalize 后 lossless_restatement 是否 session-specific
  需查；其余 method 谨慎默认不实现 → N/A 占位，不硬塞。**不预设，plan 逐
  method 出证据。**
- **D5（架构师定）persona_info**：不注入 method（官方仅用于抽 user name，
  而我们用 uuid 作 isolation_key，不需要 name）。persona_info 归私有。

## S8 非目标

- 不改协议 v3 实体（三段全部用现有 purpose/hook 表达）。
- 不做真实 API smoke（待用户预算/规模/run_id）。
- 不为 HaluMem 建 method×benchmark 专用逻辑（operation-level runner 是
  benchmark 级共享）。
- **不新增 MethodCapability/TaskFamily enum，不用 validate_compatibility**
  （S6：接口即契约）；也不在本 workstream 删除旧 enum（留 ws03）。
- 不追求论文数值严格复现（judge 模型差异，D2 已标注）。
- 本 spec 只定口径；task 拆分、逐 method 能力核实、runner 实现细节进 plan。

## S9 完成判据（plan 全部 task 通过后）

1. HaluMem adapter：user/session/turn 三层映射 + 四层隐私 +
   `is_generated_qa_session` 处理 + 时间转换器，focused 测试全绿。
2. HaluMem registration（benchmark 侧 runner 声明字段分派 operation-level）+
   接口内省 preflight（`end_session` 覆写 → extraction run-or-N/A）测试；
   **不新增 enum、不用 validate_compatibility**（S6）。
3. operation-level runner：单 user 三段驱动序列（S4.2，extraction 增量 /
   update+QA 累积，`is_generated_qa_session` 跳过三段）+ 三 artifact 流 +
   "update 探针无写副作用"契约测试 + conversation 级 resume，registered fake
   全链路 smoke 覆盖抽取/更新/QA 三段。
4. 三个 judge evaluator：离线 fake judge 测试（不调真实 API）验证聚合口径与
   category_breakdown；prompt 注官方行号。
5. 全量回归 ≥ 819 passed（当前基线）不跌破；compileall 通过。
6. 极小真实 smoke（1 user、少量 session）待用户确认预算后执行，验四段：
   跑通、manifest `protocol_version=v3`/`prompt_track=unified`、三 artifact
   非空、成本 observation 落盘。

## S10 版本留痕

- 2026-07-08 Opus 4.8 起草 draft。关键判断：协议 v3 零改动即可承载
  operation-level（推翻调研卡 2026-06-29"需扩协议"的旧判断，因该卡早于 v3）。
- 2026-07-08 用户评审 → **approved**：① D1 批准（遵循 HaluMem 官方 gold-as-query）；
  ② 定调弃用 `TaskFamily/MethodCapability/validate_compatibility` enum 门控，
  改"接口即契约"（S6 重写；架构师加 preflight 内省一条工程约束以保预算安全）；
  ③ 用户"注意三种触发时机"点出 spec 两处错误，已修：S2.3
  `is_generated_qa_session` 跳过**全部三段**（初稿误写"QA 仍触发"）、S4.2
  明确 extraction 增量 vs update/QA 累积。旧 enum 系统 + 冗余 bool 属性标为
  ws03 减重候选。下一步：架构师写 plan。
