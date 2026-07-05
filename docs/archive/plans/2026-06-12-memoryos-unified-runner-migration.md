# MemoryOS Unified Runner Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 MemoryOS 接入分层 TOML、能力注册表和通用 conversation-QA prediction/evaluation 流程，同时保留既有正式实验资产和旧 runner 的只读兼容边界。

**Architecture:** benchmark registry 声明 task family、required capabilities、数据来源和是否已开放 prediction；method registry 声明 provided capabilities、profile、system factory、source identity 和恢复 hook。统一 prediction service 负责 adapter、profile、method、RunContext 和 generic runner 的装配，不再为 MemoryOS 新增专用全量 runner。MemoryOS 继续使用官方 `eval/` 算法，resume 只恢复已经完成写入的 conversation，不伪造逐 turn 幂等能力。

**Tech Stack:** Python 3.12、dataclass、StrEnum、TOML/tomllib、pytest、Rich、uv、现有 OpenAI 与 sentence-transformers 依赖。

---

## 实施边界

- 当前目录不是 git repository，因此本计划不包含 commit 步骤。
- 不修改 `third_party/methods/MemoryOS-main/`。
- 不删除或覆盖 `outputs/memoryos-locomo-full-20260603/`。
- 不让新 generic runner 自动续跑旧 `memoryos_locomo_full` run；旧 run 继续由旧入口解释。
- 不把 MemoryOS 强行实现成 `BaseResumableMemorySystem`。官方写入单位是 QA page，并不能提供
  通用 runner 所要求的逐 turn 已确认边界。
- MemoryOS 初始 `max_workers=1`。在完成独立线程安全验证前，不并发共享同一个
  MemoryOS wrapper。
- 新路径只生成 prediction；F1 和 LLM judge 均通过已有 artifact evaluator 独立执行。

## 文件结构

### Core 与 benchmark 声明

- Create: `src/memory_benchmark/core/capabilities.py`
  - 定义 `TaskFamily`、`MethodCapability` 和 capability 兼容校验。
- Modify: `src/memory_benchmark/core/__init__.py`
  - 导出稳定枚举和兼容校验。
- Modify: `src/memory_benchmark/benchmark_adapters/registry.py`
  - 从仅保存 adapter class 扩展为保存 `BenchmarkRegistration`。
- Modify: `src/memory_benchmark/benchmark_adapters/__init__.py`
  - 导出 registration 查询和 prediction-ready 列表。
- Modify: `src/memory_benchmark/benchmark_adapters/locomo.py`
  - 接收 LoCoMo smoke 数据裁剪职责。

### Method 与 prediction 装配

- Modify: `src/memory_benchmark/methods/registry.py`
  - 声明 capability、factory、source identity、model/max-worker getter 和 resume 恢复 hook。
- Modify: `src/memory_benchmark/cli/run_prediction.py`
  - 提炼 `run_registered_conversation_qa_prediction()`；保留旧 Mem0 函数作为兼容转发。
- Modify: `src/memory_benchmark/cli/commands.py`
  - `execute_predict()` 调用统一 registered prediction service。
- Modify: `src/memory_benchmark/cli/main.py`
  - prediction benchmark choices 只展示已开放 benchmark。
- Modify: `src/memory_benchmark/runners/ingest_resume.py`
  - 移入通用 completed conversation checkpoint 读取函数。

### MemoryOS

- Create: `configs/methods/memoryos.toml`
  - 保存 `smoke` 和 `official_full` 的完整可审计配置。
- Modify: `src/memory_benchmark/methods/memoryos_adapter.py`
  - 强化配置校验、manifest/source identity，并显式接入 top-m。
- Modify: `src/memory_benchmark/methods/__init__.py`
  - 导出 MemoryOS source identity。

### Tests 与文档

