# A-Mem 机制深读卡片

完成时间：2026-07-05 21:24 CST

## 1. 写入后内部发生什么

事实：

- 本仓库接入的是官方 robust layer：`RobustAgenticMemorySystem` 初始化时创建 `memories` dict、`SimpleEmbeddingRetriever` 和 `RobustLLMController`，默认 embedding 模型是 `all-MiniLM-L6-v2`。证据：`third_party/methods/A-mem/memory_layer_robust.py:352-373`。
- 原生写入入口是 `add_note(content: str, time: str = None, **kwargs)`。它先构造 `RobustMemoryNote`，传入 content、timestamp 和 LLM controller；`RobustMemoryNote` 会在缺少 keywords/context/category/tags 时调用 LLM 分析内容。证据：`third_party/methods/A-mem/memory_layer_robust.py:273-345`、`third_party/methods/A-mem/memory_layer_robust.py:377-385`。
- content analysis 使用 `ANALYZE_CONTENT_PROMPT` 调 LLM，解析 keywords/context/tags；如果 keywords 为空，会用 focused keywords prompt 再调一次 LLM；异常时退化为启发式 keywords/context/tags。证据：`third_party/methods/A-mem/memory_layer_robust.py:317-345`。
- `process_memory()` 先用 embedding retriever 找 5 个近邻；无近邻时直接存储。若有近邻，最多进行三类 LLM 调用：evolution decision、strengthen details、update neighbors；strengthen 会更新新 note links/tags，update 会改邻居 tags/context。证据：`third_party/methods/A-mem/memory_layer_robust.py:463-540`。
- 写入最终把 note 放进 `self.memories`，并把 `content/context/keywords/tags` 拼成一个文档加入 embedding retriever；如果 evolution 计数达到阈值，会重建 retriever。证据：`third_party/methods/A-mem/memory_layer_robust.py:385-397`、`third_party/methods/A-mem/memory_layer_robust.py:399-410`。

推断/含义：

- A-Mem 写入是同步的，`add_note()` 返回时 note 已进入内存 dict 和 retriever；但写入可包含多次 LLM 调用，且 evolution 可能修改邻居，写入成本和行为依赖已有 memory 状态。

## 2. 原生 ingest 形态

事实：

- 原生 ingest 单位是一条文本 note，加可选 `time` 字符串。`RobustMemoryNote` 使用传入 timestamp；缺失时用当前时间 `YYYYMMDDHHMM`。证据：`third_party/methods/A-mem/memory_layer_robust.py:276-307`、`third_party/methods/A-mem/memory_layer_robust.py:377-397`。
- 官方 robust LoCoMo eval 中，`add_memory(content, time=None)` 只是调用 `memory_system.add_note(content, time=time)`；构建 memory 时逐 turn 生成 `Speaker <speaker>says : <text>`，并传入 session `date_time`。证据：`third_party/methods/A-mem/test_advanced_robust.py:75-79`、`third_party/methods/A-mem/test_advanced_robust.py:240-249`。
- 官方缓存边界是 sample 级：写入后把 `memory_system.memories` pickle 到 `memory_cache_sample_<idx>.pkl`，并保存 retriever cache 与 embeddings；恢复时优先加载这些缓存，否则从 memory 重建 retriever。证据：`third_party/methods/A-mem/test_advanced_robust.py:215-249`。
- MemoryData 的 A-MEM 集成使用 `AMemAdapter.add_chunk(content, timestamp)`；外层 memorizing 分支会先套 memorize template，再传 `timestamp=time.strftime("%Y%m%d%H%M")`，finalize 时把 state JSON 和 marker 写盘。证据：`第三方框架参考/MemoryData/utils/agent.py:1748-1814`、`第三方框架参考/MemoryData/utils/agent.py:3252-3264`、`第三方框架参考/MemoryData/utils/agent.py:4404-4408`。

推断/含义：

- A-Mem 最自然的输入粒度是单条 note/turn。它没有 session/conversation flush；conversation 级完成主要是 benchmark runner 的持久化边界，不是 A-Mem 算法自身的 finalize。

## 3. 检索机制

事实：

