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
- **机制卡是第三方行为唯一事实源**（`audits/mechanism-*.md`），冲突停工。
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

## Task 分解

### T1 HaluMem adapter（数据 → 统一 Dataset，隐私隔离）

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

### T2 benchmark registration + operation-level 分派声明

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

### T3 operation-level runner（唯一新 runner 能力）

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
6. artifact：extraction 复用 `session_memory_reports.jsonl`；新增
   `update_probe_results.jsonl`（session_ref + gold memory index +
   memories_from_system + duration）；QA 复用 `method_predictions.jsonl`。
   manifest `protocol_version=v3`/`prompt_track=unified`。
7. resume：单元=user（conversation 级），沿用既有 checkpoint 状态机；不做
   session 级断点。复用既有隔离键派生、原子写、efficiency 观测。

验收：`uv run pytest tests/test_operation_level_runner.py -q` 全绿；fake
provider 须覆盖 ①三段全跑（extraction/update/QA）驱动顺序与检索 purpose/top_k
断言 ②`is_generated_qa_session` 跳过三段 ③extraction N/A 路径（fake 不覆写
end_session）④update 探针无写副作用 ⑤三 artifact 落盘 ⑥累积状态（后 session
更新改变早 session 问题的检索结果）。

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
   `supported_benchmarks={"halumem"}`，prompt 摘自
   `eval/eval_tools.py` 注行号：
   - `halumem_extraction`：integrity(`EVALUATION_PROMPT_FOR_MEMORY_INTEGRITY`)
     + accuracy(`..._ACCURACY`) → recall / weighted_recall / target_accuracy /
     weighted_accuracy / interference_accuracy(FMR) / **F1**（调研卡 §4.1 口径）；
     category_breakdown 按 `memory_type`。
   - `halumem_update`：`EVALUATION_PROMPT_FOR_UPDATE_MEMORY` →
     Correct/Hallucination/Omission/Other 四比例（调研卡 §4.2）。
   - `halumem_qa`：`EVALUATION_PROMPT_FOR_QUESTION` →
     Correct/Hallucination/Omission 三比例（调研卡 §4.3）；category_breakdown
     按 `question_type`。
3. evaluator 只从私有侧读 gold（memory_points / answer / evidence），
   method artifact 读 extracted_memories / memories_from_system /
   system_response。

验收：`uv run pytest tests/test_halumem_*.py -q` 全绿（judge 用 fake client
离线）；每个 evaluator 测 ①judge 输出→聚合口径正确 ②category_breakdown
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
