# LightMem × LongMemEval 输入异形与 timestamp 透明性审计

> 取证 actor 交付（只读离线审计，不改生产代码）。本 note 保留完整一手命令、统计与
> 争议；架构师强验收后再决定哪些稳定摘要回填 `docs/survey/datasets/longmemeval.md`
> 与 `docs/reference/integration/lightmem.md`。裁决权在架构师。

> **架构师 R1（2026-07-17）**：主体计数、两层 timestamp 机制与 no-code-fix 总判词
> 接收；F2 的公开来源状态、placeholder 对 method-derived time 的影响及 query-time cutoff
> 负空间由 §8 线性勘误。凡首轮文字与 R1 冲突，以 R1 后的现行正文为准。

## 0. 基线与 identity

| 项 | 值 |
|---|---|
| 审计日期 | 2026-07-17 |
| worktree | `/Users/wz/Desktop/mb-actor-lightmem-lme-time-audit`（branch `actor/lightmem-lme-time-audit`） |
| 基线 HEAD | `914a198`（主树与 worktree 同一 commit） |
| 执行模型 | Claude Opus 4.8（`claude-opus-4-8`，见会话系统提示） |
| LightMem adapter 版本 | `conversation-qa-v5` |
| LightMem vendored `source_sha256` | `74be165faac06d5891e598e6d869f70220dfc4a90363b84bb44c0571fa8a5a35`（7 文件，`build_lightmem_source_identity()`） |
| `longmemeval_s_cleaned.json` | 277,383,467 bytes，mtime 2026-06-13 22:58 |
| `longmemeval_m_cleaned.json` | 2,737,100,077 bytes（≈2.5GiB），mtime 2026-06-13 22:58；**只 ijson 流式**，逐文件身份见 `ws02.6-first-smoke-hardening/notes/longmemeval-source-lock.json` |

数据未入 git，扫描/探针直接读主工作区绝对路径；提交前确认无软链/临时脚本被暂存。

架构师 R1 另以 HF HEAD 响应核对：当前官方 cleaned repo 为
`main@98d7416c24c778c2fee6e6f3006e7a073259d48f`，S blob 的 linked SHA-256
`d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442` 与本地一致。

### 可复算命令

```bash
# 数据扫描（_s 全量 json.load；_m ijson 流式）
uv run python <scratchpad>/lme_time_scan.py _s
uv run python <scratchpad>/lme_time_scan.py _m   # ≈2.5GiB，禁 json.load

# 逐层无 API 探针（production helper + 真实 vendored 纯函数）
uv run python <scratchpad>/lme_time_probe.py

# 定向文档门（在 worktree 内）
uv run pytest -q tests/test_documentation_standards.py   # 5 passed in 0.83s

# 官方源码 / 身份
uv run python -c "from memory_benchmark.methods.lightmem_adapter import build_lightmem_source_identity as f; print(f()['source_sha256'])"
```

扫描脚本 `lme_time_scan.py`、探针脚本 `lme_time_probe.py` 为临时产物（scratchpad），
不入仓库；其逻辑复刻自下列一手源，关键 stdout 已原样抄录进 §2/§4。

## 1. 五层数据/变换链（先把语义分层）

