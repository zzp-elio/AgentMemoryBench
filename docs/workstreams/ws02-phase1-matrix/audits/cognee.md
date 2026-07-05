# Cognee 审计卡片

完成时间：2026-07-05 17:55 CST

## 1. 来源与形态

- upstream：`https://github.com/topoteretes/cognee.git`；MANIFEST hash：`f7e2267cf02f5df15c4b60bf196b30ac2c06b32d`。
- 形态：Python 包 `cognee`，版本 1.2.2，Python `>=3.10,<3.15`；同时提供 CLI、API server、MCP server、frontend。
- 外部服务：默认可用本地文件型 SQLite/LanceDB/Ladybug/Kuzu 一类组件；Docker compose 可选 Postgres/PGVector、Neo4j、Redis、MCP、UI。README 将核心操作描述为 `remember`、`recall`、`forget`、`improve`。

## 2. 安装可行性

实测命令（一次性 venv，未触碰主环境）：

```bash
rm -rf /tmp/audit-cognee && python3 -m venv /tmp/audit-cognee && /tmp/audit-cognee/bin/python -m pip install -e third_party/methods/cognee
```

实际输出关键行：

```text
Obtaining file:///Users/wz/Desktop/memoryBenchmark/third_party/methods/cognee
Installing build dependencies: finished with status 'error'
WARNING: Retrying ... SSLCertVerificationError ... /simple/hatchling/
ERROR: Could not find a version that satisfies the requirement hatchling (from versions: none)
ERROR: No matching distribution found for hatchling
```

结论：本机 disposable venv 试装被 PyPI SSL 证书校验阻断，尚未验证依赖冲突。主环境未改动。

## 3. LLM/embedding 配置面

- LLM：`cognee/infrastructure/llm/config.py` 的 `LLMConfig` 暴露 `llm_provider`、`llm_model`、`llm_endpoint`、`llm_api_key`；默认值是 OpenAI 路径。
- OpenAI-compatible：LLM adapter 中多处使用 `api_base=self.endpoint`；可通过 `LLM_ENDPOINT`/配置对象指向 ohmygpt，并把模型设为 `openai/gpt-4o-mini` 或兼容模型名。
- embedding：`EmbeddingConfig` 暴露 `embedding_provider`、`embedding_model`、`embedding_endpoint`、`embedding_api_key`、dimensions；`get_embedding_engine.py` 支持 `fastembed`、`ollama`、`openai_compatible`、LiteLLM。
- 本地 embedding：`fastembed` 和 `ollama` 可作为本地候选，但是否满足 benchmark 质量/维度需后续 smoke 决定。

## 4. 接口映射（协议中立口径）

- 原生粒度：低层 `add(data, dataset_name=..., user=..., run_in_background=False, llm_config=None, embedding_config=None)` 接收文本、文件、URL、binary、列表；随后 `cognify(datasets=...)` 构图；`search(query_text, query_type=..., top_k=..., only_context=False, session_id=None)` 查询。
- 高层粒度：`remember(data, dataset_name, session_id=None, ...)` 无 `session_id` 时执行 add+cognify，带 `session_id` 时写 session cache 并可后台同步；`recall(query_text, top_k=..., session_id=None, only_context=False, include_references=False)` 检索。
- `add(conversation)` 负担：可把 conversation 格式化为一段 raw content 后 `remember/add+cognify`，但会把 turn 边界作为文本处理；也可按 turn 多次 `remember(..., session_id=...)`，再依赖 improve/background 同步。
- `add_turn(role, content, time, metadata)` 负担：session memory 更贴近 turn 写入，但永久 graph 需要 `improve` 或 cognify 边界；协议需表达何时构图完成。
- 会话/用户隔离：`dataset_name`、`dataset_id`、`user`、`session_id` 都可作为隔离维度；benchmark 应固定 dataset/user/session 三元组。

## 5. 可插桩性

- LLM 通过 LiteLLM/instructor adapter 与 `get_llm_client` 汇聚，可在 config 或 client wrapper 层记录 usage/latency。
- embedding 通过 `get_embedding_engine` 汇聚，支持本地和 API 路径；可 wrapper 记录 batch 与 latency。
- 内部 pipeline 支持 `run_in_background`，并有 observability span；必须禁用后台或显式 await pipeline run，否则成本和完成时间难闭合。

## 6. 风险与工作量分级

分级：L。

top 风险：

- 需要 ingestion、cognify、search 多阶段，且 graph/vector/relational 配置面宽。
- 默认搜索类型 `GRAPH_COMPLETION` 会调用 LLM 生成答案；retrieve-first 协议更适合 `only_context=True` 或 raw chunk/graph search，需要验证。
- Docker/服务形态较多，最小 faithful 配置需架构师裁定。

## 7. 未确认项

- Phase 1 是否使用高层 `remember/recall`，还是低层 `add+cognify+search(only_context=True)`。
- 默认文件型 graph/vector 后端在并发 benchmark 下是否稳定；是否需要 Postgres/Neo4j。
- `include_references` 返回的 provenance 粒度是否满足后续 metric 审计。
