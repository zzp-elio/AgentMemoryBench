# LightMem 效率指标保真审计（预算关键）

> 2026-07-12 架构师（Opus 4.8）一手核。触发：用户强调"效率指标审查很重要，
> 涉及给老师报告预算，预算不准确是大问题"。结论先行：**插桩完整、口径可信，
> 无缺口；风险在聚合层（两个 store 要合并），不在采集层。**

## 1. 成本驱动角色 × 是否插桩（一手核 `文件:行号`）

| 角色 | API 成本 | 是否采集 token+call | 出处 |
|------|:--:|:--:|------|
| build / 记忆构建（summary+extraction+update） | 大（readme Memory-Con ~1M tok/run） | ✅ | `lightmem_adapter.py:882-998` `_record_memory_manager_usage`→`collector.record_llm_call`（:958），token 来自 `extract_api_token_usage`（:934） |
| answer / QA | 大（readme QA ~4M tok/run） | ✅ | `lightmem_adapter.py:1300-1319` `_record_answer_llm_call`→`record_llm_call`（:1319） |
| retrieval | 小（本地向量） | ✅ latency+注入 token | `lightmem_adapter.py:714-732` `record_retrieval_result` |
| **judge** | 中（每问 1 call） | ✅ | `locomo_judge.py:123,173` / `longmemeval_judge.py:45,105` `_record_judge_llm_call`+`resolve_token_usage`；收进 evaluator-side collector（`evaluation.py:136-216`→`EfficiencyArtifactStore.for_evaluator`:211） |
| embedding | **0**（all-MiniLM 本地 huggingface） | N/A | readme locomo headline `--embedding-model-path .../all-MiniLM-L6-v2` |

**token 计量来源**：`resolve_token_usage` 优先真实 API `usage` 字段，缺失回退
tokenizer estimate（`token_measurement_source` 字段可审计哪条是估算）。→ 预算
优先用真实用量，可信。

## 2. 预算准确性的两个 gotcha（都在聚合层，非采集层）

1. **两个效率 store 必须合并**：prediction 阶段（build+answer+retrieval）走 adapter-side
   collector；**judge 走 evaluator-side 独立 store**（`EfficiencyArtifactStore.for_evaluator`）。
   **总成本 = prediction 效率产物 + evaluation 效率产物**；只读一个会**漏 judge 成本**。
   给老师的预算表必须显式 SUM 两个 store。
2. **双轨成本乘子跟 build/readout 二分走**（policy §2）：native 轨重跑
   answer（native 参数）+ judge（native judge）；build 是否重跑取决于 build 轴
   （embedding+超参）是否分叉。LightMem locomo：embedding 两轨同（all-MiniLM）→
   若超参也同，则 **成本 = build×1 +（answer+judge）×2**；若 native 超参 ≠ repo 默认
   → **全部 ×2**。M0.2 核 `add_locomo.py` 超参默认 vs paper (768,0.8) 定这个乘子。

## 3. token-source 混比要进预算表

真实 api_usage vs tokenizer_estimate 的占比要报（`token_measurement_source`）。
全真实 → 预算高置信；含估算 → 标注置信区间。gpt-4o-mini 经框架 OpenAI client
一般返回 usage → 预期高真实率，measure-first 首跑实测确认。

## 4. 对 M0-eff 卡的输入（审计后派）

采集层无需补插桩。M0-eff 只做**聚合层**：
- 写/核"总成本聚合器"：合并 prediction + evaluation 两个效率 store，按角色
  （build/answer/judge）+ token-source 拆分出 per-(method,benchmark,track) 成本行。
- 单价用 ohmygpt 实价离线换算（roadmap 全局约束），不绑 OpenAI 官价。
- 双轨乘子按 §2 规则套用（build/readout）。
- 输出即 5×10 预算估算表的单元格来源。
**这是纯离线聚合 + 换算，不碰采集层、不碰真实 API**，可并行于 M0-1b（改动文件
不重叠：M0-eff 动 observability 聚合/报表，M0-1b 动 reader/评测路径 wiring）。

## 5. 结论
效率采集对 LightMem **完整可信**，budget 不会因采集缺口而失真。唯一动作是聚合层
把两个 store 合并 + 套双轨乘子 + 报 token-source 混比。measure-first 首跑
（LightMem×LoCoMo unified）实测校验本审计。
