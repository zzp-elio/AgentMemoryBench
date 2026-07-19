# LongMemEval source-locked 异常账审计（R1）

> 取证 actor 交付（只读离线、零 API、零 dataset 改动）。唯一新增文件即本 note。
> 目标：把主工作区未跟踪草稿 `docs/survey/异常情况/longmemeval.md`（OpenCode 初扫）
> 的每条“异常”逐条证伪/证实，给 source-locked S/M census + 分类 + 框架/LightMem 处置，
> 供架构师验收后自行回填稳定异常账。**本 note 不改草稿、不改 README/三联页/src/tests/
> configs/third_party/data/outputs/policy/handbook。** 裁决权在架构师。

## 0. 基线与来源身份

| 项 | 值 |
|---|---|
| 审计日期 | 2026-07-19 |
| worktree | `/Users/wz/Desktop/mb-actor-longmemeval-anomaly-ledger`（branch `actor/longmemeval-anomaly-ledger-r1`） |
| 基线 HEAD | `e5ca5c4`（主树同一 commit；开工 `git status --short` 仅未跟踪主树草稿/PDF，worktree 内 `data/`、`third_party/benchmarks/` 为指向主树的只读软链） |
| 执行模型 / 入口 | Claude Opus 4.8（`claude-opus-4-8`，本会话系统提示），Claude Code CLI；无 subagent 分包，全部结论由主 actor 承重 |
| S 数据 | `data/longmemeval/longmemeval_s_cleaned.json`，277,383,467 bytes，**SHA-256 现算 `d6f21ea9…c3a442`**，与 source-lock.json 锁定值逐字一致 ✅ |
| M 数据 | `data/longmemeval/longmemeval_m_cleaned.json`，2,737,100,077 bytes，**SHA-256 现算 `9d79e552…ee495f`**，与 source-lock.json 锁定值逐字一致 ✅ |
| source lock | `docs/workstreams/ws02.6-first-smoke-hardening/notes/longmemeval-source-lock.json`（official repo/paper/HF/license；`_cleaned` 为 2025-09 re-cleanup，替换原始 release） |
| 官方源码快照 | `third_party/benchmarks/LongMemEval-main/`（无独立 git provenance，见 source lock；引用行号为该快照内） |

两文件 SHA-256 逐字复核通过，未触发 §6 停工条件。数据未入 git，探针直接读软链后的主树
绝对路径；提交前确认无软链/临时脚本被暂存（见 §8）。

## 1. 事实优先级与依赖的已强验收事实

固定优先级：**当前锁定数据/官方源码 > current framework source > 已强验收 notes > 稳定
survey 页 > 未验收草稿**。本 note 把草稿只当“待逐条证伪的候选清单”。

依赖以下已由 Opus 4.8 主体 + 架构师 R1 强验收的差分事实（同目录
`lightmem-longmemeval-input-time-audit.md` §1/§2/§4/§6/§8，`…-latest-main-preflight.md`
§1/§2）。本审计对其 S/M census **独立重算**并全部复现，未发现矛盾：

- raw turn S/M = 246,750 / 2,446,993；blank turn 12 / 295；每 retained canonical turn 恰进
  一个 pair 一次。
- q<latest 76 / 118（全同日 HH:MM 错序）、q<earliest 1 / 0、future-gold 44 / 42。
- 官方 LightMem harness（reproduction 口径）丢 2,020 / 20,283 raw turn，含 3+3 个
  answer-session assistant `has_answer=True`；unified hybrid 改用 1,986 / 20,126 placeholder
  pair 保住全部 retained turn。
- LightMem LME retrieval semantic = `n_a / pair_source_id_not_turn_exact`。

## 2. 探针复现法与关键 stdout（自包含）

一手扫描脚本（scratchpad 临时产物，**不入库**）：`lme_anomaly_scan.py`（公开 shape +
私有字段仅计数/引用完整性）、`lme_date_check.py`（q<earliest / q<latest 同日错序）。二者用
`ijson.items(handle, "item")` 流式，`_m` 禁 `json.load`。构造逻辑复刻自
`benchmark_adapters/longmemeval.py`（blank = `content`/`text` 键存在但 strip 后为空；role 取
结构化 `role` 字段；session id 去重口径 = adapter `_unique_session_id`）。私有字段
（`answer` / `answer_session_ids` / `has_answer`）**仅用于计数与引用完整性**，从不打印 gold
内容。可复算命令：

