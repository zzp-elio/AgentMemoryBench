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
③ 通用候选池：EM / token-F1 / BLEU / ROUGE-L / LLM-judge（binary + rubric）/
  recall@k / NDCG@k / abstention 口径 / parse_failed 率。

**第二步 匹配（架构师裁决矩阵）**：按 benchmark 的**答案形态**过滤：

| 答案形态 | 语义匹配的扩展 | 明确不加 |
|---|---|---|
| 短语 QA（locomo、longmemeval、halumem-QA） | LLM-judge、EM、token-F1、（BLEU/ROUGE 弱匹配，标 auxiliary 且低优先） | — |
| 单字母 MCQ（membench） | parse_failed 率（已有） | BLEU/ROUGE/F1（对单字母无意义，已有断言锁 f1 排除） |
| rubric 长答案（beam） | ROUGE-L/BLEU 可作 auxiliary 参考 | EM |
| 检索面（逐 method × benchmark 过资格门） | recall@k；有 semantic provenance、稳定顺序与足够 evaluation depth 时才可 NDCG@k | 无损 provenance 不可得、列表无序或深度不足时 N/A，不强造 |

## 3. 硬约束

1. **加法实现**：新指标=新 evaluator 注册，零改动已冻结面（frozen-v1 条款）。
2. **artifact-only**：全部从既有 prediction artifact 计算，不新增 method 侧要求
   （recall 类除外——那走 B5/B5+ 能力评估，不属本计划）。
3. **每个扩展指标登记**：动机 + 语义匹配论证 + tier + 与官方指标的差异声明，
   写进对应 benchmark 的 `integration/<b>.md`。
4. LoCoMo 特别注意：官方 BLEU-1 属于非 QA 任务面（frozen note §5 已裁"不接入"）
   ——若加 BLEU 是**我们的 supplementary 决定**，不得声称官方口径。
5. **资格先于计算**：每个 method × benchmark × metric 独立声明
   `valid / N/A / pending` 与 reason。transformation-input lineage 不等于 semantic
   evidence provenance；Recall 可评也不自动推出 NDCG 可评，后者另需保序和 depth。

## 4. 排期

- 盘点卡：可立即派（docs-only，与 method 深耕线零冲突）。
- 匹配矩阵：盘点回来后架构师裁决、更新本文 §2 为定稿。
- 实现：本计划与单个 method 冻结状态没有技术依赖；但当前先完成 retrieval metric
  eligibility 契约审计、LightMem N/A artifact 门与 MemoryOS B11，避免用扩展指标制造
  “进度感”并抢占验收注意力。排期由活跃 workstream README 决定。
