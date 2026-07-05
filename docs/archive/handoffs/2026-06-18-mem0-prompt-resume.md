# 2026-06-18 Mem0 Prompt / Top-k / Resume 交接

## 本轮目标

接续 `2026-06-17-amem-red-tests-handoff.md`，完成两个小切片：

1. 吸收 `docs/opencode-suggestions/` 中可采纳的 resume 分层建议。
2. 修正 Mem0 `get_answer()` 的 reader prompt，使其使用 vendored `memory-benchmarks`
   官方 LoCoMo / LongMemEval prompt，并保证 smoke 不降低官方 `top_k=200`。

本轮未执行真实 API，不启动任何 smoke/full prediction。

## 已完成

- `src/memory_benchmark/methods/mem0_adapter.py`
  - `MEM0_READER_PROMPT_VERSION` 升级为 `mem0-memory-benchmarks-reader-v2`。
  - `get_answer()` 的 reader 分支改为：
    - LoCoMo: `memory-benchmarks/benchmarks/locomo/prompts.py::get_answer_generation_prompt`
    - LongMemEval: `memory-benchmarks/benchmarks/longmemeval/prompts.py::get_answer_generation_prompt`
    - 未知 benchmark: 保留 generic fallback。
  - Mem0 source identity 纳入上述两个 prompt 文件，但不纳入整个 `memory-benchmarks` 仓库。
  - `Mem0Config.smoke()` 已从 `top_k=10` 改为 `top_k=200`。成本控制只能通过
    conversation/question/turn 规模裁剪，不能裁剪 method 参数。
  - 2026-06-18 纠偏：Mem0 不是只跑 LoCoMo；Mem0 仍支持 LongMemEval，但
    LongMemEval 只做 conversation-level resume。LoCoMo 保留 turn-level resume。
  - Mem0 LongMemEval `add()` 按官方 `CHUNK_SIZE=2` user+assistant pair 写入；
    `supports_turn_resume()` 对 LongMemEval 返回 False，runner 会退回完整
    `add([conversation])` 和 conversation-level resume。

- `tests/test_mem0_adapter.py`
  - 增加 LoCoMo official prompt 断言。
  - 增加 LongMemEval official prompt 断言。
  - 增加 LongMemEval pair 级写入断言。
  - 增加 LoCoMo/LongMemEval `supports_turn_resume()` 分流断言。
  - source identity 测试允许并要求两个 official prompt 文件。
  - smoke profile、search call 和 prediction metadata 均断言 `top_k=200`。

- `tests/test_prediction_runner.py`
  - 增加 `supports_turn_resume(conversation)=False` 时 runner 退回完整 `add()`、
    不创建 turn checkpoint 的测试。

- `tests/test_method_registry.py` / `tests/test_config_profiles.py`
  - registry 列表测试更新为当前四个 conversation-QA methods：
    `amem`, `lightmem`, `mem0`, `memoryos`。
  - Mem0 smoke TOML 测试更新为 `top_k=200`。

- 文档更新
  - 新增 `docs/superpowers/specs/2026-06-18-mem0-prompt-resume-design.md`。
  - `docs/method-interface-inventory.md` 增加 resume 分层表。
  - `docs/current-roadmap.md` 标记 Mem0 prompt/top-k 已完成，并记录
    Mem0 LoCoMo turn-level resume / LongMemEval conversation-level resume 分流。
  - `docs/method-resource-parameter-audit.md` 修正 Mem0 写入粒度描述。
  - `AGENTS.md` 同步当前断点和验证结果。

## 关键事实

- Mem0 官方 LoCoMo runner:
  - `third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/run.py`
  - `CHUNK_SIZE = 1`
  - `session_to_chunks()` 会把 LoCoMo turns 格式化为 messages，然后每条 message 一次 add。
  - 当前 adapter 逐 turn 写入，因此 LoCoMo 写入粒度已对齐。

- Mem0 官方 LongMemEval runner:
  - `third_party/methods/mem0-main/memory-benchmarks/benchmarks/longmemeval/run.py`
  - `CHUNK_SIZE = 2`
  - `pair_turns()` 按 user+assistant pair 写入。
  - 当前 adapter 已按官方 pair 级写入，但不做 turn-level resume；runner 只做
    conversation-level resume。

- Mem0 OSS 本体没有统一 `answer(question)`。本项目 `Mem0.get_answer()` 的正确包装方式是：

```text
Memory.search(...) -> official benchmark get_answer_generation_prompt(...) -> answerer LLM
```

## 已验证

最终收口验证：

```bash
uv run pytest tests/test_mem0_adapter.py tests/test_mem0_source_compatibility.py tests/test_prediction_runner.py tests/test_conversation_runner.py tests/test_main_cli.py tests/test_cost_calibration_smoke.py tests/test_method_registry.py tests/test_config_profiles.py -q
# 99 passed

uv run pytest tests/test_documentation_standards.py -q
# 5 passed

uv run python -m compileall -q src/memory_benchmark tests
# exit 0

git diff --check
# exit 0
```

