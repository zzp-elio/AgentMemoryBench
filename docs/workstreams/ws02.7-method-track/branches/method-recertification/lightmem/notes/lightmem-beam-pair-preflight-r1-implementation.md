# LightMem × BEAM pair 投递差量预检与 R1 实施 note

自包含实施记录（跨模型可读，不引用会话私有 scratchpad）。本卡只验并修
**BEAM → canonical event → LightMem** 的 method-specific 差量；BEAM benchmark 侧
frozen-v1 事实全部复用，不重跑全量 census、不改 public id、不重做异常大审计。

## 1. 架构裁决与本卡边界

current main 的确定性缺口：`_lightmem_consume_granularity()`（`methods/registry.py`）
只把 LongMemEval/MemBench 声明为 `pair`，BEAM 仍落到 `turn` 默认。于是严格交替的真实
user→assistant 会分别进入 `_native_turn_batch()`，变成 `[real user, placeholder
assistant]` 与 `[placeholder user, real assistant]` 两次人工 pair，而不是一次真实双边
pair，改变 LightMem 的 buffer/segment/extract 调用边界。

裁决：**LightMem × BEAM 声明 `pair`**。100k/500k/1m 的正常 user→assistant 进入一次真实
pair；10m 的两个同 role adjacency、assistant-first 或 dangling turn 由现有
`GranularityAggregator(pair)` 与 LightMem placeholder 规则诚实保留，不跨 session 配对。

## 2. 复用的 frozen benchmark 事实（source-lock 摘要，未漂移）

一手复核 `src/memory_benchmark/benchmark_adapters/beam.py` 与
`runners/event_stream.py`，确认卡 §2 的稳定事实在 current source 未漂移：

- 100k/10m 是两次独立 run；500k/1m 与 100k 同构。
- canonical public turn id 是 positional namespace（`s1:t1` / `p1:s1:t1`），非 raw
  `message.id`。`build_turn_events()` 经 `_stable_turn_id()` 用 benchmark 稳定 id。
- 100k/500k/1m 严格 user/assistant 交替；10m 基本交替、含 2 个同 role adjacency。
- 单 plan 每 session 仅首 user turn 带 `time_anchor`，adapter 保留 turn time 并把
  anchor 提升为 `session_time`，其余走 `turn_time → session_time → None`。
- 10m 有且仅一个全缺时 session；online-soft + `preserve_none` 诚实保留 None。
- BEAM gold `source_chat_ids` 是单 message unit 且 raw id 有重复/歧义 → BEAM
  Recall/NDCG 对 LightMem 仍应 `N/A`。

## 3. 生产链路一手核实（改一行为何充分）

事件流与 adapter 现成能力已足够表达 pair，改动只需 registration resolver：

- `runners/event_stream.py::GranularityAggregator._aggregate_pairs()` 先
  `_group_by_session()` 分组（pair **永不跨 session**，硬边界由框架保证），再以
  user 为锚：正常 user→assistant 产 `TurnPair(first=user, second=assistant)`；连续
  user 把前一个作 `dangling` singleton；assistant-first/连续 assistant 无锚点时产
  `orphan` singleton。这正是卡 §3.4/§3.5/§3.6 要求的形状。
- `methods/lightmem_adapter.py::_native_pair_batch()` → `_normalize_session_to_pairs()`
  （benchmark≠locomo 走 canonical role 分支）：正常 pair → `[real user, real
  assistant]` 两 slot 共享去重 candidate ids；dangling user → `[real user,
  placeholder assistant]`；orphan assistant → `[placeholder user, real assistant]`。
  placeholder 携带 `LIGHTMEM_PLACEHOLDER_MARKER`、content 空、镜像真实 child 的
  time/speaker/external_id。
- 时间：无自身时间的 assistant 经 `_turn_timestamp(turn, session, "preserve_none")`
  回落 `session.session_time`（= adapter 提升的 anchor）；全缺时双 None 原样保留。
