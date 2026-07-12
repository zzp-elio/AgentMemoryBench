"""LongMemEval 官方检索排名指标的 artifact-only 实现。"""

from __future__ import annotations

from collections import defaultdict
from math import log2
from typing import Any

from memory_benchmark.core import ConfigurationError
from memory_benchmark.storage import ExperimentPaths, read_jsonl


OFFICIAL_K = (1, 3, 5, 10, 30, 50)


class LongMemEvalRetrievalRankEvaluator:
    """按公开 provenance id 计算官方 recall_any/all 与 NDCG。"""

    metric_name = "longmemeval_retrieval_rank"

    def evaluate_run_artifacts(
        self,
        *,
        paths: ExperimentPaths,
        manifest: dict[str, Any],
        max_workers: int = 1,
    ) -> dict[str, Any]:
        """读取 answer prompt 与 evaluator-private gold 并聚合排名指标。"""

        del max_workers
        granularity = _provenance_granularity(manifest)
        if granularity in {"none", "undeclared"}:
            return _na_payload(granularity)
        if granularity not in {"turn", "session"}:
            raise ConfigurationError(
                f"Unknown provenance_granularity {granularity!r} in manifest['method']; "
                "expected 'none', 'session' or 'turn'"
            )

        answers = read_jsonl(paths.answer_prompts_path)
        private = read_jsonl(paths.evaluator_private_labels_path)
        public = read_jsonl(paths.public_questions_path)
        _validate_question_ids(answers, private, public)
        private_by_id = {record["question_id"]: record for record in private}
        category_by_id = {
            record["question_id"]: record.get("category") for record in public
        }

        records: list[dict[str, Any]] = []
        participating: dict[int, list[dict[str, float]]] = defaultdict(list)
        skipped_k: set[int] = set()
        skipped_k_count = 0
        abstention_count = 0
        empty_gold_count = 0
        for answer in answers:
            question_id = str(answer["question_id"])
            if "_abs" in question_id:
                abstention_count += 1
                records.append(
                    {
                        "question_id": question_id,
                        "conversation_id": answer.get("conversation_id"),
                        "metric_name": self.metric_name,
                        "score": None,
                        "status": "n/a",
                        "abstention": True,
                        "category": category_by_id.get(question_id),
                    }
                )
                continue

            top_k, items = _retrieval_fields(answer, granularity)
            ranked_ids = _ranked_source_ids(items, top_k, granularity)
            metadata = private_by_id[question_id].get("metadata")
            if not isinstance(metadata, dict):
                raise ConfigurationError(
                    f"question {question_id}: private label metadata must be an object"
                )
            evidence_key = (
                "evidence_turn_ids"
                if granularity == "turn"
                else "evidence_session_public_ids"
            )
            gold = _required_string_list(metadata, evidence_key, question_id)
            if not gold:
                empty_gold_count += 1

            metrics: dict[str, float] = {}
            available_k = [k for k in OFFICIAL_K if k <= top_k]
            unavailable_k = [k for k in OFFICIAL_K if k > top_k]
            skipped_k.update(unavailable_k)
            skipped_k_count += len(unavailable_k)
            for k in available_k:
                values = _evaluate_at_k(ranked_ids, gold, k)
                metrics.update(values)
                participating[k].append(values)
            records.append(
                {
                    "question_id": question_id,
                    "conversation_id": answer.get("conversation_id"),
                    "metric_name": self.metric_name,
                    "score": metrics.get(f"ndcg_any@{max(available_k)}") if available_k else None,
                    "status": "ok",
                    "abstention": False,
                    "category": category_by_id.get(question_id),
                    "retrieval_query_top_k": top_k,
                    "provenance_granularity": granularity,
                    "metrics": metrics,
                }
            )

        means = {
            metric: sum(row[metric] for row in rows) / len(rows)
            for k, rows in sorted(participating.items())
            for metric in (f"recall_any@{k}", f"recall_all@{k}", f"ndcg_any@{k}")
        }
        scored = [record for record in records if record["score"] is not None]
        return {
            "metric_name": self.metric_name,
            "score_records": records,
            "total_questions": len(scored),
            "mean_score": (
                sum(float(record["score"]) for record in scored) / len(scored)
                if scored
                else 0.0
            ),
            "correct_count": None,
            "summary": {
                "status": "ok" if scored else "n/a",
                "provenance_granularity": granularity,
                "overall_metrics": means,
                "participating_question_count_by_k": {
                    str(k): len(rows) for k, rows in sorted(participating.items())
                },
                "abstention_excluded_count": abstention_count,
                "empty_gold_question_count": empty_gold_count,
                "skipped_k_above_top_k": sorted(skipped_k),
                "skipped_k_above_top_k_count": skipped_k_count,
                "turn2session_view": "not_artifact_computable",
                "official_empty_gold_note": (
                    "Framework follows longmemeval-recall empty-gold score=1.0; "
                    "official eval_utils.py:19-20 returns ndcg=0.0 when ideal_dcg is zero."
                ),
                "official_sources": {
                    "formula": "src/retrieval/eval_utils.py:4-29",
                    "k_and_names": "src/retrieval/run_retrieval.py:316-321",
                    "abstention": "src/retrieval/run_retrieval.py:389-408",
                },
            },
        }


