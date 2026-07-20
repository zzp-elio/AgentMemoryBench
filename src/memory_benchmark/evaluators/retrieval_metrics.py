"""benchmark/method 无关的 Recall@k 纯结果内核。

四个 retrieval recall evaluator（LoCoMo/LongMemEval/MemBench/BEAM）此前各自
持有一份"从有序 retrieved_items 截取 top-k source id、按需投影到 session id、
再按 group any-of 计分"的重复逻辑。本模块把这段**真正公共**的部分收敛为单一
入口 `recall_at_k`：

- 只消费 always-on 条目和前 `top_k` 个 ranked 条目，`source_turn_ids` 按原序展开，稳定
  去重后再计分；重复 source id 不重复命中；
- gold group any-of 命中与 recall 比值仍复用 `gold_evidence_groups` 中已有的
  `group_is_hit` / `group_recall_score`，本模块不写第二份 recall 公式；
- 可选纯 `source_id_projector` 让调用方显式把公开 turn id 投影到公开 session
  id 空间（默认 identity）；projector 只变换公开 source-id 字符串，不读
  metadata、gold answer，也不按字符串猜 benchmark。

空 gold group 集合由各 benchmark 壳层自行按官方政策（LoCoMo 空 evidence=1、
MemBench/BEAM empty-gold N/A 等）处理，本内核对空 groups 一律 fail-fast，绝不
在此自行决定 0/1/N/A。本模块不 import 任何 benchmark adapter、method adapter，
也不读取 benchmark/method 名。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from memory_benchmark.core import GoldEvidenceGroup
from memory_benchmark.core.exceptions import ConfigurationError

from .gold_evidence_groups import group_is_hit, group_recall_score

# 默认 source-id 投影：Recall@k 在 turn 粒度上不做任何变换。
SourceIdProjector = Callable[[str], str]


def identity_source_id(source_id: str) -> str:
    """默认投影：原样返回公开 source id（turn 粒度不做聚合）。"""

    return source_id


@dataclass(frozen=True)
class RecallAtKResult:
    """Recall@k 纯结果内核的不可变返回。

    字段:
        score: group any-of recall（命中 group 数 / group 总数）。
        hit_count: 命中的 gold group 数（分子），与 `score` 同一 `group_is_hit`
            判定派生，二者恒一致。
        gold_unit_count: 官方 gold unit 数（分母），unmatched group 也保留在内。
        source_ids: 投影并稳定去重后的 top-k 公开 source id，保留首次出现顺序。
        requested_top_k: 调用方声明并实际截取的 top_k。
    """

    score: float
    hit_count: int
    gold_unit_count: int
    source_ids: tuple[str, ...]
    requested_top_k: int


def top_k_source_ids(
    retrieved_items: list[dict[str, Any]],
    top_k: int,
    *,
    source_id_projector: SourceIdProjector = identity_source_id,
) -> tuple[str, ...]:
    """从有序 retrieved_items 截取 top-k 并投影、稳定去重出公开 source id。

    输入:
        retrieved_items: 已通过 `validated_retrieval_fields()` 校验的有序检索项；
            只消费前 `top_k` 项，其 `source_turn_ids` 为非空字符串列表。
        top_k: 正整数；本函数只读取 `retrieved_items[:top_k]`。
        source_id_projector: 纯函数，把单个公开 source id 投影到目标 id 空间；
            默认 identity。

    输出:
        tuple[str, ...]: 投影后按首次出现顺序稳定去重的 source id 序列；同一
        投影结果只保留一次。
    """

    seen: dict[str, None] = {}
    for item in selected_retrieval_items(retrieved_items, top_k):
        for source_id in item["source_turn_ids"]:
            projected = source_id_projector(source_id)
            if projected not in seen:
                seen[projected] = None
    return tuple(seen)


def selected_retrieval_items(
    retrieved_items: list[dict[str, Any]], top_k: int
) -> list[dict[str, Any]]:
    """选择 Recall 输入：always-on 全取，ranked 才由 query k 限制。

    未声明 `selection_mode` 的历史 artifact 继续按 ranked 处理；`non_evidence`
    条目可进入产品 readout，却不应伪造可计分的 turn provenance。
    """

    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 0:
        raise ConfigurationError("top_k must be a non-negative integer")
    selected: list[dict[str, Any]] = []
    ranked_count = 0
    for item in retrieved_items:
        metadata = item.get("metadata")
        mode = metadata.get("selection_mode", "ranked") if isinstance(metadata, dict) else "ranked"
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


def recall_at_k(
    groups: tuple[GoldEvidenceGroup, ...],
    retrieved_items: list[dict[str, Any]],
    top_k: int,
    *,
    source_id_projector: SourceIdProjector = identity_source_id,
) -> RecallAtKResult:
    """计算一题的 group any-of Recall@k 纯结果。

    输入:
        groups: 非空 gold group 集合；空集合由 benchmark 壳层先按官方政策处理，
            传入空集合视为壳层未先执行政策，本内核 fail-fast。
        retrieved_items: 已 `validated_retrieval_fields()` 校验的有序检索项。
        top_k: 正整数，实际截取的 top-k。
        source_id_projector: 见 `top_k_source_ids`；默认 identity。

    输出:
        RecallAtKResult: 固定语义——只消费前 top_k 项、重复 source id 不重复
        命中、multi-child group 命中任一 child 只计一个 official unit、unmatched
        group 永远 miss 且保留在分母、空 `retrieved_items` 合法（非空 gold 时
        score=0）。recall 比值复用 `group_recall_score`，命中计数复用
        `group_is_hit`，不出现第二份公式。
    """

    if not groups:
        raise ConfigurationError(
            "recall_at_k requires non-empty gold groups; empty gold views must be "
            "handled by the benchmark-specific policy branch before scoring"
        )
    source_ids = top_k_source_ids(
        retrieved_items, top_k, source_id_projector=source_id_projector
    )
    source_id_set = set(source_ids)
    hit_count = sum(1 for group in groups if group_is_hit(group, source_id_set))
    score = group_recall_score(groups, source_id_set)
    return RecallAtKResult(
        score=score,
        hit_count=hit_count,
        gold_unit_count=len(groups),
        source_ids=source_ids,
        requested_top_k=top_k,
    )


__all__ = [
    "RecallAtKResult",
    "SourceIdProjector",
    "identity_source_id",
    "recall_at_k",
    "selected_retrieval_items",
    "top_k_source_ids",
]
