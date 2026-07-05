# Cost Calibration Smoke Orchestrator 设计

## 背景

当前框架已经具备单个 prediction run 内部的 conversation 级并行能力，也能在启用
efficiency observation 时记录 LLM token、embedding token、latency 和模型清单。缺口是
外层实验矩阵调度：我们还不能一次性启动多个 method × benchmark 的极小 smoke run，
也不能用统一入口挑战多个独立 run 的 resume、失败隔离和并发上限。

本设计只服务成本校准，不是 full parallel。它的目标是用极小样本真实调用 API，校准
本框架记录的 token 与 OhMyGPT 后台账单之间的差距。

## 目标

- 支持 `Mem0`、`MemoryOS`、`A-Mem`、`LightMem` 在 `LoCoMo` 和 `LongMemEval-S`
  上各跑一个极小 prediction smoke。
- 每个 method × benchmark 组合生成独立 run_id 和独立 `outputs/<run_id>/`。
- 每个 run 使用 smoke profile、1 个 conversation 或 LongMemEval instance、每个
  conversation 只答 1 个 question。
- 强制开启 Phase G efficiency observation，避免跑出无法估算成本的 prediction artifact。
- 全局最多同时运行 2 个 child run，避免 API 网关过载。
- 单个 child run 失败时记录失败，不阻塞其他 child run；重新执行同一个 run_prefix 时
  可以靠现有 runner resume。

## 非目标

- 不运行 full-scale experiment。
- 不计算真实费用；费用仍由后续 analysis 层根据 OhMyGPT 实际价格离线计算。
- 不实现通用集群调度、进程池隔离或远程任务队列。
- 不改变 method 官方参数；成本控制只通过 smoke 数据规模裁剪。
- 不合并 LongMemEval-S/M，也不把多个 variant 合成一个 run。

## 方案

新增一个轻量的成本校准调度层：

```text
CalibrationSmokeCommand
  -> build child task list(method × benchmark)
  -> ThreadPoolExecutor(max_workers=max_parallel_runs)
  -> run_registered_conversation_qa_prediction(..., enable_efficiency_observability=True)
  -> CalibrationSmokeSummary
```

该调度层复用现有 registered conversation-QA prediction service，不新增
`<method>_<benchmark>_full.py`。每个 child task 使用稳定 base run_id：

```text
<run_prefix>-<method>-<benchmark>
```

如果 benchmark registry 本身有多个 variant，现有 prediction service 会继续追加
variant suffix，例如 LongMemEval 默认 `s_cleaned` 会落到：

```text
<run_prefix>-mem0-longmemeval-s-cleaned
```

## 并行边界

本设计包含两层并行：

- 外层并行：多个 method × benchmark child run 同时执行，由
  `max_parallel_runs` 控制，当前上限为 2。
- 内层并行：单个 prediction run 内部的 conversation worker 只使用 method smoke
  profile 默认值。成本校准入口不暴露内层 worker override，避免混合 method 矩阵中某些
  method 不支持 override 而失败，也避免嵌套并发难以排查。

这不是 Phase I full parallel。Phase I 仍会继续处理 method execution policy、
MemoryOS 进程隔离和更大规模的并发策略。

## 错误处理

- `run_prefix` 不能为空，不能包含路径分隔符。
- `methods` 和 `benchmarks` 不能为空。
- `max_parallel_runs` 当前只允许 1 或 2。
- 每个 child run 捕获异常并写入 summary；其他 child run 继续执行。
- 失败 summary 保留 method、benchmark、base run_id、错误类型和错误消息。
- 真实 API 成本确认仍由每个 child 调用的 prediction service 执行。

## CLI 与 Python API

Python API 是核心入口，CLI 是薄封装：

```python
run_cost_calibration_smoke(command)
```

CLI 子命令：

```bash
memory-benchmark calibrate-smoke \
  --method mem0 --method memoryos --method amem --method lightmem \
  --benchmark locomo --benchmark longmemeval \
  --run-prefix ohmygpt-calib-20260617 \
  --max-parallel-runs 2 \
  --confirm-api \
  --resume
```

此外，普通 `predict` 命令增加可选
`--enable-efficiency-observability`，便于单 run 调试；成本校准入口则强制开启，不需要用户手动指定。

## 验证

- 不触网单元测试覆盖 child task 参数、run_id、强制 efficiency observation、并发上限和失败隔离。
- CLI 单元测试覆盖参数解析和 command service 转发。
- focused tests 后运行 `compileall`。
