# Method 资源与参数审计

更新日期：2026-06-22

本文记录 Phase 1 conversation + QA 实验前必须确认的 method 参数和本地资源。当前项目规则：
**smoke 只缩小 benchmark 数据规模，不降低 method 内部官方参数**。这样可以基于局部真实
运行结果估算全量成本；如果 smoke 修改检索深度、模型或压缩参数，局部成本就不再代表
正式实验。

## 通用规则

- smoke 与 official-full 使用同一套 method 算法参数；差异只来自 benchmark 采样范围、
  question 数量和 run_id。
- OpenAI-compatible answer/memory LLM 当前统一使用 `gpt-4o-mini`，除非用户明确决定更换。
- 2026-06-22 起，四个内置 method 的 `retrieve()` 返回完整
  `AnswerPromptResult.answer_prompt`，framework answer LLM 统一负责最终回答。因为 answer
  LLM 已从旧 `get_answer()` 中剥离，必须单独记录 answer LLM 的 model、temperature、
  max_tokens、top_p、timeout 和 retry。当前代码已通过 `AnswerLLMSettings` 显式记录并传递
  method × benchmark 的官方 answer LLM 参数。
- 本地模型必须在真实运行前存在；缺失时 adapter 应在调用第三方核心算法前抛
  `ConfigurationError`。
- 不用 `bge-m3` 替代论文/官方配置里的 `all-MiniLM-L6-v2`，除非另开一个明确的
  custom profile。
- 不在 prediction 阶段计算真实费用；prediction 只记录 token、latency、模型身份和
  observation，费用在实验后离线计算。

## 当前配置矩阵

| Method | 本地/外部资源 | 官方或论文参数 | 当前配置状态 | 运行前阻塞 |
| --- | --- | --- | --- | --- |
| MemoryOS | OpenAI-compatible API；`sentence-transformers/all-MiniLM-L6-v2` 可由 sentence-transformers 缓存/下载 | STM queue=7，MTM max segment=200，User KB/Agent Traits=100，heat threshold=5，retrieval top-m=5，LoCoMo dialogue page top-k=10 | `configs/methods/memoryos.toml` 的 smoke 与 official-full 已一致 | 无新增资源阻塞 |
| Mem0 | OpenAI-compatible API；API embedding `text-embedding-3-small` | OSS benchmark 默认 fact extraction `gpt-4o-mini`、embedding `text-embedding-3-small`；benchmark top-k 默认 200；LoCoMo / LongMemEval answerer 使用 memory-benchmarks 官方 `get_answer_generation_prompt(...)` | `configs/methods/mem0.toml` 的 smoke 与 official-full 均为 `top_k=200`；adapter reader 已按 benchmark 分支调用官方 LoCoMo / LongMemEval prompt；source identity 已纳入两个 prompt 文件；LoCoMo/LongMemEval 当前统一使用 conversation-level resume，不再启用 runner turn-level resume | Mem0 official-full v3 因 embedding API SSL 断连失败；需要补 retry/timeout 后再用小样本 run_id 验证 |
| A-Mem | OpenAI-compatible API；`all-MiniLM-L6-v2` 本地/缓存模型；`rank-bm25`、`litellm` 已安装 | A-Mem Table 1 使用 LoCoMo 五类 QA、F1/BLEU-1；GPT-4o-mini 行的 A-Mem 需要按类别调 `k`：Multi Hop=40、Temporal=40、Open Domain=50、Single Hop=50、Adversarial=40；embedding 为 `all-minilm-l6-v2`；官方 LoCoMo robust 脚本会先用 LLM 生成 query keywords 再检索 | Adapter 已调用官方 `RobustAgenticMemorySystem` 写入/检索；QA wrapper 已补齐 query-keyword generation 等价逻辑，并按 Table 8 对 LoCoMo category 1/2/3/4 使用 40/40/50/50；OpenAI-compatible `base_url` 已在 wrapper 层显式注入官方 OpenAI client；`retrieve_k=10` 仅作为非 LoCoMo/缺 category fallback；conversation 完成后保存 `memories.pkl`、官方 retriever cache/embeddings 和 manifest，支持 conversation-level resume | category 5 adversarial 因官方 prompt 需要 gold answer，当前显式拒绝，不参与普通 public-input smoke；不做 turn-level resume |
| LightMem | OpenAI-compatible API；本地 `models/all-MiniLM-L6-v2`；本地 `models/llmlingua-2-bert-base-multilingual-cased-meetingbank` | Table 2 LongMemEval-S 和 Table 3 LoCoMo 使用 GPT-4o-mini backbone 与 GPT-4o-mini judge；LLMLingua-2 预压缩，attention topic segmentation 也来自 LLMLingua-2；embedding 为 `all-MiniLM-L6-v2`；Table 2 GPT-4o-mini 最优在线行是 `r=0.7, th=512`，另报告 OP-update；Table 3 LoCoMo 报告 `LightMem(0.7,512)`、`LightMem(0.7,768)`、`LightMem(0.8,768)`，ACC 为 offline update 后结果；LightMem LoCoMo README reported retrieval 为 combined `total-limit=60` | 已按用户指定采用 `(r=0.7, th=512)` official-mini：TOML 和 backend config 显式 `compression_rate=0.7`、`stm_threshold=512`；adapter 已按 LightMem 的 LoCoMo / LongMemEval 脚本改为增量批次写入；LongMemEval reader prompt 已包含 `question_time`；LoCoMo 已接入 `add_locomo.py` 的 offline update 顺序，并专门化为 `search_locomo.py` 风格的 Qdrant payload/vector combined 检索与 speaker memory prompt | LongMemEval OP-update 仍未实现为独立 profile；真实 smoke 前仍需用户确认 API 预算、样本规模和 run_id |

