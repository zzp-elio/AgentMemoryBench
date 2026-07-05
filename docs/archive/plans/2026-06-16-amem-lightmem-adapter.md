# A-Mem and LightMem Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 接入 A-Mem 与 LightMem 两个第三方 memory method，使它们通过现有 conversation-QA 通用 runner 运行，并复用标准 artifact、resume 和 Phase G efficiency observation。

**Architecture:** 先实现 A-Mem 垂直闭环，再实现 LightMem。每个 adapter 都只包装 `third_party/methods/` 中的官方源码，按 `conversation_id` 隔离 runtime/state，通过 `BaseMemorySystem.add()` 与 `get_answer()` 接入 registry。效率观测优先在 wrapper 边界记录；只有 wrapper 无法精确观测时才考虑默认关闭的纯 observer。

**Tech Stack:** Python 3.12、dataclasses、TOML profile、pytest、现有 `memory_benchmark.core`、`methods.registry`、`observability.efficiency`、`storage` 和 `runners.prediction`。

---

> **2026-06-16 后续纠偏：** 本计划中的早期 smoke 示例曾降低 `retrieve_k` /
> `retrieve_limit`。最新规则以 `docs/method-resource-parameter-audit.md` 为准：
> smoke 也使用官方 method 参数，成本控制只通过 benchmark 数据规模裁剪。当前实际配置为
> A-Mem `retrieve_k=10`、Mem0 `top_k=200`、LightMem `retrieve_limit=60`。

## 文件结构

新增：

```text
configs/methods/amem.toml
configs/methods/lightmem.toml
src/memory_benchmark/methods/amem_adapter.py
src/memory_benchmark/methods/lightmem_adapter.py
tests/test_amem_adapter.py
tests/test_lightmem_adapter.py
tests/test_amem_lightmem_registry.py
```

修改：

```text
src/memory_benchmark/methods/registry.py
src/memory_benchmark/methods/__init__.py
docs/current-roadmap.md
AGENTS.md
docs/handoffs/2026-06-16-amem-lightmem-adapters.md
README.md
```

不修改：

```text
third_party/methods/A-mem/**
third_party/methods/LightMem/**
outputs/memoryos-locomo-full-20260603/**
```

除非后续确认 wrapper 无法观测关键字段，才允许对第三方源码增加默认关闭、行为等价的纯 observer。

## Task 1：A-Mem 官方入口确认与 import/source identity 基础

**Files:**
- Create: `tests/test_amem_adapter.py`
- Create: `src/memory_benchmark/methods/amem_adapter.py`
- Create: `configs/methods/amem.toml`
- Modify: `docs/handoffs/2026-06-16-amem-lightmem-adapters.md`

- [x] **Step 1: 写 A-Mem config 与 source identity 的失败测试**

在 `tests/test_amem_adapter.py` 写入：

```python
"""A-Mem adapter 的配置、源码身份和基础契约测试。

这些测试不调用真实 API。测试目标是确认 adapter 能找到 vendored A-Mem 源码、能加载
强类型 profile，并且 source identity 会覆盖官方核心源码。
"""

from pathlib import Path

import pytest

from memory_benchmark.config import load_path_settings
from memory_benchmark.core import ConfigurationError
from memory_benchmark.methods.amem_adapter import AMemConfig, build_amem_source_identity


def test_amem_config_rejects_invalid_retrieve_k():
    """retrieve_k 是 method 内部检索深度，必须为正数。"""

    with pytest.raises(ConfigurationError, match="retrieve_k"):
        AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=0,
            max_workers=1,
            use_robust_layer=True,
            profile_name="bad",
        )


def test_amem_source_identity_covers_official_core_files():
    """source identity 必须覆盖 A-Mem 官方核心文件，保证 resume 可审计。"""

    identity = build_amem_source_identity(load_path_settings())

    assert identity["source_sha256"]
    assert identity["file_count"] >= 3
    assert "memory_layer_robust.py" in identity["files"]
    assert "llm_text_parsers.py" in identity["files"]
    assert "README.md" in identity["files"]
```

- [x] **Step 2: 运行 RED**

Run:

```bash
uv run pytest tests/test_amem_adapter.py::test_amem_config_rejects_invalid_retrieve_k \
  tests/test_amem_adapter.py::test_amem_source_identity_covers_official_core_files -q
```

Expected: collection failure，原因是 `memory_benchmark.methods.amem_adapter` 尚不存在。

- [x] **Step 3: 添加 A-Mem TOML profile**

创建 `configs/methods/amem.toml`：

```toml
# A-Mem 官方 LoCoMo robust 入口的 method profile。
# smoke 只用于小样本链路验证；official_full 保留官方默认 retrieve_k=10。

[smoke]
llm_model = "gpt-4o-mini"
embedding_model = "all-MiniLM-L6-v2"
retrieve_k = 3
max_workers = 1
use_robust_layer = true
suppress_official_stdout = true

[official_full]
llm_model = "gpt-4o-mini"
embedding_model = "all-MiniLM-L6-v2"
retrieve_k = 10
max_workers = 1
use_robust_layer = true
suppress_official_stdout = true
```

- [x] **Step 4: 实现最小 AMemConfig 与 source identity**

创建 `src/memory_benchmark/methods/amem_adapter.py`，先只实现：

```python
"""A-Mem 的 conversation-QA 适配器。

本模块包装 `third_party/methods/A-mem/` 中的官方 robust memory layer。Adapter 负责
配置校验、源码身份、conversation 隔离和统一接口；不重写 A-Mem 的记忆算法。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
from typing import Any

from memory_benchmark.config.settings import PathSettings, load_path_settings
from memory_benchmark.core import ConfigurationError


AMEM_METHOD_DIRECTORY = "A-mem"
AMEM_ADAPTER_VERSION = "conversation-qa-v1"
AMEM_READER_PROMPT_VERSION = "amem-reader-v1"


@dataclass(frozen=True)
class AMemConfig:
    """A-Mem 运行 profile。

    字段:
        llm_model: A-Mem 写入、查询改写和 reader 使用的 LLM。
        embedding_model: A-Mem SimpleEmbeddingRetriever 使用的 SentenceTransformer 模型。
        retrieve_k: method 内部检索记忆数量，不进入统一接口参数。
        max_workers: runner 可读取的建议 conversation 并发数；初期保持 1。
        use_robust_layer: 是否使用官方 robust layer；当前必须为 true。
        suppress_official_stdout: 是否压制第三方源码中的 stdout。
        profile_name: 可审计 profile 名称。
    """

    llm_model: str
    embedding_model: str
    retrieve_k: int
    max_workers: int
    use_robust_layer: bool = True
    suppress_official_stdout: bool = True
    profile_name: str = "custom"

    def __post_init__(self) -> None:
        """强校验会影响实验语义的配置。"""

        if not self.llm_model.strip():
            raise ConfigurationError("A-Mem llm_model is required")
        if not self.embedding_model.strip():
            raise ConfigurationError("A-Mem embedding_model is required")
        if self.retrieve_k < 1:
            raise ConfigurationError("A-Mem retrieve_k must be positive")
        if self.max_workers < 1:
            raise ConfigurationError("A-Mem max_workers must be positive")
        if not self.use_robust_layer:
            raise ConfigurationError("A-Mem adapter currently requires use_robust_layer=true")

    def to_manifest(self) -> dict[str, Any]:
        """返回不含 secret 和绝对存储路径的公开配置。"""

        return {
            **asdict(self),
            "adapter_version": AMEM_ADAPTER_VERSION,
            "reader_prompt_version": AMEM_READER_PROMPT_VERSION,
            "llm_provider": "openai-compatible",
            "embedding_provider": "sentence-transformers",
        }


def build_amem_source_identity(
    path_settings: PathSettings | None = None,
) -> dict[str, Any]:
    """计算 vendored A-Mem 关键源码的确定性身份。"""

    settings = path_settings or load_path_settings()
    amem_root = settings.resolve_third_party_method_path(AMEM_METHOD_DIRECTORY)
    required_files = [
        "README.md",
        "memory_layer_robust.py",
        "llm_text_parsers.py",
        "requirements.txt",
    ]
    source_files = [amem_root / relative_path for relative_path in required_files]
    missing = [path for path in source_files if not path.is_file()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise ConfigurationError(f"A-Mem source files missing: {missing_text}")

    digest = hashlib.sha256()
    relative_paths: list[str] = []
    for source_file in source_files:
        relative_path = source_file.relative_to(amem_root).as_posix()
        relative_paths.append(relative_path)
        path_bytes = relative_path.encode("utf-8")
        content = source_file.read_bytes()
        digest.update(len(path_bytes).to_bytes(8, byteorder="big"))
        digest.update(path_bytes)
        digest.update(len(content).to_bytes(8, byteorder="big"))
        digest.update(content)

    return {
        "source_sha256": digest.hexdigest(),
        "file_count": len(relative_paths),
        "files": relative_paths,
    }
```

- [x] **Step 5: 运行 GREEN**

Run:

```bash
uv run pytest tests/test_amem_adapter.py::test_amem_config_rejects_invalid_retrieve_k \
  tests/test_amem_adapter.py::test_amem_source_identity_covers_official_core_files -q
```

Expected: `2 passed`。

## Task 2：A-Mem BaseMemorySystem wrapper 与私有标签边界

**Files:**
- Modify: `src/memory_benchmark/methods/amem_adapter.py`
- Modify: `tests/test_amem_adapter.py`

- [x] **Step 1: 写 fake backend 测试**

追加到 `tests/test_amem_adapter.py`：

```python
from memory_benchmark.core import (
    AnswerResult,
    Conversation,
    GoldAnswerInfo,
    Question,
    Session,
    Turn,
)
from memory_benchmark.methods.amem_adapter import AMem


class FakeAMemRuntime:
    """模拟 A-Mem runtime，只记录 wrapper 传入的公开内容。"""

    def __init__(self):
        self.added_notes = []
        self.queries = []

    def add_note(self, content, time=None):
        self.added_notes.append({"content": content, "time": time})
        return f"note-{len(self.added_notes)}"

    def find_related_memories_raw(self, query, k=5):
        self.queries.append({"query": query, "k": k})
        return "memory content from fake runtime"


class FakeLLM:
    """模拟 OpenAI-compatible reader，返回固定答案。"""

    def __init__(self):
        self.prompts = []

    def get_completion(self, prompt, temperature=0.7):
        self.prompts.append({"prompt": prompt, "temperature": temperature})
        return "fake answer"


def _conversation_with_private_gold() -> Conversation:
    question = Question(
        question_id="q-1",
        conversation_id="conv-1",
        text="What does Alice like?",
        category="1",
    )
    return Conversation(
        conversation_id="conv-1",
        sessions=[
            Session(
                session_id="s-1",
                session_time="2026-01-01",
                turns=[
                    Turn(turn_id="t-1", speaker="Alice", content="I like tea."),
                    Turn(turn_id="t-2", speaker="Bob", content="Noted."),
                ],
            )
        ],
        questions=[question],
        gold_answers={
            "q-1": GoldAnswerInfo(
                question_id="q-1",
                answer="tea",
                evidence=["private-evidence-id"],
            )
        },
    )


def test_amem_add_and_get_answer_never_pass_private_gold_to_method():
    """A-Mem wrapper 只能把公开 conversation 和 question 传给第三方 runtime。"""

    runtime = FakeAMemRuntime()
    llm = FakeLLM()
    method = AMem(
        config=AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=2,
            max_workers=1,
            profile_name="smoke",
        ),
        runtime_factory=lambda conversation_id: runtime,
        answer_llm=llm,
    )
    conversation = _conversation_with_private_gold()

    add_result = method.add([conversation])
    answer = method.get_answer(conversation.questions[0])

    assert add_result.conversation_ids == ["conv-1"]
    assert isinstance(answer, AnswerResult)
    assert answer.answer == "fake answer"
    public_text = "\n".join(note["content"] for note in runtime.added_notes)
    prompt_text = llm.prompts[0]["prompt"]
    assert "private-evidence-id" not in public_text
    assert "private-evidence-id" not in prompt_text
    assert "tea" not in prompt_text
    assert runtime.queries == [{"query": "What does Alice like?", "k": 2}]
```

