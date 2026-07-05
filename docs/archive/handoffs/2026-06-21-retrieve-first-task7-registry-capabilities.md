# 2026-06-21 Retrieve-First Task 7 Registry Capabilities Handoff

## 本次完成

- 完成 retrieve-first Task 7：
  - `src/memory_benchmark/methods/registry.py` 中 Mem0、MemoryOS、A-Mem、LightMem
    均改为声明 `CONVERSATION_ADD + MEMORY_RETRIEVAL`。
  - 四个内置 method 不再声明 `ANSWER_GENERATION`。
  - `src/memory_benchmark/benchmark_adapters/registry.py` 中 LoCoMo / LongMemEval
    conversation-QA prediction requirement 改为
    `CONVERSATION_ADD + MEMORY_RETRIEVAL`。
- 新增 `tests/test_method_registry.py::test_built_in_methods_advertise_memory_retrieval_capability`
  作为红测，先确认旧注册表缺 `MEMORY_RETRIEVAL` 会失败，再更新实现。
- 更新 `tests/test_method_registry.py` 和 `tests/test_benchmark_registry.py` 的旧 capability
  断言。

## 验证

已执行，均未触发真实 API：

```bash
uv run pytest tests/test_method_registry.py::test_built_in_methods_advertise_memory_retrieval_capability -q
uv run pytest tests/test_method_registry.py -q
uv run pytest tests/test_benchmark_registry.py -q
uv run pytest tests/test_prediction_cli.py -q
uv run pytest tests/test_main_cli.py tests/test_cost_calibration_smoke.py -q
uv run pytest tests/test_prediction_runner.py tests/test_framework_answer_reader.py -q
uv run pytest tests/test_documentation_standards.py -q
```

结果：

- `tests/test_method_registry.py`：11 passed
- `tests/test_benchmark_registry.py`：24 passed
- `tests/test_prediction_cli.py`：28 passed
- main CLI + cost calibration：40 passed
- prediction runner + framework reader：62 passed
- documentation standards：5 passed

## 当前边界

- 这一步会让 registered prediction 对四个内置 method 进入 framework reader 路径，因为
  service 层现在根据 `MEMORY_RETRIEVAL` capability 构造 `FrameworkAnswerReader`。
- 当前四个 method adapter 仍未迁移到 `retrieve(question)` 主接口。不要启动真实 API
  prediction，直到 Task 8+method adapter 迁移和 focused smoke 完成。
- legacy `get_answer()` 主路径仍保留，方便迁移期间的局部回归和历史 artifact 复查。
- 本次没有 commit。当前 worktree 混有多批 Codex/OpenCode 改动，提交前需要先整理 diff。

## 下一步建议

1. 继续执行 `docs/superpowers/plans/2026-06-20-retrieve-first-memory-module.md` 的
   Task 8：迁移 mock/fake methods 和相关 runner tests。
2. Task 8 完成后再开始逐个 method adapter 迁移，先做 fake/offline contract，不直接
   运行真实 API。
3. manifest/source identity 需要纳入 answer prompt/profile 和 reader 配置，否则不同 reader
   配置可能错误 resume 到旧 run。
