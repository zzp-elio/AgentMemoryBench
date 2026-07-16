"""method 双轨运行配置 resolver 与 track identity 契约 v1 的离线测试。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from memory_benchmark.core import ConfigurationError
from memory_benchmark.evaluators.longmemeval_judge import LongMemEvalJudgeEvaluator
from memory_benchmark.evaluators.locomo_judge import LoCoMoJudgeEvaluator
from memory_benchmark.core import AnswerResult, GoldAnswerInfo, Question
from memory_benchmark.methods.config_track import (
    CONTRACT_VERSION,
    EmbeddingIdentity,
    TrackIdentity,
    build_native_track_identity,
    build_unified_track_identity,
    resolve_config_track,
    validate_embedding_identity,
    validate_track_identity,
)
from memory_benchmark.methods.lightmem_native_prompts import (
    LIGHTMEM_LOCOMO_NATIVE_JUDGE_PROMPT,
)
from memory_benchmark.cli.run_prediction import _build_method_manifest

_MEM0_CONCRETE = ("huggingface", "sentence-transformers/all-MiniLM-L6-v2", 384, None)


def test_unified_config_track_returns_no_overrides() -> None:
    """unified 轨必须以 None 哨兵保持既有路径。"""

    assert resolve_config_track("lightmem", "locomo", "unified") is None


@pytest.mark.parametrize("benchmark", ("locomo", "longmemeval"))
def test_lightmem_native_config_track_resolves_registered_bundle(
    benchmark: str,
) -> None:
    """LightMem 两个官方实验格应解析为完整 native bundle + track identity。"""

    concrete = ("huggingface", "sentence-transformers/all-MiniLM-L6-v2", 384, None)
    bundle = resolve_config_track(
        "lightmem", benchmark, "native", concrete_embedding=concrete
    )

    assert bundle is not None
    assert bundle.answer_prompt_source == "provider_prompt_messages"
    assert bundle.answer_llm_settings.model == "gpt-4o-mini"
    assert bundle.answer_llm_settings.to_manifest_dict() == {
        "message_role": "user",
        "temperature": 0.0,
        "max_tokens": 2000,
        "top_p": 0.8,
        "timeout_seconds": 60.0,
        "max_retries": 8,
    }
    if benchmark == "locomo":
        assert bundle.judge_profile.prompt_template == LIGHTMEM_LOCOMO_NATIVE_JUDGE_PROMPT
    else:
        assert bundle.judge_profile.evaluator_type is LongMemEvalJudgeEvaluator


def test_native_config_track_rejects_unregistered_grid_cell() -> None:
    """single-track 格不得伪造 native bundle。"""

    with pytest.raises(ConfigurationError, match="No native config-track bundle"):
        resolve_config_track("lightmem", "beam", "native")


@pytest.mark.parametrize("benchmark", ("locomo", "longmemeval", "beam"))
def test_mem0_native_config_track_resolves_registered_bundle(benchmark: str) -> None:
    """Mem0 三个官方 harness 格应解析为完整 native bundle + 受控 embedding 身份。"""

    bundle = resolve_config_track(
        "mem0", benchmark, "native", concrete_embedding=_MEM0_CONCRETE
    )

    assert bundle is not None
    assert bundle.answer_prompt_source == "provider_prompt_messages"
    assert bundle.answer_llm_settings.model == "gpt-4o-mini"
    assert bundle.answer_llm_settings.to_manifest_dict() == {
        "message_role": "user",
        "temperature": 0.0,
        "max_tokens": 4096,
        "top_p": None,
        "timeout_seconds": 60.0,
        "max_retries": 8,
    }
    assert bundle.judge_profile.profile_name.startswith(f"mem0_{benchmark}")
    assert bundle.judge_profile.prompt_template
    # 强反例 #4：Mem0 unified/native 的 embedding_profile 必须仍是 controlled，不得提前
    # 冒充 product default（OpenAI/1536 留待迁移卡）。
    assert bundle.embedding_profile == "controlled_embedding_v1"
    assert bundle.declared_unwired_build_reference == "mem0.memory-benchmarks.repo_default"
    assert bundle.build_override_applied is False


@pytest.mark.parametrize("benchmark", ("membench", "halumem"))
def test_mem0_native_config_track_rejects_single_track_grid(
    benchmark: str,
) -> None:
    """Mem0 无官方 harness 的两格必须继续 fail-fast。"""

    with pytest.raises(ConfigurationError, match="No native config-track bundle"):
        resolve_config_track("mem0", benchmark, "native")


def test_memoryos_native_config_track_is_locomo_only_without_native_judge() -> None:
    """MemoryOS 只注册 LoCoMo readout-native，官方无 LLM judge 用 None 表达。"""

    bundle = resolve_config_track(
        "memoryos", "locomo", "native", concrete_embedding=("memoryos-pypi", "sentence-transformers/all-MiniLM-L6-v2", 384, None)
    )

    assert bundle is not None
    assert bundle.answer_prompt_source == "provider_prompt_messages"
    assert bundle.answer_llm_settings.model == "gpt-4o-mini"
    assert bundle.answer_llm_settings.temperature == 0.7
    assert bundle.answer_llm_settings.max_tokens == 2000
    assert bundle.judge_profile is None
    assert bundle.declared_unwired_build_reference == "memoryos.readout-native.build-profile-not-yet-wired"
    with pytest.raises(ConfigurationError, match="No native config-track bundle"):
        resolve_config_track("memoryos", "longmemeval", "native")


def test_config_track_rejects_unknown_track() -> None:
    """配置轨名称只接受政策定义的两个值。"""

    with pytest.raises(ConfigurationError, match="config_track"):
        resolve_config_track("lightmem", "locomo", "paper")


def test_unified_manifest_preserves_byte_shape_and_native_adds_identity() -> None:
    """未传 track_identity 时 manifest 字节不变；native 显式 track identity 落盘。"""

    kwargs = {
        "config_manifest": {"profile_name": "smoke"},
        "source_identity": {"source_sha256": "abc"},
        "workload_estimate": None,
        "answer_reader_manifest": {"answer_protocol": "retrieve_first_v1"},
        "prompt_track": "unified",
    }
    expected_unified = {
        "config": {"profile_name": "smoke"},
        "source": {"source_sha256": "abc"},
        "answer_reader": {"answer_protocol": "retrieve_first_v1"},
        "prompt_track": "unified",
    }

    assert _build_method_manifest(**kwargs) == expected_unified
    assert _build_method_manifest(
        **{**kwargs, "prompt_track": "native"}, config_track="native"
    ) == {
        **expected_unified,
        "prompt_track": "native",
        "config_track": "native",
    }


def test_lightmem_native_locomo_judge_uses_exact_prompt_and_category_skip() -> None:
    """native LoCoMo judge 应使用逐字 profile，并按官方跳过 category 5。"""

    bundle = resolve_config_track(
        "lightmem", "locomo", "native", concrete_embedding=("huggingface", "sentence-transformers/all-MiniLM-L6-v2", 384, None)
    )
    assert bundle is not None
    profile = bundle.judge_profile
    evaluator = LoCoMoJudgeEvaluator(
        mode="compact",
        prompt_template_override=profile.prompt_template,
        skipped_categories=profile.skipped_categories,
        prompt_profile_override=profile.profile_name,
    )
    question = Question("q1", "c1", "What happened?", category="1")

    assert evaluator.build_prompt(
        question,
        AnswerResult("q1", "c1", "generated"),
        GoldAnswerInfo("q1", "gold"),
    ) == LIGHTMEM_LOCOMO_NATIVE_JUDGE_PROMPT.format(
        question="What happened?",
        gold_answer="gold",
        generated_answer="generated",
    )
    assert evaluator.should_skip_category(5) is True
    assert evaluator.should_skip_category("5") is True
    assert evaluator.should_skip_category(4) is False


# ---------------------------------------------------------------------------
# 强反例：track identity 契约
# ---------------------------------------------------------------------------


def test_mem0_native_identity_is_readout_only_minilm_with_model_override() -> None:
    """强反例 #1：Mem0 native 必须是 readout_only + controlled MiniLM + override。"""

    identity = build_native_track_identity(
        method="mem0",
        benchmark="locomo",
        concrete_embedding=_MEM0_CONCRETE,
        judge_profile=object(),  # 非 None → official_parity
    )

    assert identity.contract_version == CONTRACT_VERSION
    assert identity.readout_track == "native"
    assert identity.native_scope == "readout_only"
    assert identity.build_override_applied is False
    assert identity.implementation_variant == "product"
    assert identity.embedding_profile == "controlled_embedding_v1"
    assert identity.embedding.provider == "huggingface"
    assert identity.embedding.model == "sentence-transformers/all-MiniLM-L6-v2"
    assert identity.embedding.dimension == 384
    assert identity.embedding.identity_status == "declared"
    # MetalMo 官方 gpt-5 被项目 gpt-4o-mini 锁覆盖。
    assert identity.answer_model_source == "framework_model_override"
    assert identity.judge_source == "official_parity"


