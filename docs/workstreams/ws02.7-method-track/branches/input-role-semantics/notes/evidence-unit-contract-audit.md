# canonical turn 与 gold evidence unit 通用契约审计

> 日期：2026-07-16。性质：actor docs-only 高判断审计（Fable 5），零真实 API、零下载、
> 零生产代码修改；本文只产出证据与推荐，最终裁决权在架构师。
> 分工披露：框架协议/事件流/artifact 链、MemBench adapter+recall evaluator、BEAM adapter、
> LME 官方剔除逻辑与三项关键计数、HaluMem schema 负空间由 Fable 5 亲自一手读取或复算；
> 三个 Opus subagent 并行取证 MemBench 官方 scorer/数据统计、BEAM 官方消费面/Arrow 统计、
> LoCoMo/LME/HaluMem 官方 qrel 语义，其全部承重锚（官方 scorer 行号、user-only corpus、
> 51/21/54 计数、memory_point 无 turn 回指）已由 Fable 5 逐条在源码/真实数据上复核。
> 文件锚点：框架侧默认相对本仓库 `src/memory_benchmark/`；官方侧相对
> `third_party/benchmarks/`；行号以 2026-07-16 主线 `a5ddf01` 为准。

## 0. 结论先行

1. 五 benchmark 的 gold evidence unit 各不相同且与 canonical `Turn` 不同构：MemBench=
   pair 级 step、BEAM=单条 message（但 raw id 仅 conversation 内唯一）、LoCoMo=单条
   utterance、LongMemEval=user 侧 has_answer turn + gold session 双粒度、HaluMem=
   memory-point fact 级（无 turn 回指，turn-level qrel 诚实 N/A）。
2. **唯一首选推荐：方案 1「gold evidence group」**——benchmark adapter 在 load 时把一个
   官方 gold unit 展开为一组 canonical child turn ids，作为 evaluator 私有 qrel 落
   `GoldAnswerInfo`；evaluator 按 group any-of 计一次命中，分母=官方 unit 数。provider
   协议与全部 method adapter **零改动**；gold 不经过任何 method 可见通道。
3. MemBench FirstAgent 拆分后，「命中一个 gold step」的官方等价语义是「命中该 step 拆出
   的任一 child turn」（any-of）：官方 scorer 只比较 step 整数、完全无 role 维度
   （§2.1）。all-of 会比官方更严，机械翻倍分母则直接改变指标含义，二者都不是 parity。
4. 顺带证实三处需架构师知情的现存偏差：LME 框架 gold 收了官方不收的 54 个 assistant 侧
   has_answer turn，且未实现官方 51 题 no-user-target 剔除（旧断点「30 abs + 21 无目标」
   表述需修正，见 §2.4）；BEAM recall 官方根本不评（框架补充指标，无官方分母可 parity）；
   MemBench 框架分母不去重、官方去重（当前数据零重复故无实际影响，随本契约一并对齐）。

## 1. 三个必须拆开的概念

全篇按以下定义使用，不得混用：

1. **`consume_granularity`**：框架把多少 canonical turn 聚合后交给 method 的**输入侧投递
   粒度**。实例级声明 `turn|pair|session|conversation`（`core/provider_protocol.py:16`），
   由 `runners/event_stream.py:63` `GranularityAggregator` 聚合投递；pair 为 user 锚定
   交换对，orphan/dangling 有 metadata 标记（`event_stream.py:110-154`）。
2. **`provenance_granularity`**：method 返回的 memory 能把**来源定位到多细**的输出侧
   声明。`none|session|turn`（`core/provider_protocol.py:17`），载体是
   `RetrievedItem.source_turn_ids`（`:247`）与逐题 `RetrievalEvidence`
   （`:305-335`，M0 已合入）。
3. **`gold_evidence_unit`**：benchmark 官方一个 relevance/qrel 项**实际指向的原始容器**。
   它是 per-benchmark 的数据事实，与前两者相互独立；本文 §2 逐家给出一手认定。

两条已裁定原则约束三者的关系：

- **method 消费 pair/session ≠ gold 是 pair/session。**消费粒度是投递便利，gold 单元是
  benchmark 数据事实。判例：Mem0 以 pair/session 批消费，其 sidecar 记的批内 turn id
  并集只是「批归属」，架构师已裁 Mem0×BEAM turn Recall=n_a、Mem0×LME 只可报 session
  口径（`../retrieval-metrics/notes/retrieval-metric-eligibility-ruling.md` §2.1、§4）。
