# HaluMem 评测流程参考

** README 和数据卡都说明每个 user JSON 对象包含 `uuid/persona_info/sessions`，每个 session 包含 `dialogue/memory_points/questions` 等字段；Halu-Medium 有 20 个 user、平均每 user 约 70 个 sessions，Halu-Long 平均约 120 个 sessions。([Hugging Face][1]) 

## 1. HaluMem 的 dataset 层级到底是什么？

可以理解成：

```text
HaluMem dataset
└── user_1  一行 JSONL，一个虚拟用户
    ├── uuid
    ├── persona_info
    └── sessions
        ├── session_1
        │   ├── start_time / end_time
        │   ├── dialogue
        │   │   ├── utterance: user
        │   │   ├── utterance: assistant
        │   │   └── ...
        │   ├── memory_points
        │   ├── questions  可选
        │   └── dialogue_token_length
        ├── session_2
        └── ...
└── user_2
└── ...
```

所以你说“每个 dataset 有多个样本，每个样本有多个 session”基本可以改成：

> **每个 dataset 有多个 user-level samples；每个 user sample 里有多个 session；每个 session 是一段多轮 user-assistant 对话。**

这里最容易误会的是 `turn`。README 里的 dialogue 示例是一个 list，里面每条是一个 utterance，字段包括 `role/content/timestamp/dialogue_turn`；示例里 user 和 assistant 两条 utterance 都是 `dialogue_turn: 0`，所以它更像是“第 0 轮交互里的一问一答”，但在 JSON 里是两条独立 utterance。([Hugging Face][1])

## 2. question 是在哪里出现的？每个 turn 都有吗？

不是每个 turn 都有。**question 是 session 级别字段**，也就是某个 session 下面可能有 `questions`。README 说 session 包含 `questions`，用于 memory reasoning and evaluation；QA 结构里有 `question/answer/evidence/difficulty/question_type`。([Hugging Face][1])

更准确地说：

```text
session
├── dialogue：这段对话内容
├── memory_points：这段对话应该产生的标准记忆点
└── questions：基于记忆点生成的问题，可选
```

代码也验证了这一点：评测脚本在处理每个 session 时，会先把 session 的 dialogue 加入 memory system，然后判断 `if "questions" not in session`，没有问题就直接进入下一个 session；有问题才逐个 question 检索记忆并生成回答。

所以不是：

```text
turn -> question
turn -> question
turn -> question
```

而是：

```text
session_1 dialogue -> add memory -> 可能没有 question
session_2 dialogue -> add memory -> 可能有若干 questions
session_3 dialogue -> add memory -> 可能没有 question
...
```

## 3. method 侧到底被当成什么？memory module 还是 end-to-end QA system？

HaluMem 比较特殊，它既看 memory module，也看 end-to-end QA，但在代码实现里分成两步：

第一步，memory system 负责：

```text
add dialogue
extract / update internal memories
search / retrieve memories
```

第二步，benchmark 脚本拿检索出来的 memory context，再用一个 LLM prompt 生成最终 answer。

以 `eval_memzero.py` 为例，流程是：

```python
client.add(dialogue, user_id=user_name, timestamp=session_start_time)
client.search(query=qa["question"], user_id=user_name, top_k=top_k)
llm_request(PROMPT_MEMZERO.format(context=context, question=qa["question"]))
```

也就是说，**Mem0 这类 memory system 本身不直接回答最终 question；它先返回 memories，HaluMem 的 eval 脚本再组织 prompt，让 LLM 基于 memories 生成 `system_response`。** 代码里 `search_memory` 返回 `context, memories, duration_ms`，随后用 `PROMPT_MEMZERO` 把 `context + question` 塞给 LLM，得到 `system_response`。 

但从最终评分角度，HaluMem 又会评估这个 `system_response`，所以结果表里有 QA Correct / Hallucination / Omission。README 也说 HaluMem 分成三类核心任务：Memory Extraction、Memory Updating、Question Answering。([GitHub][2])

你可以这样理解：

> **method 最小需要像 memory system 一样能 add dialogue、get extracted memories、search/retrieve memories；最终 QA answer 通常由 benchmark harness 调 LLM 生成，不一定要求 memory method 自己直接 answer。**

不过要注意：不同系统 wrapper 不完全一样。比如 Zep 因为没有完整的 Get Dialogue Memory API，所以不能算 memory extraction 相关指标；README 和 eval README 都明确提到这一点。([GitHub][2]) ([GitHub][3])

## 4. 真正的评测流程：按 user reset，而不是按 session reset

