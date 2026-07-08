---
id: ws02.2
parent: ws02
doc: plan（实施计划，actor 执行）
status: ready
created: 2026-07-08
author: Claude Opus 4.8（架构师）
---
# ws02.2 HaluMem 实施 plan（Full Operation-level）

依据 [spec.md](spec.md)（approved）。actor 施工前必读：`AGENTS.md`、
`docs/reference/actor-handbook.md`（规矩全文）、本 plan 指向的 spec 与机制卡。

## 施工纪律（不可协商）

- TDD：先写/改测试 → 实现 → 跑该 task 验收命令 → 把命令与真实输出粘进本
  plan 对应 task 下方 → 勾选 → **一个 task 一个 commit**（`feat:/fix:/test:/
  docs:` 一行英文）。
- **零真实 API**：全部用 fake provider / fake judge；任何需要真实 LLM 的步骤
  停工上报。judge evaluator 的测试用 fake judge client，不调 OpenAI。
- **第一手事实源按任务类型区分**（2026-07-08 架构师修正，Codex 正确点出旧
  表述不精确）：
  - **benchmark 行为**（adapter/runner/evaluator 对 HaluMem 数据与官方评测的
    映射）→ 事实源 = HaluMem **官方仓库** `third_party/benchmarks/HaluMem-main/`
    （`eval/eval_memzero.py`、`eval/eval_tools.py`、`eval/prompts.py`、
    `eval/evaluation.py`）**第一手**，加 `docs/survey/` 下**三份** HaluMem 卡
    （`benchmarks/HaluMem.md` + `datasets/halumem.md` + `workflows/halumem.md`，
    三份都要读，各有侧重）+ 真实数据 `data/halumem/*.jsonl`。
  - **method 行为**（某 method 原生接口/粒度，如 T5 Mem0 抽取）→ 事实源 =
    method **官方仓库** `third_party/methods/<m>/` 第一手 +
    `audits/mechanism-<m>.md`。
  - **HaluMem 无 `mechanism-halumem.md`**（那是 method 卡，benchmark 不适用，
    别找）。与第一手源冲突时停工。**二手文档（调研卡）可能过时/有误，冲突
    以官方仓库源码为准**。
- 中文 docstring；不改 `third_party/` 算法核心；不动 `outputs/`。
- **基线 819 passed 不得跌破**；每个 task 末尾附 `uv run pytest -q` 尾行。
- 事实源：协议状态以本 spec + ws02 README 断点为准，不凭训练先验。
- 遇 plan 未覆盖情况：停工，写 ws02.2 README"当前断点"，交回架构师。

## 明确不做（防发散）

- 不改协议 v3 实体（`core/provider_protocol.py`）。
- 不新增 `MethodCapability`/`TaskFamily` enum，不用 `validate_compatibility()`
  做 method×benchmark 门控（spec S6：接口即契约）；也不删除旧 enum（留 ws03）。
- 不做真实 API smoke（待用户预算）。
- 不为 HaluMem 建 method×benchmark 专用分支逻辑。
- 不强行给不支持 session 增量抽取的 method 造 extraction 分数（N/A 占位）。

## 架构师裁定（2026-07-08 第二轮：解 Codex T4 前停工 + smoke 定案）

**R1 session 级 evaluator-private gold artifact（解 Codex 停工，架构师 plan
失误第 3 处）**：HaluMem 的 extraction（integrity+accuracy）与 update 评测是
**session 级**——`evaluation.py:54-95` 遍历每个 session 的 `memory_points` vs
`extracted_memories`，**与该 session 有没有 question 无关**。真实数据：Medium
1387 sessions 中 **491 个有 memory_points 但无 question**（Codex 实测）。但当前
artifact 只有 question 级 `evaluator_private_labels.jsonl`，这 491 个 session
的 gold 无法还原 → extraction 分母漏。**裁定**：operation-level runner 新增
**session 级 evaluator-private artifact**（如 `evaluator_private_session_labels
.jsonl`），每个非 generated session 一条：`{conversation_id, session_id,
memory_points(全 gold，私有), dialogue(该 session turns，供 accuracy judge 的
dialogue_str)}`。这是 evaluator-only artifact（method 永不可见，与既有私有标签
同机制，公开 dialogue 放私有 artifact 无泄漏问题）。T4 extraction/update
evaluator 读它；QA evaluator 仍读 question 级私有标签。这是 T3 artifact 补写
（下一批与 T4 同做）。

**R2 smoke 用 CLI 显式 session 控制，覆盖三模式（用户 2026-07-08 提案，架构师
裁定：采纳 + 数据修正）**：
- **采纳**：加 `smoke_session_limit` 到 `BenchmarkLoadRequest` + CLI `--sessions`
  旗标；HaluMem smoke 取每 user **前 M 个连续 session**（累积语义不可跳选）。
  **替换** Codex T1-retouch 里"复用 `smoke_turn_limit` 当 session 数"的做法——
  用户说得对，HaluMem 的自然裁剪单元是 session，给它一等 CLI 控制比复用
  turn_limit 语义清晰（后者对下一个读者是坑）。LoCoMo/LongMemEval 仍用
  `--rounds`(turn) 裁剪，忽略 `--sessions`。
- **最小 smoke = `--sessions 1`（架构师二次自纠，2026-07-08 用户校正）**：
  第一手扫 Medium user[0]：`session[0]` = `n_mp=15`（extraction 有）+
  `has_questions=True`（QA 有）+ `n_update=0`。所以 **1 个 session 就跑通
  extraction + QA 两段**，证明管线通——这才是"极小 smoke"的真需求（flow-through，
  能否答对无所谓，用户 smoke 原则）。推荐最小 smoke：`--conversations 1
  --sessions 1`。
- **覆盖三模式是"可选的更大档"，非最小档**：update 模式最早出现在
  `session[3]`（第 4 个），前 3 个只有 extraction+QA。若额外要点亮 update 段，
  用 `--sessions 4`（挑 update 早出现的 user，如 Medium user[0] session[3]
  `n_update=7`）。**架构师两次自纠**：上上轮"2 sessions"、上一轮"≥5"都犯了
  同一个错——把"覆盖三模式"（nice-to-have）误当"最小 smoke"（真需求），且
  `--sessions 1` 的第一手证据（session[0] 有 mp 有 question）当时没先看。用户
  是对的：极小 smoke 先 session=1 试通，三模式覆盖另立一档。
- HaluMem **不做** turn/round/question 级裁剪（用户定，架构师认同：operation-level
  的累积+session 中心语义下，切 turn 会破坏 session 完整性、切 question 无意义）。

## Task 分解

### T1 HaluMem adapter（数据 → 统一 Dataset，隐私隔离） ✅

改动范围：新增 `src/memory_benchmark/benchmark_adapters/halumem.py` +
`tests/test_halumem_adapter.py`。

步骤：
1. `HaluMemAdapter(BenchmarkAdapter)`，`name="halumem"`，双 variant
   `medium`（`data/halumem/HaluMem-Medium.jsonl`）/ `long`
   （`data/halumem/HaluMem-Long.jsonl`），对齐 MemBench 双 variant 结构
   （`benchmark_adapters/membench.py` 的 `BenchmarkVariantSpec` 用法）。
2. 每行 JSONL（一 user）→ 一个 `Conversation`：`conversation_id=uuid`；每
   session → 一个 `Session`（`session_time`=`start_time`，另存 `end_time`）；
   每 dialogue turn → 一个 `Turn`（`role`/`content`，`turn_time`=turn
   `timestamp`，`normalized_role`=role）。
