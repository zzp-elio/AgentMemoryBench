# Agent Memory Benchmark 

## 总览

| Benchmark | 核心数据形态 | 隔离粒度 | 核心 Metric | 当前接口适配判断 |
| --- | --- | --- | --- | --- |
| BEAM | 超长 conversation，由 batch/session-like 时间段组成，最后回答 probing questions | `conversation_id` 级隔离 | Rubric-nugget LLM judge；event ordering 用顺序一致性指标 | `add(conversation) + retrieve(question)` 可覆盖第一版 |
| MemoryAgentBench | 一条 row 一个长 context，切成 chunk stream 后多任务 QA | `context_id` / dataset row 级隔离 | String metrics、Recall@5、LLM-as-judge accuracy/F1 | 需要 chunked incremental ingest；可先映射到 `add(memory_stream) + retrieve(question)` |
| MemoryBench | train feedback dialogs 构建经验记忆，test split 做多任务评测 | run / dataset 级共享 memory，部分 corpus 临时隔离 | 各 dataset 原生 metric；domain/task 级归一化聚合 | 需要专属 runner；method 侧保持 `add(memory_input) + retrieve(query)` |
| HaluMem | uuid/user 连续 sessions + memory extraction/update/QA 三阶段诊断 | `uuid` user 级隔离，同一 user 内 sessions 连续累积 | Extraction recall/accuracy/F1/FMR；Updating/QA 分类比例 | 完整接入需要 `add_dialogue`、`get_dialogue_memory`、`retrieve` |
| MemBench | `tid` trajectory 的 message stream + multiple-choice QA | `tid` trajectory 级隔离 | Memory Accuracy、evidence Recall、Capacity、Efficiency | `add(tid,event) + retrieve(tid,query)`，且要返回 source step id |
| PersonaMem | shared context OpenAI-style messages + checkpoint multiple-choice personalization QA | `(benchmark_size, shared_context_id)` 级隔离；`persona_id` 只能做非官方 stress profile | Multiple-choice Accuracy；按 context length、question type、topic、distance 分组 | 官方是 direct long-context LLM；memory-module 版需要 message-level incremental prefix ingest + multiple-choice reader |
| MemoryArena | 一行 task 包含有序 subtasks，agent 在环境中执行，subtask 轨迹写回 memory | task/group/paper/query 级 memory namespace | PS、SR、SR@k、latency；各环境有 shopping/travel/formal/search 子指标 | 需要新的 agentic-memory-environment runner；memory module 应拆成 `add_chunk + retrieve_context` |

## 1. BEAM

### Dataset 数据结构

BEAM 的 evaluation 单位是一个完整 conversation。一个 `chat.json` / HF dataset row 对应
一个 `conversation_id`，其中 `batch` 可以在我们框架里映射成 session-like 时间段；最终
probing questions 在完整 conversation 结束后提出。

本地 HuggingFace 数据路径：

| 本地目录 | split | 样本数 | 数据形态 |
| --- | --- | ---: | --- |
| `data/BEAM/beam_dataset` | `100K` | 20 | 普通 split，`chat = list[batch -> list[message]]` |
| `data/BEAM/beam_dataset` | `500K` | 35 | 普通 split，`chat = list[batch -> list[message]]` |
| `data/BEAM/beam_dataset` | `1M` | 35 | 普通 split，`chat = list[batch -> list[message]]` |
| `data/BEAM/beam_10M_dataset` | `10M` | 10 | 10M split，额外有 plan 层和 `plans` 字段 |

普通 split 中，和 evaluation / loader 直接相关的 sample 顶层字段如下：

| 字段 | 含义 | 是否给 method |
| --- | --- | --- |
| `conversation_id` | conversation 级样本 id，也是 memory 隔离 id | 是 |
| `chat` | 真正给 method 的对话历史；普通 split 中是 batch 列表，每个 batch 内是 message 列表 | 是 |
| `probing_questions` | stringified Python dict，解析后是 10 类 memory ability 的问题和评分私有字段 | 只给 `question` 文本和 ability key |

普通 split 的 `chat` 层级是：

```text
row / conversation_id
  -> chat = [batch_1, batch_2, ...]
     -> batch = [message_1, message_2, ...]
        -> message = {role, content, id, index, question_type, time_anchor}
```

message 字段含义如下：

| 字段 | 含义 | 是否给 method |
| --- | --- | --- |
| `role` | 说话方，通常是 `user` 或 `assistant` | 是 |
| `content` | 消息正文 | 是 |
| `id` | message id，可用于 provenance / source 对齐 | 是，作为 metadata |
| `index` | 原始索引，例如 `1,1` | 是，作为 metadata |
| `question_type` | 用户消息类型，例如 `main_question`、`followup_question`、`answer_ai_question`；assistant 消息常为空 | 是，作为 metadata |
| `time_anchor` | 时间锚点，例如 `March-15-2024`；可作为 session/message timestamp | 是，作为 metadata/timestamp |

10M split 的字段和普通 split 不完全一样：

| 字段 | 含义 | 是否给 method |
| --- | --- | --- |
| `conversation_id` | 10M conversation 的 row id / 隔离 id | 是 |
| `chat` | plan-keyed 对话结构：`list[holder]`，每个 holder 只有一个非空 `plan-N`，其值是 `list[batch -> turns -> message]` | 是，但 loader 要先拆 plan |
| `probing_questions` | 同普通 split，stringified Python dict | 只给 `question` 文本和 ability key |
| `plans` | 10M 的 plan-level 容器；可用其中的 `chat` 辅助按 plan 读取对话，其他元信息不作为 method 输入 | 默认否，除非 loader 用其中的 `chat` 做普通形态转换 |

