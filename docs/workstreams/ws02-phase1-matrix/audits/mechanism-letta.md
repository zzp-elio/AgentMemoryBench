# Letta 机制深读卡片

完成时间：2026-07-05 21:42 CST

## 1. 写入后内部发生什么

事实：

- 当前 `third_party/methods/letta` 是 Python 包 `letta` 0.16.8，描述为 "Create LLM agents with long-term memory and custom tools"，Python 要求 `>=3.11,<3.14`。证据：`third_party/methods/letta/pyproject.toml:1-10`。
- 当前 README 明确该仓库是 legacy Letta server，活跃开发已迁移到 Letta Agent / `letta-code`；V1 SDK 仍可用，但新项目推荐 Agent SDK。证据：`third_party/methods/letta/README.md:1-9`、`third_party/methods/letta/README.md:72-74`。
- Letta 的核心记忆不是单纯 vector store，而是 agent state：base tools 包括 `send_message`、`conversation_search`、`archival_memory_insert`、`archival_memory_search`；memory tools 包括 `core_memory_append`、`core_memory_replace`、`memory`、`memory_apply_patch`。证据：`third_party/methods/letta/letta/constants.py:112-122`。
- prompt 侧会在 history 接近上限时提醒 agent 把重要信息通过 `core_memory_append`、`core_memory_replace` 或 `archival_memory_insert` 保存；也就是说 chat 模式的记忆写入由 agent/tool call 决定。证据：`third_party/methods/letta/letta/constants.py:410-421`。
- 官方当前 server 的 archival insert 路径是 `insert_archival_memory_async(agent_id, memory_contents, actor, tags, created_at)`：先加载 agent state，按 agent model 计 token，超过 `archival_memory_token_limit` 报错，再调用 passage manager 写入。证据：`third_party/methods/letta/letta/server/server.py:856-884`、`third_party/methods/letta/letta/settings.py:463-469`。
- passage 写入会先获取/创建 agent 默认 archive；若 agent 有 embedding config，则用 `LLMClient.request_embeddings` 生成 embedding，然后写 `PydanticPassage`，包含 organization、archive、text、embedding、embedding_config、tags、created_at。证据：`third_party/methods/letta/letta/services/passage_manager.py:543-604`。
- passage 创建会把 embedding 存入 archival passage；Postgres/pgvector 路径会 pad 到 `MAX_EMBEDDING_DIM`，并把 tags 同时写 JSON 字段与 junction table 以便过滤。证据：`third_party/methods/letta/letta/services/passage_manager.py:132-190`。
- MemoryData 实际参考的 vendored Letta 是 `0.7.0`，导出 `LocalClient`、`RESTClient`、`create_client`；这与当前 `third_party/methods/letta` 的 0.16.8 legacy server 不是同一套公开入口。证据：`第三方框架参考/MemoryData/methods/letta/source/letta/__init__.py:1-5`、`third_party/methods/letta/letta/__init__.py:24-47`。

推断/含义：

- Letta 的 faithful 写入有两种语义：让 agent 在 chat loop 中自主选择 memory tools，或绕过 agent loop 直接写 archival passage。前者机制忠实但不可控且会调用作答 LLM；后者可控但更像外部把事实塞进 Letta 的长期语义存储。

## 2. 原生 ingest 形态

事实：

- 当前 server/API 的外部原生粒度是 agent：创建 agent 后，`/{agent_id}/messages` 发送 messages 驱动 agent loop；另有 `/{agent_id}/archival-memory` 可直接插入一条 archival memory。证据：`third_party/methods/letta/letta/server/rest_api/routers/v1/agents.py:1488-1502`、`third_party/methods/letta/letta/server/rest_api/routers/v1/agents.py:1662-1685`。
- direct archival insert 的 API 请求可带 `text`、`tags`、`created_at`，server 层最终落到 `passage_manager.insert_passage(...)`。证据：`third_party/methods/letta/letta/server/rest_api/routers/v1/agents.py:1488-1502`、`third_party/methods/letta/letta/server/server.py:879-884`。
- tool 级 `archival_memory_insert(content, tags)` 的文档建议存 self-contained facts/summaries，而不是 conversational fragments；它被设计为长期、永久、可语义搜索的 memory。证据：`third_party/methods/letta/letta/functions/function_sets/base.py:164-190`。
- `core_memory_append/replace` 原生作用于 agent memory block 的 label/value；append 是简单拼接，replace 要求 old content 精确匹配。证据：`third_party/methods/letta/letta/functions/function_sets/base.py:246-280`。
- MemoryData 默认配置 `letta_mode: insert`，并设置本地 Qwen LLM endpoint、embedding endpoint、chunk size、retrieval page size。证据：`第三方框架参考/MemoryData/config/hybrid_letta.yaml:1-12`、`第三方框架参考/MemoryData/config/hybrid_letta.yaml:14-31`。
- MemoryData 本地 runtime 初始化会设置独立 `LETTA_DIR` / `LETTA_LETTA_DIR`、runtime sqlite 路径、query baseline 目录、retrieval page size，并用 `LLMConfig` / `EmbeddingConfig` 绑定 OpenAI-compatible endpoint。证据：`第三方框架参考/MemoryData/utils/agent.py:1255-1292`、`第三方框架参考/MemoryData/utils/agent.py:1294-1357`。
- MemoryData 创建 agent 时构造 `human` 与 `persona` blocks，再用 `BasicBlockMemory` 和 system prompt 创建 `mm_agent`。证据：`第三方框架参考/MemoryData/utils/agent.py:1359-1385`。
- MemoryData 在 `insert` 模式的 memorizing 阶段不调用 `send_message`，而是直接 `self.client.server.passage_manager.insert_passage(agent_state, agent_id, text=formatted_message, actor=self.client.user)`。证据：`第三方框架参考/MemoryData/utils/agent.py:2708-2728`、`第三方框架参考/MemoryData/utils/agent.py:2746-2766`。

