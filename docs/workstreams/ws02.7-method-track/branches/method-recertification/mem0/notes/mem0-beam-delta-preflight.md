# Mem0 × BEAM current-main 差量预检

> actor：Claude Sonnet 5（Claude Code，本会话系统提示自报模型；未跨模型接管）
> worktree：`/Users/wz/Desktop/mb-actor-mem0-beam`，branch
> `actor/mem0-beam-delta-preflight`，基线 `6643e56`（main）。
> 范围：只读审计，零真实 API，零生产代码改动。`data/BEAM` 与
> `third_party/benchmarks/BEAM` 在本 worktree 缺失（gitignored），已按卡 §1
> 说明建立只读软链指向 `/Users/wz/Desktop/memoryBenchmark` 对应目录，未联网下载、
> 未读 `.env`。

## 0. 唯一判词

**`READY_FOR_JOINT_RULING`**

理由：Mem0 × BEAM current-main 的全部承重锚（100K/500K/1M 标准 pair、10M 三类异常、
retrieve/evidence/judge）均在生产源码与本卡新增的 8 类探针中得到直接证据支持，无一处
被生产源码推翻卡内假设。唯一需要架构师联合裁决的是 §3 新发现的**官方 REST harness
positional chunking 与 framework 角色锚定 pair aggregator 在两处已知 10M 异常窗口
的分块方式实质不同**——这不是被推翻的假设（卡内本就未断言两者字节一致），而是一个
此前未落盘的新事实，按 §4 建议记为 `product-compatible extension/variant`。

## 1. current-main 承重锚版本

- `src/memory_benchmark/benchmark_adapters/beam.py`（801 行，含 100K/10M
  session/turn/public id/time/smoke crop）
- `src/memory_benchmark/runners/event_stream.py`（285 行，pair aggregator 与
  session 边界，`_aggregate_pairs()` L110-154）
- `src/memory_benchmark/methods/registry.py::_mem0_consume_granularity()`
  （L202-211）
- `src/memory_benchmark/methods/mem0_adapter.py`（2181 行，`_ingest_native_pair()`
  L541-570，`_turn_to_message()`/`_effective_time_prefix()` L1444-1501，
  `_build_retrieval_evidence()` L1078-1118）
- `configs/methods/mem0.toml`（34 行，smoke/official_full 双 section）
- `third_party/methods/mem0-main/memory-benchmarks/benchmarks/beam/run.py`
  （1244 行）+ `benchmarks/common/mem0_client.py`
- `src/memory_benchmark/evaluators/beam_rubric_judge.py` /
  `beam_recall.py`
- 定向测试锚（symlink 补齐 gitignored 资产后现场复跑）：

```text
$ uv run pytest -x -q tests/test_mem0_adapter.py tests/test_beam_adapter.py \
    tests/test_beam_rubric_judge.py tests/test_beam_recall.py \
    tests/test_event_stream.py tests/test_method_registry.py
........................................................................ [ 46%]
........................................................................ [ 92%]
...........                                                              [100%]
155 passed in 13.21s
```

（首次不带 symlink 时 `test_beam_rubric_judge.py::test_judge_prompt_matches_official_runtime_literal_exactly`
因缺 `third_party/benchmarks/BEAM/src/prompts.py` 报 `FileNotFoundError`，`1 failed, 82 passed
in 61.33s`——纯资产缺失，非代码回归，建软链后清零。）

## 2. benchmark 稳定层核对（只核漂移，未重算全量计数）

现场重读 `docs/survey/异常情况/beam.md` 与 `docs/survey/datasets/BEAM.md`，与
`benchmark_adapters/beam.py` 逐行对照，无漂移：

- `_sessions_from_standard_chat()` / `_sessions_from_10m_chat()` 严格按官方顺序展开，
  100K/500K/1M 每 session 一个 `s{n}` id，10M 按 `chat[i]['plan-{i+1}']` 展开为
  `p{n}:s{m}`，与稳定页一致；
- `_session_from_turns()` 的 `turn_id=f"{session_id}:t{turn_index}"` 是**纯位置命名**，
  与官方 raw `id`（含 1M 四个 conversation 的重复/重启）完全解耦，raw id 只落
  `turn.metadata["id"]`；
- `_beam_evidence_group_sets()` / `_map_evidence_turn_ids()` 把 `source_chat_ids` 三种形态
  打平为 raw id 原子，重复位置→multi-child any-of，非法原子（`'--'`）→unmatched，与
  survey 页 B-I1/B-G1 描述一致；
