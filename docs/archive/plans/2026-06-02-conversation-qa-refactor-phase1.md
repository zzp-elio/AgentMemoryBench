# Conversation-QA Refactor Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old generic benchmark protocol with a clean conversation-QA evaluation framework and run Phase 1 on LoCoMo + LongMemEval.

**Architecture:** The new framework centers on `Dataset -> Conversation -> Session -> Turn -> Question`, with private `GoldAnswerInfo` kept away from method wrappers. Phase 1 uses synchronous `BaseMemorySystem.add()` and `BaseMemorySystem.get_answer()` only; retrieval capability is optional and not used by LoCoMo/LongMemEval runners.

**Tech Stack:** Python 3.11+, dataclasses, unittest, uv, python-dotenv, OpenAI SDK, rich logging.

---

## File Structure Map

Create or replace these files:

- `memory_benchmark/core/entities.py`: new dataclasses: `ImageRef`, `Turn`, `Session`, `Question`, `GoldAnswerInfo`, `Conversation`, `Dataset`, result classes.
- `memory_benchmark/core/interfaces.py`: new ABC interfaces: `BaseMemorySystem`, `BaseMemoryRetriever`.
- `memory_benchmark/core/validators.py`: common and benchmark-specific validation helpers.
- `memory_benchmark/core/exceptions.py`: keep existing domain errors, add validation/data leakage errors.
- `memory_benchmark/benchmark_adapters/base.py`: change adapter contract from `load_cases()` to `load_dataset()`.
- `memory_benchmark/benchmark_adapters/locomo.py`: emit new `Dataset` model.
- `memory_benchmark/benchmark_adapters/longmemeval.py`: emit new `Dataset` model.
- `memory_benchmark/benchmark_adapters/registry.py`: register only Phase 1 adapters initially.
- `memory_benchmark/evaluators/base.py`: evaluator base classes and result dataclasses if not kept in core.
- `memory_benchmark/evaluators/locomo_f1.py`: LoCoMo QA F1 without adversarial/retrieval metrics.
- `memory_benchmark/evaluators/llm_judge.py`: benchmark-specific LLM judge base utility.
- `memory_benchmark/evaluators/locomo_judge.py`: LoCoMo judge wrapper.
- `memory_benchmark/evaluators/longmemeval_judge.py`: LongMemEval judge wrapper.
- `memory_benchmark/runners/conversation_qa.py`: generic synchronous answer-level runner.
- `memory_benchmark/utils/run_logger.py`: rich terminal logging, text run log, JSONL event log.
- `memory_benchmark/methods/mock.py`: simple deterministic method for framework tests.
- `tests/test_core_conversation_entities.py`: validates entity privacy and serialization.
- `tests/test_conversation_dataset_validation.py`: validates required fields and no gold leakage.
- `tests/test_locomo_conversation_adapter.py`: checks LoCoMo conversion.
- `tests/test_longmemeval_conversation_adapter.py`: checks LongMemEval conversion.
- `tests/test_conversation_runner.py`: checks runner does not pass gold answers to method.
- `tests/test_locomo_answer_metrics.py`: checks LoCoMo F1.
- `tests/test_llm_judge_parsing.py`: checks compact/detailed judge output parsing.
- `AGENTS.md`: rewrite for new architecture.
- `README.md`: rewrite for new architecture and commands.
- `docs/architecture.md`, `docs/data-model.md`, `docs/method-interface.md`, `docs/benchmark-scope.md`, `docs/refactor-plan.md`: new docs.

Archive or delete:

- Move old docs and redundant roots to `old/2026-06-02-legacy/`.
- Delete all 已移除的偏好评测 files and references, including `benchmarks/已移除的偏好评测-main`, `dataset数据结构/removed_preference_eval.md`, 已移除的偏好评测 adapter/tests/docs references.

## Verification Commands

Use these throughout:

```bash
uv run python -m unittest discover -s tests -v
uv run python -m unittest tests/test_core_conversation_entities.py -v
uv run python -m unittest tests/test_locomo_conversation_adapter.py -v
uv run python -m unittest tests/test_longmemeval_conversation_adapter.py -v
uv run python -m unittest tests/test_conversation_runner.py -v
rg -n "已移除的偏好评测|removed_preference_eval|reset\\(|ingest\\(|respond\\(|EvalScope|MemorySegment|EvalQuery|IngestResult|UnifiedMemoryAgent" memory_benchmark tests docs AGENTS.md README.md || true
```

Expected final state:

- Unit tests pass.
- Search command returns no active-code/docs matches except archived `old/` if included in search manually.
- `benchmarks/已移除的偏好评测-main` does not exist.
- `dataset数据结构/removed_preference_eval.md` does not exist.

---

### Task 1: Add `rich` Dependency

**Files:**
- Modify: `pyproject.toml`
- Modify generated lock: `uv.lock`

- [ ] **Step 1: Add dependency with uv**

Run:

```bash
uv add rich
```

Expected:

```text
Resolved ... packages
Updated pyproject.toml
Updated uv.lock
```

- [ ] **Step 2: Verify dependency import**

Run:

```bash
uv run python - <<'PY'
from rich.console import Console
console = Console()
console.print("[green]rich-ok[/green]")
PY
```

Expected output contains:

```text
rich-ok
```

---

### Task 2: Archive Old Project Docs and Delete 已移除的偏好评测

**Files:**
- Create directory: `old/2026-06-02-legacy/`
- Move: `docs/*` to `old/2026-06-02-legacy/docs/`, except `docs/superpowers/specs/2026-06-02-conversation-qa-refactor-design.md` and this plan if desired to keep active.
- Move: `任务.md`, `参考.md`, `benchmark-structure-summary.md`, `reports/` to `old/2026-06-02-legacy/`
- Delete: `benchmarks/已移除的偏好评测-main/`
- Delete: `dataset数据结构/removed_preference_eval.md`
- Delete later in code tasks: `memory_benchmark/benchmark_adapters/removed_preference_eval.py`, `tests/test_removed_preference_eval_adapter_options.py`

- [ ] **Step 1: Create archive directory**

Run:

```bash
mkdir -p old/2026-06-02-legacy
```

