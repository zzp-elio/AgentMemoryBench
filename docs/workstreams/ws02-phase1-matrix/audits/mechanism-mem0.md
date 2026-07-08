# Mem0 机制深读卡片

完成时间：2026-07-05 20:40 CST

## 1. 写入后内部发生什么

事实：

- 本地 OSS `Memory` 初始化时同步构造 embedding model、vector store、LLM、SQLite history DB，并记录 collection 名；entity store 是第一次访问时懒加载的第二个向量集合。证据：`third_party/methods/mem0-main/mem0/memory/main.py:331-347`、`third_party/methods/mem0-main/mem0/memory/main.py:389-411`。
- 原生 `Memory.add()` 接受 string、dict 或 list[dict]，要求至少提供 `user_id`、`agent_id`、`run_id` 之一，并把这些 id 写入存储 metadata 与查询 filters。证据：`third_party/methods/mem0-main/mem0/memory/main.py:573-626`、`third_party/methods/mem0-main/mem0/memory/main.py:231-314`。
- `infer=False` 时，Mem0 跳过 `system` message，对每条非 system message 直接生成 embedding，调用 `_create_memory()` 写入向量库，返回 `id/memory/event/actor_id/role`。证据：`third_party/methods/mem0-main/mem0/memory/main.py:662-697`。
- `infer=True` 时，V3 pipeline 是同步分阶段执行：取最近消息与当前 message，先用 embedding 在已有 memory 中召回候选，再调用 LLM 做事实抽取；抽取结果批量 embedding、hash 去重、写入向量库与 history DB；随后抽取 entity、写入/更新 entity store；最后保存原始 messages。证据：`third_party/methods/mem0-main/mem0/memory/main.py:699-971`。
- 写入阶段会调用 LLM 与 embedding；代码路径中没有后台队列或异步 finalize，`Memory.add()` 返回时本次 records 已经插入 vector store 并写 history。证据：`third_party/methods/mem0-main/mem0/memory/main.py:738-745`、`third_party/methods/mem0-main/mem0/memory/main.py:770-834`、`third_party/methods/mem0-main/mem0/memory/main.py:957-971`。

推断/含义：

- 对本地 OSS Mem0 来说，写入完成判据可以落在 `Memory.add()` 成功返回；但如果使用官方 cloud `Mem0Client`，`timestamp` 等参数和服务端行为需要单独确认，不能直接等同于本地 `Memory`。

## 2. 原生 ingest 形态

事实：

- 本地 OSS 入口签名是 `Memory.add(messages, *, user_id=None, agent_id=None, run_id=None, metadata=None, infer=True, memory_type=None, prompt=None)`；`messages` 可是字符串、单条 dict 或 dict 列表，dict 需含 `role/content`。证据：`third_party/methods/mem0-main/mem0/memory/main.py:573-605`、`third_party/methods/mem0-main/mem0/memory/main.py:636-659`。
- 官方 Mem0 LoCoMo benchmark 以 turn 为写入 chunk：`CHUNK_SIZE = 1`，把 speaker A 映射为 user、speaker B 映射为 assistant，content 保留 `speaker: text` 和图片 caption，再调用 `mem0.add(messages, user_id, timestamp=session_epoch)`。证据：`third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/run.py:85-88`、`third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/run.py:165-193`、`third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/run.py:238-256`、`third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/run.py:300-340`。
- 官方 Mem0 LongMemEval benchmark 以 user+assistant pair 为写入 chunk：`CHUNK_SIZE = 2`，每个 question 单独 user namespace，按 session 日期转 timestamp，再调用 `mem0.add(messages, user_id, timestamp=session_timestamp)`。证据：`third_party/methods/mem0-main/memory-benchmarks/benchmarks/longmemeval/run.py:90-96`、`third_party/methods/mem0-main/memory-benchmarks/benchmarks/longmemeval/run.py:314-348`、`third_party/methods/mem0-main/memory-benchmarks/benchmarks/longmemeval/run.py:407-452`。
- MemoryData 初始化 Mem0 时构造 OpenAI LLM、可选 OpenAI embedding、Qdrant path、history DB，并通过 `Memory.from_config()` 实例化；memorizing 分支把 system prompt 与格式化 user chunk 作为两条 messages，使用 `user_id=context_<context_id>_<sub_dataset>` 调 `self.memory.add(..., infer=self.mem0_add_infer)`。证据：`第三方框架参考/MemoryData/utils/agent.py:1524-1600`、`第三方框架参考/MemoryData/utils/agent.py:3043-3063`。

