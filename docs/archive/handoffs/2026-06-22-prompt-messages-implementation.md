# 2026-06-22 Prompt Messages 实现交接

## 背景

用户指出 `answer_messages: list[AnswerMessage]` 命名不够直观，并进一步确认：
method adapter 不应该只返回单字符串 prompt，而应该返回官方 answer LLM 调用所需的
role message 结构，例如 system/user。

最终命名：

- 元素类型：`PromptMessage`
- 主字段：`AnswerPromptResult.prompt_messages`
- 兼容文本视图：`AnswerPromptResult.answer_prompt`

`prompt_messages` 表示“交给 answer LLM 的完整 prompt messages”。`answer_prompt` 不再是
主协议，只用于 artifact、日志、resume 兼容和 token 估算。

## 已完成实现

- `src/memory_benchmark/core/entities.py`
  - 新增 `PromptMessage(role, content)`。
  - `AnswerPromptResult` 新增 `prompt_messages`。
  - `answer_prompt` 为空时由 `prompt_messages` 自动生成带 `[role]` 标记的文本视图。
  - 旧 artifact 只含 `answer_prompt` 时会降级为单条 user message。
- `src/memory_benchmark/readers/answer.py`
  - `FrameworkAnswerReader` 改为要求非空 `prompt_messages`。
  - `OpenAICompatibleAnswerLLMClient` 新增 `complete_messages_with_metadata()`，直接发送
    role messages 到 chat completions。
  - `FakeAnswerLLMClient` 记录 `messages`，便于测试验证 role 结构没有被压平。
- `src/memory_benchmark/runners/prediction.py`
  - `answer_prompts.prediction.jsonl` 现在保存 `prompt_messages`。
  - answer 已失败但 prompt 已落盘时，resume 会从 artifact 还原 `prompt_messages`，
    不重新调用 provider.retrieve。
  - 旧 artifact 没有 `prompt_messages` 时仍能从 `answer_prompt` 恢复为 user message。
- 四个内置 method adapter
  - Mem0：官方 LoCoMo / LongMemEval prompt 为 user-only；通用 fallback 为 system+user。
  - A-Mem：system+user，system 为官方 controller 的格式约束语义。
  - LightMem：LoCoMo 为 system-only；LongMemEval 为 system+user。
  - MemoryOS：system+user，保留官方 eval prompt 的 system/user 分离。

## 文档同步

已同步：

- `AGENTS.md`
- `README.md`
- `docs/current-roadmap.md`
- `docs/task-ledger.md`
- `docs/method-interface-inventory.md`
- `src/memory_benchmark/core/Readme.md`
- `docs/superpowers/specs/2026-06-20-retrieve-first-memory-module-design.md`
- `docs/superpowers/plans/2026-06-20-retrieve-first-memory-module.md`

当前事实：`AnswerPromptResult.prompt_messages` 是主协议；`answer_prompt` 是兼容文本视图。

## 验证证据

已运行：

```bash
uv run pytest tests/test_prediction_runner.py::test_runner_uses_retrieve_first_provider_and_framework_reader tests/test_prediction_runner.py::test_shared_mock_provider_uses_framework_reader tests/test_prediction_runner.py::test_resume_reuses_completed_retrieval_when_answer_failed -q
```

结果：

```text
3 passed
```

已运行：

```bash
uv run pytest tests/test_framework_answer_reader.py tests/test_mem0_adapter.py tests/test_amem_adapter.py tests/test_lightmem_adapter.py tests/test_memoryos_adapter.py tests/test_prediction_runner.py::test_runner_uses_retrieve_first_provider_and_framework_reader tests/test_prediction_runner.py::test_shared_mock_provider_uses_framework_reader tests/test_prediction_runner.py::test_resume_reuses_completed_retrieval_when_answer_failed -q
```

结果：

```text
204 passed, 2 warnings, 2 subtests passed
```

警告来自第三方 A-Mem `ast.Str` 和 LightMem pydantic class config deprecation，非本轮新增。

已运行：

```bash
uv run pytest tests/test_retrieve_first_protocol.py tests/test_framework_answer_reader.py tests/test_prediction_runner.py tests/test_prediction_efficiency_observations.py tests/test_prediction_cli.py tests/test_memoryos_registered_prediction.py tests/test_amem_registered_prediction.py tests/test_lightmem_registered_prediction.py tests/test_method_registry.py tests/test_main_cli.py tests/test_cost_calibration_smoke.py tests/test_artifact_evaluation_runner.py -q
```

结果：

```text
188 passed
```

已运行：

```bash
uv run pytest tests/test_documentation_standards.py -q
uv run python -m compileall -q src/memory_benchmark tests
git diff --check
```

结果：

```text
5 passed
compileall exit 0
git diff --check exit 0
```

checkpoint 前另运行完整离线回归：

```bash
uv run pytest -q
```

结果：

```text
669 passed, 3 deselected, 2 warnings, 6 subtests passed
```

完整回归中修正了两个旧测试预期：LoCoMo judge fake client 已跟随当前
`chat.completions.create()` 路径；LongMemEval smoke registry 测试已按
`smoke_conversation_limit` 的“最多 N 个 instance”语义更新。

## 未完成事项

- 尚未执行真实 API smoke。
- legacy `get_answer()` / `BaseMemorySystem` 删除仍是后续独立任务，不能在未跑真实 retrieve-first
  smoke 前直接删除。

## 恢复建议

1. 先读 `AGENTS.md`、`docs/task-ledger.md` 和本文件。
2. 继续跑更宽 focused 回归。
3. 若通过，更新本文件验证证据或新建后续 handoff。
4. 只有用户明确确认 API 预算、run_id、method、benchmark、turn/question/conversation limit
   后，才能启动真实 API smoke。
