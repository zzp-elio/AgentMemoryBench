---
id: ws02.3
parent: ws02
doc: spec（大型 benchmark，spec 与 plan 分离）
status: draft
created: 2026-07-08
author: Claude Opus 4.8（架构师）
---
# ws02.3 BEAM Adapter 设计（conversation-QA + rubric judge）

依据（**第一手为准，本 spec 每条结论都已回官方仓库/真实数据核对**）：
官方仓库 `third_party/benchmarks/BEAM/`（`src/evaluation/compute_metrics.py`、
`src/prompts.py`、`src/answer_probing_questions/`）、真实数据
`data/BEAM/beam_dataset/{100K,500K,1M}` + `data/BEAM/beam_10M_dataset/10M`
（HuggingFace arrow）、三份 survey 卡（`benchmarks/`+`datasets/`+`workflows/BEAM.md`）。

## S0 一句话与家族定位

BEAM = **超长 conversation + 10 类记忆能力 probing questions**。评测单位 = 一个
完整 conversation；每 conversation 有 10 类能力 × 2 题 = **20 个 probing
question**（真实数据实测每类恰 2 题）。method 基于 conversation 历史回答每题，
scorer 用私有 **rubric**（打分细则清单）+ LLM judge 评回答质量。

**家族 = conversation-QA**（关键，决定工作量）：method 侧维持
`ingest(conversation) + retrieve(question, purpose="qa")` + framework reader，
**复用现有 `run_predictions` runner，不需要 operation-level runner**（与 HaluMem
相反）。真实工作量集中在：① BEAM adapter（HF arrow + 10 能力解析 + 隐私）；
② 一个 rubric-nugget LLM judge evaluator（含 ability 级聚合 + event_ordering
特殊指标 + **修官方 int 截断 bug**）；③ unified answer prompt 接线。

## S1 范围与形态

- 目标格子：BEAM × 已接入 5 method（Mem0/MemoryOS/A-Mem/LightMem/SimpleMem）。
- variant：`100k`(20 样本)/`500k`(35)/`1m`(35)（`beam_dataset`）+ `10m`(10)
  （`beam_10m_dataset`）。**保留本地 split 名 `100K` 不改成论文的 `128K`**
  （调研卡明确，已第一手确认 HF split 名为 `100K`）。
- prompt 口径：**unified**（`prompt_track="unified"`）——method 只检索返回
  `formatted_memory`，framework reader 用 BEAM answer prompt 生成 response。

## S2 数据模型映射

### S2.1 层级（第一手实测）

`data/BEAM/beam_dataset/100K` 列：`conversation_id, conversation_seed,
narratives, user_profile, conversation_plan, user_questions, chat,
probing_questions`。

```text
一个 sample (row)            → 一个 Conversation（conversation_id 隔离）
  chat: list[session]        → 每个内层 list → 一个 Session
    turn: dict               → 一个 Turn
      {content, id, index, question_type, role, time_anchor}
  probing_questions          → 20 个 Question（10 能力 × 2）
```

- `chat` 实测是 **list of list**（外层 = session 列表，内层 = turn 列表），
  turn 字段 `role/content/id/index/question_type/time_anchor`。`time_anchor`
  是日期（如 `March 15, 2024`）→ `Turn.turn_time`。**`content` 末尾带
  `->-> 1,1` 之类 index 标记**（第一手实测），adapter 需裁掉该尾标记只留
  真实文本（plan T1 核对 `->->` 分隔规则）。
- **`probing_questions` 是 Python-repr 字符串**（单引号，非 JSON），必须
  `ast.literal_eval` 解析，**不是** `json.loads`（第一手实测，调研卡未标此坑）。
  解析后是 `{ability: [question_obj, ...]}` dict，10 个 ability key，每 key 2 题。

### S2.2 10 类记忆能力（第一手，evaluator category）

`abstention, contradiction_resolution, event_ordering, information_extraction,
instruction_following, knowledge_update, multi_session_reasoning,
preference_following, summarization, temporal_reasoning`（compute_metrics.py
的 10 个 `evaluate_*` 函数 = 真实数据 probing_questions 的 10 个 key，一致）。

### S2.3 隐私边界（四层保护）

- **公开**（进 method）：`conversation_id`、`chat` 的 turn `role/content(裁尾)/
  id/index/time_anchor`、probing `question` 文本。
- **私有**（`GoldAnswerInfo`，evaluator-only）：question_obj 的 `rubric`（judge
  核心）、`ideal_response`、`difficulty`、`abstention_type`、`why_unanswerable`、
  `plan_reference`（第一手 question_obj keys 实测）；row 级
  `conversation_seed`、`user_profile`、`conversation_plan`、`user_questions`、
  `narratives`（数据生成元信息，D4 不注入）。
- 校验：公开 Conversation 过 `validate_no_private_keys` 全绿。

## S3 协议 v3 映射（conversation-QA，复用现有 runner）

- `ingest`：chat → TurnEvents，method 按各自声明粒度消费（复用既有
  `build_turn_events` + `GranularityAggregator`，与 LoCoMo 同路径）。
- `retrieve(RetrievalQuery(purpose="qa", top_k=<profile>))`：每个 probing
  question 一次检索，`formatted_memory` 喂 framework reader。
- framework reader 用 **BEAM unified answer prompt** 生成 response（prompt 源
  见 D1-note：BEAM 官方每 method 自答，无单一 answer prompt → 属 prompt 三级
  来源第 2/3 级，plan 第一手确定：从 `long_term_memory_methods.py` /
  `prompts.py` 摘录官方 QA-over-context 模板，或架构师综合冻结）。
- **无新 runner / 无协议改动 / 无 operation-level**。1M/10M 一次性 ingest 的
  工程压力见 S7（v1 smoke 用 100k + 截断规避）。

## S4 Evaluator：rubric-nugget LLM judge（第一手 compute_metrics.py）

### S4.1 核心打分（9 类通用 + event_ordering 特殊）

对每个 probing question：judge 逐条 `rubric` item 打分，用
`unified_llm_judge_base_prompt`（`prompts.py:11547-11591`，**SCORING SCALE 明写
1.0 / 0.5 / 0.0**），per-question `llm_judge_score = Σ(item score)/len(rubric)`
（compute_metrics.py:346-360）。9 类能力此逻辑相同；**event_ordering 额外**算
排序分：`event_ordering_score`（compute_metrics.py:270-308，语义对齐 →
kendall-tau_b 归一 × set-f1 → `final_score = tau_norm * f1`）+ 同样的
llm_judge_score（:396-433）。

### S4.2 **必修官方 bug：int 截断 0.5（第一手确认，你我共识）**

- **Bug**：9 个 `evaluate_*` 用 `score += int(response['score'])`
  （compute_metrics.py:357,385,454,483,512,541,570,599,628），把 judge 返回的
  **0.5 截断成 0**，丢失全部"部分合规"分；**唯独 event_ordering 用
  `float()`（:425）**。judge prompt 本身定义 0.5 为合法分（:11584），所以
  int() 与 prompt 语义自相矛盾 = bug。
- **裁定（架构师，沿用 Fable 5 记录 + mem0 memory-benchmarks 先例）**：本框架
  evaluator **统一用 float（0.0/0.5/1.0）**，profile 标注"修正官方 int 截断、
  采论文/prompt 语义，与官方数值有差异"。这是 benchmark 官方 scorer 的
  code-vs-doc 不一致（prompt 说 0.5、聚合 int 掉），属可一眼看出的实现 bug
  （用户 2026-07-08 亦以此为"一手资料也可能有易见错误"的例子）。

### S4.3 聚合与 breakdown

- per-question score → per-ability（每能力 2 题取均）→ overall（10 能力）。
  category_breakdown 按 ability（10 类，对齐 MemBench/HaluMem 先例）。
- evaluator 元信息：`metric_name="beam_rubric_judge"`、`requires_api=True`、
  `supported_benchmarks={"beam"}`、gpt-4o-mini judge（D5）；judge prompt +
  event_ordering 逻辑从 compute_metrics.py 摘录注行号。

## S5 决策点（用户/架构师分界见 playbook §6）

