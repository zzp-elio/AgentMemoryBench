# MemoryArena Benchmark 调研卡片

更新日期：2026-07-03

## 1. 一句话结论

MemoryArena 是一个 **multi-session agentic memory benchmark**，不是 LoCoMo / LongMemEval / PersonaMem 那种静态 conversation-QA。它评测的是 memory system 是否能在多轮 agent-environment 交互后，把早期 subtask 的行动轨迹、环境反馈、最终结果写入持久记忆，并在后续 interdependent subtasks 中检索出来指导 agent 行动。

它当前包含五个 HuggingFace config：

| HF config | 本地文件 | 当前本地样本数 | 任务类型 |
| --- | --- | ---: | --- |
| `bundled_shopping` | `data/MemoryArena/bundled_shopping/data.jsonl` | 150 | 多商品 bundle shopping，agent 逐步购买兼容商品。 |
| `group_travel_planner` | `data/MemoryArena/group_travel_planner/data.jsonl` | 270 | 多人组队旅行规划，后加入成员依赖前面成员/基础旅客计划。 |
| `progressive_search` | `data/MemoryArena/progressive_search/data.jsonl` | 221 | progressive web search；本地 HF 数据存在，但当前 repo 的 `run_search.py` 仍主要围绕 BrowseComp-Plus 外部环境和 qrel 文件运行。 |
| `formal_reasoning_math` | `data/MemoryArena/formal_reasoning_math/data.jsonl` | 40 | 同一论文/背景下的连续数学 reasoning subtasks。 |
| `formal_reasoning_phys` | `data/MemoryArena/formal_reasoning_phys/data.jsonl` | 20 | 同一论文/背景下的连续物理 reasoning subtasks。 |

MemoryArena 对我们当前框架的冲击很大：它不能只靠 `BaseMemoryProvider.add(conversation) + retrieve(question)` 跑起来。最小 method 侧能力更接近官方 memory server 的三接口：

```text
initialize(user_id, memory_system_name)
wrap_user_prompt(question) -> prompt with <memory_context>...</memory_context>
add(chunk)
```

其中 `wrap_user_prompt()` 不只是返回 memory items，而是直接返回被 memory context 包装后的 agent prompt；`add()` 写入的也不是普通 dialogue turn，而是 agent 在一个 subtask 或 action step 中产生的 task/action/observation/reward/judgement 文本 chunk。当前阶段按用户要求 **只调研，不接入**；后续如果接入，应作为新的 `agentic-memory-environment` task family 设计，而不是强行塞进 conversation-QA runner。

## 2. Dataset 数据结构

### 2.1 本地材料与路径

| 类型 | 路径 / 来源 | 调研结论 |
| --- | --- | --- |
| 官方仓库 | `third_party/benchmarks/MemoryArena` | preview version；README 明确说仍在 actively maintaining and improving。 |
| 论文 PDF | `third_party/benchmarks/MemoryArena/memoryarena.pdf` | 论文题为 “MemoryArena: Benchmarking Agent Memory in Interdependent Multi-Session Agentic Tasks”。 |
| 本地数据 | `data/MemoryArena` | 已从 HuggingFace `ZexueHe/memoryarena` 下载到本地。 |
| HF dataset README | `data/MemoryArena/README.md` | 描述五个 config 的统一字段：`id`、`questions`、`answers`、可选 `backgrounds` / `base_person` / `category`。 |

当前本地下载的真实数据总量是 701 条 task rows：

```text
150 + 270 + 221 + 40 + 20 = 701
```

论文 Table 1 写 MemoryArena 总任务数为 766。由于仓库 README 明确说代码仍在持续维护，当前本地 HF 数据和论文版本存在版本差异；后续若要复现实验，必须记录 dataset revision。

### 2.2 顶层统一结构

每个 `data.jsonl` 中一行是一个 **agentic task entry**，不是一条普通 QA。HF README 给出的共同抽象是：

```json
{
  "id": "...",
  "questions": ["subtask 1", "subtask 2", "..."],
  "answers": ["gold answer 1", "gold answer 2", "..."],
  "backgrounds": "optional background or list of backgrounds"
}
```

关键区别：

