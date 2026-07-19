# LightMem × MemBench current-v7 pair B11 命令包

> 状态：**2026-07-19 两个 run 已执行，R1 机器验货修正后经架构师 artifact 开箱通过；
> 本格=`REAL_SMOKE_PASSED`。**本页只认证 `0_10k` 的 current-v7 主配置、pair 投递、
> 单/双 worker、三项适用离线指标与 artifact 链。不代表 100k、full、效果、成本、resume
> 或 LightMem 整体 frozen。原验货器的目录名误判与修正版原样输出见 §7。

## 1. 已裁规模与 run 身份

MemBench 的 `--conversations 1` 是**每个 source 取一条 trajectory**。默认不传
`--membench-sources` 时同时选择 FirstHigh、FirstLow、ThirdHigh、ThirdLow，所以每个 run
实际包含 4 conversations / 4 questions：

| 角色 | CLI base run id | artifact child run id | 规模 |
|---|---|---|---|
| W1 | `lm-membench-v7-pair-r1q1-ps1-w1` | `lm-membench-v7-pair-r1q1-ps1-w1-0-10k` | 4 sources × 每源 1 conversation × 1 round × 1 question × 1 worker |
| W2 | `lm-membench-v7-pair-r1q1-ps1-w2` | `lm-membench-v7-pair-r1q1-ps1-w2-0-10k` | 同样 4 conversations，2 workers |

`ps1` 表示 per-source limit=1。W2 不把 `--conversations` 改成 2；否则会变成 8 个
conversations，无助于本轮并发门却把付费量翻倍。两个 predict 必须串行执行；不得另开两个
shell 同时跑。smoke 不测 resume，失败后保留目录与日志并停下交回架构师。

## 2. 一次性环境门

在一个新的 zsh 中整段执行，后续命令继续使用同一 shell：

```bash
cd /Users/wz/Desktop/memoryBenchmark
set -o pipefail

git status --short
git log -5 --oneline
git diff --quiet
git diff --cached --quiet
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -f .env
test -d data/membench/Membenchdata/data2test/0-10k
test -d models/all-MiniLM-L6-v2
test -d models/llmlingua-2-bert-base-multilingual-cased-meetingbank

MB_BASE_W1=lm-membench-v7-pair-r1q1-ps1-w1
MB_BASE_W2=lm-membench-v7-pair-r1q1-ps1-w2
MB_RUN_W1=${MB_BASE_W1}-0-10k
MB_RUN_W2=${MB_BASE_W2}-0-10k
MB_ROOT=outputs/runs/lightmem/membench/0-10k/smoke/unified
TMP_LOG_ROOT="${TMPDIR:-/tmp}/memory-benchmark-lightmem-membench-b11"

test ! -e "$MB_ROOT/$MB_RUN_W1"
test ! -e "$MB_ROOT/$MB_RUN_W2"
mkdir -p "$TMP_LOG_ROOT"
```

`git status --short` 可以显示 OWNER 已有的 untracked 私有资产；真正的 tracked-source clean 门是
两条 `git diff --quiet`。不得打印或 `cat .env`。

## 3. W1：四源、单 worker

```bash
uv run memory-benchmark predict smoke \
  --root . \
  --method lightmem \
  --benchmark membench \
  --variant 0_10k \
  --config-track unified \
  --run-id "$MB_BASE_W1" \
  --rounds 1 \
  --conversations 1 \
  --questions-per-conversation 1 \
  --workers 1 \
  --allow-api \
  2>&1 | tee "$TMP_LOG_ROOT/$MB_RUN_W1.predict.log"
PREDICT_STATUS=$?
mkdir -p "$MB_ROOT/$MB_RUN_W1/logs"
mv "$TMP_LOG_ROOT/$MB_RUN_W1.predict.log" \
  "$MB_ROOT/$MB_RUN_W1/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0

uv run memory-benchmark evaluate \
  --root . \
  --run-id "$MB_RUN_W1" \
  --metric membench-choice-accuracy \
  --metric membench-source-accuracy \
  --metric membench-recall \
  --workers 1 \
  2>&1 | tee "$MB_ROOT/$MB_RUN_W1/logs/terminal.evaluate-offline.log"
EVALUATE_STATUS=$?
test "$EVALUATE_STATUS" -eq 0
```

