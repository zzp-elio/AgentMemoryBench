# LightMem × MemBench 分层异常覆盖预检

> 执行者：Claude Sonnet 5（Claude Code，本会话系统提示自报模型确认，未跨模型切换）。
> 性质：零 API、零生产代码修改的取证与判词 note；按
> `cards/actor-prompt-lightmem-membench-anomaly-coverage-preflight.md` 全卡施工。
> worktree=`/Users/wz/Desktop/mb-actor-lightmem-membench-preflight`，
> branch=`actor/lightmem-membench-preflight`，基线=主树 `main` `7fe1f82`
> （`docs(lightmem): stage v7 reruns and membench audit`）。`data/`、`models/`、
> `third_party/benchmarks/` 为指向主工作区的只读软链，未 `git add`。

## 0. baseline / source / config / adapter identity

- 基线 commit：`7fe1f82`（开工时 `git status --short` 只有本人建立的三个软链
  `data`/`models`/`third_party/benchmarks`，均未纳入本次改动）。
- MemBench adapter：`src/memory_benchmark/benchmark_adapters/membench.py`
  （canonical pair split 主线 `ce1a9a8`+`d852fff`+`68b674b`，时间语义主线
  `2e6b4d7`）。
- LightMem adapter：`src/memory_benchmark/methods/lightmem_adapter.py`
  （`LIGHTMEM_ADAPTER_VERSION = "conversation-qa-v7"`）。
- LightMem method registry factory：`src/memory_benchmark/methods/registry.py:386-411`
  `_build_lightmem_system()`——**MemBench 的 `consume_granularity` 由
  `registry.py:399` 的表达式
  `"session" if halumem else "pair" if longmemeval else "turn"` 决定，MemBench
  落在 else 分支，取值 `"turn"`**（不是 `"pair"`）。已用真实 factory 现场验证：
  `system.consume_granularity == 'turn'`（见 §4 production-path 探针输出首行）。
- 生效配置：`configs/methods/lightmem.toml` `[smoke]`/`[official_full]` 均显式
  `lifecycle_profile="online_soft"`、`missing_timestamp_policy="preserve_none"`、
  `messages_use="hybrid"`。
- 标准 0_10k smoke 定义：`MEMBENCH_SMOKE_POLICY`
  （`history_axis="rounds"`, `default_history_limit=1`,
  `default_isolation_limit=1`, `default_question_limit=1`），四源各取 1 条
  trajectory，FirstAgent 按 `history_limit` 个源 step（=1）截断，ThirdAgent 按
  `history_limit*2` 个源 step（=2）截断。

## 1. 8 文件 census：方法、原始输出与公开例子定位

### 1.1 方法

两条独立零 API 扫描，互相交叉验证：

1. **正则字节级扫描**（`membench_census.py`，逐 trajectory 遍历 raw JSON，不构造
   `Turn` 对象）：统计 dict/string/other step、缺 key、空/空白正文、两种 time
   marker（`time:'…'` 与 `time'…'`，与生产正则
   `membench.py:736` `r"time:?\s*'(\d{4}-\d{2}-\d{2} \d{2}:\d{2})'"` 字节等价）、
   place 标记、FirstAgent 两侧时间对称性、duplicate tid（file 内）、
   trajectory/step 长度极值、最长单 step 文本。
2. **production adapter 全量交叉校验**（`membench_adapter_cross_check.py`，真实调用
   `MemBenchAdapter.load()` 逐 conversation 构造后立即丢弃）：校验 turn-id 唯一性、
   step→child 映射完备性（对照真实 `gold.evidence_group_sets`）、role 计数、
   `session_time is None`、`source_timestamp_embedded_in_content` marker 与
   `turn_time`/`None` 的一致性，以及 `build_turn_events()` round-trip（role/时间戳
   不因事件化改变）。

两个脚本均为临时文件（未提交），完整 stdout 见下方 §1.2/§1.3。

### 1.2 public input shape 完整 stdout（正则字节级扫描）

