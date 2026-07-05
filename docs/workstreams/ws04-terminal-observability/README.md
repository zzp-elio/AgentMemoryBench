---
id: ws04
parent: null
status: open
created: 2026-07-05
---
# ws04 终端体验与第三方输出治理

## 目标

解决两类只影响终端体验、不影响 artifact 正确性的问题：isolated worker 长时间
无中间进度，以及第三方 method 的 stdout/warning/tqdm 插入 Rich 进度区。
完成判据：并行 prediction 期间终端能看到各 worker 的 conversation/阶段级心跳；
第三方输出可靠落入 `logs/run.log`/events 且有终端显示开关。

## 当前断点

- 2026-07-05：未开工。历史现象与已修部分见
  `../../archive/status/2026-07-04-task-ledger.md` P1 两条（isolated 进度、
  stdout 治理）。开工前由架构师写 spec。

## 任务清单

- [ ] isolated worker 上报 heartbeat / 阶段事件（当前 conversation、阶段、
  已处理 turn/question 数），协调层渲染；不必给每个 worker 单独进度条。
- [ ] 框架级 stdout 约束：第三方 `print()` / warning / tqdm 路由到
  `logs/run.log`/events，提供是否在终端显示的开关；不得全局压掉用户自定义
  method 的调试输出。
- [ ] Rich cosmetic 残留复验：elapsed 停走、child run 进度交错等，修复后在
  真实并行 smoke 中验证。

## 决策记录

- 2026-06 已确认：这些问题不影响 artifact 正确性，优先级低于主线；
  但不能宣布终端体验完成。