推断/含义：

- Mem0 原生最自然的 ingest 单位不是整段 benchmark conversation，而是带明确 namespace 的 message list；LoCoMo 官方用单 turn，LongMemEval 官方用 pair。整段 conversation 需要 adapter 自己拆成这些原生 chunk。

## 3. 检索机制

事实：

- 本地 OSS `Memory.search(query, *, top_k=20, filters=None, threshold=0.1, rerank=False, **kwargs)` 要求 `filters` 至少包含 `user_id`、`agent_id` 或 `run_id`，返回 `{"results": [...]}`。证据：`third_party/methods/mem0-main/mem0/memory/main.py:1126-1237`。
- 内部检索先做 query lemmatize 与 entity extraction，再生成 query embedding，向 vector store 过量召回；若 store 支持 keyword search，则额外取 BM25 分；如果 query 有 entity，则计算 entity boost；最后融合 semantic、BM25、entity boost 排序。证据：`third_party/methods/mem0-main/mem0/memory/main.py:1343-1398`。
- 返回条目包含 `id`、`memory`、`hash`、`created_at`、`updated_at`、`score`，并提升 `user_id/agent_id/run_id/actor_id/role`，其余 payload 进入 `metadata`。证据：`third_party/methods/mem0-main/mem0/memory/main.py:1400-1438`。
- search 本身调用 embedding，不调用 answer LLM；可选 reranker 只在配置了 reranker 且 `rerank=True` 时运行。证据：`third_party/methods/mem0-main/mem0/memory/main.py:1212-1237`、`third_party/methods/mem0-main/mem0/memory/main.py:1348-1359`。
- MemoryData 的检索分支使用 `self.memory.search(query=message, user_id=user_id, limit=self.retrieve_num)`，再把 memory 文本拼入 answer prompt 并调用 answer LLM。证据：`第三方框架参考/MemoryData/utils/agent.py:3071-3125`。

推断/含义：

- Mem0 的 retrieval service 会消耗 embedding，并可能用 reranker；但 answer LLM 不在 `Memory.search()` 内部触发。按 retrieve-first 协议，应把 `search()` 输出作为 context 交给 framework reader，而不是让 method 自己回答。
- MemoryData 的 `user_id/limit` 调用形态与当前本地 OSS `filters/top_k` 签名不同，说明不同 Mem0 版本或 client 层存在 API 形态差异，adapter 需要锁定本地 vendored 版本。

## 4. 状态与边界行为

事实：

- 本地状态至少包括 vector store、history SQLite DB、entity store；本仓库 adapter 为 Mem0 配置 Qdrant 本地 path、固定 collection `mem0` 和 `history.db`。证据：`src/memory_benchmark/methods/mem0_adapter.py:324-372`。
- 官方 `Memory` 的 entity store 懒加载，并在 embedded Qdrant 模式下复用已有 client 以避免 RocksDB lock contention。证据：`third_party/methods/mem0-main/mem0/memory/main.py:389-411`。
- Mem0 的 namespace 由 `user_id/agent_id/run_id` 过滤；本仓库 adapter 写入时用 `run_id=conversation.conversation_id`，检索时用 `filters={"run_id": question.conversation_id}`。证据：`src/memory_benchmark/methods/mem0_adapter.py:488-494`、`src/memory_benchmark/methods/mem0_adapter.py:583-597`。
- 本仓库 adapter 在构造后预热 entity store，并给已构造的 OpenAI LLM/embedding client 注入 timeout/retry；这属于运行边界处理，不改变 Mem0 的记忆算法。证据：`src/memory_benchmark/methods/mem0_adapter.py:691-760`。

推断/含义：

- clean retry 的稳定边界应是 method storage root 下 Qdrant 与 history DB 的重建，而不是只清空 adapter 内存。
- 因 entity store 是懒加载，若共享一个 `Memory` 实例并发写入，首次访问边界需要由 adapter 或 runner 单线程处理。

