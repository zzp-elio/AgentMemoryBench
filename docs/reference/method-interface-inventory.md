# Method 原生接口清单

更新日期：2026-07-08

本文记录第三方 method 仓库原生暴露的接口、官方实验脚本的调用方式，以及本项目 adapter
应该如何包装成统一 memory-module 接口。

2026-07-06：provider v3 协议已在代码落地，核心路径为
`MemoryProvider.ingest(unit)` + `retrieve(RetrievalQuery) -> RetrievalResult`。
M-B 已将四个内置 method（Mem0、MemoryOS、A-Mem、LightMem）切到原生
`MemoryProvider` 路径，registry manifest 标记 `protocol_version=v3`、
`prompt_track=native`。`LegacyProviderBridge` 仍保留给未来外部旧式 provider；
四个内置 method 的旧 `add()` / `retrieve(question)` / `get_answer()` 只作为
兼容入口，不再是 registry 主路径。

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
| 当前 adapter 状态 | M-B 后为原生 v3 `MemoryProvider`：LoCoMo 默认 `consume_granularity=turn`，LongMemEval / HaluMem 由 registry 按 benchmark profile 实例级特化为 `session`；`ingest()` 直接复用官方 `Memory.add` 写入序列，`retrieve(RetrievalQuery)` 直接复用官方 search、memory formatting 和 LoCoMo / LongMemEval prompt 构造并返回 `RetrievalResult`。HaluMem 下额外打开 `session_memory_report`，`end_session()` 返回本 session `Memory.add().results[*].memory` 作为 extraction report。旧 `add()` / `retrieve(question)` / `get_answer()` 暂时作为兼容 wrapper |

## MemoryOS

事实来源（ws02.5 迁移后，memoryos-pypi 通用产品引擎，不再用 eval/ LoCoMo 主场副本）：

- `third_party/methods/MemoryOS-main/memoryos-pypi/memoryos.py`（`Memoryos` 类：`add_memory`/`get_response`）
- `third_party/methods/MemoryOS-main/memoryos-pypi/retriever.py`（`Retriever.retrieve_context`）
- `third_party/methods/MemoryOS-main/memoryos-pypi/{short_term,mid_term,long_term,updater,utils}.py`
- `src/memory_benchmark/methods/memoryos_adapter.py`
- 版本裁定与迁移 plan：`docs/workstreams/ws02.5-method-interface-audit/{README.md,plan-memoryos-migration.md}`

