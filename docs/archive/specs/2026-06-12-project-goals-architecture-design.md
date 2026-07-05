# Agent Memory Benchmark Framework 长期目标与架构设计

状态：用户已确认  
日期：2026-06-12

## 1. 项目目标

本项目要构建一个可复现、可扩展、可审计的 Agent Memory Benchmark 评测框架。

框架首先服务两类用户：

1. 实验使用者通过统一 CLI 运行官方兼容的 benchmark、method 和 metric。
2. memory method 研究者实现稳定接口后，通过 Python API 在已支持 benchmark 上评测
   自定义 method。

长期目标包括：

- 统一不同 benchmark 的数据输入、运行流程和实验产物。
- 避免为每个 method × benchmark 组合复制专用 runner。
- 将昂贵的 prediction 与可重复执行的 evaluation 分离。
- 保存数据指纹、源码版本、最终配置、逐题回答和运行期观测，保证实验可复验。
- 随真实需求增加新的 benchmark task family，而不是强迫所有 benchmark 使用同一数据模型。
- 为未来可验证排行榜保留 provenance 和标准 run bundle，但当前不实现网站、数据库或上传服务。

## 2. 当前范围与演进方式

### 2.1 当前 task family

当前只实现：

```text
conversation_qa
Dataset -> Conversation -> Session -> Turn
                           -> Question
                           -> GoldAnswerInfo
```

Phase 1 只做纯文本：

1. 先以 LoCoMo 打通各个 method 的完整链路。
2. 再接入 LongMemEval。

HaluMem、MemBench、Mem-Gallery 暂不进入主线。未来只在其真实评测协议能明确映射到某个
task family 后接入。多模态字段继续保留，但当前不运行多模态实验。

### 2.2 未来 task family

未来若出现不能自然表达为 conversation + QA 的 benchmark，应新增独立 task family：

```text
task_families/
  conversation_qa/
  <future_family>/
```

每个 task family 拥有自己的 entities、protocol、validator 和 required capabilities。
当前没有第二种真实需求，因此暂不迁移现有 `core/`，也不预先设计不存在的协议。

## 3. 运行模型

框架保留三个入口：

```text
predict
  benchmark + method + resolved config
  -> 生成回答和运行期原始观测

evaluate
  existing run artifacts + evaluator config
  -> 计算质量或效率 metric

run
  -> predict + evaluate 的便利组合
```

正式架构以可独立恢复的 `predict` 和 `evaluate` 为基础；`run` 不复制逻辑。

分离带来的约束：

- 新增或修改 evaluator 不得重新调用 method。
- 同一批 prediction 可以计算多个 metric。
- prediction 失败与 evaluation 失败分别恢复。
- LLM judge 等付费 evaluator 必须显式确认 API。

## 4. 分层架构

```text
CLI / Public Python API
  ↓
Command Service
  ↓
Registries + Compatibility Resolver + Config Resolver
  ↓
Benchmark Adapter + Method Adapter/Instance + Evaluator
  ↓
Generic Prediction / Evaluation Runner
  ↓
Immutable Run Artifacts + Checkpoints + Logs
```

### 4.1 CLI 与 Python API

CLI 面向实验使用者，运行官方内置集成：

```text
memory-benchmark predict
memory-benchmark evaluate
memory-benchmark run
```

Python API 面向研究者。自定义 method 实现接口并传入已经创建的实例；当前不实现
CLI 任意动态导入、插件自动发现或工厂路径。未来出现明确需求后，再采用 Python entry
point 插件机制。

公共 `predict()` 只接受已经注册并实现 adapter 的 benchmark 名称。任意原始 Dataset
注入属于框架内部测试接口，不作为普通用户的稳定 API。

### 4.2 Benchmark Adapter

adapter 负责：

- 定位或接收用户覆盖的数据路径。
- 读取 benchmark 原始数据。
- 转换为当前 task family 的实体。
- 分离 method public input 与 evaluator private labels。
- 执行通用和 benchmark-specific 强校验。

