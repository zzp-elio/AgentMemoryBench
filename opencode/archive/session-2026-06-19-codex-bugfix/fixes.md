# 2026-06-19 Codex 变更 bug 修复记录

## Bug 1: `allow_smoke_worker_override` 修复

**文件**: `src/memory_benchmark/methods/registry.py`

A-Mem (line 537)、LightMem (line 594)、MemoryOS (line 623) 各加一行：
```python
allow_smoke_worker_override=True,
```

**测试更新**: `tests/test_memoryos_registered_prediction.py`

1. `test_memoryos_smoke_worker_override_is_rejected_before_factory_or_runner`
   → 改名 `test_memoryos_smoke_worker_override_is_accepted`，语义反转

2. `_patch_memoryos_registration()` 扩展为同时 mock
   `efficiency_instrumentation_identity_getter` 和
   `efficiency_model_inventory_getter`，避免 tmp_path 缺少 wrapper 文件

3. 新增 `from memory_benchmark.observability.efficiency.entities import ModelDescriptor`

---

## Bug 2: Isolated worker efficiency scope 修复

**文件**: `src/memory_benchmark/runners/prediction.py`

`_isolated_worker()` (line 1186-1195)：

旧代码：
```python
if work_item.needs_ingest:
    system.add([public_conversation])
```

新代码：
```python
if work_item.needs_ingest:
    if (
        efficiency_collector is not None
        and efficiency_collector.enabled
    ):
        started_ns = perf_counter_ns()
        with efficiency_collector.conversation_scope(
            conversation.conversation_id,
        ) as conv_scope:
            system.add([public_conversation])
            efficiency_collector.record_memory_build_total_latency(
                latency_ms=_elapsed_ms(started_ns),
            )
        conv_observations.extend(conv_scope.records)
    else:
        system.add([public_conversation])
```

排除了旧代码中对 `conv_observations` 的 `list` 声明位置问题（原先声明在 `add()` 之后，现改为在 `add()` 之前声明，因为 `conv_scope.records` 需要收集到 `conv_observations`）。

---

## 验证

```bash
uv run python -m compileall -q src/memory_benchmark tests
# exit 0

uv run pytest tests/test_memoryos_registered_prediction.py tests/test_method_registry.py tests/test_prediction_runner.py tests/test_main_cli.py -q
# 90 passed

uv run pytest tests/test_prediction_runner.py tests/test_main_cli.py tests/test_cost_calibration_smoke.py tests/test_amem_adapter.py tests/test_lightmem_adapter.py tests/test_amem_lightmem_registry.py tests/test_method_registry.py tests/test_memoryos_registered_prediction.py -q
# 141 passed, 2 warnings (third-party pydantic deprecation)
```