10M 中 `chat` 和 `plans[*].chat` 是同一批对话内容的两种形态：顶层 `chat` 已经接近官方
中间格式，带 `plan-1` 到 `plan-10` 和 `turns`；`plans[*].chat` 则是每个 plan 内的普通
`batch -> message` 形态。官方 `download_dataset.py` 会逐 plan 写出 `plan-N/chat.json`，
再用 `combine_10m_chats` 合成 conversation 级 plan-keyed `chat.json`。因此 10M 的
评测隔离仍然是 `conversation_id`，plan 只是同一个超长 conversation 内的子结构；loader
可以按 plan 流式写入同一个 namespace，但不应默认把 plan 拆成独立评测样本。

`probing_questions` 解析后固定 10 类 ability，每类通常 2 个问题：

| ability key | 中文理解 |
| --- | --- |
| `abstention` | 信息缺失时是否拒答/说明无信息 |
| `contradiction_resolution` | 是否识别并处理矛盾信息 |
| `event_ordering` | 是否恢复事件/话题出现顺序 |
| `information_extraction` | 事实、实体、细节抽取 |
| `instruction_following` | 长期遵循用户指令 |
| `knowledge_update` | 新信息出现后是否更新旧事实 |
| `multi_session_reasoning` | 跨多个 batch/session 的推理 |
| `preference_following` | 个性化偏好遵循 |
| `summarization` | 长期主题概括 |
| `temporal_reasoning` | 显式/隐式时间关系推理 |

`probing_questions` 里只有 `question` 是 method public input；`rubric`、`ideal_response`、
`ideal_answer`、`answer`、`ideal_summary`、`source_chat_ids`、`conversation_references`、
`plan_reference`、`why_unanswerable` 等都属于 scorer/report 私有字段。

### 评测隔离情况

BEAM 必须按 `conversation_id` 隔离。普通 split 中不要把 batch/session 单独隔离成
conversation，因为 probing questions 可能考察跨 batch 的更新、排序和长期推理。10M 中也
不要把 plan 默认隔离成独立 conversation；plan 只能作为同一 `conversation_id` 下的子结构
metadata 或流式 ingestion 单元。若为了工程诊断临时做 `conversation_id + plan_id` 拆分，
那属于非官方 ablation，需要在 run manifest 里显式标注。

### Metric 计算方式

BEAM 的主体评分不是 exact match，而是 rubric-based LLM judge。

| Metric | 解释 |
| --- | --- |
| Rubric-nugget score | 每个 probing question 带一组原子 rubric nuggets。Judge LLM 逐 nugget 判断回答是否满足，语义分数为 `1.0` 完全满足、`0.5` 部分满足、`0.0` 不满足。 |
| Question score | 一个 question 下所有 rubric-nugget score 的平均值。 |
| Ability score | 同一 memory ability 下所有 questions 的平均值。BEAM 通常按 10 类 ability 展开报告，例如 knowledge update、temporal reasoning、preference following。 |
| Overall score | 对 ability score 或 question score 再做整体平均，用于总排名。 |
| Event ordering score | `event_ordering` 单独处理：先把模型输出的事件列表与 reference events 对齐，再计算事件覆盖和顺序一致性；官方聚合时对该 ability 使用归一化 Kendall tau-b，而不是普通 rubric judge score。 |

需要注意：BEAM 的 judge prompt 语义允许 `0.5` partial credit，但当前本地官方代码里部分函数有把 score cast 成 `int` 的风险。后续真正接入 scorer 时要决定是严格复刻代码，还是按论文语义修正为 float。

### Method adapter 接口

第一版可以继续使用当前 retrieve-first 协议。

```python
def add(conversation: Conversation) -> None:
    """写入一个完整 BEAM conversation。

    参数:
        conversation: 已由 framework loader 构造好的 conversation 对象。
            conversation.id 对应 BEAM 的 conversation_id。
            conversation.messages 是从 BEAM chat 按原始顺序展平后的 user/assistant message 序列。
            message.metadata 应保留 id、index、time_anchor、batch_number、turn_group_index、
            plan_id、question_type 等公开字段。

    adapter 需要实现的功能:
        1. 清空或切换到当前 conversation 的独立 namespace。
        2. 按原始 message 顺序写入 memory。
        3. 保留必要的时间、batch/session、plan 和 turn-group metadata，供后续
           temporal / event-ordering / multi_session_reasoning 问题检索使用。

    返回:
        None。写入后的 memory state 留在 adapter 内部或外部存储中。
    """
```

```python
def retrieve(question: Question) -> AnswerPromptResult:
    """基于已写入的 BEAM conversation 回答一个 probing question。

    参数:
        question: framework 构造的问题对象。
            question.id 建议由 conversation_id + ability + index 组成。
            question.text 是 probing question 的公开问题文本。
            question.category 是 ability key，例如 temporal_reasoning、knowledge_update。
            question.metadata 只能放公开信息，例如 difficulty、ability 标签。

    adapter 需要实现的功能:
        1. 在当前 conversation namespace 内检索相关 memories。
        2. 组织 answer LLM 所需的 prompt messages。
        3. 不得读取 rubric、ideal_answer、source_chat_ids 等 evaluator private labels。

    返回:
        AnswerPromptResult:
            prompt_messages: 交给 framework answer LLM 的完整 messages。
            answer_prompt: prompt_messages 的兼容文本视图。
            metadata: 可包含 retrieved memories、memory_context、debug trace 等非私有信息。
    """
```

