"""LoCoMo conversation-QA v2 adapter。

本模块只负责把 `data/locomo/locomo10.json` 转换为统一的
`Dataset -> Conversation -> Session -> Turn -> Question` 结构。标准答案和
evidence 只写入 `GoldAnswerInfo`，不能进入 method 可见的 `Question`。
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from memory_benchmark.core import (
    Conversation,
    Dataset,
    GoldAnswerInfo,
    ImageRef,
    Question,
    Session,
    Turn,
)
from memory_benchmark.core.exceptions import ConfigurationError, DatasetValidationError

from .base import BenchmarkAdapter, reached_limit
from .contracts import (
    BenchmarkLoadRequest,
    BenchmarkVariantSpec,
    PreparedBenchmarkRun,
    RunScope,
)


LOCOMO_SOURCE_PATH = "data/locomo/locomo10.json"
LOCOMO_VARIANT_SPECS = (
    BenchmarkVariantSpec(
        name="locomo10",
        source_relative_paths=(Path(LOCOMO_SOURCE_PATH),),
    ),
)
DEFAULT_SMOKE_TURN_LIMIT = 20
ADVERSARIAL_CATEGORY = "5"
SESSION_KEY_PATTERN = re.compile(r"^session_(\d+)$")


class LoCoMoAdapter(BenchmarkAdapter):
    """LoCoMo benchmark 的 conversation-QA v2 数据 adapter。

    输入数据:
        项目根目录下的 `data/locomo/locomo10.json`。

    输出:
        一个 top-level sample 转成一个 `Conversation`，其中 QA 被拆成公开
        `Question` 和 evaluator-only `GoldAnswerInfo`。
    """

    name = "locomo"

    def load_dataset(self, limit: int | None = None) -> Dataset:
        """读取 LoCoMo 原始数据并转换为统一 Dataset。

        输入:
            limit: 最多读取多少个 conversation；None 表示读取全部样本。

        输出:
            Dataset: dataset_name 固定为 `locomo`，metadata 记录来源和 split。
        """

        if limit is not None and limit <= 0:
            raise DatasetValidationError("locomo limit must be a positive integer")

        raw_samples = self.load_json("data", "locomo", "locomo10.json")
        sample_items = _sample_items(raw_samples)

        conversations: list[Conversation] = []
        for raw_index, sample in sample_items:
            conversations.append(self._conversation_from_sample(sample, raw_index))
            if reached_limit(len(conversations), limit):
                break

        return Dataset(
            dataset_name=self.name,
            conversations=conversations,
            metadata={
                "source_path": LOCOMO_SOURCE_PATH,
                "split": "locomo10",
                "source_format": "locomo",
                "total_raw_samples": len(sample_items),
            },
        )

    def _conversation_from_sample(
        self,
        sample: dict[str, Any],
        raw_index: str,
    ) -> Conversation:
        """把一个 LoCoMo sample 转成 Conversation。

        输入:
            sample: 原始 top-level sample。
            raw_index: sample_id 缺失时用于错误定位的原始序号。

        输出:
            Conversation: 包含 sessions、公开 questions 和私有 gold_answers。
        """

        conversation_id = _required_text(sample, "sample_id", f"sample {raw_index}")
        conversation_raw = _required_dict(sample, "conversation", conversation_id)
        sessions = [
            self._session_from_raw(conversation_raw, session_key)
            for session_key in _session_keys(conversation_raw)
        ]
        questions, gold_answers, skipped_adversarial_count = self._questions_from_raw(
            sample.get("qa", []),
            conversation_id,
        )

        return Conversation(
            conversation_id=conversation_id,
            sessions=sessions,
            questions=questions,
            gold_answers=gold_answers,
            metadata={
                "source_path": LOCOMO_SOURCE_PATH,
                "source_sample_id": conversation_id,
                "speaker_a": _optional_text(conversation_raw.get("speaker_a")),
                "speaker_b": _optional_text(conversation_raw.get("speaker_b")),
                "skipped_adversarial_question_count": skipped_adversarial_count,
            },
        )

    def _session_from_raw(
        self,
        conversation_raw: dict[str, Any],
        session_key: str,
    ) -> Session:
        """把一个 `session_<n>` 字段转成 Session。

        输入:
            conversation_raw: 原始 `conversation` 字段。
            session_key: 形如 `session_1` 的 session 字段名。

        输出:
            Session: session_id 沿用原始 key，session_time 来自相邻时间字段。
        """

        turns_raw = conversation_raw.get(session_key)
        if not isinstance(turns_raw, list):
            raise DatasetValidationError(f"{session_key}: session must be a list")

        session_number = _session_number(session_key)
        session_time = _optional_text(conversation_raw.get(f"{session_key}_date_time"))
        turns = [
            _turn_from_raw(turn_raw, session_number, turn_index)
            for turn_index, turn_raw in enumerate(turns_raw, start=1)
        ]

        return Session(
            session_id=session_key,
            session_time=session_time,
            turns=turns,
            metadata={"session_number": session_number},
        )

    def _questions_from_raw(
        self,
        qa_raw: object,
        conversation_id: str,
    ) -> tuple[list[Question], dict[str, GoldAnswerInfo], int]:
        """把 LoCoMo QA 标注拆成公开 Question 和私有 GoldAnswerInfo。

        输入:
            qa_raw: 原始 sample["qa"]，应为 list[dict]。
            conversation_id: 当前 conversation 的 id。

        输出:
            tuple: `(questions, gold_answers, skipped_adversarial_count)`。
        """

        if not isinstance(qa_raw, list):
            raise DatasetValidationError(f"{conversation_id}: qa must be a list")

        questions: list[Question] = []
        gold_answers: dict[str, GoldAnswerInfo] = {}
        skipped_adversarial_count = 0

        for index, qa_item in enumerate(qa_raw):
            if not isinstance(qa_item, dict):
                raise DatasetValidationError(f"{conversation_id}: qa[{index}] must be a dict")

            category = _qa_category(qa_item)
            if category == ADVERSARIAL_CATEGORY:
                skipped_adversarial_count += 1
                continue

            question_id = f"{conversation_id}:q{index}"
            question_text = _required_text(qa_item, "question", question_id)
            if "answer" not in qa_item:
                raise DatasetValidationError(f"{question_id}: answer is required")

            questions.append(
                Question(
                    question_id=question_id,
                    conversation_id=conversation_id,
                    text=question_text,
                    category=category,
                    metadata={"source_index": index},
                )
            )
            gold_answers[question_id] = GoldAnswerInfo(
                question_id=question_id,
                answer=_answer_to_text(qa_item.get("answer")),
                evidence=_evidence_to_list(qa_item.get("evidence")),
                metadata={
                    "category": category,
                    "source_index": index,
                },
            )

        return questions, gold_answers, skipped_adversarial_count


def prepare_locomo_run(
    project_root: Path,
    request: BenchmarkLoadRequest,
) -> PreparedBenchmarkRun:
    """为 LoCoMo concrete variant 构造一次完整或 smoke 运行。"""

    adapter = LoCoMoAdapter(project_root)
    if request.run_scope is RunScope.FULL:
        dataset = adapter.load()
    elif request.run_scope is RunScope.SMOKE:
        source_dataset = adapter.load(limit=request.smoke_conversation_limit)
        dataset = build_locomo_smoke_dataset(
            source_dataset,
            turn_limit=request.smoke_turn_limit,
            conversation_limit=request.smoke_conversation_limit,
        )
    else:  # pragma: no cover - RunScope 只有 smoke / full
        raise ConfigurationError(f"unsupported LoCoMo run scope: {request.run_scope}")

    metadata = copy.deepcopy(dataset.metadata)
    metadata["variant"] = request.variant
    metadata["run_scope"] = request.run_scope.value
    return PreparedBenchmarkRun(
        variant=request.variant,
        run_scope=request.run_scope,
        dataset=Dataset(
            dataset_name=dataset.dataset_name,
            conversations=list(dataset.conversations),
            metadata=metadata,
        ),
        source_relative_paths=LOCOMO_VARIANT_SPECS[0].source_relative_paths,
    )


def build_locomo_smoke_dataset(
    dataset: Dataset,
    turn_limit: int = DEFAULT_SMOKE_TURN_LIMIT,
    conversation_limit: int = 1,
) -> Dataset:
    """从前若干个 LoCoMo conversation 构造低成本且可回答的 smoke 数据。

    输入:
        dataset: 至少包含一个完整 LoCoMo conversation 的统一数据集。
        turn_limit: 按原始 session/turn 顺序最多保留的 turn 数。
        conversation_limit: 选择的 conversation 数。

    输出:
        Dataset: 每个 conversation 都只保留截断历史和 evidence 已覆盖的问题。

    说明:
        私有 evidence 只用于选择有意义的测试夹具。runner 仍会把公开历史/问题与
        evaluator-only gold/evidence 分开，method 不会收到 evidence。
    """

    if turn_limit < 1:
        raise ConfigurationError("LoCoMo smoke turn_limit must be at least 1")
    if not dataset.conversations:
        raise ConfigurationError("LoCoMo smoke requires at least one conversation")
    selected_conversation_limit = min(conversation_limit, len(dataset.conversations))

    smoke_conversations = [
        _build_locomo_smoke_conversation(source, turn_limit)
        for source in dataset.conversations[:selected_conversation_limit]
    ]
    return Dataset(
        dataset_name=dataset.dataset_name,
        conversations=smoke_conversations,
        metadata={
            **copy.deepcopy(dataset.metadata),
            "run_scope": "smoke",
            "smoke_turn_limit": turn_limit,
            "smoke_conversation_limit": conversation_limit,
            "smoke_selected_conversation_count": selected_conversation_limit,
        },
    )


def _build_locomo_smoke_conversation(
    source: Conversation,
    turn_limit: int,
) -> Conversation:
    """裁剪一个 LoCoMo conversation，并选择 evidence 已覆盖的问题。

    输入:
        source: 待裁剪的完整 LoCoMo conversation。
        turn_limit: 按 session/turn 顺序最多保留的 turn 数。

    输出:
        Conversation: 裁剪后的历史、可回答问题及对应私有标准答案。
    """

    retained_sessions: list[Session] = []
    retained_turn_ids: set[str] = set()
    remaining = turn_limit
    for session in source.sessions:
        if remaining <= 0:
            break
        retained_turns = copy.deepcopy(session.turns[:remaining])
        if not retained_turns:
            continue
        retained_turn_ids.update(turn.turn_id for turn in retained_turns)
        retained_sessions.append(
            Session(
                session_id=session.session_id,
                turns=retained_turns,
                session_time=session.session_time,
                start_time=session.start_time,
                end_time=session.end_time,
                metadata=copy.deepcopy(session.metadata),
            )
        )
        remaining -= len(retained_turns)

    selected_questions: list[Question] = []
    selected_gold_answers: dict[str, GoldAnswerInfo] = {}
    for question in source.questions:
        gold = source.gold_answers[question.question_id]
        evidence_ids = set(gold.evidence)
        if evidence_ids and evidence_ids.issubset(retained_turn_ids):
            selected_question = copy.deepcopy(question)
            selected_questions.append(selected_question)
            selected_gold_answers[selected_question.question_id] = copy.deepcopy(gold)
    context_truncated = False
    if not selected_questions:
        if not source.questions:
            raise ConfigurationError(
                f"LoCoMo smoke source conversation has no questions: "
                f"{source.conversation_id}"
            )
        context_truncated = True
        selected_question = copy.deepcopy(source.questions[0])
        selected_questions.append(selected_question)
        selected_gold_answers[selected_question.question_id] = copy.deepcopy(
            source.gold_answers[selected_question.question_id]
        )

    return Conversation(
        conversation_id=source.conversation_id,
        sessions=retained_sessions,
        questions=selected_questions,
        gold_answers=selected_gold_answers,
        metadata={
            **copy.deepcopy(source.metadata),
            "smoke_turn_limit": turn_limit,
            "smoke_context_truncated": context_truncated,
            "smoke_selected_question_id": selected_questions[0].question_id,
            "smoke_selected_question_ids": [
                question.question_id for question in selected_questions
            ],
        },
    )


def _session_keys(conversation_raw: dict[str, object]) -> list[str]:
    """返回按数字顺序排列的真实 session key。

    输入:
        conversation_raw: LoCoMo 原始 `conversation` 字段。

    输出:
        list[str]: 所有 `session_<n>` 字段，不包含日期字段。值类型由后续转换校验。
    """

    keys = [key for key in conversation_raw if SESSION_KEY_PATTERN.fullmatch(key)]
    return sorted(keys, key=_session_number)


def _session_number(session_key: str) -> int:
    """从 `session_<n>` 中解析数字 n。

    输入:
        session_key: 原始 session 字段名。

    输出:
        int: session 的数字序号。
    """

    match = SESSION_KEY_PATTERN.fullmatch(session_key)
    if match is None:
        raise DatasetValidationError(f"{session_key}: invalid session key")
    return int(match.group(1))


def _qa_category(raw: dict[str, object]) -> str | None:
    """读取 QA category 并转成公开字符串。

    输入:
        raw: 单条 LoCoMo QA dict。

    输出:
        str | None: category 缺失或为空时返回 None，否则返回字符串。
    """

    category = raw.get("category")
    if category is None:
        return None
    category_text = str(category).strip()
    return category_text or None


def _sample_items(raw_samples: object) -> list[tuple[str, dict[str, Any]]]:
    """把顶层 JSON 统一成 `(raw_index, sample)` 列表。

    输入:
        raw_samples: `json.load()` 读取出的顶层对象。

    输出:
        list[tuple[str, dict]]: 按原始顺序排列的 sample。
    """

    if isinstance(raw_samples, list):
        items = [(str(index), sample) for index, sample in enumerate(raw_samples)]
    elif isinstance(raw_samples, dict):
        items = [(str(key), raw_samples[key]) for key in sorted(raw_samples)]
    else:
        raise DatasetValidationError("locomo raw data must be a list or dict")

    for raw_index, sample in items:
        if not isinstance(sample, dict):
            raise DatasetValidationError(f"sample {raw_index}: sample must be a dict")
    return items


def _turn_from_raw(raw_turn: object, session_number: int, turn_index: int) -> Turn:
    """把原始 LoCoMo turn 转成统一 Turn。

    输入:
        raw_turn: 原始 turn dict。
        session_number: 所属 session 数字序号，用于生成后备 turn_id。
        turn_index: 当前 session 内从 1 开始的 turn 序号。

    输出:
        Turn: speaker/content 沿用原始字段，图片信息保存在 ImageRef/metadata。
    """

    if not isinstance(raw_turn, dict):
        raise DatasetValidationError(f"D{session_number}:{turn_index}: turn must be a dict")

    turn_id = _optional_text(raw_turn.get("dia_id")) or f"D{session_number}:{turn_index}"
    speaker = _required_text(raw_turn, "speaker", turn_id)
    content = _optional_text(raw_turn.get("text")) or ""
    images = _image_refs_from_turn(raw_turn, turn_id)

    metadata: dict[str, Any] = {}
    query = _optional_text(raw_turn.get("query"))
    if query is not None:
        metadata["image_query"] = query
    if "re-download" in raw_turn:
        metadata["image_redownload_requested"] = bool(raw_turn.get("re-download"))

    return Turn(
        turn_id=turn_id,
        speaker=speaker,
        content=content,
        normalized_role=None,
        images=images,
        metadata=metadata,
    )


def _image_refs_from_turn(raw_turn: dict[str, Any], turn_id: str) -> list[ImageRef]:
    """从 LoCoMo turn 中提取可选图片引用。

    输入:
        raw_turn: 原始 turn dict。
        turn_id: 当前 turn id，用于生成稳定 image_id。

    输出:
        list[ImageRef]: 每个 URL 一个 ImageRef；只有 caption 时也保留一个引用。
    """

    caption = _optional_text(raw_turn.get("blip_caption"))
    query = _optional_text(raw_turn.get("query"))
    image_urls = _image_url_list(raw_turn.get("img_url"))

    if not image_urls and caption is None:
        return []

    if not image_urls:
        return [
            ImageRef(
                image_id=f"{turn_id}:image1",
                caption=caption,
                metadata=_image_metadata(None, query),
            )
        ]

    return [
        ImageRef(
            image_id=f"{turn_id}:image{index}",
            caption=caption,
            metadata=_image_metadata(url, query),
        )
        for index, url in enumerate(image_urls, start=1)
    ]


def _image_url_list(value: object) -> list[str]:
    """把 `img_url` 字段转成 URL 字符串列表。

    输入:
        value: 原始 `img_url`，通常是 list[str]，也兼容单个字符串。

    输出:
        list[str]: 去掉空值后的 URL 列表。
    """

    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _image_metadata(url: str | None, query: str | None) -> dict[str, Any]:
    """构造 ImageRef 的公开 metadata。

    输入:
        url: 原始图片 URL。
        query: 原始图片搜索 query。

    输出:
        dict[str, Any]: 不包含 answer/evidence 的图片公开元信息。
    """

    metadata: dict[str, Any] = {}
    if url is not None:
        metadata["url"] = url
        metadata["source_field"] = "img_url"
    if query is not None:
        metadata["query"] = query
    return metadata


def _required_dict(raw: dict[str, Any], key: str, context: str) -> dict[str, Any]:
    """读取必填 dict 字段。

    输入:
        raw: 原始父 dict。
        key: 必填字段名。
        context: 错误消息中的定位信息。

    输出:
        dict[str, Any]: 对应字段值。
    """

    value = raw.get(key)
    if not isinstance(value, dict):
        raise DatasetValidationError(f"{context}: {key} must be a dict")
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
        value: 原始 answer，可能是 str、int、list 或 dict。

    输出:
        str: 用于 evaluator 的答案文本。
    """

    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).strip()


def _evidence_to_list(value: object) -> list[str]:
    """把原始 evidence 转成字符串列表。

    输入:
        value: 原始 evidence，通常是 list[str]。

    输出:
        list[str]: evaluator-only evidence ids。
    """

    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []
