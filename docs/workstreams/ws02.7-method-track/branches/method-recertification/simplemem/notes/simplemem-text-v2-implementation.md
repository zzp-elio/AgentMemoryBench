# SimpleMem text v2 实现记录

> 状态：离线实现与回归门通过；真实 B11 待执行。

## 1. 产品算法与接口

Phase 1 直接调用 text product 的 `add_dialogue(speaker, content, timestamp)`、`finalize()` 与
`hybrid_retriever.retrieve(query)`；不调用产品答题器。产品 buffer 达到 window_size 后由 LLM
把一组 dialogue **重新合成为**若干 MemoryEntry（`memory_builder.py:132-215`），不是一条
turn 对应一条 memory。

## 2. 五格公开输入映射

- 每个 canonical turn 独立传入；speaker 直接取 LoCoMo speaker name，其他 benchmark 取
  canonical user/assistant。接口不要求交替，不需要 placeholder。
- content 原样保留并通过共享 helper 添加图片 caption；MemBench 原 place/time 尾注不删。
- typed timestamp 严格按 `turn_time → 当前 session_time → None`。adapter 支持 ISO、
  LongMemEval、BEAM、LoCoMo 与 MemBench 已审计格式；非空但未知格式 fail-fast，None 原样进入。
- formatted_memory 显式回带产品可取出的 timestamp/location/persons/entities/topic，不用
  `str(context)` 隐式塞入。

## 3. 指标资格裁决

MemoryEntry 是语义融合结果，产品没有 output-to-source-membership；仅知道哪些 dialogue
进入过生成 prompt，不能证明最终条目仍承载每个 source fact。因此
`provenance=none`，LoCoMo/LongMemEval/MemBench/BEAM 的 Recall/NDCG 一律诚实 N/A。

hybrid retriever 会并行执行多条生成查询，用 `as_completed()` 收结果，再与 keyword/structured
结果去重（`hybrid_retriever.py:559-641`）；没有跨通道统一 score 或全局 rerank。当前列表能供
answer reader 使用，但不能宣称稳定排名，故 `stable_ranking=pending`，不是 valid。

## 4. HaluMem session extraction

HaluMem 每个 session 结束时调用产品 `finalize()`，把尚未满 40 条的当前 buffer 合成为产品
MemoryEntry；adapter 只上报本 session 新增的 entry id。为避免产品的
`previous_entries` 把上一 session 的生成结果带进下一 session extraction prompt，session
报告后只清空该 extraction-context 缓存；LanceDB 中的既有长期记忆不删除，update/QA 仍能检索
完整 conversation 历史。该边界不改生成算法，只把 benchmark 的真实 session 边界映射到产品
已有 finalize 入口。

## 5. transport、隔离与 build identity

- 每 conversation 独占 state dir、LanceDB 与 product system，W2 无共享写状态。
- 产品 OpenAI client 强制使用项目 endpoint/timeout、SDK retry=0；产品自己的显式 retry loop
  以 `api_max_retries + 1` 次总尝试实现“首次 + N 次重试”的框架语义。
- embedding observer 包装真实 `EmbeddingModel.encode`，不是估算伪调用。
- 当前主 profile 固定项目 controlled MiniLM：`models/all-MiniLM-L6-v2`、384 维、模型内部 L2
  normalize、LanceDB L2。SimpleMem 官方默认 Qwen3 embedding 属产品/效果阶段差异，不能把
  当前 smoke 冒充 paper/product-default parity；manifest 写
  `controlled_embedding_v1/local_unpinned`。

## 6. 离线验收

与 A-Mem 共用同一批回归门：最终主树
`1679 passed, 3 deselected, 1 warning, 29 subtests passed in 130.50s`，compileall exit 0，
`git diff --check` clean。强反例覆盖五种时间格式、未知格式、caption、speaker、None、
session delta、跨 session extraction context、provenance N/A、ranking pending、真实 embedding
observer、endpoint/timeout 与产品 retry 映射。