## 2. MemoryAgentBench

### Dataset 数据结构

MemoryAgentBench 的核心单位不是自然多 session conversation，而是一条 dataset row：

| 字段 | 含义 | 是否给 method |
| --- | --- | --- |
| `context` | 长文本、长对话、示例流、事实流等统一后的记忆材料 | 是，通常切 chunk 后逐步写入 |
| `question` | 对该 context 的测试问题 | 是 |
| `answer` / `answers` / `reference` | 规则指标或 judge 使用的参考答案 | 否 |
| `metadata.source` | 子任务来源，决定 prompt 模板和 metric | runner 可见，可作为公开 task metadata |
| `qa_pair_ids` | artifact / resume / judge 对齐用 id | runner/scorer 可见 |
| `metadata` 中的 keypoints / reference summary | judge 私有材料 | 否 |

它覆盖多种 source，输入形态包括长文本 QA、LongMemEval-like 对话、ICL examples、ReDial 推荐、InfBench summary 等。`context` 会被切成 chunks，method 需要按原始顺序写入。

### 评测隔离情况

MemoryAgentBench 按 dataset row 隔离：

- `1 row = 1 context = 1 个独立 memory state`。
- 同一个 context 的所有 chunks 必须写入同一个 memory state。
- 同一个 context 的多个 questions 可以共享该 context memory。
- 不同 context 之间必须隔离，不能把前一个 row 的 memory 带到下一个 row。
- chunk 顺序是语义的一部分，不能打乱。

### Metric 计算方式

MemoryAgentBench 不是单一 metric benchmark。它把多个已有长上下文/agent memory 任务统一到 memory construction + QA/evaluation 流程里，因此 metric 由 `source` 决定。

| Metric | 适用任务 | 解释 |
| --- | --- | --- |
| `exact_match` | ICL classification、DetectiveQA 等 | 归一化后预测答案必须与任一 gold answer 完全一致。通常可聚合为 Accuracy。 |
| `substring_exact_match` | RULER QA、FactConsolidation 等 | 归一化后 gold 是 prediction 子串，或 prediction 是 gold 子串，即算命中。适合短答案 QA。 |
| Token F1 / ROUGE-L | 部分开放式 QA 或长答案任务 | 按 token overlap 或 ROUGE-L 衡量预测与参考答案的重合程度；多个 gold 时通常取最大值。 |
| Recall@5 | ReDial recommendation | 模型输出 top-5 推荐电影后，与 gold movie id/name 对齐，计算 top-5 是否命中。这里评估的是最终推荐结果，不是 memory retrieval recall。 |
| LongMemEval LLM judge accuracy | LongMemEval-like QA | GPT-4o judge 按 question type 判断回答是否正确，最终是 `correct_count / total_questions`。 |
| InfBench summary LLM judge F1 | InfBench summary | Judge 分别看 fluency、keypoint recall 和 sentence precision，最后合成为 summary F1。 |

因此 MemoryAgentBench 的 evaluator 需要一个 source-aware metric router：同一个 method prediction artifact 里必须保留 `source`、`context_id`、`question_id` 和 prediction，才能选对 scorer。

### Method adapter 接口

可以先兼容 `add(conversation) + retrieve(question)`，但更贴近该 benchmark 的接口是 text/chunk stream。

```python
def add_text(context_id: str, text: str, metadata: dict | None = None) -> None:
    """向当前 context 的 memory state 写入一个 chunk。

    参数:
        context_id: 当前 dataset row 的隔离 id。所有同 context chunks 使用同一个 context_id。
        text: framework 已经构造好的待记忆文本。通常是 source-specific memorize prompt
            包装后的 chunk，而不是原始未说明用途的裸文本。
        metadata: 可选公开 metadata，例如:
            source: 子任务来源，如 longmemeval、redial、infbench。
            chunk_index: 当前 chunk 在 context 内的顺序。
            split: benchmark split 名。

    adapter 需要实现的功能:
        1. 按 chunk_index 顺序写入 memory。
        2. 使用 context_id 做 namespace 隔离。
        3. 不要求解析所有 source 的内部结构，但必须把 text 作为可检索记忆材料保存。
        4. 对超长 context 支持增量写入，不能假设一次性塞进 LLM prompt。

    返回:
        None。
    """
```

```python
def retrieve(question: Question) -> AnswerPromptResult:
    """基于当前 context memory 回答 MemoryAgentBench 问题。

    参数:
        question: 问题对象。
            question.text 是用户问题。
            question.metadata["context_id"] 指向当前 row。
            question.metadata["source"] 决定输出格式，例如分类 label、推荐列表、长摘要。

    adapter 需要实现的功能:
        1. 只在当前 context_id 的 memory 中检索。
        2. 根据 source 选择或配合 framework 生成正确 answer prompt。
        3. 对 ReDial 等任务保留可解析的 top-k 推荐输出；对 summary 任务支持长答案。
        4. 不读取 keypoints、reference summary 等 judge private labels。

    返回:
        AnswerPromptResult:
            prompt_messages: 用于 answer LLM 的完整 messages。
            metadata: 建议包含 retrieved chunks / source ids / memory context。
    """
```

## 3. MemoryBench

### Dataset 数据结构

MemoryBench 是 feedback-driven continual learning / memory adaptation benchmark。它不是每个 test item 自带一段独立历史，而是先用 train split 构建经验记忆，再在 test split 上评测迁移效果。

