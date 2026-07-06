# Method 原生接口清单

更新日期：2026-07-06

本文记录第三方 method 仓库原生暴露的接口、官方实验脚本的调用方式，以及本项目 adapter
应该如何包装成统一 memory-module 接口。

2026-07-06：provider v3 协议已在代码落地，核心路径为
`MemoryProvider.ingest(unit)` + `retrieve(RetrievalQuery) -> RetrievalResult`。
当前四个内置 method（Mem0、MemoryOS、A-Mem、LightMem）仍通过
`LegacyProviderBridge` 从旧 `BaseMemoryProvider` 桥接运行，manifest 标记
`protocol_version=v2-bridged`、`prompt_track=native`；原生 v3 adapter 迁移属于
M-B 范围，尚未在本清单内逐项改写。

当前代码仍保留旧 `BaseMemorySystem.add(list[Conversation])` /
`BaseMemorySystem.get_answer(question)` 兼容路径；2026-06-21 四个内置 method
adapter 已新增旧式 retrieve-first `BaseMemoryProvider.retrieve(question)`：

```text
add(conversation)
retrieve(question) -> AnswerPromptResult.prompt_messages
framework answer LLM(prompt_messages) -> answer
```

设计文档：
`docs/archive/specs/2026-06-20-retrieve-first-memory-module-design.md`

强规则：

- 新 method 接入目标是 memory-module interface，不再强制实现 `get_answer(question)`。
- adapter 必须实现 method 的官方写入和检索逻辑，并在 `retrieve(question)` 中返回完整
  `AnswerPromptResult.prompt_messages`。这些 role messages 由 method adapter 按官方或
  当前对齐的 method 策略构造，可直接交给 framework answer LLM。
- 如果第三方原始仓库没有统一 retrieve 接口，adapter 必须用其官方 benchmark 的
  search / query rewrite / rerank / prompt 构造逻辑包装出 `retrieve()`。
- `gpt-4o-mini` 是当前阶段唯一真实 LLM 模型选择；不要使用 `gpt-4o`、GPT-5 或其他模型，
  除非用户后续明确改口。
- gold answer、evidence、judge label、LongMemEval `answer_session_ids` 等私有字段不能
  进入 method public input。
- 新 method 未完成本清单记录前，不得启动真实 API smoke。

## 记录模板

每个 method 至少记录：

| 字段 | 需要记录的内容 |
| --- | --- |
| 原生写入接口 | 函数名、输入参数、输出结构、调用粒度 |
| 原生检索接口 | 函数名、输入参数、输出结构、top-k/limit 配置位置 |
| 原生回答/reader流程 | 是否存在 answer/question 接口；如果不存在或不采用，官方 benchmark reader prompt 在哪里 |
| 离线更新接口 | 是否有 offline update / consolidation / maintenance；触发时机 |
| 模型配置 | LLM、embedding、压缩模型、是否本地、是否 API 调用 |
| API 配置 | API key/base URL 传入位置 |
| benchmark profile | LoCoMo / LongMemEval 的官方或论文调用路径 |
| 当前 adapter 状态 | `retrieve()` 包装状态；旧 `get_answer()` 若存在，只记录为 legacy 兼容，不作为新接入要求 |

## Mem0

事实来源：

- `third_party/methods/mem0-main/mem0/memory/main.py`
- `third_party/methods/mem0-main/memory-benchmarks/README.md`
- `third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/run.py`
- `third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/prompts.py`
- `third_party/methods/mem0-main/memory-benchmarks/benchmarks/longmemeval/run.py`
- `third_party/methods/mem0-main/memory-benchmarks/benchmarks/longmemeval/prompts.py`

