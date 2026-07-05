# 2026-06-19 Codex 变更 bug 诊断与修复

## 1. 读了哪些文件

| 文件 | 用途 |
|------|------|
| `src/memory_benchmark/methods/registry.py:88-108` | `MethodRegistration` dataclass 定义，`allow_smoke_worker_override` 默认值 |
| `src/memory_benchmark/methods/registry.py:517-543` | A-Mem registration |
| `src/memory_benchmark/methods/registry.py:544-570` | Mem0 registration（对照：`allow_smoke_worker_override=True`） |
| `src/memory_benchmark/methods/registry.py:573-600` | LightMem registration |
| `src/memory_benchmark/methods/registry.py:600-635` | MemoryOS registration |
| `src/memory_benchmark/methods/registry.py:478-497` | `_memoryos_efficiency_instrumentation_identity()` |
| `src/memory_benchmark/cli/run_prediction.py:277-284` | `_resolve_smoke_max_workers()` 调用点 |
| `src/memory_benchmark/cli/run_prediction.py:688-710` | `_resolve_smoke_max_workers()` 实现 |
| `src/memory_benchmark/runners/prediction.py:1166-1247` | `_isolated_worker()` — add() 不在 scope 里 |
| `src/memory_benchmark/runners/prediction.py:1425-1454` | `_ingest_one()` — 对照：非 isolated 路径用 `conversation_scope` 包 add() |
| `src/memory_benchmark/observability/efficiency/collector.py:369` | `_require_scope()` — 无 active scope 时抛错 |
| `configs/methods/amem.toml` | A-Mem smoke profile 有 `max_workers=1` |
| `configs/methods/lightmem.toml` | LightMem smoke profile 有 `max_workers=1` |
| `tests/test_memoryos_registered_prediction.py:293-306` | `_patch_memoryos_registration()` 原始实现 |
| `tests/test_memoryos_registered_prediction.py:787-839` | `test_memoryos_smoke_worker_override_is_rejected_before_factory_or_runner` |
| `tests/test_prediction_cli.py:410,525,565,614,738,888,1003,1086,1377,1487` | Mem0 测试全部 `allow_smoke_worker_override=True` |
| `git log --oneline -5` | 确认 `allow_smoke_worker_override` 在首次 commit `97e9d44` 引入，只有 Mem0 设 True |

## 2. 根因分析

### Bug 1: `--smoke-max-workers` 仅 Mem0 可用

**根因**：历史残留。`MethodRegistration.allow_smoke_worker_override` 字段在项目首次 commit `97e9d44` (2026-06-17) 引入，当时只有 Mem0 一个 method，`--smoke-max-workers` 是为 Mem0 诊断并发设计的。后续 A-Mem、LightMem、MemoryOS 接入时（2026-06-16/17），漏设该字段，继承默认 `False`。

四个 method 的 TOML smoke profile 都有 `max_workers=1`（均在 `configs/methods/*.toml`），official-full 都有 `max_workers=10`，结构完全相同。Mem0 已不再使用内置并行——所有并行都走框架层 `ThreadPoolExecutor` 独立 worker。没有任何技术理由区分。

**证据**：
- `registry.py:565`：只有 Mem0 设 `allow_smoke_worker_override=True`
- `registry.py:537、594、622`：A-Mem/LightMem/MemoryOS 未设该字段→默认 `False`
- `run_prediction.py:704`：`if not allow_override: raise ConfigurationError(...)`
- 所有 tests/test_prediction_cli.py 的 Mem0 mock 都用 `allow_smoke_worker_override=True`

### Bug 2: Mem0 isolated worker `add()` 缺少 efficiency scope

**根因**：`_isolated_worker()` 重构时，`system.add()` 未被 efficiency scope 包裹，但非 isolated 路径 `_ingest_one()` 有。

对比：
- 非 isolated (`prediction.py:1436`): `with efficiency_collector.conversation_scope(id) as scope: system.add(...)`
- Isolated (`prediction.py:1188`): `system.add([public_conversation])` — 直接在 scope 外调用

Mem0 的 `add()` 内部会调 embedding → `EfficiencyCollector.record_embedding_call()` → `_require_scope()` 检查无 active scope → `ConfigurationError("Efficiency observation recording requires an active scope")`。

`efficiency_collector.enabled` 默认 `True`（Codex 改动），所以 Mem0 smoke 必触发此错误。

## 3. 修改了哪些文件

### 文件 1: `src/memory_benchmark/methods/registry.py`

**改动**: A-Mem (line 538)、LightMem (line 595)、MemoryOS (line 624) 各插入一行：
```python
allow_smoke_worker_override=True,
```

位置在 `display_name` 之后。

### 文件 2: `src/memory_benchmark/runners/prediction.py`

**`_isolated_worker()` 函数** (line 1186-1202)：旧代码：
```python
if work_item.needs_ingest:
    system.add([public_conversation])
conv_predictions: list[dict[str, Any]] = []
conv_observations: list[EfficiencyObservation] = []
```

