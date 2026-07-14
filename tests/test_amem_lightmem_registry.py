"""A-Mem 与 LightMem method registry 测试。

本文件只验证官方集成 method 的静态注册和离线 factory 约束，不调用真实 API。
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from memory_benchmark.config import OpenAISettings, load_path_settings
from memory_benchmark.core import Conversation, Session, Turn
from memory_benchmark.methods.amem_adapter import AMemConfig
from memory_benchmark.methods.lightmem_adapter import LightMemConfig
from memory_benchmark.methods import registry as method_registry_module
from memory_benchmark.methods.registry import (
    MethodBuildContext,
    get_method_registration,
    resolve_registered_factory_provenance_granularity,
)


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
    assert registration.provenance_granularity == "turn"
    assert (
        resolve_registered_factory_provenance_granularity(
            registration.system_factory
        )
        == "turn"
    )


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


def test_lightmem_factory_loads_completed_conversations_for_resume(
    tmp_path,
    monkeypatch,
) -> None:
    """LightMem registry factory 应恢复 completed conversations 供后续 question resume。"""

    instances: list[FakeLightMemForFactory] = []

    class FakeLightMemForFactory:
        """替代 LightMem，记录 factory 传入参数和恢复调用。"""

        def __init__(self, **kwargs) -> None:
            """保存构造参数。"""

            self.kwargs = kwargs
            self.loaded_conversations: list[Conversation] = []
            instances.append(self)

        def load_existing_conversation_state(self, conversation: Conversation) -> None:
            """记录恢复请求。"""

            self.loaded_conversations.append(conversation)

    monkeypatch.setattr(method_registry_module, "LightMem", FakeLightMemForFactory)
    conversation = Conversation(
        conversation_id="conv-lightmem",
        sessions=[
            Session(
                session_id="s-1",
                turns=[Turn(turn_id="t-1", speaker="Alice", content="I like tea.")],
            )
        ],
    )
    context = MethodBuildContext(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=5,
            max_workers=1,
            profile_name="smoke",
        ),
        openai_settings=OpenAISettings(
            api_key="sk-test",
            base_url="https://example.invalid/v1",
        ),
        path_settings=replace(
            load_path_settings(Path(__file__).resolve().parents[1]),
            outputs_root=tmp_path,
        ),
        storage_root=tmp_path / "method_state",
        completed_conversations=(conversation,),
    )
    registration = get_method_registration("lightmem")

    system = registration.system_factory(context)

    assert system.kwargs["storage_root"] == tmp_path / "method_state"
    assert [item.conversation_id for item in system.loaded_conversations] == [
        "conv-lightmem"
    ]
