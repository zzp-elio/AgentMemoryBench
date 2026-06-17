# Cost and Efficiency Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 conversation + QA prediction/evaluation 增加可审计的 token、latency、模型身份和离线费用分析，同时保持现有 method 公共接口、并发语义、resume 语义和 prediction artifact 不变。

**Architecture:** 新增独立的 efficiency observation 领域模型、线程安全作用域 collector 和标准 artifact 存储。通用 runner 负责 conversation/question 生命周期，method adapter 只在能够精确识别的内部边界上报 retrieval、Answer LLM 和 embedding 观测；Judge 在 evaluator artifact 中独立记录。价格计算只读取已完成 observation 和用户价格配置，不调用 method、LLM 或 benchmark adapter。

**Tech Stack:** Python 3.12、dataclasses、contextvars、perf_counter_ns、pytest、JSON/JSONL、TOML、现有 `RunContext`/`ExperimentPaths`/原子写入工具。

---

## 文件结构

新增：

```text
src/memory_benchmark/observability/efficiency/
  __init__.py
  entities.py
  collector.py
  token_counting.py
  storage.py

src/memory_benchmark/analysis/
  __init__.py
  efficiency.py
  cost.py

tests/
  test_efficiency_entities.py
  test_efficiency_collector.py
  test_efficiency_storage.py
  test_efficiency_token_counting.py
  test_prediction_efficiency_observations.py
  test_method_efficiency_observations.py
  test_judge_efficiency_observations.py
  test_efficiency_analysis.py
  test_cost_analysis.py
```

修改：

```text
src/memory_benchmark/observability/__init__.py
src/memory_benchmark/storage/experiment_paths.py
src/memory_benchmark/methods/registry.py
src/memory_benchmark/methods/mem0_adapter.py
src/memory_benchmark/methods/memoryos_adapter.py
src/memory_benchmark/runners/prediction.py
src/memory_benchmark/runners/evaluation.py
src/memory_benchmark/evaluators/llm_judge.py
docs/current-roadmap.md
AGENTS.md
```

当前目录不是 git repo，因此本计划不包含 commit；每个 Task 完成后立即更新本计划勾选状态和 handoff。

### Task 1：建立强类型 observation 与模型清单

**Files:**
- Create: `src/memory_benchmark/observability/efficiency/entities.py`
- Create: `src/memory_benchmark/observability/efficiency/__init__.py`
- Modify: `src/memory_benchmark/observability/__init__.py`
- Test: `tests/test_efficiency_entities.py`

- [x] **Step 1: 写 observation 校验的失败测试**

测试必须覆盖：

```python
def test_question_efficiency_requires_reason_for_unsupported_retrieval():
    with pytest.raises(ConfigurationError, match="unsupported_reason"):
        QuestionEfficiencyObservation(
            observation_id="obs-1",
            conversation_id="conv-1",
            question_id="q-1",
            retrieval_latency_ms=None,
            unsupported_reason=None,
            injected_memory_context_tokens=12,
            answer_generation_latency_ms=4.5,
        )


def test_llm_call_rejects_negative_tokens():
    with pytest.raises(ConfigurationError, match="input_tokens"):
        LLMCallObservation(
            observation_id="obs-2",
            stage=EfficiencyStage.ANSWER,
            model_id="answer-llm",
            input_tokens=-1,
            output_tokens=3,
            token_measurement_source=MeasurementSource.API_USAGE,
            conversation_id="conv-1",
            question_id="q-1",
        )
```

- [x] **Step 2: 运行测试并确认 RED**

Run:

```bash
uv run pytest tests/test_efficiency_entities.py -q
```

Expected: collection/import failure because the efficiency entities do not exist.

- [x] **Step 3: 实现枚举与 dataclass**

至少提供：