## 5. 对协议设计的含义

事实：

- 官方 LoCoMo 写入粒度是单 turn；官方 LongMemEval 写入粒度是 user+assistant pair；两者都携带会话时间戳，但本地 OSS `Memory.add()` 签名没有 `timestamp` 参数。证据：`third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/run.py:300-340`、`third_party/methods/mem0-main/memory-benchmarks/benchmarks/longmemeval/run.py:407-452`、`third_party/methods/mem0-main/mem0/memory/main.py:573-605`。
- Mem0 需要明确 namespace 边界；单个 add 调用内部会读取同 namespace 的最近 messages 与已有 memories，用于抽取与去重。证据：`third_party/methods/mem0-main/mem0/memory/main.py:701-714`、`third_party/methods/mem0-main/mem0/memory/main.py:784-818`。
- 返回结构天然有条目级 `id/score/created_at/metadata` provenance，但本仓库 adapter 当前只向 `AnswerPromptResult.metadata["retrieved_memories"]` 暴露 `content/score/created_at`。证据：`third_party/methods/mem0-main/mem0/memory/main.py:1400-1438`、`src/memory_benchmark/methods/mem0_adapter.py:598-632`。

推断/含义：

- 协议如果只提供 `add(conversation)`，Mem0 adapter 必须自行拆 turn/pair、补 session 时间、构造 namespace 与 checkpoint 边界；如果协议提供 turn 或 benchmark-native chunk 边界，adapter 的额外形变会少。
- 协议若要求可审计 provenance，Mem0 原生能提供比当前 adapter 暴露更多的 id 与 metadata，后续可考虑让 retrieve 结果保留这些字段。

## 6. 未确认项

- 官方 cloud `Mem0Client.add(messages, user_id, timestamp=...)` 的服务端 timestamp 语义，是否完全等价于本地 OSS `Memory.add(..., prompt=observation_time_prompt)`。
- Phase 1 是否需要启用 Mem0 graph store；MemoryData 只在配置存在时透传 `mem0_graph_store`，本仓库当前 adapter 未启用 graph store。证据：`第三方框架参考/MemoryData/utils/agent.py:1598-1600`、`src/memory_benchmark/methods/mem0_adapter.py:324-372`。
- 若启用 reranker，是否属于检索服务型 LLM/模型调用以及如何计入效率指标；当前本地 search 仅在配置 reranker 且 `rerank=True` 时触发。证据：`third_party/methods/mem0-main/mem0/memory/main.py:1229-1235`。

## 7. 现有 adapter 的形变记录

事实：

- 统一协议入口是 `add(conversations)`，adapter 先判断是否 LongMemEval；LongMemEval 走 pair chunk，其他数据集走逐 turn 写入。官方原生调用形态则是直接向 `Memory.add()` 传 message list 与 namespace。证据：`src/memory_benchmark/methods/mem0_adapter.py:374-411`、`third_party/methods/mem0-main/mem0/memory/main.py:573-605`。
- 非 LongMemEval 路径把 conversation 展平成 `(session, turn)`，逐 turn 构造一条 Mem0 message 和 metadata，再调用 `self._memory.add([message], run_id=conversation_id, ...)`。这是为了复现官方 LoCoMo `CHUNK_SIZE=1`。证据：`src/memory_benchmark/methods/mem0_adapter.py:426-508`、`third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/run.py:85-88`、`third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/run.py:300-340`。
- LongMemEval 路径显式禁止 turn-level resume，按 session 内每两条 turn 生成 chunk，再把 pair messages 一起传给 `Memory.add()`。这是为了保留官方 `CHUNK_SIZE=2` 的 user+assistant pair 边界。证据：`src/memory_benchmark/methods/mem0_adapter.py:470-475`、`src/memory_benchmark/methods/mem0_adapter.py:509-559`、`src/memory_benchmark/methods/mem0_adapter.py:1037-1051`、`third_party/methods/mem0-main/memory-benchmarks/benchmarks/longmemeval/run.py:90-96`、`third_party/methods/mem0-main/memory-benchmarks/benchmarks/longmemeval/run.py:407-452`。
- adapter 把统一 `Turn` 转成 Mem0 message 时自行推断 user/assistant role、拼入 speaker、session time、turn time 与图片 caption；官方 LoCoMo 脚本也保留 speaker 与图片 caption，但它从原始 LoCoMo schema 直接转换。证据：`src/memory_benchmark/methods/mem0_adapter.py:957-988`、`third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/run.py:165-193`。
- 因本地 OSS `Memory.add()` 没有 `timestamp` 参数，adapter 用公开 `prompt` 扩展点注入 observation time；官方 benchmark cloud client 直接传 `timestamp=session_epoch/session_timestamp`。证据：`src/memory_benchmark/methods/mem0_adapter.py:1093-1110`、`third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/run.py:307-340`、`third_party/methods/mem0-main/memory-benchmarks/benchmarks/longmemeval/run.py:411-452`。
- adapter 检索时把 Mem0 原生结果归一化为 `memory/score/created_at`，再分别构造 LoCoMo、LongMemEval 或 generic reader prompt；这一步把原生 `id/run_id/metadata` 等 provenance 字段裁掉了。证据：`src/memory_benchmark/methods/mem0_adapter.py:1112-1166`、`src/memory_benchmark/methods/mem0_adapter.py:1192-1240`、`third_party/methods/mem0-main/mem0/memory/main.py:1400-1438`。

