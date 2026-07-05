# 2026-06-21 Retrieve-First Task 8 Mock Provider Handoff

## 本次完成

- 完成 retrieve-first Task 8 的共享 mock/fake 测试层迁移。
- 新增 `src/memory_benchmark/methods/mock.py::MockMemoryProvider`：
  - 实现 `BaseMemoryProvider.add(conversation)`；
  - 实现 `BaseMemoryProvider.retrieve(question)`；
  - 按 `context_by_question_id` 返回 `RetrievalResult.formatted_context`；
  - 未配置问题时返回 `mock-context-for:{question_id}`。
- 保留 legacy `MockMemorySystem`，避免破坏旧 `tests/test_conversation_runner.py`。
- 新增
  `tests/test_prediction_runner.py::test_shared_mock_provider_uses_framework_reader`，
  验证共享 mock provider 走 `retrieve()` + `FrameworkAnswerReader`，最终 answer 来自
  framework reader，而不是 method 自己生成。

## 验证

已执行，均未触发真实 API：

```bash
uv run pytest tests/test_prediction_runner.py::test_shared_mock_provider_uses_framework_reader -q
uv run pytest tests/test_prediction_runner.py tests/test_prediction_efficiency_observations.py -q
uv run pytest tests/test_conversation_runner.py -q
```

结果：

- 新增共享 mock provider 测试：1 passed
- prediction runner + efficiency observations：65 passed
- legacy conversation runner：6 passed

## 当前边界

- Task 8 只迁移共享 mock/fake 测试层，不代表真实 method adapters 已完成 retrieve-first。
- 四个真实 adapters 仍保留 legacy `get_answer()`，后续需要按计划逐个新增/迁移
  `retrieve(question)`。
- 当前 registry 已把内置 method capability 切到 `MEMORY_RETRIEVAL`，因此不要启动真实 API
  prediction，直到对应 method adapter 的 retrieve-first contract 测试和 smoke 验证完成。
- 本次没有 commit。当前 worktree 混有多批 Codex/OpenCode 改动，提交前需要先整理 diff。

## 下一步建议

1. 继续 Task 9：迁移 Mem0 adapter，先写 fake-backend `retrieve(question)` 红测。
2. Mem0 迁移时复用现有 `_memory_context_text(memories)`，避免改动官方检索流程。
3. Mem0 完成后再按 A-Mem、LightMem、MemoryOS 顺序逐个迁移；每个 method 都先做
   fake/offline tests，不直接运行真实 API。
