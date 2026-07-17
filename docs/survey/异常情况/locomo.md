# LoCoMo Dataset 异常情况与处置账

> 状态：dataset 事实 verified；LightMem caption 差分待回卡强验收；复核日期：2026-07-17
> canonical data：`data/locomo/locomo10.json`
> SHA-256：`79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`
> 官方 source commit：`3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376`

本文记录 LoCoMo 当前 canonical release 的异常与 edge case。字段/规模摘要见
[`datasets/locomo.md`](../datasets/locomo.md)，统一执行语义见
[`workflows/locomo.md`](../workflows/locomo.md)。这里的“行号”仅对应上述 SHA-256 的当前
pretty-printed JSON；长期定位以 `sample_id + qa/session/dia_id` 为准。

## 1. 总览判词

| 编号 | 形态 | 类型 | 框架裁决 | 是否需要 LightMem 特判 |
| --- | --- | --- | --- | :---: |
| L-A1 | `conv-26` 16 个 date-only key | 结构孤儿 | 忽略孤儿日期，不建 phantom session | 否 |
| L-A2 | 140/272 个 odd-turn session | 合法 edge case | 原顺序全保留；不得硬凑 human pair | LoCoMo pair bridge 已处理 |
| L-A3 | 5,882 turn 无独立 timestamp | schema 能力限制 | 每个 turn 继承 session source time | 已处理 |
| L-I1 | 1,226 caption turn；316 caption-without-URL | 文本 method 兼容边界 | raw text 与 `ImageRef` 分存，注入边界统一 wrapper | **是；caption 卡处理中** |
| L-G1 | 9 个 turn-unmatched evidence unit | gold 标注异常 | 不猜修；unmatched 留分母、恒 miss | 否，gold 私有 |
| L-G2 | 1 个重复 evidence occurrence | gold 重复标注 | 按语义 unit 稳定去重并披露官方分叉 | 否，gold 私有 |
| L-G3 | 4 道非局部推理题 evidence 为空 | 官方 metric edge case | 官方兼容 Recall=1，并另报 non-empty 子集 | 否，gold 私有 |
| L-S1 | 当前 release=`img_url`，旧脚本=`img_file` | upstream schema drift | 只读当前 release 字段，不复制旧脚本漂移 | 否 |

## 2. Conversation/session 结构

### L-A1：`conv-26` 有日期、没有对应 session

**真实位置**：`conv-26 / conversation`。实际 list key 只有 `session_1..session_19`，却额外存在
`session_20_date_time..session_35_date_time`；当前 JSON 辅助行约 4,237..4,252，`sample_id` 在
第 5,271 行。

**为什么异常**：正常 schema 是 `session_<n>` list 与 `session_<n>_date_time` 成对存在。后 16
个 key 只有日期、没有 speaker/content，不能代表 16 个空会话，更不能拿来推进 method lifecycle。

**框架处置**：`benchmark_adapters/locomo.py::SESSION_KEY_PATTERN` 只枚举严格匹配
`^session_(\d+)$` 的实际 list key；date-only key 不参与 session 数量、时间继承或 method ingest。
真实数据测试锁定它们与 adapted session numbers 不相交。**不删除 raw key，但不构造 phantom
Session。**

**method 差分**：无。LightMem、Mem0 等只会收到 canonical 19 个 session；不得在 method
adapter 再写 `conv-26` 特判。

### L-A2：大量 session 是奇数 turn

**真实规模**：140/272。代表例：`conv-26/session_2` 有 17 turn（`D2:1..D2:17`），
`session_3` 有 23 turn，`session_8` 有 39 turn。

**为什么异常**：它不是坏数据，而是会击穿“一个 session 总是若干完整 user→assistant round”
的错误假设。LoCoMo 是两个 named human speakers，不是天然的 chat role pair。

**框架处置**：canonical turn 原顺序、原 speaker、原 `dia_id` 全保留。smoke 的 `round` 只是一
个预算单位（两个连续 turn），不改变 canonical 数据。pair-shaped method 必须自己明确结构槽位，
不能丢最后一条，也不能把相邻两个 human speaker 当成产品 API 的 user/assistant 身份。

**LightMem 差分**：每个真实 utterance 独立生成 `[real user, empty assistant]`，named speaker
继续写入 `speaker_id/speaker_name`；因此 odd session 不产生 dangling fact，也不需要补下一个
human turn。

### L-A3：没有 turn-level timestamp

