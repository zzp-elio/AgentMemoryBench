# LightMem 接入实例（B1-B11 逐项）

> 判据模板：`../method-integration-checklist.md` §B；勾选总表：`../integration-status.md`。
> 状态：**method-frozen-v1 定点重开（B2/B4/B5/B9/B10/B11）**。online-soft
> lifecycle 卡已强验收合入主线 `825132f`，B6/lifecycle identity 关闭；LoCoMo
> post-update 保留为另名补充轨。MemBench 时间语义 Phase A 与 LightMem preserve-none
> Phase B 的 timestamp 子门仍有效。
> 2026-07-16 补充：**hybrid role profile 已强验收合入**（主线 `d86b22a` +
> `d1c18c4`；双卡定向并集 588 项、主树全量 1435 项通过）——unified 主 build 已改为
> `messages_use="hybrid"`（adapter version 升至 `conversation-qa-v4`），通用
> role-slot normalizer 保留真实 role、只补结构占位；pair candidate ids 作为纯观测
> 链路穿过抽取管线到 Qdrant payload。官方 LongMemEval Table 2 的 `user_only` 仅作
> reproduction profile。源码 extraction `source_id` 是 pair index 且后续固定读 user
> slot，故 hybrid 的 assistant 可见性不自动等于 turn-level exact lineage；
> RetrievalEvidence 逐 benchmark 诚实矩阵已落地。详见
> `ws02.7/branches/method-recertification/lightmem/notes/lightmem-hybrid-role-profile-implementation.md`。
> 更新纪律：每过一项 B 判据 / 发现特殊情况，更新本文对应节。2026-07-13 建。

- adapter：`src/memory_benchmark/methods/lightmem_adapter.py`
- 算法源：vendored `third_party/methods/LightMem`（`src/lightmem/memory/lightmem.py`）
- native 格：**locomo、longmemeval**（官方 experiments 目录；其余格单轨 collapse）

## 0. 接口调用面（黑盒拆解）

| 框架钩子 | adapter 行为 | 落到 LightMem 官方接口 |
|---|---|---|
| `ingest(unit)` | 按 conversation 缓冲、攒批（`_convert_conversation_to_batches`，adapter:1107） | `LightMemory.add_memory(messages, force_segment=…, force_extract=…)`；**最后一批传 force=True 强制刷洗**（adapter:491-494） |
| `end_conversation` | 早退保护后写残余批（adapter:556 起；`_write_native_batch` force=is_final，adapter:579-580） | 同上 `add_memory(force_*=True)` |
| `retrieve(query)` | adapter:699；结果经 `_format_lightmem_memory`（adapter:1532，reader 版式）或 native 轨 `_format_lightmem_memory_as_official_retrieve`（adapter:1572，官方 retrieve 版式） | **不直接调 `LightMemory.retrieve()`**（其返回丢弃 payload，adapter:1497）；刻意复用其内部同款路径 `text_embedder.embed` + `embedding_retriever.search(return_full=True)` 保住 payload（adapter:1024-1056；§0.5.2 详解。M0-3 验收勘误：本行原写"落到 LightMemory.retrieve()"不准确） |
| `cleanup` / clean-retry | `clean_lightmem_conversation_state`（adapter:1660-1664 删 qdrant/logs 目录）；registry 挂 `_clean_lightmem_failed_ingest_state`（registry.py:796） | 文件系统级清理，不走官方 API |

**关键机理（一手，2026-07-15 论文+脚本+代码闭环）**：论文第 5 页把 online soft
定义为新 entry 直接插入 LTM；LongMemEval 表 2 正式报告 online-soft 与 OP-update 两行。
vendored `online_update()` 虽是 `return None` 空壳（lightmem.py:395-396），但论文的
online-soft 实际由 `update="offline" → offline_update(memory_entries)` 的 embed+insert
实现（lightmem.py:398-445）。真正的 offline consolidation 是另行调用
`construct_update_queue_all_entries()` + `offline_update_all_entries()`。

**现状（2026-07-15 online-soft 卡施工落地）**：五格 Phase 1 主 profile 已统一显式
`lifecycle_profile="online_soft"`（`LightMemConfig`，adapter version 升至
`conversation-qa-v4`，并显式声明 `messages_use="hybrid"`），LoCoMo 与其余四格同一 direct-insert 时点，conversation 边界
不再默认追加全库 consolidation。LoCoMo post-update 保留为显式 opt-in
`locomo_offline_consolidated` 补充轨，只在 `LightMem.__init__` 收到的
`benchmark_name == "locomo"` 时才允许启用，否则在触发全库 mutation 前于构造期
fail-fast（不从 conversation 的 source_path 或 question 字段猜身份）。两种 profile
构造出的 backend config 都仍传 `update="offline"`，禁止把它改为 `update="online"`。
`force_segment`（lightmem.py:313）强制切段、`force_extract` 经 `add_segments`
（lightmem.py:323）强制抽取，两者行为不受 `lifecycle_profile` 影响。真实 API 数字
尚待用户授权预算后另跑，本次施工只切代码路径，不产出新实验数字。

## 0.5 接口契约详解（官方 API）

以下签名、字段和返回分支均按 vendored 官方实现现场核对；adapter 的实际传参另以
`src/memory_benchmark/methods/lightmem_adapter.py` 双锚，不把 docstring 中的
“typically”当作结构事实（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:204-212,242-250`）。

### 0.5.1 `LightMemory.add_memory(...)`

完整签名为
`add_memory(self, messages, METADATA_GENERATE_PROMPT: Optional[Union[str, Dict[str, str]]] = None, *, force_segment: bool = False, force_extract: bool = False, boundmem_tags: Optional[Any] = None)`
（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:204-212`）。

