---
id: ws05
parent: null
status: open
created: 2026-07-05
---
# ws05 全量实验申请材料与前置工程

## 目标

在 ws02 smoke 矩阵完成后，组装与导师讨论全量实验的完整申请材料，并在预算
获批前完成全量运行的兜底工程验证。完成判据：申请材料（成本估算表 + 现有
结果汇总 + 实验方案）可直接用于导师讨论；兜底验证清单全绿后才允许启动全量。

## 当前断点

- 2026-07-05：依赖 ws02 矩阵产出，暂不开工。本 workstream 从旧
  "experiment-reporting" 口径重构而来：成本估算不再是一次性报告任务，而是
  ws02 每个格子的标准产出；本 ws 负责"组装申请材料 + 全量前置工程"。

## 任务清单

### 申请材料（依赖 ws02）

- [ ] 全矩阵成本估算表：基于各格子 smoke/pilot 的 token/latency observation，
  按 ohmygpt 实价离线计算（`memory_benchmark.analysis`；严格区分
  api_usage / method_native / tokenizer_estimate）；给出分 benchmark、
  分 method 的全量费用与时间预估区间。
- [ ] 现有结果汇总：LoCoMo 4-method full（历史口径，注明将重跑）、
  LongMemEval 1-conv pilot judge 结果；区分历史 run 与新架构 run。
- [ ] 全量实验方案：规模选项（如 LongMemEval 5/10/500 conv 梯度）、
  分批 resume 策略、run_id 规划，供导师选择。

### 全量前置兜底工程（预算获批前完成验证）

- [ ] 失败恢复演练：模拟中断后同 run_id resume，不从零开始、不重复计费。
- [ ] 防 API 空烧复验：连续失败熔断（max_consecutive_failures）、
  failed conversation 默认隔离、`--retry-failed` clean state 在真实网络
  故障场景下的行为验证。
- [ ] 断网/限流韧性测试（timeout/retry 兜底已实现，未做真实故障注入）。

### 每周导师汇报支持（常态）

- [ ] 每周从 roadmap/workstream 状态生成进度简报素材（放 `reports/`）。

## 决策记录

- 2026-07-05 用户：先 smoke 矩阵攒成本表 → 导师批预算 → 才跑全量；
  全量前兜底机制必须做好，不能中途失败从零开始或 API 空烧。
- 既定：真实费用按 ohmygpt 实价离线算，不用 OpenAI 官方价做结论。
