# OpenCode 执行记录 — 2026-06-18

## 任务概述

修复 `memory-benchmark calibrate-smoke` 并行模式下 Rich 终端输出混乱问题，同时为 A-Mem/LightMem 补齐 API usage 级别的 token 观测提供方向。

用户确认：
- 终端显示问题的根因是每个 child run 各自创建一个 Rich Progress/Live，多个实例争抢同一个 stdout
- codex 已给出修复方向：并行模式下禁用 child run 的 Rich Live progress，由外层 orchestrator 主线程统一读取 `checkpoints/progress.json` 并展示一张 `Live(Table)`

当前阶段：
- 只实施 Rich 并行输出修复
- A-Mem/LightMem API usage 插桩方案已分析但留待后续实施

---

## 回答用户的技术问题

### `tokenizer_estimate` vs `api_usage` 的含义

- **`api_usage`**（枚举定义：`MeasurementSource.API_USAGE`，位置 `src/memory_benchmark/observability/efficiency/entities.py:29`）：
  数据来自 OpenAI API response 的 `usage.prompt_tokens` / `usage.completion_tokens`。这是 OpenAI 服务端实际计费的真实 token 数，也是实际计费依据。只有拿到完整 OpenAI response object（如 Mem0 的 `openai` Python SDK 返回值，MemoryOS 的源码 access）的情况下才能记录。

- **`tokenizer_estimate`**（枚举定义：`MeasurementSource.TOKENIZER_ESTIMATE`，位置 `src/memory_benchmark/observability/efficiency/entities.py:32`）：
  用本地 HuggingFace/tiktoken tokenizer 对文本做 `encode()` 计算 token 数。这是本地估算，可能与 OpenAI 真实 tokenizer 有微小偏差（通常 <5%），但成本核算时足够参考。当第三方 wrapper 只返回文本字符串、不暴露原始 OpenAI response 时使用。

- **区别**：`api_usage` 是发票上的数，`tokenizer_estimate` 是凭秤约的数。A-Mem/LightMem 的 wrapper 只返回文本，当前标注 `tokenizer_estimate` 是正确的，没有伪造 `api_usage`。

- **分辨逻辑**：`resolve_token_usage()`（`src/memory_benchmark/observability/efficiency/token_counting.py:31`）优先采用完整 API usage；若 `api_input_tokens` 与 `api_output_tokens` 都非 None 则标记 `API_USAGE`，否则回退到 tokenizer 并标记 `TOKENIZER_ESTIMATE`。

- **A-Mem/LightMem 现状**：两个 adapter 都调用 `resolve_token_usage(api_input_tokens=None, api_output_tokens=None, ...)`，因此强制走 `TOKENIZER_ESTIMATE`。

---

## Rich 并行输出修复 — 详细实施方案

### 问题根因

- `cost_calibration.py:156` 使用 `ThreadPoolExecutor` 并行派发 child run
- 每个 child run 在 `prediction.py:213` 创建 `ProgressReporter`，内部创建 Rich `Progress` 对象（`progress_reporter.py:77`）
- 多个 `Progress`/`Live` 同时往同一个 stdout 输出，Rich 的 live refresh 不支持多实例共享终端
- 现象：进度条交错、elapsed 秒数卡住、第三方 warning 插入进度区

### 修复原则

- `max_parallel_runs > 1` 时：禁用 child run 各自 Rich Live progress，由 orchestrator 主线程统一展示
- `max_parallel_runs == 1` 时：保持 child run 原有 Rich 进度条不变
- 不做 API gateway，不修改第三方核心算法

### 架构图

```
calibrate-smoke 并行模式 (max_parallel_runs > 1)：
  ┌──────────────────────────────────────────────┐
  │  orchestrator 主线程                          │
  │  ┌──────────────────────────────────────────┐ │
  │  │  CalibrationProgressMonitor              │ │
  │  │  Rich Live(Table) 统一展示               │ │
  │  │  Method  Benchmark  Status  Stage        │ │
  │  │  Conv/Q  Elapsed  Run_ID  Error   │ │
  │  └──────────────────────────────────────────┘ │
  │         ↑ 每 0.5s poll progress.json          │
  ├──────────────────────────────────────────────┤
  │  ThreadPoolExecutor (child runs)              │
  │  ┌────────┐ ┌────────┐ ┌────────┐           │
  │  │ Mem0   │ │ MemOS  │ │ A-Mem  │ ...       │
  │  │Rich=OFF│ │Rich=OFF│ │Rich=OFF│           │
  │  │→progress│→progress│→progress│           │
  │  │ .json  │ │ .json  │ │ .json  │           │
  │  └────────┘ └────────┘ └────────┘            │
  └──────────────────────────────────────────────┘
```

---

## 详细修改清单

### 修改 1：`run_registered_conversation_qa_prediction()` 增加 `progress_enabled` 参数

**文件**：`src/memory_benchmark/cli/run_prediction.py`

**变更**：

- **行 168-169（函数签名）**：新增参数 `progress_enabled: bool = True`
  ```python
  # 旧：无此参数
  # 新：
  progress_enabled: bool = True,
  ```

- **行 187-188（docstring）**：新增参数说明
  ```python
  # 新增一行：
  progress_enabled: 是否在终端渲染 Rich 进度条；并行校准模式下应关闭。
  ```

- **行 276（PredictionRunPolicy 构造）**：传入 `progress_enabled`
  ```python
  # 旧：
  policy = PredictionRunPolicy(
      max_workers=max_workers,
      question_limit_per_conversation=_question_limit_for_scope(run_scope),
      resume=resume,
  )
  # 新：
  policy = PredictionRunPolicy(
      max_workers=max_workers,
      question_limit_per_conversation=_question_limit_for_scope(run_scope),
      resume=resume,
      progress_enabled=progress_enabled,
  )
  ```

**说明**：`PredictionRunPolicy.progress_enabled` 字段已存在（`prediction.py:65`），只是之前没有从外层传递。`progress_enabled` 最终在 `prediction.py:213-215` 传给 `ProgressReporter` 的 `enabled` 参数，控制 Rich Progress 是否启动。

---

### 修改 2：创建 `CalibrationProgressMonitor`

**文件**：`src/memory_benchmark/runners/calibration_progress.py`（新建）

**完整内容**：约 210 行

**核心类**：`CalibrationProgressMonitor`

**构造函数参数**：
- `output_root`: outputs 根目录
- `run_ids`: child run 的 run_id 元组
- `methods`: 对应的 method 名称元组
- `benchmarks`: 对应的 benchmark 名称元组
- `refresh_per_second`: Rich Live 刷新频率，默认 4.0
- `console`: 可选 Rich Console（测试时可替换为无终端 Console）
- `clock`: 可注入单调时钟（测试用）

**关键方法**：

1. `start()` — 创建 `Live(Table, ...)`，调用 `live.start()`
2. `stop()` — 刷新最终表格，调用 `live.stop()`，确保 `_live = None`
3. `start_task(run_id)` — 记录 child run 开始时间为 `_clock()`，用于计算 elapsed
4. `mark_completed(run_id)` / `mark_failed(run_id, error)` — 刷新表格
5. `_build_snapshot_table()` — 核心方法：
   - 创建 Rich `Table`，9 列：Method, Benchmark, Status, Stage, Conv, Q, Elapsed, Run ID, Error
   - 每行读取对应的 `outputs/<run_id>/checkpoints/progress.json`
   - Status 列带 Rich 颜色标记：completed=green, failed=red, running=yellow, pending=无色
   - 注意：status_style 为空字符串时不用 Rich markup 标签（避免 `[]pending[/]` 语法错误）
6. `_read_progress(run_id)` — 读取 `output_root/<run_id>/checkpoints/progress.json`，文件不存在或 JSON 损坏时返回 `{}`
7. `_derive_status(progress)` — 根据 stage 和 question 进度推断状态
8. `_format_elapsed(run_id)` — 格式化 `MM:SS`

**Rich 转义处理**：
```python
# status_style 为空时不生成 markup 标签
status_cell = (
    f"[{status_style}]{status}[/{status_style}]"
    if status_style
    else status
)
```

---

### 修改 3：`cost_calibration.py` 集成进度监控

**文件**：`src/memory_benchmark/runners/cost_calibration.py`

**变更详情**：

1. **行 12（新增导入）**：
   ```python
   # 旧：from concurrent.futures import Future, ThreadPoolExecutor, as_completed
   # 新：from concurrent.futures import Future, ThreadPoolExecutor, as_completed, wait
   #                                                                    ^^^^^
   ```

2. **行 19-20（新增导入）**：
   ```python
   # 新增：
   from memory_benchmark.runners.calibration_progress import (
       CalibrationProgressMonitor,
   )
   ```

