# AgentMemoryBench

AgentMemoryBench 是一个面向 Agent Memory 方法的可复现、可扩展、可审计评测框架。
它把不同 benchmark 的原始数据统一成可校验的数据模型，调用 memory method 写入和检索
记忆，由 framework reader 生成回答，再把 prediction、运行观测和 evaluator 结果保存为
可复算的标准实验产物。

GitHub 仓库：[zzp-elio/AgentMemoryBench](https://github.com/zzp-elio/AgentMemoryBench)

当前第一优先用户是希望低门槛运行官方集成的实验使用者；第二类用户是希望把新 memory
method 接入统一 benchmark 的研究者。

## 当前状态

当前主线只实现 **conversation + QA** task family：

```text
conversation history -> question -> answer-level score
```

### Phase 1 目标与进展（2026-07-07）

Phase 1 范围已于 2026-07-04 锁定：**5 个 benchmark × 10 个 method**，里程碑 2026-07-20。
多模态字段已在 core 中保留，但当前阶段不主动运行多模态 benchmark。

Phase 1 的**交付物是 5×10 smoke 矩阵**（每格极小规模真实测试 + 成本 observation），
不是全量实验。全量实验在预算获批后另启。

**已完成**：

- **协议**：v3 provider 协议（`ingest + retrieve`）已批准并全链路落地（M-A/M-B 验收通过），
  全量回归基线 **802 passed**。协议全文：
  [spec-protocol-v3.md](docs/workstreams/ws02-phase1-matrix/spec-protocol-v3.md)
- **Benchmark adapter（2/5）**：LoCoMo、LongMemEval S/M
- **Method adapter（4/10，均已按 retrieve-first 接入）**：Mem0、MemoryOS、A-Mem、LightMem
- **效率观测**：token、latency、model identity、memory context tokens 等原始 observation
- **CLI v2**：`predict smoke/formal` + `evaluate` + `run`；conversation 级并行/resume

**进行中**：

- MemBench adapter（[ws02.1](docs/workstreams/ws02.1-membench/README.md)）— 架构师验收通过，
  本项目第一条 unified prompt 链路 + 第一个零成本 evaluator 落地
- SimpleMem adapter（[ws02.4](docs/workstreams/ws02.4-simplemem/README.md)）— T1 完成，T2-T6 待施工

**缺口**：3 个新 benchmark adapter（HaluMem、BEAM 的 spec 待架构师起草）、
6 个新 method adapter（LangMem、Supermemory、MemOS、Cognee、Letta、SimpleMem 剩余）。
推进顺序与策略见 [路线图](docs/roadmap.md) 与
[架构师手册 §9.6](docs/reference/architect-playbook.md#96-全局规划原理防漂移北极星2026-07-07-与用户对齐)。

### 已实现基线详情

| 类型 | 当前状态 |
| --- | --- |
| Phase 1 目标 Benchmark | LoCoMo、LongMemEval、HaluMem、BEAM、MemBench |
| Phase 1 目标 Method | A-Mem、MemoryOS、MemOS、LightMem、SimpleMem、Mem0、Letta/MemGPT、Cognee、LangMem、Supermemory |
| 已接入 Benchmark | LoCoMo、LongMemEval S/M |
| 已接入 Method | Mem0、MemoryOS、A-Mem、LightMem |
| 质量指标 | LoCoMo token F1、LoCoMo LLM judge、LongMemEval LLM judge |
| 效率观测 | token、latency、model identity、memory context tokens |
| Supermemory 口径 | 纳入 Phase 1，仅 self-host/local OSS；不用 Enterprise/full platform |
| Phase 1 排除 | Zep、Graphiti（属 Zep 体系） |
| 已移除 | PrefEval（不恢复 adapter、测试、文档或原始仓库） |

### 关键约束

- **预算强约束**：全量实验必须先有成本估算表并经导师批准；当前一切真实 run 均为极小
  smoke。真实 API 调用须用户显式确认 method、benchmark、样本规模和 `run_id`。
- 当前所有真实 LLM 调用统一 `gpt-4o-mini`；未经用户改口不得切换模型。
- 真实费用按 ohmygpt 实际价格离线计算，不绑定 OpenAI 官方价。
- smoke 使用官方 method 参数；成本控制只通过数据规模裁剪。
- `outputs/memoryos-locomo-full-20260603/` 是受保护实验资产。

最新任务状态以 [AGENTS.md](AGENTS.md)、[docs/roadmap.md](docs/roadmap.md) 和各
[workstream README](docs/workstreams/) 为准。

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
data/                            # adapter 读取的 canonical runtime dataset
models/                          # 本地 embedding / compressor / NLP 模型资源
outputs/<run_id>/                # legacy run 输出目录
outputs/runs/{method}/...        # CLI v2 分层 run 输出目录
third_party/benchmarks/          # 官方 benchmark 仓库，只用于事实核验和源码参考
third_party/methods/             # 项目提供并固定版本的第三方 method 源码
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

- [docs/survey/datasets/](docs/survey/datasets/)
- [docs/survey/workflows/](docs/survey/workflows/)

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
  method.add(public Conversation)
  method.retrieve(public Question) -> AnswerPromptResult.prompt_messages
  framework answer LLM(prompt_messages)
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

当前主协议为 **v3 `MemoryProvider`**（`ingest(unit) + retrieve(query) -> RetrievalResult`），
粒度由实例级 `consume_granularity` 声明、框架事件流聚合投递。协议全文：
[docs/workstreams/ws02-phase1-matrix/spec-protocol-v3.md](docs/workstreams/ws02-phase1-matrix/spec-protocol-v3.md)。

五个内置 method adapter（Mem0、MemoryOS、A-Mem、LightMem、SimpleMem）均已原生
实现 v3 `MemoryProvider`（M-B 原生化于 2026-07-06 验收通过），registered 主路径
不经过桥接；`LegacyProviderBridge` 仅服务 `--method-class` 自定义旧式 provider
（`add + retrieve` 的 v2 形态）。新 method 接入应直接实现 v3 `MemoryProvider`。

```python
from memory_benchmark.core import (
    AddResult,
    AnswerPromptResult,
    Conversation,
    PromptMessage,
    Question,
)


class MyMemoryProvider:
    def add(self, conversation: Conversation) -> AddResult:
        ...

    def retrieve(self, question: Question) -> AnswerPromptResult:
        return AnswerPromptResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            prompt_messages=[
                PromptMessage(role="system", content="You are a helpful assistant."),
                PromptMessage(role="user", content="...method-owned prompt..."),
            ],
            metadata={"answer_context": "...optional debuggable memory text..."},
        )
```

`AnswerPromptResult.prompt_messages` 是核心输出。它表示 method 内部已经完成 query
rewrite、检索、rerank、merge、格式化和 answer prompt 构造，且保留官方 system/user
role 结构。framework answer LLM 会直接使用这些 messages 生成最终答案。
`AnswerPromptResult.answer_prompt` 只是兼容 artifact、日志和 token 估算的文本视图；
如果未显式传入，会由 `prompt_messages` 自动生成。method 需要保留的调试信息、拆出的
纯记忆上下文、原始检索项和 prompt profile 放进 `AnswerPromptResult.metadata`。

四个内置 method adapter（Mem0、A-Mem、LightMem、MemoryOS）都已新增 `retrieve()` 并
继承 `BaseMemoryProvider`。旧 `get_answer()` 暂时保留为兼容路径，主要用于历史复查和
尚未删除的 legacy 测试；新 method 接入不应再实现完整 answer system。

framework answer LLM 当前使用 `AnswerLLMSettings` 显式记录并传递 method × benchmark 的
官方 answer 参数，例如 temperature、max_tokens、top_p、message role、timeout 和 retry。
未在官方脚本中设置的字段保持 `None`，不会被框架猜默认值后传给 SDK。

answer LLM 和 judge LLM 后续会统一到 `LLMClient -> LLMResponse` 抽象，标准返回包含
文本、provider、model、usage、request id、finish reason、latency 和可选 debug raw
response。当前 registered prediction 已能在 method 声明 `MEMORY_RETRIEVAL` 时构造
OpenAI-compatible framework reader；完整多 provider 配置仍处于设计后续阶段，详见
[LLM Provider 与 Prompt 配置设计](docs/workstreams/ws03-architecture-slimming/2026-06-21-llm-provider-config-design.md)。

接口约束：

- 依靠 `conversation_id` 做记忆隔离，不提供 reset 接口。
- 新 `add()` 接收单个 `Conversation`；runner 负责循环、并行、resume 和失败隔离。
- `retrieve()` 只接收公开 `Question`，不能接收标准答案、evidence、top-k 或私有标签。
- `top_k`、reader 模型、embedding 模型等参数属于 method profile，不放进统一函数参数。
- 旧 `get_answer()` / `BaseMemorySystem` 路径只属于迁移期兼容；不要把它作为新 method
  接入接口。

自定义 method 现在也可以通过 CLI 轻量接入：传
`--method-class module:ClassName`，并让该类无参数构造且继承 `BaseMemoryProvider`。
该路径不要求用户写 AgentMemoryBench 的 TOML profile、不要求接入 source identity，也不
强制内部 LLM/embedding 观测。自定义 method 默认 `workers=1`；如果用户显式传
`--allow-unsafe-custom-parallel`，框架才允许 `workers>1`，并由用户自行保证外部数据库、
文件、namespace 和 conversation 隔离安全。手把手示例见
[docs/reference/custom-method-onboarding.md](docs/reference/custom-method-onboarding.md)。当前内置 method
原生接口审计见 [docs/reference/method-interface-inventory.md](docs/reference/method-interface-inventory.md)。

## 统一命令行入口

统一入口包含三个子命令：

- `predict`：只运行 method 并保存回答，不计算指标。
- `evaluate`：只读取已有 artifacts 计算指标，不重新运行 method。
- `run`：先 prediction，再 evaluation，是前两步的便利组合。

正式实验建议优先使用可独立恢复的 `predict` 和 `evaluate`。`run` 不复制业务逻辑。
`predict` / `run` 默认写出 prediction 阶段的 token、latency 和模型身份 observation；
只有临时调试时才建议显式传 `--disable-efficiency-observability` 关闭。
当前推荐使用 CLI v2：

- `predict smoke`：极小真实链路测试。允许裁剪 conversation、历史 round 和每个
  conversation 的问题数；不支持 `--resume` 或 `--retry-failed`。
- `predict formal`：正式 profile 运行。不能裁剪历史或问题；可用
  `--conversation-budget` 分批推进，并可用 `--resume` 继续同一个 `run_id`。
- `--allow-api` 是 `--confirm-api` 的直观别名；旧名称仍兼容。

这些预算参数语义都是上限：如果设置值大于当前 dataset / variant 的实际数量，框架按实际
可用数量运行；worker 数量也会由 runner 按实际 work item 做边界处理。

LoCoMo 小量真实链路示例：

```bash
uv run memory-benchmark predict smoke \
  --method mem0 \
  --benchmark locomo \
  --run-id mem0-locomo-smoke \
  --allow-api \
  --conversations 5 \
  --rounds 20 \
  --questions-per-conversation 2 \
  --workers 2
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
  --allow-api \
  --workers 4
```

LongMemEval-S 小量示例：

```bash
uv run memory-benchmark predict smoke \
  --method mem0 \
  --benchmark longmemeval \
  --variant s_cleaned \
  --run-id mem0-longmemeval-smoke \
  --allow-api \
  --conversations 1 \
  --rounds 20 \
  --questions-per-conversation 1
```

LongMemEval 支持 `s_cleaned`、`m_cleaned` 和命令层 selector `all`。`--variant all` 不会把
S/M 合并成一个 dataset，而是创建独立 child run，保证 resume、指标比较和排行榜口径清晰。

formal profile 会产生大量真实 API 调用；新入口只需要显式 `--allow-api`，并建议先用
`--conversation-budget` 分批推进：

```bash
uv run memory-benchmark predict formal \
  --method mem0 \
  --benchmark locomo \
  --run-id mem0-locomo-full-YYYYMMDD \
  --allow-api \
  --conversation-budget 2 \
  --workers 2
```

分批续跑选项：

```bash
uv run memory-benchmark predict formal \
  --method mem0 \
  --benchmark locomo \
  --run-id mem0-locomo-full-YYYYMMDD \
  --allow-api \
  --resume \
  --conversation-budget 2 \
  --workers 2
```

`--conversation-budget` 的语义是“本次命令最多推进 N 个尚未完成的 conversation”。
它是运行预算，不是实验 identity；同一个 `run_id` 后续可以用不同预算继续 `--resume`。
如果某个 conversation 已在 `checkpoints/conversation_status.json` 中标记为 `failed`，默认
`--resume` 不会再次处理它；确认资源和修复原因后，可用 `--retry-failed` 显式重试。

旧写法 `predict --profile smoke` / `predict --profile official-full` 仍保留兼容；新实验建议
优先使用 `predict smoke` / `predict formal`。
旧 CLI 不会立刻删除：等四个内置 method 的 LoCoMo/LongMemEval 新 CLI smoke 稳定后，
再为旧写法加 deprecated warning；至少完成一次 v2 formal 小规模 run 后，再从公开示例中
移除旧写法；对外发布前再决定是否彻底删除旧参数。

当前 prediction/full run 的并行边界是 conversation 级：单个 method × 单个 benchmark
内部可以用 worker 并行处理不同 conversation。多个 method 或多个 benchmark 同时跑实验时，
当前推荐开多个终端分别运行并使用不同 `run_id`；框架暂不把 method×benchmark 外层并行作为
full 实验主线。`calibrate-smoke` 只作为极小成本校准和批量 smoke 的便利入口。

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

CLI v2 新实验输出按 method、benchmark 和模式分层；legacy 命令和历史实验仍保留
`outputs/<run_id>/` 平铺布局。两种布局的 run 目录内部结构一致，`evaluate --run-id`
可以兼容读取；如果同名 `run_id` 同时出现在 legacy 和 v2 目录，或在 v2 目录中出现多处，
框架会报 ambiguity，要求换明确的 run id。

```text
outputs/runs/{method}/{benchmark}/{variant?}/{smoke|formal}/{run_id}/
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
    efficiency_overall.prediction.json
    efficiency_by_conversation.prediction.json
    efficiency_by_question.prediction.json
```

关键规则：

- `run_id` 对应不可变实验；resume 只能继续数据、method、reader、源码身份和关键配置一致的运行。
- `method_predictions.jsonl` 可以被多个 evaluator 复用，不需要重复调用 method。
- `method_predictions.jsonl` 应保持轻量：大段 system prompt、reader prompt、injected
  context 或重复 metadata 应按 run/conversation 单独记录一次，再在逐题 prediction 中引用。
- `evaluator_private_labels.jsonl` 只给 evaluator 使用，不能传给 method。
- `config.redacted.json` 只保存脱敏配置，不包含 secret。
- `logs/run.log` 面向人工排查；`logs/events.jsonl` 是结构化事件日志。
- `summaries/efficiency_*.prediction.json` 是从 raw observation 派生的人类可读聚合：
  overall、per-conversation 和 per-question 三个视图，方便估算单个 conversation 的 token、
  API call 和 latency；真实审计仍以 `artifacts/efficiency_observations.jsonl` 为准。
- 第三方 method 的 stdout/warning 不应直接打乱终端 Rich 进度；wrapper 应可靠写入
  `logs/run.log`/events，并用配置控制是否同步显示到终端，不应全局压掉用户 method 的
  调试输出。
- LightMem 可能输出 `LLM returned invalid source_id ... Auto-corrected`。这是 LightMem
  官方 memory build 中对 LLM 生成 source id 越界的自动修正 warning，当前不代表 run
  失败，但会污染终端，仍在 stdout/warning 治理待办中。
- 本地 Qdrant 可能输出 payload index warning；本地模式下该索引 warning 通常不影响实验
  结果，但同样应逐步重定向到日志。
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

不同 method 的 token 来源会写入 `measurement_source`。`api_usage` 表示直接读取
OpenAI-compatible response usage；`tokenizer_estimate` 表示 wrapper 无法拿到原始 usage 时
用 tokenizer 估算，不能混同为精确 API 账单。
同一个 method 内部也可能混合两种来源：例如 wrapper 可见的 reader 调用能记录
`api_usage`，第三方内部 memory build 调用若暂时无法暴露 usage，则仍会保留
`tokenizer_estimate` 并在后续审计中继续收敛。

## 日志结构

开发日志和运行日志分开：

- `docs/archive/handoffs/`: 上下文压缩或额度中断前的交接文件。
- `docs/task-ledger.md`: 当前任务和历史文档 open/closed 状态总账。
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

- [AGENTS.md](AGENTS.md): 项目入口、硬规则、协作模式、导航。
- [docs/roadmap.md](docs/roadmap.md): Phase 1 目标、workstream 索引、全局约束、恢复流程。
- [docs/workstreams/](docs/workstreams/): 各任务线状态页（README）+ spec + plan + notes。
- [docs/reference/architecture.md](docs/reference/architecture.md): 架构分层说明。
- [docs/reference/architecture-execution-flow.md](docs/reference/architecture-execution-flow.md): 完整架构与执行流程（论文级深度）。
- [docs/reference/data-model.md](docs/reference/data-model.md): core 数据模型说明。
- [docs/reference/custom-method-onboarding.md](docs/reference/custom-method-onboarding.md): 自定义 method 轻量接入指南。
- [docs/reference/method-interface-inventory.md](docs/reference/method-interface-inventory.md): 内置 method 原生接口审计。
- [docs/reference/method-resource-parameter-audit.md](docs/reference/method-resource-parameter-audit.md): method 参数与资源审计。
- [docs/reference/huggingface-datasets.md](docs/reference/huggingface-datasets.md): Hugging Face dataset 发布流程。
- [docs/reference/future-ideas.md](docs/reference/future-ideas.md): 实验监控 AI、新 method 接入 skill 等后期想法。
- [docs/reference/architect-playbook.md](docs/reference/architect-playbook.md): 架构师热规则与经验检索入口。
- [docs/reference/playbooks/architect/README.md](docs/reference/playbooks/architect/README.md): 按任务标签检索完整案例库。
- [docs/reference/actor-handbook.md](docs/reference/actor-handbook.md): 执行者施工规矩全文。
- [docs/archive/specs/2026-06-12-project-goals-architecture-design.md](docs/archive/specs/2026-06-12-project-goals-architecture-design.md): 长期项目目标与架构设计。