| 数据部分 | 关键字段 | 用途 |
| --- | --- | --- |
| train split | `dialog`、`dialog_mistral`、`implicit_feedback` 等 | 构建或更新 memory |
| test split | `input_prompt` 或 `input_chat_messages` | 提问并生成答案 |
| corpus dataset | LoCoMo / DialSim corpus | 作为 static corpus 注入 memory |
| `info` | golden answer、episode、labels、metadata | scorer private labels，默认不给 method |
| dataset config | metric、max output length、evaluator profile | runner / evaluator 使用 |

官方有 off-policy、stepwise off-policy、on-policy、training performance 等流程。最重要的主流程是 off-policy：先写入 train feedback dialogs，再回答 test prompts。

### 评测隔离情况

MemoryBench 的隔离粒度和 LoCoMo 类 benchmark 不同：

- 不是每个 test question 独立建 memory。
- train split 形成的是 run-level / dataset-level 共享经验记忆。
- test split 只读这个经验记忆。
- 对 LoCoMo / DialSim corpus dataset，需要在基础 train memory 上临时注入 static corpus。
- stepwise off-policy 会分 batch 追加 memory，并在每个 checkpoint 重新评测。
- on-policy 会由 user simulator 生成 feedback dialog，再追加写入 memory。

因此 MemoryBench 更适合专属 runner，而不是直接塞进 conversation-QA runner。

### Metric 计算方式

MemoryBench 的 metric 分两层：先按每个 dataset 的原生指标算分，再做 domain/task 级归一化聚合。

| Metric / 聚合 | 解释 |
| --- | --- |
| Single dataset metric | 每个 dataset 使用自己的 `test_metrics`。例如 LoCoMo 用 token F1，DialSim 用 accuracy，LexEval 用 ROUGE-L，WritingPrompts 用 METEOR。 |
| LLM judge score | HelloBench、NFCats、部分 DialSim fallback、LimitGen 等需要 evaluator LLM 判断 checklist、正确性或 1-5 分评分。 |
| Critic / model-based score | WritingBench 使用本地/vLLM critic model 评分；IdeaBench、JRE-L 等会混合 BERTScore、可读性和 LLM rating/ranking。 |
| Domain summary | 按 Open、Legal、Academic 等领域聚合。由于底层 metric 不同，官方会先做 min-max normalization 或 z-score，再平均。 |
| Task-shape summary | 按 LiSo、SiLo、LiLo、SiSo 聚合，分别表示 Long-Short、Short-Long、Long-Long、Short-Short 输入输出形态。Figure 3 的 7 个扇区就是 3 个 domain summary + 4 个 task-shape summary。 |

对我们框架来说，MemoryBench 不能只实现一个 `accuracy` evaluator。它需要多 metric family：规则指标、传统 NLP 指标、LLM judge、本地 critic，以及最终的归一化 summary。

### Method adapter 接口

官方 baseline 接口很多，但面向我们的框架不应全部暴露给普通用户。推荐把复杂流程放进 MemoryBench runner，method adapter 只实现泛化后的 `add(memory_input) + retrieve(query)`。

```python
def add(memory_input: MemoryInput) -> None:
    """写入一段 MemoryBench 记忆输入。

    参数:
        memory_input: runner 构造的通用记忆输入。
            source_type: 输入来源类型，例如 feedback_dialog、generated_feedback、static_corpus。
            messages: role/content messages，适合 feedback dialog 或对话 corpus。
            text: 裸文本 fallback，适合无法结构化的 corpus。
            dataset_name: 当前 MemoryBench dataset 名。
            sample_id: train/test 样本 id，例如 test_idx。
            timestamp: 可选时间字段。
            metadata: corpus_format、session_id、policy、step、lang 等公开字段。

    adapter 需要实现的功能:
        1. 将 train feedback dialog 写入长期 memory。
        2. 将 static corpus 按 runner 指定的时机写入 memory。
        3. 对 stepwise / on-policy 后续追加输入保持增量更新。
        4. 使用 runner 提供的 namespace，避免不同 dataset 或 corpus 注入互相污染。
        5. 不读取 info 中的 golden answer、labels 等 scorer private fields。

    返回:
        None。内置 method 可以额外保存 cache / trace，但轻量接口不要求。
    """
```

```python
def retrieve(query: MemoryQuery) -> AnswerPromptResult:
    """基于 MemoryBench 已构建的经验记忆回答一个 train/test prompt。

    参数:
        query: runner 构造的查询对象。
            text: 单轮 input_prompt。
            messages: 可选 multi-message input_chat_messages。
            dataset_name: 当前 dataset。
            lang: en / zh，用于选择 answer prompt 语言。
            retrieve_k: 可选检索条数。
            metadata: task、domain、sample_id 等公开信息。

    adapter 需要实现的功能:
        1. 从当前 run-level memory 中检索相关经验、反馈、corpus。
        2. 生成或返回 answer LLM 所需 prompt messages。
        3. 保留 retrieved_memories trace，方便 artifact 审计。
        4. 不负责 off-policy/on-policy 调度、feedback agent、metric aggregation，这些由 runner 完成。

    返回:
        AnswerPromptResult:
            prompt_messages: answer LLM 输入。
            metadata: retrieved_memories、memory_context、trace 等。
    """
```

内置 method 深度接入时可以额外实现：

| 可选能力 | 作用 |
| --- | --- |
| `save_state()` / `load_state()` | 复用 off-policy train memory cache |
| `clear_trace()` / `get_trace()` | 保存每题检索 trace |
| corpus isolation profile | 复现官方 corpus-copy / 临时注入流程 |

## 4. HaluMem

### Dataset 数据结构

