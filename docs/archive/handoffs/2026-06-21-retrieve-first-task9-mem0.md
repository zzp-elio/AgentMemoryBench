# 2026-06-21 Retrieve-First Task 9 Mem0 Adapter 交接

## 状态

Task 9 主体已完成，未提交 commit。

本轮只做离线/fake 测试，没有执行真实 API。当前 worktree 仍包含多批历史 Codex/OpenCode
改动，提交前需要统一整理 staged scope，避免把大型数据、outputs 或无关变更提交进去。

## 完成内容

- 在 `tests/test_mem0_adapter.py` 增加
  `test_mem0_retrieve_returns_formatted_context`。
- 按 TDD 验证红测：
  `uv run pytest tests/test_mem0_adapter.py::test_mem0_retrieve_returns_formatted_context -q`
  先因 `AttributeError: 'Mem0' object has no attribute 'retrieve'` 失败。
- 在 `src/memory_benchmark/methods/mem0_adapter.py` 新增
  `Mem0.retrieve(question) -> RetrievalResult`。
- `retrieve()` 复用旧 `get_answer()` 中的 Mem0 search 流程：
  - 强校验 conversation 已写入。
  - 强校验 question text 非空。
  - 按 `filters={"run_id": conversation_id}` 和 `top_k=config.top_k` 检索。
  - 复用 `_normalize_search_results()`。
  - 使用 `_memory_context_text()` 生成 `formatted_context`。
  - 在 collector 开启时继续记录 retrieval latency 和
    `injected_memory_context_tokens`。
- `RetrievalResult.memories` 使用标准 `RetrievedMemory`，并把 `created_at` 放入
  `metadata`，保证旧 Mem0 官方 LoCoMo/LongMemEval prompt 仍可重建日期信息。
- 旧 `get_answer()` 暂时作为兼容 wrapper：
  - 先调用 `retrieve()`。
  - 再把标准 retrieval result 转回 Mem0 官方 prompt builder 需要的记忆字典。
  - 继续调用原有 `_reader_messages()` 和 reader LLM 逻辑。
- 后续 Task 10 调试时发现 runner 的 retrieve-first 分支依赖
  `isinstance(system, BaseMemoryProvider)`。因此本轮又补齐 Mem0 的协议继承：
  `class Mem0(BaseMemoryProvider, BaseResumableMemorySystem)`。
- Mem0 `add()` 现在迁移期同时兼容单个 `Conversation` 和旧 `list[Conversation]`：
  普通 retrieve-first runner 可调用 `add(public_conversation)`，旧测试和 isolated
  worker 仍可调用 `add([public_conversation])`。
- 更新 `docs/superpowers/plans/2026-06-20-retrieve-first-memory-module.md`、
  `docs/current-roadmap.md`、`docs/task-ledger.md`、`AGENTS.md`、`README.md`。

## 验证

已通过：

```bash
uv run pytest tests/test_mem0_adapter.py::test_mem0_retrieve_returns_formatted_context -q
```

结果：`1 passed`

```bash
uv run pytest tests/test_mem0_adapter.py tests/test_mem0_source_compatibility.py -q
```

结果：`21 passed`

```bash
uv run pytest tests/test_retrieve_first_protocol.py tests/test_framework_answer_reader.py -q
```

结果：`10 passed`

Task 10 后补验证：

```bash
uv run pytest tests/test_mem0_adapter.py tests/test_mem0_source_compatibility.py -q
```

结果：`21 passed`

```bash
uv run pytest tests/test_prediction_runner.py tests/test_prediction_cli.py tests/test_main_cli.py tests/test_cost_calibration_smoke.py -q
```

结果：`123 passed`

## 当前限制

- `get_answer()` 仍存在，只是兼容 wrapper；最终删除旧路径需要等 A-Mem、LightMem、
  MemoryOS 也完成 retrieve-first 迁移，并且 runner/CLI/manifest/source identity 全部
  切到新协议后再做。
- Mem0 source identity 暂未因 `retrieve()` wrapper 变化额外调整；相关 source
  compatibility 测试已通过。
- 本轮尚未跑完整 `tests/test_prediction_runner.py`、文档规范、`compileall` 和
  `git diff --check`，完成 Task 10 前或准备提交前必须补跑。

## 下一步

1. 按计划进入 Task 10：迁移 A-Mem adapter。
2. 仍然按 TDD：先补 `test_amem_retrieve_returns_query_keywords_and_context` 红测。
3. A-Mem `retrieve()` 必须保留官方 query keyword generation、category k、base URL
   注入和现有 efficiency observation，不得把 gold answer/evidence 放进 public input。
4. 每完成一个 adapter 迁移，都同步更新 `AGENTS.md`、`docs/current-roadmap.md`、
   `docs/task-ledger.md` 和对应 handoff。