- Modify: `tests/test_config_profiles.py`
- Modify: `tests/test_method_registry.py`
- Modify: `tests/test_prediction_cli.py`
- Modify: `tests/test_main_cli.py`
- Modify: `tests/test_memoryos_adapter.py`
- Create: `tests/test_memoryos_registered_prediction.py`
- Keep: `tests/test_memoryos_locomo_full_runner.py`
  - 作为 legacy runner 回归，不迁入新路径。
- Modify: `README.md`
- Modify: `AGENTS.md`
- Create/Update: `docs/handoffs/2026-06-12-memoryos-unified-runner.md`

## Task 1: Task family 与 capability 注册契约

**Files:**
- Create: `src/memory_benchmark/core/capabilities.py`
- Modify: `src/memory_benchmark/core/__init__.py`
- Modify: `src/memory_benchmark/benchmark_adapters/registry.py`
- Modify: `src/memory_benchmark/benchmark_adapters/__init__.py`
- Test: `tests/test_benchmark_registry.py`
- Test: `tests/test_method_registry.py`

- [x] **Step 1: 写 capability RED tests**

在 `tests/test_benchmark_registry.py` 增加：

```python
def test_prediction_registry_exposes_only_current_phase_benchmark() -> None:
    assert list_benchmarks() == ["locomo", "longmemeval"]
    assert list_prediction_benchmarks() == ["locomo"]


def test_locomo_registration_declares_conversation_qa_capabilities() -> None:
    registration = get_benchmark_registration("locomo")
    assert registration.task_family is TaskFamily.CONVERSATION_QA
    assert registration.required_capabilities == frozenset(
        {
            MethodCapability.CONVERSATION_ADD,
            MethodCapability.ANSWER_GENERATION,
        }
    )
    assert registration.prediction_enabled is True


def test_longmemeval_remains_registered_but_not_prediction_enabled() -> None:
    registration = get_benchmark_registration("longmemeval")
    assert registration.task_family is TaskFamily.CONVERSATION_QA
    assert registration.prediction_enabled is False
```

在 `tests/test_method_registry.py` 增加 capability subset 校验测试：

```python
def test_compatibility_requires_task_family_and_capabilities() -> None:
    validate_compatibility(
        benchmark_task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        method_task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
    )
```

- [x] **Step 2: 运行 RED tests**

```bash
uv run pytest tests/test_benchmark_registry.py tests/test_method_registry.py -q
```

预期：因 `TaskFamily`、`MethodCapability`、`BenchmarkRegistration` 和
`list_prediction_benchmarks()` 尚不存在而失败。

- [x] **Step 3: 实现稳定枚举和兼容校验**

创建 `core/capabilities.py`：

```python
"""task family 与 method capability 的稳定声明。"""

from enum import StrEnum

from .exceptions import ConfigurationError


class TaskFamily(StrEnum):
    """框架当前认识的 benchmark 任务族。"""

    CONVERSATION_QA = "conversation_qa"


class MethodCapability(StrEnum):
    """method 可以向 benchmark 提供的稳定能力。"""

    CONVERSATION_ADD = "conversation_add"
    ANSWER_GENERATION = "answer_generation"
    MEMORY_RETRIEVAL = "memory_retrieval"


def validate_compatibility(
    *,
    benchmark_task_family: TaskFamily,
    required_capabilities: frozenset[MethodCapability],
    method_task_families: frozenset[TaskFamily],
    provided_capabilities: frozenset[MethodCapability],
) -> None:
    """校验 task family 和 capability 子集关系。"""

    if benchmark_task_family not in method_task_families:
        raise ConfigurationError(
            f"Method does not support task family: {benchmark_task_family.value}"
        )
    missing = required_capabilities - provided_capabilities
    if missing:
        names = ", ".join(sorted(capability.value for capability in missing))
        raise ConfigurationError(f"Method is missing required capabilities: {names}")
```

- [x] **Step 4: 扩展 benchmark registry**

`BenchmarkRegistration` 至少包含：