HaluMem 是 uuid/user 级连续会话，并把 memory hallucination 诊断拆成三个 operation-level 任务：Memory Extraction、Memory Updating、Memory Question Answering。

每行 JSONL 是一个 user：

| 字段 | 含义 | 是否给 method |
| --- | --- | --- |
| `uuid` | user 级隔离 id | 是 |
| `persona_info` | 初始用户画像 | 默认不直接注入完整 profile |
| `sessions` | 按时间排序的连续 sessions | 是 |
| `memory_points` | gold memory / updated memory | scorer private labels |
| `qa_pairs` | QA 问题及答案 | 问题给 method，答案给 scorer |

session 内部包含 `session_id`、`start_time`、`end_time`、`dialogue` 等。dialogue turn 只有 `role` 和 `content` 是 method 写入 memory 的核心输入。

### 评测隔离情况

HaluMem 是 uuid 级连续评测，不是 session 隔离：

```text
for user in dataset:
    reset_user(uuid)
    for session in chronological order:
        add_dialogue(uuid, session)
        evaluate extraction for this session
        evaluate updating / QA questions attached to this session
```

关键隔离规则：

- 不同 `uuid` 必须隔离。
- 同一个 `uuid` 下 sessions 按时间顺序持续累积 memory。
- QA 不是等全部 sessions 结束后才问，而是在对应 session 写入后触发。
- Extraction 必须是 session-specific，不能返回全局所有 memory。
- Updating 和 QA 从当前 user 的全局 memory state 中检索。

### Metric 计算方式

HaluMem 的指标与三个 operation 对应：Memory Extraction、Memory Updating、Memory QA。

| Metric | 所属任务 | 解释 |
| --- | --- | --- |
| `recall(all)` | Memory Extraction | 非 interference gold memory 中，被完整抽取出来的比例。Judge 对每条 gold memory 的 integrity 打 `2/1/0`，只有完整抽取计入普通 recall。 |
| `weighted_recall(all)` | Memory Extraction | 按 gold memory importance 加权，部分抽取可计半分，更细地衡量关键信息是否被写入。 |
| `target_accuracy(all)` | Memory Extraction | 系统抽取出的 target memories 中，有多少确实对应 gold memory；接近 precision。 |
| `weighted_accuracy(all)` | Memory Extraction | 对所有 extracted memories 的 accuracy 平均，衡量抽取记忆的总体可信度。 |
| `interference_accuracy(all)` / FMR | Memory Extraction | 干扰信息不应被写入记忆。该比例越高，说明系统越能抵抗 false memory / interference。 |
| `memory_extraction_f1` | Memory Extraction | 使用 `target_accuracy` 和 `recall` 的调和平均，综合衡量抽取是否又全又准。 |
| `correct_update_memory_ratio` | Memory Updating | 更新类问题中，被 judge 判为 Correct 的比例。 |
| `hallucination_update_memory_ratio` | Memory Updating | 更新结果中出现幻觉或错误更新的比例，越低越好。 |
| `omission_update_memory_ratio` | Memory Updating | 应更新但没有更新的比例，越低越好。 |
| `correct_qa_ratio` | Memory QA | QA 回答被 judge 判为 Correct 的比例。 |
| `hallucination_qa_ratio` / `omission_qa_ratio` | Memory QA | QA 中错误编造或遗漏关键记忆的比例，越低越好。 |

HaluMem 的 QA 不是字符串 exact match，而是 LLM judge 基于 question、reference answer、key memory points 和 system response 做 Correct / Hallucination / Omission 分类。

### Method adapter 接口

HaluMem 完整接入需要 operation-level 接口。

```python
def reset_user(user_id: str) -> None:
    """初始化或清空一个 HaluMem user namespace。

    参数:
        user_id: HaluMem 的 uuid。不同 uuid 必须对应不同 memory namespace。

    adapter 需要实现的功能:
        1. 确保后续 add / retrieve 只影响该 user。
        2. 清除上一个 user 的 memory 或切换到独立 namespace。

    返回:
        None。
    """
```

```python
def add_dialogue(
    user_id: str,
    session_id: str,
    dialogue: list[dict],
    start_time: str | None,
    end_time: str | None,
) -> AddDialogueResult:
    """写入一个 session 的对话，并更新当前 user 的 memory state。

    参数:
        user_id: 当前 uuid。
        session_id: 当前 session id，用于 extraction 对齐和 artifact。
        dialogue: role/content turn list，只包含 method 可见的 user/assistant 对话。
        start_time: session 开始时间，可写入 timestamp metadata。
        end_time: session 结束时间，可写入 timestamp metadata。

    adapter 需要实现的功能:
        1. 按 dialogue 顺序写入当前 user 的 memory。
        2. 从当前 session 中抽取新 memories。
        3. 将新 memories 合并或更新到 user 全局 memory state。
        4. 保留 session_id 到 extracted memories 的映射，供 get_dialogue_memory 使用。

    返回:
        AddDialogueResult:
            session_id: 当前 session id。
            extracted_memories: 可选，当前 session 新抽取出的 memories。
            metadata: 写入 trace、token、latency 或 method-specific state。
    """
```

```python
def get_dialogue_memory(
    user_id: str,
    session_id: str,
    add_result: AddDialogueResult | None = None,
) -> list[str]:
    """返回指定 session 中系统抽取出的 memories，用于 Memory Extraction 评分。

    参数:
        user_id: 当前 uuid。
        session_id: 需要评估 extraction 的 session。
        add_result: add_dialogue 的返回值；如果 adapter 已在 add_result 中返回 extracted_memories，
            可以直接复用。

    adapter 需要实现的功能:
        1. 只返回当前 session 新抽取出的 memories。
        2. 不返回该 user 全局所有 memories。
        3. 保持 memory 文本可被 judge 与 gold memory point 对齐。

    返回:
        list[str]: session-specific extracted memories。
    """
```