```
[L0 benchmark-native 数据]  haystack_sessions: list[session], session=list[turn]
        turn = {role: user/assistant, content, (私有 has_answer)}
        时间只在 session 级 haystack_dates（"2023/05/30 (Tue) 23:40"），turn 无独立时间
        question_date 独立字段；answer / answer_session_ids 私有
                │
                │  官方 generation（run_generation.py）：按 date 排序全部 session，
                │  **不过滤 date>question_date**（:224-225 sort，无 filter），
                │  进 prompt 前 pop has_answer（:182-189）。完整 history + question date。
                │
[L1 官方 LightMem LME harness]  run_lightmem_gpt.py:157-176（reproduction 口径）
        while session[0].role!='user': pop(0)      # 裁开头非 user
        num_turns=len//2；window=[2i,2i+1]，仅严格 user→assistant 才 add_memory
        → 丢弃开头非 user / 尾部奇数 / 非法 window（见 §4.4 计数）
                │
[L2 framework canonical]  benchmark_adapters/longmemeval.py
        blank content turn 直接跳过（_has_blank_message_content，:386-399）
        role 只认结构化字段；不猜测；orphan/dangling 不丢弃
                │
[L3 framework pair bridge]  runners/event_stream.py:_aggregate_pairs（:110-154）
        user 锚定：user 开 pair，下一非 user 闭合=real-real；
        连续 user / 尾部未闭合 user = dangling；无锚点 assistant = orphan
                │  LightMem×longmemeval consume_granularity="pair"
                │  （registry.py:399-405）
                │
[L4 LightMem adapter normalize]  lightmem_adapter.py:_normalize_session_to_pairs（:480-552）
        real-real → [real user, real assistant]
        orphan    → [placeholder user, real assistant]
        dangling  → [real user, placeholder assistant]
        placeholder: content="", marker=memory_benchmark_structural_placeholder=True,
        speaker/time/external_id/source_external_ids 全部镜像同 pair 真实 child
                │
[L5 vendored backend]  add_memory（lightmem.py:225-415）每次处理一个 pair batch
        (a) MessageNormalizer(offset_ms=500) 每 add_memory 新建（:296）→ layer-1 time_stamp
        (b) 段缓冲 ShortMemBufferManager：placeholder 只从 token 计数排除
            （short_term_memory.py:23，framework 插桩），仍留在 buffer/segment
        (c) force_extract 时 assign_sequence_numbers_with_timestamps(offset_ms=500)
            （utils.py:89-184）按 session_time 分组重算 → layer-2 time_stamp **覆写** layer-1
        (d) concatenate_messages（openai.py:281-316）按 messages_use 过滤 role 且
            排除 placeholder；行号=sequence_id//2
        (e) fact.source_id → sequence_n=source_id*2（utils.py:378-405）读取该偶数 slot 的
            time/speaker/source_external_ids
```

## 2. S/M 数据质量表与定义

### 定义（可复算）

- **blank turn**：`content`（或 `text`）键存在但 strip 后为空。等于 adapter 的
  `_has_blank_message_content`；这些 turn 被 framework 直接跳过，不成为 canonical turn。
- **role 形状（互斥）**：忽略 content，按非 system role 序列，优先级
  `pure-assistant`（全 assistant）> `assistant-first`（首条 assistant）>
  `consecutive-same`（相邻同 role）> `normal-user-first`（user 先说且严格交替）。与
  ws02.6 `longmemeval-b2-audit.md` 口径一致，便于对表。
- **odd session**：turn 数为奇数（与 role 形状正交，单列）。
- **q<latest / q<earliest**：`question_date` 早于全部 haystack session date 的
  max / min。
- **future gold**：至少一个 `answer_session_id` 对应 session 的 date 严格晚于
  `question_date`（私有字段只用于计数）。
- **官方 dropped raw turn**：L1 harness 里从未进入任何 `add_memory` 的原始 turn（开头
  pop、尾部奇数、非法 window 两成员）。
- **framework placeholder pair**：L3/L4 产出的、含一个 placeholder slot 的 pair
  （=orphan pair + dangling pair）。

### 表