```text
questions[i] 不是普通 question，而是第 i 个 subtask/session 的任务指令。
answers[i] 是 scorer private label，不允许传给 method 或 agent。
backgrounds[i] 是 formal reasoning 中每个 subtask 的 public context。
```

### 2.3 `bundled_shopping`

本地字段：

```json
{
  "id": "0",
  "questions": ["Product 1 task prompt", "..."],
  "answers": [
    {
      "target_asin": "B00TUDFEW2",
      "attributes": ["Almond Flour", "Gluten Free", "..."]
    }
  ],
  "category": "baking_item_0"
}
```

本地统计：

| 字段 | 真实情况 |
| --- | --- |
| rows | 150 |
| `questions` 长度 | 固定 6 |
| `answers` 长度 | 固定 6，和 questions 对齐 |
| `category` | 当前 150 个唯一值，如 `baking_item_0`；官方 loader 会按 category prefix 分组。 |

官方中间格式不是直接使用 HF 行，而是在 `env/env_systems/web_shopping_env/runtime/runner/task_files.py` 中由 `_reconstruct_task_def_from_hf_row()` 重建：

```json
{
  "task_id": "baking_item_0",
  "task_type": "bundled_shopping",
  "agent_instruction": "... full multi-product instruction ...",
  "steps": [
    {
      "step": 1,
      "target_asin": "...",
      "requirements": {"attributes": [...], "price_constraints": {}}
    }
  ],
  "target_products": ["..."],
  "global_constraints": {"purchase_order": "sequence"}
}
```

评测时 public input 是 product-step instruction 和环境 observation；private label 是 `target_asin`、required attributes、price constraints。

### 2.4 `group_travel_planner`

本地字段：

```json
{
  "id": "1",
  "base_person": {
    "name": "Jennifer",
    "query": "I am Jennifer. Please help me plan a trip ...",
    "daily_plans": [
      {
        "days": 1,
        "current_city": "...",
        "transportation": "...",
        "breakfast": "...",
        "attraction": "...",
        "lunch": "...",
        "dinner": "...",
        "accommodation": "..."
      }
    ]
  },
  "questions": ["I am Eric. I'm joining Jennifer ...", "..."],
  "answers": [[{"days": 1, "...": "..."}]]
}
```

本地统计：

| 字段 | 真实情况 |
| --- | --- |
| rows | 270 |
| `questions` 长度 | min 5 / avg 6.92 / max 8 |
| `answers` 长度 | 与 questions 对齐；每个 answer 是一个 multi-day plan。 |
| `base_person` | public input；官方 runner 会先把 base person plan 写入 memory。 |

官方 loader `travel_planner_env/data_loader.py` 会把 questions 转成：

```json
{"round_idx": 1, "name": "Eric", "query": "..."}
```

answers 转成：

```json
{"round_idx": 1, "daily_plans": [...]}
```

### 2.5 `progressive_search`

本地 HF 字段：

```json
{
  "id": "0",
  "questions": ["search subtask 1", "..."],
  "answers": ["long answer / search result text", "..."]
}
```

本地统计：

| 字段 | 真实情况 |
| --- | --- |
| rows | 221 |
| `questions` 长度 | min 4 / avg 7.43 / max 16 |
| `answers` 长度 | 与 questions 对齐 |

注意：当前 repo 的 `run_search.py` 并没有直接读取 `ZexueHe/memoryarena` 的 `progressive_search` config。它围绕 BrowseComp-Plus environment 运行，依赖：

```text
env/env_systems/web_search_env/data/browsecomp_plus_decrypted.jsonl
topics-qrels/qrel_evidence.txt
Tevatron/browsecomp-plus-corpus
```

因此本地 HF `progressive_search` 数据和当前 `run_search.py` 之间存在实现口径差异。后续接入前必须先确认作者后续是否补齐了直接使用 `ZexueHe/memoryarena/progressive_search` 的 runner。

### 2.6 `formal_reasoning_math` / `formal_reasoning_phys`

本地字段：

```json
{
  "id": "0",
  "paper_name": "2503.19064",
  "backgrounds": ["LaTeX definitions and context for subtask 1", "..."],
  "questions": ["subtask problem 1", "..."],
  "answers": ["gold solution 1", "..."]
}
```

