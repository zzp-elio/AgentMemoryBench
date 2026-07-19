# Actor 卡：Mem0 × LongMemEval current-main 差量预检

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**只审 current Mem0 × LongMemEval 差量，不调用真实 API、不修改生产代码、
不重跑 S/M 全量 census。actor 可自行组织 subagent，不能扩大 scope；实质使用须披露。

## 0. 目标与判词

确认 source-locked LongMemEval 的 assistant-first、连续同 role、pure-assistant/user、奇数与 blank
turn 经 canonical session 后，current Mem0 adapter 实际如何按位置分 batch、保 role/content/time、
隔离每题并生成诚实 retrieval evidence。核心 `Memory.add` 对这些 shape 的内部接受性由并行 core
卡裁；本卡不得重复审整个 core。

唯一判词：`READY_FOR_JOINT_RULING` 或 `BLOCKED(<最小缺口>)`。不等于付费 smoke 授权。

## 1. 环境与必读

- worktree：`/Users/wz/Desktop/mb-actor-mem0-longmemeval`
- branch：`actor/mem0-longmemeval-delta-preflight`
- 开工记录 hash/status；不碰用户未跟踪资产。

依次读：

1. `AGENTS.md`
2. ws02.7 README 顶部胶囊与最新断点
3. `branches/method-recertification/mem0/README.md`
4. `docs/reference/actor-handbook.md`
5. `docs/survey/异常情况/longmemeval.md`
6. `docs/survey/{datasets,workflows}/longmemeval.md`
7. `docs/reference/integration/mem0.md` B2/B4/B5/B9/B11
8. 本卡 §3 源码/测试

缺 data 可只读软链；禁止读未跟踪 OpenCode 草稿当事实源、联网、下载或读 `.env`。

## 2. 稳定事实复用门

只核 source-lock hash 是否漂移，不重新统计。直接复用：

- blank、assistant-first、same-role、pure-assistant/user、奇数 turn 与 duplicate session id 的现行
  计数/例子；结构化 role 权威，blank 跳过，其余非空 turn 全保留；
- duplicate session occurrence 用稳定 suffix，不覆盖；
- turn 无独立 time，继承本 session raw date；question time 只进 answer builder，不用于 history
  cutoff；完整 history 保留；
- private `has_answer/answer/answer_session_ids` 不可达 method；官方 retrieval 主 gold 只取 user
  target，canonical denominator=419；
- Mem0 的 session batch lineage 最多支持 session provenance，不冒充 fact-level turn；排名资格
  另看 stable ranking/depth。

发现 source identity 漂移即停工；没有漂移就禁止再造一份异常账。

## 3. current-main 承重链

- `benchmark_adapters/longmemeval.py` 的 session/turn/public metadata/smoke crop
- `runners/event_stream.py` 的 session 聚合
- `methods/registry.py::_mem0_consume_granularity()` 与 Mem0 factory
- `methods/mem0_adapter.py` 的 `_ingest_native_session()`、`_turn_from_event()`、
  `_turn_to_message()`、`_turn_batch_metadata()`、`_add_with_provenance()`、retrieve/evidence
- `configs/methods/mem0.toml`
- official current harness
  `third_party/methods/mem0-main/memory-benchmarks/benchmarks/longmemeval/run.py`
  的 session sort、`pair_turns()`、blank skip、`mem0.add()` 与 namespace
- LongMemEval registry/prompt/evaluators 与相关 registered/adapter tests

不得把 LightMem placeholder 机制套给 Mem0；Mem0 接受 variable-length list 时，应记录真实 list，
不是为了形式统一补空 message。

## 4. 六类 production 映射探针

从稳定异常账选公开位置或构造等价 synthetic，使用 production adapter/event + fake backend，覆盖：

1. 正常 `user→assistant`；
2. assistant-first；
3. `user→user`；
4. `assistant→assistant`；
5. singleton/pure-user；
6. singleton/pure-assistant；
7. blank 夹在真实 turn 中（额外强反例）；
8. duplicate session occurrence 边界（额外强反例）。

逐层写：

```text
raw session
→ canonical retained Turns + stable session id
→ SessionBatch
→ adapter position chunks
→ 每次 Memory.add exact messages/source_turn_ids/run_id/metadata/prompt
```

必须回答：

- current registry 真是 `session`，adapter 是否对 retained turns 纯按位置 `[0:2],[2:4]...`；
- same-role、assistant-first、singleton 是否保持结构化 role，不按 speaker 首现交替重写；
- blank 是 canonical 前跳过还是 adapter 后造成 pair 跨空位；与 current official harness
  `any(empty) skip whole pair` 的差异属于 bug、framework fidelity improvement 或 behavior variant；只给证据，
  不擅自代裁；
- session 之间不混 batch；duplicate occurrence namespace 不覆盖；每个 retained turn 恰一次；
- `_turn_to_message()` 是否额外写 `user:`/`assistant:` speaker 前缀；这与官方 current harness
  content bytes 的差异是否有明确理由；
- 每条 message 只含本 session time，绝无 question/相邻/wall-clock 回填；
- private label 负空间逐层为零。

## 5. 隔离、readout、metric 与 smoke 候选

核对：

- 每个 LongMemEval question 的完整 haystack 是一个 framework conversation/isolation key；不同题
  backend/run_id 不泄漏；
- retrieve 不做 question-time cutoff，search 只用当前 run_id；
- unified完整 answer builder 获得 formatted memory、question、question time；legacy
  `author_longmemeval` 不在本轮运行；
- RetrievalEvidence 当前应安全声明到何种 granularity；recall/rank 对 N/A/valid 的现行实际输出、
  stable ranking 与 top_k=10/k30-50 的披露；
- current registry 全 evaluator、manifest/source/adapter identity 与 resume 键。

只给不调用 API 的最小 B11 候选：一个普通 S question + 一个公开异形 S question；按 public shape
选，不看 gold/answer，不把 pair 数换算成 API 次数。若 core 卡尚未返回，写
`CORE_CONTRACT_DEPENDENCY_PENDING`，不要因此伪造 ready。

## 6. 唯一交付、自检与回报

只新增：

```text
docs/workstreams/ws02.7-method-track/branches/method-recertification/mem0/notes/
  mem0-longmemeval-delta-preflight.md
```

不得改其他文件。note 包含 source identity、八类映射、与 current official harness 差异、time/privacy/
isolation、metric/identity、测试盲点、候选与唯一判词；临时脚本构造/stdout 必须自包含。

只跑 docs 标准门与 `git diff --check`；显式 add 唯一 note，检查 status，本地 commit 建议
`docs(mem0): preflight longmemeval delta`，不 push/amend/full pytest/compileall/API。按
actor-handbook §4 回报后停止。
