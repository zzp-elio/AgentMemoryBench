"""双轨 readout resolver 与 track identity v1 的离线强反例。"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest

from memory_benchmark.cli.run_prediction import _build_method_manifest
from memory_benchmark.core import (
    AnswerResult,
    ConfigurationError,
    GoldAnswerInfo,
    Question,
)
from memory_benchmark.evaluators.longmemeval_judge import LongMemEvalJudgeEvaluator
from memory_benchmark.evaluators.locomo_judge import LoCoMoJudgeEvaluator
from memory_benchmark.methods.config_track import (
    CONTRACT_VERSION,
    BuildIdentityDeclaration,
    ConfigTrackBundle,
    EmbeddingIdentity,
    TrackIdentity,
    build_native_track_identity,
    build_unified_track_identity,
    resolve_config_track,
)
from memory_benchmark.methods.lightmem_native_prompts import (
    LIGHTMEM_LOCOMO_NATIVE_JUDGE_PROMPT,
)
from memory_benchmark.methods.registry import resolve_registered_build_identity


def _mem0_manifest() -> dict[str, Any]:
    """返回当前受控 MiniLM Mem0 config manifest 片段。"""

    return {
        "embedding_provider": "huggingface",
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
        "embedding_dimensions": 384,
    }


def _lightmem_manifest() -> dict[str, Any]:
    """返回当前 canonical-required LightMem config manifest 片段。"""

    return {
        "embedding_provider": "huggingface-local",
        "embedding_model_path": "models/all-MiniLM-L6-v2",
        "embedding_dimensions": 384,
    }


def _memoryos_manifest() -> dict[str, Any]:
    """返回当前 memoryos-pypi config manifest 片段。"""

    return {
        "engine": "memoryos-pypi",
        "embedding_model_name": "sentence-transformers/all-MiniLM-L6-v2",
    }


def _unified_identity(method: str, manifest: dict[str, Any]) -> TrackIdentity:
    """从注册表单一 build 事实源构造 unified identity。"""

    return build_unified_track_identity(
        build_identity=resolve_registered_build_identity(method, manifest)
    )


def _native_identity(
    method: str,
    benchmark: str,
    manifest: dict[str, Any],
) -> TrackIdentity:
    """从注册 build 声明与 native readout bundle 构造 identity。"""

    bundle = resolve_config_track(method, benchmark, "native")
    assert bundle is not None
    return build_native_track_identity(
        build_identity=resolve_registered_build_identity(method, manifest),
        bundle=bundle,
    )


def test_unified_config_track_returns_no_readout_overrides() -> None:
    """unified 轨必须保持 None 哨兵，build identity 由注册表另行提供。"""

    assert resolve_config_track("lightmem", "locomo", "unified") is None


@pytest.mark.parametrize("benchmark", ("locomo", "longmemeval"))
def test_lightmem_native_config_track_is_readout_only_asset(
    benchmark: str,
) -> None:
    """LightMem bundle 只保存官方 readout 资产，不重复保存 build 身份。"""

    bundle = resolve_config_track("lightmem", benchmark, "native")
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
    assert bundle.judge_source == "official_parity"
    assert bundle.answer_model_source == "official_parity"
    assert bundle.judge_model_source == "official_parity"
    assert not hasattr(bundle, "track_identity")
    assert not hasattr(bundle, "embedding_profile")
    assert not hasattr(bundle, "build_override_applied")
    assert not hasattr(bundle, "declared_unwired_build_reference")
    if benchmark == "locomo":
        assert bundle.judge_profile.prompt_template == LIGHTMEM_LOCOMO_NATIVE_JUDGE_PROMPT
    else:
        assert bundle.judge_profile.evaluator_type is LongMemEvalJudgeEvaluator


@pytest.mark.parametrize("benchmark", ("locomo", "longmemeval", "beam"))
def test_mem0_native_bundle_declares_both_model_overrides(benchmark: str) -> None:
    """Mem0 官方 answer/judge 的 gpt-5 均被全局 gpt-4o-mini 覆盖。"""

    bundle = resolve_config_track("mem0", benchmark, "native")
    assert bundle is not None
    assert bundle.answer_llm_settings.model == "gpt-4o-mini"
    assert bundle.judge_source == "official_parity"
    assert bundle.answer_model_source == "framework_model_override"
    assert bundle.judge_model_source == "framework_model_override"


def test_memoryos_native_bundle_sources_are_two_axis_truthful() -> None:
    """MemoryOS 官方 answer 模型命中 parity，judge 则明确 framework fallback。"""

    bundle = resolve_config_track("memoryos", "locomo", "native")
    assert bundle is not None
    assert bundle.answer_llm_settings.model == "gpt-4o-mini"
    assert bundle.answer_llm_settings.max_tokens == 2000
    assert bundle.judge_profile is None
    assert bundle.judge_source == "framework_fallback"
    assert bundle.answer_model_source == "official_parity"
    assert bundle.judge_model_source == "framework_default"


@pytest.mark.parametrize(
    ("method", "benchmark"),
    (
        ("lightmem", "beam"),
        ("mem0", "membench"),
        ("mem0", "halumem"),
        ("memoryos", "longmemeval"),
    ),
)
def test_native_config_track_rejects_unregistered_grid(
    method: str,
    benchmark: str,
) -> None:
    """未验收 native 的 method×benchmark 格必须 fail-fast。"""

    with pytest.raises(ConfigurationError, match="No native config-track bundle"):
        resolve_config_track(method, benchmark, "native")


def test_config_track_rejects_unknown_track() -> None:
    """配置轨名称只接受 unified/native。"""

    with pytest.raises(ConfigurationError, match="config_track"):
        resolve_config_track("lightmem", "locomo", "paper")


def test_registry_is_single_source_for_current_mem0_and_future_product_config() -> None:
    """Mem0 只按当前 config 分类，未来值未真实出现前不得提前盖 product-default。"""

    controlled = resolve_registered_build_identity("mem0", _mem0_manifest())
    assert controlled.embedding_profile == "controlled_embedding_v1"
    assert controlled.embedding.provider == "huggingface"
    assert controlled.embedding.dimension == 384
    assert controlled.embedding.revision_status == "local_unpinned"

    product = resolve_registered_build_identity(
        "mem0",
        {
            "embedding_provider": "openai",
            "embedding_model": "text-embedding-3-small",
            "embedding_dimensions": 1536,
        },
    )
    assert product.embedding_profile == "product_default_v1"
    assert product.embedding.revision_status == "provider_managed_unpinned"

    unexpected = resolve_registered_build_identity(
        "mem0",
        {
            "embedding_provider": "openai",
            "embedding_model": "text-embedding-3-small",
            "embedding_dimensions": 384,
        },
    )
    assert unexpected.embedding_profile == "unclassified_pending"
    assert unexpected.embedding.identity_status == "pending"


def test_memoryos_unified_identity_is_current_pypi_product_with_real_geometry() -> None:
    """MemoryOS unified 当前运行 pypi 产品，不得误盖 ChromaDB reproduction fork。"""

    identity = _unified_identity("memoryos", _memoryos_manifest())
    assert identity.implementation_variant == "product"
    assert identity.embedding_profile == "product_default_v1"
    assert identity.embedding.provider == "sentence-transformers"
    assert identity.embedding.model == "sentence-transformers/all-MiniLM-L6-v2"
    assert identity.embedding.dimension == 384
    assert identity.embedding.normalization == "external_l2"
    assert identity.embedding.distance == "faiss-inner-product"
    assert identity.readout_track == "unified"
    assert identity.judge_model_source == "framework_default"


def test_memoryos_chromadb_engine_cannot_masquerade_as_product_identity() -> None:
    """ChromaDB 算法 fork 必须另走 reproduction variant，当前注册不得盖 product。"""

    with pytest.raises(ConfigurationError, match="memoryos-pypi"):
        resolve_registered_build_identity(
            "memoryos",
            {
                "engine": "memoryos-chromadb",
                "embedding_model_name": "sentence-transformers/all-MiniLM-L6-v2",
            },
        )


def test_memoryos_native_identity_keeps_product_build_and_fallback_judge() -> None:
    """MemoryOS native 只切 readout，仍是 pypi product build 且 framework judge。"""

    identity = _native_identity("memoryos", "locomo", _memoryos_manifest())
    assert identity.implementation_variant == "product"
    assert identity.readout_track == "native"
    assert identity.native_scope == "readout_only"
    assert identity.build_override_applied is False
    assert identity.embedding.provider == "sentence-transformers"
    assert identity.embedding.normalization == "external_l2"
    assert identity.embedding.distance == "faiss-inner-product"
    assert identity.judge_source == "framework_fallback"
    assert identity.answer_model_source == "official_parity"
    assert identity.judge_model_source == "framework_default"


def test_lightmem_and_mem0_profiles_reflect_current_config() -> None:
    """LightMem 锁 canonical-required；Mem0 仍是 controlled，不提前迁移。"""

    lightmem = _unified_identity("lightmem", _lightmem_manifest())
    mem0 = _unified_identity("mem0", _mem0_manifest())
    assert lightmem.embedding_profile == "product_canonical_required_config_v1"
    assert lightmem.historical_controlled_build_equivalent_to_current_main is True
    assert mem0.embedding_profile == "controlled_embedding_v1"
    assert mem0.historical_controlled_build_equivalent_to_current_main is False


def test_amem_and_simplemem_pending_preserve_known_config_fields() -> None:
    """未审计 method 继续 pending，但不能丢掉 config 已知 provider/model/dimension。"""

    amem = resolve_registered_build_identity(
        "amem",
        {
            "embedding_provider": "sentence-transformers",
            "embedding_model": "all-MiniLM-L6-v2",
        },
    )
    simplemem = resolve_registered_build_identity(
        "simplemem",
        {
            "embedding_provider": "sentence-transformers-local",
            "embedding_model_path": "models/all-MiniLM-L6-v2",
            "embedding_dimension": 384,
        },
    )
    assert amem.embedding_profile == "unclassified_pending"
    assert amem.embedding.provider == "sentence-transformers"
    assert amem.embedding.model == "all-MiniLM-L6-v2"
    assert amem.embedding.dimension is None
    assert amem.embedding.distance is None
    assert amem.embedding.revision_status == "pending"
    assert simplemem.embedding_profile == "unclassified_pending"
    assert simplemem.embedding.provider == "sentence-transformers-local"
    assert simplemem.embedding.model == "models/all-MiniLM-L6-v2"
    assert simplemem.embedding.dimension == 384
    assert simplemem.embedding.distance is None


def test_lightmem_native_locomo_judge_uses_exact_prompt_and_category_skip() -> None:
    """native LoCoMo judge 继续使用逐字 profile，并按官方跳过 category 5。"""

    bundle = resolve_config_track("lightmem", "locomo", "native")
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


def test_track_identity_round_trip_is_strict_and_lossless() -> None:
    """合法 identity 可严格 round-trip，新增 judge model 轴不得丢失。"""

    identity = _native_identity("mem0", "locomo", _mem0_manifest())
    parsed = TrackIdentity.from_manifest_dict(identity.to_manifest_dict())
    assert parsed == identity
    assert parsed.judge_model_source == "framework_model_override"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("implementation_variant", "unknown"),
        ("readout_track", "paper"),
        ("native_scope", "full_native"),
        ("embedding_profile", "repo_default"),
        ("judge_source", "remote"),
        ("answer_model_source", "openai"),
        ("judge_model_source", "openai"),
    ),
)
def test_track_identity_rejects_illegal_literals(field: str, value: Any) -> None:
    """所有 Literal 在运行时从注解单源校验，未知值必须 fail-fast。"""

    base = _native_identity("mem0", "locomo", _mem0_manifest())
    with pytest.raises(ConfigurationError, match="not in"):
        replace(base, **{field: value})


@pytest.mark.parametrize("bad_dimension", (0, -1, True, 3.5, "384"))
def test_embedding_rejects_non_positive_or_non_exact_int_dimension(
    bad_dimension: Any,
) -> None:
    """dimension 必须 type(x) is int 且大于零，bool 不得冒充 1。"""

    embedding = _unified_identity("mem0", _mem0_manifest()).embedding
    with pytest.raises(ConfigurationError, match="dimension"):
        replace(embedding, dimension=bad_dimension)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("provider", ""),
        ("provider", "   "),
        ("model", ""),
        ("model", "\t"),
        ("distance", "unknown"),
    ),
)
def test_embedding_rejects_blank_or_unknown_text(field: str, value: str) -> None:
    """空白 provider/model 与字符串 unknown 都不能冒充已知事实。"""

    embedding = _unified_identity("mem0", _mem0_manifest()).embedding
    with pytest.raises(ConfigurationError):
        replace(embedding, **{field: value})


def test_embedding_rejects_pending_declared_cross_combinations() -> None:
    """pending/declared 的 revision 与 distance 互斥规则必须锁死。"""

    declared = _unified_identity("mem0", _mem0_manifest()).embedding
    with pytest.raises(ConfigurationError, match="pending revision_status"):
        replace(declared, revision_status="pending")
    with pytest.raises(ConfigurationError, match="known distance"):
        replace(declared, distance=None)

    pending = resolve_registered_build_identity(
        "amem",
        {
            "embedding_provider": "sentence-transformers",
            "embedding_model": "all-MiniLM-L6-v2",
        },
    ).embedding
    with pytest.raises(ConfigurationError, match="revision_status='pending'"):
        replace(pending, revision_status="local_unpinned")
    with pytest.raises(ConfigurationError, match="concrete revision"):
        replace(pending, revision="abc")


def test_track_identity_rejects_bool_contract_fields_and_build_override_true() -> None:
    """两个布尔字段必须是 bool，且 v1 只接受 build_override=False。"""

    identity = _native_identity("mem0", "locomo", _mem0_manifest())
    with pytest.raises(ConfigurationError, match="build_override_applied must be bool"):
        replace(identity, build_override_applied=cast(Any, 0))
    with pytest.raises(ConfigurationError, match="does not support build override"):
        replace(identity, build_override_applied=True)
    with pytest.raises(ConfigurationError, match="historical_controlled"):
        replace(
            identity,
            historical_controlled_build_equivalent_to_current_main=cast(Any, 1),
        )


def test_track_identity_parser_rejects_missing_extra_and_illegal_types() -> None:
    """manifest parser 不接受缺键、多余键、dict duck type 或 bool dimension。"""

    raw = _native_identity("mem0", "locomo", _mem0_manifest()).to_manifest_dict()
    missing = dict(raw)
    missing.pop("judge_model_source")
    with pytest.raises(ConfigurationError, match="keys mismatch"):
        TrackIdentity.from_manifest_dict(missing)
    extra = {**raw, "surprise": True}
    with pytest.raises(ConfigurationError, match="keys mismatch"):
        TrackIdentity.from_manifest_dict(extra)
    missing_embedding = {
        **raw,
        "embedding": {**raw["embedding"]},
    }
    missing_embedding["embedding"].pop("instruction")
    with pytest.raises(ConfigurationError, match="keys mismatch"):
        TrackIdentity.from_manifest_dict(missing_embedding)
    extra_embedding = {
        **raw,
        "embedding": {**raw["embedding"], "surprise": True},
    }
    with pytest.raises(ConfigurationError, match="keys mismatch"):
        TrackIdentity.from_manifest_dict(extra_embedding)
    bad_dimension = {**raw, "embedding": {**raw["embedding"], "dimension": True}}
    with pytest.raises(ConfigurationError, match="dimension"):
        TrackIdentity.from_manifest_dict(bad_dimension)
    non_text_key = {**raw, 1: "unexpected"}
    with pytest.raises(ConfigurationError, match="keys must be strings"):
        TrackIdentity.from_manifest_dict(non_text_key)
    with pytest.raises(ConfigurationError, match="must be an object"):
        TrackIdentity.from_manifest_dict(cast(Any, object()))


@pytest.mark.parametrize("bad_literal", (True, [], {}))
def test_track_identity_parser_converts_unhashable_literals_to_domain_error(
    bad_literal: Any,
) -> None:
    """bool/list/dict Literal 输入必须 fail-fast，不能泄漏 Python TypeError。"""

    raw = _native_identity("mem0", "locomo", _mem0_manifest()).to_manifest_dict()
    raw["judge_source"] = bad_literal
    with pytest.raises(ConfigurationError, match="judge_source"):
        TrackIdentity.from_manifest_dict(raw)


def test_unified_identity_rejects_native_sources_and_native_none_scope() -> None:
    """readout_track 与 scope/model 来源的矛盾组合必须 fail-fast。"""

    unified = _unified_identity("mem0", _mem0_manifest())
    with pytest.raises(ConfigurationError, match="framework-default"):
        replace(unified, answer_model_source="official_parity")
    native = _native_identity("mem0", "locomo", _mem0_manifest())
    with pytest.raises(ConfigurationError, match="native_scope"):
        replace(native, native_scope="none")


def test_method_manifest_uses_inner_version_and_rejects_duck_typed_identity() -> None:
    """顶层版本取自已校验对象，不能出现 top=v1/inner=bogus。"""

    identity = _unified_identity("mem0", _mem0_manifest())
    manifest = _build_method_manifest(
        config_manifest={"profile_name": "smoke"},
        source_identity={"source_sha256": "abc"},
        workload_estimate=None,
        track_identity=identity,
    )
    assert manifest["contract_version"] == identity.contract_version
    assert manifest["track_identity"]["contract_version"] == identity.contract_version
    assert manifest["track_identity"]["judge_model_source"] == "framework_default"

    with pytest.raises(ConfigurationError, match="must be TrackIdentity"):
        _build_method_manifest(
            config_manifest={},
            source_identity={},
            workload_estimate=None,
            track_identity=cast(Any, identity.to_manifest_dict()),
        )


def test_method_manifest_without_identity_preserves_legacy_shape() -> None:
    """旧 artifact builder 未传 identity 时继续保留原字节形状。"""

    assert _build_method_manifest(
        config_manifest={"profile_name": "smoke"},
        source_identity={"source_sha256": "abc"},
        workload_estimate=None,
        prompt_track="unified",
    ) == {
        "config": {"profile_name": "smoke"},
        "source": {"source_sha256": "abc"},
        "prompt_track": "unified",
    }


def test_bundle_constructor_rejects_judge_source_profile_contradiction() -> None:
    """native judge 来源与 profile 有无必须在 bundle 构造期一致。"""

    memoryos = resolve_config_track("memoryos", "locomo", "native")
    assert memoryos is not None
    with pytest.raises(ConfigurationError, match="official_parity"):
        replace(memoryos, judge_source="official_parity")
    mem0 = resolve_config_track("mem0", "locomo", "native")
    assert mem0 is not None
    with pytest.raises(ConfigurationError, match="framework_fallback"):
        replace(mem0, judge_source="framework_fallback")


def test_build_declaration_rejects_profile_identity_status_drift() -> None:
    """注册 build profile 与 embedding pending/declared 状态不得漂移。"""

    declared = _unified_identity("mem0", _mem0_manifest()).embedding
    with pytest.raises(ConfigurationError, match="unclassified_pending"):
        BuildIdentityDeclaration(
            implementation_variant="product",
            embedding_profile="unclassified_pending",
            historical_controlled_build_equivalent_to_current_main=False,
            embedding=declared,
        )