```python
class EfficiencyStage(str, Enum):
    MEMORY_BUILD = "memory_build"
    RETRIEVAL = "retrieval"
    ANSWER = "answer"
    JUDGE = "judge"


class MeasurementSource(str, Enum):
    API_USAGE = "api_usage"
    METHOD_NATIVE = "method_native"
    FRAMEWORK_TIMER = "framework_timer"
    TOKENIZER_ESTIMATE = "tokenizer_estimate"


@dataclass(frozen=True)
class ModelDescriptor:
    model_id: str
    model_name: str
    model_role: str
    execution_mode: str
    revision_or_path: str | None = None
    embedding_dimension: int | None = None
    tokenizer_name: str | None = None


@dataclass(frozen=True)
class ConversationEfficiencyObservation:
    observation_id: str
    conversation_id: str
    memory_build_total_latency_ms: float


@dataclass(frozen=True)
class QuestionEfficiencyObservation:
    observation_id: str
    conversation_id: str
    question_id: str
    retrieval_latency_ms: float | None
    unsupported_reason: str | None
    injected_memory_context_tokens: int | None
    answer_generation_latency_ms: float | None


@dataclass(frozen=True)
class LLMCallObservation:
    observation_id: str
    stage: EfficiencyStage
    model_id: str
    input_tokens: int
    output_tokens: int
    token_measurement_source: MeasurementSource
    conversation_id: str | None = None
    question_id: str | None = None


@dataclass(frozen=True)
class EmbeddingCallObservation:
    observation_id: str
    stage: EfficiencyStage
    model_id: str
    input_tokens: int
    latency_ms: float
    token_measurement_source: MeasurementSource
    latency_measurement_source: MeasurementSource
    conversation_id: str | None = None
    question_id: str | None = None
```

所有实体实现 `to_dict()`；验证空 id、非法 stage、负 token、NaN/inf/负 latency，以及
retrieval `null` 时必须存在非空 `unsupported_reason`。

- [x] **Step 4: 运行测试并确认 GREEN**

Run:

```bash
uv run pytest tests/test_efficiency_entities.py -q
```

Expected: all tests pass.

### Task 2：实现作用域 collector 与 token 计量

**Files:**
- Create: `src/memory_benchmark/observability/efficiency/collector.py`
- Create: `src/memory_benchmark/observability/efficiency/token_counting.py`
- Test: `tests/test_efficiency_collector.py`
- Test: `tests/test_efficiency_token_counting.py`

- [x] **Step 1: 写并发隔离、确定性 id 和来源优先级失败测试**

关键测试：

```python
def test_question_scopes_do_not_mix_records_between_threads():
    collector = EfficiencyCollector(enabled=True)
    # 两个线程分别进入 conv-a/q-a 与 conv-b/q-b，并记录 LLM call。
    # 每个 scope 返回的 records 只能包含自己的 conversation/question。


def test_usage_tokens_override_tokenizer_estimate():
    result = resolve_token_usage(
        api_input_tokens=11,
        api_output_tokens=2,
        prompt_text="ignored",
        output_text="ignored",
        tokenizer=FakeTokenizer(return_value=999),
    )
    assert result.input_tokens == 11
    assert result.output_tokens == 2
    assert result.source is MeasurementSource.API_USAGE
```

- [x] **Step 2: 运行测试并确认 RED**

Run:

```bash
uv run pytest tests/test_efficiency_collector.py tests/test_efficiency_token_counting.py -q
```

Expected: missing collector/token counting symbols.

- [x] **Step 3: 实现 collector**

公共形态：

```python
class EfficiencyCollector:
    def __init__(self, *, enabled: bool) -> None: ...

    @contextmanager
    def conversation_scope(
        self, conversation_id: str
    ) -> Iterator[ObservationScope]: ...

    @contextmanager
    def question_scope(
        self, conversation_id: str, question_id: str
    ) -> Iterator[ObservationScope]: ...

    def record_llm_call(self, ...) -> None: ...
    def record_embedding_call(self, ...) -> None: ...
    def record_retrieval_result(self, ...) -> None: ...
    def record_answer_generation(self, ...) -> None: ...
```

使用 `ContextVar` 保存当前 scope，确保共享 method 实例的多线程 conversation 不串写。
`ObservationScope.records` 在退出后冻结为 tuple。observation id 由
`run_id/stage/conversation_id/question_id/call_index/type` 组成的 canonical payload
做 SHA-256，禁止使用随机 UUID。

