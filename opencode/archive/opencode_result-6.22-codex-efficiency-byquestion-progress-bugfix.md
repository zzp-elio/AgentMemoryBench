# OpenCode 执行记录 — 2026-06-22 多问题修复与会话记录

## 概览

本次会话修复/诊断以下问题：
1. A-Mem `efficiency_by_question.prediction.json` 中 LLM token 全部为 0（数据实际已采集，summary bug）
2. `--max-new-conversations 1` 时进度条显示 0/500 而非 0/1（仅显示问题，work plan 本身正确）
3. A-Mem smoke summary 脚本重新生成（无需重跑实验）
4. 四 method embedding 观测差异诊断（A-Mem/LightMem vs MemoryOS）
5. 提供四 method × LongMemEval-S 1-conversation cost pilot 命令并二次校验参数链路

---

## 1. efficiency_by_question LLM token 全 0 — 根因与修复

### 读了哪些文件

- `outputs/amem-longmemeval-s-smoke-1c20r-20260622-s-cleaned/summaries/efficiency_by_question.prediction.json` — 确认全 0
- `outputs/amem-longmemeval-s-smoke-1c20r-20260622-s-cleaned/artifacts/efficiency_observations.prediction.jsonl` — 121 条 raw observation，确认 retrieval/answer LLM token 已采集（api_usage），只是 summary 未聚合
- `src/memory_benchmark/analysis/efficiency.py` — `build_efficiency_report_payloads()` 逻辑
- `src/memory_benchmark/runners/prediction.py` — `_build_prediction_work_plan()`、`run_predictions()`、`_run_isolated_worker_pipeline()`、`_answer_pending_questions()`
- `src/memory_benchmark/observability/progress_reporter.py` — progress API
- `src/memory_benchmark/core/interfaces.py` — `BaseMemoryProvider` / `BaseMemorySystem`
- `src/memory_benchmark/core/results.py` / `entities.py` — 数据结构
- `src/memory_benchmark/methods/registry.py` — 四 method 注册状态
- `src/memory_benchmark/methods/mock.py` — mock provider
- `src/memory_benchmark/readers/answer.py` — `FrameworkAnswerReader`

### 根因

`src/memory_benchmark/analysis/efficiency.py:234`

`build_efficiency_report_payloads()` 按 observation 顺序迭代。A-Mem LongMemEval smoke 中，retrieval LLM 调用（`amem-query-llm`）和 answer LLM 调用（`gpt-4o-mini`）的记录先于 `QuestionEfficiencyObservation` 出现。`LLMCallObservation` 处理时通过 `_question_record_if_present()` 创建或更新 question record，正确累加 token。但后续 `QuestionEfficiencyObservation` 到达时（line 234），直接用全新 dict **覆盖**已有 record，把 LLM token 计数器全重置为 0。

关键证据：raw observation 中 question-level record 有 `observation_type: llm_call, stage: answer, model_id: gpt-4o-mini, input_tokens: 9581, output_tokens: 120` 和 `stage: retrieval, model_id: amem-query-llm, input_tokens: 69, output_tokens: 13`，全部是 `api_usage`。

### 修复

**文件**: `src/memory_benchmark/analysis/efficiency.py`

处理 `QuestionEfficiencyObservation` 时，若 question record 已存在则 merge 保留已有计数器；不存在时保持原 0 初始化行为。

```python
# 修复前：直接覆盖
question_records[(obs.conversation_id, obs.question_id)] = {
    "llm_call_count": 0,  # 被重置
    ...
}

# 修复后：合并已有计数器
key = (observation.conversation_id, observation.question_id)
existing = question_records.get(key)
question_records[key] = {
    "llm_call_count": 0 if existing is None else existing["llm_call_count"],
    ...
}
```

**验证**: 对 A-Mem LongMemEval smoke 数据重新聚合：
- `llm_call_count`: 0 → 2
- `llm_input_tokens`: 0 → 9650 (9581 + 69)
- `llm_output_tokens`: 0 → 133 (120 + 13)

### A-Mem smoke summary 脚本重新生成

无需重跑实验。用现有 `efficiency_observations.prediction.jsonl` 重新执行 `build_efficiency_report_payloads()` 即可。已对 `outputs/amem-longmemeval-s-smoke-1c20r-20260622-s-cleaned/summaries/` 下三个 efficiency JSON 原子重写。

---

## 2. --max-new-conversations 1 进度条显示 0/500 — 根因与修复

### 根因

`src/memory_benchmark/runners/prediction.py:395-396`

`run_predictions()` 在构建 work plan 后，用全数据集大小初始化进度条 total：
- `progress.start_conversations(len(selected_conversations))` — 500
- `progress.start_questions(len(question_order))` — 500

`_run_isolated_worker_pipeline()` 中进度更新也使用：
- `total=work_plan.dataset_conversation_count` — 500
- `total=len(question_order)` — 500

`_build_prediction_work_plan()` 本身正确地限制了 `max_new_conversations`，只生成 1 个 work item。但进度显示完全忽略了预算限制。

### 修复

**文件**: `src/memory_benchmark/runners/prediction.py`

1. `run_predictions()` (line ~395): work plan 构建后计算实际工作量
   ```python
   _conversation_progress_total = len(work_plan.ingested_conversation_ids) + len(work_plan.items)
   _question_progress_total = len(work_plan.completed_question_ids) + sum(len(item.pending_questions) for item in work_plan.items)
   ```
   进度条初始化使用这两个值而非全数据集大小。

2. `_run_isolated_worker_pipeline()` (line ~1107): 函数内计算 `_conv_progress_total` 和 `_question_progress_total`，所有 `progress.update_conversations()/update_questions()` 的 `total` 参数改用这两个值。