- `strip_tail_marker()` 只裁剪 `->-> a,b` 尾标记，不改写正文语义。

## 3. Production 映射探针（8 类，产品 adapter/event + FakeMemoryBackend）

统一方法：复用 `tests/test_mem0_adapter.py` 已有的 `FakeMemoryBackend` /
`FakeReaderClient`，串联真实 `memory_benchmark.core.{Conversation,Session,Turn}` →
真实 `runners.event_stream.build_turn_events()` → 真实
`GranularityAggregator("pair")` → 真实 `methods.mem0_adapter.Mem0(consume_granularity=
"pair", benchmark_name="beam")`。probe 脚本与完整 stdout 如下（探针 A/B/C/D/E/F 为本卡
新增；探针 G 复用已有生产测试；探针 H 为官方 harness 一次性只读 Arrow 探针，见 §4）。

```python
def run_pairs(conversation, isolation_key):
    events = tuple(build_turn_events(conversation, isolation_key))
    agg = GranularityAggregator("pair")
    backend = FakeMemoryBackend()
    provider = Mem0(config=Mem0Config.smoke(), memory_backend=backend,
                     reader_client=FakeReaderClient(), consume_granularity="pair",
                     benchmark_name="beam")
    for signal in agg.aggregate(events, isolation_key):
        if type(signal).__name__ == "TurnPair":
            provider.ingest(signal)
    return backend
```

### 探针 1：100K 标准 user→assistant pair — 已有生产测试覆盖

`tests/test_mem0_adapter.py::test_mem0_beam_pair_ingest_keeps_official_two_turn_chunk`
（L1268-1288）：`TurnPair(first=t1, second=t2)` → 一次 `add()`、
`roles=["user","assistant"]`、`metadata["turn_ids"]==["t1","t2"]`。现场复跑
包含在 §1 的 `155 passed`。

### 探针 2：同 session 两个连续正常 pair（本卡新增，探针 A）

```
=== A: two consecutive normal pairs same session === add_calls=2
  call[0] roles=['user', 'assistant']
      content='[Turn time: 2025-01-01] user: q1'
      content='[Turn time: 2025-01-01] assistant: a1'
      metadata.turn_ids=['s1:t1', 's1:t2'] first=s1:t1 last=s1:t2 speaker=user+assistant
  call[1] roles=['user', 'assistant']
      content='[Turn time: 2025-01-01] user: q2'
      content='[Turn time: 2025-01-01] assistant: a2'
      metadata.turn_ids=['s1:t3', 's1:t4'] first=s1:t3 last=s1:t4 speaker=user+assistant
```

两个 pair 各自独立 `add()`，无跨 pair 状态污染。

### 探针 3：10M `13674–13677` dangling→next-user 边界（本卡新增，探针 B）

用真实 role/content 序列复现 `docs/survey/异常情况/beam.md` §B-R1a（conversation
1/plan-7/batch 10/group 19→20）：

```
=== B: 10M dangling(13676) -> new pair(13677,13678) === add_calls=3
  call[0] roles=['user', 'assistant']
      metadata.turn_ids=['p7:s10:t72', 'p7:s10:t73'] first=...t72 last=...t73 speaker=user+assistant
  call[1] roles=['user']
      content='[Turn time: 2025-02-20] user: set up dynamic weights for loa'
      metadata.turn_ids=['p7:s10:t74'] first=...t74 last=...t74 speaker=user
  call[2] roles=['user', 'assistant']
      metadata.turn_ids=['p7:s10:t75', 'p7:s10:t76'] first=...t75 last=...t76 speaker=user+assistant
```

**结论确证**：dangling user（原 raw id 13676）是**单元素 messages 列表**（`roles=['user']`），
`_ingest_native_pair()` 未添加任何空 assistant 占位；`metadata["turn_ids"]` 长度为 1、
`first_turn_id==last_turn_id`，不与前后 pair 共享 turn id。下一 user（13677）正常开新
pair 并与 13678 闭合，两个 user 之间没有被互配或吞并。

### 探针 4：10M `12988–12992` content 错位边界（本卡新增，探针 C）

```
=== C: 10M content-mismatch raw passthrough === add_calls=3
  call[0] roles=['user', 'assistant']   # 12988,12989 正常闭合
  call[1] roles=['user']                # 12990 dangling singleton
      content='[Turn time: 2025-02-10] user: implement batch updates in my '
  call[2] roles=['user', 'assistant']   # 12991(新话题),12992(语义错位答案) 原样闭合
      content='[Turn time: 2025-02-10] assistant: To enhance your test dash...'
```

