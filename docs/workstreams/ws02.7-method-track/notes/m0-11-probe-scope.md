# M0-11：update probe 与效率 observation scope

> 取证与修复日期：2026-07-14。范围仅限 collector 的 scope 容忍变体、五个 adapter
> 自记 retrieval 调用点及离线回归测试；未修改 runner 编排，未调用真实 API。

## 实锤链路

HaluMem operation-level runner 在每个 session 的 `conversation_scope` 内调用
`_ingest_and_probe_session`（`src/memory_benchmark/runners/operation_level.py:238-252`）。
该函数随后为 update memory point 调用 `provider.retrieve`，purpose 为
`memory_update_probe`，并把独立测得的耗时写入 `duration_ms`
（`src/memory_benchmark/runners/operation_level.py:364-380`）。因此 update probe
发生在 conversation scope，而不是 question scope；runner 的 scope 编排未改。

修复前，adapter 在 retrieve 完成后调用严格的 `record_retrieval_result`。该方法要求
question scope，并拒绝重复 retrieval 声明
（`src/memory_benchmark/observability/efficiency/collector.py:187-202`、
`src/memory_benchmark/observability/efficiency/collector.py:454-468`），故 update probe
会触发 `question efficiency requires a question scope`。

本次新增 `record_retrieval_result_if_question_scope`：question scope 委托原严格方法，
conversation/judge scope 静默 no-op；collector 关闭或无 scope 时继续沿用
`_active_state_or_none` 的原语义
（`src/memory_benchmark/observability/efficiency/collector.py:204-220`、
`src/memory_benchmark/observability/efficiency/collector.py:437-452`）。原
`record_retrieval_result` 与 `record_answer_generation` 均未改。

## 五处机械替换

只替换效率记录方法名，检索、计时与 token 统计表达式保持原样：

- LightMem：`src/memory_benchmark/methods/lightmem_adapter.py:845-851`
- A-Mem：`src/memory_benchmark/methods/amem_adapter.py:490-496`
- MemoryOS：`src/memory_benchmark/methods/memoryos_adapter.py:790-796`
- Mem0 answer-prompt 路径：`src/memory_benchmark/methods/mem0_adapter.py:902-909`
- Mem0 v3 retrieve 路径：`src/memory_benchmark/methods/mem0_adapter.py:981-988`

## 构建期探针的成本归属声明

update probe 期间，adapter 内部 embedding/LLM 调用仍显式包在
`operation_stage(EfficiencyStage.RETRIEVAL)` 中，例如 LightMem
`src/memory_benchmark/methods/lightmem_adapter.py:828-836`、A-Mem
`src/memory_benchmark/methods/amem_adapter.py:456-465`、MemoryOS
`src/memory_benchmark/methods/memoryos_adapter.py:775-783`、Mem0
`src/memory_benchmark/methods/mem0_adapter.py:882-889` 与
`src/memory_benchmark/methods/mem0_adapter.py:962-969`。显式 stage 优先于 scope
默认 stage（`src/memory_benchmark/observability/efficiency/collector.py:470-479`），
所以这些调用保留在 conversation scope 下、`stage=RETRIEVAL`，口径声明为
“构建期探针”；probe 总时延另由 `update_probe_records.duration_ms` 承载。此归属按
D3 口径接受，本卡不改代码。

## 离线回归覆盖

collector 单测覆盖 question 等价行为（含 observation id/逐字段一致）、重复声明拒绝、
conversation/judge no-op、无 scope fail-fast 与 disabled no-op
（`tests/test_efficiency_collector.py:39-118`）。operation-level 回归 stub 在每次
retrieve 后按 adapter 姿势自记效率（`tests/test_operation_level_runner.py:120-137`），
并真实走 update probe 与 QA 路径，断言两个 update probe 均完成且 question 记录仍为
两条（`tests/test_operation_level_runner.py:417-448`）。
