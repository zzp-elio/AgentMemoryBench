# MemOS 机制深读卡片

完成时间：2026-07-05 21:10 CST

## 1. 写入后内部发生什么

事实：

- MemOS 官方定位是 Memory Operating System，统一 long-term memory 的 store/retrieve/manage，并支持 KB、多模态、tool memory 和多 cube 管理。证据：`third_party/methods/MemOS/README.md:58-69`。
- MemOS 有库内 `MOS.add(...)` 与 self-host API 两种入口；README 的 self-host add 请求字段包括 `user_id`、`mem_cube_id`、`messages`、`async_mode`，搜索请求包括 `query`、`user_id`、`mem_cube_id`。证据：`third_party/methods/MemOS/README.md:224-266`。
- `MOS` 初始化会创建 chat LLM、mem_reader、chat_history_manager、user_manager，并在 `enable_mem_scheduler` 为真时初始化 scheduler。证据：`third_party/methods/MemOS/src/memos/mem_os/core.py:45-80`、`third_party/methods/MemOS/src/memos/mem_os/core.py:111-139`。
- `MOS.add()` 接受 `messages`、`memory_content`、`doc_path` 三类输入，并解析 `user_id`、`session_id`、`mem_cube_id`；如果没有显式 cube，会选择用户可访问的第一个 cube。证据：`third_party/methods/MemOS/src/memos/mem_os/core.py:684-733`。
- 对 `general_text`，`MOS.add(messages=...)` 不走 LLM 抽取，而是把每条 message 的 content 直接包装为 `TextualMemoryItem(memory=..., metadata={user_id, session_id, source="conversation"})`，再写入 text memory。证据：`third_party/methods/MemOS/src/memos/mem_os/core.py:741-757`。
- 对 `tree_text`，`MOS.add(messages=...)` 会调用 `mem_reader.get_memory([messages], type="chat", info={user_id, session_id}, mode=...)` 生成 memories，再调用 `text_mem.add()` 写入。证据：`third_party/methods/MemOS/src/memos/mem_os/core.py:757-795`。
- `GeneralTextMemory.add()` 会对 memory 文本做 embedding，构造 `VecDBItem(id, payload, vector)` 后写入 Qdrant vector db。证据：`third_party/methods/MemOS/src/memos/memories/textual/general.py:81-105`。
- `TreeTextMemory.add()` 委托 `MemoryManager.add()`；后者批量写 graph nodes，按 `memory_type` 写 LongTermMemory/UserMemory/RawFileMemory 等节点，必要时添加 reorganizer 消息。证据：`third_party/methods/MemOS/src/memos/memories/textual/tree.py:103-115`、`third_party/methods/MemOS/src/memos/memories/textual/tree_text_memory/organize/manager.py:89-118`、`third_party/methods/MemOS/src/memos/memories/textual/tree_text_memory/organize/manager.py:138-248`。

推断/含义：

- MemOS 不是单一写入语义：`general_text` 更像 raw message/vector store，`tree_text` 才是 LLM mem_reader + graph memory 管线。评测记录必须写明使用哪种 text_mem_type，否则“MemOS 机制”会混淆两条完全不同的路径。

## 2. 原生 ingest 形态

事实：

