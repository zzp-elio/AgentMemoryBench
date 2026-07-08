# MemoryOS 机制深读卡片

完成时间：2026-07-05 20:52 CST

## 1. 写入后内部发生什么

事实：

- PyPI 版 `Memoryos.__init__()` 为一个 `user_id` 和 `assistant_id` 初始化短期记忆、中期记忆、用户长期记忆、助手长期记忆、Updater 和 Retriever；状态路径按 `users/<user_id>/` 与 `assistants/<assistant_id>/` 分开。证据：`third_party/methods/MemoryOS-main/memoryos-pypi/memoryos.py:32-124`。
- PyPI 原生写入入口 `add_memory(user_input, agent_response, timestamp=None, meta_data=None)` 先构造 QA pair；若 short-term memory 已满，则先调用 `updater.process_short_term_to_mid_term()`，再把新 QA pair 加入 short-term，最后检查中期热度是否触发 profile/knowledge update。证据：`third_party/methods/MemoryOS-main/memoryos-pypi/memoryos.py:226-250`。
- short-term memory 是持久化 JSON deque，`add_qa_pair()` 补 timestamp、append、save，`is_full()` 用 `len(memory) >= max_capacity` 判断。证据：`third_party/methods/MemoryOS-main/memoryos-pypi/short_term.py:9-67`。
- Updater 将满载 short-term 批量弹出为 pages，补 `page_id/pre_page/next_page/meta_info/analyzed` 等字段；每页先用 LLM 判断连续性并生成 meta-info，再对本批 user 输入调用多主题摘要 LLM，最后按主题把 pages 插入中期记忆。证据：`third_party/methods/MemoryOS-main/memoryos-pypi/updater.py:100-207`。
- 中期记忆为 session/page 分层：session 有 summary、summary embedding、keywords、page details、访问次数、交互长度、recency 和 heat；插入时用 summary embedding 相似度加关键词重叠决定合并或新建 session，超容量时 LFU 淘汰。证据：`third_party/methods/MemoryOS-main/memoryos-pypi/mid_term.py:20-36`、`third_party/methods/MemoryOS-main/memoryos-pypi/mid_term.py:103-179`、`third_party/methods/MemoryOS-main/memoryos-pypi/mid_term.py:190-279`。
- 热度触发长期更新时，PyPI 版取堆顶中期 session 的未分析 pages，并行执行用户画像分析和知识抽取；随后更新用户 profile、用户 private knowledge、助手 knowledge，并把 session pages 标为 analyzed、重置访问/交互热度、重建 heap。证据：`third_party/methods/MemoryOS-main/memoryos-pypi/memoryos.py:126-224`。

推断/含义：

- MemoryOS 写入不是简单 append：短期队列满载是中期结构化写入的触发点，中期检索命中会累积 heat，heat 达阈值又触发长期画像/知识更新。因此“写入已可检索”的判据依赖 short-term capacity、迁移时机和 heat 更新路径。

## 2. 原生 ingest 形态

事实：

- PyPI 原生输入单位是一个 QA pair：`add_memory(user_input: str, agent_response: str, timestamp: str = None, meta_data: dict = None)`；timestamp 可选，`meta_data` 当前保留但未写入 QA pair。证据：`third_party/methods/MemoryOS-main/memoryos-pypi/memoryos.py:226-239`。
- 官方 LoCoMo eval 先把 `speaker_a` 的发言放入 `user_input`，把后续 `speaker_b` 发言填入上一条 `agent_response`，并保留 session timestamp；它使用 `ShortTermMemory(max_capacity=1)`，逐 dialog `add_qa_pair()` 后立刻在满载时 `bulk_evict_and_update_mid_term()`。证据：`third_party/methods/MemoryOS-main/eval/main_loco_parse.py:159-200`、`third_party/methods/MemoryOS-main/eval/main_loco_parse.py:247-259`。
- 官方 eval 的动态更新与 PyPI 版同构：满载 short-term 被弹出为 page，调用连续性判断、meta-info 生成、多主题摘要，再按主题插入中期记忆。证据：`third_party/methods/MemoryOS-main/eval/dynamic_update.py:121-180`。
- MemoryData 的 MemoryOS 集成不是官方 eval 脚本；它包装自带 runtime，外部只调用 `MemoryOSAdapter.add_chunk(content, timestamp)`，runtime 把自由文本 chunk 写成 `ShortTermMessage(user_input=content, agent_response="")`，short-term 满载后迁移并尝试 profile update。证据：`第三方框架参考/MemoryData/methods/memoryos/memoryos_adapter.py:18-83`、`第三方框架参考/MemoryData/methods/memoryos/source/memoryos/runtime.py:635-649`。