- [x] **Step 4: 实现 token 计量**

提供：

```python
@dataclass(frozen=True)
class ResolvedTokenUsage:
    input_tokens: int
    output_tokens: int
    source: MeasurementSource


def resolve_token_usage(
    *,
    api_input_tokens: int | None,
    api_output_tokens: int | None,
    prompt_text: str,
    output_text: str,
    tokenizer: TokenCounter | None,
) -> ResolvedTokenUsage:
    ...
```

API usage 完整时优先；否则必须存在匹配 tokenizer。不得把字符数、单词数冒充 token。

- [x] **Step 5: 运行测试并确认 GREEN**

Run:

```bash
uv run pytest tests/test_efficiency_collector.py tests/test_efficiency_token_counting.py -q
```

Expected: all tests pass.

### Task 3：标准 artifact、模型清单与 resume 身份

**Files:**
- Create: `src/memory_benchmark/observability/efficiency/storage.py`
- Modify: `src/memory_benchmark/storage/experiment_paths.py`
- Modify: `src/memory_benchmark/runners/prediction.py`
- Test: `tests/test_efficiency_storage.py`
- Test: `tests/test_prediction_efficiency_observations.py`

- [x] **Step 1: 写路径安全、原子写入和 manifest mismatch 失败测试**

测试必须断言：

```python
assert paths.prediction_model_inventory_path.name == "model_inventory.prediction.json"
assert (
    paths.prediction_efficiency_observations_path.name
    == "efficiency_observations.prediction.jsonl"
)
assert paths.evaluator_efficiency_observations_path("locomo_judge_accuracy").name == (
    "efficiency_observations.locomo_judge_accuracy.jsonl"
)
```

同时验证非法 metric 名不能路径逃逸；resume 时模型清单或 instrumentation identity 改变，
必须在 method factory 和目录副作用前报错。

- [x] **Step 2: 运行测试并确认 RED**

Run:

```bash
uv run pytest tests/test_efficiency_storage.py tests/test_prediction_efficiency_observations.py -q
```

Expected: new artifact paths and manifest fields are missing.

- [x] **Step 3: 实现路径与 storage**

`EfficiencyArtifactStore` 提供：

```python
class EfficiencyArtifactStore:
    def write_model_inventory(
        self, descriptors: Sequence[ModelDescriptor]
    ) -> None: ...

    def merge_observations(
        self, observations: Sequence[EfficiencyObservation]
    ) -> None: ...

    def read_observations(self) -> list[EfficiencyObservation]: ...
```

`merge_observations()` 按 `observation_id` 去重并稳定排序，使用现有
`atomic_write_jsonl()`；同 id 内容不同必须抛 `ConfigurationError`，不能覆盖。

- [x] **Step 4: 把 observation identity 加入 prediction manifest**

`run_predictions()` 新增可选依赖：

```python
efficiency_collector: EfficiencyCollector | None = None
model_inventory: tuple[ModelDescriptor, ...] = ()
instrumentation_identity: dict[str, object] | None = None
```

manifest 增加：

```python
"efficiency_observability": {
    "enabled": efficiency_collector is not None,
    "model_inventory": [descriptor.to_dict() for descriptor in model_inventory],
    "instrumentation_identity": instrumentation_identity,
}
```

关闭观测时保持现有行为和 artifact 集合，不写空 observation 文件。

- [x] **Step 5: 运行 focused tests**

Run:

```bash
uv run pytest tests/test_efficiency_storage.py tests/test_prediction_efficiency_observations.py tests/test_prediction_runner.py -q
```

Expected: all tests pass.

### Task 4：通用 runner 接入 conversation/question 生命周期

**Files:**
- Modify: `src/memory_benchmark/runners/prediction.py`
- Test: `tests/test_prediction_efficiency_observations.py`

- [x] **Step 1: 写 fake method 边界失败测试**

构造 fake method：

