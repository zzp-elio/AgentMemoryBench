"""测试 conversation-QA 数据强约束校验。"""

import json
import unittest

import pytest

from memory_benchmark.benchmark_adapters.base import BenchmarkAdapter
from memory_benchmark.core import (
    Conversation,
    Dataset,
    GoldAnswerInfo,
    GoldEvidenceGroup,
    GoldEvidenceGroupSet,
    Question,
    Session,
    Turn,
)
from memory_benchmark.core.exceptions import DataLeakageError, DatasetValidationError
from memory_benchmark.core.validators import (
    validate_dataset,
    validate_no_private_keys,
)


pytestmark = pytest.mark.unit


def build_valid_dataset() -> Dataset:
    """构造一个最小合法 Dataset。"""

    question = Question(question_id="q1", conversation_id="conv1", text="What does Alice like?")
    return Dataset(
        dataset_name="dummy",
        conversations=[
            Conversation(
                conversation_id="conv1",
                sessions=[
                    Session(
                        session_id="s1",
                        session_time="2024-01-01",
                        turns=[Turn(turn_id="t1", speaker="Alice", content="I like tea.")],
                    )
                ],
                questions=[question],
                gold_answers={"q1": GoldAnswerInfo(question_id="q1", answer="tea")},
            )
        ],
    )


class MetadataLeakAdapter(BenchmarkAdapter):
    """测试用 adapter，用于确认 load() 会检查公开 metadata 泄漏。"""

    name = "metadata_leak"

    def load_dataset(self, limit: int | None = None) -> Dataset:
        """返回一个结构合法但公开 metadata 含私有键的数据集。"""

        dataset = build_valid_dataset()
        dataset.conversations[0].metadata["gold_answer"] = "tea"
        return dataset


class ConversationDatasetValidationTest(unittest.TestCase):
    """验证数据缺字段时能尽早报错。"""

    def test_valid_dataset_passes(self):
        """合法数据集应通过通用校验。"""

        validate_dataset(build_valid_dataset())

    def test_question_without_gold_answer_fails(self):
        """每个 Question 必须有对应 GoldAnswerInfo。"""

        dataset = build_valid_dataset()
        dataset.conversations[0].gold_answers = {}

        with self.assertRaises(DatasetValidationError):
            validate_dataset(dataset)

    def test_extra_gold_answer_without_question_fails(self):
        """gold_answers 里不能出现没有公开 Question 对应的私有答案。"""

        dataset = build_valid_dataset()
        dataset.conversations[0].gold_answers["q2"] = GoldAnswerInfo(
            question_id="q2",
            answer="coffee",
        )

        with self.assertRaises(DatasetValidationError):
            validate_dataset(dataset)

    def test_turn_without_content_fails(self):
        """纯文本 Phase 1 中 turn content 不能为空。"""

        dataset = build_valid_dataset()
        dataset.conversations[0].sessions[0].turns[0].content = ""

        with self.assertRaises(DatasetValidationError):
            validate_dataset(dataset)

    def test_public_conversation_payload_has_no_private_keys(self):
        """公开 Conversation 导出应通过 private key 泄漏检查。"""

        conversation = build_valid_dataset().conversations[0]

        validate_no_private_keys(conversation.to_public_dict())

    def test_payload_with_gold_answer_key_fails(self):
        """公开 payload 里出现 gold_answers 应被视为泄漏风险。"""

        payload = build_valid_dataset().conversations[0].to_public_dict()
        payload["gold_answers"] = {"q1": {"answer": "tea"}}

        with self.assertRaises(DataLeakageError):
            validate_no_private_keys(payload)

    def test_payload_with_answer_session_ids_key_fails(self):
        """公开 payload 里出现 LongMemEval answer_session_ids 应被视为泄漏。"""

        payload = build_valid_dataset().conversations[0].to_public_dict()
        payload["metadata"]["answer_session_ids"] = ["session_1"]

        with self.assertRaises(DataLeakageError):
            validate_no_private_keys(payload)

    def test_adapter_load_checks_public_metadata_leakage(self):
        """BenchmarkAdapter.load 应阻止公开 metadata 中的 gold_answer 键。"""

        adapter = MetadataLeakAdapter(project_root=".")

        with self.assertRaises(DataLeakageError):
            adapter.load()


def _mapped_group(unit_id: str = "u1", child_ids: tuple[str, ...] = ("t1",)) -> GoldEvidenceGroup:
    """构造一个合法 mapped group，供反例测试逐字段污染。"""

    return GoldEvidenceGroup(
        unit_id=unit_id,
        child_ids=child_ids,
        mapping_status="mapped",
    )