12992 的错位内容（语义上回答的是 12990 而不是 12991）被**原样**发送给 Mem0，
adapter 未做任何内容级修补或角色重排，`_turn_from_event`/`_original_content_from_event`
只读 `event.metadata["original_content"]`（即 BeamAdapter 的 `strip_tail_marker()` 输出），
不参与语义纠错。

### 探针 5：10M 缺 `time_anchor` batch（本卡新增，探针 D）

```
=== D: full missing time_anchor session -> no time prefix === add_calls=1
  call[0] roles=['user', 'assistant']
      content='user: no-time q'
      content='assistant: no-time a'
      metadata.turn_ids=[...] session_time=None first_turn_time=None
```

`turn_time`/`session_time` 均 `None` 时，`_effective_time_prefix()` 返回空串，
两条消息都没有 `[Turn time]`/`[Session time]` 前缀，符合 B-T1 `preserve_none` 契约；
`metadata` 中也不写 `session_time`/`first_turn_time` 键（`_turn_batch_metadata()` 用
`if session.session_time:` / `if first_turn_time:` 守卫，None 值不落 key）。

### 探针 6：相邻 session anchor 回退（本卡新增，探针 E）

复现 B-T2 表中 `conversation=1` 一行（`p7:s10`/2025-02-28 → `p8:s1`/2025-02-15）：

```
=== E: adjacent session anchor rollback (no cross-session reorder) === add_calls=2
  call[0] ... content='[Turn time: 2025-02-28] user: late-anchor q' ...
  call[1] ... content='[Turn time: 2025-02-15] user: earlier-anchor q' ...
```

两次 `add()` 各自使用本 session 的 source anchor，晚 session 的时间字面量确实比前一
session 更早，adapter 未做任何跨 session 排序、去重或"取较晚值"处理——`_session_time_from_event()`
只读当前事件自身的 `original_session_time`/`timestamp`，无历史状态。

### 探针 7：1M raw id 重启但 public positional id 不冲突（代码级核证，非独立 probe）

`_session_from_turns()`（`beam.py:685-698`）的 `turn_id=f"{session_id}:t{turn_index}"`
只依赖 session 内位置，从不读 `turn_raw.get("id")` 参与 identity；`_conversation_from_row()`
的 `raw_id_to_public_turn_ids` 映射也是按 `conversation` 局部累积（`setdefault(raw_id,
[]).append(turn.turn_id)`），1M 四个 conversation 的 raw id 重启只会让同一 raw id 在
`raw_id_to_public_turn_ids` 下累积多个 public turn id（进而在 gold group 侧变成
multi-child any-of），不会导致两个不同 turn 共享同一 public `turn_id`——探针 1/2 已经
验证 `turn_id` 在 `TurnEvent`/`TurnPair`/`Mem0` 全链路原样透传，故本条无需再造 fixture。

### 探针 8：奇数 tail 位于 session 末尾，不能跨下一 session 配对（本卡新增，探针 F）

```
=== F: odd tail at session end cannot cross into next session === add_calls=3
  call[0] roles=['user', 'assistant']   # s1: q1/a1 正常闭合
  call[1] roles=['user']                # s1 末尾奇数 tail，dangling singleton
      content='[Turn time: 2025-01-01] user: odd tail q (unanswered at sess'
  call[2] roles=['user', 'assistant']   # s2 从自己的第一个 user 重新开始，独立 pair
      content='[Turn time: 2025-01-02] user: s2 first user turn (must NOT p'
```

`event_stream._aggregate_pairs()` 按 `_group_by_session()` 先分组再逐 session 跑
pending-user 状态机，session 末尾未闭合的 user 在该 session 循环结束前就地 flush 为
dangling（`event_stream.py:148-153`），下一 session 的第一个 event 永远从空
`pending_user=None` 开始，结构上不可能把前一 session 的奇数尾配对进下一 session。
（此为 `GranularityAggregator` 的 method-neutral 通用行为，`tests/test_event_stream.py`
已有等价通用覆盖——`test_pair_granularity_marks_unanswered_user_turns_dangling` 与
`test_session_granularity_emits_one_batch_per_session`——本探针只额外确认 Mem0 侧
接收到该边界后确实各自触发独立 `add()`，不做二次消费级 fixup。）

