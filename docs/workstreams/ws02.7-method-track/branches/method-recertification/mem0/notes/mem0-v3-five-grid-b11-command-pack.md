# Mem0 current-v3 五格 B11 真实 smoke 命令包

> 状态：**待用户执行**。命令生成基线为 `main@8344072`；该基线已经完成 Mem0 两张 R1
> 的 full-diff 强验收、主树全量 `1637 passed, 3 deselected, 2 warnings, 29 subtests
> passed` 与 `compileall exit 0`。本页只授权下列 8 个 run；不授权 full、resume、扩大题数、
> 删除失败现场或切换模型。全部真实 LLM 仍按项目政策使用 `gpt-4o-mini`。
>
> **R1（2026-07-20）**：首版 `d6cc492` 误称 LongMemEval 单题仍灌完整 haystack，并据此删去
> LME W2；用户在执行前拦下。current-main 注册层与零 API prepare 探针证明 `--rounds 1`
> 将每个 instance 裁为 2 turns。本版保留该勘误历史，并让四个非 HaluMem benchmark 各自
> 通过真实双 worker 门；首版命令已 superseded，禁止继续执行。

## 1. 八个 run：四个非 HaluMem benchmark 都有真实并行门

本轮认证五个 benchmark 的真实 build → retrieve → framework answer → evaluator 链。LoCoMo、
LongMemEval、MemBench、BEAM 的 canonical shape 与 Mem0 consume granularity 不同，因此四格各自
至少跑一次真实双 worker，不能拿另一格的并行证据代验；HaluMem 的 operation runner 按官方
交错测评契约固定 `workers=1`。

| benchmark | run | 规模与目的 |
|---|---|---|
| LoCoMo | `mem0-locomo-v3-r3q1-w1` | 1 conversation × 3 rounds × 1 question × 1 worker；覆盖非隔离路径、具名 speaker、逐 turn time 与首个 image caption |
| LoCoMo | `mem0-locomo-v3-r3q1-c2-w2` | 2 conversations × 3 rounds × 各 1 question × 2 workers；认证该格 turn ingest 的隔离并发 |
| LongMemEval | `mem0-lme-v3-r1q1-w1-s-cleaned` | S-cleaned 1 instance × **1 round=2 turns** × 1 question × 1 worker |
| LongMemEval | `mem0-lme-v3-r1q1-c2-w2-s-cleaned` | S-cleaned 2 instances × 各 **1 round=2 turns** × 各 1 question × 2 workers；认证 session ingest 的隔离并发 |
| MemBench | `mem0-membench-v3-r1q1-ps1-w2-0-10k` | 四 source 各 1 trajectory、共 4 questions、2 workers；同时覆盖 FirstAgent 双 child 与 ThirdAgent singleton |
| BEAM | `mem0-beam-v3-pair-r1q1-c2-w2-100k` | 100K 2 conversations、2 workers；覆盖标准 pair 与隔离并发 |
| BEAM | `mem0-beam-v3-pair-r1q1-w1-10m` | 10M 1 conversation、1 worker；保留不同 source shape 的真实入口 |
| HaluMem | `mem0-halumem-v3-r1-w1-medium` | Medium 固定 smoke：1 conversation、4 sessions、1 QA；边写边做 extraction/update/QA |

LongMemEval 的“一题”只裁 question 数，不负责裁历史；真正的历史门是 registered
`--rounds 1`。current-main `_build_longmemeval_smoke_dataset()` 会在每个 instance 全局只保留
前一个完整双 turn round。2026-07-20 零 API 现场探针：W1 的首条 raw 550 turns → retained 2；
W2 的两条 raw 550/485 turns → 各 retained 2。旧审计中“单题仍灌完整 haystack”的说法已被
current source、registered test 与该探针共同推翻，不得再用于预算判断。

MemBench 100K 的 missing-time 不另烧一轮：Mem0 对缺时没有 LightMem 那种第三方 normalizer 分支，
现行规则只是 `turn → session → None` 且不合成 header；R1 已用真实 adapter 强反例锁住。BEAM
10M 的两个已知 dangling 窗口也不靠首条付费 smoke 偶然命中，结构反例由零 API 生产事件流测试
承担；10M run 验的是该 variant 的真实装载、pair 通路和 rubric 接线。

