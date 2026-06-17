# Dataset Variant 与 LongMemEval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 benchmark-owned dataset variant 契约，并让 LongMemEval 的 S/M cleaned 数据通过统一 prediction/run 入口形成独立、可恢复、可离线评测的 child runs。

**Architecture:** benchmark registration 负责 concrete variant、数据源和 smoke/full preparation；command service 负责 selector 展开、child run identity 与批次结果；底层 prediction runner 仍只执行一个已准备好的 concrete dataset。manifest 升级到 v2，并把 variant 与 run scope 纳入不可变 resume 身份。

**Tech Stack:** Python 3.12、dataclasses、StrEnum、pytest、现有 registry/runner/storage/CLI、uv。

---

## 文件职责

- 新建 `src/memory_benchmark/benchmark_adapters/contracts.py`
  - 定义 `RunScope`、variant/load/prepared-run 契约和 selector 解析。
- 修改 `src/memory_benchmark/benchmark_adapters/registry.py`
  - 注册 LoCoMo/LongMemEval variants，并把 benchmark-specific preparation 收口到 registration。
- 修改 `src/memory_benchmark/benchmark_adapters/locomo.py`
  - 为 full dataset 补齐稳定 variant/run-scope metadata；保留已有 smoke builder。
- 修改 `src/memory_benchmark/benchmark_adapters/longmemeval.py`
  - 支持 `s_cleaned`、`m_cleaned`，保证 source/split/variant metadata 与 private label 隔离。
- 修改 `src/memory_benchmark/runners/prediction.py`
  - manifest schema v2 纳入 concrete variant/run scope，并拒绝 v1 resume。
- 修改 `src/memory_benchmark/cli/run_prediction.py`
  - 从单 run 装配升级为全 child 预检后串行执行的批次服务。
- 修改 `src/memory_benchmark/cli/commands.py`
  - 定义稳定批次结果，并让 `run` 对每个 child 独立 evaluate。
- 修改 `src/memory_benchmark/cli/main.py`
  - 接收 `--variant`，不在 argparse 硬编码 benchmark-specific choices。
- 修改相关 `__init__.py`
  - 只暴露稳定公共类型。
- 新增或修改 focused tests
  - variant contract、LongMemEval adapter、manifest/resume、batch atomicity、CLI/run。

当前目录不是 Git 仓库，因此以下任务不执行 commit；每个任务以 focused tests 通过、计划勾选和 handoff 更新作为检查点。

### Task 1: Benchmark Variant Contract 与 Preparation Hook

**Files:**
- Create: `src/memory_benchmark/benchmark_adapters/contracts.py`
- Modify: `src/memory_benchmark/benchmark_adapters/registry.py`
- Modify: `src/memory_benchmark/benchmark_adapters/__init__.py`
- Modify: `src/memory_benchmark/benchmark_adapters/locomo.py`
- Test: `tests/test_benchmark_registry.py`

- [x] **Step 1: 写 variant contract 的失败测试**

测试应覆盖：

```python
def test_registration_rejects_duplicate_variants() -> None: ...
def test_registration_rejects_all_as_concrete_variant() -> None: ...
def test_registration_rejects_unsafe_source_path() -> None: ...
def test_selector_uses_default_and_declared_order() -> None: ...
def test_locomo_preparation_owns_smoke_behavior(tmp_path: Path) -> None: ...
```

断言未知 selector 的 `ConfigurationError` 同时包含请求值与允许值；LoCoMo prepared dataset 的 metadata 必须包含：

```python
{"variant": "locomo10", "run_scope": "smoke"}
```

- [x] **Step 2: 运行测试并确认 RED**

Run:

```bash
uv run pytest tests/test_benchmark_registry.py -q
```

Expected: FAIL，原因是 contracts、variants 或 `prepare_run` 尚不存在。

- [x] **Step 3: 实现最小 benchmark-owned contract**

在 `contracts.py` 定义：

```python
class RunScope(StrEnum):
    SMOKE = "smoke"
    FULL = "full"


@dataclass(frozen=True)
class BenchmarkVariantSpec:
    name: str
    source_relative_paths: tuple[Path, ...]


@dataclass(frozen=True)
class BenchmarkLoadRequest:
    variant: str
    run_scope: RunScope
    smoke_turn_limit: int = 20
    smoke_conversation_limit: int = 1


@dataclass(frozen=True)
class PreparedBenchmarkRun:
    variant: str
    run_scope: RunScope
    dataset: Dataset
    source_relative_paths: tuple[Path, ...]
```

