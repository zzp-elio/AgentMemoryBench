"""BEAM benchmark 所有的统一答题与裁判 prompt。"""

from __future__ import annotations

from memory_benchmark.core import AnswerPromptResult, PromptMessage, Question
from memory_benchmark.core.provider_protocol import RetrievalResult

BEAM_ANSWER_PROMPT_PROFILE = "beam_rag_v1"
BEAM_ANSWER_PROMPT_OFFICIAL_SOURCE = (
    "third_party/benchmarks/BEAM/src/prompts.py:11683-11701"
)
BEAM_ANSWER_PROMPT_TEMPLATE = (
    "\n"
    "You are an assistant that MUST answer questions using ONLY the information "
    "provided in the context below. \n"
    "\n"
    "STRICT INSTRUCTIONS:\n"
    "1. Answer ONLY based on the provided context\n"
    "2. Do NOT use your internal knowledge\n"
    "\n"
    "CONTEXT:\n"
    "<context>\n"
    "\n"
    "QUESTION:\n"
    "<question>\n"
    "\n"
    "ANSWER REQUIREMENTS:\n"
    "- Be direct and concise\n"
    "- Only output the answer to the question without any explanation \n"
    "\n"
    "RESPONSE:\n"
)


def build_beam_unified_answer_prompt(
    question: Question,
    retrieval_result: RetrievalResult,
) -> AnswerPromptResult:
    """按官方 answer_generation_for_rag 构造完整 framework reader prompt。"""

    answer_prompt = BEAM_ANSWER_PROMPT_TEMPLATE.replace(
        "<context>", retrieval_result.formatted_memory
    ).replace("<question>", question.text)
    return AnswerPromptResult(
        question_id=question.question_id,
        conversation_id=question.conversation_id,
        answer_prompt=answer_prompt,
        prompt_messages=[PromptMessage(role="user", content=answer_prompt)],
        metadata={
            "prompt_track": "unified",
            "answer_prompt_profile": BEAM_ANSWER_PROMPT_PROFILE,
            "official_source": BEAM_ANSWER_PROMPT_OFFICIAL_SOURCE,
        },
    )


# Official source: third_party/benchmarks/BEAM/src/prompts.py:11547-11617
# Placeholders: <question>, <rubric_item>, <llm_response>
BEAM_JUDGE_PROMPT = ("""
You are an expert evaluator tasked with judging whether the LLM's response demonstrates compliance with the specified RUBRIC CRITERION.

## EVALUATION INPUTS
- QUESTION (what the user asked): <question>
- RUBRIC CRITERION (what to check): <rubric_item>
- RESPONSE TO EVALUATE: <llm_response>

## EVALUATION RUBRIC:
The rubric defines a specific requirement, constraint, or expected behavior that the LLM response should demonstrate.<OFFICIAL_SPACE>

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
- **Numbers/currencies/dates** may appear in equivalent forms (e.g., “$68,000”, “68k”, “68,000 USD”, or “sixty-eight thousand dollars”). Treat them as equal when numerically equivalent.
- If the rubric expects a number or duration, prefer **normalized comparison** (extract and compare values) over string matching.

## STYLE NEUTRALITY (prevents style contamination):
Ignore tone, politeness, length, and flourish unless the rubric explicitly requires a format/structure (e.g., “itemized list”, “no citations”, “one sentence”).
- Do **not** penalize hedging, voice, or verbosity if content satisfies the rubric.
- Only evaluate format when the rubric **explicitly** mandates it.

## SCORING SCALE:
- **1.0 (Complete Compliance)**: Fully complies with the rubric criterion.
  - Positive: required element present, accurate, properly executed (allowing semantic equivalents).
  - Negative: prohibited element **absent** AND response is **responsive**.
<OFFICIAL_TWO_SPACES>
- **0.5 (Partial Compliance)**: Partially complies.
  - Positive: element present but minor inaccuracies/incomplete execution.
  - Negative: generally responsive and mostly avoids the prohibited element but with minor/edge violations.
<OFFICIAL_TWO_SPACES>
- **0.0 (No Compliance)**: Fails to comply.
  - Positive: required element missing or incorrect.
  - Negative: prohibited element present **or** response is non-responsive/evasive even if the element is absent.

## EVALUATION INSTRUCTIONS:
1. **Understand the Requirement**: Determine if the rubric is asking for something to be present (positive) or absent (negative/constraint).

2. **Parse Compound Statements**: If the rubric contains multiple elements connected by "and" or commas, evaluate whether:
   - **All elements** must be present for full compliance (1.0)
   - **Some elements** present indicates partial compliance (0.5)
   - **No elements** present indicates no compliance (0.0)
<OFFICIAL_THREE_SPACES>
3. **Check Compliance**:<OFFICIAL_SPACE>
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
    .replace("<OFFICIAL_THREE_SPACES>", "   ")
    .replace("<OFFICIAL_TWO_SPACES>", "  ")
    .replace("<OFFICIAL_SPACE>", " ")
)

BEAM_EQUIVALENCE_MESSAGES = (
    {
        "role": "system",
        "content": """
            You are a binary classifier.
            If the TWO snippets describe the SAME event/fact, reply **YES**
            Otherwise reply **NO**. No extra words.
            DO NOT provide any exaplanation.
        """,
    },
    {
        "role": "user",
        "content": "First snippet: <first_paragraph> \n\n"
        "                       Second snippet: <second_paragraph>\n"
        "                    ",
    },
)

BEAM_JUDGE_OFFICIAL_SOURCE = (
    "third_party/benchmarks/BEAM/src/evaluation/compute_metrics.py:346-360; "
    "prompts.py:11547-11617 (unified_llm_judge_base_prompt)"
)
BEAM_JUDGE_PROFILE_NOTE = (
    "The official prompt explicitly permits 1.0, 0.5 or 0.0 at prompts.py:11579-11613, "
    "while compute_metrics.py truncates 0.5 via int() at lines 357,385,454,483,512,541,"
    "570,599,628. The primary score follows the prompt's float intent and details retain "
    "the official-int comparison. Official judge model was gpt-4.1-mini; "
    "this project uses gpt-4o-mini by policy."
)


__all__ = [
    "BEAM_ANSWER_PROMPT_OFFICIAL_SOURCE",
    "BEAM_ANSWER_PROMPT_PROFILE",
    "BEAM_ANSWER_PROMPT_TEMPLATE",
    "BEAM_EQUIVALENCE_MESSAGES",
    "BEAM_JUDGE_OFFICIAL_SOURCE",
    "BEAM_JUDGE_PROFILE_NOTE",
    "BEAM_JUDGE_PROMPT",
    "build_beam_unified_answer_prompt",
]