```
===== variant=0_10k =====

--- source=first_high path=FirstAgentDataHighLevel_multiple_0.json ---
trajectories=700 steps=15450 canonical_turns=30900
dict_steps=15450 string_steps=0 other_steps=0
dict_missing_user_key=0 dict_missing_agent_key=0
empty_user=0 empty_agent=0 empty_string_step=0
whitespace_only_user=0 whitespace_only_agent=0 whitespace_only_string=0
user_time_kinds={'colon': 15450}
agent_time_kinds={'colon': 15450}
string_time_kinds={}
user_has_place=15450 agent_has_place=15450 string_has_place=0
both_side_timed=15450 only_user_timed=0 only_agent_timed=0 neither_timed=0
side_time_equal=15450 side_time_diff=0
duplicate_tid_within_file=0 empty_message_list=0
traj_step_len_min=8 traj_step_len_max=44
qa_missing_fields={}
target_step_id_empty=1 target_step_id_total_refs=2405 target_step_id_oob_count=0
longest_step_text_len=450 at first_high:highlevel/book[75] step3 tid=75

--- source=first_low path=FirstAgentDataLowLevel_multiple_0.json ---
trajectories=900 steps=104470 canonical_turns=208940
dict_steps=104470 string_steps=0 other_steps=0
dict_missing_user_key=0 dict_missing_agent_key=0
empty_user=0 empty_agent=0 empty_string_step=0
whitespace_only_user=0 whitespace_only_agent=0 whitespace_only_string=0
user_time_kinds={'colon': 104470}
agent_time_kinds={'colon': 104470}
string_time_kinds={}
user_has_place=104470 agent_has_place=104470 string_has_place=0
both_side_timed=104470 only_user_timed=0 only_agent_timed=0 neither_timed=0
side_time_equal=104470 side_time_diff=0
duplicate_tid_within_file=0 empty_message_list=0
traj_step_len_min=13 traj_step_len_max=193
qa_missing_fields={}
target_step_id_empty=0 target_step_id_total_refs=2410 target_step_id_oob_count=1
longest_step_text_len=393 at first_low:lowlevel_rec/book[19] step0 tid=19

--- source=third_high path=ThirdAgentDataHighLevel_multiple_0.json ---
trajectories=400 steps=5302 canonical_turns=5302
dict_steps=0 string_steps=5302 other_steps=0
dict_missing_user_key=0 dict_missing_agent_key=0
empty_user=0 empty_agent=0 empty_string_step=0
whitespace_only_user=0 whitespace_only_agent=0 whitespace_only_string=0
user_time_kinds={}
agent_time_kinds={}
string_time_kinds={'colon': 5302}
user_has_place=0 agent_has_place=0 string_has_place=5302
both_side_timed=0 only_user_timed=0 only_agent_timed=0 neither_timed=0
side_time_equal=0 side_time_diff=0
duplicate_tid_within_file=0 empty_message_list=0
traj_step_len_min=6 traj_step_len_max=23
qa_missing_fields={}
target_step_id_empty=0 target_step_id_total_refs=1481 target_step_id_oob_count=0
longest_step_text_len=747 at third_high:highlevel/emotion[14] step0 tid=14

--- source=third_low path=ThirdAgentDataLowLevel_multiple_0.json ---
trajectories=1400 steps=19285 canonical_turns=19285
dict_steps=0 string_steps=19285 other_steps=0
dict_missing_user_key=0 dict_missing_agent_key=0
empty_user=0 empty_agent=0 empty_string_step=0
whitespace_only_user=0 whitespace_only_agent=0 whitespace_only_string=0
user_time_kinds={}
agent_time_kinds={}
string_time_kinds={'nocolon': 19285}
user_has_place=0 agent_has_place=0 string_has_place=19285
both_side_timed=0 only_user_timed=0 only_agent_timed=0 neither_timed=0
side_time_equal=0 side_time_diff=0
duplicate_tid_within_file=0 empty_message_list=0
traj_step_len_min=4 traj_step_len_max=36
qa_missing_fields={}
target_step_id_empty=0 target_step_id_total_refs=4568 target_step_id_oob_count=0
longest_step_text_len=1399 at third_low:conditional/items[47] step1 tid=47

===== variant=100k =====

--- source=first_high path=FirstAgentDataHighLevel_multiple_100.json ---
trajectories=140 steps=45133 canonical_turns=90266
dict_steps=45133 string_steps=0 other_steps=0
dict_missing_user_key=0 dict_missing_agent_key=0
empty_user=0 empty_agent=0 empty_string_step=0
whitespace_only_user=0 whitespace_only_agent=0 whitespace_only_string=0
user_time_kinds={'no_marker': 42000, 'colon': 3133}
agent_time_kinds={'no_marker': 42000, 'colon': 3133}
string_time_kinds={}
user_has_place=3133 agent_has_place=3133 string_has_place=0
both_side_timed=3133 only_user_timed=0 only_agent_timed=0 neither_timed=42000
side_time_equal=3133 side_time_diff=0
duplicate_tid_within_file=0 empty_message_list=0
traj_step_len_min=309 traj_step_len_max=341
qa_missing_fields={}
target_step_id_empty=0 target_step_id_total_refs=485 target_step_id_oob_count=0
longest_step_text_len=1524 at first_high:highlevel/food[9] step23 tid=9

--- source=first_low path=FirstAgentDataLowLevel_multiple_100.json ---
trajectories=360 steps=149777 canonical_turns=299554
dict_steps=149777 string_steps=0 other_steps=0
dict_missing_user_key=0 dict_missing_agent_key=0
empty_user=0 empty_agent=0 empty_string_step=0
whitespace_only_user=0 whitespace_only_agent=0 whitespace_only_string=0
user_time_kinds={'no_marker': 108000, 'colon': 41777}
agent_time_kinds={'no_marker': 108000, 'colon': 41777}
string_time_kinds={}
user_has_place=41777 agent_has_place=41777 string_has_place=0
both_side_timed=41777 only_user_timed=0 only_agent_timed=0 neither_timed=108000
side_time_equal=41777 side_time_diff=0
duplicate_tid_within_file=0 empty_message_list=0
traj_step_len_min=313 traj_step_len_max=491
qa_missing_fields={}
target_step_id_empty=0 target_step_id_total_refs=965 target_step_id_oob_count=1
longest_step_text_len=1524 at first_low:simple/roles[8] step227 tid=8

--- source=third_high path=ThirdAgentDataHighLevel_multiple_100.json ---
trajectories=80 steps=25049 canonical_turns=25049
dict_steps=0 string_steps=25049 other_steps=0
dict_missing_user_key=0 dict_missing_agent_key=0
empty_user=0 empty_agent=0 empty_string_step=0
whitespace_only_user=0 whitespace_only_agent=0 whitespace_only_string=0
user_time_kinds={}
agent_time_kinds={}
string_time_kinds={'no_marker': 24000, 'colon': 1049}
user_has_place=0 agent_has_place=0 string_has_place=1049
both_side_timed=0 only_user_timed=0 only_agent_timed=0 neither_timed=0
side_time_equal=0 side_time_diff=0
duplicate_tid_within_file=0 empty_message_list=0
traj_step_len_min=307 traj_step_len_max=321
qa_missing_fields={}
target_step_id_empty=0 target_step_id_total_refs=293 target_step_id_oob_count=0
longest_step_text_len=7236 at third_high:highlevel/emotion[13] step304 tid=13

--- source=third_low path=ThirdAgentDataLowLevel_multiple_100.json ---
trajectories=280 steps=87779 canonical_turns=87779
dict_steps=0 string_steps=87779 other_steps=0
dict_missing_user_key=0 dict_missing_agent_key=0
empty_user=0 empty_agent=0 empty_string_step=0
whitespace_only_user=0 whitespace_only_agent=0 whitespace_only_string=0
user_time_kinds={}
agent_time_kinds={}
string_time_kinds={'no_marker': 84000, 'colon': 3779}
user_has_place=0 agent_has_place=0 string_has_place=3779
both_side_timed=0 only_user_timed=0 only_agent_timed=0 neither_timed=0
side_time_equal=0 side_time_diff=0
duplicate_tid_within_file=0 empty_message_list=0
traj_step_len_min=303 traj_step_len_max=336
qa_missing_fields={}
target_step_id_empty=0 target_step_id_total_refs=913 target_step_id_oob_count=0
longest_step_text_len=7236 at third_low:conditional/events[6] step218 tid=6

===== GRAND TOTAL (8 files) =====
trajectories=4260
steps=452245
canonical_turns=767075
dict_steps=314830
string_steps=137415
target_step_id_oob_count=2
target_step_id_empty=1
only_user_timed=0
only_agent_timed=0
both_side_timed=164830
side_time_diff=0
```

**GRAND TOTAL 与 `docs/survey/datasets/membench.md`/canonical-split-implementation.md
记录的 4,260 trajectories / 452,245 source steps / 767,075 canonical turns 完全一致**，
current-main 未发生数据漂移。

### 1.3 production adapter 交叉校验完整 stdout

