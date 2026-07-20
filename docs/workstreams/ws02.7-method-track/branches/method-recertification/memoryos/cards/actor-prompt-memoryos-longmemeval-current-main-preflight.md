# Actor 卡：MemoryOS × LongMemEval current-main 差量预检

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**本卡只审 MemoryOS × LongMemEval，不调用真实 API、不修改生产代码、不
重复 LongMemEval 全量异常普查。actor 可自行组织 subagent，但不得扩大范围，主 actor 负责复核。

## 0. 目标与唯一判词

证明 current canonical LongMemEval 的 user/assistant 异形序列被 MemoryOS page 接口无损处理，
source time、question time、placeholder、session isolation、readout 与 Recall/rank 资格真实可审。

note 最后只能写：

```text
READY_FOR_B11
READY_FOR_B11_WITH_NA(<指标及原因>)
NEEDS_CODE(<最小、可测试的缺口>)
```

本卡不是付费 smoke 或冻结授权。

## 1. 隔离与必读

- 建议 worktree：`/Users/wz/Desktop/mb-actor-memoryos-lme`
- 建议 branch：`actor/memoryos-longmemeval-preflight`

依次读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/{README.md,memoryos/README.md}`
4. `docs/reference/actor-handbook.md`
5. `docs/survey/异常情况/longmemeval.md` 与 `docs/survey/{datasets,workflows}/longmemeval.md`
6. `docs/workstreams/ws02.6-first-smoke-hardening/notes/{longmemeval-source-lock.json,longmemeval-frozen-v1.md}`
7. `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/longmemeval-anomaly-ledger-audit.md`
8. `docs/reference/integration/memoryos.md` 与本卡点名源码

缺 gitignored data/models 可建只读软链并披露；不联网、不读 `.env`。

## 2. 复用的稳定事实

- canonical role 以结构化 `user`/`assistant` 为准，不从内容猜 role；
- assistant-first、同 role 相邻、singleton/odd、blank turn 等已在稳定异常账有 source-locked
  计数与位置；blank 的 canonical 处置、question_date 与完整 haystack no-filter 口径已裁；
- retained turn 必须恰一次，不能跨 session 配对；question date 只进 answer builder，不进 ingest
  timestamp 或 retrieval cutoff；
- gold evidence group/官方 419 分母及 assistant-side target 差异已由 shared evaluator 处理。

不得重算一份同名 census。只在 source lock 漂移或发现能推翻稳定页的新反证时停工。

## 3. 必须亲读的一手链

- LongMemEval canonical adapter、event stream `GranularityAggregator("pair")`
- registry `_memoryos_consume_granularity()` 与 MemoryOS registration
- MemoryOS adapter `_ingest_pair()`、`_pair_to_add_memory_args()`、timestamp/event rebuild、sidecar、
  retrieve/items/evidence/readout
- `memoryos-pypi/{memoryos,retriever,short_term,mid_term,long_term}.py`
- LongMemEval answer builder、Recall/rank evaluator、registered prediction/adapter tests
- `configs/methods/memoryos.toml`

## 4. production pair 与 time 强反例

用 production canonical objects → event stream → fake backend 记录 exact `add_memory()`；至少覆盖
稳定账里的六类 raw shape：

1. 正常 user→assistant；
2. assistant-first；
3. user→user；
4. assistant→assistant；
5. singleton user / singleton assistant；
6. odd tail、blank 被 canonical 处理后的邻接；
7. 前 session dangling user + 后 session assistant-first；
8. 同正文跨两个 session/conversation。

逐例写：raw/canonical ids → `TurnEvent.timestamp/original_turn_time` → `TurnPair` →
`add_memory(user_input, agent_response, timestamp)` → sidecar source ids。

锁死：

- orphan/dangling 只补空字符串；不跨 session、不重排、不丢 turn；
- timestamp 只取该 page 的 source turn/session time；question_date、相邻 session、wall clock 不得
  冒充 source time；若 pair 两侧时间不同，必须报告产品单 timestamp 的实际取舍与信息损失；
- content 不额外拼 `user:`/`assistant:`，因为产品接口字段已表达角色；
- private `has_answer`/answer/session ids/gold 不可达 method；
- per-question isolation 不能因完整 haystack 重复 ingest 或跨 question 污染。

若当前 pair 聚合/adapter 与以上冲突，判 `NEEDS_CODE` 并给最小强反例，不自行改代码。

## 5. Recall/rank 资格必须从完整 readout 反推

建立 STM / MTM retrieved pages / user knowledge / assistant knowledge 四层矩阵，逐层列
formatted_memory、items、lineage、rank、mutation。然后分别裁：

- LongMemEval session-level Recall；
- turn-level Recall（官方 user-side target turn 与 Gold Evidence Group 能否由 page lineage
  精确支持，不得因 page 同时含 user+assistant 就自动有效）；
- retrieval rank/NDCG（stable ranking、top_k 实际深度与官方 k）；
- no-user-target/abstention 题的 N/A/剔除行为；
- answer judge/lexical metrics。

特别检查 `_build_retrieval_evidence()` 当前 blanket `valid/turn` 与 `_retrieved_items()` 只导出
MTM page 是否矛盾。若完整 answer context 含无 exact lineage 的 knowledge/STM，不能只拿 MTM
子集冒充整个产品 retrieve，除非现有 metric/artifact 明确命名为该子检索且 evaluator 也如此消费。

## 6. identity 与 smoke 候选

核 source/config/consume granularity/evidence/track/resume identity；选两个**按原始顺序而非 gold**
的 S variant 单题候选：一个正常、一个含 assistant-first/同 role/singleton。说明 LongMemEval smoke
裁剪到底保留多少 sessions/turns，禁止把“一个 question”误写成必然完整大 haystack，也禁止用
结构数量估计 LLM 调用数。给 W1/W2 最小运行建议，不执行 API。

## 7. 唯一交付与自检

只新增：

```text
docs/workstreams/ws02.7-method-track/branches/method-recertification/memoryos/notes/
  memoryos-longmemeval-current-main-preflight.md
```

note 要自包含：source identity、8 类调用链、时间/隐私断言、全层 readout 与 metric 矩阵、smoke
候选、测试盲点、最小补丁蓝图与唯一判词。不得改其它文件。

只运行：

```bash
uv run pytest -q tests/test_documentation_standards.py
git diff --check
```

仅显式 add note，本地 commit 建议 `docs(memoryos): preflight longmemeval current main`；不 push、
不 amend、不跑全量/compileall/真实 API。按 actor-handbook §4 回报后停止。
