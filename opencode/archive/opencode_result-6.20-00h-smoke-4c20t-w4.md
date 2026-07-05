# 2026-06-20 00:00 UTC — 四 method LoCoMo 4c20t-w4 smoke 验证

## 1. 读了哪些文件

- `opencode/opencode_result.md`：文档规则
- `docs/task-ledger.md`：当前 P0 任务清单，确认 Mem0 conversation observation 和 LightMem memory-build LLM usage 两项为 `partially_closed`，需真实 smoke 复验
- `docs/handoffs/2026-06-20-observability-fixes-mem0-lightmem.md`：Codex 修复内容交接
- `docs/handoffs/2026-06-20-low-quota-opencode-handoff.md`：低额度交接，明确下一步跑极小 smoke
- `docs/handoffs/2026-06-20-locomo-smoke-question-limit.md`：question-limit 修复交接
- `outputs/mem0-locomo-smoke10c-10t-w10-20260620/summaries/efficiency_overall.prediction.json`：旧 run 确认 `memory_build_latency_ms.count=0`
- `outputs/lightmem-api-smoke-v2/artifacts/efficiency_observations.prediction.jsonl`：旧 run 确认无 memory_build LLM observation
- 四个新 run 的 `artifacts/efficiency_observations.prediction.jsonl` 和 `summaries/efficiency_overall.prediction.json`：验证数据来源

## 2. 根因

本次是观测验证任务，不涉及新 bug 诊断。此前两个 P0 缺口的根因已由 Codex 修复：

- **Mem0 conversation observation 缺失**：isolated worker 在 `conversation_scope` 退出前读取 `conv_scope.records`，而 collector 只在 scope 正常退出后冻结 records
- **LightMem memory-build LLM usage 缺失**：LightMem 官方 `ThreadPoolExecutor.map()` 不传播 ContextVar scope，子线程中 observer 看到的 `active_scope_type()` 为空

本次只验证修复后代码在真实 API smoke 中是否正确记录。

## 3. 修改了哪些文件

**无代码修改。** 本次只运行实验、记录结果。open code 目录外未修改任何文件。

open code 目录内新建：
- `opencode/opencode_result-6.20-00h-smoke-4c20t-w4.md`（本文件）

open code 目录内修改：
- `opencode/opencode_result.md`：更新"最新结果"指向本文件

## 4. 跑了哪些实验，完整结果

命令（四 method 依次执行）：

```bash
uv run memory-benchmark predict \
  --method {mem0|memoryos|amem|lightmem} --benchmark locomo --profile smoke \
  --run-id {method}-smoke-4c20t-w4-20260620 \
  --smoke-conversation-limit 4 --smoke-turn-limit 20 \
  --smoke-max-workers 4 --confirm-api
```

### 结果总览

| Method | Conversations | Questions | Status |
|--------|--------------|-----------|--------|
| Mem0 | 4/4 | 4/4 | ✅ |
| MemoryOS | 4/4 | 4/4 | ✅ |
| A-Mem | 4/4 | 4/4 | ✅ |
| LightMem | 4/4 | 4/4 | ✅ |

### 效率观测覆盖

| Observation | Mem0 | MemoryOS | A-Mem | LightMem |
|------------|------|----------|-------|----------|
| conversation_efficiency | 4 | 4 | 4 | 4 |
| llm_call / memory_build (api_usage) | 80 | 89 | 228 | 4 |
| llm_call / retrieval (api_usage) | — | 4 | 4 | — |
| llm_call / answer (api_usage) | 4 | 4 | 4 | 4 |
| embedding_call / memory_build | 209 | 53 | — | — |
| embedding_call / retrieval | 10 | 13 | — | — |
| question_efficiency | 4 | 4 | 4 | 4 |
| **Total** | **311** | **171** | **244** | **16** |

### 关键指标对比

| 指标 | Mem0 | MemoryOS | A-Mem | LightMem |
|------|------|----------|-------|----------|
| memory build mean (ms) | 134,611 | 62,208 | 153,480 | 32,281 |
| answer mean (ms) | 7,027 | 1,934 | 2,529 | 2,728 |
| injected context tokens (mean) | 492 | 865 | 7,456 | 7,088 |
| answer LLM input tokens | 8,764 | 4,752 | 30,149 | 3,834 |

### P0 缺口验证结果

| 缺口 | 旧 run | 新 run | 结论 |
|------|--------|--------|------|
| Mem0 memory_build_latency_ms.count=0 | `mem0-locomo-smoke10c-10t-w10-20260620` | count=4 | ✅ 已修复 |
| LightMem 无 memory-build LLM | `lightmem-api-smoke-v2` | api_usage=4 | ✅ 已修复 |

### 离线测试

本次为真实 API smoke，未跑 pytest。此前 Codex 已冻存的离线验证基线：

- `114 passed, 2 warnings`（focused: prediction_runner + lightmem_adapter + amem_adapter + mem0_adapter + method_registry）
- `5 passed`（文档规范）
- `compileall` exit 0

## 5. 已知风险或未解决问题

1. **Mem0 embedding token 计数为 `tokenizer_estimate`**：209 次 embedding 调用均无法从 API response 拿到真实 usage（ohmygpt OpenAI-compatible embedding endpoint 不返回 usage）。MemoryOS 的 embedding token 计数为 `method_native`，来源不同。不影响费用计算（embedding 价格通常按 token 计），但两者来源不一致会在离线价格聚合时产生不同行为。
2. **A-Mem memory_build LLM 调用 228 次**：远超其他 method。符合 A-Mem 算法特征（按 turn 逐条调用 LLM 生成 memory），但如果在更大规模上保持此调用密度，memory build 环节的 API 费用和延迟会显著高于其他 method。
3. **LightMem 观测数量少（16 条）**：无 embedding_call（本地模型），memory_build LLM 只有 4 条（LoCoMo OP-update 按 conversation 批处理）。不代表观测缺失。
4. **`--question-limit-per-conversation` 本次未传**：默认 1 题，符合预期。Codex 修复后 smoke adapter 保留所有 evidence 覆盖问题，runner 可正常按 budget 裁剪，本次未显式测试该路径。

## 6. 卡点与下一步建议

**无卡点。** 本次两个 P0 缺口均已通过真实 API smoke 验证。建议：

1. 将 `docs/task-ledger.md` 中 Mem0 isolated worker observation 和 LightMem OP-update observation 从 `partially_closed` 更新为 `closed`
2. 更新 `docs/current-roadmap.md` 和 `AGENTS.md` 断点
3. 四个 method 的 prediction efficiency 覆盖矩阵已在此次验证中自然完成，可在 task-ledger 中关闭对应 P0
4. 下一步可考虑推进 Mem0 official-full 重跑（retry/timeout 已补）
