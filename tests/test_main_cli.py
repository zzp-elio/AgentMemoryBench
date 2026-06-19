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
        "enable_efficiency_observability": False,
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
            "benchmark_name": "locomo",
            "project_root": tmp_path,
            "profile_name": "smoke",
            "variant": None,
            "run_id": "run-1",
            "resume": False,
            "confirm_api": True,
            "confirm_full": False,
            "smoke_turn_limit": 3,
            "smoke_conversation_limit": 1,
            "smoke_max_workers": 1,
            "max_new_conversations": None,
            "enable_efficiency_observability": False,
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
        lambda path, selected, expected_benchmark: (
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


def test_prediction_help_describes_max_new_conversations(capsys) -> None:
    """predict 子命令 help 应说明预算只属于本次命令，不属于实验 identity。"""

    with pytest.raises(SystemExit) as raised:
        main_cli.main(["predict", "--help"])

    assert raised.value.code == 0
    output = capsys.readouterr().out
    assert "--max-new-conversations" in output
    assert "per-command" in output
    assert "identity" in output


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
            "--smoke-turn-limit",
            "3",
            "--max-new-conversations",
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
            variant="custom-selector",
            run_id="run-1",
            confirm_api=True,
            smoke_turn_limit=3,
            max_new_conversations=2,
        )
    ]


def test_main_maps_predict_efficiency_flag_to_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """argparse 应把单 run efficiency 开关传给 command service。"""

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
            "--enable-efficiency-observability",
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
            enable_efficiency_observability=True,
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
            "--smoke-turn-limit",
            "7",
            "--smoke-conversation-limit",
            "2",
            "--smoke-max-workers",
            "2",
            "--max-new-conversations",
            "3",
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
                smoke_conversation_limit=2,
                smoke_max_workers=2,
                max_new_conversations=3,
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