推断/含义：

- MemoryOS 最自然的官方输入粒度是 QA pair/page；LoCoMo eval 偏好极小 short-term capacity，让每个 page 立即进入中期。MemoryData 的 chunk 形态可跑通工程 benchmark，但它把 `agent_response` 置空，不等价于官方 QA pair 语义。

## 3. 检索机制

事实：

- PyPI Retriever 的 `retrieve_context()` 并行检索中期 pages、用户长期知识和助手长期知识，返回 `retrieved_pages`、`retrieved_user_knowledge`、`retrieved_assistant_knowledge` 与时间戳。证据：`third_party/methods/MemoryOS-main/memoryos-pypi/retriever.py:34-130`。
- PyPI 中期检索对 query 生成 embedding，用 FAISS 在 session summary embedding 上取候选，再结合关键词重叠与 page embedding 阈值筛 pages；命中后会增加 session `N_visit/access_count`、更新 recency 和 heat，并保存状态。证据：`third_party/methods/MemoryOS-main/memoryos-pypi/mid_term.py:281-362`。
- PyPI 长期知识检索对 knowledge embedding 建 FAISS `IndexFlatIP`，按阈值和 top_k 返回用户或助手知识；用户 profile 另通过 profile getter 读取。证据：`third_party/methods/MemoryOS-main/memoryos-pypi/long_term.py:83-140`。
- 官方 eval 的 `RetrievalAndAnswer.retrieve(user_query, segment_threshold, page_threshold, knowledge_threshold, client)` 只返回 top page 队列、长期知识和 `retrieved_at`；page 队列由中期 matched pages 分数排序截断，长期知识来自 `long_term_memory.search_knowledge()`。证据：`third_party/methods/MemoryOS-main/eval/retrieval_and_answer.py:4-46`。
- 官方 LoCoMo reader 会把 recent short-term、retrieval_queue、用户 profile/private knowledge、助手 knowledge 拼进 prompt，再调用 answer LLM；retrieval 本身主要消耗 embedding 和关键词抽取，answer LLM 在 reader 阶段发生。证据：`third_party/methods/MemoryOS-main/eval/main_loco_parse.py:83-157`。

推断/含义：

- retrieve-first 协议应把 MemoryOS 的 page queue、long-term knowledge、profile/assistant knowledge 都作为 memory context，而不是只传 page 文本。中期检索本身会改变 heat，故检索不是只读操作。

## 4. 状态与边界行为

事实：

- PyPI 版状态落到多个 JSON：用户目录下有 `short_term.json`、`mid_term.json`、`long_term_user.json`，助手目录下有 `long_term_assistant.json`。证据：`third_party/methods/MemoryOS-main/memoryos-pypi/memoryos.py:70-84`。
- 官方 eval 使用每个 sample 独立的 short/mid/long JSON 文件；main 脚本把它们放在 `mem_tmp_loco_final/<sample_id>_*`。证据：`third_party/methods/MemoryOS-main/eval/main_loco_parse.py:247-252`。
- eval 中期状态保存 `sessions` 和 `access_frequency`；session 内 pages 记录 embedding、keywords、pre/next 链、meta_info、analyzed、heat 相关字段。证据：`third_party/methods/MemoryOS-main/eval/mid_term_memory.py:78-183`、`third_party/methods/MemoryOS-main/eval/mid_term_memory.py:250-271`。
- eval 长期状态保存 `user_profiles`、`knowledge_base` 和 `assistant_knowledge`；知识条目带 embedding，profile 按 user/sample id 覆盖或合并。证据：`third_party/methods/MemoryOS-main/eval/long_term_memory.py:5-35`、`third_party/methods/MemoryOS-main/eval/long_term_memory.py:68-120`。
- PyPI 的长期 profile/knowledge 更新内部用 `ThreadPoolExecutor` 并行两类 LLM 任务，但函数会等待 `future.result()`；没有后台 daemon 或异步完成回调。证据：`third_party/methods/MemoryOS-main/memoryos-pypi/memoryos.py:153-180`。
- MemoryData runtime 把全部状态保存到单个 JSON，包含 short-term、sessions、access_frequency、profiles、knowledge、assistant_knowledge、last evicted page id 和各类自增 id。证据：`第三方框架参考/MemoryData/methods/memoryos/source/memoryos/runtime.py:793-842`。

推断/含义：

- clean retry 的自然单位是一个 conversation/sample 的状态目录或状态文件。完成判据不是“已 append 到 short-term”，而是 short-term 迁移、必要的中期保存、热度触发长期保存都同步返回。

## 5. 对协议设计的含义

事实：

- 官方 LoCoMo eval 把 conversation 拆成 QA pages，并用 `ShortTermMemory(max_capacity=1)` 让每个有效 page 写入后立即进入中期记忆。证据：`third_party/methods/MemoryOS-main/eval/main_loco_parse.py:159-200`、`third_party/methods/MemoryOS-main/eval/main_loco_parse.py:247-259`。
- PyPI 默认 short-term capacity 是 10；若不足以触发满载，近期 QA 会留在 short-term，`get_response()` 仍会把 short-term history 拼进回答 prompt。证据：`third_party/methods/MemoryOS-main/memoryos-pypi/memoryos.py:35-43`、`third_party/methods/MemoryOS-main/memoryos-pypi/memoryos.py:252-270`。
- 中期 session 需要 timestamp、page 链、meta-info、summary/keywords/embedding 和 analyzed 标志；长期更新依赖 heat 阈值和未分析 pages。证据：`third_party/methods/MemoryOS-main/eval/dynamic_update.py:132-180`、`third_party/methods/MemoryOS-main/eval/main_loco_parse.py:28-82`。

推断/含义：

- 协议如果只提供整段 `add(conversation)`，adapter 必须自行决定 speaker_a/speaker_b、QA pairing、timestamp 继承和 short-term flush 策略；如果提供 `add_page(user_input, agent_response, timestamp, is_final)` 或显式 finalize，会更贴近 MemoryOS 的 page/queue 机制。
- MemoryOS 需要边界信号来区分“仍停在 short-term 的近期上下文”和“已迁入 mid-term 的可召回历史页”；这会影响不同 benchmark 的成本和可检索性。

## 6. 未确认项

- PyPI `add_memory()` 是“写新 QA 前先迁移已满 STM”，官方 eval 和本仓库 adapter 是“写入后检测满载并迁移”；两者在 capacity > 1 时对最后剩余 short-term pages 的行为不同，需要架构师裁定 Phase 1 profile 应以哪条路径为准。证据：`third_party/methods/MemoryOS-main/memoryos-pypi/memoryos.py:240-250`、`third_party/methods/MemoryOS-main/eval/main_loco_parse.py:254-259`。
- 官方 eval 的 `MidTermMemory` 在 import 阶段创建硬编码空 key/base_url client，本仓库 adapter 用 monkeypatch 安全导入并重注入 client；这是运行环境修正，是否记为 official-eval-wrapper profile 的一部分需要在 protocol manifest 中固定。证据：`third_party/methods/MemoryOS-main/eval/mid_term_memory.py:11-14`、`src/memory_benchmark/methods/memoryos_adapter.py:980-1047`。
- MemoryData runtime 支持无 LLM fallback summary/keywords，但官方 MemoryOS pipeline 的连续性、meta-info、summary、profile extraction 都是 LLM 驱动；是否可接受 fallback 作为 Phase 1 smoke 模式需另行裁定。证据：`第三方框架参考/MemoryData/methods/memoryos/source/memoryos/runtime.py:190-271`、`第三方框架参考/MemoryData/methods/memoryos/source/memoryos/runtime.py:382-430`。

## 7. 现有 adapter 的形变记录

事实：

