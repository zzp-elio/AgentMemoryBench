# LightMem offline update × Recall@k 有效性纯取证

> 日期：2026-07-15
> actor：Claude Sonnet 5（本会话系统提示自报模型；按 AGENTS.md 2026-07-08 判例，
> actor 交接记录须核实自己会话的实际模型，不套用协作池里的名字）
> 任务卡：`docs/workstreams/ws02.7-method-track/actor-prompt-lightmem-offline-recall-audit.md`
> 性质：纯取证，零真实 API，零生产代码改动，本 note 是唯一交付物。
> worktree：`/Users/wz/Desktop/mb-actor-lm-recall`，branch
> `actor/lightmem-offline-recall-audit`（新建，未与其他 actor worktree 冲突）。

## 1. 结论摘要（只写事实，不作最终裁决）

逐条回答任务卡 §1.1 五问：

1. **offline update 的输入/候选/输出**：`offline_update()`
   （`lightmem.py:398-459`）输入是本次 `add_memory()` 抽取出的新
   `MemoryEntry` 批次，输出副作用是把它们逐条 embed 后 `insert` 进向量库
   （`lightmem.py:411-444`）。真正做“合并/删除”的是另外两个函数：
   `construct_update_queue_all_entries()`（`lightmem.py:461-541`，输入=向量库
   **全部**已存 entry，输出=给每条 entry 写 `update_queue` 候选列表）和
   `offline_update_all_entries()`（`lightmem.py:543-646`，输入=向量库全部
   entry + 各自 `update_queue`，输出=对每个 target entry 调用
   `manager._call_update_llm` 决定 `update`/`delete`/`ignore`）。
2. **哪些操作 add/update/delete/merge，旧 entry 是否保留**：`insert`
   只在 `offline_update()` 发生（新 entry）。`offline_update_all_entries()`
   只有两种写副作用：`update`=原地覆盖 target entry 的 `memory` 文本字段
   （`lightmem.py:621-625`，`vector`/其余 payload 字段不变，见下）；
   `delete`=整条 target entry 从向量库移除（`lightmem.py:614-619`）。**没有
   第三种“生成新 id 的合并”**。对某个 target 的单次 update 调用只修改该
   target，不在同一次调用里写 candidate_sources；但整轮函数会并行遍历全部
   entry，一个 candidate 仍可能在自己的 `update_entry` 任务中作为 target 被更新或
   删除，因此不能笼统声称它在整轮后必然原样保留。`_call_update_llm` 只读
   `target_memory`/`candidate_memories` 两组文本（`factory/memory_manager/openai.py:
   379-406`），无 id 参与判定。
3. **update 前后 embedding retrieval 的 rank 单元**：官方脚本 `search_locomo.py`
   完全不调用 `LightMemory.retrieve()`（那个方法只返回 `list[str]`，无 id，见
   `lightmem.py:648-711`），而是自己的 `VectorRetriever.retrieve()`
   （`retrievers.py:107-132`）：一次性 `load_entries(..., with_vectors=True)`
   拿到全部 entry 的**当前 payload + 原始存储向量**，对每个 entry 用其存储
   向量与 query 向量算 cosine 后排序截断。**`update` 动作只改文本、不重算
   embedding**（`lightmem.py:623` `vector = entry.get("vector")` 原样传回
   `update()`），所以 rank 单元 = 合并前的旧向量 + 合并后的新文本，两者已经
   不是同一次生成的产物。
4. **`source_id`/`sequence_number`/`external_id` 的转换点**：官方
   `add_locomo.py:130-154` 构造消息字典只有
   `role/content/speaker_id/speaker_name`，**从未设置 `external_id`**——因此
   pristine 官方 LoCoMo 全流程下 `MemoryEntry.source_external_id` 恒为
   `None`（该字段本身是我方 2026-07-13 M0-7b 批准的 third_party 最小 diff
   新增，见 `notes/m0-7-lightmem-provenance.md` 全文，本次独立复核字段与
   diff 仍然一致）。`source_id`（LLM 在抽取时返回，`sequence_number // 2`）
   本身在 `_create_memory_entry_from_fact()`（`memory/utils.py:321-337`）
   写入 `MemoryEntry` 后即固定；`offline_update_all_entries` 的 `update`
   分支用 `new_payload = dict(payload)` 浅拷贝旧 payload 只改 `memory`
   键（`lightmem.py:620-622`），因此 `source_external_id`（我方 diff 新增
   的 payload 键）**在合并后原样不变，不随文本合并而更新或清空**。