```python
def retrieve(user_id: str, query: str, top_k: int) -> list[str]:
    """从当前 user 的全局 memory state 检索 memories。

    参数:
        user_id: 当前 uuid。
        query: 检索 query。Updating 使用 gold updated memory 文本作 query；QA 使用问题文本作 query。
        top_k: 返回 memory 数量上限。HaluMem 中 Updating 通常 top_k=10，QA 通常 top_k=20。

    adapter 需要实现的功能:
        1. 只检索当前 user 的全局 memory state。
        2. 返回与 query 最相关的 memories。
        3. 保留检索顺序，方便 scorer 和 answer prompt 构造。

    返回:
        list[str]: 检索到的 memory 文本；也可在内部 artifact 中保留结构化 memory id / score。
    """
```

## 5. MemBench

### Dataset 数据结构

MemBench 是 message-stream / conversation-stream + multiple-choice QA。核心单位是 trajectory：

| 字段 | 含义 | 是否给 method |
| --- | --- | --- |
| `tid` | trajectory id，隔离 namespace | 是 |
| `message_list` | 按时间顺序逐条写入 memory 的输入流 | 是 |
| `QA.question` | 最终测试问题 | 是 |
| `QA.choices` | A/B/C/D 选项 | 是 |
| `QA.answer` | 正确选项 | scorer private label |
| `QA.target_step_id` | gold evidence step id | scorer private label；仅用于 recall |

两类输入场景：

- Participation / FirstAgent：每个 step 是 user+agent 对话 dict。
- Observation / ThirdAgent：每个 step 是观察到的 user message string。

### 评测隔离情况

MemBench 必须按 `tid` 隔离：

- 每个 `tid` 是一条独立 trajectory。
- `message_list` 中每个 step 按顺序写入同一个 tid namespace。
- 最终 QA 只允许检索当前 tid 的 memories。
- 如果计算 retrieval recall，adapter 必须返回能映射回原始 local `step_id` 的 source ids。
- 不能使用全局 memory 混跑所有 tid，否则 Accuracy 和 Recall 都会失真。

### Metric 计算方式

MemBench 的核心指标更轻量，主要服务于 personal agent memory 的选择题评测和 evidence 追踪。

| Metric | 解释 |
| --- | --- |
| Memory Accuracy | 所有问题都是 multiple-choice。模型最终输出的选项字母与 `QA.ground_truth` 完全一致则为 1，否则为 0；整体 accuracy 是正确样本数除以总样本数。 |
| Memory Recall | 如果 method 返回 `memory_index` / retrieved source step ids，官方会与 `QA.target_step_id` 对齐，计算命中的 gold evidence step 比例。它评估的是检索证据是否命中，不是最终答案是否正确。 |
| Memory Capacity | 观察 memory 内容或 token 规模增长时，Memory Accuracy 是否下降。官方会记录 `(token_count, correct_or_not)`，再按规模画曲线或分桶分析。 |
| Memory Efficiency | 官方主要记录写入时间 WT 和读取时间 RT。WT 是平均 memory store/write time，RT 是平均 recall/retrieve time。我们框架可以额外记录 token、调用次数、retrieved context tokens 和 answer latency。 |

因此 MemBench 的 scorer 可以先做纯 Accuracy；但如果要完整复现论文分析，adapter 必须返回可映射回 `message_list` local step id 的检索 provenance。

### Method adapter 接口

MemBench 推荐接口是 trajectory-aware memory stream。

```python
@dataclass
class MemoryEvent:
    """MemBench 中一条待写入 memory 的事件。"""

    tid: str
    step_id: int
    role: str
    user: str | None = None
    agent: str | None = None
    text: str | None = None
    metadata: dict | None = None
```

```python
def add(tid: str, event: MemoryEvent) -> None:
    """向指定 tid 的 trajectory memory 写入一个 step。

    参数:
        tid: trajectory id。必须作为 namespace 使用。
        event: 当前 step。
            event.step_id 是当前 tid 内的 local step id。
            event.role 可区分 dialogue_turn 或 user_message。
            event.user / event.agent 用于 Participation scenario。
            event.text 用于 Observation scenario。
            event.metadata 可保存时间、question type、原始字段等公开信息。

    adapter 需要实现的功能:
        1. 只写入当前 tid namespace。
        2. 保存 event 与 step_id 的映射。
        3. 对 FirstAgent 场景写入 user+agent 对话。
        4. 对 ThirdAgent 场景写入观察到的 user message。

    返回:
        None。
    """
```

```python
@dataclass
class RetrievalResult:
    """MemBench 检索结果。"""

    text: str
    retrieved_source_step_ids: list[int]
    metadata: dict | None = None
```

```python
def retrieve(tid: str, query: str) -> RetrievalResult:
    """在当前 tid 的 memory 中检索和 QA 相关的 evidence。

    参数:
        tid: 当前 trajectory id。
        query: QA.question 文本，可由 runner 拼入 choices 或 time 信息。

    adapter 需要实现的功能:
        1. 只检索当前 tid namespace。
        2. 返回可放入 answer prompt 的 memory context。
        3. 如果支持 recall，必须返回原始 message_list local step_id。
        4. 不得读取 QA.answer 或 QA.target_step_id。

    返回:
        RetrievalResult:
            text: 检索到的 memory context，可交给 answer LLM。
            retrieved_source_step_ids: 与原始 message_list 对齐的 local step ids。
            metadata: 可选检索分数、memory ids、trace。
    """
```

