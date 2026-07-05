# Conversation-QA Evaluation Refactor Design

> 历史设计说明：本文记录 2026-06-02 的 conversation-QA 收缩决策。仍可用于理解当前
> 数据模型和私有边界；涉及长期项目范围、效率指标、配置、registry、发布和目录演进时，
> 以 `docs/superpowers/specs/2026-06-12-project-goals-architecture-design.md` 为准。本文中
> “不做并发”“不记录效率观测”等阶段性非目标也已经被后续设计取代，不能作为当前实施
> 约束。

## 1. 目标

本次重构把项目从“泛 benchmark 统一协议”收缩为“conversation + QA 类型 memory benchmark 评测框架”。框架只关注 answer quality，不评 retrieval recall、不评效率、不评 token 数、不评延迟。

Phase 1 只跑通两个纯文本 benchmark：

- LoCoMo
- LongMemEval

后续再考虑：

- HaluMem QA-only
- MemBench QA-only / MCQ-only
- Mem-Gallery text-only，再扩展到 multimodal

已移除的偏好评测 不再属于本项目范围，所有 已移除的偏好评测 相关源码、测试、文档、数据结构说明和原始 benchmark 仓库都删除。

## 2. 非目标

本次重构不做以下内容：

- 不保留 `reset()` 接口。
- 不做 retrieval recall、precision、hit rate、NDCG 等检索指标。
- 不做 HaluMem extraction / update / hallucination 操作级评测。
- 不做 已移除的偏好评测 preference-following 评测。
- 不做异步、并发、吞吐量、延迟、token 统计。
- Phase 1 不做多模态推理。
- Phase 1 不提供 `Conversation.iter_turns()` 或 `Conversation.to_messages()` 这类 flatten helper。

## 3. 事实来源

新架构阶段只把以下内容作为事实来源：

1. 原始 benchmark 仓库和数据文件：`benchmarks/`
2. 数据结构说明：`dataset数据结构/`
3. 新参考架构：`EVALUATION_ARCHITECTURE.md`
4. 本设计文档、重写后的 `AGENTS.md`、重写后的 `README.md`

旧文档、旧 logs、旧 reports、`任务.md`、`参考.md`、`benchmark-structure-summary.md` 会归档到：

```text
old/2026-06-02-legacy/
```

归档目录只用于历史追溯，后续编码不得把 `old/` 作为事实来源。

## 4. 核心数据模型

新 core 显式保留 `Conversation -> Session -> Turn` 层级，不把 session 展平成 messages。

### 4.1 ImageRef

`ImageRef` 保留多模态扩展能力。Phase 1 不处理图片推理，但 Mem-Gallery 后续需要该结构。

```python
@dataclass
class ImageRef:
    image_id: str | None = None
    path: str | None = None
    caption: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 4.2 Turn

`Turn` 是单条发言，不是 user+assistant round。

```python
@dataclass
class Turn:
    turn_id: str
    speaker: str
    content: str
    normalized_role: str | None = None
    turn_time: str | None = None
    images: list[ImageRef] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

字段含义：

- `speaker`: 原始数据中的真实说话人，必填。
- `content`: 文本内容，必填。多模态数据如果有 caption，可把 caption 作为文本 fallback 放入内容或 metadata。
- `normalized_role`: 可选归一化角色，例如 `user`、`assistant`。LoCoMo 这种双人自然对话可以为 `None`。
- `turn_time`: 可选 turn-level 时间。
- `images`: 可选图片引用，Phase 1 不使用。
- `metadata`: 保存不适合升为核心字段的公开元信息。

### 4.3 Session

`Session` 是一次有边界的历史对话块。

