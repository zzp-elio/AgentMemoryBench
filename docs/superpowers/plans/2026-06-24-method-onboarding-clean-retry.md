# Method Onboarding And Clean Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make custom user methods runnable through a lightweight `BaseMemoryProvider` path while making failed-ingest retry safe by default.

**Architecture:** Built-in methods continue through the existing registry/TOML/deep-instrumentation path. Custom user methods use `--method-class module:ClassName`, are no-arg constructed, must implement `BaseMemoryProvider`, default to `workers=1`, and can only use `workers>1` with `--allow-unsafe-custom-parallel`. Prediction runner states become explicit enough to distinguish answer-stage resume from ingest-stage dirty retry.

**Tech Stack:** Python 3.12, argparse CLI, dataclasses, pytest, existing `memory_benchmark` src-layout, existing conversation-QA runner and framework answer reader.

---

## Implementation Status 2026-06-25

Completed:

- Custom method loader: `src/memory_benchmark/methods/custom_loader.py`.
- CLI selector: `--method-class module:ClassName` and
  `--allow-unsafe-custom-parallel`.
- Custom prediction service path that bypasses built-in method registry/TOML and
  still writes standard prediction / answer prompt artifacts.
- End-to-end fake custom method smoke test.
- Runner status split for dirty retry safety: `failed_ingest` vs `failed_answer`.
  `failed_answer` can resume pending questions without re-ingest; `failed_ingest`
  fails closed on explicit retry unless a future clean retry hook exists.
- User-facing onboarding guide: `docs/custom-method-onboarding.md`.
- Handoff: `docs/handoffs/2026-06-25-custom-method-onboarding-clean-retry.md`.

Verification:

```bash
uv run pytest tests/test_custom_method_loader.py tests/test_main_cli.py tests/test_prediction_cli.py tests/test_prediction_runner.py -q
# 131 passed
```

Remaining non-goals / follow-up:

- Built-in method clean retry hooks or attempt namespace proof.
- Optional `--method-file` single-file quick test path.
- Later cleanup of legacy `BaseMemorySystem`, `BaseResumableMemorySystem`,
  `BaseMemoryRetriever`, and heavy capability inference after retrieve-first is
  fully stable.

---

## File Structure

- Modify `src/memory_benchmark/cli/main.py`
  - Add `--method-class` and `--allow-unsafe-custom-parallel` parsing.
  - Allow `--method` to be optional when `--method-class` is provided.
  - Keep built-in `--method` choices for the existing registry path.
- Modify `src/memory_benchmark/cli/commands.py`
  - Add fields to `PredictCommand`: `method_class`, `allow_unsafe_custom_parallel`.
  - Route custom method prediction to a new service function.
- Modify `src/memory_benchmark/cli/run_prediction.py`
  - Keep built-in method path intact.
  - Add a custom method preparation path that loads a no-arg `BaseMemoryProvider` class and builds a lightweight manifest.
  - Reuse the existing `run_predictions()` runner and framework answer reader.
- Create `src/memory_benchmark/methods/custom_loader.py`
  - Resolve `module:ClassName`, import class, no-arg instantiate, validate `BaseMemoryProvider`.
  - Build a small method manifest without TOML/source identity/deep efficiency requirements.
- Modify `src/memory_benchmark/runners/prediction.py`
  - Introduce explicit conversation statuses: `pending`, `ingesting`, `ingested`, `answering`, `completed`, `failed_ingest`, `failed_answer`.
  - Preserve backward compatibility with existing `failed` / `completed` checkpoint states.
  - Fail closed when `--retry-failed` needs to re-run ingest and no clean retry support exists.
- Modify or create tests:
  - `tests/test_custom_method_loader.py`
  - `tests/test_prediction_cli.py`
  - `tests/test_prediction_runner.py`
  - `tests/test_documentation_standards.py`
- Modify docs:
  - `README.md`
  - `AGENTS.md`
  - `docs/current-roadmap.md`
  - `docs/task-ledger.md`
  - `docs/superpowers/specs/2026-06-24-method-onboarding-simplification-and-clean-retry-design.md` if implementation details reveal a necessary correction.

---

### Task 1: Custom Method Loader

**Files:**
- Create: `src/memory_benchmark/methods/custom_loader.py`
- Test: `tests/test_custom_method_loader.py`

- [ ] **Step 1: Write failing tests for `module:ClassName` loading**

Create `tests/test_custom_method_loader.py` with:

```python
"""测试用户自定义 method 的轻量加载入口。

本模块只验证 `--method-class module:ClassName` 底层 loader，不触碰内置 method
registry、TOML 或真实 API。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from memory_benchmark.core import AddResult, AnswerPromptResult, Conversation, PromptMessage, Question
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.interfaces import BaseMemoryProvider
from memory_benchmark.methods.custom_loader import load_custom_memory_provider


def _write_module(tmp_path: Path, source: str) -> str:
    """写入一个临时 Python module，并返回 importable module 名。"""

    module_path = tmp_path / "custom_adapter.py"
    module_path.write_text(source, encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    return "custom_adapter"


def test_load_custom_memory_provider_instantiates_no_arg_class(tmp_path: Path) -> None:
    """合法用户 adapter 只需无参构造并继承 BaseMemoryProvider。"""

    module_name = _write_module(
        tmp_path,
        '''
from memory_benchmark.core import AddResult, AnswerPromptResult, PromptMessage
from memory_benchmark.core.interfaces import BaseMemoryProvider

class MyMemory(BaseMemoryProvider):
    def add(self, conversation):
        return AddResult(conversation_ids=[conversation.conversation_id])

    def retrieve(self, question):
        return AnswerPromptResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            prompt_messages=[PromptMessage(role="user", content=question.text)],
        )
''',
    )

    provider = load_custom_memory_provider(f"{module_name}:MyMemory")

    assert isinstance(provider, BaseMemoryProvider)


def test_load_custom_memory_provider_rejects_missing_colon() -> None:
    """class path 必须是 module:ClassName，避免用户传入含糊路径。"""

    with pytest.raises(ConfigurationError, match="module:ClassName"):
        load_custom_memory_provider("custom_adapter.MyMemory")


def test_load_custom_memory_provider_rejects_constructor_args(tmp_path: Path) -> None:
    """第一版用户 adapter 必须能无参数构造。"""

    module_name = _write_module(
        tmp_path,
        '''
from memory_benchmark.core.interfaces import BaseMemoryProvider

class NeedsArgs(BaseMemoryProvider):
    def __init__(self, path):
        self.path = path

    def add(self, conversation):
        raise NotImplementedError

    def retrieve(self, question):
        raise NotImplementedError
''',
    )

    with pytest.raises(ConfigurationError, match="no-argument constructor"):
        load_custom_memory_provider(f"{module_name}:NeedsArgs")


def test_load_custom_memory_provider_rejects_wrong_base_class(tmp_path: Path) -> None:
    """用户传入的类必须实现 BaseMemoryProvider。"""

    module_name = _write_module(
        tmp_path,
        '''
class NotMemory:
    pass
''',
    )

    with pytest.raises(ConfigurationError, match="BaseMemoryProvider"):
        load_custom_memory_provider(f"{module_name}:NotMemory")
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
uv run pytest tests/test_custom_method_loader.py -q
```

Expected: FAIL with `ModuleNotFoundError` or import error for `memory_benchmark.methods.custom_loader`.

- [ ] **Step 3: Implement the custom loader**

Create `src/memory_benchmark/methods/custom_loader.py`:

```python
"""用户自定义 method 的轻量加载工具。

该模块只服务普通用户接入路径：通过 `module:ClassName` import 一个无参构造的
`BaseMemoryProvider` 子类。内置 method 仍走 registry/TOML 深度集成路径。
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.interfaces import BaseMemoryProvider


def load_custom_memory_provider(class_path: str) -> BaseMemoryProvider:
    """加载并实例化用户自定义 BaseMemoryProvider。

    输入:
        class_path: `module:ClassName` 格式，例如 `my_pkg.my_adapter:MyMemory`。

    输出:
        BaseMemoryProvider: 无参数构造后的 provider 实例。
    """

    module_name, class_name = _split_class_path(class_path)
    try:
        module = import_module(module_name)
    except Exception as exc:
        raise ConfigurationError(
            f"Cannot import custom method module '{module_name}': {exc}"
        ) from exc
    try:
        cls = getattr(module, class_name)
    except AttributeError as exc:
        raise ConfigurationError(
            f"Custom method class '{class_name}' was not found in '{module_name}'"
        ) from exc
    try:
        instance: Any = cls()
    except TypeError as exc:
        raise ConfigurationError(
            f"Custom method '{class_path}' must provide a no-argument constructor"
        ) from exc
    if not isinstance(instance, BaseMemoryProvider):
        raise ConfigurationError(
            f"Custom method '{class_path}' must inherit BaseMemoryProvider"
        )
    return instance


def _split_class_path(class_path: str) -> tuple[str, str]:
    """解析 `module:ClassName`，并给出明确错误信息。"""

    if ":" not in class_path:
        raise ConfigurationError(
            "Custom method class must use 'module:ClassName' format"
        )
    module_name, class_name = class_path.split(":", 1)
    if not module_name.strip() or not class_name.strip():
        raise ConfigurationError(
            "Custom method class must use 'module:ClassName' format"
        )
    return module_name.strip(), class_name.strip()
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
uv run pytest tests/test_custom_method_loader.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/memory_benchmark/methods/custom_loader.py tests/test_custom_method_loader.py
git commit -m "feat: add custom method class loader"
```

