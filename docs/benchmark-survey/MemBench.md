# MemBench Benchmark 调研卡片

更新日期：2026-06-29

## 1. 一句话结论

MemBench 是一个面向 **LLM-based personal agent memory** 的 **message-stream / conversation-stream + multiple-choice QA** benchmark。它按时间顺序输入用户消息流或 user-agent 对话流，让 method 增量写入记忆，最后给一个带 A/B/C/D 选项的问题，用 Accuracy 评估最终选择，并可用 gold `target_step_id` 评估 retrieval recall。

它比 LoCoMo 更接近“trajectory 环境”：每个 `tid` 是一条独立评测样本，`message_list` 是需要逐步写入的 memory stream，`QA` 是最终测试问题。当前 `add + retrieve` 架构可以覆盖它，但必须保证 **tid namespace 隔离** 和 **retrieved source step id provenance**；否则 Recall 无法计算，且不同 trajectory 会互相污染。

## 2. Dataset 数据结构

### 2.1 本地材料与核心数据

| 类型 | 路径 / 来源 | 调研结论 |
| --- | --- | --- |
| 官方仓库 | `/Users/wz/Desktop/memoryBenchmark/third_party/benchmarks/Membench-main` | 包含环境、agent、memory 抽象、原始 MemData 和生成脚本。 |
| 论文 PDF | `/Users/wz/Desktop/memoryBenchmark/third_party/benchmarks/Membench-main/Tan 等 - 2025 - MemBench Towards More Comprehensive Evaluation on the Memory of LLM-based Agents.pdf` | 定义 participation/observation、factual/reflective、accuracy/recall/capacity/efficiency。 |
| 本地评测数据 | `/Users/wz/Desktop/memoryBenchmark/data/membench/Membenchdata/data2test` | 真正评测层数据，包含 0-10k 与 100k 长度版本。 |
| 官方 env | `/Users/wz/Desktop/memoryBenchmark/third_party/benchmarks/Membench-main/benchmark/env/Membenenv.py` | 逐步返回 message，最后返回 question/time/choices，并用 action 计算 accuracy/recall。 |
| 官方 agent | `/Users/wz/Desktop/memoryBenchmark/third_party/benchmarks/Membench-main/benchmark/MembenchAgent.py` | 将 message 写入 memory，question 阶段 recall + prompt + LLM 输出选择。 |

### 2.2 本地 data2test 文件与规模

本地 `data2test` 是评测层 trajectory 数据。直接统计如下：

| 文件 | Trajectories | question types | message 类型 | message_list 长度范围 |
| --- | ---: | --- | --- | --- |
| `0-10k/FirstAgentDataHighLevel_multiple_0.json` | 700 | `highlevel`, `highlevel_rec` | dict(user+agent) | 8-44 |
| `0-10k/FirstAgentDataLowLevel_multiple_0.json` | 900 | `simple`, `conditional`, `comparative`, `aggregative`, `post_processing`, `knowledge_update`, `lowlevel_rec`, `RecMultiSession`, `noisy` | dict(user+agent) | 13-193 |
| `0-10k/ThirdAgentDataHighLevel_multiple_0.json` | 400 | `highlevel` | string | 6-23 |
| `0-10k/ThirdAgentDataLowLevel_multiple_0.json` | 1400 | `simple`, `conditional`, `comparative`, `aggregative`, `post_processing`, `noisy`, `knowledge_update` | string | 4-36 |
| `100k/FirstAgentDataHighLevel_multiple_100.json` | 140 | `highlevel`, `highlevel_rec` | dict(user+agent) | 309-341 |
| `100k/FirstAgentDataLowLevel_multiple_100.json` | 360 | `simple`, `conditional`, `comparative`, `aggregative`, `post_processing`, `knowledge_update`, `lowlevel_rec`, `RecMultiSession`, `noisy` | dict(user+agent) | 313-491 |
| `100k/ThirdAgentDataHighLevel_multiple_100.json` | 80 | `highlevel` | string | 307-321 |
| `100k/ThirdAgentDataLowLevel_multiple_100.json` | 280 | `simple`, `conditional`, `comparative`, `aggregative`, `post_processing`, `noisy`, `knowledge_update` | string | 303-336 |
| `ThirdAgentDataHighLevel_multiple_100.json` | 20 | `Emotion`, `Preference` | string | 309-319 |

0-10k 主文件合计 3400 trajectories；100k 主文件合计 860 trajectories。根目录额外 20 条小文件应作为补充/异常变体处理，不能和主 0-10k/100k 混淆。

### 2.3 顶层 JSON 结构

每个 data2test JSON 大致是：

```json
{
  "<question_type>": {
    "<scenario_or_role>": [
      {
        "tid": "...",
        "message_list": [...],
        "QA": {
          "qid": 0,
          "question": "...",
          "answer": "...",
          "target_step_id": [1, 3],
          "choices": {"A": "...", "B": "...", "C": "...", "D": "..."},
          "ground_truth": "A",
          "time": "'2024-10-01 08:13' Tuesday"
        }
      }
    ]
  }
}
```

一个 trajectory 的核心是：

```text
tid + message_list + QA
```

| 字段 | 是否给 method | 含义 |
| --- | --- | --- |
| `tid` | 是 | trajectory id。每个 tid 必须独立评测或用 namespace 隔离。 |
| `message_list` | 是 | 按时间顺序逐条写入 memory 的输入流。 |
| `QA.question` | 是 | 最终问题。 |
| `QA.time` | 是 | 提问时刻，应拼到 query/prompt 中。 |
| `QA.choices` | 是 | A/B/C/D 选项。 |
| `QA.ground_truth` | 否 | 正确选项字母，只给 scorer。 |
| `QA.answer` | 否 | 正确答案文本，只用于分析/说明，不给 method。 |
| `QA.target_step_id` | 否，除非计算 scorer | gold evidence step id，用于 retrieval recall。 |

### 2.4 Participation / FirstAgent message

FirstAgent 表示 Participation Scenario。`message_list` 中每个 step 是 dict：

```json
{
  "user": "I really love The Godfather...",
  "agent": "I'm glad to hear that..."
}
```

写入 method 时应保留：

```text
tid
step_id
user message
predefined agent response
```

注意：PS 不是让 method 现场生成 agent response；agent response 已经是数据集预定义内容，method 只负责把 user+agent 对话写入 memory。

### 2.5 Observation / ThirdAgent message

ThirdAgent 表示 Observation Scenario。`message_list` 中每个 step 是 string：

```json
"My subordinate is Maya Carter. (place: Boston, MA; time'2024-10-01 08:00' Tuesday)"
```

写入 method 时应保留：

```text
tid
step_id
user message string
```

OS 不是对话，而是用户单方面消息流。

### 2.6 step_id / target_step_id

`step_id` 是当前 `tid` 内 `message_list` 的局部下标。官方 env 返回的 `info["step_id"]` 从 1 开始递增，但 `QA.target_step_id` 指向的是当前 trajectory 内的 source step id。接入时建议内部统一生成：

```text
event_id = f"{tid}:{step_id}"
```

但计算 MemBench recall 时必须映射回当前 tid 内的 local `step_id`，不能使用 method 内部 memory id。

## 3. Evaluation 流程

### 3.1 普通 trajectory 流程

官方 `MemBenchEnv.step()` 的普通流程：

```text
reset(traj_i)
-> 返回 INITIAL_INSTRUCTION

for each message in message_list:
    step() 返回 {"message": current_message}
    agent 写入 memory

step() 返回 {"question", "time", "choices"}
    agent recall/retri memory
    answer LLM 输出 A/B/C/D

step(action) 比较 action["response"] 和 QA.ground_truth
    如果 action 有 memory_index，则和 QA.target_step_id 算 recall
```

### 3.2 Participation / PS 流程

官方 `MemBenchAgent.response()` 中，如果 `observation["message"]` 是 dict：

