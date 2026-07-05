# Track A Method Audit Summary

完成时间：2026-07-05 17:55 CST

## 审计范围

本轮按计划顺序审计 MemOS、SimpleMem、LangMem、Cognee、Letta、Supermemory。全程未调用真实 LLM/embedding API，未填写 API key，未执行 `uv add`，未修改主环境依赖文件；安装验证均在 `/tmp` venv 或第三方目录 dry-run 中完成。

## 总览表

| Method | 形态 | 安装实测 | LLM/embedding 配置 | 接口映射 | 插桩 | 难度 |
| --- | --- | --- | --- | --- | --- | --- |
| SimpleMem | Python 库，text path 可本地 LanceDB/SentenceTransformer | `/tmp` venv 因 PyPI SSL 获取 setuptools 失败 | LLM 支持 OpenAI `base_url`；embedding 默认本地 | `add_dialogue` + `finalize` + `ask`，适合 turn 写入 | LLMClient 与本地 embedding 可包裹 | M |
| LangMem | Python 库，LangGraph store/tool memory | `/tmp` venv 因 PyPI SSL 获取 hatchling 失败 | 依赖 LangChain/LangGraph 配置；自身无直接 base_url 参数 | tool/store memory，namespace 隔离好，但 agent 决策与 deterministic ingest 有张力 | callbacks/store wrapper 可行 | M |
| Supermemory | Bun monorepo + local binary/API + SDK middleware | npm dry-run 不支持 `workspace:*`；需 Bun 或 local binary | local 声称支持 OpenAI-compatible/Ollama；usage 暴露未确认 | `add`/`profile`/`search`/v4 memories，containerTag/customId 贴合 turn/conversation | HTTP wrapper 可行，内部 usage 未确认 | M/L |
| MemOS | Python 包 + API server + Qdrant/Neo4j | `/tmp` venv 因 PyPI SSL 获取 poetry-core 失败 | OpenAI-compatible LLM/embedding 配置明确 | textual add/search + MOS chat；memory cube/user 需建模 | wrapper 可行，后台 scheduler 风险 | L |
| Cognee | Python 包 + API/MCP/server + graph/vector pipeline | `/tmp` venv 因 PyPI SSL 获取 hatchling 失败 | LLM endpoint、embedding endpoint/provider 配置完整 | add+cognify+search 或 remember/recall，多阶段边界重 | pipeline/LLM/embedder 可包裹，需禁后台 | L |
| Letta | legacy Python agent server + Postgres/pgvector | `/tmp` venv 因 PyPI SSL 获取 hatchling 失败 | 多 provider endpoint 支持；legacy/new Agent SDK 分裂 | send_message/agent tools；直接 memory API 与 faithful agent loop 需取舍 | provider trace 强，但多 step 汇总复杂 | L |

## 建议接入顺序

1. SimpleMem：最贴近 turn-level ingest，text-only 路径无需常驻服务，适合作为 Track B 恢复后的首个新 method。
2. LangMem：namespace/store 机制清楚；需先裁定是否允许直接用 store manager，而不是跑 agent 自主 tool。
3. Supermemory：若 local binary 可无交互启动并复用 HTTP API，可排在 M；若必须构建 Bun monorepo，降到 L。
4. MemOS：能力强但状态重；建议在协议定稿后先尝试最小 textual memory 配置。
5. Cognee：graph/vector pipeline 边界重，适合作为多阶段 pipeline 代表，需单独设计 await/cognify 验收。
6. Letta：legacy server 与新 Agent SDK 分裂，且 agent-loop 语义最强；建议等架构师裁定接入面后再动。

## 共性结论

- 新 method 多数不是单纯 `add(conversation) -> retrieve(question)`：SimpleMem、LangMem、Supermemory 更支持 turn/document/namespace；Cognee/MemOS/Letta 都有显式运行态或 pipeline 边界。
- Track 0 的 `add_turn + conversation/session end hook` 方向被审计结果进一步支持。
- 安装验证没有证明包不可用；当前所有 Python 包失败点都是本机一次性 venv 的 PyPI SSL 证书问题。

## 未决问题

- 是否统一要求 method 提供“纯检索 context”，避免内部 answer LLM 与 framework reader 重复作答。
- 对 agent-native method（LangMem、Letta）是否允许绕过 agent 自主记忆决策，使用更确定的 store/memory API。
- Supermemory local OSS 的 API/Enterprise 差异需要架构师决定是否联网核对官方 self-host 文档。
