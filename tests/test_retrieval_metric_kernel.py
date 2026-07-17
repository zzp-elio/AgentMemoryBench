"""通用 Recall@k 纯结果内核测试。

锁死 `retrieval_metrics.recall_at_k` 的固定语义：top-k 截断、重复 source id
去重、multi-child any-of、unmatched 分母、0 hit、session projector 与空 groups
拒绝；同时断言公共入口不携带任何 benchmark/method 身份参数。
"""

from __future__ import annotations

import inspect

import pytest

from memory_benchmark.core import GoldEvidenceGroup
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.evaluators import retrieval_metrics
from memory_benchmark.evaluators.retrieval_metrics import (
    RecallAtKResult,
    recall_at_k,
    top_k_source_ids,
)


pytestmark = pytest.mark.unit


def _mapped(unit_id: str, *child_ids: str) -> GoldEvidenceGroup:
    """构造一个 mapped gold group（命中任一 child 即命中一次）。"""

    return GoldEvidenceGroup(
        unit_id=unit_id,
        child_ids=tuple(child_ids),
        mapping_status="mapped",
    )


def _unmatched(unit_id: str) -> GoldEvidenceGroup:
    """构造一个 unmatched gold group（永远 miss，但保留在分母中）。"""

    return GoldEvidenceGroup(unit_id=unit_id, child_ids=(), mapping_status="unmatched")


def _item(*source_turn_ids: str) -> dict[str, list[str]]:
    """构造单个已校验形态的 retrieved item。"""

    return {"source_turn_ids": list(source_turn_ids)}


def _session_prefix(dia_id: str) -> str:
    """把 `D<n>:<turn>` 形式的公开 id 聚合到 `D<n>` session 前缀。"""

    prefix, _, rest = dia_id.partition(":")
    return prefix if rest else dia_id


def test_recall_only_consumes_top_k_items() -> None:
    """只消费 retrieved_items[:top_k]，越界项的 source id 不参与命中。"""

    groups = (_mapped("g1", "t9"),)
    items = [_item("t1"), _item("t9")]

    truncated = recall_at_k(groups, items, top_k=1)
    assert isinstance(truncated, RecallAtKResult)
    assert truncated.score == 0.0
    assert truncated.hit_count == 0
    assert truncated.source_ids == ("t1",)
    assert truncated.requested_top_k == 1

    reachable = recall_at_k(groups, items, top_k=2)
    assert reachable.score == 1.0
    assert reachable.hit_count == 1
    assert reachable.source_ids == ("t1", "t9")


def test_duplicate_source_ids_are_deduped_and_counted_once() -> None:
    """跨项与项内重复的 source id 稳定去重，一个 group 只计一次命中。"""

    groups = (_mapped("g1", "t1"), _mapped("g2", "t2"))
    items = [_item("t1", "t1"), _item("t1")]

    result = recall_at_k(groups, items, top_k=5)

    assert result.source_ids == ("t1",)
    assert result.hit_count == 1
    assert result.gold_unit_count == 2
    assert result.score == 0.5


def test_multi_child_group_any_of_hit_counts_once() -> None:
    """一个 group 含多个 child：命中任一或全部都只算一个 official unit。"""

    group = (_mapped("g1", "a", "b"),)

    both = recall_at_k(group, [_item("a", "b")], top_k=5)
    assert both.hit_count == 1
    assert both.gold_unit_count == 1
    assert both.score == 1.0

    single = recall_at_k(group, [_item("b")], top_k=5)
    assert single.hit_count == 1
    assert single.score == 1.0


def test_unmatched_group_always_misses_but_stays_in_denominator() -> None:
    """unmatched group 永远 miss，但仍保留在分母中。"""

    groups = (_mapped("g1", "t1"), _unmatched("g2"))

    result = recall_at_k(groups, [_item("t1")], top_k=5)

    assert result.hit_count == 1
    assert result.gold_unit_count == 2
    assert result.score == 0.5


def test_empty_retrieved_items_is_zero_hit_not_error() -> None:
    """空 retrieved_items 合法：非空 gold 时 score=0，不 fail-fast。"""

    groups = (_mapped("g1", "t1"),)

    result = recall_at_k(groups, [], top_k=5)

    assert result.score == 0.0
    assert result.hit_count == 0
    assert result.source_ids == ()
    assert result.gold_unit_count == 1
    assert result.requested_top_k == 5


def test_session_projector_maps_turn_ids_to_session_space() -> None:
    """调用方传入 session projector 时，turn id 被投影并去重到 session 空间。"""

    groups = (_mapped("D1", "D1"),)
    items = [_item("D1:5", "D1:6")]

    projected = recall_at_k(
        groups, items, top_k=5, source_id_projector=_session_prefix
    )
    assert projected.source_ids == ("D1",)
    assert projected.hit_count == 1
    assert projected.score == 1.0

    # 默认 identity 投影不聚合 → 同一 gold 无法命中。
    identity = recall_at_k(groups, items, top_k=5)
    assert identity.score == 0.0
    assert identity.source_ids == ("D1:5", "D1:6")


def test_top_k_source_ids_projects_and_stable_dedups() -> None:
    """`top_k_source_ids` 按首次出现顺序稳定去重，并应用投影。"""

    items = [_item("D1:5", "D1:6"), _item("D2:1"), _item("D1:5")]

    assert top_k_source_ids(items, top_k=3, source_id_projector=_session_prefix) == (
        "D1",
        "D2",
    )
    assert top_k_source_ids(items, top_k=1) == ("D1:5", "D1:6")


def test_recall_at_k_rejects_empty_gold_groups() -> None:
    """空 gold groups 由 benchmark 壳层先处理，内核一律 fail-fast。"""

    with pytest.raises(ConfigurationError, match="non-empty gold groups"):
        recall_at_k((), [_item("t1")], top_k=5)


def test_kernel_public_api_has_no_benchmark_or_method_identity() -> None:
    """公共入口的签名与 import 都不得携带 benchmark/method 身份。"""

    for func in (recall_at_k, top_k_source_ids):
        parameter_names = set(inspect.signature(func).parameters)
        assert not any(
            "benchmark" in name or "method" in name for name in parameter_names
        )

    source = inspect.getsource(retrieval_metrics)
    assert "from memory_benchmark.benchmark_adapters" not in source
    assert "import memory_benchmark.benchmark_adapters" not in source
    assert "from memory_benchmark.methods" not in source
    assert "import memory_benchmark.methods" not in source