并实现纯函数：

```python
def resolve_variant_selector(
    registration: BenchmarkRegistration,
    selector: str | None,
) -> tuple[str, ...]:
    ...
```

`BenchmarkRegistration.__post_init__()` 强校验 variant/default/path；`prepare()` 调用 hook 后校验返回 variant、scope、dataset metadata。LoCoMo preparation hook 消费现有 `build_locomo_smoke_dataset()`，通用 runner 不再承担该逻辑。

- [x] **Step 4: 运行 focused tests**

Run:

```bash
uv run pytest tests/test_benchmark_registry.py tests/test_locomo_conversation_adapter.py -q
```

Expected: PASS。

- [x] **Step 5: 主线程检查边界**

确认：

- `all` 只存在于 selector 解析；
- registration 顶层不再保存单一静态 `source_relative_paths`；
- source path 是相对路径且不能含 `..`；
- LoCoMo 默认 adapter 构造仍可用。

### Task 2: LongMemEval S/M Variant Adapter

**Files:**
- Modify: `src/memory_benchmark/benchmark_adapters/longmemeval.py`
- Modify: `src/memory_benchmark/benchmark_adapters/registry.py`
- Test: `tests/test_longmemeval_conversation_adapter.py`
- Test: `tests/test_benchmark_registry.py`

- [x] **Step 1: 写 S/M 与 smoke 完整历史的失败测试**

测试应覆盖：

```python
def test_default_variant_is_s_cleaned() -> None: ...
def test_m_cleaned_loads_500_instances() -> None: ...
def test_unknown_variant_fails() -> None: ...
def test_variant_metadata_matches_actual_source() -> None: ...
def test_longmemeval_smoke_keeps_complete_first_instance() -> None: ...
def test_m_variant_public_payload_does_not_leak_private_labels() -> None: ...
```

完整历史通过比较：

```python
full_first = LongMemEvalAdapter(ROOT, variant="s_cleaned").load(limit=1)
prepared = registration.prepare(ROOT, smoke_request)
assert prepared.dataset.conversations[0].sessions == full_first.conversations[0].sessions
```

- [x] **Step 2: 运行测试并确认 RED**

Run:

```bash
uv run pytest tests/test_longmemeval_conversation_adapter.py tests/test_benchmark_registry.py -q
```

Expected: FAIL，原因是 adapter 尚不接受 variant，LongMemEval prediction 尚未开放。

- [x] **Step 3: 实现 variant-aware adapter**

使用稳定映射：

```python
LONGMEMEVAL_VARIANT_PATHS = {
    "s_cleaned": "data/longmemeval/longmemeval_s_cleaned.json",
    "m_cleaned": "data/longmemeval/longmemeval_m_cleaned.json",
}
```

构造函数保存 concrete variant；所有 Dataset/Conversation source metadata 使用当前路径。registration 声明顺序固定为 S、M，default 为 S，`prediction_enabled=True`。smoke hook 只 `load(limit=1)`，不裁剪 session/turn。

- [x] **Step 4: 运行真实数据结构测试**

Run:

```bash
uv run pytest tests/test_longmemeval_conversation_adapter.py tests/test_benchmark_registry.py -q
```

Expected: PASS，S/M 各 500 instances。

- [x] **Step 5: 运行私有边界回归**

Run:

```bash
uv run pytest tests/test_conversation_dataset_validation.py tests/test_longmemeval_conversation_adapter.py -q
```

Expected: PASS。

### Task 3: Prediction Manifest v2 与 Resume Identity

**Files:**
- Modify: `src/memory_benchmark/runners/prediction.py`
- Test: `tests/test_prediction_runner.py`
- Test: `tests/test_artifact_evaluation_runner.py`

- [x] **Step 1: 写 manifest v2 和兼容策略失败测试**

新增测试：

```python
def test_manifest_v2_records_variant_and_run_scope(tmp_path: Path) -> None: ...
def test_resume_rejects_variant_change(tmp_path: Path) -> None: ...
def test_resume_rejects_scope_change(tmp_path: Path) -> None: ...
def test_v1_manifest_cannot_resume_through_v2_runner(tmp_path: Path) -> None: ...
def test_v1_artifacts_remain_evaluable(tmp_path: Path) -> None: ...
```