3. **四层隐私**（严格）：进入公开 `Conversation` 的仅 uuid、start/end_time、
   turn role/content/timestamp、`questions[].question`。以下进
   `GoldAnswerInfo`（每 question 一条，evidence 存该 session 的相关
   memory_points index）：`memory_points` 全字段、`questions[].answer/
   evidence/difficulty/question_type`、`persona_info`（整体私有，D5）。
   session 的 `memory_points` 也须存进私有侧（extraction/update scorer 用），
   建议挂在 session 级私有结构或每 question gold 的 metadata（actor 择一，
   但必须 `validate_no_private_keys` 扫描公开 Conversation 全绿）。
4. `is_generated_qa_session` 标志 → session 私有 metadata（`source_format`
   等旁），供 runner 跳过三段（spec S2.3）。
5. 时间转换器 `parse_halumem_timestamp`：`%b %d, %Y, %H:%M:%S`（如
   `Sep 04, 2025, 21:12:18`）→ ISO；不可解析传 None 不猜测；独立单测。
6. `prepare_halumem_run` + smoke 口径：smoke 按 user 数裁剪
   （`smoke_conversation_limit` = user 数），可选按 session 数裁剪（复用
   `smoke_turn_limit` 语义或加 session 限；actor 按 contracts.py 现有字段，
   不新增契约字段，若不够用停工上报）。

验收：`uv run pytest tests/test_halumem_adapter.py -q` 全绿；测试须含
①三层映射断言 ②公开 Conversation 私钥扫描全绿（gold 不泄漏）③时间转换
④`is_generated_qa_session` 标志保留 ⑤双 variant 源文件。

执行记录（2026-07-07，Codex）：

```text
$ uv run pytest tests/test_halumem_adapter.py -q
......                                                                   [100%]
6 passed in 0.05s
```

```text
$ uv run pytest -q
825 passed, 3 deselected, 2 warnings, 6 subtests passed in 104.61s (0:01:44)
```

**架构师验收发现（2026-07-08，Opus 4.8；两处均架构师 plan 失误，非 Codex）**：

- **F1 evidence 表示错误**：plan 原写"evidence 存该 session 的 memory_points
  index"——错。第一手核对（`datasets/halumem.md` §6.1 + 真实数据 +
  `eval_tools.py:352-365` QA judge `key_memory_points`）：evidence 是
  `list[{memory_content, memory_type}]`，QA judge 需要 evidence 的
  **memory_content 文本**（不是 index）；且 evidence 可引用**更早 session**
  的记忆，只在本 session memory_points 里映射 index 会**丢失跨 session
  evidence**。Codex 防御性保留了 `metadata["raw_evidence"]` 全结构（未丢数据，
  值得表扬），但 `GoldAnswerInfo.evidence` 存的 index 不完整、是陷阱。
  **修正（T1 re-touch）**：`GoldAnswerInfo.evidence` 直接存 evidence 的
  memory_content 字符串列表（Memory Boundary 类问题 evidence=`[]`）；保留
  raw_evidence 的 memory_type 供分析；删除不完整的 index 映射。
- **F2 smoke 口径不够小**：`prepare_halumem_run` 只按
  `smoke_conversation_limit`（user 数）裁剪，**不裁 session**。HaluMem 一个
  user ≈ 65 sessions × ~20 turns（真实数据 user0=65 sessions）——"1 user"
  smoke 依然巨大，违背用户"smoke 必须极小"要求（LoCoMo/LongMemEval 是
  ~20 rounds/40 turns 级）。**修正（T1 re-touch）**：HaluMem smoke 须能裁到
  **每 user 前 M 个整 session**（不切断 session，保 operation-level 累积语义），
  M 由 smoke 参数驱动（reinterpret `smoke_turn_limit` 为"每 user 最大 session
  数"，docstring 写清；或加 `smoke_session_limit` 字段——actor 择一，倾向前者
  免 CLI 改动，拿不准停工上报）。**注：本条 smoke 参数方案已被下方"第二轮
  R2"取代**——定案为加一等 `smoke_session_limit`+`--sessions`（HaluMem 专用），
  最小 smoke `--sessions 1`（跑通 extraction+QA），不是这里旧写的"2 sessions
  点亮三段"（2 sessions 到不了 update，见 R2 第一手数据修正）。

