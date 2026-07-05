# 2026-06-21 状态同步：Mem0 v4、四路 smoke 观测与 LongMemEval 决策点

## 本次读取与核对

- 读取 `opencode/opencode_result.md` 和
  `opencode/opencode_result-6.20-02h-mem0-reference-date-gap.md`。
- 核对四个真实 smoke 输出目录：
  - `outputs/mem0-smoke-4c20t-w4-20260620/`
  - `outputs/memoryos-smoke-4c20t-w4-20260620/`
  - `outputs/amem-smoke-4c20t-w4-20260620/`
  - `outputs/lightmem-smoke-4c20t-w4-20260620/`
- 核对 Mem0 full-v4：
  `outputs/mem0-locomo-full-v4/`。
- 核对 A-Mem full-v2 历史结果：
  `outputs/完整的正确记录/amem-locomo-full-v2/`。

## 当前结论

### Retrieve-first 状态

代码层面的 retrieve-first 主协议已经完成：四个内置 method 均继承
`BaseMemoryProvider`，并实现 `add(conversation)` 与 `retrieve(question)`。Registered
prediction 已能在 `MEMORY_RETRIEVAL` capability 下使用 framework reader 生成最终 answer。

仍不能把它称为“真实 API 全链路已完成”，因为尚未执行四个 method 在 LoCoMo 上的
retrieve-first 真实 API smoke。下一步应先跑极小 smoke，确认：

- `add(conversation)` 正常写入。
- `retrieve(question)` 正常返回 `RetrievalResult.formatted_context`。
- framework reader 正常调用 answer LLM。
- `retrieval_results.prediction.jsonl`、`method_predictions.jsonl` 和 efficiency artifacts
  都正常写出。

### 四个 method 的观测证据

四个 4c20t-w4 LoCoMo smoke 都有 prediction efficiency observation：

| Run | Progress | Raw observation lines | 关键 summary |
| --- | --- | ---: | --- |
| `mem0-smoke-4c20t-w4-20260620` | 4/4 conversations, 4/4 questions | 311 | 有 memory build、retrieval、answer、injected context、LLM 和 embedding tokens |
| `memoryos-smoke-4c20t-w4-20260620` | 4/4 conversations, 4/4 questions | 171 | 有 memory build、retrieval、answer、injected context、LLM 和 embedding tokens |
| `amem-smoke-4c20t-w4-20260620` | 4/4 conversations, 4/4 questions | 244 | 有 memory build、retrieval、answer、injected context、answer/build/retrieval LLM tokens |
| `lightmem-smoke-4c20t-w4-20260620` | 4/4 conversations, 4/4 questions | 16 | 有 memory build、retrieval、answer、injected context、answer/build LLM tokens |

A-Mem full-v2 历史 run 没有 efficiency observation。它的 answer 质量结果可用，但不能用来
做成本/效率依据。A-Mem 当前 adapter 的观测能力以 4c20t-w4 smoke 为证据。

### Mem0 full-v4

`outputs/mem0-locomo-full-v4/` 已完成：

- 10/10 conversations。
- 1540/1540 questions。
- 已生成 F1、LLM judge 和 efficiency summary。

OpenCode 审计发现 Mem0 LoCoMo prompt 的全局 `reference_date` 只传年份；但每条检索记忆
自身带完整日期，因此当前记录为 informational，不判定 full-v4 作废。若未来修复，应在
conversation metadata 中保存最后 session 的完整日期，并用新 run_id 复验。

### LongMemEval-S 讨论点

retrieve-first 之后，最终 answer prompt 不再必须由 method 提供；framework reader 可以为
LongMemEval 提供统一 answer prompt。因此 A-Mem 和 MemoryOS 缺少 LongMemEval 专用
`get_answer()` prompt，不再自动意味着不能跑。

仍需先讨论并审计：

- LongMemEval framework reader answer prompt 用官方 prompt 还是项目默认 prompt。
- LongMemEval LLM judge prompt 和 judge model 的选择；当前项目默认仍是 `gpt-4o-mini`。
- `question_time` 如何进入 public `Question` 并被 adapter/retriever 使用。
- Mem0 和 LightMem 的官方 LongMemEval prompt/脚本可以作为参考。
- A-Mem 和 MemoryOS 是否能在当前 `retrieve(question)` 路径下正确处理 LongMemEval 的
  conversation、时间信息和检索格式。

### 第三方 stdout 与 isolated worker 进度

第三方 method 输出不能简单全局压掉。用户 method 的调试信息应保留到日志，并可按配置选择
是否显示在终端；框架要解决的是不让 stdout/warning/tqdm 破坏 Rich 进度区。

isolated worker 进度长时间不动，指的是协调层通常只能在 worker 完成一个 conversation 后
看到进度；长 conversation 的 add/retrieve/answer 阶段中，终端可能看似冻结。未来更合适的
方案是 worker 上报 heartbeat 或阶段事件，而不是强行给每个 worker 画复杂进度条。

## 文档同步

本次已更新：

- `docs/task-ledger.md`
- `docs/current-roadmap.md`
- `AGENTS.md`
- `README.md`

未执行真实 API。
