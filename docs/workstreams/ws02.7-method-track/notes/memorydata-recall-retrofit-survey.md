# MemoryData 框架 Recall@k 改造模式调研（B5+ 判例库）

> 2026-07-13 用户指路：`第三方框架参考/MemoryData` 几乎为所有 method 实现了
> Recall@k，让架构师取证"它怎么改造各 method 支持 recall"。本 note 是一手取证
> 结果 + 对我们 B5+ 裁决的影响。所有行号锚指向
> `第三方框架参考/MemoryData/` 下文件（该目录是只读参考，不属于 third_party
> 纪律范围，但同样不改）。

## 1. 总体机制：血缘在 loader 侧标注，adapter 侧回收

- **loader 侧标注**：benchmark loader 切 chunk 时，把
  `[LOCOMO_META chunk_id=X source_ids=D1:3,D1:4]` header 直接拼进存储文本
  （`benchmark/locomo/loader.py:139-147` → `utils/locomo_utils.py:44-49`
  `build_locomo_storage_text`）。source_ids = 该 chunk 覆盖的官方 `dia_id`。
- **eval 侧计算**（`utils/eval_other_utils.py:802-869`）：
  `retrieved_source_id_groups` = 按检索排名的组列表（每组 = 该检索单元覆盖的
  source_ids）；`Recall@k = |前k组source_ids并集 ∩ gold evidence| / |gold|`，
  k ∈ {1,5,10} ∩ [≤retrieve_num]。严格集合覆盖，无部分分。与我们
  locomo-recall/longmemeval-recall evaluator 的口径同族。
- **resume 交互**：provenance 映射持久化为 sidecar 文件，旧 state 无 provenance
  时 **fail-fast 拒绝续跑**（`utils/agent.py:1004+`
  `_require_locomo_provenance_sidecar`）——值得我们抄的设计点。

## 2. 三条 adapter 侧回收策略（按 method 接口能力匹配）

| 策略 | 适用 method（MemoryData 内） | 机制 | 前提 | third_party 改动 |
|------|------|------|------|------|
| ① in-band 文本解析 | LightMem、A-Mem、SimpleMem | header 随存储文本入库；检索返回文本后正则解析（`utils/agent.py:902-916`） | method **原样保存文本**（verbatim/近 verbatim） | 零 |
| ② 原生 id 映射 sidecar | Mem0 | `add()` 返回 results 带 memory_id → adapter 维护 `memory_id→source_ids` 映射；`search()` 返回带 id → 查表（`utils/agent.py:3043-3149`）；查不到 id 时 fallback 到① | method add/search 均暴露条目 id | 零 |
| ③ 文本反查表 | MemoryOS | 存储时记 `normalized_text→source_ids`；检索返回原文（retrieval_queue[].user_input）反查（`utils/agent.py:2984-3042`） | method 检索**返回原样文本** | 零 |

策略②是最优雅的：**LLM 抽取改写不破坏映射**（键是 method 原生 id 不是文本）。
血缘语义 = "本次 add 产出的全部 entries 继承本次输入 chunk 的 source_ids"
（多对多传播，UPDATE/合并事件下有漂移，属已知近似）。

策略①的代价：header 进入存储文本 → **进 embedding 向量**（检索相似度轻微
污染）；进 answer prompt 前有 `strip_locomo_metadata` 清洗（answer 侧干净）。

## 3. 关键真相：LightMem 的 recall 是靠"绕过抽取管线"换来的

- 运行配置 `config/hybrid_lightmem.yaml`：**`lightmem_ingest_mode: direct`**。
- direct 模式（`methods/lightmem/lightmem_adapter.py:144-192`）：**不调
  `add_memory`**，adapter 直接手工构造
  `MemoryEntry(memory_class="verbatim_chunk", memory=原文+header)` →
  `offline_update([entry])`。预压缩/主题分段/LLM 抽取**整条管线被跳过**。
- pipeline 模式（真走 `add_memory(force_segment=True, force_extract=True)`，
  :157）**不附加任何 metadata** → 真实抽取管线下 MemoryData 同样没有
  provenance。他们没解决，也没改 LightMem 源码去解决。
- vendored 源码 diff 核实：他们的
  `methods/lightmem/source/lightmem/memory/utils.py` 与我们
  `third_party/methods/LightMem/src/lightmem/memory/utils.py` 的
  `convert_extraction_results_to_memory_entries` **同款**——上游本来就让抽取
  LLM 逐 fact 返回 `source_id`（batch 内 user 消息索引，
  `lightmem.py:342` 计算 max_source_ids），仅用于解析时间/说话人/topic，
  **构造 MemoryEntry 时丢弃**（utils.py:313-351，与我们 M0-3 结论一致）。
- 结论：MemoryData 的 LightMem 格测的是"qdrant embedding RAG + LightMem
  存储壳"，不是 LightMem 算法。**这条路我们不走**（等于放弃算法保真；
  我们框架的 LightMem 接入以真实抽取管线为准）。

## 4. 对我们 B5+ 裁决的影响（逐 method）

| method | MemoryData 判例 | 对我们的结论 |
|--------|------|------|
| Mem0 | 策略② | **可无损改造（adapter 层，零 third_party）**。我们 adapter 已在读 add 返回（end_session→SessionMemoryReport），补 `entry_id→source_ids` 映射即可让 provenance≠none。需配套：映射 sidecar 持久化 + 旧 run fail-fast（抄 §1 设计）。 |
| MemoryOS | 策略③ | **可无损改造**。get_answer 拆分流程已保留 retrieval_queue 原文，文本反查可行。 |
| A-Mem / SimpleMem | 策略① | **可无损改造**，但优先用我们框架自己的 items/provenance 通道（adapter 存储时能带 metadata 就带，不行才 in-band）；若用 in-band 须留痕 embedding 污染代价。 |
| LightMem | direct 绕管线（不可取） | 维持原判：真实管线下 **需 third_party 最小 diff**——上游抽取已产出 fact 级 `source_id`，只差 MemoryEntry 加可选字段 + `_create_memory_entry_from_fact` 透传两处（~5 行，不动算法）。MemoryData 宁可绕管线也没做这个，**佐证这是空白点 = 我们的差异化上游 PR 候选**。注意 source_id 是 batch 内索引，adapter 层需再做 batch 索引→全局 turn id 映射（adapter 知道每次 add_memory 喂了哪些 turn）。按 B5+ 流程：先在我们框架实验验证，再谈 PR。 |

## 5. 顺带发现（待核，不阻塞）

- 两边 vendored LightMem 存在版本分叉：**我们的副本多出 `bam_tags` 字段 +
  BoundMem(BAM) tag utils**（utils.py:32,158-160,755-966），MemoryData 的没有。
  需核我们 vendored 的是 pristine 上游还是带 BAM 扩展的版本/更晚 commit
  （影响"上游 PR"的基准分支选择）。