| 指标 | `_s` | `_m` | 架构师校验点 | 一致 |
|---|---:|---:|---|:--:|
| instance / session / raw turn | 500 / 23,867 / 246,750 | 500 / 237,655 / 2,446,993 | 同 | ✅ |
| blank turn | 12 | 295 | 12 / 295 | ✅ |
| blank 所在 session | 7 | 91 | — | — |
| answer python 类型 | str 468 / int 32 | str 468 / int 32 | 形状非风险 | — |
| answer `$` 前缀 | 31 | 31 | 形状非风险 | — |
| q<latest / q<earliest | 76 / 1 | 118 / 0 | 76/1 · 118/0 | ✅ |
| future gold | 44 | 42 | 44 / 42 | ✅ |
| q<latest 分层 | temporal 60 / kupdate 16 | kupdate 58 / temporal 60 | — | — |
| future gold 分层 | temporal 43 / kupdate 1 | temporal 40 / kupdate 2 | — | — |
| q<latest ∩ abs / future ∩ abs | 7 / 3 | 11 / 5 | — | — |
| role: normal-user-first | 21,920 | 218,185 | — | — |
| role: assistant-first | 1,871 | 18,822 | — | — |
| role: pure-assistant | 71 | 609 | — | — |
| role: consecutive-same | 5 | 39 | — | — |
| odd session | 1,940 | 19,395 | — | — |
| 异形 ∩ answer session | asst-first 5 / consec 1 | asst-first 5 / consec 1 | — | — |
| 异形 ∩ has_answer=True | asst-first 5 / consec 1 | asst-first 5 / consec 1 | — | — |
| 官方 dropped raw turn | 2,020 | 20,283 | 2,020 / 20,283 | ✅ |
| 官方 affected session | 1,951 | 19,497 | — | — |
| 官方 dropped `has_answer=True` | 3（全 assistant，均在 answer session，均 single-session-assistant） | 3（同） | 3 assistant / 3 assistant | ✅ |
| framework real-real pair | 122,376 | 1,213,286 | — | — |
| framework orphan placeholder pair | 1,955 | 19,726 | — | — |
| framework dangling placeholder pair | 31 | 400 | — | — |
| **framework placeholder pair 合计** | **1,986** | **20,126** | 1,986 / 20,126 | ✅ |
| retained canonical turn = real·2+orphan+dangling | 246,738 ✔ | 2,446,698 ✔ | 每 retained turn 恰好一次 | ✅ |
| max session group（turn/session） | 132 | 132 | — | — |
| group>120 / 其中 answer session | 2 / 0 | 7 / 0 | — | — |
| worst-case +500ms 越分钟 / 越小时 / 越日 | 2 / 0 / 0 | 7 / 0 / 0 | — | — |

**全部 6 个架构师校验点逐项一致，无需改代码或筛选条件对齐。** `retained turn = raw turn −
blank turn`（246,750−12=246,738；2,446,993−295=2,446,698）且 `= real-real·2 + orphan +
dangling`，证明每个保留的 canonical turn 恰好出现在一个 pair 中一次（脚本
`fw_turn_once_ok=True`）。

### future gold 最小例（仅公开字段）

| variant | question_id | type | question_date | #session | #answer session |
|---|---|---|---|---:|---:|
| _s | `gpt4_2655b836` | temporal-reasoning | 2023/04/10 (Mon) 10:15 | 45 | 3 |
| _s | `gpt4_2487a7cb` | temporal-reasoning | 2023/05/24 (Wed) 08:02 | 47 | 2 |
| _m | `07741c44` | knowledge-update | 2023/11/30 (Thu) 01:44 | 473 | 2 |

只展示公开 question id/type/time 与规模，不倾倒对话或 gold answer。

## 3. 四组探针的逐层结果（production helper + 真实 vendored 纯函数）

探针用真实 adapter（`messages_use="hybrid"`、`benchmark_name="longmemeval"`、fake
backend 仅跳过资源校验）跑 `_normalize_session_to_pairs`，再串真实 vendored
`MessageNormalizer(offset_ms=500)`（每 add_memory 一次）与
`assign_sequence_numbers_with_timestamps(offset_ms=500)`；未触发任何 LLM/embedding。
session_time 固定 `2023/05/20 (Sat) 00:44`。

**约定**：C1=每 pair 单独 force_extract（normalizer/assign 都 per-pair）；C2=整 session
在一个 extract batch 内 regroup（worst-case 单次触发）。真实 runtime 落在两者之间（见
§5 边界说明）。

### 探针 1 — normal user→assistant