## 4. official REST harness vs framework product core：接口层对照表（新证据）

一手源：`third_party/methods/mem0-main/memory-benchmarks/benchmarks/beam/run.py`
的 `parse_beam_chat()`（L192-252）、`batch_to_chunks()`（L255-272）、
`get_time_anchor_epoch()`（L275-287）、`ingest_conversation()`（L343-538）；
`benchmarks/common/mem0_client.py` 的 `Mem0Client.add()`/`_add_oss()`（L117-172）；
vendored `mem0/memory/main.py::Memory.add()` 签名（L573-584）。

| 维度 | 官方 `memory-benchmarks/benchmarks/beam` harness | framework product core（`mem0_adapter.py`） |
| --- | --- | --- |
| 调用方式 | `Mem0Client._add_oss()` 对本地 Mem0 **OSS HTTP server** 发 `POST {host}/memories`（`aiohttp`），JSON payload；是 wire-protocol 层 | `_create_memory_backend()` 直接 `importlib.import_module("mem0")` 拿到 vendored `mem0/memory/main.py::Memory` 类，`Memory.from_config(...).add(...)` 进程内直接调用；是 Python library 层 |
| 时间参数 | `mem0.add(messages, user_id, timestamp=time_epoch)`；`time_epoch=get_time_anchor_epoch(batch_turns)` 取**整个 batch 内第一个非空 `time_anchor`** 转 unix epoch，同一 batch 全部 chunk 共用一个 epoch 值，随 HTTP payload 的 `timestamp` 字段传给 OSS server | vendored 本地 `Memory.add()` **签名中没有 `timestamp` 形参**（仅
  `user_id/agent_id/run_id/metadata/infer/memory_type/prompt`）；adapter 改用公开
  `prompt` 扩展点注入 observation date 文案（`_observation_time_prompt()`），并在渲染的
  message 正文里按 **turn 粒度**前置 `[Turn time: …]`/`[Session time: …]`（`_effective_time_prefix()`，turn 优先、session fallback、`preserve_none`） |
| 分块/分组算法 | `batch_to_chunks(turns, chunk_size=2)`：**过滤空 content 后按位置每 2 条切一个 chunk，每个 batch（session）独立从位置 0 重新计数**，不检查 role，不管两条消息是否同为 user/assistant | `event_stream._aggregate_pairs()`：**以 `role=="user"` 为锚**逐 session 状态机配对；未闭合 user → dangling singleton；无锚的非 user turn → orphan singleton；正常 user→assistant → 一次两条 |
| namespace | `user_id = f"beam_{chat_size}_{conv_idx}_{run_id}"`，search 用同一 `user_id` 过滤 | `run_id=isolation_key`（`{run_id}_{conversation_id}`），search 用
  `filters={"run_id": isolation_key}`；均为 `Memory.add()` 支持的合法命名空间维度，只是
  选用了不同字段（B3 已有既定裁决，本表仅并列陈述） |

**新发现（正文分块算法实质不同，非仅时间通道不同）**：用只读探针加载真实 10M row 0/1，
对已知的两处异常窗口分别现场运行官方 `parse_beam_chat()` + `batch_to_chunks(chunk_size=2)`，
得到与 framework 完全不同的分组：

```
conv_id=1 row_idx=0 batch_idx=69 batch_len=173
  chunk[36] ids=[13674, 13675] roles=['user', 'assistant']      # 正常
  chunk[37] ids=[13676, 13677] roles=['user', 'user']           # 两个 user 同批
  chunk[38] ids=[13678, 13679] roles=['assistant', 'user']      # assistant 配到不相关的下一 user

conv_id=2 row_idx=1 batch_idx=67 batch_len=161
  chunk[69] ids=[12988, 12989] roles=['user', 'assistant']      # 正常
  chunk[70] ids=[12990, 12991] roles=['user', 'user']           # 两个 user 同批
  chunk[71] ids=[12992, 12993] roles=['assistant', 'user']      # assistant 配到不相关的下一 user
```