```python
class ObservedFakeMethod(BaseMemorySystem):
    def __init__(self, collector: EfficiencyCollector) -> None:
        self.collector = collector

    def add(self, conversations):
        time.sleep(0.001)
        return AddResult(conversation_ids=[conversations[0].conversation_id])

    def get_answer(self, question):
        self.collector.record_retrieval_result(
            latency_ms=1.5,
            injected_memory_context_tokens=7,
        )
        self.collector.record_answer_generation(latency_ms=2.5)
        return AnswerResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer="answer",
        )
```

断言每个 conversation 一条 build observation，每个 question 一条 question
observation；并发两个 conversation 时 id 和字段不串写。

- [x] **Step 2: 运行测试并确认 RED**

Run:

```bash
uv run pytest tests/test_prediction_efficiency_observations.py -q
```

Expected: runner does not yet emit observations.

- [x] **Step 3: 修改 worker batch**

新增：

```python
@dataclass(frozen=True)
class _ConversationIngestBatch:
    conversation_id: str
    observations: tuple[EfficiencyObservation, ...]


@dataclass(frozen=True)
class _ConversationAnswerBatch:
    conversation_id: str
    predictions: tuple[dict[str, Any], ...]
    observations: tuple[EfficiencyObservation, ...] = ()
```

`_ingest_one()` 在 `conversation_scope` 中使用 `perf_counter_ns()` 测量完整 add；
成功后记录 `memory_build_total_latency_ms`。`_answer_conversation_questions()` 为每题建立
`question_scope`。worker 只返回 bundle，协调层串行调用
`EfficiencyArtifactStore.merge_observations()`。

- [x] **Step 4: 明确 unsupported 行为**

如果 adapter 没有记录 retrieval：

```python
collector.record_retrieval_unsupported(
    reason="method does not expose a separable retrieval boundary"
)
```

只有 method registration/profile 明确允许 unsupported 时才能提交；必需指标缺失时在
付费运行前校验失败。

- [x] **Step 5: 验证 runner、并发和 resume**

Run:

```bash
uv run pytest tests/test_prediction_efficiency_observations.py tests/test_prediction_runner.py tests/test_turn_ingest_resume.py -q
```

Expected: all tests pass; torn-tail recovery and resume do not duplicate observation ids.

### Task 5：为 method factory 和现有 adapters 接入精确观测

**Files:**
- Modify: `src/memory_benchmark/methods/registry.py`
- Modify: `src/memory_benchmark/methods/mem0_adapter.py`
- Modify: `src/memory_benchmark/methods/memoryos_adapter.py`
- Test: `tests/test_method_efficiency_observations.py`
- Test: `tests/test_mem0_adapter.py`
- Test: `tests/test_memoryos_adapter.py`

- [x] **Step 1: 写 factory 传递和关闭观测等价测试**

`MethodBuildContext` 增加：

```python
efficiency_collector: EfficiencyCollector | None = None
```

测试断言 factory 把同一 collector 传给 adapter；collector 为 `None` 时，原有 fake
backend 调用参数、返回答案和 metadata 与修改前一致。

- [x] **Step 2: 运行测试并确认 RED**

Run:

```bash
uv run pytest tests/test_method_efficiency_observations.py tests/test_mem0_adapter.py tests/test_memoryos_adapter.py -q
```

Expected: factory/adapters do not accept collector.

- [x] **Step 3: 接入 Mem0**

在 `get_answer()` 中分别测量：

```python
retrieval_started = perf_counter_ns()
raw_result = self._memory.search(...)
retrieval_latency_ms = elapsed_ms(retrieval_started)

messages = self._reader_messages(question, memories)
answer_started = perf_counter_ns()
response = self._reader.chat.completions.create(...)
answer_latency_ms = elapsed_ms(answer_started)
```

把最终 messages 中实际注入的 memory context 单独交给匹配 reader tokenizer 计数。
reader response usage 存在时记录 `api_usage`；不存在时使用 profile 声明的 tokenizer。

Mem0 build LLM/embedding 内部 usage 优先通过官方 client/provider 接口或轻量 wrapper
采集：

