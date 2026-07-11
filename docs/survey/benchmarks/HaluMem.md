# HaluMem Benchmark 调研卡片

更新日期：2026-07-11（B5 `frozen-v1`；**现行契约以
`docs/survey/datasets/halumem.md` + `docs/survey/workflows/halumem.md`
两张契约卡与冻结记录
`docs/workstreams/ws02.6-first-smoke-hardening/notes/halumem-frozen-v1.md`
为准**；本卡正文为 2026-06-29 调研期材料。要点更正：① 官方 QA prompt
按 method 分五脚本，unified canonical = PROMPT_MEMZERO 逐字（裁决），
PROMPT_MEMOBASE 是官方死代码；② `is_update` 是字符串 "True"/"False"；
evidence 元素无 turn id → retrieval recall N/A；③ 更新探针官方路由 =
`is_update=="True"` 且检索非空才进 update 桶，空检索归 integrity；
④ Long 的 1,030 个 `is_generated_qa_session` session 官方评测端整体
跳过（questions 键恒空、无 memory_points）。）

## 1. 一句话结论

HaluMem 是一个 **uuid/user 级连续会话 + operation-level memory hallucination diagnosis** benchmark。它不是只看最终 QA，而是把 memory system 拆成 **Memory Extraction、Memory Updating、Memory Question Answering** 三个阶段分别评估，用来定位幻觉来自抽取、更新、检索还是生成。

它对当前 `add + retrieve` 框架有明显冲击：QA 阶段可以用 `retrieve + answer LLM` 覆盖，但 Memory Extraction 需要 method 返回“指定 session 新抽取出的 memories”，Memory Updating 需要用 gold updated memory 作为 query 检索当前 user 全局 memory state。因此完整接入至少需要 `add_dialogue`、`get_dialogue_memory`、`retrieve` 三类能力；不能只当作普通 conversation-QA。

## 2. Dataset 数据结构

### 2.1 本地材料与核心数据

| 类型 | 路径 / 来源 | 调研结论 |
| --- | --- | --- |
| 官方仓库 | `/Users/wz/Desktop/memoryBenchmark/third_party/benchmarks/HaluMem-main` | 包含 README、数据生成脚本、`eval/` 下的多个 memory system wrapper、scorer 和 prompt。 |
| 论文 PDF | `/Users/wz/Desktop/memoryBenchmark/third_party/benchmarks/HaluMem-main/Chen 等 - 2025 - HaluMem Evaluating Hallucinations in Memory Systems of Agents.pdf` | 定义三类 operation-level evaluation。 |
| 本地 dataset | `/Users/wz/Desktop/memoryBenchmark/data/halumem/HaluMem-Medium.jsonl`、`/Users/wz/Desktop/memoryBenchmark/data/halumem/HaluMem-Long.jsonl` | Phase 1 评测应只使用这两个最终 JSONL，而不是中间 stage 文件。 |
| 官方 eval 入口 | `/Users/wz/Desktop/memoryBenchmark/third_party/benchmarks/HaluMem-main/eval/eval_memzero.py` 等 | 每个 wrapper 都先生成 run artifact，再由 `evaluation.py` 统一 judge 和聚合。 |

本地数据规模直接统计如下：

| Dataset | Users | Sessions | Dialogue turns | Memory points | QA pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| HaluMem-Medium | 20 | 1387 | 60146 | 14948 | 3467 |
| HaluMem-Long | 20 | 2417 | 107032 | 14948 | 3467 |

Long 版本和 Medium 版本共享 memory points / QA pairs 数量，但 Long 有更多 sessions 和更长上下文/干扰。

### 2.2 顶层 user 结构

每行 JSONL 是一个 user：

```json
{
  "uuid": "...",
  "persona_info": "...",
  "sessions": [...],
  "total_dialogue_token_length": ...,
  "total_question_count": ...,
  "token_cost": ...
}
```

