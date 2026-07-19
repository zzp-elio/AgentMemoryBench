# Actor 卡：Mem0 × HaluMem current-main 差量预检

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**只做 Mem0 × HaluMem current-main 离线差量审计，不调用真实 API、不改
生产代码、不重扫 Medium/Long 数据。可使用 subagent 只读分工，不得扩 scope；主 actor 负责。

## 0. 目标与判词

HaluMem 是边 ingest 边按 session 测 extraction/update，最后测 QA，不是完整建库后一次性评分。
本卡要证明 current Mem0 每个 session 恰一次 `Memory.add()`、`end_session()` 只报告该次 add 的
results、长期 store 继续保留、operation-level 顺序正确；并核三大类细项与 memory type /
question type，而不是只看 overall。

唯一判词：`READY_FOR_JOINT_RULING` 或 `BLOCKED(<最小缺口>)`。不授权真实 smoke。

## 1. 环境与必读

- worktree：`/Users/wz/Desktop/mb-actor-mem0-halumem`
- branch：`actor/mem0-halumem-delta-preflight`
- 开工记录 hash/status；不碰主树未跟踪资产。

依次读：

1. `AGENTS.md`
2. ws02.7 README 顶部胶囊/最新断点
3. Mem0 子线 README
4. `docs/reference/actor-handbook.md`
5. `docs/survey/{datasets,workflows}/halumem.md` 与 benchmark frozen/source lock
6. `docs/reference/integration/mem0.md` 的接口面、B2/B4/B5/B6/B7/B9/B11
7. LightMem HaluMem metric breakdown note只作共享 evaluator 索引，不套 method 行为
8. 本卡 §3 current source/tests

缺 data 可只读软链；不联网、不下载、不读 `.env`。

## 2. 稳定 benchmark/evaluator 事实

禁止重做 Medium/Long census。直接复用：

- operation-level 顺序是 session ingest → extraction/update probe → 下一 session → 最终 QA →
  memory-type；runner 强制 single worker；
- extraction 评分对象是**当前 session 产生的 memory report**，不能把全库检索结果冒充本 session
  extraction；
- update 针对 session 间 memory point 变化，QA 按 question_type 分 C/H/O all/valid；
- extraction 六项、update C/H/O、QA C/H/O、Event/Persona/Relationship 三种 memory type 都应有
  分项/overall；
- HaluMem 没有 turn qrel，retrieval Recall/NDCG N/A；private memory_points/evidence/judge labels
  不可达 method。

## 3. current-main 承重链

- `benchmark_adapters/halumem.py` 的 conversation/session/turn/question/private label
- `runners/operation_level.py` 与 prediction/session report artifact 路径
- `methods/registry.py::_mem0_consume_granularity()`、Mem0 factory 的
  `session_memory_report=True`、max_workers/clean hooks
- `methods/mem0_adapter.py` 的 `_ingest_native_session()`、`end_session()`、
  `_memory_texts_from_add_result()`、renderer/add/provenance/retrieve/evidence
- current vendored `Memory.add()` 返回值与 ADD-only drift 点；详细 role/batch core语义留给并行 core卡
- HaluMem extraction/update/qa/memory-type evaluators、registry、artifact judge efficiency
- 对应 HaluMem registered/operation-level/Mem0 adapter tests与 `configs/methods/mem0.toml`

Mem0 官方 repo 没有 HaluMem 专用 harness 时明确写无；本格以通用 product core 接入为主，不杜撰
author profile。

## 4. stateful 零 API 探针

不能只用“每次 add 直接返回固定结果”的无状态 fake。用 hermetic current Mem0 core 或一个会记录
store/add-results/last-message scope 的承重 fake，至少覆盖：

1. 单 session 两 turn，一次 add；
2. 连续两个 session，s1/s2 各产生非空不同 results；
3. s1 非空、s2 零 extraction；
4. s1/s2 都非空且长期 store 最终同时存在；
5. 同 session user/assistant role与时间；
6. session time 有、turn time无；
7. source time全无；
8. add 返回 ADD results 外还含非标准/空 item 的严格解析边界。

逐层记录：

```text
canonical Session
→ SessionBatch
→ Memory.add exact messages/source ids/run_id/metadata/prompt
→ add results
→ end_session SessionMemoryReport
→ operation-level extraction/update evaluator input
→ retained product store
```

锁死：

- 每 session 只调用一次 add，内容包含该 session 全部真实 turns恰一次，session之间不混；
- report 是本次 add results 的增量，不是累计 list、全库 search 或上个 session残留；
- `end_session()` 后只清 report staging，不删除 Mem0长期 memory；
- extraction prompt 可以读取既有 memory/last messages是 method原生算法；但**公开 report 只能列本次
  返回的新增/变化结果**。若 current ADD-only path不会返回 update/delete，按真实行为说明；
- source_turn_ids 批粒度为 session，不能宣称 fact-level turn；
- time 只来自当前 turn/session，缺失为 None，不用 QA/question/wall clock；
- private memory point/label 不进 add/search/answer prompt。

临时脚本不得提交，note须写探针构造和关键 stdout；真实 core若需要 API，使用可注入 fake LLM/
embedder/vector，不连接外部端点。

## 5. evaluator/readout/identity 对表

列出 current HaluMem 全 evaluator 依赖顺序与每份 artifact：

- extraction 的 Recall/Weighted Recall/Target Precision/Accuracy/FMR/F1；
- update C/H/O；
- QA C/H/O overall + 各 question_type 的 all/valid；
- memory type Event/Persona/Relationship；
- 通用 offline answer metrics若注册则按任务资格列出，不强加 retrieval metric；
- 三类 LLM judge 的 model/token/scope observations与正确公开 scope id。

再核 product retrieve/readout、run_id隔离、manifest source/adapter/protocol/granularity、resume与
clean-failed-ingest。给出 Medium 最小 W1 smoke shape，但不估算 API次数、不运行API。

## 6. 唯一交付与门

只新增：

```text
docs/workstreams/ws02.7-method-track/branches/method-recertification/mem0/notes/
  mem0-halumem-delta-preflight.md
```

note 包含八类 stateful probe、session-report/长期 store分离、完整 metric breakdown、privacy/
identity、测试盲点与唯一判词。不得改其他文件。

只跑 `uv run pytest -q tests/test_documentation_standards.py` 与 `git diff --check`；显式 add note、
status 过目，本地 commit 建议 `docs(mem0): preflight halumem delta`，不 push/amend/full pytest/
compileall/API。按 actor-handbook §4 回报后停止。