- extraction LLM 使用 Mem0 官方 `OpenAIConfig.response_callback` 读取 response usage。
- reader LLM 使用 adapter 直接持有的 response 读取 usage。
- embedding 在官方 `embedding_model.embed/embed_batch` 实例边界计时，并根据
  `memory_action=add/update/search` 映射到 build/retrieval；官方返回值不暴露 usage 时，
  使用 `text-embedding-3-small` 对应 tokenizer 计数并标记 `tokenizer_estimate`。

上述方案不修改 Mem0 第三方源码。

- [x] **Step 4: 接入 MemoryOS**

在 `get_answer()` 中分别包围官方：

```python
state.retrieval_system.retrieve(...)
generate_system_response_with_meta(...)
```

当前 Phase G compact 观测不做 component-level breakdown，因此不修改第三方
`main_loco_parse.py`。`injected_memory_context_tokens` 使用 adapter 可见的 retrieval
queue 与 long-term knowledge 聚合文本计数；若未来需要拆分 history/profile/knowledge
组件，再进入 Task 8 的纯 observer patch。

MemoryOS adapter 已接管 `OpenAIClient.chat_completion` 和 `get_embedding`：

- `_chat_completion_with_retry()` 从成功 response 读取 usage，并按 collector 当前
  build/answer stage 上报。
- `_get_embedding()` 在 cache miss 时记录本地 embedding 输入 token 与 latency；
  cache hit 不伪造新的 embedding call。
- `retrieval_system.retrieve()` 和最终 answer generation 分别使用明确 stage scope。

- [x] **Step 5: 运行 adapter focused tests**

Run:

```bash
uv run pytest tests/test_method_efficiency_observations.py tests/test_mem0_adapter.py tests/test_memoryos_adapter.py tests/test_memoryos_registered_prediction.py -q
```

Expected: all tests pass without network.

2026-06-16 focused GREEN:

```bash
uv run pytest tests/test_prediction_efficiency_observations.py \
  tests/test_efficiency_entities.py \
  tests/test_efficiency_collector.py \
  tests/test_efficiency_storage.py \
  tests/test_method_efficiency_observations.py \
  tests/test_mem0_adapter.py \
  tests/test_memoryos_adapter.py \
  tests/test_prediction_cli.py::test_registered_prediction_wires_efficiency_observability_when_enabled -q
# 194 passed, 2 subtests passed

uv run python -m compileall -q src/memory_benchmark tests
# exit 0
```

### Task 6：接入实际 LLM Judge observation

**Files:**
- Modify: `src/memory_benchmark/evaluators/llm_judge.py`
- Modify: `src/memory_benchmark/runners/evaluation.py`
- Modify: `src/memory_benchmark/storage/experiment_paths.py`
- Test: `tests/test_judge_efficiency_observations.py`
- Test: `tests/test_llm_judge_parsing.py`
- Test: `tests/test_artifact_evaluation_runner.py`

- [x] **Step 1: 写 Judge 未运行/实际运行的失败测试**

测试要求：

```python
def test_offline_f1_does_not_create_judge_observations(...):
    run_artifact_evaluation(..., evaluator=LocomoF1Evaluator(), ...)
    assert not paths.evaluator_efficiency_observations_path(
        "locomo_f1"
    ).exists()


def test_actual_judge_call_records_usage(...):
    evaluator = LoCoMoJudgeEvaluator(
        mode="compact",
        client=FakeResponsesClient(input_tokens=41, output_tokens=1),
    )
    ...
    assert record["stage"] == "judge"
    assert record["input_tokens"] == 41
    assert record["output_tokens"] == 1
```

- [x] **Step 2: 运行测试并确认 RED**

Run:

```bash
uv run pytest tests/test_judge_efficiency_observations.py tests/test_llm_judge_parsing.py -q
```

Expected: evaluator has no collector integration.

- [x] **Step 3: 修改 Judge evaluator**

`LLMJudgeEvaluator` 接收可选 collector 和 model descriptor。`_call_model()` 返回文本和
usage：

```python
@dataclass(frozen=True)
class JudgeModelResponse:
    text: str
    input_tokens: int
    output_tokens: int
    measurement_source: MeasurementSource
```