5. **LoCoMo 官方脚本在 offline update 前还是后答题/检索**：脚本本身**同时
   支持两种**且互相矛盾：`search_locomo.py` 的 argparse 默认值
   `DEFAULT_QDRANT_DIR = './qdrant_pre_update'`（`search_locomo.py:39`）——
   若不传 `--qdrant-dir` 就是 update **前**；但仓库自带 `readme.md` 的
   Quick Start 命令（LightMem 与 StructMem 两种模式、也就是 README 结果表
   实际使用的调用方式）都显式传了 `--qdrant-dir ./qdrant_post_update`
   （`readme.md:53,72`）——即**官方 README 报告的数字用的是 update 后**的
   检索。两条路径都在仓库里，默认参数值与文档化调用方式不一致；本 note 未
   触发任务卡 §3 的“无法判定主线”停工条件，因为 README 明确写出了它自己
   报告数字所用的调用方式（post-update），只是这与脚本的 argparse 默认值
   相反，两者都据实记录，不替架构师选边。

另有一条任务卡未直接问、但取证中发现且证据充分的事实，一并列入结论：
**官方 LightMem LoCoMo 评测（`search_locomo.py`/`readme.md`）里根本没有
“Recall@k”这个指标**——README 结果表（`readme.md:113-196`）只有 LLM judge
ACC(%)、F1、BLEU-1、token/耗时统计；turn-id 归因式 Recall@k 是我方框架（和
下文 MemoryData）各自独立引入的评测口径，不是从上游继承或复现的官方数字。

## 2. 官方 LightMem 时序表（third_party/methods/LightMem）

| 阶段 | 函数:行号 | 输入对象 | 输出对象 | 写副作用 | 来源字段 |
|---|---|---|---|---|---|
| 消息规范化 | `MessageNormalizer.normalize_messages`，`lightmem.py:59-104` | 原始 message dict/list | 深拷贝后补 `session_time`/`time_stamp`/`weekday` 的消息 | 无（纯内存） | 不涉及 |
| 分段+抽取触发 | `add_memory`，`lightmem.py:204-393` | 规范化消息 | `memory_entries: List[MemoryEntry]`（每条=一个 LLM 抽取出的 fact） | 无（尚未落盘） | `source_id`（LLM 返回）→`_create_memory_entry_from_fact` 写入 entry；官方从不设 `external_id`（见 §1.1 Q4） |
| 初次持久化 | `offline_update`，`lightmem.py:398-459` | 本次新增 `memory_entries` | 无新对象；副作用式写库 | **INSERT**：`embedding_retriever.insert(...)`（:440-444），payload 含 `source_external_id` 仅当非 None（:437-439） | `source_external_id`（官方路径恒 None） |
| 候选队列构建 | `construct_update_queue_all_entries`，`lightmem.py:461-541` | 向量库**全部**已存 entry（`get_all()`，:475） | 无新对象；给每条 entry 追加 `update_queue`（更早/同时且相似的候选 id+score 列表） | **UPDATE**（payload 追加字段，`embedding_retriever.update`，:529），vector 不变 | 不涉及 provenance 字段 |
| 合并/删除 | `offline_update_all_entries`，`lightmem.py:543-646` | 向量库全部 entry + 各自 `update_queue` | 无新 id；对每个 target entry 判定 `update`/`delete`/`ignore`（`_call_update_llm` 只读两组文本，`memory_manager/openai.py:379-406`） | **UPDATE**（只改 `memory` 文本，`vector`/`source_external_id`/`time_stamp` 等字段原样浅拷贝，:620-625）或 **DELETE**（整条移除，:614-619） | `source_external_id` 合并/删除时不刷新（原样保留或随整条消失） |
| 官方 retrieve()（未被 LoCoMo 评测使用） | `LightMemory.retrieve`，`lightmem.py:648-711` | query 文本 | `list[str]`（仅 `time_stamp weekday memory` 拼接） | 无 | 不暴露任何 id |
| LoCoMo 评测检索 | `VectorRetriever.retrieve`，`retrievers.py:107-132` | `QdrantEntryLoader.load_entries(..., with_vectors=True)` 全量 entry（`search_locomo.py:338`） | 按 cosine 排序截断的 entry 列表（含 `id`/`score`/`payload`） | 无（只读） | payload 里若有 `source_external_id`（官方路径无）会原样带出，但从不使用 |
| LoCoMo 答题/评分 | `process_sample`，`search_locomo.py:287-530` | 检索结果+question | LLM judge CORRECT/WRONG + F1/BLEU-1 | 落盘 JSON | 不涉及 turn-id 归因 |

