# MemoryBench Benchmark 调研卡片

更新日期：2026-06-29

## 1. 一句话结论

MemoryBench 是一个 **feedback-driven continual learning / memory adaptation** benchmark：它不是单纯的“注入一段 conversation 后回答 QA”，而是先用 train split 的模拟用户反馈对话构建/更新 memory，再在 test split 上回答多任务、多领域问题。它仍可在 method 侧尽量抽象为 `add(memory_input) + retrieve(query)`，但复杂性必须放到 MemoryBench 专属 runner：runner 负责 train/test split、off-policy/on-policy、static corpus 注入、stepwise update、feedback agent、memory cache 和多 metric evaluator。

如果用 LoCoMo 做类比：LoCoMo 的核心单位是 `conversation`，MemoryBench 的核心单位是一次 `dataset/run` 的经验记忆环境。LoCoMo 测“能不能记住某段历史事实”，MemoryBench 测“能不能从历史反馈中形成经验、偏好或策略，并迁移到 test 任务”。

## 2. Dataset 数据结构

### 2.1 本地材料与官方入口

| 类型 | 路径 / 来源 | 调研结论 |
| --- | --- | --- |
| 官方仓库 | `/Users/wz/Desktop/memoryBenchmark/third_party/benchmarks/MemoryBench` | README 明确该仓库是 lightweight benchmark interface + baseline implementations；完整论文复现实验代码另在 `LittleDinoC/MemoryBench-code`。 |
| 论文 PDF | `/Users/wz/Desktop/memoryBenchmark/third_party/benchmarks/MemoryBench/MemoryBench.pdf` | 论文定义 benchmark 目标、off-policy/on-policy/stepwise 流程、默认模型与参数。 |
| 本地 dataset | `/Users/wz/Desktop/memoryBenchmark/data/MemoryBench` | 来自 HuggingFace `THUIR/MemoryBench`，包含 28 个 dataset config、train/test Arrow split，以及 LoCoMo/DialSim corpus。 |
| 官方 dataset loader | `/Users/wz/Desktop/memoryBenchmark/third_party/benchmarks/MemoryBench/src/dataset/utils.py` | Arrow 里的多个字段是字符串，官方 loader 会把 `dialog*`、`implicit_feedback*`、`input_chat_messages`、`info` 转回 Python object。 |
| 官方 dataset registry | `/Users/wz/Desktop/memoryBenchmark/third_party/benchmarks/MemoryBench/configs/datasets/each.json` | 每个 dataset 的 class、test metrics、max output length、部分 evaluator 模型配置都在这里。 |

### 2.2 Dataset 列表、split 规模与 metric

本地 `data/MemoryBench/dataset/` 下共有 28 个 dataset。以下计数直接由本地 Arrow split 读取。

| Dataset | Train | Test | 是否有 static corpus | 输入字段 | Test metric |
| --- | ---: | ---: | --- | --- | --- |
| `Locomo-0` | 20 | 5 | 是 | `input_prompt` | `f1` |
| `Locomo-1` | 20 | 5 | 是 | `input_prompt` | `f1` |
| `Locomo-2` | 20 | 5 | 是 | `input_prompt` | `f1` |
| `Locomo-3` | 20 | 5 | 是 | `input_prompt` | `f1` |
| `Locomo-4` | 20 | 5 | 是 | `input_prompt` | `f1` |
| `Locomo-5` | 20 | 5 | 是 | `input_prompt` | `f1` |
| `Locomo-6` | 20 | 5 | 是 | `input_prompt` | `f1` |
| `Locomo-7` | 20 | 5 | 是 | `input_prompt` | `f1` |
| `Locomo-8` | 20 | 5 | 是 | `input_prompt` | `f1` |
| `Locomo-9` | 20 | 5 | 是 | `input_prompt` | `f1` |
| `DialSim-bigbang` | 66 | 17 | 是 | `input_prompt` | `accuracy` |
| `DialSim-friends` | 66 | 17 | 是 | `input_prompt` | `accuracy` |
| `DialSim-theoffice` | 67 | 17 | 是 | `input_prompt` | `accuracy` |
| `HelloBench-Academic&Knowledge-QA` | 170 | 43 | 否 | `input_prompt` | `avg_score` |
| `HelloBench-Academic&Knowledge-Writing` | 65 | 17 | 否 | `input_prompt` | `avg_score` |
| `HelloBench-Creative&Design` | 181 | 47 | 否 | `input_prompt` | `avg_score` |
| `IdeaBench` | 200 | 50 | 否 | `input_prompt` | `bert_score`, `llm_rating_score`, `llm_novelty_ranking_score`, `llm_feasibility_ranking_score` |
| `JRE-L` | 200 | 50 | 否 | `input_prompt` | `Rouge-L`, `BERTScore-F1`, `CLI`, `FKGL`, `DCRS` |
| `JuDGE` | 200 | 50 | 否 | `input_chat_messages` | legal multi-metrics |
| `LexEval-Judge` | 200 | 50 | 否 | `input_prompt` | `rougel` |
| `LexEval-QA` | 200 | 50 | 否 | `input_prompt` | `rougel` |
| `LexEval-Summarization` | 200 | 50 | 否 | `input_prompt` | `rougel` |
| `LimitGen-Syn` | 200 | 50 | 否 | `input_chat_messages` | `accuracy`, `rating` |
| `NFCats` | 200 | 50 | 否 | `input_prompt` | `score` |
| `WritingBench-Academic&Engineering` | 133 | 34 | 否 | `input_prompt` | `score` |
| `WritingBench-Creative&Design` | 336 | 86 | 否 | `input_prompt` | `score` |
| `WritingBench-Politics&Law` | 160 | 41 | 否 | `input_prompt` | `score` |
| `WritingPrompts` | 200 | 50 | 否 | `input_prompt` | `meteor` |

