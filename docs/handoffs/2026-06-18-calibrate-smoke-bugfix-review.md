# 2026-06-18 calibrate-smoke bugfix 复核交接

## 背景

用户运行 LoCoMo 成本校准 smoke：

```bash
uv run memory-benchmark calibrate-smoke \
  --root . \
  --method mem0 \
  --method memoryos \
  --method amem \
  --method lightmem \
  --benchmark locomo \
  --run-prefix locomo-smoke-20260618 \
  --confirm-api \
  --max-parallel-runs 4
```

最初 4 个 child run 全失败：

- Mem0: `Cannot resume because manifest is missing`
- MemoryOS / A-Mem / LightMem: `Method manifest contains a secret-like field: $.llm_tokenizer`

随后用户让 OpenCode + DeepSeekV4Pro 修改并记录到
`docs/opencode-suggestions/2026-06-18-calibrate-smoke-bugfix.md`。

## 已核验结论

1. `llm_tokenizer` 报 secret 是真实 bug。
   原因是 public manifest 检查把任意包含 `token` 的字段都当成 secret，误伤
   `llm_tokenizer` / `embedding_tokenizer`。

2. calibrate-smoke 默认 resume 语义确实导致首次运行不友好。
   dataclass 默认值和 argparse 默认值必须同时处理；OpenCode 找到 argparse
   `default=True` 覆盖 dataclass 默认值的分析是正确的。

3. 直接删除 `"token"` 禁止片段不够严谨。
   当前修复改成继续拒绝 `token`、`api_token`、`access_token`、`auth_token`、
   `bearer_token`、`id_token`、`refresh_token` 和 `*_token` / `*-token`，
   但允许 `llm_tokenizer`、`embedding_tokenizer`、`input_tokens`、
   `output_tokens` 等安全技术字段。

4. calibrate-smoke 现在默认 `resume=False`，并新增显式 `--resume`。
   这保留了首次 smoke 可直接创建 run 的行为，也保留后续用户想复用同 run_id
   继续跑时的入口。`--resume` 和 `--no-resume` 是 argparse mutually exclusive group。

5. LightMem LoCoMo 时间格式转换是合理的。
   LoCoMo 原始时间如 `1:56 pm on 8 May, 2023`，LightMem normalizer 需要
   `YYYY/MM/DD (Dow) HH:MM` 或 ISO；adapter 当前把 LoCoMo 时间转成
   `2023/05/08 (Mon) 13:56`。

6. LightMem `llmlingua` / `transformers` 依赖是合理补充。
   当前环境解析为 `transformers 5.9.0`、`llmlingua 0.2.2`、`torch 2.12.0`。
   LightMem 官方 `pyproject.toml` pinned `transformers==4.57.0`，但本项目当前
   `sentence-transformers 5.5.1` 与依赖解析使用 5.9.0。为兼容该环境，adapter
   注入 `model_config={"attn_implementation": "eager"}`，第三方 LightMem
   `LlmLingua2Compressor` 只增加 `model_config` 透传到 `PromptCompressor`。
   这属于配置透传，不改变核心算法步骤。

## 实际文件证据

当前同前缀 `outputs/locomo-smoke-20260618-*` 只有三个已完成 child run：

- `outputs/locomo-smoke-20260618-mem0-locomo`
- `outputs/locomo-smoke-20260618-memoryos-locomo`
- `outputs/locomo-smoke-20260618-amem-locomo`

LightMem 成功证据位于单独 run：

- `outputs/locomo-lightmem-smoke-obs`

该目录有完整 `manifest.json`、`method_predictions.jsonl`、`efficiency_observations.prediction.jsonl`
和 `summaries/summary.json`，summary 显示 1 conversation / 1 question completed。

因此，当前可确认：