| 字段 | 是否给 method | 含义 |
| --- | --- | --- |
| `uuid` | 是 | user 级隔离 id。不同 uuid 必须隔离；同一 uuid 下 sessions 按时间连续累积。 |
| `persona_info` | 通常不直接给 | 用户初始画像。官方 Mem0 wrapper 只用正则从中提取 user name 作为 `user_id`，不是把完整 persona profile 注入 memory。 |
| `sessions` | 是，逐 session 处理 | 连续会话列表，是 method 的主要输入来源。 |
| `total_dialogue_token_length`、`total_question_count`、`token_cost` | 否 | 统计字段，不是 method public input。 |

### 2.3 Session 结构

每个 session 结构如下：

```json
{
  "start_time": "...",
  "end_time": "...",
  "memory_points_count": 3,
  "memory_points": [...],
  "dialogue_turn_num": 20,
  "dialogue": [...],
  "dialogue_token_length": 8000,
  "questions": [...],
  "question_count": 2
}
```

Long 数据的 session 还可能有 `session_id`。

| 字段 | 是否给 method | 含义 |
| --- | --- | --- |
| `start_time` / `end_time` | 是 | session 时间。官方 Mem0 wrapper 把 `start_time` 转成 timestamp 写入 memory。 |
| `dialogue` | 是 | 当前 session 的 user/assistant turns。 |
| `memory_points` | 否 | gold memory labels，只给 extraction/update scorer。 |
| `questions` | 部分给 | `question` 给 QA query；`answer`、`evidence`、`difficulty`、`question_type` 只给 scorer。 |
| `dialogue_turn_num`、`dialogue_token_length`、`memory_points_count`、`question_count` | 否 | 统计字段。 |

### 2.4 Dialogue turn 结构

Dialogue turn 示例：

```json
{
  "role": "user",
  "content": "...",
  "timestamp": "Sep 04, 2025, 18:42:18",
  "dialogue_turn": 0
}
```

| 字段 | 是否给 method | 含义 |
| --- | --- | --- |
| `role` | 是 | `user` 或 `assistant`。 |
| `content` | 是 | turn 文本。 |
| `timestamp` | 是 | turn 时间，可用于时序记忆。 |
| `dialogue_turn` | 是 | 当前 session 内 turn index。 |

官方 Mem0 wrapper 实际 `client.add(...)` 时只保留 `role/content` messages，并把 session `start_time` 作为写入 timestamp。

### 2.5 Memory point 结构

Memory point 是 gold memory，不是 method 输入：

```json
{
  "index": 1,
  "memory_content": "User's name is Martin Mark",
  "memory_type": "Persona Memory",
  "is_update": "False",
  "original_memories": [],
  "timestamp": "Sep 04, 2025, 21:12:18",
  "event_source": 0,
  "importance": 0.75,
  "memory_source": "system"
}
```

| 字段 | 含义 | 是否给 method |
| --- | --- | --- |
| `index` | session 内 memory 编号 | 否 |
| `memory_content` | 正确 memory 文本；Extraction 中是应抽取记忆，Updating 中是更新后的目标记忆 | add 阶段不注入；Updating eval 会作为检索 query |
| `memory_type` | `Persona Memory` / `Event Memory` / `Relationship Memory` 等 | 否，用于分类统计 |
| `is_update` | 是否更新已有 memory | 否，用于筛选 update eval |
| `original_memories` | update 前的旧记忆 | 否，只给 update judge |
| `timestamp` | gold memory 时间 | 否 |
| `importance` | 加权 recall 使用 | 否 |
| `memory_source` | `primary`、`secondary`、`interference`、`system` 等 | 否；`interference` 用于 FMR |

`memory_source = interference` 表示干扰/假记忆来源，用于评估 False Memory Resistance。

### 2.6 Question 结构

Question 示例：

```json
{
  "question": "What is Martin Mark's middle name?",
  "answer": "Unknown; not provided by the user.",
  "evidence": [],
  "difficulty": "easy",
  "question_type": "Memory Boundary"
}
```

