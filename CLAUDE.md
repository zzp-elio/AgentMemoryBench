# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv run pytest                    # 完整回归（默认排除 real API）
uv run pytest -q                 # 简洁输出，709 passed 为正常
uv run pytest -m memoryos -q    # MemoryOS 专项
uv run pytest -m api --collect-only -q  # 查看哪些测试会调真实 API
uv run pytest -x -q tests/test_method_registry.py  # 单个测试文件
uv run python -m compileall -q src/memory_benchmark tests  # 编译检查
uv run memory-benchmark --help   # CLI 帮助
uv run python -m memory_benchmark --help  # 等价入口
uv sync                          # 同步依赖（首次或有新依赖时）
```

- 默认 `-m "not api"` 排除付费 API
- 当前是 git repo，分支 `main`；除非用户明确要求，否则不自动 commit

## Architecture

### Core data flow
```
BenchmarkAdapter.load() → Dataset
  ↓ (public Conversation + Question, no gold_answers)
run_predictions()  → method.add([Convsersation]) → method.get_answer(Question)
  ↓ (artifacts: method_predictions.jsonl + evaluator_private_labels.jsonl)
run_artifact_evaluation() → evaluator.evaluate(question, prediction, gold)
  ↓ (scores: answer_scores.*.jsonl)
```

### Three registries (declarative, no Cartesian product)
- **BenchmarkRegistry**: task family + required capabilities + prediction_enabled
- **MethodRegistry**: task families + provided capabilities + system_factory + source_identity
- **EvaluatorRegistry**: supported_benchmarks + requires_api + factory

Compatibility check at runtime: `validate_compatibility(benchmark_task_family, required_caps, method_task_families, provided_caps)`

### Method interface
当前主协议为 `BaseMemoryProvider`（retrieve-first）：
- `add(conversation: Conversation) → AddResult`
- `retrieve(question: Question) → RetrievalResult`

旧协议 `BaseMemorySystem` 仍保留为兼容路径：
- `add(conversations: list[Conversation]) → AddResult`
- `get_answer(question: Question) → AnswerResult`

Optional: `BaseMemoryRetriever` (retrieve)

### Private data protection (4-layer)
1. **Data model**: `Conversation.to_public_dict()` excludes gold_answers
2. **Runner rebuild**: `_make_public_conversation()` deep-copies with `gold_answers={}`
3. **Key scan**: `validate_no_private_keys()` recurses into all dicts, matching 12 blacklisted keys
4. **Manifest check**: forbid api_key/secret/token/password keys

### Resume system
- Full manifest comparison: dataset_sha256 + policy + method config, exact `==` match
- Read-only preflight before any directory/file creation
- Turn-level checkpoint state machine: `ready → in_flight → completed`
  - in_flight states **never auto-resume** (can't confirm if API was processed server-side)
- Atomic writes: tmp file → fsync → os.replace
- JSONL torn tail recovery: silently drops incomplete last line if no trailing newline

### Source directories
| Path | Purpose |
|------|---------|
| `src/memory_benchmark/core/` | Entities, interfaces, validators, exceptions, capabilities (no I/O) |
| `src/memory_benchmark/config/` | .env loading, TOML profile parsing, path resolution |
| `src/memory_benchmark/benchmark_adapters/` | Raw data → unified Dataset (LoMoCo, LongMemEval) |
| `src/memory_benchmark/methods/` | Method wrappers (Mem0, MemoryOS, A-MEM, Mock) + registry |
| `src/memory_benchmark/runners/` | Prediction engine (generic) + evaluation engine + ingest resume |
| `src/memory_benchmark/evaluators/` | Metric calculators (F1, LLM judge) + registry |
| `src/memory_benchmark/observability/` | Progress reporter, event writer, run context, efficiency collector |
| `src/memory_benchmark/storage/` | Atomic file writes, fingerprint, JSONL, experiment paths |
| `src/memory_benchmark/cli/` | CLI main, command service, unified prediction service |
| `tests/` | 51 test files, pytest with markers |
| `data/` | Benchmark raw data (locomo10.json, longmemeval_*.json, mem_gallery/) |
| `third_party/methods/` | Vendored method source code (MemoryOS-main, mem0-main, A-mem) |
| `third_party/benchmarks/` | Vendored benchmark reference code (HaluMem, LoCoMo, LongMemEval, etc.) |
| `configs/methods/` | Method TOML profiles (mem0.toml, memoryos.toml) |
| `configs/evaluators/` | Evaluator TOML profiles (llm_judge.toml) |
| `outputs/` | Run artifacts (protected experiments not to be modified) |
| `docs/workstreams/` | Active workstreams: per-line README (status page) + spec + plan |
| `docs/reference/` | Long-lived reference docs (architecture, data model, method interfaces) |
| `docs/survey/` | Benchmark survey cards, dataset structures, official eval workflows |
| `docs/archive/` | Read-only history: completed specs/plans/handoffs/status docs |

### Key entry points
- `cli/main.py:main()` — CLI entry (`memory-benchmark`)
- `cli/commands.py:execute_predict/evaluate/run()` — command orchestration
- `cli/run_prediction.py:run_registered_conversation_qa_prediction()` — 13-step unified assembly
- `runners/prediction.py:run_predictions()` — generic prediction engine (~2100 lines)
- `runners/evaluation.py:run_artifact_evaluation()` — artifact-only evaluation
- `runners/ingest_resume.py` — TurnIngestCheckpointStore, load_completed_conversation_ids
- `benchmark_adapters/registry.py` — BenchmarkRegistry, _build_default_registry
- `methods/registry.py` — MethodRegistration, get_method_registration, list_methods
- `evaluators/registry.py` — EvaluatorRegistration, list_metrics, create_evaluator
- `config/profiles.py` — load_typed_profile (TOML → strong-typed dataclass)

## Key constraints
- Do not modify `third_party/` source code
- Do not call external API without `--confirm-api` / `--confirm-full`
- All Python files must have Chinese module docstring; classes/functions need Chinese docstrings
- Private data (gold answers, evidence, judge labels) must never reach method
- New method adapter: implement BaseMemorySystem → register in `methods/registry.py`
- New benchmark adapter: implement BenchmarkAdapter + register in `benchmark_adapters/registry.py`
- Review required for: resume logic, privacy boundaries, metric correctness, public protocol changes
