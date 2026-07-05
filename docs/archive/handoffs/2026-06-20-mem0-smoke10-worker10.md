# 2026-06-20 Mem0 LoCoMo smoke10 worker10 交接

## 背景

用户要求把 smoke worker 覆盖上限从 2 放宽到至少 10，并运行：

```bash
uv run memory-benchmark predict \
  --root . \
  --method mem0 \
  --benchmark locomo \
  --profile smoke \
  --run-id mem0-locomo-smoke10c-10t-w10-20260620 \
  --confirm-api \
  --smoke-conversation-limit 10 \
  --smoke-turn-limit 10 \
  --smoke-max-workers 10 \
  --question-limit-per-conversation 1
```

本次运行目标是极小真实 API smoke，不是正式实验。

## 本轮代码状态

- `--smoke-max-workers` 上限已放宽到 10。
- 统一入口 `memory-benchmark predict/run` 和旧 Mem0 兼容入口都不再由 argparse 限死 `{1,2}`。
- 配置层强校验 `1 <= smoke_max_workers <= 10`。
- 已更新：
  - `src/memory_benchmark/cli/run_prediction.py`
  - `src/memory_benchmark/cli/main.py`
  - `tests/test_prediction_cli.py`
  - `tests/test_main_cli.py`
  - `docs/task-ledger.md`
  - `AGENTS.md`

已执行验证：

```bash
uv run pytest tests/test_prediction_cli.py::test_smoke_concurrency_override_is_bounded_and_does_not_change_full \
  tests/test_main_cli.py::test_main_maps_predict_arguments_to_command \
  tests/test_main_cli.py::test_main_maps_run_arguments_to_run_command \
  tests/test_documentation_standards.py -q
# 8 passed

uv run python -m compileall -q src/memory_benchmark tests
# exit 0

git diff --check
# exit 0
```

## 运行结果核对

输出目录：

```text
outputs/mem0-locomo-smoke10c-10t-w10-20260620/
```

关键文件均存在：

- `manifest.json`
- `config.redacted.json`
- `checkpoints/progress.json`
- `checkpoints/conversation_status.json`
- `checkpoints/question_status.jsonl`
- `artifacts/public_questions.jsonl`
- `artifacts/evaluator_private_labels.jsonl`
- `artifacts/method_predictions.jsonl`
- `artifacts/efficiency_observations.prediction.jsonl`
- `artifacts/model_inventory.prediction.json`
- `summaries/summary.json`
- `summaries/efficiency_overall.prediction.json`
- `summaries/efficiency_by_conversation.prediction.json`
- `summaries/efficiency_by_question.prediction.json`
- `logs/events.jsonl`
- `logs/run.log`
- `method_state/worker_0` 到 `method_state/worker_9`

`progress.json`：

```json
{
  "stage": "Completed",
  "conversation_completed": 10,
  "conversation_total": 10,
  "question_completed": 10,
  "question_total": 10
}
```

`summary.json`：

```json
{
  "run_id": "mem0-locomo-smoke10c-10t-w10-20260620",
  "dataset_name": "locomo",
  "total_conversations": 10,
  "completed_conversations": 10,
  "total_questions": 10,
  "completed_questions": 10
}
```

`conversation_status.json`：

- completed: 10
- failed: 0
- completed conversation ids:
  `conv-26`, `conv-30`, `conv-41`, `conv-42`, `conv-43`, `conv-44`, `conv-47`,
  `conv-48`, `conv-49`, `conv-50`

JSONL 行数：

- `public_questions.jsonl`: 10
- `evaluator_private_labels.jsonl`: 10
- `method_predictions.jsonl`: 10
- `question_status.jsonl`: 10
- `efficiency_observations.prediction.jsonl`: 48
- `logs/events.jsonl`: 12

events：

- `run_started`: 1
- `conversation_completed_isolated`: 10
- `run_completed`: 1
- 未发现真实失败事件；字符串扫描中的 `failed` 只来自 `skipped_failed_conversations` 字段名。

## Efficiency 核对结论

本次 run 已记录：

- answer LLM token：
  - call_count: 10
  - input_tokens: 22600
  - output_tokens: 3460
- retrieval embedding：
  - call_count: 28
  - input_tokens: 147
  - latency_ms total: 35925.610834
- retrieval latency：
  - count: 10
  - total: 36105.852332 ms
- answer generation latency：
  - count: 10
  - total: 64436.9975 ms
- injected memory context tokens：
  - count: 10
  - total: 5362

发现的缺口：

- `memory_build_latency_ms.count = 0`
- `efficiency_observations.prediction.jsonl` 只有：
  - `embedding_call`: 28
  - `llm_call`: 10
  - `question_efficiency`: 10
- 缺少 `conversation_efficiency` 或等价 memory build observation。

这说明 Mem0 isolated worker 在本次真实 API smoke 下没有把 add/build 阶段的
conversation-level efficiency observation 写入最终 artifact。之前任务总账里
“isolated worker add efficiency scope 已关闭”的结论需要重新打开或降级复核。

该缺口不影响本次 smoke 的功能结论，但会影响成本估算中的 memory build latency / build
tokens 完整性，下一步必须修。

## 当前结论

功能链路结论：

- Mem0 + LoCoMo smoke 在 10 conversation、每 conversation 最多 10 turn、10 worker
  条件下成功跑通。
- 10 个 worker 均创建独立 `method_state/worker_*`，符合 isolated worker 隔离预期。
- 本次 run 没有 failed conversation，resume 入口可从该 run_id 继续使用。

观测链路结论：

- answer/retrieval 阶段 observation 有产物。
- memory build 阶段 observation 缺失，需要作为 P0/P1 修复项继续追踪。

## 下一步建议

1. 修复 Mem0 isolated worker 的 memory build observation 缺失。
   - 复查 `_isolated_worker()` 中 `conversation_scope` 是否只包住了 add，但 observation
     bundle 没有从 worker 返回给协调层。
   - 复查 `EfficiencyCollector` 在 isolated worker 内的 flush/serialize 路径。
   - 增加真实结构对应的离线测试：isolated add 后必须出现 `conversation_efficiency`，
     且 `efficiency_by_conversation.prediction.json` 的
     `memory_build_total_latency_ms > 0`。
2. 若要继续放大 smoke worker 超过 10，需要重新评估：
   - API rate limit
   - 本机内存
   - Mem0/Qdrant 并发稳定性
   - ohmygpt/OpenAI-compatible embedding 断连概率
3. 当前不要把本次 smoke 的 memory build efficiency 当作完整成本估算依据。

## 恢复时优先读取

1. `AGENTS.md`
2. `docs/task-ledger.md`
3. 本文件
4. `outputs/mem0-locomo-smoke10c-10t-w10-20260620/checkpoints/progress.json`
5. `outputs/mem0-locomo-smoke10c-10t-w10-20260620/summaries/efficiency_overall.prediction.json`
