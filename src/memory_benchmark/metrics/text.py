"""benchmark 无关的 answer 文本指标纯内核。

本模块只负责确定性文本变换与匹配，不读取 artifact、benchmark、method 或配置。
evaluator 负责决定某个 benchmark 是否有资格使用这些内核，并负责产出
`MetricResult`。`answer-text-v1` 语义不得原地漂移；需要 stemming、中文分词或
Unicode normalization 时应新增版本，而不是修改这里的既有行为。
"""

from __future__ import annotations

import re
import string
from typing import Any

ANSWER_TEXT_PACK_VERSION = "answer-text-v1"

_ARTICLE_PATTERN = re.compile(r"\b(a|an|the|and)\b")
_PUNCTUATION_TRANSLATION = str.maketrans("", "", string.punctuation)


def normalize_answer(text: Any) -> str:
    """执行 answer-text-v1 的小写、去标点、去冠词与空白压缩。"""

    value = "" if text is None else str(text)
    without_punctuation = value.lower().translate(_PUNCTUATION_TRANSLATION)
    without_articles = _ARTICLE_PATTERN.sub(" ", without_punctuation)
    return " ".join(without_articles.split())


def normalized_tokens(text: Any) -> list[str]:
    """返回 answer-text-v1 归一化后按空白切分的 token。"""

    return normalize_answer(text).split()


def is_contiguous_token_subsequence(
    needle: list[str], haystack: list[str]
) -> bool:
    """判断非空 `needle` 是否为 `haystack` 的连续 token 子序列。"""

    needle_length = len(needle)
    haystack_length = len(haystack)
    if needle_length == 0 or needle_length > haystack_length:
        return False
    return any(
        haystack[start : start + needle_length] == needle
        for start in range(haystack_length - needle_length + 1)
    )


__all__ = [
    "ANSWER_TEXT_PACK_VERSION",
    "is_contiguous_token_subsequence",
    "normalize_answer",
    "normalized_tokens",
]
