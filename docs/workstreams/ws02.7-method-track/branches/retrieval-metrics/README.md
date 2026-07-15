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
   首轮已由 Opus 4.8 完成于 `5fd5ac1`；架构师在数据齐备条件下独立整套复跑
   `297 passed, 1 warning in 12.35s`。主体保留，但 runtime 会接受未知 evidence status，
   首轮尚未合入。
4. [`M0 R1`](cards/actor-prompt-retrieval-evidence-contract-m0-r1.md) **待用户派回同一
   worktree**：只补 status 枚举 fail-fast 与强反例，follow-up 不 amend。
5. R1 强验收并线性合入 M0 后再写/派 M1：迁五个 evaluator、修 LongMemEval no-target
   分母和 k coverage。

## 权威材料

- 架构裁决：[`retrieval-metric-eligibility-ruling.md`](notes/retrieval-metric-eligibility-ruling.md)
- 框架审计：[`retrieval-metric-eligibility-audit.md`](notes/retrieval-metric-eligibility-audit.md)
- Mem0 mutation/provenance 审计：[`mem0-provenance-validity-audit.md`](notes/mem0-provenance-validity-audit.md)
- 对应历史卡位于 [`cards/`](cards/)。
