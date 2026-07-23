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

B1-B10 的实现、强反例、主树全量回归与 compileall 已关闭；B11 等待真实五格 smoke、
artifact/state/效率开箱与最终冻结。承重记录见
[`notes/simplemem-text-v2-implementation.md`](notes/simplemem-text-v2-implementation.md)。