这两项并入 actor 下一批（与 T3 同批 re-touch T1）。

T1 re-touch 执行记录（2026-07-07，Codex）：

```text
$ uv run pytest tests/test_halumem_adapter.py -q
.......                                                                  [100%]
7 passed in 0.04s
```

```text
$ uv run pytest -q
828 passed, 3 deselected, 2 warnings, 6 subtests passed in 101.26s (0:01:41)
```

### T2 benchmark registration + operation-level 分派声明 ✅

改动范围：`benchmark_adapters/registry.py`（+ 可能
`benchmark_adapters/contracts.py`）、`tests/test_benchmark_registry.py`。

步骤：
1. 在 `BenchmarkRegistration` 上加一个 **benchmark 侧 runner 声明字段**（建议
   `operation_level: bool = False`，或更具扩展性的 `runner_kind: str =
   "conversation_qa"`；actor 择一，倾向布尔最简）。这是 benchmark 自报用哪个
   runner，**不是** method 侧能力 enum。默认值保证既有 4 benchmark 注册不变。
2. HaluMem registration：`prompt_track="unified"` +
   `unified_prompt_builder=build_halumem_unified_answer_prompt`（PROMPT_MEMZERO，
   见 T4 note；QA 段用）、`operation_level=True`、双 variant、`prepare_run`。
   `required_capabilities` 留空 / 不参与门控（spec S6）。
3. **不**在 `_REGISTRATIONS` 里给 HaluMem 声明 `MethodCapability`，**不**调
   `validate_compatibility`。

验收：`uv run pytest tests/test_benchmark_registry.py -q` 全绿；含
①HaluMem 注册可取出且 `operation_level=True` ②既有 benchmark 默认
`operation_level=False` 不变 ③unified prompt builder 双向一致性校验
（对齐 MemBench 先例）。

执行记录（2026-07-07，Codex）：

```text
$ uv run pytest tests/test_benchmark_registry.py -q
....................................                                     [100%]
36 passed in 17.06s
```

```text
$ uv run pytest -q
827 passed, 3 deselected, 2 warnings, 6 subtests passed in 104.60s (0:01:44)
```

### T3 operation-level runner（唯一新 runner 能力） ✅

改动范围：`runners/prediction.py`（新增
`run_operation_level_predictions()` 及 helper）或新文件
`runners/operation_level.py`（actor 择一，倾向新文件以免 prediction.py 膨胀）；
`cli/run_prediction.py`（registered service 按 `operation_level` 字段分派）；
`tests/test_operation_level_runner.py`。

步骤（严格实现 spec S4.2 驱动序列）：
1. 单 user 驱动：`build provider` → 逐 session 时序：ingest turns（按 provider
   声明粒度经 `GranularityAggregator` 聚合）→ `end_session` 取 extraction 报告
   → 若 `is_generated_qa_session` 则 `continue`（跳过下面两段，spec S2.3）→
   update 探针（每个 `is_update!="False" 且 original_memories` 的 gold memory：
   `retrieve(purpose="memory_update_probe", query_text=gold.memory_content,
   top_k=10)`）→ QA（每 question：`retrieve(purpose="qa", top_k=20)` →
   framework reader PROMPT_MEMZERO → system_response）→ `end_conversation` →
   `cleanup`。
2. **extraction 增量 vs update/QA 累积**（spec S4.2）：extraction 报告是本
   session 增量；update/QA 在该 session 后就地对累积状态检索。**不得**改成
   "全 ingest 再全 retrieve"。
3. **接口即契约 preflight**（spec S6）：run 启动前用
   `type(provider).end_session is not MemoryProvider.end_session` 判定 extraction
   run-or-N/A，从 method factory 得真实 provider 类（不依赖
   `_UnusedRootSystem`）；N/A 时 extraction artifact 该 method 段留占位，
   不 assert 失败。
