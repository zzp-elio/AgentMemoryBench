# 2026-06-05 Observability + Artifacts Handoff

## 当前任务目标

用户确认采用 Subagent-Driven 方式执行 Phase A/B:

1. 给长实验 runner 增加 Rich 终端日志、进度条、`run.log`、`events.jsonl`、`progress.json`。
2. 标准化实验产物目录，支持“跑一次 method，多次评估”。
3. 当前阶段不迁 `src-layout`，不迁 pytest，不移动第三方源码。

## 已确认设计文档

- 设计草案: `docs/superpowers/specs/2026-06-05-observability-src-layout-design.md`
- 实施计划: `docs/superpowers/plans/2026-06-05-observability-artifacts-phase-ab.md`

用户已确认:

- 采用阶段式推进: Phase A 可观测性 -> Phase B 实验产物结构 -> Phase C src-layout -> Phase D pytest。
- 后续接受把第三方源码迁到 `third_party/methods/`，`src/memory_benchmark/methods/` 只保留 wrapper。
- 允许保存 `evaluator_private_labels.jsonl`，其中包含 gold answer，但该文件只能给 evaluator，不能传入 method。
- 继续使用 `outputs/<run_id>/` 作为实验输出根目录。

## 当前执行方式

正在使用 `superpowers:subagent-driven-development`。

计划任务:

1. Task 1 RunContext/EventWriter implementation and reviews
2. Task 2 ProgressReporter implementation and reviews
3. Task 3 storage primitives implementation and reviews
4. Task 4 RunLogger upgrade and reviews
5. Task 5 runner artifact integration and reviews
6. Task 6 runner rich progress integration and reviews
7. Task 7 event coverage and reviews
8. Task 8 docs updates
9. Task 9 verification suite

当前 `update_plan` 状态:

- Task 1 已完成。
- Task 2 已完成。
- Task 3 正在进行，但因额度/上下文即将耗尽暂停在 code quality review 修复前。
- Task 4-9 pending。

## Task 1 当前状态

### Implementer subagent

- Agent id: `019e95ef-1e51-7052-b3d8-98e0b5ac9c4d`
- Nickname: Euclid
- Status: DONE

实现内容:

- 新增 `memory_benchmark/observability/__init__.py`
- 新增 `memory_benchmark/observability/run_context.py`
- 新增 `memory_benchmark/observability/event_writer.py`
- 新增 `tests/test_observability_run_context.py`

测试:

```bash
uv run python -m unittest tests/test_observability_run_context.py -v
```

最终结果: 2 tests OK。

### Spec review subagent

- Agent id: `019e95f2-a688-7d31-85b0-aa5445dd6cd3`
- Nickname: Copernicus
- Status: completed with issues

发现两个 spec compliance 问题:

1. `memory_benchmark/observability/run_context.py`
   - `RunContext.create()` 使用了 `Path(output_root).expanduser().absolute()`。
   - 计划要求 resolved path，应改为 `Path(output_root).expanduser().resolve()`。

2. `tests/test_observability_run_context.py`
   - 测试断言了 `summaries_dir` 路径，但没有断言 `summaries` 目录实际被创建。
   - 需要补 `self.assertTrue(context.summaries_dir.is_dir())`。

其它要求均已通过:

- 中文模块 docstring。
- frozen dataclass 字段。
- required directory properties。
- `method_state_dir` 创建。
- `EventWriter` parent dir 创建和 JSONL append。
- package exports。

### Spec re-review subagent

- Agent id: `019e95f6-efc1-7cf0-98a1-c083e602576a`
- Nickname: Popper
- Status: ✅ Spec compliant

已确认:

- `RunContext.create()` 已使用 `.resolve()`。
- `tests/test_observability_run_context.py` 已断言 `context.summaries_dir.is_dir()`。
- focused test 已通过。

### Code quality review subagent

- Agent id: `019e95f9-1357-7a13-b7f5-b10d9911954c`
- Nickname: Lovelace
- Status: Approved

Minor 非阻塞建议:

- 可后续补测 `context.method_state_dir.is_dir()`。
- `EventWriter("~/...")` 不展开 `~`，当前通过 `RunContext.logs_dir` 使用无问题。

Task 1 当前结论: 已完成并通过两道 review。

## Task 2 当前状态

### Implementer subagent

- Agent id: `019e95fc-70e3-7251-b177-32e5c9c50ff9`
- Nickname: McClintock
- Status: DONE

实现内容:

- 新增 `memory_benchmark/observability/progress_reporter.py`
- 更新 `memory_benchmark/observability/__init__.py`
- 新增 `tests/test_observability_progress.py`

测试:

```bash
uv run python -m unittest tests/test_observability_progress.py -v
uv run python -m unittest tests/test_documentation_standards.py -v
```

均通过。

### Spec review subagent

- Agent id: `019e9600-2102-7783-bc43-7ea7cdd08f38`
- Nickname: Schrodinger
- Status: ✅ Spec compliant

### Code quality review subagent

- Agent id: `019e9602-a457-76f0-a942-4d2d638df7bc`
- Nickname: Boyle
- Status: Needs changes

Important issues:

1. `ProgressReporter._write_snapshot()` 使用 `Path.write_text()` 直接写 `progress.json`。长实验中如果崩溃或被并发读取，可能看到空文件/半写文件；需要改成同目录临时文件 + `os.replace()` 原子替换。
2. `tests/test_observability_progress.py` 覆盖太薄，只测了 `set_stage()` 和 `update_questions()`，没有覆盖 `start_conversations()`、`update_conversations()`、`start_questions()`、父目录创建、重复更新后的最新快照。

Minor:

- `__exit__()` 应用 `try/finally`，避免 `_write_snapshot()` 异常导致 Rich progress 没有退出。
- `snapshot` 是 public mutable dict，后续可考虑改成 `_snapshot` + copy accessor。

### Fix pass

Task 2 implementer 已修复:

- `_write_snapshot()` 改为同目录临时文件 + `os.replace()` 原子替换，并执行 flush/fsync。
- `__exit__()` 改为 `try/finally`，保证 Rich progress cleanup。
- `tests/test_observability_progress.py` 扩展到 5 个测试，覆盖父目录创建、conversation progress、重复 question 更新、disabled Rich 仍写 snapshot。

测试:

```bash
uv run python -m unittest tests/test_observability_progress.py -v
uv run python -m unittest tests/test_documentation_standards.py -v
```

均通过。

### Spec re-review subagent

- Agent id: `019e9607-26dd-73f3-968c-1bd22d648480`
- Nickname: Ptolemy
- Status: ✅ Spec compliant

### Code quality re-review subagent

- Agent id: `019e9609-806a-75c0-872e-4c102a5002ba`
- Nickname: Arendt
- Status: Approved

Minor 非阻塞建议:

- `_write_snapshot()` 如果在 `temporary_path` 赋值前抛异常，可能留下临时文件；不影响目标文件原子性。
- 没有专门用测试模拟 `__exit__()` 中 `_write_snapshot()` 抛异常时 progress stop 仍执行；当前代码检查通过。

Task 2 当前结论: 已完成并通过两道 review。

## Task 3 当前状态

### Implementer subagent

- Agent id: `019e960c-c2ab-7512-acb6-90e961ac1833`
- Nickname: Meitner
- Status: DONE

实现内容:

- 新增 `memory_benchmark/storage/__init__.py`
- 新增 `memory_benchmark/storage/experiment_paths.py`
- 新增 `memory_benchmark/storage/jsonl.py`
- 新增 `memory_benchmark/storage/fingerprint.py`
- 新增 `memory_benchmark/storage/artifacts.py`
- 新增 `tests/test_experiment_storage.py`

实现摘要:

- `ExperimentPaths`: 标准 run layout 与 artifact/checkpoint/summary 路径属性。
- `JsonlWriter` / `read_jsonl`: append-only JSONL 写入与读取。
- `build_dataset_fingerprint`: 记录 dataset 名称、conversation/question 数、source file size/hash；缺失文件写 `None`。
- `public_question_record`: 公开 question artifact record。
- `evaluator_private_label_record`: evaluator-only gold label artifact record。

测试:

```bash
uv run python -m unittest tests/test_experiment_storage.py -v
uv run python -m unittest tests/test_documentation_standards.py -v
```

均通过。

### Spec review subagent

- Agent id: `019e9611-0974-72a1-8f72-785f2789cbbc`
- Nickname: Tesla
- Status: completed with one issue

发现问题:

- `tests/test_experiment_storage.py` 的 `test_experiment_paths_create_standard_layout` 没有断言 `paths.summaries_dir.is_dir()`。

### Spec fix

Task 3 implementer 已补:

```python
self.assertTrue(paths.summaries_dir.is_dir())
```

测试:

```bash
uv run python -m unittest tests/test_experiment_storage.py -v
```

结果: 3 tests OK。

### Spec re-review subagent

- Agent id: `019e9614-2980-7270-aa99-af5a99e8c9b7`
- Nickname: Poincare
- Status: ✅ Spec compliant

确认:

- `ExperimentPaths` 创建 `artifacts/logs/checkpoints/summaries/method_state`。
- 所有计划要求的 path properties 存在。
- `JsonlWriter` / `read_jsonl`、dataset fingerprint、artifact helpers、evaluator-only docstring、storage exports、中文 docstring 均符合 spec。

### Code quality review subagent

- Agent id: `019e9616-ba20-7bc0-b832-3942fedcc492`
- Nickname: Mill
- Status: Needs changes

Important issues:

1. `memory_benchmark/storage/artifacts.py`
   - `public_question_record()` 直接复制 `question.metadata`。
   - 这是 public artifact 边界，如果传入 `Question(..., metadata={"gold_answer": ...})` 会把私有标签写进 `public_questions.jsonl`。
   - 需要在 helper 内校验/过滤 private keys，或者用测试证明 caller 只传 sanitized question。
   - 推荐修复: 在 `public_question_record()` 内拒绝 private metadata key，抛项目领域异常；同时补测试。

2. `memory_benchmark/storage/experiment_paths.py`
   - 当前路径命名疑似与计划/文档不一致:
     - 使用了 `redacted_config.json`
     - 使用了 `locomo_f1_scores.jsonl`
   - 计划/文档要求:
     - `config.redacted.json`
     - `answer_scores.locomo_f1.jsonl`
   - 需要改回计划命名，避免后续多 metric artifact 结构混乱。

Minor issues:

1. `tests/test_experiment_storage.py`
   - 尚未测试 artifact helpers。
   - 应补: `public_question_record()` 不应允许 `gold_answer`、`evidence`、`judge_label`、`answer_session_ids` 等 private keys 泄漏。

2. `tests/test_experiment_storage.py`
   - 只测了 missing source fingerprint。
   - 应补 existing file 的 `size_bytes` 和 `sha256`。

Task 3 当前结论: **未完成**。已通过 spec review，但 code quality review 要求修复上述问题。用户要求因额度/上下文即将耗尽，当前暂停，不继续实现。

