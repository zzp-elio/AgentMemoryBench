# LongMemEval 数据异常与边界账（source-locked）

> 状态：**verified（2026-07-19）**。本页是当前 `_cleaned` S/M 数据的稳定异常账；完整探针、
> 计数 stdout、草稿逐条裁决与架构师 R1 勘误保留在
> [`longmemeval-anomaly-ledger-audit.md`](../../workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/longmemeval-anomaly-ledger-audit.md)。
> 原 OpenCode 初扫已原封不动保存在同目录未跟踪草稿
> `longmemeval-opencode-draft-20260719.md`，不得把其中未经证实的自然语言根因当成现行契约。

## 1. 数据身份与适用范围

| variant | canonical path | bytes | SHA-256 |
| --- | --- | ---: | --- |
| S | `data/longmemeval/longmemeval_s_cleaned.json` | 277,383,467 | `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442` |
| M | `data/longmemeval/longmemeval_m_cleaned.json` | 2,737,100,077 | `9d79e5524794a2e6900a3aa9cb7d9152c5a3e8319c9a87c25494ba1eacee495f` |

身份源：
[`longmemeval-source-lock.json`](../../workstreams/ws02.6-first-smoke-hardening/notes/longmemeval-source-lock.json)。
两份 hash 已由 actor 与架构师分别重算一致。当前本地官方源码快照没有可独立验证的 git commit；
这条 provenance 仍是 pending，不能用父仓 `git rev-parse` 猜 commit。

S/M 都有 500 个相同 `question_id`，问题文本、question type 与 answer 逐题相同。M 主要增加
distractor history；两 variant 的 `answer_session_ids` 每题集合相同，但有 **124 题列表顺序不同**。
因此 evaluator gold 语义等价，raw JSON 不能称为 byte-identical，也不得为了“统一”而排序回写。

## 2. 异常分类总表

本页区分：

- `LEGAL_EDGE`：schema 允许、无需修数据；
- `SOURCE_HETEROGENEITY`：混合来源形成的合法异形；
- `CAPABILITY_LIMIT`：gold 不足以支持某 metric，不是数据错误；
- `UNRESOLVED`：形状存在，但自然语言根因无上游证据；
- `TRUE_DATA_ERROR`：只有一手上游证据足够时才使用；当前没有需要框架猜修的此类项。

| 项 | S | M | 分类 | canonical 处置 |
| --- | ---: | ---: | --- | --- |
| JSON `int` answer | 32 | 32 | LEGAL_EDGE | evaluator-private `_answer_to_text()` 做确定性 `str()`；不进 method |
| 带 `$`/逗号的金额 answer | 31 | 31 | LEGAL_EDGE | 字符串原样保留，不剥符号/单位 |
| `question_date < earliest history` | 1 | 0 | LEGAL_EDGE / raw ordering artifact | 原样保留；不删除 history、不造 corrected time |
| `question_date < latest history` | 76 | 118 | LEGAL_EDGE / raw ordering artifact | 原样保留；retrieve 不做 as-of cutoff |
| gold session 晚于 question | 44 | 42 | LEGAL_EDGE / raw ordering artifact | 不过滤 gold/history，不改原始时间 |
| `gpt4_` question id | 107 | 107 | SOURCE_HETEROGENEITY | id 原样保留；全局重复 0 |
| answer-session id 前缀族 | 892 / 25 / 31 | 同 S | SOURCE_HETEROGENEITY | 原样映射；缺引用 0 |
| S/M answer-session 顺序差 | 124 题 | 124 题 | LEGAL_EDGE | 保留各 variant 原序；集合相同，group 计分顺序无关 |
| blank turn | 12 | 295 | SOURCE_HETEROGENEITY | 空白 canonical turn 跳过并计数；若是 target，private group 记 unmatched |
| 相邻同 role occurrence | 32 / 14 records | 411 / 114 records | SOURCE_HETEROGENEITY | 结构化 role 原样保留；不从 content 猜角色 |
| pure-assistant session | 71（其中单条 65） | 609（其中单条 567） | SOURCE_HETEROGENEITY | 非空 turn 全保留 |
| pure-user session | 1 | 7 | SOURCE_HETEROGENEITY | 非空 turn 全保留 |
| assistant-first session | 1,942 | 19,431 | SOURCE_HETEROGENEITY | 顺序原样保留 |
| instance 内重复 haystack session id | 13 个额外 occurrence | 1,182 个额外 occurrence，涉及 449 records | LEGAL_EDGE | 第 2+ 次加稳定 `#occurrence_N`；不丢 session |
| assistant-side `has_answer=True` | 54 | 54 | CAPABILITY_LIMIT / official contract | 不进入官方 user-turn retrieval gold |
| evidence 无法证明 LightMem pair 内具体 child | 全部 | 全部 | CAPABILITY_LIMIT | LightMem Recall/rank=`N/A`，不强算 |

