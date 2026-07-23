# A-Mem current-product 重认证

## 范围

本支线只认证官方通用产品仓库 `third_party/A-mem/` 的
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

B1-B10 的实现、强反例、主树全量回归与 compileall 已关闭；B11 等待真实五格 smoke、
artifact/state/效率开箱与最终冻结。承重记录见
[`notes/amem-official-product-r1-implementation.md`](notes/amem-official-product-r1-implementation.md)。