```bash
uv run python <scratchpad>/lme_anomaly_scan.py data/longmemeval/longmemeval_s_cleaned.json S
uv run python <scratchpad>/lme_anomaly_scan.py data/longmemeval/longmemeval_m_cleaned.json M
uv run python <scratchpad>/lme_date_check.py   data/longmemeval/longmemeval_s_cleaned.json S
```

### 2.1 S census（关键 stdout 原样节录）

```
instances: 500
answer_types: {'str': 468, 'int': 32}
  int by qtype: {'multi-session': 22, 'temporal-reasoning': 8, 'knowledge-update': 2}
dollar_answer_count: 31
gpt4_ prefix count: 107   gpt4 by qtype: {'multi-session': 18, 'temporal-reasoning': 89}
qtype_values: {'single-session-user': 70, 'multi-session': 133, 'single-session-preference': 30,
               'temporal-reasoning': 133, 'knowledge-update': 78, 'single-session-assistant': 56}
abstention(_abs) count: 30; gpt4&abs: 5
asid_prefix_families: {'answer_': 892, 'answer_sharegpt_': 25, 'answer_ultrachat_': 31}
asid_missing_ref: 0 across 0 records
dup haystack_session_id: 13 dupes across 13 records
duplicate question_ids (global): 0
role_values: {'user': 122416, 'assistant': 124334}
unknown_roles: {}
blank_turns: 12; blank_sessions: 7
pure_assistant_session_count: 71
single_assistant(1-turn) session_count: 65
pure_user_session_count: 1   examples: [('352ab8bd', 24, 3)]
assistant_first_session_count: 1942
same_role_adjacency occurrences: 32 (uu=24, aa=8)   records_with_same_role: 14
has_answer user-target turns: 842; assistant-target turns: 54
missing_core_field_records: 0   turn_extra_keys: {}
```
```
[S] q<earliest count=1 ids=[('gpt4_2f56ae70','2023/05/26 (Fri) 00:18','2023/05/26 (Fri) 00:47')]
[S] q<latest count=76; of which same-calendar-day-as-latest=76
```

### 2.2 M census（关键 stdout 原样节录）

```
instances: 500
answer_types: {'str': 468, 'int': 32}   int by qtype: {'multi-session':22,'temporal-reasoning':8,'knowledge-update':2}
dollar_answer_count: 31
gpt4_ prefix count: 107   gpt4 by qtype: {'temporal-reasoning': 89, 'multi-session': 18}
qtype_values: {same 6 types, identical counts to S}
abstention(_abs) count: 30; gpt4&abs: 5
asid_prefix_families: {'answer_sharegpt_': 25, 'answer_ultrachat_': 31, 'answer_': 892}
asid_missing_ref: 0 across 0 records
dup haystack_session_id: 1182 dupes across 449 records
duplicate question_ids (global): 0
role_values: {'user': 1213940, 'assistant': 1233053}
unknown_roles: {}
blank_turns: 295; blank_sessions: 91
pure_assistant_session_count: 609
single_assistant(1-turn) session_count: 567
pure_user_session_count: 7
assistant_first_session_count: 19431
same_role_adjacency occurrences: 411 (uu=333, aa=78)   records_with_same_role: 114
has_answer user-target turns: 842; assistant-target turns: 54
missing_core_field_records: 0   turn_extra_keys: {}
```

### 2.3 跨 variant 结构性洞察（承重）

S 与 M **共享同一批 500 问题与同一份 gold**；M 只是加了更多 distractor haystack session。
因此**与问题/答案绑定的 schema 计数在 S/M 完全相同**：answer str468/int32、`$`31、gpt4_107
（multi18+temporal89）、`_abs`30、asid 家族 892/25/31、**has_answer user-target 842 与
assistant-target 54 逐字相同**。**与 distractor session 绑定的结构计数在 M 放大**：blank
12→295、pure-assistant 71→609、single-assistant 65→567、pure-user 1→7、dup session id
13→1182、same-role occ 32→411。这解释了为何草稿（只扫 S）能代表问题级异常，但**不能**把
session 级计数泛化到 M——本 note 对两 variant 分别给 census。

## 3. 候选逐条裁决与处置矩阵