### Code quality fix pass

恢复后已派发新的 Task 3 fix worker:

- Agent id: `019e970a-a6bc-7792-96c4-bdc9cde0830e`
- Nickname: Kant
- Status: DONE

修复内容:

- `ExperimentPaths.redacted_config_path` 改为 `config.redacted.json`。
- `ExperimentPaths.locomo_f1_scores_path` 改为 `answer_scores.locomo_f1.jsonl`。
- `public_question_record()` 调用 `validate_no_private_keys()`，阻断 public artifact 泄漏 `gold_answer/evidence/judge_label/answer_session_ids` 等 private keys。
- `evaluator_private_label_record()` 保持 evaluator-only，可包含 `gold_answer` 和 `evidence`。
- `tests/test_experiment_storage.py` 扩展到 7 个测试，覆盖 public/private artifact helper、private metadata 泄漏、existing source file `size_bytes/sha256`。

测试:

```bash
uv run python -m unittest tests/test_experiment_storage.py -v
uv run python -m unittest tests/test_documentation_standards.py -v
```

均通过。

### Spec re-review after fix

- Agent id: `019e970d-f930-7422-808d-f95e8cfa67a4`
- Nickname: Jason
- Status: ✅ Spec compliant

### Code quality re-review after fix

- Agent id: `019e9710-d6b0-7f03-989a-7ce0aba7163f`
- Nickname: Banach
- Status: Approved

Task 3 当前结论: 已完成并通过两道 review。

## Task 4 当前状态

### Implementer subagent

- Agent id: `019e9714-cd46-7b20-b170-62e52dc05134`
- Nickname: Feynman
- Status: DONE

实现内容:

- 更新 `tests/test_run_logger.py`
  - 新增 `test_info_accepts_rich_markup_and_file_log_strips_markup`
  - 验证 `logger.info("[bold]Memory Benchmark Run[/bold]")` 写入 `run.log` 时去掉 Rich markup。
- 更新 `memory_benchmark/utils/run_logger.py`
  - `RunLogger.info()` 仍用 `self.console.print(message)` 在终端渲染 Rich markup。
  - 写 `run.log` 时使用 `Text.from_markup(message).plain` 保存纯文本。
  - `log_event()` 行为未变。

测试:

```bash
uv run python -m unittest tests/test_run_logger.py -v
```

结果: 5 tests OK。实现前 red step 已确认新测试失败，修复后通过。

### Spec review subagent

- Agent id: `019e9717-5d9f-7641-9a76-f4d0ec96c784`
- Nickname: Mendel
- Status: ✅ Spec compliant

确认:

- 指定测试存在。
- 测试检查 `Memory Benchmark Run` 出现在 `run.log`，且 `[bold]` 不存在。
- `RunLogger.info()` 仍使用 `self.console.print(message)`。
- `RunLogger.info()` 使用 `Text.from_markup(message).plain` 写纯文本日志。
- `log_event()` 行为未变。
- 中文 docstring 保留。

### Code quality review subagent

- Agent id: `019e972b-cf8a-7b33-8d02-92ffd18439d6`
- Nickname: Volta
- Status: Needs changes

发现问题:

- `RunLogger.info()` 遇到坏 Rich markup（例如 `[bold]bad[/red]`）时，`Console.print()` 或 `Text.from_markup()` 会抛 `MarkupError`，可能让长实验因为日志格式中断。

### Code quality fix pass

- Agent id: `019e972f-bb1e-72f2-8401-8ec3c60dcb43`
- Nickname: Pauli
- Status: DONE

修复内容:

- `RunLogger.info()` 捕获 `rich.errors.MarkupError`。
- 对合法 Rich markup: 终端继续 Rich 渲染，`run.log` 写去 markup 的纯文本。
- 对坏 Rich markup: 终端用 `markup=False` 普通文本打印，`run.log` 写原文，避免日志中断长实验。
- 新增 `test_info_handles_malformed_rich_markup_without_aborting_run`。

测试:

```bash
uv run python -m unittest tests/test_run_logger.py -v
uv run python -m unittest tests/test_documentation_standards.py -v
```

结果: `tests/test_run_logger.py` 6 tests OK；documentation standards 4 tests OK。

### Code quality re-review subagent

- Agent id: `019e9732-e79b-79f2-8db6-673831834e4e`
- Nickname: Darwin
- Status: Approved

确认:

- 坏 Rich markup fallback 正常。
- 合法 Rich markup 仍保留终端渲染和文件纯文本。
- `log_event()` 行为未改变。

Task 4 当前结论: **已完成并通过 spec review 与 code quality review**。

## 下一步

恢复后继续 subagent-driven，从 Task 5 runner artifact integration 开始:

1. 修改 `tests/test_memoryos_locomo_full_runner.py`，先断言标准 artifact layout。
2. 修改 `memory_benchmark/runners/memoryos_locomo_full.py`，接入 `RunContext`、`ExperimentPaths`、dataset fingerprint、public/private artifact JSONL。
3. 保留 legacy root 输出兼容：`predictions.jsonl`、`scores.jsonl`、`summary.json`、`conversation_status.json`。
4. Task 5 通过 spec/code review 后，再进入 Task 6 Rich progress integration。

## 当前重要约束

- 当前目录不是 git repo，不能 commit；所有 subagent 报告“changed files + tests”，不要要求 commit。
- Python 文件需要中文模块说明、中文类/函数 docstring。
- 使用 `uv` 跑测试。
- 使用 `apply_patch` 做手动编辑。
- 不要触碰 MemoryOS 全量实验输出目录，当前任务只改框架可观测性与 artifact 结构。

## 压缩恢复说明

如果上下文压缩或额度中断，新窗口应先读:

1. `AGENTS.md`
2. `docs/handoffs/2026-06-05-observability-artifacts.md`
3. `docs/superpowers/plans/2026-06-05-observability-artifacts-phase-ab.md`

然后从 Task 5 runner artifact integration 继续。不要从 Task 1/2/3/4 重做。

## 2026-06-05 17:30 AGENTS 同步记录

用户指出 `AGENTS.md` 是新窗口默认优先读取的续航入口，必须同步当前任务进度。已更新 `AGENTS.md`:

- 添加当前可观测性与实验产物结构 handoff、spec、plan 路径。
- 写入 Task 1-3 已完成、Task 4 已实现并通过 spec review、下一步是 Task 4 code quality review。
- 补充 `memory_benchmark/observability/`、`memory_benchmark/storage/` 和标准 `outputs/<run_id>/` 子目录约定。
- 补充后续派发 subagent 时推理强度至少为 high。
- 补充 handoff 与 AGENTS 需要频繁同步的规则。

## 2026-06-05 AGENTS Router 化记录

用户确认 `AGENTS.md` 应该是项目入口和目录，不应写成长篇历史。已将 `AGENTS.md` 从 285 行压缩为约 139 行，改为 Router 风格:

- 只保留当前项目方向、当前断点、核心协议、私有数据边界、目录导航、事实来源、工程规则、AGENTS/handoff 更新规则和常用验证命令。
- MemoryOS 长实验细节、类别映射和 caveat 改为链接到 `docs/handoffs/2026-06-03-memoryos-locomo.md`。
- observability/artifact Task 细节改为链接到本 handoff、spec 和 plan。
- 明确当前断点仍为 Task 5 `memoryos_locomo_full` runner artifact integration。

## Task 5 当前状态

### Implementer subagent

- Agent id: `019e973d-3154-76e0-8d4f-9929e3906ff9`
- Nickname: Halley
- Status: DONE

实现内容:

- `memoryos_locomo_full` 接入 `RunContext` 和 `ExperimentPaths`。
- 写入标准 artifact layout:
  - `manifest.json`
  - `config.redacted.json`
  - `artifacts/public_questions.jsonl`
  - `artifacts/method_predictions.jsonl`
  - `artifacts/evaluator_private_labels.jsonl`
  - `artifacts/answer_scores.locomo_f1.jsonl`
  - `artifacts/dataset_fingerprint.json`
  - `summaries/summary.json`
  - `checkpoints/conversation_status.jsonl`
- 保留 legacy root aliases:
  - `predictions.jsonl`
  - `scores.jsonl`
  - `summary.json`
  - `conversation_status.json`
- legacy-only resume 会先 seed 到 canonical 文件，再检测已完成 question，避免重复回答。
- summary 返回 canonical artifact/summary 路径。
- 测试覆盖 public artifact 不含 `gold_answer`，evaluator-private label 含 `gold_answer`。

测试:

```bash
uv run python -m unittest tests/test_memoryos_locomo_full_runner.py -v
uv run python -m unittest tests/test_run_logger.py tests/test_documentation_standards.py -v
```

### Spec review subagent

- Agent id: `019e9744-98b6-77b0-a0d1-fb80c3a3f396`
- Nickname: Epicurus
- Status: Approved

确认:

- Task 5 spec requirements 均满足。
- 没有提前实现 Task 6 `ProgressReporter` 或 Task 7 `dataset_loaded` / `method_configured` event coverage。
- 已知命名债务：`ExperimentPaths.conversation_status_path` 当前返回 `checkpoints/conversation_status.jsonl`，但 runner 写入的是 JSON dict。Spec reviewer 接受这不是 Task 5 阻塞项，因为 runner 使用了当前 storage API，且测试明确按 JSON 读取。

### Code quality review

- Agent id: `019e9748-0a91-7673-bba7-90754b3e5770`
- Nickname: Hubble
- Status: Needs changes

发现问题:

1. P1: resume 对 partial question writes 或 canonical/legacy alias 分歧不幂等。若 prediction 已写但 score 未写，resume 会再次调用 MemoryOS 并可能重复 prediction。
2. P2: `conversation_status.jsonl` 实际写 JSON dict，扩展名应改为 `.json`，否则后续维护者可能误用 `read_jsonl()`。
3. P2: resume 时如果同一 `run_id` 使用不同 `conversation_limit`、`question_limit_per_conversation`、dataset 或 config，会混合不兼容 artifacts。
4. P2: full runner 在传给 method 前缺少 `validate_no_private_keys()` guard。

当前 Task 5 不能标记完成。下一步应修复以上问题并重新做 code quality re-review。

### Quality-fix implementer

- Status: DONE

修复内容:

1. resume 时按 `question_id` reconcile canonical/legacy predictions 与 scores JSONL；互补记录会合并并重写两侧，冲突重复记录会抛 `ConfigurationError`。
2. prediction 已存在但 score 缺失时，runner 复用已落盘 prediction 计算缺失 score，不重复调用 `MemoryOS.get_answer()`。
3. canonical conversation status 路径改为 `checkpoints/conversation_status.json`；保留 legacy root `conversation_status.json`，并支持从旧 `checkpoints/conversation_status.jsonl` 迁移。
4. resume 写 metadata 前校验既有 manifest/config 与当前 `benchmark_name`、`method_name`、`model_name`、`conversation_limit`、`question_limit_per_conversation` 和 MemoryOS config 一致，不一致抛 `ConfigurationError`。
5. 在 `add/load_existing_conversation_state` 与 `get_answer` 前对公开 conversation/question payload 调用 `validate_no_private_keys()`。

