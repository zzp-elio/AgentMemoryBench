# LightMem × BEAM current-v7 B11 命令包

> 状态：**用户已批准以下固定规模与真实 API 预算；命令待用户执行。**本页只认证
> LightMem `conversation-qa-v7` 主配置在 BEAM 100K/10M 两种结构上的 pair 投递、
> product readout、单/双 worker 隔离、逐题 RetrievalEvidence、官方 rubric judge 与
> framework-supplementary Recall 的诚实 N/A。它不代表 500K/1M 重跑、full、效果、成本、
> resume 或 LightMem 整体 frozen。

## 1. 规模与身份裁决

BEAM 必须用两个独立 run 覆盖两套真实结构，但不重复跑同构 variant：

| variant | CLI base run id | artifact child run id | 固定规模 |
|---|---|---|---|
| 100K | `lm-beam-v7-pair-r1q1-c2-w2` | `lm-beam-v7-pair-r1q1-c2-w2-100k` | 2 conversations × 1 round × 1 question × 2 workers |
| 10M | `lm-beam-v7-pair-r1q1-w1` | `lm-beam-v7-pair-r1q1-w1-10m` | 1 conversation × 1 round × 1 question × 1 worker |

100K 的第二条 conversation 只用于重验 `turn→pair` 后的 worker/state 隔离；10M 用单 worker
覆盖 plan/batch 嵌套展开。500K/1M 与 100K 同构，source-locked census 和确定性测试已覆盖，
本轮不重复烧 API。10M 两处 dangling user、一个全缺时 session 与五次跨 session anchor
回退都不位于公开顺序首个 smoke pair；这些异常由稳定异常账和 production-path 强反例承担，
不能通过读取 gold 或反复换样本来让付费 smoke “碰中”。

两个 predict 必须按本文顺序串行执行；W2 只发生在 100K 命令内部。smoke 不支持 resume，
任一命令非零时保留目录和日志，停止并交回架构师。

适用 evaluator 只有：

- `beam-recall`：零 API、framework supplementary；本次首题均为官方 abstention，且 LightMem
  pair lineage 对 BEAM single-message gold 也不具备资格，所以必须诚实落 `N/A`；
- `beam-rubric-judge`：BEAM 官方主任务，使用项目统一 `gpt-4o-mini` 与 compact profile；
- 通用 token-F1、normalized EM、substring EM 已按任务匹配裁决从 BEAM registry 移除，
  不能为了“多算指标”强加给 rubric 任务。

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
test -d data/BEAM/beam_dataset/100K
test -d data/BEAM/beam_10M_dataset/10M
test -d models/all-MiniLM-L6-v2
test -d models/llmlingua-2-bert-base-multilingual-cased-meetingbank

BEAM100_BASE=lm-beam-v7-pair-r1q1-c2-w2
BEAM100_RUN=${BEAM100_BASE}-100k
BEAM100_ROOT=outputs/runs/lightmem/beam/100k/smoke/unified

BEAM10_BASE=lm-beam-v7-pair-r1q1-w1
BEAM10_RUN=${BEAM10_BASE}-10m
BEAM10_ROOT=outputs/runs/lightmem/beam/10m/smoke/unified

TMP_LOG_ROOT="${TMPDIR:-/tmp}/memory-benchmark-lightmem-beam-b11"
test ! -e "$BEAM100_ROOT/$BEAM100_RUN"
test ! -e "$BEAM10_ROOT/$BEAM10_RUN"
mkdir -p "$TMP_LOG_ROOT"
```

`git status --short` 可以显示 OWNER 已有的 untracked 私有资产；真正的 tracked-source clean
门是两条 `git diff --quiet`。不得打印或 `cat .env`。

## 3. 100K：双 conversation / 双 worker

### 3.1 predict

```bash
uv run memory-benchmark predict smoke \
  --root . \
  --method lightmem \
  --benchmark beam \
  --variant 100k \
  --config-track unified \
  --run-id "$BEAM100_BASE" \
  --rounds 1 \
  --conversations 2 \
  --questions-per-conversation 1 \
  --workers 2 \
  --allow-api \
  2>&1 | tee "$TMP_LOG_ROOT/$BEAM100_RUN.predict.log"
