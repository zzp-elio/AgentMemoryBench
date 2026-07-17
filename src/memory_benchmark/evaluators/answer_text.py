"""answer 文本归一化的唯一版本化实现（answer-text-v1）。

通用 token-F1、normalized EM、directional substring EM 等 answer-level 补充
指标共用同一把归一化尺子：本模块是它的**唯一**实现，`f1.py::normalize_answer`
改为从这里 re-export（保留旧 import 兼容）。v1 语义逐字固定，不做 stemming、
Unicode normalization、中文分词、同义词或 category 特判——任何这类扩展都必须
是新版本，而不是原地改动 v1。
"""

from __future__ import annotations

import re
import string
from typing import Any

# 版本化身份：所有消费本归一化器的补充指标都在 score details 标注该值，供
# 报告层区分口径，永不与官方 parity 指标混层。
ANSWER_TEXT_PACK_VERSION = "answer-text-v1"

_ARTICLE_PATTERN = re.compile(r"\b(a|an|the|and)\b")
_PUNCTUATION_TRANSLATION = str.maketrans("", "", string.punctuation)


def normalize_answer(text: Any) -> str:
    """执行小写、去标点、去 a/an/the/and 和空白压缩（answer-text-v1）。

    输入:
        text: 任意值；`None` 归一化为 `""`，其它值先 `str()`。

    输出:
        str: 小写、仅按 Python `string.punctuation` 去 ASCII 标点、删除完整
        token `a/an/the/and`、再折叠空白后的字符串。
    """

    value = "" if text is None else str(text)
    without_punctuation = value.lower().translate(_PUNCTUATION_TRANSLATION)
    without_articles = _ARTICLE_PATTERN.sub(" ", without_punctuation)
    return " ".join(without_articles.split())


def normalized_tokens(text: Any) -> list[str]:
    """返回 answer-text-v1 归一化后按空白切分的 token 列表。

    输入:
        text: 任意值，先经 `normalize_answer` 归一化。

    输出:
        list[str]: 归一化字符串按空白切分的 token；空串返回空列表。
    """

    return normalize_answer(text).split()


__all__ = [
    "ANSWER_TEXT_PACK_VERSION",
    "normalize_answer",
    "normalized_tokens",
]
