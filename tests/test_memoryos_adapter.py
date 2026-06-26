"""测试 MemoryOS LoCoMo 论文配置适配器。

本文件只做不访问真实 LLM 的单元测试：确认 MemoryOS wrapper 的论文默认配置、
conversation 到官方 eval page 的转换、add 写入行为，以及未写入 conversation 时
get_answer 的强约束报错。
"""

from __future__ import annotations

from dataclasses import asdict
from functools import partial
import json
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from openai import APITimeoutError

from memory_benchmark.config.settings import AppSettings, OpenAISettings, PathSettings
from memory_benchmark.core import Conversation, GoldAnswerInfo, Question, Session, Turn
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.methods import build_memoryos_source_identity
from memory_benchmark.methods import memoryos_adapter as memoryos_adapter_module
from memory_benchmark.methods.memoryos_adapter import (
    MemoryOS,
    MemoryOSPaperConfig,
    clean_memoryos_conversation_state,
)
from memory_benchmark.observability.efficiency import EfficiencyCollector


pytestmark = [pytest.mark.integration, pytest.mark.memoryos]


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_small_conversation() -> Conversation:
    """构造一个短 conversation，保证 add 阶段不会触发 LLM 更新。

    输入:
        无。

    输出:
        Conversation: 含两个 user/assistant round、一个公开问题和一个私有 gold。
    """

    question = Question(
        question_id="conv-test:q1",
        conversation_id="conv-test",
        text="Where did Alice move?",
        category="2",
    )
    return Conversation(
        conversation_id="conv-test",
        sessions=[
            Session(
                session_id="session_1",
                session_time="2024-01-01",
                turns=[
                    Turn(turn_id="D1:1", speaker="Alice", content="I moved to Seattle."),
                    Turn(turn_id="D1:2", speaker="Bob", content="Seattle sounds great."),
                    Turn(turn_id="D1:3", speaker="Alice", content="I adopted a cat."),
                    Turn(turn_id="D1:4", speaker="Bob", content="That is lovely."),
                ],
            )
        ],
        questions=[question],
        gold_answers={
            question.question_id: GoldAnswerInfo(
                question_id=question.question_id,
                answer="Seattle",
                evidence=["D1:1"],
            )
        },
        metadata={"speaker_a": "Alice", "speaker_b": "Bob"},
    )


def test_clean_memoryos_conversation_state_only_removes_target_directory(
    tmp_path: Path,
) -> None:
    """MemoryOS clean retry 只能删除目标 conversation 的状态目录。

    输入:
        storage_root: 同时包含目标 conversation state 和 sibling state。

    输出:
        目标目录被删除，其他 conversation 的目录保持不变。
    """

    target_state = tmp_path / "conv_1"
    sibling_state = tmp_path / "conv-2"
    target_state.mkdir()
    sibling_state.mkdir()
    (target_state / "short_term.json").write_text("[]", encoding="utf-8")
    (sibling_state / "short_term.json").write_text("[]", encoding="utf-8")

    clean_memoryos_conversation_state(tmp_path, "conv/1")

    assert not target_state.exists()
    assert sibling_state.exists()


def build_longmemeval_conversation() -> Conversation:
    """构造 LongMemEval 风格 conversation。

    输入:
        无。

    输出:
        Conversation: 一个 LongMemEval instance 映射成的 conversation；speaker 使用
        `user` / `assistant`，haystack date 放在 `session_time`，question date 放在
        `question_time`。
    """

    question = Question(
        question_id="lme:q1",
        conversation_id="lme:q1",
        text="What drink does the user prefer?",
        question_time="2026-01-04",
        category="single-session-user",
        metadata={"source_format": "longmemeval"},
    )
    return Conversation(
        conversation_id="lme:q1",
        sessions=[
            Session(
                session_id="haystack-1",
                session_time="2026-01-01",
                turns=[
                    Turn(turn_id="haystack-1:t0", speaker="user", content="I prefer jasmine tea."),
                    Turn(turn_id="haystack-1:t1", speaker="assistant", content="I will remember that."),
                ],
                metadata={"source_format": "longmemeval_haystack_session"},
            )
        ],
        questions=[question],
        gold_answers={
            question.question_id: GoldAnswerInfo(
                question_id=question.question_id,
                answer="jasmine tea",
                evidence=["haystack-1"],
            )
        },
        metadata={"source_path": "data/longmemeval/longmemeval_s_cleaned.json"},
    )


