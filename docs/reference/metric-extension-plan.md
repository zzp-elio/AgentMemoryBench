# 指标扩展计划（超越各 benchmark 原生指标）

> 2026-07-13 用户提出（提升框架核心竞争力：如 LoCoMo 原生 F1 之外加 BLEU、LLM
> judge）；架构师定方法论。**原则先行：语义匹配才加，胡乱加指标是负资产。**

## 1. 分层纪律（先于一切实现，防"数字污染"）

框架已有 `metric_tier` 机制（score artifact 实测字段，如
`framework_auxiliary`）。扩展指标全部落进分层，报告**永不混层**：

| tier | 含义 | 例 |
|---|---|---|
| `official_parity` | 官方指标逐字/逐公式对齐，可与论文数字对比 | longmemeval-judge、membench-choice-accuracy、halumem 12 项 |
| `framework_supplementary` | 我们加的、语义匹配的扩展指标，**不**与论文比 | f1-on-longmemeval（已有先例） |
| `framework_auxiliary` | 衍生/参考口径 | locomo-judge（lightmem 衍生） |

## 2. 两步走：先盘点、后匹配（用户直觉正确）

**第一步 盘点（actor 卡，离线取证）**：三个池子各列一张表——
① 框架已注册 evaluator 面（`evaluators/registry.py` 一手）；
② 五 benchmark 官方指标面（五份 frozen-v1 note 已核证，含"官方死代码不接"名单）；
③ 通用候选池：normalized EM / directional substring EM / token-F1 / BLEU / ROUGE-L /
  LLM-judge（binary + rubric）/ recall@k / precision@k / retrieval-F1@k / NDCG@k /
  abstention 口径 / parse_failed 率。

**第二步 匹配（架构师裁决矩阵）**：按 benchmark 的**答案形态**过滤：

| 答案形态 | 语义匹配的扩展 | 明确不默认加 |
|---|---|---|
| 短语/事实 QA（locomo、longmemeval、halumem-QA） | normalized EM、明确方向的 gold-in-prediction substring EM、token-F1、LLM-judge | BLEU/ROUGE-L 对短答案不稳定且与 F1 高度冗余，除非另有任务级论证 |
| 单字母 MCQ（membench） | parse_failed 率（已有） | BLEU/ROUGE/F1（对单字母无意义，已有断言锁 f1 排除） |
| rubric 长答案/序列任务（beam） | 官方 rubric judge 与 event-ordering 结构指标 | EM；gold 若只是 rubric 而非 canonical reference，BLEU/ROUGE-L 也 N/A |
| 真正摘要任务（未来或经审计确认的 task） | ROUGE-L 可作 lexical coverage 辅助；仍需语义 judge/事实性 guardrail | 不能因为输出“较长”就把 rubric QA 当摘要 |
| 检索面（逐 method × benchmark 过资格门） | recall@k；gold relevance 穷尽时才加 precision@k/F1@k；另有 semantic provenance、稳定顺序与足够 depth 才可 NDCG@k | provenance 不可得、gold 非穷尽、列表无序或 depth 不足时对应指标 N/A |

**可复用的正确层次**：复用 normalization、计数、聚合、artifact I/O 和 judge engine；prompt/
rubric/适用性仍按 benchmark/task profile 注册。不能为了“通用”做一个跨任务万能 judge prompt。
同一 prediction artifact 只生成一次答案，全部答案级指标消费同一文本；禁止因某个 metric
改 answer `max_tokens` 后再把不同 prediction 混成一组。

### 2.1 “通用”不等于“全 benchmark 启用”（2026-07-17 追加裁决）

- **公式内核通用**：normalized EM、directional substring EM、token-F1、Recall@k 等公式
  不得在实现函数内部读取 benchmark 名或 method 名；同一公式只保留一个版本化实现。
- **资格/数据映射仍须分层**：benchmark 壳层只负责选择 evaluator-private gold view、处理官方
  abstention/no-target/empty-gold 政策，以及声明该任务是否适用；registry 负责启用面。公式可复用
  不代表 BEAM rubric、MemBench MCQ 等任务必须启用它。