- L4 pair：`[user t0, assistant t1]`，两 slot `source_external_ids=['t0','t1']`。
- L5a normalizer：user=`00:44:00.000`，assistant=`00:44:00.500`（同 add_memory 内 +500ms）。
- L5c C2：seq0 user=`.000`，seq1 assistant=`.500`。
- L5d concatenate：`line#0` 同时来自 user(seq0) 与 assistant(seq1)（`sequence_id//2` 都=0）。
- source_id=0 → sequence_n=0 → 读 **user slot**，time=`.000`，`source_external_ids=['t0','t1']`
  （plural，`MemoryEntry.source_external_id` 因 len≥2 置 None，lineage 记 pair 两 id）。

### 探针 2 — assistant-first（orphan）

- L4 pair：`[placeholder user, real assistant t0]`；placeholder `content=''`、marker=True、
  `speaker/time/external_id/source_external_ids` **全镜像真实 assistant**（`['t0']`）。
- L5a：placeholder user=`.000`，real assistant=`.500`。
- L5c C2：seq0 placeholder=`.000`，seq1 real assistant=`.500`。
- L5d concatenate：prompt **只出现 real assistant**（`line#0 (seq=1)`）；placeholder 被
  marker 过滤，不进抽取文本、不进 token 计数。
- source_id=0 → sequence_n=0 → 读 **placeholder slot**。该 slot 镜像真实 assistant 的
  `source_external_ids=['t0']`、speaker 与 source `session_time`，所以 lineage/speaker 仍解析
  到真实 assistant t0；但 layer-2 后 placeholder 的 method-derived `time_stamp=.000`，真实
  assistant slot 为 `.500`，故 fact time 锚在 **pair base**，不能声称 child-derived time
  也无失真。**placeholder 不改 source id / speaker / lineage，但会影响派生 time 的 slot 锚点。**

### 探针 3 — user→user（连续 user）

- L4：两 pair `[user t0, placeholder assistant]`、`[user t1, placeholder assistant]`
  （L3 dangling 拆成两个单 user pair，各自补 placeholder assistant）。
- L5a（per pair）：每 pair user=`.000`、placeholder=`.500`（normalizer per add_memory 重置）。
- L5c **C1**：每 pair 独立，两真实 user 都在各自 pair 的 `.000`。
- L5c **C2**：seq0 user t0=`.000`，seq1 ph=`.500`，seq2 user t1=`01.000`，seq3 ph=`01.500`。
  → 两真实 user 派生 time 相差 **1000ms**。
- 关键判断：相对 canonical 的两个相邻真实 user（若只按真实 turn 排序，本应相差 500ms），
  placeholder **确实额外占用一个 layer-2 sequence/time slot**，使两者变成 1000ms。探针 5
  只能证明它没有比 LightMem 固定 pair-index 结构再多拉宽一层，不能把 framework structural
  extension 对 canonical real-turn 间隔的影响说成“未改变”。

### 探针 4 — dangling user（单 user）

- 与探针 3 的单个 pair 行为完全一致：`[real user, placeholder assistant]`，user=`.000`、
  placeholder=`.500`；source_id=0 读 user slot（真实）。故与探针 3 共用结论。

### 探针 5 — 参照：同 session 两个正常 pair

- L5a（per pair）：pair0/pair1 各自 user=`.000`、assistant=`.500`（**normalizer 每 pair
  重置，跨 pair 不累积**）。
- L5c **C2**：seq0..3 = `.000/.500/01.000/01.500`（**assign_sequence 跨 pair 单调 +500ms**）。
- 证明：**layer-2 assign_sequence 覆写 layer-1 normalizer 结果**；持久化/检索展示的
  `time_stamp` 是 layer-2 派生 tie-break，而非 source time。两真实 user 相差 1000ms，与探针 3
  相同——印证探针 3 的 1000ms 属 pair 结构固有、非 placeholder 引入。

## 4. 逐项发现（分类 / severity / confidence / 受影响面）

分类取值：`benchmark-native shape` / `raw timestamp artifact` /
`official effective ordering` / `method-native transformation` / `framework extension` /
`stale documentation`。

