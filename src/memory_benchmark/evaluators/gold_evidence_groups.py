"""gold evidence contract v1 的共享私有 qrel parser 与 group 计分工具。

五个 retrieval evaluator 统一从本模块解析 evaluator-private label 中的
`evidence_group_sets` 并按 group 语义计分，不得各自复制宽松解析：

- recall：每个 mapped group 只要任一 child 出现在 top-k source ids 就命中一次；
  unmatched group 永远 miss；分母是 group 数，不是 child 数。
- rank/NDCG：一个 group 的 rank 是其任一 child 首次出现的最小 rank；同 group
  多 child 与同 child 重复命中都只计一次；unmatched 留在 ideal gold 数中但
  永远不命中。

本模块只读 evaluator 私有通道（run manifest 与 evaluator_private_labels），
不接触任何 method 可见 payload。
"""

from __future__ import annotations

from typing import Any

from memory_benchmark.core import (
    GOLD_EVIDENCE_CONTRACT_V1,
    GoldEvidenceGroup,
    GoldEvidenceGroupSet,
)
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.metrics.ranking import group_first_hit_rank
from memory_benchmark.metrics.retrieval import group_is_hit, group_recall_score


def require_manifest_gold_evidence_contract_v1(manifest: dict[str, Any]) -> None:
    """校验 run manifest 的 benchmark policy 声明 gold evidence contract v1。

    输入:
        manifest: 已加载的 run manifest。

    输出:
        None。旧无版本 manifest（缺 benchmark_policy 或缺版本）与未知版本一律
        fail-fast，不做静默兼容。
    """

    benchmark_policy = manifest.get("benchmark_policy")
    if not isinstance(benchmark_policy, dict):
        raise ConfigurationError(
            "run manifest is missing benchmark_policy; this run predates gold "
            "evidence contract v1 and cannot be scored by group-based retrieval "
            "evaluators — re-run prediction with a v1 benchmark registration"
        )
    version = benchmark_policy.get("gold_evidence_contract_version")
    if version != GOLD_EVIDENCE_CONTRACT_V1:
        raise ConfigurationError(
            "run manifest benchmark_policy declares gold_evidence_contract_version="
            f"{version!r}; expected {GOLD_EVIDENCE_CONTRACT_V1!r} — old or mixed "
            "version artifacts must not be silently scored"
        )


def parse_evidence_group_sets(
    private_record: dict[str, Any],
    question_id: str,
) -> tuple[GoldEvidenceGroupSet, ...]:
    """把 evaluator-private label 记录解析回强类型 group sets。

    输入:
        private_record: `evaluator_private_labels.jsonl` 中的一条记录。
        question_id: 当前题目 id，用于错误定位。

    输出:
        tuple[GoldEvidenceGroupSet, ...]: 强类型 view 集合；label 缺版本、版本
        非 v1 或结构非法时 fail-fast（实体构造器负责逐字段强校验）。
    """

    version = private_record.get("gold_evidence_contract_version")
    if version != GOLD_EVIDENCE_CONTRACT_V1:
        raise ConfigurationError(
            f"question {question_id}: private label declares "
            f"gold_evidence_contract_version={version!r}; expected "
            f"{GOLD_EVIDENCE_CONTRACT_V1!r} — old or mixed version labels must "
            "not be silently scored"
        )
    raw_sets = private_record.get("evidence_group_sets")
    if not isinstance(raw_sets, list):
        raise ConfigurationError(
            f"question {question_id}: v1 private label requires an "
            "evidence_group_sets list"
        )
    parsed_sets: list[GoldEvidenceGroupSet] = []
    seen_views: set[tuple[str, str]] = set()
    for set_index, raw_set in enumerate(raw_sets):
        if not isinstance(raw_set, dict):
            raise ConfigurationError(
                f"question {question_id}: evidence_group_sets[{set_index}] must "
                "be an object"
            )
        raw_groups = raw_set.get("groups")
        if not isinstance(raw_groups, list):
            raise ConfigurationError(
                f"question {question_id}: evidence_group_sets[{set_index}].groups "
                "must be a list"
            )
        groups: list[GoldEvidenceGroup] = []
        for group_index, raw_group in enumerate(raw_groups):
            if not isinstance(raw_group, dict):
                raise ConfigurationError(
                    f"question {question_id}: evidence_group_sets[{set_index}]"
                    f".groups[{group_index}] must be an object"
                )
            raw_child_ids = raw_group.get("child_ids")
            if not isinstance(raw_child_ids, list):
                raise ConfigurationError(
                    f"question {question_id}: evidence_group_sets[{set_index}]"
                    f".groups[{group_index}].child_ids must be a list"
                )
            try:
                groups.append(
                    GoldEvidenceGroup(
                        unit_id=raw_group.get("unit_id"),
                        child_ids=tuple(raw_child_ids),
                        mapping_status=raw_group.get("mapping_status"),
                    )
                )
            except ValueError as exc:
                raise ConfigurationError(
                    f"question {question_id}: invalid gold evidence group in "
                    f"evidence_group_sets[{set_index}].groups[{group_index}]: {exc}"
                ) from exc
        try:
            group_set = GoldEvidenceGroupSet(
                provenance_granularity=raw_set.get("provenance_granularity"),
                unit_kind=raw_set.get("unit_kind"),
                groups=tuple(groups),
            )
        except ValueError as exc:
            raise ConfigurationError(
                f"question {question_id}: invalid gold evidence group set at "
                f"evidence_group_sets[{set_index}]: {exc}"
            ) from exc
        view = (group_set.provenance_granularity, group_set.unit_kind)
        if view in seen_views:
            raise ConfigurationError(
                f"question {question_id}: duplicate gold evidence view {view!r}"
            )
        seen_views.add(view)
        parsed_sets.append(group_set)
    return tuple(parsed_sets)


def select_group_set(
    group_sets: tuple[GoldEvidenceGroupSet, ...],
    *,
    provenance_granularity: str,
    unit_kind: str,
    question_id: str,
) -> GoldEvidenceGroupSet:
    """严格选择当前指标所需的 (granularity, unit_kind) view。

    输入:
        group_sets: 已解析的强类型 view 集合。
        provenance_granularity: 指标所需 provenance 粒度。
        unit_kind: 指标所需 benchmark unit kind。
        question_id: 当前题目 id，用于错误定位。

    输出:
        GoldEvidenceGroupSet: 匹配的 view；缺失时 fail-fast，不做近似回退。
    """

    for group_set in group_sets:
        if (
            group_set.provenance_granularity == provenance_granularity
            and group_set.unit_kind == unit_kind
        ):
            return group_set
    raise ConfigurationError(
        f"question {question_id}: private label is missing required gold "
        f"evidence view ({provenance_granularity!r}, {unit_kind!r})"
    )


__all__ = [
    "group_first_hit_rank",
    "group_is_hit",
    "group_recall_score",
    "parse_evidence_group_sets",
    "require_manifest_gold_evidence_contract_v1",
    "select_group_set",
]
