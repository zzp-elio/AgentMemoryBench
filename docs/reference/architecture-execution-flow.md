⚠ **2026-07-07 核查：本文 §2.3（两个 Method 协议）、§2.4（AnswerPromptResult 为核心输出）、§5（CLI 层）、§7（Prediction Runner 引擎）、§8（四个 Method Adapter 详细对比）仍描述 v2 协议（`add+retrieve` / `BaseMemoryProvider` / `AnswerPromptResult`），当前主协议已升级为 v3（`ingest+retrieve` / `MemoryProvider` / `RetrievalResult`，见 [spec-protocol-v3.md](../workstreams/ws02-phase1-matrix/spec-protocol-v3.md)），待 ws03 重写。**

# AgentMemoryBenchmark 完整架构与执行流程

本文档提供项目的端到端完整说明，涵盖从研究动机、架构设计、数据流转、method 实现、评测方法论到实验结果的各方面，达到可据此撰写学术论文的深度。

---

## 1. 项目定位与研究动机

AgentMemoryBenchmark 是一个**可复现、可扩展、可审计的 Agent Memory 评测集成框架**。核心研究问题：

> 给定一段长期多会话对话历史，记忆系统能否正确存储并检索相关信息以回答问题？

当前聚焦 **conversation + QA** 任务类型：

```
conversation history → method 写入记忆 → question → method 检索+构建 prompt → answer LLM 生成答案 → metric
```

### 1.1 核心设计目标

1. **可复现性**：每个实验有密码学 manifest（SHA-256），源码版本、数据集、配置全部锁定
2. **可扩展性**：三个声明式注册中心，新 method/benchmark/evaluator 即插即用
3. **可审计性**：四层隐私保护，私有数据（金答案、evidence）绝不泄露给 method
4. **公平对比**：所有 method 使用相同的 answer LLM（framework 统一管理），消除答案生成模型的混淆

---

## 2. 统一数据模型

### 2.1 实体层级（`core/entities.py`）

```
Dataset
└── Conversation (1:N)          — 隔离的记忆命名空间
    ├── Session (1:N)           — 一个有边界的对话段
    │   └── Turn (1:N)          — 单 speaker 单次发言
    ├── Question (1:N)          — 公开，method 可见
    └── GoldAnswerInfo (1:N)    — 私有，evaluator 专用
```

### 2.2 公开/私有字段边界

| 实体 | 公开字段 | 私有字段 |
|------|---------|---------|
| Dataset | dataset_name, conversations(去金), metadata | conversations[*].gold_answers |
| Conversation | conversation_id, sessions, questions, metadata | gold_answers |
| Session | session_id, turns, session_time, start_time, end_time | 无 |
| Turn | turn_id, speaker, content, normalized_role, turn_time | 无 |
| Question | question_id, conversation_id, text, question_time, category | 无 |
| GoldAnswerInfo | 永不对 method 暴露 | question_id, answer, evidence, metadata |

### 2.3 两个 Method 协议（`core/interfaces.py`）

**BaseMemoryProvider（新，retrieve-first，当前主协议）：**
```python
add(conversation: Conversation) -> AddResult          # 单 conversation
retrieve(question: Question) -> AnswerPromptResult     # 返回完整 prompt messages
```
- method 只负责存储（`add`）和检索+prompt 构建（`retrieve`）
- framework 的 answer LLM 统一负责最终答案生成
- **关键设计决策**：解耦检索质量与答案生成质量，所有 method 共享相同 answer LLM

**BaseMemorySystem（旧，legacy 兼容）：**
```python
add(conversations: list[Conversation]) -> AddResult   # 批量
get_answer(question: Question) -> AnswerResult         # method 自己生成答案
```
- 所有四个生产 adapter 同时实现两个协议，`get_answer()` 内部委托给 `retrieve()` + LLM

### 2.4 关键结果结构

**AnswerPromptResult**（retrieve-first 核心输出）：
- `prompt_messages: list[PromptMessage]` — 角色消息列表（system/user/assistant），直接喂给 answer LLM
- `answer_prompt: str` — 兼容文本视图（`[system]`/`[user]` 标签包裹），自动从 prompt_messages 生成
- `metadata.answer_context` — 注入的记忆上下文文本，用于 token 计数
- `metadata.retrieved_memories` — 检索到的原始记忆列表（诊断用）

**PromptMessage**：`role`（system/user/assistant）+ `content`，两者均非空，`__post_init__` 严格校验

---

## 3. 隐私保护四层机制

| 层 | 机制 | 具体位置 |
|---|------|---------|
| 1. 结构排除 | `Conversation.to_public_dict()` 彻底移除 `gold_answers` 键 | entities.py:123-137 |
| 2. 递归键名扫描 | `validate_no_private_keys()` 遍历所有 dict，匹配 12 个黑名单键 | validators.py:133-155 |
| 3. Adapter 级清洗 | LongMemEval `_public_message_metadata()` 剔除 `has_answer` 等私有标签 | longmemeval.py:460-476 |
| 4. 文件隔离 | `evaluator_private_labels.jsonl` 独立文件，prediction runner 不接触其路径 | artifacts.py:39 |