| 项 | 记录 |
| --- | --- |
| 原生写入接口 | `Memoryos.add_memory(user_input, agent_response, timestamp=None, meta_data=None)`（memoryos.py:226）|
| 官方写入粒度 | QA pair（user turn + assistant turn）。adapter `consume_granularity` 按 benchmark：LongMemEval→`pair`，LoCoMo→`session`（registry 按 benchmark profile 实例级设，与 LightMem/A-Mem 既有模式一致）。LoCoMo 数据 role=speaker 名，pair 聚合按 `role=="user"` 锚失效，故用 session 粒度由 adapter 内部 `conversation_to_memory_pages` 按 speaker 配对 |
| 写入 LLM 触发 | `add_memory` 满 STM 时触发 `updater.process_short_term_to_mid_term`（LLM：summarize/continuity/meta_info）+ `_trigger_profile_and_knowledge_update_if_needed`（LLM：profile/knowledge 抽取）。fake 测试须 stub `backend.client.chat_completion` |
| orphan/dangling 容错 | dangling user（second=None, role=user）→ `agent_response=""`；orphan assistant（second=None, role≠user）→ `user_input=""`。空串容错已第一手验证通过 |
| 原生检索接口 | pypi **无独立公开 retrieve**；检索埋在 `get_response`（memoryos.py:252-348）步骤 1-7 |
| adapter 检索（剥离） | 复刻 `get_response` 步骤 1-7：`retriever.retrieve_context`（中期 pages + user/assistant knowledge）+ `short_term_memory.get_all`（短期 history）+ `user_long_term_memory.get_raw_user_profile`（长期 profile），组装全层 formatted_memory；**跳过步骤 8-9 答题 LLM 与步骤 10 `add_memory` 写副作用** |
| formatted_memory 全层 | 短期 history + 中期 retrieved_pages + 长期 user_profile + 长期 user_knowledge + 长期 assistant_knowledge（忠实复刻 get_response :270-302）。漏任何一层=记忆不完整=数字失真 |
| 无写副作用契约 | retrieve 不触发 `add_memory`；记忆内容（short_term/profile/user_knowledge/assistant_knowledge）前后不变。注：`retrieve_context` 内部 `search_sessions` 会更新 mid_term 访问统计（N_visit/last_visit_time/H_segment）并 save——这是 MemoryOS 检索算法固有行为（用于 LFU/heat），非 add_memory 写副作用，不改 third_party 无法消除 |
| 原生回答接口 | `get_response`（步骤 8-9 答题 LLM + 步骤 10 add_memory）；adapter **不用**，主线用框架 unified answer prompt（retrieve-first）|
| 参数 | pypi 官方默认（short_term_capacity=10/mid_term_capacity=2000/long_term_knowledge_capacity=100/retrieval_queue_capacity=7/mid_term_heat_threshold=5.0/mid_term_similarity_threshold=0.6），不再用旧 eval/ LoCoMo 调参（旧 7/200 等）|
| 模型配置 | `gpt-4o-mini` + 本地 `all-MiniLM-L6-v2`（pypi 默认）|
| 隔离 | per-conversation 独立 `Memoryos` 实例（user_id + data_storage_path）；clean-retry = 删该 conversation 目录 |
| pypi 包加载 | 目录名含连字符无法作包名；adapter 用 `importlib.util.spec_from_file_location` 加载为命名包 `memoryos_pypi_vendor`（submodule_search_locations），带锁缓存，不污染全局 `utils` |
| 当前 adapter 状态 | 原生 v3 `MemoryProvider`：`consume_granularity` 按 benchmark；`ingest(TurnPair/SessionBatch)`→`add_memory`；`retrieve(RetrievalQuery/Question)` 剥离全层 formatted_memory 无写副作用；旧 `add()`/`get_answer()` 兼容 |

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
| 当前 adapter 状态 | M-B 后为原生 v3 `MemoryProvider`：`consume_granularity=turn`，`ingest(TurnEvent)` 复用官方 robust runtime add 序列，`end_conversation()` 保存 `memories.pkl`、retriever 与 manifest；`retrieve(RetrievalQuery)` 保留 query keyword generation、category `k`、retriever 输出和 LoCoMo / LongMemEval answer prompt 构造并返回 `RetrievalResult`。category 5 adversarial 仍因官方 prompt 需要 gold answer，按 public-input 规则显式拒绝；旧 `add()` / `retrieve(question)` / `get_answer()` 暂时作为兼容 wrapper |

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
| 当前 adapter 状态 | M-B 后为原生 v3 `MemoryProvider`：LoCoMo 默认 `consume_granularity=turn`，LongMemEval 由 registry 按 benchmark profile 实例级特化为 `pair`；`ingest()` 使用一拍缓冲保证最后一批 `force_segment=True, force_extract=True` 与桥接路径一致，`end_conversation()` 执行 LoCoMo `construct_update_queue_all_entries()` 与 `offline_update_all_entries(score_threshold=0.9)`；`retrieve(RetrievalQuery)` 保留 LoCoMo `search_locomo.py` 风格 Qdrant payload/vector combined 检索、LongMemEval `LightMemory.retrieve()` online 路径和 answer prompt 构造并返回 `RetrievalResult`。旧 `add()` / `retrieve(question)` / `get_answer()` 暂时作为兼容 wrapper |
| 已知差异 | LongMemEval OP-update 仍未作为独立 profile 实现；LoCoMo 真实 API smoke 尚未运行，因此不能宣称 Table 3 真实复现完成 |

## SimpleMem

事实来源：

- `docs/workstreams/ws02-phase1-matrix/audits/mechanism-simplemem.md`
- `third_party/methods/SimpleMem/main.py`
- `third_party/methods/SimpleMem/simplemem/core/memory_builder.py`
- `third_party/methods/SimpleMem/simplemem/core/hybrid_retriever.py`
- `third_party/methods/SimpleMem/simplemem/core/answer_generator.py`
- `third_party/methods/SimpleMem/simplemem/core/database/vector_store.py`
- `src/memory_benchmark/methods/simplemem_adapter.py`

