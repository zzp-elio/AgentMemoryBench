# BEAM 评测流程详解

## 概述

BEAM（Beyond a Million Tokens）是一个多尺度长对话记忆评测，包含 **4 个规模**（100K/500K/1M/10M tokens）、**10 种记忆能力**的 probing question。评测范式是 **"注入一段完整 conversation → 逐题问答 → LLM-Judge 评分"**，每个 conversation 之间完全隔离。

## 1. 数据层级

### 1.1 顶层层级

一个 conversation（HF dataset 的一个 row）对应一段完整长期对话和它的所有 probing questions：

```text
BEAM Dataset
├── split: "100K"  (20 conversations)
├── split: "500K"  (35 conversations)
├── split: "1M"    (35 conversations)
└── split: "10M"   (10 conversations, 独立仓库 BEAM-10M)
```

### 1.2 一个 conversation 的内部结构（100K/500K/1M）

HF dataset 中每个 row 的字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `conversation_id` | `str` | 对话编号，如 `"1"` |
| `conversation_seed` | `struct` | `{category, id, subtopics, theme, title}` |
| `narratives` | `str` | 对话叙事标签分类文本 |
| `user_profile` | `struct` | `{user_info: str, user_relationships: str}` |
| `conversation_plan` | `str` | 对话生成计划（BATCH X PLAN） |
| `user_questions` | `list[dict]` | 用户原始提问（非 probing questions） |
| `chat` | `list[list[dict]]` | **核心对话数据**（见 1.3） |
| `probing_questions` | `str` | **评测问题**，需 `ast.literal_eval()` 解析（见 1.4） |

chat 和 probing_questions 是评测中唯二需要的字段。其他字段为生成中间产物，评测流程不读取。

### 1.3 `chat` 字段的精确结构（100K/500K/1M）

HF 数据集中的 `chat` 是 **两层 list**，没有 `batch_number` 或 `turns` 键：

```text
chat: list[list[dict]]
├── 外层 list: 对应 batch（10 个 batch for 1M，3 个 for 100K）
│   └── 内层 list: 该 batch 内的消息序列（~160 条/1M batch）
│       └── 每条消息是一个 dict：
│           {
│               "role":       "user" | "assistant",
│               "content":    str,       # 消息正文
│               "id":         int,       # 全局递增消息 ID
│               "index":      str,       # 如 "1,1"
│               "question_type": "main_question" | "followup_question" | "answer_ai_question" | None,
│               "time_anchor": str,      # 如 "March-01-2024"
│           }
```

消息类型分布（以 1M 为例）：
- `user / main_question`: 625 条（发起的主动提问）
- `user / followup_question`: 200 条（追问）
- `user / answer_ai_question`: 30 条（回答 AI 的提问）
- `assistant / None`: 855 条（AI 的回答）

**关键点：** 内层 list 是扁平的消息序列，user 和 assistant 交替出现。每条 user 消息的 `question_type` 可为 `None`（assistant 消息时）、`"main_question"`、`"followup_question"` 或 `"answer_ai_question"`。

**与本地 `chat.json` 的区别：** 本地 GitHub 仓库中的 `chat.json` 经过 `download_dataset.py` 的 `convert_chats_pickle_to_json()` 处理后，多了 `batch_number` 和 `turns`（把消息按 turn 分组）两个嵌套层：

```json
// 本地 chat.json 结构（派生物，非原始）
[
  {
    "batch_number": 1,
    "turns": [
      [{user_msg}, {assistant_msg}],  // turn 1 (一个 user-assistant pair)
      [{user_msg}, {assistant_msg}],  // turn 2
      ...
    ]
  },
  ...
]
```

HF 数据集的 `chat` 更扁平，没有 turn 分组——所有消息按顺序展开在内层 list 中。官方的 `probing_question_evaluation` 代码实际上是按本地 `chat.json` 的 `batch['turns']` 结构处理的。

### 1.4 `probing_questions` 字段的精确结构

`probing_questions` 是 **一个 Python 字典的字符串表示**，必须 `ast.literal_eval()` 解析后才能使用。解析后是一个按 10 种记忆能力分类的 dict：