- `SimpleEmbeddingRetriever` 用 SentenceTransformer 编码文档；`search(query, k)` 对 query 编码并用 cosine similarity 取 top-k indices。证据：`third_party/methods/A-mem/memory_layer.py:554-610`。
- `find_related_memories(query, k)` 返回 top-k memory 的 index、timestamp、content、context、keywords、tags；`find_related_memories_raw(query, k)` 还会展开每个命中 memory 的 `links` 邻居并把邻居内容拼进返回字符串。证据：`third_party/methods/A-mem/memory_layer_robust.py:411-459`。
- 官方 robust QA 不是直接用原问题检索，而是先用 `generate_query_llm(question)` 生成 keywords，再用 keywords 调 `retrieve_memory(..., k=self.retrieve_k)`。证据：`third_party/methods/A-mem/test_advanced_robust.py:96-113`。
- 官方 robust answer prompt 按 LoCoMo category 分支；category 5 adversarial prompt 会把 gold answer 和 "Not mentioned in the conversation" 作为二选一候选。证据：`third_party/methods/A-mem/test_advanced_robust.py:109-153`。
- MemoryData adapter 的 `retrieve_with_source_groups()` 直接对 question 做 retriever search，返回 root memory 加 links 邻居，并从 memory content 中解析 LoCoMo source ids；它未复刻官方 `generate_query_llm()`。证据：`第三方框架参考/MemoryData/methods/a_mem/a_mem_adapter.py:225-267`。

推断/含义：

- A-Mem 的检索阶段含一个 query-rewrite LLM 调用，这是检索服务型调用；真正 answer LLM 在 `answer_question()` 或本仓库 `get_answer()` 中另行发生。retrieve-first adapter 应保留 keyword generation 与 raw memory retrieval，但不能把 gold answer 交给 method。

## 4. 状态与边界行为

事实：

- 原生状态在进程内：`memories` dict 保存 `RobustMemoryNote`，retriever 保存 corpus 与 embedding matrix。证据：`third_party/methods/A-mem/memory_layer_robust.py:366-373`、`third_party/methods/A-mem/memory_layer.py:563-587`。
- 官方 robust eval 用 pickle/numpy 文件缓存 sample 级 memories、retriever corpus 和 embeddings。证据：`third_party/methods/A-mem/test_advanced_robust.py:215-249`、`third_party/methods/A-mem/memory_layer.py:612-664`。
- 本仓库 adapter 为每个 conversation 保存 `memories.pkl`、`retriever.pkl`、`retriever_embeddings.npy` 和 `state_manifest.json`，并用 source hash、profile、turn_count 与文件 checksum 做强校验。证据：`src/memory_benchmark/methods/amem_adapter.py:448-555`。
- 恢复时，本仓库 adapter 加载 memories pickle、调用官方 retriever.load()，并校验当前 conversation turn_count 与 manifest 一致；clean retry 删除单个 conversation 状态目录。证据：`src/memory_benchmark/methods/amem_adapter.py:279-322`、`src/memory_benchmark/methods/amem_adapter.py:1076-1091`。
- 官方 robust OpenAI controller 构造时只调用 `OpenAI(api_key=api_key)`，`RobustLLMController` 接受 `api_base` 但 openai 分支没有传下去；本仓库 adapter 因此在 runtime 构造后替换 client 以注入 base URL、timeout、retry。证据：`third_party/methods/A-mem/memory_layer_robust.py:97-121`、`third_party/methods/A-mem/memory_layer_robust.py:243-263`、`src/memory_benchmark/methods/amem_adapter.py:562-615`。

推断/含义：

- A-Mem 没有后台任务；写入完成点是每次 `add_note()` 返回，稳定恢复点则需要 runner 在 conversation 完成后保存 memories 与 retriever 双状态。

## 5. 对协议设计的含义

事实：

- A-Mem 官方 LoCoMo 写入逐 turn 调 `add_note(content, time=session_date_time)`，没有整段 conversation API。证据：`third_party/methods/A-mem/test_advanced_robust.py:240-249`。
- A-Mem 检索前需要 query keyword generation；本仓库 adapter 在 `retrieve()` 中先 `_generate_query_keywords()`，再 `runtime.find_related_memories_raw(query_keywords, k=retrieve_k)`，并把 keywords 放进 metadata。证据：`src/memory_benchmark/methods/amem_adapter.py:323-391`、`src/memory_benchmark/methods/amem_adapter.py:749-778`。
- 本仓库 adapter 按 LoCoMo Table 8 profile 为 category 1/2/3/4/5 配不同 k；但 category 5 因官方 prompt 需要 gold answer 被显式拒绝。证据：`src/memory_benchmark/methods/amem_adapter.py:67-73`、`src/memory_benchmark/methods/amem_adapter.py:779-794`。

推断/含义：

- 协议如果能提供 `add_turn(content, time, speaker)`，A-Mem adapter 可直接映射原生 `add_note()`；若只给 `add(conversation)`，adapter 仍需自行遍历 turn、拼 speaker 文本、传 session_time，并在 conversation 末尾持久化。
- A-Mem 的 retrieve 输出最好保留 query keywords、k、raw memory context；条目级 id/score 原生没有直接暴露，只能通过 retriever indices 与 memories 顺序间接恢复。

## 6. 未确认项