- Mem0 / MemoryOS / A-Mem 已在同一个 `locomo-smoke-20260618-*` 前缀下完成。
- LightMem 已单独完成 LoCoMo 1 conversation / 1 question smoke。
- “四个 method 在同一个 calibrate-smoke 前缀下一次性 4/4 completed”还没有重新运行验证。

## 本轮代码修正

- `src/memory_benchmark/cli/main.py`
  - `calibrate-smoke` 新增 `--resume`，保留 `--no-resume`，默认 `resume=False`。
  - `--max-parallel-runs` 保持支持 `{1,2,4}`。
- `src/memory_benchmark/runners/cost_calibration.py`
  - `CalibrationSmokeCommand.resume=False`。
  - `max_parallel_runs` 强校验 `{1,2,4}`。
- `src/memory_benchmark/runners/prediction.py`
  - public manifest secret 检查允许 tokenizer/tokens 字段，继续拒绝真实 token 字段。
- `src/memory_benchmark/methods/lightmem_adapter.py`
  - 修正 `llmlingua_config` 缩进。
  - 注入 `attn_implementation=eager`。
  - 增加 LoCoMo 时间格式转换。
- `third_party/methods/LightMem/src/lightmem/factory/pre_compressor/llmlingua_2.py`
  - 增加 `model_config` 透传到 `PromptCompressor`。
- `pyproject.toml` / `uv.lock`
  - 增加 `llmlingua` 和 `transformers`。
- 测试：
  - `tests/test_main_cli.py` 增加 `calibrate-smoke --resume` 解析测试。
  - `tests/test_prediction_runner.py` 增加 tokenizer/tokens 安全字段和真实 token 字段拒绝测试。

## 验证

未由本轮 Codex 重新启动真实 API calibrate-smoke。

已运行离线验证：

```bash
uv run pytest tests/test_main_cli.py::test_main_maps_calibration_smoke_arguments_to_command \
  tests/test_main_cli.py::test_main_maps_calibration_smoke_resume_flag_to_command \
  tests/test_cost_calibration_smoke.py \
  tests/test_prediction_runner.py::test_public_manifest_allows_tokenizer_and_token_count_fields \
  tests/test_prediction_runner.py::test_public_manifest_rejects_real_token_fields \
  tests/test_lightmem_adapter.py -q
# 33 passed, 1 warning

uv run pytest tests/test_cost_calibration_smoke.py tests/test_main_cli.py \
  tests/test_prediction_runner.py tests/test_lightmem_adapter.py \
  tests/test_documentation_standards.py -q
# 83 passed, 1 warning

uv run python -m compileall -q src/memory_benchmark tests
# exit 0

git diff --check
# exit 0

uv run memory-benchmark calibrate-smoke --help
# shows [--resume | --no-resume] and --max-parallel-runs {1,2,4}
```

## 待办和风险

1. 下一次如需验证四路并发 LoCoMo calibrate smoke，建议使用新的 run-prefix，
   避免与已经存在的 `locomo-smoke-20260618-*` 目录发生不可变 manifest 冲突。

2. 如果要接着复用已有同前缀三条完成 run，必须显式传 `--resume`，但 LightMem
   缺同前缀 manifest，会失败。因此要么用新前缀重跑四路，要么单独补 LightMem
   对应 run_id。

3. OpenCode 发现 LongMemEval smoke 只限制 instance 数，不限制 instance 内 turns。
   该发现基本成立，但本轮未修。下一步若跑 LongMemEval smoke，应先实现
   LongMemEval smoke turn/session 裁剪。

4. OpenCode 推断 LightMem LongMemEval 并发导入存在 `sys.path` 竞态；当前证据只显示
   `ModuleNotFoundError`，没有具体模块名，尚未完成根因确认。本轮不修。

5. A-Mem 和 LightMem 仍只有 conversation/question 汇总级 efficiency observation，
   没有像 Mem0/MemoryOS 那样的逐 LLM/embedding call 观测。若后续要精确估算成本，
   需要继续做 observer hook。
