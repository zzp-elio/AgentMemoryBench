---
id: ws02.3
parent: ws02
doc: plan（大型 benchmark，spec 与 plan 分离）
status: ready（待 actor 施工）
created: 2026-07-08
author: Claude Opus 4.8（架构师）
---
# ws02.3 BEAM Adapter 实施 plan（conversation-QA + rubric judge）

依据 [spec.md](spec.md)（approved，D1-D6 全定案）。本 plan 每条第三方结论都回
一手源（`third_party/benchmarks/BEAM/` 源码 `文件:行号` + `data/BEAM/` 真实
arrow）。BEAM 是 **conversation-QA 家族**，复用现有 `run_predictions`，无
operation-level runner、无协议改动。工作量三处：① adapter；② `beam_rubric_judge`
evaluator（含修官方 int 截断 bug + ability 聚合）；③ unified answer prompt 接线。

## 架构师第一手已定（施工前必读，免 actor 重新踩坑）

- **answer prompt 源已定（解 spec D1-note）**：BEAM unified answer prompt =
  官方 `answer_generation_for_rag`（`src/prompts.py:11683-11701`），占位符
  `<context>` / `<question>`（注意是尖括号占位、`.replace()` 注入，不是
  f-string）。语义："只用 context 回答、**不得**用内部知识、直接简洁、只输出
  答案不解释"。这是 **RAG 路径**模板（`long_term_memory_methods.py:639-641`
  用它），正好对应我们 unified 口径：method 返回 `formatted_memory` → `<context>`，
  probing question 文本 → `<question>`。**不要**用 long-context 路径那条
  （`long_term_memory_methods.py:587-591`，只把 `NOTE: Only provide the answer…
  Question:{query}` 追加到全量历史——那是 no-memory 基线，不是我们的检索口径）。
- **裁剪轴 = turn**（BEAM 是超长单 conversation 的 conversation-QA，§spec S1）：
  smoke 沿用 LoCoMo 的 turn/round 裁剪，**不是** HaluMem 的 session 裁剪。CLI
  轴校验：BEAM 吃 `--rounds`，忽略 `--sessions`（见 roadmap CLI 整治条）。
- **int→float 修正是硬要求**（spec S4.2，D1）：官方 9 个 `evaluate_*` 用
  `int(response['score'])`（`compute_metrics.py:357,385,454,483,512,541,570,
  599,628`）把 judge 的 0.5 截成 0；judge prompt 明写 0.5 合法
  （`prompts.py:11584`）。本框架 evaluator 统一 float，profile 标注差异。

## Task 分解

### T1 BEAM adapter（arrow → 统一 Dataset，四层隐私）

改动范围：新增 `src/memory_benchmark/benchmark_adapters/beam.py` +
`tests/test_beam_adapter.py`；数据 `data/BEAM/beam_dataset/{100K,500K,1M}`
（HF arrow，`load_from_disk`）。

步骤（每条回一手实测，spec S2）：
1. `BeamAdapter(BenchmarkAdapter)`，`name="beam"`，variant `100k`/`500k`/`1m`
   （**保留本地 split 名 `100K` 不改成论文 `128K`**，spec S1，HF split 名已
   第一手确认为 `100K`）。`10m` 本期不做（spec D3/S7）。
2. **加载**：`datasets.load_from_disk`；一 row → 一 Conversation
   （`conversation_id` 隔离）。列：`conversation_id, conversation_seed,
   narratives, user_profile, conversation_plan, user_questions, chat,
   probing_questions`（第一手实测）。
3. **chat 映射**：`chat` 是 **list[session]**（外层 session 列表、内层 turn
   列表）；turn 字段 `role/content/id/index/question_type/time_anchor`。
   每内层 list → 一 `Session`，每 turn → 一 `Turn`；`time_anchor`（如
   `March 15, 2024`）→ `Turn.turn_time`。**content 末尾裁 `->-> a,b` 尾标记**
   （第一手实测，plan 施工时核对 `->->` 分隔规则，只留真实文本；用参数化测试
   锁裁剪正确、不误伤正文里的 `->`）。
4. **probing_questions 解析**：是 **Python-repr 字符串**（单引号），必须
   `ast.literal_eval`，**不是** `json.loads`（第一手实测，调研卡未标）。解析后
   `{ability: [question_obj, ...]}`，**10 个 ability × 每 2 题 = 20 Question**
   （第一手实测每类恰 2）。ability key 见 T3。