```python
@dataclass(frozen=True)
class BenchmarkRegistration:
    name: str
    adapter_cls: type[BenchmarkAdapter]
    task_family: TaskFamily
    required_capabilities: frozenset[MethodCapability]
    source_relative_paths: tuple[Path, ...]
    prediction_enabled: bool
```

默认注册：

```python
locomo = BenchmarkRegistration(
    name="locomo",
    adapter_cls=LoCoMoAdapter,
    task_family=TaskFamily.CONVERSATION_QA,
    required_capabilities=frozenset(
        {
            MethodCapability.CONVERSATION_ADD,
            MethodCapability.ANSWER_GENERATION,
        }
    ),
    source_relative_paths=(Path(LOCOMO_SOURCE_PATH),),
    prediction_enabled=True,
)
```

LongMemEval 保持 adapter 可用，但 `prediction_enabled=False`。

- [x] **Step 5: 运行 focused tests**

```bash
uv run pytest tests/test_benchmark_registry.py tests/test_method_registry.py -q
```

预期：PASS。

## Task 2: LoCoMo smoke scope 归属 benchmark

**Files:**
- Modify: `src/memory_benchmark/benchmark_adapters/locomo.py`
- Modify: `src/memory_benchmark/cli/run_prediction.py`
- Modify: `tests/test_prediction_cli.py`

- [x] **Step 1: 写 RED import/behavior test**

把 `tests/test_prediction_cli.py` 的导入改为：

```python
from memory_benchmark.benchmark_adapters.locomo import build_locomo_smoke_dataset
```

保留现有测试，继续要求：

- 只保留指定 turn 数。
- 选择 evidence 完整落在历史范围内的一道问题。
- 不向 public payload 泄漏 evidence。
- 支持 1 或 2 个 conversation。

- [x] **Step 2: 运行 RED test**

```bash
uv run pytest tests/test_prediction_cli.py -q
```

预期：因 helper 尚未位于 LoCoMo adapter 模块而失败。

- [x] **Step 3: 移动 smoke helper**

把当前 `cli/run_prediction.py` 中
`build_locomo_smoke_dataset()` 与 `_build_locomo_smoke_conversation()` 的完整函数体及
`copy` import 原样移入 `benchmark_adapters/locomo.py`。函数签名保持不变，默认值继续为
`turn_limit=20`、`conversation_limit=1`，不能在移动过程中改变 evidence 范围选择算法。

`cli/run_prediction.py` 只导入并调用，不再拥有 benchmark-specific evidence 选择逻辑。

- [x] **Step 4: 运行 focused tests**

```bash
uv run pytest tests/test_prediction_cli.py tests/test_locomo_conversation_adapter.py -q
```

预期：PASS。

## Task 3: Method registration 变为 factory + capabilities

**Files:**
- Modify: `src/memory_benchmark/methods/registry.py`
- Modify: `src/memory_benchmark/runners/ingest_resume.py`
- Modify: `src/memory_benchmark/cli/run_prediction.py`
- Modify: `src/memory_benchmark/cli/commands.py`
- Modify: `tests/test_method_registry.py`
- Modify: `tests/test_prediction_cli.py`
- Modify: `tests/test_main_cli.py`

- [x] **Step 1: 写新的 registration RED tests**

要求 Mem0 registration 声明：

```python
assert registration.task_families == frozenset({TaskFamily.CONVERSATION_QA})
assert registration.provided_capabilities == frozenset(
    {
        MethodCapability.CONVERSATION_ADD,
        MethodCapability.ANSWER_GENERATION,
        MethodCapability.MEMORY_RETRIEVAL,
    }
)
assert registration.system_factory is not None
assert registration.source_identity_factory is not None
assert registration.model_name_getter is not None
assert registration.max_workers_getter is not None
```

并删除对 `supported_benchmarks` 和 method-specific `predictor` 的依赖。

- [x] **Step 2: 运行 RED tests**

```bash
uv run pytest tests/test_method_registry.py tests/test_main_cli.py -q
```

预期：registration 字段不匹配而失败。

- [x] **Step 3: 定义 method build context**

