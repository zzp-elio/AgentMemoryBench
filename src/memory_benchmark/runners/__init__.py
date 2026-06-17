"""运行层。

后续放 evaluation runner、dry-run runner 和小样本调试 runner。
runner 负责串联 adapter、method、metric 和 result writer。
"""

from memory_benchmark.runners.evaluation import (
    EvaluationRunSummary,
    run_artifact_evaluation,
)

__all__ = [
    "EvaluationRunSummary",
    "run_artifact_evaluation",
]
