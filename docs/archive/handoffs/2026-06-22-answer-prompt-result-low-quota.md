# 2026-06-22 AnswerPromptResult 重构低额度交接

时间：2026-06-22 00:26 CST

## 当前任务

用户最新决策：

- 不再让 `retrieve()` 返回“只是一段可填入默认 prompt 的 memory context”。
- 新协议改为 `AnswerPromptResult`。
- `retrieve(question)` 必须返回 method 内部构造好的完整 `answer_prompt`。
- framework answer LLM 直接把 `answer_prompt` 作为输入生成最终答案。
- method 想保留的调试信息、原始检索结果、拆分出的 memory context、prompt profile 等都放进 `metadata`。
- `get_answer()` 作为新 method 接入目标应逐步废弃；当前四个内置 method 的 legacy wrapper 暂时保留，避免一次性破坏历史测试和复查路径。

## 本轮已做的事情

### 1. 设计文档已补充

已更新：

- `docs/superpowers/specs/2026-06-20-retrieve-first-memory-module-design.md`

新增的核心结论：

- 很多 benchmark 没有官方统一 answer prompt，answer prompt 设计事实上也是 method 的一部分。
- 新链路是：

```text
add(conversation)
retrieve(question) -> AnswerPromptResult.answer_prompt
framework answer LLM(answer_prompt) -> answer
evaluate(answer)
```

- `AnswerPromptResult.answer_prompt` 是核心字段。
- `metadata["answer_context"]` 只在 method 能稳定拆出“纯记忆上下文”时可选提供，用于 efficiency 里的 `injected_memory_context_tokens`。
- `metadata["retrieved_memories"]`、`metadata["raw_items_ref"]`、`metadata["answer_prompt_profile"]` 等都是可选调试/报告字段，不进入主协议硬字段。

### 2. TDD 红测已写并跑过

已改测试：

- `tests/test_retrieve_first_protocol.py`
- `tests/test_framework_answer_reader.py`

一开始运行：

```bash
uv run pytest tests/test_retrieve_first_protocol.py tests/test_framework_answer_reader.py -q
```

出现 `ImportError: cannot import name 'AnswerPromptResult'`，符合预期红测。

### 3. core / reader 已迁移

已改：

- `src/memory_benchmark/core/entities.py`
  - 新增/替换为 `AnswerPromptResult`。
  - 当前字段为 `question_id`、`conversation_id`、`answer_prompt`、`metadata`。
- `src/memory_benchmark/core/__init__.py`
  - 导出 `AnswerPromptResult`。
  - 不再导出旧 `RetrievalResult`。
- `src/memory_benchmark/core/interfaces.py`
  - `BaseMemoryProvider.retrieve()` 返回 `AnswerPromptResult`。
  - 历史 `BaseMemoryRetriever.retrieve()` 也同步返回 `AnswerPromptResult`，但仍应视作 legacy。
- `src/memory_benchmark/readers/answer.py`
  - `FrameworkAnswerReader` 现在直接使用 `retrieval.answer_prompt.strip()` 调 answer LLM。
  - 不再把 question + formatted_context 拼进默认 prompt。
  - 空 prompt 会 fail closed，错误字段为 `answer_prompt`。
  - `AnswerPromptTemplate` 仍暂时保留，后续再决定是否删除或降级为 future/legacy 工具。

验证：

```bash
uv run pytest tests/test_retrieve_first_protocol.py tests/test_framework_answer_reader.py -q
```

结果：`10 passed`。

### 4. runner 主体已迁移到 answer prompt artifact

已改：

- `src/memory_benchmark/runners/prediction.py`

主要变化：

- `paths.answer_prompts_path` 成为 retrieve-first 中间 artifact。
- 单题 retrieve-first 路径现在写：

```json
{
  "question_id": "...",
  "conversation_id": "...",
  "answer_prompt": "...",
  "metadata": {...}
}
```

- answer 失败时，已完成的 `answer_prompt` 会先落盘；resume 时可复用，不重复调用 `provider.retrieve()`。
- `injected_memory_context_tokens` 现在只从 `AnswerPromptResult.metadata["answer_context"]` 统计；如果没有该字段则写 `null/unsupported`，不要拿完整 prompt 冒充 memory-only context。

注意：

- 函数名/变量名里仍有一些 `retrieval` 语义，例如 `_answer_question_retrieve_first`、`batch.retrievals`、`_RetrieveFirstAnswerError`。这不是功能错误，但后续清理旧内容时可以统一改名。
- `ExperimentPaths.retrieval_results_path` 仍保留为 legacy property，当前新路径是 `answer_prompts_path`。

### 5. 四个 method adapter 已迁移主体

已改：

