# Retrieval summary N/A 可空契约实现记录（retrieval-summary-v2）

> 施工 actor：Claude Sonnet 5（Claude Code，本会话系统提示自报模型确认，未跨模型
> 切换）。基线：主树 `main` HEAD `ecea1ab`。worktree=
> `/Users/wz/Desktop/mb-actor-retrieval-summary-contract`，branch=
> `actor/retrieval-summary-contract`。按
> `cards/actor-prompt-retrieval-summary-nullability.md` 全卡施工，未使用 subagent。

## 1. 问题重述

LightMem × LongMemEval latest-v6 真实 B11 run 已证明逐题资格门正确：全 N/A 题
`score=null, status=n/a`。但 M1 实现的五个 evaluator 在**聚合层**仍把"全 N/A"
误写成 `mean_score=0.0, total_questions=0`——即用 `sum(scores)/len(scores) if
scores else 0.0` 计算均值、用 `len(scored_records)` 作 `total_questions`，把
"有题但零题可评分"混同于"零题"。本卡只收敛这一层聚合真值与 JSON 契约，不碰
逐题公式/gold group/419 分母/provider evidence 判定。

## 2. 做了什么

### 2.1 共享 helper（`src/memory_benchmark/evaluators/retrieval_evidence.py`）

新增两个纯函数 + 一个常量，供五个 evaluator 共用，避免五份漂移实现：

- `AGGREGATION_CONTRACT_VERSION = "retrieval-summary-v2"`：五个 evaluator 的
  summary 显式落盘同一个版本号。
- `nullable_mean(scores)`：零样本返回 `None`；非空样本正常求均值（含真实均值
  恰为 `0.0` 的情形，此时仍返回 `0.0` 而不是 `None`）。
- `score_status_counts(score_records)`：按每条 score record 的 `status` 字段
  （必须是 `ok`/`n/a`/`pending` 之一，否则 fail-fast）统计计数，零计数 key
  省略（与既有 `retrieval_evidence_status_counts` 的省略惯例一致）。`sum(...)`
  恒等于 `len(score_records)`，用于校验新 `total_questions` 语义。

### 2.2 五个 evaluator 的聚合层改动

`locomo_recall.py` / `longmemeval_recall.py` / `longmemeval_retrieval_rank.py`
/ `membench_recall.py` / `beam_recall.py` 的 `_scored_payload`（或等价内联块）
统一做三处改动：

1. 顶层 `total_questions` 从 `len(scored_records)` 改为 `len(score_records)`
   （本 evaluator 消费的**全部**记录，含 provider n_a/pending 与
   benchmark-policy 排除）；`scored_question_count`（已存在于 summary）继续
   是 `mean_score` 的唯一分母，未改名。
2. 顶层 `mean_score` 与 `summary["overall_mean_recall_at_requested_k"]`
   （rank 是 `summary["overall_metrics"]`，本就在零参与者时保持空 dict，
   未改动）改为 `nullable_mean(scores)`，不再在零样本时伪造 `0.0`。
3. `summary` 新增 `score_status_counts`（用 §2.1 helper 从**全部** score
   record 计算）与 `aggregation_contract_version="retrieval-summary-v2"`。

**未改动**：既有 `retrieval_evidence_status_counts` /
`retrieval_evidence_reason_code_counts` 语义不变——继续只统计"具有 scoreable
gold 后 provider 给出的资格陈述"，benchmark-policy 排除（LongMemEval
`_abs`/no-target、MemBench 空 target、BEAM 空 gold）依旧不计入这两个计数器，
但它们的最终 score-row `status` 会被新 `score_status_counts` 计入——这正是
卡 §2.2 要求的"exclusion 必须落到最终 score-row status，不能从总数消失，但不
能污染 provider evidence 计数"。逐题公式、gold group、419 分母、reason code
均未触碰。

### 2.3 runner 的显式 `None` 契约（`src/memory_benchmark/runners/evaluation.py`）

