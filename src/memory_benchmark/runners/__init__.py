"""运行编排层 (Runners)。

包含两大核心运行器：
1. `prediction`：串联 `Ingest(Session) -> Retrieve -> Answer` 并采集三大黑盒效率指标（`ingest_latency_ms`、`retrieve_latency_ms`、`retrieved_context_tokens`）；
2. `evaluation`：基于落盘 Artifacts 执行离线 Answer-Level 评测的统一评估运行器。
"""

from memory_benchmark.runners.evaluation import (
    EvaluationRunSummary,
    run_artifact_evaluation,
)
from memory_benchmark.runners.prediction import (
    PredictionRunPolicy,
    PredictionRunSummary,
    count_context_tokens,
    default_isolation_key,
    run_predictions,
)

__all__ = [
    "EvaluationRunSummary",
    "PredictionRunPolicy",
    "PredictionRunSummary",
    "count_context_tokens",
    "default_isolation_key",
    "run_artifact_evaluation",
    "run_predictions",
]