黑名单键（`PRIVATE_KEY_NAMES`）：`answer, answer_session_ids, answers, evidence, gold, gold_answer, gold_answers, ground_truth, has_answer, judge_label, label, target_step_id`

---

## 4. 三大注册中心（声明式，消除 Cartesian 积）

### 4.1 BenchmarkRegistry

两个已注册 benchmark：

| Benchmark | Task Family | Required Capabilities | Variants | Question/Conv |
|-----------|------------|----------------------|----------|:---:|
| LoCoMo | CONVERSATION_QA | CONVERSATION_ADD + MEMORY_RETRIEVAL | locomo10 | 154 |
| LongMemEval | CONVERSATION_QA | CONVERSATION_ADD + MEMORY_RETRIEVAL | s_cleaned, m_cleaned | 1 |

### 4.2 MethodRegistry

四个已注册 method，全部声明 `provided_capabilities = {CONVERSATION_ADD, MEMORY_RETRIEVAL}`：

| Method | requires_api | shared_instance_parallelism | Config class |
|--------|:---:|:---:|---|
| Mem0 | ✅ | ❌ | Mem0Config |
| MemoryOS | ✅ | ❌ | MemoryOSPaperConfig |
| A-Mem | ✅ | ❌ | AMemConfig |
| LightMem | ✅ | ❌ | LightMemConfig |

### 4.3 EvaluatorRegistry

三个已注册 metric：

| Metric | benchmark | requires_api | Profile |
|--------|----------|:---:|---|
| locomo-f1 | locomo | ❌ | 无 |
| locomo-judge | locomo | ✅ | compact/detailed |
| longmemeval-judge | longmemeval | ✅ | compact/detailed |

### 4.4 运行时兼容性校验

```python
validate_compatibility(
    benchmark_task_family,      # benchmark 要求
    required_capabilities,      # benchmark 需要 method 提供
    method_task_families,        # method 支持
    provided_capabilities,       # method 提供
)
```

纯静态前置校验，method 构建前就发现问题。

---

## 5. CLI 层

### 5.1 四个子命令

| 命令 | 功能 |
|------|------|
| `predict` | 只生成 method answer，不计算指标 |
| `evaluate` | 只基于已有 artifact 计算指标，不调用 method |
| `run` | predict → evaluate 串联管道（严格两阶段：prediction 全部完成后才 evaluation） |
| `calibrate-smoke` | method × benchmark 矩阵的 API 成本标定（并行 ThreadPoolExecutor） |

### 5.2 CLI v2 参数风格

三种调用风格统一归一化为 `PredictCommand`：
- **Legacy**：`predict --profile smoke --method mem0`
- **v2 smoke**：`predict smoke --method mem0`（强制 confirm_full=False）
- **v2 formal**：`predict formal --method mem0`（强制 profile=official-full, confirm_full=True）

### 5.3 成本安全门

两层保护，在 method 构建**之前**校验：
1. `--confirm-api`：method requires_api 时必需
2. `--confirm-full`：profile 为 official-full 时额外必需

---

## 6. Prediction 统一装配（13 步，`run_prediction.py`）

| 步骤 | 操作 | 关键说明 |
|------|------|---------|
| 1 | 解析路径 | expand project_root → PathSettings |
| 2 | 查找注册 | get_benchmark_registration() + get_method_registration() |
| 3 | 校验 prediction_enabled | benchmark 是否允许 prediction |
| 4 | 校验 task-family 兼容 | validate_compatibility() |
| 5 | 解析 profile section | 确认 profile 在 method config 中存在 |
| 6 | 成本门确认 | --confirm-api / --confirm-full |
| 7 | 校验 resume 约束 | resume=True 时 run_id 必须显式提供 |
| 8 | 加载 method profile config | TOML → 强类型 dataclass（如 Mem0Config） |
| 9 | 解析 run scope & variants | smoke→SMOKE, official-full→FULL；variant selector → 具体 variant 元组 |
| 10 | 生成 child run ID | 显式或自动 {method}-{benchmark}-{profile}-{uuid8} |
| 11 | 解析输出目录 | flat（outputs/）或 hierarchical（outputs/runs/{method}/{benchmark}/...） |
| 12 | 装配 per-child 准备 | load dataset → 构建 manifest → 创建 policy → 创建 RunContext |
| 13 | 预检 + 构建 + 运行 | preflight → 决定 shared/isolated → 创建 method → run_predictions() |

---

## 7. Prediction Runner 引擎（`runners/prediction.py`，~2100 行）

### 7.1 初始化流程

1. **构建 manifest**：dataset SHA-256 + source fingerprint + method manifest → 密码学不可变身份
2. **选择 conversations/questions**：whitelist filter + question_limit_per_conversation
3. **准备运行目录**：创建或校验 manifest（resume 时比对 identity）
4. **回灌先前状态**：从 `method_predictions.jsonl`、`conversation_status.json`、`question_status.jsonl` 恢复
5. **决定执行模式**：shared-instance vs isolated-worker

### 7.2 Work Plan 系统

