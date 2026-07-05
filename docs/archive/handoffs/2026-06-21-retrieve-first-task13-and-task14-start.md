# 2026-06-21 Retrieve-First Task 13 Complete / Task 14 Start Handoff

## 当前状态

额度低时暂停。请下次恢复时先读：

1. `AGENTS.md`
2. `docs/current-roadmap.md`
3. `docs/task-ledger.md`
4. `docs/superpowers/plans/2026-06-20-retrieve-first-memory-module.md`
5. 本文件

未执行真实 API。

## 已完成：Task 13

Task 13 “Switch Registered Prediction to Retrieve-First” 已完成主体：

- `src/memory_benchmark/cli/run_prediction.py`
  - registered prediction 的 `method_manifest` 已加入 `answer_reader` 公开身份：
    - `answer_protocol: retrieve_first_v1`
    - `answer_prompt_profile`
    - `answer_prompt_file_sha256`
    - `answer_model`
  - reader identity 放在 `method_manifest["answer_reader"]`，因此会进入 immutable
    prediction manifest 和 resume preflight。
  - `.env` / OpenAI settings 读取顺序仍保持在所有 child preflight 之后，避免恢复
    Task 13 时误以为可以提前读 secret。
  - 当前 Phase 1 固定 `DEFAULT_OPENAI_MODEL == "gpt-4o-mini"`，并在构造 framework
    answer reader 前校验实际 `openai_settings.model` 一致。
- `tests/test_prediction_cli.py`
  - `test_registered_prediction_builds_framework_answer_reader` 已新增 reader manifest
    identity 断言。

验证：

```bash
uv run pytest tests/test_prediction_cli.py::test_registered_prediction_builds_framework_answer_reader -q
# red: KeyError: 'answer_reader'
# green: 1 passed

uv run pytest tests/test_prediction_cli.py::test_second_child_preflight_failure_creates_no_output_or_method tests/test_prediction_cli.py::test_openai_settings_load_only_after_all_preflights tests/test_prediction_cli.py::test_registered_prediction_builds_framework_answer_reader -q
# 3 passed

uv run pytest tests/test_prediction_cli.py tests/test_cost_calibration_smoke.py tests/test_main_cli.py -q
# 68 passed
```

Task 13 commit 未做，因为当前 worktree 混有多批 Codex/OpenCode 改动，应后续分组提交。

## 已开始但未完成：Task 14

Task 14 “Update Efficiency Observation for Framework Answer” 只做了测试夹具准备，尚未完成。

已改文件：

- `tests/test_prediction_efficiency_observations.py`
  - 新增 imports：
    - `RetrievalResult`
    - `BaseMemoryProvider`
    - `FakeAnswerLLMClient`
    - `FrameworkAnswerReader`
  - 新增 `_RetrieveFirstFakeProvider(BaseMemoryProvider)`：
    - `add(conversation)`
    - `retrieve(question)` 返回固定 `formatted_context`

尚未完成：

- 尚未成功插入 `test_retrieve_first_records_context_tokens_and_answer_latency`。
- production code 尚未改。
- 当前 retrieve-first runner 仍在 `_answer_question_retrieve_first()` 中调用：

```python
efficiency_collector.record_retrieval_result(
    latency_ms=_elapsed_ms(started_ns),
    injected_memory_context_tokens=None,
)
```

这正是 Task 14 下一步要改的点：`injected_memory_context_tokens` 应基于
`retrieval.formatted_context` 计数，而不是 `None`。

## 下一步建议

1. 继续 Task 14，先把红测插入 `tests/test_prediction_efficiency_observations.py`。
   建议插入位置：`test_resume_manifest_mismatch_due_to_instrumentation_identity`
   之后、`test_runner_records_isolated_build_and_question_observations_concurrently` 之前。
2. 红测命令：

```bash
uv run pytest tests/test_prediction_efficiency_observations.py::test_retrieve_first_records_context_tokens_and_answer_latency -q
```

预期失败：

```text
AssertionError
```

原因应是 `QuestionEfficiencyObservation.injected_memory_context_tokens is None`。

3. 实现时优先做最小闭环：
   - 在 retrieve-first runner 分支用现有 token counter 对
     `retrieval.formatted_context` 计数。
   - 先不强行实现 answer LLM API usage；如果要做 usage，需要扩展
     `FrameworkAnswerReader` / `OpenAICompatibleAnswerLLMClient` 的返回结构。
4. Task 14 focused 验证：

```bash
uv run pytest tests/test_prediction_efficiency_observations.py tests/test_efficiency_analysis.py -q
```

5. 完成 Task 14 后再更新：
   - `AGENTS.md`
   - `docs/current-roadmap.md`
   - `docs/task-ledger.md`
   - 本实施计划

## 已知注意事项

- 不要启动真实 API。
- 不要提前读取 `.env` 或 OpenAI settings 到 child preflight 之前。
- 当前 `git status` 很脏，包含多批历史改动；不要在未分组前一次性 commit。