def _evaluate_at_k(ranked_ids: list[str], gold: list[str], k: int) -> dict[str, float]:
    """按官方二值相关性公式计算一个 k；空 gold 延续既有 recall 满分边界。"""

    if not gold:
        return {
            f"recall_any@{k}": 1.0,
            f"recall_all@{k}": 1.0,
            f"ndcg_any@{k}": 1.0,
        }
    recalled = set(ranked_ids[:k])
    relevances = [1.0 if item in gold else 0.0 for item in ranked_ids[:k]]
    actual_dcg = _dcg(relevances)
    # 官方 eval_utils.py:14-18 对全 corpus 二值相关性降序。无需 corpus 的等价式：
    # ideal relevance 即 [1] * min(n_gold, k)，其余零不贡献 DCG。
    ideal_dcg = _dcg([1.0] * min(len(set(gold)), k))
    return {
        f"recall_any@{k}": float(any(item in recalled for item in gold)),
        f"recall_all@{k}": float(all(item in recalled for item in gold)),
        f"ndcg_any@{k}": actual_dcg / ideal_dcg if ideal_dcg else 0.0,
    }


def _dcg(relevances: list[float]) -> float:
    """复刻官方 eval_utils.py:4-9 的 DCG 折损。"""

    if not relevances:
        return 0.0
    return relevances[0] + sum(
        relevance / log2(index)
        for index, relevance in enumerate(relevances[1:], start=2)
    )


def _ranked_source_ids(
    items: list[dict[str, Any]], top_k: int, granularity: str
) -> list[str]:
    """按 retrieved item/source 顺序展开公开 id，并保留首次出现位置。"""

    ranked: list[str] = []
    seen: set[str] = set()
    for item in items[:top_k]:
        for raw_id in item["source_turn_ids"]:
            source_id = str(raw_id)
            if granularity == "session":
                source_id = _public_session_id(source_id)
            if source_id not in seen:
                seen.add(source_id)
                ranked.append(source_id)
    return ranked


def _retrieval_fields(
    record: dict[str, Any], granularity: str
) -> tuple[int, list[dict[str, Any]]]:
    """校验声明 provenance 后所需的 top_k/items/source ids。"""

    question_id = record.get("question_id")
    top_k = record.get("retrieval_query_top_k")
    items = record.get("retrieved_items")
    if not isinstance(top_k, int) or top_k < 1:
        raise ConfigurationError(
            f"question {question_id}: provider declares provenance_granularity="
            f"{granularity!r} but retrieval_query_top_k is missing or invalid"
        )
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ConfigurationError(
            f"question {question_id}: provider declares provenance_granularity="
            f"{granularity!r} but retrieved_items is missing or invalid"
        )
    for item in items[:top_k]:
        source_ids = item.get("source_turn_ids")
        if not isinstance(source_ids, list) or not source_ids:
            raise ConfigurationError(
                f"question {question_id}: provider declares provenance_granularity="
                f"{granularity!r} but a retrieved item has missing or empty source_turn_ids"
            )
    return top_k, items


def _provenance_granularity(manifest: dict[str, Any]) -> str:
    """读取 method manifest 的 provenance 声明。"""

    method = manifest.get("method")
    if not isinstance(method, dict) or method.get("provenance_granularity") is None:
        return "undeclared"
    return str(method["provenance_granularity"])


def _required_string_list(
    metadata: dict[str, Any], key: str, question_id: str
) -> list[str]:
    """读取 evaluator-private metadata 中必需的公开匹配键列表。"""

    value = metadata.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ConfigurationError(
            f"question {question_id}: private label metadata requires {key} list"
        )
    return value


def _validate_question_ids(
    answers: list[dict[str, Any]],
    private: list[dict[str, Any]],
    public: list[dict[str, Any]],
) -> None:
    """校验三类 artifact question id 唯一且集合完全一致。"""

    id_lists = [
        [record.get("question_id") for record in records]
        for records in (answers, private, public)
    ]
    if any(len(ids) != len(set(ids)) for ids in id_lists) or not (
        set(id_lists[0]) == set(id_lists[1]) == set(id_lists[2])
    ):
        raise ConfigurationError(
            "LongMemEval retrieval-rank artifact question IDs must match exactly "
            "across answer prompts, private labels and public questions"
        )


def _public_session_id(source_id: str) -> str:
    """把公开 turn id 上卷到公开 session id。"""

    prefix, separator, suffix = source_id.rpartition(":t")
    return prefix if separator and suffix.isdigit() else source_id


def _na_payload(granularity: str) -> dict[str, Any]:
    """构造 provider 未声明 provenance 时的结构化 N/A。"""

    return {
        "metric_name": LongMemEvalRetrievalRankEvaluator.metric_name,
        "score_records": [],
        "total_questions": 0,
        "mean_score": 0.0,
        "correct_count": None,
        "summary": {
            "status": "n/a",
            "reason": "provider provenance is unavailable",
            "provenance_granularity": granularity,
            "turn2session_view": "not_artifact_computable",
        },
    }


__all__ = ["LongMemEvalRetrievalRankEvaluator"]
