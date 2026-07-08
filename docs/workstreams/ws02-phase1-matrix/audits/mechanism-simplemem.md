# SimpleMem 机制深读卡片

完成时间：2026-07-05 20:59 CST

## 1. 写入后内部发生什么

事实：

- 文本路径的主类是 `SimpleMemSystem`，初始化时创建 `LLMClient`、`EmbeddingModel`、`VectorStore`、`MemoryBuilder`、`HybridRetriever` 和 `AnswerGenerator`；README 也说明 `add_dialogue()` 首次调用会选择 Text backend。证据：`third_party/methods/SimpleMem/main.py:16-109`、`third_party/methods/SimpleMem/README.md:167-210`。
- 原生 `add_dialogue(speaker, content, timestamp=None)` 只把输入包装成 `Dialogue(dialogue_id, speaker, content, timestamp)`，再交给 `MemoryBuilder.add_dialogue()`；它本身不直接写 LanceDB。证据：`third_party/methods/SimpleMem/main.py:111-128`、`third_party/methods/SimpleMem/simplemem/core/models/memory_entry.py:70-81`。
- `MemoryBuilder` 维护 `dialogue_buffer`、`processed_count` 和 `previous_entries`；单条写入会 append 到 buffer，只有 buffer 长度达到 `window_size` 时才自动 `process_window()`。证据：`third_party/methods/SimpleMem/simplemem/core/memory_builder.py:31-67`。
- `process_window()` 按 `window_size` 取窗口，并按 `step_size = window_size - overlap_size` 前移，保留 overlap 上下文；随后调用 LLM 从窗口生成 MemoryEntry，成功后批量写入 vector store，并把 entries 设为下一窗口参考上下文。证据：`third_party/methods/SimpleMem/simplemem/core/memory_builder.py:41-56`、`third_party/methods/SimpleMem/simplemem/core/memory_builder.py:132-155`。
- `finalize()` 调用 `process_remaining()`，把尚未达到窗口大小的剩余 buffer 也交给 LLM 抽取并写入 vector store，之后清空 buffer。证据：`third_party/methods/SimpleMem/main.py:138-144`、`third_party/methods/SimpleMem/simplemem/core/memory_builder.py:157-168`。
- 抽取 prompt 要求从对话窗口生成完整、无指代、带绝对时间的结构化 memory entries；schema 包括 `lossless_restatement`、`keywords`、`timestamp`、`location`、`persons`、`entities` 和 `topic`。证据：`third_party/methods/SimpleMem/simplemem/core/memory_builder.py:229-306`、`third_party/methods/SimpleMem/simplemem/core/models/memory_entry.py:13-67`。
- LLM 抽取最多重试 3 次；解析成功后把 JSON array 转成 `MemoryEntry`，失败则本窗口返回空 entries。证据：`third_party/methods/SimpleMem/simplemem/core/memory_builder.py:170-228`、`third_party/methods/SimpleMem/simplemem/core/memory_builder.py:308-336`。
- 写入 vector store 时，对每条 `lossless_restatement` 生成 embedding，向 LanceDB 表写入 entry id、restatement、keywords、timestamp、location、persons、entities、topic 和 vector；首次写入后初始化 FTS index。证据：`third_party/methods/SimpleMem/simplemem/core/database/vector_store.py:53-99`、`third_party/methods/SimpleMem/simplemem/core/database/vector_store.py:121-149`。

推断/含义：

- SimpleMem 的写入完成点不是 `add_dialogue()` 返回，而是窗口处理或 `finalize()` 返回。输入 turn 会先停留在内存 buffer，只有被 LLM 压缩成 MemoryEntry 并写入 LanceDB 后才可被检索。

## 2. 原生 ingest 形态

事实：

- Text backend 原生单条入口是 `add_dialogue(speaker: str, content: str, timestamp: Optional[str] = None)`；批量入口是 `add_dialogues(dialogues: List[Dialogue])`；完成边界是显式 `finalize()`。证据：`third_party/methods/SimpleMem/main.py:111-144`。
- Auto router 会在第一次 `add_dialogue()` 或 `add_dialogues()` 时选择 text backend，之后不能混用 multimodal backend；`finalize()` 和 `ask()` 都要求 text mode。证据：`third_party/methods/SimpleMem/simplemem/router.py:280-332`。
- `Dialogue` 原生字段只有 `dialogue_id`、`speaker`、`content` 和可选 ISO timestamp；没有 conversation_id、session_id 或 metadata 字段。证据：`third_party/methods/SimpleMem/simplemem/core/models/memory_entry.py:70-81`。
- `add_dialogues()` 在大批量且启用并行时会先把所有 dialogues 分成带 overlap 的 windows，再并行调用 worker 抽取 entries；小批量则逐条入 buffer，再按完整窗口处理。证据：`third_party/methods/SimpleMem/simplemem/core/memory_builder.py:68-130`、`third_party/methods/SimpleMem/simplemem/core/memory_builder.py:338-433`。
- MemoryData 的 SimpleMem adapter 使用 `add_chunk(content, timestamp)` 包一层，实际固定调用 `self.system.add_dialogue(speaker="Benchmark", content=content, timestamp=timestamp)`；在 agent finalize 阶段才调用 `self.simplemem.finalize()` 并写 marker/source map。证据：`第三方框架参考/MemoryData/methods/simplemem/simplemem_adapter.py:153-159`、`第三方框架参考/MemoryData/utils/agent.py:3151-3160`、`第三方框架参考/MemoryData/utils/agent.py:4392-4398`。
- MemoryData 初始化时给 SimpleMem 每个 context 单独的 LanceDB path/table name，并把 LLM、embedding、并行、top-k、window/overlap 等参数写入 SimpleMem runtime config。证据：`第三方框架参考/MemoryData/utils/agent.py:1606-1679`、`第三方框架参考/MemoryData/methods/simplemem/simplemem_adapter.py:23-151`。

推断/含义：

- SimpleMem 最舒服的输入粒度是有 speaker 和 timestamp 的 dialogue turn，并且必须有 conversation/session 结束信号来触发 `finalize()`。如果只给自由文本 chunk，也可以跑，但会丢失真实 speaker 结构或需要 adapter 自己编码进 content。

## 3. 检索机制

事实：

- 原生 `ask(question)` 先调用 `hybrid_retriever.retrieve(question)`，再把 contexts 交给 `AnswerGenerator.generate_answer()` 生成最终答案。证据：`third_party/methods/SimpleMem/main.py:145-169`。
- `HybridRetriever.retrieve()` 默认走 planning；关闭 planning 时退化为单路 semantic search。证据：`third_party/methods/SimpleMem/simplemem/core/hybrid_retriever.py:58-73`。
- planning 路径先用 LLM 分析信息需求、生成 targeted queries；随后执行 semantic searches，再对原 query 做 LLM query analysis，追加 keyword search 和 structured search，最后按 entry_id 去重。证据：`third_party/methods/SimpleMem/simplemem/core/hybrid_retriever.py:75-127`、`third_party/methods/SimpleMem/simplemem/core/hybrid_retriever.py:176-240`、`third_party/methods/SimpleMem/simplemem/core/hybrid_retriever.py:409-421`。
- semantic search 用 query embedding 在 LanceDB vector 上取 top_k；keyword search 使用 LanceDB FTS；structured search 根据 persons、location、entities 和 timestamp_range 构造 where 条件。证据：`third_party/methods/SimpleMem/simplemem/core/database/vector_store.py:150-183`、`third_party/methods/SimpleMem/simplemem/core/database/vector_store.py:185-233`。
- reflection 打开时，SimpleMem 会用 LLM 判断当前 contexts 是否足以回答；若不足，再生成 additional queries 并追加检索，最多按 `max_reflection_rounds` 循环。证据：`third_party/methods/SimpleMem/simplemem/core/hybrid_retriever.py:120-127`、`third_party/methods/SimpleMem/simplemem/core/hybrid_retriever.py:423-545`。
- `AnswerGenerator.generate_answer()` 是作答型 LLM 调用：它把 MemoryEntry contexts 格式化进 prompt，要求输出 JSON `{reasoning, answer}`。证据：`third_party/methods/SimpleMem/simplemem/core/answer_generator.py:22-83`、`third_party/methods/SimpleMem/simplemem/core/answer_generator.py:85-153`。
- MemoryData 查询阶段没有调用 `system.ask()`；它直接调用 `self.system.hybrid_retriever.retrieve(question)`，只返回 entry id、lossless_restatement 和 source_ids，再由 MemoryData 外层 answer generator 作答。证据：`第三方框架参考/MemoryData/methods/simplemem/simplemem_adapter.py:160-177`、`第三方框架参考/MemoryData/utils/agent.py:3162-3184`。