在 `methods/registry.py` 增加：

```python
@dataclass(frozen=True)
class MethodBuildContext:
    config: Any
    openai_settings: OpenAISettings
    path_settings: PathSettings
    storage_root: Path
    completed_conversations: tuple[Conversation, ...] = ()
```

`MethodRegistration` 改为：

```python
@dataclass(frozen=True)
class MethodRegistration:
    name: str
    task_families: frozenset[TaskFamily]
    provided_capabilities: frozenset[MethodCapability]
    profile_sections: tuple[tuple[str, str], ...]
    profile_relative_path: Path
    config_type: type[Any]
    requires_api: bool
    system_factory: Callable[[MethodBuildContext], BaseMemorySystem]
    source_identity_factory: Callable[[PathSettings], dict[str, Any]]
    model_name_getter: Callable[[Any], str]
    max_workers_getter: Callable[[Any], int]
```

Mem0 factory 必须继续传入：

```python
Mem0(
    config=context.config,
    openai_settings=context.openai_settings,
    storage_root=context.storage_root,
    path_settings=context.path_settings,
    existing_conversation_ids={
        conversation.conversation_id
        for conversation in context.completed_conversations
    },
)
```

- [x] **Step 4: 把 completed conversation 读取移入 runner resume 工具**

把当前 `cli/run_prediction.py` 中 `load_completed_conversation_ids()` 的完整实现移入
`runners/ingest_resume.py`。签名、coarse checkpoint 解析、逐 turn completed checkpoint
补充逻辑和异常行为全部保持不变；`cli/run_prediction.py` 删除本地实现并导入该函数。

- [x] **Step 5: 实现统一 registered prediction service**

在 `cli/run_prediction.py` 增加
`run_registered_conversation_qa_prediction()`。函数参数必须完整包含
`project_root`、`method_name`、`benchmark_name`、`profile_name`、`run_id`、`resume`、
`confirm_api`、`confirm_full`、`smoke_turn_limit`、`smoke_conversation_limit` 和
`smoke_max_workers`，返回 `PredictionRunSummary`。

执行顺序固定为：

1. 读取 benchmark/method registration。
2. 拒绝 `prediction_enabled=False`。
3. `validate_compatibility()`。
4. 在读取 `.env` 和构造 method 前完成 profile/cost confirmation。
5. 加载 profile 和 dataset。
6. smoke 时调用 benchmark-owned LoCoMo smoke helper。
7. 创建 `RunContext`。
8. 读取 completed conversation ids，并传给 method factory。
9. 构造 method manifest：

```python
{
    "config": config.to_manifest(),
    "source": registration.source_identity_factory(path_settings),
}
```

10. 调用 `run_predictions()`。

旧函数只保留兼容转发：

```python
def run_mem0_locomo_prediction(
    project_root: str | Path,
    profile_name: str = "smoke",
    run_id: str | None = None,
    resume: bool = False,
    confirm_api: bool = False,
    confirm_full: bool = False,
    smoke_turn_limit: int = DEFAULT_SMOKE_TURN_LIMIT,
    smoke_conversation_limit: int = 1,
    smoke_max_workers: int | None = None,
) -> PredictionRunSummary:
    return run_registered_conversation_qa_prediction(
        project_root=project_root,
        method_name="mem0",
        benchmark_name="locomo",
        profile_name=profile_name,
        run_id=run_id,
        resume=resume,
        confirm_api=confirm_api,
        confirm_full=confirm_full,
        smoke_turn_limit=smoke_turn_limit,
        smoke_conversation_limit=smoke_conversation_limit,
        smoke_max_workers=smoke_max_workers,
    )
```

- [x] **Step 6: command service 改用统一装配**

`execute_predict()` 直接调用
`run_registered_conversation_qa_prediction()`，不再让 method registry 保存 predictor
callback。

- [x] **Step 7: 运行 focused tests**