```python
{
    "abstention":               [{q1}, {q2}],   # 各 2 题
    "contradiction_resolution": [{q1}, {q2}],
    "event_ordering":           [{q1}, {q2}],
    "information_extraction":   [{q1}, {q2}],
    "instruction_following":    [{q1}, {q2}],
    "knowledge_update":         [{q1}, {q2}],
    "multi_session_reasoning":  [{q1}, {q2}],
    "preference_following":     [{q1}, {q2}],
    "summarization":            [{q1}, {q2}],
    "temporal_reasoning":       [{q1}, {q2}],
}
```

每个 question 对象包含（以 `information_extraction` 为例，字段因类型而异）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `question` | `str` | 问题文本 |
| `answer` | `str` | 正确答案（只有部分类型有，如 information_extraction；abstention 没有） |
| `difficulty` | `str` | 如 `"easy"` `"medium"` |
| `question_type` | `str` | 如 `"short_answer"` |
| `conversation_reference` | `str` | 引用哪些对话部分 |
| `key_facts_tested` | `list[str]` | 考察的关键事实 |
| `source_chat_ids` | `list[int]` | 答案依据的消息 ID |
| `rubric` | `list[str]` | **评分标准**：一列自然语言描述的评分项，每条是一个评判维度 |

**rubric 是评测阶段的核心输入**（见第 3 节）。以 `information_extraction` 为例，rubric 如：
```json
["LLM response should state the amount: 83% accuracy",
 "LLM response should mention the number of languages: 12",
 "LLM response should state: the initial accuracy was 76%"]
```

注意：abstention 类型没有 `answer` 字段，而是有 `ideal_response`（理想回答是"无法回答"）和 `why_unanswerable`（解释原因）。

### 1.5 BEAM-10M 的特殊结构

`Mohammadta/BEAM-10M` 是独立的 HF 仓库。与主数据集的差异：

**`chat` 字段：** 不是 `list[list[dict]]`，而是 `list[dict]`，其中 10 个 dict 分别以 `plan-1` 到 `plan-10` 为键：

```text
chat: list[10]
├── {"plan-1": list[list[dict]]}   # plan-1 的 batch × message 序列
├── {"plan-2": list[list[dict]]}
├── ...
└── {"plan-10": list[list[dict]]}
```

每个 plan 内部结构等同于普通规模的 chat：`list[batch][message]`。10M 的对话是通过 10 个独立 plan 生成后拼接而成的，每个 plan 代表一个时间阶段。

**额外的 `plans` 字段：** 10M 多了一个 `plans: list[10]`，每个 plan 对象包含独立的 `chat`、`conversation_seed`、`user_profile`、`conversation_plan`、`user_questions` 等。这是生成阶段的详细记录，**评测流程不读取 `plans` 字段，只用顶层的 `chat`**。

**`user_questions` 为空（`list[0]`）。**

## 2. 评测流程：Answer Generation（预测阶段）

### 2.1 隔离粒度

**隔离粒度为 conversation 级别**。每个 conversation 独立处理：

```
for each conversation:
    chat = conversation.chat          # 一次读入整个对话
    probing_questions = conversation.probing_questions  # 一次读入所有问题
    
    for each question_type in probing_questions:       # 10 种能力
        for each question in question_type:             # 每种 2 题
            answer = answer_question(chat, question)    # 用同一个 chat 回答
            save(answer)
```

- conversation A 的 chat 不会进入 conversation B 的问答
- 一个 conversation 的所有 20 个 probing question 共享同一个 chat
- 不同 conversation 之间没有信息泄漏

### 2.2 三种评测模式

BEAM 官方支持三种 `evaluation_type`：

#### 2.2.1 long-context 模式

把整段对话直接灌入 LLM context window，从尾部按 max_tokens 截断。

```
步骤 1: 从 chat 中展开所有消息为 flat list[dict]
        - 100K/500K/1M: for batch in chat → for msg in batch → messages.append({role, content})
        - 10M:         for plan_dict in chat → for batch in plan → for msg in batch → messages.append(...)

步骤 2: 计算总 token 数（4 tokens/msg 固定开销 + 内容 token）
        - 如果超过 max_tokens - 10000，从尾部开始丢弃消息直到 token 数降到 max_tokens - 2000 以内
        - 丢弃后确保消息数为偶数（保持 user/assistant 成对）

步骤 3: 把问题追加到消息列表末尾
        messages.append({
            "role": "user",
            "content": "NOTE: Only provide the answer without any explanations.\nQuestion: {query}"
        })

步骤 4: backbone LLM 直接 invoke(messages)，返回 answer
        - 整个 chat 作为 message history，问题直接跟在后面
        - backbone LLM 凭自身 long-context 能力回答

步骤 5: saved_messages 缓存（去掉最后一条问题消息），下一个 question 复用以避免重复 token 计数/截断
```

