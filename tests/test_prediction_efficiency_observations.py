"""Prediction manifest 中效率观测身份和 resume 兼容性测试。"""

from __future__ import annotations

import json
import threading
import time

import pytest

from memory_benchmark.benchmark_adapters.contracts import RunScope
from memory_benchmark.core import (
    AddResult,
    AnswerResult,
    ConfigurationError,
    Conversation,
    Question,
)
from memory_benchmark.core.interfaces import BaseMemorySystem
from memory_benchmark.observability import RunContext
from memory_benchmark.observability.efficiency import (
    ConversationEfficiencyObservation,
    EfficiencyCollector,
    EfficiencyArtifactStore,
    ModelDescriptor,
    QuestionEfficiencyObservation,
    RetrievalObservationContract,
)
from memory_benchmark.runners import prediction as prediction_module
from memory_benchmark.runners.prediction import PredictionRunPolicy, run_predictions
from memory_benchmark.storage import ExperimentPaths, atomic_write_json
from tests.test_prediction_runner import _build_dataset


def _context(tmp_path, *, resume: bool) -> RunContext:
    """构造不创建目录的 prediction 上下文。"""

    return RunContext.create(
        run_id="efficiency-run",
        benchmark_name="fake-conversation-qa",
        method_name="recording",
        model_name="gpt-4o-mini",
        output_root=tmp_path,
        resume=resume,
        ensure_directories=False,
    )


def _inventory(model_name: str = "gpt-4o-mini") -> tuple[ModelDescriptor, ...]:
    """构造测试用 answer LLM 模型清单。"""

    return (
        ModelDescriptor(
            model_id="answer-llm",
            model_name=model_name,
            model_role="answer_llm",
            execution_mode="api",
            tokenizer_name=model_name,
        ),
    )


def _build_manifest(
    tmp_path,
    *,
    model_inventory: tuple[ModelDescriptor, ...],
    instrumentation_identity: dict[str, object],
) -> dict[str, object]:
    """通过真实 helper 构造启用效率观测的 manifest。"""

    _, manifest = prediction_module._build_prediction_resume_artifacts(
        dataset=_build_dataset(),
        run_context=_context(tmp_path, resume=False),
        policy=PredictionRunPolicy(max_workers=1),
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
        source_paths=(),
        efficiency_collector=EfficiencyCollector(
            run_id="efficiency-run",
            enabled=True,
        ),
        model_inventory=model_inventory,
        instrumentation_identity=instrumentation_identity,
        retrieval_observation_contract=RetrievalObservationContract(
            required_by_profile=True,
            supported_by_method=True,
        ),
    )
    return manifest


class _ObservedFakeMethod(BaseMemorySystem):
    """使用真实 collector API 上报精确 question 边界的无网络 fake method。"""

    def __init__(
        self,
        collector: EfficiencyCollector,
        *,
        report_retrieval: bool = True,
    ) -> None:
        """保存共享 collector，并初始化线程安全调用记录。"""

        self.collector = collector
        self.report_retrieval = report_retrieval
        self.added_conversation_ids: list[str] = []
        self.answered_question_ids: list[str] = []
        self._lock = threading.Lock()

    def add(self, conversations: list[Conversation]) -> AddResult:
        """模拟一次可并发的记忆构建，并返回 conversation id。"""

        conversation_id = conversations[0].conversation_id
        with self._lock:
            self.added_conversation_ids.append(conversation_id)
        time.sleep(0.005)
        return AddResult(conversation_ids=[conversation_id])

    def get_answer(self, question: Question) -> AnswerResult:
        """上报可控的 retrieval/answer 观测，并返回确定性答案。"""

        with self._lock:
            self.answered_question_ids.append(question.question_id)
        if self.report_retrieval:
            suffix = int(question.conversation_id.rsplit("-", 1)[1])
            self.collector.record_retrieval_result(
                latency_ms=float(suffix),
                injected_memory_context_tokens=suffix * 10,
            )
        self.collector.record_answer_generation(latency_ms=2.5)
        return AnswerResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer=f"answer:{question.question_id}",
        )