## Answer LLM 配置审计

背景：旧链路直接调用每个 method 的 `get_answer()`，answer LLM 参数隐藏在 method 官方脚本
或 wrapper 内部。现在主链路改为：

```text
method.retrieve(question) -> AnswerPromptResult.answer_prompt
framework answer LLM(answer_prompt) -> answer
```

因此 answer LLM 参数必须在框架层显式记录和配置，否则实验不可复现。

### 当前框架实现

当前 `OpenAICompatibleAnswerLLMClient` 位于
`src/memory_benchmark/readers/answer.py`。它调用：

```python
client.chat.completions.create(
    model=settings.model,
    messages=[{"role": "user", "content": answer_prompt}],
)
```

`OpenAISettings` 当前字段：

| 字段 | 当前值/来源 |
| --- | --- |
| `api_key` | `.env` 中 `OPENAI_KEY` 或 `OPENAI_API_KEY` |
| `base_url` | `.env` 中 `BASE_URL` 或 `OPENAI_BASE_URL` |
| `model` | 固定 `gpt-4o-mini` |
| `timeout_seconds` | 默认 `30.0` |
| `max_retries` | 默认 `2` |
| `temperature` | 已由 `AnswerLLMSettings` 按 method × benchmark 显式配置；未设置的官方字段不传 |
| `max_tokens` | 已由 `AnswerLLMSettings` 按 method × benchmark 显式配置；未设置的官方字段不传 |
| `top_p` | 已由 `AnswerLLMSettings` 按 method × benchmark 显式配置；未设置的官方字段不传 |

结论：`AnswerLLMSettings` 已实现。当前可以做 retrieve-first 真实极小 smoke 来验证
链路、artifact、resume 和 observation；正式 full 仍需用户确认 API 预算、run_id 和规模。

### 四个 method 官方 answer LLM 参数