新增/更新测试覆盖:

- canonical/legacy JSONL 互补记录 reconcile。
- 同一 `question_id` 冲突重复记录 fail fast。
- prediction-without-score resume 不重复调用 `get_answer()`。
- run-shaping config mismatch 与 MemoryOS config mismatch。
- 旧 `checkpoints/conversation_status.jsonl` 到新 `.json` 路径迁移。
- public question metadata 私有键在 method 调用前被拦截。

验证:

```bash
uv run python -m unittest tests/test_memoryos_locomo_full_runner.py tests/test_experiment_storage.py -v
uv run python -m unittest tests/test_run_logger.py tests/test_documentation_standards.py -v
```

结果均为 OK。

下一步: Task 5 code quality re-review；通过后再进入 Task 6 Rich progress integration。

### Code quality re-review

- Agent id: `019e9756-a52e-70b1-b093-fbb8036f0d64`
- Nickname: Beauvoir
- Status: Approved

确认:

- canonical/legacy JSONL 按 `question_id` reconcile，冲突重复记录会失败。
- prediction-without-score resume 会复用已有 prediction，不重复调用 `get_answer()`。
- canonical conversation status 已改为 `checkpoints/conversation_status.json`，并支持旧 `checkpoints/conversation_status.jsonl` 迁移。
- resume metadata/config mismatch guard 已覆盖 run shape 和 MemoryOS config。
- `validate_no_private_keys()` 已在 method add/attach/get_answer 前执行。
- 没有提前实现 Task 6 progress 或 Task 7 extra events。

验证:

```bash
uv run python -m unittest tests/test_memoryos_locomo_full_runner.py tests/test_experiment_storage.py -v
uv run python -m unittest tests/test_run_logger.py tests/test_documentation_standards.py -v
```

结果: 16 tests OK；10 tests OK。

Task 5 当前结论: **已完成并通过 spec review 与 code quality review**。

## Task 6 当前状态

当前断点已进入 Task 6 `memoryos_locomo_full` Rich progress integration。下一步:

1. 按计划先修改 `tests/test_memoryos_locomo_full_runner.py`，断言 `progress.json`。
2. 在 runner 中接入 `ProgressReporter`，写阶段、conversation progress 和 question progress。
3. 不提前实现 Task 7 event coverage。
4. 完成后做 spec review 与 code quality review。

## 2026-06-06 额度恢复交接

### 上次中断原因

- Task 6 implementer subagent:
  - Agent id: `019e975a-85d5-7eb3-887c-6f70dbcb4d37`
  - Nickname: Hooke
  - Status: errored
- 错误原因是 Codex 5h usage limit 耗尽，不是代码、测试或设计问题。
- 已检查 `memory_benchmark/runners/memoryos_locomo_full.py` 和 `tests/test_memoryos_locomo_full_runner.py`，没有出现 `ProgressReporter`、`show_progress` 或 `progress.json` 集成，因此 Task 6 尚未产生需要恢复的半成品代码。
- 恢复时应重新派发 Task 6 implementer，不能把上次 errored subagent 当成已完成。

### OpenCode 副手机制

用户在 `AGENTS.md` 中新增 OpenCode + DeepSeek V4 Pro 副手机制:

- Codex 额度快耗尽且用户通知剩余恢复时间时，除更新 handoff 外，还应把一个机械式、低创造性、边界明确的任务写入 `opencode/opencode_task.md`。
- OpenCode 的结果写入 `opencode/opencode_result.md`。
- Codex 额度恢复后，必须先读 handoff，再检查 `opencode/opencode_result.md`。
- `opencode_result.md` 为空表示 OpenCode 没有完成任务。
- OpenCode 只能处理机械式工作，不能承担架构设计、复杂 debug、指标解释、论文/benchmark 判断、涉及私有数据边界的设计或高风险重构。
- OpenCode 产出不能直接视为可信完成结果；Codex 恢复后必须审查其修改和结果，并重新运行相关测试后才能纳入项目。
- 给 OpenCode 的任务应明确允许修改的文件、禁止修改的文件、逐步操作、验证命令和结果报告格式，避免它自行扩大范围。

本次恢复检查:

- `opencode/opencode_task.md`: 空。
- `opencode/opencode_result.md`: 空。
- 结论: 上次额度中断期间没有 OpenCode 工作需要审查或合并。

### 当前准确恢复点

1. `AGENTS.md` 当前步骤仍正确指向 Task 6。
2. 重新派发 high reasoning Task 6 implementer。
3. Task 6 只接入 Rich progress 和 `checkpoints/progress.json`，不提前实现 Task 7 event coverage。
4. 实现后依次执行 focused tests、spec review、code quality review。

### Task 6 implementer 恢复后结果

- Agent id: `019e9ab9-7288-77b1-b5b0-fbaac9299f82`
- Nickname: McClintock
- Status: DONE

实现内容:

- `run_memoryos_locomo_full()` 新增 `show_progress: bool = True`；真实运行默认显示 Rich 进度，测试可关闭终端渲染。
- 接入 `ProgressReporter(paths.progress_path, enabled=show_progress)`。
- 使用六个阶段:
  1. `Load dataset`
  2. `Prepare method state`
  3. `Add conversations`
  4. `Answer questions`
  5. `Evaluate answers`
  6. `Write summary`
- conversation ensure 后更新 conversation 完成数和当前 `conversation_id`。
- question score 写入后更新 question 完成数、当前 `conversation_id` 和 `question_id`。
- resume 时会用已有 score 数初始化 question progress。
- `show_progress=False` 时仍写 `checkpoints/progress.json`。
- 未加入 Task 7 的 `dataset_loaded` / `method_configured` events。

测试:

```bash
uv run python -m unittest tests/test_memoryos_locomo_full_runner.py -v
uv run python -m unittest tests/test_observability_progress.py tests/test_run_logger.py tests/test_documentation_standards.py -v
```

结果: 9 tests OK；15 tests OK。

当前精确断点: Task 6 implementation 已完成，下一步是 Task 6 spec review，然后 code quality review。Task 6 尚未正式标记完成。

### Task 6 spec review

- Agent id: `019e9abc-e801-77d1-8ac5-5a5d0b910547`
- Nickname: Aquinas
- Status: Approved

确认:

- `checkpoints/progress.json` 正常写入。
- 最终阶段是 `Write summary`。
- conversation/question 最终完成数正确。
- 六个阶段名称和序号准确。
- resume 已完成 score 会初始化 question progress。
- `show_progress=False` 仍写快照。
- 未提前加入 Task 7 events。

验证:

```bash
uv run python -m unittest tests/test_memoryos_locomo_full_runner.py -v
```

结果: 9 tests OK。

当前精确断点: Task 6 implementation + spec review 已完成，下一步是 Task 6 code quality review。通过后才可进入 Task 7。

### Task 6 code quality review

- Agent id: `019e9abd-eb26-7582-9830-9c49e6fec093`
- Nickname: Zeno
- Status: Needs changes

发现问题:

1. resume 只初始化 question progress，没有在 MemoryOS 构造和循环开始前初始化 conversation progress；若此时失败，快照会错误显示 `conversation_completed=0`。
2. 当前 question id 只在成功评分后写入快照；`get_answer()` 或 evaluator 中途失败时，快照仍显示上一题。
3. 每题在 `Answer questions` / `Evaluate answers` 间切换并触发原子写 + `fsync`，全量运行会产生数千次持久化写；同时 `ProgressReporter.set_stage()` 没有 Rich stage task，终端看不到阶段文本。
4. 测试缺少 resume progress 初始化和注入失败时 current question 快照断言。

技术处理方向:

- 在构造 MemoryOS 前，按当前计划内 conversation ids 初始化 conversation progress；同时初始化已有 completed question 数。
- 在调用 `get_answer()` 前写入当前 conversation/question id，使异常快照指向正在处理的题。
- 为 Rich progress 增加可见的 stage/current item 描述。
- 避免每题反复持久化 stage 切换；question 循环保持 `Answer questions`，评分完成通过 question progress 更新，阶段 5 只在最终聚合/评估收尾进入一次，再进入阶段 6。
- 如仍需高频 current item 更新，应在 `ProgressReporter` 内加入节流/合并策略，并保证退出、阶段切换和最终完成强制落盘。
- 补 resume 初始化和 injected failure 测试。

当前 Task 6 不能标记完成。下一步是派发 quality-fix implementer，修复后重新做 code quality review。

### Task 6 quality-fix implementer

- Agent id: `019e9ac1-72f9-7410-8b8b-545521552200`
- Nickname: Linnaeus
- Status: DONE

修复内容:

- resume 在 MemoryOS 构造前按当前计划内 conversation ids 恢复 conversation 完成数，同时恢复已有 score 的 question 完成数。
- 调用 `get_answer()` 前先更新 current conversation/question；异常退出时 `ProgressReporter.__exit__()` 强制写入最新快照。
- Rich 新增 stage task；conversation/question task description 展示当前 ids。
- 高频普通更新使用 1 秒 `time.monotonic()` 节流；阶段切换、任务启动、显式 `flush()` 和上下文退出强制落盘。
- 移除每题在 `Answer questions` / `Evaluate answers` 间的阶段切换；阶段 5 只在最终聚合前进入一次。
- 未添加 Task 7 events。

新增测试:

- resume 在 MemoryOS 构造失败前已经恢复 conversation/question counters。
- `get_answer()` 失败后快照指向失败 question。
- 高频更新被合并，但退出上下文强制保存最新状态。
- Rich task description 包含 stage、conversation id 和 question id。

验证:

```bash
uv run python -m unittest tests/test_memoryos_locomo_full_runner.py tests/test_observability_progress.py -v
uv run python -m unittest tests/test_run_logger.py tests/test_documentation_standards.py -v
```

结果: 18 tests OK；10 tests OK。

当前精确断点: Task 6 quality-fix 已完成，下一步是 code quality re-review。

### Task 6 code quality re-review

- Agent id: `019e9ac5-56ff-7382-8bfc-b778781ae49a`
- Nickname: Anscombe
- Status: Approved

确认:

- resume 只统计当前计划内 conversation，并在 MemoryOS 构造前恢复进度。
- 异常退出快照能指向失败 question。
- Rich description 展示 stage 和当前 ids。
- 1 秒单调时钟节流与强制落盘边界正确。
- 已移除每题阶段切换。
- 未加入 Task 7 events，Task 5 行为未回归。

验证: runner/progress 18 tests OK；logger/docs 10 tests OK；额外节流边界检查通过。

Task 6 当前结论: **已完成并通过 spec review 与 code quality review**。

## Task 7 当前状态

当前断点已进入 Task 7 `memoryos_locomo_full` event coverage。目标是补齐关键结构化事件并增加测试，不改变 method、metric、artifact、resume 或 progress 行为。

### Task 7 implementer