- **provider 报出「参与过生成」的 turn ids ≠ 当前 memory 对每个 gold fact 语义相关。**
  变换输入 lineage 只证明参与，不证明语义承载（`AGENTS.md` 指标资格原则；LightMem
  transformation-input union 假阳性判例）。因此 gold group 匹配只能在
  `RetrievalEvidence.semantic_provenance` 资格门放行之后进行，id 交集本身不是资格。

另一条既定架构判据（本文对表的承重前提）：spec-protocol-v3 §5 已经用户定案——
**「统一按最细粒度（turn 级 `source_turn_ids`）记录……任何更粗粒度的 recall 都由框架
向上聚合得出」**（`docs/workstreams/ws02-phase1-matrix/spec-protocol-v3.md:195-203`）。
即「粗单元 = 细单元集合 + 框架侧映射」是既有方向，不是本文新发明。

## 2. 五 benchmark 一手资格表

### 2.1 MemBench

| 维度 | 一手事实 |
|---|---|
| 官方 gold 字段 | `QA.target_step_id: list[int]`，0 基 `message_list` 索引（数据集结构说明.md:100；加噪回写 `load_test_data.py:208` `[id[0] for id in ...]` 展平自 `[within, session]` pair） |
| 指向容器 | 一个 int = 一个 step。FirstAgent step=`{"user": str, "agent": str}` dict（4 文件全量确认 dict 形态）；ThirdAgent step=纯字符串 |
| canonical 映射（现状） | `benchmark_adapters/membench.py:626-629` 一 step 一 Turn；`:707` `turn_id=str(step_index+1)`（1 基）；`:712-716` FirstAgent 拼成伪 user content，`:715` 公开 metadata 已留 `ps_user`/`ps_agent` 两侧原文；gold `evidence=[str(id+1)]` 进私有 `GoldAnswerInfo.evidence`（`:790`） |
| 一 unit 多 child？ | **拆分后是**：FirstAgent 一 step → user turn + assistant turn 两个 child。ThirdAgent 仍单 child |
| any-of/group 语义 | 官方 `env/Membenenv.py:5-15` `get_recall`：`res=list(set(res))`、分子=|set(res)∩std|、**分母=len(set(std))**；只比 step 整数。**零 role 维度**——官方存储把 user+agent 塞同一 step 前缀（`MembenchAgent.py:69` `store("{}[|]'user': ...; 'agent': ...")`），`retri` 只 parse 前缀整数（`CommonMemory.py:270/1008/1082/1119`）。多 target 普遍（如 FirstHigh 647/700 题 len>1），逐 step 部分给分 |
| id 异常 | 同题内重复=0、负数=0、None=0；越界 1 例（FirstLow comparative/events tid=4，val=111=len，同源 bug 存在于 100k 版）；空 target 1 例（FirstHigh highlevel_rec/movie tid=25） |
| 框架 evaluator 分母 | `evaluators/membench_recall.py:114-121` `score=hits/len(evidence)`——**不去重**，与官方 `len(set(std))` 有细微口径差（当前数据零重复故无实际影响）；空 evidence 记 1.0（`:116`）；step 假设不在 evaluator（纯 turn-id 字符串交集），写死在 adapter 三处（`:626-629,:707,:790`） |
| 公开 artifact 最少保存 | 题干/选项/时间/类别/conversation_id/公开 turn 序列。**`target_step_id` 及其 +1 映射必须私有**：虽不含答案正文，但精确泄漏证据位置，method 可据此直刷 recall。官方 QA 公开字段无任何 step 引用。现状路径隔离正确（公开 `Question.metadata` 无该字段，`membench.py:775-781`） |

拆分后官方等价语义的裁决输入：官方「命中 step S」=「携带整数 S 的记忆单元被检索到」，
S 唯一标识整个 `{user, agent}` step，官方无法、也从未区分证据在哪一侧。故 parity 翻译
只能是 **any-of over {user_child, assistant_child}，每个官方 step 计一次**；gold 的
user/agent 侧归属官方无标注，标 UNDETERMINED，禁止代裁。另：官方运行时驱动脚本未随
vendored 源发布，其存储 step 整数是否与 0 基 target 有 off-by-one 属 UNDETERMINED，
但框架自建 1 基 turn-id 空间并自洽映射，不受影响。