---

### Task 2: CLI Surface For Custom Methods

**Files:**
- Modify: `src/memory_benchmark/cli/main.py`
- Modify: `src/memory_benchmark/cli/commands.py`
- Test: `tests/test_main_cli.py`

- [ ] **Step 1: Write failing CLI argument tests**

Add these tests to `tests/test_main_cli.py`:

```python
def test_predict_accepts_custom_method_class_without_builtin_method(monkeypatch) -> None:
    """用户 method 允许通过 --method-class 指定，且不需要 --method。"""

    captured = {}

    def fake_execute_predict(command):
        captured["command"] = command
        return {"ok": True}

    monkeypatch.setattr("memory_benchmark.cli.main.execute_predict", fake_execute_predict)

    exit_code = main(
        [
            "predict",
            "smoke",
            "--root",
            ".",
            "--method-class",
            "my_pkg.adapter:MyMemory",
            "--benchmark",
            "locomo",
            "--allow-api",
        ]
    )

    assert exit_code == 0
    assert captured["command"].method is None
    assert captured["command"].method_class == "my_pkg.adapter:MyMemory"


def test_predict_rejects_method_and_method_class_together() -> None:
    """内置 method 和用户 method class 不能同时指定。"""

    exit_code = main(
        [
            "predict",
            "smoke",
            "--root",
            ".",
            "--method",
            "mem0",
            "--method-class",
            "my_pkg.adapter:MyMemory",
            "--benchmark",
            "locomo",
            "--allow-api",
        ]
    )

    assert exit_code == 2


def test_custom_method_parallel_requires_explicit_unsafe_flag() -> None:
    """用户 method 默认不允许 workers>1，避免并发污染外部状态。"""

    exit_code = main(
        [
            "predict",
            "smoke",
            "--root",
            ".",
            "--method-class",
            "my_pkg.adapter:MyMemory",
            "--benchmark",
            "locomo",
            "--workers",
            "2",
            "--allow-api",
        ]
    )

    assert exit_code == 2
```

If current `tests/test_main_cli.py` uses helper names different from `main`, adapt only the helper import, not the behavior.

- [ ] **Step 2: Run the targeted CLI tests and verify they fail**

Run:

```bash
uv run pytest tests/test_main_cli.py -q
```

Expected: FAIL because `--method-class` and `--allow-unsafe-custom-parallel` are not parsed.

- [ ] **Step 3: Extend command dataclass**

In `src/memory_benchmark/cli/commands.py`, change `PredictCommand` fields:

```python
@dataclass(frozen=True)
class PredictCommand:
    """生成 method prediction 的运行参数。"""

    project_root: str | Path
    benchmark: str
    profile: str
    method: str | None = None
    method_class: str | None = None
    allow_unsafe_custom_parallel: bool = False
    variant: str | None = None
    run_id: str | None = None
    resume: bool = False
    confirm_api: bool = False
    confirm_full: bool = False
    smoke_turn_limit: int = 20
    smoke_round_limit: int | None = None
    smoke_conversation_limit: int = 1
    smoke_max_workers: int | None = None
    max_new_conversations: int | None = None
    retry_failed_conversations: bool = False
    question_limit_per_conversation: int | None = None
    enable_efficiency_observability: bool = True
    answer_prompt_file: str | Path | None = None
    answer_prompt_profile: str = "default"
    output_layout: str = "flat"
```

Update `execute_predict()` to pass both `method_name=command.method` and `method_class=command.method_class` to the prediction service. If the service does not yet accept `method_class`, add it in Task 3 and keep this call temporarily failing until Task 3.

- [ ] **Step 4: Add CLI arguments and validation**

In `src/memory_benchmark/cli/main.py`:

1. Change `--method` from required to optional:

```python
parser.add_argument("--method", choices=list_methods(), default=None)
```

2. Add custom method args:

```python
parser.add_argument(
    "--method-class",
    default=None,
    help="Custom user method class in module:ClassName format.",
)
parser.add_argument(
    "--allow-unsafe-custom-parallel",
    action="store_true",
    help=(
        "Allow workers>1 for a custom --method-class. The user is responsible "
        "for run, benchmark, worker and conversation isolation."
    ),
)
```

3. In `_prediction_command_from_args()`, validate exactly one of `--method` or `--method-class`:

```python
if bool(args.method) == bool(args.method_class):
    raise MemoryBenchmarkError("Pass exactly one of --method or --method-class")
if args.method_class and normalized["workers"] is not None and normalized["workers"] > 1:
    if not args.allow_unsafe_custom_parallel:
        raise MemoryBenchmarkError(
            "Custom --method-class uses workers=1 by default. Pass "
            "--allow-unsafe-custom-parallel to use workers>1 after confirming "
            "your adapter is safe for parallel runs."
        )
```

