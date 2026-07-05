# LangMem 审计卡片

完成时间：2026-07-05 17:55 CST

## 1. 来源与形态

- upstream：`https://github.com/langchain-ai/langmem.git`；MANIFEST hash：`c01e273b94aa4c06e41d0ed1ccce0db17de2bc11`。
- 形态：Python 包 `langmem`，版本 0.0.30，Python `>=3.10`；构建后端 `hatchling`。
- 外部服务：核心依赖 LangGraph store；可用 `InMemoryStore`，生产可接 Postgres 等 store。默认 README 示例用 OpenAI embedding 字符串。

## 2. 安装可行性

实测命令（一次性 venv，未触碰主环境）：

```bash
rm -rf /tmp/audit-langmem && python3 -m venv /tmp/audit-langmem && /tmp/audit-langmem/bin/python -m pip install -e third_party/methods/langmem
```

实际输出关键行：

```text
Obtaining file:///Users/wz/Desktop/memoryBenchmark/third_party/methods/langmem
Installing build dependencies: finished with status 'error'
WARNING: Retrying ... SSLCertVerificationError ... /simple/hatchling/
ERROR: Could not find a version that satisfies the requirement hatchling (from versions: none)
ERROR: No matching distribution found for hatchling
```

结论：本机 disposable venv 试装被 PyPI SSL 证书校验阻断，尚未验证 LangGraph/LangChain 依赖兼容性。主环境未改动。

## 3. LLM/embedding 配置面

- LLM：`src/langmem/knowledge/extraction.py` 的 `create_memory_manager` / `create_memory_store_manager` 可接 model 字符串或 chat model；示例使用 `"openai:gpt-4o-mini"`。
- embedding：README 示例中 `InMemoryStore(index={"dims": 1536, "embed": "openai:text-embedding-3-small"})`，embedding 由 LangGraph store 层处理。
- OpenAI-compatible：取决于 LangChain/LangGraph model 初始化与环境变量支持；包自身不直接暴露 `base_url`，需要通过 LangChain provider 配置或传入已构造 model/embedder。
- 本地 embedding：理论上可传自定义 store/index embedder，但此仓库内未看到针对本地 embedding 的直接封装。

## 4. 接口映射（协议中立口径）

- 原生粒度：`create_manage_memory_tool(namespace, store=...)` 提供增删改 memory 的 tool；`create_search_memory_tool(namespace, store=...)` 提供搜索 tool；`MemoryStoreManager` 直接对 `BaseStore.put/search/delete` 操作。
- `add(conversation)` 负担：如果跑完整 agent，是否写入由 agent/tool decision 决定，和 benchmark deterministic ingest 不一致；更可控做法是 adapter 调 MemoryStoreManager 或 store API 手动写入。
- `add_turn(role, content, time, metadata)` 负担：需要把 turn 包装成 memory/doc，并设计 namespace。LangMem 天然以 namespace 隔离，`("{langgraph_user_id}")` 等模板可绑定 user/session。
- 会话/用户隔离：namespace 是核心隔离机制；benchmark 应使用 run_id/sample_id/user_id 组成 namespace，避免 store 复用污染。

## 5. 可插桩性

- LLM/embedding 使用 LangChain/LangGraph 生态，适合通过 callbacks、model wrapper、store wrapper 记录 latency 和 usage。
- 如果使用 agent tools，会出现 agent 自主 tool-call、后台 extraction 的不确定性；如果直接使用 store manager，可插桩性更强但偏离官方 agent memory 用法。
- Store 层 search/put/delete 可包裹，便于记录检索条数、namespace、top_k。

## 6. 风险与工作量分级

分级：M。

top 风险：

- 官方主路径是 agent tool memory，不是 benchmark 的固定写入/检索 API。
- OpenAI-compatible base_url 需落在 LangChain 配置层，非 LangMem 自身显式参数。
- 使用 agent 决策写入会影响可复现；使用 store manager 又需要架构师确认是否算 faithful 接入。

## 7. 未确认项

- Phase 1 是否允许绕过 agent tool 决策，直接调 MemoryStoreManager/store API 写入。
- LangGraph store 的本地 embedding 注入方式和 ohmygpt base_url 配置需要最小运行验证。
- search tool 返回格式能否稳定转换为 `prompt_messages` 所需 context。
