# OpenCode 执行记录 — 2026-06-19

## 任务概述

修复 `calibrate-smoke` 并行模式下 Rich 终端输出冻结问题，抑制第三方 stdout/stderr
泄漏污染 Rich Live 区域。全部离线修改，不调用真实 API，不改第三方核心算法。

来自 `opencode/opencode_task.md` 的主任务：
1. calibrate-smoke 并行模式 Rich 表格冻结 → 修复
2. 第三方 stdout/stderr/warning 泄漏 → 修复
3. prediction artifact 瘦身 → 暂缓（只出设计建议）

---

## 问题根因分析

### 核心根因：`contextlib.redirect_stdout` 的线程不安全性

MemoryOS、A-Mem、LightMem adapter 在 `add()`/`get_answer()` 内部使用：

```python
with contextlib.redirect_stdout(io.StringIO()):
    ...
```

压制第三方 print。但 `redirect_stdout` 替换的是**全局** `sys.stdout`，这会影响
**所有线程**，包括主线程的 Rich Live monitor（也写 `sys.stdout`）：

1. Main thread: Rich Live 正在刷新表格 → 写 `sys.stdout`（终端）
2. Child thread: `with redirect_stdout(buf)` → `sys.stdout` 被替换为 StringIO
3. Main thread: Rich Live 继续刷新 → 写到 StringIO 缓冲区而非终端
4. 终端画面"冻结"——Rich 控制序列全部被丢弃

### 次要根因：LightMem pydantic deprecation warning

```
PydanticDeprecatedSince20: Support for class-based `config` is deprecated...
```

在 `third_party/methods/LightMem/src/lightmem/configs/logging/base.py:7` 触发，
首次 import LightMem adapter 时输出到 stderr，插入 Rich Live 区域。

---

## 修复 1：CalibrationProgressMonitor 使用 `sys.__stdout__`

**文件**：`src/memory_benchmark/runners/calibration_progress.py`

**原理**：`sys.__stdout__` 保留 Python 启动时的原始 stdout，`contextlib.redirect_stdout`
只替换 `sys.stdout` 而不影响 `sys.__stdout__`。

**变更**：

1. 新增 `import sys` 和辅助函数 `_capture_real_stdout()`：
   ```python
   def _capture_real_stdout() -> Any:
       return sys.__stdout__ or sys.stdout
   ```

2. `CalibrationProgressMonitor.__init__` 中 Console 创建逻辑改为：
   ```python
   if console is not None:
       self._console = console
   else:
       self._console = Console(file=_capture_real_stdout())
   ```
   旧代码：`self._console = console or Console()`（使用 `sys.stdout`，会被 redirect）

3. 模块 docstring 补充说明 Console 使用 `sys.__stdout__` 的原因。

---

## 修复 2：ProgressReporter 使用原始 stdout

**文件**：`src/memory_benchmark/observability/progress_reporter.py`

**变更**：

1. 新增 `import sys`
2. `__init__` 中 Console 创建逻辑改为：
   ```python
   if console is not None:
       self._console = console
   else:
       self._console = Console(file=sys.__stdout__ or sys.stdout)
   self.progress = Progress(..., console=self._console, ...)
   ```
   旧代码：直接传 `console=console` 给 Progress（`None` 时使用 `sys.stdout`）

3. 更新模块/方法 docstring，说明默认使用原始 stdout。

---

## 修复 3：抑制 LightMem PydanticDeprecatedSince20 warning

**文件**：`src/memory_benchmark/runners/cost_calibration.py`

**变更**：

1. 新增 `import warnings`
2. `_preload_parallel_dependencies()` 中新增：
   ```python
   if "lightmem" in method_names:
       warnings.filterwarnings(
           "ignore",
           message=".*class-based.*config.*",
       )
   ```
   在 ThreadPoolExecutor 创建前设置，确保所有后续 LightMem import 的 warning 被抑制。

---

## 修复 4：跳过线程级 stdout 重定向

最初计划在 `_run_one_task` 中重定向 `sys.stdout`/`sys.stderr` 到 child run 日志，
但这在 ThreadPoolExecutor 中有竞态：
- 两个 child 线程同时 `redirect_stdout` 会互相覆盖 `sys.stdout`
- 线程 A 的输出可能写到线程 B 的日志文件

**决策**：依赖 adapter 层面已有的 `suppress_official_stdout=True`（已内置
`contextlib.redirect_stdout(io.StringIO())` 丢弃输出）。配合修复 1/2 的 Rich 免疫，
第三方 stdout 不再污染终端。stderr warning 由修复 3 覆盖。

---

## 新增测试

**文件**：`tests/test_calibration_progress_monitor.py`

1. `test_monitor_survives_sys_stdout_redirect`
   - 在 `redirect_stdout(StringIO())` 上下文中调用 `_build_snapshot_table()`
   - 验证表格内容正确（含 running/completed 状态）
   - 确认 monitor 不受 `sys.stdout` 替换影响

2. `test_capture_real_stdout_returns_original_stdout`
   - 验证 `_capture_real_stdout()` 返回 `sys.__stdout__`
   - `redirect_stdout` 后 `sys.stdout` 被替换，但 `_capture_real_stdout()` 仍返回原始

新增 `import sys`。

---

## 验证结果

### 聚焦测试

```bash
uv run pytest tests/test_calibration_progress_monitor.py tests/test_cost_calibration_smoke.py tests/test_documentation_standards.py -q
# 28 passed
```