PREDICT_STATUS=$?
mkdir -p "$BEAM100_ROOT/$BEAM100_RUN/logs"
mv "$TMP_LOG_ROOT/$BEAM100_RUN.predict.log" \
  "$BEAM100_ROOT/$BEAM100_RUN/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0
```

### 3.2 零 API Recall

```bash
uv run memory-benchmark evaluate \
  --root . \
  --run-id "$BEAM100_RUN" \
  --metric beam-recall \
  --workers 1 \
  2>&1 | tee "$BEAM100_ROOT/$BEAM100_RUN/logs/terminal.evaluate-offline.log"
OFFLINE_STATUS=$?
test "$OFFLINE_STATUS" -eq 0
```

离线算分保持单 worker；本轮并发认证对象是 predict 的 provider/Qdrant 隔离，不为飞快的
artifact-only 指标额外制造并行噪声。

### 3.3 付费官方 rubric judge

```bash
uv run memory-benchmark evaluate \
  --root . \
  --run-id "$BEAM100_RUN" \
  --metric beam-rubric-judge \
  --judge-profile compact \
  --workers 2 \
  --allow-api \
  2>&1 | tee "$BEAM100_ROOT/$BEAM100_RUN/logs/terminal.evaluate-judge.log"
JUDGE_STATUS=$?
test "$JUDGE_STATUS" -eq 0
```

## 4. 10M：单 conversation / 单 worker

只有 §3 三段全部 exit 0 后继续：

### 4.1 predict

```bash
uv run memory-benchmark predict smoke \
  --root . \
  --method lightmem \
  --benchmark beam \
  --variant 10m \
  --config-track unified \
  --run-id "$BEAM10_BASE" \
  --rounds 1 \
  --conversations 1 \
  --questions-per-conversation 1 \
  --workers 1 \
  --allow-api \
  2>&1 | tee "$TMP_LOG_ROOT/$BEAM10_RUN.predict.log"
PREDICT_STATUS=$?
mkdir -p "$BEAM10_ROOT/$BEAM10_RUN/logs"
mv "$TMP_LOG_ROOT/$BEAM10_RUN.predict.log" \
  "$BEAM10_ROOT/$BEAM10_RUN/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0
```

### 4.2 零 API Recall

```bash
uv run memory-benchmark evaluate \
  --root . \
  --run-id "$BEAM10_RUN" \
  --metric beam-recall \
  --workers 1 \
  2>&1 | tee "$BEAM10_ROOT/$BEAM10_RUN/logs/terminal.evaluate-offline.log"
OFFLINE_STATUS=$?
test "$OFFLINE_STATUS" -eq 0
```

### 4.3 付费官方 rubric judge

```bash
uv run memory-benchmark evaluate \
  --root . \
  --run-id "$BEAM10_RUN" \
  --metric beam-rubric-judge \
  --judge-profile compact \
  --workers 1 \
  --allow-api \
  2>&1 | tee "$BEAM10_ROOT/$BEAM10_RUN/logs/terminal.evaluate-judge.log"
JUDGE_STATUS=$?
test "$JUDGE_STATUS" -eq 0
```

## 5. 两个 run 的机器验货（零 API）

六段命令全部成功后执行。脚本不要求答案正确或分数高；它验证 current-v7 identity、两种
source-locked 数据结构、pair crop、官方 answer builder、逐题 evidence、Recall N/A、rubric
float/official-int 双字段、embedding 观测与 worker Qdrant 隔离。

真实 extraction 可以合法返回零 memory。机器门因此采用 actual-call-aware 口径：每个
conversation 必须真正发生 memory-build LLM，每道题必须发生 retrieval embedding；有持久化
LTM 时再强校验 pair lineage、source time 与 build embedding。零 LTM 不伪造“本应发生”的
insert，但会在 PASS 输出中明确披露。

```bash
uv run python - <<'PY'
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from qdrant_client import QdrantClient

