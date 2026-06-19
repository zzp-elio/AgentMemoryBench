# 2026-06-18 Token Observation 与四路 LoCoMo Smoke 交接

## 背景

用户确认当前不做统一 OpenAI-compatible API gateway。当前目标改为：每个 method 在
prediction artifact 中记录可审计 token 消耗量，后续通过离线聚合汇总 method 级成本。

本轮同时要求并行跑四个 method 的 LoCoMo 极小 smoke，并观察 Rich 终端输出。

## 本轮完成

1. A-Mem 补齐 wrapper 层 LLM token observation。
   - `amem-query-llm`：query keyword generation，stage=`retrieval`。
   - `amem-answer-llm`：固定 reader，stage=`answer`。
   - 因官方 wrapper 只返回文本，不暴露原始 response usage，当前使用
     `tokenizer_estimate`，不冒充 `api_usage`。

2. LightMem 补齐 wrapper 层 LLM token observation。
   - `lightmem-answer-llm`：固定 reader，stage=`answer`。
   - 同样使用 `tokenizer_estimate`。

3. 修复四路并行 smoke 下 LightMem 偶发 `ModuleNotFoundError`。
   - 现象：首次四路 `calibrate-smoke` 中 LightMem 失败：
     `No module named 'transformers.tokenization_utils_fast'`。
   - 证据：LightMem 单独 registered prediction smoke 能成功，说明不是模型或配置缺失。
   - 结论：外层 `ThreadPoolExecutor` 同时启动多个 third-party method 时，
     transformers / sentence-transformers lazy import 有竞态。
   - 修复：`run_cost_calibration_smoke()` 在线程池创建前串行预加载
     `transformers`、`transformers.tokenization_utils_fast`、`sentence_transformers`。

4. 四 method 并行 LoCoMo 极小 smoke 已通过。
   - 命令：

```bash
uv run memory-benchmark calibrate-smoke \
  --root . \
  --method mem0 \
  --method memoryos \
  --method amem \
  --method lightmem \
  --benchmark locomo \
  --run-prefix locomo-smoke-20260618-token-rich-v1 \
  --confirm-api \
  --resume \
  --max-parallel-runs 4
```

   - 结果：`completed_count=4`，`failed_count=0`。
   - 输出目录：
     - `outputs/locomo-smoke-20260618-token-rich-v1-mem0-locomo/`
     - `outputs/locomo-smoke-20260618-token-rich-v1-memoryos-locomo/`
     - `outputs/locomo-smoke-20260618-token-rich-v1-amem-locomo/`
     - `outputs/locomo-smoke-20260618-token-rich-v1-lightmem-locomo/`

## 本次 smoke token 摘要

基于各 run 的 `artifacts/efficiency_observations.prediction.jsonl` 聚合：

| method | LLM input | LLM output | LLM calls | embedding input | embedding calls | LLM token source |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| A-Mem | 7,066 | 12 | 2 | 0 | 0 | tokenizer_estimate |
| LightMem | 934 | 5 | 1 | 0 | 0 | tokenizer_estimate |
| Mem0 | 167,240 | 1,250 | 21 | 1,351 | 49 | api_usage |
| MemoryOS | 6,028 | 805 | 26 | 676 | 21 | api_usage |

说明：

- A-Mem / LightMem 现在记录的是 wrapper 可见 LLM 调用。若未来要精确记录其内部
  memory build LLM/embedding call，需要继续深入第三方源码做 observer 插桩，或重新
  讨论 gateway；当前用户已明确不做 gateway。
- Mem0 / MemoryOS 当前能拿到更多逐调用明细，包括 memory build、retrieval 和 answer。

## Rich 输出观察

并行 child run 时 Rich 终端输出仍不理想：

- 多个 child run 各自创建 progress/live 输出，终端会顺序或交错出现多组进度条。
- 进度条可能停在旧画面，进度条后的 elapsed 秒数不再刷新，但实验仍在后台运行。
- 第三方 warning 可能插入 progress 区域，例如 LightMem 的 pydantic deprecation warning。
- 不影响实验结果和 artifact，但用户体验不够清晰。

Root cause：

- `calibrate-smoke` 使用外层线程并发启动多个 independent child run。
- 每个 child run 内部又各自创建 `ProgressReporter` / Rich `Progress`，同时向同一个
  stdout 做 live refresh。
