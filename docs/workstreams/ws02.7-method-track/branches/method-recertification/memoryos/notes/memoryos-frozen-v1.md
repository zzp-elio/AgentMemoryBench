# MemoryOS method-frozen-v1 验收记录

> 冻结日期：2026-07-20
>
> 真实 smoke 代码/命令基线：main `3262f68`
>
> method source identity：
> `2270871a42753e6f1cf0b26ac075d25ae7cc86300a822ed13d6a45149a4b5928`
>
> adapter：`conversation-qa-v2-shared-lifecycle`
>
> 裁决：**B1-B11 current product build 重认证完成，MemoryOS 冻结为
> `method-frozen-v1`。**

## 1. 冻结对象

主轨继续运行 vendored `memoryos-pypi` 产品 core，通过 framework wrapper 拆出纯
`ingest → retrieve → framework answer` 流程。LoCoMo `eval/` 只是一手角色映射与作者
readout 证据；`memoryos-chromadb` 会改变检索、合并与持久化语义，仍是独立 reproduction
variant，不在本冻结身份内。

本次冻结覆盖 shared-lifecycle R1-R5 后的 current source：单侧 page 不丢、双空拒绝、source
time 不伪造、page occurrence 精确 lineage、STM/MTM 共享 readout、完整 HaluMem update product
view，以及 extraction N/A 向 composite memory type 的清洁传播。完整实现史见
[`memoryos-shared-r1-implementation.md`](memoryos-shared-r1-implementation.md)。

## 2. B1-B11 最终判词

| 判据 | v1 判词 | 承重证据 |
|---|---|---|
| B1 产品接口/来源 | 通过 | `memoryos-pypi.Memoryos.add_memory` + 拆出的产品全层 retrieve；source hash 与 manifest 一致 |
| B2 注入粒度 | 通过 | LoCoMo/MemBench/HaluMem/BEAM=session，LongMemEval=pair；产品原生存储单元为 QA page，单侧用空字符串结构占位但不造事实 |
| B3 隔离 | 通过 | 每 conversation 独立物理 state；LoCoMo/LME/MemBench/BEAM 的真实 W2 worker 目录互不共享 |
| B4 输入/时间/readout | 通过 | LoCoMo speaker map、共享 caption wrapper、typed source time、MemBench 原文 place/time 与全产品层 readout 均经真实 artifact/state 验收 |
| B5/B5+ provenance | 通过（含诚实 N/A/pending） | page metadata 保存 occurrence-exact turn ids；五格逐题 `valid/turn`；stable ranking 仍 pending；benchmark-policy 可独立把无 gold 题判 N/A |
| B6 flush/finalize | 通过 | retrieve 可直接读取 STM 与已迁移 MTM；不需要 conversation 末额外 flush |
| B7 效率 | 通过 | build/embedding/retrieval/framework answer 与全部付费 judge observation/model inventory 落盘；不可达调用不伪造 observation |
| B8/B8+ | 通过（有声明缺口） | 保留官方 heat/N_visit 检索副作用，禁止 eval 问答回写；timeout/retry/clean-retry 与降级审计均有离线门 |
| B9 build identity | 通过 | `gpt-4o-mini` + MiniLM-384/L2/FAISS-IP 写入 manifest；本地模型 revision 如实 unpinned |
| B10 TOML/builder | 通过（作者校准延后） | current smoke identity truthful；`author_locomo` 完整 builder 与旧 config-track 迁移在首个作者校准/full 前完成 |
| B11 smoke+冻结 | 通过 | 五 benchmark、8 个真实 run、适用 evaluator、judge、state、并行、效率与统一机器门全部关闭 |

N/A 是 task/metric 资格结论，不是 method 接入失败；smoke 得分也不作效果优劣结论。

## 3. 真实 run roster

| benchmark | 真实 run |
|---|---|
| LoCoMo | `memoryos-locomo-v2sl-r3q1-w1`；`memoryos-locomo-v2sl-r3q1-c2-w2` |
| LongMemEval | `memoryos-lme-v2sl-r1q1-w1-s-cleaned`；`memoryos-lme-v2sl-r1q1-c2-w2-s-cleaned` |
| MemBench `0_10k` | `memoryos-membench-v2sl-r1q1-ps1-w2-0-10k` |
| BEAM | `memoryos-beam-v2sl-r1q1-c2-w2-100k`；`memoryos-beam-v2sl-r1q1-w1-10m` |
| HaluMem | `memoryos-halumem-v2sl-r1-w1-medium` |

这些 run 认证 cropped smoke 的接线、真实 API、artifact、state 与并行边界，不外推 full、效果、
成本或真实 resume。

## 4. 开箱验货结果

