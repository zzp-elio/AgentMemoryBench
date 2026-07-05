# 2026-06-02 Conversation-QA Refactor Handoff

## 为什么写这份交接

本轮已经发生过一次上下文压缩，且额度接近不足。为了让下一个窗口可以像没中断一样继续，本文件记录当前真实状态、已完成内容、未完成内容、验证命令和下一步执行策略。

## 用户已确认的方案

- 采用 conversation + QA 架构，不再修补旧协议。
- Phase 1 只做 LoCoMo + LongMemEval。
- 不再做 reset。隔离粒度是 `conversation_id`。
- 只做 answer 质量评测。
- 不做 retrieval recall / precision / NDCG / hit rate。
- 不做 adversarial、效率、延迟、token 统计。
- 多模态字段保留，但 Phase 1 只跑纯文本。
- `Conversation -> Session -> Turn` 显式保留。
- 一个 turn 是单个 speaker 的一次 content；一个 user+assistant round 应拆成两个 turn。
- `Question` 是公开问题，不能含答案。
- `GoldAnswerInfo` 是 evaluator-only 标准答案信息。
- method 接口是 `BaseMemorySystem.add(list[Conversation])` 和 `BaseMemorySystem.get_answer(Question)`。
- `BaseMemoryRetriever.retrieve(Question)` 是可选接口，Phase 1 不要求。
- `top_k` 属于 method 自己配置，不进统一接口。
- 任何实质性架构疑问都先和用户讨论再行动。

## 当前文件状态

已完成并通过 spec review：

- `memory_benchmark/core/entities.py`
- `memory_benchmark/core/interfaces.py`
- `memory_benchmark/core/validators.py`
- `memory_benchmark/core/exceptions.py`
- `memory_benchmark/core/__init__.py`
- `memory_benchmark/benchmark_adapters/base.py`
- `memory_benchmark/benchmark_adapters/registry.py`
- `memory_benchmark/benchmark_adapters/__init__.py`
- `memory_benchmark/methods/mem0_adapter.py`
- `tests/test_core_conversation_entities.py`
- `tests/test_conversation_dataset_validation.py`

已归档：

- 旧 `docs/` 内容
- 旧 `reports/`
- `任务.md`
- `参考.md`
- `benchmark-structure-summary.md`

归档目录：

- `old/2026-06-02-legacy/`

当前仍需重写：

- `memory_benchmark/benchmark_adapters/locomo.py`
- `memory_benchmark/benchmark_adapters/longmemeval.py`
- `README.md`
- `memory_benchmark/core/Readme.md`
- 新版 `docs/architecture.md`
- 新版 `docs/data-model.md`
- 新版 `docs/method-interface.md`
- 新版 `docs/benchmark-scope.md`
- 新版 `docs/refactor-plan.md`

## 当前 Subagent 状态

Task 3-6 spec reviewer 已 APPROVED。

旧 Task 3-6 code quality reviewer 曾派发：

- agent id: `019e88cb-a460-7db3-931f-a53ea0fcd884`
- nickname: `Carson`
- 状态：2026-06-02 因额度保护已关闭，不要再等待它。

2026-06-03 恢复后已重新派发 Task 3-6 code quality reviewer：

- agent id: `019e8af4-751c-70b0-984c-6c8fa67bdeed`
- nickname: `Laplace`
- 状态：第一次返回 `ISSUES_FOUND`，发现两个 Important validators 问题；已修复并请求同一 reviewer 复审；复审结果 `APPROVED`。

Reviewer 第一次发现的问题：

1. `PRIVATE_KEY_NAMES` 缺少 `answer_session_ids`，LongMemEval 私有 evidence session 字段可能泄漏。
2. `validate_dataset()` 只校验 public question 有 gold，没有反向校验 `gold_answers` 不能多出 question_id。

已修复：

- `memory_benchmark/core/validators.py`
  - `PRIVATE_KEY_NAMES` 增加 `answer_session_ids`。
  - 增加反向校验：`conversation.gold_answers` 的每个 key 必须存在于 public `Question.question_id` 集合中。
- `tests/test_conversation_dataset_validation.py`
  - 新增 `test_payload_with_answer_session_ids_key_fails`。
  - 新增 `test_extra_gold_answer_without_question_fails`。