## 3. 本框架 provenance/Recall@k 链表（src/memory_benchmark）

| 环节 | 函数:行号 | 关键行为 |
|---|---|---|
| 公开 turn id 来源 | `benchmark_adapters/locomo.py:491` | `turn_id = raw_turn.get("dia_id") or f"D{session_number}:{turn_index}"`——即公开 `Turn.turn_id` **就是**官方 `dia_id` 本身；`evidence`（私有 gold，:247）也是原始 `dia_id` 字符串列表，二者天然同一 id 空间（插入时刻） |
| 消息构造注入 | `lightmem_adapter.py:1289-1321`（LoCoMo）/`:1323-1373`（LongMemEval） | 每条写入的 user（及 LoCoMo 合成空 assistant）消息都带 `"external_id": turn.turn_id`；`messages_use` 全局固定 `"user_only"`（`lightmem_adapter.py:428`），与官方一致，保证 `source_id*2` 恒定位到 user 位置 |
| third_party 透传（M0-7b 已批准 diff） | `third_party/methods/LightMem/src/lightmem/memory/utils.py:125,337`；`lightmem.py:437-439` | `external_id` 经 `assign_sequence_numbers_with_timestamps`→`_create_memory_entry_from_fact`→`MemoryEntry.source_external_id`→仅非 None 时写入 payload；未附 id 的旧调用路径行为不变（详见 `notes/m0-7-lightmem-provenance.md` §6.3） |
| offline update 触发点 | `lightmem_adapter.py:482-515`（`add()`，LoCoMo 立即触发）/`:659-669`（`end_conversation()`，v3 native 路径） | 忠实复刻官方 `add_locomo.py` Phase 3：`construct_update_queue_all_entries()` + `offline_update_all_entries(score_threshold=config.offline_update_score_threshold)`（`_run_locomo_offline_update`，`lightmem_adapter.py:1123-1140`），同一顺序、同一两个函数 |
| 检索 | `_retrieve_with_payload`，`lightmem_adapter.py:1142-1201` | 直接调用 `backend.text_embedder.embed` + `backend.embedding_retriever.search(limit=self.config.retrieve_limit, return_full=True)`（`retrieve_limit=60`，`configs/methods/lightmem.toml:14,31`，对齐官方 `--total-limit 60`）；绕开官方 `LightMemory.retrieve()`，与官方评测脚本自己绕开的做法同构，但**不读 `query.top_k`**（见下） |
| provenance 转换 | `_retrieved_items_from_lightmem_memories`，`lightmem_adapter.py:1226-1264` | 对每条检索结果，要求 `payload["source_external_id"]` 是非空字符串，否则**整次结果**回落 `items=None`（不返回部分来源，:1232-1235,899）；每个 `RetrievedItem.source_turn_ids` 恒为**单元素元组** `(source_external_id,)`（:1260），取自检索时刻 payload 的**当前**值 |
| top_k 声明与实际检索脱钩 | `runners/prediction.py:2762` vs `lightmem_adapter.py:1174-1180` | `RetrievalQuery.top_k` 在 `_retrieval_query_from_question()` 里对**所有 method/benchmark 硬编码为 `10`**（与任何 method 配置无关）；LightMem adapter 的 `_retrieve_with_payload` 全程不读 `query.top_k`，只用 `self.config.retrieve_limit`（=60）；`retrieved_items` payload 不做截断（`_retrieved_items_payload`，:2795-2800，原样 60 条），真正的 `[:top_k]` 截断发生在 evaluator 侧（下一行） |
| recall 评分 | `evaluators/locomo_recall.py:103-142,182-217`；`longmemeval_recall.py:183-229` | 用 artifact 里的 `retrieval_query_top_k`（=10）对（最多 60 条的）`retrieved_items` 做 `[:top_k]`，并集 `source_turn_ids` 与私有 `evidence` 精确匹配算 `hits/len(evidence)` |
| 强校验实际检查的内容 | `locomo_recall.py:103-129`；`longmemeval_recall.py:183-205` | 只检查：`retrieval_query_top_k` 是否存在且为正整数、`retrieved_items` 是否是 list、`[:top_k]` 内每条的 `source_turn_ids` 是否非空——**不检查** `retrieval_query_top_k` 与 method 实际配置的检索宽度（如 `retrieve_limit=60`）是否有语义关系，也不检查 `provenance_granularity="turn"` 在**检索发生那一刻**是否仍然准确（即是否发生过合并/删除），纯粹是字段存在性/类型校验 |