### 2.2 BEAM

| 维度 | 一手事实 |
|---|---|
| 官方 gold 字段 | `probing_questions`（Python-repr 字符串列）内每题的 `source_chat_ids`；结构三态：flat `list[int]`、语义分组 dict（如 contradiction 的 `{first_statement, second_statement}`）、`None`（abstention 恒 None） |
| 指向容器 | **一个 chat id = 一条单 speaker message**，与 canonical Turn 同构。铁证：生成侧 `BEAM/src/beam/main.py:2313` `chat_id: {message['id']}, {ROLE}: {content}`（Fable 亲核） |
| id 唯一性 | conversation 内 0..N-1 全局连续（跨 session 不重置）；**跨 conversation 从 0 重启**——全局定位必须复合键 `(conversation_id, id)` |
| 官方消费 | **官方评测完全不消费 `source_chat_ids`**：`evaluation/compute_metrics.py` 10 个 `evaluate_*`（:339-636）只吃 rubric+response 走 LLM judge，`grep source_chat_ids evaluation/`=0（Fable 亲核）。它是生成期 provenance 元数据。**框架 BEAM recall 是补充指标，无官方分母可 parity**（`beam_recall.py:16-19` 已自标 `framework_supplementary`） |
| evidence role 分布 | 100K：information_extraction 7/40 assistant-only、13/40 mixed；summarization 12/40 assistant-only、21/40 mixed；multi_session_reasoning 14/40 mixed。**「证据只在 user 侧」不成立** |
| canonical 映射（现状） | `beam.py:623` `turn_id=f"{session_id}:t{turn_index}"`（10M 为 `p{n}:s{m}:t{k}`，`:501`）；raw id 进 `Turn.metadata["id"]`（`:629`）；`_map_evidence_turn_ids`（`:522-547`）load 时把 raw id 映射为公开 turn_id 列表，连同 ambiguous/unmatched 计数落私有 `GoldAnswerInfo.metadata`（`:402-414`，`evidence=[]` `:428`）；公开 `Question.metadata={}`（`:422`）；`core/validators.py:61` 黑名单拦 `source_chat_ids` |
| 一 unit 多 child？ | 否（1 id = 1 message = 1 turn，退化单元素 group）；但 raw id 理论一对多时 adapter 已有 ambiguous 防御（实测恒 0） |
| 分母/异常 | `beam_recall.py:90-101` `hits/len(evidence)` 逐 gold turn any-match；abstention/空 evidence 题记 `score=None,status="n/a"` 不进均值（`:71-88`）——**这是全框架唯一把空 gold 正确记 n/a 的 evaluator**，可作 LME/MemBench 修正样板。10M 超长 evidence（event_ordering 单题至 83 id）；10M 恰 2 处 user→user adjacency（conv `1` id 13676→13677、conv `2` id 12990→12991），pair 聚合 orphan 分支必须保留 |
| 公开 artifact 最少保存 | 题干/category/conversation_id。turn_id 与 chat id 列表都是答案定位器，必须私有；现状安全 |

### 2.3 LoCoMo

| 维度 | 一手事实 |
|---|---|
| 官方 gold 字段 | `evidence: list[str]`，元素为 `dia_id`，格式 `D<session>:<turn>` |
| 指向容器 | 单条 utterance（命名 speaker 的一次发言），**与 canonical Turn 一一对应** |
| 官方消费 | `locomo-main/task_eval/evaluation.py:228-237`（Fable 亲核）：答案分不用 evidence；RAG 召回诊断 `recall=hits/len(evidence)` 逐 evidence 部分给分；context 以 `S` 开头时上卷 session 号比较；**空 evidence 或无 context 记 1**（`:237`，官方原生行为） |
| id 异常 | 5882 turns 格式 0 畸形、sample 内 0 重复；但 **9/2815 evidence token 畸形**（多 id 挤一格 `D8:6; D9:17`、多冒号 `D:11:26`、前导零、截断 `D`、越界）——官方精确匹配下永不命中 |
| canonical 映射 | `locomo.py:491` turn_id 直接沿用 `dia_id`；evidence 进私有 `GoldAnswerInfo.evidence`（`:244-247`） |
| 一 unit 多 child？ | 否（退化单元素 group）；一题多 evidence 常见（cat 1 多跳 2-4 条） |
| 框架 evaluator 分母 | `locomo_recall.py:202-217` 复刻官方 `hits/len(evidence)`；turn 精确匹配/session 上卷；空 evidence 记 1.0（`:135-137`，与官方一致——LoCoMo 的 1.0 是官方 parity，**不同于** LME 的 1.0 是框架 bug）；k 来自逐题 `retrieval_query_top_k` |
| 公开 artifact 最少保存 | 题干/类别/时间；dia_id evidence 私有。cat 5 adversarial 题 evidence 仍是 dia_id 形态（指向「看似相关」turn），同样私有 |