官方还用两个 group config 组织实验：

| Group 类型 | 配置文件 | 分组 |
| --- | --- | --- |
| Domain | `configs/datasets/domain.json` | `Open-Domain` 17 个、`Legal` 5 个、`Academic&Knowledge` 6 个 |
| Task shape | `configs/datasets/task.json` | `Long-Short` 16 个、`Short-Long` 3 个、`Long-Long` 6 个、`Short-Short` 3 个 |

MemoryBench 因此有三种运行粒度：

| 运行粒度 | 含义 | Memory 隔离方式 |
| --- | --- | --- |
| `single` | 只跑一个 dataset，例如 `Locomo-0` 或 `HelloBench-Academic&Knowledge-QA`。 | 一个 dataset 对应一个 run-level memory state。 |
| `domain` | 按领域跑多个 dataset，例如 `Open-Domain`。 | 多个 dataset 的 train dialogs 会合并进同一个 group/run memory state。 |
| `task` | 按输入输出长度形态跑多个 dataset，例如 `Long-Short`。 | 多个 dataset 的 train dialogs 会合并进同一个 group/run memory state。 |

这里的 `run` 指“一次实验运行”：给定 `dataset_type`、`set_name`、`memory_system` 和配置后，官方会构建一个对应的 memory cache、prediction artifact 和 summary。它不是 dataset 本身，而是“一场实验”的状态容器。

### 2.3 通用字段

MemoryBench 的样本不是单一 schema，但 `BaseDataset` 在加载后强约束这些字段：

| 字段 | 类型 | 是否给 method | 作用 |
| --- | --- | --- | --- |
| `test_idx` | int | 是 | 样本 id。官方 memory 写入时也把 train 样本的 `test_idx` 作为 conversation id。 |
| `input_prompt` | str | 是 | 大多数 dataset 的 test-time user prompt。 |
| `input_chat_messages` | list[message] | 是 | 少数 chat-style dataset 使用，例如 `JuDGE`、`LimitGen-Syn`。 |
| `dataset_name` | str | 是 | 当前 dataset 名，用于 routing、summary 和 prediction 校验。 |
| `lang` | str | 是 | `en` 或 `zh`，官方 agent 根据它选择英文/中文 answer prompt。 |
| `info` | dict | 否，只给 scorer | 评测标签、rubric、gold answer、criteria 等 private 字段。不能进入 method public input。 |

本地 28 个 dataset 的 test 输入字段已经逐个确认：

| Test 输入字段 | Dataset |
| --- | --- |
| `input_prompt` | `DialSim-bigbang`、`DialSim-friends`、`DialSim-theoffice`、`HelloBench-Academic&Knowledge-QA`、`HelloBench-Academic&Knowledge-Writing`、`HelloBench-Creative&Design`、`IdeaBench`、`JRE-L`、`LexEval-Judge`、`LexEval-QA`、`LexEval-Summarization`、`Locomo-0..9`、`NFCats`、`WritingBench-Academic&Engineering`、`WritingBench-Creative&Design`、`WritingBench-Politics&Law`、`WritingPrompts` |
| `input_chat_messages` | `JuDGE`、`LimitGen-Syn` |

官方 `BaseDataset.get_initial_chat_messages(test_idx)` 会把 `input_prompt` 包装成单条 user message：

```python
[{"role": "user", "content": input_prompt}]
```

如果样本没有 `input_prompt`、但有 `input_chat_messages`，则直接把 `input_chat_messages` 作为 answer agent 的输入 messages。`dataset_name`、`lang`、`test_idx` 是 public routing metadata；`info` 只能进入 evaluator/scorer。

`input_chat_messages` 应理解为“chat-format query”，不是一段要预先写入 memory 的历史。
例如本地样本中，`JuDGE` 是 `system: 你是一个法律助理` + `user: 案件事实...`；
`LimitGen-Syn` 是 `system: 生成论文限制的格式/类别要求` + `user: paper title/abstract...`。
接入我们框架时不要把每条 message 拆成多个 question，而应把整组 messages 作为当前
test query 的 prompt messages：

```text
MemoryBench test item
-> query_messages = input_chat_messages
-> query_text = 最后一条 user message，可用于 retrieval key
-> answer prompt = query_messages + retrieved memory context
```

如果复用当前 `Question` 数据结构，至少需要在 `Question.metadata["input_messages"]`
保留完整 `input_chat_messages`；更干净的做法是为 MemoryBench runner 定义
`MemoryQuery(messages, text, dataset_name, lang, test_idx)`。

### 2.4 Train split 的 feedback dialog 字段

MemoryBench 的核心是：用 train split 的反馈对话让 memory method “学习经验”，再在 test split 上回答问题。

非 corpus dataset 通常有这些 train 字段：

| 字段 | 结构 | 用途 |
| --- | --- | --- |
| `dialog` | list[message]，每条包含 `role`、`content` | 默认 off-policy 训练对话。README 说明由 Qwen3-8B assistant 与 Qwen3-32B user simulator 生成。 |
| `implicit_feedback` | list[feedback] | 与 `dialog` 对应的隐式反馈日志。常见字段包括 `round`、`implicit_actions`、`satisfaction_score`、`terminated`。 |
| `dialog_mistral` | list[message] | Mistral-Small-3.2-24B-Instruct-2506 user simulator 版本的训练对话。 |
| `implicit_feedback_mistral` | list[feedback] | Mistral simulator 版本的隐式反馈日志。常见字段包括 `round`、`implicit_action`、`terminated`。 |

注意：当前官方 `src/off-policy.py` 默认对非 corpus dataset 只读取 `dialog`，没有默认读取 `dialog_mistral`；Mistral 版本是 dataset 提供的可选反馈来源。