本地统计：

| config | rows | questions min/avg/max | 说明 |
| --- | ---: | --- | --- |
| `formal_reasoning_math` | 40 | 2 / 8.85 / 16 | 每行对应一篇 paper / task；每个 subtask 有对应 background。 |
| `formal_reasoning_phys` | 20 | 2 / 4.30 / 12 | 结构同 math。 |

public input 是 `backgrounds[i] + questions[i]`；private label 是 `answers[i]`。

## 3. Evaluation 流程

### 3.1 统一 Memory-Agent-Environment loop

论文和代码的共同流程是：

```text
for task in dataset:
    initialize memory namespace for this task/user
    for subtask/session in ordered subtasks:
        prompt = memory.wrap_user_prompt(current_subtask_or_observation)
        agent acts in environment, often with tool calls / multiple action steps
        env returns observation / reward / judgement
        memory.add(task/action/observation/reward chunk)
    score task success and progress
```

官方 memory client 是 `memory/client.py`：

```python
MemoryClient(user_id, memory_system_name, base_url)
wrap_user_prompt(question) -> {"prompt": "... <memory_context> ..."}
add(chunk: str)
```

这里最重要的是：MemoryArena 不是“把历史灌入 method，然后问一个 QA”。它是 **task agent 先检索 memory，再行动；行动后的轨迹再写回 memory；下一个 subtask 使用更新后的 memory**。

官方 `wrap_user_prompt()` 把两件事合并在一个接口里：

```text
1. 用传入的 prompt/question 字符串作为检索 query，取回 memory context。
2. 把 memory context 放进 <memory_context>...</memory_context>，并把原始 prompt 追加在后面。
```

这不是说 memory module 必须负责完整 actor prompt。代码里的 RAG、Mem0、A-Mem、
LightMem、MIRIX 等实现都直接使用传入的 `prompt` / `question` 字符串检索 memory；
`User: {prompt}` 或 `User Prompt: {prompt}` 只是官方 memory server 的简单包装层。对我们
自己的框架来说，更合理的拆分是：

```text
memory.retrieve_context(query_or_observation) -> memory_context
benchmark/agent.build_actor_prompt(task, env_observation, tool_spec, memory_context) -> actor prompt
```

也就是说，MemoryArena 给当前架构带来的核心需求是“memory query 可以是 subtask /
environment observation / background+problem，而不只是 QA question”，不是要求 memory
method 自己理解整个 environment prompt 体系。

### 3.2 retrieval / update 粒度

论文 Appendix B.1 明确说明：因为 subtasks 内部结构一致，MemoryArena 默认在每个 subtask/session 开始时检索一次 memory，即 **session-level memory retrieval**；如果需要更细粒度，也可配置 action-level memory。

代码中对应关系：

| 粒度 | 代码表现 |
| --- | --- |
| session-level retrieval | `memory_system.wrap_user_prompt(single_query)` / `memory_client.wrap_user_prompt(query)` 在 subtask 开始前调用。 |
| session-level update | subtask 完成后 `memory_system.add(memory_entry)`，写入 task/action/observation/reward。 |
| action-level update | shopping 的 `use_step_memory=True` 会每个 turn 写入；search 可通过 `step_memory` 把 memory env vars 传给 subprocess。 |

当前官方代码中各任务传给 `wrap_user_prompt()` 的 query 来源如下：

| 任务 | 作为 memory retrieval query 的内容 | 代码位置 |
| --- | --- | --- |
| Group Travel Planner | 当前加入成员的 `single_query`，即 `round_item["query"]`。base person 的 query/plan 会先通过 `memory.add()` 写入。 | `run_travel.py` |
| Formal Reasoning Math/Phys | `agent.build_prompt(task=subtask, background=background)`，即 background + 当前 subtask problem。 | `run_math.py` |
| Bundled Shopping | 当前 environment observation/state，即 `prompt_source = observation.get("state") ...`；默认每个 product episode 第一次注入 memory。 | `run_shopping.py` |
| Progressive Search | 当前 search query / decomposed query 由 search environment/agent 内部传给 memory。当前 repo 的 `run_search.py` 仍主要走 BrowseComp-Plus 外部数据和环境。 | `run_search.py` / search agent |