def _run_with_efficiency(
    tmp_path,
    *,
    system: BaseMemorySystem,
    collector: EfficiencyCollector,
    resume: bool = False,
    max_workers: int = 2,
    retrieval_observation_contract: RetrievalObservationContract | None = None,
) -> None:
    """通过真实通用 runner 执行启用 efficiency observation 的最小运行。"""

    run_predictions(
        dataset=_build_dataset(),
        system=system,
        run_context=_context(tmp_path, resume=resume),
        policy=PredictionRunPolicy(
            max_workers=max_workers,
            resume=resume,
            progress_enabled=False,
        ),
        method_manifest={"adapter": "observed-fake-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
        efficiency_collector=collector,
        model_inventory=_inventory(),
        instrumentation_identity={
            "collector_schema": 1,
            "wrapper_sha256": "observed-fake",
        },
        retrieval_observation_contract=(
            retrieval_observation_contract
            or RetrievalObservationContract(
                required_by_profile=True,
                supported_by_method=True,
            )
        ),
    )


def test_prediction_manifest_records_enabled_observability_identity(tmp_path) -> None:
    """启用观测时模型清单和插桩身份必须进入不可变 manifest。"""

    manifest = _build_manifest(
        tmp_path,
        model_inventory=_inventory(),
        instrumentation_identity={
            "collector_schema": 1,
            "wrapper_sha256": "abc123",
        },
    )

    assert manifest["efficiency_observability"] == {
        "enabled": True,
        "model_inventory": [descriptor.to_dict() for descriptor in _inventory()],
        "instrumentation_identity": {
            "collector_schema": 1,
            "wrapper_sha256": "abc123",
        },
        "retrieval_observation_contract": {
            "required_by_profile": True,
            "supported_by_method": True,
            "unsupported_reason": None,
        },
    }


def test_prediction_manifest_omits_observability_when_disabled(tmp_path) -> None:
    """关闭观测时保持旧 schema v2 manifest，避免破坏已有 run 的 resume。"""

    _, manifest = prediction_module._build_prediction_resume_artifacts(
        dataset=_build_dataset(),
        run_context=_context(tmp_path, resume=False),
        policy=PredictionRunPolicy(max_workers=1),
        method_manifest={"adapter": "recording-v1"},
        benchmark_variant="test_variant",
        run_scope=RunScope.FULL,
        source_paths=(),
    )

    assert "efficiency_observability" not in manifest


def test_enabled_observability_requires_explicit_retrieval_contract(
    tmp_path,
) -> None:
    """启用观测时必须显式声明 retrieval 的 profile 要求和 method 能力。"""

    with pytest.raises(ConfigurationError, match="retrieval observation contract"):
        prediction_module._build_prediction_resume_artifacts(
            dataset=_build_dataset(),
            run_context=_context(tmp_path, resume=False),
            policy=PredictionRunPolicy(max_workers=1),
            method_manifest={"adapter": "recording-v1"},
            benchmark_variant="test_variant",
            run_scope=RunScope.FULL,
            source_paths=(),
            efficiency_collector=EfficiencyCollector(
                run_id="efficiency-run",
                enabled=True,
            ),
            model_inventory=_inventory(),
            instrumentation_identity={
                "collector_schema": 1,
                "wrapper_sha256": "abc123",
            },
        )


@pytest.mark.parametrize(
    ("changed_inventory", "changed_instrumentation"),
    [
        (_inventory("different-model"), {"collector_schema": 1, "wrapper_sha256": "abc123"}),
        (_inventory(), {"collector_schema": 1, "wrapper_sha256": "changed"}),
    ],
)
def test_preflight_rejects_changed_observability_identity_without_writes(
    tmp_path,
    changed_inventory,
    changed_instrumentation,
) -> None:
    """模型或插桩身份变化必须在 resume preflight 阶段拒绝且不产生新文件。"""

    run_context = _context(tmp_path, resume=True)
    original_manifest = _build_manifest(
        tmp_path,
        model_inventory=_inventory(),
        instrumentation_identity={
            "collector_schema": 1,
            "wrapper_sha256": "abc123",
        },
    )
    run_context.run_dir.mkdir(parents=True)
    atomic_write_json(run_context.run_dir / "manifest.json", original_manifest)

    before = sorted(path.name for path in run_context.run_dir.iterdir())
    with pytest.raises(ConfigurationError, match="Resume manifest mismatch"):
        prediction_module._preflight_prediction_run(
            dataset=_build_dataset(),
            run_context=run_context,
            policy=PredictionRunPolicy(max_workers=1, resume=True),
            method_manifest={"adapter": "recording-v1"},
            benchmark_variant="test_variant",
            run_scope=RunScope.FULL,
            source_paths=(),
            efficiency_collector=EfficiencyCollector(
                run_id="efficiency-run",
                enabled=True,
            ),
            model_inventory=changed_inventory,
            instrumentation_identity=changed_instrumentation,
            retrieval_observation_contract=RetrievalObservationContract(
                required_by_profile=True,
                supported_by_method=True,
            ),
        )

    assert sorted(path.name for path in run_context.run_dir.iterdir()) == before
    assert json.loads(
        (run_context.run_dir / "manifest.json").read_text(encoding="utf-8")
    ) == original_manifest


def test_runner_records_isolated_build_and_question_observations_concurrently(
    tmp_path,
) -> None:
    """并发 conversation 必须各自产生一条 build 和一条 question observation。"""

    collector = EfficiencyCollector(run_id="efficiency-run", enabled=True)
    system = _ObservedFakeMethod(collector)

    _run_with_efficiency(
        tmp_path,
        system=system,
        collector=collector,
        max_workers=2,
    )

    observations = EfficiencyArtifactStore.for_prediction(
        ExperimentPaths(run_dir=tmp_path / "efficiency-run")
    ).read_observations()
    build_records = [
        record
        for record in observations
        if isinstance(record, ConversationEfficiencyObservation)
    ]
    question_records = [
        record
        for record in observations
        if isinstance(record, QuestionEfficiencyObservation)
    ]

    assert {record.conversation_id for record in build_records} == {
        "conv-1",
        "conv-2",
    }
    assert all(record.memory_build_total_latency_ms > 0 for record in build_records)
    assert {
        (
            record.conversation_id,
            record.question_id,
            record.retrieval_latency_ms,
            record.injected_memory_context_tokens,
            record.answer_generation_latency_ms,
        )
        for record in question_records
    } == {
        ("conv-1", "conv-1:q1", 1.0, 10, 2.5),
        ("conv-2", "conv-2:q1", 2.0, 20, 2.5),
    }


def test_runner_marks_missing_separable_retrieval_as_unsupported(tmp_path) -> None:
    """method 未上报 retrieval 时，runner 应显式写 unsupported 而不是伪造 0。"""

    collector = EfficiencyCollector(run_id="efficiency-run", enabled=True)
    system = _ObservedFakeMethod(collector, report_retrieval=False)

    _run_with_efficiency(
        tmp_path,
        system=system,
        collector=collector,
        max_workers=1,
        retrieval_observation_contract=RetrievalObservationContract(
            required_by_profile=False,
            supported_by_method=False,
            unsupported_reason=(
                "method does not expose a separable retrieval boundary"
            ),
        ),
    )

    observations = EfficiencyArtifactStore.for_prediction(
        ExperimentPaths(run_dir=tmp_path / "efficiency-run")
    ).read_observations()
    question_records = [
        record
        for record in observations
        if isinstance(record, QuestionEfficiencyObservation)
    ]
    assert len(question_records) == 2
    assert all(record.retrieval_latency_ms is None for record in question_records)
    assert all(record.injected_memory_context_tokens is None for record in question_records)
    assert {
        record.unsupported_reason for record in question_records
    } == {"method does not expose a separable retrieval boundary"}


def test_runner_rejects_missing_retrieval_from_declared_supported_method(
    tmp_path,
) -> None:
    """声明支持精确 retrieval 的 adapter 漏报时必须失败，不能自动降级。"""

    collector = EfficiencyCollector(run_id="efficiency-run", enabled=True)
    system = _ObservedFakeMethod(collector, report_retrieval=False)

    with pytest.raises(
        ConfigurationError,
        match="question scope requires retrieval latency",
    ):
        _run_with_efficiency(
            tmp_path,
            system=system,
            collector=collector,
            max_workers=1,
            retrieval_observation_contract=RetrievalObservationContract(
                required_by_profile=False,
                supported_by_method=True,
            ),
        )


def test_completed_resume_does_not_duplicate_efficiency_observations(
    tmp_path,
) -> None:
    """完整运行后的 resume 必须跳过 method 调用并保持 observation id 唯一。"""

    first_collector = EfficiencyCollector(run_id="efficiency-run", enabled=True)
    _run_with_efficiency(
        tmp_path,
        system=_ObservedFakeMethod(first_collector),
        collector=first_collector,
        max_workers=2,
    )
    store = EfficiencyArtifactStore.for_prediction(
        ExperimentPaths(run_dir=tmp_path / "efficiency-run")
    )
    before = [record.to_dict() for record in store.read_observations()]

    resumed_collector = EfficiencyCollector(
        run_id="efficiency-run",
        enabled=True,
    )
    resumed_system = _ObservedFakeMethod(resumed_collector)
    _run_with_efficiency(
        tmp_path,
        system=resumed_system,
        collector=resumed_collector,
        resume=True,
        max_workers=2,
    )

    after = [record.to_dict() for record in store.read_observations()]
    assert resumed_system.added_conversation_ids == []
    assert resumed_system.answered_question_ids == []
    assert after == before
    assert len({record["observation_id"] for record in after}) == len(after)
