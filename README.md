# Agent Memory Benchmark Framework

本项目要构建一个可复现、可扩展、可审计的 Agent Memory Benchmark 评测框架。框架读取
benchmark 原始数据，转换为经过校验的 task-family 数据模型，调用 memory method，并把
prediction、运行期观测和 evaluator 结果保存为可复算的标准实验产物。

第一优先用户是希望低门槛运行官方集成的实验使用者；第二类用户是希望评测新 memory
method 的研究者。

当前只实现 **conversation + QA** task family。Phase 1 只做纯文本闭环：

1. 先以 LoCoMo 打通各个 method。
2. 再接入 LongMemEval。

HaluMem、MemBench、Mem-Gallery 当前不进入主线。能自然适配为 conversation + QA 的版本
或切片可后续接入；不能自然适配的内容只有在真实需求明确后，才为其设计新的 task family。
偏好遵循类 benchmark 已从当前项目范围移除，不再恢复 adapter、测试、文档或数据仓库。

未来若出现不能自然表达为 conversation + QA 的 benchmark，将新增独立 task family，而
不是强迫它使用当前实体。第二种真实需求出现前，不提前重构 `core/` 或设计空协议。

完整长期设计见：
[项目目标与架构设计](docs/superpowers/specs/2026-06-12-project-goals-architecture-design.md)。

## 项目层次

```text
src/
  memory_benchmark/
    config/               # .env、路径和 OpenAI 配置读取
    core/                 # 数据实体、抽象接口、校验、领域异常、结果摘要
    benchmark_adapters/   # 原始 benchmark dataset 到统一 Dataset 的转换层
    evaluators/           # answer-level 指标和 LLM judge
    runners/              # 串联 dataset、method、evaluator 的执行层
    methods/              # 官方 method wrapper、profile 装配和能力声明
    observability/         # Rich 进度、事件日志和效率 observation
    storage/               # 标准实验目录、JSONL、fingerprint 和 artifact 工具
    utils/                # logger、运行期日志等通用工具
    cli/                  # 本地 dry-run/debug 命令
tests/                  # 单元测试和可维护性约定测试
docs/                   # 当前架构文档、日志规范、交接文件和开发计划
data/                   # 当前运行时数据入口，本地 benchmark runtime 数据只读使用
third_party/benchmarks/  # 官方 benchmark 仓库与参考源码，本项目只读使用
third_party/methods/    # 项目提供并固定版本的第三方 method 源码
models/                 # 本地模型/NLP 资源
outputs/                # 运行结果、日志和调试产物
old/                    # 历史归档，不作为当前事实来源
```

核心分层原则：

- `core/` 不读取数据、不调用模型、不计算指标，只定义公共语言。
- `benchmark_adapters/` 只做 schema 转换和强校验，不调用 method；当前运行时数据从 `data/` 读取，官方 benchmark 仓库和源码参考在 `third_party/benchmarks/`。
- `runners/` 只调公开对象，不能把标准答案或 evidence 传给 method。
- `evaluators/` 才能读取 `GoldAnswerInfo` 等私有答案信息。
- `methods/` 用 wrapper 隔离第三方源码，runner 不直接依赖第三方内部类。
- `utils/` 放跨模块工具；库代码不直接 `print()` 调试信息。
- `registry` 只保存名称、静态能力和 factory，不保存 secret 或运行实例。

数据结构参考与评测流程参考已经分离到：

- `docs/dataset_structures/`
- `docs/evaluation_workflows/`

当前运行时数据入口是 `data/`，官方 benchmark 仓库与源码参考位于 `third_party/benchmarks/`。这两类外部资产维持只读，路径契约仍以各 benchmark 的原始文件为准。

## 运转逻辑

```text
CLI / Python API
  ↓
Registry + Config Resolver
  ↓
BenchmarkAdapter
  读取本地原始数据
  ↓
Dataset
  Conversation -> Session -> Turn
  Conversation -> Question + GoldAnswerInfo
  ↓
Prediction Runner
  method.add([public Conversation])
  method.get_answer(public Question)
  ↓
标准 predictions + runtime observations
  ↓
Evaluation Runner
  prediction + private GoldAnswerInfo
  ↓
EvaluationResult
  answer-level metrics + per-question details
```

公开/私有边界是框架的硬约束：