### 2.4 LongMemEval

| 维度 | 一手事实 |
|---|---|
| 官方 gold 字段 | 双粒度：session 级 `answer_session_ids`（500/500 非空）；turn 级逐 turn `has_answer: bool`（10960/10960 全标注） |
| 指向容器 | turn 级 gold=**只有 user role** 的 has_answer turn：官方 corpus 构建只收 `role=='user'`（`LongMemEval-main/src/retrieval/run_retrieval.py:214`，Fable 亲核），gold doc id=`{sess_id}_{i_turn+1}`（1 基、含 assistant 在内的原始下标），`correct_docs` 按 id 含 `answer` 判（`:272`） |
| 官方分母 | `run_retrieval.py:389-410`（Fable 亲核）聚合时剔除两类：`_abs` 30 题 + 「user 侧无任何 has_answer」51 题 → **分母 419**。Fable 在框架实际使用的 `longmemeval_s_cleaned.json` 上复算：abs=30、非 abs no-user-target=51、全角色无目标=21 且全部是 abs、assistant 侧 has_answer turn=54。**旧断点「30 abs + 21 无目标题」中的 21 实为「任意 role 均无目标」计数（全是 abs 子集），官方剔除口径是 51**，相关表述需随 M1 修正 |
| 官方内部矛盾 | `src/evaluation/print_retrieval_metrics.py:12` 只剔 `_abs`（分母 470），与 run_retrieval.py 的 419 不一致。两条都是官方一手入口；本文按「retrieval 实验主路径 run_retrieval.py 为 canonical、print 脚本为便捷汇总」记录，**parity 口径选哪条由架构师裁**，不代裁 |
| 多 evidence 语义 | 官方同题三口径：`recall_any / recall_all / ndcg_any`（`eval_utils.py:24-29`）；turn→session 上卷 `strip_turn_id`（`:32-46`） |
| canonical 映射（现状） | `longmemeval.py:363` turn_id=`{session_id}:t{turn_index}`（0 基）；`:362-370`（Fable 亲核）`has_answer is True` 即收 gold——**未过滤 role**，54 个 assistant 目标被框架多收；官方剔除的 51 题在框架侧因 assistant 目标而 evidence 非空、照常评分入分母 |
| 框架 evaluator 分母 | `longmemeval_recall.py:103-105` 与 `longmemeval_retrieval_rank.py:156-161` 空 gold 记 1.0——但对真实数据是**死路径**（session gold 恒非空；turn gold 因 role-agnostic 多收也恒非空；21 个真空题全是 abs、在更早 `_abs` 分支已记 n/a）。**真正的分母偏差载体是缺失 no-user-target 剔除**，rank.py:140-143 自注低估了该偏差。`OFFICIAL_K=(1,3,5,10,30,50)`（rank.py:13），`available_k` 按 `k<=top_k` 过滤（`:89`），runner `top_k=10` 写死（`runners/prediction.py:2780`）→ k30/50 结构性缺失 |
| 公开 artifact 最少保存 | 题干/类别/question_time/haystack 公开对话本体；`answer_session_ids`、has_answer 派生 turn id 均私有 |

### 2.5 HaluMem