`_build_prediction_work_plan()` 确定本轮需要做什么：
- **ingested**：conversation status 为 `"completed"` 或（retry-failed + ingested=true）
- **pending_questions**：question_id 不在 completed_question_ids 中
- **max_new_conversations**：只计入未完成 conversation，不进 manifest identity
- **question_limit_per_conversation**：也不进 manifest identity，后续可加题

### 7.3 Shared-Instance 模式

单 worker 或方法支持共享实例时使用（当前不常用）：

**Phase A — Ingest：** ThreadPoolExecutor → `_ingest_one()` → 去私有字段 → `system.add()` → 写 conversation_status

**Phase B — Answer：** ThreadPoolExecutor → 对每个 pending question → `retrieve()` + `answer_reader.generate_answer_with_trace()`（或 legacy `get_answer()`）

### 7.4 Isolated-Worker 模式（实际主力模式）

用于 Mem0/MemoryOS/A-Mem/LightMem（`supports_shared_instance_parallelism=False`）：

**Stable chunking**：`conversation_index % worker_count`，确保跨 resume 同一 conversation 始终到同一 worker 索引，保持 `worker_{idx}/` 存储目录稳定。

**Per-worker 执行**（`_isolated_worker`）：
1. 创建独立 method 实例（独立 Qdrant/存储目录）
2. 预加载 completed_conversations
3. 串行处理 assigned conversations：
   - needs_ingest → `system.add(conversation)`
   - pending questions → `retrieve()` + `answer_reader.generate_answer_with_trace()`
   - 成功 → `_ConversationAnswerBatch`
   - 失败 → `_ConversationFailureBatch`（含 partial predictions + retrieval records）

**协调线程**：`as_completed()` 处理每个 batch，失败 batch 的 partial 数据也持久化。每个 batch 后原子重写所有 artifacts，最多丢失一个 conversation 的工作。

**连续失败熔断**：单个 worker 连续失败 ≥ max_consecutive_failures → 设 cancellation_event → 所有 worker 停止。

### 7.5 Resume 机制（仅 conversation-level）

**Conversation-level resume**（2026-06-20 起唯一生效的续传策略）：
- `conversation_status.json`：记录每个 conversation 的 coarse 状态（completed/failed/ingested）
- `question_status.jsonl`：记录每个 question 的完成状态
- `method_predictions.jsonl`：已答 question 的答案，resume 时跳过
- `answer_prompts.jsonl`：retrieve-first 中间检索记录，resume 时复用检索结果跳过 `retrieve()`

**Turn 级续传历史状态**：`BaseResumableMemorySystem` 接口、`add_from_turn()`、`TurnIngestCheckpointStore` 等代码仍保留但已禁用。`Mem0.supports_turn_resume()` 硬编码返回 `False`（2026-06-20 决策）。Isolated 模式显式拒绝已有 turn checkpoint。

**Manifest 比对**：resume 时比对 `dataset_sha256` + `source_fingerprint_sha256` + `method_manifest`（不含 question_limit_per_conversation）。Schema v1 清单拒绝 resume。

### 7.6 原子写入

所有 artifact 使用相同模式（`storage/atomic.py`）：
1. 写到同目录临时文件
2. `flush()` + `os.fsync()`
3. `os.replace()` 原子替换

JSONL 读取支持 torn-tail 恢复（最后一行无换行且 JSON 无效 → 静默丢弃）。

---

## 8. 四个 Method Adapter 详细对比

### 8.1 Mem0（`methods/mem0_adapter.py`，55KB）

**记忆架构**：Mem0 OSS v2.0.4，基于 LLM fact extraction + embedding + Qdrant vector store

**add() 策略**：
- LoCoMo：逐 turn 写入（CHUNK_SIZE=1），每个 turn 调用 `Memory.add([message], run_id=conversation_id, infer=True)`
- LongMemEval：按 turn 对写入（CHUNK_SIZE=2，user+assistant pair）
- 注入 `_observation_time_prompt`（session time 相对锚点）到 Mem0 extractor
- 命名空间预留用 `threading.RLock` 保护

**retrieve() 策略**：
- `Memory.search(question.text, filters={"run_id": conversation_id}, top_k=200)`
- 根据 dataset 类型选择 prompt：LoCoMo → vendored `memory-benchmarks/benchmarks/locomo/prompts.py`，LongMemEval → vendored `longmemeval/prompts.py`
- 返回 `AnswerPromptResult` 含 role 结构消息

**模型使用**：extraction=gpt-4o-mini, embedding=text-embedding-3-small(API, 1536dim), reader=gpt-4o-mini

**关键特性**：注入 timeout/max_retries 到 vendored OpenAI client；可选安装 LLM/embedding 效率观测 monkey-patch

### 8.2 MemoryOS（`methods/memoryos_adapter.py`，70KB）

**记忆架构**：三层记忆（论文结构）— ShortTermMemory（deque, capacity=7）+ MidTermMemory（FAISS, capacity=200）+ LongTermMemory（knowledge base, capacity=100）+ DynamicUpdate（STM→MTM 驱逐 + MTM→LTM profile 更新）

