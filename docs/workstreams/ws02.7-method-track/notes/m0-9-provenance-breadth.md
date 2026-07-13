# M0-9 LightMem provenance 注入宽度核查

日期：2026-07-13  
分支：`actor/m0-9-provenance`

## 1. 基线差异

任务卡称只有 LoCoMo 批次附带 `external_id`，但本分支基线已包含 M0-7b：

- LoCoMo 单 turn 构建器已把同一个公开 `turn.turn_id` 写入真实 user 消息和合成空
  assistant 消息（`src/memory_benchmark/methods/lightmem_adapter.py:1180-1212`）。
- LongMemEval role message 构建器也已写入每条 turn 自己的 `turn.turn_id`
  （`src/memory_benchmark/methods/lightmem_adapter.py:1214-1264`）。
- v3 `TurnEvent`/`TurnPair` 分别复用上述两个构建器
  （`src/memory_benchmark/methods/lightmem_adapter.py:533-612`），且 event 转回 Turn
  时逐字保留 `event.turn_id`（同文件 `:648-659`）。

因此本卡无需再次修改生产 adapter；新增测试把这些已存在但覆盖不足的契约钉死。

## 2. 消息构建点清单

| 路径 | turn 到 message 的位置 | `external_id` 语义 |
|---|---|---|
| LoCoMo bridge / v3 turn | `_conversation_to_locomo_batches`，`lightmem_adapter.py:1180-1212` | 原始公开 turn id；合成空 assistant 与 user 共用同一来源 id |
| LongMemEval bridge / v3 pair | `_turn_to_role_message`，`lightmem_adapter.py:1243-1264` | 每条 user/assistant turn 各自的公开 turn id |
| v3 共用入口 | `ingest` → `_native_turn_batch` / `_native_pair_batch`，`lightmem_adapter.py:533-612` | 不改写 id，只选择上述构建器 |
| canonical event 生成 | `build_turn_events`，`src/memory_benchmark/runners/event_stream.py:29-59` | `Turn.turn_id` 经稳定化后进入 `TurnEvent.turn_id` |
| provenance 出口 | `_retrieved_items_from_lightmem_memories`，`lightmem_adapter.py:1117-1155` | payload 的 `source_external_id` 原样成为 `RetrievedItem.source_turn_ids` |

没有第二处绕过这两类 helper、独立把 turn 构造成 LightMem message 的生产路径。
`_write_native_batch` 只把已构造的 message list 交给 `add_memory`
（`lightmem_adapter.py:569-588`）。

## 3. LongMemEval 契约

**结论：确定对齐，无 gap。**

- adapter 生成公开 turn id `{session_id}:t{raw_index}`，并把同一值写入私有
  `metadata.evidence_turn_ids`；session gold 另存
  `evidence_session_public_ids`（`benchmark_adapters/longmemeval.py:216-247,358-374`）。
- `longmemeval-recall` 在 turn 声明下读取 `evidence_turn_ids`，在 session 声明下
  读取 `evidence_session_public_ids`（`evaluators/longmemeval_recall.py:77-100`）。
  它消费 artifact 的 `source_turn_ids`；session 模式用末尾 `:t<数字>` 确定性上卷
  到公开 session id（同文件 `:223-255`）。
- `longmemeval-retrieval-rank` 使用相同 gold 键选择，并在 session 模式对每个
  `source_turn_ids` 做同样上卷（`evaluators/longmemeval_retrieval_rank.py:75-84,
  186-201,274-278`）。

LightMem 声明 turn provenance，因此当前正式路径直接按 turn id 匹配；即使未来仅
以 session 视图审计，公开 id 结构也有确定映射，不需要 adapter 增加 benchmark 分支。

## 4. MemBench 契约

**结论：确定对齐，无 gap。**

- 公开 turn id 是 1 基 step 字符串 `str(step_index + 1)`
  （`benchmark_adapters/membench.py:698-735`）。私有 evidence 在落库前把官方 0 基
  `target_step_id` 转到同一公开空间（同文件 `:738-793`）。
- evaluator 从 private label 顶层 `evidence` 读取这些公开 turn id，并与 artifact
  `source_turn_ids` 直接比较（`evaluators/membench_recall.py:82-121`）。
- v3 event 以同一公开 `Turn.turn_id` 进入 adapter；本卡测试使用真实 ID 形态 `"17"`
  证明 message 的 `external_id` 不被加前缀或改写。

MemBench 的 session provenance 被 evaluator 明确视作 N/A；LightMem 出口保持 turn
粒度，故不触发降粒度需求。

## 5. BEAM 契约

**结论：确定对齐，无 gap。**

- 公开 turn id 固定为 `{session_id}:t{turn_index}`
  （`benchmark_adapters/beam.py:620-632`）。adapter 已把官方 evidence id 映射到
  这组公开 id，并存入私有 `metadata.evidence_turn_ids`
  （同文件 `:394-407`）。
- `beam-recall` 从该私有键读取 gold，并与 retrieved item 的
  `source_turn_ids` 直接比较（`evaluators/beam_recall.py:54-102`）。歧义官方 id
  已在 benchmark adapter 阶段映射为所有公开候选，不要求 method 猜测。
- 本卡测试使用真实公开 ID 形态 `p1:s1:t1`，证明共享 v3 turn 构建点不产生
  benchmark 语义分叉。

BEAM 只评 turn provenance，故无需降粒度转换。

## 6. 离线测试覆盖

- `test_native_lightmem_locomo_matches_bridge_force_and_update_sequence`：回归锁定
  LoCoMo user + 合成 assistant 的同源 `external_id`。
- `test_native_lightmem_longmemeval_matches_bridge_pair_sequence`：锁定 LME v3 pair
  的两个公开 turn id 分别进入消息。
- `test_native_lightmem_turn_path_preserves_public_external_id`：参数化覆盖 MemBench
  与 BEAM 共用 v3 `TurnEvent` 路径，断言真实公开 ID 形态原样进入 user 与合成
  assistant 消息。

真实 predict 点亮各 benchmark recall 留待架构师/用户后续运行，本卡不调用 API。

## 7. Gap 清单

无。四个 evaluator 的 gold id 都已在 benchmark adapter 阶段转换到公开 canonical
空间；唯一非 turn 视图是 LongMemEval session 口径，现有 evaluator 可由公开
`{session_id}:tN` 确定上卷。

## 施工报告

- 创建命令：`git -C /Users/wz/Desktop/memoryBenchmark worktree add ../mb-actor-m09 -b actor/m0-9-provenance`
- 生产代码：零改动；当前基线已经覆盖任务卡要求的注入点。
- 测试改动：补齐 LoCoMo/LME native 断言，新增 MemBench/BEAM v3 turn 参数化测试。
- 目标测试：`uv run pytest -q tests/test_lightmem_adapter.py` →
  `45 passed, 1 warning in 61.47s (0:01:01)`。
- 编译检查：`uv run python -m compileall -q src/memory_benchmark tests` → 退出码 0，
  无输出。
- third_party：零改动。
- 真实 API：零调用。
- 偏离：任务卡背景晚于 M0-7b 实际实现面；按现状补测试和取证，没有重复改代码。