三项 evaluator 都是 artifact-only、零 API；`source-accuracy` 依赖先生成的
`choice-accuracy` artifact，所以顺序不可交换。MemBench 没有当前适用的 LLM judge；自由文本
F1/EM 也不适用于 A-D 选择题，本轮不强加。

## 4. W2：四源、双 worker

只有 W1 两段都 exit 0 后继续：

```bash
uv run memory-benchmark predict smoke \
  --root . \
  --method lightmem \
  --benchmark membench \
  --variant 0_10k \
  --config-track unified \
  --run-id "$MB_BASE_W2" \
  --rounds 1 \
  --conversations 1 \
  --questions-per-conversation 1 \
  --workers 2 \
  --allow-api \
  2>&1 | tee "$TMP_LOG_ROOT/$MB_RUN_W2.predict.log"
PREDICT_STATUS=$?
mkdir -p "$MB_ROOT/$MB_RUN_W2/logs"
mv "$TMP_LOG_ROOT/$MB_RUN_W2.predict.log" \
  "$MB_ROOT/$MB_RUN_W2/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0

uv run memory-benchmark evaluate \
  --root . \
  --run-id "$MB_RUN_W2" \
  --metric membench-choice-accuracy \
  --metric membench-source-accuracy \
  --metric membench-recall \
  --workers 1 \
  2>&1 | tee "$MB_ROOT/$MB_RUN_W2/logs/terminal.evaluate-offline.log"
EVALUATE_STATUS=$?
test "$EVALUATE_STATUS" -eq 0
```

离线 evaluator 保持单 worker；W2 的认证对象是 predict 阶段真实 method state 隔离，不靠给飞快的
本地算分再加并发制造噪声。

## 5. 两个 run 的机器验货（零 API）

四段命令全部成功后执行。它不要求答案正确或分数高；它验证 current identity、四源规模、官方
question-time builder、product readout、逐题 retrieval evidence、三项 metric、embedding
observation、First/Third lineage 与 worker state。若末尾因某类真实抽取没有形成持久化 payload
而失败，保留现场交回架构师，不删除 run 重试。

```bash
uv run python - <<'PY'
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from qdrant_client import QdrantClient
from memory_benchmark.methods.lightmem_adapter import _storage_safe_collection_name
from memory_benchmark.runners.event_stream import default_isolation_key


ISO_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\s")
SENTINEL = "(No relevant memories found)"
EXPECTED_CELLS = {"first-high", "first-low", "third-high", "third-low"}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def qdrant_payloads(
    run_dir: Path,
    *,
    expected_workers: int,
    conversation_ids: set[str],
) -> tuple[dict[str, list[dict]], dict[str, set[str]]]:
    state_root = run_dir / "method_state"
    worker_dirs = sorted(state_root.glob("worker_*"))
    if expected_workers == 1:
        assert worker_dirs == [], (run_dir, worker_dirs)
        roots = (("run", state_root / "qdrant"),)
    else:
        assert [path.name for path in worker_dirs] == ["worker_0", "worker_1"]
        roots = tuple((path.name, path / "qdrant") for path in worker_dirs)

    payloads_by_conversation = {key: [] for key in conversation_ids}
    locations: dict[str, set[str]] = defaultdict(set)
    database_to_conversation = {
        _storage_safe_collection_name(
            default_isolation_key(run_dir.name, conversation_id)
        ): conversation_id
        for conversation_id in conversation_ids
    }
    assert len(database_to_conversation) == len(conversation_ids)
    for location, root in roots:
        assert root.is_dir() and any(root.iterdir()), root
        databases = [
            path
            for path in sorted(root.iterdir())
            if path.is_dir()
            and not path.name.endswith("_summary")
            and (path / "collection").is_dir()
        ]
        for database in databases:
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
                    payloads_by_conversation[conversation_id].extend(
                        point.payload or {} for point in points
                    )
            finally:
                client.close()
    assert set(locations) == conversation_ids, (run_dir, locations, conversation_ids)
    assert all(len(value) == 1 for value in locations.values()), locations
    return payloads_by_conversation, locations


cases = (
    ("lm-membench-v7-pair-r1q1-ps1-w1-0-10k", 1),
    ("lm-membench-v7-pair-r1q1-ps1-w2-0-10k", 2),
)
root = Path("outputs/runs/lightmem/membench/0-10k/smoke/unified")
all_iso_hits = 0
all_first_pair_lineage = 0
all_third_singleton_lineage = 0
all_build_calls = 0

for run_id, expected_workers in cases:
    run_dir = root / run_id
    manifest = read_json(run_dir / "manifest.json")
    method = manifest["method"]
    config = method["config"]
    reader = method["answer_reader"]
    assert manifest["run_id"] == run_id
    assert manifest["benchmark_name"] == "membench"
    assert manifest["benchmark_variant"] == "0_10k"
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
    assert reader["answer_parameters"] == {
        "message_role": "user",
        "temperature": 0.0,
        "max_tokens": None,
        "top_p": None,
        "timeout_seconds": 60.0,
        "max_retries": 8,
    }

    summary = read_json(run_dir / "summaries/summary.json")
    progress = read_json(run_dir / "checkpoints/progress.json")
    assert summary["total_conversations"] == 4
    assert summary["completed_conversations"] == 4
    assert summary["total_questions"] == 4
    assert summary["completed_questions"] == 4
    assert progress["stage"] == "Completed"
    assert progress["conversation_completed"] == 4
    assert progress["question_completed"] == 4

    public = read_jsonl(run_dir / "artifacts/public_questions.jsonl")
    predictions = read_jsonl(run_dir / "artifacts/method_predictions.jsonl")
    answers = read_jsonl(run_dir / "artifacts/answer_prompts.prediction.jsonl")
    private = read_jsonl(run_dir / "artifacts/evaluator_private_labels.jsonl")
    assert len(public) == len(predictions) == len(answers) == len(private) == 4
    question_ids = {row["question_id"] for row in public}
    assert question_ids == {row["question_id"] for row in predictions}
    assert question_ids == {row["question_id"] for row in answers}
    assert question_ids == {row["question_id"] for row in private}
    conversation_ids = {row["conversation_id"] for row in public}
    cells = {"-".join(cid.split("-", 2)[:2]) for cid in conversation_ids}
    assert cells == EXPECTED_CELLS, cells

    public_by_id = {row["question_id"]: row for row in public}
    parse_statuses = Counter()
    for row in predictions:
        assert row["metadata"]["answer_prompt_profile"] == (
            "membench_instruction_first_v1"
        )
        parse_statuses[row["metadata"]["choice_parse_status"]] += 1
    for row in answers:
        public_row = public_by_id[row["question_id"]]
        question_time = public_row["question_time"]
        assert isinstance(question_time, str) and question_time
        assert f"(current time is {question_time})" in row["answer_prompt"]
        assert "Choices:\nA. " in row["answer_prompt"]
        assert row["formatted_memory"] in row["answer_prompt"]
        assert row["metadata"]["answer_context"] == row["formatted_memory"]
        assert row["metadata"]["answer_prompt_profile"] == (
            "membench_instruction_first_v1"
        )
        assert row["retrieval_query_top_k"] == 10
        assert isinstance(row["retrieved_items"], list)
        evidence = row["retrieval_evidence"]
        assert evidence["semantic_provenance"]["status"] == "valid"
        assert evidence["provenance_granularity"] == "turn"
        assert evidence["stable_ranking"]["status"] == "pending"
        assert row["metadata"]["provenance_granularity"] == "turn"
        if row["retrieved_items"]:
            assert row["formatted_memory"] == "\n".join(
                item["content"] for item in row["retrieved_items"]
            )
            iso_items = [
                item for item in row["retrieved_items"]
                if ISO_PREFIX.match(item["content"])
            ]
            assert len(iso_items) == len(row["retrieved_items"]), row["question_id"]
            all_iso_hits += len(iso_items)
        else:
            assert row["formatted_memory"] == SENTINEL
        assert "[Memory recorded on:" not in row["formatted_memory"]

    choice = read_json(run_dir / "summaries/summary.membench_choice_accuracy.json")
    source = read_json(run_dir / "summaries/summary.membench_source_accuracy.json")
    recall = read_json(run_dir / "summaries/summary.membench_recall.json")
    assert choice["total_questions"] == 4
    assert isinstance(choice["mean_score"], (int, float))
    assert source["total_questions"] == 4
    assert source["source_cell_order"] == [
        "first-high", "first-low", "third-high", "third-low"
    ]
    assert [row["question_count"] for row in source["source_breakdown"][:4]] == [
        1, 1, 1, 1
    ]
    assert recall["total_questions"] == 4
    assert recall["status"] == "ok"
    assert recall["scored_question_count"] == 4
    assert recall["provenance_granularity"] == "turn"
    assert recall["score_status_counts"] == {"ok": 4}
    assert recall["aggregation_contract_version"] == "retrieval-summary-v2"

    inventory = read_json(run_dir / "artifacts/model_inventory.prediction.json")
    assert {model["model_id"] for model in inventory["models"]} == {
        "gpt-4o-mini", "lightmem-embedding", "lightmem-memory-llm"
    }
    observations = read_jsonl(
        run_dir / "artifacts/efficiency_observations.prediction.jsonl"
    )
    embeds = [row for row in observations if row["observation_type"] == "embedding_call"]
    build_embeds = [row for row in embeds if row["stage"] == "memory_build"]
    retrieval_embeds = [row for row in embeds if row["stage"] == "retrieval"]
    assert question_ids <= {row["question_id"] for row in retrieval_embeds}
    for row in embeds:
        assert row["model_id"] == "lightmem-embedding"
        assert row["input_tokens"] > 0
        assert row["latency_ms"] >= 0
        assert row["token_measurement_source"] == "tokenizer_estimate"
        assert row["latency_measurement_source"] == "framework_timer"

    payloads_by_conversation, locations = qdrant_payloads(
        run_dir,
        expected_workers=expected_workers,
        conversation_ids=conversation_ids,
    )
    persisted_counts = {
        cid: len(payloads) for cid, payloads in payloads_by_conversation.items()
    }
    build_counts = Counter(row["conversation_id"] for row in build_embeds)
    for cid, persisted_count in persisted_counts.items():
        if persisted_count:
            assert build_counts[cid] >= persisted_count, (
                run_id, cid, persisted_count, build_counts[cid]
            )
        for payload in payloads_by_conversation[cid]:
            ids = payload.get("source_external_ids")
            assert isinstance(ids, list) and ids, (cid, payload)
            if cid.startswith("first-") and (
                any(str(value).endswith(":user") for value in ids)
                and any(str(value).endswith(":assistant") for value in ids)
            ):
                all_first_pair_lineage += 1
            if cid.startswith("third-") and len(set(ids)) == 1:
                all_third_singleton_lineage += 1

    all_build_calls += len(build_embeds)
    for terminal_name in ("terminal.predict.log", "terminal.evaluate-offline.log"):
        assert (run_dir / "logs" / terminal_name).is_file()
    print(
        f"PASS {run_id}: parse={dict(parse_statuses)}, "
        f"ltm={persisted_counts}, build_embeds={dict(build_counts)}, "
        f"retrieval_embeds={len(retrieval_embeds)}, locations={dict(locations)}"
    )

assert all_iso_hits > 0, "two MemBench runs had no retrieved ISO product readout"
assert all_first_pair_lineage > 0, "no persisted FirstAgent real-pair lineage"
assert all_third_singleton_lineage > 0, "no persisted ThirdAgent singleton lineage"
assert all_build_calls > 0, "two MemBench runs made no observed build embedding call"
print(
    "PASS ALL LightMem×MemBench B11: "
    f"iso_hits={all_iso_hits}, first_pair_lineage={all_first_pair_lineage}, "
    f"third_singleton_lineage={all_third_singleton_lineage}, "
    f"build_embedding_calls={all_build_calls}"
)
PY
```