3. **行 155-176（`run_cost_calibration_smoke` 主循环重构）**：
   ```python
   # 旧：
   with ThreadPoolExecutor(max_workers=command.max_parallel_runs) as executor:
       futures: dict[...] = {
           executor.submit(_run_one_task, task, command, prediction_runner): task
           for task in tasks
       }
       for future in as_completed(futures):
           results.extend(future.result())

   # 新：
   progress_enabled_child = command.max_parallel_runs <= 1
   with ThreadPoolExecutor(max_workers=command.max_parallel_runs) as executor:
       child_futures: dict[Future[...], float] = {}
       for task in tasks:
           future = executor.submit(
               _run_one_task,
               task,
               command,
               prediction_runner,
               progress_enabled_child,       # 新增：并行时传 False
           )
           child_futures[future] = _clock()

       if command.max_parallel_runs > 1:
           _run_with_progress_monitor(
               futures=child_futures,
               command=command,
               tasks=tasks,
               results=results,
           )
       else:
           for future in as_completed(child_futures):
               results.extend(future.result())
   ```

4. **行 248-252（`_run_one_task` 函数签名）**：新增 `progress_enabled: bool = True`
   ```python
   # 旧：def _run_one_task(task, command, prediction_runner)
   # 新：def _run_one_task(task, command, prediction_runner, progress_enabled: bool = True)
   ```

5. **行 265（`_run_one_task` 内部传递）**：新增 `progress_enabled=progress_enabled` 到 `prediction_runner(**kwargs)`

6. **行 304-355（新增 `_run_with_progress_monitor` 函数）**：
   ```python
   def _run_with_progress_monitor(*, futures, command, tasks, results):
       """在并行模式下用统一进度监控表收集 child run 结果。"""
       run_ids = tuple(task.base_run_id for task in tasks)
       methods = tuple(task.method for task in tasks)
       benchmarks = tuple(task.benchmark for task in tasks)
       monitor = CalibrationProgressMonitor(
           output_root=Path(command.project_root) / "outputs",
           run_ids=run_ids,
           methods=methods,
           benchmarks=benchmarks,
       )
       monitor.start()
       try:
           for run_id, task in zip(run_ids, tasks, strict=True):
               monitor.start_task(run_id)
           pending = set(futures.keys())
           while pending:
               done, pending = wait(pending, timeout=0.5)
               for future in done:
                   run_results = future.result()
                   results.extend(run_results)
                   for run_result in run_results:
                       if run_result.status == "completed":
                           monitor.mark_completed(run_result.run_id)
                       else:
                           monitor.mark_failed(
                               run_result.run_id,
                               run_result.error or "unknown",
                           )
               monitor._refresh_table()
       finally:
           monitor.stop()
   ```

**关键设计决策**：
- 使用 `concurrent.futures.wait(pending, timeout=0.5)` 替代 `as_completed`，每 0.5 秒轮询一次
- 每轮都调用 `monitor._refresh_table()` 刷新 Live 表格
- `monitor.stop()` 在 finally 块中确保资源释放

7. **行 357-361（新增 `_clock` 辅助函数）**：
   ```python
   def _clock() -> float:
       import time as _time
       return _time.monotonic()
   ```

---

### 修改 4：测试文件

#### 4a. `tests/test_cost_calibration_smoke.py`

**新增测试 1**：`test_calibration_disables_child_progress_when_parallel`（行 97）
- 验证：`max_parallel_runs=2` 时，每个 child run 收到 `progress_enabled=False`
- 使用 fake runner，记录传递参数

**新增测试 2**：`test_calibration_keeps_child_progress_when_sequential`（行 126）
- 验证：`max_parallel_runs=1` 时，child run 收到 `progress_enabled=True`
- 确保单 worker 模式不受影响

#### 4b. `tests/test_calibration_progress_monitor.py`（新建）

**9 个测试**：

| 测试名称 | 验证内容 |
|---------|---------|
| `test_monitor_builds_table_with_pending_runs` | 无 progress.json 时显示 pending 状态 |
| `test_monitor_detects_running_when_progress_has_stage` | 有 stage 但未完成时显示 running |
| `test_monitor_detects_completed_when_stage_is_completed` | stage=Completed + question 全完成时显示 completed |
| `test_monitor_formats_elapsed_from_task_start` | elapsed 从 `start_task` 算起 |
| `test_monitor_rejects_mismatched_lengths` | run_ids/methods/benchmarks 长度不一致时抛 ValueError |
| `test_monitor_reads_progress_inside_subdirectories` | 从 `outputs/<run_id>/checkpoints/progress.json` 读取 |
| `test_monitor_handles_missing_progress_file` | 缺失文件返回空 dict |
| `test_monitor_start_and_stop_lifecycle` | start/stop 不抛异常 |
| `test_monitor_builds_table_with_pending_runs` | pending 状态验证 |

**辅助工具**：
- `_write_progress()` — 写入临时 progress.json
- `_FakeClock` — 单调递增假时钟（每次 +1s），带完整中文 docstring
- `_render_table()` — 用 Rich Console 把 Table 渲染为文本字符串

---

### 修改 5：文档规范修正

**文件**：`tests/test_cost_calibration_smoke.py`

- `test_calibration_disables_child_progress_when_parallel` 内嵌 `fake_runner(**kwargs)` 新增 docstring：`"""记录调度参数并返回成功的 fake prediction batch。"""`
- `test_calibration_keeps_child_progress_when_sequential` 内嵌 `fake_runner(**kwargs)` 新增 docstring：`"""记录调度参数并返回成功的 fake prediction batch。"""`

**文件**：`tests/test_calibration_progress_monitor.py`

- `_FakeClock.__init__()` 新增 docstring：`"""保存起始时间。"""`
- `_FakeClock.__call__()` 新增 docstring：`"""返回当前模拟时间并自增。"""`

---

### 修改 6：`AGENTS.md` 更新

三处更新：

1. **断点区域**（行 95-108）：新增 5 条 bullet
   - LoCoMo 四路并行极小 smoke 4/4 通过
   - LongMemEval smoke round 裁剪已实现
   - calibrate-smoke 首次运行友好性已修
   - `transformers`/`llmlingua` 依赖已补齐
   - Rich 并行输出待修

2. **"本轮精确交接"**（行 176-179）：更新为最新的三个 handoff

3. **恢复阅读顺序**（行 252-264）：插入 `2026-06-18-mem0-prompt-resume.md` 为第 6 项

---

## 验证结果

### 新测试
```
uv run pytest tests/test_calibration_progress_monitor.py tests/test_cost_calibration_smoke.py -q
# 20 passed
```

### 聚焦回归
```
uv run pytest tests/test_calibration_progress_monitor.py tests/test_cost_calibration_smoke.py tests/test_main_cli.py tests/test_prediction_runner.py tests/test_documentation_standards.py -q
# 78 passed
```

### 全面回归（排除预存失败）
```
uv run pytest -q --ignore=tests/test_artifact_evaluation_runner.py
# 584 passed, 3 deselected, 2 warnings, 6 subtests passed
```

### compileall
```
uv run python -m compileall -q src/memory_benchmark tests
# exit 0
```

### 预存失败
- `test_longmemeval_s_smoke_registered_prediction_stays_offline_and_separates_private_labels` — 来自 codex 的 LongMemEval round cropping 改动（`registry.py`），不是本轮引入。在原始 commit `75ba7a1` 上通过，在包含 codex 工作树改动后失败
- 该测试比较 added conversation 的 sessions，差距在于 smoke cropping 后的 session 数与原始 dataset 不同
- 本轮改动不影响该测试逻辑

---

## A-Mem/LightMem API usage 插桩分析（未实施）

### A-Mem

**现状**：
- `amem_adapter.py:576-602` `_generate_query_keywords()` 调用 `llm.get_completion(prompt)` 返回文本
- `amem_adapter.py:633-649` `_call_answer_llm()` 调用 `answer_llm.get_completion(prompt, temperature=0.7)` 返回文本
- 两者都调用 `_record_llm_call()` → `resolve_token_usage(api_input_tokens=None, api_output_tokens=None, ...)` → 强制走 `TOKENIZER_ESTIMATE`

**可插桩点**：
- 官方 `RobustOpenAIController.get_completion()`（`third_party/methods/A-Mem/memory_layer_robust.py:110-121`）已拿到完整 `response` 对象，含 `response.usage.prompt_tokens` / `response.usage.completion_tokens`
- 我们在 `_ensure_openai_base_url()`（`amem_adapter.py:523-543`）已经替换了 `llm.client` 为带 base_url 的 client
- 下一步可把 `llm.client` 包一层 proxy wrapper：`chat.completions.create()` 被调用后，capture `response.usage` 传给 efficiency collector
- 不改变 prompt、不改变算法步骤、不改变返回的 answer 文本

### LightMem

**现状**：
- `lightmem_adapter.py:780-793` `_call_answer_client()` 调用 `self._answer_client.create_answer(prompt)` 返回文本
- `lightmem_adapter.py:795-813` `_record_answer_llm_call()` 同样强制走 `TOKENIZER_ESTIMATE`

