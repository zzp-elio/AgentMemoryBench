# 2026-06-21 Low Quota Handoff: Retrieve-first Task 16 Closed

## 当前断点

本次低额度交接发生在一个完整闭合点：

- retrieve-first 实施计划 Task 15 已完成。
- retrieve-first 实施计划 Task 16 已完成。
- 当前没有正在运行的命令或后台 session。
- 未执行任何真实 API 调用。
- 未提交 git commit；当前工作区仍包含大量前序 Codex/OpenCode 改动，需要后续按主题分组
  review/stage/commit。

## 本轮完成内容

### Task 15: Artifact / Evaluation Compatibility

已完成：

- `tests/test_artifact_evaluation_runner.py` 新增
  `test_answer_level_evaluation_ignores_retrieval_artifact_by_default`。
- 规则已锁定：answer-level evaluation 默认只读：
  - `artifacts/public_questions.jsonl`
  - `artifacts/method_predictions.jsonl`
  - `artifacts/evaluator_private_labels.jsonl`
- `artifacts/retrieval_results.prediction.jsonl` 可以存在，但 F1/Judge 默认不会读取它。
- LongMemEval offline 装配测试已从旧
  `BaseMemorySystem + ANSWER_GENERATION` fake 迁移为
  `BaseMemoryProvider + MEMORY_RETRIEVAL` fake provider。
- 测试仍保持离线：不读真实 `.env`，使用 fake OpenAI-compatible settings 和 fake answer
  client。

验证：

```bash
uv run pytest tests/test_artifact_evaluation_runner.py::test_answer_level_evaluation_ignores_retrieval_artifact_by_default -q
```

结果：`1 passed`。

```bash
uv run pytest tests/test_artifact_evaluation_runner.py tests/test_llm_judge_parsing.py -q
```

结果：`29 passed`。

### Task 16: Documentation and Migration Cleanup

已完成：

- 更新 `README.md`：当前主协议改为已落地的
  `add(conversation) + retrieve(question)`，旧 `get_answer()` 是迁移期兼容。
- 更新 `src/memory_benchmark/core/Readme.md`：core 接口说明切到
  `BaseMemoryProvider`，旧 `BaseMemorySystem` / `BaseResumableMemorySystem` /
  `BaseMemoryRetriever` 标为 legacy。
- 更新 `docs/method-interface-inventory.md`：新 method 接入只记录 `retrieve()` 包装状态；
  `get_answer()` 只作为 legacy 兼容状态记录。
- 创建总 handoff：
  `docs/handoffs/2026-06-20-retrieve-first-implementation.md`。
- 更新：
  - `AGENTS.md`
  - `docs/current-roadmap.md`
  - `docs/task-ledger.md`
  - `docs/superpowers/plans/2026-06-20-retrieve-first-memory-module.md`

Task 16 focused 回归：

```bash
uv run pytest tests/test_retrieve_first_protocol.py tests/test_framework_answer_reader.py tests/test_prediction_runner.py tests/test_prediction_efficiency_observations.py tests/test_method_registry.py tests/test_mem0_adapter.py tests/test_amem_adapter.py tests/test_lightmem_adapter.py tests/test_memoryos_adapter.py tests/test_main_cli.py tests/test_prediction_cli.py -q
```

结果：`332 passed, 2 warnings, 2 subtests passed`。

文档和静态验证：

```bash
uv run pytest tests/test_documentation_standards.py -q
uv run python -m compileall -q src/memory_benchmark tests
git diff --check
```

结果：

- `tests/test_documentation_standards.py`: `5 passed`
- `compileall`: exit 0
- `git diff --check`: exit 0

## 当前事实

- retrieve-first 实施计划 Task 1-16 已完成。
- 四个内置 method：Mem0、A-Mem、LightMem、MemoryOS 都已继承 `BaseMemoryProvider` 并新增
  `retrieve(question) -> RetrievalResult`。
- registered prediction 已在 `MEMORY_RETRIEVAL` capability 下构造
  `FrameworkAnswerReader`。
- framework answer path 已记录：
  - injected memory context tokens
  - answer latency
  - answer LLM input/output tokens
  - framework answer model inventory
- retrieval artifact 与 answer artifact 已分离：
  - retrieval 写入 `retrieval_results.prediction.jsonl`
  - answer 写入 `method_predictions.jsonl`
- artifact-only evaluation 默认忽略 retrieval artifact。

## 仍未完成 / 不要误判

- 尚未执行 retrieve-first 真实 API smoke。
- 未执行 full API 实验。
- 旧 `get_answer()` / `BaseMemorySystem` / `BaseResumableMemorySystem` /
  `BaseMemoryRetriever` 尚未删除，只是标为迁移期兼容。
- 统一 `LLMRuntimeConfig` / `LLMResponse` 还只是设计，尚未实现。
- registry / capability 减重还只是设计，尚未实施代码删除。
- 当前 working tree 很脏，包含多天 Codex/OpenCode 的大量改动；不要随手 `git add .`。

## 下次恢复建议

优先读取：

1. `AGENTS.md`
2. `docs/task-ledger.md`
3. `docs/current-roadmap.md`
4. 本文件
5. `docs/handoffs/2026-06-20-retrieve-first-implementation.md`

下一步建议顺序：

1. 做 git scope review：确认哪些改动属于 retrieve-first 主协议、哪些属于 OpenCode/并行/
   observability，准备分组 commit。
2. 如果用户确认 API 预算、run_id、method、benchmark、profile、turn/question/conversation
   limits 和 worker 数，再跑 retrieve-first 真实极小 smoke。
3. 真实 smoke 通过后，再考虑 legacy `get_answer()` / old base class 删除。
4. 再进入 `LLMRuntimeConfig` / `LLMResponse` 实现或 registry/capability 减重。

## 恢复时注意

- 不要重复大范围扫描全部历史 handoff；以 `AGENTS.md`、`docs/task-ledger.md` 和本文件为准。
- 不要启动真实 API，除非用户明确确认规模和 run_id。
- 不要删除或覆盖受保护实验：
  `outputs/memoryos-locomo-full-20260603/`。
- 不要恢复 PrefEval。
- 不要把 `data/`、`models/`、`outputs/`、`.env` 或 third-party 大资产加入 git。
