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

import pytest

from memory_benchmark.core import (
    AddResult,
    AnswerResult,
    ConfigurationError,
    Conversation,
    Dataset,
    DatasetValidationError,
    GoldAnswerInfo,
    Question,
    Session,
    Turn,
)
from memory_benchmark.benchmark_adapters.contracts import RunScope
from memory_benchmark.core.interfaces import BaseMemorySystem, BaseResumableMemorySystem
from memory_benchmark.observability import RunContext
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
    dataset = _build_dataset()
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
    dataset = _build_dataset()
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
        "budget_exhausted": True,
    }
    summary_payload = json.loads(
        (tmp_path / "prediction-run" / "summaries" / "summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary_payload["metadata"]["run_control"] == {
        "max_new_conversations": 2,
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
