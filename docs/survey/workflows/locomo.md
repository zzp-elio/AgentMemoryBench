# LoCoMo 评测流程详解

1. **一个 sample 不是一个 QA 样本，而是一整段长期对话。**
   `locomo10.json` 是一个列表，里面每个 sample 代表一组两个人之间的完整长期 conversation。README 明确说 LoCoMo 当前 release 有 **10 conversations**，每个 sample 是一个 conversation 及其 annotation。([GitHub][1]) 

2. **session 是长期对话中的一次会话片段，turn 是一个人说的一句话，不是“一问一答一轮”。**
   `conversation` 里有 `session_<num>` 和 `session_<num>_date_time`，`<num>` 是时间顺序；每个 session 里是多个 turn，每个 turn 有 `speaker`、`dia_id`、`text`，可选有图片 URL / BLIP caption / image query。([GitHub][1])

3. **question 是 sample/conversation 级别的 QA，不是每个 session 或每个 turn 后面都有。**
   每个 sample 里有一个 `qa` 列表，每个 QA 包含 `question`、`answer`、`category`、`evidence`。`evidence` 是若干 `dia_id`，比如 `D1:3` 表示第 1 个 session 的第 3 条 dialogue turn。README 和数据样例都能看到这种结构。([GitHub][1]) ([GitHub][2])

---

## 1. LoCoMo 的真实数据层级

你可以把 LoCoMo 理解成：

```text
locomo10.json
└── sample_1 / conversation_1
    ├── sample_id
    ├── conversation
    │   ├── speaker_a
    │   ├── speaker_b
    │   ├── session_1_date_time
    │   ├── session_1
    │   │   ├── turn_1: {speaker, dia_id, text, ...}
    │   │   ├── turn_2: {speaker, dia_id, text, ...}
    │   │   └── ...
    │   ├── session_2_date_time
    │   ├── session_2
    │   └── ...
    ├── observation
    ├── session_summary
    ├── event_summary
    └── qa
        ├── question_1
        ├── question_2
        └── ...
```

这里的 **sample = 一整段长期对话**。不是“一个问题一个样本”。这点很重要，因为 reset 的边界应该按 sample/conversation 来划，而不是按 question 来划。

`session` 是长期对话中的一次聊天，比如 2023 年 5 月 21 日的一次聊天、2023 年 6 月某天的一次聊天。`turn` 是 session 内的一条发言。你之前说“一个 turn 就是你说一句我说一句”，这个不太准确。更准确是：**一个 turn = 一个 speaker 的单条 utterance**。如果 A 说一句、B 回一句，这是两个 turn。

---

## 2. QA 是什么时候问的？

LoCoMo 官方 QA 不是边对话边问，也不是每个 session 后都问。更接近：

```text
先给模型 / memory method 整个长期 conversation
然后对这个 conversation 后面的 qa 列表逐题提问
最后把模型 answer 和 gold answer 算分
```

官方 `evaluate_qa.py` 里就是先加载 `data-file`，然后 `for data in samples` 遍历每个 conversation/sample，再把这个 sample 的 `qa` 拷贝出来，调用 `get_gpt_answers / get_claude_answers / get_gemini_answers / get_hf_answers` 生成答案。([GitHub][3])

所以，**LoCoMo QA 的评测时间点是“一个完整 sample 的所有 sessions 都可用之后”**。不是 session 级别 quiz，也不是 turn 级别 quiz。

---

## 3. 官方 LoCoMo 到底评测的是 memory module 还是 final answer system？

这个地方你一定要分清楚。

**LoCoMo 官方代码评测的是最终 answer，不是单独的 memory retrieve 结果。**
`evaluate_qa.py` 最后调用 `eval_question_answering(answers['qa'], prediction_key)`，也就是说它需要每个 QA 上有一个模型预测答案，然后用这个预测答案和 gold answer 算分。([GitHub][3])

也就是说，官方范式更像：

```text
conversation context / retrieved context
        ↓
LLM reader
        ↓
short answer
        ↓
和 gold answer 算 F1
```

而不是：

```text
memory method.retrieve(question)
        ↓
只评价 retrieved memory 本身
```