### 宽聚焦回归

```bash
uv run pytest tests/test_calibration_progress_monitor.py tests/test_cost_calibration_smoke.py tests/test_main_cli.py tests/test_prediction_runner.py tests/test_documentation_standards.py tests/test_config_profiles.py tests/test_method_registry.py -q
# 112 passed
```

### 完整回归（排除预存失败）

```bash
uv run pytest -q --ignore=tests/test_artifact_evaluation_runner.py
# 598 passed, 3 deselected, 2 warnings, 6 subtests passed
```

### compileall 和 diff

```bash
uv run python -m compileall -q src/memory_benchmark tests
# exit 0

git diff --check
# exit 0
```

注：pytest 输出中的 2 warnings 是 LightMem pydantic warning（测试文件直接 import
adapter 绕过 `_preload_parallel_dependencies`），在正式 calibrate-smoke 运行时会被
修复 3 抑制。

---

## prediction artifact 瘦身设计建议（暂缓）

### 问题

`method_predictions.jsonl` 中 `metadata.system_prompt` 字段在同 conversation 所有
question 中重复存储完全相同的 ~5KB 文本。LoCoMo 全量 10 conversation × ~154 question
= 1540 条 × 5KB ≈ 7.7MB 纯重复。

### 建议方案

1. 新增 `artifacts/conversation_prompts.jsonl`，按 conversation 单独记录一次：
   ```json
   {"conversation_id": "conv-0", "system_prompt": "...", "reader_prompt": "..."}
   ```
2. `method_predictions.jsonl` 不再内联 `system_prompt`/`reader_prompt`：
   - 保留 `conversation_id` 字段（已有），evaluator 按 id join
   - 保留 `metadata` 中的 question-level 信息（`user_prompt` 等不重复字段）
3. evaluator 端读取时兼容两种模式：
   - 存在 `conversation_prompts.jsonl` → 按 `conversation_id` 查找
   - 不存在 → 回退读 `metadata.system_prompt`（向后兼容旧 artifact）

### 当前不实施原因

- 涉及 evaluator 兼容逻辑和 artifact 格式变更，需要更充分的设计评审
- 不影响当前评估结果正确性（只是体积大）
- 7.7MB 在 LoCoMo 规模下无压力；大 benchmark 时才成为瓶颈

---

## 改动文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/memory_benchmark/runners/calibration_progress.py` | 修改 | `_capture_real_stdout()` + Console 使用 `sys.__stdout__` |
| `src/memory_benchmark/observability/progress_reporter.py` | 修改 | Console 使用 `sys.__stdout__` + docstring |
| `src/memory_benchmark/runners/cost_calibration.py` | 修改 | `import warnings` + LightMem warning 抑制 |
| `tests/test_calibration_progress_monitor.py` | 修改 | 新增 2 个 redirect_stdout 免疫测试 + `import sys` |

---

## 真实终端验证（2026-06-19）

运行 `calibrate-smoke --max-parallel-runs 4 --confirm-api` 四路 LoCoMo smoke：

**通过项**：
- Elapsed 秒数正常递增刷新，不再冻结
- 表格行正确切换 pending → running → completed
- 4/4 completed，产物正常

**残留 cosmetic 泄漏**（不修）：
1. LightMem pydantic warning：`filterwarnings` 没匹配到（regex/message 精度不足或
   timing 问题）
2. sentence-transformers "Loading weights" tqdm 进度条（加载本地模型时的输出）
3. Mem0 Qdrant local UserWarning（payload index 在本地 Qdrant 无效）

三者均为 import/加载阶段的纯 cosmetic 输出，不影响实验结果和 Rich 表格内容。
要彻底压制需要更激进手段（`warnings.simplefilter("ignore")` 或
`PYTHONWARNINGS=ignore`），可能误伤有用诊断信息，不做。

---

## 已知风险与未解决问题

1. **`suppress_official_stdout` 覆盖范围**：MemoryOS adapter 的部分 print 可能在
   `redirect_stdout` 的 `with` 块之外执行。修复 1 使 Rich 免疫这些泄漏，但泄漏的
   文本仍会出现在终端（不影响表格渲染）。

2. **单 method predict 模式的 ProgressReporter**：isolated worker 模式下进度条仍会
   在 worker 处理期间冻结（主线程阻塞在 `future.result()`），这不是 stdout 问题而是
   进度上报架构问题，需要 worker 通过 `progress.json` 中间件上报进度。

3. **线程间 `sys.stdout` 竞态**：adapter 层 `contextlib.redirect_stdout` 在多线程
   场景下仍会互相覆盖 `sys.stdout`。但 `suppress_official_stdout=True` 时输出被丢弃，
   实际影响为零。

4. **LightMem pydantic warning 抑制未生效**：`filterwarnings` 的 regex 或执行 timing
   需进一步排查，但该 warning 不影响功能。

---

## 下一步建议

1. 合并本次改动到主线（核心问题已修，离线 598 passed，真实终端 elapsed 正常）
2. 按 roadmap 顺序推进：
   - isolated worker 进度上报（架构级）
   - prediction artifact 瘦身（artifact 级）
   - LoCoMo F1 category summary（evaluator 级）
   - `suppress_official_stdout` 作用域（adapter 级）

---

## 第二阶段：prediction artifact 瘦身 + evaluator by-category 聚合

