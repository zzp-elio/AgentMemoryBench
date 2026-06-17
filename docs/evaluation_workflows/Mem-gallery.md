# Mem-Gallery 评测流程参考

**Mem-Gallery 的评测单位不是“每个 turn 测一次”，也不是“每个 session 后测一次”。它的真实流程是：对每个 scenario JSON 文件，先 reset 一个 memory method，然后把这个 scenario 的所有 multi-session dialogues 全部按 round 灌入 memory，灌完以后，再遍历这个 scenario 下面的所有 QA，用 memory.recall 找相关记忆，再由 benchmark 的 MLLM backbone 生成最终 answer，最后和 ground-truth answer 计算指标。**

---

## 1. Dataset 到底长什么样？

Mem-Gallery 的数据不是一个简单的“样本列表”。它更像这样：

```text
Mem-Gallery dataset
└── data/dialog/
    ├── AI_Robotics_Automation_Future_Tech.json
    ├── Dog_Behavior_Research_Academic_Life.json
    ├── ...
    └── 共 20 个 scenario JSON
```

Hugging Face 页面明确说它有 **20 个 scenarios**，总共 **240 sessions、3962 dialogue rounds、1490 images**，平均每个 scenario 约 12 个 session，每个 session 约 16.51 个 round。([Hugging Face][1])

每个 JSON 大概是这种结构：

```json
{
  "character_profile": {...},
  "multi_session_dialogues": [
    {
      "session_id": "D1",
      "date": "2025-03-02",
      "dialogues": [
        {
          "round": "D1:1",
          "user": "...",
          "assistant": "..."
        },
        {
          "round": "D1:2",
          "user": "...",
          "assistant": "...",
          "image_id": ["D1:IMG_001"],
          "input_image": ["../image/...jpg"],
          "image_caption": ["..."]
        }
      ]
    }
  ],
  "human-annotated QAs": [
    {
      "point": "VR",
      "question": "...",
      "question_image": "...",
      "answer": "...",
      "session_id": ["D1"],
      "clue": ["D1:2"]
    }
  ]
}
```

真实样例里，一个文件先有 `character_profile`，例如用户叫 Evelyn；然后是 `multi_session_dialogues`；每个 session 有 `session_id`、`date`、`dialogues`；每个 dialogue round 里有 `round`、`user`、`assistant`，有些 round 还带 `image_id`、`input_image`、`image_caption`。([Hugging Face][2])

所以你的理解需要微调：

```text
一个 benchmark = 20 个 scenario JSON
一个 scenario JSON ≈ 一个长期用户/人物/主题的完整多 session 记忆样本
一个 scenario 里有多个 session
一个 session 里有多个 dialogue round
一个 dialogue round = user 说一句 + assistant 回一句，被代码合并成一个 memory event
一个 scenario 下面有一组 QA
一个 QA = 一个 evaluation instance
```

这里最容易混的地方是：**“sample”这个词不稳定**。从数据组织看，一个 JSON 文件更像一个长期记忆样本；从评测指标看，每个 QA 又是一个打分样本。你写论文/框架时最好明确叫：

```text
scenario-level sample：一个完整 JSON 文件
QA-level instance：一个具体问题
memory event：一个 dialogue round
```

---

## 2. session、turn、timestamp 的关系

代码里的 `process_conversation()` 明确按 session 遍历：

```python
for session_idx, session_data in enumerate(conversation_data):
    session_id = session_data.get("session_id", "")
    session_date = session_data.get("date", "")
    dialogues = session_data.get("dialogues", [])

    for dialog in dialogues:
        ...
```

然后它把每个 `dialog` 转成一个 memory 记录。注意：**它不是把 user 和 assistant 分成两个 turn 存，而是把 user + assistant 合并成一个 text 字段**：

```python
user (Evelyn): ...
assistant: ...
```

如果这个 round 有图，就加上 image path、caption、img_id；如果没图，image 就是 `None`。同时它把 `timestamp` 设置成 `session_date`，把 `dialogue_id` 设置成 `round`，比如 `D1:2`。