所有 predict 必须串行执行。`workers=2` 指单条命令内部隔离并行，不得同时在两个 shell 启动
两条 predict。smoke 不支持 resume；失败时保留目录和 terminal log，停止并交回架构师。

## 2. 一次性环境门与 run 变量

在一个新的 zsh 中整段执行，后续继续使用同一 shell。`git status --short` 允许显示 OWNER 的
既有 untracked 私有资产；真正的 tracked-source 门是两条 `git diff --quiet`。

```bash
cd /Users/wz/Desktop/memoryBenchmark
set -o pipefail

git status --short
git log -5 --oneline
git diff --quiet
git diff --cached --quiet
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
git merge-base --is-ancestor 8344072 HEAD
test -f .env
test -f data/locomo/locomo10.json
test -f data/longmemeval/longmemeval_s_cleaned.json
test -d data/membench/Membenchdata/data2test/0-10k
test -d data/BEAM/beam_dataset/100K
test -d data/BEAM/beam_10M_dataset/10M
test -f data/halumem/HaluMem-Medium.jsonl
test -d models/all-MiniLM-L6-v2

LOCO_RUN_W1=mem0-locomo-v3-r3q1-w1
LOCO_RUN_W2=mem0-locomo-v3-r3q1-c2-w2
LOCO_ROOT=outputs/runs/mem0/locomo/smoke/unified

LME_BASE_W1=mem0-lme-v3-r1q1-w1
LME_BASE_W2=mem0-lme-v3-r1q1-c2-w2
LME_RUN_W1=${LME_BASE_W1}-s-cleaned
LME_RUN_W2=${LME_BASE_W2}-s-cleaned
LME_ROOT=outputs/runs/mem0/longmemeval/s-cleaned/smoke/unified

MB_BASE=mem0-membench-v3-r1q1-ps1-w2
MB_RUN=${MB_BASE}-0-10k
MB_ROOT=outputs/runs/mem0/membench/0-10k/smoke/unified

BEAM100_BASE=mem0-beam-v3-pair-r1q1-c2-w2
BEAM100_RUN=${BEAM100_BASE}-100k
BEAM100_ROOT=outputs/runs/mem0/beam/100k/smoke/unified

BEAM10_BASE=mem0-beam-v3-pair-r1q1-w1
BEAM10_RUN=${BEAM10_BASE}-10m
BEAM10_ROOT=outputs/runs/mem0/beam/10m/smoke/unified

HALU_BASE=mem0-halumem-v3-r1-w1
HALU_RUN=${HALU_BASE}-medium
HALU_ROOT=outputs/runs/mem0/halumem/medium/smoke/unified

TMP_LOG_ROOT="${TMPDIR:-/tmp}/memory-benchmark-mem0-v3-b11"
mkdir -p "$TMP_LOG_ROOT"

test ! -e "$LOCO_ROOT/$LOCO_RUN_W1"
test ! -e "$LOCO_ROOT/$LOCO_RUN_W2"
test ! -e "$LME_ROOT/$LME_RUN_W1"
test ! -e "$LME_ROOT/$LME_RUN_W2"
test ! -e "$MB_ROOT/$MB_RUN"
test ! -e "$BEAM100_ROOT/$BEAM100_RUN"
test ! -e "$BEAM10_ROOT/$BEAM10_RUN"
test ! -e "$HALU_ROOT/$HALU_RUN"
```

不得打印或 `cat .env`。若最后八条 `test ! -e` 任一失败，不要删除旧目录；先把冲突 run id
交给架构师裁决。

## 3. LoCoMo：具名 speaker、caption、turn Recall

### 3.1 单 worker

```bash
uv run memory-benchmark predict smoke \
  --root . --method mem0 --benchmark locomo --config-track unified \
  --run-id "$LOCO_RUN_W1" --rounds 3 --conversations 1 \
  --questions-per-conversation 1 --workers 1 --allow-api \
  2>&1 | tee "$TMP_LOG_ROOT/$LOCO_RUN_W1.predict.log"
PREDICT_STATUS=$?
mkdir -p "$LOCO_ROOT/$LOCO_RUN_W1/logs"
mv "$TMP_LOG_ROOT/$LOCO_RUN_W1.predict.log" \
  "$LOCO_ROOT/$LOCO_RUN_W1/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0

uv run memory-benchmark evaluate --root . --run-id "$LOCO_RUN_W1" \
  --metric locomo-f1 --metric f1 --metric normalized-em \
  --metric substring-em --metric locomo-recall --workers 1 \
  2>&1 | tee "$LOCO_ROOT/$LOCO_RUN_W1/logs/terminal.evaluate-offline.log"
test "$?" -eq 0

uv run memory-benchmark evaluate --root . --run-id "$LOCO_RUN_W1" \
  --metric locomo-judge --judge-profile compact --workers 1 --allow-api \
  2>&1 | tee "$LOCO_ROOT/$LOCO_RUN_W1/logs/terminal.evaluate-judge.log"
test "$?" -eq 0
```