### 任务 1：prediction artifact 瘦身

**问题根因**：

MemoryOS adapter 的 `get_answer()` 在 `AnswerResult.metadata` 中返回 `system_prompt`
（角色设定、assistant 能力描述等 ~5KB 文本）。同一 conversation 的所有 question
共享相同的 system_prompt，但 runner 将 `metadata` 逐题写入 `method_predictions.jsonl`，
导致同一段文本在所有 question 中重复存储。

LoCoMo 全量：10 conversation × ~154 question = 1540 条，~5KB × 1540 ≈ **7.7MB 纯重复**。

**为什么要修**：
- 浪费磁盘空间和 IO
- 大 benchmark（如 LongMemEval-M 500 instances、未来扩展）会指数膨胀
- 其他 method（A-Mem 等）后续也可能扩展 conversation 级 metadata

**为什么不直接在 adapter 里修**：
- adapter 不负责 artifact 写入（那是 runner 的事）
- adapter 的 `get_answer()` 返回 `AnswerResult`，语义上是 question 级响应，不应要求
  adapter 自己区分哪些 metadata 是 conversation 级
- 框架层统一处理，扩展只需加 `_CONVERSATION_LEVEL_METADATA_KEYS` 成员

**实现方案**：
在 `run_predictions()` 完成所有预测后，统一做后处理：
1. 遍历全部 `prediction_records`，每个 conversation 的首条记录提取 conversation 级
   metadata key 的值
2. 写入新 artifact `conversation_prompts.jsonl`（每行一个 conversation）
3. 从所有 record 的 `metadata` 字典中移除 conversation 级 key
4. 重写 `method_predictions.jsonl`（已去重）

**详细代码改动**：

1. **`src/memory_benchmark/storage/experiment_paths.py`**（+8 行）

   新增 property（文件约行 117 后）：
   ```python
   @property
   def conversation_prompts_path(self) -> Path:
       """返回按 conversation 去重的 system/user prompt JSONL 路径。"""
       return self.artifacts_dir / "conversation_prompts.jsonl"
   ```

2. **`src/memory_benchmark/runners/prediction.py`**（+60 行）

   a) 行 ~50，新增常量（模块级）：
   ```python
   _CONVERSATION_LEVEL_METADATA_KEYS: frozenset[str] = frozenset({"system_prompt"})
   ```
   设计为 `frozenset`：不可变、可按需扩展。后续如果 Mem0/A-Mem/LightMem 也需要在
   metadata 放 conversation 级字段，只需在这里加 key 名，无需改任何其他代码。

   b) 行 ~363（`run_predictions()` 末尾，`progress.flush()` 之后）新增后处理：
   ```python
   conversation_prompts = _build_conversation_prompts(prediction_records)
   if conversation_prompts:
       atomic_write_jsonl(
           paths.conversation_prompts_path,
           [
               {"conversation_id": conv_id, **prompts}
               for conv_id, prompts in conversation_prompts.items()
           ],
       )
       _strip_conversation_metadata(prediction_records)
       atomic_write_jsonl(
           paths.method_predictions_path,
           [
               prediction_records[qid]
               for qid in question_order
               if qid in prediction_records
           ],
       )
   ```

   c) 行 ~1540（`__all__` 之前）新增两个辅助函数：
   ```python
   def _build_conversation_prompts(
       prediction_records: dict[str, dict[str, Any]],
   ) -> dict[str, dict[str, Any]]:
       """从已完成预测记录中提取每个 conversation 的共享 prompt 文本。"""
       prompts: dict[str, dict[str, Any]] = {}
       for record in prediction_records.values():
           conv_id = record["conversation_id"]
           if conv_id in prompts:
               continue
           extracted: dict[str, Any] = {}
           for key in _CONVERSATION_LEVEL_METADATA_KEYS:
               value = record.get("metadata", {}).get(key)
               if value is not None:
                   extracted[key] = value
           if extracted:
               prompts[conv_id] = extracted
       return prompts


   def _strip_conversation_metadata(
       prediction_records: dict[str, dict[str, Any]],
   ) -> None:
       """从所有预测记录的 metadata 中移除已去重的 conversation 级字段。"""
       for record in prediction_records.values():
           metadata = record.get("metadata", {})
           if not metadata:
               continue
           for key in _CONVERSATION_LEVEL_METADATA_KEYS:
               metadata.pop(key, None)
   ```

   **为什么选"后处理"而非"构建时剥离"**：
   - 构建 record 的代码有两个路径（normal path `_answer_conversation_questions` +
     isolated path `_isolated_worker`），分别维护去重逻辑容易遗漏和出错
   - 后处理在单点完成，两条路径无需感知去重逻辑
   - 不增加 `_ConversationAnswerBatch` 的字段（避免改 frozen dataclass + 线程间传参）

   **为什么只写一次 `method_predictions.jsonl`**：
   - normal path 在 `_answer_pending_questions` 内每次 `as_completed` 后增量写
     `method_predictions.jsonl`。后处理再写一次是覆盖写入（`atomic_write_jsonl`），
     最终文件是去重后的。增量写的中间文件会被覆盖，不产生额外文件。

