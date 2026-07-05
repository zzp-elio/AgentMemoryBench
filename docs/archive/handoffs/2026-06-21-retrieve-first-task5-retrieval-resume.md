# 2026-06-21 Retrieve-First Task 5 Retrieval Resume Handoff

## Completed

- Added `FailingAnswerClient` and
  `test_resume_reuses_completed_retrieval_when_answer_failed()` in
  `tests/test_prediction_runner.py`.
- Added `_RetrieveFirstAnswerError` to carry completed retrieval records when framework answer
  generation fails after successful retrieval.
- Added `_persist_retrieval_records()` for stable `question_order`-ordered
  `retrieval_results.prediction.jsonl` writes.
- `_answer_pending_questions()` now persists completed retrieval records from a failed
  retrieve-first answer batch before re-raising the original answer error.
- `_answer_conversation_questions()` now accepts existing retrieval records and reuses them before
  calling `provider.retrieve()`.
- Added `_answer_question_retrieve_first_or_reuse()` and `_retrieval_from_record()`.

## TDD Evidence

Initial RED:

```bash
uv run pytest tests/test_prediction_runner.py::test_resume_reuses_completed_retrieval_when_answer_failed -q
```

The first version of the test used two conversations and exposed an unrelated executor behavior:
the second submitted conversation could run before the failing future propagated. The test was
corrected to use one conversation with two questions.

Final RED:

```bash
uv run pytest tests/test_prediction_runner.py::test_resume_reuses_completed_retrieval_when_answer_failed -q
```

Failed as expected because retrieval was not persisted before answer failure:

```text
assert [] == ['conv-1:q1']
```

GREEN:

```bash
uv run pytest tests/test_prediction_runner.py::test_resume_reuses_completed_retrieval_when_answer_failed -q
```

Result:

```text
1 passed
```

Focused regression:

```bash
uv run pytest tests/test_prediction_runner.py::test_runner_uses_retrieve_first_provider_and_framework_reader tests/test_prediction_runner.py::test_resume_reuses_completed_retrieval_when_answer_failed tests/test_prediction_runner.py tests/test_prediction_efficiency_observations.py -q
```

Result:

```text
64 passed
```

Static checks:

```bash
uv run python -m compileall -q src/memory_benchmark/runners/prediction.py tests/test_prediction_runner.py
git diff --check -- src/memory_benchmark/runners/prediction.py tests/test_prediction_runner.py
```

Both exited 0.

## Review Note

Claude Code read-only review was attempted, but it produced no output after multiple polls and was
interrupted. No Claude Code findings need follow-up for this task.

## Important Limitations

- Isolated worker retrieve-first provider path is still not migrated.
- Built-in method adapters still expose legacy `get_answer()` as their runner-facing path.
- `injected_memory_context_tokens` is still `None` for framework-owned retrieve-first path; Task 14
  should define the tokenizer source and exact recording policy.
- No commit was created because the repository has many pre-existing uncommitted OpenCode/Codex
  changes.

## Next Step

Continue with Task 6 in
`docs/superpowers/plans/2026-06-20-retrieve-first-memory-module.md`: wire the
OpenAI-compatible framework reader and CLI/config prompt options.
