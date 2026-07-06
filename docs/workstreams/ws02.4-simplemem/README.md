---
id: ws02.4
parent: ws02
status: draft
created: 2026-07-07
---
# ws02.4 SimpleMem Adapter（Track C 第一个新 method）

## 目标

按协议 v3 原生接入 SimpleMem（text backend，turn 粒度 + finalize 钩子），
打通 SimpleMem × LoCoMo/LongMemEval 两格 fake 全链路。完成判据见
[spec-and-plan.md](spec-and-plan.md) T5/T6 验收。

## 当前断点

- 2026-07-07：spec+plan 合订本已起草（小型 method 接入先例），
  **等待用户批准**；批准后 Codex 按 PLAN 部分 T1-T6 施工。
  用户前置动作：下载 `Qwen/Qwen3-Embedding-0.6B` 到 `models/`（T1 会强校验）。

## 任务清单

- [x] 架构师起草 spec+plan 合订本（2026-07-07）
- [ ] 用户批准 + 下载 Qwen3-Embedding-0.6B 本地模型
- [ ] Codex 施工 T1-T6
- [ ] 架构师验收
- [ ] 极小真实 smoke（待用户确认预算）

## 决策记录

- 2026-07-07 架构师裁定（spec S1）：text backend、gpt-4o-mini 覆盖、
  官方窗口参数不动、provenance=none 不做 sidecar。
