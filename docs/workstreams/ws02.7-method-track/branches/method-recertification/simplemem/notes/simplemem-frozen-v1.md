# SimpleMem method-frozen-v1 验收记录

> 冻结日期：2026-07-23
>
> 真实 smoke 代码/命令基线：main `526e978` 加本冻结批 compatibility/docs diff
>
> method source identity：
> `d9ce839d5852db8be33d74f5984aec2ae3f94240b53403b14da6677529747b38`
>
> vendored source identity：
> `1aae7311a85f9a809f1f1912ab77420d68717b259883269adbac915b0ee39e16`
>
> adapter：`simplemem-text-v2`
>
> 裁决：**B1-B11 current text product 重认证完成，SimpleMem 冻结为
> `method-frozen-v1`。**

## 1. 冻结对象

主轨使用官方 text product
`third_party/methods/SimpleMem/SimpleMemSystem.add_dialogue/finalize` 与
`hybrid_retriever.retrieve`，上游 commit
`60a48e83a7fef10d386e1f438589047d3a4257bc`。最终回答由 framework reader
生成，不调用产品 `ask()`。

每个 canonical turn 独立传入原生 `speaker/content/timestamp`；LoCoMo 使用真实
speaker name，其余 benchmark 使用 canonical role。图片走共享 caption wrapper，
MemBench 原 place/time 尾注不删，typed time 严格为
`turn → 当前 session → None`，不造 placeholder 或合成时间。

## 2. 构建与 session 生命周期裁决

主配置显式 `enable_parallel_processing=false`。当前 adapter 逐 turn 调用
`add_dialogue()`；窗口满时同步处理，因此后一窗口能看到前一窗口生成的
`previous_entries`，并保留 overlap 的顺序依赖。官方 `add_dialogues_parallel()`
会让同批窗口共享提交前的旧 context，不等价于这条链，故不用于 Phase 1 build。

检索阶段的 multi-query parallelism 是官方 Stage 3，继续启用；compatibility patch 只给
worker 传播 framework 的 observation ContextVar，不改 query 集合、worker 数、
`as_completed()` 合并顺序或返回值。

HaluMem 在每个真实 session 边界调用产品 `finalize()`，只上报本段新生成的
MemoryEntry。报告后只清下一窗口抽取参考用的 `memory_builder.previous_entries`，
不删除 LanceDB 长期记忆；后续 update/QA 仍检索完整 conversation 历史。该边界避免
上一 session 的最后窗口被冒充为下一 session 的 extraction 输入。

## 3. B1-B11 最终判词

| 判据 | v1 判词 | 承重证据 |
|---|---|---|
| B1 产品接口/来源 | 通过 | 官方 text product、MIT、固定 upstream commit 与 source hash |
| B2 注入粒度 | 通过 | 五格均 turn；speaker/content/timestamp 原生表达，无 placeholder |
| B3 隔离 | 通过 | 每 conversation 独占 product system、LanceDB 与 state；W2 物理分离 |
| B4 输入/时间/readout | 通过 | role/speaker/content/caption/place/source time 无损；readout 回带全部产品字段 |
| B5 provenance/ranking | 通过（N/A/pending） | 合成 memory 无 exact source membership；多路 completion-order merge 无统一全局 score |
| B6 flush/finalize | 通过 | conversation 尾 finalize；HaluMem session-local finalize/delta，长期记忆保留 |
| B7 效率 | 通过 | build/retrieval embedding、memory/answer/judge LLM observation 全部落盘 |
| B8/B8+ | 通过 | retrieve 不写 memory；endpoint/timeout/retry/clean retry 已锁 |
| B9 build identity | 通过（controlled） | `gpt-4o-mini` + MiniLM-384/internal L2 + LanceDB L2，如实非 product-default |
| B10 TOML/builder | 通过 | 跨五格固定主配置；build 串行、retrieval 并行显式声明 |
| B11 smoke+冻结 | 通过 | 五 benchmark、11 个正式真实 run、全部 worker/variant、适用 metric 与机器门关闭 |