- **D1（架构师定，已precedent）int→float 修正**：统一 float，标注差异（S4.2）。
  **附 answer-prompt 来源**：BEAM 无单一官方 answer prompt（每 method 自答），
  plan 需第一手从 `long_term_memory_methods.py`/`prompts.py` 摘录 QA-over-context
  模板并冻结 profile；拿不准则架构师综合设计（三级来源第 3 级），留痕。
- **D2（架构师定）smoke split + 截断**：默认 `100k`（最小，20 样本）。BEAM 单
  conversation 是 100K token 超长，smoke 必须**截断**——沿用 LoCoMo turn 级
  `--rounds` 裁剪（BEAM 是 conversation-QA，turn 截断适用，与 HaluMem 的
  session 截断不同）。**smoke 只需流程跑通，probing 能否答对无所谓**（用户
  smoke 原则）；保留每能力少量题即可，覆盖尽量多 ability。
- **D3（架构师定）10M 缓做**：10M split 有多 `plans` 层级 + 10M token 工程
  压力，v1 只做 `100k/500k/1m`；`10m` 作后续 variant（需 streaming ingest，
  见 S7）。
- **D4（架构师定）user_profile 等不注入**：conversation_seed/user_profile/
  conversation_plan/user_questions/narratives 是数据生成元信息，默认不进
  method（对齐调研卡，若做 profile-aware 特殊 profile 另行显式留痕）。
- **D5（架构师定）judge 模型**：gpt-4o-mini，标注非论文严格复现。
- **D6（待用户/架构师）event_ordering 排序分是否 v1 纳入**：官方
  event_ordering = kendall-tau 排序分 + rubric judge 双分量。排序分需额外
  fact-extraction LLM + 对齐，较重。**架构师推荐**：v1 先做全 10 能力统一
  rubric judge（含 event_ordering 的 llm_judge_score），kendall-tau 排序分作
  **标注的增强项**（plan 里列为可选 task，成本/复杂度评估后决定），不阻塞
  BEAM 列点亮。请用户认可此裁剪或要求 v1 全做。

## S6 非目标

- 不改协议 v3 实体；不建 operation-level runner（BEAM 是 conversation-QA）。
- 不新增 MethodCapability/TaskFamily enum（S6 接口即契约原则，同 HaluMem）。
- v1 不做 `10m` split；不做真实 API smoke（待预算）。
- 不追求论文数值严格复现（int→float 修正 + judge 模型差异，已标注）。

## S7 工程note（供 plan/未来）

- BEAM 1M/10M 单 conversation 极长，一次性 `ingest(整段)` 有内存/耗时压力。
  v1 smoke 用 `100k` + turn 截断规避。全量 1M/10M 未来可能需框架内 streaming/
  iterator ingest——**但这不暴露为 method 必实现的新接口**（框架内部事，
  归 ws03/工程优化专项），本 workstream 不做。

## S8 完成判据（plan 全部 task 通过后）

1. BEAM adapter：HF arrow 加载（`load_from_disk`）+ `ast.literal_eval` 解析
   probing_questions + chat list[session] 映射 + content 尾标记裁剪 + 四层隐私
   + 三 variant（100k/500k/1m），focused 测试全绿（含私钥扫描）。
2. registration（conversation-QA，`prompt_track="unified"` +
   `unified_prompt_builder`），复用现有 runner，无 operation_level 字段。
3. `beam_rubric_judge` evaluator：rubric 逐条 judge（fake judge 离线测）+
   **float 0/0.5/1（修 int bug，测试专门锁 0.5 不被截断）** + ability breakdown
   + event_ordering 排序分（若 D6 纳入）。
4. registered fake 全链路 smoke：BEAM × fake provider → judge → manifest
   （v3/unified）、artifact、resume。
5. 全量回归 ≥ 当前基线不跌破；compileall 通过。
6. 极小真实 smoke（少量 conversation × turn 截断，覆盖多 ability）待用户预算。

## S9 版本留痕

- 2026-07-08 Opus 4.8 起草 draft，全部结论第一手核对（数据结构、10 能力、
  int/float bug、judge 0/0.5/1 档位、conversation-QA 家族均回官方仓库/真实数据
  验证）。待用户批准（尤其 D6 event_ordering 裁剪）后转 approved 并写 plan。
