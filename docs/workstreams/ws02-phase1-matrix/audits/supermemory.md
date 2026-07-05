# Supermemory 审计卡片

完成时间：2026-07-05 17:55 CST

## 1. 来源与形态

- upstream：`https://github.com/supermemoryai/supermemory.git`；MANIFEST hash：`acd2fea9a958361e7add50c1c8c8956a8c5c1814`。
- 形态：TypeScript/Bun monorepo，根 `package.json` 声明 `packageManager: bun@1.3.6`、Node `>=20`；包含 Web app、docs、MCP、browser extension、SDK wrappers、validation schema、memory graph 等包。
- local OSS/self-host：README 明确提供 `curl ... | bash`、`npx supermemory local`、`supermemory-server`，本地 API 运行在 `http://localhost:6767`，数据放 `./.supermemory`。
- Enterprise/cloud：README/文档列出 hosted API、Dashboard、connectors、file processing 等；local-vs-Enterprise 详细差异需要官方 self-host 文档进一步确认。

## 2. 安装可行性

实测命令（第三方目录内 dry-run，未写 lock，未触碰主环境）：

```bash
npm install --dry-run --ignore-scripts --package-lock=false
```

实际输出关键行：

```text
npm error code EUNSUPPORTEDPROTOCOL
npm error Unsupported URL Type "workspace:": workspace:*
npm error A complete log of this run can be found in: /Users/wz/.npm/_logs/2026-07-05T09_54_37_255Z-debug-0.log
```

环境探测输出：

```text
/opt/homebrew/bin/npm
v22.22.1
```

结论：本机没有 `bun`，npm dry-run 不能解析 Bun workspace 依赖，仓库源码安装未通过。README 推荐 local binary / `npx supermemory local`，但本次按零 API、零主环境污染纪律未安装全局工具、未运行 server。

## 3. LLM/embedding 配置面

- local 版 README：首次启动会设置 embedded graph engine、本地 embeddings 和凭据；支持 OpenAI、Anthropic、Gemini、Groq、任意 OpenAI-compatible endpoint；也可指向 Ollama 完全离线。
- SDK/API：`new Supermemory({ apiKey, baseURL: "http://localhost:6767" })` 只需切换 baseURL 即可从云切到 local。
- 仓库内 evidence：`packages/validation/api.ts` 定义 memory/document/search/profile schema；`packages/tools` 与 `packages/openai-sdk-python` 提供 OpenAI/AI SDK middleware，要求 `containerTag` 与 `customId`。
- 可配置到 ohmygpt/gpt-4o-mini：local wizard 理论支持 OpenAI-compatible endpoint；源码中未定位到 local server 的模型配置实现，因为 local binary/server 实现不在显式 `apps/api` 路径下。

## 4. 接口映射（协议中立口径）

- 原生写入粒度：
  - `client.add({ content, containerTag, customId, metadata })` 写 raw context/document；`customId` 可用于 conversation/doc 去重与增量更新。
  - v4 `POST /memories` 可直接创建已知 fact memory：`memories[].content/isStatic/metadata` + `containerTag`。
  - `documents.uploadFile` 支持文件写入。
- 原生检索粒度：
  - `client.search.memories({ q, containerTag, searchMode: "hybrid" | "memories", limit, threshold })` 返回 memory 或 chunk。
  - `client.profile({ containerTag, q? })` 返回 static/dynamic profile，可附带 search results。
- `add(conversation)` 负担：可把整段 conversation 格式化为字符串，使用 `customId=conversation_id` 和 `containerTag=user/run` 调 `add`；Supermemory 自动抽取 facts/profile，但抽取是异步/处理管线，需等待完成。
- `add_turn(role, content, time, metadata)` 负担：可按 turn 追加到同一 `customId`，README 明确支持“只发送新内容”或“发送全量更新内容”；这是较自然的 streaming ingest 形态。
- 会话/用户隔离：`containerTag` 是核心隔离键；`customId` 聚合一段 conversation/document。Phase 1 应用 run_id/sample_id/user_id 组合 containerTag。

## 5. 可插桩性

- SDK middleware 会额外调用 profile/search/add；可在 SDK wrapper 或 HTTP client 层记录 latency、request/response、status。
- local API 如果复用 HTTP API，可用统一 HTTP wrapper 获取端到端延迟；token usage 取决于 local server 是否暴露内部 LLM usage，当前未确认。
- 自动后台处理、profile 更新和 memory extraction 会造成写入完成时间不等于 `add` 返回时间；需要轮询 document status 或使用 local API 提供的 completion signal。

## 6. 风险与工作量分级

分级：M（若 local binary/API 可直接运行）；否则 L（若必须从 Bun monorepo 构建 server）。

top 风险：

- local server 实现未在当前仓库中以简单 Python/TS API server 形式显露，源码构建路径依赖 Bun。
- Hosted/Enterprise 能力多，Phase 1 只能使用用户指定的 local OSS/self-host 口径，不能用云 API 替代。
- 自动 memory extraction/profile 的异步性会影响 benchmark resume 和成本归因。
- provenance：search 返回 memory/chunk、document id、metadata 等是否足够满足每个 benchmark metric，需要实测。

## 7. 未确认项

- local OSS 与 Enterprise 的逐项差异：README 指向官方 local-vs-Enterprise 文档，但本次未联网打开；需要架构师确认是否允许引用在线文档。
- local `supermemory-server` 是否包含完整 documents/memories/profile/hybrid search API 的实现与状态轮询 endpoint。
- local server 是否暴露 LLM/embedding usage；若不暴露，只能外层估算或接管模型 endpoint wrapper。
- 是否可在 CI/本机用 `npx supermemory local` 无交互启动；首次 wizard 如何自动化配置 ohmygpt/Ollama。
