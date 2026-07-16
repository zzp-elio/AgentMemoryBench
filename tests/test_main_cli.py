"""测试统一 CLI command service 和后续 argparse 入口。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from memory_benchmark.cli import commands
from memory_benchmark.cli import main as main_cli
from memory_benchmark.cli.commands import (
    CalibrationSmokeCommand,
    EvaluateCommand,
    PredictCommand,
    RunCommand,
    RunCommandResult,
    RunVariantResult,
    execute_evaluate,
    execute_calibrate_smoke,
    execute_predict,
    execute_run,
)
from memory_benchmark.cli.run_prediction import (
    PredictionBatchResult,
    PredictionVariantResult,
)
from memory_benchmark.core import ConfigurationError
from memory_benchmark.methods.config_track import (
    build_native_track_identity,
    resolve_config_track,
)
from memory_benchmark.methods.registry import resolve_registered_build_identity
from memory_benchmark.runners import EvaluationRunSummary
from memory_benchmark.runners.prediction import PredictionRunSummary


pytestmark = pytest.mark.unit
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _predict_command(tmp_path: Path, **overrides) -> PredictCommand:
    """构造可按需覆盖字段的最小 prediction command。"""

    values = {
        "project_root": tmp_path,
        "method": "mem0",
        "benchmark": "locomo",
        "profile": "smoke",
        "variant": None,
        "run_id": "run-1",
        "resume": False,
        "confirm_api": True,
        "confirm_full": False,
        "smoke_turn_limit": 3,
        "smoke_conversation_limit": 1,
        "smoke_max_workers": 1,
        "max_new_conversations": None,
        "question_limit_per_conversation": None,
        "enable_efficiency_observability": True,
    }
    values.update(overrides)
    return PredictCommand(**values)


def _write_manifest(tmp_path: Path, run_id: str, benchmark: str = "locomo") -> Path:
    """写入 command service 读取的最小 run manifest。"""

    run_dir = tmp_path / "outputs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "benchmark_name": benchmark,
                "method_name": "Mem0",
            }
        ),
        encoding="utf-8",
    )
    return run_dir


def test_resolve_run_dir_finds_old_hierarchical_output_layout(tmp_path: Path) -> None:
    """evaluate 应继续找到不含 track 段的旧 CLI v2 分层目录。"""

    run_dir = tmp_path / "outputs" / "runs" / "mem0" / "locomo" / "smoke" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "benchmark_name": "locomo",
                "method_name": "Mem0",
            }
        ),
        encoding="utf-8",
    )

    assert commands._resolve_run_dir(tmp_path, "run-1") == run_dir.resolve()


def test_resolve_run_dir_finds_track_aware_output_layout(tmp_path: Path) -> None:
    """evaluate 应通过递归 manifest 查找带 track 段的新布局。"""

    run_dir = (
        tmp_path
        / "outputs"
        / "runs"
        / "mem0"
        / "locomo"
        / "smoke"
        / "unified"
        / "run-1"
    )
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "benchmark_name": "locomo",
                "method_name": "Mem0",
            }
        ),
        encoding="utf-8",
    )

    assert commands._resolve_run_dir(tmp_path, "run-1") == run_dir.resolve()


def test_resolve_run_dir_not_found_fails_fast_with_near_miss_hint(
    tmp_path: Path,
) -> None:
    """三布局均未命中时应 fail-fast，并提示 variant 后缀等相近 run id。"""

    real = (
        tmp_path
        / "outputs"
        / "runs"
        / "lightmem"
        / "longmemeval"
        / "s-cleaned"
        / "smoke"
        / "unified"
        / "run-1-s-cleaned"
    )
    real.mkdir(parents=True)
    (real / "manifest.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ConfigurationError) as excinfo:
        commands._resolve_run_dir(tmp_path, "run-1")
    message = str(excinfo.value)
    assert "not found" in message
    assert "run-1-s-cleaned" in message


def test_resolve_run_dir_not_found_without_candidates_has_no_hint(
    tmp_path: Path,
) -> None:
    """没有相近 run id 时报错不带建议，但仍列出两处查找位置。"""

    (tmp_path / "outputs" / "runs").mkdir(parents=True)
    with pytest.raises(ConfigurationError) as excinfo:
        commands._resolve_run_dir(tmp_path, "totally-absent")
    message = str(excinfo.value)
    assert "not found" in message
    assert "Closest run ids" not in message


def test_resolve_run_dir_rejects_ambiguous_hierarchical_run_id(
    tmp_path: Path,
) -> None:
    """同一个 run_id 出现在多个分层目录时，evaluate 必须要求用户消歧。"""

    first = tmp_path / "outputs" / "runs" / "mem0" / "locomo" / "smoke" / "run-1"
    second = first.parent / "unified" / "run-1"
    for run_dir in (first, second):
        run_dir.mkdir(parents=True)
        (run_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "run_id": "run-1",
                    "benchmark_name": "locomo",
                    "method_name": "method",
                }
            ),
            encoding="utf-8",
        )

    with pytest.raises(ConfigurationError, match="ambiguous"):
        commands._resolve_run_dir(tmp_path, "run-1")


def test_resolve_run_dir_rejects_flat_and_hierarchical_collision(
    tmp_path: Path,
) -> None:
    """同名 run 同时存在 legacy 和 CLI v2 目录时，evaluate 不能静默选错。"""

    _write_manifest(tmp_path, "run-1")
    nested = tmp_path / "outputs" / "runs" / "mem0" / "locomo" / "smoke" / "run-1"
    nested.mkdir(parents=True)
    (nested / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "benchmark_name": "locomo",
                "method_name": "Mem0",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="ambiguous"):
        commands._resolve_run_dir(tmp_path, "run-1")


def test_execute_predict_delegates_to_registered_prediction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """predict command 应转发明确参数，不复制 method/runner 实现。"""

    calls: list[dict[str, object]] = []
    expected = PredictionBatchResult(
        benchmark="locomo",
        selector="locomo10",
        runs=(
            PredictionVariantResult(
                variant="locomo10",
                run_id="run-1",
                summary=SimpleNamespace(run_id="run-1"),
            ),
        ),
    )
    monkeypatch.setattr(
        commands,
        "run_registered_conversation_qa_prediction",
        lambda **kwargs: calls.append(kwargs) or expected,
    )

    result = execute_predict(_predict_command(tmp_path))

    assert result is expected
    assert calls == [
        {
            "method_name": "mem0",
            "method_class": None,
            "allow_unsafe_custom_parallel": False,
            "benchmark_name": "locomo",
            "project_root": tmp_path,
            "profile_name": "smoke",
            "config_track": "unified",
            "variant": None,
            "run_id": "run-1",
            "resume": False,
            "confirm_api": True,
            "confirm_full": False,
            "smoke_turn_limit": 3,
            "smoke_round_limit": None,
            "smoke_conversation_limit": 1,
            "smoke_session_limit": None,
            "smoke_max_workers": 1,
            "max_new_conversations": None,
            "retry_failed_conversations": False,
            "question_limit_per_conversation": None,
            "enable_efficiency_observability": True,
            "answer_prompt_file": None,
            "answer_prompt_profile": "default",
            "output_layout": "flat",
            "membench_sources": (),
        }
    ]


def test_execute_predict_can_enable_efficiency_observability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """predict command 可显式开启效率观测，供单 run 成本调试使用。"""

    calls: list[dict[str, object]] = []
    expected = PredictionBatchResult(
        benchmark="locomo",
        selector="locomo10",
        runs=(),
    )
    monkeypatch.setattr(
        commands,
        "run_registered_conversation_qa_prediction",
        lambda **kwargs: calls.append(kwargs) or expected,
    )

    result = execute_predict(
        _predict_command(tmp_path, enable_efficiency_observability=True)
    )

    assert result is expected
    assert calls[0]["enable_efficiency_observability"] is True


def test_execute_predict_forwards_max_new_conversations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """predict command 应把本次命令预算透传给 registered prediction。"""

    calls: list[dict[str, object]] = []
    expected = PredictionBatchResult(
        benchmark="locomo",
        selector="locomo10",
        runs=(),
    )
    monkeypatch.setattr(
        commands,
        "run_registered_conversation_qa_prediction",
        lambda **kwargs: calls.append(kwargs) or expected,
    )

    result = execute_predict(
        _predict_command(tmp_path, max_new_conversations=2)
    )

    assert result is expected
    assert calls[0]["max_new_conversations"] == 2


def test_execute_calibrate_smoke_delegates_to_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """command service 不实现校准调度，只转发强类型 calibration command。"""

    command = CalibrationSmokeCommand(
        project_root=tmp_path,
        methods=("mem0",),
        benchmarks=("locomo",),
        run_prefix="calib",
    )
    expected = SimpleNamespace(failed_count=0)
    received: list[CalibrationSmokeCommand] = []
    monkeypatch.setattr(
        commands,
        "run_cost_calibration_smoke",
        lambda selected: received.append(selected) or expected,
    )

    result = execute_calibrate_smoke(command)

    assert result is expected
    assert received == [command]


def test_execute_evaluate_runs_offline_f1_without_loading_openai(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """离线 F1 只能构造 evaluator 和 artifact runner，不能读取 secret。"""

    run_dir = _write_manifest(tmp_path, "run-1")
    evaluator = object()
    summary = SimpleNamespace(metric_name="locomo_f1")
    calls: list[tuple[Path, object, str]] = []
    monkeypatch.setattr(
        commands,
        "create_evaluator",
        lambda metric_name, benchmark_name, **kwargs: evaluator,
    )
    monkeypatch.setattr(
        commands,
        "run_artifact_evaluation",
        lambda path, selected, expected_benchmark, max_workers=1: (
            calls.append((Path(path), selected, expected_benchmark)) or summary
        ),
    )
    results = execute_evaluate(
        EvaluateCommand(
            project_root=tmp_path,
            run_id="run-1",
            metrics=("locomo-f1",),
        )
    )

    assert results == (summary,)
    assert calls == [(run_dir, evaluator, "locomo")]


def test_execute_evaluate_rejects_unconfirmed_judge_before_profile_or_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM judge 未确认成本时不能加载 profile、secret 或构造 evaluator。"""

    _write_manifest(tmp_path, "run-1")
    monkeypatch.setattr(
        commands,
        "load_evaluator_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("profile must not load before confirmation")
        ),
    )

    with pytest.raises(ConfigurationError, match="confirm-api"):
        execute_evaluate(
            EvaluateCommand(
                project_root=tmp_path,
                run_id="run-1",
                metrics=("locomo-judge",),
                confirm_api=False,
            )
        )