- `Conversation` 和 `Question` 是 method 可见输入。
- `GoldAnswerInfo` 只给 evaluator 和审计日志使用。
- gold answer、evidence id、judge label、私有 metadata 不能进入 method。
- runner 会重建 public 对象，避免 Python dataclass 动态属性泄漏。

## 数据模型

核心层级：

```text
Dataset
└── Conversation
    ├── Session
    │   └── Turn
    ├── Question
    └── GoldAnswerInfo
```

实体含义：

- `Dataset`: 一个 benchmark split 的统一载体。
- `Conversation`: 一个独立记忆空间，用 `conversation_id` 隔离。
- `Session`: 一段有边界的历史对话，可带 session-level 时间。
- `Turn`: 单个 speaker 的一次发言；一个 user/assistant round 应拆成两个 turn。
- `Question`: method 可见问题，可带可选时间、类别、选项和公开 metadata。
- `GoldAnswerInfo`: evaluator 私有标准答案信息。
- `ImageRef`: 为后续多模态保留；Phase 1 不主动处理图片。

## Method 接口

完整记忆系统实现：

```python
from memory_benchmark.core import AddResult, AnswerResult, Conversation, Question
from memory_benchmark.core.interfaces import BaseMemorySystem


class MyMemorySystem(BaseMemorySystem):
    def add(self, conversations: list[Conversation]) -> AddResult:
        ...

    def get_answer(self, question: Question) -> AnswerResult:
        ...
```

可选检索能力实现：

```python
from memory_benchmark.core import Question, RetrievalResult
from memory_benchmark.core.interfaces import BaseMemoryRetriever


class MyRetriever(BaseMemoryRetriever):
    def retrieve(self, question: Question) -> RetrievalResult:
        ...
```

Phase 1 的 LoCoMo 和 LongMemEval 不要求检索接口，也不计算检索召回指标。`top_k` 这类参数属于 method 自身配置，不放进统一接口参数。

method 分为：

- `end_to_end`：method 自行生成答案。
- `memory_module`：原始模块负责写入和检索，框架使用统一 fixed-reader wrapper 生成答案。

固定 reader 的模型、prompt、参数和版本由框架统一管理，避免把 reader 差异误认为 memory
能力差异。纯 memory module 不需要伪造自己的 `get_answer()`；wrapper 会把它组合成
通用 runner 可调用的完整回答系统。

官方内置 method 同时支持 CLI 和 Python API。自定义 method 当前实现统一接口后，通过
Python API 传入已经创建的实例；CLI 插件自动发现暂不实现。

## 指标范围

当前只评估 answer 质量：

- LoCoMo: token F1，可选 LLM judge accuracy。
- LongMemEval: LLM judge accuracy。

当前不做：

- 检索召回类指标。
- adversarial 单独评测。
- 异步 runner。

当前效率 observation 底座已经实现，运行时保存原始 token、调用、延迟、模型身份和
计量来源；真实费用必须在实验结束后按实际 API 服务商价格离线计算。效率评测优先覆盖
三项：

1. `Retrieval Latency`：检索 embedding、搜索、过滤和重排的时间，不含最终回答生成。
2. `Memory Context Tokens`：真正注入回答 LLM 的记忆上下文 token。
3. `Memory Update Cost`：更新延迟、LLM input/output tokens、embedding input tokens。

prediction 阶段逐操作保存原始 observation，evaluate 阶段再计算总量、均值、P50 和
P95。method 不支持某项观测时明确报错或标记 `unsupported`，不能估算冒充实测。

## 统一命令行入口

项目提供两个等价入口：

```bash
uv run memory-benchmark --help
uv run python -m memory_benchmark --help
```

统一入口包含三个子命令：

- `predict`：只运行 method 并保存回答，不计算指标。
- `evaluate`：只读取已有标准 artifacts 计算指标，不重新运行 method。
- `run`：先生成回答，再对本次 run 执行指定指标。

正式架构以可独立恢复的 `predict` 和 `evaluate` 为基础；`run` 只是便利组合，不复制
prediction 或 evaluation 逻辑。

当前统一入口已经开放 **LoCoMo** 和 **LongMemEval** prediction；已注册的 Mem0、
MemoryOS、A-Mem 与 LightMem 都通过同一套 method capability 契约接入。A-Mem 与
LightMem 目前已通过离线/fake registered smoke。真实 API smoke 前先核对
[docs/method-resource-parameter-audit.md](/Users/wz/Desktop/memoryBenchmark/docs/method-resource-parameter-audit.md)；
LightMem 所需本地 `all-MiniLM-L6-v2` 和 LLMLingua2 模型已放在 `models/`。旧
MemoryOS 直跑入口只保留给历史复现，不再作为新实验默认路径。