即官方**纯位置**分块在两处已知异常窗口都产生"级联错位"：dangling user 与下一个新话题
user 被塞进同一次 `add()`，随后原本应配对的 assistant 又被迫和更后面一个不相关的 user
凑成一条。而 framework 的角色锚定 pair aggregator（探针 3/4）在同样的窗口分别产出
dangling singleton + 干净新 pair，从不把两个同角色 turn 塞进一次 `add()`。这一差异
**只影响 10M**（100K/500K/1M 全量 0 处相邻同 role，见 `beam.md` B-S1，故两种算法在
三个标准 split 上结果等价，只是消息正文/metadata 渲染不同），且**只波及 10M 已知的
两处异常窗口**（`beam.md` B-R1a/B-R1b，全库仅 2/77,569 groups）；未在其余 10M 数据中
另行扫描是否存在其他非文档化的连续同 role 序列（若存在会命中同一种官方级联错位，
但不改变 framework 侧行为，因为 framework 的判定只依赖本地 role 状态机，与官方分块
无关）。

**建议裁决方向**：与 B4（时间双通道）同构——不要求官方 positional chunking 与
framework 角色锚定 pair aggregator 字节对齐，记为 `product-compatible extension/
variant`：framework 的算法更严格（保证同一次 `add()` 内不出现两个同角色 turn），
理由是 v3 协议要求 `TurnPair` 语义上表达"一次真实交换"，而官方脚本的定长滑窗
分块本身就是已知会在非标准角色序列上产生错位配对的简化实现（这也是为什么它需要
一个独立的、只信任 `time_anchor` 而不信任 role 顺序的时间戳注入路径）。此判断留给
架构师在联合裁决中确认或推翻。

## 5. readout / metric / judge / identity 核对

- **search 只用 run_id**：`_retrieve_native()`（L979-1076）唯一过滤条件是
  `filters={"run_id": query.isolation_key}`，`formatted_memory` 来自
  `_memory_context_text(memories)`，`prompt_messages` 走 `_reader_messages()` →
  `benchmark_name=="beam"` 时调用 `_build_mem0_beam_prompt()` 直接复用官方
  `get_beam_answer_generation_prompt`；但 unified 主口径由
  `beam.py::build_beam_unified_answer_prompt()` 只读 `retrieval_result.formatted_memory`
  重新套用框架统一 `BEAM_ANSWER_PROMPT_TEMPLATE`，两者互不干扰
  （`test_mem0_beam_unified_prompt_ignores_native_provider_messages` 现场通过）。
- **RetrievalEvidence**：`_build_retrieval_evidence()`（L1093-1103）对 `benchmark_name=="beam"`
  返回 `status="n_a"`、`reason_code="ingest_batch_coarser_than_gold"`、
  `provenance_granularity="none"`。卡内提议的 reason_code 是
  `beam_gold_is_single_message`（LightMem 侧使用的措辞），Mem0 现场用的是
  `ingest_batch_coarser_than_gold`；两者语义等价（pair 批 sidecar 无法把抽取事实精确
  归因到 pair 内单条 turn），但**字面不同**。`evaluators/beam_recall.py::
  decide_retrieval_eligibility()` 只消费 `semantic.status`（非 `valid` 即整题 N/A，
  reason_code 仅落盘披露，不参与判定逻辑），故不影响 Recall=N/A 的最终行为，
  `test_mem0_retrieval_evidence_matrix_across_benchmarks`（L1303-1325）现场锁死这个
  具体字符串。是否统一两个 method 的 reason_code 措辞留给联合裁决，非本卡阻塞项。
- **judge float**：`beam_rubric_judge.py` L250 `item_score = float(result["score"])`，
  L259 `official_int_total += int(item_score)` 双轨并存，method-neutral（不区分
  Mem0/LightMem），`test_score_0_5_is_preserved_not_truncated_to_0` 等三个测试现场通过
  （见 §1 的 `155 passed`，这批含 `test_beam_rubric_judge.py` 全量）。
- **judge/model/token/scope efficiency**：`evaluate_run_artifacts()` 用
  `self._new_efficiency_observation_sink()` + `sink.unit_scope(conversation_id,
  question_id)` 包裹逐题 rubric+equivalence 调用，离线路径（fake client 分支）不生成
  observation；`_finalize_artifact_payload()` 统一落盘。这是 README 记录的
  `174bd46` 共享修复覆盖范围，现场 `test_beam_rubric_judge.py` 的
  T3.8（`paths.evaluator_efficiency_observations_path("beam_rubric_judge")`）测试组
  在 §1 全部通过，未发现新回归。
