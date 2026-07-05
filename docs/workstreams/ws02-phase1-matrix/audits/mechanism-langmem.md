# LangMem 机制深读卡片

完成时间：2026-07-05 21:01 CST

## 1. 写入后内部发生什么

事实：

- LangMem 官方定位是“functional primitives + LangGraph storage integration”，提供 hot-path memory tools、background memory manager 和 LangGraph long-term store 集成。证据：`third_party/methods/langmem/README.md:1-17`。
- hot-path 写入入口是 `create_manage_memory_tool(namespace, ...)` 生成的 tool；tool 运行时解析 namespace，然后按 action 执行 `store.put()`/`store.delete()` 或 async 对应方法，写入值形如 `{"content": content}`。证据：`third_party/methods/langmem/src/langmem/knowledge/tools.py:25-39`、`third_party/methods/langmem/src/langmem/knowledge/tools.py:271-337`。
- hot-path 是否写入由 agent tool-call 决定；README 示例中 `create_react_agent` 绑定 `create_manage_memory_tool` 和 `create_search_memory_tool`，普通聊天输入后 agent 自主调用工具写记忆。证据：`third_party/methods/langmem/README.md:30-86`。
- background 写入入口是 `create_memory_store_manager()` 返回 `MemoryStoreManager`；它会先在 namespace 中搜索相关旧记忆，再用 `MemoryManager` 从 messages 和 existing memories 中抽取/更新/删除 memories，最后批量 `store.put()`/`store.delete()`。证据：`third_party/methods/langmem/src/langmem/knowledge/extraction.py:832-897`、`third_party/methods/langmem/src/langmem/knowledge/extraction.py:1006-1137`、`third_party/methods/langmem/src/langmem/knowledge/extraction.py:1139-1280`。
- `MemoryManager` 用 `trustcall.create_extractor()` 绑定 LLM 和 schema，默认 schema 是 `Memory(content: str)`；它接收 `messages`、可选 existing memories 和 `max_steps`，输出 `ExtractedMemory(id, content)`。证据：`third_party/methods/langmem/src/langmem/knowledge/extraction.py:86-93`、`third_party/methods/langmem/src/langmem/knowledge/extraction.py:217-260`、`third_party/methods/langmem/src/langmem/knowledge/extraction.py:536-692`。
- background quickstart 明确 memory 可以 hot path 由 agent conscious tool 保存，也可以 background 从 conversation 自动抽取；示例每轮对话后把 user+response messages 传给 `memory_manager.ainvoke()`。证据：`third_party/methods/langmem/docs/docs/background_quickstart.md:8-16`、`third_party/methods/langmem/docs/docs/background_quickstart.md:31-80`。

推断/含义：

- LangMem 的“写入”不是固定 add API。hot-path 模式是 agent 决策 + tool put/delete；background 模式是 LLM extraction + store search/upsert/delete。benchmark 若需要确定性 ingest，应优先使用 background manager 或直接 store API，而不是让 answer agent 自主决定记忆写入。

## 2. 原生 ingest 形态

事实：

- hot-path manage tool 的逻辑签名是 `manage_memory(content=None, action="create", *, id=None)`，action 可限制为 create/update/delete 子集；创建时不得传 id，更新/删除必须传 id。证据：`third_party/methods/langmem/src/langmem/knowledge/tools.py:59-70`、`third_party/methods/langmem/src/langmem/knowledge/tools.py:271-337`。
- search tool 的逻辑签名是 `search_memory(query, *, limit=10, offset=0, filter=None)`，返回序列化 memories，或在 `content_and_artifact` 模式返回原始 memory objects。证据：`third_party/methods/langmem/src/langmem/knowledge/tools.py:362-487`。
- background manager 原生输入是 `{"messages": list[AnyMessage], "max_steps": int}`，namespace 默认 `("memories", "{langgraph_user_id}")`，可接 `store` 实例或使用 LangGraph context store。证据：`third_party/methods/langmem/src/langmem/knowledge/extraction.py:825-879`、`third_party/methods/langmem/src/langmem/knowledge/extraction.py:1666-1725`。
- namespace 由 `NamespaceTemplate` 解析，支持静态字符串/tuple，也支持从 RunnableConfig 的 `configurable` 字段替换 `{var}`。证据：`third_party/methods/langmem/src/langmem/utils.py:15-91`。
- LightMem/MemBase baseline 的 `LangMemLayer.add_message(message, timestamp=...)` 会把 timestamp 拼进 message content，然后调用 `self.memory_layer.invoke({"messages": [message_copy]}, **kwargs)`；`add_messages(..., message_level=True)` 默认逐条调用。证据：`third_party/methods/LightMem/src/lightmem/memory_toolkits/memories/layers/langmem.py:25-115`、`third_party/methods/LightMem/src/lightmem/memory_toolkits/memories/layers/langmem.py:117-193`。
- mem0 evaluation baseline 使用两个 LangMem agent 分别对应两个 speaker；每条 conversation message 被格式化为 `timestamp | speaker: text`，再调用 `agent.add_memory()` 进入 react agent。证据：`third_party/methods/mem0-main/evaluation/src/langmem.py:59-90`、`third_party/methods/mem0-main/evaluation/src/langmem.py:96-164`。

