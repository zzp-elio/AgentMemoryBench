# A-Mem 官方通用产品 R1 实现记录

> 状态：离线实现、真实 B11 与冻结门均通过；最终验收见
> [`amem-frozen-v1.md`](amem-frozen-v1.md)。

## 1. 为什么迁移产品源

旧 adapter 调用 `third_party/methods/A-mem/memory_layer_robust.py`，该仓库 README
明确是 LoCoMo 论文复现面。Phase 1 要比较各 method 的通用产品接口，因此改接官方通用
仓库 `third_party/A-mem/agentic_memory`。源码按上游 commit
`ceffb860f0712bbae97b184d440df62bc910ca8d` 原样 vendoring；嵌套 `.git` 不进入主仓，
避免形成没有 `.gitmodules` 的不可克隆 gitlink。

主接口是一手源码中的 `AgenticMemorySystem.add_note()` 与 `search_agentic()`：前者保留
一条 `MemoryNote` 的原始 content/timestamp，并在写入前执行链接/evolution；后者返回
Chroma 命中以及官方 link neighbor（`memory_system.py:233-264,509-588`）。不用
`ask/chat`，最终回答始终由 framework reader 完成。

## 2. 五格公开输入映射

- 每个 canonical turn 独立调用一次 `add_note`，不要求 user/assistant 配对或 placeholder。
- LoCoMo 把真实 speaker name 写入 content 前缀；其余 benchmark 写入结构化
  `user:`/`assistant:` 前缀。图片统一追加
  `[Sharing image that shows: {caption}]`，原 content 不删除。
- source time 严格按 `turn_time → 当前 session_time → None`；MemBench 尾注原文保留，
  同时把解析出的 turn time 送入 typed `time=` 参数。两者都缺时不借 question time、
  相邻 turn 或墙钟。
- 官方 `MemoryNote(timestamp=None)` 会填墙钟（`memory_system.py:74-77`）；adapter 在写入后
  立即经官方 `update(timestamp=None)` 恢复 source-time 缺失语义。内部 `last_accessed`
  仍是产品运行时字段，不冒充 source time，也不进入公开 provenance。

## 3. provenance 事实与检索指标资格

A-Mem 的 evolution 不是 LightMem 式文本合并：新 note 的 content 不被改写，旧 note 的
content/timestamp/id 也不变；`update_neighbor` 只改旧 note 的 tags/context
（`memory_system.py:676-718`）。但产品检索返回的是已 evolution 的当前 `MemoryNote`
对象，不是 dataset 原始 turn；links/context/tags 已成为其当前语义的一部分。

adapter 保存 `note_id → canonical_turn_id` sidecar，retrieve 按产品真实返回顺序构造
`RetrievedItem(source_turn_ids=(turn_id,))`，仅用于审计当前记忆的生成 lineage。lineage
只能证明原始 turn 参与过生成，不能证明当前 memory 仍等同或逐事实承载该 turn。因此
Phase 1 对 A-Mem 的 Recall@K、Precision@K、retrieval-F1@K 与 NDCG 一律判 N/A，不运行、
不报告。该裁决不删除 sidecar，也不把“指标 N/A”误写成“产品没有 note id”；sidecar 继续
服务 HaluMem session delta、隔离和状态一致性验货。

Chroma 返回值是 distance（数值越小越近），可以解释产品内部当前 memory 的检索顺序；
它不能修复 evidence unit 不同构的问题，也不能直接作跨 method headline。

## 4. HaluMem session extraction

每个 turn 都同步生成一个官方 MemoryNote；adapter 在 session 边界只上报本 session 新建
note 的公开 readout，不删除历史 note，也不伪造 summary。因此 extraction、update、QA 与
memory-type 四类 HaluMem evaluator 均有结构资格。最终是否通过由真实 operation smoke 的
session report、judge scope 和 state 开箱决定。

## 5. 隔离、持久化与假绿防线

- 每 conversation 独占 Chroma persistent directory 与 collection；官方构造器原本固定
  collection 名 `memories`，adapter 用 scoped retriever 包装。
- 官方每 100 次 evolution 的 `consolidate_memories()` 会重建全局 collection；adapter 只把
  重建位置改为当前 conversation 的 scoped retriever，不改变触发时刻、note 集合或顺序。
- pickle 保存官方 note 集合，JSON 保存 lineage；resume 重建 Chroma 时不调用 LLM。
- 官方 `analyze_content()` 任意异常会退化为固定
  `{keywords: [], context: "General", tags: []}`（`memory_system.py:204-231`），adapter 将其
  判为失败，禁止 API 失败后写一条假绿 note。
- 官方 `search_agentic()` 会吞异常并返回空列表（`:514-588`）；已有非空 memory store 时
  空结果不可能是合法 Chroma top-k，adapter fail-fast。
- OpenAI-compatible client 强制注入项目 endpoint、timeout 与 SDK retry；真实 LLM/embedding
  调用均走效率 collector。

## 6. build identity

当前 main profile 使用官方产品默认 `all-MiniLM-L6-v2`、384 维、Chroma cosine；本地模型
revision 未 pin，manifest 如实写 `local_unpinned`。A-Mem 的生成/evolution LLM 继续固定
`gpt-4o-mini`。作者 LoCoMo 复现参数/answer builder 不混入主 smoke。

## 7. 离线验收

- A-Mem/SimpleMem 与共享契约定向门：130 passed（中间逐批强反例另有 79/81/82 passed）。
- 第一轮全量发现且仅发现一条旧 fixture 仍期待 evidence contract 缺失；修正 fixture 后重跑：
  `1679 passed, 3 deselected, 1 warning, 29 subtests passed in 130.50s`。
- compileall：`src/memory_benchmark`、`tests`、官方 A-Mem product 与 SimpleMem text 路径，
  exit 0。
- `git diff --check`：clean。
- 真 Chroma 零 API 隔离/重建探针：
  `AMEM_SCOPED_CONSOLIDATION_PASSED before=(1, 1) after=(1, 1)`。

唯一 warning 是既有 vendored LightMem Pydantic v2 deprecation，与本批无关。

## 8. 真实 B11 收口

2026-07-23 在 main `526e978` 上完成 11 个正式真实 run：LoCoMo、LongMemEval、
MemBench 各 W1/W2，BEAM 100K/10M 各 W1/W2，HaluMem Medium 固定 W1。统一机器门
逐 run 复核 completed checkpoint、worker 物理 state、384 维 embedding identity、
pickle/lineage/hash、实际 LLM/embedding 调用数、适用 evaluator 与私有字段负空间。

HaluMem 真实产物为四个 session 各 2 条官方 note；update probe 7 个非空；judge
observation 精确为 extraction=113、update=7、QA=1，且 extraction/update/QA question
type 与 Event/Persona/Relationship memory type 细分均落盘。

按用户同日裁决，正式 roster 中没有运行或生成任何 A-Mem Recall/rank/NDCG 产物。
完整 run id、机器门与失效触发器见冻结记录。