- [x] **Step 2: 运行 RED**

Run:

```bash
uv run pytest tests/test_amem_adapter.py::test_amem_add_and_get_answer_never_pass_private_gold_to_method -q
```

Expected: fail，原因是 `AMem` 未实现。

- [x] **Step 3: 实现 wrapper 最小闭环**

在 `src/memory_benchmark/methods/amem_adapter.py` 增加：

```python
import contextlib
import io
from collections.abc import Callable
from time import perf_counter_ns

from memory_benchmark.core import AddResult, AnswerResult, Conversation, Question, Turn
from memory_benchmark.core.interfaces import BaseMemorySystem


class AMem(BaseMemorySystem):
    """使用官方 A-Mem robust memory layer 的统一 memory system。"""

    def __init__(
        self,
        config: AMemConfig,
        runtime_factory: Callable[[str], Any] | None = None,
        answer_llm: Any | None = None,
    ):
        """初始化 A-Mem adapter。

        输入:
            config: A-Mem 强类型 profile。
            runtime_factory: 测试可注入 fake；生产为空时后续任务构造官方 runtime。
            answer_llm: 测试可注入 fake；生产为空时后续任务使用官方 LLM controller。
        """

        self.config = config
        self._runtime_factory = runtime_factory
        self._answer_llm = answer_llm
        self._runtimes: dict[str, Any] = {}

    def add(self, conversations: list[Conversation]) -> AddResult:
        """写入一个或多个 conversation。"""

        conversation_ids: list[str] = []
        for conversation in conversations:
            runtime = self._get_or_create_runtime(conversation.conversation_id)
            for turn in self._iter_turns(conversation):
                self._call_runtime_add(runtime, turn)
            conversation_ids.append(conversation.conversation_id)
        return AddResult(conversation_ids=conversation_ids)

    def get_answer(self, question: Question) -> AnswerResult:
        """基于 A-Mem 检索上下文回答公开问题。"""

        if question.conversation_id not in self._runtimes:
            raise ConfigurationError(
                f"A-Mem conversation has not been added: {question.conversation_id}"
            )
        runtime = self._runtimes[question.conversation_id]
        context = runtime.find_related_memories_raw(question.text, k=self.config.retrieve_k)
        prompt = self._build_answer_prompt(question=question, memory_context=str(context))
        answer = self._call_answer_llm(prompt=prompt, question=question)
        return AnswerResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer=str(answer).strip(),
            metadata={
                "method": "amem",
                "retrieve_k": self.config.retrieve_k,
                "reader_prompt_version": AMEM_READER_PROMPT_VERSION,
            },
        )

    def _get_or_create_runtime(self, conversation_id: str) -> Any:
        """返回当前 conversation 的隔离 runtime。"""

        if conversation_id not in self._runtimes:
            if self._runtime_factory is None:
                raise ConfigurationError("A-Mem production runtime is not wired yet")
            self._runtimes[conversation_id] = self._runtime_factory(conversation_id)
        return self._runtimes[conversation_id]

    def _iter_turns(self, conversation: Conversation) -> list[Turn]:
        """按 session 顺序展开公开 turn。"""

        turns: list[Turn] = []
        for session in conversation.sessions:
            turns.extend(session.turns)
        return turns

    def _call_runtime_add(self, runtime: Any, turn: Turn) -> None:
        """把一个公开 turn 写入 A-Mem runtime。"""

        content = f"Speaker {turn.speaker} says: {turn.content}"
        self._suppress_stdout_if_needed(runtime.add_note, content, time=turn.turn_time)

    def _build_answer_prompt(self, question: Question, memory_context: str) -> str:
        """构造不含 gold answer 的固定 reader prompt。"""

        if question.category == "2":
            return (
                f"Based on the context: {memory_context}, answer the following question. "
                "Use DATE of CONVERSATION to answer with an approximate date. "
                "Please generate the shortest possible answer, using words from the "
                "conversation where possible, and avoid using any subjects.\n\n"
                f"Question: {question.text} Short answer:"
            )
        return (
            f"Based on the context: {memory_context}, write an answer in the form of a "
            "short phrase for the following question. Answer with exact words from the "
            f"context whenever possible.\n\nQuestion: {question.text} Short answer:"
        )

    def _call_answer_llm(self, prompt: str, question: Question) -> str:
        """调用 reader LLM；测试阶段由 fake LLM 提供。"""

        if self._answer_llm is None:
            raise ConfigurationError("A-Mem production answer LLM is not wired yet")
        temperature = 0.7
        return self._suppress_stdout_if_needed(
            self._answer_llm.get_completion,
            prompt,
            temperature=temperature,
        )

    def _suppress_stdout_if_needed(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """按配置压制第三方源码 stdout。"""

        if not self.config.suppress_official_stdout:
            return func(*args, **kwargs)
        with contextlib.redirect_stdout(io.StringIO()):
            return func(*args, **kwargs)
```

- [x] **Step 4: 运行 GREEN**

Run:

```bash
uv run pytest tests/test_amem_adapter.py -q
```

Expected: `3 passed`。

## Task 3：A-Mem 官方 robust runtime 构造与 OpenAI-compatible 配置

**Files:**
- Modify: `src/memory_benchmark/methods/amem_adapter.py`
- Modify: `tests/test_amem_adapter.py`

- [x] **Step 1: 写 runtime factory 不触网导入测试**

追加：

```python
def test_amem_can_import_official_robust_layer_without_calling_api():
    """adapter 应能从 vendored A-Mem 源码导入官方 robust runtime 类。"""

    from memory_benchmark.methods.amem_adapter import import_amem_robust_classes

    classes = import_amem_robust_classes(load_path_settings())

    assert classes["RobustAgenticMemorySystem"].__name__ == "RobustAgenticMemorySystem"
```

- [x] **Step 2: 运行 RED**

Run:

```bash
uv run pytest tests/test_amem_adapter.py::test_amem_can_import_official_robust_layer_without_calling_api -q
```

Expected: fail，原因是 `import_amem_robust_classes` 不存在。

- [x] **Step 3: 实现临时 sys.path 导入**

在 `amem_adapter.py` 增加：

```python
import importlib
import sys


def import_amem_robust_classes(path_settings: PathSettings | None = None) -> dict[str, Any]:
    """从 vendored A-Mem 源码导入 robust 类。

    导入过程临时把 A-Mem 根目录放入 `sys.path`，避免把第三方源码安装成一等 package。
    """

    settings = path_settings or load_path_settings()
    amem_root = settings.resolve_third_party_method_path(AMEM_METHOD_DIRECTORY)
    if not (amem_root / "memory_layer_robust.py").is_file():
        raise ConfigurationError(f"A-Mem robust layer missing: {amem_root}")

    root_text = str(amem_root)
    inserted = False
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
        inserted = True
    try:
        module = importlib.import_module("memory_layer_robust")
        return {
            "RobustAgenticMemorySystem": module.RobustAgenticMemorySystem,
            "RobustLLMController": module.RobustLLMController,
        }
    finally:
        if inserted:
            with contextlib.suppress(ValueError):
                sys.path.remove(root_text)
```

- [x] **Step 4: 支持生产 runtime factory**

扩展 `AMem.__init__`，增加 `openai_api_key`、`openai_base_url`、`path_settings` 参数；当
`runtime_factory` 为空时，构造官方 `RobustAgenticMemorySystem`，并把 `api_key` 和
`api_base` 传进去。`answer_llm` 为空时使用 runtime 的 `llm_controller.llm`。

关键实现形态：

```python
    def _create_official_runtime(self, conversation_id: str) -> Any:
        """构造官方 A-Mem robust runtime。"""

        classes = import_amem_robust_classes(self.path_settings)
        runtime_cls = classes["RobustAgenticMemorySystem"]
        return runtime_cls(
            model_name=self.config.embedding_model,
            llm_backend="openai",
            llm_model=self.config.llm_model,
            api_key=self._openai_api_key,
            api_base=self._openai_base_url,
            check_connection=False,
        )
```

同时 `_get_or_create_runtime()` 在 `runtime_factory is None` 时调用 `_create_official_runtime()`。

- [x] **Step 5: 运行 A-Mem focused 测试**

Run:

```bash
uv run pytest tests/test_amem_adapter.py -q
```

Expected: all A-Mem tests pass；不得触网。

## Task 4：A-Mem efficiency observation

**Files:**
- Modify: `src/memory_benchmark/methods/amem_adapter.py`
- Modify: `tests/test_amem_adapter.py`

- [x] **Step 1: 写 observation 失败测试**

追加：

```python
from memory_benchmark.observability.efficiency import EfficiencyCollector


def test_amem_records_question_efficiency_observations():
    """启用 collector 后，A-Mem 应记录 retrieval、context token 和 answer latency。"""

    runtime = FakeAMemRuntime()
    llm = FakeLLM()
    collector = EfficiencyCollector(enabled=True)
    method = AMem(
        config=AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=2,
            max_workers=1,
            profile_name="smoke",
        ),
        runtime_factory=lambda conversation_id: runtime,
        answer_llm=llm,
        efficiency_collector=collector,
    )
    conversation = _conversation_with_private_gold()
    method.add([conversation])

    with collector.question_scope("conv-1", "q-1") as scope:
        method.get_answer(conversation.questions[0])
        bundle = scope.finalize()

    assert bundle.question_observation is not None
    assert bundle.question_observation.retrieval_latency_ms is not None
    assert bundle.question_observation.injected_memory_context_tokens > 0
    assert bundle.question_observation.answer_generation_latency_ms is not None
```

- [x] **Step 2: 运行 RED**

Run:

```bash
uv run pytest tests/test_amem_adapter.py::test_amem_records_question_efficiency_observations -q
```

Expected: fail，原因是 adapter 尚未记录 question efficiency。

- [x] **Step 3: 添加 wrapper 边界计时与 token 计数**

在 `AMem.__init__` 保存 `efficiency_collector`。在 `get_answer()` 中：

```python
retrieval_start_ns = perf_counter_ns()
context = runtime.find_related_memories_raw(question.text, k=self.config.retrieve_k)
retrieval_latency_ms = (perf_counter_ns() - retrieval_start_ns) / 1_000_000
self._record_retrieval_latency(question, retrieval_latency_ms)
self._record_injected_context_tokens(question, str(context))

answer_start_ns = perf_counter_ns()
answer = self._call_answer_llm(prompt=prompt, question=question)
answer_latency_ms = (perf_counter_ns() - answer_start_ns) / 1_000_000
self._record_answer_latency(question, answer_latency_ms)
```