底层 API 显式接收：

```python
benchmark_variant="s_cleaned"
run_scope=RunScope.SMOKE
```

- [x] **Step 2: 运行测试并确认 RED**

Run:

```bash
uv run pytest tests/test_prediction_runner.py tests/test_artifact_evaluation_runner.py -q
```

Expected: FAIL，manifest 仍为 schema v1。

- [x] **Step 3: 实现 v2 manifest**

`run_predictions()`、`_preflight_prediction_run()` 和内部 artifact builder 增加 concrete variant/run scope 参数。manifest 固定包含：

```python
{
    "schema_version": 2,
    "benchmark_variant": benchmark_variant,
    "run_scope": run_scope.value,
}
```

resume 读取 existing manifest 时：

- schema v1：给出“artifact-only evaluation 可继续，但 v2 service 不能 resume”的领域错误；
- schema v2：完整 dict 比较，variant/scope 任一变化均拒绝。

artifact-only evaluator 不新增 schema 限制，继续读取 v1/v2 共同字段。

- [x] **Step 4: 运行 focused tests**

Run:

```bash
uv run pytest tests/test_prediction_runner.py tests/test_artifact_evaluation_runner.py -q
```

Expected: PASS。

- [x] **Step 5: 检查受保护 legacy 路径**

确认未修改 `memoryos_locomo_full.py` 的 legacy manifest/恢复协议，也未写入受保护输出目录。

### Task 4: Batch Registered Prediction 与原子预检

**Files:**
- Modify: `src/memory_benchmark/cli/run_prediction.py`
- Modify: `src/memory_benchmark/config/settings.py`（仅在需要修正两阶段加载调用时修改）
- Test: `tests/test_prediction_cli.py`
- Test: `tests/test_memoryos_registered_prediction.py`

- [x] **Step 1: 写 selector、run-id 和原子预检失败测试**

覆盖：

```python
def test_all_expands_in_registration_order() -> None: ...
def test_longmemeval_child_run_ids_include_variant() -> None: ...
def test_locomo_run_id_does_not_add_single_variant_suffix() -> None: ...
def test_resume_requires_explicit_base_run_id() -> None: ...
def test_second_child_preflight_failure_creates_no_output_or_method() -> None: ...
def test_openai_settings_load_only_after_all_preflights() -> None: ...
```

批次结果：

```python
@dataclass(frozen=True)
class PredictionVariantResult:
    variant: str
    run_id: str
    summary: PredictionRunSummary


@dataclass(frozen=True)
class PredictionBatchResult:
    benchmark: str
    selector: str
    runs: tuple[PredictionVariantResult, ...]
```

- [x] **Step 2: 运行测试并确认 RED**

Run:

```bash
uv run pytest tests/test_prediction_cli.py tests/test_memoryos_registered_prediction.py -q
```

Expected: FAIL，registered service 仍返回单 summary 且直接加载 secret。

- [x] **Step 3: 拆分 prepare/preflight/execute**

实现顺序：

```text
load_path_settings
-> registration + method/profile/cost validation
-> resolve concrete variants
-> prepare every benchmark child
-> build every run identity/context/manifest
-> preflight every child
-> load_openai_settings once
-> execute children sequentially
```

新增纯函数集中生成 child run ID；拒绝空 ID、路径逃逸、重复 suffix 和 child 冲突。禁止在全部 preflight 完成前调用：

- `RunContext.ensure_directories()`
- method `system_factory`
- `load_openai_settings()`

旧 `run_mem0_locomo_prediction()` 取批次中唯一 summary 返回，保持内部兼容。

- [x] **Step 4: 运行 focused tests**

Run:

```bash
uv run pytest tests/test_prediction_cli.py tests/test_memoryos_registered_prediction.py -q
```

Expected: PASS。

- [x] **Step 5: 检查通用性**

Run:

```bash
rg -n "build_locomo_smoke_dataset|benchmark_adapters\\.locomo" \
  src/memory_benchmark/cli/run_prediction.py
```

Expected: 无匹配。

### Task 5: CLI Commands、Run Batch 与 LongMemEval Evaluation

