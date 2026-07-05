# Agent Memory Benchmark Survey

本目录记录 Phase S 的 benchmark landscape survey。目标不是复述论文摘要，而是判断每个
benchmark 对框架协议、dataset loader、evaluation runner 和 method adapter 的真实要求。

每个 benchmark 调研必须优先回答：

```text
如果一个全新的 memory method 想在这个 benchmark 上测评，
它最少必须实现什么输入/输出能力？
```

## 调研顺序

1. 论文 PDF：确认 benchmark 目标、任务定义、metric 和实验设置。
2. 官方仓库：确认真实评测脚本、prompt、scorer、preprocessing 和 baseline 接入方式。
3. 本地 dataset：抽样真实字段，区分 method public input 和 scorer private labels。
4. 接口判断：判断当前 `BaseMemoryProvider.add(conversation) + retrieve(question)` 是否足够。
5. 框架影响：记录需要新增的 task family、metric profile、loader 能力或公开 API。

## 单个 Benchmark 卡片字段

每个 benchmark 文档统一使用中文为主，重点写 evaluation 怎么使用 dataset，不复述数据
生成过程。推荐结构：

1. 一句话结论：这个 benchmark 属于哪类 task family，对当前接口有什么冲击。
2. Dataset 数据结构：只介绍 evaluation 会用到的字段，明确 public input 和 private labels。
3. Evaluation 流程：method 看到什么、输出什么、answer prompt 如何构造、scorer 如何运行。
4. Metric 计算方式：主指标、分类指标、聚合方式、是否可 artifact-only 复算。
5. Answer LLM / Judge LLM 配置和 Prompt：官方是否提供 prompt、默认模型、temperature、
   max tokens、top-k 等运行参数。
6. Method Adapter 接口需求：最小接口、可选接口、是否需要 update/delete/forget/write_memory、
   multimodal、environment action 或 preference-only 特殊能力。
7. 未确认项：论文、代码、dataset 不一致或尚未核验的地方。

原则：Dataset 结构和 Evaluation 流程要写得足够细；数据生成字段、prompt 生成过程和论文
背景只在影响 evaluation 时记录。

## 已完成调研卡片

| Benchmark | 调研卡片 | 当前判断 |
| --- | --- | --- |
| BEAM | `docs/benchmark-survey/BEAM.md` | conversation probing-QA，可暂归入 conversation-QA，但需要 rubric judge 和 event-ordering metric。 |
| MemoryAgentBench | `docs/benchmark-survey/MemoryAgentBench.md` | chunk-stream memory construction + multi-task QA/evaluation，提示 loader/runner 需要支持顺序 chunk ingest 和更多 metric family。 |
| MemoryBench | `docs/benchmark-survey/MemoryBench.md` | feedback-driven continual learning / memory adaptation；完整接入需要 train-memory construction、static corpus injection、stepwise/on-policy runner 和多 evaluator。 |
| HaluMem | `docs/benchmark-survey/HaluMem.md` | uuid/user 级连续会话 + operation-level memory hallucination diagnosis；完整接入需要 Add Dialogue、Get Dialogue Memory、Retrieve Memory 三类能力。 |
| MemBench | `docs/benchmark-survey/MemBench.md` | message-stream / conversation-stream + multiple-choice QA；可映射到 add+retrieve，但必须保留 tid 隔离和 retrieved source step id provenance。 |
| PersonaMem | `docs/benchmark-survey/PersonaMem.md` | persona-oriented multi-session long-context multiple-choice QA；官方主链路是 direct long-context LLM，memory-module 官方 profile 应按 `(benchmark_size, shared_context_id)` 隔离，并至少支持 OpenAI-style message 粒度的 incremental prefix ingest；persona_id-only 只能作为非官方 stress profile。 |
| MemoryArena | `docs/benchmark-survey/MemoryArena.md` | multi-session agentic memory benchmark；不是 conversation-QA，核心是 Memory-Agent-Environment loop，完整接入需要 initialize / wrap_user_prompt / add(chunk) 或新的 agentic-memory-environment task family。 |

## Phase 1 锁定范围

2026-07-04 已敲定 Phase 1 不再继续扩大候选池，先围绕以下 5×10 目标矩阵做接入、
metric 覆盖和成本评估准备：

| 类型 | 范围 |
| --- | --- |
| Benchmark | LoCoMo、LongMemEval、HaluMem、BEAM、MemBench |
| 学术/论文型 Method | A-Mem、MemoryOS、MemOS、LightMem、SimpleMem |
| 工程/生产生态型 Method | Mem0、Letta/MemGPT、Cognee、LangMem、Supermemory |
| 明确排除 | Zep；Graphiti 也不作为替代，因为仍属于 Zep 体系 |

该范围是目标矩阵，不表示上述 benchmark / method 均已完成 adapter 或真实实验。
Supermemory 已纳入 Phase 1，但只评估 self-host/local OSS 版本；如果 local API 对某些
benchmark 的 provenance、session/update trace 或效率观测支持不足，需要记录为 gap，
再与用户讨论取舍。

## 汇报简报

| 文档 | 内容 |
| --- | --- |
| `docs/benchmark-survey/meeting-brief-5-benchmarks.md` | 面向汇报讨论的 7 benchmark 横向简报。文件名沿用早期 5-benchmark 命名，但标题和内容已更新为 BEAM、MemoryAgentBench、MemoryBench、HaluMem、MemBench、PersonaMem、MemoryArena。 |