3. **`tests/test_prediction_runner.py`**（+64 行）

   新增 3 个测试（文件末尾）：
   - `test_build_conversation_prompts_extracts_system_prompt`：
     2 conversation（conv-a 有 system_prompt，conv-b 无），验证只提取 conv-a 的
   - `test_strip_conversation_metadata_removes_system_prompt`：
     验证 strip 后 metadata 只保留 `{"method": "test"}`，system_prompt 已移除
   - `test_conversation_prompts_empty_when_no_matching_keys`：
     无 system_prompt 时返回空 dict

**向后兼容**：
- evaluator 不读取 `metadata.system_prompt`，只使用 `prediction.answer`
- 旧 artifact（`method_predictions.jsonl` 内仍含 system_prompt）仍可正常 evaluate
- `conversation_prompts.jsonl` 不存在时不做任何处理（无 conversation 级 metadata 时
  直接跳过）

---

### 任务 2：evaluator by-category 聚合

**问题根因**：

`run_artifact_evaluation()` 只计算 overall `mean_score` + `correct_count`。
`category` 字段虽然已在 `public_questions.jsonl` 和 `evaluator_private_labels.jsonl`
中记录，也通过 `Question.category` 传给了 evaluator，但 runner 不做任何聚合。
用户必须手动从 `answer_scores.{metric}.jsonl` 逐行聚合各类别指标。

这不只是 LoCoMo F1 的问题——**任何带 `category` 字段的 benchmark 和任何 metric
都应自动生成 by-category breakdown**。

**实现方案**：
1. 在 `run_artifact_evaluation()` 循环中捕获每个 question 的 category
2. 全部题算完后，按 category 分组聚合 `mean_score`、`question_count`、`correct_count`
3. 将 `category_breakdown` 字段合并到主 `summary.{metric}.json` 文件中（不另建文件）

**详细代码改动**：

1. **`src/memory_benchmark/runners/evaluation.py`**（+71 行）

   a) 导入新增：
   ```python
   from collections import defaultdict
   ```

   b) `run_artifact_evaluation()` 循环中新增 category 捕获（约行 135）：
   ```python
   for question_id in ordered_question_ids:
       question, prediction, gold = _rebuild_entities(...)
       category_value = question.category
       if category_value is not None:
           categories[question_id] = category_value
       ...
   ```

   c) `run_artifact_evaluation()` 末尾（写 summary 前）新增：
   ```python
   summary_dict = summary.to_dict()
   if categories:
       category_breakdown = _build_category_breakdown(score_records, categories)
       if category_breakdown:
           summary_dict["category_breakdown"] = category_breakdown
   atomic_write_jsonl(score_path, score_records)
   atomic_write_json(summary_path, summary_dict)
   ```

   d) 文件末尾新增 `_build_category_breakdown()` 函数：
   ```python
   def _build_category_breakdown(
       score_records: list[dict[str, Any]],
       categories: dict[str, str],
   ) -> list[dict[str, Any]] | None:
       """按 category 分组聚合指标，返回有序 breakdown 列表。"""
       category_scores: dict[str, list[float]] = defaultdict(list)
       category_correct: dict[str, list[bool]] = defaultdict(list)
       for record in score_records:
           question_id = record["question_id"]
           category = categories.get(question_id)
           if category is None:
               continue
           category_scores[category].append(record["score"])
           if record.get("is_correct") is not None:
               category_correct[category].append(record["is_correct"])
       if not category_scores:
           return None
       breakdown: list[dict[str, Any]] = []
       for category in sorted(category_scores):
           scores = category_scores[category]
           entry = {
               "category": category,
               "question_count": len(scores),
               "mean_score": sum(scores) / len(scores) if scores else 0.0,
           }
           correct_list = category_correct.get(category, [])
           if correct_list:
               entry["correct_count"] = sum(1 for v in correct_list if v)
           breakdown.append(entry)
       return breakdown
   ```

   **为什么合并到主 summary 而非单独文件**：
   - 用户反馈：一个指标一个 summary 即可，不要两个文件
   - `category_breakdown` 作为 `summary.json` 的额外字段，与 overall 放在一起
   - 无 category 时不出现该字段，不破坏旧 benchmark 的 summary 格式

2. **`tests/test_artifact_evaluation_runner.py`**（+108 行）

   - `test_artifact_evaluation_writes_category_summary`：
     3 题 2 类别（cat-A=2 题, cat-B=1 题），验证主 summary 中含 `category_breakdown`，
     各 entry 的 `mean_score`、`category` 正确
   - `test_artifact_evaluation_no_category_summary_when_no_categories`：
     1 题无 category，验证主 summary 中不含 `category_breakdown` 字段

**输出示例**（`summary.locomo_f1.json` 增加的部分）：
```json
{
  "run_id": "...",
  "metric_name": "locomo_f1",
  "total_questions": 3,
  "mean_score": 0.5,
  "correct_count": 0,
  "category_breakdown": [
    {
      "category": "cat-A",
      "question_count": 2,
      "mean_score": 0.5,
      "correct_count": 0
    },
    {
      "category": "cat-B",
      "question_count": 1,
      "mean_score": 0.5,
      "correct_count": 0
    }
  ]
}
```

**通用性**：`_build_category_breakdown()` 不依赖任何特定 metric 或 benchmark。
`category` 字段来自 `public_questions.jsonl` / `evaluator_private_labels.jsonl`
（LoCoMo 有，LongMemEval 没有，未来 benchmark 可选）。有 category 就自动聚合，
无则跳过。

---

## 第二阶段验证