benchmark 数据路径采用“默认路径 + 用户可覆盖路径”。自动下载 benchmark 属于成熟阶段
功能，当前不实现。

### 4.3 Method

method 分为两种形态：

- `end_to_end`：method 实现写入并直接生成答案。
- `memory_module`：原始模块实现写入和检索，框架用固定 reader wrapper 把它包装为
  runner 可调用的完整回答系统。

固定 reader 的模型、prompt、参数和版本由框架统一管理。同一比较中的 memory module
必须使用相同 reader profile；benchmark 官方指定 reader 时以官方设置为准。

官方兼容 method 的第三方源码由项目提供、固定版本并手动升级，不自动追踪 upstream。
每个 method 必须记录上游地址、版本或 tree hash、许可证、是否修改源码和验证状态。
许可证不允许或不明确时，不直接再分发源码。

自定义 method 当前通过 Python API 接入，不要求修改官方 registry。

### 4.4 Evaluator

evaluator 只消费标准 artifacts，不重新调用 method。

当前质量指标：

- LoCoMo token F1。
- LoCoMo 可选 LLM judge。
- LongMemEval LLM judge，在统一入口迁移完成后启用。

当前不实现 retrieval recall。未来效率 evaluator 只聚合 prediction 阶段保存的原始
observation。

### 4.5 Runner

通用 conversation-QA runner 负责：

- 运行前强校验。
- 依据 `conversation_id` 隔离 method 状态。
- conversation 内保证 `add -> questions` 顺序。
- conversation 间可并行。
- worker 返回结果，协调层串行提交共享 artifacts。
- checkpoint、resume、日志和错误边界。

禁止继续新增 `<method>_<benchmark>_full.py` 文件矩阵。现有 MemoryOS 专用 runner 是待迁移
的历史垂直实现，不是未来扩展模式。

## 5. Registry 与兼容性

Registry 是“名称到实现与声明”的目录，不保存运行实例或 secret。

保留三类独立 registry：

- benchmark registry：adapter、task family、required capabilities、默认数据位置。
- method registry：官方 method、profile、provided capabilities、源码身份和装配入口。
- evaluator registry：metric、支持的 task family/benchmark、profile、是否需要 API。

不把三类 registry 合并成万能 registry。

长期兼容判断不维护 method × benchmark 白名单，而使用：

```text
benchmark.task_family == method.supported_task_family
benchmark.required_capabilities ⊆ method.provided_capabilities
evaluator.required_observations ⊆ run.available_observations
```

只有确实存在已知不兼容时，才添加显式限制规则。

## 6. Method 能力分级

### 6.1 最低质量评测能力

```python
class BaseMemorySystem(ABC):
    def add(self, conversations: list[Conversation]) -> AddResult: ...
    def get_answer(self, question: Question) -> AnswerResult: ...
```

### 6.2 可选检索能力

```python
class BaseMemoryRetriever(ABC):
    def retrieve(self, question: Question) -> RetrievalResult: ...
```

纯 memory module 不需要伪造自己的 `get_answer()`。它实现写入与检索能力后，由框架的
fixed-reader wrapper 组合为 `BaseMemorySystem`，通用 runner 仍只依赖完整回答接口。

### 6.3 可选效率观测能力

效率观测不应强迫所有 method 实现。用户选择对应效率 metric 时，框架必须在付费实验启动前
检查能力；缺失能力直接报错或在既有 run 上标记 `unsupported`，不得估算冒充实测。

## 7. 效率评测范围

第一阶段只规划三项：

### 7.1 Retrieval Latency

范围：

```text
接收 query
-> embedding
-> search
-> filter/rerank
-> 返回最终记忆
```

不包含最终 LLM 回答生成。外层统一使用 `time.perf_counter_ns()` 计时，保存原始纳秒值。

### 7.2 Memory Context Tokens

统计真正注入固定 reader 或最终回答 LLM prompt 的记忆上下文 token，不统计数据库全部记忆、
问题文本或普通 system instruction。必须记录 tokenizer/model。