from memory_benchmark.benchmark_adapters.beam import prepare_beam_run
from memory_benchmark.benchmark_adapters.contracts import BenchmarkLoadRequest, RunScope
from memory_benchmark.core.validators import validate_no_private_keys
from memory_benchmark.methods.lightmem_adapter import _storage_safe_collection_name
from memory_benchmark.runners.event_stream import default_isolation_key


ISO_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\s")
SENTINEL = "(No relevant memories found)"
EXPECTED_ABILITIES = {
    "abstention",
    "contradiction_resolution",
    "event_ordering",
    "information_extraction",
    "instruction_following",
    "knowledge_update",
    "multi_session_reasoning",
    "preference_following",
    "summarization",
    "temporal_reasoning",
}


def read_json(path: Path) -> dict:
    """读取一个 JSON object。"""

    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    """读取非空 JSONL records。"""

    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def read_qdrant_payloads(
    run_dir: Path,
    *,
    expected_workers: int,
    conversation_ids: set[str],
) -> tuple[dict[str, list[dict]], dict[str, set[str]]]:
    """按生产 identity 找到每个 conversation 的 Qdrant payload 与物理位置。"""

    state_root = run_dir / "method_state"
    worker_dirs = sorted(state_root.glob("worker_*"))
    if expected_workers == 1:
        assert worker_dirs == [], (run_dir, worker_dirs)
        roots = (("run", state_root / "qdrant"),)
    else:
        assert [path.name for path in worker_dirs] == ["worker_0", "worker_1"]
        roots = tuple((path.name, path / "qdrant") for path in worker_dirs)

    database_to_conversation = {
        _storage_safe_collection_name(
            default_isolation_key(run_dir.name, conversation_id)
        ): conversation_id
        for conversation_id in conversation_ids
    }
    assert len(database_to_conversation) == len(conversation_ids)
    payloads = {conversation_id: [] for conversation_id in conversation_ids}
    locations: dict[str, set[str]] = defaultdict(set)

    for location, root in roots:
        assert root.is_dir() and any(root.iterdir()), root
        for database in sorted(path for path in root.iterdir() if path.is_dir()):
            if database.name.endswith("_summary") or not (database / "collection").is_dir():
                continue
            conversation_id = database_to_conversation.get(database.name)
            assert conversation_id is not None, (
                database,
                sorted(database_to_conversation),
            )
            locations[conversation_id].add(location)
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
                    payloads[conversation_id].extend(
                        point.payload or {} for point in points
                    )
            finally:
                client.close()

    assert set(locations) == conversation_ids, (locations, conversation_ids)
    assert all(len(value) == 1 for value in locations.values()), locations
    return payloads, locations


cases = (
    {
        "variant": "100k",
        "split_name": "100K",
        "root": Path("outputs/runs/lightmem/beam/100k/smoke/unified"),
        "run_id": "lm-beam-v7-pair-r1q1-c2-w2-100k",
        "workers": 2,
        "conversations": {"1", "2"},
        "questions": {"1:abstention:q1", "2:abstention:q1"},
        "session_id": "s1",
        "pair_ids": {"s1:t1", "s1:t2"},
        "source_time": "March-15-2024",
        "source_date": "2024-03-15",
        "fingerprint_questions": 40,
    },
    {
        "variant": "10m",
        "split_name": "10M",
        "root": Path("outputs/runs/lightmem/beam/10m/smoke/unified"),
        "run_id": "lm-beam-v7-pair-r1q1-w1-10m",
        "workers": 1,
        "conversations": {"1"},
        "questions": {"1:abstention:q1"},
        "session_id": "p1:s1",
        "pair_ids": {"p1:s1:t1", "p1:s1:t2"},
        "source_time": "July-01-2024",
        "source_date": "2024-07-01",
        "fingerprint_questions": 20,
    },
)

source_lock = read_json(
    Path("docs/workstreams/ws02.6-first-smoke-hardening/notes/beam-source-lock.json")
)
total_payloads = 0
total_build_embeddings = 0