4. **私有 gold → update 探针受控通道**（spec S4.3）：gold memory_content 从
   `GoldAnswerInfo` 私有侧注入 `RetrievalQuery.query_text`，只在本 runner、只对
   `purpose="memory_update_probe"`；不经公开 Conversation。
5. **update 探针无写副作用契约**（D1 兜底）：断言 update 探针 `retrieve` 前后
   provider 记忆状态不变（对 fake provider 记录的写调用计数断言）。
6. artifact：extraction 复用 `session_memory_reports.jsonl`（provider 报告）；
   新增 `update_probe_results.jsonl`（session_ref + gold memory index +
   memories_from_system + duration）；QA 复用 `method_predictions.jsonl`。
   manifest `protocol_version=v3`/`prompt_track=unified`。**⚠ R1 补充（见文末
   任务卡）**：还须新增 **evaluator-private** `evaluator_private_session_labels
   .jsonl`（session gold memory_points + dialogue，method-agnostic），T4
   extraction/update evaluator 读它——这是本步在 R1 裁定后的追加，别只写
   provider 报告。
7. resume：单元=user（conversation 级），沿用既有 checkpoint 状态机；不做
   session 级断点。复用既有隔离键派生、原子写、efficiency 观测。

验收：`uv run pytest tests/test_operation_level_runner.py -q` 全绿；fake
provider 须覆盖 ①三段全跑（extraction/update/QA）驱动顺序与检索 purpose/top_k
断言 ②`is_generated_qa_session` 跳过三段 ③extraction N/A 路径（fake 不覆写
end_session）④update 探针无写副作用 ⑤三 artifact 落盘 ⑥累积状态（后 session
更新改变早 session 问题的检索结果）。

执行记录（2026-07-07，Codex）：

```text
$ uv run pytest tests/test_operation_level_runner.py -q
...                                                                      [100%]
3 passed in 0.47s
```

```text
$ uv run pytest -q
831 passed, 3 deselected, 2 warnings, 6 subtests passed in 102.16s (0:01:42)
```

### T4 三个 judge evaluator + QA unified prompt

改动范围：`evaluators/halumem_extraction.py`、`evaluators/halumem_update.py`、
`evaluators/halumem_qa.py`、`evaluators/registry.py`、HaluMem unified prompt
（放 `benchmark_adapters/halumem.py`，对齐 MemBench 的
`build_membench_unified_answer_prompt` 位置）；对应 tests。

步骤：
1. QA unified prompt `build_halumem_unified_answer_prompt`：复刻官方
   `PROMPT_MEMZERO`（`third_party/benchmarks/HaluMem-main/eval/prompts.py:1-40`，
   变量 `{context}{question}`），摘录注行号，冻结 profile
   `halumem_memzero_v1`；`prompt_track="unified"`。
2. 三 evaluator（模板：`longmemeval_judge.py`），均 gpt-4o-mini judge
   （D2，profile 标注非论文严格复现），`requires_api=True`，
   `supported_benchmarks={"halumem"}`。**judge 签名与聚合口径以第一手
   `eval/eval_tools.py` + `eval/evaluation.py` 为准**（不是调研卡转述），prompt
   摘录注行号：
   - `halumem_extraction`（两次 judge，`eval_tools.py:286-326`）：
     ① integrity `evaluation_for_memory_integrity(extract_memories,
     target_memory)` **按每个 gold memory point 迭代**（`_INTEGRITY` prompt）→
     score 2/1/0；② accuracy `evaluation_for_memory_accuracy(dialogue,
     golden_memories, candidate_memory)` **按每条 extracted memory 迭代**
     （`_ACCURACY` prompt）→ score 2/1/0 —— **注意 accuracy judge 需要本
     session 的 dialogue 文本**（公开侧）+ golden_memories（私有）。聚合
     recall(integrity==2 占非 interference gold) / weighted_recall(importance
     加权) / target_accuracy / weighted_accuracy / FMR(interference gold 的
     integrity==0 比例) / **F1=2·target_accuracy·recall/(target_accuracy+
     recall)**——**公式以 `evaluation.py` 源码为准，actor 逐行核对**；
     category_breakdown 按 `memory_type`。
   - `halumem_update`（`eval_tools.py:329-349`）：
     `evaluation_for_update_memory(extract_memories=memories_from_system,
     target_update_memory=gold.memory_content, original_memory=concat(
     original_memories))` → Correct/Hallucination/Omission/Other 四比例。
   - `halumem_qa`（`eval_tools.py:352-365`）：`evaluation_for_question(
     question, reference_answer=gold.answer, key_memory_points=concat(evidence
     的 memory_content), response=system_response)` → Correct/Hallucination/
     Omission 三比例；category_breakdown 按 `question_type`（6 类，见
     `datasets/halumem.md` §8）。
