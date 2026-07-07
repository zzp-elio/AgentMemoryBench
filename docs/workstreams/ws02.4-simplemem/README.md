---
id: ws02.4
parent: ws02
status: in-review
created: 2026-07-07
---
# ws02.4 SimpleMem Adapter（Track C 第一个新 method）

## 目标

按协议 v3 原生接入 SimpleMem（text backend，turn 粒度 + finalize 钩子），
打通 SimpleMem × LoCoMo/LongMemEval 两格 fake 全链路。完成判据见
[spec-and-plan.md](spec-and-plan.md) T5/T6 验收。

## 当前断点

- 2026-07-07（Codex）：SimpleMem PLAN T1-T6 已完成并逐 task commit。当前实现
  接入 SimpleMem text backend 原生 v3 provider：turn 级 `ingest()`、conversation
  末尾 `finalize()`、绕开 `ask()` 的 retrieve-first 路径、failed_ingest clean retry
  和 LLM usage observation 均有 focused 测试覆盖；LoCoMo / LongMemEval registered
  fake smoke 均通过。验收基线：`uv run pytest -q` 为 **810 passed, 3 deselected,
  2 warnings, 6 subtests passed**；`uv run python -m compileall -q
  src/memory_benchmark tests` 通过。下一步交架构师复跑验收；真实 API smoke 需
  用户确认预算、规模和 run_id。

- 2026-07-07：**用户已批准 + Qwen3-Embedding-0.6B 已下载到 models/**。
  Codex 队列第②项解锁，按 PLAN 部分 T1-T6 施工。

## 任务清单

- [x] 架构师起草 spec+plan 合订本（2026-07-07）
- [x] 用户批准 + 下载 Qwen3-Embedding-0.6B 本地模型（2026-07-07）
- [x] Codex 施工 T1-T6
- [ ] 架构师验收
- [ ] 极小真实 smoke（待用户确认预算）

## 决策记录

- 2026-07-07 架构师裁定（spec S1）：text backend、gpt-4o-mini 覆盖、
  官方窗口参数不动、provenance=none 不做 sidecar。