从代码看，同一个 task family 内的 actor prompt 模板基本稳定，变化的是每个 subtask 的变量：

| 任务 | 模板稳定性 | 每个 subtask 变化的变量 |
| --- | --- | --- |
| Group Travel Planner | 稳定。`TravelPlannerAgent` 使用固定 system prompt、`AGENT_USER_PROMPT_TEMPLATE`、可选 history/base-person 模板。 | 当前 traveler name/query、round index、memory context、previous plans / judgement。 |
| Formal Reasoning Math/Phys | 稳定。`MathAgent.build_prompt()` 固定使用 `### BACKGROUND` + `### PROBLEM`。 | 当前 background、当前 problem、memory context。 |
| Bundled Shopping | 稳定但由 environment observation 驱动。初始 conversation/action format 固定，当前 step instruction 由 `build_instruction_for_step()` 生成。 | 当前 page state / observation、当前 product step、purchase history、memory context。 |
| Progressive Search | 当前 repo 仍走 BrowseComp-Plus/search agent，不宜据此固化 MemoryArena HF `progressive_search` 接入口径。 | query / decomposed query、search trace、retrieved docs。 |

因此，后续如果我们接入 MemoryArena，不建议照搬官方 `wrap_user_prompt()` 混合接口；更干净的
框架边界是：memory module 只暴露 `add_chunk()` / `retrieve_context()`，benchmark runner
负责把 `memory_context` 填入对应 task family 的 actor prompt。这样更符合“memory module
只管记忆存取，benchmark 负责环境、工具和 agent prompt”的职责划分。

### 3.3 Bundled Shopping 流程

入口：`run_shopping.py`

核心流程：

```text
collect_task_files_from_hf()
  -> 从 bundled_shopping HF row 重建内部 task_def

for task_file:
    memory = MemoryClient(task_memory_user_id(...))
    for product step:
        current_instruction = build_instruction_for_step(...)
        observation = env.reset()
        prompt = memory.wrap_user_prompt(observation/state)  # 默认只在 episode 第一次注入
        agent ReAct: search/click actions
        env.step(action, ground_truth=target_products, need_judge=True)
        build_memory_entries(...)
        memory.add(entry)
```

`split_steps=True` 时每个 product step 作为单独 episode 运行，并通过 memory 持久化前面 step 的行动结果；`resume=True` 时会从已保存 artifacts backfill memory。

### 3.4 Group Travel Planner 流程

入口：`run_travel.py`

核心流程：

```text
for travel group:
    env.reset(seed=data_idx)
    memory_user_id = f"data_{data_idx}_{model}_{memory_system}"
    if base_person:
        memory.add(json.dumps(base person query + final plan))

    for joining traveler in order:
        memory_context = memory.wrap_user_prompt(single_query)
        agent prepares prompt with memory context
        agent uses tools to generate travel plan
        env.step(action, ground_truth=daily_plan, need_judge=True)
        memory.add(agent.build_memory_entry(task, action, observation, reward))
```

后续 traveler 的 task 依赖 base person 和前面 travelers 的 plan；因此必须按 group 隔离 memory namespace。

### 3.5 Formal Reasoning 流程

入口：`run_math.py`

核心流程：

```text
for paper/task row:
    task_id = uuid4()
    memory_client = MemoryClient(task_id, memory_system_name)
    env_client = EnvironmentClient(task_id, env_name="math" or "phys")
    memory_client.add("Initial result: Empty")

    for subtask, ground_truth, background in paper:
        query = agent.build_prompt(task=subtask, background=background)
        prompt = memory_client.wrap_user_prompt(query)
        action = agent.act(prompt)
        result = env_client.step(action, ground_truth=ground_truth, need_judge=True)
        memory_client.add(agent.build_memory_entry(task, action, observation, reward?))
```

默认配置 `judge_result_in_memory=false`，即 judge 结果用于评估 progress/passrate，但不写入 memory；如果打开该配置，则可把 correctness 反馈写进 memory。

### 3.6 Progressive Search 流程

入口：`run_search.py`

当前代码流程更接近 BrowseComp-Plus：

