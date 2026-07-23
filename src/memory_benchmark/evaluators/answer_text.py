"""旧 answer-text evaluator import 路径的兼容转发层。

纯文本指标内核已归入高内聚的 `memory_benchmark.metrics.text`；本模块只保留
历史 import 兼容，不再持有第二份实现。
"""

from memory_benchmark.metrics.text import (
    ANSWER_TEXT_PACK_VERSION,
    normalize_answer,
    normalized_tokens,
)


__all__ = [
    "ANSWER_TEXT_PACK_VERSION",
    "normalize_answer",
    "normalized_tokens",
]