for case in cases:
    variant = case["variant"]
    run_id = case["run_id"]
    expected_workers = case["workers"]
    expected_conversations = case["conversations"]
    expected_questions = case["questions"]
    run_dir = case["root"] / run_id

    # 用 production adapter 复算公开顺序切片，不从 gold 选择 smoke 样本。
    prepared = prepare_beam_run(
        Path("."),
        BenchmarkLoadRequest(
            variant=variant,
            run_scope=RunScope.SMOKE,
            smoke_turn_limit=1,
            smoke_conversation_limit=len(expected_conversations),
        ),
    )
    assert {c.conversation_id for c in prepared.dataset.conversations} == (
        expected_conversations
    )
    for conversation in prepared.dataset.conversations:
        assert len(conversation.sessions) == 1
        session = conversation.sessions[0]
        assert session.session_id == case["session_id"]
        assert session.session_time == case["source_time"]
        assert len(session.turns) == 2
        assert {turn.turn_id for turn in session.turns} == case["pair_ids"]
        assert [turn.normalized_role for turn in session.turns] == ["user", "assistant"]
        assert session.turns[0].turn_time == case["source_time"]
        assert session.turns[1].turn_time is None
        assert conversation.questions[0].category == "abstention"

    manifest = read_json(run_dir / "manifest.json")
    method = manifest["method"]
    config = method["config"]
    reader = method["answer_reader"]
    assert manifest["run_id"] == run_id
    assert manifest["benchmark_name"] == "beam"
    assert manifest["benchmark_variant"] == variant
    assert manifest["run_scope"] == "smoke"
    assert manifest["policy"]["max_workers"] == expected_workers
    assert method["protocol_version"] == "v3"
    assert method["consume_granularity"] == "pair"
    assert method["prompt_track"] == "unified"
    assert method["retrieval_evidence_contract_version"] == "v1"
    assert manifest["benchmark_policy"]["gold_evidence_contract_version"] == "v1"
    assert config["adapter_version"] == "conversation-qa-v7"
    assert config["messages_use"] == "hybrid"
    assert config["lifecycle_profile"] == "online_soft"
    assert config["missing_timestamp_policy"] == "preserve_none"
    assert config["retrieve_limit"] == 60
    assert config["embedding_dimensions"] == 384
    assert reader["answer_parameters"]["temperature"] == 0.0
    assert reader["answer_parameters"]["max_tokens"] is None

    fingerprint = read_json(run_dir / "artifacts/dataset_fingerprint.json")
    assert fingerprint["conversation_count"] == len(expected_conversations)
    assert fingerprint["question_count"] == case["fingerprint_questions"]
    assert len(fingerprint["source_paths"]) == 1
    source = fingerprint["source_paths"][0]
    locked = source_lock["split_directory_identity"][case["split_name"]]
    assert source["sha256"] == locked["sha256"]
    assert source["size_bytes"] == locked["size_bytes"]

    public = read_jsonl(run_dir / "artifacts/public_questions.jsonl")
    predictions = read_jsonl(run_dir / "artifacts/method_predictions.jsonl")
    answers = read_jsonl(run_dir / "artifacts/answer_prompts.prediction.jsonl")
    assert len(public) == len(predictions) == len(answers) == len(expected_questions)
    assert {row["question_id"] for row in public} == expected_questions
    assert {row["conversation_id"] for row in public} == expected_conversations
    validate_no_private_keys(public)
    validate_no_private_keys(answers)

    retrieved_by_conversation: Counter[str] = Counter()
    for row in answers:
        assert row["retrieval_query_top_k"] == 10
        assert row["metadata"]["answer_prompt_profile"] == "beam_rag_v1"
        assert row["metadata"]["prompt_track"] == "unified"
        assert row["formatted_memory"] in row["answer_prompt"]
        assert "Answer ONLY based on the provided context" in row["answer_prompt"]
        assert "[Memory recorded on:" not in row["formatted_memory"]
        assert "None None" not in row["formatted_memory"]
        items = row["retrieved_items"]
        if items:
            assert row["formatted_memory"] == "\n".join(
                item["content"] for item in items
            )
            assert all(ISO_PREFIX.match(item["content"]) for item in items)
            retrieved_by_conversation[row["conversation_id"]] += len(items)
        else:
            assert row["formatted_memory"] == SENTINEL

        evidence = row["retrieval_evidence"]
        assert evidence["semantic_provenance"]["status"] == "n_a"
        assert evidence["semantic_provenance"]["reason_code"] == (
            "beam_gold_is_single_message"
        )
        assert evidence["provenance_granularity"] == "none"
        assert evidence["stable_ranking"]["status"] == "pending"

    progress = read_json(run_dir / "checkpoints/progress.json")
    prediction_summary = read_json(run_dir / "summaries/summary.json")
    assert progress["stage"] == "Completed"
    assert progress["conversation_completed"] == len(expected_conversations)
    assert progress["question_completed"] == len(expected_questions)
    assert prediction_summary["completed_conversations"] == len(expected_conversations)
    assert prediction_summary["completed_questions"] == len(expected_questions)

    recall = read_json(run_dir / "summaries/summary.beam_recall.json")
    recall_rows = read_jsonl(run_dir / "artifacts/answer_scores.beam_recall.jsonl")
    assert recall["total_questions"] == len(expected_questions)
    assert recall["mean_score"] is None
    assert recall["status"] == "n/a"
    assert recall["scored_question_count"] == 0
    assert recall["abstention_question_count"] == len(expected_questions)
    assert recall["score_status_counts"] == {"n/a": len(expected_questions)}
    assert recall["aggregation_contract_version"] == "retrieval-summary-v2"
    assert len(recall_rows) == len(expected_questions)
    assert all(row["score"] is None and row["status"] == "n/a" for row in recall_rows)
    assert all(row["exclusion_source"] == "benchmark_policy" for row in recall_rows)

    judge = read_json(run_dir / "summaries/summary.beam_rubric_judge.json")
    judge_rows = read_jsonl(
        run_dir / "artifacts/answer_scores.beam_rubric_judge.jsonl"
    )
    assert judge["total_questions"] == len(expected_questions)
    assert judge["status"] == "ok"
    assert isinstance(judge["mean_score"], (int, float))
    assert len(judge_rows) == len(expected_questions)
    assert all(row["ability"] == "abstention" for row in judge_rows)
    assert all(row["rubric_count"] > 0 for row in judge_rows)
    assert all(isinstance(row["score"], (int, float)) for row in judge_rows)
    assert all(
        isinstance(row["llm_judge_score_official_int"], (int, float))
        for row in judge_rows
    )
    breakdown = {row["category"]: row for row in judge["category_breakdown"]}
    assert set(breakdown) == EXPECTED_ABILITIES
    assert breakdown["abstention"]["question_count"] == len(expected_questions)

    inventory = read_json(run_dir / "artifacts/model_inventory.prediction.json")
    assert {model["model_id"] for model in inventory["models"]} == {
        "gpt-4o-mini",
        "lightmem-embedding",
        "lightmem-memory-llm",
    }

    observations = read_jsonl(
        run_dir / "artifacts/efficiency_observations.prediction.jsonl"
    )
    embeds = [row for row in observations if row["observation_type"] == "embedding_call"]
    build_embeds = [row for row in embeds if row["stage"] == "memory_build"]
    retrieval_embeds = [row for row in embeds if row["stage"] == "retrieval"]
    memory_build_llm = [
        row
        for row in observations
        if row["observation_type"] == "llm_call" and row["stage"] == "memory_build"
    ]
    assert {row["question_id"] for row in retrieval_embeds} == expected_questions
    build_llm_counts = Counter(row["conversation_id"] for row in memory_build_llm)
    assert set(build_llm_counts) == expected_conversations
    assert all(count >= 1 for count in build_llm_counts.values())
    assert all(row["model_id"] == "lightmem-embedding" for row in embeds)
    assert all(row["input_tokens"] > 0 and row["latency_ms"] >= 0 for row in embeds)

    overall = read_json(run_dir / "summaries/efficiency_overall.prediction.json")
    embedding_tokens = overall["summary"]["embedding_tokens"]
    assert sum(item["call_count"] for item in embedding_tokens.values()) == len(embeds)

    payloads, locations = read_qdrant_payloads(
        run_dir,
        expected_workers=expected_workers,
        conversation_ids=expected_conversations,
    )
    build_counts = Counter(row["conversation_id"] for row in build_embeds)
    persisted_counts = {cid: len(rows) for cid, rows in payloads.items()}
    for conversation_id, rows in payloads.items():
        for payload in rows:
            ids = payload.get("source_external_ids")
            assert isinstance(ids, list) and set(ids) == case["pair_ids"], (
                conversation_id,
                payload,
            )
            assert str(payload.get("time_stamp", "")).startswith(case["source_date"])
        if rows:
            assert build_counts[conversation_id] >= len(rows)

    total_payloads += sum(persisted_counts.values())
    total_build_embeddings += len(build_embeds)
    for terminal_name in (
        "terminal.predict.log",
        "terminal.evaluate-offline.log",
        "terminal.evaluate-judge.log",
    ):
        assert (run_dir / "logs" / terminal_name).is_file()

    print(
        f"PASS {run_id}: conversations={len(expected_conversations)}, "
        f"workers={expected_workers}, ltm={persisted_counts}, "
        f"retrieved={dict(retrieved_by_conversation)}, "
        f"memory_build_llm={dict(build_llm_counts)}, "
        f"build_embeddings={dict(build_counts)}, retrieval_embeddings={len(retrieval_embeds)}, "
        f"recall=N/A, judge_rows={len(judge_rows)}, state={dict(locations)}"
    )