### 3.2 双 worker

```bash
uv run memory-benchmark predict smoke \
  --root . --method mem0 --benchmark locomo --config-track unified \
  --run-id "$LOCO_RUN_W2" --rounds 3 --conversations 2 \
  --questions-per-conversation 1 --workers 2 --allow-api \
  2>&1 | tee "$TMP_LOG_ROOT/$LOCO_RUN_W2.predict.log"
PREDICT_STATUS=$?
mkdir -p "$LOCO_ROOT/$LOCO_RUN_W2/logs"
mv "$TMP_LOG_ROOT/$LOCO_RUN_W2.predict.log" \
  "$LOCO_ROOT/$LOCO_RUN_W2/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0

uv run memory-benchmark evaluate --root . --run-id "$LOCO_RUN_W2" \
  --metric locomo-f1 --metric f1 --metric normalized-em \
  --metric substring-em --metric locomo-recall --workers 1 \
  2>&1 | tee "$LOCO_ROOT/$LOCO_RUN_W2/logs/terminal.evaluate-offline.log"
test "$?" -eq 0

uv run memory-benchmark evaluate --root . --run-id "$LOCO_RUN_W2" \
  --metric locomo-judge --judge-profile compact --workers 2 --allow-api \
  2>&1 | tee "$LOCO_ROOT/$LOCO_RUN_W2/logs/terminal.evaluate-judge.log"
test "$?" -eq 0
```

低 Recall、EM 或 judge 分数不是结构失败；本格必须形成 `valid/turn` retrieval evidence。当前
stable ranking 仍是 `pending`，因此不追加未经资格审计的排序指标。

## 4. LongMemEval：每 instance 一个双 turn round、session Recall、rank N/A

只有 §3 全绿后执行。

### 4.1 单 worker

```bash
uv run memory-benchmark predict smoke \
  --root . --method mem0 --benchmark longmemeval --variant s_cleaned \
  --config-track unified --run-id "$LME_BASE_W1" --rounds 1 --conversations 1 \
  --questions-per-conversation 1 --workers 1 --allow-api \
  2>&1 | tee "$TMP_LOG_ROOT/$LME_RUN_W1.predict.log"
PREDICT_STATUS=$?
mkdir -p "$LME_ROOT/$LME_RUN_W1/logs"
mv "$TMP_LOG_ROOT/$LME_RUN_W1.predict.log" \
  "$LME_ROOT/$LME_RUN_W1/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0

uv run memory-benchmark evaluate --root . --run-id "$LME_RUN_W1" \
  --metric f1 --metric normalized-em --metric substring-em \
  --metric longmemeval-recall --metric longmemeval-retrieval-rank --workers 1 \
  2>&1 | tee "$LME_ROOT/$LME_RUN_W1/logs/terminal.evaluate-offline.log"
test "$?" -eq 0

uv run memory-benchmark evaluate --root . --run-id "$LME_RUN_W1" \
  --metric longmemeval-judge --judge-profile compact --workers 1 --allow-api \
  2>&1 | tee "$LME_ROOT/$LME_RUN_W1/logs/terminal.evaluate-judge.log"
test "$?" -eq 0
```

### 4.2 双 worker