### F1 · 输入异形（blank / assistant-first / pure-assistant / consecutive-same / odd）
- 分类：**benchmark-native shape**。confidence 高（全量结构化扫描，两 variant 一致）。
- 事实：blank 12/295、非严格交替 1,947/19,470、odd 1,940/19,395。framework L2 跳过 blank，
  L3/L4 用 placeholder 保留其余；每 retained turn 恰一次。
- severity：**low**。受影响：无（诚实保留，已裁不清洗）。

### F2 · question_date 落在部分 history 之前/之中
- 分类：**raw timestamp artifact** + **official effective ordering**。
- 事实：q<latest 76/118，且架构师 R1 流式复算确认两 variant 的这些题**全部是同一日内的
  HH:MM 错序**；future gold 44/42。`_s` future gold 43/44 属 temporal-reasoning，`_m`
  knowledge-update 也占 58 个 q<latest，但这些分层不能再用来支持“有意 within-history as-of”。
- 官方仓库 OWNER 在 issue #8 comment `2895395636` 明确裁决：mis-ordering 并非有意；问题
  annotation 只确定 date、未确定可靠的 specific time；question 与 final conversation 同日时，
  应视为紧接 final conversation 之后。comment `2936960111` 又说明：无 temporal constraints
  的题可由 haystack creation algorithm 随机赋 question date，正确性不应受影响。最终 cleaned
  JSON 确实含 `HH:MM`；OWNER 说的是**标注语义精度**，不是字段格式。
- issue 早于 2025-09 cleaned release，但当前 official-cleaned S 仍有上述 76 个同日错序；issue
  点名的 `gpt4_2487a7cb` 在 cleaned S/oracle 中仍保留 `2023/05/24 08:02` /
  `2023/05/28 06:47` 差异，所以公开裁决没有被新版数据废止。
- 官方 `run_generation.py:224-225` 排序全部 session 且**不 filter date>question_date**；README
  也要求在全部 interaction sessions 后答题。实现因此原样传 dataset raw timestamp 与完整
  history，不生成 corrected time、不重排、不清洗；“after final conversation”只解释可见性与
  同日错序，不产生第三份 timestamp。
- severity：**low（仅披露）**。受影响：无代码修复项；框架原样传递 history + question time。
  建议 report 披露“存在 raw q<latest / future-gold 题，按官方 no-filter 口径完整传递”。

### F3 · 官方 LightMem harness 丢弃异形 turn（reproduction 口径）
- 分类：**method-native transformation**（author reproduction）。confidence 高（复刻
  run_lightmem_gpt.py:157-176 全量模拟）。
- 事实：L1 丢 2,020/20,283 raw turn，affected session 1,951/19,497；其中 **3+3 个
  `has_answer=True` 且在 answer session 的 assistant turn 被丢**（均 single-session-assistant
  题）。unified hybrid（L2-L4）改用 1,986/20,126 placeholder pair 保住全部 retained canonical
  turn。
- severity：**medium**。这是 reproduction profile 与 unified 主 profile 的**已知分叉，必须
  分开命名、不得混名**（B2 已 retested，本审计只量化 exact loss/overlap）。受影响：
  `messages_use="user_only"` 的 author/reproduction section 与主 `hybrid` 的可比性声明；B11
  真实 smoke 报告必须披露该分叉，不能把 hybrid 行为冒充官方复现。

### F4 · framework placeholder pair 机制
- 分类：**framework extension**。confidence 高（探针 + 全量计数）。
- 事实：placeholder 只补 pair 结构槽（content=""、marker=True），镜像真实 child 的
  time/speaker/external_id/source_external_ids；从 extraction 文本（concatenate_messages
  openai.py:298）和 token 计数（short_term_memory.py:23）中过滤；不新增 source id，不进
  public turn。真实空 content（blank）在 L2 已被跳过，与 placeholder 由 marker 严格区分。
- 镜像能保住 source `session_time`、speaker 与 lineage；不能保住真实 child 的 layer-2
  `time_stamp` slot（assistant-first 见探针 2），连续同 role 也会相对 canonical real-turn
  adjacency 多占一个 500ms slot（探针 3）。
