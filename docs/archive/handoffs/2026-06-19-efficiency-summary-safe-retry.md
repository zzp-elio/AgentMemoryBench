# 2026-06-19 交接：Efficiency Summary 与 Failed Conversation Safe Retry

## 背景

用户要求在额度即将耗尽前交接。本轮 Codex 接在 OpenCode 大量改动之后继续推进，重点处理：

1. 跑实验后能直接看到 per-conversation / per-question 的 token、latency、API call 汇总。
2. A-Mem / LightMem 尽量使用真实 API response usage，而不是只靠 tokenizer estimate。
3. 失败 conversation 默认不在 resume 时反复重跑，避免失败后空烧 API。

本轮没有执行真实 API，只做离线/fake focused 验证。

## 本轮完成

### 1. Prediction efficiency summary artifacts

新增从 raw observation 派生的人类可读 summary：

- `outputs/<run_id>/summaries/efficiency_overall.prediction.json`
- `outputs/<run_id>/summaries/efficiency_by_conversation.prediction.json`
- `outputs/<run_id>/summaries/efficiency_by_question.prediction.json`

实现位置：

- `src/memory_benchmark/analysis/efficiency.py`
- `src/memory_benchmark/storage/experiment_paths.py`
- `src/memory_benchmark/runners/prediction.py`

注意：`artifacts/efficiency_observations.jsonl` 仍是事实来源，summary 只做离线聚合视图。

### 2. A-Mem / LightMem memory-build API usage observer

A-Mem:

- 在 official runtime 的 `llm_controller.llm.get_completion()` 外围加透明 observer。
- 只在 collector 当前处于 conversation scope 时记录 `memory_build` LLM observation。
- 不改变 A-Mem 核心算法、prompt、返回值和状态。

LightMem:

- 在 backend `manager.generate_response()` 外围加透明 observer。
- 读取返回 tuple 中的 `usage_info`，可见时记录 `measurement_source=api_usage`。
- usage 不可见时回退 tokenizer estimate，并保留 measurement source。

实现位置：

- `src/memory_benchmark/methods/amem_adapter.py`
- `src/memory_benchmark/methods/lightmem_adapter.py`
- `src/memory_benchmark/observability/efficiency/collector.py`

### 3. Failed conversation quarantine

新增策略：

- `PredictionRunPolicy.retry_failed_conversations: bool = False`
- CLI 新增 `--retry-failed`
- 默认 resume 跳过 `checkpoints/conversation_status.json` 中 `status=failed` 的 conversation。
- 只有显式 `--retry-failed` 才把 failed conversation 重新纳入 work plan。
- isolated worker 中某个 conversation 失败时，会写入具体 `conversation_id` 的 failed checkpoint。
- 对外仍抛原始异常类型，不隐藏真实错误。

实现位置：

- `src/memory_benchmark/runners/prediction.py`
- `src/memory_benchmark/cli/main.py`
- `src/memory_benchmark/cli/commands.py`
- `src/memory_benchmark/cli/run_prediction.py`

已处理 turn-level ready checkpoint 边界：有可恢复 turn checkpoint 时不会被 failed quarantine 误跳过。

## 验证结果

已运行：

```bash
uv run pytest tests/test_prediction_runner.py::test_prediction_work_plan_quarantines_failed_conversations_by_default tests/test_main_cli.py::test_prediction_help_describes_retry_failed tests/test_main_cli.py::test_main_maps_predict_arguments_to_command -q
```

结果：`3 passed`

```bash
uv run pytest tests/test_prediction_runner.py::test_isolated_worker_failure_stops_remaining_conversation_work -q
```

结果：`1 passed`

```bash
uv run pytest tests/test_prediction_runner.py tests/test_main_cli.py -q
```

结果：`74 passed`

```bash
uv run pytest tests/test_efficiency_analysis.py tests/test_prediction_efficiency_observations.py tests/test_amem_adapter.py tests/test_lightmem_adapter.py tests/test_prediction_runner.py tests/test_main_cli.py tests/test_cost_calibration_smoke.py -q
```

结果：`133 passed, 2 warnings`

warning 均来自第三方代码：

- A-Mem `ast.Str` deprecation。
- LightMem pydantic class config deprecation。

未运行：

- 未运行真实 API smoke。
- 未运行完整 `uv run pytest -q`。
- 未运行 `compileall` / `git diff --check`。

## 文档同步

已更新：

- `AGENTS.md`
- `README.md`
- `docs/current-roadmap.md`
- `docs/task-ledger.md`
- `docs/superpowers/plans/2026-06-19-efficiency-summary-and-safe-retry.md`

新增：

- 本文件。

## 当前工作树注意

当前 git worktree 仍包含 OpenCode 和 Codex 之前的大量改动，不是本轮全部产生。低额度下没有执行清理、commit 或 push。

重要：`opencode/opencode_result.md` 当前有大幅变动，`opencode/opencode_task.md` 显示删除；恢复后先检查这些是否为用户/OpenCode 预期，不要贸然提交。

## 下次恢复第一步

1. 先读 `AGENTS.md`、`docs/current-roadmap.md`、`docs/task-ledger.md` 和本文件。
2. 运行轻量验证：

   ```bash
   uv run pytest tests/test_efficiency_analysis.py tests/test_prediction_efficiency_observations.py tests/test_amem_adapter.py tests/test_lightmem_adapter.py tests/test_prediction_runner.py tests/test_main_cli.py tests/test_cost_calibration_smoke.py -q
   uv run python -m compileall -q src/memory_benchmark tests
   git diff --check
   ```

3. 如果用户允许，可做一个极小真实 API smoke 验证 A-Mem / LightMem 的真实 usage 字段是否按 `api_usage` 记录。
4. 继续处理未关闭任务：
   - Rich / stdout / warning 终端污染。
   - isolated prediction 进度长时间不动。
   - Mem0 新 run_id 极小 smoke，验证 failed quarantine 和 isolated cancellation。
   - MemoryOS LongMemEval adapter 方案。
