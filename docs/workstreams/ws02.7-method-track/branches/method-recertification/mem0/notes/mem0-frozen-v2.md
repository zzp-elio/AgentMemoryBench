# Mem0 method-frozen-v2 验收记录

> 冻结日期：2026-07-20
>
> 真实 smoke 代码基线：main `8bb4808`
>
> smoke 后 model-inventory 真实性修复：`14b6c31`
>
> method source identity：
> `debda89ed60d9f104ab6fa65d6178d5f146b3216158f3dc2fdba2ee16a3ff08e`
>
> adapter：`conversation-qa-v3`
>
> 裁决：**B1-B11 current build 重认证完成，Mem0 冻结为 `method-frozen-v2`。**

## 1. 为什么另立 v2

`method-frozen-v1` 是 2026-07-14 的有效历史快照。之后 source-time 单次渲染、逐题
RetrievalEvidence、Gold Evidence Group、LoCoMo speaker/caption、role-native content、
MemBench generic readout、HaluMem update top-k 与 operation clean retry 都发生了实质变化，
adapter 也由 v2 升为 v3。旧 memory state 不可 resume，不能用 v1 的 13 格历史产物代证 current
build；因此以本轮五格 8 个真实 run 与重新开箱结果另立 v2。

## 2. B1-B11 最终判词

| 判据 | v2 判词 | 承重证据 |
|---|---|---|
| B1 产品接口/来源 | 通过 | vendored OSS `Memory.add/search`；package 2.0.4 + 146 文件 content hash |
| B2 注入粒度 | 通过 | LoCoMo/MemBench=turn，LongMemEval/HaluMem=session，BEAM=pair；singleton 合法，不造 placeholder |
| B3 隔离 | 通过 | W2 的 LoCoMo/LME/MemBench/BEAM 均为独立 worker state；worker 内按 `run_id` namespace 隔离 |
| B4 输入/时间/readout | 通过 | LoCoMo 显式 A/B role + speaker/caption；role-native 正文；effective source time 恰一次；MemBench place/time 原文保留、缺时不补 |
| B5/B5+ provenance | 通过（含诚实 N/A/pending） | LoCoMo/MemBench valid-turn；LME valid-session；BEAM N/A；stable ranking pending |
| B6 flush/finalize | 通过 | `Memory.add()` 同步建库，无 conversation 尾部 buffer；HaluMem 每 session 返回本次 add 的 report |
| B7 效率 | 通过 | build/embedding/retrieval/framework answer 与全部付费 judge observation/model inventory 落盘；registered inventory R1 删除不可达 legacy reader |
| B8/B8+ | 通过 | timeout/retry、失败原子 stage、默认 skip、显式 retry 前 clean namespace，partial operation artifacts 不落盘 |
| B9 build identity | 通过（效果阶段有声明缺口） | 当前 smoke 固定 MiniLM-384、Qdrant cosine、`gpt-4o-mini`，manifest/source hash 可审计 |
| B10 TOML/builder | 通过（作者校准延后） | 当前主 section/track identity 诚实；`author_<benchmark>` 完整 builder 在首个作者校准前迁移 |
| B11 smoke+冻结 | 通过 | 五 benchmark、8 个真实 run、适用 metric、judge、state、并行与 artifact 机器门全部关闭 |

N/A 是 metric 资格结论，不是 method 接入失败；smoke 分数也不作为效果优劣结论。

## 3. current-v3 真实 run roster

| benchmark | 真实 run |
|---|---|
| LoCoMo | `mem0-locomo-v3-r3q1-w1`；`mem0-locomo-v3-r3q1-c2-w2` |
| LongMemEval | `mem0-lme-v3-r1q1-w1-s-cleaned`；`mem0-lme-v3-r1q1-c2-w2-s-cleaned` |
| MemBench `0_10k` | `mem0-membench-v3-r1q1-ps1-w2-0-10k` |
| BEAM | `mem0-beam-v3-pair-r1q1-c2-w2-100k`；`mem0-beam-v3-pair-r1q1-w1-10m` |
| HaluMem | `mem0-halumem-v3-r1-w1-medium` |

LongMemEval 的 `--rounds 1` 在 current registered smoke 中每 instance 只保留首个 2-turn
session，不是完整 haystack。上述 run 只认证 cropped smoke 的接线、身份与 artifact，不外推
full、效果、成本或真实 resume。

## 4. 开箱验货结果

统一机器门修正 HaluMem operation-level answer artifact 的负空间契约后，8 个 run 全部 PASS：

```text
LoCoMo: W1=1 question, W2=2 questions, evidence=valid/turn
LongMemEval: W1=1 question, W2=2 questions, evidence=valid/session
MemBench: 4 sources / 4 questions / W2, evidence=valid/turn
BEAM: 100K W2 + 10M W1, evidence=n_a/none
HaluMem: 1 conversation / 4 sessions / 1 QA, evidence=valid/session
```

进一步逐 artifact 验收确认：

