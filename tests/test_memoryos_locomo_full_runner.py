"""测试 MemoryOS-LoCoMo 全量 F1 runner。

本文件不访问真实 LLM。测试通过 fake MemoryOS 和小型 fake Dataset 验证正式 runner
的核心行为：按 conversation 隔离写入、逐题输出预测和 F1、生成 summary，以及
resume 时不重复 add 已完成 conversation。
"""

from __future__ import annotations

import inspect
import json
import re
import tempfile
import traceback
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

from memory_benchmark.core import (
    AddResult,
    AnswerResult,
    ConfigurationError,
    Conversation,
    Dataset,
    DataLeakageError,
    GoldAnswerInfo,
    Question,
    Session,
    Turn,
)
from memory_benchmark.observability import ProgressReporter
from memory_benchmark.methods import get_method_registration
from memory_benchmark.runners import memoryos_locomo_full as runner_module
from memory_benchmark.runners.memoryos_locomo_full import run_memoryos_locomo_full
from memory_benchmark.storage import (
    atomic_write_json,
    atomic_write_jsonl,
    build_dataset_fingerprint,
    evaluator_private_label_record,
    public_question_record,
)
from memory_benchmark.utils.run_logger import RunLogger


pytestmark = [pytest.mark.integration, pytest.mark.memoryos]


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeMemoryOS:
    """测试用 MemoryOS fake，记录 add/attach/get_answer 调用。"""

    instances: list["FakeMemoryOS"] = []

    def __init__(self, *args, **kwargs):
        """保存初始化参数并登记实例。"""

        self.args = args
        self.kwargs = kwargs
        self.added_conversation_ids: list[str] = []
        self.attached_conversation_ids: list[str] = []
        self.answered_question_ids: list[str] = []
        FakeMemoryOS.instances.append(self)

    def add(self, conversations: list[Conversation]) -> AddResult:
        """记录被写入的 conversation ids。"""

        ids = [conversation.conversation_id for conversation in conversations]
        self.added_conversation_ids.extend(ids)
        return AddResult(conversation_ids=ids)

    def load_existing_conversation_state(self, conversation: Conversation) -> None:
        """记录 runner 请求 attach 的 conversation id。"""

        self.attached_conversation_ids.append(conversation.conversation_id)

    def get_answer(self, question: Question) -> AnswerResult:
        """返回预置答案，模拟 MemoryOS 回答。"""

        self.answered_question_ids.append(question.question_id)
        answers = {
            "conv-a:q1": "Seattle",
            "conv-a:q2": "tea",
            "conv-b:q1": "wrong",
        }
        return AnswerResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer=answers[question.question_id],
        )