已验证：

```bash
uv run python -m unittest tests/test_conversation_dataset_validation.py -v
uv run python -m unittest tests/test_core_conversation_entities.py tests/test_conversation_dataset_validation.py -v
```

结果：

- `test_conversation_dataset_validation.py`: 8 tests OK。
- core + validation: 14 tests OK。
- reviewer 复审也运行 core + validation：14 tests OK。

该 reviewer 已关闭，不需要继续等待。

2026-06-03 已开始 Task 7 LoCoMo adapter worker：

- agent id: `019e8afa-b8ba-7e82-8a2c-a12f6afaafd5`
- nickname: `Boyle`
- 写入范围：
  - `memory_benchmark/benchmark_adapters/locomo.py`
  - `tests/test_locomo_conversation_adapter.py`
  - 必要时 `memory_benchmark/benchmark_adapters/__init__.py`
  - 必要时 `memory_benchmark/benchmark_adapters/registry.py`
- 当前状态：第一次 `wait_agent(..., timeout_ms=360000)` 超时，worker 尚未返回，未关闭。
- 最新状态：第二次等待后 worker 返回 `DONE`。

Worker 报告：

- 替换 LoCoMo 旧 `BenchmarkCase` adapter 为 conversation-QA v2 `Dataset`。
- sample/session/turn/QA 已映射到 `Conversation`、`Session`、`Turn`、`Question`、`GoldAnswerInfo`。
- category `5` adversarial QA 已跳过。
- 图片 URL/caption/query 已通过 `ImageRef` 和公开 metadata 保留。
- `LoCoMoAdapter` 已注册/导出。

Worker 报告的验证：

```bash
uv run python -m unittest tests/test_locomo_conversation_adapter.py -v
uv run python -m unittest tests/test_core_conversation_entities.py tests/test_conversation_dataset_validation.py tests/test_locomo_conversation_adapter.py -v
```

结果：

- LoCoMo adapter: 5 tests OK。
- core + validation + LoCoMo: 19 tests OK。

下一步：Task 7 仍需 spec compliance review 和 code quality review，二者都通过后才能标记完成。

2026-06-03 已派发 Task 7 spec compliance reviewer：

- agent id: `019e8b03-bdbf-7411-9c7c-9c9b8eefbbe0`
- nickname: `Beauvoir`
- 状态：`SPEC_COMPLIANT`，已关闭。

本地复跑 worker 验证：

```bash
uv run python -m unittest tests/test_locomo_conversation_adapter.py -v
uv run python -m unittest tests/test_core_conversation_entities.py tests/test_conversation_dataset_validation.py tests/test_locomo_conversation_adapter.py -v
```

结果：

- LoCoMo adapter: 5 tests OK。
- core + validation + LoCoMo: 19 tests OK。

Spec reviewer 独立 full-load check：

- Raw samples: 10。
- Converted conversations: 10。
- Raw QA: 1,986。
- Raw category 5 QA skipped: 446。
- Converted public questions: 1,540。
- Converted gold answers: 1,540。
- Public category `5` questions: 0。
- Question/gold alignment issues: none。
- Public private-key hits for `gold_answers`、`answer`、`evidence`、`answer_session_ids`: none。
- Image refs present and preserving URL/caption/query。

2026-06-03 已派发 Task 7 code quality reviewer：

- agent id: `019e8b07-e93f-7dd0-8e0f-d04e95050c49`
- nickname: `Lovelace`
- 状态：第一次 `wait_agent(..., timeout_ms=240000)` 超时；第二次返回 `ISSUES_FOUND`；已修复并请求复审。

Quality reviewer 第一次发现的问题：

1. Important: `_session_keys()` 过滤掉非 list 的 `session_<n>`，导致 malformed session 被静默丢弃。
2. Minor: `load(limit=0)` 会返回一条 conversation，limit 边界不清晰。

已按 TDD 修复：

- 新增测试：
  - `test_malformed_session_is_not_silently_dropped`
  - `test_zero_limit_fails_with_clear_validation_error`
- 两个测试修复前均失败。
- `memory_benchmark/benchmark_adapters/locomo.py`
  - `load_dataset()` 现在对 `limit <= 0` 抛 `DatasetValidationError`。
  - `_session_keys()` 现在返回所有匹配 `^session_(\\d+)$` 的 key，不再按 value 类型过滤；非 list 值交给 `_session_from_raw()` 抛错。