| 参数 | 官方类型 / 默认值 | 含义 | 本项目 adapter 实际传值 |
|---|---|---|---|
| `messages` | 未写类型标注；实现接受 `dict` 或 `list[dict]`，每项须有时间信息 | 标准化会复制消息，并补 `session_time`、递增 ISO `time_stamp` 与 `weekday`；本项目最小 diff 同时读取可选 `external_id` 作观测血缘 | LoCoMo 每个原始 turn 传 `[user, assistant("")]`，LongMemEval 传真实 pair；键含 `role/content/speaker_id/speaker_name/time_stamp/external_id`（adapter:1289-1373）。`external_id` 不进入 memory 文本或 prompt。 |
| `METADATA_GENERATE_PROMPT` | `Optional[Union[str, Dict[str, str]]] = None`（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:207`） | `str` 会归一为 `{"factual": prompt}`；`dict` 原样使用；`None` 使用 extraction mode 默认 prompt（`third_party/methods/LightMem/src/lightmem/memory/utils.py:356-373`）。 | 仅 LoCoMo 注入官方 `METADATA_GENERATE_PROMPT_locomo`（`src/memory_benchmark/methods/lightmem_adapter.py:1209-1220`），并由调用点放进 kwargs（`src/memory_benchmark/methods/lightmem_adapter.py:496-501`）；其他 benchmark 不传，取默认 `None`（同一调用点）。 |
| `force_segment` | `bool = False`（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:209`） | `True` 时无视缓冲条件，调用 segmenter 强制切段（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:311-315`）。 | 每个 conversation 的最后一批为 `True`，此前批次为 `False`（`src/memory_benchmark/methods/lightmem_adapter.py:490-494`）；v3 native 缓冲写出同样以 `is_final` 传值（`src/memory_benchmark/methods/lightmem_adapter.py:568-580`）。 |
| `force_extract` | `bool = False`（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:210`） | 传给 short-memory buffer 的 `add_segments(..., force_extract)`，可强制触发抽取（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:323-327`）。 | 与 `force_segment` 相同，仅最后一批 / `is_final` 为 `True`（`src/memory_benchmark/methods/lightmem_adapter.py:490-494,568-580`）。 |
| `boundmem_tags` | `Optional[Any] = None`（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:211`） | 非空时先解析为 hard tags，再写入每条 `MemoryEntry.bam_tags`，同时给 `memory` 文本加 tag（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:373-378`）。 | adapter 调用 kwargs 中没有该键，故使用 `None`（`src/memory_benchmark/methods/lightmem_adapter.py:490-502,577-587`）。 |

`add_memory()` 有两种可完整枚举的字典结构；这些是配置/流水线阶段分支，不是返回
自定义类（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:267-271,300-318,392`）：

| 返回分支 | 精确结构 | 键的含义 |
|---|---|---|
| topic segmentation 开启的常规路径，以及“尚无 segment”或“尚未触发 extraction”的早退 | `{"add_input_prompt": list, "add_output_prompt": list, "api_call_nums": int}`（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:267-271,316-318,325-327,392`） | 每个 extraction 结果的 `input_prompt` 依次追加到 `add_input_prompt`，`output_prompt` 依次追加到 `add_output_prompt`，每处理一个非空结果就把 `api_call_nums` 加一（`third_party/methods/LightMem/src/lightmem/memory/utils.py:383-403`）。**没有逐次 token 键**：token usage 只累加到实例的 `self.token_stats`（`third_party/methods/LightMem/src/lightmem/memory/utils.py:386-391`）。 |
| `config.topic_segment == False` 的早退 | `{"triggered": True, "cut_index": len(msgs), "boundaries": [0, len(msgs)], "emitted_messages": msgs, "carryover_size": 0}`（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:300-309`） | 返回整批标准化消息及固定边界；该分支在抽取和 `MemoryEntry` 构造之前直接返回（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:300-311`）。 |

**memory-point 关键答案：没有。** 抽取结果会在函数内部转成
`list[MemoryEntry]`（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:363-371`），
随后写入 online/offline update（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:382-385`），
但最终只返回上述 `result` 字典（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:387-392`）；
该字典没有 memory entries、entry ids 或 entry count 键（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:267-271`）。

效率信息另有实例级 `get_token_statistics()`：返回顶层 `summary/llm/embedding`；
`summary` 含 `total_llm_calls/total_llm_tokens/total_embedding_calls/total_embedding_tokens`，
`llm` 下按 `add_memory/update/summarize` 各含 `calls/prompt_tokens/completion_tokens/total_tokens`，
`embedding` 含 `total_calls/total_tokens/note`（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:709-748`）。
这不是 `add_memory()` 返回值，当前 adapter 也不调用它；adapter 实际通过包装 manager
的 `generate_response()` 读取 `(parsed_response, usage_info)` 记录效率（`src/memory_benchmark/methods/lightmem_adapter.py:870-907,910-949`）。

### 0.5.2 `LightMemory.retrieve(...)`