不同 note 的“same-role”数字可能不同，先看单位：本表是所有 session 的 adjacency occurrence 与
record 数；旧 input-time audit 的 `consecutive-same` 是互斥 session-shape 分类，assistant-first
或 pure-assistant 已先分桶，不能直接对比。

## 3. 可复核例子与裁决

### 3.1 时间顺序

- `S / question_id=gpt4_2f56ae70`：`question_date=2023/05/26 00:18`，最早 history 为
  `2023/05/26 00:47`，相差 29 分钟。
- S 中另有 76 题 question clock 早于最新 history，且都发生在同一个 calendar day；M 为 118。

这些字段是真实 raw artifact，不是框架可以擅自修正的数据。现行裁决是：

1. adapter 保留数据集原始 session/question time；
2. history 按官方主路径全部交付，不做 `date > question_date` 过滤；
3. question time 只进入 benchmark answer builder 的公开槽；
4. method retrieve 明确 `filters=None`；
5. 不用相邻 session、首个有时 turn、wall clock 或人工“紧接最后 session”时间覆盖 raw JSON。

历史 issue 只能解释旧标注意图，不能覆盖当前 source-locked cleaned 文件。若 owner 发布新数据，
先换 source lock，再重验本节。

### 3.2 role/content 异形

稳定语义坐标例子：

- `S / f8c5f88b / session[0]`：开头有相邻 assistant turns；
- `S / gpt4_2ba83207 / session[34]`：content 内含 `User/Assistant/System` 字样，但结构化 role
  仍是 assistant；
- `S / 352ab8bd / session[24]`：3 条 pure-user turns。

形状存在是已验证事实；“角色错标”“截断 split”“角色扮演残留”只是从 content 推测的根因，
没有 upstream script/changelog 证明，统一记 `UNRESOLVED`。框架必须信结构化 `role`，不能看到
content 像 user 就把 assistant 改写成 user。

### 3.3 id 与引用

- 全局 duplicate question id：0；未知 question type：0；未知结构化 role：0；核心字段缺失：0。
- `answer_session_ids` 有 `answer_`、`answer_sharegpt_`、`answer_ultrachat_` 三个来源族，但每个
  id 都能在本 record 的 haystack session id 中找到，missing reference=0。
- S/M 有 124 题只改变 answer-session id 列表排列，长度与集合不变；例如
  `00ca467f` 的 S 顺序为 `_3,_2,_1`，M 为 `_1,_2,_3`。这是 raw 顺序差异，不是 gold 集合变化。
- duplicate haystack session id 不能用 dict 覆盖。`_unique_session_id()` 保留第一次原 id，
  后续加 `#occurrence_N`；一个 answer-session id 映射到该 original id 的**全部**公开 occurrence。

## 4. canonical / private / evaluator 三层处置

### 4.1 canonical public 层

