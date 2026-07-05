# Supermemory 机制深读卡片

完成时间：2026-07-05 21:06 CST

## 1. 写入后内部发生什么

事实：

- Supermemory 官方定位是面向 agent 的 memory/context layer，会从对话自动学习、抽取事实、维护 profile，并处理更新、矛盾和遗忘。证据：`third_party/methods/supermemory/README.md:33-39`。
- raw content 写入入口是 `client.add({ content, containerTag, metadata })` / `client.add(content=..., container_tag=...)`；文档明确写入后会自动抽取 memories，建议提供 `customId` 以便更新和去重。证据：`third_party/methods/supermemory/apps/docs/add-memories.mdx:8-12`、`third_party/methods/supermemory/apps/docs/add-memories.mdx:23-48`。
- `add` 返回的是异步队列状态，示例响应为 `{ "id": "abc123", "status": "queued" }`，不是立即可检索的完成信号。证据：`third_party/methods/supermemory/apps/docs/add-memories.mdx:71-74`。
- 文档处理状态包括 `queued`、`extracting`、`chunking`、`embedding`、`done`、`failed`；官方建议轮询直到 `done` 或 `failed`。证据：`third_party/methods/supermemory/apps/docs/document-operations.mdx:148-171`。
- 直接 memory 创建是另一条路径：`POST /v4/memories` 接收 1-100 条已知事实，写明这些 memories 会被 embedding 并立即可搜索，适合偏好、traits、结构化事实。证据：`third_party/methods/supermemory/apps/docs/memory-operations.mdx:15-20`、`third_party/methods/supermemory/apps/docs/memory-operations.mdx:79-88`。
- memorybench 的 Supermemory provider ingest 会把每个 session 的 `messages` 整体 `JSON.stringify`，可选加 formattedDate 前缀，再调用 `client.add({ content, containerTag, metadata: { sessionId, date } })`，并保存返回的 document id。证据：`第三方框架参考/memorybench/src/providers/supermemory/index.ts:31-60`。
- memorybench 的完成判据比文档状态更严格：先轮询 `documents.get(docId)`，再查 `memories.get(docId)`，只有 document status 和 memory status 都是 `done` 才认为 indexing 完成。证据：`第三方框架参考/memorybench/src/providers/supermemory/index.ts:62-118`。

推断/含义：

- Supermemory 的原生 raw ingest 是“文档入队 -> 抽取/分块/embedding -> memory/profile/search 可用”的异步服务管线。benchmark adapter 不能把 `add` 返回视为写入完成，至少需要 document done；若沿用 memorybench 口径，还要等对应 memory done。

## 2. 原生 ingest 形态

事实：

- add API 的核心字段是 `content`、`customId`、`containerTag`、`metadata`、`filterByMetadata`、`entityContext`、`dreaming`；metadata 要求键值为字符串/数字/布尔，不能嵌套。证据：`third_party/methods/supermemory/apps/docs/add-memories.mdx:194-205`、`third_party/methods/supermemory/packages/validation/api.ts:82-86`。
- conversation 没有强制 schema；官方文档接受任意字符串格式，包括简单文本、`JSON.stringify` 或 template literal。证据：`third_party/methods/supermemory/apps/docs/add-memories.mdx:127-143`。
- 同一个 `customId` 可用于更新已有内容；可以只发增量，也可以发送完整更新内容，Supermemory 会链接/比较内容。证据：`third_party/methods/supermemory/apps/docs/add-memories.mdx:78-111`。
- 文档更新时，content 变化会触发完整重处理；只改 metadata 不会重新索引。证据：`third_party/methods/supermemory/apps/docs/document-operations.mdx:176-205`。
- 自托管 quickstart 显示本地 SDK 构造需要 `apiKey` 与 `baseURL: "http://localhost:6767"`；写入示例仍是 `client.memories.add({ content, containerTag })` / Python `client.memories.add(content=..., container_tag=...)`。证据：`third_party/methods/supermemory/apps/docs/self-hosting/quickstart.mdx:53-84`。
- memorybench 的原生消费粒度是 session：每个 session 被序列化成一个 raw document，metadata 只保留 `sessionId` 与可选 date。证据：`第三方框架参考/memorybench/src/providers/supermemory/index.ts:31-60`。
- AI SDK/OpenAI/Mastra 工具包还提供 middleware/tool 模式，可按 containerTag/customId 自动检索和自动保存 user message；这属于 agent 集成形态，不是 benchmark 的稳定 ingest API。证据：`third_party/methods/supermemory/packages/tools/README.md:58-80`、`third_party/methods/supermemory/packages/tools/README.md:180-209`。

