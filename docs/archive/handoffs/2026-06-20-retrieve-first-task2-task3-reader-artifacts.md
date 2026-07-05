# 2026-06-20 Retrieve-First Task 2-3 Reader and Artifact Paths Handoff

## Completed

Task 2:

- Added `src/memory_benchmark/readers/answer.py`.
- Added `src/memory_benchmark/readers/__init__.py`.
- Added `tests/test_framework_answer_reader.py`.
- `FrameworkAnswerReader` now turns a public `Question` plus
  `RetrievalResult.formatted_context` into an `AnswerResult`.
- `AnswerPromptTemplate` validates `{question}` and `{memory_context}` placeholders.
- `FakeAnswerLLMClient` records prompts and never calls a real API.
- Reader fails closed on empty retrieval context, mismatched question/conversation ids, and
  empty LLM output.

Task 3:

- Added `ExperimentPaths.retrieval_results_path`.
- Added `ExperimentPaths.answer_prompts_path`.
- Added focused path test in `tests/test_prediction_runner.py`.

## TDD Evidence

Task 2 RED:

```bash
uv run pytest tests/test_framework_answer_reader.py -q
```

Failed as expected with:

```text
ModuleNotFoundError: No module named 'memory_benchmark.readers'
```

Task 2 GREEN:

```bash
uv run pytest tests/test_framework_answer_reader.py -q
```

Result:

```text
7 passed
```

Task 3 RED:

```bash
uv run pytest tests/test_prediction_runner.py::test_experiment_paths_include_retrieval_and_answer_prompt_artifacts -q
```

Failed as expected with:

```text
AttributeError: 'ExperimentPaths' object has no attribute 'retrieval_results_path'
```

Task 3 GREEN:

```bash
uv run pytest tests/test_prediction_runner.py::test_experiment_paths_include_retrieval_and_answer_prompt_artifacts -q
```

Result:

```text
1 passed
```

Focused combined verification:

```bash
uv run pytest tests/test_retrieve_first_protocol.py tests/test_framework_answer_reader.py tests/test_prediction_runner.py::test_experiment_paths_include_retrieval_and_answer_prompt_artifacts tests/test_documentation_standards.py tests/test_method_registry.py -q
```

Result:

```text
25 passed
```

Static checks:

```bash
uv run python -m compileall -q src/memory_benchmark/readers src/memory_benchmark/storage/experiment_paths.py tests/test_framework_answer_reader.py tests/test_prediction_runner.py tests/test_retrieve_first_protocol.py
git diff --check -- src/memory_benchmark/readers src/memory_benchmark/storage/experiment_paths.py tests/test_framework_answer_reader.py tests/test_prediction_runner.py docs/superpowers/plans/2026-06-20-retrieve-first-memory-module.md
```

Both exited 0.

## Review Note

Claude Code was used for a read-only review, but that review mixed in unrelated pre-existing
dirty worktree changes and did not see untracked reader files from a plain `git diff`.
Do not treat that review as authoritative for Task 2. Its useful coverage concern was handled
locally by adding fail-closed tests for id mismatch and empty LLM output.

## Not Done

- Runner does not yet call `BaseMemoryProvider.retrieve`.
- Retrieval and answer prompt artifacts are not written yet; only stable paths exist.
- No commit was created because the repository has many pre-existing uncommitted
  OpenCode/Codex changes.

## Next Step

Continue with Task 4 in
`docs/superpowers/plans/2026-06-20-retrieve-first-memory-module.md`: add the retrieve-first
runner path with a fake provider.
