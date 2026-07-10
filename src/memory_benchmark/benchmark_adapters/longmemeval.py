"""LongMemEval conversation-QA v2 adapter。

本模块只负责把 `data/longmemeval/longmemeval_s_cleaned.json` 和
`data/longmemeval/longmemeval_m_cleaned.json` 转换为统一的
`Dataset -> Conversation -> Session -> Turn -> Question` 结构。
标准答案、evidence session id 和 turn 级 `has_answer` 标签不能进入 method
可见的公开对象。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import ijson

from memory_benchmark.core import (
    Conversation,
    Dataset,
    GoldAnswerInfo,
    Question,
    Session,
    Turn,
)
from memory_benchmark.core.exceptions import ConfigurationError, DatasetValidationError

from .base import BenchmarkAdapter, reached_limit
from .contracts import BenchmarkVariantSpec


LONGMEMEVAL_VARIANT_SPECS = (
    BenchmarkVariantSpec(
        name="s_cleaned",
        source_relative_paths=(Path("data/longmemeval/longmemeval_s_cleaned.json"),),
    ),
    BenchmarkVariantSpec(
        name="m_cleaned",
        source_relative_paths=(Path("data/longmemeval/longmemeval_m_cleaned.json"),),
    ),
)
LONGMEMEVAL_VARIANT_BY_NAME = {spec.name: spec for spec in LONGMEMEVAL_VARIANT_SPECS}
LONGMEMEVAL_SOURCE_PATH = str(
    LONGMEMEVAL_VARIANT_BY_NAME["s_cleaned"].source_relative_paths[0]
)
NORMALIZED_ROLES = {"user", "assistant", "system"}
PRIVATE_MESSAGE_KEYS = {
    "answer",
    "answer_session_ids",
    "answers",
    "evidence",
    "gold",
    "gold_answer",
    "gold_answers",
    "ground_truth",
    "has_answer",
    "judge_label",
    "label",
}
MESSAGE_CORE_KEYS = {"role", "speaker", "content", "text"}

# 官方来源身份锁定值：见
# docs/workstreams/ws02.6-first-smoke-hardening/notes/longmemeval-source-lock.json。
# 仓库 URL / 论文 / license / dataset 来源是外部事实，无法从本地数据文件计算，
# 保持常量；数据集哈希改为 load_dataset() 中对实际读取字节现算，不在此硬编码。
LONGMEMEVAL_OFFICIAL_REPO_URL = "https://github.com/xiaowu0162/LongMemEval"
LONGMEMEVAL_OFFICIAL_PAPER_URL = "https://arxiv.org/abs/2410.10813"
LONGMEMEVAL_OFFICIAL_DATASET_URL = (
    "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned"
)
LONGMEMEVAL_LICENSE = "MIT"
# LongMemEval 论文另外包含 retrieval 与 index expansion 任务，本 adapter 只冻结
# chat-assistant QA 这一个 task（与官方 evaluate_qa.py 答 correctness 对齐）。
LONGMEMEVAL_TASK = "question_answering"


class LongMemEvalAdapter(BenchmarkAdapter):
    """LongMemEval benchmark 的 conversation-QA v2 数据 adapter。

    输入数据:
        项目根目录下的 `data/longmemeval/longmemeval_s_cleaned.json` 或
        `data/longmemeval/longmemeval_m_cleaned.json`。

    输出:
        每条 evaluation instance 转成一个 `Conversation`，包含一个公开
        `Question` 和一个 evaluator-only `GoldAnswerInfo`。
    """

    name = "longmemeval"

    def __init__(self, project_root: str | Path, variant: str = "s_cleaned"):
        """初始化 LongMemEval adapter 并锁定 concrete variant。

        输入:
            project_root: 项目根目录路径。
            variant: concrete variant 名称，必须是 `s_cleaned` 或 `m_cleaned`。

        输出:
            None。初始化后会缓存选中的 variant、split 和源文件路径。
        """

        super().__init__(project_root)
        normalized_variant = variant.strip() if isinstance(variant, str) else ""
        if not normalized_variant:
            raise ConfigurationError("longmemeval variant is required")
        try:
            self._variant_spec = LONGMEMEVAL_VARIANT_BY_NAME[normalized_variant]
        except KeyError as exc:
            allowed = ", ".join(spec.name for spec in LONGMEMEVAL_VARIANT_SPECS)
            raise ConfigurationError(
                f"Unknown longmemeval variant '{variant}'. Allowed: {allowed}"
            ) from exc

        self.variant = self._variant_spec.name
        self.split = self._variant_spec.name
        self.source_relative_path = self._variant_spec.source_relative_paths[0]

    def load_dataset(self, limit: int | None = None) -> Dataset:
        """读取选定的 LongMemEval 原始数据并转换为统一 Dataset。

        输入:
            limit: 最多读取多少个 evaluation instance；None 表示读取全部样本。

        输出:
            Dataset: dataset_name 固定为 `longmemeval`，metadata 记录来源、split
            和 variant。limit 只会截断已转换的 conversation 数，不会破坏单条
            instance 内的 session/turn 结构。
        """

        if limit is not None and limit <= 0:
            raise DatasetValidationError("longmemeval limit must be a positive integer")

        conversations: list[Conversation] = []
        source_fully_scanned = False
        source_path = self.require_path(*self.source_relative_path.parts)
        with source_path.open("rb") as handle:
            for raw_index, instance in enumerate(ijson.items(handle, "item")):
                if not isinstance(instance, dict):
                    raise DatasetValidationError(
                        f"instance {raw_index}: instance must be a dict"
                    )
                conversations.append(self._conversation_from_instance(instance, raw_index))
                if reached_limit(len(conversations), limit):
                    break
            else:
                source_fully_scanned = True

        # source_sha256 对整文件字节现算（对齐 locomo T1：无论是否 limit 都报全文件
        # 哈希，与 source-lock.json 锁定值可比），不硬编码；official_* 身份常量来自
        # source-lock.json，无法从本地数据反推。_m 有 2.7GB，必须分块流式哈希，
        # 禁止 read_bytes() 一次性载入内存。
        source_digest = hashlib.sha256()
        with source_path.open("rb") as source_file:
            while chunk := source_file.read(1024 * 1024):
                source_digest.update(chunk)
        source_sha256 = source_digest.hexdigest()

        return Dataset(
            dataset_name=self.name,
            conversations=conversations,
            metadata={
                "source_path": str(self.source_relative_path),
                "split": self.split,
                "variant": self.variant,
                "source_format": "longmemeval",
                "task": LONGMEMEVAL_TASK,
                "official_repo_url": LONGMEMEVAL_OFFICIAL_REPO_URL,
                "official_paper_url": LONGMEMEVAL_OFFICIAL_PAPER_URL,
                "official_dataset_url": LONGMEMEVAL_OFFICIAL_DATASET_URL,
                "license": LONGMEMEVAL_LICENSE,
                "source_sha256": source_sha256,
                "total_raw_instances": len(conversations),
                "source_fully_scanned": source_fully_scanned,
                "official_question_count": len(conversations),
                # abstention 题数：question_id 带 `_abs` 后缀者（私有边界不受影响，
                # 此处只计公开 question 的来源分布标记，answer/answer_session_ids
                # 仍只在 gold_answers 内）。
                "abstention_question_count": sum(
                    1
                    for conversation in conversations
                    if "_abs" in conversation.metadata.get("source_question_id", "")
                ),
                "skipped_blank_turn_count": sum(
                    int(conversation.metadata.get("skipped_blank_turn_count", 0))
                    for conversation in conversations
                ),
                "deduplicated_session_id_count": sum(
                    int(conversation.metadata.get("deduplicated_session_id_count", 0))
                    for conversation in conversations
                ),
            },
        )

    def _conversation_from_instance(
        self,
        instance: dict[str, Any],
        raw_index: int | str,
    ) -> Conversation:
        """把一条 LongMemEval evaluation instance 转成 Conversation。

        输入:
            instance: 原始 evaluation instance。
            raw_index: instance 缺字段时报错使用的原始序号。

        输出:
            Conversation: 包含 history sessions、一个公开问题和私有标准答案。
        """

        context = f"instance {raw_index}"
        question_id = _required_text(instance, "question_id", context)
        question_text = _required_text(instance, "question", question_id)
        question_type = _optional_text(instance.get("question_type"))
        question_date = _optional_text(instance.get("question_date"))

        (
            sessions,
            skipped_blank_turn_count,
            deduplicated_session_id_count,
            evidence_turn_ids,
            evidence_turn_corpus_ids,
        ) = self._sessions_from_instance(instance, question_id)
        answer_session_ids = _string_list(instance.get("answer_session_ids"))
        evidence_session_public_ids = _evidence_session_public_ids(
            sessions,
            answer_session_ids,
        )
        question = Question(
            question_id=question_id,
            conversation_id=question_id,
            text=question_text,
            question_time=question_date,
            category=question_type,
            metadata={"source_index": raw_index},
        )
        gold = GoldAnswerInfo(
            question_id=question_id,
            answer=_answer_to_text(instance.get("answer")),
            evidence=answer_session_ids,
            metadata={
                "question_type": question_type,
                "question_date": question_date,
                "source_index": raw_index,
                "evidence_turn_ids": evidence_turn_ids,
                "evidence_turn_corpus_ids": evidence_turn_corpus_ids,
                "evidence_session_public_ids": evidence_session_public_ids,
            },
        )

        return Conversation(
            conversation_id=question_id,
            sessions=sessions,
            questions=[question],
            gold_answers={question_id: gold},
            metadata={
                "source_path": str(self.source_relative_path),
                "split": self.split,
                "variant": self.variant,
                "source_question_id": question_id,
                "skipped_blank_turn_count": skipped_blank_turn_count,
                "deduplicated_session_id_count": deduplicated_session_id_count,
            },
        )

    def _sessions_from_instance(
        self,
        instance: dict[str, Any],
        question_id: str,
    ) -> tuple[list[Session], int, int, list[str], list[str]]:
        """把 LongMemEval 三个 haystack 并行列表转成 Session 列表。

        输入:
            instance: 原始 evaluation instance。
            question_id: 当前问题 id，用于错误定位和稳定 fallback。

        输出:
            tuple: sessions、空 turn 数、重复 session id 数、公开 evidence turn ids、
            官方 evidence corpus ids。
        """

        session_ids = _required_list(instance, "haystack_session_ids", question_id)
        session_dates = _required_list(instance, "haystack_dates", question_id)
        sessions_raw = _required_list(instance, "haystack_sessions", question_id)
        _validate_parallel_haystack_lengths(
            question_id,
            session_ids,
            session_dates,
            sessions_raw,
        )

        sessions: list[Session] = []
        skipped_blank_turn_count = 0
        deduplicated_session_id_count = 0
        evidence_turn_ids: list[str] = []
        evidence_turn_corpus_ids: list[str] = []
        seen_session_ids: dict[str, int] = {}
        for session_index, (session_id_raw, session_date_raw, turns_raw) in enumerate(
            zip(session_ids, session_dates, sessions_raw),
        ):
            original_session_id = (
                _optional_text(session_id_raw) or f"{question_id}:session_{session_index}"
            )
            occurrence = seen_session_ids.get(original_session_id, 0) + 1
            seen_session_ids[original_session_id] = occurrence
            session_id = _unique_session_id(original_session_id, occurrence)
            if occurrence > 1:
                deduplicated_session_id_count += 1
            session_time = _optional_text(session_date_raw)
            session, skipped_count, session_evidence_ids, session_corpus_ids = (
                self._session_from_raw(
                    session_id,
                    session_time,
                    turns_raw,
                    original_session_id=original_session_id,
                    session_index=session_index,
                    occurrence=occurrence,
                )
            )
            skipped_blank_turn_count += skipped_count
            sessions.append(session)
            evidence_turn_ids.extend(session_evidence_ids)
            evidence_turn_corpus_ids.extend(session_corpus_ids)
        return (
            sessions,
            skipped_blank_turn_count,
            deduplicated_session_id_count,
            evidence_turn_ids,
            evidence_turn_corpus_ids,
        )

    def _session_from_raw(
        self,
        session_id: str,
        session_time: str | None,
        turns_raw: object,
        *,
        original_session_id: str,
        session_index: int,
        occurrence: int,
    ) -> tuple[Session, int, list[str], list[str]]:
        """把一个 haystack session 转成统一 Session。

        输入:
            session_id: 原始 session id，缺失时由调用方生成 fallback。
            session_time: 原始 haystack date。
            turns_raw: 原始 turn list。
            original_session_id: 数据集中原始 session id，用于 debug。
            session_index: 当前 instance 内的 session 序号。
            occurrence: 同一个原始 session id 在当前 instance 中第几次出现。

        输出:
            tuple: Session、空 turn 数、公开 evidence turn ids、官方 corpus ids。
        """

        if not isinstance(turns_raw, list):
            raise DatasetValidationError(f"{session_id}: session must be a list")

        turns: list[Turn] = []
        skipped_blank_turn_count = 0
        evidence_turn_ids: list[str] = []
        evidence_turn_corpus_ids: list[str] = []
        for turn_index, turn_raw in enumerate(turns_raw):
            turn_id = f"{session_id}:t{turn_index}"
            if not isinstance(turn_raw, dict):
                raise DatasetValidationError(f"{turn_id}: turn must be a dict")
            if turn_raw.get("has_answer") is True:
                evidence_turn_ids.append(turn_id)
                evidence_turn_corpus_ids.append(
                    f"{original_session_id}_{turn_index + 1}"
                )
            if _has_blank_message_content(turn_raw):
                skipped_blank_turn_count += 1
                continue
            turns.append(_turn_from_raw(turn_raw, session_id, turn_index))

        if not turns:
            raise DatasetValidationError(f"{session_id}: session has no non-empty turns")

        return (
            Session(
                session_id=session_id,
                session_time=session_time,
                turns=turns,
                metadata={
                    "source_format": "longmemeval_haystack_session",
                    "source_index": session_index,
                    "original_session_id": original_session_id,
                    "session_id_occurrence": occurrence,
                    "skipped_blank_turn_count": skipped_blank_turn_count,
                },
            ),
            skipped_blank_turn_count,
            evidence_turn_ids,
            evidence_turn_corpus_ids,
        )


def _validate_parallel_haystack_lengths(
    question_id: str,
    session_ids: list[Any],
    session_dates: list[Any],
    sessions_raw: list[Any],
) -> None:
    """校验 LongMemEval 三个 haystack list 必须按 index 对齐。

    输入:
        question_id: 当前 question id，用于错误定位。
        session_ids: `haystack_session_ids`。
        session_dates: `haystack_dates`。
        sessions_raw: `haystack_sessions`。

    输出:
        None。长度不一致时抛 DatasetValidationError。
    """

    lengths = {
        "haystack_session_ids": len(session_ids),
        "haystack_dates": len(session_dates),
        "haystack_sessions": len(sessions_raw),
    }
    if len(set(lengths.values())) != 1:
        raise DatasetValidationError(
            f"{question_id}: haystack parallel list length mismatch: {lengths}"
        )


def _unique_session_id(original_session_id: str, occurrence: int) -> str:
    """根据原始 session id 和出现次数生成内部唯一 session_id。

    输入:
        original_session_id: LongMemEval 原始 `haystack_session_ids` 值。
        occurrence: 该原始 id 在同一个 instance 中第几次出现，从 1 开始。

    输出:
        str: 第一次出现沿用原始 id；重复出现时追加稳定 suffix。
    """

    if occurrence <= 1:
        return original_session_id
    return f"{original_session_id}#occurrence_{occurrence}"


def _evidence_session_public_ids(
    sessions: list[Session],
    answer_session_ids: list[str],
) -> list[str]:
    """把官方 answer_session_ids 映射到去重后的公开 session id 空间。"""

    public_ids_by_original: dict[str, list[str]] = {}
    for session in sessions:
        original_id = str(session.metadata.get("original_session_id", ""))
        public_ids_by_original.setdefault(original_id, []).append(session.session_id)

    public_ids: list[str] = []
    seen: set[str] = set()
    for original_id in answer_session_ids:
        for public_id in public_ids_by_original.get(original_id, []):
            if public_id not in seen:
                public_ids.append(public_id)
                seen.add(public_id)
    return public_ids


def _turn_from_raw(raw_turn: object, session_id: str, turn_index: int) -> Turn:
    """把原始 LongMemEval message 转成统一 Turn。

    输入:
        raw_turn: 原始 message dict。
        session_id: 所属 session id，用于生成 turn_id。
        turn_index: 当前 session 内从 0 开始的 turn 序号。

    输出:
        Turn: speaker/content 沿用原始字段，private evidence 标签被丢弃。
    """

    turn_id = f"{session_id}:t{turn_index}"
    if not isinstance(raw_turn, dict):
        raise DatasetValidationError(f"{turn_id}: turn must be a dict")

    role = _optional_text(raw_turn.get("role"))
    speaker = role or _required_text(raw_turn, "speaker", turn_id)
    content = _message_content(raw_turn, turn_id)

    return Turn(
        turn_id=turn_id,
        speaker=speaker,
        content=content,
        normalized_role=_normalized_role(role),
        metadata=_public_message_metadata(raw_turn),
    )


def _message_content(raw_turn: dict[str, Any], turn_id: str) -> str:
    """从 message 的 `content` 或 `text` 字段读取非空内容。

    输入:
        raw_turn: 原始 message dict。
        turn_id: 当前 turn id，用于错误定位。

    输出:
        str: 去掉首尾空白后的 message 内容。
    """

    content = _message_content_value(raw_turn)
    if content is None:
        raise DatasetValidationError(f"{turn_id}: content is required")
    return content


def _message_content_value(raw_turn: dict[str, Any]) -> str | None:
    """读取可选 message 内容，供空 message 跳过逻辑复用。

    输入:
        raw_turn: 原始 message dict。

    输出:
        str | None: content/text 均为空时返回 None。
    """

    content = _optional_text(raw_turn.get("content"))
    if content is None:
        content = _optional_text(raw_turn.get("text"))
    return content


def _has_blank_message_content(raw_turn: dict[str, Any]) -> bool:
    """判断 message 是否属于字段存在但内容为空的官方脏数据。

    输入:
        raw_turn: 原始 message dict。

    输出:
        bool: `content` 或 `text` 字段存在但清洗后为空时返回 True。
    """

    for key in ("content", "text"):
        if key in raw_turn and _optional_text(raw_turn.get(key)) is None:
            return True
    return False


def _normalized_role(role: str | None) -> str | None:
    """把原始 role 归一化为可选标准角色。

    输入:
        role: 原始 `role` 字段。

    输出:
        str | None: user/assistant/system 之一，其他值返回 None。
    """

    if role is None:
        return None
    normalized = role.lower()
    return normalized if normalized in NORMALIZED_ROLES else None


def _public_message_metadata(raw_turn: dict[str, Any]) -> dict[str, Any]:
    """保留 message 上非核心且非私有的公开 metadata。

    输入:
        raw_turn: 原始 message dict。

    输出:
        dict[str, Any]: 不包含 `has_answer`、answer 或 evidence 等评测标签。
    """

    metadata: dict[str, Any] = {}
    for key, value in raw_turn.items():
        normalized_key = str(key).lower()
        if normalized_key in MESSAGE_CORE_KEYS or normalized_key in PRIVATE_MESSAGE_KEYS:
            continue
        metadata[str(key)] = value
    return metadata


def _required_list(raw: dict[str, Any], key: str, context: str) -> list[Any]:
    """读取必填 list 字段。

    输入:
        raw: 原始父 dict。
        key: 必填字段名。
        context: 错误消息中的定位信息。

    输出:
        list[Any]: 对应字段值。
    """

    value = raw.get(key)
    if not isinstance(value, list):
        raise DatasetValidationError(f"{context}: {key} must be a list")
    return value


def _required_text(raw: dict[str, Any], key: str, context: str) -> str:
    """读取必填文本字段。

    输入:
        raw: 原始父 dict。
        key: 必填字段名。
        context: 错误消息中的定位信息。

    输出:
        str: 去掉首尾空白后的文本。
    """

    value = _optional_text(raw.get(key))
    if value is None:
        raise DatasetValidationError(f"{context}: {key} is required")
    return value


def _optional_text(value: object) -> str | None:
    """把可选字段转成非空字符串。

    输入:
        value: 任意原始值。

    输出:
        str | None: None 或空白字符串返回 None，其余值返回字符串。
    """

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _answer_to_text(value: object) -> str:
    """把标准答案安全转成字符串。

    输入:
        value: 原始 answer，通常是 str，也兼容 list/dict。

    输出:
        str: evaluator 使用的答案文本。
    """

    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).strip()


def _string_list(value: object) -> list[str]:
    """把 evidence session id 字段转成字符串列表。

    输入:
        value: 原始 `answer_session_ids`，通常是 list[str]。

    输出:
        list[str]: evaluator-only evidence session ids。
    """

    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []
