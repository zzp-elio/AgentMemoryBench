# Mem0 source-time 单次渲染实现 note（Phase C）

> 日期：2026-07-16。actor 自报；架构师强验收。
> 性质：Phase C 强验收材料；只动允许清单内 4 文件 + 1 note。
> 范围：Mem0×MemBench 去重 + `turn → session → None` 唯一 effective timestamp
> fallback；不修改 Mem0 extraction/update/retrieve 算法。
> 上游裁决：`docs/workstreams/ws02.7-method-track/branches/membench-time-semantics/notes/membench-100k-time-ruling.md` §5 §7。

## 1. 两类根因

1. **MemBench 原文已嵌 source time 时被双前置**：`src/memory_benchmark/benchmark_adapters/membench.py::_turn_from_step` 已无损保留 `(place: …; time: '2024-10-01 08:00' …)` 子串并把 `turn_time` 抽到 `Turn.turn_time`，但 `src/memory_benchmark/methods/mem0_adapter.py::_turn_to_message` 又把同一 `turn_time` 前置为 `[Turn time: …]`，与原文里的 `time: '…'` 重复。
2. **turn/session 同时存在时双前缀**：旧 renderer 总是先写 `[Session time: …]` 再写 `[Turn time: …]`，与项目已裁的 `turn_time → session_time → None` 唯一 fallback 契约不一致；BEAM（turn 自带时间、session 也有时间）和 HaluMem（整 session batch）两条路径都受影响。

## 2. 公开 marker 契约

MemBench adapter 在 `_turn_from_step()` 形成的 `Turn.metadata` 写 JSON-safe boolean `source_timestamp_embedded_in_content`：

- `turn_time` 真的由 content 内完整 time marker 解析得到 → `True`；
- 无 time marker → `False`。

不写 `if benchmark == "membench"` 特判。规则由 marker 表达，method renderer 读通用标记。

事件流往返安全：`_turn_from_event()` 通过 `metadata=dict(event.metadata.get("turn_metadata") or {})` 保留 `turn_metadata`，marker 不会在 v3 provider 路径丢失。`build_turn_events()` 把 `turn_metadata` 写进 event.metadata，`build_turn_events -> GranularityAggregator -> ingest` 路径下 marker 仍然有效。

## 3. 唯一 effective timestamp fallback

`Mem0._effective_time_prefix(turn_time, session_time, marker)` 静态 helper 把策略集中成一条：

| turn_time | session_time | marker | prefix |
|---|---|---|---|
| 非空 | 任意 | `True` | （空，原文里的 place/time 已是唯一正文表示） |
| 非空 | 任意 | False / 缺键 | `[Turn time: …] ` |
| `None` | 非空 | 任意 | `[Session time: …] ` |
| `None` | `None` / 空串 | 任意 | （空） |

marker 严格 `True` 才跳过：`"true"` / `1` / `None` / 缺键全部回退到 `[Turn time:]`。该判断已由 `test_mem0_renderer_session_only_and_no_time_byte_stable` 强反例锁住。

`_turn_to_message()` 把 `turn.metadata.get("source_timestamp_embedded_in_content")` 透传给 helper，speaker name 与 image caption 既有行为不变；本卡没有动过它们。

## 4. legacy / v3 两条路径

- **legacy**：`add_from_turn()` / `_add_longmemeval_conversation()` → `_turn_to_message(turn, speaker_roles, session_time=session.session_time)`。
- **v3 turn**：`ingest(TurnEvent)` → `_ingest_native_turn()` → `_turn_to_message(turn, speaker_roles, session_time=event.session_time)`。
- **v3 pair**：`ingest(TurnPair)` → `_ingest_native_pair()` 循环 `_turn_to_message`。
- **v3 session**：`ingest(SessionBatch)` → `_ingest_native_session()` 循环 `_turn_to_message`。

四条路径都走同一个 helper，行为字节一致；`test_mem0_v3_ingest_dedups_marker_after_event_stream` 与 `test_mem0_renderer_falls_back_to_turn_when_both_turn_and_session_set` 用 v3 session 路径与 legacy add 路径做一致性断言。

