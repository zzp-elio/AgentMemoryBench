"""BEAM rubric-nugget LLM judge evaluator。

对每个 probing question 的 rubric 逐条打分（0.0 / 0.5 / 1.0），按能力聚合，
输出 overall 和 category_breakdown。**统一用 float 修正官方 int 截断 0.5 的 bug**
（compute_metrics.py 9 个 evaluate_* 用 int(response['score']) 把 0.5 截成 0）。
event_ordering v1 仅 rubric judge，kendall-tau 排序分 defer 到 v2。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from memory_benchmark.core.exceptions import ConfigurationError, JudgeOutputError
from memory_benchmark.evaluators.llm_judge import LLMJudgeEvaluator
from memory_benchmark.storage import ExperimentPaths, read_jsonl


# Official source: third_party/benchmarks/BEAM/src/prompts.py:11547-11617
# Placeholders: <question>, <rubric_item>, <llm_response>
BEAM_JUDGE_PROMPT = """You are an expert evaluator tasked with judging whether the LLM's response demonstrates compliance with the specified RUBRIC CRITERION.

## EVALUATION INPUTS
- QUESTION (what the user asked): <question>
- RUBRIC CRITERION (what to check): <rubric_item>
- RESPONSE TO EVALUATE: <llm_response>

## EVALUATION RUBRIC:
The rubric defines a specific requirement, constraint, or expected behavior that the LLM response should demonstrate.

**IMPORTANT**: Pay careful attention to whether the rubric specifies:
- **Positive requirements** (things the response SHOULD include/do)
- **Negative constraints** (things the response SHOULD NOT include/do, often indicated by "no", "not", "avoid", "absent")

## RESPONSIVENESS REQUIREMENT (anchored to the QUESTION)
A compliant response must be **on-topic with respect to the QUESTION** and attempt to answer it.
- If the response does not address the QUESTION, score **0.0** and stop.
- For negative constraints, both must hold: (a) the response is responsive to the QUESTION, and (b) the prohibited element is absent.

## SEMANTIC TOLERANCE RULES:
Judge by meaning, not exact wording.
- Accept **paraphrases** and **synonyms** that preserve intent.
- **Case/punctuation/whitespace** differences must be ignored.
- **Numbers/currencies/dates** may appear in equivalent forms (e.g., "$68,000", "68k", "68,000 USD", or "sixty-eight thousand dollars"). Treat them as equal when numerically equivalent.
- If the rubric expects a number or duration, prefer **normalized comparison** (extract and compare values) over string matching.

## STYLE NEUTRALITY (prevents style contamination):
Ignore tone, politeness, length, and flourish unless the rubric explicitly requires a format/structure (e.g., "itemized list", "no citations", "one sentence").
- Do **not** penalize hedging, voice, or verbosity if content satisfies the rubric.
- Only evaluate format when the rubric **explicitly** mandates it.

## SCORING SCALE:
- **1.0 (Complete Compliance)**: Fully complies with the rubric criterion.
  - Positive: required element present, accurate, properly executed (allowing semantic equivalents).
  - Negative: prohibited element **absent** AND response is **responsive**.

- **0.5 (Partial Compliance)**: Partially complies.
  - Positive: element present but minor inaccuracies/incomplete execution.
  - Negative: generally responsive and mostly avoids the prohibited element but with minor/edge violations.

- **0.0 (No Compliance)**: Fails to comply.
  - Positive: required element missing or incorrect.
  - Negative: prohibited element present **or** response is non-responsive/evasive even if the element is absent.

## EVALUATION INSTRUCTIONS:
1. **Understand the Requirement**: Determine if the rubric is asking for something to be present (positive) or absent (negative/constraint).

2. **Parse Compound Statements**: If the rubric contains multiple elements connected by "and" or commas, evaluate whether:
   - **All elements** must be present for full compliance (1.0)
   - **Some elements** present indicates partial compliance (0.5)
   - **No elements** present indicates no compliance (0.0)

3. **Check Compliance**:
   - For positive requirements: Look for the presence and quality of the required element
   - For negative constraints: Look for the absence of the prohibited element

4. **Assign Score**: Based on compliance with the specific rubric criterion according to the scoring scale above.

5. **Provide Reasoning**: Explain whether the rubric criterion was satisfied and justify the score.

## OUTPUT FORMAT:
Return your evaluation in JSON format with two fields:

{
   "score": [your score: 1.0, 0.5, or 0.0],
   "reason": "[detailed explanation of whether the rubric criterion was satisfied and why this justified the assigned score]"
}

NOTE: ONLY output the json object, without any explanation before or after that
"""

# Official source: compute_metrics.py:346-360（9/10 evaluate_* 均此模式）。
BEAM_JUDGE_OFFICIAL_SOURCE = (
    "third_party/benchmarks/BEAM/src/compute_metrics.py:346-360; "
    "prompts.py:11547-11617 (unified_llm_judge_base_prompt)"
)
BEAM_JUDGE_PROFILE_NOTE = (
    "Official compute_metrics.py uses int(response['score']) which truncates 0.5→0 "
    "(bug at lines 357,385,454,483,512,541,570,599,628; only event_ordering uses "
    "float() at line 425). This evaluator uniformly uses float(0.0/0.5/1.0), "
    "matching the judge prompt scoring scale. Official judge model was gpt-4o; "
    "this project uses gpt-4o-mini by policy."
)

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

            # 逐条 rubric item 打分（用 float，不用 int）
            item_scores: list[dict[str, Any]] = []
            total_score = 0.0
            for rubric_item in rubric:
                prompt = BEAM_JUDGE_PROMPT.replace(
                    "<question>", question_text
                ).replace(
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

            llm_judge_score = total_score / len(rubric) if rubric else 0.0

            score_records.append(
                {
                    "record_kind": "beam_rubric_judge",
                    "question_id": question_id,
                    "conversation_id": public_record.get("conversation_id"),
                    "metric_name": self.metric_name,
                    "score": llm_judge_score,
                    "ability": ability,
                    "item_scores": item_scores,
                    "rubric_count": len(rubric),
                    "question_text": question_text,
                    "prediction_text": prediction_text,
                }
            )

        return _build_evaluation_payload(score_records)


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
    for record in score_records:
        ability = record.get("ability")
        if ability:
            ability_scores[ability].append(record["score"])

    ability_means: dict[str, float] = {}
    for ability in BEAM_ABILITY_KEYS:
        scores = ability_scores.get(ability, [])
        ability_means[ability] = sum(scores) / len(scores) if scores else 0.0

    # overall = 10 能力均值
    overall = sum(ability_means.values()) / len(BEAM_ABILITY_KEYS)

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
                "ability_breakdown": ability_means,
            },
            "category_breakdown": category_breakdown,
            "official_source": BEAM_JUDGE_OFFICIAL_SOURCE,
            "profile_note": BEAM_JUDGE_PROFILE_NOTE,
        },
    }