## 6. PersonaMem

### Dataset 数据结构

PersonaMem 是 persona-oriented multi-session long-context multiple-choice QA。官方发布版按
context length 分成 32k、128k、1M 三档；每档都有 question CSV 和 shared context JSONL。

| 数据文件 | 关键字段 | 用途 |
| --- | --- | --- |
| `questions_32k/128k/1M.csv` | `persona_id`、`question_id`、`question_type`、`topic`、`user_question_or_message`、`all_options`、`correct_answer`、`shared_context_id`、`end_index_in_shared_context` | 每行是一道 multiple-choice personalization probe。 |
| `shared_contexts_32k/128k/1M.jsonl` | `{shared_context_id: list[OpenAI-style message]}` | 提供可见长期历史；每条 message 是 `role/content`。 |

PersonaMem 的 public input 是：

```text
shared_contexts[shared_context_id][:end_index_in_shared_context]
+ user_question_or_message
+ all_options
```

private label 是 `correct_answer`。`distance_to_ref_*`、`num_irrelevant_tokens` 等字段只用于
分组分析，不是 method 可见 evidence。发布版没有 gold evidence turn id，因此不能自然计算
retrieval recall。

`shared_contexts` 中的 `system` message 很重要，它通常是 `Current user persona: ...`。
官方 direct long-context evaluation 会把它作为 public context 一起喂给模型；如果我们做
memory-module profile，不能默认丢弃这些 persona system messages。

### 评测隔离情况

官方隔离粒度不是 `persona_id`，而是：

```text
(benchmark_size, shared_context_id)
```

每道题只能看到该行 `end_index_in_shared_context` 之前的 messages。同一个
`shared_context_id` 下有多道题，且 checkpoint 位置可能不同；推荐按 `end_index` 升序增量
推进 memory，而不是每道题重复灌入完整 prefix。

`persona_id` 级隔离只能作为非官方 stress profile。原因是同一个 persona 可能有多个
shared context / context variant；混合后可能引入未来信息、重复信息或冲突偏好，从而破坏
原始 `correct_answer` 标签语义。

### Metric 计算方式

PersonaMem 主指标是 multiple-choice accuracy：

```text
accuracy = 正确选项数 / 总问题数
```

官方 parser 会从模型输出中解析 `(a)`、`(b)`、`(c)`、`(d)` 或唯一字母选项，并与
`correct_answer` 比较。它没有 LLM judge，也没有原生 retrieval recall。

常见分组分析包括：

| 维度 | 字段 |
| --- | --- |
| context length | 32k / 128k / 1M |
| personalization ability | `question_type` |
| topic | `topic` |
| reference 距离 | `distance_to_ref_in_blocks`、`distance_to_ref_in_tokens` |
| persona | `persona_id` |

### Method adapter 接口

PersonaMem 官方默认不需要 memory method。官方脚本是 direct long-context LLM：

```python
answer(messages: list[{"role": str, "content": str}]) -> str
```

如果我们把它改造成 memory-module benchmark，最关键的新要求是 **message-level incremental
prefix ingest**：

```python
def add_messages(memory_scope_id: str, messages: list[dict]) -> None:
    """写入 shared_context[cursor:end_index] 这一段 OpenAI-style message delta。"""
```

```python
def retrieve(question: str, choices: list[str]) -> AnswerPromptResult:
    """在当前 shared_context namespace 中检索，构造 multiple-choice answer prompt。"""
```

对当前框架的冲击：

1. `add(conversation)` 可以概念上覆盖，但 runner 不能只支持“一次性完整 conversation 写入”。
2. 需要按 shared context checkpoint 增量写入，防止未来信息泄露和重复写入。
3. 需要 multiple-choice reader，而不是 LoCoMo/LongMemEval 的 free-form answer reader。
4. 不能把 probe question 或模型回答写回 memory，否则会污染同 checkpoint 或后续 checkpoint。

## 7. MemoryArena

### Dataset 数据结构

MemoryArena 是 multi-session agentic memory benchmark，不是静态 conversation-QA。每个
`data.jsonl` row 是一个 task entry，里面的 `questions` 是有序 subtasks，而不是普通 QA。

当前本地 HuggingFace 数据包含五个 config：

| Config | 样本数 | 数据形态 |
| --- | ---: | --- |
| `bundled_shopping` | 150 | 一个 task 有 6 个 product subtasks；gold 是 `target_asin` 和 attributes。 |
| `group_travel_planner` | 270 | 一个 group 有 base person 和多个 joining travelers；gold 是每人的 daily plan。 |
| `progressive_search` | 221 | 本地 HF 有 `questions/answers`，但当前 repo `run_search.py` 仍走 BrowseComp-Plus 外部环境。 |
| `formal_reasoning_math` | 40 | 一篇 paper / task 下有多个 math subtasks，每个 subtask 有 background。 |
| `formal_reasoning_phys` | 20 | 结构同 math，用于 physics reasoning。 |

本地数据合计 701 条 task rows；论文 Table 1 写 766，说明当前 HF / repo preview 版本和论文
版本存在差异，后续正式接入必须记录 dataset revision。

### 评测隔离情况

MemoryArena 的隔离单位是 task/group/paper/query，而不是 conversation：