推断/含义：

- retrieve-first 接入应绕开 `ask()`，保留 `hybrid_retriever.retrieve()` 的检索服务型 LLM 调用和返回 entries；最终 answer LLM 应由 framework reader 执行。SimpleMem 原生返回的 `MemoryEntry` 没有相似度分数，provenance 主要是 `entry_id` 和 MemoryData 自行维护的 source map。

## 4. 状态与边界行为

事实：

- 持久状态主要在 LanceDB：`VectorStore` 初始化时连接 `LANCEDB_PATH` 和 `MEMORY_TABLE_NAME`，本地路径会自动创建目录和表。证据：`third_party/methods/SimpleMem/simplemem/core/database/vector_store.py:28-72`。
- LanceDB 表 schema 包含 `entry_id/lossless_restatement/keywords/timestamp/location/persons/entities/topic/vector`；clear 会 drop table 并重建 schema。证据：`third_party/methods/SimpleMem/simplemem/core/database/vector_store.py:53-72`、`third_party/methods/SimpleMem/simplemem/core/database/vector_store.py:245-250`。
- 非持久状态包括 `MemoryBuilder.dialogue_buffer`、`processed_count`、`previous_entries`；如果进程在 finalize 前退出，未处理 buffer 不在 LanceDB 中。证据：`third_party/methods/SimpleMem/simplemem/core/memory_builder.py:51-67`、`third_party/methods/SimpleMem/simplemem/core/memory_builder.py:157-168`。
- 并行写入和并行检索都用 `ThreadPoolExecutor`，但都是同步等待 futures 完成；没有常驻后台 worker。证据：`third_party/methods/SimpleMem/simplemem/core/memory_builder.py:338-373`、`third_party/methods/SimpleMem/simplemem/core/hybrid_retriever.py:559-620`。
- LLM client 使用 OpenAI SDK，支持 `base_url`，并在失败时指数退避重试；embedding 默认用 SentenceTransformers 加载配置的 embedding 模型，query/document 编码都在本地模型接口。证据：`third_party/methods/SimpleMem/simplemem/core/utils/llm_client.py:14-106`、`third_party/methods/SimpleMem/simplemem/core/utils/embedding.py:11-157`。
- 默认 settings 中 `WINDOW_SIZE=40`、`OVERLAP_SIZE=2`、`SEMANTIC_TOP_K=25`、`KEYWORD_TOP_K=5`、`STRUCTURED_TOP_K=5`，默认 LLM 是 `gpt-4.1-mini`，默认 embedding 是 `Qwen/Qwen3-Embedding-0.6B`。证据：`third_party/methods/SimpleMem/simplemem/core/settings.py:12-40`。

推断/含义：

