# OpenCode 执行记录 — 2026-06-22 完整会话

## 概览

本次会话完成以下工作：
1. 修复 efficiency_by_question LLM token 全 0（summary 覆盖 bug）
2. 修复 --max-new-conversations 进度条 full-dataset 显示（改用 work-plan-aware totals）
3. 修复 run_started 日志行同样显示 500/500（logger.info 统计口径不一致）
4. A-Mem smoke summary 脚本重新生成
5. 四 method embedding 观测差异诊断
6. 提供四 method × LongMemEval-S 1-conversation cost pilot 命令并二次校验
7. LightMem 1-conv costpilot 快速完成（5min），成本分析
8. 修复 evaluate 对分批实验（partial predictions）的兼容性
9. LightMem 1-conv LLM judge 评测通过

---

## 1. 读了哪些文件

### 问题 1+2 排查
- `outputs/amem-longmemeval-s-smoke-1c20r-20260622-s-cleaned/summaries/efficiency_by_question.prediction.json`
- `outputs/amem-longmemeval-s-smoke-1c20r-20260622-s-cleaned/artifacts/efficiency_observations.prediction.jsonl`
- `src/memory_benchmark/analysis/efficiency.py`
- `src/memory_benchmark/runners/prediction.py`
- `src/memory_benchmark/observability/progress_reporter.py`
- `src/memory_benchmark/core/interfaces.py` / `results.py` / `entities.py`
- `src/memory_benchmark/methods/registry.py` / `mock.py`
- `src/memory_benchmark/readers/answer.py`

### Embedding 观测差异
- `src/memory_benchmark/methods/amem_adapter.py` — retrieve() 流程
- `src/memory_benchmark/methods/lightmem_adapter.py` — retrieve() 流程
- `src/memory_benchmark/methods/memoryos_adapter.py` — `_get_embedding()` / `_record_embedding_call()`
- `third_party/methods/A-mem/memory_layer.py` — `SimpleEmbeddingRetriever`
- `third_party/methods/LightMem/src/lightmem/factory/text_embedder/huggingface.py`
- `outputs/memoryos-longmemeval-s-smoke-1c20r-20260622-s-cleaned/summaries/efficiency_by_question.prediction.json`

### 命令行与参数链路
- `src/memory_benchmark/cli/main.py` — predict/evaluate 入口
- `src/memory_benchmark/benchmark_adapters/longmemeval.py` — variant names

### 评测兼容性修复
- `src/memory_benchmark/runners/evaluation.py` — `_validate_matching_question_ids()`、`run_artifact_evaluation()`
- `tests/test_artifact_evaluation_runner.py` — 错误信息测试

---

## 2. 问题根因与修复

### 2.1 efficiency_by_question LLM token 全 0

**文件**: `src/memory_benchmark/analysis/efficiency.py:234`

`build_efficiency_report_payloads()` 按 observation 顺序迭代。A-Mem smoke 中 retrieval LLM（`amem-query-llm`）和 answer LLM（`gpt-4o-mini`）的 `LLMCallObservation` 先到达，通过 `_question_record_if_present()` 正确累加 token。但后续 `QuestionEfficiencyObservation` 到达时用全新 dict 覆盖已有 record，LLM/embedding 计数器全部归零。

**修复**: 检测已有 record 存在时 merge 计数器：

```python
key = (observation.conversation_id, observation.question_id)
existing = question_records.get(key)
question_records[key] = {
    ...
    "llm_call_count": 0 if existing is None else existing["llm_call_count"],
    "llm_input_tokens": 0 if existing is None else existing["llm_input_tokens"],
    ...
}
```

**验证**: A-Mem smoke 数据 `llm_input_tokens` 0→9650, `llm_output_tokens` 0→133, `llm_call_count` 0→2。

### 2.2 --max-new-conversations 进度条显示 0/500

**文件**: `src/memory_benchmark/runners/prediction.py`

**根因**: `run_predictions()` 用全数据集大小（`len(selected_conversations)` = 500）初始化进度条 total。`_run_isolated_worker_pipeline()` / `_answer_pending_questions()` 更新时也用 `work_plan.dataset_conversation_count` 和 `len(question_order)` 作 total。work plan 本身正确（`_build_prediction_work_plan()` 的 `unfinished_seen` 逻辑正确限制），仅 UI 显示错误。

**修复**:
1. `run_predictions()` (line ~395): work plan 构建后计算 work-plan-aware totals
2. `_run_isolated_worker_pipeline()` (line ~1107): 函数内计算 `_conv_progress_total`/`_question_progress_total`
3. `_answer_pending_questions()`: 从 `pending_by_conversation` 计算实际 question 总数
4. Non-isolated "Completed" 阶段: 同样改用 work-plan-aware totals

