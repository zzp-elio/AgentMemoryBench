# Dataset Variant 与 LongMemEval 闭环设计

更新日期：2026-06-14

## 1. 目标

Phase F 建立 benchmark-owned dataset variant 契约，并让 LongMemEval 的
`s_cleaned`、`m_cleaned` 都能通过统一 conversation-QA prediction 入口运行。

本阶段同时移除通用 registered runner 对 LoCoMo smoke 逻辑的直接依赖，使 runner
只处理通用编排，benchmark-specific 数据选择与 smoke 裁剪由 benchmark registration
负责。

## 2. 范围

本阶段实现：

- benchmark variant 强类型声明与校验；
- LongMemEval `s_cleaned`、`m_cleaned` 和选择器 `all`；
- `all` 展开为多个独立且不可变的 child run；
- LoCoMo smoke 裁剪迁入 benchmark registration hook；
- manifest schema v2，显式记录 concrete variant 和 run scope；
- LongMemEval registered prediction；
- `predict`、`run` 的批次结果；
- 离线 contract、adapter、runner、resume 和 CLI 测试。

本阶段不实现：

- HaluMem adapter 或 Medium/Long prediction；
- retrieval recall；
- LongMemEval oracle variant；
- 效率指标；
- 多个 child run 的并行调度；
- 真实全量 API 实验；
- MemoryOS PyPI backend。

## 3. 核心概念

### 3.1 Method Profile

method profile 继续描述 method 自身参数，例如：

```text
smoke
official-full
custom
```

它控制模型、embedding、top-k、并发和写入批次等 method 行为。

### 3.2 Benchmark Variant

benchmark variant 只描述 benchmark 数据版本，例如：

```text
LoCoMo:
  locomo10

LongMemEval:
  s_cleaned
  m_cleaned
```

variant 不能写入 method TOML，也不能成为 method capability。

### 3.3 Variant Selector

`all` 是命令层选择器，不是 concrete variant，不允许进入 adapter、Dataset metadata、
manifest、fingerprint 或 evaluator artifact。

```text
longmemeval + all
  -> longmemeval + s_cleaned
  -> longmemeval + m_cleaned
```

底层单次 prediction runner 永远只接收一个 concrete variant。

### 3.4 Run Scope

run scope 描述一次运行使用完整数据还是低成本 smoke 范围：

```python
class RunScope(StrEnum):
    SMOKE = "smoke"
    FULL = "full"
```

run scope 与 method profile 分开记录。当前 profile 名仍决定默认 scope：

- `smoke` profile -> `smoke`
- 其他正式 profile -> `full`

该映射集中在命令编排层，不让底层 runner根据字符串猜测 benchmark 行为。

## 4. Benchmark 注册契约

新增 benchmark-owned 类型，建议放在：

```text
src/memory_benchmark/benchmark_adapters/contracts.py
```

核心结构：

```python
@dataclass(frozen=True)
class BenchmarkVariantSpec:
    name: str
    source_relative_paths: tuple[Path, ...]


@dataclass(frozen=True)
class BenchmarkLoadRequest:
    variant: str
    run_scope: RunScope
    smoke_turn_limit: int
    smoke_conversation_limit: int


@dataclass(frozen=True)
class PreparedBenchmarkRun:
    variant: str
    run_scope: RunScope
    dataset: Dataset
    source_relative_paths: tuple[Path, ...]
```

`BenchmarkRegistration` 增加：

```python
variants: tuple[BenchmarkVariantSpec, ...]
default_variant: str
prepare_run: Callable[
    [Path, BenchmarkLoadRequest],
    PreparedBenchmarkRun,
]
```

registration 必须在注册时强校验：

- variant 名称非空且唯一；
- `default_variant` 必须属于 concrete variants；
- concrete variant 不能命名为 `all`；
- source path 必须是项目根目录下的相对路径，不能是绝对路径或包含 `..`；
- `prepare_run()` 返回的 variant 必须和请求一致；
- Dataset metadata 必须包含相同的 `variant` 和 `run_scope`。

`source_relative_paths` 不再作为 registration 顶层静态字段，因为 LongMemEval 的实际
source path 取决于 concrete variant。运行时只使用 `PreparedBenchmarkRun` 返回的路径。

`smoke_turn_limit` 是现有 LoCoMo CLI 的兼容参数，只有 LoCoMo preparation hook 消费；
LongMemEval 明确忽略它且不裁剪内部 history。本阶段不为尚不存在的更多 benchmark
预先设计通用 benchmark-option 插件系统。

## 5. Adapter 构造

### 5.1 LoCoMo

LoCoMo 只有一个 concrete variant：

```text
locomo10 -> data/locomo/locomo10.json
```

`LoCoMoAdapter` 保持默认构造可用，便于现有 loader 和 dry-run：

```python
LoCoMoAdapter(project_root)
```

LoCoMo registration 的 `prepare_run()`：

