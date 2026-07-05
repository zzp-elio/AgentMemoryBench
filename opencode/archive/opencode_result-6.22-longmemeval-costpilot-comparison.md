# OpenCode 执行记录 — 2026-06-22 LongMemEval-S 四 Method 1-conv Cost Pilot 横向对比

## 概览

四 method × LongMemEval-S `s_cleaned` `official-full` profile，各跑 1 conversation（`--max-new-conversations 1`），评测 LLM judge（`longmemeval-judge` compact），计算 GPT-4o-mini 成本并估算 500 conversation 全量花费。

## 命令

```bash
uv run memory-benchmark predict --root . --method {mem0,amem,lightmem,memoryos} \
  --benchmark longmemeval --variant s_cleaned --profile official-full \
  --run-id {method}-longmemeval-s-1conv-costpilot-20260622 \
  --confirm-api --confirm-full --max-new-conversations 1
```

评测：
```bash
uv run memory-benchmark evaluate --root . \
  --run-id {method}-longmemeval-s-1conv-costpilot-20260622-s-cleaned \
  --metric longmemeval-judge --judge-profile compact --confirm-api
```

**注意**: framework 自动追加 `-s_cleaned` 后缀到 run_id。

## 横向对比

| | LightMem | Mem0 | MemoryOS | A-Mem |
|---|---|---|---|---|
| **Judge** | 1/1 ✅ | 1/1 ✅ | 1/1 ✅ | 1/1 ✅ |
| **Memory build tokens** | 35K | 2.60M | 805K | 2.47M |
| **LLM 调用次数 (build)** | 19 | 277 | 1,362 | 1,687 |
| **Answer tokens** | 2K | 5K | 8K | 10K |
| **Embedding API** | 无(本地) | 147K tok | 无(本地) | 无(本地) |
| **GPT-4o-mini $/conv** | **$0.011** | **$0.454** | **$0.188** | **$0.460** |
| **500 conv 估算** | **$6** | **$227** | **$94** | **$230** |
| **耗时** | 5min | 48min | 72min | 87min |

### GPT-4o-mini 定价

- 输入: $0.165/MTok
- 输出: $0.66/MTok
- 缓存输入: $0.0825/MTok
- 批量输入: $0.0825/MTok
- 批量输出: $0.33/MTok

### 总成本估算

四 method × 500 conversation GPT-4o-mini 费用:

| Method | 500 conv |
|--------|----------|
| LightMem | $6 |
| Mem0 | $227 |
| MemoryOS | $94 |
| A-Mem | $230 |
| **合计** | **$557** |

Mem0 额外有 text-embedding-3-small API 费用（147K tok/conv），未包含在上表。

## 各 Method 详细数据

### LightMem

- **耗时**: 5min (memory build 315s)
- **模型**: gpt-4o-mini (memory + answer)
- **Memory build LLM**: 19 calls, 25,640 in + 9,805 out
- **Answer LLM**: 1 call, 2,062 in + 9 out
- **Embedding**: 本地 all-MiniLM-L6-v2, 0 API 调用
- **Retrieval**: 17ms (本地 Qdrant 向量检索)
- **Answer generation**: 1.7s

### Mem0

- **耗时**: 48min (memory build 47.9min)
- **模型**: gpt-4o-mini (memory + answer)
- **Memory build LLM**: 277 calls, 2,551,756 in + 48,955 out
- **Answer LLM**: 1 call, 5,183 in + 53 out
- **Embedding API**: text-embedding-3-small, 827 calls, 147,377 tokens (mem build) + 1 call 7 tokens (retrieval)
- **Retrieval**: 1.2s
- **Answer generation**: 4.0s

### MemoryOS

- **耗时**: 72min (memory build 71.8min)
- **模型**: gpt-4o-mini (memory + answer)
- **Memory build LLM**: 1,361 calls, 696,203 in + 109,204 out
- **Retrieval LLM**: 1 call, 77 in + 5 out
- **Answer LLM**: 1 call, 8,285 in + 30 out
- **Embedding**: 本地 all-MiniLM-L6-v2, 921 calls (memory build + retrieval), 0 API 费用
- **Retrieval latency**: 1.5s
- **Answer generation**: 4.0s

### A-Mem

- **耗时**: 87min (memory build 86.8min)
- **模型**: gpt-4o-mini (memory + query + answer)
- **Memory build LLM**: 1,686 calls, 2,372,378 in + 101,901 out
- **Retrieval (query keyword) LLM**: 1 call, 69 in + 13 out
- **Answer LLM**: 1 call, 9,525 in + 9 out
- **Embedding**: 本地 all-MiniLM-L6-v2, 0 API 调用
- **Retrieval**: 1.5s
- **Answer generation**: 4.2s

## 分析

1. **LightMem $0.01/conv 极其便宜**：batch 记忆处理 + 本地 embedding，仅 19 次 LLM 调用。500 conv 只需 $6。

2. **Mem0 $0.45/conv 最贵的主要开销在 memory build**：每 turn 调 LLM 做 memory extraction，277 次调用消耗 2.6M tokens。额外还有 embedding API 费用。

3. **MemoryOS $0.19/conv 中等**：1,361 次 LLM 调用但每次 token 较少（平均 512 in/turn），总 tokens 805K。

4. **A-Mem $0.46/conv 最贵**：1,687 次 LLM 调用是四 method 最多（每 turn memory extraction），总 tokens 2.47M。

5. **四 method 全部 1/1 correct**：单 conversation 无法得出统计结论，仅确认链路正常。

6. **A-Mem 86.8min 最长**：1,687 次 LLM API 调用的网络延迟叠加 + 本地 embedding。

## 已知注意事项

- 单 conversation 成本波动大（conversation e47becba 可能不是全 dataset 的代表性样本），500 conv 估算供参考
- Mem0 embedding API 费用未计入（需确认 text-embedding-3-small 实际定价）
- Judge 评测 token 消耗极小（1 次 LLM 调用 per question），未单列
- 所有 method 均有 timeout=60s + max_retries=8 兜底