## 6. 回收门

用户执行后把机器验货的完整输出交回架构师。只有架构师亲读两个 run 的 manifest、四类
artifact、三项 summary、raw/overall efficiency、terminal log 与 Qdrant state 后，本格才能从
`READY_FOR_B11_SMOKE` 改为 `REAL_SMOKE_PASSED`。分数高低不作为 smoke 通过条件；结构、隐私、
身份、隔离或观测缺失则是硬失败。

## 7. R1：Qdrant 目录身份修正与架构师开箱判词

### 7.1 原验货器为何误报

用户完成两个 predict 与三项 evaluator 后，R0 验货器在第一个 W1 Qdrant database 报：

```text
AssertionError: (PosixPath('.../lightmem_lm-membench-v7-pair-r1q1-ps1-w1-0-10k_first-high-highlevel-movie_3ba7e0e943'), [])
```

run 没有丢 `conversation_id=-0`。生产路径先构造完整 isolation key
`default_isolation_key(run_id, conversation_id)`，再由
`_storage_safe_collection_name()` 把可读部分截为 64 字符并追加完整 isolation key 的 SHA-1
前 10 位。FirstHigh 的 key 较长，因此目录可读前缀恰好在 `movie-0` 的 `-0` 之前截断；R0
用 `f"_{conversation_id}_" in database.name` 反推身份，错误地把有损前缀当成完整身份字段。

