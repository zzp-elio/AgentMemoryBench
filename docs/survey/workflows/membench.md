# MemBench 评测流程参考

> **一个 test sample / trajectory = 一条完整的待记忆信息流 + 一个最终 QA。**
> Participation 场景里，这条信息流来自多个 session/turn 展平后的 user-agent 对话；Observation 场景里，这条信息流是单向 message list，不是对话 session。
> 常规评测时，先把整条 trajectory 的 message 全部灌入 memory，再问一个多选题，比较选项 A/B/C/D 是否等于 ground_truth。reset 是按 trajectory 级别做，不是按 session 或 turn 做。

---

## 1. MemBench 的 dataset 到底是什么结构？

MemBench 不是一个单一形式的数据集，而是按两个维度拆成 4 类：

| 维度   | 类型                         | 含义                             |
| ---- | -------------------------- | ------------------------------ |
| 场景   | Participation / FirstAgent | agent 参与对话，数据是 user-agent 多轮对话 |
| 场景   | Observation / ThirdAgent   | agent 只观察用户信息流，数据是单向 messages  |
| 记忆层级 | Factual / LowLevel         | 记具体事实，例如生日、地点、时间、职业            |
| 记忆层级 | Reflective / HighLevel     | 从多个低层事实中总结偏好、倾向、画像             |

README 里对应的 4 个正式数据文件就是：

* `FirstAgentHighLevel`：Participation-Reflective
* `FirstAgentLowLevel`：Participation-Factual
* `ThirdAgentHighLevel`：Observation-Reflective
* `ThirdAgentLowLevel`：Observation-Factual


论文也明确说，MemBench 的数据由两部分组成：一部分是 500 个用户关系图，另一部分是用户-助手对话、用户消息流，以及对应 questions；统计表里也把 PS-RM、PS-FM、OS-RM、OS-FM 分开统计。([ar5iv][1])

---

## 2. 你的“dataset → sample → session → turn → question”猜测哪里对，哪里不对？

更真实的层级应该这样理解：

```text
MemBench dataset
  └── question_type / ability_type
        └── scenario / subcategory
              └── trajectory sample
                    ├── message_list
                    └── QA
```

最终进入 benchmark 的不是原始 session 树，而是一个个 **trajectory sample**。代码的 `load_dataset()` 会把 JSON 中的层级结构打平成一个 `test_data` 列表，每个 `traj` 都会被 append 进去。

所以你可以把 **trajectory** 理解为 MemBench 真正的“样本单位”。

---

## 3. Participation 场景：确实有 session 和 turn，但评测前会展平成 message_list

Participation / FirstAgent 是 agent 参与对话的场景。论文说得很清楚：Participation 数据由很多 sessions 组成，每个 session 里有很多 dialogue turns；agent 需要同时记住 user message 和 agent response。([ar5iv][1])

代码生成 FirstAgent 数据时，也能看到 session 结构。比如 `CoupleSimple.py` 里，一个 graph 会生成多个 session，每个 session 里有多轮 `user_message` 和 `assistant_message`，并带有 `time`、`place`、`target_step_id`、`question` 等字段。 

但是重点来了：**评测用的数据不是直接一层层 session 跑，而是被处理成一条扁平 message_list。**

`MakeNoiseSession()` / `infuse_single_trajectory_session()` 会遍历原始 `message_list` 里的 session，再遍历 session 内的 turn，把每个 turn 转成：

```python
{
  "user": "...",
  "agent": "..."
}
```

也就是说，最终送进环境的是一个展平后的 user-agent turn 序列。

所以 Participation 最准确的说法是：

```text
raw data: 多个 session，每个 session 多个 turn
test data: 展平成一个 trajectory.message_list
每个元素是 {"user": ..., "agent": ...}
```

---

## 4. Observation 场景：不是 session-turn 对话，而是 message flow

Observation / ThirdAgent 不是 agent 和 user 对话。论文说它是 agent 作为 observer，被动接收用户输入的 message flow，不需要行动，只需要记录用户表达的信息。([ar5iv][1])

