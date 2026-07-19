# BEAM Dataset 异常情况与处置账

> 状态：dataset 事实已由架构师复核；LightMem pair 差量已强验收，100K/10M current-v7
> 真实 B11 待跑；复核日期：2026-07-19
> canonical data：`data/BEAM/beam_dataset/{100K,500K,1M}` 与
> `data/BEAM/beam_10M_dataset/10M`
> 数据身份：[`beam-source-lock.json`](../../workstreams/ws02.6-first-smoke-hardening/notes/beam-source-lock.json)

本文记录当前 source-locked BEAM 数据的异常、合法 edge case 与框架处置。schema 摘要见
[`datasets/BEAM.md`](../datasets/BEAM.md)，运行流程见
[`workflows/BEAM.md`](../workflows/BEAM.md)。2026-07-19 现场重算五个 Arrow shard 的 SHA-256，
与 source lock 全部一致；数据身份变化后，本页计数自动失效。

## 1. 总览判词

| 编号 | 形态 | 类型 | 规模 | 框架裁决 | LightMem 差分 |
| --- | --- | --- | ---: | --- | --- |
| B-S1 | 100K/500K/1M 严格 user→assistant 交替 | 正常 schema | 790 sessions / 118,420 turns | 保持官方顺序与 role | `consume_granularity=pair`，每两条一次真实双边 add |
| B-I1 | 1M 四个 conversation 的 raw `id` 在后续 session 从 0 重启 | 身份异常 | 1,720 个重复 raw id | public id 用 positional namespace；私有 gold group 一 raw id 对多 child | 不按 raw id 建隔离或 lineage |
| B-G1 | 10M 一个 `source_chat_ids` 原子为 `'--'` | malformed private gold | 1 | unmatched group，留痕；不猜修 | gold 不可达 method |
| B-R1 | 10M 两个 turn group 以 follow-up user 悬空，下一 group 又从 user 开始 | 真实 role adjacency 异常 | 2 / 77,569 groups | 两条 user 都保留，不能跨组错配 | 前 user 为 dangling singleton；后 user 开新 pair，各自补结构 placeholder |
| B-C1 | 其中一处下一组 assistant 明显回答上一组悬空问题 | 语义错位/源数据噪声 | 1 | 原文原序保留，不替 upstream 搬答案 | 按 raw role/pair 注入，不做内容猜配 |
| B-T1 | 10M 一个完整 batch 无任何 `time_anchor` | 合法缺时 edge case | 1 / 1,000 sessions | `session_time=None`、turn time 全 None | `preserve_none`，不造时间 |
| B-T2 | 10M 按官方 plan→batch 顺序有相邻 session anchor 回退 | 跨 session 时间线不单调 | 5 | 不全局排序/修钟；每个 batch 是独立 canonical session | pair 内只用本 session anchor |
| B-N1 | 10M `index` 重复、跳号、回访 | 非 identity 字段；owner 语义未完全说明 | 常见 | 只作 metadata；identity 用 positional turn id | 无 method 特判 |

## 2. 标准三 split：结构干净，但 raw id 不是永远唯一

### B-S1：100K / 500K / 1M role 形状

独立全量扫描结果：

| split | conversations | sessions | turns | 奇数 session | 非 user 开头 | 非 assistant 收尾 | 相邻同 role |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100K | 20 | 90 | 5,732 | 0 | 0 | 0 | 0 |
| 500K | 35 | 350 | 38,058 | 0 | 0 | 0 | 0 |
| 1M | 35 | 350 | 74,630 | 0 | 0 | 0 | 0 |

这三格确实是严格 `user, assistant, user, assistant, ...`，不是靠 placeholder 才跑通。
LightMem 原先注册为 `turn` 会把每个天然 pair 拆成两次人工单边 pair；现改为 `pair`，正常形态
一次投递两个真实 slot，不增加或删除 content。

### B-I1：1M raw id 在四个 conversation 中重启

四处稳定位置（row 为 0 基；括号内为 `conversation_id`）：

| row / conversation | 重复的 distinct raw ids | raw id 范围 |
| --- | ---: | --- |
| 4 / `5` | 150 | 0–149 |
| 25 / `26` | 424 | 0–423 |
| 32 / `33` | 206 | 0–205 |
| 33 / `34` | 940 | 0–939 |

