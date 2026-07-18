# LightMem × LoCoMo B11 真实 smoke 命令包

> 状态：2026-07-17 两次真实 predict 与全部当时适用 evaluator 已执行，架构师完成开箱
> 验货并裁定通过。正式证据见
> [`lightmem-frozen-v2.md`](lightmem-frozen-v2.md)。本 note 保留当时命令并修正两处验货
> 模板错误：terminal log 归入各 run 的 `logs/`，单 worker state 不带 `worker_0/` 子层。
> 2026-07-18：上述状态只对应 v6 历史 run；v7 改变公共 readout/embedding observation，
> LoCoMo current-v7 的受影响 B4/B7/B11 已重新打开，旧 run 不得 resume 或冒充当前证据。

## 1. 为什么是两次 run

- `lm-locomo-v6-r3q1-w1`：1 conversation × 3 rounds × 1 question × 1 worker，验证最小真实
  build/retrieve/answer 链，并覆盖首个 caption turn `D1:5`。
- `lm-locomo-v6-r3q1-c2-w2`：2 conversations × 3 rounds × 每 conversation 1 question ×
  2 workers。至少两段 conversation 才会真实调度两个 worker；只跑一段却写
  `--workers 2` 不能作为并行证据。

两条 predict 命令必须前后串行，不得在两个 shell 同时启动；第二条内部的 workers=2 才是本次
要验的并行层。smoke 不支持 resume，失败后保留现场，交回架构师裁决新 run_id，禁止删目录后
假装首次执行。

## 2. 环境与变量

```bash
cd /Users/wz/Desktop/memoryBenchmark
set -o pipefail

git status --short
git log -5 --oneline
git diff --quiet
git diff --cached --quiet
test -f .env
test -f data/locomo/locomo10.json
test -d models/all-MiniLM-L6-v2
test -d models/llmlingua-2-bert-base-multilingual-cased-meetingbank

RUN_W1=lm-locomo-v6-r3q1-w1
RUN_W2=lm-locomo-v6-r3q1-c2-w2
RUN_ROOT=outputs/runs/lightmem/locomo/smoke/unified
RUN_DIR_W1="$RUN_ROOT/$RUN_W1"
RUN_DIR_W2="$RUN_ROOT/$RUN_W2"
TMP_LOG_ROOT="${TMPDIR:-/tmp}/memory-benchmark-lightmem-b11"

test ! -e "$RUN_DIR_W1"
test ! -e "$RUN_DIR_W2"
mkdir -p "$TMP_LOG_ROOT"
```

`git status --short` 可以显示用户已有 untracked 私有资产；真正的门是两条
`git diff --quiet`，确保没有 tracked/暂存改动混入实验身份。不要打印或 `cat .env`。

## 3. 单 worker predict + 已实现全部 LoCoMo evaluator

```bash
uv run memory-benchmark predict smoke --root . --method lightmem --benchmark locomo --config-track unified --run-id "$RUN_W1" --rounds 3 --conversations 1 --questions-per-conversation 1 --workers 1 --allow-api 2>&1 | tee "$TMP_LOG_ROOT/$RUN_W1.predict.log"
PREDICT_STATUS=$?
mkdir -p "$RUN_DIR_W1/logs"
mv "$TMP_LOG_ROOT/$RUN_W1.predict.log" "$RUN_DIR_W1/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0

uv run memory-benchmark evaluate --root . --run-id "$RUN_W1" --metric locomo-f1 --metric f1 --metric locomo-recall --workers 1 2>&1 | tee "$RUN_DIR_W1/logs/terminal.evaluate-offline.log"

uv run memory-benchmark evaluate --root . --run-id "$RUN_W1" --metric locomo-judge --judge-profile compact --workers 1 --allow-api 2>&1 | tee "$RUN_DIR_W1/logs/terminal.evaluate-judge.log"
```

离线命令包含当前已注册的全部无 API LoCoMo 指标；judge 单独执行，避免付费失败掩盖前三项
已经成功写盘的事实。

## 4. 两 worker 并行 predict + 同一 evaluator 集合

只在 §3 三条命令都返回 shell exit 0 后执行：