- `BaseTextMemory` 的核心接口是 `extract(messages)`、`add(memories: list[TextualMemoryItem | dict])`、`search(query, top_k, info=None, **kwargs)`、`delete/delete_all/drop`。证据：`third_party/methods/MemOS/src/memos/memories/textual/base.py:20-94`。
- `TextualMemoryMetadata` 原生支持 `user_id`、`session_id`、`status`、`source`、`tags`、`updated_at`、`info` 等字段；tree metadata 还支持 `memory_type`、`sources`、embedding、usage、background、file_ids。证据：`third_party/methods/MemOS/src/memos/memories/textual/item.py:94-162`、`third_party/methods/MemOS/src/memos/memories/textual/item.py:175-215`。
- `SimpleStructMemReader.get_memory()` 的输入是 `scene_data`、`type`、`info`、`mode`，强制 `info` 含字符串 `user_id` 与 `session_id`。证据：`third_party/methods/MemOS/src/memos/mem_reader/simple_struct.py:479-532`。
- chat reader 会把每条消息格式化为 role/content，可保留 `chat_time`；fast mode 直接按窗口构造 `TextualMemoryItem`，fine mode 调 LLM 抽取 key/value/tags/summary。证据：`third_party/methods/MemOS/src/memos/mem_reader/simple_struct.py:320-356`、`third_party/methods/MemOS/src/memos/mem_reader/simple_struct.py:358-429`。
- API add handler 会规范化 writable cube，单 cube 走 `SingleCubeView.add_memories()`，多 cube 走 `CompositeCubeView` fan-out。证据：`third_party/methods/MemOS/src/memos/api/handlers/add_handler.py:41-116`、`third_party/methods/MemOS/src/memos/api/handlers/add_handler.py:118-160`、`third_party/methods/MemOS/src/memos/multi_mem_cube/composite_cube.py:17-44`。
- SingleCubeView 的 add 流程是 get_memory -> flatten -> write_db -> schedule -> format response；响应包含 `memory`、`memory_id`、`memory_type`、`cube_id`。证据：`third_party/methods/MemOS/src/memos/multi_mem_cube/single_cube.py:662-846`。
- MemoryData 集成选择 `text_mem_type: general_text`，配置 Qdrant 本地目录、OpenAI-compatible chat/embedding endpoint、`enable_mem_scheduler: false`。证据：`第三方框架参考/MemoryData/config/hybrid_memos.yaml:1-32`、`第三方框架参考/MemoryData/utils/agent.py:2198-2249`。
- MemoryData ingest 时把 benchmark 的 memorize template 渲染成一段 `formatted_message`，调用 `self.memos.add(memory_content=formatted_message, memorize_mode=self.memos_memorize_mode)`。证据：`第三方框架参考/MemoryData/utils/agent.py:3689-3698`。

推断/含义：

- MemOS 原生最舒服的输入不是整段不可结构化 conversation，而是带 role/content/time 的 messages list，或显式 `TextualMemoryItem` 列表。MemoryData 的 `memory_content` 路径更偏“一段文本直接入库”，对 turn/source 的保留依赖 template 文本本身。

## 3. 检索机制

事实：

- `MOS.search(query, user_id=None, install_cube_ids=None, top_k=None, mode="fast", internet_search=False, session_id=None, ...)` 会按用户可访问 cube fan-out 检索 text/pref memory，并返回 `{"text_mem": [], "act_mem": [], "para_mem": [], "pref_mem": []}`。证据：`third_party/methods/MemOS/src/memos/mem_os/core.py:546-682`。
- 对 general_text，检索是 query embedding -> vector db search -> 按 score 降序 -> 将 payload 还原为 `TextualMemoryItem`；返回的 memory item 本身不保留 vector score 字段。证据：`third_party/methods/MemOS/src/memos/memories/textual/general.py:121-137`。
- 对 tree_text，`TreeTextMemory.search()` 构造 AdvancedSearcher，参数包含 dispatcher_llm、graph_store、embedder、reranker、BM25、internet retriever、search_strategy、include_embedding。证据：`third_party/methods/MemOS/src/memos/memories/textual/tree.py:139-231`。
- tree search 的注释流程是 User query -> TaskGoalParser -> MemoryPathResolver -> GraphMemoryRetriever -> MemoryReranker -> MemoryReasoner -> Final output；fast/fine 模式分别代表较快检索或调用大模型做更精细处理。证据：`third_party/methods/MemOS/src/memos/memories/textual/tree.py:157-198`。
- API search request 支持 `mode`、`top_k`、`relativity`、`dedup`、`rerank`、preference/tool/skill memory 开关、filter、internet_search、search_memory_type 等。证据：`third_party/methods/MemOS/src/memos/api/product_models.py:366-520`。
- SingleCubeView fast search 调 `search_text_memories(... mode=FAST ...)`，然后 `_postformat_memories()` 转成 API dict；fine search 可能调用 searcher.retrieve/post_retrieve、scheduler.retriever enhancement、missing memory recall。证据：`third_party/methods/MemOS/src/memos/multi_mem_cube/single_cube.py:268-384`、`third_party/methods/MemOS/src/memos/multi_mem_cube/single_cube.py:386-469`。
- API formatter 会给每条 memory 添加 `ref_id`，把 `id`、`memory` 放入 metadata，并可清空 embedding/sources；post-process 会按 memory_type 分到 text/tool/skill/pref memory。证据：`third_party/methods/MemOS/src/memos/api/handlers/formatters_handler.py:43-72`、`third_party/methods/MemOS/src/memos/api/handlers/formatters_handler.py:75-138`。
- MemoryData query 阶段调用 `self.memos.search(message, top_k=self.retrieve_num, mode=self.memos_search_mode)`，再从 `text_mem[].memories[]` 抽取 memory 文本，交给统一 answer prompt。证据：`第三方框架参考/MemoryData/utils/agent.py:3700-3725`。