所以你问 timestamp 是 session 级还是 turn 级：**原始数据里 timestamp/date 是 session 级；但代码处理后，每个 turn/event 都会复制一份 session date 作为自己的 timestamp。**

也就是：

```text
D1 session date = 2025-03-02

D1:1 memory_event.timestamp = 2025-03-02
D1:2 memory_event.timestamp = 2025-03-02
D1:3 memory_event.timestamp = 2025-03-02
...
```

这其实是合理的，因为 retrieval/排序时 memory event 是最小存储粒度，但它继承了 session 的时间。

---

## 3. QA 是在哪里出现的？每个 session 后都有吗？

不是。

QA 在 JSON 里是一个单独字段：`human-annotated QAs`。代码直接这样取：

```python
conversation_data = dataset.get("multi_session_dialogues", [])
qa_pairs = dataset.get("human-annotated QAs", [])
```

也就是说，**对话数据和 QA 数据是并列的两块**，不是每个 turn 后面跟一个 question，也不是每个 session 后面马上跟一组 question。

每个 QA 里通常有：

```text
point/category：题目类型，比如 FR、VS、TR、VR、MR、KR、CD、AR
question：问题文本
question_image：可选，有些问题自己带图
answer：标准答案
session_id：这个问题主要关联哪些 session
clue：证据 turn id，比如 ["D4:10", "D4:11"]
```

真实数据里，QA 部分是放在所有 `multi_session_dialogues` 之后的。比如 `Dog_Behavior_Research_Academic_Life.json` 在对话结束后出现 `"human-annotated QAs"`，里面有 `point`、`question`、`question_image`、`answer` 等字段。([Hugging Face][2])

`clue` 很关键：它不是给模型看的标准答案，而是标注“这个问题的答案证据来自哪些 dialogue round”。代码在开启 retrieval metrics 时会拿 `clue` 和 method 检索到的 `retrieved_ids` 算 Precision/Recall/HitRate。

所以真实逻辑是：

```text
先给 method 看完整长期历史
再拿 QA 问它
QA 自己带 ground truth answer 和 evidence clue
```

不是：

```text
每个 turn 后问一次  ❌
每个 session 后清空再问  ❌
每个 session 后立刻问这个 session 的问题  ❌
```

---

## 4. Method 侧到底要返回 answer 还是 memory？

这是你最关心的点。

在仓库当前 `run_bench.py` 里，memory method **不是直接返回最终 answer**，而是作为 memory module 被调用：

```python
memory_context = memory_agent.memory_recall(question, observation_image)
system_answer = memory_agent.response(memory_context, question, speaker_a, speaker_b, ...)
```

也就是说：

```text
memory method.store(dialog)        # 存记忆
memory method.recall(question)     # 返回相关 memory_context
benchmark 的 VLM/MLLM response()   # 用 memory_context + question 生成 answer
```

代码里 `DialogueAgent.memory_recall()` 对多模态 memory 会把 `{text: question, image: question_image}` 传给 `memory.recall()`；对文本 memory，如果 question 有图，会把图 caption 拼到 question 里再 recall。

最终回答不是 memory method 直接生成的，而是 `DialogueAgent.response()` 调用 `VLMAgent` 生成的。对于多模态 memory，它会把检索到的 memory text + memory image 一起喂给 MLLM；对于文本 memory，它把 memory_context 拼成文本 prompt 再喂给 MLLM。

所以 Mem-Gallery 当前主流程的范式是：

```text
benchmark 把 method 当成 memory module
method 返回 retrieved memory/context
benchmark 负责组织最终 answer generation
```

不是：

```text
benchmark 直接拿 method.response(question) 的答案打分
```

但是要注意一个细节：`DialogueAgent` 这个 wrapper 里有 `response()` 函数，所以从外面看像是 agent 在回答。但真正 memory class 的核心接口还是 `reset/store/recall`。`BaseMemory` 抽象类还定义了 `manage/optimize`，但 `run_bench.py` 主评测流程实际只调用了 `reset()`、`store()`、`recall()`。

---

## 5. reset 的真实时机是什么？

真实代码里，`run_mm_bench()` 对每个 `data_name` 创建一个新的 `DialogueAgent`，然后立刻：