R1 改为用生产侧同一对 helper 为每个 `(run_id, conversation_id)` 计算**完整预期 database
name**，再做一对一映射；稳定 hash 参与匹配，不做模糊前缀猜测。这只修本文零 API验货器，
不改 production、run 或 artifact，也不需要重跑任何 API。

### 7.2 修正后机器验货原样输出

```text
PASS lm-membench-v7-pair-r1q1-ps1-w1-0-10k: parse={'parsed': 4}, ltm={'first-high-highlevel-movie-0': 3, 'third-low-simple-roles-0': 4, 'first-low-simple-roles-0': 1, 'third-high-highlevel-movie-0': 4}, build_embeds={'first-low-simple-roles-0': 1, 'third-high-highlevel-movie-0': 4, 'first-high-highlevel-movie-0': 3, 'third-low-simple-roles-0': 4}, retrieval_embeds=4, locations={'first-high-highlevel-movie-0': {'run'}, 'first-low-simple-roles-0': {'run'}, 'third-high-highlevel-movie-0': {'run'}, 'third-low-simple-roles-0': {'run'}}
PASS lm-membench-v7-pair-r1q1-ps1-w2-0-10k: parse={'parsed': 3, 'invalid_choice': 1}, ltm={'first-high-highlevel-movie-0': 3, 'third-low-simple-roles-0': 4, 'first-low-simple-roles-0': 2, 'third-high-highlevel-movie-0': 4}, build_embeds={'first-high-highlevel-movie-0': 3, 'third-high-highlevel-movie-0': 4, 'third-low-simple-roles-0': 4, 'first-low-simple-roles-0': 2}, retrieval_embeds=4, locations={'first-high-highlevel-movie-0': {'worker_0'}, 'third-high-highlevel-movie-0': {'worker_0'}, 'first-low-simple-roles-0': {'worker_1'}, 'third-low-simple-roles-0': {'worker_1'}}
PASS ALL LightMem×MemBench B11: iso_hits=25, first_pair_lineage=9, third_singleton_lineage=16, build_embedding_calls=25
```

### 7.3 artifact 开箱

- 两个 run 都是 4/4 conversations、4/4 questions、checkpoint `Completed`；manifest 为
  `conversation-qa-v7`、`consume_granularity=pair`、`hybrid`、`online_soft`、
  `preserve_none`、unified builder、RetrievalEvidence v1；
- W1 state 在 run 级 Qdrant，四个 conversation 各一套 database；W2 中 FirstHigh/ThirdHigh
  只在 `worker_0`，FirstLow/ThirdLow 只在 `worker_1`，无跨 worker collection；
- 25 条持久化 LTM 与 25 次 memory-build embedding observation 对齐；8 道 query 的 retrieval
  embedding 全齐。readout 共 25 个 item，全部保留完整 ISO timestamp；
- FirstAgent 实见 9 条同时含 `:user`/`:assistant` 的双 child lineage；ThirdAgent 实见 16 条
  去重后单 child lineage，证明真实 pair 与 singleton+placeholder 两条路径均落库；
- 两个 run 的 choice/source accuracy 都是 0.5，MemBench Recall 都是 1/6，四题均
  `status=ok/provenance_granularity=turn`，summary contract=`retrieval-summary-v2`；这些分数只作
  artifact 完整性证据，不是效果结论；
- W2 的一条 `invalid_choice` 原始回答是“没有关于 niece company 的信息”。该 smoke 只保留
  FirstLow 第 1 个 source step，而该题 gold target 是 step 119；检索 Recall 正确为 0，模型
  没有瞎猜 A-D，parser 也正确落 `invalid_choice`/0 分。W1 同题随机猜 A 但同样计错。两次 prompt
  均含公开 question time 与四个 choices，因此这不是 builder/parser/并发故障；
- terminal/run/method/event logs 无 traceback、exception、timeout 或失败 conversation。文本
  `retry_failed_conversations=false` 不是错误事件。

**架构师裁决：LightMem × MemBench current-v7 `0_10k` 单/双 worker B11 通过，格子升为
`REAL_SMOKE_PASSED`。**仍不外推 100k、full、效果、成本、resume、stable ranking，也不使
LightMem 整体 frozen；下一格按既定顺序进入 BEAM 异常/接口预检。
