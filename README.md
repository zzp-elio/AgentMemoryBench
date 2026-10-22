# AgentMemoryBench

评测端统一答题和打分，记忆系统只交回记忆。这样比较的是记忆本身，而不是各家论文自己的答题模型、提示词和指标。

记忆系统实现两个接口即可接入：

| 接口 | 做什么 |
| :--- | :--- |
| `ingest` | 一次写入一个会话。会话包含各轮发言和会话时间，并用 `isolation_key` 把不同对话分开。标准答案不传入。 |
| `retrieve` | 按问题和 `isolation_key` 取回记忆，只返回一段 `formatted_memory`。不返回答案。 |

评测端把这段记忆拼进答题提示词，生成回答后再打分。召回率不进入总分：取回的是改写后的记忆，不是原话位置。

---

## 评测题

五个基准的原题按「做对时该回答什么」收成 6 类。总分和这 6 类用同一批题。对不上的原题在加载时去掉。

| 类型 | 做对时 |
| :--- | :--- |
| 事实回忆 | 把已经说过的内容说出来 |
| 多证据综合 | 把好几处说过的内容拼起来 |
| 时间与顺序 | 用日期或先后作答 |
| 记忆更新 | 只答更新后的当前值 |
| 拒答 | 明确说没说过 |
| 个性化 | 偏好已经说过，回答要照着做 |

不进入这 6 类的题包括：LoCoMo 的对抗题和开放域常识题，MemBench 没说破的偏好、情绪、再加工和带噪问题，BEAM 的内部矛盾、指令遵循和长期总结，HaluMem 的错误前提纠正和新情境应用。

打分用三个评测器：精确匹配、F1、LLM 裁判。信息不够时，裁判可以拒绝打分并转人工，而不是猜一个对错。

---

## 流水线

```mermaid
flowchart LR
    D["五个基准"] --> A["读入并标成 6 类"]
    A --> I["ingest 按会话写入"]
    I --> R["retrieve 取回一段记忆"]
    R --> Q["评测端生成回答"]
    Q --> E["精确匹配 / F1 / LLM 裁判"]
```

---

## 目录结构

代码采用标准微服务中间层架构，Git 仅白名单跟踪评测端核心源码与配置文件：

```text
├── configs/
│   └── application.yaml                # 统一配置（LLM 客户端与动态 Prompt 矩阵）
├── src/memory_benchmark/               # 评测中间层核心源码
│   ├── benchmark_adapters/             # 5 大基准加载与 6 类题型过滤适配器 (LoCoMo / LongMemEval 等)
│   ├── core/                           # 核心领域实体、中间层协议 (MemoryProvider) 与安全变量格式化引擎
│   ├── coordinator/                    # 评测协调微服务 (IoC 容器，接收外部容器 /ready 握手编排)
│   ├── readers/                        # 统一回答生成器 (FrameworkAnswerReader 拼接记忆与生成回答)
│   ├── evaluators/                     # 通用评估器 (ExactMatch / F1 / 支持拒判转人工的双模式 LLM-Judge)
│   ├── runners/                        # 执行器 (prediction.py 并发预测与 evaluation.py 离线解耦打分)
│   ├── storage/                        # 评测实验产物管理 (JSON Lines 读写与原子落地)
│   ├── utils/                          # 通用工具 (线程安全运行日志记录器等)
│   └── __main__.py                     # 极简 CLI 命令行入口
├── pyproject.toml                      # 项目元数据与评测必要依赖规范 (无重型依赖冲突)
├── uv.lock                             # 确定性依赖版本锁定文件
├── .env.example                        # 环境变量模板 (API_KEY / BASE_URL / MODEL_NAME)
└── .gitignore                          # 严格白名单过滤规则
```

### 关键目录与模块职责

