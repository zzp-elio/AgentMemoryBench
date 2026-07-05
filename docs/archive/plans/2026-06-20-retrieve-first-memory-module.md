# Retrieve-First Memory Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate conversation-QA prediction from method-owned `get_answer()` to framework-owned
`retrieve(question) -> AnswerPromptResult.prompt_messages -> answer reader`.

**2026-06-22 update:** early steps in this plan mention `RetrievalResult.formatted_context`
because that was the first draft. The accepted current protocol is
`AnswerPromptResult.prompt_messages`; `answer_prompt` is only a compatibility text view.
Use `docs/task-ledger.md` and
`docs/handoffs/2026-06-22-prompt-messages-implementation.md` as the current truth before
continuing work.

**Architecture:** Add a new `BaseMemoryProvider` protocol beside the legacy `BaseMemorySystem`, then migrate runner, artifacts, registry, and four built-in methods incrementally. During migration, the runner keeps a legacy fallback so existing outputs and tests remain debuggable until all adapters are converted.

**Tech Stack:** Python 3.12, dataclasses, pytest, OpenAI-compatible SDK, existing `uv` workflow, existing `EfficiencyCollector`, existing src-layout.

---

## File Structure

Core protocol:

- Modify `src/memory_benchmark/core/entities.py`
  - Make `RetrievalResult.formatted_context` the required answer-context field in behavior and docs.
- Modify `src/memory_benchmark/core/interfaces.py`
  - Add `BaseMemoryProvider.add(conversation)` and `BaseMemoryProvider.retrieve(question)`.
  - Keep `BaseMemorySystem` temporarily for legacy compatibility.
- Modify `src/memory_benchmark/core/__init__.py`
  - Export `BaseMemoryProvider`.
- Modify `src/memory_benchmark/core/capabilities.py`
  - Make `MEMORY_RETRIEVAL` the required prediction capability for retrieve-first path.

Reader:

- Create `src/memory_benchmark/readers/__init__.py`
- Create `src/memory_benchmark/readers/answer.py`
  - Prompt template validation.
  - Default answer prompt.
  - Fake-testable `AnswerLLMClient` protocol.
  - OpenAI-compatible client implementation.
  - `FrameworkAnswerReader.generate_answer`.

Prediction runner and artifacts:

- Modify `src/memory_benchmark/storage/experiment_paths.py`
  - Add `retrieval_results_path`.
  - Add `answer_prompts_path`.
- Modify `src/memory_benchmark/runners/prediction.py`
  - Add retrieve-first question flow.
  - Persist retrieval artifacts before answer generation.
  - Resume from retrieval completed / answer pending state.
  - Record framework-level retrieval latency, injected context tokens, answer latency, answer LLM tokens.
- Modify `src/memory_benchmark/cli/commands.py`
- Modify `src/memory_benchmark/cli/main.py`
- Modify `src/memory_benchmark/cli/run_prediction.py`
  - Wire answer prompt profile / answer prompt file.
  - Add manifest identity fields for reader protocol.

Registry:

- Modify `src/memory_benchmark/methods/registry.py`
  - Update built-in method capabilities from `ANSWER_GENERATION` to `MEMORY_RETRIEVAL`.
  - Keep compatibility checks explicit during migration.
- Modify `src/memory_benchmark/benchmark_adapters/registry.py`
  - Conversation-QA prediction should require `CONVERSATION_ADD` + `MEMORY_RETRIEVAL` once runner migration lands.

Methods:

- Modify `src/memory_benchmark/methods/mock.py`
- Modify `src/memory_benchmark/methods/mem0_adapter.py`
- Modify `src/memory_benchmark/methods/amem_adapter.py`
- Modify `src/memory_benchmark/methods/lightmem_adapter.py`
- Modify `src/memory_benchmark/methods/memoryos_adapter.py`
  - Add `retrieve(question)` returning `RetrievalResult`.
  - Keep `get_answer()` only as a temporary legacy wrapper until all tests are migrated.

Tests:

- Create `tests/test_retrieve_first_protocol.py`
- Create `tests/test_framework_answer_reader.py`
- Modify `tests/test_prediction_runner.py`
- Modify `tests/test_prediction_efficiency_observations.py`
- Modify method-specific tests:
  - `tests/test_mem0_adapter.py`
  - `tests/test_amem_adapter.py`
  - `tests/test_lightmem_adapter.py`
  - `tests/test_memoryos_adapter.py`
  - `tests/test_method_registry.py`
  - `tests/test_config_profiles.py`
  - `tests/test_main_cli.py`
  - `tests/test_prediction_cli.py`

Docs:

- Modify `README.md`
- Modify `AGENTS.md`
- Modify `docs/current-roadmap.md`
- Modify `docs/task-ledger.md`
- Modify `docs/method-interface-inventory.md`

---

## Task 1: Add Retrieve-First Core Protocol

**Files:**

- Modify: `src/memory_benchmark/core/interfaces.py`
- Modify: `src/memory_benchmark/core/entities.py`
- Modify: `src/memory_benchmark/core/__init__.py`
- Modify: `src/memory_benchmark/core/capabilities.py`
- Create: `tests/test_retrieve_first_protocol.py`

- [x] **Step 1: Write the failing protocol tests**

Add `tests/test_retrieve_first_protocol.py`:

```python
"""测试 retrieve-first 核心协议。

本文件只验证 core 层数据结构和抽象接口，不调用外部模型。
"""

from __future__ import annotations

from memory_benchmark.core import (
    AddResult,
    Conversation,
    MethodCapability,
    Question,
    RetrievalResult,
    Session,
    Turn,
)
from memory_benchmark.core.interfaces import BaseMemoryProvider


class TinyProvider(BaseMemoryProvider):
    """最小 retrieve-first provider，用于验证抽象接口可实例化。"""

    def __init__(self) -> None:
        self.added: list[str] = []

    def add(self, conversation: Conversation) -> AddResult:
        self.added.append(conversation.conversation_id)
        return AddResult(conversation_ids=[conversation.conversation_id])

    def retrieve(self, question: Question) -> RetrievalResult:
        return RetrievalResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            formatted_context="Alice likes tea.",
            metadata={"strategy": "tiny"},
        )


def test_base_memory_provider_adds_one_conversation_and_retrieves_context() -> None:
    """新主接口应只接收单个 conversation，并返回 formatted_context。"""

    provider = TinyProvider()
    conversation = Conversation(
        conversation_id="conv-1",
        sessions=[
            Session(
                session_id="s1",
                turns=[Turn(turn_id="t1", speaker="Alice", content="I like tea.")],
            )
        ],
    )
    question = Question(
        question_id="q1",
        conversation_id="conv-1",
        text="What does Alice like?",
    )

    add_result = provider.add(conversation)
    retrieval = provider.retrieve(question)

    assert add_result.conversation_ids == ["conv-1"]
    assert retrieval.question_id == "q1"
    assert retrieval.conversation_id == "conv-1"
    assert retrieval.formatted_context == "Alice likes tea."
    assert retrieval.metadata == {"strategy": "tiny"}


def test_memory_retrieval_capability_is_public_contract() -> None:
    """capability 层应包含 memory_retrieval，供 registry 做兼容性判断。"""

    assert MethodCapability.MEMORY_RETRIEVAL.value == "memory_retrieval"
```

- [x] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/test_retrieve_first_protocol.py -q
```

Expected before implementation:

```text
ImportError: cannot import name 'BaseMemoryProvider'
```

- [x] **Step 3: Implement `BaseMemoryProvider`**

Update `src/memory_benchmark/core/interfaces.py` module docstring and add the class before legacy `BaseMemorySystem`:

```python
class BaseMemoryProvider(ABC):
    """retrieve-first memory module 主接口。

    新 method 只需要实现 conversation 写入和 question 检索。最终答案由 framework
    reader 统一生成。
    """

    @abstractmethod
    def add(self, conversation: Conversation) -> AddResult:
        """写入单个公开 conversation。

        输入:
            conversation: 已清洗的公开 Conversation，不含 gold answer/evidence。

        输出:
            AddResult: 至少包含当前 conversation_id。
        """

        raise NotImplementedError

    @abstractmethod
    def retrieve(self, question: Question) -> RetrievalResult:
        """根据公开问题返回可直接注入 prompt 的记忆上下文。

        输入:
            question: method 可见公开问题。

        输出:
            RetrievalResult: `formatted_context` 是 framework reader 的核心输入。
        """

        raise NotImplementedError
```

Keep `BaseMemorySystem`, `BaseResumableMemorySystem`, and `BaseMemoryRetriever` unchanged in this task except docstrings that label them as legacy.

- [x] **Step 4: Export `BaseMemoryProvider`**

Update `src/memory_benchmark/core/__init__.py`:

```python
from .interfaces import (
    BaseMemoryProvider,
    BaseMemoryRetriever,
    BaseMemorySystem,
    BaseResumableMemorySystem,
)
```

Add `"BaseMemoryProvider"` to `__all__`.

- [x] **Step 5: Tighten `RetrievalResult` docstring**

Update `src/memory_benchmark/core/entities.py`:

```python
@dataclass
class RetrievalResult:
    """retrieve-first 输出。

    `formatted_context` 是 framework reader 的核心输入，必须是 method 内部已经
    完成检索、合并、去重和格式化后的最终上下文。
    """