- `EvaluationRunSummary.mean_score` 类型注解从 `float` 放宽为 `float | None`。
- `_run_artifact_level_evaluation` 原先用 `_number_or_default(payload.get(
  "mean_score"), _mean_score(score_records), ...)`——`dict.get` 无法区分
  "key 缺失"与"值为 `None`"，导致 evaluator 想表达 `None` 时总是被回退成计算
  默认值。新增 `_resolve_artifact_mean_score(payload, score_records)`：
  - payload 完全不含 `mean_score` key → 按旧行为回算默认值（兼容
    `halumem_*`/`membench_source_accuracy`/`beam_rubric_judge` 等仍固定返回
    float、从未涉及本卡的既有 artifact evaluator，它们的行为逐一确认未变，
    见 §4 之外的 diagnostic）。
  - 显式 `"mean_score": None` → 忠实返回 `None`，JSON 写 `null`。
  - 显式数值 → 必须是非 bool 的有限 `int|float`；`NaN`/`Infinity`/`-Infinity`
    与字符串、布尔统一 `ConfigurationError`（这是本卡新收紧的一条口子：改前
    `_number_or_default` 对 `NaN`/`Infinity` 不做有限性检查，会被 `json.dump`
    的 `allow_nan=True` 默认值悄悄写成非标准 JSON token；改后 fail-fast）。
  - 原 `_number_or_default` 已无其它调用点，直接替换删除。

## 3. 新旧 JSON 对比（LoCoMo 全 N/A 场景，其余四个 evaluator 结构同构）

改前（M1 遗留，两条题都 `semantic_provenance=n_a`）：

```json
{
  "total_questions": 0,
  "mean_score": 0.0,
  "summary": {
    "status": "n/a",
    "scored_question_count": 0,
    "retrieval_evidence_status_counts": {"n_a": 2}
  }
}
```

改后（本卡，`tests/test_locomo_retrieval_recall.py::
test_all_na_run_reports_null_mean_not_zero`）：

```json
{
  "total_questions": 2,
  "mean_score": null,
  "summary": {
    "status": "n/a",
    "scored_question_count": 0,
    "retrieval_evidence_status_counts": {"n_a": 2},
    "score_status_counts": {"n/a": 2},
    "aggregation_contract_version": "retrieval-summary-v2"
  }
}
```

## 4. summary v2 字段表

| 字段 | 含义 | 分母/来源 |
| --- | --- | --- |
| `total_questions`（顶层） | evaluator 消费的全部 score record 数 | `len(score_records)` |
| `mean_score`（顶层） | `scored_question_count==0` 时为 `null`；否则真实均值 | `nullable_mean(scored scores)` |
| `summary.scored_question_count` | 数值计分记录数 | 不变，均值唯一分母 |
| `summary.score_status_counts` | `{ok, n/a, pending}` 计数，零计数省略 | 新增，`sum()==total_questions` |
| `summary.aggregation_contract_version` | `"retrieval-summary-v2"` | 新增，五个 evaluator 一致 |
| `summary.retrieval_evidence_status_counts` | provider 资格陈述计数（不含 benchmark 排除） | 不变 |

## 5. 定向自检（唯一一次，原样输出）

```
uv run pytest -q \
  tests/test_artifact_evaluation_runner.py \
  tests/test_locomo_retrieval_recall.py \
  tests/test_longmemeval_retrieval_recall.py \
  tests/test_longmemeval_retrieval_rank.py \
  tests/test_membench_retrieval_recall.py \
  tests/test_beam_recall.py \
  tests/test_documentation_standards.py
```

尾行：`149 passed in 3.89s`（复跑一次得 `149 passed in 4.14s`，波动属正常
计时抖动）。`git diff --check` 无输出（exit 0）。

## 6. §5 强反例覆盖清单（逐条对应到具体测试）

