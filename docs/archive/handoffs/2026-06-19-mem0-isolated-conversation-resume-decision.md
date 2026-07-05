# 2026-06-19 Mem0 isolated 并发与 conversation-level resume 决策

## 用户决策

用户明确决定：

- Mem0 不再使用共享 OSS `Memory` 实例做 conversation 并发。
- Mem0 不再保留 LoCoMo turn-level resume。
- Mem0 改为框架自己的 isolated conversation 并发，并统一使用 conversation-level resume。

## 已完成文档同步

- `docs/task-ledger.md`
  - 新增 P0：isolated worker state 路径稳定化。
  - 新增 P0：Mem0 改为 isolated conversation 并发。
  - 新增 P0：Mem0 移除 turn-level resume，统一 conversation-level resume。
- `docs/current-roadmap.md`
  - Phase I 增加 isolated worker state root 稳定性前置任务。
  - Phase I 增加 Mem0 并发/resume 策略重构任务。
- `AGENTS.md`
  - 标注 Mem0 共享实例并发和 turn-level resume 是历史方向，已被用户新决策覆盖。
- `README.md`
  - 标注 Mem0 full 并发策略正在调整。

## subagent 只读审计结论

### Mem0 当前状态

- `src/memory_benchmark/methods/registry.py`
  - Mem0 registration 当前仍为 `supports_shared_instance_parallelism=True`。
  - 因此 `official_full max_workers=10` 当前会走共享实例线程并发。
- `src/memory_benchmark/methods/mem0_adapter.py`
  - `Mem0.supports_turn_resume()` 当前对非 LongMemEval 返回 `True`。
  - LoCoMo 当前会走 `add_from_turn()` 和 runner turn checkpoint。
  - LongMemEval 当前已走 conversation-level resume。

### runner 风险

isolated worker 路径已有 conversation-level resume 和 question-level resume，但 state root
目前使用 `method_state/worker_{idx}`。`worker_{idx}` 由当前剩余 work plan 动态分块产生：

- 首轮某 conversation 可能在 `worker_5` 完成 ingest 但未答完。
- resume 时剩余 work plan 变小，该 conversation 可能被分到 `worker_0`。
- 对 Mem0 这类本地 Qdrant/history state 位于 worker storage root 的 method，会导致
  `existing_conversation_ids` 认为 namespace 已完成，但 backend 实际读不到旧 state。

因此 Mem0 切 isolated 前必须先稳定 state root 映射。

## 推荐实施顺序

1. 修 isolated worker state root 稳定性。
   - 推荐使用 conversation-stable state root，例如 `method_state/conversations/<conversation_id>/`，
     或持久化 `conversation_id -> state_root` 映射。
   - 需要覆盖 partial question resume：已完成 ingest、未完成所有 question 的 conversation
     必须在 resume 后加载同一 state root。
2. 切 Mem0 registration。
   - `supports_shared_instance_parallelism=False`。
   - official-full 的 `max_workers=10` 才会进入 isolated worker。
3. 切 Mem0 turn resume。
   - `supports_turn_resume()` 对 LoCoMo 和 LongMemEval 都返回 `False`。
   - 保留 `Mem0.add()` 内部 LoCoMo 逐 turn 调用官方 `Memory.add([message])` 的算法语义；
     只是 runner 不再做 turn checkpoint。
4. 清理/调整测试。
   - 修改 Mem0 registry 测试。
   - 修改 Mem0 `supports_turn_resume` 测试。
   - 保留 LoCoMo 单 message 写入和 LongMemEval pair 写入测试。
   - 增加旧 turn checkpoint fail-closed 测试。
   - 增加 stable state root + partial question resume 测试。
5. 做离线 focused 回归。
6. 用户确认后，再做极小 Mem0 LoCoMo isolated smoke；不要直接 resume
   `outputs/mem0-locomo-0619-1302/` 当作成功 run。

## 当前未执行

本 handoff 只记录决策和任务拆分，尚未修改代码。
