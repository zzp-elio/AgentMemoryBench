# A-Mem Conversation State Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add wrapper-level conversation state persistence for A-Mem so completed conversations can be restored after process restart.

**Architecture:** Keep A-Mem algorithm calls unchanged. Persist only wrapper-managed snapshots of official runtime state after `add([conversation])` completes, and reload them through registry-provided `completed_conversations`.

**Tech Stack:** Python dataclasses, pickle, official A-Mem retriever `save/load`, pytest, existing `ConfigurationError`, existing generic prediction runner.

---

### Task 1: Persistence Contract Tests

**Files:**
- Modify: `tests/test_amem_adapter.py`

- [ ] Add fake retriever `save()` and `load()` behavior to the existing fake runtime.
- [ ] Add a test that calls `AMem.add([conversation])` with `storage_root=tmp_path`, then asserts the state directory contains `memories.pkl`, `retriever.pkl`, `retriever_embeddings.npy`, and `state_manifest.json`.
- [ ] Add a test that creates a second `AMem` with the same `storage_root`, calls `load_existing_conversation_state(conversation)`, then answers a question without calling `add()` again.
- [ ] Add a test that corrupts `state_manifest.json` and expects `ConfigurationError`.
- [ ] Run: `uv run pytest tests/test_amem_adapter.py -q`; expected: new tests fail before implementation.

### Task 2: A-Mem Adapter Persistence

**Files:**
- Modify: `src/memory_benchmark/methods/amem_adapter.py`

- [ ] Add `storage_root` to `AMem.__init__`, defaulting to a safe project output path for direct tests.
- [ ] Add helpers for safe conversation state directory, checksum calculation, atomic manifest write, and state validation.
- [ ] After each conversation completes in `add()`, call `_save_conversation_state(conversation, runtime, turn_count)`.
- [ ] Add `load_existing_conversation_state(conversation)` to create runtime, load `memories.pkl`, call official retriever `load(...)`, and register the runtime.
- [ ] Run: `uv run pytest tests/test_amem_adapter.py -q`; expected: pass.

### Task 3: Registry Resume Wiring

**Files:**
- Modify: `src/memory_benchmark/methods/registry.py`
- Modify: `tests/test_amem_registered_prediction.py` or `tests/test_method_registry.py`

- [ ] Pass `context.storage_root` into `AMem(...)`.
- [ ] After constructing A-Mem, loop over `context.completed_conversations` and call `load_existing_conversation_state(...)`.
- [ ] Add a registry-level test proving completed conversations are loaded without rerunning add.
- [ ] Run focused registry tests.

### Task 4: Documentation and Verification

**Files:**
- Modify: `docs/method-interface-inventory.md`
- Modify: `docs/current-roadmap.md`
- Modify: `AGENTS.md`
- Add: `docs/handoffs/2026-06-18-amem-persistence.md`

- [ ] Update docs from “A-Mem lacks persistence” to “conversation-level persistence implemented”.
- [ ] Run:
  `uv run pytest tests/test_amem_adapter.py tests/test_amem_registered_prediction.py tests/test_method_registry.py tests/test_config_profiles.py -q`
- [ ] Run:
  `uv run pytest tests/test_documentation_standards.py -q`
- [ ] Run:
  `uv run python -m compileall -q src/memory_benchmark tests`
- [ ] Run:
  `git diff --check`
- [ ] Commit with message:
  `feat: persist A-Mem conversation state`
