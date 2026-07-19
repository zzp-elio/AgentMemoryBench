# LightMem v7 readout / observability 受影响格 B11 复验命令包

> 状态：用户已于 2026-07-19 批准本命令包的预算、规模与 run id；待用户执行。
> 本轮只重验 `conversation-qa-v7` 改动实际影响的 LongMemEval 与 LoCoMo，不能据此宣布
> LightMem 五格冻结。MemBench、BEAM、HaluMem 仍按各自异常覆盖门逐格推进。

## 1. 为什么必须新建四个 run

v7 没有改变 LightMem 的抽取、分段、向量检索或 online-soft lifecycle，但改变了三个公开
artifact 契约：

1. product `formatted_memory` 保留完整 ISO timestamp，不再误用 LoCoMo author pretty-date；
2. 真实 `text_embedder.embed()` 在 memory-build 与 retrieval 阶段落 embedding observation；
3. legacy metadata 的 provenance granularity 与逐题 `RetrievalEvidence` 使用同一裁决。

因此 v6 只能保留为历史证据，不能 resume 或冒充修复后证据。四个新 run 为：

| benchmark | 角色 | predict run id | artifact / evaluate run id | 规模 |
|---|---|---|---|---|
| LongMemEval S-cleaned | W1 | `lm-lme-v7-r1q1-w1` | `lm-lme-v7-r1q1-w1-s-cleaned` | 注册默认 1 conversation × 1 round × 1 question × 1 worker |
| LongMemEval S-cleaned | W2 | `lm-lme-v7-r1q1-c2-w2` | `lm-lme-v7-r1q1-c2-w2-s-cleaned` | 2 conversations × 1 round × 1 question × 2 workers |
| LoCoMo | W1 | `lm-locomo-v7-r3q1-w1` | 同左 | 1 conversation × 3 rounds × 1 question × 1 worker |
| LoCoMo | W2 | `lm-locomo-v7-r3q1-c2-w2` | 同左 | 2 conversations × 3 rounds × 1 question × 2 workers |

LoCoMo 保留 3 rounds，是为了让首个 caption turn `conv-26/D1:5` 真正进入 backend。四个
predict 必须按本文顺序串行；W2 命令内部的两个 worker 才是受控并行，不得另开四个 shell
同时运行。smoke 不支持 resume；失败后保留目录和日志，停止并交回架构师。

## 2. 一次性环境门

在一个新的 zsh 中整段执行；后续各节继续使用同一个 shell：

```bash
cd /Users/wz/Desktop/memoryBenchmark
set -o pipefail

git status --short
git log -5 --oneline
git diff --quiet
git diff --cached --quiet
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -f .env
test -f data/longmemeval/longmemeval_s_cleaned.json
test -f data/locomo/locomo10.json
test -d models/all-MiniLM-L6-v2
test -d models/llmlingua-2-bert-base-multilingual-cased-meetingbank

LME_BASE_W1=lm-lme-v7-r1q1-w1
LME_BASE_W2=lm-lme-v7-r1q1-c2-w2
LME_RUN_W1=${LME_BASE_W1}-s-cleaned
LME_RUN_W2=${LME_BASE_W2}-s-cleaned
LME_ROOT=outputs/runs/lightmem/longmemeval/s-cleaned/smoke/unified

LOCO_RUN_W1=lm-locomo-v7-r3q1-w1
LOCO_RUN_W2=lm-locomo-v7-r3q1-c2-w2
LOCO_ROOT=outputs/runs/lightmem/locomo/smoke/unified

TMP_LOG_ROOT="${TMPDIR:-/tmp}/memory-benchmark-lightmem-v7-b11"
test ! -e "$LME_ROOT/$LME_RUN_W1"
test ! -e "$LME_ROOT/$LME_RUN_W2"
test ! -e "$LOCO_ROOT/$LOCO_RUN_W1"
test ! -e "$LOCO_ROOT/$LOCO_RUN_W2"
mkdir -p "$TMP_LOG_ROOT"
```

`git status --short` 可以显示 OWNER 已有的 untracked 私有资产；真正的 source clean 门是两条
`git diff --quiet`。不要打印或 `cat .env`。

## 3. LongMemEval W1：注册默认规模、单 worker

### 3.1 predict

```bash
uv run memory-benchmark predict smoke --root . --method lightmem --benchmark longmemeval --variant s_cleaned --config-track unified --run-id "$LME_BASE_W1" --workers 1 --allow-api 2>&1 | tee "$TMP_LOG_ROOT/$LME_RUN_W1.predict.log"
PREDICT_STATUS=$?
mkdir -p "$LME_ROOT/$LME_RUN_W1/logs"
mv "$TMP_LOG_ROOT/$LME_RUN_W1.predict.log" "$LME_ROOT/$LME_RUN_W1/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0
```