5. **四层隐私**（spec S2.3）：
   - 公开进 method：`conversation_id`、turn `role/content(裁尾)/id/index/
     time_anchor`、probing `question` 文本。
   - 私有入 `GoldAnswerInfo`（evaluator-only）：question_obj 的 `rubric`（judge
     核心）、`ideal_response`、`difficulty`、`abstention_type`、`why_unanswerable`、
     `plan_reference`（第一手 question_obj keys 实测）；row 级 `conversation_seed`
     / `user_profile` / `conversation_plan` / `user_questions` / `narratives`
     （数据生成元信息，D4 不注入）。
   - 唯一 case id：`conversation_id + ability + 题序`（probing 无全局 qid）。
6. 校验：公开 Conversation 过 `validate_no_private_keys` 全绿（rubric/
   ideal_response 等私钥不得泄漏）。

验收：`uv run pytest tests/test_beam_adapter.py -q` 全绿；含 ①三 variant 加载
②chat list[session] 映射 + content 尾标记裁剪（参数化）③probing_questions
`ast.literal_eval` 解析出 10 ability × 2 题 ④私钥扫描（rubric 等不入公开侧）。

### T2 benchmark registration（conversation-QA + unified answer prompt）

改动范围：`benchmark_adapters/registry.py`、`benchmark_adapters/beam.py`
（unified prompt builder）、`tests/test_benchmark_registry.py`。

步骤：
1. **unified answer prompt** `build_beam_unified_answer_prompt(formatted_memory,
   question)`：复刻官方 `answer_generation_for_rag`
   （`src/prompts.py:11683-11701`，摘录注行号），`<context>`←formatted_memory、
   `<question>`←question 文本；冻结 profile `beam_rag_v1`；`prompt_track=
   "unified"`。放 `beam.py`（对齐 MemBench `build_membench_unified_answer_prompt`
   位置）。
2. BEAM registration：`prompt_track="unified"` + `unified_prompt_builder` +
   `prediction_transform`（若答案需归一，如去引号/截断；BEAM 是自由文本答案，
   一般直通，带双向一致性校验对齐 MemBench 先例）、三 variant、`prepare_run`。
   **不声明** `operation_level`（默认 False = conversation-QA，复用现有 runner）。
   **不声明** MethodCapability / 不调 `validate_compatibility`（spec S6 接口即
   契约）。
3. `required_capabilities` 留空 / 不参与门控。

验收：`uv run pytest tests/test_benchmark_registry.py -q` 全绿；含 ①BEAM 注册
可取出、`operation_level` 缺省 False ②unified prompt builder 双向一致性校验
③既有 benchmark 注册不变。

### T3 `beam_rubric_judge` evaluator（rubric 逐条 judge + 修 int bug + ability 聚合）

改动范围：新增 `evaluators/beam_rubric_judge.py`、`evaluators/registry.py`、
`configs/evaluators/beam_rubric_judge.toml`、`tests/test_beam_rubric_judge.py`。

步骤（第一手 `compute_metrics.py`，spec S4）：
1. **per-question 打分**：judge 用 `unified_llm_judge_base_prompt`
   （`src/prompts.py:11547-11591`，**SCORING SCALE 明写 1.0/0.5/0.0**），逐条
   `rubric` item 判（1.0 完全 / 0.5 部分 / 0.0 不合规）；
   `llm_judge_score = Σ(item score)/len(rubric)`（`compute_metrics.py:346-360`）。
2. **修官方 int 截断 bug（硬要求，spec S4.2 / D1）**：**统一用 float**，绝不
   `int()`。官方 9 个 `evaluate_*` 的 `int(response['score'])`
   （`compute_metrics.py:357,385,454,483,512,541,570,599,628`）把 0.5 截成 0，
   唯 `evaluate_event_ordering` 用 `float()`（:425）。**测试专门锁**：单条
   rubric item 得 0.5 时聚合分是 0.5 不是 0。profile 标注"修正官方 int 截断、
   采 prompt/论文语义、与官方数值有差异"。
3. **event_ordering（v1 仅 rubric，kendall-tau 排序分 defer 到 v2）**：v1 只算
   event_ordering 的 `llm_judge_score`（与其余 9 类同逻辑）。**不做** kendall-tau
   排序分（`compute_metrics.py:270-308` 的 tau_b×set-f1，需额外 fact-extraction
   LLM，spec D6 已决 defer）。→ 见文末"承诺 backlog"。
