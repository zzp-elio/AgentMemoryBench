# Actor 卡：LightMem × BEAM pair 投递差量预检与 R1

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**你负责在隔离 worktree 中核清并修复 LightMem × BEAM 的消费粒度接线，
补齐直接强反例与一份自包含实施 note。actor 可自行组织 subagent，但不得扩大允许范围；若
实质使用，最终报告披露分工，主 actor 仍对全部结论负责。

## 0. 这张卡解决什么

LightMem 已完成 LoCoMo、LongMemEval、MemBench 三格 current-v7 真实 B11；下一格是 BEAM。
BEAM benchmark 侧已经 frozen-v1，稳定事实、全量异常账、gold group 与官方 prompt/metric
不从头重做。本卡只验 **BEAM → canonical event → LightMem** 的 method-specific 差量。

current main 有一个确定性嫌疑：`_lightmem_consume_granularity()` 只把 LongMemEval/MemBench
声明为 `pair`，BEAM 仍落到 `turn`。于是严格交替的真实 user→assistant 会分别进入
`_native_turn_batch()`，变成 `[real user, placeholder assistant]` 与
`[placeholder user, real assistant]` 两次人工 pair，而不是一次真实双边 pair。这会改变
LightMem 的 buffer/segment/extract 调用边界，不能用“内容最终都出现过”代替语义等价。

本卡的架构裁决是：**若 current source/data 复核无反证，LightMem × BEAM 应声明 `pair`。**
100k/500k/1m 的正常 user→assistant 进入一次真实 pair；10m 的两个同 role adjacency、
assistant-first 或 dangling turn 由现有 `GranularityAggregator(pair)` 与 LightMem placeholder
规则诚实保留，不跨 session 配对。若一手证据推翻此前提，按 §7 停工，不为完成卡而硬改。

完成后唯一总判词只能是：

```text
READY_FOR_BEAM_B11_COMMAND
```

或：

```text
BLOCKED(<最小缺口列表>)
```

## 1. 隔离环境与最小读序

- 建议 worktree：`/Users/wz/Desktop/mb-actor-lightmem-beam-pair`
- 建议 branch：`actor/lightmem-beam-pair-preflight-r1`
- 基线：包含本卡的 latest `main`；开工先记录 `git rev-parse --short HEAD` 与
  `git status --short`