这里故意不传 conversations/rounds/questions 三个裁剪参数，用来验证注册默认仍为 1/1/1。

### 3.2 五项零 API evaluator

```bash
uv run memory-benchmark evaluate --root . --run-id "$LME_RUN_W1" --metric f1 --metric normalized-em --metric substring-em --metric longmemeval-recall --metric longmemeval-retrieval-rank --workers 1 2>&1 | tee "$LME_ROOT/$LME_RUN_W1/logs/terminal.evaluate-offline.log"
OFFLINE_STATUS=$?
test "$OFFLINE_STATUS" -eq 0
```

前三项应产数值；后两项必须产 `score=null/status=n/a`，因为 LightMem pair candidate lineage
不能证明 fact 来自 pair 内哪个 child turn。

### 3.3 付费 judge

```bash
uv run memory-benchmark evaluate --root . --run-id "$LME_RUN_W1" --metric longmemeval-judge --judge-profile compact --workers 1 --allow-api 2>&1 | tee "$LME_ROOT/$LME_RUN_W1/logs/terminal.evaluate-judge.log"
JUDGE_STATUS=$?
test "$JUDGE_STATUS" -eq 0
```

## 4. LongMemEval W2：两 conversation、双 worker

只有 §3 三段都 exit 0 后继续：

```bash
uv run memory-benchmark predict smoke --root . --method lightmem --benchmark longmemeval --variant s_cleaned --config-track unified --run-id "$LME_BASE_W2" --conversations 2 --workers 2 --allow-api 2>&1 | tee "$TMP_LOG_ROOT/$LME_RUN_W2.predict.log"
PREDICT_STATUS=$?
mkdir -p "$LME_ROOT/$LME_RUN_W2/logs"
mv "$TMP_LOG_ROOT/$LME_RUN_W2.predict.log" "$LME_ROOT/$LME_RUN_W2/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0

uv run memory-benchmark evaluate --root . --run-id "$LME_RUN_W2" --metric f1 --metric normalized-em --metric substring-em --metric longmemeval-recall --metric longmemeval-retrieval-rank --workers 2 2>&1 | tee "$LME_ROOT/$LME_RUN_W2/logs/terminal.evaluate-offline.log"
OFFLINE_STATUS=$?
test "$OFFLINE_STATUS" -eq 0

uv run memory-benchmark evaluate --root . --run-id "$LME_RUN_W2" --metric longmemeval-judge --judge-profile compact --workers 2 --allow-api 2>&1 | tee "$LME_ROOT/$LME_RUN_W2/logs/terminal.evaluate-judge.log"
JUDGE_STATUS=$?
test "$JUDGE_STATUS" -eq 0
```

W2 的两个 conversation 是并行隔离证据；离线指标本身很快，`--workers 2` 不是为了省指标计算
时间。

## 5. LoCoMo W1：3 rounds、单 worker

只有 LongMemEval W1/W2 全部成功后继续：

```bash
uv run memory-benchmark predict smoke --root . --method lightmem --benchmark locomo --config-track unified --run-id "$LOCO_RUN_W1" --rounds 3 --conversations 1 --questions-per-conversation 1 --workers 1 --allow-api 2>&1 | tee "$TMP_LOG_ROOT/$LOCO_RUN_W1.predict.log"
PREDICT_STATUS=$?
mkdir -p "$LOCO_ROOT/$LOCO_RUN_W1/logs"
mv "$TMP_LOG_ROOT/$LOCO_RUN_W1.predict.log" "$LOCO_ROOT/$LOCO_RUN_W1/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0

uv run memory-benchmark evaluate --root . --run-id "$LOCO_RUN_W1" --metric locomo-f1 --metric f1 --metric normalized-em --metric substring-em --metric locomo-recall --workers 1 2>&1 | tee "$LOCO_ROOT/$LOCO_RUN_W1/logs/terminal.evaluate-offline.log"
OFFLINE_STATUS=$?
test "$OFFLINE_STATUS" -eq 0

uv run memory-benchmark evaluate --root . --run-id "$LOCO_RUN_W1" --metric locomo-judge --judge-profile compact --workers 1 --allow-api 2>&1 | tee "$LOCO_ROOT/$LOCO_RUN_W1/logs/terminal.evaluate-judge.log"
JUDGE_STATUS=$?
test "$JUDGE_STATUS" -eq 0
```