两个容易混淆的参数必须分开理解：

- `--profile`：选择 method 运行配置，例如 `smoke` 或 `official-full`。
- `--variant`：选择 benchmark 数据版本。LoCoMo 当前只有 `locomo10`；
  LongMemEval 支持 `s_cleaned`、`m_cleaned` 和命令层 selector `all`。

LongMemEval 默认使用较小的 `s_cleaned`。`--variant all` 不会合并两份数据，而是按固定
顺序创建两个独立 child run；每个 child 都有自己的 manifest、method state、checkpoint、
prediction 和 metric。用户基础 run ID `exp1` 会展开为 `exp1-s-cleaned` 与
`exp1-m-cleaned`，框架不会跨 variant 计算一个混合平均值。

小量 Mem0 smoke 示例：

```bash
uv run memory-benchmark predict \
  --method mem0 \
  --benchmark locomo \
  --profile smoke \
  --run-id mem0-locomo-smoke \
  --confirm-api \
  --smoke-turn-limit 20
```

Mem0 official-full 会产生大量真实 API 调用，必须同时提供两次成本确认：

```bash
uv run memory-benchmark predict \
  --method mem0 \
  --benchmark locomo \
  --profile official-full \
  --run-id mem0-locomo-full-YYYYMMDD \
  --confirm-api \
  --confirm-full
```

已有回答可以独立计算 LoCoMo F1，不读取 `.env`，也不会再次调用 Mem0：

```bash
uv run memory-benchmark evaluate \
  --run-id mem0-locomo-full-YYYYMMDD \
  --metric locomo-f1
```

同一份回答可以继续增加 LLM judge；只有 judge 需要 API 确认：

```bash
uv run memory-benchmark evaluate \
  --run-id mem0-locomo-full-YYYYMMDD \
  --metric locomo-f1 \
  --metric locomo-judge \
  --judge-profile compact \
  --confirm-api
```

一次完成 prediction 和 evaluation：

```bash
uv run memory-benchmark run \
  --method mem0 \
  --benchmark locomo \
  --profile smoke \
  --metric locomo-f1 \
  --run-id mem0-locomo-smoke \
  --confirm-api
```

MemoryOS 的新实验也支持同一套统一入口：

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

MemoryOS `official-full` 和 Mem0 一样会触发大量真实 API 调用，因此也需要
`--confirm-api` 和 `--confirm-full`。MemoryOS 目前仍按 conversation 级串行执行；旧的
`outputs/memoryos-locomo-full-20260603/` 只用于历史复现，不会自动迁入新的 resume。

LongMemEval-S 的最小 smoke 会保留所选 instance 的完整 sessions/turns，只限制为一个
evaluation instance，不使用 LoCoMo 专属的 turn 裁剪：

```bash
uv run memory-benchmark predict \
  --method mem0 \
  --benchmark longmemeval \
  --profile smoke \
  --variant s_cleaned \
  --run-id mem0-longmemeval-smoke \
  --confirm-api
```

prediction 完成后，可以单独运行 LongMemEval 官方范式的 LLM judge，不重新调用 method：

```bash
uv run memory-benchmark evaluate \
  --run-id mem0-longmemeval-smoke-s-cleaned \
  --metric longmemeval-judge \
  --judge-profile compact \
  --confirm-api
```

需要显式运行两个数据版本时使用：

```bash
uv run memory-benchmark predict \
  --method mem0 \
  --benchmark longmemeval \
  --profile smoke \
  --variant all \
  --run-id mem0-longmemeval-smoke \
  --confirm-api
```

该命令依次创建 `mem0-longmemeval-smoke-s-cleaned` 和
`mem0-longmemeval-smoke-m-cleaned`。正式实验仍建议先独立执行可恢复的 `predict`，再对
每个 child run 使用 `evaluate`；`run` 只是这两步的便利组合。

## 日志结构

开发日志和运行日志分开：

- `docs/handoffs/`: 上下文压缩或额度中断前的交接文件。
- `docs/logs/`: 开发过程中的主题日志，命名规则见 [docs/logs/README.md](docs/logs/README.md)。
- `outputs/<run_id>/logs/run.log`: 单次运行的人类可读日志。
- `outputs/<run_id>/logs/events.jsonl`: 单次运行的结构化事件日志。