**add() 策略**：
- 将 conversation 转为"pages"（user_input + agent_response + timestamp）
- 每个 page 进 STM deque，满时触发 `bulk_evict_and_update_mid_term()`：
  1. 弹 STM pages → LLM 检测对话连续性 → 生成 meta-info 链
  2. LLM 生成 multi-summary（最多 2 个子主题摘要 + 关键词）
  3. 余弦相似度+关键词重叠合并到已有 MTM session，或创建新 session
  4. 超出 MTM capacity → LFU 驱逐
  5. Top segment heat ≥ H_THRESHOLD → LLM 个性分析 → 更新 LTM
- LTM knowledge_base 和 assistant_knowledge 各截断到 100 条

**retrieve() 策略**：
- MTM FAISS 搜索（余弦相似度 over session summary embeddings，top 5 sessions）
- 关键词重叠评分 + 时间衰减 → 过滤到 segment_threshold（0.1）
- Page 级余弦过滤到 page_threshold（0.1）→ heap 排序取 top 10 pages
- LTM knowledge FAISS 搜索（top 10，knowledge_threshold=0.1）
- 构建四段式 prompt：Recent conversation(STM) + Relevant past(MTM) + User traits(LTM) + Assistant knowledge(LTM)

**模型使用**：answer=gpt-4o-mini, embedding=all-MiniLM-L6-v2(本地), STM/MTM/LTM 操作共用 gpt-4o-mini

**LongMemEval prompt**：两个 profile — `lightmem_longmemeval_reader_v1`（简洁 system: "You are a helpful assistant"）和 `memoryos_pypi_generic_v1`（角色扮演 prompt）

**关键特性**：LLM retry 使用指数退避（5s base, ×2 multiplier, 60s cap）；embedding 字符串缓存避免重复编码；并行 worker 间 module import 锁

### 8.3 A-Mem（`methods/amem_adapter.py`，42KB）

**记忆架构**：RobustAgenticMemorySystem — RobustMemoryNote 列表 + SimpleEmbeddingRetriever（本地 all-MiniLM-L6-v2）

**add() 策略**：
- 逐 turn 调用 `RobustAgenticMemorySystem.add_note()`：
  - 内容格式化：`"Speaker {speaker} says: {content}"`
  - 时间戳：`turn.turn_time or session.session_time`（缺失时 vendored 代码静默回退到 `datetime.now()` — 已知语义缺陷）
- Conversation 完成后 pickle 持久化：`memories.pkl` + `retriever.pkl` + `retriever_embeddings.npy` + `state_manifest.json`

**retrieve() 策略**：
- **Query keyword generation**：LLM prompt → 逗号分隔关键词抽取（model_id: `amem-query-llm`）
- **Category-K 映射**（LoCoMo GPT-4o-mini 配置，来自论文 Table 8）：
  - Category 1(multi-hop): k=40, 2(single-assistant): k=40, 3(preference): k=50, 4(temporal): k=50
  - 非 LoCoMo/缺 category → fallback to config.retrieve_k（10）
- `find_related_memories_raw(keywords, k)` → 余弦相似度向量检索
- Category 5(adversarial) 拒绝：官方 prompt 需要 gold answer → 违反隐私约束

**模型使用**：memory build + query keyword + answer 共用 gpt-4o-mini；embedding=all-MiniLM-L6-v2(本地)

**Session time bug 历史**：v1 运行（amem-locomo-0619-1303）因 session_time 未正确传递导致 temporal 结果无效（Cat2 F1 仅 0.1375），v2 修复后 Cat2 F1 恢复到 0.4783。当前通过 `turn.turn_time or session.session_time` 回退链解决。

### 8.4 LightMem（`methods/lightmem_adapter.py`，56KB）

**记忆架构**：LightMemory — LLMLingua-2 预压缩（70% rate）+ Topic segmentation + STM buffer(512 tokens) + Qdrant vector store + Offline update

**add() 策略**：
- **LoCoMo**：逐 turn 转为 `[user(content)+assistant("")]` pair → `add_memory(messages, force_segment/is_last, force_extract/is_last)`
  - 最后一个 batch 时 force_segment=True + force_extract=True（flush 压缩器/分段器）
  - Post-build：`construct_update_queue_all_entries()` + `offline_update_all_entries(score_threshold=0.9)` — 复现 `add_locomo.py`
- **LongMemEval**：真实 user+assistant pair → `add_memory()` → 不触发 offline update
- 时间戳转换：LoCoMo `"1:56 pm on 8 May, 2023"` → LightMem `"2023/05/08 (Mon) 13:56"`
- 缺失时间戳 → `ConfigurationError`（不像 A-Mem 静默回退）

**retrieve() 策略**：
- **LongMemEval**：`backend.retrieve(question.text, limit=60, filters=None)` — 标准 Qdrant 向量检索
- **LoCoMo**：**暴力余弦搜索** — `get_all(with_vectors=True, with_payload=True)` → 手动计算每个 entry 的余弦相似度 → 排序取 top 60 — 精确复现 `search_locomo.py`
- 记忆格式化：提取 time_stamp + weekday → `"[Memory recorded on: 08 May 2023, Monday]\n{memory_text}"`
- LoCoMo prompt：使用 vendored `ANSWER_PROMPT`，按 speaker_a/speaker_b 分区排列记忆

