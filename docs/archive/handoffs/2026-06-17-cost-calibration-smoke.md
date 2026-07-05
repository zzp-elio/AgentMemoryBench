# 2026-06-17 成本校准 Smoke Orchestrator 交接

## 本轮完成

- 新增设计：
  `docs/superpowers/specs/2026-06-17-cost-calibration-smoke-orchestrator-design.md`
- 新增实施计划：
  `docs/superpowers/plans/2026-06-17-cost-calibration-smoke-orchestrator.md`
- 新增外层调度模块：
  `src/memory_benchmark/runners/cost_calibration.py`
- 新增 CLI 子命令：
  `memory-benchmark calibrate-smoke`
- 普通 `predict` 新增可选参数：
  `--enable-efficiency-observability`
- 新增测试：
  `tests/test_cost_calibration_smoke.py`
- 已同步：
  `docs/current-roadmap.md`
  `AGENTS.md`

## 当前能力

`calibrate-smoke` 不是 full parallel。它只用于 OhMyGPT 成本校准：

- 多个 method × benchmark 组合生成独立 child run。
- 每个组合只跑 smoke profile。
- 每个组合固定 1 个 conversation 或 LongMemEval instance。
- smoke scope 下每个 conversation 只回答 1 个 question。
- 强制开启 efficiency observation。
- 外层 child run 并发由 `--max-parallel-runs` 控制，当前只允许 1 或 2。
- 单个 child run 失败会写入 summary，不阻塞其他 child run。
- 重新执行同一 `--run-prefix` 且保持兼容配置时，可以依赖已有 prediction resume。

## 推荐真实 API 校准命令

真实运行前需要用户再次确认 run_prefix、并发数和预算。建议初次运行：

```bash
uv run memory-benchmark calibrate-smoke \
  --method mem0 \
  --method memoryos \
  --method amem \
  --method lightmem \
  --benchmark locomo \
  --benchmark longmemeval \
  --run-prefix ohmygpt-calib-20260617 \
  --max-parallel-runs 2 \
  --confirm-api
```

如果 OhMyGPT 发生限流或网络超时，直接用同一个命令重跑；默认 `resume=True`。

## 重要注意

- 本轮没有启动真实 API。
- 本轮没有计算真实费用。
- 真实费用仍需实验完成后基于实际 provider 价格离线计算。
- 普通 `predict` 如果不传 `--enable-efficiency-observability`，不会写成本校准所需的
 完整 token/latency observation。
- `calibrate-smoke` 会强制开启 observation，因此成本校准推荐用该入口。

## 验证

已通过：

```bash
uv run pytest tests/test_cost_calibration_smoke.py tests/test_main_cli.py tests/test_documentation_standards.py -q
uv run python -m compileall -q src/memory_benchmark tests
```

结果：

```text
34 passed
compileall exit 0
```