- severity：**low（披露）**。它仍是“完整保留 retained turn”的必要实现手段，但并非对派生
  timestamp 零影响。

### F5 · 两层 timestamp 派生（normalizer per-pair + assign_sequence regroup 覆写）
- 分类：**method-native transformation**。confidence 高（探针 5 实测覆写）。
- 事实：(a) `MessageNormalizer(offset_ms=500)` 每 add_memory 新建、按 raw session_time 字符串
  维护 `last_timestamp_map`，作用域=单次 add_memory 调用（=单 pair，2 msg）：首 slot=session
  time、次 slot +500ms，**跨 pair 不累积**。(b) `assign_sequence_numbers_with_timestamps`
  在 force_extract 时按 session_time **重新分组**，组内按 extract-list 顺序 base+i·500ms，
  **覆写 layer-1**，写入 `timestamps_list` → `MemoryEntry.time_stamp/float_time_stamp`。
- `+500ms` 只发生在**相同 raw timestamp 字符串**的组内，不是全局改写所有 turn。架构师以
  官方 `main@4372c8e479932706a61d2e9ec84fd57e4d71e26c` 复核两层源码，并跑 vendored 纯函数
  探针：输入 `23:44:00/23:44:05/23:44:10` 时 normalizer 与 regroup 后均保持三组原值；输入
  三个相同 `23:44:00` 时才得到 `.000/.500/01.000`。因此有真实 distinct turn timestamp 的
  benchmark 通常保持原时间；LongMemEval 因所有 turn 继承 session time 才触发组内递增，
  placeholder 镜像同一真实 child 时也会制造重复 key。
- placeholder 占一个 sequence/time slot；相对 canonical real-turn 序列会把连续 user 的派生
  间隔从 500ms 拉到 1000ms，但相对 LightMem 固定 pair-index 结构不会再额外放大（探针 3 与
  正常 pair 参照探针 5 均为 1000ms）。这是 framework extension 与 method pair contract 的
  组合效应，不改 source session time。
- severity：**low（披露）**。受影响：任何依赖 LightMem `time_stamp/float_time_stamp` 排序或
  展示的检索/consolidated 逻辑——这是 method-derived tie-break，不是 source time。

### F6 · source_id=pair index，非 turn-exact（本审计再证）
- 分类：**method-native transformation**。confidence 高。
- 事实：concatenate 行号=`sequence_id//2`，fact.source_id→`sequence_n=source_id*2` 恒读**偶数
  (user) slot**；assistant-first 时读 placeholder slot，但镜像字段使 lineage 落到真实
  assistant；method-derived fact time 同时锚到 placeholder 的偶数 pair-base slot，而非真实
  assistant 的奇数 slot。plural `source_external_ids` 含 pair 两 id →
  `MemoryEntry.source_external_id` 置 None。
- severity：**low**。受影响：**印证 adapter 现有 `_build_retrieval_evidence` 对 longmemeval
  记 `n_a / pair_source_id_not_turn_exact` 是正确的**（lightmem_adapter.py:1284-1293），无需
  改动。LME turn Recall 保持 N/A。

### F7 · 派生 time_stamp ≠ source time（可审计性）
- 分类：**method-native transformation**。confidence 高。
- 事实：`session_time` 字段全程=原 session date 字符串，是唯一可审计 source timestamp；
  LongMemEval 每个真实 turn 只有 session-level source time，framework 未用 question time /
  墙钟 / 相邻 session 伪造 turn time（`_turn_timestamp` 只 `turn_time→session_time`，LME turn
  无 turn_time 故一律 session time）。持久化/检索的 `time_stamp` 已是 method tie-break。
- severity：**low（披露）**。受影响：效果实验里如需报告"记忆时间"，须声明用的是 method-derived
  order time，非 source time。

### F8 · timestamp worst-case 上界
- 分类：**method-native transformation**（bounded）。confidence 中（上界确定，实际 batch 边界
  runtime-dependent）。
