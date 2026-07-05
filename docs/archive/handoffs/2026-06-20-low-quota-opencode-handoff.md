# 2026-06-20 低额度交接：交给 OpenCode 前的最新状态

## 本轮 Codex 已完成

### 1. Mem0 isolated worker conversation observation

问题：

- 真实旧 run `outputs/mem0-locomo-smoke10c-10t-w10-20260620/` 功能成功，但
  `memory_build_latency_ms.count=0`。

根因：

- isolated worker 在 `conversation_scope` 退出前读取 `conv_scope.records`。
- `EfficiencyCollector` 只在 scope 正常退出后冻结 records。

修复：

- `src/memory_benchmark/runners/prediction.py` 已把读取 `conv_scope.records` 移到
  scope 退出后。
- 新增测试覆盖 isolated worker 会持久化 conversation-level observation。

状态：

- 代码已离线验证。
- 旧 run 仍不能作为完整 memory-build efficiency 依据。
- 需要新代码极小真实 API smoke 复验。

### 2. LightMem OP-update memory-build LLM usage

问题：

- 真实旧 run `outputs/lightmem-api-smoke-v2/` 未记录 OP-update 内部
  `manager.generate_response()` 的 build LLM usage。

根因：

- LightMem 官方 OP-update 内部使用 `ThreadPoolExecutor.map()`，ContextVar scope 不传播。

修复：

- `src/memory_benchmark/methods/lightmem_adapter.py` 已加入子线程 usage buffer。
- 子线程中解析 usage 后暂存；`add()` 回到 conversation scope 后 flush 到 collector。
- 不修改 LightMem 核心算法、prompt、调用顺序或返回值。

状态：

- fake 线程池 OP-update 测试已通过。
- 旧 run 仍不能作为完整 LightMem build LLM 成本依据。
- 需要新代码极小真实 API smoke 复验。

### 3. LoCoMo smoke question-limit

问题：

- LoCoMo smoke adapter 过去每 conversation 只保留 1 道 evidence 覆盖题，导致
  `--question-limit-per-conversation > 1` 实际无效。

修复：

- `src/memory_benchmark/benchmark_adapters/locomo.py` 已改为保留所有 evidence 完整落在
  截断历史里的问题。
- runner 再按 `question_limit_per_conversation` 做本次命令预算裁剪。
- `smoke_turn_limit` 过小仍 fail closed。

状态：

- 定向测试已通过。

## 本轮验证

```bash
uv run pytest tests/test_lightmem_adapter.py::test_lightmem_records_memory_build_manager_api_usage tests/test_lightmem_adapter.py::test_lightmem_buffers_threaded_offline_update_manager_usage -q
# 2 passed

uv run pytest tests/test_lightmem_adapter.py -q
# 20 passed, 1 warning

uv run pytest tests/test_prediction_runner.py tests/test_prediction_efficiency_observations.py -q
# 61 passed

uv run pytest tests/test_lightmem_adapter.py tests/test_amem_lightmem_registry.py tests/test_method_registry.py tests/test_config_profiles.py tests/test_main_cli.py tests/test_cost_calibration_smoke.py -q
# 84 passed, 1 warning

uv run pytest tests/test_prediction_cli.py::test_smoke_dataset_keeps_turns_covering_private_evidence_sets tests/test_prediction_cli.py::test_smoke_dataset_keeps_all_questions_covered_by_retained_evidence tests/test_prediction_cli.py::test_smoke_dataset_can_select_two_independent_conversations tests/test_prediction_cli.py::test_smoke_dataset_rejects_history_without_answerable_question tests/test_benchmark_registry.py::test_locomo_registration_prepares_full_and_smoke_datasets tests/test_documentation_standards.py -q
# 10 passed

uv run python -m compileall -q src/memory_benchmark tests
# exit 0

git diff --check
# exit 0
```

## 文档已同步

- `AGENTS.md`
- `README.md`
- `docs/current-roadmap.md`
- `docs/task-ledger.md`
- `docs/handoffs/2026-06-20-observability-fixes-mem0-lightmem.md`
- `docs/handoffs/2026-06-20-locomo-smoke-question-limit.md`

## OpenCode 接手建议

优先级按下面顺序：

1. 用新代码做极小真实 API smoke 复验：
   - Mem0: 1-2 conversation、20 turns、1-2 questions、worker 1-2。
   - LightMem: 1 conversation、20 turns、1 question、worker 1。
   - 检查 `artifacts/efficiency_observations.prediction.jsonl` 和
     `summaries/efficiency_overall.prediction.json` 是否包含 conversation-level build
     observation 和 LightMem memory-build LLM usage。
2. 如果 smoke 通过，把 `docs/task-ledger.md` 中 Mem0 isolated observation 与 LightMem
   OP-update observation 从 `partially_closed` 更新为 `closed`。
3. 继续 P0：四个 method 的 prediction efficiency 覆盖矩阵。
4. 继续 P0/P1：非 Mem0 method 的 API/network retry/timeout 审计。

## 不要做

- 不要启动 full API 实验。
- 不要删除或覆盖 `outputs/memoryos-locomo-full-20260603/`。
- 不要把旧 run 的 observation 当作新代码修复后的事实。
- 不要恢复 PrefEval。

## Claude Code 备注

Codex 本轮尝试 `claude -p ...` 时返回：

```text
API Error: Unable to connect to API (ConnectionRefused)
```

这更像是 Codex 受限 shell / 沙箱中的网络或本地 Claude 服务连接问题，不代表用户本机
Claude Code 配置坏。用户已确认自己直接运行 Claude Code 正常。后续如果 Codex 需要使用
Claude Code，可尝试：

- 在 Codex 中用更小的 `claude -p` 只读任务；
- 若仍出现连接错误，再按 Codex 的沙箱规则申请 escalated command；
- 不把 Claude Code 结果直接采纳，必须复查 diff 和测试。
