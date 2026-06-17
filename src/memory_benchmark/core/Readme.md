# core 层说明

`memory_benchmark/core/` 是框架的公共语言层。它只定义实体、接口、校验和领域异常，不读取原始 dataset，不调用 LLM，不计算 metric。

当前核心目标是支撑 conversation + QA benchmark：

```text
Dataset -> Conversation -> Session -> Turn
                           -> Question
                           -> GoldAnswerInfo
```

## 文件职责

- `entities.py`: 数据实体，例如 `Conversation`、`Session`、`Turn`、`Question`、`GoldAnswerInfo`。
- `interfaces.py`: method 抽象基类，包括完整记忆系统和可选检索能力。
- `validators.py`: 数据结构强校验和公开 payload 私有字段泄漏检查。
- `exceptions.py`: 项目领域异常，调用方可以稳定捕获。
- `results.py`: dry-run 等框架级摘要对象。
- `__init__.py`: core 层稳定导出入口。

## 实体设计理由

### Dataset

`Dataset` 表示 adapter 一次加载出的统一数据集。它包含多个 `Conversation`，并用 `metadata` 保存 split、source path、规范化计数等公开调试信息。

### Conversation

`Conversation` 是记忆隔离空间。框架不做全局清空，而是用 `conversation_id` 隔离问题和历史。

字段：

- `conversation_id`: 当前 conversation 的唯一 id。
- `sessions`: 历史对话片段。
- `questions`: method 可见问题。
- `gold_answers`: evaluator 私有标准答案，key 必须和 `Question.question_id` 对齐。
- `metadata`: method 可见公开元信息，不能含答案/evidence。

### Session

`Session` 是一段有边界的历史对话。LoCoMo 的 `session_1`、LongMemEval 的一个 haystack session 都会映射为 `Session`。

字段：

- `session_id`: 当前 session 唯一 id。
- `turns`: 按原始顺序排列的发言。
- `session_time`: 原始 session-level 时间。
- `start_time` / `end_time`: 可选时间范围。
- `metadata`: 公开调试信息，例如原始 session id、source index。

### Turn

`Turn` 是单个 speaker 的一次发言。

约定：

- `speaker1: "content"` 是一个 turn。
- `speaker1: "content" + speaker2: "content"` 是一个 round，应拆成两个 turn。

字段：

- `turn_id`: 当前发言 id。
- `speaker`: 原始说话人，不强行改写。
- `content`: 文本内容；纯文本 Phase 1 要求非空。
- `normalized_role`: 可选标准角色，例如 `user`、`assistant`。
- `turn_time`: 可选发言时间。
- `images`: 后续多模态扩展使用。
- `metadata`: 公开发言级元信息。

### Question

`Question` 是 method 可见问题。它不能包含标准答案、evidence、judge label 或 private metadata。

字段：

- `question_id`: 问题 id。
- `conversation_id`: 所属 conversation。
- `text`: 问题文本。
- `question_time`: 可选问题时间，例如 LongMemEval 的 question date。
- `category`: benchmark 原始题型或类别。
- `options`: 可选选择题选项，Phase 1 暂不使用。
- `metadata`: 公开问题级元信息。

### GoldAnswerInfo

`GoldAnswerInfo` 是 evaluator 私有标准答案对象。runner 可以读取它并交给 evaluator，但绝不能传给 method。

字段：

- `question_id`: 对齐公开问题。
- `answer`: 标准答案。
- `evidence`: 私有 evidence id 列表，只用于 scorer 或审计。
- `metadata`: scorer-only 信息，例如原始标签。

### ImageRef

`ImageRef` 为后续多模态 benchmark 保留。Phase 1 不主动读取图片，但 core 允许 turn 带图片引用和 caption fallback。

### AnswerResult / MetricResult / EvaluationResult

- `AnswerResult`: method 对公开问题的回答。
- `MetricResult`: evaluator 对单题的打分。
- `EvaluationResult`: runner 汇总后的结果。

### RetrievalResult

`RetrievalResult` 是可选能力的输出。Phase 1 不要求 method 实现检索接口，也不计算检索召回类指标；该实体只为后续需要记忆模块诊断的 benchmark 保留。

## 接口

完整记忆系统继承 `BaseMemorySystem`：

```python
class MyMemorySystem(BaseMemorySystem):
    def add(self, conversations: list[Conversation]) -> AddResult:
        ...

    def get_answer(self, question: Question) -> AnswerResult:
        ...
```

可选检索器继承 `BaseMemoryRetriever`：

```python
class MyRetriever(BaseMemoryRetriever):
    def retrieve(self, question: Question) -> RetrievalResult:
        ...
```

Phase 1 runner 只要求 `BaseMemorySystem`。

## 校验规则

`validators.py` 负责两类校验：

- `validate_dataset(dataset)`: 检查 conversation/session/turn/question/gold 的必填字段和对齐关系。
- `validate_no_private_keys(payload)`: 检查公开 payload 中是否出现答案、evidence、judge label 等私有键。

runner 在调用 method 前会重建公开对象，而不是复制完整对象，避免 Python dataclass 动态属性把私有信息带入 method。