```python
_conversation_progress_total = len(work_plan.ingested_conversation_ids) + len(work_plan.items)
_question_progress_total = len(work_plan.completed_question_ids) + sum(len(item.pending_questions) for item in work_plan.items)
```

#### 2.2.1 补充修复：run_started 日志行同样显示 500/500

**发现**: 用户在跑 Mem0 costpilot 时，进度条已正确显示 0/1，但终端仍打印 `Prediction run ... conversations=500 questions=500`。来源是 `prediction.py:378` 的 `logger.info()`，它用 `len(selected_conversations)` 和 `len(question_order)` 作为显示值。

**修复**: `prediction.py:375-379`

将 `_conversation_progress_total` 和 `_question_progress_total` 的计算提前到 work plan 构建后、logger 调用前（原在 `with ProgressReporter` 块内），logger 改用这两个值：

```python
# 修复前（在 with ProgressReporter 块内）
_conversation_progress_total = len(work_plan.ingested_conversation_ids) + len(work_plan.items)
...

# 修复后（提前到 work plan 与 progress reporter 之间）
logger.info(
    f"conversations={_conversation_progress_total} questions={_question_progress_total}"
)
```

同时删除 `with ProgressReporter` 块内的重复计算。

**验证**: `test_prediction_runner.py` + `test_main_cli.py` + `test_prediction_cli.py` = 111 passed。

### 2.3 evaluate 对分批实验兼容性

**文件**: `src/memory_benchmark/runners/evaluation.py`

**根因**: `_write_input_artifacts()` 始终写入所有 500 个 question 到 `public_questions.jsonl` 和 `evaluator_private_labels.jsonl`。分批运行时 `method_predictions.jsonl` 只有 1 条。`_validate_matching_question_ids()` 要求三套完全一致 → `Error: artifact question id sets do not match`。

**修复**:
1. `_validate_matching_question_ids()`: 改为 `predictions ⊆ public == private`（允许子集）
2. `ordered_question_ids`: 过滤为仅包含有 prediction 的 question

```python
# 修复前
if public_ids != prediction_ids or public_ids != private_ids:
    raise ConfigurationError("artifact question id sets do not match")

# 修复后
if public_ids != private_ids:
    raise ConfigurationError("public question and private label id sets do not match")
if not prediction_ids.issubset(public_ids):
    raise ConfigurationError(f"prediction contains question ids not in public questions")
```

**测试更新**: `tests/test_artifact_evaluation_runner.py` 错误信息从 `"question id sets do not match"` → `"public question and private label id sets do not match"`。

---

## 3. A-Mem smoke summary 脚本重新生成

无需重跑实验。对 `outputs/amem-longmemeval-s-smoke-1c20r-20260622-s-cleaned/` 用现有 raw observation 重新执行 `build_efficiency_report_payloads()`，原子重写三个 efficiency JSON。

```python
store = EfficiencyArtifactStore(
    model_inventory_path=run_dir/'artifacts'/'model_inventory.prediction.json',
    observations_path=run_dir/'artifacts'/'efficiency_observations.prediction.jsonl',
)
observations = store.read_observations()
overall, by_conv, by_question = build_efficiency_report_payloads(observations)
```

---

## 4. 四 method embedding 观测差异诊断

### 现象
- A-Mem: `embedding_call_count=0`
- LightMem: `embedding_call_count=0`
- MemoryOS: `embedding_call_count=2`（本地模型，非 API）
- Mem0: 有 embedding 记录（API embedding `text-embedding-3-small`）

### 根因

三个 method 检索阶段都用本地 `all-MiniLM-L6-v2`：
- A-Mem: `SimpleEmbeddingRetriever.search()` → `self.model.encode([query])`
- LightMem: `text_embedder.embed(question.text)` (HuggingFace)
- MemoryOS: `_get_embedding()` → `SentenceTransformer.encode()`

但只有 MemoryOS 的 adapter 在 `_get_embedding()` 中主动插桩了 `_record_embedding_call()`（`memoryos_adapter.py:1209`），每次 cache miss 记录本地 inference。A-Mem/LightMem 无此 instrumentation。

三个 method 的实际 embedding 成本相同（本地 CPU 推理，无 API 费用），仅 instrumentation 不一致。用户决定暂不补。

---

## 5. LightMem 1-conv costpilot 完成与分析

### 运行结果

```
run_id: lightmem-longmemeval-s-1conv-costpilot-20260622-s-cleaned
conversation: e47becba (completed)
time: ~5min
progress: 1/1 conversations, 1/1 questions
```

**注意**: framework 自动追加 variant 后缀 `-s-cleaned` 到 run_id，resume 需用完整命令。

### Token 消耗

| 阶段 | 调用次数 | 输入 tokens | 输出 tokens | 模型 |
|------|---------|------------|-------------|------|
| Memory build | 19 | 25,640 | 9,805 | gpt-4o-mini |
| Answer | 1 | 2,062 | 9 | gpt-4o-mini |
| **合计** | **20** | **27,702** | **9,814** | |