共 1,720 个 distinct raw id 各出现两次。raw `id` 因此只能是 source locator，不能充当
conversation 内唯一 public turn id。adapter 已用 `{session_id}:t{turn_index}`（10M 为
`pN:sM:tK`）建立 positional namespace；私有 qrel 把一个歧义 raw id 展开成 multi-child
any-of group。当前 1M 为 41 个受影响问题、逐题累计 198 个歧义原子。用户曾建议的
`session序号:turn序号` 与现行方案同构，无需为缩短字符串重命名既有 identity。

## 3. 10M role 与 content 异常

10M 共 10 conversations × 10 plans × 10 batches = **1,000 canonical sessions**，原始
`turns` 下有 **77,569 groups / 208,696 messages**。77,567 groups 为偶数；只有下面两组是
`user→assistant→user` 三条，因最后 follow-up 无回复，和下一组首 user 形成两处
user→user adjacency。

### B-R1a：conversation `1` 的悬空 follow-up

稳定位置：`conversation_id=1 / plan-7 / batch 10 / group 19`：

```text
id=13674 user      main_question     incremental refactoring / system resilience
id=13675 assistant                   回答该 main question
id=13676 user      followup_question "...set up dynamic weights for load balancing?"
```

紧接 `group 20` 从 `id=13677 user` 的 Keycloak 新话题开始，`id=13678 assistant` 正常回答
Keycloak；因此 13676 是单纯缺回复，没有证据允许框架把 13678 搬回来。

### B-R1b / B-C1：conversation `2` 的悬空 follow-up + 下一槽答案错位

稳定位置：`conversation_id=2 / plan-7 / batch 8 / group 51→52`：

```text
id=12988 user      test dashboard refresh lag
id=12989 assistant 回答开头提到 Batch Updates，但正文中途结束
id=12990 user      "...implement batch updates in my current setup?"（悬空）
id=12991 user      全新的 CARLA v0.9.27 regression 话题
id=12992 assistant "To enhance your test dashboards... Batch Updates..."
```

12992 的主题与措辞明显延续 12990，而不是回答 12991。架构师裁决为**源数据语义错位噪声**，
不是 role parser 问题；当前 20 个 probing questions 的 `source_chat_ids` 没有引用
12990/12991/12992，故它不是已知 gold 定位器，但仍可能作为 haystack noise 影响记忆抽取。

**统一处置**：不修改 Arrow、不把 12992 移到 12990、不按内容猜 role。canonical adapter 按
官方顺序展平；pair aggregator 在 12991 到来时先把 12990 发成 dangling singleton，再以
12991 开新 pair、让 12992 按 raw role 闭合。这样既不吞消息，也不把两个 user 互配。

## 4. 时间与索引

### B-T1：唯一全缺时 session

稳定位置：`conversation_id=7 / plan-1 / batch 1`，93 groups / 244 messages，raw id 0–243；
所有 message 的 `time_anchor=None`。adapter 不从相邻 batch、question、wall clock 或 raw id
合成时间，整个 `p1:s1` 的 `session_time` 与 turn time 均为 None。LightMem
`online_soft + missing_timestamp_policy=preserve_none` 原样接收；该路径已有双边 None 强反例，
真实 10M B11 只负责验证 backend/API 组合链。

### B-T2：相邻 canonical session 的 anchor 并非全局单调

按官方 `chat[i]['plan-i']`、再按 batch 顺序展开，忽略唯一缺时 session后，现场得到 5 个
相邻 anchor 回退；先前只读报告的“2 处”是漏计，不能进入稳定文档：

| conversation | 前 session / raw id / anchor | 后 session / raw id / anchor |
| --- | --- | --- |
| `1` | `p7:s10` / 13602 / 2025-02-28 | `p8:s1` / 13775 / 2025-02-15 |
| `3` | `p1:s1` / 0 / 2024-07-15 | `p1:s2` / 168 / 2024-07-02 |
| `4` | `p7:s10` / 12618 / 2025-03-28 | `p8:s1` / 12916 / 2025-03-15 |
| `5` | `p1:s1` / 0 / 2025-03-31 | `p1:s2` / 160 / 2024-07-02 |
| `5` | `p7:s10` / 12692 / 2025-03-24 | `p8:s1` / 12908 / 2025-03-15 |

