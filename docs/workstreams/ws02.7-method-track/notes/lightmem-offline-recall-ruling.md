# LightMem offline update × Recall@k 架构裁决

> 日期：2026-07-15
> 裁决者：GPT-5 架构师
> 取证底：`lightmem-offline-recall-validity-audit.md`（Claude Sonnet 5）
> 范围：LoCoMo post-build offline update、provenance、Recall@k、检索单元粒度。
> 零真实 API；裁决依据已由架构师回读官方 LightMem、本框架和 MemoryData 源码。

## 1. 一句话裁决

**当前 LightMem × LoCoMo 的 Recall@10 可以被程序机械算出，但在 post-build
`offline_update_all_entries()` 发生 `update` 后，单一 `source_external_id` 不再是
当前 memory 文本的完整血缘，因此该数不能继续标为可信的 turn-level retrieval
recall。LightMem method-frozen-v1 的 B5/B11 暂时重开；修复只补传递血缘，禁止改变
update/delete 决策、旧 embedding、排序或 answer 路径。**

## 2. 为什么 update 后仍“能算”，却暂时“不可信”

官方 LoCoMo README 的报告命令检索 `qdrant_post_update`；构建脚本先完成抽取与
insert，再构造全库 update queue，最后运行 `offline_update_all_entries()`。官方
`UPDATE_PROMPT` 要求：同一事实有补充时，把 candidate 信息整合进 target；冲突时删
target；无关时忽略（`third_party/methods/LightMem/src/lightmem/memory/prompts.py:
334-404`）。

现实现的 `update` 分支却只覆盖 target payload 的 `memory`，复用旧 vector 和其余
payload（`lightmem.py:620-625`）；LLM 只看到 target/candidate 文本，看不到来源 id
（`factory/memory_manager/openai.py:379-406`）。本框架再把仍留在 target 上的单个
`source_external_id` 变成一个 `RetrievedItem.source_turn_ids`（adapter:1226-1264）。

因此会同时存在两种误判机制：

1. candidate 的信息已进入 target 文本，但 target 没带 candidate id：检索到这条
   memory 时可能对 candidate evidence **假阴性**；
2. target 原事实被更新文本弱化或替换，target id 仍保留：可能对 target evidence
   **假阳性**。

`delete` 本身不是 provenance bug：条目被方法删除后无法检索，Recall 下降正是被测
系统的真实行为。旧 embedding 与新文本不一致也是上游 post-update 算法的现状；为
“修好排序”重算 embedding 会改变算法，**本项目不得改**。

## 3. 修复口径：传递变换血缘，不改算法

批准一个 B5+ 观测级最小 diff：

- 初次 insert 时，在既有 singular anchor 之外写结构化
  `source_external_ids=[source_external_id]`；该字段不进入 memory 文本、embedding
  或 LLM prompt。
- action=`update` 时，把 target 与本次 candidate_sources 的 plural lineage 稳定
  去重并集写回 target；保留旧 vector、旧 singular anchor 和全部算法参数。
- action=`delete` 时照官方删除 target，不把被删来源伪挂到其他 entry。
- adapter 只把 plural lineage 转成 `source_turn_ids`；旧 state 缺 plural schema 时
  fail-fast，禁止回落 singular 后继续声称完整 turn provenance。
- lineage 的语义是“这个当前 memory 的变换输入来自哪些公开 turns”，不是声称
  LLM 输出中的每个 token 都能逐 turn 做 entailment。该语义与 summary/chunk 的来源
  并集一致，足以支持 retrieval lineage recall。

整轮 update 使用 `get_all()` 的初始快照并并行写回。某 candidate 在更新另一个
target 的单次调用中只读，但它可能在自己的任务中被更新/删除；血缘合并必须以该轮
实际提供给当前 update LLM 的快照输入为准，不能假设 candidate 轮末仍存在。

## 4. MemoryData：可参考手艺，不可拿数字校准

