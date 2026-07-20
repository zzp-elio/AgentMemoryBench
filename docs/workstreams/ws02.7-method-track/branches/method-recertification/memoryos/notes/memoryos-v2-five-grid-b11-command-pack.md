# MemoryOS current-v2 shared-lifecycle 五格 B11 真实 smoke 命令包

> 状态：**已获用户预算、规模与 run-id 授权，待执行**。命令生成基线为
> `main@ed945d2`；该基线已完成 shared-lifecycle R1-R5 full-diff 强验收、主树无 API
> 全量 `1666 passed, 3 deselected, 2 warnings, 29 subtests passed in 145.12s` 与
> compileall exit 0。本页只授权下列 8 个 run；不授权 full、resume、扩大题数、删除失败
> 现场或切换模型。全部真实 LLM 调用继续使用 `gpt-4o-mini`。

## 1. 运行矩阵与边界

| benchmark | run | 规模与承重点 |
|---|---|---|
| LoCoMo | `memoryos-locomo-v2sl-r3q1-w1` | 1 conversation × 3 rounds × 1 question × 1 worker；覆盖具名 speaker、图片 caption、source time |
| LoCoMo | `memoryos-locomo-v2sl-r3q1-c2-w2` | 2 conversations × 3 rounds × 各 1 question × 2 workers；第二条 conversation 同时覆盖 orphan assistant 与 dangling user 的空侧 page |
| LongMemEval | `memoryos-lme-v2sl-r1q1-w1-s-cleaned` | S-cleaned 1 instance × 1 round=2 turns × 1 question × 1 worker |
| LongMemEval | `memoryos-lme-v2sl-r1q1-c2-w2-s-cleaned` | S-cleaned 2 instances × 各 1 round × 各 1 question × 2 workers |
| MemBench | `memoryos-membench-v2sl-r1q1-ps1-w2-0-10k` | 四 source 各 1 trajectory，共 4 questions，2 workers；覆盖 FirstAgent pair 与 ThirdAgent user-only page |
| BEAM | `memoryos-beam-v2sl-r1q1-c2-w2-100k` | 100K 2 conversations × 2 workers；标准 pair + 并发隔离 |
| BEAM | `memoryos-beam-v2sl-r1q1-w1-10m` | 10M 1 conversation × 1 worker；不同 source shape 真实入口 |
| HaluMem | `memoryos-halumem-v2sl-r1-w1-medium` | Medium 固定 smoke：1 conversation、4 sessions、1 QA；边写边做 extraction/update/QA |

`v2sl` 表示 adapter `conversation-qa-v2-shared-lifecycle`。四个非 HaluMem benchmark
各有真实双 worker 证据；HaluMem operation runner 按协议固定 `workers=1`。所有 predict
必须串行执行；`workers=2` 只是单条命令内部并发，不能同时从两个 shell 启动 predict。

当前最小 shape 每个 conversation 都低于 STM capacity=10，所以 manifest 的
`total_update_batches` 应为 0：真实 smoke 会覆盖产品 STM 写入、全层 readout、local embedding、
framework answer 与 evaluator，但不会付费触发 STM→MTM updater。单侧 page 的 STM→MTM 迁移
已经由真实 vendored backend 的 capacity-crossing 强反例覆盖；本页不会把该无 API 证据偷换成
“付费 smoke 已走 updater”。

在没有重试的正常路径下，预计真实 LLM 调用共 31 次：14 次 framework answer、LoCoMo/
LongMemEval/BEAM 共 9 次 judge、HaluMem update/QA 共 8 次；MemoryOS updater 为 0 次，
HaluMem extraction 为 0 次。任何 provider 重试会增加实际调用，最终以 efficiency artifact 为准。

## 2. 一次性环境门与 run 变量

在新的 zsh 中整段执行，后续继续使用同一 shell。`git status --short` 可显示 OWNER 的既有
untracked 私有资产；tracked-source 门由两条 `git diff --quiet` 保证。