```python
self.memory.store(f"{step}[|]'user': {user}; 'agent': {agent}")
action = {"response": observation["message"]["agent"]}
```

也就是说：

```text
add(tid, step_id, "'user': ...; 'agent': ...")
```

question 阶段：

```python
memory_context = self.memory.recall(f"{question} ({time})")
memory_id = self.memory.retri(f"{question} ({time})")
```

再用 `INSTRUCTION_FIRST` 让 Answer LLM 选 A/B/C/D。

### 3.3 Observation / OS 流程

如果 `observation["message"]` 不是 dict：

```python
self.memory.store(f"{step}[|]{message}")
action = {"response": "No Need Reply"}
```

也就是说：

```text
add(tid, step_id, user_message)
```

question 阶段官方 active code 仍使用 `INSTRUCTION_FIRST`，但仓库中保留了更适合 OS 的 `INSTRUCTION_THIRD`。实现时应记录 prompt profile；如果严格复刻当前代码，用 active path 的 `INSTRUCTION_FIRST`。

### 3.4 Capacity 流程

官方 `step_cap()` 不是新的 QA 类型，而是容量曲线流程：

```text
先输入到最后一个 target_step_id
从 target_step_id 出现后开始反复问同一个 QA
继续输入后续 message
记录 (token_count, correct_or_not)
```

最终可以画：

```text
x-axis: memory token count
y-axis: accuracy
```

### 3.5 tid 隔离

MemBench 必须按 trajectory / tid 隔离：

```python
add(tid, event)
retrieve(tid, query)
```

可以物理 reset，也可以同一个 store 用 metadata namespace，但 `retrieve` 必须只检索当前 tid。否则不同 trajectory 的 evidence 会互相污染，Accuracy 和 Recall 都无效。

## 4. Metric 计算方式

### 4.1 Memory Accuracy

所有问题是 multiple-choice：

```python
correct = int(pred_choice == QA["ground_truth"])
accuracy = correct_count / total_count
```

官方 env 直接比较：

```python
correct = action["response"] == self.task_info["QA"]["ground_truth"]
```

不需要 Judge LLM。

### 4.2 Memory Recall

如果 action 包含 `memory_index`，官方 env 会计算：

```python
recall = len(set(retrieved_step_ids) & set(target_step_id)) / len(set(target_step_id))
```

官方函数 `get_recall(res, std)` 会先去重 retrieved ids，再计算命中 target step ids 的比例。

这个 recall 是 retrieval-level evidence recall，不是最终 answer recall；它要求 method 返回的 retrieved source ids 能映射回原始 `message_list` step id。

### 4.3 Memory Capacity

Capacity 是观察 Accuracy 随 memory content 增长是否下降，不是单独问题类型。

官方 `step_cap()` 输出单条记录：

```python
(token_count, correct_or_not)
```

最终按 token_count 分桶或画曲线。

### 4.4 Memory Efficiency

官方 `MemBenchAgent` 记录：

```python
self.write_time.append(time_02 - time_01)
self.read_time.append(time_04 - time_03)
```

对应论文中的：

| 指标 | 含义 |
| --- | --- |
| WT | mean write time per memory store operation |
| RT | mean read time per recall/retrieve operation |

我们框架可扩展记录 write latency、read latency、answer LLM tokens、retrieved context tokens，但原始 MemBench 主要报告 RT / WT。

## 5. Answer LLM / Judge LLM 配置和 Prompt

### 5.1 Judge LLM

MemBench 原始评测不需要 Judge LLM。原因是所有问题都是 multiple-choice，最终只比较 A/B/C/D：

```python
pred_choice == ground_truth
```

### 5.2 Answer LLM

官方 agent 通过：

```python
self.llm = create_LLM(config["LLM_config"])
```

创建 Answer LLM。论文实验中，作者基于 MemEngine 实现 memory mechanisms，并使用 Qwen2.5-7B 作为 agent application base model；涉及 retrieval 的方法使用 multilingual-e5-small 做 retrieval。具体运行以 config 为准。

### 5.3 Prompt

官方 `benchmark/MembenchAgent.py` 定义两个 prompt：

