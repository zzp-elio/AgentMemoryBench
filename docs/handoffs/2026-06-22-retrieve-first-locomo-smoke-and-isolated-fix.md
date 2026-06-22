# 2026-06-22 LoCoMo Retrieve-First Smoke 复核与 Isolated Worker 修复交接

## 背景

用户在额度恢复后运行了四个 LoCoMo retrieve-first 极小真实 API smoke，并要求检查
`outputs/`。本轮没有 OpenCode 新改动。

预期 run_id：

- `retrieve-first-locomo-mem0-smoke-2c20t-20260622`
- `retrieve-first-locomo-memoryos-smoke-2c20t-20260622`
- `retrieve-first-locomo-amem-smoke-2c20t-20260622`
- `retrieve-first-locomo-lightmem-smoke-2c20t-20260622`

四个 run 都使用 LoCoMo smoke、2 conversations、20 turns、每 conversation 1 question、
2 workers。

## 输出复核结果

四个 run 的 `summaries/summary.json` 均显示：

- `total_conversations = 2`
- `completed_conversations = 2`
- `total_questions = 2`
- `completed_questions = 2`

四个 run 的 `logs/events.jsonl` event 序列均为：

```text
run_started
conversation_completed_isolated
conversation_completed_isolated
run_completed
```

按结构化 event 名称检查，没有 `failed` / `error` / `exception` event。
`logs/run.log` 中也没有 `ERROR`、`WARNING`、`Traceback`、`SSL`、`timeout` 或 `Retry`
相关文本。

四个 run 均有：

- `artifacts/method_predictions.jsonl`
- `artifacts/efficiency_observations.prediction.jsonl`
- `summaries/efficiency_overall.prediction.json`
- `summaries/efficiency_by_conversation.prediction.json`
- `summaries/efficiency_by_question.prediction.json`

raw observation 行数：

| Method | Observation rows |
| --- | ---: |
| A-Mem | 124 |
| LightMem | 8 |
| Mem0 | 152 |
| MemoryOS | 96 |

efficiency summary 关键字段均存在，包括：

- `memory_build_latency_ms`
- `retrieval_latency_ms`
- `answer_generation_latency_ms`
- `injected_memory_context_tokens`
- `retrieval_supported_count = 2`
- `retrieval_unsupported_count = 0`
- answer / memory_build / retrieval LLM token 聚合
- Mem0 / MemoryOS 的 embedding token/latency 聚合

示例聚合：

- A-Mem：answer LLM 2 calls，memory-build LLM 116 calls，retrieval query LLM 2 calls。
- LightMem：answer LLM 2 calls，memory-build LLM 2 calls。
- Mem0：answer LLM 2 calls，memory-build LLM 40 calls，memory-build embedding 101 calls，
  retrieval embedding 5 calls。
- MemoryOS：answer LLM 2 calls，memory-build LLM 47 calls，retrieval LLM 2 calls，
  memory-build embedding 33 calls，retrieval embedding 8 calls。

## 发现的关键问题

四个真实 smoke 都没有生成：

```text
artifacts/answer_prompts.prediction.jsonl
```

进一步检查代码后确认根因不是产物改名，而是 isolated worker 路径仍在调用 legacy
`system.get_answer(question)`，没有走：

```text
BaseMemoryProvider.retrieve(question)
FrameworkAnswerReader.generate_answer(...)
```

因此，这四个 run 可以证明：

- 四个 method 的 LoCoMo 小规模真实 API 运行可完成。
- prediction artifact 与 efficiency observation 可写出。
- conversation-level isolated worker 没有失败。

但不能作为严格的 retrieve-first 链路验证证据，因为 `--smoke-max-workers 2` 进入
isolated worker path，而该 path 在本轮修复前仍走 legacy `get_answer()`。

## 已完成修复

文件：

- `src/memory_benchmark/runners/prediction.py`
- `tests/test_prediction_runner.py`

修复内容：

- isolated worker pipeline 现在接收 `answer_reader`。
- isolated worker 会读取并合并已有 `answer_prompts.prediction.jsonl`，支持 answer
  prompt 已落盘、answer pending 的 resume。
- isolated worker 在遇到 `BaseMemoryProvider` 时走 retrieve-first：

```text
retrieve(question) -> FrameworkAnswerReader -> prediction
```

- isolated worker 成功 batch 会把 `retrievals` 合并并持久化到
  `answer_prompts.prediction.jsonl`。
- isolated worker 失败 batch 新增 `retrievals` 字段，answer 失败时也可以保存已生成的
  prompt record。
- 新增 `_add_public_conversation_coarse()`，让 isolated conversation-level 写入同时兼容：
  - `BaseMemoryProvider.add(conversation)`
  - legacy `BaseMemorySystem.add([conversation])`
- legacy isolated fake system 的 `add()` 返回 `None` 仍保持兼容；provider path 仍要求
  `AddResult` 中包含当前 `conversation_id`。

新增测试：

```text
tests/test_prediction_runner.py::test_isolated_retrieve_first_worker_persists_answer_prompt_artifact
```

该测试先失败，失败现象为 isolated provider path 无法写出 prediction / answer prompt；
修复后通过，并断言 `answer_prompts.prediction.jsonl` 包含 `prompt_messages`。

## 验证证据

已运行红测：

```bash
uv run pytest tests/test_prediction_runner.py::test_isolated_retrieve_first_worker_persists_answer_prompt_artifact -q
```

修复前失败，修复后：

```text
1 passed
```

已运行 focused 回归：

```bash
uv run pytest tests/test_prediction_runner.py tests/test_prediction_efficiency_observations.py tests/test_framework_answer_reader.py -q
```

结果：

```text
80 passed
```

已运行 adapter / registered focused 回归：

```bash
uv run pytest tests/test_mem0_adapter.py tests/test_memoryos_adapter.py tests/test_amem_adapter.py tests/test_lightmem_adapter.py tests/test_prediction_cli.py tests/test_method_registry.py tests/test_cost_calibration_smoke.py -q
```

结果：

```text
241 passed, 2 warnings, 2 subtests passed
```

两个 warning 均来自第三方代码：

- A-Mem `ast.Str` deprecation。
- LightMem pydantic class config deprecation。

## 当前结论

- 用户刚跑的四个 `retrieve-first-locomo-*-smoke-2c20t-20260622` run 产物有效，但只能作为
  “legacy isolated answer path 完成 + efficiency observation 可写出”的证据。
- 严格 retrieve-first isolated path 已在本轮代码中修复，但尚未重新运行真实 API smoke。
- 下一次真实 retrieve-first smoke 必须重新跑，并确认：
  - `artifacts/answer_prompts.prediction.jsonl` 存在。
  - 每条 prompt record 含 `prompt_messages`。
  - `method_predictions.jsonl` 仍保持轻量，不写入完整 prompt。
  - `efficiency_observations.prediction.jsonl` 仍有 memory_build / retrieval / answer 观测。

## 下一步建议

1. 运行文档规范、`compileall` 和 `git diff --check`。
2. 如时间允许，运行更宽离线回归。
3. 用户确认后，用新的 run_id 重跑四个 method 的 LoCoMo retrieve-first 极小 smoke。
   建议 run_id 带 `strict` 或 `isolated-fixed`，避免和本轮已完成但非严格 retrieve-first 的
   smoke 混淆。
4. 重跑成功后再把 `docs/task-ledger.md` 中 “Retrieve-first 真实 API smoke” 从 open
   改为 closed。
