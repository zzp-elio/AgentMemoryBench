# LightMem method-frozen-v2 验收记录

> 冻结日期：2026-07-17
>
> 真实 smoke 代码基线：main `568b95d`（包含 LightMem adapter
> `conversation-qa-v6`）
>
> 裁决：**B1-B11 重认证完成，LightMem 恢复为 `method-frozen-v2`。**

## 1. 为什么是 v2

历史 `method-frozen-v1` 后，LightMem 先后发生 lifecycle、role、缺失时间、MemBench canonical
pair、RetrievalEvidence 与 LoCoMo image caption 的实质契约变化。旧五格 smoke 仍是历史证据，
但不能替代最新 v6 build 的真实复验；冻结后推翻必须版本化，因此本轮不覆盖旧 note，而是形成
`method-frozen-v2`。

## 2. B1-B11 对表判词

| 判据 | v2 判词 | 承重证据 |
|---|---|---|
| B1 产品接口 | 通过 | vendored `LightMemory.add_memory` + 官方内部 embed/search 产品路径；不走 benchmark 专用 runner |
| B2 注入粒度 | 通过 | unified hybrid；LoCoMo 每个真实 named-speaker utterance 独立组成 `[real user, empty assistant]` pair；caption 在 method 边界渲染一次 |
| B3 隔离 | 通过 | 单 worker 直接使用 run 级 `method_state/`；并行使用 `worker_<idx>/` 物理隔离，每个 worker 只含自己的 conversation collection |
| B4 输入/时间/readout | 通过 | source time、speaker、role、caption 与 formatted memory 的离线强反例已过；真实 v6 smoke 覆盖 `conv-26/D1:5` |
| B5/B5+ provenance | 通过（含 N/A/pending） | online-soft LoCoMo 为 `valid/turn`；逐题 `RetrievalEvidence v1` 被 evaluator 严格消费；stable ranking 仍诚实为 pending |
| B6 flush | 通过 | conversation 尾批 force segment/extract；online-soft direct insert，不暗跑全库 consolidation |
| B7 效率 | 通过 | prediction model inventory、raw observations 与 overall/by-conversation/by-question summary 齐全 |
| B8/B8+ | 通过 | retrieve 纯读；每 conversation 独立 Qdrant；timeout/retry/失败清理证据保留 |
| B9 build identity | 通过 | MiniLM/384/Qdrant cosine、hybrid、online-soft、`gpt-4o-mini` 均落 manifest；本地模型 revision 如实 `local_unpinned` |
| B10 TOML/builder | 通过（性能阶段有声明缺口） | 当前 `smoke` 主 section 可复算；author section/完整官方 builder 只在首个作者校准或效果 full 前迁移，不阻塞 5×10 smoke |
| B11 主配置 smoke | 通过 | 历史五 benchmark 五件套证据保留；本轮补齐唯一被 caption v6 失效的 LoCoMo 最新 build 单/双 worker 实测 |

N/A 是能力裁决，不是接入失败；stable-ranking pending 只挡 rank/NDCG，不挡不依赖顺序的
Recall@k。

## 3. 最新 LoCoMo v6 真实 smoke

两条 run 都在 main `568b95d`、同一 source fingerprint、同一 method config/track identity 下执行：

| run_id | 规模 | prediction | evaluator |
|---|---:|---:|---|
| `lm-locomo-v6-r3q1-w1` | 1 conversation × 3 rounds × 1 question × 1 worker | 1/1 | `locomo-f1`、`f1`、`locomo-recall`、`locomo-judge` 全落盘 |
| `lm-locomo-v6-r3q1-c2-w2` | 2 conversations × 3 rounds × 每段 1 question × 2 workers | 2/2 | 同上四项全落盘 |

运行身份现场值：

- adapter=`conversation-qa-v6`；protocol=`v3`；prompt/readout=`unified`；
- `messages_use="hybrid"`；`lifecycle_profile="online_soft"`；
- embedding=`models/all-MiniLM-L6-v2` / 384 / Qdrant cosine；
- method retrieve limit=60；framework retrieval observation query depth=10；
- semantic provenance=`valid`，granularity=`turn`，stable ranking=`pending`。

两种 scope 的 `dataset_sha256` 不同是正确行为：双 worker run 多裁一段 conversation；真正应相同的
source fingerprint、method config 与 track identity 已逐项相等。

## 4. 开箱验货结果

### 4.1 完整性与隐私

- 两个 `checkpoints/progress.json` 均为 `stage="Completed"`；conversation/question 完成数分别
  为 `1/1` 与 `2/2`；`budget_exhausted=false`、空记忆 bridge sentinel=0。
- `method_predictions`、`answer_prompts`、`evaluator_private_labels` 行数严格对齐为 1/1/1 与
  2/2/2；四种 metric score/summary 文件全部存在。
- public question、answer-prompt 与 prediction metadata 通过私有键扫描；redacted config 未出现
  原始 API key。
- `logs/events.jsonl` 的末事件与 `logs/run.log` 的末行均是正式 `run_completed`。

### 4.2 Recall@10 不是“有分就算过”

三道题的 `retrieval_query_top_k=10`，每题实际返回 5 个 item；每个 top-k item 均有非空、无
首尾空白的公开 `source_turn_ids`。架构师没有信任既有 summary，而是重新从 evaluator-private
`GoldEvidenceGroupSet(turn, locomo_utterance)` 选择官方 unit，按 top-k source-id 并集执行
group any-of 公式：