| 字段 | 是否给 method | 含义 |
| --- | --- | --- |
| `question` | 是 | QA query。 |
| `answer` | 否 | reference answer，只给 QA judge。 |
| `evidence` | 否 | key memory points，只给 QA judge。 |
| `difficulty` | 否 | 统计/分析标签。 |
| `question_type` | 否 | 统计/分析标签。 |

## 3. Evaluation 流程

### 3.1 总体 uuid/user 级连续流程

HaluMem 是 user 级连续评测，不是 session 隔离：

```text
for user in dataset:
    reset_or_switch_user_namespace(uuid)

    for session in user.sessions in chronological order:
        add_dialogue(uuid, session.dialogue, session.start_time)

        if session.memory_points:
            evaluate memory extraction

        if session has update memory_points:
            evaluate memory updating

        if session.questions:
            evaluate memory QA
```

关键点：

- 不同 `uuid` 必须隔离。
- 同一 `uuid` 下 sessions 持续累积 memory。
- QA 不是等整个 user 的所有 sessions 结束后才问；问题挂在哪个 session 下，就在该 session 写入后触发。

### 3.2 Memory Extraction

目标：当前 session 处理后，系统是否抽取了应该记住的 memory，同时是否产生了幻觉 memory。

官方 wrapper 的实际 artifact 形态是：

```python
result = add_dialogue(session.dialogue)
extracted_memories = [item["memory"] for item in result["results"]]
new_session["extracted_memories"] = extracted_memories
```

Scorer 输入：

```text
dialogue
gold memory_points
system extracted_memories
```

因此完整 method 接入需要能拿到“本 session 新产生的 extracted memories”。如果底层 method 只支持全局 retrieve，不支持 session-specific extraction dump，则不能准确完成 extraction 任务。

### 3.3 Memory Updating

目标：系统是否把旧记忆正确更新成新记忆。

官方 Mem0 wrapper 只对满足下面条件的 memory point 做 update eval：

```python
memory["is_update"] != "False" and memory["original_memories"]
```

调用方式：

```python
query = memory["memory_content"]          # gold updated memory
memories_from_system = retrieve(user_id, query, top_k=10)
memory["memories_from_system"] = memories_from_system
```

关键理解：

- Updating 不是要求 method 显式返回 old-new pair。
- 它用 gold new memory 文本作为 query，检索当前 user 的全局 memory state。
- Judge 会看 retrieved memories 是否包含正确新记忆、是否还保留旧记忆或产生错误更新。

### 3.4 Memory Question Answering

QA 流程：

```python
retrieved = retrieve(user_id, query=qa["question"], top_k=20)
system_response = answer_llm(context=retrieved, question=qa["question"])
judge(question, qa["answer"], qa["evidence"], system_response)
```

官方 Mem0 wrapper 会把 retrieved memory context 和 question 填入 `PROMPT_MEMZERO`，再调用统一 LLM 生成 `system_response`。QA 阶段每个问题默认检索 top_k=20。

### 3.5 输出 artifact 关键字段

官方 eval wrapper 会输出新的 user/session JSON，关键字段包括：

| 字段 | 来源 | 用途 |
| --- | --- | --- |
| `extracted_memories` | add dialogue 返回或 get dialogue memory | Extraction scorer |
| `memories_from_system` | update query 检索 top-k | Updating scorer |
| `context` | QA query 检索结果格式化文本 | Answer LLM 输入记录 |
| `system_response` | Answer LLM 输出 | QA scorer |
| `add_dialogue_duration_ms`、`search_duration_ms`、`response_duration_ms` | wrapper 计时 | 效率分析 |

## 4. Metric 计算方式

### 4.1 Memory Extraction

Extraction 包含 integrity/recall、accuracy、FMR 和 F1。