**真实规模**：5,882/5,882 turn 都没有独立时间字段；272/272 个真实 session 都有
`session_<n>_date_time`。

**为什么异常**：这是粒度限制，不是缺失值 bug。框架若从相邻 turn、question time 或 wall
clock 伪造时间，会制造 dataset 没提供的事实。

**框架处置**：每条 canonical turn 的 effective source time 回落到所属 session time；原始
source time 与 method-derived sequence/tie-break time 分开审计。

**LightMem 差分**：真实 message 与同 pair 的空 placeholder 收到相同 source session time。
upstream normalizer 后续产生的 500ms/1,000ms 间隔只能解释为排序时间，不能写成 dataset turn
timestamp。

## 3. 图片/caption 边界

### L-I1：caption-without-URL turn 与旧文本 renderer

**真实规模**：910 个 turn 有 `img_url`，1,226 个有 `blip_caption`，其中 316 个只有 caption、
没有 URL。这里的 `caption-without-URL` 仍可同时带正文；它不是“只有 caption、没有正文”。

**真实例子**：

- `conv-26/session_1/D1:5`（当前 JSON 约第 1,680 行）：同时有 URL、caption、`query` 与正文；
  caption 是 `a photo of a dog walking past ...`。
- `conv-26/session_4/D4:4`（约第 2,011 行）：有 caption 和正文但没有 URL，是
  caption-without-URL 引用的代表。

**为什么是兼容异常**：对文本 memory method，丢掉 caption 会丢公开对话事实；但在 canonical
adapter 提前把 caption 烤进 `Turn.content`，又会破坏结构化图片边界并诱发二次拼接。`query`
是图片检索/生成副产物，不等同 speaker 发言。

**框架处置**：canonical 层保持 `Turn.content=raw text`、`Turn.images[].caption=BLIP caption`；
文本 method 注入边界恰好一次渲染
`[Sharing image that shows: {caption}]`。URL 不下载、不进 content，`query` 不进 method。

**LightMem 差分**：截至本页复核时，caption v6 修复卡正在独立 worktree 施工；验收目标是
legacy/v3 都恢复 `ImageRef` 并调用共享 helper，且 caption 只出现一次。本条在 actor 回卡并经
架构师强验收前仍是 pending，不能因文档已写而标 solved。

## 4. Gold evidence 异常

所有本节字段只在 evaluator-private 通道中存在，**绝不可达 method ingest、retrieve 或 answer
prompt**。

### L-G1：9 个 evidence unit 无法精确映射到 turn

全量 raw evidence token 为 2,815；Phase 1（排除 category 5）为 2,355。下列 9 个全在
Phase 1，均无法 exact-match 到同 conversation 的 canonical `dia_id`：

| sample / qa 零基下标 | 当前 JSON 行 | raw evidence unit | 异常理由 | session view |
| --- | ---: | --- | --- | --- |
| `conv-26 / qa[37]` | 320 | `D8:6; D9:17` | 两个 id 被分号挤进一个 list 元素 | 上卷首 prefix `D8` |
| `conv-42 / qa[58]` | 17,058 | `D10:19` | 格式合法，但该 conversation 无此 turn | 上卷 `D10` |
| `conv-42 / qa[88]` | 17,359 | `D` | 截断，缺 session/turn | `unmatched` |
| `conv-43 / qa[18]` | 24,167 | `D:11:26` | session 位缺失且多冒号 | `unmatched` |
| `conv-47 / qa[38]` | 47,075 | `D4:36` | 格式合法，但该 conversation 无此 turn | 上卷 `D4` |
| `conv-49 / qa[31]` | 54,212 | `D9:1 D4:4 D4:6` | 三个 id 被空格挤进一个元素 | 上卷首 prefix `D9` |
| `conv-49 / qa[38]` | 54,279 | `D22:1 D22:2 D9:10 D9:11` | 四个 id 被挤进一个元素 | 上卷首 prefix `D22` |
| `conv-49 / qa[46]` | 54,355 | `D21:18 D21:22 D11:15 D11:19` | 四个 id 被挤进一个元素 | 上卷首 prefix `D21` |
| `conv-50 / qa[69]` | 60,693 | `D30:05` | 前导零；真实 id 是 `D30:5` | 上卷 `D30` |