def _turn_group_set(groups: tuple[GoldEvidenceGroup, ...]) -> GoldEvidenceGroupSet:
    """构造一个 turn 粒度合法 group set。"""

    return GoldEvidenceGroupSet(
        provenance_granularity="turn",
        unit_kind="fake_unit",
        groups=groups,
    )


class GoldEvidenceGroupEntityTest(unittest.TestCase):
    """GoldEvidenceGroup/GoldEvidenceGroupSet 的运行时强反例。"""

    def test_valid_mapped_and_unmatched_groups_pass(self):
        """mapped 至少一个 child；unmatched 零 child；同名退化 unit 合法。"""

        mapped = GoldEvidenceGroup(
            unit_id="D1:2",
            child_ids=("D1:2",),
            mapping_status="mapped",
        )
        unmatched = GoldEvidenceGroup(
            unit_id="--",
            child_ids=(),
            mapping_status="unmatched",
        )
        self.assertEqual(mapped.unit_id, "D1:2")
        self.assertEqual(unmatched.child_ids, ())

    def test_unknown_mapping_status_rejected(self):
        """未知 mapping status 必须构造期拒绝。"""

        for status in ("bogus", "MAPPED", "", None, 1):
            with self.subTest(status=status), self.assertRaises(ValueError):
                GoldEvidenceGroup(unit_id="u1", child_ids=("t1",), mapping_status=status)

    def test_blank_or_padded_ids_rejected(self):
        """空串或带首尾空白的 unit/child id 拒绝，不做宽松正规化。"""

        for bad_id in ("", " u1", "u1 ", "\tu1", "u1\n"):
            with self.subTest(unit_id=bad_id), self.assertRaises(ValueError):
                GoldEvidenceGroup(unit_id=bad_id, child_ids=("t1",), mapping_status="mapped")
            with self.subTest(child_id=bad_id), self.assertRaises(ValueError):
                GoldEvidenceGroup(unit_id="u1", child_ids=(bad_id,), mapping_status="mapped")

    def test_non_string_ids_rejected(self):
        """unit/child id 类型必须严格是 str。"""

        with self.assertRaises(ValueError):
            GoldEvidenceGroup(unit_id=1, child_ids=("t1",), mapping_status="mapped")
        with self.assertRaises(ValueError):
            GoldEvidenceGroup(unit_id="u1", child_ids=(1,), mapping_status="mapped")

    def test_list_cannot_impersonate_child_tuple(self):
        """child_ids 必须是 tuple，list 冒充直接拒绝。"""

        with self.assertRaises(ValueError):
            GoldEvidenceGroup(unit_id="u1", child_ids=["t1"], mapping_status="mapped")

    def test_mapped_requires_child_and_unmatched_forbids_child(self):
        """mapped 空 child、unmatched 非空 child 都是非法状态。"""

        with self.assertRaises(ValueError):
            GoldEvidenceGroup(unit_id="u1", child_ids=(), mapping_status="mapped")
        with self.assertRaises(ValueError):
            GoldEvidenceGroup(unit_id="u1", child_ids=("t1",), mapping_status="unmatched")

    def test_duplicate_child_ids_rejected(self):
        """同一 group 内 child id 不得重复。"""

        with self.assertRaises(ValueError):
            GoldEvidenceGroup(
                unit_id="u1",
                child_ids=("t1", "t1"),
                mapping_status="mapped",
            )

    def test_group_set_rejects_unknown_granularity(self):
        """granularity 只接受 turn/session。"""

        for granularity in ("pair", "conversation", "", None, "TURN"):
            with self.subTest(granularity=granularity), self.assertRaises(ValueError):
                GoldEvidenceGroupSet(
                    provenance_granularity=granularity,
                    unit_kind="fake_unit",
                    groups=(_mapped_group(),),
                )

    def test_group_set_rejects_blank_unit_kind_and_list_groups(self):
        """unit_kind 必须非空未 padded；groups 必须是强类型 tuple。"""

        with self.assertRaises(ValueError):
            GoldEvidenceGroupSet(
                provenance_granularity="turn",
                unit_kind=" fake",
                groups=(),
            )
        with self.assertRaises(ValueError):
            GoldEvidenceGroupSet(
                provenance_granularity="turn",
                unit_kind="fake_unit",
                groups=[_mapped_group()],
            )
        with self.assertRaises(ValueError):
            GoldEvidenceGroupSet(
                provenance_granularity="turn",
                unit_kind="fake_unit",
                groups=({"unit_id": "u1"},),
            )

    def test_group_set_rejects_duplicate_unit_ids(self):
        """同一 set 内 unit id 不得重复。"""

        with self.assertRaises(ValueError):
            _turn_group_set((_mapped_group("u1"), _mapped_group("u1", ("t2",))))

    def test_empty_group_set_is_legal(self):
        """groups=() 合法，表示该 view 确实没有 gold。"""

        group_set = _turn_group_set(())
        self.assertEqual(group_set.groups, ())