真实 API usage 优先；缺失时使用匹配 tokenizer。只有调用成功才记录 Judge observation。

- [x] **Step 4: evaluator runner 写独立 artifact**

`run_artifact_evaluation()` 对实际支持 observation 的 evaluator 建立 evaluator scope，
将记录写入：

```text
artifacts/model_inventory.<metric_name>.json
artifacts/efficiency_observations.<metric_name>.jsonl
```

离线 F1 evaluator 不创建空文件。Judge resume/重跑时同 id 同内容可复用，不同内容报错。

- [x] **Step 5: 运行 evaluator focused tests**

Run:

```bash
uv run pytest tests/test_judge_efficiency_observations.py tests/test_llm_judge_parsing.py tests/test_artifact_evaluation_runner.py -q
```

Expected: all tests pass without network.

2026-06-16 focused GREEN:

```bash
uv run pytest tests/test_judge_efficiency_observations.py \
  tests/test_llm_judge_parsing.py \
  tests/test_artifact_evaluation_runner.py \
  tests/test_evaluator_registry.py \
  tests/test_main_cli.py -q
# 48 passed

uv run pytest tests/test_prediction_efficiency_observations.py \
  tests/test_efficiency_entities.py \
  tests/test_efficiency_collector.py \
  tests/test_efficiency_storage.py \
  tests/test_method_efficiency_observations.py \
  tests/test_mem0_adapter.py \
  tests/test_memoryos_adapter.py \
  tests/test_judge_efficiency_observations.py \
  tests/test_llm_judge_parsing.py \
  tests/test_artifact_evaluation_runner.py \
  tests/test_evaluator_registry.py \
  tests/test_main_cli.py -q
# 241 passed, 2 subtests passed

uv run python -m compileall -q src/memory_benchmark tests
# exit 0
```

### Task 7：实现离线效率聚合与真实价格计算

**Files:**
- Create: `src/memory_benchmark/analysis/__init__.py`
- Create: `src/memory_benchmark/analysis/efficiency.py`
- Create: `src/memory_benchmark/analysis/cost.py`
- Test: `tests/test_efficiency_analysis.py`
- Test: `tests/test_cost_analysis.py`

- [x] **Step 1: 写聚合和防重复计费失败测试**

核心断言：

```python
def test_cost_does_not_charge_injected_context_twice():
    report = calculate_cost(
        observations=[
            llm_call(stage="answer", input_tokens=100, output_tokens=10),
            question_efficiency(injected_memory_context_tokens=40),
        ],
        prices={"answer-llm": api_llm_price(input_per_million=1, output_per_million=2)},
    )
    assert report.total_cost == Decimal("0.00012")


def test_missing_api_price_is_reported_not_silently_zero():
    report = calculate_cost(observations=[api_llm_call(model_id="unknown")], prices={})
    assert report.complete is False
    assert report.missing_price_model_ids == ("unknown",)
```

- [x] **Step 2: 运行测试并确认 RED**

Run:

```bash
uv run pytest tests/test_efficiency_analysis.py tests/test_cost_analysis.py -q
```

Expected: analysis modules do not exist.

Actual:

```bash
uv run pytest tests/test_efficiency_analysis.py tests/test_cost_analysis.py -q
# 2 collection errors: ModuleNotFoundError: No module named 'memory_benchmark.analysis'
```

- [x] **Step 3: 实现无价格聚合**

`aggregate_efficiency()` 输出：

- build/retrieval/answer latency 的 count、sum、mean、P50、P95。
- retrieval supported/unsupported count。
- injected context token 的 count、sum、mean、P50、P95。
- 按 stage/model 汇总 LLM input/output。
- 按 stage/model 汇总 embedding input token/latency。

百分位算法固定写入 docstring 和测试，避免不同报告实现不一致。

- [x] **Step 4: 实现价格配置和 Decimal 计算**

提供强类型价格：

```python
@dataclass(frozen=True)
class APILLMPrice:
    input_cost_per_million_tokens: Decimal
    output_cost_per_million_tokens: Decimal
    currency: str


@dataclass(frozen=True)
class APIEmbeddingPrice:
    input_cost_per_million_tokens: Decimal
    currency: str
```

