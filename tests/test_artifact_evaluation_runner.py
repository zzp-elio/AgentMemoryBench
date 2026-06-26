"""artifact-only evaluation runner 测试。

本文件验证离线评测 runner 只读取标准 artifacts，重建核心实体并写入
metric 专属 score/summary 文件，同时对 id、conversation 和必填字段做强校验。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from memory_benchmark.cli import run_prediction as run_prediction_module
from memory_benchmark.config import OpenAISettings
from memory_benchmark.core import (
    AddResult,
    AnswerResult,
    BaseMemoryProvider,
    BaseMemorySystem,
    ConfigurationError,
    Conversation,
    GoldAnswerInfo,
    MetricResult,
    MethodCapability,
    Question,
    AnswerPromptResult,
    TaskFamily,
)
from memory_benchmark.methods.registry import MethodBuildContext
from memory_benchmark.benchmark_adapters import (
    BenchmarkLoadRequest,
    RunScope,
    get_benchmark_registration,
)
from memory_benchmark.cli.run_prediction import PredictionBatchResult
from memory_benchmark.evaluators import LoCoMoF1Evaluator
from memory_benchmark.runners.evaluation import run_artifact_evaluation
from memory_benchmark.storage import (
    ExperimentPaths,
    evaluator_private_label_record,
    public_question_record,
    read_jsonl,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeEvaluator:
    """返回固定分数的最小 evaluator。"""

    def __init__(self, metric_name: str, score: float):
        """保存 metric 名称和固定分数。"""

        self.metric_name = metric_name
        self.score = score

    def evaluate(self, question, prediction, gold_answer) -> MetricResult:
        """返回固定 metric，并保留实体重建后的核心字段。"""

        return MetricResult(
            metric_name=self.metric_name,
            score=self.score,
            is_correct=self.score >= 0.5,
            details={
                "question_text": question.text,
                "prediction_answer": prediction.answer,
                "gold_answer": gold_answer.answer,
            },
        )


class QuestionTimeEvaluator:
    """把重建后的 question_time 写入 details，供 artifact round-trip 断言。"""

    metric_name = "question_time_probe"

    def evaluate(self, question, prediction, gold_answer) -> MetricResult:
        """返回固定分数，并暴露重建后的公开时间和私有审计时间。"""

        return MetricResult(
            metric_name=self.metric_name,
            score=1.0,
            is_correct=True,
            details={
                "question_time": question.question_time,
                "private_question_date": gold_answer.metadata.get("question_date"),
            },
        )


class _FakeOfflineSystem(BaseMemorySystem):
    """用于离线装配测试的最小 memory system。"""

    def __init__(self) -> None:
        """初始化 add 调用记录。"""

        self.added_conversations: list[list[Conversation]] = []

    def add(self, conversations: list[Conversation]) -> AddResult:
        """记录写入的完整公开 conversation。"""

        self.added_conversations.append(conversations)
        return AddResult(
            conversation_ids=[conversation.conversation_id for conversation in conversations]
        )

    def get_answer(self, question: Question) -> AnswerResult:
        """返回固定答案，避免任何真实模型调用。"""

        return AnswerResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer="offline fake answer",
            metadata={"method": "offline-fake"},
        )


class _FakeOfflineProvider(BaseMemoryProvider):
    """用于离线装配测试的 retrieve-first fake provider。"""

    def __init__(self) -> None:
        """初始化 add/retrieve 调用记录。"""

        self.added_conversations: list[Conversation] = []
        self.retrieved_questions: list[Question] = []

    def add(self, conversation: Conversation) -> AddResult:
        """记录写入的完整公开 conversation。"""

        self.added_conversations.append(conversation)
        return AddResult(conversation_ids=[conversation.conversation_id])

    def retrieve(self, question: Question) -> AnswerPromptResult:
        """返回离线固定上下文，避免真实 method/API 调用。"""

        self.retrieved_questions.append(question)
        return AnswerPromptResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer_prompt=f"offline context for {question.text}",
            metadata={"method": "offline-fake"},
        )


def test_run_artifact_evaluation_scores_locomo_f1_without_env_or_method(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """runner 应仅靠 artifacts 完成离线 F1，并且不读取 .env。"""

    run_dir = _build_run_dir(tmp_path)
    _write_manifest(run_dir, benchmark_name="locomo")
    _write_jsonl(
        run_dir / "artifacts" / "public_questions.jsonl",
        [
            {
                "question_id": "conv-1:q1",
                "conversation_id": "conv-1",
                "question_text": "Where did Alice move?",
                "category": "2",
                "metadata": {"source": "unit"},
            }
        ],
    )
    _write_jsonl(
        run_dir / "artifacts" / "method_predictions.jsonl",
        [
            {
                "question_id": "conv-1:q1",
                "conversation_id": "conv-1",
                "answer": "Seattle",
                "metadata": {"method": "fake"},
            }
        ],
    )
    _write_jsonl(
        run_dir / "artifacts" / "evaluator_private_labels.jsonl",
        [
            {
                "question_id": "conv-1:q1",
                "gold_answer": "Seattle",
                "category": "2",
                "evidence": ["conv-1:t1"],
                "metadata": {"answer_session_ids": ["s1"]},
            }
        ],
    )
    original_read_text = Path.read_text

    def guarded_read_text(self: Path, *args, **kwargs):
        """阻止离线 artifact evaluation 意外读取 `.env`。"""

        if self.name == ".env":
            raise AssertionError("artifact evaluation must not read .env")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    summary = run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=LoCoMoF1Evaluator(),
        expected_benchmark="locomo",
    )

    scores = read_jsonl(Path(summary.score_path))
    summary_payload = json.loads(Path(summary.summary_path).read_text(encoding="utf-8"))

    assert summary.run_id == "unit-run"
    assert summary.metric_name == "locomo_f1"
    assert summary.total_questions == 1
    assert summary.mean_score == 1.0
    assert summary.correct_count == 1
    assert scores == [
        {
            "question_id": "conv-1:q1",
            "conversation_id": "conv-1",
            "metric_name": "locomo_f1",
            "score": 1.0,
            "is_correct": True,
            "details": {
                "question_id": "conv-1:q1",
                "conversation_id": "conv-1",
                "answer_question_id": "conv-1:q1",
                "gold_question_id": "conv-1:q1",
                "category": "2",
                "strategy": "single_answer_f1",
                "normalized_prediction": "seattle",
                "normalized_gold": "seattle",
                "prediction_tokens": ["seattl"],
                "gold_tokens": ["seattl"],
                "common_tokens": {"seattl": 1},
                "common_token_count": 1,
                "precision": 1.0,
                "recall": 1.0,
            },
        }
    ]
    assert summary_payload["metric_name"] == "locomo_f1"
    assert summary_payload["score_path"] == summary.score_path
    assert summary_payload["summary_path"] == summary.summary_path


def test_answer_level_evaluation_ignores_retrieval_artifact_by_default(
    tmp_path: Path,
) -> None:
    """answer-level metric 只依赖 prediction 和 private labels。"""

    run_dir = _build_run_dir(tmp_path)
    _write_manifest(run_dir, benchmark_name="locomo")
    _write_jsonl(
        run_dir / "artifacts" / "public_questions.jsonl",
        [
            {
                "question_id": "conv-1:q1",
                "conversation_id": "conv-1",
                "question_text": "What does Alice like?",
                "category": "2",
                "metadata": {},
            }
        ],
    )
    _write_jsonl(
        run_dir / "artifacts" / "method_predictions.jsonl",
        [
            {
                "question_id": "conv-1:q1",
                "conversation_id": "conv-1",
                "answer": "tea",
                "metadata": {"method": "fake"},
            }
        ],
    )
    _write_jsonl(
        run_dir / "artifacts" / "evaluator_private_labels.jsonl",
        [
            {
                "question_id": "conv-1:q1",
                "gold_answer": "tea",
                "category": "2",
                "evidence": ["conv-1:t1"],
                "metadata": {},
            }
        ],
    )
    _write_jsonl(
        run_dir / "artifacts" / "answer_prompts.prediction.jsonl",
        [
            {
                "question_id": "conv-1:q1",
                "conversation_id": "conv-1",
                "answer_prompt": "This prompt should not be read by F1.",
                "metadata": {"debug": "answer-prompt-only"},
            }
        ],
    )

    summary = run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=FakeEvaluator(metric_name="fake_metric", score=1.0),
        expected_benchmark="locomo",
    )

    scores = read_jsonl(Path(summary.score_path))
    assert summary.total_questions == 1
    assert summary.mean_score == 1.0
    assert scores[0]["details"] == {
        "question_text": "What does Alice like?",
        "prediction_answer": "tea",
        "gold_answer": "tea",
    }


def test_new_memoryos_prediction_can_be_scored_by_existing_locomo_f1(
    tmp_path: Path,
) -> None:
    """通用 prediction 写出的 canonical records 应可直接被现有 LoCoMo F1 离线复算。"""

    run_dir = _build_run_dir(tmp_path)
    _write_manifest(run_dir, benchmark_name="locomo")
    _write_jsonl(
        run_dir / "artifacts" / "public_questions.jsonl",
        [
            {
                "question_id": "conv-1:q1",
                "conversation_id": "conv-1",
                "question_text": "前两轮里说了什么？",
                "category": "2",
                "metadata": {},
            }
        ],
    )
    _write_jsonl(
        run_dir / "artifacts" / "method_predictions.jsonl",
        [
            {
                "question_id": "conv-1:q1",
                "conversation_id": "conv-1",
                "question_text": "前两轮里说了什么？",
                "answer": "前两轮答案",
                "metadata": {"method": "fake-memoryos"},
            }
        ],
    )
    _write_jsonl(
        run_dir / "artifacts" / "evaluator_private_labels.jsonl",
        [
            {
                "question_id": "conv-1:q1",
                "gold_answer": "前两轮答案",
                "category": "2",
                "evidence": ["conv-1:t1", "conv-1:t2"],
                "metadata": {},
            }
        ],
    )

    summary = run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=LoCoMoF1Evaluator(),
        expected_benchmark="locomo",
    )

    score_path = run_dir / "artifacts" / "answer_scores.locomo_f1.jsonl"
    summary_path = run_dir / "summaries" / "summary.locomo_f1.json"
    scores = read_jsonl(score_path)
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary.metric_name == "locomo_f1"
    assert summary.total_questions == 1
    assert summary.mean_score == 1.0
    assert summary.correct_count == 1
    assert summary.score_path == str(score_path.resolve())
    assert summary.summary_path == str(summary_path.resolve())
    assert scores == [
        {
            "question_id": "conv-1:q1",
            "conversation_id": "conv-1",
            "metric_name": "locomo_f1",
            "score": 1.0,
            "is_correct": True,
            "details": {
                "question_id": "conv-1:q1",
                "conversation_id": "conv-1",
                "answer_question_id": "conv-1:q1",
                "gold_question_id": "conv-1:q1",
                "category": "2",
                "strategy": "single_answer_f1",
                "normalized_prediction": "前两轮答案",
                "normalized_gold": "前两轮答案",
                "prediction_tokens": ["前两轮答案"],
                "gold_tokens": ["前两轮答案"],
                "common_tokens": {"前两轮答案": 1},
                "common_token_count": 1,
                "precision": 1.0,
                "recall": 1.0,
            },
        }
    ]
    assert summary_payload["metric_name"] == "locomo_f1"
    assert summary_payload["mean_score"] == 1.0
    assert summary_payload["score_path"] == str(score_path.resolve())
    assert summary_payload["summary_path"] == str(summary_path.resolve())


def test_schema_v1_prediction_manifest_remains_evaluable(
    tmp_path: Path,
) -> None:
    """schema v1 prediction manifest 仍应支持 artifact-only evaluation。"""

    run_dir = _build_run_dir(tmp_path)
    _write_manifest(run_dir, benchmark_name="locomo")
    _write_jsonl(
        run_dir / "artifacts" / "public_questions.jsonl",
        [
            {
                "question_id": "conv-legacy:q1",
                "conversation_id": "conv-legacy",
                "question_text": "legacy question",
                "category": "2",
                "metadata": {},
            }
        ],
    )
    _write_jsonl(
        run_dir / "artifacts" / "method_predictions.jsonl",
        [
            {
                "question_id": "conv-legacy:q1",
                "conversation_id": "conv-legacy",
                "answer": "legacy answer",
                "metadata": {},
            }
        ],
    )
    _write_jsonl(
        run_dir / "artifacts" / "evaluator_private_labels.jsonl",
        [
            {
                "question_id": "conv-legacy:q1",
                "gold_answer": "legacy answer",
                "category": "2",
                "evidence": ["conv-legacy:t1"],
                "metadata": {},
            }
        ],
    )

    summary = run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=LoCoMoF1Evaluator(),
        expected_benchmark="locomo",
    )

    assert summary.metric_name == "locomo_f1"
    assert summary.total_questions == 1
    assert summary.mean_score == 1.0


def test_question_time_round_trips_through_canonical_artifacts(
    tmp_path: Path,
) -> None:
    """canonical public record 应保留 question_time，离线重建后值不变。"""

    run_dir = _build_run_dir(tmp_path)
    _write_manifest(run_dir, benchmark_name="longmemeval")
    question = Question(
        question_id="longmemeval:q1",
        conversation_id="longmemeval:q1",
        text="What did I say I like?",
        question_time="2023/05/30 (Tue) 23:40",
        category="single-session-user",
        metadata={"source_index": 0},
    )
    gold = GoldAnswerInfo(
        question_id=question.question_id,
        answer="tea",
        evidence=["session_a"],
        metadata={
            "question_type": "single-session-user",
            "question_date": "2023/05/30 (Tue) 23:40",
            "source_index": 0,
        },
    )
    public_record = public_question_record(question)
    private_record = evaluator_private_label_record(gold, question.category)

    assert public_record["question_time"] == "2023/05/30 (Tue) 23:40"
    assert "question_date" not in public_record.get("metadata", {})
    assert not {"gold_answer", "evidence", "answer_session_ids"} & set(public_record)
    assert private_record["metadata"]["question_date"] == "2023/05/30 (Tue) 23:40"

    _write_jsonl(
        run_dir / "artifacts" / "public_questions.jsonl",
        [public_record],
    )
    _write_jsonl(
        run_dir / "artifacts" / "method_predictions.jsonl",
        [
            {
                "question_id": question.question_id,
                "conversation_id": question.conversation_id,
                "answer": "tea",
                "metadata": {},
            }
        ],
    )
    _write_jsonl(
        run_dir / "artifacts" / "evaluator_private_labels.jsonl",
        [private_record],
    )

    summary = run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=QuestionTimeEvaluator(),
        expected_benchmark="longmemeval",
    )

    details = read_jsonl(Path(summary.score_path))[0]["details"]
    assert details["question_time"] == "2023/05/30 (Tue) 23:40"
    assert details["private_question_date"] == "2023/05/30 (Tue) 23:40"


def test_legacy_public_record_without_question_time_rebuilds_none(
    tmp_path: Path,
) -> None:
    """旧 public record 缺少 question_time 时应兼容重建为 None。"""

    run_dir = _build_run_dir(tmp_path)
    _write_manifest(run_dir, benchmark_name="longmemeval")
    _write_jsonl(
        run_dir / "artifacts" / "public_questions.jsonl",
        [
            {
                "question_id": "longmemeval:legacy",
                "conversation_id": "longmemeval:legacy",
                "question_text": "Legacy question?",
                "category": "single-session-user",
                "metadata": {},
            }
        ],
    )
    _write_jsonl(
        run_dir / "artifacts" / "method_predictions.jsonl",
        [
            {
                "question_id": "longmemeval:legacy",
                "conversation_id": "longmemeval:legacy",
                "answer": "legacy answer",
                "metadata": {},
            }
        ],
    )
    _write_jsonl(
        run_dir / "artifacts" / "evaluator_private_labels.jsonl",
        [
            {
                "question_id": "longmemeval:legacy",
                "gold_answer": "legacy answer",
                "category": "single-session-user",
                "evidence": [],
                "metadata": {"question_date": "2023/05/30 (Tue) 23:40"},
            }
        ],
    )

    summary = run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=QuestionTimeEvaluator(),
        expected_benchmark="longmemeval",
    )

    details = read_jsonl(Path(summary.score_path))[0]["details"]
    assert details["question_time"] is None
    assert details["private_question_date"] == "2023/05/30 (Tue) 23:40"


def test_longmemeval_s_smoke_registered_prediction_stays_offline_and_separates_private_labels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LongMemEval S smoke 装配应产出 v2 artifacts，且公开/私有字段保持分离。"""

    captured_systems: list[_FakeOfflineProvider] = []
    original_read_text = Path.read_text

    def guarded_read_text(self: Path, *args, **kwargs):
        """阻止测试期间读取真实 `.env`。"""

        if self.name == ".env":
            raise AssertionError("offline LongMemEval smoke must not read .env")
        return original_read_text(self, *args, **kwargs)

    class _FakeProfile:
        """最小 method profile。"""

        profile_name = "smoke"

        def to_manifest(self) -> dict[str, object]:
            """返回不含 secret 的配置快照。"""

            return {"profile_name": "smoke"}

    def build_fake_system(context: MethodBuildContext) -> BaseMemoryProvider:
        """构造离线 fake provider，并保留 build context 供断言。"""

        assert context.config.profile_name == "smoke"
        assert context.openai_settings == OpenAISettings(
            api_key="sk-test",
            base_url="https://example.test/v1",
            model="gpt-4o-mini",
        )
        system = _FakeOfflineProvider()
        captured_systems.append(system)
        return system

    class _FakeOpenAIAnswerClient:
        """测试用 answer client，避免构造真实 OpenAI SDK client。"""

        model_name = "offline-answer-llm"

        def __init__(self, *, settings: OpenAISettings, answer_settings=None) -> None:
            """只校验配置来源，不创建真实网络 client。"""

            assert settings == OpenAISettings(
                api_key="sk-test",
                base_url="https://example.test/v1",
                model="gpt-4o-mini",
            )

        def complete(self, *, prompt: str) -> str:
            """返回固定答案，证明 framework reader 可以离线装配。"""

            assert "offline context" in prompt
            return "offline fake answer"

    fake_method_registration = SimpleNamespace(
        name="offline-fake",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
        requires_api=False,
        allow_smoke_worker_override=False,
        display_name="OfflineFake",
        source_identity_factory=lambda path_settings: {"source": "offline-fake"},
        max_workers_getter=lambda config: 1,
        model_name_getter=lambda config: "offline-fake-model",
        resolve_profile_section=lambda profile_name: profile_name,
        system_factory=build_fake_system,
        workload_estimator=None,
    )

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    monkeypatch.setattr(
        run_prediction_module,
        "get_method_registration",
        lambda method_name: fake_method_registration,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_method_profile",
        lambda **kwargs: _FakeProfile(),
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_path_settings",
        lambda project_root: SimpleNamespace(
            project_root=PROJECT_ROOT,
            outputs_root=tmp_path / "outputs",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_openai_settings",
        lambda project_root: OpenAISettings(
            api_key="sk-test",
            base_url="https://example.test/v1",
            model="gpt-4o-mini",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "OpenAICompatibleAnswerLLMClient",
        _FakeOpenAIAnswerClient,
        raising=False,
    )

    expected_smoke_first = get_benchmark_registration("longmemeval").prepare(
        PROJECT_ROOT,
        BenchmarkLoadRequest(
            variant="s_cleaned",
            run_scope=RunScope.SMOKE,
            smoke_turn_limit=20,
        ),
    ).dataset
    batch_result = run_prediction_module.run_registered_conversation_qa_prediction(
        project_root=tmp_path,
        method_name="offline-fake",
        benchmark_name="longmemeval",
        profile_name="smoke",
        variant="s_cleaned",
        run_id="offline-longmemeval",
        confirm_api=False,
        enable_efficiency_observability=False,
    )

    assert isinstance(batch_result, PredictionBatchResult)
    assert batch_result.benchmark == "longmemeval"
    assert batch_result.selector == "s_cleaned"
    assert [run.variant for run in batch_result.runs] == ["s_cleaned"]
    child = batch_result.runs[0]
    assert child.run_id == "offline-longmemeval-s-cleaned"
    assert child.summary.run_id == "offline-longmemeval-s-cleaned"
    assert child.summary.total_conversations == 1
    assert child.summary.total_questions == 1
    assert len(captured_systems) == 1
    assert len(captured_systems[0].added_conversations) == 1
    added_conversation = captured_systems[0].added_conversations[0]
    assert added_conversation.sessions == expected_smoke_first.conversations[0].sessions
    assert len(captured_systems[0].retrieved_questions) == 1

    run_dir = tmp_path / "outputs" / child.run_id
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    public_questions = read_jsonl(run_dir / "artifacts" / "public_questions.jsonl")
    predictions = read_jsonl(run_dir / "artifacts" / "method_predictions.jsonl")
    private_labels = read_jsonl(
        run_dir / "artifacts" / "evaluator_private_labels.jsonl"
    )

    assert manifest["schema_version"] == 2
    assert manifest["benchmark_name"] == "longmemeval"
    assert manifest["benchmark_variant"] == "s_cleaned"
    assert manifest["run_scope"] == RunScope.SMOKE.value
    assert len(public_questions) == 1
    assert len(predictions) == 1
    assert len(private_labels) == 1
    assert "gold_answer" not in public_questions[0]
    assert "question_date" not in public_questions[0].get("metadata", {})
    assert private_labels[0]["gold_answer"]
    assert private_labels[0]["metadata"]["question_date"]


@pytest.mark.parametrize(
    ("public_records", "prediction_records", "private_records", "error_text"),
    [
        (
            [
                {
                    "question_id": "conv-1:q1",
                    "conversation_id": "conv-1",
                    "question_text": "Question?",
                    "category": "2",
                    "metadata": {},
                },
                {
                    "question_id": "conv-1:q1",
                    "conversation_id": "conv-1",
                    "question_text": "Question?",
                    "category": "2",
                    "metadata": {},
                },
            ],
            [
                {
                    "question_id": "conv-1:q1",
                    "conversation_id": "conv-1",
                    "answer": "Seattle",
                    "metadata": {},
                }
            ],
            [
                {
                    "question_id": "conv-1:q1",
                    "gold_answer": "Seattle",
                    "category": "2",
                    "evidence": [],
                    "metadata": {},
                }
            ],
            "duplicate question_id",
        ),
        (
            [
                {
                    "question_id": "conv-1:q1",
                    "conversation_id": "conv-1",
                    "question_text": "Question?",
                    "category": "2",
                    "metadata": {},
                }
            ],
            [
                {
                    "question_id": "conv-1:q1",
                    "conversation_id": "conv-1",
                    "answer": "Seattle",
                    "metadata": {},
                }
            ],
            [
                {
                    "question_id": "conv-1:q2",
                    "gold_answer": "Seattle",
                    "category": "2",
                    "evidence": [],
                    "metadata": {},
                }
            ],
            "public question and private label id sets do not match",
        ),
        (
            [
                {
                    "question_id": "conv-1:q1",
                    "conversation_id": "conv-1",
                    "question_text": "Question?",
                    "category": "2",
                    "metadata": {},
                }
            ],
            [
                {
                    "question_id": "conv-1:q1",
                    "conversation_id": "conv-2",
                    "answer": "Seattle",
                    "metadata": {},
                }
            ],
            [
                {
                    "question_id": "conv-1:q1",
                    "gold_answer": "Seattle",
                    "category": "2",
                    "evidence": [],
                    "metadata": {},
                }
            ],
            "conversation_id mismatch",
        ),
        (
            [
                {
                    "question_id": "conv-1:q1",
                    "conversation_id": "conv-1",
                    "question_text": "Question?",
                    "category": "2",
                    "metadata": {},
                }
            ],
            [
                {
                    "question_id": "conv-1:q1",
                    "conversation_id": "conv-1",
                    "answer": "   ",
                    "metadata": {},
                }
            ],
            [
                {
                    "question_id": "conv-1:q1",
                    "gold_answer": "Seattle",
                    "category": "2",
                    "evidence": [],
                    "metadata": {},
                }
            ],
            "prediction answer is empty",
        ),
        (
            [
                {
                    "question_id": "conv-1:q1",
                    "conversation_id": "conv-1",
                    "question_text": "Question?",
                    "category": "2",
                    "metadata": {},
                }
            ],
            [
                {
                    "question_id": "conv-1:q1",
                    "conversation_id": "conv-1",
                    "answer": "Seattle",
                    "metadata": {},
                }
            ],
            [
                {
                    "question_id": "conv-1:q1",
                    "category": "2",
                    "evidence": [],
                    "metadata": {},
                }
            ],
            "gold_answer is required",
        ),
    ],
)
def test_run_artifact_evaluation_rejects_invalid_artifacts(
    tmp_path: Path,
    public_records: list[dict[str, object]],
    prediction_records: list[dict[str, object]],
    private_records: list[dict[str, object]],
    error_text: str,
) -> None:
    """runner 应显式拒绝重复 id、集合不一致、conversation 错配和缺字段。"""

    run_dir = _build_run_dir(tmp_path)
    _write_manifest(run_dir, benchmark_name="locomo")
    _write_jsonl(run_dir / "artifacts" / "public_questions.jsonl", public_records)
    _write_jsonl(run_dir / "artifacts" / "method_predictions.jsonl", prediction_records)
    _write_jsonl(
        run_dir / "artifacts" / "evaluator_private_labels.jsonl",
        private_records,
    )

    with pytest.raises(ConfigurationError, match=error_text):
        run_artifact_evaluation(
            run_dir=run_dir,
            evaluator=LoCoMoF1Evaluator(),
            expected_benchmark="locomo",
        )


def test_run_artifact_evaluation_rejects_missing_required_artifact(
    tmp_path: Path,
) -> None:
    """缺失任一必需 artifact 时必须报错，不能生成零题成功摘要。"""

    run_dir = _build_run_dir(tmp_path)
    _write_manifest(run_dir, benchmark_name="locomo")

    with pytest.raises(ConfigurationError, match="public_questions.*missing"):
        run_artifact_evaluation(
            run_dir=run_dir,
            evaluator=LoCoMoF1Evaluator(),
            expected_benchmark="locomo",
        )


def test_run_artifact_evaluation_rejects_empty_required_artifacts(
    tmp_path: Path,
) -> None:
    """三类 artifact 即使都存在也不能全部为空。"""

    run_dir = _build_run_dir(tmp_path)
    _write_manifest(run_dir, benchmark_name="locomo")
    for filename in (
        "public_questions.jsonl",
        "method_predictions.jsonl",
        "evaluator_private_labels.jsonl",
    ):
        _write_jsonl(run_dir / "artifacts" / filename, [])

    with pytest.raises(ConfigurationError, match="public_questions.*empty"):
        run_artifact_evaluation(
            run_dir=run_dir,
            evaluator=LoCoMoF1Evaluator(),
            expected_benchmark="locomo",
        )


def test_run_artifact_evaluation_wraps_malformed_jsonl_as_domain_error(
    tmp_path: Path,
) -> None:
    """损坏 JSONL 应转换为 CLI 可处理的 ConfigurationError。"""

    run_dir = _build_run_dir(tmp_path)
    _write_manifest(run_dir, benchmark_name="locomo")
    malformed_path = run_dir / "artifacts" / "public_questions.jsonl"
    malformed_path.write_text("{not-json}\n", encoding="utf-8")
    _write_jsonl(run_dir / "artifacts" / "method_predictions.jsonl", [])
    _write_jsonl(run_dir / "artifacts" / "evaluator_private_labels.jsonl", [])

    with pytest.raises(ConfigurationError, match="public_questions.*invalid JSONL"):
        run_artifact_evaluation(
            run_dir=run_dir,
            evaluator=LoCoMoF1Evaluator(),
            expected_benchmark="locomo",
        )


def test_run_artifact_evaluation_writes_isolated_files_for_multiple_metrics(
    tmp_path: Path,
) -> None:
    """同一 run 上连续执行两个 evaluator 时应写入彼此独立的文件。"""

    run_dir = _build_run_dir(tmp_path)
    _write_manifest(run_dir, benchmark_name="locomo")
    _write_jsonl(
        run_dir / "artifacts" / "public_questions.jsonl",
        [
            {
                "question_id": "conv-1:q1",
                "conversation_id": "conv-1",
                "question_text": "Question?",
                "category": "2",
                "metadata": {},
            }
        ],
    )
    _write_jsonl(
        run_dir / "artifacts" / "method_predictions.jsonl",
        [
            {
                "question_id": "conv-1:q1",
                "conversation_id": "conv-1",
                "answer": "Seattle",
                "metadata": {},
            }
        ],
    )
    _write_jsonl(
        run_dir / "artifacts" / "evaluator_private_labels.jsonl",
        [
            {
                "question_id": "conv-1:q1",
                "gold_answer": "Seattle",
                "category": "2",
                "evidence": [],
                "metadata": {},
            }
        ],
    )

    first_summary = run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=FakeEvaluator(metric_name="fake_one", score=0.25),
        expected_benchmark="locomo",
    )
    second_summary = run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=FakeEvaluator(metric_name="fake_two", score=0.75),
        expected_benchmark="locomo",
    )

    assert first_summary.score_path != second_summary.score_path
    assert first_summary.summary_path != second_summary.summary_path
    assert read_jsonl(Path(first_summary.score_path))[0]["metric_name"] == "fake_one"
    assert read_jsonl(Path(second_summary.score_path))[0]["metric_name"] == "fake_two"
    assert json.loads(Path(first_summary.summary_path).read_text(encoding="utf-8"))[
        "mean_score"
    ] == 0.25
    assert json.loads(Path(second_summary.summary_path).read_text(encoding="utf-8"))[
        "mean_score"
    ] == 0.75