MemoryData 的 `hybrid_lightmem.yaml` 选择 `lightmem_ingest_mode: direct`。其 adapter
不走 `add_memory()` 的预压缩、分段、LLM 抽取和 post-build merge/delete，而是把
约 4096-token 原文 chunk 加带 source ids 的文本 header，手造 `MemoryEntry` 后只调
负责 embed+insert 的 `offline_update([entry])`。

所以它避开了本问题，不是解决了本问题；它测的是“chunked Qdrant RAG + LightMem
存储壳”。其 Recall@k 可帮助我们识别多来源 header/sidecar 的实现选项，但不能作为
LightMem 原算法的数值校准，更不能照抄其 direct ingest。

## 5. 粒度强校验：保留结构门，拒绝错误绑定

这里有三个不同概念，必须拆开：

1. `consume_granularity`：runner 以 turn/pair/session/conversation 哪种批次喂 method；
2. `provenance_granularity`：检索结果能归因到 turn 还是 session；
3. retrieval item granularity：top-k 中“一项”是 fact、summary、session 还是大 chunk。

当前 evaluator **没有**把 Recall@k 与 `consume_granularity` 强绑定；它只校验
manifest 的 provenance 枚举、`retrieval_query_top_k`、`retrieved_items` 和 top-k
内非空 `source_turn_ids`。这个方向是对的：conversation 级 ingest 完全可能返回
turn-level lineage，turn 级 ingest 也可能最终只生成 session summary。若强制二者相等，
反而会错杀合法方法。

现校验的问题不是“太强”，而是**只强在结构、不强在语义**：它无法确认 update/
merge 后的 `source_turn_ids` 是否仍覆盖当前条目的传递血缘。该语义保证应由 method
adapter 的变换级测试和 provenance schema 版本承担，不能靠 evaluator 猜。

另一个独立公平性风险是 retrieval item 宽度：一个 item 若覆盖 100 个 turns，
Recall@1 天然比一个 item=单 fact 更容易命中。禁止强制每 item 只能有一个 source id，
那会让 summary/merge 系统伪造精度；Phase 1 应把 Recall@k 定位为
**method-native item recall 的辅助指标**，同时报告 top-k 内 unique source 数和
`source_turn_ids/item` 分布。未加入 source/token budget 归一化前，不把它单独作为
跨 method headline 排名。

## 6. `top_k=10` 与 LightMem `retrieve_limit=60`

LightMem 返回有序 60 项，evaluator 取前 10 项计算 Recall@10；在血缘正确的前提下，
这件事本身成立，60 是 answer/native 检索宽度，10 是当前评测截面，二者不必相等。

但 runner 把 `RetrievalQuery.top_k` 全局硬编码为 10，LongMemEval 官方 rank evaluator
又只计算 `k <= retrieval_query_top_k`，于是官方 k=30/50 在真实通用 run 中必然被
跳过，即便 LightMem artifact 已保存 60 项。这是**answer context depth 与 metric
ranking depth 被同一个字段混用**的框架级缺口，不归本次 LightMem 单点修复。后续
协议卡应拆分 method-native answer depth 与 benchmark-required evaluation depth；在
拆分前不得把“有 60 条 artifact”偷换成“已公平覆盖所有 method 的 Recall@50”。

## 7. 影响面与恢复门

- 作废的只有既有 LightMem × LoCoMo post-update turn-recall 数字（包括
  `lm-locomo-unified-prov1` 的 recall=0.0 作为可信指标的声明）；answer/judge/F1、
  成本和 formatted_memory 证据不受此 metadata 缺口影响。
- LongMemEval/MemBench/BEAM/HaluMem 不调用 LoCoMo post-build merge/delete；其初始
  source id 透传未被本裁决否定，但 method-native item 宽度限制仍要随报告声明。
- 修复后必须跑定向离线测试、主树全量，并在用户批准预算/规模/run_id 后重跑至少
  LightMem × LoCoMo provenance smoke；开箱核 plural lineage 后，B5/B11 才能重新
  关闭并恢复 method-frozen 状态。
- 施工边界见 `actor-prompt-lightmem-lineage-repair.md`；由用户选择跨模型 actor 派发。