**模型使用**：memory manager + answer 共用 gpt-4o-mini；embedding=all-MiniLM-L6-v2(本地)；LLMLingua-2(CPU, 本地)

**关键特性**：memory manager LLM usage 在子线程中通过线程安全缓冲区收集（`_memory_manager_usage_lock` + `ContextVar` 跨线程刷新），解决 offline update 的观测问题

### 8.5 Method 对比总结

| 维度 | Mem0 | MemoryOS | A-Mem | LightMem |
|------|------|----------|-------|----------|
| 记忆结构 | LLM fact extraction + Qdrant | STM+MTM+LTM 三层 | RobustMemoryNote 列表 | LLMLingua 压缩 + Qdrant |
| Embedding | OpenAI API (1536dim) | 本地 ST (384dim) | 本地 ST (384dim) | 本地 ST (384dim) |
| 写入粒度 | Turn (LoCoMo) / Turn-pair (LME) | Page (user+assistant) | Turn | Batch (多 turn) |
| 检索方式 | Qdrant search (top 200) | FAISS + 关键词 + LTM | 关键词生成 + 向量检索 (k=40-50) | Qdrant (LME) / 暴力余弦 (LoCoMo, top 60) |
| LLM 调用频率 | 极高（每 turn extract, ~5882 次/full） | 中等（每 STM 驱逐 + LTM 更新, ~1363 次/conv） | 中等（每 question 关键词生成 + answer） | 低（每 batch 处理, ~20 次/conv） |
| Post-build 处理 | 无 | 无（即时更新） | 无（即时） | LoCoMo: offline_update queue |
| 时间戳处理 | Prompt 注入相对时间 | 原生 timestamp | 回退链（可能静默降级） | 严格格式转换 + 缺失报错 |
| LongMemEval 适配 | CHUNK_SIZE=2 + 官方 prompt | 专用 prompt profile | 简化的 prompt 模板 | 在线检索路径 |

---

## 9. Benchmark Adapter 详细对比

### 9.1 LoCoMo（`benchmark_adapters/locomo.py`）

- **数据源**：`data/locomo/locomo10.json`（单 JSON，10 sample）
- **Conversation**：1 sample = 1 conversation（conversation_id = sample_id）
- **Sessions**：从 `conversation["session_1"..."session_N"]` 提取，按数字键排序
- **Questions**：从 `sample["qa"]` 列表提取，category "5"（adversarial）被跳过
- **Evidence 粒度**：turn 级（dia_id）
- **图片支持**：有（img_url + blip_caption → ImageRef）
- **Smoke 截断**：逐 turn 截断 + 证据过滤（移除 evidence turn 不在保留范围内的 question）

### 9.2 LongMemEval（`benchmark_adapters/longmemeval.py`）

- **数据源**：`data/longmemeval/longmemeval_s_cleaned.json`（~277MB）/ `m_cleaned.json`（~2.7GB）
- **加载方式**：ijson 流式解析（不一次性加载整个文件）
- **Conversation**：1 instance = 1 conversation（conversation_id = question_id，每 instance 仅 1 question）
- **Sessions**：三个并行列表（haystack_session_ids / haystack_dates / haystack_sessions）按 index 对齐
- **Session ID 去重**：同一 instance 内重复 session_id 自动加 `#occurrence_N` 后缀
- **空白 turn 过滤**：content/text 为空的消息被跳过
- **Evidence 粒度**：session 级（answer_session_ids）
- **Smoke 截断**：按完整两轮（user+assistant pair）截断，非逐 turn
- **隐私清洗**：`_public_message_metadata()` 在构建 Turn 前剔除 `has_answer` 等 12 个私有键

### 9.3 关键差异

| 维度 | LoCoMo | LongMemEval |
|------|--------|-------------|
| Conversation 数 | 10 | 500 |
| Question/Conversation | 154（多） | 1（单） |
| 证据粒度 | turn 级 | session 级 |
| 数据加载 | 一次性 JSON 解析 | ijson 流式 |
| 图片 | 有（img_url, blip_caption） | 无 |
| Session 去重 | 不需要（键唯一） | 需要（相同 session 可能重复） |
| Smoke 截断 | 逐 turn + 证据过滤 | 逐完整 round（2 turn pair） |
| 时间格式 | `"1:56 pm on 8 May, 2023"` | `"2023/05/30 (Tue) 23:40"` |

---

## 10. 评测方法论

### 10.1 Evaluation Runner（`runners/evaluation.py`）

纯 artifact 读取器，永不构建 method、不读 `.env`、不调用 prediction：

```
run_artifact_evaluation()
├─ 读 manifest.json → run_id, benchmark_name
├─ 索引三个 JSONL：public_questions + method_predictions + evaluator_private_labels
├─ 校验：prediction_ids ⊆ public_ids == private_ids（支持分批运行的 partial 数据）
├─ 重建 Question / AnswerResult / GoldAnswerInfo
├─ 对每个 question → evaluator.evaluate(question, prediction, gold)
│    └─ 可选并行（ThreadPoolExecutor, max_workers）
├─ 按 category 分组统计 → category_breakdown
└─ 写 answer_scores.<metric>.jsonl + summary.<metric>.json
```

