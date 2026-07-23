"""测试 SimpleMem 通过统一 registry 进入 v3 prediction runner。"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from memory_benchmark.benchmark_adapters import (
    BenchmarkLoadRequest,
    PreparedBenchmarkRun,
    RunScope,
)
from memory_benchmark.cli import run_prediction as run_prediction_module
from memory_benchmark.config import AnswerLLMSettings, OpenAISettings, load_path_settings
from memory_benchmark.core import (
    Conversation,
    Dataset,
    GoldAnswerInfo,
    MethodCapability,
    PromptMessage,
    Question,
    Session,
    TaskFamily,
    Turn,
)
from memory_benchmark.core.provider_protocol import (
    EvidenceAssertion,
    IngestResult,
    IngestUnit,
    MemoryProvider,
    RetrievalQuery,
    RetrievalEvidence,
    RetrievalResult,
    RetrievedItem,
    TurnEvent,
    UnitRef,
)
from memory_benchmark.methods import registry as method_registry_module
from memory_benchmark.storage import read_jsonl


pytestmark = pytest.mark.unit
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeSimpleMemForRegisteredPrediction(MemoryProvider):
    """替代真实 SimpleMem adapter，避免模型加载和真实 API。"""

    consume_granularity = "turn"
    session_memory_report = False
    provenance_granularity = "none"
    instances: list["FakeSimpleMemForRegisteredPrediction"] = []

    def __init__(self, **kwargs) -> None:
        """记录 registry factory 传入的构造参数。"""

        self.kwargs = kwargs
        self.ingested_turns: list[TurnEvent] = []
        self.finalized: list[str] = []
        self.retrievals: list[RetrievalQuery] = []
        self.instances.append(self)

    def ingest(self, unit: IngestUnit) -> IngestResult | None:
        """记录 v3 turn ingest。"""

        assert isinstance(unit, TurnEvent)
        self.ingested_turns.append(unit)
        return IngestResult(unit_ref=UnitRef(unit.isolation_key))

    def end_conversation(self, ref: UnitRef) -> None:
        """记录 conversation finalize 信号。"""

        self.finalized.append(ref.isolation_key)
        return None

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """返回固定 native prompt，覆盖 retrieve-first 主路径。"""

        self.retrievals.append(query)
        return RetrievalResult(
            formatted_memory="[2026-01-01T00:00:00] fake simplemem memory",
            prompt_messages=(
                PromptMessage(
                    role="system",
                    content="You are a professional Q&A assistant.",
                ),
                PromptMessage(
                    role="user",
                    content=f"Question: {query.query_text}\nContext: fake memory",
                ),
            ),
            items=(
                RetrievedItem(
                    item_id="fake-entry-1",
                    content="fake simplemem memory",
                    score=None,
                    timestamp="2026-01-01T00:00:00",
                ),
            ),
            metadata={
                "method": "simplemem",
                "prompt_track": "native",
                "provenance_granularity": "none",
            },
            evidence=RetrievalEvidence(
                semantic_provenance=EvidenceAssertion(
                    status="n_a",
                    reason_code="simplemem_synthesized_memory_not_turn_exact",
                    reason="Fake mirrors the SimpleMem synthesized-memory contract.",
                ),
                provenance_granularity="none",
                stable_ranking=EvidenceAssertion(
                    status="pending",
                    reason_code="simplemem_parallel_merge_has_no_stable_global_rank",
                    reason="Fake mirrors the SimpleMem product-order contract.",
                ),
            ),
        )


def test_simplemem_registered_prediction_runs_locomo_and_longmemeval_fake_smoke(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SimpleMem 应在 LoCoMo 与 LongMemEval fake smoke 中写出 v3 artifacts。"""

    FakeSimpleMemForRegisteredPrediction.instances.clear()
    real_paths = load_path_settings(PROJECT_ROOT)
    test_paths = replace(real_paths, outputs_root=tmp_path / "outputs")
    monkeypatch.setattr(
        run_prediction_module,
        "load_path_settings",
        lambda project_root: test_paths,
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_openai_settings",
        lambda project_root: OpenAISettings(
            api_key="sk-test",
            base_url="https://example.invalid/v1",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "OpenAICompatibleAnswerLLMClient",
        FakeAnswerClient,
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "get_benchmark_registration",
        lambda benchmark_name: _fake_registration(benchmark_name),
    )
    monkeypatch.setattr(
        method_registry_module,
        "SimpleMem",
        FakeSimpleMemForRegisteredPrediction,
    )

    for benchmark_name in ("locomo", "longmemeval"):
        result = run_prediction_module.run_registered_conversation_qa_prediction(
            project_root=PROJECT_ROOT,
            method_name="simplemem",
            benchmark_name=benchmark_name,
            profile_name="smoke",
            run_id=f"simplemem-{benchmark_name}-fake-smoke",
            confirm_api=True,
            smoke_turn_limit=2,
            smoke_conversation_limit=1,
            enable_efficiency_observability=False,
        )

        assert result.benchmark == benchmark_name
        assert result.runs[0].run_id == f"simplemem-{benchmark_name}-fake-smoke"

    assert len(FakeSimpleMemForRegisteredPrediction.instances) == 2
    for benchmark_name, instance in zip(
        ("locomo", "longmemeval"),
        FakeSimpleMemForRegisteredPrediction.instances,
        strict=True,
    ):
        assert instance.kwargs["config"].profile_name == "smoke"
        assert len(instance.ingested_turns) == 2
        assert len(instance.finalized) == 1
        assert [query.query_text for query in instance.retrievals] == [
            f"What should {benchmark_name} remember?"
        ]

        run_dir = tmp_path / "outputs" / f"simplemem-{benchmark_name}-fake-smoke"
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        predictions = read_jsonl(run_dir / "artifacts" / "method_predictions.jsonl")
        prompts = read_jsonl(run_dir / "artifacts" / "answer_prompts.prediction.jsonl")
        public_questions = read_jsonl(run_dir / "artifacts" / "public_questions.jsonl")

        assert manifest["method_name"] == "SimpleMem"
        assert manifest["method"]["protocol_version"] == "v3"
        assert manifest["method"]["provenance_granularity"] == "none"
        assert manifest["method"]["retrieval_evidence_contract_version"] == "v1"
        assert manifest["method"]["prompt_track"] == "native"
        assert manifest["method"]["config"]["profile_name"] == "smoke"
        assert predictions[0]["answer"] == "framework fake answer"
        assert prompts[0]["metadata"]["prompt_track"] == "native"
        assert prompts[0]["formatted_memory"] == (
            "[2026-01-01T00:00:00] fake simplemem memory"
        )
        assert prompts[0]["retrieved_items"][0]["item_id"] == "fake-entry-1"
        assert public_questions[0]["question_id"] == f"{benchmark_name}:q1"
        assert "gold_answers" not in public_questions[0]


def test_simplemem_registered_prediction_workers_gt_1_manifest_has_protocol_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--smoke-max-workers > 1 时 manifest 必须包含三协议身份字段。"""

    FakeSimpleMemForRegisteredPrediction.instances.clear()
    real_paths = load_path_settings(PROJECT_ROOT)
    test_paths = replace(real_paths, outputs_root=tmp_path / "outputs")
    monkeypatch.setattr(
        run_prediction_module,
        "load_path_settings",
        lambda project_root: test_paths,
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_openai_settings",
        lambda project_root: OpenAISettings(
            api_key="sk-test",
            base_url="https://example.invalid/v1",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "OpenAICompatibleAnswerLLMClient",
        FakeAnswerClient,
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "get_benchmark_registration",
        lambda benchmark_name: _fake_registration(benchmark_name),
    )
    monkeypatch.setattr(
        method_registry_module,
        "SimpleMem",
        FakeSimpleMemForRegisteredPrediction,
    )

    result = run_prediction_module.run_registered_conversation_qa_prediction(
        project_root=PROJECT_ROOT,
        method_name="simplemem",
        benchmark_name="locomo",
        profile_name="smoke",
        run_id="simplemem-locomo-fake-smoke-workers2",
        confirm_api=True,
        smoke_turn_limit=2,
        smoke_conversation_limit=1,
        smoke_max_workers=2,
        enable_efficiency_observability=False,
    )

    assert result.benchmark == "locomo"
    run_dir = tmp_path / "outputs" / "simplemem-locomo-fake-smoke-workers2"
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["method_name"] == "SimpleMem"
    assert manifest["method"]["protocol_version"] == "v3"
    assert manifest["method"]["prompt_track"] == "native"
    assert manifest["method"]["profile"] == {}
    # 交叉校验：worker 内实例必须是 MemoryProvider
    assert len(FakeSimpleMemForRegisteredPrediction.instances) >= 1
    for instance in FakeSimpleMemForRegisteredPrediction.instances:
        assert isinstance(instance, MemoryProvider)


class FakeAnswerClient:
    """离线 fake framework answer client，避免 registered 测试触发真实 API。"""

    model_name = "fake-answer-client"

    def __init__(
        self,
        *,
        settings: OpenAISettings,
        answer_settings: AnswerLLMSettings,
    ) -> None:
        """保存 settings，以覆盖真实 client 的构造路径。"""

        self.settings = settings
        self.answer_settings = answer_settings

    def complete(self, *, prompt: str) -> str:
        """返回固定答案；prompt 拼接由 framework reader 负责。"""

        return "framework fake answer"


def _fake_registration(benchmark_name: str):
    """构造 LoCoMo/LongMemEval 共用的最小 fake benchmark registration。"""

    return SimpleNamespace(
        name=benchmark_name,
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
        default_variant=f"{benchmark_name}-fake",
        variant_names=lambda: (f"{benchmark_name}-fake",),
        prepare=lambda project_root, request: _prepared_run(
            benchmark_name=benchmark_name,
            project_root=project_root,
            request=request,
        ),
        prediction_enabled=True,
    )


def _prepared_run(
    *,
    benchmark_name: str,
    project_root: Path,
    request: BenchmarkLoadRequest,
) -> PreparedBenchmarkRun:
    """返回固定 fake smoke dataset，并校验 registered service 请求。"""

    assert project_root == PROJECT_ROOT
    assert request == BenchmarkLoadRequest(
        variant=f"{benchmark_name}-fake",
        run_scope=RunScope.SMOKE,
        smoke_turn_limit=2,
        smoke_conversation_limit=1,
    )
    return PreparedBenchmarkRun(
        variant=f"{benchmark_name}-fake",
        run_scope=RunScope.SMOKE,
        dataset=_fake_dataset(benchmark_name),
        source_relative_paths=(Path("pyproject.toml"),),
    )


def _fake_dataset(benchmark_name: str) -> Dataset:
    """构造最小 conversation-QA fake dataset。"""

    question = Question(
        question_id=f"{benchmark_name}:q1",
        conversation_id=f"{benchmark_name}:conv-1",
        text=f"What should {benchmark_name} remember?",
    )
    return Dataset(
        dataset_name=benchmark_name,
        metadata={"variant": f"{benchmark_name}-fake", "run_scope": "smoke"},
        conversations=[
            Conversation(
                conversation_id=f"{benchmark_name}:conv-1",
                sessions=[
                    Session(
                        session_id="session-1",
                        session_time="2026-01-01T00:00:00",
                        turns=[
                            Turn(
                                turn_id="t1",
                                speaker="Alice",
                                content=f"{benchmark_name} fact one.",
                            ),
                            Turn(
                                turn_id="t2",
                                speaker="Bob",
                                content=f"{benchmark_name} fact two.",
                            ),
                        ],
                    )
                ],
                questions=[question],
                gold_answers={
                    question.question_id: GoldAnswerInfo(
                        question_id=question.question_id,
                        answer="fake answer",
                        evidence=["private-evidence"],
                    )
                },
            )
        ],
    )