| Method | 事实来源 | 官方 answer LLM 参数 | 当前框架状态 |
| --- | --- | --- | --- |
| Mem0 LoCoMo / LongMemEval | `third_party/methods/mem0-main/memory-benchmarks/benchmarks/common/llm_client.py`；`benchmarks/locomo/run.py`；`benchmarks/longmemeval/run.py` | `LLMClient.generate(system="", user=prompt)` 默认 `temperature=0`、`max_tokens=4096`；官方 CLI 当前默认 `--answerer-model gpt-5`，但本项目阶段一统一指定 `gpt-4o-mini`。OpenAI-compatible client 自带 `max_retries=5`、`timeout=120.0`、`rpm=200`。 | framework answer LLM 现显式传 `temperature=0.0`、`max_tokens=4096`、`message_role=user`；`top_p` 不传。 |
| A-Mem LoCoMo | `third_party/methods/A-mem/test_advanced_robust.py`；`third_party/methods/A-mem/memory_layer_robust.py` | 非 adversarial category 1/2/3/4 的 answer prompt 调 `get_completion(..., temperature=0.7)`；category 5 使用 `temperature_c5=0.5`，但 category 5 需要 gold answer，当前 public-input 规则拒绝。OpenAI controller `max_tokens=1000`，官方 decorator `max_retries=2`。 | framework answer LLM 现显式传 `temperature=0.7`、`max_tokens=1000`、`message_role=user`；`top_p` 不传。category 5 仍不跑。 |
| LightMem LoCoMo | `third_party/methods/LightMem/experiments/locomo/search_locomo.py` | LoCoMo answer 调 `client.chat.completions.create(model=llm_model, messages=[{"role": "system", "content": user_prompt}], temperature=0.0)`；未显式设置 `max_tokens`、`top_p`。 | framework answer LLM 现显式传 `temperature=0.0`、`message_role=system`；`max_tokens`、`top_p` 不传。 |
| LightMem LongMemEval | `third_party/methods/LightMem/experiments/longmemeval/run_lightmem_gpt.py` | `LLMModel` 固定 `max_tokens=2000`、`temperature=0.0`、`top_p=0.8`，`max_retries=3`。 | framework answer LLM 现显式传 `temperature=0.0`、`max_tokens=2000`、`top_p=0.8`、`message_role=user`。 |
| MemoryOS LoCoMo | `third_party/methods/MemoryOS-main/eval/main_loco_parse.py`；`third_party/methods/MemoryOS-main/eval/utils.py` | `client.chat_completion(model="gpt-4o-mini", messages=messages, temperature=0.7, max_tokens=2000)`。 | framework answer LLM 现显式传 `temperature=0.7`、`max_tokens=2000`、`message_role=user`；`top_p` 不传。 |

### 暂定执行口径

`AnswerLLMSettings` 已实现，因此 answer LLM 参数不再阻塞 retrieve-first 极小 smoke。
真实结果仍需等 smoke 验证后再决定是否进入 full。

当前实现口径：

- `AnswerLLMSettings` 字段为 `model`、`message_role`、`temperature`、`max_tokens`、
  `top_p`、`timeout_seconds`、`max_retries`。
- `OpenAICompatibleAnswerLLMClient` 只把非 `None` 的 `temperature`、`max_tokens` 和
  `top_p` 传给 SDK。
- registered prediction 的 method manifest 写入 `answer_reader.answer_parameters`。
- framework answer model inventory 使用最终 `answer_settings.model`。

## API / Network 兜底审计

### Framework answer LLM

当前 framework answer LLM 使用 `OpenAISettings` 读取 API key/base URL，并使用
`AnswerLLMSettings` 控制请求参数：

- 默认 `timeout_seconds=60.0`
- 默认 `max_retries=8`

该兜底已经与 answer 参数结构分离；未来多 provider 实现时应迁入统一
`LLMRuntimeConfig` / `LLMResponse`。

### Method 内部 API