代码里也对应这个设计。ThirdAgent 的低层数据生成出来是 `message_list`，每条 message 有 `message`、`time`、`place`、`attr`、`value` 等信息，不是 user-agent pair。 

最终在 `MakeNoiseMessage()` 里，Observation 的每条 message 会被整理成字符串：

```python
"{message} (place: ...; time...)"
```

并放进 `noisy_traj["message_list"]`。

所以 Observation 最准确的说法是：

```text
trajectory.message_list = [message1, message2, message3, ...]
```

它不是：

```text
session -> turn -> user/assistant
```

这一点你之前的猜测要改。

---

## 5. question 是每个 turn 都有吗？不是

常规 MemBench accuracy 评测里，**每个 trajectory 最终对应一个 QA**。

环境 `step()` 的逻辑非常清楚：

1. 先依次返回 `message_list` 里的每条 message；
2. 当 message 全部返回完之后，才返回一个 question；
3. 再下一步，用 agent 的 response 和 `QA["ground_truth"]` 比较。

核心逻辑是：

```python
if current_step - 1 < len(message_list):
    return message
elif current_step - 1 == len(message_list):
    return question, time, choices
elif current_step - 1 == len(message_list) + 1:
    compare response with ground_truth
```

所以常规流程不是每个 turn 问一个问题，也不是每个 session 问一个问题，而是：

```text
一条 trajectory 的全部记忆输入完
  ↓
问一个 QA
  ↓
算 accuracy
```

不过有一个特殊例外：**capacity evaluation**。`step_cap()` 会在关键 evidence 出现之后，从某个位置开始反复带着同一个 question 测准确率，用来观察 token 数增加后记忆是否崩掉。这个不是普通 accuracy 评测，而是 memory capacity 曲线测试。

---

## 6. QA 的结构是什么？

最终评测用的 QA 大概长这样：

```json
{
  "question": "...",
  "answer": "...",
  "target_step_id": [...],
  "choices": {
    "A": "...",
    "B": "...",
    "C": "...",
    "D": "..."
  },
  "ground_truth": "C",
  "time": "..."
}
```

生成代码里可以看到 question 会被转成多选题，并保存 `choices` 和 `ground_truth`。例如 ThirdAgent factual 的生成代码中，`question_list` 里包含 `question`、`answer`、`target_step_id`、`choices`、`ground_truth`、`time`。

Participation 生成代码也类似，每个 session 会生成 question_json，包括 `question`、`answer`、`target_step_id`、`choices`、`ground_truth`、`time`。

这里 `target_step_id` 很重要。它不是给模型看的标准答案，而是用来算 retrieval recall 的 evidence index。

---

## 7. MemBench 到底要求 method 返回 answer，还是返回 memory？

严格说：**官方 benchmark 最终需要 answer，也就是 A/B/C/D 选项。**

论文也说明，为避免自由表达带来的误判，所有 questions 都设置成多选题，memory accuracy 通过比较 agent 选择的选项和真实选项来计算。([ar5iv][1])

代码里也一样，环境最终比较的是：

```python
action["response"] == QA["ground_truth"]
```



但是，MemBench 也可以额外评估 memory retrieval。`action` 里如果包含 `memory_index`，环境会用它和 `QA["target_step_id"]` 算 recall。

所以它不是纯粹的“只返回 memory”。更准确是：

```text
必须返回：response = A/B/C/D
可选返回：memory_index = 检索到的证据 step id 列表
```

官方 `MemBenchAgent` 的流程也是：先调用 memory.recall(question)，把召回的 memory 塞进 prompt，让 LLM 输出 A/B/C/D；然后再调用 memory.retri(question) 拿 memory index，用于 recall 评估。

---

## 8. method 侧最少需要什么接口？

从官方 memory 抽象看，memory module 至少定义了这些接口：

```python
reset()
store(observation)
recall(observation)
retri(observation)
manage()
train()
```



但如果你是为了复现 MemBench 的核心评测，真正关键的是这 4 个：

```text
reset()
store(message)
recall(question)
retri(question)   # 可选，用于 recall metric
```