4. Return:

```python
return PredictCommand(
    project_root=Path(args.root),
    method=args.method,
    method_class=args.method_class,
    allow_unsafe_custom_parallel=args.allow_unsafe_custom_parallel,
    benchmark=args.benchmark,
    ...
)
```

- [ ] **Step 5: Run CLI tests**

Run:

```bash
uv run pytest tests/test_main_cli.py -q
```

Expected: PASS for existing tests plus the new custom method parsing tests. If `execute_predict()` still fails because Task 3 is not implemented, mark only the service call failure and continue to Task 3 before rerunning the full file.

- [ ] **Step 6: Commit**

```bash
git add src/memory_benchmark/cli/main.py src/memory_benchmark/cli/commands.py tests/test_main_cli.py
git commit -m "feat: expose custom method CLI"
```

---

### Task 3: Custom Prediction Service Path

**Files:**
- Modify: `src/memory_benchmark/cli/run_prediction.py`
- Modify: `src/memory_benchmark/cli/commands.py`
- Test: `tests/test_prediction_cli.py`

- [ ] **Step 1: Write a failing service-level test**

Add to `tests/test_prediction_cli.py`:

```python
def test_custom_method_class_runs_without_builtin_registry(monkeypatch, tmp_path: Path) -> None:
    """自定义 method class 应绕开内置 method TOML/profile/source identity。"""

    calls = {}

    class FakeProvider(BaseMemoryProvider):
        def add(self, conversation):
            return AddResult(conversation_ids=[conversation.conversation_id])

        def retrieve(self, question):
            return AnswerPromptResult(
                question_id=question.question_id,
                conversation_id=question.conversation_id,
                prompt_messages=[PromptMessage(role="user", content=question.text)],
            )

    monkeypatch.setattr(
        "memory_benchmark.cli.run_prediction.load_custom_memory_provider",
        lambda class_path: FakeProvider(),
    )

    def fake_run_predictions(**kwargs):
        calls["kwargs"] = kwargs
        return PredictionRunSummary(
            run_id="custom-smoke",
            dataset_name="locomo",
            total_conversations=1,
            completed_conversations=1,
            total_questions=1,
            completed_questions=1,
            prediction_path="predictions.jsonl",
            private_label_path="labels.jsonl",
            summary_path="summary.json",
        )

    monkeypatch.setattr(
        "memory_benchmark.cli.run_prediction.run_predictions",
        fake_run_predictions,
    )

    result = run_registered_conversation_qa_prediction(
        project_root=tmp_path,
        method_name=None,
        method_class="my_pkg.adapter:MyMemory",
        benchmark_name="locomo",
        profile_name="smoke",
        run_id="custom-smoke",
        confirm_api=True,
        smoke_conversation_limit=1,
        smoke_round_limit=20,
        question_limit_per_conversation=1,
    )

    assert result.runs[0].run_id == "custom-smoke"
    assert calls["kwargs"]["method_manifest"]["method_name"] == "custom"
    assert calls["kwargs"]["policy"].max_workers == 1
```

Import missing names at the top of `tests/test_prediction_cli.py`:

```python
from memory_benchmark.core import AddResult, AnswerPromptResult, PromptMessage
from memory_benchmark.core.interfaces import BaseMemoryProvider
from memory_benchmark.runners.prediction import PredictionRunSummary
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
uv run pytest tests/test_prediction_cli.py::test_custom_method_class_runs_without_builtin_registry -q
```

Expected: FAIL because `run_registered_conversation_qa_prediction()` requires a string `method_name` and uses built-in registry unconditionally.

- [ ] **Step 3: Add custom service parameters**

In `src/memory_benchmark/cli/run_prediction.py`:

1. Import loader:

```python
from memory_benchmark.methods.custom_loader import load_custom_memory_provider
```

2. Change function signature:

```python
def run_registered_conversation_qa_prediction(
    project_root: str | Path,
    method_name: str | None,
    benchmark_name: str,
    profile_name: str = "smoke",
    *,
    method_class: str | None = None,
    allow_unsafe_custom_parallel: bool = False,
    ...
) -> PredictionBatchResult:
```

3. Add early validation:

```python
if bool(method_name) == bool(method_class):
    raise ConfigurationError("Pass exactly one of method_name or method_class")
```

4. Split built-in and custom preparation:
   - Built-in path keeps `get_method_registration()`, `load_method_profile()`, source identity and deep efficiency requirements.
   - Custom path:

```python
is_custom_method = method_class is not None
method_display_name = f"custom:{method_class}"
method_cli_name = "custom"
requires_api = True
use_framework_answer_reader = True
```

5. For custom path:
   - Load benchmark registration normally.
   - Use `RunScope.SMOKE` for smoke profile and `RunScope.FULL` for official-full/formal profile.
   - Build run ids with `"custom"` as method token unless user provides explicit run id.
   - Set max workers from CLI normalized worker value or `1`.
   - If max workers > 1 and `allow_unsafe_custom_parallel` is false, raise `ConfigurationError`.
   - Build method manifest:

```python
method_manifest = {
    "method_name": "custom",
    "method_class": method_class,
    "method_protocol": "BaseMemoryProvider",
    "integration_depth": "user_lightweight",
    "custom_method_contract": {
        "no_arg_constructor": True,
        "conversation_isolation_required": True,
        "parallel_requires_allow_unsafe_custom_parallel": True,
    },
    "answer_reader": answer_reader_manifest,
}
```

6. Create a custom `system_factory`:

```python
def _build_custom_system(_context: MethodBuildContext) -> BaseMemoryProvider:
    if method_class is None:
        raise ConfigurationError("method_class is required")
    return load_custom_memory_provider(method_class)
```

7. Keep the same `run_predictions()` call.

- [ ] **Step 4: Wire `execute_predict()`**

In `src/memory_benchmark/cli/commands.py`, update `execute_predict()`:

```python
return run_registered_conversation_qa_prediction(
    method_name=command.method,
    method_class=command.method_class,
    allow_unsafe_custom_parallel=command.allow_unsafe_custom_parallel,
    benchmark_name=command.benchmark,
    ...
)
```

- [ ] **Step 5: Run service tests**

Run:

```bash
uv run pytest tests/test_prediction_cli.py::test_custom_method_class_runs_without_builtin_registry -q
```

Expected: PASS.

- [ ] **Step 6: Run broader CLI focused tests**

Run:

```bash
uv run pytest tests/test_main_cli.py tests/test_prediction_cli.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/memory_benchmark/cli/run_prediction.py src/memory_benchmark/cli/commands.py tests/test_prediction_cli.py
git commit -m "feat: run custom BaseMemoryProvider predictions"
```

---

### Task 4: Prediction Runner Status Machine And Dirty Retry Guard

**Files:**
- Modify: `src/memory_benchmark/runners/prediction.py`
- Test: `tests/test_prediction_runner.py`

- [ ] **Step 1: Add failing work-plan tests for explicit states**

Add to `tests/test_prediction_runner.py`:

```python
def test_failed_answer_resume_does_not_reingest(tmp_path: Path) -> None:
    """answer 阶段失败后，retry-failed 只补问题，不重新 add。"""

    dataset = _build_two_question_dataset()
    run_context = RunContext.create(
        run_id="failed-answer-resume",
        benchmark_name="fake",
        method_name="fake",
        model_name="fake",
        output_root=tmp_path,
        resume=True,
    )
    atomic_write_json(
        run_context.paths.conversation_status_path,
        {
            "conv-1": {
                "status": "failed_answer",
                "ingested": True,
                "stage": "answer",
            }
        },
    )
    atomic_write_jsonl(
        run_context.paths.method_predictions_path,
        [
            {
                "question_id": "conv-1:q1",
                "conversation_id": "conv-1",
                "question": "问题 1",
                "answer": "old answer",
                "metadata": {},
            }
        ],
    )
    provider = RecordingMemoryProvider()

    run_predictions(
        dataset=dataset,
        system=provider,
        run_context=run_context,
        policy=PredictionRunPolicy(resume=True, retry_failed_conversations=True),
        method_manifest={"method_name": "fake"},
        benchmark_variant="default",
        run_scope=RunScope.FULL,
        answer_reader=FrameworkAnswerReader(client=FakeAnswerLLMClient()),
    )

    assert provider.added_conversation_ids == []
    assert provider.retrieved_question_ids == ["conv-1:q2"]


def test_failed_ingest_retry_without_clean_support_fails_closed(tmp_path: Path) -> None:
    """ingest 阶段失败的 conversation 不能在脏状态上直接重跑。"""

    dataset = _build_dataset()
    run_context = RunContext.create(
        run_id="failed-ingest-resume",
        benchmark_name="fake",
        method_name="fake",
        model_name="fake",
        output_root=tmp_path,
        resume=True,
    )
    atomic_write_json(
        run_context.paths.conversation_status_path,
        {
            "conv-1": {
                "status": "failed_ingest",
                "ingested": False,
                "stage": "ingest",
            }
        },
    )

    with pytest.raises(ConfigurationError, match="clean retry"):
        run_predictions(
            dataset=dataset,
            system=RecordingMemoryProvider(),
            run_context=run_context,
            policy=PredictionRunPolicy(resume=True, retry_failed_conversations=True),
            method_manifest={"method_name": "fake"},
            benchmark_variant="default",
            run_scope=RunScope.FULL,
            answer_reader=FrameworkAnswerReader(client=FakeAnswerLLMClient()),
        )
```

