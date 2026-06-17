"""效率 observation 标准 artifact 的路径、写入、读取和冲突测试。"""

from __future__ import annotations

import json

import pytest

from memory_benchmark.core import ConfigurationError
from memory_benchmark.observability.efficiency import (
    ConversationEfficiencyObservation,
    EfficiencyArtifactStore,
    EfficiencyStage,
    LLMCallObservation,
    MeasurementSource,
    ModelDescriptor,
    QuestionEfficiencyObservation,
)
from memory_benchmark.storage import ExperimentPaths


def _model_descriptor(model_id: str = "answer-llm") -> ModelDescriptor:
    """构造测试用 API LLM 身份。"""

    return ModelDescriptor(
        model_id=model_id,
        model_name="gpt-4o-mini",
        model_role="answer_llm",
        execution_mode="api",
        tokenizer_name="gpt-4o-mini",
    )


def _conversation_observation(
    *,
    observation_id: str = "build-1",
    latency_ms: float = 8.0,
) -> ConversationEfficiencyObservation:
    """构造测试用 conversation observation。"""

    return ConversationEfficiencyObservation(
        observation_id=observation_id,
        conversation_id="conv-1",
        memory_build_total_latency_ms=latency_ms,
    )


def _question_observation(
    *,
    observation_id: str = "question-1",
) -> QuestionEfficiencyObservation:
    """构造测试用 question observation。"""

    return QuestionEfficiencyObservation(
        observation_id=observation_id,
        conversation_id="conv-1",
        question_id="q-1",
        retrieval_latency_ms=1.5,
        unsupported_reason=None,
        injected_memory_context_tokens=12,
        answer_generation_latency_ms=2.5,
    )


def test_experiment_paths_expose_prediction_and_evaluator_efficiency_artifacts(
    tmp_path,
) -> None:
    """标准目录应为 prediction 和每个 evaluator 提供互不覆盖的路径。"""

    paths = ExperimentPaths.create(tmp_path / "run")

    assert paths.prediction_model_inventory_path.name == (
        "model_inventory.prediction.json"
    )
    assert paths.prediction_efficiency_observations_path.name == (
        "efficiency_observations.prediction.jsonl"
    )
    assert paths.evaluator_model_inventory_path("locomo_judge_accuracy").name == (
        "model_inventory.locomo_judge_accuracy.json"
    )
    assert paths.evaluator_efficiency_observations_path(
        "locomo_judge_accuracy"
    ).name == "efficiency_observations.locomo_judge_accuracy.jsonl"


def test_evaluator_efficiency_path_rejects_path_escape(tmp_path) -> None:
    """evaluator metric 名不能通过路径片段逃逸 artifacts 目录。"""

    paths = ExperimentPaths.create(tmp_path / "run")

    with pytest.raises(ConfigurationError, match="metric_name"):
        paths.evaluator_efficiency_observations_path("../escape")


def test_evaluator_efficiency_paths_reject_reserved_prediction_name(
    tmp_path,
) -> None:
    """evaluator 不能使用会覆盖 prediction artifact 的保留名称。"""

    paths = ExperimentPaths.create(tmp_path / "run")

    with pytest.raises(ConfigurationError, match="reserved"):
        paths.evaluator_model_inventory_path("prediction")
    with pytest.raises(ConfigurationError, match="reserved"):
        paths.evaluator_efficiency_observations_path("prediction")