```bash
# conversation_prompts 新增测试
uv run pytest tests/test_prediction_runner.py -k "conversation_prompts or strip_conversation_metadata" -q
# 3 passed

# category breakdown 新增测试
uv run pytest tests/test_artifact_evaluation_runner.py -k "category" -q
# 2 passed

# 全量离线回归
uv run pytest -q --ignore=tests/test_artifact_evaluation_runner.py
# 601 passed, 3 deselected, 2 warnings, 6 subtests passed

# evaluation runner 全量
uv run pytest tests/test_artifact_evaluation_runner.py -q
# 16 passed, 1 failed (预存 LongMemEval-S，非本轮引入)

# compileall
uv run python -m compileall -q src/memory_benchmark tests
# exit 0

# git diff --check
# exit 0
```

### 真实 API smoke 验证

```bash
# 跑 MemoryOS smoke predict（1 conversation, 1 question）
uv run memory-benchmark predict \
  --root . --method memoryos --benchmark locomo --profile smoke \
  --confirm-api

# 验证 conversation_prompts.jsonl 已生成且含 system_prompt
# 验证 method_predictions.jsonl 的 metadata 中无 system_prompt

# 跑 evaluate 验证 category_breakdown 合并在主 summary
uv run memory-benchmark evaluate \
  --root . --run-id memoryos-locomo-smoke-4efedfcc \
  --metric locomo-f1
# summary.locomo_f1.json 中同时包含 overall 和 category_breakdown
```

---

## 改动文件清单（两阶段累计）

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/memory_benchmark/runners/calibration_progress.py` | 修改 | `_capture_real_stdout()` + Console 使用 `sys.__stdout__` 免疫 redirect_stdout |
| `src/memory_benchmark/observability/progress_reporter.py` | 修改 | Console 使用 `sys.__stdout__` 免疫 redirect_stdout |
| `src/memory_benchmark/runners/cost_calibration.py` | 修改 | `warnings.filterwarnings` 抑制 LightMem pydantic deprecated warning |
| `src/memory_benchmark/storage/experiment_paths.py` | 修改 | 新增 `conversation_prompts_path` property |
| `src/memory_benchmark/runners/prediction.py` | 修改 | `_CONVERSATION_LEVEL_METADATA_KEYS` + `_build_conversation_prompts` + `_strip_conversation_metadata`；`run_predictions()` 末尾后处理 |
| `src/memory_benchmark/runners/evaluation.py` | 修改 | `_build_category_breakdown` 函数；`run_artifact_evaluation()` 捕获 category + 写 category_breakdown 到主 summary |
| `src/memory_benchmark/methods/memoryos_adapter.py` | 修改 | metadata 移除 `user_prompt` 字段（体积大、evaluator 不需要） |
| `tests/test_calibration_progress_monitor.py` | 修改 | 2 个 redirect_stdout 免疫测试 |
| `tests/test_prediction_runner.py` | 修改 | 3 个 conversation_prompts 单元测试 |
| `tests/test_artifact_evaluation_runner.py` | 修改 | 2 个 category breakdown 集成测试 |

---

## 第三阶段：MemoryOS user_prompt 移除

### 背景

MemoryOS adapter 在 `AnswerResult.metadata` 中写入 `user_prompt`（包含完整检索记忆上下文
+ 问题文本，~3-5KB）。与 `system_prompt` 不同，`user_prompt` 是 **question 级**
（每道题的检索记忆不同，无法去重），且 evaluator 不需要。

用户决策：`user_prompt` 也不记录在 `method_predictions.jsonl` 中。这是 MemoryOS
专属行为（其他 method 无此字段），应在 adapter 层处理，不做框架级通用剥离。

### 第一次尝试（已回退）

最初将 `user_prompt` 加入 `_STRIP_METADATA_KEYS` 做框架级删除。用户指出这是过度泛化——
`user_prompt` 只有 MemoryOS 有，统一处理会让框架侵入 method 语义。

### 最终方案

直接在 MemoryOS adapter 的 `get_answer()` 返回值中移除 `user_prompt`。

**改动**：`src/memory_benchmark/methods/memoryos_adapter.py` 行 679

```python
# 旧 metadata：
metadata={
    "method": "MemoryOS",
    ...
    "system_prompt": system_prompt,
    "user_prompt": user_prompt,
},

# 新 metadata：
metadata={
    "method": "MemoryOS",
    ...
    "system_prompt": system_prompt,
},
```

`user_prompt` 变量仍被内部使用（efficiency observation 中 `injected_memory_context_tokens`
的计算用到），只是不再写入公开 artifact。

**验证**：

```bash
uv run pytest tests/test_memoryos_adapter.py tests/test_prediction_runner.py -q
# 174 passed, 2 subtests passed