调用 collector 的现有 record 方法时，以 `EfficiencyStage.RETRIEVAL`、`ANSWER` 和
`MeasurementSource.FRAMEWORK_TIMER` / `TOKENIZER_ESTIMATE` 标注来源。若 fake LLM 无 usage，
只记录 question-level latency/context tokens，不伪造 LLM usage。

- [x] **Step 4: 运行 GREEN**

Run:

```bash
uv run pytest tests/test_amem_adapter.py -q
```

Expected: all A-Mem tests pass。

## Task 5：A-Mem registry 接入

**Files:**
- Modify: `src/memory_benchmark/methods/registry.py`
- Modify: `src/memory_benchmark/methods/__init__.py`
- Create: `tests/test_amem_lightmem_registry.py`

- [x] **Step 1: 写 registry 失败测试**

创建 `tests/test_amem_lightmem_registry.py`：

```python
"""A-Mem 与 LightMem method registry 测试。

本文件只验证官方集成 method 的静态注册和离线 factory 约束，不调用真实 API。
"""

from memory_benchmark.methods.registry import get_method_registration


def test_amem_is_registered_for_conversation_qa():
    """A-Mem 应作为 conversation-QA 官方 method 注册。"""

    registration = get_method_registration("amem")

    assert registration.name == "amem"
    assert registration.display_name == "A-Mem"
    assert "smoke" in registration.profile_names
    assert "official_full" in registration.profile_names
    assert registration.requires_api is True
```

- [x] **Step 2: 运行 RED**

Run:

```bash
uv run pytest tests/test_amem_lightmem_registry.py::test_amem_is_registered_for_conversation_qa -q
```

Expected: fail，原因是 registry 未注册 `amem`。

- [x] **Step 3: 注册 A-Mem**

在 `registry.py` 导入 `AMem`、`AMemConfig`、`build_amem_source_identity`。增加：

```python
def _build_amem_system(context: MethodBuildContext) -> BaseMemorySystem:
    """根据统一 build context 构造 A-Mem adapter。"""

    if not isinstance(context.config, AMemConfig):
        raise ConfigurationError("A-Mem factory requires AMemConfig")
    if context.openai_settings is None:
        raise ConfigurationError("A-Mem factory requires OpenAI settings")
    return AMem(
        config=context.config,
        openai_api_key=context.openai_settings.api_key,
        openai_base_url=context.openai_settings.base_url,
        path_settings=context.path_settings,
        efficiency_collector=context.efficiency_collector,
    )
```

增加 model inventory getter，至少返回：

```python
ModelDescriptor(model_id="amem-memory-llm", model_name=config.llm_model, model_role="memory_llm", execution_mode="api", tokenizer_name=config.llm_model)
ModelDescriptor(model_id="amem-answer-llm", model_name=config.llm_model, model_role="answer_llm", execution_mode="api", tokenizer_name=config.llm_model)
ModelDescriptor(model_id="amem-embedding", model_name=config.embedding_model, model_role="embedding", execution_mode="local", tokenizer_name=config.embedding_model)
```

并在 method registrations 中加入 `amem`，profile path 指向 `configs/methods/amem.toml`。

- [x] **Step 4: 运行 registry GREEN**

Run:

```bash
uv run pytest tests/test_amem_lightmem_registry.py -q
```

Expected: A-Mem registry tests pass。

## Task 6：A-Mem registered runner offline smoke

**Files:**
- Modify: `tests/test_amem_adapter.py`
- Modify: `tests/test_amem_lightmem_registry.py`

暂停备注：当前只完成了 A-Mem registry 静态接入和 retrieval observation contract focused
测试；真正通过通用 registered prediction runner 的极小 LoCoMo offline/fake smoke 尚未
完成。恢复时不要把 Task 6 误认为已完成。

- [x] **Step 1: 写 runner 装配测试**

如果现有 runner tests 已有 fake method factory pattern，按同样模式新增：

```python
def test_amem_registration_exposes_efficiency_contract():
    """A-Mem 启用效率观测时应声明 retrieval 可拆分。"""

    registration = get_method_registration("amem")
    config = AMemConfig(
        llm_model="gpt-4o-mini",
        embedding_model="all-MiniLM-L6-v2",
        retrieve_k=3,
        max_workers=1,
        profile_name="smoke",
    )

    contract = registration.retrieval_observation_contract_getter(config)

    assert contract.required_by_profile is True
    assert contract.supported_by_method is True
```

- [x] **Step 2: 运行 focused registry + adapter 测试**

Run:

```bash
uv run pytest tests/test_amem_adapter.py tests/test_amem_lightmem_registry.py -q
```

Expected: all pass；不得触网。

- [x] **Step 3: 更新文档断点**

更新：

```text
docs/current-roadmap.md
AGENTS.md
docs/handoffs/2026-06-16-amem-lightmem-adapters.md
```

记录 A-Mem 已完成到 registered offline smoke，LightMem 尚未开始。

## Task 7：LightMem import、config 与 source identity

**Files:**
- Create: `tests/test_lightmem_adapter.py`
- Create: `src/memory_benchmark/methods/lightmem_adapter.py`
- Create: `configs/methods/lightmem.toml`

- [x] **Step 1: 写 LightMem 配置和源码身份失败测试**

创建 `tests/test_lightmem_adapter.py`：

