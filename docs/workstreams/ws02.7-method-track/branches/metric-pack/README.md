# 通用 Metric Pack 支线

## 目的

把“公式是否可复用”和“某 benchmark 是否适用”拆开：公式内核不得读取 benchmark/method
身份，benchmark 壳层只保留 gold view、官方排除与 task eligibility。新增 answer metric 只读取
已有 prediction/private-label artifact，不要求 method 重跑。

## 当前事实与依赖

1. RetrievalEvidence M1 与 Gold Evidence Group v1 已关闭；不能在本支线重改资格协议、gold
   schema、LongMemEval 419 分母或 query depth。
2. Recall 不是完全未抽象：`evaluators/gold_evidence_groups.py::group_recall_score()` 已是共享
   group any-of 公式，`evaluators/retrieval_evidence.py` 已统一逐题资格与 artifact 校验。
3. 仍可收敛的是 top-k source-id 投影、纯 Recall@k 结果与重复聚合骨架；LoCoMo/LME/MemBench/
   BEAM 的 gold unit、empty-gold、abstention/no-target 与 tier 差异不得统一掉。
4. Answer Metric Pack M0 首批只新增 normalized EM 与 directional gold-in-prediction substring EM；
   两者与通用 token-F1 共用一个版本化 normalizer。BLEU/ROUGE-L 暂不实现，Precision/F1@k 等
   relevance 穷尽性审计。
5. 通用 token-F1 当前 registry 误覆盖 BEAM；M0 只收窄启用面到短答案 QA，不删除公式组件。

## 依赖顺序

当前唯一施工卡：
[`actor-prompt-metric-kernels-m0.md`](cards/actor-prompt-metric-kernels-m0.md)。

该卡可以在独立 worktree 与 LightMem × LoCoMo 真实 smoke 并行，因为 smoke 使用主树、卡内
零真实 API且不改 method/runner/benchmark adapter。actor 回卡后仍须架构师 full diff、定向与
全量回归；验收前不得拿新 metric 名执行主树 evaluate。

权威当前动作、commit/test 快照继续只写父级 `../../README.md`。
