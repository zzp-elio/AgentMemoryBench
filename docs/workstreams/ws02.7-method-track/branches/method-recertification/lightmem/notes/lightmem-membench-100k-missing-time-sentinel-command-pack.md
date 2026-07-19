# LightMem × MemBench 100k 缺失时间真实哨兵命令包

> 状态（2026-07-19 R4 勘误）：**旧 source identity 的 R3 run 曾按当时源码通过；forced-flush
> 修复后的 exact-smoke reachability 证明 ThirdHigh final add 正好命中 automatic+tail，旧实现
> 实际漏掉 step 1，因此“不需要重跑”已被 supersede。当前必须用新 run id 最小补跑同一
> FirstHigh+ThirdHigh W1 哨兵；预算/run id 待用户再次确认。**本哨兵不阻塞
> LightMem × BEAM；它只补 `100k` 独有的真实 `time=None` 组合路径，不重复已经通过的
> `0_10k` 单/双 worker B11，也不代表 100k full、效果、成本或 resume 认证。

## 0. R0 参数门事故与无损续跑

用户于 2026-07-19 按本文执行首轮 predict，CLI 在任何 provider/API/backend 构造前报：

```text
Error: --membench-sources is only supported for MemBench smoke
```

命令没有把 benchmark 写错。根因是
`cli/main.py::_validate_smoke_axis_args()` 已进入 `benchmark == "membench"` 分支，却调用
`_validate_membench_sources(args.membench_sources)` 时漏传 `is_membench=True`；后面的正常化层
本来传对了该参数，但永远到不了。R1 必须同时保留“非 MemBench 显式传入会拒绝”的负例，并
新增“MemBench 显式两源会进入 command service”的正例，不能删校验绕过。

失败目录里现场确认只有 `logs/terminal.predict.log`；没有 manifest、checkpoint、Qdrant、
artifact 或 API 结果。R1 合入后先把它**非破坏性归档**，再复用原 run id：

```bash
cd /Users/wz/Desktop/memoryBenchmark

MB100_BASE=lm-membench-v7-none100k-fh-th-r1q1-w1
MB100_RUN=${MB100_BASE}-100k
MB100_ROOT=outputs/runs/lightmem/membench/100k/smoke/unified
FAILED_DIR="$MB100_ROOT/$MB100_RUN"
FAILED_ARCHIVE="$MB100_ROOT/${MB100_RUN}.failed-cli-preflight-20260719"

test -f "$FAILED_DIR/logs/terminal.predict.log"
grep -F -- "--membench-sources is only supported for MemBench smoke" \
  "$FAILED_DIR/logs/terminal.predict.log"
test ! -e "$FAILED_ARCHIVE"
mv "$FAILED_DIR" "$FAILED_ARCHIVE"
test ! -e "$FAILED_DIR"
```

这不是 resume：R0 根本没有可恢复的执行状态。归档后重新执行 §2 起的完整命令即可。

## 0.1 R1 source identity 门事故与无损续跑

`9bd2ab0` 让显式两源参数进入 command service 后，第二次 predict 又在 provider/API/backend
构造前报：

```text
Error: membench: prepared source_relative_paths do not match variant '100k'
```

命令与数据仍然没有写错。根因是 source filter 只接到了 MemBench adapter：adapter 按请求正确
返回 concrete `100k` variant 的两源有序子集，但 benchmark registration 仍把 adapter 返回值
硬等式比较为 variant 的四源全集。R2 没有删除 source-lock 校验，而是给 registration 增加显式
source resolver：静态 variant 继续声明四源全集；smoke 动态选择只能得到其中的有序非空子集；
adapter 返回路径、dataset metadata 与 fingerprint 必须与该选择精确一致；full 少源继续 fail-fast。

第二个失败目录也只含 `logs/terminal.predict.log`，没有 manifest、checkpoint、Qdrant、artifact
或 API 结果。保留 R0 归档，再把 R1 现场非破坏性归档：