```python
"""LightMem adapter 的配置、源码身份和基础契约测试。

这些测试不调用真实 API，也不初始化重模型。目标是先锁定官方源码路径和强配置校验。
"""

import pytest

from memory_benchmark.config import load_path_settings
from memory_benchmark.core import ConfigurationError
from memory_benchmark.methods.lightmem_adapter import (
    LightMemConfig,
    build_lightmem_source_identity,
    import_lightmem_classes,
)


def test_lightmem_config_rejects_invalid_retrieve_limit():
    """retrieve_limit 是 method 内部检索数量，必须为正数。"""

    with pytest.raises(ConfigurationError, match="retrieve_limit"):
        LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path="models/llmlingua-2-bert-base-multilingual-cased-meetingbank",
            retrieve_limit=0,
            max_workers=1,
            profile_name="bad",
        )


def test_lightmem_source_identity_covers_official_core_files():
    """source identity 必须覆盖 LightMem 官方核心包和实验入口。"""

    identity = build_lightmem_source_identity(load_path_settings())

    assert identity["source_sha256"]
    assert "src/lightmem/memory/lightmem.py" in identity["files"]
    assert "experiments/locomo/add_locomo.py" in identity["files"]
    assert "experiments/locomo/search_locomo.py" in identity["files"]


def test_lightmem_can_import_official_lightmemory_class():
    """adapter 应能从 vendored LightMem 源码导入官方 LightMemory 类。"""

    classes = import_lightmem_classes(load_path_settings())

    assert classes["LightMemory"].__name__ == "LightMemory"
```

- [x] **Step 2: 运行 RED**

Run:

```bash
uv run pytest tests/test_lightmem_adapter.py -q
```

Expected: collection failure，原因是 `lightmem_adapter` 不存在。

- [x] **Step 3: 添加 LightMem TOML profile**

创建 `configs/methods/lightmem.toml`：

```toml
# LightMem 官方 conversation-QA profile。
# smoke 使用较小 retrieve_limit；official_full 保留 LightMem LoCoMo 脚本的核心模型路径和参数。

[smoke]
llm_model = "gpt-4o-mini"
embedding_model_path = "models/all-MiniLM-L6-v2"
llmlingua_model_path = "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
retrieve_limit = 5
max_workers = 1
pre_compress = true
topic_segment = true
text_summary = true
suppress_official_stdout = true

[official_full]
llm_model = "gpt-4o-mini"
embedding_model_path = "models/all-MiniLM-L6-v2"
llmlingua_model_path = "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
retrieve_limit = 10
max_workers = 1
pre_compress = true
topic_segment = true
text_summary = true
suppress_official_stdout = true
```

- [x] **Step 4: 实现 LightMemConfig、import 和 source identity**

创建 `src/memory_benchmark/methods/lightmem_adapter.py`，采用与 A-Mem 相同结构：

```python
"""LightMem 的 conversation-QA 适配器。

本模块包装 `third_party/methods/LightMem/` 中的官方 LightMemory。Adapter 负责配置、
conversation 隔离、状态路径和统一接口；不重写 LightMem 的核心记忆算法。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import contextlib
import hashlib
import importlib
from pathlib import Path
import sys
from typing import Any

from memory_benchmark.config.settings import PathSettings, load_path_settings
from memory_benchmark.core import ConfigurationError


LIGHTMEM_METHOD_DIRECTORY = "LightMem"
LIGHTMEM_ADAPTER_VERSION = "conversation-qa-v1"
LIGHTMEM_READER_PROMPT_VERSION = "lightmem-reader-v1"


@dataclass(frozen=True)
class LightMemConfig:
    """LightMem 运行 profile。"""

    llm_model: str
    embedding_model_path: str
    llmlingua_model_path: str
    retrieve_limit: int
    max_workers: int
    pre_compress: bool = True
    topic_segment: bool = True
    text_summary: bool = True
    suppress_official_stdout: bool = True
    profile_name: str = "custom"

    def __post_init__(self) -> None:
        """强校验会影响实验语义的配置。"""

        if not self.llm_model.strip():
            raise ConfigurationError("LightMem llm_model is required")
        if not self.embedding_model_path.strip():
            raise ConfigurationError("LightMem embedding_model_path is required")
        if not self.llmlingua_model_path.strip():
            raise ConfigurationError("LightMem llmlingua_model_path is required")
        if self.retrieve_limit < 1:
            raise ConfigurationError("LightMem retrieve_limit must be positive")
        if self.max_workers < 1:
            raise ConfigurationError("LightMem max_workers must be positive")

    def to_manifest(self) -> dict[str, Any]:
        """返回不含 secret 和绝对存储路径的公开配置。"""

        return {
            **asdict(self),
            "adapter_version": LIGHTMEM_ADAPTER_VERSION,
            "reader_prompt_version": LIGHTMEM_READER_PROMPT_VERSION,
            "llm_provider": "openai-compatible",
            "embedding_provider": "huggingface-local",
        }


def import_lightmem_classes(path_settings: PathSettings | None = None) -> dict[str, Any]:
    """从 vendored LightMem 源码导入官方 LightMemory 类。"""

    settings = path_settings or load_path_settings()
    lightmem_root = settings.resolve_third_party_method_path(LIGHTMEM_METHOD_DIRECTORY)
    src_root = lightmem_root / "src"
    if not (src_root / "lightmem" / "memory" / "lightmem.py").is_file():
        raise ConfigurationError(f"LightMem source package missing: {src_root}")

    root_text = str(src_root)
    inserted = False
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
        inserted = True
    try:
        module = importlib.import_module("lightmem.memory.lightmem")
        return {"LightMemory": module.LightMemory}
    finally:
        if inserted:
            with contextlib.suppress(ValueError):
                sys.path.remove(root_text)


def build_lightmem_source_identity(
    path_settings: PathSettings | None = None,
) -> dict[str, Any]:
    """计算 vendored LightMem 关键源码的确定性身份。"""

    settings = path_settings or load_path_settings()
    lightmem_root = settings.resolve_third_party_method_path(LIGHTMEM_METHOD_DIRECTORY)
    required_files = [
        "README.md",
        "pyproject.toml",
        "src/lightmem/memory/lightmem.py",
        "experiments/locomo/add_locomo.py",
        "experiments/locomo/search_locomo.py",
    ]
    source_files = [lightmem_root / relative_path for relative_path in required_files]
    missing = [path for path in source_files if not path.is_file()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise ConfigurationError(f"LightMem source files missing: {missing_text}")

    digest = hashlib.sha256()
    relative_paths: list[str] = []
    for source_file in source_files:
        relative_path = source_file.relative_to(lightmem_root).as_posix()
        relative_paths.append(relative_path)
        path_bytes = relative_path.encode("utf-8")
        content = source_file.read_bytes()
        digest.update(len(path_bytes).to_bytes(8, byteorder="big"))
        digest.update(path_bytes)
        digest.update(len(content).to_bytes(8, byteorder="big"))
        digest.update(content)

    return {
        "source_sha256": digest.hexdigest(),
        "file_count": len(relative_paths),
        "files": relative_paths,
    }
```