- Agent id: `019e9ac7-98ff-7e90-b94c-99d561a7b129`
- Nickname: Laplace
- Status: DONE

实现内容:

- 数据加载成功后写 `dataset_loaded`:
  - `dataset_name`
  - `conversation_count`
  - `question_count`
- MemoryOS 构造前写 `method_configured`:
  - `method_name`
  - `storage_root`
  - `asdict(MemoryOSPaperConfig)`，不含 API key/base URL/secret
- 保留既有 `full_run_started`、`conversation_added/attached`、`question_scored`、`full_run_finished`。
- 测试读取 `logs/events.jsonl` 并断言关键 event names。

验证:

```bash
uv run python -m unittest tests/test_memoryos_locomo_full_runner.py -v
uv run python -m unittest tests/test_run_logger.py tests/test_documentation_standards.py -v
```

结果: 11 tests OK；10 tests OK。

当前精确断点: Task 7 implementation 已完成，下一步是 spec review 和 code quality review。

### Task 7 spec review

- Agent id: `019e9ac9-a8d6-74b0-a6c2-1296e91a5f17`
- Nickname: Feynman
- Status: Approved

确认:

- 测试读取 `logs/events.jsonl` 并断言六类关键事件。
- `dataset_loaded` payload 正确。
- `method_configured` 在 MemoryOS 构造前写入，配置不含 secret。
- `conversation_attached` 保留。
- 未改变 method、metric、artifact、resume 或 progress 行为。

验证: runner 11 tests OK。

当前精确断点: Task 7 implementation + spec review 已完成，下一步是 code quality review。

### Task 7 code quality review

- Agent id: `019e9aca-c2b8-7003-88f6-8c741dd036ee`
- Nickname: Copernicus
- Status: Needs changes

审查发现:

1. `full_run_started` 当前在 dataset、resume 校验和 MemoryOS 构造之后才写入。若前置阶段失败，事件日志没有本次运行尝试的开始记录，也没有统一失败记录。
2. 同一个 `run_id` 多次 resume 会把事件追加到同一 `events.jsonl`，但当前没有 `attempt_id`，无法可靠区分每次运行尝试。
3. `method_configured` 直接记录 `asdict(config)`。当前 `MemoryOSPaperConfig` 不含 secret，但以后新增 `api_key`、`base_url`、prompt 等字段时可能被日志自动带出。
4. 现有测试只断言 event name 存在，没有验证事件顺序、关键 payload、隐私边界、失败路径和重复 resume 的尝试关联。

技术判断:

- 这些问题超出 Task 7 原始最小规格，但直接关系到长实验的可审计性和 secret 安全，应该在 Task 7 关闭前受控修复。
- 不引入通用 telemetry 框架；修复范围保持在 `memoryos_locomo_full.py` 和对应测试。
- 每次函数调用生成唯一 `attempt_id`。`full_run_started` 应在 logger 创建后尽早写入，并包含 `run_id`、`attempt_id`、`resume`。
- 成功和失败生命周期事件都要包含同一 `attempt_id`。关键中间事件也应带上该 id，确保同一文件中的事件可按尝试过滤。
- 捕获 runner 主流程异常，写入脱敏的 `full_run_failed`：只记录异常类型、当前 stage、conversation/question id，不记录异常 message，然后原样重新抛出。
- `method_configured` 改为显式公开字段 allowlist，并可附配置指纹；不能继续直接日志化整个 dataclass。
- 测试补充成功事件顺序和 payload、日志 forbidden keys、构造/答题失败事件、同 run_id 多次 resume 的 attempt id 区分。

当前精确断点: Task 7 code quality review 未通过。下一步派发 high-reasoning quality-fix implementer，先写失败测试，再做最小实现；随后重新进行 code quality review。

## 暂停原因

用户提示 Codex 5h 额度即将用完，且上下文即将压缩。当前已按要求停止推进实现，只更新本 handoff，保证下一窗口无缝衔接。

## 2026-06-06 恢复记录

- 用户确认 5h 额度已恢复，继续执行 Task 7。
- 已读取 `AGENTS.md`、本 handoff、实施计划和 OpenCode 结果。
- `opencode/opencode_result.md` 为空，本轮没有 OpenCode 产物需要验收。
- 已核对当前代码，确认 code quality review 的问题真实存在。
- 已派发 high-reasoning quality-fix worker:
  - Agent id: `019e9ace-ce78-7d03-aff0-683ffc2cf845`
  - Nickname: Cicero
  - 写入范围: `memory_benchmark/runners/memoryos_locomo_full.py`、`tests/test_memoryos_locomo_full_runner.py`

当前精确断点: worker 正在实现 Task 7 lifecycle/privacy quality-fix。返回后先做本地 diff 和 focused tests，再派发独立 code quality re-review。

### Task 7 quality-fix implementer

- Agent id: `019e9ace-ce78-7d03-aff0-683ffc2cf845`
- Nickname: Cicero
- Status: DONE

完成内容:

- 每次 runner 调用生成唯一 `attempt_id`。
- `full_run_started` 移到 logger 创建后、dataset load 前。
- 当前模块写出的全部事件都包含 `attempt_id` 和 `resume`。
- 异常时写脱敏 `full_run_failed`，记录异常类型、stage 和当前公开 ids，然后重新抛出。
- `method_configured` 改用显式公开配置白名单和 SHA-256 指纹，不再直接记录整个 dataclass。
- 测试补充成功顺序、事件隐私、MemoryOS 构造失败、回答失败以及同 run_id 两次 attempt。

主控复核:

```bash
uv run python -m unittest tests/test_memoryos_locomo_full_runner.py -v
uv run python -m unittest tests/test_run_logger.py tests/test_documentation_standards.py -v
```

结果: 12 tests OK；10 tests OK。

当前精确断点: Task 7 quality-fix 已通过主控 focused tests，下一步派发独立 high-reasoning code quality re-review。

### Task 7 code quality re-review

- Agent id: `019e9ad3-e795-72e3-b461-8b37b2a90f01`
- Nickname: Hubble
- Status: Needs changes

确认已正确实现:

- attempt 关联、事件 payload、`conversation_attached` 关联字段。
- 配置白名单和指纹。
- 成功事件顺序、隐私检查和重复 resume attempts。

剩余问题:

1. 业务异常发生后，如果 `ProgressReporter.__exit__()` 写快照/停止进度时再次失败，后者可能覆盖原始业务异常。
2. 写 `full_run_failed` 时如果 logger 再次失败，当前 `finally: raise` 会重抛 logger 异常，而不是原始业务异常。
3. 测试尚未注入上述两类 observability secondary failure。

技术决策:

- 可观测性属于旁路能力，不能覆盖 dataset/method/evaluator/storage 的原始根因。
- 在 runner 本地增加受控 progress scope：有业务异常时尽力关闭/落盘，但吞掉 secondary progress failure 后原样重抛业务异常；无业务异常时 progress 自身失败仍应作为运行失败暴露。
- `full_run_failed` 写入改为 best-effort；失败时吞掉该 secondary exception，并用裸 `raise` 原样抛出外层原始异常。
- 新增两个注入测试，分别验证 progress exit 和 failure-event logger 故障不会掩盖原始异常。

当前精确断点: Task 7 第二轮 quality-fix 待实现，完成后再次做独立 re-review。

### Task 7 第二轮 quality-fix

- Implementer: Cicero (`019e9ace-ce78-7d03-aff0-683ffc2cf845`)
- Status: DONE

修复:

- runner 本地新增 `_progress_scope()`，主流程已有异常时，progress 退出故障不再覆盖原始异常。
- 正常成功路径上的 progress 退出故障仍正常向上传播。
- `full_run_failed` 事件写入改为 best-effort，写日志失败后仍裸 `raise` 原始异常。
- 两个注入测试使用 `assertIs` 验证重抛的是同一个原始异常对象。

主控验证:

```bash
uv run python -m unittest tests/test_memoryos_locomo_full_runner.py -v
uv run python -m unittest tests/test_run_logger.py tests/test_documentation_standards.py -v
```

结果: 14 tests OK；10 tests OK。

当前精确断点: 第二轮修复已通过主控 focused tests，等待独立 code quality re-review。

### Task 7 最终 code quality re-review

- Reviewer: Hubble (`019e9ad3-e795-72e3-b461-8b37b2a90f01`)
- Status: APPROVED
- Findings: 无

确认:

- progress 次生故障不会遮蔽原始业务异常。
- 正常路径 progress 退出故障仍然可见。
- failure event logger 故障不会遮蔽原始异常。
- 新增注入测试有效使用同一异常对象断言。
- 事件关联、隐私、配置白名单、resume、method、metric、artifact 行为均无回归。

reviewer 验证:

- focused tests: 27 passed。
- full suite: 122/122 passed。

Task 7 结论: **已完成并通过 spec review 与 code quality review**。

## Task 8 当前状态

目标:

- 更新 `README.md`，记录真实标准实验输出目录和复用方式。
- 更新 `AGENTS.md`，加入长实验 runner 的稳定工程规则。
- 更新设计草案，链接 Phase A/B implementation plan，并标明实现后的真实路径:
  - `artifacts/dataset_fingerprint.json`
  - `checkpoints/progress.json`
- 明确 src-layout 和 pytest 仍属于后续 Phase C/D，本轮不迁移。

当前精确断点: Task 8 文档更新待实现；完成后需要 documentation standards 测试、spec review 和 code quality review。

## 2026-06-06 额度暂停交接

暂停原因:

- 用户通知 Codex 5h 额度只剩约 10%。
- 为防止 Task 8 编辑或后续 review 在中途被截断，当前主动停止主任务。

已确认状态:

- Task 1-7 全部完成。
- Task 7 最终独立 code quality re-review 已 APPROVED。
- reviewer 报告 focused 27 tests 和 full suite 122/122 tests 均通过。
- `AGENTS.md` 已切换到 Task 8，并标注当前因额度暂停。
- `opencode/opencode_result.md` 在本轮恢复时为空，没有旧结果待合并。

OpenCode 委派:

- 任务文件: `opencode/opencode_task.md`
- 任务类型: 机械文档编辑，不涉及架构判断或 Python 代码。
- 允许修改:
  - `README.md`
  - `docs/superpowers/specs/2026-06-05-observability-src-layout-design.md`
  - `opencode/opencode_result.md`
- 禁止修改:
  - `AGENTS.md`
  - handoff、plan
  - 任意 Python 文件、测试文件、配置或第三方仓库
- 任务目标: 按任务文件给出的固定路径清单补充真实实验输出结构和实现状态，并运行 documentation standards 测试。

额度恢复后的严格恢复顺序:

1. 读 `AGENTS.md`。
2. 读本 handoff 的 Task 7 最终结论和本节。
3. 读 `opencode/opencode_result.md`；为空则视为未执行。
4. 检查 `README.md` 和设计草案的实际 diff，核对所有路径均与 `ExperimentPaths` 一致。
5. 重新运行 `uv run python -m unittest tests/test_documentation_standards.py -v`。
6. OpenCode 产物通过主控审查后，继续 Task 8 spec review 和 code quality review。
7. Task 8 通过后进入 Task 9 focused/full verification。