| Method | 当前兜底状态 |
| --- | --- |
| Mem0 | `configs/methods/mem0.toml` 已配置 `api_timeout_seconds=60.0`、`api_max_retries=8`。adapter 在 backend 构造后对 vendored Mem0 LLM 和 embedding client 调 `with_options(timeout=..., max_retries=...)`，不改算法。 |
| A-Mem | `configs/methods/amem.toml` 已配置 `api_timeout_seconds=60.0`、`api_max_retries=8`。adapter 替换官方 robust OpenAI controller client，显式带 `base_url`、timeout 和 max_retries。官方 robust layer 自身还有 `@retry_llm_call(max_retries=2)`，但框架层以 adapter 注入为准。 |
| LightMem | `configs/methods/lightmem.toml` 已配置 `api_timeout_seconds=60.0`、`api_max_retries=8`。adapter 在 `LightMemory` backend 构造后对 `manager.client` 调 `with_options(timeout=..., max_retries=...)`。LongMemEval 官方脚本自身 `LLMModel.call()` 有 `max_retries=3`，当前 adapter 仍以 OpenAI client 注入为主。 |
| MemoryOS | `configs/methods/memoryos.toml` 已配置 `api_timeout_seconds=120`、`api_max_retries=8`、`api_retry_wait_seconds=5`、`api_retry_backoff_multiplier=2`、`api_retry_max_wait_seconds=60`。adapter 把官方 eval client 替换为 `_chat_completion_with_retry()`，SDK 内部 `max_retries=0`，由 adapter 自己处理重试、退避和 usage observation。 |

结论：四个 method 内部 OpenAI-compatible API/network 兜底仍在，且与之前的配置一致。
当前最大的缺口不是 method 内部 API 兜底，而是 framework answer LLM 的采样参数没有显式化。

## A-Mem Table 1 对齐记录

事实来源：

- 论文：`third_party/methods/A-mem/A-mem.pdf`
- 复现实验脚本：`third_party/methods/A-mem/test_advanced_robust.py`
- k 扫描脚本：`third_party/methods/A-mem/run_k_sweep.sh`
- 当前 adapter：`src/memory_benchmark/methods/amem_adapter.py`

论文 Table 1 评测对象是 LoCoMo 五类 QA：Multi Hop、Temporal、Open Domain、Single Hop、
Adversarial。Table 1 的 GPT-4o-mini + A-Mem 结果为：

| Category | F1 | BLEU-1 | Table 8 `k` |
| --- | ---: | ---: | ---: |
| Multi Hop | 27.02 | 20.09 | 40 |
| Temporal | 45.85 | 36.67 | 40 |
| Open Domain | 12.14 | 12.00 | 50 |
| Single Hop | 44.65 | 37.06 | 50 |
| Adversarial | 50.03 | 49.47 | 40 |

论文 4.2 写明：主要使用 `k=10` 以保持计算效率，但会针对特定类别调整 `k` 以优化性能；
Appendix A.5 / Table 8 给出具体类别和模型的 `k`。因此：

- `retrieve_k=10` 是官方 robust 脚本默认值和低成本默认值。
- Table 1 的 GPT-4o-mini 结果不是固定 `k=10` 的结果，而是按 Table 8 类别选择 `k`。
- 仓库 README 也说明需要运行 k-sweep，并按结果调整 `k` 才能达到论文最优表现。

官方 robust QA 调用路径是：

```text
question
-> generate_query_llm(question)
-> retrieve_memory(generated_keywords, k=category/model specific k)
-> category-specific answer prompt
-> answer LLM
```

当前 adapter 调用路径已改为：

```text
question
-> generate_query_keywords(question)
-> find_related_memories_raw(generated_keywords, k=category/model specific k)
-> category-specific answer prompt
-> answer LLM
```

补充约束：A-Mem 官方 adversarial/category 5 prompt 需要 gold answer 构造候选项。由于本
项目禁止把 gold answer 传入 method public input，当前 `official-mini` wrapper 对 category 5
显式抛 `ConfigurationError`，不把它静默降级成普通 QA prompt。