- [x] **Step 5: 运行 GREEN**

Run:

```bash
uv run pytest tests/test_lightmem_adapter.py -q
```

Expected: config/source identity/import tests pass。若 import 因缺第三方依赖失败，先记录缺失依赖并通过 `uv add` 安装运行 LightMem 所必需的公共依赖；不得通过跳过测试掩盖问题。

## Task 8：LightMem wrapper 与 fake/offline 闭环

**Files:**
- Modify: `src/memory_benchmark/methods/lightmem_adapter.py`
- Modify: `tests/test_lightmem_adapter.py`

- [x] **Step 1: 写 fake LightMemory 测试**

追加：

```python
from memory_benchmark.core import AnswerResult, Conversation, Question, Session, Turn
from memory_benchmark.methods.lightmem_adapter import LightMem


class FakeLightMemory:
    """模拟官方 LightMemory 的 add_memory/retrieve 方法。"""

    def __init__(self):
        self.added_messages = []
        self.queries = []

    def add_memory(self, messages, **kwargs):
        self.added_messages.append({"messages": messages, "kwargs": kwargs})
        return {"api_call_nums": 0}

    def retrieve(self, query, limit=10, filters=None):
        self.queries.append({"query": query, "limit": limit, "filters": filters})
        return ["2026-01-01 Alice likes tea"]


class FakeChatClient:
    """模拟回答 LLM。"""

    def __init__(self):
        self.messages = []

    def create_answer(self, prompt):
        self.messages.append(prompt)
        return "fake lightmem answer"


def _lightmem_conversation() -> Conversation:
    question = Question(
        question_id="q-1",
        conversation_id="conv-1",
        text="What does Alice like?",
    )
    return Conversation(
        conversation_id="conv-1",
        sessions=[
            Session(
                session_id="s-1",
                session_time="2026-01-01",
                turns=[
                    Turn(turn_id="t-1", speaker="Alice", content="I like tea."),
                    Turn(turn_id="t-2", speaker="Bob", content="I will remember that."),
                ],
            )
        ],
        questions=[question],
    )


def test_lightmem_add_and_get_answer_with_fake_backend():
    """LightMem wrapper 应能通过统一接口写入 conversation 并回答问题。"""

    backend = FakeLightMemory()
    chat = FakeChatClient()
    method = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path="models/llmlingua-2-bert-base-multilingual-cased-meetingbank",
            retrieve_limit=2,
            max_workers=1,
            profile_name="smoke",
        ),
        backend_factory=lambda conversation_id: backend,
        answer_client=chat,
    )
    conversation = _lightmem_conversation()

    add_result = method.add([conversation])
    answer = method.get_answer(conversation.questions[0])

    assert add_result.conversation_ids == ["conv-1"]
    assert isinstance(answer, AnswerResult)
    assert answer.answer == "fake lightmem answer"
    assert backend.queries == [{"query": "What does Alice like?", "limit": 2, "filters": None}]
    assert "Alice likes tea" in chat.messages[0]
```

- [x] **Step 2: 运行 RED**

Run:

```bash
uv run pytest tests/test_lightmem_adapter.py::test_lightmem_add_and_get_answer_with_fake_backend -q
```

Expected: fail，原因是 `LightMem` 未实现。

- [x] **Step 3: 实现 LightMem wrapper**

在 `lightmem_adapter.py` 增加 `LightMem(BaseMemorySystem)`，结构与 A-Mem 相同：

- `_get_or_create_backend(conversation_id)`
- `add(conversations)`
- `get_answer(question)`
- `_conversation_to_lightmem_messages(conversation)`
- `_build_answer_prompt(question, memory_context)`

`_conversation_to_lightmem_messages()` 输出 list[dict]，字段包含：

```python
{
    "role": "user",
    "content": turn.content,
    "speaker_id": turn.speaker,
    "speaker_name": turn.speaker,
    "timestamp": turn.turn_time or session.session_time,
}
```

`add()` 调用官方 `backend.add_memory(messages, force_segment=True, force_extract=True)`。

- [x] **Step 4: 运行 GREEN**

Run:

```bash
uv run pytest tests/test_lightmem_adapter.py -q
```

Expected: LightMem fake/offline tests pass。

## Task 9：LightMem efficiency observation

**Files:**
- Modify: `src/memory_benchmark/methods/lightmem_adapter.py`
- Modify: `tests/test_lightmem_adapter.py`

- [x] **Step 1: 写 LightMem observation 失败测试**

追加：

```python
from memory_benchmark.observability.efficiency import EfficiencyCollector


def test_lightmem_records_question_efficiency_observations():
    """LightMem wrapper 应记录 retrieval/context/answer 的 question-level observation。"""

    backend = FakeLightMemory()
    chat = FakeChatClient()
    collector = EfficiencyCollector(enabled=True)
    method = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path="models/llmlingua-2-bert-base-multilingual-cased-meetingbank",
            retrieve_limit=2,
            max_workers=1,
            profile_name="smoke",
        ),
        backend_factory=lambda conversation_id: backend,
        answer_client=chat,
        efficiency_collector=collector,
    )
    conversation = _lightmem_conversation()
    method.add([conversation])

    with collector.question_scope("conv-1", "q-1") as scope:
        method.get_answer(conversation.questions[0])
        bundle = scope.finalize()

    assert bundle.question_observation.retrieval_latency_ms is not None
    assert bundle.question_observation.injected_memory_context_tokens > 0
    assert bundle.question_observation.answer_generation_latency_ms is not None
```