当前精确断点: **Task 8 未完成；等待额度恢复后验收 OpenCode 的机械文档草稿。**

## 2026-06-06 第二次恢复记录

- 用户确认 5h 额度已恢复。
- 用户没有让 OpenCode 执行任务，并决定在项目底座成熟前暂不让 OpenCode 参与。
- 当前工作区中不存在 `opencode/` 目录，因此没有 OpenCode 结果或文件修改需要验收。
- `AGENTS.md` 已解除额度暂停，当前任务恢复为 Task 8。
- 后续继续使用 Codex high-reasoning subagent 执行既定 Subagent-Driven 流程。

当前精确断点: Task 8 文档 implementation 待 Codex implementer 执行；随后依次进行 spec review、code quality review 和 Task 9 验证。

### Task 8 documentation implementer

- Agent id: `019e9c6e-67be-7dd3-8945-a336cee5e270`
- Nickname: Arendt
- Status: DONE

修改:

- `README.md`: 新增真实标准实验输出结构、artifact 复用规则、private label 边界、attempt id、progress 和 legacy alias 说明。
- `AGENTS.md`: 新增长实验 runner、标准 artifact、evaluator 复用和 Phase C/D 边界规则，保持 router 风格。
- `docs/superpowers/specs/2026-06-05-observability-src-layout-design.md`: 增加 Phase A/B 实施状态、计划链接和实际路径偏差。

主控核对:

- README 路径与 `ExperimentPaths` 一致。
- `artifacts/dataset_fingerprint.json` 与 `checkpoints/progress.json` 使用正确。
- `evaluator_private_labels.jsonl` 明确不能传给 method。
- `AGENTS.md` 共 144 行，未写成长篇历史。
- 未修改 Python、测试、plan 或 handoff 之外的任务文件。

验证:

```bash
uv run python -m unittest tests/test_documentation_standards.py -v
```

结果: 4 tests OK。

当前精确断点: Task 8 implementation 与主控核对已完成，下一步独立 spec review。

### Task 8 spec review

- Agent id: `019e9c70-9e67-74c0-a5e4-d6adb3b136aa`
- Nickname: Gauss
- Status: Needs changes

发现:

- 设计草案的输出树仍写 `checkpoints/question_status.json`，但 `ExperimentPaths.question_status_path` 的权威路径是 `checkpoints/question_status.jsonl`。

其余 Task 8 要求均满足，documentation standards 4 tests OK。

当前精确断点: 修正设计草案中的 question status 扩展名，测试后交回同一 reviewer 复审。

### Task 8 spec re-review

- Reviewer: Gauss (`019e9c70-9e67-74c0-a5e4-d6adb3b136aa`)
- Status: APPROVED
- 修正: `question_status.json` -> `question_status.jsonl`
- 验证: documentation standards 4 tests OK

当前精确断点: Task 8 implementation 与 spec review 已完成，下一步独立 code/documentation quality review。

### Task 8 documentation quality review

- Agent id: `019e9c72-86c2-74b0-9e33-599a66705ea3`
- Nickname: Herschel
- Status: Needs changes

发现:

1. README 对 `manifest.json` 的描述称其记录标准 artifact 路径，但当前 payload 只记录 `output_dir`，描述不准确。
2. 设计草案的 Phase B 推荐树包含尚未由当前 runner 写出的 `question_status.jsonl`、`answer_scores.llm_judge.jsonl` 和 `summary.md`，需要明确标为目标/预留文件，避免与已实现结构混淆。
3. README 链接不存在的 `.env.example`。

技术处理:

- 只修正文档事实，不创建新配置文件、不改变架构。
- README 的 manifest 描述改为实际公开运行元数据和输出根目录。
- 删除 `.env.example` 死链接，保留当前 `.env` 字段示例。
- 设计草案明确推荐树是目标结构，并列出当前未写出的预留文件；`ExperimentPaths` 仍是路径权威来源。

当前精确断点: Task 8 quality-fix 待原 implementer 完成，随后重新做文档质量复审。

### Task 8 documentation quality-fix

- Implementer: Arendt (`019e9c6e-67be-7dd3-8945-a336cee5e270`)
- Status: DONE

修正:

- README 的 manifest 描述改为当前实际 payload。
- README 删除不存在的 `.env.example` 链接，保留内联环境变量示例。
- 设计草案明确 Phase B 树是推荐目标结构，并标出当前 runner 尚未写出的三个预留产物。

验证:

- documentation standards 4 tests OK。
- README/AGENTS 无 `.env.example` 死链接。
- 设计草案中 `.env.example` 仅作为 Phase C 未来目录结构条目，不是当前链接或当前文件声明。

当前精确断点: Task 8 quality-fix 已完成，等待同一 reviewer 复审。

### Task 8 final documentation quality re-review

- Reviewer: Herschel (`019e9c72-86c2-74b0-9e33-599a66705ea3`)
- Status: APPROVED
- Findings: 无
- 验证: documentation standards 4 tests OK

Task 8 结论: **已完成并通过 spec review 与 documentation quality review**。

## Task 9 当前状态

目标:

1. 运行 observability/storage/runner focused suite。
2. 运行完整 unittest suite。
3. 再运行 fake MemoryOS-LoCoMo runner 测试，确认标准 artifacts、logs、checkpoints 和 summary。
4. 最终整体 code review 后关闭 Phase A/B。

当前精确断点: Task 9 验证待主控执行；当前不应修改业务代码，除非测试暴露真实问题。

### Task 9 主控验证

Focused suite:

```bash
uv run python -m unittest \
  tests/test_observability_run_context.py \
  tests/test_observability_progress.py \
  tests/test_experiment_storage.py \
  tests/test_run_logger.py \
  tests/test_memoryos_locomo_full_runner.py \
  -v
```

结果: 36/36 tests OK。

Full suite:

```bash
uv run python -m unittest discover -s tests -v
```

结果: 122/122 tests OK。包含 `gpt-4o-mini` API smoke，输出未显示 API key 或 base URL。

Fake runner 独立验证:

```bash
uv run python -m unittest tests/test_memoryos_locomo_full_runner.py -v
```

结果: 14/14 tests OK。覆盖标准 artifacts、legacy aliases、progress、events、resume、失败路径和 attempt 关联。

当前精确断点: Task 9 主控验证全部通过；下一步是 Phase A/B 整体最终 code review。最终 reviewer 通过后才可标记 Phase A/B 完成。

### Phase A/B final review

- Agent id: `019e9c77-588e-75c0-a9f9-59e8b7bbed8c`
- Nickname: Turing
- Status: NEEDS_CHANGES

发现:

1. P1: resume 未比较当前 dataset fingerprint 与已保存 fingerprint，数据版本变化后可能复用旧 prediction/score/method state。
2. P2: `_build_summary()` 统计所有 status 中的 `added`，可能让 `completed_conversations > total_conversations`。
3. P2: dataset load 等早期失败只写 `events.jsonl`，不会生成 `logs/run.log`。
4. P2: status/summary JSON 和 reconcile JSONL 直接覆盖写，进程中断可能留下截断文件，破坏 resume。
5. P3: 设计文档仍写 Task 8/9 pending，状态过时。

审查同时确认:

- focused 36/36、full 122/122 通过，但现有测试未覆盖上述故障。
- standard paths、public/private 边界和第三方源码隔离其余部分正确。
- Phase C src-layout / Phase D pytest 仍不在本轮范围。

当前精确断点: 进入 systematic debugging Phase 1，先逐项复现和确认数据流；完成根因分析后再按 TDD 派发修复。

### Final review remediation 根因结论

1. Dataset fingerprint:
   - 当前 fingerprint 只有 dataset 名称、计数和源文件 hash。
   - 没有统一 Dataset 内容 hash，无法检测 adapter 行为变化或同源文件下的内存数据变化。
   - resume 在复用/合并旧 prediction、score 和 status 前没有比较当前 fingerprint。
2. Summary count:
   - progress 初始化按当前 planned conversation ids 过滤。
   - `_build_summary()` 却统计 status 字典中的全部 `added`，两处逻辑不一致。
3. Early run log:
   - `RunLogger` 构造只创建目录；`run.log` 直到 method 构造后的首个 `info()` 才创建。
   - dataset load/resume validation/method construction 失败时只有 events，没有人类日志。
4. Atomic replacement:
   - `ProgressReporter` 已采用临时文件、flush、fsync、`os.replace`。
   - runner 的 JSON 和 reconcile JSONL 重写仍直接覆盖目标文件，崩溃时可留下截断产物。

修复拆分:

- Task 9A: 在 `storage/` 提供可复用 atomic JSON/JSONL replacement 原语和单元测试。
- Task 9B: runner 在复用任何旧状态前验证含 Dataset 内容 hash 的 fingerprint；过滤 summary conversation ids；提前写 start/failure 人类日志；使用 atomic 原语。
- Task 9C: 重新运行 focused/full/fake suite 和最终整体 review。

当前精确断点: Task 9A 待 high-reasoning implementer 按 TDD 实现。

### Task 9A atomic storage implementer

- Agent id: `019e9c7b-deef-7be2-aba0-1678c0fe857e`
- Nickname: Russell
- Status: DONE

实现:

- 新增 `atomic_write_json()`。
- 新增 `atomic_write_jsonl()`。
- 同目录临时文件、flush、fsync、`os.replace`。
- 序列化/写入/replace 失败时清理临时文件；replace 前失败不破坏旧目标。
- 从 `memory_benchmark.storage` 公开导出。
- 未改变 append-only `JsonlWriter`。

TDD RED: 新测试最初因 `atomic_write_json` 未导出而失败。

主控验证:

```bash
uv run python -m unittest tests/test_experiment_storage.py tests/test_documentation_standards.py -v
```

结果: 18/18 tests OK。

当前精确断点: Task 9A implementation 已完成，下一步 spec review 和 code quality review。

### Task 9A reviews

Spec review:

- Reviewer: Tesla (`019e9c7e-30cf-7c31-a51b-db41b9494e5a`)
- Status: APPROVED

Code quality review:

- Reviewer: Bacon (`019e9c7f-5ca6-7812-bdfb-e5d349dfb186`)
- Status: NEEDS_CHANGES

发现:

1. 临时文件 cleanup 的 `exists()` / `unlink()` 异常可能覆盖原始序列化、fsync 或 replace 异常。
2. `Iterable[Mapping[str, Any]]` 比 `json.dump` 实际支持范围更宽，应收窄为 `Iterable[dict[str, Any]]` 或明确约束。

技术处理:

- cleanup 改为 best-effort，保留原始写入异常；清理失败本身不覆盖根因。
- 收窄 JSONL records 类型为 `Iterable[dict[str, Any]]`。
- 新增 cleanup failure 不掩盖 replace failure 的回归测试。

