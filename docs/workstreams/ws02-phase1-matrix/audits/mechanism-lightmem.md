# LightMem 机制深读卡片

完成时间：2026-07-05 21:03 CST

## 1. 写入后内部发生什么

事实：

- `LightMemory.__init__()` 按配置构造可选 pre-compressor、topic segmenter、memory manager、短期 buffer、text embedder、context/embedding retriever、summary retriever 和可选 graph memory。证据：`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:107-192`。
- 原生写入入口是 `add_memory(messages, METADATA_GENERATE_PROMPT=None, *, force_segment=False, force_extract=False, boundmem_tags=None)`；注释声明 pipeline 包含 message normalize、可选压缩、topic segmentation、阈值/force 触发 extraction、可选 metadata/text summary、构造成 `MemoryEntry` 并按 online/offline update 写入。证据：`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:204-257`。
- `add_memory()` 先标准化消息，再按配置预压缩；若 `topic_segment=False`，当前源码直接返回 emitted messages，不进入 extraction 和持久化。证据：`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:258-310`。
- `topic_segment=True` 时，sensory buffer 先累计 messages；`force_segment=True` 可强制切分。切分后的 segments 进入 short-term buffer，只有 token 阈值溢出或 `force_extract=True` 时才触发 extraction。证据：`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:311-327`、`third_party/methods/LightMem/src/lightmem/factory/memory_buffer/sensory_memory.py:15-43`、`third_party/methods/LightMem/src/lightmem/factory/memory_buffer/short_term_memory.py:36-57`。
- 触发 extraction 后，LightMem 分配 topic id、调用 memory manager 做 metadata/text extraction，转换为 `MemoryEntry`，再根据 `config.update` 进入 `online_update()` 或 `offline_update()`；当前 `online_update()` 是空实现。证据：`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:329-392`、`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:394-397`。
- `offline_update(memory_list)` 对每个 `MemoryEntry` 生成 embedding、写入 Qdrant payload；如果调用时传 `construct_update_queue_trigger` 或 `offline_update_trigger`，可继续触发全库 update queue 与 offline update。证据：`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:397-456`。

推断/含义：

- LightMem 的一次 `add_memory()` 返回不一定表示 memory 已经可检索：只有触发 extraction 并完成 `offline_update()` 后才有 Qdrant 条目。没有 `force_extract` 的中间 turn 可能仍停在 buffer。

## 2. 原生 ingest 形态

事实：

- 原生 `messages` 可为 dict 或 list[dict]，每条 message 需要 role/content，并依赖 `time_stamp` 生成 `MemoryEntry` 的时间字段。官方 LoCoMo/LongMemEval 脚本在写入前都给每条 message 补 `time_stamp`。证据：`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:204-240`、`third_party/methods/LightMem/experiments/locomo/add_locomo.py:320-337`、`third_party/methods/LightMem/experiments/longmemeval/run_lightmem_gpt.py:157-174`。
- 官方 LoCoMo 写入先把每条原始发言转成 `user(content)+assistant("")` 两条 message，保留 `speaker_id/speaker_name`；按 turn pair 逐批调用 `add_memory(..., METADATA_GENERATE_PROMPT=..., force_segment=is_last_turn, force_extract=is_last_turn)`。证据：`third_party/methods/LightMem/experiments/locomo/add_locomo.py:104-154`、`third_party/methods/LightMem/experiments/locomo/add_locomo.py:320-337`。
- 官方 LongMemEval 写入按真实 user+assistant pair 调 `add_memory()`，同样只在最后一批设置 `force_segment=True, force_extract=True`。证据：`third_party/methods/LightMem/experiments/longmemeval/run_lightmem_gpt.py:148-178`。
- 官方 LoCoMo 构建完成后先备份 pre-update Qdrant，再执行 `construct_update_queue_all_entries()` 与 `offline_update_all_entries(score_threshold=0.9)`；独立 LongMemEval offline-update 脚本对每个 collection 执行同样两步，但阈值是 0.8。证据：`third_party/methods/LightMem/experiments/locomo/add_locomo.py:348-370`、`third_party/methods/LightMem/experiments/locomo/add_locomo.py:437-458`、`third_party/methods/LightMem/experiments/longmemeval/offline_update.py:31-42`。
- MemoryData 的 LightMem 集成不是完整官方 LoCoMo pipeline；默认 `ingest_mode=direct`，`add_chunk()` 解析 benchmark chunk 后构造单个 `MemoryEntry` 并直接调用 `self.lightmem.offline_update([entry])`，`finalize()` 为空。证据：`第三方框架参考/MemoryData/utils/agent.py:1680-1746`、`第三方框架参考/MemoryData/utils/agent.py:3203-3212`、`第三方框架参考/MemoryData/methods/lightmem/lightmem_adapter.py:144-193`、`第三方框架参考/MemoryData/methods/lightmem/lightmem_adapter.py:263-264`。