print(
    "PASS LightMem×BEAM current-v7 B11 machine gate: "
    f"total_ltm={total_payloads}, total_build_embeddings={total_build_embeddings}"
)
PY
```

机器门若因某个 run 零 LTM 仍会通过，但 PASS 尾行会如实显示 `ltm=0`；这表示真实 run
承担了 normalizer/extraction/zero-hit，而 pair payload 的持久化强反例继续由已验收的
production-path/local-Qdrant 测试承重。不得为了“制造非空 memory”更换样本或重复调用 API。

## 6. 用户执行后交回什么

只需把 §5 的全部 `PASS ...` 尾行，以及任何非零命令的完整报错交回架构师。其余 terminal
log、manifest、prompt、Qdrant、efficiency 与 evaluator artifact 都在 run 目录中，架构师会
直接开箱。零报错不等于最终验收；两个 run 通过也只关闭 LightMem × BEAM current-v7 B11，
不替代 HaluMem 或 LightMem 整体冻结门。

## 7. 编制时零 API 门

2026-07-19 架构师在 current main 上完成以下非付费自检：

- 全部 `bash` fenced blocks 经 `zsh -n`：exit 0；
- §5 Python 机器验货正文经 `compile(..., mode="exec")`：exit 0；
- `git diff --check`：exit 0；
- `uv run pytest -q tests/test_beam_adapter.py tests/test_beam_registered_prediction.py
  tests/test_lightmem_adapter.py tests/test_method_registry.py
  tests/test_artifact_evaluation_runner.py tests/test_documentation_standards.py`：
  `265 passed, 1 warning in 23.79s`。唯一 warning 是 vendored LightMem 的既有 Pydantic V2
  deprecation，与本命令包无关。

这些自检证明 CLI/adapter/evaluator/文档契约当前一致，不代替用户真实 API run 与其后的
artifact 开箱。

## 8. 真实执行、R1 验货勘误与开箱判词（2026-07-19）

用户已按本包执行 100K W2 与 10M W1 的两组 predict、Recall、rubric judge。六段命令均成功；
R0 机器门随后在旧断言处报：

```text
KeyError: 'provenance_granularity'
```

这是**验货器错误，不是 artifact 缺字段**。`answer_prompts.prediction.jsonl` 的
`metadata` 由 benchmark answer builder 所有，只含 `prompt_track / answer_prompt_profile /
official_source`；逐题检索资格的公共权威字段是同一 record 顶层 `retrieval_evidence`。
production writer 也明确把 `retrieval.metadata` 与 `_retrieval_evidence_payload(...)` 分开落盘。
R0 把 HaluMem/历史局部 metadata 形状误当成所有 benchmark 必须复制的公共契约，违反单事实源。
本 note 已删除该重复断言；**不改 production，不重跑任何付费 predict/evaluate**。

架构师直接对既有两个 run 执行 R1 机器门，尾行原文：

```text
PASS lm-beam-v7-pair-r1q1-c2-w2-100k: conversations=2, workers=2, ltm={'1': 1, '2': 1}, retrieved={'1': 1, '2': 1}, memory_build_llm={'2': 1, '1': 1}, build_embeddings={'2': 1, '1': 1}, retrieval_embeddings=2, recall=N/A, judge_rows=2, state={'1': {'worker_0'}, '2': {'worker_1'}}
PASS lm-beam-v7-pair-r1q1-w1-10m: conversations=1, workers=1, ltm={'1': 3}, retrieved={'1': 3}, memory_build_llm={'1': 1}, build_embeddings={'1': 3}, retrieval_embeddings=1, recall=N/A, judge_rows=1, state={'1': {'run'}}
PASS LightMem×BEAM current-v7 B11 machine gate: total_ltm=5, total_build_embeddings=5
```

逐层开箱确认：manifest identity、100K/10M source lock、pair crop、三道公开问题、product ISO
readout、5 条 pair-lineage LTM、2+1 retrieval embedding、2+1 memory-build LLM、W2 worker
物理隔离、Recall 全 N/A 与 rubric score/official-int 双字段均成立；terminal logs 无 traceback /
timeout / rate-limit。

同时发现一条与 BEAM 分数、LightMem build 无关的**共享 runner 缺口**：
`_run_artifact_level_evaluation()` 没有执行普通逐题路径已有的 evaluator collector/scope/store，
所以 rubric judge 虽已真实调用并落分，却没有
`model_inventory.beam_rubric_judge.json` / `efficiency_observations.beam_rubric_judge.jsonl`。
HaluMem extraction/update/qa 走同一路径，也会受影响。当前裁决：

```text
BEAM_CORE_ARTIFACTS_PASSED__JUDGE_OBSERVABILITY_REPAIR_PENDING
```

prediction、Recall、Qdrant 与已有 judge score 均无需重跑；共享修复合入后，只需在既有两组 run
上重跑共三道 rubric judge 以补 metric-side efficiency artifacts。修复边界见
`../../../evaluator-observability/README.md`，不得把它误修成 BEAM/LightMem 专用分支。

## 9. 共享修复后的 judge-only 补观测（2026-07-19）

共享修复已由架构师以主树 `174bd46` 强验收关闭。以下命令**不重跑 predict、Recall、
LightMem build 或 Qdrant state**；只对既有 100K 两题与 10M 一题重跑 rubric evaluator。
当前三题均为 `abstention` 且各只有一个 rubric item，因此本批预期恰好 3 次真实 judge LLM
调用；该数字来自既有 score artifact 的实际 `ability/rubric_count`，不是用问题数猜一般 BEAM
调用成本。若以后样本含多个 rubric item 或 event-ordering，真实调用数会更大，必须以
observation 为准。

在一个新的 zsh 中整段执行：

```bash
cd /Users/wz/Desktop/memoryBenchmark
set -o pipefail

