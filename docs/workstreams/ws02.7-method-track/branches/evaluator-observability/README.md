# Artifact-level evaluator 可观测性支线

## 范围

本支线只修共享 `artifact-only evaluation runner` 对 API evaluator 的效率观测契约，不改
benchmark 公式、prompt、method adapter、prediction artifact 或既有分数。

2026-07-19 LightMem × BEAM current-v7 B11 开箱时发现：`beam-rubric-judge` 已真实调用
judge 并正确落分，但只有 prediction 侧 model inventory / efficiency observations；该 metric
自己的 evaluator efficiency artifacts 完全缺失。源码闭环确认根因不是 BEAM 或 LightMem：

1. 普通逐题 evaluator 路径会创建 `EfficiencyCollector`、建立 `judge_scope`、写 evaluator
   model inventory 与 observations；
2. 带 `evaluate_run_artifacts()` 的路径在 `_run_artifact_level_evaluation()` 中直接调用 evaluator
   并写 score/summary，跳过上述全部步骤；
3. BEAM rubric judge 与 HaluMem extraction/update/qa 都继承
   `supports_efficiency_observability=True`，因此共享受影响；离线 artifact evaluator 不受影响。

## 稳定顺序

1. 当前事实与修复边界已由架构师写入
   [`actor-prompt-artifact-judge-efficiency-r1.md`](cards/actor-prompt-artifact-judge-efficiency-r1.md)。
2. 代码卡回卡后由架构师 full diff、fake-API 定向测试与共享 runner 回归强验收。
3. 修复合入前，不启动 LightMem × HaluMem 真实 B11；否则三个 judge 会出分但不留下成本观测。
4. 修复合入后，BEAM **不重跑 predict/Recall**；只在既有两个 run 上重跑共 3 道已批准的
   rubric judge，以补 evaluator efficiency artifact。HaluMem 再按固定 Medium smoke 首次执行。

## 非目标

- 不把 judge 调用数当效果或预算估算；真实成本仍只读实际 observations。
- 不把 artifact-level evaluator 改造成 method × benchmark 专用 runner。
- 不趁机并行化 HaluMem evaluator、改 aggregation、重写 prompt 或增加 metric。
- 不要求 benchmark builder 的 `metadata` 复制 `retrieval_evidence` 等公共契约字段。