推断/含义：

- retrieve-first 接入可以绕过 `MOS.chat()`，直接用 `MOS.search()`，避免 MemOS 自己生成答案。若选择 `tree_text` fine/deep 路径，检索阶段会包含 LLM query/reasoning/增强调用；若选择 `general_text` fast，则主要是 embedding + vector search。

## 4. 状态与边界行为

事实：

- 完整 self-host Docker compose 启动 `memos`、`neo4j`、`qdrant`，端口包括 8000、7474/7687、6333/6334；memos 依赖 Neo4j 与 Qdrant。证据：`third_party/methods/MemOS/docker/docker-compose.yml:1-71`。
- `GeneralMemCube` 初始化时按配置创建 text/activation/parametric/preference memory；dump/load 会把 config 和各类 memory 写入/读出目录。证据：`third_party/methods/MemOS/src/memos/mem_cube/general.py:21-49`、`third_party/methods/MemOS/src/memos/mem_cube/general.py:50-133`。
- default config 的 `general_text` 使用 Qdrant vector db；`tree_text` 使用 Neo4j graph db，并对 Community Edition 提醒只能用默认 database，必要时以 `user_name` 做隔离。证据：`third_party/methods/MemOS/src/memos/mem_os/utils/default_config.py:131-232`。
- embedder 支持 `ollama`、`sentence_transformer`、`ark`、`universal_api`；universal API 包含 provider、api_key、base_url。证据：`third_party/methods/MemOS/src/memos/configs/embedder.py:8-23`、`third_party/methods/MemOS/src/memos/configs/embedder.py:50-104`。
- `MOSConfig` 以 `user_id` 和 `session_id` 区分用户/会话，并有 `enable_mem_scheduler`、`PRO_MODE`、top_k、max_turns_window 等边界开关。证据：`third_party/methods/MemOS/src/memos/configs/mem_os.py:14-72`。
- tree memory 的 `MemoryManager.add()` 在 sync 模式会清理 WorkingMemory；如果 `is_reorganize` 为真，会把新增节点交给 reorganizer，并提供 `wait_reorganizer()` / `close()` 等等待接口。证据：`third_party/methods/MemOS/src/memos/memories/textual/tree_text_memory/organize/manager.py:89-118`、`third_party/methods/MemOS/src/memos/memories/textual/tree_text_memory/organize/manager.py:243-248`、`third_party/methods/MemOS/src/memos/memories/textual/tree_text_memory/organize/manager.py:549-558`。
- `TreeTextMemory.delete_all()` 清空 graph store，`GeneralTextMemory.delete_all()` 删除并重建 Qdrant collection；`MOS.delete_all()` 调用对应 text_mem 的 delete_all。证据：`third_party/methods/MemOS/src/memos/memories/textual/tree.py:419-426`、`third_party/methods/MemOS/src/memos/memories/textual/general.py:166-173`、`third_party/methods/MemOS/src/memos/mem_os/core.py:1063-1087`。