- `full`：加载完整 `locomo10`；
- `smoke`：先按 conversation limit 加载，再调用现有
  `build_locomo_smoke_dataset()`；
- smoke 保留 evidence 覆盖约束；
- 最终 Dataset metadata 写入：
  - `variant = "locomo10"`
  - `run_scope = "smoke" | "full"`。

通用 prediction service 不再 import `build_locomo_smoke_dataset`。

### 5.2 LongMemEval

LongMemEval adapter 构造改为：

```python
LongMemEvalAdapter(project_root, variant="s_cleaned")
```

支持：

```text
s_cleaned -> data/longmemeval/longmemeval_s_cleaned.json
m_cleaned -> data/longmemeval/longmemeval_m_cleaned.json
```

默认仍为 `s_cleaned`，保证：

```python
LongMemEvalAdapter(project_root)
```

继续读取 S variant。

adapter 必须拒绝未知 variant，不能静默回退。Dataset 和 Conversation metadata 中的
source path、split、variant 必须反映实际选择。

LongMemEval registration 的 `prepare_run()`：

- `full`：加载 concrete variant 全部 500 instances；
- `smoke`：加载一个完整 evaluation instance；
- smoke 不裁剪该 instance 内的 sessions 或 turns；
- smoke 默认只回答该 instance 唯一问题；
- Dataset metadata 写入 concrete variant 和 run scope。

不把 LongMemEval 的长历史截断成 oracle-style 数据。

## 6. Selector 与 Run 展开

命令层增加：

```text
--variant <name|all>
```

未提供时使用 registration 的 `default_variant`。

selector 解析函数返回 concrete variants：

```python
resolve_variant_selector(registration, None)
-> ("default_variant",)

resolve_variant_selector(registration, "s_cleaned")
-> ("s_cleaned",)

resolve_variant_selector(registration, "all")
-> ("s_cleaned", "m_cleaned")
```

顺序使用 registration 声明顺序，保证可复现。

LoCoMo 的 `all` 只展开为 `locomo10`；它不会制造重复 run。

## 7. Run ID 规则

LongMemEval 是多 variant benchmark，child run ID 必须包含 concrete variant。

用户提供基础 ID：

```text
--benchmark longmemeval --variant all --run-id exp1
  -> exp1-s-cleaned
  -> exp1-m-cleaned
```

显式单 variant 同样使用 concrete 后缀：

```text
--benchmark longmemeval --variant s_cleaned --run-id exp1
  -> exp1-s-cleaned
```

自动生成：

```text
<method>-longmemeval-<variant>-<profile>-<random>
```

LoCoMo 是单 variant benchmark，继续保留现有 run ID 规则，不追加 `locomo10`，避免无意义
破坏现有使用方式。

run ID 生成必须集中在一个纯函数中，并拒绝：

- 空基础 ID；
- 已带相同 variant 后缀而导致双重后缀；
- 多个 child run 解析成相同 ID；
- 路径逃逸字符。

## 8. 批次执行和原子预检

新增批次编排层：

```text
PredictCommand
  -> resolve concrete variants
  -> build every PreparedBenchmarkRun
  -> build every child run identity
  -> preflight every child
  -> execute children sequentially
```

本阶段 child run 串行执行。跨 run 并行属于 Phase G。

`all` 必须先对所有 child run 完成只读预检，确认：

- variant 有效；
- source file 存在；
- run ID 不冲突；
- resume manifest 兼容；
- method/benchmark capability 兼容；
- API/full 成本确认已经满足。

只有全部 child preflight 通过后，才允许：

- 创建任一输出目录；
- 构造任一 method；
- 读取 `.env` secret；
- 发起 API 请求。

如果第二个 child 预检失败，第一个 child 也不能留下新目录或产生 API 成本。

为满足该边界，配置加载拆成两阶段：

1. preflight 前只调用 `load_path_settings()`，读取 method TOML、benchmark 数据和源码
   identity，不读取 `.env`；
2. 全部 child preflight 通过后再调用 `load_openai_settings()`，构造 method 并执行。

`RunContext.create(..., ensure_directories=False)` 可以用于只读 preflight，但此阶段不得
调用 `ensure_directories()`。

## 9. Manifest 与 Resume

generic prediction manifest 升级：

```json
{
  "schema_version": 2,
  "benchmark_name": "longmemeval",
  "benchmark_variant": "s_cleaned",
  "run_scope": "smoke"
}
```

以下内容共同构成不可变实验身份：

- benchmark name；
- concrete variant；
- run scope；
- dataset SHA-256；
- 实际 source path 指纹；
- method name、源码身份和配置；
- model name；
- prediction policy。

resume 必须逐字段完全一致。

schema v1 generic run：

- 继续允许 artifact-only evaluation；
- 不自动补写 v2 字段；
- 不允许通过 v2 registered prediction service resume；
- 错误信息明确说明应继续使用兼容旧入口，或使用新 run ID。

受保护 legacy MemoryOS-LoCoMo run 不走 generic schema，本阶段不修改其文件和恢复逻辑。