```bash
cd /Users/wz/Desktop/memoryBenchmark
set -o pipefail

git status --short
git log -5 --oneline
git diff --quiet
git diff --cached --quiet
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
git merge-base --is-ancestor ed945d2 HEAD
test -f .env
test -f data/locomo/locomo10.json
test -f data/longmemeval/longmemeval_s_cleaned.json
test -d data/membench/Membenchdata/data2test/0-10k
test -d data/BEAM/beam_dataset/100K
test -d data/BEAM/beam_10M_dataset/10M
test -f data/halumem/HaluMem-Medium.jsonl
test -d models/all-MiniLM-L6-v2

LOCO_RUN_W1=memoryos-locomo-v2sl-r3q1-w1
LOCO_RUN_W2=memoryos-locomo-v2sl-r3q1-c2-w2
LOCO_ROOT=outputs/runs/memoryos/locomo/smoke/unified

LME_BASE_W1=memoryos-lme-v2sl-r1q1-w1
LME_BASE_W2=memoryos-lme-v2sl-r1q1-c2-w2
LME_RUN_W1=${LME_BASE_W1}-s-cleaned
LME_RUN_W2=${LME_BASE_W2}-s-cleaned
LME_ROOT=outputs/runs/memoryos/longmemeval/s-cleaned/smoke/unified

MB_BASE=memoryos-membench-v2sl-r1q1-ps1-w2
MB_RUN=${MB_BASE}-0-10k
MB_ROOT=outputs/runs/memoryos/membench/0-10k/smoke/unified

BEAM100_BASE=memoryos-beam-v2sl-r1q1-c2-w2
BEAM100_RUN=${BEAM100_BASE}-100k
BEAM100_ROOT=outputs/runs/memoryos/beam/100k/smoke/unified

BEAM10_BASE=memoryos-beam-v2sl-r1q1-w1
BEAM10_RUN=${BEAM10_BASE}-10m
BEAM10_ROOT=outputs/runs/memoryos/beam/10m/smoke/unified

HALU_BASE=memoryos-halumem-v2sl-r1-w1
HALU_RUN=${HALU_BASE}-medium
HALU_ROOT=outputs/runs/memoryos/halumem/medium/smoke/unified

TMP_LOG_ROOT="${TMPDIR:-/tmp}/memory-benchmark-memoryos-v2sl-b11"
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

不得打印或 `cat .env`。最后八条任一失败时不要删除旧目录，先停下并把冲突 run id 交回
架构师。

## 3. LoCoMo：角色扮演映射、caption、空侧 page 与 turn Recall

### 3.1 单 worker

```bash
uv run memory-benchmark predict smoke \
  --root . --method memoryos --benchmark locomo --config-track unified \
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
  --root . --method memoryos --benchmark locomo --config-track unified \
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

本格必须形成 `valid/turn` retrieval evidence。低 Recall、EM 或 judge 分数不是结构失败；
stable ranking 仍为 `pending`，不加未经资格审计的 rank 指标。

## 4. LongMemEval：完整双 turn round、turn Recall、rank N/A

只有 LoCoMo 两条全绿后执行。

### 4.1 单 worker

```bash
uv run memory-benchmark predict smoke \
  --root . --method memoryos --benchmark longmemeval --variant s_cleaned \
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
  --root . --method memoryos --benchmark longmemeval --variant s_cleaned \
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

MemoryOS 原生 page metadata 保 exact child turn ids，因此 LongMemEval Recall 是
`valid/turn`，不是旧 Mem0 的 session-only 口径。rank/NDCG 还要求稳定返回顺序；当前应成功
落盘但 `mean_score=null`，不能把 `stable_ranking=pending` 硬算成分数。

## 5. MemBench：四 source、FirstAgent pair、ThirdAgent 空 assistant 侧

```bash
uv run memory-benchmark predict smoke \
  --root . --method memoryos --benchmark membench --variant 0_10k \
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

`--conversations 1` 表示每个 source 各取一条，所以该 run 共 4 questions；不传
`--membench-sources`。MemBench 没有当前适用的 LLM judge，也不对 A-D 选择题强加自由文本
F1/EM。

## 6. BEAM：100K 双 worker + 10M 单 worker

### 6.1 100K

```bash
uv run memory-benchmark predict smoke \
  --root . --method memoryos --benchmark beam --variant 100k \
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
  --root . --method memoryos --benchmark beam --variant 10m \
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

MemoryOS page 持久化 exact child ids，所以 BEAM Recall 也应为 `valid/turn`；10M 两处已知
orphan/错位窗口由零 API source-locked 反例承担，不要求首条付费 smoke 偶然选中。

## 7. HaluMem：extraction N/A，update/QA 可测

### 7.1 predict

HaluMem smoke shape 固定，不接受 `--rounds/--sessions/--conversations/--questions-*`：

```bash
uv run memory-benchmark predict smoke \
  --root . --method memoryos --benchmark halumem --variant medium \
  --config-track unified --run-id "$HALU_BASE" --workers 1 --allow-api \
  2>&1 | tee "$TMP_LOG_ROOT/$HALU_RUN.predict.log"