结论：当前 adapter 已对齐 Table 1 GPT-4o-mini profile 中非 adversarial LoCoMo QA 的 query
keyword generation 和 Table 8 类别 `k`。由于 vendored `RobustOpenAIController` 接收
`api_base` 但没有传给 `OpenAI(...)`，adapter 会在 wrapper 层替换官方 controller 的
OpenAI-compatible client，显式带上 `base_url`；该注入不改变 A-Mem 的记忆算法、prompt
或调用顺序。

source identity 已覆盖 A-Mem README、`memory_layer_robust.py`、`llm_text_parsers.py`、
`test_advanced_robust.py`、`run_k_sweep.sh` 和 `requirements.txt`，避免官方 QA/k-sweep
入口变化后旧 run 被错误 resume。

## LightMem Table 2 / Table 3 对齐记录

事实来源：

- 论文：`third_party/methods/LightMem/lightmem.pdf`
- 论文文本抽取：`tmp/pdf_text/lightmem-pymupdf.txt`
- LoCoMo 复现说明：`third_party/methods/LightMem/experiments/locomo/readme.md`
- LoCoMo 构建脚本：`third_party/methods/LightMem/experiments/locomo/add_locomo.py`
- LoCoMo 检索脚本：`third_party/methods/LightMem/experiments/locomo/search_locomo.py`
- LongMemEval 脚本：`third_party/methods/LightMem/experiments/longmemeval/run_lightmem_gpt.py`
- LongMemEval offline update 脚本：
  `third_party/methods/LightMem/experiments/longmemeval/offline_update.py`
- README：`third_party/methods/LightMem/README.md`
- 当前 adapter：`src/memory_benchmark/methods/lightmem_adapter.py`

论文实验设置要点：

- 使用 Incremental Dialogue Turn Feeding：对话历史按 turn 级别逐步输入。
- 使用 LLMLingua-2 做 pre-compressor，topic segmentation 的 attention scores 也来自
  LLMLingua-2。
- sensory memory buffer size 为 512 tokens。
- 使用 LongMemEval-S 和 LoCoMo。
- Table 2 / Table 3 的 GPT 组使用 `gpt-4o-mini` backbone；LLM judge 也是
  `gpt-4o-mini`。
- 效率指标主要统计 memory bank construction 阶段的 Summary / Update token、calls 和
  runtime；retrieval 和 usage 阶段不是论文效率比较重点。
- 论文 Table 4 / Table 5 进一步明确：`fseg()` 是 turn-level granularity input；
  `findex()` 使用 `all-MiniLM-L6-v2`；`fpre_compress()` 和 `ftopic()` 使用
  LLMLingua-2；`fchat()`、`fsum/extract()` 和 `fupdate()` 使用系统 backbone
  `gpt-4o-mini` 等模型。
- Appendix C.1 说明 topic segmentation 主要抽取 user sentences，因为 user 句子通常更
  简洁，assistant responses 在同一 turn 内保持主题一致；官方源码配置中
  `messages_use="user_only"` 与该描述一致。

Table 2 LongMemEval-S 的 GPT-4o-mini LightMem 配置：

| Row | ACC | Summary In/Out(k) | Update In/Out(k) | Total(k) | Calls | Runtime(s) |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| `r=0.5, th=256` | 64.29 | 20.80 / 10.01 | - | 30.81 | 25.67 | 302.69 |
| OP-update for `r=0.5, th=256` | 64.69 | - | 44.46 / 2.56 | 47.02 | 70.23 | 342.63 |
| `r=0.6, th=256` | 67.78 | 24.58 / 10.53 | - | 35.11 | 30.47 | 329.61 |
| OP-update for `r=0.6, th=256` | 65.39 | - | 53.98 / 3.18 | 57.16 | 85.07 | 411.56 |
| `r=0.7, th=512` | 68.64 | 18.88 / 9.37 | - | 28.25 | 18.43 | 283.76 |
| OP-update for `r=0.7, th=512` | 67.07 | - | 79.38 / 4.06 | 83.44 | 125.47 | 496.03 |

Table 3 LoCoMo 的 GPT-4o-mini LightMem 配置：