1. 两条全 provider N/A → total=2/scored=0/mean=null/status=n_a/counts 合计 2：
   `test_all_na_run_reports_null_mean_not_zero`（locomo）、
   `test_all_benchmark_policy_exclusion_reports_null_mean_but_nonzero_total`
   （longmemeval_recall，实际是两条 benchmark-policy no-target，同样验证
   "有题但零可评分"分支）、
   `test_all_empty_gold_exclusion_reports_null_mean_but_nonzero_total`
   （membench、beam 各一份）。
2. 两条全 pending → mean=null/status=pending/total=2：
   `test_all_pending_run_reports_null_mean_and_pending_status`（locomo）、
   `test_zero_participants_reports_null_mean_and_empty_metrics_structure`
   （longmemeval rank，额外锁定 `overall_metrics=={}`）。
3. 一条真实 `0.0` + 一条 N/A → 总数 2/计分 1/均值必须是 `0.0`：
   `test_one_zero_score_plus_one_na_reports_zero_not_null`（locomo）、
   `test_real_zero_ndcg_reports_zero_mean_not_null`（rank）。
4. 数值 1 与 0 + exclusion → 均值只用两条 numeric=0.5，total 含全部，provider
   evidence counts 不吸收 exclusion：
   `test_numeric_scores_plus_exclusion_mean_only_averages_numeric_rows`
   （longmemeval_recall）、
   `test_numeric_and_exclusion_mean_only_averages_numeric_rows`（membench、
   beam 各一份）。
5. 全 benchmark-policy exclusion → 总数不为零/计分零/均值 null/status n_a/
   provider evidence counts 保持空：同第 1 条各测试均已覆盖
   `retrieval_evidence_status_counts == {}`。
6. LongMemEval recall metric-specific mean（`overall_mean_recall_at_
   requested_k`）：零参与者为 null 已含在
   `test_all_benchmark_policy_exclusion_...`；真实零分为 0.0 由
   `test_numeric_scores_plus_exclusion_mean_only_averages_numeric_rows`
   间接锁定（该场景均值非零，另加断言 `overall_mean_recall_at_requested_k
   == pytest.approx(0.5)` 验证与顶层 `mean_score` 同步）。
7. LongMemEval rank：零参与者 mean null + `overall_metrics=={}`；真实零分仍
   `0.0`：`test_zero_participants_reports_null_mean_and_empty_metrics_structure`
   + `test_real_zero_ndcg_reports_zero_mean_not_null`。
8. 五个 evaluator 均写同一 `aggregation_contract_version`，status counts 总和
   恒等于总题数：每个文件至少一个测试断言
   `result["summary"]["aggregation_contract_version"] ==
   "retrieval-summary-v2"` 且 `sum(score_status_counts.values()) ==
   total_questions`。
9. runner 收到显式 `mean_score=None` → JSON null；既有 float 不变；字符串/
   布尔/NaN/正负无穷 fail-fast；payload 完全未声明 key 时按旧行为回算：
   `tests/test_artifact_evaluation_runner.py::
   test_artifact_evaluator_explicit_null_mean_score_writes_json_null` +
   `test_artifact_evaluator_explicit_float_mean_score_passes_through_unchanged`
   + `test_artifact_evaluator_missing_mean_score_key_falls_back_to_computed_default`
   + `test_artifact_evaluator_invalid_mean_score_fails_fast`（参数化覆盖
   字符串/`NaN`/`inf`/`-inf`/布尔五种非法值）。
10. 现有公式、gold group、419 分母、reason code 与 score-row 测试：未删除、
    未弱化任何既有断言，只新增/修正 `total_questions`/`mean_score` 相关断言
    （见 §7 偏差说明具体哪些既有断言被按新语义更新）。
11. 中文 docstring：定向自检包含 `tests/test_documentation_standards.py`，
    本次新增的 `nullable_mean`/`score_status_counts`/
    `_resolve_artifact_mean_score`/`_FixedPayloadArtifactEvaluator` 及其
    方法、全部新增测试函数均通过该门。