- 所有标准 run checkpoint 均为 `Completed`，terminal logs 无 traceback、API error、timeout 或
  rate-limit；HaluMem operation artifacts 全部落盘。
- 12 个实际 state root 的 Qdrant point 数与 provenance sidecar memory 数逐根相等；W2 worker
  state 物理分立，namespace 总数与 conversation 数相等。
- LoCoMo Recall=1.0；LongMemEval Recall=0、rank=`null/pending`；MemBench choice/source=0.5、
  Recall=1/6；BEAM Recall=`null/n_a`；这些都是小样本接线结果，不作效果结论。
- HaluMem session reports 为前三段 0 条、s4 3 条；7 个 update probe 均只读同一 conversation
  namespace。细分 summary 完整：extraction 108 个评测单元、update 7、QA 1，且
  Event/Persona/Relationship 与 QA category breakdown 均存在。
- judge observation 精确为 LoCoMo `1+2`、LongMemEval `1+2`、BEAM `2+1`、HaluMem
  extraction/update/QA=`8+7+1`；scope 均能回指真实 question/session/evaluator unit。
- public question/prediction/answer-prompt artifacts 不含 gold answer、gold evidence、answer
  session id、memory point 等私有字段。

首次机器门的 `KeyError: retrieval_query_top_k` 是验货器错误：普通 prediction answer artifact
必须有公共查询深度 10；HaluMem operation-level answer artifact 没有这一字段，**缺席**才是
真实契约。模板已改成按 runner 类型断言，既有付费 run 无需重跑。

## 5. 为什么没有把每个 variant × worker 数跑成笛卡尔积

这是有意的最小覆盖，不是漏项：

- MemBench W2 同时覆盖 four-source canonical shape、turn ingest 与 isolated-worker 路径；其
  worker 内仍逐 conversation 串行执行同一 ingest→retrieve→answer 核心。非隔离 W1 + turn
  ingest 已由 LoCoMo W1 实证，代码不存在 MemBench 专属 W1 分支，所以不再付费复制一格。
- BEAM 100K W2 认证标准 pair + isolated workers；10M W1 同时认证不同 source loader/shape、
  pair 与非隔离路径。runner 不按 variant 分叉，因此再跑 100K W1、10M W2 只会复制已覆盖的
  两个轴。10M 两处 dangling/content mismatch 由 deterministic production-event tests 承重，
  不靠付费首样本碰运气。
- HaluMem operation runner 依官方交错评测契约固定 W1，不允许为“齐格”强开并行。

## 6. model inventory R1 的重跑边界

真实开箱发现旧 `model_inventory.prediction.json` 多声明了 `mem0-answer-llm`，但 8 个 run 的
actual observations 中该 id 出现次数严格为 0；registered v3 的 answer 始终由 framework
`gpt-4o-mini` 记录。`14b6c31` 只从 registry 预声明清单删除该不可达 legacy reader，不改
message、memory、retrieve、answer、score 或任何调用，因此以真实 observation + 144 项定向回归
关闭，不重烧付费 smoke。最终主树全量为 `1638 passed, 3 deselected, 2 warnings, 29 subtests
passed in 174.94s`，`compileall exit 0`。旧 artifact 保留原样作为历史；新 run 会写收紧后的
inventory。

## 7. 冻结后保留的声明缺口

1. stable ranking 尚未审计，LongMemEval NDCG/rank 继续 pending；官方 k=30/50 也超出当前公共
   query depth 10。
2. BEAM pair lineage 不能证明单-message gold，Recall 保持 N/A；HaluMem 官方没有 turn qrel，
   retrieval Recall/NDCG 不强算。
3. product-default OpenAI embedding、`official_full` 效果参数、稀疏 author builder、full cost
   pilot 与真实 resume 属正式实验阶段；若切 embedding，必须全量重建并局部重开 B8+/B11。
4. vendored source 没有可追 upstream commit，继续以 content hash 锁定；5×10 完成后再做最新
   upstream drift 对比，不改写本轮身份。
5. Mem0 官方 0.1 relevance threshold、首次模型下载预热与 MiniLM 512-token 截断风险继续按
   product/effect 阶段声明，不把空检索误报成框架故障。
6. HaluMem 只认证 Medium fixed W1，不外推 Long 或 operation-level 多 worker。

## 8. 失效触发器与最终裁决

以下任一变化时按影响面局部解冻：vendored/method source hash、adapter/public protocol、
message role/time/caption/granularity、namespace/clean retry、readout/provenance/ranking、benchmark
canonical mapping、RetrievalEvidence/Gold Evidence Group 或 evaluator 公式。纯 artifact-only 新
答案指标可消费既有 prediction，不反向解冻 memory build。

Mem0 current Phase 1 smoke build 正式冻结为 **`method-frozen-v2`**。下一家按既定顺序转入
MemoryOS；效果阶段缺口继续保留，但不阻塞 5×10 smoke 主线。