| 维度 | 一手事实 |
|---|---|
| 官方 gold 字段 | extraction/update gold=`session["memory_points"]`（fact 级；`HaluMem-main/eval/evaluation.py:54,59-63`）；QA gold=`evidence: list[{memory_content, memory_type}]`（仍指 memory point） |
| turn 回指 | **无**（Fable 亲核 schema）：memory_point 键=`{event_source, importance, index, is_update, memory_content, memory_source, memory_type, original_memories, timestamp}`，无任何 dialogue turn/session id 字段；`memory_source` 是来源类别枚举、`event_source` 指向未释出的生成中间结构（UNDETERMINED）、`original_memories` 是 fact 级更新链 |
| 原生 turn 语义 | 原始 `dialogue_turn` 是**一问一答 pair 索引**（0,0,1,1…，Fable 亲核）；框架 canonical turn_id=`{session_id}:t{turn_index}` 单 utterance 1 基（`halumem.py:431`），pair 索引留 metadata（`:436`）——但 **qrel 不指 dialogue_turn**，故该错配不产生 gold 映射问题 |
| 分母 | extraction=逐 session 遍历 memory_points（`halumem_extraction.py:80-100`）；update=is_update 点数（`halumem_update.py:54-56,106-112`）；QA=全部题走 LLM judge（`halumem_qa.py:61,91-97`）。无 retrieval recall 指标 |
| 裁决输入 | turn-level retrieval qrel **诚实 N/A**：数据不存在该标注，禁止从答案/evidence 文本反推 turn 归属喂给 method 或 evaluator |

### 2.6 汇总

| benchmark | gold unit | =canonical Turn? | 拆分后 1 unit 多 child? | 官方多 evidence 语义 | 空 gold 官方处理 |
|---|---|---|---|---|---|
| MemBench | pair 级 step（0 基 int） | 否（FirstAgent） | 是（user+assistant 两 child） | 逐 step 部分给分，分母去重 | 数据孤例（1 题）；官方 scorer 对空 std 会除零，无显式处理 |
| BEAM | 单 message（conversation 内唯一 int id） | 是 | 否 | 官方不评；框架补充指标逐 id 部分给分 | abstention 恒 None；框架记 n/a（正确样板） |
| LoCoMo | 单 utterance dia_id | 是 | 否 | 逐 dia_id 部分给分 | 记 1（官方原生） |
| LongMemEval | user 侧 has_answer turn + gold session | turn 级是（但限 user role） | 否 | any/all/ndcg 三口径 | **整题剔除**（run_retrieval 路径） |
| HaluMem | memory point（fact） | 否（非 turn 概念） | N/A | LLM judge | N/A |

## 3. 四类候选方案对表

评价维度统一为：五 benchmark 表达力 / benchmark 知识是否泄入 method / 协议与 artifact
改动面 / resume-manifest 版本 / 旧产物兼容 / Recall-NDCG-Precision 分母与 rank 语义 /
method adapter 是否被迫特判 / 迁移风险与强反例。

### 3.1 方案 1：gold qrel/evidence group（推荐）

一个官方 gold unit 在 benchmark adapter load 时展开为一组 canonical child turn ids，
作为 evaluator 私有 qrel 存储；evaluator 按「group 内任一 child 命中即该 unit 命中一次」
计分，分母=官方 unit 数。

- **表达力**：五家全覆盖且各自退化优雅——MemBench FirstAgent step→2 元素 group、
  ThirdAgent→1 元素 group；BEAM/LoCoMo/LME turn 级→1 元素 group（现状语义字节级不变）；
  LME session gold→「该 session 全部 turn」的 group 恰好等于官方 turn→session 上卷语义，
  与 spec §5 框架向上聚合原则同构；HaluMem→无 qrel，不建 group，指标 N/A。
- **泄漏**：零。group 只存在于 `GoldAnswerInfo`/evaluator-private label；provider 继续
  只见 canonical turn 流、只报 canonical `source_turn_ids`。
- **协议/artifact 改动**：`RetrievalResult`/`RetrievalEvidence`/`RetrievedItem` **零改动**。
  改动集中在私有链：`GoldAnswerInfo` 增 group 结构 →
  `storage/artifacts.py:39 evaluator_private_label_record` 序列化 → 五个 recall/rank
  evaluator 改读 group。
- **resume/manifest**：私有 label schema 需版本化（见 §4）；预测侧 manifest 严格 `==`
  已保证新旧 run 不混；评测侧需对旧版 label fail-fast。
