# LightMem method-frozen-v3 验收记录

> 冻结日期：2026-07-19
>
> 真实 smoke 代码基线：main `c241b73`
>
> method source identity：
> `a44d7d99790496337270058d71f38737375ff4b2763495ed2b02baa43698d7e5`
>
> adapter：`conversation-qa-v7`
>
> 裁决：**B1-B11 current build 重认证完成，LightMem 冻结为 `method-frozen-v3`。**

## 1. 为什么另立 v3

`method-frozen-v2` 是 `conversation-qa-v6` 的有效历史快照。其后公共 product readout、embedding
observation、MemBench/BEAM pair 投递、HaluMem session flush 与 vendored sensory bookkeeping
均发生了实质变化；尤其 `8879af9` 把 sensory runtime 纳入 source identity，旧 run 不能冒充新
build resume。因此不覆盖 v2，而以 current-v7 的五格真实 artifact 与最终 100K refill 形成 v3。

## 2. B1-B11 最终判词

| 判据 | v3 判词 | 承重证据 |
|---|---|---|
| B1 产品接口/来源 | 通过 | 通用 `LightMemory.add_memory` 与官方内部 embed/search 产品路径；8 文件 source identity 含 `sensory_memory.py` |
| B2 注入粒度 | 通过 | unified hybrid；LoCoMo named speaker、LME/MemBench/BEAM pair、HaluMem session 均按 concrete manifest 投递 |
| B3 隔离 | 通过 | W1 run 级 state；W2 worker 物理 state，LoCoMo/LME/MemBench/BEAM 均有真实隔离证据 |
| B4 输入/时间/readout | 通过 | caption、role、speaker、source time/place、missing-time None 与完整 ISO product readout 均实测；不以 question time 回填 history |
| B5/B5+ provenance | 通过（含诚实 N/A/pending） | LoCoMo/MemBench valid；LME/BEAM/HaluMem 按证据单位 N/A；stable ranking pending，不伪造资格 |
| B6 flush/finalize | 通过 | forced cleanup 与 automatic-prefix+tail 合并已修；real vendored 双 session、HaluMem B11 与 100K ThirdHigh 两次 extraction 共同承重 |
| B7 效率 | 通过 | prediction、embedding、answer 与 artifact-level judge observation/model inventory 均落盘；离线 evaluator 不造调用 |
| B8/B8+ | 通过 | retrieve 纯读、失败清理/timeout/retry 证据保留、无跨 conversation state |
| B9 build identity | 通过 | MiniLM/384/Qdrant cosine + hybrid + online-soft + `gpt-4o-mini` 写入 manifest；本地 revision 如实 unpinned |
| B10 TOML/builder | 通过（效果阶段有声明缺口） | 当前 smoke section truthful；author section/完整 builder 在首次作者校准前迁移，不阻塞 5×10 smoke |
| B11 smoke+冻结 | 通过 | 五 benchmark current-v7 真实行为门、适用指标、效率与并行门均关闭；forced-flush 唯一 reachability 命中的 100K 哨兵已用 current identity 补跑并验收 |

N/A 是 metric 能力结论，不是 method 接入失败；smoke 分数不参与 B11 的通过判定。

## 3. current-v7 真实 run roster

| benchmark | 真实 run |
|---|---|
| LoCoMo | `lm-locomo-v7-r3q1-w1`；`lm-locomo-v7-r3q1-c2-w2` |
| LongMemEval | `lm-lme-v7-r1q1-w1-s-cleaned`；`lm-lme-v7-r1q1-c2-w2-s-cleaned` |
| MemBench `0_10k` | `lm-membench-v7-pair-r1q1-ps1-w1-0-10k`；`lm-membench-v7-pair-r1q1-ps1-w2-0-10k` |
| MemBench `100k` 补充哨兵 | `lm-membench-v7-flush-r1-none100k-fh-th-r1q1-w1-100k` |
| BEAM | `lm-beam-v7-pair-r1q1-c2-w2-100k`；`lm-beam-v7-pair-r1q1-w1-10m` |
| HaluMem | `lm-halumem-v7-flush-r1-w1-medium` |

这些 run 认证的是 cropped smoke 的接线和 artifact，不外推 full、效果、成本或真实 resume。

## 4. 最终 100K current-identity 冻结门

最终 run 精确选择 FirstHigh+ThirdHigh 各首条、1 round、1 question、W1，不从 gold 选样。
manifest 为 pair/hybrid/online-soft/preserve-none，source hash 精确等于本文顶部值并包含
`sensory_memory.py`。独立开箱结果：

```text
conversations/questions = 2/2
memory_build_llm_calls = {FirstHigh: 1, ThirdHigh: 2}
ltm = {FirstHigh: 0, ThirdHigh: 0}
retrieval_embedding_calls = 2
retrieved = {}
qdrant_write = n/a_zero_extraction_local_qdrant_regression
```

ThirdHigh 的两次 memory-build 与零 API reachability 的 automatic step 1 + forced step 2 精确
对应，关闭旧实现漏 prefix 的反证。三项 MemBench metric 均完整落盘：choice/source/Recall 都为
0，Recall 两题 status 均为 `ok`。这是 distractor 未产生记忆后的诚实结果，不是漏评或异常；
terminal logs 无 traceback、error、timeout、rate-limit，checkpoint=`Completed`。

## 5. 冻结后保留的声明缺口

1. stable ranking 尚未审计，rank/NDCG 保持 pending；LongMemEval 官方 k=30/50 也仍受 framework
   query depth 10 限制。
2. LoCoMo offline-consolidated 补充 profile 的 provenance Recall/NDCG 为 N/A；v3 主冻结只覆盖
   `online_soft` direct-insert profile。
3. LME/BEAM/HaluMem 的 turn-exact retrieval metric 按各自 evidence unit 继续 N/A。
4. missing timestamp 是 framework-extended `preserve_none` 兼容，不冒充 upstream native parity。
5. product/effect 主配置、embedding revision pin、`author_locomo`/`author_longmemeval` 完整 builder、
   full cost pilot 与真实 resume 均属于效果/正式实验阶段，不由 smoke 冻结代证。
6. HaluMem 只认证 Medium fixed W1 operation-level smoke，不外推 Long 或多 worker。

## 6. 失效触发器

以下任一发生时，按影响面局部解冻，不盲目重烧五格：8 文件 method source hash、adapter/public
protocol、role/granularity/time/caption/readout/lifecycle、benchmark canonical mapping、
RetrievalEvidence/gold-unit 或 evaluator 公式发生变化。纯 artifact-only 新 metric 可直接消费既有
prediction，不反向解冻 method build。

## 7. 最终裁决

LightMem current Phase 1 smoke build 正式冻结为 **`method-frozen-v3`**。下一家 method 按既定
顺序转入 Mem0；本文列出的效果阶段缺口继续保留，但不阻塞 5×10 smoke 主线。
