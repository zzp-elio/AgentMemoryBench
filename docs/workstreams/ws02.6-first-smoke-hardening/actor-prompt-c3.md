# 发给 actor：LongMemEval C3

C1、C2 已完成并由架构师验收（commits `dda4487`、`c3c5264`），不要重做。当前
只执行 `docs/workstreams/ws02.6-first-smoke-hardening/plan-b2-longmemeval.md`
的 **C3：unified answer prompt + answer LLM 归一**；完成后停下，不要开始 C4。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b2-longmemeval.md`
   第 1、2 节和第 3 节的 C3
4. `docs/reference/actor-handbook.md`（规矩全文，必读）
5. **官方事实源（模板必须从这里逐字抄，不许从 plan 转抄）**：
   `third_party/benchmarks/LongMemEval-main/src/generation/run_generation.py`
   第 46-70 行（非 CoT、`merge_key_expansion_into_value='none'` 分支，即
   第 57 行模板）与第 360-368 行（调用参数）
6. **结构模板（照此模式做）**：LoCoMo A4 的落法——
   `src/memory_benchmark/benchmark_adapters/locomo_prompt.py`、
   registry 注册块的 `prompt_track="unified"` + `unified_prompt_builder`、
   `src/memory_benchmark/config/settings.py` 中 LoCoMo answer 配置按
   benchmark 归一的写法

不要碰 metric/evaluator（C4），不要改 smoke/resume policy（C2 已冻），不要改
其他 benchmark 的 prompt 或 answer 配置，不要调用真实 API，不要运行全量
pytest/compileall，不要更新 README/roadmap/survey/frozen 文档。

本批只做三件事：

1. **新建 `src/memory_benchmark/benchmark_adapters/longmemeval_prompt.py`**：
   `build_longmemeval_unified_answer_prompt(...)`，使用官方非-CoT 模板
   （`run_generation.py:57` 逐字）：
   - `History Chats` 槽位 = provider 返回的 `formatted_memory` **原样代入**，
     框架不重排、不截断、不二次拼 `### Session` 头（那是官方对原始 haystack
     的排版；我们的记忆内容排版权属于 method）；
   - `Current Date` 槽位 = 公开 `question_date`（已在 Question 的
     `question_time` 与 metadata 中，`longmemeval.py:223,233`，无边界改动）；
     该字段理论上非空，但仍需处理缺失：为 None 时用空串代入并在 prompt
     metadata 记 warning 标记，不崩；
   - `Question` 槽位 = 公开 question 文本；
   - 超长不截断、不崩（长度控制是 method 的责任）。
2. **registry 注册**：longmemeval 注册块加 `prompt_track="unified"` +
   `unified_prompt_builder=build_longmemeval_unified_answer_prompt`；
   native 不需要额外代码（`--prompt-track native` 全局机制已有）。
3. **answer LLM 配置按 benchmark 归一**（对齐 LoCoMo A4 在
   `config/settings.py` 的做法）：LongMemEval 下所有 method 固定
   `gpt-4o-mini`、role=user、temperature=0、`max_tokens=500`、n=1
   （官方 `run_generation.py:360-368` 的非-CoT 参数）；把 (method,
   longmemeval) 的分叉收敛为 longmemeval 单键；不改其他 benchmark。

直接相关测试按需更新/新增（参照 LoCoMo A4 动过的测试面）：
`tests/test_prediction_cli.py`、`tests/test_benchmark_registry.py`、
`tests/test_config_profiles.py`、`tests/test_longmemeval_conversation_adapter.py`，
以及新建 prompt builder 的单测（对照 `tests/` 下 locomo prompt 测试的组织方式）。

完成后只运行一次：

```bash
uv run pytest -q tests/test_prediction_cli.py tests/test_benchmark_registry.py \
  tests/test_config_profiles.py tests/test_longmemeval_conversation_adapter.py
```

（若你新建了独立的 prompt 测试文件，把它追加到同一条命令里一起跑。）

通过后做一个本地 commit（不 push），只提交本批文件，commit message：
`feat(ws02.6): freeze LongMemEval unified answer prompt + per-benchmark answer config`。

最后只回复：commit hash、测试尾行、实际改动文件、是否存在 plan 偏差/停工点。
遇到 plan 未覆盖的情况立即停工写断点，交回架构师裁决，不要自行发挥。
