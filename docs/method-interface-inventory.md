# Method 原生接口清单

更新日期：2026-06-18

本文记录第三方 method 仓库原生暴露的接口、官方实验脚本的调用方式，以及本项目 adapter
应该如何包装成统一 `BaseMemorySystem.add()` / `BaseMemorySystem.get_answer()`。

强规则：

- conversation + QA benchmark 在框架层一定需要 `get_answer(question)`。
- 如果第三方原始仓库没有同名 answer 接口，adapter 必须用该 method 官方 benchmark 的
  `retrieval/search + prompt + LLM` 流程包装出 `get_answer()`。
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
| 原生回答接口 | 是否存在 answer/question 接口；如果不存在，官方 benchmark reader prompt 在哪里 |
| 离线更新接口 | 是否有 offline update / consolidation / maintenance；触发时机 |
| 模型配置 | LLM、embedding、压缩模型、是否本地、是否 API 调用 |
| API 配置 | API key/base URL 传入位置 |
| benchmark profile | LoCoMo / LongMemEval 的官方或论文调用路径 |
| 当前 adapter 状态 | 已对齐、部分对齐、阻塞项 |

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
| 当前 adapter 状态 | add/search 调官方 OSS；LoCoMo 写入粒度与官方 `CHUNK_SIZE=1` 对齐并启用 turn-level resume；LongMemEval 按官方 `CHUNK_SIZE=2` user+assistant pair 写入，并由 runner 使用 conversation-level resume；reader 已按 benchmark 分支调用 Mem0 memory-benchmarks 官方 LoCoMo / LongMemEval `get_answer_generation_prompt(...)`；未知 benchmark 保留通用 fallback |

## MemoryOS

事实来源：

- `third_party/methods/MemoryOS-main/memoryos-pypi/memoryos.py`
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
| 当前 adapter 状态 | LoCoMo 路径基本按官方 eval wrapper 包装；MemoryOS LongMemEval 短期不跑 |

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
| 当前 adapter 状态 | 写入粒度对齐；QA 已补齐官方 `generate_query_llm()` 等价关键词生成和 Table 8 GPT-4o-mini 类别 `k`；category 5 adversarial 因官方 prompt 需要 gold answer，当前按 public-input 规则显式拒绝 |

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
| 当前 adapter 状态 | 已改为 adapter 内部按来源展开：LoCoMo 单原始 turn -> `user(content)+assistant("")`，LongMemEval 真实 `user+assistant` pair；仅最后一批 `force_segment=True, force_extract=True`；`r=0.7, th=512` 已进入 config/profile；LoCoMo `add()` 后执行 `construct_update_queue_all_entries()` 与 `offline_update_all_entries(score_threshold=0.9)`；LoCoMo `get_answer()` 使用 `search_locomo.py` 风格 Qdrant payload/vector combined 检索和 speaker-organized prompt；LongMemEval `get_answer()` 保持 `LightMemory.retrieve()` + `question_time` prompt |
| 已知差异 | LongMemEval OP-update 仍未作为独立 profile 实现；LoCoMo 真实 API smoke 尚未运行，因此不能宣称 Table 3 真实复现完成 |

## Resume 策略分层

该分层吸收 `docs/opencode-suggestions/method-resume-feasibility-analysis.md` 中经源码核验后
可采纳的部分。原则是只在 method 的最小写入单元“完成即持久化”时使用 turn 级 resume；
否则退回 conversation 级，避免 checkpoint 记录的进度和 method 实际持久化状态不一致。

| Method | 当前 resume 级别 | 依据 | 后续任务 |
| --- | --- | --- | --- |
| Mem0 | LoCoMo turn 级；LongMemEval conversation 级 | LoCoMo 官方 `CHUNK_SIZE=1`，每次 `Memory.add([message], run_id=...)` 完成完整写入；LongMemEval 官方 `CHUNK_SIZE=2` user+assistant pair，不适合 turn checkpoint | `supports_turn_resume()` 已按 conversation 分流；LoCoMo 使用 turn checkpoint，LongMemEval 使用 conversation status |
| MemoryOS | conversation 级 | 官方 LoCoMo eval 以 dialogue page / QA pair 写入，状态落到独立 JSON 目录；当前 adapter 通过 conversation state 目录恢复 | 后续并行时优先做进程隔离，不强行降到 turn 级 |
| A-Mem | conversation 级 | 官方 robust runtime 主要是内存 dict + retriever；当前 wrapper 在 conversation 完成后保存 `memories.pkl`、官方 retriever cache/embeddings 和强校验 manifest | 不做 turn 级 resume；resume 时 registry 对 completed conversations 调 `load_existing_conversation_state()` |
| LightMem | conversation 级 | `add_memory()` 中间调用可能只进入 buffer，只有 force extraction/offline update 后才具备完整持久化语义；resume 时按同一 `storage_root+conversation_id` 重建 backend | 不做 turn 级 resume；LoCoMo `add()` 返回后已执行 offline update，可作为 conversation 完成点；registry 会对 completed conversations 调 `load_existing_conversation_state()` |

question 级 resume 由 runner 统一基于 `method_predictions.jsonl` 处理。当前四个 method 的
`get_answer()` 都按只读路径设计，不应修改 method 记忆状态。

## 四个 method 的当前 resume 状态

| Method | 写入记忆 resume | 问问题 resume |
| --- | --- | --- |
| Mem0 | LoCoMo 为 turn-level；LongMemEval 为 conversation-level | 统一基于 `method_predictions.jsonl` 和 question status |
| MemoryOS | conversation-level；恢复已有 JSON state 目录 | 统一基于 `method_predictions.jsonl` 和 question status |
| A-Mem | conversation-level；恢复 `memories.pkl`、retriever cache/embeddings 和 manifest | 统一基于 `method_predictions.jsonl` 和 question status |
| LightMem | conversation-level；按同一状态目录重建 LightMemory backend | 统一基于 `method_predictions.jsonl` 和 question status |