推断/含义：

- Supermemory 最自然的输入单位是 raw document/session 或一段 conversation transcript。若 Phase 1 要保留 turn 级 provenance，adapter 需要把 turn id、speaker、timestamp 明确编码进 content 或 metadata；否则 Supermemory 返回的 chunk/memory 只能反查到 document/session 级来源。

## 3. 检索机制

事实：

- `search.memories` 支持 `q`、`containerTag`、`searchMode`、`limit`、`threshold`、`rerank`、`filters` 等参数；`searchMode: "hybrid"` 会同时搜索 extracted memories 与 document chunks。证据：`third_party/methods/supermemory/apps/docs/search.mdx:8-12`、`third_party/methods/supermemory/apps/docs/search.mdx:99-130`。
- search 响应包含 results、timing、total；单条 result 可包含 `memory` 或 `chunk`、`similarity`、metadata、updatedAt、version 等字段。证据：`third_party/methods/supermemory/apps/docs/search.mdx:67-90`。
- reranking 是可选项，文档明确会增加延迟，适用于需要更高相关性的场景。证据：`third_party/methods/supermemory/apps/docs/search.mdx:173-185`。
- profile API 返回自动维护的 `static` 长期事实与 `dynamic` 近期上下文；加 `q` 参数时可在一次调用中同时返回 profile 与 search results。证据：`third_party/methods/supermemory/apps/docs/user-profiles.mdx:8-18`、`third_party/methods/supermemory/apps/docs/user-profiles.mdx:79-113`。
- memorybench 检索固定调用 `client.search.memories({ q, containerTag, limit: 30, threshold: options.threshold || 0.3, searchMode: "hybrid", include: { summaries: true, chunks: true } })`，返回 `response.results || []`。证据：`第三方框架参考/memorybench/src/providers/supermemory/index.ts:120-136`。
- memorybench 的 answer prompt builder 会合并 memory summaries 与 raw chunks，且提示 reader 优先使用 chunks 作为详细原始来源。证据：`第三方框架参考/memorybench/src/providers/supermemory/prompts.ts:27-80`、`第三方框架参考/memorybench/src/providers/supermemory/prompts.ts:83-160`。

推断/含义：

- retrieve-first adapter 可以直接使用 `search.memories(..., searchMode="hybrid")`，把返回的 memory/chunk/similarity/metadata 组装给统一 reader。若使用 profile API，返回会混入长期画像和近期动态，适合个性化 agent，但会改变 benchmark retrieval 的粒度和解释边界。

## 4. 状态与边界行为

事实：

- self-hosted local 是一个本地 binary/server，默认 URL 为 `http://localhost:6767`，首次启动会设置嵌入式 graph engine、本地 embeddings 与凭据。证据：`third_party/methods/supermemory/apps/docs/self-hosting/quickstart.mdx:30-47`。
- 默认状态目录是 `./.supermemory/` 或 `$SUPERMEMORY_DATA_DIR`，包含 graph engine data、auth secret、embedding model cache；installer keys 存在 `~/.supermemory/env`。证据：`third_party/methods/supermemory/apps/docs/self-hosting/quickstart.mdx:133-140`。
- local 与 Enterprise 使用相同 API；local 是单机单进程、单自动生成 API key，Enterprise 才有组织级访问控制、dashboard、连接器和弹性扩展。证据：`third_party/methods/supermemory/apps/docs/self-hosting/local-vs-enterprise.mdx:8-24`、`third_party/methods/supermemory/apps/docs/self-hosting/local-vs-enterprise.mdx:45-47`。
- containerTags 是原生隔离机制，可用于 user、project 或其他分组标识。证据：`third_party/methods/supermemory/packages/validation/api.ts:122-130`、`third_party/methods/supermemory/apps/docs/install.md:60-87`。
- v4 memory 操作支持按 id 或 exact content 在 containerTag 范围内 soft-delete 单条 memory，也支持 dryRun 后批量忘记匹配主题。证据：`third_party/methods/supermemory/apps/docs/memory-operations.mdx:122-171`、`third_party/methods/supermemory/apps/docs/memory-operations.mdx:174-215`。
- memorybench provider 的 `clear` 尚未实现，只打印 warning。证据：`第三方框架参考/memorybench/src/providers/supermemory/index.ts:138-140`。