修复后本地验证：

```bash
uv run python -m unittest tests/test_locomo_conversation_adapter.py -v
uv run python -m unittest tests/test_core_conversation_entities.py tests/test_conversation_dataset_validation.py tests/test_locomo_conversation_adapter.py -v
rg -n "UnifiedMemoryAgent|reset\\(|ingest\\(|respond\\(|EvalScope|MemorySegment|EvalQuery|EvalOutput|top_k" memory_benchmark/benchmark_adapters/locomo.py tests/test_locomo_conversation_adapter.py memory_benchmark/benchmark_adapters/registry.py memory_benchmark/benchmark_adapters/__init__.py || true
```

结果：

- LoCoMo adapter: 7 tests OK。
- core + validation + LoCoMo: 21 tests OK。
- old protocol search: no matches。

当前等待同一 quality reviewer 复审。

Quality reviewer 复审结果：`APPROVED`，已关闭。Task 7 LoCoMo adapter 完成。

Task 7 最终验证：

- `uv run python -m unittest tests/test_locomo_conversation_adapter.py -v`: 7 tests OK。
- `uv run python -m unittest tests/test_core_conversation_entities.py tests/test_conversation_dataset_validation.py tests/test_locomo_conversation_adapter.py -v`: 21 tests OK。
- Task 7 touched-file old protocol scan: no matches；唯一 `gold_answers` 命中是测试中的 no-leak assertion。

## Task 8 LongMemEval 当前状态

2026-06-03 已派发 Task 8 LongMemEval adapter worker：

- agent id: `019e8b0f-cf4b-7630-922c-da3f66fbcf54`
- nickname: `Volta`
- 写入范围：
  - `memory_benchmark/benchmark_adapters/longmemeval.py`
  - `tests/test_longmemeval_conversation_adapter.py`
  - 必要时 `memory_benchmark/benchmark_adapters/__init__.py`
  - 必要时 `memory_benchmark/benchmark_adapters/registry.py`
- 状态：第一次 `wait_agent(..., timeout_ms=360000)` 超时，worker 尚未返回，未关闭。
- 最新状态：第二次等待后 worker 返回 `DONE_WITH_CONCERNS`。

Worker concern：

- 官方 `longmemeval_s_cleaned.json` 全量加载时有 12 条空 content message。
- 官方数据中有 13 个 instance 出现重复 `haystack_session_ids`。
- 若完全按强校验直接转换，全量 `LongMemEvalAdapter(ROOT).load()` 会失败。

已系统核验：

- blank message count: 12。
- duplicate session id instance count: 13。
- 原因来自官方 raw 数据，不是 adapter 误读。

已采用 source normalization 策略：

- 空 message 不生成统一 `Turn`，并记录跳过数量。
- 重复原始 session id 生成唯一内部 `session_id`，例如追加 occurrence suffix。
- `Session.metadata.original_session_id` 保留原始 id，便于 debug/audit。
- `Conversation.metadata` 与 `Dataset.metadata` 记录：
  - `skipped_blank_turn_count`
  - `deduplicated_session_id_count`
- `answer_session_ids` 仍只保存在 `GoldAnswerInfo.evidence`，不进入公开 payload。

已按 TDD 添加并通过测试：

- `test_full_official_split_loads_after_source_normalization`
- `test_blank_message_is_skipped_and_recorded`
- `test_duplicate_session_ids_are_made_unique_with_original_id_metadata`

修复后验证：

```bash
uv run python -m unittest tests/test_longmemeval_conversation_adapter.py -v
uv run python -m unittest tests/test_core_conversation_entities.py tests/test_conversation_dataset_validation.py tests/test_locomo_conversation_adapter.py tests/test_longmemeval_conversation_adapter.py -v
```

结果：

- LongMemEval adapter: 11 tests OK。
- core + validation + LoCoMo + LongMemEval: 32 tests OK。
- `LongMemEvalAdapter(ROOT).load()` full split: 500 conversations, 12 skipped blank turns, 13 deduplicated session ids。

下一步：Task 8 需要 spec compliance review 和 code quality review。