### 10.2 LoCoMo F1 Evaluator（`evaluators/locomo_f1.py`）

离线、无 API，复现 LoCoMo 官方评测脚本。基于 Porter Stemmer 的 token 重叠 F1。

**预处理管道**：去逗号 → 小写 → 去标点 → 去冠词（a/an/the/and）→ 压缩空白

**按 Category 的分发策略**：

| Category | 策略 | 说明 |
|----------|------|------|
| 1 (multi-hop/multi-answer) | Multi-answer F1 | 逗号分割，对每个 gold 部分取最佳预测部分 F1，取均值 |
| 2 (temporal) | 单答案 Token F1 | 标准词干 token 重叠 |
| 3 (open-domain) | 单答案 Token F1 | Gold 截断到第一个分号（去除解释部分） |
| 4 (single-hop) | 单答案 Token F1 | 标准词干 token 重叠 |
| 5 (adversarial) | 正则匹配 | 预测含 "no information available" 或 "not mentioned" → 1.0，否则 0.0 |

### 10.3 LoCoMo LLM Judge（`evaluators/locomo_judge.py`）

使用 LightMem 官方 `ACCURACY_PROMPT` 模板，gpt-4o-mini 作 judge（temperature=0.0）。

**Prompt 设计**：
- 宽松评分哲学："as long as it touches on the same topic as the gold answer, it should be counted as CORRECT"
- 时间问题容错：格式差异如 "May 7th" vs "7 May" 视为正确
- Compact 模式：`response_format={"type": "json_object"}`，期望 `{"label": "CORRECT"/"WRONG"}`
- 解析回退：JSON 解析失败 → regex 匹配 CORRECT/WRONG

### 10.4 LongMemEval LLM Judge（`evaluators/longmemeval_judge.py`）

使用 LongMemEval 官方 prompt 模板，**6 种任务类型各有专用 prompt**：

| Task Type | Prompt 特点 |
|-----------|------------|
| single-session-user/assistant, multi-session | 标准："response contains correct answer"；等价或中间步骤算正确；子集不算 |
| temporal-reasoning | 额外：off-by-one 天数误差不惩罚 |
| knowledge-update | 额外：同时提到旧信息+更新答案，只要更新答案正确即算对 |
| single-session-preference | Gold 是 "Rubric" 非 "Correct Answer"；只需正确回忆个人信息 |
| abstention | Gold 是 "Explanation"；判断模型是否识别不可回答 |

**解析逻辑**（`_parse_lightmem_yes_no`）：小写取首行 → 去 `.!/;` → 首 token 匹配 yes/no → 否则检查 yes/no 是否出现 → 都不匹配默认 False

### 10.5 F1 vs Judge 的语义差异

F1 衡量**精确词面匹配**（Porter stemmed token overlap），Judge 衡量**语义正确性**。两者互补：
- F1 高分 = 简洁、精确的答案（如 "Business Administration"）
- Judge 高分 + F1 低分 = 答案语义正确但冗长或措辞不同（Mem0 的典型特征）

---

## 11. 完整实验结果

### 11.1 LoCoMo Full（10 conversations, 1540 questions, gpt-4o-mini）

| Method | F1 | Judge | Cat1 F1 | Cat2 F1 | Cat3 F1 | Cat4 F1 | Run |
|--------|:---:|:-----:|:-------:|:-------:|:-------:|:-------:|-----|
| **LightMem** | **0.5019** | 0.6981 | 0.3672 | **0.6027** | **0.2567** | **0.5366** | lightmem-locomo-0619-1303 |
| MemoryOS (old) | 0.4535 | — | 0.3724 | 0.4126 | 0.2591 | 0.5186 | memoryos-locomo-full-20260603 |
| MemoryOS | 0.4418 | 0.5760 | 0.3520 | 0.4330 | 0.3014 | 0.4913 | memoryos-locomo-official_full-14b68b2d |
| A-Mem v2 | 0.4164 | 0.6513 | 0.2698 | 0.4783 | 0.1266 | 0.4750 | amem-locomo-full-v2 |
| A-Mem (old, 作废) | 0.3457 | — | 0.2801 | 0.1375 | 0.1502 | 0.4696 | amem-locomo-0619-1303 |
| **Mem0** | 0.3209 | **0.8636** | 0.3260 | 0.3480 | 0.1887 | 0.3240 | mem0-locomo-full-v4 |

**关键发现**：
- LightMem 在 F1 上全面领先（所有 category 均最高）
- Mem0 呈现极端的 F1-Judge 分裂：F1 最低（0.32）但 Judge 最高（0.86），只有 88/1540 F1 正确 vs 1330/1540 Judge 正确 → Mem0 生成语义正确但冗长、措辞不同的答案
- Cat 3（Open-domain）对所有方法都是最难的
- Cat 4（Single-hop）对所有方法都是最简单的
- A-Mem 的 session_time bug 导致 v1 Cat2 F1 从 0.48 跌到 0.14，v2 修复后恢复

