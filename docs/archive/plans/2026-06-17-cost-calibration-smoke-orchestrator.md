# Cost Calibration Smoke Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增加一个不触网可测试的外层 smoke 矩阵调度入口，用于后续 OhMyGPT 成本校准。

**Architecture:** 新增 runner 级 `cost_calibration` 模块负责 method × benchmark child run 调度；CLI command service 只做参数承载和转发；现有 registered prediction service 继续负责 benchmark/method 装配、resume、artifact 和 efficiency observation。

**Tech Stack:** Python dataclass、ThreadPoolExecutor、现有 `run_registered_conversation_qa_prediction()`、pytest、Rich CLI JSON 输出。

---

### Task 1: Cost Calibration Runner

**Files:**
- Create: `src/memory_benchmark/runners/cost_calibration.py`
- Test: `tests/test_cost_calibration_smoke.py`

- [x] **Step 1: 写失败测试**

覆盖：

- command 校验 method/benchmark/run_prefix/max_parallel_runs。
- 每个 method × benchmark 都调用 registered prediction。
- 每次调用都强制 `enable_efficiency_observability=True`。
- 单个 child run 异常不会阻止其他 child run。

- [x] **Step 2: 实现 runner**

新增 `CalibrationSmokeCommand`、`CalibrationChildRunResult`、`CalibrationSmokeSummary` 和
`run_cost_calibration_smoke()`。

- [x] **Step 3: 运行 focused tests**

```bash
uv run pytest tests/test_cost_calibration_smoke.py -q
```

### Task 2: CLI Command Service

**Files:**
- Modify: `src/memory_benchmark/cli/commands.py`
- Modify: `src/memory_benchmark/cli/main.py`
- Test: `tests/test_main_cli.py`

- [x] **Step 1: 写失败测试**

覆盖：

- `PredictCommand` 可传递 `enable_efficiency_observability`。
- `predict --enable-efficiency-observability` 传到底层 registered prediction。
- `calibrate-smoke` 参数解析为强类型 command。
- calibration summary 有失败时 CLI 返回非 0。

- [x] **Step 2: 实现 CLI/service**

新增 `CalibrationSmokeCliCommand` 和 `execute_calibrate_smoke()`；`main` 增加
`calibrate-smoke` 子命令。

- [x] **Step 3: 运行 focused tests**

```bash
uv run pytest tests/test_main_cli.py tests/test_cost_calibration_smoke.py -q
```

### Task 3: Roadmap, AGENTS, Handoff

**Files:**
- Modify: `docs/current-roadmap.md`
- Modify: `AGENTS.md`
- Create: `docs/handoffs/2026-06-17-cost-calibration-smoke.md`

- [x] **Step 1: 更新当前路线图**

在 Phase J 下新增成本校准 smoke 子任务，并标记实现状态。

- [x] **Step 2: 更新入口断点**

在 `AGENTS.md` 当前断点中记录该入口已实现但未执行真实 API。

- [x] **Step 3: 写 handoff**

记录命令示例、验证结果、未执行真实 API 和下一步需要用户确认的参数。

### Task 4: Final Verification

**Files:**
- All modified files

- [x] **Step 1: 运行 focused tests**

```bash
uv run pytest tests/test_cost_calibration_smoke.py tests/test_main_cli.py tests/test_documentation_standards.py -q
```

- [x] **Step 2: 编译检查**

```bash
uv run python -m compileall -q src/memory_benchmark tests
```

- [x] **Step 3: 检查 git diff**

确认没有修改 protected `data/`、`models/`、`outputs/` 或第三方源码。

