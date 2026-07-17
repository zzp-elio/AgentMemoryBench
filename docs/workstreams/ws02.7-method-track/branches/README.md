# ws02.7 活跃支线索引

这里只收纳已经形成独立依赖链的活跃支线。一次性小修仍记在 ws02.7 README；既有历史
卡不为目录整洁而批量搬迁。

| 支线 | 解决的问题 | 稳定依赖入口 |
|---|---|---|
| [`lightmem-lifecycle`](lightmem-lifecycle/README.md) | 论文 online soft 与 offline consolidation 的术语、主 profile、provenance 边界 | lifecycle profile 是 retrieval M0 的前置门 |
| [`membench-time-semantics`](membench-time-semantics/README.md) | 100k message/question 时间隔离、LightMem preserve-none、Mem0 effective-time 渲染 | Phase A+B+C 离线验收；三格内容抽查并入后续五格主配置 B11 |
| [`retrieval-metrics`](retrieval-metrics/README.md) | 逐题 RetrievalEvidence、Recall/NDCG 资格、LongMemEval depth/分母 | M0/M1、gold/canonical 与 depth=10 披露均已关闭；stable ranking/depth 扩展另立裁决 |
| [`metric-pack`](metric-pack/README.md) | benchmark-agnostic metric kernel、normalized EM/substring EM、任务适用面 | RetrievalEvidence M1 已关闭；M0 卡待用户派发，可与付费 smoke 在隔离 worktree 并行 |
| [`dual-track-identity`](dual-track-identity/README.md) | 旧 config-track/TrackIdentity、通用产品/eval 实现身份与 MemoryOS reproduction variant | M0 R1/R2 已关闭；只解释历史身份，新配置看 TOML/builder 现行政策 |
| [`method-config-profiles`](method-config-profiles/README.md) | 一个 method TOML、主/作者 section、完整 answer builder 与旧 config-track 兼容迁移 | 已排期、尚未写卡；首个作者校准或真实效果 full run 前关闭 |
| [`input-role-semantics`](input-role-semantics/README.md) | canonical speaker role、benchmark gold evidence unit、Recall/NDCG 分母 | gold M0 + LightMem hybrid + MemBench split 均已关闭；交棒 retrieval M1 |
| [`method-recertification`](method-recertification/README.md) | 共享修复完成后按现行 commit 逐 method 重走 B1-B11，不靠历史 frozen 惯性 | LightMem 当前唯一 active method；先 gap matrix，后决定施工卡，严格串行 |

每条支线用自身 README 记录范围、文档索引和稳定依赖顺序，`cards/` 放可整份复制给
actor 的卡，`notes/` 放一手审计、架构裁决与施工记录。**权威当前动作、commit/test
快照仍只写 ws02.7 README**，不在这里复制。
