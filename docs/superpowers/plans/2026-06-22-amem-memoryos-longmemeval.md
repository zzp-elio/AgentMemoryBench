# A-Mem / MemoryOS LongMemEval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make A-Mem and MemoryOS run LongMemEval through the retrieve-first pipeline without dropping method-specific memory context.

**Architecture:** Keep each method's memory construction and retrieval algorithm unchanged. Add benchmark-aware LongMemEval reader prompt construction in A-Mem and MemoryOS, using LightMem-style LongMemEval role messages while preserving each method's retrieved memory details.

**Tech Stack:** Python dataclasses, pytest, OpenAI-compatible answer reader settings, existing conversation-QA runner artifacts.

---

### Task 1: A-Mem LongMemEval Reader Prompt

**Files:**
- Modify: `src/memory_benchmark/methods/amem_adapter.py`
- Test: `tests/test_amem_adapter.py`

- [x] Add a test that builds a LongMemEval-style `Question(question_time=...)`, calls `AMem.retrieve()`, and asserts the returned `prompt_messages` are `system + user`.
- [x] Assert the user prompt contains `Question time:<date> and question:<question>` and the A-Mem memory context returned by `find_related_memories_raw()`.
- [x] Implement `_is_longmemeval_question()` and route `_build_answer_prompt()` / prompt messages to `lightmem_longmemeval_reader_v1` when true.
- [x] Keep A-Mem `query_keywords`, `retrieve_k`, and `answer_context` metadata unchanged.

### Task 2: MemoryOS LongMemEval Reader Prompt

**Files:**
- Modify: `src/memory_benchmark/methods/memoryos_adapter.py`
- Test: `tests/test_memoryos_adapter.py`

- [x] Add a test that builds a LongMemEval-style conversation with user/assistant turns and `question_time`.
- [x] Patch `state.retrieval_system.retrieve()` to return a retrieval queue and long-term knowledge without API calls.
- [x] Assert the LongMemEval prompt uses `system: You are a helpful assistant.` and a user message containing question time, question, recent context, retrieved memory, user profile/knowledge, and assistant knowledge.
- [x] Implement LongMemEval branch in `_build_memoryos_answer_prompt()` while preserving the existing LoCoMo branch.

### Task 3: Answer LLM Settings

**Files:**
- Modify: `src/memory_benchmark/config/settings.py`
- Test: existing focused config/registered prediction tests or add assertions to method-specific tests.

- [x] Add `("amem", "longmemeval")` and `("memoryos", "longmemeval")` to `resolve_answer_llm_settings()`.
- [x] Use LightMem LongMemEval parameters: `temperature=0.0`, `top_p=0.8`, `max_tokens=2000`.
- [x] Verify these settings are reflected in focused tests.

### Task 4: Official LongMemEval Judge Prompt

**Files:**
- Modify: `src/memory_benchmark/evaluators/longmemeval_judge.py`
- Test: `tests/test_llm_judge_parsing.py`

- [x] Replace the simplified LongMemEval judge prompt with the official task-specific templates from `third_party/benchmarks/LongMemEval-main/src/evaluation/evaluate_qa.py`.
- [x] Preserve compact output parsing compatibility.
- [x] Add tests for temporal, knowledge-update, preference, and abstention prompt branches.

### Task 5: Documentation And Focused Verification

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/current-roadmap.md`
- Modify: `docs/task-ledger.md`

- [x] Record that A-Mem/MemoryOS LongMemEval support uses LightMem-style reader prompts with method-specific context preserved.
- [x] Run focused pytest for A-Mem, MemoryOS, settings, LongMemEval judge, and documentation standards.
- [x] Run `uv run python -m compileall -q src/memory_benchmark tests`.
- [x] Run `git diff --check`.
