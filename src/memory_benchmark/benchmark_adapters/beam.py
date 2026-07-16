"""BEAM conversation-QA benchmark adapter。

把 `data/BEAM/` 下 100K/500K/1M/10M 的 HF arrow 数据转换为统一
Dataset。前三个 variant 的 chat 是 list[session]；10M 是按 plan 聚合的
list[dict]，按官方顺序展开为全 conversation 唯一的 canonical session。
probing_questions 是 Python-repr 字符串（`ast.literal_eval` 解析），
content 末尾带 `->-> a,b` 尾标记需裁剪。私有 rubric/ideal_response 等仅
进 GoldAnswerInfo，公开 conversation 过 validate_no_private_keys。
"""

from __future__ import annotations

import ast
import copy
import hashlib
import re
from pathlib import Path
from typing import Any

from memory_benchmark.core import (
    AnswerPromptResult,
    Conversation,
    Dataset,
    GoldAnswerInfo,
    GoldEvidenceGroup,
    GoldEvidenceGroupSet,
    PromptMessage,
    Question,
    Session,
    Turn,
)
from memory_benchmark.core.exceptions import ConfigurationError, DatasetValidationError
from memory_benchmark.core.provider_protocol import RetrievalResult

from .base import BenchmarkAdapter, reached_limit
from .contracts import (
    BenchmarkLoadRequest,
    BenchmarkResumePolicy,
    BenchmarkSmokePolicy,
    BenchmarkVariantSpec,
    PreparedBenchmarkRun,
    RunScope,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_BEAM_DATASET_DIR = Path("data/BEAM/beam_dataset")
_BEAM_10M_DATASET_DIR = Path("data/BEAM/beam_10M_dataset")

BEAM_OFFICIAL_REPO_URL = "https://github.com/mohammadtavakoli78/BEAM"
BEAM_OFFICIAL_PAPER_URL = "https://arxiv.org/abs/2510.27246"
BEAM_OFFICIAL_DATASET_URL = "https://huggingface.co/datasets/Mohammadta/BEAM"
BEAM_OFFICIAL_10M_DATASET_URL = "https://huggingface.co/datasets/Mohammadta/BEAM-10M"
BEAM_LICENSE = "CC-BY-SA-4.0"
_SOURCE_HASH_CHUNK_SIZE = 1024 * 1024

# Arrow 目录名保留 HF 原始大写 split 名；10M 使用独立数据集目录。
_VARIANT_PATH_MAP: dict[str, Path] = {
    "100k": _BEAM_DATASET_DIR / "100K",
    "500k": _BEAM_DATASET_DIR / "500K",
    "1m": _BEAM_DATASET_DIR / "1M",
    "10m": _BEAM_10M_DATASET_DIR / "10M",
}

BEAM_VARIANT_SPECS: tuple[BenchmarkVariantSpec, ...] = tuple(
    BenchmarkVariantSpec(
        name=variant_name,
        source_relative_paths=(source_path,),
    )
    for variant_name, source_path in _VARIANT_PATH_MAP.items()
)

BEAM_VARIANT_BY_NAME: dict[str, BenchmarkVariantSpec] = {
    spec.name: spec for spec in BEAM_VARIANT_SPECS
}

# 单次 run 始终对应一个 variant。双结构认证由默认 100k smoke 和显式
# `--variant 10m` smoke 两次独立运行组成，不混合数据指纹，也不扩 selector。
BEAM_SMOKE_POLICY = BenchmarkSmokePolicy(
    history_axis="rounds",
    default_history_limit=1,
    default_isolation_limit=1,
    default_question_limit=1,
)
BEAM_RESUME_POLICY = BenchmarkResumePolicy(
    smoke_enabled=False,
    ingest_checkpoint="conversation",
    answer_checkpoint="question",
    reuse_saved_retrieval=True,
    evaluation_artifact_only=True,
)

# 10 类记忆能力（第一手 compute_metrics.py 10 个 evaluate_* = 真实 probing_questions 10 key）。
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

# --- unified answer prompt --------------------------------------------------
# 官方 answer_generation_for_rag（src/prompts.py:11683-11701），由 RAG/记忆
# 分支在 long_term_memory_methods.py:598-643 实际调用。long-context 分支
# (:534-596) 直接发送 raw history messages，属于另一 baseline，不适合框架
# formatted_memory。官方 typo/首尾换行/行尾空格均按字节保留。

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

# --- content 尾标记裁剪 -----------------------------------------------------
# turn content 末尾的 "->-> a,b" 是数据生成 artifact（session 索引,turn 索引
# 或 N/A），只留真实文本。正则：末尾可选空白 + ->-> + 空格 + 数字 + , + (数字|N/A)。

_TAIL_MARKER_PATTERN = re.compile(r"\s*->->\s+\d+\s*,\s*(?:\d+|N/A)\s*$")


def strip_tail_marker(content: str) -> str:
    """裁掉 content 末尾的 `->-> a,b` 尾标记，保留真实文本。

    输入:
        content: 原始 turn content，可能以 `->-> 1,1` 结尾。

    输出:
        str: 裁剪尾标记后的纯文本。若 content 不以尾标记结尾则原样返回。
    """

    return _TAIL_MARKER_PATTERN.sub("", content)


# ---------------------------------------------------------------------------
# BeamAdapter
# ---------------------------------------------------------------------------


class BeamAdapter(BenchmarkAdapter):
    """BEAM arrow → 统一 Dataset adapter。"""

    name = "beam"

    def __init__(
        self,
        project_root: str | Path,
        variant: str = "100k",
    ) -> None:
        """初始化 BEAM adapter 并锁定 concrete variant。"""

        super().__init__(project_root)
        normalized_variant = variant.strip().lower() if isinstance(variant, str) else ""
        if not normalized_variant:
            raise ConfigurationError("beam variant is required")
        if normalized_variant not in _VARIANT_PATH_MAP:
            allowed = ", ".join(_VARIANT_PATH_MAP)
            raise ConfigurationError(
                f"Unknown beam variant '{variant}'. Allowed: {allowed}"
            )
        self.variant = normalized_variant
        self._source_relative_path = _VARIANT_PATH_MAP[normalized_variant]

    def load_dataset(self, limit: int | None = None) -> Dataset:
        """读取 HF arrow 并转换为统一 Dataset。"""

        if limit is not None and limit <= 0:
            raise DatasetValidationError("beam limit must be a positive integer")

        try:
            import datasets as hf_datasets
        except ImportError as exc:
            raise ConfigurationError(
                "datasets (HuggingFace) is required for BEAM adapter"
            ) from exc

        dataset_path = self.require_path(*self._source_relative_path.parts)
        ds = hf_datasets.load_from_disk(str(dataset_path))

        conversations: list[Conversation] = []
        source_fully_scanned = True
        for row_idx, row in enumerate(ds):
            conversations.append(
                _conversation_from_row(
                    row,
                    row_idx=row_idx,
                    ten_million=self.variant == "10m",
                )
            )
            if reached_limit(len(conversations), limit):
                source_fully_scanned = False
                break

        source_size_bytes, source_sha256 = _directory_source_identity(dataset_path)
        return Dataset(
            dataset_name=self.name,
            conversations=conversations,
            metadata={
                "source_paths": [str(dataset_path)],
                "variant": self.variant,
                "source_format": "beam_arrow",
                "official_repo_url": BEAM_OFFICIAL_REPO_URL,
                "official_paper_url": BEAM_OFFICIAL_PAPER_URL,
                "official_dataset_url": (
                    BEAM_OFFICIAL_10M_DATASET_URL
                    if self.variant == "10m"
                    else BEAM_OFFICIAL_DATASET_URL
                ),
                "license": BEAM_LICENSE,
                "source_size_bytes": source_size_bytes,
                "source_sha256": source_sha256,
                "total_raw_rows": len(ds),
                "source_fully_scanned": source_fully_scanned,
                "loaded_conversation_count": len(conversations),
                "loaded_session_count": sum(
                    len(conversation.sessions) for conversation in conversations
                ),
                "loaded_turn_count": sum(
                    len(session.turns)
                    for conversation in conversations
                    for session in conversation.sessions
                ),
                "loaded_question_count": sum(
                    len(conversation.questions) for conversation in conversations
                ),
            },
        )


# ---------------------------------------------------------------------------
# prepare_run
# ---------------------------------------------------------------------------


def prepare_beam_run(
    project_root: Path,
    request: BenchmarkLoadRequest,
) -> PreparedBenchmarkRun:
    """为 BEAM concrete variant 构造 full 或 smoke 运行。"""

    variant_spec = BEAM_VARIANT_BY_NAME.get(request.variant)
    if variant_spec is None:
        allowed = ", ".join(spec.name for spec in BEAM_VARIANT_SPECS)
        raise ConfigurationError(
            f"Unknown beam variant '{request.variant}'. Allowed: {allowed}"
        )

    adapter = BeamAdapter(project_root, variant=request.variant)
    if request.run_scope is RunScope.FULL:
        dataset = adapter.load()
    elif request.run_scope is RunScope.SMOKE:
        dataset = _build_beam_smoke_dataset(
            adapter.load(limit=request.smoke_conversation_limit),
            round_limit=request.smoke_turn_limit,
        )
    else:  # pragma: no cover
        raise ConfigurationError(f"unsupported BEAM run scope: {request.run_scope}")

    metadata = copy.deepcopy(dataset.metadata)
    metadata["variant"] = request.variant
    metadata["run_scope"] = request.run_scope.value
    metadata["smoke_policy"] = BEAM_SMOKE_POLICY.to_dict()
    metadata["resume_policy"] = BEAM_RESUME_POLICY.to_dict()
    return PreparedBenchmarkRun(
        variant=request.variant,
        run_scope=request.run_scope,
        dataset=Dataset(
            dataset_name=dataset.dataset_name,
            conversations=list(dataset.conversations),
            metadata=metadata,
        ),
        source_relative_paths=variant_spec.source_relative_paths,
    )


def build_beam_unified_answer_prompt(
    question: Question,
    retrieval_result: RetrievalResult,
) -> AnswerPromptResult:
    """按 BEAM 官方 answer_generation_for_rag 构造 framework reader prompt。"""

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


# ---------------------------------------------------------------------------
# 内部 helper
# ---------------------------------------------------------------------------


def _conversation_from_row(
    row: dict[str, Any],
    *,
    row_idx: int,
    ten_million: bool = False,
) -> Conversation:
    """把 BEAM arrow row 转成 Conversation。"""

    conversation_id = str(row.get("conversation_id", row_idx + 1))
    chat_raw = row.get("chat")
    if not isinstance(chat_raw, list):
        raise DatasetValidationError(
            f"beam row {row_idx}: chat must be a list, got {type(chat_raw).__name__}"
        )

    sessions = (
        _sessions_from_10m_chat(chat_raw, conversation_id=conversation_id)
        if ten_million
        else _sessions_from_standard_chat(chat_raw, conversation_id=conversation_id)
    )
    raw_id_to_public_turn_ids: dict[int, list[str]] = {}
    for session in sessions:
        for turn in session.turns:
            raw_id = turn.metadata.get("id")
            if isinstance(raw_id, int) and not isinstance(raw_id, bool):
                raw_id_to_public_turn_ids.setdefault(raw_id, []).append(turn.turn_id)

    # probing_questions: Python-repr 字符串 → ast.literal_eval
    probing_raw = row.get("probing_questions")
    if not isinstance(probing_raw, str) or not probing_raw.strip():
        raise DatasetValidationError(
            f"{conversation_id}: probing_questions must be a non-empty string"
        )
    try:
        probing = ast.literal_eval(probing_raw)
    except (ValueError, SyntaxError) as exc:
        raise DatasetValidationError(
            f"{conversation_id}: probing_questions is not valid Python literal: {exc}"
        ) from exc
    if not isinstance(probing, dict):
        raise DatasetValidationError(
            f"{conversation_id}: probing_questions must evaluate to a dict"
        )

    # 公开 Question + 私有 GoldAnswerInfo
    questions: list[Question] = []
    gold_answers: dict[str, GoldAnswerInfo] = {}
    for ability, question_list in probing.items():
        if not isinstance(question_list, list):
            raise DatasetValidationError(
                f"{conversation_id}/{ability}: probing value must be a list"
            )
        for q_idx, q_obj in enumerate(question_list, start=1):
            if not isinstance(q_obj, dict):
                raise DatasetValidationError(
                    f"{conversation_id}/{ability}[{q_idx - 1}]: must be a dict"
                )
            question_id = f"{conversation_id}:{ability}:q{q_idx}"
            question_text = _required_text(q_obj, "question", question_id)

            # 不同 ability 的 "答案" 字段不同（第一手实测）：
            # abstention → ideal_response; contradiction_resolution → ideal_answer;
            # event_ordering/information_extraction/knowledge_update/
            # multi_session_reasoning/temporal_reasoning → answer;
            # instruction_following/preference_following → expected_compliance;
            # summarization → ideal_summary
            gold_answer_text = _resolve_answer_field(q_obj, question_id)
            evidence_turn_ids, ambiguous_count, unmatched_count = _map_evidence_turn_ids(
                q_obj.get("source_chat_ids"),
                raw_id_to_public_turn_ids,
            )

            # 防御性保留原始 question_obj 全部字段（不含 question 文本自身），
            # 对齐 actor 好行为判例（raw_evidence 保留）。
            gold_metadata: dict[str, Any] = {
                "ability": ability,
                **{k: copy.deepcopy(v) for k, v in q_obj.items() if k != "question"},
                "evidence_turn_ids": evidence_turn_ids,
                "ambiguous_gold_id_count": ambiguous_count,
                "unmatched_gold_id_count": unmatched_count,
                # row 级私有元信息
                "conversation_seed": row.get("conversation_seed"),
                "user_profile": row.get("user_profile"),
                "conversation_plan": row.get("conversation_plan"),
                "user_questions": row.get("user_questions"),
                "narratives": row.get("narratives"),
            }

            questions.append(
                Question(
                    question_id=question_id,
                    conversation_id=conversation_id,
                    text=question_text,
                    category=ability,
                    metadata={},
                )
            )
            gold_answers[question_id] = GoldAnswerInfo(
                question_id=question_id,
                answer=gold_answer_text,
                evidence=[],
                metadata=gold_metadata,
                gold_evidence_contract_version="v1",
                evidence_group_sets=_beam_evidence_group_sets(
                    q_obj.get("source_chat_ids"),
                    raw_id_to_public_turn_ids,
                ),
            )

    return Conversation(
        conversation_id=conversation_id,
        sessions=sessions,
        questions=questions,
        gold_answers=gold_answers,
        metadata={},
    )


def _sessions_from_standard_chat(
    chat_raw: list[Any],
    *,
    conversation_id: str,
) -> list[Session]:
    """把 100K/500K/1M 的 list[session] chat 转成 canonical sessions。"""

    sessions: list[Session] = []
    for session_index, session_turns in enumerate(chat_raw, start=1):
        if not isinstance(session_turns, list):
            raise DatasetValidationError(
                f"{conversation_id}: chat[{session_index - 1}] must be a list"
            )
        sessions.append(
            _session_from_turns(
                session_turns,
                conversation_id=conversation_id,
                session_id=f"s{session_index}",
            )
        )
    return sessions


def _sessions_from_10m_chat(
    chat_raw: list[Any],
    *,
    conversation_id: str,
) -> list[Session]:
    """按官方 `chat[i]['plan-{i+1}']` 顺序展开 10M plan/batch。"""

    sessions: list[Session] = []
    for plan_index, plan_slot in enumerate(chat_raw):
        plan_number = plan_index + 1
        plan_id = f"plan-{plan_number}"
        if not isinstance(plan_slot, dict):
            raise DatasetValidationError(
                f"{conversation_id}: 10M chat[{plan_index}] must be a dict"
            )
        batches = plan_slot.get(plan_id)
        if not isinstance(batches, list):
            raise DatasetValidationError(
                f"{conversation_id}: 10M chat[{plan_index}]['{plan_id}'] must be a list"
            )
        for batch_index, batch in enumerate(batches):
            if not isinstance(batch, dict) or not isinstance(batch.get("turns"), list):
                raise DatasetValidationError(
                    f"{conversation_id}/{plan_id}: batch[{batch_index}] must contain turns"
                )
            session_turns: list[dict[str, Any]] = []
            for group_index, turn_group in enumerate(batch["turns"]):
                if not isinstance(turn_group, list):
                    raise DatasetValidationError(
                        f"{conversation_id}/{plan_id}/batch[{batch_index}]: "
                        f"turns[{group_index}] must be a list"
                    )
                session_turns.extend(turn_group)
            sessions.append(
                _session_from_turns(
                    session_turns,
                    conversation_id=conversation_id,
                    session_id=f"p{plan_number}:s{batch_index + 1}",
                    session_metadata={
                        "plan_id": plan_id,
                        "plan_index": plan_index,
                        "batch_number": batch.get("batch_number", batch_index + 1),
                    },
                )
            )
    return sessions


def _flatten_evidence_atoms(value: Any) -> list[Any]:
    """递归打平 BEAM 三种 source_chat_ids 结构，保留原子顺序。"""

    if isinstance(value, dict):
        return [atom for nested in value.values() for atom in _flatten_evidence_atoms(nested)]
    if isinstance(value, (list, tuple)):
        return [atom for nested in value for atom in _flatten_evidence_atoms(nested)]
    return [] if value is None else [value]


def _beam_evidence_group_sets(
    source_chat_ids: Any,
    raw_id_to_public_turn_ids: dict[int, list[str]],
) -> tuple[GoldEvidenceGroupSet, ...]:
    """把官方 raw source id 展开为 evaluator-private gold evidence groups。

    输入:
        source_chat_ids: 官方 `source_chat_ids` 原始结构（flat list / 语义分组
            dict / None）。
        raw_id_to_public_turn_ids: 当前 conversation 内 raw id 到全部公开 turn id
            的映射（1M 四个异常 conversation 中一个 raw id 可对应多个位置）。

    输出:
        tuple[GoldEvidenceGroupSet, ...]: 单个 turn view
        （`beam_source_message`）。每个稳定去重后的官方 raw id 是一个 unit：
        单一位置 → singleton mapped；重复 raw id → multi-child mapped any-of；
        找不到（含 10M `'--'`）→ unmatched；`None` → 空 groups。canonical turn
        id namespace 保持现状（`s1:t1` / `p1:s1:t1`），raw id 只作私有 unit_id。
    """

    groups: list[GoldEvidenceGroup] = []
    seen_unit_ids: set[str] = set()
    for atom in _flatten_evidence_atoms(source_chat_ids):
        unit_id = str(atom)
        if unit_id in seen_unit_ids:
            continue
        seen_unit_ids.add(unit_id)
        public_ids = (
            raw_id_to_public_turn_ids.get(atom, [])
            if isinstance(atom, int) and not isinstance(atom, bool)
            else []
        )
        if public_ids:
            groups.append(
                GoldEvidenceGroup(
                    unit_id=unit_id,
                    child_ids=tuple(dict.fromkeys(public_ids)),
                    mapping_status="mapped",
                )
            )
        else:
            groups.append(
                GoldEvidenceGroup(
                    unit_id=unit_id,
                    child_ids=(),
                    mapping_status="unmatched",
                )
            )
    return (
        GoldEvidenceGroupSet(
            provenance_granularity="turn",
            unit_kind="beam_source_message",
            groups=tuple(groups),
        ),
    )


def _map_evidence_turn_ids(
    source_chat_ids: Any,
    raw_id_to_public_turn_ids: dict[int, list[str]],
) -> tuple[list[str], int, int]:
    """把官方 raw id 原子映射到全部公开 turn id，并统计歧义与非法原子。"""

    mapped: list[str] = []
    seen_public_ids: set[str] = set()
    ambiguous_raw_ids: set[int] = set()
    unmatched_count = 0
    for atom in _flatten_evidence_atoms(source_chat_ids):
        public_ids = (
            raw_id_to_public_turn_ids.get(atom, [])
            if isinstance(atom, int) and not isinstance(atom, bool)
            else []
        )
        if not public_ids:
            unmatched_count += 1
            continue
        if len(public_ids) > 1:
            ambiguous_raw_ids.add(atom)
        for public_id in public_ids:
            if public_id not in seen_public_ids:
                mapped.append(public_id)
                seen_public_ids.add(public_id)
    return mapped, len(ambiguous_raw_ids), unmatched_count


def _directory_source_identity(source_path: Path) -> tuple[int, str]:
    """按相对路径排序聚合目录内全部文件，返回总字节数和 SHA-256。"""

    digest = hashlib.sha256()
    size_bytes = 0
    for member in sorted(path for path in source_path.rglob("*") if path.is_file()):
        digest.update(member.relative_to(source_path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with member.open("rb") as source_file:
            while chunk := source_file.read(_SOURCE_HASH_CHUNK_SIZE):
                digest.update(chunk)
                size_bytes += len(chunk)
    return size_bytes, digest.hexdigest()


# 不同 ability 的 gold answer 字段名映射（第一手实测，按尝试优先级排序）。
_ANSWER_FIELD_CANDIDATES: tuple[str, ...] = (
    "ideal_response",       # abstention
    "ideal_answer",         # contradiction_resolution
    "answer",               # event_ordering, information_extraction, knowledge_update,
                            #   multi_session_reasoning, temporal_reasoning
    "expected_compliance",  # instruction_following, preference_following
    "ideal_summary",        # summarization
)


def _resolve_answer_field(q_obj: dict[str, Any], question_id: str) -> str:
    """按优先级查找 question_obj 中的 gold answer 字段。"""

    for field_name in _ANSWER_FIELD_CANDIDATES:
        value = q_obj.get(field_name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise DatasetValidationError(
        f"{question_id}: no valid answer field found (tried: "
        + ", ".join(_ANSWER_FIELD_CANDIDATES)
        + ")"
    )


def _session_from_turns(
    session_turns: list[dict[str, Any]],
    *,
    conversation_id: str,
    session_id: str,
    session_metadata: dict[str, Any] | None = None,
) -> Session:
    """把 BEAM 内层 turn 列表转成 Session。"""

    turns: list[Turn] = []
    session_time: str | None = None
    for turn_index, turn_raw in enumerate(session_turns, start=1):
        if not isinstance(turn_raw, dict):
            raise DatasetValidationError(
                f"{conversation_id}/{session_id}: turn[{turn_index - 1}] must be a dict"
            )
        role = _required_text(turn_raw, "role", f"{conversation_id}/{session_id}/t{turn_index}")
        raw_content = _required_text(
            turn_raw, "content", f"{conversation_id}/{session_id}/t{turn_index}"
        )
        content = strip_tail_marker(raw_content)

        time_anchor = turn_raw.get("time_anchor")
        if isinstance(time_anchor, str) and time_anchor.strip():
            turn_time = time_anchor.strip()
            # 首 session 首 turn 的 time_anchor 作 session_time
            if session_time is None:
                session_time = turn_time
        else:
            turn_time = None

        turns.append(
            Turn(
                turn_id=f"{session_id}:t{turn_index}",
                speaker=role,
                normalized_role=role,
                content=content,
                turn_time=turn_time,
                metadata={
                    "id": turn_raw.get("id"),
                    "index": turn_raw.get("index"),
                    "question_type": turn_raw.get("question_type"),
                },
            )
        )

    return Session(
        session_id=session_id,
        turns=turns,
        session_time=session_time,
        start_time=session_time,
        end_time=None,
        metadata=copy.deepcopy(session_metadata or {}),
        private_metadata={},
    )


def _build_beam_smoke_dataset(
    dataset: Dataset,
    *,
    round_limit: int,
) -> Dataset:
    """按公开顺序裁 BEAM 单 variant smoke 的 conversation 与 round。"""

    if round_limit < 1:
        raise ConfigurationError("BEAM smoke round_limit must be at least 1")
    turn_limit = round_limit * 2

    cropped_conversations: list[Conversation] = []
    total_original_turn_count = 0
    total_retained_turn_count = 0
    for conversation in dataset.conversations:
        original_turn_count = sum(
            len(session.turns) for session in conversation.sessions
        )
        total_original_turn_count += original_turn_count

        remaining = turn_limit
        cropped_sessions: list[Session] = []
        for session in conversation.sessions:
            if remaining <= 0:
                break
            take = min(len(session.turns), remaining)
            if take <= 0:
                continue
            cropped_sessions.append(
                Session(
                    session_id=session.session_id,
                    turns=copy.deepcopy(session.turns[:take]),
                    session_time=session.session_time,
                    start_time=session.start_time,
                    end_time=session.end_time,
                    metadata=copy.deepcopy(session.metadata),
                    private_metadata=copy.deepcopy(session.private_metadata),
                )
            )
            remaining -= take

        retained_turn_count = sum(
            len(session.turns) for session in cropped_sessions
        )
        total_retained_turn_count += retained_turn_count

        conversation_metadata = copy.deepcopy(conversation.metadata)
        conversation_metadata.update(
            {
                "smoke_round_limit": round_limit,
                "smoke_original_turn_count": original_turn_count,
                "smoke_retained_turn_count": retained_turn_count,
            }
        )
        cropped_conversations.append(
            Conversation(
                conversation_id=conversation.conversation_id,
                sessions=cropped_sessions,
                questions=copy.deepcopy(conversation.questions),
                gold_answers=copy.deepcopy(conversation.gold_answers),
                metadata=conversation_metadata,
            )
        )

    metadata = copy.deepcopy(dataset.metadata)
    metadata.update(
        {
            "smoke_round_limit": round_limit,
            "smoke_original_turn_count": total_original_turn_count,
            "smoke_retained_turn_count": total_retained_turn_count,
        }
    )
    return Dataset(
        dataset_name=dataset.dataset_name,
        conversations=cropped_conversations,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# 字段校验 helper
# ---------------------------------------------------------------------------


def _required_text(payload: dict[str, Any], key: str, context: str) -> str:
    """读取必需字符串字段并标准化空白。"""

    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DatasetValidationError(f"{context}: {key} is required")
    return value.strip()