```bash
cd /Users/wz/Desktop/memoryBenchmark

MB100_BASE=lm-membench-v7-none100k-fh-th-r1q1-w1
MB100_RUN=${MB100_BASE}-100k
MB100_ROOT=outputs/runs/lightmem/membench/100k/smoke/unified
FAILED_DIR="$MB100_ROOT/$MB100_RUN"
FAILED_ARCHIVE="$MB100_ROOT/${MB100_RUN}.failed-source-contract-preflight-20260719"

test -f "$FAILED_DIR/logs/terminal.predict.log"
grep -F -- "prepared source_relative_paths do not match variant '100k'" \
  "$FAILED_DIR/logs/terminal.predict.log"
test ! -e "$FAILED_ARCHIVE"
mv "$FAILED_DIR" "$FAILED_ARCHIVE"
test ! -e "$FAILED_DIR"
test -d "$MB100_ROOT/${MB100_RUN}.failed-cli-preflight-20260719"
```

R2 的离线 registered regression 使用真实 registry、MemBench 100k 两源 adapter、prediction
runner、artifact 与 dataset fingerprint，只在 method/answer 边界换成 fake；它锁定 2
conversations、2 questions、4 canonical turns 与恰好两个 source fingerprints。故这次不是再用
CLI mock 证明“参数传到了下一层”，而是已经穿过本次失败的 identity 门。

## 1. 架构裁决与最小规模

旧预检曾因为 MemBench 错接为 `turn`，把“STM 是否跨两次 add 合并 FirstAgent 双侧”误判成
付费 blocker。R1 已把 LightMem × MemBench 改为 `pair`，所以那个 blocker 已被 supersede。

100k 仍有一个值得在最终 LightMem frozen 前关闭的**旁路覆盖缺口**：258,000/307,738 source
steps 没有 place/time marker，走的是 `turn_time=None → session_time=None → preserve_none`；既有
`0_10k` 真实 run 全部带时间，没有真实经过 “canonical 100k noise → LightMem normalizer →
extraction → zero-hit readout” 的组合。no-time 数据是官方 distractor，真实 extraction 合法输出
零 LTM 时不会进入 embedding/Qdrant insert；该持久化分支应由确定性、零 API 的官方
`offline_update → local Qdrant → retrieve` 强反例证明，不能要求模型从噪声制造假记忆。

不需要重跑四源 W1/W2。最小哨兵固定为：

| 轴 | 裁决 |
|---|---|
| variant | `100k` |
| sources | `first_high,third_high` |
| 每源 conversation | 1（各自文件内第一条，纯公开顺序选择） |
| rounds | 1 |
| questions | 1 |
| workers | 1；并发/隔离已由 0_10k W2 验收，不重复烧 |
| base run id | `lm-membench-v7-none100k-fh-th-r1q1-w1` |
| artifact run id | `lm-membench-v7-none100k-fh-th-r1q1-w1-100k` |

production adapter 零 API 现场确认该切片为：

```text
first-high-highlevel-movie-0: 1:user + 1:assistant，二者 turn_time/session_time 均 None
third-high-highlevel-movie-0: turn 1 + turn 2，二者 turn_time/session_time 均 None
```

FirstHigh 覆盖真实双边 pair；ThirdHigh 的两个连续 user 各自成为 singleton + structural
assistant placeholder。四条真实 content 都没有尾部 place/time marker，question time 只进入
answer builder，不能反灌 history。

本 smoke 不从 pair 数推算 LLM 调用/费用。真实 memory LLM、embedding、answer LLM 调用以
run 的 efficiency artifact 为准。

## 2. R2 合入后的环境门

规模与 run id 已获用户批准；确认 main 含 R2 后，在同一个新 zsh 中执行：

```bash
cd /Users/wz/Desktop/memoryBenchmark
set -o pipefail

git status --short
git log -5 --oneline
git diff --quiet
git diff --cached --quiet
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -f .env
test -d data/membench/Membenchdata/data2test/100k
test -d models/all-MiniLM-L6-v2
test -d models/llmlingua-2-bert-base-multilingual-cased-meetingbank

MB100_BASE=lm-membench-v7-none100k-fh-th-r1q1-w1
MB100_RUN=${MB100_BASE}-100k
MB100_ROOT=outputs/runs/lightmem/membench/100k/smoke/unified
TMP_LOG_ROOT="${TMPDIR:-/tmp}/memory-benchmark-lightmem-membench-100k-sentinel"

test ! -e "$MB100_ROOT/$MB100_RUN"
mkdir -p "$TMP_LOG_ROOT"
```

`git status --short` 可以显示 OWNER 既有 untracked 私有资产；tracked-source clean 门是两条
`git diff --quiet`。不得输出 `.env` 内容。

## 3. predict 与全部当前适用离线指标

```bash
uv run memory-benchmark predict smoke \
  --root . \
  --method lightmem \
  --benchmark membench \
  --variant 100k \
  --membench-sources first_high,third_high \
  --config-track unified \
  --run-id "$MB100_BASE" \
  --rounds 1 \
  --conversations 1 \
  --questions-per-conversation 1 \
  --workers 1 \
  --allow-api \
  2>&1 | tee "$TMP_LOG_ROOT/$MB100_RUN.predict.log"
PREDICT_STATUS=$?
mkdir -p "$MB100_ROOT/$MB100_RUN/logs"
mv "$TMP_LOG_ROOT/$MB100_RUN.predict.log" \
  "$MB100_ROOT/$MB100_RUN/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0

uv run memory-benchmark evaluate \
  --root . \
  --run-id "$MB100_RUN" \
  --metric membench-choice-accuracy \
  --metric membench-source-accuracy \
  --metric membench-recall \
  --workers 1 \
  2>&1 | tee "$MB100_ROOT/$MB100_RUN/logs/terminal.evaluate-offline.log"
EVALUATE_STATUS=$?
test "$EVALUATE_STATUS" -eq 0
```

三项 evaluator 都是 artifact-only、零 API。分数高低不决定 sentinel 是否通过；这里验证的是
缺时输入没有被造时间、丢角色、丢 lineage 或写坏 readout。

## 4. 单 run 机器验货（零 API）

no-time source 是官方 distractor，某个 conversation 没抽出任何 LTM 是合法甚至理想的算法
输出。脚本采用 actual-call-aware 两分支：有 LTM 时核真实 null payload/lineage/build embedding；
全零时核 memory-build LLM 确实消费了两个 no-time conversation、Qdrant collection 合法为空、
readout 为真实 zero-hit，null payload 的持久化改由零 API local-Qdrant 强反例承重。

```bash
uv run python - <<'PY'
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from qdrant_client import QdrantClient

from memory_benchmark.benchmark_adapters.contracts import BenchmarkLoadRequest, RunScope
from memory_benchmark.benchmark_adapters.membench import prepare_membench_run
from memory_benchmark.methods.lightmem_adapter import _storage_safe_collection_name
from memory_benchmark.runners.event_stream import default_isolation_key


RUN_ID = "lm-membench-v7-none100k-fh-th-r1q1-w1-100k"
RUN_DIR = Path("outputs/runs/lightmem/membench/100k/smoke/unified") / RUN_ID
EXPECTED_CONVERSATIONS = {
    "first-high-highlevel-movie-0",
    "third-high-highlevel-movie-0",
}
SENTINEL = "(No relevant memories found)"


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


# 先用同一 production adapter 复算选中切片，锁定它确实全是 source-time None。
prepared = prepare_membench_run(
    Path("."),
    BenchmarkLoadRequest(
        variant="100k",
        run_scope=RunScope.SMOKE,
        smoke_turn_limit=1,
        smoke_conversation_limit=1,
        membench_sources=("first_high", "third_high"),
    ),
)
assert {c.conversation_id for c in prepared.dataset.conversations} == EXPECTED_CONVERSATIONS
selected_turns = [
    turn
    for conversation in prepared.dataset.conversations
    for session in conversation.sessions
    for turn in session.turns
]
assert len(selected_turns) == 4
assert all(turn.turn_time is None for turn in selected_turns)
assert all(
    session.session_time is None
    for conversation in prepared.dataset.conversations
    for session in conversation.sessions
)
assert all(
    turn.metadata.get("source_timestamp_embedded_in_content") is False
    for turn in selected_turns
)

manifest = read_json(RUN_DIR / "manifest.json")
method = manifest["method"]
config = method["config"]
assert manifest["run_id"] == RUN_ID
assert manifest["benchmark_name"] == "membench"
assert manifest["benchmark_variant"] == "100k"
assert manifest["run_scope"] == "smoke"
assert manifest["policy"]["max_workers"] == 1
assert method["protocol_version"] == "v3"
assert method["consume_granularity"] == "pair"
assert method["prompt_track"] == "unified"
assert method["retrieval_evidence_contract_version"] == "v1"
assert config["adapter_version"] == "conversation-qa-v7"
assert config["messages_use"] == "hybrid"
assert config["lifecycle_profile"] == "online_soft"
assert config["missing_timestamp_policy"] == "preserve_none"

fingerprint = read_json(RUN_DIR / "artifacts/dataset_fingerprint.json")
assert fingerprint["conversation_count"] == 2
assert fingerprint["question_count"] == 2
source_names = {Path(row["path"]).name for row in fingerprint["source_paths"]}
assert source_names == {
    "FirstAgentDataHighLevel_multiple_100.json",
    "ThirdAgentDataHighLevel_multiple_100.json",
}

summary = read_json(RUN_DIR / "summaries/summary.json")
progress = read_json(RUN_DIR / "checkpoints/progress.json")
assert summary["total_conversations"] == summary["completed_conversations"] == 2
assert summary["total_questions"] == summary["completed_questions"] == 2
assert progress["stage"] == "Completed"

public = read_jsonl(RUN_DIR / "artifacts/public_questions.jsonl")
predictions = read_jsonl(RUN_DIR / "artifacts/method_predictions.jsonl")
answers = read_jsonl(RUN_DIR / "artifacts/answer_prompts.prediction.jsonl")
assert len(public) == len(predictions) == len(answers) == 2
assert {row["conversation_id"] for row in public} == EXPECTED_CONVERSATIONS
public_by_id = {row["question_id"]: row for row in public}
retrieved_by_conversation: Counter[str] = Counter()
for row in answers:
    question = public_by_id[row["question_id"]]
    assert f"(current time is {question['question_time']})" in row["answer_prompt"]
    assert row["formatted_memory"] in row["answer_prompt"]
    assert "None None" not in row["formatted_memory"]
    evidence = row["retrieval_evidence"]
    assert evidence["semantic_provenance"]["status"] == "valid"
    assert evidence["provenance_granularity"] == "turn"
    assert evidence["stable_ranking"]["status"] == "pending"
    if row["retrieved_items"]:
        assert row["formatted_memory"] == "\n".join(
            item["content"] for item in row["retrieved_items"]
        )
        assert all(item["timestamp"] is None for item in row["retrieved_items"])
        retrieved_by_conversation[row["conversation_id"]] += len(row["retrieved_items"])
    else:
        assert row["formatted_memory"] == SENTINEL

for metric in (
    "membench_choice_accuracy",
    "membench_source_accuracy",
    "membench_recall",
):
    metric_summary = read_json(RUN_DIR / "summaries" / f"summary.{metric}.json")
    assert metric_summary["total_questions"] == 2
recall = read_json(RUN_DIR / "summaries/summary.membench_recall.json")
assert recall["status"] == "ok"
assert recall["scored_question_count"] == 2
assert recall["score_status_counts"] == {"ok": 2}

# 单 worker 的真实 state 位于 run 级目录；按生产 helper 映射完整 identity，禁止猜截断前缀。
state_root = RUN_DIR / "method_state"
assert not list(state_root.glob("worker_*"))
qdrant_root = state_root / "qdrant"
expected_databases = {
    _storage_safe_collection_name(default_isolation_key(RUN_ID, cid)): cid
    for cid in EXPECTED_CONVERSATIONS
}
payloads: dict[str, list[dict]] = {cid: [] for cid in EXPECTED_CONVERSATIONS}
for database_name, conversation_id in expected_databases.items():
    database = qdrant_root / database_name
    assert (database / "collection").is_dir(), database
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
            payloads[conversation_id].extend(point.payload or {} for point in points)
    finally:
        client.close()

observations = read_jsonl(
    RUN_DIR / "artifacts/efficiency_observations.prediction.jsonl"
)
embeds = [row for row in observations if row["observation_type"] == "embedding_call"]
build = [row for row in embeds if row["stage"] == "memory_build"]
retrieval = [row for row in embeds if row["stage"] == "retrieval"]
memory_build_llm = [
    row
    for row in observations
    if row["observation_type"] == "llm_call" and row["stage"] == "memory_build"
]
assert len(retrieval) == 2
assert {row["question_id"] for row in retrieval} == {
    row["question_id"] for row in public
}
memory_build_llm_by_conversation = Counter(
    row["conversation_id"] for row in memory_build_llm
)
assert set(memory_build_llm_by_conversation) == EXPECTED_CONVERSATIONS
assert all(count >= 1 for count in memory_build_llm_by_conversation.values())
assert all(
    row["input_tokens"] > 0 and row["output_tokens"] > 0
    for row in memory_build_llm
)
assert all(row["model_id"] == "lightmem-embedding" for row in embeds)
assert all(row["input_tokens"] > 0 and row["latency_ms"] >= 0 for row in embeds)

persisted_count = sum(len(rows) for rows in payloads.values())
if persisted_count:
    for cid, rows in payloads.items():
        for payload in rows:
            assert payload.get("time_stamp") is None, (cid, payload)
            assert payload.get("float_time_stamp") is None, (cid, payload)
            assert payload.get("weekday") is None, (cid, payload)
            ids = payload.get("source_external_ids")
            assert isinstance(ids, list) and ids
            if cid.startswith("first-"):
                assert set(ids) == {"1:user", "1:assistant"}
            else:
                assert set(ids) in ({"1"}, {"2"})
    assert len(build) == persisted_count
    qdrant_write_status = "observed_null_payload"
else:
    assert not retrieved_by_conversation
    assert not build
    assert all(not row["retrieved_items"] for row in answers)
    qdrant_write_status = "n/a_zero_extraction_local_qdrant_regression"

for terminal_name in ("terminal.predict.log", "terminal.evaluate-offline.log"):
    assert (RUN_DIR / "logs" / terminal_name).is_file()

print(
    "PASS LightMem×MemBench 100k missing-time sentinel: "
    f"ltm={dict((cid, len(rows)) for cid, rows in payloads.items())}, "
    f"retrieved={dict(retrieved_by_conversation)}, "
    f"memory_build_llm_calls={dict(memory_build_llm_by_conversation)}, "
    f"build_embedding_calls={len(build)}, retrieval_embedding_calls={len(retrieval)}, "
    f"qdrant_write={qdrant_write_status}"
)
PY
```

## 5. 验收与状态边界

用户执行的真实 run 已完成；架构师须亲读 manifest、两个 answer artifact、Qdrant collection、
efficiency observations 与 terminal log。若真实 extraction 产生 LTM，机器门直接核 null payload；
若像本次一样对 distractor 合法输出零 LTM，则真实 run 承担 normalizer/extraction/zero-hit，
`tests/test_lightmem_adapter.py::test_lightmem_official_insert_roundtrips_null_time_through_local_qdrant`
承担官方 insert/local-Qdrant/readout。两层都通过后才能记为
`100K_MISSING_TIME_SENTINEL_PASSED_ZERO_EXTRACTION`；不得写成“真实 run 已持久化 null payload”。

它只关闭 framework-extended `preserve_none` 的真实组合覆盖，不把 upstream LightMem 宣称为
原生支持缺时，也不把 100k 长历史、效果、成本、full 或 resume 认证为通过。若 sentinel 尚未
执行，LoCoMo/LME/MemBench `0_10k` 的既有 `REAL_SMOKE_PASSED` 不降级；只是在 LightMem 最终
frozen 门保留一条明确待项。首版机器断言失败不要求重跑已经成功的真实 API run。

## 6. 2026-07-19 实际验收结果

真实 run：
`lm-membench-v7-none100k-fh-th-r1q1-w1-100k`。用户已经执行 predict 与全部既有免费
evaluator；架构师随后亲读 manifest、两个公开 answer、两座本地 Qdrant、prediction
efficiency observations、terminal log 与 evaluator summary，并在现有产物上运行 §4 的 R3
机器门。完整尾行：

