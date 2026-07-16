"""测试实验产物存储工具。"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pytest

from memory_benchmark.core import (
    Conversation,
    DataLeakageError,
    Dataset,
    GoldAnswerInfo,
    GoldEvidenceGroup,
    GoldEvidenceGroupSet,
    Question,
    Session,
    Turn,
)
from memory_benchmark.storage import (
    ExperimentPaths,
    JsonlWriter,
    atomic_write_json,
    atomic_write_jsonl,
    build_dataset_fingerprint,
    evaluator_private_label_record,
    public_question_record,
    read_jsonl,
)


pytestmark = pytest.mark.integration


class ExperimentStorageTests(unittest.TestCase):
    """验证标准输出路径、JSONL 写入和数据指纹。"""

    def test_experiment_paths_create_standard_layout(self):
        """ExperimentPaths 应创建 artifacts/logs/checkpoints/summaries。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ExperimentPaths.create(Path(temp_dir) / "run-001")

            self.assertTrue(paths.artifacts_dir.is_dir())
            self.assertTrue(paths.logs_dir.is_dir())
            self.assertTrue(paths.checkpoints_dir.is_dir())
            self.assertTrue(paths.summaries_dir.is_dir())
            self.assertEqual(paths.method_predictions_path.name, "method_predictions.jsonl")
            self.assertEqual(paths.redacted_config_path.name, "config.redacted.json")
            self.assertEqual(paths.conversation_status_path.name, "conversation_status.json")
            self.assertEqual(
                paths.locomo_f1_scores_path.name,
                "answer_scores.locomo_f1.jsonl",
            )
            self.assertEqual(paths.summary_path.name, "summary.json")

    def test_jsonl_writer_appends_records(self):
        """JsonlWriter 应把多条记录追加为多行 JSONL。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            writer = JsonlWriter(path)

            writer.append({"id": "a", "score": 1.0})
            writer.append({"id": "b", "score": 0.5})

            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

            self.assertEqual([row["id"] for row in rows], ["a", "b"])

    def test_read_jsonl_is_strict_by_default_for_torn_tail(self):
        """默认读取遇到无末尾换行的损坏尾行时仍应抛 JSON 解析错误。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            path.write_text('{"id":"complete"}\n{"id":"torn"', encoding="utf-8")

            with self.assertRaises(json.JSONDecodeError):
                read_jsonl(path)

    def test_read_jsonl_can_explicitly_recover_torn_tail(self):
        """显式恢复应只返回损坏尾行之前已经完整写入的字典记录。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            path.write_text('{"id":"complete"}\n{"id":"torn"', encoding="utf-8")

            records = read_jsonl(path, recover_torn_tail=True)

        self.assertEqual(records, [{"id": "complete"}])

    def test_read_jsonl_recovery_rejects_malformed_middle_line(self):
        """显式恢复不能掩盖中间坏行，即使文件最后一条记录是完整的。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            path.write_text(
                '{"id":"first"}\n{"id":"broken"\n{"id":"last"}',
                encoding="utf-8",
            )

            with self.assertRaises(json.JSONDecodeError):
                read_jsonl(path, recover_torn_tail=True)

    def test_read_jsonl_recovery_rejects_malformed_tail_with_newline(self):
        """带末尾换行的坏记录已完整落盘，不能被当作崩溃半行静默丢弃。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            path.write_text('{"id":"complete"}\n{"id":"broken"\n', encoding="utf-8")

            with self.assertRaises(json.JSONDecodeError):
                read_jsonl(path, recover_torn_tail=True)

    def test_read_jsonl_rejects_non_object_record(self):
        """JSONL 业务记录必须是对象，合法 JSON 数组也不能冒充记录字典。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            path.write_text('{"id":"complete"}\n["not-an-object"]', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "JSON object"):
                read_jsonl(path, recover_torn_tail=True)

    def test_atomic_write_json_creates_parent_and_writes_pretty_utf8(self):
        """atomic_write_json 应创建父目录并写入缩进 UTF-8 JSON。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested" / "snapshot.json"

            atomic_write_json(path, {"message": "你好", "count": 2})

            self.assertEqual(
                path.read_text(encoding="utf-8"),
                json.dumps(
                    {"message": "你好", "count": 2},
                    ensure_ascii=False,
                    indent=2,
                ),
            )

    def test_atomic_write_jsonl_writes_one_object_per_line(self):
        """atomic_write_jsonl 应逐行写对象并为非空记录保留末尾换行。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested" / "records.jsonl"

            atomic_write_jsonl(
                path,
                [
                    {"id": "一", "score": 1.0},
                    {"id": "二", "score": 0.5},
                ],
            )

            content = path.read_text(encoding="utf-8")
            self.assertTrue(content.endswith("\n"))
            self.assertEqual(
                content.splitlines(),
                [
                    json.dumps({"id": "一", "score": 1.0}, ensure_ascii=False),
                    json.dumps({"id": "二", "score": 0.5}, ensure_ascii=False),
                ],
            )

    def test_atomic_write_jsonl_empty_records_writes_empty_file(self):
        """atomic_write_jsonl 遇到空记录集合时应原子替换为空文件。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            path.write_text("old\n", encoding="utf-8")

            atomic_write_jsonl(path, [])

            self.assertEqual(path.read_text(encoding="utf-8"), "")

    def test_atomic_write_json_serialization_failure_preserves_target(self):
        """JSON 序列化失败时应保留旧目标且不遗留临时文件。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "snapshot.json"
            path.write_text('{"status":"old"}', encoding="utf-8")

            with self.assertRaises(TypeError):
                atomic_write_json(path, {"invalid": object()})

            self.assertEqual(path.read_text(encoding="utf-8"), '{"status":"old"}')
            self.assertEqual(list(Path(temp_dir).iterdir()), [path])

    def test_atomic_write_jsonl_write_failure_preserves_target(self):
        """JSONL 中途序列化失败时应保留旧目标且清理临时文件。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            path.write_text('{"status":"old"}\n', encoding="utf-8")

            with self.assertRaises(TypeError):
                atomic_write_jsonl(
                    path,
                    [{"id": "valid"}, {"invalid": object()}],
                )

            self.assertEqual(path.read_text(encoding="utf-8"), '{"status":"old"}\n')
            self.assertEqual(list(Path(temp_dir).iterdir()), [path])

    def test_atomic_write_json_uses_fsync_and_same_directory_replace(self):
        """原子 JSON 写入应 fsync 临时文件并从同目录替换目标。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "snapshot.json"

            with (
                mock.patch(
                    "memory_benchmark.storage.atomic.os.fsync",
                    wraps=__import__("os").fsync,
                ) as fsync_mock,
                mock.patch(
                    "memory_benchmark.storage.atomic.os.replace",
                    wraps=__import__("os").replace,
                ) as replace_mock,
            ):
                atomic_write_json(path, {"status": "new"})

            fsync_mock.assert_called_once()
            source, target = replace_mock.call_args.args
            self.assertEqual(Path(source).parent, path.parent)
            self.assertEqual(Path(target), path)

    def test_atomic_write_json_replace_failure_cleans_temporary_file(self):
        """目标替换失败时应保留旧文件并清理同目录临时文件。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "snapshot.json"
            path.write_text('{"status":"old"}', encoding="utf-8")

            with (
                mock.patch(
                    "memory_benchmark.storage.atomic.os.replace",
                    side_effect=OSError("replace failed"),
                ),
                self.assertRaisesRegex(OSError, "replace failed"),
            ):
                atomic_write_json(path, {"status": "new"})

            self.assertEqual(path.read_text(encoding="utf-8"), '{"status":"old"}')
            self.assertEqual(list(Path(temp_dir).iterdir()), [path])

    def test_atomic_write_cleanup_failure_does_not_mask_replace_failure(self):
        """临时文件清理失败时不应覆盖原始替换异常。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "snapshot.json"
            primary_error = OSError("replace failed")
            cleanup_error = OSError("cleanup failed")

            with (
                mock.patch(
                    "memory_benchmark.storage.atomic.os.replace",
                    side_effect=primary_error,
                ),
                mock.patch(
                    "memory_benchmark.storage.atomic.Path.unlink",
                    side_effect=cleanup_error,
                ),
                self.assertRaises(OSError) as raised,
            ):
                atomic_write_json(path, {"status": "new"})

            self.assertIs(raised.exception, primary_error)

    def test_atomic_write_cleanup_exists_failure_does_not_mask_replace_failure(self):
        """检查临时文件失败时不应覆盖原始替换异常。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "snapshot.json"
            primary_error = OSError("replace failed")

            with (
                mock.patch(
                    "memory_benchmark.storage.atomic.os.replace",
                    side_effect=primary_error,
                ),
                mock.patch(
                    "memory_benchmark.storage.atomic.Path.exists",
                    side_effect=PermissionError("exists failed"),
                ),
                self.assertRaises(OSError) as raised,
            ):
                atomic_write_json(path, {"status": "new"})

            self.assertIs(raised.exception, primary_error)

    def test_dataset_fingerprint_counts_conversations_and_questions(self):
        """dataset fingerprint 应记录 conversation/question 数。"""

        dataset = Dataset(
            dataset_name="fake",
            conversations=[
                Conversation(
                    conversation_id="conv-1",
                    sessions=[
                        Session(
                            session_id="s1",
                            turns=[Turn("t1", "Alice", "hello")],
                        )
                    ],
                    questions=[
                        Question("conv-1:q1", "conv-1", "Where?"),
                        Question("conv-1:q2", "conv-1", "When?"),
                    ],
                )
            ],
        )

        fingerprint = build_dataset_fingerprint(
            dataset=dataset,
            source_paths=[Path("sources/fake/data.json")],
        )

        self.assertEqual(fingerprint["dataset_name"], "fake")
        self.assertEqual(fingerprint["conversation_count"], 1)
        self.assertEqual(fingerprint["question_count"], 2)
        self.assertEqual(fingerprint["source_paths"][0]["path"], "sources/fake/data.json")

    def test_dataset_fingerprint_hashes_existing_source_file(self):
        """dataset fingerprint 应记录真实源文件的字节数和 sha256。"""

        dataset = Dataset(dataset_name="fake", conversations=[])

        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "source.json"
            source_bytes = b'{"conversation_id":"conv-1","question":"Where?"}\n'
            source_path.write_bytes(source_bytes)

            fingerprint = build_dataset_fingerprint(dataset=dataset, source_paths=[source_path])

        source_fingerprint = fingerprint["source_paths"][0]
        self.assertEqual(source_fingerprint["path"], str(source_path))
        self.assertEqual(source_fingerprint["size_bytes"], len(source_bytes))
        self.assertEqual(
            source_fingerprint["sha256"],
            hashlib.sha256(source_bytes).hexdigest(),
        )

    def test_source_fingerprint_identity_is_content_only(self):
        """相同内容在不同路径下必须得到相同的 source_fingerprint_sha256。

        path 只是 provenance 记录；若把路径混进身份哈希，换机器或挪目录会让
        resume 拒绝内容完全相同的 run。
        """

        dataset = Dataset(dataset_name="fake", conversations=[])
        source_bytes = b'{"conversation_id":"conv-1","question":"Where?"}\n'

        with tempfile.TemporaryDirectory() as temp_dir:
            path_a = Path(temp_dir) / "machine-a" / "data.json"
            path_b = Path(temp_dir) / "another" / "place" / "data-renamed.json"
            for path in (path_a, path_b):
                path.parent.mkdir(parents=True)
                path.write_bytes(source_bytes)

            fingerprint_a = build_dataset_fingerprint(
                dataset=dataset, source_paths=[path_a]
            )
            fingerprint_b = build_dataset_fingerprint(
                dataset=dataset, source_paths=[path_b]
            )

        self.assertEqual(
            fingerprint_a["source_fingerprint_sha256"],
            fingerprint_b["source_fingerprint_sha256"],
        )
        self.assertNotEqual(
            fingerprint_a["source_paths"][0]["path"],
            fingerprint_b["source_paths"][0]["path"],
        )

    def test_dataset_fingerprint_reads_source_file_in_bounded_chunks(self):
        """源文件哈希必须分块读取，不能一次把大文件全部载入内存。"""

        dataset = Dataset(dataset_name="fake", conversations=[])

        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "large-source.json"
            source_bytes = b"x" * (3 * 1024 * 1024)
            source_path.write_bytes(source_bytes)
            original_open = Path.open
            read_sizes: list[int] = []

            class TrackingReader:
                """记录每次 read 大小并转发到真实文件。"""

                def __init__(self, file_object):
                    """保存被包装的真实文件对象。"""

                    self._file_object = file_object

                def __enter__(self):
                    """进入真实文件上下文。"""

                    self._file_object.__enter__()
                    return self

                def __exit__(self, exc_type, exc_value, traceback):
                    """退出真实文件上下文。"""

                    return self._file_object.__exit__(
                        exc_type,
                        exc_value,
                        traceback,
                    )

                def read(self, size=-1):
                    """拒绝无界读取并记录每次 chunk 大小。"""

                    read_sizes.append(size)
                    if size is None or size <= 0:
                        raise AssertionError("source fingerprint read must be bounded")
                    return self._file_object.read(size)

            def tracking_open(path, mode="r", *args, **kwargs):
                """只包装目标源文件的二进制读取。"""

                file_object = original_open(path, mode, *args, **kwargs)
                if Path(path) == source_path and mode == "rb":
                    return TrackingReader(file_object)
                return file_object

            with mock.patch.object(Path, "open", tracking_open):
                fingerprint = build_dataset_fingerprint(
                    dataset=dataset,
                    source_paths=[source_path],
                )

        self.assertEqual(
            fingerprint["source_paths"][0]["sha256"],
            hashlib.sha256(source_bytes).hexdigest(),
        )
        self.assertGreater(len(read_sizes), 1)
        self.assertTrue(all(size > 0 for size in read_sizes))

    def test_dataset_fingerprint_hashes_full_normalized_dataset_deterministically(self):
        """相同规范化 Dataset 内容应生成相同 dataset_sha256。"""

        first_dataset = _build_fingerprint_dataset(gold_answer="Seattle")
        second_dataset = _build_fingerprint_dataset(gold_answer="Seattle")

        first_fingerprint = build_dataset_fingerprint(first_dataset, [])
        second_fingerprint = build_dataset_fingerprint(second_dataset, [])

        canonical_dataset = json.dumps(
            first_dataset.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(
            first_fingerprint["dataset_sha256"],
            hashlib.sha256(canonical_dataset).hexdigest(),
        )
        self.assertEqual(
            first_fingerprint["dataset_sha256"],
            second_fingerprint["dataset_sha256"],
        )

    def test_dataset_fingerprint_changes_when_gold_answer_changes(self):
        """规范化 Dataset 的 gold 或 conversation 内容变化时 hash 必须变化。"""

        original_dataset = _build_fingerprint_dataset(gold_answer="Seattle")
        original = build_dataset_fingerprint(original_dataset, [])
        changed = build_dataset_fingerprint(
            _build_fingerprint_dataset(gold_answer="Portland"),
            [],
        )
        changed_content_dataset = _build_fingerprint_dataset(gold_answer="Seattle")
        changed_content_dataset.conversations[0].sessions[0].turns[0].content = (
            "I moved to Portland."
        )
        changed_content = build_dataset_fingerprint(changed_content_dataset, [])

        self.assertNotEqual(original["dataset_sha256"], changed["dataset_sha256"])
        self.assertNotEqual(
            original["dataset_sha256"],
            changed_content["dataset_sha256"],
        )

    def test_public_question_record_rejects_private_metadata_keys(self):
        """公开问题记录遇到私有 metadata 键时必须抛 DataLeakageError。"""

        private_keys = ("gold_answer", "evidence", "judge_label", "answer_session_ids")
        for private_key in private_keys:
            with self.subTest(private_key=private_key):
                question = Question(
                    question_id=f"conv-1:{private_key}",
                    conversation_id="conv-1",
                    text="Who joined the meeting?",
                    metadata={private_key: "private-value"},
                )

                with self.assertRaises(DataLeakageError):
                    public_question_record(question)

    def test_public_question_record_contains_only_public_fields(self):
        """公开问题记录应保留公开字段且不包含标准答案、证据或 judge label。"""

        question = Question(
            question_id="conv-1:q1",
            conversation_id="conv-1",
            text="Who joined the meeting?",
            category="single-hop",
            metadata={"source_question_type": "fact"},
        )

        record = public_question_record(question)

        self.assertEqual(record["question_id"], "conv-1:q1")
        self.assertEqual(record["conversation_id"], "conv-1")
        self.assertEqual(record["question_text"], "Who joined the meeting?")
        self.assertEqual(record["category"], "single-hop")
        self.assertEqual(record["metadata"], {"source_question_type": "fact"})
        self.assertNotIn("gold_answer", record)
        self.assertNotIn("evidence", record)
        self.assertNotIn("judge_label", record)
        self.assertNotIn("answer_session_ids", record)

    def test_evaluator_private_label_record_keeps_private_fields(self):
        """evaluator-only 标签记录应保留打分所需的 gold_answer 和 evidence。"""

        gold = GoldAnswerInfo(
            question_id="conv-1:q1",
            answer="Alice",
            evidence=["turn-1", "turn-2"],
            metadata={"answer_session_ids": ["session-1"]},
        )

        record = evaluator_private_label_record(gold, category="single-hop")

        self.assertEqual(record["question_id"], "conv-1:q1")
        self.assertEqual(record["gold_answer"], "Alice")
        self.assertEqual(record["evidence"], ["turn-1", "turn-2"])
        self.assertEqual(record["category"], "single-hop")
        self.assertEqual(record["metadata"], {"answer_session_ids": ["session-1"]})

    def test_legacy_label_record_does_not_grow_v1_fields(self):
        """旧无版本 gold 序列化后保持旧 shape，不凭空加 v1 字段。"""

        gold = GoldAnswerInfo(
            question_id="conv-1:q1",
            answer="Alice",
            evidence=["turn-1"],
        )

        record = evaluator_private_label_record(gold, category=None)

        self.assertNotIn("gold_evidence_contract_version", record)
        self.assertNotIn("evidence_group_sets", record)
        self.assertEqual(
            sorted(record),
            ["category", "evidence", "gold_answer", "metadata", "question_id"],
        )

    def test_v1_label_record_serializes_group_sets_as_json_lists(self):
        """v1 label 顶层写 version 与 JSON list 形态的 evidence_group_sets。"""

        gold = GoldAnswerInfo(
            question_id="conv-1:q1",
            answer="Alice",
            evidence=["turn-1"],
            gold_evidence_contract_version="v1",
            evidence_group_sets=(
                GoldEvidenceGroupSet(
                    provenance_granularity="turn",
                    unit_kind="fake_unit",
                    groups=(
                        GoldEvidenceGroup(
                            unit_id="u1",
                            child_ids=("turn-1", "turn-2"),
                            mapping_status="mapped",
                        ),
                        GoldEvidenceGroup(
                            unit_id="u2",
                            child_ids=(),
                            mapping_status="unmatched",
                        ),
                    ),
                ),
            ),
        )

        record = evaluator_private_label_record(gold, category="single-hop")

        self.assertEqual(record["gold_evidence_contract_version"], "v1")
        self.assertIsInstance(record["evidence_group_sets"], list)
        self.assertEqual(
            record["evidence_group_sets"],
            [
                {
                    "provenance_granularity": "turn",
                    "unit_kind": "fake_unit",
                    "groups": [
                        {
                            "unit_id": "u1",
                            "child_ids": ["turn-1", "turn-2"],
                            "mapping_status": "mapped",
                        },
                        {
                            "unit_id": "u2",
                            "child_ids": [],
                            "mapping_status": "unmatched",
                        },
                    ],
                }
            ],
        )
        # 序列化必须直接 JSON 可写，list/dict 形态在 json.dumps 下无损。
        self.assertEqual(
            json.loads(json.dumps(record, ensure_ascii=False))["evidence_group_sets"],
            record["evidence_group_sets"],
        )


def _build_fingerprint_dataset(gold_answer: str) -> Dataset:
    """构造包含公开内容和私有 gold 的指纹测试数据集。"""

    question = Question("conv-1:q1", "conv-1", "Where did Alice move?")
    return Dataset(
        dataset_name="fake",
        conversations=[
            Conversation(
                conversation_id="conv-1",
                sessions=[
                    Session(
                        session_id="s1",
                        turns=[Turn("t1", "Alice", "I moved to Seattle.")],
                    )
                ],
                questions=[question],
                gold_answers={
                    question.question_id: GoldAnswerInfo(
                        question.question_id,
                        gold_answer,
                    )
                },
            )
        ],
    )


if __name__ == "__main__":
    unittest.main()
