# 2026-06-21 Retrieve-First Task 10 A-Mem Adapter 交接

## 状态

Task 10 主体已完成，未提交 commit。

本轮只做离线/fake 测试，没有执行真实 API。当前 worktree 仍包含多批历史 Codex/OpenCode
改动，提交前需要统一整理 staged scope。

## 完成内容

- 在 `tests/test_amem_adapter.py` 增加
  `test_amem_retrieve_returns_query_keywords_and_context`。
- 按 TDD 验证红测：
  `uv run pytest tests/test_amem_adapter.py::test_amem_retrieve_returns_query_keywords_and_context -q`
  先因 `AttributeError: 'AMem' object has no attribute 'retrieve'` 失败。
- 在 `src/memory_benchmark/methods/amem_adapter.py` 新增
  `AMem.retrieve(question) -> RetrievalResult`。
- `retrieve()` 从旧 `get_answer()` 中抽出 A-Mem 官方检索前半段：
  - 校验 conversation 已写入。
  - 继续拒绝 LoCoMo category 5 adversarial，因为官方 prompt 需要 gold answer，
    不能进入 method public input。
  - 继续使用 `_retrieve_k_for_question()`，保留 Table 8 category k。
  - 继续使用 `_generate_query_keywords()`，保留官方 query keyword generation。
  - 调用 `runtime.find_related_memories_raw(query_keywords, k=retrieve_k)`。
  - 在 collector 开启时继续记录 retrieval latency 和
    `injected_memory_context_tokens`。
- `RetrievalResult.formatted_context` 保存 A-Mem 检索后格式化 context；
  metadata 包含 `method`、`retrieve_k`、`query_keywords` 和
  `query_keyword_prompt_version`。
- 旧 `get_answer()` 暂时作为兼容 wrapper：
  - 先调用 `retrieve()`。
  - 再把 `retrieval.formatted_context` 传入原 `_build_answer_prompt()`。
  - 继续使用原 `_call_answer_llm()` 和 answer observation。
- 修正 retrieve-first runner 分支的协议判定缺口：
  - `AMem` 现在继承 `BaseMemoryProvider` 和 `BaseMemorySystem`。
  - `AMem.add()` 迁移期同时兼容单个 `Conversation` 和旧 `list[Conversation]`。
  - `tests/test_amem_registered_prediction.py` 的 fake method 也继承
    `BaseMemoryProvider`，fake benchmark capability 改为 `MEMORY_RETRIEVAL`，
    并用 fake framework answer client 避免真实 API。
- 同步更新实施计划、路线图、任务总账、AGENTS 和 README。

## 验证

已通过：

```bash
uv run pytest tests/test_amem_adapter.py::test_amem_retrieve_returns_query_keywords_and_context -q
```

结果：`1 passed`

```bash
uv run pytest tests/test_amem_adapter.py tests/test_amem_registered_prediction.py -q
```

结果：`17 passed, 1 warning`

```bash
uv run pytest tests/test_mem0_adapter.py tests/test_mem0_source_compatibility.py -q
```

结果：`21 passed`

```bash
uv run pytest tests/test_prediction_runner.py tests/test_framework_answer_reader.py -q
```

结果：`63 passed`

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
  不在 Task 10 内完成。
- LightMem 和 MemoryOS 尚未迁移到 `retrieve()`。
- `get_answer()` 仍保留兼容路径；最终删除需要等四个 adapter 和 isolated worker 路径
  全部完成后再单独处理。
- 本轮尚未跑文档规范、`compileall` 和 `git diff --check`；准备暂停或提交前必须补跑。

## 下一步

1. 进入 Task 11：迁移 LightMem adapter。
2. 先补两个红测：
   - LoCoMo retrieve 走 `search_locomo.py` 风格专门检索。
   - LongMemEval retrieve 保留 `LightMemory.retrieve()` online 路径。
3. LightMem 完成后再迁移 MemoryOS。
4. 之后再统一处理 isolated worker 的 retrieve-first 路径，以及 manifest/source identity
   是否需要增加 answer protocol 字段。