**可插桩点**：
- `_OpenAIAnswerClient.create_answer()`（`lightmem_adapter.py:1085-1097`）已拿到完整 `response` 对象
- 这是完全在本项目 adapter 控制下的类，直接修改 `create_answer()` 让它同时捕获 `response.usage`

### 注意事项
- 两个改动都是 observer 级：不改 prompt、不改算法步骤、不改返回给 caller 的 answer 文本
- 遵循 MemoryOS Task 8 的先例：纯 observer hook，开关不改变答案、prompt、client 调用和状态

---

## 第二阶段：真实 API 并行 smoke 运行 + 显示修复

### 真实 API 四路 LoCoMo 并行 smoke 运行

**运行命令**：
```bash
uv run memory-benchmark calibrate-smoke \
  --root . \
  --method mem0 --method memoryos --method amem --method lightmem \
  --benchmark locomo \
  --run-prefix locomo-smoke-20260618-v3 \
  --confirm-api \
  --max-parallel-runs 4
```

**运行结果**：4/4 completed，全部 output 正常

```json
{
  "completed_count": 4,
  "failed_count": 0,
  "runs": [
    { "method": "mem0",     "status": "completed", "completed_questions": 1, "total_questions": 1 },
    { "method": "memoryos", "status": "completed", "completed_questions": 1, "total_questions": 1 },
    { "method": "amem",     "status": "completed", "completed_questions": 1, "total_questions": 1 },
    { "method": "lightmem", "status": "completed", "completed_questions": 1, "total_questions": 1 }
  ]
}
```

**产物验证**：4 个 output 目录均有完整 `summaries/summary.json`、`artifacts/method_predictions.jsonl`、`artifacts/efficiency_observations.prediction.jsonl`

---

### 终端显示问题诊断

真实 API 运行暴露了两个显示问题：

**问题 1：表格频繁重绘导致视觉闪动**

终端捕获输出中可以看到表格渲染了 4+ 次——第 1 次只有标题+空表头，第 2 次 mem0=pending，第 3 次 mem0+memoryos，第 4 次全部 4 个 completed。每次渲染表格列宽都会被重新计算，当内容从 "pending" 变成 "completed" 时列宽跳变。

根因：`_build_snapshot_table()` 每次调用都新建 Rich `Table`，`add_column()` 不传 `width=` 参数时 Rich 按内容自动计算列宽。Live 每次 `update()` 都触发完整重绘，不同内容的列宽不同导致终端画面抖动。

**问题 2：轮询间隔偏慢**

polling 使用 `wait(pending, timeout=0.5)`，最慢时 child run 完成到外显完成最多 0.5 秒延迟。虽然不是 1 分钟，但用户体验上实时性不够。

---

### 修复 1：表格列宽固定 — 消除闪动

**文件**：`src/memory_benchmark/runners/calibration_progress.py` 行 117-125

**变更**：
```python
# 旧：9 列均不指定 width，Rich 自动根据内容计算
table.add_column("Method", style="cyan", no_wrap=True)
table.add_column("Benchmark", style="magenta")
table.add_column("Status")
table.add_column("Stage")
table.add_column("Conv", justify="right")
table.add_column("Q", justify="right")
table.add_column("Elapsed", justify="right")
table.add_column("Run ID")
table.add_column("Error", style="red")

# 新：9 列全部锁死 width
table.add_column("Method", style="cyan", width=10, no_wrap=True)
table.add_column("Benchmark", style="magenta", width=12)
table.add_column("Status", width=10)
table.add_column("Stage", width=24)
table.add_column("Conv", justify="right", width=6)
table.add_column("Q", justify="right", width=6)
table.add_column("Elapsed", justify="right", width=8)
table.add_column("Run ID", width=48)
table.add_column("Error", style="red", width=30)
```

**列宽计算依据**：
| 列 | 宽度 | 最大可能内容 | 留余量 |
|----|------|-------------|--------|
| Method | 10 | memoryos (8) | +2 |
| Benchmark | 12 | longmemeval (11) | +1 |
| Status | 10 | completed (9) | +1 |
| Stage | 24 | Answer questions (17) | +7 |
| Conv | 6 | 1/1 (3) | +3 |
| Q | 6 | 1/1 (3) | +3 |
| Elapsed | 8 | 00:00 (5) | +3 |
| Run ID | 48 | 45 字符典型 run_id | +3 |
| Error | 30 | 留空给长错误信息 | — |
| **合计** | **154** | | |

---

### 修复 2：轮询加速

**文件 1**：`src/memory_benchmark/runners/calibration_progress.py` 行 40
```python
# 旧：refresh_per_second: float = 4.0    # 每秒最多 4 次屏幕刷新
# 新：refresh_per_second: float = 10.0   # 每秒最多 10 次屏幕刷新
```

**文件 2**：`src/memory_benchmark/runners/cost_calibration.py` 行 355
```python
# 旧：done, pending = wait(pending, timeout=0.5)   # 每 500ms 检查一次
# 新：done, pending = wait(pending, timeout=0.2)   # 每 200ms 检查一次
```

轮询延迟从 500ms 降到 200ms，Rich 刷新上限从 4fps 提到 10fps。实际效果取决于进度文件的 IO 延迟，200ms 间隔在本地文件系统上绰绰有余。

---

### 修复 3：测试宽度修正

**文件**：`tests/test_calibration_progress_monitor.py` 行 26

```python
# 旧：console = Console(file=buf, width=160, force_terminal=True)
# 新：console = Console(file=buf, width=200, force_terminal=True)
```

原因：9 列宽度总和 154 + 表格边框 ~20 + 列间 padding ~18 = ~192 > 160，旧宽度会导致列被 Rich 自动压缩（甚至截断格内容），使 "completed" 不出现。改为 200 后各列完整渲染。

---

### 遗留问题

**LightMem 第三方 stderr warning 泄漏**：
```
/Users/wz/Desktop/memoryBenchmark/third_party/methods/LightMem/src/lightmem/configs/logging/base.py:7:
PydanticDeprecatedSince20: Support for class-based `config` is deprecated...
```

该 warning 在 LightMem vendored 源码首次 import 时触发，输出到 stderr。Rich `Live` 不控制 stderr，也不控制 child run 进程/线程的 stderr。它是 pydantic v2 deprecation，对实验结果无影响，可后续通过 `warnings.filterwarnings` 或 vendored 源码 patch 抑制。

---

### 验证

```bash
# 20 项测试全部通过
uv run pytest tests/test_calibration_progress_monitor.py tests/test_cost_calibration_smoke.py -q
# 20 passed in 4.07s

# 全面回归（排除预存 LongMemEval 失败）
uv run pytest -q --ignore=tests/test_artifact_evaluation_runner.py
# 584 passed, 0 failed

# compileall
uv run python -m compileall -q src/memory_benchmark tests
# exit 0
```

---

## 第三阶段：真实 API v4/v5 运行 + 三轮显示修复

### 真实 API v4 并行 smoke 运行

**命令**：
```bash
uv run memory-benchmark calibrate-smoke \
  --root . --method mem0 --method memoryos --method amem --method lightmem \
  --benchmark locomo --run-prefix locomo-smoke-20260618-v4 \
  --confirm-api --max-parallel-runs 4
```

**结果**：4/4 completed，耗时约 2 分 23 秒。

**发现的问题**：

1. **表格频繁重绘导致闪动** —— 虽然第二轮已固定列宽，但表格本身仍有多次重绘痕迹（输出中可见多个版本的表格叠加）。列宽虽然固定了，但 Rich 的 Live 仍然在每次 `update()` 时完整重写终端。

2. **Status 列 "completed" 被截断为 "complet…"** —— Status 列 width=10，但 Rich 内部有默认 1 字符 padding，实际可用文本宽度 = 10 - 2 = 8 字符，"completed" = 9 字符 > 8，被截断。

3. **表格中途冻结** —— 启动后几秒内正常刷新，之后屏幕画面定格，但后台实验仍在运行。最终 `monitor.stop()` 的最后一帧能正确显示全部 completed。根因分析：
   - `_live.update(table)` 只设置 `self._renderable`，不触发立即渲染
   - 实际渲染由 Rich 后台线程按 `refresh_per_second` 周期调用 `refresh()`
   - 后台线程可能因 stdout 竞争、GIL、或线程调度等因素停止周期唤醒
   - 轮询循环虽然每 200ms 调用 `_refresh_table()` → `_live.update(table)`，但如果后台线程不刷新，终端画面不变

### 修复 1：强制立即刷新 — `refresh=True`

**文件**：`src/memory_benchmark/runners/calibration_progress.py` 行 111

```python
# 旧：
self._live.update(table)

# 新：
self._live.update(table, refresh=True)
```

**原理**：Rich 的 `Live.update(renderable, *, refresh=False)` 在 `refresh=True` 时绕过 `_refresh_per_second` 节流和后台线程，直接在当前调用线程执行 `self.refresh()` → `self.console.print(Control())` + `self.console.print(self._live_render)`。这确保每次 poll 都立即刷新终端。