```

Do not add dataclass `__post_init__` in this task. Empty context is a runner validation rule, not a core serialization rule.

- [x] **Step 6: Run protocol tests**

Run:

```bash
uv run pytest tests/test_retrieve_first_protocol.py -q
```

Expected:

```text
2 passed
```

- [x] **Step 7: Run focused compatibility tests**

Run:

```bash
uv run pytest tests/test_documentation_standards.py tests/test_method_registry.py -q
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit**

```bash
git add src/memory_benchmark/core/interfaces.py src/memory_benchmark/core/entities.py src/memory_benchmark/core/__init__.py tests/test_retrieve_first_protocol.py
git commit -m "feat: add retrieve-first memory provider protocol"
```

Current status: deferred because the repository has many pre-existing uncommitted
OpenCode/Codex changes. Do not commit this task alone until the broader dirty
state is reviewed.

---

## Task 2: Add Framework Answer Reader

**Files:**

- Create: `src/memory_benchmark/readers/__init__.py`
- Create: `src/memory_benchmark/readers/answer.py`
- Create: `tests/test_framework_answer_reader.py`

- [x] **Step 1: Write failing reader tests**

Add `tests/test_framework_answer_reader.py`:

```python
"""测试 framework-owned answer reader。

Reader 只负责把 question 和 retrieved context 变成 prompt，并调用可替换 LLM client。
"""

from __future__ import annotations

import pytest

from memory_benchmark.core import Question, RetrievalResult
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.readers.answer import (
    AnswerPromptTemplate,
    FakeAnswerLLMClient,
    FrameworkAnswerReader,
)


def _question() -> Question:
    return Question(
        question_id="q1",
        conversation_id="conv-1",
        text="What does Alice like?",
        question_time="2024-01-01",
        category="single_hop",
    )


def _retrieval() -> RetrievalResult:
    return RetrievalResult(
        question_id="q1",
        conversation_id="conv-1",
        formatted_context="Alice said she likes tea.",
    )


def test_default_reader_injects_question_and_memory_context() -> None:
    """默认 prompt 必须包含 question 和 formatted_context。"""

    client = FakeAnswerLLMClient(answer="Alice likes tea.")
    reader = FrameworkAnswerReader(client=client)

    result = reader.generate_answer(question=_question(), retrieval=_retrieval())

    assert result.answer == "Alice likes tea."
    assert result.question_id == "q1"
    assert result.conversation_id == "conv-1"
    assert "What does Alice like?" in client.calls[0]["prompt"]
    assert "Alice said she likes tea." in client.calls[0]["prompt"]


def test_custom_prompt_requires_question_and_memory_context_placeholders() -> None:
    """自定义 prompt 少任一核心占位符都应 fail closed。"""

    with pytest.raises(ConfigurationError, match="memory_context"):
        AnswerPromptTemplate(
            template="Question: {question}\nAnswer:",
            profile_name="broken",
        )

    with pytest.raises(ConfigurationError, match="question"):
        AnswerPromptTemplate(
            template="Memory: {memory_context}\nAnswer:",
            profile_name="broken",
        )


def test_reader_rejects_empty_formatted_context() -> None:
    """Phase 1 默认不允许空检索上下文静默回答。"""

    reader = FrameworkAnswerReader(client=FakeAnswerLLMClient(answer="anything"))
    retrieval = RetrievalResult(
        question_id="q1",
        conversation_id="conv-1",
        formatted_context=" ",
    )

    with pytest.raises(ConfigurationError, match="formatted_context"):
        reader.generate_answer(question=_question(), retrieval=retrieval)
```

- [x] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/test_framework_answer_reader.py -q
```

Expected before implementation:

```text
ModuleNotFoundError: No module named 'memory_benchmark.readers'
```

- [x] **Step 3: Implement `readers/answer.py`**

Create `src/memory_benchmark/readers/answer.py`:

```python
"""framework-owned answer reader。

本模块把 retrieve-first 的 `formatted_context` 和公开 Question 拼成 prompt，
并通过可替换 LLM client 生成最终 answer。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from memory_benchmark.core import AnswerResult, ConfigurationError, Question, RetrievalResult


DEFAULT_ANSWER_PROMPT = """You are a question-answering system.
Answer the question using only the retrieved memory context.
If the context is insufficient, answer "I don't know".

Question:
{question}

Question Time:
{question_time}

Retrieved Memory Context:
{memory_context}