本轮未执行真实 API。

历史中间验证：

```bash
uv run pytest tests/test_mem0_adapter.py tests/test_method_registry.py tests/test_config_profiles.py tests/test_documentation_standards.py -q
# 40 passed

uv run pytest tests/test_mem0_adapter.py tests/test_mem0_source_compatibility.py tests/test_conversation_runner.py tests/test_main_cli.py tests/test_cost_calibration_smoke.py tests/test_method_registry.py tests/test_config_profiles.py -q
# 71 passed

uv run python -m compileall -q src/memory_benchmark tests
# exit 0
```

中间按 TDD 先改测试后跑过红测：

```text
4 failed, 31 passed
```

失败点正是 `Mem0Config.smoke().top_k == 10` 和 search metadata 仍为 10，确认测试有效。

## 当前未提交文件

预计至少包含：

- `AGENTS.md`
- `docs/current-roadmap.md`
- `docs/method-interface-inventory.md`
- `docs/method-resource-parameter-audit.md`
- `docs/superpowers/specs/2026-06-18-mem0-prompt-resume-design.md`
- `src/memory_benchmark/methods/mem0_adapter.py`
- `tests/test_config_profiles.py`
- `tests/test_mem0_adapter.py`
- `tests/test_method_registry.py`

## 下一步建议

1. 如需提交，先再次跑：
   `uv run pytest tests/test_documentation_standards.py -q`
   和 `uv run python -m compileall -q src/memory_benchmark tests`。
2. 如果用户要求提交，验证后 commit。
3. LoCoMo 方向可优先做极小真实 smoke：Mem0 + LoCoMo 1 conversation / 1 question，
   但必须先让用户确认 run_id、预算和 API 余额。
4. LongMemEval 方向可做 Mem0 + LongMemEval-S 1 instance / 1 question smoke；该路径
   使用 conversation-level resume。
5. 继续保持不启动全量实验；真实费用和 token/cost 聚合仍在实验 artifact 生成后离线计算。

## 额度前最新断点（2026-06-18）

用户纠正了一个关键语义：不是“Mem0 只跑 LoCoMo”，而是：

- Mem0 + LoCoMo：官方 `CHUNK_SIZE=1`，保留 turn-level resume。
- Mem0 + LongMemEval：官方 `CHUNK_SIZE=2` user+assistant pair，仍然要能跑实验，
  但只做 conversation-level resume，不做 turn-level resume。

本轮已经据此修改：

- `BaseResumableMemorySystem` 增加默认方法
  `supports_turn_resume(conversation) -> bool`。
- 通用 prediction runner 已按 conversation 调用该方法：
  - True: 使用 `add_from_turn()` 和 turn checkpoint。
  - False: 使用完整 `add([conversation])`，不创建 turn checkpoint，依赖 coarse
    conversation status 实现 conversation-level resume。
- Mem0 adapter:
  - `supports_turn_resume()` 对 LongMemEval 返回 False。
  - `add()` 对 LongMemEval 按官方 `CHUNK_SIZE=2` pair 写入。
  - `add_from_turn()` 对 LongMemEval 仍显式拒绝，防止绕过 runner 误用 turn-level resume。
  - LongMemEval official answer prompt 和 source identity 已恢复。
- `tests/test_mem0_adapter.py` 已增加 pair 写入、LongMemEval official prompt、
  LoCoMo/LongMemEval resume 分流测试。
- `tests/test_prediction_runner.py` 已增加 selective resumable fake，验证
  `supports_turn_resume=False` 时 runner 使用完整 `add()` 且不写 turn checkpoint。

已通过：

```bash
uv run pytest tests/test_mem0_adapter.py -q
# 17 passed

uv run pytest tests/test_prediction_runner.py::test_resumable_system_can_disable_turn_resume_per_conversation -q
# 1 passed

uv run pytest tests/test_mem0_adapter.py tests/test_prediction_runner.py::test_resumable_system_can_disable_turn_resume_per_conversation tests/test_method_registry.py tests/test_config_profiles.py tests/test_documentation_standards.py -q
# 43 passed

uv run python -m compileall -q src/memory_benchmark tests
# exit 0
```

宽回归当前结果已更新：

```bash
uv run pytest tests/test_mem0_adapter.py tests/test_mem0_source_compatibility.py tests/test_prediction_runner.py tests/test_conversation_runner.py tests/test_main_cli.py tests/test_cost_calibration_smoke.py tests/test_method_registry.py tests/test_config_profiles.py -q
# 99 passed

uv run pytest tests/test_documentation_standards.py -q
# 5 passed

uv run python -m compileall -q src/memory_benchmark tests
# exit 0

git diff --check
# exit 0
```

已修复的旧断言：

- `tests/test_prediction_runner.py::test_non_resumable_method_rejects_existing_turn_checkpoint`
  已从匹配旧报错 `BaseResumableMemorySystem` 改为匹配
  `method does not enable turn-level resume`。