运行期日志通过 `memory_benchmark.utils.run_logger.RunLogger` 写入，终端展示使用 `rich`。

## 实验输出结构

长实验的标准输出位于 `outputs/<run_id>/`：

```text
outputs/<run_id>/
  manifest.json
  config.redacted.json
  artifacts/
    dataset_fingerprint.json
    public_questions.jsonl
    method_predictions.jsonl
    evaluator_private_labels.jsonl
    answer_scores.locomo_f1.jsonl
  logs/
    run.log
    events.jsonl
  checkpoints/
    conversation_status.json
    progress.json
  method_state/
  summaries/
    summary.json
```

重要文件：

- `manifest.json`：记录公开运行元数据、配置形状和输出根目录。
- `config.redacted.json`：保存脱敏后的运行配置，不包含 secret。
- `artifacts/dataset_fingerprint.json`：记录完整规范化 `Dataset` 内容哈希、数据来源哈希和 conversation/question 数量。
- `artifacts/public_questions.jsonl`：保存 method 可见的公开问题，不含 gold answer 等私有字段。
- `artifacts/method_predictions.jsonl`：保存 method 回答，供后续复算和新增 evaluator 使用。
- `artifacts/evaluator_private_labels.jsonl`：保存 evaluator-only 的标准答案和私有标签，绝不能传给 method。
- `artifacts/answer_scores.locomo_f1.jsonl`：保存逐题 LoCoMo F1 明细；其他 evaluator 应写独立 score artifact。
- `logs/run.log`：面向人工排查的运行日志。
- `logs/events.jsonl`：append-only 结构化事件；同一 `run_id` 多次 resume 时用 `attempt_id` 区分每次尝试。
- `checkpoints/conversation_status.json`：保存 conversation 级断点状态。
- `checkpoints/progress.json`：保存最近进度快照；即使关闭 Rich 终端展示也会继续写入。
- `method_state/`：隔离 method 自身的持久化状态。
- `summaries/summary.json`：保存聚合结果和标准 artifact 路径。

已有 `method_predictions.jsonl` 和 `evaluator_private_labels.jsonl` 时，可以新增或重算 evaluator，而无需再次调用 method。根目录兼容 alias 只由旧 MemoryOS legacy runner 维护：`predictions.jsonl`、`scores.jsonl`、`summary.json`、`conversation_status.json`。统一 `predict/evaluate/run` 的新 generic run 只写 canonical artifacts 和 checkpoints，不再依赖这些 alias。

`resume=True` 只会复用 fingerprint 与当前完整 `Dataset`、运行形状和 method 配置一致的状态。已有 prediction、score、checkpoint、question artifact 或 method state 却缺少兼容 fingerprint 时，runner 会明确报错，不会猜测旧状态可用；旧实验若需继续运行，应通过后续显式迁移工具处理。

append-only prediction/score JSONL 如果因进程崩溃留下“无行终止符的损坏尾行”，runner 会在 canonical/legacy alias 对账时显式丢弃该半行，并用两侧仍然完整的记录原子修复 alias。中间坏行、已带行终止符的坏尾行和非对象 JSON 仍会报错，避免把一般数据损坏误判成可恢复中断。

## 配置层

配置分层组合，避免把 secret、官方实验参数和单次运行选项混在一起，也不创建
method × benchmark 的配置文件笛卡尔积。

### Secret 与服务地址

项目使用 `python-dotenv` 读取根目录 `.env`：

```text
OPENAI_KEY=<本地私有 API key>
BASE_URL=https://api.openai.com/v1
```

`.env` 只保存 secret 和服务地址，不应提交，也不能进入 manifest 或日志。离线 evaluator
不会读取 OpenAI 配置。

```python
from openai import OpenAI
from memory_benchmark.config import load_openai_settings

settings = load_openai_settings()
client = OpenAI(**settings.to_client_kwargs())
```

### 实验 profile

可审计、可复用的 method/evaluator 参数放在 TOML：

```text
configs/
  methods/
  datasets/     # 后续增加，用于按数据集组织配置
  runners/      # 后续增加
  evaluators/
  examples/     # 带详细注释的完整使用示例
```

TOML 读取后必须转换为 owner 模块的强类型 dataclass 并执行字段校验。面向用户的配置
示例必须逐项写清字段意义、默认值和影响，便于实验使用和调试。

Profile 在架构上分为：