| 项 | 记录 |
| --- | --- |
| 原生写入接口 | text backend 主类 `SimpleMemSystem.add_dialogue(speaker, content, timestamp=None)`；该方法把输入包装为 `Dialogue` 后交给 `MemoryBuilder.add_dialogue()` |
| 官方写入粒度 | 单条 dialogue turn；`MemoryBuilder` 以 `WINDOW_SIZE=40` / `OVERLAP_SIZE=2` 攒窗口，完整窗口自动抽取，残余窗口必须在 conversation 末尾显式 `finalize()` |
| 原生检索接口 | `SimpleMemSystem.hybrid_retriever.retrieve(query)`；planning 路径会调用 LLM 做需求分析和 targeted queries，再执行 semantic / keyword / structured search，reflection 打开时可能追加检索 |
| 原生回答接口 | `SimpleMemSystem.ask(question)` 会调用 `hybrid_retriever.retrieve()` 后再调用 `AnswerGenerator.generate_answer()`；本项目 retrieve-first 路径刻意绕开 `ask()`，不让 method 自己生成最终答案 |
| 官方回答流程 | native prompt 复刻 `simplemem/core/answer_generator.py` 的 system message 与 `_build_answer_prompt()` 模板；framework answer LLM 执行最终作答 |
| 离线更新接口 | 无后台 worker；`finalize()` 同步调用 `process_remaining()`，成功返回才算写入完成。finalize 前进程中断会丢失 buffer，retry 必须删除该 isolation 状态并整段重放 |
| 模型配置 | official-text-v1：LLM 显式覆盖为项目统一 `gpt-4o-mini`；embedding 使用本地 `models/Qwen3-Embedding-0.6B`；窗口/top-k 使用官方默认 `40/2/25/5/5` |
| API 配置 | OpenAI-compatible key/base URL 传入 `SimpleMemSystem(api_key, model, base_url, ...)`；embedding 为本地 SentenceTransformers，不产生 API observation |
| 状态隔离 | 每个 `isolation_key` 映射到独立 `method_state/isolation_<sha16>/lancedb` 和固定 table `memories`；wrapper 写公开 `conversation_id.txt` marker，供 failed_ingest clean retry 删除对应 isolation 目录 |
| 当前 adapter 状态 | ws02.4 T1-T6 后为原生 v3 `MemoryProvider`：`consume_granularity=turn`，`ingest(TurnEvent)` 调 `add_dialogue()`，`end_conversation(UnitRef)` 调 `finalize()`；`retrieve(RetrievalQuery)` 直接调用 `hybrid_retriever.retrieve()` 并返回 `formatted_memory`、native `prompt_messages` 和 `RetrievedItem`。LoCoMo / LongMemEval registered fake smoke 已通过；真实 API smoke 待用户确认预算 |
| 已知差异 | 不接 multimodal / EvolveMem / Omni；不做 provenance sidecar，`provenance_granularity=none`；真实 API smoke 尚未运行，不能宣称官方效果复现 |

## HaluMem operation-level 接入状态

HaluMem 在 ws02.2 采用 full operation-level runner，不是普通 conversation-QA
runner。runner 对每个 user 按 session 顺序执行：

```text
ingest(session) -> end_session(extraction report) -> update probes -> QA
```

当前实现状态（2026-07-08）：

- benchmark adapter 已支持 Medium / Long variant、每 user 前 M 个完整 session 的
  smoke 裁剪，CLI 使用 HaluMem 专用 `--sessions`，最小 smoke 为 `--sessions 1`。
- operation-level runner 写公开 input/output artifacts，并新增
  `evaluator_private_session_labels.jsonl` 承载 session 级 gold memory_points +
  dialogue；gold 不进入 method 或 provider report metadata。
- 三个 evaluator 已注册：`halumem-extraction`、`halumem-update`、`halumem-qa`。
  extraction/update 读 session 私有 artifact，QA 读 question 私有 labels。
- Mem0 在 HaluMem 下声明 `consume_granularity=session` 和
  `session_memory_report=True`，可产出 session 增量 extraction report。
- SimpleMem、MemoryOS、A-Mem、LightMem 不提供干净 session 增量 extraction report；
  HaluMem extraction 对这些 method 记 N/A，update + QA 仍按 v3 retrieve 路径运行。
- fake registered 全链路已通过，真实 API smoke 仍需用户确认预算、规模和 run_id。

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
| SimpleMem | conversation 级 | `add_dialogue()` 先进入内存 buffer，完整窗口或 `finalize()` 后才写入 LanceDB；finalize 前中断无法从 LanceDB 恢复残余 buffer | 不做 turn 级 resume；failed_ingest clean retry 删除对应 isolation 目录后整段重放 |

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
| SimpleMem | conversation-level；finalize 前失败通过 clean retry 删除 isolation LanceDB 后整段重放 | 统一基于 `method_predictions.jsonl` 和 question status |