Expected: directory exists.

- [ ] **Step 2: Preserve active Superpowers docs before archiving**

Run:

```bash
mkdir -p /tmp/memory_benchmark_active_specs
cp docs/superpowers/specs/2026-06-02-conversation-qa-refactor-design.md /tmp/memory_benchmark_active_specs/
cp docs/superpowers/plans/2026-06-02-conversation-qa-refactor-phase1.md /tmp/memory_benchmark_active_specs/
```

Expected: both files exist in `/tmp/memory_benchmark_active_specs`.

- [ ] **Step 3: Move old docs and reports**

Run:

```bash
mkdir -p old/2026-06-02-legacy/docs
if [ -d docs ]; then mv docs/* old/2026-06-02-legacy/docs/ 2>/dev/null || true; fi
mkdir -p docs/superpowers/specs docs/superpowers/plans
cp /tmp/memory_benchmark_active_specs/2026-06-02-conversation-qa-refactor-design.md docs/superpowers/specs/
cp /tmp/memory_benchmark_active_specs/2026-06-02-conversation-qa-refactor-phase1.md docs/superpowers/plans/
for f in 任务.md 参考.md benchmark-structure-summary.md; do
  if [ -e "$f" ]; then mv "$f" old/2026-06-02-legacy/; fi
done
if [ -d reports ]; then mv reports old/2026-06-02-legacy/reports; fi
```

Expected:

```text
docs/superpowers/specs/2026-06-02-conversation-qa-refactor-design.md
docs/superpowers/plans/2026-06-02-conversation-qa-refactor-phase1.md
old/2026-06-02-legacy/docs/
```

- [ ] **Step 4: Delete 已移除的偏好评测 assets**

Run:

```bash
rm -rf benchmarks/已移除的偏好评测-main
rm -f dataset数据结构/removed_preference_eval.md
rm -f memory_benchmark/benchmark_adapters/removed_preference_eval.py
rm -f tests/test_removed_preference_eval_adapter_options.py
```

Expected:

```bash
test ! -e benchmarks/已移除的偏好评测-main
test ! -e dataset数据结构/removed_preference_eval.md
test ! -e memory_benchmark/benchmark_adapters/removed_preference_eval.py
```

- [ ] **Step 5: Verify 已移除的偏好评测 active references are gone except archive**

Run:

```bash
rg -n "已移除的偏好评测|removed_preference_eval" memory_benchmark tests dataset数据结构 benchmarks docs AGENTS.md README.md || true
```

Expected: no matches.

---

### Task 3: Rewrite Core Entities

**Files:**
- Replace: `memory_benchmark/core/entities.py`
- Modify: `memory_benchmark/core/__init__.py`
- Test: `tests/test_core_conversation_entities.py`

- [ ] **Step 1: Write entity tests**

Create `tests/test_core_conversation_entities.py`:

```python
"""测试 conversation-QA v2 core 实体。

这些测试确认新实体明确区分 method 可见的 Question 和 evaluator 私有的
GoldAnswerInfo，避免把标准答案泄漏给 method。
"""

import unittest

from memory_benchmark.core import (
    AnswerResult,
    Conversation,
    Dataset,
    GoldAnswerInfo,
    ImageRef,
    Question,
    Session,
    Turn,
)


class CoreConversationEntitiesTest(unittest.TestCase):
    """验证核心 dataclass 的最小行为。"""

    def test_question_does_not_contain_gold_answer(self):
        """Question 只能包含公开问题字段，不能出现 answer/evidence。"""

        question = Question(
            question_id="q1",
            conversation_id="conv1",
            text="What does Alice like?",
            category="single-hop",
        )

        self.assertFalse(hasattr(question, "answer"))
        self.assertFalse(hasattr(question, "evidence"))
        self.assertEqual(question.conversation_id, "conv1")

    def test_conversation_keeps_gold_answers_separate(self):
        """Conversation 用 questions 和 gold_answers 分离 public/private 数据。"""

        question = Question(question_id="q1", conversation_id="conv1", text="What?")
        gold = GoldAnswerInfo(question_id="q1", answer="Alice likes tea.", evidence=["D1:1"])
        conversation = Conversation(
            conversation_id="conv1",
            sessions=[
                Session(
                    session_id="session_1",
                    session_time="2024-01-01",
                    turns=[Turn(turn_id="t1", speaker="Alice", content="I like tea.")],
                )
            ],
            questions=[question],
            gold_answers={"q1": gold},
        )

        self.assertEqual(conversation.questions[0].text, "What?")
        self.assertEqual(conversation.gold_answers["q1"].answer, "Alice likes tea.")

    def test_image_ref_can_be_attached_to_turn(self):
        """Turn 支持可选 ImageRef，为后续 Mem-Gallery 多模态扩展预留结构。"""

        image = ImageRef(image_id="img1", path="/tmp/a.jpg", caption="a whiteboard")
        turn = Turn(turn_id="t1", speaker="Lena", content="Look at this.", images=[image])

        self.assertEqual(turn.images[0].caption, "a whiteboard")

    def test_answer_result_only_stores_prediction(self):
        """AnswerResult 保存 method 输出，不保存 gold answer。"""

        result = AnswerResult(question_id="q1", conversation_id="conv1", answer="tea")

        self.assertEqual(result.answer, "tea")
        self.assertFalse(hasattr(result, "gold_answer"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
uv run python -m unittest tests/test_core_conversation_entities.py -v
```

Expected: FAIL because new classes are not exported yet.

- [ ] **Step 3: Replace `entities.py`**

Replace `memory_benchmark/core/entities.py` with:

```python
"""conversation-QA v2 核心数据实体。

本模块只定义纯数据对象，不读取文件、不调用模型、不计算指标。核心层级是：
Dataset -> Conversation -> Session -> Turn，以及公开 Question 和私有
GoldAnswerInfo 的强隔离。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ImageRef:
    """多模态图片引用。

    字段:
        image_id: benchmark 内部图片 id。
        path: 本地图片路径。
        caption: 文本 fallback。
        metadata: 图片级公开元信息。
    """

    image_id: str | None = None
    path: str | None = None
    caption: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)


@dataclass
class Turn:
    """单条发言，即一个 speaker 的一次 content。

    `speaker` 是原始说话人；`normalized_role` 是可选标准角色，不能替代 speaker。
    """

    turn_id: str
    speaker: str
    content: str
    normalized_role: str | None = None
    turn_time: str | None = None
    images: list[ImageRef] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)


@dataclass
class Session:
    """一次有边界的对话 session。"""

    session_id: str
    turns: list[Turn] = field(default_factory=list)
    session_time: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)


@dataclass
class Question:
    """method 可见的公开问题。

    注意：这里绝不能包含 gold answer、evidence 或 judge label。
    """

    question_id: str
    conversation_id: str
    text: str
    question_time: str | None = None
    category: str | None = None
    options: dict[str, str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)


@dataclass
class GoldAnswerInfo:
    """evaluator 可见的私有标准答案信息。

    该对象只能进入 evaluator、日志或结果审计，不能传给 method。
    """

    question_id: str
    answer: str
    evidence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)


@dataclass
class Conversation:
    """一个独立 memory namespace 下的长期 conversation。"""

    conversation_id: str
    sessions: list[Session] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)
    gold_answers: dict[str, GoldAnswerInfo] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        """导出 method 可见内容，不包含 gold_answers。"""

        return {
            "conversation_id": self.conversation_id,
            "sessions": [session.to_dict() for session in self.sessions],
            "questions": [question.to_dict() for question in self.questions],
            "metadata": self.metadata,
        }

    def to_dict(self) -> dict[str, Any]:
        """导出完整内容，仅用于 evaluator/debug。"""

        return asdict(self)


@dataclass
class Dataset:
    """一次加载得到的统一数据集。"""

    dataset_name: str
    conversations: list[Conversation] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)


@dataclass
class AddResult:
    """method 写入 conversation 后的最小结果。"""

    conversation_ids: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievedMemory:
    """method 返回的一条相关记忆。"""

    content: str
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    """检索能力输出，Phase 1 runner 不强制使用。"""

    question_id: str
    conversation_id: str
    memories: list[RetrievedMemory] = field(default_factory=list)
    formatted_context: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnswerResult:
    """method 对公开 Question 的回答。"""

    question_id: str
    conversation_id: str
    answer: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricResult:
    """单题或聚合 metric 结果。"""

    metric_name: str
    score: float
    is_correct: bool | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationResult:
    """一次 evaluation 的聚合结果。"""

    dataset_name: str
    total_questions: int
    metrics: dict[str, Any] = field(default_factory=dict)
    detailed_results: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 4: Update `core/__init__.py` exports**

Replace `memory_benchmark/core/__init__.py` with:

```python
"""core 层统一导出入口。"""

from .entities import (
    AddResult,
    AnswerResult,
    Conversation,
    Dataset,
    EvaluationResult,
    GoldAnswerInfo,
    ImageRef,
    MetricResult,
    Question,
    RetrievedMemory,
    RetrievalResult,
    Session,
    Turn,
)
from .exceptions import (
    AdapterAlreadyRegisteredError,
    ConfigurationError,
    DatasetNotFoundError,
    MemoryBenchmarkError,
    UnknownBenchmarkError,
)
from .interfaces import BaseMemoryRetriever, BaseMemorySystem

__all__ = [
    "AddResult",
    "AdapterAlreadyRegisteredError",
    "AnswerResult",
    "BaseMemoryRetriever",
    "BaseMemorySystem",
    "ConfigurationError",
    "Conversation",
    "Dataset",
    "DatasetNotFoundError",
    "EvaluationResult",
    "GoldAnswerInfo",
    "ImageRef",
    "MemoryBenchmarkError",
    "MetricResult",
    "Question",
    "RetrievedMemory",
    "RetrievalResult",
    "Session",
    "Turn",
    "UnknownBenchmarkError",
]
```

- [ ] **Step 5: Run entity test**

Run:

```bash
uv run python -m unittest tests/test_core_conversation_entities.py -v
```

Expected: PASS after interfaces are updated in Task 4, or import failure until Task 4 is complete.

---

### Task 4: Replace Method Interfaces

**Files:**
- Replace: `memory_benchmark/core/interfaces.py`
- Test: `tests/test_core_conversation_entities.py`

- [ ] **Step 1: Replace `interfaces.py`**

Replace `memory_benchmark/core/interfaces.py` with:

```python
"""method / memory system 抽象接口。

Phase 1 使用同步接口，只要求完整 memory system 支持 add 和 get_answer。
检索能力拆到 BaseMemoryRetriever，只有需要检索能力的 benchmark runner 才会要求。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .entities import AddResult, AnswerResult, Conversation, Question, RetrievalResult


class BaseMemorySystem(ABC):
    """完整记忆系统接口。"""

    @abstractmethod
    def add(self, conversations: list[Conversation]) -> AddResult:
        """写入一个或多个 conversation。

        输入:
            conversations: 已完成校验的公开 conversation 列表，不含私有 gold answers。

        输出:
            AddResult: 写入结果，只包含 conversation ids 和公开元信息。
        """

        raise NotImplementedError

    @abstractmethod
    def get_answer(self, question: Question) -> AnswerResult:
        """基于已写入的 conversation 回答公开问题。

        输入:
            question: method 可见问题，不含 gold answer/evidence。

        输出:
            AnswerResult: method 生成答案。
        """

        raise NotImplementedError


class BaseMemoryRetriever(ABC):
    """可选记忆检索能力接口。"""

    @abstractmethod
    def retrieve(self, question: Question) -> RetrievalResult:
        """根据公开问题返回相关记忆。

        输入:
            question: method 可见问题。

        输出:
            RetrievalResult: 相关记忆。Phase 1 不把它用于 recall metric。
        """

        raise NotImplementedError
```

- [ ] **Step 2: Run entity imports again**

Run:

```bash
uv run python -m unittest tests/test_core_conversation_entities.py -v
```

Expected: PASS.

---

### Task 5: Add Validation Layer

**Files:**
- Create: `memory_benchmark/core/validators.py`
- Modify: `memory_benchmark/core/exceptions.py`
- Test: `tests/test_conversation_dataset_validation.py`

- [ ] **Step 1: Write validation tests**

Create `tests/test_conversation_dataset_validation.py`:

```python
"""测试 conversation-QA 数据强约束校验。"""

import unittest

from memory_benchmark.core import Conversation, Dataset, GoldAnswerInfo, Question, Session, Turn
from memory_benchmark.core.exceptions import DatasetValidationError
from memory_benchmark.core.validators import validate_dataset


def build_valid_dataset() -> Dataset:
    """构造一个最小合法 Dataset。"""

    question = Question(question_id="q1", conversation_id="conv1", text="What does Alice like?")
    return Dataset(
        dataset_name="dummy",
        conversations=[
            Conversation(
                conversation_id="conv1",
                sessions=[
                    Session(
                        session_id="s1",
                        session_time="2024-01-01",
                        turns=[Turn(turn_id="t1", speaker="Alice", content="I like tea.")],
                    )
                ],
                questions=[question],
                gold_answers={"q1": GoldAnswerInfo(question_id="q1", answer="tea")},
            )
        ],
    )


class ConversationDatasetValidationTest(unittest.TestCase):
    """验证数据缺字段时能尽早报错。"""

    def test_valid_dataset_passes(self):
        """合法数据集应通过通用校验。"""

        validate_dataset(build_valid_dataset())

    def test_question_without_gold_answer_fails(self):
        """每个 Question 必须有对应 GoldAnswerInfo。"""

        dataset = build_valid_dataset()
        dataset.conversations[0].gold_answers = {}

        with self.assertRaises(DatasetValidationError):
            validate_dataset(dataset)

    def test_turn_without_content_fails(self):
        """纯文本 Phase 1 中 turn content 不能为空。"""

        dataset = build_valid_dataset()
        dataset.conversations[0].sessions[0].turns[0].content = ""

        with self.assertRaises(DatasetValidationError):
            validate_dataset(dataset)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Add validation exception**

Append to `memory_benchmark/core/exceptions.py`:

```python

class DatasetValidationError(MemoryBenchmarkError):
    """统一数据集校验失败。"""

    def __init__(self, message: str):
        super().__init__(f"Dataset validation failed: {message}")


class DataLeakageError(MemoryBenchmarkError):
    """检测到 private data 可能泄漏给 method。"""

    def __init__(self, message: str):
        super().__init__(f"Private data leakage risk: {message}")
```

Update `memory_benchmark/core/__init__.py` to export both classes.

- [ ] **Step 3: Create validators**

Create `memory_benchmark/core/validators.py`:

```python
"""conversation-QA 数据校验工具。