完整签名为
`retrieve(self, query: str, limit: int = 10, filters: Optional[dict] = None, *, boundmem_tags: Optional[Any] = None, boundmem_drop_untagged: bool = False) -> list[str]`
（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:644-652`）。

| 参数 | 官方类型 / 默认值 | 含义 | 本项目 adapter 实际传值 |
|---|---|---|---|
| `query` | `str`，无默认（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:644-647`） | 自然语言检索 query；先由 `text_embedder.embed(query)` 向量化（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:671-675`）。 | adapter **没有直接调用 `LightMemory.retrieve()`**；它把公开 `question.text` 传给同一个官方 `text_embedder.embed()`（`src/memory_benchmark/methods/lightmem_adapter.py:1019-1052`）。 |
| `limit` | `int = 10`（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:647`） | 向量搜索最多返回的条数（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:675-680`）。 | adapter 向底层官方 `embedding_retriever.search()` 传 `self.config.retrieve_limit`（`src/memory_benchmark/methods/lightmem_adapter.py:1052-1056`）。 |
| `filters` | `Optional[dict] = None`（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:648`） | 透传到向量库搜索的 payload filter（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:675-680`）。 | adapter 底层调用固定传 `None`（`src/memory_benchmark/methods/lightmem_adapter.py:1052-1056`）。 |
| `boundmem_tags` | `Optional[Any] = None`（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:649-650`） | 非空时对搜索结果执行 BAM tag 过滤，并在输出前移除文本 tag（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:682-700`）。 | adapter 的底层调用没有 tag-filter 步骤或对应参数（`src/memory_benchmark/methods/lightmem_adapter.py:1051-1077`）。 |
| `boundmem_drop_untagged` | `bool = False`（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:651`） | 有 `boundmem_tags` 时，控制是否丢弃未带 BAM tag 的条目（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:682-688`）。 | adapter 不调用该入口，故未传（`src/memory_benchmark/methods/lightmem_adapter.py:1019-1078`）。 |

官方公开返回恒为 `list[str]`；每项精确由
`f"{payload.time_stamp} {payload.weekday} {payload.memory}"` 生成，列表顺序沿用向量搜索结果
（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:693-707`）。因此
**官方 `LightMemory.retrieve()` 返回中没有 entry id、score、payload、原始 turn id 或其他可定位来源字段**
（同一格式化循环）。

当前 adapter 为保留 speaker/payload，实际复用官方内部组件而非这个格式化出口：
`embedding_retriever.search(..., return_full=True)` 的原始元素为
`{"id": h.id, "score": h.score, "payload": h.payload}`
（`third_party/methods/LightMem/src/lightmem/factory/retriever/embeddingretriever/qdrant.py:126-147,169-191`），
adapter 再形成 `{"id": str, "score": float, "payload": dict, "source": "vector", "_retrieved_speaker": str}`
（`src/memory_benchmark/methods/lightmem_adapter.py:1181-1201`）。这里的 `id` 是
`MemoryEntry.id` 写入 Qdrant 的存储 UUID，不是抽取输入的 `source_id`。2026-07-13
M0-7b 已加最小观测 diff：adapter message 携带公开 `external_id`，构造时写入
`MemoryEntry.source_external_id`（`memory/utils.py:33,321-361`），insert 再条件写入
payload（`lightmem.py:437-439`）。所以初始 entry 已可定位到单一公开 turn；但
2026-07-15 审计确认 LoCoMo all-entry update 会合并文本而不合并该 singular id，
当前仍不满足 post-update 完整血缘，见 §B5。

### 0.5.3 `LightMemory.offline_update(...)`

完整签名为
`offline_update(self, memory_list: List, construct_update_queue_trigger: bool = False, offline_update_trigger: bool = False)`；
函数没有显式 `return`，因此 Python 返回 `None`（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:397-455`）。

| 参数 | 官方类型 / 默认值 | 含义 | 本项目 adapter 实际传值 |
|---|---|---|---|
| `memory_list` | `List`，无元素类型标注（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:397`）；实际循环按 `MemoryEntry` 属性读取（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:410-433`） | 要持久化的 memory entries；context/hybrid 写 JSON，embedding/hybrid 做 embedding 后插入向量库（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:403-440`）。 | adapter 不直接调用；`add_memory()` 在 `config.update == "offline"` 时把刚构造的 `memory_entries` 作为唯一位置参数传入（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:363-385`），而 adapter backend config 固定 `update="offline"`（`src/memory_benchmark/methods/lightmem_adapter.py:450-462`）。 |
| `construct_update_queue_trigger` | `bool = False`（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:397`） | 插入完成后是否调用 `construct_update_queue_all_entries(top_k=20, keep_top_n=10)`（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:443-449`）。 | `add_memory()` 只传 `memory_entries`，故为 `False`（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:382-385`）。LoCoMo 的 post-build queue 是 adapter 另行调用 `construct_update_queue_all_entries()`，不是通过此参数开启（`src/memory_benchmark/methods/lightmem_adapter.py:1000-1016`）。 |
| `offline_update_trigger` | `bool = False`（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:397`） | 插入完成后是否调用全库 offline update（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:451-455`）。 | `add_memory()` 未传，故为 `False`（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:382-385`）；LoCoMo adapter 在 conversation 写完后另行调用 `offline_update_all_entries(score_threshold=配置值)`（`src/memory_benchmark/methods/lightmem_adapter.py:1000-1017`）。 |

关系链是：`force_segment` 决定是否强制切出 segment，`force_extract` 决定是否强制让
short-memory buffer 产出抽取批次（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:311-327`）；
只有抽取结果被转换成 `MemoryEntry` 后，`add_memory()` 才把该列表交给 `offline_update()` 持久化
（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:340-385`）。两个 force 参数不属于
`offline_update()` 签名，也不会继续透传（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:397`）。

### 0.5.4 自定义数据类逐字段