- **旧产物**：MemBench 旧 artifact 因 canonical turn 数改变本就必须作废重跑；其余四家
  1 元素 group 语义不变，旧 artifact 可经 schema 迁移或声明重评，不产生静默数值漂移。
- **分母/rank 语义**：Recall 分母=去重后官方 unit 数（顺带修复框架 MemBench 不去重的
  口径差）；NDCG 的 group rank=组内 child 的最优（最小）名次，any 口径与官方
  `ndcg_any` 一致；Precision 类在 relevance gold 未证穷尽时维持 N/A（既有裁决不变）。
- **method 特判**：无。
- **强反例/风险**：① group 匹配必须在 `RetrievalEvidence` 资格门之后执行（id 交集不是
  资格，§1）；② LME 的 role 过滤（官方只收 user）必须在 adapter 建 group 时执行，
  否则 54 个 assistant 目标继续污染；③ MemBench 空 target/越界 target 需显式分支
  （空→按 BEAM 样板记 n/a 而非 1.0，越界→unmatched 计数，均需架构师确认口径）。

### 3.2 方案 2：独立 `source_unit_id`（provider 同时报 benchmark-unit id）

- **表达力**：可表达 pair-step，但对 HaluMem（无 unit 概念）与 BEAM（unit=turn，报了
  等于白报）没有增益。
- **泄漏与冗余（主要败因）**：unit 结构要么由 method adapter 认识 benchmark（10 个
  method 特判，违反「method 不做 benchmark 特判」红线），要么由框架把 unit id 塞进
  `TurnEvent.metadata` 让 provider 回声——但框架本来就掌握 turn_id→unit 映射（映射由
  adapter 自己创建，如 `membench.py:709` 公开 `source_step_index`），provider 回声
  **不增加任何信息**，纯冗余契约面；且 method 对内容做变换后，回声 unit id 与回声
  turn id 有完全相同的语义承载缺陷（Mem0 批归属判例），资格问题一点没解决。
- **改动面**：`RetrievedItem` 增字段 + artifact schema + 全部已声明 provenance 的
  method adapter + sidecar 迁移 + contract v1→v2，改动面最大的一档。
- **裁决**：违背 spec §5「细粒度记录、框架向上聚合」的既定架构，**否**。

### 3.3 方案 3：canonical `TurnPair` 升入公共数据模型

- **表达力（主要败因）**：pair 不是通用容器。BEAM 10M 存在真实 user→user adjacency
  （2 处，§2.2）；LoCoMo 是命名 speaker 无 user/assistant 二元；MemBench ThirdAgent
  是单条 observation；LME/BEAM 有 assistant 侧 gold。五家中 gold unit 是 pair 的只有
  MemBench FirstAgent 一家——把单一 benchmark 的容器知识升进 `core/entities.py` 是
  反向污染。
- **改动面**：entities、event_stream、全部 benchmark adapter、全部 provider、artifact、
  resume、既有 pair 聚合语义（user 锚定 + orphan/dangling）全部受累，爆炸半径最大。
- **与 gold 的关系**：即使做了，gold=pair 也只是 MemBench 一家的事实，其余四家仍需
  §3.1 的 group/退化映射——等于花最大代价只解决五分之一问题。
- **裁决**：**否**。pair 继续只作为 `consume_granularity` 的投递选项存在。

### 3.4 方案 4：从 turn-id 前缀解析 parent step

- **碰撞实锤（主要败因）**：LoCoMo canonical turn_id 就是 `D1:3`（自带冒号）；BEAM 是
  `s1:t1`/`p1:s1:t1`（自带一到两个冒号）；LME 是 `{原始 session id}:t{n}`（原始 id 含
  下划线与 hash）。任何分隔符约定都已与现存 id 空间冲突。
- **契约性质**：隐式命名约定不进 manifest/version，adapter 改 id scheme 会静默破坏
  evaluator，且无法表达 BEAM dict 分组、LME session group 这类非前缀语义。
- **裁决**：**否**，不得作为权威判据；充其量在调试输出里当便利显示。

### 3.5 「gold group 私有还是 provider 可见」的明确回答（卡 §5 点名问题）