推断/含义：

- LangMem 最自然的消费单位不是整段 conversation，而是 messages list 或 agent tool call。若要保留 timestamp/session/source，adapter 需要把它编码进 message content、schema，或作为 store value/filter 字段。

## 3. 检索机制

事实：

- search tool 直接调用 `store.search(namespace, query=query, filter=filter, limit=limit, offset=offset)`；检索语义、embedding 和分数由 LangGraph BaseStore 实现决定。证据：`third_party/methods/langmem/src/langmem/knowledge/tools.py:436-474`。
- `create_memory_searcher(model, namespace=...)` 会用 LLM 生成 search_memory tool call，再批量执行 search tool，并按 artifact 的 `score` 倒序排序。证据：`third_party/methods/langmem/src/langmem/knowledge/extraction.py:695-815`。
- `MemoryStoreManager` 在写入前也会检索旧记忆：若配置了 `query_model`，它让 LLM 生成多条 tool calls；否则使用 `get_dialated_windows()` 从最近 messages 构造多个查询窗口，再对 store 执行 search。证据：`third_party/methods/langmem/src/langmem/knowledge/extraction.py:1006-1039`、`third_party/methods/langmem/src/langmem/knowledge/extraction.py:1139-1184`、`third_party/methods/langmem/src/langmem/utils.py:98-119`。
- LightMem/MemBase baseline 的 `retrieve(query, k)` 调 `memory_layer.search(query=query, limit=k)`，返回每条 memory 的 `content` 和除 value 外的 metadata。证据：`third_party/methods/LightMem/src/lightmem/memory_toolkits/memories/layers/langmem.py:194-210`。
- mem0 evaluation baseline 的 search path 仍走 react agent：prompt 先调用 `store.search(("memories",), query=last_message.content)` 注入 system memories，再由 agent answer；最终另有外层 `get_answer()` 把两位 speaker 的 memory responses 拼成 LoCoMo answer prompt。证据：`third_party/methods/mem0-main/evaluation/src/langmem.py:25-56`、`third_party/methods/mem0-main/evaluation/src/langmem.py:85-90`、`third_party/methods/mem0-main/evaluation/src/langmem.py:142-164`。

推断/含义：

- retrieve-first 接入可以直接调用 store/search tool 或 `MemoryStoreManager.search()`，避免 react agent answer。若使用 `create_memory_searcher()`，检索阶段会有 query-generation LLM；若直接 `store.search()`，检索是否调用 embedding/API 取决于 store index 的 embed 配置。

## 4. 状态与边界行为

事实：

