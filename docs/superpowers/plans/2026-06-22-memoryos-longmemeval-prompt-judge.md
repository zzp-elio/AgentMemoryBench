# MemoryOS LongMemEval Prompt And Judge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional MemoryOS PyPI generic LongMemEval prompt profile and align LongMemEval judge defaults with LightMem's LongMemEval flow.

**Architecture:** Keep MemoryOS default LongMemEval profile as `lightmem_longmemeval_reader_v1`; add `memoryos_pypi_generic_v1` behind explicit config. Override LongMemEval judge call/compact parsing only inside the LongMemEval evaluator so other evaluators stay unchanged.

**Tech Stack:** Python dataclasses, pytest/unittest, OpenAI-compatible chat completions, project TOML profiles.

---

### Task 1: MemoryOS Prompt Profile Tests

**Files:**
- Modify: `tests/test_memoryos_adapter.py`
- Modify: `tests/test_config_profiles.py`

- [x] Add a test that `MemoryOSPaperConfig(longmemeval_prompt_profile="memoryos_pypi_generic_v1")` builds LongMemEval `prompt_messages` containing MemoryOS PyPI markers: role-play instruction, `<CONTEXT>`, `<MEMORY>`, `<USER TRAITS>`, question time, retrieval text, user profile, and assistant knowledge.
- [x] Add a test that unknown `longmemeval_prompt_profile` raises `ConfigurationError`.
- [x] Add config profile assertions that project TOML keeps the default `lightmem_longmemeval_reader_v1`.

### Task 2: MemoryOS Prompt Profile Implementation

**Files:**
- Modify: `src/memory_benchmark/methods/memoryos_adapter.py`
- Modify: `configs/methods/memoryos.toml`

- [x] Add constants for allowed LongMemEval prompt profiles.
- [x] Add `longmemeval_prompt_profile` to `MemoryOSPaperConfig`, `to_manifest()`, and TOML profiles.
- [x] Pass the selected profile into `_build_memoryos_answer_prompt()`.
- [x] Implement `memoryos_pypi_generic_v1` branch using MemoryOS PyPI prompt structure while reusing existing MemoryOS short/mid/long-term formatting.

### Task 3: LongMemEval Judge Tests

**Files:**
- Modify: `tests/test_llm_judge_parsing.py`

- [x] Add a fake Chat Completions client test proving `LongMemEvalJudgeEvaluator(mode="compact")` calls `chat.completions.create()` with `temperature=0.0`, `top_p=0.8`, `max_tokens=2000`.
- [x] Add compact parse tests for LightMem-style `yes` and `no` outputs through `LongMemEvalJudgeEvaluator.evaluate()`.

### Task 4: LongMemEval Judge Implementation

**Files:**
- Modify: `src/memory_benchmark/evaluators/longmemeval_judge.py`

- [x] Override compact output instruction to request yes/no only.
- [x] Override `evaluate()` or compact parsing so yes/no outputs become `MetricResult` booleans.
- [x] Override `_call_model_with_usage()` to use Chat Completions and LightMem-compatible parameters.
- [x] Keep detailed mode compatible with existing JSON parser for debug use.

### Task 5: Documentation And Verification

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/current-roadmap.md`
- Modify: `docs/method-interface-inventory.md`

- [x] Record MemoryOS LongMemEval prompt profile choices and A-Mem no-generic-prompt finding.
- [x] Record LongMemEval judge now follows LightMem flow for comparability.
- [x] Run focused tests:
  `uv run pytest tests/test_memoryos_adapter.py tests/test_config_profiles.py tests/test_llm_judge_parsing.py -q`
- [x] Run a wider no-API check:
  `uv run pytest tests/test_evaluator_registry.py tests/test_method_registry.py tests/test_documentation_standards.py -q`
- [x] Run `uv run python -m compileall -q src/memory_benchmark tests` and `git diff --check`.
