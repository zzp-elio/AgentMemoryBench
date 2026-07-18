# Actor 卡：Retrieval metric N/A summary 可空契约

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**你是施工 actor，不是架构师；本卡就是完整、自包含的执行 prompt。
允许自行组织 subagent，但不得扩大 scope；发生实质使用时须在完成报告披露，主 actor 对最终
diff 与报告负责。

## 0. 这张卡解决什么

LightMem × LongMemEval latest-v6 的真实 B11 单/双 worker run 已证明逐题资格门是正确的：
retrieval score rows 都是 `score=null, status=n/a`，没有伪造 Recall/NDCG。但两个 summary
仍写 `mean_score=0.0, total_questions=0`。这会把“本次共有题目，但没有一道具备计分资格”
误读成“零道题，平均分恰好为零”。

本卡只修**共享 retrieval summary 的聚合真值与 JSON 契约**。不改任何指标公式、gold group、
provider evidence、LongMemEval canonical 419 分母、query depth、top-k 或 method 资格判定。

本卡与 LightMem 产品 readout/embedding observation 修复卡可并行：本卡不得修改 method adapter、
registry、TOML 或真实 run artifacts。

## 1. 隔离环境与最小读序

- worktree：`/Users/wz/Desktop/mb-actor-retrieval-summary-contract`
- branch：`actor/retrieval-summary-contract`
- 基线：派发时最新 `main`；先原样记录 `git rev-parse --short HEAD`

若路径或分支已存在，停工报告，禁止删除/复用。若用户尚未创建，可执行：

```bash
git -C /Users/wz/Desktop/memoryBenchmark worktree add \
  /Users/wz/Desktop/mb-actor-retrieval-summary-contract \
  -b actor/retrieval-summary-contract main
cd /Users/wz/Desktop/mb-actor-retrieval-summary-contract
uv sync
```

只按顺序读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与最新断点
3. `docs/workstreams/ws02.7-method-track/branches/retrieval-metrics/README.md`
4. `docs/workstreams/ws02.7-method-track/branches/retrieval-metrics/notes/
   retrieval-evidence-m1-implementation.md`
5. `docs/reference/actor-handbook.md` §0-§4
6. 本卡允许清单内的生产代码与测试

不得重审五个 benchmark 数据、method provenance 或历史卡；真实 B11 artifact 只是反例来源，
不允许修改。

## 2. 已裁 summary v2 契约

### 2.1 计数与均值

五个 retrieval evaluator 的 summary 统一遵守：

- `total_questions`：本次 evaluator 消费的**全部** score record 数，包括有数值分数、provider
  `n_a`、`pending` 与 benchmark-policy exclusion；不能再等同于 numeric denominator。
- `scored_question_count`：`score` 为有限数值的记录数，且是 `mean_score` 的唯一分母。
- `mean_score: float | null`：
  - `scored_question_count == 0` 时必须为 JSON `null`；
  - 至少一道真正计分且实际均值为零时才可写 `0.0`；
  - 不能把显式 `None` 通过 `or 0.0`、默认值或类型强转重新变成零。
- evaluator 自有 mean 字段遵守同一可空语义，例如
  `overall_mean_recall_at_requested_k`；LongMemEval rank 没有任何参与者时，`mean_score=null`
  且既有空 metrics 结构保持诚实。
- `aggregation_contract_version="retrieval-summary-v2"`，五个 evaluator 都必须显式落盘。

这里不引入“eligible_question_count”一类第二套含混分母；若现有 evaluator 有同义字段，须对照
上述定义统一，而不是制造第三种口径。

### 2.2 summary status 与状态计数

- 至少一题真正计分：summary `status="ok"`；即使同时有 N/A/exclusion，也不改为 partial。
- 零题计分且至少一条 `pending`：`status="pending"`。
- 零题计分且无 pending：`status="n/a"`。
- 新增或统一 `score_status_counts`，键只使用 score-row 公共状态 `ok`、`n/a`、`pending`；
  零计数键是否省略必须五个 evaluator 一致，并由测试锁定。
- `sum(score_status_counts.values()) == total_questions`。benchmark exclusion 也必须落到它最终写出的
  score-row status，不能从总数消失。

现有 `retrieval_evidence_status_counts` / `retrieval_evidence_reason_code_counts` 继续只统计
**具有 scoreable gold 后 provider 给出的资格陈述**。benchmark-policy exclusion 不得混入或伪装成
provider evidence；M1 的这条边界不变。

### 2.3 runner 的显式 `None` 契约

共享 `EvaluationRunSummary.mean_score` 必须能表达 `float | None`。artifact evaluation runner：

- evaluator 显式返回 `None` 时，JSON 写 `null`；
- 既有 answer/judge evaluator 返回 float 的行为与 schema 不变；
- 非法字符串、`NaN`、正负无穷仍 fail-fast，不得因为放宽到 Optional 而漏过；
- resume/文件命名/score-row schema 不变。本卡不新增 metric 名，也不改 CLI 注册。

如现有 runner 还有 summary 重建或序列化入口，必须使用同一个可空规则；不要只修某一个写盘点。

## 3. 严禁改动的语义

以下均已由 M0/M1 或 benchmark contract 裁定，本卡不能借机重开：

