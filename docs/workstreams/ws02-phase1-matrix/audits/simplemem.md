# SimpleMem 审计卡片

完成时间：2026-07-05 17:55 CST

## 1. 来源与形态

- upstream：`https://github.com/aiming-lab/SimpleMem.git`；MANIFEST hash：`60a48e83a7fef10d386e1f438589047d3a4257bc`。
- 形态：Python 包 `simplemem`，`setup.py` 要求 Python `>=3.10`；包含 text、multimodal、MCP、EvolveMem 等多套入口。
- 外部服务：核心 text path 使用 LanceDB 本地库与 SentenceTransformer；仓库也提供 Docker/MCP/server 形态，但 text-only 接入不必先起常驻服务。

## 2. 安装可行性

实测命令（一次性 venv，未触碰主环境）：

```bash
rm -rf /tmp/audit-simplemem && python3 -m venv /tmp/audit-simplemem && /tmp/audit-simplemem/bin/python -m pip install -e third_party/methods/SimpleMem
```

实际输出关键行：

```text
Obtaining file:///Users/wz/Desktop/memoryBenchmark/third_party/methods/SimpleMem
Installing build dependencies: finished with status 'error'
WARNING: Retrying ... SSLCertVerificationError ... /simple/setuptools/
ERROR: Could not find a version that satisfies the requirement setuptools>=40.8.0 (from versions: none)
ERROR: No matching distribution found for setuptools>=40.8.0
```

结论：本机 disposable venv 试装被 PyPI SSL 证书校验阻断，尚未进入 torch / transformers / lancedb 等重依赖解析阶段。主环境未改动。

## 3. LLM/embedding 配置面

- LLM：`simplemem/text/system.py` 与 `main.py` 的 `SimpleMemSystem.__init__` 接收 `api_key`、`model`、`base_url`；`simplemem/core/utils/llm_client.py` 优先使用显式参数，否则读 settings / 环境变量。
- OpenAI-compatible：`LLMClient` 用 OpenAI SDK 初始化，支持 `base_url`，可指向 ohmygpt 并指定 `gpt-4o-mini`。
- embedding：`simplemem/core/utils/embedding.py` 使用本地 SentenceTransformer；text path 默认可不调用 embedding API。
- 依赖风险：默认依赖包含 `torch`、`transformers`、`open_clip_torch`、`librosa` 等，多模态依赖较重，即使 text-only 也可能被 `setup.py` 一次性安装。

## 4. 接口映射（协议中立口径）

- 原生粒度：README quickstart 使用 `SimpleMem().add_dialogue(speaker, content, timestamp)` 多次写入，随后 `finalize()`，最后 `ask(question)`；`add_dialogues` 支持批量 dialogue。
- `add(conversation)` 负担：适合 adapter 遍历 conversation turns 调 `add_dialogue`，并在 conversation 结束调用 `finalize()`；比整段拼接更贴近原生设计。
- `add_turn(role, content, time, metadata)` 负担：最自然。role 可映射 speaker，time 可映射 timestamp；metadata 需要自行保留在外层或扩展字段中，源码公开签名未看到 metadata 参数。
- 会话/用户隔离：可通过不同 db path/table name 或 router 层实例隔离；benchmark 中每个 run/sample 应创建独立路径或明确清理 LanceDB。

## 5. 可插桩性

- LLM 调用集中在 `LLMClient.chat_completion`，适合包裹 usage、latency、错误。
- embedding 是本地 SentenceTransformer encode，通常没有 provider usage；可记录 latency、batch size 和模型名。
- 内部有 parallel 参数和 hybrid retriever/answer generator，延迟拆分需要在 builder/retriever/answerer 层增加 wrapper；不需要改第三方源码即可从 adapter 外层做粗粒度计时。

## 6. 风险与工作量分级

分级：M。

top 风险：

- 安装重依赖多，text-only 仍可能拉起多模态依赖。
- `finalize()` 是必要边界，协议必须显式表达 conversation/session end。
- 多个子系统（SimpleMem router、text system、EvolveMem）入口不统一，需先裁定 Phase 1 使用 text system 还是 auto router。

## 7. 未确认项

- 在只安装 text 所需依赖时能否规避 open_clip/librosa 等多模态包。
- `metadata` 是否有官方扩展点；若没有，benchmark 的 time/session 信息需由 adapter 外部索引保存。
- `ask()` 是否总是由内部 LLM 直接生成答案，还是能返回纯 retrieved context 供 framework reader 使用，需要后续最小源码运行确认。