```python
memory_agent = DialogueAgent(...)
memory_agent.reset()
```

之后才开始灌入这个 scenario 的所有对话。

然后：

```python
for dialog in processed_dialogs:
    memory_agent.memory_store(dialog)
```

这一步是把该 scenario 的所有 session、所有 round 都灌进去。

接着才：

```python
for qa_idx, qa in enumerate(qa_pairs):
    memory_context = memory_agent.memory_recall(question, observation_image)
    system_answer = memory_agent.response(...)
```

也就是说：

```text
reset 一次
灌完整个 scenario 的所有 dialogue rounds
遍历这个 scenario 的所有 QA
这个 scenario 结束
下一个 scenario 再重新创建/重置 memory agent
```

当 `--all_datasets` 开启时，它会扫描 `data/dialog/*.json`，然后对每个 dataset/scenario 调一次 `run_mm_bench()`。 

因此 reset 策略应该是：

```text
不同 scenario 之间：必须 reset
同一个 scenario 的不同 session 之间：不能 reset
同一个 scenario 的不同 QA 之间：当前代码不 reset
```

这里有一个你必须意识到的坑：**当前代码不在 QA 之间 reset，所以如果你的 memory method 的 recall 会修改内部状态，那么 QA 顺序可能影响后续问题结果。**

比如 Generative Agent 风格的 memory 可能在 recall 时更新 recency。代码里的 `GAMemoryRecall` 就有 retention 逻辑，会更新被检索 memory 的 recency。

所以你如果设计自己的统一评测框架，我建议你明确规定：

```text
方案 A：recall 必须是 read-only，QA 之间不 reset。
方案 B：每个 QA 前复制一份 memory snapshot，避免 QA 顺序污染。
```

Mem-Gallery 当前仓库更接近方案 A，但它没有强制所有 method recall 纯只读，这是一个真实存在的公平性隐患。

---

## 6. 一条 dialogue 是怎么变成 memory event 的？

假设原始数据里有一个 round：

```json
{
  "round": "D2:2",
  "user": "Exactly! The first Sussex Spaniel we saw, named Rocky...",
  "assistant": "A perfect description! Sussex Spaniels...",
  "image_id": ["D2:IMG_001"],
  "input_image": ["../image/Dog_Behavior_Research_Academic_Life/D2_IMG_001.jpg"],
  "image_caption": ["Long-haired brown dog..."]
}
```

代码会变成：

```python
{
  "text": "user (Evelyn): Exactly! ...\nassistant: A perfect description! ...",
  "image": {
    "path": ".../benchmark/data/image/Dog_Behavior_Research_Academic_Life/D2_IMG_001.jpg",
    "caption": "Long-haired brown dog...",
    "img_id": "D2:IMG_001"
  },
  "timestamp": "2025-03-14",
  "dialogue_id": "D2:2"
}
```

如果是文本 memory method，代码不会保留原图，而是把 image caption 拼进 text：

```text
image:
image_id: D2:IMG_001
image_caption: Long-haired brown dog...
```

如果是多模态 memory method，它会把原始 image path 保留下来。这个逻辑在 `memory_store()` 里写得很清楚：`is_multimodal=True` 时直接 `store(message_dict)`；否则把图片 caption 拼进文本再 store。

所以 Mem-Gallery 对文本记忆和多模态记忆是两套输入策略：

```text
Textual memory：吃 user/assistant 文本 + image caption
Multimodal memory：吃 user/assistant 文本 + 原图 path + caption/img_id metadata
```

---

## 7. 具体评测全流程：从命令行到结果文件

真实执行可以抽象成这样：

