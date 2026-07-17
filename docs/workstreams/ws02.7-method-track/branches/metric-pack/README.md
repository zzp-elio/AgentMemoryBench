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

首轮卡：
[`actor-prompt-metric-kernels-m0.md`](cards/actor-prompt-metric-kernels-m0.md)。Opus 4.8 已交付
`760f251`；架构师 full diff 与定向复跑确认 Recall/EM/registry 主体成立，但
`SubstringExactMatchEvaluator` 缺首卡明确要求的 `normalized_prediction` / `normalized_gold`
details 字段，故首轮尚未合入。

当前唯一施工卡是同 worktree 最小 follow-up：
[`actor-prompt-metric-kernels-m0-r1.md`](cards/actor-prompt-metric-kernels-m0-r1.md)。

R1 零真实 API且不改 method/runner/benchmark adapter。回卡后架构师补齐 gitignored benchmark/
method 资产运行全量回归；验收前不得拿新 metric 名执行主树 evaluate。LightMem 已冻结为 v2，
R1/新增离线评分不反向解冻 method build。

权威当前动作、commit/test 快照继续只写父级 `../../README.md`。