adapter 转换原始数据后必须立刻调用这些函数，保证缺字段在进入 method 前暴露。
"""

from __future__ import annotations

from .entities import Conversation, Dataset
from .exceptions import DatasetValidationError


def validate_dataset(dataset: Dataset) -> None:
    """校验完整 Dataset。

    输入:
        dataset: adapter 生成的统一数据集。

    输出:
        None。发现问题时抛 DatasetValidationError。
    """

    if not dataset.dataset_name:
        raise DatasetValidationError("dataset_name is required")
    if not dataset.conversations:
        raise DatasetValidationError("dataset must contain at least one conversation")
    for conversation in dataset.conversations:
        validate_conversation(conversation)


def validate_conversation(conversation: Conversation) -> None:
    """校验单个 Conversation。"""

    if not conversation.conversation_id:
        raise DatasetValidationError("conversation_id is required")
    if not conversation.sessions:
        raise DatasetValidationError(f"{conversation.conversation_id}: sessions are required")
    for session in conversation.sessions:
        if not session.session_id:
            raise DatasetValidationError(f"{conversation.conversation_id}: session_id is required")
        if not session.turns:
            raise DatasetValidationError(f"{conversation.conversation_id}/{session.session_id}: turns are required")
        for turn in session.turns:
            if not turn.turn_id:
                raise DatasetValidationError(f"{conversation.conversation_id}/{session.session_id}: turn_id is required")
            if not turn.speaker:
                raise DatasetValidationError(f"{turn.turn_id}: speaker is required")
            if not turn.content and not turn.images:
                raise DatasetValidationError(f"{turn.turn_id}: content or images are required")
    if not conversation.questions:
        raise DatasetValidationError(f"{conversation.conversation_id}: questions are required")
    for question in conversation.questions:
        if not question.question_id:
            raise DatasetValidationError(f"{conversation.conversation_id}: question_id is required")
        if question.conversation_id != conversation.conversation_id:
            raise DatasetValidationError(
                f"{question.question_id}: question conversation_id does not match parent conversation"
            )
        if not question.text:
            raise DatasetValidationError(f"{question.question_id}: question text is required")
        if question.question_id not in conversation.gold_answers:
            raise DatasetValidationError(f"{question.question_id}: missing GoldAnswerInfo")
        gold = conversation.gold_answers[question.question_id]
        if gold.question_id != question.question_id:
            raise DatasetValidationError(f"{question.question_id}: gold question_id mismatch")
        if not gold.answer:
            raise DatasetValidationError(f"{question.question_id}: gold answer is required")
```

- [ ] **Step 4: Run validation tests**

Run:

```bash
uv run python -m unittest tests/test_conversation_dataset_validation.py -v
```

Expected: PASS.

---

### Task 6: Replace Adapter Base and Registry

**Files:**
- Replace: `memory_benchmark/benchmark_adapters/base.py`
- Modify: `memory_benchmark/benchmark_adapters/registry.py`
- Modify: `memory_benchmark/benchmark_adapters/__init__.py`
- Test: `tests/test_architecture_extensibility.py` or new registry smoke test

- [ ] **Step 1: Replace adapter base**

Replace `memory_benchmark/benchmark_adapters/base.py` with:

```python
"""benchmark adapter 基类。

adapter 负责读取原始 benchmark 数据，并转换成 conversation-QA v2 Dataset。
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from memory_benchmark.core import Dataset
from memory_benchmark.core.exceptions import DatasetNotFoundError
from memory_benchmark.core.validators import validate_dataset