- clean retry 应删除或重建每个 run/context 的 LanceDB path/table，并重新 replay 原始 dialogues 到 finalize。恢复如果只打开 LanceDB，无法恢复尚未 finalize 的 buffer。

## 5. 对协议设计的含义

事实：

- README 的基础用法是多次 `mem.add_dialogue(speaker, content, timestamp)`，随后 `mem.finalize()`，再 `mem.ask(question)`。证据：`third_party/methods/SimpleMem/README.md:167-210`。
- SimpleMem 的写入窗口和 overlap 是算法参数，完整窗口会自动抽取，剩余窗口必须靠 `finalize()`。证据：`third_party/methods/SimpleMem/simplemem/core/memory_builder.py:41-67`、`third_party/methods/SimpleMem/simplemem/core/memory_builder.py:157-168`。
- MemoryEntry 是压缩后的事实单元，而不是原始 dialogue；它含结构化字段但不保留原始 dialogue ids，MemoryData 因此 monkeypatch `_generate_memory_entries()` 从 content 中解析 LoCoMo source ids，并把 entry_id 到 source_ids 的映射另存 sidecar。证据：`third_party/methods/SimpleMem/simplemem/core/models/memory_entry.py:13-67`、`第三方框架参考/MemoryData/methods/simplemem/simplemem_adapter.py:179-210`。

推断/含义：

- 协议若只提供 `add(conversation)`，adapter 必须遍历 turns、选择 speaker/content/timestamp 映射，并在 conversation 末尾显式 finalize。协议若提供 `add_turn()` 加 `finalize_conversation()`，会更贴近 SimpleMem。
- 如果 benchmark 需要 evidence/provenance，协议需要允许 adapter 传入 source id 或 sidecar；否则 SimpleMem 的 LLM 压缩会把多条原始 turn 合并成 MemoryEntry，难以从结果反查原始证据。
- 检索服务型 LLM 调用包括 query planning、query analysis、reflection adequacy/additional query；这些应算入 retrieval 成本，但最终 `AnswerGenerator` 不应在 retrieve-first path 中调用。

## 6. 未确认项

- Phase 1 是否使用 `SimpleMem` auto router、`SimpleMemSystem` text backend，还是 EvolveMem/Omni 子系统，需要架构师裁定；本卡按 text backend 与 MemoryData 实际接入口径分析。证据：`third_party/methods/SimpleMem/README.md:130-138`、`third_party/methods/SimpleMem/simplemem/router.py:260-332`、`第三方框架参考/MemoryData/methods/simplemem/simplemem_adapter.py:16-21`。
- 官方默认 LLM 是 `gpt-4.1-mini`，项目硬规则当前统一 `gpt-4o-mini`；未来接入时需要 adapter 显式覆盖 `model`。证据：`third_party/methods/SimpleMem/simplemem/core/settings.py:12-24`、`第三方框架参考/MemoryData/methods/simplemem/simplemem_adapter.py:127-129`。
- 默认安装一次性包含 text、multimodal 和 EvolveMem 依赖；是否能为 Phase 1 维护 text-only 依赖集，需后续接入时验证。证据：`third_party/methods/SimpleMem/setup.py:24-50`。

## 7. 现有 adapter 的形变记录

HaluMem extraction 裁定（2026-07-08，ws02.2 T5）：

- SimpleMem 不提供干净的 session 增量 extraction 报告，本轮保持不覆写 `end_session()`，HaluMem extraction 记 N/A。原因是原生 `add_dialogue()` 先进入 `dialogue_buffer`，只有窗口满 `WINDOW_SIZE` 时自动 `process_window()`，剩余内容要到 `finalize()/process_remaining()` 才抽取并写入；MemoryEntry 可能跨 session/window 合并，不能安全归因到单个 session 的新增 memory。证据：`third_party/methods/SimpleMem/simplemem/core/memory_builder.py:51-67`、`third_party/methods/SimpleMem/simplemem/core/memory_builder.py:157-168`。