```
===== variant=0_10k adapter cross-check =====
total_conversations=3400 (first=1600 third=1800)
total_turns=264427
session_time_not_none=0 (期望 0)
turn_id_dupes_within_session=0 (期望 0)
role_counts={'user': 144507, 'assistant': 119920, 'other': 0}
first_pair_role_wrong=0 (期望 0)
third_singleton_role_wrong=0 (期望 0)
timed_turn_effective_ts_none=0 (期望 0，标 embedded=True 却 turn_time=None)
untimed_turn_effective_ts_nonnone=0 (期望 0，标 embedded=False 却 turn_time 非空)
step_child_incomplete=0 (期望 0)
event_role_mismatch=0 (期望 0)
event_ts_mismatch=0 (期望 0)

===== variant=100k adapter cross-check =====
total_conversations=860 (first=500 third=360)
total_turns=502648
session_time_not_none=0 (期望 0)
turn_id_dupes_within_session=0 (期望 0)
role_counts={'user': 307738, 'assistant': 194910, 'other': 0}
first_pair_role_wrong=0 (期望 0)
third_singleton_role_wrong=0 (期望 0)
timed_turn_effective_ts_none=0 (期望 0，标 embedded=True 却 turn_time=None)
untimed_turn_effective_ts_nonnone=0 (期望 0，标 embedded=False 却 turn_time 非空)
step_child_incomplete=0 (期望 0)
event_role_mismatch=0 (期望 0)
event_ts_mismatch=0 (期望 0)
```

即：全部 767,075 canonical turn（`role_counts` 两个 variant 相加
`user=452,245` `assistant=314,830`，与 dict_steps/string_steps 恰好对齐：
`dict_steps=314,830`→各贡献 1 个 assistant turn，`total_steps=452,245`→各贡献 1 个
user turn）、全部 `session_time` 恒 `None`、turn-id 在各自 session 内零重复、
`source_timestamp_embedded_in_content` marker 与 `turn_time`/`None` 完全一致（无
"标记有时间却结构化失败"或"标记无时间却仍有值"的漂移）、step→child 映射对照真实
`GoldEvidenceGroup` 零缺陷、`build_turn_events()` round-trip 零 role/时间戳漂移。

### 1.4 已知公开异常（真实位置）

1. **FirstAgent 两侧时间恒对称**：全部 164,830 个双侧均带 marker 的 dict step，
   `side_time_equal=164,830`、`side_time_diff=0`；`only_user_timed`/
   `only_agent_timed` 恒为 0（跨 8 文件）。**真实数据中不存在"一侧有时一侧无时"
   的 FirstAgent pair**——§4 该行反例改用 synthetic。
2. **两种 time marker 格式按文件严格分区，不跨文件混布（0-10k）**：
   `first_high`/`first_low`/`third_high` 均 100% `colon`；`third_low` 100%
   `nocolon`（19,285/19,285）。**`nocolon` 格式在 100k 完全不存在**
   （100k `third_high`/`third_low` 的 `string_time_kinds` 只有
   `no_marker`/`colon` 两个 key，无 `nocolon`）——`nocolon` 是 0-10k
   `third_low` 独有形状，标准 smoke 恰好覆盖它（见 §6）。
3. **100k no-time noise 占比 83.84%**（258,000/307,738），与既有
   `membench-100k-time-ruling.md` 记录的数字完全一致；均结构化为
   `turn_time=None`。
4. **未发现新的结构异常**：0 个缺 `user`/`agent` key、0 个空/空白 user/agent/
   string 正文、0 个空 `message_list`、0 个 file 内重复 `tid`、0 个 QA 缺字段。
   数据集在 canonical-split-implementation.md 记录的强度上继续保持干净，
   本轮亲读未发现新形状。
5. **最长单 step 文本 7,236 字符**（100k third_high/third_low 均有此长度，
   位于 `third_high:highlevel/emotion[13] step304 tid=13` 与
   `third_low:conditional/events[6] step218 tid=6`），仅记录长度与定位，未把全文
   倾倒进本 note。
6. **trajectory 源 step 数极值**：最短 4 步（0-10k third_low
   `conditional/items` 内某条），最长 491 步（100k first_low
   `simple/roles[8] tid=8`）。

## 2. private gold shape 隔离统计

独立脚本 `membench_private_gold_census.py`，只输出 `variant/source/qtype/scenario/
tid/n_steps/target_step_id` 定位信息，不展示 `answer`/`ground_truth` 内容，不用于
挑选后续 sentinel。完整 stdout：

```
EMPTY_TARGET variant=0_10k source=first_high qtype=highlevel_rec scenario=movie tid=25 n_steps=35
OOB_TARGET variant=0_10k source=first_low qtype=comparative scenario=events tid=4 n_steps=111 target_step_id=111 (len(target_step_id)=2)
OOB_TARGET variant=100k source=first_low qtype=comparative scenario=events tid=4 n_steps=411 target_step_id=411 (len(target_step_id)=2)
```

与 `docs/survey/datasets/membench.md` §4 记录的"越界 target_step_id 2 例
（两规模同源 comparative/events tid=4，=len 疑似官方 off-by-one）；空
target_step_id 1 例（0-10k FirstHigh highlevel_rec/movie tid=25）"精确一致，
current-main 未漂移，未发现新的私有异常。两例 OOB 均满足
`target_step_id == n_steps`（0 基越界一格，即用 1 基长度当 0 基下标），支持既有
"官方 off-by-one"判断。这两条私有事实**只影响 evaluator 处置**（`membench.py`
`_membench_evidence_group_sets()` 已把它们分别建为 `mapping_status="unmatched"`
与空 `groups`），未在 §4 探针的任何 method-visible payload 中出现。

## 3. production-path 强反例：逐层 payload

探针脚本（临时，未提交）：
`lightmem_membench_production_path_probe.py` + `..._probe2.py`。调用链严格复用
生产入口，不 fake 映射 helper、不跳过 event stream、不调 LLM/embedding API：

```
MemBenchAdapter.load()（真实 adapter）
  -> build_turn_events() + GranularityAggregator(provider.consume_granularity)
  -> runners.prediction._ingest_memory_provider_conversation()（真实 dispatch loop）
  -> LightMem.ingest()/end_session()/end_conversation()（真实 adapter 方法）
  -> FakeLightMemoryBackend.add_memory()（fake，只记录调用；复用
     tests/test_lightmem_adapter.py 既有 fixture 类，只读引用未改测试文件）
```

`LightMem` 实例通过真实 `registry._build_lightmem_system(MethodBuildContext(...,
benchmark_name="membench"))` 构造后，只把 `_backend_factory` 换成 fake；
`consume_granularity` 保留 registry 的真实选择。

### 3.0 关键发现：MemBench 走 `consume_granularity="turn"`，不是 `"pair"`

`registry.py:399` 的真实表达式是
`"session" if halumem else "pair" if longmemeval else "turn"`——LoCoMo、BEAM、
MemBench 都落在 `else` 分支，取 `"turn"`。这意味着 **event stream 从不为
MemBench 产出 `TurnPair`**，`ingest()` 每次只收到一个 `TurnEvent`；
`_native_turn_batch()` 用该单个 event 构造只含 1 条 turn 的 session，
`_normalize_session_to_pairs()` 因而永远只看到单侧真实 turn，另一侧必然补
placeholder。

