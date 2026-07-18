# LightMem × LongMemEval B11 真实 smoke 命令包

> 状态：两组命令已由用户于 2026-07-18 执行，机器验货均 PASS；架构师完成 artifact 开箱后
> 发现产品 readout/embedding 观测与共享 retrieval summary 契约缺口。当前格子为
> `B11_ARTIFACT_REPAIR_PENDING`，不能升级为 `REAL_SMOKE_PASSED`，也不得沿用 v6 artifact
> 冒充修复后的证据。

## 1. 规模与 run identity

本轮只验证 cropped ingest → retrieve → answer → artifact/evaluate 接线，不作效果或成本结论：

- W1：注册默认 `1 conversation × 1 round × 1 question × 1 worker`。命令故意不传
  `--conversations/--rounds/--questions-per-conversation`，同时验证注册默认值没有漂移；
- W2：`2 conversations × 1 round × 每 conversation 1 question × 2 workers`。只有两个
  conversation 才能真实占用两个隔离 worker；只写 `--workers 2`、仍跑一个 conversation
  不能作为并行证据；
- W1 的 predict、五项离线 evaluate、judge 必须全部成功后，才开始 W2。两个 predict 不得在
  两个 shell 同时运行；
- CLI variant 的真实名字是 `s_cleaned`。LongMemEval 是 multi-variant benchmark，因此 predict
  接收的是 **base run id**，框架会自动追加 `-s-cleaned`；evaluate 必须使用追加后的 child
  run id。

本轮选定：

| 角色 | predict base run id | artifact / evaluate child run id |
|---|---|---|
| W1 | `lm-lme-v6-r1q1-w1` | `lm-lme-v6-r1q1-w1-s-cleaned` |
| W2 | `lm-lme-v6-r1q1-c2-w2` | `lm-lme-v6-r1q1-c2-w2-s-cleaned` |

smoke 不支持 resume。任一命令失败都保留目录与日志，停止并交回架构师；禁止删除失败目录后用
同一 run id 假装首次执行。

## 2. 环境与变量

先在一个新的 zsh 中整段执行：

```bash
cd /Users/wz/Desktop/memoryBenchmark
set -o pipefail

git status --short
git log -5 --oneline
git diff --quiet
git diff --cached --quiet
test -f .env
test -f data/longmemeval/longmemeval_s_cleaned.json
test -d models/all-MiniLM-L6-v2
test -d models/llmlingua-2-bert-base-multilingual-cased-meetingbank

BASE_W1=lm-lme-v6-r1q1-w1
BASE_W2=lm-lme-v6-r1q1-c2-w2
RUN_W1=${BASE_W1}-s-cleaned
RUN_W2=${BASE_W2}-s-cleaned
RUN_ROOT=outputs/runs/lightmem/longmemeval/s-cleaned/smoke/unified
RUN_DIR_W1="$RUN_ROOT/$RUN_W1"
RUN_DIR_W2="$RUN_ROOT/$RUN_W2"
TMP_LOG_ROOT="${TMPDIR:-/tmp}/memory-benchmark-lightmem-lme-b11"

test ! -e "$RUN_DIR_W1"
test ! -e "$RUN_DIR_W2"
mkdir -p "$TMP_LOG_ROOT"
```

`git status --short` 可以显示 OWNER 已有的 untracked 私有资产；真正的 clean 门是两条
`git diff --quiet`，它们阻止 tracked 或 staged 改动混入实验身份。不要打印或 `cat .env`。

## 3. W1：注册默认规模、单 worker

### 3.1 predict

```bash
uv run memory-benchmark predict smoke --root . --method lightmem --benchmark longmemeval --variant s_cleaned --config-track unified --run-id "$BASE_W1" --workers 1 --allow-api 2>&1 | tee "$TMP_LOG_ROOT/$RUN_W1.predict.log"
PREDICT_STATUS=$?
mkdir -p "$RUN_DIR_W1/logs"
mv "$TMP_LOG_ROOT/$RUN_W1.predict.log" "$RUN_DIR_W1/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0
```

这里故意不传三个 smoke 裁剪参数。当前注册默认应在 manifest/workload 中解析为
`1 conversation × 1 round × 1 question`；机器验货会复核最终问题数。

### 3.2 五项无 API evaluator

```bash
uv run memory-benchmark evaluate --root . --run-id "$RUN_W1" --metric f1 --metric normalized-em --metric substring-em --metric longmemeval-recall --metric longmemeval-retrieval-rank --workers 1 2>&1 | tee "$RUN_DIR_W1/logs/terminal.evaluate-offline.log"
OFFLINE_STATUS=$?
test "$OFFLINE_STATUS" -eq 0
```

