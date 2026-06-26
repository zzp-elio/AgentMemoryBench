# 2026-06-26 Clean Retry Hooks 交接

## 本次完成

- Runner 新增可选 `clean_failed_ingest_conversation(public_conversation, failed_state)` hook。
- `failed_ingest + --retry-failed` 的行为现在分两类：
  - 没有 clean hook：继续 fail closed，避免重复写入污染记忆。
  - 有 clean hook：先清理对应 conversation 的 method state，再把 conversation 重新纳入 add + answer。
- isolated worker 失败 checkpoint 现在会写入 `worker_idx`，用于恢复时定位旧脏状态所在的
  `method_state/worker_<idx>/`。
- A-Mem、LightMem、MemoryOS 已声明 conversation 级 clean retry hook：
  - A-Mem：删除目标 conversation 的持久化 state 目录。
  - MemoryOS：删除目标 conversation 的短中长期记忆 state 目录。
  - LightMem：删除目标 conversation 的 embedding Qdrant、summary Qdrant 和日志目录。
- Mem0 暂不声明 clean hook，因为当前状态是共享 `qdrant/` 和 `history.db`，按
  conversation 删除需要更细的 namespace 清理语义；因此 Mem0 failed-ingest retry 仍
  fail closed，这是刻意的安全选择。

## 修改的核心文件

- `src/memory_benchmark/runners/prediction.py`
- `src/memory_benchmark/cli/run_prediction.py`
- `src/memory_benchmark/methods/registry.py`
- `src/memory_benchmark/methods/amem_adapter.py`
- `src/memory_benchmark/methods/lightmem_adapter.py`
- `src/memory_benchmark/methods/memoryos_adapter.py`
- `tests/test_prediction_runner.py`
- `tests/test_prediction_cli.py`
- `tests/test_method_registry.py`
- `tests/test_amem_adapter.py`
- `tests/test_lightmem_adapter.py`
- `tests/test_memoryos_adapter.py`

## 验证

已执行：

```bash
uv run pytest tests/test_prediction_runner.py tests/test_prediction_cli.py tests/test_method_registry.py tests/test_amem_adapter.py tests/test_memoryos_adapter.py tests/test_lightmem_adapter.py tests/test_mem0_adapter.py -q
```

结果：

```text
298 passed, 2 warnings, 2 subtests passed
```

未执行真实 API。

## 当前结论

- “四个内置 method clean retry hook 或 attempt namespace 证明”这项已关闭：
  A-Mem、LightMem、MemoryOS 通过 clean hook 支持；Mem0 通过安全性证明保持 fail closed。
- 不要重复实现用户轻量接入路径；`--method-class`、custom loader、unsafe parallel guard
  和 failed-ingest fail-closed 已完成。
- `BaseMemorySystem` 按用户最新决策暂时保留；不要把它纳入近期删除范围。

## 下一步建议

1. 运行最终非 API 校验：`compileall`、`git diff --check` 和文档规范测试。
2. 若通过，考虑提交本次 clean retry hooks 改动。
3. 后续主线可继续：
   - 可选 `--method-file` 单文件 method 快速测试入口。
   - legacy `BaseResumableMemorySystem`、`BaseMemoryRetriever`、历史 turn-level resume
     和过重 capability 逻辑减重。
   - 按用户确认规模推进 LongMemEval-S 后续 cost/formal 实验。
