# 2026-06-20 Retrieve-First Implementation Handoff

## Completed

- Core protocol:
  - `BaseMemoryProvider.add(conversation)` 与 `retrieve(question)` 已进入 core 导出。
  - `RetrievalResult.formatted_context` 被定义为 framework reader 可直接注入 prompt 的
    method 输出。
  - 测试证据：`tests/test_retrieve_first_protocol.py` 已纳入 focused 回归。
- Framework reader:
  - `FrameworkAnswerReader` 支持默认/custom prompt template。
  - `generate_answer_with_trace()` 返回 answer、完整 prompt 和标准化 answer LLM metadata。
  - OpenAI-compatible answer client 当前仍固定使用 `gpt-4o-mini` 小步实现；统一
    `LLMRuntimeConfig` / `LLMResponse` 是后续任务。
- Runner, artifact, and resume:
  - generic prediction runner 已支持 `BaseMemoryProvider.retrieve()` ->
    `FrameworkAnswerReader` -> `method_predictions.jsonl`。
  - retrieval 结果单独写入 `retrieval_results.prediction.jsonl`，避免 answer artifact
    重复记录大段 memory context。
  - retrieve completed / answer pending 的 resume 已实现：answer 失败后，resume 会复用
    已落盘 retrieval，不重复调用 provider.retrieve。
  - framework answer 路径已记录 context tokens、answer latency、answer LLM token
    observation，并把 framework answer model 写入 model inventory。
  - answer-level artifact evaluation 默认忽略 retrieval artifact；F1/Judge 仍只使用
    answer prediction 和 evaluator private labels，除非未来 evaluator 显式声明需要
    retrieval context。
- Method adapter:
  - Mem0、A-Mem、LightMem、MemoryOS 均已继承 `BaseMemoryProvider` 并新增
    `retrieve(question) -> RetrievalResult`。
  - 四个 adapter 的旧 `get_answer()` 暂时作为 legacy compatibility wrapper 保留；
    新 method 接入不应再依赖该接口。
  - 注册表已让 LoCoMo / LongMemEval conversation-QA prediction 要求
    `CONVERSATION_ADD + MEMORY_RETRIEVAL`，四个内置 method 不再声明
    `ANSWER_GENERATION`。

## Verification

已执行并通过的 focused 验证包括：

```bash
uv run pytest tests/test_retrieve_first_protocol.py tests/test_method_registry.py tests/test_benchmark_registry.py -q
```

结果：`37 passed`。

```bash
uv run pytest tests/test_prediction_runner.py tests/test_prediction_cli.py tests/test_cost_calibration_smoke.py tests/test_main_cli.py -q
```

结果：`123 passed`。

```bash
uv run pytest tests/test_prediction_efficiency_observations.py tests/test_efficiency_analysis.py tests/test_framework_answer_reader.py -q
```

结果：`23 passed`。

```bash
uv run pytest tests/test_mem0_adapter.py tests/test_amem_adapter.py tests/test_lightmem_adapter.py tests/test_memoryos_adapter.py -q
```

结果：`189 passed, 2 warnings, 2 subtests passed`。

```bash
uv run pytest tests/test_mem0_source_compatibility.py tests/test_amem_registered_prediction.py tests/test_lightmem_registered_prediction.py tests/test_memoryos_registered_prediction.py -q
```

结果：`10 passed`。

```bash
uv run pytest tests/test_artifact_evaluation_runner.py tests/test_llm_judge_parsing.py -q
```

结果：`29 passed`。

最新文档/静态验证：

```bash
uv run pytest tests/test_documentation_standards.py -q
uv run python -m compileall -q src/memory_benchmark tests
git diff --check
```

结果：文档规范 `5 passed`，`compileall` exit 0，`git diff --check` exit 0。

未执行真实 API。

## Remaining Risks

- Legacy `get_answer()` removal timing:
  - 当前仍保留旧接口和兼容 wrapper，避免破坏历史 run 复查、旧测试和真实 smoke 前的
    fallback。
  - 删除前必须确认四个内置 method 的 retrieve-first 真实 API smoke 和 artifact-only
    evaluation 均稳定。
- Full API smoke:
  - retrieve-first 全链路真实 API smoke 仍需用户显式确认 method、benchmark、profile、
    run_id、conversation/question/turn limits 和 worker 数量。
  - 当前不要擅自启动付费 API 实验。
- LLM provider config:
  - 当前 framework answer reader 仍使用 `OpenAISettings` 小步实现。
  - 统一 `LLMRuntimeConfig` / `LLMResponse`、Anthropic/Gemini provider 和本地模型接入是
    后续任务。
- Registry/capability simplification:
  - 已记录减重方向，但尚未实施代码删除。
  - 短期继续保留轻量 registry；避免退回散落的 `if/else`。