分类取值：`TRUE_DATA_ERROR` / `LEGAL_EDGE` / `SOURCE_HETEROGENEITY` / `CAPABILITY_LIMIT` /
`UNRESOLVED`。canonical 处置只可 preserve / deterministic-normalize / skip-blank /
fail-fast，**绝不改 raw data**。

### C1 · int 类型 answer（S 32 / M 32，census）
- **分类：LEGAL_EDGE**（计数/时序类问题的原生 int 答案；`answer` 是无类型 union，非 str-only
  schema 契约，故非违规）。分布：multi-session 22 / temporal-reasoning 8 / knowledge-update 2
  （`0f05491a`=120、`a2f3aa27`=1300），两 variant 一致。
- **为什么**：answer_types 全量扫描 `{str:468,int:32}`，S/M 逐字相同；官方从未声明 answer 必为
  str。
- **canonical**：deterministic-normalize。`_answer_to_text`（longmemeval.py:730-746）仅在
  **evaluator-private** `GoldAnswerInfo.answer` 入口把 int `str()` 化，不改语义、不进任何公开
  对象。
- **evaluator-private**：进 gold.answer 字符串，judge 比对用。
- **LightMem 差分**：无（answer 永不进 method payload/prompt/retrieve）。
- **回归锚**：`longmemeval.py:730-746` + input-time-audit §2 表（answer 类型 str468/int32）。

### C2 · `$`/逗号/单位 金额 answer（S 31 / M 31，census）
- **分类：LEGAL_EDGE**（金额表面格式；如 `$0.75`、`$25,000`、`$400,000`）。与 C1 同源，非
  schema 违规。
- **canonical**：preserve。`_answer_to_text` 对 str 只 `strip()`，**不剥 `$`、不去逗号、不改单位**
  —— gold answer 逐字保留，任何金额归一化留给 judge，不在 adapter 层分叉官方 raw。
- **evaluator-private / LightMem**：同 C1。
- **回归锚**：`longmemeval.py:742-743`。

### C3 · question_date 落在部分/全部 history 之前（q<earliest S1/M0，q<latest S76/M118，future-gold S44/M42）
- **分类：LEGAL_EDGE + official effective ordering**（非“question 必晚于全部 history”的 schema
  规则）。
- **为什么**：`lme_date_check` 复算 S q<earliest=1（唯一 `gpt4_2f56ae70`，question 00:18 早于
  最早 haystack 00:47 共 29 分钟，**与草稿点 3 逐字一致**），q<latest=76 且 **76 条全为同日
  HH:MM 错序**（same-calendar-day-as-latest=76）。M q<earliest=0、q<latest=118（同 input-time-audit
  §2）。
- **官方裁决**：OWNER issue #8（comment `2895395636`/`2936960111`，见 input-time-audit §F2）明确
  mis-ordering 非有意，annotation 只可靠到 date，同日 question 视为紧接 final conversation 之后；
  无 temporal 约束题可随机赋 question date。cleaned JSON 仍含 `HH:MM`——是**标注语义精度**问题，
  非字段格式错误。
- **canonical**：preserve。`run_generation.py:224-225` 排序全部 session 且**不 filter
  date>question_date**；adapter 原样传 raw session date + question date，**不生成 corrected time、
  不重排、不清洗**。
- **LightMem 差分**：F9——raw `question_time` 只进 answer prompt `Question time:` 行
  （adapter:1764），`_retrieve_with_payload` 传 `filters=None`，**不做 retrieval cutoff**；
  76/118 条不因该字段丢 session/target。method-derived `time_stamp` 是 tie-break，非 source time。
- **回归锚**：input-time-audit §F2/§F9（架构师 R1 已强验收）。

### C4 · `gpt4_` 前缀 question_id（S 107 / M 107，census；仅 multi-session 18 + temporal-reasoning 89）
- **分类：SOURCE_HETEROGENEITY**（GPT-4 生成的补充题 provenance 标记，**非错误**；覆盖不均是
  设计，不是 schema 违规）。census 精确复现草稿点 4：107 = multi18 + temporal89，两 variant 一致。
- **为什么**：question_id 唯一性 census `duplicate question_ids (global): 0`，无碰撞；`gpt4_` 只是
  来源前缀。
- **canonical**：preserve（原样作 question_id / conversation_id）；abstention 经 `_abs` 后缀计数
  （`gpt4&abs`=5 与总 30 独立）。
