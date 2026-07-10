"""MemBench 条件式 retrieval recall（artifact-only，离线）。

匹配键统一在公开 turn-id 空间（1 基），官方 0 基 `target_step_id` 仅作
metadata 留档。MemBench 单 session，session 粒度声明视同 conversation 级
记 N/A（数据无 session 结构可召回）。
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from memory_benchmark.core import ConfigurationError
from memory_benchmark.storage import ExperimentPaths, read_jsonl


class MemBenchRetrievalRecallEvaluator:
    """按 provider 声明的 provenance 粒度计算 MemBench 条件式 recall。"""

    metric_name = "membench_recall"
    official_source = (
        "third_party/benchmarks/Membench-main/benchmark/load_test_data.py:57,"
        "MembenchAgent.py:46-92"
    )

    def evaluate_run_artifacts(
        self,
        *,
        paths: ExperimentPaths,
        manifest: dict[str, Any],
        max_workers: int = 1,
    ) -> dict[str, Any]:
        """从 manifest、answer prompt 与 evaluator-private labels 计算 recall。"""

        del max_workers
        provenance_granularity = _method_provenance_granularity(manifest)
        if provenance_granularity in {"none", "undeclared"}:
            return _na_payload(
                metric_name=self.metric_name,
                reason="provider provenance is unavailable; retrieval recall is not evaluable for this run",
                provenance_granularity=provenance_granularity,
                official_source=self.official_source,
            )
        if provenance_granularity == "session":
            # MemBench 单 session（每个 conversation 一个 s1 session），
            # 公开 dataset 层级没有 session 结构可召回；视为 conversation 级 N/A。
            return _na_payload(
                metric_name=self.metric_name,
                reason=(
                    "MemBench has no session structure to recall; each conversation "
                    "is a single session and per-step gold is the only available "
                    "evidence. Treat session provenance as conversation-level N/A."
                ),
                provenance_granularity=provenance_granularity,
                official_source=self.official_source,
            )
        if provenance_granularity != "turn":
            raise ConfigurationError(
                f"Unknown provenance_granularity {provenance_granularity!r} in "
                "manifest['method']; expected 'none', 'session' or 'turn'"
            )

        answer_records = read_jsonl(paths.answer_prompts_path)
        private_records = read_jsonl(paths.evaluator_private_labels_path)
        public_records = read_jsonl(paths.public_questions_path)
        _validate_matching_question_ids(answer_records, private_records, public_records)
        private_by_id = {record["question_id"]: record for record in private_records}
        category_by_id = {
            record["question_id"]: record.get("category") for record in public_records
        }

        score_records: list[dict[str, Any]] = []
        scored_records: list[dict[str, Any]] = []
        top_k_values: list[int] = []
        empty_evidence_count = 0
        unmatched_gold_total = 0
        out_of_bounds_gold_total = 0

        for answer_record in answer_records:
            question_id = str(answer_record["question_id"])
            category = category_by_id.get(question_id)
            top_k, retrieved_items = _validated_retrieval_fields(
                answer_record,
                provenance_granularity,
            )
            source_ids = _source_turn_ids(retrieved_items, top_k)
            private_record = private_by_id[question_id]
            private_metadata = private_record.get("metadata")
            if not isinstance(private_metadata, dict):
                raise ConfigurationError(
                    f"question {question_id}: private label metadata must be an object"
                )
            # evidence（公开 turn-id 空间的 gold）在 private label 的**顶层**——
            # `storage/artifacts.py:evaluator_private_label_record` 把
            # `GoldAnswerInfo.evidence` 序列化为顶层键；metadata 只存官方
            # 0 基原值 target_step_id 等对照记录（D5 停工裁决，勿读 metadata）。
            evidence = _required_string_list(
                private_record,
                "evidence",
                question_id,
            )
            target_step_ids = _required_int_list(
                private_metadata,
                "target_step_id",
                question_id,
            )
            oob_ids = _out_of_bounds_target_step_ids(
                target_step_ids,
                answer_record,
                question_id,
            )
            out_of_bounds_gold_total += len(oob_ids)

            if not evidence:
                empty_evidence_count += 1
                score = 1.0
            else:
                hits = sum(evidence_id in source_ids for evidence_id in evidence)
                unmatched = [eid for eid in evidence if eid not in source_ids]
                unmatched_gold_total += len(unmatched)
                score = hits / len(evidence)

            top_k_values.append(top_k)
            record = {
                "question_id": question_id,
                "conversation_id": answer_record.get("conversation_id"),
                "metric_name": self.metric_name,
                "score": score,
                "status": "ok",
                "category": category,
                "requested_top_k": top_k,
                "provenance_granularity": provenance_granularity,
                "details": {
                    "gold_evidence_turn_ids": evidence,
                    "target_step_id_original": target_step_ids,
                    "out_of_bounds_target_step_ids": oob_ids,
                    "retrieved_source_turn_ids": sorted(source_ids),
                    "official_source": self.official_source,
                },
            }
            score_records.append(record)
            scored_records.append(record)

        return _scored_payload(
            metric_name=self.metric_name,
            score_records=score_records,
            scored_records=scored_records,
            top_k_values=top_k_values,
            empty_evidence_count=empty_evidence_count,
            unmatched_gold_total=unmatched_gold_total,
            out_of_bounds_gold_total=out_of_bounds_gold_total,
            provenance_granularity=provenance_granularity,
            official_source=self.official_source,
        )


def _method_provenance_granularity(manifest: dict[str, Any]) -> str:
    """读取 method manifest 的 provenance_granularity 声明。"""

    method = manifest.get("method")
    if not isinstance(method, dict) or method.get("provenance_granularity") is None:
        return "undeclared"
    return str(method["provenance_granularity"])


def _validate_matching_question_ids(
    answer_records: list[dict[str, Any]],
    private_records: list[dict[str, Any]],
    public_records: list[dict[str, Any]],
) -> None:
    """校验三类 artifact 的 question id 必须唯一且集合完全一致。"""

    id_lists = [
        [record.get("question_id") for record in records]
        for records in (answer_records, private_records, public_records)
    ]
    if any(len(ids) != len(set(ids)) for ids in id_lists) or not (
        set(id_lists[0]) == set(id_lists[1]) == set(id_lists[2])
    ):
        raise ConfigurationError(
            "MemBench recall artifact question IDs must match exactly across "
            "answer prompts, private labels and public questions"
        )


def _validated_retrieval_fields(
    record: dict[str, Any],
    provenance_granularity: str,
) -> tuple[int, list[dict[str, Any]]]:
    """校验声明 provenance 后必需的 top_k、retrieved_items 与 source ids。"""

    question_id = record.get("question_id")
    top_k = record.get("retrieval_query_top_k")
    retrieved_items = record.get("retrieved_items")
    if not isinstance(top_k, int) or top_k < 1:
        raise ConfigurationError(
            f"question {question_id}: provider declares provenance_granularity="
            f"{provenance_granularity!r} but retrieval_query_top_k is missing or invalid"
        )
    if not isinstance(retrieved_items, list) or any(
        not isinstance(item, dict) for item in retrieved_items
    ):
        raise ConfigurationError(
            f"question {question_id}: provider declares provenance_granularity="
            f"{provenance_granularity!r} but retrieved_items is missing or invalid"
        )
    for item in retrieved_items[:top_k]:
        source_ids = item.get("source_turn_ids")
        if not isinstance(source_ids, list) or not source_ids:
            raise ConfigurationError(
                f"question {question_id}: provider declares provenance_granularity="
                f"{provenance_granularity!r} but a retrieved item has missing or empty "
                "source_turn_ids"
            )
    return top_k, retrieved_items


def _required_string_list(
    metadata: dict[str, Any],
    key: str,
    question_id: str,
) -> list[str]:
    """读取 evaluator-private metadata 中必需的字符串列表。"""

    value = metadata.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ConfigurationError(
            f"question {question_id}: private label metadata requires {key} list"
        )
    return value


def _required_int_list(
    metadata: dict[str, Any],
    key: str,
    question_id: str,
) -> list[int]:
    """读取 evaluator-private metadata 中必需的整数列表。"""

    value = metadata.get(key)
    if not isinstance(value, list):
        raise ConfigurationError(
            f"question {question_id}: private label metadata requires {key} list"
        )
    parsed: list[int] = []
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, int):
            raise ConfigurationError(
                f"question {question_id}: private label metadata {key}[{index}] "
                "must be an integer"
            )
        parsed.append(item)
    return parsed


def _source_turn_ids(
    retrieved_items: list[dict[str, Any]],
    top_k: int,
) -> set[str]:
    """合并有序 top-k retrieved items 的公开 source turn ids。"""

    return {
        str(source_id)
        for item in retrieved_items[:top_k]
        for source_id in item["source_turn_ids"]
    }


def _out_of_bounds_target_step_ids(
    target_step_ids: list[int],
    answer_record: dict[str, Any],
    question_id: str,
) -> list[int]:
    """识别 0 基 target_step_id 中越界（>= 公开 turn 总数）的官方 id。

    公开 turn 数通过 answer record 的 `public_turn_count` metadata 暴露（由
    框架 reader 在生成 answer prompt 时写入；缺则视为不可判定，记 N/A 但
    不阻断）。0 基下 == len(message_list) 越界映射后无对应公开 turn，recall
    侧记 unmatched-gold + 单独计数，不崩。
    """

    if not target_step_ids:
        return []
    metadata = answer_record.get("metadata")
    if not isinstance(metadata, dict):
        return []
    public_turn_count = metadata.get("public_turn_count")
    if not isinstance(public_turn_count, int) or public_turn_count < 0:
        return []
    return [sid for sid in target_step_ids if sid >= public_turn_count]


def _na_payload(
    *,
    metric_name: str,
    reason: str,
    provenance_granularity: str,
    official_source: str,
) -> dict[str, Any]:
    """构造 provenance 不可用或不支持时的结构化 N/A payload。"""

    return {
        "metric_name": metric_name,
        "score_records": [],
        "total_questions": 0,
        "mean_score": 0.0,
        "correct_count": None,
        "summary": {
            "status": "n/a",
            "reason": reason,
            "provenance_granularity": provenance_granularity,
            "official_source": official_source,
        },
    }


def _scored_payload(
    *,
    metric_name: str,
    score_records: list[dict[str, Any]],
    scored_records: list[dict[str, Any]],
    top_k_values: list[int],
    empty_evidence_count: int,
    unmatched_gold_total: int,
    out_of_bounds_gold_total: int,
    provenance_granularity: str,
    official_source: str,
) -> dict[str, Any]:
    """聚合已评分问题，按 question_type 输出分类聚合。"""

    scores = [float(record["score"]) for record in scored_records]
    mean_score = sum(scores) / len(scores) if scores else 0.0
    by_category: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[float]] = {}
    for record in scored_records:
        category = record.get("category")
        key = "unknown" if category is None else str(category)
        grouped.setdefault(key, []).append(float(record["score"]))
    for category, category_scores in sorted(grouped.items()):
        by_category[category] = {
            "scored_count": len(category_scores),
            "mean_score": sum(category_scores) / len(category_scores),
        }
    return {
        "metric_name": metric_name,
        "score_records": score_records,
        "total_questions": len(scored_records),
        "mean_score": mean_score,
        "correct_count": None,
        "summary": {
            "status": "ok" if scored_records else "n/a",
            "provenance_granularity": provenance_granularity,
            "scored_question_count": len(scored_records),
            "empty_evidence_question_count": empty_evidence_count,
            "unmatched_gold_total": unmatched_gold_total,
            "out_of_bounds_gold_total": out_of_bounds_gold_total,
            "overall_mean_recall_at_requested_k": mean_score,
            "by_category": by_category,
            "requested_top_k_distribution": dict(Counter(top_k_values)),
            "official_source": official_source,
        },
    }


__all__ = ["MemBenchRetrievalRecallEvaluator"]