| Prompt | 适用语义 | 关键变量 |
| --- | --- | --- |
| `INSTRUCTION_FIRST` | Participation / first-person：基于 “your conversation with the user” | `{memory}`、`{time}`、`{question}`、`{choice_A/B/C/D}` |
| `INSTRUCTION_THIRD` | Observation / third-person：基于 “the user's messages” | 同上 |

当前 active response path 使用 `INSTRUCTION_FIRST` 构造 prompt，并用 JSON schema 要求 LLM 输出：

```json
{"choice": "A"}
```

`choice` 枚举为 `A/B/C/D`。如果实现自己的 reader，建议保留 JSON schema；不支持 schema 时退化为“只输出 A/B/C/D”。

## 6. Method Adapter 接口需求

### 6.1 官方 Agent / Memory 接口

官方 Agent 抽象：

```python
class BaseAgent:
    def reset(self): ...
    def response(self, observation, reward, terminated, info): ...
    def train(self, env): ...
```

官方 Memory 抽象：

```python
class BaseMemory:
    def reset(self): ...
    def store(self, observation): ...
    def recall(self, observation): ...
    def retri(self, observation): ...
    def manage(self): ...
    def train(self, **kwargs): ...
```

官方 `response()` 混合了写入、检索、answer LLM 和 action 返回；不适合作为我们框架的统一 method 接口。

### 6.2 推荐统一接口

对我们框架，MemBench 最稳抽象是：

```python
add(tid: str, event: MemoryEvent) -> None
retrieve(tid: str, query: str) -> RetrievalResult
```

推荐数据结构：

```python
@dataclass
class MemoryEvent:
    tid: str
    step_id: int
    content: str
    role: str  # "dialogue_turn" or "user_message"
    user: str | None = None
    assistant: str | None = None
    timestamp: str | None = None
    metadata: dict | None = None
```

```python
@dataclass
class RetrievalResult:
    text: str
    retrieved_source_step_ids: list[int]
    items: list[dict] | None = None
```

关键契约：

- `retrieve(tid, query)` 只能查当前 `tid` 的 memory。
- `retrieved_source_step_ids` 必须是原始 `message_list` 的 local step id。
- `QA.ground_truth`、`QA.answer`、`QA.target_step_id` 只能给 scorer。

### 6.3 与当前 `add + retrieve` 的关系

MemBench 可以很好地映射到当前轻量协议：

| MemBench | 我们框架 |
| --- | --- |
| `memory.store(observation)` | `add(tid, event)` |
| `memory.recall(observation)` | `retrieve(...).text` |
| `memory.retri(observation)` | `retrieve(...).retrieved_source_step_ids` |
| `MemBenchAgent` answer LLM | framework answer reader |
| `MemBenchEnv` scorer | evaluator |

也就是说，MemBench 不需要 method 实现完整 agent；method 只需实现 memory module 写入与检索。Answer LLM 和 multiple-choice parsing 可以放在 framework reader。

## 7. 未确认项

1. 当前 active code path 对 Observation/ThirdAgent 仍使用 `INSTRUCTION_FIRST`，虽然仓库中有 `INSTRUCTION_THIRD`。如果严格复刻 GitHub，按 active path；如果按语义优化，Observation 应使用 Third prompt。需要 profile 决策。
2. `data2test/ThirdAgentDataHighLevel_multiple_100.json` 根目录额外 20 条样本与 `100k/` 下主文件不同，后续实现 loader 时需要明确它是否纳入默认评测。
3. 官方 `step_id` 在 env 中从 1 开始递增，`target_step_id` 来自数据构造层；实现 recall 前必须抽样确认 indexing 对齐，避免 off-by-one。
4. 论文中的 capacity/efficiency 需要额外运行模式；普通 accuracy/retrieval recall 不自动覆盖完整 capacity curve。
5. MemBench 原始数据构造层 `MemData/` 与评测层 `data2test/` 不同；接入时应默认使用 `data2test`，不要把构造层文件当作 evaluation split。
