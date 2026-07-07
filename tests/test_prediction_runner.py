"""测试通用 conversation-QA prediction runner。

本模块只使用无网络 fake method，验证 prediction runner 的公开/私有数据隔离、
标准 artifact、conversation 级并发和断点续跑。metric 不属于本 runner 的职责。
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from memory_benchmark.core import (
    AddResult,
    AnswerResult,
    ConfigurationError,
    Conversation,
    Dataset,
    DatasetValidationError,
    GoldAnswerInfo,
    PromptMessage,
    Question,
    AnswerPromptResult,
    Session,
    Turn,
)
from memory_benchmark.benchmark_adapters.contracts import RunScope
from memory_benchmark.benchmark_adapters.membench import (
    build_membench_unified_answer_prompt,
    normalize_membench_choice_prediction,
)
from memory_benchmark.core.interfaces import (
    BaseMemoryProvider,
    BaseMemorySystem,
    BaseResumableMemorySystem,
)
from memory_benchmark.core.provider_protocol import (
    BRIDGE_EMPTY_MEMORY_SENTINEL,
    IngestResult,
    MemoryProvider,
    RetrievedItem,
    RetrievalQuery,
    RetrievalResult,
    SessionMemoryReport,
    SessionRef,
    TurnEvent,
    UnitRef,
)
from memory_benchmark.observability import RunContext
from memory_benchmark.readers.answer import FakeAnswerLLMClient, FrameworkAnswerReader
from memory_benchmark.methods.mock import MockMemoryProvider
from memory_benchmark.runners.ingest_resume import TurnIngestCheckpointStore
from memory_benchmark.runners.prediction import (
    PredictionRunPolicy,
    run_predictions,
)
from memory_benchmark.storage import atomic_write_json, atomic_write_jsonl, read_jsonl


pytestmark = pytest.mark.integration

EMPTY_SOURCE_FINGERPRINT_SHA256 = hashlib.sha256(b"[]").hexdigest()


def _build_dataset() -> Dataset:
    """构造两个互相隔离、各含一道问题的最小数据集。"""

    conversations: list[Conversation] = []
    for index in (1, 2):
        conversation_id = f"conv-{index}"
        question_id = f"{conversation_id}:q1"
        conversations.append(
            Conversation(
                conversation_id=conversation_id,
                sessions=[
                    Session(
                        session_id=f"{conversation_id}:s1",
                        turns=[
                            Turn(
                                turn_id=f"{conversation_id}:t1",
                                speaker=f"Speaker-{index}",
                                content=f"公开记忆 {index}",
                            )
                        ],
                    )
                ],
                questions=[
                    Question(
                        question_id=question_id,
                        conversation_id=conversation_id,
                        text=f"问题 {index}",
                    )
                ],
                gold_answers={
                    question_id: GoldAnswerInfo(
                        question_id=question_id,
                        answer=f"标准答案 {index}",
                        evidence=[f"{conversation_id}:t1"],
                    )
                },
            )
        )
    return Dataset(dataset_name="fake-conversation-qa", conversations=conversations)


def _build_numbered_dataset(conversation_count: int) -> Dataset:
    """构造指定数量 conversation 的一问一答数据集。"""

    conversations: list[Conversation] = []
    for index in range(1, conversation_count + 1):
        conversation_id = f"conv-{index}"
        question_id = f"{conversation_id}:q1"
        conversations.append(
            Conversation(
                conversation_id=conversation_id,
                sessions=[
                    Session(
                        session_id=f"{conversation_id}:s1",
                        turns=[
                            Turn(
                                turn_id=f"{conversation_id}:t1",
                                speaker=f"Speaker-{index}",
                                content=f"公开记忆 {index}",
                            )
                        ],
                    )
                ],
                questions=[
                    Question(
                        question_id=question_id,
                        conversation_id=conversation_id,
                        text=f"问题 {index}",
                    )
                ],
                gold_answers={
                    question_id: GoldAnswerInfo(
                        question_id=question_id,
                        answer=f"标准答案 {index}",
                    )
                },
            )
        )
    return Dataset(dataset_name="fake-conversation-qa", conversations=conversations)


def _build_two_question_dataset() -> Dataset:
    """构造一个 conversation 两个 question 的数据集，用于 question-level resume。"""

    conversation_id = "conv-1"
    question_ids = [f"{conversation_id}:q{index}" for index in (1, 2)]
    return Dataset(
        dataset_name="fake-conversation-qa",
        conversations=[
            Conversation(
                conversation_id=conversation_id,
                sessions=[
                    Session(
                        session_id=f"{conversation_id}:s1",
                        turns=[
                            Turn(
                                turn_id=f"{conversation_id}:t1",
                                speaker="Speaker-1",
                                content="公开记忆",
                            )
                        ],
                    )
                ],
                questions=[
                    Question(
                        question_id=question_ids[0],
                        conversation_id=conversation_id,
                        text="问题 1",
                    ),
                    Question(
                        question_id=question_ids[1],
                        conversation_id=conversation_id,
                        text="问题 2",
                    ),
                ],
                gold_answers={
                    question_id: GoldAnswerInfo(
                        question_id=question_id,
                        answer=f"标准答案 {question_id}",
                    )
                    for question_id in question_ids
                },
            )
        ],
    )


class RecordingPredictionSystem(BaseMemorySystem):
    """记录调用并检测 conversation worker 是否真正发生重叠。"""

    def __init__(self, delay_seconds: float = 0.0):
        """初始化线程安全调用记录。

        输入:
            delay_seconds: add 阶段主动等待时间，用于稳定观察并发重叠。
        """

        self.delay_seconds = delay_seconds
        self.added_payloads: list[Conversation] = []
        self.answered_questions: list[Question] = []
        self._lock = threading.Lock()
        self._active_adds = 0
        self.max_active_adds = 0

    def add(self, conversations: list[Conversation]) -> AddResult:
        """记录公开 conversation，并返回其 id。"""

        with self._lock:
            self._active_adds += 1
            self.max_active_adds = max(self.max_active_adds, self._active_adds)
            self.added_payloads.extend(conversations)
        try:
            if self.delay_seconds:
                time.sleep(self.delay_seconds)
        finally:
            with self._lock:
                self._active_adds -= 1
        return AddResult(
            conversation_ids=[conversation.conversation_id for conversation in conversations]
        )

    def get_answer(self, question: Question) -> AnswerResult:
        """记录公开问题，并返回可预测的非空回复。"""

        with self._lock:
            self.answered_questions.append(question)
        return AnswerResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer=f"预测:{question.text}",
            metadata={"method": "recording"},
        )


class RecordingMemoryProvider(BaseMemoryProvider):
    """记录 add/retrieve 调用的 retrieve-first fake provider。"""

    def __init__(self) -> None:
        """初始化线程安全调用记录。"""

        self.added_conversation_ids: list[str] = []
        self.retrieved_question_ids: list[str] = []
        self._lock = threading.Lock()

    def add(self, conversation: Conversation) -> AddResult:
        """记录单个公开 conversation 写入。"""

        with self._lock:
            self.added_conversation_ids.append(conversation.conversation_id)
        return AddResult(conversation_ids=[conversation.conversation_id])

    def retrieve(self, question: Question) -> AnswerPromptResult:
        """记录公开问题检索，并返回可注入 prompt 的上下文。"""

        with self._lock:
            self.retrieved_question_ids.append(question.question_id)
        return AnswerPromptResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer_prompt=f"memory for {question.text}",
            metadata={"provider": "recording"},
        )


class RecordingV3TurnProvider(MemoryProvider):
    """记录 v3 turn 粒度 ingest/retrieve 调用的 fake provider。"""

    consume_granularity = "turn"
    session_memory_report = True
    provenance_granularity = "turn"

    def __init__(
        self,
        *,
        shared_events: list[tuple[str, str]] | None = None,
        report_sessions: bool = True,
    ) -> None:
        """初始化调用记录和 session report 开关。"""

        self.shared_events = shared_events if shared_events is not None else []
        self.report_sessions = report_sessions
        self.ingested_turn_ids: list[str] = []
        self.ended_sessions: list[SessionRef] = []
        self.ended_conversations: list[UnitRef] = []
        self.retrieval_queries: list[RetrievalQuery] = []

    def ingest(self, unit) -> IngestResult:
        """记录 turn 粒度 ingest 单元。"""

        if not isinstance(unit, TurnEvent):
            raise AssertionError(f"expected TurnEvent, got {type(unit).__name__}")
        self.ingested_turn_ids.append(unit.turn_id)
        self.shared_events.append(("ingest", unit.turn_id))
        return IngestResult()

    def end_session(self, ref: SessionRef) -> SessionMemoryReport | None:
        """记录 session 边界并按需返回 session memory report。"""

        self.ended_sessions.append(ref)
        self.shared_events.append(("end_session", ref.session_id or ""))
        if not self.report_sessions:
            return None
        return SessionMemoryReport(
            session_ref=ref,
            memories=[f"session-memory:{ref.session_id}"],
            metadata={"provider": "recording-v3"},
        )

    def end_conversation(self, ref: UnitRef) -> None:
        """记录 conversation 边界。"""

        self.ended_conversations.append(ref)
        self.shared_events.append(("end_conversation", ref.isolation_key))

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """返回包含 formatted_memory、items 和 native prompt messages 的 v3 结果。"""

        self.retrieval_queries.append(query)
        return RetrievalResult(
            formatted_memory=f"v3 memory for {query.query_text}",
            prompt_messages=(
                PromptMessage(role="user", content=f"native prompt {query.query_text}"),
            ),
            items=(
                RetrievedItem(
                    item_id=f"{query.source_question.question_id}:hit",
                    content="命中记忆",
                    score=0.9,
                    timestamp=None,
                    source_turn_ids=("conv-1:t1",),
                ),
            ),
            metadata={"provider": "recording-v3"},
        )


class FailingAnswerClient(FakeAnswerLLMClient):
    """第一次调用失败，后续调用返回固定答案。"""

    def __init__(self) -> None:
        """初始化一次性失败开关。"""

        super().__init__(answer="second answer")
        self.fail_once = True

    def complete(self, *, prompt: str) -> str:
        """第一次 answer 调用抛错，模拟 retrieval 已成功但 answer 失败。"""

        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("answer failed once")
        return super().complete(prompt=prompt)

    def complete_messages_with_metadata(self, *, messages):  # type: ignore[no-untyped-def]
        """第一次 message-based answer 调用同样抛错。"""

        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("answer failed once")
        return super().complete_messages_with_metadata(messages=messages)


class ResumablePredictionSystem(BaseResumableMemorySystem):
    """可故障注入的逐 turn fake method。

    该 fake 只用于验证 runner 的 callback 边界和恢复起点，不模拟真实 Mem0 算法。
    """

    def __init__(
        self,
        *,
        fail_on_started_index: int | None = None,
        fail_after_completed_index: int | None = None,
    ):
        """配置在 turn 调用前后注入的确定性故障。"""

        self.fail_on_started_index = fail_on_started_index
        self.fail_after_completed_index = fail_after_completed_index
        self.start_indices: list[tuple[str, int]] = []
        self.processed_turn_ids: list[str] = []
        self.answered_questions: list[str] = []
        self._lock = threading.Lock()

    def add(self, conversations: list[Conversation]) -> AddResult:
        """禁止 resumable runner 退回完整 conversation 写入。"""

        raise AssertionError("resumable runner must call add_from_turn()")

    def add_from_turn(
        self,
        conversation: Conversation,
        start_turn_index: int,
        on_turn_started,
        on_turn_completed,
    ) -> AddResult:
        """从指定 index 顺序执行 turn，并在 callback 边界注入故障。"""

        turns = [
            turn
            for session in conversation.sessions
            for turn in session.turns
        ]
        with self._lock:
            self.start_indices.append(
                (conversation.conversation_id, start_turn_index)
            )
        for turn_index in range(start_turn_index, len(turns)):
            turn = turns[turn_index]
            on_turn_started(turn_index, turn)
            if turn_index == self.fail_on_started_index:
                raise RuntimeError(f"failed while turn {turn_index} was in flight")
            with self._lock:
                self.processed_turn_ids.append(turn.turn_id)
            on_turn_completed(turn_index, turn)
            if turn_index == self.fail_after_completed_index:
                raise RuntimeError(f"failed after turn {turn_index} was confirmed")
        return AddResult(conversation_ids=[conversation.conversation_id])

    def get_answer(self, question: Question) -> AnswerResult:
        """返回确定性答案，并记录是否进入 question 阶段。"""

        with self._lock:
            self.answered_questions.append(question.question_id)
        return AnswerResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer=f"预测:{question.text}",
        )


class SelectiveResumablePredictionSystem(ResumablePredictionSystem):
    """按 conversation 决定是否启用 turn-level resume 的 fake method。"""

    def __init__(self, turn_resume_conversation_ids: set[str]):
        """保存允许 turn-level resume 的 conversation id 集合。"""

        super().__init__()
        self.turn_resume_conversation_ids = turn_resume_conversation_ids
        self.added_conversation_ids: list[str] = []

    def supports_turn_resume(self, conversation: Conversation) -> bool:
        """只有白名单中的 conversation 才走 `add_from_turn()`。"""

        return conversation.conversation_id in self.turn_resume_conversation_ids

    def add(self, conversations: list[Conversation]) -> AddResult:
        """记录 conversation-level 写入，用于验证 runner fallback 路径。"""

        self.added_conversation_ids.extend(
            conversation.conversation_id for conversation in conversations
        )
        return AddResult(
            conversation_ids=[
                conversation.conversation_id for conversation in conversations
            ]
        )


def _build_three_turn_dataset() -> Dataset:
    """构造一个含 3 个 turn 的 conversation，用于精确验证恢复 index。"""

    question_id = "conv-1:q1"
    return Dataset(
        dataset_name="fake-conversation-qa",
        conversations=[
            Conversation(
                conversation_id="conv-1",
                sessions=[
                    Session(
                        session_id="conv-1:s1",
                        turns=[
                            Turn("conv-1:t1", "Alice", "第一条公开记忆"),
                            Turn("conv-1:t2", "Bob", "第二条公开记忆"),
                            Turn("conv-1:t3", "Alice", "第三条公开记忆"),
                        ],
                    )
                ],
                questions=[
                    Question(
                        question_id=question_id,
                        conversation_id="conv-1",
                        text="测试问题",
                    )
                ],
                gold_answers={
                    question_id: GoldAnswerInfo(
                        question_id=question_id,
                        answer="标准答案",
                    )
                },
            )
        ],
    )


def _create_context(tmp_path: Path, *, resume: bool = False) -> RunContext:
    """创建测试用标准运行目录。"""

    return RunContext.create(
        run_id="prediction-run",
        benchmark_name="fake-conversation-qa",
        method_name="recording",
        model_name="fake-reader",
        output_root=tmp_path,
        resume=resume,
    )


def _create_provisional_context(
    tmp_path: Path,
    *,
    resume: bool = False,
) -> RunContext:
    """创建不触发目录副作用的测试上下文。"""

    return RunContext.create(
        run_id="prediction-run",
        benchmark_name="fake-conversation-qa",
        method_name="recording",
        model_name="fake-reader",
        output_root=tmp_path,
        resume=resume,
        ensure_directories=False,
    )


def _make_build_context(tmp_path: Path):
    """创建 isolated worker 测试用 build context。"""

    from memory_benchmark.methods.registry import MethodBuildContext

    return MethodBuildContext(
        config={},
        openai_settings=None,
        path_settings=None,
        storage_root=tmp_path / "prediction-run" / "method_state",
    )


def _write_resume_manifest(
    *,
    dataset: Dataset,
    run_context: RunContext,
    policy: PredictionRunPolicy,
    method_manifest: dict[str, object],
    benchmark_variant: str = "default",
    run_scope: RunScope = RunScope.FULL,
) -> None:
    """为手工 checkpoint 测试写入与 runner 一致的 manifest。

    输入:
        dataset: 当前测试使用的统一数据集。
        run_context: resume 目标 run。
        policy: 当前测试的 runner policy。
        method_manifest: 公开 method 身份。
        benchmark_variant: concrete benchmark variant。
        run_scope: smoke/full scope。

    输出:
        None。函数只写 `manifest.json`，其余 checkpoint 由测试单独构造。
    """

    from memory_benchmark.runners import prediction as prediction_module

    _, manifest = prediction_module._build_prediction_resume_artifacts(
        dataset=dataset,
        run_context=run_context,
        policy=policy,
        method_manifest=method_manifest,
        benchmark_variant=benchmark_variant,
        run_scope=run_scope,
        source_paths=(),
    )
    run_context.run_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(run_context.run_dir / "manifest.json", manifest)


def test_preflight_prediction_run_accepts_matching_resume_without_writes(
    tmp_path: Path,
) -> None:
    """只读 preflight 在 manifest 一致时应通过且不创建任何新文件。"""

    from memory_benchmark.runners import prediction as prediction_module

    run_context = RunContext.create(
        run_id="prediction-run",
        benchmark_name="fake-conversation-qa",
        method_name="recording",
        model_name="fake-reader",
        output_root=tmp_path,
        resume=True,
        ensure_directories=False,
    )
    dataset = _build_two_question_dataset()
    policy = PredictionRunPolicy(max_workers=1, resume=True)
    dataset_fingerprint, manifest = prediction_module._build_prediction_resume_artifacts(
        dataset=dataset,
        run_context=run_context,
        policy=policy,
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
        source_paths=(),
    )
    run_context.run_dir.mkdir(parents=True)
    atomic_write_json(run_context.run_dir / "manifest.json", manifest)

    prediction_module._preflight_prediction_run(
        run_context=run_context,
        policy=policy,
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
        dataset=dataset,
        source_paths=(),
    )

    assert dataset_fingerprint["dataset_name"] == "fake-conversation-qa"
    assert sorted(path.name for path in run_context.run_dir.iterdir()) == ["manifest.json"]
    assert manifest["schema_version"] == 2
    assert manifest["benchmark_variant"] == "test_variant"
    assert manifest["run_scope"] == "full"


def test_preflight_prediction_run_rejects_changed_source_file_on_resume(
    tmp_path: Path,
) -> None:
    """源文件内容变化时，即使规范化 Dataset 未变也必须拒绝 resume。"""

    from memory_benchmark.runners import prediction as prediction_module

    source_path = tmp_path / "source.json"
    source_path.write_text('{"version": 1}', encoding="utf-8")
    run_context = RunContext.create(
        run_id="prediction-run",
        benchmark_name="fake-conversation-qa",
        method_name="recording",
        model_name="fake-reader",
        output_root=tmp_path,
        resume=True,
        ensure_directories=False,
    )
    dataset = _build_two_question_dataset()
    policy = PredictionRunPolicy(max_workers=1, resume=True)
    _, manifest = prediction_module._build_prediction_resume_artifacts(
        dataset=dataset,
        run_context=run_context,
        policy=policy,
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
        source_paths=(source_path,),
    )
    run_context.run_dir.mkdir(parents=True)
    atomic_write_json(run_context.run_dir / "manifest.json", manifest)
    source_path.write_text('{"version": 2}', encoding="utf-8")

    with pytest.raises(ConfigurationError, match="source"):
        prediction_module._preflight_prediction_run(
            run_context=run_context,
            policy=policy,
            method_manifest={"adapter": "recording-v1"},
            benchmark_variant="test_variant",
            run_scope=RunScope.FULL,
            dataset=dataset,
            source_paths=(source_path,),
        )


def test_preflight_prediction_run_rejects_blank_benchmark_variant(
    tmp_path: Path,
) -> None:
    """空白 concrete benchmark variant 必须在写入前被拒绝。"""

    from memory_benchmark.runners import prediction as prediction_module

    with pytest.raises(ConfigurationError, match="benchmark_variant"):
        prediction_module._preflight_prediction_run(
            run_context=_create_provisional_context(tmp_path),
            policy=PredictionRunPolicy(max_workers=1),
            method_manifest={"adapter": "recording-v1"},
            benchmark_variant="  ",
            run_scope=RunScope.FULL,
            dataset=_build_dataset(),
            source_paths=(),
        )


def test_preflight_prediction_run_rejects_all_variant_selector(
    tmp_path: Path,
) -> None:
    """命令层 selector `all` 不能进入底层 generic prediction runner。"""

    from memory_benchmark.runners import prediction as prediction_module

    with pytest.raises(ConfigurationError, match="benchmark_variant"):
        prediction_module._preflight_prediction_run(
            run_context=_create_provisional_context(tmp_path),
            policy=PredictionRunPolicy(max_workers=1),
            method_manifest={"adapter": "recording-v1"},
            benchmark_variant="all",
            run_scope=RunScope.FULL,
            dataset=_build_dataset(),
            source_paths=(),
        )


def test_preflight_prediction_run_rejects_non_run_scope_value(
    tmp_path: Path,
) -> None:
    """run_scope 必须是强类型 RunScope，不能接受裸字符串。"""

    from memory_benchmark.runners import prediction as prediction_module

    with pytest.raises(ConfigurationError, match="run_scope"):
        prediction_module._preflight_prediction_run(
            run_context=_create_provisional_context(tmp_path),
            policy=PredictionRunPolicy(max_workers=1),
            method_manifest={"adapter": "recording-v1"},
            benchmark_variant="test_variant",
            run_scope="full",
            dataset=_build_dataset(),
            source_paths=(),
        )


def test_preflight_prediction_run_rejects_mismatch_without_writes(
    tmp_path: Path,
) -> None:
    """只读 preflight 发现 manifest 不一致时应报错且不写任何文件。"""

    from memory_benchmark.runners import prediction as prediction_module

    run_context = RunContext.create(
        run_id="prediction-run",
        benchmark_name="fake-conversation-qa",
        method_name="recording",
        model_name="fake-reader",
        output_root=tmp_path,
        resume=True,
        ensure_directories=False,
    )
    run_context.run_dir.mkdir(parents=True)
    atomic_write_json(
        run_context.run_dir / "manifest.json",
        {
            "schema_version": 2,
            "runner": "generic_conversation_qa_prediction",
            "run_id": "prediction-run",
            "benchmark_name": "fake-conversation-qa",
            "method_name": "recording",
            "model_name": "fake-reader",
            "dataset_sha256": "different",
            "source_fingerprint_sha256": EMPTY_SOURCE_FINGERPRINT_SHA256,
            "benchmark_variant": "test_variant",
            "run_scope": "full",
            "policy": {
                "max_workers": 1,
                "conversation_ids": None,
                "question_limit_per_conversation": None,
            },
            "method": {"adapter": "recording-v0"},
        },
    )

    with pytest.raises(ConfigurationError, match="Resume manifest mismatch"):
        prediction_module._preflight_prediction_run(
            run_context=run_context,
            policy=PredictionRunPolicy(max_workers=1, resume=True),
            method_manifest={"adapter": "recording-v1"},
            benchmark_variant="test_variant",
            run_scope=RunScope.FULL,
            dataset=_build_dataset(),
            source_paths=(),
        )

    assert sorted(path.name for path in run_context.run_dir.iterdir()) == ["manifest.json"]


def test_preflight_prediction_run_rejects_variant_change_on_resume(
    tmp_path: Path,
) -> None:
    """resume 时 concrete variant 变化必须直接拒绝。"""

    from memory_benchmark.runners import prediction as prediction_module

    run_context = RunContext.create(
        run_id="prediction-run",
        benchmark_name="fake-conversation-qa",
        method_name="recording",
        model_name="fake-reader",
        output_root=tmp_path,
        resume=True,
        ensure_directories=False,
    )
    run_context.run_dir.mkdir(parents=True)
    atomic_write_json(
        run_context.run_dir / "manifest.json",
        {
            "schema_version": 2,
            "runner": "generic_conversation_qa_prediction",
            "run_id": "prediction-run",
            "benchmark_name": "fake-conversation-qa",
            "method_name": "recording",
            "model_name": "fake-reader",
            "dataset_sha256": "same-for-test",
            "source_fingerprint_sha256": EMPTY_SOURCE_FINGERPRINT_SHA256,
            "benchmark_variant": "other_variant",
            "run_scope": "full",
            "policy": {
                "max_workers": 1,
                "conversation_ids": None,
                "question_limit_per_conversation": None,
            },
            "method": {"adapter": "recording-v1"},
        },
    )

    with pytest.raises(ConfigurationError, match="Resume manifest mismatch"):
        prediction_module._preflight_prediction_run(
            run_context=run_context,
            policy=PredictionRunPolicy(max_workers=1, resume=True),
            method_manifest={"adapter": "recording-v1"},
            benchmark_variant="test_variant",
            run_scope=RunScope.FULL,
            dataset=_build_dataset(),
            source_paths=(),
        )


def test_preflight_prediction_run_rejects_run_scope_change_on_resume(
    tmp_path: Path,
) -> None:
    """resume 时 run scope 变化必须直接拒绝。"""

    from memory_benchmark.runners import prediction as prediction_module

    run_context = RunContext.create(
        run_id="prediction-run",
        benchmark_name="fake-conversation-qa",
        method_name="recording",
        model_name="fake-reader",
        output_root=tmp_path,
        resume=True,
        ensure_directories=False,
    )
    run_context.run_dir.mkdir(parents=True)
    atomic_write_json(
        run_context.run_dir / "manifest.json",
        {
            "schema_version": 2,
            "runner": "generic_conversation_qa_prediction",
            "run_id": "prediction-run",
            "benchmark_name": "fake-conversation-qa",
            "method_name": "recording",
            "model_name": "fake-reader",
            "dataset_sha256": "same-for-test",
            "source_fingerprint_sha256": EMPTY_SOURCE_FINGERPRINT_SHA256,
            "benchmark_variant": "test_variant",
            "run_scope": "smoke",
            "policy": {
                "max_workers": 1,
                "conversation_ids": None,
                "question_limit_per_conversation": None,
            },
            "method": {"adapter": "recording-v1"},
        },
    )

    with pytest.raises(ConfigurationError, match="Resume manifest mismatch"):
        prediction_module._preflight_prediction_run(
            run_context=run_context,
            policy=PredictionRunPolicy(max_workers=1, resume=True),
            method_manifest={"adapter": "recording-v1"},
            benchmark_variant="test_variant",
            run_scope=RunScope.FULL,
            dataset=_build_dataset(),
            source_paths=(),
        )


def test_preflight_prediction_run_rejects_schema_v1_resume(
    tmp_path: Path,
) -> None:
    """schema v1 generic artifacts 只允许离线 evaluate，不允许经 v2 runner resume。"""

    from memory_benchmark.runners import prediction as prediction_module

    run_context = RunContext.create(
        run_id="prediction-run",
        benchmark_name="fake-conversation-qa",
        method_name="recording",
        model_name="fake-reader",
        output_root=tmp_path,
        resume=True,
        ensure_directories=False,
    )
    run_context.run_dir.mkdir(parents=True)
    atomic_write_json(
        run_context.run_dir / "manifest.json",
        {
            "schema_version": 1,
            "runner": "generic_conversation_qa_prediction",
            "run_id": "prediction-run",
            "benchmark_name": "fake-conversation-qa",
            "method_name": "recording",
            "model_name": "fake-reader",
            "dataset_sha256": "legacy-sha",
            "policy": {
                "max_workers": 1,
                "conversation_ids": None,
                "question_limit_per_conversation": None,
            },
            "method": {"adapter": "recording-v1"},
        },
    )

    with pytest.raises(
        ConfigurationError,
        match="schema v1 artifacts remain usable for artifact-only evaluation",
    ):
        prediction_module._preflight_prediction_run(
            run_context=run_context,
            policy=PredictionRunPolicy(max_workers=1, resume=True),
            method_manifest={"adapter": "recording-v1"},
            benchmark_variant="test_variant",
            run_scope=RunScope.FULL,
            dataset=_build_dataset(),
            source_paths=(),
        )


def test_runner_writes_predictions_and_private_labels_separately(tmp_path: Path) -> None:
    """runner 应保存回复，并把 gold/evidence 隔离到 evaluator-only artifact。"""

    system = RecordingPredictionSystem()
    context = _create_context(tmp_path)

    summary = run_predictions(
        dataset=_build_dataset(),
        system=system,
        run_context=context,
        policy=PredictionRunPolicy(max_workers=1),
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    prediction_path = context.artifacts_dir / "method_predictions.jsonl"
    private_path = context.artifacts_dir / "evaluator_private_labels.jsonl"
    predictions = read_jsonl(prediction_path)
    private_labels = read_jsonl(private_path)

    assert summary.completed_questions == 2
    assert len(predictions) == 2
    assert predictions[0]["answer"].startswith("预测:")
    assert "gold_answer" not in json.dumps(predictions, ensure_ascii=False)
    assert "evidence" not in json.dumps(predictions, ensure_ascii=False)
    assert {row["gold_answer"] for row in private_labels} == {
        "标准答案 1",
        "标准答案 2",
    }
    assert not (context.artifacts_dir / "answer_scores.locomo_f1.jsonl").exists()


def test_runner_uses_retrieve_first_provider_and_framework_reader(
    tmp_path: Path,
) -> None:
    """新 provider 路径应先 retrieve，再由 framework reader 生成 answer。"""

    dataset = _build_dataset()
    provider = RecordingMemoryProvider()
    answer_client = FakeAnswerLLMClient(answer="framework answer")
    reader = FrameworkAnswerReader(client=answer_client)
    context = _create_context(tmp_path)

    summary = run_predictions(
        dataset=dataset,
        system=provider,
        run_context=context,
        policy=PredictionRunPolicy(max_workers=1),
        answer_reader=reader,
        method_manifest={"adapter": "recording-provider-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    predictions = read_jsonl(context.artifacts_dir / "method_predictions.jsonl")
    retrievals = read_jsonl(
        context.artifacts_dir / "answer_prompts.prediction.jsonl"
    )

    assert summary.completed_questions == 2
    assert provider.added_conversation_ids == ["conv-1", "conv-2"]
    assert provider.retrieved_question_ids == ["conv-1:q1", "conv-2:q1"]
    assert [record["answer"] for record in predictions] == [
        "framework answer",
        "framework answer",
    ]
    assert retrievals[0]["answer_prompt"] == "memory for 问题 1"
    assert retrievals[0]["prompt_messages"] == [
        {"role": "user", "content": "memory for 问题 1"}
    ]
    assert "memory for 问题 1" in answer_client.calls[0]["prompt"]
    assert answer_client.calls[0]["messages"] == [
        {"role": "user", "content": "memory for 问题 1"}
    ]


def test_runner_ingests_native_v3_provider_with_event_stream_and_reports(
    tmp_path: Path,
) -> None:
    """v3 provider 主链路应按声明粒度 ingest 并写 session memory artifact。"""

    dataset = _build_dataset()
    provider = RecordingV3TurnProvider()
    answer_client = FakeAnswerLLMClient(answer="framework answer")
    reader = FrameworkAnswerReader(client=answer_client)
    context = _create_context(tmp_path)

    summary = run_predictions(
        dataset=dataset,
        system=provider,
        run_context=context,
        policy=PredictionRunPolicy(max_workers=1),
        answer_reader=reader,
        method_manifest={"adapter": "recording-v3"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    retrievals = read_jsonl(
        context.artifacts_dir / "answer_prompts.prediction.jsonl"
    )
    session_reports = read_jsonl(
        context.artifacts_dir / "session_memory_reports.jsonl"
    )
    manifest = json.loads((context.run_dir / "manifest.json").read_text())

    assert summary.completed_questions == 2
    assert provider.ingested_turn_ids == ["conv-1:t1", "conv-2:t1"]
    assert [ref.session_id for ref in provider.ended_sessions] == [
        "conv-1:s1",
        "conv-2:s1",
    ]
    assert [ref.isolation_key for ref in provider.ended_conversations] == [
        "prediction-run_conv-1",
        "prediction-run_conv-2",
    ]
    assert manifest["method"]["protocol_version"] == "v3"
    assert retrievals[0]["formatted_memory"] == "v3 memory for 问题 1"
    assert retrievals[0]["retrieved_items"][0]["source_turn_ids"] == ["conv-1:t1"]
    assert session_reports[0]["memories"] == ["session-memory:conv-1:s1"]
    assert session_reports[0]["session_ref"] == {
        "isolation_key": "prediction-run_conv-1",
        "session_id": "conv-1:s1",
    }


def test_runner_uses_membench_unified_prompt_builder_and_choice_parser(
    tmp_path: Path,
) -> None:
    """MemBench unified track 应用 formatted_memory 拼官方 prompt 并解析选择。"""

    conversation_id = "membench-conv-1"
    question_id = f"{conversation_id}:q1"
    dataset = Dataset(
        dataset_name="membench",
        conversations=[
            Conversation(
                conversation_id=conversation_id,
                sessions=[
                    Session(
                        session_id="s1",
                        turns=[Turn("1", "user", "Alex prefers coffee.")],
                    )
                ],
                questions=[
                    Question(
                        question_id=question_id,
                        conversation_id=conversation_id,
                        text="What does Alex prefer?",
                        question_time="2026-01-02",
                        options={
                            "A": "Tea",
                            "B": "Coffee",
                            "C": "Juice",
                            "D": "Water",
                        },
                    )
                ],
                gold_answers={
                    question_id: GoldAnswerInfo(
                        question_id=question_id,
                        answer="B",
                    )
                },
            )
        ],
    )
    provider = RecordingV3TurnProvider()
    answer_client = FakeAnswerLLMClient(answer="The answer is b.")
    context = _create_context(tmp_path)

    summary = run_predictions(
        dataset=dataset,
        system=provider,
        run_context=context,
        policy=PredictionRunPolicy(max_workers=1),
        answer_reader=FrameworkAnswerReader(client=answer_client),
        method_manifest={"adapter": "recording-v3"},
        benchmark_variant="0_10k",
        run_scope=RunScope.SMOKE,
        unified_prompt_builder=build_membench_unified_answer_prompt,
        prediction_transform=normalize_membench_choice_prediction,
    )

    predictions = read_jsonl(context.artifacts_dir / "method_predictions.jsonl")
    retrievals = read_jsonl(
        context.artifacts_dir / "answer_prompts.prediction.jsonl"
    )
    manifest = json.loads((context.run_dir / "manifest.json").read_text())

    assert summary.completed_questions == 1
    assert predictions[0]["answer"] == "B"
    assert predictions[0]["metadata"]["raw_answer"] == "The answer is b."
    assert retrievals[0]["metadata"]["prompt_track"] == "unified"
    assert retrievals[0]["formatted_memory"] == (
        "v3 memory for What does Alex prefer?"
    )
    assert retrievals[0]["prompt_messages"] == answer_client.calls[0]["messages"]
    assert "Past memory: v3 memory for What does Alex prefer?" in retrievals[0][
        "answer_prompt"
    ]
    assert "Question: (current time is 2026-01-02) What does Alex prefer?" in (
        retrievals[0]["answer_prompt"]
    )
    assert "B. Coffee" in retrievals[0]["answer_prompt"]
    assert manifest["method"]["prompt_track"] == "unified"


def test_isolated_worker_ingests_native_v3_provider_with_event_stream(
    tmp_path: Path,
) -> None:
    """isolated worker path 也必须对 v3 provider 使用事件流 ingest。"""

    from memory_benchmark.methods.registry import MethodBuildContext

    dataset = _build_dataset()
    shared_events: list[tuple[str, str]] = []
    answer_client = FakeAnswerLLMClient(answer="isolated answer")
    reader = FrameworkAnswerReader(client=answer_client)
    context = _create_context(tmp_path)

    def fake_factory(_context: MethodBuildContext) -> RecordingV3TurnProvider:
        """每个 worker 创建独立 v3 provider，并共享观测列表。"""

        return RecordingV3TurnProvider(shared_events=shared_events)

    run_predictions(
        dataset=dataset,
        system=RecordingV3TurnProvider(shared_events=shared_events),
        run_context=context,
        policy=PredictionRunPolicy(max_workers=2),
        answer_reader=reader,
        method_manifest={"adapter": "recording-v3"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
        system_factory=fake_factory,
        build_context_template=MethodBuildContext(
            config={},
            openai_settings=None,
            path_settings=None,
            storage_root=context.run_dir / "method_state",
        ),
        supports_shared_instance_parallelism=False,
    )

    assert ("ingest", "conv-1:t1") in shared_events
    assert ("ingest", "conv-2:t1") in shared_events
    assert ("end_session", "conv-1:s1") in shared_events
    assert ("end_conversation", "prediction-run_conv-2") in shared_events


def test_v3_session_memory_report_contract_fails_when_declared_but_empty(
    tmp_path: Path,
) -> None:
    """声明 session_memory_report=True 但从不报告时应 fail-fast。"""

    dataset = _build_dataset()
    provider = RecordingV3TurnProvider(report_sessions=False)
    reader = FrameworkAnswerReader(client=FakeAnswerLLMClient(answer="unused"))
    context = _create_context(tmp_path)

    with pytest.raises(ConfigurationError, match="session_memory_report"):
        run_predictions(
            dataset=dataset,
            system=provider,
            run_context=context,
            policy=PredictionRunPolicy(max_workers=1),
            answer_reader=reader,
            method_manifest={"adapter": "recording-v3"},
            benchmark_variant="test_variant",
            run_scope=RunScope.FULL,
        )


def test_runner_bridges_legacy_provider_and_counts_empty_memory_sentinel(
    tmp_path: Path,
) -> None:
    """旧 BaseMemoryProvider 应经 v3 桥接运行并统计 sentinel fallback。"""

    dataset = _build_dataset()
    provider = RecordingMemoryProvider()
    answer_client = FakeAnswerLLMClient(answer="framework answer")
    reader = FrameworkAnswerReader(client=answer_client)
    context = _create_context(tmp_path)

    summary = run_predictions(
        dataset=dataset,
        system=provider,
        run_context=context,
        policy=PredictionRunPolicy(max_workers=1),
        answer_reader=reader,
        method_manifest={"adapter": "recording-provider-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    manifest = json.loads((context.run_dir / "manifest.json").read_text())
    retrievals = read_jsonl(
        context.artifacts_dir / "answer_prompts.prediction.jsonl"
    )

    assert manifest["method"]["protocol_version"] == "v2-bridged"
    assert manifest["method"]["prompt_track"] == "native"
    assert manifest["method"]["profile"] == {}
    assert summary.metadata["bridge_empty_memory_sentinel_count"] == 2
    assert retrievals[0]["formatted_memory"] == BRIDGE_EMPTY_MEMORY_SENTINEL
    assert retrievals[0]["metadata"]["bridge_warning"] == (
        "legacy_provider_exposed_no_memory_context"
    )
    assert answer_client.calls[0]["messages"] == [
        {"role": "user", "content": "memory for 问题 1"}
    ]
    assert BRIDGE_EMPTY_MEMORY_SENTINEL not in answer_client.calls[0]["prompt"]


def test_shared_mock_provider_uses_framework_reader(tmp_path: Path) -> None:
    """共享 mock provider 应走 retrieve-first reader，而不是 method 自己回答。"""

    dataset = _build_dataset()
    provider = MockMemoryProvider(
        context_by_question_id={"conv-1:q1": "conv-1 custom memory"}
    )
    answer_client = FakeAnswerLLMClient(answer="framework mock answer")
    reader = FrameworkAnswerReader(client=answer_client)
    context = _create_context(tmp_path)

    summary = run_predictions(
        dataset=dataset,
        system=provider,
        run_context=context,
        policy=PredictionRunPolicy(max_workers=1),
        answer_reader=reader,
        method_manifest={"adapter": "shared-mock-provider-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    predictions = read_jsonl(context.artifacts_dir / "method_predictions.jsonl")
    retrievals = read_jsonl(
        context.artifacts_dir / "answer_prompts.prediction.jsonl"
    )

    assert summary.completed_questions == 2
    assert provider.added_conversation_ids == ["conv-1", "conv-2"]
    assert [record["answer"] for record in predictions] == [
        "framework mock answer",
        "framework mock answer",
    ]
    assert retrievals[0]["formatted_memory"] == "conv-1 custom memory"
    assert retrievals[0]["prompt_messages"] == [
        {"role": "user", "content": "conv-1 custom memory"}
    ]
    assert retrievals[1]["formatted_memory"] == "mock-context-for:conv-2:q1"
    assert "conv-1 custom memory" in answer_client.calls[0]["prompt"]


@pytest.mark.parametrize("granularity", ["turn", "pair", "session", "conversation"])
def test_mock_memory_provider_runs_as_native_v3_for_each_granularity(
    tmp_path: Path,
    granularity: str,
) -> None:
    """MockMemoryProvider 应支持四种 v3 consume granularity。"""

    dataset = _build_dataset()
    provider = MockMemoryProvider(
        consume_granularity=granularity,
        context_by_question_id={"conv-1:q1": "conv-1 mock memory"},
    )
    reader = FrameworkAnswerReader(client=FakeAnswerLLMClient(answer="mock answer"))
    context = _create_context(tmp_path)

    summary = run_predictions(
        dataset=dataset,
        system=provider,
        run_context=context,
        policy=PredictionRunPolicy(max_workers=1),
        answer_reader=reader,
        method_manifest={"adapter": f"mock-v3-{granularity}"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    manifest = json.loads((context.run_dir / "manifest.json").read_text())
    retrievals = read_jsonl(
        context.artifacts_dir / "answer_prompts.prediction.jsonl"
    )
    session_reports = read_jsonl(
        context.artifacts_dir / "session_memory_reports.jsonl"
    )

    assert summary.completed_questions == 2
    assert provider.added_conversation_ids == ["conv-1", "conv-2"]
    assert manifest["method"]["protocol_version"] == "v3"
    assert manifest["method"]["prompt_track"] == "native"
    assert retrievals[0]["formatted_memory"] == "conv-1 mock memory"
    assert retrievals[0]["retrieved_items"][0]["source_turn_ids"]
    assert session_reports
    assert session_reports[0]["memories"]


def test_isolated_retrieve_first_worker_persists_answer_prompt_artifact(
    tmp_path: Path,
) -> None:
    """isolated worker 路径也必须写出完整 answer prompt artifact。"""

    from memory_benchmark.methods.registry import MethodBuildContext

    dataset = _build_dataset()
    answer_client = FakeAnswerLLMClient(answer="isolated framework answer")
    reader = FrameworkAnswerReader(client=answer_client)
    context = _create_context(tmp_path)

    def fake_factory(_context: MethodBuildContext) -> BaseMemoryProvider:
        """每个 isolated worker 创建独立 provider 实例。"""

        return RecordingMemoryProvider()

    summary = run_predictions(
        dataset=dataset,
        system=RecordingMemoryProvider(),
        run_context=context,
        policy=PredictionRunPolicy(max_workers=2),
        answer_reader=reader,
        method_manifest={"adapter": "recording-provider-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
        system_factory=fake_factory,
        build_context_template=MethodBuildContext(
            config={},
            openai_settings=None,
            path_settings=None,
            storage_root=context.run_dir / "method_state",
        ),
        supports_shared_instance_parallelism=False,
    )

    retrievals = read_jsonl(
        context.artifacts_dir / "answer_prompts.prediction.jsonl"
    )

    assert summary.completed_questions == 2
    assert [record["question_id"] for record in retrievals] == [
        "conv-1:q1",
        "conv-2:q1",
    ]
    assert retrievals[0]["prompt_messages"] == [
        {"role": "user", "content": "memory for 问题 1"}
    ]
    assert retrievals[1]["prompt_messages"] == [
        {"role": "user", "content": "memory for 问题 2"}
    ]


def test_resume_reuses_completed_retrieval_when_answer_failed(
    tmp_path: Path,
) -> None:
    """retrieve 已落盘但 answer 失败时，resume 不应重新调用 provider.retrieve。"""

    dataset = _build_two_question_dataset()
    provider = RecordingMemoryProvider()
    failing_reader = FrameworkAnswerReader(client=FailingAnswerClient())
    context = _create_context(tmp_path)

    with pytest.raises(RuntimeError, match="answer failed once"):
        run_predictions(
            dataset=dataset,
            system=provider,
            run_context=context,
            policy=PredictionRunPolicy(max_workers=1),
            answer_reader=failing_reader,
            method_manifest={"adapter": "recording-provider-v1"},
            benchmark_variant="test_variant",
            run_scope=RunScope.FULL,
        )

    retrievals_after_failure = read_jsonl(
        context.artifacts_dir / "answer_prompts.prediction.jsonl"
    )
    assert provider.retrieved_question_ids == ["conv-1:q1"]
    assert [record["question_id"] for record in retrievals_after_failure] == [
        "conv-1:q1"
    ]

    provider_after_resume = RecordingMemoryProvider()
    success_reader = FrameworkAnswerReader(
        client=FakeAnswerLLMClient(answer="resumed answer")
    )
    resumed_context = _create_context(tmp_path, resume=True)

    run_predictions(
        dataset=dataset,
        system=provider_after_resume,
        run_context=resumed_context,
        policy=PredictionRunPolicy(max_workers=1, resume=True),
        answer_reader=success_reader,
        method_manifest={"adapter": "recording-provider-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    predictions = read_jsonl(context.artifacts_dir / "method_predictions.jsonl")
    assert provider_after_resume.retrieved_question_ids == ["conv-1:q2"]
    assert success_reader.client.calls[0]["messages"] == [
        {"role": "user", "content": "memory for 问题 1"}
    ]
    assert [record["answer"] for record in predictions] == [
        "resumed answer",
        "resumed answer",
    ]


def test_runner_rebuilds_public_objects_before_calling_method(tmp_path: Path) -> None:
    """method 收到的 conversation/question 不能携带 gold、evidence 或动态私有属性。"""

    dataset = _build_dataset()
    dataset.conversations[0].sessions[0].turns[0].evidence = ["private-turn"]
    dataset.conversations[0].questions[0].answer = "private-answer"
    system = RecordingPredictionSystem()

    run_predictions(
        dataset=dataset,
        system=system,
        run_context=_create_context(tmp_path),
        policy=PredictionRunPolicy(max_workers=1),
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    first_conversation = system.added_payloads[0]
    first_question = system.answered_questions[0]
    assert first_conversation.gold_answers == {}
    assert not hasattr(first_conversation.sessions[0].turns[0], "evidence")
    assert not hasattr(first_question, "answer")


def test_runner_uses_conversation_workers_but_coordinator_writes_complete_artifacts(
    tmp_path: Path,
) -> None:
    """两个 conversation 可并发执行，最终 JSONL 仍应完整且每题仅一条。"""

    system = RecordingPredictionSystem(delay_seconds=0.05)

    run_predictions(
        dataset=_build_dataset(),
        system=system,
        run_context=_create_context(tmp_path),
        policy=PredictionRunPolicy(max_workers=2),
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    predictions = read_jsonl(
        tmp_path / "prediction-run" / "artifacts" / "method_predictions.jsonl"
    )
    assert system.max_active_adds == 2
    assert sorted(row["question_id"] for row in predictions) == [
        "conv-1:q1",
        "conv-2:q1",
    ]


def test_resumable_failure_leaves_current_turn_in_flight(tmp_path: Path) -> None:
    """第二个 turn 开始后失败时，应保留不可自动重放的 in_flight 状态。"""

    system = ResumablePredictionSystem(fail_on_started_index=1)

    with pytest.raises(RuntimeError, match="in flight"):
        run_predictions(
            dataset=_build_three_turn_dataset(),
            system=system,
            run_context=_create_context(tmp_path),
            policy=PredictionRunPolicy(max_workers=1),
            method_manifest={"adapter": "resumable-v1"},
            benchmark_variant="test_variant",
            run_scope=RunScope.FULL,
        )

    store = TurnIngestCheckpointStore(
        tmp_path / "prediction-run" / "checkpoints" / "ingest_turns"
    )
    checkpoint = store.load("conv-1", total_turns=3)
    assert checkpoint is not None
    assert checkpoint.status == "in_flight"
    assert checkpoint.next_turn_index == 1
    assert checkpoint.current_turn_id == "conv-1:t2"
    assert system.processed_turn_ids == ["conv-1:t1"]


def test_ready_checkpoint_resumes_only_unconfirmed_turns(tmp_path: Path) -> None:
    """已确认第一个 turn 后的 ready checkpoint 应从 index 1 继续。"""

    first_system = ResumablePredictionSystem(fail_after_completed_index=0)
    with pytest.raises(RuntimeError, match="confirmed"):
        run_predictions(
            dataset=_build_three_turn_dataset(),
            system=first_system,
            run_context=_create_context(tmp_path),
            policy=PredictionRunPolicy(max_workers=1),
            method_manifest={"adapter": "resumable-v1"},
            benchmark_variant="test_variant",
            run_scope=RunScope.FULL,
        )

    resumed_system = ResumablePredictionSystem()
    summary = run_predictions(
        dataset=_build_three_turn_dataset(),
        system=resumed_system,
        run_context=_create_context(tmp_path, resume=True),
        policy=PredictionRunPolicy(max_workers=1, resume=True),
        method_manifest={"adapter": "resumable-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    assert resumed_system.start_indices == [("conv-1", 1)]
    assert resumed_system.processed_turn_ids == ["conv-1:t2", "conv-1:t3"]
    assert summary.completed_conversations == 1
    assert summary.completed_questions == 1


def test_resumable_system_can_disable_turn_resume_per_conversation(
    tmp_path: Path,
) -> None:
    """method 可按 conversation 退回完整 add，从而使用 conversation-level resume。"""

    system = SelectiveResumablePredictionSystem(turn_resume_conversation_ids=set())

    summary = run_predictions(
        dataset=_build_three_turn_dataset(),
        system=system,
        run_context=_create_context(tmp_path),
        policy=PredictionRunPolicy(max_workers=1),
        method_manifest={"adapter": "selective-resumable-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    assert system.added_conversation_ids == ["conv-1"]
    assert system.start_indices == []
    assert summary.completed_conversations == 1
    checkpoint_path = (
        tmp_path
        / "prediction-run"
        / "checkpoints"
        / "ingest_turns"
        / "conv-1.json"
    )
    assert not checkpoint_path.exists()


def test_ready_at_total_turns_still_validates_method_finalization(
    tmp_path: Path,
) -> None:
    """最后一个 turn 已确认后仍应调用零 turn 收尾，不能直接升级 completed。"""

    first_system = ResumablePredictionSystem(fail_after_completed_index=2)
    with pytest.raises(RuntimeError, match="confirmed"):
        run_predictions(
            dataset=_build_three_turn_dataset(),
            system=first_system,
            run_context=_create_context(tmp_path),
            policy=PredictionRunPolicy(max_workers=1),
            method_manifest={"adapter": "resumable-v1"},
            benchmark_variant="test_variant",
            run_scope=RunScope.FULL,
        )

    resumed_system = ResumablePredictionSystem()
    summary = run_predictions(
        dataset=_build_three_turn_dataset(),
        system=resumed_system,
        run_context=_create_context(tmp_path, resume=True),
        policy=PredictionRunPolicy(max_workers=1, resume=True),
        method_manifest={"adapter": "resumable-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    assert resumed_system.start_indices == [("conv-1", 3)]
    assert resumed_system.processed_turn_ids == []
    assert summary.completed_conversations == 1


def test_in_flight_resume_aborts_before_any_method_call(tmp_path: Path) -> None:
    """任一 in_flight checkpoint 都必须在创建 worker 前阻止 resume。"""

    first_system = ResumablePredictionSystem(fail_on_started_index=1)
    with pytest.raises(RuntimeError, match="in flight"):
        run_predictions(
            dataset=_build_three_turn_dataset(),
            system=first_system,
            run_context=_create_context(tmp_path),
            policy=PredictionRunPolicy(max_workers=1),
            method_manifest={"adapter": "resumable-v1"},
            benchmark_variant="test_variant",
            run_scope=RunScope.FULL,
        )

    resumed_system = ResumablePredictionSystem()
    with pytest.raises(ConfigurationError, match="in_flight"):
        run_predictions(
            dataset=_build_three_turn_dataset(),
            system=resumed_system,
            run_context=_create_context(tmp_path, resume=True),
            policy=PredictionRunPolicy(max_workers=1, resume=True),
            method_manifest={"adapter": "resumable-v1"},
            benchmark_variant="test_variant",
            run_scope=RunScope.FULL,
        )

    assert resumed_system.start_indices == []
    assert resumed_system.answered_questions == []


def test_any_in_flight_checkpoint_blocks_all_conversation_workers(
    tmp_path: Path,
) -> None:
    """两个 conversation 中任一状态不确定时，resume 不能先启动另一侧 worker。"""

    first_system = ResumablePredictionSystem()
    run_predictions(
        dataset=_build_dataset(),
        system=first_system,
        run_context=_create_context(tmp_path),
        policy=PredictionRunPolicy(max_workers=2),
        method_manifest={"adapter": "resumable-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )
    store = TurnIngestCheckpointStore(
        tmp_path / "prediction-run" / "checkpoints" / "ingest_turns"
    )
    atomic_write_json(
        store.path_for("conv-2"),
        {
            "schema_version": 1,
            "conversation_id": "conv-2",
            "status": "in_flight",
            "next_turn_index": 0,
            "total_turns": 1,
            "current_turn_index": 0,
            "current_turn_id": "conv-2:t1",
        },
    )

    resumed_system = ResumablePredictionSystem()
    with pytest.raises(ConfigurationError, match="in_flight"):
        run_predictions(
            dataset=_build_dataset(),
            system=resumed_system,
            run_context=_create_context(tmp_path, resume=True),
            policy=PredictionRunPolicy(max_workers=2, resume=True),
            method_manifest={"adapter": "resumable-v1"},
            benchmark_variant="test_variant",
            run_scope=RunScope.FULL,
        )

    assert resumed_system.start_indices == []
    assert resumed_system.answered_questions == []


def test_non_resumable_method_rejects_existing_turn_checkpoint(
    tmp_path: Path,
) -> None:
    """未启用 turn-level resume 时遇到 turn checkpoint 应报错。"""

    first_system = RecordingPredictionSystem()
    run_predictions(
        dataset=_build_dataset(),
        system=first_system,
        run_context=_create_context(tmp_path),
        policy=PredictionRunPolicy(max_workers=1),
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )
    store = TurnIngestCheckpointStore(
        tmp_path / "prediction-run" / "checkpoints" / "ingest_turns"
    )
    store.mark_started("conv-1", 0, "conv-1:t1", total_turns=1)
    store.mark_turn_completed("conv-1", 0, "conv-1:t1", total_turns=1)

    resumed_system = RecordingPredictionSystem()
    with pytest.raises(
        ConfigurationError,
        match="method does not enable turn-level resume",
    ):
        run_predictions(
            dataset=_build_dataset(),
            system=resumed_system,
            run_context=_create_context(tmp_path, resume=True),
            policy=PredictionRunPolicy(max_workers=1, resume=True),
            method_manifest={"adapter": "recording-v1"},
            benchmark_variant="test_variant",
            run_scope=RunScope.FULL,
        )

    assert resumed_system.added_payloads == []
    assert resumed_system.answered_questions == []


def test_completed_turn_checkpoint_repairs_missing_coarse_status(
    tmp_path: Path,
) -> None:
    """逐 turn 已完成但 coarse 状态缺失时，resume 只补交状态而不重复 add。"""

    first_system = ResumablePredictionSystem()
    run_predictions(
        dataset=_build_three_turn_dataset(),
        system=first_system,
        run_context=_create_context(tmp_path),
        policy=PredictionRunPolicy(max_workers=1),
        method_manifest={"adapter": "resumable-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )
    run_dir = tmp_path / "prediction-run"
    atomic_write_json(run_dir / "checkpoints" / "conversation_status.json", {})

    resumed_system = ResumablePredictionSystem()
    summary = run_predictions(
        dataset=_build_three_turn_dataset(),
        system=resumed_system,
        run_context=_create_context(tmp_path, resume=True),
        policy=PredictionRunPolicy(max_workers=1, resume=True),
        method_manifest={"adapter": "resumable-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    assert resumed_system.start_indices == []
    assert summary.completed_conversations == 1
    coarse_status = json.loads(
        (run_dir / "checkpoints" / "conversation_status.json").read_text(
            encoding="utf-8"
        )
    )
    assert coarse_status == {"conv-1": {"status": "completed"}}


def test_resumable_conversations_write_independent_checkpoint_files(
    tmp_path: Path,
) -> None:
    """并发 conversation 应各自写一个 checkpoint 文件，不能共享状态文件。"""

    system = ResumablePredictionSystem()
    run_predictions(
        dataset=_build_dataset(),
        system=system,
        run_context=_create_context(tmp_path),
        policy=PredictionRunPolicy(max_workers=2),
        method_manifest={"adapter": "resumable-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    checkpoint_dir = (
        tmp_path / "prediction-run" / "checkpoints" / "ingest_turns"
    )
    checkpoint_files = sorted(checkpoint_dir.glob("*.json"))
    assert len(checkpoint_files) == 2
    assert {
        json.loads(path.read_text(encoding="utf-8"))["conversation_id"]
        for path in checkpoint_files
    } == {"conv-1", "conv-2"}


def test_resume_skips_completed_conversations_and_questions(tmp_path: Path) -> None:
    """resume 应复用 checkpoint，不重复调用已经完成的 add/get_answer。"""

    first_system = RecordingPredictionSystem()
    run_predictions(
        dataset=_build_dataset(),
        system=first_system,
        run_context=_create_context(tmp_path),
        policy=PredictionRunPolicy(max_workers=1),
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    resumed_system = RecordingPredictionSystem()
    summary = run_predictions(
        dataset=_build_dataset(),
        system=resumed_system,
        run_context=_create_context(tmp_path, resume=True),
        policy=PredictionRunPolicy(max_workers=1, resume=True),
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    assert resumed_system.added_payloads == []
    assert resumed_system.answered_questions == []
    assert summary.completed_questions == 2
    assert len(
        read_jsonl(
            tmp_path / "prediction-run" / "artifacts" / "method_predictions.jsonl"
        )
    ) == 2
    assert not list(
        (tmp_path / "prediction-run" / "checkpoints" / "ingest_turns").glob(
            "*.json"
        )
    )


def test_resume_accepts_json_stable_conversation_id_policy_and_skips_work(
    tmp_path: Path,
) -> None:
    """带 conversation_ids 白名单的相同 resume 应成功且不重复执行已完成工作。"""

    first_system = RecordingPredictionSystem()
    run_predictions(
        dataset=_build_dataset(),
        system=first_system,
        run_context=_create_context(tmp_path),
        policy=PredictionRunPolicy(
            max_workers=1,
            conversation_ids=("conv-2",),
        ),
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    resumed_system = RecordingPredictionSystem()
    summary = run_predictions(
        dataset=_build_dataset(),
        system=resumed_system,
        run_context=_create_context(tmp_path, resume=True),
        policy=PredictionRunPolicy(
            max_workers=1,
            conversation_ids=("conv-2",),
            resume=True,
        ),
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    assert resumed_system.added_payloads == []
    assert resumed_system.answered_questions == []
    assert summary.total_conversations == 1
    assert summary.completed_questions == 1
    predictions = read_jsonl(
        tmp_path / "prediction-run" / "artifacts" / "method_predictions.jsonl"
    )
    assert [row["question_id"] for row in predictions] == ["conv-2:q1"]


def test_policy_can_limit_conversations_and_questions_without_changing_dataset(
    tmp_path: Path,
) -> None:
    """smoke policy 应能选定 conversation 并限制每个 conversation 的题数。"""

    system = RecordingPredictionSystem()
    summary = run_predictions(
        dataset=_build_dataset(),
        system=system,
        run_context=_create_context(tmp_path),
        policy=PredictionRunPolicy(
            max_workers=1,
            conversation_ids=("conv-2",),
            question_limit_per_conversation=1,
        ),
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    assert [item.conversation_id for item in system.added_payloads] == ["conv-2"]
    assert [item.question_id for item in system.answered_questions] == ["conv-2:q1"]
    assert summary.total_conversations == 1
    assert summary.completed_questions == 1


def test_question_limit_is_resume_budget_not_manifest_identity(
    tmp_path: Path,
) -> None:
    """同一 run_id 可先答少量题，随后用更大题数预算 resume 继续。"""

    first_system = RecordingPredictionSystem()
    first_summary = run_predictions(
        dataset=_build_two_question_dataset(),
        system=first_system,
        run_context=_create_context(tmp_path),
        policy=PredictionRunPolicy(
            max_workers=1,
            question_limit_per_conversation=1,
        ),
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    resumed_system = RecordingPredictionSystem()
    resumed_summary = run_predictions(
        dataset=_build_two_question_dataset(),
        system=resumed_system,
        run_context=_create_context(tmp_path, resume=True),
        policy=PredictionRunPolicy(
            max_workers=1,
            question_limit_per_conversation=2,
            resume=True,
        ),
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    assert [item.question_id for item in first_system.answered_questions] == [
        "conv-1:q1"
    ]
    assert [item.question_id for item in resumed_system.answered_questions] == [
        "conv-1:q2"
    ]
    assert first_summary.completed_questions == 1
    assert resumed_summary.total_questions == 2
    assert resumed_summary.completed_questions == 2
    predictions = read_jsonl(
        tmp_path / "prediction-run" / "artifacts" / "method_predictions.jsonl"
    )
    assert [row["question_id"] for row in predictions] == [
        "conv-1:q1",
        "conv-1:q2",
    ]


def test_prediction_budget_limits_new_unfinished_conversations(
    tmp_path: Path,
) -> None:
    """max_new_conversations=2 时只推进前两个未完成 conversation。"""

    system = RecordingPredictionSystem()
    summary = run_predictions(
        dataset=_build_numbered_dataset(4),
        system=system,
        run_context=_create_context(tmp_path),
        policy=PredictionRunPolicy(
            max_workers=1,
            max_new_conversations=2,
        ),
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    assert [item.conversation_id for item in system.added_payloads] == [
        "conv-1",
        "conv-2",
    ]
    assert [item.question_id for item in system.answered_questions] == [
        "conv-1:q1",
        "conv-2:q1",
    ]
    assert summary.total_conversations == 4
    assert summary.completed_conversations == 2
    assert summary.total_questions == 4
    assert summary.completed_questions == 2
    assert summary.metadata["run_control"] == {
        "max_new_conversations": 2,
        "retry_failed_conversations": False,
        "skipped_failed_conversations": [],
        "budget_exhausted": True,
    }
    summary_payload = json.loads(
        (tmp_path / "prediction-run" / "summaries" / "summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary_payload["metadata"]["run_control"] == {
        "max_new_conversations": 2,
        "retry_failed_conversations": False,
        "skipped_failed_conversations": [],
        "budget_exhausted": True,
    }


def test_prediction_budget_skips_completed_conversations_on_resume(
    tmp_path: Path,
) -> None:
    """resume 时预算应跳过已完成 conversation，继续后续未完成 conversation。"""

    first_system = RecordingPredictionSystem()
    run_predictions(
        dataset=_build_numbered_dataset(4),
        system=first_system,
        run_context=_create_context(tmp_path),
        policy=PredictionRunPolicy(
            max_workers=1,
            max_new_conversations=2,
        ),
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    resumed_system = RecordingPredictionSystem()
    summary = run_predictions(
        dataset=_build_numbered_dataset(4),
        system=resumed_system,
        run_context=_create_context(tmp_path, resume=True),
        policy=PredictionRunPolicy(
            max_workers=1,
            resume=True,
            max_new_conversations=1,
        ),
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    assert [item.conversation_id for item in resumed_system.added_payloads] == [
        "conv-3"
    ]
    assert [item.question_id for item in resumed_system.answered_questions] == [
        "conv-3:q1"
    ]
    assert summary.total_conversations == 4
    assert summary.completed_conversations == 3
    assert summary.completed_questions == 3
    assert summary.metadata["run_control"] == {
        "max_new_conversations": 1,
        "retry_failed_conversations": False,
        "skipped_failed_conversations": [],
        "budget_exhausted": True,
    }
    predictions = read_jsonl(
        tmp_path / "prediction-run" / "artifacts" / "method_predictions.jsonl"
    )
    assert [row["question_id"] for row in predictions] == [
        "conv-1:q1",
        "conv-2:q1",
        "conv-3:q1",
    ]


def test_prediction_work_plan_quarantines_failed_conversations_by_default() -> None:
    """默认 resume 不应重跑已标记 failed 的 conversation，避免失败后空烧 API。

    输入:
        conversation_status: 模拟上次运行中 `conv-1` 已在 add 或 answer 阶段失败。
        prediction_records: 空，表示没有任何问题已经完成。

    输出:
        默认 policy 只推进 `conv-2`；显式 retry policy 对没有 `ingested=true`
        的 legacy failed 直接 fail closed。
    """

    from memory_benchmark.runners.prediction import _build_prediction_work_plan

    dataset = _build_numbered_dataset(2)
    selected_questions = {
        conversation.conversation_id: list(conversation.questions)
        for conversation in dataset.conversations
    }
    conversation_status = {
        "conv-1": {
            "status": "failed",
            "error_type": "RuntimeError",
            "error": "boom",
        }
    }

    default_plan = _build_prediction_work_plan(
        conversations=list(dataset.conversations),
        selected_questions=selected_questions,
        conversation_status=conversation_status,
        prediction_records={},
        policy=PredictionRunPolicy(resume=True),
    )
    assert [
        item.conversation.conversation_id for item in default_plan.items
    ] == ["conv-2"]

    with pytest.raises(ConfigurationError, match="clean retry"):
        _build_prediction_work_plan(
            conversations=list(dataset.conversations),
            selected_questions=selected_questions,
            conversation_status=conversation_status,
            prediction_records={},
            policy=PredictionRunPolicy(
                resume=True,
                retry_failed_conversations=True,
            ),
        )


def test_retry_failed_ingested_conversation_resumes_pending_questions_only() -> None:
    """retry failed 时已完成写入的 conversation 不应重复 add。

    输入:
        conversation_status: `conv-1` 上次失败，但 `ingested=true` 表示 memory state
            已经持久化完成。
        prediction_records: `q1` 已有预测，`q2` 尚未回答。

    输出:
        work plan 只回答 `q2`，且 `needs_ingest=False`。
    """

    from memory_benchmark.runners.prediction import _build_prediction_work_plan

    dataset = _build_two_question_dataset()
    conversation = dataset.conversations[0]
    selected_questions = {
        conversation.conversation_id: list(conversation.questions),
    }
    plan = _build_prediction_work_plan(
        conversations=list(dataset.conversations),
        selected_questions=selected_questions,
        conversation_status={
            "conv-1": {
                "status": "failed",
                "stage": "isolated_worker",
                "error_type": "RuntimeError",
                "error": "reader failed",
                "ingested": True,
            }
        },
        prediction_records={
            "conv-1:q1": {
                "question_id": "conv-1:q1",
                "conversation_id": "conv-1",
                "answer": "partial",
            }
        },
        policy=PredictionRunPolicy(
            resume=True,
            retry_failed_conversations=True,
        ),
    )

    assert len(plan.items) == 1
    assert plan.items[0].conversation.conversation_id == "conv-1"
    assert plan.items[0].needs_ingest is False
    assert [question.question_id for question in plan.items[0].pending_questions] == [
        "conv-1:q2"
    ]


def test_failed_answer_resume_does_not_reingest(tmp_path: Path) -> None:
    """answer 阶段失败后，retry-failed 只补问题，不重新 add。

    输入:
        conversation_status: `failed_answer + ingested=true` 表示上次写入记忆已经完成，
            只是回答问题阶段失败。

    输出:
        runner 只回答未完成的 `q2`，不会再次调用 provider.add()。
    """

    dataset = _build_two_question_dataset()
    run_context = RunContext.create(
        run_id="failed-answer-resume",
        benchmark_name="fake",
        method_name="fake",
        model_name="fake",
        output_root=tmp_path,
        resume=True,
    )
    policy = PredictionRunPolicy(
        resume=True,
        retry_failed_conversations=True,
    )
    method_manifest = {"method_name": "fake"}
    _write_resume_manifest(
        dataset=dataset,
        run_context=run_context,
        policy=policy,
        method_manifest=method_manifest,
    )
    run_dir = tmp_path / "failed-answer-resume"
    atomic_write_json(
        run_dir / "checkpoints" / "conversation_status.json",
        {
            "conv-1": {
                "status": "failed_answer",
                "ingested": True,
                "stage": "answer",
            }
        },
    )
    atomic_write_jsonl(
        run_dir / "artifacts" / "method_predictions.jsonl",
        [
            {
                "question_id": "conv-1:q1",
                "conversation_id": "conv-1",
                "question_text": "问题 1",
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
        policy=policy,
        method_manifest=method_manifest,
        benchmark_variant="default",
        run_scope=RunScope.FULL,
        answer_reader=FrameworkAnswerReader(client=FakeAnswerLLMClient("new answer")),
    )

    assert provider.added_conversation_ids == []
    assert provider.retrieved_question_ids == ["conv-1:q2"]


def test_failed_ingest_retry_without_clean_support_fails_closed(
    tmp_path: Path,
) -> None:
    """ingest 阶段失败的 conversation 不能在脏状态上直接重跑。

    输入:
        conversation_status: `failed_ingest + ingested=false` 表示上次 add 可能只写入
            了部分第三方 memory state。

    输出:
        即使用户传了 retry_failed_conversations，runner 也拒绝在未知脏状态上重试。
    """

    dataset = _build_dataset()
    run_context = RunContext.create(
        run_id="failed-ingest-resume",
        benchmark_name="fake",
        method_name="fake",
        model_name="fake",
        output_root=tmp_path,
        resume=True,
    )
    policy = PredictionRunPolicy(
        resume=True,
        retry_failed_conversations=True,
    )
    method_manifest = {"method_name": "fake"}
    _write_resume_manifest(
        dataset=dataset,
        run_context=run_context,
        policy=policy,
        method_manifest=method_manifest,
    )
    run_dir = tmp_path / "failed-ingest-resume"
    atomic_write_json(
        run_dir / "checkpoints" / "conversation_status.json",
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
            policy=policy,
            method_manifest=method_manifest,
            benchmark_variant="default",
            run_scope=RunScope.FULL,
            answer_reader=FrameworkAnswerReader(
                client=FakeAnswerLLMClient("unused")
            ),
        )


def test_failed_ingest_retry_with_clean_support_reingests_conversation(
    tmp_path: Path,
) -> None:
    """内置 method 明确提供 clean retry 时，failed_ingest 可重新 add。

    输入:
        conversation_status: `conv-1` 上次在 ingest 阶段失败，method state 可能残留
            半写入数据。
        clean_failed_ingest_conversation: runner 调用的清理 hook，负责删除当前
            conversation 的脏 state。

    输出:
        runner 先调用 clean hook，再把 `conv-1` 重新纳入 add + answer 流程。
    """

    dataset = _build_dataset()
    run_context = RunContext.create(
        run_id="failed-ingest-clean-retry",
        benchmark_name="fake",
        method_name="fake",
        model_name="fake",
        output_root=tmp_path,
        resume=True,
    )
    policy = PredictionRunPolicy(
        resume=True,
        retry_failed_conversations=True,
    )
    method_manifest = {"method_name": "fake"}
    _write_resume_manifest(
        dataset=dataset,
        run_context=run_context,
        policy=policy,
        method_manifest=method_manifest,
    )
    run_dir = tmp_path / "failed-ingest-clean-retry"
    atomic_write_json(
        run_dir / "checkpoints" / "conversation_status.json",
        {
            "conv-1": {
                "status": "failed_ingest",
                "ingested": False,
                "stage": "ingest",
            }
        },
    )
    dirty_marker = run_dir / "method_state" / "conv-1" / "partial.txt"
    dirty_marker.parent.mkdir(parents=True)
    dirty_marker.write_text("partial memory state", encoding="utf-8")
    cleaned_conversations: list[str] = []

    observed_failed_states: list[dict[str, object]] = []

    def clean_failed_ingest_conversation(
        conversation: Conversation,
        failed_state: dict[str, object],
    ) -> None:
        """测试用 clean hook，模拟删除当前 conversation 的脏 method state。"""

        cleaned_conversations.append(conversation.conversation_id)
        observed_failed_states.append(failed_state)
        if dirty_marker.exists():
            dirty_marker.unlink()

    provider = RecordingMemoryProvider()
    run_predictions(
        dataset=dataset,
        system=provider,
        run_context=run_context,
        policy=policy,
        method_manifest=method_manifest,
        benchmark_variant="default",
        run_scope=RunScope.FULL,
        answer_reader=FrameworkAnswerReader(client=FakeAnswerLLMClient("answer")),
        clean_failed_ingest_conversation=clean_failed_ingest_conversation,
    )

    assert cleaned_conversations == ["conv-1"]
    assert observed_failed_states == [
        {
            "status": "failed_ingest",
            "ingested": False,
            "stage": "ingest",
        }
    ]
    assert "conv-1" in provider.added_conversation_ids
    assert not dirty_marker.exists()
    persisted_status = json.loads(
        (run_dir / "checkpoints" / "conversation_status.json").read_text(
            encoding="utf-8"
        )
    )
    assert persisted_status["conv-1"]["status"] == "completed"


@pytest.mark.parametrize(
    ("dataset", "method_manifest", "error_type", "error_pattern"),
    [
        (
            Dataset(dataset_name="invalid", conversations=[]),
            {"adapter": "recording-v1"},
            DatasetValidationError,
            "at least one conversation|at least 1 conversation|Conversation",
        ),
        (
            _build_dataset(),
            {"api_key": "sk-test"},
            ConfigurationError,
            "secret-like field|private",
        ),
    ],
)
def test_run_predictions_validates_before_creating_paths_or_logs(
    tmp_path: Path,
    dataset: Dataset,
    method_manifest: dict[str, object],
    error_type: type[Exception],
    error_pattern: str,
) -> None:
    """直接调用 run_predictions 的共享校验必须先于目录和日志副作用。"""

    with pytest.raises(error_type, match=error_pattern):
        run_predictions(
            dataset=dataset,
            system=RecordingPredictionSystem(),
            run_context=_create_provisional_context(tmp_path),
            policy=PredictionRunPolicy(max_workers=1),
            method_manifest=method_manifest,
            benchmark_variant="test_variant",
            run_scope=RunScope.FULL,
        )

    run_dir = tmp_path / "prediction-run"
    assert not run_dir.exists()


def test_public_manifest_allows_tokenizer_and_token_count_fields() -> None:
    """公开 manifest 可记录 tokenizer 身份和 token 数，不应误判为密钥。"""

    from memory_benchmark.runners import prediction as prediction_module

    prediction_module._validate_public_manifest(
        {
            "instrumentation": {
                "llm_tokenizer": "gpt-4o-mini",
                "embedding_tokenizer": "models/all-MiniLM-L6-v2",
                "input_tokens": 10,
                "output_tokens": 2,
                "token_count_strategy": "usage_or_tokenizer",
            }
        }
    )


@pytest.mark.parametrize(
    "secret_key",
    ["token", "api_token", "access_token", "auth_token", "bearer_token"],
)
def test_public_manifest_rejects_real_token_fields(secret_key: str) -> None:
    """公开 manifest 仍必须拒绝真实 API token 类字段。"""

    from memory_benchmark.runners import prediction as prediction_module

    with pytest.raises(ConfigurationError, match="secret-like field"):
        prediction_module._validate_public_manifest({"client": {secret_key: "sk-test"}})


def test_split_into_chunks_distributes_conversations_evenly() -> None:
    """conversation 应轮转分布到各 chunk，最后非满 chunk 自然处理剩余。"""

    from memory_benchmark.runners.prediction import _split_into_chunks
    from memory_benchmark.core import Conversation

    convs = [Conversation(conversation_id=f"c{i}", sessions=(), gold_answers={}) for i in range(10)]
    chunks = _split_into_chunks(convs, 4)
    assert len(chunks) == 4
    assert [len(c) for c in chunks] == [3, 3, 2, 2]
    all_ids = {conv.conversation_id for chunk in chunks for conv in chunk}
    assert all_ids == {f"c{i}" for i in range(10)}
    # 轮转分布验证
    assert [conv.conversation_id for conv in chunks[0]] == ["c0", "c4", "c8"]


def test_split_into_chunks_handles_fewer_than_num_chunks() -> None:
    """conversation 数少于 chunk 数时退回实际 conversation 数个 chunk。"""

    from memory_benchmark.runners.prediction import _split_into_chunks
    from memory_benchmark.core import Conversation

    convs = [Conversation(conversation_id=f"c{i}", sessions=(), gold_answers={}) for i in range(2)]
    chunks = _split_into_chunks(convs, 4)
    assert len(chunks) == 2
    assert [len(c) for c in chunks] == [1, 1]


def test_split_into_chunks_handles_single_conversation() -> None:
    """单个 conversation 产生单个 chunk。"""

    from memory_benchmark.runners.prediction import _split_into_chunks
    from memory_benchmark.core import Conversation

    convs = [Conversation(conversation_id="c0", sessions=(), gold_answers={})]
    chunks = _split_into_chunks(convs, 1)
    assert len(chunks) == 1
    assert len(chunks[0]) == 1


def test_experiment_paths_include_answer_prompt_artifact(
    tmp_path: Path,
) -> None:
    """answer-prompt runner 需要单独保存 method 生成的完整 prompt。"""

    from memory_benchmark.storage import ExperimentPaths

    paths = ExperimentPaths.create(tmp_path / "run")

    assert paths.answer_prompts_path.name == "answer_prompts.prediction.jsonl"
    assert paths.answer_prompts_path.parent == paths.artifacts_dir


def test_isolated_worker_pipeline_creates_per_worker_instances(
    tmp_path,
) -> None:
    """独立 instance 模式下每个 worker 应有自己的 method 实例。"""

    from memory_benchmark.runners.prediction import (
        PredictionRunPolicy,
        _build_prediction_work_plan,
        _run_isolated_worker_pipeline,
    )
    from memory_benchmark.methods.registry import MethodBuildContext
    from memory_benchmark.observability import ProgressReporter
    from memory_benchmark.storage import ExperimentPaths
    from memory_benchmark.utils.run_logger import RunLogger
    from memory_benchmark.core import Conversation, Question

    factory_calls: list[MethodBuildContext] = []

    class _FakeSystem:
        """独立 worker 测试用的假 method 实例。"""

        def __init__(self, ctx: MethodBuildContext):
            """记录工厂调用，验证每个 worker 创建了独立实例。"""

            factory_calls.append(ctx)

        def add(self, conversations):
            """空实现，只验证调用路径。"""

            pass

        def get_answer(self, question):
            """返回固定测试答案。"""

            from memory_benchmark.core import AnswerResult
            return AnswerResult(
                question_id=question.question_id,
                conversation_id=question.conversation_id,
                answer="test",
            )

    def fake_factory(ctx: MethodBuildContext):
        """假工厂，创建 _FakeSystem 实例。"""

        return _FakeSystem(ctx)

    convs = [
        Conversation(conversation_id=f"c{i}", sessions=(), gold_answers={f"c{i}_q0": None})
        for i in range(6)
    ]
    for conv in convs:
        conv.question_ids = [f"{conv.conversation_id}_q0"]

    selected_questions = {
        conv.conversation_id: [
            Question(
                question_id=f"{conv.conversation_id}_q0",
                conversation_id=conv.conversation_id,
                text="q?",
            )
        ]
        for conv in convs
    }

    paths = ExperimentPaths.create(tmp_path / "run")
    paths.method_state_dir.mkdir(parents=True, exist_ok=True)
    paths.method_predictions_path.parent.mkdir(parents=True, exist_ok=True)

    build_ctx = MethodBuildContext(
        config={},
        openai_settings=None,
        path_settings=None,
        storage_root=paths.method_state_dir,
    )
    policy = PredictionRunPolicy(max_workers=4)
    prediction_records: dict = {}
    conversation_status: dict = {}
    question_status: dict = {}
    question_order = [f"{c.conversation_id}_q0" for c in convs]
    work_plan = _build_prediction_work_plan(
        conversations=convs,
        selected_questions=selected_questions,
        conversation_status=conversation_status,
        prediction_records=prediction_records,
        policy=policy,
    )

    with ProgressReporter(paths.progress_path, enabled=False) as progress:
        progress.start_conversations(len(convs))
        progress.start_questions(len(question_order))
        _run_isolated_worker_pipeline(
            work_plan=work_plan,
            system_factory=fake_factory,
            build_context_template=build_ctx,
            policy=policy,
            paths=paths,
            progress=progress,
            logger=RunLogger(paths.logs_dir),
            efficiency_collector=None,
            efficiency_store=None,
            retrieval_observation_contract=None,
            prediction_records=prediction_records,
            conversation_status=conversation_status,
            question_status=question_status,
            question_order=question_order,
        )

    assert len(factory_calls) == 4
    storage_roots = {str(ctx.storage_root).rstrip("/") for ctx in factory_calls}
    assert len(storage_roots) == 4
    for idx in range(4):
        assert any(
            f"worker_{idx}" in root
            for root in storage_roots
        ), f"worker_{idx} not in {storage_roots}"
    assert len(prediction_records) == 6
    assert all(
        question_status[qid]["status"] == "completed"
        for qid in question_order
    )


def test_isolated_worker_restores_state_and_skips_completed_questions(
    tmp_path: Path,
) -> None:
    """isolated resume 应恢复已 add 的 conversation，并只回答缺失问题。"""

    dataset = _build_two_question_dataset()
    first_system = RecordingPredictionSystem()
    run_predictions(
        dataset=dataset,
        system=first_system,
        run_context=_create_context(tmp_path),
        policy=PredictionRunPolicy(max_workers=2),
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    run_dir = tmp_path / "prediction-run"
    predictions = read_jsonl(run_dir / "artifacts" / "method_predictions.jsonl")
    question_status = read_jsonl(run_dir / "checkpoints" / "question_status.jsonl")
    atomic_write_jsonl(
        run_dir / "artifacts" / "method_predictions.jsonl",
        [record for record in predictions if record["question_id"] == "conv-1:q1"],
    )
    atomic_write_jsonl(
        run_dir / "checkpoints" / "question_status.jsonl",
        [record for record in question_status if record["question_id"] == "conv-1:q1"],
    )

    from memory_benchmark.methods.registry import MethodBuildContext

    factory_contexts: list[MethodBuildContext] = []
    add_calls: list[str] = []
    answer_calls: list[str] = []

    class _ResumeAwareSystem(BaseMemorySystem):
        """记录 isolated worker 是否拿到已完成 conversation state。"""

        def __init__(self, context: MethodBuildContext):
            """保存工厂上下文，供断言 completed_conversations。"""

            factory_contexts.append(context)

        def add(self, conversations: list[Conversation]) -> AddResult:
            """记录不应发生的重复 add。"""

            add_calls.extend(
                conversation.conversation_id for conversation in conversations
            )
            return AddResult(
                conversation_ids=[
                    conversation.conversation_id for conversation in conversations
                ]
            )

        def get_answer(self, question: Question) -> AnswerResult:
            """记录实际恢复后回答的问题。"""

            answer_calls.append(question.question_id)
            return AnswerResult(
                question_id=question.question_id,
                conversation_id=question.conversation_id,
                answer=f"恢复回答:{question.text}",
            )

    def fake_factory(context: MethodBuildContext) -> BaseMemorySystem:
        """创建记录型 isolated worker system。"""

        return _ResumeAwareSystem(context)

    build_context = MethodBuildContext(
        config={},
        openai_settings=None,
        path_settings=None,
        storage_root=run_dir / "method_state",
    )
    summary = run_predictions(
        dataset=dataset,
        system=RecordingPredictionSystem(),
        run_context=_create_context(tmp_path, resume=True),
        policy=PredictionRunPolicy(max_workers=2, resume=True),
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
        system_factory=fake_factory,
        build_context_template=build_context,
        supports_shared_instance_parallelism=False,
    )

    assert add_calls == []
    assert answer_calls == ["conv-1:q2"]
    assert factory_contexts
    assert [
        conversation.conversation_id
        for context in factory_contexts
        for conversation in context.completed_conversations
    ] == ["conv-1"]
    assert summary.completed_questions == 2
    assert [
        row["question_id"]
        for row in read_jsonl(run_dir / "artifacts" / "method_predictions.jsonl")
    ] == ["conv-1:q1", "conv-1:q2"]


def test_isolated_worker_persists_conversation_efficiency_observation(
    tmp_path: Path,
) -> None:
    """isolated worker 应把 add 阶段 conversation efficiency 写入 artifact。"""

    from memory_benchmark.methods.registry import MethodBuildContext
    from memory_benchmark.observability.efficiency import (
        EfficiencyCollector,
        ModelDescriptor,
        RetrievalObservationContract,
    )

    class _EfficiencyAwareSystem(BaseMemorySystem):
        """在 question scope 内记录 answer latency 的 fake method。"""

        def __init__(self, context: MethodBuildContext) -> None:
            """保存 collector，模拟真实 adapter 通过 build context 获取观测器。"""

            self.collector = context.efficiency_collector

        def add(self, conversations: list[Conversation]) -> AddResult:
            """模拟一次完整 conversation 写入。"""

            return AddResult(
                conversation_ids=[
                    conversation.conversation_id for conversation in conversations
                ]
            )

        def get_answer(self, question: Question) -> AnswerResult:
            """记录 answer latency 并返回固定答案。"""

            assert self.collector is not None
            self.collector.record_answer_generation(latency_ms=1.0)
            return AnswerResult(
                question_id=question.question_id,
                conversation_id=question.conversation_id,
                answer=f"回答:{question.text}",
            )

    def fake_factory(context: MethodBuildContext) -> BaseMemorySystem:
        """为每个 isolated worker 构造带 collector 的 fake method。"""

        return _EfficiencyAwareSystem(context)

    context = _create_context(tmp_path)
    collector = EfficiencyCollector(run_id=context.run_id, enabled=True)

    run_predictions(
        dataset=_build_dataset(),
        system=RecordingPredictionSystem(),
        run_context=context,
        policy=PredictionRunPolicy(max_workers=2),
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
        efficiency_collector=collector,
        model_inventory=(
            ModelDescriptor(
                model_id="fake-answer",
                model_name="fake-answer",
                model_role="answer_llm",
                execution_mode="local",
            ),
        ),
        instrumentation_identity={"observer_version": "test-v1"},
        retrieval_observation_contract=RetrievalObservationContract(
            required_by_profile=False,
            supported_by_method=False,
            unsupported_reason="fake method does not expose retrieval latency",
        ),
        system_factory=fake_factory,
        build_context_template=MethodBuildContext(
            config={},
            openai_settings=None,
            path_settings=None,
            storage_root=context.run_dir / "method_state",
            efficiency_collector=collector,
        ),
        supports_shared_instance_parallelism=False,
    )

    observations = read_jsonl(
        context.artifacts_dir / "efficiency_observations.prediction.jsonl"
    )
    assert [
        observation["observation_type"]
        for observation in observations
        if observation["observation_type"] == "conversation_efficiency"
    ] == ["conversation_efficiency", "conversation_efficiency"]


def test_isolated_worker_resume_keeps_stable_worker_state_root(
    tmp_path: Path,
) -> None:
    """partial question resume 时同一 conversation 必须回到稳定 worker state 目录。

    这个测试模拟首轮四个 conversation 以两 worker 运行，其中 `conv-2` 按完整数据集
    顺序属于 `worker_1`。首轮完成 ingest 后只保留 `conv-2` 的第一题 prediction，
    resume 时 work plan 只剩 `conv-2`。正确行为是仍把它的 completed conversation
    state 挂到 `worker_1`，不能因为剩余列表重分块而变成 `worker_0`。
    """

    conversations: list[Conversation] = []
    for index in range(4):
        conversation_id = f"conv-{index + 1}"
        questions = [
            Question(
                question_id=f"{conversation_id}:q1",
                conversation_id=conversation_id,
                text=f"问题 {index + 1}-1",
            ),
            Question(
                question_id=f"{conversation_id}:q2",
                conversation_id=conversation_id,
                text=f"问题 {index + 1}-2",
            ),
        ]
        conversations.append(
            Conversation(
                conversation_id=conversation_id,
                sessions=[
                    Session(
                        session_id=f"{conversation_id}:s1",
                        turns=[
                            Turn(
                                turn_id=f"{conversation_id}:t1",
                                speaker="Speaker",
                                content=f"公开记忆 {index + 1}",
                            )
                        ],
                    )
                ],
                questions=questions,
                gold_answers={
                    question.question_id: GoldAnswerInfo(
                        question_id=question.question_id,
                        answer=f"标准答案 {question.question_id}",
                    )
                    for question in questions
                },
            )
        )
    dataset = Dataset(dataset_name="fake-conversation-qa", conversations=conversations)

    run_predictions(
        dataset=dataset,
        system=RecordingPredictionSystem(),
        run_context=_create_context(tmp_path),
        policy=PredictionRunPolicy(max_workers=2),
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
        system_factory=lambda context: RecordingPredictionSystem(),
        build_context_template=_make_build_context(tmp_path),
        supports_shared_instance_parallelism=False,
    )

    run_dir = tmp_path / "prediction-run"
    predictions = read_jsonl(run_dir / "artifacts" / "method_predictions.jsonl")
    atomic_write_jsonl(
        run_dir / "artifacts" / "method_predictions.jsonl",
        [record for record in predictions if record["question_id"] != "conv-2:q2"],
    )

    from memory_benchmark.methods.registry import MethodBuildContext

    resume_contexts: list[MethodBuildContext] = []

    class _ResumeStateProbe(RecordingPredictionSystem):
        """记录 resume 时 completed conversation 使用的 state root。"""

        def __init__(self, context: MethodBuildContext):
            """保存 isolated worker build context。"""

            super().__init__()
            resume_contexts.append(context)

    def fake_factory(context: MethodBuildContext) -> BaseMemorySystem:
        """创建会记录 build context 的 fake system。"""

        return _ResumeStateProbe(context)

    run_predictions(
        dataset=dataset,
        system=RecordingPredictionSystem(),
        run_context=_create_context(tmp_path, resume=True),
        policy=PredictionRunPolicy(max_workers=2, resume=True),
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
        system_factory=fake_factory,
        build_context_template=_make_build_context(tmp_path),
        supports_shared_instance_parallelism=False,
    )

    completed_contexts = [
        context
        for context in resume_contexts
        if any(
            conversation.conversation_id == "conv-2"
            for conversation in context.completed_conversations
        )
    ]
    assert len(completed_contexts) == 1
    assert completed_contexts[0].storage_root == run_dir / "method_state" / "worker_1"


def test_isolated_worker_marks_failed_conversation_and_continues_work(
    tmp_path: Path,
) -> None:
    """单个 conversation 失败后应标记 failed，但 worker 继续后续 conversation。"""

    from memory_benchmark.methods.registry import MethodBuildContext
    from memory_benchmark.observability import ProgressReporter
    from memory_benchmark.runners.prediction import (
        _build_prediction_work_plan,
        _run_isolated_worker_pipeline,
    )
    from memory_benchmark.storage import ExperimentPaths
    from memory_benchmark.utils.run_logger import RunLogger

    dataset = _build_numbered_dataset(4)
    calls: list[tuple[str, str, str]] = []
    calls_lock = threading.Lock()

    class _FailFastSystem(RecordingPredictionSystem):
        """按 worker 和 conversation 注入失败或等待的 fake system。"""

        def __init__(self, context: MethodBuildContext) -> None:
            """根据 storage_root 判断当前 worker id。"""

            super().__init__()
            self.worker_id = context.storage_root.name

        def add(self, conversations: list[Conversation]) -> AddResult:
            """worker_0 在第一个 conversation 失败，但之后仍应继续 conv-3。"""

            conversation_id = conversations[0].conversation_id
            with calls_lock:
                calls.append((self.worker_id, "add", conversation_id))
            if self.worker_id == "worker_0" and conversation_id == "conv-1":
                raise RuntimeError("boom from worker_0")
            if self.worker_id == "worker_1" and conversation_id == "conv-2":
                time.sleep(0.2)
            return AddResult(conversation_ids=[conversation_id])

        def get_answer(self, question: Question) -> AnswerResult:
            """记录 answer 调用，便于确认失败不会阻断其他 conversation。"""

            with calls_lock:
                calls.append((self.worker_id, "answer", question.conversation_id))
            return super().get_answer(question)

    def fake_factory(context: MethodBuildContext) -> BaseMemorySystem:
        """创建带失败注入的 isolated worker system。"""

        return _FailFastSystem(context)

    run_dir = tmp_path / "run"
    paths = ExperimentPaths.create(run_dir)
    conversation_status: dict[str, dict[str, str]] = {}
    work_plan = _build_prediction_work_plan(
        conversations=list(dataset.conversations),
        selected_questions={
            conversation.conversation_id: list(conversation.questions)
            for conversation in dataset.conversations
        },
        conversation_status={},
        prediction_records={},
        policy=PredictionRunPolicy(max_workers=2),
    )

    with ProgressReporter(paths.progress_path, enabled=False) as progress:
        progress.start_conversations(len(dataset.conversations))
        progress.start_questions(4)
        prediction_records: dict[str, dict[str, object]] = {}
        question_status: dict[str, dict[str, object]] = {}
        _run_isolated_worker_pipeline(
            work_plan=work_plan,
            system_factory=fake_factory,
            build_context_template=MethodBuildContext(
                config={},
                openai_settings=None,
                path_settings=None,
                storage_root=paths.method_state_dir,
            ),
            policy=PredictionRunPolicy(max_workers=2),
            paths=paths,
            progress=progress,
            logger=RunLogger(paths.logs_dir),
            efficiency_collector=None,
            efficiency_store=None,
            retrieval_observation_contract=None,
            prediction_records=prediction_records,
            conversation_status=conversation_status,
            question_status=question_status,
            question_order=[f"conv-{index}:q1" for index in range(1, 5)],
        )

    assert ("worker_0", "add", "conv-3") in calls
    assert ("worker_1", "add", "conv-4") in calls
    assert conversation_status["conv-1"]["status"] == "failed_ingest"
    assert conversation_status["conv-1"]["stage"] == "isolated_worker"
    assert conversation_status["conv-1"]["error_type"] == "RuntimeError"
    assert conversation_status["conv-1"]["worker_idx"] == 0
    assert conversation_status["conv-2"]["status"] == "completed"
    assert conversation_status["conv-3"]["status"] == "completed"
    assert conversation_status["conv-4"]["status"] == "completed"
    assert set(prediction_records) == {"conv-2:q1", "conv-3:q1", "conv-4:q1"}
    persisted_status = json.loads(paths.conversation_status_path.read_text())
    assert persisted_status["conv-1"]["status"] == "failed_ingest"
    assert persisted_status["conv-3"]["status"] == "completed"
    events = read_jsonl(paths.logs_dir / "events.jsonl")
    failure_events = [
        event for event in events if event["event"] == "conversation_failed_isolated"
    ]
    assert failure_events
    assert failure_events[0]["payload"]["worker_idx"] == 0
    assert failure_events[0]["payload"]["conversation_id"] == "conv-1"
    assert failure_events[0]["payload"]["error_type"] == "RuntimeError"
    assert "boom from worker_0" in failure_events[0]["payload"]["traceback"]


def test_isolated_worker_stops_after_consecutive_failure_threshold(
    tmp_path: Path,
) -> None:
    """连续失败达到阈值后，应停止后续 conversation，避免批量空烧。"""

    from memory_benchmark.methods.registry import MethodBuildContext
    from memory_benchmark.observability import ProgressReporter
    from memory_benchmark.runners.prediction import (
        _build_prediction_work_plan,
        _run_isolated_worker_pipeline,
    )
    from memory_benchmark.storage import ExperimentPaths
    from memory_benchmark.utils.run_logger import RunLogger

    dataset = _build_numbered_dataset(3)
    calls: list[str] = []

    class _AlwaysFailFirstTwoSystem(RecordingPredictionSystem):
        """前两个 conversation 失败，第三个不应被尝试。"""

        def add(self, conversations: list[Conversation]) -> AddResult:
            """记录 add，并让 conv-1/conv-2 失败。"""

            conversation_id = conversations[0].conversation_id
            calls.append(conversation_id)
            if conversation_id in {"conv-1", "conv-2"}:
                raise RuntimeError(f"boom {conversation_id}")
            return AddResult(conversation_ids=[conversation_id])

    def fake_factory(context: MethodBuildContext) -> BaseMemorySystem:
        """创建会连续失败的 fake system。"""

        return _AlwaysFailFirstTwoSystem()

    run_dir = tmp_path / "run"
    paths = ExperimentPaths.create(run_dir)
    conversation_status: dict[str, dict[str, object]] = {}
    work_plan = _build_prediction_work_plan(
        conversations=list(dataset.conversations),
        selected_questions={
            conversation.conversation_id: list(conversation.questions)
            for conversation in dataset.conversations
        },
        conversation_status={},
        prediction_records={},
        policy=PredictionRunPolicy(max_workers=1, max_consecutive_failures=2),
    )

    with ProgressReporter(paths.progress_path, enabled=False) as progress:
        progress.start_conversations(len(dataset.conversations))
        progress.start_questions(3)
        _run_isolated_worker_pipeline(
            work_plan=work_plan,
            system_factory=fake_factory,
            build_context_template=MethodBuildContext(
                config={},
                openai_settings=None,
                path_settings=None,
                storage_root=paths.method_state_dir,
            ),
            policy=PredictionRunPolicy(max_workers=1, max_consecutive_failures=2),
            paths=paths,
            progress=progress,
            logger=RunLogger(paths.logs_dir),
            efficiency_collector=None,
            efficiency_store=None,
            retrieval_observation_contract=None,
            prediction_records={},
            conversation_status=conversation_status,
            question_status={},
            question_order=[f"conv-{index}:q1" for index in range(1, 4)],
        )

    assert calls == ["conv-1", "conv-2"]
    assert conversation_status["conv-1"]["status"] == "failed_ingest"
    assert conversation_status["conv-2"]["status"] == "failed_ingest"
    assert "conv-3" not in conversation_status


def test_registered_isolated_prediction_does_not_construct_root_system(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """registered isolated path 不应构造顶层 method instance 产生副作用。"""

    from memory_benchmark.benchmark_adapters import PreparedBenchmarkRun
    from memory_benchmark.cli import run_prediction as run_prediction_module
    from memory_benchmark.core import MethodCapability, TaskFamily
    from memory_benchmark.methods.registry import MethodBuildContext, MethodRegistration

    class _FakeConfig:
        """registered prediction 测试用最小 method config。"""

        profile_name = "smoke"
        max_workers = 2

        def to_manifest(self) -> dict[str, object]:
            """返回公开配置快照。"""

            return {"profile_name": self.profile_name, "max_workers": self.max_workers}

    class _SideEffectSystem(RecordingPredictionSystem):
        """构造时写 marker，用于检测是否创建了根实例。"""

        def __init__(self, context: MethodBuildContext) -> None:
            """在当前 storage_root 写入构造 marker。"""

            super().__init__()
            context.storage_root.mkdir(parents=True, exist_ok=True)
            (context.storage_root / "constructed.txt").write_text(
                context.storage_root.name,
                encoding="utf-8",
            )

    def fake_factory(context: MethodBuildContext) -> BaseMemorySystem:
        """创建带构造副作用的 fake system。"""

        return _SideEffectSystem(context)

    dataset = _build_numbered_dataset(2)
    benchmark_registration = SimpleNamespace(
        name="fake-benchmark",
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        default_variant="default",
        variant_names=lambda: ("default",),
        prepare=lambda project_root, request: PreparedBenchmarkRun(
            variant="default",
            run_scope=request.run_scope,
            dataset=dataset,
            source_relative_paths=(),
        ),
        prediction_enabled=True,
    )
    method_registration = MethodRegistration(
        name="fake-method",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        profile_sections=(("smoke", "smoke"),),
        profile_relative_path=Path("configs/methods/fake.toml"),
        config_type=_FakeConfig,
        requires_api=False,
        system_factory=fake_factory,
        source_identity_factory=lambda path_settings: {"source_sha256": "fake"},
        model_name_getter=lambda config: "fake-model",
        max_workers_getter=lambda config: config.max_workers,
        display_name="FakeMethod",
        supports_shared_instance_parallelism=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_path_settings",
        lambda project_root: SimpleNamespace(
            project_root=tmp_path,
            outputs_root=tmp_path / "outputs",
        ),
    )
    monkeypatch.setattr(
        run_prediction_module,
        "get_benchmark_registration",
        lambda benchmark_name: benchmark_registration,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "get_method_registration",
        lambda method_name: method_registration,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_method_profile",
        lambda **kwargs: _FakeConfig(),
    )

    run_prediction_module.run_registered_conversation_qa_prediction(
        project_root=tmp_path,
        method_name="fake-method",
        benchmark_name="fake-benchmark",
        profile_name="smoke",
        run_id="isolated-root-side-effect",
        enable_efficiency_observability=False,
    )

    state_root = tmp_path / "outputs" / "isolated-root-side-effect" / "method_state"
    assert not (state_root / "constructed.txt").exists()
    assert (state_root / "worker_0" / "constructed.txt").is_file()
    assert (state_root / "worker_1" / "constructed.txt").is_file()


def test_isolated_worker_rejects_turn_checkpoint_resume(
    tmp_path: Path,
) -> None:
    """存在 turn-level checkpoint 时 isolated worker 应 fail closed。"""

    dataset = _build_three_turn_dataset()
    first_system = ResumablePredictionSystem()
    run_predictions(
        dataset=dataset,
        system=first_system,
        run_context=_create_context(tmp_path),
        policy=PredictionRunPolicy(max_workers=2),
        method_manifest={"adapter": "resumable-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
    )

    from memory_benchmark.methods.registry import MethodBuildContext

    def fake_factory(context: MethodBuildContext) -> BaseMemorySystem:
        """若 isolated checkpoint 保护失效，本工厂会创建普通记录系统。"""

        return RecordingPredictionSystem()

    run_dir = tmp_path / "prediction-run"
    with pytest.raises(ConfigurationError, match="turn-level ingest checkpoints"):
        run_predictions(
            dataset=dataset,
            system=RecordingPredictionSystem(),
            run_context=_create_context(tmp_path, resume=True),
            policy=PredictionRunPolicy(max_workers=2, resume=True),
            method_manifest={"adapter": "resumable-v1"},
            benchmark_variant="test_variant",
            run_scope=RunScope.FULL,
            system_factory=fake_factory,
            build_context_template=MethodBuildContext(
                config={},
                openai_settings=None,
                path_settings=None,
                storage_root=run_dir / "method_state",
            ),
            supports_shared_instance_parallelism=False,
        )


def test_build_conversation_prompts_extracts_system_prompt() -> None:
    """_build_conversation_prompts 从 metadata 提取 system_prompt 到按 conversation 去重的 dict。"""

    from memory_benchmark.runners.prediction import (
        _build_conversation_prompts,
    )

    records = {
        "q-0": {
            "question_id": "q-0",
            "conversation_id": "conv-a",
            "metadata": {"system_prompt": "You are a helpful assistant.", "method": "test"},
        },
        "q-1": {
            "question_id": "q-1",
            "conversation_id": "conv-a",
            "metadata": {"system_prompt": "You are a helpful assistant.", "method": "test"},
        },
        "q-2": {
            "question_id": "q-2",
            "conversation_id": "conv-b",
            "metadata": {"method": "test"},
        },
    }
    prompts = _build_conversation_prompts(records)
    assert prompts == {"conv-a": {"system_prompt": "You are a helpful assistant."}}


def test_strip_conversation_metadata_removes_system_prompt() -> None:
    """_strip_conversation_metadata 从 metadata 中移除 system_prompt。"""

    from memory_benchmark.runners.prediction import (
        _strip_conversation_metadata,
    )

    records = {
        "q-0": {
            "question_id": "q-0",
            "conversation_id": "conv-a",
            "metadata": {"system_prompt": "You are helpful.", "method": "test"},
        },
    }
    _strip_conversation_metadata(records)
    assert "system_prompt" not in records["q-0"]["metadata"]
    assert records["q-0"]["metadata"] == {"method": "test"}


def test_conversation_prompts_empty_when_no_matching_keys() -> None:
    """无 conversation 级 metadata 时 _build_conversation_prompts 返回空 dict。"""

    from memory_benchmark.runners.prediction import (
        _build_conversation_prompts,
    )

    records = {
        "q-0": {
            "question_id": "q-0",
            "conversation_id": "conv-a",
            "metadata": {"method": "test"},
        },
    }
    assert _build_conversation_prompts(records) == {}

def test_merge_session_report_records_replaces_same_conversation() -> None:
    """retry 重新 ingest 时，同一 conversation 的 session report 必须整体替换。"""

    from memory_benchmark.runners.prediction import _merge_session_report_records

    existing = [
        {"conversation_id": "conv-1", "memories": ["old-a"]},
        {"conversation_id": "conv-2", "memories": ["keep"]},
    ]
    merged = _merge_session_report_records(
        existing=existing,
        conversation_id="conv-1",
        new_reports=(
            {"conversation_id": "conv-1", "memories": ["new-a"]},
            {"conversation_id": "conv-1", "memories": ["new-b"]},
        ),
    )
    assert [record["memories"] for record in merged] == [["keep"], ["new-a"], ["new-b"]]