## 10. 公共命令结果

`predict` 统一返回批次：

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

即使只运行一个 concrete variant，`runs` 也只有一个元素，不返回两种不同类型。

`run` 返回：

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

每个 child prediction 只评测自己的 artifacts。不同 variants 的指标不合并、不平均。

Python 内部兼容函数 `run_mem0_locomo_prediction()` 可以暂时继续返回单个
`PredictionRunSummary`，作为明确标记的旧调用兼容层；统一 CLI 和 command service 使用
批次结果。

## 11. CLI 与 Python API

统一 CLI：

```text
memory-benchmark predict \
  --method mem0 \
  --benchmark longmemeval \
  --variant s_cleaned \
  --profile smoke
```

`predict` 和 `run` 都接受 `--variant`。

CLI parser 不硬编码不同 benchmark 的 variant choices，因为 choices 取决于
`--benchmark`。解析后由 command service 根据 registration 强校验，并返回包含允许值的
领域错误。

当前 Python API 仍只接受官方已注册 benchmark。自定义 benchmark 插件机制不在本阶段。

## 12. LongMemEval Prediction

LongMemEval registration 的 `prediction_enabled` 改为 `True`。

兼容性仍使用：

```text
TaskFamily.CONVERSATION_QA
CONVERSATION_ADD
ANSWER_GENERATION
```

LongMemEval 不要求 public retrieval 接口。

prediction artifacts 继续保存：

- method public question；
- method answer；
- evaluator-only gold answer；
- category/question type；
- question time；
- conversation ID。

`answer_session_ids`、`has_answer` 和其他 evidence 不能进入 method public input。

LongMemEval 的 LLM judge 继续通过 artifact-only evaluation 单独执行。真实 judge API
需要显式 `--confirm-api`，本阶段只做离线装配测试。

## 13. 错误处理

必须在创建 run 目录或读取 secret 前拒绝：

- benchmark 不支持请求的 variant；
- adapter 返回的 variant 与请求不一致；
- concrete variant source file 缺失；
- `all` child run ID 冲突；
- `resume=True` 但没有明确基础 run ID；
- schema v1 run 尝试通过 v2 service resume；
- existing manifest 的 variant/run scope 不匹配；
- LongMemEval smoke 被配置为裁剪内部 history。

错误使用项目 `ConfigurationError` 或更具体的 benchmark 配置异常，不抛裸
`KeyError`、`ValueError`。

## 14. 测试策略

### 14.1 Variant Contract

- registration variant 名唯一；
- default variant 必须存在；
- `all` 不允许作为 concrete variant；
- 未知 variant 明确报错；
- selector 展开顺序稳定。

### 14.2 LongMemEval Adapter

- 默认读取 `s_cleaned`；
- 显式读取 `m_cleaned`；
- 两者各加载 500 instances；
- source path、split、variant metadata 正确；
- M variant 保持 private labels 隔离；
- 未知 variant 失败。

### 14.3 Benchmark Preparation

- LoCoMo smoke 行为与当前结果一致；
- 通用 runner 不直接 import LoCoMo；
- LongMemEval smoke 保留完整 instance 历史；
- full 不做 smoke 裁剪。

### 14.4 Batch Expansion

- default selector 产生一个 child；
- `all` 产生 S/M 两个 child；
- run ID 后缀稳定；
- 全部 child preflight 成功前没有目录、secret 或 method 副作用；
- 一个 child 预检失败时没有部分运行。

### 14.5 Manifest 与 Resume

- schema v2 含 variant/run scope；
- variant 或 scope 变化导致 resume 拒绝；
- source path 指向 concrete variant；
- v1 artifact 仍可 evaluate；
- v1 run 不能走 v2 resume。

### 14.6 CLI 与 Commands

- `--variant` 正确进入 command；
- LongMemEval 出现在 prediction choices；
- predict 单 variant 也返回 batch；
- run 对每个 child 分别 evaluate；
- 未知 variant 的错误列出允许值。

### 14.7 Verification

最终离线验收：

```bash
uv run pytest -q
uv run pytest -m api --collect-only -q
uv run pytest -m memoryos -q
uv run pytest tests/test_documentation_standards.py -q
uv run python -m compileall -q src/memory_benchmark tests
```

不得执行真实 API。

受保护实验聚合 SHA-256 必须仍为：

```text
2bf09d4109396feb7af4eb174d21bff791afc1c03b5a8ba62180da1315df642f
```

## 15. 完成标准

Phase F 完成需同时满足：

- 通用 prediction service 不再 import 具体 benchmark；
- LongMemEval S/M adapter 均通过真实数据全量结构测试；
- `all` 只产生独立 child runs；
- manifest/resume 明确区分 variant 和 scope；
- LongMemEval registered prediction 可离线完成装配和 preflight；
- public/private 数据边界没有退化；
- 完整离线回归通过；
- 阶段级综合 review 通过；
- 未调用真实 API。
