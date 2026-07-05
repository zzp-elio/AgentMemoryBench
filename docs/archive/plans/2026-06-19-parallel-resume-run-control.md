# Parallel Resume Run Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make serial, conversation-parallel, isolated-worker, and method×benchmark-parallel prediction safely resumable, and add a per-command `max_new_conversations` budget for staged experiments.

**Architecture:** Add a generic work-planning layer inside `src/memory_benchmark/runners/prediction.py`. The planner reads persisted conversation/question state, selects unfinished conversations within the command budget, and feeds both normal and isolated execution paths. CLI and calibrate-smoke only pass run-control arguments through; method adapters remain unchanged.

**Tech Stack:** Python dataclasses, pytest, existing `PredictionRunPolicy`, existing JSONL/JSON checkpoint storage, Rich progress artifacts.

---

## File Map

- Modify: `src/memory_benchmark/runners/prediction.py`
  - Add run-control policy field.
  - Add `_ConversationWorkItem` / `_PredictionWorkPlan`.
  - Make normal and isolated branches consume the same work plan.
- Modify: `src/memory_benchmark/cli/run_prediction.py`
  - Accept and pass `max_new_conversations`.
- Modify: `src/memory_benchmark/cli/main.py`
  - Add CLI flag for `predict`, `run`, and `calibrate-smoke` if applicable.
- Modify: `src/memory_benchmark/cli/commands.py`
  - Add command dataclass field if current CLI command objects require it.
- Modify: `src/memory_benchmark/runners/cost_calibration.py`
  - Add child-run budget field and forward it to registered prediction.
- Modify: `tests/test_prediction_runner.py`
  - Add focused normal/isolated resume and budget tests.
- Modify: `tests/test_main_cli.py`
  - Add CLI flag plumbing tests.
- Modify: `tests/test_cost_calibration_smoke.py`
  - Add budget forwarding tests.
- Modify: `AGENTS.md`, `README.md`, `docs/current-roadmap.md`
  - Record final behavior and remaining constraints.

## Task 1: Add Policy Field and Work Plan Tests

**Files:**
- Modify: `src/memory_benchmark/runners/prediction.py`
- Modify: `tests/test_prediction_runner.py`

- [x] **Step 1: Add failing tests for budget selection**

Add tests that create a small fake dataset with four conversations and one question each. Use existing fake systems in `tests/test_prediction_runner.py` where possible.

Expected test cases:

```python
def test_prediction_budget_limits_new_unfinished_conversations(tmp_path):
    """max_new_conversations=2 时只推进前两个未完成 conversation。"""
```

```python
def test_prediction_budget_skips_already_completed_conversations_on_resume(tmp_path):
    """resume 时预算应跳过已完成 conversation，继续后续未完成 conversation。"""
```

Run:

```bash
uv run pytest tests/test_prediction_runner.py -k "budget" -q
```

Expected: tests fail because policy/work plan does not exist.

- [x] **Step 2: Extend `PredictionRunPolicy`**

In `src/memory_benchmark/runners/prediction.py`, add:

```python
max_new_conversations: int | None = None
```

Validation:

```python
if self.max_new_conversations is not None and self.max_new_conversations < 1:
    raise ConfigurationError("max_new_conversations must be at least 1")
```

Do not add this field to `_build_manifest()` policy payload.

- [x] **Step 3: Add work-plan dataclasses**

Add internal dataclasses near `_ConversationAnswerBatch`:

```python
@dataclass(frozen=True)
class _ConversationWorkItem:
    """本次命令要处理的单个 conversation 工作项。"""

    conversation: Conversation
    needs_ingest: bool
    pending_questions: tuple[Question, ...]


@dataclass(frozen=True)
class _PredictionWorkPlan:
    """本次命令裁剪后的 prediction 工作计划。"""

    items: tuple[_ConversationWorkItem, ...]
    selected_questions: dict[str, list[Question]]
    question_order: tuple[str, ...]
    completed_question_ids: frozenset[str]
    ingested_conversation_ids: frozenset[str]
    dataset_conversation_count: int
    budget_exhausted: bool
```

