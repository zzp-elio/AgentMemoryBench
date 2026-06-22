# A-Mem / MemoryOS LongMemEval 接入设计

## 背景

当前框架已经迁移到 retrieve-first 主链路：method 负责
`add(conversation) + retrieve(question)`，并在 `retrieve()` 中返回完整
`AnswerPromptResult.prompt_messages`；framework answer LLM 只负责按这些 role
messages 生成最终答案。

Mem0 和 LightMem 的第三方仓库提供了 LongMemEval 评测脚本或 prompt。A-Mem 和
MemoryOS 的第三方仓库没有 LongMemEval 评测脚本，但 LightMem 论文 Table 2 报告了
A-Mem 和 MemoryOS 在 LongMemEval-S 上的结果，说明它们可以通过额外 baseline glue
接入 LongMemEval。

本设计目标不是声称复现 LightMem 作者未公开的 baseline glue，而是在公开代码可审计的
前提下，让 A-Mem 和 MemoryOS 以 LongMemEval-compatible 方式运行，并尽量贴近
LightMem 论文中的 LongMemEval reader 风格。

## 数据口径

LongMemEval 和 LoCoMo 在统一数据模型里都可以表示为：

```text
Conversation
  -> Session(session_time)
      -> Turn(speaker/content)
  -> Question
```

LongMemEval 的映射规则：

- `haystack_sessions[i]` -> `Session.turns`
- `haystack_dates[i]` -> `Session.session_time`
- `question_date` -> `Question.question_time`
- `question_type` -> `Question.category`
- `has_answer`、`answer_session_ids`、`answer` 只进入 evaluator 私有标签，不能进入 method。

`haystack_dates` 不是额外接口，但必须传给 method 写入阶段。它影响 temporal
reasoning、knowledge update、recency 和长期记忆更新逻辑。

## A-Mem 接入策略

A-Mem 保留自身算法流程：

- 写入时仍按 turn 调用官方 robust `add_note()`。
- 写入文本仍包含 speaker 与 turn content。
- `Session.session_time` 继续传给 `add_note(..., time=...)`。
- 检索时仍先调用官方 query keyword generation。
- 检索上下文仍来自 `find_related_memories_raw()`，保留 memory content、context、
  keywords、tags 和 linked neighbor expansion。

LongMemEval 问题不再使用 LoCoMo/A-Mem 原始 short-answer prompt，而使用
LightMem-style LongMemEval reader：

```text
system: You are a helpful assistant.

user:
Question time:{question_time} and question:{question}
Please answer the question based on the following memories: {amem_memory_context}
```

适配条件：

- `Question.question_time` 必须非空。
- memory context 为空时显式写 `(No relevant memories found)`，不能静默给空 prompt。
- `answer_prompt_profile` 记录为 `lightmem_longmemeval_reader_v1`。
- `metadata` 保留 A-Mem 的 `query_keywords`、`retrieve_k`、`answer_context` 和 prompt
  profile，便于 debug。

## MemoryOS 接入策略

MemoryOS 保留自身算法流程：

- 写入时仍把 conversation 转成官方 eval 的 QA page。
- page timestamp 来自 `Session.session_time`。
- 短期记忆 STM、中期记忆 MTM、长期记忆 LPM、用户画像、assistant knowledge 和
  retrieval queue 的更新逻辑不改。
- 检索时仍调用官方 `retrieval_system.retrieve(...)`。

MemoryOS 的 LongMemEval reader 不能只塞 retrieval queue。必须把官方 LoCoMo eval prompt
中的核心上下文全部保留：

- recent short-term conversation window
- retrieved historical memory queue
- user profile
- long-term knowledge
- assistant knowledge / traits

这些内容会被组织成一个 structured memory context，然后放进 LightMem-style
LongMemEval reader：

```text
system: You are a helpful assistant.

user:
Question time:{question_time} and question:{question}
Please answer the question based on the following memories:

<CONTEXT>
...

<MEMORY>
...

<CHARACTER TRAITS>
...

<ASSISTANT KNOWLEDGE>
...
```

适配条件：

- `Question.question_time` 必须非空。
- MemoryOS 必须能从 LongMemEval conversation 中解析两个 speaker；通常为
  `user` / `assistant`。
- `answer_prompt_profile` 记录为 `lightmem_longmemeval_reader_v1`。
- `metadata["answer_context"]` 保留完整 structured memory context，用于 token
  observation 和 debug。

## Answer LLM 参数

A-Mem 和 MemoryOS 在 LongMemEval 上采用 LightMem LongMemEval 脚本中的 answer LLM
参数：

- model: 当前项目固定 `gpt-4o-mini`
- temperature: `0.0`
- top_p: `0.8`
- max_tokens: `2000`

这组参数只用于 framework answer LLM，不改变 method 内部 memory build/retrieval 使用的
LLM 参数。

## Judge 口径

LongMemEval judge 应改为官方 `src/evaluation/evaluate_qa.py` 的 task-specific prompt：

- 常规 QA 类别：判断 response 是否包含/等价于 correct answer。
- `temporal-reasoning`：允许 day/week/month 等 off-by-one。
- `knowledge-update`：允许包含旧信息，只要更新后的 required answer 正确。
- `single-session-preference`：按 rubric/personalization 判断。
- `_abs` abstention：判断模型是否正确拒答。

Judge LLM 参数：

- temperature: `0`
- max_tokens: `10`

当前 `LongMemEvalJudgeEvaluator` 的简化 prompt 只作为旧实现事实，不再作为目标口径。

## 验证范围

第一步只做离线/fake 单元测试与极小真实 smoke 的准备：

- A-Mem LongMemEval prompt 包含 question time、question、memory context、query keywords
  metadata。
- MemoryOS LongMemEval prompt 包含 question time、question、short-term context、
  retrieval queue、user profile、long-term knowledge 和 assistant knowledge。
- A-Mem / MemoryOS LongMemEval answer LLM settings 与 LightMem LongMemEval 一致。
- LongMemEval judge prompt 对不同 question type 使用官方 task-specific 文本。

真实 API smoke 需用户确认 run id 和规模后再运行。