| 环境 | 推荐隔离 id |
| --- | --- |
| shopping | `shopping:{category/task_id}` |
| travel | `travel:{data_idx}` |
| formal | `formal:{paper_name or row_id}` |
| search | `search:{query_id}` |

同一个 task 内 subtasks 按顺序执行。前面 subtask 的行动轨迹、环境反馈、最终结果会写入
memory，后面的 subtask 再检索这些 memory 来辅助行动。

### Evaluation 流程

MemoryArena 的共同结构是 Memory-Agent-Environment loop：

```text
for task in dataset:
    initialize memory namespace
    for subtask in ordered subtasks:
        query = 当前 subtask / env observation / background+problem
        memory_context = memory.retrieve_context(query)
        actor_prompt = benchmark runner 构造(task, env, tool, memory_context)
        agent 在 environment 中行动
        env 返回 observation / reward / judgement
        memory.add_chunk(task/action/observation/reward chunk)
    scorer 计算 PS / SR / task-specific metrics
```

官方 memory server 把 `retrieve_context()` 和简单包装合并成 `wrap_user_prompt()`：

```python
wrap_user_prompt(question) -> "<memory_context>...</memory_context>\nUser: {question}"
```

但代码中 RAG、Mem0、A-Mem、LightMem、MIRIX 等实现都直接拿传入的 `prompt/question`
字符串做检索；`User: {prompt}` 只是包装层。因此后续我们接入时应该拆分职责：

```text
memory module: add_chunk + retrieve_context
benchmark runner: build_actor_prompt
```

同一个 task family 内的 actor prompt 模板基本稳定，变化的是 subtask 变量：

| 任务 | 检索 query | Prompt 变量 |
| --- | --- | --- |
| Travel | 当前 traveler query | name、round、memory context、previous plans / judgement |
| Formal reasoning | `background + problem` | background、problem、memory context |
| Shopping | 当前 env observation/state | page state、product step、purchase history、memory context |
| Search | search query / decomposed query | search trace、retrieved docs、tool config |

### Metric 计算方式

论文统一指标：

| Metric | 含义 |
| --- | --- |
| PS / Task Progress Score | 一个 task 内正确完成的 subtask 比例，再对 task 平均。 |
| SR / Task Success Rate | 整个 task 是否全部成功。 |
| SR@k | 第 k 个 subtask 的成功率，用于观察 interdependent depth 的衰减。 |
| Latency | subtask/task completion time。 |

各子环境还有自己的指标：shopping 的 reward / item success rate，travel 的 PS/SPS/SR，
formal 的 progress score / passrate@k，search 的 accuracy / recall / tool calls /
calibration error。

### Method adapter 接口

MemoryArena 不能直接塞进当前 conversation-QA runner。更合理的新 task family 是：

```text
agentic-memory-environment
```

method 最小接口建议是：

```python
def initialize(memory_scope_id: str) -> None: ...
def add_chunk(chunk: str, metadata: dict | None = None) -> None: ...
def retrieve_context(query_or_observation: str) -> str: ...
```

其中：

| 参数 | 含义 |
| --- | --- |
| `memory_scope_id` | 当前 task/group/paper/search query 的隔离 namespace。 |
| `chunk` | 上一个 subtask/action 的 task、action、observation、reward/judgement 轨迹文本。 |
| `query_or_observation` | 当前 subtask instruction、env observation 或 background+problem。 |

MemoryArena 带来的核心架构结论是：它要求我们把 “memory 管理” 和 “agent prompt / environment
loop” 分开。memory method 只应负责写入和检索；工具、环境规则、动作格式、actor prompt
都应属于 benchmark runner。

## 汇报时可以强调的接口分层

这 7 个 benchmark 说明，不能只用一个“conversation-QA”概念解释所有 agent memory evaluation。更稳的说法是：

| 层级 | 代表 benchmark | Method 最小接口 |
| --- | --- | --- |
| Conversation QA | BEAM | `add(conversation) + retrieve(question)` |
| Context/chunk stream QA | MemoryAgentBench | `add_text(context_id, chunk) + retrieve(question)` |
| Feedback continual learning | MemoryBench | `add(memory_input) + retrieve(query)`，runner 负责 train/test/on-policy |
| Operation-level memory diagnosis | HaluMem | `reset_user + add_dialogue + get_dialogue_memory + retrieve` |
| Trajectory evidence QA | MemBench | `add(tid,event) + retrieve(tid,query)`，需要 source step id |
| Prefix-checkpoint personalization QA | PersonaMem | `add_messages(scope_id, message_delta) + retrieve(question)`，需要 multiple-choice reader |
| Agentic memory-environment loop | MemoryArena | `initialize + add_chunk + retrieve_context`，runner 负责 actor prompt、tools 和 env step |

对框架设计的结论：

1. LoCoMo / LongMemEval / BEAM 类任务可以继续走 retrieve-first conversation-QA。
2. MemoryAgentBench 需要把 conversation 扩展成 memory stream 或 chunk stream。
3. MemoryBench 需要新的 feedback continual-learning runner，不适合硬塞进 LoCoMo runner。
4. HaluMem 需要 operation-level API，否则只能做 QA 子集，不能完整评估 extraction/update hallucination。
5. MemBench 可以接入，但必须保留 trajectory namespace 和 source step provenance。
6. PersonaMem 可以作为 personalization QA 接入，但 runner 必须支持 shared-context checkpoint
   增量写入和 multiple-choice scoring。
7. MemoryArena 属于更大的 agentic-memory-environment 类任务，短期只作为架构压力来源记录；
   接入前要先设计 environment runner，而不是扩展 conversation-QA runner。
