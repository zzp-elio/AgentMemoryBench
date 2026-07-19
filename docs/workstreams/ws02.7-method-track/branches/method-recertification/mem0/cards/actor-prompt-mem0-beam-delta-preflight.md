# Actor 卡：Mem0 × BEAM current-main 差量预检

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**只审 Mem0 × BEAM current-main method 差量，不调用真实 API、不改生产
代码、不重扫全量 Arrow 数据。可自行用 subagent 分包只读取证，但不得扩大 scope；主 actor
亲核承重锚并披露分工。

## 0. 目标与判词

确认 100K/500K/1M 标准 pair 与 10M dangling user、错位 content、缺时 batch、anchor 回退、raw
id 重启，经 current Mem0 pair ingest 后保持 source order/role/content/time/isolation；同时核
Mem0 官方 current BEAM harness、rubric judge、evidence N/A 与浮点分数链。

唯一判词：`READY_FOR_JOINT_RULING` 或 `BLOCKED(<最小缺口>)`。本卡不授权 smoke。

## 1. 环境与必读

- worktree：`/Users/wz/Desktop/mb-actor-mem0-beam`
- branch：`actor/mem0-beam-delta-preflight`
- 记录基线/status；用户未跟踪文件与数据只读。

依次读：

1. `AGENTS.md`
2. ws02.7 README 顶部恢复胶囊/最新断点
3. Mem0 子线 README
4. `docs/reference/actor-handbook.md`
5. `docs/survey/异常情况/beam.md`
6. BEAM dataset/workflow 稳定页
7. `docs/reference/integration/mem0.md` B2/B4/B5/B9/B11
8. 本卡 §3 current source/tests

缺 data/benchmark source 可只读软链；不联网下载、不读 `.env`。

## 2. benchmark 稳定层直接复用

只核 source lock 是否漂移，禁止重算全量计数：

- 100K/500K/1M 结构严格 user→assistant 偶数 pair；1M 四个 conversation raw id 重启，public id
  已用 positional namespace；
- 10M 两个 group 为 `user→assistant→user`，下一 group 从 user 开始；其中一处下一 assistant
  内容似乎答上一 dangling user，框架仍按 raw role/order 保留、不搬答案；
- 10M 一个 batch 无 time_anchor、5 次跨 session anchor 回退；不造时、不全局排序；
- 10M malformed private gold `'--'` 与 ambiguous raw ids 只由 private group处理；
- BEAM gold 是单 message unit，Mem0 pair batch sidecar 不能证明抽取 fact来自 pair 内哪个 child，
  retrieval Recall=N/A；
- rubric judge 必须保留 0/0.5/1 浮点，历史 int 截断已经修复，本卡只查 current 回归锚。

## 3. current-main 承重链

- `benchmark_adapters/beam.py` 的 100K/10M session/turn/public id/time/smoke crop
- `runners/event_stream.py` 的 pair aggregator 与 session boundary
- `methods/registry.py::_mem0_consume_granularity()` / factory
- `methods/mem0_adapter.py` 的 `_ingest_native_pair()`、turn renderer、metadata/provenance、retrieve/
  evidence
- `configs/methods/mem0.toml`
- current official harness
  `third_party/methods/mem0-main/memory-benchmarks/benchmarks/beam/run.py`
  的 `parse_beam_chat()`、`batch_to_chunks()`、time epoch、namespace/add/search
- BEAM answer/rubric evaluator、artifact judge efficiency 与相关 registered/adapter tests

产品 core 对 consecutive roles 的语义由并行 core 卡统一裁，不在本卡重复全链。

## 4. production 映射探针

用 production adapter/event + fake Mem0 backend，覆盖：

1. 100K 标准 user→assistant pair；
2. 同 session 两个连续正常 pairs；
3. 10M `13674–13677` dangling→next-user 边界；
4. 10M `12988–12992` content 错位边界；
5. 10M 缺 time_anchor batch；
6. 相邻 session anchor 回退；
7. 1M raw id 重启但 public positional id 不冲突；
8. 奇数 tail 位于 session 末尾，不能跨下一 session配对。

逐层记录：

```text
raw group/message
→ canonical session/turn id/role/content/source time
→ TurnPair(first/second/orphan/dangling)
→ Memory.add exact messages/source_turn_ids/run_id/metadata/prompt
```

必须回答：

- current registry=`pair` 与 strict manifest/resume 是否一致；
- 正常 pair 一次 add 两个真实 role；dangling user 是 singleton list 还是被 placeholder/下一 user
  改写；Mem0 不需要结构 placeholder 时不得添加空 assistant；
- session 边界绝不组成 pair；每条真实 message 恰一次；
- raw content 错位不由 framework 猜修；
- effective time 取每个 turn/source session；缺时为 None且不前缀，anchor 回退不排序；
- official REST harness 的 `timestamp=time_epoch` 与 framework product core 的 content+metadata 是
  两个接口层，不能写成 byte parity；列为 product-compatible extension/variant并给理由；
- public positional ids 进入 sidecar，raw id只作 locator，private rubric/gold不进 method。

## 5. readout、metric、judge 与 identity

核对：

- search 只用 run_id，formatted memory 与 unified BEAM完整 answer builder；
- RetrievalEvidence 应为 `n_a/beam_gold_is_single_message`（或 current source真实值），不能因
  pair lineage非空就硬算 Recall；
- BEAM rubric judge 与 abstention/equivalence 分支都保持 float，检查 current tests/score artifact
  类型，不能只看论文表；
- judge model/token/scope efficiency 共享修复仍挂载，离线 evaluator 不造空 observation；
- adapter/source/contract/granularity/track identity 与 resume；TOML current 参数。

给出 100K W1/W2 与 10M W1/W2 的最小 runtime 覆盖建议；可建议哪些轴正交而省略，但不得调用
API或把结构 chunk 数当 API 次数。

## 6. 唯一交付与门

只新增：

```text
docs/workstreams/ws02.7-method-track/branches/method-recertification/mem0/notes/
  mem0-beam-delta-preflight.md
```

note 自包含八类 probe、official-vs-product time/namespace 表、metric/judge/identity、测试盲点与唯一
判词；不得改其他文件。

只跑 docs 标准门与 `git diff --check`；显式 add note、status 过目，本地 commit 建议
`docs(mem0): preflight beam delta`，不 push/amend/full pytest/compileall/API。按 handbook §4
回报并停止。