- `src/memory_benchmark/methods/mock.py`
- `src/memory_benchmark/methods/mem0_adapter.py`
- `src/memory_benchmark/methods/amem_adapter.py`
- `src/memory_benchmark/methods/lightmem_adapter.py`
- `src/memory_benchmark/methods/memoryos_adapter.py`

当前语义：

- Mem0:
  - `retrieve()` 调 Mem0 search。
  - 用官方 LoCoMo/LongMemEval reader prompt 逻辑构造完整 prompt。
  - 返回 `AnswerPromptResult.answer_prompt`。
  - `metadata` 包含 `answer_context`、`retrieved_memories`、`retrieved_memory_count`、`top_k`、`answer_prompt_profile`。
  - `get_answer()` 暂时作为 wrapper：调用 `retrieve()` 后把完整 prompt 发给旧 LLM client。
- A-Mem:
  - `retrieve()` 保留 query keyword generation、category k、retrieval observation。
  - 调 `_build_answer_prompt(question, memory_context)` 构造完整 prompt。
  - `metadata["answer_context"]` 保存 memory context。
- LightMem:
  - LoCoMo 保留专门化 `search_locomo.py` 风格检索。
  - LongMemEval 保留 `LightMemory.retrieve()` online 路径。
  - `retrieve()` 调 `_build_answer_prompt(question, memories)` 构造完整 prompt。
  - `metadata` 中保留 `answer_context` 和调试用 `retrieved_memories`。
- MemoryOS:
  - `retrieve()` 调官方 eval `retrieval_system.retrieve(...)`。
  - 新增 `_build_memoryos_answer_prompt(...)`，按官方 `generate_system_response_with_meta()` 的 prompt 结构构造完整 prompt，但不调用 LLM。
  - `get_answer()` 仍保留官方原行为，避免破坏历史复查路径。

### 6. 已通过的 focused 验证

已跑并通过：

```bash
uv run pytest tests/test_retrieve_first_protocol.py tests/test_framework_answer_reader.py -q
```

结果：`10 passed`。

已跑并通过：

```bash
uv run pytest \
  tests/test_prediction_runner.py::test_runner_uses_retrieve_first_provider_and_framework_reader \
  tests/test_prediction_runner.py::test_shared_mock_provider_uses_framework_reader \
  tests/test_prediction_runner.py::test_resume_reuses_completed_retrieval_when_answer_failed \
  tests/test_mem0_adapter.py::test_mem0_retrieve_returns_answer_prompt \
  tests/test_framework_answer_reader.py \
  tests/test_retrieve_first_protocol.py \
  -q
```

结果：`14 passed`。

## 本轮中断时的未完成验证

曾启动：

```bash
uv run pytest tests/test_mem0_adapter.py tests/test_amem_adapter.py tests/test_lightmem_adapter.py tests/test_memoryos_adapter.py -q
```

第一次运行发现 9 个失败，已按错误修复：

- Mem0 `get_answer()` 中旧变量 `memories` 未定义，已改为从 `prompt_result.metadata` 读取。
- A-Mem / LightMem / MemoryOS adapter 测试仍按旧 `formatted_context` 断言，已改为断言完整 `answer_prompt` 与 `metadata["answer_context"]`。

修完后重新运行同一命令，命令输出到中途显示：

```text
WARN Retry attempt #0. Sleeping ...
WARN Retry attempt #1. Sleeping ...
.............................
```

但在上下文压缩前没有拿到最终退出结果。因此恢复时必须重新跑该命令，不能声称四 adapter focused 已全部通过。

建议恢复后第一条验证命令：

```bash
uv run pytest tests/test_mem0_adapter.py tests/test_amem_adapter.py tests/test_lightmem_adapter.py tests/test_memoryos_adapter.py -q
```

## 当前已知旧内容残留

低额度下只做交接，没有大面积文档替换。恢复时需要清理这些当前文档中的旧说法：

- `README.md`
  - 仍写 `retrieve(public Question) -> formatted_context`。
  - 接入示例仍 import `RetrievalResult`。
- `AGENTS.md`
  - 已在顶部补当前 handoff 指针，但中段仍有大量旧 `RetrievalResult/formatted_context` 说明。
- `src/memory_benchmark/core/Readme.md`
  - 仍有 `RetrievalResult` 小节。
- `docs/current-roadmap.md`
  - Phase K 仍描述 `formatted_context`。
- `docs/method-interface-inventory.md`
  - 四个 method 当前 adapter 状态仍写 `RetrievalResult/formatted_context`。
- `docs/task-ledger.md`
  - retrieve-first 已关闭项仍写旧字段。

恢复时先改“当前状态类文档”，不要批量重写历史 handoff / 旧 plan 里的旧术语。历史文档保留当时事实即可。

当前扫描命令：