git status --short
git diff --quiet
git diff --cached --quiet
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -f .env

BEAM100_RUN=lm-beam-v7-pair-r1q1-c2-w2-100k
BEAM100_ROOT=outputs/runs/lightmem/beam/100k/smoke/unified
BEAM10_RUN=lm-beam-v7-pair-r1q1-w1-10m
BEAM10_ROOT=outputs/runs/lightmem/beam/10m/smoke/unified

test -f "$BEAM100_ROOT/$BEAM100_RUN/manifest.json"
test -f "$BEAM10_ROOT/$BEAM10_RUN/manifest.json"
test ! -e "$BEAM100_ROOT/$BEAM100_RUN/artifacts/model_inventory.beam_rubric_judge.json"
test ! -e "$BEAM100_ROOT/$BEAM100_RUN/artifacts/efficiency_observations.beam_rubric_judge.jsonl"
test ! -e "$BEAM10_ROOT/$BEAM10_RUN/artifacts/model_inventory.beam_rubric_judge.json"
test ! -e "$BEAM10_ROOT/$BEAM10_RUN/artifacts/efficiency_observations.beam_rubric_judge.jsonl"

uv run memory-benchmark evaluate \
  --root . \
  --run-id "$BEAM100_RUN" \
  --metric beam-rubric-judge \
  --judge-profile compact \
  --workers 2 \
  --allow-api \
  2>&1 | tee "$BEAM100_ROOT/$BEAM100_RUN/logs/terminal.evaluate-judge-observability-refill.log"