```text
load query_ids from config
load ground_truth from env/data/browsecomp_plus_decrypted.jsonl
load qrel evidence from topics-qrels/qrel_evidence.txt
for query_id:
    env_client.reset()
    env_client.step({"command": "run_sequential"})
    summarize judgement, retrieved_docids, tool_call_counts, recall
```

它通过 environment server 内部调用 `agent/search.py`，而 `agent/search.py` 会：

```text
memory_client.wrap_user_prompt(query)
run search agent subprocess
return answer, trace, retrieved_docids, tool_call_counts
```

但是当前 `run_search.py` 没有直接使用本地 `data/MemoryArena/progressive_search/data.jsonl`。这必须作为当前 repo preview 状态下的未闭合问题记录。

## 4. Metric 计算方式

### 4.1 论文统一指标

论文 §4.2 定义：

| 指标 | 含义 | 公式/判定 |
| --- | --- | --- |
| PS / Task Progress Score | 一个 task 内正确完成的 subtask 比例，再对 task 平均。 | `PS_task = passed_subtasks / total_subtasks`，`PS = mean(PS_task)` |
| SR / Task Success Rate | 整个 task 是否成功。 | 对 shopping/travel：最终 bundle/plan 是否满足所有成员或所有 step；对 search/formal：final subtask 是否正确。 |
| SR@k | 第 k 个 subtask 的成功率。 | 用于观察随 subtask depth 增长的性能衰减。 |
| Latency | end-to-end subtask completion time。 | 论文 Table 4 报告不同 memory paradigm 的平均 latency。 |

论文 Table 3 同时报告 SR、PS；travel 还报告 sPS / soft Process Score。

### 4.2 Bundled Shopping

代码：`web_shopping_env/compute_reward.py`

单步 reward：

```text
r_type  : product name/category similarity
r_attr  : required attributes match ratio
r_price : price constraint satisfaction
reward  = r_type * (r_attr + r_price) / constrained_terms
如果 purchased_asin == target_asin，则 reward = 1.0
```

聚合：

| 输出字段 | 含义 |
| --- | --- |
| `average_reward` | 所有 step reward 平均。 |
| `item_success_rate` | 一个 item/task 的所有 steps 是否全成功。 |
| `average_success_rate` | per-step success rate 平均。 |
| `per_step` | 每个 step 的 success/failure 统计。 |

属性匹配可用 LLM judge；也可 `--no-llm` 回退到字符串匹配。

### 4.3 Group Travel Planner

代码：`travel_planner_env/eval.py`

| 指标 | 含义 |
| --- | --- |
| PS | person full pass rate；某个 traveler 的每一天每个 slot 都和 gold plan 足够相似才算 pass。 |
| SPS | data-level average constraint slot rate；只看相对 base plan 发生变化的 constraint slots。 |
| SR | group success rate；一个 group 中所有 persons 全 pass 才算 group success。 |

slot similarity 用 `difflib.SequenceMatcher`，阈值 `SIM_TH = 0.7`。

### 4.4 Formal Reasoning

代码：`formal_reasoning_env/eval.py`

| 指标 | 含义 |
| --- | --- |
| `progress_score` | 每个 paper/task 内答对 subtask 数 / subtask 总数。 |
| `overall_average_passrate` | 每个 paper 最后一个 subtask 是否正确的平均。 |
| `passrate_at_k` | 第 k 个 subtask 的平均正确率。 |
| `cummulative_passrate_at_k` | 到第 k 个 subtask 为止的累计平均正确率。 |
| `average_memory_length` | `memory_context` token 长度平均。 |
| `average_session_time` / `average_task_time` | session/task 时间。 |

`is_correct` 来自 environment judge。

### 4.5 Progressive Search

代码：`run_search.py`、`web_search_env/evaluate_with_openai.py`

| 指标 | 含义 |
| --- | --- |
| Accuracy | judge 判断 final answer 是否匹配 correct answer。 |
| Recall | `retrieved_docids` 与 qrel evidence docs 的重合比例。 |
| Average Tool Calls | 每种工具调用次数平均。 |
| Calibration Error | 根据 judge confidence 和 correctness 计算。 |

该任务同时评估 answer correctness 和 retrieval evidence recall，因此它不是纯 answer-level benchmark。