- **evaluator / LightMem**：无特判。
- **回归锚**：census（0 dup qid）；无需测试改动。

### C5 · answer_session_ids 三前缀家族（`answer_` 892 / `answer_sharegpt_` 25 / `answer_ultrachat_` 31，S/M census 相同）
- **分类：SOURCE_HETEROGENEITY**（上游语料 provenance：ShareGPT/UltraChat 混入 gold session id
  命名），非引用完整性错误。
- **为什么（关键澄清草稿点 5）**：**引用完整性成立**——`asid_missing_ref = 0 across 0 records`
  两 variant 均如此，即**每个 answer_session_id 都能在本 record 的 haystack_session_ids 中找到**，
  前缀差异只是命名族，不是悬空引用。
- **canonical**：preserve + 映射。`_evidence_session_public_ids` / `_longmemeval_evidence_group_sets`
  （longmemeval.py:470-562）把每个 answer_session_id 映射到公开 session id；因 0 missing，session
  view group 全 `mapped`，无 unmatched，不静默删分母。
- **LightMem 差分**：无（session-view gold 只进 evaluator-private group contract）。
- **回归锚**：census（0 missing ref）；adapter group-set 构造。

### C6 · 同角色相邻发言（occurrences S 32 / M 411；records S 14 / M 114，census）
- **分类：SOURCE_HETEROGENEITY**（ShareGPT/UltraChat 混入的结构异形）；草稿的**根因子分类需降格**
  （见 §4）。
- **为什么 / 口径澄清**：本 census 按**结构化 `role` 字段**统计相邻同 role（忽略 system）的
  occurrence 与 record；`unknown_roles: {}`——所有 role 均 user/assistant，**没有第三种 role**。
  S 32 occ / 14 record **逐字复现草稿点 6 的“14 records / 32 处”**；M 411 occ / 114 record。
  注意与 input-time-audit 的 role-shape `consecutive-same`（S5/M39）**不是同一口径**：后者是
  session 级互斥 shape（优先级 pure-assistant > assistant-first > consecutive-same >
  normal-user-first，assistant-first 内的相邻同 role 不再计入 consecutive-same），本 census 是跨
  全部 session 的 occurrence/record 计数。两者各自正确，单位不同。
- **canonical**：preserve。adapter **只读结构化 role，绝不因 content 像 user 就改写 role**
  （`_turn_from_raw` speaker=role or speaker）。
- **LightMem 差分**：pair bridge（event_stream `_aggregate_pairs`）把连续同 role 变
  orphan/dangling，`_normalize_session_to_pairs` 补 placeholder slot；每 retained turn 恰一次
  （input-time-audit §1/§4 已验收）。
- **回归锚**：census（unknown_roles 空）+ input-time-audit §F1。

### C7 · 单条 assistant session / pure-assistant session（single-assistant S 65 / M 567；pure-assistant S 71 / M 609，census）
- **分类：SOURCE_HETEROGENEITY**（ShareGPT/UltraChat 残留，assistant-only）。census 复现草稿点 7
  的“65 个单条 assistant session”（S）；pure-assistant 71 = 65 单条 + 6 多条 assistant-only。
- **canonical**：preserve（这些非 blank，不触发 skip；`_session_from_raw` 仅 blank 为空才 skip，
  非空 assistant-only session 原样保留）。
- **LightMem 差分**：assistant-first / orphan → placeholder user pair（占 1,986/20,126 placeholder
  pair 的主体）。retrieval corpus 官方口径只收 user turn，故 assistant-only session 不产 user-target
  （与 §C10 一致）。
- **回归锚**：census + input-time-audit §2（pure-assistant 71/609）。

### C8 · 全 user 无 assistant session（pure-user S 1 / M 7，census）
- **分类：SOURCE_HETEROGENEITY**（角色扮演，如草稿点 8 的 `352ab8bd` session 24 “Dr. Jekyll” 3 条
  user）。census S=1（`('352ab8bd',24,3)`，逐字复现草稿）、M=7。
- **canonical**：preserve；多条 user → 触发 §C6 same-role adjacency。
- **LightMem 差分**：dangling user → placeholder assistant pair（31/400 dangling placeholder pair）。
- **回归锚**：census + input-time-audit §2（dangling 31/400）。