| Row | ACC | Summary In/Out(k) | Update In/Out(k) | Total(k) | Calls | Runtime(s) |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| `LightMem(0.7,512)` | 71.95 | 73.19 / 20.13 | 6.05 / 0.40 | 99.76 | 41.65 | 848.49 |
| `LightMem(0.7,768)` | 70.26 | 57.54 / 18.92 | 3.79 / 0.23 | 80.48 | 29.55 | 737.80 |
| `LightMem(0.8,768)` | 72.99 | 62.82 / 17.95 | 4.14 / 0.28 | 85.19 | 29.83 | 815.32 |

仓库 LoCoMo README 额外说明 reported retrieval 使用：

```text
--retrieval-mode combined
--total-limit 60
--embedder huggingface
--embedding-model-path all-MiniLM-L6-v2
--llm-model gpt-4o-mini
--judge-model gpt-4o-mini
```

当前对齐状态：

- 用户已指定 LoCoMo / 阶段一 LightMem profile 使用 `(r=0.7, th=512)`。
- `configs/methods/lightmem.toml` 和 `LightMemConfig` 已显式记录
  `compression_rate=0.7`、`stm_threshold=512`。
- backend config 已将 `compress_config.rate` 从旧值 `0.6` 改为 profile 中的
  `0.7`。
- 当前 LightMem 核心初始化 `ShortMemBufferManager(max_tokens=512)` 是源码硬编码；
  因此 adapter 只允许 `th=512`，不会静默运行 Table 3 的 `th=768` 行。
- adapter 已把 `Conversation` 展开成官方脚本粒度：
  LoCoMo 每条原始 turn -> `user(content)+assistant("")`；
  LongMemEval 每个真实 `user+assistant` pair -> 一次 `add_memory()`。
- 只有最后一批写入使用 `force_segment=True, force_extract=True`。
- LoCoMo 写入会传入官方 `METADATA_GENERATE_PROMPT_locomo`。
- LongMemEval reader prompt 已复刻脚本中的
  `Question time:{question_date} and question:{question}` 格式。
- LoCoMo reader prompt 已使用官方 `ANSWER_PROMPT` 的 speaker-organized memory 布局。

已对齐的 LoCoMo 专门化点：

- LightMem 的 LoCoMo `search_locomo.py` 不直接调用 `LightMemory.retrieve()`，而是加载 Qdrant
  entries、使用 query embedding 对 entry vectors 做 cosine similarity，再按 payload 中的
  `speaker_name` 组织 prompt。当前 adapter 的 LoCoMo 分支已复刻这个 combined retrieval
  路径：`embedding_retriever.get_all(with_vectors=True, with_payload=True)` +
  `text_embedder.embed(question)` + top `retrieve_limit`。
- LoCoMo 写入后的 offline update 顺序已在 adapter 的 `add()` 内执行：
  `construct_update_queue_all_entries()` 和
  `offline_update_all_entries(score_threshold=0.9)`。
- 已核实官方 LightMem `Qdrant.get_all()` 返回 `p.model_dump()` 后的 dict list；当前 adapter
  按 dict 读取 `id`、`vector`、`payload`，与
  `experiments/locomo/retrievers.py` 的 `VectorRetriever` 入口一致。

仍未完全对齐的点：

- LongMemEval 的 OP-update 是论文 Table 2 中额外报告的 offline parallel update 行；当前
  adapter 仍保持 `run_lightmem_gpt.py` 的 online `LightMemory.retrieve()` 路径，尚未把
  OP-update 实现为独立 profile。

结论：LightMem fake/offline contract 已覆盖 `(0.7,512)` profile、增量写入、LoCoMo
offline update、LoCoMo `search_locomo.py` 风格 retrieval 和官方 reader prompt。真实 API
smoke 前仍需用户确认 API 预算、样本规模和 run_id。

### LightMem `add_memory()` 调用粒度证据

LightMem 原生接口：