```bash
uv run memory-benchmark predict smoke \
  --root . --method mem0 --benchmark longmemeval --variant s_cleaned \
  --config-track unified --run-id "$LME_BASE_W2" --rounds 1 --conversations 2 \
  --questions-per-conversation 1 --workers 2 --allow-api \
  2>&1 | tee "$TMP_LOG_ROOT/$LME_RUN_W2.predict.log"
PREDICT_STATUS=$?
mkdir -p "$LME_ROOT/$LME_RUN_W2/logs"
mv "$TMP_LOG_ROOT/$LME_RUN_W2.predict.log" \
  "$LME_ROOT/$LME_RUN_W2/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0

uv run memory-benchmark evaluate --root . --run-id "$LME_RUN_W2" \
  --metric f1 --metric normalized-em --metric substring-em \
  --metric longmemeval-recall --metric longmemeval-retrieval-rank --workers 1 \
  2>&1 | tee "$LME_ROOT/$LME_RUN_W2/logs/terminal.evaluate-offline.log"
test "$?" -eq 0

uv run memory-benchmark evaluate --root . --run-id "$LME_RUN_W2" \
  --metric longmemeval-judge --judge-profile compact --workers 2 --allow-api \
  2>&1 | tee "$LME_ROOT/$LME_RUN_W2/logs/terminal.evaluate-judge.log"
test "$?" -eq 0
```

Mem0 sidecar 对 LongMemEval 只证明 session lineage，因此 Recall 是 `valid/session`；官方 gold
包含 answer session，框架可按 session group 计 Recall。NDCG/rank 还要求已审计的稳定返回顺序，
当前应成功落盘但 `mean_score=null/status=n/a`，不能把 pending 排名硬算成分数。

## 5. MemBench：四 source、真实双 worker

```bash
uv run memory-benchmark predict smoke \
  --root . --method mem0 --benchmark membench --variant 0_10k \
  --config-track unified --run-id "$MB_BASE" --rounds 1 \
  --conversations 1 --questions-per-conversation 1 --workers 2 --allow-api \
  2>&1 | tee "$TMP_LOG_ROOT/$MB_RUN.predict.log"
PREDICT_STATUS=$?
mkdir -p "$MB_ROOT/$MB_RUN/logs"
mv "$TMP_LOG_ROOT/$MB_RUN.predict.log" \
  "$MB_ROOT/$MB_RUN/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0

uv run memory-benchmark evaluate --root . --run-id "$MB_RUN" \
  --metric membench-choice-accuracy --metric membench-source-accuracy \
  --metric membench-recall --workers 1 \
  2>&1 | tee "$MB_ROOT/$MB_RUN/logs/terminal.evaluate-offline.log"
test "$?" -eq 0
```

`--conversations 1` 是每个 source 各取 1 条，所以该 run 共 4 questions；不传
`--membench-sources`，避免把四源认证偷换成子集。MemBench 没有当前适用的 LLM judge；A-D
选择题也不强加自由文本 F1/EM。

## 6. BEAM：100K 双 worker + 10M 单 worker

### 6.1 100K

```bash
uv run memory-benchmark predict smoke \
  --root . --method mem0 --benchmark beam --variant 100k \
  --config-track unified --run-id "$BEAM100_BASE" --rounds 1 \
  --conversations 2 --questions-per-conversation 1 --workers 2 --allow-api \
  2>&1 | tee "$TMP_LOG_ROOT/$BEAM100_RUN.predict.log"
PREDICT_STATUS=$?
mkdir -p "$BEAM100_ROOT/$BEAM100_RUN/logs"
mv "$TMP_LOG_ROOT/$BEAM100_RUN.predict.log" \
  "$BEAM100_ROOT/$BEAM100_RUN/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0

uv run memory-benchmark evaluate --root . --run-id "$BEAM100_RUN" \
  --metric beam-recall --workers 1 \
  2>&1 | tee "$BEAM100_ROOT/$BEAM100_RUN/logs/terminal.evaluate-offline.log"
test "$?" -eq 0

uv run memory-benchmark evaluate --root . --run-id "$BEAM100_RUN" \
  --metric beam-rubric-judge --judge-profile compact --workers 2 --allow-api \
  2>&1 | tee "$BEAM100_ROOT/$BEAM100_RUN/logs/terminal.evaluate-judge.log"
test "$?" -eq 0
```

### 6.2 10M

```bash
uv run memory-benchmark predict smoke \
  --root . --method mem0 --benchmark beam --variant 10m \
  --config-track unified --run-id "$BEAM10_BASE" --rounds 1 \
  --conversations 1 --questions-per-conversation 1 --workers 1 --allow-api \
  2>&1 | tee "$TMP_LOG_ROOT/$BEAM10_RUN.predict.log"
PREDICT_STATUS=$?
mkdir -p "$BEAM10_ROOT/$BEAM10_RUN/logs"
mv "$TMP_LOG_ROOT/$BEAM10_RUN.predict.log" \
  "$BEAM10_ROOT/$BEAM10_RUN/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0

uv run memory-benchmark evaluate --root . --run-id "$BEAM10_RUN" \
  --metric beam-recall --workers 1 \
  2>&1 | tee "$BEAM10_ROOT/$BEAM10_RUN/logs/terminal.evaluate-offline.log"
test "$?" -eq 0

uv run memory-benchmark evaluate --root . --run-id "$BEAM10_RUN" \
  --metric beam-rubric-judge --judge-profile compact --workers 1 --allow-api \
  2>&1 | tee "$BEAM10_ROOT/$BEAM10_RUN/logs/terminal.evaluate-judge.log"
test "$?" -eq 0
```

