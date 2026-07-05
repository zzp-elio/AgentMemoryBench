# Mem0 Generic Prediction Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

状态：2026-06-12 已完成 Tasks 1-6 并通过默认回归；下一阶段是单独设计和批准
2-conversation 真实并发隔离 smoke，不属于本计划的已批准付费范围。

**Goal:** 使用 vendored Mem0 OSS 源码和通用 conversation-QA runner，在一个低成本 LoCoMo 小样本上生成并持久化回复，不计算 metric。

**Architecture:** `Mem0` adapter 只负责官方算法配置、conversation namespace、逐 turn 写入、检索和固定 reader；通用 prediction runner 只依赖 `BaseMemorySystem`，负责公开数据边界、conversation 调度、预测/私有标签 artifact 和 checkpoint。smoke/full profile 显式分离，真实 API 测试默认跳过。

**Tech Stack:** Python 3.11+、uv、pytest、Mem0 OSS 2.0.4、OpenAI-compatible API、Qdrant local、Rich、JSONL artifacts。

---

## 文件结构

- `src/memory_benchmark/methods/mem0_adapter.py`：Mem0 配置 profile、源码装载、消息转换、add/search/reader。
- `src/memory_benchmark/runners/prediction.py`：与 benchmark/method 无关的 prediction runner。
- `src/memory_benchmark/cli/run_prediction.py`：选择 benchmark、method、profile 后启动 runner。
- `tests/test_mem0_adapter.py`：fake Mem0/fake reader 下验证 adapter 契约。
- `tests/test_prediction_runner.py`：fake method 下验证 artifacts、数据边界、resume 和 conversation 调度。
- `tests/test_mem0_locomo_api.py`：显式启用的单 conversation、少量 turn、单 question 真实 API smoke。
- `pyproject.toml`：增加 `mem0` pytest marker，不把真实 API smoke 放入默认测试。
- `AGENTS.md` 与 `docs/handoffs/2026-06-11-mem0-locomo-parallel-runner.md`：同步当前断点和验证结果。

### Task 1: 锁定 Mem0 profile 与源码身份

**Files:**
- Modify: `src/memory_benchmark/methods/mem0_adapter.py`
- Create: `tests/test_mem0_adapter.py`

- [ ] **Step 1: 写失败测试**

测试 `Mem0Config.smoke()` 和 `Mem0Config.official_full()`，要求：

```python
assert smoke.extraction_model == "gpt-4o-mini"
assert smoke.embedding_model == "text-embedding-3-small"
assert smoke.top_k == 10
assert smoke.max_workers == 1
assert full.top_k == 200
assert full.max_workers == 10
assert full.ingestion_chunk_size == 1
assert full.infer is True
```

同时测试源码身份摘要包含 `package_version == "2.0.4"` 和 64 位 SHA-256，且不包含
`memory-benchmarks/.git`、缓存、输出文件。

- [ ] **Step 2: 验证 RED**

Run:

```bash
uv run pytest tests/test_mem0_adapter.py -q
```

Expected: FAIL，因为 `Mem0Config` 和源码身份函数尚不存在。

- [ ] **Step 3: 最小实现**

在 `mem0_adapter.py` 增加不可变配置对象：

```python
@dataclass(frozen=True)
class Mem0Config:
    extraction_model: str
    embedding_model: str
    embedding_dimensions: int
    top_k: int
    max_workers: int
    ingestion_chunk_size: int = 1
    infer: bool = True
```

增加 `smoke()`、`official_full()` 构造器，以及只遍历 Mem0 核心源码文件的确定性
SHA-256 计算函数。API key 不进入配置序列化结果。

- [ ] **Step 4: 验证 GREEN**

Run:

```bash
uv run pytest tests/test_mem0_adapter.py -q
```

Expected: profile 与 source identity 测试 PASS。

### Task 2: 实现真实 Mem0 adapter 契约

**Files:**
- Modify: `src/memory_benchmark/methods/mem0_adapter.py`
- Modify: `tests/test_mem0_adapter.py`

- [ ] **Step 1: 写失败测试**

通过 fake `Memory` 和 fake OpenAI reader 验证：

```python
system.add([conversation])
prediction = system.get_answer(question)
```

必须满足：

- 每个 turn 独立调用一次 `Memory.add(..., run_id=conversation_id, infer=True)`。
- speaker 名称写入 content，role 使用公开 `normalized_role` 或稳定映射。
- session/turn 时间进入公开 metadata。
- search 使用 `filters={"run_id": question.conversation_id}` 和 profile `top_k`。
- question 指向未写入 conversation 时抛领域异常。
- 返回 `AnswerResult` 的 id、conversation_id 和 answer 对齐。
- metadata 可包含脱敏后的检索结果，不包含 API key、gold、evidence。

- [ ] **Step 2: 验证 RED**

Run:

```bash
uv run pytest tests/test_mem0_adapter.py -q
```

Expected: FAIL，因为占位 `Mem0` 仍会抛 `ConfigurationError`。

- [ ] **Step 3: 最小实现**

实现：

```python
class Mem0(BaseMemorySystem):
    def add(self, conversations: list[Conversation]) -> AddResult: ...
    def get_answer(self, question: Question) -> AnswerResult: ...
```

构造时支持注入 fake `memory_backend` 和 `reader_client`；生产模式才从 vendored
`mem0.Memory.from_config()` 构造 backend。LLM 与 embedder 都注入项目
`OpenAISettings.api_key/base_url`；Qdrant path 和 history DB 放在当前 run 的 method
state 目录。设置 `MEM0_TELEMETRY=False`，不修改第三方源码。

- [ ] **Step 4: 验证 GREEN**

Run:

```bash
uv run pytest tests/test_mem0_adapter.py tests/test_mem0_source_compatibility.py -q
```