## 4. MemoryData 对照表（第三方框架参考/MemoryData，只读本地资产，独立
worktree 无该 gitignored 目录，未复制，全部从主树只读路径核对）

| 环节 | 文件:行号 | 行为 |
|---|---|---|
| 运行配置 | `config/hybrid_lightmem.yaml:9-10` | `retrieve_num: 10`；`lightmem_ingest_mode: direct` |
| backend 构造 | `methods/lightmem/lightmem_adapter.py:51-142` | `LightMemory.from_config(...)`，`metadata_generate=False`/`text_summary=False`/`pre_compress=False`/`topic_segment=False` 均为默认值且 yaml 未覆盖——即**官方 `add_memory()` 的压缩/分段/LLM 抽取整条管线在 direct 模式下从不被调用** |
| 写入（direct 模式） | `lightmem_adapter.py:144-192` | **不调用 `add_memory()`**：自己的正则解析器 `_parse_chunk_messages`（:285-357）切分/识别 role，`_render_messages`（:373-393）拼回文本，`_attach_locomo_metadata`（:395-399）→`build_locomo_storage_text`（`utils/locomo_utils.py:44-49`）把 `[LOCOMO_META chunk_id=... source_ids=id1,id2,...]` header 拼在文本最前面，手工构造 `MemoryEntry(memory_class="verbatim_chunk", memory=header+正文)`，只调用 `self.lightmem.offline_update([entry])`（:192，只做 embed+insert 这一半） |
| 合并/删除 | 全仓库 `grep` | `construct_update_queue_all_entries`/`offline_update_all_entries` **在该 adapter 及其调用点（`utils/agent.py:3203-3212`）中均未出现**——本审计问的“offline update 合并/删除对 Recall@k 的影响”在 MemoryData 的 LightMem 评测里**不存在**，因为这条合并/删除算法从未被调用 |
| 检索 | `lightmem_adapter.py:194-217` | 同样绕开官方 `LightMemory.retrieve()`；自己 `text_embedder.embed`+`embedding_retriever.search`；返回字符串时把 header 留在正文里（`parse_locomo_source_ids` 判断是否已带 header，:210） |
| provenance 恢复 | `utils/agent.py:3203-3216`；`utils/locomo_utils.py:52-71` | 从每条检索到的原始文本正则解出 `[LOCOMO_META ...]`，`source_ids` 是**该 chunk 覆盖的全部原始 `dia_id` 列表**（可能多个，取决于 `agent_chunk_size=4096` token 窗口打包了多少原始 turn，`config/hybrid_lightmem.yaml:7`），不是单一 id |
| 官方对照结论 | `notes/memorydata-recall-retrofit-survey.md:39-58`（既有二手 note，本次独立复核源码后结论一致） | MemoryData 自己的实现选择等价于放弃了 LightMem 的压缩/分段/抽取/合并算法，测的是“qdrant embedding RAG + LightMem 存储壳”，不是 LightMem 算法本身；pipeline 模式（真跑 `add_memory`）反而完全不附加 metadata，同样没有 provenance |