两条 BEAM Recall 命令应成功写 `N/A`，不是 0 分：Mem0 的 pair add 把两个 source turn id
共同挂到抽取事实，不能无损归因到 BEAM 的单 message gold。rubric judge 仍正常测答案质量。

## 7. HaluMem：边灌边测、三类 judge 与细分项

### 7.1 predict

HaluMem smoke shape 是冻结的，不接受 `--rounds/--sessions/--conversations/--questions-*`：

```bash
uv run memory-benchmark predict smoke \
  --root . --method mem0 --benchmark halumem --variant medium \
  --config-track unified --run-id "$HALU_BASE" --workers 1 --allow-api \
  2>&1 | tee "$TMP_LOG_ROOT/$HALU_RUN.predict.log"
PREDICT_STATUS=$?
mkdir -p "$HALU_ROOT/$HALU_RUN/logs"
mv "$TMP_LOG_ROOT/$HALU_RUN.predict.log" \
  "$HALU_ROOT/$HALU_RUN/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0
```

### 7.2 下一步真实 judge 调用数预览（零 API）

该脚本读取刚生成的 session report/update probe/private label，镜像 evaluator 空路由；不是用
add 数量猜 LLM 调用数。

```bash
uv run python - <<'PY'
from __future__ import annotations

import json
from pathlib import Path

run_dir = Path(
    "outputs/runs/mem0/halumem/medium/smoke/unified/"
    "mem0-halumem-v3-r1-w1-medium"
)

def read_jsonl(path: Path) -> list[dict]:
    """读取 JSONL。"""
    assert path.is_file(), path
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

reports = read_jsonl(run_dir / "artifacts/session_memory_reports.jsonl")
labels = {
    row["session_id"]: row
    for row in read_jsonl(
        run_dir / "artifacts/evaluator_private_session_labels.jsonl"
    )
}
probes = read_jsonl(run_dir / "artifacts/update_probe_results.jsonl")
predictions = read_jsonl(run_dir / "artifacts/method_predictions.jsonl")
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

### 7.3 三项官方 judge（真实 API）

```bash
for METRIC in halumem-extraction halumem-update halumem-qa; do
  uv run memory-benchmark evaluate --root . --run-id "$HALU_RUN" \
    --metric "$METRIC" --judge-profile compact --workers 1 --allow-api \
    2>&1 | tee "$HALU_ROOT/$HALU_RUN/logs/terminal.evaluate.$METRIC.log"
  EVAL_STATUS=$?
  test "$EVAL_STATUS" -eq 0 || break
done
test "$EVAL_STATUS" -eq 0
```

### 7.4 memory type 与通用离线指标（零 API）

`halumem-memory-type` 消费 extraction + update 产物，必须放在三项官方 judge 之后：

```bash
for METRIC in halumem-memory-type f1 normalized-em substring-em; do
  uv run memory-benchmark evaluate --root . --run-id "$HALU_RUN" \
    --metric "$METRIC" --workers 1 \
    2>&1 | tee "$HALU_ROOT/$HALU_RUN/logs/terminal.evaluate.$METRIC.log"
  EVAL_STATUS=$?
  test "$EVAL_STATUS" -eq 0 || break
done
test "$EVAL_STATUS" -eq 0
```

最终 artifact 必须同时保留 extraction 的 recall/weighted recall/target precision/accuracy/FMR/F1，
update 的 correct/hallucination/omission，QA 的 correct/hallucination/omission；`category_breakdown`
保留 QA question type，`halumem-memory-type` 保留 Event/Persona/Relationship 三类，而不是只有
overall。

## 8. 八个 run 的统一机器验货（零 API）

全部命令 exit 0 后执行。该门验证 current v3 身份、规模、worker state、逐题 retrieval 资格、
所有适用 summary、judge 观测与 HaluMem 细分项；不以 smoke 分数高低判成败。

```bash
uv run python - <<'PY'
from __future__ import annotations

