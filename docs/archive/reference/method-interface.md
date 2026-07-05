# Method 接口

Phase 1 使用同步接口，采用“最低必需接口 + 可选能力”分级。

## 完整记忆系统

```python
class MyMemorySystem(BaseMemorySystem):
    def add(self, conversations: list[Conversation]) -> AddResult:
        ...

    def get_answer(self, question: Question) -> AnswerResult:
        ...
```

`add()` 接收 `list[Conversation]`，不接收单个 session。这样 method 可以一次看到同一个 conversation 的完整历史，也方便后续批量写入。

`get_answer()` 只接收 `Question`，不接收标准答案、evidence、检索结果或额外打分标签。

## Method 类型

- `end_to_end`：实现 `add()` 和 `get_answer()`，自行生成答案。
- `memory_module`：原始模块实现写入和检索，由框架 fixed-reader wrapper 组合成
  `BaseMemorySystem` 后生成答案。

固定 reader 的模型、prompt 和参数由框架统一管理，保证不同 memory module 可公平比较。
纯 memory module 不需要伪造自己的 `get_answer()`。

## 可选检索能力

```python
class MyRetriever(BaseMemoryRetriever):
    def retrieve(self, question: Question) -> RetrievalResult:
        ...
```

检索接口用于 memory module、需要检索能力的 benchmark，以及未来 Retrieval Latency
观测。Phase 1 的 LoCoMo 和 LongMemEval 质量评测不强制实现。

## 可选效率观测

未来只规划三项：

- retrieval latency。
- memory context tokens。
- memory update latency、LLM tokens、embedding tokens。

运行时必须保存逐操作原始 observation，evaluate 再聚合。method 不支持某项能力时，
质量评测仍可运行；用户选择对应效率 metric 时必须在付费调用前报错，不能估算冒充实测。

## Method 不应该看到什么

runner 调用 method 前会剥离：

- `GoldAnswerInfo`
- evidence
- judge label
- private metadata
- dataclass 动态挂载的私有属性

如果公开 payload 中出现常见私有键，框架会抛 `DataLeakageError`。

## 用户自定义 Method

当前自定义 method 通过 Python API 接入：

```python
method = MyMemorySystem(...)
predict(benchmark="locomo", method=method, config=config)
```

公共 API 只接受已注册且 adapter 完成的 benchmark，并在 API 调用前校验数据、接口、能力、
配置和 run compatibility。CLI 当前只运行官方集成；插件自动发现等真实需求出现后再增加。

## 兼容判断

长期使用 task family 和 capability 自动判断兼容性，不要求每个 method 手工列出所有
benchmark。只有已知异常才添加显式限制规则。