3. `_answer_pending_questions()` (line ~1822): 非 isolated 路径同样修正，从 `pending_by_conversation` 计算实际 question 总数。

4. Non-isolated "Completed" 阶段 (line ~470): 同样改用 work-plan-aware totals。

### 二次校验：--max-new-conversations 1 真正只跑 1 conversation

参数链路完整追踪：
```
CLI --max-new-conversations 1
  → PredictCommand.max_new_conversations=1 (cli/main.py:340)
  → PredictionRunPolicy.max_new_conversations=1 (cli/run_prediction.py:360)
  → _build_prediction_work_plan() (prediction.py:674)
```

work plan 生成逻辑：
- 遍历全部 500 conversation，`unfinished_seen` 从 0 开始
- 第 1 个 conversation: `unfinished_seen=0 < 1`, 加入 work plan, `unfinished_seen=1`
- 第 2 个 conversation: `unfinished_seen=1 >= 1`, `budget_exhausted=True`, skip
- 第 3-500: 同样 skip
- 结果: work_plan.items 只有 1 项

Resume 同样正确：
- 第 1 个 conversation 已完成 (ingested + answered), skip
- 第 2 个 conversation: `unfinished_seen=0 < 1`, 加入, `unfinished_seen=1`
- 结果: 每次 resume --max-new-conversations 1 精确推进 1 个新 conversation

**结论**: 上次实验是显示问题，不会倾家荡产。

---

## 3. 四 method embedding 观测差异诊断

### 现象

- A-Mem: `embedding_call_count=0, embedding_input_tokens=0`
- LightMem: `embedding_call_count=0, embedding_input_tokens=0`
- MemoryOS: `embedding_call_count=2, embedding_input_tokens=278`
- Mem0: 有 embedding 记录（API embedding）

### 根因

所有 method 检索阶段都使用本地 embedding（`all-MiniLM-L6-v2`）：
- A-Mem: `SimpleEmbeddingRetriever.search()` 内 `self.model.encode([query])` (SentenceTransformer)
- LightMem: `text_embedder.embed(question.text)` (HuggingFace)
- MemoryOS: `_get_embedding()` 内 `SentenceTransformer.encode()` (SentenceTransformer)

MemoryOS 的 adapter 在 `_get_embedding()` 中**主动插桩**了 `_record_embedding_call()`（`memoryos_adapter.py:1209-1218`），每次 cache miss 记录本地 inference 为 observation。A-Mem 和 LightMem 没有这个 instrumentation。

三个 method 的 embedding 实际上都是本地 `all-MiniLM-L6-v2`，无 API 费用。只是 instrumentation 不一致。

**决策**: 用户暂不要求给 A-Mem/LightMem 补本地 embedding 记录。

---

## 4. 四 method × LongMemEval-S 1-conversation cost pilot 命令

### 命令

```bash
# Mem0
uv run memory-benchmark predict --root . --method mem0 --benchmark longmemeval \
  --variant s_cleaned --profile official-full \
  --run-id mem0-longmemeval-s-1conv-costpilot-20260622 \
  --confirm-api --confirm-full --max-new-conversations 1

# A-Mem
uv run memory-benchmark predict --root . --method amem --benchmark longmemeval \
  --variant s_cleaned --profile official-full \
  --run-id amem-longmemeval-s-1conv-costpilot-20260622 \
  --confirm-api --confirm-full --max-new-conversations 1

# LightMem
uv run memory-benchmark predict --root . --method lightmem --benchmark longmemeval \
  --variant s_cleaned --profile official-full \
  --run-id lightmem-longmemeval-s-1conv-costpilot-20260622 \
  --confirm-api --confirm-full --max-new-conversations 1

# MemoryOS
uv run memory-benchmark predict --root . --method memoryos --benchmark longmemeval \
  --variant s_cleaned --profile official-full \
  --run-id memoryos-longmemeval-s-1conv-costpilot-20260622 \
  --confirm-api --confirm-full --max-new-conversations 1
```

进度条将显示 0/1 conversation, 0/1 question（已修复）。

### Resume 命令（每个 method 单独 resume）

```bash
uv run memory-benchmark predict --root . --method mem0 --benchmark longmemeval \
  --variant s_cleaned --profile official-full \
  --run-id mem0-longmemeval-s-1conv-costpilot-20260622 \
  --confirm-api --confirm-full --resume --max-new-conversations N
```

---

## 跑了哪些测试

```
uv run pytest tests/test_efficiency_analysis.py -q       3 passed
uv run pytest tests/test_prediction_runner.py -q          56 passed
uv run pytest tests/test_prediction_efficiency_observations.py -q  12 passed
uv run pytest tests/test_main_cli.py tests/test_cost_calibration_smoke.py tests/test_calibration_progress_monitor.py tests/test_prediction_cli.py -q  79 passed
uv run pytest tests/test_documentation_standards.py -q    5 passed
uv run python -m compileall -q src/memory_benchmark tests  exit 0
git diff --check                                            exit 0
```

**总计**: 155 passed, compileall OK, git diff OK

## 已知风险 / 未解决问题

- `--max-new-conversations 1` 进度条修复未执行真实 API 验证（只有离线测试）
- `test_prediction_runner.py` 中 `max_new_conversations` 测试未覆盖进度条 total 正确性，建议补
- Non-isolated path `_ingest_pending_conversations` 的 progress total 未同时修改（仅 `max_workers=1` 场景用）
- A-Mem/LightMem 本地 embedding 调用未插桩（MemoryOS 有），instrumentation 不一致
- A-Mem full-costpilot run（旧目录 `amem-longmemeval-s-full-costpilot-20260622-s-cleaned`）无 efficiency observation，无法 retro 更新 summary