推断/含义：

- Letta 原生最自然的输入是 agent-facing user message 或 self-contained archival memory，而不是整段 benchmark conversation。MemoryData 为了可控写入，选择把 template 渲染后的 context 直接当 archival passage。

## 3. 检索机制

事实：

- API 暴露 direct archival search：`GET /{agent_id}/archival-memory/search`，参数包括 `query`、`tags`、`tag_match_mode`、`top_k`、`start_datetime`、`end_datetime`；它使用与 agent `archival_memory_search` tool 相同的功能。证据：`third_party/methods/letta/letta/server/rest_api/routers/v1/agents.py:1505-1529`。
- server direct search 调 `search_agent_archival_memory_async`，后者按 agent 取 embedding config，解析时间范围，调用 `query_agent_passages_async`，再返回 `id`、`timestamp`、`content`、`tags` 和可选 relevance metadata。证据：`third_party/methods/letta/letta/services/agent_manager.py:2534-2569`、`third_party/methods/letta/letta/services/agent_manager.py:2615-2670`。
- `query_agent_passages_async` 在 `embed_query=True` 且有 embedding config 时，优先做 embedding/vector search；Turbopuffer archive 走 hybrid search，否则 fallback 到 SQL query。证据：`third_party/methods/letta/letta/services/agent_manager.py:2416-2478`。
- SQL fallback 会用 `build_agent_passage_query`，该函数对 query text 生成 embedding 后按 Postgres cosine distance 或 SQLite `cosine_distance` 排序；没有 embedding 时退化为 text contains。证据：`third_party/methods/letta/letta/services/helpers/agent_manager_helper.py:1180-1213`、`third_party/methods/letta/letta/services/helpers/agent_manager_helper.py:1241-1259`。
- conversation search 是另一条路径，搜索 prior conversation history，可按 query、roles、limit、start/end date 过滤；tool executor 版本会过滤 tool messages 和调用 conversation_search 的 assistant messages。证据：`third_party/methods/letta/letta/functions/function_sets/base.py:87-161`、`third_party/methods/letta/letta/services/tool_executor/core_tool_executor.py:81-180`。
- MemoryData `insert` 模式 query 阶段没有直接调用 archival search API；它调用 `self.client.send_message(... role='user')`，再从 Letta response 中抽取最终用户可见回答。证据：`第三方框架参考/MemoryData/utils/agent.py:2720-2728`、`第三方框架参考/MemoryData/utils/agent.py:2751-2766`、`第三方框架参考/MemoryData/utils/agent.py:2794-2810`。
- MemoryData vendored 0.7 的 `archival_memory_search` tool 会 `agent_manager.list_passages(... embed_query=True)` 并格式化为 timestamp/content 列表。证据：`第三方框架参考/MemoryData/methods/letta/source/letta/functions/function_sets/base.py:86-127`。

推断/含义：

- Letta 可以提供 retrieval-only direct archival search，但 MemoryData 当前 query 是 agent answer loop，检索、工具调用和作答混在一起。若接入 retrieve-first 协议，应改用 direct archival search，而不是 `send_message` 的最终回答。

## 4. 状态与边界行为

事实：