- 官方 README 示例使用 `InMemoryStore(index={"dims": 1536, "embed": "openai:text-embedding-3-small"})`；说明 InMemoryStore 在进程内，重启丢失，生产建议使用 AsyncPostgresStore 等持久 store。证据：`third_party/methods/langmem/README.md:40-64`、`third_party/methods/langmem/docs/docs/background_quickstart.md:40-79`。
- manage/search tools 如果没有显式传 `store`，会从 LangGraph runtime `get_store()` 获取；缺少 store 会抛 configuration error。证据：`third_party/methods/langmem/src/langmem/knowledge/tools.py:489-497`、`third_party/methods/langmem/src/langmem/knowledge/extraction.py:897-913`。
- store item 的典型结构包括 namespace、key、value、created_at、updated_at、score；background quickstart 展示 value 为 `{"kind": "Memory", "content": {"content": "..."}}`。证据：`third_party/methods/langmem/docs/docs/background_quickstart.md:82-105`。
- `MemoryStoreManager` 暴露 `put(key, value, index=None, ttl=..., config=None)`、`delete(key)`、`search(query, filter, limit, offset, refresh_ttl)` 等 store wrapper；namespace 从 config 解析。证据：`third_party/methods/langmem/src/langmem/knowledge/extraction.py:1380-1478`、`third_party/methods/langmem/src/langmem/knowledge/extraction.py:1660-1663`。
- LightMem/MemBase baseline 用 `InMemoryStore`，保存时只把 config.json 和 memory key/value pickle；注释说明不保存 vector embeddings，加载时重建 store 并逐条 put 回去。证据：`third_party/methods/LightMem/src/lightmem/memory_toolkits/memories/layers/langmem.py:239-322`。
- LangMem 包自身依赖 LangGraph/LangChain/Trustcall，没有固定本地 DB；持久化、embedding 和 TTL 能力来自所选 BaseStore。证据：`third_party/methods/langmem/pyproject.toml:1-24`。

推断/含义：

- clean retry 的单位应是 namespace + store backend。若使用 InMemoryStore，重建实例即可；若使用持久 store，需要删除 namespace 下 keys 或重建 store/table。写入完成点是 `store.put/delete` 或 `MemoryStoreManager.invoke()` 返回，没有额外 finalize。

## 5. 对协议设计的含义

事实：

- LangMem 的核心隔离机制是 namespace；官方示例用 `("memories", "{langgraph_user_id}")` 这类模板把 user id 从 runtime config 注入。证据：`third_party/methods/langmem/src/langmem/knowledge/tools.py:72-82`、`third_party/methods/langmem/src/langmem/utils.py:15-91`、`third_party/methods/langmem/src/langmem/knowledge/extraction.py:1666-1725`。
- 官方 hot-path 模式强调 agent 自己决定何时保存/搜索；background 模式则允许每轮或延迟处理 messages。证据：`third_party/methods/langmem/README.md:60-86`、`third_party/methods/langmem/docs/docs/background_quickstart.md:8-16`、`third_party/methods/langmem/docs/docs/background_quickstart.md:107-109`。
- LightMem/MemBase baseline 为了适配 benchmark，采用 message-level `add_message()` 并把 timestamp 拼进 content，而不是原生 store metadata。证据：`third_party/methods/LightMem/src/lightmem/memory_toolkits/memories/layers/langmem.py:163-193`。

推断/含义：

- 协议如果提供 `add_turn(messages, namespace, metadata)`，LangMem 可自然映射到 background manager 或 store.put；如果只提供整段 conversation，adapter 需要决定是整段一次抽取还是逐 turn 抽取，两者会影响去重/更新行为。
- 对可复现实验，不宜让 answer agent 自主调用 manage_memory；更可控的是固定 background manager 或直接 store API，并把 query-generation/search/LLM extraction 计入 retrieval/write 成本。
- retrieve 输出应保留 namespace、key、score、value、created_at/updated_at；否则后续 update/delete/provenance 很难审计。

## 6. 未确认项

- MemoryData 目录下没有独立 `methods/langmem/` adapter；本卡使用官方源码、LightMem/MemBase baseline 和 mem0 evaluation baseline 作为集成证据。证据：`第三方框架参考/MemoryData/methods/lightmem/source/lightmem/memory_toolkits/memories/layers/langmem.py:1-6`、`third_party/methods/mem0-main/evaluation/src/langmem.py:1-16`。
- Phase 1 应采用 hot-path tools、background `MemoryStoreManager`，还是直接 BaseStore put/search，需要架构师裁定；三者的 LLM 调用、可复现性和原生忠实度不同。证据：`third_party/methods/langmem/README.md:11-17`、`third_party/methods/langmem/docs/docs/background_quickstart.md:8-16`。
- OpenAI-compatible base_url 和本地 embedding 的配置不在 LangMem 自身参数上，主要落在 LangChain model 初始化和 LangGraph store `embed` 配置；需要后续接入时以项目 settings 显式注入。证据：`third_party/methods/langmem/pyproject.toml:8-17`、`third_party/methods/LightMem/src/lightmem/memory_toolkits/memories/layers/langmem.py:28-61`、`third_party/methods/LightMem/src/lightmem/memory_toolkits/memories/layers/langmem.py:130-151`。