当前精确断点: Task 9A quality-fix 待原 implementer 按 TDD 完成并复审。

### Task 9A quality re-review 1

- Reviewer: Bacon (`019e9c7f-5ca6-7812-bdfb-e5d349dfb186`)
- Status: NEEDS_CHANGES

已修正:

- `unlink()` failure 不再覆盖 primary error。
- JSONL records 类型已收窄。

剩余:

- `temporary_path.exists()` 仍在 best-effort try 外；某些 `OSError` 会覆盖 primary replace error。

下一步:

- 将 `exists()+unlink()` 整体纳入 best-effort cleanup。
- 扩展回归测试覆盖 exists failure，并重新复审。

### Task 9A final quality re-review

- Reviewer: Bacon (`019e9c7f-5ca6-7812-bdfb-e5d349dfb186`)
- Status: APPROVED

最终修正:

- `temporary_path.exists()` 和 `temporary_path.unlink()` 已整体放入
  best-effort cleanup，清理阶段的 `OSError` 不再覆盖原始写入或 replace 异常。
- JSONL records 类型已收窄为 `Iterable[dict[str, Any]]`。
- 回归测试覆盖 unlink failure 和 exists failure 两种清理异常。

验证:

```bash
uv run python -m unittest \
  tests/test_experiment_storage.py \
  tests/test_documentation_standards.py \
  -v
```

结果: 20/20 tests OK。

Task 9A 结论: **已完成并通过 spec review 与 code quality review**。

### Task 9B 恢复决策

2026-06-06 恢复任务后确认:

- OpenCode 暂不参与；待项目底座成熟后再评估启用。
- 全新空 run 目录即使 `resume=True` 也允许正常开始。
- 若 run 目录已存在 prediction、score、status、manifest、config 或非空 method
  state 等可复用状态，但缺少 dataset fingerprint，必须抛
  `ConfigurationError`，不能静默补写或猜测兼容。
- 旧真实实验目录需要后续单独的显式 migration 工具；当前 runner 不自动信任
  未验证的 legacy 状态。
- dataset fingerprint 增加统一 `Dataset` 完整规范化内容的确定性 SHA-256，
  用于检测源文件未变但 adapter 行为、gold label 或统一数据内容变化的情况。
- fingerprint 校验必须发生在 legacy migration、JSONL reconciliation、状态加载和
  MemoryOS 构造之前，避免不兼容状态被读取或改写。
- summary 的 `completed_conversations` 只统计当前计划内的 conversation id。
- runner 构造 logger 后立即写脱敏启动日志；失败时写不含异常消息和 secret 的
  失败摘要，确保 dataset load 等早期失败也产生 `logs/run.log`。
- runner 的 JSON 覆盖写和 reconciliation JSONL 重写统一使用 Task 9A atomic
  primitives；append-only JSONL 行为保持不变。

当前精确断点: Task 9B 进入 high-reasoning implementer TDD 实现。

### Task 9B implementer

- Agent id: `019e9c86-d769-7f60-9bfb-f9295c3bf717`
- Nickname: Euler
- Status: DONE

TDD RED:

- 新增回归测试首次运行出现 7 个预期失败/错误，覆盖完整 Dataset 内容 hash、
  缺失或不匹配 fingerprint、summary 当前计划过滤、早期失败人类日志和 runner
  atomic helper 委托。

实现:

- `build_dataset_fingerprint()` 新增完整规范化 `Dataset.to_dict()` 的确定性
  `dataset_sha256`。
- resume 在 legacy migration、JSONL reconciliation、旧状态读取和 MemoryOS
  构造前校验 fingerprint。
- 可复用状态缺少 fingerprint、旧 fingerprint 缺少 `dataset_sha256` 或当前内容
  不匹配时抛 `ConfigurationError`。
- summary 只统计当前计划 conversation ids。
- runner 启动后立即写 `run.log`；失败摘要只记录异常类型和公开定位字段。
- JSON 覆盖写、JSONL reconciliation 和公开/私有 question artifacts 重写使用
  atomic storage primitives。

主控重新验证:

```bash
uv run python -m unittest \
  tests/test_experiment_storage.py \
  tests/test_memoryos_locomo_full_runner.py \
  -v
```

结果: 37/37 tests OK。

```bash
uv run python -m compileall -q memory_benchmark tests
```

结果: exit 0。

当前精确断点: Task 9B implementation 已完成，等待独立 spec review；尚未标记完成。

### Task 9B spec review 1

- Reviewer: Hubble (`019e9d7c-7495-7a53-94cd-bde210bf8419`)
- Status: NEEDS_CHANGES

发现:

1. P1: resume reusable-state 检测只检查标准 `method_state/`，漏掉本项目早期
   runner 使用的根目录 `memoryos_state/`。仅残留 legacy method state 且无
   fingerprint 时会被错误当作空 run。
2. P1: `ProgressReporter` 在 fingerprint 校验前构造并执行 `set_stage()`，
   会先覆盖现有 `checkpoints/progress.json`，不符合 mismatch 必须在任何旧状态
   改写前失败的要求。
3. P2: 损坏的 fingerprint JSON 会泄漏底层 `JSONDecodeError`，没有转换成
   项目领域 `ConfigurationError`，且缺少回归测试。

审查验证:

- focused suite 37/37 通过。
- reviewer 使用临时行为探针分别复现以上三个缺口。

处理:

- 交回原 implementer 按 TDD 修复。
- 新测试必须覆盖 legacy `memoryos_state/`、mismatch 前 `progress.json` 字节不变、
  malformed fingerprint -> `ConfigurationError`。

当前精确断点: Task 9B spec-fix 待原 implementer 完成，再交同一 reviewer 复审。

### Task 9B spec re-review 2

- Reviewer: Hubble (`019e9d7c-7495-7a53-94cd-bde210bf8419`)
- Status: NEEDS_CHANGES

已确认修复:

- legacy `memoryos_state/` 非空目录已纳入 reusable-state 检测。
- fingerprint 校验已早于 `ProgressReporter` 创建和 `progress.json` 改写。
- malformed fingerprint 已转换为脱敏 `ConfigurationError`。

新增发现:

1. P1: `public_questions.jsonl` 和 `evaluator_private_labels.jsonl` 在 resume 时若
   同时存在会被直接保留，但未纳入 reusable-state 检测。两份陈旧 artifact 可在
   缺少 fingerprint 时存活并被错误信任。
2. P2: 原 `test_operational_error_survives_progress_exit_failure` 仍让 dataset load
   失败；由于 progress 现在在 fingerprint 校验后才构造，该测试已不会触发
   `ProgressReporter.__exit__()`，属于假绿测试。

处理:

- 把实际会被 resume 保留的 public/private question artifacts 纳入
  reusable-state 检测并增加回归测试。
- 调整 progress-exit failure 测试，让主流程在 progress 已进入后失败，并明确
  断言退出钩子确实执行且不遮蔽主异常。

当前精确断点: Task 9B 第二轮 spec-fix 待原 implementer TDD 修复。

### Task 9B final spec re-review

- Reviewer: Hubble (`019e9d7c-7495-7a53-94cd-bde210bf8419`)
- Status: APPROVED

最终确认:

- public/private question artifacts 已纳入 reusable-state 检测。
- 缺失 fingerprint 与旧 fingerprint 两种 artifact-only 情况均有行为测试。
- progress-exit 测试已真正进入 scope、触发次生退出异常，并保留原始异常对象。
- fingerprint 校验仍早于 progress 创建和所有状态复用/改写。
- legacy state、malformed fingerprint、summary 过滤、脱敏日志和 atomic overwrite
  要求均符合 Task 9B 规格。

验证:

- focused suite 42/42 tests OK。
- `compileall` exit 0。

当前精确断点: Task 9B spec review 已通过，下一步独立 code quality review。

### Task 9B code quality review 1

- Reviewer: Bohr (`019e9d85-ffed-79b0-ac9d-4127e508b712`)
- Status: NEEDS_CHANGES

发现:

1. P1: public/private question artifacts 分别原子写入，但不是跨文件事务。若 public
   替换成功、private 替换失败，下一次 resume 看到两文件都存在会跳过重写，
   使新 public 与旧 private 永久不一致。reviewer 已用行为探针复现。
2. P2: malformed fingerprint 当前使用 `raise ConfigurationError(...) from exc`，
   外层消息虽脱敏，但 `JSONDecodeError.doc` 仍保留原始损坏文档；完整 traceback
   可能暴露敏感内容。现有测试只检查外层异常字符串。

处理:

- fingerprint 校验通过后，每次运行都确定性重写 public/private artifacts，不再用
  “两文件都存在”作为跳过条件；增加首次部分失败、第二次重试恢复一致性的测试。
- malformed fingerprint 转换时抑制包含原文的异常 cause，并测试格式化后的完整异常链
  不包含 sentinel。

当前精确断点: Task 9B quality-fix 待原 implementer 按 TDD 完成。

### Task 9B final code quality re-review

- Reviewer: Bohr (`019e9d85-ffed-79b0-ac9d-4127e508b712`)
- Status: APPROVED

最终确认:

- fingerprint 校验通过后，每次 run/resume 都确定性重写 public/private artifact 对。
- 回归测试真实模拟 private 写失败，并验证下一次 retry 恢复两份当前数据产物。
- malformed fingerprint 的转换异常不保留包含原文的 cause/context，完整格式化异常链
  不包含 sentinel。
- 未发现新的正确性、可维护性或回归问题。

验证:

- focused suite 43/43 tests OK。
- `compileall` exit 0。

Task 9B 结论: **已完成并通过 spec review 与 code quality review**。

当前精确断点: 进入 Task 9C，执行完整回归、fake runner 验证、文档状态收口和最终整体 review。

### Task 9C 主控验证与文档收口

Focused suite:

```bash
uv run python -m unittest \
  tests/test_observability_run_context.py \
  tests/test_observability_progress.py \
  tests/test_experiment_storage.py \
  tests/test_run_logger.py \
  tests/test_memoryos_locomo_full_runner.py \
  tests/test_documentation_standards.py \
  -v
```

结果: 62/62 tests OK。

Full suite:

```bash
uv run python -m unittest discover -s tests -v
```

结果: 144/144 tests OK。包含一次真实 `gpt-4o-mini` API smoke，终端输出未显示
API key 或 base URL。

Fake runner:

```bash
uv run python -m unittest tests/test_memoryos_locomo_full_runner.py -v
```

结果: 25/25 tests OK。

Compile:

```bash
uv run python -m compileall -q memory_benchmark tests
```

结果: exit 0。

文档更新:

- README 补充完整规范化 Dataset hash 和严格 resume 规则。
- 设计草案标记 Phase A/B Task 1-9 已完成，并记录最终验证数字和实际强化项。
- 实施计划标记为 2026-06-06 COMPLETE；未勾选框仅保留原始 TDD 执行流程。
- 修正实施计划中残留的 `logs/progress.json` 为
  `checkpoints/progress.json`。

