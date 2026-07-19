# Artifact-level evaluator 可观测性支线

> 状态：**CODE_ACCEPTED / REAL_ARTIFACT_REFILL_PENDING**。Opus 4.8 actor `b41aa97`
> 已由架构师强验收并线性合入主树 `174bd46`；共享代码缺口关闭，既有 BEAM 两组 run
> 仍须重跑 2+1 个 rubric evaluator 单元以生成历史缺失的 metric-side artifacts。完成后
> 再启动 HaluMem Medium W1。

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
2. 代码卡已按 full diff、fake-API 定向测试、注册/生产链补充门、全量回归与 compileall
   强验收：`79 passed` + `113 passed` + `1605 passed, 3 deselected, 2 warnings,
   29 subtests passed`，compileall exit 0。
3. 修复合入前不得启动 LightMem × HaluMem 真实 B11 的代码门已关闭；仍按串行顺序先补
   BEAM 历史 artifact，再启动 HaluMem，避免两批付费结果同时在途。
4. BEAM **不重跑 predict/Recall/build**；只在既有两个 run 上重跑共 3 道已批准的
   rubric judge，以补 evaluator efficiency artifact。HaluMem 再按固定 Medium smoke 首次执行。

## 验收判词

- runner-internal `efficiency_observations` 在启用 collector 时为必填强类型字段；缺失、类型错误
  或元素错误 fail-fast，写盘前从 payload 剥离，不进入 score/summary。
- BEAM 的 rubric 与 event-ordering equivalence 均走同一计量外壳；官方 messages 不改写，
  每次真实 Responses 调用恰记录一次。
- HaluMem extraction/update/qa 的 observation 分别按真实 session evaluator unit、真实 update
  point、真实公开 QA 归属；被官方路由跳过的空 retrieval 不造调用或 observation。
- 未声明 support 的离线 artifact evaluator 不创建空 model inventory/observation 文件。
- 第一次全量门仅因隔离 worktree 缺 gitignored SimpleMem 目录出现 3 个环境失败；复制资产到
  worktree 内部后这 3 条与全量门均通过。外部 symlink 被路径逃逸保护拒绝是预期安全行为。

## 非目标

- 不把 judge 调用数当效果或预算估算；真实成本仍只读实际 observations。
- 不把 artifact-level evaluator 改造成 method × benchmark 专用 runner。
- 不趁机并行化 HaluMem evaluator、改 aggregation、重写 prompt 或增加 metric。
- 不要求 benchmark builder 的 `metadata` 复制 `retrieval_evidence` 等公共契约字段。
