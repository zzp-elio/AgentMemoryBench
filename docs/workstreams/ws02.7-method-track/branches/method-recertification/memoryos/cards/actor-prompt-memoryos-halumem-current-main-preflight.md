# Actor 卡：MemoryOS × HaluMem current-main operation 预检

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**本卡只审 MemoryOS × HaluMem，不调用真实 API、不修改生产代码、不重扫
HaluMem 全量数据。actor 可自行组织 subagent，但不得扩大范围；主 actor 对最终证据负责。

## 0. 目标与唯一判词

HaluMem 是边 ingest session 边测 extraction/update/QA，不是完整 build 后统一答题。本卡要证明
MemoryOS 当前到底能诚实支持哪些 operation metric，尤其“刚结束的当前 session 的 method
memory”是否可获得；不为补满表格而回显 raw input 或扭曲 MemoryOS 层级迁移。

note 最后只能写：

```text
READY_FOR_B11
READY_FOR_B11_WITH_NA(<extraction/update/QA/memory_type 中的具体项及原因>)
NEEDS_CODE(<最小、可测试的缺口>)
```

N/A 是合法资格结论。本卡不是付费 smoke 或冻结授权。

## 1. 隔离与必读

- 建议 worktree：`/Users/wz/Desktop/mb-actor-memoryos-halumem`
- 建议 branch：`actor/memoryos-halumem-preflight`

依次读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/{README.md,memoryos/README.md}`
4. `docs/reference/actor-handbook.md`
5. `docs/survey/{datasets,workflows}/halumem.md`
6. `docs/workstreams/ws02.6-first-smoke-hardening/notes/{halumem-source-lock.json,halumem-frozen-v1.md}`
7. LightMem/Mem0 HaluMem frozen/preflight notes只作 runner/benchmark 入口导航，不继承 method 结论
8. `docs/reference/integration/memoryos.md` 与点名源码

缺 gitignored data/models/official benchmark 可建只读软链并披露；不得联网、读 `.env` 或运行 judge。

## 2. 复用事实

- operation runner 对每个真实 session：ingest → 可选 `end_session` report → update probes；随后按
  canonical 顺序继续下一 session，QA 在相应状态上执行；
- extraction gold 是当前 session memory points，不能用累计全库、下一 session 或 raw input
  直接回显；
- update probe 的 `RetrievalQuery.top_k=10` 是请求字段，但 shared HaluMem scorer 不对所有 method
  强制统一 top-10；产品没有可控 top_k 时要披露 product depth，不能在 shared runner 截文本；
- QA question_type 的完整 C/H/O breakdown、extraction/update 六列、Event/Persona/Relationship
  memory_type breakdown 与 judge efficiency 已由 shared evaluator 层实现；
- private memory_points/answer/judge labels 只到 operation runner/evaluator，不能进入 ingest。

只核 source lock；不重跑全量 census。

## 3. 必须亲读的一手链

- HaluMem canonical adapter 的 public/private session payload
- `src/memory_benchmark/runners/operation_level.py` 的真实阶段顺序、supports_extraction 判定、失败态
- provider protocol `SessionMemoryReport` / `end_session`
- registry MemoryOS registration/factory/consume granularity/capabilities
- MemoryOS adapter ingest/end_session(含继承默认)/retrieve/items/evidence/state/sidecar/clean
- product STM→MTM→LPM 迁移、`add_memory()`、retriever、各层持久状态
- HaluMem extraction/update/QA/memory_type evaluator 与 registered tests
- `configs/methods/memoryos.toml`

## 4. current-session extraction：先判能力，后谈实现

用真实 product classes 配本地 fake LLM/embedding（零 API）或等价承重 stateful backend，按至少
四个连续 session 运行；不能用“每次 add 直接返回固定 memory”的薄 fake。构造覆盖：

1. 单 pair session；
2. 多 pair session；
3. dangling user / orphan assistant 的空 placeholder；
4. STM 未满；
5. STM threshold crossing 触发迁移；
6. 新 session 内容与旧 session 高相似、可能合并；
7. update probe 后有 heat/N_visit 副作用；
8. clean/retry 后重放。

先现场确认：当前 `MemoryOS` 是否覆写 `end_session()`、operation runner 是否会写 N/A report。
然后回答以下三问：

1. 产品公开/持久状态能否识别“本 session 新增或变更的 method memory”，而非仅输入 page？
2. 若 page 被迁移/合并/summary，能否在不复制算法、不回滚状态、不泄露旧 session 的情况下返回
   当前 session 内容？
3. report 的 content 是否真是 method memory，还是 canonical raw conversation 的换皮回显？

只有三问都能用一手状态证明，才建议 `end_session()`。否则 extraction 必须 N/A；不得为了
HaluMem 修改 MemoryOS 核心迁移/合并或给产品强塞专用 flush。

## 5. update 与 QA 独立裁定

即使 extraction N/A，也必须继续零 API 审：

- 每个 update memory_point 的 query 在当时状态上检索，不提前看到未来 session；
- `query.top_k=10` 是否被 MemoryOS 忽略；产品实际 STM/MTM/LPM readout depth 与 formatted text
  怎么表示；无统一 top_k 不自动判失败，但必须 truthful identity；
- `RetrievalResult.items` 是否只含 MTM page而 formatted memory 含 STM/LPM，HaluMem update judge
  消费哪个字段；零 hit/降级状态是否可审；
- QA 用同一 operation state + benchmark builder，question/private gold 不回写 method；
- retrieval heat/N_visit 是官方副作用，不能为了 probe purity 压掉；
- failed ingest/update/QA/cleanup 的 resume 状态沿用共享 clean-retry 契约。

分别给 extraction、update、QA、memory_type 四项 eligibility，不得用一个 overall 结论代替。

## 6. metric 细项与观测

对当前 evaluator 实际 artifact 列出：

- extraction：R、Weighted R、Target P、Acc、FMR、F1 及 memory_type breakdown；
- update：C/H/O overall 与 memory_type breakdown；
- QA：C/H/O overall、valid denominator、六类 question_type breakdown；
- memory_type：Event/Persona/Relationship（以 current canonical label 为准）的合成条件；
- judge model/token/scope observations 与零调用分支。

若 extraction N/A 导致 memory_type 合成 N/A，要明确链式原因；不能输出 0 冒充不可评。

## 7. identity 与 B11 候选

核 source/config/consume/evidence/track/resume identity、max_workers=1 operation gate。给 Medium
1 conversation 的最小 B11 候选，必须包含足以触发 MemoryOS STM→MTM 的 session/turn 规模；若
默认 smoke 裁剪不足，给“结构覆盖规模”，但不要把 page 数换算成 API calls。列 judge-call preview
从 private labels 计算的方法，不执行 API。

## 8. 唯一交付与自检

只新增：

```text
docs/workstreams/ws02.7-method-track/branches/method-recertification/memoryos/notes/
  memoryos-halumem-current-main-preflight.md
```

note 必含 stateful trace、三问答案、四项 eligibility、完整 metric breakdown、identity/smoke 候选、
测试盲点、最小补丁蓝图与唯一判词。不得改其它文件。

只运行：

```bash
uv run pytest -q tests/test_documentation_standards.py
git diff --check
```

仅显式 add note，本地 commit 建议 `docs(memoryos): preflight halumem current main`；不 push、
不 amend、不跑全量/compileall/真实 API。按 actor-handbook §4 回报后停止。