`_observation_time_prompt()` 是 batch 相对时间锚点，不是逐 turn 时间通道；本卡不修改其 prompt 文本与 batch/session 选取策略。`test_mem0_observation_time_prompt_text_unchanged` 强锁字节稳定。

## 5. 受影响面

- **MemBench first-person dict step**（`{user, agent}` → 拼接 content）：marker=True；原文 `place` + `time: '…'` 一字不动，renderer 不再前置 `[Turn time]`。
- **MemBench third-person string step**（含 `time'…'` 无冒号格式，0-10k 100% 形态）：marker=True；同上。
- **BEAM**：每 turn 自带时间，session 也带时间，事件流下 session_time 会回退到 event.timestamp（= turn_time），renderer 只输出 `[Turn time: …]`，旧双前缀收敛。
- **HaluMem**：session 级 batch，session_time 与 turn_time 关系同上，v3 session 路径同样只输出 `[Turn time: …]`。
- **LoCoMo / LongMemEval**：turn 不带 typed turn_time，只 session_time，行为与原版完全一致（`[Session time: …]`）。`test_add_batches_longmemeval_turns_as_user_assistant_pairs` 验证 LME pair 字节不变。
- **噪声 message**（无 time marker）：turn_time=None，session_time=None，prefix 为空；`test_mem0_renderer_session_only_and_no_time_byte_stable` 锁住全空 turn。
- **QA.time**：仍只进入 `Question.question_time`，不串到 turn metadata / content / event。`test_membench_marker_states_cover_first_third_and_noise` 用 `'2099-12-31 23:59' Sunday` 未来日期 + `_MSG_EMBEDDED_TIME` 过去日期做对照。

## 6. 版本 bump

`MEM0_ADAPTER_VERSION` 从 `conversation-qa-v1` 升到 `conversation-qa-v2`。原因：v1 renderer 把同一 source time 在 `Turn.turn_time` + content + `[Turn time]` 三个位置同时存在；v2 renderer 删去第三条重复。manifest 严格比较会自然拒绝旧 v1 run resume，不新增兼容删除键。

`RetrievalEvidence` / sidecar 协议版本不动；本次修复不涉及 retrieval 事实。

## 7. 测试尾行

```
uv run pytest -q \
  tests/test_membench_conversation_adapter.py \
  tests/test_mem0_adapter.py
```

尾行 `61 passed in 2.34s`。

新增 / 改动测试：

- `tests/test_membench_conversation_adapter.py`：
  - `test_membench_parses_both_embedded_time_formats_and_keeps_content`：加 marker=True 断言（覆盖 first/third、有冒号/无冒号）。
  - `test_membench_marker_states_cover_first_third_and_noise`（新）：三种态全锁 + JSON 严格 boolean 断言。
  - `test_membench_marker_survives_event_stream_roundtrip`（新）：v3 事件层往返不丢 marker。
- `tests/test_mem0_adapter.py`：
  - `test_add_writes_each_turn_separately_with_conversation_namespace`：t1 由 `[Session time] [Turn time]` 收敛为 `[Turn time]`。
  - `test_mem0_legacy_add_skips_duplicate_turn_time_when_content_has_marker`（新）。
  - `test_mem0_v3_ingest_dedups_marker_after_event_stream`（新）。
  - `test_mem0_renderer_falls_back_to_turn_when_both_turn_and_session_set`（新，覆盖 BEAM/HaluMem 形态）。
  - `test_mem0_renderer_session_only_and_no_time_byte_stable`（新）：session-only 与全空 turn 字节稳定 + marker 严格 True 强反例。
  - `test_mem0_observation_time_prompt_text_unchanged`（新）。
  - `test_mem0_adapter_version_bumped_to_v2_with_v1_legacy_mention`（新）。

## 8. 未改算法声明

- 不修改 Mem0 extraction/update/retrieve 算法。
- 不修改 MemBench time parser。
- 不删除 place。
- 不为无时 noise 造时间。
- 不修改 Mem0 manifest 中非 `adapter_version` 字段；现有 run 因 manifest 严格比较被拒后需新建 run_id。
- 不引入 benchmark 名特判（`if benchmark == "membench"` 等）——所有判断由公开 `turn.metadata["source_timestamp_embedded_in_content"]` 驱动。