- `conv-26:q0`（单 worker）：5 items / 5 unique source ids / 1 gold group → 1.0；
- `conv-26:q0`（双 worker）：5 / 5 / 1 → 1.0；
- `conv-30:q0`（双 worker）：5 items / 4 unique source ids / 1 gold group → 1.0。

`conv-30` 的两个 memory item 指向同一公开 turn，Recall 按 source-id 稳定去重后只命中一次；
这正是 group Recall 的预期语义，不是重复加分。

### 4.3 caption 与物理隔离

真实 Qdrant 逐 collection 打开检查：三段 conversation build 均写出 5 个 LTM entries，每条都有
plural lineage。caption-bearing `conv-26/D1:5` 在单 worker 与双 worker 的 conv-26 LTM lineage
中都存在，证明它实际进入 v6 抽取/落库链。payload 没有保留字面 wrapper 不构成缺口：B4
要求 caption 对算法可见，不要求抽取 LLM 必须逐字复制 wrapper；字节级边界由 caption v6 离线
强反例负责，真实 smoke 负责证明新 build 确实走通。

单 worker 的真实布局是 `method_state/qdrant/`；双 worker 才是
`method_state/worker_0/qdrant/` 与 `worker_1/qdrant/`。双 worker 中 worker 0 只含 `conv-26`，
worker 1 只含 `conv-30`，collection 名与路径均不同，未发现跨 conversation state。

### 4.4 分数解释

- 单 worker：LoCoMo F1=1、通用 F1=1、Recall=1、judge=1。
- 双 worker：两种 F1 mean=`0.153846...`，Recall=1，judge=1。

低 token-F1 不是并行回归。相同 `conv-26:q0` 的两次真实 build 产生了不同 retrieved memory 文本，
answer prompt 因而不同；一个答案直接写日期，另一个用“May 8 的前一天”表达。`conv-30` 又把
`19 January 2023` 写成 `20230119`。token overlap 会惩罚这些表述，semantic judge 判正确；smoke
只认证链路与 artifact，不把三题分数当效果结论。

### 4.5 冻结后追加的 artifact-only answer metrics

Metric Pack M0 合入后，架构师直接消费上述既有 prediction/private-label artifact，零 API、零
method 重跑，追加 `normalized-em` 与 directional `substring-em`：

- `lm-locomo-v6-r3q1-w1`：两项均 0/1；
- `lm-locomo-v6-r3q1-c2-w2`：两项均 0/2。

逐题 details 已写入 normalized 字符串/token。单 worker 的 `May 7, 2023` 对 gold
`7 May 2023` 因 token 顺序不同而两项均 0；双 worker 的相对日期叙述与 `20230119` 对自然语言
日期也不满足 exact/contiguous-token 条件。该结果与既有 semantic judge=1 不矛盾，反而说明不同
metric 捕捉不同性质；不能为了让 lexical 分数变高而改 normalizer 或答案。terminal receipts 位于
两条 run 各自的 `logs/terminal.evaluate-answer-metric-pack.log`。

## 5. 日志归档与已知显示缺口

六份 terminal log 已归入各 run 的 `logs/terminal.*.log`，不再散放在
`outputs/terminal-logs/`。`tee` 令 stdout 不再被识别为 TTY，Rich 默认关闭颜色，所以用户看到
白色输出；这是显示策略，不影响 artifact。

双 worker 的 terminal tee 没显示 `Prediction run completed` 与最终 JSON，但 run 内
`run.log`、`events.jsonl`、checkpoint、summary 和全部后续 evaluate 均完整，裁为 terminal
receipt 缺口，不是 prediction 中断。终端体验整改已另有日程，本轮不扩成 runner 改造。

## 6. 冻结后保留的声明缺口

1. stable ranking 尚未审计，LightMem rank/NDCG 保持 pending；不能拿 Recall=1 推导排序健康。
2. framework observation depth 当前为 10，不能报告 LongMemEval 官方 k=30/50。
3. LoCoMo consolidated 补充 profile 会 merge/update，semantic provenance 指标 N/A；v2 主冻结只
   覆盖 paper online-soft direct-insert profile。
4. LME/BEAM/HaluMem 的 turn-exact provenance 依各自契约为 N/A；MemBench 只能声明 pair-step
   unit，不伪造 child-exact。
5. 本地 embedding revision 尚未 pin；效果 full 前要完成最终主参数/embedding 裁决。
6. `author_locomo`/`author_longmemeval` TOML section 与完整 answer builder 在首次作者校准前迁移；
   旧 `unified/native` 只保留历史产物身份。
7. 真实 resume 按既有裁决延后到 formal/full cost-probe，不阻塞 v2。
8. 新 answer metric 可以基于本次 artifacts 离线追加，不重跑 method；它们的新增不反向解冻
   LightMem build。

## 7. 最终裁决

LightMem 在当前 Phase 1 主 build 上恢复为 **`method-frozen-v2`**。下一家 method 严格串行转入
Mem0；Metric Pack 是共享 evaluator 支线，可在不解冻 LightMem 的前提下单独 R1/合入，并对本次
run 追加离线评分。
