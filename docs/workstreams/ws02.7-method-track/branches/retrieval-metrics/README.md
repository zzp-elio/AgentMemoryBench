# Retrieval metrics 资格支线

## 目的

让 provider 逐题陈述“这次检索是否有可审 semantic provenance、排名是否可信”，再由
evaluator 按 Recall/NDCG 各自要求导出 `valid / n_a / pending`。这样不能算的格子不会被
硬算成 0 或 1，也不维护会漂移的 method × benchmark × metric 人工白名单。

## 依赖顺序

权威当前动作看父级 `../../README.md`，本节只定义稳定先后关系：

1. 两份 docs-only audit 与架构裁决已合入。
2. LightMem lifecycle profile 卡已于主线 `825132f` 强验收合入，原依赖关闭。
3. [`actor-prompt-retrieval-evidence-contract-m0.md`](cards/actor-prompt-retrieval-evidence-contract-m0.md)
   + [`M0 R1`](cards/actor-prompt-retrieval-evidence-contract-m0-r1.md) 已强验收：actor
   `5fd5ac1` + `1999f56` 合入主线为 `352ed3c` + `6b4fd4e`；架构师 hardening=
   `afd4040`（不可哈希 status）+ `c879343`（registered preflight/resume 身份对称）。
4. M0 最终门：七文件 `307 passed, 1 warning`；主树
   `1235 passed, 3 deselected, 2 warnings, 4 subtests passed`；compileall exit 0。
5. Gold v1 已先关闭 LongMemEval no-target 分母=419，MemBench canonical split 也已以
   `ce1a9a8` + `d852fff` + `68b674b` 关闭。
6. **M1 已强验收关闭**：
   [`actor-prompt-retrieval-evidence-m1.md`](cards/actor-prompt-retrieval-evidence-m1.md)。
   Sonnet 5 首轮 `b6c4b32` 合入主线 `5d8fce3`；架构师 R1 卡=
   [`actor-prompt-retrieval-evidence-m1-r1.md`](cards/actor-prompt-retrieval-evidence-m1-r1.md)，
   实现重建合入 `e10110f`。五个 evaluator 现逐题消费 v1，保留 n_a/pending reason，
   benchmark 排除不污染 provider counts；当前 depth=10 只覆盖 LongMemEval k≤10，未二次
   retrieve、未重改 419/group/canonical。最终全量 1486 passed，compileall exit 0。
7. M1 的逐题公式/资格契约仍然关闭；stable ranking method 审计或 query depth 扩展须另立裁决，
   不借本批发散。LightMem × LongMemEval v6 真实 B11 暴露的**聚合展示契约**已由 Sonnet 5
   `8a81723` 强验收并以主线 `68bb7f9` 关闭：五 evaluator 统一
   `retrieval-summary-v2`，`total_questions` 计全部 score row、零数值样本的 `mean_score=null`，
   runner 区分 key 缺失与显式 null。架构师用真实 v6 W1/W2 零 API 重评得到 total=1/2、
   mean 均为 null；未重开公式、gold group、LME 419、top-k 或 provider evidence。
8. **Precision/F1@k M2 已排期、尚未施工**：Gold Evidence Group v1 的有限官方 qrel 足以实现
   `relevance_scope=annotated_gold_groups` 的通用内核，不再用“未证明全语义穷尽”阻塞代码存在；
   但 score 解释必须披露 annotation scope。正式启用前还要裁 method-native item 与
   canonical-source-normalized 两种粒度、multi-child item、dedup、返回不足 k 的分母及 LoCoMo
   malformed/empty/unmatched evidence。该批只消费已有 ordered retrieved items + private gold +
   RetrievalEvidence v1；不改 M1 资格顺序，不为旧 artifact 补猜。

## 权威材料

- 架构裁决：[`retrieval-metric-eligibility-ruling.md`](notes/retrieval-metric-eligibility-ruling.md)
- 框架审计：[`retrieval-metric-eligibility-audit.md`](notes/retrieval-metric-eligibility-audit.md)
- Mem0 mutation/provenance 审计：[`mem0-provenance-validity-audit.md`](notes/mem0-provenance-validity-audit.md)
- 对应历史卡位于 [`cards/`](cards/)。