- `official`：经过验证的官方/论文复现配置类别，具体 profile 可以命名为
  `official-full` 等；关键参数不可临时覆盖。
- `smoke`：低成本真实链路测试。smoke 也使用官方 method 参数，成本控制只通过
  conversation/question/turn 规模裁剪。
- `custom`：允许用户进行消融和参数调整。

### 单次运行参数

解析优先级：

```text
代码安全默认值
< 命名 profile
< 用户实验 TOML
< 少量 CLI 显式覆盖
```

CLI 只保留高频选项；参数较多时使用带注释的实验 TOML。运行前保存脱敏后的最终 resolved
config。secret 只能来自 `.env` 或环境变量。

## 实验不可变性

一个 `run_id` 首次创建后，benchmark、数据指纹、method、源码身份、reader 和关键配置
不可改变。`--resume` 只能继续完全兼容的实验；配置变化必须使用新 `run_id`。

`evaluate` 可以为同一 prediction 增加 metric，但不能修改原 prediction。未来重算已有
metric 时必须显式 `--force`，并记录 evaluator 版本和配置。

## 发布方向

近期使用 GitHub + `uv`：

- 第一方框架位于 `src/`。
- 项目提供许可证允许再分发、经过验证并固定版本的 method 源码。
- benchmark 大型数据不进入 Python 安装包，adapter 使用默认路径并允许用户覆盖。

成熟后再发布 PyPI 核心包和 CLI，并评估 benchmark install/register/verify。排行榜网站、
数据库和结果上传只保留扩展边界，当前不实现。

## 验证命令

使用 `uv` 运行测试：

```bash
uv run pytest
uv run pytest -m unit
uv run pytest -m "integration and not api"
uv run pytest -m memoryos
uv run pytest -m api
```

默认 `uv run pytest` 只会运行 `tests/` 下的测试，并通过默认 marker 排除 `api`，不会调用真实外部 API。需要真实 API smoke 时，显式使用 `-m api`。
不要把 `unittest discover` 作为默认入口，因为 unittest 不识别 pytest marker，会连同真实
API smoke 一起执行。需要验证 unittest 兼容性时，应显式列出不含 API smoke 的测试模块。

Phase 1 focused suite：

```bash
uv run python -m unittest \
  tests/test_core_conversation_entities.py \
  tests/test_conversation_dataset_validation.py \
  tests/test_locomo_conversation_adapter.py \
  tests/test_longmemeval_conversation_adapter.py \
  tests/test_conversation_runner.py \
  tests/test_locomo_answer_metrics.py \
  tests/test_llm_judge_parsing.py \
  tests/test_run_logger.py \
  -v
```

adapter dry-run：

```bash
uv run python -m memory_benchmark.cli.dry_run --benchmark all --limit 1
```

MemoryOS-LoCoMo legacy smoke：

这段只用于历史 MemoryOS smoke 复现；新实验请使用上面的统一 `predict/evaluate/run`。

```python
from pathlib import Path
from memory_benchmark.runners.memoryos_locomo_smoke import run_memoryos_locomo_smoke

# 默认只估算 LoCoMo 第一条样本在论文默认配置下的 add 成本，不实例化 MemoryOS。
estimate = run_memoryos_locomo_smoke(project_root=Path.cwd())

# safe add-only 会把 STM capacity 调到大于 page 数，只验证真实写入链路，不触发 MemoryOS 更新。
add_only = run_memoryos_locomo_smoke(project_root=Path.cwd(), mode="add-only")
```

LoCoMo 第一条样本 `conv-26` 会转成 214 个 MemoryOS page。论文默认
`short_term_capacity=7` 时，官方队列行为会触发约 208 批 MemoryOS 更新；不要在未
确认成本前直接跑 paper-default add 或完整 QA。

OpenAI 配置 smoke test：

```bash
uv run python -m unittest tests/test_API.py -v
```

该测试会读取 `.env` 并发起一次最小 API 调用，不会打印 API key。

## 开发约定

- Python 文件顶端必须有中文模块说明。
- 类、函数、测试函数必须有中文 docstring，解释输入、输出和关键字段。
- 新增 benchmark 时先识别 task family；当前只有 `conversation_qa` 可用。
- 新增字段优先放到 `metadata`，只有跨 benchmark 稳定复用时才升格为核心字段。
- 缺 required 字段、question/gold 不对齐、私有字段泄漏都应抛项目领域异常。
- 任何实质性架构变化都先和用户讨论再执行。