- `_build_retrieval_evidence()` 完全按 `benchmark_name`/`lifecycle_profile` 分流，与
  granularity 无关：BEAM 恒 `n_a / beam_gold_is_single_message / none`，stable_ranking
  仍 pending。改 pair 不触碰该资格。

结论：唯一生产改动是 registration resolver 把 `beam` 归入 `pair` 集合；不 bump
`LIGHTMEM_ADAPTER_VERSION`（concrete `method.consume_granularity` 已严格参与
manifest/resume，只失效旧 BEAM `turn` 身份，不连坐另四格）。

## 4. 实际改动文件

- `src/memory_benchmark/methods/registry.py`：`_lightmem_consume_granularity()` 的
  `pair` 集合由 `{"longmemeval", "membench"}` 扩为
  `{"longmemeval", "membench", "beam"}`。这是唯一生产改动。
- `tests/test_method_registry.py`：resolver 参数表新增 `("lightmem", "beam", "pair")`。
- `tests/test_prediction_cli.py`：manifest 身份参数表新增 `("beam", "pair")`；新增
  `test_lightmem_beam_pair_manifest_breaks_resume_against_legacy_turn`（用真实
  `_build_method_manifest` + `_manifests_match_for_resume` 证明旧 `turn` 与新 `pair`
  双向 resume mismatch、同值才 match）。
- `tests/test_lightmem_adapter.py`：
  - `test_lightmem_registry_specializes_consume_granularity_by_benchmark` 增 beam 实例
    `consume_granularity == "pair"` 与 manifest `consume_granularity == "pair"`；
  - BEAM 逐 benchmark evidence 断言补 `provenance_granularity == "none"`；
  - 新增 5 条生产事件流强反例（均走真实
    `build_turn_events → GranularityAggregator(pair) → LightMem.ingest`，断言 backend
    实际 call 序列/payload，不只断言 helper 返回类型）：
    - `..._ingests_normal_pair_with_session_anchor`（§5.2：一次 call、两真实 slot、
      零 placeholder、content/role/public id 稳定、assistant 回落 session anchor、
      question time 不泄漏）；
    - `..._keeps_positional_ids_as_pair_candidates`（§5.3：`p1:s1:t1`/`p1:s1:t2` 原样
      进 candidate ids）；
    - `..._keeps_consecutive_users_as_singletons`（§5.4：两 call、各一真实 id + 各自
      placeholder，不互配）；
    - `..._orphan_assistant_never_pairs_across_session`（§5.5：orphan assistant 保真实
      role、下一 session 的 user 不跨 session 配对）；
    - `..._preserves_two_sided_none`（§5.6：双 None 原样进两 slot）。
- `docs/reference/integration/lightmem.md`：consume_granularity 稳定 roster 补 BEAM=pair
  裁决与 `N/A` 资格保持说明。
- 本 note。

## 5. 定向自检（一次，零真实 API）

```
uv run pytest -q \
  tests/test_lightmem_adapter.py tests/test_method_registry.py \
  tests/test_prediction_cli.py tests/test_beam_adapter.py \
  tests/test_beam_registered_prediction.py tests/test_event_stream.py \
  tests/test_artifact_evaluation_runner.py tests/test_documentation_standards.py
```

尾行：`330 passed, 1 warning in 82.38s`（唯一 warning 为 third_party LightMem 的
Pydantic V2 deprecation，非本卡引入）。`git diff --check` 无输出。

`test_beam_registered_prediction.py` 既有 100k/10m registered fake workflow 用 mem0
探针（mem0 beam 早已 `pair`），本卡未触及，契约不退化（§5.9）。

## 6. 隔离环境与偏差

- worktree `/Users/wz/Desktop/mb-actor-lightmem-beam-pair`，branch
  `actor/lightmem-beam-pair-preflight-r1`，基线 `4a598b5`。
- gitignored `data/`、`models/`、`third_party/benchmarks/` 用指向主工作区的只读软链补齐
  （未复制/修改/暂存）；零真实 API、零模型下载、零外网、零 outputs 写入、未读 `.env`。
- subagent：未使用。
- 无停工点：卡 §2 承重事实经 current source 复核全部成立，未被生产源码推翻。