本地模型费用固定为 0；API 模型缺价格时报告 incomplete。不同币种不得直接相加。

- [x] **Step 5: 运行 analysis tests**

Run:

```bash
uv run pytest tests/test_efficiency_analysis.py tests/test_cost_analysis.py -q
```

Expected: all tests pass.

Actual:

```bash
uv run pytest tests/test_efficiency_analysis.py tests/test_cost_analysis.py -q
# 7 passed

uv run pytest tests/test_efficiency_analysis.py tests/test_cost_analysis.py \
  tests/test_efficiency_entities.py \
  tests/test_efficiency_collector.py \
  tests/test_efficiency_storage.py \
  tests/test_efficiency_token_counting.py \
  tests/test_prediction_efficiency_observations.py \
  tests/test_method_efficiency_observations.py \
  tests/test_judge_efficiency_observations.py \
  tests/test_artifact_evaluation_runner.py \
  tests/test_main_cli.py -q
# 95 passed

uv run python -m compileall -q src/memory_benchmark tests
# exit 0

uv run pytest tests/test_documentation_standards.py -q
# 5 passed
```

### Task 8：MemoryOS 纯 observer 插桩、文档同步与阶段验证

**Files:**
- Modify: `third_party/methods/MemoryOS-main/eval/main_loco_parse.py`
- Modify: `src/memory_benchmark/methods/memoryos_adapter.py`
- Modify: `src/memory_benchmark/cli/run_prediction.py`
- Modify: `AGENTS.md`
- Modify: `docs/current-roadmap.md`
- Create: `docs/handoffs/2026-06-15-cost-efficiency-observability.md`
- Test: relevant adapter/source identity tests

- [x] **Step 1: 写 MemoryOS observer on/off 等价失败测试**

固定同一 fake LLM/embedding 输入，并断言 observer 开关前后：

```python
assert result_without_observer == result_with_observer
assert backend_calls_without_observer == backend_calls_with_observer
assert persisted_state_without_observer == persisted_state_with_observer
```

- [x] **Step 2: 运行测试并确认 RED**

Run:

```bash
uv run pytest tests/test_method_efficiency_observations.py -q
```

Expected: official function does not expose the context observer hook.

Actual:

```bash
uv run pytest tests/test_memoryos_adapter.py::MemoryOSAdapterTests::test_official_memory_context_observer_does_not_change_generation_result \
  tests/test_memoryos_adapter.py::MemoryOSAdapterTests::test_get_answer_uses_observed_final_memory_context_tokens -q
# 2 failed
```

RED 失败点：

- `observed_payloads` 为空，说明官方 `generate_system_response_with_meta()` 尚未触发
  `memory_context_observer`。
- 空 retrieval result 时 `injected_memory_context_tokens == 0`，说明 wrapper 尚未用最终
  prompt 的 memory context observer payload 计数。

- [x] **Step 3: 实施最小纯观测 patch**

在官方模块中增加模块级可选 callback：

```python
memory_context_observer = None
```

`generate_system_response_with_meta()` 完成 context parts 构造后，在发送 LLM 前调用：

```python
if memory_context_observer is not None:
    try:
        memory_context_observer(
            {
                "history_text": history_text,
                "retrieval_text": retrieval_text,
                "user_profile_and_knowledge": background,
                "assistant_knowledge": assistant_knowledge_text,
            }
        )
    except Exception:
        pass
```

callback 异常不能改变官方算法返回。adapter 在 `_patch_eval_modules()` 注入 callback。
记录未插桩 upstream tree hash 和 instrumentation patch hash，并更新 source identity；
不得修改 Mem0 第三方源码。

Actual:

- `third_party/methods/MemoryOS-main/eval/main_loco_parse.py` 增加模块级
  `memory_context_observer = None`。
- 官方 `generate_system_response_with_meta()` 在发送 LLM 前把最终 prompt 中的
  `history_text`、`retrieval_text`、`user_profile_and_knowledge`、
  `assistant_knowledge` 旁路传给 observer。