对非 corpus dataset，官方 off-policy train 阶段写入 method 的内容可以确定为 train row 的 `dialog` 字段。`implicit_feedback`、`dialog_mistral`、`implicit_feedback_mistral` 和 `info` 不会被默认 off-policy runner 写入 method。

官方构造的 `total_dialogs` 不是一个扁平 message list，而是一个 dialog 列表：

```python
[
    {
        "test_idx": 0,
        "dataset": "HelloBench-Academic&Knowledge-QA",
        "dialog": [
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."}
        ]
    },
    ...
]
```

也就是说，`total_dialogs` 的元素是一条 train sample 的 feedback dialog；每个 `dialog` 内部才是多轮 role/content messages。

### 2.5 Corpus dataset 的特殊字段：LoCoMo / DialSim

LoCoMo 和 DialSim 不只依赖 train feedback dialog，还依赖静态多 session corpus。

| Dataset | Corpus 路径 | Raw corpus 结构 | 官方转换 |
| --- | --- | --- | --- |
| `Locomo-0..9` | `data/MemoryBench/corpus/Locomo-*.jsonl` | 每行 `text` 是 JSON 字符串，内部有 `conversation`，包含 `session_i_date_time` 和 `session_i` turns。turn 有 `speaker`、`dia_id`、`text`，部分有图片字段。 | `load_from_hf()` 解析 JSON，并把 `corpus_format` 设为 `locomo`。 |
| `DialSim-*` | `data/MemoryBench/corpus/DialSim-*.jsonl` | 每行 `text` 是按 `[Date: ..., Session #...]` 分段的剧集对话文本。 | `change_dialsim_conversation_to_locomo_form()` 转成 LoCoMo-like `session_i_date_time` / `session_i` 格式，并把 `corpus_format` 设为 `dialsim`。 |

Corpus dataset 的 train split 不使用通用 `dialog` 字段，而是包含按 baseline 预生成的对话字段：

| 字段形态 | 示例 | 含义 |
| --- | --- | --- |
| `dialog_{baseline}` | `dialog_a_mem`、`dialog_memoryos`、`dialog_bm25`、`dialog_embedder`、`dialog_mem0` | 某个 baseline 在该问题上生成的 feedback dialogue。 |
| `implicit_feedback_{baseline}` | `implicit_feedback_a_mem` 等 | 与 baseline-specific dialog 对应的反馈。 |
| `dialog_{baseline}_dialog` | `dialog_bm25_dialog`、`dialog_embedder_dialog` | session-level baseline 版本。 |

本地抽样显示：`Locomo-0` 有 `dialog_mem0`，但 `DialSim-friends` 没有 `dialog_mem0`；这与官方 registry 中 Mem0 跳过 `Open-Domain` / `Long-Short` 的说明一致，原因是 Mem0 在这些组合上太慢。

Corpus 的作用不是评分辅助字段，而是 method public input 的一部分。可以把 MemoryBench 的记忆来源分成两类：

| 来源 | 作用 |
| --- | --- |
| train feedback dialogs | 让 method 学“经验”：用户偏好、错误反馈、任务策略、回答风格等。 |
| static corpus | 给 corpus dataset 提供“事实背景”：LoCoMo/DialSim 这类任务需要具体历史事实，只有 feedback dialogs 不足以回答 test questions。 |

官方不是把 corpus 当一个大字符串直接塞给 method，而是先解析成 `session_i_date_time` / `session_i` / turn，再 dispatch 到 solver 的 corpus 注入函数：

```python
load_corpus_to_memory(solver, dataset)
-> solver.memory_locomo_conversation(conversation, session_cnt)
或 solver.memory_dialsim_conversation(conversation, session_cnt)
```

因此 corpus 注入是 method-specific 的：例如 MemoryOS solver 会遍历 session/turn 并调用 `memory_system.add_memory(user_input=..., agent_response=..., timestamp=...)`；Mem0 solver 会遍历 session/turn 并调用 `memory_system.add(messages=[...], metadata=..., user_id="user")`。

### 2.6 `info` private labels

| Dataset 类别 | `info` 关键字段 | 是否可给 method |
| --- | --- | --- |
| LoCoMo | `golden_answer`、`category`、`evidence` | 否，只给 scorer。 |
| DialSim | `golden_answer`、`episode`、`session_num`、`conversation_num` | `golden_answer` 否；其他 metadata 若用于定位 corpus 也需谨慎，官方 scorer 使用。 |
| LexEval / WritingPrompts | `golden_answer` | 否。 |
| HelloBench | `checklist` | 否，LLM evaluator 使用。 |
| WritingBench | `criteria` | 否，critic evaluator 使用。 |
| LimitGen-Syn | `ground_truth`、`category` | 否。 |
| JuDGE | `golden_answer` | 否。 |
| IdeaBench | `paperId`、`title`、`abstract` | `abstract` 是评价 reference；不能给 method。 |
| JRE-L | `sc-title`、`sc-abstract`、`pr-title`、`pr-abstract` | `pr-abstract` 是 reference；不能给 method。 |
| NFCats | 空 dict | 无私有标签。 |

## 3. Evaluation 流程

### 3.1 Off-policy：主实验流程

官方 `src/off-policy.py` 是最重要的 evaluation 入口。流程如下：

1. 根据 `--dataset_type single|domain|task` 和 `--set_name` 加载一个或多个 dataset。
2. 构建 train memory dialogs：
   - 非 corpus dataset：读取每个 train row 的 `dialog`。
   - corpus dataset：按 `get_dialog_key(memory_system)` 读取 baseline-specific `dialog_*`。
   - 将 `{test_idx, dialog, dataset}` 加入 `total_dialogs`，固定 seed=42 shuffle。