3. evaluator 私有侧读 gold（`session_memory_points` / answer / evidence
   memory_content），method artifact 读 extracted_memories /
   memories_from_system / system_response。**QA judge 的 key_memory_points 用
   evidence 的 memory_content（T1-F1 修正后 `GoldAnswerInfo.evidence` 即该
   列表）**。

**T4 第一手口径补充（架构师 2026-07-08 读 `evaluation.py` 逐行核对，必须遵守——
调研卡没讲清这些，之前 spec 也漏了）**：

- **integrity 与 update 是互斥路由，不是独立两段**（`evaluation.py:58-70`）：
  对每个 gold memory point——`is_update=="True" 且 memories_from_system 非空`
  → 进 **update** 评测；**否则**（非 update，或 update 但检索为空）→ 进
  **integrity/recall**。即成功探测到的 update 点**从 recall 分母中剔除**。
  T4 必须复刻此路由，否则 recall 分母错。
- **integrity 聚合**（`evaluation.py:214-246`）：非 interference gold 计入
  `recall(all)=(integrity_score==2 的数)/(非 interference gold 数)`；
  `weighted_recall=Σ(0.5·integrity_score·importance)/Σ importance`（**0.5
  因子**：score2→满分、score1→半分）；extracted 为空串时 integrity 直接记 0
  （`:108-111`）。
- **FMR 在 memory_accuracy 名下**（`:247-250`）：
  `interference_accuracy=(interference gold 中 integrity_score==0 的数)/
  (interference gold 数)`。
- **accuracy 聚合**（`:259-286`）：需 `is_included_in_golden_memories`；
  `target_accuracy(all)=Σ(0.5·accuracy_score, 仅 included)/(included 数)`；
  `weighted_accuracy(all)=Σ(0.5·accuracy_score, 全部)/(全部 extracted 数)`。
- **F1**（`:289-292`）：`compute_f1(precision=target_accuracy(all),
  recall=recall(all))`。
- **accuracy judge 的 dialogue_str 格式**（`:74-81`）：
  `[{timestamp}]{role}: {content}`，每个 **assistant turn 后加一空行**；
  `golden_memories_str` **排除 interference**（`:83-85`）。
- **update judge 输入**（`:158-162`）：`"\n".join(memories_from_system)`、
  `memory_content`、`"\n".join(original_memories)`；ratio 分母 = 全部 update
  records（`:321`，即有 memories_from_system 的点）。
- **QA judge 输入**（`:180-185`）：question、answer、
  `"\n".join(e["memory_content"] for e in evidence)`、system_response；
  Memory Boundary 类 evidence=`[]`（key_memory_points 为空串）。

验收：`uv run pytest tests/test_halumem_*.py -q` 全绿（judge 用 fake client
离线）；每个 evaluator 测 ①judge 输出→聚合口径与 `evaluation.py` 逐条对齐
（含 integrity/update 互斥路由、0.5 因子、FMR、F1）②category_breakdown
③N/A（extraction 段某 method 无报告时不计入分母、记 N/A 不记 0）。

### T5 逐 method extraction 能力核实（D4，接口即契约的落地）

改动范围：`methods/mem0_adapter.py`（+ 测试）；`audits/mechanism-*.md` 记录
逐 method 裁定；**不改**其余 method 的行为（保持不覆写 end_session = N/A）。