**Files:**
- Modify: `src/memory_benchmark/cli/commands.py`
- Modify: `src/memory_benchmark/cli/main.py`
- Modify: `src/memory_benchmark/cli/run_prediction.py`
- Modify: `src/memory_benchmark/benchmark_adapters/__init__.py`
- Modify: `src/memory_benchmark/runners/__init__.py`
- Test: `tests/test_main_cli.py`
- Test: `tests/test_evaluator_registry.py`
- Test: `tests/test_artifact_evaluation_runner.py`

- [x] **Step 1: 写 CLI 与 batch run 失败测试**

覆盖：

```python
def test_predict_accepts_variant_without_argparse_choices() -> None: ...
def test_unknown_variant_error_lists_allowed_values() -> None: ...
def test_longmemeval_is_prediction_choice() -> None: ...
def test_execute_predict_returns_batch_for_single_variant() -> None: ...
def test_execute_run_evaluates_each_child_independently() -> None: ...
def test_run_does_not_average_variant_metrics() -> None: ...
```

`PredictCommand` 新增 `variant: str | None = None`。`RunCommandResult` 使用：

```python
@dataclass(frozen=True)
class RunVariantResult:
    variant: str
    prediction: PredictionRunSummary
    evaluations: tuple[EvaluationRunSummary, ...]


@dataclass(frozen=True)
class RunCommandResult:
    benchmark: str
    selector: str
    runs: tuple[RunVariantResult, ...]
```

- [x] **Step 2: 运行测试并确认 RED**

Run:

```bash
uv run pytest tests/test_main_cli.py tests/test_evaluator_registry.py \
  tests/test_artifact_evaluation_runner.py -q
```

Expected: FAIL，CLI 尚无 `--variant` 且 run 只处理一个 summary。

- [x] **Step 3: 实现公共 command 结果**

CLI parser 增加自由字符串 `--variant`；command service 把值交给 benchmark registry 校验。`execute_run()` 遍历 prediction batch：

```python
for child in prediction_batch.runs:
    evaluations = execute_evaluate(
        EvaluateCommand(run_id=child.run_id, ...)
    )
```

每个 child 形成独立 `RunVariantResult`，不跨 variant 聚合。

- [x] **Step 4: 运行 CLI/command tests**

Run:

```bash
uv run pytest tests/test_main_cli.py tests/test_prediction_cli.py \
  tests/test_evaluator_registry.py tests/test_artifact_evaluation_runner.py -q
```

Expected: PASS。

- [x] **Step 5: 离线 LongMemEval 装配验证**

使用 monkeypatched/fake method 路径验证 `longmemeval + s_cleaned + smoke` 能准备一个完整 instance、生成 v2 manifest，并保持 private labels 分离。不得加载 `.env` 或触网。

### Task 6: 阶段回归、Review 与文档收口

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/current-roadmap.md`
- Modify: `docs/handoffs/2026-06-14-dataset-variant-longmemeval.md`
- Modify: 本计划勾选状态

- [x] **Step 1: 更新用户文档**

README 说明：

```text
--profile = method profile
--variant = benchmark dataset variant
LongMemEval variants = s_cleaned / m_cleaned / all
all creates independent child runs
predict and evaluate remain separated
```

- [x] **Step 2: 运行完整离线回归**

Run:

```bash
uv run pytest -q
uv run pytest -m api --collect-only -q
uv run pytest -m memoryos -q
uv run pytest tests/test_documentation_standards.py -q
uv run python -m compileall -q src/memory_benchmark tests
```

Expected: 全部通过，且不执行真实 API。

- [x] **Step 3: 校验受保护实验资产**

Run 项目既有聚合哈希命令，Expected：

```text
2bf09d4109396feb7af4eb174d21bff791afc1c03b5a8ba62180da1315df642f
```

- [x] **Step 4: 阶段级综合 review**

review 重点：

- runner 是否仍含具体 benchmark import；
- `all` 是否泄漏到 dataset/manifest；
- 全 child preflight 是否真的先于 secret、目录和 method；
- v1 evaluate/v2 resume 边界是否清楚；
- LongMemEval private labels 是否可能进入 public input；
- 单 variant 与 all 的 run ID 是否稳定且无碰撞。

- [x] **Step 5: 更新续航入口**

同步：

- `docs/current-roadmap.md` 勾选 Phase F 完成项；
- `AGENTS.md` 写最新验证基线和下一精确断点；
- handoff 记录改动、验证、review 结论和下一阶段；
- 本计划全部任务状态。