不过，RAG 模式下官方也会额外记录 retrieval context ids，然后和 `evidence` 计算 recall。代码里如果 `prediction_key + '_context'` 存在，并且 QA 有 evidence，就会计算 retrieved context 是否命中 evidence。([GitHub][4])

所以如果你做统一框架，LoCoMo 可以有两种接法：

```text
A. system-level：
method.answer(question) 直接返回答案，评 final answer F1

B. memory-module-level：
method.retrieve(question) 返回 memory
reader.answer(question, memory) 返回答案
同时可额外算 retrieval recall
```

但你要诚实地说：**LoCoMo 官方主评测是 answer-level，不是 memory-only-level。**

---

## 4. 官方 full-context 评测流程

官方非 RAG 版本大概是这样：

```text
for each sample in locomo10.json:
    读取 sample['conversation']
    读取 sample['qa']

    把 conversation 拼成 prompt context
    如果太长，就按模型上下文窗口截断
    对 qa 里的问题生成 short answer
    保存 prediction

    对 prediction 和 answer 算 F1
```

代码里 `get_input_context` 会遍历 session，并把每条 turn 拼成：

```text
speaker said, "text"
```

如果有图片 caption，还会把 BLIP caption 加进去。它还会带上 session 的日期信息，因为 temporal question 需要日期。([GitHub][5])

然后它构造 prompt：

```text
Based on the above context, write an answer in the form of a short phrase...
Question: ...
Short answer:
```

官方 prompt 明确要求短答案，并尽量使用 context 中的原词。([GitHub][5])

---

## 5. 官方 RAG 评测流程

RAG 版本不是把整段 conversation 全塞进去，而是先建一个 per-sample database。README 说 RAG 可以用三种 database：`dialogs`、`observations`、`session summaries`。([GitHub][1])

脚本里也确实分别跑：

```text
rag-mode dialog
rag-mode observation
rag-mode summary
```

并且 top-k 会取 5 / 10 / 25 / 50 等不同设置。([GitHub][6])

以 `rag-mode=dialog` 为例，官方代码会：

```text
for session_i in conversation:
    for dialog in session_i:
        context_ids.append(dialog['dia_id'])
        date_times.append(session_i_date_time)
        context.append(speaker said "text")
        如果有 blip_caption，也拼进去

对这些 context 建 embedding database
对每个 question 建 query embedding
点积检索 top-k
把 top-k context 拼进 prompt
让 GPT 生成 short answer
```

这部分在 `prepare_for_rag` 和 `get_rag_context` 里写得很清楚：dialog database 存 `embeddings`、`date_time`、`dia_id`、`context`；检索时按 embedding 相似度排序，取 top-k context，并返回对应 context ids。([GitHub][5]) ([GitHub][5])

---

## 6. 如果你现在有一个 memory method，最合理的 LoCoMo 接入流程

你应该这么设计：

```python
for sample in locomo_samples:
    method.reset(sample_id=sample["sample_id"])

    # 1. 按时间顺序灌入完整 conversation
    conv = sample["conversation"]
    session_nums = sorted(all session ids)

    for session_id in session_nums:
        session_time = conv[f"session_{session_id}_date_time"]

        for turn in conv[f"session_{session_id}"]:
            method.ingest({
                "sample_id": sample["sample_id"],
                "session_id": session_id,
                "timestamp": session_time,
                "dia_id": turn["dia_id"],
                "speaker": turn["speaker"],
                "text": turn["text"],
                "blip_caption": turn.get("blip_caption"),
                "img_url": turn.get("img_url")
            })

    # 2. 所有 session 灌完以后，再问 qa
    for qa in sample["qa"]:
        question = qa["question"]

        # memory-module 评测方式
        memories = method.retrieve(question, top_k=k)
        pred = reader.answer(question, memories)

        # 或 system-level 评测方式
        # pred = method.answer(question)

        score = evaluate(pred, qa["answer"], qa["category"])

    # 3. 一个 sample 结束后 reset，防止不同 conversation 之间串记忆
    method.reset(sample_id=sample["sample_id"])
```

这个流程才最贴近 LoCoMo 的真实评测逻辑。

---