**框架处置与理由**：不把分号/空格猜拆，不把前导零猜改，也不静默删除。官方 turn-context
scorer 对每个 raw list 元素做 exact match；擅自修复会凭主观改变 gold unit 和分母。Gold
Evidence Group v1 按稳定去重后的 raw 值建 unit：turn view 全部标 `unmatched`、永远 miss 但
保留分母；session view 复刻官方 `ev.split(':')[0]` 上卷，所以只有 `D` 与 `D:11:26` 仍
unmatched。

按现行 turn group 口径，即便其它 unit 全命中，Phase 1 overall recall 理论上限仍只有
`0.996134817563389`；报告必须把该上限与 method 漏检区分。

### L-G2：同一 evidence occurrence 重复

**真实位置**：`conv-50 / qa[5]`，问题 `What are Dave's dreams?`，当前 JSON 第 60,120 行；
raw evidence（60,123..60,125 行）是 `['D4:5', 'D4:5', 'D5:5']`。

**为什么异常**：同一个 utterance 被写两次并没有产生第二个语义证据单位；官方 raw scorer
却会在分子/分母中对它双重计权。

**框架处置**：Gold Evidence Group v1 按首次出现稳定去重，因此 Phase 1 是 2,355 raw tokens
→ 2,354 group units。这是有意的 framework normalization；结果不得标成与官方 raw scorer
分母逐字节 parity。没有 method 特判。

### L-G3：4 道有答案但 evidence 为空的 category-3 题

| 位置 | 当前 JSON 行 | 问题 | gold answer |
| --- | ---: | --- | --- |
| `conv-26 / qa[30]` | 259 | Would Melanie be considered a member of the LGBTQ community? | Likely no... |
| `conv-26 / qa[46]` | 401 | Would Melanie be considered an ally to the transgender community? | Yes, she is supportive |
| `conv-50 / qa[39]` | 60,424 | Would Dave prefer working on a Dodge Charger or a Subaru Forester? | Dodge Charger |
| `conv-50 / qa[42]` | 60,448 | Did Calvin and Dave have a Boston meeting in the given interval? | No |

**为什么异常**：这些是 commonsense/推理类问题，答案存在，但 turn-level retrieval qrel 为空；
它们不能证明“检索到了正确证据”。这更像官方 metric 的 edge case，而非 adapter 漏读。

**框架处置**：复刻官方 `evaluation.py` 行为，空 evidence 的 overall recall 记 1.0；同时必须
报告 `empty_evidence_question_count` 与 non-empty-evidence mean，避免把这四个 1.0 解读为
真实检索成功。gold 不进入 method，因此所有 method 都无特判。

## 5. Upstream schema drift

当前 release 使用 `img_url`；官方旧统计脚本还残留 `img_file`。框架以 source-locked JSON 为
准读取 `img_url + blip_caption`，不为了让旧脚本计数对齐而制造 `img_file` fallback。若 dataset
hash 或官方 release 改变，必须重新统计后更新本页。

## 6. Method 差分矩阵

| 异常面 | canonical/evaluator 已吸收 | LightMem | 其余 method |
| --- | --- | --- | --- |
| date-only / odd session | 是 | named-speaker 单 utterance pair 已审计 | 到站时只验证消费粒度，不复制数据特判 |
| session-only timestamp | canonical 提供 source fallback | placeholder/sequence 差分已披露 | 到站时检查 typed timestamp 或 content fallback |
| caption | canonical 只保留结构，不能替 method 渲染 | v6 卡施工中，待强验收 | Mem0 已知裸拼债；其它 method 到站逐一核 |
| malformed/duplicate/empty gold | evaluator-private 完全吸收 | 无特判、不可见 gold | 全部无特判、不可见 gold |

“到站时检查”不是默认通过；只表示异常事实不再重复调查，method 的实际 payload 仍要各自做
强反例。

## 7. 回归锚与失效条件

- `tests/test_locomo_conversation_adapter.py` 锁定 16 个 date-only key、140 odd session、图片
  计数、2,355 raw → 2,354 group units、9 个 turn-unmatched 与 2 个 session-unmatched。
- `tests/test_locomo_retrieval_recall.py` 锁定 empty evidence=1 + non-empty 单报，以及 unmatched
  留在分母且恒 miss。
- `tests/test_image_text.py` 锁定共享 wrapper、caption-without-URL 与 query 不入文本。
- source identity、Gold Evidence Contract、caption renderer、smoke crop policy 任一改变时，
  必须重开本页；仅 actor 回报“测试绿”不能自动改状态。