```python
@dataclass
class Session:
    session_id: str
    turns: list[Turn]
    session_time: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

字段含义：

- `session_id`: 当前 conversation 内唯一的 session id。
- `turns`: 按原始顺序排列的发言。
- `session_time`: 数据集只有一个 session 时间点时使用，例如 LoCoMo。
- `start_time` / `end_time`: 数据集有时间区间时使用，例如 HaluMem。
- `metadata`: 保存 session 级公开元信息。

### 4.4 Question

`Question` 是 method 可见的公开问题对象，不包含 gold answer、evidence 或 judge label。

```python
@dataclass
class Question:
    question_id: str
    conversation_id: str
    text: str
    question_time: str | None = None
    category: str | None = None
    options: dict[str, str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

字段含义：

- `question_id`: 问题唯一 id。
- `conversation_id`: 问题所属 conversation，用于 memory namespace 隔离。
- `text`: 问题文本。
- `question_time`: 可选问题时间，例如 LongMemEval 的 `question_date`。
- `category`: 可选题型，例如 LoCoMo category 或 LongMemEval question_type。
- `options`: 可选选择题选项，服务未来 MemBench。
- `metadata`: method 可见的公开问题元信息。

### 4.5 GoldAnswerInfo

`GoldAnswerInfo` 是 evaluator 可见的私有答案信息，严禁传给 method。

```python
@dataclass
class GoldAnswerInfo:
    question_id: str
    answer: str
    evidence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

说明：

- `answer` 用于 answer quality metric。
- `evidence` 保留用于 debug/audit，不用于 Phase 1 metric。
- `metadata` 保存 benchmark-specific 私有评分信息。

### 4.6 Conversation

`Conversation` 是 memory 隔离和 QA 评测的核心单位。

```python
@dataclass
class Conversation:
    conversation_id: str
    sessions: list[Session]
    questions: list[Question]
    gold_answers: dict[str, GoldAnswerInfo]
    metadata: dict[str, Any] = field(default_factory=dict)
```

设计约束：

- `conversation_id` 是 method memory namespace 的核心字段。
- `questions` 只包含公开问题。
- `gold_answers` 只能给 evaluator 使用，通过 `question_id` 和 `questions` 对齐。
- method 不能接触 `gold_answers`。

### 4.7 Dataset

```python
@dataclass
class Dataset:
    dataset_name: str
    conversations: list[Conversation]
    metadata: dict[str, Any] = field(default_factory=dict)
```

## 5. Method 接口

接口使用同步版本。异步、并发和批量优化留到未来。

### 5.1 完整记忆系统接口

```python
class BaseMemorySystem(ABC):
    @abstractmethod
    def add(self, conversations: list[Conversation]) -> AddResult:
        raise NotImplementedError

    @abstractmethod
    def get_answer(self, question: Question) -> AnswerResult:
        raise NotImplementedError
```

说明：

- `add()` 接收 `list[Conversation]`，Phase 1 runner 默认每次传一个 conversation：`add([conversation])`。
- `get_answer()` 直接从 method / system 获取 answer。
- `get_answer()` 不接收 retrieval 参数。
- method 不接收 `GoldAnswerInfo`。

### 5.2 检索能力接口

```python
class BaseMemoryRetriever(ABC):
    @abstractmethod
    def retrieve(self, question: Question) -> RetrievalResult:
        raise NotImplementedError
```

说明：

- `retrieve()` 是否需要由 benchmark runner 决定，不由 method 类型决定。
- LoCoMo 和 LongMemEval Phase 1 不要求实现 `retrieve()`。
- 未来如果某个 benchmark 测记忆模块，可以要求 method wrapper 实现 `BaseMemoryRetriever`。
- `top_k` 不作为接口参数，由 method 自己配置。

### 5.3 Result 类

```python
@dataclass
class AddResult:
    conversation_ids: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class RetrievedMemory:
    content: str
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class RetrievalResult:
    question_id: str
    conversation_id: str
    memories: list[RetrievedMemory]
    formatted_context: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class AnswerResult:
    question_id: str
    conversation_id: str
    answer: str
    metadata: dict[str, Any] = field(default_factory=dict)
```

Phase 1 的 result 不记录 latency、tokens、new memories 或 retrieval recall 相关统计。

## 6. 数据转换与校验

### 6.1 动态转换为内部 dataclass

主流程采用动态转换：

```text
raw benchmark files
-> adapter / loader
-> Dataset / Conversation / Session / Turn / Question / GoldAnswerInfo
-> validation
-> runner
```

不把静态 normalized JSON 作为主数据源。

### 6.2 可选 normalized snapshot

为了 debug 和人工检查，可以额外导出统一格式快照：

```text
outputs/<run_id>/normalized/<dataset>.json
```

该快照只用于检查和复现，不作为下一次运行的默认输入。

### 6.3 强约束校验

adapter 转换完成后必须立刻校验。校验分两层：

通用校验：

- `Dataset.dataset_name` 必填。
- `Conversation.conversation_id` 必填。
- `Conversation.sessions` 不能为空。
- `Session.session_id` 必填。
- `Session.turns` 不能为空。
- `Turn.turn_id` 必填。
- `Turn.speaker` 必填。
- `Turn.content` 必填，除非该 benchmark 明确允许纯图片 turn 且 `images` 非空。
- `Question.question_id` 必填。
- `Question.conversation_id` 必须等于所在 `Conversation.conversation_id`。
- `Question.text` 必填。
- 每个 `Question` 必须能在 `gold_answers` 中找到同 id 的 `GoldAnswerInfo`。
- `GoldAnswerInfo.answer` 必填。

benchmark-specific 校验：

- LoCoMo：session time 必须保留；Phase 1 跳过 adversarial category。
- LongMemEval：question time 必须保留；question type 必须保留。
- MemBench QA-only：未来必须校验 `options` 和正确答案。
- HaluMem QA-only：未来只校验 QA 所需字段，不校验 extraction/update gold memory points。
- Mem-Gallery：未来必须校验图片 path/caption 之一，Phase 1 不进入 eval。

校验失败使用项目自定义异常，不让底层 `KeyError` / `FileNotFoundError` 直接泄漏到用户层。

## 7. Benchmark 范围

### 7.1 Phase 1

LoCoMo：

- 转换为 `Conversation -> Session -> Turn -> Question`。
- 一个 LoCoMo sample 对应一个 conversation。
- sample 下所有 QA 作为该 conversation 的 questions。
- 不评 retrieval recall。
- 不评 adversarial category。
- 指标：QA F1 + LLM judge accuracy。

LongMemEval：

- 一个 evaluation instance 对应一个 conversation。
- haystack sessions 转为 sessions。
- final question 转为一个 question。
- `question_date` 转为 `Question.question_time`。
- `question_type` 转为 `Question.category`。
- 指标：LLM judge accuracy。

### 7.2 后续阶段

HaluMem QA-only：

- user 可以转为 conversation。
- sessions 保留为 sessions。
- 只处理 session questions 的 answer-level QA。
- 不做 extraction/update/hallucination 操作级指标。

MemBench QA-only / MCQ-only：

- trajectory 转为 conversation。
- message_list 转为 session/turn。
- QA 转为 question，choices 转为 options。
- 指标为 answer/choice accuracy。

Mem-Gallery：

- scenario 转为 conversation。
- multi-session dialogues 转为 sessions。
- dialogue round 拆成 user turn 和 assistant turn。
- Phase 3 先 text-only，后续再处理 images。

已移除的偏好评测：

- 完全删除，不归档为可用 benchmark。

## 8. Runner 流程

Phase 1 runner 使用最小同步流程：

```python
dataset = adapter.load()
validate_dataset(dataset)

for conversation in dataset.conversations:
    system.add([conversation])

    for question in conversation.questions:
        answer = system.get_answer(question)
        gold = conversation.gold_answers[question.question_id]
        metric = evaluator.evaluate(question, answer, gold)
        writer.save_prediction(...)
        logger.log_event(...)
```

执行约束：

- runner 不调用 `reset()`。
- runner 不把 `GoldAnswerInfo` 传给 system。
- runner 不要求 `retrieve()`，除非 benchmark 明确声明需要检索能力。
- Phase 1 不做并发。

## 9. Metric 与 LLM Judge

### 9.1 LoCoMo

指标：

- QA F1
- LLM judge accuracy

限制：

- 不做 retrieval recall。
- 不做 adversarial category。

### 9.2 LongMemEval

指标：

- LLM judge accuracy

限制：

- 不把 LongMemEval 改成 F1。
- judge prompt 必须保留 question type 和 question time 等公开上下文。

### 9.3 LLM Judge 输出模式

LLM judge 按 benchmark 区分，不使用一个完全通用 prompt。

建议类：

- `LoCoMoJudgeEvaluator`
- `LongMemEvalJudgeEvaluator`

输出模式可配置：

```text
compact: 只返回 true / false，节省 token
detailed: 返回 true / false + reason，便于 debug
```

Phase 1 默认可以使用 `compact`，debug 时使用 `detailed`。

OpenAI 配置继续读取 `.env` 中的：

- `OPENAI_KEY`
- `BASE_URL`

模型固定使用当前项目约定的 `gpt-4o-mini`，除非用户明确修改。

## 10. 日志与输出

引入 `rich` 改善终端日志。

日志分三层：

1. 终端日志：
   - rich console
   - 当前 dataset、system、conversation、QA 进度
   - 当前 metric summary

2. 文件日志：

```text
outputs/<run_id>/logs/run.log
```

3. 结构化事件日志：

```text
outputs/<run_id>/logs/events.jsonl
```

事件示例：

- `run_started`
- `dataset_loaded`
- `conversation_validated`
- `conversation_added`
- `question_answered`
- `judge_completed`
- `run_completed`

预测与结果建议输出：

```text
outputs/<run_id>/
├── predictions/
│   └── <dataset>.jsonl
├── metrics/
│   └── <dataset>.json
├── normalized/
│   └── <dataset>.json
└── logs/
    ├── run.log
    └── events.jsonl
```

## 11. 文档整改

重构开始时：

- `docs/` 旧内容归档到 `old/2026-06-02-legacy/docs/`。
- `任务.md`、`参考.md`、`benchmark-structure-summary.md` 归档到 `old/2026-06-02-legacy/`。
- 旧 reports 归档到 `old/2026-06-02-legacy/reports/`。
- 已移除的偏好评测 相关内容直接删除，不放入新事实来源。

新文档最少包括：

- `AGENTS.md`
- `README.md`
- `docs/architecture.md`
- `docs/data-model.md`
- `docs/method-interface.md`
- `docs/benchmark-scope.md`
- `docs/refactor-plan.md`

新 `AGENTS.md` 必须写明：

- 后续遇到实质性设计问题，必须先和用户讨论再行动。
- `old/` 是历史废纸篓，不作为事实来源。
- Phase 1 只做 LoCoMo + LongMemEval。
- 项目只做 conversation + QA 类型 answer quality evaluation。
- 已移除的偏好评测 已永久移出项目范围。

## 12. 方案结论

采用方案 B：重建 conversation-QA v2 架构。

不在旧 `EvalScope -> MemorySegment -> EvalQuery` 和 `reset / ingest / respond` 模型上继续打补丁。

第一阶段的交付判断：

- 已移除的偏好评测 全删。
- 旧文档归档。
- core 数据模型替换为 conversation/session/turn/question/gold answer info。
- method 接口替换为 `BaseMemorySystem.add()` + `BaseMemorySystem.get_answer()`。
- retrieval 能力拆到 `BaseMemoryRetriever`，Phase 1 不强制实现。
- LoCoMo 和 LongMemEval 能加载、校验、运行 answer-level evaluation。
- 日志和输出结构清晰可 debug。