2026-06-03 已派发 Task 8 spec compliance reviewer：

- agent id: `019e8b1d-bb59-7f50-b360-442a178fa53c`
- nickname: `Copernicus`
- 状态：第一次返回 `ISSUES_FOUND`；已修复并请求复审。

Spec reviewer 第一次发现的问题：

- 缺少 `content/text` 字段的 malformed message 会被当成空字符串脏数据跳过；规范要求只有官方存在字段但内容为空的 message 可跳过，缺字段必须报 `DatasetValidationError`。

已按 TDD 修复：

- 新增 `test_message_missing_content_and_text_fails`，修复前失败。
- 新增 `_has_blank_message_content()`：
  - 只有 `content` 或 `text` 字段存在且清洗后为空，才当作官方 blank message 跳过。
  - 同时缺失 `content` 和 `text` 时，继续走 `_message_content()` 并抛领域异常。

修复后验证：

```bash
uv run python -m unittest tests/test_longmemeval_conversation_adapter.py -v
uv run python -m unittest tests/test_core_conversation_entities.py tests/test_conversation_dataset_validation.py tests/test_locomo_conversation_adapter.py tests/test_longmemeval_conversation_adapter.py -v
```

结果：

- LongMemEval adapter: 12 tests OK。
- core + validation + LoCoMo + LongMemEval: 33 tests OK。
- Full load + privacy check: 500 conversations, 12 skipped blank turns, 13 deduplicated session ids。

Spec reviewer 复审结果：`SPEC_COMPLIANT`，已关闭。

Spec reviewer 复审验证：

- LongMemEval adapter: 12 tests OK。
- core + validation + LoCoMo + LongMemEval: 33 tests OK。
- Full-load/privacy probe: 500 conversations, 500 questions, 500 gold answers；`validate_no_private_keys(dataset.to_public_dict())` passed。
- Synthetic missing-content probe now raises `DatasetValidationError`。

下一步：派发 Task 8 code quality reviewer。

2026-06-03 已派发 Task 8 code quality reviewer：

- agent id: `019e8b25-516f-7671-ba2d-715b2772af44`
- nickname: `Einstein`
- 状态：第一次 `wait_agent(..., timeout_ms=300000)` 超时；第二次返回 `APPROVED`；已关闭。

Task 8 最终状态：LongMemEval adapter 完成。

最终验证：

- `uv run python -m unittest tests/test_longmemeval_conversation_adapter.py -v`: 12 tests OK。
- `uv run python -m unittest tests/test_core_conversation_entities.py tests/test_conversation_dataset_validation.py tests/test_locomo_conversation_adapter.py tests/test_longmemeval_conversation_adapter.py -v`: 33 tests OK。
- Full-load privacy check: `loaded=500 skipped_blank_turn_count=12 deduplicated_session_id_count=13 privacy=ok`。
- 质量 reviewer 补充 raw split sanity check：
  - 官方数据有 12 条真正空 `content` message。
  - 无 `text` fallback case。
  - 无缺失 content/text message。
  - 13 个重复 session-id occurrence。
  - 无 `answer_session_ids` 指向重复原始 session id。

## Task 9-12 当前状态

下一组目标：实现 conversation-QA runner、mock method、answer-level evaluator、LLM judge 解析、rich run logger。

相关计划原文在：

```bash
sed -n '1135,1605p' docs/superpowers/plans/2026-06-02-conversation-qa-refactor-phase1.md
```

2026-06-03 已并行派发 Task 9-12 workers：

- Task 9 runner/mock worker:
  - agent id: `019e8b2c-66b9-73f1-a17c-31e1ccf1fcd8`
  - nickname: `Jason`
  - write scope: `memory_benchmark/methods/mock.py`, `memory_benchmark/runners/conversation_qa.py`, `tests/test_conversation_runner.py`, optional methods/runners `__init__.py`
- Task 10 LoCoMo F1 worker:
  - agent id: `019e8b2c-ac16-7a33-9ba4-ba6e12e452cf`
  - nickname: `Poincare`
  - write scope: `memory_benchmark/evaluators/locomo_f1.py`, `tests/test_locomo_answer_metrics.py`, optional `memory_benchmark/evaluators/__init__.py`
