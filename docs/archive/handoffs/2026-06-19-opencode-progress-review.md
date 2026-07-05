# 2026-06-19 OpenCode 推进结果审查交接

## 背景

用户已重新定义 OpenCode 的定位：OpenCode 将在 Codex 额度空窗期正式持续推进项目。
OpenCode 的推进记录写在 `opencode/opencode_result.md`。Codex 恢复后必须先读取该文件、
核对实际代码 diff 和测试证据，再决定哪些结论可以进入主线。

本次审查的 `opencode/opencode_result.md` 共 1443 行，已完整读取。下面只记录经过 Codex
核对后的状态，不直接采信 OpenCode 自称完成的内容。

## OpenCode 声称完成的主要内容

1. `calibrate-smoke` 并行模式的统一 Rich 表格进度：
   - 新增 `src/memory_benchmark/runners/calibration_progress.py`。
   - `cost_calibration.py` 在 `max_parallel_runs > 1` 时禁用 child run Rich progress，
     由外层轮询各 run 的 `checkpoints/progress.json`。
   - `run_prediction.py` 新增 `progress_enabled` 透传。
2. conversation-level 并行原型：
   - `prediction.py` 新增 `_split_into_chunks()`、`_run_isolated_worker_pipeline()`、
     `_isolated_worker()`。
   - `MethodRegistration` 新增 `supports_shared_instance_parallelism`。
   - 非共享实例 method 可在 worker 内构造独立 method instance。
3. MemoryOS 并行导入竞态修复：
   - `memoryos_adapter.py` 增加 `_MEMORYOS_EVAL_IMPORT_LOCK`，保护官方 eval 模块导入。
4. MemoryOS 论文参数对齐：
   - `configs/methods/memoryos.toml` 保持 STC=7、MTC=200。
   - `memoryos_adapter.py` heat alpha/beta/gamma 保持 1.0/1.0/1.0。
5. 发现但未解决的问题：
   - Rich 真实终端显示仍可能冻结或被第三方 warning 打断。
   - isolated worker 并行不支持 conversation-level resume。
   - MemoryOS stdout 泄漏。
   - MemoryOS `method_predictions.jsonl` 每题重复保存大段 `metadata.system_prompt`。
   - LoCoMo F1 evaluator 没有自动输出 category summary。

## Codex 实际核验

实际文件检查确认 OpenCode 提到的核心文件和符号存在：

- `src/memory_benchmark/runners/calibration_progress.py`
- `tests/test_calibration_progress_monitor.py`
- `src/memory_benchmark/runners/prediction.py` 中的 isolated worker 相关函数
- `src/memory_benchmark/methods/registry.py` 中的 `supports_shared_instance_parallelism`
- `src/memory_benchmark/methods/memoryos_adapter.py` 中的 `_MEMORYOS_EVAL_IMPORT_LOCK`

第一次运行 focused tests 时，OpenCode 新增的 `tests/test_calibration_progress_monitor.py`
有 4 个失败。根因不是业务逻辑，而是测试 helper 使用
`Console(..., force_terminal=True)`，当前 Rich 在该模式下把宽度回退到 80 列，导致表格
文本被截断。Codex 已做最小修复：测试 helper 改为 `force_terminal=False` 并保留足够宽度。

已通过的离线验证：

```bash
uv run pytest tests/test_calibration_progress_monitor.py tests/test_cost_calibration_smoke.py -q
# 20 passed

uv run pytest tests/test_prediction_runner.py tests/test_config_profiles.py tests/test_method_registry.py -q
# 56 passed

uv run pytest tests/test_memoryos_adapter.py -q
# 131 passed, 2 subtests passed

uv run python -m compileall -q src/memory_benchmark tests
# exit 0

git diff --check
# exit 0
```

注意：上述验证均为离线验证，未执行真实 API。

## 不能标记完成的内容

1. isolated worker 并行不能用于 official/full 长实验。

   证据：`_run_isolated_worker_pipeline()` 创建 `MethodBuildContext` 时
   `completed_conversations=()` 写死，没有读取 `conversation_status` 或跳过已完成
   conversation。它只证明“独立实例并行处理 conversation chunk”的雏形存在，不满足用户
   要求的 conversation-level resume。

2. Rich 终端显示问题不能标记完成。

   `CalibrationProgressMonitor` 的离线逻辑测试已经通过，但 OpenCode 真实运行仍观察到：
   elapsed 停住、第三方 warning 插入进度区、isolated prediction 进度长时间不动。
   后续需要在真实终端自测，不要只看单元测试。

3. OpenCode 修改 official-full `max_workers=10` 不能直接作为默认 full 实验策略。

   这需要先完成 resume、请求并发上限、失败恢复和 API 成本控制。当前只可作为待审配置，
   不得未经用户确认启动 official/full。

4. MemoryOS-LoCoMo category summary 和 system prompt 去重只是发现，不是已修。

   后续应分别进入 evaluator artifact 改造和 MemoryOS metadata 瘦身任务。

## 文档同步

本次已更新：

- `AGENTS.md`
  - 记录 OpenCode 已成为正式外部推进通道。
  - 记录恢复时必须审查 `opencode/opencode_result.md`、diff 和测试。
  - 记录 isolated worker 的 resume 缺口、Rich 真实终端显示未完成、MemoryOS 待办。
- `docs/current-roadmap.md`
  - Phase I 增加 isolated worker 原型验收和 resume 待办。
  - Phase J 标记 `CalibrationProgressMonitor` 离线逻辑已通过，但真实终端体验仍待修。
  - 增加 MemoryOS stdout、system prompt 去重、LoCoMo category summary 待办。
- `docs/subagent-strategy.md`
  - OpenCode 从“默认禁用”改为“用户启用的正式外部推进通道”。
  - 明确 OpenCode 结果必须由 Codex 核验。

## 下一步建议

1. 先修 isolated worker 的 conversation-level resume，否则不要用它跑 official/full。
2. 再修真实终端进度显示：需要对 `calibrate-smoke` 和 isolated prediction 分别自测。
3. 处理 MemoryOS stdout 泄漏，避免第三方输出破坏 Rich Live。
4. 增加 LoCoMo F1 category summary artifact，避免每次手动聚合。
5. 评估 MemoryOS prediction metadata，去掉每题重复的大段 `system_prompt`。

## 当前风险提示

OpenCode 已经可以推进项目，但其报告中存在“测试通过”与实际 pytest 结果不一致的情况。
后续所有 OpenCode 结果仍必须按候选变更处理：先读 result，再看 diff，再跑测试，最后
才更新主线状态。