推断/含义：

- clean retry 需要绑定 user_id + mem_cube_id + collection/db/user_name。general_text 可以删除 collection 或用独立 qdrant_path；tree_text 还要考虑 Neo4j user_name/db 与 reorganizer 是否已 drain。

## 5. 对协议设计的含义

事实：

- MemOS 官方强调 multi-cube KB 用于用户、项目、agent 之间的隔离/共享；API 与配置也以 user_id/mem_cube_id/readable/writable cube ids 为基本边界。证据：`third_party/methods/MemOS/README.md:63-69`、`third_party/methods/MemOS/src/memos/api/product_models.py:136-206`。
- `MOS.chat()` 会先检索 memory，再拼 system prompt，调用 chat LLM 生成答案，并更新 chat history；这不是 retrieve-first 协议所需的检索-only 行为。证据：`third_party/methods/MemOS/src/memos/mem_os/core.py:251-352`。
- `MOS.search()` 已经提供可复用的 retrieval-only 入口；MemoryData 也使用 search 后自行构造 answer prompt。证据：`third_party/methods/MemOS/src/memos/mem_os/core.py:546-682`、`第三方框架参考/MemoryData/utils/agent.py:3700-3725`。
- `SimpleStructMemReader` 的 provenance sources 能记录每条源 message 的 type、index、role、chat_time、content。证据：`third_party/methods/MemOS/src/memos/mem_reader/simple_struct.py:320-356`、`third_party/methods/MemOS/src/memos/memories/textual/item.py:16-47`。

推断/含义：

- 对 MemOS，协议最好提供 messages list + user/session/cube 标识，而不是只给纯文本 conversation。这样 tree_text/fine 能保留 sources，general_text 也能至少写入 user/session metadata。
- 若 Phase 1 追求轻量稳定，MemoryData 的 general_text + local Qdrant 路径更容易控状态，但它没有充分使用 MemOS 的 graph/tree 机制。若追求机制忠实度，tree_text 会引入 Neo4j、mem_reader LLM、scheduler/reorganizer 和更复杂的完成边界。
- retrieve 输出应保留 `memory_id`、`memory_type`、`cube_id`、metadata/source/ref_id；只保留 memory string 会丢掉 MemOS 最有价值的审计线索。

## 6. 未确认项

- MemoryData 的 `self.memos.add(memory_content=..., memorize_mode=...)` 传入了 `memorize_mode`，但 `MOS.add()` 签名只通过 `**kwargs` 接收，源码主流程未读取该字段；它是否在当前 vendored 版本中实际生效未确认。证据：`第三方框架参考/MemoryData/utils/agent.py:3691-3698`、`third_party/methods/MemOS/src/memos/mem_os/core.py:684-923`。
- 本轮未启动 Qdrant/Neo4j/API server，也未进行真实 LLM/embedding 调用；只完成包安装与源码审计。证据：`third_party/methods/MemOS/docker/docker-compose.yml:1-71`、`docs/workstreams/ws02-phase1-matrix/plan-track-a2-method-mechanism.md:14-23`。
- MemOS API server 的 add status/scheduler status 是否能作为统一 finalize 信号，需要后续接入时结合 scheduler handler 实测；本卡只确认库内 `reorganizer.wait_reorganizer()` 和 scheduler submit 存在。证据：`third_party/methods/MemOS/src/memos/memories/textual/tree_text_memory/organize/manager.py:549-558`、`third_party/methods/MemOS/src/memos/multi_mem_cube/single_cube.py:761-806`。
- `general_text` 检索返回的 `TextualMemoryItem` 不包含向量库 score；如果协议需要分数，需要在 Qdrant result -> item 还原处额外保留。证据：`third_party/methods/MemOS/src/memos/memories/textual/general.py:121-137`。