- 事实：单 session 最大 132 turn；若整 session 落在一个 extract batch（worst case），末 turn
  派生 time = session_time + 131·500ms ≈ +65.5s，**越分钟**（_s 2 例 / _m 7 例），**从不越
  小时或日**；group>120 的 session **无一是 answer session**。真实 runtime 因 STM 512-token
  阈值与 topic segmentation 会把一个 session 拆成更小 extract batch（layer-1 甚至每 pair 重置），
  实际派生 spread ≤ 上界。**不把 worst-case 写成已发生。**
- severity：**low**。受影响：无 answer session 命中大 group，检索/评测语义不受实质影响。

### F9 · raw question_time 不参与 retrieval cutoff
- 分类：**official effective ordering**。confidence 高（framework→adapter→vendored 负空间
  逐调用点核对）。
- 事实：v3 `_retrieve_native()` 虽把 raw `query.question_time` 保留进 `Question`，
  `_retrieve_with_payload()` 只 embed `question.text`，并明确调用
  `embedding_retriever.search(..., filters=None, return_full=True)`（adapter:1191-1197,
  1565-1603）。vendored `LightMemory.retrieve()` 的时间过滤也只能经可选 `filters` 参数进入
  search（lightmem.py:673-709）；当前 adapter 没传。raw question time 只进入 LME answer
  prompt 的 `Question time:` 行（adapter:1764），不决定 memory visibility。
- severity：**无**。76/118 个 raw q<latest instance 不会因该字段丢 session/target；无需代码
  修复或 corrected timestamp。

### F10 · 过时文档已在基线修正（无残留）
- 分类：**stale documentation（已消解）**。
- 事实：本审计按 §3.2 指令搜索残留 "skips orphan / official trim / 等价官方裁剪" 文字：
  - `tests/test_lightmem_adapter.py:2311` 测试名已是
    `..._assistant_first_preserves_orphan_with_placeholder`（旧 `..._skips_orphan_like_official_trim`
    已更正）；
  - `lightmem_adapter.py:1014-1020` `_native_pair_batch` docstring 已写"unified hybrid 主
    profile 不复刻 author harness 的开头裁剪…None 仅保留为防御性空结果分支"。
  - 全仓 `grep "skip.*orphan|official.*trim|trim.*orphan"` 于 adapter+test 无其他命中。
- severity：**无**。受影响：无。**当前源码已分开 author-reproduction 裁剪与 unified hybrid
  保留两口径**，不存在需本审计修改的过时文字（且本卡禁改 test/survey）。

## 5. 关键边界说明（不越裁）

- **真实 extract batch 作用域无法离线确定**：force_extract 只在 conversation 末（或 STM
  512-token 溢出）触发；其间每 pair 一次 `add_memory`（force=False）累积进 buffer，placeholder
  留在 buffer。因此单次 `assign_sequence` regroup 的 message 集合 = "自上次触发以来累积的 pair，
  按 session_time 分组"，介于 C1（每 pair）与 C2（整 session）之间。精确边界依赖 segmenter/
  compressor（需真实模型），本审计不跑；只给出机制与上界，worst-case 不当已发生。
- 私有字段（answer / answer_session_ids / has_answer）在扫描中仅用于计数与分层，从未进入任何
  method 可见 payload、prompt 或探针输入；探针 backend 为 fake、不触发抽取。
- 本审计未触发真实 API、未下载模型、未改任何 `src/tests/third_party/configs/data/outputs`
  或 survey/integration/policy/handbook 及用户未跟踪草稿。

## 6. 最小后续建议（交回架构师裁）

按"必须改代码 / 只改测试或稳定文档 / 只需披露 / 保持原样"分列：

1. **必须改代码**：无。现有 `_build_retrieval_evidence`（LME=n_a/pair_source_id_not_turn_exact）、
   placeholder 镜像、`_turn_timestamp`（LME→session time）均与一手行为一致；两层 timestamp
   是 vendored 算法核心，不在本框架修复范围。