```python
for data_name in datasets:  # 每个 scenario JSON
    dataset = load_json(data/dialog/{data_name}.json)

    memory_agent = DialogueAgent(memory_name, config)
    memory_agent.reset()

    character_profile = dataset["character_profile"]
    conversation_data = dataset["multi_session_dialogues"]
    qa_pairs = dataset["human-annotated QAs"]

    processed_dialogs = process_conversation(conversation_data)

    # 1. 写入记忆
    for dialog_event in processed_dialogs:
        memory_agent.memory_store(dialog_event)

    # 2. 问答评测
    for qa in qa_pairs:
        question = qa["question"]
        question_image = qa.get("question_image")
        gt_answer = qa["answer"]
        category = qa["point"]
        clue = qa.get("clue", [])

        memory_context = memory_agent.memory_recall(question, question_image)

        system_answer = memory_agent.response(
            memory_context,
            question,
            speaker_a,
            speaker_b,
            question_image,
            format_constraint
        )

        save {
            sample_id,
            session_id,
            question,
            system_answer,
            original_answer,
            category,
            retrieved_ids,
            clue
        }
```

代码里结果字段也正是这些：`sample_id`、`session_id`、`question`、`system_answer`、`original_answer`、`category`、`timestamp`，如果开了 retrieval metrics，还会存 `retrieved_ids` 和 `clue`。

---

## 8. 问题类型有哪些？

论文里把任务分成三大类、九个子任务：

```text
Memory Extraction & Adaptation
- FR: Factual Retrieval
- VS: Visual-centric Search
- TTL: Test-Time Learning

Memory Reasoning
- TR: Temporal Reasoning
- VR: Visual-centric Reasoning
- MR: Multi-entity Reasoning

Memory Knowledge Management
- KR: Knowledge Resolution
- CD: Conflict Detection
- AR: Answer Refusal
```

论文明确说这三大类分别对应：获取可用记忆、基于 evolving multimodal evidence 推理、在动态/矛盾/缺失状态下管理记忆。([ar5iv][3])

代码里 `qa["point"]` 就是 category。比如：

```json
"point": "VS",
"question": "Which image in the dialogue shows the user's laptop?",
"answer": "D6:IMG_001",
"clue": ["D6:3"]
```

对于特殊类型，代码会额外加格式约束 prompt：

```text
AR：如果 conversation 没有信息，回答 “Not mentioned.”
CD：只回答 “Yes.” 或 “No.”
VS：返回 image_id，多个 image_id 升序、逗号分隔
```

这三个 prompt 文件在仓库里分别就是这样写的。  

---

## 9. metric 怎么算？

Mem-Gallery 有三类指标：

```text
1. QA answer performance
   - F1
   - EM
   - BLEU / BLEU-1 / BLEU-2
   - LLM-as-a-Judge

2. Retrieval effectiveness
   - Precision@K
   - Recall@K
   - HitRate@K

3. Efficiency
   - memory storage time
   - QA retrieval + generation time
   - total time
```

论文里说 QA 指标包括 F1、EM、BLEU-1、LLM-as-a-Judge；retrieval 指标包括 Recall@K、Precision@K、Hit@K；efficiency 统计记忆写入时间和 retrieval + answer generation 时间。([ar5iv][3])

代码实现里，answer metric 是拿 `system_answer` 和 `original_answer` 算；retrieval metric 是拿 `retrieved_ids` 和 `clue` 算。

其中 retrieval 的 `clue` 是人工标注的证据 turn，比如：

```json
"clue": ["D6:3"]
```

如果 method 检索出来的 memory event 的 `dialogue_id` 命中了 `D6:3`，retrieval metric 就会更高。

---

## 10. 你原来的猜测哪些是对的，哪些要改？

你的猜测里，**大方向是对的**：

> dataset 有多个样本，每个样本有多个 session，每个 session 包含多个 turn，灌入 memory 后再 question，然后 response 获取 answer 或相关记忆，reset 时机要考虑。

但具体要改成下面这样：

| 你的说法                        | Mem-Gallery 真实情况                                                        |
| --------------------------- | ----------------------------------------------------------------------- |
| dataset 有多个样本               | 更准确：dataset 有 20 个 scenario JSON；每个 scenario 是一个长期用户/主题的完整多 session 样本  |
| 每个样本有多个 session             | 对                                                                       |
| session 是一次对话               | 基本对，但这里 session 更像某一天/某阶段的一段多轮对话                                        |
| session 包含多个 turn           | 对，但代码叫 `dialogues`，每个 round 有 user+assistant                            |
| 一个 turn 是你说一句我说一句           | 对，代码把 user+assistant 合并为一个 memory event                                 |
| question 可能每个 session 后设置   | 不对。QA 是 scenario 级别的统一列表，代码先灌完整个 scenario，再遍历所有 QA                      |
| 每个 turn 会有 question 吗       | 不会。turn 只是 memory evidence；QA 通过 `clue` 指向相关 turn                       |
| method 灌入记忆后返回 answer 或相关记忆 | 当前主流程：method 返回相关 memory/context；benchmark 的 MLLM 用这个 context 生成 answer |
| reset 可能需要考虑                | 对。真实代码是每个 scenario reset 一次，不在 session/QA 之间 reset                      |