```bash
rg -n "RetrievalResult|formatted_context|retrieval_results\\.prediction|retrieval_results_path|answer_prompts_path|AnswerPromptResult" \
  src tests docs AGENTS.md README.md -g '*.*'
```

扫描结果显示：

- `src/` 中主代码已基本切到 `AnswerPromptResult`。
- `src/memory_benchmark/storage/experiment_paths.py` 仍有 legacy `retrieval_results_path`。
- `src/memory_benchmark/methods/amem_adapter.py` 中 `runtime.memories` 是 A-Mem 官方内部变量，不是旧协议残留。
- 大量旧残留主要在 README、AGENTS、docs 和历史 handoff/plan。

## 下一步建议顺序

1. 先跑四 adapter focused：

```bash
uv run pytest tests/test_mem0_adapter.py tests/test_amem_adapter.py tests/test_lightmem_adapter.py tests/test_memoryos_adapter.py -q
```

2. 如果失败，先按失败栈修复，不要继续做文档。

3. 再跑 runner / registered focused：

```bash
uv run pytest \
  tests/test_prediction_runner.py \
  tests/test_prediction_efficiency_observations.py \
  tests/test_artifact_evaluation_runner.py \
  tests/test_amem_registered_prediction.py \
  tests/test_lightmem_registered_prediction.py \
  tests/test_memoryos_registered_prediction.py \
  tests/test_method_registry.py \
  tests/test_main_cli.py \
  tests/test_cost_calibration_smoke.py \
  -q
```

4. 然后清理当前文档：

- `README.md`
- `AGENTS.md`
- `docs/current-roadmap.md`
- `docs/task-ledger.md`
- `docs/method-interface-inventory.md`
- `src/memory_benchmark/core/Readme.md`

5. 重新跑扫描：

```bash
rg -n "RetrievalResult|formatted_context|retrieval_results\\.prediction" \
  src tests README.md AGENTS.md docs/current-roadmap.md docs/task-ledger.md docs/method-interface-inventory.md src/memory_benchmark/core/Readme.md -g '*.*'
```

目标：

- 当前状态文档和代码不再把主协议描述为 `RetrievalResult.formatted_context`。
- 历史 handoff / 历史 plan 可以保留旧术语。

6. 最后跑：

```bash
uv run pytest tests/test_documentation_standards.py -q
uv run python -m compileall -q src/memory_benchmark tests
git diff --check
```

## 禁止事项

- 不要启动真实 API smoke。
- 不要运行 full 实验。
- 不要改动受保护实验目录 `outputs/memoryos-locomo-full-20260603/`。
- 不要批量删除 legacy `get_answer()`，除非先写单独计划和测试。
- 不要把历史 handoff 里的 `RetrievalResult` 全部强行改掉；那些是历史记录。

## 2026-06-22 恢复后更新

本 handoff 中“下一步建议顺序”的收尾工作已经完成。

最新验证：

```bash
uv run pytest tests/test_mem0_adapter.py tests/test_amem_adapter.py tests/test_lightmem_adapter.py tests/test_memoryos_adapter.py -q
```

结果：`189 passed, 2 warnings, 2 subtests passed`。

```bash
uv run pytest \
  tests/test_prediction_runner.py \
  tests/test_prediction_efficiency_observations.py \
  tests/test_artifact_evaluation_runner.py \
  tests/test_amem_registered_prediction.py \
  tests/test_lightmem_registered_prediction.py \
  tests/test_memoryos_registered_prediction.py \
  tests/test_method_registry.py \
  tests/test_main_cli.py \
  tests/test_cost_calibration_smoke.py \
  -q
```

结果：`146 passed`。

```bash
uv run pytest tests/test_prediction_runner.py::test_experiment_paths_include_answer_prompt_artifact tests/test_artifact_evaluation_runner.py -q
```

结果：`20 passed`。

```bash
uv run pytest tests/test_documentation_standards.py -q
uv run python -m compileall -q src/memory_benchmark tests
git diff --check
```

结果：文档规范 `5 passed`，`compileall` exit 0，`git diff --check` exit 0。

当前代码和当前状态文档扫描：

```bash
rg -n "RetrievalResult|formatted_context|retrieval_results\\.prediction|retrieval_results_path" \
  src tests README.md AGENTS.md docs/current-roadmap.md docs/task-ledger.md docs/method-interface-inventory.md src/memory_benchmark/core/Readme.md -g '*.*'
```

结果：无命中。历史 handoff / 历史 plan 中的旧术语未批量修改。

## 当前判断

核心代码、reader、runner 和四个 method adapter 主体已经切向 `AnswerPromptResult.answer_prompt`，
当前状态文档已同步。尚未执行真实 API smoke，也尚未删除 legacy `get_answer()` 兼容路径。
