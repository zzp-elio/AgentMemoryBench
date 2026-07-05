# 2026-06-20 LoCoMo smoke question-limit 修复交接

## 背景

用户指出希望 smoke/full 都能灵活控制：

- 最多加载多少 conversation。
- 每个 conversation 最多保留多少 turn。
- 每个 conversation 最多回答多少 question。

此前 LoCoMo smoke adapter 在 dataset 阶段每个 conversation 只保留 1 道 evidence 覆盖题。
因此即使用户传 `--question-limit-per-conversation 2` 或更大，runner 也只能看到 1 道题。

## 修复

修改 `src/memory_benchmark/benchmark_adapters/locomo.py`：

- `_build_locomo_smoke_conversation()` 现在保留所有 evidence 完整落在截断历史里的问题。
- 私有 gold/evidence 仍只放在 `gold_answers`，不会进入 method 可见的 public input。
- metadata 保留兼容字段：
  - `smoke_selected_question_id`: 第一个可回答问题 id。
  - `smoke_selected_question_ids`: 所有可回答问题 id。
- 若截断历史没有覆盖任何完整 evidence，继续 fail closed，提示提高
  `--smoke-turn-limit`。

runner 仍负责 `question_limit_per_conversation` 的本次命令预算裁剪；该参数不进入
prediction manifest identity，允许后续用同一 `run_id --resume` 增加题数。

## 验证

```bash
uv run pytest tests/test_prediction_cli.py::test_smoke_dataset_keeps_turns_covering_private_evidence_sets tests/test_prediction_cli.py::test_smoke_dataset_keeps_all_questions_covered_by_retained_evidence tests/test_prediction_cli.py::test_smoke_dataset_can_select_two_independent_conversations tests/test_prediction_cli.py::test_smoke_dataset_rejects_history_without_answerable_question tests/test_benchmark_registry.py::test_locomo_registration_prepares_full_and_smoke_datasets -q
# 5 passed
```

## 文档同步

已更新：

- `AGENTS.md`
- `README.md`
- `docs/current-roadmap.md`
- `docs/task-ledger.md`

## 后续注意

旧 run 的 smoke dataset 不会自动变化。若需要验证真实 API 行为，请用新的 `run_id` 跑极小
smoke。