| 指标 | 代码口径 | 含义 |
| --- | --- | --- |
| `recall(all)` | `memory_integrity_score == 2` 的非 interference gold memory 数 / 非 interference gold memory 总数 | 完整抽取 recall |
| `weighted_recall(all)` | `0.5 * score * importance` 加权后除以 importance 总和 | 部分抽取计 0.5 的加权 recall |
| `target_accuracy(all)` | 被判定属于 gold target memory 的 extracted memory 的 accuracy 平均 | target memory precision |
| `weighted_accuracy(all)` | 所有 extracted memories 的 accuracy 平均 | 系统抽取 memory 的总体准确性 |
| `interference_accuracy(all)` | interference gold memory 得分为 0 的比例 | FMR，越高表示越能抵抗干扰假记忆 |
| `memory_extraction_f1` | `2 * target_accuracy * recall / (target_accuracy + recall)` | Extraction 综合 F1 |

LLM judge 对 memory integrity 输出 `score in {2,1,0}`；对 memory accuracy 输出 `accuracy_score in {2,1,0}` 和 `is_included_in_golden_memories`。

### 4.2 Memory Updating

Judge 输出：

```text
Correct / Hallucination / Omission / Other
```

聚合字段：

| 指标 | 含义 | 越高越好 |
| --- | --- | --- |
| `correct_update_memory_ratio` | 正确更新比例 | 是 |
| `hallucination_update_memory_ratio` | 错误/幻觉更新比例 | 否 |
| `omission_update_memory_ratio` | 该更新但遗漏比例 | 否 |
| `other_update_memory_ratio` | 其他失败类型比例 | 否 |

### 4.3 Memory QA

Judge 输出：

```text
Correct / Hallucination / Omission
```

聚合字段：

| 指标 | 含义 | 越高越好 |
| --- | --- | --- |
| `correct_qa_ratio` | QA 正确比例 | 是 |
| `hallucination_qa_ratio` | QA 幻觉比例 | 否 |
| `omission_qa_ratio` | QA 遗漏比例 | 否 |

QA 不是字符串 exact match，而是 LLM judge 基于 question、reference answer、key memory points、system response 分类。

## 5. Answer LLM / Judge LLM 配置和 Prompt

### 5.1 统一 LLM 配置

`eval/README.md` 要求 `.env` 提供：

| 变量 | 含义 |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI-compatible API key |
| `OPENAI_BASE_URL` | OpenAI-compatible endpoint |
| `OPENAI_MODEL` | 示例为 `gpt-4o` |
| `OPENAI_MAX_TOKENS` | 示例为 `16384` |
| `OPENAI_TEMPERATURE` | 示例为 `0.0` |
| `OPENAI_TIMEOUT` | 示例为 `300` |
| `RETRY_TIMES`、`WAIT_TIME_LOWER`、`WAIT_TIME_UPPER` | tenacity retry 配置 |

`eval/llms.py` 通过 OpenAI SDK 读取这些环境变量，并以单条 user message 调用 chat completions。

### 5.2 Answer prompt

QA answer prompt 在 `eval/prompts.py`。Mem0 / Mem0-Graph 使用 `PROMPT_MEMZERO`，核心变量：

```text
{context}
{question}
```

Prompt 要求：

- 只基于 retrieved memories 回答。
- 注意 timestamp。
- 矛盾信息优先最近 memory。
- 相对时间要换算成具体日期。
- 不要混淆 memory 里提到的人名和真实 user。
- 答案少于 5-6 个词。

不同 wrapper 有不同 prompt，例如 Zep 用 `PROMPT_ZEP`，MemOS/Supermemory 用 `PROMPT_MEMOS`，Memobase 用 `PROMPT_MEMOBASE`。实现时应按 method profile 记录使用的 prompt。

### 5.3 Judge prompt

Judge prompt 在 `eval/eval_tools.py`：