- **Recall 当前是“部分去耦”，不是从零开始**：`gold_evidence_groups.py` 已有共享
  `group_recall_score()`，RetrievalEvidence M1 也统一了资格门。剩余重复是 top-k source-id
  提取、纯计分结果和通用聚合骨架；后续 M0 只收敛这些真实公共部分。LoCoMo 空 evidence=1、
  LongMemEval 419 分母/排除、MemBench/BEAM empty-gold N/A 与各自 gold unit 继续留在壳层，
  禁止为了少几个文件而抹平。
- **已关闭勘误**：registry 曾让通用 `f1` 覆盖 BEAM，与本节 rubric 任务匹配裁决冲突；Answer
  Metric Pack M0 已把启用面收窄到 HaluMem/LoCoMo/LongMemEval，同时保留 `F1Evaluator`
  作为纯公式组件的可复用性。

## 3. 硬约束

1. **加法实现**：新指标=新 evaluator 注册，零改动已冻结面（frozen-v1 条款）。
2. **artifact-only**：全部从既有 prediction artifact 计算，不新增 method 侧要求
   （recall 类除外——那走 B5/B5+ 能力评估，不属本计划）。
3. **每个扩展指标登记**：动机 + 语义匹配论证 + tier + 与官方指标的差异声明，
   写进对应 benchmark 的 `integration/<b>.md`。
4. LoCoMo 特别注意：官方 BLEU-1 属于非 QA 任务面（frozen note §5 已裁"不接入"）
   ——若加 BLEU 是**我们的 supplementary 决定**，不得声称官方口径。
5. **资格先于计算**：每个 method × benchmark × metric 都要得到
   `valid / N/A / pending` 与 reason，但不手填笛卡尔积白名单。provider 逐题陈述
   semantic provenance / stable ranking 事实，evaluator 用通用要求导出 metric 资格。
   transformation-input lineage 不等于 semantic evidence provenance；Recall 可评也不
   自动推出 NDCG 可评，后者另需保序和 depth。
6. **Precision/F1 需要穷尽 relevance gold**：Recall 只问已标 evidence 是否被找回，允许
   gold 是一组“足够支持答案”的证据；Precision 会把未标注但实际相关的 item 当假阳性。
   未证明 annotation 穷尽时，precision@k 与 retrieval-F1@k 必须 N/A，不能从 Recall@k
   机械派生。
7. **LoCoMo `max_tokens=32` 保持 canonical**：它是 benchmark 官方 answer 配置；F1、EM、
   BLEU/ROUGE（若未来批准）与 LLM judge 都消费同一份 32-token prediction。judge 自己的输出
   budget 是独立调用参数；若发现 answer 截断，另建带新 run identity 的 ablation，不按 metric
   暗改 answer 配置。

## 4. 冻结语义：benchmark core 与 metric-pack 分层

- `benchmark frozen-v1` 锁 data/canonical mapping/privacy/prompt/官方 metric parity，不因新增
  artifact-only supplementary evaluator 整体解冻。
- 扩展指标进入独立 `metric-pack` 版本；新增/修正 evaluator 时只重开 metric surface，并记录
  tier、公式、适用 task 与 artifact schema。
- 既有 prediction 已含所需公开字段时离线复算，不重跑 method；LLM judge 可复用 prediction，
  但会新增付费 evaluate 调用，仍需用户批准预算。
- 若新 retrieval metric 需要更深 top-k、stable ranking 或新 provenance，重开受影响 method ×
  benchmark 的 B5/B11 与 prediction profile，而不是重开 benchmark data/prompt。改变 top-k 后
  formatted_memory/answer 也可能变化，必须使用新 run identity。
- 只有指标要求新增/改写 gold 映射、改变 benchmark prompt/data，才重开 benchmark 对应 A 项。

## 5. 排期

- 盘点卡：可立即派（docs-only，与 method 深耕线零冲突）。
- 匹配矩阵：盘点回来后架构师裁决、更新本文 §2 为定稿。
- 实现：RetrievalEvidence M1 与 answer-metric pack M0 均已关闭。M0 已合入 normalized EM、
  directional substring EM、共享 retrieval kernel，并收窄 BEAM 的 token-F1 误注册；主树验收
  `1524 passed, 3 deselected, 2 warnings, 29 subtests passed`。BLEU/ROUGE-L 不因库已存在就自动
  排入；Precision@k/retrieval-F1@k 仍须先完成五 benchmark relevance 穷尽性审计。后续排期由
  活跃 workstream README 指针消费，本文不单独充当“待办墓地”。
