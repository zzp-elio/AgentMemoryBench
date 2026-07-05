# Efficiency Summary and Safe Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让真实实验在不开 full 的情况下也能精确估算单个 conversation 的 token、latency、API call，并避免失败 conversation 在同一次或默认 resume 中反复空烧 API。

**Architecture:** 保持现有 raw observation JSONL 为事实来源，新增离线聚合层把 observation 汇总成 run/question/conversation 三类可读摘要。并行调度继续使用稳定 worker 分片，不做动态抢任务；失败 conversation 由 checkpoint 显式记录，默认 resume 跳过，只有用户显式请求才重试。

**Tech Stack:** Python dataclass、pytest、现有 `EfficiencyArtifactStore`、`ExperimentPaths`、registered conversation-QA runner、uv。

---

### Task 1: Efficiency Summary Artifacts

**Files:**
- Modify: `src/memory_benchmark/analysis/efficiency.py`
- Modify: `src/memory_benchmark/runners/prediction.py`
- Modify: `src/memory_benchmark/storage/experiment_paths.py`
- Test: `tests/test_efficiency_analysis.py`
- Test: `tests/test_prediction_efficiency_observations.py`

- [x] Write failing tests proving raw observations can be aggregated into:
  - `summaries/efficiency_overall.prediction.json`
  - `summaries/efficiency_by_conversation.prediction.json`
  - `summaries/efficiency_by_question.prediction.json`
- [x] Verify tests fail because summary artifact generation does not exist.
- [x] Implement minimal aggregation from existing observation records; do not change raw JSONL schema.
- [x] Run focused tests.

### Task 2: A-Mem / LightMem API Usage Audit

**Files:**
- Modify: `src/memory_benchmark/methods/amem_adapter.py`
- Modify: `src/memory_benchmark/methods/lightmem_adapter.py`
- Test: `tests/test_amem_adapter.py`
- Test: `tests/test_lightmem_adapter.py`

- [x] Add failing tests that wrapper-visible memory-build LLM calls record `measurement_source=api_usage` when OpenAI-compatible responses expose usage.
- [x] Audit internal memory-build LLM call paths. If calls pass through an adapter-owned client, attach a usage observer. If a third-party path only returns plain text, keep `tokenizer_estimate` and record the limitation in docs.
- [x] Verify A-Mem/LightMem focused tests pass.

### Task 3: Failed Conversation Quarantine

**Files:**
- Modify: `src/memory_benchmark/runners/prediction.py`
- Modify: `src/memory_benchmark/storage/experiment_paths.py`
- Modify: `src/memory_benchmark/cli/main.py`
- Modify: `src/memory_benchmark/cli/commands.py`
- Test: `tests/test_prediction_runner.py`
- Test: `tests/test_main_cli.py`

- [x] Add failing tests that a failed conversation is written once to a failure checkpoint and is skipped by default on resume.
- [x] Add explicit `--retry-failed` to include failed conversations in a later command.
- [x] Ensure a single command still never retries the same conversation.
- [x] Verify focused runner/CLI tests pass.

### Task 4: Documentation and Smoke Gate

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/current-roadmap.md`
- Modify: `docs/task-ledger.md`
- Add: `docs/handoffs/2026-06-19-efficiency-summary-safe-retry.md`

- [ ] Document the required efficiency metric contract and files.
- [ ] Document that dynamic work stealing is intentionally deferred.
- [ ] After offline tests pass, run at most one tiny API smoke if needed to verify API usage observation.
