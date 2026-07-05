# 2026-06-21 Retrieve-first Task 15 Artifact Evaluation Handoff

## 状态

已完成 retrieve-first 实施计划 Task 15：answer-level artifact evaluation 与新增
retrieval artifact 兼容。

## 本次改动

- 在 `tests/test_artifact_evaluation_runner.py` 新增
  `test_answer_level_evaluation_ignores_retrieval_artifact_by_default`。
  该测试构造最小 answer-level run，同时写入
  `artifacts/retrieval_results.prediction.jsonl`，断言
  `run_artifact_evaluation()` 默认只依赖：
  - `artifacts/public_questions.jsonl`
  - `artifacts/method_predictions.jsonl`
  - `artifacts/evaluator_private_labels.jsonl`
- 该测试锁定当前规则：除非未来 evaluator 显式声明需要 retrieval context，
  F1/Judge 等 answer-level metric 不读取 retrieval artifact。
- 同步修复同文件中的 LongMemEval offline smoke 装配测试：
  - 旧 fake method 从 `BaseMemorySystem + ANSWER_GENERATION` 迁移为
    `BaseMemoryProvider + MEMORY_RETRIEVAL`。
  - 测试继续保持离线：不读真实 `.env`，通过 fake OpenAI-compatible settings 和
    fake answer client 装配 framework reader。
  - 该修复不是生产逻辑修改，只是测试夹具跟随 retrieve-first 注册契约迁移。

## 验证

已通过：

```bash
uv run pytest tests/test_artifact_evaluation_runner.py::test_answer_level_evaluation_ignores_retrieval_artifact_by_default -q
```

结果：

```text
1 passed
```

已通过：

```bash
uv run pytest tests/test_artifact_evaluation_runner.py tests/test_llm_judge_parsing.py -q
```

结果：

```text
29 passed
```

未执行真实 API。

## 文档同步

已更新：

- `docs/superpowers/plans/2026-06-20-retrieve-first-memory-module.md`
- `docs/current-roadmap.md`
- `docs/task-ledger.md`
- `AGENTS.md`

## 下一步

进入 retrieve-first 实施计划 Task 16：文档与迁移清理。

重点：

- 更新 README / method interface inventory，让用户看到当前主协议为
  `BaseMemoryProvider.add(conversation) + retrieve(question)`。
- 明确旧 `get_answer()` / `BaseMemorySystem` / `BaseResumableMemorySystem` /
  `BaseMemoryRetriever` 是迁移期兼容，不是新 method 接入主线。
- 继续保留旧路径，直到四个内置 method 和 smoke/full 验证都稳定后再删除。
