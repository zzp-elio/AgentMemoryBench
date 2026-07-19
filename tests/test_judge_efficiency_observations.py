"""LLM Judge efficiency observation 的 artifact 测试。

本模块验证 artifact-only evaluation runner 对 evaluator-side efficiency 的处理：
离线 F1 不生成 judge 观测文件；真实 LLM judge 使用 fake client 运行时，必须写入
evaluator 专属模型清单和 LLM token observation。所有测试都不访问网络。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from memory_benchmark.evaluators import LoCoMoF1Evaluator, LoCoMoJudgeEvaluator
from memory_benchmark.evaluators.llm_judge import LLMJudgeEvaluator
from memory_benchmark.observability.efficiency import EfficiencyCollector
from memory_benchmark.runners.evaluation import run_artifact_evaluation
from memory_benchmark.storage import ExperimentPaths, read_jsonl


pytestmark = pytest.mark.unit


def test_offline_f1_does_not_create_judge_efficiency_artifacts(
    tmp_path: Path,
) -> None:
    """离线 F1 没有真实 judge 调用，因此不能创建空的 judge observation 文件。"""

    run_dir = _build_minimal_run_dir(tmp_path)
    paths = ExperimentPaths(run_dir=run_dir)

    run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=LoCoMoF1Evaluator(),
        expected_benchmark="locomo",
    )

    assert not paths.evaluator_model_inventory_path("locomo_f1").exists()
    assert not paths.evaluator_efficiency_observations_path("locomo_f1").exists()


def test_actual_llm_judge_records_model_inventory_and_token_usage(
    tmp_path: Path,
) -> None:
    """真实 LLM judge 路径应记录 judge input/output token 和模型身份。"""

    run_dir = _build_minimal_run_dir(tmp_path)
    evaluator = LoCoMoJudgeEvaluator(
        mode="compact",
        model="gpt-4o-mini",
        client=_FakeResponsesClient(
            text='{"label": "CORRECT"}',
            input_tokens=41,
            output_tokens=1,
        ),
    )

    summary = run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=evaluator,
        expected_benchmark="locomo",
    )

    paths = ExperimentPaths(run_dir=run_dir)
    inventory = json.loads(
        paths.evaluator_model_inventory_path(
            "locomo_judge_accuracy"
        ).read_text(encoding="utf-8")
    )
    observations = read_jsonl(
        paths.evaluator_efficiency_observations_path(
            "locomo_judge_accuracy"
        )
    )

    assert summary.metric_name == "locomo_judge_accuracy"
    assert inventory == {
        "schema_version": 1,
        "models": [
            {
                "model_id": "judge-llm",
                "model_name": "gpt-4o-mini",
                "model_role": "judge_llm",
                "execution_mode": "api",
                "revision_or_path": None,
                "embedding_dimension": None,
                "tokenizer_name": "gpt-4o-mini",
            }
        ],
    }
    assert len(observations) == 1
    assert observations[0]["observation_type"] == "llm_call"
    assert observations[0]["stage"] == "judge"
    assert observations[0]["model_id"] == "judge-llm"
    assert observations[0]["input_tokens"] == 41
    assert observations[0]["output_tokens"] == 1
    assert observations[0]["token_measurement_source"] == "api_usage"
    assert observations[0]["conversation_id"] == "conv-1"
    assert observations[0]["question_id"] == "conv-1:q1"


class _MinimalArtifactJudgeEvaluator(LLMJudgeEvaluator):
    """最小 artifact-level judge evaluator：在真实评测单元 scope 内做一次 judge 调用。

    用于隔离验证 runner 的 artifact-level 效率观测契约：collector 启用时写出 metric 专属
    model inventory 与恰好一条 judge LLM observation，且内部 `efficiency_observations`
    字段不泄漏进 score/summary。
    """

    metric_name = "minimal_artifact_judge"
    benchmark_name = "locomo"

    def __init__(self, *, conversation_id: str, question_id: str, **kwargs: object) -> None:
        """记录本 evaluator 会把 observation 归属到的真实 conversation/question 身份。"""

        super().__init__(**kwargs)
        self._conversation_id = conversation_id
        self._question_id = question_id

    def evaluate_run_artifacts(
        self, *, paths: object, manifest: dict[str, object], max_workers: int = 1
    ) -> dict[str, object]:
        """在一个真实单元 scope 内做一次 judge 调用并把 observation 回传给 runner。"""

        del paths, manifest, max_workers
        sink = self._new_efficiency_observation_sink()
        with sink.unit_scope(self._conversation_id, self._question_id):
            model_response = self._call_model_with_usage("judge this prediction")
            self._record_judge_llm_call(model_response)
        payload = {
            "metric_name": self.metric_name,
            "score_records": [
                {
                    "question_id": self._question_id,
                    "conversation_id": self._conversation_id,
                    "score": 1.0,
                    "is_correct": True,
                }
            ],
            "total_questions": 1,
            "mean_score": 1.0,
            "correct_count": 1,
            "summary": {"status": "ok"},
        }
        return self._finalize_artifact_payload(payload, sink)


class _OfflineArtifactEvaluator:
    """离线 artifact-level evaluator：不声明 efficiency support，不建立任何 judge scope。"""

    metric_name = "offline_artifact_metric"

    def evaluate_run_artifacts(
        self, *, paths: object, manifest: dict[str, object], max_workers: int = 1
    ) -> dict[str, object]:
        """返回固定 payload，绝不产生 judge inventory/observation。"""

        del paths, manifest, max_workers
        return {
            "metric_name": self.metric_name,
            "score_records": [
                {"question_id": "conv-1:q1", "conversation_id": "conv-1", "score": 1.0}
            ],
            "total_questions": 1,
            "mean_score": 1.0,
            "correct_count": None,
            "summary": {},
        }


def test_artifact_level_api_evaluator_writes_inventory_and_exact_observation(
    tmp_path: Path,
) -> None:
    """artifact-level API evaluator 经 runner 后写 metric 专属 inventory 与一条精确 observation。"""

    run_dir = _build_minimal_run_dir(tmp_path)
    evaluator = _MinimalArtifactJudgeEvaluator(
        mode="compact",
        model="gpt-4o-mini",
        client=_FakeResponsesClient(text="true", input_tokens=53, output_tokens=2),
        conversation_id="conv-1",
        question_id="conv-1:q1",
    )

    summary = run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=evaluator,
        expected_benchmark="locomo",
    )

    paths = ExperimentPaths(run_dir=run_dir)
    inventory = json.loads(
        paths.evaluator_model_inventory_path(
            "minimal_artifact_judge"
        ).read_text(encoding="utf-8")
    )
    observations = read_jsonl(
        paths.evaluator_efficiency_observations_path("minimal_artifact_judge")
    )

    assert summary.run_id == "unit-run"
    assert summary.metric_name == "minimal_artifact_judge"
    assert inventory == {
        "schema_version": 1,
        "models": [
            {
                "model_id": "judge-llm",
                "model_name": "gpt-4o-mini",
                "model_role": "judge_llm",
                "execution_mode": "api",
                "revision_or_path": None,
                "embedding_dimension": None,
                "tokenizer_name": "gpt-4o-mini",
            }
        ],
    }
    assert len(observations) == 1
    observation = observations[0]
    assert observation["observation_type"] == "llm_call"
    assert observation["stage"] == "judge"
    assert observation["model_id"] == "judge-llm"
    assert observation["input_tokens"] == 53
    assert observation["output_tokens"] == 2
    assert observation["token_measurement_source"] == "api_usage"
    assert observation["conversation_id"] == "conv-1"
    assert observation["question_id"] == "conv-1:q1"


def test_artifact_efficiency_observations_do_not_leak_into_score_or_summary(
    tmp_path: Path,
) -> None:
    """内部 `efficiency_observations` 字段不得出现在 summary JSON 或 score row 中。"""

    run_dir = _build_minimal_run_dir(tmp_path)
    evaluator = _MinimalArtifactJudgeEvaluator(
        mode="compact",
        model="gpt-4o-mini",
        client=_FakeResponsesClient(text="true", input_tokens=7, output_tokens=1),
        conversation_id="conv-1",
        question_id="conv-1:q1",
    )

    summary = run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=evaluator,
        expected_benchmark="locomo",
    )

    summary_json = json.loads(Path(summary.summary_path).read_text(encoding="utf-8"))
    score_rows = read_jsonl(Path(summary.score_path))
    assert "efficiency_observations" not in summary_json
    assert all("efficiency_observations" not in row for row in score_rows)


def test_offline_artifact_evaluator_creates_no_empty_judge_efficiency_files(
    tmp_path: Path,
) -> None:
    """不声明 support 的离线 artifact evaluator 不得生成空的 judge inventory/observation。"""

    run_dir = _build_minimal_run_dir(tmp_path)

    run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=_OfflineArtifactEvaluator(),
        expected_benchmark="locomo",
    )

    paths = ExperimentPaths(run_dir=run_dir)
    assert not paths.evaluator_model_inventory_path("offline_artifact_metric").exists()
    assert not paths.evaluator_efficiency_observations_path(
        "offline_artifact_metric"
    ).exists()


class _FakeResponsesClient:
    """模拟 OpenAI Responses API 和 Chat Completions client。"""

    def __init__(self, *, text: str, input_tokens: int, output_tokens: int) -> None:
        """保存 fake 输出文本和 usage。"""

        self.calls: list[dict[str, object]] = []
        self.responses = SimpleNamespace(create=self._create)
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create_chat_completion)
        )
        self._text = text
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens

    def _create(self, **kwargs: object) -> object:
        """记录请求参数并返回带 usage 的 fake response。"""

        self.calls.append(kwargs)
        return SimpleNamespace(
            output_text=self._text,
            usage=SimpleNamespace(
                input_tokens=self._input_tokens,
                output_tokens=self._output_tokens,
            ),
        )

    def _create_chat_completion(self, **kwargs: object) -> object:
        """记录 Chat Completions 请求，并返回带 usage 的 fake response。"""

        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self._text),
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=self._input_tokens,
                completion_tokens=self._output_tokens,
            ),
        )


def _build_minimal_run_dir(tmp_path: Path) -> Path:
    """创建只有一个问题的标准 prediction artifact 目录。"""

    run_dir = ExperimentPaths.create(tmp_path / "unit-run").run_dir
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "runner": "generic_conversation_qa_prediction",
                "run_id": "unit-run",
                "benchmark_name": "locomo",
                "method_name": "fake-method",
                "model_name": "fake-model",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _write_jsonl(
        run_dir / "artifacts" / "public_questions.jsonl",
        [
            {
                "question_id": "conv-1:q1",
                "conversation_id": "conv-1",
                "question_text": "Where did Alice move?",
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
    return run_dir


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    """写入测试用 JSONL。"""

    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