- 每个 evaluation instance 是独立 `Conversation`；question id 同时提供 conversation namespace。
- 三个 haystack parallel list 长度不一致时 fail-fast。
- 非空 turn 保持原 role/content/session date；blank turn 跳过并计入 metadata。
- 重复 session id 稳定 suffix，不删除、不合并、不跨 record 复用 public identity。
- answer、answer_session_ids、has_answer、gold/evidence、judge label 不得进入公开 Turn、method
  message、retrieve query 或 answer prompt。

### 4.2 evaluator-private gold 层

- int answer 只在 private `GoldAnswerInfo.answer` 入口转字符串；字符串 answer 只 `strip()`。
- turn view 只取官方 `role=='user' and has_answer=True`；blank target 记 unmatched，不删分母。
- session view 一个官方 answer-session id 对应一个 group；duplicate original id 的所有 public
  occurrence 都是 child；找不到时记 unmatched。
- 官方主 retrieval 分母：500 − 30 abstention − 51 no-user-target = **419**。辅助脚本的 470
  分母冲突只披露，不替换主路径。

### 4.3 metric 资格

assistant-side target 不进入官方 user-only corpus；这不是框架应偷偷补进 Recall 分母的遗漏。
provider 还必须逐题证明 semantic provenance 与 stable ranking。没有资格时输出 N/A，而不是 0。

## 5. LightMem current-v7 差分

LongMemEval benchmark 异常由 shared canonical/private 层吸收；LightMem 只承担自己的接口差量：

1. registered consume granularity=`pair`，主 profile=`messages_use="hybrid"`、
   `lifecycle_profile="online_soft"`；官方 Table 2 的 user-only 属未来 author calibration。
2. 正常 `user→assistant` 是 real-real pair；assistant-first、same-role、pure-user/pure-assistant 等
   orphan/dangling slot 补结构 placeholder，绝不跨 session 配对。每个 retained real turn 恰一次。
3. LongMemEval 没有 turn-level time；真实 message 只继承所属 session raw time。LightMem 对相同
   timestamp 的 slot 产生 500ms method-derived tie-break，这不是 source time，报告必须区分。
4. question time 只进 answer builder；retrieve 使用 `filters=None`，不会裁掉 future-looking history。
5. online-soft 只做抽取后 direct insert；不运行全库 offline consolidation。
6. extraction source id 是 pair candidate，不能证明 memory 来自 pair 内 user 还是 assistant；
   RetrievalEvidence 固定 `n_a / pair_source_id_not_turn_exact / none`，Recall 与 rank summary 为 N/A。
7. current-v7 LoCoMo/LME 真实 W1/W2 已开箱；本页只证明输入异常处置，不把 smoke 结果写成 full、
   效果或成本认证。

详细映射与时间探针：
[`lightmem-longmemeval-input-time-audit.md`](../../workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/lightmem-longmemeval-input-time-audit.md)。

## 6. 回归锚与重开条件

主要回归：

- `tests/test_longmemeval_conversation_adapter.py`：双 variant、blank、duplicate session mapping、
  private group、419 分母；
- `tests/test_lightmem_adapter.py`：六类 role/pair、placeholder、time、online-soft、N/A evidence；
- `tests/test_longmemeval_retrieval_recall.py` 与
  `tests/test_longmemeval_retrieval_rank.py`：group 计分、N/A 与 summary；
- source identity：`longmemeval-source-lock.json`。

只在以下任一条件发生时重开本账：

1. S/M hash、字节数或官方 cleaned release 改变；
2. canonical role/blank/session-id、Gold Evidence Group、answer builder 或 retrieval evaluator
   contract 改版；
3. owner 提供能把某个 `UNRESOLVED` 根因升级为 TRUE_DATA_ERROR 的一手证据；
4. 新 method 的接口差量无法由本页 shared 处置吸收。第 4 项通常只重开该 method integration，
   不自动重扫 LongMemEval 数据。