这是你最关心的点。**reset 的时机是每个 user 开始前，而不是每个 session 后。**

代码里 `process_user(user_data, ...)` 一开始会从 `persona_info` 提取用户名字，然后：

```python
client.delete_all(user_id=user_name)
```

这就是 reset。随后它按 session 顺序逐个灌入这个 user 的所有对话。

所以真实执行逻辑是：

```text
for each user:
    reset/delete_all(user_id)
    for each session in user.sessions in chronological order:
        add this session dialogue into memory system
        evaluate extraction for this session
        if this session has update memory:
            search updated memory
        if this session has questions:
            search memories by question
            generate answer using retrieved memories
    save this user's result
```

为什么不能每个 session reset？因为 HaluMem 要测长期记忆和更新能力。很多问题可能依赖前面 session 里写入的记忆，update 也要求新 session 覆盖旧记忆。如果每个 session 都 reset，你就把长期记忆任务毁掉了。

正确 reset 方式：

```text
user_1 开始前 reset
user_1 session_1 ingest
user_1 session_2 ingest
user_1 session_3 ingest
...
user_1 结束

user_2 开始前 reset
user_2 session_1 ingest
...
```

错误方式：

```text
session_1 ingest -> reset
session_2 ingest -> reset
session_3 ingest -> reset
```

这个会导致 HaluMem 的 update、multi-hop、dynamic update、memory conflict 等问题都失真。

## 5. 每个 session 进入 method 时，输入的是什么？

以 Mem0 wrapper 为例，它不是一条 utterance 一条 utterance 加，而是把整个 session 的 dialogue 转成：

```python
formatted_dialogue = [
    {"role": turn["role"], "content": turn["content"]}
    for turn in dialogue
]
```

然后一次性：

```python
client.add(
    message=formatted_dialogue,
    user_id=user_name,
    timestamp=session_start_time
)
```

也就是说：

> **HaluMem 的官方 eval wrapper 是 session-level ingest，不是 turn-level ingest。**

timestamp 用的是 `session["start_time"]` 转成 Unix timestamp，而不是每个 utterance 自己的 timestamp。代码里解析的是 `session["start_time"]`。

这个细节对你设计统一框架很重要：HaluMem 的 `MemoryEvent` 可以用 session 作为 ingest 单位；如果你内部想拆成 turn，也可以，但要知道官方 wrapper 是整段 session 加进去。

## 6. Memory Extraction 是怎么评的？

每个 session 都有 golden `memory_points`。memory system 在 `add dialogue` 后会返回它提取出的 memories：

```python
extracted_memories = [item["memory"] for item in result["results"]]
```

然后 scorer 做两类判断。

第一类叫 **Memory Integrity / Recall**：对每个 golden memory，看它是否被 extracted memories 覆盖。评分是 2/1/0，2 表示完整覆盖，1 表示部分覆盖，0 表示没覆盖或错误。评测 prompt 里明确写了这个 rubrics。 

第二类叫 **Memory Accuracy / Precision**：对每条 extracted memory，看它是否被当前 session 的 dialogue 或 golden memories 支持。如果候选记忆完全支持得 2，部分支持但带有 unsupported/contradictory 内容得 1，完全幻觉得 0。 

所以 extraction 不是简单字符串匹配，而是 LLM-as-judge 语义评分。

## 7. Memory Update 是怎么评的？

`memory_points` 里有两个关键字段：

```json
"is_update": "True",
"original_memories": [...]
```

如果某个 memory point 是更新型记忆，并且有原始记忆，脚本会用这条 updated memory 的内容作为 query 去 memory system 里 search 一下，取回系统当前认为相关的 memories：

```python
if memory["is_update"] == "False" or not memory["original_memories"]:
    continue

_, memories_from_system, duration_ms = search_memory(
    query=memory["memory_content"],
    top_k=10
)
memory["memories_from_system"] = memories_from_system
```

然后 scorer 对比三样东西：

```text
Generated Memories：系统检索出的 memories_from_system
Target Memory for Update：golden updated memory
Original Memory Content：被更新前的 original_memories
```

分类为：

```text
Correct
Hallucination
Omission
Other
```

代码就是这么调用的。 

这说明 HaluMem 的 update 不是问“最终回答对不对”，而是直接检查 memory system 里有没有正确的新记忆，以及旧记忆有没有被正确替换或标记过时。评测 prompt 也明确要求 generated memories 包含目标更新内容，并且 original memory 被有效替换或标记为 outdated。

## 8. QA 是怎么评的？

QA 流程分两步。

第一步，检索：

```python
context, _, duration_ms = search_memory(
    query=qa["question"],
    user_id=user_name,
    top_k=top_k
)
```

