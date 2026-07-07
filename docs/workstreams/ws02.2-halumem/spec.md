---
id: ws02.2
parent: ws02
doc: spec（大型 benchmark，spec 与 plan 分离）
status: draft
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

官方对 `session.get("is_generated_qa_session")==True` 的 session 只 add
dialogue、**跳过** extraction 与 update eval，删除 `dialogue/memory_points`
输出键（eval_memzero.py:196-202）。adapter 必须保留该标志到私有 metadata，
runner 据此对这类 session 只跑 ingest（不发抽取报告断言、不发 update 探针），
QA 仍按需触发。

## S3 协议 v3 映射（零实体改动）

### S3.1 Extraction = `end_session` 报告

- method 声明 `session_memory_report=True` 时，`end_session(SessionRef)` 返回
  `SessionMemoryReport(memories=[本 session 新抽取记忆文本])`。runner 已有管线
  在 ingest 阶段捕获 SessionMemoryReport 并落 `session_memory_reports.jsonl`
  （prediction.py:1519-1523,1935-1943 等，M-A 已建）——operation-level runner
  复用该落盘，无需新 artifact schema。
- 官方 Mem0 从 `add` 返回值取 extracted memories；我们在 session 边界取，
  语义等价（HaluMem 一 session 一 add，session 边界 = 该 add 完成点）。

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

这是**按 task family 分派的 runner**（operation-level），对 HaluMem 下所有
method 共享，未来其他 operation-level benchmark 复用——**不是 method×benchmark
专用 runner**，不违反硬规则（AGENTS.md）。实现建议：新增
`run_operation_level_predictions()`，复用既有 primitives（隔离键派生、
artifact 原子写、SessionMemoryReport 捕获、efficiency 观测、resume 状态机），
只重写"驱动顺序"。

### S4.2 单 user 驱动序列（增量状态）

```text
for user in dataset:                       # isolation_key = run_id + uuid
    provider = build(user)                 # 每 user 独立命名空间（R5）
    for session in user.sessions (时序):
        for turn in session: provider.ingest(turn_event)     # 按声明粒度聚合
        report = provider.end_session(SessionRef)            # 抽取报告
        assert (session_memory_report 声明) == (report is not None)  # 契约校验
        if not session.is_generated_qa_session:
            for gold_mp in session 的 update memory points:  # 私有侧注入
                provider.retrieve(purpose="memory_update_probe", ...)
        for q in session.questions:
            r = provider.retrieve(purpose="qa", top_k=20)
            reader(PROMPT_MEMZERO, r.formatted_memory) → system_response
    provider.end_conversation(UnitRef); provider.cleanup()
```

### S4.3 私有 gold → update 探针的受控通道

update 探针的 query 来自私有 gold `memory_content`。这打破"gold 绝不达
method"的默认边界，是 HaluMem 设计本身要求的探针（官方 :210-222）。约束：
- 该通道**只在 operation-level runner 内、只对 `purpose="memory_update_probe"`
  开放**，由私有 `GoldAnswerInfo` 侧显式注入，不经公开 Conversation；
- query 文本进入 `RetrievalQuery.query_text`，不进入任何会流回 QA 的路径
  （QA 检索用 question 文本，互不污染）；
- 见决策点 **D1**：是否接受此受控例外（用户拍板）。

### S4.4 artifact 与 resume

- 新 artifact：`update_probe_results.jsonl`（每条：session_ref + gold memory
  index + memories_from_system + duration）；抽取复用
  `session_memory_reports.jsonl`；QA 复用 `method_predictions.jsonl`。
- resume 单元 = user（conversation 级），沿用既有 conversation checkpoint
  状态机；session 内的抽取/更新/QA 作为该 user 的子步骤整体重放（不做
  session 级断点，避免半 user 状态歧义）。

## S5 三个 Evaluator（全 LLM judge，requires_api=True）

均对齐官方 `eval/eval_tools.py` judge prompt 与聚合口径（调研卡 §4/§5.3）。
evaluator 模板：现有 `longmemeval_judge.py` / `locomo_judge.py`。

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

## S6 能力声明与占位

- 新增 `MethodCapability.SESSION_MEMORY_EXTRACTION`（映射
  `session_memory_report=True`）与 `TaskFamily.OPERATION_LEVEL_MEMORY`。
  HaluMem registration `required_capabilities` 含该能力；
  `validate_compatibility` 在运行时 fail-fast 不匹配的 method×benchmark。