修正 BEAM abstention 的机器门口径后，既有 8 个 run 无需重烧 API，统一门全部 PASS：

```text
LoCoMo: W1=1 question, W2=2 questions, evidence=valid/turn
LongMemEval: W1=1 question, W2=2 questions, evidence=valid/turn
MemBench: 4 sources / 4 questions / W2, evidence=valid/turn
BEAM: 100K W2 + 10M W1, evidence=valid/turn；首题均为 abstention，Recall=N/A
HaluMem: 1 conversation / 4 sessions / 1 QA, evidence=valid/turn
PASS MemoryOS current-v2 shared-lifecycle five-grid B11 machine gate
```

逐层开箱确认：

- 7 个普通 prediction checkpoint 与 HaluMem operation conversation status 全部 completed；terminal
  logs 无 traceback、API error、timeout、rate-limit 或半写失败。
- 14 个 conversation state/sidecar 与 worker 拓扑精确对应，合计 26 个 STM page；每个 page 至少
  一侧非空且携带公开 source turn ids。W2 run 均为两个物理 worker state。
- LoCoMo caption、具名 speaker readout、空侧 page；MemBench ThirdAgent user-only page 与 typed
  timestamp；HaluMem 四段 session state 均由机器门直接读取生产 state 验证。
- LoCoMo Recall=1、judge=1；LongMemEval Recall=0、rank=`null/pending`；MemBench
  choice/source=0.5、Recall=1/6。这些仅是极小样本的诚实输出。
- BEAM provider artifact 为 `valid/turn`，但 100K 两题与 10M 一题都是官方 abstention，private
  gold group 为空；因此 `beam_recall` 正确聚合为 `null/n_a`，scored=0、abstention=2/1、无
  unmatched/ambiguous id。rubric judge 均正常出分。原机器门错误地要求数值 Recall，修正的是
  验货器，不是 production 或历史 artifact。
- HaluMem `JUDGE_CALL_PREVIEW extraction=0 update=7 qa=1 total=8` 与真实 observation 一致；四个
  session extraction report 均为明确 N/A，update 7 个单元中 1 个命中，QA 1/1；composite
  memory type 因 extraction N/A 正确为 `null/n_a`，没有把缺失伪装成 0 分。
- public question/prediction/prompt 未发现 gold answer、gold evidence、answer-session id 或
  memory point 私有字段泄漏。

## 5. 为什么不补烧 BEAM 非 abstention smoke

100K/10M 的每个首选 conversation 前两题均为 abstention，第 3 题才出现非空 gold group。为拿到
一个数值 Recall 必须把同一 conversation 的前三题都重新回答与 judge，超出本次已授权的
1-question smoke。现有真实 run 已证明 product retrieve、`valid/turn` evidence、artifact 与 rubric
judge；非空 group 的 Recall 公式和 provider lineage 已由确定性端到端强反例承重，full run 会自然
覆盖。故不为“让 summary 变成数字”额外付费。

## 6. 冻结后保留的声明缺口

1. 当前 smoke 每个 conversation 都低于 STM capacity=10，真实 API run 没有触发 STM→MTM
   updater；单侧 page 跨 capacity 迁移由 real-vendored hermetic 强反例承重，不能写成付费 smoke
   已覆盖。
2. stable ranking 尚未审计，LongMemEval rank/NDCG 保持 pending；公共 query depth 10 也不能
   冒充官方 k=30/50。
3. HaluMem extraction 与依赖它的 composite memory type 对本产品接口为 N/A；update 与 QA
   分别可测。只认证 Medium fixed W1，不外推 Long 或多 worker。
4. BEAM 本轮首题是官方 abstention，所以真实 smoke 没有数值 Recall；这不改变 MemoryOS
   `valid/turn` 能力声明。
5. product/effect 参数、embedding revision pin、`author_locomo` 完整 builder、full cost pilot 与
   真实 resume 属正式实验阶段；若切 build 参数或实现 variant，必须重建 state 并局部重开 B8+/B11。
6. ChromaDB reproduction variant 不继承本冻结结论。

## 7. 失效触发器与最终裁决

以下任一变化时按影响面局部解冻：method/source hash、adapter/public protocol、page role/time/
caption/speaker/granularity、STM→MTM lifecycle、product readout、provenance/ranking、benchmark
canonical mapping、RetrievalEvidence/Gold Evidence Group 或 evaluator 公式。纯 artifact-only 新答案
指标可消费既有 prediction，不反向解冻 memory build；需要新 retrieval depth/identity 的指标则局部
重开 B5/B11。

MemoryOS current Phase 1 smoke build 正式冻结为 **`method-frozen-v1`**。下一家按既定顺序进入
A-Mem；效果阶段缺口继续留档，但不阻塞 5×10 smoke 主线。
