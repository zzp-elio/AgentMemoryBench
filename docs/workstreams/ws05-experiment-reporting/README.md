---
id: ws05
parent: null
status: open
created: 2026-07-05
---
# ws05 实验推进与成本/结果报告

## 目标

基于已有 efficiency observation 完成真实成本估算，汇总已完成 run 的指标，
并给出 full 实验矩阵的扩大方案。完成判据：ohmygpt 实价成本报告、
LoCoMo 结果汇总表落地；LongMemEval-S 扩大规模方案获用户确认。

## 当前断点

- 2026-07-05：未开工。可用证据已齐：LongMemEval-S 四 method 1-conv cost pilot
  （`outputs/{lightmem,mem0,memoryos,amem}-longmemeval-s-1conv-costpilot-20260622-s-cleaned/`，
  judge 均 1/1，可同 run_id resume）；LoCoMo 各 full/smoke run 的 F1、judge 与
  efficiency summary。历史 run 的可用性口径见
  `../../archive/status/2026-07-04-task-ledger.md`。

## 任务清单

- [ ] 基于 1-conv cost pilot 的 token/latency observation，按 ohmygpt 实际价格
  离线计算经费/时间估算报告；不得以 OpenAI 官方美元估算为最终结论
  （聚合工具：`memory_benchmark.analysis`）。
- [ ] 汇总 LoCoMo 已完成 run 的 F1、LLM judge、efficiency 表；区分历史 run 与
  retrieve-first/AnswerPromptResult 之后的 run（历史 run 口径见归档 task-ledger：
  如 A-Mem full-v2 无 efficiency、Mem0 full-v4 reference_date 旧口径）。
- [ ] 依据成本报告向用户提交 LongMemEval-S 扩大方案（建议先 5 或 10
  conversations / method，同 run_id resume，再决定是否 full 500）。
- [ ] 决策项：最终报告若要求最严谨 Mem0 LoCoMo prompt 复现，用新 run_id 重跑
  （reference_date 完整日期修复已于 2026-06-23 落地，旧 full-v4 不自动作废）。
- [ ] 复用 prediction artifact 计算 LoCoMo F1 的遗留补算项。
- [ ] 4 method × 2 benchmark 可选实验矩阵完成度审计（扩大规模后的稳定性、
  失败恢复与成本波动）。

## 决策记录

- 用户既定：任何真实 API run 需确认预算、规模、run_id；真实费用按实际服务商
  价格离线计算；`measurement_source`（api_usage / method_native /
  tokenizer_estimate）必须在成本估算中区分。
- 并行边界既定：只做单 method × 单 benchmark 内的 conversation 级并行；
  多组合实验开多个终端跑。