If `FakeAnswerLLMClient` constructor in this repo requires fixed answers, use the existing helper pattern in this file rather than changing the runner behavior.

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/test_prediction_runner.py::test_failed_answer_resume_does_not_reingest tests/test_prediction_runner.py::test_failed_ingest_retry_without_clean_support_fails_closed -q
```

Expected: FAIL because current states are `failed/completed + ingested`.

- [ ] **Step 3: Add status helpers in runner**

In `src/memory_benchmark/runners/prediction.py`, add near `_PredictionWorkPlan`:

```python
_STATUS_PENDING = "pending"
_STATUS_INGESTING = "ingesting"
_STATUS_INGESTED = "ingested"
_STATUS_ANSWERING = "answering"
_STATUS_COMPLETED = "completed"
_STATUS_FAILED_INGEST = "failed_ingest"
_STATUS_FAILED_ANSWER = "failed_answer"


def _conversation_state_status(state: dict[str, Any]) -> str:
    """读取 conversation 当前状态，并兼容旧 checkpoint。"""

    status = str(state.get("status", _STATUS_PENDING))
    if status == "failed":
        return _STATUS_FAILED_ANSWER if state.get("ingested") is True else _STATUS_FAILED_INGEST
    return status


def _conversation_is_ingested(state: dict[str, Any]) -> bool:
    """判断 conversation 是否已经完成 add，可直接继续回答问题。"""

    status = _conversation_state_status(state)
    return status in {
        _STATUS_INGESTED,
        _STATUS_ANSWERING,
        _STATUS_COMPLETED,
        _STATUS_FAILED_ANSWER,
    } or state.get("ingested") is True
```

- [ ] **Step 4: Update work-plan state logic**

Change `_build_prediction_work_plan()`:

```python
ingested_conversation_ids = frozenset(
    conversation.conversation_id
    for conversation in conversations
    if _conversation_is_ingested(
        conversation_status.get(conversation.conversation_id, {})
    )
)
```

Replace failed skip logic:

```python
status = _conversation_state_status(conversation_state)
if status == _STATUS_FAILED_INGEST:
    if not policy.retry_failed_conversations:
        skipped_failed_conversation_ids.append(conversation_id)
        continue
    raise ConfigurationError(
        f"Cannot retry conversation '{conversation_id}' after failed ingest "
        "without clean retry support"
    )
if status == _STATUS_FAILED_ANSWER and not policy.retry_failed_conversations:
    skipped_failed_conversation_ids.append(conversation_id)
    continue
```

This is the first fail-closed implementation. Later tasks can add reset hooks or attempt namespaces.

- [ ] **Step 5: Update status writes**

Update success writes:

```python
conversation_status[conversation_id] = {
    "status": _STATUS_INGESTED,
    "ingested": True,
}
```

after ingest-only completion, and:

```python
conversation_status[conversation_id] = {
    "status": _STATUS_COMPLETED,
    "ingested": True,
}
```

after all selected questions are answered.

Update isolated failure writes:

```python
status = _STATUS_FAILED_ANSWER if batch.ingested else _STATUS_FAILED_INGEST
conversation_status[batch.conversation_id] = {
    "status": status,
    "stage": batch.stage,
    "error_type": batch.error_type,
    "error": batch.error,
    "traceback": batch.traceback_text,
    "ingested": batch.ingested,
}
```

Update non-isolated `_ingest_pending_conversations()` failure writes similarly with `_STATUS_FAILED_INGEST`.

- [ ] **Step 6: Run targeted runner tests**

Run:

```bash
uv run pytest tests/test_prediction_runner.py::test_failed_answer_resume_does_not_reingest tests/test_prediction_runner.py::test_failed_ingest_retry_without_clean_support_fails_closed -q
```

Expected: PASS.

- [ ] **Step 7: Run runner focused tests**

Run:

```bash
uv run pytest tests/test_prediction_runner.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/memory_benchmark/runners/prediction.py tests/test_prediction_runner.py
git commit -m "fix: fail closed on dirty failed ingest retry"
```

---

### Task 5: End-To-End Custom Method Smoke Contract

**Files:**
- Create: `tests/fixtures/custom_method_provider.py`
- Modify: `tests/test_prediction_cli.py`
- Modify: `tests/test_main_cli.py`

- [ ] **Step 1: Create a real fixture custom method**

Create `tests/fixtures/custom_method_provider.py`:

```python
"""pytest 用的用户自定义 method fixture。

它模拟普通用户只实现 BaseMemoryProvider，不接入内置 registry/TOML/source identity。
"""