class MemoryOSAdapterTests(unittest.TestCase):
    """验证 MemoryOS wrapper 的核心无网络行为。"""

    def test_default_config_uses_paper_settings(self):
        """默认配置应优先遵循 MemoryOS 论文中的 LoCoMo 实验设置。"""

        config = MemoryOSPaperConfig()

        self.assertEqual(config.llm_model, "gpt-4o-mini")
        self.assertEqual(config.embedding_model_name, "sentence-transformers/all-MiniLM-L6-v2")
        self.assertEqual(config.short_term_capacity, 7)
        self.assertEqual(config.mid_term_capacity, 200)
        self.assertEqual(config.long_term_knowledge_capacity, 100)
        self.assertEqual(config.heat_threshold, 5.0)
        self.assertEqual(config.topic_similarity_threshold, 0.6)
        self.assertEqual(config.retrieval_top_m_segments, 5)
        self.assertEqual(config.retrieval_queue_capacity, 10)

    def test_config_does_not_expose_unused_generation_parameters(self):
        """配置对象不应暴露 MemoryOS 官方代码已内置的生成参数。"""

        config = MemoryOSPaperConfig()

        self.assertFalse(hasattr(config, "final_answer_temperature"))
        self.assertFalse(hasattr(config, "final_answer_max_tokens"))

    def test_conversation_to_memory_pages_pairs_turns_by_speaker(self):
        """conversation 应按 speaker_a -> speaker_b 转成 MemoryOS 官方 QA page。"""

        conversation = build_small_conversation()

        pages = MemoryOS.conversation_to_memory_pages(conversation)

        self.assertEqual(
            pages,
            [
                {
                    "user_input": "I moved to Seattle.",
                    "agent_response": "Seattle sounds great.",
                    "timestamp": "2024-01-01",
                },
                {
                    "user_input": "I adopted a cat.",
                    "agent_response": "That is lovely.",
                    "timestamp": "2024-01-01",
                },
            ],
        )

    def test_add_writes_public_conversation_pages_without_gold(self):
        """add 应只写公开对话 page，不把 gold answer/evidence 写入 MemoryOS 状态。"""

        conversation = build_small_conversation()
        with tempfile.TemporaryDirectory() as temp_dir:
            system = MemoryOS(
                openai_api_key="unit-test-key",
                openai_base_url="https://example.invalid/v1",
                storage_root=Path(temp_dir),
            )

            result = system.add([conversation])

            self.assertEqual(result.conversation_ids, ["conv-test"])
            state = system.get_debug_state("conv-test")
            short_term_pages = state.short_memory.get_all()
            self.assertEqual(len(short_term_pages), 2)
            self.assertNotIn("answer", short_term_pages[0])
            self.assertNotIn("gold_answer", short_term_pages[0])
            self.assertNotIn("evidence", str(short_term_pages))
            self.assertEqual(short_term_pages[0]["user_input"], "I moved to Seattle.")

    def test_get_answer_requires_conversation_to_be_added_first(self):
        """get_answer 在 conversation_id 未写入时必须报配置错误。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            system = MemoryOS(
                openai_api_key="unit-test-key",
                openai_base_url="https://example.invalid/v1",
                storage_root=Path(temp_dir),
            )
            question = Question(
                question_id="missing:q1",
                conversation_id="missing",
                text="What does Alice remember?",
            )

            with self.assertRaises(ConfigurationError):
                system.get_answer(question)

    def test_retrieve_formats_retrieval_queue_and_knowledge(self):
        """retrieve 应返回 framework reader 可用的 MemoryOS 检索上下文。"""

        conversation = build_small_conversation()
        with tempfile.TemporaryDirectory() as temp_dir:
            system = MemoryOS(
                openai_api_key="unit-test-key",
                openai_base_url="https://example.invalid/v1",
                storage_root=Path(temp_dir),
            )
            system.add([conversation])
            state = system.get_debug_state(conversation.conversation_id)

            def fake_retrieve(*_: object, **__: object) -> dict[str, object]:
                """返回固定检索结果，避免调用官方检索 LLM。"""

                return {
                    "retrieval_queue": [
                        {
                            "user_input": "Alice likes tea.",
                            "agent_response": "Tea preference noted.",
                        }
                    ],
                    "long_term_knowledge": ["Alice likes tea."],
                }

            state.retrieval_system.retrieve = fake_retrieve

            retrieval = system.retrieve(conversation.questions[0])

        self.assertEqual(retrieval.question_id, "conv-test:q1")
        self.assertEqual(retrieval.conversation_id, "conv-test")
        self.assertEqual(
            [message.role for message in retrieval.prompt_messages],
            ["system", "user"],
        )
        self.assertIn("role-playing", retrieval.prompt_messages[0].content)
        self.assertIn("<MEMORY>", retrieval.answer_prompt)
        self.assertIn("【Historical Memory】", retrieval.answer_prompt)
        self.assertIn("Alice likes tea.", retrieval.answer_prompt)
        self.assertIn("Alice likes tea.", retrieval.metadata["answer_context"])
        self.assertEqual(retrieval.metadata["method"], "MemoryOS")
        self.assertEqual(retrieval.metadata["retrieved_page_count"], 1)
        self.assertEqual(retrieval.metadata["retrieved_knowledge_count"], 1)

    def test_longmemeval_retrieve_preserves_memoryos_context_sections(self):
        """LongMemEval prompt 不能丢掉 MemoryOS 的短中长期记忆上下文。

        MemoryOS 的核心不是单一 retrieval string；LongMemEval reader prompt 必须保留
        recent short memory、retrieval queue、user profile、long-term knowledge 和
        assistant knowledge，再使用 LightMem-style question_time 入口。
        """

        conversation = build_longmemeval_conversation()
        with tempfile.TemporaryDirectory() as temp_dir:
            system = MemoryOS(
                openai_api_key="unit-test-key",
                openai_base_url="https://example.invalid/v1",
                storage_root=Path(temp_dir),
            )
            system.add(conversation)
            state = system.get_debug_state(conversation.conversation_id)
            state.long_memory.user_profiles[conversation.conversation_id] = {
                "data": "User profile says the user prefers tea.",
                "last_updated": "2026-01-02",
            }
            state.long_memory.assistant_knowledge.append(
                {
                    "knowledge": "I should answer drink questions concisely.",
                    "timestamp": "2026-01-02",
                }
            )

            def fake_retrieve(*_: object, **__: object) -> dict[str, object]:
                """返回固定检索结果，避免调用官方检索 LLM。"""

                return {
                    "retrieval_queue": [
                        {
                            "user_input": "The user ordered jasmine tea.",
                            "agent_response": "Tea preference noted.",
                            "timestamp": "2026-01-03",
                            "meta_info": "drink preference chain",
                        }
                    ],
                    "long_term_knowledge": [
                        {"knowledge": "Long-term knowledge: user avoids coffee."}
                    ],
                }

            state.retrieval_system.retrieve = fake_retrieve

            retrieval = system.retrieve(conversation.questions[0])

        self.assertEqual(
            [message.role for message in retrieval.prompt_messages],
            ["system", "user"],
        )
        self.assertEqual(
            retrieval.prompt_messages[0].content,
            "You are a helpful assistant.",
        )
        user_prompt = retrieval.prompt_messages[1].content
        self.assertIn(
            "Question time:2026-01-04 and question:What drink does the user prefer?",
            user_prompt,
        )
        self.assertIn("Please answer the question based on the following memories:", user_prompt)
        self.assertIn("<CONTEXT>", user_prompt)
        self.assertIn("user: I prefer jasmine tea.", user_prompt)
        self.assertIn("<MEMORY>", user_prompt)
        self.assertIn("The user ordered jasmine tea.", user_prompt)
        self.assertIn("drink preference chain", user_prompt)
        self.assertIn("<CHARACTER TRAITS>", user_prompt)
        self.assertIn("user profile says the user prefers tea.", user_prompt)
        self.assertIn("Long-term knowledge: user avoids coffee.", user_prompt)
        self.assertIn("<ASSISTANT KNOWLEDGE>", user_prompt)
        self.assertIn("assistant should answer drink questions concisely.", user_prompt)
        self.assertEqual(
            retrieval.metadata["answer_prompt_profile"],
            "lightmem_longmemeval_reader_v1",
        )
        self.assertIn(
            "user profile says the user prefers tea.",
            retrieval.metadata["answer_context"],
        )
        self.assertIn("The user ordered jasmine tea.", retrieval.metadata["answer_context"])

    def test_longmemeval_retrieve_can_use_memoryos_pypi_generic_prompt(self):
        """MemoryOS 可选 PyPI generic prompt profile 应保留完整记忆上下文。

        该 profile 不替代默认 LightMem-style LongMemEval QA prompt，只作为
        MemoryOS-native 通用会话 prompt 的可选对照。
        """

        conversation = build_longmemeval_conversation()
        with tempfile.TemporaryDirectory() as temp_dir:
            system = MemoryOS(
                openai_api_key="unit-test-key",
                openai_base_url="https://example.invalid/v1",
                storage_root=Path(temp_dir),
                config=MemoryOSPaperConfig(
                    longmemeval_prompt_profile="memoryos_pypi_generic_v1"
                ),
            )
            system.add(conversation)
            state = system.get_debug_state(conversation.conversation_id)
            state.long_memory.user_profiles[conversation.conversation_id] = {
                "data": "User profile says the user prefers jasmine tea.",
                "last_updated": "2026-01-02",
            }
            state.long_memory.assistant_knowledge.append(
                {
                    "knowledge": "I should answer drink questions concisely.",
                    "timestamp": "2026-01-02",
                }
            )

            def fake_retrieve(*_: object, **__: object) -> dict[str, object]:
                """返回固定检索结果，避免调用官方检索 LLM。"""

                return {
                    "retrieval_queue": [
                        {
                            "user_input": "The user ordered jasmine tea.",
                            "agent_response": "Tea preference noted.",
                            "timestamp": "2026-01-03",
                            "meta_info": "drink preference chain",
                        }
                    ],
                    "long_term_knowledge": [
                        {"knowledge": "Long-term knowledge: user avoids coffee."}
                    ],
                }

            state.retrieval_system.retrieve = fake_retrieve

            retrieval = system.retrieve(conversation.questions[0])

        self.assertEqual(
            [message.role for message in retrieval.prompt_messages],
            ["system", "user"],
        )
        self.assertIn(
            "As a communication expert",
            retrieval.prompt_messages[0].content,
        )
        self.assertIn("role of assistant", retrieval.prompt_messages[0].content)
        self.assertIn("User's profile:", retrieval.prompt_messages[0].content)
        user_prompt = retrieval.prompt_messages[1].content
        self.assertIn("<CONTEXT>", user_prompt)
        self.assertIn("I prefer jasmine tea.", user_prompt)
        self.assertIn("<MEMORY>", user_prompt)
        self.assertIn("The user ordered jasmine tea.", user_prompt)
        self.assertIn("drink preference chain", user_prompt)
        self.assertIn("<USER TRAITS>", user_prompt)
        self.assertIn("Long-term knowledge: user avoids coffee.", user_prompt)
        self.assertIn("The user just said:", user_prompt)
        self.assertIn(
            "Question time:2026-01-04 and question:What drink does the user prefer?",
            user_prompt,
        )
        self.assertEqual(
            retrieval.metadata["answer_prompt_profile"],
            "memoryos_pypi_generic_v1",
        )
        self.assertIn(
            "user profile says the user prefers jasmine tea.",
            retrieval.metadata["answer_context"],
        )

    def test_estimate_add_workload_counts_pages_and_update_batches(self):
        """add 前应能估算 page 数和会触发的 MemoryOS 更新批次数。"""

        conversation = build_small_conversation()

        default_estimate = MemoryOS.estimate_add_workload(conversation, MemoryOSPaperConfig())
        small_capacity_estimate = MemoryOS.estimate_add_workload(
            conversation,
            MemoryOSPaperConfig(short_term_capacity=2),
        )

        self.assertEqual(default_estimate.page_count, 2)
        self.assertEqual(default_estimate.update_batch_count, 0)
        self.assertEqual(default_estimate.remaining_short_term_pages, 2)
        self.assertFalse(default_estimate.will_trigger_updates)
        self.assertEqual(small_capacity_estimate.page_count, 2)
        self.assertEqual(small_capacity_estimate.update_batch_count, 1)
        self.assertEqual(small_capacity_estimate.remaining_short_term_pages, 1)
        self.assertTrue(small_capacity_estimate.will_trigger_updates)

    def test_estimate_add_workload_matches_official_one_page_eviction_loop(self):
        """估算应匹配 MemoryOS 官方满队列后每次只淘汰一页的行为。"""

        conversation = build_small_conversation()
        conversation.sessions[0].turns.extend(
            [
                Turn(turn_id="D1:5", speaker="Alice", content="I joined a club."),
                Turn(turn_id="D1:6", speaker="Bob", content="That club sounds fun."),
            ]
        )

        estimate = MemoryOS.estimate_add_workload(
            conversation,
            MemoryOSPaperConfig(short_term_capacity=2),
        )

        self.assertEqual(estimate.page_count, 3)
        self.assertEqual(estimate.update_batch_count, 2)
        self.assertEqual(estimate.remaining_short_term_pages, 1)
        self.assertTrue(estimate.will_trigger_updates)

    def test_default_storage_root_is_unique_per_instance(self):
        """默认 storage_root 应按实例隔离，避免不同 run 复用同一 JSON 状态。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            fake_settings = _build_fake_settings(Path(temp_dir))

            with patch(
                "memory_benchmark.methods.memoryos_adapter.load_path_settings",
                return_value=fake_settings.paths,
            ):
                first = MemoryOS(
                    openai_api_key="unit-test-key",
                    openai_base_url="https://example.invalid/v1",
                )
                second = MemoryOS(
                    openai_api_key="unit-test-key",
                    openai_base_url="https://example.invalid/v1",
                )

        self.assertNotEqual(first.storage_root, second.storage_root)
        self.assertTrue(str(first.storage_root).startswith(str(Path(temp_dir).resolve())))
        self.assertTrue(str(second.storage_root).startswith(str(Path(temp_dir).resolve())))

    def test_manual_api_key_still_uses_configured_base_url_when_base_url_is_omitted(self):
        """调用方只传 api key 时，base_url 仍应从配置层读取。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            fake_settings = _build_fake_settings(Path(temp_dir))

            with patch(
                "memory_benchmark.methods.memoryos_adapter.load_settings",
                return_value=fake_settings,
            ):
                system = MemoryOS(openai_api_key="manual-key")

        self.assertEqual(system.openai_api_key, "manual-key")
        self.assertEqual(system.openai_base_url, "https://configured.example/v1")

    def test_eval_modules_are_isolated_between_memoryos_instances(self):
        """每个 MemoryOS 实例应持有独立 eval module，避免跨实例 monkeypatch 污染。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            first = MemoryOS(
                openai_api_key="first-key",
                openai_base_url="https://first.example/v1",
                storage_root=Path(temp_dir) / "first",
            )
            second = MemoryOS(
                openai_api_key="second-key",
                openai_base_url="https://second.example/v1",
                storage_root=Path(temp_dir) / "second",
            )

        self.assertIsNot(first.get_debug_modules().utils, second.get_debug_modules().utils)
        self.assertIs(first.get_debug_modules().utils.get_embedding.__self__, first)
        self.assertIs(second.get_debug_modules().utils.get_embedding.__self__, second)

    def test_load_eval_modules_resolves_eval_dir_via_path_settings(self):
        """官方 eval 目录必须经由 PathSettings resolver 解析，避免硬编码源码位置。"""

        fake_path_settings = _build_fake_settings(PROJECT_ROOT / "outputs").paths
        expected_eval_dir = PROJECT_ROOT / "third_party" / "methods" / "MemoryOS-main" / "eval"
        original_resolver = PathSettings.resolve_third_party_method_path

        with patch.object(
            PathSettings,
            "resolve_third_party_method_path",
            autospec=True,
            wraps=original_resolver,
        ) as resolver:
            with tempfile.TemporaryDirectory() as temp_dir:
                with patch(
                    "memory_benchmark.methods.memoryos_adapter.load_path_settings",
                    return_value=fake_path_settings,
                ):
                    MemoryOS(
                        openai_api_key="unit-test-key",
                        openai_base_url="https://example.invalid/v1",
                        storage_root=Path(temp_dir),
                    )

        resolver.assert_any_call(fake_path_settings, "MemoryOS-main", "eval")
        self.assertTrue(expected_eval_dir.is_dir())

    def test_load_existing_conversation_state_attaches_without_duplicate_add(self):
        """已写入的 conversation 状态应能重新 attach，且不会重复写入 page。"""

        conversation = build_small_conversation()
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_root = Path(temp_dir) / "memoryos_state"
            first = MemoryOS(
                openai_api_key="unit-test-key",
                openai_base_url="https://example.invalid/v1",
                storage_root=storage_root,
            )
            first.add([conversation])

            second = MemoryOS(
                openai_api_key="unit-test-key",
                openai_base_url="https://example.invalid/v1",
                storage_root=storage_root,
            )
            second.load_existing_conversation_state(conversation)

            state = second.get_debug_state(conversation.conversation_id)
            self.assertEqual(len(state.short_memory.get_all()), 2)

    def test_load_existing_conversation_state_requires_short_term_file(self):
        """attach 已有状态时至少应存在 short_term.json，否则说明 add 未完成。"""

        conversation = build_small_conversation()
        with tempfile.TemporaryDirectory() as temp_dir:
            system = MemoryOS(
                openai_api_key="unit-test-key",
                openai_base_url="https://example.invalid/v1",
                storage_root=Path(temp_dir),
            )

            with self.assertRaises(ConfigurationError):
                system.load_existing_conversation_state(conversation)

    def test_load_existing_conversation_state_accepts_short_only_state_without_updates(self):
        """未触发 MemoryOS 更新的短对话只保留 short_term.json 也应允许 attach。"""

        conversation = build_small_conversation()
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_root = Path(temp_dir)
            state_dir = storage_root / conversation.conversation_id
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / "short_term.json").write_text("[]", encoding="utf-8")

            system = MemoryOS(
                openai_api_key="unit-test-key",
                openai_base_url="https://example.invalid/v1",
                storage_root=storage_root,
            )

            system.load_existing_conversation_state(conversation)

            state = system.get_debug_state(conversation.conversation_id)
            self.assertEqual(state.storage_dir.resolve(), state_dir.resolve())

    def test_load_existing_conversation_state_rejects_corrupted_short_term_json(self):
        """short_term.json 损坏时必须拒绝 attach。"""

        conversation = build_small_conversation()
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_root = Path(temp_dir)
            state_dir = storage_root / conversation.conversation_id
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / "short_term.json").write_text("{bad json", encoding="utf-8")

            system = MemoryOS(
                openai_api_key="unit-test-key",
                openai_base_url="https://example.invalid/v1",
                storage_root=storage_root,
            )

            with self.assertRaises(ConfigurationError):
                system.load_existing_conversation_state(conversation)

    def test_load_existing_conversation_state_rejects_non_utf8_short_term_json(self):
        """short_term.json 不是 UTF-8 时也必须包装成配置错误。"""

        conversation = build_small_conversation()
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_root = Path(temp_dir)
            state_dir = storage_root / conversation.conversation_id
            state_dir.mkdir(parents=True, exist_ok=True)
            short_term_path = state_dir / "short_term.json"
            short_term_path.write_bytes(b"\xff\xfe\xfd")

            system = MemoryOS(
                openai_api_key="unit-test-key",
                openai_base_url="https://example.invalid/v1",
                storage_root=storage_root,
            )

            with self.assertRaises(ConfigurationError) as error:
                system.load_existing_conversation_state(conversation)

        self.assertIn("short_term.json", str(error.exception))
        self.assertIn(str(short_term_path), str(error.exception))

    def test_load_existing_conversation_state_wraps_read_text_os_errors(self):
        """状态文件读取抛 OSError/PermissionError 时应统一包装为配置错误。"""

        conversation = build_small_conversation()
        original_read_text = Path.read_text

        for error_type in (OSError, PermissionError):
            with self.subTest(error_type=error_type.__name__):
                with tempfile.TemporaryDirectory() as temp_dir:
                    storage_root = Path(temp_dir)
                    state_dir = storage_root / conversation.conversation_id
                    state_dir.mkdir(parents=True, exist_ok=True)
                    short_term_path = state_dir / "short_term.json"
                    short_term_path.write_text("[]", encoding="utf-8")
                    resolved_short_term_path = short_term_path.resolve()

                    def fake_read_text(path: Path, *args: object, **kwargs: object) -> str:
                        """仅让目标 short_term 文件模拟底层读取失败。"""

                        if path.resolve() == resolved_short_term_path:
                            raise error_type("simulated read failure")
                        return original_read_text(path, *args, **kwargs)

                    system = MemoryOS(
                        openai_api_key="unit-test-key",
                        openai_base_url="https://example.invalid/v1",
                        storage_root=storage_root,
                    )

                    with patch.object(Path, "read_text", autospec=True, side_effect=fake_read_text):
                        with self.assertRaises(ConfigurationError) as error:
                            system.load_existing_conversation_state(conversation)

                self.assertIn("short_term.json", str(error.exception))
                self.assertIn(str(short_term_path), str(error.exception))

    def test_load_existing_conversation_state_rejects_invalid_mid_term_schema(self):
        """mid_term.json 存在但 schema 类型不符时必须拒绝 attach。"""

        conversation = build_small_conversation()
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_root = Path(temp_dir)
            state_dir = storage_root / conversation.conversation_id
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / "short_term.json").write_text("[]", encoding="utf-8")
            (state_dir / "mid_term.json").write_text(
                json.dumps({"sessions": [], "access_frequency": {}}),
                encoding="utf-8",
            )

            system = MemoryOS(
                openai_api_key="unit-test-key",
                openai_base_url="https://example.invalid/v1",
                storage_root=storage_root,
            )

            with self.assertRaises(ConfigurationError):
                system.load_existing_conversation_state(conversation)

    def test_load_existing_conversation_state_rejects_corrupted_mid_term_json(self):
        """mid_term.json 损坏时必须拒绝 attach。"""

        conversation = build_small_conversation()
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_root = Path(temp_dir)
            state_dir = storage_root / conversation.conversation_id
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / "short_term.json").write_text("[]", encoding="utf-8")
            (state_dir / "mid_term.json").write_text("{bad json", encoding="utf-8")

            system = MemoryOS(
                openai_api_key="unit-test-key",
                openai_base_url="https://example.invalid/v1",
                storage_root=storage_root,
            )

            with self.assertRaises(ConfigurationError):
                system.load_existing_conversation_state(conversation)

    def test_load_existing_conversation_state_rejects_invalid_long_term_schema(self):
        """long_term.json 存在但 schema 类型不符时必须拒绝 attach。"""

        conversation = build_small_conversation()
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_root = Path(temp_dir)
            state_dir = storage_root / conversation.conversation_id
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / "short_term.json").write_text("[]", encoding="utf-8")
            (state_dir / "long_term.json").write_text(
                json.dumps(
                    {
                        "user_profiles": [],
                        "knowledge_base": [],
                        "assistant_knowledge": [],
                    }
                ),
                encoding="utf-8",
            )

            system = MemoryOS(
                openai_api_key="unit-test-key",
                openai_base_url="https://example.invalid/v1",
                storage_root=storage_root,
            )

            with self.assertRaises(ConfigurationError):
                system.load_existing_conversation_state(conversation)

    def test_load_existing_conversation_state_rejects_corrupted_long_term_json(self):
        """long_term.json 损坏时必须拒绝 attach。"""

        conversation = build_small_conversation()
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_root = Path(temp_dir)
            state_dir = storage_root / conversation.conversation_id
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / "short_term.json").write_text("[]", encoding="utf-8")
            (state_dir / "long_term.json").write_text("{bad json", encoding="utf-8")

            system = MemoryOS(
                openai_api_key="unit-test-key",
                openai_base_url="https://example.invalid/v1",
                storage_root=storage_root,
            )

            with self.assertRaises(ConfigurationError):
                system.load_existing_conversation_state(conversation)

    def test_chat_completion_retries_timeout_and_returns_successful_content(self):
        """MemoryOS API 超时时应等待后重试，并返回后续成功响应内容。"""

        timeout_error = APITimeoutError(
            request=httpx.Request("POST", "https://example.invalid/v1/chat/completions")
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            system = MemoryOS(
                openai_api_key="unit-test-key",
                openai_base_url="https://example.invalid/v1",
                storage_root=Path(temp_dir),
                config=MemoryOSPaperConfig(
                    api_timeout_seconds=1.0,
                    api_max_retries=2,
                    api_retry_wait_seconds=0.01,
                ),
            )
            fake_client = _FakeOpenAIClient([timeout_error, "retry success"])
            system.get_debug_modules().utils.gpt_client = fake_client

            with patch("memory_benchmark.methods.memoryos_adapter.time.sleep") as sleep:
                content = system._client.chat_completion(  # noqa: SLF001 - 测试 wrapper 注入的官方入口。
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": "hello"}],
                )

        self.assertEqual(content, "retry success")
        self.assertEqual(fake_client.call_count, 2)
        sleep.assert_called_once_with(0.01)

    def test_chat_completion_raises_after_retry_budget_is_exhausted(self):
        """MemoryOS API 连续超时时应在重试次数耗尽后抛出最后一次异常。"""

        first_timeout = APITimeoutError(
            request=httpx.Request("POST", "https://example.invalid/v1/chat/completions")
        )
        second_timeout = APITimeoutError(
            request=httpx.Request("POST", "https://example.invalid/v1/chat/completions")
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            system = MemoryOS(
                openai_api_key="unit-test-key",
                openai_base_url="https://example.invalid/v1",
                storage_root=Path(temp_dir),
                config=MemoryOSPaperConfig(
                    api_timeout_seconds=1.0,
                    api_max_retries=1,
                    api_retry_wait_seconds=0.01,
                ),
            )
            fake_client = _FakeOpenAIClient([first_timeout, second_timeout])
            system.get_debug_modules().utils.gpt_client = fake_client

            with patch("memory_benchmark.methods.memoryos_adapter.time.sleep") as sleep:
                with self.assertRaises(APITimeoutError):
                    system._client.chat_completion(  # noqa: SLF001 - 测试 wrapper 注入的官方入口。
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": "hello"}],
                    )

        self.assertEqual(fake_client.call_count, 2)
        sleep.assert_called_once_with(0.01)

    def test_get_answer_records_question_and_llm_efficiency_observations(self):
        """get_answer 应区分 retrieval LLM、answer LLM 和 question 聚合效率。"""

        conversation = build_small_conversation()
        collector = EfficiencyCollector(run_id="memoryos-eff-run", enabled=True)
        with tempfile.TemporaryDirectory() as temp_dir:
            system = MemoryOS(
                openai_api_key="unit-test-key",
                openai_base_url="https://example.invalid/v1",
                storage_root=Path(temp_dir),
                efficiency_collector=collector,
            )
            system.add([conversation])
            state = system.get_debug_state(conversation.conversation_id)
            fake_client = _FakeOpenAIClient(
                [
                    _FakeCompletionResponse(
                        "retrieval keywords",
                        prompt_tokens=11,
                        completion_tokens=2,
                    ),
                    _FakeCompletionResponse(
                        "Seattle",
                        prompt_tokens=31,
                        completion_tokens=4,
                    ),
                ]
            )
            system.get_debug_modules().utils.gpt_client = fake_client

            def fake_retrieve(*_: object, **__: object) -> dict[str, object]:
                """模拟检索内部的 query understanding LLM 调用和检索结果。"""

                system._client.chat_completion(  # noqa: SLF001 - 测试 wrapper 注入的官方入口。
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": "extract keywords"}],
                )
                return {
                    "retrieval_queue": [
                        {
                            "user_input": "I moved to Seattle.",
                            "agent_response": "Seattle sounds great.",
                        }
                    ],
                    "long_term_knowledge": ["Alice moved to Seattle."],
                }

            def fake_generate_response_with_meta(
                question_text: str,
                short_memory: object,
                long_memory: object,
                retrieval_queue: object,
                long_term_knowledge: object,
                client: object,
                conversation_id: str,
                speaker_a: str,
                speaker_b: str,
                metadata: dict[str, str],
            ) -> tuple[str, str, str]:
                """模拟最终 answer LLM 调用，并返回官方函数形状。"""

                answer = client.chat_completion(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": question_text}],
                )
                return (
                    answer,
                    "system prompt with Seattle memory",
                    "Where did Alice move?",
                )

            state.retrieval_system.retrieve = fake_retrieve
            system.get_debug_modules().main_loco_parse.generate_system_response_with_meta = (
                fake_generate_response_with_meta
            )

            with collector.question_scope("conv-test", "conv-test:q1") as scope:
                result = system.get_answer(conversation.questions[0])

        self.assertEqual(result.answer, "Seattle")
        records = [record.to_dict() for record in scope.records]
        retrieval_llm = [
            record
            for record in records
            if record["observation_type"] == "llm_call"
            and record["stage"] == "retrieval"
        ]
        answer_llm = [
            record
            for record in records
            if record["observation_type"] == "llm_call"
            and record["stage"] == "answer"
        ]
        question_records = [
            record
            for record in records
            if record["observation_type"] == "question_efficiency"
        ]
        self.assertEqual(retrieval_llm[0]["model_id"], "memoryos-chat-llm")
        self.assertEqual(retrieval_llm[0]["input_tokens"], 11)
        self.assertEqual(retrieval_llm[0]["output_tokens"], 2)
        self.assertEqual(answer_llm[0]["model_id"], "memoryos-chat-llm")
        self.assertEqual(answer_llm[0]["input_tokens"], 31)
        self.assertEqual(answer_llm[0]["output_tokens"], 4)
        self.assertEqual(len(question_records), 1)
        self.assertGreaterEqual(question_records[0]["retrieval_latency_ms"], 0)
        self.assertIsNone(question_records[0]["unsupported_reason"])
        self.assertGreater(question_records[0]["injected_memory_context_tokens"], 0)
        self.assertGreaterEqual(question_records[0]["answer_generation_latency_ms"], 0)

    def test_get_embedding_records_local_token_count_and_latency_on_cache_miss(self):
        """MemoryOS 本地 embedding 应用模型 tokenizer 计数，缓存命中不重复记录。"""

        collector = EfficiencyCollector(run_id="memoryos-embedding-run", enabled=True)
        with tempfile.TemporaryDirectory() as temp_dir:
            system = MemoryOS(
                openai_api_key="unit-test-key",
                openai_base_url="https://example.invalid/v1",
                storage_root=Path(temp_dir),
                efficiency_collector=collector,
            )
            system._embedding_model = _FakeSentenceTransformer()  # noqa: SLF001 - 单测注入本地模型假身。

            with collector.conversation_scope("conv-test") as scope:
                first = system._get_embedding("Alice moved to Seattle.")  # noqa: SLF001
                second = system._get_embedding("Alice moved to Seattle.")  # noqa: SLF001
                collector.record_memory_build_total_latency(latency_ms=1.0)

        self.assertEqual(first, second)
        records = [record.to_dict() for record in scope.records]
        embedding_records = [
            record
            for record in records
            if record["observation_type"] == "embedding_call"
        ]
        self.assertEqual(len(embedding_records), 1)
        self.assertEqual(embedding_records[0]["stage"], "memory_build")
        self.assertEqual(embedding_records[0]["model_id"], "memoryos-embedding")
        self.assertEqual(embedding_records[0]["input_tokens"], 4)
        self.assertEqual(
            embedding_records[0]["token_measurement_source"],
            "method_native",
        )
        self.assertEqual(
            embedding_records[0]["latency_measurement_source"],
            "framework_timer",
        )
        self.assertGreaterEqual(embedding_records[0]["latency_ms"], 0)

    def test_official_memory_context_observer_does_not_change_generation_result(self):
        """官方函数的纯 observer 只能旁路记录上下文，不能改变 prompt、调用和答案。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            system = MemoryOS(
                openai_api_key="unit-test-key",
                openai_base_url="https://example.invalid/v1",
                storage_root=Path(temp_dir),
            )
            module = system.get_debug_modules().main_loco_parse
            short_memory = SimpleNamespace(
                get_all=lambda: [
                    {
                        "user_input": "I moved to Seattle.",
                        "agent_response": "Seattle sounds great.",
                        "timestamp": "2024-01-01",
                    }
                ]
            )
            long_memory = SimpleNamespace(
                get_user_profile=lambda sample_id: {"data": "Alice likes hiking."},
                get_assistant_knowledge=lambda: [
                    {"knowledge": "Bob knows Seattle parks.", "timestamp": "2024-01-02"}
                ],
            )
            retrieval_queue = [
                {
                    "user_input": "I adopted a cat.",
                    "agent_response": "Cats are great.",
                    "timestamp": "2024-01-03",
                    "meta_info": "pet adoption",
                }
            ]
            long_knowledge = [{"knowledge": "Alice lives near Lake Union."}]

            def run_once(observer: object) -> tuple[tuple[str, str, str], list[dict[str, object]]]:
                """运行一次官方生成函数，并返回结果和 fake client 收到的消息。"""

                calls: list[dict[str, object]] = []
                client = SimpleNamespace(
                    chat_completion=lambda **kwargs: (
                        calls.append(kwargs) or "Seattle"
                    )
                )
                module.memory_context_observer = observer
                result = module.generate_system_response_with_meta(
                    "Where did Alice move?",
                    short_memory,
                    long_memory,
                    retrieval_queue,
                    long_knowledge,
                    client,
                    "conv-test",
                    "Alice",
                    "Bob",
                    {"conversation_id": "conv-test", "question_id": "conv-test:q1"},
                )
                return result, calls

            without_observer, calls_without_observer = run_once(None)
            observed_payloads: list[dict[str, str]] = []
            with_observer, calls_with_observer = run_once(observed_payloads.append)

        self.assertEqual(with_observer, without_observer)
        self.assertEqual(calls_with_observer, calls_without_observer)
        self.assertEqual(len(observed_payloads), 1)
        self.assertIn("I moved to Seattle", observed_payloads[0]["history_text"])
        self.assertIn("I adopted a cat", observed_payloads[0]["retrieval_text"])
        self.assertIn(
            "Alice likes hiking",
            observed_payloads[0]["user_profile_and_knowledge"],
        )
        self.assertIn(
            "Bob knows Seattle parks",
            observed_payloads[0]["assistant_knowledge"],
        )

    def test_get_answer_uses_observed_final_memory_context_tokens(self):
        """MemoryOS 应记录最终 prompt 中的记忆上下文 token，而不是只看 retrieval 结果。"""

        conversation = build_small_conversation()
        collector = EfficiencyCollector(run_id="memoryos-context-token-run", enabled=True)
        with tempfile.TemporaryDirectory() as temp_dir:
            system = MemoryOS(
                openai_api_key="unit-test-key",
                openai_base_url="https://example.invalid/v1",
                storage_root=Path(temp_dir),
                efficiency_collector=collector,
            )
            system.add([conversation])
            state = system.get_debug_state(conversation.conversation_id)
            fake_client = _FakeOpenAIClient(
                [_FakeCompletionResponse("Seattle", prompt_tokens=31, completion_tokens=4)]
            )
            system.get_debug_modules().utils.gpt_client = fake_client

            def fake_retrieve(*_: object, **__: object) -> dict[str, object]:
                """返回空检索结果，确保 token 只能来自 observer payload。"""

                return {
                    "retrieval_queue": [],
                    "long_term_knowledge": [],
                }

            def fake_generate_response_with_meta(
                question_text: str,
                short_memory: object,
                long_memory: object,
                retrieval_queue: object,
                long_term_knowledge: object,
                client: object,
                conversation_id: str,
                speaker_a: str,
                speaker_b: str,
                metadata: dict[str, str],
            ) -> tuple[str, str, str]:
                """模拟官方函数触发最终记忆上下文 observer。"""

                observer = getattr(
                    system.get_debug_modules().main_loco_parse,
                    "memory_context_observer",
                    None,
                )
                if observer is not None:
                    observer(
                        {
                            "history_text": "Alice: I moved to Seattle.",
                            "retrieval_text": "",
                            "user_profile_and_knowledge": "【User Profile】\nAlice likes hiking.",
                            "assistant_knowledge": "【Assistant Knowledge】\n- Bob knows Seattle.",
                        }
                    )
                answer = client.chat_completion(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": question_text}],
                )
                return answer, "system prompt", "user prompt"

            state.retrieval_system.retrieve = fake_retrieve
            system.get_debug_modules().main_loco_parse.generate_system_response_with_meta = (
                fake_generate_response_with_meta
            )

            with collector.question_scope("conv-test", "conv-test:q1") as scope:
                system.get_answer(conversation.questions[0])

        question_records = [
            record.to_dict()
            for record in scope.records
            if record.to_dict()["observation_type"] == "question_efficiency"
        ]
        self.assertEqual(len(question_records), 1)
        self.assertGreater(question_records[0]["injected_memory_context_tokens"], 0)


def _build_fake_settings(outputs_root: Path) -> AppSettings:
    """构造 MemoryOS 初始化测试使用的配置对象。

    输入:
        outputs_root: 临时 outputs 根目录。

    输出:
        AppSettings: 包含 fake API key/base_url 和临时路径的配置。
    """

    return AppSettings(
        paths=PathSettings(
            project_root=PROJECT_ROOT,
            data_root=PROJECT_ROOT / "data",
            models_root=PROJECT_ROOT / "models",
            outputs_root=outputs_root,
            third_party_root=PROJECT_ROOT / "third_party",
            third_party_benchmarks_root=PROJECT_ROOT / "third_party" / "benchmarks",
            third_party_methods_root=PROJECT_ROOT / "third_party" / "methods",
        ),
        openai=OpenAISettings(
            api_key="configured-key",
            base_url="https://configured.example/v1",
        ),
    )


class _FakeOpenAIClient:
    """模拟 OpenAI SDK client，只实现 MemoryOS wrapper 会调用的路径。"""

    def __init__(self, outcomes: list[object]):
        """保存每次 `create()` 调用要返回或抛出的结果。"""

        self._outcomes = list(outcomes)
        self.call_count = 0
        self.chat = _FakeChatResource(self)

    def create_completion(self) -> object:
        """返回下一次 fake completion；异常对象会直接抛出。"""

        self.call_count += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if isinstance(outcome, _FakeCompletionResponse):
            return outcome
        return _FakeCompletionResponse(str(outcome))


class _FakeChatResource:
    """模拟 `client.chat`。"""

    def __init__(self, fake_client: _FakeOpenAIClient):
        """绑定外层 fake client。"""

        self.completions = _FakeCompletionsResource(fake_client)


class _FakeCompletionsResource:
    """模拟 `client.chat.completions`。"""

    def __init__(self, fake_client: _FakeOpenAIClient):
        """绑定外层 fake client。"""

        self._fake_client = fake_client

    def create(self, **_: object) -> object:
        """模拟 OpenAI SDK 的 `create()` 方法。"""

        return self._fake_client.create_completion()


class _FakeCompletionResponse:
    """模拟 OpenAI chat completion response。"""

    def __init__(
        self,
        content: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
    ):
        """构造只有第一条 message content 的响应对象。"""

        self.choices = [_FakeChoice(content)]
        self.usage = (
            SimpleNamespace(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            if prompt_tokens is not None and completion_tokens is not None
            else None
        )


class _FakeChoice:
    """模拟 OpenAI response choice。"""

    def __init__(self, content: str):
        """保存 assistant message 内容。"""

        self.message = _FakeMessage(content)


class _FakeMessage:
    """模拟 OpenAI response message。"""

    def __init__(self, content: str):
        """保存最终文本内容。"""

        self.content = content


class _FakeSentenceTransformer:
    """模拟 SentenceTransformer，仅提供 encode 和 tokenizer。"""

    def __init__(self):
        """初始化调用记录和 fake tokenizer。"""

        self.calls: list[list[str]] = []
        self.tokenizer = _FakeSentenceTokenizer()

    def encode(self, texts: list[str], convert_to_numpy: bool = True):
        """记录待编码文本并返回稳定向量。"""

        self.calls.append(list(texts))
        return [[0.1, 0.2, 0.3] for _ in texts]


class _FakeSentenceTokenizer:
    """模拟 HuggingFace tokenizer 的最小返回结构。"""

    def __call__(self, text: str, add_special_tokens: bool = True):
        """按空格切分并返回 input_ids。"""

        return {"input_ids": list(range(len(text.split())))}


if __name__ == "__main__":
    unittest.main()


def test_memoryos_config_manifest_includes_public_fields_and_adapter_metadata() -> None:
    """manifest 应包含配置字段及 adapter/source 模式标识。"""

    config = MemoryOSPaperConfig()

    assert config.to_manifest() == {
        **asdict(config),
        "adapter_version": "conversation-qa-v1",
        "source_mode": "official-eval-wrapper",
    }
    for value in config.to_manifest().values():
        if isinstance(value, float):
            assert math.isfinite(value)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("llm_model", ""),
        ("llm_model", "   "),
        ("llm_model", 123),
        ("llm_model", None),
        ("embedding_model_name", ""),
        ("embedding_model_name", "   "),
        ("embedding_model_name", 123),
        ("embedding_model_name", None),
        ("profile_name", ""),
        ("profile_name", "   "),
        ("profile_name", 123),
        ("profile_name", None),
    ],
)
def test_memoryos_config_requires_non_empty_model_names(field_name: str, value: object) -> None:
    """模型名与 profile_name 必须是非空字符串。"""

    with pytest.raises(ConfigurationError, match=field_name):
        MemoryOSPaperConfig(**{field_name: value})


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("short_term_capacity", 0),
        ("short_term_capacity", -1),
        ("short_term_capacity", True),
        ("short_term_capacity", 1.5),
        ("short_term_capacity", "1"),
        ("mid_term_capacity", 0),
        ("mid_term_capacity", -1),
        ("mid_term_capacity", True),
        ("mid_term_capacity", 1.5),
        ("mid_term_capacity", "1"),
        ("long_term_knowledge_capacity", 0),
        ("long_term_knowledge_capacity", -1),
        ("long_term_knowledge_capacity", True),
        ("long_term_knowledge_capacity", 1.5),
        ("long_term_knowledge_capacity", "1"),
        ("retrieval_top_m_segments", 0),
        ("retrieval_top_m_segments", -1),
        ("retrieval_top_m_segments", True),
        ("retrieval_top_m_segments", 1.5),
        ("retrieval_top_m_segments", "1"),
        ("retrieval_queue_capacity", 0),
        ("retrieval_queue_capacity", -1),
        ("retrieval_queue_capacity", True),
        ("retrieval_queue_capacity", 1.5),
        ("retrieval_queue_capacity", "1"),
        ("max_workers", 0),
        ("max_workers", -1),
        ("max_workers", True),
        ("max_workers", 1.5),
        ("max_workers", "1"),
        ("api_max_retries", True),
        ("api_max_retries", 1.5),
        ("api_max_retries", "1"),
    ],
)
def test_memoryos_config_requires_positive_integers(field_name: str, value: object) -> None:
    """整数字段必须满足精确整数类型约束。"""

    with pytest.raises(ConfigurationError, match=field_name):
        MemoryOSPaperConfig(**{field_name: value})


@pytest.mark.parametrize("value", [0, 1, "true", None])
def test_memoryos_config_requires_boolean_suppress_flag(value: object) -> None:
    """stdout 抑制开关必须是真正的 bool。"""

    with pytest.raises(ConfigurationError, match="suppress_official_stdout"):
        MemoryOSPaperConfig(suppress_official_stdout=value)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("topic_similarity_threshold", -0.1),
        ("topic_similarity_threshold", 1.1),
        ("topic_similarity_threshold", True),
        ("topic_similarity_threshold", "0.1"),
        ("topic_similarity_threshold", math.nan),
        ("topic_similarity_threshold", math.inf),
        ("segment_threshold", -0.1),
        ("segment_threshold", 1.1),
        ("segment_threshold", True),
        ("segment_threshold", "0.1"),
        ("segment_threshold", math.nan),
        ("segment_threshold", math.inf),
        ("page_threshold", -0.1),
        ("page_threshold", 1.1),
        ("page_threshold", True),
        ("page_threshold", "0.1"),
        ("page_threshold", math.nan),
        ("page_threshold", math.inf),
        ("knowledge_threshold", -0.1),
        ("knowledge_threshold", 1.1),
        ("knowledge_threshold", True),
        ("knowledge_threshold", "0.1"),
        ("knowledge_threshold", math.nan),
        ("knowledge_threshold", math.inf),
    ],
)
def test_memoryos_config_requires_unit_interval_thresholds(
    field_name: str,
    value: float,
) -> None:
    """topic、segment、page、knowledge threshold 都必须在 [0, 1]。"""

    with pytest.raises(ConfigurationError, match=field_name):
        MemoryOSPaperConfig(**{field_name: value})


def test_memoryos_config_requires_non_negative_heat_threshold() -> None:
    """heat threshold 不得为负。"""

    with pytest.raises(ConfigurationError, match="heat_threshold"):
        MemoryOSPaperConfig(heat_threshold=-0.1)


@pytest.mark.parametrize("value", [True, "5", math.nan, math.inf, -math.inf])
def test_memoryos_config_requires_finite_numeric_heat_threshold(value: object) -> None:
    """heat threshold 必须是有限数值。"""

    with pytest.raises(ConfigurationError, match="heat_threshold"):
        MemoryOSPaperConfig(heat_threshold=value)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("api_timeout_seconds", 0.0),
        ("api_timeout_seconds", True),
        ("api_timeout_seconds", "120"),
        ("api_timeout_seconds", math.nan),
        ("api_timeout_seconds", math.inf),
        ("api_max_retries", -1),
        ("api_retry_wait_seconds", -0.1),
        ("api_retry_wait_seconds", True),
        ("api_retry_wait_seconds", "5"),
        ("api_retry_wait_seconds", math.nan),
        ("api_retry_wait_seconds", math.inf),
        ("api_retry_backoff_multiplier", 0.5),
        ("api_retry_backoff_multiplier", True),
        ("api_retry_backoff_multiplier", "2"),
        ("api_retry_backoff_multiplier", math.nan),
        ("api_retry_backoff_multiplier", math.inf),
        ("api_retry_max_wait_seconds", 0.0),
        ("api_retry_max_wait_seconds", True),
        ("api_retry_max_wait_seconds", "60"),
        ("api_retry_max_wait_seconds", math.nan),
        ("api_retry_max_wait_seconds", math.inf),
    ],
)
def test_memoryos_config_preserves_retry_and_timeout_guards(
    field_name: str,
    value: float | int,
) -> None:
    """原有 timeout/retry 约束仍应保留。"""

    with pytest.raises(ConfigurationError, match=field_name):
        MemoryOSPaperConfig(**{field_name: value})


def test_build_memoryos_source_identity_is_deterministic_and_scoped() -> None:
    """MemoryOS source identity 应稳定记录 vendored 官方源码和本项目 wrapper。"""

    first = build_memoryos_source_identity()
    second = build_memoryos_source_identity()

    assert first == second
    assert len(first["source_sha256"]) == 64
    assert all(character in "0123456789abcdef" for character in first["source_sha256"])
    assert len(first["vendored_source_sha256"]) == 64
    assert len(first["wrapper_sha256"]) == 64
    assert first["wrapper_path"] == "src/memory_benchmark/methods/memoryos_adapter.py"
    assert not first["wrapper_path"].startswith("/")
    assert first["file_count"] == len(first["files"])
    assert first["file_count"] > 0
    assert first["files"] == sorted(first["files"])
    assert first["source_mode"] == "vendored-official-eval-with-framework-wrapper"
    assert first["vendored_source_mode"] == "vendored-official-eval"
    assert all(not path.startswith("/") for path in first["files"])
    assert all(
        path == "README.md"
        or path == "LICENSE"
        or path == "memoryos-pypi/prompts.py"
        or path.startswith("eval/")
        for path in first["files"]
    )
    assert all(
        path == "memoryos-pypi/prompts.py"
        or "/" not in path.removeprefix("eval/")
        or path.startswith("eval/")
        for path in first["files"]
    )
    assert all("__pycache__" not in path for path in first["files"])
    assert all(not path.lower().endswith((".png", ".jpg", ".jpeg", ".pdf")) for path in first["files"])
    assert first["source_sha256"] != first["vendored_source_sha256"]


def test_memoryos_source_identity_wrapper_bytes_change_only_wrapper_component() -> None:
    """wrapper 字节变化时，应只改变 wrapper 组件和组合 source hash。"""

    current_identity = build_memoryos_source_identity()
    first = memoryos_adapter_module._build_memoryos_source_identity_from_components(
        vendored_files=current_identity["files"],
        vendored_source_sha256=current_identity["vendored_source_sha256"],
        wrapper_logical_path=current_identity["wrapper_path"],
        wrapper_bytes=b"wrapper version one",
    )
    second = memoryos_adapter_module._build_memoryos_source_identity_from_components(
        vendored_files=current_identity["files"],
        vendored_source_sha256=current_identity["vendored_source_sha256"],
        wrapper_logical_path=current_identity["wrapper_path"],
        wrapper_bytes=b"wrapper version two",
    )

    assert first["files"] == second["files"] == current_identity["files"]
    assert first["file_count"] == second["file_count"] == current_identity["file_count"]
    assert (
        first["vendored_source_sha256"]
        == second["vendored_source_sha256"]
        == current_identity["vendored_source_sha256"]
    )
    assert first["wrapper_path"] == second["wrapper_path"] == current_identity["wrapper_path"]
    assert first["wrapper_sha256"] != second["wrapper_sha256"]
    assert first["source_sha256"] != second["source_sha256"]


def test_create_state_binds_retrieval_top_m_into_official_search_call() -> None:
    """wrapper 应在项目侧把 configured top-m 绑定到官方检索方法。"""

    conversation = build_small_conversation()
    fake_modules = _build_fake_eval_modules_for_top_m_binding()
    with tempfile.TemporaryDirectory() as temp_dir:
        system = object.__new__(MemoryOS)
        system.config = MemoryOSPaperConfig(retrieval_top_m_segments=3, retrieval_queue_capacity=10)
        system.storage_root = Path(temp_dir)
        system._client = object()
        system._modules = fake_modules

        state = system._create_state(conversation)  # noqa: SLF001 - 验证 wrapper 的官方接线。
        assert isinstance(state.mid_memory.search_sessions_by_summary, partial)

        state.retrieval_system.retrieve(
            "Where did Alice move?",
            segment_threshold=0.2,
            page_threshold=0.3,
            knowledge_threshold=0.4,
            client=system._client,
        )

    assert fake_modules.mid_term_memory.recorded_calls == [
        {
            "query": "Where did Alice move?",
            "client": system._client,
            "segment_threshold": 0.2,
            "page_threshold": 0.3,
            "top_k": 3,
        }
    ]


def _build_fake_eval_modules_for_top_m_binding() -> SimpleNamespace:
    """构造仅用于 top-m 接线测试的最小官方 eval 模块替身。"""

    class _FakeShortTermMemory:
        """模拟官方短期记忆对象。"""

        def __init__(self, max_capacity: int, file_path: str):
            """保存短期记忆初始化参数。"""

            self.max_capacity = max_capacity
            self.file_path = file_path

    class _FakeMidTermMemory:
        """模拟官方中期记忆对象，并记录检索调用。"""

        recorded_calls: list[dict[str, object]] = []

        def __init__(self, max_capacity: int, file_path: str):
            """保存中期记忆初始化参数。"""

            self.max_capacity = max_capacity
            self.file_path = file_path

        def search_sessions_by_summary(
            self,
            query: str,
            client: object,
            segment_threshold: float = 0.8,
            page_threshold: float = 0.7,
            top_k: int = 5,
        ) -> list[dict[str, object]]:
            """记录 top-m 绑定后的官方检索入参。"""

            type(self).recorded_calls.append(
                {
                    "query": query,
                    "client": client,
                    "segment_threshold": segment_threshold,
                    "page_threshold": page_threshold,
                    "top_k": top_k,
                }
            )
            return []

    class _FakeLongTermMemory:
        """模拟官方长期记忆对象。"""

        def __init__(self, file_path: str):
            """保存长期记忆初始化参数。"""

            self.file_path = file_path

        def search_knowledge(self, user_query: str, threshold: float = 0.7) -> list[object]:
            """返回空知识结果，避免引入额外行为。"""

            return []

    class _FakeDynamicUpdate:
        """模拟官方动态更新器。"""

        def __init__(
            self,
            short_memory: object,
            mid_memory: object,
            long_memory: object,
            topic_similarity_threshold: float,
            client: object,
        ):
            """保存动态更新器依赖，供测试接线使用。"""

            self.short_memory = short_memory
            self.mid_memory = mid_memory
            self.long_memory = long_memory
            self.topic_similarity_threshold = topic_similarity_threshold
            self.client = client

    class _FakeRetrievalAndAnswer:
        """模拟官方检索与回答协调器。"""

        def __init__(
            self,
            short_memory: object,
            mid_term_memory: _FakeMidTermMemory,
            long_term_memory: _FakeLongTermMemory,
            dynamic_updater: object,
            queue_capacity: int = 25,
        ):
            """保存检索协调器依赖与队列容量。"""

            self.short_memory = short_memory
            self.mid_term_memory = mid_term_memory
            self.long_term_memory = long_term_memory
            self.dynamic_updater = dynamic_updater
            self.queue_capacity = queue_capacity

        def retrieve(
            self,
            user_query: str,
            segment_threshold: float = 0.7,
            page_threshold: float = 0.7,
            knowledge_threshold: float = 0.7,
            client: object | None = None,
        ) -> dict[str, object]:
            """复刻官方调用链，触发中期记忆检索记录。"""

            matched = self.mid_term_memory.search_sessions_by_summary(
                user_query,
                client,
                segment_threshold,
                page_threshold,
            )
            return {
                "retrieval_queue": matched,
                "long_term_knowledge": self.long_term_memory.search_knowledge(
                    user_query,
                    threshold=knowledge_threshold,
                ),
            }

    _FakeMidTermMemory.recorded_calls = []
    return SimpleNamespace(
        short_term_memory=SimpleNamespace(ShortTermMemory=_FakeShortTermMemory),
        mid_term_memory=SimpleNamespace(MidTermMemory=_FakeMidTermMemory, recorded_calls=_FakeMidTermMemory.recorded_calls),
        long_term_memory=SimpleNamespace(LongTermMemory=_FakeLongTermMemory),
        dynamic_update=SimpleNamespace(DynamicUpdate=_FakeDynamicUpdate),
        retrieval_and_answer=SimpleNamespace(RetrievalAndAnswer=_FakeRetrievalAndAnswer),
    )