- [`configs/application.yaml`](configs/application.yaml)：全局基准与差异化覆盖配置中心。定义 `llm.answer` 与 `llm.judge` 默认模型参数，并配置各大 Benchmark 细分题型的定制化 System/User 提示词。
- [`src/memory_benchmark/benchmark_adapters/`](src/memory_benchmark/benchmark_adapters/)：统一数据接口。负责解析原始对话为 `Conversation -> Session -> Turn`，只保留映射进 6 类的有效题，并剥离私有参考答案。
- [`src/memory_benchmark/core/`](src/memory_benchmark/core/)：系统核心抽象层。提供泛型响应封装 `Result[T]`、极简双方法客户端协议 [`HttpMemoryProvider`](src/memory_benchmark/core/provider_protocol.py)，以及免疫 JSON 花括号冲突的安全提示词格式化引擎。
- [`src/memory_benchmark/readers/`](src/memory_benchmark/readers/)：统一答题生成层。将被测记忆系统返回的纯文本 `formatted_memory` 拼入提示词，使用统一配置的 Answer LLM 回答问题。
- [`src/memory_benchmark/evaluators/`](src/memory_benchmark/evaluators/)：统一指标打分层。包括字符串精确匹配 `ExactMatch`、Token 级重叠度 `F1` 以及强类型 Pydantic 双模式的 `LLMJudgeEvaluator`（遇到不可判情况自动标记 `UNDECIDABLE` 拒判转人工复核）。
- [`src/memory_benchmark/runners/`](src/memory_benchmark/runners/)：流水线编排调度层。以对话（Conversation）为粒度进行多线程并发执行，并按原始索引严格确定性归并生成产物。

---

## 运行

评测中间层与被测记忆系统采用 **C/S 微服务解耦架构**：
评测端只负责发送评测流量（调度 Ingest、Retrieve 并打分），被测记忆系统作为独立 HTTP Server 运行（实现 `/ingest` 与 `/retrieve`）。

### 1. 安装 uv 与依赖初始化