from __future__ import annotations

from memory_benchmark.core import AddResult, AnswerPromptResult, Conversation, PromptMessage, Question
from memory_benchmark.core.interfaces import BaseMemoryProvider


class FixtureCustomMemory(BaseMemoryProvider):
    """最小用户 memory provider：把 conversation 文本存在进程内 dict。"""

    def __init__(self) -> None:
        """无参数构造，符合用户轻量接入契约。"""

        self._memory_by_conversation: dict[str, str] = {}

    def add(self, conversation: Conversation) -> AddResult:
        """按 conversation_id 写入公开历史。"""

        snippets: list[str] = []
        for session in conversation.sessions:
            for turn in session.turns:
                snippets.append(f"{turn.speaker}: {turn.content}")
        self._memory_by_conversation[conversation.conversation_id] = "\\n".join(snippets)
        return AddResult(conversation_ids=[conversation.conversation_id])

    def retrieve(self, question: Question) -> AnswerPromptResult:
        """构造完整 answer prompt messages。"""

        memory = self._memory_by_conversation.get(question.conversation_id, "")
        return AnswerPromptResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            prompt_messages=[
                PromptMessage(role="system", content="Answer from the provided memory."),
                PromptMessage(
                    role="user",
                    content=f"Memory:\\n{memory}\\n\\nQuestion: {question.text}",
                ),
            ],
            metadata={"answer_context": memory},
        )
```

- [ ] **Step 2: Add end-to-end fake API test**

In `tests/test_prediction_cli.py`, add a test that monkeypatches `OpenAICompatibleAnswerLLMClient` to a fake or uses existing `FakeAnswerLLMClient` path if available from `FrameworkAnswerReader` injection. The test must call the service with:

```python
method_class="tests.fixtures.custom_method_provider:FixtureCustomMemory"
```

and assert:

```python
summary.completed_conversations == 1
summary.completed_questions == 1
```

Also assert `artifacts/answer_prompts.prediction.jsonl` exists and the first record has non-empty `prompt_messages`.

- [ ] **Step 3: Run custom smoke test**

Run:

```bash
uv run pytest tests/test_prediction_cli.py -q
```

Expected: PASS.

- [ ] **Step 4: Run CLI + runner focused suite**

Run:

```bash
uv run pytest tests/test_custom_method_loader.py tests/test_main_cli.py tests/test_prediction_cli.py tests/test_prediction_runner.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/custom_method_provider.py tests/test_prediction_cli.py tests/test_main_cli.py
git commit -m "test: cover lightweight custom method prediction"
```

---

### Task 6: Documentation And User-Facing Example

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/current-roadmap.md`
- Modify: `docs/task-ledger.md`
- Create: `docs/custom-method-onboarding.md`

- [ ] **Step 1: Write custom method onboarding guide**

Create `docs/custom-method-onboarding.md`:

```markdown
# Custom Method Onboarding

This guide is for ordinary users who want to evaluate their own memory method on
AgentMemoryBench conversation + QA benchmarks.

## Minimal Adapter

Create a Python class that inherits `BaseMemoryProvider`:

```python
from memory_benchmark.core import AddResult, AnswerPromptResult, PromptMessage
from memory_benchmark.core.interfaces import BaseMemoryProvider


class MyMemory(BaseMemoryProvider):
    def __init__(self) -> None:
        self.memory_by_conversation = {}

    def add(self, conversation):
        self.memory_by_conversation[conversation.conversation_id] = conversation
        return AddResult(conversation_ids=[conversation.conversation_id])

    def retrieve(self, question):
        conversation = self.memory_by_conversation[question.conversation_id]
        prompt = f"Use this conversation to answer:\\n{conversation}\\n\\n{question.text}"
        return AnswerPromptResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            prompt_messages=[PromptMessage(role="user", content=prompt)],
        )
```

## Run A Smoke Test

```bash
uv run memory-benchmark predict smoke \
  --root . \
  --method-class my_package.my_adapter:MyMemory \
  --benchmark locomo \
  --run-id my-method-locomo-smoke \
  --allow-api \
  --conversations 1 \
  --rounds 20 \
  --questions-per-conversation 1 \
  --workers 1
```

## Parallel Safety

Custom methods default to `workers=1`. If you pass `workers>1`, you must also pass:

```bash
--allow-unsafe-custom-parallel
```

Only do this if your method isolates state by `run_id`, `benchmark`, and
`conversation_id`, and your storage backend supports multiple adapter instances.

## Resume And Retry

Framework resume skips completed conversations and answered questions.

If `add(conversation)` failed, the framework will not automatically retry that
conversation because your method may have partially written memory. To support
safe failed-ingest retry, implement a future clean-reset hook or manually clean
your method state before using a new run id.
```