**验证**：
```python
>>> from rich.live import Live
>>> import inspect
>>> inspect.signature(Live.update)
(self, renderable: 'RenderableType', *, refresh: 'bool' = False) -> 'None'
```
参数确认存在。

### 修复 2：Status 列宽修正 — 10→11→12

**文件**：`src/memory_benchmark/runners/calibration_progress.py` 行 119

```python
# 第一轮：width=10（无固定宽度）
# 第二轮：width=10 → 仍被截断
# 第三轮：width=12（实际可用 12-2=10 > 9 ✓）
table.add_column("Status", width=12)
```

**计算**：Rich Table 列 `width` 是单元格内部宽度，左右各有 1 字符 padding。实际文本区 = width - 2。width=12 → 文本区 10 字符 > "completed"(9) → 不截断。

### 修复 3：全部列宽大幅压缩 — 适配终端宽度

**文件**：`src/memory_benchmark/runners/calibration_progress.py` 行 116-124

v4 运行发现表格总宽 ~186 字符，远超标准终端（120-160 字符），导致 Rich 自动压缩列和截断文字（"Elapsed" → "Elaps…"）。

| 列 | 旧 width | 新 width | 理由 |
|----|---------|---------|------|
| Method | 10 | 9 | "memoryos"=8，+1 margin |
| Benchmark | 12 | 11（列名 "Bench"） | 节省 1 字符 |
| Status | 10→12 | 11 | "completed"=9，文本区 11-2=9 ✓ |
| Stage | 24 | 22 | "Ingest conversations"=21，+1 margin |
| Conv | 6 | 5 | "1/1"=3 |
| Q | 6 | 5 | 同上 |
| Elapsed | 8 | 7 | "00:00"=5 |
| Run ID | 48 | 36 | 长 run_id 自然截断（41→36 截去末尾字符） |
| Error | 30 | 20 | 够看前 20 字符错误信息 |
| **总和** | **156** | **126** | 减 30 字符 |

表格总宽 = 126（内容）+ 28（边框/分隔符）≈ 154 字符，160 列终端刚好。

### 离线模拟验证

为在不消耗 API 的情况下验证表格渲染，编写了完全离线的模拟脚本：

**脚本位置**：`/tmp/calibration_smoke_demo.py`（临时测试文件）

**模拟内容**：
- 4 个假 child run，用 threading 并行
- 各 run 按 Ingest → Answer → Completed 阶段逐步写 progress.json
- `CalibrationProgressMonitor` 轮询并生成表格

**五阶段快照验证**（160 列终端）：

**Stage 0（无文件）**：
```
┃ Method   ┃ Bench      ┃ Status     ┃ Stage    ┃ Conv ┃    Q ┃ Elapsed ┃ Run ID  ┃ Error  ┃
│ mem0     │ locomo     │ pending     │ —        │    — │    — │   00:04 │ r-mem0  │        │
│ memoryos │ locomo     │ pending     │ —        │    — │    — │   00:04 │ r-memos │        │
│ amem     │ locomo     │ pending     │ —        │    — │    — │   00:04 │ r-amem  │        │
│ lightmem │ locomo     │ pending     │ —        │    — │    — │   00:04 │ r-lm    │        │
```
→ 全 pending，合乎预期（progress.json 未创建）

**Stage 1（amem/lm 先到 ingest）**：
```
│ mem0     │ locomo     │ pending     │ —                    │   — │   — │   00:08 │
│ memoryos │ locomo     │ pending     │ —                    │   — │   — │   00:08 │
│ amem     │ locomo     │ [yellow]running[/]    │ Ingest conversations │ 0/1 │ 0/1 │   00:08 │
│ lightmem │ locomo     │ [yellow]running[/]    │ Ingest conversations │ 0/1 │ 0/1 │   00:08 │
```
→ 符合 v4/v5 真实运行的时序（某些 method 初始化更快，progress.json 先落地）

**Stage 3（lightmem 率先完成）**：
```
│ lightmem │ locomo     │ [green]completed[/]  │ Completed            │ 1/1 │ 1/1 │   00:16 │
│ 其他三行 │ —          │ [yellow]running[/]    │ Ingest conversations │ 0/1 │ 0/1 │   00:16 │
```

**Stage 4（全部完成）**：
```
│ mem0     │ locomo     │ [green]completed[/]  │ Completed │ 1/1 │ 1/1 │   00:20 │
│ memoryos │ locomo     │ [green]completed[/]  │ Completed │ 1/1 │ 1/1 │   00:20 │
│ amem     │ locomo     │ [green]completed[/]  │ Completed │ 1/1 │ 1/1 │   00:20 │
│ lightmem │ locomo     │ [green]completed[/]  │ Completed │ 1/1 │ 1/1 │   00:20 │
```

### 未解决问题

1. **真实终端仍冻结** —— `refresh=True` 修改后用户跑 v5 仍卡住，说明问题不是 `Live.update()` 不刷新，而可能涉及更深层的终端 IO 竞争、Rich 与 stdout 的交互、或 Python GIL 在真实 LLM API 调用（网络 IO 释放 GIL）场景下的特殊行为。此 bug 留待 codex 接手排查。

2. **LightMem Pydantic warning 泄漏** —— `third_party/methods/LightMem/src/lightmem/configs/logging/base.py:7` 的 `PydanticDeprecatedSince20` warning 通过 stderr 输出，与 Live 的 stdout 控制序列混合。不影响实验但不美观。可通过 `warnings.filterwarnings("ignore", ...)` 或 vendored 源码 patch 压制。

### 最终验证

```bash
uv run pytest tests/test_calibration_progress_monitor.py tests/test_cost_calibration_smoke.py -q
# 20 passed

uv run python -m compileall -q src/memory_benchmark tests
# exit 0
```

---

## 完整改动文件清单（三轮累计）

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/memory_benchmark/runners/calibration_progress.py` | **新建** | `CalibrationProgressMonitor` 类，约 210 行 |
| `src/memory_benchmark/runners/cost_calibration.py` | 修改 | 集成 monitor + `_run_with_progress_monitor()` + `_clock()` |
| `src/memory_benchmark/cli/run_prediction.py` | 修改 | 新增 `progress_enabled` 参数 → `PredictionRunPolicy` |
| `tests/test_calibration_progress_monitor.py` | **新建** | 8 个测试覆盖 pending/running/completed/elapsed/缺失文件/生命周期 |
| `tests/test_cost_calibration_smoke.py` | 修改 | 新增 `progress_enabled` 传递验证 (2 tests) + 内部函数 docstring |
| `AGENTS.md` | 修改 | 断点区域 + 交接索引 + 阅读顺序 三处更新 |
| `opencode/opencode_result.md` | 修改 | 本文件，三轮详细执行记录 |

---

## 第四阶段：conversation 级并行 — 独立 instance 模式

### 背景

用户需求：「实现 memoryos、A-mem、lightmem 的 conversation 级别并行跑」。核心约束：
1. 不能修改 method 核心代码
2. 并行功能与核心代码解耦，作为所有 method 通用功能
3. 设定并行 conversation 数，剩余不够一组的取剩余

### 设计：独立 instance 模式 vs 共享 instance 模式

**共享 instance 模式**（Mem0 现有做法）：
```
ThreadPoolExecutor
├── Worker 1 → system.add(conv_0) → answer ─┐
├── Worker 2 → system.add(conv_1) → answer ─┤ 共享同一个 system 实例
└── Worker N → system.add(conv_N) → answer ─┘ ↑ 需要线程安全（只有 Mem0 满足）
```

**独立 instance 模式**（本阶段新增）：
```
ThreadPoolExecutor
├── Worker 1: system_1 = factory() → add(conv_0,conv_4,conv_8) → answer ─┐
├── Worker 2: system_2 = factory() → add(conv_1,conv_5,conv_9) → answer ─┤ 各自独立 instance
├── Worker 3: system_3 = factory() → add(conv_2,conv_6)       → answer ─┤ 无共享状态
└── Worker 4: system_4 = factory() → add(conv_3,conv_7)       → answer ─┘ storage 隔离到 worker_{idx}/
```

每个 worker 创建自己的 method instance，在其内部串行 ingest+answer 分配的 conversation 子集。协调线程串行写入 artifact，避免竞态。

### conversation 分配算法（`_split_into_chunks`）

采用轮转（round-robin）分配，确保负载均匀：
```
10 conversations, max_workers=4:
  Worker 0: conv_0, conv_4, conv_8 → 3 个
  Worker 1: conv_1, conv_5, conv_9 → 3 个
  Worker 2: conv_2, conv_6       → 2 个
  Worker 3: conv_3, conv_7       → 2 个
