# 2026-06-21 LLM Provider 与 Prompt 配置设计交接

## 本次目标

用户要求参考 `第三方框架参考/` 下的 supermemoryai-memorybench 和 EverOS 设计资料，
结合我们当前 retrieve-first 重构，明确未来 LLM/provider/prompt 应如何配置。

## 已读取资料

- `第三方框架参考/supermemoryai讨论.md`
- `第三方框架参考/supermemoryai-memorybench.md`
- `第三方框架参考/EVALUATION_ARCHITECTURE.md`
- `docs/superpowers/specs/2026-06-20-retrieve-first-memory-module-design.md`
- `docs/superpowers/plans/2026-06-20-retrieve-first-memory-module.md`

## 已完成

- 新增设计文档：
  `docs/superpowers/specs/2026-06-21-llm-provider-config-design.md`
- 更新项目入口：
  - `AGENTS.md`
  - `README.md`
  - `docs/current-roadmap.md`
  - `docs/task-ledger.md`

## 核心结论

- 框架内部统一定义 `LLMClient -> LLMResponse`。
- 第一版只实现 `openai_compatible` provider。
- OpenAI-compatible 同时覆盖 OpenAI、ohmygpt、DeepSeek 兼容接口和本地
  OpenAI-compatible server，如 vLLM/Ollama/LM Studio。
- Anthropic/Gemini 作为后续原生 provider。
- 进程内 Hugging Face Transformers provider 暂不进入 Phase 1；若需要本地开源模型，
  优先通过本地 OpenAI-compatible server 接入。
- `LLMResponse` 应包含稳定字段：`text/provider/model/usage/request_id/finish_reason/latency_ms`。
- 原 SDK response 可保留在 `raw_response` 供 debug，但不默认写入标准 artifact。
- 用户自定义黑盒 method 不强制使用框架 LLM client；仍只需实现 `add()` / `retrieve()`。

## 与当前 Task 6 的关系

当前 Task 6 已部分实现：

- `OpenAICompatibleAnswerLLMClient(settings=OpenAISettings)`
- `load_answer_prompt_template(...)`
- CLI `--answer-prompt-file`
- CLI `--answer-prompt-profile`

这可以作为 Phase 1 小步继续推进。不要为了多 provider 设计中断当前 retrieve-first
Task 6。后续应先完成 Task 6 接线，再单独做 `LLMRuntimeConfig` / `LLMResponse` 迁移。

## 未完成

- 尚未实现 `memory_benchmark.llms` 包。
- 尚未把 `FrameworkAnswerReader` 从纯字符串 client 改为消费 `LLMResponse`。
- 尚未把 LLM judge 或四个内置 method 的内部 LLM 调用迁移到统一 LLM client。
- 尚未实现 Anthropic/Gemini/local HF provider。

## 验证

本次只改文档，未执行真实 API。

建议恢复后先运行：

```bash
uv run pytest tests/test_documentation_standards.py -q
git diff --check -- AGENTS.md README.md docs/current-roadmap.md docs/task-ledger.md docs/superpowers/specs/2026-06-21-llm-provider-config-design.md docs/handoffs/2026-06-21-llm-provider-config-design.md
```