- observer 异常被吞掉，不改变答案、prompt、client 调用和状态。
- `MemoryOS._patch_eval_modules()` 注入实例级 callback。
- wrapper 优先使用 observer payload 计算 `injected_memory_context_tokens`；
  未触发 observer 时回退到原有 retrieval result 文本。

- [x] **Step 4: 运行 focused 与完整离线回归**

Run:

```bash
uv run pytest tests/test_efficiency_entities.py \
  tests/test_efficiency_collector.py \
  tests/test_efficiency_storage.py \
  tests/test_efficiency_token_counting.py \
  tests/test_prediction_efficiency_observations.py \
  tests/test_method_efficiency_observations.py \
  tests/test_judge_efficiency_observations.py \
  tests/test_efficiency_analysis.py \
  tests/test_cost_analysis.py -q

uv run pytest -q
uv run pytest -m memoryos -q
uv run pytest -m api --collect-only -q
uv run python -m compileall -q src/memory_benchmark tests
```

Expected: all offline tests pass; API tests are collected but not executed.

Actual:

```bash
uv run pytest tests/test_memoryos_adapter.py::MemoryOSAdapterTests::test_official_memory_context_observer_does_not_change_generation_result \
  tests/test_memoryos_adapter.py::MemoryOSAdapterTests::test_get_answer_uses_observed_final_memory_context_tokens -q
# 2 passed

uv run pytest tests/test_memoryos_adapter.py tests/test_method_efficiency_observations.py tests/test_memoryos_registered_prediction.py -q
# 141 passed, 2 subtests passed

uv run pytest tests/test_efficiency_analysis.py tests/test_cost_analysis.py \
  tests/test_efficiency_entities.py \
  tests/test_efficiency_collector.py \
  tests/test_efficiency_storage.py \
  tests/test_efficiency_token_counting.py \
  tests/test_prediction_efficiency_observations.py \
  tests/test_method_efficiency_observations.py \
  tests/test_judge_efficiency_observations.py \
  tests/test_memoryos_adapter.py \
  tests/test_memoryos_registered_prediction.py \
  tests/test_artifact_evaluation_runner.py \
  tests/test_main_cli.py -q
# 232 passed, 2 subtests passed

uv run pytest -m memoryos -q
# 172 passed, 353 deselected, 2 subtests passed

uv run pytest -m api --collect-only -q
# 3/525 tests collected (522 deselected)

uv run pytest -q
# 522 passed, 3 deselected, 6 subtests passed

uv run python -m compileall -q src/memory_benchmark tests third_party/methods/MemoryOS-main/eval/main_loco_parse.py
# exit 0

uv run pytest tests/test_documentation_standards.py -q
# 5 passed
```

- [x] **Step 5: 校验受保护资产**

Run:

```bash
find outputs/memoryos-locomo-full-20260603 -type f -print0 \
  | sort -z \
  | xargs -0 shasum -a 256 \
  | shasum -a 256
```

Expected:

```text
2bf09d4109396feb7af4eb174d21bff791afc1c03b5a8ba62180da1315df642f
```

Actual:

```text
2bf09d4109396feb7af4eb174d21bff791afc1c03b5a8ba62180da1315df642f  -
```

- [x] **Step 6: 更新项目状态**

只有全部验证和阶段级综合 review 通过后：

- 勾选 `docs/current-roadmap.md` Phase G 已完成项。
- 更新 `AGENTS.md` 当前断点、测试基线和下一步。
- 在 handoff 记录 observer patch、验证命令、测试数和未支持指标。
- 不启动任何真实 API smoke 或 full run。

Actual:

- `Franklin` 只读阶段级综合 review：`APPROVED`，无 Critical/Important findings。
- Reviewer 发现 handoff 中间历史“当前断点”仍写 Task 6；已改为“历史断点（已完成）”，
  并指向文件末尾最新稳定断点。
- `docs/current-roadmap.md` 已标记 Phase G 阶段验证/review 完成。
- `AGENTS.md` 已更新为 Phase G 完成，下一步是 Phase H 通用并行调度设计/实施。