- 官方 A-Mem robust 论文/脚本是否要求 query-time `retrieve_memory_llm()` 二次筛选；robust eval 中该函数存在，但 `answer_question()` 当前直接使用 raw_context。证据：`third_party/methods/A-mem/test_advanced_robust.py:81-94`、`third_party/methods/A-mem/test_advanced_robust.py:109-113`。
- MemoryData 的 direct question retrieval 与官方 keyword generation retrieval 不一致；若参考 MemoryData 做工程接入，需要架构师确认是否接受这种偏离。证据：`第三方框架参考/MemoryData/methods/a_mem/a_mem_adapter.py:225-267`、`third_party/methods/A-mem/test_advanced_robust.py:96-113`。
- category 5 adversarial 的公开协议替代 prompt 需要架构师裁定；当前本仓库 adapter 按隐私规则拒绝。证据：`third_party/methods/A-mem/test_advanced_robust.py:117-128`、`src/memory_benchmark/methods/amem_adapter.py:330-335`。

## 7. 现有 adapter 的形变记录

事实：

- 统一 `add(conversation)` 迫使本仓库 adapter 双层遍历 conversation/session/turn，再对每个 turn 调 `_call_runtime_add()`；官方原生形态是单 note `add_note(content, time)`。证据：`src/memory_benchmark/methods/amem_adapter.py:258-277`、`src/memory_benchmark/methods/amem_adapter.py:687-695`、`third_party/methods/A-mem/memory_layer_robust.py:377-397`。
- adapter 把统一 Turn 拼成 `Speaker <speaker> says: <content>`，并用 `turn.turn_time or session_time` 作为 timestamp；官方 robust eval 使用 `Speaker <speaker>says : <text>` 和 session `date_time`。证据：`src/memory_benchmark/methods/amem_adapter.py:687-695`、`third_party/methods/A-mem/test_advanced_robust.py:240-249`。
- adapter 在 `retrieve()` 中复刻官方 query keyword generation，并把 LongMemEval `question_time` 拼进有效问题文本；官方 LoCoMo robust eval 没有 LongMemEval 分支。证据：`src/memory_benchmark/methods/amem_adapter.py:749-778`、`src/memory_benchmark/methods/amem_adapter.py:911-920`、`third_party/methods/A-mem/test_advanced_robust.py:96-113`。
- adapter 为 retrieve-first 构造 `AnswerPromptResult.prompt_messages`，LongMemEval 使用 LightMem-style system+user reader，LoCoMo 使用 A-Mem robust LoCoMo prompt；旧 `get_answer()` 只是 wrapper。证据：`src/memory_benchmark/methods/amem_adapter.py:323-429`、`src/memory_benchmark/methods/amem_adapter.py:696-747`。
- adapter 增加了 conversation-level state manifest、source identity、checksum 与 profile 校验；这是为了 runner resume 和审计，而不是 A-Mem 原生 API。证据：`src/memory_benchmark/methods/amem_adapter.py:448-555`。
- adapter 替换官方 OpenAI client 以支持 OpenAI-compatible base URL、timeout、retry，并安装 usage observer；这是运行环境/观测形变，不改变记忆算法。证据：`src/memory_benchmark/methods/amem_adapter.py:562-685`、`third_party/methods/A-mem/memory_layer_robust.py:97-121`。

推断/含义：

- A-Mem adapter 的主要形变来自整段 conversation 输入、跨 benchmark reader 兼容、隐私规则对 category 5 的限制，以及 production 运行所需的状态持久化与 OpenAI-compatible client 注入。

原生化后状态（2026-07-06，M-B T4）：

- registered 主路径已是 `consume_granularity="turn"` 的 v3 provider；`AMem.ingest(TurnEvent)` 直接复用 `_call_runtime_add()` 拼 `Speaker X says: ...` 并调用 `add_note(content, time)`，不再从整段 `Conversation` 双层遍历后写入。
- conversation 级持久化移动到 `end_conversation()`，继续保存 `memories.pkl`、`retriever.pkl`、`retriever_embeddings.npy` 与 `state_manifest.json`；等价测试比较桥接与原生路径的 add/retrieve 调用和状态文件内容哈希。
- 旧 `add()` 本轮按计划保留，理由是旧接口、resume 恢复和桥接等价对照仍依赖它；category 5 拒绝、LongMemEval reader prompt、OpenAI-compatible client 注入与 usage observer 语义不变。

HaluMem extraction 裁定（2026-07-08，ws02.2 T5）：

- A-Mem 本轮不提供 session 增量 extraction 报告，保持不覆写 `end_session()`，HaluMem extraction 记 N/A。原因是原生边界是单 note `add_note(content, time)`，返回值只有 note id；它没有 session flush 或 session 级新增 memory 列表，conversation 级持久化是本仓 adapter 的 runner 边界。证据：`third_party/methods/A-mem/memory_layer_robust.py:377-397`、`src/memory_benchmark/methods/amem_adapter.py:258-277`、`src/memory_benchmark/methods/amem_adapter.py:687-695`。
