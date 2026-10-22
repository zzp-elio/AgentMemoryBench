"""6 类统一记忆评测类型与基准映射 (`UnifiedCapability`).

五个基准的原题按「做对时该回答什么」收成 6 类。做对的话不同、或只有一家基准
且题量不足以单独成榜的原生题型返回 `None`，不塞进这 6 类。
"""

from __future__ import annotations

from enum import Enum


class UnifiedCapability(str, Enum):
    """6 类统一记忆评测类型。"""

    FACT_RECALL = "fact_recall"
    """事实回忆：把已经说过的内容说出来。"""

    MULTI_HOP = "multi_hop"
    """多证据综合：把好几处说过的内容拼成一个答案。"""

    TEMPORAL = "temporal"
    """时间与顺序：用日期或先后作答。事件排序也算在这一类。"""

    MEMORY_UPDATE = "memory_update"
    """记忆更新：只答更新后的当前值。"""

    ABSTENTION = "abstention"
    """拒答：明确说没说过。"""

    PREFERENCE = "preference"
    """个性化：偏好已经说过，回答要照着做。"""

    @property
    def label_zh(self) -> str:
        """返回评测类型的中文名称。"""
        return _CAPABILITY_LABELS[self]

    @property
    def layer(self) -> str:
        """返回类型所属的分组，供汇总报告使用。"""
        return _CAPABILITY_LAYERS[self]


_CAPABILITY_LABELS: dict[UnifiedCapability, str] = {
    UnifiedCapability.FACT_RECALL: "事实回忆",
    UnifiedCapability.MULTI_HOP: "多证据综合",
    UnifiedCapability.TEMPORAL: "时间与顺序",
    UnifiedCapability.MEMORY_UPDATE: "记忆更新",
    UnifiedCapability.ABSTENTION: "拒答",
    UnifiedCapability.PREFERENCE: "个性化",
}

_CAPABILITY_LAYERS: dict[UnifiedCapability, str] = {
    UnifiedCapability.FACT_RECALL: "事实",
    UnifiedCapability.MULTI_HOP: "事实",
    UnifiedCapability.TEMPORAL: "变化",
    UnifiedCapability.MEMORY_UPDATE: "变化",
    UnifiedCapability.ABSTENTION: "拒答",
    UnifiedCapability.PREFERENCE: "个性化",
}


def map_native_task_to_capability(
    benchmark: str,
    native_task: str | None,
) -> UnifiedCapability | None:
    """将基准原生题型映射为 6 类之一。

    返回 `None` 的题不进入这 6 类，包括：
    LoCoMo 对抗题与开放域常识题；LongMemEval 以外没有对应物的题；
    BEAM 的内部矛盾、指令遵循、长期总结；
    MemBench 的再加工、带噪问题、没说破的偏好和情绪；
    HaluMem 的错误前提纠正与新情境应用。
    """
    if not native_task:
        return None

    bench = benchmark.strip().lower()
    raw = native_task.strip()
    key = raw.lower().replace(" ", "_").replace("-", "_")

    if bench == "locomo":
        if key in {"4", "category_4", "cat_4", "single_hop"}:
            return UnifiedCapability.FACT_RECALL
        if key in {"1", "category_1", "cat_1", "multi_hop"}:
            return UnifiedCapability.MULTI_HOP
        if key in {"2", "category_2", "cat_2", "temporal"}:
            return UnifiedCapability.TEMPORAL
        return None

    if bench == "longmemeval":
        if key.endswith("_abs") or key in {"abstention", "abs"}:
            return UnifiedCapability.ABSTENTION
        if "preference" in key:
            return UnifiedCapability.PREFERENCE
        if "update" in key:
            return UnifiedCapability.MEMORY_UPDATE
        if "temporal" in key:
            return UnifiedCapability.TEMPORAL
        if "multi" in key:
            return UnifiedCapability.MULTI_HOP
        if "single_session" in key or key in {"user", "assistant"}:
            return UnifiedCapability.FACT_RECALL

    if bench == "beam":
        if key == "information_extraction":
            return UnifiedCapability.FACT_RECALL
        if key in {"multi_session_reasoning", "multi_hop_reasoning"}:
            return UnifiedCapability.MULTI_HOP
        if key in {"temporal_reasoning", "event_ordering"}:
            return UnifiedCapability.TEMPORAL
        if key == "knowledge_update":
            return UnifiedCapability.MEMORY_UPDATE
        if key == "preference_following":
            return UnifiedCapability.PREFERENCE
        if key == "abstention":
            return UnifiedCapability.ABSTENTION
        return None

    if bench == "membench":
        if key in {"simple", "lowlevel_rec"}:
            return UnifiedCapability.FACT_RECALL
        if key in {
            "conditional",
            "comparative",
            "aggregative",
            "recmultisession",
        }:
            return UnifiedCapability.MULTI_HOP
        if key == "knowledge_update":
            return UnifiedCapability.MEMORY_UPDATE
        return None

    if bench == "halumem":
        if "basic_fact" in key or key == "fact_recall":
            return UnifiedCapability.FACT_RECALL
        if "multi_hop" in key:
            return UnifiedCapability.MULTI_HOP
        if "dynamic_update" in key or key == "update":
            return UnifiedCapability.MEMORY_UPDATE
        if "memory_boundary" in key or key == "boundary":
            return UnifiedCapability.ABSTENTION
        return None

    for cap in UnifiedCapability:
        if cap.value == key:
            return cap

    return None


__all__ = [
    "UnifiedCapability",
    "map_native_task_to_capability",
]