def test_memoryos_native_identity_marks_judge_framework_fallback() -> None:
    """强反例 #2：MemoryOS native judge_source 必须显式 framework_fallback。"""

    identity = build_native_track_identity(
        method="memoryos",
        benchmark="locomo",
        concrete_embedding=("memoryos-pypi", "sentence-transformers/all-MiniLM-L6-v2", 384, None),
        judge_profile=None,
    )

    assert identity.judge_source == "framework_fallback"
    assert identity.answer_model_source == "framework_default"
    assert identity.embedding_profile == "product_default_v1"
    assert identity.historical_controlled_build_equivalent_to_current_main is True


def test_lightmem_unified_identity_is_canonical_required_config() -> None:
    """强反例 #3：LightMem unified profile 是 product canonical required config，非 repo default。"""

    identity = build_unified_track_identity(
        method="lightmem",
        concrete_embedding=("huggingface-local", "sentence-transformers/all-MiniLM-L6-v2", 384, None),
    )

    assert identity.readout_track == "unified"
    assert identity.native_scope == "none"
    assert identity.embedding_profile == "product_canonical_required_config_v1"
    assert identity.answer_model_source == "framework_default"
    assert identity.judge_source == "framework_default"


def test_mem0_unified_identity_is_controlled_not_product_default() -> None:
    """强反例 #4：Mem0 unified 必须仍是 controlled，不能提前冒充 product default。"""

    identity = build_unified_track_identity(
        method="mem0", concrete_embedding=_MEM0_CONCRETE
    )

    assert identity.embedding_profile == "controlled_embedding_v1"
    assert identity.historical_controlled_build_equivalent_to_current_main is False