Expected: adapter 与 vendored source contract 全部 PASS。

### Task 3: 通用 prediction runner

**Files:**
- Create: `src/memory_benchmark/runners/prediction.py`
- Create: `tests/test_prediction_runner.py`
- Modify: `src/memory_benchmark/runners/__init__.py`

- [ ] **Step 1: 写失败测试**

构造两个 conversation 的 fake Dataset 和线程安全 fake method，验证：

- runner 只传公开 Conversation/Question。
- `max_workers=1/2` 均能产生一条 prediction/question。
- worker 返回 batch，只有 coordinator 写 JSONL。
- `method_predictions.jsonl` 保存公开问题和 answer。
- `evaluator_private_labels.jsonl` 单独保存 gold。
- `progress.json` 与 conversation/question checkpoint 完整。
- resume 不重复调用已经完成的 question。
- evaluators 为空时不生成 metric artifact，也不调用 scorer。

- [ ] **Step 2: 验证 RED**

Run:

```bash
uv run pytest tests/test_prediction_runner.py -q
```

Expected: FAIL，因为 prediction runner 尚不存在。

- [ ] **Step 3: 最小实现**

定义：

```python
@dataclass(frozen=True)
class PredictionRunPolicy:
    max_workers: int = 1
    conversation_ids: tuple[str, ...] | None = None
    question_limit_per_conversation: int | None = None
    resume: bool = False

def run_predictions(
    dataset: Dataset,
    system: BaseMemorySystem,
    run_context: RunContext,
    policy: PredictionRunPolicy,
    method_manifest: dict[str, object],
) -> PredictionRunSummary:
    ...
```

conversation worker 执行 add 后串行回答本 conversation 的问题；主线程按完成 batch
写 artifacts/checkpoints。复用现有 `RunContext`、`ExperimentPaths`、JSONL 和原子写
工具，不复制 MemoryOS runner 的 method-specific 分支。

- [ ] **Step 4: 验证 GREEN**

Run:

```bash
uv run pytest tests/test_prediction_runner.py tests/test_conversation_runner.py -q
```

Expected: 新旧 runner 契约全部 PASS。

### Task 4: 通用 CLI 与低成本保护

**Files:**
- Create: `src/memory_benchmark/cli/run_prediction.py`
- Modify: `tests/test_prediction_runner.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: 写失败测试**

测试 CLI/build 函数：

- `benchmark=locomo, method=mem0, profile=smoke` 能构建依赖。
- 未传 `--confirm-api` 时拒绝实例化真实 Mem0 backend。
- smoke 强制 1 conversation、1 question，并允许显式限制 turn 数。
- `official-full` 要求再次确认，且配置必须与官方 profile 完全相等。
- 未支持的 benchmark/method/profile 抛 `ConfigurationError`。

- [ ] **Step 2: 验证 RED**

Run:

```bash
uv run pytest tests/test_prediction_runner.py -q
```

Expected: FAIL，因为 CLI/build 函数尚不存在。

- [ ] **Step 3: 最小实现**

CLI 只负责依赖装配，不包含 benchmark 或 method 算法。真实 smoke 命令必须显式：

```bash
uv run python -m memory_benchmark.cli.run_prediction \
  --benchmark locomo \
  --method mem0 \
  --profile smoke \
  --confirm-api
```

在 pytest markers 增加 `mem0`，默认仍排除 `api`。

- [ ] **Step 4: 验证 GREEN**

Run:

```bash
uv run pytest tests/test_prediction_runner.py -q
```

Expected: CLI 保护测试 PASS。

### Task 5: 真实 LoCoMo API smoke

**Files:**
- Create: `tests/test_mem0_locomo_api.py`

- [ ] **Step 1: 编写显式 API smoke**

从真实 LoCoMo adapter 选择 1 个 conversation，保留少量连续 turn 和 1 个 question。
evidence 只用于测试代码选择夹具，随后清空 private payload 再交给 method。测试标记：

```python
pytestmark = [pytest.mark.api, pytest.mark.expensive, pytest.mark.mem0]
```

- [ ] **Step 2: 先运行无网络测试**

Run:

```bash
uv run pytest tests/test_mem0_adapter.py tests/test_prediction_runner.py -q
```

Expected: 全部 PASS。

- [ ] **Step 3: 执行一次真实 smoke**

Run:

```bash
uv run pytest tests/test_mem0_locomo_api.py -q -m "api and mem0"
```

Expected:

- Mem0 `infer=True` 写入成功。
- prediction artifact 恰好 1 条。
- answer 非空。
- 日志和 manifest 不含 API key。
- 不产生 metric/scores。

- [ ] **Step 4: 全量回归**

Run:

```bash
uv run pytest -q
uv run python -m compileall -q src tests
```

Expected: 默认测试不执行真实 API；其余测试全部 PASS，compileall exit 0。

### Task 6: 文档与交接

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/handoffs/2026-06-11-mem0-locomo-parallel-runner.md`

- [ ] **Step 1: 更新当前断点**

记录：

- Mem0 官方 benchmark 配置来源与 vendored source identity。
- 已完成的 adapter/runner 文件。
- smoke 命令、输出目录、实际调用范围和验证结果。
- API 或 backend 的任何兼容问题。
- official full 尚未启动，启动前需要用户再次确认成本。

- [ ] **Step 2: 文档验证**

Run:

```bash
uv run pytest tests/test_documentation_standards.py -q
```

Expected: PASS。

- [ ] **Step 3: 最终核对**

确认没有修改：

- `third_party/methods/mem0-main/mem0/`
- `third_party/methods/mem0-main/memory-benchmarks/`
- `outputs/memoryos-locomo-full-20260603/`