| 函数 | Prompt | 输出 |
| --- | --- | --- |
| `evaluation_for_memory_integrity(...)` | `EVALUATION_PROMPT_FOR_MEMORY_INTEGRITY` | `{"score": "2|1|0"}` |
| `evaluation_for_memory_accuracy(...)` | `EVALUATION_PROMPT_FOR_MEMORY_ACCURACY` | `{"accuracy_score": "2|1|0", "is_included_in_golden_memories": "true|false"}` |
| `evaluation_for_update_memory(...)` | `EVALUATION_PROMPT_FOR_UPDATE_MEMORY` | `{"evaluation_result": "Correct|Hallucination|Omission|Other"}` |
| `evaluation_for_question(...)` | `EVALUATION_PROMPT_FOR_QUESTION` | `{"evaluation_result": "Correct|Hallucination|Omission"}` |

这些 judge prompt 都不能看到 method 不该看的私有字段以外的内容；它们属于 scorer 阶段。

## 6. Method Adapter 接口需求

### 6.1 官方论文/API 需求

HaluMem 论文抽象出三类 memory system API：

| API | 作用 |
| --- | --- |
| Add Dialogue API | 输入一个 session 的 dialogue，让 memory system 抽取/更新/存储 memories。 |
| Get Dialogue Memory API | 返回指定 session 中系统抽取出的 memories，用于 Memory Extraction。 |
| Retrieve Memory API | 按 query 从当前 user 全局 memory state 检索 memories，用于 Updating 和 QA。 |

GitHub 没有统一 `BaseMethod` 抽象类，而是通过多个 `eval_*.py` wrapper 实现相同 artifact contract。

### 6.2 推荐接入接口

HaluMem 完整接入建议至少需要：

```python
reset_user(user_id: str) -> None
add_dialogue(user_id: str, session_id: str, dialogue: list[dict], start_time: str | None, end_time: str | None) -> AddDialogueResult
get_dialogue_memory(user_id: str, session_id: str, add_result: AddDialogueResult | None = None) -> list[str]
retrieve(user_id: str, query: str, top_k: int) -> list[str]
```

| 接口 | 输入 | 输出 | 用途 |
| --- | --- | --- | --- |
| `reset_user` | `uuid` 或 user namespace | `None` | 不同 uuid 隔离；同一 uuid 内连续累积。 |
| `add_dialogue` | session dialogue + 时间 | `AddDialogueResult`，最好包含 `extracted_memories` | 写入当前 session。 |
| `get_dialogue_memory` | user_id、session_id | `list[str]` | Extraction 任务的核心。必须是 session-specific，不能返回全局全部 memory。 |
| `retrieve` | user_id、query、top_k | `list[str]` 或结构化 memories | Updating 和 QA 使用当前 user 全局 memory state。 |

QA answer 可以由统一 framework reader 完成：

```python
answer(question: str, retrieved_memories: list[str]) -> str
```

### 6.3 与当前 `add + retrieve` 的关系

HaluMem 中 `retrieve` 可以自然对齐当前框架，但 `add` 需要能返回或关联 session-level extracted memories。也就是说：

- 如果只做 QA 子集：`add_dialogue + retrieve + answer LLM` 足够。
- 如果做完整 HaluMem：必须支持 `get_dialogue_memory` 或在 `add_dialogue` 返回 `extracted_memories`。
- 如果 method 无法提供 session-specific extracted memory，例如只能返回最近上下文或全局 user profile，则无法准确评估 Memory Extraction。

强约束：`memory_points`、`questions.answer`、`questions.evidence`、`difficulty`、`question_type` 不得进入 method public input。

### 6.4 2026-07-06 增补：原生粒度与喂入方式

HaluMem 的原生运行单位不是单个 QA instance，而是 `uuid -> sessions -> dialogue turns / memory_points / questions` 的 user 级连续轨迹。官方 Mem0 wrapper 对每个 user 先 `delete_all(user_id=...)`，然后按 session 顺序调用 add；同一 user 的 memory state 在 session 之间持续累积。证据：`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py:148-159`、`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py:168-194`。