推荐使用现代 Python 极速包管理工具 [uv](https://docs.astral.sh/uv/) 初始化环境：

```bash
# 1. 安装 uv (如未安装)
# macOS / Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh
# 或使用 Homebrew:
# brew install uv

# 2. 一键创建虚拟环境并锁定安装依赖
uv sync
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，配置用于答题和裁判的大模型参数：

```bash
cp .env.example .env
```

在 `.env` 中填写以下变量（兼容任何提供 OpenAI `/v1/chat/completions` 接口的模型服务或中转地址）：

```bash
API_KEY=your_api_key_here
BASE_URL=https://api.openai.com/v1
MODEL_NAME=gpt-4o-mini
```

### 3. 运行自动化契约测试

在运行真实实验前，可运行测试套件验证代码与文档防漂移契约：

```bash
uv run pytest -q
```

---

### 4. 运行评测实验

#### 方式 A：零外部服务依赖快速冒烟（单方面立即可跑）

无需启动任何外部记忆微服务，使用内置的 `mock` 内存测试桩单方面跑通全流程：

```bash
uv run memory-benchmark \
  --benchmark locomo \
  --method mock \
  --max-conversations 1 \
  --metrics f1
```

#### 方式 B：对接真实 Memory Server 的端到端评测（C/S 协同跑法）

1. **步骤 1：启动被测记忆服务**
   启动你的 Memory Server（需提供标准的 `POST /ingest` 与 `POST /retrieve` 接口）。
   例如服务启动并监听在本地 `8002` 端口（`http://127.0.0.1:8002`）。

2. **步骤 2：启动评测打流**
   通过 `--server-url` 指定你的 Memory Server 真实访问地址：

   ```bash
   uv run memory-benchmark \
     --benchmark locomo \
     --method http \
     --server-url http://127.0.0.1:8002 \
     --metrics f1 \
     --max-conversations 1
   ```

---

## 命令行参数完整参考 (CLI Reference)

> **全量与抽样规则**：
> - **默认全量评测**：如果不指定 `-c` / `--max-conversations`（缺省值为 `None`），框架将**默认加载该 Benchmark 的 100% 全量数据**进行完整评测；
> - **微规模抽样**：指定 `-c 1` 或 `-q 5` 仅用于开发调试、网络连通性测试与快速冒烟。

### 1. 评测基准与数据抽样选项 (Benchmark & Data Sampling)

| 参数 (Option) | 短选项 | 默认值 | 取值范围 / 示例 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `--benchmark` | `-b` | `locomo` | `locomo`, `longmemeval`, `halumem`, `beam`, `membench` | 目标评测基准数据集。 |
| `--max-conversations` | `-c` | `None` *(全量)* | 整数（如 `1`, `10`） | 评测的最大对话数。**不传时默认 100% 全量评测**。 |
| `--max-questions` | `-q` | `None` *(全量)* | 整数（如 `5`, `20`） | 每段对话评测的最大问题数。支持别名 `--max-questions-per-conversation`。 |
| `--project-root` | - | `.` | 路径字符串 | 项目根目录路径。 |

### 2. 被测记忆系统连接配置 (Memory Server Connection)

| 参数 (Option) | 短选项 | 默认值 | 取值范围 / 示例 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `--method` | `-m` | `mock` | `http`, `mock` | 评测模式：`http` 连接外部独立记忆微服务；`mock` 本地离线自测。 |
| `--server-url` | `-u` | `None` | `http://127.0.0.1:8002` | 被测 Memory Server 的真实 HTTP 根地址（`--method http` 时必填）。 |

### 3. 评测指标与模型控制 (Metrics & LLM Execution)

| 参数 (Option) | 短选项 | 默认值 | 取值范围 / 示例 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `--metrics` | - | `f1` | `f1`, `exact_match`, `llm_judge` | 逗号分隔的评估指标列表，如 `--metrics f1,exact_match`。 |
| `--mock-llm` | - | `False` | 标志位（无需值） | 强制使用本地确定性测试客户端生成回答，绝不调用外部 LLM API。 |

### 4. 并发调度与执行管理 (Concurrency & Execution)

| 参数 (Option) | 短选项 | 默认值 | 取值范围 / 示例 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `--max-workers` | `-w` | `1` | 整数（如 `4`, `10`） | 会话级多线程并发 Worker 数。评测自动按原始索引确定性归并产物。 |
| `--run-id` | - | 自动生成 | 字符串（如 `test_run_01`） | 显式指定本次实验运行标识符，输出将保存在 `outputs/{run_id}/`。 |

### 5. 高级解耦模式与 Coordinator 微服务 (Advanced & Service Modes)

| 参数 (Option) | 短选项 | 默认值 | 取值范围 / 示例 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `--eval-run-dir` | - | `None` | 产物目录路径 | 离线打分模式：直接对已有预测产物重新评测，无需重复写入与检索记忆。 |
| `--server` | - | `False` | 标志位（无需值） | 启动 Coordinator 微服务，常驻监听外部容器的 `/ready` 握手。 |
| `--host` | - | `127.0.0.1` | IP 地址字符串 | Coordinator 服务绑定的主机地址。 |
| `--port` | - | `8000` | 端口号（整数） | Coordinator 服务绑定的端口号。 |

---

## 常用评测场景示例 (Cookbook)

#### 场景 1：全量真实评测（默认全量，对接外部微服务）
```bash
uv run memory-benchmark \
  -b locomo \
  -m http \
  -u http://127.0.0.1:8002 \
  --metrics f1
```

#### 场景 2：10 线程高并发加速评测（推荐用于 LoCoMo 全量 10 个独立会话）
```bash
uv run memory-benchmark \
  -b locomo \
  -m http \
  -u http://127.0.0.1:8002 \
  -w 10 \
  --metrics f1
```

#### 场景 3：快速单会话冒烟验证（抽样 1 个 Conversation，秒级验证连通性）
```bash
uv run memory-benchmark \
  -b locomo \
  -m mock \
  -c 1 \
  --metrics f1
```

#### 场景 4：多指标复合评测（同时运行 F1 与精确匹配）
```bash
uv run memory-benchmark \
  -b locomo \
  -m http \
  -u http://127.0.0.1:8002 \
  -c 1 \
  --metrics f1,exact_match
```

#### 场景 5：离线二次评估（无需再次请求 Memory Server 与重复消耗 Token）
```bash
uv run memory-benchmark \
  --eval-run-dir outputs/locomo_http \
  --metrics exact_match,llm_judge
```
