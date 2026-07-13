# 注入记忆 token（injected_memory_context_tokens）双轨口径

> 2026-07-13 用户提问"unified 记 formatted_memory 就行,native 怎么办"后架构师
> 定口径 + 四个真实 smoke run 实证。效率指标无外部锚可校准,口径必须自己钉死。

## 1. 口径定义（两轨统一）

`injected_memory_context_tokens` = **实际注入 answer prompt 的记忆载荷 token 数**
（memory payload 本身），由各 adapter 在 retrieve 侧统计
（lightmem_adapter.py:728、memoryos_adapter.py:792、amem_adapter.py:492、
mem0_adapter.py:904/983；字段语义 `analysis/efficiency.py:70`）。

- **unified 轨**：载荷 = formatted_memory 实体内容。
- **native 轨**：载荷 = 同一份检索结果注入 prompt_messages 的记忆段。
  **模板开销（native prompt 的指令文字）不计入**——这保证跨轨、跨 method
  可比：比较记忆系统的"上下文占用"，不是比较谁的 prompt 模板长。
- 模板开销可推得：answer llm_call 的 `input_tokens`（api_usage）−
  `injected_memory_context_tokens` ≈ 模板+问题开销。
- **空记忆 → 0**：哨兵文本（如 "(No relevant memories found)"）不计入。

## 2. native 有效性条件（逐 method 审计项，进 B7）

口径在 native 轨成立的前提：**adapter 统计的载荷 ≡ prompt_messages 里实际
嵌入的记忆段**。每个 method 的每个 native prompt builder 接入时必须核一次
（builder 若对记忆做截断/改写/重排，统计必须跟着实际嵌入走）。

## 3. 实证锚（2026-07-13 四 smoke run）

| run | track | formatted_memory | injected_tokens |
|---|---|---|---|
| lm-locomo-unified-diag-log1 | unified | 227 字符 2 条记忆 | **68** |
| lm-locomo-native-smoke1 | native | 同一份 | **68**（模板不计入的直接证据） |
| lm-lme-unified-smoke1-s-cleaned | unified | 空（哨兵） | **0**（真实零：抽取 0 条） |
| lm-lme-native-smoke1-s-cleaned | native | 空（哨兵） | **0** |

lme 双轨同空是自洽的：native **build** 侧 profile 尚未实现（config-track 目前
只切 readout），两轨 build 同为 unified 配置（extract_threshold=0.5），1 round
任务型对话抽不出记忆点属合法行为（与 locomo 首跑空库同现象）。

## 4. 报告纪律

- 跨轨/跨 method 的"上下文效率"比较**只用本字段**，不得用 answer prompt
  总 token（模板开销污染）。
- 预算估算用 api_usage 总量（那是真实花费），两者用途不同勿混。