PREDICT_STATUS=$?
mkdir -p "$HALU_ROOT/$HALU_RUN/logs"
mv "$TMP_LOG_ROOT/$HALU_RUN.predict.log" \
  "$HALU_ROOT/$HALU_RUN/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0
```

### 7.2 judge 调用预览（零 API）

MemoryOS 没有 session-local `end_session()` report，所以 extraction 调用数必须为 0；update
按实际非空检索 probe 计数，QA 按 prediction 计数。该脚本读真实 artifact，不用 add/page 数
猜调用量。

```bash
uv run python - <<'PY'
from __future__ import annotations

import json
from pathlib import Path

run_dir = Path(
    "outputs/runs/memoryos/halumem/medium/smoke/unified/"
    "memoryos-halumem-v2sl-r1-w1-medium"
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
probes = read_jsonl(run_dir / "artifacts/update_probe_results.jsonl")
predictions = read_jsonl(run_dir / "artifacts/method_predictions.jsonl")
assert reports and all(row.get("status") == "n/a" for row in reports)
extraction_calls = 0
update_calls = sum(bool(row.get("memories_from_system")) for row in probes)
qa_calls = len(predictions)
print(
    "JUDGE_CALL_PREVIEW "
    f"extraction={extraction_calls} update={update_calls} qa={qa_calls} "
    f"total={extraction_calls + update_calls + qa_calls}"
)
PY
```

预期当前 fixed smoke 为 `extraction=0 update=7 qa=1 total=8`。若不同，不要立即运行付费
judge，先把真实预览尾行交回架构师。

### 7.3 三项官方 evaluator

extraction 虽不发 API，也必须执行一次以落下正式 N/A summary；随后再跑 update 与 QA。

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

### 7.4 memory type 与通用离线指标

`halumem-memory-type` 依赖 extraction/update 产物，必须放在上一步之后。由于 extraction
明确 N/A，它也必须清洁传播为 N/A；不得只拿 update 伪造 Event/Persona/Relationship 总表。

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

## 8. 八个 run 的统一机器验货（零 API）

全部命令 exit 0 后执行。本门不按 smoke 分数高低判成败，而是验证 source/build identity、
规模、worker state、空侧 page、caption、typed time、逐题 retrieval 资格、适用 summary、
judge 观测与 HaluMem N/A 传播。

```bash
uv run python - <<'PY'
from __future__ import annotations

import json
from pathlib import Path

from memory_benchmark.config import load_path_settings
from memory_benchmark.methods.memoryos_adapter import build_memoryos_source_identity


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
        "run_dir": Path("outputs/runs/memoryos/locomo/smoke/unified/memoryos-locomo-v2sl-r3q1-w1"),
        "benchmark": "locomo", "variant": "locomo10", "questions": 1,
        "workers": 1, "conversations": 1, "consume": "session",
        "summaries": ("locomo_f1", "f1", "normalized_em", "substring_em",
                      "locomo_recall", "locomo_judge_accuracy"),
        "null_summaries": (), "judge_metrics": ("locomo_judge_accuracy",),
        "logs": ("terminal.predict.log", "terminal.evaluate-offline.log",
                 "terminal.evaluate-judge.log"),
    },
    {
        "run_dir": Path("outputs/runs/memoryos/locomo/smoke/unified/memoryos-locomo-v2sl-r3q1-c2-w2"),
        "benchmark": "locomo", "variant": "locomo10", "questions": 2,
        "workers": 2, "conversations": 2, "consume": "session",
        "summaries": ("locomo_f1", "f1", "normalized_em", "substring_em",
                      "locomo_recall", "locomo_judge_accuracy"),
        "null_summaries": (), "judge_metrics": ("locomo_judge_accuracy",),
        "logs": ("terminal.predict.log", "terminal.evaluate-offline.log",
                 "terminal.evaluate-judge.log"),
    },
    {
        "run_dir": Path("outputs/runs/memoryos/longmemeval/s-cleaned/smoke/unified/memoryos-lme-v2sl-r1q1-w1-s-cleaned"),
        "benchmark": "longmemeval", "variant": "s_cleaned", "questions": 1,
        "workers": 1, "conversations": 1, "consume": "pair",
        "summaries": ("f1", "normalized_em", "substring_em", "longmemeval_recall",
                      "longmemeval_retrieval_rank", "longmemeval_judge_accuracy"),
        "null_summaries": ("longmemeval_retrieval_rank",),
        "judge_metrics": ("longmemeval_judge_accuracy",),
        "logs": ("terminal.predict.log", "terminal.evaluate-offline.log",
                 "terminal.evaluate-judge.log"),
    },
    {
        "run_dir": Path("outputs/runs/memoryos/longmemeval/s-cleaned/smoke/unified/memoryos-lme-v2sl-r1q1-c2-w2-s-cleaned"),
        "benchmark": "longmemeval", "variant": "s_cleaned", "questions": 2,
        "workers": 2, "conversations": 2, "consume": "pair",
        "summaries": ("f1", "normalized_em", "substring_em", "longmemeval_recall",
                      "longmemeval_retrieval_rank", "longmemeval_judge_accuracy"),
        "null_summaries": ("longmemeval_retrieval_rank",),
        "judge_metrics": ("longmemeval_judge_accuracy",),
        "logs": ("terminal.predict.log", "terminal.evaluate-offline.log",
                 "terminal.evaluate-judge.log"),
    },
    {
        "run_dir": Path("outputs/runs/memoryos/membench/0-10k/smoke/unified/memoryos-membench-v2sl-r1q1-ps1-w2-0-10k"),
        "benchmark": "membench", "variant": "0_10k", "questions": 4,
        "workers": 2, "conversations": 4, "consume": "session",
        "summaries": ("membench_choice_accuracy", "membench_source_accuracy",
                      "membench_recall"),
        "null_summaries": (), "judge_metrics": (),
        "logs": ("terminal.predict.log", "terminal.evaluate-offline.log"),
    },
    {
        "run_dir": Path("outputs/runs/memoryos/beam/100k/smoke/unified/memoryos-beam-v2sl-r1q1-c2-w2-100k"),
        "benchmark": "beam", "variant": "100k", "questions": 2,
        "workers": 2, "conversations": 2, "consume": "session",
        "summaries": ("beam_recall", "beam_rubric_judge"),
        "null_summaries": (), "judge_metrics": ("beam_rubric_judge",),
        "logs": ("terminal.predict.log", "terminal.evaluate-offline.log",
                 "terminal.evaluate-judge.log"),
    },
    {
        "run_dir": Path("outputs/runs/memoryos/beam/10m/smoke/unified/memoryos-beam-v2sl-r1q1-w1-10m"),
        "benchmark": "beam", "variant": "10m", "questions": 1,
        "workers": 1, "conversations": 1, "consume": "session",
        "summaries": ("beam_recall", "beam_rubric_judge"),
        "null_summaries": (), "judge_metrics": ("beam_rubric_judge",),
        "logs": ("terminal.predict.log", "terminal.evaluate-offline.log",
                 "terminal.evaluate-judge.log"),
    },
    {
        "run_dir": Path("outputs/runs/memoryos/halumem/medium/smoke/unified/memoryos-halumem-v2sl-r1-w1-medium"),
        "benchmark": "halumem", "variant": "medium", "questions": 1,
        "workers": 1, "conversations": 1, "consume": "session",
        "summaries": ("halumem_extraction", "halumem_update", "halumem_qa",
                      "halumem_memory_type", "f1", "normalized_em", "substring_em"),
        "null_summaries": ("halumem_memory_type",),
        "judge_metrics": ("halumem_extraction", "halumem_update", "halumem_qa"),
        "logs": (
            "terminal.predict.log", "terminal.evaluate.halumem-extraction.log",
            "terminal.evaluate.halumem-update.log", "terminal.evaluate.halumem-qa.log",
            "terminal.evaluate.halumem-memory-type.log", "terminal.evaluate.f1.log",
            "terminal.evaluate.normalized-em.log", "terminal.evaluate.substring-em.log",
        ),
    },
)