官方 agent 里确实是这么调用的：

* 每来一条 message，就 `memory.store(...)`
* 来 question 时，`memory.recall(question + time)`
* 如果要算 recall，再 `memory.retri(question + time)`
* 每条 trajectory 开始前，`memory.reset()`
    

---

## 9. 最真实的常规评测流程

用你的话说，MemBench 的真实流程应该是这样：

```text
for each dataset_file in selected MemBench subsets:
    load data
    flatten into test_data = [trajectory_1, trajectory_2, ...]

    for each trajectory_i:
        env.reset(trajectory_i)
        agent.reset() / memory.reset()

        # 1. 灌入记忆
        for step, message in trajectory_i.message_list:
            observation = env.step(...)
            agent.response(observation)
                if Participation:
                    memory.store("step[|]'user': ...; 'agent': ...")
                if Observation:
                    memory.store("step[|]message ...")

        # 2. 问题阶段
        observation = env.step(...)
        # observation contains:
        # question, time, choices

        memory_context = memory.recall(question + time)
        answer = reader_llm(memory_context, question, choices)
        memory_index = memory.retri(question + time)  # optional

        # 3. 评分
        env.step({
            "response": answer,
            "memory_index": memory_index
        })

        score accuracy = answer == ground_truth
        score recall = overlap(memory_index, target_step_id)
        record read_time / write_time
```

官方 prompt 要求模型只输出一个选项字母，不要输出解释。 

---

## 10. reset 的时机到底是什么？

你的直觉是对的：reset 时机非常重要。

在 MemBench 里，**reset 应该发生在每个 trajectory/sample 开始前**。

不应该：

```text
每个 turn reset
每个 session reset
question 前 reset
```

如果你在 session 之间 reset，就把跨 session 记忆能力破坏掉了；Participation 数据本来就有跨 session/多 session 的设计，论文也说 timestamp 在 session 内连续，session 之间保持时间顺序但间隔更长。([ar5iv][1])

所以正确 reset 策略是：

```text
trajectory_i 开始：
    reset memory

trajectory_i 内：
    不 reset
    持续 store 所有 message / turn

trajectory_i 的 QA 结束：
    记录结果

trajectory_{i+1} 开始：
    reset memory
```

这个和环境代码一致：`reset(traj_i)` 会把 `current_step` 置 0，并把当前任务设为 `dataset[traj_i]`。

---

## 11. 你可以怎么把 MemBench 接到自己的统一 memory framework？

我建议你不要把 MemBench 强行理解成“benchmark 直接问 method 要答案”，也不要理解成“benchmark 只评 memory”。它实际是一个 **memory module + reader LLM** 的组合评测：

```text
MemoryMethod:
    reset()
    ingest/store(event)
    retrieve/recall(query)
    retrieve_indices(query) optional

Reader:
    answer(memory_context, question, choices) -> A/B/C/D
```

然后 MemBench 的 metrics 是：

```text
accuracy = Reader 最终选项是否正确
recall = MemoryMethod 检索到的 evidence step 是否覆盖 target_step_id
efficiency = store / recall 的平均时间
capacity = token 增长后 accuracy 是否断崖式下降
```

论文里也明确说 MemBench 评估四个方面：accuracy、recall、capacity、temporal efficiency。([ar5iv][1])

所以如果你要统一 6 个 benchmark，我会把 MemBench 适配成：

```python
class MemoryMethod:
    def reset(self): ...
    def ingest(self, event): ...
    def retrieve(self, query): ...
    def retrieve_with_ids(self, query): ...  # optional

class BenchmarkReader:
    def answer(self, retrieved_memory, question, choices): ...
```

但是注意，**MemBench 官方代码里 `MemBenchAgent` 把 memory 和 reader LLM 包在一起了**。工程上你可以拆开，但论文里要说清楚：这是你们统一框架的抽象，不是 MemBench 原仓库原生 API 完全长这样。

[1]: https://ar5iv.org/html/2506.21605v1 "[2506.21605] MemBench: Towards More Comprehensive Evaluation on the Memory of LLM-based Agents"
