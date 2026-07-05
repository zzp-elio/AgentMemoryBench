---
id: ws01
parent: null
status: in-progress
created: 2026-07-05
---
# ws01 文档治理与任务树重构

## 目标

把扁平的 spec/plan/handoff 文档体系重构为 workstream 任务树，状态同步从四处收敛到
两处，AGENTS.md 瘦身为 ≤100 行静态入口，git 工作区收干净并恢复小步提交节奏。
完成判据见 [spec.md](spec.md) §8。

## 当前断点

- 2026-07-05（已解除）：Codex 在 T0 发现 pytest 基线不绿并按纪律停工。架构师裁定：
  `test_membench_placeholder_directory_exists_and_is_empty` 把"MemBench 数据未收集"
  的临时状态固化成空目录断言，属测试过时；已由 Claude 修改为
  `test_membench_semantic_directory_exists`（仅断言目录存在），复跑全量回归
  `709 passed, 3 deselected, 2 warnings, 6 subtests passed`，正式基线更新为
  709 passed。**Codex 下一步：执行 plan T0.5 提交测试修复，然后从 T1 继续。**
- 2026-07-05：spec 已获用户批准；三项决策已拍板（见下方决策记录）。
  plan.md 已写好，等待 Codex 按 M1 → M2 顺序施工；M3 入口文档内容由
  Claude（架构师）起草。Codex 开工前先读 [plan.md](plan.md) 的"施工纪律"一节。

## 任务清单

- [x] 全库盘点与问题诊断（Claude，2026-07-05）
- [x] 写 spec 并获用户批准
- [x] 用户决策：vendored 用 manifest + 下载脚本；task-ledger/handoffs 全部归档
- [x] 写迁移 plan（M1/M2/M3 逐任务验收命令）
- [ ] M1：git 收干净（Codex 施工）
- [ ] M2：docs 目录迁移（Codex 施工）
- [ ] M3：AGENTS.md / docs/README.md / docs/roadmap.md 重写（Claude 起草，Codex 校验）
- [ ] Claude 审查验收：对照 spec §8 逐条核验，出具审查记录（notes/）
- [ ] M4 派生：tests 目录重组 → 建 ws06-tests-restructure（另写 spec）

## 子任务

- ws06-tests-restructure — 待建（M4，独立排期）

## 决策记录

- 2026-07-05 用户批准整体方案：workstream 任务树 + 状态两处同步 + AGENTS.md 瘦身。
- 2026-07-05 vendored methods 策略：新增 6 个（MemOS/SimpleMem/cognee/langmem/
  letta/supermemory）加 .gitignore，用 MANIFEST.md 锁 upstream + commit hash，
  配下载脚本；已跟踪的 4 个维持不动。
- 2026-07-05 task-ledger.md 与全部 handoffs：git mv 归档到 docs/archive/，
  状态裁定职能由各 workstream README 承接。
- 2026-07-05 协作模式：Claude Code = 架构师（spec/plan/审查），Codex = 执行者，
  OpenCode = 额度空档通道（角色不变）。