- 本仓库 adapter 明确接入官方 `eval/` 目录而非 PyPI `Memoryos` 类；初始化时动态导入 `utils/short_term_memory/mid_term_memory/long_term_memory/dynamic_update/retrieval_and_answer/main_loco_parse`，并为每个 conversation 创建 eval 状态。证据：`src/memory_benchmark/methods/memoryos_adapter.py:1-6`、`src/memory_benchmark/methods/memoryos_adapter.py:497-510`、`src/memory_benchmark/methods/memoryos_adapter.py:971-1023`。
- 统一 `add(conversation)` 迫使 adapter 先调用 `_create_state()`，再把整段 Conversation 转为 MemoryOS pages，循环 `short_memory.add_qa_pair()`、满载后 `dynamic_updater.bulk_evict_and_update_mid_term()`，每页后检查热度更新；官方 PyPI 原生入口则是单次 `add_memory(user_input, agent_response, timestamp)`。证据：`src/memory_benchmark/methods/memoryos_adapter.py:579-618`、`third_party/methods/MemoryOS-main/memoryos-pypi/memoryos.py:226-250`。
- adapter 的 `conversation_to_memory_pages()` 需要从公开 metadata 或 turn 顺序解析 speaker_a/speaker_b，把 speaker_a turn 放入 `user_input`，把 speaker_b turn 补到上一页 `agent_response`，并把图片 caption 拼入文本；这复刻并扩展了官方 LoCoMo `process_conversation()`。证据：`src/memory_benchmark/methods/memoryos_adapter.py:797-840`、`src/memory_benchmark/methods/memoryos_adapter.py:1256-1285`、`third_party/methods/MemoryOS-main/eval/main_loco_parse.py:159-200`。
- adapter profile 默认 `short_term_capacity=7`，不是官方 LoCoMo eval 的 1，也不是 PyPI 默认 10；它另有 `estimate_add_workload()` 估算 page 数、预计迁移批次和剩余 short-term pages。证据：`src/memory_benchmark/methods/memoryos_adapter.py:92-141`、`src/memory_benchmark/methods/memoryos_adapter.py:887-919`、`third_party/methods/MemoryOS-main/eval/main_loco_parse.py:247-259`。
- adapter 的 `retrieve()` 只调用官方 eval retrieval，再构造 `AnswerPromptResult.prompt_messages`；旧 `get_answer()` 才调用官方 `generate_system_response_with_meta()` 直接生成 answer。证据：`src/memory_benchmark/methods/memoryos_adapter.py:620-683`、`src/memory_benchmark/methods/memoryos_adapter.py:685-795`。
- adapter 为 eval 脚本补 OpenAI-compatible base URL、timeout、retry、usage observation、本地 embedding cache，并把官方 heat 公式替换为论文 Eq.4 默认权重；这些是 runner/观测/论文 profile 形变，不是原生 API。证据：`src/memory_benchmark/methods/memoryos_adapter.py:1034-1065`、`src/memory_benchmark/methods/memoryos_adapter.py:1082-1225`。
- adapter 为每个 conversation 使用独立状态目录，并支持 `load_existing_conversation_state()` 校验 short/mid/long JSON 顶层结构后挂载；这是 resume/审计形变。证据：`src/memory_benchmark/methods/memoryos_adapter.py:377-447`、`src/memory_benchmark/methods/memoryos_adapter.py:857-874`、`src/memory_benchmark/methods/memoryos_adapter.py:921-969`。

推断/含义：

- MemoryOS adapter 的主要形变来自整段 conversation 输入和 retrieve-first 输出：它必须在 adapter 内完成 speaker 解析、QA page pairing、STM 迁移循环、状态目录隔离、client/embedding 注入以及 reader prompt 构造；这些都不是单条 `add_memory()` 原生接口直接提供的能力。

原生化后状态（2026-07-06，M-B T5）：

- registered 主路径已是 `consume_granularity="session"` 的 v3 provider；`MemoryOS.ingest(SessionBatch)` 按 session 恢复公开 conversation 片段，复用 `conversation_to_memory_pages()` 生成 QA pages，不再从整段 `Conversation` 自行拆所有 session。
- 原生路径继续逐 page 调 `short_memory.add_qa_pair()`，满载时触发 `bulk_evict_and_update_mid_term()` 并检查热度更新；等价测试比较桥接与原生路径的 short-term pages 序列，覆盖连续同 speaker 与图片 caption 语料。
- `end_conversation()` 对 MemoryOS 保持 no-op；旧 `add()` 本轮按计划保留，理由是旧接口、resume 挂载和桥接等价对照仍依赖它。

HaluMem extraction 裁定（2026-07-08，ws02.2 T5）：

- MemoryOS 本轮不提供 session 增量 extraction 报告，保持不覆写 `end_session()`，HaluMem extraction 记 N/A。原因是原生写入单元是 QA page/short-term queue，满载后迁移到 mid-term，且长期更新依赖 heat 与未分析 pages；session 内新增 page 不等价于最终可检索 memory。证据：`third_party/methods/MemoryOS-main/eval/main_loco_parse.py:159-200`、`third_party/methods/MemoryOS-main/eval/main_loco_parse.py:247-259`、`third_party/methods/MemoryOS-main/eval/dynamic_update.py:132-180`。
