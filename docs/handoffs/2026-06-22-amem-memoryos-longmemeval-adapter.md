# 2026-06-22 A-Mem / MemoryOS LongMemEval Adapter Handoff

## 本次完成

- A-Mem 已新增 LongMemEval retrieve-first reader 分支：
  - 识别 `Question.question_time` 或 LongMemEval question type。
  - 保留 A-Mem 官方 query keyword generation、category `k`、retriever memory context 和 metadata。
  - LongMemEval prompt 使用 LightMem-style role messages：
    `system: You are a helpful assistant.` +
    `user: Question time:<date> and question:<question> ... memories: <A-Mem memory context>`。
- MemoryOS 已新增 LongMemEval retrieve-first reader 分支：
  - 继续调用官方 eval `retrieval_system.retrieve(...)`。
  - LongMemEval prompt 使用 LightMem-style role messages。
  - 不丢 MemoryOS 的核心上下文：recent context、retrieval queue、user profile、
    long-term knowledge 和 assistant knowledge 都进入 prompt / `answer_context`。
  - LoCoMo 分支仍保持 MemoryOS 官方 eval prompt 结构，旧 `get_answer()` 仅作为兼容路径。
- A-Mem / MemoryOS LongMemEval answer LLM 参数已对齐 LightMem LongMemEval profile：
  `temperature=0.0`、`top_p=0.8`、`max_tokens=2000`。
- LongMemEval judge prompt 已从简化 prompt 迁移为官方
  `third_party/benchmarks/LongMemEval-main/src/evaluation/evaluate_qa.py`
  的 task-specific 规则：
  - common QA: `single-session-user`、`single-session-assistant`、`multi-session`
  - `temporal-reasoning`: off-by-one days/weeks/months 容错
  - `knowledge-update`: 旧信息 + 更新答案时按更新答案判断
  - `single-session-preference`: gold answer 作为 personalized rubric
  - `_abs` question id: 官方 unanswerable / abstention 规则
  - 输出格式仍映射到本项目 compact/detailed parser。

## 修改的关键文件

- `src/memory_benchmark/methods/amem_adapter.py`
- `src/memory_benchmark/methods/memoryos_adapter.py`
- `src/memory_benchmark/config/settings.py`
- `src/memory_benchmark/evaluators/longmemeval_judge.py`
- `tests/test_amem_adapter.py`
- `tests/test_memoryos_adapter.py`
- `tests/test_config_profiles.py`
- `tests/test_llm_judge_parsing.py`
- `AGENTS.md`
- `README.md`
- `docs/current-roadmap.md`
- `docs/task-ledger.md`
- `docs/method-interface-inventory.md`
- `docs/superpowers/specs/2026-06-22-amem-memoryos-longmemeval-design.md`
- `docs/superpowers/plans/2026-06-22-amem-memoryos-longmemeval.md`

## 已验证

- `uv run pytest tests/test_amem_adapter.py tests/test_memoryos_adapter.py tests/test_config_profiles.py tests/test_llm_judge_parsing.py tests/test_documentation_standards.py -q`
  - `181 passed, 1 warning, 2 subtests passed`
  - warning 来自第三方 A-Mem `ast.Str` deprecation。
- `uv run pytest tests/test_evaluator_registry.py -q`
  - `6 passed`
- `uv run python -m compileall -q src/memory_benchmark tests`
  - exit 0
- `git diff --check`
  - exit 0

未执行真实 API。

## 当前判断

- A-Mem / MemoryOS 现在具备 LongMemEval retrieve-first 代码主体。
- 这不等于 full 复现已完成；仍需真实 LongMemEval-S 极小 smoke 验证：
  - third-party 状态构建是否可承受 LongMemEval 输入；
  - retrieval 是否能稳定返回可用 context；
  - framework answer LLM 是否按新的 prompt messages 正常回答；
  - efficiency observation 是否完整落盘。

## 下一步建议

1. 让用户确认 LongMemEval-S 极小 smoke 的 `run_id`、规模和预算。
2. 建议先跑 4 个 method 的极小单独命令，规模保持很小，例如：
   - `--profile smoke`
   - `--variant s_cleaned`
   - `--smoke-conversation-limit 1`
   - `--question-limit-per-conversation 1`
   - `--smoke-max-workers 1`
3. 真实 smoke 完成后检查：
   - `artifacts/answer_prompts.prediction.jsonl` 是否有非空 `prompt_messages`
   - `artifacts/method_predictions.jsonl` 是否有 answer
   - `summaries/efficiency_overall.prediction.json`
   - `logs/run.log` 和 structured events 是否无 fatal error
4. 若 LongMemEval-S smoke 通过，再讨论是否扩大到更多 conversations 或进入 full。