3. 构建 solver 和 memory cache：
   - `SolverFactory.create(...)` 根据 `--memory_system` 加载 agent/solver。
   - `create_or_load_memory(total_dialogs)` 对每个 train dialog 调 `agent.add_conversation_to_memory(dialog, test_idx)`。
   - 完成后 `save_memories()`、`write_memory_records()`，并用 `saved.txt` 标记 cache 可复用。
4. Test prediction：
   - 非 corpus dataset：直接 `memory_solver.predict_test(dataset)`。
   - corpus dataset + `wo_memory`：走 `predict_test_with_corpus()`，把能塞进上下文窗口的 corpus session 拼到 prompt。
   - corpus dataset + memory method：先复制 train memory cache，再调用 `load_corpus_to_memory(single_solver, dataset)` 把 static corpus 加进 memory，然后在该 dataset test split 上预测。
5. 保存 artifact：
   - `run_config.json`
   - `predict.json`
   - `evaluate_details.json`
   - `summary.json`

这里和 LoCoMo/LongMemEval 最大不同点是：**MemoryBench 的 memory 输入主要来自 train split feedback dialog，不是 test question 所属的一个单独 conversation；test split 是只读评测。**

#### 3.1.1 Off-policy 的隔离与 corpus 注入时机

Off-policy 下，官方先构建基础 train feedback memory，再按 dataset 预测 test：

```text
加载 selected datasets
-> 收集所有 train dialogs
-> shuffle
-> 写入基础 memory cache
-> 遍历每个 dataset 做 test
```

如果当前 dataset 没有 corpus：

```text
直接使用基础 memory cache 预测 test split
```

如果当前 dataset 有 corpus 且 method 不是 `wo_memory`：

```text
复制基础 memory cache
-> 在复制出来的临时 solver 里注入当前 dataset 的 corpus
-> 预测当前 dataset 的 test split
-> 临时 solver 用完即丢弃
```

这里的“复制基础 memory cache”是为了让每个 corpus dataset 都共享同一批 train feedback experience，但不让某个 dataset 的 static corpus 污染另一个 dataset。例如在 `Open-Domain` group 中，`Locomo-0` 测试前会把基础 memory 复制一份并注入 `Locomo-0` corpus；`Locomo-1` 测试前会重新复制基础 memory 并注入 `Locomo-1` corpus，而不是继续沿用已经注入过 `Locomo-0` corpus 的 memory。

因此 off-policy 的隔离规则是：

| Setting | Train feedback memory | Corpus memory |
| --- | --- | --- |
| `single` | 只来自该 dataset 的 train dialogs。 | 若有 corpus，测试前注入该 dataset corpus。 |
| `domain` / `task` | 来自该 group 内多个 dataset 的 train dialogs，合并成一个基础 memory。 | 每个 corpus dataset 测试前复制基础 memory，并只注入当前 dataset corpus。 |

### 3.2 Stepwise off-policy

官方 `src/stepwise_off-policy.py` 用于观察训练数据规模增长时的 performance curve：

1. 先把 corpus dataset 的 static corpus 加进 memory。
2. 在未加入任何 train feedback dialog 前，对完整 test split 评测一次，输出到 `begin/`。
3. 将 train dialogs 按 batch 分组，默认 `batch_size=100`。
4. 每加入一个 batch，就调用 `agent.add_conversation_to_memory(...)` 更新 memory。
5. 每个 step 都重新预测完整 test set 并评估。

这要求 runner 能支持“持续追加 memory + 多次 evaluation checkpoint”，不是当前 LoCoMo/LongMemEval 的一次性 ingest。

### 3.3 On-policy

官方 `src/on-policy.py` 用于在线反馈模拟：

1. 加载 feedback agent，默认配置在 `configs/memory_systems/feedback.json`。
2. 创建一个 `memory_solver`。
3. 对 selected datasets 中所有 `dataset.has_corpus == True` 的 dataset，先调用 `load_corpus_to_memory(memory_solver, dataset)`。
4. 每一步从 train set 采样若干 item。
5. 先让 memory system 对当前 train item 生成回答。
6. feedback agent 模拟用户反馈，最多 `max_rounds` 轮。
7. 将生成出来的新 `dialog` 和 `implicit_feedback` 写入 memory。
8. 对完整 test set 评测并保存每一步结果。

这意味着完整 MemoryBench 不只是 `add(train_dialog) -> test QA`，还要求框架支持 user-simulator loop 和 incremental memory update。

on-policy 里的“环境”不是 WebArena / tool-use 那种外部可交互环境，而是一个模拟用户反馈
闭环：assistant/actor 只和 feedback agent 做多轮文本交互。除 corpus dataset 预先注入的
static corpus 外，actor 看到的信息主要是当前 train item 的 input messages、自己 memory
检索到的内容、上一轮用户反馈文本；不直接看到 `info` 里的 gold answer / rubric /
criteria。feedback agent 则会读取完整 `data` 和 `dataset_instance`，可使用 scorer 私有
标签来决定正负反馈或生成追问。

#### 3.3.1 On-policy 的真实训练循环

官方 `predict_single_data(...)` 的 on-policy train sample 流程是：

```text
1. dataset.get_initial_chat_messages(test_idx) 得到 train input messages
2. solver.predict_single_data(dataset, data) 让 method 先回答
3. 把 method answer 追加为 assistant message
4. feedback_agent.get_feedback(messages, data, dataset_instance) 生成用户反馈
5. 如果 feedback agent 判断 should_stop，则结束该 train sample
6. 如果未结束，追加 user feedback
7. 用 solver.agent.llm.generate_response(messages=chat_messages) 生成 assistant continuation
8. 重复，直到 max_rounds 或 terminated
9. 保存生成的 dialog 与 implicit_feedback
10. 调 agent.add_conversation_to_memory(dialog, test_idx) 写入 memory
```