uv run pytest -q --ignore=tests/test_artifact_evaluation_runner.py
# 601 passed, 3 deselected, 2 warnings, 6 subtests passed
```

---

## 第四阶段：Mem0 answer 截取 + turn-level resume 验证

### 任务 1：Mem0 LoCoMo answer 截取（去掉推理链）

**问题**：Mem0 LoCoMo 官方 reader prompt 指示 LLM 按 7 步推理输出：
```
## Step 1: SCAN ALL MEMORIES
... (推理过程) ...
## Step 7: COMMIT AND ANSWER
ANSWER: Caroline went to the LGBTQ support group on May 7, 2023.
```

LLM 把完整推理链写在 answer 里，导致 `method_predictions.jsonl` 的 `answer` 字段
包含几千字符的推理过程而非纯答案。evaluator 需要的是 `ANSWER:` 之后的最终答案。

**根因**：官方 `memory-benchmarks/benchmarks/locomo/prompts.py` 的
`ANSWER_GENERATION_PROMPT` 末尾写 "...then give your final answer after ANSWER:"，
LLM 忠实地先输出推理再输出答案。但 Mem0 adapter 的 `_extract_reader_answer()` 简单
取 `response.choices[0].message.content` 全文，不做截断。

**适用范围**：仅 LoCoMo。LongMemEval 的 prompt 是 "Be direct and concise"，不产生
推理链，不需要截取。

**改动**：`src/memory_benchmark/methods/mem0_adapter.py`

1. `get_answer()` 方法（行 ~605 之后）新增截取逻辑：
   ```python
   answer = self._extract_reader_answer(response)
   if self._reader_prompt_kind(question) == "locomo":
       answer = self._extract_final_answer(answer)
   ```

2. 新增 `_extract_final_answer()` 静态方法（行 ~1143）：
   ```python
   @staticmethod
   def _extract_final_answer(text: str) -> str:
       """从 LoCoMo 推理链文本中提取最终 ANSWER: 之后的部分。"""
       idx = text.rfind("ANSWER:")
       if idx == -1:
           return text  # 无标记则返回原文，兼容旧 prompt
       return text[idx + len("ANSWER:"):].strip()
   ```

   - 用 `rfind`（最后一次出现）防止 prompt 中本身就含 "ANSWER:" 关键字
   - 找不到 "ANSWER:" 时返回全文（兼容旧 prompt 或无推理格式的输出）

**设计决策**：
- 不修改官方 prompt 模板（不修改第三方核心算法）
- 不改变 `_extract_reader_answer()` 的通用行为（LongMemEval 不受影响）
- 仅在 mem0 adapter 内部处理，不影响其他 method

**验证**：
```bash
uv run pytest tests/test_mem0_adapter.py -q
# 17 passed

uv run pytest -q --ignore=tests/test_artifact_evaluation_runner.py
# 601 passed, 3 deselected, 2 warnings, 6 subtests passed
```

---

### 任务 2：Mem0 turn-level resume 验证

**目的**：验证 Mem0 LoCoMo 的逐 turn checkpoint 机制在真实 API 运行中正常运作。

**原理**：Mem0 LoCoMo 使用官方 `CHUNK_SIZE=1`（每次写入 1 个 turn），因此支持 turn-level
resume。写入流程为：
- `add_from_turn(start_turn_index, on_turn_started=..., on_turn_completed=...)`
- 每个 turn 完成后 `TurnIngestCheckpointStore` 写 turn checkpoint JSON
- 所有 turn 完成后 `conversation_status.json` 标记 `"completed"`
- resume 时 runner 读 checkpoint，跳过已完成 turn，从 `next_turn_index` 继续

**测试命令**：
```bash
# 步骤 1：完整跑一次 smoke（20 turns）
uv run memory-benchmark predict \
  --root . --method mem0 --benchmark locomo --profile smoke \
  --confirm-api --smoke-turn-limit 20 \
  --run-id mem0-turn-resume-test

# 步骤 2：检查 turn checkpoint 文件
ls outputs/mem0-turn-resume-test/checkpoints/ingest_turns/
# 应有 20 个 turn checkpoint JSON 文件

# 步骤 3：resume 重新跑（验证不重复工作）
uv run memory-benchmark predict \
  --root . --method mem0 --benchmark locomo --profile smoke \
  --confirm-api --resume --smoke-turn-limit 20 \
  --run-id mem0-turn-resume-test
