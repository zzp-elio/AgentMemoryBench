# 2026-06-19 Parallel Resume Run Control 交接

## 本轮目标

实现 conversation-QA prediction 的分批运行与 isolated worker resume 修复：

- `max_new_conversations` 作为“本次命令预算”，允许同一 `run_id` 用不同预算多次 `--resume`。
- normal path 与 isolated worker path 共用同一套 work plan，统一判断 completed conversation 和 pending question。
- isolated worker 支持 conversation-level resume 与 question-level resume。
- isolated worker 遇到 turn-level ingest checkpoint 时 fail closed，避免误重放 Mem0 LoCoMo 这类 turn-level 状态。
- CLI `predict` / `run` / `calibrate-smoke` 均可传递 `--max-new-conversations`。

## 关键实现

- `src/memory_benchmark/runners/prediction.py`
  - `PredictionRunPolicy.max_new_conversations`：校验为正整数或 `None`。
  - `_ConversationWorkItem` / `_PredictionWorkPlan`：把一次命令需要处理的 conversation 和 question 显式建模。
  - `_build_prediction_work_plan()`：从 `conversation_status.json` 与 `method_predictions.jsonl` 恢复已完成状态，预算只作用于未完成 conversation。
  - `_build_manifest()`：没有写入 `max_new_conversations`，因此它不参与 resume identity。
  - `_run_isolated_worker_pipeline()`：只调度 work plan 中的 pending work，向 worker factory 传递 `completed_conversations`，由协调层串行写 artifact。
  - `_isolated_worker()`：已完成 ingest 的 conversation 不再重复 `add()`，已完成 question 不再重复 `get_answer()`。
- `src/memory_benchmark/cli/main.py` / `src/memory_benchmark/cli/run_prediction.py`
  - `predict` 与 `run` 接入 `--max-new-conversations`。
- `src/memory_benchmark/runners/cost_calibration.py`
  - `calibrate-smoke` 接入同名预算，并继续要求 smoke 的 conversation limit 为 1。
- `tests/test_prediction_runner.py`
  - 覆盖预算裁剪、不同预算 resume、isolated worker 状态恢复、turn checkpoint fail closed。

## Fresh 验证

本轮未执行真实 API。

已运行：

```bash
uv run pytest tests/test_documentation_standards.py tests/test_main_cli.py tests/test_cost_calibration_smoke.py tests/test_prediction_runner.py tests/test_mem0_adapter.py tests/test_method_registry.py tests/test_config_profiles.py -q
```

结果：

```text
119 passed in 10.54s
```

已运行：

```bash
uv run python -m compileall -q src/memory_benchmark tests
git diff --check
```

结果：均 exit 0。

## 已确认的不变量

- `max_new_conversations` 不在 prediction manifest identity 中。
- 同一 `run_id` 可以先用 `max_new_conversations=2` 跑一批，再用 `max_new_conversations=1` 继续 resume。
- 已完成 conversation 不占后续命令预算。
- 已完成 question 不会在 isolated worker resume 中重复回答。
- 已完成 ingest 但未答完问题的 conversation，会作为 `completed_conversations` 传给 method factory 恢复状态。
- isolated worker 不支持 turn-level ingest checkpoint resume；检测到 checkpoint 会抛 `ConfigurationError`。

## 剩余限制

- 本轮只做离线 focused 验证；还没有跑真实 API smoke。
- MemoryOS / A-Mem / LightMem 的大规模 isolated 并行仍需要从小并发真实 smoke 开始验证。
- Rich 并行终端展示仍存在历史问题：多 child run 进度区可能被第三方 warning 打乱，elapsed 可能停住但后台任务仍运行。
- 框架级 stdout 捕获、prediction artifact 瘦身、按 category 聚合所有 answer-level metric 仍在 roadmap 待办中。

## 下一步建议

1. 如用户确认 API 余额、组合和 run_id，先做极小真实 smoke：
   - 每个目标组合 `max_new_conversations=1`
   - 每个 conversation 只答 1 个 question
   - 并发从 1 或 2 开始，不直接拉满。
2. 修 Rich 并行展示：禁用 child run progress，由 orchestrator 读取各 run 的 `checkpoints/progress.json` 统一展示。
3. 实现框架级 stdout/warning 捕获和 prediction artifact 瘦身。
4. 为 evaluator summary 建立通用 by-category 聚合契约。