```text
LightMemory.add_memory(
    messages,
    METADATA_GENERATE_PROMPT=None,
    force_segment=False,
    force_extract=False,
    boundmem_tags=None,
) -> dict
```

接口层面 `messages` 可以是一个 message dict 或 `list[dict]`，所以“整段 conversation 一次性
传入”在 Python 类型上可以调用成功；但它不符合论文和复现实验脚本。

论文证据：

- Section 5.1 Experimental Details 写明实验采用 Incremental Dialogue Turn Feeding：
  dialogue history 按 turn level、one turn at a time 喂入。
- Table 4 / Table 5 写明 `fseg()` 是 turn-level granularity input。

README 证据：

- `README.md` 的 Add Memory 示例遍历 `session["turns"]`，对每个 `turn_messages` 添加
  `time_stamp`，再调用 `lightmem.add_memory(messages=turn_messages, ...)`。

LoCoMo 脚本证据：

- `experiments/locomo/add_locomo.py` 将每条 LoCoMo 原始 turn 转成两条 message：
  user content 和空 assistant content。
- 构建阶段按 `turn_idx` 切 `turn_messages = session[turn_idx*2 : turn_idx*2 + 2]`，
  给 pair 内每条 message 写入相同 `time_stamp`。
- 每个 pair 调一次 `add_memory(..., METADATA_GENERATE_PROMPT=METADATA_GENERATE_PROMPT_locomo,
  force_segment=is_last_turn, force_extract=is_last_turn)`。
- `is_last_turn` 只在最后一个 session 的最后一个 pair 为 true。
- 写入完成后脚本备份 pre-update 状态，再调用
  `construct_update_queue_all_entries()` 和 `offline_update_all_entries(score_threshold=0.9)`。

LongMemEval 脚本证据：

- `experiments/longmemeval/run_lightmem_gpt.py` 遍历 `haystack_sessions` 与
  `haystack_dates`。
- 每个 session 同样切 user+assistant pair，并给 pair 内 message 写入同一
  `time_stamp`。
- 每个 pair 调一次 `add_memory(..., force_segment=is_last_turn,
  force_extract=is_last_turn)`。
- 检索阶段调用 `lightmem.retrieve(item["question"], limit=20)`。
- 回答 prompt 显式包含 `Question time:{item['question_date']}`。

结论：本项目 adapter 已把 `Conversation` 展开成官方粒度逐次调用 `add_memory()`，不再把
完整 conversation 一次性传入。对于 LoCoMo official-mini profile，当前已经复刻
`METADATA_GENERATE_PROMPT_locomo` 与 `force_segment/is_last_turn`；offline update 顺序仍是
真实 smoke 前需要确认的剩余项。

## LightMem 本地资源

当前 `models/` 下已有：

```text
models/BAAI/bge-m3
models/nltk
models/all-MiniLM-L6-v2
models/llmlingua-2-bert-base-multilingual-cased-meetingbank
```

LightMem 所需两个本地模型已下载到：

```text
models/all-MiniLM-L6-v2
models/llmlingua-2-bert-base-multilingual-cased-meetingbank
```

来源：

- `sentence-transformers/all-MiniLM-L6-v2`
- `microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank`

当前本地体积：

- `models/all-MiniLM-L6-v2`: 约 956M
- `models/llmlingua-2-bert-base-multilingual-cased-meetingbank`: 约 680M

Adapter 已增加资源前置校验：如果配置指向 `models/...` 或绝对路径但目录不存在，真实
LightMem backend 构造前会抛 `ConfigurationError`。fake/offline 测试不会要求这些模型存在。

## Method add 接口粒度记录

本节记录第三方 method 官方暴露的写入接口、官方实验脚本的实际喂入粒度，以及本项目
adapter 当前实现。`BaseMemorySystem.add(list[Conversation])` 是框架统一入口；
adapter 的职责是把 conversation 展开成目标 method 官方算法期望的最小写入单元。