def test_amem_and_simplemem_unified_identity_stays_pending() -> None:
    """强反例 #5：A-Mem/SimpleMem 不因同名 MiniLM 自动盖 product-default。"""

    for method in ("amem", "simplemem"):
        identity = build_unified_track_identity(
            method=method,
            concrete_embedding=None,
        )
        assert identity.embedding_profile == "unclassified_pending"
        assert identity.embedding.identity_status == "pending"
        assert identity.embedding.model is None
        assert identity.embedding.dimension is None

    # 即使传入同名 MiniLM concrete，未裁 method 仍不盖 product-default（embedding_profile
    # 由方法预设期望决定，不由 concrete 推断）。
    amem = build_unified_track_identity(
        method="amem",
        concrete_embedding=("huggingface", "sentence-transformers/all-MiniLM-L6-v2", 384, None),
    )
    assert amem.embedding_profile == "unclassified_pending"
    assert amem.embedding.identity_status == "declared"
    assert amem.embedding.model == "sentence-transformers/all-MiniLM-L6-v2"


@pytest.mark.parametrize(
    "bad_identity_field",
    [
        {"implementation_variant": "unknown"},
        {"readout_track": "paper"},
        {"native_scope": "full_native"},
        {"embedding_profile": "repo_default"},
        {"judge_source": "remote"},
        {"answer_model_source": "openai"},
    ],
)
def test_track_identity_rejects_illegal_enums(bad_identity_field: dict) -> None:
    """强反例 #6：非法枚举值必须 fail-fast。"""

    base = TrackIdentity(
        contract_version=CONTRACT_VERSION,
        implementation_variant="product",
        readout_track="native",
        native_scope="readout_only",
        build_override_applied=False,
        embedding_profile="controlled_embedding_v1",
        historical_controlled_build_equivalent_to_current_main=False,
        embedding=EmbeddingIdentity(
            provider="huggingface",
            model="sentence-transformers/all-MiniLM-L6-v2",
            dimension=384,
            revision=None,
            revision_status="local_unpinned",
            normalization=None,
            instruction=None,
            distance="qdrant-cosine",
            identity_status="declared",
        ),
        judge_source="official_parity",
        answer_model_source="framework_model_override",
    )
    with pytest.raises(ConfigurationError, match="not in"):
        validate_track_identity(replace(base, **bad_identity_field))


def test_embedding_identity_rejects_empty_model_and_dimension_below_one() -> None:
    """强反例 #6 续：空 model / dimension<=0 必须拒绝。"""

    with pytest.raises(ConfigurationError, match="non-empty model"):
        validate_embedding_identity(
            EmbeddingIdentity(
                provider="huggingface",
                model="",
                dimension=384,
                revision=None,
                revision_status="local_unpinned",
                normalization=None,
                instruction=None,
                distance="qdrant-cosine",
                identity_status="declared",
            )
        )
    with pytest.raises(ConfigurationError, match="dimension"):
        raw = (
            "huggingface",
            "sentence-transformers/all-MiniLM-L6-v2",
            0,
            None,
        )
        identity = build_native_track_identity(
            method="mem0",
            benchmark="locomo",
            concrete_embedding=raw,
            judge_profile=object(),
        )
        # build 内 validate 已触发
        assert False  # pragma: no cover - should not reach


def test_native_readout_with_none_scope_is_rejected() -> None:
    """强反例 #6 续：native readout 配 native_scope=none 必须互斥拒绝。"""

    base = build_native_track_identity(
        method="mem0",
        benchmark="locomo",
        concrete_embedding=_MEM0_CONCRETE,
        judge_profile=object(),
    )
    with pytest.raises(ConfigurationError, match="native_scope"):
        validate_track_identity(replace(base, native_scope="none"))


def test_unified_manifest_includes_explicit_track_identity_and_contract_version() -> None:
    """新 run manifest 必须显式写 readout_track=unified + track_identity + contract_version。"""

    identity = build_unified_track_identity(method="mem0", concrete_embedding=_MEM0_CONCRETE)
    manifest = _build_method_manifest(
        config_manifest={"profile_name": "smoke"},
        source_identity={"source_sha256": "abc"},
        workload_estimate=None,
        track_identity=identity,
    )

    assert manifest["contract_version"] == CONTRACT_VERSION
    assert manifest["track_identity"]["contract_version"] == CONTRACT_VERSION
    assert manifest["track_identity"]["readout_track"] == "unified"
    assert manifest["track_identity"]["native_scope"] == "none"
    assert manifest["track_identity"]["embedding"]["dimension"] == 384