推断/含义：

- Mem0 adapter 的主要复杂度不是调用 `Memory.add/search` 本身，而是被整段 `Conversation` 输入迫使承担 benchmark-native chunking、时间锚点补偿、resume 边界和 reader prompt 选择。

原生化后状态（2026-07-06，M-B T2）：

- registry 按 benchmark profile 设置实例级 `consume_granularity`：LoCoMo 为 `turn`，LongMemEval 为 `pair`；runner 事件流负责给 adapter 提供 benchmark-native ingest unit，原生路径不再从整段 `Conversation` 自行切 turn/pair。
- `Mem0.ingest(TurnEvent|TurnPair)` 复用既有 message、metadata、observation-time prompt 构造 helper，namespace 改为 v3 `isolation_key`；等价测试用 namespace 归一化断言原生路径与桥接路径发出的 `Memory.add/search` 序列一致。
- 旧 `add()`、`add_from_turn()`、`_longmemeval_ingestion_chunks()` 本轮按计划保留，理由是旧接口、resume 兼容与桥接等价对照仍依赖它们；它们不再是 registered 原生 v3 主路径。

pair→session 修订（2026-07-07，对照 smoke 回归修复的连带定案）：

- 框架级 pair 聚合改为 user 锚定后，位置切分不再由框架提供；而 Mem0 官方 LongMemEval `CHUNK_SIZE=2` 恰是**位置切块（不裁开头、允许 (assistant, user) 组）**。为在全部 session 形状（含 8.1% assistant 开头）上精确复刻官方分组，LongMemEval 粒度改声明为 `session`，`Mem0.ingest(SessionBatch)` 在 adapter 内部按官方 `range(0, len, 2)` 切块调用 `Memory.add()`。assistant-first 等价测试锁死 bridge==native。证据：`src/memory_benchmark/methods/mem0_adapter.py`（`_ingest_native_session`）、`tests/test_mem0_adapter.py::test_native_mem0_longmemeval_assistant_first_session_keeps_official_chunks`。

HaluMem extraction 裁定（2026-07-08，ws02.2 T5）：

- Mem0 可提供 session 增量 extraction 报告：HaluMem registry 将 Mem0 的 `consume_granularity` 特化为 `session`，并只在 HaluMem 下打开 `session_memory_report`；`Mem0.end_session()` 返回当前 session 内 `Memory.add()` 返回的 `results[*].memory`。证据：`third_party/methods/mem0-main/mem0/memory/main.py:608-611`、`third_party/methods/mem0-main/mem0/memory/main.py:659-660`、`third_party/methods/mem0-main/mem0/memory/main.py:957-971`、`tests/test_mem0_adapter.py::test_mem0_halumem_session_report_returns_current_session_add_results`。