BEAM100_JUDGE_STATUS=$?
test "$BEAM100_JUDGE_STATUS" -eq 0

uv run memory-benchmark evaluate \
  --root . \
  --run-id "$BEAM10_RUN" \
  --metric beam-rubric-judge \
  --judge-profile compact \
  --workers 1 \
  --allow-api \
  2>&1 | tee "$BEAM10_ROOT/$BEAM10_RUN/logs/terminal.evaluate-judge-observability-refill.log"
BEAM10_JUDGE_STATUS=$?
test "$BEAM10_JUDGE_STATUS" -eq 0
```

两条 evaluate 均为 exit 0 后执行零 API 机器门：

```bash
uv run python - <<'PY'
from __future__ import annotations

import json
from pathlib import Path


RUNS = (
    (
        Path("outputs/runs/lightmem/beam/100k/smoke/unified")
        / "lm-beam-v7-pair-r1q1-c2-w2-100k",
        2,
    ),
    (
        Path("outputs/runs/lightmem/beam/10m/smoke/unified")
        / "lm-beam-v7-pair-r1q1-w1-10m",
        1,
    ),
)


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


for run_dir, expected_calls in RUNS:
    artifacts = run_dir / "artifacts"
    summaries = run_dir / "summaries"
    inventory = json.loads(
        (artifacts / "model_inventory.beam_rubric_judge.json").read_text(
            encoding="utf-8"
        )
    )
    observations = read_jsonl(
        artifacts / "efficiency_observations.beam_rubric_judge.jsonl"
    )
    scores = read_jsonl(artifacts / "answer_scores.beam_rubric_judge.jsonl")
    summary = json.loads(
        (summaries / "summary.beam_rubric_judge.json").read_text(encoding="utf-8")
    )

    assert inventory["schema_version"] == 1
    assert len(inventory["models"]) == 1
    model = inventory["models"][0]
    assert model["model_id"] == "judge-llm"
    assert model["model_name"] == "gpt-4o-mini"
    assert model["model_role"] == "judge_llm"
    assert model["execution_mode"] == "api"

    assert len(scores) == expected_calls
    assert all(row["ability"] == "abstention" for row in scores)
    assert all(row["rubric_count"] == 1 for row in scores)
    assert len(observations) == expected_calls
    assert len({row["observation_id"] for row in observations}) == expected_calls

    score_scopes = {
        (row["conversation_id"], row["question_id"])
        for row in scores
    }
    observation_scopes = {
        (row["conversation_id"], row["question_id"])
        for row in observations
    }
    assert observation_scopes == score_scopes
    for row in observations:
        assert row["observation_type"] == "llm_call"
        assert row["stage"] == "judge"
        assert row["model_id"] == "judge-llm"
        assert row["token_measurement_source"] == "api_usage"
        assert isinstance(row["input_tokens"], int) and row["input_tokens"] >= 0
        assert isinstance(row["output_tokens"], int) and row["output_tokens"] >= 0

    assert "efficiency_observations" not in summary
    assert all("efficiency_observations" not in row for row in scores)
    print(
        f"PASS {run_dir.name}: judge_calls={len(observations)}, "
        f"scopes={sorted(observation_scopes)}"
    )

print("BEAM_JUDGE_OBSERVABILITY_REFILL_PASSED")
PY
```

本节通过后，BEAM current-v7 的 B7/B11 才能从“core passed”升为完整通过；随后生成并执行
LightMem × HaluMem Medium W1 命令包。若任一命令失败，保留新 refill log 与现有 run，不删除、
不重跑 predict，交回架构师开箱。