def test_memoryos_native_evaluate_falls_back_to_framework_default_judge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MemoryOS 无 native judge profile 时应保留 create_evaluator 默认实例。"""

    run_dir = _write_manifest(tmp_path, "memoryos-native")
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["method_name"] = "MemoryOS"
    manifest["method"] = {"config_track": "native"}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    default_evaluator = object()
    observed: list[object] = []
    monkeypatch.setattr(
        commands,
        "load_evaluator_profile",
        lambda **kwargs: SimpleNamespace(mode="compact", model="gpt-4o-mini"),
    )
    monkeypatch.setattr(
        commands,
        "create_evaluator",
        lambda *args, **kwargs: default_evaluator,
    )
    monkeypatch.setattr(
        commands,
        "run_artifact_evaluation",
        lambda run_dir, evaluator, benchmark, max_workers=1: (
            observed.append(evaluator) or SimpleNamespace(metric_name="locomo_judge")
        ),
    )

    execute_evaluate(
        EvaluateCommand(
            project_root=tmp_path,
            run_id="memoryos-native",
            metrics=("locomo-judge",),
            confirm_api=True,
        )
    )

    assert observed == [default_evaluator]


def _native_track_identity_dict(
    method: str,
    benchmark: str,
    config_manifest: dict[str, object],
) -> dict[str, object]:
    """构造 command evaluate 测试使用的合法 registered native identity。"""

    bundle = resolve_config_track(method, benchmark, "native")
    assert bundle is not None
    return build_native_track_identity(
        build_identity=resolve_registered_build_identity(method, config_manifest),
        bundle=bundle,
    ).to_manifest_dict()


def test_memoryos_v1_native_evaluate_validates_identity_and_uses_framework_judge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MemoryOS v1 明确 fallback 时必须验证身份并保留 framework evaluator。"""

    run_dir = _write_manifest(tmp_path, "memoryos-v1-native")
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["method_name"] = "MemoryOS"
    track_identity = _native_track_identity_dict(
        "memoryos",
        "locomo",
        {
            "engine": "memoryos-pypi",
            "embedding_model_name": "sentence-transformers/all-MiniLM-L6-v2",
        },
    )
    manifest["method"] = {
        "config_track": "native",
        "contract_version": "v1",
        "track_identity": track_identity,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    default_evaluator = object()
    observed: list[object] = []
    monkeypatch.setattr(
        commands,
        "load_evaluator_profile",
        lambda **kwargs: SimpleNamespace(mode="compact", model="gpt-4o-mini"),
    )
    monkeypatch.setattr(
        commands,
        "create_evaluator",
        lambda *args, **kwargs: default_evaluator,
    )
    monkeypatch.setattr(
        commands,
        "run_artifact_evaluation",
        lambda run_dir, evaluator, benchmark, max_workers=1: (
            observed.append(evaluator) or SimpleNamespace(metric_name="locomo_judge")
        ),
    )

    execute_evaluate(
        EvaluateCommand(
            project_root=tmp_path,
            run_id="memoryos-v1-native",
            metrics=("locomo-judge",),
            confirm_api=True,
        )
    )
    assert observed == [default_evaluator]


def test_mem0_v1_native_evaluate_uses_registered_official_judge_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """只有 identity 声明 official_parity 时才应用 Mem0 native judge prompt。"""

    run_dir = _write_manifest(tmp_path, "mem0-v1-native")
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    track_identity = _native_track_identity_dict(
        "mem0",
        "locomo",
        {
            "embedding_provider": "huggingface",
            "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
            "embedding_dimensions": 384,
        },
    )
    manifest["method"] = {
        "config_track": "native",
        "contract_version": "v1",
        "track_identity": track_identity,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    default_evaluator = object()
    native_evaluator = object()
    observed: list[object] = []
    monkeypatch.setattr(
        commands,
        "load_evaluator_profile",
        lambda **kwargs: SimpleNamespace(mode="compact", model="gpt-4o-mini"),
    )
    monkeypatch.setattr(
        commands,
        "create_evaluator",
        lambda *args, **kwargs: default_evaluator,
    )
    monkeypatch.setattr(
        commands,
        "LoCoMoJudgeEvaluator",
        lambda **kwargs: native_evaluator,
    )
    monkeypatch.setattr(
        commands,
        "run_artifact_evaluation",
        lambda run_dir, evaluator, benchmark, max_workers=1: (
            observed.append(evaluator) or SimpleNamespace(metric_name="locomo_judge")
        ),
    )

    execute_evaluate(
        EvaluateCommand(
            project_root=tmp_path,
            run_id="mem0-v1-native",
            metrics=("locomo-judge",),
            confirm_api=True,
        )
    )
    assert observed == [native_evaluator]


def test_v1_native_evaluate_rejects_identity_bundle_contradiction(
    tmp_path: Path,
) -> None:
    """v1 manifest 的 judge/model 来源与注册 readout bundle 冲突时 fail-fast。"""

    run_dir = _write_manifest(tmp_path, "mem0-v1-contradiction")
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    track_identity = _native_track_identity_dict(
        "mem0",
        "locomo",
        {
            "embedding_provider": "huggingface",
            "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
            "embedding_dimensions": 384,
        },
    )
    track_identity["judge_model_source"] = "official_parity"
    manifest["method"] = {
        "config_track": "native",
        "contract_version": "v1",
        "track_identity": track_identity,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="disagrees with registered"):
        execute_evaluate(
            EvaluateCommand(
                project_root=tmp_path,
                run_id="mem0-v1-contradiction",
                metrics=("locomo-f1",),
            )
        )


@pytest.mark.parametrize(
    "malformation",
    (
        "identity_without_version",
        "version_without_identity",
        "inner_version_skew",
        "identity_extra_field",
        "embedding_missing_field",
    ),
)
def test_v1_evaluate_strictly_parses_identity_and_version_pair(
    tmp_path: Path,
    malformation: str,
) -> None:
    """evaluate 对声明 v1 的 artifact 必须严格解析，只有完全旧 artifact 可兼容。"""

    run_id = f"malformed-{malformation}"
    run_dir = _write_manifest(tmp_path, run_id)
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    identity = _native_track_identity_dict(
        "mem0",
        "locomo",
        {
            "embedding_provider": "huggingface",
            "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
            "embedding_dimensions": 384,
        },
    )
    method_manifest: dict[str, object] = {"config_track": "native"}
    if malformation != "identity_without_version":
        method_manifest["contract_version"] = "v1"
    if malformation != "version_without_identity":
        method_manifest["track_identity"] = identity
    if malformation == "inner_version_skew":
        identity["contract_version"] = "v2"
    elif malformation == "identity_extra_field":
        identity["unexpected"] = True
    elif malformation == "embedding_missing_field":
        embedding = identity["embedding"]
        assert isinstance(embedding, dict)
        embedding.pop("instruction")
    manifest["method"] = method_manifest
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ConfigurationError):
        execute_evaluate(
            EvaluateCommand(
                project_root=tmp_path,
                run_id=run_id,
                metrics=("locomo-f1",),
            )
        )


def test_execute_run_stops_when_prediction_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """prediction 失败时不得进入 evaluation。"""

    monkeypatch.setattr(
        commands,
        "execute_predict",
        lambda command: (_ for _ in ()).throw(RuntimeError("prediction failed")),
    )
    monkeypatch.setattr(
        commands,
        "execute_evaluate",
        lambda command: (_ for _ in ()).throw(
            AssertionError("evaluation must not run")
        ),
    )

    with pytest.raises(RuntimeError, match="prediction failed"):
        execute_run(
            RunCommand(
                prediction=_predict_command(tmp_path),
                metrics=("locomo-f1",),
            )
        )


def test_execute_run_evaluates_each_child_independently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """batch prediction 的每个 child 都必须独立触发 evaluation。"""

    prediction_batch = PredictionBatchResult(
        benchmark="longmemeval",
        selector="all",
        runs=(
            PredictionVariantResult(
                variant="s_cleaned",
                run_id="generated-run-s-cleaned",
                summary=PredictionRunSummary(
                    run_id="generated-run-s-cleaned",
                    dataset_name="longmemeval",
                    completed_conversations=1,
                    total_conversations=1,
                    completed_questions=1,
                    total_questions=1,
                    prediction_path=str(tmp_path / "outputs" / "generated-run-s-cleaned" / "artifacts" / "method_predictions.jsonl"),
                    private_label_path=str(tmp_path / "outputs" / "generated-run-s-cleaned" / "artifacts" / "evaluator_private_labels.jsonl"),
                    summary_path=str(tmp_path / "outputs" / "generated-run-s-cleaned" / "summaries" / "summary.json"),
                ),
            ),
            PredictionVariantResult(
                variant="m_cleaned",
                run_id="generated-run-m-cleaned",
                summary=PredictionRunSummary(
                    run_id="generated-run-m-cleaned",
                    dataset_name="longmemeval",
                    completed_conversations=1,
                    total_conversations=1,
                    completed_questions=1,
                    total_questions=1,
                    prediction_path=str(tmp_path / "outputs" / "generated-run-m-cleaned" / "artifacts" / "method_predictions.jsonl"),
                    private_label_path=str(tmp_path / "outputs" / "generated-run-m-cleaned" / "artifacts" / "evaluator_private_labels.jsonl"),
                    summary_path=str(tmp_path / "outputs" / "generated-run-m-cleaned" / "summaries" / "summary.json"),
                ),
            ),
        ),
    )
    s_eval = EvaluationRunSummary(
        run_id="generated-run-s-cleaned",
        benchmark_name="longmemeval",
        metric_name="longmemeval_judge_accuracy",
        total_questions=1,
        mean_score=1.0,
        correct_count=1,
        score_path=str(tmp_path / "outputs" / "generated-run-s-cleaned" / "artifacts" / "answer_scores.longmemeval_judge_accuracy.jsonl"),
        summary_path=str(tmp_path / "outputs" / "generated-run-s-cleaned" / "summaries" / "summary.longmemeval_judge_accuracy.json"),
    )
    m_eval = EvaluationRunSummary(
        run_id="generated-run-m-cleaned",
        benchmark_name="longmemeval",
        metric_name="longmemeval_judge_accuracy",
        total_questions=1,
        mean_score=0.0,
        correct_count=0,
        score_path=str(tmp_path / "outputs" / "generated-run-m-cleaned" / "artifacts" / "answer_scores.longmemeval_judge_accuracy.jsonl"),
        summary_path=str(tmp_path / "outputs" / "generated-run-m-cleaned" / "summaries" / "summary.longmemeval_judge_accuracy.json"),
    )
    received: list[EvaluateCommand] = []
    monkeypatch.setattr(
        commands,
        "execute_predict",
        lambda command: prediction_batch,
    )
    monkeypatch.setattr(
        commands,
        "execute_evaluate",
        lambda command: received.append(command)
        or (
            (s_eval,)
            if command.run_id.endswith("s-cleaned")
            else (m_eval,)
        ),
    )

    result = execute_run(
        RunCommand(
            prediction=_predict_command(
                tmp_path,
                benchmark="longmemeval",
                run_id=None,
                variant="all",
            ),
            metrics=("longmemeval-judge",),
        )
    )

    assert result == RunCommandResult(
        benchmark="longmemeval",
        selector="all",
        runs=(
            RunVariantResult(
                variant="s_cleaned",
                prediction=prediction_batch.runs[0].summary,
                evaluations=(s_eval,),
            ),
            RunVariantResult(
                variant="m_cleaned",
                prediction=prediction_batch.runs[1].summary,
                evaluations=(m_eval,),
            ),
        ),
    )
    assert [command.run_id for command in received] == [
        "generated-run-s-cleaned",
        "generated-run-m-cleaned",
    ]
    assert all(command.confirm_api is True for command in received)


def test_main_help_lists_predict_evaluate_and_run(capsys) -> None:
    """统一入口 help 应明确显示三个子命令。"""

    with pytest.raises(SystemExit) as raised:
        main_cli.main(["--help"])

    assert raised.value.code == 0
    output = capsys.readouterr().out
    assert "predict" in output
    assert "evaluate" in output
    assert "run" in output
    assert "calibrate-smoke" in output


def test_prediction_help_describes_conversation_budget(capsys) -> None:
    """predict 子命令 help 应说明 conversation 预算只属于本次命令、不属于实验 identity。"""

    with pytest.raises(SystemExit) as raised:
        main_cli.main(["predict", "--help"])

    assert raised.value.code == 0
    output = capsys.readouterr().out
    assert "--conversation-budget" in output
    assert "per-command" in output
    assert "identity" in output


def test_prediction_help_describes_retry_failed(capsys) -> None:
    """predict 子命令 help 应说明 failed conversation 默认隔离、需显式重试。"""

    with pytest.raises(SystemExit) as raised:
        main_cli.main(["predict", "--help"])

    assert raised.value.code == 0
    output = capsys.readouterr().out
    assert "--retry-failed" in output
    assert "failed conversations" in output


def test_predict_accepts_custom_method_class_without_builtin_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """用户 method 允许通过 --method-class 指定，且不需要 --method。"""

    captured: dict[str, PredictCommand] = {}

    def fake_execute_predict(command: PredictCommand):
        """捕获 CLI 转换后的 prediction 命令，不执行真实预测。"""

        captured["command"] = command
        return SimpleNamespace(failed_count=0)

    monkeypatch.setattr(main_cli, "execute_predict", fake_execute_predict)

    exit_code = main_cli.main(
        [
            "predict",
            "smoke",
            "--root",
            ".",
            "--method-class",
            "my_pkg.adapter:MyMemory",
            "--benchmark",
            "locomo",
            "--allow-api",
        ]
    )

    assert exit_code == 0
    assert captured["command"].method is None
    assert captured["command"].method_class == "my_pkg.adapter:MyMemory"


def test_predict_rejects_method_and_method_class_together() -> None:
    """内置 method 和用户 method class 不能同时指定。"""

    exit_code = main_cli.main(
        [
            "predict",
            "smoke",
            "--root",
            ".",
            "--method",
            "mem0",
            "--method-class",
            "my_pkg.adapter:MyMemory",
            "--benchmark",
            "locomo",
            "--allow-api",
        ]
    )

    assert exit_code == 2


def test_custom_method_parallel_requires_explicit_unsafe_flag() -> None:
    """用户 method 默认不允许 workers>1，避免并发污染外部状态。"""

    exit_code = main_cli.main(
        [
            "predict",
            "smoke",
            "--root",
            ".",
            "--method-class",
            "my_pkg.adapter:MyMemory",
            "--benchmark",
            "locomo",
            "--workers",
            "2",
            "--allow-api",
        ]
    )

    assert exit_code == 2


def test_calibration_help_describes_max_new_conversations(capsys) -> None:
    """calibrate-smoke help 也应说明该字段只是本次命令预算。"""

    with pytest.raises(SystemExit) as raised:
        main_cli.main(["calibrate-smoke", "--help"])

    assert raised.value.code == 0
    output = capsys.readouterr().out
    assert "--max-new-conversations" in output
    assert "per-command" in output
    assert "identity" in output


def test_main_maps_predict_arguments_to_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """argparse 层只负责构造 PredictCommand 并调用 command service。"""

    received: list[PredictCommand] = []
    monkeypatch.setattr(
        main_cli,
        "execute_predict",
        lambda command: received.append(command)
        or SimpleNamespace(run_id="run-1"),
    )

    exit_code = main_cli.main(
        [
            "predict",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "locomo",
            "--profile",
            "smoke",
            "--variant",
            "custom-selector",
            "--run-id",
            "run-1",
            "--confirm-api",
            "--rounds",
            "3",
            "--conversations",
            "10",
            "--workers",
            "10",
            "--conversation-budget",
            "2",
            "--retry-failed",
        ]
    )

    assert exit_code == 0
    assert received == [
        PredictCommand(
            project_root=tmp_path,
            method="mem0",
            benchmark="locomo",
            profile="smoke",
            variant="custom-selector",
            run_id="run-1",
            confirm_api=True,
            smoke_turn_limit=3,
            smoke_conversation_limit=10,
            smoke_max_workers=10,
            max_new_conversations=2,
            # legacy `--profile smoke` 路径：未传 --questions-per-conversation 时
            # cost-safety 默认取 1（smoke 只评 1 个问题），不再回退到 None。
            question_limit_per_conversation=1,
            retry_failed_conversations=True,
            output_layout="hierarchical",
        )
    ]


def test_main_maps_predict_smoke_v2_arguments_to_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI v2 的 `predict smoke` 应使用直观参数映射到 smoke profile。"""

    received: list[PredictCommand] = []
    monkeypatch.setattr(
        main_cli,
        "execute_predict",
        lambda command: received.append(command)
        or SimpleNamespace(run_id="run-1"),
    )

    exit_code = main_cli.main(
        [
            "predict",
            "smoke",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "locomo",
            "--run-id",
            "20260623-1430-mem0-locomo-smoke",
            "--allow-api",
            "--conversations",
            "2",
            "--rounds",
            "20",
            "--questions-per-conversation",
            "1",
            "--workers",
            "2",
        ]
    )

    assert exit_code == 0
    assert received == [
        PredictCommand(
            project_root=tmp_path,
            method="mem0",
            benchmark="locomo",
            profile="smoke",
            run_id="20260623-1430-mem0-locomo-smoke",
            confirm_api=True,
            smoke_turn_limit=20,
            smoke_round_limit=20,
            smoke_conversation_limit=2,
            smoke_max_workers=2,
            question_limit_per_conversation=1,
            output_layout="hierarchical",
        )
    ]


def test_main_locomo_smoke_defaults_round_limit_from_registered_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未传 --rounds 时，LoCoMo smoke 应归一为已注册 policy 的 1 round，
    而不是全局 legacy 默认值 20。"""

    received: list[PredictCommand] = []
    monkeypatch.setattr(
        main_cli,
        "execute_predict",
        lambda command: received.append(command)
        or SimpleNamespace(run_id="run-1"),
    )

    exit_code = main_cli.main(
        [
            "predict",
            "smoke",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "locomo",
            "--run-id",
            "run-1",
            "--allow-api",
        ]
    )

    assert exit_code == 0
    assert received == [
        PredictCommand(
            project_root=tmp_path,
            method="mem0",
            benchmark="locomo",
            profile="smoke",
            run_id="run-1",
            confirm_api=True,
            smoke_turn_limit=1,
            smoke_round_limit=1,
            smoke_conversation_limit=1,
            question_limit_per_conversation=1,
            output_layout="hierarchical",
        )
    ]


def test_main_locomo_smoke_explicit_rounds_overrides_registered_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """显式 --rounds 2 应覆盖 LoCoMo 已注册 policy 的默认值 1。"""

    received: list[PredictCommand] = []
    monkeypatch.setattr(
        main_cli,
        "execute_predict",
        lambda command: received.append(command)
        or SimpleNamespace(run_id="run-1"),
    )

    exit_code = main_cli.main(
        [
            "predict",
            "smoke",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "locomo",
            "--run-id",
            "run-1",
            "--allow-api",
            "--rounds",
            "2",
        ]
    )

    assert exit_code == 0
    assert received == [
        PredictCommand(
            project_root=tmp_path,
            method="mem0",
            benchmark="locomo",
            profile="smoke",
            run_id="run-1",
            confirm_api=True,
            smoke_turn_limit=2,
            smoke_round_limit=2,
            smoke_conversation_limit=1,
            question_limit_per_conversation=1,
            output_layout="hierarchical",
        )
    ]


def test_main_legacy_predict_smoke_locomo_defaults_round_limit_from_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """legacy `predict --profile smoke` 对 LoCoMo 也要读注册 policy 默认值。"""

    received: list[PredictCommand] = []
    monkeypatch.setattr(
        main_cli,
        "execute_predict",
        lambda command: received.append(command)
        or SimpleNamespace(run_id="run-1"),
    )

    exit_code = main_cli.main(
        [
            "predict",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "locomo",
            "--profile",
            "smoke",
            "--run-id",
            "run-1",
            "--confirm-api",
        ]
    )

    assert exit_code == 0
    assert received == [
        PredictCommand(
            project_root=tmp_path,
            method="mem0",
            benchmark="locomo",
            profile="smoke",
            run_id="run-1",
            confirm_api=True,
            smoke_turn_limit=1,
            question_limit_per_conversation=1,
            output_layout="hierarchical",
        )
    ]


def test_main_legacy_predict_smoke_longmemeval_uses_registered_policy_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已注册 smoke policy 的 LongMemEval 在 legacy --profile 路径下用 policy 默认 1 round。"""

    received: list[PredictCommand] = []
    monkeypatch.setattr(
        main_cli,
        "execute_predict",
        lambda command: received.append(command)
        or SimpleNamespace(run_id="run-1"),
    )

    exit_code = main_cli.main(
        [
            "predict",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "longmemeval",
            "--profile",
            "smoke",
            "--run-id",
            "run-1",
            "--confirm-api",
        ]
    )

    assert exit_code == 0
    assert received == [
        PredictCommand(
            project_root=tmp_path,
            method="mem0",
            benchmark="longmemeval",
            profile="smoke",
            run_id="run-1",
            confirm_api=True,
            smoke_turn_limit=1,
            question_limit_per_conversation=1,
            output_layout="hierarchical",
        )
    ]


def test_main_rejects_turns_for_locomo_smoke(tmp_path: Path) -> None:
    """LoCoMo smoke 的历史轴是 rounds，不接受 --turns。"""

    exit_code = main_cli.main(
        [
            "predict",
            "smoke",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "locomo",
            "--allow-api",
            "--turns",
            "3",
        ]
    )

    assert exit_code == 2


def test_main_rejects_sources_for_locomo_smoke(tmp_path: Path) -> None:
    """LoCoMo smoke 的历史轴是 rounds，不接受 --sources。"""

    exit_code = main_cli.main(
        [
            "predict",
            "smoke",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "locomo",
            "--allow-api",
            "--sources",
            "2",
        ]
    )

    assert exit_code == 2


@pytest.mark.parametrize("axis", ["--turns", "--sources"])
def test_main_rejects_unwired_smoke_axes_for_other_benchmarks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    axis: str,
) -> None:
    """尚未声明对应 policy 的 benchmark 不能静默吞掉未接线的裁剪轴。"""

    dispatched: list[PredictCommand] = []
    monkeypatch.setattr(
        main_cli,
        "execute_predict",
        lambda command: dispatched.append(command)
        or SimpleNamespace(run_id="should-not-run"),
    )

    exit_code = main_cli.main(
        [
            "predict",
            "smoke",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "longmemeval",
            "--allow-api",
            axis,
            "3",
        ]
    )

    assert exit_code == 2
    assert dispatched == []


def test_main_maps_halumem_fixed_smoke_shape_to_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HaluMem smoke 无裁剪旗标时应使用声明的固定形状。"""

    received: list[PredictCommand] = []
    monkeypatch.setattr(
        main_cli,
        "execute_predict",
        lambda command: received.append(command)
        or SimpleNamespace(run_id="run-1"),
    )

    exit_code = main_cli.main(
        [
            "predict",
            "smoke",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "halumem",
            "--run-id",
            "mem0-halumem-smoke",
            "--allow-api",
        ]
    )

    assert exit_code == 0
    assert received == [
        PredictCommand(
            project_root=tmp_path,
            method="mem0",
            benchmark="halumem",
            profile="smoke",
            run_id="mem0-halumem-smoke",
            confirm_api=True,
            smoke_turn_limit=4,
            smoke_round_limit=None,
            smoke_session_limit=None,
            smoke_conversation_limit=1,
            question_limit_per_conversation=1,
            output_layout="hierarchical",
        )
    ]


@pytest.mark.parametrize(
    "axis",
    [
        ("--rounds", "2"),
        ("--turns", "2"),
        ("--sessions", "2"),
        ("--conversations", "2"),
        ("--questions-per-conversation", "2"),
    ],
)
def test_main_rejects_all_cropping_parameters_for_halumem_smoke(
    tmp_path: Path, axis: tuple[str, str]
) -> None:
    """HaluMem 固定 smoke 不接受任何显式裁剪参数。"""

    exit_code = main_cli.main(
        [
            "predict",
            "smoke",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "halumem",
            "--allow-api",
            *axis,
        ]
    )

    assert exit_code == 2


def test_main_rejects_sessions_for_non_halumem_smoke(tmp_path: Path) -> None:
    """非 HaluMem benchmark 不接受 session 轴裁剪。"""

    exit_code = main_cli.main(
        [
            "predict",
            "smoke",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "locomo",
            "--allow-api",
            "--sessions",
            "1",
        ]
    )

    assert exit_code == 2


def test_main_maps_predict_formal_v2_arguments_to_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI v2 的 `predict formal` 应映射到 official-full profile 和正式预算。"""

    received: list[PredictCommand] = []
    monkeypatch.setattr(
        main_cli,
        "execute_predict",
        lambda command: received.append(command)
        or SimpleNamespace(run_id="run-1"),
    )

    exit_code = main_cli.main(
        [
            "predict",
            "formal",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "longmemeval",
            "--variant",
            "s_cleaned",
            "--run-id",
            "20260623-1600-mem0-longmemeval-s-formal",
            "--allow-api",
            "--conversation-budget",
            "5",
            "--workers",
            "4",
        ]
    )

    assert exit_code == 0
    assert received == [
        PredictCommand(
            project_root=tmp_path,
            method="mem0",
            benchmark="longmemeval",
            profile="official-full",
            variant="s_cleaned",
            run_id="20260623-1600-mem0-longmemeval-s-formal",
            confirm_api=True,
            confirm_full=True,
            smoke_round_limit=None,
            smoke_max_workers=4,
            max_new_conversations=5,
            output_layout="hierarchical",
        )
    ]


def test_predict_smoke_rejects_resume_and_retry_failed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """smoke 很小，不支持 resume / retry failed 的复杂状态语义。"""

    exit_code = main_cli.main(
        [
            "predict",
            "smoke",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "locomo",
            "--allow-api",
            "--resume",
            "--retry-failed",
        ]
    )

    assert exit_code == 2
    assert "predict smoke does not support --resume" in capsys.readouterr().err


def test_predict_smoke_rejects_membench_sources_on_other_benchmark(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--membench-sources 传给非 membench 必须 fail-fast，不许静默吞掉。"""

    exit_code = main_cli.main(
        [
            "predict",
            "smoke",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "locomo",
            "--allow-api",
            "--membench-sources",
            "first_high",
        ]
    )

    assert exit_code == 2
    assert "--membench-sources is only supported for MemBench smoke" in (
        capsys.readouterr().err
    )


@pytest.mark.parametrize("unsupported_axis", ["--turns", "--sessions", "--sources"])
def test_predict_beam_smoke_rejects_unwired_history_axes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    unsupported_axis: str,
) -> None:
    """BEAM 只接线 rounds，其他历史轴必须明确 fail-fast。"""

    exit_code = main_cli.main(
        [
            "predict",
            "smoke",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "beam",
            "--allow-api",
            unsupported_axis,
            "1",
        ]
    )

    assert exit_code == 2
    assert "BEAM smoke uses --rounds" in capsys.readouterr().err


