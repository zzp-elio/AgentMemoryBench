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
            text="true",
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


class _FakeResponsesClient:
    """模拟 OpenAI Responses API client。"""

    def __init__(self, *, text: str, input_tokens: int, output_tokens: int) -> None:
        """保存 fake 输出文本和 usage。"""

        self.calls: list[dict[str, object]] = []
        self.responses = SimpleNamespace(create=self._create)
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
