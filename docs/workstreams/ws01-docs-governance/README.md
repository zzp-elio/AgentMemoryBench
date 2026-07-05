---
id: ws01
parent: null
status: done
created: 2026-07-05
---
# ws01 文档治理与任务树重构

## 目标

把扁平的 spec/plan/handoff 文档体系重构为 workstream 任务树，状态同步从四处收敛到
两处，AGENTS.md 瘦身为 ≤100 行静态入口，git 工作区收干净并恢复小步提交节奏。
完成判据见 [spec.md](spec.md) §8。

## 当前断点

- 2026-07-05：**ws01 终验通过（APPROVED），workstream 关闭**。审查记录：
  [notes/2026-07-05-final-review.md](notes/2026-07-05-final-review.md)。
  唯一遗留动作：13 个未推送 commit（ahead 13，含终验收尾）是否 push 由用户决定。
- 2026-07-05（已解除）：Codex 已完成 M3/T10 验收并提交：
  AGENTS.md 57 行，AGENTS.md + docs/README.md + docs/roadmap.md 合计 139 行；
  6 个 workstream README 链接和 3 个 archive/status 文件均已 `test -f` 通过；
  `uv run pytest -q` 为 `709 passed, 3 deselected, 2 warnings, 6 subtests passed`；
  T10 commit 后 `git status --short --branch` 为 `## main...origin/main [ahead 12]`。
  **下一步：请架构师按 [spec.md](spec.md) §8 做终验并在 notes/ 写审查记录；终验通过后由用户决定是否 push。**
- 2026-07-05（已解除）：M2（T7-T9）已由架构师审查通过（3 个 commit、归档数量 72/21/21/3、
  旧路径 grep 清零、709 passed）。M3/T10 内容已由 Claude 直接起草并落位到工作区：
  新 AGENTS.md（57 行）、docs/README.md、docs/roadmap.md、4 个 seed workstream
  README（ws02/ws04/ws05/ws06）、ws03 README、CLAUDE.md 路径与基线更新，
  旧 AGENTS/current-roadmap/task-ledger 已 git mv/cp 到 archive/status/。Codex 已完成
  plan T10/T11 可执行收尾。
- 2026-07-05（已解除）：Codex T7 预检发现 plan 迁移数量与仓库不符并停工。架构师
  复核裁定：差异源于 plan 初稿的 60/22/24 是架构师目测估数（失误），Codex 预检的
  72/21/23/3 正确，仓库本身无异常文件。plan T7 已勘误（含"迁移验收以实测数量为准"
  的通用原则），两份 ws03 留用 spec 已确认存在。**Codex 下一步：按勘误后的 T7 继续
  全量迁移，顺序执行到 T9。**
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
- [x] M1：git 收干净（Codex，T0.5-T6 共 7 commit，709 passed 基线保持）
- [x] M2：docs 目录迁移（Codex，T7-T9 共 3 commit + 文档规范测试路径更新，
  架构师审查通过）
- [x] M3 内容起草：新 AGENTS.md / docs/README.md / docs/roadmap.md /
  5 个 workstream 状态页 / CLAUDE.md 更新（Claude，2026-07-05）
- [x] M3 落位验收与提交（Codex，plan T10 验收清单，709 passed）
- [x] Claude 终验：spec §8 四条全部通过，审查记录见
  [notes/2026-07-05-final-review.md](notes/2026-07-05-final-review.md)
- [x] M4 派生：ws06-tests-restructure 状态页已建立（spec 另写）

## 子任务

- [ws06-tests-restructure](../ws06-tests-restructure/README.md) — open（M4，独立排期）

## 决策记录

- 2026-07-05 用户批准整体方案：workstream 任务树 + 状态两处同步 + AGENTS.md 瘦身。
- 2026-07-05 vendored methods 策略：新增 6 个（MemOS/SimpleMem/cognee/langmem/
  letta/supermemory）加 .gitignore，用 MANIFEST.md 锁 upstream + commit hash，
  配下载脚本；已跟踪的 4 个维持不动。
- 2026-07-05 task-ledger.md 与全部 handoffs：git mv 归档到 docs/archive/，
  状态裁定职能由各 workstream README 承接。
- 2026-07-05 协作模式：Claude Code = 架构师（spec/plan/审查），Codex = 执行者，
  OpenCode = 额度空档通道（角色不变）。
