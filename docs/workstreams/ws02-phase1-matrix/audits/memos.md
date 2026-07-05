# MemOS 审计卡片

完成时间：2026-07-05 17:55 CST

## 1. 来源与形态

- upstream：`https://github.com/MemTensor/MemOS.git`；MANIFEST hash：`b051e6384d8c667ae7d521baa679f542f4488d19`。
- 形态：Python 包 `MemoryOS`（`pyproject.toml` 版本 2.0.22，Python `>=3.10`），同时提供 API server / Docker 自托管路径。
- 外部服务：Docker compose 包含 `memos`、`neo4j`、`qdrant` 三类服务，端口覆盖 8000、7474/7687、6333/6334。完整图/向量记忆路径需要 Qdrant 与 Neo4j。
- 核心能力：README 描述统一 add/retrieve/manage、memory cube、graph、多模态与 cloud/self-host 两种模式。

## 2. 安装可行性

实测命令（一次性 venv，未触碰主环境）：

```bash
rm -rf /tmp/audit-memos && python3 -m venv /tmp/audit-memos && /tmp/audit-memos/bin/python -m pip install -e third_party/methods/MemOS
```

实际输出关键行：

```text
Obtaining file:///Users/wz/Desktop/memoryBenchmark/third_party/methods/MemOS
Installing build dependencies: finished with status 'error'
WARNING: Retrying ... SSLCertVerificationError ... /simple/poetry-core/
ERROR: Could not find a version that satisfies the requirement poetry-core (from versions: none)
ERROR: No matching distribution found for poetry-core
```

结论：本机 disposable venv 试装被 PyPI SSL 证书校验阻断，尚未验证真实依赖冲突。该失败发生在构建依赖 `poetry-core` 下载阶段，不是主环境污染或 MemOS 源码安装逻辑失败。

## 3. LLM/embedding 配置面

- LLM：`src/memos/configs/llm.py` 中有 OpenAI、Azure、Qwen、DeepSeek、MiniMax、Ollama、HuggingFace、vLLM 等后端配置；OpenAI 类配置包含 `api_key` 与 `api_base`，vLLM 默认使用本地 OpenAI-compatible `/v1` 风格 endpoint。
- 默认快速路径：`src/memos/mem_os/main.py` 的 `MOS.simple()` 读取 `OPENAI_API_KEY`、`OPENAI_API_BASE`、`MOS_TEXT_MEM_TYPE`；未配置 key 会报错。
- embedding：`src/memos/configs/embedder.py` 的 `UniversalAPIEmbedderConfig` 支持 provider/api_key/base_url；`src/memos/embedders/universal_api.py` 用 OpenAI/Azure client 发 embedding 请求。
- 可配置到 ohmygpt/gpt-4o-mini：LLM 可通过 OpenAI-compatible `api_base` 指向转发；embedding 也可通过 base_url 注入。若要零外部 embedding，需要另查是否能稳定走本地 HF/ollama embedder，当前未确认。

## 4. 接口映射（协议中立口径）

- 原生粒度：高层 `MOS.simple()` 示例是 `add_memory("...")` 与 `chat(...)`；底层 `TextualMemoryBase` 提供 `add(memories: list[TextualMemoryItem | dict])` 与 `search(query, top_k, info=None, **kwargs)`；`MOS.chat(query, user_id=None, base_prompt=None)` 内部先检索、再调用 chat LLM 生成答案。
- `add(conversation)` 负担：可把一段 conversation 序列化为文本或 memory item 列表后调用 textual memory `add`；但会丢失 turn 边界、时间戳和角色语义，除非 adapter 自行构造 metadata。
- `add_turn(role, content, time, metadata)` 负担：更贴近 MemOS item 写入，但仍需决定 user/session/memory cube 归属、conversation end 时是否触发重组/调度。
- 会话/用户隔离：`MOS.chat` 支持 `user_id`；memory cube 和配置层有更复杂隔离结构。benchmark adapter 需要显式固定 cube/user/session，以避免跨样本污染。

## 5. 可插桩性

- LLM 调用集中在 llm wrapper 与 `self.chat_llm.generate` 一类入口，可包裹响应 usage 与 latency。
- embedding 调用集中在 universal embedder 的 `embeddings.create`，可在 wrapper 层记录请求、维度、latency；但不同后端 usage 字段不一致。
- 风险：scheduler、memory reorganizer、Redis/RabbitMQ 可引入后台任务；若启用，单次 `add` 的真实成本与完成时刻不一定在同步调用返回前闭合。

## 6. 风险与工作量分级

分级：L。

top 风险：

- 完整能力依赖 Qdrant/Neo4j/API server 与 memory cube 运行态，状态管理重。
- 默认 `MOS.simple()` 强依赖 API key；本地无 API smoke 需要额外配置路径。
- 后台调度/重组会影响可复现性、resume 粒度和成本归因。
- 对 conversation/turn 边界的语义需要 adapter 明确建模，不能只传整段文本。

## 7. 未确认项

- 是否存在推荐的纯本地 embedding 配置，可在 Phase 1 smoke 中避免外部 embedding API。
- 在不启用 scheduler 的最小配置下，textual memory 的检索质量是否足够覆盖 LoCoMo/LongMemEval smoke。
- API server 与纯库模式哪个更适合作为 Phase 1 接入面，需要架构师裁定。
