# 2026-06-21 Retrieve-First Task 11 LightMem Adapter 交接

## 状态

Task 11 主体已完成，未提交 commit。

本轮只做离线/fake 测试，没有执行真实 API。当前 worktree 仍包含多批历史 Codex/OpenCode
改动，提交前需要统一整理 staged scope。

## 完成内容

- 在 `tests/test_lightmem_adapter.py` 增加：
  - `test_lightmem_retrieve_locomo_uses_specialized_context`
  - `test_lightmem_retrieve_longmemeval_uses_backend_retrieve`
- 按 TDD 验证红测：
  `uv run pytest tests/test_lightmem_adapter.py::test_lightmem_retrieve_locomo_uses_specialized_context tests/test_lightmem_adapter.py::test_lightmem_retrieve_longmemeval_uses_backend_retrieve -q`
  先因 `AttributeError: 'LightMem' object has no attribute 'retrieve'` 失败。
- 在 `src/memory_benchmark/methods/lightmem_adapter.py` 新增
  `LightMem.retrieve(question) -> RetrievalResult`。
- `retrieve()` 从旧 `get_answer()` 中抽出 LightMem 检索前半段：
  - 校验 conversation 已写入。
  - LongMemEval 问题继续调用 `backend.retrieve(question.text, limit=retrieve_limit,
    filters=None)`，metadata 标记 `retrieval_profile="lightmemory_retrieve"`。
  - LoCoMo 问题继续调用 `_retrieve_locomo_memories()`，即官方
    `experiments/locomo/search_locomo.py` 风格的 Qdrant payload/vector combined search，
    metadata 标记 `retrieval_profile="locomo_qdrant_combined"`。
  - 在 collector 开启时继续记录 retrieval latency 和
    `injected_memory_context_tokens`。
- `RetrievalResult.formatted_context` 使用 `_format_lightmem_memory()` 格式化后的公开
  memory context。
- `RetrievalResult.memories` 使用标准 `RetrievedMemory`；LoCoMo payload、speaker 和
  score 被保存在 metadata 中，供迁移期旧 `get_answer()` 无损重建官方 speaker 分组 prompt。
- 旧 `get_answer()` 暂时作为兼容 wrapper：
  - 先调用 `retrieve()`。
  - 再把标准 retrieval result 转回 `_build_answer_prompt()` 需要的结构。
  - 继续使用原 `_call_answer_client()` 和 answer observation。
- `LightMem` 现在继承 `BaseMemoryProvider` 和 `BaseMemorySystem`。
- `LightMem.add()` 迁移期同时兼容单个 `Conversation` 和旧 `list[Conversation]`。
- `tests/test_lightmem_registered_prediction.py` 的 fake method 也改为
  `BaseMemoryProvider`，fake benchmark capability 改为 `MEMORY_RETRIEVAL`，并用 fake
  framework answer client 避免真实 API。
- 同步更新实施计划、路线图、任务总账、AGENTS 和 README。

## 验证

已通过：

```bash
uv run pytest tests/test_lightmem_adapter.py::test_lightmem_retrieve_locomo_uses_specialized_context tests/test_lightmem_adapter.py::test_lightmem_retrieve_longmemeval_uses_backend_retrieve -q
```

结果：`2 passed`

```bash
uv run pytest tests/test_lightmem_adapter.py tests/test_lightmem_registered_prediction.py -q
```

结果：`23 passed, 1 warning`

```bash
uv run pytest tests/test_amem_adapter.py tests/test_amem_registered_prediction.py tests/test_mem0_adapter.py tests/test_mem0_source_compatibility.py -q
```

结果：`38 passed, 1 warning`

```bash
uv run pytest tests/test_prediction_runner.py tests/test_prediction_cli.py tests/test_main_cli.py tests/test_cost_calibration_smoke.py -q
```

结果：`123 passed`

```bash
uv run pytest tests/test_method_registry.py tests/test_benchmark_registry.py tests/test_retrieve_first_protocol.py tests/test_framework_answer_reader.py -q
```

结果：`45 passed`

## 当前限制

- isolated worker 内部仍使用旧 `get_answer()` 路径；这是 runner 层后续迁移事项，
  不在 Task 11 内完成。
- MemoryOS 尚未迁移到 `retrieve()`。
- LightMem `RetrievedMemory.metadata` 为了兼容旧 prompt 保留公开 payload；后续做
  artifact 瘦身时要统一决定是否压缩 retrieval memories 明细。
- 本轮尚未跑文档规范、`compileall` 和 `git diff --check`；准备暂停或提交前必须补跑。

## 下一步

1. 进入 Task 12：迁移 MemoryOS adapter。
2. MemoryOS retrieve 需要保留当前 LoCoMo paper/eval backend 的官方 retrieval queue、
   long-term knowledge 和最终 prompt context 观测语义。
3. Task 12 完成后再处理 isolated worker 的 retrieve-first 路径，避免多 worker 仍走
   legacy `get_answer()`。
4. 最后统一更新 manifest/source identity/observability，并跑 focused full
   retrieve-first regression。
