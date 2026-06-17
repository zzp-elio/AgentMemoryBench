"""A-Mem 与 LightMem method registry 测试。

本文件只验证官方集成 method 的静态注册和离线 factory 约束，不调用真实 API。
"""

from __future__ import annotations

from memory_benchmark.methods.amem_adapter import AMemConfig
from memory_benchmark.methods.lightmem_adapter import LightMemConfig
from memory_benchmark.methods.registry import get_method_registration


def test_amem_is_registered_for_conversation_qa() -> None:
    """A-Mem 应作为 conversation-QA 官方 method 注册。"""

    registration = get_method_registration("amem")

    assert registration.name == "amem"
    assert registration.display_name == "A-Mem"
    assert "smoke" in registration.profile_names
    assert "official-full" in registration.profile_names
    assert registration.requires_api is True


def test_amem_registration_exposes_efficiency_contract() -> None:
    """A-Mem 启用效率观测时应声明 retrieval 可拆分。"""

    registration = get_method_registration("amem")
    config = AMemConfig(
        llm_model="gpt-4o-mini",
        embedding_model="all-MiniLM-L6-v2",
        retrieve_k=3,
        max_workers=1,
        profile_name="smoke",
    )

    assert registration.retrieval_observation_contract_getter is not None
    contract = registration.retrieval_observation_contract_getter(config)

    assert contract.required_by_profile is True
    assert contract.supported_by_method is True


def test_lightmem_is_registered_for_conversation_qa() -> None:
    """LightMem 应作为 conversation-QA 官方 method 注册。"""

    registration = get_method_registration("lightmem")

    assert registration.name == "lightmem"
    assert registration.display_name == "LightMem"
    assert "smoke" in registration.profile_names
    assert "official-full" in registration.profile_names
    assert registration.requires_api is True


def test_lightmem_registration_exposes_efficiency_contract() -> None:
    """LightMem 启用效率观测时应声明 retrieval 可拆分。"""

    registration = get_method_registration("lightmem")
    config = LightMemConfig(
        llm_model="gpt-4o-mini",
        embedding_model_path="models/all-MiniLM-L6-v2",
        llmlingua_model_path=(
            "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
        ),
        retrieve_limit=5,
        max_workers=1,
        profile_name="smoke",
    )

    assert registration.retrieval_observation_contract_getter is not None
    contract = registration.retrieval_observation_contract_getter(config)

    assert contract.required_by_profile is True
    assert contract.supported_by_method is True
