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

- 2026-07-07：spec 已起草（[spec.md](spec.md)，status: draft），**等待用户批准**。
  批准后架构师拆实施 plan 交 Codex。这是 M-C 阶段第一个 benchmark，后续
  ws02.2-halumem、ws02.3-beam 按同模式推进。

## 任务清单

- [x] 架构师起草 spec（2026-07-07）
- [ ] 用户批准 spec
- [ ] 架构师写实施 plan（loader/adapter/evaluator/CLI 接线 + 验收命令）
- [ ] Codex 施工 + fake 全链路
- [ ] 架构师验收
- [ ] 极小真实 smoke（待用户确认预算）

## 决策记录

- 沿用 ws02 已定案：INSTRUCTION_FIRST（决策点 B）、evidence recall 不强求
  （落盘 turn_id 口径但不算 metric）、根目录 20 条补充样本排除。