推断/含义：

- LightMem 原生最舒服的写入粒度是 benchmark-native turn/pair，并且需要显式“最后一批”信号来 flush segmentation/extraction；LoCoMo 还需要 post-build offline update 作为第二阶段边界。

## 3. 检索机制

事实：

- 原生 `retrieve(query, limit=10, filters=None, *, boundmem_tags=None, boundmem_drop_untagged=False)` 先生成 query embedding，再调用 embedding retriever 的 Qdrant search，最后把每条 payload 格式化成 `time_stamp weekday memory` 字符串列表。证据：`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:644-707`。
- Qdrant retriever 的 `search()` 支持 filters、limit、exclude_ids 和 `return_full`；`return_full=True` 时返回 `id/score/payload`，否则只返回 `id/score`。证据：`third_party/methods/LightMem/src/lightmem/factory/retriever/embeddingretriever/qdrant.py:126-191`。
- Qdrant retriever 也提供 `get_all(with_vectors=True, with_payload=True)`，官方 LoCoMo search 脚本先加载全量 entries，再按 `combined` 或 `per-speaker` 模式用向量相似度检索。证据：`third_party/methods/LightMem/src/lightmem/factory/retriever/embeddingretriever/qdrant.py:367-392`、`third_party/methods/LightMem/experiments/locomo/search_locomo.py:72-188`、`third_party/methods/LightMem/experiments/locomo/search_locomo.py:383-399`。
- 官方 LoCoMo reader 把检索 memory 按 speaker 分组后填入 `ANSWER_PROMPT` 或带 summary 的 `ANSWER_PROMPT_StructMem`，再用单条 system message 调 answer LLM。证据：`third_party/methods/LightMem/experiments/locomo/search_locomo.py:207-282`、`third_party/methods/LightMem/experiments/locomo/search_locomo.py:441-463`。
- 官方 LongMemEval reader 直接调用 `lightmem.retrieve(question, limit=20)`，再构造 system+user messages，user content 中带 `Question time:{question_date}` 和检索 memories。证据：`third_party/methods/LightMem/experiments/longmemeval/run_lightmem_gpt.py:181-188`。

推断/含义：

- LightMem 检索阶段消耗 embedding，不在 `retrieve()` 中调用 answer LLM；LoCoMo 官方 answer LLM 在 search 脚本中，LongMemEval answer LLM 在 run 脚本中。retrieve-first 协议应保留检索上下文和官方 reader prompt，但不让 method 直接产出最终 answer。

## 4. 状态与边界行为

事实：

- 状态主要在 Qdrant collection；官方配置中 collection/path 由 sample/question id 派生，`on_disk=True` 时落本地目录。证据：`third_party/methods/LightMem/experiments/locomo/add_locomo.py:193-221`、`third_party/methods/LightMem/src/lightmem/factory/retriever/embeddingretriever/qdrant.py:23-64`。
- sensory buffer 与 short-term buffer 是进程内状态；它们决定何时切 segment、何时抽取并清空 buffer。证据：`third_party/methods/LightMem/src/lightmem/factory/memory_buffer/sensory_memory.py:4-43`、`third_party/methods/LightMem/src/lightmem/factory/memory_buffer/short_term_memory.py:4-57`。
- offline update 的第一步 `construct_update_queue_all_entries()` 遍历全库 entries，用更早时间戳过滤候选，并把候选写回 payload 的 `update_queue`；第二步 `offline_update_all_entries()` 遍历全库，基于其他 entry 的 update_queue 和阈值调用 update LLM，然后更新或删除 Qdrant 条目。证据：`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:457-537`、`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:539-642`。
- MemoryData 用 marker file `lightmem_ready.txt` 表示 build 已完成；但它的 `finalize()` 为空，ready 只是外层流程标记，不是 LightMem 原生 flush。证据：`第三方框架参考/MemoryData/utils/agent.py:4399-4403`、`第三方框架参考/MemoryData/utils/agent.py:4491-4495`、`第三方框架参考/MemoryData/methods/lightmem/lightmem_adapter.py:263-264`。
- 本仓库 adapter 每个 conversation 独占 backend/Qdrant collection，并在 LoCoMo `add()` 后执行官方 post-build offline update；completed conversation resume 只重建 backend，不重跑 `add_memory()`。证据：`src/memory_benchmark/methods/lightmem_adapter.py:323-435`、`src/memory_benchmark/methods/lightmem_adapter.py:437-470`、`src/memory_benchmark/methods/lightmem_adapter.py:472-494`、`src/memory_benchmark/methods/lightmem_adapter.py:780-798`。

