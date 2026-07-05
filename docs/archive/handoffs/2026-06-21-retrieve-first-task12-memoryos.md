# 2026-06-21 Retrieve-First Task 12 MemoryOS Handoff

## 状态

已完成。MemoryOS adapter 已迁移到 retrieve-first provider 形态：

- `MemoryOS` 继承 `BaseMemoryProvider`。
- `add()` 在迁移期同时兼容单个 `Conversation` 和旧 `list[Conversation]` 输入。
- 新增 `retrieve(question) -> RetrievalResult`，调用 MemoryOS eval 路径的
  `retrieval_system.retrieve(...)`。
- `RetrievalResult.formatted_context` 会把 retrieval queue 和 long-term knowledge 格式化为
  framework reader 可直接注入 prompt 的上下文。
- 旧 `get_answer()` 保持原行为，没有改成调用 `retrieve()`，避免破坏 MemoryOS 现有
  system prompt observer 和历史复查路径。

未执行真实 API。

## 修改文件

- `src/memory_benchmark/methods/memoryos_adapter.py`
  - 新增 `RetrievalResult` / `BaseMemoryProvider` 接线。
  - 新增 `MemoryOS.retrieve()`。
  - 新增 `_memoryos_formatted_context(...)`。
- `tests/test_memoryos_adapter.py`
  - 新增 MemoryOS retrieve 格式化测试。
- `tests/test_memoryos_registered_prediction.py`
  - fake MemoryOS 改为 `BaseMemoryProvider`。
  - fake MemoryOS 新增 `retrieve()`。
  - registered prediction 测试改为使用 fake framework answer client，避免真实 API。
  - `load_openai_settings` 测试替身改为完整 `OpenAISettings`，避免缺少 `model` 字段。
- 文档：
  - `AGENTS.md`
  - `README.md`
  - `docs/current-roadmap.md`
  - `docs/task-ledger.md`
  - `docs/method-interface-inventory.md`
  - `docs/superpowers/plans/2026-06-20-retrieve-first-memory-module.md`

## 验证

已通过：

```bash
uv run pytest tests/test_memoryos_adapter.py::MemoryOSAdapterTests::test_retrieve_formats_retrieval_queue_and_knowledge -q
# 1 passed

uv run pytest tests/test_memoryos_adapter.py tests/test_memoryos_registered_prediction.py -q
# 138 passed, 2 subtests passed

uv run pytest tests/test_mem0_adapter.py tests/test_mem0_source_compatibility.py tests/test_amem_adapter.py tests/test_amem_registered_prediction.py tests/test_lightmem_adapter.py tests/test_lightmem_registered_prediction.py tests/test_memoryos_adapter.py tests/test_memoryos_registered_prediction.py -q
# 199 passed, 2 warnings, 2 subtests passed

uv run pytest tests/test_prediction_runner.py tests/test_prediction_cli.py tests/test_main_cli.py tests/test_cost_calibration_smoke.py -q
# 123 passed

uv run pytest tests/test_method_registry.py tests/test_benchmark_registry.py tests/test_retrieve_first_protocol.py tests/test_framework_answer_reader.py -q
# 45 passed
```

文档更新后补充验证：

```bash
uv run pytest tests/test_documentation_standards.py -q
# 5 passed

uv run python -m compileall -q src/memory_benchmark tests
# exit 0

git diff --check
# exit 0
```

## 调试记录

MemoryOS registered focused tests 初次失败不是生产代码问题，而是测试夹具问题：

- retrieve-first registered service 会构造 `OpenAICompatibleAnswerLLMClient`。
- 旧测试用 `SimpleNamespace(api_key, base_url)` 假装 OpenAI settings，缺少 `model`。
- 解决方式是使用真实 `OpenAISettings` 测试对象，并 patch fake framework answer client，
  保持测试离线。

## 下一步

1. 跑文档规范、`compileall` 和 `git diff --check`。
2. 进入 retrieve-first 计划 Task 13/14：
   - manifest/source identity 加入 reader/protocol identity。
   - 检查 efficiency observation 中 framework answer 与 adapter retrieval 的归属。
   - 明确旧 `get_answer()` 兼容路径何时下线。
3. 真实 API smoke 仍需用户确认 method、benchmark、样本规模和 run_id 后才能启动。
4. 本轮未 commit。当前 worktree 混有多批 Codex/OpenCode 变更，建议后续按功能分组提交。
