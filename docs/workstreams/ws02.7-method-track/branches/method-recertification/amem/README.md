# A-Mem current-product 重认证

## 范围

本支线只认证官方通用产品仓库 `third_party/methods/A-mem-product/` 的
`AgenticMemorySystem.add_note/search_agentic`。论文 LoCoMo 复现仓库
`third_party/methods/A-mem/` 保留为作者实验参照，不再充当 Phase 1 主产品接口。

## 当前身份

- 上游：`https://github.com/agiresearch/A-mem.git`
- 上游 commit：`ceffb860f0712bbae97b184d440df62bc910ca8d`
- license：MIT
- adapter：`conversation-qa-v2-product`
- ingest：turn
- provenance：turn（官方 note id 到 canonical turn id 的 sidecar）
- HaluMem：每个 session 上报本段新建的官方 MemoryNote

## 当前状态

B1-B11 已关闭，current official product build 于 2026-07-23 冻结为
`method-frozen-v1`。承重记录：

- [`notes/amem-official-product-r1-implementation.md`](notes/amem-official-product-r1-implementation.md)
- [`notes/amem-frozen-v1.md`](notes/amem-frozen-v1.md)

Phase 1 不运行或报告 A-Mem provenance Recall@K/Precision@K/NDCG：产品检索命中的是
evolution 后的当前记忆，而不是原始 dataset turn。note id/sidecar 仍存在，但只证明生成
lineage，不能把当前记忆重新解释成原始 evidence。