- 当前包的基础依赖包括 SQLAlchemy、Alembic、OpenAI、letta-client、LLamaIndex、provider SDK、OTel、FastAPI 等；optional extras 包含 Postgres、Redis、Pinecone、SQLite、server、desktop 等。证据：`third_party/methods/letta/pyproject.toml:11-82`、`third_party/methods/letta/pyproject.toml:87-158`。
- 当前 settings 默认 `LETTA_DIR` 是 `~/.letta`，database engine enum 支持 `postgres` 与 `sqlite`；默认 Postgres URI 为 `postgresql+pg8000://letta:letta@localhost:5432/letta`。证据：`third_party/methods/letta/letta/settings.py:273-281`、`third_party/methods/letta/letta/settings.py:471-489`。
- provider trace backend 默认是 `postgres`，说明成本/trace 侧也默认绑定 server DB。证据：`third_party/methods/letta/letta/settings.py:570-576`。
- REST send_message 明确提示同一个 agent 的并发请求行为未定义，应等待前一请求完成或使用不同 agent/conversation 并行。证据：`third_party/methods/letta/letta/server/rest_api/routers/v1/agents.py:1669-1685`。
- MemoryData 本地 Letta 状态以 agent_save_folder 下的 `agent_id.txt` 和 `letta_runtime/sqlite.db` 判定可复用；query 前会恢复 memorization-only sqlite baseline，并 dispose/重置 Letta DB globals。证据：`第三方框架参考/MemoryData/utils/initialization.py:293-304`、`第三方框架参考/MemoryData/utils/agent.py:1429-1472`、`第三方框架参考/MemoryData/utils/agent.py:1474-1520`。
- API 模式 force reset 会通过 `letta_client.Letta(...).agents.delete(agent_id)` 删除远端/self-hosted agent。证据：`第三方框架参考/MemoryData/utils/initialization.py:442-480`。

推断/含义：

- Clean retry 需要至少绑定 agent_id、actor/user、LETTA_DIR 或 server DB。若使用 agent loop，还要避免 query 阶段新增消息/工具调用污染后续 query；MemoryData 通过 sqlite baseline copy 解决这一点。

## 5. 对协议设计的含义

事实：

- Letta 的 direct archival search 返回条目级 `id`、timestamp、content、tags 和 relevance metadata；这些字段满足 provenance 审计的基础需求。证据：`third_party/methods/letta/letta/services/agent_manager.py:2632-2670`。
- agent loop 的 `send_message` 端点会处理用户消息、可能运行多步工具调用并返回完整 LettaResponse；同一请求可以包含 streaming/background 行为。证据：`third_party/methods/letta/letta/server/rest_api/routers/v1/agents.py:1662-1685`。
- MemoryData 选择直接写 archival passage，是为了避免 memorizing 阶段让 agent 自主决定是否写记忆；但 query 仍让 agent 自己搜索并作答。证据：`第三方框架参考/MemoryData/utils/agent.py:2751-2766`。
- archival insert 的官方建议是写 self-contained fact/summary，而不是 conversational fragments；如果 benchmark 把整段 raw context 塞入 passage，机制忠实度和 Letta 推荐用法存在偏差。证据：`third_party/methods/letta/letta/functions/function_sets/base.py:164-190`。

推断/含义：

- 对 retrieve-first 协议，Letta 最舒服的边界是 `agent_id + archival passage`：add 阶段可直接插入 passages，retrieve 阶段调用 direct archival search，reader 由 framework 统一执行。
- 如果要评估 Letta agent 自主记忆能力，输入粒度应是 sequential user messages，并接受每条 message 都可能触发 LLM/tool/memory edits；这会违反当前 retrieve-first 的“method 不作答”简化口径，需另设任务类型或明确例外。
- 只给 `add(conversation)` 会迫使 adapter 在 raw transcript、summary/fact、或逐 message chat 三者之间做不可见选择；协议最好显式声明是写 raw passage、写 extracted fact，还是让 agent 自主写 memory。

## 6. 未确认项

- 当前 `third_party/methods/letta` 0.16.8 与 MemoryData vendored 0.7.0 的本地 client API 差异较大；Phase 1 真接入应以哪一个为准，需要架构师裁定。证据：`third_party/methods/letta/pyproject.toml:1-10`、`第三方框架参考/MemoryData/methods/letta/source/letta/__init__.py:1-5`。
- 本轮没有启动 Letta server、Postgres/SQLite runtime，也没有创建 agent 或调用 embedding/LLM；只完成 uv 隔离安装与源码审计。证据：`docs/workstreams/ws02-phase1-matrix/plan-track-a2-method-mechanism.md:14-23`、`third_party/methods/letta/letta/services/passage_manager.py:572-604`。
- direct archival search 在 SQLite 与 Postgres/pgvector 下的 score/metadata 一致性未实测；源码显示 SQL fallback metadata 可能为空。证据：`third_party/methods/letta/letta/services/agent_manager.py:2478-2530`、`third_party/methods/letta/letta/services/agent_manager.py:2653-2668`。
- MemoryData 的 `insert` 模式 query 结果是 Letta agent 的最终回答，不是 retrieved memories；如果要复用 MemoryData 路径做 Phase 1 retrieve-first，需要改造 query 阶段。证据：`第三方框架参考/MemoryData/utils/agent.py:2761-2766`、`第三方框架参考/MemoryData/utils/agent.py:2794-2810`。
