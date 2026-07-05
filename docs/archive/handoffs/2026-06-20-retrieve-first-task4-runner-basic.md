# 2026-06-20 Retrieve-First Task 4 Basic Runner Path Handoff

## Completed

- `run_predictions()` now accepts either legacy `BaseMemorySystem` or new
  `BaseMemoryProvider`.
- Non-isolated ingest supports `BaseMemoryProvider.add(conversation)` while preserving the
  legacy `BaseMemorySystem.add([conversation])` path.
- `_answer_conversation_questions()` branches between:
  - retrieve-first: `provider.retrieve(question)` -> `FrameworkAnswerReader.generate_answer()`
  - legacy: `system.get_answer(question)`
- Added `_validate_retrieval()` for strict question/conversation/context alignment and private
  metadata checks.
- Added `retrievals` to `_ConversationAnswerBatch`.
- `_answer_pending_questions()` persists `retrieval_results.prediction.jsonl` for retrieve-first
  batches.
- Added `RecordingMemoryProvider` and
  `test_runner_uses_retrieve_first_provider_and_framework_reader()` in
  `tests/test_prediction_runner.py`.

## TDD Evidence

RED:

```bash
uv run pytest tests/test_prediction_runner.py::test_runner_uses_retrieve_first_provider_and_framework_reader -q
```

Failed as expected with:

```text
TypeError: run_predictions() got an unexpected keyword argument 'answer_reader'
```

GREEN:

```bash
uv run pytest tests/test_prediction_runner.py::test_runner_uses_retrieve_first_provider_and_framework_reader -q
```

Result:

```text
1 passed
```

Focused runner regression:

```bash
uv run pytest tests/test_prediction_runner.py tests/test_prediction_efficiency_observations.py -q
```

Result:

```text
63 passed
```

Focused combined verification:

```bash
uv run pytest tests/test_retrieve_first_protocol.py tests/test_framework_answer_reader.py tests/test_prediction_runner.py tests/test_prediction_efficiency_observations.py tests/test_documentation_standards.py tests/test_method_registry.py -q
```

Result:

```text
87 passed
```

Static checks:

```bash
uv run python -m compileall -q src/memory_benchmark tests/test_retrieve_first_protocol.py tests/test_framework_answer_reader.py tests/test_prediction_runner.py
git diff --check -- src/memory_benchmark/core src/memory_benchmark/readers src/memory_benchmark/storage/experiment_paths.py src/memory_benchmark/runners/prediction.py tests/test_retrieve_first_protocol.py tests/test_framework_answer_reader.py tests/test_prediction_runner.py AGENTS.md docs/current-roadmap.md docs/task-ledger.md docs/superpowers/plans/2026-06-20-retrieve-first-memory-module.md docs/handoffs/2026-06-20-retrieve-first-task2-task3-reader-artifacts.md
```

Both exited 0.

## Important Limitations

- Task 5 is not done: if retrieval is persisted but answer fails, resume still does not reuse the
  persisted retrieval record.
- Isolated worker retrieve-first provider path is not migrated yet.
- `injected_memory_context_tokens` is recorded as `None` for the framework-owned retrieve-first
  path. Task 14 should decide the canonical tokenizer source for framework reader context tokens.
- Built-in method adapters still expose legacy `get_answer()` as their runner-facing path.
- No commit was created because the repository has many pre-existing uncommitted OpenCode/Codex
  changes.

## Next Step

Continue with Task 5 in
`docs/superpowers/plans/2026-06-20-retrieve-first-memory-module.md`: reuse completed retrieval
artifacts when answer generation failed before prediction persistence.