- [x] **Step 2: 运行 RED**

Run:

```bash
uv run pytest tests/test_lightmem_adapter.py::test_lightmem_records_question_efficiency_observations -q
```

Expected: fail，原因是 wrapper 尚未记录 question observation。

- [x] **Step 3: 实现 wrapper 观测**

在 `get_answer()` 中包住：

- `backend.retrieve()` 的 latency。
- `"\n".join(retrieved_memories)` 的 injected memory context tokens。
- answer client 的 generation latency。

token 计数复用现有 efficiency token counting 工具；fake backend 不伪造 LLM usage。

- [x] **Step 4: 运行 GREEN**

Run:

```bash
uv run pytest tests/test_lightmem_adapter.py -q
```

Expected: LightMem tests pass。

## Task 10：LightMem registry 接入

**Files:**
- Modify: `src/memory_benchmark/methods/registry.py`
- Modify: `src/memory_benchmark/methods/__init__.py`
- Modify: `tests/test_amem_lightmem_registry.py`

- [x] **Step 1: 写 LightMem registry 失败测试**

追加：

```python
def test_lightmem_is_registered_for_conversation_qa():
    """LightMem 应作为 conversation-QA 官方 method 注册。"""

    registration = get_method_registration("lightmem")

    assert registration.name == "lightmem"
    assert registration.display_name == "LightMem"
    assert "smoke" in registration.profile_names
    assert "official_full" in registration.profile_names
    assert registration.requires_api is True
```

- [x] **Step 2: 运行 RED**

Run:

```bash
uv run pytest tests/test_amem_lightmem_registry.py::test_lightmem_is_registered_for_conversation_qa -q
```

Expected: fail，原因是 registry 未注册 `lightmem`。

- [x] **Step 3: 注册 LightMem**

在 `registry.py` 导入 LightMem 类型和 identity 函数，添加 `_build_lightmem_system()`，
profile path 指向 `configs/methods/lightmem.toml`。model inventory 至少包含：

```python
ModelDescriptor(model_id="lightmem-memory-llm", model_name=config.llm_model, model_role="memory_llm", execution_mode="api", tokenizer_name=config.llm_model)
ModelDescriptor(model_id="lightmem-answer-llm", model_name=config.llm_model, model_role="answer_llm", execution_mode="api", tokenizer_name=config.llm_model)
ModelDescriptor(model_id="lightmem-embedding", model_name=config.embedding_model_path, model_role="embedding", execution_mode="local", tokenizer_name=config.embedding_model_path)
```

- [x] **Step 4: 运行 registry GREEN**

Run:

```bash
uv run pytest tests/test_amem_lightmem_registry.py -q
```

Expected: A-Mem 与 LightMem registry tests pass。

## Task 11：focused 回归与文档更新

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/current-roadmap.md`
- Create/Modify: `docs/handoffs/2026-06-16-amem-lightmem-adapters.md`

- [x] **Step 1: 运行 focused tests**

Run:

```bash
uv run pytest tests/test_amem_adapter.py tests/test_lightmem_adapter.py tests/test_amem_lightmem_registry.py -q
uv run pytest tests/test_documentation_standards.py -q
uv run python -m compileall -q src/memory_benchmark tests
```

Expected:

- adapter/registry tests pass。
- documentation standards pass。
- compileall exit 0。

- [x] **Step 2: 更新 roadmap 勾选状态**

在 `docs/current-roadmap.md` 中把已完成项勾选：

```text
- [x] 编写实施计划。
- [x] 接入 A-Mem config、adapter、registry、source identity。
- [x] A-Mem 接入现有 efficiency observation。
- [x] A-Mem 通过 adapter contract、fake/offline 和 registered runner smoke。
- [x] 接入 LightMem config、adapter、registry、source identity。
- [x] LightMem 接入可精确观测的 efficiency observation。
- [x] LightMem 通过 adapter contract、fake/offline 和 registered runner smoke。
```

如果某项只完成到部分状态，只勾选真实完成的项，并把未完成原因写入 handoff。

- [x] **Step 3: 更新 AGENTS 当前断点**

在 `AGENTS.md` 当前断点中记录：

```text
- A-Mem 与 LightMem adapter 接入已完成 focused offline 验证；未执行真实 API。
```

若 LightMem 依赖或官方 API 导入失败，则记录具体阻塞条件和下一步，不写成已完成。

- [x] **Step 4: 写 handoff**

创建或更新 `docs/handoffs/2026-06-16-amem-lightmem-adapters.md`，记录：

- 完成任务。
- 修改文件。
- 验证命令和结果。
- 是否触网。
- 是否修改第三方源码。
- 后续真实 API smoke 前置条件。

## Plan 自检

- Spec 覆盖：本计划覆盖 A-Mem/LightMem wrapper、配置、registry、source identity、efficiency observation、离线测试和文档更新。
- 私有边界：A-Mem 明确不使用官方传 gold answer 的 `answer_question()` 入口。
- 并行：本计划不实现通用并行调度，符合用户最新要求。
- 付费 API：本计划只要求离线/fake 测试，不启动 full run。
- 占位扫描：未保留 TBD/TODO。
- Git 状态：当前已经初始化为 Git 仓库，但尚未做 initial commit；本计划仍不包含
  commit 步骤，交付以验证与 handoff 为准。