### C9 · haystack_session_id 实例内重复（S 13 dupes / M 1182 dupes across 449 records，census）
（草稿未列，§3.1 补充）
- **分类：LEGAL_EDGE**（同一 distractor session id 在一个 haystack 内被复用；M 的 large-haystack
  padding 使其普遍）。
- **canonical**：**去重不丢弃**。`_unique_session_id`（longmemeval.py:454-467）对第 2+ 次出现追加
  `#occurrence_N` 稳定 suffix，`deduplicated_session_id_count` 计数；answer_session_ids 经
  `_evidence_session_public_ids` 映射到**同 original id 的全部公开 occurrence**，不静默删。
- **LightMem / evaluator 差分**：无（公开 session id 唯一化后交付）。
- **回归锚**：census + `metadata["deduplicated_session_id_count"]`（load_dataset:190-193）。

### C10 · gold / evaluator 资格（user-target 842 / assistant-target 54，两 variant 逐字相同；abstention 30）
- **分类：LEGAL_EDGE（official contract）**，非 dataset 错误。
- **为什么**：`has_answer=True` 中 user 侧 842、assistant 侧 54。官方 retrieval corpus 只收
  `role=='user'`（`run_retrieval.py:214`），故 **assistant-side has_answer 不是官方 turn 级 gold**；
  adapter `user_target_turns` 只收 `role=='user'`（longmemeval.py:395-396），turn-view group
  `longmemeval_user_target_turn` 只含 user target，未保留的空内容 user target 记 `unmatched`
  不删分母。
- **evaluator-private**：`_abs` 题按 benchmark policy 记 N/A（`benchmark_policy`）；非 abs 但
  canonical turn 无 user-target → `official_no_target` N/A；分母口径
  `run_retrieval.py:389-410`（canonical **419**；`print_retrieval_metrics.py:12` 的 **470** 只是
  官方辅助脚本冲突披露，不用于主口径）。gold 只进 evaluator-private group contract，异常 gold
  不进 public Turn / method message / retrieve query / answer prompt。
- **LightMem 差分（CAPABILITY_LIMIT，非 dataset 异常）**：LME retrieval Recall/rank =
  `n_a / pair_source_id_not_turn_exact`（`lightmem_adapter.py:1329-1338`；注：input-time-audit 记
  的 1284-1293 为 adapter v5 行号，v6 漂移到 1329-1338，行为不变）。`RetrievalQuery.top_k=10` 与
  官方 k30/50、stable_ranking pending 是**独立能力缺口**，不得混成 dataset 异常。
- **回归锚**：`longmemeval_recall.py` / `longmemeval_retrieval_rank.py` summary 分母字段 + adapter
  N/A verdict。

### C11 · 引用完整性 / schema 完备性（全部 PASS，census）
（草稿未列，§3.1 补充；均为“无异常”正向结论）
- duplicate question_id（global）：**0 / 0** → 唯一性成立。
- unknown question_type：**无**（仅 6 个官方类型，S/M 计数一致）。
- unknown 结构化 role：**无**（`unknown_roles: {}`）。
- missing core field record：**0 / 0**（question_id/question/haystack_*/answer 齐全）。
- turn extra keys（非 core/private 的意外字段）：**{}**（无泄漏字段进公开 metadata）。
- 跨 record 泄漏：**by construction 不适用**——每个 Conversation 以 question_id 独立 scope，
  turn_id/session_id 在 instance 内命名空间化；distractor session id 跨 record 复用是共享
  haystack 池的预期，不构成公开对象泄漏。此为构造性论证，非 census 断言。
- **分类：无异常（referential/schema integrity PASS）**。

## 4. 草稿候选 → verified verdict 对照

