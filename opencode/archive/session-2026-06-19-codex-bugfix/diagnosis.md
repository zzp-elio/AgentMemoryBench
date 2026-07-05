# 2026-06-19 Codex 变更引入的两个 bug 诊断

## Bug 1: `allow_smoke_worker_override` 不对称

### 现象

```
uv run memory-benchmark predict --method amem --profile smoke --smoke-max-workers 1 ...
Error: A-Mem does not support --smoke-max-workers override

uv run memory-benchmark predict --method lightmem --profile smoke --smoke-max-workers 1 ...
Error: LightMem does not support --smoke-max-workers override
```

Mem0 却正常工作。

### 根因

`MethodRegistration.allow_smoke_worker_override` 只在 Mem0 注册时设为 `True`（`registry.py:565`）。A-Mem (line 517)、LightMem (line 573)、MemoryOS (line 600) 均不设，继承默认 `False`。

这是历史残留。该字段在项目首次 commit (`97e9d44`, 2026-06-17) 引入，当时只有 Mem0 一个 method，`--smoke-max-workers` 是为 Mem0 诊断并发设计的。后续三个 method 接入时漏设该字段。

四个 method 的 TOML smoke profile 都有 `max_workers=1`，official-full 都有 `max_workers=10`，结构完全相同。且 Mem0 已不再使用内置并行——所有并行都走框架层 `ThreadPoolExecutor` isolation。没有技术理由区分。

### 校验

- `registry.py:107`: `allow_smoke_worker_override: bool = False`
- `registry.py:565`: Mem0 显式设 `True`，其他三个不设
- `run_prediction.py:704`: `if not allow_override: raise`
- 所有四个 method smoke `max_workers` 都是 1

### 修复

将 A-Mem、LightMem、MemoryOS 的注册改为 `allow_smoke_worker_override=True`。

---

## Bug 2: Isolated worker `add()` 缺少 efficiency scope

### 现象

```
uv run memory-benchmark predict --method mem0 --benchmark locomo --profile smoke
  --smoke-conversation-limit 2 --question-limit-per-conversation 1
  --confirm-api
...
Error: Efficiency observation recording requires an active scope
```

### 根因

非 isolated worker 路径 (`_ingest_one`, `prediction.py:1436`) 用 `conversation_scope` 包裹 `add()`：

```python
with efficiency_collector.conversation_scope(conversation_id) as scope:
    system.add([conversation])
    efficiency_collector.record_memory_build_total_latency(...)
```

但 isolated worker (`_isolated_worker`, `prediction.py:1188`) 直接调用 `add()` 没有 scope：

```python
if work_item.needs_ingest:
    system.add([public_conversation])  # NO SCOPE!
```

后续 `question_scope` 只包裹 `get_answer()`，不回溯覆盖 `add()` 阶段。

Mem0 的 `add()` 内部调用 embedding → `EfficiencyCollector.record_embedding_call()` → `self._require_scope()` 发现无 active scope → 抛异常。

### 确认

- `prediction.py:1436`: 非 isolated 路径有 `conversation_scope`
- `prediction.py:1188-1189`: isolated 路径缺少
- `collector.py:369`: `_active_state_or_none()` 返回 None → `_require_scope()` 抛错

### 修复

在 `_isolated_worker` 中用 `conversation_scope` 包裹 `add()` 调用，与 `_ingest_one` 行为一致。