expected_source = build_memoryos_source_identity(load_path_settings(Path(".")))

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
    assert method["workload_estimate"] == {
        "kind": "memory_update_batches",
        "total_update_batches": 0,
        "conversation_count": case["conversations"],
    }
    assert config["adapter_version"] == "conversation-qa-v2-shared-lifecycle"
    assert config["profile_name"] == "smoke"
    assert config["engine"] == "memoryos-pypi"
    assert config["source_mode"] == "memoryos-pypi-wrapper"
    assert config["llm_model"] == "gpt-4o-mini"
    assert config["embedding_model_name"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert config["short_term_capacity"] == 10
    assert config["mid_term_capacity"] == 2000
    assert config["long_term_knowledge_capacity"] == 100
    assert config["retrieval_queue_capacity"] == 7
    assert config["top_k_sessions"] == 5
    assert config["top_k_knowledge"] == 20
    assert method["source"]["source_sha256"] == expected_source["source_sha256"]
    assert method["source"]["vendored_source_sha256"] == expected_source["vendored_source_sha256"]
    assert method["source"]["wrapper_sha256"] == expected_source["wrapper_sha256"]
    assert track["implementation_variant"] == "product"
    assert track["readout_track"] == "unified"
    assert track["native_scope"] == "none"
    assert track["embedding_profile"] == "product_default_v1"
    assert track["embedding"] == {
        "provider": "sentence-transformers",
        "model": "sentence-transformers/all-MiniLM-L6-v2",
        "dimension": 384,
        "revision": None,
        "revision_status": "local_unpinned",
        "normalization": "external_l2",
        "instruction": None,
        "distance": "faiss-inner-product",
        "identity_status": "declared",
    }

    predictions = read_jsonl(run_dir / "artifacts/method_predictions.jsonl")
    answers = read_jsonl(run_dir / "artifacts/answer_prompts.prediction.jsonl")
    assert len(predictions) == case["questions"], (run_dir, len(predictions))
    assert len(answers) == case["questions"], (run_dir, len(answers))
    assert len({row["conversation_id"] for row in predictions}) == case["conversations"]
    for row in answers:
        assert isinstance(row["formatted_memory"], str) and row["formatted_memory"].strip()
        assert isinstance(row["retrieved_items"], list) and row["retrieved_items"]
        if case["benchmark"] == "halumem":
            assert "retrieval_query_top_k" not in row
        else:
            assert row["retrieval_query_top_k"] == 10
        evidence = row["retrieval_evidence"]
        assert evidence["semantic_provenance"]["status"] == "valid"
        assert evidence["provenance_granularity"] == "turn"
        assert evidence["stable_ranking"]["status"] == "pending"
        for item in row["retrieved_items"]:
            mode = item["metadata"]["selection_mode"]
            if mode in {"always_on", "ranked"}:
                assert item["source_turn_ids"]
            else:
                assert mode == "non_evidence"
                assert item["source_turn_ids"] == []

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
        observation_path = run_dir / f"artifacts/efficiency_observations.{metric}.jsonl"
        inventory_path = run_dir / f"artifacts/model_inventory.{metric}.json"
        observations = read_jsonl(observation_path)
        assert inventory_path.is_file(), inventory_path
        if metric == "halumem_extraction":
            assert observations == []
        else:
            assert observations, (run_dir, metric)

    state_root = run_dir / "method_state"
    worker_dirs = sorted(state_root.glob("worker_*"))
    if case["workers"] == 1:
        assert worker_dirs == [], (run_dir, worker_dirs)
    else:
        assert len(worker_dirs) == case["workers"], (run_dir, worker_dirs)
    sidecars = sorted(state_root.glob("worker_*/*/memory-benchmark-sidecar.json"))
    if not sidecars:
        sidecars = sorted(state_root.glob("*/memory-benchmark-sidecar.json"))
    assert len(sidecars) == case["conversations"], (run_dir, sidecars)
    all_pages = []
    for sidecar_path in sidecars:
        sidecar = read_json(sidecar_path)
        assert sidecar["schema_version"] == 1
        assert isinstance(sidecar["pages"], dict) and sidecar["pages"]
        assert all(ids and all(isinstance(turn_id, str) and turn_id for turn_id in ids)
                   for ids in sidecar["pages"].values())
        if case["benchmark"] == "locomo":
            assert set(sidecar["speaker_map"]) == {"speaker_a", "speaker_b"}
        else:
            assert sidecar["speaker_map"] is None
        state_dir = sidecar_path.parent
        short_term_paths = list((state_dir / "users").glob("*/short_term.json"))
        assert len(short_term_paths) == 1, state_dir
        pages = json.loads(short_term_paths[0].read_text(encoding="utf-8"))
        assert isinstance(pages, list) and pages
        for page in pages:
            assert (str(page.get("user_input", "")).strip()
                    or str(page.get("agent_response", "")).strip())
            ids = page.get("meta_data", {}).get("_memory_benchmark_source_turn_ids")
            assert isinstance(ids, list) and ids
        all_pages.extend(pages)

    if case["benchmark"] == "locomo":
        assert any("[Sharing image that shows:" in (
            str(page.get("user_input", "")) + str(page.get("agent_response", ""))
        ) for page in all_pages)
        if case["conversations"] == 2:
            assert any(not str(page.get("user_input", "")).strip() for page in all_pages)
            assert any(not str(page.get("agent_response", "")).strip() for page in all_pages)
    if case["benchmark"] == "membench":
        third_pages = []
        for sidecar_path in sidecars:
            if "third-" not in sidecar_path.parent.name:
                continue
            short_path = next((sidecar_path.parent / "users").glob("*/short_term.json"))
            third_pages.extend(json.loads(short_path.read_text(encoding="utf-8")))
        assert third_pages and all(not page["agent_response"] for page in third_pages)
        assert all(page["timestamp"] is not None for page in all_pages)

    for log_name in case["logs"]:
        assert (run_dir / "logs" / log_name).is_file(), (run_dir, log_name)
    print(
        f"PASS {run_dir.name}: benchmark={case['benchmark']}, "
        f"questions={case['questions']}, workers={case['workers']}, evidence=valid/turn"
    )

halu_dir = cases[-1]["run_dir"]
reports = read_jsonl(halu_dir / "artifacts/session_memory_reports.jsonl")
probes = read_jsonl(halu_dir / "artifacts/update_probe_results.jsonl")
assert len(reports) == 4
assert [row["session_ref"]["session_id"] for row in reports] == ["s1", "s2", "s3", "s4"]
assert all(row == {
    "session_ref": row["session_ref"], "memories": [], "metadata": {}, "status": "n/a"
} for row in reports)
assert len(probes) == 7
assert all(row["memories_from_system"] for row in probes)

extraction = read_json(halu_dir / "summaries/summary.halumem_extraction.json")
update = read_json(halu_dir / "summaries/summary.halumem_update.json")
qa = read_json(halu_dir / "summaries/summary.halumem_qa.json")
memory_type = read_json(halu_dir / "summaries/summary.halumem_memory_type.json")
assert extraction["status"] == "n/a"
assert extraction["total_questions"] == 0
assert extraction["category_breakdown"] == []
assert "memory_update" in update["overall_score"]
assert "question_answering" in qa["overall_score"]
assert qa["category_breakdown"] and all(
    row.get("category") and row.get("qa_num", 0) > 0
    for row in qa["category_breakdown"]
)
assert memory_type["status"] == "n/a"
assert memory_type["reason_code"] == "upstream_extraction_n_a"
assert memory_type["mean_score"] is None
assert memory_type["category_breakdown"] == []
assert len(read_jsonl(
    halu_dir / "artifacts/efficiency_observations.halumem_update.jsonl"
)) == 7
assert len(read_jsonl(
    halu_dir / "artifacts/efficiency_observations.halumem_qa.jsonl"
)) == 1
print(
    "PASS MemoryOS current-v2 shared-lifecycle five-grid B11 machine gate: "
    "8 runs, exact page lineage, worker isolation, all eligible metrics and "
    "HaluMem N/A propagation present"
)
PY
```

## 9. 执行后回报

只需把以下两段原样发给架构师；其余 terminal log、manifest、artifact、state 与 summary 由
架构师直接从 run 目录开箱，不需要把整段终端输出粘进聊天：

1. HaluMem `JUDGE_CALL_PREVIEW ...` 尾行；
2. 统一机器验货的全部 `PASS ...` 尾行，尤其最后一行。

任何命令或机器门失败时，保留完整 run 目录与 log，停止后续付费步骤；不要自行删目录、改
artifact 或为了过门修改校验脚本。