前三项应落正常数值；后两项必须成功执行资格门，但 LightMem 的 pair source 不能证明具体 child
turn，因此应落 `score=null/status=n/a/reason_code=pair_source_id_not_turn_exact`，不能伪造
Recall/NDCG 数值，也不能把 N/A 当成命令失败。

### 3.3 付费官方 judge

```bash
uv run memory-benchmark evaluate --root . --run-id "$RUN_W1" --metric longmemeval-judge --judge-profile compact --workers 1 --allow-api 2>&1 | tee "$RUN_DIR_W1/logs/terminal.evaluate-judge.log"
JUDGE_STATUS=$?
test "$JUDGE_STATUS" -eq 0
```

judge 与离线指标分开执行，避免 API 失败掩盖已经成功写盘的免费指标。

## 4. W2：两 conversation、真实双 worker

只有 §3 三段均 exit 0 后，继续在**同一 shell**执行。

### 4.1 predict

```bash
uv run memory-benchmark predict smoke --root . --method lightmem --benchmark longmemeval --variant s_cleaned --config-track unified --run-id "$BASE_W2" --conversations 2 --workers 2 --allow-api 2>&1 | tee "$TMP_LOG_ROOT/$RUN_W2.predict.log"
PREDICT_STATUS=$?
mkdir -p "$RUN_DIR_W2/logs"
mv "$TMP_LOG_ROOT/$RUN_W2.predict.log" "$RUN_DIR_W2/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0
```

只覆盖 conversation 数与 worker 数；round/question 仍沿用注册默认 1。双 worker 的意义是验证
conversation state、Qdrant collection 与写盘路径物理隔离，不是加速一个 conversation。

### 4.2 五项无 API evaluator

```bash
uv run memory-benchmark evaluate --root . --run-id "$RUN_W2" --metric f1 --metric normalized-em --metric substring-em --metric longmemeval-recall --metric longmemeval-retrieval-rank --workers 2 2>&1 | tee "$RUN_DIR_W2/logs/terminal.evaluate-offline.log"
OFFLINE_STATUS=$?
test "$OFFLINE_STATUS" -eq 0
```

这里的 `--workers 2` 不是性能需要；两题的程序指标本来就很快。它只顺带覆盖 answer-level
artifact evaluator 的并发入口；两个 retrieval artifact evaluator 会按自身实现串行聚合。

### 4.3 付费官方 judge

```bash
uv run memory-benchmark evaluate --root . --run-id "$RUN_W2" --metric longmemeval-judge --judge-profile compact --workers 2 --allow-api 2>&1 | tee "$RUN_DIR_W2/logs/terminal.evaluate-judge.log"
JUDGE_STATUS=$?
test "$JUDGE_STATUS" -eq 0
```

## 5. 机器验货（零 API）

六段运行命令全部成功后，在同一 shell 执行：

