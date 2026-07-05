# 2026-06-21 Retrieve-first Task 6 部分交接

## 时间

- 2026-06-21 00:43 CST 左右
- 本次未执行真实 API 调用。

## 当前任务

继续 `docs/superpowers/plans/2026-06-20-retrieve-first-memory-module.md` 的 Task 6：Wire OpenAI-Compatible Framework Reader。

## 已完成

1. 新增 OpenAI-compatible answer reader client 的不触网单测：
   - 文件：`tests/test_framework_answer_reader.py`
   - 测试：`test_openai_compatible_answer_client_uses_configured_model`
   - 红灯验证结果：ImportError，符合预期。
2. 实现 `OpenAICompatibleAnswerLLMClient`：
   - 文件：`src/memory_benchmark/readers/answer.py`
   - 行为：从 `OpenAISettings` 读取 `api_key/base_url/model/timeout/max_retries`，构造 OpenAI SDK client，并用 `chat.completions.create()` 返回纯文本 answer。
   - 同文件新增 `load_answer_prompt_template(...)`，可读取默认 prompt 或用户自定义 prompt 文件。
3. 更新 reader 包导出：
   - 文件：`src/memory_benchmark/readers/__init__.py`
   - 导出 `OpenAICompatibleAnswerLLMClient` 和 `load_answer_prompt_template`。
4. 新增 CLI prompt 参数映射测试：
   - 文件：`tests/test_main_cli.py`
   - 测试：`test_main_maps_answer_prompt_arguments_to_predict_command`
   - 红灯验证结果：argparse 不认识 `--answer-prompt-file` / `--answer-prompt-profile`，符合预期。
5. 完成 CLI/command 字段透传：
   - `src/memory_benchmark/cli/commands.py`
     - `PredictCommand.answer_prompt_file`
     - `PredictCommand.answer_prompt_profile`
     - `execute_predict()` 透传到 `run_registered_conversation_qa_prediction()`。
   - `src/memory_benchmark/cli/main.py`
     - 新增 `--answer-prompt-file`
     - 新增 `--answer-prompt-profile`
     - `_prediction_command_from_args()` 将相对路径解析成 `Path(...)` 存进 command。
   - `src/memory_benchmark/cli/run_prediction.py`
     - 函数签名先接收 `answer_prompt_file` / `answer_prompt_profile`，但尚未构造并传入真实 `FrameworkAnswerReader`。
6. 更新实施计划 Task 6 Step 1-5 为完成。

## 已验证

```bash
uv run pytest tests/test_framework_answer_reader.py::test_openai_compatible_answer_client_uses_configured_model -q
# 1 passed

uv run pytest tests/test_main_cli.py::test_main_maps_answer_prompt_arguments_to_predict_command tests/test_framework_answer_reader.py::test_openai_compatible_answer_client_uses_configured_model -q
# 2 passed
```

## 未完成

Task 6 还没有完成。下一步应继续：

1. 在 `tests/test_prediction_cli.py` 中补红灯测试，确认 `run_registered_conversation_qa_prediction()` 会构造 `FrameworkAnswerReader` 并把它传给 `run_predictions()`。
2. 在 `src/memory_benchmark/cli/run_prediction.py` 中使用：
   - `load_answer_prompt_template(project_root=root, prompt_file=answer_prompt_file, profile_name=answer_prompt_profile)`
   - `OpenAICompatibleAnswerLLMClient(settings=openai_settings)`
   - `FrameworkAnswerReader(...)`
3. 只对 retrieve-first provider path 传入 reader；旧 `get_answer()` path 暂时继续存在，直到后续 adapter 迁移完成。
4. 跑 Task 6 focused tests：

```bash
uv run pytest tests/test_framework_answer_reader.py tests/test_main_cli.py tests/test_prediction_cli.py -q
```

5. 如果通过，再更新 `docs/current-roadmap.md`、`docs/task-ledger.md`、`AGENTS.md`，并写 Task 6 完成交接。

## 注意事项

- 当前 git worktree 仍有大量历史未提交改动，不是本轮 Task 6 独有。不要直接大包 commit，除非先确认提交范围。
- 本轮只完成 Task 6 的前半段。不要把 retrieve-first CLI/config/manifest 迁移标记为完成。
- 当前 `run_registered_conversation_qa_prediction()` 已接收 `answer_prompt_file` / `answer_prompt_profile`，但参数尚未实际使用；这正是下一步要做的事情。
- 未执行真实 API。