## 7. reset 到底什么时候做？

这个问题你问得非常关键。我的建议是：

### 必须 reset：每个 sample / conversation 开始前

因为 LoCoMo 的每个 sample 是不同的两个人、不同的人设、不同的长期对话。如果不 reset，前一个 conversation 的信息会污染下一个 conversation。

```text
conv-1 评测完
reset
conv-2 开始
reset
conv-3 开始
...
```

这是最基本的隔离。

### 不要 reset：session 之间不要 reset

LoCoMo 测的就是 long-term conversational memory。如果你每个 session reset，那就把长期记忆任务破坏了。

```text
session_1 ingest
session_2 ingest
session_3 ingest
...
session_N ingest
然后 QA
```

中间不能 reset。

### 一般不要 reset：question 之间不需要 reset

如果你的 `retrieve` / `answer` 是只读的，那么同一个 sample 下多个 QA 可以连续问，不需要 reset。

但是有一个坑：**如果你的 method 会把 question 和 answer 也写入 memory，那就会造成 QA 泄漏。**
比如第 1 个问题问了 “Caroline 是哪里人？”，第 2 个问题再问相关问题，method 可能利用刚才 QA 产生的新记忆，这就不公平了。

所以更严谨的做法是：

```text
灌完整个 conversation
保存 memory snapshot

for each question:
    restore 到 QA 前 snapshot
    ask question
    禁止把 question / prediction 写回长期 memory
```

如果你的方法不支持 snapshot，那至少要保证 QA 阶段是 read-only。

---

## 8. evidence 是干什么用的？

`evidence` 不是给模型看的标准答案线索，而是标注者告诉你：这个问题的答案来自哪些 dialogue turns。

例如：

```json
{
  "question": "When did Caroline go to the LGBTQ support group?",
  "answer": "7 May 2023",
  "evidence": ["D1:3"],
  "category": 2
}
```

这里 `D1:3` 表示答案证据在第 1 个 session 的第 3 条 turn。官方 RAG 模式会把检索出来的 context id 存起来，然后和 evidence 比较，算 retrieval recall。([GitHub][4])

所以对你的统一框架来说，LoCoMo 可以同时产出两个指标：

```text
answer_score: pred answer vs gold answer
retrieval_recall: retrieved dia_id 是否覆盖 evidence dia_id
```

这就很适合你之前说的统一接口：

```text
retrieve → 看 memory 找得准不准
answer   → 看最终回答对不对
```

但要注意：**LoCoMo 官方主要报告的是 answer 分数，retrieval recall 是 RAG 额外分析。**

---

## 9. category 怎么理解？

LoCoMo 网站说 QA 分成五类：single-hop、multi-hop、temporal、commonsense/world knowledge、adversarial。([Snap Research][7])

从代码实际处理看：

```text
category 1: multi-hop
category 2: temporal
category 3: open-domain / commonsense-world knowledge
category 4: single-hop
category 5: adversarial
```

代码里 category 1 用 multi-answer F1，category 2/3/4 用普通 F1，category 5 按是否回答 “no information / not mentioned” 处理。([GitHub][4])

这里我要提醒你一个坑：LoCoMo 的 category 文档和代码/数据之间有点不够干净，GitHub issue 里也有人专门问过 category 编号映射问题。([GitHub][8]) 所以你写论文或框架时，最好明确说：**我们 follow official source-code category mapping**，不要只按论文文字猜。

---

## 10. 最终一句话版流程

LoCoMo 的真实 QA 测评流程是：

```text
一个 sample = 一整段两人长期对话
一个 sample 里有多个按时间排列的 session
一个 session 里有多个单 speaker turn
QA 是挂在整个 sample 后面的，不是挂在每个 session/turn 后面的

评测时：
对每个 sample reset memory
按 session 时间顺序 ingest 所有 turns
完整 conversation ingest 完后，对 sample['qa'] 逐题提问
method / reader 返回 short answer
用 gold answer 算 F1
如果是 RAG / retrieve 型方法，还可以用 evidence dia_id 算 retrieval recall
sample 结束后 reset，进入下一个 sample
```

LoCoMo QA 是 conversation-level 的后测题。**