# 2026-06-20 观测缺口修复交接：Mem0 isolated worker + LightMem OP-update

## 本次背景

用户指出：

- `outputs/mem0-locomo-smoke10c-10t-w10-20260620/` 功能上跑通，但缺少
  conversation-level memory build observation。
- LightMem 真实旧 run `outputs/lightmem-api-smoke-v2/` 只记录 answer LLM usage，
  未记录 OP-update 内部 memory-build LLM usage。
- 这些缺口会直接影响按 conversation 估算 token、调用次数和耗时，因此属于 P0。

## 修复内容

### Mem0 isolated worker

根因：

- isolated worker 在 `conversation_scope` 还没退出时读取 `conv_scope.records`。
- `EfficiencyCollector` 只在 scope 正常退出后冻结 `ObservationScope.records`。
- 因此 worker bundle 没有把 `conversation_efficiency` 带回协调层。

修复：

- 在 `src/memory_benchmark/runners/prediction.py` 中，把
  `conv_observations.extend(conv_scope.records)` 移到 `with conversation_scope(...)`
  之外。
- 新增测试
  `tests/test_prediction_runner.py::test_isolated_worker_persists_conversation_efficiency_observation`。

注意：

- 旧 run `mem0-locomo-smoke10c-10t-w10-20260620` 不会自动变完整。
- 后续需要用新代码跑一个极小真实 API smoke，才能确认真实 artifact 中出现
  conversation-level build observation。

### LightMem OP-update

根因：

- LightMem LoCoMo OP-update 的 `offline_update_all_entries()` 内部使用
  `ThreadPoolExecutor.map()`。
- 子线程不会自动传播 `EfficiencyCollector` 的 ContextVar scope。
- 旧 observer 只在 `collector.active_scope_type() == "conversation"` 时记录，导致
  子线程中的 `manager.generate_response()` usage 丢失。

修复：

- 在 `src/memory_benchmark/methods/lightmem_adapter.py` 中新增
  `_BufferedMemoryManagerUsage`、线程安全 buffer 和 flush。
- `manager.generate_response()` 返回后先解析 usage：
  - 当前线程仍在 conversation scope 内：立即记录。
  - 子线程无 scope：暂存到当前 `conversation_id` 的 buffer。
- `LightMem.add()` 完成写入和 LoCoMo offline update 后，在仍处于 runner
  conversation scope 时 flush buffer，统一写入 `lightmem-memory-llm` 的
  memory_build LLM observation。
- 不修改第三方 LightMem 核心算法、prompt、调用顺序或返回值。

新增测试：

- `tests/test_lightmem_adapter.py::test_lightmem_records_memory_build_manager_api_usage`
- `tests/test_lightmem_adapter.py::test_lightmem_buffers_threaded_offline_update_manager_usage`

注意：

- 旧 run `lightmem-api-smoke-v2` 仍不能作为完整 LightMem build LLM 成本依据。
- 后续需要用新代码跑一个极小真实 API smoke 复验。

## 已执行验证

```bash
uv run pytest tests/test_lightmem_adapter.py::test_lightmem_records_memory_build_manager_api_usage tests/test_lightmem_adapter.py::test_lightmem_buffers_threaded_offline_update_manager_usage -q
# 2 passed

uv run pytest tests/test_lightmem_adapter.py -q
# 20 passed, 1 warning

uv run pytest tests/test_prediction_runner.py tests/test_prediction_efficiency_observations.py -q
# 61 passed

uv run pytest tests/test_lightmem_adapter.py tests/test_amem_lightmem_registry.py tests/test_method_registry.py tests/test_config_profiles.py tests/test_main_cli.py tests/test_cost_calibration_smoke.py -q
# 84 passed, 1 warning
```

## 文档同步

已更新：

- `AGENTS.md`
- `README.md`
- `docs/current-roadmap.md`
- `docs/task-ledger.md`

状态口径：

- Mem0 isolated worker observation：代码修复并离线验证，通过后仍需真实极小 smoke 复验。
- LightMem OP-update memory-build LLM observation：代码修复并离线验证，通过后仍需真实极小
  smoke 复验。

## Claude Code 尝试

本轮曾尝试用 Claude Code 做只读根因排查：

```bash
claude -p --max-budget-usd 0.25 "..."
```

Claude Code 返回 `API Error: Unable to connect to API (ConnectionRefused)`，未产出可采纳
结果。本次修复由 Codex 本地 TDD 完成。

## 下一步建议

1. 跑极小真实 API smoke 复验 Mem0 和 LightMem 的新 observation。
2. 若真实 observation 正常，再更新 `docs/task-ledger.md` 把对应任务从
   `partially_closed` 改为 `closed`。
3. 继续处理当前 P0：
   - LoCoMo smoke 下 `--question-limit-per-conversation > 1` 实际不生效。
   - 四个 method 的 prediction efficiency 覆盖矩阵。
   - API/network retry 与 timeout 的非 Mem0 method 审计。
