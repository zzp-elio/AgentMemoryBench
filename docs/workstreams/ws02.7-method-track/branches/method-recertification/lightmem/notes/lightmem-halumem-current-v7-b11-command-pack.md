# LightMem × HaluMem current-v7 B11 命令包

> 状态：**用户已批准固定 Medium smoke、真实 API 与本页 run identity；命令待用户执行。**
> 本页只认证 LightMem `conversation-qa-v7`（含 forced-flush R1 source identity）在 HaluMem
> 固定 operation-level smoke 上的 session-local extraction、在线 update probe、QA、官方三类
> judge、memory-type 合成与通用离线答案指标。它不代表 Long variant、full、效果、成本外推、
> resume 或整个 LightMem frozen。

## 1. 固定规模与身份

- CLI base run id：`lm-halumem-v7-flush-r1-w1`
- artifact child run id：`lm-halumem-v7-flush-r1-w1-medium`
- 输出目录：
  `outputs/runs/lightmem/halumem/medium/smoke/unified/lm-halumem-v7-flush-r1-w1-medium`
- 固定形状：Medium 首个 conversation，4 sessions，每 session 前 2 turns，1 QA，1 worker。

HaluMem smoke 自己固定裁剪形状；命令**不得**传 `--rounds`、`--sessions`、
`--conversations` 或 `--questions-per-conversation`。operation-level runner 只支持一个 worker，
所以本格没有 W2。smoke 不支持 resume；失败时保留 run 与 terminal log，交回架构师，不在原
run 上重试。

适用 evaluator 按依赖顺序为：

1. `halumem-extraction`（官方，API）；
2. `halumem-update`（官方，API）；
3. `halumem-qa`（官方，API）；
4. `halumem-memory-type`（官方共享分母合成，零 API，依赖前两项）；
5. `f1`、`normalized-em`、`substring-em`（framework supplementary，零 API）。

HaluMem 没有 turn qrel，Retrieval Recall/NDCG 诚实 N/A，本页不运行并不存在的 evaluator。

## 2. 一次性环境门

在一个新的 zsh 中整段执行，后续各节继续使用同一 shell：

```bash
cd /Users/wz/Desktop/memoryBenchmark
set -o pipefail

git status --short
git log -5 --oneline
git diff --quiet
git diff --cached --quiet
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -f .env
test -f data/halumem/HaluMem-Medium.jsonl
test -d models/all-MiniLM-L6-v2
test -d models/llmlingua-2-bert-base-multilingual-cased-meetingbank

HALU_BASE=lm-halumem-v7-flush-r1-w1
HALU_RUN=${HALU_BASE}-medium
HALU_ROOT=outputs/runs/lightmem/halumem/medium/smoke/unified
HALU_DIR=$HALU_ROOT/$HALU_RUN
TMP_LOG_ROOT="${TMPDIR:-/tmp}/memory-benchmark-lightmem-halumem-b11"

test ! -e "$HALU_DIR"
mkdir -p "$TMP_LOG_ROOT"
```

`git status --short` 可以显示 OWNER 的 untracked 私有资产；tracked-source clean 门是两条
`git diff --quiet`。不得打印或 `cat .env`。

## 3. Predict（真实 API）

```bash
uv run memory-benchmark predict smoke \
  --root . \
  --method lightmem \
  --benchmark halumem \
  --variant medium \
  --config-track unified \
  --run-id "$HALU_BASE" \
  --workers 1 \
  --allow-api \
  2>&1 | tee "$TMP_LOG_ROOT/$HALU_RUN.predict.log"
PREDICT_STATUS=$?
mkdir -p "$HALU_DIR/logs"
mv "$TMP_LOG_ROOT/$HALU_RUN.predict.log" \
  "$HALU_DIR/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0
```

只有最后一行 `test` 成功后才继续。

## 4. 付费 judge 调用数预览（零 API）

这不是用 add/pair 数猜成本，而是读取本次真实 predict 的 session report、update probe 与
private evaluator label，严格镜像三家 evaluator 的实际空路由，给出下一节将发生的 judge
调用数。执行：

