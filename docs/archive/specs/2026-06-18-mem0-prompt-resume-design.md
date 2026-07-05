# Mem0 Prompt 对齐与 Resume 分层设计

## 背景

本切片吸收 `docs/opencode-suggestions/` 中经源码核验后可采纳的两点：

- Mem0 的回答生成应使用其 vendored `memory-benchmarks` 中的 benchmark-specific prompt。
- method resume 应按最小写入单元是否“完成即持久化”分层，不强行统一 turn 级断点。

本切片不启动真实 API，不改变统一 `BaseMemorySystem` / `BaseResumableMemorySystem` 接口。

## Mem0 Prompt 设计

Mem0 OSS 本体没有可用的 `answer(question)`；其 `chat()` 未实现。Mem0 官方
`memory-benchmarks` 的 conversation-QA 流程是：

```text
Memory.search(...) -> get_answer_generation_prompt(...) -> answerer LLM
```

因此 adapter 的 `get_answer()` 保持检索逻辑不变，只替换 reader prompt：

- LoCoMo：调用 `memory-benchmarks/benchmarks/locomo/prompts.py::get_answer_generation_prompt`。
- LongMemEval：调用 `memory-benchmarks/benchmarks/longmemeval/prompts.py::get_answer_generation_prompt`。
- 未知 benchmark：保留原 generic fallback，避免把 LoCoMo prompt 错套到未来 task family。

benchmark 分支依据：

- conversation metadata 的 `source_path/source_format/variant`。
- question category 属于 LoCoMo 数字类别时使用 LoCoMo。
- question category 属于 LongMemEval question types 或存在 `question_time` 时使用 LongMemEval。

因为 adapter 行为依赖这两个 prompt 文件，Mem0 source identity 需要包含：

- `memory-benchmarks/benchmarks/locomo/prompts.py`
- `memory-benchmarks/benchmarks/longmemeval/prompts.py`

Mem0 官方 LongMemEval runner 使用 `CHUNK_SIZE=2`，即 user+assistant pair 级写入；
这和 LoCoMo-safe turn-level resume 不一致。用户已确认：Mem0 仍需支持
LongMemEval 实验，但 LongMemEval 只做 conversation-level resume，不实现 turn-level
resume。adapter 因此按 benchmark 分流：

- LoCoMo：`CHUNK_SIZE=1`，启用 `add_from_turn()` 和 turn-level checkpoint。
- LongMemEval：`CHUNK_SIZE=2`，`supports_turn_resume()` 返回 False，runner 退回
  完整 `add([conversation])` 和 conversation-level resume。

## Resume 分层设计

采用以下策略：

| Method | Resume 级别 | 原因 |
| --- | --- | --- |
| Mem0 | LoCoMo turn 级；LongMemEval conversation 级 | Mem0 LoCoMo 官方 `CHUNK_SIZE=1`，可逐 turn checkpoint；Mem0 LongMemEval 官方 `CHUNK_SIZE=2`，保持 pair 写入并由 runner 只做 conversation-level resume |
| MemoryOS | conversation 级 | 官方 LoCoMo eval 以 dialogue page / QA pair 为语义单元，状态按 conversation JSON 目录持久化 |
| A-Mem | 暂无可靠跨进程 resume | robust runtime 主要为内存 dict + Faiss；后续可做 wrapper 层 Faiss + JSON 持久化 |
| LightMem | conversation 级 | `add_memory()` 中间调用可能只进 buffer；LoCoMo `add()` 返回后才执行 offline update，可作为 conversation 完成点 |

question 级 resume 继续由 runner 基于 `method_predictions.jsonl` 统一处理。

## 验证

必须覆盖：

- LoCoMo question 使用 Mem0 官方 LoCoMo answer prompt。
- LongMemEval question 使用 Mem0 官方 LongMemEval answer prompt。
- Mem0 LongMemEval 使用官方 pair 写入，且 runner 不创建 turn-level checkpoint。
- Mem0 source identity 包含两个官方 prompt 文件，但不纳入整个 `memory-benchmarks` 仓库。
- 原有 namespace、efficiency observation、parallel isolation 和 config tests 不回退。