第二步，回答：

```python
prompt = PROMPT_MEMZERO.format(context=context, question=qa["question"])
response = llm_request(prompt)
new_qa["system_response"] = response
```

也就是说，**HaluMem 的 QA 不是把所有历史 dialogue 直接塞给模型，而是先让 memory system 检索相关 memories，再用检索结果回答问题。**

回答 prompt 里还规定了几个重要规则：根据 timestamp 判断最新事实；如果 memories 矛盾，优先最新 memory；答案要短，少于 5–6 个词。

最后 scorer 用：

```text
question
reference answer
evidence memory points
system_response
```

判断结果是：

```text
Correct
Hallucination
Omission
```

代码里 `evaluation_for_question` 就是这样调用的。 

## 9. 所以如果你有自己的 memory method，最真实的适配接口应该是什么？

你不要把 HaluMem 理解成“我给 method 一个 question，method 直接 answer”。更合理的统一接口是：

```python
class MemoryMethod:
    def reset(self, user_id: str):
        """清空这个 user 的历史记忆"""

    def ingest_session(self, user_id: str, dialogue: list[dict], timestamp: str | int):
        """
        输入一个完整 session 的 dialogue。
        返回本 session 新抽取出来的 memories。
        """

    def retrieve(self, user_id: str, query: str, top_k: int):
        """
        根据 question 或 updated memory query 检索相关 memories。
        """

    def answer(self, question: str, retrieved_memories: list[str]):
        """
        可选。
        如果你的 method 是完整 system，可以自己 answer；
        如果你只做 memory module，则 benchmark harness 用统一 reader LLM 来 answer。
        """
```

对 HaluMem 来说，最低限度其实是：

```text
reset(user)
ingest_session(user, dialogue, timestamp) -> extracted_memories
retrieve(user, query, top_k) -> retrieved_memories
```

`answer()` 可以放在 harness 侧，因为官方 eval 对 Mem0/MemOS/Memobase 这类系统就是“memory system retrieve + external LLM answer”的范式。

## 10. 一句话复盘你的原始猜测

你的猜测里正确的部分：

```text
dataset 有多个样本
样本里有多个 session
session 是对话
session 里有 user/assistant 多轮交互
灌入记忆后再根据 question 检索或回答
reset 时机很重要
```

需要修正的部分：

```text
1. HaluMem 的样本更准确说是 user，不是单个 QA 或单个 conversation。
2. question 是 session 级别的可选字段，不是每个 turn 后都有。
3. 官方 wrapper 是按 session 整体 ingest，不是每个 turn 单独 ingest。
4. reset 是每个 user 一次，不是每个 session 一次。
5. HaluMem 不只评 QA answer，还单独评 memory extraction 和 memory update。
6. QA answer 通常不是 memory method 直接产出，而是 benchmark 用检索到的 memories 再调用 LLM 生成。
```

最真实的 HaluMem 流程可以压缩成这个：

```text
读取 HaluMem-medium / HaluMem-long JSONL
for user in dataset:
    reset memory system for this user

    for session in user.sessions:
        ingest whole session dialogue into memory system

        collect extracted memories
        compare extracted memories with session.memory_points
        -> Memory Integrity / Memory Accuracy

        for update memory in session.memory_points:
            retrieve memories using updated memory as query
            compare retrieved memories with target updated memory and original memory
            -> Update Correct / Hallucination / Omission / Other

        for qa in session.questions if exists:
            retrieve memories using qa.question
            use retrieved memories + question to generate system_response
            compare system_response with qa.answer and qa.evidence
            -> QA Correct / Hallucination / Omission

aggregate all users
output extraction, update, QA, typewise accuracy, latency
```

这个 benchmark 对你们统一框架的启发很明确：**HaluMem 更适合把 method 当成“可检索、可更新、可检查内部状态的 memory system”，而不是只当成一个黑盒聊天机器人。**这点和很多只看 end-to-end QA accuracy 的 memory benchmark 不一样，也是它设计 HaluMem 的核心动机。

[1]: https://huggingface.co/datasets/IAAR-Shanghai/HaluMem "IAAR-Shanghai/HaluMem · Datasets at Hugging Face"
[2]: https://github.com/MemTensor/HaluMem "GitHub - MemTensor/HaluMem: HaluMem is the first operation level hallucination evaluation benchmark tailored to agent memory systems. · GitHub"
[3]: https://github.com/MemTensor/HaluMem/blob/main/eval/README.md "HaluMem/eval/README.md at main · MemTensor/HaluMem · GitHub"