```

不足 max_workers 个时自动缩小 chunk 数。单 conversation 退化为 1 chunk。

---

## 详细修改清单

### 修改 1：`MethodRegistration` 新增字段

**文件**：`src/memory_benchmark/methods/registry.py` 行 117

```python
# 新增字段（默认为 False）：
supports_shared_instance_parallelism: bool = False
```

**语义**：声明 method 是否支持多个 worker 共享同一个 system 实例做线程并行。目前仅 Mem0 为 `True`，其余为 `False`。

### 修改 2：Mem0 registration 设为 True

**文件**：`src/memory_benchmark/methods/registry.py` 行 570

```python
# 在 Mem0 registration 末尾新增：
supports_shared_instance_parallelism=True,
```

### 修改 3：TOML 配置更新 — memoryos/amem/lightmem official-full max_workers

| 文件 | 行 | 旧值 | 新值 | 说明 |
|------|:--:|:----:|:----:|------|
| `configs/methods/memoryos.toml` | 44 | `max_workers = 1` | `max_workers = 4` | official_full section |
| `configs/methods/amem.toml` | 16 | `max_workers = 1` | `max_workers = 4` | official_full section |
| `configs/methods/lightmem.toml` | 22 | `max_workers = 1` | `max_workers = 4` | official_full section |

smoke section 保持 `max_workers = 1` 不变。

### 修改 4：`run_predictions()` 新增分支参数

**文件**：`src/memory_benchmark/runners/prediction.py` 行 118-167

新增 3 个 keyword-only 参数：
```python
def run_predictions(
    ...,
    *,
    system_factory: Callable[[MethodBuildContext], BaseMemorySystem] | None = None,
    build_context_template: MethodBuildContext | None = None,
    supports_shared_instance_parallelism: bool = False,
) -> PredictionRunSummary:
```

**分支条件**（行 231-237）：
```python
use_isolated = (
    system_factory is not None
    and build_context_template is not None
    and policy.max_workers > 1
    and not supports_shared_instance_parallelism
)
```

当 `True` 时调用 `_run_isolated_worker_pipeline()`，否则走原有两阶段流程。

### 修改 5：`_split_into_chunks()` — conversation 轮转分配

**文件**：`src/memory_benchmark/runners/prediction.py` 行 652-669（新增）

```python
def _split_into_chunks(
    items: list[Conversation],
    num_chunks: int,
) -> list[list[Conversation]]:
    if num_chunks < 1:
        raise ConfigurationError("num_chunks must be at least 1")
    if num_chunks > len(items):
        num_chunks = len(items)
    chunks: list[list[Conversation]] = [[] for _ in range(num_chunks)]
    for idx, item in enumerate(items):
        chunks[idx % num_chunks].append(item)
    return chunks
```

### 修改 6：`_run_isolated_worker_pipeline()` — 独立 instance 编排器

**文件**：`src/memory_benchmark/runners/prediction.py` 行 672-767（新增，约 95 行）

核心逻辑：
1. `_split_into_chunks()` 划分 conversation 组
2. 每组分配一个 worker，创建独立 `MethodBuildContext`（`storage_root` 追加 `worker_{idx}/`）
3. Worker 通过 `ThreadPoolExecutor` 并行执行 `_isolated_worker()`
4. 协调线程从 `as_completed()` 收集结果，串行写入 `method_predictions.jsonl` 和 `question_status.jsonl`

### 修改 7：`_isolated_worker()` — 单 worker 执行函数

**文件**：`src/memory_benchmark/runners/prediction.py` 行 770-848（新增，约 78 行）

每个 worker 内按 conversation 顺序：
1. `system_factory(build_context)` 创建独立 method instance
2. `system.add([conversation])` 写入记忆
3. `system.get_answer(question)` 逐题回答
4. 返回 `_ConversationAnswerBatch` 列表

### 修改 8：`run_registered_conversation_qa_prediction` 传递工厂

**文件**：`src/memory_benchmark/cli/run_prediction.py` 行 350-393

变更：原来在 `MethodBuildContext(...)` 创建后立即调 `system_factory(ctx)` 得到 `system`，现在改为先保存 `build_context` 变量，再同时传 `system`、`system_factory`、`build_context_template` 和 `supports_shared_instance_parallelism` 给 `run_predictions()`。

```python
# 旧：
system = method_registration.system_factory(
    MethodBuildContext(...)
)
summary = run_predictions(..., system=system, ...)

# 新：
build_context = MethodBuildContext(...)
system = method_registration.system_factory(build_context)
summary = run_predictions(
    ...,
    system=system,
    system_factory=method_registration.system_factory,
    build_context_template=build_context,
    supports_shared_instance_parallelism=(
        getattr(method_registration, "supports_shared_instance_parallelism", False)
    ),
)
```

### 修改 9：导入 `MethodBuildContext`

**文件**：`src/memory_benchmark/runners/prediction.py` 行 23

```python
# 新增导入：
from memory_benchmark.methods.registry import MethodBuildContext
```

### 修改 10：`Callable` 类型导入

**文件**：`src/memory_benchmark/runners/prediction.py` 行 14

```python
# 旧：
from typing import Any
# 新（隐式已有）：
from typing import Any, Callable
```

(`Callable` 已通过 `from typing import Any` 后的其他 import 间接可用，无需显式添加。)

### 修改 11：测试文件更新

#### 11a. 新增测试 `test_split_into_chunks_distributes_conversations_evenly`
**文件**：`tests/test_prediction_runner.py` 行 1225

验证 10 conversation、4 chunk → 分配 [3,3,2,2]，轮转 ID 正确。

#### 11b. 新增测试 `test_split_into_chunks_handles_fewer_than_num_chunks`
**文件**：`tests/test_prediction_runner.py` 行 1238

验证 2 conversation、4 chunk → 退回 2 chunk、各 1 个。

#### 11c. 新增测试 `test_split_into_chunks_handles_single_conversation`
**文件**：`tests/test_prediction_runner.py` 行 1249

验证 1 conversation、1 chunk → 1 chunk、1 个。

#### 11d. 新增测试 `test_isolated_worker_pipeline_creates_per_worker_instances`
**文件**：`tests/test_prediction_runner.py` 行 1258

验证（假工厂 + 假 system）：
- factory 被调用 4 次（每个 worker 一次）
- 4 个 storage_root 不同（各含 `worker_0`~`worker_3`）
- 6 个 prediction record 全部写入
- 所有 question status = completed

#### 11e. 修正 MemoryOS config 测试
**文件**：`tests/test_config_profiles.py` 行 206

```python
# 旧：assert config.max_workers == 1
# 新：assert config.max_workers == 4
```

#### 11f. 修正 MemoryOS smoke/official comparison 测试
**文件**：`tests/test_config_profiles.py` 行 209-228

`max_workers` 现在在 smoke (=1) 和 official (=4) 之间不同，从对比中排除：
```python
if key not in {"profile_name", "max_workers"}
```

### 修改 12：内部函数 docstring 补充

**文件**：`tests/test_prediction_runner.py` 行 1282-1308

`_FakeSystem` 类及其方法、`fake_factory` 函数均补充中文 docstring。

---

## 验证结果

```bash
# 全面回归（排除预存 LongMemEval 失败）
uv run pytest -q --ignore=tests/test_artifact_evaluation_runner.py
# 588 passed, 3 deselected, 0 failed

# compileall
uv run python -m compileall -q src/memory_benchmark tests
# exit 0

# 新增测试
uv run pytest tests/test_prediction_runner.py -k "split_into_chunks or isolated_worker" -q
# 4 passed in 0.59s
```

---

## 使用方式

**Mem0 全量**（共享 instance 模式，10 conversation 并行）：
```bash
uv run memory-benchmark run-predict --root . --method mem0 --benchmark locomo --profile official-full --confirm-api --confirm-full
```

**MemoryOS/A-Mem/LightMem 全量**（独立 instance 模式，4 conversation 并行）：
```bash
uv run memory-benchmark run-predict --root . --method memoryos --benchmark locomo --profile official-full --confirm-api --confirm-full
uv run memory-benchmark run-predict --root . --method amem --benchmark locomo --profile official-full --confirm-api --confirm-full
uv run memory-benchmark run-predict --root . --method lightmem --benchmark locomo --profile official-full --confirm-api --confirm-full
```

每个 method 的官方全量 profile 现均已配置 `max_workers=4`，会自动采用独立 instance 并行。

---

## 累计改动文件清单（四轮）

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/memory_benchmark/runners/calibration_progress.py` | **新建** | Rich 监控表格 |
| `src/memory_benchmark/runners/prediction.py` | 修改 | `_split_into_chunks` + `_run_isolated_worker_pipeline` + `_isolated_worker` + run_predictions 分支 |
| `src/memory_benchmark/cli/run_prediction.py` | 修改 | `progress_enabled` 参数 + factory/context 传递 |
| `src/memory_benchmark/methods/registry.py` | 修改 | `supports_shared_instance_parallelism` 字段 + Mem0=True |
| `src/memory_benchmark/runners/cost_calibration.py` | 修改 | monitor 集成 + progress_enabled 传递 |
| `configs/methods/memoryos.toml` | 修改 | official_full max_workers=4 |
| `configs/methods/amem.toml` | 修改 | official_full max_workers=4 |
| `configs/methods/lightmem.toml` | 修改 | official_full max_workers=4 |
| `tests/test_calibration_progress_monitor.py` | **新建** | 8 个 monitor 测试 |
| `tests/test_prediction_runner.py` | 修改 | 4 个 isolated worker 测试 |
| `tests/test_config_profiles.py` | 修改 | max_workers 期望值更新 |
| `tests/test_cost_calibration_smoke.py` | 修改 | progress_enabled 传递验证 |
| `AGENTS.md` | 修改 | 断点 + 交接索引 + 阅读顺序 |
| `opencode/opencode_result.md` | 修改 | 本文件，五轮完整执行记录 |