## 5. Answer LLM / Judge LLM 配置和 Prompt

### 5.1 Task agent LLM

官方配置样例中主要使用：

| 环境 | 默认 task agent | 参数位置 |
| --- | --- | --- |
| shopping | `gpt-5-mini`，`temperature=1.0`，`max_tokens=4096` | `configs/web_shopping_configs/*.json` |
| travel | `gpt-5-mini` 或 long-context variants | `configs/travel_planner_configs/*.json` |
| formal reasoning | `gpt-5-mini`，`temperature=0.0`，`max_tokens=8192` | `configs/formal_reasoning_configs/*.json` |
| search | `gpt-5-mini` agent，`text-embedding-3-small` embedding | `configs/web_search_configs/search_task.json` |

README / setup 文档同时声称支持 OpenAI、Gemini、Anthropic backends；具体能否运行取决于对应 agent client 和环境依赖。

### 5.2 Memory prompt

MemoryArena 没有统一的“answer prompt”。memory server 的核心是：

```text
wrap_user_prompt(question) -> prompt containing <memory_context>...</memory_context>
```

也就是说，method/memory system 直接控制 memory context 如何插入 agent prompt。

### 5.3 Task-specific prompts

| 环境 | prompt 来源 | 说明 |
| --- | --- | --- |
| travel | `travel_planner_env/prompts.py` | `AGENT_SYSTEM_PROMPT` 定义工具使用和最终 plan 格式；`HISTORY_TEMPLATE` / `BASE_PERSON_TEMPLATE` 控制多 traveler 上下文。 |
| shopping | `run_shopping.py` + web shopping runtime runner | HF row 被重建为 `agent_instruction`；每个 product step 生成单步 instruction。 |
| formal | `agent/math.py` | `build_prompt()` 把 `background` 和 `problem` 拼成 `### BACKGROUND` / `### PROBLEM`；`MathAgent` 内部还有 math solver system prompt。 |
| search | `web_search_env/search_agent/prompts.py` | 包含 direct/oracle query prompt、WebSailor-style search prompt 和 grader prompt。 |

### 5.4 Judge / scorer LLM

| 环境 | 是否 LLM judge | 配置 / prompt |
| --- | --- | --- |
| shopping | 可选 | `compute_reward.py` 的 `LLM_SYSTEM_PROMPT` 是 strict product-attribute judge，要求 JSON；默认也可回退 string matching。 |
| travel | final eval 主要是规则匹配 | `eval.py` 用 slot string similarity；`run_travel.py` 中 `judgement_mode` 可让 env 返回 judgement，但最终 PS/SPS/SR 用规则聚合。 |
| formal | 是 | env config 默认 `model_name=gpt-5-mini`、`temperature=1.0`、`max_tokens=4096`，用于判断 subtask answer。 |
| search | 是 | `evaluate_with_openai.py` 默认 judge model `gpt-4.1`；`GRADER_TEMPLATE` 要求输出 `extracted_final_answer`、`reasoning`、`correct yes/no`、`confidence`。 |

## 6. Method Adapter 接口需求

### 6.1 MemoryArena 官方 memory API

官方 memory client/server 的最小 API：

```python
class MemoryClient:
    def __init__(self, user_id: str, memory_system_name: str, base_url: str): ...
    def wrap_user_prompt(self, question: str) -> str: ...
    def add(self, chunk: str) -> dict: ...
```

对应 server endpoint：

| endpoint | 输入 | 输出 | 作用 |
| --- | --- | --- | --- |
| `POST /memory/initialize` | `user_id`, `memory_system_name` | status | 为一个 task/user 初始化 memory instance。 |
| `POST /memory/wrap_user_prompt` | `user_id`, `memory_system_name`, `question` | `prompt` | 检索 memory 并返回带 `<memory_context>` 的完整 prompt。 |
| `POST /memory/add` | `user_id`, `memory_system_name`, `chunk` | status | 写入完成 subtask/action 的经验 chunk。 |

### 6.2 对我们当前接口的判断

当前 `BaseMemoryProvider.add(conversation) + retrieve(question)` **不足以完整表达 MemoryArena**：