4. **聚合与 breakdown**（spec S4.3）：per-question → per-ability（每能力 2 题取
   均）→ overall（10 能力）；`category_breakdown` 按 ability。
5. **10 个 ability**（第一手 `compute_metrics.py` 10 个 `evaluate_*` = 真实
   probing_questions 10 key）：`abstention, contradiction_resolution,
   event_ordering, information_extraction, instruction_following,
   knowledge_update, multi_session_reasoning, preference_following,
   summarization, temporal_reasoning`。
6. evaluator 元信息：`metric_name="beam_rubric_judge"`、`requires_api=True`、
   `supported_benchmarks={"beam"}`、gpt-4o-mini judge（D5，标注非严格复现）；
   judge prompt 摘录注行号。

验收：`uv run pytest tests/test_beam_rubric_judge.py -q` 全绿（judge 用 fake
client 离线）；含 ①rubric 逐条聚合口径与 `compute_metrics.py:346-360` 对齐
②**float 0/0.5/1 锁 0.5 不被截断**（回归官方 bug）③10 ability breakdown
④event_ordering v1 走 rubric 路径不触发 kendall-tau。

### T4 registered fake 全链路 smoke

改动范围：`tests/test_beam_registered_prediction.py`。

步骤：BEAM × fake provider 端到端：`ingest(conversation)` → 每 probing
question `retrieve(purpose="qa")` → framework reader（`answer_generation_for_rag`
unified prompt）→ `beam_rubric_judge`（fake judge）→ 断言 manifest
（`protocol_version=v3`, `prompt_track=unified`）、artifact
（`method_predictions.jsonl` + `answer_prompts.prediction.jsonl` +
`evaluator_private_labels.jsonl` 含 rubric）非空、resume completed/pending
conversation 回归。

验收：该文件全绿；`uv run pytest -q` ≥ 当前基线不跌破；
`uv run python -m compileall -q src/memory_benchmark tests` 通过。

### T5 smoke CLI 接线 + 极小真实 smoke 命令

改动范围：确认 BEAM 走既有 turn/round 裁剪（`--rounds`）；若 CLI 轴校验整治
（roadmap CLI 条）未落地，本期 BEAM 至少复用 LoCoMo 的 turn 裁剪路径，不新增
session 轴。

步骤：
1. BEAM smoke：默认 `100k`（最小，20 样本）+ **turn 截断**（`--rounds`，
   spec D2）。**smoke 只需 flow-through**（probing 能否答对无所谓，用户 smoke
   原则）；保留少量 turn，覆盖尽量多 ability。
2. 产出架构师给用户的**极小真实 smoke 命令**（1 worker + 1 conversation +
   turn 截断），待用户预算确认后跑，记成本 observation（对齐 ws05）。BEAM 单
   conversation 超长（100K token），1M/10M 一次性 ingest 的工程压力见 spec S7
   （v1 用 100k + 截断规避）。

验收：fake 链路下 `--rounds` 截断生效、覆盖多 ability；真实 smoke 命令写入
README（待预算）。

### T6 收尾

改动范围：`docs/reference/method-interface-inventory.md`（BEAM 接入节，若适用）、
ws02 README 矩阵表（BEAM 列点亮为 adapter 就绪待 smoke）、ws02.3 README 勾选与
断点、roadmap 行（ws02.3 → adapter 就绪）。

验收：`git status --short` 干净；文档链接有效。

## 承诺 backlog（非可选，D6 已决，勿当可选砍）

- **kendall-tau event_ordering 排序分（v2）**：官方 event_ordering 是
  kendall-tau_b 排序分（`compute_metrics.py:270-308`：语义对齐 → tau_norm ×
  set-f1 → `final_score=tau_norm*f1`）+ rubric judge 双分量。需额外
  fact-extraction LLM + 事件对齐。**触发条件 = BEAM v1 smoke 跑通后**。挂
  ws02.3 README"长期挂账"。用户 2026-07-08 明确"别忘记后续把 kendall-tau
  排序加上"。

## 基线与顺序

- 顺序：T1→T2→T3→T4→T5→T6（T3 独立可与 T1/T2 并行；T4 依赖 T1-T3；T5 依赖
  T4）。
- 每个 task 验收门（focused 测试全绿 + 全量基线不跌破 + compileall）不可跳过。
- actor 每会话开工先读本 plan"当前进度"（勾选状态）+ `actor-handbook.md`；遇
  plan 未覆盖的一手事实缺口 → 停工上报架构师，别硬编（对齐 HaluMem R1 判例）。