注意第 7 步：官方代码后续 assistant continuation 直接调用 `solver.agent.llm.generate_response(...)`，不是再次调用 `solver.agent.generate_response(...)`。这意味着 on-policy 官方实现隐式要求 method agent 暴露可用的 `self.llm`，但这属于官方 runner 的耦合设计；如果我们未来实现自己的 MemoryBench runner，更合理的是让 runner 自己持有 feedback/assistant LLM，不强迫 method adapter 暴露内部 LLM。

因此，单个 train item 的 on-policy 交互可以理解为：

```text
初始 user/system prompt
-> actor 用当前 memory 回答一次
-> feedback agent 根据对话 + 私有评测信息生成用户反馈
-> actor 继续回答
-> 若 feedback agent 结束或达到 max_rounds，整段 dialog 写入 memory
```

这段 dialog 才是 on-policy 训练阶段新产生并写入 memory 的“记忆轨迹”。

#### 3.3.2 On-policy 的 corpus 注入差异与污染风险

on-policy 的 corpus 处理和 off-policy 不同。官方 `src/on-policy.py` 是在训练循环开始前直接把 selected datasets 中所有 corpus 加进同一个 `memory_solver`：

```python
for dataset in dataset_lists:
    if dataset.has_corpus:
        load_corpus_to_memory(memory_solver, dataset)
```

因此：

| Setting | On-policy corpus 行为 |
| --- | --- |
| `single` | 只注入该 dataset 的 corpus，不存在跨 dataset corpus 混入。 |
| `domain` / `task` | 该 group 内所有 corpus dataset 的 corpus 会注入同一个 `memory_solver`，存在跨 corpus dataset 混入同一 memory state 的官方行为。 |

这和 off-policy 的“复制基础 memory 后只注入当前 dataset corpus”不同。后续如果严格复现 MemoryBench on-policy，应按官方代码记录该行为；如果我们从框架严谨性出发，也可以把它标为官方 lightweight implementation 的潜在 corpus contamination risk，并在自研 runner 中提供 per-dataset corpus isolation profile。

### 3.4 Training performance

官方 `src/train_performance.py` 用 train split 评测训练集表现，用于观察过拟合或灾难遗忘。它与 off-policy 类似，但 prediction split 是 `train` 而不是 `test`。

### 3.5 Answer artifact

官方 prediction 的最小格式为：

| 字段 | 含义 |
| --- | --- |
| `test_idx` | test row id |
| `messages` | 实际送入 answer LLM 的 messages；memory agent 会修改最后一条 user message，把检索到的 memory/context 拼进去 |
| `response` | answer LLM 输出 |
| `retrieved_memories` | agent 记录的检索 trace，用于调试 |
| `dataset` | 多 dataset group evaluation 时必须有 |

## 4. Metric 计算方式

### 4.1 单 dataset summary

`memorybench.summary_results("single", name, predicts, evaluate_details)` 对该 dataset 的 `test_metrics` 逐项取平均。prediction 必须至少包含 `test_idx`、`response`、`dataset`。

### 4.2 Domain / task group summary

对于 `dataset_type="domain"` 或 `"task"`：

1. 官方先对每个 dataset 单独评估。
2. 多 metric dataset 会通过 `evaluate_single_only_one_metric()` 合并成单一分数。
3. LoCoMo-0..9 会用 `summary_group_name="Locomo"` 合并为一个 normalization key。
4. 使用 `configs/final_evaluate_summary_wo_details.json` 中的 min/max、mu/sigma 做 min-max normalization 和 z-score aggregation。

论文主表的 off-policy 结果主要报告 domain/task 级 min-max normalized average 和 z-score，而不是只看某个 dataset 的原始 metric。

论文 Figure 3 的 7 个扇区不是 7 个互斥 dataset 类型，而是两套聚合视角并列展示：

| 图中标签 | 官方配置名 | 含义 |
| --- | --- | --- |
| `Open` | `domain/Open-Domain` | 开放域 dataset 聚合 |
| `Legal` | `domain/Legal` | 法律域 dataset 聚合 |
| `Academic` | `domain/Academic&Knowledge` | 学术/知识域 dataset 聚合 |
| `LiSo` | `task/Long-Short` | 长输入、短输出任务聚合 |
| `SiLo` | `task/Short-Long` | 短输入、长输出任务聚合 |
| `LiLo` | `task/Long-Long` | 长输入、长输出任务聚合 |
| `SiSo` | `task/Short-Short` | 短输入、短输出任务聚合 |

同一个原始 dataset 会同时属于一个 domain group 和一个 task-shape group，所以 Figure 3 是
3 个 domain summary + 4 个 task summary，而不是把 28 个 dataset 切成 7 个互斥大类。

### 4.3 各 dataset 的 metric

| Dataset / 类别 | Metric | 计算来源 |
| --- | --- | --- |
| LoCoMo | `f1` | `src/dataset/Locomo.py`：归一化、去标点、Porter stemming 后 token F1；category 1 多答案拆分取 max 后平均，category 5 先把选项映射成真实答案。 |
| DialSim | `accuracy` | `src/dataset/DialSim.py`：先 exact / punctuation-tolerant match；不匹配时用 LLM judge 判 Correct/Wrong。 |
| LexEval | `rougel` | `src/dataset/LexEval.py`：中文分词后 ROUGE-L。 |
| WritingPrompts | `meteor` | `src/dataset/WritingPrompts.py`：NLTK METEOR。 |
| HelloBench | `avg_score` | `src/dataset/HelloBench.py`：LLM evaluator 对 checklist item 打 0/0.25/0.5/0.75/1，取平均。 |
| IdeaBench | BERTScore + LLM rating/ranking | `src/dataset/IdeaBench.py`：按分隔符切候选 idea，BERTScore 对 reference abstract 选 best hypothesis，再读保存/计算的 LLM rating、novelty ranking、feasibility ranking；group summary 时可 LLM 合并为 1-10。 |
| JRE-L | `Rouge-L`, `BERTScore-F1`, `CLI`, `FKGL`, `DCRS` | `src/dataset/JRE-L.py`：ROUGE、BERTScorer、textstat readability；group summary 时可 LLM 合并成 1-10。 |
| JuDGE | legal multi-metrics | `src/dataset/JuDGE.py` + `src/dataset/judge/calc_score.py`：reasoning/judge 的 METEOR 和 BERTScore，crime/penalcode precision/recall/F1，time/amount score。 |
| LimitGen-Syn | `accuracy`, `rating` | `src/dataset/LimitGen.py`：解析 JSON `limitations`，LLM 检查 aspect/subtype 与相关性；group summary 用 `rating`。 |
| NFCats | `score` | `src/dataset/NFCats.py`：LLM judge 输出 1-5 整数。 |
| WritingBench | `score` | `src/dataset/WritingBench.py`：本地/vLLM critic 模型 `AQuarterMile/WritingBench-Critic-Model-Qwen-7B` 根据 criteria 评分。 |

### 4.4 是否可 artifact-only 复算

可以，但前提是保留：

1. 每条 prediction 的 `dataset`、`test_idx`、`response`。
2. 对应本地 dataset 和官方 evaluator 依赖。
3. LLM judge / critic evaluator 的运行配置和可用模型。

传统指标如 LoCoMo F1、LexEval ROUGE-L、WritingPrompts METEOR 可离线复算；DialSim、HelloBench、IdeaBench 合并、JRE-L 合并、LimitGen、NFCats、WritingBench 等需要 evaluator LLM 或 critic model，因此不是纯离线 deterministic metric。

## 5. Answer LLM / Judge LLM 配置和 Prompt

### 5.1 Answer LLM 默认配置

官方 memory system config 位于 `configs/memory_systems/*.json`。

| 用途 | 默认模型 / 服务 | 参数 |
| --- | --- | --- |
| Memory system answer LLM | vLLM `Qwen/Qwen3-8B`，默认 base URL `http://localhost:12366/v1` | config 显式 `temperature=0.1`；`BaseLlmConfig` 默认 `top_p=0.1`、`top_k=1`、`max_tokens=2000`；论文写最大生成长度 2048。 |
| Feedback simulator | vLLM `Qwen/Qwen3-32B`，默认 base URL `http://localhost:12345/v1` | `feedback.json` 未显式写 temperature/max_tokens，继承 LLM config 默认值。 |
| Embedding | vLLM `Qwen/Qwen3-Embedding-0.6B`，默认 base URL `http://localhost:12377/v1` | `embedding_dim=1024`，用于 Embedder/Mem0；论文还说明 A-Mem/MemoryOS 使用各自默认 embedding，其中 MemoryOS 使用 `all-MiniLM-L6-v2`。 |
| WritingBench critic | `AQuarterMile/WritingBench-Critic-Model-Qwen-7B` | README 建议通过 vLLM 端口 12388 部署。 |

论文 Appendix A.3.2 明确：backbone LLM 使用 Qwen3-8B，temperature=0.1，top_p=0.1，top_k=1，最大生成长度 2048；RAG/A-Mem/Mem0 默认 `retrieve_k=5`，如果超上下文长度就逐步减少 retrieved entries。

### 5.2 Answer prompt

MemoryBench 没有一个完全统一的 answer prompt；prompt 是 memory system agent 的一部分。

| Method / 路径 | Prompt 行为 |
| --- | --- |
| `BM25Agent` / `EmbedderAgent` / `AMemAgent` | 检索 memory/context 后，把最后一条 user message 改写为 `Context + User + Based on the context...`；中文样本使用中文模板。 |
| `AMemAgent` | 先调用 `generate_query_llm(question)` 生成关键词，再用关键词检索 memory。 |
| `Mem0Agent` | 检索 `memories_str` 后，用 `User Memories + User input + Based on the memories...` 模板。 |
| `MemoryOSAgent` | 调用 MemoryOS 的 `get_user_prompt(query, lang)` 生成带 memory/profile/context 的 user prompt。 |
| `wo_memory` + corpus dataset | `predict_test_with_corpus()` 把能容纳的 static corpus session 拼成 `Context + User` prompt。 |

论文里展示的通用英文回答模板是 `User Memories: {memories_str}` + `User input: {query}` + 基于记忆回答，但代码中 BM25/A-Mem/Embedder 实际使用 `Context:` 模板。因此实现时应以官方代码为准，并在文档中记录论文/代码 prompt 口径差异。

### 5.3 Judge LLM / evaluator 配置和 prompt

| Evaluator | 配置来源 | Prompt / 配置 |
| --- | --- | --- |
| DialSim judge | `src/dataset/DialSim.py` | `SYS_PROMPT` 要求只输出 `Correct` 或 `Wrong`；OpenAI-compatible，env `EVALUATE_BASE_URL` / `EVALUATE_MODEL` / `EVALUATE_API_KEY`，temperature=0.2，top_p=0.1，max_tokens=1024。 |
| HelloBench judge | `src/dataset/HelloBench.py` | checklist evaluator prompt；OpenAI-compatible，env `EVALUATE_*`，temperature=0.8，max_tokens=4096。 |
| IdeaBench judge | `src/dataset/IdeaBench.py` | rating、novelty ranking、feasibility ranking，以及 group summary 合并 prompt；env `EVALUATE_*`，temperature=0.0，max_tokens=1024。 |
| JRE-L judge | `src/dataset/JRE-L.py` | 基于预计算 metrics 合并为 1-10 的 LLM-as-judge prompt；env `EVALUATE_*`，temperature=0.0，max_tokens=1024。 |
| LimitGen judge | `src/dataset/LimitGen.py` | aspect check、subtype classification、pair rating；env `EVALUATE_*`，temperature=0.8，max_tokens=4096。 |
| NFCats judge | `src/dataset/NFCats.py` | 1-5 分整数评分 prompt；env `EVALUATE_*`，temperature=0.0，max_tokens=1024。 |
| WritingBench judge | `src/dataset/WritingBench.py` | 使用本地/vLLM critic 模型和 `src/dataset/writingbench/prompt.py` 的 scoring prompt，不是普通 OpenAI judge。 |
| JuDGE | `src/dataset/judge/*` | 主要是结构抽取 + METEOR/BERTScore/precision/recall/F1/time/amount 规则，不是单一 LLM judge prompt。 |