当前精确断点: Task 9C 主控验证已通过，下一步最终整体 review；review 通过前不关闭 Phase A/B。

### Task 9C final overall review

- Reviewer: Volta (`019e9d8e-fe4a-7581-9ef0-fad265bac0c2`)
- Reasoning effort: `xhigh`
- Status: NEEDS_CHANGES

发现:

1. P1: 缺少 `manifest.json` 时 `_validate_resume_metadata()` 直接返回，即使已有
   fingerprint、状态和不匹配的 `config.redacted.json`，仍会 attach/reuse 旧
   MemoryOS 状态。reviewer 已用行为探针复现。
2. P1: score 存在但 prediction 缺失时，runner 仅按 score id 认定 question 已完成并
   跳过回答；summary 也按 score 数计完成。探针结果可出现 3 个 completed question
   但只有 2 条 prediction。
3. P1: append-only JSONL 出现崩溃导致的截断尾行时，`read_jsonl()` 直接抛
   `JSONDecodeError`。即使 canonical/legacy 另一侧完整，reconciliation 也无法恢复，
   必须人工修文件。
4. P2: `full_run_finished` 在退出 progress context 前写入。若业务成功但
   `ProgressReporter.__exit__()` 失败，同一 attempt 会同时记录
   `full_run_finished` 和 `full_run_failed`。
5. P3: 设计草案和实施计划提前声明 Phase A/B complete，与 `AGENTS.md` 和 handoff
   的 pending 状态冲突。

审查确认:

- focused suite 当时仍为 62/62，但以上场景不在现有覆盖内。
- verdict 为 NEEDS_CHANGES，因此 Phase A/B 不能关闭。

### Task 9D systematic debugging 根因结论

已读取并遵循 `superpowers:systematic-debugging`，完成 Phase 1 根因追踪:

1. Resume metadata 根因:
   - fingerprint 只证明 Dataset 一致，不证明 run shape 或 method config 一致。
   - 当前 metadata 校验把 manifest 当作可选入口；manifest 缺失时连已有 redacted
     config 也不校验。
   - 必须把“已有可复用状态/fingerprint 时，manifest 和 config metadata 必须完整”
     固化成显式不变量。
2. Prediction/score 根因:
   - `completed_question_ids = set(score_records_by_question_id)` 只以 score 为完成依据。
   - runner 没有在 resume 后校验 `score_ids <= prediction_ids`。
   - summary 读取全部 score 并直接计数，导致审计产物不完整时仍宣称完成。
   - 必须把“每条 score 必须有同 id prediction”作为 resume 强约束；prediction-only
     仍允许复用并补评分。
3. Torn JSONL 根因:
   - append-only writer 一次写一行，但进程可能在最后一行换行前中断。
   - 通用 `read_jsonl()` 当前无法区分中间坏行与无换行的截断尾行。
   - 可安全自动恢复的唯一范围是：仅最后一个非空行、文件末尾没有换行、该行 JSON
     解析失败。中间坏行、带换行的完整坏行或非 dict 记录必须报领域错误，不能静默丢弃。
   - reconciliation 应能忽略单侧可确认的截断尾行，再由完整 alias 恢复并原子重写两侧。
4. Lifecycle 根因:
   - 成功事件位于 `_progress_scope` 内部，早于 `__exit__`。
   - 必须先成功退出 progress scope，再写唯一 `full_run_finished`；任何退出失败只能产生
     `full_run_failed`。
5. 文档状态:
   - 已立即回退为 final review remediation，不能在重新审查前写 COMPLETE。

### Task 9D 推荐 TDD 拆分

建议下一窗口继续使用 Subagent-Driven，但按最新规则按复杂度选择 reasoning effort:

#### Task 9D-1: runner resume invariants and terminal lifecycle

建议 implementer reasoning: `high`。

允许修改:

- `memory_benchmark/runners/memoryos_locomo_full.py`
- `tests/test_memoryos_locomo_full_runner.py`

测试先行:

1. 已有匹配 fingerprint、状态和不匹配 redacted config，但 manifest 缺失:
   - 必须 `ConfigurationError`。
   - 不构造 MemoryOS，不 attach，不改 prediction/score/status/progress。
2. 已有 score 但缺同 id prediction:
   - 必须在 MemoryOS 构造和 question skip 前 `ConfigurationError`。
   - prediction-only 继续允许补评分，已有测试必须保持通过。
3. 成功业务流程后 progress `__exit__` 失败:
   - events 只能有 `full_run_failed`，不能有 `full_run_finished`。
   - 原始 progress-exit 异常正常传播。

设计建议:

- `_validate_resume_metadata()` 在存在可复用 resume metadata/state 时要求 manifest。
- 无 manifest 但 config/state/fingerprint 存在不能静默继续。
- 增加独立 `_validate_prediction_score_consistency(...)`，明确
  `score_ids - prediction_ids` 报错；不要把 score-only 自动降级成重答，因为已有 score
  的来源不可审计。
- 将 summary/finished event 结果暂存，退出 `_progress_scope` 成功后再记录
  `full_run_finished` 和 return。

#### Task 9D-2: torn-tail JSONL recovery

建议 implementer reasoning: `high`，与 9D-1 写集冲突较少但测试文件可能冲突，最好顺序执行。

允许修改:

- `memory_benchmark/storage/jsonl.py`
- `memory_benchmark/runners/memoryos_locomo_full.py`
- `tests/test_experiment_storage.py`
- `tests/test_memoryos_locomo_full_runner.py`

测试先行:

1. `read_jsonl()` 正常文件行为不变。
2. 可选 recovery 模式只忽略“无末尾换行且最后一行 JSON 损坏”的截断尾行。
3. 中间坏行、最后坏行但已有换行、非 dict JSON 仍明确失败。
4. canonical prediction 尾行截断、legacy 完整时，resume reconciliation 恢复完整记录并
   原子重写两侧。
5. canonical 与 legacy 都只有相同截断且没有完整记录时，不应假装完成；后续按可用完整
   records 继续或明确报错，需 implementer/reviewer基于不变量选择最保守行为。

设计建议:

- 不要让通用 `read_jsonl()` 默认静默容错；增加显式参数或专用读取结果，只有
  reconciliation 路径启用 torn-tail recovery。
- 返回记录之外最好能表明是否丢弃过截断尾行，便于 reconciliation 决定和测试。
- JSON 错误信息必须脱敏，不把整行私有 label 或 prediction 内容放进异常。

#### Task 9D-3: reviews and full verification

1. 9D-1 spec review -> quality review。
2. 9D-2 spec review -> quality review。
3. focused suite。
4. full suite。
5. fake runner suite。
6. compileall。
7. 更新 README/spec/plan/handoff 的真实最终数字。
8. 新的 `xhigh` final overall review。
9. 只有最终 APPROVED 后，才把 Phase A/B 和计划写成 COMPLETE。

### 当前暂停状态

- 用户报告 5h 额度和上下文即将耗尽，已停止代码修改。
- OpenCode 当前不参与，也没有派发任务。
- `AGENTS.md` 已更新为 Task 9D final-review remediation。
- 设计草案和实施计划已从 COMPLETE 回退为整改中。
- 当前没有运行中的必要 shell session。
- Volta final reviewer 已完成，可关闭。

恢复时严格顺序:

1. 读 `AGENTS.md`。
2. 读本 handoff 最后约 300 行，从 “Task 9C final overall review” 开始。
3. 检查工作区实际文件，确认没有中断期间外部改动。
4. 更新 task plan 为 9D-1 in progress。
5. 派 high-reasoning implementer 按 TDD 做 9D-1，不要直接跳到修代码。

最后已验证基线（修复前）:

- focused: 62/62 OK。
- full: 144/144 OK，含真实 API smoke。
- fake runner: 25/25 OK。
- documentation: 4/4 OK。
- compileall: exit 0。

注意: 这些测试数字不能证明 Task 9D 已解决；最终 reviewer 已用额外行为探针稳定复现
上述缺口。

### 2026-06-11 Subagent 策略更新

用户新增了 OpenCode subagent skill，用于未来在 Codex 额度不足时承担可验收的任务。
当前决定:

- OpenCode skill 已检查，支持 workspace-local server、命名 session、continue/fork、
  async watch、messages/diff 检查和失败处理，当前能力足够，不修改 skill。
- OpenCode 当前仍禁止启动，必须等用户明确允许。
- 新增 `docs/subagent-strategy.md`，统一规定 Codex/OpenCode subagent 的选择规则。
- Codex subagent 不再默认使用最高模型或高推理；根据任务复杂度选择最低合理规格。
- 初始基线:
  - 机械任务: `gpt-5.4-mini medium`
  - 小型明确实现: `gpt-5.4-mini high`
  - 一般跨文件实现/review: `gpt-5.4 high`
  - 复杂调试/关键契约: `gpt-5.5 high`
  - 架构/最终整体审查: `gpt-5.5 xhigh`
- 根据遗漏、返工、review 结果动态升级；连续稳定通过后可降级节省额度。
- handoff 后续要记录 subagent 模型、推理强度、返工次数和同类任务的调整结论。

当前业务断点未改变: 仍从 Task 9D-1 继续。

### 2026-06-11 Task 9D-1 实现与审查进度

Implementer:

- 类型: Codex worker。
- 模型: `gpt-5.5`。
- reasoning effort: `high`。
- agent: Carson (`019eb481-91cc-7cc0-9cbb-d1f6aed78a87`)。
- 写范围:
  - `memory_benchmark/runners/memoryos_locomo_full.py`
  - `tests/test_memoryos_locomo_full_runner.py`

已完成并观察到 RED 的行为:

1. 缺少 manifest 时旧实现未报错。
2. score-only 记录未报错。
3. progress 成功路径退出失败时同时写 finished/failed。
4. manifest 不含 `memoryos_config` 且无 `config.redacted.json` 时旧实现仍继续运行。

当前实现:

- resume metadata 校验已提前到 alias/status/progress 业务状态改写之前。
- score id 必须是 prediction id 子集。
- `full_run_finished` 已移到 progress context 成功退出之后。
- manifest 不含 method config 时，必须由 `config.redacted.json` 提供兼容配置。

当前验证:

- fake runner: 29/29 OK。
- scoped compileall: exit 0。

Spec review:

- Reviewer: Kant (`019eb485-3270-7ad2-b4ba-e52b8cab72cc`)。
- 模型: `gpt-5.4`。
- reasoning effort: `high`。
- 首轮发现 1 个有效 P1: 两个 method config 来源都缺失时仍会通过。
- implementer 按 TDD 修复后复审: APPROVED。
- 返工次数: 1。

Code quality review:

- Reviewer: Maxwell (`019eb489-44e1-7d11-a6a2-7c08c50ec4a1`)。
- 模型: `gpt-5.4`。
- reasoning effort: `high`。
- 状态: NEEDS_CHANGES。
- 采纳:
  1. score/prediction 不一致检查前 alias reconciliation 已可能改写业务产物，应先纯内存
     preflight，再持久化。
  2. manifest 与 redacted config 同时存在时应同时校验，不能忽略 stale config。
  3. malformed manifest/redacted config 应转换为脱敏 `ConfigurationError`。