import json
from pathlib import Path


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


cases = (
    {
        "run_dir": Path("outputs/runs/mem0/locomo/smoke/unified/mem0-locomo-v3-r3q1-w1"),
        "benchmark": "locomo", "variant": "locomo10", "questions": 1,
        "workers": 1, "conversations": 1, "consume": "turn",
        "semantic": "valid", "granularity": "turn", "query_top_k": 10,
        "summaries": ("locomo_f1", "f1", "normalized_em", "substring_em",
                      "locomo_recall", "locomo_judge_accuracy"),
        "null_summaries": (),
        "judge_metrics": ("locomo_judge_accuracy",),
        "terminal_logs": ("terminal.predict.log", "terminal.evaluate-offline.log",
                          "terminal.evaluate-judge.log"),
    },
    {
        "run_dir": Path("outputs/runs/mem0/locomo/smoke/unified/mem0-locomo-v3-r3q1-c2-w2"),
        "benchmark": "locomo", "variant": "locomo10", "questions": 2,
        "workers": 2, "conversations": 2, "consume": "turn",
        "semantic": "valid", "granularity": "turn", "query_top_k": 10,
        "summaries": ("locomo_f1", "f1", "normalized_em", "substring_em",
                      "locomo_recall", "locomo_judge_accuracy"),
        "null_summaries": (),
        "judge_metrics": ("locomo_judge_accuracy",),
        "terminal_logs": ("terminal.predict.log", "terminal.evaluate-offline.log",
                          "terminal.evaluate-judge.log"),
    },
    {
        "run_dir": Path("outputs/runs/mem0/longmemeval/s-cleaned/smoke/unified/mem0-lme-v3-r1q1-w1-s-cleaned"),
        "benchmark": "longmemeval", "variant": "s_cleaned", "questions": 1,
        "workers": 1, "conversations": 1, "consume": "session",
        "semantic": "valid", "granularity": "session", "query_top_k": 10,
        "summaries": ("f1", "normalized_em", "substring_em", "longmemeval_recall",
                      "longmemeval_retrieval_rank", "longmemeval_judge_accuracy"),
        "null_summaries": ("longmemeval_retrieval_rank",),
        "judge_metrics": ("longmemeval_judge_accuracy",),
        "terminal_logs": ("terminal.predict.log", "terminal.evaluate-offline.log",
                          "terminal.evaluate-judge.log"),
    },
    {
        "run_dir": Path("outputs/runs/mem0/longmemeval/s-cleaned/smoke/unified/mem0-lme-v3-r1q1-c2-w2-s-cleaned"),
        "benchmark": "longmemeval", "variant": "s_cleaned", "questions": 2,
        "workers": 2, "conversations": 2, "consume": "session",
        "semantic": "valid", "granularity": "session", "query_top_k": 10,
        "summaries": ("f1", "normalized_em", "substring_em", "longmemeval_recall",
                      "longmemeval_retrieval_rank", "longmemeval_judge_accuracy"),
        "null_summaries": ("longmemeval_retrieval_rank",),
        "judge_metrics": ("longmemeval_judge_accuracy",),
        "terminal_logs": ("terminal.predict.log", "terminal.evaluate-offline.log",
                          "terminal.evaluate-judge.log"),
    },
    {
        "run_dir": Path("outputs/runs/mem0/membench/0-10k/smoke/unified/mem0-membench-v3-r1q1-ps1-w2-0-10k"),
        "benchmark": "membench", "variant": "0_10k", "questions": 4,
        "workers": 2, "conversations": 4, "consume": "turn",
        "semantic": "valid", "granularity": "turn", "query_top_k": 10,
        "summaries": ("membench_choice_accuracy", "membench_source_accuracy",
                      "membench_recall"),
        "null_summaries": (), "judge_metrics": (),
        "terminal_logs": ("terminal.predict.log", "terminal.evaluate-offline.log"),
    },
    {
        "run_dir": Path("outputs/runs/mem0/beam/100k/smoke/unified/mem0-beam-v3-pair-r1q1-c2-w2-100k"),
        "benchmark": "beam", "variant": "100k", "questions": 2,
        "workers": 2, "conversations": 2, "consume": "pair",
        "semantic": "n_a", "granularity": "none", "query_top_k": 10,
        "summaries": ("beam_recall", "beam_rubric_judge"),
        "null_summaries": ("beam_recall",),
        "judge_metrics": ("beam_rubric_judge",),
        "terminal_logs": ("terminal.predict.log", "terminal.evaluate-offline.log",
                          "terminal.evaluate-judge.log"),
    },
    {
        "run_dir": Path("outputs/runs/mem0/beam/10m/smoke/unified/mem0-beam-v3-pair-r1q1-w1-10m"),
        "benchmark": "beam", "variant": "10m", "questions": 1,
        "workers": 1, "conversations": 1, "consume": "pair",
        "semantic": "n_a", "granularity": "none", "query_top_k": 10,
        "summaries": ("beam_recall", "beam_rubric_judge"),
        "null_summaries": ("beam_recall",),
        "judge_metrics": ("beam_rubric_judge",),
        "terminal_logs": ("terminal.predict.log", "terminal.evaluate-offline.log",
                          "terminal.evaluate-judge.log"),
    },
    {
        "run_dir": Path("outputs/runs/mem0/halumem/medium/smoke/unified/mem0-halumem-v3-r1-w1-medium"),
        "benchmark": "halumem", "variant": "medium", "questions": 1,
        "workers": 1, "conversations": 1, "consume": "session",
        "semantic": "valid", "granularity": "session", "query_top_k": None,
        "summaries": ("halumem_extraction", "halumem_update", "halumem_qa",
                      "halumem_memory_type", "f1", "normalized_em", "substring_em"),
        "null_summaries": (),
        "judge_metrics": ("halumem_extraction", "halumem_update", "halumem_qa"),
        "terminal_logs": (
            "terminal.predict.log", "terminal.evaluate.halumem-extraction.log",
            "terminal.evaluate.halumem-update.log", "terminal.evaluate.halumem-qa.log",
            "terminal.evaluate.halumem-memory-type.log", "terminal.evaluate.f1.log",
            "terminal.evaluate.normalized-em.log", "terminal.evaluate.substring-em.log",
        ),
    },
)

