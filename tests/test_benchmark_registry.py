"""测试 benchmark registry 的 variant、scope 与 capability 声明。"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_benchmark.benchmark_adapters import (
    BenchmarkLoadRequest,
    BenchmarkRegistration,
    BenchmarkVariantSpec,
    PreparedBenchmarkRun,
    RunScope,
    get_benchmark_registration,
    list_benchmarks,
    list_prediction_benchmarks,
    resolve_variant_selector,
)
from memory_benchmark.benchmark_adapters.locomo import (
    LoCoMoAdapter,
    build_locomo_smoke_dataset,
)
from memory_benchmark.benchmark_adapters.longmemeval import LongMemEvalAdapter
from memory_benchmark.core import (
    Conversation,
    Dataset,
    GoldAnswerInfo,
    MethodCapability,
    Question,
    Session,
    TaskFamily,
    Turn,
)
from memory_benchmark.core.exceptions import ConfigurationError


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
    )


def test_prediction_registry_exposes_only_current_phase_benchmark() -> None:
    """当前 phase 应开放 LoCoMo 与 LongMemEval prediction。"""

    assert list_benchmarks() == ["locomo", "longmemeval"]
    assert list_prediction_benchmarks() == ["locomo", "longmemeval"]


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
            MethodCapability.ANSWER_GENERATION,
        }
    )
    assert registration.prediction_enabled is True
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
                MethodCapability.ANSWER_GENERATION,
            }
    )
    assert registration.prediction_enabled is True
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
    assert smoke_run.dataset.metadata["total_raw_instances"] == 1
    assert smoke_run.dataset.metadata["source_fully_scanned"] is False
    assert smoke_run.dataset.metadata["smoke_round_limit"] == 1
    assert smoke_run.dataset.metadata["smoke_original_turn_count"] > 2
    assert smoke_run.dataset.metadata["smoke_retained_turn_count"] == 2
    assert smoke_run.dataset.metadata["smoke_retained_round_count"] == 1
    assert len(smoke_run.dataset.conversations) == 1
    smoke_conversation = smoke_run.dataset.conversations[0]
    assert sum(len(session.turns) for session in smoke_conversation.sessions) == 2
    assert smoke_conversation.metadata["smoke_retained_round_count"] == 1
    assert smoke_conversation.metadata["smoke_retained_turn_count"] == 2


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
    assert len(smoke_run.dataset.conversations) == 2
    assert smoke_run.dataset.conversations == expected_smoke.conversations