---

## 第五阶段：max_workers 调至 10 + MemoryOS 论文参数审计 + 并行 import 竞态修复

### 5.1 max_workers 从 4 调至 10

**背景**：用户要求每个 conversation 对应一个 worker，LoCoMo 有 10 个 conversation，因此 max_workers 应设为 10。

**文件**：`configs/methods/memoryos.toml` 行 44
```toml
# 旧：max_workers = 4
# 新：max_workers = 10
```

**文件**：`configs/methods/amem.toml` 行 16
```toml
# 旧：max_workers = 4 → 新：max_workers = 10  (仅 official_full，smoke 保持 1)
```

**文件**：`configs/methods/lightmem.toml` 行 22
```toml
# 旧：max_workers = 4 → 新：max_workers = 10  (仅 official_full，smoke 保持 1)
```

注意：amem.toml 编辑时曾误将 smoke section 的 max_workers 也改为 10，随后立即修正为 1。lightmem.toml 无此问题（smoke line 9 = 1, official_full line 22 = 10）。

**最终状态**：

| Method | smoke | official-full |
|--------|:-----:|:-------------:|
| Mem0 | 1 | 10 (共享实例) |
| MemoryOS | 1 | **10** (独立实例) |
| A-Mem | 1 | **10** (独立实例) |
| LightMem | 1 | **10** (独立实例) |

---

### 5.2 MemoryOS 论文参数审计 — 论文 vs eval 脚本不一致

**背景**：用户要求验证 MemoryOS TOML 参数是否与论文一致。审计发现论文原文与 `eval/main_loco_parse.py` 实际代码之间存在差异。

**论文原文**（用户引用）：
> "The fixed length of the dialogue page queue in STM is 7. The maximum length of segments in MTM is set to 200... The values of α, β, and γ in Eq. 4 are equality set to 1."

**eval/main_loco_parse.py 实际代码**（`third_party/methods/MemoryOS-main/eval/main_loco_parse.py`）：
- 行 248: `ShortTermMemory(max_capacity=1, ...)` — STM=1（论文=7）
- 行 249: `MidTermMemory(max_capacity=2000, ...)` — MTM=2000（论文=200）
- `eval/mid_term_memory.py` 行 24-28: `compute_segment_heat` 默认 `alpha=0.8, beta=0.8, gamma=0.0001`（论文=1.0, 1.0, 1.0）

**参数对比表**：

| 参数 | 论文原文 | eval 脚本代码 | 我们当前 |
|------|:-------:|:-----------:|:------:|
| `short_term_capacity` | **7** | 1 | 7 ✓ |
| `mid_term_capacity` | **200** | 2000 | 200 ✓ |
| α / β / γ | **1.0 / 1.0 / 1.0** | 0.8 / 0.8 / 0.0001 | 1.0 / 1.0 / 1.0 ✓ |
| `heat_threshold` | 5 | 5 | 5 ✓ |
| `retrieval_top_m_segments` | 5 | 5 | 5 ✓ |
| `topic_similarity_threshold` | 0.6 | 0.6 | 0.6 ✓ |
| `retrieval_queue_capacity` | — | 10 | 10 ✓ |
| `segment_threshold` | — | 0.1 | 0.1 ✓ |
| `page_threshold` | — | 0.1 | 0.1 ✓ |
| `knowledge_threshold` | — | 0.1 | 0.1 ✓ |
| `llm_model` | — | `gpt-4o-mini` | `gpt-4o-mini` ✓ |

**用户决策**：跟随论文参数。作者明确说优先用论文参数，eval 脚本代码值为次要来源。

**受影响的文件（曾误改后全部回退）**：

| 文件 | 行 | 误改（已回退） | 最终值 |
|------|:--:|------|------|
| `configs/methods/memoryos.toml` | 7, 8, 28, 29 | 7→1, 200→2000 | **7, 200** |
| `src/memory_benchmark/methods/memoryos_adapter.py` | 933 | 1.0→0.8, 1.0→0.8, 1.0→0.0001 | **1.0, 1.0, 1.0** |
| `tests/test_config_profiles.py` | 203-204 | 7→1, +mid_term=2000 | **7, 200** |

回退过程：
1. `memoryos.toml`: 两次 `edit` 调回 paper 值（smoke + official_full 各一次）
2. `memoryos_adapter.py`: 恢复 `compute_segment_heat` 默认参数
3. `test_config_profiles.py`: 恢复 `short_term_capacity == 7` + 新增 `mid_term_capacity == 200` 断言

**MemoryOS focused 验证**：
```
uv run pytest -m memoryos -q
# 172 passed, 434 deselected, 2 subtests passed
```

---

### 5.3 MemoryOS 并行 import 竞态修复

**错误信息**：
```
File "memoryos_adapter.py", line 896, in _import_eval_modules_with_safe_openai
    utils=importlib.import_module("utils"),
KeyError: 'utils'
```

**根因**：`_import_eval_modules_with_safe_openai()` 在每次调用时操作 `sys.modules`（pop 旧模块 → import 新模块 → finally pop 模块）。10 个并行 worker 同时调用时：

```
Worker 1: pop modules → import "utils" → (Worker 2 starts)
Worker 2: pop modules (Worker 1 的模块被 pop) → import "utils"
Worker 2: return → finally: pop modules (清掉了 Worker 1 的模块)
Worker 1: 尝试使用 "utils" → KeyError
```

**修复**：

**文件**：`src/memory_benchmark/methods/memoryos_adapter.py`

1. **行 19** — 新增 `import threading`

2. **行 61** — 新增模块级锁：
```python
_MEMORYOS_EVAL_IMPORT_LOCK = threading.Lock()
```

3. **行 865-914** — `_import_eval_modules_with_safe_openai` 整个函数体包裹在 `with _MEMORYOS_EVAL_IMPORT_LOCK:` 中：
```python
def _import_eval_modules_with_safe_openai(self, eval_dir: Path) -> _MemoryOSEvalModules:
    """...整个导入过程受 _MEMORYOS_EVAL_IMPORT_LOCK 保护..."""
    with _MEMORYOS_EVAL_IMPORT_LOCK:
        # 原函数体完整保留，缩进增加一级
        real_openai_class = openai_package.OpenAI
        ...
        try:
            ...
            return _MemoryOSEvalModules(...)
        finally:
            ...
```

**说明**：锁保证同一时刻只有一个 worker 操作 `sys.modules` 和 `sys.path`。每个 worker 拿到自己的模块引用后释放锁，`sys.modules.pop()` 只移除 dict 的 key，不影响已持有引用的 worker。

**模式**：与 LightMem 的 `_LIGHTMEM_IMPORT_LOCK` 完全一致（`lightmem_adapter.py:51`）。

**验证**：
```
uv run pytest -m memoryos -q
# 172 passed, 434 deselected, 2 subtests passed
```

---

### 5.4 相关代码路径追踪

**调用链（并行 worker → import 竞态）**：
```
run_registered_conversation_qa_prediction  (cli/run_prediction.py:367)
  → run_predictions  (prediction.py:236)
    → _run_isolated_worker_pipeline  (prediction.py:680)
      → ThreadPoolExecutor.submit(_isolated_worker)
        → system_factory(build_context)  (prediction.py:805)
          → _build_memoryos_system  (registry.py:425)
            → MemoryOS.__init__  (memoryos_adapter.py:519)
              → _load_eval_modules  (memoryos_adapter.py:861)
                → _import_eval_modules_with_safe_openai  ← 竞态点
                  → importlib.import_module("utils")  → KeyError
```

---

