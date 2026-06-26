# 2026-06-23 CLI v2 与输出布局交接

## 本轮完成

- 新增推荐 CLI：
  - `memory-benchmark predict smoke ...`
  - `memory-benchmark predict formal ...`
- `predict smoke` 语义：
  - 使用 `--conversations`、`--rounds`、`--questions-per-conversation`、`--workers`。
  - 不支持 `--resume`、`--retry-failed`、`--conversation-budget`。
  - `--rounds N` 在 LoCoMo 内部转换为 `2N` turns；LongMemEval 继续按完整 user+assistant round 裁剪。
- `predict formal` 语义：
  - 使用 `--conversation-budget`、`--workers`、`--resume`、`--retry-failed`。
  - 不支持 `--rounds`、`--conversations`、`--questions-per-conversation`。
  - `--retry-failed` 必须和 `--resume` 一起使用。
- `--allow-api` 已作为 `--confirm-api` 别名接入。
- `evaluate --workers` 已作为 `--max-eval-workers` 别名接入。
- CLI v2 新 run 输出到：

```text
outputs/runs/{method}/{benchmark}/{variant?}/{smoke|formal}/{run_id}/
```

- legacy `predict --profile ...` 仍输出到 `outputs/{run_id}/`，用于兼容旧脚本和历史实验。
- `evaluate --run-id` 现在兼容新旧布局：
  - 只在 legacy 或 v2 中找到一个匹配时正常读取。
  - 同名 run 同时存在 legacy 和 v2，或 v2 中多处同名时，报 `ambiguous`，避免静默选错。
- LoCoMo smoke 现在允许历史过短时继续做连通性测试，并在 public metadata 中标记
  `smoke_context_truncated=True`；不再因为缺完整 evidence 直接拒绝 smoke。
- 超过真实数据量的 `--conversations` 会取 min，不再因请求数大于实际数失败。

## 主要改动文件

- `src/memory_benchmark/cli/main.py`
- `src/memory_benchmark/cli/commands.py`
- `src/memory_benchmark/cli/run_prediction.py`
- `src/memory_benchmark/benchmark_adapters/locomo.py`
- `tests/test_main_cli.py`
- `tests/test_prediction_cli.py`
- `README.md`
- `AGENTS.md`
- `docs/current-roadmap.md`
- `docs/task-ledger.md`
- `docs/superpowers/specs/2026-06-23-cli-v2-output-layout-design.md`

## 已验证

```bash
uv run memory-benchmark predict --help
uv run memory-benchmark evaluate --help
uv run pytest tests/test_main_cli.py tests/test_prediction_cli.py tests/test_documentation_standards.py -q
uv run python -m compileall -q src/memory_benchmark tests
git diff --check
```

结果：

- CLI help 正常输出。
- `tests/test_main_cli.py tests/test_prediction_cli.py tests/test_documentation_standards.py` 为 `69 passed`。
- `compileall` 通过。
- `git diff --check` 通过。

## 后续建议

- 真实 API smoke 以后优先使用新命令，例如：

```bash
uv run memory-benchmark predict smoke \
  --method mem0 \
  --benchmark locomo \
  --run-id 20260623-mem0-locomo-smoke \
  --allow-api \
  --conversations 2 \
  --rounds 20 \
  --questions-per-conversation 1 \
  --workers 2
```

- 不急着删除 legacy `--profile` 参数；等当前实验和文档全部迁移到 v2 后，再单独做 deprecated 参数清理。

## Legacy CLI 清理决策

- 当前继续支持旧写法：
  - `memory-benchmark predict --profile smoke ...`
  - `memory-benchmark predict --profile official-full ...`
  - 以及旧参数 `--confirm-api`、`--confirm-full`、`--smoke-turn-limit`、
    `--smoke-conversation-limit`、`--smoke-max-workers`、
    `--question-limit-per-conversation`、`--max-new-conversations`。
- 不在当前阶段删除旧参数，原因是已有实验脚本、handoff 和历史 outputs 仍依赖旧布局。
- 分阶段清理：
  1. 四个内置 method 的 LoCoMo/LongMemEval 新 CLI smoke 稳定后，给旧写法加
     deprecated warning。
  2. 至少完成一次 v2 formal 小规模 run 后，从 README 和新手示例里移除旧写法。
  3. 保留兼容测试，直到确认历史 run 复查和内部脚本不再依赖旧参数。
  4. 对外发布前，再决定是否彻底删除旧参数。