| 项 | 记录 |
| --- | --- |
| 原生写入接口 | OSS `Memory.add(messages, run_id/user_id, metadata, infer, prompt, ...)`；输入是 message list |
| 官方写入粒度 | memory-benchmarks 中 LoCoMo `CHUNK_SIZE=1`，即每条格式化 turn/message 一次写入；LongMemEval `CHUNK_SIZE=2`，即 user+assistant pair |
| 原生检索接口 | `Memory.search(query, filters, top_k, ...)`；conversation 隔离通过 `run_id`/filter |
| 原生回答接口 | Mem0 OSS 本体没有统一 `answer(question)` |
| 官方回答流程 | memory-benchmarks 使用 `search_results -> get_answer_generation_prompt(...) -> answerer LLM` |
| LoCoMo prompt | `benchmarks/locomo/prompts.py::get_answer_generation_prompt` |
| LongMemEval prompt | `benchmarks/longmemeval/prompts.py::get_answer_generation_prompt` |
| 模型配置 | OSS server 默认 fact extraction `gpt-4o-mini`、embedding `text-embedding-3-small`；当前阶段 answerer/judge 统一改用 `gpt-4o-mini` |
| API 配置 | Mem0 extraction/embedder 和 answerer LLM 都需要从配置层传入 API key/base URL |
| 当前 adapter 状态 | add/search 调官方 OSS；LoCoMo 写入粒度与官方 `CHUNK_SIZE=1` 对齐，LongMemEval 按官方 `CHUNK_SIZE=2` user+assistant pair 写入；当前按用户 2026-06-20 决策统一使用 conversation-level resume，不再启用 runner turn-level resume；`retrieve()` 已保留 search、memory formatting 和官方 LoCoMo / LongMemEval prompt 构造，官方 profile 返回 user-only `AnswerPromptResult.prompt_messages`，通用 fallback 返回 system+user；旧 `get_answer()` 暂时作为兼容 wrapper |

## MemoryOS

事实来源：

- `third_party/methods/MemoryOS-main/memoryos-pypi/memoryos.py`
- `third_party/methods/MemoryOS-main/memoryos-pypi/prompts.py`
- `third_party/methods/MemoryOS-main/eval/main_loco_parse.py`
- `third_party/methods/MemoryOS-main/eval/retrieval_and_answer.py`
- `src/memory_benchmark/methods/memoryos_adapter.py`

| 项 | 记录 |
| --- | --- |
| 原生写入接口 | PyPI/官方语义近似 `add_memory(user_input, agent_response, timestamp, meta_data)` |
| 官方写入粒度 | LoCoMo eval 使用 dialogue page / QA pair，即 user turn + assistant turn |
| 原生检索接口 | eval 路径使用 `retrieval_system.retrieve(query, thresholds, client)` |
| 原生回答接口 | LoCoMo eval 路径使用 `generate_system_response_with_meta(...)` |
| 官方回答流程 | `retrieve(...) -> generate_system_response_with_meta(...)` |
| 模型配置 | 论文优先；当前 LoCoMo 运行使用 `gpt-4o-mini` 与本地/缓存 `all-MiniLM-L6-v2` |
| API 配置 | OpenAI-compatible key/base URL 传给 MemoryOS eval client |
| LongMemEval prompt profile | 默认 `lightmem_longmemeval_reader_v1`，用于和 LightMem LongMemEval QA 流程对比；可选 `memoryos_pypi_generic_v1`，复用 MemoryOS PyPI generic prompt 结构，但它不是 LongMemEval 专用 QA prompt |
| 当前 adapter 状态 | LoCoMo 路径基本按官方 eval wrapper 包装。`retrieve()` 已调用 `retrieval_system.retrieve(...)`；LoCoMo 分支按官方 eval prompt 结构把 retrieval queue 和 long-term knowledge 构造成 system+user `AnswerPromptResult.prompt_messages`；LongMemEval 默认分支复用 LightMem-style reader prompt，并保留 recent context、retrieval queue、user profile、long-term knowledge 和 assistant knowledge；可选 PyPI generic 分支也保留这些上下文。旧 `get_answer()` 暂时保持原官方 `generate_system_response_with_meta(...)` 行为，避免破坏 system prompt observer 和历史复查路径 |

## A-Mem

事实来源：

- `third_party/methods/A-mem/memory_layer_robust.py`
- `third_party/methods/A-mem/test_advanced_robust.py`
- `third_party/methods/A-mem/run_k_sweep.sh`
- `third_party/methods/A-mem/A-mem.pdf`
- `src/memory_benchmark/methods/amem_adapter.py`