- Task 11 LLM judge worker:
  - agent id: `019e8b2d-1c0a-79e0-a631-d70bc620bbaf`
  - nickname: `Anscombe`
  - write scope: `memory_benchmark/evaluators/llm_judge.py`, `locomo_judge.py`, `longmemeval_judge.py`, `tests/test_llm_judge_parsing.py`, optional evaluator/core exception exports
- Task 12 run logger worker:
  - agent id: `019e8b2d-57a2-7bd3-a6b7-43e02fea8a7f`
  - nickname: `Ptolemy`
  - write scope: `memory_benchmark/utils/run_logger.py`, `tests/test_run_logger.py`, optional `memory_benchmark/utils/__init__.py`

2026-06-03 额度中断后恢复确认：

- 四个 Task 9-12 worker 都已返回 DONE，并且文件已落盘。
- 当前工具会话无法继续关闭旧 worker handle，`close_agent` 对 Task 9 worker 返回 `not_found`；后续不依赖旧 worker。
- 2026-06-03 当前窗口本地复跑：

```bash
uv run python -m unittest tests/test_conversation_runner.py tests/test_locomo_answer_metrics.py tests/test_llm_judge_parsing.py tests/test_run_logger.py -v
```

结果：23 tests OK。

Worker 结果摘要：

- Task 9 runner/mock:
  - `memory_benchmark/methods/mock.py`
  - `memory_benchmark/runners/conversation_qa.py`
  - `tests/test_conversation_runner.py`
  - worker reported 5 runner tests OK, 19 core+validation+runner tests OK。
- Task 10 LoCoMo F1:
  - `memory_benchmark/evaluators/locomo_f1.py`
  - `tests/test_locomo_answer_metrics.py`
  - `memory_benchmark/evaluators/__init__.py`
  - worker reported 6 tests OK。
- Task 11 LLM judge:
  - `memory_benchmark/evaluators/llm_judge.py`
  - `memory_benchmark/evaluators/locomo_judge.py`
  - `memory_benchmark/evaluators/longmemeval_judge.py`
  - `memory_benchmark/evaluators/__init__.py`
  - `memory_benchmark/core/exceptions.py`
  - `memory_benchmark/core/__init__.py`
  - `tests/test_llm_judge_parsing.py`
  - worker reported judge parsing 7 tests OK、LoCoMo F1 6 tests OK、core+validation 14 tests OK。
- Task 12 run logger:
  - `memory_benchmark/utils/run_logger.py`
  - `tests/test_run_logger.py`
  - worker reported 4 tests OK。

2026-06-03 恢复后已派发 Task 9-12 spec reviewers：

- Task 9 runner/mock spec reviewer:
  - agent id: `019e8c8e-57f5-7e33-8c79-3e29657ee8bd`
  - nickname: `Carson`
  - result: `SPEC_COMPLIANT`
  - tests: runner 5 tests OK; core+validation+runner 19 tests OK。
- Task 10 LoCoMo F1 spec reviewer:
  - agent id: `019e8c8e-8d2b-7d00-8015-8c8f98e5714a`
  - nickname: `Godel`
  - result: `SPEC_COMPLIANT`
  - tests: LoCoMo F1 6 tests OK。
- Task 11 LLM judge spec reviewer:
  - agent id: `019e8c8f-828b-7592-bae1-4b009015ad4a`
  - nickname: `Bohr`
  - first result: `ISSUES_FOUND`
  - issue: detailed judge parser accepted `{"reason": null}` by converting it to empty string. Spec says reason is optional string; if provided, non-string should raise `JudgeOutputError`.
  - fix:
    - `tests/test_llm_judge_parsing.py` added `test_null_reason_raises_when_reason_field_is_present`.
    - `memory_benchmark/evaluators/llm_judge.py` now defaults reason to `""` only when absent; present non-string/null reason raises `JudgeOutputError`.
  - TDD result:
    - new test failed before implementation.
    - after fix: `uv run python -m unittest tests/test_llm_judge_parsing.py -v` -> 8 tests OK.
    - after fix: `uv run python -m unittest tests/test_locomo_answer_metrics.py tests/test_llm_judge_parsing.py -v` -> 14 tests OK.
  - re-review result: `SPEC_COMPLIANT`
  - reviewer confirmation: `reason` now defaults only when absent; present non-string / `null` raises `JudgeOutputError`。
  - re-review tests: judge parsing 8 tests OK; LoCoMo F1 + judge parsing 14 tests OK。
  - status: reviewer 已关闭。