这与既有测试
`test_lightmem_membench_canonical_pair_yields_two_real_pair_candidate_ids` /
`test_lightmem_membench_extraction_batch_keeps_pair_lineage_by_source_id`
的前提**不同**：那两个测试直接调用 `system._normalize_session_to_pairs(session,
conversation)`，手工构造一个**同时含 user+assistant 两个真实 turn**的 session
（等价于"pair 粒度"消费），从而得到"一个 pair 两侧都真实、
`source_external_ids=['1:user','1:assistant']`"的结果。**这个 2-真实-id 场景在
当前生产 `ingest()` 调用链中不会发生**——它是对 helper 函数的正确单元测试，但不是
`provider.ingest(...) → actual add_memory batch` 这一层的真实路径。下方 ROW1 用
真实 production 调用链证明了这一点。

### 3.1 ROW1 — FirstAgent 正常 pair（真实数据，0-10k FirstAgentDataHighLevel 第一条
trajectory 的 step0）

```
[system] consume_granularity from real registry factory = 'turn'
real conversation_id=first-high-highlevel-movie-0
step0 turn_ids=['1:user', '1:assistant'] roles=['user', 'assistant']
step0[user].content="I really love The Godfather; it's such a classic with its powerful storytelling and unforgettable characters. (place: Boston, MA; time: '2024-10-01 08:00' Tuesday)"
step0[assistant].content="I'm glad to hear that you love The Godfather! It's a timeless masterpiece that truly captures the complexity of family and power. Do you have a favorite character or scene from the film? (place: Boston, MA; time: '2024-10-01 08:00' Tuesday)"

--- ROW1 FirstAgent step0 (1 step = 2 canonical turns): add_memory() 调用序列 (共 2 次) ---
  call[0] kwargs={'force_segment': False, 'force_extract': False}
    msg[0] role='user' content="I really love The Godfather; ..." time_stamp='2024-10-01 08:00' external_id='1:user' source_external_ids=['1:user'] placeholder=False
    msg[1] role='assistant' content='' time_stamp='2024-10-01 08:00' external_id='1:user' source_external_ids=['1:user'] placeholder=True
  call[1] kwargs={'force_segment': True, 'force_extract': True}
    msg[0] role='user' content='' time_stamp='2024-10-01 08:00' external_id='1:assistant' source_external_ids=['1:assistant'] placeholder=True
    msg[1] role='assistant' content="I'm glad to hear that you love The Godfather! ..." time_stamp='2024-10-01 08:00' external_id='1:assistant' source_external_ids=['1:assistant'] placeholder=False
session_reports=()
```

**事实**：真实 MemBench FirstAgent 的一个 `{user, agent}` source step，在生产
`ingest()` 路径下产出 **两次独立 `add_memory()` 调用**，每次恰好 1 条真实消息 +
1 条结构占位；**从未有一次调用同时携带两侧真实内容**。两次调用的
`source_external_ids` 各自都是**单元素**列表（`['1:user']` 与
`['1:assistant']`），精确、无歧义地指向各自真实 turn——比既有 helper 单测展示的
"两个真实 id 的模糊候选集"更精确，但生成机制完全不同。role 不变、content
不丢、时间戳一致（都是 `'2024-10-01 08:00'`）、无跨 session 污染。**不是
crash/drop/role 错误/时间错误**，但是一条此前未被任何文档记录的真实生产行为
分叉，详见 §5 分层表判词。

### 3.2 ROW2 — ThirdAgent 单 user（真实数据，0-10k ThirdAgentDataHighLevel 第一条
trajectory 的 step0）

```
real conversation_id=third-high-highlevel-movie-0
step0 turn_ids=['1'] roles=['user']
step0[0].content="I really love Casablanca; the timeless romance and memorable lines always draw me in. (place: Boston, MA; time: '2024-10-01 08:00' Tuesday)"

--- ROW2 ThirdAgent step0 (1 step = 1 canonical turn): add_memory() 调用序列 (共 1 次) ---
  call[0] kwargs={'force_segment': True, 'force_extract': True}
    msg[0] role='user' content="I really love Casablanca; ..." time_stamp='2024-10-01 08:00' external_id='1' source_external_ids=['1'] placeholder=False
    msg[1] role='assistant' content='' time_stamp='2024-10-01 08:00' external_id='1' source_external_ids=['1'] placeholder=True
```

真实 user observation 正确产出 `[real user, placeholder assistant]`；单条
crop 场景下 `force_extract=True` 是因为该 crop 恰好触发 `end_conversation`，与
smoke/full 全量场景一致（该 kwargs 只在 pending 批次最终写出时为 True）。

### 3.3 ROW3 — `time:`（colon）与 `time'`（no-colon）两种真实格式

```
colon-format turn_id=1:user role=user turn_time='2024-10-01 08:00' embedded_marker=True
    content="I really love The Godfather; ... (place: Boston, MA; time: '2024-10-01 08:00' Tuesday)"
colon-format turn_id=1:assistant role=assistant turn_time='2024-10-01 08:00' embedded_marker=True
nocolon-format turn_id=1 role=user turn_time='2024-10-01 08:00' embedded_marker=True
    content="My subordinate is Maya Carter. (place: Boston, MA; time'2024-10-01 08:00' Tuesday)"

--- ROW3 两种 time marker 格式: add_memory() 调用序列 (共 3 次) ---
  call[0]: msg[0] role=user content=(colon 原文完整保留) time_stamp='2024-10-01 08:00' ...
  call[1]: msg[1] role=assistant content=(colon 原文完整保留) time_stamp='2024-10-01 08:00' ...
  call[2]: msg[0] role=user content="My subordinate is Maya Carter. (place: Boston, MA; time'2024-10-01 08:00' Tuesday)" time_stamp='2024-10-01 08:00' ...

vendored-normalizer: external_id=1:user time_stamp(adapter)='2024-10-01 08:00' -> time_stamp(normalized)='2024-10-01T08:00:00.000' weekday='Tue'
vendored-normalizer: external_id=1:assistant time_stamp(adapter)='2024-10-01 08:00' -> time_stamp(normalized)='2024-10-01T08:00:01.000' weekday='Tue'
vendored-normalizer: external_id=1 time_stamp(adapter)='2024-10-01 08:00' -> time_stamp(normalized)='2024-10-01T08:00:02.000' weekday='Tue'
```