```bash
uv run python - <<'PY'
from __future__ import annotations

import json
from pathlib import Path


RUN_DIR = Path(
    "outputs/runs/lightmem/halumem/medium/smoke/unified/"
    "lm-halumem-v7-flush-r1-w1-medium"
)


def read_jsonl(path: Path) -> list[dict]:
    """读取 JSONL。"""

    assert path.is_file(), path
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


reports = read_jsonl(RUN_DIR / "artifacts/session_memory_reports.jsonl")
labels = {
    row["session_id"]: row
    for row in read_jsonl(
        RUN_DIR / "artifacts/evaluator_private_session_labels.jsonl"
    )
}
probes = read_jsonl(RUN_DIR / "artifacts/update_probe_results.jsonl")
predictions = read_jsonl(RUN_DIR / "artifacts/method_predictions.jsonl")
update_keys = {
    (row["session_ref"]["session_id"], row["gold_memory_index"])
    for row in probes
}

extraction_calls = 0
for report in reports:
    if report.get("status") != "ok":
        continue
    session_id = report["session_ref"]["session_id"]
    memories = report.get("memories") or []
    if not memories:
        continue
    for point in labels[session_id]["memory_points"]:
        key = (session_id, point.get("index"))
        if point.get("is_update") == "True" and key in update_keys:
            continue
        extraction_calls += 1
    extraction_calls += len(memories)

update_calls = sum(bool(row.get("memories_from_system")) for row in probes)
qa_calls = len(predictions)
print(
    "JUDGE_CALL_PREVIEW "
    f"extraction={extraction_calls} update={update_calls} qa={qa_calls} "
    f"total={extraction_calls + update_calls + qa_calls}"
)
PY
```

调用数随真实抽取是否为空而变化：空 extraction memory 的 integrity 由官方空路由直接记 0，
不调 judge；空 retrieval 的 update point 也不调 judge。预览只是透明披露，不修改本次 run。

## 5. 三项官方 judge（真实 API）

按顺序整段执行：

```bash
for METRIC in halumem-extraction halumem-update halumem-qa; do
  uv run memory-benchmark evaluate \
    --root . \
    --run-id "$HALU_RUN" \
    --metric "$METRIC" \
    --judge-profile compact \
    --workers 1 \
    --allow-api \
    2>&1 | tee "$HALU_DIR/logs/terminal.evaluate.$METRIC.log"
  EVAL_STATUS=$?
  test "$EVAL_STATUS" -eq 0 || break
done
test "$EVAL_STATUS" -eq 0
```

任一 metric 非零就停止，不继续跑免费合成项。

## 6. 四项零 API evaluator

`halumem-memory-type` 必须在 extraction + update artifact 已存在后运行：

```bash
for METRIC in halumem-memory-type f1 normalized-em substring-em; do
  uv run memory-benchmark evaluate \
    --root . \
    --run-id "$HALU_RUN" \
    --metric "$METRIC" \
    --workers 1 \
    2>&1 | tee "$HALU_DIR/logs/terminal.evaluate.$METRIC.log"
  EVAL_STATUS=$?
  test "$EVAL_STATUS" -eq 0 || break
done
test "$EVAL_STATUS" -eq 0
```

## 7. 全 run 机器验货（零 API）

上面全部命令成功后执行。机器门不要求“分数高”，而是验证：current source identity、固定
4-session 输入、session report 与 Qdrant lineage 一致、无跨 session residual、官方 MEMZERO
answer builder、HaluMem retrieval N/A、真实 embedding/LLM 观测、三类 judge 调用与 scope、
memory-type 依赖和三个通用离线指标。

