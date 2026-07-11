"""测试 benchmark registry 的 variant、scope 与 capability 声明。"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_benchmark.benchmark_adapters import (
    BenchmarkLoadRequest,
    BenchmarkRegistration,
    BenchmarkResumePolicy,
    BenchmarkSmokePolicy,
    BenchmarkVariantSpec,
    PreparedBenchmarkRun,
    RunScope,
    get_benchmark_registration,
    list_benchmarks,
    list_prediction_benchmarks,
    resolve_variant_selector,
)
from memory_benchmark.benchmark_adapters.registry import (
    LOCOMO_RESUME_POLICY,
    LOCOMO_SMOKE_POLICY,
)
from memory_benchmark.benchmark_adapters.locomo import (
    LoCoMoAdapter,
    build_locomo_smoke_dataset,
)
from memory_benchmark.benchmark_adapters.locomo_prompt import (
    LOCOMO_UNIFIED_ANSWER_PROMPT_PROFILE,
)
from memory_benchmark.benchmark_adapters.beam import (
    BEAM_ANSWER_PROMPT_PROFILE,
    BEAM_RESUME_POLICY,
    BEAM_SMOKE_POLICY,
    BeamAdapter,
)
from memory_benchmark.benchmark_adapters.halumem import (
    HALUMEM_RESUME_POLICY,
    HALUMEM_SMOKE_POLICY,
    HALUMEM_MEMZERO_PROMPT_PROFILE,
    HaluMemAdapter,
)
from memory_benchmark.benchmark_adapters.longmemeval import LongMemEvalAdapter
from memory_benchmark.benchmark_adapters.longmemeval_prompt import (
    build_longmemeval_unified_answer_prompt,
)
from memory_benchmark.benchmark_adapters.membench import (
    MEMBENCH_INSTRUCTION_FIRST_PROFILE,
    MemBenchAdapter,
    parse_membench_choice,
)
from memory_benchmark.core import (
    AnswerResult,
    Conversation,
    Dataset,
    GoldAnswerInfo,
    MethodCapability,
    PromptMessage,
    Question,
    Session,
    TaskFamily,
    Turn,
)
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.provider_protocol import RetrievalResult


pytestmark = pytest.mark.unit


def _make_valid_dataset(variant: str, run_scope: RunScope) -> Dataset:
    """构造一个满足通用校验的最小数据集。"""

    conversation = Conversation(
        conversation_id="conv-1",
        sessions=[
            Session(
                session_id="session-1",
                turns=[
                    Turn(
                        turn_id="turn-1",
                        speaker="user",
                        content="hello",
                    )
                ],
            )
        ],
        questions=[
            Question(
                question_id="question-1",
                conversation_id="conv-1",
                text="what happened?",
            )
        ],
        gold_answers={
            "question-1": GoldAnswerInfo(
                question_id="question-1",
                answer="there was a greeting",
            )
        },
        metadata={"variant": variant, "run_scope": run_scope.value},
    )
    return Dataset(
        dataset_name="demo",
        conversations=[conversation],
        metadata={"variant": variant, "run_scope": run_scope.value},
    )


def _make_registration(
    *,
    variants: tuple[BenchmarkVariantSpec, ...],
    default_variant: str,
    prepare_run=None,
    smoke_policy: BenchmarkSmokePolicy | None = None,
    resume_policy: BenchmarkResumePolicy | None = None,
) -> BenchmarkRegistration:
    """构造用于测试的最小 registration。"""

    if prepare_run is None:
        def prepare_run(project_root: Path, request: BenchmarkLoadRequest) -> PreparedBenchmarkRun:
            """返回与请求一致的最小 prepared run。"""

            return PreparedBenchmarkRun(
                variant=request.variant,
                run_scope=request.run_scope,
                dataset=_make_valid_dataset(request.variant, request.run_scope),
                source_relative_paths=next(
                    spec.source_relative_paths
                    for spec in variants
                    if spec.name == request.variant
                ),
            )

    return BenchmarkRegistration(
        name="demo",
        adapter_cls=LoCoMoAdapter,
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        variants=variants,
        default_variant=default_variant,
        prepare_run=prepare_run,
        prediction_enabled=True,
        smoke_policy=smoke_policy,
        resume_policy=resume_policy,
    )


def test_prediction_registry_exposes_only_current_phase_benchmark() -> None:
    """当前 phase 应开放 LoCoMo、LongMemEval、MemBench、HaluMem 与 BEAM prediction。"""

    assert list_benchmarks() == ["beam", "halumem", "locomo", "longmemeval", "membench"]
    assert list_prediction_benchmarks() == [
        "beam",
        "halumem",
        "locomo",
        "longmemeval",
        "membench",
    ]


def test_variant_selector_uses_default_concrete_variant_and_stable_order() -> None:
    """selector 为空、具体值和 all 时，应返回稳定的 concrete variant 序列。"""

    registration = _make_registration(
        variants=(
            BenchmarkVariantSpec(
                name="beta",
                source_relative_paths=(Path("data/demo/beta.json"),),
            ),
            BenchmarkVariantSpec(
                name="alpha",
                source_relative_paths=(Path("data/demo/alpha.json"),),
            ),
        ),
        default_variant="beta",
    )

    assert resolve_variant_selector(registration, None) == ("beta",)
    assert resolve_variant_selector(registration, "alpha") == ("alpha",)
    assert resolve_variant_selector(registration, "all") == ("beta", "alpha")


def test_variant_selector_rejects_unknown_value_with_allowed_choices() -> None:
    """未知 selector 应报错并列出请求值和允许值。"""

    registration = _make_registration(
        variants=(
            BenchmarkVariantSpec(
                name="beta",
                source_relative_paths=(Path("data/demo/beta.json"),),
            ),
            BenchmarkVariantSpec(
                name="alpha",
                source_relative_paths=(Path("data/demo/alpha.json"),),
            ),
        ),
        default_variant="beta",
    )

    with pytest.raises(ConfigurationError) as exc_info:
        resolve_variant_selector(registration, "gamma")

    message = str(exc_info.value)
    assert "gamma" in message
    assert "beta" in message
    assert "alpha" in message
    assert "all" in message


def test_registration_rejects_duplicate_variant_names() -> None:
    """重复 variant 名称应在 registration 构造阶段被拒绝。"""

    with pytest.raises(ConfigurationError):
        _make_registration(
            variants=(
                BenchmarkVariantSpec(
                    name="dup",
                    source_relative_paths=(Path("data/demo/one.json"),),
                ),
                BenchmarkVariantSpec(
                    name="dup",
                    source_relative_paths=(Path("data/demo/two.json"),),
                ),
            ),
            default_variant="dup",
        )


def test_variant_spec_rejects_whitespace_only_names() -> None:
    """仅包含空白的 variant 名称应被拒绝。"""

    with pytest.raises(ConfigurationError):
        BenchmarkVariantSpec(
            name="   ",
            source_relative_paths=(Path("data/demo/one.json"),),
        )


def test_variant_spec_rejects_empty_source_path_list() -> None:
    """variant 必须至少声明一个 source path。"""

    with pytest.raises(ConfigurationError):
        BenchmarkVariantSpec(
            name="demo",
            source_relative_paths=(),
        )


def test_registration_rejects_concrete_variant_named_all() -> None:
    """concrete variant 不能占用 all 这个 selector 名称。"""

    with pytest.raises(ConfigurationError):
        _make_registration(
            variants=(
                BenchmarkVariantSpec(
                    name="all",
                    source_relative_paths=(Path("data/demo/one.json"),),
                ),
            ),
            default_variant="all",
        )


@pytest.mark.parametrize(
    "source_path",
    [
        Path("/tmp/demo.json"),
        Path("data/../demo.json"),
    ],
)
def test_registration_rejects_unsafe_source_paths(source_path: Path) -> None:
    """绝对路径和包含 .. 的路径都不应进入 variant 声明。"""

    with pytest.raises(ConfigurationError):
        _make_registration(
            variants=(
                BenchmarkVariantSpec(
                    name="demo",
                    source_relative_paths=(source_path,),
                ),
            ),
            default_variant="demo",
        )


@pytest.mark.parametrize(
    "unsafe_name",
    ("foo/bar", "../foo", "..", ".hidden", "foo bar"),
)
def test_variant_spec_rejects_unsafe_run_id_names(unsafe_name: str) -> None:
    """variant 名不能包含路径逃逸或无法安全组成 run_id 的字符。"""

    with pytest.raises(ConfigurationError, match="variant name"):
        BenchmarkVariantSpec(
            name=unsafe_name,
            source_relative_paths=(Path("data/demo/value.json"),),
        )


def test_registration_rejects_normalized_variant_token_collision() -> None:
    """不同 variant 名归一化为同一 run-id token 时必须在注册阶段拒绝。"""

    with pytest.raises(ConfigurationError, match="run-id token"):
        _make_registration(
            variants=(
                BenchmarkVariantSpec(
                    name="a_b",
                    source_relative_paths=(Path("data/demo/a.json"),),
                ),
                BenchmarkVariantSpec(
                    name="a-b",
                    source_relative_paths=(Path("data/demo/b.json"),),
                ),
            ),
            default_variant="a_b",
        )


def test_registration_rejects_case_insensitive_variant_token_collision() -> None:
    """不同大小写但目标 run-id 仅大小写不同的 variant 必须保守拒绝。"""

    with pytest.raises(ConfigurationError, match="case-insensitive"):
        _make_registration(
            variants=(
                BenchmarkVariantSpec(
                    name="A",
                    source_relative_paths=(Path("data/demo/a.json"),),
                ),
                BenchmarkVariantSpec(
                    name="a",
                    source_relative_paths=(Path("data/demo/b.json"),),
                ),
            ),
            default_variant="A",
        )


def test_registration_rejects_missing_default_variant() -> None:
    """default_variant 必须指向已声明的 concrete variant。"""

    with pytest.raises(ConfigurationError):
        _make_registration(
            variants=(
                BenchmarkVariantSpec(
                    name="demo",
                    source_relative_paths=(Path("data/demo/demo.json"),),
                ),
            ),
            default_variant="missing",
        )


def test_registration_prepare_rejects_returned_variant_mismatch() -> None:
    """prepare_run 返回的 variant 必须和请求一致。"""

    def prepare_run(project_root: Path, request: BenchmarkLoadRequest) -> PreparedBenchmarkRun:
        """返回故意错配 variant 的 prepared run。"""

        return PreparedBenchmarkRun(
            variant="other",
            run_scope=request.run_scope,
            dataset=_make_valid_dataset(request.variant, request.run_scope),
            source_relative_paths=(Path("data/demo/demo.json"),),
        )

    registration = _make_registration(
        variants=(
            BenchmarkVariantSpec(
                name="demo",
                source_relative_paths=(Path("data/demo/demo.json"),),
            ),
        ),
        default_variant="demo",
        prepare_run=prepare_run,
    )

    with pytest.raises(ConfigurationError):
        registration.prepare(
            Path("."),
            BenchmarkLoadRequest(variant="demo", run_scope=RunScope.FULL),
        )


def test_registration_prepare_rejects_returned_source_path_mismatch() -> None:
    """prepare_run 返回的 source path 必须和注册声明一致。"""

    def prepare_run(project_root: Path, request: BenchmarkLoadRequest) -> PreparedBenchmarkRun:
        """返回故意错配 source path 的 prepared run。"""

        return PreparedBenchmarkRun(
            variant=request.variant,
            run_scope=request.run_scope,
            dataset=_make_valid_dataset(request.variant, request.run_scope),
            source_relative_paths=(Path("data/demo/other.json"),),
        )

    registration = _make_registration(
        variants=(
            BenchmarkVariantSpec(
                name="demo",
                source_relative_paths=(Path("data/demo/demo.json"),),
            ),
        ),
        default_variant="demo",
        prepare_run=prepare_run,
    )

    with pytest.raises(ConfigurationError):
        registration.prepare(
            Path("."),
            BenchmarkLoadRequest(variant="demo", run_scope=RunScope.FULL),
        )


def test_registration_prepare_rejects_dataset_metadata_mismatch() -> None:
    """prepare_run 返回的数据集 metadata 必须写入 variant 和 run_scope。"""

    def prepare_run(project_root: Path, request: BenchmarkLoadRequest) -> PreparedBenchmarkRun:
        """返回故意错配 dataset metadata 的 prepared run。"""

        dataset = _make_valid_dataset(request.variant, request.run_scope)
        dataset.metadata["variant"] = "other"
        return PreparedBenchmarkRun(
            variant=request.variant,
            run_scope=request.run_scope,
            dataset=dataset,
            source_relative_paths=(Path("data/demo/demo.json"),),
        )

    registration = _make_registration(
        variants=(
            BenchmarkVariantSpec(
                name="demo",
                source_relative_paths=(Path("data/demo/demo.json"),),
            ),
        ),
        default_variant="demo",
        prepare_run=prepare_run,
    )

    with pytest.raises(ConfigurationError):
        registration.prepare(
            Path("."),
            BenchmarkLoadRequest(variant="demo", run_scope=RunScope.FULL),
        )


def test_locomo_registration_declares_conversation_qa_capabilities() -> None:
    """LoCoMo registration 应声明 conversation-QA 所需能力。"""

    registration = get_benchmark_registration("locomo")

    assert registration.task_family is TaskFamily.CONVERSATION_QA
    assert registration.required_capabilities == frozenset(
        {
            MethodCapability.CONVERSATION_ADD,
            MethodCapability.MEMORY_RETRIEVAL,
        }
    )
    assert registration.prediction_enabled is True
    assert registration.operation_level is False
    assert registration.default_variant == "locomo10"
    assert registration.variants == (
        BenchmarkVariantSpec(
            name="locomo10",
            source_relative_paths=(Path("data/locomo/locomo10.json"),),
        ),
    )
    assert resolve_variant_selector(registration, None) == ("locomo10",)
    assert resolve_variant_selector(registration, "all") == ("locomo10",)


def test_longmemeval_registration_declares_both_variants_and_prediction_enabled() -> None:
    """LongMemEval registration 应声明 S/M 两个 variant 且开放 prediction。"""

    registration = get_benchmark_registration("longmemeval")

    assert registration.task_family is TaskFamily.CONVERSATION_QA
    assert registration.required_capabilities == frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
    )
    assert registration.prediction_enabled is True
    assert registration.operation_level is False
    assert registration.prompt_track == "unified"
    assert (
        registration.unified_prompt_builder
        is build_longmemeval_unified_answer_prompt
    )
    assert registration.default_variant == "s_cleaned"
    assert registration.variants == (
        BenchmarkVariantSpec(
            name="s_cleaned",
            source_relative_paths=(Path("data/longmemeval/longmemeval_s_cleaned.json"),),
        ),
        BenchmarkVariantSpec(
            name="m_cleaned",
            source_relative_paths=(Path("data/longmemeval/longmemeval_m_cleaned.json"),),
        ),
    )
    assert resolve_variant_selector(registration, None) == ("s_cleaned",)
    assert resolve_variant_selector(registration, "all") == ("s_cleaned", "m_cleaned")


def test_membench_registration_declares_variants_and_prediction_enabled() -> None:
    """MemBench registration 应声明 0_10k/100k 两个 variant 且开放 prediction。"""

    registration = get_benchmark_registration("membench")

    assert registration.adapter_cls is MemBenchAdapter
    assert registration.task_family is TaskFamily.CONVERSATION_QA
    assert registration.required_capabilities == frozenset(
        {
            MethodCapability.CONVERSATION_ADD,
            MethodCapability.MEMORY_RETRIEVAL,
        }
    )
    assert registration.prediction_enabled is True
    assert registration.operation_level is False
    assert registration.prompt_track == "unified"
    assert registration.unified_prompt_builder is not None
    assert registration.prediction_transform is not None
    assert registration.default_variant == "0_10k"
    assert registration.variants == (
        BenchmarkVariantSpec(
            name="0_10k",
            source_relative_paths=(
                Path(
                    "data/membench/Membenchdata/data2test/0-10k/FirstAgentDataHighLevel_multiple_0.json"
                ),
                Path(
                    "data/membench/Membenchdata/data2test/0-10k/FirstAgentDataLowLevel_multiple_0.json"
                ),
                Path(
                    "data/membench/Membenchdata/data2test/0-10k/ThirdAgentDataHighLevel_multiple_0.json"
                ),
                Path(
                    "data/membench/Membenchdata/data2test/0-10k/ThirdAgentDataLowLevel_multiple_0.json"
                ),
            ),
        ),
        BenchmarkVariantSpec(
            name="100k",
            source_relative_paths=(
                Path(
                    "data/membench/Membenchdata/data2test/100k/FirstAgentDataHighLevel_multiple_100.json"
                ),
                Path(
                    "data/membench/Membenchdata/data2test/100k/FirstAgentDataLowLevel_multiple_100.json"
                ),
                Path(
                    "data/membench/Membenchdata/data2test/100k/ThirdAgentDataHighLevel_multiple_100.json"
                ),
                Path(
                    "data/membench/Membenchdata/data2test/100k/ThirdAgentDataLowLevel_multiple_100.json"
                ),
            ),
        ),
    )
    assert resolve_variant_selector(registration, None) == ("0_10k",)
    assert resolve_variant_selector(registration, "all") == ("0_10k", "100k")


def test_halumem_registration_declares_operation_level_unified_prompt() -> None:
    """HaluMem registration 应声明 operation-level runner 与 unified prompt。"""

    registration = get_benchmark_registration("halumem")

    assert registration.adapter_cls is HaluMemAdapter
    assert registration.task_family is TaskFamily.CONVERSATION_QA
    assert registration.required_capabilities == frozenset()
    assert registration.prediction_enabled is True
    assert registration.operation_level is True
    assert registration.prompt_track == "unified"
    assert registration.unified_prompt_builder is not None
    assert registration.smoke_policy == HALUMEM_SMOKE_POLICY
    assert registration.resume_policy == HALUMEM_RESUME_POLICY
    assert registration.smoke_policy == BenchmarkSmokePolicy(
        history_axis="sessions",
        default_history_limit=4,
        default_isolation_limit=1,
        default_question_limit=1,
    )
    assert registration.resume_policy == BenchmarkResumePolicy(
        smoke_enabled=False,
        ingest_checkpoint="conversation",
        answer_checkpoint="question",
        reuse_saved_retrieval=True,
        evaluation_artifact_only=True,
    )
    assert registration.default_variant == "medium"
    assert registration.variants == (
        BenchmarkVariantSpec(
            name="medium",
            source_relative_paths=(Path("data/halumem/HaluMem-Medium.jsonl"),),
        ),
        BenchmarkVariantSpec(
            name="long",
            source_relative_paths=(Path("data/halumem/HaluMem-Long.jsonl"),),
        ),
    )
    assert resolve_variant_selector(registration, None) == ("medium",)
    assert resolve_variant_selector(registration, "all") == ("medium", "long")


def test_halumem_unified_prompt_builder_uses_official_memzero_prompt() -> None:
    """HaluMem unified prompt 应复刻官方 PROMPT_MEMZERO 拼接形态。"""

    registration = get_benchmark_registration("halumem")
    question = Question(
        question_id="conv-1:s1:q1",
        conversation_id="conv-1",
        text="Where does Riley live?",
    )
    retrieval_result = RetrievalResult(
        formatted_memory="[2025-09-04] Riley lives in Boston.",
        metadata={"provider": "fake"},
    )

    prompt = registration.unified_prompt_builder(question, retrieval_result)

    assert prompt.metadata["answer_prompt_profile"] == HALUMEM_MEMZERO_PROMPT_PROFILE
    assert prompt.metadata["prompt_track"] == "unified"
    assert prompt.metadata["official_source"].endswith("prompts.py:1-40")
    assert prompt.prompt_messages == [
        PromptMessage(role="user", content=prompt.answer_prompt)
    ]
    assert "[2025-09-04] Riley lives in Boston." in prompt.answer_prompt
    assert "Question: Where does Riley live?" in prompt.answer_prompt
    assert "You have access to memories from two speakers in a conversation." in (
        prompt.answer_prompt
    )


def test_membench_unified_prompt_builder_uses_official_instruction_first() -> None:
    """MemBench unified prompt 应复刻官方 INSTRUCTION_FIRST 拼接形态。"""

    registration = get_benchmark_registration("membench")
    question = Question(
        question_id="conv-1:q1",
        conversation_id="conv-1",
        text="What will Alex choose?",
        question_time="2026-01-02",
        options={
            "A": "Tea",
            "B": "Coffee",
            "C": "Juice",
            "D": "Water",
        },
    )
    retrieval_result = RetrievalResult(
        formatted_memory="Alex said coffee is the morning choice.",
        metadata={"provider": "fake"},
    )

    prompt = registration.unified_prompt_builder(question, retrieval_result)

    assert prompt.metadata["answer_prompt_profile"] == MEMBENCH_INSTRUCTION_FIRST_PROFILE
    assert prompt.metadata["prompt_track"] == "unified"
    assert prompt.metadata["official_source"].endswith(
        "MembenchAgent.py:21-31,89-92,93-112"
    )
    assert prompt.prompt_messages == [
        PromptMessage(role="user", content=prompt.answer_prompt)
    ]
    assert prompt.answer_prompt == (
        "Please answer the following question based on past memories of "
        "your'conversation with the user.\n"
        "Past memory: Alex said coffee is the morning choice.\n"
        "Question: (current time is 2026-01-02) What will Alex choose?\n"
        "Choices:\n"
        "A. Tea\n"
        "B. Coffee\n"
        "C. Juice\n"
        "D. Water\n"
        "Please output the correct option for the question, only one "
        "corresponding letter, without any other messages.\n"
        "Example: D\n"
    )


@pytest.mark.parametrize(
    ("raw_answer", "expected"),
    [
        ("A", "A"),
        ("b.", "B"),
        ("The answer is C.", "C"),
        ('{"choice": "d"}', "D"),
        ("I cannot decide", "invalid_choice"),
        # 大写优先：独立小写 "a" 是英文冠词，不得抢在真实选项字母之前
        ("Alex bought a bike, so the answer is C.", "C"),
        ("the answer is a", "A"),
    ],
)
def test_membench_choice_parser_accepts_common_reader_outputs(
    raw_answer: str,
    expected: str,
) -> None:
    """MemBench choice parser 应容忍大小写、句号、前后缀和官方 JSON 输出。"""

    assert parse_membench_choice(raw_answer) == expected

    registration = get_benchmark_registration("membench")
    transformed = registration.prediction_transform(
        AnswerResult(
            question_id="q1",
            conversation_id="conv-1",
            answer=raw_answer,
            metadata={"answer_reader": "framework"},
        )
    )
    assert transformed.answer == expected
    assert transformed.metadata["raw_answer"] == raw_answer


def test_longmemeval_registration_prepares_full_and_smoke_datasets() -> None:
    """LongMemEval registration 的 full 与 smoke 预处理应写入正确 metadata。"""

    registration = get_benchmark_registration("longmemeval")

    full_run = registration.prepare(
        Path("."),
        BenchmarkLoadRequest(variant="s_cleaned", run_scope=RunScope.FULL),
    )
    assert full_run.variant == "s_cleaned"
    assert full_run.run_scope is RunScope.FULL
    assert full_run.source_relative_paths == (
        Path("data/longmemeval/longmemeval_s_cleaned.json"),
    )
    assert full_run.dataset.metadata["variant"] == "s_cleaned"
    assert full_run.dataset.metadata["run_scope"] == "full"
    assert full_run.dataset.metadata["total_raw_instances"] == 500
    assert full_run.dataset.metadata["source_fully_scanned"] is True

    smoke_run = registration.prepare(
        Path("."),
        BenchmarkLoadRequest(
            variant="m_cleaned",
            run_scope=RunScope.SMOKE,
            smoke_turn_limit=1,
            smoke_conversation_limit=99,
        ),
    )
    assert smoke_run.variant == "m_cleaned"
    assert smoke_run.run_scope is RunScope.SMOKE
    assert smoke_run.source_relative_paths == (
        Path("data/longmemeval/longmemeval_m_cleaned.json"),
    )
    assert smoke_run.dataset.metadata["variant"] == "m_cleaned"
    assert smoke_run.dataset.metadata["run_scope"] == "smoke"
    assert smoke_run.dataset.metadata["total_raw_instances"] == 99
    assert smoke_run.dataset.metadata["source_fully_scanned"] is False
    assert smoke_run.dataset.metadata["smoke_round_limit"] == 1
    assert smoke_run.dataset.metadata["smoke_original_turn_count"] > 2
    assert smoke_run.dataset.metadata["smoke_retained_turn_count"] == 198
    assert smoke_run.dataset.metadata["smoke_retained_round_count"] == 99
    assert len(smoke_run.dataset.conversations) == 99
    smoke_conversation = smoke_run.dataset.conversations[0]
    assert sum(len(session.turns) for session in smoke_conversation.sessions) == 2
    assert smoke_conversation.metadata["smoke_retained_round_count"] == 1
    assert smoke_conversation.metadata["smoke_retained_turn_count"] == 2


def test_membench_registration_prepares_full_and_per_file_smoke_datasets() -> None:
    """MemBench smoke 应从每个主文件取前 N 条 trajectory，且不裁剪 message_list。"""

    registration = get_benchmark_registration("membench")

    smoke_run = registration.prepare(
        Path("."),
        BenchmarkLoadRequest(
            variant="0_10k",
            run_scope=RunScope.SMOKE,
            smoke_conversation_limit=2,
            smoke_turn_limit=1,
        ),
    )

    assert smoke_run.variant == "0_10k"
    assert smoke_run.run_scope is RunScope.SMOKE
    assert smoke_run.dataset.metadata["variant"] == "0_10k"
    assert smoke_run.dataset.metadata["run_scope"] == "smoke"
    assert smoke_run.dataset.metadata["smoke_per_source_conversation_limit"] == 2
    assert smoke_run.dataset.metadata["smoke_selected_conversation_count"] == 8
    assert set(smoke_run.dataset.metadata["smoke_source_counts"].values()) == {2}
    assert len(smoke_run.dataset.conversations) == 8
    # 第一人称 1 round = 1 Turn（FirstAgentDataHighLevel 是第一个源文件）
    assert len(smoke_run.dataset.conversations[0].sessions[0].turns) == 1
    assert smoke_run.dataset.metadata["smoke_history_limit"] == 1
    assert "smoke_original_turn_count" in smoke_run.dataset.metadata
    assert "smoke_retained_turn_count" in smoke_run.dataset.metadata
    assert "smoke_policy" in smoke_run.dataset.metadata
    assert "resume_policy" in smoke_run.dataset.metadata
    assert smoke_run.source_relative_paths == registration.variants[0].source_relative_paths

    full_run = registration.prepare(
        Path("."),
        BenchmarkLoadRequest(variant="100k", run_scope=RunScope.FULL),
    )
    assert full_run.variant == "100k"
    assert full_run.run_scope is RunScope.FULL
    assert full_run.dataset.metadata["variant"] == "100k"
    assert full_run.dataset.metadata["run_scope"] == "full"
    assert len(full_run.dataset.conversations) == 860


def test_locomo_registration_prepares_full_and_smoke_datasets() -> None:
    """LoCoMo registration 的 full 与 smoke 预处理应写入正确 metadata。"""

    registration = get_benchmark_registration("locomo")

    full_run = registration.prepare(
        Path("."),
        BenchmarkLoadRequest(variant="locomo10", run_scope=RunScope.FULL),
    )
    assert full_run.variant == "locomo10"
    assert full_run.run_scope is RunScope.FULL
    assert full_run.source_relative_paths == (
        Path("data/locomo/locomo10.json"),
    )
    assert full_run.dataset.metadata["variant"] == "locomo10"
    assert full_run.dataset.metadata["run_scope"] == "full"
    # smoke/resume policy 必须写入 dataset metadata（不只存在于 CLI --help），
    # 供审计和 resume 一致性检查复用；full run 同样携带，因为 policy 属于
    # benchmark 声明本身，与 run_scope 无关。
    assert full_run.dataset.metadata["smoke_policy"] == LOCOMO_SMOKE_POLICY.to_dict()
    assert full_run.dataset.metadata["resume_policy"] == LOCOMO_RESUME_POLICY.to_dict()

    smoke_run = registration.prepare(
        Path("."),
        BenchmarkLoadRequest(
            variant="locomo10",
            run_scope=RunScope.SMOKE,
            smoke_conversation_limit=2,
        ),
    )
    expected_smoke = build_locomo_smoke_dataset(
        LoCoMoAdapter(Path(".")).load(limit=2),
        conversation_limit=2,
    )
    assert smoke_run.variant == "locomo10"
    assert smoke_run.run_scope is RunScope.SMOKE
    assert smoke_run.source_relative_paths == (
        Path("data/locomo/locomo10.json"),
    )
    assert smoke_run.dataset.metadata["variant"] == "locomo10"
    assert smoke_run.dataset.metadata["run_scope"] == "smoke"
    assert smoke_run.dataset.metadata["smoke_turn_limit"] == 20
    assert smoke_run.dataset.metadata["smoke_conversation_limit"] == 2
    assert smoke_run.dataset.metadata["smoke_policy"] == LOCOMO_SMOKE_POLICY.to_dict()
    assert smoke_run.dataset.metadata["resume_policy"] == LOCOMO_RESUME_POLICY.to_dict()
    assert len(smoke_run.dataset.conversations) == 2
    assert smoke_run.dataset.conversations == expected_smoke.conversations


def test_locomo_registration_declares_frozen_smoke_and_resume_policy() -> None:
    """LoCoMo registration 必须声明 plan 指定的 smoke/resume policy 精确取值。"""

    registration = get_benchmark_registration("locomo")

    assert registration.smoke_policy == BenchmarkSmokePolicy(
        history_axis="rounds",
        default_history_limit=1,
        default_isolation_limit=1,
        default_question_limit=1,
    )
    assert registration.resume_policy == BenchmarkResumePolicy(
        smoke_enabled=False,
        ingest_checkpoint="conversation",
        answer_checkpoint="question",
        reuse_saved_retrieval=True,
        evaluation_artifact_only=True,
    )


def test_longmemeval_registration_declares_frozen_smoke_and_resume_policy() -> None:
    """LongMemEval registration 必须声明 C2 冻结的 smoke/resume policy 精确取值。"""

    registration = get_benchmark_registration("longmemeval")

    # smoke 轴 = rounds（双 turn round），默认 1 instance × 1 round；选择不读私有
    # answer/answer_session_ids/has_answer，答对不属于 smoke 成功条件（见
    # plan-b2-longmemeval.md C2）。
    assert registration.smoke_policy == BenchmarkSmokePolicy(
        history_axis="rounds",
        default_history_limit=1,
        default_isolation_limit=1,
        default_question_limit=1,
    )
    # resume：smoke 禁 resume；formal 为 conversation(=instance) 级，不引入
    # turn/session 级 resume。
    assert registration.resume_policy == BenchmarkResumePolicy(
        smoke_enabled=False,
        ingest_checkpoint="conversation",
        answer_checkpoint="question",
        reuse_saved_retrieval=True,
        evaluation_artifact_only=True,
    )


def test_longmemeval_prepared_run_carries_policy_metadata() -> None:
    """prepared run 的 dataset metadata 必须写入 smoke/resume policy 字典。"""

    registration = get_benchmark_registration("longmemeval")
    full_run = registration.prepare(
        Path("."),
        BenchmarkLoadRequest(
            variant="s_cleaned",
            run_scope=RunScope.FULL,
        ),
    )
    assert full_run.dataset.metadata["smoke_policy"] == (
        registration.smoke_policy.to_dict()
    )
    assert full_run.dataset.metadata["resume_policy"] == (
        registration.resume_policy.to_dict()
    )


def test_locomo_registration_declares_unified_prompt_track() -> None:
    """LoCoMo registration 必须默认 unified prompt_track 并声明 builder。"""

    registration = get_benchmark_registration("locomo")

    assert registration.prompt_track == "unified"
    assert registration.unified_prompt_builder is not None


def test_locomo_unified_prompt_uses_official_short_phrase_qa_prompt() -> None:
    """普通题必须用官方 short-phrase QA prompt，且不含 method 名/gold/evidence。"""

    registration = get_benchmark_registration("locomo")
    question = Question(
        question_id="conv-1:q1",
        conversation_id="conv-1",
        text="What did Alice eat?",
        category="4",
    )
    retrieval_result = RetrievalResult(
        formatted_memory="[2023-01-01] Alice: I ate pizza.",
        metadata={"provider": "fake"},
    )

    prompt = registration.unified_prompt_builder(question, retrieval_result)

    assert prompt.prompt_messages[0].role == "user"
    assert "What did Alice eat? Short answer:" in prompt.prompt_messages[0].content
    assert "Answer with exact words from the context" in prompt.prompt_messages[0].content
    assert "[2023-01-01] Alice: I ate pizza." in prompt.prompt_messages[0].content
    assert "Use DATE of CONVERSATION" not in prompt.prompt_messages[0].content
    assert prompt.metadata["prompt_track"] == "unified"
    assert prompt.metadata["answer_prompt_profile"] == LOCOMO_UNIFIED_ANSWER_PROMPT_PROFILE
    assert prompt.metadata["answer_context"] == retrieval_result.formatted_memory
    assert "gpt_utils.py" in prompt.metadata["official_source"]
    for private_key in ("gold", "evidence", "judge_label", "mem0", "memoryos"):
        assert private_key not in prompt.prompt_messages[0].content.lower()


def test_locomo_unified_prompt_appends_official_date_hint_for_category_2() -> None:
    """category 2（temporal）必须追加官方日期提示，其他 category 不追加。"""

    registration = get_benchmark_registration("locomo")
    question = Question(
        question_id="conv-1:q2",
        conversation_id="conv-1",
        text="When did Alice move?",
        category="2",
    )
    retrieval_result = RetrievalResult(formatted_memory="[2023-01-01] Alice moved.")

    prompt = registration.unified_prompt_builder(question, retrieval_result)

    assert (
        "When did Alice move? Use DATE of CONVERSATION to answer with an "
        "approximate date. Short answer:" in prompt.prompt_messages[0].content
    )


def test_benchmark_smoke_policy_rejects_unknown_history_axis() -> None:
    """history_axis 只能是 rounds/turns/sessions/sources 之一。"""

    with pytest.raises(ConfigurationError):
        BenchmarkSmokePolicy(
            history_axis="messages",  # type: ignore[arg-type]
            default_history_limit=1,
        )


@pytest.mark.parametrize(
    "field_name",
    ["default_history_limit", "default_isolation_limit", "default_question_limit"],
)
def test_benchmark_smoke_policy_rejects_non_positive_limits(field_name: str) -> None:
    """smoke policy 的三个预算字段都必须是正整数。"""

    kwargs = {
        "history_axis": "rounds",
        "default_history_limit": 1,
        "default_isolation_limit": 1,
        "default_question_limit": 1,
        field_name: 0,
    }
    with pytest.raises(ConfigurationError):
        BenchmarkSmokePolicy(**kwargs)


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [("ingest_checkpoint", "turn"), ("answer_checkpoint", "conversation")],
)
def test_benchmark_resume_policy_rejects_unknown_checkpoint_granularity(
    field_name: str,
    bad_value: str,
) -> None:
    """resume policy 的 checkpoint 粒度当前只接受 conversation/question。"""

    kwargs = {
        "smoke_enabled": False,
        "ingest_checkpoint": "conversation",
        "answer_checkpoint": "question",
        "reuse_saved_retrieval": True,
        "evaluation_artifact_only": True,
        field_name: bad_value,
    }
    with pytest.raises(ConfigurationError):
        BenchmarkResumePolicy(**kwargs)


def test_registration_requires_smoke_and_resume_policy_declared_together() -> None:
    """只声明 smoke_policy 或只声明 resume_policy 都应在构造阶段被拒绝。"""

    smoke_policy = BenchmarkSmokePolicy(history_axis="rounds", default_history_limit=1)
    resume_policy = BenchmarkResumePolicy(
        smoke_enabled=False,
        ingest_checkpoint="conversation",
        answer_checkpoint="question",
        reuse_saved_retrieval=True,
        evaluation_artifact_only=True,
    )

    with pytest.raises(ConfigurationError):
        _make_registration(
            variants=(
                BenchmarkVariantSpec(
                    name="only-smoke",
                    source_relative_paths=(Path("data/demo/one.json"),),
                ),
            ),
            default_variant="only-smoke",
            smoke_policy=smoke_policy,
            resume_policy=None,
        )

    with pytest.raises(ConfigurationError):
        _make_registration(
            variants=(
                BenchmarkVariantSpec(
                    name="only-resume",
                    source_relative_paths=(Path("data/demo/one.json"),),
                ),
            ),
            default_variant="only-resume",
            smoke_policy=None,
            resume_policy=resume_policy,
        )

    # 两者一起声明应正常构造并保留字段。
    registration = _make_registration(
        variants=(
            BenchmarkVariantSpec(
                name="both",
                source_relative_paths=(Path("data/demo/one.json"),),
            ),
        ),
        default_variant="both",
        smoke_policy=smoke_policy,
        resume_policy=resume_policy,
    )
    assert registration.smoke_policy is smoke_policy
    assert registration.resume_policy is resume_policy


# ---------------------------------------------------------------------------
# BEAM registration
# ---------------------------------------------------------------------------


def test_beam_registration_declares_conversation_qa_unified_prompt() -> None:
    """BEAM registration 应声明 conversation-QA、unified prompt、无 operation_level。"""

    registration = get_benchmark_registration("beam")

    assert registration.adapter_cls is BeamAdapter
    assert registration.task_family is TaskFamily.CONVERSATION_QA
    assert registration.required_capabilities == frozenset()
    assert registration.prediction_enabled is True
    assert registration.operation_level is False
    assert registration.prompt_track == "unified"
    assert registration.unified_prompt_builder is not None
    assert registration.prediction_transform is None
    assert registration.default_variant == "100k"
    assert registration.variants == (
        BenchmarkVariantSpec(
            name="100k",
            source_relative_paths=(Path("data/BEAM/beam_dataset/100K"),),
        ),
        BenchmarkVariantSpec(
            name="500k",
            source_relative_paths=(Path("data/BEAM/beam_dataset/500K"),),
        ),
        BenchmarkVariantSpec(
            name="1m",
            source_relative_paths=(Path("data/BEAM/beam_dataset/1M"),),
        ),
        BenchmarkVariantSpec(
            name="10m",
            source_relative_paths=(Path("data/BEAM/beam_10M_dataset/10M"),),
        ),
    )
    assert registration.smoke_policy == BEAM_SMOKE_POLICY
    assert registration.resume_policy == BEAM_RESUME_POLICY
    assert resolve_variant_selector(registration, None) == ("100k",)
    assert resolve_variant_selector(registration, "all") == (
        "100k", "500k", "1m", "10m"
    )


def test_beam_unified_prompt_builder_uses_official_rag_prompt() -> None:
    """BEAM unified prompt 应复刻官方 answer_generation_for_rag（RAG 路径）。"""

    registration = get_benchmark_registration("beam")
    question = Question(
        question_id="1:abstention:q1",
        conversation_id="1",
        text="What did I do yesterday?",
    )
    retrieval_result = RetrievalResult(
        formatted_memory="Yesterday you wrote code.",
        metadata={"provider": "fake"},
    )

    prompt = registration.unified_prompt_builder(question, retrieval_result)

    assert prompt.metadata["answer_prompt_profile"] == BEAM_ANSWER_PROMPT_PROFILE
    assert prompt.metadata["prompt_track"] == "unified"
    assert prompt.metadata["official_source"].endswith("prompts.py:11683-11701")
    assert prompt.prompt_messages == [
        PromptMessage(role="user", content=prompt.answer_prompt)
    ]
    # 双向一致性：formatted_memory 应出现在 prompt 中（替换 <context>）
    assert "Yesterday you wrote code." in prompt.answer_prompt
    # question 文本应出现在 prompt 中（替换 <question>）
    assert "What did I do yesterday?" in prompt.answer_prompt
    # RAG 约束关键词
    assert "Answer ONLY based on the provided context" in prompt.answer_prompt
    # 确认是 RAG 路径而非 long-context 路径（不应出现 "NOTE: Only provide the answer"）
    assert "NOTE: Only provide the answer" not in prompt.answer_prompt


def test_beam_registration_prepares_smoke_with_declared_round_policy() -> None:
    """BEAM smoke 应按已声明的 round policy 裁剪并写入 metadata。"""

    registration = get_benchmark_registration("beam")

    smoke_run = registration.prepare(
        Path("."),
        BenchmarkLoadRequest(
            variant="100k",
            run_scope=RunScope.SMOKE,
            smoke_turn_limit=1,
            smoke_conversation_limit=1,
        ),
    )
    assert smoke_run.variant == "100k"
    assert smoke_run.run_scope is RunScope.SMOKE
    assert smoke_run.dataset.metadata["variant"] == "100k"
    assert smoke_run.dataset.metadata["run_scope"] == "smoke"
    assert smoke_run.dataset.metadata["smoke_round_limit"] == 1
    assert smoke_run.dataset.metadata["smoke_policy"] == BEAM_SMOKE_POLICY.to_dict()
    assert smoke_run.dataset.metadata["resume_policy"] == BEAM_RESUME_POLICY.to_dict()
    assert len(smoke_run.dataset.conversations) == 1
    conversation = smoke_run.dataset.conversations[0]
    total_turns = sum(len(s.turns) for s in conversation.sessions)
    assert total_turns == 2
    assert len(conversation.questions) >= 1
    assert registration.smoke_policy.default_question_limit == 1