两种格式都被生产正则正确提取为 `turn_time='2024-10-01 08:00'`，content 原文
（含 `place`/`time` 片段）**逐字节保留、不删除、不重复前置**；随后真实 vendored
`MessageNormalizer.normalize_messages()`（非 mock，从
`import_lightmem_classes()` 取得的官方类）成功把两种格式都解析为合法 ISO
`time_stamp` 与正确 `weekday`，**不 raise**；相同 raw timestamp key
（`'2024-10-01 08:00'`）按官方 `last_timestamp_map` 逐次 `+1000ms` 递增（
`08:00:00.000`→`08:00:01.000`→`08:00:02.000`），与既有 500ms/1000ms
"仅作用于重复 raw timestamp key"裁决一致，未发现新契约冲突。

### 3.4 ROW4 — 100k 真实 no-time noise + 真实/合成 timed step 混合

```
real conversation_id=first-high-highlevel-movie-0（100k FirstAgentDataHighLevel）
noise step0 embedded_marker=[False, False]
noise step0 turn_time=[None, None]
noise step0[user].content[:120]='I just saw the news that Donald Trump has pledged to do everything...'

--- ROW4: add_memory() 调用序列 (共 4 次) ---
  call[0] kwargs={force_segment: False, force_extract: False}
    msg[0] role=user content=(真实 noise 正文完整保留，未阉割) time_stamp=None external_id='1:user' source_external_ids=['1:user'] placeholder=False
    msg[1] role=assistant content='' time_stamp=None external_id='1:user' source_external_ids=['1:user'] placeholder=True
  call[1] kwargs={force_segment: False, force_extract: False}
    msg[0] role=user content='' time_stamp=None external_id='1:assistant' placeholder=True
    msg[1] role=assistant content=(真实 noise 正文完整保留) time_stamp=None external_id='1:assistant' placeholder=False
  call[2]/call[3]（合成 timed step，Godfather 文本）: time_stamp='2024-10-01 08:00' 正确结构化，与 noise 段落零串扰
```

无时间 noise 的**真实**正文完整原样送达 `add_memory()`，`time_stamp=None`
无损透传（`missing_timestamp_policy=preserve_none` 生效，未 raise、未回填 QA
time/wall clock/sentinel）；随后一个真实时间 step 正确恢复为非空 `time_stamp`，
两者互不污染。这证明 `lightmem-missing-time-online-soft-implementation.md`
已验收的 Phase B 契约在 **MemBench 特有的 turn-granularity 双 call 拆分**下依然
成立——此前该 Phase B 验收使用的是通用/LoCoMo 场景，未曾在 MemBench 真实
production-path 下重新确认。

### 3.5 ROW5（synthetic）— FirstAgent 一侧有时一侧无时

§1.4 已证明真实数据中不存在此形状（`only_user_timed=only_agent_timed=0`，
跨全部 8 文件）。按卡面允许，构造合成反例：

```
user turn_time='2024-10-01 08:00' embedded=True
assistant turn_time=None embedded=False

--- ROW5: add_memory() 调用序列 (共 2 次) ---
  call[0]: msg[0] role=user time_stamp='2024-10-01 08:00' external_id='1:user' ...
  call[1]: msg[1] role=assistant time_stamp=None external_id='1:assistant' ...
```

两侧各自独立判定，**不从 peer fallback**；user 侧非空、assistant 侧
`preserve_none` 生效为 `None`；pair lineage（`external_id`/
`source_external_ids`）与 role 仍完整。

### 3.6 ROW6 — 两个连续 source step，不跨 step union candidate ids

真实数据 0-10k FirstAgentDataHighLevel 第一条 trajectory 的 step0+step1：

```
turn_ids in order=['1:user', '1:assistant', '2:user', '2:assistant']
--- ROW6: add_memory() 调用序列 (共 4 次) ---
  call[0]: source_external_ids=['1:user']（step0 user）
  call[1]: source_external_ids=['1:assistant']（step0 assistant）
  call[2]: source_external_ids=['2:user']（step1 user，time_stamp='2024-10-01 08:01'，与 step0 的 08:00 不同）
  call[3]: source_external_ids=['2:assistant']（step1 assistant）
union of all source_external_ids seen across all calls=['1:assistant', '1:user', '2:assistant', '2:user']
```

四次调用各自的 `source_external_ids` **严格单元素**，从未出现跨 step 合并的
多元素列表；`_stamp_pair_ids()` 的作用域天然被 turn-granularity 的单 turn
normalize 调用限制在当前 step 内，不可能 union 两个 step。此行同时印证了
canonical-split-implementation.md R1 提到的"承重门"（该门用手工双 pair session
测试同一结论）在真实逐 turn 生产路径下同样成立，只是生产路径的隔离粒度比该门
展示的更细（每次 1 turn 而不是 1 pair）。

### 3.7 ROW7 — retrieve() evidence：zero-hit / complete-hit / malformed lineage

```
7a zero-hit items=() -> semantic=EvidenceAssertion(status='valid', reason_code=None, reason=None) granularity=turn
7b complete-hit items=(1 item) -> semantic=EvidenceAssertion(status='valid', reason_code=None, reason=None) granularity=turn
7c malformed(items=None) -> semantic=EvidenceAssertion(status='n_a', reason_code='retrieval_hit_lineage_incomplete', ...) granularity=none
7d malformed payload (含空白 id) -> _retrieved_items_from_lightmem_memories 返回 = None
7d evidence -> semantic=EvidenceAssertion(status='n_a', reason_code='retrieval_hit_lineage_incomplete', ...) granularity=none
7e legal payload -> items=(RetrievedItem(item_id='mem-2', ..., source_turn_ids=('1:user', '1:assistant'), ...),)
```

真实 0-hit（空 tuple，不是 `None`）正确保持 `valid/turn`（Recall 分子记 0，不是
"不可评"）；完整合法命中同样 `valid/turn`；**混入一个非法 id（含首尾空白）的
payload 会让 `_retrieved_items_from_lightmem_memories()` 把整批 items 判为
`None`**（不是静默丢弃坏 id、保留好 id），随后 `_build_retrieval_evidence(None)`
正确降级为 `n_a/none`——符合 `actor-handbook.md` §6 "不要把坏 lineage 过滤成好
lineage"的既有纪律，本轮在 MemBench 分支上重新确认成立。

### 3.8 ROW8 — conversation 隔离

> **R1 订正（2026-07-19）**：本节首轮把两个 conversation 的局部 child id 集合写成
> “完全不交叉”是错误的；两边都可从 `1:user`/`1:assistant` 重新编号。隔离成立的证据是
> backend/storage namespace 与 isolation key 不同，不是 local id 全局唯一。下方首轮 stdout
> 作为历史探针保留，不再承载“id 集合不交叉”结论。

