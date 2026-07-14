# M2 Mem0 adapter 对齐施工记录

> 日期：2026-07-14。范围仅含 B2 注入粒度、B3 failed-ingest 清理与隔离测试、
> B5 原生 memory id provenance sidecar。全程离线，未调用真实 API。

## 1. B2 注入粒度

| benchmark | 一手口径 | 本次落点 | 结果 |
|---|---|---|---|
| LoCoMo | 官方 `CHUNK_SIZE=1`，逐 turn add（`third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/run.py:88,165-193,302-340`） | turn 路径参数未变（`src/memory_benchmark/methods/mem0_adapter.py:503-521`） | 保持逐 turn |
| LongMemEval | 官方按原位置每 2 turn 分块（`third_party/methods/mem0-main/memory-benchmarks/benchmarks/longmemeval/run.py:96,314-324,407-451`） | session 路径在非 report 模式仍按位置每 2 turn 分块（`src/memory_benchmark/methods/mem0_adapter.py:554-595`） | 调用序列不变 |
| BEAM | 官方 `CHUNK_SIZE=2`，先把 role 归一到 user/assistant，再两条一组 add（`third_party/methods/mem0-main/memory-benchmarks/benchmarks/beam/run.py:89,255-272,428-476`） | registry 把 BEAM 实例改为 pair；pair 一次提交两条规范消息（`src/memory_benchmark/methods/registry.py:171-181`；`src/memory_benchmark/methods/mem0_adapter.py:523-552`） | 从 turn 修正为 2-turn chunk |
| HaluMem | 官方 wrapper 把整个 session dialogue 一次 add；证据已锁在 `docs/workstreams/ws02.7-method-track/notes/m1-mem0-evidence.md:67-84` | `session_memory_report=True` 时整个 SessionBatch 只形成一个 chunk，add 返回的 results 仍归本 session（`src/memory_benchmark/methods/mem0_adapter.py:574-599`） | 从 session 内 pair 修正为整 session单次 add |
| MemBench | Mem0 官方仓库没有复现脚本（`docs/workstreams/ws02.7-method-track/notes/m1-mem0-evidence.md:17-25`） | registry 继续使用 turn（`src/memory_benchmark/methods/registry.py:171-181`） | **轻姿态：不增加 flush/finalize，不声称官方 parity** |

Mem0 的同步 add 在提取前读取同 scope 最近 10 条消息，但没有限制本次 `messages`
列表长度（`third_party/methods/mem0-main/mem0/memory/main.py:699-704`）；因此 HaluMem
整 session 单次提交没有撞内部消息数硬上限。最近 10 条只影响下一次 add 的历史上下文。

## 2. B3 清理修复

Mem0 用 `_build_session_scope` 按 `user_id/agent_id/run_id` 排序拼 scope；框架只传
`run_id`，故写入 recent messages 的精确 scope 是 `run_id=<isolation_key>`
（`third_party/methods/mem0-main/mem0/memory/main.py:317-324,699-704`）。清理顺序为：

1. `Memory.delete_all(run_id=...)` 删除该 namespace 的向量；官方实现把同一 filter
   交给 vector store list 后逐条删除（`third_party/methods/mem0-main/mem0/memory/main.py:1540-1571`）。
2. 新增 `SQLiteManager.delete_messages(session_scope)`，事务内只删目标 scope 的
   `messages` 行（`third_party/methods/mem0-main/mem0/memory/storage.py:326-339`）。
3. adapter 删除相同 isolation key 的 sidecar 映射和 namespace，再原子持久化
   （`src/memory_benchmark/methods/mem0_adapter.py:1669-1685`）。
4. registry 按 failed checkpoint 的 `worker_idx` 选择真实 worker state 根；clean
   hook 从 `{run_dir}/method_state` 的父目录恢复 run id，再构造与 ingest 相同的
   `{run_id}_{conversation_id}`（`src/memory_benchmark/methods/registry.py:581-601,636-650,798-800`）。

history tombstone 保留是声明性无害偏差：`delete_all` 会留下删除历史，但 Mem0
提取阶段读取的是 `messages` recent context 与 vector search 结果，不读取 history
（`third_party/methods/mem0-main/mem0/memory/main.py:699-714`）。本次没有更改 history
schema 或删除历史记录。

生产 Qdrant 的零 API 测试直接使用 vendored `Qdrant` 和本地 Qdrant client，写入
两个 `run_id` 后分别检索，锁定 filter 零跨读；生产 filter 将标量变成
`MatchValue` 并传入 `query_filter`（`third_party/methods/mem0-main/mem0/vector_stores/qdrant.py:224-248,374-394`）。

