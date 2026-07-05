# Letta 审计卡片

完成时间：2026-07-05 17:55 CST

## 1. 来源与形态

- upstream：`https://github.com/letta-ai/letta.git`；MANIFEST hash：`b76da9092518cbaa2d09042e52fdcbde69243e18`。
- 形态：Python 包 `letta` 0.16.8，Python `>=3.11,<3.14`；README 明确该仓库是 legacy Letta server，活跃开发已迁移到 Letta Agent / `letta-code`。
- 外部服务：server 形态强依赖 Postgres/pgvector；compose 文件包含 `letta_db` 与 `letta_server`，脚本 compose 还包含 Redis。

## 2. 安装可行性

实测命令（一次性 venv，未触碰主环境）：

```bash
rm -rf /tmp/audit-letta && python3 -m venv /tmp/audit-letta && /tmp/audit-letta/bin/python -m pip install -e third_party/methods/letta
```

实际输出关键行：

```text
Obtaining file:///Users/wz/Desktop/memoryBenchmark/third_party/methods/letta
Installing build dependencies: finished with status 'error'
WARNING: Retrying ... SSLCertVerificationError ... /simple/hatchling/
ERROR: Could not find a version that satisfies the requirement hatchling (from versions: none)
ERROR: No matching distribution found for hatchling
```

结论：本机 disposable venv 试装被 PyPI SSL 证书校验阻断，尚未验证大依赖集合。主环境未改动。

## 3. LLM/embedding 配置面

- LLM：`letta/schemas/llm_config.py` 的 `LLMConfig` 支持 `model_endpoint_type`（openai、anthropic、google、azure、ollama、vllm、lmstudio、deepseek、openrouter 等）与 `model_endpoint`。
- 环境变量：`conf.yaml` 与 `config_file.py` 映射 `OPENAI_API_KEY`、`OPENAI_API_BASE`、`VLLM_API_BASE`、`OLLAMA_BASE_URL` 等；Docker compose 透传多 provider key/base URL。
- embedding：`letta/schemas/embedding_config.py` 支持 `embedding_endpoint_type`、`embedding_endpoint`、`embedding_model`、`embedding_dim`；默认 OpenAI text-embedding-3-small，也有 Letta hosted embedding endpoint。
- 可配置到 ohmygpt/gpt-4o-mini：理论上可用 OpenAI endpoint/base 配置；但 active Agent SDK 与 legacy server 配置路径不同，需要选定接入面。

## 4. 接口映射（协议中立口径）

- 原生粒度：Letta 是 agent server。REST `POST /agents` 创建 agent，`POST /{agent_id}/messages` 发送用户消息并跑 agent loop。
- 记忆 API：核心记忆是 agent tool 层，`core_memory_append/replace`、`memory_insert/replace` 操作 agent state memory block；`archival_memory_insert(content, tags)` 与 `archival_memory_search(query, tags, top_k, start/end)` 处理长期语义记忆；`conversation_search(query, roles, limit, start/end)` 搜历史消息。
- `add(conversation)` 负担：没有简单批量 ingest conversation 的 retrieve-first API；可逐条发送 message 让 agent 自主写 memory，或直接调用 server/manager 的 archival memory 插入能力。前者 faithful 但不可控，后者可控但绕过 agent 自主记忆策略。
- `add_turn(role, content, time, metadata)` 负担：可映射为 send_message 序列，但 assistant/tool role 写入和时间戳控制不自然；直接 archival insert 只能写 fact/summary，不是原始对话。
- 会话/用户隔离：agent_id、actor/user、conversation_id 是隔离维度；每个 benchmark sample 应独立 agent 或严格重置 agent state。

## 5. 可插桩性

- Letta 内部有 provider trace backends，可记录 provider request/response、agent/run/step 等元数据；streaming interface 也保存 raw usage。
- REST server/agent loop 工具调用复杂，单个用户消息可能触发多步 LLM、工具、memory edits；需要从 provider trace 或 LLM client wrapper 汇总成本。
- 并发风险显式存在：REST send_message 注释提示同一 agent 并发请求行为未定义，应串行执行或每样本独立 agent。

## 6. 风险与工作量分级

分级：L。

top 风险：

- 仓库是 legacy server；新推荐本地 Agent SDK/CLI 不在当前 vendored 代码内。
- faithful 接入需要运行 server + Postgres/pgvector，并管理 agent 生命周期。
- Agent 自主记忆策略和 retrieve-first benchmark 协议天然张力大。
- 成本归因要跨 agent steps/tool calls/provider traces 汇总。

## 7. 未确认项

- Phase 1 是否审计/接入当前 vendored legacy server，还是需要另行 vendor 新 Letta Agent repo。
- 是否允许直接调用 archival memory insert/search 作为 method 能力，而非通过 send_message 让 agent 自主写记忆。
- 本地 sqlite 可用性与 Postgres/pgvector 是否为 smoke 必需条件，需要最小运行验证。
