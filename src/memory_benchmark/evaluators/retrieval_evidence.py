"""retrieval evidence contract v1 的共享私有资格判定工具。

五个 retrieval evaluator 统一从本模块获取"provider 能否被这个 metric 评分"的
逐题裁决，不得各自复制一份宽松 parser 或资格规则：

- 先过两道版本门（gold evidence contract v1 由
  `gold_evidence_groups.require_manifest_gold_evidence_contract_v1` 负责，
  retrieval evidence contract v1 由本模块的
  `require_manifest_retrieval_evidence_contract_v1` 负责），旧/未声明
  manifest 一律 fail-fast，不允许因为"反正要评 N/A"而绕过身份门；
- 对每条 answer prompt 记录的 `retrieval_evidence` 做严格 preflight：缺失、
  null、非 object、缺字段、多余字段、非法 status/granularity/reason 组合，
  统一转成带 question id 的 `ConfigurationError`；preflight 复用
  `EvidenceAssertion`/`RetrievalEvidence` 协议构造器的运行期校验，不另写
  一套可能漂移的规则；
- 再按 metric 的静态需求（允许比较的 gold granularity 集合、是否要求
  stable ranking）从合法 `RetrievalEvidence` 派生 valid/n_a/pending 资格
  裁决，不建 method×benchmark×metric 白名单。

本模块只读 provider 公开返回值（经 runner 落盘的 answer prompt artifact），
不接触任何 gold/私有标签内容。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.provider_protocol import (
    EvidenceAssertion,
    ProvenanceGranularity,
    RetrievalEvidence,
    RetrievalEvidenceStatus,
)

RETRIEVAL_EVIDENCE_CONTRACT_V1 = "v1"
GOLD_GRANULARITY_MISMATCH_REASON_CODE = "gold_granularity_mismatch"

_ASSERTION_KEYS = frozenset({"status", "reason_code", "reason"})
_EVIDENCE_KEYS = frozenset(
    {"semantic_provenance", "provenance_granularity", "stable_ranking"}
)


def require_manifest_retrieval_evidence_contract_v1(manifest: dict[str, Any]) -> None:
    """校验 run manifest 的 method 声明 retrieval evidence contract v1。

    输入:
        manifest: 已加载的 run manifest。

    输出:
        None。缺 `method`、缺 version 或版本非 v1 一律 `ConfigurationError`；
        旧/未声明契约的 artifact 不得因为"反正要评 N/A"而绕过本门——该门必须
        在旧 `provenance_granularity=none/undeclared`、benchmark
        `_abs`/no-target/empty-gold 与逐题 N/A 之前发生。
    """

    method_manifest = manifest.get("method")
    if not isinstance(method_manifest, dict):
        raise ConfigurationError(
            "run manifest is missing method; this run predates retrieval "
            "evidence contract v1 and cannot be scored by per-question "
            "retrieval evaluators — re-run prediction with a v1 registered method"
        )
    version = method_manifest.get("retrieval_evidence_contract_version")
    if version != RETRIEVAL_EVIDENCE_CONTRACT_V1:
        raise ConfigurationError(
            "run manifest method declares retrieval_evidence_contract_version="
            f"{version!r}; expected {RETRIEVAL_EVIDENCE_CONTRACT_V1!r} — old or "
            "unknown version artifacts must not be silently scored"
        )


def _require_object(value: Any, question_id: str, field_path: str) -> dict[str, Any]:
    """校验字段是 object，否则 fail-fast。"""

    if not isinstance(value, dict):
        raise ConfigurationError(
            f"question {question_id}: {field_path} must be an object, got "
            f"{type(value).__name__}"
        )
    return value


def _require_exact_keys(
    raw: dict[str, Any],
    allowed: frozenset[str],
    question_id: str,
    field_path: str,
) -> None:
    """校验 object 的 key 集合与允许集合完全一致，不容忍缺失或多余 key。"""

    non_string_keys = [key for key in raw if not isinstance(key, str)]
    if non_string_keys:
        raise ConfigurationError(
            f"question {question_id}: {field_path} has non-string object keys; "
            "all keys must be strings"
        )
    actual = set(raw)
    if actual != allowed:
        missing = sorted(allowed - actual)
        extra = sorted(actual - allowed)
        raise ConfigurationError(
            f"question {question_id}: {field_path} has missing keys {missing} "
            f"or unexpected keys {extra}; expected exactly {sorted(allowed)}"
        )


def _parse_evidence_assertion(
    raw: Any, question_id: str, field_path: str
) -> EvidenceAssertion:
    """严格解析单个 assertion object（`semantic_provenance`/`stable_ranking` 共用）。"""

    raw_object = _require_object(raw, question_id, field_path)
    _require_exact_keys(raw_object, _ASSERTION_KEYS, question_id, field_path)
    try:
        return EvidenceAssertion(
            status=raw_object["status"],
            reason_code=raw_object["reason_code"],
            reason=raw_object["reason"],
        )
    except ValueError as exc:
        raise ConfigurationError(
            f"question {question_id}: invalid {field_path}: {exc}"
        ) from exc


def parse_retrieval_evidence(raw: Any, question_id: str) -> RetrievalEvidence:
    """把一条 answer prompt artifact 的 `retrieval_evidence` 严格解析回协议实体。

    输入:
        raw: `answer_prompt_record.get("retrieval_evidence")` 的原始值；key
            缺失或值为 null 都会传入 None。非 object、缺字段、多余字段、字段
            内非法值都必须 fail-fast，不能静默当作某种默认资格——preflight
            必须在任何 benchmark-specific 排除或计分循环之前对**全部**
            answer records 执行，不计分题（如即将被 `_abs`/no-target/
            empty-gold 剔除的题）也不得携带非法 evidence。
        question_id: 当前题目 id，用于错误定位。

    输出:
        RetrievalEvidence: 严格校验后的强类型逐题证据；一律通过
        `EvidenceAssertion`/`RetrievalEvidence` 的协议构造器复用运行期校验，
        不另写一套可能与协议漂移的规则。
    """

    if raw is None:
        raise ConfigurationError(
            f"question {question_id}: retrieval_evidence is missing or null; "
            "a run declaring retrieval evidence contract v1 must carry "
            "per-question evidence for every answer prompt record"
        )
    raw_object = _require_object(raw, question_id, "retrieval_evidence")
    _require_exact_keys(raw_object, _EVIDENCE_KEYS, question_id, "retrieval_evidence")

    semantic_provenance = _parse_evidence_assertion(
        raw_object["semantic_provenance"],
        question_id,
        "retrieval_evidence.semantic_provenance",
    )
    stable_ranking = _parse_evidence_assertion(
        raw_object["stable_ranking"],
        question_id,
        "retrieval_evidence.stable_ranking",
    )
    try:
        return RetrievalEvidence(
            semantic_provenance=semantic_provenance,
            provenance_granularity=raw_object["provenance_granularity"],
            stable_ranking=stable_ranking,
        )
    except ValueError as exc:
        raise ConfigurationError(
            f"question {question_id}: invalid retrieval_evidence: {exc}"
        ) from exc


@dataclass(frozen=True)
class RetrievalEligibilityDecision:
    """evaluator 从逐题 `RetrievalEvidence` 派生的资格裁决。

    字段:
        status: 该题对当前 metric 是否可评分：`valid` 可评分，`n_a`/
            `pending` 不可评分且不进分母。
        reason_code: `status` 非 valid 时的稳定原因码；valid 时为 None。
        reason: `status` 非 valid 时的可读原因；valid 时为 None。
        provenance_granularity: `status=valid` 时用于挑选 Gold Evidence
            Group view 的粒度；非 valid 时保留当前裁决对应的逐题粒度。
            semantic provenance 非 valid 时协议保证为 `none`，但 granularity
            mismatch 或 stable-ranking 非 valid 时仍可保留原始 turn/session。
    """

    status: RetrievalEvidenceStatus
    reason_code: str | None
    reason: str | None
    provenance_granularity: ProvenanceGranularity


def decide_retrieval_eligibility(
    evidence: RetrievalEvidence,
    *,
    allowed_granularities: frozenset[str],
    requires_stable_ranking: bool,
) -> RetrievalEligibilityDecision:
    """按 metric 的静态需求从逐题 `RetrievalEvidence` 派生资格裁决。

    输入:
        evidence: 已通过 `parse_retrieval_evidence` 校验的逐题证据。
        allowed_granularities: 该 metric 能够比较的 gold view 粒度集合（如
            LoCoMo/LongMemEval recall 允许 `{"turn","session"}`，
            MemBench/BEAM recall 只允许 `{"turn"}`）。
        requires_stable_ranking: rank/NDCG 类 metric 在 semantic provenance
            通过后还需要 `stable_ranking=valid`；recall 类恒为 False。

    输出:
        RetrievalEligibilityDecision: 固定优先级 —— semantic provenance 非
        valid 直接原样传播其 status/reason；valid 但 granularity 不在允许
        集合记 `n_a`/`gold_granularity_mismatch`；不要求 stable ranking 时到
        此即 valid（Recall 不看 stable_ranking）；要求时再检查
        stable_ranking，非 valid 同样原样传播；全部满足才是 valid。
    """

    semantic = evidence.semantic_provenance
    if semantic.status != "valid":
        return RetrievalEligibilityDecision(
            status=semantic.status,
            reason_code=semantic.reason_code,
            reason=semantic.reason,
            provenance_granularity=evidence.provenance_granularity,
        )
    if evidence.provenance_granularity not in allowed_granularities:
        allowed = ", ".join(sorted(allowed_granularities))
        return RetrievalEligibilityDecision(
            status="n_a",
            reason_code=GOLD_GRANULARITY_MISMATCH_REASON_CODE,
            reason=(
                "semantic provenance is valid at granularity "
                f"{evidence.provenance_granularity!r}, but this metric only "
                f"has gold evidence at granularity in {{{allowed}}}"
            ),
            provenance_granularity=evidence.provenance_granularity,
        )
    if not requires_stable_ranking:
        return RetrievalEligibilityDecision(
            status="valid",
            reason_code=None,
            reason=None,
            provenance_granularity=evidence.provenance_granularity,
        )
    ranking = evidence.stable_ranking
    if ranking.status != "valid":
        return RetrievalEligibilityDecision(
            status=ranking.status,
            reason_code=ranking.reason_code,
            reason=ranking.reason,
            provenance_granularity=evidence.provenance_granularity,
        )
    return RetrievalEligibilityDecision(
        status="valid",
        reason_code=None,
        reason=None,
        provenance_granularity=evidence.provenance_granularity,
    )


def display_status(status: RetrievalEvidenceStatus) -> str:
    """把非 valid 的内部 status 映射为 artifact record 惯用的展示态字符串。

    输入:
        status: 逐题裁决的 `n_a`/`pending`（不接受 `valid`——记分行的
            `"status": "ok"` 由各 evaluator 自行书写，避免误用本函数覆盖
            真正已评分的分支）。

    输出:
        str: `n_a` 展示为 `"n/a"`（与既有 abstention/no-target 记录的
        `status` 字段拼写一致），`pending` 原样展示。
    """

    if status == "n_a":
        return "n/a"
    if status == "pending":
        return "pending"
    raise ConfigurationError(
        f"display_status does not accept status={status!r}; valid decisions "
        "should not be displayed via this helper"
    )


def summary_status(*, scored_count: int, pending_count: int) -> str:
    """按已评分/pending 数量计算 summary 三态状态。

    输入:
        scored_count: 真实计分（`retrieval_evidence_status=valid` 且未被
            benchmark policy 剔除）的题数。
        pending_count: 有可评分 gold、且
            `retrieval_evidence_status=pending` 的题数；benchmark-policy
            排除题不进入 evidence status 统计。

    输出:
        str: 至少一题 scored 为 `"ok"`；零 scored 且至少一题 pending 为
        `"pending"`；否则为 `"n/a"`。
    """

    if scored_count > 0:
        return "ok"
    if pending_count > 0:
        return "pending"
    return "n/a"


def summary_provenance_granularity(
    scored_decisions: Sequence[RetrievalEligibilityDecision],
) -> str | None:
    """从实际评分裁决聚合 summary 级 `provenance_granularity`。

    历史 summary 曾把 `provenance_granularity` 当作整个 run 唯一值直接使用；
    v1 逐题裁决后该字段已不再是资格判据（真正的资格判定见
    `decide_retrieval_eligibility`，逐题真实粒度见每条 score record 自身的
    `provenance_granularity`），本函数只为仍在读取 summary 顶层该字段的存量
    消费者保留审计辅助值，但只允许实际进入 metric 分母的裁决参与：没有
    scored question 返回 None；只有一种粒度返回该粒度；同时出现多种粒度
    返回稳定值 `"mixed"`。benchmark-policy 排除题与 valid 但未评分题均不能
    污染该值；本字段仍不驱动资格、gold view 选择或计分。

    输入:
        scored_decisions: 本 run 实际进入分母的 valid 裁决。

    输出:
        str | None: 唯一粒度、`"mixed"`，或 None（无 scored question）。
    """

    granularities = {
        decision.provenance_granularity for decision in scored_decisions
    }
    if not granularities:
        return None
    if len(granularities) == 1:
        return next(iter(granularities))
    return "mixed"


def validated_retrieval_fields(
    record: dict[str, Any], question_id: str
) -> tuple[int, list[dict[str, Any]]]:
    """严格校验 decision valid 且非 benchmark 排除题的 retrieval artifact。

    `retrieval_query_top_k` 必须是非 bool 的正整数；`retrieved_items` 必须是
    list 且每项都是 object。只对实际进入 top-k 的 item 要求非空
    `source_turn_ids`，其中每个 id 必须是无首尾空白的非空字符串。真实
    `retrieved_items=[]` 合法，表示 0 hit。
    """

    top_k = record.get("retrieval_query_top_k")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
        raise ConfigurationError(
            f"question {question_id}: retrieval_query_top_k must be a positive int"
        )
    items = record.get("retrieved_items")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ConfigurationError(
            f"question {question_id}: retrieved_items must be a list of objects"
        )
    for item in items[:top_k]:
        source_ids = item.get("source_turn_ids")
        if not isinstance(source_ids, list) or not source_ids:
            raise ConfigurationError(
                f"question {question_id}: top-k retrieved item source_turn_ids "
                "must be a non-empty list"
            )
        if any(
            not isinstance(source_id, str)
            or not source_id.strip()
            or source_id != source_id.strip()
            for source_id in source_ids
        ):
            raise ConfigurationError(
                f"question {question_id}: top-k retrieved item source_turn_ids "
                "must contain non-empty strings without surrounding whitespace"
            )
    return top_k, items


__all__ = [
    "GOLD_GRANULARITY_MISMATCH_REASON_CODE",
    "RETRIEVAL_EVIDENCE_CONTRACT_V1",
    "RetrievalEligibilityDecision",
    "decide_retrieval_eligibility",
    "display_status",
    "parse_retrieval_evidence",
    "require_manifest_retrieval_evidence_contract_v1",
    "summary_provenance_granularity",
    "summary_status",
    "validated_retrieval_fields",
]
