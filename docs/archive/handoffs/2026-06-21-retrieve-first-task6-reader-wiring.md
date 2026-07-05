# 2026-06-21 Retrieve-First Task 6 Reader Wiring Handoff

## 本次完成

- 完成 retrieve-first Task 6 的 service 层接线：
  `run_registered_conversation_qa_prediction()` 现在会在 method 声明
  `MethodCapability.MEMORY_RETRIEVAL` 时构造 `FrameworkAnswerReader`，并把它传给
  `run_predictions(answer_reader=...)`。
- legacy `ANSWER_GENERATION` 路径继续保持旧行为，不提前构造 framework reader，避免破坏
  当前四个 method 尚未迁移时的稳定性。
- 新增 `tests/test_prediction_cli.py::test_registered_prediction_builds_framework_answer_reader`，
  用 fake OpenAI-compatible answer client 验证：
  - 自定义 prompt 文件被加载；
  - `answer_prompt_profile` 进入 reader；
  - `OpenAISettings` 被传给 answer client；
  - `answer_reader` 确实传给 `run_predictions()`。
- 更新 `tests/test_main_cli.py` 中 command delegation 断言，覆盖
  `answer_prompt_file` / `answer_prompt_profile`。
- 对 `tests/test_prediction_cli.py` 中与效率观测无关的简化 mock 用例显式关闭
  `enable_efficiency_observability`，避免用不完整 `SimpleNamespace` 模拟完整
  `MethodRegistration`。

## 验证

已执行，均未触发真实 API：

```bash
uv run pytest tests/test_prediction_cli.py::test_registered_prediction_builds_framework_answer_reader -q
uv run pytest tests/test_prediction_cli.py -q
uv run pytest tests/test_main_cli.py -q
uv run pytest tests/test_framework_answer_reader.py tests/test_prediction_runner.py tests/test_prediction_efficiency_observations.py -q
uv run python -m compileall -q src/memory_benchmark tests
git diff --check
```

结果：

- `tests/test_prediction_cli.py`：28 passed
- `tests/test_main_cli.py`：27 passed
- reader/runner/efficiency focused：72 passed
- `compileall`：exit 0
- `git diff --check`：exit 0

## 当前边界

- Task 6 完成，但 retrieve-first 主迁移尚未完成。
- `FrameworkAnswerReader` 只在 `MEMORY_RETRIEVAL` capability 下启用；当前 registry 仍有大量
  legacy `ANSWER_GENERATION` 路径。
- 还没有把 answer prompt/profile、reader model、reader source identity 写入 prediction
  manifest；这是后续 manifest/source identity 任务。
- 还没有把 Mem0、A-Mem、LightMem、MemoryOS adapters 迁移到 `retrieve()` 主路径。
- LLM provider config 设计已完成，但当前代码仍使用 `OpenAISettings` 小步实现；后续再迁移
  到统一 `LLMRuntimeConfig` / `LLMResponse`。
- 本次没有 commit。当前 worktree 混有多批 Codex/OpenCode 改动，提交前需要先整理 diff。

## 下一步建议

1. 按 `docs/superpowers/plans/2026-06-20-retrieve-first-memory-module.md` 继续 Task 7：
   registry / benchmark capability 从 `ANSWER_GENERATION` 迁移到 `MEMORY_RETRIEVAL`。
2. 同步更新 manifest/source identity，确保不同 answer prompt/profile 或 reader 配置不能
   错误 resume 到旧 run。
3. 再开始 method adapter 迁移；每个 method 都先做 fake/offline retrieve contract 测试，
   不直接启动真实 API。