步骤：
1. **Mem0 → 实现 session 增量 extraction 报告**：HaluMem 下 Mem0 消费粒度
   特化为 `session`（registry 按 benchmark，对齐既有 LongMemEval 特化先例），
   `end_session` 返回 `SessionMemoryReport(memories=本 session add().results 的
   memory 文本)`。证据：`Memory.add()` 返回本次插入 records
   （机制卡 mem0 §"add 返回"，main.py:738-745,957-971）。加 focused 测试：
   一 session ingest 后 end_session 返回该 session 增量记忆。
2. **SimpleMem → N/A**：窗口抽取 WINDOW_SIZE=40，粒度≠session，给不出干净
   session 增量（机制卡 simplemem：finalize/window 语义）→ 不覆写 end_session
   返回报告，extraction N/A。在机制卡 §7 记录裁定 + 证据。
3. **MemoryOS / A-Mem / LightMem → 逐卡核实**：默认不实现 session 增量抽取
   → N/A，除非机制卡证据显示可干净提供。每个在机制卡 §7 记一句裁定 + 证据。

验收：`uv run pytest tests/test_mem0_adapter.py -q` 全绿（含 Mem0 HaluMem
extraction 报告测试）；机制卡逐 method 裁定已写。

### T6 registered fake 全链路 smoke

改动范围：`tests/test_halumem_registered_prediction.py`。

步骤：HaluMem × fake provider（覆写 end_session 提供增量报告）端到端：
operation-level run → 三 evaluator（fake judge）→ 断言 manifest
（`protocol_version=v3`, `prompt_track=unified`）、三 artifact 非空、
resume completed/pending user 回归。另加一条 fake provider **不**覆写
end_session 的用例，断言 extraction N/A 而 update+QA 正常。

验收：该文件全绿；`uv run pytest -q` ≥819 passed；
`uv run python -m compileall -q src/memory_benchmark tests` 通过。

### T7 收尾

改动范围：`docs/reference/method-interface-inventory.md`（HaluMem 接入节）、
ws02 README 矩阵表（HaluMem 列点亮为 adapter 就绪待 smoke）、ws02.2 README
勾选与断点、roadmap 行。

验收：`git status --short` 干净；文档链接有效。

## 基线与顺序

- 顺序：T1→T2→T3→T4→T5→T6→T7（T3 依赖 T1/T2，T4 独立可与 T3 并行，T5 依赖
  T3 的 end_session 契约，T6 依赖全部）。
- 这是目前最大的 plan（7 task，跨 adapter/runner/evaluator/method 四层）。允许
  跨多个 actor 会话接力；每个 actor 上工先读本 plan"当前进度"（勾选状态）。
- 做不对可迭代（用户 2026-07-08："一次性作为，做不对也没关系，可后续再改"）——
  但每个 task 的验收门（测试全绿 + 基线不跌）不可跳过。

## 下一批 actor 任务卡（架构师 Opus 4.8 2026-07-08 签发；Codex 从这里接）

> 这张卡是下一批的**唯一权威入口**，凡与上文 T3 步骤6 / T4 步骤3 的旧措辞冲突，
> 以本卡为准（那两处是 R1 裁定前写的，未并入 session 私有 artifact）。

**先解 Codex 停工的二选一 —— R1 裁定（决定性，非提案）：新增
evaluator-private session artifact，不走 report metadata。**

裁定 = **Option A**。operation-level runner 新增 `evaluator_private_session_labels
.jsonl`，每个 `is_generated_qa_session==False` 的 session 一条：

```
{conversation_id, session_id,
 memory_points: [<该 session 全部 gold memory point，私有>],
 dialogue:      [<该 session 的公开 turns，供 accuracy judge 的 dialogue_str>]}
```