## 7. 既有测试断言的显式语义更新（不是新增反例，是修正旧错误断言）

M1 遗留测试断言的是旧的错误语义（`total_questions == scored_question_count`），
按卡 §2.1 新语义更新为"全部 record 数"，均标注了更新说明注释：

- `tests/test_locomo_retrieval_recall.py::
  test_semantic_provenance_na_produces_na_record_not_whole_run_na`：
  `total_questions` 0→1（1 条 n_a record），新增 `mean_score is None`/
  `score_status_counts` 断言。
- `tests/test_locomo_retrieval_recall.py::
  test_mixed_valid_na_pending_questions_in_one_run`：`total_questions` 1→3
  （3 条 record：valid+n_a+pending）。
- `tests/test_longmemeval_retrieval_recall.py::
  test_abstention_question_is_na_and_counted_separately`：`total_questions`
  1→2（含 abstention 那条 n/a record）。
- `tests/test_longmemeval_retrieval_rank.py::
  test_abstention_questions_excluded_with_count`：`total_questions` 1→2。

这四处更新均只改 `total_questions` 断言值本身，未删除或放宽任何其它既有
断言（gold group/公式/reason code/status 判定原样保留），新增的
`score_status_counts`/`aggregation_contract_version` 断言是补充，不替代。

## 8. 偏差与环境说明

1. **隔离 worktree 缺 gitignored `data/`**（沿用 M1 的已有先例）：
   `ln -s /Users/wz/Desktop/memoryBenchmark/data
   /Users/wz/Desktop/mb-actor-retrieval-summary-contract/data`，仅用于让
   `tests/test_artifact_evaluation_runner.py::
   test_longmemeval_s_smoke_registered_prediction_stays_offline_and_
   separates_private_labels`（本卡定向自检范围内、依赖真实 LongMemEval
   数据文件解析 dataset 的既有测试）可跑；该符号链接未被 `git add`
   （`git status --short` 显示为独立 `?? data`，未纳入本次 commit 的显式
   路径列表），也未修改其内容。
2. **诊断性复跑（非本卡定向自检、只为确认无越界回归）**：
   ```
   uv run pytest -q \
     tests/test_beam_registered_prediction.py \
     tests/test_evaluator_registry.py \
     tests/test_lightmem_adapter.py \
     tests/test_locomo_registered_prediction.py \
     tests/test_longmemeval_registered_prediction.py \
     tests/test_membench_registered_prediction.py
   ```
   尾行：`168 passed, 1 warning in 29.42s`（warning 是 LightMem 第三方
   Pydantic class-based config deprecation，与本卡无关）。这些文件均不在
   卡 §4 允许清单内，本次**未修改**，只读复跑确认 `total_questions`/
   `mean_score` 语义变化未影响它们（它们的 fixture 全部题都能计分，
   `len(score_records) == len(scored_records)`，两种语义下数值相同）。
3. 未使用 subagent，全程主 actor 会话直接施工。
4. 未调用真实 API、未读取私有数据（gold/evidence/judge label）、未改
   `outputs/`、未跑全量 pytest 或 compileall（只对本卡改动文件做了
   `python -m compileall`）。

## 9. 允许文件改动清单核对

全部改动落在卡 §4 允许列表内：
`src/memory_benchmark/runners/evaluation.py`；
`src/memory_benchmark/evaluators/{retrieval_evidence,locomo_recall,
longmemeval_recall,longmemeval_retrieval_rank,membench_recall,beam_recall}.py`；
`tests/test_{artifact_evaluation_runner,locomo_retrieval_recall,
longmemeval_retrieval_recall,longmemeval_retrieval_rank,
membench_retrieval_recall,beam_recall}.py`；本 note 文件本身。未触碰 method
adapter、registry、provider protocol、entity/gold contract、benchmark
adapter、TOML、CLI、README、third_party、outputs 或其它测试。