```bash
uv run pytest \
  tests/test_method_registry.py \
  tests/test_prediction_cli.py \
  tests/test_main_cli.py \
  tests/test_prediction_runner.py \
  -q
```

预期：PASS，且不调用真实 API。

## Task 4: MemoryOS TOML、配置校验与 source identity

**Files:**
- Create: `configs/methods/memoryos.toml`
- Modify: `src/memory_benchmark/methods/memoryos_adapter.py`
- Modify: `src/memory_benchmark/methods/__init__.py`
- Modify: `tests/test_config_profiles.py`
- Modify: `tests/test_memoryos_adapter.py`

- [x] **Step 1: 写 MemoryOS profile/source RED tests**

新增测试：

```python
def test_memoryos_profile_loads_from_toml(tmp_path: Path) -> None:
    config = load_typed_profile(
        tmp_path / "configs/methods/memoryos.toml",
        "official_full",
        MemoryOSPaperConfig,
    )
    assert config.profile_name == "official_full"
    assert config.short_term_capacity == 7
    assert config.retrieval_top_m_segments == 5
    assert config.retrieval_queue_capacity == 10
    assert config.max_workers == 1


def test_memoryos_source_identity_is_deterministic() -> None:
    first = build_memoryos_source_identity(load_path_settings())
    second = build_memoryos_source_identity(load_path_settings())
    assert first == second
    assert len(first["source_sha256"]) == 64
    assert all(
        path.startswith(("eval/", "README.md", "LICENSE"))
        for path in first["files"]
    )
```

增加无效容量、threshold、top-m、queue capacity、retry 配置的参数化测试。

- [x] **Step 2: 运行 RED tests**

```bash
uv run pytest tests/test_config_profiles.py tests/test_memoryos_adapter.py -q
```

预期：缺少 TOML、字段和 source identity 而失败。

- [x] **Step 3: 创建完整 TOML**

`configs/methods/memoryos.toml` 的 `smoke` 与 `official_full` 都显式列出：

```toml
[smoke]
llm_model = "gpt-4o-mini"
embedding_model_name = "sentence-transformers/all-MiniLM-L6-v2"
short_term_capacity = 7
mid_term_capacity = 200
long_term_knowledge_capacity = 100
heat_threshold = 5.0
topic_similarity_threshold = 0.6
retrieval_top_m_segments = 5
retrieval_queue_capacity = 10
segment_threshold = 0.1
page_threshold = 0.1
knowledge_threshold = 0.1
api_timeout_seconds = 120.0
api_max_retries = 8
api_retry_wait_seconds = 5.0
api_retry_backoff_multiplier = 2.0
api_retry_max_wait_seconds = 60.0
suppress_official_stdout = true
max_workers = 1

[official_full]
llm_model = "gpt-4o-mini"
embedding_model_name = "sentence-transformers/all-MiniLM-L6-v2"
short_term_capacity = 7
mid_term_capacity = 200
long_term_knowledge_capacity = 100
heat_threshold = 5.0
topic_similarity_threshold = 0.6
retrieval_top_m_segments = 5
retrieval_queue_capacity = 10
segment_threshold = 0.1
page_threshold = 0.1
knowledge_threshold = 0.1
api_timeout_seconds = 120.0
api_max_retries = 8
api_retry_wait_seconds = 5.0
api_retry_backoff_multiplier = 2.0
api_retry_max_wait_seconds = 60.0
suppress_official_stdout = true
max_workers = 1
```

smoke 只缩小数据范围，不修改 MemoryOS 算法参数。

- [x] **Step 4: 强化 MemoryOS config**

`MemoryOSPaperConfig` 增加：

```python
max_workers: int = 1
profile_name: str = "custom"

def to_manifest(self) -> dict[str, Any]:
    return {
        **asdict(self),
        "adapter_version": "conversation-qa-v1",
        "source_mode": "official-eval-wrapper",
    }
```

`__post_init__()` 必须校验：