推断/含义：

- clean retry 最简单的边界是独立 containerTag 加独立 local data dir；仅靠 memorybench provider 目前没有可用的清空实现。写入完成边界应是 polling done，而不是 HTTP add 成功。

## 5. 对协议设计的含义

事实：

- 官方安装与集成文档把 `containerTag` 作为 user/org/project 级数据模型决策的核心字段，profile/search/add 都围绕该字段隔离。证据：`third_party/methods/supermemory/apps/docs/install.md:20-32`、`third_party/methods/supermemory/apps/docs/install.md:60-87`。
- add API 接受 raw conversation string，direct memory API 接受已知 atomic facts；两者分别对应“让 Supermemory 抽取”和“调用方已完成抽取”。证据：`third_party/methods/supermemory/apps/docs/add-memories.mdx:127-143`、`third_party/methods/supermemory/apps/docs/memory-operations.mdx:15-20`。
- search 返回 memory 与 chunk 两类结果；memorybench answer prompt 也显式区分 Memory high-level summary/atomic fact 与 Chunks detailed raw content。证据：`third_party/methods/supermemory/apps/docs/search.mdx:111-130`、`第三方框架参考/memorybench/src/providers/supermemory/prompts.ts:83-160`。
- self-hosted 模式允许同一 API 在本地 server 与 Enterprise 间通过 `baseURL` 切换；Phase 1 的 Supermemory 口径应优先绑定 local/self-host。证据：`third_party/methods/supermemory/apps/docs/self-hosting/quickstart.mdx:53-84`、`third_party/methods/supermemory/apps/docs/self-hosting/local-vs-enterprise.mdx:45-47`。

推断/含义：

- 协议若只提供整段 `conversation`，Supermemory 可以自然吞下；若协议要比较 turn/message 级记忆策略，就需要额外规定 `customId`、metadata、session/turn/timestamp 编码和 finalize polling。
- Supermemory 的 retrieve 输出需要保留 result 类型、similarity、metadata、document/chunk 标识和原始 chunk 文本，否则很难审计 answer prompt 中哪些内容来自抽取 memory、哪些来自原文 chunk。
- 本地接入必须把 `baseURL` 作为 method config 的一等字段；否则默认云端 endpoint 会违反 Phase 1 self-host/local OSS 口径。

## 6. 未确认项

- memorybench 的 `getProviderConfig("supermemory")` 读取了 `SUPERMEMORY_BASE_URL`，但 provider 初始化只传 `apiKey`，没有把 `baseUrl` 传给 `new Supermemory(...)`；这会阻碍本地 server 口径，需要后续接入时修正或另写 adapter。证据：`第三方框架参考/memorybench/src/utils/config.ts:11-24`、`第三方框架参考/memorybench/src/providers/supermemory/index.ts:24-29`。
- 本轮没有启动 `supermemory-server`，因此没有实测本地 API 与 cloud v4 endpoint 的完全兼容性；文档声称 local 与 Enterprise 使用相同 API。证据：`third_party/methods/supermemory/apps/docs/self-hosting/quickstart.mdx:131-140`、`third_party/methods/supermemory/apps/docs/self-hosting/local-vs-enterprise.mdx:45-47`。
- self-hosted 首次启动可能需要交互式选择 LLM provider 或配置本地模型；本轮按“零真实 API、零 key”纪律未验证抽取质量、embedding 质量或成本。证据：`third_party/methods/supermemory/apps/docs/self-hosting/quickstart.mdx:49-51`。
- bulk clean retry 是否应删除 containerTag 下 documents、memories，还是重置 `$SUPERMEMORY_DATA_DIR`，需要后续 adapter 设计决定；memorybench provider 暂无 clear。证据：`第三方框架参考/memorybench/src/providers/supermemory/index.ts:138-140`。