```bash
uv run python - <<'PY'
from __future__ import annotations

import json
from pathlib import Path


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


root = Path("outputs/runs/lightmem/longmemeval/s-cleaned/smoke/unified")
cases = (
    ("lm-lme-v6-r1q1-w1-s-cleaned", 1, 1),
    ("lm-lme-v6-r1q1-c2-w2-s-cleaned", 2, 2),
)
summary_names = (
    "summary.f1.json",
    "summary.normalized_em.json",
    "summary.substring_em.json",
    "summary.longmemeval_recall.json",
    "summary.longmemeval_retrieval_rank.json",
    "summary.longmemeval_judge_accuracy.json",
)

for run_id, expected_questions, expected_workers in cases:
    run_dir = root / run_id
    manifest = read_json(run_dir / "manifest.json")
    config = manifest["method"]["config"]
    reader = manifest["method"]["answer_reader"]
    assert manifest["run_id"] == run_id
    assert manifest["benchmark_name"] == "longmemeval"
    assert manifest["benchmark_variant"] == "s_cleaned"
    assert manifest["run_scope"] == "smoke"
    assert manifest["policy"]["max_workers"] == expected_workers
    assert manifest["method"]["retrieval_evidence_contract_version"] == "v1"
    assert manifest["benchmark_policy"]["gold_evidence_contract_version"] == "v1"
    assert config["adapter_version"] == "conversation-qa-v6"
    assert config["messages_use"] == "hybrid"
    assert config["lifecycle_profile"] == "online_soft"
    assert config["missing_timestamp_policy"] == "preserve_none"
    assert config["retrieve_limit"] == 60
    assert config["embedding_dimensions"] == 384
    assert reader["answer_parameters"] == {
        "message_role": "user",
        "temperature": 0.0,
        "max_tokens": 500,
        "top_p": None,
        "timeout_seconds": 60.0,
        "max_retries": 8,
    }

    prediction_rows = read_jsonl(run_dir / "artifacts/method_predictions.jsonl")
    answer_rows = read_jsonl(run_dir / "artifacts/answer_prompts.prediction.jsonl")
    assert len(prediction_rows) == expected_questions
    assert len(answer_rows) == expected_questions
    assert len({row["conversation_id"] for row in prediction_rows}) == expected_questions
    for row in answer_rows:
        assert row["retrieval_query_top_k"] == 10
        assert isinstance(row["retrieved_items"], list)
        assert isinstance(row["formatted_memory"], str) and row["formatted_memory"].strip()
        assert "Current Date:" in row["answer_prompt"]
        evidence = row["retrieval_evidence"]
        assert evidence["semantic_provenance"]["status"] == "n_a"
        assert evidence["semantic_provenance"]["reason_code"] == (
            "pair_source_id_not_turn_exact"
        )
        assert evidence["provenance_granularity"] == "none"
        assert evidence["stable_ranking"]["status"] == "pending"

    prediction_summary = read_json(run_dir / "summaries/summary.json")
    progress = read_json(run_dir / "checkpoints/progress.json")
    assert prediction_summary["total_conversations"] == expected_questions
    assert prediction_summary["completed_conversations"] == expected_questions
    assert prediction_summary["total_questions"] == expected_questions
    assert prediction_summary["completed_questions"] == expected_questions
    assert progress["stage"] == "Completed"
    assert progress["conversation_completed"] == expected_questions
    assert progress["question_completed"] == expected_questions

    for name in summary_names:
        assert (run_dir / "summaries" / name).is_file(), (run_id, name)
    for name in ("f1", "normalized_em", "substring_em", "longmemeval_judge_accuracy"):
        summary = read_json(run_dir / "summaries" / f"summary.{name}.json")
        assert summary["total_questions"] == expected_questions, (run_id, name)

    for name in ("longmemeval_recall", "longmemeval_retrieval_rank"):
        summary = read_json(run_dir / "summaries" / f"summary.{name}.json")
        scores = read_jsonl(run_dir / "artifacts" / f"answer_scores.{name}.jsonl")
        assert summary["status"] == "n/a"
        assert summary["scored_question_count"] == 0
        assert summary["retrieval_evidence_status_counts"] == {
            "n_a": expected_questions
        }
        assert summary["retrieval_evidence_reason_code_counts"] == {
            "pair_source_id_not_turn_exact": expected_questions
        }
        assert len(scores) == expected_questions
        assert all(row["score"] is None and row["status"] == "n/a" for row in scores)
        assert all(
            row["reason_code"] == "pair_source_id_not_turn_exact" for row in scores
        )

    observations = read_jsonl(
        run_dir / "artifacts/efficiency_observations.prediction.jsonl"
    )
    observation_types = {row["observation_type"] for row in observations}
    assert {
        "question_efficiency",
        "conversation_efficiency",
        "llm_call",
    } <= observation_types
    llm_calls = [row for row in observations if row["observation_type"] == "llm_call"]
    assert llm_calls
    assert all(row["token_measurement_source"] == "api_usage" for row in llm_calls)
    assert (run_dir / "artifacts/model_inventory.prediction.json").is_file()
    assert (
        run_dir / "artifacts/model_inventory.longmemeval_judge_accuracy.json"
    ).is_file()
    assert (
        run_dir / "artifacts/efficiency_observations.longmemeval_judge_accuracy.jsonl"
    ).stat().st_size > 0
    for name in (
        "efficiency_overall.prediction.json",
        "efficiency_by_conversation.prediction.json",
        "efficiency_by_question.prediction.json",
    ):
        assert (run_dir / "summaries" / name).is_file(), (run_id, name)

    state_root = run_dir / "method_state"
    worker_dirs = sorted(state_root.glob("worker_*"))
    if expected_workers == 1:
        assert worker_dirs == []
        qdrant_roots = (state_root / "qdrant",)
    else:
        assert len(worker_dirs) == expected_workers
        qdrant_roots = tuple(worker / "qdrant" for worker in worker_dirs)
    assert all(path.is_dir() and any(path.iterdir()) for path in qdrant_roots)

    for terminal_name in (
        "terminal.predict.log",
        "terminal.evaluate-offline.log",
        "terminal.evaluate-judge.log",
    ):
        assert (run_dir / "logs" / terminal_name).is_file()
    print(
        f"PASS {run_id}: questions={expected_questions}, "
        f"workers={expected_workers}, retrieval_metrics=N/A"
    )
PY
```