- Task 12 run logger spec reviewer:
  - agent id: `019e8c8f-c4c0-79a2-a7e5-e46f43804743`
  - nickname: `Confucius`
  - result: `SPEC_COMPLIANT`
  - tests: run logger 4 tests OK。

当前精确断点：

1. Task 9 runner/mock spec 已通过，code quality reviewer 已复审通过。
   - agent id: `019e8c9a-5211-75f2-9988-1e388616418b`
   - nickname: `Kierkegaard`
   - first result: `ISSUES_FOUND`
   - issue: `deepcopy` public conversation 会泄漏 dataclass 动态私有属性。
   - re-review result: `APPROVED`
   - tests: runner 6 tests OK；Task 9-12 focused 26 tests OK。
   - status: reviewer 已关闭。
2. Task 10 LoCoMo F1 spec 已通过，code quality reviewer 已派发，等待返回。
   - agent id: `019e8c9a-882c-72d3-9e8b-e1c93e3d56ee`
   - nickname: `Darwin`
   - result: `APPROVED`
   - tests: `uv run python -m unittest tests/test_locomo_answer_metrics.py -v` OK；evaluator import smoke OK。
   - status: reviewer 已关闭。
3. Task 11 LLM judge spec 已复审通过，code quality reviewer 已复审通过。
   - agent id: `019e8c9a-efa6-7a43-8194-944c4d23615b`
   - nickname: `Boole`
   - first result: `ISSUES_FOUND`
   - issue: compact parser 与 benchmark prompt 固定 JSON 不一致。
   - re-review result: `APPROVED`
   - tests: judge parsing 10 tests OK；Task 9-12 focused 26 tests OK。
   - status: reviewer 已关闭。
4. Task 12 run logger spec 已通过，code quality reviewer 已派发，等待返回。
   - agent id: `019e8c9b-20ed-70d0-89d8-cecb37e30b19`
   - nickname: `Fermat`
   - result: `APPROVED`
   - tests: `uv run python -m unittest tests/test_run_logger.py -v` -> 4 tests OK。
   - status: reviewer 已关闭。
5. Task 9 code quality reviewer 返回 `ISSUES_FOUND`，发现 public conversation 使用 `deepcopy` 会泄漏 dataclass 动态私有属性；已按 TDD 修复并通过同一 reviewer 复审。
   - fix:
     - `tests/test_conversation_runner.py` 新增 `test_runner_rebuilds_public_objects_without_dynamic_private_attrs`。
     - RED: 新测试先失败，证明动态属性会泄漏到 `system.add()`。
     - `memory_benchmark/runners/conversation_qa.py` 改为递归重建 `Conversation/Session/Turn/ImageRef/Question` 的公开对象，不再 deep-copy 整个 conversation。
     - GREEN: runner 6 tests OK；Task 9-12 focused 26 tests OK。
6. Task 11 code quality reviewer 返回 `ISSUES_FOUND`，发现 compact mode parser 与 benchmark prompt 固定 JSON 的不一致；已按 TDD 修复并通过同一 reviewer 复审。
   - fix:
     - `tests/test_llm_judge_parsing.py` 新增 LoCoMo/LongMemEval compact prompt 回归测试。
     - RED: 两个 compact prompt 测试先失败，证明 prompt 仍要求 JSON。
     - `LLMJudgeEvaluator._output_instruction()` 根据 `mode` 返回 true/false 或 JSON 指令。
     - LoCoMo/LongMemEval judge prompt 使用 `_output_instruction()`。
     - GREEN: judge parsing/prompt 10 tests OK；Task 9-12 focused 26 tests OK。
7. Task 9-12 code quality review 已全部通过。集中验证已完成。
   - `uv run python -m unittest tests/test_core_conversation_entities.py tests/test_conversation_dataset_validation.py tests/test_locomo_conversation_adapter.py tests/test_longmemeval_conversation_adapter.py tests/test_conversation_runner.py tests/test_locomo_answer_metrics.py tests/test_llm_judge_parsing.py tests/test_run_logger.py -v` -> 59 tests OK。
   - 当时旧协议扫描仍命中 README、旧 tests、HaluMem/MemBench/Mem-Gallery 旧 adapter、旧 LoCoMo runner、mem0 smoke CLI 等 legacy 活跃文件；这些已在 Task 13-15 中清理。
