"""测试本地 OSS Mem0 在真实 LoCoMo 小样本上的付费 API 闭环。

本模块默认不会运行。只有显式选择 `api and mem0` marker 时，才会读取根目录
`.env`，调用 extraction、embedding 和 reader API，并把临时实验产物写入 pytest
提供的隔离目录。该 smoke 只验证回复生成链路，不计算或声明任何 benchmark metric。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_benchmark.benchmark_adapters import RunScope
from memory_benchmark.benchmark_adapters import get_adapter
from memory_benchmark.benchmark_adapters.locomo import (
    LOCOMO_SOURCE_PATH,
    build_locomo_smoke_dataset,
)
from memory_benchmark.config.settings import load_path_settings, load_settings
from memory_benchmark.methods.mem0_adapter import (
    Mem0,
    Mem0Config,
    build_mem0_source_identity,
)
from memory_benchmark.observability import RunContext
from memory_benchmark.runners.prediction import PredictionRunPolicy, run_predictions


pytestmark = [
    pytest.mark.api,
    pytest.mark.expensive,
    pytest.mark.integration,
    pytest.mark.mem0,
]


def test_mem0_locomo_single_question_real_api_smoke(tmp_path: Path) -> None:
    """用 3 个真实 turn 写入 Mem0，并为 evidence 已覆盖的问题生成非空回答。

    输入:
        根目录 `.env`、vendored Mem0 2.0.4 和 LoCoMo 首个 conversation。

    输出:
        一个 prediction artifact；gold/evidence 只存在于私有标签 artifact，
        且运行目录中不产生 metric 或 score 文件。
    """

    project_root = load_path_settings().project_root
    settings = load_settings(project_root=project_root)
    config = Mem0Config.smoke()
    dataset = build_locomo_smoke_dataset(
        get_adapter("locomo", project_root).load(limit=1),
        turn_limit=3,
    )
    run_context = RunContext.create(
        run_id="mem0-locomo-pytest-smoke",
        benchmark_name="locomo",
        method_name="Mem0",
        model_name=config.reader_model,
        output_root=tmp_path,
    )
    system = Mem0(
        config=config,
        openai_settings=settings.openai,
        storage_root=run_context.method_state_dir,
        path_settings=settings.paths,
    )

    summary = run_predictions(
        dataset=dataset,
        system=system,
        run_context=run_context,
        policy=PredictionRunPolicy(
            max_workers=1,
            question_limit_per_conversation=1,
        ),
        method_manifest={
            "config": config.to_manifest(),
            "source": build_mem0_source_identity(settings.paths),
        },
        benchmark_variant="locomo10",
        run_scope=RunScope.SMOKE,
        source_paths=(project_root / LOCOMO_SOURCE_PATH,),
    )

    prediction_text = summary.prediction_path.read_text(encoding="utf-8")
    assert summary.completed_conversations == 1
    assert summary.completed_questions == 1
    assert '"answer": "' in prediction_text
    assert "gold_answer" not in prediction_text
    assert not list(run_context.run_dir.rglob("*metric*"))
    assert not list(run_context.run_dir.rglob("*score*"))


def test_mem0_locomo_two_conversation_concurrent_api_smoke(
    tmp_path: Path,
) -> None:
    """用共享 OSS Mem0 实例并发处理两个 conversation，验证 namespace 隔离。

    输入:
        LoCoMo 前两个 conversation，各保留前三个 turn 和一道 evidence 已覆盖的问题。

    输出:
        两条 conversation_id 对齐的 prediction；运行仍不产生 metric 或 score。
    """

    project_root = load_path_settings().project_root
    settings = load_settings(project_root=project_root)
    config = Mem0Config.smoke()
    dataset = build_locomo_smoke_dataset(
        get_adapter("locomo", project_root).load(limit=2),
        turn_limit=3,
        conversation_limit=2,
    )
    run_context = RunContext.create(
        run_id="mem0-locomo-pytest-concurrent-smoke",
        benchmark_name="locomo",
        method_name="Mem0",
        model_name=config.reader_model,
        output_root=tmp_path,
    )
    system = Mem0(
        config=config,
        openai_settings=settings.openai,
        storage_root=run_context.method_state_dir,
        path_settings=settings.paths,
    )

    summary = run_predictions(
        dataset=dataset,
        system=system,
        run_context=run_context,
        policy=PredictionRunPolicy(
            max_workers=2,
            question_limit_per_conversation=1,
        ),
        method_manifest={
            "config": config.to_manifest(),
            "source": build_mem0_source_identity(settings.paths),
        },
        benchmark_variant="locomo10",
        run_scope=RunScope.SMOKE,
        source_paths=(project_root / LOCOMO_SOURCE_PATH,),
    )

    prediction_text = summary.prediction_path.read_text(encoding="utf-8")
    assert summary.completed_conversations == 2
    assert summary.completed_questions == 2
    assert '"conversation_id": "conv-26"' in prediction_text
    assert '"conversation_id": "conv-30"' in prediction_text
    assert "gold_answer" not in prediction_text
    assert not list(run_context.run_dir.rglob("*metric*"))
    assert not list(run_context.run_dir.rglob("*score*"))
