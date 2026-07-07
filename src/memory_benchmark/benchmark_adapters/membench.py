"""MemBench conversation-QA v2 adapter。

本模块只负责把 `data/membench/Membenchdata/data2test` 下的 MemBench
trajectory 转换为统一 `Dataset -> Conversation -> Session -> Turn -> Question`
结构。`ground_truth`、`answer` 和 `target_step_id` 只进入 `GoldAnswerInfo`，
不能出现在 method 可见的公开 payload 中。
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from memory_benchmark.core import (
    AnswerPromptResult,
    AnswerResult,
    Conversation,
    Dataset,
    GoldAnswerInfo,
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
    BenchmarkVariantSpec,
    PreparedBenchmarkRun,
    RunScope,
)


MEMBENCH_DATA2TEST_ROOT = Path("data/membench/Membenchdata/data2test")
MEMBENCH_0_10K_SOURCE_PATHS = (
    MEMBENCH_DATA2TEST_ROOT / "0-10k/FirstAgentDataHighLevel_multiple_0.json",
    MEMBENCH_DATA2TEST_ROOT / "0-10k/FirstAgentDataLowLevel_multiple_0.json",
    MEMBENCH_DATA2TEST_ROOT / "0-10k/ThirdAgentDataHighLevel_multiple_0.json",
    MEMBENCH_DATA2TEST_ROOT / "0-10k/ThirdAgentDataLowLevel_multiple_0.json",
)
MEMBENCH_100K_SOURCE_PATHS = (
    MEMBENCH_DATA2TEST_ROOT / "100k/FirstAgentDataHighLevel_multiple_100.json",
    MEMBENCH_DATA2TEST_ROOT / "100k/FirstAgentDataLowLevel_multiple_100.json",
    MEMBENCH_DATA2TEST_ROOT / "100k/ThirdAgentDataHighLevel_multiple_100.json",
    MEMBENCH_DATA2TEST_ROOT / "100k/ThirdAgentDataLowLevel_multiple_100.json",
)
MEMBENCH_VARIANT_SPECS = (
    BenchmarkVariantSpec(
        name="0_10k",
        source_relative_paths=MEMBENCH_0_10K_SOURCE_PATHS,
    ),
    BenchmarkVariantSpec(
        name="100k",
        source_relative_paths=MEMBENCH_100K_SOURCE_PATHS,
    ),
)
MEMBENCH_VARIANT_BY_NAME = {spec.name: spec for spec in MEMBENCH_VARIANT_SPECS}
MEMBENCH_INSTRUCTION_FIRST_PROFILE = "membench_instruction_first_v1"
MEMBENCH_INSTRUCTION_FIRST = """Please answer the following question based on past memories of your'conversation with the user.
Past memory: {memory}
Question: (current time is {time}) {question}
Choices:
A. {choice_A}
B. {choice_B}
C. {choice_C}
D. {choice_D}
Please output the correct option for the question, only one corresponding letter, without any other messages.
Example: D
"""

_MEMBENCH_CHOICE_PATTERN = re.compile(
    r"(?<![A-Za-z])([ABCD])(?![A-Za-z])",
    re.IGNORECASE,
)


class MemBenchAdapter(BenchmarkAdapter):
    """MemBench benchmark 的 trajectory-QA 数据 adapter。

    输入数据:
        项目根目录下的 `data/membench/Membenchdata/data2test/<variant>` 主文件。

    输出:
        每条 MemBench trajectory 转成一个 `Conversation`，包含单个 session、
        一个公开 multiple-choice question 和一个 evaluator-only gold label。
    """

    name = "membench"

    def __init__(
        self,
        project_root: str | Path,
        variant: str = "0_10k",
        source_relative_paths: tuple[Path, ...] | None = None,
    ):
        """初始化 MemBench adapter 并锁定 concrete variant。

        输入:
            project_root: 项目根目录路径。
            variant: concrete variant 名称，必须是 `0_10k` 或 `100k`。
            source_relative_paths: 测试专用覆盖；为空时使用 variant 注册源文件。

        输出:
            None。初始化后会缓存 variant 和源文件路径。
        """

        super().__init__(project_root)
        normalized_variant = variant.strip() if isinstance(variant, str) else ""
        if not normalized_variant:
            raise ConfigurationError("membench variant is required")
        if source_relative_paths is None:
            try:
                variant_spec = MEMBENCH_VARIANT_BY_NAME[normalized_variant]
            except KeyError as exc:
                allowed = ", ".join(spec.name for spec in MEMBENCH_VARIANT_SPECS)
                raise ConfigurationError(
                    f"Unknown membench variant '{variant}'. Allowed: {allowed}"
                ) from exc
            selected_source_paths = variant_spec.source_relative_paths
        else:
            selected_source_paths = tuple(Path(path) for path in source_relative_paths)
            if not selected_source_paths:
                raise ConfigurationError("membench source_relative_paths cannot be empty")

        self.variant = normalized_variant
        self.source_relative_paths = selected_source_paths

    def load_dataset(self, limit: int | None = None) -> Dataset:
        """读取选定 MemBench 文件并转换为统一 Dataset。

        输入:
            limit: 最多读取多少条 trajectory；None 表示读取 variant 全量主文件。

        输出:
            Dataset: dataset_name 固定为 `membench`，metadata 记录 variant、来源路径
            和已转换 trajectory 数。limit 只截断 trajectory 数，不裁剪 message_list。
        """

        if limit is not None and limit <= 0:
            raise DatasetValidationError("membench limit must be a positive integer")

        conversations: list[Conversation] = []
        total_raw_trajectories = 0
        source_fully_scanned = True
        for source_relative_path in self.source_relative_paths:
            raw_data = self.load_json(*source_relative_path.parts)
            source_context = source_relative_path.as_posix()
            source_profile = _source_profile_from_path(source_relative_path)
            seen_conversation_ids_in_file: set[str] = set()
            for question_type, scenario, trajectory in _iter_trajectories(
                raw_data,
                source_context,
            ):
                total_raw_trajectories += 1
                tid = _required_text(trajectory, "tid", source_context)
                conversation_id = _conversation_id(
                    source_profile=source_profile,
                    question_type=question_type,
                    scenario=scenario,
                    tid=tid,
                )
                if conversation_id in seen_conversation_ids_in_file:
                    raise DatasetValidationError(
                        f"{source_context}: duplicate conversation_id within source file: "
                        f"{conversation_id}"
                    )
                seen_conversation_ids_in_file.add(conversation_id)
                conversations.append(
                    _conversation_from_trajectory(
                        trajectory,
                        question_type=question_type,
                        scenario=scenario,
                        source_profile=source_profile,
                        source_relative_path=source_relative_path,
                    )
                )
                if reached_limit(len(conversations), limit):
                    source_fully_scanned = False
                    return self._dataset(
                        conversations,
                        total_raw_trajectories=total_raw_trajectories,
                        source_fully_scanned=source_fully_scanned,
                    )

        return self._dataset(
            conversations,
            total_raw_trajectories=total_raw_trajectories,
            source_fully_scanned=source_fully_scanned,
        )

    def _dataset(
        self,
        conversations: list[Conversation],
        *,
        total_raw_trajectories: int,
        source_fully_scanned: bool,
    ) -> Dataset:
        """构造带统一 metadata 的 MemBench Dataset。"""

        return Dataset(
            dataset_name=self.name,
            conversations=conversations,
            metadata={
                "source_paths": [path.as_posix() for path in self.source_relative_paths],
                "variant": self.variant,
                "source_format": "membench_data2test",
                "total_raw_trajectories": total_raw_trajectories,
                "source_fully_scanned": source_fully_scanned,
            },
        )


def prepare_membench_run(
    project_root: Path,
    request: BenchmarkLoadRequest,
) -> PreparedBenchmarkRun:
    """为 MemBench concrete variant 构造 full 或 per-source smoke 运行。"""

    variant_spec = MEMBENCH_VARIANT_BY_NAME.get(request.variant)
    if variant_spec is None:
        allowed = ", ".join(spec.name for spec in MEMBENCH_VARIANT_SPECS)
        raise ConfigurationError(
            f"Unknown membench variant '{request.variant}'. Allowed: {allowed}"
        )

    if request.run_scope is RunScope.FULL:
        dataset = MemBenchAdapter(project_root, variant=request.variant).load()
    elif request.run_scope is RunScope.SMOKE:
        dataset = _build_membench_smoke_dataset(
            project_root,
            variant=request.variant,
            source_relative_paths=variant_spec.source_relative_paths,
            per_source_limit=request.smoke_conversation_limit,
        )
    else:  # pragma: no cover - RunScope 只有 smoke / full
        raise ConfigurationError(f"unsupported MemBench run scope: {request.run_scope}")

    metadata = dict(dataset.metadata)
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
        source_relative_paths=variant_spec.source_relative_paths,
    )


def build_membench_unified_answer_prompt(
    question: Question,
    retrieval_result: RetrievalResult,
) -> AnswerPromptResult:
    """按 MemBench 官方 INSTRUCTION_FIRST 构造 framework reader prompt。"""

    choices = question.options or {}
    missing_choices = [
        choice for choice in ("A", "B", "C", "D") if choice not in choices
    ]
    if missing_choices:
        raise DatasetValidationError(
            f"MemBench question choices missing {missing_choices}: {question.question_id}"
        )

    answer_prompt = MEMBENCH_INSTRUCTION_FIRST.format(
        memory=retrieval_result.formatted_memory,
        question=question.text,
        time=question.question_time or "",
        choice_A=choices["A"],
        choice_B=choices["B"],
        choice_C=choices["C"],
        choice_D=choices["D"],
    )
    metadata = dict(retrieval_result.metadata)
    metadata.update(
        {
            "answer_prompt_profile": MEMBENCH_INSTRUCTION_FIRST_PROFILE,
            "prompt_track": "unified",
            "answer_context": retrieval_result.formatted_memory,
            "official_source": (
                "third_party/benchmarks/Membench-main/benchmark/"
                "MembenchAgent.py:21-31,89-92"
            ),
        }
    )
    return AnswerPromptResult(
        question_id=question.question_id,
        conversation_id=question.conversation_id,
        answer_prompt=answer_prompt,
        prompt_messages=[PromptMessage(role="user", content=answer_prompt)],
        metadata=metadata,
    )


def normalize_membench_choice_prediction(prediction: AnswerResult) -> AnswerResult:
    """把 MemBench reader 原始输出规整为 A/B/C/D；无法解析时记 invalid_choice。"""

    raw_answer = prediction.answer
    parsed_choice = parse_membench_choice(raw_answer)
    metadata = dict(prediction.metadata)
    metadata["raw_answer"] = raw_answer
    metadata["choice_parse_status"] = (
        "parsed" if parsed_choice != "invalid_choice" else "invalid_choice"
    )
    return AnswerResult(
        question_id=prediction.question_id,
        conversation_id=prediction.conversation_id,
        answer=parsed_choice,
        metadata=metadata,
    )


def parse_membench_choice(raw_answer: str) -> str:
    """从 reader 输出中提取 A/B/C/D，失败返回 `invalid_choice`。"""

    text = str(raw_answer).strip()
    if not text:
        return "invalid_choice"
    json_choice = _choice_from_json_text(text)
    if json_choice is not None:
        return json_choice
    match = _MEMBENCH_CHOICE_PATTERN.search(text)
    if match is None:
        return "invalid_choice"
    return match.group(1).upper()


def _choice_from_json_text(text: str) -> str | None:
    """尝试从官方 JSON schema 形态的输出中读取 choice。"""

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    choice = payload.get("choice")
    if not isinstance(choice, str):
        return None
    normalized = choice.strip().upper()
    if normalized in {"A", "B", "C", "D"}:
        return normalized
    return "invalid_choice"


def _build_membench_smoke_dataset(
    project_root: Path,
    *,
    variant: str,
    source_relative_paths: tuple[Path, ...],
    per_source_limit: int,
) -> Dataset:
    """按每个 MemBench 主文件前 N 条 trajectory 构造 smoke Dataset。"""

    if per_source_limit < 1:
        raise ConfigurationError("MemBench smoke per-source limit must be positive")

    conversations: list[Conversation] = []
    source_counts: dict[str, int] = {}
    for source_relative_path in source_relative_paths:
        source_dataset = MemBenchAdapter(
            project_root,
            variant=variant,
            source_relative_paths=(source_relative_path,),
        ).load(limit=per_source_limit)
        conversations.extend(source_dataset.conversations)
        source_counts[source_relative_path.as_posix()] = len(source_dataset.conversations)

    return Dataset(
        dataset_name=MemBenchAdapter.name,
        conversations=conversations,
        metadata={
            "source_paths": [path.as_posix() for path in source_relative_paths],
            "variant": variant,
            "source_format": "membench_data2test",
            "run_scope": RunScope.SMOKE.value,
            "smoke_per_source_conversation_limit": per_source_limit,
            "smoke_source_counts": source_counts,
            "smoke_selected_conversation_count": len(conversations),
        },
    )


def _iter_trajectories(
    raw_data: object,
    source_context: str,
) -> list[tuple[str, str, dict[str, Any]]]:
    """按 question_type -> scenario -> trajectory 顺序展开 MemBench JSON。"""

    if not isinstance(raw_data, dict):
        raise DatasetValidationError(f"{source_context}: top-level JSON must be a dict")

    trajectories: list[tuple[str, str, dict[str, Any]]] = []
    for question_type, scenarios in raw_data.items():
        if not isinstance(scenarios, dict):
            raise DatasetValidationError(
                f"{source_context}/{question_type}: scenarios must be a dict"
            )
        for scenario, trajectory_list in scenarios.items():
            if not isinstance(trajectory_list, list):
                raise DatasetValidationError(
                    f"{source_context}/{question_type}/{scenario}: trajectories must be a list"
                )
            for index, trajectory in enumerate(trajectory_list):
                if not isinstance(trajectory, dict):
                    raise DatasetValidationError(
                        f"{source_context}/{question_type}/{scenario}[{index}]: "
                        "trajectory must be a dict"
                    )
                trajectories.append((str(question_type), str(scenario), trajectory))
    return trajectories


def _conversation_from_trajectory(
    trajectory: dict[str, Any],
    *,
    question_type: str,
    scenario: str,
    source_profile: dict[str, str],
    source_relative_path: Path,
) -> Conversation:
    """把一条 MemBench trajectory 转成 Conversation。"""

    tid = _required_text(trajectory, "tid", source_relative_path.as_posix())
    conversation_id = _conversation_id(
        source_profile=source_profile,
        question_type=question_type,
        scenario=scenario,
        tid=tid,
    )
    messages = _required_list(trajectory, "message_list", conversation_id)
    qa = _required_dict(trajectory, "QA", conversation_id)
    turns = [
        _turn_from_step(step, step_index=index, conversation_id=conversation_id)
        for index, step in enumerate(messages)
    ]
    if not turns:
        raise DatasetValidationError(f"{conversation_id}: message_list is empty")

    question, gold = _question_and_gold_from_qa(
        qa,
        conversation_id=conversation_id,
        question_type=question_type,
        scenario=scenario,
        tid=tid,
    )

    return Conversation(
        conversation_id=conversation_id,
        sessions=[
            Session(
                session_id="s1",
                session_time=None,
                turns=turns,
                metadata={
                    "source_format": "membench_trajectory",
                    "tid": tid,
                    "scenario": scenario,
                    **source_profile,
                },
            )
        ],
        questions=[question],
        gold_answers={question.question_id: gold},
        metadata={
            "source_path": source_relative_path.as_posix(),
            "source_format": "membench",
            "variant_source_stream": source_profile["source_stream"],
            "level": source_profile["level"],
            "question_type": question_type,
            "scenario": scenario,
            "source_tid": tid,
        },
    )


def _turn_from_step(
    step: object,
    *,
    step_index: int,
    conversation_id: str,
) -> Turn:
    """把 MemBench message_list 中的一个 step 转成公开 Turn。"""

    turn_id = str(step_index + 1)
    metadata: dict[str, Any] = {
        "source_step_index": step_index,
        "source_step_number": step_index + 1,
    }
    if isinstance(step, dict):
        user_text = _required_text(step, "user", f"{conversation_id}:step{turn_id}")
        agent_text = _required_text(step, "agent", f"{conversation_id}:step{turn_id}")
        metadata.update({"ps_user": user_text, "ps_agent": agent_text})
        content = f"'user': {user_text}; 'agent': {agent_text}"
    elif isinstance(step, str):
        content = step
    else:
        raise DatasetValidationError(
            f"{conversation_id}: message_list[{step_index}] must be a dict or string"
        )

    if not content.strip():
        raise DatasetValidationError(f"{conversation_id}: step {turn_id} content is empty")

    return Turn(
        turn_id=turn_id,
        speaker="user",
        normalized_role="user",
        content=content,
        turn_time=None,
        metadata=metadata,
    )


def _question_and_gold_from_qa(
    qa: dict[str, Any],
    *,
    conversation_id: str,
    question_type: str,
    scenario: str,
    tid: str,
) -> tuple[Question, GoldAnswerInfo]:
    """把 MemBench QA 拆成公开 Question 和私有 GoldAnswerInfo。"""

    question_text = _required_text(qa, "question", conversation_id)
    answer_text = _required_text(qa, "answer", conversation_id)
    ground_truth = _required_text(qa, "ground_truth", conversation_id).upper()
    if ground_truth not in {"A", "B", "C", "D"}:
        raise DatasetValidationError(
            f"{conversation_id}: ground_truth must be one of A/B/C/D"
        )
    question_time = _optional_text(qa.get("time"))
    choices = _choices_dict(qa.get("choices"), conversation_id)
    target_step_ids = _target_step_ids(qa.get("target_step_id"), conversation_id)
    qid = _optional_text(qa.get("qid")) or "0"
    question_id = f"{conversation_id}:q{qid}"

    question = Question(
        question_id=question_id,
        conversation_id=conversation_id,
        text=question_text,
        question_time=question_time,
        category=question_type,
        options=choices,
        metadata={
            "choices": choices,
            "question_type": question_type,
            "scenario": scenario,
            "source_qid": qid,
            "source_tid": tid,
        },
    )
    gold = GoldAnswerInfo(
        question_id=question_id,
        answer=answer_text,
        evidence=[str(step_id) for step_id in target_step_ids],
        metadata={
            "ground_truth": ground_truth,
            "answer": answer_text,
            "target_step_id": target_step_ids,
            "question_type": question_type,
            "scenario": scenario,
            "source_qid": qid,
            "source_tid": tid,
        },
    )
    return question, gold


def _source_profile_from_path(path: Path) -> dict[str, str]:
    """从 MemBench 文件名中解析 first/third 与 high/low profile。"""

    name = path.name
    if name.startswith("FirstAgent"):
        source_stream = "first"
    elif name.startswith("ThirdAgent"):
        source_stream = "third"
    else:
        raise DatasetValidationError(f"{path.as_posix()}: unknown MemBench source stream")

    if "HighLevel" in name:
        level = "high"
    elif "LowLevel" in name:
        level = "low"
    else:
        raise DatasetValidationError(f"{path.as_posix()}: unknown MemBench level")
    return {"source_stream": source_stream, "level": level}


def _conversation_id(
    *,
    source_profile: dict[str, str],
    question_type: str,
    scenario: str,
    tid: str,
) -> str:
    """生成 MemBench trajectory conversation_id。"""

    return (
        f"{source_profile['source_stream']}-"
        f"{source_profile['level']}-"
        f"{question_type}-"
        f"{_safe_id_part(scenario)}-"
        f"{tid}"
    )


def _safe_id_part(value: str) -> str:
    """把 MemBench scenario 文本转换为稳定 conversation_id 片段。"""

    return str(value).strip().replace(" ", "_")


def _required_text(raw: dict[str, Any], key: str, context: str) -> str:
    """读取必填非空文本字段。"""

    value = raw.get(key)
    text = str(value).strip() if value is not None else ""
    if not text:
        raise DatasetValidationError(f"{context}: {key} is required")
    return text


def _optional_text(value: object) -> str | None:
    """把可选值转换为去空白字符串。"""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_dict(raw: dict[str, Any], key: str, context: str) -> dict[str, Any]:
    """读取必填 dict 字段。"""

    value = raw.get(key)
    if not isinstance(value, dict):
        raise DatasetValidationError(f"{context}: {key} must be a dict")
    return value


def _required_list(raw: dict[str, Any], key: str, context: str) -> list[Any]:
    """读取必填 list 字段。"""

    value = raw.get(key)
    if not isinstance(value, list):
        raise DatasetValidationError(f"{context}: {key} must be a list")
    return value


def _choices_dict(value: object, context: str) -> dict[str, str]:
    """校验并归一化 A/B/C/D 选项。"""

    if not isinstance(value, dict):
        raise DatasetValidationError(f"{context}: choices must be a dict")
    choices: dict[str, str] = {}
    for key in ("A", "B", "C", "D"):
        text = str(value.get(key)).strip() if value.get(key) is not None else ""
        if not text:
            raise DatasetValidationError(f"{context}: choices.{key} is required")
        choices[key] = text
    return choices


def _target_step_ids(value: object, context: str) -> list[int]:
    """读取 MemBench 私有 target_step_id 列表。"""

    if not isinstance(value, list) or not value:
        raise DatasetValidationError(f"{context}: target_step_id must be a non-empty list")
    step_ids: list[int] = []
    for index, item in enumerate(value):
        if isinstance(item, bool):
            raise DatasetValidationError(
                f"{context}: target_step_id[{index}] must be an integer"
            )
        try:
            step_id = int(item)
        except (TypeError, ValueError) as exc:
            raise DatasetValidationError(
                f"{context}: target_step_id[{index}] must be an integer"
            ) from exc
        if step_id < 0:
            raise DatasetValidationError(
                f"{context}: target_step_id[{index}] must be non-negative"
            )
        step_ids.append(step_id)
    return step_ids


__all__ = [
    "MEMBENCH_0_10K_SOURCE_PATHS",
    "MEMBENCH_100K_SOURCE_PATHS",
    "MEMBENCH_INSTRUCTION_FIRST",
    "MEMBENCH_INSTRUCTION_FIRST_PROFILE",
    "MEMBENCH_VARIANT_SPECS",
    "MemBenchAdapter",
    "build_membench_unified_answer_prompt",
    "normalize_membench_choice_prediction",
    "parse_membench_choice",
    "prepare_membench_run",
]
