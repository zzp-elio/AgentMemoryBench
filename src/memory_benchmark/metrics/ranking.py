"""benchmark 无关的 retrieval ranking 纯内核。"""

from __future__ import annotations

from collections.abc import Callable
from math import log2
from typing import Any

from memory_benchmark.core import GoldEvidenceGroup

from .retrieval import identity_source_id


def discounted_cumulative_gain(relevances: list[float]) -> float:
    """按首位不折损、后续 `log2(rank)` 折损计算 DCG。"""

    if not relevances:
        return 0.0
    return relevances[0] + sum(
        relevance / log2(index)
        for index, relevance in enumerate(relevances[1:], start=2)
    )


def group_first_hit_rank(
    group: GoldEvidenceGroup,
    ranked_ids: list[str],
) -> int | None:
    """返回 mapped group 任一 child 的最早 0 基名次，否则返回 None。"""

    if group.mapping_status != "mapped":
        return None
    return next(
        (
            rank
            for rank, source_id in enumerate(ranked_ids)
            if source_id in group.child_ids
        ),
        None,
    )


def ranked_source_ids(
    items: list[dict[str, Any]],
    *,
    source_id_projector: Callable[[str], str] = identity_source_id,
) -> list[str]:
    """按调用方已选择的检索项/source 顺序投影并保留 id 首次出现位置。"""

    ranked: list[str] = []
    seen: set[str] = set()
    for item in items:
        for raw_id in item["source_turn_ids"]:
            source_id = source_id_projector(str(raw_id))
            if source_id not in seen:
                seen.add(source_id)
                ranked.append(source_id)
    return ranked


def group_rank_metrics_at_k(
    ranked_ids: list[str],
    groups: tuple[GoldEvidenceGroup, ...],
    k: int,
) -> dict[str, float]:
    """计算 group any/all recall 与二值 NDCG@k。"""

    window_ids = set(ranked_ids[:k])
    any_hit = any(
        group.mapping_status == "mapped"
        and any(child_id in window_ids for child_id in group.child_ids)
        for group in groups
    )
    all_hit = all(
        group.mapping_status == "mapped"
        and any(child_id in window_ids for child_id in group.child_ids)
        for group in groups
    )

    actual_hits: list[float] = [0.0] * k
    for group in groups:
        rank = group_first_hit_rank(group, ranked_ids[:k])
        if rank is not None:
            actual_hits[rank] = 1.0
    actual_dcg = discounted_cumulative_gain(actual_hits)
    ideal_dcg = discounted_cumulative_gain([1.0] * min(len(groups), k))
    ndcg = actual_dcg / ideal_dcg if ideal_dcg else 0.0
    return {
        f"recall_any@{k}": float(any_hit),
        f"recall_all@{k}": float(all_hit),
        f"ndcg_any@{k}": ndcg,
    }


__all__ = [
    "discounted_cumulative_gain",
    "group_first_hit_rank",
    "group_rank_metrics_at_k",
    "ranked_source_ids",
]