## 6. LoCoMo W2：3 rounds、双 worker

只有 §5 三段都成功后继续：

```bash
uv run memory-benchmark predict smoke --root . --method lightmem --benchmark locomo --config-track unified --run-id "$LOCO_RUN_W2" --rounds 3 --conversations 2 --questions-per-conversation 1 --workers 2 --allow-api 2>&1 | tee "$TMP_LOG_ROOT/$LOCO_RUN_W2.predict.log"
PREDICT_STATUS=$?
mkdir -p "$LOCO_ROOT/$LOCO_RUN_W2/logs"
mv "$TMP_LOG_ROOT/$LOCO_RUN_W2.predict.log" "$LOCO_ROOT/$LOCO_RUN_W2/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0

uv run memory-benchmark evaluate --root . --run-id "$LOCO_RUN_W2" --metric locomo-f1 --metric f1 --metric normalized-em --metric substring-em --metric locomo-recall --workers 2 2>&1 | tee "$LOCO_ROOT/$LOCO_RUN_W2/logs/terminal.evaluate-offline.log"
OFFLINE_STATUS=$?
test "$OFFLINE_STATUS" -eq 0

uv run memory-benchmark evaluate --root . --run-id "$LOCO_RUN_W2" --metric locomo-judge --judge-profile compact --workers 2 --allow-api 2>&1 | tee "$LOCO_ROOT/$LOCO_RUN_W2/logs/terminal.evaluate-judge.log"
JUDGE_STATUS=$?
test "$JUDGE_STATUS" -eq 0
```

## 7. 四个 run 的机器验货（零 API）

十二段运行命令全部成功后执行。脚本不要求答案正确或分数高；它验证的是 v7 身份、readout、
逐题 evidence、summary v2、embedding 观测、caption lineage 与 worker state。