class GoldAnswerInfoContractTest(unittest.TestCase):
    """GoldAnswerInfo 的 gold evidence contract v1 强校验。"""

    def test_version_only_accepts_none_or_v1(self):
        """未知 version（含空白与 v2）全部拒绝。"""

        for version in ("", " ", "v2", "V1", "bogus"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                GoldAnswerInfo(
                    question_id="q1",
                    answer="tea",
                    gold_evidence_contract_version=version,
                )

    def test_group_sets_require_v1(self):
        """携带 group sets 时 version 必须显式 v1。"""

        with self.assertRaises(ValueError):
            GoldAnswerInfo(
                question_id="q1",
                answer="tea",
                evidence_group_sets=(_turn_group_set((_mapped_group(),)),),
            )

    def test_group_sets_must_be_typed_tuple(self):
        """evidence_group_sets 必须是 GoldEvidenceGroupSet tuple。"""

        with self.assertRaises(ValueError):
            GoldAnswerInfo(
                question_id="q1",
                answer="tea",
                gold_evidence_contract_version="v1",
                evidence_group_sets=[_turn_group_set(())],
            )
        with self.assertRaises(ValueError):
            GoldAnswerInfo(
                question_id="q1",
                answer="tea",
                gold_evidence_contract_version="v1",
                evidence_group_sets=({"provenance_granularity": "turn"},),
            )

    def test_duplicate_view_rejected(self):
        """同一 GoldAnswerInfo 内 (granularity, unit_kind) 不得重复。"""

        with self.assertRaises(ValueError):
            GoldAnswerInfo(
                question_id="q1",
                answer="tea",
                gold_evidence_contract_version="v1",
                evidence_group_sets=(_turn_group_set(()), _turn_group_set(())),
            )

    def test_v1_with_zero_group_sets_is_legal(self):
        """HaluMem 形态：声明 v1 但没有任何 qrel view。"""

        gold = GoldAnswerInfo(
            question_id="q1",
            answer="tea",
            gold_evidence_contract_version="v1",
            evidence_group_sets=(),
        )
        self.assertEqual(gold.evidence_group_sets, ())

    def test_json_round_trip_preserves_groups(self):
        """to_dict → json → 重建后 group 结构逐字段一致。"""

        gold = GoldAnswerInfo(
            question_id="q1",
            answer="tea",
            gold_evidence_contract_version="v1",
            evidence_group_sets=(
                GoldEvidenceGroupSet(
                    provenance_granularity="turn",
                    unit_kind="fake_unit",
                    groups=(
                        GoldEvidenceGroup(
                            unit_id="u1",
                            child_ids=("t1", "t2"),
                            mapping_status="mapped",
                        ),
                        GoldEvidenceGroup(
                            unit_id="u2",
                            child_ids=(),
                            mapping_status="unmatched",
                        ),
                    ),
                ),
                GoldEvidenceGroupSet(
                    provenance_granularity="session",
                    unit_kind="fake_session_unit",
                    groups=(),
                ),
            ),
        )

        payload = json.loads(json.dumps(gold.to_dict(), ensure_ascii=False))
        rebuilt_sets = tuple(
            GoldEvidenceGroupSet(
                provenance_granularity=raw_set["provenance_granularity"],
                unit_kind=raw_set["unit_kind"],
                groups=tuple(
                    GoldEvidenceGroup(
                        unit_id=raw_group["unit_id"],
                        child_ids=tuple(raw_group["child_ids"]),
                        mapping_status=raw_group["mapping_status"],
                    )
                    for raw_group in raw_set["groups"]
                ),
            )
            for raw_set in payload["evidence_group_sets"]
        )
        self.assertEqual(payload["gold_evidence_contract_version"], "v1")
        self.assertEqual(rebuilt_sets, gold.evidence_group_sets)


if __name__ == "__main__":
    unittest.main()