`MemoryEntry` 是 add 路径唯一内部持久化数据载体 dataclass；字段定义集中在
`third_party/methods/LightMem/src/lightmem/memory/utils.py:13-32`。`add_memory()` 和
`retrieve()` 的公开返回均为内建 `dict`/`list[str]`，没有自定义返回类或 TypedDict
（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:267-271,392,644-652,693-707`）。

| 字段 | 类型 / 默认 | 含义 | 谁写入 | 谁消费 |
|---|---|---|---|---|
| `id` | `str` / UUID4 factory（`utils.py:15`） | 存储条目 id。 | dataclass 默认生成；碰撞时 `offline_update` 改成新 UUID（`lightmem.py:414-417`）。 | 作为 Qdrant point id 插入（`lightmem.py:436-440`），底层检索可返回它（`qdrant.py:180-185`）。 |
| `time_stamp` | `str` / 当前 ISO 时间（`utils.py:16`） | 抽取事实锚定消息的 ISO 时间。 | 构造器按 `source_id * 2` 从标准化消息时间表读取（`utils.py:313-343`）。 | 写入 payload（`lightmem.py:418-420`）并进入官方 retrieve 字符串（`lightmem.py:693-701`）。 |
| `float_time_stamp` | `float` / `0`（`utils.py:17`） | 同一时间的 Unix timestamp 数值。 | 构造器从 `time_stamp` 转换（`utils.py:316-344`）。 | 写入 payload（`lightmem.py:418-421`），update queue 按它过滤历史候选（`lightmem.py:483-500`）。 |
| `weekday` | `str` / `""`（`utils.py:18`） | timestamp 对应星期文本。 | 构造器从标准化消息星期表读取（`utils.py:325-344`）。 | 写入 payload（`lightmem.py:418-422`）并进入官方 retrieve 字符串（`lightmem.py:693-701`）。 |
| `category` | `str` / `""`（`utils.py:19`） | 预留类别字段；当前 `_create_memory_entry_from_fact` 构造路径不赋非默认值。 | dataclass 默认；`_create_memory_entry_from_fact` 未传该字段（`utils.py:341-351`）。 | 原样写入 JSON / Qdrant payload（`utils.py:137-160`；`lightmem.py:418-425`）。 |
| `subcategory` | `str` / `""`（`utils.py:20`） | 预留子类别字段；当前构造路径不赋非默认值。 | dataclass 默认（`utils.py:341-351`）。 | 原样写入 JSON / Qdrant payload（`utils.py:137-160`；`lightmem.py:418-425`）。 |
| `memory_class` | `str` / `""`（`utils.py:21`） | 预留 memory class 字段；当前构造路径不赋非默认值。 | dataclass 默认（`utils.py:341-351`）。 | 原样写入 JSON / Qdrant payload（`utils.py:137-160`；`lightmem.py:418-427`）。 |
| `memory` | `str` / `""`（`utils.py:22`） | 抽取出的事实文本；`fact` 缺失时退到 `relation`。 | `_create_memory_entry_from_fact` 写 `fact or relation`（`utils.py:341-346`）；BoundMem 可再加 tag（`lightmem.py:373-378`）。 | 用作 embedding 文本并写入 payload（`lightmem.py:410-429`），官方 retrieve 输出该字段（`lightmem.py:693-701`）。 |
| `original_memory` | `str` / `""`（`utils.py:23`） | 原始记忆文本槽；当前构造路径不赋非默认值。 | dataclass 默认（`utils.py:341-351`）。 | 写入 JSON / Qdrant payload（`utils.py:137-160`；`lightmem.py:418-429`）；adapter 的 reader formatter 在 `memory` 为空时把它作为 fallback（`src/memory_benchmark/methods/lightmem_adapter.py:1532-1546`）。 |
| `compressed_memory` | `str` / `""`（`utils.py:24`） | 压缩记忆文本槽；当前构造路径不赋非默认值。 | dataclass 默认（`utils.py:341-351`）。 | 写入 JSON / Qdrant payload（`utils.py:137-160`；`lightmem.py:418-429`）；adapter 在前两种文本为空时把它作为 fallback（`src/memory_benchmark/methods/lightmem_adapter.py:1532-1546`）。 |
| `topic_id` | `Optional[int]` / `None`（`utils.py:25`） | segment 对应的全局 topic id。 | `source_id * 2` 映射到 topic id 后传给构造器（`utils.py:247-281,341-349`）。 | 写入 JSON / Qdrant payload（`utils.py:137-160`；`lightmem.py:418-423`）。 |
| `topic_summary` | `str` / `""`（`utils.py:26`） | 预留 topic summary；官方 docstring 明示 reserved for future use。 | 当前转换调用固定传空串（`utils.py:273-280,301-308`）。 | 写入 JSON / Qdrant payload（`utils.py:137-160`；`lightmem.py:418-424`）。 |
| `speaker_id` | `str` / `""`（`utils.py:27`） | source 消息的 speaker id。 | 构造器从 `speaker_list[source_id * 2]` 读取（`utils.py:313-347`）。 | 写入 Qdrant payload（`lightmem.py:418-431`）。 |
| `speaker_name` | `str` / `""`（`utils.py:28`） | source 消息的 speaker 显示名。 | 构造器从 `speaker_list[source_id * 2]` 读取（`utils.py:313-347`）。 | 写入 Qdrant payload（`lightmem.py:418-432`）；adapter 用 payload 值做 LoCoMo speaker 分组（`src/memory_benchmark/methods/lightmem_adapter.py:1516-1529`）。 |
| `hit_time` | `int` / `0`（`utils.py:29`） | 命中计数槽；当前 add/retrieve embedding 路径无写增量或读取点。 | dataclass 默认（`utils.py:13-32`）。 | 仅 context JSON serializer 写出（`utils.py:137-160`）；初始 embedding payload 列表不含它（`lightmem.py:418-435`）。 |
| `update_queue` | `List` / 新空 list（`utils.py:30`） | offline update 候选 `{id, score}` 列表。 | `MemoryEntry` 初始为空；全库 queue 构造在 Qdrant payload 上另写候选列表（`lightmem.py:502-525`）。 | `offline_update_all_entries` 遍历其他 payload 的 queue 来寻找待更新 entry（`lightmem.py:570-592`）；context JSON serializer 也写出 dataclass 初值（`utils.py:137-160`）。 |
| `consolidated` | `bool` / `False`（`utils.py:31`） | 是否已进入 summary consolidation。 | 构造器显式写 `False`（`utils.py:341-351`）；summary 流程处理后在 payload 写 `True`（`utils.py:640-654`）。 | 写入 Qdrant payload（`lightmem.py:418-433`），summary 时间窗以 `False` 过滤（`utils.py:584-610`）。 |
| `bam_tags` | `List[Any]` / 新空 list（`utils.py:32`） | BoundMem 标签集合。 | `boundmem_tags` 非空时写入并给文本加 tag（`lightmem.py:373-378`）。 | embedding 前决定是否 strip tag，非空时写入 payload（`lightmem.py:410-435`）；retrieve 的 tag filter 消费 payload tags（`lightmem.py:682-700`）。 |
| `source_external_id` | `Optional[str] = None`（本项目 M0-7b 最小 diff，`utils.py:33`） | 初始 extracted fact 对应的公开 turn anchor。 | `_create_memory_entry_from_fact` 用消息 `external_id` 写入（`utils.py:321-361`）。 | insert 条件写入 payload（`lightmem.py:437-439`）；当前 adapter 读取 singular。它不是 merge 后 semantic provenance；不以 plural 输入 union 修补。 |

add 路径另有内部状态类 `MessageNormalizer`，不是返回数据类：实例字段仅
`last_timestamp_map: Dict[str, datetime]`（按原始 session timestamp 记上次时间）与
`offset: timedelta`（默认由 `add_memory` 以 500ms 构造），用于给同 session 后续消息递增时间
（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:28-35,86-100,275-276`）。