**不公平点（事实陈述，不裁决）**：官方 README 报告数字、MemoryData 报告数字、
本框架报告数字，三者的“检索单元”彼此都不是同一个对象——

- 官方 README：单 fact 级 `MemoryEntry`（LLM 抽取产物），跑完整 add_memory
  + offline update 全流程，无 turn-id 归因（只有 judge ACC/F1/BLEU）。
- MemoryData：整块 ~4096-token 原始文本（无压缩/分段/抽取/合并），归因是
  嵌入正文的多 id header。
- 本框架：单 fact 级 `MemoryEntry`，跑完整 add_memory + offline update
  全流程（与官方 README 同源算法路径），归因是外挂 payload 字段、单
  turn id、且合并后不刷新（见 §1.1 Q2/Q4、§3“provenance 转换”行）。

三者中只有本框架与官方 README 走的是同一条算法路径（含 offline
update）；MemoryData 的数字不应被当作“LightMem 算法在 Recall@k 下应有表现”
的校准基准，因为它评测的对象在算法层面就不同（本节列出的差异是本次一手
复核结果，与既有二手 note 结论一致，供架构师参考，不代裁）。

## 5. 待架构师裁决的候选风险

### 风险 A：offline update 后来源合并/删除是否导致 Recall@k 失真

- **支持证据**：
  - `offline_update_all_entries` 的 `update` 分支只重写 `memory` 文本字段，
    `vector`/`source_external_id`/其余 payload 字段原样浅拷贝
    （`lightmem.py:620-625`）；`_call_update_llm` 判定合并/删除时只读
    `target_memory`/`candidate_memories` 两组纯文本，不涉及任何 id
    （`memory_manager/openai.py:379-406`）。
  - `delete` 分支把 target entry（含它唯一记录的 source turn）整条从向量库
    移除（`lightmem.py:614-619`），之后任何问题都不可能再检索到它。
  - 本框架的 `_retrieved_items_from_lightmem_memories` 读的是**检索那一刻**
    payload 里的 `source_external_id`（`lightmem_adapter.py:1243-1260`），
    结构上无法知道合并前还有哪些 candidate_sources 曾经贡献过当前文本。
  - 对当前 target 的单次写操作不会同时写 candidate_sources；但
    `offline_update_all_entries` 并行遍历全部 entry，candidate 可能在另一任务中
    作为 target 被更新或删除。整轮使用最初 `get_all()` 快照选取输入，不能据此
    保证 candidate 在轮末仍原样可检索（`lightmem.py:555,574-631`）。
- **反证/未知**：本卡红线禁止真实 API，未做真实 LoCoMo smoke，因此
  `update`/`delete` 在真实数据上的**实际触发频率**、以及触发后是否真的让
  某个 gold 问题的命中判定翻转（漏判或误判）均未测量；本节只证明了“机制上
  存在这个缺口”，未证明“在当前 `offline_update_score_threshold` 下这个缺口
  的实际影响有多大”。

### 风险 B：rank 单元与 gold 单元是否可比（含 top-k 与检索宽度脱钩）