def _build_run_dir(tmp_path: Path) -> Path:
    """创建标准实验目录。"""

    return ExperimentPaths.create(tmp_path / "unit-run").run_dir


def _write_manifest(run_dir: Path, *, benchmark_name: str) -> None:
    """写入最小 manifest。"""

    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "runner": "generic_conversation_qa_prediction",
                "run_id": "unit-run",
                "benchmark_name": benchmark_name,
                "method_name": "fake-method",
                "model_name": "fake-model",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    """写入测试所需 JSONL。"""

    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def test_artifact_evaluation_writes_category_summary(tmp_path: Path) -> None:
    """category 存在时 summary 包含 category_breakdown 字段。"""

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    paths = ExperimentPaths.create(run_dir)
    _write_manifest(run_dir, benchmark_name="test-bench")
    public_questions = [
        public_question_record(
            Question(
                question_id="q-1",
                conversation_id="c-1",
                text="What is X?",
                category="cat-A",
            )
        ),
        public_question_record(
            Question(
                question_id="q-2",
                conversation_id="c-2",
                text="What is Y?",
                category="cat-B",
            )
        ),
        public_question_record(
            Question(
                question_id="q-3",
                conversation_id="c-2",
                text="What is Z?",
                category="cat-A",
            )
        ),
    ]
    _write_jsonl(paths.public_questions_path, public_questions)
    _write_jsonl(
        paths.method_predictions_path,
        [
            {"question_id": "q-1", "conversation_id": "c-1", "question_text": "What is X?", "answer": "X1"},
            {"question_id": "q-2", "conversation_id": "c-2", "question_text": "What is Y?", "answer": "Y1"},
            {"question_id": "q-3", "conversation_id": "c-2", "question_text": "What is Z?", "answer": "Z1"},
        ],
    )
    _write_jsonl(
        paths.evaluator_private_labels_path,
        [
            evaluator_private_label_record(
                GoldAnswerInfo(question_id="q-1", answer="XA"),
                category="cat-A",
            ),
            evaluator_private_label_record(
                GoldAnswerInfo(question_id="q-2", answer="YB"),
                category="cat-B",
            ),
            evaluator_private_label_record(
                GoldAnswerInfo(question_id="q-3", answer="ZA"),
                category="cat-A",
            ),
        ],
    )

    summary = run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=FakeEvaluator("fake-metric", score=0.5),
        expected_benchmark="test-bench",
    )
    assert summary.total_questions == 3

    summary_path = run_dir / "summaries" / "summary.fake-metric.json"
    summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
    breakdown = summary_data.get("category_breakdown")
    assert breakdown is not None
    assert len(breakdown) == 2
    category_names = {entry["category"] for entry in breakdown}
    assert category_names == {"cat-A", "cat-B"}
    for entry in breakdown:
        assert entry["mean_score"] == 0.5