def test_predict_formal_rejects_membench_sources(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--membench-sources 是 smoke 调试旋钮；formal 静默忽略会误导为部分源运行。"""

    exit_code = main_cli.main(
        [
            "predict",
            "formal",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "membench",
            "--allow-api",
            "--membench-sources",
            "first_high",
        ]
    )

    assert exit_code == 2
    assert "predict formal does not support --membench-sources" in (
        capsys.readouterr().err
    )


def test_predict_formal_rejects_question_limit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """formal 必须完整回答所选 conversation，不能按 question 裁剪。"""

    exit_code = main_cli.main(
        [
            "predict",
            "formal",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "locomo",
            "--allow-api",
            "--questions-per-conversation",
            "1",
        ]
    )

    assert exit_code == 2
    assert "predict formal does not support --questions-per-conversation" in (
        capsys.readouterr().err
    )


def test_predict_formal_retry_failed_requires_resume(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """failed conversation 只有 resume 场景下才允许显式重试。"""

    exit_code = main_cli.main(
        [
            "predict",
            "formal",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "locomo",
            "--allow-api",
            "--retry-failed",
        ]
    )

    assert exit_code == 2
    assert "--retry-failed requires --resume" in capsys.readouterr().err


def test_main_maps_predict_efficiency_flag_to_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """predict 默认开启 efficiency observation，避免真实长实验丢成本记录。"""

    received: list[PredictCommand] = []
    monkeypatch.setattr(
        main_cli,
        "execute_predict",
        lambda command: received.append(command)
        or SimpleNamespace(run_id="run-1"),
    )

    exit_code = main_cli.main(
        [
            "predict",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "locomo",
            "--profile",
            "smoke",
            "--run-id",
            "run-1",
            "--confirm-api",
        ]
    )

    assert exit_code == 0
    assert received == [
        PredictCommand(
            project_root=tmp_path,
            method="mem0",
            benchmark="locomo",
            profile="smoke",
            run_id="run-1",
            confirm_api=True,
            # LoCoMo 注册了 BenchmarkSmokePolicy(default_history_limit=1)；未传
            # --rounds 时不再退回全局 legacy 默认值 20。
            smoke_turn_limit=1,
            question_limit_per_conversation=1,
            enable_efficiency_observability=True,
            output_layout="hierarchical",
        )
    ]


def test_main_maps_predict_disable_efficiency_flag_to_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """用户显式关闭时，argparse 才把 efficiency observation 传为 False。"""

    received: list[PredictCommand] = []
    monkeypatch.setattr(
        main_cli,
        "execute_predict",
        lambda command: received.append(command)
        or SimpleNamespace(run_id="run-1"),
    )

    exit_code = main_cli.main(
        [
            "predict",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "locomo",
            "--profile",
            "smoke",
            "--run-id",
            "run-1",
            "--confirm-api",
            "--disable-efficiency-observability",
        ]
    )

    assert exit_code == 0
    assert received == [
        PredictCommand(
            project_root=tmp_path,
            method="mem0",
            benchmark="locomo",
            profile="smoke",
            run_id="run-1",
            confirm_api=True,
            smoke_turn_limit=1,
            question_limit_per_conversation=1,
            enable_efficiency_observability=False,
            output_layout="hierarchical",
        )
    ]


def test_main_maps_answer_prompt_arguments_to_predict_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """predict 应把自定义 answer prompt 参数传入 command service。"""

    received: list[PredictCommand] = []
    monkeypatch.setattr(
        main_cli,
        "execute_predict",
        lambda command: received.append(command)
        or SimpleNamespace(run_id="run-1"),
    )

    exit_code = main_cli.main(
        [
            "predict",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "locomo",
            "--profile",
            "smoke",
            "--run-id",
            "run-1",
            "--confirm-api",
            "--answer-prompt-file",
            "prompts/locomo.txt",
            "--answer-prompt-profile",
            "locomo-custom",
        ]
    )

    assert exit_code == 0
    assert received == [
        PredictCommand(
            project_root=tmp_path,
            method="mem0",
            benchmark="locomo",
            profile="smoke",
            run_id="run-1",
            confirm_api=True,
            smoke_turn_limit=1,
            question_limit_per_conversation=1,
            answer_prompt_file=Path("prompts/locomo.txt"),
            answer_prompt_profile="locomo-custom",
            output_layout="hierarchical",
        )
    ]


def test_main_accepts_memoryos_as_registered_method_choice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """argparse 的 method choices 应通过 registry 暴露 memoryos。"""

    received: list[PredictCommand] = []
    monkeypatch.setattr(
        main_cli,
        "execute_predict",
        lambda command: received.append(command)
        or SimpleNamespace(run_id="memoryos-run"),
    )

    exit_code = main_cli.main(
        [
            "predict",
            "--root",
            str(tmp_path),
            "--method",
            "memoryos",
            "--benchmark",
            "locomo",
            "--profile",
            "smoke",
            "--run-id",
            "memoryos-run",
            "--confirm-api",
        ]
    )

    assert exit_code == 0
    assert received == [
        PredictCommand(
            project_root=tmp_path,
            method="memoryos",
            benchmark="locomo",
            profile="smoke",
            run_id="memoryos-run",
            confirm_api=True,
            smoke_turn_limit=1,
            question_limit_per_conversation=1,
            output_layout="hierarchical",
        )
    ]


def test_main_accepts_longmemeval_benchmark_and_free_string_variant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """argparse 不应拦截 LongMemEval 或未知 variant；具体校验交给 registry。"""

    received: list[PredictCommand] = []
    monkeypatch.setattr(
        main_cli,
        "execute_predict",
        lambda command: received.append(command)
        or PredictionBatchResult(
            benchmark="longmemeval",
            selector=command.variant or "s_cleaned",
            runs=(),
        ),
    )

    exit_code = main_cli.main(
        [
            "predict",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "longmemeval",
            "--variant",
            "unknown-yet-allowed-by-parser",
            "--profile",
            "smoke",
            "--confirm-api",
        ]
    )

    assert exit_code == 0
    assert received == [
        PredictCommand(
            project_root=tmp_path,
            method="mem0",
            benchmark="longmemeval",
            profile="smoke",
            variant="unknown-yet-allowed-by-parser",
            confirm_api=True,
            smoke_turn_limit=1,
            question_limit_per_conversation=1,
            output_layout="hierarchical",
        )
    ]


def test_main_accepts_membench_benchmark_choice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """argparse 的 benchmark choices 应通过 registry 暴露 membench。"""

    received: list[PredictCommand] = []
    monkeypatch.setattr(
        main_cli,
        "execute_predict",
        lambda command: received.append(command)
        or PredictionBatchResult(
            benchmark="membench",
            selector=command.variant or "0_10k",
            runs=(),
        ),
    )

    exit_code = main_cli.main(
        [
            "predict",
            "smoke",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "membench",
            "--variant",
            "100k",
            "--run-id",
            "mem0-membench-smoke",
            "--allow-api",
            "--conversations",
            "2",
        ]
    )

    assert exit_code == 0
    assert received == [
        PredictCommand(
            project_root=tmp_path,
            method="mem0",
            benchmark="membench",
            profile="smoke",
            variant="100k",
            run_id="mem0-membench-smoke",
            confirm_api=True,
            smoke_turn_limit=1,
            smoke_round_limit=1,
            smoke_conversation_limit=2,
            question_limit_per_conversation=1,
            output_layout="hierarchical",
            membench_sources=("first_high", "first_low", "third_high", "third_low"),
        )
    ]


def test_main_maps_repeated_metrics_for_evaluate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """evaluate 应保留 metric 输入顺序并支持重复参数。"""

    received: list[EvaluateCommand] = []
    monkeypatch.setattr(
        main_cli,
        "execute_evaluate",
        lambda command: received.append(command) or (),
    )

    exit_code = main_cli.main(
        [
            "evaluate",
            "--root",
            str(tmp_path),
            "--run-id",
            "run-1",
            "--metric",
            "locomo-f1",
            "--metric",
            "locomo-judge",
            "--judge-profile",
            "compact",
            "--confirm-api",
        ]
    )

    assert exit_code == 0
    assert received == [
        EvaluateCommand(
            project_root=tmp_path,
            run_id="run-1",
            metrics=("locomo-f1", "locomo-judge"),
            judge_profile="compact",
            confirm_api=True,
        )
    ]


def test_main_maps_run_arguments_to_run_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run 的 argv 应完整映射到 RunCommand，包含嵌套 prediction 参数。"""

    received: list[RunCommand] = []
    monkeypatch.setattr(
        main_cli,
        "execute_run",
        lambda command: received.append(command)
        or SimpleNamespace(run_id="run-1"),
    )

    exit_code = main_cli.main(
        [
            "run",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "locomo",
            "--profile",
            "official-full",
            "--variant",
            "all",
            "--run-id",
            "run-1",
            "--resume",
            "--confirm-api",
            "--confirm-full",
            "--rounds",
            "7",
            "--conversations",
            "5",
            "--workers",
            "10",
            "--conversation-budget",
            "3",
            "--questions-per-conversation",
            "2",
            "--metric",
            "locomo-f1",
            "--metric",
            "locomo-judge",
            "--judge-profile",
            "detailed",
        ]
    )

    assert exit_code == 0
    assert received == [
        RunCommand(
            prediction=PredictCommand(
                project_root=tmp_path,
                method="mem0",
                benchmark="locomo",
                profile="official-full",
                variant="all",
                run_id="run-1",
                resume=True,
                confirm_api=True,
                confirm_full=True,
                smoke_turn_limit=7,
                smoke_conversation_limit=5,
                smoke_max_workers=10,
                max_new_conversations=3,
                question_limit_per_conversation=2,
                output_layout="hierarchical",
            ),
            metrics=("locomo-f1", "locomo-judge"),
            judge_profile="detailed",
        )
    ]


def test_main_maps_calibration_smoke_arguments_to_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """calibrate-smoke 应解析 method/benchmark 矩阵和外层并发参数。"""

    received: list[CalibrationSmokeCommand] = []
    monkeypatch.setattr(
        main_cli,
        "execute_calibrate_smoke",
        lambda command: received.append(command)
        or SimpleNamespace(failed_count=0),
    )

    exit_code = main_cli.main(
        [
            "calibrate-smoke",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--method",
            "memoryos",
            "--benchmark",
            "locomo",
            "--benchmark",
            "longmemeval",
            "--run-prefix",
            "ohmygpt-calib",
            "--confirm-api",
            "--smoke-turn-limit",
            "7",
            "--max-new-conversations",
            "2",
            "--max-parallel-runs",
            "4",
        ]
    )

    assert exit_code == 0
    assert received == [
        CalibrationSmokeCommand(
            project_root=tmp_path,
            methods=("mem0", "memoryos"),
            benchmarks=("locomo", "longmemeval"),
            run_prefix="ohmygpt-calib",
            resume=False,
            confirm_api=True,
            smoke_turn_limit=7,
            max_new_conversations=2,
            max_parallel_runs=4,
        )
    ]


def test_main_maps_calibration_smoke_resume_flag_to_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """calibrate-smoke 只有显式传入 `--resume` 时才续跑 child run。"""

    received: list[CalibrationSmokeCommand] = []
    monkeypatch.setattr(
        main_cli,
        "execute_calibrate_smoke",
        lambda command: received.append(command)
        or SimpleNamespace(failed_count=0),
    )

    exit_code = main_cli.main(
        [
            "calibrate-smoke",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "locomo",
            "--run-prefix",
            "ohmygpt-calib",
            "--confirm-api",
            "--resume",
        ]
    )

    assert exit_code == 0
    assert received == [
        CalibrationSmokeCommand(
            project_root=tmp_path,
            methods=("mem0",),
            benchmarks=("locomo",),
            run_prefix="ohmygpt-calib",
            resume=True,
            confirm_api=True,
        )
    ]


def test_main_returns_nonzero_when_calibration_has_failed_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """校准矩阵若存在失败 child，CLI 应返回非零但仍打印 summary。"""

    monkeypatch.setattr(
        main_cli,
        "execute_calibrate_smoke",
        lambda command: SimpleNamespace(failed_count=1, run_prefix="calib"),
    )

    exit_code = main_cli.main(
        [
            "calibrate-smoke",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "locomo",
            "--run-prefix",
            "calib",
            "--confirm-api",
        ]
    )

    assert exit_code == 1


def test_main_returns_nonzero_for_domain_error_without_traceback(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认 CLI 应把领域异常转成非零退出码。"""

    monkeypatch.setattr(
        main_cli,
        "execute_evaluate",
        lambda command: (_ for _ in ()).throw(ConfigurationError("bad run")),
    )

    exit_code = main_cli.main(
        [
            "evaluate",
            "--run-id",
            "run-1",
            "--metric",
            "locomo-f1",
        ]
    )

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err
    assert "bad run" in captured.err


@pytest.mark.parametrize(
    "command",
    [
        [sys.executable, "-m", "memory_benchmark", "--help"],
        ["uv", "run", "memory-benchmark", "--help"],
    ],
)
def test_cli_help_subprocesses_are_stable(command: list[str]) -> None:
    """module 和 console script 的 help 应可稳定启动且不依赖网络。"""

    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "predict" in completed.stdout
    assert "evaluate" in completed.stdout
    assert "calibrate-smoke" in completed.stdout
    assert "run" in completed.stdout
    assert completed.stderr == ""


def test_main_debug_reraises_domain_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """debug 模式应保留 traceback 所需的原始异常。"""

    monkeypatch.setattr(
        main_cli,
        "execute_evaluate",
        lambda command: (_ for _ in ()).throw(ConfigurationError("bad run")),
    )

    with pytest.raises(ConfigurationError, match="bad run"):
        main_cli.main(
            [
                "--debug",
                "evaluate",
                "--run-id",
                "run-1",
                "--metric",
                "locomo-f1",
            ]
        )


# --- ws04 CLI dedup: legacy 别名已删 + smoke 默认问题帽=1 ---

@pytest.mark.parametrize(
    "legacy_flag",
    [
        "--smoke-turn-limit",
        "--smoke-conversation-limit",
        "--smoke-max-workers",
        "--max-new-conversations",
        "--question-limit-per-conversation",
    ],
)
def test_predict_rejects_removed_legacy_alias(legacy_flag: str, capsys) -> None:
    """删掉的旧 CLI 别名应被 argparse 报为 unrecognized argument。"""

    with pytest.raises(SystemExit) as raised:
        main_cli.main(
            [
                "predict",
                "smoke",
                "--root",
                ".",
                "--method",
                "mem0",
                "--benchmark",
                "locomo",
                "--allow-api",
                legacy_flag,
                "1",
            ]
        )

    assert raised.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err


def test_calibrate_smoke_still_keeps_max_new_conversations(capsys) -> None:
    """calibrate-smoke 不是去重对象，--max-new-conversations 在该子命令仍保留。"""

    with pytest.raises(SystemExit) as raised:
        main_cli.main(["calibrate-smoke", "--help"])

    assert raised.value.code == 0
    output = capsys.readouterr().out
    assert "--max-new-conversations" in output
    assert "--smoke-turn-limit" in output


def test_legacy_smoke_defaults_questions_to_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """legacy `predict --profile smoke` 未传问题时默认 question_limit_per_conversation=1。"""

    received: list[PredictCommand] = []
    monkeypatch.setattr(
        main_cli,
        "execute_predict",
        lambda command: received.append(command)
        or SimpleNamespace(run_id="run-1"),
    )

    exit_code = main_cli.main(
        [
            "predict",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "locomo",
            "--profile",
            "smoke",
            "--run-id",
            "run-1",
            "--confirm-api",
        ]
    )

    assert exit_code == 0
    assert received[0].question_limit_per_conversation == 1


def test_legacy_smoke_explicit_questions_overrides_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """显式 --questions-per-conversation 覆盖 smoke 默认帽 1。"""

    received: list[PredictCommand] = []
    monkeypatch.setattr(
        main_cli,
        "execute_predict",
        lambda command: received.append(command)
        or SimpleNamespace(run_id="run-1"),
    )

    exit_code = main_cli.main(
        [
            "predict",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "locomo",
            "--profile",
            "smoke",
            "--run-id",
            "run-1",
            "--confirm-api",
            "--questions-per-conversation",
            "7",
        ]
    )

    assert exit_code == 0
    assert received[0].question_limit_per_conversation == 7


def test_legacy_formal_questions_per_conversation_still_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """legacy `predict --profile official-full` 不设问题帽，默认仍为 None。"""

    received: list[PredictCommand] = []
    monkeypatch.setattr(
        main_cli,
        "execute_predict",
        lambda command: received.append(command)
        or SimpleNamespace(run_id="run-1"),
    )

    exit_code = main_cli.main(
        [
            "predict",
            "--root",
            str(tmp_path),
            "--method",
            "mem0",
            "--benchmark",
            "locomo",
            "--profile",
            "official-full",
            "--run-id",
            "run-1",
            "--confirm-api",
        ]
    )

    assert exit_code == 0
    assert received[0].question_limit_per_conversation is None
