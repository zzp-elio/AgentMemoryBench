"""旧 evaluator import 路径的兼容转发层。

Recall 纯内核已归入 `memory_benchmark.metrics.retrieval`；本模块只保留历史
import 兼容，避免一次目录整理迫使下游同步迁移。
"""

from memory_benchmark.metrics.retrieval import (
    RecallAtKResult,
    SourceIdProjector,
    identity_source_id,
    recall_at_k,
    selected_retrieval_items,
    top_k_source_ids,
)


__all__ = [
    "RecallAtKResult",
    "SourceIdProjector",
    "identity_source_id",
    "recall_at_k",
    "selected_retrieval_items",
    "top_k_source_ids",
]
