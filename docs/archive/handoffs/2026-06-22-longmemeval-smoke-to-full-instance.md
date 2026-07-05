# 2026-06-22 LongMemEval Smoke 到单完整 Instance 交接

## 当前状态

用户已完成四个 method 在 LongMemEval-S `s_cleaned` 上的极小 smoke：

- `outputs/mem0-longmemeval-s-smoke-1c20r-20260622-s-cleaned`
- `outputs/memoryos-longmemeval-s-smoke-1c20r-20260622-s-cleaned`
- `outputs/amem-longmemeval-s-smoke-1c20r-20260622-s-cleaned`
- `outputs/lightmem-longmemeval-s-smoke-1c20r-20260622-s-cleaned`

检查结论：

- 四个 run 均为 `completed_conversations=1`、`completed_questions=1`。
- 四个 run 均写出：
  - `artifacts/method_predictions.jsonl`
  - `artifacts/evaluator_private_labels.jsonl`
  - `artifacts/answer_prompts.prediction.jsonl`
  - `artifacts/efficiency_observations.prediction.jsonl`
  - `summaries/efficiency_overall.prediction.json`
  - `summaries/efficiency_by_conversation.prediction.json`
  - `summaries/efficiency_by_question.prediction.json`
- LightMem 终端里的 `invalid source_id ... Auto-corrected` 是 LightMem 自身可恢复 warning，不是 run 失败。
- LightMem 的 `Token indices sequence length ... 638 > 512` 也是 warning，本次 run 未失败；如果完整 instance 频繁出现并影响结果，再回头审计 LightMem 本地模型/截断策略。
- 当前 20 round smoke 因历史过短，四个 method 均没答对 `Business Administration`，这不能说明 method 效果，只能说明链路可跑。

## Efficiency Observation 状态

四个 method 的 per-conversation 成本估算已有可用数据。

极小 smoke 的 per-conversation 总量摘要：

- Mem0:
  - memory build latency: `190085.83675 ms`
  - retrieval latency: `1339.56625 ms`
  - answer latency: `3644.92375 ms`
  - LLM tokens: answer `2819/49`，memory build `182994/3270`
  - embedding tokens: memory build `12166`，retrieval `7`
- MemoryOS:
  - memory build latency: `211249.30375 ms`
  - retrieval latency: `1521.231708 ms`
  - answer latency: `4006.630334 ms`
  - LLM tokens: answer `4256/55`，memory build `40523/2997`，retrieval `77/5`
  - embedding tokens: memory build `7349`，retrieval `1316`
- A-Mem:
  - memory build latency: `348881.13625 ms`
  - retrieval latency: `1529.160833 ms`
  - answer latency: `4171.778291 ms`
  - LLM tokens: answer `9581/120`，memory build `160623/7306`，retrieval `69/13`
  - embedding tokens: 当前 wrapper 未记录；需要后续确认 A-Mem 官方 embedding 是否本地/是否可观测
- LightMem:
  - memory build latency: `23525.037833 ms`
  - retrieval latency: `12.908709 ms`
  - answer latency: `2489.990709 ms`
  - LLM tokens: answer `786/40`，memory build `2310/790`

注意：A-Mem 原始 observation 已有 `stage=answer` 和 `stage=retrieval` 的 LLM token，并且 source 是 `api_usage`；但 `summaries/efficiency_by_question.prediction.json` 里对应 `llm_call_count/input/output` 为 0。这是 by-question 聚合逻辑或归因的小 bug，不是原始采集缺失。按 conversation 估算成本仍可用；如果后续要按 question 精确拆分，需要修复聚合。

## 下一步用户要运行的命令

目标是跑 LongMemEval-S `s_cleaned` 的 **1 个完整 instance**，用于估算 500 instances 成本。

必须使用：

- `--profile official-full`
- `--variant s_cleaned`
- `--max-new-conversations 1`
- `--confirm-api`
- `--confirm-full`

不要使用 `--smoke-turn-limit`、`--smoke-conversation-limit` 或 `--smoke-max-workers`，否则会继续走 smoke 裁剪语义。

这些命令使用稳定 run_id；跑完 1 个完整 instance 后，可用相同 run_id 加 `--resume` 继续跑。`max-new-conversations` 是“本次运行预算”，不是实验身份；后续 resume 可以改成 1、5、10 或直接省略来跑剩余全部。

## 继续跑的 resume 规则

如果第一次跑：

```bash
uv run memory-benchmark predict ... --run-id <same-run-id> --max-new-conversations 1
```

后续继续跑下一个完整 instance：

```bash
uv run memory-benchmark predict ... --run-id <same-run-id> --resume --max-new-conversations 1
```

后续一次推进 10 个 instance：

```bash
uv run memory-benchmark predict ... --run-id <same-run-id> --resume --max-new-conversations 10
```

后续跑完剩余所有 instance：

```bash
uv run memory-benchmark predict ... --run-id <same-run-id> --resume
```

## 待办

- 修 A-Mem `efficiency_by_question.prediction.json` 未聚合 answer/retrieval LLM token 的问题。
- 完整 instance 跑完后，用 `summaries/efficiency_by_conversation.prediction.json` 和 `efficiency_overall.prediction.json` 做 500 instances 成本估算。
- 如果 LightMem 完整 instance 仍大量出现 source_id warning，记录为 method-native warning，并考虑审计 LightMem extraction source_id prompt/解析策略。
- 如果任一 method 的完整 instance 因网络断连失败，优先检查已配置 retry/timeout 是否覆盖该调用点。