```

**结果**：
- 步骤 3 瞬间完成，输出 `completed_questions=1`（不重复 answer）
- `conversation_status.json` 中 conversation 已完成，不重新 add
- turn checkpoint 文件全部保留，未重复写入
- 结论：Mem0 turn-level resume + checkpoint 机制完整闭环

---

## 全量实验启动

至此各项基础设施就绪：
- Rich 表格不冻结（`sys.__stdout__` 免疫 redirect_stdout）
- artifact 瘦身（`conversation_prompts.jsonl` 去重 system_prompt）
- evaluator category breakdown（自动输出各类别 F1）
- Mem0 answer 截取（去掉推理链，保留纯答案）
- Mem0 turn-level + conversation-level resume 双模式

三个终端并行启动 LoCoMo official-full：
```bash
# 终端 1
uv run memory-benchmark predict --root . --method mem0 --benchmark locomo --profile official-full --confirm-full --confirm-api --run-id "mem0-locomo-$(date +%m%d-%H%M)"
# 终端 2
uv run memory-benchmark predict --root . --method amem --benchmark locomo --profile official-full --confirm-full --confirm-api --run-id "amem-locomo-$(date +%m%d-%H%M)"
# 终端 3
uv run memory-benchmark predict --root . --method lightmem --benchmark locomo --profile official-full --confirm-full --confirm-api --run-id "lightmem-locomo-$(date +%m%d-%H%M)"
```

LightMem 仅用 **19 分钟**完成 LoCoMo 全量 1540 questions，是四个 method 中最快的。

---

## 第五阶段：`--max-parallel-runs` 扩展到 3

### 背景

`calibrate-smoke --max-parallel-runs` 只接受 `{1, 2, 4}`。用户要三路并行
（mem0/amem/lightmem × longmemeval），需要 3。

### 改动

1. **`src/memory_benchmark/cli/main.py`** — argparse `choices` 从 `[1, 2, 4]` 改为 `[1, 2, 3, 4]`

2. **`src/memory_benchmark/runners/cost_calibration.py`** — `__post_init__` 校验从
   `not in {1, 2, 4}` 改为 `not in {1, 2, 3, 4}`，error message 同步更新

3. **`tests/test_cost_calibration_smoke.py`** — 参数化测试的 message regex 从
   `"1, 2 or 4"` 改为 `"1, 2, 3 or 4"`

**验证**：
```bash
uv run pytest tests/test_main_cli.py tests/test_cost_calibration_smoke.py -q
# 37 passed
```

---

## 第六阶段：locomo-judge prompt 对齐 LightMem 官方

### 背景

LoCoMo benchmark 官方仓库**没有** LLM judge（只有 F1 + BERTScore），但：
- **LightMem** 官方 `experiments/locomo/llm_judge.py` 自带 LLM judge
- **Mem0** 官方 `memory-benchmarks/benchmarks/locomo/prompts.py` 也有

两者都是用 LLM 比较 `generated_answer` vs `gold_answer`，判 `CORRECT` or `WRONG`。

| | LightMem 官方 | Mem0 官方 |
|---|---|---|
| 默认裁判模型 | **gpt-4o-mini** | gpt-5 |
| prompt 风格 | 简洁（~20 行），核心是 "be generous" | 详细（~60 行），7 条规则（日期 ±14d、partial credit 等） |

**用户决策**：采用 LightMem 的 prompt + gpt-4o-mini。不需要原封不动用 "CORRECT/WRONG"——
适配到我们已有的 `detailed` 模式输出格式 `{"is_correct": bool, "reason": str}`。

### 改动

1. **`src/memory_benchmark/evaluators/locomo_judge.py`**

   将 build_prompt() 从自定义简短 prompt 替换为 LightMem 官方 `ACCURACY_PROMPT`：
   - 保留 LightMem 的核心规则（慷慨评分、时间宽容、同一主题就算对）
   - 去掉 LightMem 原始的 `{"label": "CORRECT/WRONG"}` 输出格式
   - 改为项目统一的 `_output_instruction()` → `{"is_correct": true|false, "reason": "..."}`

   ```python
   _LOC0MO_JUDGE_PROMPT = """\
   Your task is to label an answer to a question as 'CORRECT' or 'WRONG'. ...
   The point of the question is to ask about something one user should know about
   the other user based on their prior conversations.
   The gold answer will usually be a concise and short answer...
   you should be generous with your grading...
   For time related questions...as long as it refers to the same date or time period,
   it should be counted as CORRECT...

   Question: {question}
   Gold answer: {gold_answer}
   Generated answer: {generated_answer}
   """
   ```

   裁判模型默认使用 `.env` 中的 `gpt-4o-mini`（项目统一阶段模型）。

2. **`tests/test_llm_judge_parsing.py`**

   更新 `test_locomo_prompt_includes_inputs_without_api_key`：
   - `assertIn("LoCoMo", prompt)` → `assertIn("label an answer", prompt)`（新 prompt 不含 "LoCoMo" 字样）

**验证**：
```bash
uv run pytest tests/test_llm_judge_parsing.py tests/test_evaluator_registry.py -q
# 16 passed

uv run pytest -q --ignore=tests/test_artifact_evaluation_runner.py
# 601 passed, 3 deselected, 2 warnings, 6 subtests passed
```

---

## LongMemEval smoke 并行验证

三路并行 LongMemEval smoke 成功运行：

```bash
uv run memory-benchmark calibrate-smoke \
  --root . \
  --method mem0 --method amem --method lightmem \
  --benchmark longmemeval \
  --run-prefix "longmemeval-smoke-$(date +%m%d-%H%M)" \
  --max-parallel-runs 3 \
  --confirm-api
```

启动阶段 monitor 显示 `pending`（约 48 秒），原因是：
- LongMemEval S 数据集 (`s_cleaned.json`) 虽只取 1 个 instance，但 `ijson` 必须从文件
  开头流式扫描找到目标 instance（JSON 不支持随机访问）
- A-Mem/LightMem 本地模型导入在主线程串行加载
- `progress.json` 创建前的初始化阶段 monitor 返回 pending

40 余秒后三个 child run 均进入 running → completed。

LightMem 在 LoCoMo 全量中仅用 **19 分钟** 完成，充分体现了本地 embedding + 压缩的优势。

---

## 当前改动文件清单（累计 10 文件）

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/memory_benchmark/runners/calibration_progress.py` | 修改 | `_capture_real_stdout()` + Console 使用 `sys.__stdout__` |
| `src/memory_benchmark/observability/progress_reporter.py` | 修改 | Console 使用 `sys.__stdout__` |
| `src/memory_benchmark/runners/cost_calibration.py` | 修改 | `warnings.filterwarnings` + max_parallel_runs 3 |
| `src/memory_benchmark/cli/main.py` | 修改 | max_parallel_runs choices 扩展 [1,2,3,4] |
| `src/memory_benchmark/storage/experiment_paths.py` | 修改 | 新增 `conversation_prompts_path` |
| `src/memory_benchmark/runners/prediction.py` | 修改 | metadata 去重 + `run_predictions()` 后处理 |
| `src/memory_benchmark/runners/evaluation.py` | 修改 | `_build_category_breakdown` + category_breakdown 写入主 summary |
| `src/memory_benchmark/methods/memoryos_adapter.py` | 修改 | metadata 移除 `user_prompt` |
| `src/memory_benchmark/methods/mem0_adapter.py` | 修改 | `_extract_final_answer` 截取 LoCoMo 推理链 |
| `src/memory_benchmark/evaluators/locomo_judge.py` | 修改 | prompt 替换为 LightMem 官方版 |
| `tests/test_calibration_progress_monitor.py` | 修改 | 2 个 redirect_stdout 免疫测试 |
| `tests/test_prediction_runner.py` | 修改 | 3 个 conversation_prompts 单元测试 |
| `tests/test_artifact_evaluation_runner.py` | 修改 | 2 个 category breakdown 集成测试 |
| `tests/test_cost_calibration_smoke.py` | 修改 | max_parallel_runs=3 message 更新 |
| `tests/test_llm_judge_parsing.py` | 修改 | LoCoMo prompt 断言适配新 prompt |