- 不采纳:
  - “resume 校验失败前不能写 full_run_started/run.log”。原规格禁止修改的是
    prediction/score/status/progress；启动和失败日志是必要审计记录，不属于可复用业务状态。

当前精确断点:

- 原 implementer 正待按 TDD 修复上述 3 个 code-quality 问题。
- 修复后重新进行 code-quality review。
- Task 9D-1 通过前不要进入 Task 9D-2。

### 2026-06-11 Task 9D-1 完成

Code-quality remediation RED:

1. score-only 拒绝前 canonical prediction alias 被提前改写。
2. manifest 配置匹配时 stale `config.redacted.json` 被忽略。
3. malformed manifest/redacted config 暴露原始 `JSONDecodeError`。

最终实现:

- canonical/legacy JSONL 先纯内存合并和冲突检查。
- score/prediction 一致性通过后才持久化 alias 和 status migration。
- manifest 与已存在的 redacted config 都必须兼容。
- malformed resume metadata 统一转换为脱敏 `ConfigurationError`，不保留原始异常链。
- 启动/失败审计日志仍允许在 preflight 失败时写入；业务产物保持不变。

最终验证:

- fake runner: 33/33 OK。
- scoped compileall: exit 0。

Final code-quality re-review:

- Reviewer: Maxwell (`019eb489-44e1-7d11-a6a2-7c08c50ec4a1`)。
- 模型: `gpt-5.4`。
- reasoning effort: `high`。
- 结论: APPROVED。
- implementer 总返工次数: 2。

Task 9D-1 结论: **已完成并通过 spec review 与 code-quality review**。

当前精确断点: 进入 Task 9D-2 torn-tail JSONL recovery，继续按 TDD 和双 review 执行。

### 2026-06-11 额度风险暂停交接

用户报告 5h 额度即将耗尽，已立即停止后续实现。

暂停时状态:

- Task 9D-1 已完成，spec review 和 code-quality review 均 APPROVED。
- 最新验证:
  - `tests/test_memoryos_locomo_full_runner.py`: 33/33 OK。
  - scoped compileall: exit 0。
- Task 9D-2 **尚未开始**:
  - 未派发 implementer。
  - 未修改 `memory_benchmark/storage/jsonl.py`。
  - 未修改 `tests/test_experiment_storage.py`。
- 所有本轮 Codex subagent 均已关闭，没有运行中的 agent 或必要 shell session。
- OpenCode 仍未启用。

下次恢复严格顺序:

1. 读 `AGENTS.md`。
2. 读本 handoff 最后约 180 行。
3. 检查以下文件的当前内容和时间戳，确认没有外部改动:
   - `memory_benchmark/runners/memoryos_locomo_full.py`
   - `tests/test_memoryos_locomo_full_runner.py`
   - `memory_benchmark/storage/jsonl.py`
   - `tests/test_experiment_storage.py`
4. 将 task plan 保持为 Task 9D-2 in progress。
5. 按 Task 9D-2 既定 TDD 范围实施:
   - 通用 `read_jsonl()` 默认保持严格。
   - 只显式恢复最后一个非空行、文件末尾无换行、且该行 JSON 解析失败的情况。
   - 中间坏行、带换行的坏尾行、非 dict JSON 必须失败。
   - canonical 截断而 legacy 健康时，alias reconciliation 应恢复并原子写回两侧。
   - 两侧都截断时只能使用截断前完整记录，不能把损坏记录视为完成。
6. 完成后执行 spec review、code-quality review，再进入 Task 9C 全量验证。

Subagent 成本策略调整:

- 用户明确要求进一步降低额度消耗。
- Task 9D-2 规格已经非常明确，首选 `gpt-5.4-mini high` 或
  `gpt-5.4 medium`，不要直接使用 `gpt-5.5 high`。
- 一般 spec/quality review 首选 `gpt-5.4 medium`；机械核验可用
  `gpt-5.4-mini high`。
- `gpt-5.5 medium` 只用于确实复杂的关键契约调试。
- `high/xhigh` 仅在较低档失败、任务跨模块高风险或最终整体审查确有必要时使用。
- 已同步更新 `docs/subagent-strategy.md` 和 `AGENTS.md`。

当前精确断点:

> Task 9D-2 尚未开始。恢复后从 torn-tail JSONL 的第一个 RED 测试开始，不要重复
> Task 9D-1，也不要提前跑 Task 9C。

### 2026-06-11 上下文压缩与流程加速提案

用户认为当前推进速度过慢，并指出项目现阶段仍属于小型项目，不应继续为每个小改动
执行完整 implementer -> spec review -> quality review -> full verification 流程。

主控判断:

- 该判断成立。前一阶段在边界场景上投入了过多 review 轮次，流程成本已经超过多数代码
  修改本身。
- 严格 resume、private/public 隔离和真实实验产物不能降低正确性标准；可以删除的是重复
  仪式，而不是这些核心不变量。
- 推荐切换到“轻量工程模式”，待用户确认后写入 `AGENTS.md`。

推荐轻量模式:

1. 边界清晰、修改不超过约 3 个文件的任务由主 Codex 直接完成，不默认派 implementer。
2. 不再对每个小 task 分别做 spec review 和 quality review；一个完整功能切片完成后只做
   一次综合 review。
3. TDD 只强制用于 bug、resume/隐私/指标等关键契约；纯文档、命名、显然的机械调整可
   直接修改后验证。
4. 开发中只运行相关 focused tests；full suite 只在阶段收口、公共协议改动或发布前运行。
5. subagent 只用于真正可并行的独立工作、复杂调查或最终综合审查，不再作为每一步的
   固定流水线。
6. handoff 只在关键里程碑、上下文/额度风险或长任务中断前更新，不再记录每个微小
   review 往返。
7. Task 9D-2 采用最小实现范围；通过 focused tests 后与 Task 9D-1 一起做一次综合 review，
   然后立即进入最终全量验证。
8. Phase A/B 关闭后，不继续打磨 observability 的理论边界；优先推进 LongMemEval 与
   可实际运行的统一 benchmark 闭环。

不推荐的两个极端:

- 继续当前严格模式: 正确性高，但对当前项目规模明显过重。
- 完全取消 TDD/review/full verification: 速度最快，但会直接威胁长实验断点和私有数据
  边界，不可接受。

用户澄清:

- 不跳过任务，也不为了加速提前关闭 Phase A/B。
- 任务仍然一步一步完成。
- 只有真正可并行时才并行；存在依赖时必须串行。
- 主要需要删除的是过多、重复的 review 环节。

最终采用的流程:

1. 默认串行，小步完成并 focused verification。
2. 只有无前置依赖、写集不冲突、可独立验收时并行。
3. 普通局部修改不再固定做 spec + quality 双 review。
4. 一个完整功能切片结束后做一次综合 review。
5. resume、隐私、指标、公共协议等高风险契约可单独 review。
6. 阶段验收前保留 full suite 和最终整体 review。
7. Review 发现问题后由同一 reviewer 复审，不叠加重复 reviewer。

该规则已同步写入 `AGENTS.md` 和 `docs/subagent-strategy.md`。

当前压缩交接:

- 业务断点仍是 Task 9D-2 尚未开始。
- Task 9D-1 已完成，fake runner 33/33，scoped compileall exit 0。
- OpenCode 未启用，无运行中的 agent 或 shell session。
- 下一窗口先读 `AGENTS.md` 和本 handoff 尾部，然后串行实施 Task 9D-2；通过 focused
  tests 后做一次综合 review，再决定下一步，不提前关闭 Phase A/B。

### 2026-06-11 Task 9D-2 与 Task 9C 主控验证完成

Task 9D-2 实现:

- `read_jsonl()` 新增默认关闭的 `recover_torn_tail` 关键字参数。
- 只有 JSON 解析失败、位于最后一个非空物理行且该行没有行终止符时才允许丢弃。
- 默认读取、中间坏行、带行终止符的坏尾行和非 dict JSON 继续严格失败。
- MemoryOS-LoCoMo runner 只在 resume canonical/legacy alias 纯内存对账时显式启用恢复。
- 健康 alias 可以补回另一侧截断记录；两侧都截断时只复用完整记录，损坏问题重新回答。
- 对账通过后仍使用原子 JSONL 重写统一两侧 alias。

Task 9D-2 验证与 review:

- 新增 5 个存储层边界测试和 2 个 runner 自愈测试。
- 存储层 + fake runner 相关测试: 58/58 OK。
- scoped compileall: exit 0。
- 综合 reviewer Herschel（`gpt-5.4 medium`）: APPROVED。
- reviewer 仅记录两个非阻塞重复覆盖缺口：runner 层没有再次测试带换行坏尾行，
  也没有专门构造 UnicodeDecodeError；核心严格行为已在存储层和直接传播路径覆盖。

Task 9C 最新主控验证:

- focused suite: 77/77 OK。
- full suite: 159/159 OK，包含真实 `gpt-4o-mini` API smoke。
- fake runner: 35/35 OK。
- `uv run python -m compileall -q memory_benchmark tests`: exit 0。
- 文档已更新为“整改与全量验证通过，等待最终整体审查”，未提前关闭 Phase A/B。

当前精确断点:

> 下一步只执行一次最终整体审查。审查通过后再更新 README/spec/plan/handoff 和
> `AGENTS.md` 的阶段状态；审查前 Phase A/B 仍未关闭。

### 2026-06-11 Phase A/B 最终整体审查完成

最终 reviewer Ampere（`gpt-5.5 high`）首轮发现:

1. resume 会接受 planned question 范围外的 prediction/score，导致
   `completed_questions > total_questions` 并污染 overall F1。
2. 成功运行的 `progress.json` 仍保留最后一个 current conversation/question id。

主控按 TDD 串行修复:

- 新增本次计划的 `question_id -> conversation_id` 映射。
- alias 合并和 score/prediction 一致性校验后、业务产物改写前，拒绝计划外记录和
  conversation_id 错配记录。
- 成功收尾时通过现有 ProgressReporter 更新接口清空 current id，再写最终快照。
- 新增计划外记录、conversation_id 错配和成功终态 ID 清空测试。

同一 reviewer 复审:

- 结论: APPROVED。
- reviewer 独立复现未知记录会在产物改写前失败、已有文件保持不变、正常结果为 3/3，
  且终态 current id 为 None/None。

最终验证:

- focused suite: 79/79 OK。
- full suite: 161/161 OK，包含真实 `gpt-4o-mini` API smoke。
- fake runner: 37/37 OK。
- `uv run python -m compileall -q memory_benchmark tests`: exit 0。

Phase A/B 结论: **已完成并通过最终整体审查**。

下一步:

> 单独对齐 Phase C src-layout 迁移计划。该阶段会移动包目录，属于实质性架构变化；
> 用户确认前不实施。Phase D pytest 迁移继续后置。
