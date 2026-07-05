# 2026-06-25 Custom Method Onboarding And Clean Retry Handoff

## 本次完成

- 新增用户自定义 method 轻量加载器：
  `src/memory_benchmark/methods/custom_loader.py`。
  加载格式为 `module:ClassName`，要求目标类无参数构造且实例是
  `BaseMemoryProvider`。
- CLI 新增 `--method-class module:ClassName`，允许用户不通过内置 method registry/TOML
  运行自定义 method。
- CLI 新增 `--allow-unsafe-custom-parallel`。自定义 method 默认只允许 `workers=1`；
  如果用户显式确认并行风险，才允许 `workers>1`。
- `run_registered_conversation_qa_prediction()` 新增 custom method path：
  自定义 method 绕过内置 method profile、source identity 和白盒 efficiency inventory，
  但仍复用标准 benchmark adapter、conversation-QA runner、framework answer reader、
  prediction artifact 和基础 efficiency observation。
- 新增端到端 fake custom method smoke 测试，验证只实现
  `BaseMemoryProvider.add(conversation)` 和 `retrieve(question)` 也能写出
  `method_predictions.jsonl` 与 `answer_prompts.prediction.jsonl`。
- Prediction runner 的失败状态从旧的泛化 `failed` 细化为：
  - `failed_ingest`：`add()` 阶段失败，可能留下脏记忆状态。
  - `failed_answer`：记忆已写入，只是回答阶段失败。
- `failed_answer` 在 `--retry-failed` 下可以只补 pending questions，不重新 `add()`。
- `failed_ingest` 在没有 clean retry support 时会 fail closed，避免重复写入污染记忆。
- 新增普通用户接入指南：`docs/custom-method-onboarding.md`。
- 已同步更新：
  - `README.md`
  - `AGENTS.md`
  - `docs/current-roadmap.md`
  - `docs/task-ledger.md`
  - `docs/superpowers/plans/2026-06-24-method-onboarding-clean-retry.md`

## 验证

已运行：

```bash
uv run pytest tests/test_custom_method_loader.py -q
# 4 passed

uv run pytest tests/test_prediction_cli.py::test_custom_method_class_runs_without_builtin_registry -q
# 1 passed

uv run pytest tests/test_prediction_runner.py -q
# 58 passed

uv run pytest tests/test_prediction_cli.py::test_custom_method_class_writes_prediction_artifacts -q
# 1 passed

uv run pytest tests/test_custom_method_loader.py tests/test_main_cli.py tests/test_prediction_cli.py tests/test_prediction_runner.py -q
# 131 passed

uv run pytest tests/test_documentation_standards.py -q
# 5 passed

uv run python -m compileall -q src/memory_benchmark tests
# exit 0

git diff --check
# exit 0
```

本轮没有执行真实 API 调用。

## 关键行为

普通用户最小接入方式：

```bash
uv run memory-benchmark predict smoke \
  --root . \
  --method-class my_package.my_adapter:MyMemory \
  --benchmark locomo \
  --run-id my-memory-locomo-smoke \
  --allow-api \
  --conversations 1 \
  --rounds 20 \
  --questions-per-conversation 1 \
  --workers 1
```

用户 adapter 第一版不接收框架构造参数。用户自己的 API key、数据库地址、内部模型参数
由用户自己的代码管理。框架只要求：

- 继承 `BaseMemoryProvider`。
- `add(conversation)` 写入一个 conversation 的记忆。
- `retrieve(question)` 返回 `AnswerPromptResult.prompt_messages`，即完整 answer prompt
  role messages。
- 保证 `question.conversation_id` 不会检索到其他 conversation 的记忆。

## 剩余事项

- 为四个内置 method 分别补 clean retry hook 或 attempt namespace 证明。当前 custom
  path 已能 fail closed，但内置 method 的安全重跑策略还没有逐一证明。
- 评估是否需要 `--method-file path.py:ClassName` 这种单文件快速测试入口。
- 后续在 retrieve-first 主路径完全稳定后，清理 legacy：
  `BaseMemorySystem`、`BaseResumableMemorySystem`、`BaseMemoryRetriever` 和过重
  capability 推理。
- 如需对外发布，需要把 `docs/custom-method-onboarding.md` 打磨成正式用户文档，并补一个
  最小可运行 example package。