2. **只改稳定文档（经验收后回填，非本卡执行）**：
   - `docs/survey/datasets/longmemeval.md`：补一行"存在 q<latest 76/118、future-gold 44/42
     题，且均为同日 HH:MM 错序；OWNER 已裁 annotation 只可靠到 date、同日 question 视为
     final conversation 之后；框架按官方 no-filter 口径原样传 history + question date"。
   - `docs/reference/integration/lightmem.md`：补"LME time_stamp 为 method-derived tie-break
     （normalizer per-pair + assign_sequence regroup 覆写），source time 仅 session-level；
     placeholder 占结构 slot、保住真实 turn 的 source id/speaker/lineage，但会让连续同 role
     相对 canonical real-turn 顺序多占 500ms，并使 assistant-first fact time 锚到 pair base"。
3. **只需 manifest/report 披露**：B11 真实 smoke 报告须声明 (a) unified `hybrid` 与官方
   `user_only` reproduction 的 turn-drop 分叉（2,020/20,283，含 3+3 answer-session assistant
   丢弃）；(b) LME turn Recall 因 pair-source-id 保持 N/A；(c) 时间字段为 method-derived order
   time。
4. **保持原样以维持 author reproduction**：`messages_use="user_only"` author section 继续复刻
   L1 裁剪，不得为对齐 hybrid 而改；两层 500ms/pair-index 是 LightMem 算法核心，保持零改。

## 7. 结论

- 6 个架构师校验点（blank 12/295、q<latest 76/118、q<earliest 1/0、future-gold 44/42、官方
  dropped 2,020/20,283、placeholder pair 1,986/20,126、dropped has_answer=True 3+3 assistant）
  **逐项复算一致**；retained turn 恒等式成立。
- placeholder **占** sequence/time slot且从 prompt/token 过滤；镜像真实 child 保住 source
  id/speaker/lineage，但连续同 role 相对 canonical real-turn adjacency 会多占 500ms，
  assistant-first fact 的 method-derived time 锚到偶数 pair-base placeholder slot。source
  session time 仍可审计。
- 两层 timestamp：normalizer per-pair（+500ms，跨 pair 重置）→ assign_sequence regroup
  **覆写**（只在相同 raw `session_time` 组内 base+i·500ms；distinct raw timestamp 保持
  原值）；持久化 `time_stamp` 在重复组内是 method tie-break，source time 仍在
  `session_time` 可审计。
- question_date 与 history 的交叉属 raw timestamp artifact + official effective ordering；
  OWNER 公开裁决已锚，框架按 dataset-raw + official no-filter 完整保留，且检索明确
  `filters=None`，**无清洗、无 corrected timestamp、无代码修复项**。
- **本审计结论：B4 无需另发代码修复卡**；剩余为稳定文档回填 + B11 report 披露，交架构师强验收。

## 8. 架构师 R1 强验收

- full diff 逐行审读；actor 唯一文件与 allow-list 一致，commit `0b1ca2e` 线性合入为
  `aeabb3a`。
- 架构师复跑 `tests/test_documentation_standards.py`：`5 passed in 0.85s`；
  `git diff --check` 干净。
- 独立 ijson 复算：S/M q<latest=`76/118`，其中 same-calendar-day=`76/118`；按 user-anchor
  pair 规则复算 max real/slot=`132/132`、跨 minute boundary=`2/7`、跨 hour/day=`0/0`，与
  actor 主体一致。
- 官方 LightMem `main@4372c8e` 与 vendored 双锚确认 timestamp key 分组机制；零 API 探针
  实测 distinct raw timestamps 两层均保持，repeated raw timestamps 才按 500ms 递增。
- R1 驳回三处首轮判词而非主体取证：公开 contract 不是 unresolved；placeholder 对派生 time
  不是零影响；旧卡漏查 query-time cutoff。现行 F2/F4-F6/F9 已订正。
- 最终裁决：B4 可按“offline retested + 必披露 method-derived time”关闭；无需代码返工卡。
