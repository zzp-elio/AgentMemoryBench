# OpenCode 任务：修复并行 smoke 终端展示与 stdout 捕获

## 任务身份

你现在不是“机械执行者”，而是 Codex 额度空档期的正式外部推进副手。你可以做实质开发，
但必须完整记录你的设计、修改文件、测试命令和结果到：

```text
opencode/opencode_result.md
```

Codex 恢复后会逐项复核你的 diff 和验证证据。

## 必读入口

请先读：

1. `AGENTS.md`
2. `docs/current-roadmap.md`
3. `docs/handoffs/2026-06-19-parallel-resume-run-control.md`
4. `docs/handoffs/2026-06-19-low-quota-checkpoint.md`
5. `opencode/opencode_result.md` 中你上次关于 Rich 修复的记录

## 当前背景

`calibrate-smoke` 并行跑多个 method×benchmark child run 时，终端 Rich 输出仍有问题：

- 多个 child run 的进度条或 Live 输出会交错。
- 第三方 warning/stdout 会插入进度区。
- 有时 elapsed 秒数或 stage 显示停住，但后台实验仍在运行。

目标是让并行 smoke 运行时由外层 orchestrator 统一展示状态，而不是每个 child run 各自
操作 Rich Live。

## 主任务

实现并验证：

1. 当 `calibrate-smoke --max-parallel-runs > 1` 时：
   - child run 内部 Rich progress 必须关闭。
   - orchestrator 主线程用单个 Rich `Live(Table)` 展示所有 child run 状态。
   - 展示字段至少包括：method、benchmark、status、stage、conversation progress、
     question progress、elapsed、run_id、error。
2. 当 `--max-parallel-runs == 1` 时：
   - 保持单 child run 原有 Rich progress 行为，不强制使用总表。
3. 第三方 stdout/stderr/warning：
   - 不得直接污染 Rich Live 区域。
   - 需要被重定向到每个 child run 对应日志，或被外层安全捕获后写入结构化/文本日志。
   - 不得吞掉异常堆栈；失败时 CLI 仍应能显示明确 error type 和 message。

## 可接受实现方向

- 优先复用或修正已有：
  - `src/memory_benchmark/runners/calibration_progress.py`
  - `src/memory_benchmark/runners/cost_calibration.py`
  - `src/memory_benchmark/observability/progress_reporter.py`
- 如果已有 `CalibrationProgressMonitor` 设计有 bug，请修它，不要再新建一套平行实现。
- 尽量通过 `progress.json` 作为 child run 与 orchestrator 的状态边界。
- 不要为了终端显示修改 method adapter 的核心算法。

## 暂缓任务

prediction artifact 瘦身暂时不要直接做大改。你可以：

- 写一份简短设计建议到 `opencode/opencode_result.md`。
- 或添加不会破坏现有行为的红测草案。

但不要删除 `method_predictions.jsonl` 现有字段，避免破坏 evaluator 复用。

## 禁止事项

- 不要运行 full 实验。
- 不要调用真实 API；本任务必须用 fake/offline 测试。
- 不要修改 `.env`。
- 不要提交 `data/`、`models/`、`outputs/`、`tmp/` 里的大文件。
- 不要改 PrefEval。
- 不要修改第三方核心算法，除非只是可关闭、可审计的 stdout/observer 层改动。

## 必须新增或修复的测试

优先补充离线测试：

```bash
uv run pytest tests/test_calibration_progress_monitor.py tests/test_cost_calibration_smoke.py -q
```

如果你改了 CLI：

```bash
uv run pytest tests/test_main_cli.py -q
```

如果你改了 runner/progress：

```bash
uv run pytest tests/test_prediction_runner.py tests/test_cost_calibration_smoke.py -q
```

最后至少运行：

```bash
uv run pytest tests/test_documentation_standards.py tests/test_cost_calibration_smoke.py tests/test_calibration_progress_monitor.py -q
uv run python -m compileall -q src/memory_benchmark tests
git diff --check
```

## 结果记录要求

在 `opencode/opencode_result.md` 中追加：

1. 你读了哪些文件。
2. 你认为问题根因是什么。
3. 修改了哪些文件，每个文件改了什么。
4. 跑了哪些测试，完整结果是什么。
5. 还有哪些已知风险或没解决的问题。
6. 如果你无法修复，写清楚卡点、复现步骤和下一步建议。