**关键特征：** 不提取、不检索、不总结。完全依赖 backbone LLM 的长上下文能力。对于第一个问题做 token 截断后，后续问题直接复用截断后的消息列表。

#### 2.2.2 rag 模式（RAG baseline）

先对整个 chat 做 chunking + 索引构建（只做一次），之后每个问题独立检索并拼接 prompt。

```
步骤 1: chunking（只做一次，saved_retriever 缓存）

        根据 retrieval_method 选择 chunking 策略:

        a) "pair_chunk": 每个 user-assistant pair 为一个 chunk
           遍历 batch → turns → 每 2 个相邻消息配对
           
           chunk = {
               "text": "USER: {u.content}\n\nASSISTANT: {a.content}",
               "metadata": {"batch_number": N, "turn_number": N, "pair_number": N}
           }

        b) "turn_chunk": 每个 turn 内的所有消息拼成一个 chunk
           chunk = {
               "text": "USER: ...\n\nASSISTANT: ...",
               "metadata": {"batch_number": N, "turn_number": N}
           }

        c) "kv": 每对 user-assistant → qwen LLM 提取 key:value 结构化事实
           chunk = {"text": "Key1: Value1\nKey2: Value2\n...", "metadata": {...}, "original_text": {...}}
           额外保留 original_text 用于后续 context 还原

步骤 2: 构建 retriever（只做一次）

        根据 retriever 类型选择:
        - "bm25":     BM25Retriever (sparse, 无模型下载)
        - "splade":   SPLADE sparse retriever（需下载 naver/splade-cocondenser-ensembledistil + Qdrant）
        - "e5":       E5 dense retriever（intfloat/e5-large-v2 + FAISS）
        - "dense":    BGE dense retriever（BAAI/bge-small-en-v1.5 + FAISS）
        - "hybrid":   BM25 + BGE ensemble（权重 0.3 / 0.7）

步骤 3: 对每个 question，检索 top-k 相关 chunk
        result = retriever.get_relevant_documents(query=question, k=k)

步骤 4: handling_context() 将检索结果拼成 context
        - pair_chunk / turn_chunk: 直接拼接 chunk 文本，限制 reader_max_tokens=29000
        - kv: 用检索到的 doc.metadata["id"] 回查 original_text，再拼接

步骤 5: 拼 prompt → backbone LLM 回答
        prompt = answer_generation_for_rag
            .replace("<context>", context)
            .replace("<question>", query)

        prompt 模板:
        "You are an assistant that MUST answer questions using ONLY the information provided
         in the context below.
         STRICT INSTRUCTIONS:
         1. Answer ONLY based on the provided context
         2. Do NOT use your internal knowledge
         
         CONTEXT: {context}
         QUESTION: {question}
         
         ANSWER REQUIREMENTS:
         - Be direct and concise
         - Only output the answer to the question without any explanation
         
         RESPONSE:"

步骤 6: backbone LLM invoke(prompt)，返回 answer
```

**关键特征：** chunking + 索引构建每个 conversation 只做一次。所有 20 个 probing question 复用同一个 retriever 实例。

#### 2.2.3 light 模式（LIGHT: Episodic + Working + Scratchpad）

论文核心贡献。在 rag 的基础上额外增加三个预处理步骤（只做一次）：