### 0.5.5 能力证据摘要

| 能力 | 一手事实 |
|---|---|
| memory-point 可得性 | `add_memory()` 内部创建 `MemoryEntry`，但返回字典不含 entries、ids 或数量（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:363-392`）。 |
| source id 可得性 | 官方 `retrieve()` 仍只返回格式化 `list[str]`；本项目 adapter 保留 raw payload，并由 M0-7b 透传 singular public external id。初始 entry 可得；LoCoMo post-update 无 output-to-source semantic mapping，相关 provenance metric 为 N/A，B5 当前为 🟡。 |
| 效率字段清单 | `add_memory()` 返回仅有 `api_call_nums` 这一计数字段，另带 `add_input_prompt/add_output_prompt`（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:267-271`）；逐阶段累计 token/call 字段由 `get_token_statistics()` 单独返回（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:709-748`）。 |

### 0.5.6 历史取证报告（2026-07-13；现状以 §B5 为准）

- 取证范围仅为本节；未修改 §0 与 §B1-B11 既有内容，未改代码，未调用真实 API。
- 返回分支可由同一张表完整描述，未触发停工条件（返回点：
  `third_party/methods/LightMem/src/lightmem/memory/lightmem.py:300-318,325-327,392,707`）。
- 发现既有 §0 表述“adapter 落到 `LightMemory.retrieve()`”与当前代码不完全一致：adapter
  实际调用 `text_embedder.embed + embedding_retriever.search(return_full=True)`，以保留官方
  `LightMemory.retrieve()` 会格式化丢弃的 payload（`src/memory_benchmark/methods/lightmem_adapter.py:1019-1078`；
  `third_party/methods/LightMem/src/lightmem/memory/lightmem.py:693-707`）。依卡片纪律只在此记录，未改 §0 原文。

## B1-B11 逐项

- **B1 来源锁与接口选择 ✅**：vendored 路径如上；只用 `retrieve+add_memory`，不用其
  chat 入口（公平性）。审查记录 `docs/workstreams/ws02.7-method-track/notes/lightmem-m0-audit.md`。
- **B2 注入粒度 ✅（2026-07-14 frozen-v1 收口：halumem=SessionBatch 整批+force
  刷洗已落地实证（M0-8+s2 run），姿态声明齐备,下述历史推理留档）**：
  locomo=turn/batch、longmemeval=pair。**HaluMem memory_point：
  官方接口无此能力（M0-3 实锤，§0.5.1）**——add_memory 只返回 prompt 列表 +
  api_call_nums，内部构造的 `list[MemoryEntry]` 不外露。叠加注册面缺口
  （task_families={CONVERSATION_QA}，registry.py:770，operation-level 进不去）。
  **B5+ 改造评估（2026-07-13 用户纠偏后修正）**：HaluMem 要的是**单个 session
  的增量 memory points**，不是累计全量——直答两问：add_memory **既不返回**当次
  输入产出的 entries、**也没有** session 概念/内部 session id（M0-3 §0.5.1）。
  因此"包装 offline_update"不是完整方案，完整对齐 = ① **session 级注入**
  （官方 `messages` 收 list，注入粒度天然可调——用户观察正确）+ ② session 末
  force_segment/force_extract 强制刷洗 + ③ 包装层捕获"该次 session 调用期间"
  构造的 entries → 增量归属自然对齐。**语义代价留档**：逐 session 强制抽取
  改变 LightMem 自然分段节奏，属 HaluMem 评测协议所需，报告须声明。
  **"是否过度介入算法核心"的裁决判据（用户 2026-07-13 质疑后定）**：
  ① force 参数是官方公开 API 旋钮、wrapper 只读观察，都不改算法内部——红线
  是改抽取逻辑/存储结构；② 但"官方旋钮的非常规使用节奏"仍可能失真 →
  前置取证 HaluMem 官方 harness 的喂法（M0-5 卡）。
  **✅ 裁决（2026-07-13，M0-5 证据 `notes/m0-5-halumem-harness-feeding.md`）：
  方案公平、不牵强，采纳。** 三条证据：① 官方六个 wrapper **全部 session 级
  批量注入**（Mem0 整 session 一次 add，eval_memzero.py:168-194）；② **Memobase
  = 官方自己就是"强制 flush + 事后增量收集"姿势**——每批 insert 后显式
  `u.flush(sync=True)`，完毕后按本次起始时间直读底层 DB 增量
  （eval_memobase.py:101-114,150-174），比我们的 wrapper 只读捕获**更深**
  （直读被测系统数据库）；③ **Zep 先例 = 兜底政策有官方背书**：收集不完整时
  官方照跑但 README 显式声明 extraction 指标"不能准确反映性能"
  （eval/README.md:137-141）——若我们捕获路径有缺口，同样如实声明或记 N/A，
  不硬造。红线不变（不改抽取逻辑/存储结构）；报告仍须声明 force 刷洗对
  分段节奏的语义代价。剩余前置 = 注册面缺口（task_families）与 wrapper 实现，
  排 membench/beam 之后。
  横向提醒：逐 method 同款核（Mem0 的 end_session 已按 session 聚合
  add().results，是现成对齐样板）。不改造则 HaluMem 格 = N/A。
  **HaluMem × offline_update 姿态声明（2026-07-14 架构师裁决）**：LightMem 的
  `offline_update_all_entries` 在本框架**只在 locomo 路径**跑（adapter:512 构建
  末 + :668 end_conversation，`_is_native_locomo` 守卫）；**HaluMem 路径不跑**——
  交错型 benchmark 结构上不存在"答题前"的 post-build 时点（QA 与灌入逐 session
  交替），逐 session 跑全库 offline update = O(n²) LLM 成本 + 反复改写旧条目，
  比 force 刷洗偏离算法设计更远。因此 HaluMem QA/update-probe 是在"抽取即插入、
  未离线整理"的在线状态上测——这是 benchmark 形状约束下所有 method 的共同姿态
  （官方六 wrapper 同理），属声明语义非缺陷；update 指标低分若出现，如实报告为
  LightMem 在线姿态的真实测量。
  **offline consolidation 覆盖面（2026-07-15 online-soft 卡施工落地）**：① locomo
  的 Phase 1 主线（`lifecycle_profile="online_soft"`）不再跑官方 post-build
  consolidation，与其余四格同一 direct-insert 时点；官方 `score_threshold=0.9`
  论文值 vs 本项目 TOML 0.8 repo 默认的三岔口留待 `locomo_offline_consolidated`
  补充轨复现时再对齐（`experiments/locomo/add_locomo.py:445-451`）；② longmemeval
  **不跑**（官方主评测管线 `run_lightmem_gpt.py` 自述"complete evaluation
  pipeline"不含 offline update；`offline_update.py` 被官方 readme 定位为独立
  "utility script" 演示件,不在主管线）；③ membench/beam 无官方实验,采
  lme 同款轻姿态（不跑）;④ halumem 见上条（交错型结构上无 post-build 点）。
  adapter 现由 `_should_run_locomo_offline_consolidation()` 统一判定 legacy
  `add()` 与 v3 `end_conversation()` 两处调用点：只有显式
  `lifecycle_profile="locomo_offline_consolidated"` 才触发，且要求
  `LightMem.__init__` 收到的 `benchmark_name == "locomo"`，否则构造期
  fail-fast；不再读 `_is_native_locomo`/`_is_locomo_conversation` 的
  source_path 启发式判断是否执行 consolidation（这两个 helper 仍用于选择
  METADATA_GENERATE_PROMPT，与是否 consolidation 无关）。
- **B3 隔离 ✅ 物理**：per-conversation Qdrant collection + 独立路径（adapter:388-390，
  summary 库另置 :390）；clean-retry = 删目录（:1660-1664），干净。并行安全。
- **B4 formatted_memory+时间戳 ✅（MemBench 100k explicit-None 已验收）**：locomo 官方
  speaker 分组 + `_format_lightmem_memory`；longmemeval native 已透传
  `prompt_messages` 对齐官方（M0-1b）。**时间戳逐 benchmark 实测**：locomo ✓、
  membench **仅 0-10k smoke 四源 ✓**、beam-100k `15 March 2024` ✓（月名转换端到端）、halumem
  probe `15 December 2025, Mon` ✓;**lme 例外声明**：smoke 1 round 抽取为空,
  时间戳无非零样本——格式化管线与其他四家共用 `_format_lightmem_memory`,
  机制同源,实测留待更大切片（cost-probe/full）。MemBench Phase A 已删除旧 session
  fallback，258,000 个 noise 诚实保持 None。架构裁决允许仅在 online-soft 中新增
  `missing_timestamp_policy=preserve_none`，不进入 consolidated 时间排序；Phase B 已由
  `915f73c` + `3968373` 强验收，只有 explicit 双 None 放行，缺键/空串仍拒绝。该格可进入
  后续免费 dry-run/smoke，但结果必须声明 framework-extended compatibility，既有 0-10k
  timestamped 证据仍不能外推成 upstream 对 None 的 native parity。
- **B5 provenance 🟡 逐格（2026-07-15 重开）**：M0-7b 已把公开
  `external_id` 透传为 `MemoryEntry.source_external_id`，初始 insert 的单来源映射与
  lme/membench/beam 等不跑 post-build merge 的路径仍成立。2026-07-13
  `lm-locomo-unified-prov1` 确实产出非空 items，但当时只验证了 id 空间/字段存在，
  **没有审计 LoCoMo 后续 `offline_update_all_entries` 的血缘变换**。

  2026-07-15 复核确认：action=`update` 会整合 candidate 文本，却只覆盖 target 的
  `memory` 并保留旧 singular id/vector；因此既有 LoCoMo Recall@10 可机械算出但
  不能证明完整 turn lineage，原 score=0.0 的“可信真实测量”定性撤回。第一版曾批准
  plural 输入并集；Sonnet 5 `3e2d957` 忠实实现并通过 57 项定向测试，但用户指出新
  memory 未必仍承载全部输入事实，架构师复核后改判：该 union 只能作审计 lineage，
  不能进入 Recall/NDCG 的 `source_turn_ids`，commit 不合入。LoCoMo post-update
  provenance metric 应 N/A。新主线 online-soft 未经过该 mutation，可按逐题 items 审
  semantic provenance；lifecycle 与 missing-time 前置均已关闭，`RetrievalEvidence` M0
  已强验收：online-soft 按实际 items 写 valid(turn)/N/A，consolidated 恒 N/A，rank 审计前
  保持 pending；不建手写 method × benchmark × metric 白名单。M1 再由 evaluator 消费。
  完整证据与现行裁决见
  `ws02.7/branches/lightmem-lifecycle/notes/lightmem-update-lifecycle-ruling.md` 与
  `ws02.7/branches/retrieval-metrics/notes/retrieval-metric-eligibility-ruling.md`。
- **B6 flush ✅ lifecycle identity 已强验收**：`add_memory(update="offline")`
  的 force 刷洗与 direct insert 已成立；`online_soft` 主 profile 下 conversation
  边界不再追加 queue + all-entry update，LoCoMo 与其余四格同一时点。显式
  `locomo_offline_consolidated` 补充 profile 保留旧行为（要求显式
  `benchmark_name=="locomo"`，否则构造期 fail-fast）。`LIGHTMEM_ADAPTER_VERSION`
  已升至 `conversation-qa-v3`（v2 为 lifecycle，v3 再加入 missing timestamp policy），
  旧 post-update 或缺 policy 的 run 不会误 resume 到新 soft profile。lifecycle 主体
  `825132f` 与 missing-time `915f73c` + `3968373` 均已通过架构师定向/全量门。
  不 flush 检索到空记忆的历史判例仍有效。
- **B7 效率插桩 ✅**：build/answer/judge 三角色 api_usage 真 token（2026-07-12 效率审计
  无拦截缺口）；LightMem add_memory 自带 token/api_call_nums 返回值可做交叉参照（待留档）。
- **B8 副作用/clean-retry ✅（2026-07-14 frozen-v1 收口）**：物理隔离 + 删目录
  清理已具备；**检索纯读已锚死**：`LightMemory.retrieve`
  （`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:648-710`）=
  embed → `embedding_retriever.search` → 可选 tag 过滤 → 字符串格式化,全程
  无任何 insert/update/save,唯一副作用是日志写文件（观测性,非算法状态）。
- **B9 模型口径 ✅（当前 MiniLM smoke build；性能参数待后裁）**：证据全表
  `ws02.7/notes/lightmem-native-config-threeway.md`。历史主/作者候选差异已实锤：
  extract_threshold 0.5 vs 0.1、compression rate 0.7 vs 0.6(locomo)/0.8(lme)、offline
  score 0.8 vs 0.9(locomo)。这些不是现在要为 smoke 调优的理由；当前五格继续使用已验收
  TOML 与 local HF all-MiniLM-L6-v2/384/Qdrant cosine，零重建。本地 revision/hash 尚未 pin，
  如实声明 `local_unpinned`。真实效果实验前再裁 `official_full` 最终数值；作者 LoCoMo/LME
  参数只进入对应 `author_<benchmark>` section，不自动按 benchmark 切换。repo schema 顶层
  `text_embedder=None` 且 compressor/topic 默认 OFF 的事实继续保留，不能把不可运行默认当权威。
- **B10 🟡（旧 config-track truthful；新 TOML/完整 builder 待迁）**：历史 M0 R1/R2 已让
  manifest 显式写 `native_scope=readout_only`、实际 embedding、answer/judge model source，
  严格参与 evaluate/resume，旧产物身份可信。现行政策不再新增双轨：首个作者校准 run 前，
  LoCoMo/LME 改由 `author_locomo`/`author_longmemeval` section 选择各自完整 answer builder，
  并验收从 speaker/time/retrieved memories 到最终 messages 的变量构造；不能只复用旧
  `ANSWER_PROMPT` 模板或 readout bundle 宣称 parity。
- **B11 smoke+冻结 🟡（2026-07-15 lifecycle + metric contract 重开）**：2026-07-14
  五格既有 flow-through 与 answer/judge/成本证据仍有效；既有 LoCoMo post-update recall
  数字撤销。online-soft lifecycle identity 已在 `825132f` 完成；逐题 RetrievalEvidence
  M0 已强验收落盘，当前下一门是 M1 evaluator requirement。LightMem preserve-none Phase B
  已关闭。不得用真实 API 绕过结构施工，也不为
  “所有指标都亮”强跑。
  以下为 2026-07-13~14 的历史 smoke 证据：
  ① unified：空库悬案已关闭（diag-log1 复跑：1 round → force 刷洗 → 抽取 2 条
  记忆 → 检索命中，sentinel=0；此前空库判为抽取 LLM 单次返 0 波动，非结构性 bug）。
  ② native（lm-locomo-native-smoke1）：**产物级实锤读出分叉**——answer 用官方
  ANSWER_PROMPT 经 prompt_messages（与 unified 模板逐字不同）、judge 用
  `lightmem_locomo_paper_native_judge_v1` 返回官方 JSON 契约；manifest
  config_track=native；且是 **M0-1c 新路径 `smoke/native/` 的首个实战验证**。
  ③ **longmemeval 双轨 smoke 亦通**（2026-07-13：predict answers=1/1 + judge
  evaluate 双轨落盘；native 读出产物级核实 = 官方 [system,user] `Question time:…`
  模板）。**lme 空记忆真相**：memory_build 输出仅 7 token ≈ 空抽取，
  formatted_memory=哨兵、injected_tokens=0（真实零）——1 round 任务型对话抽
  不出记忆点属方法合法行为，与 locomo 首跑同现象；两轨 build 均为 unified
  配置（native build profile 未实现）故双轨同空自洽。cost-probe 整 instance
  时复查内容检查。
  ④ **五件套认证进度**（checklist B11 口径）：locomo/lme 格 ①predict
  ②**全指标 evaluate**（2026-07-13 补全，用户点出遗漏：locomo=judge 0.5 +
  locomo-f1 + f1 + locomo-recall(n=0 条件式 N/A 路径正确)；lme 双轨=judge +
  f1 + longmemeval-recall(N/A) + longmemeval-retrieval-rank(N/A)——recall 类
  n=0 是 provenance=none 的**正确**输出，非故障）③效率观测（四 run 落盘实证，
  injected tokens 口径见 `efficiency-injected-tokens-policy.md`）④时间戳抽查
  （locomo ✓；lme 空记忆留痕）已达成；⑤ **并行冒烟 locomo 已通**（2026-07-13 `lm-locomo-unified-par2`：
  2 conv × workers=2，answers 2/2、judge 0.5——首个非零分；并行机制与 track
  无关，unified 一次即认证该格）。**lme 格 ⑤ 待跑**（同一 worker 池机制 +
  per-instance 物理隔离，风险低，随 cost-probe 顺带补）。→ **locomo 格 =
  首个五件套全齐的格子**。
  ⑤ **membench 格五件套全齐（2026-07-13，第二个全齐格）**：M0-4 离线核查放行后
  实跑——①predict `lm-membench-unified-s1-0-10k` 4/4、sentinel=0（run_id 带
  `-0-10k` variant 后缀，multi-variant 判例再验证）；②全指标：choice-accuracy
  0.5(2/4) + source-accuracy 0.5 + membench-recall n=0（条件 N/A 正确；f1 设计上
  不含 membench，选择题）；③效率三类齐（build/retrieval/answer latency +
  injected tokens mean=108.25 非零 + `token_measurement_source=api_usage`）；
  ④formatted_memory 4/4 全带 `[Memory recorded on: …]` 时间戳、全真实记忆——
  B4 的 membench 时间戳实测=**有**（M0-4 §3 预判兑现）；⑤并行 par2 4/4、
  choice-accuracy 与 s1 一致(0.5)。
  **B3 附带裁决（2026-07-13 用户问逻辑隔离改造）**：**不改造**。LightMem
  MemoryEntry/payload 无 namespace 字段（§0.5.4 字段表）、adapter 检索
  filters=None → 原生无逻辑隔离能力，按 B3 判据物理兜底正确；改造需动存储
  结构+检索过滤（红线级）且**零评测能力收益**（不同于 source_id→recall），
  不符合 B5+ 改造原则。物理隔离的向量存储总量与逻辑隔离相同（同一批向量只是
  分库），真实代价是 per-conversation 固定开销（embedding 模型逐 conv 重载
  ≈2s/个，smoke 日志 "Loading weights" 连刷即此）；若 full 阶段（lme×500 conv）
  实测成瓶颈，优化路径=**adapter 层 embedder 实例共享缓存**（框架侧、零
  third_party），不走逻辑隔离。
  ⑥ **beam 格与 lme 格⑤ 已于 2026-07-13 补齐**（beam 双 variant + par2b
  2conv×2workers；lme par2 2/2——详录 ws02.7 README 断点区 2026-07-13 各条）
  → 四格全齐。
  ⑦ **halumem 格（2026-07-14，lm-halumem-unified-s2）**：①predict 流通 1
  conv/4 session/1 QA（s1 首跑撞 probe-scope bug=M0-11 修复后 s2 通过）；
  ③效率三类落盘（llm_call×5 + conversation_efficiency×5 + question×1）；
  ④时间戳实测=update probe 的 formatted_memory 带
  `[Memory recorded on: 15 December 2025, Mon]`（HaluMem 真实数据端到端）；
  **session_memory_reports 真实数据首秀**：s4 捕获 3 条真实记忆
  （capture_status=ok），s1-s3 空捕获如实 `empty`（Zep 先例：跑但声明——
  抽取 LLM 每 session 都调了（llm_call 齐），未产出即如实记零，不造数）；
  ②evaluate 依赖序实锤：**memory-type（免费）是 extraction+update 分数的
  合成指标,必须后评**（官方共同分母怪癖的连带），付费三项先行；
  ⑤ **N/A（2026-07-14 裁决,M0-12 停工证据 `notes/m0-12-halumem-par-smoke.md`）**：
  operation-level runner 设计上单 worker（入口硬校验 max_workers==1 +
  conversation 串行循环），并行冒烟无协调路径可验；operation-level 并行化
  = full 阶段前的独立设计项（wall-clock 需要时再立卡）。
  ⑧ **halumem ② 收口 → 五格通关（2026-07-14）**：四指标全落盘——
  extraction 0.0/108 点（judge 理由 "empty extracted memories" = s1-s3 空
  捕获的诚实后果）、update 0/7（judge 推理实读了 s4 捕获的 3 条记忆逐条
  比对=真实判定）、**qa 1.0/1（Memory Boundary 题,gold="Unknown; not
  provided"，答 "No information available" 判 Correct=真金,不知为不知）**、
  memory-type 0.0/3 型（extraction+update 合成,依赖序=付费先行）。低分=
  LightMem 在线姿态+稀抽取的真实测量（B2 姿态声明覆盖）,smoke 判据是
  流通不是分数。**B11 smoke 半场完成:五格（locomo/membench/beam/lme/
  halumem）全绿;冻结半场（frozen-v1 note + B2/B4/B8 残留 🟡 收口核对）
  待架构师专场。**
  剩余：frozen-v1 note（含 B2/B4/B8 收口）→ native build profile →
  cost-probe → method-frozen-v1（真实 resume 验证缓期至预算批复，已声明
  缺口）。

## 特殊情况
1. **StructMem（`--enable-summary`）是另一个实验**：换 build+检索+embedding
   （text-embedding-3-small），非 paper headline，也改变实现语义，不能伪装成普通
   `author_locomo` TOML 参数；旧判例保留在 `dual-track-config-policy.md` §10。
2. 现行配置政策是 `method-toml-and-answer-builder-policy.md`；既有作者 prompt 资产
   `methods/lightmem_native_prompts.py` 仍解释历史 readout（longmemeval builder 透传
   prompt_messages，2-message 守卫）。track-aware 路径层已生效（M0-1c，2026-07-13）：
   旧 run 落 `…/{mode}/{track}/{run_id}`，旧布局仅可 evaluate 不可 resume；新配置迁移前
   不改写这些历史身份。
3. **日志已知限制**：LightMem 内部诊断走 `self.logger`（`Created N`=INFO :372、
   `No entries found`=WARNING :474/:554），INFO 级连它自己的内部日志文件都不落
   （实测 0 字节）；框架 `logs/method.log` 亦未捕获。真需要内部 INFO 时再查其
   logger 配置，当前不阻塞。