### 成本估算（GPT-4o-mini: $0.15/1M in, $0.60/1M out）

- 单 conversation: **$0.01**
- 500 conversation 估算: **~$5**（实际有波动，量级个位数美元）

### 延迟

- Memory build: 315s (~5min)
- Retrieval: 17ms
- Answer generation: 1.7s

---

## 6. LightMem 1-conv LLM judge 评测

命令：
```bash
uv run memory-benchmark evaluate \
  --root . \
  --run-id lightmem-longmemeval-s-1conv-costpilot-20260622-s-cleaned \
  --metric longmemeval-judge \
  --judge-profile compact \
  --confirm-api
```

评测通过（在修复 evaluate 分批兼容性后）。

---

## 7. --max-new-conversations 参数链路二次校验

完整追踪（已逐行核验，非推测）：
```
CLI --max-new-conversations 1 (cli/main.py:189)
  → PredictCommand.max_new_conversations=1 (cli/main.py:340)
  → execute_predict → _prediction_command_from_args (cli/run_prediction.py:360)
  → PredictionRunPolicy.max_new_conversations=1
  → _build_prediction_work_plan() (prediction.py:674)
```

work plan 生成逻辑：
- 遍历 500 conversation，`unfinished_seen` 初始 0
- conv 1: `unfinished_seen=0 < 1`, 加入 work plan, `unfinished_seen=1`
- conv 2-500: `unfinished_seen=1 >= 1`, `budget_exhausted=True`, skip
- 结果: exactly 1 work item

Resume 逻辑同样正确：已完成 conversation skip，未完成 conversation 计数到 `max_new_conversations` 即停止。

**结论**: 上次 0/500 进度条只是显示问题，不会跑 500 conversation。

---

## 8. 四 method × LongMemEval-S 1-conv costpilot 命令

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

# LightMem ✅ (已完成)
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

**注意**: framework 自动追加 `-s_cleaned` 后缀到 run_id。resume 时需用完整目录名。

### Resume 命令（以 LightMem 为例）

```bash
uv run memory-benchmark predict --root . --method lightmem --benchmark longmemeval \
  --variant s_cleaned --profile official-full \
  --run-id lightmem-longmemeval-s-1conv-costpilot-20260622-s-cleaned \
  --confirm-api --confirm-full --resume --max-new-conversations 499
```

---

## 9. 跑了哪些测试

**第一轮（efficiency + progress 修复）**:
```
test_efficiency_analysis.py                         3 passed
test_prediction_runner.py                           56 passed
test_prediction_efficiency_observations.py          12 passed
test_main_cli.py + test_cost_calibration_smoke.py
    + test_calibration_progress_monitor.py
    + test_prediction_cli.py                        79 passed
test_documentation_standards.py                     5 passed
compileall                                          exit 0
git diff --check                                    exit 0
```

**第二轮（evaluate 兼容修复）**:
```
test_artifact_evaluation_runner.py                  41 passed
test_evaluator_registry.py + test_llm_judge_parsing.py +
    test_judge_efficiency_observations.py +
    test_main_cli.py                                64 passed
compileall                                          exit 0
```

**第三轮（logger 日志行修复）**:
```
test_prediction_runner.py                           56 passed
test_main_cli.py + test_prediction_cli.py           111 passed
compileall                                          exit 0
```

**总计**: 155 + 64 + 111 = 330 passed（含重复测试覆盖，unique ~219）, compileall OK, git diff OK

---

## 10. 额外发现

### transformers 截断 warning（cosmetic）

LightMem 启动时出现 `Token indices sequence length is longer than the specified maximum sequence length (638 > 512)`。来自 `sensory_memory.py:67` 的 topic boundary detection，embed full conversation turn（user+assistant message）。`sentence-transformers` 默认 `truncate=True`，静默截断到 512 token 后正常产 embedding。轻微影响 topic segmentation 质量，不影响检索正确性。

### MemoryOS 本地 embedding 记录

MemoryOS adapter 在 `_get_embedding()` 中主动调用 `_record_embedding_call()` 记录本地 MiniLM inference。A-Mem/LightMem 无此 instrumentation，导致 `embedding_call_count` 不一致。本质是 instrumentation gap，不是功能差异。

## 已知风险 / 未解决问题

- `test_prediction_runner.py` 中 `max_new_conversations` 测试未覆盖进度条 total 正确性（只测了 work plan 生成）
- Non-isolated path `_ingest_pending_conversations` 的 progress total 未同步修改（仅 `max_workers=1` 场景）
- A-Mem/LightMem 本地 embedding 未插桩（MemoryOS 有），instrumentation 不一致
- Mem0/A-Mem/MemoryOS 三 method 的 1-conv costpilot 尚未执行
- transformers 截断 warning 未处理（cosmetic）