推断/含义：

- LightMem 的写入完成判据不能只看每个 turn 调用成功；应以最后一批 `force_extract` 完成，并且 LoCoMo 还要等 post-build offline update 完成。clean retry 应重建 conversation 独占 Qdrant/log 状态目录。

## 5. 对协议设计的含义

事实：

- 官方 LoCoMo/LongMemEval 都以 turn/pair 增量输入，最后一批才强制 flush；这需要协议表达“当前 batch 是 conversation 末尾”或提供 finalize。证据：`third_party/methods/LightMem/experiments/locomo/add_locomo.py:320-337`、`third_party/methods/LightMem/experiments/longmemeval/run_lightmem_gpt.py:157-178`。
- LoCoMo 的离线更新依赖全 conversation 已经写完后的全库相似候选，因此它天然需要 conversation-level build 完成信号。证据：`third_party/methods/LightMem/experiments/locomo/add_locomo.py:437-458`、`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:457-642`。
- LightMem 原生 payload 有 `time_stamp/weekday/topic_id/topic_summary/category/subcategory/memory_class/memory/original_memory/compressed_memory/speaker_id/speaker_name/consolidated`，Qdrant search 可返回 `id/score/payload`。证据：`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:418-440`、`third_party/methods/LightMem/src/lightmem/factory/retriever/embeddingretriever/qdrant.py:126-191`。

推断/含义：

- 如果协议只给 `add(conversation)`，adapter 必须自行模拟 turn/pair incremental feeding、最后一批 flush、LoCoMo post-build update 和 reader prompt 分支；如果协议提供 `add_batch(..., is_final=True)` 或 `finalize_conversation()`，LightMem 的状态边界会更自然。
- LightMem 的原生 provenance 足够丰富，应保留 Qdrant `id/score/payload`，而不是只传格式化字符串。

## 6. 未确认项

- LongMemEval 是否应在 Phase 1 默认执行独立 `offline_update.py` 的 OP-update；官方 run 脚本本身只 add/retrieve，独立脚本存在但需要架构师确认 profile。证据：`third_party/methods/LightMem/experiments/longmemeval/run_lightmem_gpt.py:148-188`、`third_party/methods/LightMem/experiments/longmemeval/offline_update.py:31-42`。
- `online_update()` 目前是空实现，若后续 profile 设置 `update="online"`，实际不会持久化更新；是否禁用该 profile 需要架构师裁定。证据：`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:382-397`。
- `topic_segment=False` 时 `add_memory()` 会提前返回 emitted messages，不进入 extraction；MemoryData 的 direct ingest 绕开这个问题，但不等价于官方 full pipeline。证据：`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:300-310`、`第三方框架参考/MemoryData/methods/lightmem/lightmem_adapter.py:144-193`。

## 7. 现有 adapter 的形变记录

事实：