- **支持证据**：
  - `RetrievalQuery.top_k` 在 `runners/prediction.py:2762` 对所有
    method/benchmark **硬编码为 `10`**；LightMem adapter 的
    `_retrieve_with_payload`（`lightmem_adapter.py:1174-1180`）全程不读
    `query.top_k`，只用 `self.config.retrieve_limit`（=60，
    `configs/methods/lightmem.toml:14,31`，对齐官方 `--total-limit 60`）；
    `retrieved_items` payload 不截断（`runners/prediction.py:2795-2800`）。
  - 因此 `locomo_recall.py`/`longmemeval_recall.py` 当前对 LightMem 算出的
    一律是“60 条检索结果里的前 10 条”，这个“10”与 LightMem 自身配置
    及官方论文配置的“60”没有任何代码层面的关联或校验。
  - rank 单元（单 fact，合并后可能糅合多个 turn 的信息但只声明一个
    source turn，见风险 A）与 gold 单元（LoCoMo 单个 `dia_id`）的粒度
    对应关系在“未发生合并”的条目上是精确的（`turn_id`=`dia_id`，
    `benchmark_adapters/locomo.py:491`），但在“已发生合并”的条目上出现
    风险 A 描述的偏差。
- **反证/未知**：这个 top_k=10 硬编码是**框架级**常量（`longmemeval_recall.py`
  同样读同一个 `retrieval_query_top_k` 字段），并非只影响 LightMem；是否
  所有其他已接入 method 的实际检索宽度也偏离 10（从而这是一个对所有
  method 都同等生效、不改变横向可比性的“共同尺子”），还是 LightMem 的
  60 相对其他 method 的配置值偏离最大（从而单独放大 LightMem 的失真），
  本次审计未逐一核对其余 method 的配置值，留待架构师或后续横向审计确认。

### 风险 C：当前粒度强校验是必要 fail-fast、过强，还是只强在结构不强在语义

- **支持证据**：`locomo_recall.py:103-129`、`longmemeval_recall.py:183-205`
  的 `ConfigurationError` 触发条件只有三类：`retrieval_query_top_k`
  缺失/非正整数、`retrieved_items` 缺失/类型不对、`[:top_k]` 内某条
  `source_turn_ids` 缺失或为空。三者都是**存在性/类型**检查，没有任何一处
  检查“`retrieval_query_top_k` 是否与 method 实际检索宽度语义相容”（风险
  B）或“`provenance_granularity` 在检索这一刻是否仍然准确反映 payload
  实际来源”（风险 A，即是否发生过合并/删除）。
- **反证/未知**：对 LoCoMo/LongMemEval 而言，`provenance_granularity`
  与 gold id 空间在**插入时刻**的兼容性是有保障的——`Turn.turn_id`
  就是官方 `dia_id`（`benchmark_adapters/locomo.py:491`），LongMemEval/
  MemBench/BEAM 三个 benchmark 的对应关系也已由既有
  `notes/m0-9-provenance-breadth.md`（本次未重新逐行复核，仅确认该 note
  仍在且未被后续改动废止）证实无 gap。因此风险 C 并非“完全没有语义
  保障”，而是精确地缺在**时间维度**（插入时刻正确 ≠ 检索时刻仍正确，见
  风险 A）和**宽度维度**（风险 B）这两处，是否需要为这两处补强验证、以及
  补强的代价是否值得，是留给架构师的设计判断，本卡不代裁。

## 停工点

无。本卡三个停工触发条件（官方脚本互斥时序无法判定主线 / vendored diff 与
声称的 provenance 链不一致 / MemoryData 配置指向实现缺失 / 需要真实
API-下载-越权文件）均未触发：§1.1 Q5 的“两条时序”在 README 里有明确的
“报告数字用哪条”的文档化说明（post-update），不构成“无法判定”；M0-7b/M0-9
既有 diff 与 provenance 链经本次独立复核一致；MemoryData 的
`hybrid_lightmem.yaml` 指向的 `LightMemAdapter`/`source/` 均完整可读；全程
0 次真实 API 调用，只读 third_party、本框架源码与 MemoryData 只读参考目录。
