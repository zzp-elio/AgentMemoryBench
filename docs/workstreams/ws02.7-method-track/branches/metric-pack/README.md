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

## M0 验收状态

首轮卡 [`actor-prompt-metric-kernels-m0.md`](cards/actor-prompt-metric-kernels-m0.md) 与 R1
[`actor-prompt-metric-kernels-m0-r1.md`](cards/actor-prompt-metric-kernels-m0-r1.md) 已关闭。Opus 4.8
交付 `760f251` + `2f8a1e1`，架构师 full diff、R1 定向复跑 `44 passed in 2.33s` 后以主线
`3bc9019` + `54a360e` 合入；主树全量门=`1524 passed, 3 deselected, 2 warnings, 29 subtests
passed in 166.45s`，`src+tests` compileall exit 0。

M0 现提供版本化 answer-text-v1 normalized EM、directional gold-in-prediction substring EM，
并收敛共享 retrieval metric kernel；token-F1 已从 BEAM rubric 任务移除。R1 补齐两种 answer
metric 统一的 normalized artifact identity，没有改变公式或分数。

LightMem 两条既有 LoCoMo v6 run 已用新 evaluator 离线追加评分，零真实 API、零 method 重跑：
单 worker 与双 worker 的 normalized EM / substring EM 均为 0；逐题 details 证明是日期表达/顺序
不满足 lexical exact/contiguous-token 条件，不是 evaluator 接线失败。该补充分数不反向解冻
LightMem build。BLEU/ROUGE-L 与 Precision/F1@k 继续受任务匹配/穷尽 relevance 判据约束，不能
因 M0 关闭而自动实现。

权威当前动作、commit/test 快照继续只写父级 `../../README.md`。