source_sha = "debda89ed60d9f104ab6fa65d6178d5f146b3216158f3dc2fdba2ee16a3ff08e"

for case in cases:
    run_dir = case["run_dir"]
    manifest = read_json(run_dir / "manifest.json")
    method = manifest["method"]
    config = method["config"]
    track = method["track_identity"]
    assert manifest["run_id"] == run_dir.name
    assert manifest["benchmark_name"] == case["benchmark"]
    assert manifest["benchmark_variant"] == case["variant"]
    assert manifest["run_scope"] == "smoke"
    assert manifest["policy"]["max_workers"] == case["workers"]
    assert method["protocol_version"] == "v3"
    assert method["retrieval_evidence_contract_version"] == "v1"
    assert method["consume_granularity"] == case["consume"]
    assert config["adapter_version"] == "conversation-qa-v3"
    assert config["extraction_model"] == "gpt-4o-mini"
    assert config["reader_model"] == "gpt-4o-mini"
    assert config["embedding_provider"] == "huggingface"
    assert config["embedding_model"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert config["embedding_dimensions"] == 384
    assert config["top_k"] == 20
    assert method["source"]["source_sha256"] == source_sha
    assert track["implementation_variant"] == "product"
    assert track["readout_track"] == "unified"
    assert track["native_scope"] == "none"
    assert track["embedding_profile"] == "controlled_embedding_v1"
    assert track["embedding"]["identity_status"] == "declared"

    predictions = read_jsonl(run_dir / "artifacts/method_predictions.jsonl")
    answers = read_jsonl(run_dir / "artifacts/answer_prompts.prediction.jsonl")
    assert len(predictions) == case["questions"], (run_dir, len(predictions))
    assert len(answers) == case["questions"], (run_dir, len(answers))
    assert len({row["conversation_id"] for row in predictions}) == case["conversations"]
    for row in answers:
        assert isinstance(row["formatted_memory"], str)
        assert isinstance(row["retrieved_items"], list)
        assert row["retrieval_query_top_k"] == case["query_top_k"]
        evidence = row["retrieval_evidence"]
        assert evidence["semantic_provenance"]["status"] == case["semantic"]
        assert evidence["provenance_granularity"] == case["granularity"]
        assert evidence["stable_ranking"]["status"] == "pending"
        if case["benchmark"] == "beam":
            assert evidence["semantic_provenance"]["reason_code"] == (
                "ingest_batch_coarser_than_gold"
            )

    for metric in case["summaries"]:
        summary = read_json(run_dir / "summaries" / f"summary.{metric}.json")
        assert summary["metric_name"] == metric
        if metric in case["null_summaries"]:
            assert summary["mean_score"] is None, (run_dir, metric, summary)
        else:
            assert isinstance(summary["mean_score"], (int, float)), (run_dir, metric)

    prediction_efficiency = read_jsonl(
        run_dir / "artifacts/efficiency_observations.prediction.jsonl"
    )
    assert prediction_efficiency, run_dir
    assert (run_dir / "artifacts/model_inventory.prediction.json").is_file()
    for metric in case["judge_metrics"]:
        assert (run_dir / f"artifacts/efficiency_observations.{metric}.jsonl").is_file()
        assert (run_dir / f"artifacts/model_inventory.{metric}.json").is_file()

    state_root = run_dir / "method_state"
    worker_dirs = sorted(state_root.glob("worker_*"))
    state_dirs = tuple(worker_dirs) if worker_dirs else (state_root,)
    if case["workers"] == 1:
        assert worker_dirs == [], (run_dir, worker_dirs)
    else:
        assert len(worker_dirs) == case["workers"], (run_dir, worker_dirs)
    namespace_count = 0
    for state_dir in state_dirs:
        assert (state_dir / "history.db").is_file(), state_dir
        assert (state_dir / "qdrant").is_dir(), state_dir
        sidecar = read_json(state_dir / "provenance-sidecar.json")
        assert sidecar["schema_version"] == 1
        namespace_count += len(sidecar["namespaces"])
    assert namespace_count == case["conversations"], (run_dir, namespace_count)

    for log_name in case["terminal_logs"]:
        assert (run_dir / "logs" / log_name).is_file(), (run_dir, log_name)
    print(
        f"PASS {run_dir.name}: benchmark={case['benchmark']}, "
        f"questions={case['questions']}, workers={case['workers']}, "
        f"evidence={case['semantic']}/{case['granularity']}"
    )

halu_dir = cases[-1]["run_dir"]
reports = read_jsonl(halu_dir / "artifacts/session_memory_reports.jsonl")
probes = read_jsonl(halu_dir / "artifacts/update_probe_results.jsonl")
assert len(reports) == 4
assert [row["session_ref"]["session_id"] for row in reports] == ["s1", "s2", "s3", "s4"]
assert all(row["status"] == "ok" for row in reports)
assert all(row["metadata"]["method"] == "mem0" for row in reports)
assert all(row["metadata"]["source"] == "mem0_add_results" for row in reports)
assert len(probes) == 7

extraction = read_json(halu_dir / "summaries/summary.halumem_extraction.json")
update = read_json(halu_dir / "summaries/summary.halumem_update.json")
qa = read_json(halu_dir / "summaries/summary.halumem_qa.json")
memory_type = read_json(halu_dir / "summaries/summary.halumem_memory_type.json")
assert "memory_integrity" in extraction["overall_score"]
assert "memory_accuracy" in extraction["overall_score"]
assert "memory_extraction_f1" in extraction["overall_score"]
assert "memory_update" in update["overall_score"]
assert "question_answering" in qa["overall_score"]
assert qa["category_breakdown"] and all(
    row.get("category") and row.get("question_count", 0) > 0
    for row in qa["category_breakdown"]
)
expected_types = {"Event Memory", "Persona Memory", "Relationship Memory"}
assert {row["category"] for row in memory_type["category_breakdown"]} == expected_types
print(
    "PASS Mem0 five-grid B11 machine gate: 8 runs, all eligible metrics, "
    "worker isolation, retrieval eligibility and HaluMem breakdowns present"
)
PY
```

## 9. 回收协议

用户执行后只需告诉架构师“全部完成”或粘贴**第一处 exception/PASS 尾行**；无需把所有 terminal
输出手工复制进聊天。架构师会直接从上述 8 个 run 目录开箱：逐 manifest、artifact、summary、
efficiency、sidecar/Qdrant 与 worker state 复核。机器门 PASS 也不自动等于 frozen；开箱后才做
B11 对表、生成 Mem0 frozen note、更新报告与清理本轮断点。
