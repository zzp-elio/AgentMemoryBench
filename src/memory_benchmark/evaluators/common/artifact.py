"""artifact-only retrieval evaluator 的公共装载与身份校验。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from memory_benchmark.core import ConfigurationError
from memory_benchmark.storage import ExperimentPaths, read_jsonl

from ..gold_evidence_groups import require_manifest_gold_evidence_contract_v1
from ..retrieval_evidence import require_manifest_retrieval_evidence_contract_v1


@dataclass(frozen=True)
class RetrievalArtifacts:
    """一次 retrieval 评测所需的三类对齐 artifact。"""

    answer_records: list[dict[str, Any]]
    private_records: list[dict[str, Any]]
    public_records: list[dict[str, Any]]
    private_by_id: dict[Any, dict[str, Any]]
    category_by_id: dict[Any, Any]


def load_retrieval_artifacts(
    *,
    paths: ExperimentPaths,
    manifest: dict[str, Any],
    mismatch_error: str,
) -> RetrievalArtifacts:
    """先过两道版本门，再装载并严格对齐三类 question artifact。"""

    require_manifest_gold_evidence_contract_v1(manifest)
    require_manifest_retrieval_evidence_contract_v1(manifest)
    answers = read_jsonl(paths.answer_prompts_path)
    private = read_jsonl(paths.evaluator_private_labels_path)
    public = read_jsonl(paths.public_questions_path)
    _validate_matching_question_ids(
        answers,
        private,
        public,
        mismatch_error=mismatch_error,
    )
    return RetrievalArtifacts(
        answer_records=answers,
        private_records=private,
        public_records=public,
        private_by_id={record["question_id"]: record for record in private},
        category_by_id={
            record["question_id"]: record.get("category") for record in public
        },
    )


def _validate_matching_question_ids(
    *record_groups: list[dict[str, Any]],
    mismatch_error: str,
) -> None:
    """校验每组 question id 唯一且各组集合完全一致。"""

    id_lists = [
        [record.get("question_id") for record in records]
        for records in record_groups
    ]
    if (
        not id_lists
        or any(len(ids) != len(set(ids)) for ids in id_lists)
        or any(set(ids) != set(id_lists[0]) for ids in id_lists[1:])
    ):
        raise ConfigurationError(mismatch_error)


__all__ = ["RetrievalArtifacts", "load_retrieval_artifacts"]