class BenchmarkAdapter(ABC):
    """所有 benchmark adapter 的基类。"""

    name: str

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root)

    def path(self, *parts: str) -> Path:
        """拼接项目内路径。"""

        return self.project_root.joinpath(*parts)

    def require_path(self, *parts: str) -> Path:
        """检查路径存在，不存在时抛领域异常。"""

        path = self.path(*parts)
        if not path.exists():
            raise DatasetNotFoundError(self.name, "/".join(parts))
        return path

    def load_json(self, *parts: str):
        """读取 JSON 文件。"""

        with self.require_path(*parts).open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def load(self, limit: int | None = None) -> Dataset:
        """读取、转换并校验 Dataset。"""

        dataset = self.load_dataset(limit=limit)
        validate_dataset(dataset)
        self.validate_benchmark_rules(dataset)
        return dataset

    @abstractmethod
    def load_dataset(self, limit: int | None = None) -> Dataset:
        """读取并转换为统一 Dataset。"""

        raise NotImplementedError

    def validate_benchmark_rules(self, dataset: Dataset) -> None:
        """benchmark-specific 校验 hook。默认无额外校验。"""


def reached_limit(count: int, limit: int | None) -> bool:
    """判断是否达到读取上限。"""

    return limit is not None and count >= limit


def sorted_json_files(path: Path) -> list[Path]:
    """返回目录下排序后的 JSON 文件。"""

    return sorted(file for file in path.glob("*.json") if file.is_file())
```

- [ ] **Step 2: Update registry imports only for active adapters**

In `memory_benchmark/benchmark_adapters/__init__.py`, export only:

```python
"""benchmark adapter 注册入口。"""

from .locomo import LoCoMoAdapter
from .longmemeval import LongMemEvalAdapter
from .registry import BenchmarkRegistry, get_adapter, list_benchmarks

__all__ = [
    "BenchmarkRegistry",
    "LoCoMoAdapter",
    "LongMemEvalAdapter",
    "get_adapter",
    "list_benchmarks",
]
```

Ensure `registry.py` registers only LoCoMo and LongMemEval until later phases.

- [ ] **Step 3: Run import smoke**

Run:

```bash
uv run python - <<'PY'
from memory_benchmark.benchmark_adapters import list_benchmarks
print(list_benchmarks())
PY
```

Expected:

```text
['locomo', 'longmemeval']
```

---

### Task 7: Implement LoCoMo Conversation Adapter

**Files:**
- Replace: `memory_benchmark/benchmark_adapters/locomo.py`
- Test: `tests/test_locomo_conversation_adapter.py`

- [ ] **Step 1: Write adapter tests**

Create `tests/test_locomo_conversation_adapter.py`:

```python
"""测试 LoCoMo 转换为 conversation-QA v2 Dataset。"""

from pathlib import Path
import unittest

from memory_benchmark.benchmark_adapters.locomo import LoCoMoAdapter


ROOT = Path(__file__).resolve().parents[1]


class LoCoMoConversationAdapterTest(unittest.TestCase):
    """验证 LoCoMo 的 conversation/session/turn/question 结构。"""

    def test_load_one_conversation(self):
        """第一条 LoCoMo sample 应转换为一个合法 Conversation。"""

        dataset = LoCoMoAdapter(ROOT).load(limit=1)
        conversation = dataset.conversations[0]

        self.assertEqual(dataset.dataset_name, "locomo")
        self.assertTrue(conversation.conversation_id)
        self.assertGreater(len(conversation.sessions), 0)
        self.assertGreater(len(conversation.questions), 0)
        self.assertEqual(conversation.questions[0].conversation_id, conversation.conversation_id)
        self.assertIn(conversation.questions[0].question_id, conversation.gold_answers)
        self.assertTrue(conversation.sessions[0].session_time)
        self.assertTrue(conversation.sessions[0].turns[0].speaker)
        self.assertTrue(conversation.sessions[0].turns[0].content)

    def test_public_conversation_does_not_include_gold_answers(self):
        """to_public_dict 不能包含 gold_answers。"""

        conversation = LoCoMoAdapter(ROOT).load(limit=1).conversations[0]
        public = conversation.to_public_dict()

        self.assertIn("questions", public)
        self.assertNotIn("gold_answers", public)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Implement LoCoMo adapter**

Replace `memory_benchmark/benchmark_adapters/locomo.py` with a readable implementation that:

- reads `benchmarks/locomo-main/data/locomo10.json`;
- creates one `Conversation` per sample;
- creates one `Session` per `session_<n>`;
- creates one `Turn` per original turn;
- creates `Question` objects for QA categories except adversarial category `5`;
- creates `GoldAnswerInfo` with answer and evidence;
- preserves speaker names and session times.

Use these helper signatures:

```python
def _session_keys(conversation_raw: dict[str, object]) -> list[str]: ...
def _session_number(session_key: str) -> int: ...
def _qa_category(raw: dict[str, object]) -> str | None: ...
```

- [ ] **Step 3: Run LoCoMo adapter test**

Run:

```bash
uv run python -m unittest tests/test_locomo_conversation_adapter.py -v
```

Expected: PASS.

---

### Task 8: Implement LongMemEval Conversation Adapter

**Files:**
- Replace: `memory_benchmark/benchmark_adapters/longmemeval.py`
- Test: `tests/test_longmemeval_conversation_adapter.py`

- [ ] **Step 1: Write adapter tests**

Create `tests/test_longmemeval_conversation_adapter.py`:

```python
"""测试 LongMemEval 转换为 conversation-QA v2 Dataset。"""

from pathlib import Path
import unittest

from memory_benchmark.benchmark_adapters.longmemeval import LongMemEvalAdapter


ROOT = Path(__file__).resolve().parents[1]


class LongMemEvalConversationAdapterTest(unittest.TestCase):
    """验证 LongMemEval QA-centered instance 转换。"""

    def test_load_one_instance(self):
        """第一条 LongMemEval instance 应转换为一个 conversation 和一个 question。"""

        dataset = LongMemEvalAdapter(ROOT).load(limit=1)
        conversation = dataset.conversations[0]
        question = conversation.questions[0]

        self.assertEqual(dataset.dataset_name, "longmemeval")
        self.assertEqual(len(conversation.questions), 1)
        self.assertEqual(question.conversation_id, conversation.conversation_id)
        self.assertTrue(question.question_time)
        self.assertTrue(question.category)
        self.assertIn(question.question_id, conversation.gold_answers)
        self.assertGreater(len(conversation.sessions), 0)
        self.assertGreater(len(conversation.sessions[0].turns), 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Implement LongMemEval adapter**

Replace `memory_benchmark/benchmark_adapters/longmemeval.py` so it:

- reads `benchmarks/LongMemEval-main/data/longmemeval_s_cleaned.json` by default;
- creates one `Conversation` per evaluation instance;
- maps `haystack_sessions` to sessions and turns;
- maps `haystack_dates` to `session_time`;
- maps `question` to `Question.text`;
- maps `question_date` to `Question.question_time`;
- maps `question_type` to `Question.category`;
- maps `answer` to `GoldAnswerInfo.answer`;
- keeps `answer_session_ids` in `GoldAnswerInfo.evidence`.

- [ ] **Step 3: Run LongMemEval adapter test**

Run:

```bash
uv run python -m unittest tests/test_longmemeval_conversation_adapter.py -v
```

Expected: PASS.

---

### Task 9: Add Mock Memory System and Runner

**Files:**
- Create: `memory_benchmark/methods/mock.py`
- Create: `memory_benchmark/runners/conversation_qa.py`
- Test: `tests/test_conversation_runner.py`

- [ ] **Step 1: Write runner test**

Create `tests/test_conversation_runner.py`:

```python
"""测试 conversation-QA runner 不泄漏 gold answer。"""

import unittest

from memory_benchmark.core import (
    AddResult,
    AnswerResult,
    BaseMemorySystem,
    Conversation,
    Dataset,
    GoldAnswerInfo,
    Question,
    Session,
    Turn,
)
from memory_benchmark.runners.conversation_qa import run_conversation_qa


class RecordingSystem(BaseMemorySystem):
    """记录 runner 调用输入的假系统。"""

    def __init__(self):
        self.added_public_payloads = []
        self.questions_seen = []

    def add(self, conversations: list[Conversation]) -> AddResult:
        self.added_public_payloads.extend([conversation.to_public_dict() for conversation in conversations])
        return AddResult(conversation_ids=[conversation.conversation_id for conversation in conversations])

    def get_answer(self, question: Question) -> AnswerResult:
        self.questions_seen.append(question)
        return AnswerResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer="tea",
        )


def build_dataset() -> Dataset:
    """构造最小 runner 数据集。"""

    question = Question(question_id="q1", conversation_id="conv1", text="What does Alice like?")
    return Dataset(
        dataset_name="dummy",
        conversations=[
            Conversation(
                conversation_id="conv1",
                sessions=[
                    Session(session_id="s1", turns=[Turn(turn_id="t1", speaker="Alice", content="I like tea.")])
                ],
                questions=[question],
                gold_answers={"q1": GoldAnswerInfo(question_id="q1", answer="tea")},
            )
        ],
    )