def test_artifact_evaluation_no_category_summary_when_no_categories(tmp_path: Path) -> None:
    """无 category 时 summary 不含 category_breakdown。"""

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    paths = ExperimentPaths.create(run_dir)
    _write_manifest(run_dir, benchmark_name="test-bench")
    public_questions = [
        public_question_record(
            Question(question_id="q-1", conversation_id="c-1", text="X")
        ),
    ]
    _write_jsonl(paths.public_questions_path, public_questions)
    _write_jsonl(
        paths.method_predictions_path,
        [{"question_id": "q-1", "conversation_id": "c-1", "question_text": "X", "answer": "A"}],
    )
    _write_jsonl(
        paths.evaluator_private_labels_path,
        [evaluator_private_label_record(GoldAnswerInfo(question_id="q-1", answer="XA"), category=None)],
    )
    run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=FakeEvaluator("fake-metric", score=0.5),
        expected_benchmark="test-bench",
    )
    summary_path = run_dir / "summaries" / "summary.fake-metric.json"
    summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
    assert "category_breakdown" not in summary_data


def test_parallel_evaluation_produces_same_results_as_serial(tmp_path: Path) -> None:
    """max_workers>1 结果应与串行一致，且顺序正确。"""

    question_count = 20

    public_records = [
        public_question_record(
            Question(
                question_id=f"q-{i}",
                conversation_id="c-1",
                text=f"question {i}",
                category=str(i % 3 + 1),
            )
        )
        for i in range(question_count)
    ]

    def _setup_run(sub_path: str) -> Path:
        """创建独立评测目录并写入最小 artifacts。"""
        run_dir = ExperimentPaths.create(tmp_path / sub_path).run_dir
        _write_manifest(run_dir, benchmark_name="test-parallel")
        spawn_paths = ExperimentPaths.create(run_dir)
        _write_jsonl(spawn_paths.public_questions_path, public_records)
        _write_jsonl(
            spawn_paths.method_predictions_path,
            [
                {
                    "question_id": f"q-{i}",
                    "conversation_id": "c-1",
                    "question_text": f"question {i}",
                    "answer": f"answer {i}",
                }
                for i in range(question_count)
            ],
        )
        _write_jsonl(
            spawn_paths.evaluator_private_labels_path,
            [
                evaluator_private_label_record(
                    GoldAnswerInfo(question_id=f"q-{i}", answer=f"gold {i}"),
                    category=None,
                )
                for i in range(question_count)
            ],
        )
        return run_dir

    serial_dir = _setup_run("serial-run")
    parallel_dir = _setup_run("parallel-run")

    serial_summary = run_artifact_evaluation(
        run_dir=serial_dir,
        evaluator=FakeEvaluator("same-metric", score=0.8),
        expected_benchmark="test-parallel",
        max_workers=1,
    )

    parallel_summary = run_artifact_evaluation(
        run_dir=parallel_dir,
        evaluator=FakeEvaluator("same-metric", score=0.8),
        expected_benchmark="test-parallel",
        max_workers=4,
    )

    assert parallel_summary.total_questions == serial_summary.total_questions
    assert parallel_summary.mean_score == serial_summary.mean_score
    assert parallel_summary.correct_count == serial_summary.correct_count

    serial_scores = read_jsonl(Path(serial_summary.score_path))
    parallel_scores = read_jsonl(Path(parallel_summary.score_path))
    assert len(parallel_scores) == len(serial_scores)
    for sp, pp in zip(serial_scores, parallel_scores):
        assert pp["question_id"] == sp["question_id"]
        assert pp["score"] == sp["score"]

    serial_summary_data = json.loads(
        Path(serial_summary.summary_path).read_text(encoding="utf-8")
    )
    parallel_summary_data = json.loads(
        Path(parallel_summary.summary_path).read_text(encoding="utf-8")
    )
    assert "category_breakdown" in parallel_summary_data
    assert (
        parallel_summary_data["category_breakdown"]
        == serial_summary_data["category_breakdown"]
    )