- [x] **Step 4: Implement `_build_prediction_work_plan()`**

Inputs:

```python
def _build_prediction_work_plan(
    *,
    conversations: list[Conversation],
    selected_questions: dict[str, list[Question]],
    conversation_status: dict[str, Any],
    prediction_records: dict[str, dict[str, Any]],
    policy: PredictionRunPolicy,
) -> _PredictionWorkPlan:
```

Rules:

- `ingested_conversation_ids` comes from `conversation_status[conversation_id]["status"] == "completed"`.
- `completed_question_ids` comes from `prediction_records`.
- A conversation is unfinished if it is not ingested or has any selected question missing.
- Apply `max_new_conversations` after filtering completed conversations.
- Keep dataset order.

- [x] **Step 5: Make normal path consume the work plan**

Inside `run_predictions()`:

- Build `work_plan` after loading persisted state.
- Pass only `work_plan.items` conversations that need ingest to `_ingest_pending_conversations()`.
- Pass only `work_plan.items` and pending questions to `_answer_pending_questions()`.

If a helper needs list/dict conversion, keep that conversion local and obvious.

- [x] **Step 6: Verify tests pass**

Run:

```bash
uv run pytest tests/test_prediction_runner.py -k "budget" -q
```

Expected: new budget tests pass.

## Task 2: Fix Isolated Worker Resume

**Files:**
- Modify: `src/memory_benchmark/runners/prediction.py`
- Modify: `tests/test_prediction_runner.py`

- [x] **Step 1: Add failing tests for isolated resume**

Add tests:

```python
def test_isolated_worker_skips_completed_questions_on_resume(tmp_path):
    """isolated worker resume 不应重复调用已完成 question。"""
```

```python
def test_isolated_worker_restores_completed_conversation_state(tmp_path):
    """已完成 ingest 但未答完问题的 conversation 应传给 worker factory 恢复状态。"""
```

```python
def test_isolated_worker_rejects_turn_checkpoint_resume(tmp_path):
    """存在 turn-level checkpoint 时 isolated worker 应 fail closed。"""
```

Run:

```bash
uv run pytest tests/test_prediction_runner.py -k "isolated_worker" -q
```

Expected: new tests fail with current isolated branch.

- [x] **Step 2: Change `_run_isolated_worker_pipeline()` signature**

Replace raw `conversations` / `selected_questions` scheduling with:

```python
work_plan: _PredictionWorkPlan
```

Keep `prediction_records`, `question_status`, and `question_order` in coordinator.

- [x] **Step 3: Reject turn checkpoint in isolated mode**

Before spawning workers:

```python
if any(paths.ingest_turn_checkpoints_dir.glob("*.json")):
    raise ConfigurationError(
        "Isolated worker prediction cannot resume turn-level ingest checkpoints"
    )
```

This protects Mem0-like partial ingest from accidental isolated replay.

- [x] **Step 4: Build worker contexts with completed conversations**

For each chunk:

```python
completed_for_chunk = tuple(
    _make_public_conversation(item.conversation)
    for item in chunk
    if not item.needs_ingest
)
```

Pass `completed_for_chunk` to `MethodBuildContext.completed_conversations`.

- [x] **Step 5: Make `_isolated_worker()` consume work items**

Change worker loop to:

```python
for item in work_items:
    public_conversation = _make_public_conversation(item.conversation)
    if item.needs_ingest:
        system.add([public_conversation])
    for source_question in item.pending_questions:
        ...
```

It must not see already completed questions.

- [x] **Step 6: Seed progress counters from persisted state**

Use:

```python
conversation_completed = len(work_plan.ingested_conversation_ids)
question_answered = len(work_plan.completed_question_ids)
```

Progress should never double-count resumed predictions.

- [x] **Step 7: Verify isolated tests**

Run:

```bash
uv run pytest tests/test_prediction_runner.py -k "isolated_worker or budget" -q
```

Expected: all related tests pass.

## Task 3: CLI and Calibrate-Smoke Plumbing