8. Task 13-15 已完成。
   - 删除旧协议测试：旧 interface contract、旧 dataset normalization、旧 structure alignment、旧 temporal、旧 LoCoMo runner、旧 mem0 wrapper、旧 mem0 smoke、旧 LoCoMo metric 测试。
   - 删除旧协议模块：HaluMem/MemBench/Mem-Gallery 旧 adapter、旧 LoCoMo runner、旧 mem0 LoCoMo smoke CLI、旧 duplicate LoCoMo metrics。
   - dry-run CLI 改为读取新 `Dataset` 并输出 conversation/session/turn/question 计数。
   - README、core Readme、active docs 已重写为 conversation-QA v2。
   - 新增 `docs/architecture.md`、`docs/data-model.md`、`docs/method-interface.md`、`docs/benchmark-scope.md`、`docs/refactor-plan.md`、`docs/logs/README.md`。
   - `uv run python -m unittest discover -s tests -v` -> 69 tests OK。
   - active 旧协议关键词扫描无命中。
   - adapter 单样本验证：`locomo conv-26 19 152`，`longmemeval e47becba 53 1`。
   - PrefEval 删除验证通过：`benchmarks/PrefEval-main`、`dataset数据结构/prefeval.md`、`memory_benchmark/benchmark_adapters/prefeval.py` 均不存在。
9. 2026-06-03 最终复验：
   - `uv run python -m unittest discover -s tests -v` -> 69 tests OK。
   - active 旧协议关键词扫描 -> no output。
   - adapter 单样本验证 -> `locomo conv-26 19 152`，`longmemeval e47becba 53 1`。

当前最新断点：

- conversation-QA v2 Phase 1 基线已完成。
- 当前可运行范围是 LoCoMo + LongMemEval。
- 下一步不要继续旧协议；若继续代码工作，优先讨论并实现真实 method wrapper，例如 mem0 的 `BaseMemorySystem` 适配。

上下文压缩后最小续跑命令：

```bash
cd /Users/wz/Desktop/memoryBenchmark
uv run python -m unittest tests/test_conversation_runner.py tests/test_locomo_answer_metrics.py tests/test_llm_judge_parsing.py tests/test_run_logger.py -v
```

预期当前结果：23 tests OK。

如果仍在同一个线程继续，下一步直接派发 Task 9-12 code quality reviewers。若工具状态丢失，不需要恢复 Bohr；Task 11 spec 已通过。

## 已运行验证

已完成的关键验证：

```bash
uv run python -m unittest tests/test_core_conversation_entities.py tests/test_conversation_dataset_validation.py -v
uv run python -m unittest tests/test_locomo_conversation_adapter.py -v
uv run python -m unittest tests/test_longmemeval_conversation_adapter.py -v
uv run python -m unittest tests/test_conversation_runner.py tests/test_locomo_answer_metrics.py tests/test_llm_judge_parsing.py tests/test_run_logger.py -v
```

结果：

- core + validation: 14 tests OK。
- LoCoMo adapter: 7 tests OK。
- LongMemEval adapter: 12 tests OK。
- Task 9-12 focused tests: 26 tests OK。
- Phase 1 focused full suite: 59 tests OK。

本轮 handoff 前也确认：

```bash
find docs -maxdepth 3 -type f | sort
```

当前 active docs 只有：

- `docs/superpowers/plans/2026-06-02-conversation-qa-refactor-phase1.md`
- `docs/superpowers/specs/2026-06-02-conversation-qa-refactor-design.md`

同时运行了 Task 3-6 窄范围旧协议搜索。结果：代码范围内无 blocker；仅 `memory_benchmark/core/Readme.md` 仍有旧协议说明，它属于 Task 13 文档重写范围。

## 下一步必须做什么

### Step 1: 派发 Task 9-12 code quality reviewers

只读审查，建议可以 2 个一组，避免上下文和工具状态过乱。

Task 9 质量审查范围：