```
conv_a=first-high-highlevel-movie-0 conv_b=first-high-highlevel-movie-1
backend_a is backend_b: False (期望 False)
backend_a.add_memory 调用次数=26   backend_b.add_memory 调用次数=34
backend_a 涉及 external_id 集合=['1:assistant','1:user', ..., '13:assistant','13:user']  (13 步)
backend_b 涉及 external_id 集合=['1:assistant','1:user', ..., '17:assistant','17:user']  (17 步)
pending_batches 残留(应为空)={}
conversation_metadata 中 conv_a.conversation_id 是否串到 conv_b: True（即未被覆盖污染，取的是各自正确的值）
```

两个真实 tid（`highlevel/movie` scenario 内 tid=0 和 tid=1）分别产出独立
`FakeLightMemoryBackend` 实例（`is` 比较为 `False`），`external_id` 集合完全不
交叉（backend_a 只到 `13:*`，backend_b 从 `1:*` 到 `17:*`，两者互不包含对方
turn id），两个 conversation 各自 `end_conversation()` 后 `_native_pending_batches`
清空、无残留跨 conversation 状态，`_conversation_metadata` 按 namespace 正确隔离。

### 3.9 负空间检查

以上全部 §3.1-§3.8 探针的 `add_memory()` 调用参数、`RetrievedItem`/
`RetrievalEvidence` 构造中，**未出现任何 `answer`、`ground_truth`、
`target_step_id`、gold group 或 judge label 字段**——探针构造 `Conversation` 时
虽然透传了真实 `conv.gold_answers`（框架 `Conversation` 对象的私有字段），但
`LightMem._normalize_session_to_pairs()`/`_native_conversation_from_events()`
只读 `session.turns`，从不读取 `conversation.gold_answers`；上方逐条 message
dump 只含 `role/content/speaker_id/speaker_name/time_stamp/external_id/
source_external_ids` 字段，人工逐条核对确认干净。

## 4. 分层 anomaly coverage 表

| 异常类 | 真实位置/规模 | 风险 | census | production-path test/probe | evaluator-private test | 是否还需真实 sentinel | 当前判词/缺口 |
|---|---|---|---|---|---|---|---|
| FirstAgent dict step 正常拆分（user+assistant 两 child） | 全 8 文件 314,830 个 dict step | 中（role/content 混淆会致命） | §1.2/1.3 零缺陷 | §3.1 ROW1（真实数据，turn-granularity 双 call） | `test_lightmem_membench_canonical_pair_yields_two_real_pair_candidate_ids` 覆盖 helper 层单侧场景，非本生产路径 | 建议：见 §7（验证 STM 跨多次 `add_memory` 调用后 extraction LLM 是否真的同时看到两侧真实内容） | census+production-path 已关闭 crash/role/id 正确性；**STM 跨调用聚合行为需真实 backend 才能证明，标记为待 sentinel** |
| ThirdAgent string step 单 user | 全 8 文件 137,415 个 string step | 低 | §1.2/1.3 零缺陷 | §3.2 ROW2（真实数据） | — | 否 | 已关闭，不需塞进付费 smoke |
| `time:`（colon）格式 | 0-10k first_high/first_low/third_high 全量 + 100k 全部有时 step（49,738） | 中 | §1.2 精确计数 | §3.3 ROW3（真实数据 + 真实 vendored normalizer） | — | 否 | 已关闭 |
| `time'`（no-colon）格式 | **仅** 0-10k third_low 19,285 条，100k 不存在 | 中 | §1.2/1.4 已确认边界 | §3.3 ROW3（真实数据 + 真实 vendored normalizer） | — | 否 | 已关闭；标准 smoke 天然覆盖（third_low 是四源之一） |
| 100k no-time noise（`turn_time=None`） | 100k 四源合计 258,000/307,738=83.84% | 高（曾经被 sibling/session 时间污染，见 `membench-100k-time-ruling.md`） | §1.2 精确计数、与既有裁决数字一致 | §3.4 ROW4（真实 noise 正文 + `preserve_none` 端到端，turn-granularity 特有双 call 场景下重新确认） | — | 是，见 §7 | census+production-path 已关闭"造时间/丢内容"；**真实 backend 内 STM/向量写入路径未覆盖，标记为待 sentinel** |
| FirstAgent 一侧有时一侧无时 | **真实数据中不存在**（`only_user_timed=only_agent_timed=0`，全 8 文件） | 低（数据层面不可达） | §1.2/1.4 已证明不存在 | §3.5 ROW5（synthetic，按卡允许） | — | 否 | 已用 synthetic 关闭，不需真实 sentinel（真实数据没有这个形状） |
| 两个连续 source step 不跨 union | 结构性质，适用全部 dict step 序列 | 高（跨 step 污染会让 Recall 分母/分子失真） | 隐含在 §1.3 step_child_incomplete=0 | §3.6 ROW6（真实数据，逐 call 单元素验证） | — | 否 | 已关闭 |
| zero-hit / complete-hit / malformed lineage evidence | 结构性质，检索结果形状 | 高（malformed 若被误判 valid 会污染 Recall） | 不适用（检索行为非数据形状） | §3.7 ROW7（含真实 `_retrieved_items_from_lightmem_memories` 边界） | 不适用（不涉及 gold 字段） | 否 | 已关闭 |
| conversation 隔离（跨 tid） | 结构性质，适用全部 4,260 trajectory | 高（跨 conversation 串写是严重污染） | 不适用 | §3.8 ROW8（真实数据，2 个真实 tid） | — | 否 | 已关闭 |
| 越界 `target_step_id`（2 例） | 0-10k/100k 同源 `comparative/events` tid=4 | 高（若泄漏到 method 或错记 1.0） | §2 隔离统计精确定位 | 不适用（私有字段不可达 method，已由 `_membench_evidence_group_sets` 建 `mapping_status="unmatched"`） | 由 `test_membench_retrieval_recall.py` 既有 OOB 诊断测试覆盖 | 否 | 已关闭，只走 evaluator-private 通道 |
| 空 `target_step_id`（1 例） | 0-10k FirstHigh `highlevel_rec/movie` tid=25 | 中 | §2 隔离统计精确定位 | 不适用 | `membench_recall.py` 已有空 group→`n/a` 分支覆盖 | 否 | 已关闭 |
| dict 缺 `user`/`agent` key、空/空白正文、空 `message_list`、file 内重复 tid、QA 缺字段 | 全 8 文件均为 0 例 | — | §1.2 精确计数，均为 0 | 不适用（数据中不存在） | 不适用 | 否 | 未观测到，无需覆盖；后续若数据更新需重跑本 census |
| 最长单 step 文本（7,236 字符） | 100k third_high/third_low 各 1 例 | 低（超长文本可能影响 token 预算，非正确性风险） | §1.2/1.4 已定位 | 未单独探针（非 crash/role/time 类高风险异常） | — | 否，若后续要验证 token 预算另评估 | 只记录位置，未列为高风险异常，不强制覆盖 |

