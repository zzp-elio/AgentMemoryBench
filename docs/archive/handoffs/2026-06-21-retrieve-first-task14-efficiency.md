# 2026-06-21 Retrieve-first Task 14 Efficiency Handoff

## 状态

已完成。

本次关闭 retrieve-first framework reader 路径的效率观测缺口。当前 runner 在
`BaseMemoryProvider.retrieve()` 后会记录最终进入 framework reader prompt 的
`injected_memory_context_tokens`，并在 framework answer LLM 调用后记录 answer 阶段的
LLM input/output tokens。

## 代码变更

- `src/memory_benchmark/observability/efficiency/collector.py`
  - 新增 `record_retrieval_result_if_missing()`。
  - 如果 adapter 已经记录 retrieval latency，runner 只回填最终 context tokens。
  - 如果 adapter 未记录 retrieval，runner 记录 retrieval latency 和 context tokens。

- `src/memory_benchmark/readers/answer.py`
  - 新增 `AnswerLLMResponse`。
  - `OpenAICompatibleAnswerLLMClient.complete_with_metadata()` 保留 SDK usage 和 raw response。
  - `FrameworkAnswerReader.generate_answer_with_trace()` 返回
    `(AnswerResult, prompt, AnswerLLMResponse)`。
  - 旧 `generate_answer()` / `complete()` 仍保持兼容。
  - `FakeAnswerLLMClient` 保持只实现 `complete()`，确保测试子类覆盖 `complete()` 时不会被
    metadata 路径绕过。

- `src/memory_benchmark/runners/prediction.py`
  - retrieve-first 新问题路径记录：
    - retrieval latency。
    - injected memory context tokens。
    - answer latency。
    - answer LLM input/output tokens。
  - answer LLM token 计量优先使用 API usage，缺失时用 `tiktoken` 估算并标记为
    `tokenizer_estimate`。
  - 对 resume 复用 retrieval 的 answer 路径也记录 answer LLM token 和 latency。

- `src/memory_benchmark/cli/run_prediction.py`
  - retrieve-first 且 efficiency 开启时，model inventory 自动追加 framework answer model
    `gpt-4o-mini`，便于后续离线成本聚合。

- `tests/test_prediction_efficiency_observations.py`
  - 新增 retrieve-first context token / answer latency / answer LLM token 测试。
  - 新增 adapter 已记录 retrieval latency 时 runner 只补 context tokens 的测试。

- `tests/test_prediction_cli.py`
  - retrieve-first framework reader 装配测试现在校验 model inventory 包含 framework
    answer model。

## 验证

已运行：

```bash
uv run pytest tests/test_prediction_efficiency_observations.py tests/test_efficiency_analysis.py tests/test_framework_answer_reader.py -q
```

结果：`23 passed`

```bash
uv run pytest tests/test_prediction_runner.py tests/test_prediction_cli.py tests/test_cost_calibration_smoke.py tests/test_main_cli.py -q
```

结果：`123 passed`

```bash
uv run pytest tests/test_retrieve_first_protocol.py tests/test_method_registry.py tests/test_benchmark_registry.py -q
```

结果：`37 passed`

未执行真实 API。

## 注意

- Task 14 已完成，但 retrieve-first 总计划仍未全部结束。
- 下一步进入 Task 15：artifact/evaluation compatibility。
- 旧 `get_answer()` 兼容路径仍未删除；删除必须等 retrieve-first 全链路和真实 smoke 稳定后再做。
- Registry/capability 减重方向已另写入
  `docs/superpowers/specs/2026-06-21-registry-capability-simplification-design.md`，当前只记录
  设计，不在 Task 14 中实施。