拆成两件事：**unit 成员结构**（哪些 turn 属于哪个 step/session）是公开信息——它就是
对话结构本身，公开 turn metadata 已携带（`source_step_index`、`session_id`），provider
本来就看得见也不需要更多；**unit 相关性**（哪些 unit 是本题 gold）是私有 qrel，只能落
`GoldAnswerInfo` → evaluator-private label 通道（`storage/artifacts.py:39` 注释明确
该边界）。方案 1 恰好把两者放回各自通道：adapter 用公开结构在 load 时替 evaluator 预
展开 group，provider 全程只报 canonical turn ids，评测时框架在私有侧完成
turn→unit 归组。不存在「provider 需要看 gold 才能建映射」的问题。

## 4. 唯一首选推荐与最小协议草图

**推荐方案 1。**不选 2/3/4 的理由见 §3.2-§3.4 各「主要败因」。以下草图是给架构师的
裁决输入，字段名与版本号均可由架构师改定，本文不改任何现行协议。

私有 qrel 侧（唯一新增结构）：

```
GoldAnswerInfo（或其序列化 label）新增：
  evidence_groups: list[list[str]]   # 每个内层 list = 一个官方 gold unit 的
                                     # canonical child turn ids；单元素为退化情形
  evidence_unit_kind: str            # "step" | "message" | "utterance" |
                                     # "user_turn" | "session"，per-benchmark 声明，
                                     # 供审计与 summary 披露
私有 label schema 版本：evaluator_private_labels 记录（或 manifest）新增
  gold_evidence_schema_version: "v2"；evaluator 读到无版本/旧版本时 fail-fast，
  不做静默兼容。
```

evaluator 侧通用计分规则（五家共享 helper，不再各写一份集合逻辑）：

```
eligible = 逐题 RetrievalEvidence 资格门（M1 契约）通过
hit(group) = any(child in retrieved_source_turn_ids_at_k for child in group)
recall@k  = |{group : hit(group)}| / |groups|          # 分母=官方 unit 数，去重
rank(group) = min(child 首次出现名次)                    # NDCG any 口径
空 groups  = 按 per-benchmark 官方口径显式声明：
  LME → 官方剔除（n/a, reason_code=official_no_target）
  LoCoMo → 官方记 1（parity，保留并披露）
  BEAM/MemBench → n/a（BEAM 现状即样板；MemBench 空 target 孤例由架构师确认）
```

provider/method/公开 artifact 侧：**零改动**。`retrieval_evidence_contract_version`
维持 v1（本方案不动该契约）；若架构师选择把 label 版本挂进同一 version 体系，则升 v2
并按既有 manifest 严格比对 fail-fast。

## 5. 分阶段迁移顺序（依赖序，均需架构师逐段验收）

1. **契约先行**：`GoldAnswerInfo`/private label 增 `evidence_groups` + schema version +
   共享 group 计分 helper；四家非 MemBench adapter 以 1 元素 group 迁移（语义不变，可
   用旧新双跑断言数值恒等）；evaluator 对旧版 label fail-fast。
2. **MemBench canonical split 施工卡**：adapter 拆 FirstAgent step 为两条 turn，gold
   展开为 2 元素 group；强反例见 §6。
3. **LME 官方口径修正**（可并入 M1）：gold turn 过滤 `role=='user'`、实现 51 题
   no-user-target 官方剔除（parity 口径 419 vs 470 由架构师先裁）、k30/50 depth 拆分。
4. **RetrievalEvidence M1**：五 evaluator 改读逐题 evidence 事实 + group qrel，替换
   manifest 级静态门。
LightMem unified-hybrid 卡与本契约正交，可并行推进。

## 6. 对后续施工的可执行交接

**预计修改文件（只列不改）**：

- 生产：`core/entities.py`（GoldAnswerInfo）、`storage/artifacts.py`
  （evaluator_private_label_record）、`benchmark_adapters/membench.py`（拆分 + group）、
  `benchmark_adapters/longmemeval.py`（user role 过滤，:362-370）、其余三家 adapter
  （1 元素 group 迁移）、`evaluators/{membench,locomo,longmemeval,beam}_recall.py`、
  `longmemeval_retrieval_rank.py`、新共享 helper（建议 `evaluators/` 下独立模块）、
  `cli/run_prediction.py`（若 label 版本进 manifest）。
