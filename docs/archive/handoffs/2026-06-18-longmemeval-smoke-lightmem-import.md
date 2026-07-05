# 2026-06-18 LongMemEval smoke 裁剪与 LightMem import 交接

## 背景

用户确认：

- 四个 method 功能上已经跑通 LoCoMo 极小 smoke；LightMem 最终是单独 run 跑通。
- LongMemEval smoke 当前只取 1 个 instance，但 instance 内仍有大量 sessions/messages，
  这会导致 smoke 成本不可控，必须修。
- smoke 裁剪不应按单 turn 硬切，应该按 round 裁剪；一个 round 是双 turn。
- LightMem LongMemEval 并发导入 `sys.path` 竞态也应修。
- 统一 API token 观测闸口是后续重要需求，但本轮不混入该 bugfix。

## 已完成修改

### LongMemEval smoke round 裁剪

修改文件：

- `src/memory_benchmark/benchmark_adapters/registry.py`
- `tests/test_benchmark_registry.py`

实现：

- 新增 `_build_longmemeval_smoke_dataset(dataset, round_limit=...)`。
- `LongMemEvalAdapter.load(limit=1)` 仍只负责读一个原始 instance。
- registry 在 `RunScope.SMOKE` 下对该 instance 内部 sessions 继续裁剪。
- 裁剪单位是完整双 turn round：每保留 1 个 round，最多保留 2 个连续 turn。
- 不保留半个 round，避免破坏 Mem0 LongMemEval 等 pair 级写入逻辑。
- metadata 新增：
  - `smoke_round_limit`
  - `smoke_original_turn_count`
  - `smoke_retained_turn_count`
  - `smoke_retained_round_count`
- 如果一个 conversation 连 1 个完整双 turn round 都没有，直接报
  `ConfigurationError`，避免静默产生无意义 smoke。

说明：

- 现有 CLI 参数名仍是 `--smoke-turn-limit`，为了不扩大改动，本轮内部把它作为
  LongMemEval 的 round budget 使用。
- 后续如果要更清晰，可以另起任务把 CLI 增加 `--smoke-round-limit`，并保留旧参数兼容。

### LightMem import 线程安全

修改文件：

- `src/memory_benchmark/methods/lightmem_adapter.py`
- `tests/test_lightmem_adapter.py`

实现：

- 新增模块级 `_LIGHTMEM_IMPORT_LOCK = threading.Lock()`。
- `import_lightmem_classes()` 在 lock 内检查并插入 LightMem vendored `src` 路径。
- 插入后在当前进程保留该路径，不再 `finally` 中移除。
- 原因：LightMem 后续可能有 lazy import；并发 child run 中反复插拔 `sys.path`
  容易造成另一个线程 import 期间路径消失。

## 验证

已执行：

```bash
uv run pytest tests/test_benchmark_registry.py::test_longmemeval_registration_prepares_full_and_smoke_datasets -q
# 1 passed

uv run pytest tests/test_lightmem_adapter.py::test_lightmem_import_keeps_vendored_src_path_for_thread_safety tests/test_lightmem_adapter.py -q
# 17 passed, 1 warning

uv run pytest tests/test_longmemeval_conversation_adapter.py tests/test_benchmark_registry.py -q
# 44 passed
```

尚未执行：

- 没有重新启动真实 API smoke。
- 没有修 Rich 终端显示问题。
- 没有实现统一 API 闸口。

## 用户新增诉求记录

用户希望后续有一个统一 API 闸口，因为当前四个 method 都用同一个 OpenAI-compatible
API。目标：

- 横跨 Mem0、MemoryOS、A-Mem、LightMem 统一记录真实 API 使用量。
- 记录每次 API call 的 input/output tokens、latency、是否失败/重试。
- 能聚合到 method 总 token、method 总运行时间。
- 最好同时带上 run_id、method、benchmark、conversation_id、question_id、stage。

当前判断：

- 短期 adapters 内 observer 已能覆盖部分 method，但 A-Mem/LightMem 仍缺逐调用明细。
- 真正统一的办法是设计一个本地 OpenAI-compatible proxy/gateway，所有 method 的
  `base_url` 指向该 proxy，再由 proxy 转发到 ohmygpt。
- 这样不用深入每个第三方 method 内部 patch client，也能统一记录所有请求和响应 usage。
- 该功能应单独设计和实现，不能和本轮 smoke bugfix 混在一起。

## 下一步建议

1. 运行 focused 回归和 `compileall`。
2. 如用户确认，启动新 run-prefix 的真实 API smoke：

```bash
uv run memory-benchmark calibrate-smoke \
  --root . \
  --method mem0 \
  --method memoryos \
  --method amem \
  --method lightmem \
  --benchmark locomo \
  --run-prefix locomo-smoke-20260618-v2 \
  --confirm-api \
  --max-parallel-runs 4
```

3. 在跑 LongMemEval smoke 前，建议只跑 Mem0/A-Mem/LightMem，MemoryOS 暂不纳入：

```bash
uv run memory-benchmark calibrate-smoke \
  --root . \
  --method mem0 \
  --method amem \
  --method lightmem \
  --benchmark longmemeval \
  --run-prefix longmemeval-smoke-20260618-v2 \
  --confirm-api \
  --max-parallel-runs 2
```

4. 单独设计统一 API gateway 和 Rich 输出修复。