- [ ] **Step 2: Link guide from README**

Add a short section to `README.md`:

```markdown
### Custom Method Onboarding

Ordinary users can evaluate a new memory method by implementing
`BaseMemoryProvider.add(conversation)` and `BaseMemoryProvider.retrieve(question)`,
then running with `--method-class module:ClassName`. See
[`docs/custom-method-onboarding.md`](docs/custom-method-onboarding.md).
```

- [ ] **Step 3: Update project state docs**

Update:

- `AGENTS.md`: mark custom method lightweight implementation completed only after tests pass.
- `docs/current-roadmap.md`: check off implemented items.
- `docs/task-ledger.md`: update P0 row with test evidence.

Do not mark clean retry hooks for built-in methods complete unless Task 4 only implements fail-closed preflight.

- [ ] **Step 4: Run documentation tests**

Run:

```bash
uv run pytest tests/test_documentation_standards.py -q
git diff --check -- README.md AGENTS.md docs/current-roadmap.md docs/task-ledger.md docs/custom-method-onboarding.md
```

Expected: `5 passed`, then no `git diff --check` output.

- [ ] **Step 5: Commit**

```bash
git add README.md AGENTS.md docs/current-roadmap.md docs/task-ledger.md docs/custom-method-onboarding.md
git commit -m "docs: document lightweight custom method onboarding"
```

---

### Task 7: Final Focused Regression

**Files:**
- No source changes unless a regression is found.

- [ ] **Step 1: Run focused custom-method regression**

```bash
uv run pytest \
  tests/test_custom_method_loader.py \
  tests/test_main_cli.py \
  tests/test_prediction_cli.py \
  tests/test_prediction_runner.py \
  tests/test_documentation_standards.py \
  -q
```

Expected: all pass.

- [ ] **Step 2: Run broader relevant suite**

```bash
uv run pytest \
  tests/test_method_registry.py \
  tests/test_config_profiles.py \
  tests/test_artifact_evaluation_runner.py \
  tests/test_mem0_adapter.py \
  tests/test_amem_adapter.py \
  tests/test_lightmem_adapter.py \
  tests/test_memoryos_adapter.py \
  -q
```

Expected: all pass. Existing unrelated warnings are acceptable only if they already existed and do not indicate a failed assertion.

- [ ] **Step 3: Compile source and tests**

```bash
uv run python -m compileall -q src/memory_benchmark tests
```

Expected: exit code 0.

- [ ] **Step 4: Check patch whitespace**

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 5: Update handoff**

Create `docs/handoffs/2026-06-24-method-onboarding-clean-retry.md` with:

```markdown
# 2026-06-24 Method Onboarding And Clean Retry Handoff

## Completed

- Custom `--method-class module:ClassName` loading.
- Custom method no-arg `BaseMemoryProvider` validation.
- Custom method default `workers=1`.
- `--allow-unsafe-custom-parallel` guard for custom method workers>1.
- Explicit failed-ingest fail-closed retry behavior.
- Custom method onboarding guide.

## Verification

- `<paste exact pytest commands and results>`

## Remaining

- Built-in method clean retry hooks / attempt namespace proof.
- Later cleanup of legacy `BaseMemorySystem` / `BaseResumableMemorySystem` /
  `BaseMemoryRetriever` after retrieve-first stability.
```

- [ ] **Step 6: Commit final handoff**

```bash
git add docs/handoffs/2026-06-24-method-onboarding-clean-retry.md
git commit -m "docs: hand off custom method onboarding implementation"
```

---

## Self-Review

### Spec Coverage

- User lightweight path: covered by Tasks 1, 2, 3, 5, 6.
- `--method-class module:ClassName`: covered by Tasks 1, 2, 3.
- No-arg constructor: covered by Task 1 tests and Task 6 docs.
- No forced TOML/source identity for user methods: covered by Task 3 custom service path and Task 6 docs.
- Custom method default `workers=1`: covered by Task 2 CLI validation and Task 3 custom service path.
- `--allow-unsafe-custom-parallel`: covered by Task 2 and Task 6 docs.
- Resume/retry status machine: covered by Task 4.
- Failed ingest fail-closed: covered by Task 4.
- Built-in method deep integration preserved: covered by Task 7 focused regression.

### Known Non-Goals

- This plan does not implement `--method-file`.
- This plan does not implement `MethodRuntimeContext`.
- This plan does not implement built-in method-specific reset hooks; it only prevents unsafe dirty retry by default.
- This plan does not remove legacy `BaseMemorySystem`, `BaseResumableMemorySystem`, or `BaseMemoryRetriever`.
