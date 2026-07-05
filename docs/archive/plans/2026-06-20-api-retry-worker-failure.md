# API Retry and Worker Failure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make long prediction runs resilient to transient API/network failures and let conversation-level worker failures be quarantined without stopping unrelated conversations.

**Architecture:** The runner keeps a per-run work plan where each conversation is attempted at most once. Isolated workers return both successful batches and failed conversation records; the coordinator serially commits both. Mem0 receives adapter-level API timeout/retry settings and applies them to vendored OpenAI LLM/embedding clients after construction, avoiding third-party algorithm changes.

**Tech Stack:** Python 3.12, pytest, dataclasses, `ThreadPoolExecutor`, OpenAI Python SDK, existing `uv` workflow.

---

## File Map

- Modify `src/memory_benchmark/runners/prediction.py`: isolated worker return types, failure handling, failed conversation checkpoint writes, optional consecutive-failure policy.
- Modify `tests/test_prediction_runner.py`: update old fail-fast test and add retry-failed/max-new-conversations edge tests.
- Modify `src/memory_benchmark/methods/mem0_adapter.py`: Mem0 network config fields and OpenAI client `with_options()` application.
- Modify `configs/methods/mem0.toml`: expose Mem0 timeout/retry values for smoke and official profiles.
- Modify `tests/test_mem0_adapter.py`: assert Mem0 production clients receive timeout/retry options.
- Modify `docs/current-roadmap.md`, `docs/task-ledger.md`, `AGENTS.md`: update task status after implementation.

## Task 1: Isolated Worker Continues After Conversation Failure

**Files:**
- Modify: `tests/test_prediction_runner.py`
- Modify: `src/memory_benchmark/runners/prediction.py`

- [ ] **Step 1: Write the failing test**

Replace `test_isolated_worker_failure_stops_remaining_conversation_work` with a test named `test_isolated_worker_marks_failed_conversation_and_continues_work`.

Expected test behavior:

```python
def test_isolated_worker_marks_failed_conversation_and_continues_work(tmp_path: Path) -> None:
    """单个 conversation 失败后应标记 failed，但 worker 继续后续 conversation。"""
```

The fake system should make `worker_0` fail on `conv-1`, then confirm `worker_0` still reaches `conv-3`, while `worker_1` reaches `conv-2` and `conv-4`. Assert:

```python
assert conversation_status["conv-1"]["status"] == "failed"
assert conversation_status["conv-3"]["status"] == "completed"
assert conversation_status["conv-2"]["status"] == "completed"
assert conversation_status["conv-4"]["status"] == "completed"
assert ("worker_0", "add", "conv-3") in calls
assert ("worker_1", "add", "conv-4") in calls
assert len(prediction_records) == 3
```

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/test_prediction_runner.py::test_isolated_worker_marks_failed_conversation_and_continues_work -q
```

Expected: fail because current `_run_isolated_worker_pipeline()` raises after the first worker error.

- [ ] **Step 3: Implement worker failure batches**

In `prediction.py`, add a `_ConversationFailureBatch` dataclass carrying:

```python
conversation_id: str
stage: str
error_type: str
error: str
traceback_text: str
```

Change `_isolated_worker()` to catch exceptions per work item, append a failure batch, and continue to the next work item instead of raising `_ConversationWorkItemError`.

Change `_run_isolated_worker_pipeline()` to:

- merge success batches as today,
- write failed conversation status for failure batches,
- log `conversation_failed_isolated`,
- not set `cancellation_event` for local conversation failures,
- only raise for worker-level/global exceptions such as factory failure.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
uv run pytest tests/test_prediction_runner.py::test_isolated_worker_marks_failed_conversation_and_continues_work -q
```

Expected: pass.

## Task 2: Retry-Failed and Max-New-Conversations Contracts

**Files:**
- Modify: `tests/test_prediction_runner.py`
- Modify: `src/memory_benchmark/runners/prediction.py` only if tests expose a gap.

- [ ] **Step 1: Add contract tests**

Add tests covering:

1. `max_new_conversations=4` attempts at most 4 eligible conversations and records completed + failed within that budget.
2. `retry_failed_conversations=True` includes historical failed conversations in eligible selection.
3. A failed conversation is not retried twice in the same run.
4. `max_workers > eligible conversations` starts only non-empty chunks.

- [ ] **Step 2: Verify RED or Existing GREEN**

Run:

```bash
uv run pytest tests/test_prediction_runner.py -k "max_new_conversations or retry_failed or fewer_than_num_chunks or marks_failed_conversation" -q
```

Expected: existing max worker edge tests may pass; retry-failed same-run behavior should be verified explicitly.

- [ ] **Step 3: Implement only missing behavior**

If current `_build_prediction_work_plan()` already enforces the contract, keep production code unchanged. If a gap appears, fix only that gap.

- [ ] **Step 4: Verify**

Run the same focused command and expect pass.

## Task 3: Mem0 API Timeout and Retry Settings

**Files:**
- Modify: `src/memory_benchmark/methods/mem0_adapter.py`
- Modify: `configs/methods/mem0.toml`
- Modify: `tests/test_mem0_adapter.py`

- [ ] **Step 1: Write failing tests**

Add fake OpenAI clients with `with_options()` methods and assert Mem0 applies:

```python
timeout == config.api_timeout_seconds
max_retries == config.api_max_retries
```

Cover both:

- `backend.llm.client`
- `backend.embedding_model.client`

Also assert `Mem0Config` rejects non-positive timeout or negative retries.

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/test_mem0_adapter.py -k "timeout or retries" -q
```

Expected: fail because `Mem0Config` lacks fields and adapter does not call `with_options()`.

- [ ] **Step 3: Implement Mem0 network config**

Add fields to `Mem0Config`:

```python
api_timeout_seconds: float = 60.0
api_max_retries: int = 8
```

Validate:

```python
if self.api_timeout_seconds <= 0: raise ConfigurationError(...)
if self.api_max_retries < 0: raise ConfigurationError(...)
```

Include fields in smoke/full factory methods, TOML profiles, and public manifest.

Add `_configure_backend_openai_clients()` called after backend construction and before observers. It should:

- find `self._memory.llm.client`,
- find `self._memory.embedding_model.client`,
- if client has `with_options`, replace it with `client.with_options(timeout=..., max_retries=...)`,
- if absent, leave it unchanged for fake/non-OpenAI clients.

Reader client is already built with `OpenAISettings.to_client_kwargs()`, so do not double wrap unless tests show it missing.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
uv run pytest tests/test_mem0_adapter.py -k "timeout or retries or production_config" -q
```

Expected: pass.

## Task 4: Focused Regression

**Files:**
- Tests only unless failures reveal integration gaps.

- [ ] **Step 1: Run focused runner and method tests**

```bash
uv run pytest tests/test_prediction_runner.py tests/test_mem0_adapter.py tests/test_method_registry.py tests/test_config_profiles.py tests/test_main_cli.py -q
```

Expected: pass.

- [ ] **Step 2: Run documentation and syntax checks**

```bash
git diff --check
uv run pytest tests/test_documentation_standards.py -q
uv run python -m compileall -q src/memory_benchmark tests
```

Expected: all pass.

## Task 5: Documentation and Git Boundary

**Files:**
- Modify: `docs/current-roadmap.md`
- Modify: `docs/task-ledger.md`
- Modify: `AGENTS.md`
- Optional create: `docs/handoffs/2026-06-20-api-retry-worker-failure.md`

- [ ] **Step 1: Update task statuses**

Mark worker failure policy and Mem0 retry/timeout as closed only after focused tests pass. If tests pass but real API smoke is still pending, mark as `partially_closed` with the exact remaining smoke command.

- [ ] **Step 2: Record handoff**

Create a short handoff with:

- files changed,
- tests run,
- behavior changes,
- real API not run unless explicitly done.

- [ ] **Step 3: Decide git action**

Because the worktree contains many OpenCode changes, stage only files touched in this implementation if committing. If unrelated dirty files make a clean commit risky, leave uncommitted and state that clearly.