| 项 | 记录 |
| --- | --- |
| 原生写入接口 | `RobustAgenticMemorySystem.add_note(content, time)`；robust eval wrapper 也提供 `add_memory(content, time)` |
| 官方写入粒度 | 一条 note，一般对应一条说话内容或片段 |
| 原生检索接口 | `find_related_memories_raw(query, k)`；robust eval wrapper 还有 `retrieve_memory(content, k)` |
| 原生回答接口 | robust eval wrapper 有 `answer_question(question, category, answer)` |
| 官方回答流程 | `generate_query_llm(question) -> retrieve_memory(keywords, k) -> category prompt -> LLM` |
| 私有字段冲突 | `answer_question(..., answer)` 对 adversarial 类别会使用 gold answer 构造二选一 prompt，和本项目普通 public-input 规则冲突 |
| 模型配置 | Table 1 GPT-4o-mini profile 使用 `gpt-4o-mini`；embedding `all-MiniLM-L6-v2`；按类别 Table 8 `k` |
| API 配置 | robust LLM controller 需要 API key/base URL；当前 adapter 在 wrapper 层显式替换官方 OpenAI client，保证 OpenAI-compatible `base_url` 生效 |
| generic reader prompt | 本地 A-Mem 仓库未发现类似 MemoryOS PyPI `prompts.py` 的通用 answer-reader prompt；只有 LoCoMo 评测 reader prompt 和 memory construction/evolution prompt |
| 当前 adapter 状态 | 写入粒度对齐；QA 已补齐官方 `generate_query_llm()` 等价关键词生成和 Table 8 GPT-4o-mini 类别 `k`；category 5 adversarial 因官方 prompt 需要 gold answer，当前按 public-input 规则显式拒绝。`retrieve()` 已保留 query keyword generation、category `k`、retriever 输出和 answer prompt 构造；LoCoMo 使用 A-Mem 官方 prompt 结构，LongMemEval 复用 LightMem-style reader prompt 并填入 A-Mem memory context，返回 system+user `AnswerPromptResult.prompt_messages`；旧 `get_answer()` 暂时作为兼容 wrapper |

## LightMem

事实来源：

- `third_party/methods/LightMem/src/lightmem/memory/lightmem.py`
- `third_party/methods/LightMem/README.md`
- `third_party/methods/LightMem/experiments/locomo/add_locomo.py`
- `third_party/methods/LightMem/experiments/locomo/search_locomo.py`
- `third_party/methods/LightMem/experiments/longmemeval/run_lightmem_gpt.py`
- `third_party/methods/LightMem/experiments/longmemeval/offline_update.py`
- `third_party/methods/LightMem/lightmem.pdf`
- `src/memory_benchmark/methods/lightmem_adapter.py`

| 项 | 记录 |
| --- | --- |
| 原生写入接口 | `LightMemory.add_memory(messages, METADATA_GENERATE_PROMPT=None, force_segment=False, force_extract=False, boundmem_tags=None)`；`messages` 可以是 `dict` 或 `list[dict]`，每条 message 需要 `time_stamp` |
| 写入接口输出 | 返回 dict，通常包含 `add_input_prompt`、`add_output_prompt`、`api_call_nums`；未触发 extraction 时可能返回空统计结构或 segmentation 结果 |
| 官方写入粒度 | 论文 5.1 写明 Incremental Dialogue Turn Feeding：整个 dialogue history 按 turn level、one turn at a time 输入。LoCoMo / LongMemEval 脚本具体实现为 user+assistant turn pair 多次调用 `add_memory()`；仅最后一轮 `force_segment=True, force_extract=True` |
| README 示例 | `README.md` 的 Add Memory 示例也是遍历 `session["turns"]`，对每个 `turn_messages` 添加 `time_stamp` 后调用 `lightmem.add_memory(messages=turn_messages, ...)` |
| LoCoMo 写入流程 | `experiments/locomo/add_locomo.py` 会把每条原始 turn 转成 `[{"role":"user","content":...}, {"role":"assistant","content":""}]`，按 pair 调 `add_memory(..., METADATA_GENERATE_PROMPT=METADATA_GENERATE_PROMPT_locomo, force_segment=is_last_turn, force_extract=is_last_turn)`，之后备份 pre-update、执行 `construct_update_queue_all_entries()` 和 `offline_update_all_entries(score_threshold=0.9)` |
| LongMemEval 写入流程 | `experiments/longmemeval/run_lightmem_gpt.py` 遍历 `haystack_sessions` 和 `haystack_dates`，按 user+assistant pair 调 `add_memory(..., force_segment=is_last_turn, force_extract=is_last_turn)` |
| 原生检索接口 | `LightMemory.retrieve(query, limit, filters, ...)` 返回格式化 memory string list；LightMem 针对 LoCoMo 的 `search_locomo.py` 另有从 Qdrant entries 读取后做 vector retrieval 的评测路径 |
| 原生回答接口 | LightMem 本体没有统一 `answer(question)` |
| 官方回答流程 | 官方实验脚本使用检索结果 + prompt + LLM；LoCoMo `search_locomo.py` 使用 speaker-organized memories 和 `ANSWER_PROMPT`；LongMemEval 脚本直接构造 `Question time:{question_date} and question:{question}` prompt |
| 离线更新接口 | README 和脚本均使用 `construct_update_queue_all_entries()` 与 `offline_update_all_entries(score_threshold=...)`；LoCoMo 脚本为 `score_threshold=0.9`，README 示例和 LongMemEval 独立 `offline_update.py` 为 `0.8` |
| 论文实验细节 | 论文 5.1：使用 LLMLingua-2 作为 pre-compressor；topic segmentation attention scores 也来自 LLMLingua-2；sensory memory buffer size 为 512 tokens；fseg 为 turn-level granularity input；findex 为 `all-MiniLM-L6-v2`；fchat / fsum/extract / fupdate 使用 `gpt-4o-mini` 等 backbone |
| 模型配置 | 用户当前指定 LoCoMo profile `(r=0.7, th=512)`；当前阶段真实 LLM 统一 `gpt-4o-mini`；embedding `all-MiniLM-L6-v2`；LLMLingua-2 本地模型 |
| API 配置 | memory manager 和 answerer LLM 需要 API key/base URL |
| 当前 adapter 状态 | 已改为 adapter 内部按来源展开：LoCoMo 单原始 turn -> `user(content)+assistant("")`，LongMemEval 真实 `user+assistant` pair；仅最后一批 `force_segment=True, force_extract=True`；`r=0.7, th=512` 已进入 config/profile；LoCoMo `add()` 后执行 `construct_update_queue_all_entries()` 与 `offline_update_all_entries(score_threshold=0.9)`；`retrieve()` 已保留 LoCoMo `search_locomo.py` 风格 Qdrant payload/vector combined 检索、LongMemEval `LightMemory.retrieve()` online 路径和 answer prompt 构造，并返回官方 role 结构：LoCoMo system-only、LongMemEval system+user `AnswerPromptResult.prompt_messages`；旧 `get_answer()` 暂时作为兼容 wrapper |
| 已知差异 | LongMemEval OP-update 仍未作为独立 profile 实现；LoCoMo 真实 API smoke 尚未运行，因此不能宣称 Table 3 真实复现完成 |

