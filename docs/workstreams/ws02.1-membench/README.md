---
id: ws02.1
parent: ws02
status: draft
created: 2026-07-07
---
# ws02.1 MemBench Adapter（Phase 1 第一个新 benchmark）

## 目标

按协议 v3 接入 MemBench（Phase 1 smoke 口径：multiple-choice accuracy 主指标、
trajectory 隔离、0-10k/100k 双 variant），完成 fake 全链路 + 极小真实 smoke，
为 5×10 矩阵打开第三列。完成判据见 [spec.md](spec.md) §7。

## 当前断点

- 2026-07-07：**spec 已获用户批准**（"非常完美"原话），实施 plan 已备
  （[plan.md](plan.md)，T1-T6，含本项目第一条 unified prompt 链路）。
  **Codex 可开工。**

## 任务清单

- [x] 架构师起草 spec（2026-07-07）
- [x] 用户批准 spec（2026-07-07）
- [x] 架构师写实施 plan（[plan.md](plan.md)）
- [ ] Codex 施工 + fake 全链路（T1-T6）
- [ ] 架构师验收
- [ ] 极小真实 smoke（待用户确认预算）

## 决策记录

- 沿用 ws02 已定案：INSTRUCTION_FIRST（决策点 B）、evidence recall 不强求
  （落盘 turn_id 口径但不算 metric）、根目录 20 条补充样本排除。