| 草稿断言 | verdict | 说明 |
|---|---|---|
| ① int answer 32（S） | **CONFIRMED**（S32/M32） | 计数精确；本 note 补 M 及 qtype 细分（multi22/temporal8/kupdate2）与 canonical normalize 口径 |
| ② `$` answer 31（S） | **CONFIRMED**（S31/M31） | 计数精确；补“canonical 不剥 `$`/逗号，逐字保留” |
| ③ question_date 早于所有 haystack（1，`gpt4_2f56ae70`，29 分钟） | **CONFIRMED**（S q<earliest=1 逐字；M=0） | id/时间/gap 逐字复现 |
| ③ 附注“其余 424 晚于所有 haystack，属正常” | **改判/降格** | 忽略了 q<latest=76 的**同日 HH:MM 错序**与 future-gold 44；应改述为 official effective ordering（C3） |
| ④ gpt4_ 107，仅 multi18+temporal89 | **CONFIRMED**（S107/M107 逐字） | 分类应为 SOURCE_HETEROGENEITY，非“异常”；“分布不均”非错误 |
| ⑤ answer_session_ids 三前缀 | **CONFIRMED 存在，但降格** | 三家族计数 892/25/31；**引用完整性 0 missing**——是 provenance 异质性，非悬空引用错误 |
| ⑥ 同角色相邻“14 records / 32 处” | **CONFIRMED 计数**（S14rec/32occ 逐字；M114/411） | 计数对；但根因子分类需降格（下三行） |
| ⑥a “user 消息被错标为 assistant”（4 条 `This is great`） | **改判为 UNRESOLVED/可疑标注** | 结构化 role 字段确为 assistant（`unknown_roles:{}`）；无一手 upstream 证据证明“错标”，按 §3.2 **不得**当 TRUE_DATA_ERROR，canonical 保留结构化 role |
| ⑥b “assistant 回复被截断 split”（`f8c5f88b` s0） | **改判为可疑标注** | 相邻 assistant-assistant 已由 census 证实存在；“截断”是 content 推测，非结构证据 |
| ⑥c “角色扮演内容残留”（`gpt4_2ba83207` s34） | **改判为可疑标注** | 同上；content 里出现 User/Assistant 字样不改结构化 role 的权威性 |
| ⑦ 单条 assistant session“65 sessions / 60 records” | **CONFIRMED**（single-assistant S65/M567） | session 计数逐字；record 计数为派生细节，未单独 census |
| ⑧ 无 assistant session 1（`352ab8bd` s24） | **CONFIRMED**（pure-user S1/M7） | 逐字复现；M 补 7 |
| （草稿全程用 JSON 行号定位） | **方法学勘误** | 行号随重格式化漂移；本 note 一律用 `variant/question_id/session_index[/turn_index]` 语义坐标，行号不作一手证据 |
| （草稿仅扫 S，未分 S/M） | **范围勘误** | 问题级异常 S/M 相同，但结构级计数 M 显著放大（§2.3），不可用 S 泛化 M |

**未被草稿覆盖、本 note 新增的裁定**：C9（实例内 dup session id，去重不丢弃）、C10（user-only
gold 资格 + LME retrieval N/A 能力缺口）、C11（唯一性/完备性/跨 record 全 PASS）。

## 5. 剩余 pending / 不越裁边界

- **UNRESOLVED（交架构师）**：草稿 6a/6b/6c 的“content 与 role 不一致”本质是 upstream
  ShareGPT/UltraChat 语料特性；要升级为 TRUE_DATA_ERROR 需官方 upstream 脚本或 changelog 佐证，
  本 batch 无网络、不下载，故记 UNRESOLVED（倾向 SOURCE_HETEROGENEITY，canonical 已 preserve、
  无需修复）。
- **provenance pending（沿用 source lock）**：LongMemEval-main 快照无独立 git commit provenance；
  issue #8 评论与旧 release 只作历史背景，本 note 未据其覆盖当前锁定数据（当前 cleaned S 仍含
  76 同日错序 + `gpt4_2487a7cb` 差异，公开裁决未被新版废止）。
- **CAPABILITY_LIMIT（非 dataset 异常）**：LME turn Recall 因 pair-source-id 恒 N/A；top-k=10 vs
  k30/50、stable_ranking pending。属 method/评测能力缺口，勿混入稳定异常账的 dataset 行。
- 本审计未触发真实 API、未下载、未读 `.env`/credential、未改任何 src/tests/third_party/data/
  outputs/configs/policy/handbook/survey 三联页/未跟踪草稿；私有字段仅计数。

## 6. 门与自检

```
uv run pytest -q tests/test_documentation_standards.py   # 结果见完成报告
git diff --check                                          # 结果见完成报告
```

提交只显式 `git add` 本 note 唯一路径，禁用 `git add -A`/`.`；本地 commit，不 push、不 amend
其他 commit。

## 7. 总判词

READY_FOR_ARCHITECT_STABLE_LEDGER_INTEGRATION
