# LightMem × LongMemEval 输入异形与 timestamp 透明性审计

> 取证 actor 交付（只读离线审计，不改生产代码）。本 note 保留完整一手命令、统计与
> 争议；架构师强验收后再决定哪些稳定摘要回填 `docs/survey/datasets/longmemeval.md`
> 与 `docs/reference/integration/lightmem.md`。裁决权在架构师。

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
- source_id=0 → sequence_n=0 → 读 **placeholder slot**，但该 slot 的
  `source_external_ids=['t0']`、speaker、time 已镜像真实 assistant，所以 lineage/speaker/
  time **仍解析到真实 assistant t0**。**placeholder 不改 source id / speaker / lineage。**

### 探针 3 — user→user（连续 user）

- L4：两 pair `[user t0, placeholder assistant]`、`[user t1, placeholder assistant]`
  （L3 dangling 拆成两个单 user pair，各自补 placeholder assistant）。
- L5a（per pair）：每 pair user=`.000`、placeholder=`.500`（normalizer per add_memory 重置）。
- L5c **C1**：每 pair 独立，两真实 user 都在各自 pair 的 `.000`。
- L5c **C2**：seq0 user t0=`.000`，seq1 ph=`.500`，seq2 user t1=`01.000`，seq3 ph=`01.500`。
  → 两真实 user 派生 time 相差 **1000ms**。
- 关键判断：这个 1000ms **不是 placeholder 造成的额外拉宽**——pair-index 方案下相邻同 role
  turn 本来就隔 2 个 slot（见探针 5，两真实 user 同样相差 1000ms）。placeholder 只是占了本
  就属于 assistant slot 的位置，派生间隔与"该位置换成真实 assistant"完全相同。

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

分类取值：`benchmark-native shape` / `benchmark-native temporal semantics` /
`public-contract unresolved` / `method-native transformation` / `framework extension` /
`stale documentation`。

### F1 · 输入异形（blank / assistant-first / pure-assistant / consecutive-same / odd）
- 分类：**benchmark-native shape**。confidence 高（全量结构化扫描，两 variant 一致）。
- 事实：blank 12/295、非严格交替 1,947/19,470、odd 1,940/19,395。framework L2 跳过 blank，
  L3/L4 用 placeholder 保留其余；每 retained turn 恰一次。
- severity：**low**。受影响：无（诚实保留，已裁不清洗）。

### F2 · question_date 落在部分 history 之前/之中
- 分类：**benchmark-native temporal semantics** + **public-contract unresolved**。
- 事实：q<latest 76/118，其中 future gold 44/42。分层显示两假说都有支撑：`_s` future gold
  43/44 是 temporal-reasoning（支持"有意 as-of"），`_m` 则 knowledge-update 也占 58 个 q<latest
  （支持"非时间题未约束先后"）。唯一 `_s` q<earliest=1 的题（`_m`=0）仍属 temporal-reasoning。
- 一手交叉核对：官方 `run_generation.py:224-225` 排序全部 session 且**不 filter
  date>question_date**，即官方本身把完整 history + question date 一起喂给 reader——与本框架
  "完整保留、只披露"一致。论文符号 `t_q>t_N`、README"answer after all sessions"、生成代码
  实际行为、用户转述作者口径四者并列：README/论文是**叙述性理想**，生成代码是**实际契约**，
  两者对少数 as-of/未约束题不一致；用户转述的作者动机**尚无可引用公开原文**。
- 公开 issue `xiaowu0162/LongMemEval#8`：提问者已指出 S 中 question date 早于最后 session
  并询问是否有意；**本次审计未在公开页面见 maintainer 回复**（不得把提问者推测当作者答复）。
- severity：**low（仅披露）**。受影响：无代码修复项；框架原样传递 history + question time。
  建议 report/manifest 披露"存在 q<latest / future-gold 题，按官方 no-filter 口径完整传递"。

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
- severity：**low**。受影响：无。是"完整保留 retained turn"的实现手段，符合既有裁决。

### F5 · 两层 timestamp 派生（normalizer per-pair + assign_sequence regroup 覆写）
- 分类：**method-native transformation**。confidence 高（探针 5 实测覆写）。
- 事实：(a) `MessageNormalizer(offset_ms=500)` 每 add_memory 新建、按 raw session_time 字符串
  维护 `last_timestamp_map`，作用域=单次 add_memory 调用（=单 pair，2 msg）：首 slot=session
  time、次 slot +500ms，**跨 pair 不累积**。(b) `assign_sequence_numbers_with_timestamps`
  在 force_extract 时按 session_time **重新分组**，组内按 extract-list 顺序 base+i·500ms，
  **覆写 layer-1**，写入 `timestamps_list` → `MemoryEntry.time_stamp/float_time_stamp`。
- placeholder 占一个 sequence/time slot，但（见 F4）它占的正是 pair 结构里 assistant slot 的
  位置；相邻真实 turn 的派生间隔与"该 slot 换成真实 assistant"相同（探针 3 vs 5 均 1000ms），
  **placeholder 未在 pair 结构之外额外拉宽真实 turn 间隔**。
- severity：**low（披露）**。受影响：任何依赖 LightMem `time_stamp/float_time_stamp` 排序或
  展示的检索/consolidated 逻辑——这是 method-derived tie-break，不是 source time。

### F6 · source_id=pair index，非 turn-exact（本审计再证）
- 分类：**method-native transformation**。confidence 高。
- 事实：concatenate 行号=`sequence_id//2`，fact.source_id→`sequence_n=source_id*2` 恒读**偶数
  (user) slot**；assistant-first 时读 placeholder slot，但镜像字段使 lineage 落到真实
  assistant。plural `source_external_ids` 含 pair 两 id → `MemoryEntry.source_external_id`
  置 None。
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

### F9 · 过时文档已在基线修正（无残留）
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
     题（temporal as-of 与非时间题未约束两类，公开动机待锚 issue#8）；框架按官方 no-filter
     口径完整传递 history + question date"。
   - `docs/reference/integration/lightmem.md`：补"LME time_stamp 为 method-derived tie-break
     （normalizer per-pair + assign_sequence regroup 覆写），source time 仅 session-level；
     placeholder 占结构 slot 但不改真实 turn 的 source id/speaker/lineage，也不在 pair 结构外
     额外拉宽派生间隔"。
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
- placeholder **占** sequence/time slot 但（i）从 prompt/token 过滤、（ii）镜像真实 child 使
  source id/speaker/lineage 不失真、（iii）占的是 pair 结构里本就存在的 assistant slot，故
  **不在 pair 结构外额外改变相邻真实 turn 的派生间隔**。
- 两层 timestamp：normalizer per-pair（+500ms，跨 pair 重置）→ assign_sequence regroup
  **覆写**（session_time 组内 base+i·500ms）；持久化 `time_stamp` 是 method tie-break，source
  time 仅在 session_time 可审计。
- question_date 与 history 的交叉属 benchmark-native temporal semantics + public-contract
  unresolved，框架已按官方 no-filter 完整保留，**无清洗、无代码修复项**。
- **本审计结论：B4 无需另发代码修复卡**；剩余为稳定文档回填 + B11 report 披露，交架构师强验收。