---

## 11. 你如果要把自己的 memory method 接进 Mem-Gallery，最小应该怎么适配？

当前 benchmark 的核心调用链要求你的 method 至少能被包装成：

```python
memory.reset()
memory.store(memory_event)
memory.recall(query_or_query_dict)
```

其中 `store()` 收到的 memory event 大概是：

```python
{
  "text": "user (...): ...\nassistant: ...",
  "image": None 或 {"path": "...jpg", "caption": "...", "img_id": "D1:IMG_001"},
  "timestamp": "2025-03-02",
  "dialogue_id": "D1:2"
}
```

`recall()` 应该返回：

```text
文本 memory：一段 memory_context string
多模态 memory：一组 memory dict list，里面可以含 text/image
```

然后 benchmark 会负责：

```python
system_answer = response(memory_context, question, ...)
```

如果你要做统一评测框架，我建议你把接口设计成：

```python
reset(sample_id)
ingest(event: MemoryEvent)
retrieve(query: MemoryQuery) -> MemoryContext
answer(query: MemoryQuery, memory_context: MemoryContext) -> str
```

但注意：在 Mem-Gallery 这个 benchmark 的真实实现中，`answer()` 不是 memory method 的职责，而是 benchmark harness 的职责。你可以在统一框架里保留 `answer()`，但要把它标注为 **reader/backbone generation stage**，不要和 memory method 混成一个东西。

---

## 12. 最后给你一张真实流程图

```text
For each scenario JSON
│
├── 1. Load JSON
│   ├── character_profile
│   ├── multi_session_dialogues
│   └── human-annotated QAs
│
├── 2. Create memory_agent
│   └── memory_agent.reset()
│
├── 3. Process all sessions
│   └── For each session
│       └── For each dialogue round
│           ├── merge user + assistant into text
│           ├── attach image path/caption/img_id if exists
│           ├── timestamp = session date
│           └── dialogue_id = round id, e.g. D3:5
│
├── 4. Ingest memory
│   └── memory.store(memory_event)
│
├── 5. QA evaluation
│   └── For each QA
│       ├── question
│       ├── optional question_image
│       ├── category/point
│       ├── ground-truth answer
│       ├── clue evidence ids
│       ├── memory_context = memory.recall(question)
│       ├── system_answer = MLLM(memory_context + question)
│       └── save result
│
├── 6. Metric
│   ├── answer quality: F1 / EM / BLEU / LLM Judge
│   ├── retrieval: Precision@K / Recall@K / HitRate@K
│   └── efficiency: storage time / QA time
│
└── 7. Next scenario
    └── reset again
```

一句话总结：**Mem-Gallery 测的不是“模型能不能在当前上下文直接答题”，而是“一个 memory system 能不能把长时间、多 session、含图含文的历史对话组织成可检索记忆，并让统一的 MLLM backbone 借助这些记忆回答 QA”。**

[1]: https://huggingface.co/datasets/Ethan-Bei/Mem-Gallery "Ethan-Bei/Mem-Gallery · Datasets at Hugging Face"
[2]: https://huggingface.co/datasets/Ethan-Bei/Mem-Gallery/blob/main/data/dialog/Dog_Behavior_Research_Academic_Life.json "data/dialog/Dog_Behavior_Research_Academic_Life.json · Ethan-Bei/Mem-Gallery at main"
[3]: https://ar5iv.org/html/2601.03515v1 "[2601.03515] Mem-Gallery: Benchmarking Multimodal Long-Term Conversational Memory for MLLM Agents"