Answer:"""


class AnswerLLMClient(Protocol):
    """framework reader 使用的最小 LLM client 协议。"""

    model_name: str

    def complete(self, *, prompt: str) -> str:
        """输入 prompt，返回纯文本 answer。"""


@dataclass(frozen=True)
class AnswerPromptTemplate:
    """answer prompt 模板。"""

    template: str = DEFAULT_ANSWER_PROMPT
    profile_name: str = "default"

    def __post_init__(self) -> None:
        """校验核心占位符，避免 prompt 未注入问题或记忆上下文。"""

        if "{question}" not in self.template:
            raise ConfigurationError("Answer prompt template must include {question}")
        if "{memory_context}" not in self.template:
            raise ConfigurationError(
                "Answer prompt template must include {memory_context}"
            )

    def render(self, *, question: Question, memory_context: str) -> str:
        """渲染公开 Question 和检索上下文。"""

        return self.template.format(
            question=question.text,
            memory_context=memory_context,
            question_time=question.question_time or "",
            conversation_id=question.conversation_id,
            category=question.category or "",
            options=question.options or {},
        )


@dataclass
class FrameworkAnswerReader:
    """统一 answer reader。"""

    client: AnswerLLMClient
    prompt_template: AnswerPromptTemplate = field(
        default_factory=AnswerPromptTemplate
    )

    def generate_answer(
        self,
        *,
        question: Question,
        retrieval: RetrievalResult,
    ) -> AnswerResult:
        """基于检索上下文生成最终 answer。"""

        if retrieval.question_id != question.question_id:
            raise ConfigurationError(
                f"Retrieval question_id mismatch: {retrieval.question_id} != {question.question_id}"
            )
        if retrieval.conversation_id != question.conversation_id:
            raise ConfigurationError(
                "Retrieval conversation_id mismatch: "
                f"{retrieval.conversation_id} != {question.conversation_id}"
            )
        memory_context = retrieval.formatted_context.strip()
        if not memory_context:
            raise ConfigurationError(
                f"Retrieval formatted_context is empty: {question.question_id}"
            )
        prompt = self.prompt_template.render(
            question=question,
            memory_context=memory_context,
        )
        answer = self.client.complete(prompt=prompt).strip()
        if not answer:
            raise ConfigurationError(
                f"Framework answer reader returned an empty answer: {question.question_id}"
            )
        return AnswerResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer=answer,
            metadata={
                "answer_reader": "framework",
                "answer_model": self.client.model_name,
                "answer_prompt_profile": self.prompt_template.profile_name,
            },
        )


class FakeAnswerLLMClient:
    """测试用 LLM client，记录 prompt 并返回固定文本。"""

    model_name = "fake-answer-llm"

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls: list[dict[str, str]] = []

    def complete(self, *, prompt: str) -> str:
        self.calls.append({"prompt": prompt})
        return self.answer
```

- [x] **Step 4: Export reader classes**

Create `src/memory_benchmark/readers/__init__.py`:

```python
"""framework reader 公开导出。"""

from .answer import (
    AnswerLLMClient,
    AnswerPromptTemplate,
    FakeAnswerLLMClient,
    FrameworkAnswerReader,
)

__all__ = [
    "AnswerLLMClient",
    "AnswerPromptTemplate",
    "FakeAnswerLLMClient",
    "FrameworkAnswerReader",
]
```

- [x] **Step 5: Run reader tests**

Run:

```bash
uv run pytest tests/test_framework_answer_reader.py -q
```

Expected by original plan:

```text
3 passed
```

Actual after Claude Code review coverage improvements:

```text
7 passed
```

- [ ] **Step 6: Commit**

```bash
git add src/memory_benchmark/readers tests/test_framework_answer_reader.py
git commit -m "feat: add framework answer reader"
```

Current status: deferred because the repository has many pre-existing uncommitted
OpenCode/Codex changes. Do not commit this task alone until the broader dirty
state is reviewed.

---

## Task 3: Add Retrieval Artifacts and Reader Paths

**Files:**

- Modify: `src/memory_benchmark/storage/experiment_paths.py`
- Modify: `tests/test_prediction_runner.py`

- [x] **Step 1: Write failing artifact path test**

Add this test to `tests/test_prediction_runner.py` near existing path/artifact tests:

```python
def test_experiment_paths_include_retrieval_and_answer_prompt_artifacts(tmp_path: Path) -> None:
    """retrieve-first runner 需要单独保存 retrieval context 和 answer prompt。"""

    from memory_benchmark.storage import ExperimentPaths

    paths = ExperimentPaths.create(tmp_path / "run")

    assert paths.retrieval_results_path.name == "retrieval_results.prediction.jsonl"
    assert paths.answer_prompts_path.name == "answer_prompts.prediction.jsonl"
    assert paths.retrieval_results_path.parent == paths.artifacts_dir
    assert paths.answer_prompts_path.parent == paths.artifacts_dir
```

- [x] **Step 2: Run test and verify failure**

Run:

```bash
uv run pytest tests/test_prediction_runner.py::test_experiment_paths_include_retrieval_and_answer_prompt_artifacts -q
```

Expected before implementation:

```text
AttributeError: 'ExperimentPaths' object has no attribute 'retrieval_results_path'
```

- [x] **Step 3: Add artifact paths**

Update `src/memory_benchmark/storage/experiment_paths.py`:

```python
    @property
    def retrieval_results_path(self) -> Path:
        """返回 retrieve-first 检索结果 JSONL 路径。"""

        return self.artifacts_dir / "retrieval_results.prediction.jsonl"

    @property
    def answer_prompts_path(self) -> Path:
        """返回 framework answer prompt JSONL 路径。"""

        return self.artifacts_dir / "answer_prompts.prediction.jsonl"
```

Place these properties near `method_predictions_path`.

- [x] **Step 4: Run focused test**

Run:

```bash
uv run pytest tests/test_prediction_runner.py::test_experiment_paths_include_retrieval_and_answer_prompt_artifacts -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Commit**

```bash
git add src/memory_benchmark/storage/experiment_paths.py tests/test_prediction_runner.py
git commit -m "feat: add retrieve-first artifact paths"
```

Current status: deferred because the repository has many pre-existing uncommitted
OpenCode/Codex changes. Do not commit this task alone until the broader dirty
state is reviewed.

---

## Task 4: Add Retrieve-First Runner Path with Fake Provider

**Files:**

- Modify: `src/memory_benchmark/runners/prediction.py`
- Modify: `tests/test_prediction_runner.py`

- [x] **Step 1: Add fake provider test classes**

Add to `tests/test_prediction_runner.py` after `RecordingPredictionSystem`:

```python
from memory_benchmark.core import RetrievalResult
from memory_benchmark.core.interfaces import BaseMemoryProvider
from memory_benchmark.readers.answer import FakeAnswerLLMClient, FrameworkAnswerReader


class RecordingMemoryProvider(BaseMemoryProvider):
    """记录 add/retrieve 调用的 retrieve-first fake provider。"""

    def __init__(self) -> None:
        self.added_conversation_ids: list[str] = []
        self.retrieved_question_ids: list[str] = []

    def add(self, conversation: Conversation) -> AddResult:
        self.added_conversation_ids.append(conversation.conversation_id)
        return AddResult(conversation_ids=[conversation.conversation_id])

    def retrieve(self, question: Question) -> RetrievalResult:
        self.retrieved_question_ids.append(question.question_id)
        return RetrievalResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            formatted_context=f"memory for {question.text}",
            metadata={"provider": "recording"},
        )
```

If imports already exist, merge them instead of duplicating.

- [x] **Step 2: Add failing runner test**

Add:

```python
def test_runner_uses_retrieve_first_provider_and_framework_reader(tmp_path: Path) -> None:
    """新 provider 路径应先 retrieve，再由 framework reader 生成 answer。"""

    dataset = _build_dataset()
    provider = RecordingMemoryProvider()
    answer_client = FakeAnswerLLMClient(answer="framework answer")
    reader = FrameworkAnswerReader(client=answer_client)

    summary = run_predictions(
        dataset=dataset,
        system=provider,
        run_context=RunContext(
            run_id="retrieve-first",
            output_root=tmp_path,
            source_identity={"test": "retrieve-first"},
        ),
        policy=PredictionRunPolicy(max_workers=1),
        answer_reader=reader,
    )

    run_dir = Path(summary.summary_path).parents[1]
    predictions = read_jsonl(run_dir / "artifacts" / "method_predictions.jsonl")
    retrievals = read_jsonl(run_dir / "artifacts" / "retrieval_results.prediction.jsonl")

    assert provider.added_conversation_ids == ["conv-1", "conv-2"]
    assert provider.retrieved_question_ids == ["conv-1:q1", "conv-2:q1"]
    assert [record["answer"] for record in predictions] == [
        "framework answer",
        "framework answer",
    ]
    assert retrievals[0]["formatted_context"] == "memory for 问题 1"
    assert "memory for 问题 1" in answer_client.calls[0]["prompt"]
```

- [x] **Step 3: Run test and verify failure**

Run:

```bash
uv run pytest tests/test_prediction_runner.py::test_runner_uses_retrieve_first_provider_and_framework_reader -q
```

Expected before implementation:

```text
TypeError: run_predictions() got an unexpected keyword argument 'answer_reader'
```

- [x] **Step 4: Update `run_predictions` signature**

In `src/memory_benchmark/runners/prediction.py`, import:

```python
from memory_benchmark.core.interfaces import (
    BaseMemoryProvider,
    BaseMemorySystem,
    BaseResumableMemorySystem,
)
from memory_benchmark.readers.answer import FrameworkAnswerReader
```

Change `run_predictions` signature from `system: BaseMemorySystem` to a union:

```python
def run_predictions(
    dataset: Dataset,
    system: BaseMemorySystem | BaseMemoryProvider,
    run_context: RunContext,
    policy: PredictionRunPolicy | None = None,
    answer_reader: FrameworkAnswerReader | None = None,
) -> PredictionRunSummary:
```

Keep every existing parameter after `policy` in its current order. Add `answer_reader` immediately after `policy` if that is the least invasive call-site change.

- [x] **Step 5: Implement retrieve-first answer helper**

Add a helper near `_answer_conversation_questions`:

```python
def _answer_question_retrieve_first(
    *,
    provider: BaseMemoryProvider,
    question: Question,
    answer_reader: FrameworkAnswerReader,
    efficiency_collector: EfficiencyCollector | None,
) -> tuple[AnswerResult, dict[str, Any], tuple[EfficiencyObservation, ...]]:
    """执行 retrieve -> framework reader，并返回 prediction 和 retrieval record。"""

    started_ns = perf_counter_ns()
    if efficiency_collector is not None and efficiency_collector.enabled:
        with efficiency_collector.operation_stage(EfficiencyStage.RETRIEVAL):
            retrieval = provider.retrieve(question)
    else:
        retrieval = provider.retrieve(question)
    _validate_retrieval(retrieval, question)

    injected_tokens = _count_context_tokens(
        retrieval.formatted_context,
        model_name="gpt-4o-mini",
    )
    if efficiency_collector is not None and efficiency_collector.enabled:
        efficiency_collector.record_retrieval_result(
            latency_ms=_elapsed_ms(started_ns),
            injected_memory_context_tokens=injected_tokens,
        )

    answer_started_ns = perf_counter_ns()
    prediction = answer_reader.generate_answer(question=question, retrieval=retrieval)
    if efficiency_collector is not None and efficiency_collector.enabled:
        efficiency_collector.record_answer_generation(
            latency_ms=_elapsed_ms(answer_started_ns)
        )

    retrieval_record = {
        "question_id": retrieval.question_id,
        "conversation_id": retrieval.conversation_id,
        "formatted_context": retrieval.formatted_context,
        "memories": [memory.to_dict() for memory in retrieval.memories],
        "metadata": retrieval.metadata,
    }
    return prediction, retrieval_record, ()
```

Use the existing token counting utility instead of hard-coding `_count_context_tokens` if the repository already has an equivalent helper. The final implementation must record the same value as `injected_memory_context_tokens`.

- [x] **Step 6: Add retrieval validation helper**

Add:

```python
def _validate_retrieval(retrieval: RetrievalResult, question: Question) -> None:
    """校验 retrieve 输出与公开问题严格对齐。"""

    if retrieval.question_id != question.question_id:
        raise ConfigurationError(
            f"Retrieval question_id mismatch: {retrieval.question_id} != {question.question_id}"
        )
    if retrieval.conversation_id != question.conversation_id:
        raise ConfigurationError(
            "Retrieval conversation_id mismatch: "
            f"{retrieval.conversation_id} != {question.conversation_id}"
        )
    if not retrieval.formatted_context.strip():
        raise ConfigurationError(
            f"Retrieval formatted_context is empty: {question.question_id}"
        )
    validate_no_private_keys(retrieval.metadata)
    for memory in retrieval.memories:
        validate_no_private_keys(memory.metadata)
```

- [x] **Step 7: Thread retrieve-first through `_answer_conversation_questions`**

Update `_answer_conversation_questions` to branch:

```python
if isinstance(system, BaseMemoryProvider):
    if answer_reader is None:
        raise ConfigurationError("Retrieve-first prediction requires answer_reader")
    prediction, retrieval_record, extra_observations = _answer_question_retrieve_first(
        provider=system,
        question=question,
        answer_reader=answer_reader,
        efficiency_collector=efficiency_collector,
    )
else:
    prediction = system.get_answer(question)
    retrieval_record = None
    extra_observations = ()
```

Extend `_ConversationAnswerBatch` with `retrievals: tuple[dict[str, Any], ...] = ()`.

- [x] **Step 8: Persist retrieval artifacts**

In `_answer_pending_questions`, maintain a `retrieval_records` mapping loaded from `paths.retrieval_results_path` if it exists. After each batch:

```python
for retrieval_record in batch.retrievals:
    retrieval_records[retrieval_record["question_id"]] = retrieval_record
atomic_write_jsonl(
    paths.retrieval_results_path,
    [
        retrieval_records[question_id]
        for question_id in question_order
        if question_id in retrieval_records
    ],
)
```

- [x] **Step 9: Run retrieve-first runner test**

Run:

```bash
uv run pytest tests/test_prediction_runner.py::test_runner_uses_retrieve_first_provider_and_framework_reader -q
```

Expected:

```text
1 passed
```

- [x] **Step 10: Run focused runner tests**

Run:

```bash
uv run pytest tests/test_prediction_runner.py tests/test_prediction_efficiency_observations.py -q
```

Expected:

```text
passed
```

- [ ] **Step 11: Commit**

```bash
git add src/memory_benchmark/runners/prediction.py tests/test_prediction_runner.py
git commit -m "feat: support retrieve-first prediction flow"
```

Current status: deferred because the repository has many pre-existing uncommitted
OpenCode/Codex changes. Do not commit this task alone until the broader dirty
state is reviewed.

---

## Task 5: Add Retrieve/Answer Resume Semantics

**Files:**

- Modify: `src/memory_benchmark/runners/prediction.py`
- Modify: `tests/test_prediction_runner.py`

- [x] **Step 1: Add failing resume test**

Add:

```python
class FailingAnswerClient(FakeAnswerLLMClient):
    """第一次调用失败，第二次调用成功。"""

    def __init__(self) -> None:
        super().__init__(answer="second answer")
        self.fail_once = True

    def complete(self, *, prompt: str) -> str:
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("answer failed once")
        return super().complete(prompt=prompt)


def test_resume_reuses_completed_retrieval_when_answer_failed(tmp_path: Path) -> None:
    """retrieve 已落盘但 answer 失败时，resume 不应重新调用 provider.retrieve。"""

    dataset = _build_dataset()
    provider = RecordingMemoryProvider()
    failing_reader = FrameworkAnswerReader(client=FailingAnswerClient())
    run_context = RunContext(
        run_id="retrieve-answer-resume",
        output_root=tmp_path,
        source_identity={"test": "retrieve-answer-resume"},
    )

    with pytest.raises(RuntimeError, match="answer failed once"):
        run_predictions(
            dataset=dataset,
            system=provider,
            run_context=run_context,
            policy=PredictionRunPolicy(max_workers=1),
            answer_reader=failing_reader,
        )

    assert provider.retrieved_question_ids == ["conv-1:q1"]

    provider_after_resume = RecordingMemoryProvider()
    success_reader = FrameworkAnswerReader(
        client=FakeAnswerLLMClient(answer="resumed answer")
    )
    run_predictions(
        dataset=dataset,
        system=provider_after_resume,
        run_context=run_context,
        policy=PredictionRunPolicy(max_workers=1, resume=True),
        answer_reader=success_reader,
    )

    assert provider_after_resume.retrieved_question_ids == ["conv-2:q1"]
```

This test expects the first question retrieval to be reused, while the second question still retrieves normally.

- [x] **Step 2: Run test and verify failure**

Run:

```bash
uv run pytest tests/test_prediction_runner.py::test_resume_reuses_completed_retrieval_when_answer_failed -q
```

Expected before implementation:

```text
AssertionError: provider_after_resume.retrieved_question_ids == ['conv-1:q1', 'conv-2:q1']
```

- [x] **Step 3: Load existing retrieval records**

In `run_predictions`, load:

```python
retrieval_records = {
    record["question_id"]: record
    for record in read_jsonl(paths.retrieval_results_path)
}
```

If the file does not exist, use `{}`. Follow the repository’s existing `read_jsonl` empty-file behavior.

- [x] **Step 4: Reuse retrieval before calling provider**

In `_answer_conversation_questions`, accept `existing_retrieval_records: dict[str, dict[str, Any]]`.

For retrieve-first branch:

```python
existing_retrieval = existing_retrieval_records.get(question.question_id)
if existing_retrieval is not None:
    retrieval = _retrieval_from_record(existing_retrieval)
    prediction = answer_reader.generate_answer(question=question, retrieval=retrieval)
    retrieval_record = None
else:
    prediction, retrieval_record, extra_observations = _answer_question_retrieve_first(
        provider=provider,
        question=question,
        answer_reader=answer_reader,
        efficiency_collector=efficiency_collector,
    )
```

Add `_retrieval_from_record(record)`:

```python
def _retrieval_from_record(record: dict[str, Any]) -> RetrievalResult:
    """从 retrieval artifact 还原 RetrievalResult。"""

    return RetrievalResult(
        question_id=str(record["question_id"]),
        conversation_id=str(record["conversation_id"]),
        formatted_context=str(record["formatted_context"]),
        memories=[],
        metadata=dict(record.get("metadata") or {}),
    )
```

Do not reconstruct `memories` in this task; `formatted_context` is the canonical resume input.

- [x] **Step 5: Run resume test**

Run:

```bash
uv run pytest tests/test_prediction_runner.py::test_resume_reuses_completed_retrieval_when_answer_failed -q
```

Expected:

```text
1 passed
```

- [ ] **Step 6: Commit**

```bash
git add src/memory_benchmark/runners/prediction.py tests/test_prediction_runner.py
git commit -m "feat: resume retrieve-first answer generation"
```

Current status: deferred because the repository has many pre-existing uncommitted
OpenCode/Codex changes. Do not commit this task alone until the broader dirty
state is reviewed. A Claude Code read-only review was attempted but produced no
output after multiple polls and was interrupted; rely on the focused local
verification recorded in the Task 5 handoff.

---

## Task 6: Wire OpenAI-Compatible Framework Reader

**Files:**

- Modify: `src/memory_benchmark/readers/answer.py`
- Modify: `src/memory_benchmark/cli/run_prediction.py`
- Modify: `src/memory_benchmark/cli/commands.py`
- Modify: `src/memory_benchmark/cli/main.py`
- Modify: `tests/test_framework_answer_reader.py`
- Modify: `tests/test_main_cli.py`
- Modify: `tests/test_prediction_cli.py`

- [x] **Step 1: Add OpenAI reader client test using monkeypatch**

In `tests/test_framework_answer_reader.py`, add:

```python
def test_openai_compatible_answer_client_uses_configured_model(monkeypatch) -> None:
    """OpenAI-compatible reader client 应从 settings 读取 model/base_url，但测试不触网。"""

    from memory_benchmark.config import OpenAISettings
    from memory_benchmark.readers.answer import OpenAICompatibleAnswerLLMClient

    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return type(
                "Response",
                (),
                {
                    "choices": [
                        type(
                            "Choice",
                            (),
                            {"message": type("Message", (), {"content": "answer"})()},
                        )()
                    ],
                    "usage": None,
                },
            )()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.chat = type(
                "Chat",
                (),
                {"completions": FakeCompletions()},
            )()

    monkeypatch.setattr("memory_benchmark.readers.answer.OpenAI", FakeOpenAI)

    client = OpenAICompatibleAnswerLLMClient(
        settings=OpenAISettings(
            api_key="sk-test",
            base_url="https://example.test/v1",
            model="gpt-4o-mini",
            timeout_seconds=60,
            max_retries=8,
        )
    )

    assert client.complete(prompt="hello") == "answer"
    assert captured["client_kwargs"]["base_url"] == "https://example.test/v1"
    assert captured["model"] == "gpt-4o-mini"
```

- [x] **Step 2: Run test and verify failure**

Run:

```bash
uv run pytest tests/test_framework_answer_reader.py::test_openai_compatible_answer_client_uses_configured_model -q
```

Expected:

```text
ImportError: cannot import name 'OpenAICompatibleAnswerLLMClient'
```

- [x] **Step 3: Implement OpenAI-compatible client**

In `src/memory_benchmark/readers/answer.py`, add:

```python
from openai import OpenAI
from memory_benchmark.config import OpenAISettings


class OpenAICompatibleAnswerLLMClient:
    """OpenAI-compatible answer LLM client。"""

    def __init__(self, *, settings: OpenAISettings) -> None:
        self.settings = settings
        self.model_name = settings.model
        self._client = OpenAI(**settings.to_client_kwargs())

    def complete(self, *, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self.settings.model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content
        return "" if content is None else str(content)
```

Export this class from `src/memory_benchmark/readers/__init__.py`.

- [x] **Step 4: Add CLI prompt file parsing tests**

In `tests/test_main_cli.py`, add a test that verifies `--answer-prompt-file` maps into `PredictCommand`.

Expected command fragment:

```bash
uv run memory-benchmark predict --method mem0 --benchmark locomo --profile smoke --answer-prompt-file prompt.txt
```

Test should assert:

```python
assert captured_command.answer_prompt_file == Path("prompt.txt")
```

- [x] **Step 5: Add command fields**

In `src/memory_benchmark/cli/commands.py`, add to `PredictCommand`:

```python
answer_prompt_file: str | Path | None = None
answer_prompt_profile: str = "default"
```

In `src/memory_benchmark/cli/main.py`, add:

```python
predict_parser.add_argument(
    "--answer-prompt-file",
    default=None,
    help="Path to a custom answer prompt template containing {question} and {memory_context}.",
)
predict_parser.add_argument(
    "--answer-prompt-profile",
    default="default",
    help="Answer prompt profile name written to manifest and artifacts.",
)
```

Wire the parsed values into `PredictCommand`.

- [x] **Step 6: Build reader in `run_registered_conversation_qa_prediction`**

In `src/memory_benchmark/cli/run_prediction.py`, after OpenAI settings are loaded for prediction, build:

```python
answer_template = load_answer_prompt_template(
    project_root=root,
    prompt_file=answer_prompt_file,
    profile_name=answer_prompt_profile,
)
answer_reader = FrameworkAnswerReader(
    client=OpenAICompatibleAnswerLLMClient(settings=openai_settings),
    prompt_template=answer_template,
)
```

Create `load_answer_prompt_template` in `src/memory_benchmark/readers/answer.py`:

```python
def load_answer_prompt_template(
    *,
    project_root: Path,
    prompt_file: str | Path | None,
    profile_name: str,
) -> AnswerPromptTemplate:
    """读取默认或用户自定义 answer prompt。"""

    if prompt_file is None:
        return AnswerPromptTemplate(profile_name=profile_name)
    path = Path(prompt_file).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return AnswerPromptTemplate(
        template=path.read_text(encoding="utf-8"),
        profile_name=profile_name,
    )
```

- [x] **Step 7: Run focused tests**

Run:

```bash
uv run pytest tests/test_framework_answer_reader.py tests/test_main_cli.py tests/test_prediction_cli.py -q
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit**

```bash
git add src/memory_benchmark/readers src/memory_benchmark/cli tests/test_framework_answer_reader.py tests/test_main_cli.py tests/test_prediction_cli.py
git commit -m "feat: wire framework answer reader into prediction CLI"
```

Current status: deferred because the repository has many pre-existing
OpenCode/Codex changes. Task 6 implementation is complete and verified; do not
commit this task alone until the broader dirty state is reviewed.

---

## Task 7: Update Registry Capabilities for Retrieve-First

**Files:**

- Modify: `src/memory_benchmark/methods/registry.py`
- Modify: `src/memory_benchmark/benchmark_adapters/registry.py`
- Modify: `tests/test_method_registry.py`
- Modify: `tests/test_benchmark_registry.py`
- Modify: `tests/test_prediction_cli.py`

- [x] **Step 1: Add failing registry test**

In `tests/test_method_registry.py`, add:

```python
def test_built_in_methods_advertise_memory_retrieval_capability() -> None:
    """retrieve-first prediction requires conversation_add + memory_retrieval."""

    from memory_benchmark.core import MethodCapability
    from memory_benchmark.methods.registry import get_method_registration

    for method_name in ("mem0", "memoryos", "amem", "lightmem"):
        registration = get_method_registration(method_name)
        assert MethodCapability.CONVERSATION_ADD in registration.provided_capabilities
        assert MethodCapability.MEMORY_RETRIEVAL in registration.provided_capabilities
        assert MethodCapability.ANSWER_GENERATION not in registration.provided_capabilities
```

- [x] **Step 2: Run test and verify failure**

Run:

```bash
uv run pytest tests/test_method_registry.py::test_built_in_methods_advertise_memory_retrieval_capability -q
```

Expected:

```text
AssertionError
```

- [x] **Step 3: Update method registrations**

In `src/memory_benchmark/methods/registry.py`, replace each built-in method capability set:

```python
provided_capabilities=frozenset(
    {
        MethodCapability.CONVERSATION_ADD,
        MethodCapability.MEMORY_RETRIEVAL,
    }
),
```

Do this for `amem`, `mem0`, `lightmem`, and `memoryos`.

- [x] **Step 4: Update benchmark requirements**

In `src/memory_benchmark/benchmark_adapters/registry.py`, ensure conversation-QA prediction registrations require:

```python
required_capabilities=frozenset(
    {
        MethodCapability.CONVERSATION_ADD,
        MethodCapability.MEMORY_RETRIEVAL,
    }
)
```

If tests still depend on `ANSWER_GENERATION`, update them to the new capability.

- [x] **Step 5: Run registry tests**

Run:

```bash
uv run pytest tests/test_method_registry.py tests/test_benchmark_registry.py tests/test_prediction_cli.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

```bash
git add src/memory_benchmark/methods/registry.py src/memory_benchmark/benchmark_adapters/registry.py tests/test_method_registry.py tests/test_benchmark_registry.py tests/test_prediction_cli.py
git commit -m "feat: require memory retrieval capability for prediction"
```

Current status: deferred because the repository has many pre-existing
OpenCode/Codex changes. Task 7 implementation is complete and verified; do not
commit this task alone until the broader dirty state is reviewed.

---

## Task 8: Migrate Mock and Fake Methods

**Files:**

- Modify: `src/memory_benchmark/methods/mock.py`
- Modify: `tests/test_prediction_runner.py`
- Modify: `tests/test_prediction_efficiency_observations.py`

- [x] **Step 1: Update mock method tests**

Replace mock `get_answer` expectations in runner tests with retrieve-first reader expectations. For the shared mock in `src/memory_benchmark/methods/mock.py`, add this behavior:

```python
def retrieve(self, question: Question) -> RetrievalResult:
    return RetrievalResult(
        question_id=question.question_id,
        conversation_id=question.conversation_id,
        formatted_context=self.context_by_question_id.get(
            question.question_id,
            f"mock-context-for:{question.question_id}",
        ),
        metadata={"method": "mock"},
    )
```

Test should assert that the final answer comes from `FrameworkAnswerReader`, not from the mock method.

- [x] **Step 2: Run targeted mock tests**

Run:

```bash
uv run pytest tests/test_prediction_runner.py tests/test_prediction_efficiency_observations.py -q
```

Expected before implementation:

```text
failed because MockMemorySystem does not implement BaseMemoryProvider
```

- [x] **Step 3: Implement `MockMemoryProvider`**

In `src/memory_benchmark/methods/mock.py`, either rename `MockMemorySystem` to `MockMemoryProvider` with a compatibility alias, or add a new class and keep the old one for legacy tests.

Required implementation:

```python
class MockMemoryProvider(BaseMemoryProvider):
    """按 question_id 返回固定 retrieval context 的 mock provider。"""

    def __init__(
        self,
        context_by_question_id: Mapping[str, str] | None = None,
        default_context: str | None = None,
    ) -> None:
        self.context_by_question_id = dict(context_by_question_id or {})
        self.default_context = default_context
        self.added_conversation_ids: list[str] = []

    def add(self, conversation: Conversation) -> AddResult:
        self.added_conversation_ids.append(conversation.conversation_id)
        return AddResult(
            conversation_ids=[conversation.conversation_id],
            metadata={"method": "mock"},
        )

    def retrieve(self, question: Question) -> RetrievalResult:
        context = self.context_by_question_id.get(question.question_id)
        if context is None:
            context = self.default_context or f"mock-context-for:{question.question_id}"
        return RetrievalResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            formatted_context=context,
            metadata={"method": "mock"},
        )
```

Keep:

```python
MockMemorySystem = MockMemoryProvider
```

only if existing imports require it.

- [x] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/test_prediction_runner.py tests/test_prediction_efficiency_observations.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit**

```bash
git add src/memory_benchmark/methods/mock.py tests/test_prediction_runner.py tests/test_prediction_efficiency_observations.py
git commit -m "test: migrate fake methods to retrieve-first"
```

Current status: deferred because the repository has many pre-existing
OpenCode/Codex changes. Task 8 implementation is complete and verified; do not
commit this task alone until the broader dirty state is reviewed.

---

## Task 9: Migrate Mem0 Adapter

**Files:**

- Modify: `src/memory_benchmark/methods/mem0_adapter.py`
- Modify: `tests/test_mem0_adapter.py`
- Modify: `tests/test_mem0_source_compatibility.py`

- [x] **Step 1: Add failing Mem0 retrieve test**

In `tests/test_mem0_adapter.py`, add a fake-backend test that calls `adapter.retrieve(question)` and asserts:

```python
retrieval.question_id == question.question_id
retrieval.conversation_id == question.conversation_id
retrieval.formatted_context
retrieval.metadata["method"] == "mem0"
retrieval.metadata["top_k"] == config.top_k
```

Use existing fake Mem0 backend helpers already in the file. The expected formatted context should match current `_memory_context_text(memories)` behavior.

- [x] **Step 2: Run Mem0 test and verify failure**

Run:

```bash
uv run pytest tests/test_mem0_adapter.py::test_mem0_retrieve_returns_formatted_context -q
```

Expected:

```text
AttributeError: 'Mem0' object has no attribute 'retrieve'
```

- [x] **Step 3: Extract current retrieval logic**

In `src/memory_benchmark/methods/mem0_adapter.py`, move the retrieval part of `get_answer()` into:

```python
def retrieve(self, question: Question) -> RetrievalResult:
    """检索当前 question 所属 conversation 的 Mem0 memory context。"""
```

The method must:

- Check conversation was added.
- Check question text is non-empty.
- Call `self._memory.search` with existing filters and `top_k`.
- Normalize results.
- Build `injected_memory_text = self._memory_context_text(memories)`.
- Record retrieval latency and injected context tokens when collector is active.
- Return:

```python
RetrievalResult(
    question_id=question.question_id,
    conversation_id=question.conversation_id,
    formatted_context=injected_memory_text,
    memories=[
        RetrievedMemory(
            content=memory_text,
            score=score,
            metadata=metadata,
        )
        for memory_text, score, metadata in normalized_memories
    ],
    metadata={
        "method": "mem0",
        "retrieved_memory_count": len(memories),
        "top_k": self.config.top_k,
        "retrieval_profile": self._reader_prompt_kind(question),
    },
)
```

If normalized memories are dicts, use the existing fields already used by `_memory_context_text`. Do not invent private metadata.

- [x] **Step 4: Keep legacy `get_answer()` as wrapper**

Keep `get_answer()` temporarily:

```python
def get_answer(self, question: Question) -> AnswerResult:
    retrieval = self.retrieve(question)
    reader_messages = self._reader_messages_from_context(question, retrieval.formatted_context)
    return self._generate_legacy_answer_from_messages(question, reader_messages)
```

This wrapper is only for legacy tests during migration. The new runner path should not use it.

- [x] **Step 5: Run Mem0 focused tests**

Run:

```bash
uv run pytest tests/test_mem0_adapter.py tests/test_mem0_source_compatibility.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

```bash
git add src/memory_benchmark/methods/mem0_adapter.py tests/test_mem0_adapter.py tests/test_mem0_source_compatibility.py
git commit -m "feat: migrate Mem0 adapter to retrieve-first"
```

---

## Task 10: Migrate A-Mem Adapter

**Files:**

- Modify: `src/memory_benchmark/methods/amem_adapter.py`
- Modify: `tests/test_amem_adapter.py`

- [x] **Step 1: Add failing A-Mem retrieve test**

In `tests/test_amem_adapter.py`, add:

```python
def test_amem_retrieve_returns_query_keywords_and_context(fake_amem_system) -> None:
    """A-Mem retrieve 应保留官方 query keyword generation 和 category k。"""

    question = Question(
        question_id="q1",
        conversation_id="conv-1",
        text="Where did Alice go?",
        category="1",
    )

    retrieval = fake_amem_system.retrieve(question)

    assert retrieval.question_id == "q1"
    assert retrieval.conversation_id == "conv-1"
    assert retrieval.formatted_context
    assert retrieval.metadata["method"] == "amem"
    assert "query_keywords" in retrieval.metadata
    assert "retrieve_k" in retrieval.metadata
```

Adapt fixture names to existing fixtures in the file. The assertions above are the required behavior.

- [x] **Step 2: Run test and verify failure**

Run:

```bash
uv run pytest tests/test_amem_adapter.py::test_amem_retrieve_returns_query_keywords_and_context -q
```

Expected:

```text
AttributeError: 'AMem' object has no attribute 'retrieve'
```

- [x] **Step 3: Extract current retrieval logic**

In `src/memory_benchmark/methods/amem_adapter.py`, create:

```python
def retrieve(self, question: Question) -> RetrievalResult:
    """执行 A-Mem 官方 query keyword generation 和 memory retrieval。"""
```

Move from `get_answer()`:

- added conversation check.
- adversarial public-input rejection.
- `_retrieve_k_for_question(question)`.
- `_generate_query_keywords`.
- `runtime.find_related_memories_raw(query_keywords, k=retrieve_k)`.
- retrieval latency/injected context tokens observation.

Return:

```python
RetrievalResult(
    question_id=question.question_id,
    conversation_id=question.conversation_id,
    formatted_context=str(context),
    metadata={
        "method": "amem",
        "retrieve_k": retrieve_k,
        "query_keywords": query_keywords,
        "query_keyword_prompt_version": AMEM_QUERY_KEYWORD_PROMPT_VERSION,
    },
)
```

- [x] **Step 4: Keep legacy `get_answer()` as wrapper**

Temporarily make `get_answer()` call `retrieve()` and then current `_build_answer_prompt`.

Do not change A-Mem answer prompt in this task. The framework reader migration will stop using legacy `get_answer()`.

- [x] **Step 5: Run A-Mem focused tests**

Run:

```bash
uv run pytest tests/test_amem_adapter.py tests/test_amem_registered_prediction.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

```bash
git add src/memory_benchmark/methods/amem_adapter.py tests/test_amem_adapter.py
git commit -m "feat: migrate A-Mem adapter to retrieve-first"
```

---

## Task 11: Migrate LightMem Adapter

**Files:**

- Modify: `src/memory_benchmark/methods/lightmem_adapter.py`
- Modify: `tests/test_lightmem_adapter.py`

- [x] **Step 1: Add failing LightMem retrieve tests**

Add two tests:

```python
def test_lightmem_retrieve_locomo_uses_specialized_context(fake_lightmem_locomo) -> None:
    """LoCoMo retrieve 应走 search_locomo 风格专门路径。"""

    question = Question(
        question_id="q1",
        conversation_id="conv-1",
        text="What does Alice like?",
        category="1",
    )

    retrieval = fake_lightmem_locomo.retrieve(question)

    assert retrieval.formatted_context
    assert retrieval.metadata["method"] == "lightmem"
    assert retrieval.metadata["retrieval_profile"] == "locomo_qdrant_combined"


def test_lightmem_retrieve_longmemeval_uses_backend_retrieve(fake_lightmem_longmemeval) -> None:
    """LongMemEval retrieve 应保留 LightMemory.retrieve online 路径。"""

    question = Question(
        question_id="q1",
        conversation_id="lme-1",
        text="What happened?",
        question_time="2024-01-01",
        metadata={"benchmark": "longmemeval"},
    )

    retrieval = fake_lightmem_longmemeval.retrieve(question)

    assert retrieval.formatted_context
    assert retrieval.metadata["method"] == "lightmem"
    assert retrieval.metadata["retrieval_profile"] == "lightmemory_retrieve"
```

Use existing fake backend fixtures; if fixture names differ, add local fake fixtures with the same behavior.

- [x] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/test_lightmem_adapter.py::test_lightmem_retrieve_locomo_uses_specialized_context tests/test_lightmem_adapter.py::test_lightmem_retrieve_longmemeval_uses_backend_retrieve -q
```

Expected:

```text
AttributeError: 'LightMem' object has no attribute 'retrieve'
```

- [x] **Step 3: Extract current retrieval logic**

In `src/memory_benchmark/methods/lightmem_adapter.py`, create:

```python
def retrieve(self, question: Question) -> RetrievalResult:
    """检索 LightMem context，不生成最终 answer。"""
```

Move from current `get_answer()`:

- backend existence check.
- LongMemEval branch using `backend.retrieve`.
- LoCoMo branch using `_retrieve_locomo_memories`.
- retrieval latency and injected token observation.

Return metadata:

```python
metadata={
    "method": "lightmem",
    "retrieve_limit": self.config.retrieve_limit,
    "retrieval_profile": (
        "lightmemory_retrieve"
        if _is_longmemeval_question(question, self._conversation_metadata)
        else "locomo_qdrant_combined"
    ),
}
```

- [x] **Step 4: Keep legacy `get_answer()` as wrapper**

Temporarily call `retrieve()` and then use current `_build_answer_prompt` logic by converting `formatted_context` back into the expected prompt input if needed.

The new runner should only call `retrieve()`.

- [x] **Step 5: Run LightMem focused tests**

Run:

```bash
uv run pytest tests/test_lightmem_adapter.py tests/test_lightmem_registered_prediction.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

```bash
git add src/memory_benchmark/methods/lightmem_adapter.py tests/test_lightmem_adapter.py
git commit -m "feat: migrate LightMem adapter to retrieve-first"
```

---

## Task 12: Migrate MemoryOS Adapter

**Files:**

- Modify: `src/memory_benchmark/methods/memoryos_adapter.py`
- Modify: `tests/test_memoryos_adapter.py`

- [x] **Step 1: Add failing MemoryOS retrieve test**

In `tests/test_memoryos_adapter.py`, add a fake state/retrieval test:

```python
def test_memoryos_retrieve_formats_retrieval_queue_and_knowledge(fake_memoryos_system) -> None:
    """MemoryOS retrieve 应返回最终 answer prompt 所需的 formatted_context。"""

    question = Question(
        question_id="q1",
        conversation_id="conv-1",
        text="What does Alice remember?",
    )

    retrieval = fake_memoryos_system.retrieve(question)

    assert retrieval.question_id == "q1"
    assert retrieval.conversation_id == "conv-1"
    assert retrieval.formatted_context
    assert retrieval.metadata["method"] == "MemoryOS"
    assert "retrieved_page_count" in retrieval.metadata
    assert "retrieved_knowledge_count" in retrieval.metadata
```

Use or extend existing MemoryOS fake modules to return:

```python
{
    "retrieval_queue": [{"user_input": "Alice likes tea", "agent_response": ""}],
    "long_term_knowledge": ["Alice likes tea."],
}
```

- [x] **Step 2: Run test and verify failure**

Run:

```bash
uv run pytest tests/test_memoryos_adapter.py::test_memoryos_retrieve_formats_retrieval_queue_and_knowledge -q
```

Expected:

```text
AttributeError: 'MemoryOS' object has no attribute 'retrieve'
```

- [x] **Step 3: Extract current MemoryOS retrieval**

In `src/memory_benchmark/methods/memoryos_adapter.py`, create:

```python
def retrieve(self, question: Question) -> RetrievalResult:
    """执行 MemoryOS 官方 retrieval 并格式化上下文。"""
```

Move from `get_answer()`:

- state lookup.
- `_effective_question_text(question)`.
- `state.retrieval_system.retrieve`.
- retrieval latency observation.

Create helper:

```python
def _memoryos_formatted_context(retrieval_result: dict[str, Any]) -> str:
    """把 MemoryOS retrieval queue 和 long-term knowledge 转为 reader context。"""

    parts: list[str] = []
    retrieval_queue = retrieval_result.get("retrieval_queue") or []
    if retrieval_queue:
        parts.append("Retrieved dialogue pages:")
        for index, page in enumerate(retrieval_queue, start=1):
            parts.append(f"[Page {index}] {page}")
    knowledge = retrieval_result.get("long_term_knowledge") or []
    if knowledge:
        parts.append("Long-term knowledge:")
        for index, item in enumerate(knowledge, start=1):
            parts.append(f"[Knowledge {index}] {item}")
    return "\n".join(parts)
```

Return:

```python
RetrievalResult(
    question_id=question.question_id,
    conversation_id=question.conversation_id,
    formatted_context=_memoryos_formatted_context(retrieval_result),
    metadata={
        "method": "MemoryOS",
        "retrieved_page_count": len(retrieval_result["retrieval_queue"]),
        "retrieved_knowledge_count": len(retrieval_result["long_term_knowledge"]),
    },
)
```

- [x] **Step 4: Keep legacy `get_answer()` wrapper**

For migration safety, leave existing `get_answer()` behavior intact for tests that compare old MemoryOS prompt behavior. Do not call `retrieve()` from `get_answer()` yet if that would lose `system_prompt` observer behavior; new runner will call `retrieve()` directly.

- [x] **Step 5: Run MemoryOS focused tests**

Run:

```bash
uv run pytest tests/test_memoryos_adapter.py tests/test_memoryos_registered_prediction.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

```bash
git add src/memory_benchmark/methods/memoryos_adapter.py tests/test_memoryos_adapter.py
git commit -m "feat: migrate MemoryOS adapter to retrieve-first"
```

Status: deferred. 2026-06-21 code and focused tests are complete, but the worktree contains
multiple Codex/OpenCode batches, so commit should be done after diff grouping.

---

## Task 13: Switch Registered Prediction to Retrieve-First

**Files:**

- Modify: `src/memory_benchmark/cli/run_prediction.py`
- Modify: `src/memory_benchmark/methods/registry.py`
- Modify: `tests/test_prediction_cli.py`
- Modify: `tests/test_cost_calibration_smoke.py`
- Modify: `tests/test_main_cli.py`

- [x] **Step 1: Add registered prediction test**

In `tests/test_prediction_cli.py`, add:

```python
def test_registered_prediction_passes_framework_reader_to_runner(monkeypatch, tmp_path: Path) -> None:
    """统一入口应构造 framework reader 并传给 prediction runner。"""

    captured: dict[str, object] = {}

    def fake_run_predictions(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            run_id="run",
            dataset_name="fake",
            total_conversations=1,
            completed_conversations=1,
            total_questions=1,
            completed_questions=1,
            prediction_path=str(tmp_path / "p.jsonl"),
            private_label_path=str(tmp_path / "l.jsonl"),
            summary_path=str(tmp_path / "s.json"),
            metadata={},
        )

    monkeypatch.setattr(
        "memory_benchmark.cli.run_prediction.run_predictions",
        fake_run_predictions,
    )

    # Reuse existing registry monkeypatch helpers in this file to avoid real API.
    # The assertion below is the required behavior.
    run_registered_conversation_qa_prediction(
        method_name="fake",
        benchmark_name="fake",
        project_root=tmp_path,
        profile_name="smoke",
        confirm_api=True,
    )

    assert captured["answer_reader"] is not None
```

Adapt the fake registry setup to the helpers already used in the file.

- [x] **Step 2: Run test and verify failure**

Run:

```bash
uv run pytest tests/test_prediction_cli.py::test_registered_prediction_passes_framework_reader_to_runner -q
```

Expected:

```text
AssertionError: None is not None
```

- [x] **Step 3: Pass `answer_reader` into runner**

In `src/memory_benchmark/cli/run_prediction.py`, ensure the `run_predictions` call includes:

```python
answer_reader=answer_reader
```

The reader must be constructed after `openai_settings` is available and before `run_predictions`.

- [x] **Step 4: Manifest identity**

Add to prediction manifest:

```python
"answer_protocol": "retrieve_first_v1",
"answer_prompt_profile": answer_prompt_profile,
"answer_prompt_file_sha256": _sha256_file(answer_prompt_path) if answer_prompt_path else None,
"answer_model": openai_settings.model,
```

Do not write API key or unredacted base URL.

- [x] **Step 5: Run registered prediction tests**

Run:

```bash
uv run pytest tests/test_prediction_cli.py tests/test_cost_calibration_smoke.py tests/test_main_cli.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

```bash
git add src/memory_benchmark/cli/run_prediction.py tests/test_prediction_cli.py tests/test_cost_calibration_smoke.py tests/test_main_cli.py
git commit -m "feat: use framework reader in registered prediction"
```

Status: deferred. 2026-06-21 Task 13 implementation and focused tests are complete,
but commit should be done after grouping the broader dirty worktree.

---

## Task 14: Update Efficiency Observation for Framework Answer

**Files:**

- Modify: `src/memory_benchmark/readers/answer.py`
- Modify: `src/memory_benchmark/runners/prediction.py`
- Modify: `tests/test_prediction_efficiency_observations.py`
- Modify: `tests/test_efficiency_analysis.py`

- [x] **Step 1: Add failing observation test**

In `tests/test_prediction_efficiency_observations.py`, add:

```python
def test_retrieve_first_records_context_tokens_and_answer_latency(tmp_path: Path) -> None:
    """framework reader 路径必须记录 retrieval context tokens 和 answer latency。"""

    dataset = _build_dataset()
    provider = RecordingMemoryProvider()
    reader = FrameworkAnswerReader(client=FakeAnswerLLMClient(answer="answer"))

    summary = run_predictions(
        dataset=dataset,
        system=provider,
        run_context=RunContext(
            run_id="retrieve-first-efficiency",
            output_root=tmp_path,
            source_identity={"test": "retrieve-first-efficiency"},
        ),
        policy=PredictionRunPolicy(max_workers=1),
        answer_reader=reader,
        enable_efficiency_observability=True,
    )

    run_dir = Path(summary.summary_path).parents[1]
    observations = read_jsonl(
        run_dir / "artifacts" / "efficiency_observations.prediction.jsonl"
    )
    question_obs = [
        record for record in observations
        if record["observation_type"] == "question_efficiency"
    ]

    assert question_obs
    assert question_obs[0]["retrieval_latency_ms"] is not None
    assert question_obs[0]["injected_memory_context_tokens"] > 0
    assert question_obs[0]["answer_generation_latency_ms"] is not None
```

- [x] **Step 2: Run test and verify failure**

Run:

```bash
uv run pytest tests/test_prediction_efficiency_observations.py::test_retrieve_first_records_context_tokens_and_answer_latency -q
```

Expected failure depends on Task 4 implementation. Acceptable pre-fix failures:

```text
KeyError: 'injected_memory_context_tokens'
```

or:

```text
AssertionError: None is not None
```

- [x] **Step 3: Count answer prompt and context tokens consistently**

Use existing token utilities in `src/memory_benchmark/observability/efficiency/token_counting.py`.

In retrieve-first runner branch:

```python
context_tokens = token_counter.count_text(
    retrieval.formatted_context,
    model_name=answer_reader.client.model_name,
)
```

If current token utility has a different method name, use the existing public API and keep the measurement source as tokenizer estimate unless the API response exposes usage.

- [x] **Step 4: Record answer LLM tokens from OpenAI response**

Enhance `OpenAICompatibleAnswerLLMClient` to expose last usage:

```python
@dataclass(frozen=True)
class AnswerLLMResponse:
    text: str
    raw_response: object | None = None
```

If that is too invasive for the existing `complete()` signature, add `complete_with_metadata()` and make `FrameworkAnswerReader` use it when available.

The runner must record `LLMCallObservation` for answer stage using API usage when available and tokenizer estimate otherwise.

- [x] **Step 5: Run efficiency focused tests**

Run:

```bash
uv run pytest tests/test_prediction_efficiency_observations.py tests/test_efficiency_analysis.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

```bash
git add src/memory_benchmark/readers/answer.py src/memory_benchmark/runners/prediction.py tests/test_prediction_efficiency_observations.py tests/test_efficiency_analysis.py
git commit -m "feat: observe framework reader efficiency"
```

Status: implementation complete, commit deferred. 2026-06-21 Task 14 added
retrieve-first question efficiency tests, context token recording, adapter-safe
retrieval observation fill-in, answer LLM token observation, and framework answer
model inventory. Focused verification:

```bash
uv run pytest tests/test_prediction_efficiency_observations.py tests/test_efficiency_analysis.py tests/test_framework_answer_reader.py -q
uv run pytest tests/test_prediction_runner.py tests/test_prediction_cli.py tests/test_cost_calibration_smoke.py tests/test_main_cli.py -q
uv run pytest tests/test_retrieve_first_protocol.py tests/test_method_registry.py tests/test_benchmark_registry.py -q
```

Results: `23 passed`, `123 passed`, `37 passed`.

---

## Task 15: Update Artifacts and Evaluation Compatibility

**Files:**

- Modify: `src/memory_benchmark/runners/evaluation.py`
- Modify: `tests/test_artifact_evaluation_runner.py`
- Modify: `tests/test_llm_judge_parsing.py`

- [x] **Step 1: Add artifact compatibility test**

In `tests/test_artifact_evaluation_runner.py`, add a fixture run directory containing:

- `artifacts/method_predictions.jsonl`
- `artifacts/evaluator_private_labels.jsonl`
- `artifacts/retrieval_results.prediction.jsonl`

The test should assert existing F1/Judge evaluation ignores retrieval artifact unless evaluator explicitly needs it:

```python
def test_answer_level_evaluation_ignores_retrieval_artifact_by_default(tmp_path: Path) -> None:
    """answer-level metric 只依赖 prediction 和 private labels。"""

    run_dir = _write_minimal_answer_run(tmp_path)
    atomic_write_jsonl(
        run_dir / "artifacts" / "retrieval_results.prediction.jsonl",
        [
            {
                "question_id": "q1",
                "conversation_id": "conv-1",
                "formatted_context": "context",
                "metadata": {},
                "memories": [],
            }
        ],
    )

    summary = run_artifact_evaluation(run_dir, fake_answer_metric, "locomo")

    assert summary.total_questions == 1
```

Use existing helper names in the file.

- [x] **Step 2: Run test**

Run:

```bash
uv run pytest tests/test_artifact_evaluation_runner.py::test_answer_level_evaluation_ignores_retrieval_artifact_by_default -q
```

Expected:

```text
1 passed
```

If it fails, fix evaluation loader so it ignores unknown retrieval artifacts.

- [x] **Step 3: Add optional context passthrough only if already supported**

If LLM judge currently supports context field, pass retrieval context by question id only when evaluator declares it needs context. Do not make LoCoMo F1 depend on retrieval context.

Concrete rule:

```python
if evaluator.requires_retrieval_context:
    context_by_question_id = _load_retrieval_context(paths.retrieval_results_path)
else:
    context_by_question_id = {}
```

If there is no evaluator capability field yet, do not add it in this task.

Current implementation note: there is no evaluator capability field yet, so Task 15
does not pass retrieval context into F1/Judge evaluation. The compatibility test
locks the default answer-level behavior: `retrieval_results.prediction.jsonl` may
exist beside answer artifacts, but `run_artifact_evaluation()` ignores it unless a
future evaluator explicitly opts in.

- [x] **Step 4: Run artifact evaluation tests**

Run:

```bash
uv run pytest tests/test_artifact_evaluation_runner.py tests/test_llm_judge_parsing.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit**

Commit deferred because the working tree contains a large batch of ongoing
retrieve-first/OpenCode changes. Stage and commit only after reviewing the full
scope.

```bash
git add src/memory_benchmark/runners/evaluation.py tests/test_artifact_evaluation_runner.py tests/test_llm_judge_parsing.py
git commit -m "test: keep answer evaluation compatible with retrieval artifacts"
```

---

## Task 16: Documentation and Migration Cleanup

**Files:**

- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/current-roadmap.md`
- Modify: `docs/task-ledger.md`
- Modify: `docs/method-interface-inventory.md`
- Create: `docs/handoffs/2026-06-20-retrieve-first-implementation.md`

- [x] **Step 1: Update docs after code migration**

Set docs to implementation-complete wording:

- `README.md`: remove “尚未完成代码迁移” once all four adapters pass retrieve-first tests.
- `AGENTS.md`: change current断点 to retrieve-first implemented.
- `docs/current-roadmap.md`: check off Phase K implementation tasks that are complete.
- `docs/task-ledger.md`: change “Retrieve-first 主协议实现” from open to closed with test evidence.
- `docs/method-interface-inventory.md`: keep legacy `get_answer()` as historical compatibility only.

- [x] **Step 2: Add handoff**

Create `docs/handoffs/2026-06-20-retrieve-first-implementation.md` with these sections:

```markdown
# 2026-06-20 Retrieve-First Implementation Handoff

## Completed

- Core protocol evidence.
- Framework reader evidence.
- Runner, artifact, and resume evidence.
- Method adapter evidence.

## Verification

- Command output summary.

## Remaining Risks

- Legacy get_answer removal timing
- Full API smoke still requires user confirmation
```

Each bullet must contain the actual completed evidence before committing the implementation.

- [x] **Step 3: Run documentation checks**

Run:

```bash
uv run pytest tests/test_documentation_standards.py -q
git diff --check
```

Expected:

```text
5 passed
git diff --check exits 0
```

- [x] **Step 4: Run focused full retrieve-first regression**

Run:

```bash
uv run pytest \
  tests/test_retrieve_first_protocol.py \
  tests/test_framework_answer_reader.py \
  tests/test_prediction_runner.py \
  tests/test_prediction_efficiency_observations.py \
  tests/test_method_registry.py \
  tests/test_mem0_adapter.py \
  tests/test_amem_adapter.py \
  tests/test_lightmem_adapter.py \
  tests/test_memoryos_adapter.py \
  tests/test_main_cli.py \
  tests/test_prediction_cli.py \
  -q
```

Expected:

```text
passed
```

- [x] **Step 5: Compile**

Run:

```bash
uv run python -m compileall -q src/memory_benchmark tests
```

Expected:

```text
exit 0
```

- [ ] **Step 6: Commit**

Commit deferred because the working tree includes many ongoing retrieve-first,
OpenCode and documentation changes. Review and stage a coherent batch before
committing.

```bash
git add README.md AGENTS.md docs/current-roadmap.md docs/task-ledger.md docs/method-interface-inventory.md docs/handoffs/2026-06-20-retrieve-first-implementation.md
git commit -m "docs: finalize retrieve-first migration status"
```

---

## Final Verification Before Real API Smoke

After all tasks above:

```bash
uv run pytest tests/test_documentation_standards.py -q
uv run pytest tests/test_retrieve_first_protocol.py tests/test_framework_answer_reader.py -q
uv run pytest tests/test_prediction_runner.py tests/test_prediction_efficiency_observations.py -q
uv run pytest tests/test_method_registry.py tests/test_main_cli.py tests/test_prediction_cli.py -q
uv run pytest tests/test_mem0_adapter.py tests/test_amem_adapter.py tests/test_lightmem_adapter.py tests/test_memoryos_adapter.py -q
uv run python -m compileall -q src/memory_benchmark tests
git diff --check
```

Do not run paid API smoke until the user confirms:

- method
- benchmark
- profile
- run_id
- conversation/question/turn limits
- worker count

## Plan Self-Review

Spec coverage:

- `add(conversation)` protocol: Task 1.
- `retrieve(question) -> formatted_context`: Tasks 1, 4, 9, 10, 11, 12.
- framework reader: Tasks 2 and 6.
- custom prompt validation: Task 2 and Task 6.
- retrieval artifact: Task 3 and Task 4.
- retrieve completed / answer pending resume: Task 5.
- efficiency observation: Task 14.
- registry/capability: Task 7.
- built-in method migration: Tasks 9-12.
- docs/handoff: Task 16.

No placeholders remain in required implementation steps. Any instruction that says to adapt a fixture name also states the required behavior and exact assertions.