def test_store_writes_sorted_model_inventory(tmp_path) -> None:
    """模型清单应按 model_id 稳定排序并带 schema 版本。"""

    paths = ExperimentPaths.create(tmp_path / "run")
    store = EfficiencyArtifactStore.for_prediction(paths)

    store.write_model_inventory(
        [_model_descriptor("z-model"), _model_descriptor("a-model")]
    )

    payload = json.loads(
        paths.prediction_model_inventory_path.read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == 1
    assert [model["model_id"] for model in payload["models"]] == [
        "a-model",
        "z-model",
    ]


def test_store_rejects_duplicate_model_id(tmp_path) -> None:
    """同一 run 的 model_id 必须唯一，不能让 observation 指向歧义模型。"""

    store = EfficiencyArtifactStore.for_prediction(
        ExperimentPaths.create(tmp_path / "run")
    )

    with pytest.raises(ConfigurationError, match="duplicate model_id"):
        store.write_model_inventory(
            [_model_descriptor("duplicate"), _model_descriptor("duplicate")]
        )


def test_merge_observations_is_idempotent_and_sorted(tmp_path) -> None:
    """重复提交同内容 observation 应幂等，文件按 observation_id 稳定排序。"""

    paths = ExperimentPaths.create(tmp_path / "run")
    store = EfficiencyArtifactStore.for_prediction(paths)
    build = _conversation_observation(observation_id="z-build")
    question = _question_observation(observation_id="a-question")

    store.merge_observations([build, question])
    store.merge_observations([build])

    records = store.read_observations()
    assert [record.observation_id for record in records] == [
        "a-question",
        "z-build",
    ]
    assert isinstance(records[0], QuestionEfficiencyObservation)
    assert isinstance(records[1], ConversationEfficiencyObservation)


def test_merge_observations_rejects_conflicting_same_id(tmp_path) -> None:
    """同一 observation_id 内容变化时必须报错，不能覆盖实验事实。"""

    store = EfficiencyArtifactStore.for_prediction(
        ExperimentPaths.create(tmp_path / "run")
    )
    store.merge_observations(
        [_conversation_observation(observation_id="same", latency_ms=8.0)]
    )

    with pytest.raises(ConfigurationError, match="conflicting observation_id"):
        store.merge_observations(
            [_conversation_observation(observation_id="same", latency_ms=9.0)]
        )


@pytest.mark.parametrize("second_latency_ms", [8.0, 9.0])
def test_store_rejects_preexisting_duplicate_observation_ids(
    tmp_path,
    second_latency_ms,
) -> None:
    """磁盘上已有重复 id 时必须报错，不能静默选择最后一条。"""

    paths = ExperimentPaths.create(tmp_path / "run")
    first = _conversation_observation(
        observation_id="duplicate",
        latency_ms=8.0,
    ).to_dict()
    second = _conversation_observation(
        observation_id="duplicate",
        latency_ms=second_latency_ms,
    ).to_dict()
    paths.prediction_efficiency_observations_path.write_text(
        "\n".join(
            [
                json.dumps(first, ensure_ascii=False),
                json.dumps(second, ensure_ascii=False),
                "",
            ]
        ),
        encoding="utf-8",
    )
    store = EfficiencyArtifactStore.for_prediction(paths)

    with pytest.raises(ConfigurationError, match="duplicate observation_id"):
        store.read_observations()
    with pytest.raises(ConfigurationError, match="duplicate observation_id"):
        store.merge_observations([])


def test_store_round_trips_llm_observation_enum_fields(tmp_path) -> None:
    """JSONL 读取后应重建强类型 stage 和 measurement source。"""

    store = EfficiencyArtifactStore.for_prediction(
        ExperimentPaths.create(tmp_path / "run")
    )
    store.merge_observations(
        [
            LLMCallObservation(
                observation_id="llm-1",
                stage=EfficiencyStage.ANSWER,
                model_id="answer-llm",
                input_tokens=20,
                output_tokens=3,
                token_measurement_source=MeasurementSource.API_USAGE,
                conversation_id="conv-1",
                question_id="q-1",
            )
        ]
    )

    record = store.read_observations()[0]
    assert isinstance(record, LLMCallObservation)
    assert record.stage is EfficiencyStage.ANSWER
    assert record.token_measurement_source is MeasurementSource.API_USAGE


def test_store_rejects_unknown_observation_type(tmp_path) -> None:
    """未知 observation_type 不能被宽松当作普通字典读取。"""

    paths = ExperimentPaths.create(tmp_path / "run")
    paths.prediction_efficiency_observations_path.write_text(
        '{"observation_type":"unknown","observation_id":"x"}\n',
        encoding="utf-8",
    )
    store = EfficiencyArtifactStore.for_prediction(paths)

    with pytest.raises(ConfigurationError, match="observation_type"):
        store.read_observations()