新代码：
```python
conv_predictions: list[dict[str, Any]] = []
conv_observations: list[EfficiencyObservation] = []
if work_item.needs_ingest:
    if efficiency_collector is not None and efficiency_collector.enabled:
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

说明：
- `add()` 现在在 `conversation_scope` 内，与 `_ingest_one()` 行为一致
- `record_memory_build_total_latency()` 记录 conversation 级 build 耗时
- scope 结束后收集 `conv_scope.records` 到 `conv_observations`
- 新代码复用 `perf_counter_ns()` 和 `_elapsed_ms()`（均已定义于同文件）
- 声明 `conv_predictions`/`conv_observations` 的位置上移到 add() 之前，保证 scope records 能正确收集

### 文件 3: `tests/test_memoryos_registered_prediction.py`

**3a**: 改名并重写测试：
```python
test_memoryos_smoke_worker_override_is_rejected_before_factory_or_runner
→ test_memoryos_smoke_worker_override_is_accepted
```

旧测试断言 `pytest.raises(ConfigurationError, match="MemoryOS.*smoke-max-workers")`。
新测试验证 `run_predictions` 正常被调用（override 被接受）。

**3b**: 扩展 `_patch_memoryos_registration()`（line 293-316）— 原来只 mock `source_identity_factory`，现在同时 mock `efficiency_instrumentation_identity_getter` 和 `efficiency_model_inventory_getter`，避免 tmp_path 无 wrapper 源码文件导致 `_sha256_file()` 失败。mock 返回 `ModelDescriptor` 实例（非 dict），因为 `prediction.py:790` 要求 `.model_id` 属性。

**3c**: 新增 import `from memory_benchmark.observability.efficiency.entities import ModelDescriptor`

### 文件 4: `opencode/opencode_result.md`

更新最新结果指向 `session-2026-06-19-codex-bugfix/`。

### 新增文件

- `opencode/session-2026-06-19-codex-bugfix/diagnosis.md`：根因诊断
- `opencode/session-2026-06-19-codex-bugfix/fixes.md`：修复内容与验证
- `opencode/opencode_result-6.19-codex-bugfix.md`：本文件

## 4. 跑了哪些测试

```bash
# 编译检查
uv run python -m compileall -q src/memory_benchmark tests
# exit 0

# 核心聚焦
uv run pytest tests/test_memoryos_registered_prediction.py \
  tests/test_method_registry.py \
  tests/test_prediction_runner.py \
  tests/test_main_cli.py -q
# 90 passed

# 宽回归
uv run pytest tests/test_prediction_runner.py \
  tests/test_main_cli.py \
  tests/test_cost_calibration_smoke.py \
  tests/test_amem_adapter.py \
  tests/test_lightmem_adapter.py \
  tests/test_amem_lightmem_registry.py \
  tests/test_method_registry.py \
  tests/test_memoryos_registered_prediction.py -q
# 141 passed, 2 warnings

# 2 warnings 来源：LightMem pydantic V2 deprecation（第三方代码）
```

## 5. 已知风险与未解决问题

| 风险 | 等级 | 说明 |
|------|------|------|
| Mem0 smoke 未做真实 API 验证 | 中 | 离线测试能验证 error type/traceback logging 和 cooperative cancellation，但真实 API smoke 才能确认完整链路。建议用修正后的命令行跑一次 Mem0 2-conversation smoke。 |
| `--smoke-max-workers` 仍限制为 `{1,2}` | 低 | `run_prediction.py:708` 硬限制 `smoke_max_workers not in {1, 2}`。该限制对诊断目的合理，但未来如需 3+ worker smoke 需要改。 |
| `_patch_memoryos_registration()` mock 影响面 | 低 | 扩展到 mock efficiency getter 后，所有调用该 helper 的测试都使用 fake identity。不影响测试意图（这些测试不验证 identity 内容），但需注意。 |
| Isolated worker 中间进度仍然不更新 | 低 | `conversation_scope` 只影响 observation 收集，不影响终端进度显示。isolated worker 的 progress 仍只在每个 conversation 完成后由 coordinator 更新。 |

## 6. 命令行使用

修复后，以下三个 smoke 命令应全部正常工作：

```bash
# A-Mem smoke（1 conversation × 3 questions）
uv run memory-benchmark predict \
  --method amem --benchmark locomo --profile smoke \
  --run-id amem-api-smoke \
  --smoke-conversation-limit 1 --question-limit-per-conversation 3 \
  --confirm-api

# LightMem smoke（1 conversation × 3 questions）
uv run memory-benchmark predict \
  --method lightmem --benchmark locomo --profile smoke \
  --run-id lightmem-api-smoke \
  --smoke-conversation-limit 1 --question-limit-per-conversation 3 \
  --confirm-api

# Mem0 smoke（2 conversation × 2 worker，验证 isolated worker pipeline）
uv run memory-benchmark predict \
  --method mem0 --benchmark locomo --profile smoke \
  --run-id mem0-worker-smoke \
  --smoke-conversation-limit 2 --question-limit-per-conversation 1 \
   --confirm-api