```
前置步骤 A: Scratchpad 生成
        对每个 user-assistant pair → qwen LLM 提取关键信息
        → 所有 pair 结果 iterative summarize (gpt-4.1-mini, tokens_limit=14000)
        → 输出一个压缩的 scratchpad 文本，缓存到 scrach_pad_new.txt

前置步骤 B: Episodic Memory（长期记忆）
        对每个 user-assistant pair → qwen LLM 提取 key:value 结构化事实
        → 每对输出 "Key1: Value1\nKey2: Value2\n...\nSummary: ..."
        → 缓存到 long_term_chunks.pkl

前置步骤 C: Working Memory（短期记忆）
        取最后 100 个 pair_chunk = 最近的对话窗口
        → short_term_texts = 最后 100 个 chunk 的文本
        → short_term_metas = 最后 100 个 chunk 的元数据

主流程:
步骤 1: 检索（复用 rag 的 retriever 逻辑）
        从 Episodic Memory chunks 中用 dense retriever (BAAI/bge-large-en-v1.5) 检索 top-k

步骤 2: noise_filtering:
        a) Scratchpad 经 SemanticChunker 切分
           → 每个 segment 用 qwen LLM 判断与 query 的相关性
           → 只保留 qwen 判断为 "yes" 的 segment

        b) 最终 context 由三部分组成:
           - 检索到的 episodic memory 原始文本（original_text 版本，限制 14000 tokens）
           - 最后 100 个 working memory chunks
           - 过滤后的 scratchpad（追加在末尾 "SCRATCH PAD: {filtered}"）

步骤 3: 拼 prompt（同 rag 模式）→ backbone LLM 回答
```

**关键特征：** LIGHT 的 scratchpad + episodic memory 预处理需要两次额外的 LLM 调用（qwen + gpt-4.1-mini），每个 conversation 全局只做一次。

### 2.3 并发

官方支持 `ThreadPoolExecutor` 并发处理 conversation（非 question 级别并发）：

```python
# batch_run_answer_generation 中
with ThreadPoolExecutor(max_workers=num_threads) as executor:
    for index in range(start_index, end_index):
        executor.submit(worker, index)  # 每个 worker 处理一个 conversation
```

每个 worker 独立处理一个完整的 conversation：读 chat → 回答问题 → 写结果。conversation 之间不共享任何状态。

### 2.4 输出产物

每个 conversation 输出一个 JSON 文件到 `results/{chat_size}/{conversation_id}/{result_file_name}`：

```json
{
    "abstention": [
        {
            "question": "...",
            "difficulty": "easy",
            ...原始字段...,
            "llm_response": "Based on the provided chat..."
        },
        ...
    ],
    "information_extraction": [...],
    ...
}
```

即在原始 probing question dict 基础上追加 `"llm_response"` 字段。

## 3. 评测流程：Evaluation（评分阶段）

### 3.1 LLM-as-Judge 评分

评分阶段**不读取 chat**，只读取两个文件：
- 预测结果 JSON（含 `llm_response` 字段）
- `probing_questions.json`（获取 rubric）

```
for each question:
    rubric = probing_questions[question_type][index]["rubric"]  # 评分标准列表
    
    for each rubric_item in rubric:
        prompt = unified_llm_judge_base_prompt
            .replace("<rubric_item>", rubric_item)
            .replace("<llm_response>", llm_response)
            .replace("<question>", probing_question)
        
        judge_response = gpt-4.1-mini.invoke(prompt)  → 返回 {"score": 0.0|0.5|1.0, ...}
    
    final_score = sum(all rubric_item scores) / len(rubric)
```

### 3.2 Judge 评分标准

LLM Judge 对每条 rubric_item 输出 0.0 / 0.5 / 1.0：

- **1.0 (Complete Compliance):** 完全满足 rubric 要求
- **0.5 (Partial Compliance):** 部分满足但有小问题
- **0.0 (No Compliance):** 不满足 / 回答不切题

10 种 question type 共用同一个 judge prompt 模板，差异只在 rubric 内容。例外：`event_ordering` 额外计算 Kendall's tau 排序相关性。

## 4. 总结

| 维度 | BEAM |
|------|------|
| 隔离粒度 | **conversation 级别** |
| chat 注入方式 | 一次性读入整个 chat（100K/500K/1M 是 `list[list[dict]]`，10M 多一层 `plan` 嵌套） |
| 问答时机 | chat 全部注入后，逐题问答（20 题 / conversation） |
| 评测方式 | LLM-as-Judge（gpt-4.1-mini）按 rubric 打分 |
| 三种模式 | long-context（全量灌入）、rag（检索增强）、light（Episodic + Working + Scratchpad） |
| chunking 复用 | rag/light 模式下 chunking + 索引构建每个 conversation 只做一次，所有 question 复用 |
| 长上下文截断 | long-context 模式从尾部按 max_tokens 截断 |
| 10M 特殊性 | chat 嵌套 10 个 plan，多 `plans` 字段（评测不读），user_questions 为空 |