### 11.2 LongMemEval（当前状态：无完整 full run）

所有四个 method 的 1conv-costpilot smoke 跑通（1 question, judge accuracy 1.0），效率数据显示 LightMem 成本最低（315K ms, 27K tokens）vs MemoryOS 最高（4.3M ms, 805K tokens）。Full-costpilot 四个 run 均无 summary — 未完成。

### 11.3 Mem0 LoCoMo 效率数据（唯一有完整 efficiency 的 full run）

| 指标 | Count | Mean | P50 | P95 |
|------|:---:|------|-----|-----|
| Memory Build (ms) | 10 conv | 4,591,937 | 4,964,483 | 5,335,704 |
| Retrieval (ms) | 1540 | 4,352 | 4,278 | 6,591 |
| Answer Gen (ms) | 1540 | 7,994 | 7,159 | 13,984 |
| Context Tokens | 1540 | 5,482 | 5,480 | 6,091 |

| Token 类型 | Calls | Input Tokens | Output Tokens |
|-----------|:---:|-------------|---------------|
| LLM Total | 7,422 | 64,816,236 | 1,309,027 |
| Embedding Total | 20,543 | 704,065 | — |

---

## 12. 效率观测系统

### 12.1 四类观测

| 观测类型 | 字段 | Stage |
|---------|------|-------|
| ConversationEfficiencyObservation | memory_build_total_latency_ms | MEMORY_BUILD |
| QuestionEfficiencyObservation | retrieval_latency_ms, injected_memory_context_tokens, answer_generation_latency_ms | RETRIEVAL/ANSWER |
| LLMCallObservation | model_id, input/output_tokens, measurement_source | MEMORY_BUILD/RETRIEVAL/ANSWER/JUDGE |
| EmbeddingCallObservation | model_id, input_tokens, latency_ms, measurement_source | MEMORY_BUILD/RETRIEVAL |

### 12.2 measurement_source 语义

- `api_usage`：从 OpenAI response usage 直接读取（最精确）
- `tokenizer_estimate`：tiktoken 估算（fallback，不等同真实账单）
- `method_native`：method 自身仪表报告
- `framework_timer`：框架 wall-clock 计时

**Token 解析策略**：优先全量 API usage，任一侧缺失 → 全部回退到 tokenizer 估算（避免混合来源）

### 12.3 线程安全

通过 `ContextVar` 实现 — 每个线程独立 scope。三种 scope 类型：
- `conversation_scope`：memory build
- `question_scope`：retrieval + answer
- `judge_scope`：evaluation LLM call

Scope 不可嵌套。Observation ID 通过 SHA-256 生成（确定性去重，支持 resume/merge）。

### 12.4 输出

三个 JSON summary：`efficiency_overall.prediction.json`、`efficiency_by_conversation.prediction.json`、`efficiency_by_question.prediction.json`。每项含 count/total/mean/p50/p95。

---

## 13. Smoke Test 与 Cost Calibration

### 13.1 Smoke vs Full 差异

**Smoke 和 official-full profile 在所有四个 method 的 TOML 中完全相同**（模型、top-k、阈值等），唯一差异是 `max_workers`（1 vs 10）。数据规模控制由 benchmark adapter 层处理：

| 维度 | Smoke | Full |
|------|-------|------|
| Conversations | smoke_conversation_limit（默认 1） | 全部 |
| History | smoke_turn_limit（默认 20）truncation | 完整 |
| Questions | 1 per conversation | 全部 |
| Profile params | 与 full 完全相同 | — |
| confirm_full | 不需要 | 需要 |
| 输出布局 | hierarchical（smoke/） | hierarchical（formal/） |

### 13.2 LoCoMo vs LongMemEval Smoke 截断差异

- **LoCoMo**：逐 turn 截断 + 证据过滤（`smoke_round_limit * 2` → turn count），移除 evidence turn 不在保留范围的 question
- **LongMemEval**：逐完整 round（2 turn pair）截断，不单独截断 turn，不涉及 evidence 过滤

### 13.3 Cost Calibration（`runners/cost_calibration.py`）

`calibrate-smoke` 命令运行 method × benchmark 矩阵，每个组合强制 smoke profile：
- Conversation 数硬编码为 1
- 每个 child run 独立 ThreadPoolExecutor（max_parallel_runs 1-4）
- Child failure 隔离（单组合失败不影响其他）
- 并行进度监控：Rich Live table 读取各 child 的 `progress.json`

---

## 14. 测试覆盖分析

### 14.1 总览

52 个测试文件，6 个 pytest markers：`unit`, `integration`, `mem0`, `memoryos`, `api`, `slow`, `expensive`。默认 `-m 'not api'` 排除付费 API 测试。**无 conftest.py** — fixtures 在各模块内联定义。

### 14.2 测试模式

大规模使用手写 Fake 类而非 `unittest.mock.MagicMock`：
- `FakeMemoryBackend`、`NamespacedFakeMemoryBackend`、`ObservableMemoryBackend` 等（Mem0）
- `FakeEvaluator`、`FakeOpenAIAnswerClient`（prediction/evaluation）
- `_FakeOfflineSystem`、`_FakeOfflineProvider`（artifact evaluation）