- model 名非空。
- capacity/top-m/top-k/max_workers 为正整数。
- similarity/过滤 threshold 在 `[0, 1]`。
- heat threshold 非负。
- retry/timeout 约束保持现有行为。

- [x] **Step 5: 实现 deterministic source identity**

`build_memoryos_source_identity()` 分别计算并组合：

- vendored 官方 `eval/*.py`、`README.md`、`LICENSE` 的确定性 hash；
- 本项目实际执行的 `src/memory_benchmark/methods/memoryos_adapter.py` wrapper hash。

排除 `.git`、PDF、图片、cache、实验数据和其它发行形态。输出使用稳定相对标识，
不暴露机器绝对路径。结果包含组合 `source_sha256`、vendored
`vendored_source_sha256`、`file_count`、`files`、`wrapper_path` 和
`wrapper_sha256`。wrapper 变化必须让旧 run 的 resume fail-closed。

- [x] **Step 6: 显式接入 retrieval top-m**

在 `_create_state()` 构造 `mid_memory` 后，用本项目侧 wrapper 把
`self.config.retrieval_top_m_segments` 传给官方
`search_sessions_by_summary` 的 `top_k` 参数。不得修改第三方文件，也不得重写官方检索
算法。

新增测试：把 `retrieval_top_m_segments` 设为 3，调用 wrapped search，确认底层原方法收到
`top_k=3`。

- [x] **Step 7: 运行 focused tests**

```bash
uv run pytest tests/test_config_profiles.py tests/test_memoryos_adapter.py -q
```

预期：PASS。

## Task 5: 注册 MemoryOS 并通过 generic runner 生成 prediction

**Files:**
- Modify: `src/memory_benchmark/methods/registry.py`
- Modify: `src/memory_benchmark/cli/run_prediction.py`
- Modify: `src/memory_benchmark/cli/main.py`
- Modify: `tests/test_method_registry.py`
- Create: `tests/test_memoryos_registered_prediction.py`
- Modify: `tests/test_main_cli.py`

- [x] **Step 1: 写 MemoryOS registration RED tests**

```python
def test_registry_lists_mem0_and_memoryos() -> None:
    assert list_methods() == ["mem0", "memoryos"]


def test_memoryos_registration_uses_generic_contract() -> None:
    registration = get_method_registration("memoryos")
    assert registration.profile_names == frozenset({"smoke", "official-full"})
    assert registration.task_families == frozenset({TaskFamily.CONVERSATION_QA})
    assert MethodCapability.ANSWER_GENERATION in registration.provided_capabilities
    assert registration.profile_relative_path == Path(
        "configs/methods/memoryos.toml"
    )
```

- [x] **Step 2: 写 cost/resume RED tests**

`tests/test_memoryos_registered_prediction.py` 使用 fake adapter、fake MemoryOS class 和临时
run 目录验证：

1. 未传 `confirm_api` 时，在 system factory 前失败。
2. `official-full` 未传 `confirm_full` 时，在 system factory 前失败。
3. smoke 只选择有限历史和一道 evidence 覆盖问题。
4. `max_workers` 固定来自 MemoryOS config，不能用 `smoke_max_workers=2` 绕过。
5. resume 的 completed conversation 会调用
   `MemoryOS.load_existing_conversation_state()`，不会再次 `add()`。
6. 新 run 调用的是 `run_predictions()`，不调用 `run_memoryos_locomo_full()`。

- [x] **Step 3: 运行 RED tests**

```bash
uv run pytest \
  tests/test_method_registry.py \
  tests/test_memoryos_registered_prediction.py \
  tests/test_main_cli.py \
  -q
```

预期：MemoryOS registration 尚不存在而失败。

- [x] **Step 4: 实现 MemoryOS factory 与恢复 hook**

factory 逻辑：

```python
def _build_memoryos_system(context: MethodBuildContext) -> BaseMemorySystem:
    system = MemoryOS(
        openai_api_key=context.openai_settings.api_key,
        openai_base_url=context.openai_settings.base_url,
        storage_root=context.storage_root,
        config=context.config,
    )
    for conversation in context.completed_conversations:
        system.load_existing_conversation_state(conversation)
    return system
```