```bash
uv run memory-benchmark predict smoke --root . --method lightmem --benchmark locomo --config-track unified --run-id "$RUN_W2" --rounds 3 --conversations 2 --questions-per-conversation 1 --workers 2 --allow-api 2>&1 | tee "$TMP_LOG_ROOT/$RUN_W2.predict.log"
PREDICT_STATUS=$?
mkdir -p "$RUN_DIR_W2/logs"
mv "$TMP_LOG_ROOT/$RUN_W2.predict.log" "$RUN_DIR_W2/logs/terminal.predict.log"
test "$PREDICT_STATUS" -eq 0

uv run memory-benchmark evaluate --root . --run-id "$RUN_W2" --metric locomo-f1 --metric f1 --metric locomo-recall --workers 2 2>&1 | tee "$RUN_DIR_W2/logs/terminal.evaluate-offline.log"

uv run memory-benchmark evaluate --root . --run-id "$RUN_W2" --metric locomo-judge --judge-profile compact --workers 2 --allow-api 2>&1 | tee "$RUN_DIR_W2/logs/terminal.evaluate-judge.log"
```

## 5. 机器验货（零 API）

六条运行命令均成功后，在同一 shell 执行：

```bash
uv run python - <<'PY'
from __future__ import annotations

import json
from pathlib import Path

root = Path("outputs/runs/lightmem/locomo/smoke/unified")
cases = (
    ("lm-locomo-v6-r3q1-w1", 1, 1),
    ("lm-locomo-v6-r3q1-c2-w2", 2, 2),
)
summary_names = (
    "summary.f1.json",
    "summary.locomo_f1.json",
    "summary.locomo_recall.json",
    "summary.locomo_judge_accuracy.json",
)

for run_id, expected_questions, expected_workers in cases:
    run_dir = root / run_id
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    config = manifest["method"]["config"]
    assert manifest["run_id"] == run_id
    assert manifest["benchmark_name"] == "locomo"
    assert manifest["policy"]["max_workers"] == expected_workers
    assert config["adapter_version"] == "conversation-qa-v6"
    assert config["messages_use"] == "hybrid"
    assert config["lifecycle_profile"] == "online_soft"
    assert config["retrieve_limit"] == 60

    prediction_path = run_dir / "artifacts/method_predictions.jsonl"
    answer_path = run_dir / "artifacts/answer_prompts.prediction.jsonl"
    prediction_rows = [
        json.loads(line)
        for line in prediction_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    answer_rows = [
        json.loads(line)
        for line in answer_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(prediction_rows) == expected_questions
    assert len(answer_rows) == expected_questions
    for row in answer_rows:
        assert row["retrieval_query_top_k"] == 10
        assert isinstance(row["retrieved_items"], list)
        evidence = row["retrieval_evidence"]
        assert evidence["semantic_provenance"]["status"] == "valid"
        assert evidence["provenance_granularity"] == "turn"
        assert evidence["stable_ranking"]["status"] == "pending"

    for name in summary_names:
        assert (run_dir / "summaries" / name).is_file(), (run_id, name)
    assert (run_dir / "artifacts/efficiency_observations.prediction.jsonl").stat().st_size > 0
    assert (run_dir / "artifacts/model_inventory.prediction.json").is_file()

    state_root = run_dir / "method_state"
    worker_dirs = sorted(state_root.glob("worker_*"))
    if expected_workers == 1:
        # 非 isolated 路径直接使用 run 级 method_state，不额外造 worker_0。
        assert worker_dirs == []
        qdrant_roots = (state_root / "qdrant",)
    else:
        assert len(worker_dirs) == expected_workers
        qdrant_roots = tuple(worker / "qdrant" for worker in worker_dirs)
    assert all(root.is_dir() and any(root.iterdir()) for root in qdrant_roots)
    for terminal_name in (
        "terminal.predict.log",
        "terminal.evaluate-offline.log",
        "terminal.evaluate-judge.log",
    ):
        assert (run_dir / "logs" / terminal_name).is_file()
    print(f"PASS {run_id}: questions={expected_questions}, workers={expected_workers}")
PY
```

本脚本只验结构、身份、逐题 Recall 资格、效率记录与 worker state 隔离，不把 smoke 分数高低当作
效果结论。Recall 可为 0；judge 可判错。只要流程和 artifact 合同正确，低分不是 B11 失败。

## 6. 架构师回收结果

两组 run 均已通过结构、身份、逐题 Recall 复算、效率观测与 worker state 隔离门；六份 terminal
log 已从旧的全局 `outputs/terminal-logs/` 移入各自 run 的 `logs/`。双 worker terminal tee
没有显示最终 JSON，但 run 内 `logs/run.log` 与 `logs/events.jsonl` 均有正式 `run_completed`，
artifact/checkpoint 计数完整，因此裁为显示层缺口而非 prediction 失败。

Answer Metric Pack M0 合入后，可在这两个 run_id 上只追加
`evaluate --metric normalized-em --metric substring-em`；不重跑 predict。