## Resume 策略分层

该分层吸收 `docs/archive/opencode-suggestions/method-resume-feasibility-analysis.md` 中经源码核验后
可采纳的部分。原则是只在 method 的最小写入单元“完成即持久化”时使用 turn 级 resume；
否则退回 conversation 级，避免 checkpoint 记录的进度和 method 实际持久化状态不一致。

| Method | 当前 resume 级别 | 依据 | 后续任务 |
| --- | --- | --- | --- |
| Mem0 | conversation 级 | 用户 2026-06-19/20 已决定暂时抛弃 turn-level resume；LoCoMo 虽然内部仍按官方 `CHUNK_SIZE=1` 调用，但 runner 不再暴露 turn checkpoint | 不做 turn 级 resume；LoCoMo / LongMemEval 均使用 conversation status |
| MemoryOS | conversation 级 | 官方 LoCoMo eval 以 dialogue page / QA pair 写入，状态落到独立 JSON 目录；当前 adapter 通过 conversation state 目录恢复 | 后续并行时优先做进程隔离，不强行降到 turn 级 |
| A-Mem | conversation 级 | 官方 robust runtime 主要是内存 dict + retriever；当前 wrapper 在 conversation 完成后保存 `memories.pkl`、官方 retriever cache/embeddings 和强校验 manifest | 不做 turn 级 resume；resume 时 registry 对 completed conversations 调 `load_existing_conversation_state()` |
| LightMem | conversation 级 | `add_memory()` 中间调用可能只进入 buffer，只有 force extraction/offline update 后才具备完整持久化语义；resume 时按同一 `storage_root+conversation_id` 重建 backend | 不做 turn 级 resume；LoCoMo `add()` 返回后已执行 offline update，可作为 conversation 完成点；registry 会对 completed conversations 调 `load_existing_conversation_state()` |

question 级 resume 当前由 runner 统一基于 `method_predictions.jsonl` 处理。retrieve-first
迁移后应拆为 retrieval artifact 和 answer artifact：retrieve completed / answer pending
时，resume 应复用已保存的 retrieval result。

## 四个 method 的当前 resume 状态

| Method | 写入记忆 resume | 问问题 resume |
| --- | --- | --- |
| Mem0 | LoCoMo / LongMemEval 均为 conversation-level | 统一基于 `method_predictions.jsonl`、`conversation_status.json` 和 question status；历史 turn-level resume 已禁用 |
| MemoryOS | conversation-level；恢复已有 JSON state 目录 | 统一基于 `method_predictions.jsonl` 和 question status |
| A-Mem | conversation-level；恢复 `memories.pkl`、retriever cache/embeddings 和 manifest | 统一基于 `method_predictions.jsonl` 和 question status |
| LightMem | conversation-level；按同一状态目录重建 LightMemory backend | 统一基于 `method_predictions.jsonl` 和 question status |