## 5. 标准 `0_10k` smoke 的覆盖 / 盲区

标准 smoke = 四源各 1 条 trajectory，FirstAgent 截 1 个源 step（2 canonical
turn），ThirdAgent 截 2 个源 step（2 canonical turn，均为 user role）。

**已覆盖**：

- FirstAgent 正常 pair 拆分（turn-granularity 双 call，first_high/first_low）；
- ThirdAgent 单 user placeholder（third_high/third_low）；
- 两种 time marker 格式（colon 由 first_high/first_low/third_high 覆盖，
  nocolon 由 third_low 100% 覆盖）；
- ThirdAgent 两个连续 source step（third_high/third_low 的 `history_limit*2`
  截断天然产出 2 个连续 string step）；
- conversation 隔离的基本形状（4 个不同 tid 分属 4 个不同 source
  namespace，虽然不是本 note §3.8 测的"同一 source 内两个 tid"）。

**盲区（默认 smoke 不覆盖，本轮已用零 API 探针补齐）**：

1. **FirstAgent 两个连续 source step**（即同一 trajectory 内两个 pair-step 首尾
   相邻，验证不跨 step union candidate ids）——smoke 的 `history_limit=1` 只截
   1 个源 step，永远不会产出这个形状；由 §3.6 ROW6 补齐。
2. **同一 source 文件内两个不同 tid 的隔离**——smoke 每源只取 1 条
   trajectory（`per_source_limit=1`）；由 §3.8 ROW8 补齐。
3. **100k 全部形状**（no-time noise、100k 独有的极端长 trajectory 等）——
   smoke 固定用 `0_10k` 变体，与 100k 完全无关；由 §3.4 ROW4 部分补齐（仅
   production-path 层，真实 backend 层仍缺，见 §7）。
4. **FirstAgent 一侧有时一侧无时**——真实数据不存在，smoke 天然也不会产出；
   §3.5 ROW5 synthetic 补齐。
5. **检索侧 zero-hit/malformed lineage**——smoke 只验证 ingest 侧数据形状，不
   驱动检索结果分布；由 §3.7 ROW7 补齐。

## 6. 是否需要 100k real sentinel

**建议保留 100k real sentinel 需求**，理由集中在唯一未被 fake backend 证明的
性质：**真实 vendored `ShortMemBufferManager` 的 STM 是否真的跨多次
`add_memory()` 调用累积消息、进而让 extraction LLM 在同一次调用中同时看到
FirstAgent pair 的真实 user 与真实 assistant 内容**。这一性质由 §3.0/§3.1 的
`turn`-granularity 发现直接引出：由于生产路径把每个 pair 拆成两次
`add_memory()` 调用（各含 1 真 1 占位），"`hybrid` 让 assistant 内容进入
extraction"这一既有裁决（`lightmem-messages-membench-beam-role-audit.md`）
在 MemBench 上是否真正生效，**取决于真实 STM 缓冲区跨调用合并的行为，fake
backend 无法证明**（fake backend 直接替换了整个 `LightMemory` 实例，STM 逻辑
在被替换对象内部，观测不到）。这属于"只有真实 LightMem normalizer/extraction
才能证明"的性质，按卡面裁定必须留给真实 sentinel，不能只用 production-path
关闭。

其次，100k 的 `preserve_none` 契约虽已在 §3.4 用真实 noise 正文在 production-path
层重新验证，但真实 Qdrant 写入/检索（含 `time_stamp=None` payload 与本地
MiniLM embedding 的组合）仍只在通用（非 MemBench 专属）场景下验收过
（`lightmem-missing-time-online-soft-implementation.md` 用的是构造 message
而非真实 100k 数据流），MemBench 特有的 turn-granularity 双 call 节奏叠加
`preserve_none` 的真实 backend 组合尚未验证。

默认 `0_10k` 四源 smoke：**建议继续保留**，用于覆盖 §5"已覆盖"清单里的形状
（FirstAgent/ThirdAgent 基本 pair 结构、两种 time 格式），这些是最高频、最基础
的路径，production-path 层已确认但真实 backend 层（STM/extraction/Qdrant）从
未在 MemBench 上跑过。

### 6.1 公开候选（按 source path + 顺序选择，不按 gold/答案/命中率）

对每个 100k 源文件，按"文件内第一条 trajectory"（与既有 0_10k smoke
"每源第一条"的选择原则一致）定位其 message_list 中**首次出现**无 time marker
与首次出现 time marker 的公开位置（纯按顺序扫描得到，未读取/参考 answer 或
target_step_id）：

| 100k 源文件 | 候选 conversation（qtype/scenario/tid） | 公开 `n_steps` | 首个 no-time-marker 位置 | 首个 timed 位置 |
|---|---|---:|---:|---:|
| FirstAgentDataHighLevel | `highlevel/movie` tid=0 | 313 | step0 | step129 |
| FirstAgentDataLowLevel | `simple/roles` tid=0 | 464 | step0 | step21 |
| ThirdAgentDataHighLevel | `highlevel/movie` tid=0 | 311 | step0 | step150 |
| ThirdAgentDataLowLevel | `simple/roles` tid=0 | 320 | step0 | step3 |

四个候选恰好都在**同一条 trajectory 内**同时含 no-time noise 与真实 timed
step（因为 100k noise 是官方混布进原始 timed 序列的，见
`membench-100k-time-ruling.md` §3.1），意味着**每源只需 1 条 trajectory**、
配合一个覆盖到上表"首个 timed 位置"之后的 `history_limit`（或直接用完整
trajectory），即可让同一次 sentinel run 同时覆盖"纯 noise 段"与"noise→真实
时间过渡段"两种 STM 累积场景。是否采用完整 trajectory（如 FirstHigh
313 步）还是裁剪到刚过首个 timed step（如 130 步）、配几个 worker、批准多少
真实 API 预算与 run_id，由架构师按当前 v7 预算节奏另裁；本 note 不建议具体
规模、不生成 command pack、不创建 run 目录。

## 7. metric eligibility

- **answer 指标（`membench-choice-accuracy`）**：不受本轮任何异常影响——
  `parse_membench_choice()`/`normalize_membench_choice_prediction()`
  只消费 method 的自由文本回答，与 ingest 侧 turn-granularity 分叉、
  time marker 格式、no-time noise 均无耦合；`parse_failed` 分开统计的既有机制
  不变。