- **能力门控**（调研卡 §7.3 先例：Zep 因缺 Get Dialogue Memory 无法准确评
  extraction）：method 声明 `session_memory_report=False` 时，其 HaluMem
  extraction 段记 **N/A 占位**（不硬造 0 分），update+QA 仍跑。哪些 method
  声明 True 由架构师按机制卡逐一裁定（见 D4）——**本 spec 不预设**，plan 里
  按 method 出接线子任务。

## S7 决策点（用户/架构师分界见 playbook §6）

- **D1（用户拍板）gold-as-query 隐私政策**：update 探针用 gold
  `memory_content` 作检索 query，method 会看到 gold 派生文本。这是 HaluMem
  设计要求的探针，非答案泄漏（QA 段独立，不受污染）。
  **架构师推荐：接受此受控例外**——理由：① 官方 wrapper 即如此
  （:210-222），不接受就无法做 update 段；② 通道受限于
  `purpose="memory_update_probe"`、由私有侧注入、可审计；③ 不影响 QA/extraction
  的公私边界。**风险**：若未来有 method 把 update 探针的 query 文本回填进
  自己的记忆，会造成 gold 污染——plan 需加一条"update 探针 retrieve 不得
  触发写入副作用"的契约校验。请用户确认是否接受。
- **D2（架构师定，标注）judge 模型**：官方论文用 gpt-4o；项目硬规则统一
  gpt-4o-mini。**裁定：用 gpt-4o-mini**，profile 明确标注"非论文严格复现"，
  与 LoCoMo/LongMemEval judge 一致口径。
- **D3（架构师定）smoke variant**：默认 `medium`（更小），`long` 作第二
  variant 备用。
- **D4（架构师定，plan 展开）extraction 能力门控**：逐 method 按机制卡裁定
  `session_memory_report`。初判（待 plan 核实机制卡）：Mem0 的 `add` 返回
  incremental memories → 可 True；SimpleMem finalize 后的
  lossless_restatement 是否 session-specific 需查；其余 method 谨慎默认
  False + N/A 占位，不硬塞。**不预设，plan 逐 method 出证据。**
- **D5（架构师定）persona_info**：不注入 method（官方仅用于抽 user name，
  而我们用 uuid 作 isolation_key，不需要 name）。persona_info 归私有。

## S8 非目标

- 不改协议 v3 实体（三段全部用现有 purpose/hook 表达）。
- 不做真实 API smoke（待用户预算/规模/run_id）。
- 不为 HaluMem 建 method×benchmark 专用逻辑（operation-level runner 是
  task-family 级共享）。
- 不追求论文数值严格复现（judge 模型差异，D2 已标注）。
- 本 spec 只定口径；task 拆分、逐 method 门控、runner 实现细节进 plan。

## S9 完成判据（plan 全部 task 通过后）

1. HaluMem adapter：user/session/turn 三层映射 + 四层隐私 +
   `is_generated_qa_session` 处理 + 时间转换器，focused 测试全绿。
2. `TaskFamily.OPERATION_LEVEL_MEMORY` + `MethodCapability.
   SESSION_MEMORY_EXTRACTION` + registration + 兼容门控 fail-fast 测试。
3. operation-level runner：单 user 增量驱动序列（S4.2）+ 三 artifact 流 +
   conversation 级 resume，registered fake 全链路 smoke 覆盖抽取/更新/QA 三段。
4. 三个 judge evaluator：离线 fake judge 测试（不调真实 API）验证聚合口径与
   category_breakdown；prompt 注官方行号。
5. 全量回归 ≥ 819 passed（当前基线）不跌破；compileall 通过。
6. 极小真实 smoke（1 user、少量 session）待用户确认预算后执行，验四段：
   跑通、manifest `protocol_version=v3`/`prompt_track=unified`、三 artifact
   非空、成本 observation 落盘。

## S10 版本留痕

- 2026-07-08 Opus 4.8 起草 draft。关键判断：协议 v3 零改动即可承载
  operation-level（推翻调研卡 2026-06-29"需扩协议"的旧判断，因该卡早于
  v3）。待用户批准 D1 后转 approved 并写 plan。