- Rich 的 live progress 不适合多个并发实例共享同一个终端；stdout 竞争会导致画面不
  再刷新，虽然 worker 仍在运行并持续写各自 `checkpoints/progress.json`。

建议后续修复方向：

1. `calibrate-smoke` 并行模式下禁用 child run 各自 Rich Live progress。
2. 外层 orchestrator 统一显示一张 child run 表：method、benchmark、status、elapsed、
   run_id、error。
3. child run 详细日志仍写入各自 `logs/run.log` 和 `logs/events.jsonl`。
4. 外层表格通过定时读取每个 child run 的 `checkpoints/progress.json` 更新，不从
   worker 线程直接写 Rich progress。

建议终端布局：

```text
Method     Benchmark   Status      Stage                 Conv   Q     Elapsed
Mem0       LoCoMo      completed   Completed             1/1    1/1   00:58
MemoryOS   LoCoMo      running     Answer questions      1/1    0/1   02:13
A-Mem      LoCoMo      running     Ingest conversations  0/1    0/1   01:44
LightMem   LoCoMo      failed      Ingest conversations  0/1    0/1   00:12
```

下一次实现建议：

- 给 registered prediction / prediction runner 增加“child progress disabled”路径，
  或让 `calibrate-smoke` 调用 runner 时显式传 `progress_enabled=False`。
- 在 `run_cost_calibration_smoke()` 或 CLI 层增加一个 `CalibrationProgressReporter`，
  只由主线程刷新 Rich `Live(Table)`。
- 测试用 fake runner + 临时 `progress.json` 模拟 running/completed/failed，不需要真实 API。

## Token source 解释

- `api_usage`：OpenAI-compatible API response 中直接返回的真实 usage，例如
  `prompt_tokens` / `completion_tokens`。这是最可信来源。
- `tokenizer_estimate`：API usage 不可见时，用本地 tokenizer 对 prompt 和输出文本估算。
  这是可审计估算，不等同于真实账单 usage。

当前状态：

- Mem0 / MemoryOS：adapter 能拿到原始 API response，因此 LLM token 多数是 `api_usage`。
- A-Mem：官方 `get_completion()` 对外只返回字符串，原始 response usage 被第三方
  wrapper 吃掉；当前只能记录 wrapper 可见 prompt/output，因此为 `tokenizer_estimate`。
- LightMem：当前固定 reader 也只通过 `create_answer()` 返回字符串，因此 answer token
  为 `tokenizer_estimate`。未来可优先把 `_OpenAIAnswerClient` 改成保留 usage，再升级
  LightMem answer 为 `api_usage`；内部 memory build 调用仍需第三方 observer 才能完整拿到。

## 验证

本轮离线验证：

```bash
uv run pytest tests/test_amem_adapter.py::test_amem_records_question_efficiency_observations -q
# 1 passed

uv run pytest tests/test_lightmem_adapter.py::test_lightmem_records_question_efficiency_observations -q
# 1 passed

uv run pytest tests/test_amem_adapter.py tests/test_lightmem_adapter.py -q
# 29 passed, 2 warnings

uv run pytest tests/test_cost_calibration_smoke.py -q
# 10 passed

uv run pytest tests/test_cost_calibration_smoke.py tests/test_main_cli.py tests/test_method_registry.py tests/test_config_profiles.py -q
# 50 passed

uv run python -m compileall -q \
  src/memory_benchmark/methods/amem_adapter.py \
  src/memory_benchmark/methods/lightmem_adapter.py \
  tests/test_amem_adapter.py \
  tests/test_lightmem_adapter.py
# exit 0
```

真实 API smoke：

- 首次四路 run：Mem0、MemoryOS、A-Mem completed，LightMem 因 lazy import 竞态 failed。
- LightMem 单独 debug smoke：completed。
- 修复预加载后，带 `--resume` 重跑同一 `run_prefix`：四个 child run 全部 completed。

## 下一步

1. 若继续 Phase J，优先修 Rich 并行输出；这不需要真实 API，可用 fake runner 和 PTY
   快速验证。
2. 再跑 LongMemEval-S 极小 smoke。建议先不纳入 MemoryOS；优先 Mem0、A-Mem、LightMem。
3. 后续若需要用户更易读的成本表，再基于现有 observation artifact 增加离线汇总命令，
   不重新调用 method。