- 本仓库 adapter 的统一入口是 `add(conversations)`；它按 conversation 创建/复用 backend，把统一 conversation 转成 LightMem batches，再只在最后一批传 `force_segment=True, force_extract=True`。官方原生入口则是多次 `LightMemory.add_memory(messages=turn_or_pair, ...)`。证据：`src/memory_benchmark/methods/lightmem_adapter.py:437-470`、`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:204-257`。
- adapter 根据公开 metadata 区分 LoCoMo 与 LongMemEval：LoCoMo 每个原始 turn 被包装为 `user(content)+assistant("")`，LongMemEval 则强校验并保留真实 user+assistant pair。证据：`src/memory_benchmark/methods/lightmem_adapter.py:874-956`、`third_party/methods/LightMem/experiments/locomo/add_locomo.py:104-154`、`third_party/methods/LightMem/experiments/longmemeval/run_lightmem_gpt.py:157-174`。
- adapter 必须把 LoCoMo 时间格式转换为 LightMem 可读的 `YYYY/MM/DD (Dow) HH:MM`，并为每条 message 填 `time_stamp`。证据：`src/memory_benchmark/methods/lightmem_adapter.py:1178-1215`、`third_party/methods/LightMem/experiments/locomo/add_locomo.py:95-101`。
- adapter 对 LoCoMo 在 `add()` 末尾手动调用 `construct_update_queue_all_entries()` 和 `offline_update_all_entries(score_threshold=0.9)`，因为该步骤不属于单次 `add_memory()` 的必然结果。证据：`src/memory_benchmark/methods/lightmem_adapter.py:466-468`、`src/memory_benchmark/methods/lightmem_adapter.py:780-798`、`third_party/methods/LightMem/experiments/locomo/add_locomo.py:437-458`。
- adapter 的 `retrieve()` 对 LongMemEval 走原生 `backend.retrieve()`；对 LoCoMo 则复刻官方 `search_locomo.py` 的 combined vector search：读取全量 Qdrant entries、自算 cosine similarity、排序截断。证据：`src/memory_benchmark/methods/lightmem_adapter.py:495-562`、`src/memory_benchmark/methods/lightmem_adapter.py:799-849`、`third_party/methods/LightMem/experiments/locomo/search_locomo.py:129-160`、`third_party/methods/LightMem/experiments/locomo/search_locomo.py:391-399`。
- adapter 的 reader prompt 也按 benchmark 分叉：LongMemEval 返回 system+user，LoCoMo 返回单条 system prompt，并从官方 prompt 文件读取 `ANSWER_PROMPT`。证据：`src/memory_benchmark/methods/lightmem_adapter.py:1002-1055`、`third_party/methods/LightMem/experiments/longmemeval/run_lightmem_gpt.py:181-188`、`third_party/methods/LightMem/experiments/locomo/search_locomo.py:441-463`。
- adapter 还注入本地模型路径、Qdrant conversation collection、LLMLingua 压缩率、STM 阈值强校验、API timeout/retry 和线程池 usage 回收。这些是统一 runner/观测/资源约束带来的形变。证据：`src/memory_benchmark/methods/lightmem_adapter.py:82-154`、`src/memory_benchmark/methods/lightmem_adapter.py:323-435`、`src/memory_benchmark/methods/lightmem_adapter.py:606-648`、`src/memory_benchmark/methods/lightmem_adapter.py:650-779`。

推断/含义：

- LightMem adapter 的主要复杂度来自协议缺少 incremental batch/finalize/offline-update 三个显式边界；整段 conversation 输入迫使 adapter 同时承担写入粒度转换、flush 触发、post-build update 和 benchmark-specific reader 选择。

原生化后状态（2026-07-06，M-B T3）：

- registry 按 benchmark profile 设置实例级 `consume_granularity`：LoCoMo 为 `turn`，LongMemEval 为 `pair`；原生路径由 runner 事件流提供增量 unit，不再从整段 `Conversation` 自行拆所有 batch。
- `LightMem.ingest(TurnEvent|TurnPair)` 采用一拍缓冲：收到下一 unit 时把上一批以 `force_segment=False/force_extract=False` 写入，`end_conversation()` 才把最后一批以 `True/True` 写入，并在 LoCoMo namespace 内执行 `construct_update_queue_all_entries()` 与 `offline_update_all_entries(score_threshold=0.9)`。
- 旧 `add()` 与 `_conversation_to_lightmem_batches()` 本轮按计划保留，理由是旧接口、resume 重建和桥接等价对照仍依赖它们；registered 原生 v3 主路径不再把整段 conversation 作为写入入口。

orphan 处置（2026-07-07，对照 smoke 回归修复）：

- 框架 pair 聚合改为 user 锚定后，assistant 开头 session 产出 orphan 单元；`_native_pair_batch` 对 orphan 经官方开头裁剪得到空批次时返回 None，`ingest` 直接跳过——与旧路径整段 session 裁剪行为等价（assistant-first 等价测试锁死）。已知遗留：LongMemEval s_cleaned 有 14 个 session 不满足"裁剪后偶数且严格 user/assistant 交替"口径，新旧路径同样 fail-fast，全量 run 前需定案（见 ws02 README 已知问题）。证据：`src/memory_benchmark/methods/lightmem_adapter.py`（`_native_pair_batch`）、`tests/test_lightmem_adapter.py::test_native_lightmem_longmemeval_assistant_first_skips_orphan_like_official_trim`。

HaluMem extraction 裁定（2026-07-08，ws02.2 T5）：

- LightMem 本轮不提供 session 增量 extraction 报告，保持不覆写 `end_session()`，HaluMem extraction 记 N/A。原因是原生 `add_memory()` 的中间批次不保证抽取或可检索，只有 `force_segment/force_extract` 与后续 offline update 边界完成后才形成稳定 memory；这不是单个 session 边界能干净表达的新增 memory 列表。证据：`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:204-257`、`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:300-310`、`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:457-642`。