喂入 method 的自然粒度是 session dialogue：每个 session 的 `dialogue` 会被压成 `role/content` message list，session `start_time` 会转成 timestamp 写入；turn 级 `timestamp` 可作为更细边界信号，但官方 Mem0 wrapper 实际以 session start time 作为写入时间。证据：`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py:174-187`。

完整 HaluMem 需要三种输出/查询边界：add 后立刻记录本 session 新 `extracted_memories`；update eval 用 gold `memory_content` 检索当前 user 全局 state，`top_k=10`；QA eval 用 `qa.question` 检索，wrapper 传入的 `top_k` 默认来自脚本参数，已有说明中 Mem0 QA 默认为 20。证据：`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py:204-219`、`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py:231-247`。

因此 `add(conversation)` 若只返回成功状态，最多覆盖 QA 子集；要覆盖 operation-level 评测，adapter 需要把 session-specific extracted memories 暴露给 scorer，或提供 `get_dialogue_memory(user_id, session_id)` 等价接口。官方 README 也说明各 wrapper 应遵循相同 artifact contract，Zep 因缺 Get Dialogue Memory API 无法准确评估 extraction。证据：`third_party/benchmarks/HaluMem-main/eval/README.md:81-92`、`third_party/benchmarks/HaluMem-main/eval/README.md:137-141`。

### 6.5 2026-07-06 增补：成本画像

本地最终数据规模为 Medium 20 users / 1,387 sessions / 60,146 dialogue turns / 14,948 memory points / 3,467 QA pairs，Long 20 users / 2,417 sessions / 107,032 dialogue turns / 14,948 memory points / 3,467 QA pairs。证据：本轮验收命令读取 `data/halumem/HaluMem-Medium.jsonl` 与 `data/halumem/HaluMem-Long.jsonl`。

单 session 的 method 成本至少包含一次 add dialogue；若 session 含 update memory points，则每个 update point 触发一次 `top_k=10` retrieval；若 session 含 QA，则每个 question 触发一次 retrieval、一次 answer LLM。证据：`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py:189-194`、`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py:215-220`、`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py:233-252`。

Scorer 成本另算：evaluation 会为 memory integrity、memory accuracy、memory update、question answering 四类输入分别提交 LLM judge；memory integrity/accuracy 数量与 memory points / extracted memories 相关，QA judge 数量与 question 数相关。证据：`third_party/benchmarks/HaluMem-main/eval/evaluation.py:104-186`。

官方 eval LLM 通过 OpenAI-compatible chat completions 单 user message 调用，模型、max_tokens、temperature、timeout 和 retry 均来自 `.env`；README 示例模型为 `gpt-4o`、`OPENAI_MAX_TOKENS=16384`、`OPENAI_TEMPERATURE=0.0`。证据：`third_party/benchmarks/HaluMem-main/eval/README.md:32-48`、`third_party/benchmarks/HaluMem-main/eval/llms.py:20-39`、`third_party/benchmarks/HaluMem-main/eval/llms.py:60-69`。

## 7. 未确认项

1. HaluMem 论文实验使用 GPT-4o 进行 scoring 和 QA answer generation；本项目若用 `gpt-4o-mini` 或 ohmygpt 中转，需要在实验 profile 中明确记录，不可声称严格复现论文数值。
2. `persona_info` 官方 wrapper 只用于抽取 user name；是否允许作为 memory 输入需要用户决策。当前建议不直接注入完整 persona，避免泄漏 profile gold。
3. Zep 等系统由于不支持 Get Dialogue Memory API，官方 README 明确说 extraction 指标不能准确反映真实性能。后续接入类似系统时必须标注 unsupported / approximate。
4. HaluMem 的完整接入需要 operation-level runner，不应硬塞进 LoCoMo/LongMemEval conversation-QA runner。