```bash
uv run python - <<'PY'
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from qdrant_client import QdrantClient

from memory_benchmark.benchmark_adapters.contracts import (
    BenchmarkLoadRequest,
    RunScope,
)
from memory_benchmark.benchmark_adapters.halumem import prepare_halumem_run
from memory_benchmark.core.validators import validate_no_private_keys
from memory_benchmark.methods.lightmem_adapter import (
    _storage_safe_collection_name,
    build_lightmem_source_identity,
)
from memory_benchmark.config import load_path_settings
from memory_benchmark.runners.event_stream import default_isolation_key


RUN_ID = "lm-halumem-v7-flush-r1-w1-medium"
RUN_DIR = Path(
    "outputs/runs/lightmem/halumem/medium/smoke/unified"
) / RUN_ID
CONVERSATION_ID = "2f1f897e-d67f-dbc5-6a7b-b7634a9e294f"
QUESTION_ID = f"{CONVERSATION_ID}:s1:q1"
SESSION_IDS = ("s1", "s2", "s3", "s4")
SESSION_DATES = {
    "s1": "2025-09-04",
    "s2": "2025-09-05",
    "s3": "2025-09-06",
    "s4": "2025-12-15",
}
SENTINEL = "(No relevant memories found)"
ISO_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}")


def read_json(path: Path) -> dict:
    """读取 JSON object。"""

    assert path.is_file(), path
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), path
    return payload


def read_jsonl(path: Path) -> list[dict]:
    """读取 JSONL；允许合法空文件。"""

    assert path.is_file(), path
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sha256_file(path: Path) -> str:
    """流式计算文件 SHA-256。"""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


# 1. source-locked 固定公开输入。
source_path = Path("data/halumem/HaluMem-Medium.jsonl")
source_lock = read_json(
    Path(
        "docs/workstreams/ws02.6-first-smoke-hardening/notes/"
        "halumem-source-lock.json"
    )
)["data_files"][source_path.as_posix()]
assert source_path.stat().st_size == source_lock["size_bytes"]
assert sha256_file(source_path) == source_lock["sha256"]

prepared = prepare_halumem_run(
    Path("."),
    BenchmarkLoadRequest(
        variant="medium",
        run_scope=RunScope.SMOKE,
        smoke_turn_limit=4,
        smoke_conversation_limit=1,
    ),
)
assert prepared.dataset.metadata["smoke_fixed_shape"] is True
assert prepared.dataset.metadata["smoke_retained_session_count"] == 4
assert prepared.dataset.metadata["smoke_retained_turn_count"] == 8
assert prepared.dataset.metadata["smoke_retained_question_count"] == 1
assert len(prepared.dataset.conversations) == 1
conversation = prepared.dataset.conversations[0]
assert conversation.conversation_id == CONVERSATION_ID
assert tuple(session.session_id for session in conversation.sessions) == SESSION_IDS
for session in conversation.sessions:
    assert len(session.turns) == 2
    assert [turn.normalized_role for turn in session.turns] == [
        "user",
        "assistant",
    ]
    assert [turn.turn_id for turn in session.turns] == [
        f"{session.session_id}:t1",
        f"{session.session_id}:t2",
    ]
    assert all(turn.turn_time == session.session_time for turn in session.turns)
assert [question.question_id for question in conversation.questions] == [QUESTION_ID]

# 2. run / method / instrumentation identity。
manifest = read_json(RUN_DIR / "manifest.json")
method = manifest["method"]
config = method["config"]
assert manifest["runner"] == "operation_level_prediction"
assert manifest["run_id"] == RUN_ID
assert manifest["benchmark_name"] == "halumem"
assert manifest["benchmark_variant"] == "medium"
assert manifest["run_scope"] == "smoke"
assert manifest["policy"]["max_workers"] == 1
assert method["protocol_version"] == "v3"
assert method["consume_granularity"] == "session"
assert method["prompt_track"] == "unified"
assert method["retrieval_evidence_contract_version"] == "v1"
assert method["provenance_granularity"] == "turn"
assert config["adapter_version"] == "conversation-qa-v7"
assert config["messages_use"] == "hybrid"
assert config["lifecycle_profile"] == "online_soft"
assert config["missing_timestamp_policy"] == "preserve_none"
assert config["retrieve_limit"] == 60
assert config["embedding_dimensions"] == 384

current_source = build_lightmem_source_identity(load_path_settings())
assert method["source"] == current_source
assert current_source["file_count"] == 8
assert (
    "src/lightmem/factory/memory_buffer/sensory_memory.py"
    in current_source["files"]
)
instrumentation = manifest["instrumentation_identity"]
assert instrumentation["method_source_sha256"] == current_source["source_sha256"]
wrapper = Path(instrumentation["wrapper_path"])
assert sha256_file(wrapper) == instrumentation["wrapper_sha256"]

# 3. operation-level 输出完整性、公开/私有边界与官方 builder。
checkpoint = read_json(RUN_DIR / "checkpoints/conversation_status.json")
assert checkpoint == {
    CONVERSATION_ID: {"status": "completed", "ingested": True}
}
summary = read_json(RUN_DIR / "summaries/summary.json")
assert summary["total_conversations"] == summary["completed_conversations"] == 1
assert summary["total_questions"] == summary["completed_questions"] == 1

public = read_jsonl(RUN_DIR / "artifacts/public_questions.jsonl")
predictions = read_jsonl(RUN_DIR / "artifacts/method_predictions.jsonl")
answers = read_jsonl(RUN_DIR / "artifacts/answer_prompts.prediction.jsonl")
assert len(public) == len(predictions) == len(answers) == 1
assert public[0]["question_id"] == predictions[0]["question_id"] == QUESTION_ID
assert answers[0]["question_id"] == QUESTION_ID
assert predictions[0]["answer"].strip()
validate_no_private_keys(public)
validate_no_private_keys(answers)

answer = answers[0]
assert answer["metadata"]["prompt_track"] == "unified"
assert answer["metadata"]["answer_prompt_profile"] == "halumem_memzero_v1"
assert answer["formatted_memory"] in answer["answer_prompt"]
assert "The answer should be less than 5-6 words" in answer["answer_prompt"]
assert "[Memory recorded on:" not in answer["formatted_memory"]
assert "None None" not in answer["formatted_memory"]
if answer["retrieved_items"]:
    assert answer["formatted_memory"] == "\n".join(
        item["content"] for item in answer["retrieved_items"]
    )
    assert all(ISO_PREFIX.match(item["content"]) for item in answer["retrieved_items"])
else:
    assert answer["formatted_memory"] == SENTINEL

evidence = answer["retrieval_evidence"]
assert evidence["semantic_provenance"]["status"] == "n_a"
assert evidence["semantic_provenance"]["reason_code"] == "halumem_no_turn_qrel"
assert evidence["provenance_granularity"] == "none"
assert evidence["stable_ranking"]["status"] == "pending"

# 4. 四份 session report 必须逐 session 对齐；capture count 与真实 LTM lineage 相等。
reports = read_jsonl(RUN_DIR / "artifacts/session_memory_reports.jsonl")
assert [row["session_ref"]["session_id"] for row in reports] == list(SESSION_IDS)
isolation_key = default_isolation_key(RUN_ID, CONVERSATION_ID)
report_memories: Counter[tuple[str, str]] = Counter()
for report in reports:
    ref = report["session_ref"]
    session_id = ref["session_id"]
    metadata = report["metadata"]
    memories = report["memories"]
    assert ref["isolation_key"] == isolation_key
    assert report["status"] == "ok"
    assert metadata["source"] == "embedding_insert_observer"
    assert metadata["force_segment"] is True
    assert metadata["force_extract"] is True
    assert metadata["captured_memory_count"] == len(memories)
    assert metadata["capture_status"] == ("ok" if memories else "empty")
    report_memories.update((session_id, memory) for memory in memories)

state_root = RUN_DIR / "method_state"
assert list(state_root.glob("worker_*")) == []
qdrant_root = state_root / "qdrant"
database_name = _storage_safe_collection_name(isolation_key)
database = qdrant_root / database_name
assert database.is_dir(), database
payloads: list[dict] = []
client = QdrantClient(path=str(database))
try:
    for collection in client.get_collections().collections:
        points, next_offset = client.scroll(
            collection_name=collection.name,
            limit=1000,
            with_payload=True,
            with_vectors=False,
        )
        assert next_offset is None
        payloads.extend(point.payload or {} for point in points)
finally:
    client.close()

payload_memories: Counter[tuple[str, str]] = Counter()
ltm_by_session: Counter[str] = Counter()
for payload in payloads:
    source_ids = payload.get("source_external_ids")
    assert isinstance(source_ids, list) and source_ids, payload
    assert all(isinstance(source_id, str) for source_id in source_ids)
    source_sessions = {source_id.split(":", 1)[0] for source_id in source_ids}
    assert len(source_sessions) == 1, payload
    session_id = next(iter(source_sessions))
    assert session_id in SESSION_IDS
    assert set(source_ids).issubset(
        {f"{session_id}:t1", f"{session_id}:t2"}
    )
    assert str(payload.get("time_stamp", "")).startswith(SESSION_DATES[session_id])
    memory = payload.get("memory")
    assert isinstance(memory, str) and memory.strip()
    payload_memories[(session_id, memory)] += 1
    ltm_by_session[session_id] += 1

assert payload_memories == report_memories, (payload_memories, report_memories)
assert len(payloads) == sum(
    report["metadata"]["captured_memory_count"] for report in reports
)

# 5. update probes 只来自固定 s4 的七个 update points。
probes = read_jsonl(RUN_DIR / "artifacts/update_probe_results.jsonl")
assert len(probes) == 7
assert {row["session_ref"]["session_id"] for row in probes} == {"s4"}
assert {row["gold_memory_index"] for row in probes} == {1, 3, 4, 5, 6, 7, 9}
assert all(row["session_ref"]["isolation_key"] == isolation_key for row in probes)
assert all(isinstance(row["memories_from_system"], list) for row in probes)

# 6. prediction 期 model/LLM/embedding 观测。
prediction_inventory = read_json(
    RUN_DIR / "artifacts/model_inventory.prediction.json"
)
assert {model["model_id"] for model in prediction_inventory["models"]} == {
    "gpt-4o-mini",
    "lightmem-embedding",
    "lightmem-memory-llm",
}
prediction_observations = read_jsonl(
    RUN_DIR / "artifacts/efficiency_observations.prediction.jsonl"
)
memory_llm = [
    row
    for row in prediction_observations
    if row["observation_type"] == "llm_call"
    and row["stage"] == "memory_build"
    and row["model_id"] == "lightmem-memory-llm"
]
answer_llm = [
    row
    for row in prediction_observations
    if row["observation_type"] == "llm_call" and row["stage"] == "answer"
]
embeddings = [
    row
    for row in prediction_observations
    if row["observation_type"] == "embedding_call"
]
qa_retrieval_embeddings = [
    row
    for row in embeddings
    if row["stage"] == "retrieval" and row["question_id"] == QUESTION_ID
]
assert len(memory_llm) >= 4
assert len(answer_llm) == 1 and answer_llm[0]["question_id"] == QUESTION_ID
assert len(qa_retrieval_embeddings) == 1
assert len(embeddings) >= len(probes) + 1
assert all(row["model_id"] == "lightmem-embedding" for row in embeddings)
assert all(row["input_tokens"] > 0 and row["latency_ms"] >= 0 for row in embeddings)

# 7. 三个官方 judge 的 score/observation 数须逐真实路由精确一致。
judge_metrics = ("halumem_extraction", "halumem_update", "halumem_qa")
score_rows = {
    metric: read_jsonl(RUN_DIR / f"artifacts/answer_scores.{metric}.jsonl")
    for metric in judge_metrics
}
summaries = {
    metric: read_json(RUN_DIR / f"summaries/summary.{metric}.json")
    for metric in judge_metrics
}
for metric in judge_metrics:
    assert summaries[metric]["run_id"] == RUN_ID
    assert summaries[metric]["benchmark_name"] == "halumem"
    assert summaries[metric]["metric_name"] == metric
    assert summaries[metric]["total_questions"] == len(score_rows[metric])
    assert all("efficiency_observations" not in row for row in score_rows[metric])
    inventory = read_json(RUN_DIR / f"artifacts/model_inventory.{metric}.json")
    assert {model["model_id"] for model in inventory["models"]} == {"judge-llm"}

nonempty_report_sessions = {
    row["session_ref"]["session_id"] for row in reports if row["memories"]
}
expected_extraction_calls = sum(
    row["record_kind"] == "memory_accuracy"
    or (
        row["record_kind"] == "memory_integrity"
        and row["session_id"] in nonempty_report_sessions
    )
    for row in score_rows["halumem_extraction"]
)
expected_calls = {
    "halumem_extraction": expected_extraction_calls,
    "halumem_update": len(score_rows["halumem_update"]),
    "halumem_qa": len(score_rows["halumem_qa"]),
}
judge_observations: dict[str, list[dict]] = {}
for metric in judge_metrics:
    rows = read_jsonl(
        RUN_DIR / f"artifacts/efficiency_observations.{metric}.jsonl"
    )
    judge_observations[metric] = rows
    assert len(rows) == expected_calls[metric], (metric, len(rows), expected_calls)
    assert len({row["observation_id"] for row in rows}) == len(rows)
    assert all(row["observation_type"] == "llm_call" for row in rows)
    assert all(row["stage"] == "judge" for row in rows)
    assert all(row["model_id"] == "judge-llm" for row in rows)
    assert all(row["conversation_id"] == CONVERSATION_ID for row in rows)
    assert all(row["input_tokens"] > 0 and row["output_tokens"] >= 0 for row in rows)
    assert all(row["token_measurement_source"] == "api_usage" for row in rows)

assert all(
    row["question_id"].startswith("halumem_extraction:s")
    for row in judge_observations["halumem_extraction"]
)
expected_update_scopes = {
    f"halumem_update:{row['session_id']}:{row['gold_memory_index']}"
    for row in score_rows["halumem_update"]
}
assert {
    row["question_id"] for row in judge_observations["halumem_update"]
} == expected_update_scopes
assert {
    row["question_id"] for row in judge_observations["halumem_qa"]
} == {QUESTION_ID}

# 8. memory-type 与三个通用离线指标已落盘，且不伪造 judge observation。
offline_metrics = ("halumem_memory_type", "f1", "normalized_em", "substring_em")
for metric in offline_metrics:
    metric_summary = read_json(RUN_DIR / f"summaries/summary.{metric}.json")
    metric_rows = read_jsonl(RUN_DIR / f"artifacts/answer_scores.{metric}.jsonl")
    assert metric_summary["run_id"] == RUN_ID
    assert metric_summary["benchmark_name"] == "halumem"
    assert metric_summary["metric_name"] == metric
    assert metric_summary["total_questions"] == len(metric_rows)
    assert not (RUN_DIR / f"artifacts/model_inventory.{metric}.json").exists()
    assert not (
        RUN_DIR / f"artifacts/efficiency_observations.{metric}.jsonl"
    ).exists()
assert len(score_rows["halumem_qa"]) == 1
assert all(
    read_json(RUN_DIR / f"summaries/summary.{metric}.json")["total_questions"] == 1
    for metric in ("f1", "normalized_em", "substring_em")
)

for terminal_name in (
    "terminal.predict.log",
    "terminal.evaluate.halumem-extraction.log",
    "terminal.evaluate.halumem-update.log",
    "terminal.evaluate.halumem-qa.log",
    "terminal.evaluate.halumem-memory-type.log",
    "terminal.evaluate.f1.log",
    "terminal.evaluate.normalized-em.log",
    "terminal.evaluate.substring-em.log",
):
    assert (RUN_DIR / "logs" / terminal_name).is_file(), terminal_name

print(
    f"PASS {RUN_ID}: sessions=4, reports="
    f"{[row['metadata']['captured_memory_count'] for row in reports]}, "
    f"ltm={dict(ltm_by_session)}, update_probes={len(probes)}, "
    f"memory_llm_calls={len(memory_llm)}, embedding_calls={len(embeddings)}"
)
print(
    "PASS HaluMem judges: "
    f"calls={expected_calls}, scopes=exact, efficiency=observed"
)
print(
    "PASS LightMem×HaluMem current-v7 B11 machine gate: "
    "session-local flush, online LTM retained, all eligible metrics present"
)
PY
```

若真实 extraction 合法返回零 memory，`reports=[0,0,0,0]` 与 `ltm={}` 可以通过；这表示真实
API 已走完 normalizer/extraction/empty route，而 non-empty lineage 与 forced-flush 则继续由
已强验收的真实 vendored production-chain 测试承重。机器门绝不会为制造非空 memory 换样本、
重跑 API 或放宽 source/session 一致性。

## 8. 用户执行后交回内容

只需交回：

1. §4 的 `JUDGE_CALL_PREVIEW ...`；
2. §7 的三条 `PASS ...`；
3. 任一非零命令的完整错误。

其余 manifest、prompt、session report、Qdrant、效率与 evaluator artifacts 都在 run 目录，
架构师会直接开箱。零报错不等于最终验收；本页通过只关闭 LightMem × HaluMem current-v7 B11。