| 当前框架能力 | MemoryArena 需求 | 是否足够 |
| --- | --- | --- |
| add conversation/session/turn | 需要写入 task/action/observation/reward/judgement chunk；有时是每个 subtask，有时是每个 action step。 | 不足，需要更通用的 `add_event/add_chunk`。 |
| retrieve(question) -> answer prompt | 需要 `wrap_user_prompt(observation_or_subtask)`，返回可直接给 agent 使用的 prompt；不是只返回 answer reader prompt。 | 不足。 |
| conversation-level QA runner | 需要环境 server、tool actions、multi-step agent loop、env reward/judge。 | 不足，必须新 task family runner。 |
| answer-level metric | 需要 SR、PS、sPS、reward、Recall、tool calls、latency。 | 不足，metric family 更复杂。 |

如果未来接入，建议新增一个独立 task family，例如：

```text
agentic-memory-environment
```

最小 method contract 可设计为：

```python
class BaseAgenticMemoryProvider:
    def initialize(self, memory_scope_id: str) -> None: ...
    def wrap_user_prompt(self, query_or_observation: str) -> str: ...
    def add_chunk(self, chunk: str, metadata: dict | None = None) -> None: ...
```

其中：

```text
memory_scope_id = task id / group id / paper id / search query id
query_or_observation = 当前 subtask instruction 或 env observation
chunk = 上一个 subtask/action 的 task + action + observation + reward/judgement
```

### 6.3 隔离粒度

每个 task row 必须是独立 memory namespace：

| 环境 | 推荐 memory_scope_id |
| --- | --- |
| shopping | `shopping:{category/task_id}:{model}:{memory_system}` |
| travel | `travel:{data_idx}:{model}:{memory_system}` |
| formal | `formal:{paper_name or row id}:{model}:{memory_system}` |
| search | `search:{query_id}:{model}:{memory_system}` |

不能把不同 task rows 混进同一个 memory namespace，否则后续 subtask 会检索到别的 task 的行动轨迹。

### 6.4 不能传给 method 的内容

| 数据 | 是否可给 method | 原因 |
| --- | --- | --- |
| `answers` / `target_asin` / gold daily plans / formal gold answer | 否 | scorer private labels。 |
| qrel evidence / correct answer / judge result | 默认否 | 用于 evaluation；只有官方配置明确 `judge_result_in_memory=true` 时才可把 feedback 写入 memory。 |
| future subtasks | 否 | MemoryArena 的核心是按 ordered subtasks 执行，未来信息泄露会破坏 benchmark。 |
| environment reward | 取决于 profile | shopping/travel 默认 memory entry 中可能包含 reward/judgement；formal 默认 `judge_result_in_memory=false`。必须按官方 config 记录。 |

## 7. 未确认项

1. **仓库仍在更新**：官方 README 写明当前是 preview version，仍在 actively maintaining and improving。本文档只反映 2026-07-03 本地仓库和本地 HF 数据快照。
2. **论文总任务数和当前 HF 数据不一致**：论文 Table 1 写总任务 766；当前本地 HF 五个 config 合计 701。需要后续记录 HF revision 或等待仓库稳定。
3. **Progressive Search 代码/数据口径不闭合**：HF `progressive_search` config 已下载，但当前 `run_search.py` 依赖 BrowseComp-Plus 外部 decrypted data、corpus、qrel 和 embeddings，不直接读取 `data/MemoryArena/progressive_search/data.jsonl`。
4. **Shopping setup 文档命名不一致**：`setup_web_shopping.md` 写 config `web_shopping`，但 HF dataset 真实 config 是 `bundled_shopping`，代码 `task_files.py` 也使用 `bundled_shopping`。
5. **外部环境依赖很重**：travel 需要额外航班 CSV；shopping 需要产品数据库和 WebShop runtime；search 需要 BrowseComp-Plus corpus、FAISS indexes/qrel；formal 需要 env server 和 judge backend。短期不适合直接接入我们当前的 lightweight conversation-QA runner。
6. **Memory method 接口和我们现有接口差异大**：MemoryArena 官方更像 memory server / prompt wrapper，而不是单纯 memory retrieval module。接入前需要先完成新的 task-family 设计。