脚本检查 run identity、默认/覆盖规模、prediction/prompt 数量、逐题 evidence、LongMemEval 的诚实
N/A、六项 evaluator、API usage token、latency、judge 观测与 worker state 隔离。它不要求 answer
答对、retrieved items 非空或 lexical/judge 得高分；这些都不是 B11 接线门。

## 6. 执行后回收

用户执行后把六段 terminal 尾行与机器验货输出交回架构师。架构师仍需亲读 run 内 manifest、
checkpoint、answer prompt、formatted memory、retrieval evidence、效率 artifact 与两个 worker 的
Qdrant/state，不能用“命令 exit 0”代替开箱验货。通过后同步：

1. 本 command pack 状态；
2. `lightmem-five-benchmark-safety-dossier.md` 的 LongMemEval 格；
3. LightMem 子线与父 workstream README；
4. 对应 frozen/验收 note 与 commit/push 状态。

## 7. 2026-07-18 实际执行与架构师开箱判词

实际 run：

- `lm-lme-v6-r1q1-w1-s-cleaned`：1 question / 1 worker；
- `lm-lme-v6-r1q1-c2-w2-s-cleaned`：2 questions / 2 workers。

机器脚本原始末行均为 PASS。manifest/workload/checkpoint、prediction/prompt/score 行数、compact
judge、API usage、隐私边界与单/双 worker Qdrant/state 隔离成立；LongMemEval retrieval 两项逐题
均诚实写 `score=null,status=n/a,reason_code=pair_source_id_not_turn_exact`。这些证明主接线与资格门
没有失败。

但开箱同时抓到四项不能被“零报错”掩盖的事实：

1. W2 命中记忆的 Qdrant payload 保存完整 `2023-05-20T03:29:00.000`，公共
   `formatted_memory`/unified `History Chats` 却只剩 `20 May 2023, Sat`。这是把 LoCoMo author
   pretty-date formatter 错用于产品 readout 的降精度；时间题可能因此改答案。
2. 两个 run 的 model inventory 都声明 `lightmem-embedding`，但 prediction observation 中
   `embedding_call=0`、overall `embedding_tokens={}`；B7 不能据 inventory 自证通过。
3. 同一道 LongMemEval 题的 v1 evidence 写 `provenance_granularity=none`，legacy retrieval
   metadata 却写 `turn`；evaluator 读 v1 所以没有误计分，但公开 artifact 自相矛盾。
4. Recall/rank score rows 的 N/A 真值正确，summary 却写 `total_questions=0,mean_score=0.0`；这把
   “有题但零题可评分”误表示成“零题且平均零分”。

修复拆为两张零 API、无文件交叉的卡：

- [LightMem 产品 readout 与 embedding 观测](../cards/actor-prompt-lightmem-readout-observability-repair.md)：
  adapter v7、产品格式保真、embedding observation、逐题 metadata 单事实源；
- [Retrieval summary v2](../../../retrieval-metrics/cards/actor-prompt-retrieval-summary-nullability.md)：
  total/scored/null/status-count 聚合与 runner JSON null。

两卡强验收并线性合入前，不再调用真实 API。合入后 v6 不能 resume；由架构师重新给出最小 v7
验证命令，并另行裁定哪些旧 artifact 可做零 API re-evaluate。

## 8. 2026-07-18 零 API 修复强验收

- retrieval summary v2：actor `8a81723` → 主线 `68bb7f9`；真实 v6 W1/W2 已零 API 重评，
  Recall/rank 均保持逐题 N/A，summary 分别为 `total_questions=1/2`、`mean_score=null`、
  W1/W2 的 `score_status_counts` 分别为 `{"n/a":1}` / `{"n/a":2}`，contract 均为
  `retrieval-summary-v2`。
- LightMem v7 主体：actor `8f6f883` 首轮被架构师抓到 zero-hit 双源与 observer 旁路异常会
  反向打断算法；Codex R1 `1a07938` 线性关闭，主线为 `d11d749` + `2f21291`。
- 架构师门：LightMem 原卡 204 项、两卡合流 325 项、主树全量
  `1557 passed, 3 deselected, 2 warnings, 29 subtests passed`，compileall exit 0。

因此四项代码缺口均已关闭，但状态仍是 `B11_ARTIFACT_REPAIR_PENDING`：v6 artifact 只能证明
旧接线与 summary 可重评，不能证明 v7 的完整 ISO readout、zero-hit 双源一致或真实 embedding
observation。下一步必须由用户重新批准预算/规模/run_id 后执行最小 v7 W1/W2；本节不把零 API
验收冒充真实 B11。
