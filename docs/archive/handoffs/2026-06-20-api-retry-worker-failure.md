# 2026-06-20 交接：API 兜底与 Worker 失败语义

## 本轮目标

基于用户确认的设计，优先修复两类 P0 问题：

1. Mem0 official-full v3 暴露的 embedding API SSL 断连缺 retry/timeout 兜底。
2. isolated worker 中一个 conversation 失败后旧逻辑会停止整个 run。

设计文档：

- `docs/superpowers/specs/2026-06-20-api-retry-worker-failure-design.md`

实施计划：

- `docs/superpowers/plans/2026-06-20-api-retry-worker-failure.md`

## 已完成

### 1. Isolated worker 局部失败继续运行

修改文件：

- `src/memory_benchmark/runners/prediction.py`
- `tests/test_prediction_runner.py`

当前行为：

- `_isolated_worker()` 对每个 conversation 单独捕获异常。
- 当前 conversation 失败时返回 `_ConversationFailureBatch`，不再抛出
  `_ConversationWorkItemError` 终止整个 future。
- coordinator 写入：
  - `conversation_status.json`
  - `conversation_failed_isolated` event
  - 完整 traceback
  - `ingested` 标记
- 当前 worker 会继续处理后续 conversation。
- 其他 worker 不受该局部失败影响。
- factory 构造失败等 worker/global 异常仍走 fail-fast。

### 2. `--retry-failed` 与 `ingested=true`

如果 failed conversation 的 checkpoint 中 `ingested=true`，后续显式
`--retry-failed` 时 work plan 会把它视为已经完成 memory add，只继续缺失问题，避免重复
add 污染 namespace。

`--retry-failed` 仍只影响 eligible selection，同一次 run 内每个 conversation 最多一个
work item，不会被其他 worker 接手反复重试。

### 3. 连续失败熔断

`PredictionRunPolicy` 新增：

```python
max_consecutive_failures: int | None = 3
```

单个 worker 连续失败达到阈值后，会停止该 worker 后续 conversation，并设置
`cancellation_event`，避免系统性配置/API 问题导致批量空烧。

### 4. Mem0 API timeout/retry

修改文件：

- `src/memory_benchmark/methods/mem0_adapter.py`
- `configs/methods/mem0.toml`
- `tests/test_mem0_adapter.py`

`Mem0Config` 新增：

```python
api_timeout_seconds: float = 60.0
api_max_retries: int = 8
```

adapter 在 vendored Mem0 backend 构造后，对以下 OpenAI SDK client 调
`with_options(timeout=..., max_retries=...)`：

- `memory.llm.client`
- `memory.embedding_model.client`

这只改变网络兜底参数，不修改第三方核心算法、prompt、retrieval 或状态写入逻辑。

## 验证

已运行：

```bash
uv run pytest tests/test_prediction_runner.py::test_isolated_worker_marks_failed_conversation_and_continues_work -q
uv run pytest tests/test_prediction_runner.py::test_isolated_worker_stops_after_consecutive_failure_threshold -q
uv run pytest tests/test_prediction_runner.py -q
uv run pytest tests/test_mem0_adapter.py -k "timeout or retries or retry_settings" -q
uv run pytest tests/test_mem0_adapter.py tests/test_config_profiles.py tests/test_method_registry.py -q
uv run pytest tests/test_prediction_runner.py tests/test_mem0_adapter.py tests/test_method_registry.py tests/test_config_profiles.py tests/test_main_cli.py -q
uv run pytest tests/test_cost_calibration_smoke.py tests/test_prediction_efficiency_observations.py -q
```

结果：

- `tests/test_prediction_runner.py`: `50 passed`
- Mem0/config/registry focused: `39 passed`
- main focused: `115 passed`
- calibration/efficiency focused: `23 passed`

未执行真实 API smoke。

## 剩余风险

- Mem0 retry/timeout 还需要极小真实 API smoke 验证，尤其是 ohmygpt/OpenAI-compatible
  embedding API 的实际重试行为。
- 其他 method 的内部 API/network 调用还没有逐个审计，`docs/task-ledger.md` 中仍保持
  框架级 API/network 兜底为 `partially_closed`。
- 当前熔断是 worker 内连续失败阈值，不是跨 worker 的全局失败计数器；后续如果需要更强
  的全局熔断，可以单独设计。
