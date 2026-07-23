# SimpleMem text-product 重认证

## 范围

本支线认证 `third_party/methods/SimpleMem` 的 text product：
`SimpleMemSystem.add_dialogue/finalize` 与 `hybrid_retriever.retrieve`。最终回答仍由 framework
reader 完成，不调用产品 `ask/answer_generator`。

## 当前身份

- 上游：`https://github.com/aiming-lab/SimpleMem.git`
- 上游 commit：`60a48e83a7fef10d386e1f438589047d3a4257bc`
- license：MIT
- adapter：`simplemem-text-v2`
- ingest：turn（speaker/content/timestamp）
- provenance：none（产品合成记忆无 exact source-membership）
- HaluMem：session 边界 finalize，并上报本段新生成的 MemoryEntry

## 当前状态

B1-B11 已关闭，current text product build 于 2026-07-23 冻结为
`method-frozen-v1`。承重记录：

- [`notes/simplemem-text-v2-implementation.md`](notes/simplemem-text-v2-implementation.md)
- [`notes/simplemem-frozen-v1.md`](notes/simplemem-frozen-v1.md)

构建显式逐窗口串行，保留 overlap 与 `previous_entries` 顺序依赖；检索阶段保留官方
multi-query parallelism。SimpleMem 合成 memory 无 exact source membership，因此
Recall/Precision/NDCG=N/A，stable ranking=pending。