SimpleMem 的 MemoryEntry 是 LLM 对窗口的语义融合结果，产品不保存
output-to-source membership。输入 lineage 只能证明 dialogue 参与过生成，不能证明每条
当前 memory 仍承载某个原始 fact。因此 Recall@K、Precision@K、retrieval-F1@K 与
NDCG 一律 N/A。hybrid retriever 的输出可供 answer reader 使用，但 completion-order
多查询结果再追加 lexical/symbolic hit，没有统一全局 score/rerank，故
`stable_ranking=pending`。

## 4. 可复现的产品兼容层

真实哨兵暴露两处上游依赖兼容问题：

1. LanceDB 0.34 已删除 `create_fts_index(use_tantivy=True)`，上游吞异常后 keyword
   retrieval 静默退化为 0 hit；修复为同列、同 `en_stem`、同 BM25/top-k 的 native FTS。
2. Python `ThreadPoolExecutor` 不自动继承 ContextVar，语义检索实际发生但 retrieval
   embedding observation 丢失；每个 submit 使用独立 `copy_context()` 传播当前 scope。

SimpleMem repo 本身 local-only，不入主 Git。上述最小 diff 固化在
`scripts/patches/simplemem-product-compat.patch`，由
`scripts/fetch_third_party_methods.sh` 在固定 upstream commit 后幂等应用。测试同时锁
patch 可逆校验、真实产品 import、真实 LanceDB FTS hit 与双并发 query scope；不会出现
“本机改过、换机器丢修复”的假冻结。

## 5. 真实 run roster

| benchmark | 正式真实 run |
|---|---|
| LoCoMo | `simplemem-locomo-v2-r3q1-w1-r4`；`simplemem-locomo-v2-r3q1-c2-w2` |
| LongMemEval | `simplemem-lme-v2-r1q1-w1-s-cleaned`；`simplemem-lme-v2-r1q1-c2-w2-s-cleaned` |
| MemBench `0_10k` | `simplemem-membench-v2-r1q1-ps1-w1-0-10k`；`simplemem-membench-v2-r1q1-ps1-w2-0-10k` |
| BEAM `100K` | `simplemem-beam-v2-r1q1-w1-100k`；`simplemem-beam-v2-r1q1-c2-w2-100k` |
| BEAM `10M` | `simplemem-beam-v2-r1q1-w1-10m`；`simplemem-beam-v2-r1q1-c2-w2-10m` |
| HaluMem Medium | `simplemem-halumem-v2-r1-w1-medium` |

以下 run 是修复前诊断资产，不进入冻结 roster：

- `simplemem-locomo-v2-r3q1-w1`：缺 `dateparser`，在 API 前 import fail-fast；
- `simplemem-locomo-v2-r3q1-w1-r2`：旧 LanceDB Tantivy 参数使 FTS 退化；
- `simplemem-locomo-v2-r3q1-w1-r3`：线程 ContextVar 未传播，缺 retrieval embedding
  observation。

`r4` 是 LoCoMo 正式 W1 证据。

## 6. 统一机器门

```text
PASS simplemem-locomo-v2-r3q1-w1-r4: q=1, c=1, w=1, rows=[7], retrieval=N/A, ranking=pending
PASS simplemem-locomo-v2-r3q1-c2-w2: q=2, c=2, w=2, rows=[7, 4], retrieval=N/A, ranking=pending
PASS simplemem-lme-v2-r1q1-w1-s-cleaned: q=1, c=1, w=1, rows=[2], retrieval=N/A, ranking=pending
PASS simplemem-lme-v2-r1q1-c2-w2-s-cleaned: q=2, c=2, w=2, rows=[3, 8], retrieval=N/A, ranking=pending
PASS simplemem-membench-v2-r1q1-ps1-w1-0-10k: q=4, c=4, w=1, rows=[2, 2, 2, 2], retrieval=N/A, ranking=pending
PASS simplemem-membench-v2-r1q1-ps1-w2-0-10k: q=4, c=4, w=2, rows=[2, 2, 2, 2], retrieval=N/A, ranking=pending
PASS simplemem-beam-v2-r1q1-w1-100k: q=1, c=1, w=1, rows=[4], retrieval=N/A, ranking=pending
PASS simplemem-beam-v2-r1q1-c2-w2-100k: q=2, c=2, w=2, rows=[4, 8], retrieval=N/A, ranking=pending
PASS simplemem-beam-v2-r1q1-w1-10m: q=1, c=1, w=1, rows=[16], retrieval=N/A, ranking=pending
PASS simplemem-beam-v2-r1q1-c2-w2-10m: q=2, c=2, w=2, rows=[16, 9], retrieval=N/A, ranking=pending
PASS simplemem-halumem-v2-r1-w1-medium: q=1, c=1, w=1, rows=[9], retrieval=N/A, ranking=pending
PASS SimpleMem x HaluMem: session-local delta, cumulative LTM,
  122 exact judge scopes, full breakdowns
SIMPLEMEM_B11_MACHINE_GATE_PASSED
```