class ConversationRunnerTest(unittest.TestCase):
    """验证 runner 的最小执行流程。"""

    def test_runner_does_not_pass_gold_to_system(self):
        """system.add 和 system.get_answer 都不应看到 gold answer。"""

        system = RecordingSystem()
        result = run_conversation_qa(dataset=build_dataset(), system=system, evaluators=[])

        self.assertEqual(result.total_questions, 1)
        self.assertNotIn("gold_answers", system.added_public_payloads[0])
        self.assertFalse(hasattr(system.questions_seen[0], "answer"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Implement runner**

Create `memory_benchmark/runners/conversation_qa.py`:

```python
"""通用 conversation-QA 同步 runner。"""

from __future__ import annotations

from collections.abc import Iterable

from memory_benchmark.core import BaseMemorySystem, Dataset, EvaluationResult, MetricResult
from memory_benchmark.core.validators import validate_dataset


class BaseAnswerEvaluator:
    """answer-level evaluator 最小协议。"""

    metric_name: str

    def evaluate(self, question, answer, gold) -> MetricResult:
        """评估一个 answer。"""

        raise NotImplementedError


def run_conversation_qa(
    dataset: Dataset,
    system: BaseMemorySystem,
    evaluators: Iterable[BaseAnswerEvaluator],
) -> EvaluationResult:
    """按 conversation 隔离执行 answer quality evaluation。"""

    validate_dataset(dataset)
    detailed_results: list[dict] = []
    total_questions = 0

    for conversation in dataset.conversations:
        system.add([conversation])
        for question in conversation.questions:
            total_questions += 1
            answer = system.get_answer(question)
            gold = conversation.gold_answers[question.question_id]
            metric_outputs = [
                evaluator.evaluate(question=question, answer=answer, gold=gold)
                for evaluator in evaluators
            ]
            detailed_results.append(
                {
                    "conversation_id": conversation.conversation_id,
                    "question_id": question.question_id,
                    "question": question.text,
                    "prediction": answer.answer,
                    "metrics": [metric.__dict__ for metric in metric_outputs],
                }
            )

    return EvaluationResult(
        dataset_name=dataset.dataset_name,
        total_questions=total_questions,
        detailed_results=detailed_results,
        metrics={},
    )
```

- [ ] **Step 3: Add mock method**

Create `memory_benchmark/methods/mock.py`:

```python
"""用于测试 runner 的 mock memory system。"""

from __future__ import annotations

from memory_benchmark.core import AddResult, AnswerResult, BaseMemorySystem, Conversation, Question


class MockMemorySystem(BaseMemorySystem):
    """按 question_id 返回固定答案的测试系统。"""

    def __init__(self, answers: dict[str, str] | None = None):
        self.answers = answers or {}
        self.added_conversation_ids: list[str] = []

    def add(self, conversations: list[Conversation]) -> AddResult:
        self.added_conversation_ids.extend(conversation.conversation_id for conversation in conversations)
        return AddResult(conversation_ids=[conversation.conversation_id for conversation in conversations])

    def get_answer(self, question: Question) -> AnswerResult:
        return AnswerResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer=self.answers.get(question.question_id, ""),
        )
```

- [ ] **Step 4: Run runner test**

Run:

```bash
uv run python -m unittest tests/test_conversation_runner.py -v
```

Expected: PASS.

---

### Task 10: Implement LoCoMo F1 Metric

**Files:**
- Create or replace: `memory_benchmark/evaluators/locomo_f1.py`
- Test: `tests/test_locomo_answer_metrics.py`

- [ ] **Step 1: Write metric test**

Create `tests/test_locomo_answer_metrics.py`:

```python
"""测试 LoCoMo answer-level F1。"""

import unittest

from memory_benchmark.core import AnswerResult, GoldAnswerInfo, Question
from memory_benchmark.evaluators.locomo_f1 import LoCoMoF1Evaluator


class LoCoMoAnswerMetricsTest(unittest.TestCase):
    """验证 LoCoMo F1 的基本行为。"""

    def test_exact_answer_gets_one(self):
        """完全一致答案 F1 为 1。"""

        evaluator = LoCoMoF1Evaluator()
        result = evaluator.evaluate(
            question=Question(question_id="q1", conversation_id="c1", text="What?"),
            answer=AnswerResult(question_id="q1", conversation_id="c1", answer="green tea"),
            gold=GoldAnswerInfo(question_id="q1", answer="green tea"),
        )

        self.assertEqual(result.score, 1.0)

    def test_partial_overlap_between_prediction_and_gold(self):
        """部分 token 重叠时 F1 介于 0 和 1。"""

        evaluator = LoCoMoF1Evaluator()
        result = evaluator.evaluate(
            question=Question(question_id="q1", conversation_id="c1", text="What?"),
            answer=AnswerResult(question_id="q1", conversation_id="c1", answer="tea"),
            gold=GoldAnswerInfo(question_id="q1", answer="green tea"),
        )

        self.assertGreater(result.score, 0.0)
        self.assertLess(result.score, 1.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Implement evaluator**

Create `memory_benchmark/evaluators/locomo_f1.py` with lowercase/punctuation/article normalization and token F1. Do not implement retrieval recall or adversarial special rules.

- [ ] **Step 3: Run metric test**

Run:

```bash
uv run python -m unittest tests/test_locomo_answer_metrics.py -v
```

Expected: PASS.

---

### Task 11: Implement LLM Judge Parsing and Benchmark-Specific Judge Classes

**Files:**
- Create: `memory_benchmark/evaluators/llm_judge.py`
- Create: `memory_benchmark/evaluators/locomo_judge.py`
- Create: `memory_benchmark/evaluators/longmemeval_judge.py`
- Test: `tests/test_llm_judge_parsing.py`

- [ ] **Step 1: Write parsing tests**

Create `tests/test_llm_judge_parsing.py`:

```python
"""测试 LLM judge compact/detailed 输出解析。"""

import unittest

from memory_benchmark.evaluators.llm_judge import parse_judge_response


class LLMJudgeParsingTest(unittest.TestCase):
    """验证 judge 输出解析。"""

    def test_parse_compact_true(self):
        """compact 模式允许 true。"""

        parsed = parse_judge_response("true", mode="compact")
        self.assertTrue(parsed.is_correct)

    def test_parse_compact_false(self):
        """compact 模式允许 false。"""

        parsed = parse_judge_response("false", mode="compact")
        self.assertFalse(parsed.is_correct)

    def test_parse_detailed_json(self):
        """detailed 模式解析 JSON reason。"""

        parsed = parse_judge_response('{"is_correct": true, "reason": "same meaning"}', mode="detailed")
        self.assertTrue(parsed.is_correct)
        self.assertEqual(parsed.reason, "same meaning")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Implement parser and judge dataclass**

Create `memory_benchmark/evaluators/llm_judge.py` with:

```python
@dataclass
class JudgeDecision:
    is_correct: bool
    reason: str = ""
```

and:

```python
def parse_judge_response(text: str, mode: str) -> JudgeDecision:
    ...
```

Rules:

- compact accepts only `true` or `false` after strip/lower.
- detailed accepts JSON object with `is_correct` and optional `reason`.
- invalid output raises `DatasetValidationError` or a new `JudgeOutputError`.

- [ ] **Step 3: Add benchmark-specific judge shell classes**

Create classes with prompt-building methods:

```python
class LoCoMoJudgeEvaluator:
    metric_name = "locomo_judge_accuracy"
    ...

class LongMemEvalJudgeEvaluator:
    metric_name = "longmemeval_judge_accuracy"
    ...
```

Use OpenAI config from `load_settings()`; do not print API keys.

- [ ] **Step 4: Run parser tests**

Run:

```bash
uv run python -m unittest tests/test_llm_judge_parsing.py -v
```

Expected: PASS.

---

### Task 12: Add Rich Run Logger

**Files:**
- Create: `memory_benchmark/utils/run_logger.py`
- Test: `tests/test_run_logger.py`

- [ ] **Step 1: Write logger test**

Create `tests/test_run_logger.py`:

```python
"""测试运行期日志文件和 JSONL 事件日志。"""

import json
from pathlib import Path
import tempfile
import unittest

from memory_benchmark.utils.run_logger import RunLogger


class RunLoggerTest(unittest.TestCase):
    """验证日志会写入文件。"""

    def test_event_log_writes_jsonl(self):
        """log_event 应追加 JSONL。"""

        with tempfile.TemporaryDirectory() as tmp:
            logger = RunLogger(Path(tmp))
            logger.log_event("run_started", {"dataset": "locomo"})
            events_file = Path(tmp) / "events.jsonl"
            records = [json.loads(line) for line in events_file.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(records[0]["event"], "run_started")
        self.assertEqual(records[0]["dataset"], "locomo")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Implement logger**

Create `memory_benchmark/utils/run_logger.py`:

```python
"""运行期日志工具。

终端使用 rich 展示，人类可读日志写 run.log，结构化事件写 events.jsonl。
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from rich.console import Console


class RunLogger:
    """一次 eval run 的日志封装。"""

    def __init__(self, log_dir: str | Path):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.console = Console()
        self.events_file = self.log_dir / "events.jsonl"
        self.run_log_file = self.log_dir / "run.log"
        self.events_file.write_text("", encoding="utf-8")
        self.logger = logging.getLogger(f"memory_benchmark.run.{id(self)}")
        self.logger.setLevel(logging.INFO)
        self.logger.handlers.clear()
        handler = logging.FileHandler(self.run_log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        self.logger.addHandler(handler)

    def info(self, message: str) -> None:
        """同时写终端和 run.log。"""

        self.console.print(f"[cyan]{message}[/cyan]")
        self.logger.info(message)

    def log_event(self, event: str, payload: dict[str, Any]) -> None:
        """追加结构化 JSONL 事件。"""

        record = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "event": event,
            **payload,
        }
        with self.events_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
```

- [ ] **Step 3: Run logger test**

Run:

```bash
uv run python -m unittest tests/test_run_logger.py -v
```

Expected: PASS.

---

### Task 13: Rewrite Project Documentation

**Files:**
- Replace: `AGENTS.md`
- Replace: `README.md`
- Create: `docs/architecture.md`
- Create: `docs/data-model.md`
- Create: `docs/method-interface.md`
- Create: `docs/benchmark-scope.md`
- Create: `docs/refactor-plan.md`

- [ ] **Step 1: Rewrite `AGENTS.md`**

Must include:

- Project now only targets conversation + QA memory benchmarks.
- Phase 1 only LoCoMo + LongMemEval.
- 已移除的偏好评测 is permanently removed.
- `old/` is archive only and not a source of truth.
- Any substantive design uncertainty must be discussed with the user before action.
- Gold answers must never be passed to method code.
- Phase 1 is sync only, no efficiency metrics.

- [ ] **Step 2: Rewrite `README.md`**

Must include:

- New architecture diagram in text.
- Directory responsibilities.
- Method interface.
- Dataset model.
- Phase 1 commands.
- Logging output structure.

- [ ] **Step 3: Create docs**

Create concise Chinese docs matching the spec:

```text
docs/architecture.md
docs/data-model.md
docs/method-interface.md
docs/benchmark-scope.md
docs/refactor-plan.md
```

- [ ] **Step 4: Verify documentation does not mention old active model**

Run:

```bash
rg -n "EvalScope|MemorySegment|EvalQuery|UnifiedMemoryAgent|reset\\(|ingest\\(|respond\\(|已移除的偏好评测|removed_preference_eval" AGENTS.md README.md docs || true
```

Expected: no matches except statements saying 已移除的偏好评测 was removed if deliberately included.

---

### Task 14: Remove or Rewrite Old Tests

**Files:**
- Delete or rewrite tests tied to old protocol:
  - `tests/test_phase1_skeleton.py`
  - `tests/test_core_interface_contract.py`
  - `tests/test_dataset_normalization_samples.py`
  - `tests/test_dataset_structure_alignment.py`
  - `tests/test_temporal_fields.py`
  - `tests/test_locomo_runner.py`
  - `tests/test_mem0_wrapper.py` if tied to `reset/ingest/respond`
  - `tests/test_mem0_locomo_smoke_cli.py` if tied to old CLI

- [ ] **Step 1: Identify old-protocol test references**

Run:

```bash
rg -n "EvalScope|MemorySegment|EvalQuery|IngestResult|UnifiedMemoryAgent|reset\\(|ingest\\(|respond\\(|已移除的偏好评测|removed_preference_eval" tests
```

Expected: list of old tests to remove or rewrite.

- [ ] **Step 2: Remove obsolete tests**

Delete tests that cannot be adapted to conversation-QA v2.

- [ ] **Step 3: Run focused new tests**

Run:

```bash
uv run python -m unittest tests/test_core_conversation_entities.py tests/test_conversation_dataset_validation.py tests/test_locomo_conversation_adapter.py tests/test_longmemeval_conversation_adapter.py tests/test_conversation_runner.py -v
```

Expected: PASS.

---

### Task 15: Final Phase 1 Verification

**Files:**
- All modified files.

- [ ] **Step 1: Run all tests**

Run:

```bash
uv run python -m unittest discover -s tests -v
```

Expected: PASS.

- [ ] **Step 2: Search active code/docs for removed concepts**

Run:

```bash
rg -n "已移除的偏好评测|removed_preference_eval|EvalScope|MemorySegment|EvalQuery|IngestResult|UnifiedMemoryAgent|reset\\(|ingest\\(|respond\\(" memory_benchmark tests docs AGENTS.md README.md || true
```

Expected: no active matches, except explicit documentation sentence that 已移除的偏好评测 is removed if retained.

- [ ] **Step 3: Verify 已移除的偏好评测 deletion**

Run:

```bash
test ! -e benchmarks/已移除的偏好评测-main
test ! -e dataset数据结构/removed_preference_eval.md
test ! -e memory_benchmark/benchmark_adapters/removed_preference_eval.py
```

Expected: exit code 0.

- [ ] **Step 4: Verify adapters load one sample**

Run:

```bash
uv run python - <<'PY'
from pathlib import Path
from memory_benchmark.benchmark_adapters.locomo import LoCoMoAdapter
from memory_benchmark.benchmark_adapters.longmemeval import LongMemEvalAdapter
root = Path.cwd()
for adapter_cls in [LoCoMoAdapter, LongMemEvalAdapter]:
    dataset = adapter_cls(root).load(limit=1)
    conv = dataset.conversations[0]
    print(dataset.dataset_name, conv.conversation_id, len(conv.sessions), len(conv.questions))
PY
```

Expected output has two lines, one for `locomo`, one for `longmemeval`, each with positive session/question counts.

---

## Execution Recommendation

Use subagent-driven execution if available:

- Task 1-2: cleanup subagent
- Task 3-6: core/interface/validation subagent
- Task 7-8: adapters subagent
- Task 9-12: runner/evaluator/logging subagent
- Task 13-15: docs/final verification subagent

If executing inline, stop after Tasks 2, 6, 8, 12, and 15 for review checkpoints.