- `memory_benchmark/methods/mock.py`
- `memory_benchmark/runners/conversation_qa.py`
- `tests/test_conversation_runner.py`

Task 10 质量审查范围：

- `memory_benchmark/evaluators/locomo_f1.py`
- `tests/test_locomo_answer_metrics.py`
- `memory_benchmark/evaluators/__init__.py`

Task 11 质量审查范围：

- `memory_benchmark/evaluators/llm_judge.py`
- `memory_benchmark/evaluators/locomo_judge.py`
- `memory_benchmark/evaluators/longmemeval_judge.py`
- `memory_benchmark/evaluators/__init__.py`
- `memory_benchmark/core/exceptions.py`
- `memory_benchmark/core/__init__.py`
- `tests/test_llm_judge_parsing.py`

Task 12 质量审查范围：

- `memory_benchmark/utils/run_logger.py`
- `tests/test_run_logger.py`

统一质量重点：

- 是否还有 active 旧协议。
- 是否符合 conversation-QA v2 公开/私有隔离。
- 是否没有 retrieval recall、reset、ingest、respond、top_k、async、效率指标。
- 中文模块说明、类/函数 docstring 是否清楚。
- 错误处理是否用项目领域异常，不静默吞错。
- 库代码不能直接 `print()`；日志通过统一 logger。
- `.env` / API key 不能进入日志或测试输出。

### Step 2: 复审通过后集中验证

```bash
uv run python -m unittest tests/test_core_conversation_entities.py tests/test_conversation_dataset_validation.py tests/test_locomo_conversation_adapter.py tests/test_longmemeval_conversation_adapter.py tests/test_conversation_runner.py tests/test_locomo_answer_metrics.py tests/test_llm_judge_parsing.py tests/test_run_logger.py -v
rg -n "UnifiedMemoryAgent|reset\\(|ingest\\(|respond\\(|EvalScope|MemorySegment|EvalQuery|EvalOutput|retrieval recall|NDCG|hit rate" memory_benchmark tests docs AGENTS.md README.md --glob '!methods/mem0-main/**' --glob '!old/**' || true
```

通过后再进入 Task 13-15：README、core Readme、docs 重写、旧测试清理和最终验证。

## 不要做的事

- 不要从 `old/` 恢复旧协议。
- 不要实现 retrieval recall。
- 不要把 gold answer/evidence 放进 `Question.metadata`。
- 不要重新引入 `reset/ingest/respond`。
- 不要继续 mem0 真实实验；当前目标是框架整改。
- 不要一次性铺开 HaluMem、MemBench、Mem-Gallery。

## 额度/上下文保护策略

我无法读取用户 5h 额度的实时剩余百分比，因此不能准确检测“少于 10%”。为了尽量做到中断后无缝恢复，后续执行必须采用以下策略：

1. 每完成一个 task 或 review checkpoint，立即更新本 handoff 或新增 `docs/handoffs/YYYY-MM-DD-<topic>.md`。
2. 每次派发 subagent 后，把 agent id、nickname、任务、等待状态写入 handoff。
3. 每次进入大范围文件修改前，先确认 handoff 中记录了当前断点和回滚/续跑方式。
4. 如果出现长时间等待、上下文压缩迹象或用户提示额度风险，立刻暂停新实现，更新 handoff。
5. 下一窗口优先读 `AGENTS.md` 和最新 handoff，再继续，不要依赖上一个窗口的隐式记忆。

Subagent 指令后续可优先使用英文，以提高 LLM 执行稳定性；但项目规则、中文注释要求、用户确认的中文术语必须明确写入。

## 最小续跑命令

新窗口开始后先跑：

```bash
cd /Users/wz/Desktop/memoryBenchmark
uv run python -m unittest tests/test_conversation_runner.py tests/test_locomo_answer_metrics.py tests/test_llm_judge_parsing.py tests/test_run_logger.py -v
rg -n "UnifiedMemoryAgent|reset\\(|ingest\\(|respond\\(|EvalScope|MemorySegment|EvalQuery|EvalOutput|retrieval recall|NDCG|hit rate" memory_benchmark tests docs AGENTS.md README.md --glob '!methods/mem0-main/**' --glob '!old/**' || true
```

如果测试通过且旧协议搜索没有 active blocker，直接派发 Task 9-12 code quality review。