**Files:**
- Modify: `src/memory_benchmark/cli/main.py`
- Modify: `src/memory_benchmark/cli/run_prediction.py`
- Modify: `src/memory_benchmark/cli/commands.py`
- Modify: `src/memory_benchmark/runners/cost_calibration.py`
- Modify: `tests/test_main_cli.py`
- Modify: `tests/test_cost_calibration_smoke.py`

- [x] **Step 1: Add CLI tests**

Add a `tests/test_main_cli.py` case verifying:

```bash
memory-benchmark predict ... --max-new-conversations 2
```

passes `max_new_conversations=2` into `run_registered_conversation_qa_prediction()`.

Add a calibrate-smoke test verifying the field is forwarded to each child run.

- [x] **Step 2: Add CLI flag**

In `src/memory_benchmark/cli/main.py`, add:

```python
parser.add_argument(
    "--max-new-conversations",
    type=int,
    default=None,
    help="Only process this many unfinished conversations in this invocation; "
    "not part of experiment identity and can change across resume commands.",
)
```

Wire the value through `run_prediction.py` and command dataclasses.

- [x] **Step 3: Add calibrate-smoke field**

In `CalibrationSmokeCommand`, add:

```python
max_new_conversations: int | None = None
```

Validate positive when present. Forward it in `_run_one_task()`.

- [x] **Step 4: Verify CLI plumbing**

Run:

```bash
uv run pytest tests/test_main_cli.py tests/test_cost_calibration_smoke.py -q
```

Expected: tests pass.

## Task 4: Summary, Events, and Documentation

**Files:**
- Modify: `src/memory_benchmark/runners/prediction.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/current-roadmap.md`
- Add or modify tests in `tests/test_prediction_runner.py`

- [x] **Step 1: Record run control in logs and summary metadata**

Add a `run_control` record to `run_started` event payload:

```python
"run_control": {
    "max_new_conversations": policy.max_new_conversations,
    "budget_exhausted": work_plan.budget_exhausted,
}
```

If changing `PredictionRunSummary`, keep backward compatibility by adding optional fields at the end or a `metadata` dict.

- [x] **Step 2: Add summary test**

Verify partial budget run records `max_new_conversations` and `budget_exhausted`.

- [x] **Step 3: Update README**

Add a short section under prediction/run usage:

```text
Use --max-new-conversations N to run experiments in batches. It is a per-command
budget, not an experiment identity field, so later resume commands may use a
different value.
```

- [x] **Step 4: Update roadmap and AGENTS**

Mark spec/plan created and record next implementation checkpoint.

- [x] **Step 5: Verify docs and focused suite**

Run:

```bash
uv run pytest tests/test_documentation_standards.py tests/test_prediction_runner.py tests/test_main_cli.py tests/test_cost_calibration_smoke.py -q
uv run python -m compileall -q src/memory_benchmark tests
git diff --check
```

Expected: all pass.

## Task 5: Safety Review Before Real API

**Files:**
- No code ownership by default; review only unless a focused issue is found.

- [x] **Step 1: Review invariants**

Check:

- `max_new_conversations` is not in manifest identity.
- resume with a different `max_new_conversations` is allowed.
- resume with changed method/source/dataset remains rejected.
- isolated worker does not re-add completed conversations.
- isolated worker does not re-answer completed questions.
- Mem0 LoCoMo turn-level resume tests still pass.

- [x] **Step 2: Run focused regression**

Run:

```bash
uv run pytest tests/test_mem0_adapter.py tests/test_prediction_runner.py tests/test_method_registry.py tests/test_config_profiles.py -q
```

Expected: pass without real API.

- [x] **Step 3: Update handoff**

Create:

```text
docs/handoffs/YYYY-MM-DD-parallel-resume-run-control.md
```

Record:

- implemented behavior
- tests run
- remaining known limitations
- whether real API is still blocked

## Self-Review Notes

- The plan keeps run control in the runner layer, not method TOML.
- The plan does not add method × benchmark specialized runners.
- The plan keeps Mem0 LoCoMo turn-level resume.
- The plan treats isolated worker turn checkpoint as unsupported and fail-closed.
- The plan does not require real API.