- **写入方 = runner**（它已逐 session 迭代）；gold 从私有 Conversation 取（与既有
  question 级 `evaluator_private_labels.jsonl` **同一取 gold 路径**，method 永不
  可见），dialogue 用公开 turns。**method-agnostic**：不管 provider 有没有
  extraction 能力都写（gold 来自数据集，不依赖 method 是否产报告）。
- **为何不选 Option B（report metadata 携带 gold）**：① `session_memory_reports
  .jsonl` 是 provider 产出物（方法抽了什么），塞进 benchmark gold = 混淆两种
  数据来源，违背四层隐私"gold 不进任何 method-邻接物"的精神；② N/A method 没
  report（`report=None`），但那 491 个无 question session 的 gold 必须存在才能
  算 extraction 分母——gold 挂在 method-依赖、可能为 None 的 report 上是脆的；
  ③ 已有 question 级私有标签先例，加一个 session 级私有标签文件是同机制、同发现
  路径，evaluator 统一从私有标签文件读 gold。

**批次顺序（一个 actor 会话可接力，每步验收门不可跳）：**

1. **T3-patch（R1 artifact）**：runner 写 `evaluator_private_session_labels.jsonl`
   （上述 schema，非 generated session 全写，method-agnostic）。测试锁：491-类
   session（有 mp 无 question）也进该 artifact、公开 conversation 仍过
   `validate_no_private_keys`。

   执行记录（2026-07-08，Codex）：

   ```text
   $ uv run pytest tests/test_operation_level_runner.py -q
   ...                                                                      [100%]
   3 passed in 0.35s
   ```

   ```text
   $ uv run pytest -q
   831 passed, 3 deselected, 2 warnings, 6 subtests passed in 107.92s (0:01:47)
   ```
2. **R2（CLI session 控制，HaluMem 专用）**：加 `smoke_session_limit` 到
   `BenchmarkLoadRequest` + `--sessions` 旗标；HaluMem smoke 取每 user 前 M
   连续 session。**替换** T1-retouch 的"复用 smoke_turn_limit 当 session 数"。
   **最小 smoke = `--sessions 1`（跑通 extraction+QA，第一手 session[0]
   `n_mp=15`+`has_questions=True` 证据），不是旧写的 ≥5**。HaluMem 忽略
   `--rounds`；LoCoMo/LME 忽略 `--sessions`——**传错轴要明确报错，别静默**。

   执行记录（2026-07-08，Codex）：

   ```text
   $ uv run pytest tests/test_halumem_adapter.py tests/test_main_cli.py tests/test_prediction_cli.py -q
   ........................................................................ [ 90%]
   ........                                                                 [100%]
   80 passed in 7.65s
   ```

   ```text
   $ uv run pytest -q
   834 passed, 3 deselected, 2 warnings, 6 subtests passed in 108.76s (0:01:48)
   ```
3. **T4（三 evaluator）**：extraction/update evaluator 读 R1 session artifact 取
   gold memory_points + dialogue_str；QA evaluator 读 question 级私有标签。聚合
   口径**逐行照 T4"第一手口径补充"块 + `evaluation.py`**（integrity/update
   互斥路由、0.5 因子、FMR、F1、dialogue_str 格式、排除 interference）。judge
   用 fake client 离线测。
4. **T5（逐 method extraction）**：Mem0 实现 session 增量报告（HaluMem 下粒度
   特化 session）；SimpleMem/其余默认 N/A（不覆写 end_session），机制卡记裁定+
   证据。
5. **T6 fake 全链路 smoke** + **T7 收尾**。

**纪律（每 actor 会话开工必读）**：① 一手源 = 第三方仓库代码 + 真实数据，调研卡
二手可疑，口径拿不准去 `evaluation.py` 逐行核；② 遇 plan 未覆盖的事实缺口 →
停工上报，别硬编（你这次 R1 停**对了**）；③ 不改 `third_party/`；④ 不自动
commit；⑤ 基线 ≥831 不跌破，每 task focused 测试全绿是硬门；⑥ 私有 gold 只走
evaluator-private artifact，公开 conversation 过私钥扫描。
