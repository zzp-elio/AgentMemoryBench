# A-Mem method-frozen-v1 验收记录

> 冻结日期：2026-07-23
>
> 真实 smoke 代码/命令基线：main `526e978`
>
> method source identity：
> `6ca55fc8780e4d2dff0c2a8cb11643e48c804831a010e9d8e3cc1805f855c024`
>
> adapter：`conversation-qa-v2-product`
>
> 裁决：**B1-B11 current official product 重认证完成，A-Mem 冻结为
> `method-frozen-v1`。**

## 1. 冻结对象

主轨使用官方通用产品仓库 `third_party/A-mem/` 的
`AgenticMemorySystem.add_note/search_agentic`，上游 commit
`ceffb860f0712bbae97b184d440df62bc910ca8d`。论文 LoCoMo 复现仓库
`third_party/methods/A-mem/` 仅保留为作者实验参照，不代表本冻结 build。

每个 canonical turn 独立生成一个官方 `MemoryNote`；LoCoMo 用真实 speaker name，
其余 benchmark 用 canonical role，图片走共享 caption wrapper，source time 严格
`turn → 当前 session → None`。检索使用产品 Chroma 与 linked-neighbor readout，
最终回答仍由 framework reader 生成。

## 2. B1-B11 最终判词

| 判据 | v1 判词 | 承重证据 |
|---|---|---|
| B1 产品接口/来源 | 通过 | 官方 general product、MIT、固定 upstream commit 与 source hash |
| B2 注入粒度 | 通过 | 五格均 turn；不强配 pair、不造 placeholder；speaker/role 独立表达 |
| B3 隔离 | 通过 | 每 conversation 独占 Chroma/state；W2 真实 worker state 物理分离 |
| B4 输入/时间/readout | 通过 | content/caption/place/source time 无损；readout 回带 content/time/context/keywords/tags |
| B5 provenance | 审计 lineage 通过；retrieval metric=N/A | 检索命中 evolution 后当前 memory，不是原始 turn；正式 run 不生成 Recall/Precision/rank/NDCG |
| B6 flush/finalize | 通过 | `add_note` 同步落 note/evolution，无待 flush buffer |
| B7 效率 | 通过 | build LLM、embedding、retrieval、answer 与 judge observation 全部落盘 |
| B8/B8+ | 通过 | 检索只读；官方 swallow-error 路径由 wrapper fail-fast；timeout/retry/clean retry 已锁 |
| B9 build identity | 通过 | `gpt-4o-mini` + product-default MiniLM-384/Chroma cosine；revision 如实 unpinned |
| B10 TOML/builder | 通过 | 跨五格固定主配置；作者 LoCoMo 复现配置不混入主表 |
| B11 smoke+冻结 | 通过 | 五 benchmark、11 个真实 run、全 worker/variant、适用 metric、state 与机器门关闭 |

sidecar 继续用于审计、HaluMem session delta、隔离与状态一致性；但 lineage 只证明原始
turn 参与过生成，不能证明 evolution 后当前 memory 仍等同或逐事实承载该 turn。因此这里是
明确的 retrieval metric **N/A**，不是为了主表好看而“政策性不展示”。

## 3. 真实 run roster

| benchmark | 正式真实 run |
|---|---|
| LoCoMo | `amem-locomo-v2p-r3q1-w1-r2`；`amem-locomo-v2p-r3q1-c2-w2` |
| LongMemEval | `amem-lme-v2p-r1q1-w1-s-cleaned`；`amem-lme-v2p-r1q1-c2-w2-s-cleaned` |
| MemBench `0_10k` | `amem-membench-v2p-r1q1-ps1-w1-0-10k`；`amem-membench-v2p-r1q1-ps1-w2-0-10k` |
| BEAM `100K` | `amem-beam-v2p-r1q1-w1-100k`；`amem-beam-v2p-r1q1-c2-w2-100k` |
| BEAM `10M` | `amem-beam-v2p-r1q1-w1-10m`；`amem-beam-v2p-r1q1-c2-w2-10m` |
| HaluMem Medium | `amem-halumem-v2p-r1-w1-medium` |

`amem-locomo-v2p-r1q1-w1-sentinel` 是发现 embedding dimension 声明缺口的修复前哨兵；
`amem-locomo-v2p-r3q1-w1` 在用户追加 Recall 政策裁决时被主动中止。两者均不属于冻结
roster，也不作为通过证据。

## 4. 统一机器门