逐层验货确认：

- 最终主树回归为
  `1680 passed, 3 deselected, 1 warning, 29 subtests passed in 150.75s`；
  `src+tests+SimpleMem core` compileall exit 0，唯一 warning 是既有 LightMem
  Pydantic deprecation。
- 所有 checkpoint 均 completed；W2 run 存在 worker 物理 state，W1 不伪造 worker 层。
- 所有正式 manifest 均为 `simplemem-text-v2`、MiniLM-384，
  `enable_parallel_processing=false`、`enable_parallel_retrieval=true`。
- LanceDB row 数与每个 isolation 的合成 MemoryEntry 数一致；state/source identity
  和文件 hash 闭合。
- 每题 evidence 均为 `semantic_provenance=n_a/none`、
  `stable_ranking=pending`；所有 retrieval metric summary 诚实为 N/A，没有回落 0 分。
- public question/artifact 负空间没有 gold answer、evidence、target id、memory point 等
  私有字段；answer/judge 与效率 observation 数量闭合。

## 7. HaluMem 细粒度验收

- 四个 session extraction report 分别新增 `2/2/2/3` 条合成 memory，共 9 条；LanceDB
  长期视图在最后仍为 9 条，不因 session-local delta 清理。
- update probe 共 7 个，每个都消费 9 条当前长期记忆；真实 judge observation 为
  `extraction=114 / update=7 / QA=1`，总计 122，与 score row 一一对应。
- extraction 同时落 recall、weighted recall、target/interference accuracy、FMR、F1；
  update 落 C/H/O；QA 落 C/H/O。
- memory type 分别落 Event、Persona、Relationship；当前 QA 的
  `Memory Boundary` question type 单独落盘。

这些极小样本分数只证明 evaluator、session lifecycle 与产物契约可达，不代表正式效果。

## 8. 冻结后声明缺口

1. 当前主 build 是 controlled MiniLM-384，不是 SimpleMem product-default Qwen3；效果阶段
   若切 embedding/LLM/参数，必须重建 state 并局部重开 B8+/B11。
2. build parallel 模式不是当前身份。未来若改走 `add_dialogues_parallel()`，必须作为算法
   profile 重新认证 overlap/previous_entries 语义，不能只翻 TOML 布尔值。
3. stable ranking 仍 pending；不得用当前 completion-order 列表计算 NDCG。
4. smoke 只认证裁剪后的真实接线、API、state、并行与 artifact，不外推 full 效果、成本或
   长窗口质量。
5. 作者 answer builder/效果参数、真实 resume、full cost pilot 属后续正式实验阶段。

## 9. 失效触发器与最终裁决

upstream/source hash、compatibility patch、adapter/protocol、speaker/time/caption、
window/overlap/finalize、session extraction boundary、hybrid merge、state identity 或
benchmark canonical mapping 发生变化时，按影响面局部解冻。纯 artifact-only 新答案指标
可以消费现有 prediction；任何试图用生成 lineage 计算 retrieval evidence 的指标都必须先
重开 B5 裁决。

SimpleMem current text product build 正式冻结为 **`method-frozen-v1`**。