这不是新的公共 method 接口；它是 registry 内部装配 hook。

- [x] **Step 5: 实现 MemoryOS 成本 guard**

在构造 MemoryOS 前：

```python
total_update_batches = sum(
    MemoryOS.estimate_add_workload(conversation, config).update_batch_count
    for conversation in dataset.conversations
)
```

规则：

- 所有真实 MemoryOS prediction 都要求 `confirm_api`。
- `official-full` 额外要求 `confirm_full`。
- 日志/错误可以报告 update batch 数，不能打印 secret。
- smoke 仍使用论文参数，只通过裁剪 dataset 降低成本。

- [x] **Step 6: 注册 MemoryOS**

registration 使用：

```python
task_families=frozenset({TaskFamily.CONVERSATION_QA})
provided_capabilities=frozenset(
    {
        MethodCapability.CONVERSATION_ADD,
        MethodCapability.ANSWER_GENERATION,
        MethodCapability.MEMORY_RETRIEVAL,
    }
)
profile_sections=(
    ("smoke", "smoke"),
    ("official-full", "official_full"),
)
```

`max_workers_getter` 返回 `config.max_workers`；当前两个 profile 都为 1。

- [x] **Step 7: 运行 focused tests**

```bash
uv run pytest \
  tests/test_method_registry.py \
  tests/test_memoryos_registered_prediction.py \
  tests/test_main_cli.py \
  tests/test_prediction_runner.py \
  -q
```

预期：PASS，不访问外部 API。

实际结果（2026-06-13）：

```bash
uv run pytest \
  tests/test_prediction_cli.py \
  tests/test_method_registry.py \
  tests/test_memoryos_registered_prediction.py \
  tests/test_main_cli.py \
  tests/test_prediction_runner.py \
  -q
```

结果：`53 passed`，未访问外部 API。Task 5 独立综合 review 与完整回归仍待执行。

## Task 6: Legacy 边界与 artifact-only evaluation 回归

**Files:**
- Modify: `src/memory_benchmark/runners/memoryos_locomo_full.py`
- Modify: `src/memory_benchmark/runners/memoryos_locomo_smoke.py`
- Modify: `tests/test_memoryos_locomo_full_runner.py`
- Modify: `tests/test_artifact_evaluation_runner.py`
- Modify: `README.md`

- [x] **Step 1: 写新旧边界 tests**

在 `tests/test_memoryos_registered_prediction.py` 增加
`test_new_memoryos_run_writes_only_canonical_prediction_artifacts`，使用 fake MemoryOS
运行一个 conversation/一个 question，断言 canonical prediction/private-label 文件存在，
且根目录三个 legacy alias 不存在。

在 `tests/test_artifact_evaluation_runner.py` 增加
`test_new_memoryos_prediction_can_be_scored_by_existing_locomo_f1`，读取上述标准 record
形状构造临时 run，断言 `run_artifact_evaluation()` 输出 `locomo_f1` score artifact。

在 `tests/test_memoryos_locomo_full_runner.py` 增加
`test_legacy_memoryos_runner_remains_callable_but_is_not_registered`，断言旧函数仍可导入，
但 method registration 的 system factory 不引用该函数。

新路径不得创建根目录 `predictions.jsonl`、`scores.jsonl` 或
`conversation_status.json` alias。

- [x] **Step 2: 标记旧入口为 legacy**

旧模块顶部和公开函数 docstring 明确：

- 只用于解释/复查历史 MemoryOS run。
- 新实验必须使用统一 `predict/evaluate/run`。
- 不允许把新 generic run 与旧 alias resume 混用。

本任务不删除旧代码和旧测试。

- [x] **Step 3: 更新 README 命令**

增加：