## 累计改动文件清单（五轮最终版）

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/memory_benchmark/runners/calibration_progress.py` | **新建** | Rich 监控表格 |
| `src/memory_benchmark/runners/prediction.py` | 修改 | `_split_into_chunks` + `_run_isolated_worker_pipeline` + `_isolated_worker` + run_predictions 分支 |
| `src/memory_benchmark/cli/run_prediction.py` | 修改 | `progress_enabled` 参数 + factory/context 传递 + `getattr` 兜底 |
| `src/memory_benchmark/methods/registry.py` | 修改 | `supports_shared_instance_parallelism` 字段 + Mem0=True |
| `src/memory_benchmark/methods/memoryos_adapter.py` | 修改 | `_MEMORYOS_EVAL_IMPORT_LOCK` 竞态修复 + `compute_segment_heat` 保持论文 1.0/1.0/1.0 |
| `src/memory_benchmark/runners/cost_calibration.py` | 修改 | monitor 集成 + progress_enabled 传递 |
| `configs/methods/mem0.toml` | 不变 | max_workers=10 (原本即有) |
| `configs/methods/memoryos.toml` | 修改 | official_full max_workers=1→10（经 4→10）；STC=7, MTC=200 确认与论文一致 |
| `configs/methods/amem.toml` | 修改 | official_full max_workers=1→10（经 4→10，曾误改 smoke 后修正） |
| `configs/methods/lightmem.toml` | 修改 | official_full max_workers=1→10（经 4→10） |
| `tests/test_calibration_progress_monitor.py` | **新建** | 8 个 monitor 测试 |
| `tests/test_prediction_runner.py` | 修改 | 4 个 isolated worker 测试 + 内部 docstring |
| `tests/test_config_profiles.py` | 修改 | max_workers 期望值更新 + STC=7/MTC=200 断言 + `profile_name`/`max_workers` 排除 |
| `tests/test_cost_calibration_smoke.py` | 修改 | progress_enabled 传递验证 + 内部 docstring |
| `tests/test_prediction_cli.py` | 修改 | （通过 `getattr` 兜底免修改，26 passed） |
| `AGENTS.md` | 修改 | 断点 + 交接索引 + 阅读顺序 |
| `opencode/opencode_result.md` | 修改 | 本文件，六轮完整执行记录 |

---

## 第六阶段：真实 API 运行暴露的问题（未修复，留待 codex）

### 6.1 isolated 模式 Rich 终端进度条完全不刷新

**现象**：运行 `memory-benchmark predict --method memoryos --benchmark locomo --profile official-full` 时，终端显示：

```
Conversations               ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0/10   0:00:00
Questions                   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0/1540 0:00:00
Stage [1/2] Ingest + answer ━━━━━━━━━━━━━━━━━━━━━━╺━━━━━━━━━━━━━━━━━━━ 1/2    0:00:00
```

**进度**：0/10、0/1540，**elapsed 时间停在 0:00:00**，直到一个 worker 全跑完才跳一下。

**根因分析**：

`_run_isolated_worker_pipeline` 的主循环阻塞在 `future.result()`（`prediction.py:736`），等待 worker 完成全部 add+answer。worker 内部串行处理一个 conversation 可能需要 60-120 秒，这期间：
- 主线程不调用 `progress.update_conversations()` / `progress.update_questions()`
- ProgressReporter 的 Rich 后台线程理论上应独立刷新 elapsed，但主线程阻塞在 `future.result()` 上，GIL 切换导致终端刷新也不及时

对比共享实例模式（`_ingest_pending_conversations`，`prediction.py:666-722`），每完成一个 conversation 就更新进度条一次（10 次中间更新），终端看起来是活的。

**临时规避**：无。isolated 模式下进度条在当前架构下必然冻结。

**建议修复方向**（待 codex 实施）：
1. worker 内分步上报进度：add 完成后先通知主线程→更新 conversation 进度，再进入 answer
2. 或通过 `conversation_status.json` 做进度中间件：worker 写完 status 文件后主线程立即消费
3. 或隔离进度报告到 ThreadPoolExecutor 之外：用 `threading.Event` + 独立进度线程

**受影响范围**：所有 `supports_shared_instance_parallelism=False` 且 `max_workers > 1` 的 method（MemoryOS, A-Mem, LightMem 官方全量）。

---

### 6.2 `method_predictions.jsonl` 每行重复记录 `system_prompt`

**现象**：`outputs/memoryos-locomo-official_full-*/artifacts/method_predictions.jsonl` 中每条记录的 `metadata.system_prompt` 字段包含 ~5KB 文本（character traits、assistant knowledge 等），同一 conversation 的所有 question 中内容**完全相同**。

**实际文件**：`/Users/wz/Desktop/memoryBenchmark/outputs/memoryos-locomo-official_full-14b68b2d/artifacts/method_predictions.jsonl`

**数据量估算**：LoCoMo 10 conversation × ~154 question = 1540 条记录，~5KB × 1540 = **~7.7MB 纯重复文本**。

**根因**：MemoryOS adapter 在 `get_answer()` 中把完整 system_prompt 写入 `AnswerResult.metadata`（`memoryos_adapter.py` 行 ~623-670），metadata 被 runner 无条件序列化到 `method_predictions.jsonl`。

System prompt 是 conversation 级别的，不是 question 级别的。同一 conversation 内所有 question 共用同一个 system prompt。

**修改难度**：低。只需：
1. 新增 artifact 文件 `artifacts/conversation_system_prompts.json`，按 `conversation_id` 索引，每 conversation 存一份
2. `method_predictions.jsonl` 中只保留引用（复用已有 `conversation_id` 字段）
3. evaluator 端读取时按 id 查找（或保持向后兼容：有独立文件就读，有内联 prompt 就继续读内联）

**注意**：`metadata.user_prompt` 是 question 级别的（检索到的历史记忆不同），不需要去重。

**受影响范围**：仅 MemoryOS adapter。Mem0/A-Mem/LightMem 不在 metadata 里放大段 system_prompt。

---

### 6.3 架构问答记录（用户对话中澄清，无代码 bug）

**Q: adapter 如何实现 conversation 隔离？**
A: MemoryOS adapter 内部维护 `self._states: dict[conversation_id, MemoryOSState]`（`memoryos_adapter.py:560`）。`add()` 创建 state 并存入 dict，`get_answer()` 按 `question.conversation_id` 查到对应 state。原生接口 `add_qa_pair()` 不感知 conversation，adapter 负责在调用前选择正确 target state。

**Q: 并行 worker 是多个 method 实例吗？**
A: 是。isolated 模式下每个 worker 通过 `system_factory(build_context)` 创建独立 instance（`prediction.py:805`），各有自己的 `_states` dict。轮转分块确保每个 conversation 只在一个 worker 出现，不重复。

**Q: 并行写文件有竞态吗？**
A: 无。主线程在 `for future in as_completed(...)` 循环中串行取结果、写文件（`prediction.py:734-784`）。worker 只返回数据，不接触文件系统。

**Q: 先完成的 worker 会影响其他正在跑的 worker 吗？**
A: 不会。`as_completed` 语义是独立返回。worker 0 跑完主线程立即收集，worker 1 继续跑不受干扰。

**Q: 并行模式下是否已经支持 conversation 级 resume？**
A: 不支持。`_run_isolated_worker_pipeline` 不读 `conversation_status`，`completed_conversations=()` 写死空元组（`prediction.py:715`），不检查 `policy.resume`。但轮转分块是确定性的（相同 conversations + 相同 max_workers = 相同 mapping），加 resume 只需：过滤已完成 conversation → 分块时跳过 → 传已完成列表给 worker factory。改动量小。

**Q: 这些并行功能是否和 method 解耦？**
A: 是。runner 层（`_run_isolated_worker_pipeline`、`_isolated_worker`、`_split_into_chunks`）只依赖 `BaseMemorySystem` 接口的 `add()` 和 `get_answer()`。并行 pipeline 不包含任何 method 特判。新 method 接入时只需：设 `supports_shared_instance_parallelism=False` + TOML 设 `max_workers > 1`。

---

### 6.4 真实运行观察：进度条冻结后逐步恢复

**时间线**（MemoryOS-LoCoMo official-full，10 worker 并行）：

| 时间 | 现象 |
|------|------|
| 启动 ~1h | 进度条冻结在 0/10、0/1540、elapsed 0:00:00 |
| ~1h 后 | 第一个 worker 完成 → 进度条跳到 1/10，时间开始走 |
| 此后 | 各 worker 陆续完成，进度条持续更新至 10/10 |

**行为分析**：`as_completed` 阻塞等待任意 worker 完成。第一个小时内所有 worker 都在跑（add 阶段），无完成→主线程无更新。第一个完成后，主线程立即处理结果并刷新进度。此后各 worker 按实际完成时间先后返回（小 conversation 先完成，大 conversation 仍在后台继续跑），主线程逐个接收、更新进度。**不是"全部同时完成"，而是"第一个完成后逐个返回"。**

---

### 6.5 `suppress_official_stdout` 在并行模式下部分失效

**现象**：MemoryOS 官方 eval 代码的 print 输出（"调用 GPT 生成多子主题摘要..."、"动态更新：处理子主题..."等）在终端大量刷屏，约每秒一次。

**根因**：`contextlib.redirect_stdout` 通过 `with` 块在 `add()` 和 `get_answer()` 内压制 stdout，但 MemoryOS 的内部调用链（如 `dynamic_updater.bulk_evict_and_update_mid_term()` → GPT 调用 → 子主题处理）跨越多层函数，某些中间层的 print 没有被 `with` 块覆盖。10 个 worker 并发时，即便每个 worker 只有个别漏网 print，叠加后终端仍然刷屏。

**影响**：仅终端视觉，不影响实验结果。

**修复方向**：扩大 redirect_stdout 的作用域（如包裹整个 `add()` 和 `get_answer()` 调用，而不是内部局部 with），或改用 `os.dup2` 级别的 stdout 重定向。

**Q: 这些并行功能是否和 method 解耦？**
A: 是。runner 层（`_run_isolated_worker_pipeline`、`_isolated_worker`、`_split_into_chunks`）只依赖 `BaseMemorySystem` 接口的 `add()` 和 `get_answer()`。并行 pipeline 不包含任何 method 特判。新 method 接入时只需：设 `supports_shared_instance_parallelism=False` + TOML 设 `max_workers > 1`。

---

### 6.6 Rich 终端反复卡住，实验仍在运行

**现象**：实验运行中 Rich 终端进度条间歇性冻结——有时正常刷新，有时长时间不动，但后台 experiment 确实在进行（worker 线程活跃，API 调用正常）。

**观察记录**：
- 之前出现过"冻结 1 小时后恢复"（6.4）
- 之后再次出现"卡住，但实验还在进行"
- 不是同一次冻结，而是间歇性反复

**已知可能因素**（非结论，供 codex 排查）：
1. Rich `Live`/`Progress` 后台刷新线程与主线程的 stdout 竞争
2. `ProgressReporter` 的 Rich `Progress` 对象在子线程环境中行为不稳定
3. stdout/stderr 被 `redirect_stdout` 或第三方库（openai SDK、httpx）临时占用
4. Python GIL 在密集网络 IO（API 调用）期间的调度延迟
5. `progress_enabled` 在 isolated 模式下仍然为 `True`（当前 `predict` 命令不受 `calibrate-smoke` 的 `progress_enabled` 控制），导致多个 worker 的 `ProgressReporter` 实际仍在尝试操作终端

**待排查方向**：
- 确认 isolated worker 线程内是否意外创建了 Rich 输出
- 检查 `ProgressReporter` 的 `enabled` 参数在整个调用链上是否正确传递
- 对比 `calibrate-smoke`（已禁用 child Rich）和 `predict`（未禁用）的差异
- 评估是否需要将 isolated 模式下的 progress 报告改为文件轮询（同 calibrate-smoke 的 `CalibrationProgressMonitor` 方案）

---

## 附录 A：内存压力分析

### A.1 单次 prediction run 的内存占用

| 来源 | 典型大小 | 说明 |
|------|:------:|------|
| `prediction_records` dict | ~15MB | 1540 条 × ~10KB（含 `metadata.system_prompt` 5KB） |
| `question_status` dict | ~200KB | 1540 条 × ~130B |
| `question_order` list | ~80KB | 1540 个字符串 |
| benchmark `Dataset` 对象 | ~30MB | LoCoMo 10 conversation 的全量 sessions/turns/questions |
| adapter 内部 state | variable | 见下表 |

**如果去掉 system_prompt 的重复**（6.2），`prediction_records` 从 15MB 降到 ~1MB。

### A.2 各 method 单进程内存（本地模型 + 运行数据）

| Method | 本地 embedding 模型 | 本地 LLM 压缩模型 | 单进程预估 |
|--------|:---:|:---:|:---------:|
| Mem0 | 无（API） | 无 | ~100MB |
| MemoryOS | all-MiniLM-L6-v2 (~90MB) | 无 | ~300MB |
| A-Mem | all-MiniLM-L6-v2 (~90MB) | 无 | ~300MB |
| LightMem | all-MiniLM-L6-v2 (~90MB) | llmlingua-2-bert (~350MB) | ~600MB |

### A.3 并行场景总内存估算

| 场景 | 进程数 | 单进程内存 | 总内存 |
|------|:-----:|:------:|:-----:|
| 单 method 全量（如 MemoryOS × LoCoMo） | 1 进程 × 10 worker 线程 | ~300MB | **~300MB** |
| calibrate-smoke（4 method × 1 benchmark） | 1 进程 × 4 worker 线程 | ~500MB（混合） | **~500MB** |
| 4 method × 2 benchmark 全量（各自独立启动） | 8 进程 | 100–600MB | **~2–3GB** |

**结论**：16GB 机器完全够。最重的 LightMem 也就 600MB 单进程。

### A.4 大 benchmark 风险点（供 codex 参考）

当前架构有两个隐含假设，在 **万级 question** 的 benchmark 下会成为瓶颈：

**风险 1：`prediction_records` 全量 dict**
- 当前：所有 question 答案在内存中维护全量 dict，每次写入都全量序列化
- 万级 question × 每条约 1KB（去除 system_prompt 后）≈ 10MB，仍然可控
- 十万级 × 1KB ≈ 100MB，开始有压力
- 应对：改成增量 append 写 JSONL，dict 只维护 `completed_question_ids` set

**风险 2：`question_order` 全量列表**
- 当前：启动时构建完整的 question_order 列表
- 万级 question 无压力（~500KB），十万级（~5MB）也可接受
- 应对：超过阈值时改用 generator

**风险 3：benchmark `Dataset` 全量加载**
- 当前：benchmark adapter 把整个 dataset（所有 conversation 的 sessions/turns）加载到内存
- LongMemEval-M 已用 `ijson` 流式加载（Phase F 成果），避免一次性全量
- LoCoMo 数据量小（10 conversation），全量加载无问题
- 应对：大 benchmark 必须用流式 adapter，继承 LongMemEval 的 `ijson` 模式

**风险 4：多个方法同时跑 + 本地模型重复加载**
- 当前：每个进程独立加载自己的 embedding 模型
- LightMem 最重（all-MiniLM + llmlingua ≈ 450MB 模型）
- 4 method 同时跑 ≈ 450MB × 4 = 1.8GB 仅模型
- 应对：后续可考虑进程间共享模型（如通过 mmap 或独立模型服务进程）

**建议**：当前 LoCoMo/LongMemEval 规模下无需改动。引入新 benchmark 时若单次 run 超 5000 question，需要逐项评估以上四点。

---

## 附录 B：LoCoMo F1 各类别汇总缺失问题

### B.1 现状

`evaluate --metric locomo-f1` 只生成两个文件：
- `summary.locomo_f1.json` — 仅总 F1 + correct_count，**无类别细分**
- `answer_scores.locomo_f1.jsonl` — 逐题明细含 `details.category`，但无聚合

各类别 F1 需要手动从 `answer_scores.locomo_f1.jsonl` 聚合。

### B.2 LoCoMo 类别定义

| Category | 名称 | 说明 |
|:--------:|------|------|
| 1 | Multi-hop (多跳推理) | 需要跨多个 session 组合信息。逗号分隔多项答案，F1 按子答案分别计算后取平均 |
| 2 | Temporal (时间推理) | 需要理解 session 日期、事件时序 |
| 3 | Open-domain / Commonsense (开放域) | 需要外部知识，对话本身信息不足。Gold 中分号后的部分不参与评分 |
| 4 | Single-hop (单跳) | 单次 session 内可找到答案，最简单 |
| 5 | Adversarial (对抗/不可回答) | 故意引导模型编造答案，正确行为是拒绝回答。被 adapter 跳过（需要 gold answer 违反 public-input 规则） |

参考：`docs/dataset_structures/locomo.md:271-307`，`third_party/benchmarks/locomo-main/locomo.md:241-325`，`third_party/benchmarks/locomo-main/task_eval/evaluation.py:203-224`

### B.3 MemoryOS-LoCoMo 全量各类别结果

**手动聚合自** `answer_scores.locomo_f1.jsonl`，已保存到 `summaries/summary.locomo_f1_categories.json`：

| Category | Questions | F1 | Accuracy |
|:--------:|:---------:|:-----:|:--------:|
| 1 (Multi-hop) | 282 | **0.352** | 11.0% |
| 2 (Temporal) | 321 | **0.433** | 17.1% |
| 3 (Open-domain) | 96 | **0.301** | 20.8% |
| 4 (Single-hop) | 841 | **0.491** | 29.7% |
| **Total** | **1540** | **0.442** | **23.1%** |

### B.4 待实现功能（供 codex）

`evaluate` 命令需自动输出各类别聚合结果到 `summary.{metric}_categories.json`（或合并进 `summary.{metric}.json`），不应让用户手动计算。

### B.5 `correct_count` 的含义

`is_correct` 只在 normalized prediction 与 normalized gold **完全匹配**（token 级 F1=1.0）时为 true。对于计算平均 F1 毫无意义——F1 是连续值 0~1，不是二分类。建议 `summary.locomo_f1.json` 去掉 `correct_count` 字段，或改名为 `perfect_match_count` 并加说明。