注意：多处 evaluator 的具体 `EVALUATE_MODEL` 不是 repo 中固定值，而是环境变量传入；因此复现实验时必须记录 evaluator provider/model/base URL。

## 6. Method Adapter 接口需求

### 6.1 官方 MemoryBench baseline 接口

官方 `BaseSolver` / agent 体系隐含要求 method 至少提供：

| 能力 | 官方函数 / 位置 | 作用 |
| --- | --- | --- |
| 写入 feedback dialog | `agent.add_conversation_to_memory(messages, conversation_idx)` | 将 train split 中的 feedback dialog 写入 memory。 |
| 生成回答 | `agent.generate_response(messages, lang, retrieve_k)` | 对 test prompt 生成 answer；通常内部会检索 memory 并改写最后一条 user message。 |
| 保存 / 加载 memory | `save_memories()` / `load_memories()` | off-policy 先构建 train memory cache，再在 corpus dataset 上复制 cache 后追加 static corpus。 |
| 导出 memory records | `write_memory_records()` | 保存可审计 memory artifact。 |
| 检索 trace | `get_last_memory_trace()` | prediction artifact 中保存 `retrieved_memories`。 |
| corpus 注入 | `solver.memory_locomo_conversation(...)`、`solver.memory_dialsim_conversation(...)` | LoCoMo/DialSim 需要把 static corpus 加进 memory。 |
| 删除 / 回滚 corpus memory | `delete_conversation_memory()` | 部分 solver 支持删除刚注入的 corpus memory；MemoryOS 等不一定完整支持。 |

官方核心 agent 函数的输入输出如下：

| 函数 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| `add_conversation_to_memory(messages, conversation_idx)` | `messages: list[{"role","content"}]`，`conversation_idx: int|str` | `None` | 写入一条 train feedback dialog；on-policy 中也用于写入在线生成的 feedback dialog。 |
| `generate_response(messages, lang="en", retrieve_k=None)` | `messages` 来自 `input_prompt` 包装或 `input_chat_messages` 原文；`lang` 为 `en/zh`；`retrieve_k` 为检索条数 | `str` | method 内部通常检索 memory、改写最后一条 user message、调用 answer LLM。 |
| `save_memories()` | 无 | `None` | 保存 memory cache。 |
| `load_memories()` | 无 | `None` | 恢复 memory cache。 |
| `clear_last_memory_trace()` | 无 | `None` | 每题回答前清空检索 trace。 |
| `get_last_memory_trace()` | 无 | `list[dict]` | prediction artifact 写入 `retrieved_memories`。 |

如果要支持 corpus dataset，solver 还需要：

| 函数 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| `memory_locomo_conversation(conversation, session_cnt)` | 解析后的 LoCoMo-like corpus dict；session 数量 | `None` | 按 session/turn 写入 LoCoMo corpus。 |
| `memory_dialsim_conversation(conversation, session_cnt)` | 解析后的 DialSim-as-LoCoMo corpus dict；session 数量 | `None` | 按 session/turn 写入 DialSim corpus。 |

这些是官方 baseline 接口，不等于我们未来必须向用户暴露同样多的接口。

### 6.2 映射到我们当前框架

当前讨论后的框架方向是：不要照搬官方 MemoryBench 的多接口设计，而是尽量保留 method 侧轻量抽象：

```python
method.add(memory_input)
prompt = method.retrieve(query)
answer = framework_answer_llm(prompt)
```

MemoryBench 的复杂性应由 runner/predict 层承担。也就是说，runner 负责决定何时把 train feedback dialog、static corpus、on-policy generated feedback 转成 `memory_input` 并调用 `add(...)`；runner 也负责把 test/train prompt 转成 query 并调用 `retrieve(...) + answer LLM`。

如果只做 MemoryBench 的 **off-policy 子集**，当前 `BaseMemoryProvider.add(...) + retrieve(...)` 可以承载，但 `add` 的输入粒度需要从单纯 LoCoMo-style `Conversation` 泛化为 `MemoryInput` 或类似结构：

| MemoryBench 概念 | 我们当前可能的映射 | 风险 |
| --- | --- | --- |
| train split feedback dialog | `MemoryInput(source_type="feedback_dialog", messages=[...])` | 这不是 test question 的同一个 conversation，而是训练经验库；需要 run-level memory store，而不是 per-test-conversation 隔离。 |
| on-policy generated feedback dialog | `MemoryInput(source_type="generated_feedback", messages=[...])` | 由 feedback agent 在线生成，写入时机由 runner 控制。 |
| static corpus | `MemoryInput(source_type="static_corpus", messages/text=..., metadata={corpus_format, session_id, timestamp})` | LoCoMo/DialSim corpus 不是 feedback dialog，注入时机依赖 off-policy/on-policy profile。 |
| test prompt | `Question` | `input_chat_messages` 需要支持 multi-message question；不能只支持 plain string。 |
| method 检索结果 | `AnswerPromptResult` / `retrieve(question)` | MemoryBench 官方 method 往往把 prompt 构造视为 method 一部分；仍应允许 method 返回完整 answer prompt/messages。 |
| evaluator labels | private label store | `info` 绝不能给 method。 |