```bash
uv run memory-benchmark predict \
  --method memoryos \
  --benchmark locomo \
  --profile smoke \
  --run-id memoryos-locomo-smoke-YYYYMMDD \
  --confirm-api

uv run memory-benchmark evaluate \
  --run-id memoryos-locomo-smoke-YYYYMMDD \
  --metric locomo-f1
```

明确：

- `official-full` 还需要 `--confirm-full`。
- MemoryOS 当前为串行 conversation 执行。
- 旧 2026-06-03 run 不会自动迁入新 resume。

- [x] **Step 4: 运行 legacy + new focused tests**

```bash
uv run pytest \
  tests/test_memoryos_registered_prediction.py \
  tests/test_artifact_evaluation_runner.py \
  tests/test_memoryos_locomo_full_runner.py \
  -q
```

预期：PASS。

实际结果（2026-06-13）：`55 passed`。综合 reviewer 最终 `APPROVED`，未访问外部 API。

## Task 7: 文档、handoff 与阶段验收

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Create/Update: `docs/handoffs/2026-06-12-memoryos-unified-runner.md`

- [x] **Step 1: 更新状态文档**

记录：

- MemoryOS 已加入 method registry。
- Mem0 和 MemoryOS 都通过同一个 registered prediction service 和 generic runner。
- LoCoMo 仍是唯一 prediction-enabled benchmark。
- LongMemEval adapter 可读，但统一 prediction 尚未开放。
- MemoryOS 新 run 使用 canonical artifacts；旧正式 run 保持原样。
- MemoryOS 暂不并发，原因是共享 wrapper/thread-safety 尚未单独验证。

- [x] **Step 2: 运行 focused suite**

```bash
uv run pytest \
  tests/test_benchmark_registry.py \
  tests/test_config_profiles.py \
  tests/test_method_registry.py \
  tests/test_prediction_cli.py \
  tests/test_main_cli.py \
  tests/test_prediction_runner.py \
  tests/test_memoryos_adapter.py \
  tests/test_memoryos_registered_prediction.py \
  tests/test_artifact_evaluation_runner.py \
  tests/test_memoryos_locomo_smoke.py \
  tests/test_memoryos_locomo_full_runner.py \
  -q
```

预期：全部 PASS。

实际结果（2026-06-13）：`253 passed, 2 subtests passed`。

- [x] **Step 3: 运行完整离线回归**

```bash
uv run pytest -q
uv run pytest -m memoryos -q
uv run pytest -m api --collect-only -q
uv run python -m compileall -q src/memory_benchmark tests
```

要求：

- 默认 suite 不调用外部 API。
- MemoryOS marker 全部通过。
- API 测试只 collect，不实际执行。
- compileall exit 0。

实际结果（2026-06-13）：

- full pytest：`386 passed, 3 deselected, 6 subtests passed`
- MemoryOS marker：`168 passed, 221 deselected, 2 subtests passed`
- API collect-only：3 项
- documentation standards：`5 passed`
- compileall：exit 0

- [x] **Step 4: 综合 review**

重点检查：

- private labels 没有进入 method。
- `official-full` 参数来自 TOML，且 manifest 完整记录。
- MemoryOS 仍调用第三方 `eval/` 算法。
- resume 只 attach completed conversation，不重复 add。
- generic runner 不出现 `if method_name == "memoryos"`。
- `outputs/memoryos-locomo-full-20260603/` 未变化。

最终 reviewer（`gpt-5.5 high`）结论：`APPROVED`。wrapper source identity
缺失问题已通过 TDD 修复；受保护实验目录聚合哈希保持
`2bf09d4109396feb7af4eb174d21bff791afc1c03b5a8ba62180da1315df642f`。

- [x] **Step 5: 更新最终 handoff**

handoff 必须记录：

- 实际修改文件。
- focused/full 验证数量。
- subagent 模型、推理强度、调查或实现范围。
- 尚未运行的真实 API 项目。
- 下一步是 Mem0 official-full 或 LongMemEval 迁移，而不是继续复制 runner。
