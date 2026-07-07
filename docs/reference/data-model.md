⚠ **2026-07-07 核查：本文描述的 Dataset → Conversation → Session → Turn 层级仍是 benchmark adapter 的规范数据模型（v3 spec §1 确认为"三层同构"），但未涵盖 v3 协议新增的 TurnEvent 事件流表示与 IsolationUnit 隔离模型，待 ws03 补全。**

# 数据模型

统一数据模型用于把不同 conversation + QA benchmark 转成同一套 Python 对象。

```text
Dataset
└── Conversation
    ├── Session
    │   └── Turn
    ├── Question
    └── GoldAnswerInfo
```

## Conversation

`Conversation` 是隔离粒度。一个问题只能基于同一个 `conversation_id` 下的历史回答。

LoCoMo 中，一个 sample 对应一个 `Conversation`。LongMemEval 中，一条 evaluation instance 对应一个 `Conversation`。

## Session

`Session` 是历史对话的一段自然边界。它可以有 `session_time`，也可以缺时间。缺时间只有在 benchmark 本身不提供时间时才允许。

## Turn

`Turn` 是一次单方发言：

```text
speaker: content
```

一个 user + assistant round 应拆成两个 `Turn`。这样 speaker、role、时间和图片都能在最小粒度上调试。

## Question

`Question` 是公开问题，只包含 method 回答所需的信息。`question_time`、`category`、`options` 都是可选字段；如果某个 benchmark 的评测流程要求它们存在，adapter 或 runner 必须做强校验。

## GoldAnswerInfo

`GoldAnswerInfo` 保存 evaluator 私有信息。它和 `Question` 通过 `question_id` 对齐。

禁止进入 method 的信息包括：

- 标准答案。
- evidence id。
- judge label。
- benchmark 私有评分标签。

## Metadata

`metadata` 用于保留公开、可调试、但不值得升格为核心字段的信息。新字段是否进入核心层的判断标准是：是否被多个 benchmark 稳定复用，且是否会影响统一 runner 的行为。
