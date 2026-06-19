# AgentMemoryBench

AgentMemoryBench 是一个面向 Agent Memory 方法的可复现、可扩展、可审计评测框架。
它把不同 benchmark 的原始数据统一成可校验的数据模型，调用 memory method 生成回答，
再把 prediction、运行观测和 evaluator 结果保存为可复算的标准实验产物。

GitHub 仓库：[buctzzp/AgentMemoryBench](https://github.com/buctzzp/AgentMemoryBench)

当前第一优先用户是希望低门槛运行官方集成的实验使用者；第二类用户是希望把新 memory
method 接入统一 benchmark 的研究者。

## 当前状态

当前主线只实现 **conversation + QA** task family：

```text
conversation history -> question -> answer-level score
```

Phase 1 只跑纯文本闭环，先以 LoCoMo 打通各个 method，再接入 LongMemEval。多模态字段
已在 core 中保留，但当前阶段不主动运行多模态 benchmark。

已接入或正在验证的范围：

| 类型 | 当前状态 |
| --- | --- |
| Benchmark | LoCoMo、LongMemEval S/M |
| Method | Mem0、MemoryOS、A-Mem、LightMem |
| 质量指标 | LoCoMo token F1、LoCoMo LLM judge、LongMemEval LLM judge |
| 效率观测 | token、latency、model identity、memory context tokens 等原始 observation |
| 暂缓 | HaluMem、MemBench、Mem-Gallery |
| 已移除 | PrefEval，不恢复 adapter、测试、文档或原始仓库 |

真实 API prediction、LLM judge 或 full profile 实验必须由用户显式确认 method、benchmark、
样本规模和 `run_id`。框架不会在普通测试或默认命令里自动发起付费调用。

最新任务状态以 [AGENTS.md](AGENTS.md) 和 [docs/current-roadmap.md](docs/current-roadmap.md)
为准。长期架构设计见
[项目目标与架构设计](docs/superpowers/specs/2026-06-12-project-goals-architecture-design.md)。

## 快速开始

安装依赖：

```bash
uv sync
```

配置 API。根目录 `.env` 只保存 secret 和服务地址，不提交到 Git：

```text
OPENAI_KEY=<your-api-key>
BASE_URL=https://api.openai.com/v1
```

查看 CLI：

```bash
uv run memory-benchmark --help
uv run python -m memory_benchmark --help
```

运行离线验证，不会调用真实外部 API：

```bash
uv run pytest tests/test_documentation_standards.py tests/test_method_official_smoke_profiles.py -q
uv run python -m compileall -q src/memory_benchmark tests
```

更完整的本地回归：

```bash
uv run pytest -q
uv run pytest -m api --collect-only -q
```

默认 `pytest` 通过 marker 排除 `api`，不会触发真实 API。需要真实 API smoke 时，必须显式
使用 `-m api` 或 CLI 的 `--confirm-api`。

## 本地资产

大型数据、模型和实验输出不进入 Git，也不会塞进 Python 安装包。当前 `.gitignore` 保护：

- `data/`
- `models/`
- `outputs/`
- `third_party/benchmarks/`
- `paper-make/`
- `.env`

本地运行时约定：

```text
data/                    # adapter 读取的 canonical runtime dataset
models/                  # 本地 embedding / compressor / NLP 模型资源
outputs/<run_id>/        # prediction、evaluation、日志、checkpoint 和 method state
third_party/benchmarks/  # 官方 benchmark 仓库，只用于事实核验和源码参考
third_party/methods/     # 项目提供并固定版本的第三方 method 源码
```

LightMem 当前需要本地模型：

- `models/all-MiniLM-L6-v2`
- `models/llmlingua-2-bert-base-multilingual-cased-meetingbank`

method 资源和官方参数核对见
[docs/method-resource-parameter-audit.md](docs/method-resource-parameter-audit.md)。
当前 public Hugging Face 数据仓库为
[BuptZZP/agentmemorybench-data](https://huggingface.co/datasets/BuptZZP/agentmemorybench-data)，
准备和上传流程见
[docs/huggingface-datasets.md](docs/huggingface-datasets.md)。

## 项目层次

```text
src/
  memory_benchmark/
    config/               # .env、路径、profile 和服务配置读取
    core/                 # 数据实体、抽象接口、校验、领域异常、结果摘要
    benchmark_adapters/   # 原始 dataset -> 统一 Dataset
    evaluators/           # answer-level 指标和 LLM judge
    runners/              # prediction/evaluation/run 编排
    methods/              # method wrapper、profile 装配和能力声明
    observability/        # Rich 进度、事件日志和效率 observation
    storage/              # 标准实验目录、JSONL、fingerprint 和 artifact 工具
    utils/                # logger 与通用工具
    cli/                  # 统一命令行入口
tests/                    # pytest 测试和可维护性约定测试
configs/                  # method/evaluator TOML profile
docs/                     # 当前设计、计划、资源审计、交接文档
third_party/methods/      # vendored method 源码
```

核心分层原则：

- `core/` 不读取数据、不调用模型、不计算指标，只定义公共语言。
- `benchmark_adapters/` 只做 schema 转换和强校验，不调用 method。
- `runners/` 只向 method 传公开对象，不能传 gold answer、evidence 或 judge label。
- `evaluators/` 才能读取 `GoldAnswerInfo` 等 evaluator-only 私有信息。
- `methods/` 用 wrapper 隔离第三方源码，runner 不直接依赖第三方内部类。
- `registry` 只保存名称、静态能力和 factory，不保存 secret 或运行实例。

数据结构参考与评测流程参考位于：

- [docs/dataset_structures/](docs/dataset_structures/)
- [docs/evaluation_workflows/](docs/evaluation_workflows/)

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

公开/私有边界是硬约束：

- `Conversation` 和 `Question` 是 method 可见输入。
- `GoldAnswerInfo` 只给 evaluator 和审计日志使用。
- gold answer、evidence id、judge label、私有 metadata 不能进入 method。
- runner 会重建 public 对象，避免 dataclass 动态属性泄漏。

## 数据模型

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
- `ImageRef`: 后续多模态扩展字段，Phase 1 不主动处理图片。

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

接口约束：

- 依靠 `conversation_id` 做记忆隔离，不提供 reset 接口。
- `add()` 接收 `list[Conversation]`，不设计 `add(session)` 或强制 turn-only 接口。
- `get_answer()` 只接收 `Question`，不能接收标准答案、检索结果或 top-k。
- `retrieve()` 是可选能力；LoCoMo / LongMemEval 的 Phase 1 质量评测不要求它。
- `top_k`、reader 模型、embedding 模型等参数属于 method profile，不放进统一接口参数。

method 分为：

- `end_to_end`：method 自行写入记忆并生成答案。
- `memory_module`：原始模块负责写入和检索，由框架 fixed-reader wrapper 组合成完整回答系统。

自定义 method 当前通过 Python API 传入实现接口的实例；CLI 只运行官方集成。详细规则见
[docs/method-interface.md](docs/method-interface.md)。

## 统一命令行入口

统一入口包含三个子命令：

- `predict`：只运行 method 并保存回答，不计算指标。
- `evaluate`：只读取已有 artifacts 计算指标，不重新运行 method。
- `run`：先 prediction，再 evaluation，是前两步的便利组合。

正式实验建议优先使用可独立恢复的 `predict` 和 `evaluate`。`run` 不复制业务逻辑。

LoCoMo 小量真实链路示例：

```bash
uv run memory-benchmark predict \
  --method mem0 \
  --benchmark locomo \
  --profile smoke \
  --run-id mem0-locomo-smoke \
  --confirm-api \
  --smoke-turn-limit 20
```

已有回答可以离线计算 LoCoMo F1，不读取 `.env`，也不会再次调用 method：

```bash
uv run memory-benchmark evaluate \
  --run-id mem0-locomo-smoke \
  --metric locomo-f1
```

同一份回答可以继续增加 LLM judge；只有 judge 本身需要 API 确认：

```bash
uv run memory-benchmark evaluate \
  --run-id mem0-locomo-smoke \
  --metric locomo-judge \
  --judge-profile compact \
  --confirm-api
```

LongMemEval-S 小量示例：

```bash
uv run memory-benchmark predict \
  --method mem0 \
  --benchmark longmemeval \
  --profile smoke \
  --variant s_cleaned \
  --run-id mem0-longmemeval-smoke \
  --confirm-api
```

LongMemEval 支持 `s_cleaned`、`m_cleaned` 和命令层 selector `all`。`--variant all` 不会把
S/M 合并成一个 dataset，而是创建独立 child run，保证 resume、指标比较和排行榜口径清晰。

full profile 会产生大量真实 API 调用，必须额外提供 `--confirm-full`：

```bash
uv run memory-benchmark predict \
  --method mem0 \
  --benchmark locomo \
  --profile official-full \
  --run-id mem0-locomo-full-YYYYMMDD \
  --confirm-api \
  --confirm-full
```

分批续跑选项：

```bash
uv run memory-benchmark predict \
  --method mem0 \
  --benchmark locomo \
  --profile official-full \
  --run-id mem0-locomo-full-YYYYMMDD \
  --confirm-api \
  --confirm-full \
  --max-new-conversations 2
```

`--max-new-conversations` 的语义是“本次命令最多推进 N 个尚未完成的 conversation”。
它是运行预算，不是实验 identity；同一个 `run_id` 后续可以用不同预算继续 `--resume`。
该选项已接入 `predict` / `run` / `calibrate-smoke`，用于把长实验拆成多次可恢复的小批次。

## 配置

配置分层组合，避免把 secret、官方参数和单次运行选项混在一起。

```text
代码安全默认值
< 命名 profile
< 用户实验 TOML
< 少量 CLI 显式覆盖
```

TOML profile 位于：

```text
configs/
  methods/
    mem0.toml
    memoryos.toml
    amem.toml
    lightmem.toml
  evaluators/
    llm_judge.toml
```

profile 类型：

- `official` / `official-full`：官方或论文复现配置，关键参数不可临时覆盖。
- `smoke`：低成本真实链路测试；smoke 也使用官方 method 参数，成本只通过数据规模裁剪。
- `custom`：允许用户进行消融和参数调整。

用户配置采用分层 TOML，不为每个 method × benchmark 创建配置文件笛卡尔积。

## 实验输出

长实验输出位于 `outputs/<run_id>/`：

```text
outputs/<run_id>/
  manifest.json
  config.redacted.json
  artifacts/
    dataset_fingerprint.json
    public_questions.jsonl
    method_predictions.jsonl
    evaluator_private_labels.jsonl
    answer_scores.<metric>.jsonl
    efficiency_observations.jsonl
  logs/
    run.log
    events.jsonl
  checkpoints/
    progress.json
    conversation_status.json
  method_state/
  summaries/
    summary.json
```

关键规则：

- `run_id` 对应不可变实验；resume 只能继续数据、method、reader、源码身份和关键配置一致的运行。
- `method_predictions.jsonl` 可以被多个 evaluator 复用，不需要重复调用 method。
- `method_predictions.jsonl` 应保持轻量：大段 system prompt、reader prompt、injected
  context 或重复 metadata 应按 run/conversation 单独记录一次，再在逐题 prediction 中引用。
- `evaluator_private_labels.jsonl` 只给 evaluator 使用，不能传给 method。
- `config.redacted.json` 只保存脱敏配置，不包含 secret。
- `logs/run.log` 面向人工排查；`logs/events.jsonl` 是结构化事件日志。
- 第三方 method 的 stdout/warning 不应直接打乱终端 Rich 进度；wrapper 应捕获、重定向到
  日志或按配置静默。
- 如果 question 带 `category`，evaluator summary 应同时输出 overall 和 by-category
  聚合；这不是某个 benchmark 的特例。

## 指标与效率观测

当前只评估 answer 质量：

- LoCoMo: token F1，可选 LLM judge accuracy。
- LongMemEval: LLM judge accuracy。

当前不做 retrieval recall，也不把 adversarial 作为独立主线。

效率 observation 在 prediction 阶段逐操作保存原始数据，后续离线聚合。当前优先关注：

1. `Retrieval Latency`：检索 embedding、搜索、过滤、重排耗时，不含最终回答生成。
2. `Memory Context Tokens`：真正注入回答 LLM prompt 的记忆上下文 token。
3. `Memory Update Cost`：记忆写入延迟、LLM input/output tokens、embedding input tokens。

真实费用不绑定 OpenAI 官方价格。实验结束后按实际 API 服务商价格离线计算；本地模型成本
保留为零成本或仅记录 token/latency。

## 日志结构

开发日志和运行日志分开：

- `docs/handoffs/`: 上下文压缩或额度中断前的交接文件。
- `docs/logs/`: 开发过程中的主题日志，命名规则见 [docs/logs/README.md](docs/logs/README.md)。
- `outputs/<run_id>/logs/run.log`: 单次运行的人类可读日志。
- `outputs/<run_id>/logs/events.jsonl`: 单次运行的结构化事件日志。

运行期日志通过统一 logger / observability 工具写入，终端展示使用 `rich`。

## 验证命令

常用命令：

```bash
uv run pytest --collect-only -q
uv run pytest -q
uv run pytest -m memoryos -q
uv run pytest -m api --collect-only -q
uv run python -m compileall -q src/memory_benchmark tests
```

文档和 official smoke profile 的快速检查：

```bash
uv run pytest tests/test_documentation_standards.py tests/test_method_official_smoke_profiles.py -q
```

adapter dry-run：

```bash
uv run python -m memory_benchmark.cli.dry_run --benchmark all --limit 1
```

OpenAI 配置最小 smoke test 会真实调用 API，只在需要时运行：

```bash
uv run python -m unittest tests/test_API.py -v
```

## 开发约定

- 使用 `uv` 管理和运行 Python。
- Python 文件顶端必须有中文模块说明。
- 类、函数、测试函数必须有中文 docstring，解释输入、输出和关键字段。
- 新增 benchmark 时先识别 task family；当前只有 `conversation_qa` 主线。
- 新增字段优先放到 `metadata`，只有跨 benchmark 稳定复用时才升格为核心字段。
- 缺 required 字段、question/gold 不对齐、私有字段泄漏都应抛项目领域异常。
- 任何实质性架构变化都先和用户讨论再执行。
- 禁止修改第三方核心算法；必要观测优先通过 wrapper 或可关闭 observer 实现。

## 参考文档

- [AGENTS.md](AGENTS.md): 当前项目入口、断点和最高优先级工程规则。
- [docs/current-roadmap.md](docs/current-roadmap.md): 动态路线图。
- [docs/benchmark-scope.md](docs/benchmark-scope.md): benchmark 范围。
- [docs/method-interface.md](docs/method-interface.md): method 接口。
- [docs/data-model.md](docs/data-model.md): core 数据模型说明。
- [docs/method-resource-parameter-audit.md](docs/method-resource-parameter-audit.md): method 参数与资源审计。
- [docs/huggingface-datasets.md](docs/huggingface-datasets.md): dataset 上传到 Hugging Face 的流程。
- [docs/superpowers/specs/2026-06-12-project-goals-architecture-design.md](docs/superpowers/specs/2026-06-12-project-goals-architecture-design.md): 长期项目目标与架构设计。