```

---

## 附录：Smoke 下 `--question-limit-per-conversation` 不生效

### 发现

A-Mem 和 LightMem smoke 传入 `--question-limit-per-conversation 3`，但实际只回答了 1 题。

### 根因

`build_locomo_smoke_dataset()`（`locomo.py:259-302`）内部硬编码每 conversation 只保留 1 道 evidence 覆盖的题。用户传 `--question-limit-per-conversation 3` 后 dataset 仍只有 1 题，`PredictionRunPolicy.question_limit_per_conversation=3` 被 `conversation.questions[:3]`（`prediction.py:520`）静默截断为 1，无任何提示或报错。

这不是上述两个 bug 修复引入的问题，而是 smoke dataset 裁剪策略与 CLI 语义之间的既有 gap。

### 建议修复

`_question_limit_for_scope()`（`run_prediction.py:508-522`）在 smoke 下检测 `explicit_limit > 1` 时，调用 benchmark adapter 用实际可用题数重新裁剪 dataset，使 `--question-limit-per-conversation` 在 smoke 下也能真正生效。或者在 CLI 层加校验：若 smoke 下 explicit_limit > 1，抛提示告知 smoke 默认只有 1 题，需改 smoke dataset 裁剪逻辑。

### 验证

```bash
# 两个 smoke run 的 manifest 均无 question_limit_per_conversation 字段
# method_predictions.jsonl 均只有 1 题
```

---

## 附录二：LightMem memory-build observer 不生效

### 现象

`lightmem-api-smoke-v2`（200 turn）终端明确显示 OP-update 触发了 LLM 调用（LightMemory WARNING: "LLM returned invalid source_id=25" 等），但 `efficiency_observations.prediction.jsonl` 只有 3 条记录：

```
1. conversation_efficiency|                   ← 只有 latency
2. llm_call|answer              api_usage      ← answer LLM
3. question_efficiency|                        ← retrieval/answer 指标
```

OP-update 的 `manager.generate_response()` 调用全部未被记录。

### 根因

调用链：

```
offline_update_all_entries()                     [LightMem 官方]
  └─ ThreadPoolExecutor.map(update_entry, ...)   [line 627]
       └─ update_entry()
            └─ self.manager._call_update_llm()   [line 592]
                 └─ self.generate_response()      [openai.py:393] ← observer 在这里
```

observer 在 `generate_response` 被调用时检查：
```python
if collector.active_scope_type() == "conversation":
    collector.record_llm_call(...)
```

`active_scope_type()` 从 `ContextVar` 读取当前 scope。但 `executor.map()` **不传播 ContextVar** 到 worker 线程。

验证脚本（Python 3.12.8）：
```python
cv = ContextVar('test', default='NOT_SET')
cv.set('OUTSIDE')
def worker(x):
    print(f'worker sees: {cv.get()}')  # → NOT_SET
with ThreadPoolExecutor(max_workers=1) as ex:
    list(ex.map(worker, [1]))
```

`executor.map()` 内部用 C 扩展或不同上下文传递机制，不复制 ContextVar。只有 `executor.submit()` 才复制。

同样的问题也存在于 `construct_update_queue_all_entries()`（`lightmem.py:457`），它也用 `executor.map()`。

### 建议修复

**方案 A（推荐）**：将 `executor.map()` 替换为 `executor.submit()` + `future.result()`。

改动位置（均为 LightMem 官方源码）：

`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:626-627`：
```python
# 旧
with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
    executor.map(update_entry, all_entries)

# 新
with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = [executor.submit(update_entry, entry) for entry in all_entries]
    for future in futures:
        future.result()
```

`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:500-501`（`construct_update_queue_all_entries` 同理）：
```python
# 旧
with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
    executor.map(_update_queue_construction, all_entries)

# 新
with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = [executor.submit(_update_queue_construction, entry) for entry in all_entries]
    for future in futures:
        future.result()
```

**方案 B（备选）**：不修改第三方代码，在 adapter 层读完 `offline_update_all_entries` 后读取 `backend.token_stats` 中的 `update_*` 字段做 delta 计算，手动写入 observation。

方案 A 更干净，且不改变算法行为——只改变线程任务提交方式（`submit` vs `map`）。符合 AGENTS.md 中"可审计、可关闭、行为等价"的 observer 插桩原则。

### 风险评估

- `submit` + `result()` 的行为与 `map` 等价（按顺序提交、按顺序等待）
- 差别仅在 `map` 是惰性迭代器、`submit` 是显式列表。两者都对 `all_entries` 做全量处理
- 但 `update_entry` 内部写 `self.token_stats`（共享状态），`submit` 线程间仍通过 `threading.Lock` 保护，与 `map` 一致
- 需在 `offline_update_all_entries` 和 `construct_update_queue_all_entries` 两处同时修改

### 当前状态

**未修改。** 等待 Codex 审阅后决定是否执行以及用哪个方案。