严格按顺序读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与最新断点
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/README.md`
4. `docs/reference/actor-handbook.md`
5. BEAM 已验收稳定事实，只读任务相关段落：
   - `docs/survey/datasets/BEAM.md`
   - `docs/survey/workflows/BEAM.md`
   - `docs/reference/integration/beam.md`
   - `docs/workstreams/ws02.6-first-smoke-hardening/notes/beam-frozen-v1.md`
6. 既有 LightMem 差量证据，只读承重段落：
   - `docs/workstreams/ws02.7-method-track/branches/input-role-semantics/notes/
     lightmem-messages-membench-beam-role-audit.md` 的 §3、§5、§9、§10
   - `docs/workstreams/ws02.7-method-track/notes/m0-6-beam-time-adapter.md`
   - `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/
     lightmem-five-benchmark-safety-dossier.md` 的共同前提与后续格规则
7. §4 点名的 current-main 代码与测试

新 worktree 缺 gitignored `data/`、`models/`、`third_party/benchmarks/` 时，可建立指向主
工作区的只读软链；不得复制、修改、暂存这些资产。不得读取或打印 `.env`。全程零真实 API、
零模型下载、零外网请求、零输出目录写入。

## 2. 已冻结 benchmark 事实：复用，不重造

以下不是本卡待重新发明的结论；只需用 source lock/current source 定点确认未漂移：

1. `100k` 与 `10m` 是 BEAM B11 的两次独立 run；500k/1m 与 100k 同构，不另烧 smoke。
2. canonical public turn id 是 positional namespace（如 `s1:t1`、`p1:s1:t1`），不使用会
   重复/跳跃的 raw `message.id` 作为全局 id。
3. 100k/500k/1m 严格 user/assistant 交替；10m 基本交替，但存在 2 个同 role adjacency。
4. 单 plan 每个 session 只有首个 user turn 带 `time_anchor`；adapter 保留该 turn time 并把
   anchor 提升为本 session 的 `session_time`，其余 turn 走 `turn_time → session_time → None`。
5. 10m 有且仅有一个全缺时 session；online-soft + `preserve_none` 应诚实保留 None，不能从
   邻 session、question、wall clock 或人工 offset 造 source time。
6. 月名 anchor 经通用 `_turn_timestamp()` 转为 LightMem 可接受的 ISO；canonical raw anchor
   仍可审计。
7. BEAM gold `source_chat_ids` 是单 message unit，且 raw id 有重复/歧义。LightMem extraction
   只证明 pair candidate ids，因此 BEAM Recall/NDCG 对 LightMem 仍应是 `N/A`；改成 pair 不得
   顺手把资格写成 valid。
8. 官方 BEAM rubric judge、event-ordering 特殊评分、Gold Evidence Group 与私有字段隔离均已
   frozen；本卡不修改 benchmark adapter、prompt、evaluator 或 gold。

若这些稳定事实未漂移，就禁止重跑全量 2,000 题统计、重新设计 public id 或复制一份新的
benchmark anomaly 大审计。只把 current source-lock 摘要写入实施 note 的“复用证据”小节。

## 3. 已裁实现边界

1. `_lightmem_consume_granularity("beam")` 改为 `pair`；resolver 仍是 factory 与 manifest 的
   单一事实源。
2. 不 bump `LIGHTMEM_ADAPTER_VERSION`：本批不改 extraction/embedding/readout/third_party
   算法；concrete `method.consume_granularity` 已严格参与 manifest/resume，足以只失效 BEAM
   的旧 `turn` 身份，不连坐另四格。
3. 正常 user→assistant：一次 `TurnPair`、一次真实双边 `add_memory()`，两条 content/role/
   timestamp/source id 原样进入；不得出现 placeholder。
4. 连续 user：前一个 dangling 与后一个 user 分别成为 singleton pair，各补自己的 assistant
   placeholder；不得把两条 user 互配或 union lineage。
5. assistant-first/连续 assistant：每条 orphan assistant 用 placeholder user 保留；不得丢弃、
   改成 user 或跨 session 寻找配偶。
6. session 边界是硬边界；pair 不得跨 `session_id`。
7. 真实 pair 的两个 slot 使用同一稳定 candidate child-id 集；singleton 的 placeholder 镜像唯一
   real child id。placeholder 仍不进入 extraction prompt/token count。
8. time 继续只走 current source contract。100k 默认 smoke 的第二条 assistant 从本 session
   anchor fallback；10m 全缺时 synthetic/真实定点路径保持 None。不得改 BEAM adapter 数据。
9. RetrievalEvidence 对 BEAM 保持 `n_a/none + beam_gold_is_single_message`，stable ranking
   保持 pending。
10. 真实 smoke、LLM/Qdrant 产物与双 worker 验货不在本卡执行；本卡只把 current main 推到
    `READY_FOR_BEAM_B11_COMMAND`。

## 4. 必须亲读的 current-main 链路

- `src/memory_benchmark/benchmark_adapters/beam.py`
  - 100k/10m 展开、public id、role、session_time、smoke round 裁剪
- `src/memory_benchmark/runners/event_stream.py`
  - `build_turn_events()`、`GranularityAggregator._aggregate_pairs()`、session 边界
- `src/memory_benchmark/methods/registry.py`
  - `_lightmem_consume_granularity()`、LightMem factory、registration resolver
- `src/memory_benchmark/methods/lightmem_adapter.py`
  - `ingest()`、`_native_turn_batch()`、`_native_pair_batch()`、
    `_normalize_session_to_pairs()`、`_real_message()`、`_placeholder_message()`、
    `_turn_timestamp()`、`_build_retrieval_evidence()`
- `configs/methods/lightmem.toml`
- 直接测试：
  - `tests/test_lightmem_adapter.py`
  - `tests/test_method_registry.py`
  - `tests/test_beam_adapter.py`
  - `tests/test_beam_registered_prediction.py`
  - `tests/test_event_stream.py`
  - manifest/resume 相关用例按引用定点读取

## 5. 必须新增/收紧的强反例

测试必须走真实 `build_turn_events → GranularityAggregator(pair) → LightMem.ingest` 生产边界，
不能只手调 `_normalize_session_to_pairs()`：

1. registry/factory 对 `beam` 同时解析为 `pair`，manifest concrete identity 也为 `pair`；
2. 100k 风格正常 user→assistant 只产生一次 backend call，两个 real slot、零 placeholder，
   content/role/public ids 不漂移；无自身时间的 assistant 只回落本 session anchor；
3. 10m 风格 positional id（含 `pN:sM:tK`）原样进入 pair candidate ids；
4. 两个连续 user 不互配：两个独立 call、各一个 real id、各自 placeholder；
5. assistant-first/连续 assistant 不丢失、不改 role，且不与下一 session 的 user 配对；
6. explicit 双 None 在 `online_soft + preserve_none` 下原样进入两个 slot；空串/缺 timestamp
   语义不被本批放宽；
7. BEAM RetrievalEvidence 仍为 `n_a/none`，reason code 不变；
8. 旧 manifest `consume_granularity=turn` 与新 `pair` resume mismatch，同值才 match；不得为救
   fixture 放宽严格门；
9. 100k 与 10m registered fake workflow 的 ingest/answer/evaluate 既有契约不退化；若测试替身
   模拟 LightMem，就必须镜像 concrete pair 身份，不能继承被替换 method 的声明蒙混过关。

测试 docstring 与新增 helper 均需中文。凡声称“没有 placeholder”“没有跨 session”“两个 id
同批”必须断言实际 backend payload/call sequence，不准只断言 helper 返回类型。

## 6. 允许修改的文件

只允许修改：

- `src/memory_benchmark/methods/registry.py`
- `tests/test_lightmem_adapter.py`
- `tests/test_method_registry.py`
- `tests/test_prediction_cli.py`
- `tests/test_beam_registered_prediction.py`
- `tests/test_artifact_evaluation_runner.py`
- `docs/reference/integration/lightmem.md`
- 新建 `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/
  lightmem-beam-pair-preflight-r1-implementation.md`

允许清单中的文件不需要制造空白改动；只提交真实需要的路径。禁止修改：

- `src/memory_benchmark/benchmark_adapters/beam.py`
- `src/memory_benchmark/runners/event_stream.py`
- `src/memory_benchmark/methods/lightmem_adapter.py`
- 任意 evaluator/provider protocol/TOML/third_party/data/outputs
- README、roadmap、policy、checklist、safety dossier、actor 卡自身

发现必须修改禁止路径才能正确完成时，按 §7 停工交回，不许扩大 scope。

## 7. 停工条件

立即停工并记录最小反证，不得硬做：

1. current source-lock/data 推翻 §2 的角色、session 或时间结构；
2. pair 聚合会跨 session、丢真实 turn，或无法表达已知 10m same-role adjacency；
3. 修复需要改变 LightMem segmentation/extraction/placeholder 核心算法，而不只是 registration
   消费边界；
4. 发现 BEAM 已有 current-v7 真实 run 依赖旧 `turn` 身份且新 manifest 仍可能错误 resume；
5. 需要修改允许清单外文件；
6. 真实 API、模型下载、外网或私有 gold 才能继续；
7. 15 分钟内无法用一手源码/数据消解的承重矛盾。

## 8. 最小自检

只跑一次最终相关集合，不跑全量 pytest、compileall、真实 API：

```bash
uv run pytest -q \
  tests/test_lightmem_adapter.py \
  tests/test_method_registry.py \
  tests/test_prediction_cli.py \
  tests/test_beam_adapter.py \
  tests/test_beam_registered_prediction.py \
  tests/test_event_stream.py \
  tests/test_artifact_evaluation_runner.py \
  tests/test_documentation_standards.py
git diff --check
```

隔离 worktree 缺 gitignored 资产造成的失败，须在同一 pristine baseline 复现后才可标环境问题；
不得删除断言、吞异常、改 expected 到错误现状或跳过测试来“变绿”。

## 9. commit 与回报

提交前：

1. `git status --short` 过目；
2. `git add` 只列本卡真实修改的显式路径，禁止 `-A` / `.`；
3. 再看暂存区；
4. 本地 commit，禁止 amend 既有 commit、禁止 push。

按 `actor-handbook.md` §4 回报：

1. commit hash；
2. 定向测试尾行原文与 `git diff --check`；
3. 实际改动文件；
4. 偏差/停工点；
5. subagent 分工（未使用也写）；
6. 实际模型/入口及是否切换。

到此停止，等待架构师 full diff、定向复跑、合流/全量门与最终裁决。