class MemoryOSLoCoMoFullRunnerTests(unittest.TestCase):
    """验证 MemoryOS-LoCoMo full runner 的输出和恢复行为。"""

    def setUp(self):
        """清空 fake MemoryOS 实例记录。"""

        FakeMemoryOS.instances = []

    def test_legacy_memoryos_runner_remains_callable_but_is_not_registered(self):
        """旧入口仍可导入，但统一 registry 的 system factory 不应指向它。"""

        registration = get_method_registration("memoryos")

        self.assertTrue(callable(run_memoryos_locomo_full))
        self.assertIsNot(
            registration.system_factory,
            run_memoryos_locomo_full,
        )
        self.assertNotIn(
            "run_memoryos_locomo_full",
            inspect.getclosurevars(registration.system_factory).globals,
        )
        self.assertIsNot(
            registration.system_factory,
            runner_module.run_memoryos_locomo_full,
        )

    def test_full_runner_writes_predictions_scores_and_summary(self):
        """runner 应逐题写预测、F1 明细和聚合 summary。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            with _patched_full_runner_dependencies(dataset):
                summary = run_memoryos_locomo_full(
                    project_root=PROJECT_ROOT,
                    output_root=Path(temp_dir),
                    run_id="unit-full",
                    show_progress=False,
                )

            run_dir = Path(temp_dir) / "unit-full"
            predictions = _read_jsonl(run_dir / "predictions.jsonl")
            scores = _read_jsonl(run_dir / "scores.jsonl")
            legacy_summary_payload = json.loads(
                (run_dir / "summary.json").read_text(encoding="utf-8")
            )
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            redacted_config = json.loads(
                (run_dir / "config.redacted.json").read_text(encoding="utf-8")
            )
            public_questions = _read_jsonl(run_dir / "artifacts" / "public_questions.jsonl")
            artifact_predictions = _read_jsonl(
                run_dir / "artifacts" / "method_predictions.jsonl"
            )
            private_labels = _read_jsonl(
                run_dir / "artifacts" / "evaluator_private_labels.jsonl"
            )
            artifact_scores = _read_jsonl(
                run_dir / "artifacts" / "answer_scores.locomo_f1.jsonl"
            )
            fingerprint = json.loads(
                (run_dir / "artifacts" / "dataset_fingerprint.json").read_text(
                    encoding="utf-8"
                )
            )
            canonical_summary_payload = json.loads(
                (run_dir / "summaries" / "summary.json").read_text(encoding="utf-8")
            )
            canonical_status_payload = json.loads(
                (run_dir / "checkpoints" / "conversation_status.json").read_text(
                    encoding="utf-8"
                )
            )
            legacy_status_payload = json.loads(
                (run_dir / "conversation_status.json").read_text(encoding="utf-8")
            )
            progress = json.loads(
                (run_dir / "checkpoints" / "progress.json").read_text(
                    encoding="utf-8"
                )
            )
            events = _read_jsonl(run_dir / "logs" / "events.jsonl")

        self.assertEqual(summary.total_questions, 3)
        self.assertEqual(summary.completed_questions, 3)
        self.assertEqual(summary.overall_f1, 2 / 3)
        self.assertEqual(summary.f1_by_category["2"], 0.5)
        self.assertEqual(summary.f1_by_category["1"], 1.0)
        self.assertEqual(len(predictions), 3)
        self.assertEqual(len(scores), 3)
        self.assertEqual(legacy_summary_payload["completed_questions"], 3)
        self.assertEqual(manifest["run_id"], "unit-full")
        self.assertEqual(manifest["benchmark_name"], "locomo")
        self.assertEqual(manifest["method_name"], "MemoryOS")
        self.assertIn("memoryos_config", redacted_config)
        self.assertEqual(fingerprint["question_count"], 3)
        self.assertRegex(fingerprint["dataset_sha256"], re.compile(r"^[0-9a-f]{64}$"))
        self.assertEqual(len(public_questions), 3)
        self.assertEqual(len(artifact_predictions), 3)
        self.assertEqual(len(private_labels), 3)
        self.assertEqual(len(artifact_scores), 3)
        self.assertNotIn("gold_answer", public_questions[0])
        self.assertNotIn("gold_answer", artifact_predictions[0])
        self.assertIn("gold_answer", private_labels[0])
        self.assertEqual(canonical_summary_payload["completed_questions"], 3)
        self.assertEqual(canonical_status_payload, {"conv-a": "added", "conv-b": "added"})
        self.assertEqual(legacy_status_payload, canonical_status_payload)
        self.assertEqual(
            summary.prediction_path,
            str((run_dir / "artifacts" / "method_predictions.jsonl").resolve()),
        )
        self.assertEqual(
            summary.score_path,
            str((run_dir / "artifacts" / "answer_scores.locomo_f1.jsonl").resolve()),
        )
        self.assertEqual(
            summary.summary_path,
            str((run_dir / "summaries" / "summary.json").resolve()),
        )
        self.assertEqual(progress["stage"], "Write summary")
        self.assertEqual(progress["question_completed"], 3)
        self.assertEqual(progress["question_total"], 3)
        self.assertEqual(progress["conversation_completed"], 2)
        self.assertEqual(progress["conversation_total"], 2)
        self.assertIsNone(progress["current_conversation_id"])
        self.assertIsNone(progress["current_question_id"])
        self.assertEqual(FakeMemoryOS.instances[0].added_conversation_ids, ["conv-a", "conv-b"])
        event_names = [event["event"] for event in events]
        self.assertEqual(event_names[0], "full_run_started")
        self.assertLess(event_names.index("full_run_started"), event_names.index("dataset_loaded"))
        self.assertLess(event_names.index("dataset_loaded"), event_names.index("method_configured"))
        self.assertLess(event_names.index("method_configured"), event_names.index("conversation_added"))
        self.assertLess(event_names.index("conversation_added"), event_names.index("question_scored"))
        self.assertEqual(event_names[-1], "full_run_finished")

        attempt_ids = {event["payload"]["attempt_id"] for event in events}
        self.assertEqual(len(attempt_ids), 1)
        for event in events:
            self.assertIs(event["payload"]["resume"], True)

        started_payload = events[0]["payload"]
        self.assertEqual(started_payload["run_id"], "unit-full")
        self.assertIs(started_payload["confirm_expensive"], False)
        self.assertRegex(started_payload["attempt_id"], re.compile(r"^[0-9a-f]{32}$"))

        method_payload = next(
            event["payload"] for event in events if event["event"] == "method_configured"
        )
        self.assertEqual(method_payload["method_name"], "MemoryOS")
        self.assertEqual(
            set(method_payload["config"]),
            {
                "llm_model",
                "embedding_model_name",
                "short_term_capacity",
                "mid_term_capacity",
                "long_term_knowledge_capacity",
                "mid_term_heat_threshold",
                "mid_term_similarity_threshold",
                "top_k_sessions",
                "retrieval_queue_capacity",
                "segment_similarity_threshold",
                "page_similarity_threshold",
                "knowledge_threshold",
            },
        )
        self.assertRegex(
            method_payload["config_fingerprint"],
            re.compile(r"^[0-9a-f]{64}$"),
        )

        forbidden_keys = {
            "api_key",
            "base_url",
            "prompt",
            "secret",
            "gold_answer",
            "evidence",
            "judge_label",
            "answer_session_ids",
            "exception_message",
            "traceback",
        }
        for event in events:
            self.assertEqual(
                _find_forbidden_keys(event["payload"], forbidden_keys),
                set(),
                event["event"],
            )

    def test_resume_uses_existing_state_and_skips_completed_questions(self):
        """resume 时已完成 question 不应重复回答，已 add conversation 应 attach 状态。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-resume"
            run_dir.mkdir(parents=True)
            _seed_matching_dataset_fingerprint(run_dir, dataset)
            _write_json(
                run_dir / "conversation_status.json",
                {
                    "conv-a": "added",
                    "outside-current-plan": "added",
                },
            )
            _append_jsonl(
                run_dir / "predictions.jsonl",
                {
                    "conversation_id": "conv-a",
                    "question_id": "conv-a:q1",
                    "question_text": "Where did Alice move?",
                    "prediction_answer": "Seattle",
                },
            )
            _append_jsonl(
                run_dir / "scores.jsonl",
                {
                    "conversation_id": "conv-a",
                    "question_id": "conv-a:q1",
                    "category": "2",
                    "f1": 1.0,
                },
            )

            with _patched_full_runner_dependencies(dataset):
                summary = run_memoryos_locomo_full(
                    project_root=PROJECT_ROOT,
                    output_root=Path(temp_dir),
                    run_id="unit-resume",
                    resume=True,
                    show_progress=False,
                )

            scores = _read_jsonl(run_dir / "scores.jsonl")
            canonical_scores = _read_jsonl(
                run_dir / "artifacts" / "answer_scores.locomo_f1.jsonl"
            )
            canonical_status_payload = json.loads(
                (run_dir / "checkpoints" / "conversation_status.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(summary.completed_questions, 3)
        self.assertEqual(summary.completed_conversations, 2)
        self.assertEqual(FakeMemoryOS.instances[0].attached_conversation_ids, ["conv-a"])
        self.assertEqual(FakeMemoryOS.instances[0].added_conversation_ids, ["conv-b"])
        self.assertEqual(FakeMemoryOS.instances[0].answered_question_ids, ["conv-a:q2", "conv-b:q1"])
        self.assertEqual(len(scores), 3)
        self.assertEqual(len(canonical_scores), 3)
        self.assertEqual(
            canonical_status_payload,
            {
                "conv-a": "added",
                "outside-current-plan": "added",
                "conv-b": "added",
            },
        )

    def test_resume_reconciles_legacy_and_canonical_jsonl_by_question_id(self):
        """resume 应按 question_id 合并 canonical 与 legacy JSONL 的互补记录。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-reconcile"
            artifacts_dir = run_dir / "artifacts"
            checkpoints_dir = run_dir / "checkpoints"
            artifacts_dir.mkdir(parents=True)
            checkpoints_dir.mkdir(parents=True)
            _seed_matching_dataset_fingerprint(run_dir, dataset)
            _write_json(checkpoints_dir / "conversation_status.json", {"conv-a": "added"})
            _append_jsonl(
                artifacts_dir / "method_predictions.jsonl",
                _prediction_record("conv-a:q1", "conv-a", "Where did Alice move?", "Seattle", "2"),
            )
            _append_jsonl(
                run_dir / "predictions.jsonl",
                _prediction_record("conv-a:q2", "conv-a", "What drink does Alice like?", "tea", "1"),
            )
            _append_jsonl(
                artifacts_dir / "answer_scores.locomo_f1.jsonl",
                _score_record("conv-a:q1", "conv-a", "2", 1.0),
            )
            _append_jsonl(
                run_dir / "scores.jsonl",
                _score_record("conv-a:q2", "conv-a", "1", 1.0),
            )

            with _patched_full_runner_dependencies(dataset):
                summary = run_memoryos_locomo_full(
                    project_root=PROJECT_ROOT,
                    output_root=Path(temp_dir),
                    run_id="unit-reconcile",
                    resume=True,
                    show_progress=False,
                )

            canonical_predictions = _read_jsonl(
                artifacts_dir / "method_predictions.jsonl"
            )
            legacy_predictions = _read_jsonl(run_dir / "predictions.jsonl")
            canonical_scores = _read_jsonl(artifacts_dir / "answer_scores.locomo_f1.jsonl")
            legacy_scores = _read_jsonl(run_dir / "scores.jsonl")

        self.assertEqual(summary.completed_questions, 3)
        self.assertEqual(
            [record["question_id"] for record in canonical_predictions],
            ["conv-a:q1", "conv-a:q2", "conv-b:q1"],
        )
        self.assertEqual(canonical_predictions, legacy_predictions)
        self.assertEqual(canonical_scores, legacy_scores)
        self.assertEqual(FakeMemoryOS.instances[0].answered_question_ids, ["conv-b:q1"])

    def test_resume_recovers_torn_canonical_alias_from_healthy_legacy_alias(self):
        """canonical 尾行截断时，resume 应使用健康 legacy 记录并修复两侧文件。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-torn-canonical"
            artifacts_dir = run_dir / "artifacts"
            checkpoints_dir = run_dir / "checkpoints"
            _seed_matching_dataset_fingerprint(run_dir, dataset)
            _write_json(checkpoints_dir / "conversation_status.json", {"conv-a": "added"})

            first_prediction = _prediction_record(
                "conv-a:q1",
                "conv-a",
                "Where did Alice move?",
                "Seattle",
                "2",
            )
            second_prediction = _prediction_record(
                "conv-a:q2",
                "conv-a",
                "What drink does Alice like?",
                "tea",
                "1",
            )
            canonical_prediction_path = artifacts_dir / "method_predictions.jsonl"
            legacy_prediction_path = run_dir / "predictions.jsonl"
            _append_jsonl(canonical_prediction_path, first_prediction)
            with canonical_prediction_path.open("a", encoding="utf-8") as file:
                file.write('{"question_id":"conv-a:q2"')
            _append_jsonl(legacy_prediction_path, first_prediction)
            _append_jsonl(legacy_prediction_path, second_prediction)

            for score_path in (
                artifacts_dir / "answer_scores.locomo_f1.jsonl",
                run_dir / "scores.jsonl",
            ):
                _append_jsonl(score_path, _score_record("conv-a:q1", "conv-a", "2", 1.0))
                _append_jsonl(score_path, _score_record("conv-a:q2", "conv-a", "1", 1.0))

            with _patched_full_runner_dependencies(dataset):
                summary = run_memoryos_locomo_full(
                    project_root=PROJECT_ROOT,
                    output_root=Path(temp_dir),
                    run_id="unit-torn-canonical",
                    resume=True,
                    show_progress=False,
                )

            canonical_predictions = _read_jsonl(canonical_prediction_path)
            legacy_predictions = _read_jsonl(legacy_prediction_path)

        self.assertEqual(summary.completed_questions, 3)
        self.assertEqual(canonical_predictions, legacy_predictions)
        self.assertEqual(
            [record["question_id"] for record in canonical_predictions],
            ["conv-a:q1", "conv-a:q2", "conv-b:q1"],
        )
        self.assertEqual(FakeMemoryOS.instances[0].answered_question_ids, ["conv-b:q1"])

    def test_resume_drops_torn_tail_from_both_aliases_and_reanswers_question(self):
        """两侧同为截断尾行时，只复用完整记录并重新回答损坏记录对应的问题。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-both-aliases-torn"
            artifacts_dir = run_dir / "artifacts"
            checkpoints_dir = run_dir / "checkpoints"
            _seed_matching_dataset_fingerprint(run_dir, dataset)
            _write_json(checkpoints_dir / "conversation_status.json", {"conv-a": "added"})

            first_prediction = _prediction_record(
                "conv-a:q1",
                "conv-a",
                "Where did Alice move?",
                "Seattle",
                "2",
            )
            prediction_paths = (
                artifacts_dir / "method_predictions.jsonl",
                run_dir / "predictions.jsonl",
            )
            for prediction_path in prediction_paths:
                _append_jsonl(prediction_path, first_prediction)
                with prediction_path.open("a", encoding="utf-8") as file:
                    file.write('{"question_id":"conv-a:q2"')

            for score_path in (
                artifacts_dir / "answer_scores.locomo_f1.jsonl",
                run_dir / "scores.jsonl",
            ):
                _append_jsonl(score_path, _score_record("conv-a:q1", "conv-a", "2", 1.0))

            with _patched_full_runner_dependencies(dataset):
                summary = run_memoryos_locomo_full(
                    project_root=PROJECT_ROOT,
                    output_root=Path(temp_dir),
                    run_id="unit-both-aliases-torn",
                    resume=True,
                    show_progress=False,
                )

            canonical_predictions = _read_jsonl(prediction_paths[0])
            legacy_predictions = _read_jsonl(prediction_paths[1])

        self.assertEqual(summary.completed_questions, 3)
        self.assertEqual(canonical_predictions, legacy_predictions)
        self.assertEqual(
            [record["question_id"] for record in canonical_predictions],
            ["conv-a:q1", "conv-a:q2", "conv-b:q1"],
        )
        self.assertEqual(
            FakeMemoryOS.instances[0].answered_question_ids,
            ["conv-a:q2", "conv-b:q1"],
        )

    def test_resume_rejects_conflicting_duplicate_question_records(self):
        """resume 遇到同一 question_id 的冲突记录时应失败，而不是任选一侧。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-conflict"
            artifacts_dir = run_dir / "artifacts"
            artifacts_dir.mkdir(parents=True)
            _seed_matching_dataset_fingerprint(run_dir, dataset)
            _append_jsonl(
                artifacts_dir / "method_predictions.jsonl",
                _prediction_record("conv-a:q1", "conv-a", "Where did Alice move?", "Seattle", "2"),
            )
            _append_jsonl(
                run_dir / "predictions.jsonl",
                _prediction_record("conv-a:q1", "conv-a", "Where did Alice move?", "Portland", "2"),
            )

            with _patched_full_runner_dependencies(dataset):
                with self.assertRaises(ConfigurationError):
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-conflict",
                        resume=True,
                        show_progress=False,
                    )

    def test_resume_scores_existing_prediction_without_answering_again(self):
        """prediction 已存在但 score 缺失时，应复用预测补评分而不重复 get_answer。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-prediction-only"
            run_dir.mkdir(parents=True)
            _seed_matching_dataset_fingerprint(run_dir, dataset)
            _write_json(run_dir / "conversation_status.json", {"conv-a": "added"})
            _append_jsonl(
                run_dir / "predictions.jsonl",
                _prediction_record("conv-a:q1", "conv-a", "Where did Alice move?", "Seattle", "2"),
            )

            with _patched_full_runner_dependencies(dataset):
                summary = run_memoryos_locomo_full(
                    project_root=PROJECT_ROOT,
                    output_root=Path(temp_dir),
                    run_id="unit-prediction-only",
                    resume=True,
                    show_progress=False,
                )

            scores = _read_jsonl(run_dir / "scores.jsonl")

        self.assertEqual(summary.completed_questions, 3)
        self.assertIn("conv-a:q1", {record["question_id"] for record in scores})
        self.assertEqual(FakeMemoryOS.instances[0].answered_question_ids, ["conv-a:q2", "conv-b:q1"])

    def test_resume_rejects_score_without_matching_prediction_before_memoryos(self):
        """score 缺少同 id prediction 时应在构造 MemoryOS 和跳题前失败。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-score-only"
            with _patched_full_runner_dependencies(dataset):
                run_memoryos_locomo_full(
                    project_root=PROJECT_ROOT,
                    output_root=Path(temp_dir),
                    run_id="unit-score-only",
                    resume=True,
                    show_progress=False,
                )

            prediction_paths = (
                run_dir / "artifacts" / "method_predictions.jsonl",
                run_dir / "predictions.jsonl",
            )
            retained_predictions = [
                record
                for record in _read_jsonl(prediction_paths[0])
                if record["question_id"] != "conv-a:q1"
            ]
            for prediction_path in prediction_paths:
                atomic_write_jsonl(prediction_path, retained_predictions)
            FakeMemoryOS.instances = []

            with _patched_full_runner_dependencies(dataset):
                with self.assertRaisesRegex(
                    ConfigurationError,
                    "score.*prediction",
                ):
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-score-only",
                        resume=True,
                        show_progress=False,
                    )

        self.assertEqual(FakeMemoryOS.instances, [])

    def test_resume_rejects_records_outside_planned_questions(self):
        """resume 不能把当前数据集计划之外的 prediction/score 计入完成结果。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-outside-plan-record"
            artifacts_dir = run_dir / "artifacts"
            _seed_matching_dataset_fingerprint(run_dir, dataset)
            prediction_path = artifacts_dir / "method_predictions.jsonl"
            score_path = artifacts_dir / "answer_scores.locomo_f1.jsonl"
            _append_jsonl(
                prediction_path,
                _prediction_record(
                    "outside:q1",
                    "outside",
                    "Unknown question",
                    "unknown",
                    "1",
                ),
            )
            _append_jsonl(
                score_path,
                _score_record("outside:q1", "outside", "1", 1.0),
            )
            original_prediction = prediction_path.read_bytes()
            original_score = score_path.read_bytes()

            with _patched_full_runner_dependencies(dataset):
                with self.assertRaisesRegex(
                    ConfigurationError,
                    "planned question",
                ):
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-outside-plan-record",
                        resume=True,
                        show_progress=False,
                    )

            self.assertEqual(prediction_path.read_bytes(), original_prediction)
            self.assertEqual(score_path.read_bytes(), original_score)

        self.assertEqual(FakeMemoryOS.instances, [])

    def test_resume_rejects_record_conversation_id_mismatch(self):
        """resume 记录的 question_id 合法但 conversation_id 错配时必须拒绝。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-record-conversation-mismatch"
            artifacts_dir = run_dir / "artifacts"
            _seed_matching_dataset_fingerprint(run_dir, dataset)
            _append_jsonl(
                artifacts_dir / "method_predictions.jsonl",
                _prediction_record(
                    "conv-a:q1",
                    "conv-b",
                    "Where did Alice move?",
                    "Seattle",
                    "2",
                ),
            )
            _append_jsonl(
                artifacts_dir / "answer_scores.locomo_f1.jsonl",
                _score_record("conv-a:q1", "conv-b", "2", 1.0),
            )

            with _patched_full_runner_dependencies(dataset):
                with self.assertRaisesRegex(
                    ConfigurationError,
                    "conversation_id",
                ):
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-record-conversation-mismatch",
                        resume=True,
                        show_progress=False,
                    )

        self.assertEqual(FakeMemoryOS.instances, [])

    def test_score_only_preflight_does_not_mutate_resume_business_artifacts(self):
        """score-only 失败应发生在 alias/status/progress 业务产物改写之前。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-score-only-preflight"
            artifacts_dir = run_dir / "artifacts"
            checkpoints_dir = run_dir / "checkpoints"
            _seed_matching_dataset_fingerprint(run_dir, dataset)
            paths = {
                "canonical_predictions": artifacts_dir / "method_predictions.jsonl",
                "legacy_predictions": run_dir / "predictions.jsonl",
                "canonical_scores": artifacts_dir / "answer_scores.locomo_f1.jsonl",
                "legacy_scores": run_dir / "scores.jsonl",
                "canonical_status": checkpoints_dir / "conversation_status.json",
                "legacy_status": run_dir / "conversation_status.json",
                "progress": checkpoints_dir / "progress.json",
            }
            _append_jsonl(
                paths["canonical_predictions"],
                _prediction_record(
                    "conv-a:q2",
                    "conv-a",
                    "What drink does Alice like?",
                    "tea",
                    "1",
                ),
            )
            _append_jsonl(
                paths["legacy_predictions"],
                _prediction_record(
                    "conv-b:q1",
                    "conv-b",
                    "Where did Bob move?",
                    "wrong",
                    "2",
                ),
            )
            _append_jsonl(
                paths["canonical_scores"],
                _score_record("conv-a:q1", "conv-a", "2", 1.0),
            )
            _append_jsonl(
                paths["canonical_scores"],
                _score_record("conv-a:q2", "conv-a", "1", 1.0),
            )
            _append_jsonl(
                paths["legacy_scores"],
                _score_record("conv-b:q1", "conv-b", "2", 0.0),
            )
            _write_json(paths["canonical_status"], {"conv-a": "added"})
            _write_json(paths["legacy_status"], {"conv-b": "added"})
            _write_json(paths["progress"], {"stage": "existing-progress"})
            original_bytes = {
                name: path.read_bytes() for name, path in paths.items()
            }

            with _patched_full_runner_dependencies(dataset):
                with self.assertRaisesRegex(
                    ConfigurationError,
                    "score.*prediction",
                ):
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-score-only-preflight",
                        resume=True,
                        show_progress=False,
                    )

            for name, path in paths.items():
                self.assertEqual(
                    path.read_bytes(),
                    original_bytes[name],
                    name,
                )

        self.assertEqual(FakeMemoryOS.instances, [])

    def test_resume_rejects_run_shaping_config_mismatch(self):
        """resume 时已有 manifest 与当前 run-shaping 配置不一致必须报错。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-config-mismatch"
            run_dir.mkdir(parents=True)
            _seed_matching_dataset_fingerprint(run_dir, dataset)
            _write_json(
                run_dir / "manifest.json",
                {
                    "benchmark_name": "locomo",
                    "method_name": "MemoryOS",
                    "model_name": "gpt-4o-mini",
                    "conversation_limit": 1,
                    "question_limit_per_conversation": None,
                },
            )

            with _patched_full_runner_dependencies(dataset):
                with self.assertRaises(ConfigurationError):
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-config-mismatch",
                        conversation_limit=None,
                        resume=True,
                        show_progress=False,
                    )

    def test_resume_rejects_memoryos_config_mismatch(self):
        """resume 时既有 MemoryOS 配置与当前配置不一致必须报错。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-memoryos-config-mismatch"
            run_dir.mkdir(parents=True)
            _seed_matching_dataset_fingerprint(run_dir, dataset)
            _write_json(
                run_dir / "manifest.json",
                {
                    "benchmark_name": "locomo",
                    "method_name": "MemoryOS",
                    "model_name": "gpt-4o-mini",
                    "conversation_limit": None,
                    "question_limit_per_conversation": None,
                },
            )
            _write_json(
                run_dir / "config.redacted.json",
                {
                    "memoryos_config": {"short_term_capacity": 999},
                    "secrets": "redacted",
                },
            )

            with _patched_full_runner_dependencies(dataset):
                with self.assertRaises(ConfigurationError):
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-memoryos-config-mismatch",
                        resume=True,
                        show_progress=False,
                    )

    def test_resume_validates_redacted_config_even_when_manifest_config_matches(self):
        """manifest 配置匹配时，已存在的 redacted config 也必须兼容。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-stale-redacted-config"
            _seed_matching_dataset_fingerprint(run_dir, dataset)
            _write_json(
                run_dir / "config.redacted.json",
                {
                    "memoryos_config": {"short_term_capacity": 999},
                    "secrets": "redacted",
                },
            )

            with _patched_full_runner_dependencies(dataset):
                with self.assertRaisesRegex(
                    ConfigurationError,
                    "config.redacted.*memoryos_config",
                ):
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-stale-redacted-config",
                        resume=True,
                        show_progress=False,
                    )

        self.assertEqual(FakeMemoryOS.instances, [])

    def test_resume_requires_memoryos_config_from_manifest_or_redacted_config(self):
        """manifest 缺配置且无 redacted config 时应在改写状态前拒绝 resume。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-missing-memoryos-config"
            _seed_matching_dataset_fingerprint(run_dir, dataset)
            config = runner_module.MemoryOSPaperConfig()
            _write_json(
                run_dir / "manifest.json",
                {
                    "benchmark_name": "locomo",
                    "method_name": "MemoryOS",
                    "model_name": config.llm_model,
                    "conversation_limit": None,
                    "question_limit_per_conversation": None,
                },
            )
            (run_dir / "config.redacted.json").unlink()
            status_path = run_dir / "conversation_status.json"
            progress_path = run_dir / "checkpoints" / "progress.json"
            _write_json(status_path, {"conv-a": "added"})
            _write_json(progress_path, {"stage": "existing-progress"})
            original_status = status_path.read_bytes()
            original_progress = progress_path.read_bytes()

            with _patched_full_runner_dependencies(dataset):
                with self.assertRaisesRegex(
                    ConfigurationError,
                    "config.redacted",
                ):
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-missing-memoryos-config",
                        resume=True,
                        show_progress=False,
                    )

            self.assertEqual(status_path.read_bytes(), original_status)
            self.assertEqual(progress_path.read_bytes(), original_progress)
            self.assertFalse(
                (run_dir / "checkpoints" / "conversation_status.json").exists()
            )

        self.assertEqual(FakeMemoryOS.instances, [])

    def test_resume_rejects_missing_manifest_before_mutating_reusable_state(self):
        """已有可复用状态但缺 manifest 时应在构造 method 和改写产物前失败。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-missing-manifest"
            _seed_matching_dataset_fingerprint(run_dir, dataset)
            (run_dir / "manifest.json").unlink()
            status_path = run_dir / "conversation_status.json"
            prediction_path = run_dir / "predictions.jsonl"
            score_path = run_dir / "scores.jsonl"
            progress_path = run_dir / "checkpoints" / "progress.json"
            _write_json(status_path, {"conv-a": "added"})
            _append_jsonl(
                prediction_path,
                _prediction_record(
                    "conv-a:q1",
                    "conv-a",
                    "Where did Alice move?",
                    "Seattle",
                    "2",
                ),
            )
            _append_jsonl(
                score_path,
                _score_record("conv-a:q1", "conv-a", "2", 1.0),
            )
            _write_json(
                run_dir / "config.redacted.json",
                {
                    "memoryos_config": {"short_term_capacity": 999},
                    "secrets": "redacted",
                },
            )
            _write_json(progress_path, {"stage": "existing-progress"})
            original_status = status_path.read_bytes()
            original_predictions = prediction_path.read_bytes()
            original_scores = score_path.read_bytes()
            original_progress = progress_path.read_bytes()

            with _patched_full_runner_dependencies(dataset):
                with self.assertRaisesRegex(
                    ConfigurationError,
                    "manifest",
                ):
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-missing-manifest",
                        resume=True,
                        show_progress=False,
                    )

            self.assertEqual(status_path.read_bytes(), original_status)
            self.assertEqual(prediction_path.read_bytes(), original_predictions)
            self.assertEqual(score_path.read_bytes(), original_scores)
            self.assertEqual(progress_path.read_bytes(), original_progress)
            self.assertFalse(
                (run_dir / "checkpoints" / "conversation_status.json").exists()
            )
            self.assertFalse(
                (run_dir / "artifacts" / "method_predictions.jsonl").exists()
            )
            self.assertFalse(
                (run_dir / "artifacts" / "answer_scores.locomo_f1.jsonl").exists()
            )

        self.assertEqual(FakeMemoryOS.instances, [])

    def test_resume_migrates_old_checkpoint_status_jsonl_path(self):
        """旧版 checkpoints/conversation_status.jsonl 应迁移到新的 JSON 路径。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-status-migration"
            checkpoints_dir = run_dir / "checkpoints"
            checkpoints_dir.mkdir(parents=True)
            _seed_matching_dataset_fingerprint(run_dir, dataset)
            _write_json(checkpoints_dir / "conversation_status.jsonl", {"conv-a": "added"})

            with _patched_full_runner_dependencies(dataset):
                summary = run_memoryos_locomo_full(
                    project_root=PROJECT_ROOT,
                    output_root=Path(temp_dir),
                    run_id="unit-status-migration",
                    resume=True,
                    show_progress=False,
                )

            canonical_status_payload = json.loads(
                (checkpoints_dir / "conversation_status.json").read_text(encoding="utf-8")
            )

        self.assertEqual(summary.completed_conversations, 2)
        self.assertEqual(FakeMemoryOS.instances[0].attached_conversation_ids, ["conv-a"])
        self.assertEqual(canonical_status_payload, {"conv-a": "added", "conv-b": "added"})

    def test_private_question_metadata_is_rejected_before_get_answer(self):
        """公开 question metadata 出现私有键时，应在调用 get_answer 前抛错。"""

        dataset = build_fake_locomo_dataset()
        dataset.conversations[0].questions[0].metadata["gold_answer"] = "Seattle"
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-private-key"
            artifacts_dir = run_dir / "artifacts"
            run_dir.mkdir(parents=True)
            artifacts_dir.mkdir(parents=True)
            _seed_matching_dataset_fingerprint(run_dir, dataset)
            (artifacts_dir / "public_questions.jsonl").write_text("", encoding="utf-8")
            (artifacts_dir / "evaluator_private_labels.jsonl").write_text(
                "",
                encoding="utf-8",
            )
            _write_json(run_dir / "conversation_status.json", {"conv-a": "added"})
            _append_jsonl(
                run_dir / "predictions.jsonl",
                _prediction_record("conv-a:q2", "conv-a", "What drink does Alice like?", "tea", "1"),
            )
            _append_jsonl(
                run_dir / "scores.jsonl",
                _score_record("conv-a:q2", "conv-a", "1", 1.0),
            )

            with _patched_full_runner_dependencies(dataset):
                with self.assertRaises(DataLeakageError):
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-private-key",
                        resume=True,
                        show_progress=False,
                    )

        self.assertEqual(FakeMemoryOS.instances[0].answered_question_ids, [])

    def test_resume_initializes_progress_before_memoryos_construction_failure(self):
        """resume 应在 MemoryOS 构造前恢复当前计划内的完成计数。"""

        dataset = build_fake_locomo_dataset()

        class FailingMemoryOS:
            """构造时失败的 MemoryOS fake。"""

            def __init__(self, *args, **kwargs):
                """模拟 method 初始化失败。"""

                raise RuntimeError("memoryos construction failed")

        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-resume-progress"
            run_dir.mkdir(parents=True)
            _seed_matching_dataset_fingerprint(run_dir, dataset)
            _write_json(
                run_dir / "conversation_status.json",
                {
                    "conv-a": "added",
                    "outside-current-plan": "added",
                },
            )
            _append_jsonl(
                run_dir / "predictions.jsonl",
                _prediction_record(
                    "conv-a:q1",
                    "conv-a",
                    "Where did Alice move?",
                    "Seattle",
                    "2",
                ),
            )
            _append_jsonl(
                run_dir / "scores.jsonl",
                _score_record("conv-a:q1", "conv-a", "2", 1.0),
            )
            adapter = type(
                "FakeLoCoMoAdapter",
                (),
                {"load": lambda self, limit=None: dataset},
            )

            with patch.multiple(
                "memory_benchmark.runners.memoryos_locomo_full",
                LoCoMoAdapter=lambda project_root: adapter(),
                MemoryOS=FailingMemoryOS,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "memoryos construction failed",
                ):
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-resume-progress",
                        resume=True,
                        show_progress=False,
                    )

            progress = json.loads(
                (run_dir / "checkpoints" / "progress.json").read_text(
                    encoding="utf-8"
                )
            )
            events = _read_jsonl(run_dir / "logs" / "events.jsonl")

        self.assertEqual(progress["conversation_completed"], 1)
        self.assertEqual(progress["conversation_total"], 2)
        self.assertEqual(progress["question_completed"], 1)
        self.assertEqual(progress["question_total"], 3)
        self.assertEqual(
            [event["event"] for event in events],
            ["full_run_started", "dataset_loaded", "method_configured", "full_run_failed"],
        )
        failed_payload = events[-1]["payload"]
        self.assertEqual(failed_payload["run_id"], "unit-resume-progress")
        self.assertIs(failed_payload["resume"], True)
        self.assertEqual(failed_payload["exception_type"], "RuntimeError")
        self.assertEqual(failed_payload["stage"], "Prepare method state")
        self.assertIsNone(failed_payload["current_conversation_id"])
        self.assertIsNone(failed_payload["current_question_id"])
        self.assertNotIn("memoryos construction failed", json.dumps(failed_payload))
        self.assertEqual(
            failed_payload["attempt_id"],
            events[0]["payload"]["attempt_id"],
        )

    def test_resume_rejects_prior_state_without_dataset_fingerprint(self):
        """已有可复用状态但缺少 dataset fingerprint 时必须拒绝 resume。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-missing-fingerprint"
            run_dir.mkdir(parents=True)
            _append_jsonl(
                run_dir / "scores.jsonl",
                _score_record("conv-a:q1", "conv-a", "2", 1.0),
            )

            with _patched_full_runner_dependencies(dataset):
                with self.assertRaises(ConfigurationError):
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-missing-fingerprint",
                        resume=True,
                        show_progress=False,
                    )

        self.assertEqual(FakeMemoryOS.instances, [])

    def test_resume_rejects_public_private_artifacts_without_fingerprint(self):
        """仅有公开问题和私有标签产物时也必须要求 dataset fingerprint。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-artifacts-without-fingerprint"
            public_path = run_dir / "artifacts" / "public_questions.jsonl"
            private_path = run_dir / "artifacts" / "evaluator_private_labels.jsonl"
            public_bytes = b'{"question_id":"stale-public"}\n'
            private_bytes = b'{"question_id":"stale-private","gold_answer":"secret"}\n'
            public_path.parent.mkdir(parents=True)
            public_path.write_bytes(public_bytes)
            private_path.write_bytes(private_bytes)

            with _patched_full_runner_dependencies(dataset):
                with self.assertRaises(ConfigurationError):
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-artifacts-without-fingerprint",
                        resume=True,
                        show_progress=False,
                    )

            self.assertEqual(public_path.read_bytes(), public_bytes)
            self.assertEqual(private_path.read_bytes(), private_bytes)
            self.assertFalse((run_dir / "manifest.json").exists())
            self.assertFalse(
                (run_dir / "artifacts" / "dataset_fingerprint.json").exists()
            )

        self.assertEqual(FakeMemoryOS.instances, [])

    def test_resume_rejects_legacy_fingerprint_for_public_private_artifacts(self):
        """公开/私有产物使用无 dataset_sha256 的旧指纹时必须拒绝 resume。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-artifacts-legacy-fingerprint"
            fingerprint = _matching_dataset_fingerprint(dataset)
            fingerprint.pop("dataset_sha256")
            _write_json(
                run_dir / "artifacts" / "dataset_fingerprint.json",
                fingerprint,
            )
            public_path = run_dir / "artifacts" / "public_questions.jsonl"
            private_path = run_dir / "artifacts" / "evaluator_private_labels.jsonl"
            public_bytes = b'{"question_id":"stale-public"}\n'
            private_bytes = b'{"question_id":"stale-private","gold_answer":"secret"}\n'
            public_path.write_bytes(public_bytes)
            private_path.write_bytes(private_bytes)

            with _patched_full_runner_dependencies(dataset):
                with self.assertRaises(ConfigurationError):
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-artifacts-legacy-fingerprint",
                        resume=True,
                        show_progress=False,
                    )

            self.assertEqual(public_path.read_bytes(), public_bytes)
            self.assertEqual(private_path.read_bytes(), private_bytes)
            self.assertFalse((run_dir / "manifest.json").exists())

        self.assertEqual(FakeMemoryOS.instances, [])

    def test_resume_rejects_nonempty_legacy_memoryos_state_without_fingerprint(self):
        """旧版 memoryos_state 非空且无 fingerprint 时必须在构造 method 前失败。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-legacy-method-state"
            legacy_state_dir = run_dir / "memoryos_state" / "conv-a"
            legacy_state_dir.mkdir(parents=True)
            (legacy_state_dir / "state.json").write_text(
                '{"status":"existing"}',
                encoding="utf-8",
            )

            with _patched_full_runner_dependencies(dataset):
                with self.assertRaises(ConfigurationError):
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-legacy-method-state",
                        resume=True,
                        show_progress=False,
                    )

            self.assertFalse((run_dir / "manifest.json").exists())
            self.assertFalse(
                (run_dir / "artifacts" / "dataset_fingerprint.json").exists()
            )

        self.assertEqual(FakeMemoryOS.instances, [])

    def test_resume_allows_empty_legacy_memoryos_state_without_fingerprint(self):
        """旧版 memoryos_state 仅为空目录时不应被视为可复用状态。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-empty-legacy-method-state"
            (run_dir / "memoryos_state").mkdir(parents=True)

            with _patched_full_runner_dependencies(dataset):
                summary = run_memoryos_locomo_full(
                    project_root=PROJECT_ROOT,
                    output_root=Path(temp_dir),
                    run_id="unit-empty-legacy-method-state",
                    resume=True,
                    show_progress=False,
                )

        self.assertEqual(summary.completed_questions, 3)
        self.assertEqual(len(FakeMemoryOS.instances), 1)

    def test_resume_rejects_legacy_fingerprint_without_dataset_sha256(self):
        """已有状态使用旧版无内容 hash 指纹时必须拒绝 resume。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-legacy-fingerprint"
            fingerprint = _matching_dataset_fingerprint(dataset)
            fingerprint.pop("dataset_sha256")
            _write_json(
                run_dir / "artifacts" / "dataset_fingerprint.json",
                fingerprint,
            )
            _append_jsonl(
                run_dir / "scores.jsonl",
                _score_record("conv-a:q1", "conv-a", "2", 1.0),
            )

            with _patched_full_runner_dependencies(dataset):
                with self.assertRaises(ConfigurationError):
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-legacy-fingerprint",
                        resume=True,
                        show_progress=False,
                    )

        self.assertEqual(FakeMemoryOS.instances, [])

    def test_resume_rejects_changed_gold_before_reusing_or_mutating_state(self):
        """同一 run_id 的规范化 Dataset 变化时应在复用或改写旧状态前失败。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            with _patched_full_runner_dependencies(dataset):
                run_memoryos_locomo_full(
                    project_root=PROJECT_ROOT,
                    output_root=Path(temp_dir),
                    run_id="unit-dataset-mismatch",
                    resume=True,
                    show_progress=False,
                )

            run_dir = Path(temp_dir) / "unit-dataset-mismatch"
            canonical_score_path = (
                run_dir / "artifacts" / "answer_scores.locomo_f1.jsonl"
            )
            legacy_score_path = run_dir / "scores.jsonl"
            original_canonical_scores = canonical_score_path.read_bytes()
            original_legacy_scores = legacy_score_path.read_bytes()
            progress_path = run_dir / "checkpoints" / "progress.json"
            original_progress = progress_path.read_bytes()
            dataset.conversations[0].gold_answers["conv-a:q1"].answer = "Portland"

            with _patched_full_runner_dependencies(dataset):
                with self.assertRaises(ConfigurationError):
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-dataset-mismatch",
                        resume=True,
                        show_progress=False,
                    )

            self.assertEqual(canonical_score_path.read_bytes(), original_canonical_scores)
            self.assertEqual(legacy_score_path.read_bytes(), original_legacy_scores)
            self.assertEqual(progress_path.read_bytes(), original_progress)

        self.assertEqual(len(FakeMemoryOS.instances), 1)

    def test_resume_rejects_malformed_fingerprint_as_configuration_error(self):
        """fingerprint JSON 损坏时应抛脱敏 ConfigurationError 且不构造 method。"""

        dataset = build_fake_locomo_dataset()
        malformed_sentinel = "MALFORMED_SECRET_SENTINEL"
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-malformed-fingerprint"
            fingerprint_path = run_dir / "artifacts" / "dataset_fingerprint.json"
            fingerprint_path.parent.mkdir(parents=True)
            fingerprint_path.write_text(
                '{"dataset_sha256": "' + malformed_sentinel,
                encoding="utf-8",
            )
            _append_jsonl(
                run_dir / "scores.jsonl",
                _score_record("conv-a:q1", "conv-a", "2", 1.0),
            )

            with _patched_full_runner_dependencies(dataset):
                try:
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-malformed-fingerprint",
                        resume=True,
                        show_progress=False,
                    )
                except ConfigurationError as exc:
                    raised = exc
                    rendered_exception = "".join(traceback.format_exception(exc))
                else:
                    self.fail("malformed fingerprint should raise ConfigurationError")

        self.assertIn("dataset fingerprint JSON is invalid", str(raised))
        self.assertNotIn(malformed_sentinel, rendered_exception)
        self.assertIsNone(raised.__cause__)
        self.assertIsNone(raised.__context__)
        self.assertEqual(FakeMemoryOS.instances, [])

    def test_resume_sanitizes_malformed_manifest_json_error(self):
        """manifest JSON 损坏时应转换为不泄露原文的 ConfigurationError。"""

        dataset = build_fake_locomo_dataset()
        malformed_sentinel = "MALFORMED_MANIFEST_SECRET_SENTINEL"
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-malformed-manifest"
            _seed_matching_dataset_fingerprint(run_dir, dataset)
            (run_dir / "manifest.json").write_text(
                '{"memoryos_config": "' + malformed_sentinel,
                encoding="utf-8",
            )

            with _patched_full_runner_dependencies(dataset):
                try:
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-malformed-manifest",
                        resume=True,
                        show_progress=False,
                    )
                except ConfigurationError as exc:
                    raised = exc
                    rendered_exception = "".join(traceback.format_exception(exc))
                else:
                    self.fail("malformed manifest should raise ConfigurationError")

        self.assertIn("manifest JSON is invalid", str(raised))
        self.assertNotIn(malformed_sentinel, rendered_exception)
        self.assertEqual(FakeMemoryOS.instances, [])

    def test_resume_sanitizes_malformed_redacted_config_json_error(self):
        """redacted config JSON 损坏时应转换为不泄露原文的 ConfigurationError。"""

        dataset = build_fake_locomo_dataset()
        malformed_sentinel = "MALFORMED_REDACTED_SECRET_SENTINEL"
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-malformed-redacted-config"
            _seed_matching_dataset_fingerprint(run_dir, dataset)
            config = runner_module.MemoryOSPaperConfig()
            _write_json(
                run_dir / "manifest.json",
                {
                    "benchmark_name": "locomo",
                    "method_name": "MemoryOS",
                    "model_name": config.llm_model,
                    "conversation_limit": None,
                    "question_limit_per_conversation": None,
                },
            )
            (run_dir / "config.redacted.json").write_text(
                '{"memoryos_config": "' + malformed_sentinel,
                encoding="utf-8",
            )

            with _patched_full_runner_dependencies(dataset):
                try:
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-malformed-redacted-config",
                        resume=True,
                        show_progress=False,
                    )
                except ConfigurationError as exc:
                    raised = exc
                    rendered_exception = "".join(traceback.format_exception(exc))
                else:
                    self.fail(
                        "malformed redacted config should raise ConfigurationError"
                    )

        self.assertIn("config.redacted JSON is invalid", str(raised))
        self.assertNotIn(malformed_sentinel, rendered_exception)
        self.assertEqual(FakeMemoryOS.instances, [])

    def test_retry_regenerates_public_private_artifact_pair_after_private_failure(self):
        """私有标签原子替换失败后，retry 应确定性重建公开/私有产物对。"""

        dataset = build_fake_locomo_dataset()
        expected_public = [
            public_question_record(question)
            for conversation in dataset.conversations
            for question in conversation.questions
        ]
        expected_private = [
            evaluator_private_label_record(
                conversation.gold_answers[question.question_id],
                question.category,
            )
            for conversation in dataset.conversations
            for question in conversation.questions
        ]
        private_failure = OSError("private label replacement failed")
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-artifact-pair-retry"
            _seed_matching_dataset_fingerprint(run_dir, dataset)
            public_path = run_dir / "artifacts" / "public_questions.jsonl"
            private_path = run_dir / "artifacts" / "evaluator_private_labels.jsonl"
            public_path.write_text('{"question_id":"stale-public"}\n', encoding="utf-8")
            private_path.write_text(
                '{"question_id":"stale-private","gold_answer":"stale"}\n',
                encoding="utf-8",
            )

            def fail_private_replacement(
                path: str | Path,
                records: list[dict[str, object]],
            ) -> None:
                """公开文件正常替换，私有文件抛出指定主流程异常。"""

                if Path(path).name == private_path.name:
                    raise private_failure
                atomic_write_jsonl(path, records)

            with (
                _patched_full_runner_dependencies(dataset),
                patch.object(
                    runner_module,
                    "atomic_write_jsonl",
                    side_effect=fail_private_replacement,
                ),
                self.assertRaises(OSError) as raised,
            ):
                run_memoryos_locomo_full(
                    project_root=PROJECT_ROOT,
                    output_root=Path(temp_dir),
                    run_id="unit-artifact-pair-retry",
                    resume=True,
                    show_progress=False,
                )

            self.assertIs(raised.exception, private_failure)
            self.assertEqual(_read_jsonl(public_path), expected_public)
            self.assertEqual(
                _read_jsonl(private_path),
                [
                    {
                        "question_id": "stale-private",
                        "gold_answer": "stale",
                    }
                ],
            )

            with _patched_full_runner_dependencies(dataset):
                run_memoryos_locomo_full(
                    project_root=PROJECT_ROOT,
                    output_root=Path(temp_dir),
                    run_id="unit-artifact-pair-retry",
                    resume=True,
                    show_progress=False,
                )

            actual_public = _read_jsonl(public_path)
            actual_private = _read_jsonl(private_path)

        self.assertEqual(actual_public, expected_public)
        self.assertEqual(actual_private, expected_private)

    def test_dataset_load_failure_writes_sanitized_human_log(self):
        """dataset load 失败也应写不含异常消息的 run.log 摘要。"""

        sentinel = "SENTINEL_SECRET_DATASET_FAILURE"

        class FailingAdapter:
            """加载数据时抛出带敏感哨兵的异常。"""

            def load(self, limit=None):
                """模拟 dataset 加载失败。"""

                raise RuntimeError(sentinel)

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "memory_benchmark.runners.memoryos_locomo_full.LoCoMoAdapter",
                lambda project_root: FailingAdapter(),
            ):
                with self.assertRaisesRegex(RuntimeError, sentinel):
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-dataset-load-log",
                        show_progress=False,
                    )

            run_log = (
                Path(temp_dir) / "unit-dataset-load-log" / "logs" / "run.log"
            ).read_text(encoding="utf-8")

        self.assertIn("unit-dataset-load-log", run_log)
        self.assertIn("RuntimeError", run_log)
        self.assertNotIn(sentinel, run_log)

    def test_runner_overwrite_helpers_delegate_to_atomic_storage_primitives(self):
        """runner 的 JSON/JSONL 覆盖 helper 应统一委托原子写原语。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "snapshot.json"
            jsonl_path = Path(temp_dir) / "records.jsonl"
            records = [{"question_id": "q1"}]

            with (
                patch.object(
                    runner_module,
                    "atomic_write_json",
                    side_effect=atomic_write_json,
                    create=True,
                ) as json_mock,
                patch.object(
                    runner_module,
                    "atomic_write_jsonl",
                    side_effect=atomic_write_jsonl,
                    create=True,
                ) as jsonl_mock,
            ):
                runner_module._write_json(json_path, {"status": "added"})
                runner_module._rewrite_jsonl(jsonl_path, records)

        json_mock.assert_called_once_with(json_path, {"status": "added"})
        jsonl_mock.assert_called_once_with(jsonl_path, records)

    def test_get_answer_failure_persists_failing_question_id(self):
        """get_answer 失败时，progress.json 应指向正在处理的问题。"""

        dataset = build_fake_locomo_dataset()

        class FailingAnswerMemoryOS(FakeMemoryOS):
            """在首题回答时失败的 MemoryOS fake。"""

            def get_answer(self, question: Question) -> AnswerResult:
                """记录问题后模拟回答失败。"""

                self.answered_question_ids.append(question.question_id)
                raise RuntimeError("answer failed")

        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-answer-failure"
            adapter = type(
                "FakeLoCoMoAdapter",
                (),
                {"load": lambda self, limit=None: dataset},
            )

            with patch.multiple(
                "memory_benchmark.runners.memoryos_locomo_full",
                LoCoMoAdapter=lambda project_root: adapter(),
                MemoryOS=FailingAnswerMemoryOS,
            ):
                with self.assertRaisesRegex(RuntimeError, "answer failed"):
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-answer-failure",
                        show_progress=False,
                    )

            progress = json.loads(
                (run_dir / "checkpoints" / "progress.json").read_text(
                    encoding="utf-8"
                )
            )
            events = _read_jsonl(run_dir / "logs" / "events.jsonl")

        self.assertEqual(progress["stage"], "Answer questions")
        self.assertEqual(progress["question_completed"], 0)
        self.assertEqual(progress["current_conversation_id"], "conv-a")
        self.assertEqual(progress["current_question_id"], "conv-a:q1")
        failed_payload = events[-1]["payload"]
        self.assertEqual(events[-1]["event"], "full_run_failed")
        self.assertEqual(failed_payload["exception_type"], "RuntimeError")
        self.assertEqual(failed_payload["stage"], "Answer questions")
        self.assertEqual(failed_payload["current_conversation_id"], "conv-a")
        self.assertEqual(failed_payload["current_question_id"], "conv-a:q1")
        self.assertNotIn("answer failed", json.dumps(failed_payload))
        self.assertEqual(
            failed_payload["attempt_id"],
            events[0]["payload"]["attempt_id"],
        )

    def test_operational_error_survives_progress_exit_failure(self):
        """已进入 progress scope 后，退出失败不应遮蔽主流程异常。"""

        operational_error = RuntimeError("memoryos construction failed")

        class ExitFailingProgressReporter(ProgressReporter):
            """退出时额外抛错的进度报告器。"""

            exit_calls = 0
            secondary_error_raised = False

            def __exit__(self, exc_type, exc_value, traceback) -> None:
                """完成正常清理后模拟 progress 次生失败。"""

                type(self).exit_calls += 1
                super().__exit__(exc_type, exc_value, traceback)
                type(self).secondary_error_raised = True
                raise OSError("progress exit failed")

        class FailingMemoryOS:
            """构造时抛出主流程异常的 MemoryOS fake。"""

            def __init__(self, *args, **kwargs):
                """模拟进入 progress scope 后的 method 构造失败。"""

                raise operational_error

        dataset = build_fake_locomo_dataset()
        adapter = type(
            "FakeLoCoMoAdapter",
            (),
            {"load": lambda self, limit=None: dataset},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.multiple(
                "memory_benchmark.runners.memoryos_locomo_full",
                LoCoMoAdapter=lambda project_root: adapter(),
                MemoryOS=FailingMemoryOS,
                ProgressReporter=ExitFailingProgressReporter,
            ):
                with self.assertRaises(RuntimeError) as raised:
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-progress-exit-failure",
                        show_progress=False,
                    )

        self.assertIs(raised.exception, operational_error)
        self.assertEqual(ExitFailingProgressReporter.exit_calls, 1)
        self.assertTrue(ExitFailingProgressReporter.secondary_error_raised)

    def test_progress_exit_failure_emits_only_failed_terminal_event(self):
        """业务成功但 progress 退出失败时只应记录失败终态并传播退出异常。"""

        exit_error = OSError("progress exit failed after successful body")

        class ExitFailingProgressReporter(ProgressReporter):
            """在成功业务流程退出 progress 时抛出指定异常。"""

            def __exit__(self, exc_type, exc_value, traceback) -> None:
                """完成正常清理后模拟退出失败。"""

                super().__exit__(exc_type, exc_value, traceback)
                raise exit_error

        dataset = build_fake_locomo_dataset()
        adapter = type(
            "FakeLoCoMoAdapter",
            (),
            {"load": lambda self, limit=None: dataset},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "unit-successful-body-exit-failure"
            with patch.multiple(
                "memory_benchmark.runners.memoryos_locomo_full",
                LoCoMoAdapter=lambda project_root: adapter(),
                MemoryOS=FakeMemoryOS,
                ProgressReporter=ExitFailingProgressReporter,
            ):
                with self.assertRaises(OSError) as raised:
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-successful-body-exit-failure",
                        show_progress=False,
                    )

            events = _read_jsonl(run_dir / "logs" / "events.jsonl")

        self.assertIs(raised.exception, exit_error)
        terminal_events = [
            event["event"]
            for event in events
            if event["event"] in {"full_run_finished", "full_run_failed"}
        ]
        self.assertEqual(terminal_events, ["full_run_failed"])

    def test_operational_error_survives_failure_event_logging_failure(self):
        """失败事件写入异常不应遮蔽已发生的数据加载异常。"""

        operational_error = RuntimeError("dataset operation failed")

        class FailureEventFailingLogger(RunLogger):
            """仅在写 full_run_failed 时抛错的 logger。"""

            def log_event(self, event: str, payload: dict[str, object]) -> None:
                """模拟失败事件持久化异常。"""

                if event == "full_run_failed":
                    raise OSError("failure event logging failed")
                super().log_event(event, payload)

        class FailingAdapter:
            """加载数据时抛出主流程异常的 adapter。"""

            def load(self, limit=None):
                """模拟 dataset 加载失败。"""

                raise operational_error

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.multiple(
                "memory_benchmark.runners.memoryos_locomo_full",
                LoCoMoAdapter=lambda project_root: FailingAdapter(),
                RunLogger=FailureEventFailingLogger,
            ):
                with self.assertRaises(RuntimeError) as raised:
                    run_memoryos_locomo_full(
                        project_root=PROJECT_ROOT,
                        output_root=Path(temp_dir),
                        run_id="unit-failure-event-failure",
                        show_progress=False,
                    )

        self.assertIs(raised.exception, operational_error)

    def test_same_run_id_records_distinct_correlatable_attempts(self):
        """同一 run_id 的新跑和 resume 应能按 attempt_id 独立过滤。"""

        dataset = build_fake_locomo_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            with _patched_full_runner_dependencies(dataset):
                run_memoryos_locomo_full(
                    project_root=PROJECT_ROOT,
                    output_root=Path(temp_dir),
                    run_id="unit-two-attempts",
                    resume=False,
                    show_progress=False,
                )
                run_memoryos_locomo_full(
                    project_root=PROJECT_ROOT,
                    output_root=Path(temp_dir),
                    run_id="unit-two-attempts",
                    resume=True,
                    show_progress=False,
                )

            events = _read_jsonl(
                Path(temp_dir) / "unit-two-attempts" / "logs" / "events.jsonl"
            )

        started_events = [
            event for event in events if event["event"] == "full_run_started"
        ]
        self.assertEqual(len(started_events), 2)
        attempt_ids = [
            event["payload"]["attempt_id"] for event in started_events
        ]
        self.assertEqual(len(set(attempt_ids)), 2)
        for attempt_id, expected_resume in zip(attempt_ids, (False, True)):
            attempt_events = [
                event
                for event in events
                if event["payload"]["attempt_id"] == attempt_id
            ]
            self.assertTrue(attempt_events)
            self.assertEqual(attempt_events[0]["event"], "full_run_started")
            self.assertEqual(attempt_events[-1]["event"], "full_run_finished")
            self.assertTrue(
                all(
                    event["payload"]["resume"] is expected_resume
                    for event in attempt_events
                )
            )


def build_fake_locomo_dataset() -> Dataset:
    """构造包含两个 conversation 的 fake LoCoMo Dataset。

    输入:
        无。

    输出:
        Dataset: 三个 question，覆盖 category 1 和 category 2。
    """

    conv_a_questions = [
        Question("conv-a:q1", "conv-a", "Where did Alice move?", category="2"),
        Question("conv-a:q2", "conv-a", "What drink does Alice like?", category="1"),
    ]
    conv_b_questions = [
        Question("conv-b:q1", "conv-b", "Where did Bob move?", category="2"),
    ]
    return Dataset(
        dataset_name="locomo",
        conversations=[
            Conversation(
                conversation_id="conv-a",
                sessions=[
                    Session(
                        session_id="session_1",
                        turns=[
                            Turn("a-1", "Alice", "I moved to Seattle."),
                            Turn("a-2", "Bob", "Nice."),
                        ],
                    )
                ],
                questions=conv_a_questions,
                gold_answers={
                    "conv-a:q1": GoldAnswerInfo("conv-a:q1", "Seattle"),
                    "conv-a:q2": GoldAnswerInfo("conv-a:q2", "tea"),
                },
                metadata={"speaker_a": "Alice", "speaker_b": "Bob"},
            ),
            Conversation(
                conversation_id="conv-b",
                sessions=[
                    Session(
                        session_id="session_1",
                        turns=[
                            Turn("b-1", "Bob", "I moved to Denver."),
                            Turn("b-2", "Alice", "Nice."),
                        ],
                    )
                ],
                questions=conv_b_questions,
                gold_answers={
                    "conv-b:q1": GoldAnswerInfo("conv-b:q1", "Denver"),
                },
                metadata={"speaker_a": "Bob", "speaker_b": "Alice"},
            ),
        ],
    )


def _patched_full_runner_dependencies(dataset: Dataset):
    """patch full runner 的 LoCoMoAdapter 和 MemoryOS。

    输入:
        dataset: fake adapter 应返回的数据集。

    输出:
        context manager: 可在 with 中使用的 patch 组合。
    """

    adapter = type("FakeLoCoMoAdapter", (), {"load": lambda self, limit=None: dataset})
    return patch.multiple(
        "memory_benchmark.runners.memoryos_locomo_full",
        LoCoMoAdapter=lambda project_root: adapter(),
        MemoryOS=FakeMemoryOS,
    )


def _seed_matching_dataset_fingerprint(run_dir: Path, dataset: Dataset) -> None:
    """为 intentional resume fixture 写入兼容的指纹和公开 metadata。"""

    _write_json(
        run_dir / "artifacts" / "dataset_fingerprint.json",
        _matching_dataset_fingerprint(dataset),
    )
    config = runner_module.MemoryOSPaperConfig()
    _write_json(
        run_dir / "manifest.json",
        {
            "benchmark_name": "locomo",
            "method_name": "MemoryOS",
            "model_name": config.llm_model,
            "conversation_limit": None,
            "question_limit_per_conversation": None,
            "memoryos_config": runner_module._build_redacted_config_payload(config)[
                "memoryos_config"
            ],
        },
    )
    _write_json(
        run_dir / "config.redacted.json",
        runner_module._build_redacted_config_payload(config),
    )


def _matching_dataset_fingerprint(dataset: Dataset) -> dict[str, object]:
    """返回与 runner 数据源路径一致的测试 Dataset 指纹。"""

    source_path = PROJECT_ROOT / "data/locomo/locomo10.json"
    return build_dataset_fingerprint(dataset=dataset, source_paths=[source_path])


def _append_jsonl(path: Path, payload: dict[str, object]) -> None:
    """追加一条 JSONL。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    """读取 JSONL 文件。"""

    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _find_forbidden_keys(
    value: object,
    forbidden_keys: set[str],
) -> set[str]:
    """递归查找事件 payload 中禁止出现的敏感键。"""

    found: set[str] = set()
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if str(key).lower() in forbidden_keys:
                found.add(str(key).lower())
            found.update(_find_forbidden_keys(nested_value, forbidden_keys))
    elif isinstance(value, list):
        for nested_value in value:
            found.update(_find_forbidden_keys(nested_value, forbidden_keys))
    return found


def _write_json(path: Path, payload: dict[str, object]) -> None:
    """写入 JSON 文件。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _prediction_record(
    question_id: str,
    conversation_id: str,
    question_text: str,
    answer: str,
    category: str,
) -> dict[str, object]:
    """构造测试用 prediction JSONL 记录。"""

    return {
        "conversation_id": conversation_id,
        "question_id": question_id,
        "question_text": question_text,
        "category": category,
        "prediction_answer": answer,
        "answer_metadata": {},
    }


def _score_record(
    question_id: str,
    conversation_id: str,
    category: str,
    f1: float,
) -> dict[str, object]:
    """构造测试用 score JSONL 记录。"""

    return {
        "conversation_id": conversation_id,
        "question_id": question_id,
        "category": category,
        "f1": f1,
    }


if __name__ == "__main__":
    unittest.main()
