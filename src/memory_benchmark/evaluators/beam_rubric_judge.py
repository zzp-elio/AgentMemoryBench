"""BEAM rubric judge 与 event-ordering 官方有效评测面。

九类逐条 rubric 打分；event_ordering 另按官方实际调用路径计算
LLM 语义判等后的 Kendall tau-b x F1 复合分。主分保留 prompt 明确允许的
0.5，同时记录官方 ``int()`` 截断对照分。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from scipy.stats import kendalltau

from memory_benchmark.core.exceptions import ConfigurationError, JudgeOutputError
from memory_benchmark.evaluators.llm_judge import LLMJudgeEvaluator
from memory_benchmark.prompts.benchmarks.beam import (
    BEAM_EQUIVALENCE_MESSAGES,
    BEAM_JUDGE_OFFICIAL_SOURCE,
    BEAM_JUDGE_PROFILE_NOTE,
    BEAM_JUDGE_PROMPT,
)
from memory_benchmark.storage import ExperimentPaths, read_jsonl


BEAM_ABILITY_KEYS: tuple[str, ...] = (
    "abstention",
    "contradiction_resolution",
    "event_ordering",
    "information_extraction",
    "instruction_following",
    "knowledge_update",
    "multi_session_reasoning",
    "preference_following",
    "summarization",
    "temporal_reasoning",
)


class BeamRubricJudgeEvaluator(LLMJudgeEvaluator):
    """BEAM rubric 逐条 LLM judge + ability 聚合 evaluator。"""

    metric_name = "beam_rubric_judge"
    benchmark_name = "BEAM"
    official_source = BEAM_JUDGE_OFFICIAL_SOURCE
    profile_note = BEAM_JUDGE_PROFILE_NOTE

    @property
    def client(self) -> Any | None:
        """返回测试注入的 fake client。"""

        return self._client

    def _judge_json(self, prompt: str) -> dict[str, Any]:
        """调用 fake/真实 judge 并解析 JSON 对象。"""

        if self._client is not None and hasattr(self._client, "judge_json"):
            payload = self._client.judge_json(prompt)
            if not isinstance(payload, dict):
                raise JudgeOutputError("fake BEAM judge must return a dict")
            return payload
        model_response = self._call_model_with_usage(prompt)
        self._record_judge_llm_call(model_response)
        return _parse_judge_json(model_response.text)

    def _judge_equivalence(self, first: str, second: str) -> bool:
        """按官方 system/user 消息判定两段文本是否同一事件。"""

        messages = _equivalence_messages(first, second)
        if self._client is not None and hasattr(self._client, "judge_equivalence"):
            response = self._client.judge_equivalence(messages)
            if not isinstance(response, str):
                raise JudgeOutputError("fake BEAM equivalence judge must return text")
            return "yes" in response.lower()
        # The project Responses API wrapper accepts role-tagged input messages. This is
        # the same judge dependency as rubric scoring, not a new API/model class.
        # 走与 rubric 相同的计量外壳：原始 messages 原样发送、恰好记一次 usage observation。
        model_response = self._invoke_judge_model(
            api_input=messages,
            tokenizer_prompt_text=_equivalence_messages_text(messages),
        )
        self._record_judge_llm_call(model_response)
        return "yes" in model_response.text.lower()

    def evaluate_run_artifacts(
        self,
        *,
        paths: ExperimentPaths,
        manifest: dict[str, Any],
        max_workers: int = 1,
    ) -> dict[str, Any]:
        """读取 prediction + private labels 并计算 rubric judge 指标。"""

        public_by_id = _index_by_question_id(
            _read_required_jsonl(paths.public_questions_path, "public_questions")
        )
        prediction_by_id = _index_by_question_id(
            _read_required_jsonl(paths.method_predictions_path, "method_predictions")
        )
        private_by_id = _index_by_question_id(
            _read_required_jsonl(
                paths.evaluator_private_labels_path,
                "evaluator_private_labels",
            )
        )

        sink = self._new_efficiency_observation_sink()
        score_records: list[dict[str, Any]] = []
        for question_id in public_by_id:
            if question_id not in prediction_by_id:
                continue
            if question_id not in private_by_id:
                raise ConfigurationError(
                    f"missing private label for {question_id}"
                )

            public_record = public_by_id[question_id]
            prediction_record = prediction_by_id[question_id]
            private_record = private_by_id[question_id]

            question_text = public_record.get("question_text", "")
            prediction_text = prediction_record.get("answer", "")
            rubric = _extract_rubric(private_record)
            ability = _extract_ability(private_record)

            if not rubric:
                continue

            conversation_id = public_record.get("conversation_id")
            # 同一真实公开问题的全部 rubric-item judge 与 event-ordering 判等调用共用一个
            # judge scope，靠 collector 的 call index 区分，不拆成伪 question。
            with sink.unit_scope(conversation_id, question_id):
                # 逐条 rubric item 打分；float 主分与官方 int 对照分同时保留。
                item_scores: list[dict[str, Any]] = []
                total_score = 0.0
                official_int_total = 0
                for rubric_item in rubric:
                    # Official evaluate_* leaves <question> untouched and replaces only
                    # rubric/response (compute_metrics.py:347-349 and repeated call sites).
                    prompt = BEAM_JUDGE_PROMPT.replace(
                        "<rubric_item>", str(rubric_item)
                    ).replace(
                        "<llm_response>", prediction_text
                    )
                    result = self._judge_json(prompt)
                    item_score = float(result["score"])
                    item_scores.append(
                        {
                            "rubric_item": rubric_item,
                            "score": item_score,
                            "reason": result.get("reason", ""),
                        }
                    )
                    total_score += item_score
                    official_int_total += int(item_score)

                llm_judge_score = total_score / len(rubric) if rubric else 0.0
                official_int_score = official_int_total / len(rubric) if rubric else 0.0

                event_details: dict[str, Any] = {}
                if ability == "event_ordering":
                    event_details = _event_ordering_score(
                        reference=list(map(str, rubric)),
                        system=prediction_text.split("\n"),
                        equivalent=self._judge_equivalence,
                    )

            score_records.append(
                {
                    "record_kind": "beam_rubric_judge",
                    "question_id": question_id,
                    "conversation_id": conversation_id,
                    "metric_name": self.metric_name,
                    "score": llm_judge_score,
                    "llm_judge_score_official_int": official_int_score,
                    "ability": ability,
                    "item_scores": item_scores,
                    "rubric_count": len(rubric),
                    "question_text": question_text,
                    "prediction_text": prediction_text,
                    "details": event_details,
                    "event_ordering_composite_score": event_details.get(
                        "event_ordering_composite_score"
                    ),
                }
            )

        return self._finalize_artifact_payload(
            _build_evaluation_payload(score_records),
            sink,
        )


def _extract_rubric(private_record: dict[str, Any]) -> list[Any]:
    """从私有标签中提取 rubric items。"""

    metadata = private_record.get("metadata")
    if not isinstance(metadata, dict):
        return []
    rubric = metadata.get("rubric")
    if not isinstance(rubric, list):
        return []
    return rubric


def _extract_ability(private_record: dict[str, Any]) -> str | None:
    """从私有标签中提取 ability 名称。"""

    metadata = private_record.get("metadata")
    if not isinstance(metadata, dict):
        return None
    ability = metadata.get("ability")
    return ability if isinstance(ability, str) else None


def _equivalence_messages(first: str, second: str) -> list[dict[str, str]]:
    """将官方 llm_equivalence 模板填入 role-tagged messages。"""

    return [
        dict(BEAM_EQUIVALENCE_MESSAGES[0]),
        {
            "role": "user",
            "content": BEAM_EQUIVALENCE_MESSAGES[1]["content"]
            .replace("<first_paragraph>", first)
            .replace("<second_paragraph>", second),
        },
    ]


def _equivalence_messages_text(messages: list[dict[str, str]]) -> str:
    """把 role-tagged 判等 messages 确定性拼接为 tokenizer 回退估算文本。

    仅在 API usage 缺失时用于 token 估算；不改变发送给 API 的原始 messages，也不改变
    官方 equivalence prompt。拼接顺序与内容固定，便于测试逐字断言。
    """

    return "\n".join(
        f"{message['role']}: {message['content']}" for message in messages
    )


def _event_ordering_score(
    *,
    reference: list[str],
    system: list[str],
    equivalent: Any,
) -> dict[str, Any]:
    """按官方贪心 1-1 LLM alignment 计算 tau-b x F1。"""

    used: set[int] = set()
    system_canon: list[str] = []
    for system_item in system:
        matched_index = None
        for index, reference_item in enumerate(reference):
            if index not in used and equivalent(reference_item, system_item):
                matched_index = index
                break
        if matched_index is None:
            system_canon.append(system_item)
        else:
            system_canon.append(reference[matched_index])
            used.add(matched_index)

    tp = len(set(reference) & set(system_canon))
    fp = len([item for item in system_canon if item not in reference])
    fn = len([item for item in reference if item not in system_canon])
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    union = list(dict.fromkeys(reference + system_canon))
    tie_rank = len(union) + 1

    def to_rank(sequence: list[str]) -> list[int]:
        """把顺序列表投影到官方 union rank 空间。"""

        ranks = {item: index + 1 for index, item in enumerate(sequence)}
        return [ranks.get(item, tie_rank) for item in union]

    tau_b, _ = kendalltau(
        to_rank(reference),
        to_rank(system_canon),
        variant="b",
        method="auto",
    )
    tau_norm = (float(tau_b) + 1) / 2 if tau_b is not None else 0.0
    return {
        "event_ordering_precision": precision,
        "event_ordering_recall": recall,
        "event_ordering_f1": f1,
        "event_ordering_tau_norm": tau_norm,
        "event_ordering_composite_score": tau_norm * f1,
        "aligned_prediction_items": system_canon,
        "alignment": "llm_equivalence_greedy_1_to_1",
        "prediction_split": "llm_response.split('\\n')",
    }


def _index_by_question_id(
    records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """按 question_id 索引 artifact records。"""

    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        question_id = record.get("question_id")
        if not isinstance(question_id, str) or not question_id.strip():
            raise ConfigurationError("question_id is required")
        if question_id in indexed:
            raise ConfigurationError(f"duplicate question_id: {question_id}")
        indexed[question_id] = record
    return indexed


def _read_required_jsonl(path: Any, artifact_name: str) -> list[dict[str, Any]]:
    """读取非空 JSONL artifact。"""

    if not path.is_file():
        raise ConfigurationError(f"{artifact_name} is missing: {path}")
    rows = read_jsonl(path)
    if not rows:
        raise ConfigurationError(f"{artifact_name} is empty: {path}")
    if any(not isinstance(row, dict) for row in rows):
        raise ConfigurationError(f"{artifact_name} rows must be JSON objects")
    return rows


def _parse_judge_json(text: str) -> dict[str, Any]:
    """解析 judge JSON，兼容 ```json fenced block。"""

    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    import json

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise JudgeOutputError("BEAM judge output must be JSON") from exc
    if not isinstance(payload, dict):
        raise JudgeOutputError("BEAM judge output must be a JSON object")
    return payload


def _build_evaluation_payload(
    score_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """构造 BEAM rubric judge 完整 evaluation payload。"""

    if not score_records:
        return {
            "metric_name": "beam_rubric_judge",
            "score_records": [],
            "total_questions": 0,
            "mean_score": 0.0,
            "correct_count": None,
            "summary": {
                "status": "n/a",
                "overall_score": {},
                "category_breakdown": [],
                "official_source": BEAM_JUDGE_OFFICIAL_SOURCE,
                "profile_note": BEAM_JUDGE_PROFILE_NOTE,
            },
        }

    # per-ability 聚合（每能力取均）
    ability_scores: dict[str, list[float]] = defaultdict(list)
    official_int_scores: dict[str, list[float]] = defaultdict(list)
    for record in score_records:
        ability = record.get("ability")
        if ability:
            ability_scores[ability].append(record["score"])
            official_int_scores[ability].append(
                record.get("llm_judge_score_official_int", int(record["score"]))
            )

    ability_means: dict[str, float] = {}
    for ability in BEAM_ABILITY_KEYS:
        scores = ability_scores.get(ability, [])
        ability_means[ability] = sum(scores) / len(scores) if scores else 0.0

    # overall = 10 能力均值
    overall = sum(ability_means.values()) / len(BEAM_ABILITY_KEYS)
    official_int_means = {
        ability: (
            sum(official_int_scores.get(ability, []))
            / len(official_int_scores[ability])
            if official_int_scores.get(ability)
            else 0.0
        )
        for ability in BEAM_ABILITY_KEYS
    }
    official_int_overall = sum(official_int_means.values()) / len(BEAM_ABILITY_KEYS)
    event_composite_scores = [
        float(record["event_ordering_composite_score"])
        for record in score_records
        if record.get("event_ordering_composite_score") is not None
    ]

    category_breakdown = [
        {
            "category": ability,
            "rubric_judge_mean_score": ability_means[ability],
            "question_count": len(ability_scores.get(ability, [])),
        }
        for ability in BEAM_ABILITY_KEYS
    ]

    return {
        "metric_name": "beam_rubric_judge",
        "score_records": score_records,
        "total_questions": len(score_records),
        "mean_score": overall,
        "correct_count": None,
        "summary": {
            "status": "ok",
            "overall_score": {
                "beam_rubric_judge_mean": overall,
                "llm_judge_score_official_int": official_int_overall,
                "ability_breakdown": ability_means,
                "official_int_ability_breakdown": official_int_means,
                "event_ordering_composite_mean": (
                    sum(event_composite_scores) / len(event_composite_scores)
                    if event_composite_scores
                    else None
                ),
            },
            "category_breakdown": category_breakdown,
            "official_source": BEAM_JUDGE_OFFICIAL_SOURCE,
            "profile_note": BEAM_JUDGE_PROFILE_NOTE,
        },
    }
