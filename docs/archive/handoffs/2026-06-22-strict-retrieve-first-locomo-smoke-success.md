# 2026-06-22 严格 Retrieve-First LoCoMo Smoke 成功交接

## 背景

上一轮 `retrieve-first-locomo-*-smoke-2c20t-20260622` 真实 API smoke 完成了
prediction/observation，但暴露 isolated worker 仍走 legacy `get_answer()` 的缺口，
因此不能作为严格 retrieve-first 链路证据。

该缺口已在 commit `4879abe` 中修复。本轮用户用新的 run id 重跑了四个 method 的
LoCoMo 极小真实 smoke。

## 本轮 run id

- `retrieve-first-strict-locomo-mem0-smoke-2c20t-w2-20260622`
- `retrieve-first-strict-locomo-memoryos-smoke-2c20t-w2-20260622`
- `retrieve-first-strict-locomo-amem-smoke-2c20t-w2-20260622`
- `retrieve-first-strict-locomo-lightmem-smoke-2c20t-w2-20260622`

规模：

- LoCoMo smoke profile
- 2 conversations
- 20 turns
- 2 isolated workers
- 每 conversation 1 question

## 核心结果

四个 run 均完成：

| Method | Conversations | Questions | `answer_prompts` lines | Observation lines |
| --- | ---: | ---: | ---: | ---: |
| A-Mem | 2/2 | 2/2 | 2 | 118 |
| LightMem | 2/2 | 2/2 | 2 | 8 |
| Mem0 | 2/2 | 2/2 | 2 | 150 |
| MemoryOS | 2/2 | 2/2 | 2 | 94 |

四个 run 均存在：

- `artifacts/answer_prompts.prediction.jsonl`
- `artifacts/method_predictions.jsonl`
- `artifacts/efficiency_observations.prediction.jsonl`
- `summaries/efficiency_overall.prediction.json`

四个 run 的 `logs/events.jsonl` event 序列均为：

```text
run_started
conversation_completed_isolated
conversation_completed_isolated
run_completed
```

结构化 event 中没有 failed/error/exception event。
`logs/run.log` 中没有 `ERROR`、`WARNING`、`Traceback`、`SSL`、`timeout` 或 `Retry` 关键词。

## Prompt Message 证据

`answer_prompts.prediction.jsonl` 均有 2 行，且每行都有非空 `prompt_messages`。

role 结构：

| Method | Prompt message roles |
| --- | --- |
| A-Mem | `system + user` |
| LightMem | `system` |
| Mem0 | `user` |
| MemoryOS | `system + user` |

这与当前 method adapter 的官方 prompt 结构预期一致。

## Efficiency Observation 证据

四个 run 的 efficiency summary 均包含：

- `memory_build_latency_ms`
- `retrieval_latency_ms`
- `answer_generation_latency_ms`
- `injected_memory_context_tokens`
- `retrieval_supported_count = 2`
- `retrieval_unsupported_count = 0`
- `llm_tokens`
- `embedding_tokens`

LLM token key：

- A-Mem：`answer:gpt-4o-mini`、`memory_build:amem-memory-build-llm`、
  `retrieval:amem-query-llm`
- LightMem：`answer:gpt-4o-mini`、`memory_build:lightmem-memory-llm`
- Mem0：`answer:gpt-4o-mini`、`memory_build:mem0-memory-llm`
- MemoryOS：`answer:gpt-4o-mini`、`memory_build:memoryos-chat-llm`、
  `retrieval:memoryos-chat-llm`

Embedding token key：

- Mem0：`memory_build:mem0-embedding`、`retrieval:mem0-embedding`
- MemoryOS：`memory_build:memoryos-embedding`、`retrieval:memoryos-embedding`
- A-Mem / LightMem：本轮没有 API embedding observation。

## 当前结论

严格 retrieve-first LoCoMo 极小真实 smoke 已通过。

该结论覆盖上一份 handoff 中的待重跑事项：

```text
docs/handoffs/2026-06-22-retrieve-first-locomo-smoke-and-isolated-fix.md
```

下一步可以进入：

1. 用 artifact-only 方式计算这四个 smoke 的 LoCoMo F1。
2. 讨论并执行 LongMemEval-S 最小 retrieve-first smoke。
3. 在用户确认预算和 run_id 后，扩大 LoCoMo / LongMemEval 的实验规模。