### 7.3 Memory Update Cost

分别记录：

- update latency。
- LLM input tokens。
- LLM output tokens。
- embedding input tokens。

聚合时再给出 LLM total、embedding total 和总 token。不得只保存不可审计的平均值。

### 7.4 Observation 规则

prediction 阶段逐操作保存原始观测：

- 每次 turn/chunk 或 add 的 update observation。
- 每道 question 的 retrieval observation。
- 每道 question 的 memory context observation。

evaluate 阶段统一计算总量、均值、P50、P95，以及按 turn、conversation、question 的归一化
结果。旧实验没有原始 observation 时不能补造效率结果。

## 8. 配置体系

避免 method × benchmark 配置笛卡尔积：

```text
configs/
  methods/
  benchmarks/
  runners/
  evaluators/
  examples/
```

解析优先级：

```text
代码安全默认值
< 命名 profile
< 用户实验 TOML
< 少量 CLI 显式覆盖
```

配置分级：

- `official`：官方/论文复现配置，影响实验语义的关键参数禁止临时覆盖。
- `smoke`：低成本真实链路测试。
- `custom`：允许用户调整 method、runner 和 reader 参数。

所有面向用户的示例配置必须带详细注释。运行前把最终合并配置强类型校验，并写入脱敏的
resolved config；secret 只能来自 `.env` 或环境变量。

## 9. 实验不可变性

一个 `run_id` 首次创建后，以下内容不可改变：

- task family、benchmark 和数据指纹。
- method、源码身份和关键配置。
- reader profile。
- prediction 范围和运行形状。

`--resume` 只能继续完全兼容的实验。配置改变必须使用新 `run_id`。

`evaluate` 可以为同一 prediction 增加独立 metric。重算已有 metric 必须显式 `--force`，
保留 evaluator 配置和版本，不修改原 prediction。

## 10. 资源、发布与目录方向

近期发布方式：

- GitHub 完整工程。
- 使用 `uv` 安装和运行。
- 项目携带许可证允许再分发的固定 method 源码。
- benchmark 大型数据不进入 Python wheel，由用户配置本地路径。

成熟后：

- 发布 PyPI 核心包和 CLI。
- 增加 benchmark install/register/verify，但当前不实现。
- 用户自定义 method 如有真实 CLI 需求，再增加标准 Python entry-point 插件。

长期目录方向：

```text
src/                  # 第一方可安装框架
configs/              # 分层 profile 和带注释示例
tests/                # unit/integration/api/contract
docs/                 # 架构、协议、参考资料和 handoff
third_party/
  benchmarks/         # 官方 benchmark 仓库和数据
  methods/            # 官方兼容 method 固定源码
models/               # 本地模型和 NLP 资源
outputs/              # 不可变 run 产物
```

当前 `benchmarks/` 的迁移涉及大文件和大量路径引用，应作为独立迁移任务执行，不在文档更新
阶段移动。

## 11. 当前实施顺序

1. 保持 LoCoMo 为第一优先 benchmark。
2. 把 MemoryOS 迁入 TOML、method registry 和通用 prediction/evaluation runner。
3. API 余额恢复后，使用统一入口运行 Mem0-LoCoMo official-full prediction。
4. 复用 prediction 计算 LoCoMo F1，必要时再执行 LLM judge。
5. 在 LoCoMo 上至少两个 method 的统一闭环稳定后，再迁移 LongMemEval。
6. 之后再设计三项效率 observation schema 和能力接口。
7. 项目底座稳定后，执行目录清理、tests 分组和 benchmark 第三方目录迁移。

## 12. 明确暂不实施

- 第二种 task family。
- 排行榜网站、数据库和结果上传。
- benchmark 自动下载。
- 自定义 method CLI 动态导入或插件发现。
- 完整效率指标实现。
- 异步 runner。

这些内容只保留架构边界，不提前增加当前系统复杂度。