- 测试：`tests/` 下全部断言「1 step = 1 turn」的 MemBench 用例、LME recall/rank 分母
  用例、私有 label schema 用例、四家 group 退化恒等用例。
- 文档：`docs/reference/` 数据模型与 dataset-quirks、method-integration-checklist B5、
  本支线 README 索引；胶囊「30 abs + 21 无目标」表述修正为「30 abs + 51 no-user-target
  （官方剔除口径）；21=任意 role 无目标且全为 abs 子集」。

**schema/version**：必须升级（私有 label v2）；旧 artifact 评测时 fail-fast，报明确
错误指向迁移说明；MemBench 旧 predict artifact 因 canonical turn 数改变整体作废，不做
兼容读取。

**MemBench canonical split 最少强反例**：

- FirstAgent step 拆出 user/assistant 两条 turn，speaker/normalized_role 正确，
  `ps_user`/`ps_agent` 原文与拆分后 content 逐字节一致；
- place/time 原文无损保留，`source_timestamp_embedded_in_content` 标记按侧重算
  （现在 `:717` 的 user-or-agent fallback 需拆开重裁）；
- 无时间 noise 保持 `turn_time=None`；
- **pair gold 分母不翻倍**：多 target 题（如 3 step gold）拆分后 recall 分母仍为 3，
  命中一 step 的任一 child 得 1/3；
- ThirdAgent string step 不被误拆，仍单 turn 单元素 group；
- 越界 target（FirstLow comparative/events tid=4）与空 target（FirstHigh
  highlevel_rec/movie tid=25）显式分支；
- 官方 recall 去重口径对齐（同题重复 target 当前为 0，测试仍需钉死 group 集合语义）。

**BEAM 强反例**：assistant-only gold 题（100K information_extraction）可正常计分；
raw id 跨 conversation 重复必须复合 namespace 隔离；10M 两处 user→user adjacency
（conv `1` 13676→13677、conv `2` 12990→12991）在 pair 聚合下产出 orphan/dangling 而非
静默吞并；abstention `None` evidence 记 n/a 不记 1；dict 三形态展平顺序稳定。

**RetrievalEvidence M1 应读取的运行时事实**：逐题 `retrieval_evidence`
（semantic_provenance/provenance_granularity/stable_ranking，artifact 键见
`runners/prediction.py:2688`）+ `retrieved_items[].source_turn_ids` +
`retrieval_query_top_k` + 私有 `evidence_groups`。必须 N/A/pending 的 metric：NDCG 在
stable_ranking 非 valid 或 depth 不足时 pending；LME k30/50 在 answer/evaluation depth
拆分前 unavailable；HaluMem turn recall 恒 N/A；BEAM recall 永久标注
framework_supplementary；Mem0×BEAM turn recall 维持 n_a（eligibility ruling §4）。

**将因现行错误语义而必须更新的旧测试/文档**：MemBench「一 step 一 turn」全部断言、
`membench_recall` 空 evidence 记 1.0 的期望（若架构师采纳 n/a 口径）、LME recall/rank
的 role-agnostic gold 与无剔除分母期望、rank.py:140-143 低估偏差的自注、
`docs/survey/` 中 MemBench/LME 结构描述。禁止用兼容代码保住上述过时断言。

## 7. UNDETERMINED 与停工判定

- MemBench gold 的 user/agent 侧归属：官方无标注，any-of 是唯一 parity 翻译；侧级
  归属 UNDETERMINED，不得代裁或反推。
- MemBench 官方运行时 step 基数（驱动 runner 未 vendored）：UNDETERMINED，不影响框架
  自建映射。
- HaluMem `event_source` 整数的确切指向（生成中间结构未释出）：UNDETERMINED；释出
  数据无 memory_point→turn 直接字段是确定的。
- BEAM 100K/500K/1M 同 role adjacency 未逐条穷举（既有审计报 0，本轮未重扫）。
- LME 官方两条聚合路径分母冲突（419 vs 470）：两个一手入口均属实，非本卡可消解的
  字段含义冲突——按停工条件记录为**裁决输入**而非停工：建议以 run_retrieval.py 主
  路径为 canonical，最终由架构师拍板。

本卡范围内无需要中止的停工条件命中；以上各项均不阻塞 §5 迁移顺序的裁决。
