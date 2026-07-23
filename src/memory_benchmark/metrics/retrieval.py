"""benchmark/method 无关的 retrieval recall 纯内核。

本模块只接收强类型 gold group、公开 source id 与有序检索项；不读取 artifact、
manifest、benchmark 名或 method 配置。空 gold 的 0/1/N/A 语义属于 benchmark
政策，必须由 evaluator 壳层先处理。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from memory_benchmark.core import GoldEvidenceGroup
from memory_benchmark.core.exceptions import ConfigurationError

SourceIdProjector = Callable[[str], str]


def identity_source_id(source_id: str) -> str:
    """原样返回公开 source id。"""

    return source_id


def group_is_hit(group: GoldEvidenceGroup, source_ids: set[str]) -> bool:
    """判断 group 是否命中：mapped 且任一 child 出现在 source ids 中。"""

    return group.mapping_status == "mapped" and any(
        child_id in source_ids for child_id in group.child_ids
    )


def group_recall_score(
    groups: tuple[GoldEvidenceGroup, ...],
    source_ids: set[str],
) -> float:
    """计算 group any-of recall；unmatched group 保留在分母且永远 miss。"""

    if not groups:
        raise ConfigurationError(
            "group_recall_score requires non-empty groups; empty views must be "
            "handled by the benchmark-specific policy branch"
        )
    return sum(1 for group in groups if group_is_hit(group, source_ids)) / len(groups)


@dataclass(frozen=True)
class RecallAtKResult:
    """Recall@k 纯内核的不可变返回。"""

    score: float
    hit_count: int
    gold_unit_count: int
    source_ids: tuple[str, ...]
    requested_top_k: int


def selected_retrieval_items(
    retrieved_items: list[dict[str, Any]], top_k: int
) -> list[dict[str, Any]]:
    """选择计分检索项：always-on 全取，ranked 受 top-k 限制。"""

    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 0:
        raise ConfigurationError("top_k must be a non-negative integer")
    selected: list[dict[str, Any]] = []
    ranked_count = 0
    for item in retrieved_items:
        metadata = item.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise ConfigurationError("retrieved item metadata must be an object")
        mode = metadata.get("selection_mode", "ranked") if metadata is not None else "ranked"
        if mode not in {"always_on", "ranked", "non_evidence"}:
            raise ConfigurationError(
                "retrieved item selection_mode must be always_on, ranked, or non_evidence"
            )
        if mode == "always_on":
            selected.append(item)
        elif mode == "ranked":
            if ranked_count < top_k:
                selected.append(item)
            ranked_count += 1
    return selected


def top_k_source_ids(
    retrieved_items: list[dict[str, Any]],
    top_k: int,
    *,
    source_id_projector: SourceIdProjector = identity_source_id,
) -> tuple[str, ...]:
    """截取计分检索项并投影、稳定去重公开 source id。"""

    seen: dict[str, None] = {}
    for item in selected_retrieval_items(retrieved_items, top_k):
        for source_id in item["source_turn_ids"]:
            projected = source_id_projector(source_id)
            if projected not in seen:
                seen[projected] = None
    return tuple(seen)


def recall_at_k(
    groups: tuple[GoldEvidenceGroup, ...],
    retrieved_items: list[dict[str, Any]],
    top_k: int,
    *,
    source_id_projector: SourceIdProjector = identity_source_id,
) -> RecallAtKResult:
    """按 group any-of 语义计算单题 Recall@k。"""

    if not groups:
        raise ConfigurationError(
            "recall_at_k requires non-empty gold groups; empty gold views must be "
            "handled by the benchmark-specific policy branch before scoring"
        )
    source_ids = top_k_source_ids(
        retrieved_items, top_k, source_id_projector=source_id_projector
    )
    source_id_set = set(source_ids)
    return RecallAtKResult(
        score=group_recall_score(groups, source_id_set),
        hit_count=sum(
            1 for group in groups if group_is_hit(group, source_id_set)
        ),
        gold_unit_count=len(groups),
        source_ids=source_ids,
        requested_top_k=top_k,
    )


__all__ = [
    "RecallAtKResult",
    "SourceIdProjector",
    "group_is_hit",
    "group_recall_score",
    "identity_source_id",
    "recall_at_k",
    "selected_retrieval_items",
    "top_k_source_ids",
]