## 3. B5 provenance sidecar

官方 add 返回每条新增 memory 的 UUID `id`（`third_party/methods/mem0-main/mem0/memory/main.py:957-971`），
search 返回同一原生 id；adapter 现在在每次 add 返回后记录：

```text
official memory id -> {isolation_key, source_turn_ids[]}
```

单 turn 映射一个公开 turn id，pair/session chunk 映射该次提交的全部公开 turn ids
（`src/memory_benchmark/methods/mem0_adapter.py:1557-1590`）。v3 retrieve 的
`RetrievedItem.item_id` 直接使用官方 id，`source_turn_ids` 从 sidecar 读取；缺 id、
缺映射或坏 schema 均 fail-fast，不再生成 `mem0:<rank>` 假来源
（`src/memory_benchmark/methods/mem0_adapter.py:1021-1032,1592-1649`）。registry 与
实例均声明 `provenance_granularity="turn"`（adapter `:281-282`；registry `:798`）。

sidecar 位于当前 worker 的 `method_state/provenance-sidecar.json`，写临时文件后
`os.replace`；同时保存真实 v3 isolation keys，即使 add 没抽出 memory 也保存 namespace
（`src/memory_benchmark/methods/mem0_adapter.py:355-360,1557-1577,1651-1667`）。resume
加载这些 key，不改 runner checkpoint；已有 completed conversation 但没有 sidecar 的
旧 state 明确 fail-fast（同文件 `:368-376`），满足“旧 state 不伪造来源”的裁决。

## 4. upstream PR 素材

### 动机

`delete_all(run_id=...)` 只清向量，未清同 namespace 的 recent messages；失败重试时
旧消息仍进入下一次 extraction prompt（`third_party/methods/mem0-main/mem0/memory/main.py:699-704,957-958,1540-1571`）。新增 API 只补齐已有 SQLiteManager 的
scope 级删除能力，不改变 add/search/delete_all 的既有行为。

### third_party 完整 diff

```diff
diff --git a/third_party/methods/mem0-main/mem0/memory/storage.py b/third_party/methods/mem0-main/mem0/memory/storage.py
index 6abda7b..b2b9a85 100644
--- a/third_party/methods/mem0-main/mem0/memory/storage.py
+++ b/third_party/methods/mem0-main/mem0/memory/storage.py
@@ -323,6 +323,21 @@ class SQLiteManager:
             for r in rows
         ]
 
+    def delete_messages(self, session_scope: str) -> None:
+        """Delete all recent messages stored for one session scope."""
+        with self._lock:
+            try:
+                self.connection.execute("BEGIN")
+                self.connection.execute(
+                    "DELETE FROM messages WHERE session_scope = ?",
+                    (session_scope,),
+                )
+                self.connection.execute("COMMIT")
+            except Exception as e:
+                self.connection.execute("ROLLBACK")
+                logger.error(f"Failed to delete messages for session scope: {e}")
+                raise
+
     def reset(self) -> None:
         """Drop and recreate the history and messages tables."""
         with self._lock:
```

### 零行为变化论证

新方法没有既有调用方；只有框架 failed-ingest hook 显式调用。事务和锁风格与
`save_messages/get_last_messages/reset` 相同（`third_party/methods/mem0-main/mem0/memory/storage.py:257-340`）。
正常 add/search、抽取 prompt、向量排序和 history 行为均未修改。

## 5. 测试与遗留

- `tests/test_mem0_adapter.py`：LoCoMo/LME 等价序列回归、BEAM pair、HaluMem 整
  session、清理污染、SQLite scope 删除、生产 Qdrant 双 namespace、单 turn/chunk
  provenance、sidecar resume 与旧 state fail-fast。
- `tests/test_method_registry.py`：Mem0 clean hook 注册断言。
- 真实五格 smoke、真实 recall `n>0` 由架构师/用户后续运行，本卡未调用 API。

## 施工报告

- worktree：`/Users/wz/Desktop/mb-actor-m2mem0`
- branch：`actor/m2-mem0-adapter`
- 计划偏差/停工点：无；三个停工条件均未触发。
- 定向测试：`uv run pytest -q tests/test_mem0_adapter.py tests/test_method_registry.py tests/test_mem0_source_compatibility.py` → `49 passed in 1.91s`。
- 编译检查：`uv run python -m compileall -q src/memory_benchmark tests` → exit 0，
  无输出。
- commit：本文件所在的 M2 本地提交；未 push。