```text
PASS LightMem×MemBench 100k missing-time sentinel: ltm={'third-high-highlevel-movie-0': 0, 'first-high-highlevel-movie-0': 0}, retrieved={}, memory_build_llm_calls={'third-high-highlevel-movie-0': 1, 'first-high-highlevel-movie-0': 1}, build_embedding_calls=0, retrieval_embedding_calls=2, qdrant_write=n/a_zero_extraction_local_qdrant_regression
```

当时裁决：**`100K_MISSING_TIME_SENTINEL_PASSED_ZERO_EXTRACTION`**。两个官方 no-time distractor
conversation 都实际进入 memory-build LLM，且各自合法地产生零 LTM；两个 query 仍各发生一次
retrieval embedding，公开 readout 为真实 zero-hit，没有伪造记忆。真实 run 因而没有经过
Qdrant insert；null timestamp 的持久化由同一 current source 上的确定性 local-Qdrant 回归承担，
不能表述成“真实 API run 已写入 null payload”。

## 7. R4 forced-flush reachability 勘误

`8879af9` 把 sensory runtime 纳入 source identity 后，架构师对旧 B11 exact crop 做了 production
registration + 本地 LLMLingua 零 API probe。ThirdHigh 两批压缩后分别为 438/361 sensory tokens，
第二个 final add 会先自动切出 step 1、再 forced cut step 2。真实 vendored chain 进一步记录到：

```text
cut_trace = [(automatic, step 1), (forced, step 2)]
fixed shortmem input = [step 1, step 2]
```

旧 `lightmem.py` 在该条件下以 forced tail 覆盖 automatic prefix，所以 R3 run 的 ThirdHigh
memory-build LLM 并没有看到完整 retained history；“两个 conversation 都有 memory-build 调用”
不足以证明每个 conversation 的所有 retained step 都进入 extraction。R3 的分层验货逻辑本身没有
伪造结果，但它缺少 segment-level reachability，判词据此降级为
`SUPERSEDED_BY_FORCED_FLUSH_SOURCE_IDENTITY`。

当前建议新 base run id：`lm-membench-v7-flush-r1-none100k-fh-th-r1q1-w1`，artifact run id 自动
为 `...-100k`。规模仍为 FirstHigh+ThirdHigh 各 1 conversation / 1 round / 1 question / W1；
不换样本、不追求非空 LTM。用户确认预算与 run id 后，复用 §3 的 predict/evaluate 结构，并把
§4 的 `RUN_ID` 改为新 id；另须在验货中核 current source hash=`a44d7d99…`。完整 reachability
证据见 [forced-flush note](lightmem-front-four-forced-flush-reachability.md)。