### 14.3 覆盖重点

- **隐私保护**：13+ 测试覆盖四层防护，验证 gold/evidence 不泄露
- **Resume**：30+ 测试覆盖 manifest 比对、conversation/question 级续传、retry-failed、turn 级拒绝、isolated worker 稳定性
- **Mem0 adapter**：contract tests 覆盖 add/retrieve/get_answer、隐私隔离、conversation 隔离、resume、效率观测
- **MemoryOS**：integration tests 覆盖 full runner、adapter、resume legacy migration

### 14.4 已知缺口

- LightMem/A-Mem 无 `@pytest.mark.api` 测试（无端到端 API smoke test）
- LightMem/A-Mem adapter 测试文件无 module-level pytestmark
- 无 evaluator registry integration 测试
- 无 benchmark registry integration 测试（用真实数据集）
- 无 CI config 可见于仓库

---

## 15. 标准输出目录

```
outputs/<run_id>/  (flat) 或 outputs/runs/<method>/<bench>/<variant>/<mode>/<run_id>/  (hierarchical)
├── manifest.json                          # 不可变运行身份（密码学 SHA-256）
├── config.redacted.json                   # 公开安全配置
├── artifacts/
│   ├── dataset_fingerprint.json
│   ├── public_questions.jsonl             # method 输入
│   ├── method_predictions.jsonl           # method 答案
│   ├── answer_prompts.prediction.jsonl    # retrieve-first 中间检索记录
│   ├── conversation_prompts.jsonl         # 去重 system_prompt
│   ├── evaluator_private_labels.jsonl     # 金答案（evaluator 专用）
│   ├── model_inventory.prediction.json
│   ├── efficiency_observations.prediction.jsonl
│   └── answer_scores.<metric>.jsonl       # evaluator 输出
├── checkpoints/
│   ├── conversation_status.json
│   ├── question_status.jsonl
│   ├── progress.json
│   └── ingest_turns/                      # 历史 turn 级续传（已禁用）
├── summaries/
│   ├── summary.json                       # PredictionRunSummary
│   ├── summary.<metric>.json              # 评分汇总
│   └── efficiency_*.prediction.json       # 效率汇总（overall/by_conv/by_q）
├── logs/
│   ├── run.log
│   └── events.jsonl
└── method_state/                          # method 私有状态（Qdrant/history.db/worker_N/）
```

---

## 16. 完整端到端执行路径（Mem0 LoCoMo official-full 为例）

```
1. CLI: memory-benchmark predict formal --method mem0 --benchmark locomo --confirm-api --confirm-full
2. main.py: 归一化 PredictCommand
3. commands.py → run_registered_conversation_qa_prediction()（13 步装配）
4. 加载 Mem0Config(max_workers=10, top_k=200, extraction=gpt-4o-mini, embedding=text-embedding-3-small)
5. prepare_locomo_run() → locomo10.json → Dataset(10 conv, 1540 q)
6. 构建 manifest（dataset SHA + mem0 source SHA + config manifest）
7. 决定 isolated-worker（max_workers=10, supports_shared_instance_parallelism=False）
8. run_predictions():
   a. 写 manifest.json + config.redacted.json
   b. 写 dataset_fingerprint.json + public_questions.jsonl + evaluator_private_labels.jsonl
   c. Stable chunking：10 worker，conv_index % 10 分配
   d. 每 worker 独立 Mem0 实例（独立 Qdrant worker_N/）
   e. 并行：add conversation → retrieve question → answer_reader 生成答案
   f. 每 batch 后原子写 artifacts
   g. 写 summary.json

9. 产出：1540 行 method_predictions.jsonl + 10 completed conversation_status + efficiency 数据
```

---

## 17. 关键架构决策总结

1. **声明式注册 + 运行时校验**：三个注册中心消除 Cartesian 积，`validate_compatibility()` 前置发现问题
2. **Retrieve-first 协议**：method 只管存储和检索，answer LLM 框架统一管理 — 解耦检索质量与答案生成质量，确保公平对比
3. **Immutable experiments**：manifest 是密码学身份，`max_new_conversations`/`question_limit_per_conversation` 是预算不进身份 — 支持分批运行
4. **Isolated worker 并行**：每个 worker 独立 method 实例 + 独立存储目录 — 消除线程安全隐患，stable chunking 保证跨 resume 一致
5. **Conversation-level resume**（唯一生效策略）：turn 级续传已于 2026-06-20 禁用，`Mem0.supports_turn_resume()` 硬编码 False
6. **Atomic writes + torn-tail recovery**：进程崩溃最多丢一个 conversation
7. **Cooperative cancellation + 连续失败熔断**：一个 worker 失败 → 通知所有 worker 停止，避免空跑浪费 API
8. **四层隐私保护**：结构排除 + 递归键名扫描 + adapter 级清洗 + 文件隔离
9. **Smoke = Full 参数**（仅 max_workers 不同）：smoke 只控制数据规模，不改变 method 行为
10. **F1 + Judge 互补评测**：F1 测精确匹配，Judge 测语义正确，两者差异揭示答案风格特征