```bash
uv run python - <<'PY'
from __future__ import annotations

import json
import re
from pathlib import Path

from qdrant_client import QdrantClient


ISO_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\s")
SENTINEL = "(No relevant memories found)"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def qdrant_payloads(run_dir: Path, expected_workers: int) -> list[dict]:
    state_root = run_dir / "method_state"
    worker_dirs = sorted(state_root.glob("worker_*"))
    if expected_workers == 1:
        assert worker_dirs == [], run_dir
        qdrant_roots = (state_root / "qdrant",)
    else:
        assert len(worker_dirs) == expected_workers, (run_dir, worker_dirs)
        qdrant_roots = tuple(worker / "qdrant" for worker in worker_dirs)
    assert all(root.is_dir() and any(root.iterdir()) for root in qdrant_roots)

    payloads: list[dict] = []
    for qdrant_root in qdrant_roots:
        for database in sorted(path for path in qdrant_root.iterdir() if path.is_dir()):
            if database.name.endswith("_summary"):
                continue
            if not (database / "collection").is_dir():
                continue
            client = QdrantClient(path=str(database))
            try:
                for collection in client.get_collections().collections:
                    points, next_offset = client.scroll(
                        collection_name=collection.name,
                        limit=1000,
                        with_payload=True,
                        with_vectors=False,
                    )
                    assert next_offset is None, (database, collection.name)
                    payloads.extend(point.payload or {} for point in points)
            finally:
                client.close()
    return payloads


cases = (
    {
        "root": Path("outputs/runs/lightmem/longmemeval/s-cleaned/smoke/unified"),
        "run_id": "lm-lme-v7-r1q1-w1-s-cleaned",
        "benchmark": "longmemeval",
        "variant": "s_cleaned",
        "questions": 1,
        "workers": 1,
    },
    {
        "root": Path("outputs/runs/lightmem/longmemeval/s-cleaned/smoke/unified"),
        "run_id": "lm-lme-v7-r1q1-c2-w2-s-cleaned",
        "benchmark": "longmemeval",
        "variant": "s_cleaned",
        "questions": 2,
        "workers": 2,
    },
    {
        "root": Path("outputs/runs/lightmem/locomo/smoke/unified"),
        "run_id": "lm-locomo-v7-r3q1-w1",
        "benchmark": "locomo",
        "variant": "locomo10",
        "questions": 1,
        "workers": 1,
    },
    {
        "root": Path("outputs/runs/lightmem/locomo/smoke/unified"),
        "run_id": "lm-locomo-v7-r3q1-c2-w2",
        "benchmark": "locomo",
        "variant": "locomo10",
        "questions": 2,
        "workers": 2,
    },
)

lme_iso_hit_count = 0
locomo_iso_hit_count = 0

for case in cases:
    run_id = case["run_id"]
    benchmark = case["benchmark"]
    expected_questions = case["questions"]
    expected_workers = case["workers"]
    run_dir = case["root"] / run_id

    manifest = read_json(run_dir / "manifest.json")
    config = manifest["method"]["config"]
    reader = manifest["method"]["answer_reader"]
    assert manifest["run_id"] == run_id
    assert manifest["benchmark_name"] == benchmark
    assert manifest["benchmark_variant"] == case["variant"]
    assert manifest["run_scope"] == "smoke"
    assert manifest["policy"]["max_workers"] == expected_workers
    assert manifest["method"]["prompt_track"] == "unified"
    assert manifest["method"]["protocol_version"] == "v3"
    assert manifest["method"]["retrieval_evidence_contract_version"] == "v1"
    assert manifest["benchmark_policy"]["gold_evidence_contract_version"] == "v1"
    assert config["adapter_version"] == "conversation-qa-v7"
    assert config["messages_use"] == "hybrid"
    assert config["lifecycle_profile"] == "online_soft"
    assert config["missing_timestamp_policy"] == "preserve_none"
    assert config["retrieve_limit"] == 60
    assert config["embedding_dimensions"] == 384
    assert reader["answer_parameters"]["temperature"] == 0.0
    assert reader["answer_parameters"]["max_tokens"] == (
        500 if benchmark == "longmemeval" else 32
    )

    predictions = read_jsonl(run_dir / "artifacts/method_predictions.jsonl")
    answers = read_jsonl(run_dir / "artifacts/answer_prompts.prediction.jsonl")
    assert len(predictions) == expected_questions
    assert len(answers) == expected_questions
    conversation_ids = {row["conversation_id"] for row in predictions}
    question_ids = {row["question_id"] for row in answers}
    assert len(conversation_ids) == expected_questions
    assert len(question_ids) == expected_questions

    for row in answers:
        assert row["retrieval_query_top_k"] == 10
        assert isinstance(row["retrieved_items"], list)
        assert row["metadata"]["answer_context"] == row["formatted_memory"]
        assert row["metadata"]["provenance_granularity"] == row[
            "retrieval_evidence"
        ]["provenance_granularity"]
        assert row["formatted_memory"] in row["answer_prompt"]
        assert "[Memory recorded on:" not in row["formatted_memory"]

        items = row["retrieved_items"]
        if items:
            assert row["formatted_memory"] == "\n".join(item["content"] for item in items)
            iso_items = [item for item in items if ISO_PREFIX.match(item["content"])]
            if benchmark == "longmemeval":
                lme_iso_hit_count += len(iso_items)
            else:
                locomo_iso_hit_count += len(iso_items)
        else:
            assert row["formatted_memory"] == SENTINEL

        evidence = row["retrieval_evidence"]
        if benchmark == "longmemeval":
            assert evidence["semantic_provenance"]["status"] == "n_a"
            assert evidence["semantic_provenance"]["reason_code"] == (
                "pair_source_id_not_turn_exact"
            )
            assert evidence["provenance_granularity"] == "none"
        else:
            assert evidence["semantic_provenance"]["status"] == "valid"
            assert evidence["provenance_granularity"] == "turn"
        assert evidence["stable_ranking"]["status"] == "pending"

    progress = read_json(run_dir / "checkpoints/progress.json")
    prediction_summary = read_json(run_dir / "summaries/summary.json")
    assert progress["stage"] == "Completed"
    assert progress["conversation_completed"] == expected_questions
    assert progress["question_completed"] == expected_questions
    assert prediction_summary["completed_conversations"] == expected_questions
    assert prediction_summary["completed_questions"] == expected_questions

    if benchmark == "longmemeval":
        scalar_metrics = (
            "f1",
            "normalized_em",
            "substring_em",
            "longmemeval_judge_accuracy",
        )
        retrieval_metrics = ("longmemeval_recall", "longmemeval_retrieval_rank")
        for metric in retrieval_metrics:
            summary = read_json(run_dir / "summaries" / f"summary.{metric}.json")
            rows = read_jsonl(run_dir / "artifacts" / f"answer_scores.{metric}.jsonl")
            assert summary["total_questions"] == expected_questions
            assert summary["scored_question_count"] == 0
            assert summary["mean_score"] is None
            assert summary["status"] == "n/a"
            assert summary["score_status_counts"] == {"n/a": expected_questions}
            assert summary["aggregation_contract_version"] == "retrieval-summary-v2"
            assert len(rows) == expected_questions
            assert all(row["score"] is None and row["status"] == "n/a" for row in rows)
            assert all(
                row["reason_code"] == "pair_source_id_not_turn_exact" for row in rows
            )
    else:
        scalar_metrics = (
            "locomo_f1",
            "f1",
            "normalized_em",
            "substring_em",
            "locomo_judge_accuracy",
        )
        recall = read_json(run_dir / "summaries/summary.locomo_recall.json")
        assert recall["total_questions"] == expected_questions
        assert recall["scored_question_count"] == expected_questions
        assert recall["status"] == "ok"
        assert isinstance(recall["mean_score"], (int, float))
        assert recall["score_status_counts"] == {"ok": expected_questions}
        assert recall["aggregation_contract_version"] == "retrieval-summary-v2"

    for metric in scalar_metrics:
        summary = read_json(run_dir / "summaries" / f"summary.{metric}.json")
        assert summary["total_questions"] == expected_questions, (run_id, metric)

    inventory = read_json(run_dir / "artifacts/model_inventory.prediction.json")
    model_ids = {model["model_id"] for model in inventory["models"]}
    assert model_ids == {
        "gpt-4o-mini",
        "lightmem-embedding",
        "lightmem-memory-llm",
    }
    assert "lightmem-answer-llm" not in model_ids

    observations = read_jsonl(
        run_dir / "artifacts/efficiency_observations.prediction.jsonl"
    )
    embeds = [row for row in observations if row["observation_type"] == "embedding_call"]
    build_embeds = [row for row in embeds if row["stage"] == "memory_build"]
    retrieval_embeds = [row for row in embeds if row["stage"] == "retrieval"]
    assert build_embeds, f"{run_id}: no memory-build embedding observation"
    assert retrieval_embeds, f"{run_id}: no retrieval embedding observation"
    assert conversation_ids <= {row["conversation_id"] for row in build_embeds}
    assert question_ids <= {row["question_id"] for row in retrieval_embeds}
    for row in embeds:
        assert row["model_id"] == "lightmem-embedding"
        assert row["input_tokens"] > 0
        assert row["latency_ms"] >= 0
        assert row["token_measurement_source"] == "tokenizer_estimate"
        assert row["latency_measurement_source"] == "framework_timer"

    overall = read_json(run_dir / "summaries/efficiency_overall.prediction.json")
    embedding_tokens = overall["summary"]["embedding_tokens"]
    assert embedding_tokens
    assert sum(item["call_count"] for item in embedding_tokens.values()) == len(embeds)

    payloads = qdrant_payloads(run_dir, expected_workers)
    if benchmark == "locomo":
        assert payloads, f"{run_id}: no LTM payloads"
        assert all(isinstance(payload.get("source_external_ids"), list) for payload in payloads)
        assert any(
            "D1:5" in payload["source_external_ids"] for payload in payloads
        ), f"{run_id}: caption-bearing D1:5 did not reach persisted lineage"

    for terminal_name in (
        "terminal.predict.log",
        "terminal.evaluate-offline.log",
        "terminal.evaluate-judge.log",
    ):
        assert (run_dir / "logs" / terminal_name).is_file()

    print(
        f"PASS {run_id}: questions={expected_questions}, workers={expected_workers}, "
        f"embedding_calls={len(embeds)}"
    )

assert lme_iso_hit_count > 0, "LongMemEval v7 runs had no hit with an ISO timestamp"
assert locomo_iso_hit_count > 0, "LoCoMo v7 runs had no hit with an ISO timestamp"
print(
    "PASS v7 readout delta: "
    f"lme_iso_items={lme_iso_hit_count}, locomo_iso_items={locomo_iso_hit_count}"
)
PY
```

脚本如果因“没有命中任何带 ISO 时间的 memory”或“D1:5 没有形成持久化 lineage”失败，不代表
应该删 run 重试；它表示这批真实 artifact 没能提供本轮所需的 delta 证据，必须保留现场交回
架构师裁决。

## 8. 用户执行后交回什么

只需把 §7 的全部 `PASS ...` / assertion 尾部，以及任何非零命令的完整报错交回架构师；其余
terminal log、manifest、prompt、Qdrant 与 efficiency artifact 都在 run 目录中，架构师会直接
开箱。零报错仍不等于最终验收，且四个 run 通过也只关闭 LoCoMo/LME 的 v7 受影响门，不替代
MemBench、BEAM、HaluMem 的逐格重认证。
