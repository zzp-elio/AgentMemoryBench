# Actor 卡：MemoryOS × BEAM current-main 差量预检

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**本卡只审 MemoryOS × BEAM，不调用真实 API、不修改生产代码、不重做 BEAM
全量异常普查。actor 可自行组织 subagent，但不得扩大范围；主 actor 负责最终复核。

## 0. 目标与唯一判词

验证标准 split 与 10M 已知异常在 MemoryOS page 接口上的 role/pair/placeholder/session time、
canonical id、readout、BEAM rubric 与 retrieval metric 资格；不得“修正”官方错位内容。

note 最后只能写：

```text
READY_FOR_B11
READY_FOR_B11_WITH_NA(<指标及原因>)
NEEDS_CODE(<最小、可测试的缺口>)
```

本卡不是付费 smoke 或冻结授权。

## 1. 隔离与必读

- 建议 worktree：`/Users/wz/Desktop/mb-actor-memoryos-beam`
- 建议 branch：`actor/memoryos-beam-preflight`

依次读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/{README.md,memoryos/README.md}`
4. `docs/reference/actor-handbook.md`
5. `docs/survey/异常情况/beam.md`
6. `docs/workstreams/ws02.6-first-smoke-hardening/notes/{beam-source-lock.json,beam-frozen-v1.md}`
7. `docs/reference/integration/memoryos.md` 与本卡点名源码

缺 gitignored `data/BEAM`、`third_party/benchmarks/BEAM`、models 时可建只读软链并披露；不得
联网下载或读 `.env`。

## 2. 复用事实

- 100K/500K/1M role 结构严格 user→assistant；10M 有两处 dangling user，其中一处下一组正文
  明显答错位，raw content 必须原样保留；
- raw `id/index` 会重复/跳跃，canonical public turn id 使用 session/batch/position namespace，
  不能回退到 raw id 作唯一键；
- 10M 有缺时与跨 session anchor 回退，框架不重排、不猜修；source time 只按 canonical 契约传；
- BEAM gold unit 是单 message，歧义 raw id 已由 evaluator-private group 解决；BEAM retrieval Recall
  是 framework supplementary，官方主评是 rubric judge；
- variant 不混 run，标准 split 与 10M 至少各有一个真实 sentinel。

只核 source lock，禁止重扫同一 census。

## 3. 必须亲读的一手链

- BEAM canonical adapter、source lock 与 smoke crop
- event stream pair/session aggregator、registry `_memoryos_consume_granularity()`
- MemoryOS adapter session converter/pair helper/timestamp/sidecar/retrieve/items/evidence/readout
- product `memoryos-pypi/{memoryos,retriever,short_term,mid_term,long_term}.py`
- BEAM recall、rubric judge、answer builder、registered tests
- `configs/methods/memoryos.toml`

## 4. exact-call 强反例

用 canonical adapter → event stream → fake backend，至少覆盖：

1. 标准 user→assistant pair；
2. 连续两个正常 pair；
3. 10M dangling user；
4. 10M 已知错位窗口（内容只观察、不改写）；
5. assistant orphan 的合成反例；
6. session 尾 dangling + 下一 session assistant-first；
7. 有 session anchor、无 turn time；
8. 缺 time；
9. 跨 session time 回退；
10. 重复 raw id/跳跃 index 但 canonical ids 唯一。

逐例记录到 `add_memory(user_input, agent_response, timestamp)` 和 sidecar ids，锁死：

- 空侧只用 `""`，每个真实 turn 恰一次，不跨 session；
- raw 错位内容原样进对应 canonical turn，不向后搬答案；
- typed timestamp 只来自该 page 的合法 source turn/session anchor；missing 不拿 wall clock 冒充
  source time；time 回退不重排；
- consume granularity 的 registered 值、实际 call sequence 与 manifest 必须一致；
- private rubric/gold/evidence 不可达 method。

比较 current `session` 与产品 page 单元：若改成 framework `pair` 只会消除 adapter 自行重配且保持
exact call 等价，可列最小建议；但本卡不得自行改 registry。

## 5. readout、Recall 与 rubric

按 STM/MTM/user knowledge/assistant knowledge 做全层矩阵，分别裁：

- BEAM single-message gold 对 page `source_turn_ids` 的 Recall 资格；一页包含两个 child 时 group
  any-of 是否准确，不能靠 raw id；
- 完整 formatted memory 与 `items` 覆盖面是否一致；
- stable ranking/NDCG/Precision/F1@k；
- BEAM rubric judge、equivalence、abstention scope 与 efficiency observation；
- answer-only lexical metrics是否按 registry 启用。

官方不算 Recall，所以即使 lineage 有效也必须标 `framework_supplementary`；若产品多层 readout
无法完整列 item，则 Recall N/A，不得把 N/A 当接入失败。

## 6. identity 与 smoke 候选

核 source/config/consume/evidence/track/resume identity。给一个 100K W2 与一个 10M W1 候选，
覆盖标准 pair 与真实 dangling/错位 shape；说明 rubric judge 调用数由真实 artifact 预览决定，
不执行 API、不用 pair 数估计 API 次数。

## 7. 唯一交付与自检

只新增：

```text
docs/workstreams/ws02.7-method-track/branches/method-recertification/memoryos/notes/
  memoryos-beam-current-main-preflight.md
```

note 必含 10 类映射、session-vs-pair 对表、time/id/隐私、全层 metric 矩阵、smoke 候选、测试盲点、
最小补丁蓝图与唯一判词。不得改其它文件。

只运行：

```bash
uv run pytest -q tests/test_documentation_standards.py
git diff --check
```

仅显式 add note，本地 commit 建议 `docs(memoryos): preflight beam current main`；不 push、不 amend、
不跑全量/compileall/真实 API。按 actor-handbook §4 回报后停止。