| Method | 官方暴露写入接口 | 官方实验喂入粒度 | 当前 adapter 喂入粒度 | 结论 |
| --- | --- | --- | --- | --- |
| Mem0 | `Memory.add(messages, run_id/user_id, metadata, ...)` | Mem0 官方 memory-benchmarks 中，LoCoMo `CHUNK_SIZE=1`，即每条格式化 turn/message 一次写入；LongMemEval `CHUNK_SIZE=2`，即 user+assistant pair | 当前 adapter 按来源展开：LoCoMo 每个 turn 调 `Memory.add([message], run_id=conversation_id, ...)`；LongMemEval 每个 session 内按 2 条 message 一组调用 `Memory.add(messages, run_id=conversation_id, ...)` | 写入粒度仍与官方对齐；resume 策略已按用户 2026-06-20 决策统一降为 conversation-level，不再启用 turn-level resume |
| MemoryOS | PyPI/官方接口近似 `add_memory(user_input, agent_response, timestamp, meta_data)`；LoCoMo eval 路径使用 dialogue page / QA pair | user turn + assistant turn 组成一个 dialogue page / QA pair | 当前 adapter 将 turns 配对成 page，再逐 page 调用 MemoryOS 短期记忆写入 | LoCoMo 路径已按 round/page 级展开 |
| A-Mem | `add_note(content, time=...)` / robust wrapper 的 `add_memory(content, time)` | 一条 note，一般对应一条说话内容或片段 | 当前 adapter 展开每个 turn，格式化 speaker/content 后逐 turn 调用 `add_note(...)`；整个 conversation 完成后保存 wrapper 状态 | 写入粒度基本对齐；QA 阶段已补 query keyword generation 和按类别 `k`；category 5 因 gold answer 冲突显式拒绝；resume 粒度为 conversation |
| LightMem | `LightMemory.add_memory(messages, force_segment, force_extract, ...)` | 官方 LoCoMo / LongMemEval 脚本按 user+assistant turn pair 多次调用；仅最后一轮 `force_segment=True, force_extract=True` | 当前 adapter 已按来源展开：LoCoMo 单原始 turn + 空 assistant，LongMemEval 真实 user+assistant pair | 写入粒度已对齐；LoCoMo search 路径和 offline update 已专门化；LongMemEval OP-update 仍是 future profile |

LightMem 的 `OP-update` 已在论文 Table 2 中确认：每组 `r/th` 对应两行，一行是在线 soft
update，一行是 offline parallel update。用户当前指定的 LoCoMo/阶段一 LightMem profile
为 `(r=0.7, th=512)`；后续实现应先保证该 profile 的 online 写入与最终提问流程对齐，再
决定是否在 LongMemEval 上额外支持 OP-update。

## 下一步真实 smoke 建议

在完成上面的算法路径和参数修正后，再确认 API 余额和 run_id，按以下顺序做极小真实 smoke：

1. Mem0 + LoCoMo：已有历史 smoke，但新规则下 `top_k=200` 且 reader prompt 已对齐
   Mem0 memory-benchmarks 官方 LoCoMo prompt，建议重新跑 1 conversation、
   1 question。
2. MemoryOS + LoCoMo：参数已对齐，成本较高，先跑 1 conversation、1 question。
3. A-Mem + LoCoMo：选择非 category 5/adversarial 的 1 conversation、1 question 先跑真实
   smoke；category 5 需另行讨论 gold answer 边界。
4. LightMem + LoCoMo：Table 3 `(0.7,512)` profile、add 粒度、LoCoMo offline update 和
   `search_locomo.py` 风格检索已离线对齐；下一步可在用户确认 API 预算与 run_id 后跑
   1 conversation、1 question。
5. LoCoMo 四个 method 均通过后，再对 LongMemEval-S 做同样极小 smoke；Mem0
   LongMemEval 使用 conversation-level resume，MemoryOS 暂不跑 LongMemEval。

每个 smoke 都必须写入标准 artifacts、logs、checkpoints 和 efficiency observations。不得把
smoke 的结果当作正式指标，只用于验证链路和估算成本。