在这个设计下，MemoryBench 的统一逻辑可以表达为：

```text
off-policy:
  add(train feedback dialogs)
  add(static corpus, if needed)
  retrieve(test input) + answer LLM

on-policy:
  retrieve(train input) + answer LLM
  feedback agent 生成 feedback dialog
  add(generated feedback dialog)
  retrieve(test input) + answer LLM
```

因此 method adapter 不需要知道 off-policy/on-policy、stepwise、domain/task aggregation、feedback agent 或 evaluator。它只需要能把 runner 给出的 memory input 写入记忆，并基于 query 返回可用于 answer LLM 的 prompt/messages。

### 6.3 完整接入需要的新 runner 能力

MemoryBench 对当前框架的冲击比 LoCoMo/LongMemEval 大：

1. 需要 **train/test split memory construction**：先把 train dialogs 写入 memory，再回答 test questions。
2. 需要 **run-level memory store**：同一个 dataset/domain/task 的 train memory 是共享经验库，不是每个 test conversation 独立建库。
3. 需要 **static corpus injection**：LoCoMo/DialSim 要把 corpus 作为 declarative memory 加入 method。
4. 需要 **stepwise checkpoints**：每个 batch 更新后都评估完整 test set。
5. 需要 **on-policy user simulator loop**：method 回答 train item 后，feedback agent 继续生成用户反馈并写入 memory。
6. 需要 **多 metric evaluator family**：规则指标、BERT/Rouge/METEOR、LLM judge、本地 critic、group normalization。
7. 需要 **memory cache save/load**：否则 off-policy 和 corpus-copy 流程很难复现官方效率与结果。
8. 需要 **language-aware prompt**：官方 agent 根据 `lang` 切英文/中文模板。

### 6.4 对 method 的最小要求建议

面向我们未来接入 MemoryBench，可以分两层：

| 层级 | Method 需要实现 | 适用范围 |
| --- | --- | --- |
| 用户轻量 method | `add(memory_input)`、`retrieve(query)`，返回完整 `AnswerPromptResult` / prompt messages | 可覆盖 off-policy、on-policy、corpus 的大部分流程；复杂流程由 MemoryBench runner 管。 |
| 内置 method 深度接入 | 在轻量接口基础上额外支持 state/cache、corpus 隔离 profile、trace、细粒度 observation | 用于复现官方效率、降低重复注入成本、提供更完整 artifact。 |

`add` 的输入粒度应比当前 LoCoMo-style conversation 更细、更泛化。未来可考虑标准 `MemoryInput`：

| 字段 | 含义 |
| --- | --- |
| `source_type` | `feedback_dialog`、`generated_feedback`、`static_corpus`、`text_chunk` 等。 |
| `messages` | 多轮 role/content messages；适合 feedback dialog 和 corpus conversation。 |
| `text` | 裸文本 fallback；适合无法结构化的 chunk/corpus。 |
| `dataset_name` | 当前 MemoryBench dataset。 |
| `sample_id` | train/test sample id，例如 `test_idx`。 |
| `timestamp` | 可选时间字段。 |
| `metadata` | corpus format、session id、policy、step、lang 等非私有字段。 |

`retrieve` 的输入则应支持 multi-message query，因为 `JuDGE` 和 `LimitGen-Syn` 的 test 输入是 `input_chat_messages`，不是单字符串。

强约束：`info.golden_answer`、`info.criteria`、`info.checklist`、`info.abstract`、`info.evidence` 等 private fields 只能进入 scorer，不能进入 method public input。

## 7. 未确认项

1. 当前本地仓库 README 明确：该仓库是 lightweight interface；论文完整复现实验代码在 `LittleDinoC/MemoryBench-code`。如果后续要严格复现论文所有表格，需要再拉取并审计完整复现仓库。
2. 本地 `THUIR/MemoryBench` 主 dataset 有 28 个 config；论文正文/附录某些表述中出现的 dataset 名称与本地 registry 不完全一致，例如调研文本中提到过 `SciTechNews`，本地主数据配置中对应的是 `JRE-L`。实现时以本地 dataset + official code 为准，并把差异记录到实验说明。
3. README 说 2025-12-05 用户反馈模拟器升级为 Mistral-Small-3.2-24B-Instruct-2506；但官方默认 off-policy 代码仍读取 `dialog`，论文主实验也写 Qwen3-32B feedback simulator。dataset 同时提供 `dialog_mistral` / `implicit_feedback_mistral`，具体跑哪套反馈必须作为 profile 显式声明。
4. 多个 evaluator 的 judge model 通过 `EVALUATE_MODEL` 环境变量传入，repo 没有固定模型名；复现实验必须记录实际 evaluator model。
5. Corpus dataset 的 baseline-specific `dialog_*` 字段不是所有 method 都齐全；例如本地 DialSim 抽样未见 `dialog_mem0`，且 registry 默认跳过 Mem0 的 `Open-Domain` / `Long-Short`。
6. 官方代码中的 answer prompt 与论文展示的通用 prompt 不完全一致；adapter 应优先复用代码路径中的 method-specific prompt，而不是只按论文模板重写。
7. 当前我们的 conversation-QA runner 不应直接硬接 MemoryBench；应先把它作为新的 feedback continual-learning task family 设计，至少先支持 off-policy 子集后再考虑 stepwise/on-policy。
8. 官方 on-policy 在 group setting 下会把 selected datasets 的所有 corpus 注入同一个 `memory_solver`，不同于 off-policy 的 per-dataset corpus 临时副本隔离。后续如果接入 on-policy，需要决定是严格复现该行为，还是提供更严谨的 corpus isolation profile。
9. MemoryBench 官方接口较重，但我们当前设计倾向是不把这些接口全部暴露给用户；method 侧仍保持 `add(memory_input) + retrieve(query)`，新增复杂度放到 MemoryBench runner。