```text
PASS LoCoMo: q=1/2, workers=1/2, states=1/2, build calls=11/22
PASS LongMemEval: q=1/2, workers=1/2, states=1/2, build calls=3/6
PASS MemBench: q=4/4, workers=1/2, states=4/4, build calls=12/12
PASS BEAM 100K: q=1/2, workers=1/2, states=1/2, build calls=3/6
PASS BEAM 10M: q=1/2, workers=1/2, states=1/2, build calls=3/6
PASS HaluMem: q=1, sessions=4, reports=4x2 notes, build calls=15
PASS A-Mem B11: 11 formal runs, state/lineage/384d identity valid,
  Recall/rank/NDCG artifacts absent by policy
```

逐层验货确认：

- 最终主树回归为
  `1680 passed, 3 deselected, 1 warning, 29 subtests passed in 150.75s`，
  compileall exit 0；唯一 warning 是既有 LightMem Pydantic deprecation。
- 所有 checkpoint 均 `completed + ingested`；W2 run 都存在
  `method_state/worker_0` 与 `worker_1`，W1 不伪造 worker 层。
- 每个 state manifest 的 adapter/source identity、文件 SHA-256、turn count 均与
  `memories.pkl` 和 `note_lineage.json` 对上；note id 集合一一相等，lineage 无重复。
- 每个 conversation 的 memory-build LLM 与 embedding 调用数均为
  `2 × turn_count - 1`，与一次 analyze 加相邻 evolution 的产品行为吻合；每题各有一次
  retrieval embedding 与 framework answer LLM。HaluMem 另有 7 次 update probe retrieval。
- prediction model inventory 与 track identity 都声明
  `all-MiniLM-L6-v2 / dimension=384 / local_unpinned / Chroma cosine`。
- public question 负空间未出现 gold answer、evidence、answer-session id、memory point 等
  私有字段；适用 evaluator 的 score 行与 summary 分母闭合。
- terminal log 无 API retry、rate limit、半写或 traceback。一次 LiteLLM 在线价格表 SSL
  timeout 自动回落本地静态表，不影响模型调用或实验产物。

## 5. HaluMem 细粒度验收

- 四个 session extraction report 均为 `ok`，每段恰好上报本 session 新增的 2 条官方
  `MemoryNote`；长期 memory 继续保留，不把全库冒充本段 extraction。
- update probe 共 7 个且 retrieval 非空；真实 judge observation：
  `extraction=113 / update=7 / QA=1`，与 score row 一一对应。
- extraction 汇总同时给出 recall、weighted recall、target/interference accuracy、FMR 与 F1；
  category breakdown 含 Event、Persona、Relationship。
- update 汇总给出 C/H/O，并按 Event、Persona 细分；QA 给出 C/H/O，当前 smoke 的
  `Memory Boundary` question type 单独落盘。
- `halumem_memory_type` 按官方共享分母分别落 Event、Persona、Relationship 三类，不以
  overall 掩盖类别差异。

这些极小样本分数只证明 evaluator 与产物契约可达，不代表正式效果。

## 6. 冻结后声明缺口

1. A-Mem evolution 会更新 links/context/tags。即使 current product 没改写
   `MemoryNote.content/id/source time`，检索对象仍是演化后的当前 memory；不得用 sidecar
   把它冒充原始 dataset turn 计算 Recall/Precision/NDCG。未来若另开语义相似度消融，必须
   另立 metric 定义，不能沿用 turn evidence 指标名称。
2. Chroma distance 是 method-native item score；不得直接与其他 method 的不同记忆粒度、
   score 标尺作 headline 横比。
3. smoke 只认证裁剪后的接线、真实 API、state、并行与 artifact，不外推 full 效果、成本或
   长程 100-evolution consolidation。
4. 本地 embedding revision 未 pin；正式效果阶段若切模型、revision、参数或 product source，
   必须重建 state 并局部重开 B8+/B11。
5. 作者 LoCoMo answer builder/复现参数、full cost pilot 与真实 resume 属正式实验阶段。

## 7. 失效触发器与最终裁决

method/source hash、adapter/public protocol、turn role/speaker/time/caption、evolution/
consolidation、product readout、state/sidecar、benchmark canonical mapping 或 HaluMem
evaluator 语义发生变化时，按影响面局部解冻。纯 artifact-only 新答案指标可以消费现有
prediction；任何重新消费 provenance lineage 的 retrieval 指标必须先重开 B5 裁决。

A-Mem current official product build 正式冻结为 **`method-frozen-v1`**。下一步转入
SimpleMem current text product 的真实五格 B11。