- Recall、DCG/NDCG、group any-of、dedup、rank order 的公式；
- GoldEvidenceGroup parser、五家 qrel/gold 单位；
- LongMemEval canonical turn denominator=419 与 no-target exclusion；
- `RetrievalEvidence` 的 valid/n_a/pending 决策及 reason code；
- query depth=10、requested k、stable-ranking pending；
- LoCoMo/MemBench/BEAM/LongMemEval/HaluMem 的任务匹配；
- 逐题 score row 的 `score/status/reason_code` 现有真值；
- method、benchmark adapter、provider protocol、manifest/resume identity。

若修 summary 必须改变上述任一项，停工并给最小反例，不自行代裁。

## 4. 允许修改文件

```text
src/memory_benchmark/runners/evaluation.py
src/memory_benchmark/evaluators/retrieval_evidence.py
src/memory_benchmark/evaluators/locomo_recall.py
src/memory_benchmark/evaluators/longmemeval_recall.py
src/memory_benchmark/evaluators/longmemeval_retrieval_rank.py
src/memory_benchmark/evaluators/membench_recall.py
src/memory_benchmark/evaluators/beam_recall.py
tests/test_artifact_evaluation_runner.py
tests/test_locomo_retrieval_recall.py
tests/test_longmemeval_retrieval_recall.py
tests/test_longmemeval_retrieval_rank.py
tests/test_membench_retrieval_recall.py
tests/test_beam_recall.py
docs/workstreams/ws02.7-method-track/branches/retrieval-metrics/notes/
  retrieval-summary-nullability-implementation.md
```

不得改 method adapter、registry、provider protocol、entity/gold contract、benchmark adapter、
TOML、CLI、README、third_party、outputs 或其它测试。若 `EvaluationRunSummary` 实际定义不在允许
文件且无法在 `evaluation.py` 内诚实修复，停工报告；不要越界改实体。

## 5. 必测强反例

1. 两条全为 provider N/A：`total_questions=2`、`scored_question_count=0`、
   `mean_score is None`、`status=n/a`、status counts 合计 2。
2. 两条全为 pending：均值 `None`、status `pending`、总数 2。
3. 一条真实数值 `0.0` + 一条 N/A：总数 2、计分数 1、均值必须是 `0.0` 而不是 null。
4. 数值 1 与 0，再加 N/A/exclusion：均值只用两条 numeric 得 0.5，但 `total_questions` 包含全部
   score rows；provider evidence counts 不吸收 exclusion。
5. 全为 benchmark-policy exclusion：总数不为零、计分数零、均值 null、status n/a，provider
   evidence counts 保持空。
6. LongMemEval recall 的 metric-specific mean：零参与者为 null；有一条真实零分时为 0.0。
7. LongMemEval rank：零参与者时 mean null、既有 metrics 空结构；真实零分仍为 0.0。
8. 五个 evaluator 均写同一 `aggregation_contract_version`，status counts 总和恒等于总题数。
9. runner 收到 evaluator 显式 `mean_score=None` 后 JSON 是 null；既有 float 仍原样；字符串、
   NaN、正负无穷强反例继续拒绝。
10. 现有公式、gold group、419 分母、reason code 与 score-row 测试不删、不弱化。
11. 所有新增/修改 Python 函数、nested helper 与测试函数有准确中文 docstring。

测试 fixture 应直接构造最小 artifact/score rows，不读取真实 B11 run，不依赖 data、模型或 API。

## 6. 唯一定向自检

```bash
uv run pytest -q \
  tests/test_artifact_evaluation_runner.py \
  tests/test_locomo_retrieval_recall.py \
  tests/test_longmemeval_retrieval_recall.py \
  tests/test_longmemeval_retrieval_rank.py \
  tests/test_membench_retrieval_recall.py \
  tests/test_beam_recall.py \
  tests/test_documentation_standards.py
```

允许失败定位时跑单条；完成报告须给上述最终组合的真实尾行。不得调用真实 API、读取私有数据、
下载模型、改 outputs、跑全量 pytest 或 compileall。

## 7. 停工条件

以下任一出现即停工：

- 可空均值必须修改允许清单外的公开 entity/protocol/resume contract；
- 五个 evaluator 的 score-row status 集合不一致，无法在不改协议的情况下统一；
- 当前 source 证明 benchmark exclusion 根本没有 score row，因而 `total_questions` 定义不能按本卡
  落地；
- 定向失败暴露与本卡无关的真实缺陷且 15 分钟内不能消解；
- 需要删除/放宽现有强反例才能变绿。

停工 note 写清当前数据流、最小复现、受影响文件与可选裁决，不得用 `0.0` 占位绕过。

## 8. 提交纪律与报告

- `git diff --check`；add 前后各看 `git status --short`；只显式 add，禁 `-A`/`.`。
- 本地单 commit，不 amend、不 push；建议：
  `fix(metrics): preserve n-a retrieval summary semantics`
- note 必须记录真实 B11 反例、summary v2 字段表、旧→新 JSON 示例、测试尾行与偏差。
- Co-Authored-By 只写可核实真实模型；模型切换无法核实时不猜。
- 按 actor-handbook §4 回报：commit hash、最终测试尾行、实际改动文件、偏差/停工点、subagent
  分工和模型切换。到此停止，等待架构师 full diff 与强验收。