这证明“整个 10M conversation 的 session time 严格递增”是假设，不证明哪个日期应被改写。
框架把每个 batch 作为独立 session，保留 source order 与 source anchor；不跨 session 排序、修钟
或借后一个时刻覆盖前一个。需要全局时间推理时，这种矛盾属于 benchmark noise，报告披露即可。

### B-N1：`index` 不是 identity

`index` 可出现 `1,2 → 1,3 → 1,2 → 1,4` 式回访，且 assistant/follow-up 常为 None。
当前 owner 文档不足以把它正式命名为“话题 id”，所以不把“作者有意设计”写成已证事实；但可以
确定它**不具备唯一、连续、单调 identity 契约**。adapter 只将其保留在 metadata，public
identity 与 gold 映射均不依赖它，因此无代码修复。

## 5. Evaluator-private gold 异常

### B-G1：非法 `'--'` evidence 原子

稳定位置：10M row 5（`conversation_id=6`）/
`probing_questions.event_ordering[0].source_chat_ids[6][0]`。全库 10,534 个 evidence 原子仅此
一个非整数。框架不猜它指向哪条消息：建立 unmatched group、记录 unmatched count；gold 仍在
evaluator-private artifact，不可达 ingest/retrieve/answer prompt。

BEAM 官方 evaluation 根本不消费 `source_chat_ids`，因此框架 `beam-recall` 只能标
`framework_supplementary`。对 LightMem 而言，pair-level lineage 不能证明 single-message gold
仍被当前 memory 精确承载，所以逐题 RetrievalEvidence 保持
`n_a / beam_gold_is_single_message / provenance_granularity=none`，不能为了填矩阵硬算 Recall。

## 6. LightMem 差量与覆盖边界

LightMem × BEAM 的现行稳定契约：

- registry resolver 返回 `consume_granularity="pair"`；该 concrete 值进入 manifest/resume，
  旧 `turn` run 不兼容，但 adapter version 保持 `conversation-qa-v7`；
- 标准三 split 的每个 user→assistant 一次进入 backend，两个真实 child 共用 pair candidate ids；
- 10M dangling user、assistant-first 或连续同 role 都逐条保留，以 structural placeholder 补缺侧，
  不跨 session 配对；placeholder 不冒充第二个 source fact；
- 有 `time_anchor` 的 turn 只取本 session source anchor；全缺时保持 None；question/gold 不反灌；
- raw content mismatch 不由 method adapter 猜修；错误答案仍按官方 raw assistant role 注入；
- BEAM Recall/NDCG 保持 N/A，真实 smoke 不以检索分数作为通过门。

强验收锚：主线 `de40d63`（actor 原提交 `ff8dfc5`）只把 BEAM 加进 resolver 的 pair 集合；
`tests/test_lightmem_adapter.py` 走 production event stream 锁正常 pair、positional id、连续 user、
跨 session orphan/dangling 与双 None；`tests/test_event_stream.py` 和通用 normalizer 另锁
assistant-first、连续 assistant 等数据外防御形态。架构师定向复跑为
`330 passed, 1 warning`；合流定向为 `428 passed, 1 warning`，主树全量为
`1588 passed, 3 deselected, 2 warnings, 29 subtests passed`，compileall exit 0。

真实 B11 仍须分别跑 100K 与 10M，因为二者结构/时间面不同；但不要求付费 smoke 恰好抽中
13676/12990 或 1M 重复 id。稀有事实由全量 census + deterministic contract test 锁定；真实
smoke 只验证当前 runtime/backend/API/artifact 链，不承担随机异常抽样。

## 7. 失效条件

以下任一变化都必须重开本页：BEAM Arrow shard/source lock 变化；10M plan/batch 展开顺序变化；
public positional id 或 Gold Evidence Group 合同变化；pair aggregator 的 orphan/dangling 规则变化；
LightMem missing-time、lineage 或 RetrievalEvidence 资格变化。只改 answer-level metric、TOML 效果
超参数或别的 method，不自动重开 BEAM dataset census。
