# 2026-06-22 AnswerLLMSettings 实现交接

时间：2026-06-22 11:00 CST

## 本轮完成

在 `retrieve() -> AnswerPromptResult.answer_prompt -> framework answer LLM` 主链路下，
answer LLM 参数已从隐式 SDK 默认值改为显式配置：

- 新增 `AnswerLLMSettings`，字段包括：
  - `model`
  - `message_role`
  - `temperature`
  - `max_tokens`
  - `top_p`
  - `timeout_seconds`
  - `max_retries`
- 新增 `resolve_answer_llm_settings()`，按 method × benchmark 解析当前内置组合的官方参数：
  - Mem0 LoCoMo / LongMemEval: `temperature=0.0`, `max_tokens=4096`, `message_role=user`
  - A-Mem LoCoMo: `temperature=0.7`, `max_tokens=1000`, `message_role=user`
  - LightMem LoCoMo: `temperature=0.0`, `message_role=system`
  - LightMem LongMemEval: `temperature=0.0`, `top_p=0.8`, `max_tokens=2000`, `message_role=user`
  - MemoryOS LoCoMo: `temperature=0.7`, `max_tokens=2000`, `message_role=user`
- `OpenAICompatibleAnswerLLMClient` 现在接收 API 连接配置 `OpenAISettings` 和
  请求参数配置 `AnswerLLMSettings`。
- chat completions 请求只传非 `None` 的 `temperature`、`max_tokens`、`top_p`，避免把
  未设置字段猜成官方参数。
- registered prediction 的 method manifest 已写入 `answer_reader.answer_parameters`。
- framework answer model inventory 使用 `answer_settings.model`。
- README、AGENTS、current-roadmap、task-ledger 和 method 参数审计文档已同步当前状态。

## 本轮测试

已执行：

```bash
uv run pytest tests/test_framework_answer_reader.py -q
uv run pytest tests/test_prediction_cli.py::test_registered_prediction_builds_framework_answer_reader -q
uv run pytest tests/test_memoryos_registered_prediction.py tests/test_amem_registered_prediction.py tests/test_lightmem_registered_prediction.py -q
uv run pytest tests/test_framework_answer_reader.py tests/test_prediction_cli.py tests/test_memoryos_registered_prediction.py tests/test_amem_registered_prediction.py tests/test_lightmem_registered_prediction.py -q
uv run pytest tests/test_method_registry.py tests/test_main_cli.py tests/test_cost_calibration_smoke.py tests/test_prediction_efficiency_observations.py -q
```

结果：

- framework reader focused: `10 passed`
- registered reader focused: `1 passed`
- method registered focused: `9 passed`
- wider reader/registered focused: `47 passed`
- registry/main/calibration/efficiency focused: `63 passed`

最终收口命令：

```bash
uv run pytest tests/test_documentation_standards.py -q
uv run python -m compileall -q src/memory_benchmark tests
git diff --check
```

结果：

- 文档规范：`5 passed`
- `compileall`: exit 0
- `git diff --check`: exit 0

## 未做

- 未执行真实 API smoke。
- 未实现统一 `LLMRuntimeConfig` / `LLMResponse` 多 provider 设计。
- 未删除 legacy `get_answer()` / `BaseMemorySystem` 兼容路径。
- 未启动任何 full 实验。

## 下一步建议

1. 跑最终收口验证。
2. 若验证通过，检查 git diff，考虑提交当前 retrieve-first + answer LLM settings 大批改动。
3. 用户确认 API 预算、run_id、conversation/question/turn limits 和 worker 数后，启动
   四 method LoCoMo retrieve-first 极小真实 API smoke。