- **adapter/source/contract/granularity/track identity**：
  `tests/test_method_registry.py` 现场断言 `("mem0", "beam", "pair")`；
  `tests/test_mem0_adapter.py::test_mem0_v3_provider_declares_consume_granularity_per_benchmark`
  （对应 L1255-1257 `beam.consume_granularity == "pair"`）与
  `_build_mem0_system()`（registry.py L234-254）现场核对一致，`consume_granularity`
  经 `context.benchmark_name` 单一注入点决定，无第二条暗路径可绕过。
- **TOML current 参数**：`configs/methods/mem0.toml` 的 `smoke`/`official_full` 两个
  section 都不含 benchmark 专用字段，`max_workers` 是唯一差异（1 vs 10），与
  AGENTS.md「method 配置不再按 native/unified 双轨」现行政策一致；BEAM 无
  `author_beam` section（尚未有作者复现证据），符合当前政策"只有确有作者证据才增补"。

## 6. 测试盲点（现有测试未覆盖、本卡探针已补但未落成正式 pytest）

1. **Mem0 对 dangling `TurnPair`（second=None）的 singleton-not-placeholder 行为**——
   现有 `tests/test_mem0_adapter.py` 只测了正常两 turn pair（L1268-1288），没有专门
   针对 BEAM dangling/orphan 场景的断言；本卡探针 B/C/F 已经用真实生产链路证明该行为，
   但尚未沉淀为仓库内可回归的 pytest（若架构师认为有必要，值得在共享实现卡里补一条
   `test_mem0_beam_pair_ingest_singleton_dangling_has_no_placeholder`）。
2. **官方 positional chunking vs framework 角色锚定 pair aggregator 的等价性**——
   全仓没有任何测试比较两者在 10M 已知异常窗口的分组差异；§4 的发现完全靠本卡新增的
   一次性只读 Arrow 探针得出，不是被动态测试保护的不变量，未来官方 harness 或
   `_aggregate_pairs()` 任一方变化都不会有测试报警。
3. **BEAM `beam_recall` reason_code 字面值**未与 LightMem 侧统一，两个 method 各自的
   测试各自断言自己的字符串（Mem0 侧断言 `ingest_batch_coarser_than_gold`），没有一个
   跨 method 一致性测试。

以上三项均不构成 `BLOCKED`：现有生产行为都是良定义且被至少一层证据覆盖
（现场探针或既有测试），只是回归保护粒度不同，留给联合裁决决定是否需要新增测试
而非本卡自行改代码。

## 7. 100K/10M 最小 runtime 覆盖建议（不可调用 API，仅供后续命令包参考）

- **100K W1**：1 conversation × 1 round（2 turns）× 1 question × 1 worker，复用
  `BEAM_SMOKE_POLICY` 默认值；只验证 pair 正常两 turn 链路 + unified answer builder +
  rubric judge float + Recall=N/A 四点，不需要刻意命中任何异常窗口（100K 全量 0 处
  role 异常）。
- **100K W2**：显式 `2 conversations × 2 workers`，只加验证 worker 物理隔离（B3），
  round/question 继续用默认，避免重复验证 W1 已覆盖的内容。
- **10M W1**：`--variant 10m smoke` 默认 1 conversation × 1 round，不強制选中
  conversation 1/2（异常窗口不在数据集开头，命中与否不影响契约验证——本卡探针已经
  在离线层面覆盖异常窗口，真实 smoke 的职责只是验证 runtime/backend/API 链，不是
  重新抽样异常）。
- **10M W2**：如需再补一次 worker 隔离验证可选做，但鉴于 100K W2 已验证同一套
  `Mem0` 双 worker 隔离机制（B3 是 method-level 而非 benchmark-level 能力），10M W2
  可视为**冗余轴**，建议省略以节省预算——两个 variant 的差异只在数据/结构，不在
  worker 隔离算法本身。

## 8. 结论

`READY_FOR_JOINT_RULING`。无需真实 API 即可确认：Mem0 pair ingest 对 100K/500K/1M
标准 pair 与 10M 全部四类已知异常（dangling、content 错位、缺时、anchor 回退）保持
source order/role/content/isolation，且不添加结构占位符；raw id 重启不影响 public
positional id 唯一性；RetrievalEvidence 正确标 N/A（reason_code 字面值与 LightMem
不同但语义等价、不影响判定）；rubric judge 全链路保留 float 主分；judge efficiency
共享修复仍生效。唯一需要架构师确认的新事实是 §4 的官方 positional chunking 与
framework 角色锚定 pair aggregator 的分块算法级差异——建议记为
`product-compatible extension/variant` 但需联合裁决拍板措辞与是否需要补充测试。