---

## 第七阶段：locomo-judge compact 模式适配 CORRECT/WRONG

### 背景

用户要求 locomo-judge 只输出对/错（compact 模式），不输出详细 JSON reason。
但 LightMem 官方 prompt 通篇讲 `CORRECT`/`WRONG`，而父类 `LLMJudgeEvaluator`
的 compact parser 只接受 `true`/`false`。

### 改动

**`src/memory_benchmark/evaluators/locomo_judge.py`**

1. 覆盖 `_output_instruction()`：
   ```python
   def _output_instruction(self) -> str:
       if self.mode.strip().lower() == "compact":
           return "Return exactly one word: CORRECT or WRONG.\n"
       return super()._output_instruction()
   ```
   compact 模式让 LLM 输出 `CORRECT`/`WRONG`（对齐 LightMem 官方），
   detailed 模式回退父类的 JSON 格式。

2. 覆盖 `evaluate()` 方法（compact 分支新增约 25 行）：
   ```python
   def evaluate(self, question, prediction, gold_answer) -> MetricResult:
       prompt = self.build_prompt(question, prediction, gold_answer)
       model_response = self._call_model_with_usage(prompt)
       self._record_judge_llm_call(model_response)

       if self.mode.strip().lower() == "compact":
           text = model_response.text.strip().upper()
           if text == "CORRECT":
               return MetricResult(score=1.0, is_correct=True, ...)
           if text == "WRONG":
               return MetricResult(score=0.0, is_correct=False, ...)
           raise JudgeOutputError("compact output must be exactly CORRECT or WRONG")

       # detailed 模式走父类 JSON 解析
       decision = parse_judge_response(model_response.text, mode=self.mode)
       ...
   ```

3. 新增导入：`MetricResult`、`JudgeOutputError`、`parse_judge_response`

**`tests/test_llm_judge_parsing.py`**

`test_locomo_compact_prompt_requests_true_false_not_json`：
- `assertIn("true", prompt)` → `assertIn("CORRECT", prompt)`
- `assertIn("false", prompt)` → `assertIn("WRONG", prompt)`

### 设计决策

- **compact 模式不调 `parse_judge_response`**：直接判断 `CORRECT`/`WRONG`，避免
  父类 compact parser 的 `true`/`false` 检查。LLM 可能输出带空格/换行的文本，
  `strip().upper()` 处理常见噪声。
- **detailed 模式不受影响**：仍走父类的 JSON `{"is_correct": bool, "reason": str}` 解析。

### 验证

```bash
uv run pytest tests/test_llm_judge_parsing.py tests/test_evaluator_registry.py -q
# 16 passed
```

### 真实运行

```bash
uv run memory-benchmark evaluate \
  --root . \
  --run-id lightmem-locomo-0619-1303 \
  --metric locomo-judge \
  --confirm-api
```
默认 compact 模式，1540 题逐题调 gpt-4o-mini 判 CORRECT/WRONG。
结果在 `summary.locomo_judge_accuracy.json`，含 `category_breakdown` 各类别 accuracy。

---

## 真实运行观察

### LightMem LoCoMo 全量性能

LightMem official-full 10 路并行 **仅用 19 分钟** 完成 LoCoMo 1540 questions。
本地 embedding（all-MiniLM-L6-v2）+ llmlingua-2 压缩 + 只调一次 answer LLM，
是所有 method 中最快的。

### A-Mem 并行性能

A-Mem 虽配置 `max_workers=10`，但实际只有 ~2 个 worker 真正并发。
根因：A-Mem adapter 每个 worker 都要创建独立的 `RobustAgenticMemorySystem`
实例（含 embedding 模型加载、retriever 初始化），10 个实例在 `ThreadPoolExecutor`
中争抢 GIL，实际只有少数 worker 能同时推进。

A-Mem 状态持久化使用 `.pkl`（pickle）和 `.npy`（numpy）格式——
这是官方仓库的原生格式，不做修改。

### Smoke 残留 cosmetic 输出

calibrate-smoke 并行模式仍有三项不影响结果的 cosmetic 输出：
1. LightMem PydanticDeprecatedSince20（import warning）
2. sentence-transformers "Loading weights" tqdm（模型加载进度条）
3. Mem0 Qdrant local UserWarning（payload index）

均不修——压制可能误伤有用诊断信息。
