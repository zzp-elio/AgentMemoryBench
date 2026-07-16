# ws02.7 活跃支线索引

这里只收纳已经形成独立依赖链的活跃支线。一次性小修仍记在 ws02.7 README；既有历史
卡不为目录整洁而批量搬迁。

| 支线 | 解决的问题 | 稳定依赖入口 |
|---|---|---|
| [`lightmem-lifecycle`](lightmem-lifecycle/README.md) | 论文 online soft 与 offline consolidation 的术语、主 profile、provenance 边界 | lifecycle profile 是 retrieval M0 的前置门 |
| [`membench-time-semantics`](membench-time-semantics/README.md) | 100k message/question 时间隔离、LightMem preserve-none、Mem0 effective-time 渲染 | Phase A+B 已验收；Mem0×MemBench/BEAM/HaluMem B4 Phase C 待施工/局部复证 |
| [`retrieval-metrics`](retrieval-metrics/README.md) | 逐题 RetrievalEvidence、Recall/NDCG 资格、LongMemEval depth/分母 | M0 已验收 → evaluator M1 待架构师起草 |
| [`dual-track-identity`](dual-track-identity/README.md) | 通用产品/eval 实现身份、product-default build 轴、partial-native、MemoryOS 存储变体 | 主轨/controlled 身份已裁 → 三家 docs-only 查精确默认与迁移/复证面 |

每条支线用自身 README 记录范围、文档索引和稳定依赖顺序，`cards/` 放可整份复制给
actor 的卡，`notes/` 放一手审计、架构裁决与施工记录。**权威当前动作、commit/test
快照仍只写 ws02.7 README**，不在这里复制。
