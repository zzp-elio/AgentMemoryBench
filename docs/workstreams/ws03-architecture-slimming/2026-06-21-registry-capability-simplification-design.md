# Registry 与 Capability 减重设计备忘

日期：2026-06-21

## 背景

项目主协议正在收敛到 retrieve-first memory-module 架构：

```text
add(conversation) -> retrieve(question) -> framework reader -> answer
```

在这个方向下，`BaseMemoryProvider` 已经天然表达了 conversation + QA 主线需要的
method 能力。继续维护较重的 capability 枚举和多套旧 base class，会让代码看起来比
实际需求更复杂，也会增加新 method 接入者的理解成本。

## 结论

保留 registry，但把 registry 做轻。

Registry 不应变成复杂策略系统，也不应模拟数据库式的持久化表。它的主要职责只保留：

- CLI 名称到 method/benchmark/evaluator factory 的映射。
- profile/config/source identity 的集中声明。
- run 前构造对象所需的稳定元信息。

也就是说，registry 替代分散的 `if method == "mem0"` / `if benchmark == "locomo"`，
但不应该承载过重的能力推理。

## Capability 收敛方向

第一版目标是让继承关系成为主要能力声明：

- `BaseMemoryProvider` 代表 `add(conversation) + retrieve(question)`。
- conversation + QA prediction 主路径只接受 `BaseMemoryProvider`。
- `MethodCapability.CONVERSATION_ADD`、`MethodCapability.MEMORY_RETRIEVAL`、
  `MethodCapability.ANSWER_GENERATION` 在 retrieve-first 全链路稳定后逐步删除或降级为
  兼容层内部细节。

运行时判断应逐步从：

```python
MethodCapability.MEMORY_RETRIEVAL in method_registration.provided_capabilities
```

收敛为：

```python
isinstance(system, BaseMemoryProvider)
```

这更直观，也更贴近用户接入新 method 时实际需要实现的接口。

## 旧接口处理方向

以下接口属于迁移期历史接口，不应继续扩展新功能：

- `BaseMemorySystem`
- `BaseResumableMemorySystem`
- `BaseMemoryRetriever`

删除条件：

1. 四个内置 method 的 registered prediction 主路径全部稳定走 `BaseMemoryProvider`。
2. fake/offline 测试不再依赖 legacy `get_answer()`。
3. 旧 artifact-only evaluation 和历史 runner 不再需要这些接口。

删除前允许保留兼容 wrapper，但文档必须明确新 method 不应实现旧接口。

## Evaluator Registry 减重方向

Evaluator registry 也应保持轻量。F1、LLM judge 这类 evaluator 应尽量作为通用 metric
入口存在。LoCoMo / LongMemEval 的差异优先通过以下内容表达：

- label schema。
- metric profile。
- judge prompt profile。
- 是否需要 API。

不再为每个 benchmark 复制一套过重的 evaluator 类，除非该 benchmark 的评分逻辑确实
无法用通用 metric profile 表达。

## 非目标

- 当前不把 registry 替换成二维兼容表。
- 当前不一次性删除所有 legacy base class。
- 当前不重写 evaluator 系统。
- 当前不改变真实实验运行结果和 artifact schema。

## 实施原则

1. 小步迁移，先测试后改代码。
2. registry 只保留映射和构造职责，不做复杂能力推理。
3. 新增 method 的用户文档只讲 `BaseMemoryProvider`。
4. 如果某处仍必须保留 capability 或 legacy 接口，必须在代码注释或文档中说明是迁移期兼容。