- **MemBench group Recall（`membench-recall`）valid/N/A 条件**：
  `_build_retrieval_evidence()` 对 `benchmark_name == "membench"` 的判词是
  `items is not None -> valid/turn`，`items is None -> n_a/none`
  （`retrieval_hit_lineage_incomplete`）。§3.7 已在真实 zero-hit/complete-hit/
  malformed 三态下确认该判词逻辑正确、无静默降级。**本轮新发现的
  turn-granularity 双 call 机制不改变这个 valid/N/A 边界**——它只影响
  "candidate id 集合的精度"（从"两个真实 id 的模糊候选"变成"单个真实 id 的
  精确候选"），不影响"是否声明 valid"。这意味着 `_build_retrieval_evidence()`
  现有 docstring 里"不声称能判断事实来自 user 还是 assistant child"的表述，对
  MemBench 而言实际比字面更保守——真实生产路径下每次 extraction 的
  candidate id 天然就是单值精确指向，而不是需要在两者间"猜"。这是一处
  **文档表述可以更精确、但不构成正确性缺陷**的观察，留给架构师决定是否更新
  `_build_retrieval_evidence()` 的 docstring/dossier 措辞。
- **stable ranking**：`_LIGHTMEM_UNAUDITED_STABLE_RANKING` 继续覆盖 MemBench
  （`pending/ranking_fidelity_not_audited`），本轮未审计排名保真度，维持
  pending，不受本次发现影响。
- **私有 gold 越界/空 target**：已在 §2/§4 确认只走 evaluator-private
  `mapping_status`/空 `groups` 分支，不影响 method-visible payload 或
  `parse_failed`/`membench-choice-accuracy` 计算。

## 8. 唯一总判词

```text
BLOCKED(需要 100k real sentinel 验证 STM 跨 add_memory 调用聚合是否让
FirstAgent 真实 user/assistant 内容进入同一次 extraction；MemBench 从未有真实
backend/API 跑过，preserve_none 在 MemBench turn-granularity 双 call 节奏下的
真实 Qdrant 写入路径也未验证)
```

**最小缺口清单**（均为需要真实 LightMem backend 才能关闭，不是代码/文档缺陷）：

1. 真实 vendored `ShortMemBufferManager`/`add_memory()` 在 MemBench
   `turn`-granularity 双 call 节奏下，STM 是否跨调用累积消息、extraction LLM
   实际收到的 prompt 是否同时含某 pair 两侧真实内容——production-path fake
   backend 无法证明（fake backend 整体替换了 `LightMemory` 实例）。
2. 100k `preserve_none` 契约叠加 MemBench 特有 turn-granularity 双 call 的真实
   Qdrant 写入/检索路径未验证（此前 Phase B 验收用的是通用构造消息，非真实
   100k 数据流）。
3. §6.1 已给出 4 个候选 conversation（按 source path + 顺序选择，未看
   gold/答案），供架构师裁定具体规模、worker 数、预算与 run_id；本 note 不
   生成 command pack、不建 run 目录、不估算 API 调用次数。

**非缺口（已用 census + production-path + evaluator-private 三层关闭，明确
不需要塞进付费 smoke）**：FirstAgent/ThirdAgent 基本拆分正确性、两种 time
marker 格式解析、FirstAgent 跨 step 不 union、conversation 隔离、检索
zero-hit/complete-hit/malformed lineage 判词、越界/空 target_step_id 私有
处置、"一侧有时一侧无时"（真实数据不存在，已用 synthetic 关闭）。这些异常类的
风险闭环证据均已在 §3/§4 逐条给出真实调用链 payload，理由是：它们只依赖真实
adapter/event stream/LightMem message-construction helper 的确定性行为，不
依赖真实 STM 累积或向量数据库这类只有真实 backend 才能观测的状态。

## 9. R1 实现订正（2026-07-19）

首轮审计 §3.0 已经发现 registered LightMem × MemBench 实际为 `turn`，这直接推翻了
原审计卡“FirstAgent 以真实 pair 投递”的承重前提；按原卡 §10 当时应停工回报。首轮 note
却继续写成“无偏差/无停工点”并把缺口推给付费 sentinel，属于漏报停工条件。本 R1 如实
订正：问题是 production registration/manifest 契约缺陷，不是必须先花 API 预算才能确认的
未知算法行为。

R1 将 LightMem resolver 改为 HaluMem=`session`、LongMemEval/MemBench=`pair`、其余=`turn`。
`build_turn_events → GranularityAggregator → LightMem.ingest` 强反例现证明：FirstAgent 一个
canonical dict step 只触发一次 `add_memory()`，同批含真实 user/assistant 与两条 child id，
零 placeholder；ThirdAgent 连续 user 不互配，每条独立触发真实 user + structural assistant，
source id 不串。vendored `SenMemBufferManager`/`ShortMemBufferManager` 的 buffer 均是实例字段，
源码已足以证明跨调用保持；更重要的是 R1 已消除 FirstAgent split-call 路径，因此首轮 §6/§8
“必须先做 100k real sentinel 才能确认 STM 跨 add 聚合”的 BLOCKED 判词被本节 supersede。
离线门全绿后，状态应回到 B11 smoke 待用户预算裁定，而不是 API sentinel blocker。

时间与内容边界也由 production-path fake backend 锁定：每条 canonical content 的
`place/time` 原文逐字保留；typed `time_stamp` 只取该 child 自身 `turn_time`。100k 风格双侧
或单侧无时均保持 `None`，不读取 QA/question time、兄弟 turn、相邻消息或 wall clock。
官方 `INSTRUCTION_FIRST` 的 `Question: (current time is {time}) {question}` 仍由 unified
builder 用 `Question.question_time` 填入 answer/query 侧，绝不反灌历史消息。

R1 独立读取 8 个正式文件并按 trajectory 内相邻可解析 source timestamp 统计时间倒序，按
`0-10k FirstHigh/FirstLow/ThirdHigh/ThirdLow → 100k 同序` 的分布为
`3, 7, 2, 21, 0, 3, 1, 2`，合计 `39`；同时复核 trajectory/source-step/canonical-turn
总数为 `4,260 / 452,245 / 767,075`。实现与测试保持输入顺序和各自 timestamp，不排序、
不修钟、不丢 turn。

运行身份不通过 bump `LIGHTMEM_ADAPTER_VERSION` 粗暴失效其他 benchmark。注册级纯 resolver
同时供 factory 与 manifest 使用；registered CLI 顶层 `method.consume_granularity` 写 concrete
值，并与真实 v3 provider 实例 fail-fast 交叉校验。该字段严格参与 resume：旧 manifest
缺字段、`turn→pair`、`pair→turn` 均 mismatch，相同 concrete 值才 match；isolated worker
不提前构造根实例，worker 内仍以同一 factory/resolver 产出的声明交叉校验真实实例。
