# Method 原生接口全面清单 (opencode-deepseekV4pro)

更新日期：2026-06-17

本文从 vendored 第三方源码直接读取，记录 Mem0、MemoryOS、A-Mem、LightMem 四个 method
官方仓库暴露的全部关键接口、写入粒度、隔离机制、reset 能力和工程特征。

---

## 一、Mem0

**源码位置**：`third_party/methods/mem0-main/mem0/memory/main.py`
**主类**：`Memory`（同步）/ `AsyncMemory`（异步）
**基类**：`MemoryBase`

### 1.1 所有公开方法

| 方法 | 签名 | 用途 | 适配器使用？ |
|---|---|---|---|
| `from_config` | `(cls, config_dict: Dict) -> Memory` | 工厂方法，从字典创建实例 | 是 |
| `add` | `(messages, *, user_id, agent_id, run_id, metadata, infer=True, memory_type, prompt)` | 写入记忆。`messages` 是 `str` 或 `List[Dict]`。`infer=True` 时 LLM 提取事实。`run_id` 做 namespace 隔离 | 是 |
| `search` | `(query, *, top_k=20, filters, threshold=0.1, rerank=False)` | 语义检索，支持 `filters={"run_id": ...}` 做 conversation 隔离 | 是 |
| `get` | `(memory_id)` | 按 ID 获取单条记忆 | 否 |
| `get_all` | `(*, filters, top_k=20)` | 列出所有记忆 | 否 |
| `update` | `(memory_id, data, metadata)` | 修改记忆 | 否 |
| `delete` | `(memory_id)` | 删除单条 | 否 |
| `delete_all` | `(user_id, agent_id, run_id)` | 按范围清空 | 否 |
| `reset` | `()` | **全量销毁**：重建向量存储集合和 SQLite 历史表 | 否 |
| `history` | `(memory_id)` | 变更历史 | 否 |
| `close` | `()` | 释放资源（SQLite 连接等） | 否 |
| `chat` | `(query)` | 抛 `NotImplementedError`，未实现 | 否 |

另有公开属性：`Memory.llm`、`Memory.embedding_model`（适配器用于安装效率观测代理）、
`Memory.entity_store`（懒加载实体存储）。

### 1.2 写入接口详情

```python
def add(
    self,
    messages,                    # str | List[Dict[str, str]]
    *,
    user_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    run_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    infer: bool = True,          # True = LLM 提取事实；False = 直存原文
    memory_type: Optional[str] = None,
    prompt: Optional[str] = None,
) -> dict:
```

`messages` 单条 string 自动包成 `[{"role": "user", "content": ...}]`；单个 dict
自动包成单元素 list。内部 V3 管道：拼接全部 messages → 一次 LLM 提取 → 批量
embedding → 批量写入向量库 → 批量链接实体。

返回值：`{"results": [{"id": "<uuid>", "memory": "<extracted text>", "event": "ADD"}, ...]}`

**官方 LoCoMo 脚本调用方式**：`CHUNK_SIZE=1`，每次传 1-2 条 message
（`[{"role":"user","content":"<speaker>: <text>"}, {"role":"assistant","content":"<speaker>: <text>"}]`）。

### 1.3 Conversation 隔离

原生支持。`add()` 和 `search()` 都接受 `run_id` 参数，不同 `run_id` 的记忆自动隔离。
适配器直接传 `run_id=conversation_id` 即可，无需额外 hack。

### 1.4 Reset 能力

**有**。`reset()` 删除向量存储集合、删除 SQLite 历史表、重建两者，同时清除实体存储。
四个 method 中唯一具备完整清空能力的。

### 1.5 异步版本

`AsyncMemory` 类提供全部方法的 `async def` 版本（`async add()`、`async search()` 等）。
内部用 `asyncio.to_thread()` 将阻塞操作（embedding、LLM、向量库）丢到线程池。

---

## 二、MemoryOS

**源码位置**：`third_party/methods/MemoryOS-main/eval/`
**三层记忆架构**：短期记忆（STM deque）→ 中期记忆（MTM heap+segment）→ 长期记忆（LTM profile+knowledge）

### 2.1 各类公开方法

**ShortTermMemory** (`short_term_memory.py`)

| 方法 | 签名 | 用途 | 适配器使用？ |
|---|---|---|---|
| `__init__` | `(max_capacity=10, file_path="short_term.json")` | 构造，STM 双端队列容量 | 是 |
| `add_qa_pair` | `(qa_pair: dict)` | **写入一个 QA pair**。dict 需包含 `user_input`、`agent_response`、`timestamp` | 是 |
| `get_all` | `()` | 返回全部 STM 页面 | 否（官方内部调用） |
| `is_full` | `()` | 队列是否满 | 是（触发 MTM 驱逐） |
| `pop_oldest` | `()` | 弹出最旧页面 | 否（驱逐时内部调用） |
| `save` | `()` | 持久化到 JSON 文件 | 否（内部自动调用） |
| `load` | `()` | 从 JSON 文件恢复 | 否（内部自动调用） |

**MidTermMemory** (`mid_term_memory.py`)

| 方法 | 签名 | 用途 | 适配器使用？ |
|---|---|---|---|
| `__init__` | `(max_capacity=7, file_path="mid_term.json")` | 构造 | 是 |
| `search_sessions_by_summary` | `(query, client, segment_threshold, page_threshold, top_k, tau, gamma, alpha)` | 按 query 检索 MTM session | 是（top_k 被 partial 为论文 top-m） |
| `insert_pages_into_session` | `(summary, keywords, pages, similarity_threshold, alpha)` | 将多个页面插入一个 session | 否（内部调用） |
| `add_session` | `(summary, details)` | 创建新 session | 否（内部调用） |
| `evict_lfu` | `()` | LFU 驱逐 | 否（容量满时内部调用） |
| `get_page_by_id` | `(page_id)` | 按 ID 获取页面 | 否（内部调用） |
| `update_page_connections` | `(prev_page_id, next_page_id)` | 维护页面链接 | 否（内部调用） |

**LongTermMemory** (`long_term_memory.py`)

| 方法 | 签名 | 用途 | 适配器使用？ |
|---|---|---|---|
| `__init__` | `(file_path="long_term.json")` | 构造 | 是 |
| `add_knowledge` | `(knowledge_text)` | 添加知识条目 | 否（内部调用） |
| `add_assistant_knowledge` | `(text)` | 添加 agent 专属知识 | 否（内部调用） |
| `get_knowledge` | `()` | 获取全部知识 | 否（内部调用） |
| `search_knowledge` | `(query, threshold, top_k)` | 检索知识 | 否（RetrievalAndAnswer 内部调用） |
| `update_user_profile` | `(user_id, new_data, merge)` | 更新用户画像 | 否（内部调用） |
| `get_user_profile` | `(user_id)` | 获取用户画像 | 否（内部调用） |

**DynamicUpdate** (`dynamic_update.py`)

| 方法 | 签名 | 用途 | 适配器使用？ |
|---|---|---|---|
| `__init__` | `(short_term_memory, mid_term_memory, long_term_memory, topic_similarity_threshold, client)` | 构造 | 是 |
| `bulk_evict_and_update_mid_term` | `()` | STM 满时批量驱逐+更新 MTM | 是 |
| `update_long_term` | `(user_id, new_profile_data, knowledge_text)` | 更新 LTM | 否（用官方独立函数替代） |

**RetrievalAndAnswer** (`retrieval_and_answer.py`)

| 方法 | 签名 | 用途 | 适配器使用？ |
|---|---|---|---|
| `__init__` | `(short_term_memory, mid_term_memory, long_term_memory, dynamic_updater, queue_capacity)` | 构造 | 是 |
| `retrieve` | `(user_query, segment_threshold, page_threshold, knowledge_threshold, client)` | 统一检索入口，跨三级记忆 | 是 |

**官方独立函数** (`main_loco_parse.py`)

| 函数 | 签名 | 用途 | 适配器使用？ |
|---|---|---|---|
| `generate_system_response_with_meta` | `(query, short_mem, long_mem, retrieval_queue, long_knowledge, client, sample_id, speaker_a, speaker_b, meta_data)` | 用检索结果生成最终回答 | 是 |
| `update_user_profile_from_top_segment` | `(mid_mem, long_mem, sample_id, client)` | 从热度最高的 MTM segment 更新 LTM 用户画像 | 是 |
| `process_conversation` | `(conversation_data)` | 把原始对话转为 QA page 列表 | 否（adapter 自行实现） |

**OpenAIClient** (`utils.py`)

| 方法 | 签名 | 用途 | 适配器使用？ |
|---|---|---|---|
| `chat_completion` | `(model, messages, temperature, max_tokens)` | 调用 OpenAI API | 是（被 adapter 的重试 wrapper 覆盖） |

### 2.2 写入接口详情

```python
# ShortTermMemory
def add_qa_pair(self, qa_pair: dict) -> None:
    # qa_pair 格式: {"user_input": ..., "agent_response": ..., "timestamp": ...}
    # 追加到 self.memory (deque)，满了自动标记 is_full()
```

**调用粒度**：单个 QA pair（user+assistant 两句话组成的一个对话轮）。

add 内部流程：
```
add_qa_pair(page)
  → 如果 STM 满了 → bulk_evict_and_update_mid_term()
    → 驱逐最旧 pages → 聚类为 MTM sessions
    → 更新 LTM 知识
  → update_user_profile_from_top_segment()
    → 按热度更新 user profile
```

每个 QA pair 来自 `process_conversation()` 把原始 `Conversation` 拆成连续的
`user_input/agent_response` 对，speaker_a → user，speaker_b → assistant。

### 2.3 Conversation 隔离

无原生 namespace。适配器为每个 conversation_id 创建独立的三级记忆实例
（`self._states[cid] = MemoryOSConversationState(...)`），每个实例指向独立的
JSON 文件目录（`storage_root/<safe_cid>/short_term.json` 等）。

### 2.4 Reset 能力

**无**。STM `pop_oldest()` 和 MTM `evict_lfu()` 是容量驱动的算法回收，不是用户可控的
清空接口。

---

## 三、A-Mem

**源码位置**：`third_party/methods/A-mem/memory_layer_robust.py`
**主类**：`RobustAgenticMemorySystem`

### 3.1 所有公开方法

| 方法 | 签名 | 用途 | 适配器使用？ |
|---|---|---|---|
| `__init__` | `(model_name='all-MiniLM-L6-v2', llm_backend="sglang", llm_model="gpt-4o-mini", evo_threshold=100, api_key, api_base, sglang_host, sglang_port, check_connection)` | 构造，初始化 embedding 模型、LLM controller、检索器 | 是 |
| `add_note` | `(content: str, time: str = None, **kwargs)` | **写入一条记忆笔记**。内部自动 LLM 提取关键词/上下文/标签，触发演进管线（最多 3 次 LLM 调用），每 `evo_threshold` 次后合并记忆 | 是 |
| `find_related_memories_raw` | `(query: str, k: int = 5)` | **检索**，返回相关记忆字符串列表（含邻居扩展） | 是 |
| `find_related_memories` | `(query: str, k: int = 5)` | 检索，返回 (字符串列表, 索引列表) 元组 | 否（内部调用） |
| `consolidate_memories` | `()` | 以当前状态重建检索索引 | 否（内部自动触发） |
| `process_memory` | `(note)` | 单条记忆的演进处理 | 否（`add_note` 内部调用） |

另有公开属性：`RobustAgenticMemorySystem.memories`（dict）、`.retriever`（SimpleEmbeddingRetriever）、
`.llm_controller.llm`（LLM 实例，adapter 通过 `hasattr` 检查用于回答生成回退）。

### 3.2 写入接口详情

```python
def add_note(
    self,
    content: str,           # 单条文本，如 "Speaker Alice says: I went to the park"
    time: str = None,       # 可选时间戳
    **kwargs,               # 透传给 RobustMemoryNote（可预填 id/keywords/links/importance_score）
) -> str:                   # 返回新建 note 的 UUID
```

内部流程：
```
add_note(content, time)
  → 创建 RobustMemoryNote
  → analyze_content()      # LLM 提取：keywords, context, tags
  → process_memory(note)   # 演进管线（最多 3 次 LLM 调用）
    → evolution_step()     # 决定演变方向
    → strengthen_step()    # 强化细节
    → neighbor_update()    # 更新邻居
  → 存入 self.memories[note.id]
  → 更新检索索引
  → 每 evo_threshold 次 → consolidate_memories()
```

**官方 LoCoMo 脚本调用方式**：逐 turn 构造 `"Speaker X says: <text>"` 字符串，调
`add_memory(content, time=turn_datatime)`，其中 `add_memory()` 是 eval wrapper 的薄封装
（`self.memory_system.add_note(content, time=time)`）。

### 3.3 Conversation 隔离

无原生 namespace。适配器为每个 conversation_id 创建独立的 `RobustAgenticMemorySystem`
实例（`self._runtimes[cid]`），每个实例在内存中完全隔离。

### 3.4 Reset 能力

**无**。`consolidate_memories()` 重建索引但不删除记忆。

---

## 四、LightMem

**源码位置**：`third_party/methods/LightMem/src/lightmem/memory/lightmem.py`
**主类**：`LightMemory`

### 4.1 所有公开方法

| 方法 | 签名 | 用途 | 适配器使用？ |
|---|---|---|---|
| `from_config` | `(cls, config: Dict[str, Any])` | 工厂方法，从字典创建实例 | 是 |
| `add_memory` | `(messages, METADATA_GENERATE_PROMPT=None, *, force_segment=False, force_extract=False, boundmem_tags=None)` | **写入**。内部管线：归一化→预压缩(LLMLingua-2)→主题分割→提取→元数据生成(LLM)→离线更新 | 是 |
| `retrieve` | `(query, limit=10, filters=None, *, boundmem_tags, boundmem_drop_untagged)` | **检索**，返回格式化字符串列表 | 是 |
| `offline_update` | `(memory_list, construct_update_queue_trigger, offline_update_trigger)` | 把待处理条目写入 Qdrant，可选构建更新队列和离线更新 | 否（`add_memory` 内部调用） |
| `construct_update_queue_all_entries` | `(top_k=20, keep_top_n=10, max_workers=8)` | 并行构建更新队列 | 否 |
| `offline_update_all_entries` | `(score_threshold=0.9, max_workers=5)` | **并行离线更新/删除冗余条目**（最接近清理的操作） | 否 |
| `online_update` | `(memory_list)` | 存根方法，返回 `None`（未实现） | 否 |
| `get_token_statistics` | `()` | 聚合 token 统计 | 否 |
| `summarize` | `(SUMMARY_PROMPT=None, *, time_window=3600, process_all=False, enable_cross_event=True, retrieval_scope="global", top_k_seeds=15)` | 跨事件摘要 | 否 |

### 4.2 写入接口详情

```python
def add_memory(
    self,
    messages,                                        # dict | List[dict]
    METADATA_GENERATE_PROMPT: Optional[Union[str, Dict[str, str]]] = None,
    *,
    force_segment: bool = False,
    force_extract: bool = False,
    boundmem_tags: Optional[Any] = None,
) -> dict:
```

每条 message dict 必须有 `time_stamp`、`role`、`content`、`speaker_id`、`speaker_name`。

**关键：内部缓冲机制**。消息先进入 `senmem_buffer_manager`，只有满足阈值或
`force_extract=True` 时才真正触发提取→embedding→写入 Qdrant。平时调 `add_memory()`
只是往缓冲区里放，不等价于"完成了一次持久化写入"。

官方 LoCoMo 脚本配置为 offline update 模式：所有 turn pair 写入完成后，再调用
`construct_update_queue_all_entries()` + `offline_update_all_entries(score_threshold=0.9)`
做最终的向量库同步。

**官方 LoCoMo 脚本调用方式**：
```python
# 遍历所有 session，按 user+assistant pair 逐对喂入
for turn_idx in range(num_turns):
    turn_messages = session[turn_idx*2 : turn_idx*2 + 2]
    for msg in turn_messages:
        msg["time_stamp"] = timestamp
    is_last_turn = (session is sessions[-1] and turn_idx == num_turns - 1)
    lightmem.add_memory(
        messages=turn_messages,
        METADATA_GENERATE_PROMPT=METADATA_GENERATE_PROMPT_locomo,
        force_segment=is_last_turn,
        force_extract=is_last_turn,
    )
```

LoCoMo 每条原始 turn 被转为 `[user(content), assistant("")]`，即一条真实内容 + 一条
空 assistant。LongMemEval 使用真实的 user+assistant pair。

### 4.3 Conversation 隔离

无原生 namespace。适配器为每个 conversation_id 创建独立的 `LightMemory` 实例
（`self._backends[cid]`），每个实例的 Qdrant collection 名从 `conversation_id` 派生
（`lightmem_<safe_cid>_<sha1[:10]>`）。

### 4.4 Reset 能力

**无顶层 reset/delete_all**。`offline_update_all_entries()` 可以删除冗余条目，但不是
批量清空。

---

## 五、横向对比

### 5.1 写入接口粒度

| Method | 原生写入函数 | 粒度 | 能否降到单 turn？ |
|---|---|---|---|
| Mem0 | `add(messages)` | list of messages（官方 LoCoMo 每次传 1 turn pair） | 可以，`CHUNK_SIZE=1` 时即单条 |
| MemoryOS | `add_qa_pair(qa_pair)` | 单 QA pair（user+assistant） | 不能，语义上是一个 round |
| A-Mem | `add_note(content)` | 单 string（一个 turn 的发言） | 已经是最小单元 |
| LightMem | `add_memory(messages)` | list of dicts（官方 LoCoMo 每次传 1 turn pair） | 有内部缓冲，平时只是入队 |

### 5.2 隔离方式

| Method | 原生支持 namespace？ | 适配器隔离策略 |
|---|---|---|
| Mem0 | **是**。`run_id` 原生隔离 | 传 `run_id=conversation_id` |
| MemoryOS | 否 | 独立实例 + 独立 JSON 目录 |
| A-Mem | 否 | 独立实例，纯内存隔离 |
| LightMem | 否 | 独立实例 + 独立 Qdrant collection |

### 5.3 Reset / 清空能力

| Method | 有 reset？ | 有 delete/delete_all？ |
|---|---|---|
| Mem0 | **是**（`reset()` 全量销毁重建） | **是**（`delete()` + `delete_all()`） |
| MemoryOS | 无 | 无 |
| A-Mem | 无 | 无 |
| LightMem | 无 | 仅 `offline_update_all_entries()` 可删冗余条目 |

### 5.4 检索接口

| Method | 检索函数 | 返回格式 | 支持 conversation 过滤？ |
|---|---|---|---|
| Mem0 | `search(query, *, filters)` | list of dict（含 memory/score/created_at） | 是，`filters={"run_id": ...}` |
| MemoryOS | `RetrievalAndAnswer.retrieve(...)` | dict（含 retrieval_queue + long_term_knowledge） | 每个实例独立，天然隔离 |
| A-Mem | `find_related_memories_raw(query, k)` | list of str | 每个实例独立 |
| LightMem | `retrieve(query, limit, filters)` | list of str（格式化后的记忆文本） | 每个实例独立 |

### 5.5 回答生成

| Method | 是否有原生回答接口？ | 适配器如何生成回答 |
|---|---|---|
| Mem0 | 无（`chat()` 抛 NotImplementedError） | 固定 reader：search → 构造 prompt → `gpt-4o-mini` |
| MemoryOS | **是**：`generate_system_response_with_meta()` | 直接调用官方函数 |
| A-Mem | 无（有 `answer_question()` 但需要 gold answer） | 固定 reader：`find_related_memories_raw()` → category prompt → LLM |
| LightMem | 无 | 固定 reader：`retrieve()` → prompt → `gpt-4o-mini` |

### 5.6 工程成熟度

| 维度 | Mem0 | MemoryOS | A-Mem | LightMem |
|---|---|---|---|---|
| 配置注入 | `from_config()` 标准工厂 | 无，手工拼装 | 构造函数传参 | `from_config()` 标准工厂 |
| namespace 隔离 | **原生支持** | 需多实例 hack | 需多实例 hack | 需多实例 hack |
| 异步支持 | 完整 `AsyncMemory` | 无 | 无 | 无 |
| CRUD 完整性 | add/search/get/update/delete/reset | 仅 add + retrieve | 仅 add_note + retrieve | add/retrieve + 离线更新管线 |
| 测试覆盖 | 完善（pytest CI） | eval 脚本级别 | 少量 | 少量 |
| 代码风格 | 工厂模式 + 抽象基类 | 脚本风格 | 单文件类 | 模块化但要依赖重型 |

---

## 六、对本项目 resume 解耦的影响

### 6.1 当前 resume 耦合点

- **Mem0**：实现 `BaseResumableMemorySystem`（`add_from_turn` + `existing_conversation_ids`）
- **MemoryOS**：非标准 `load_existing_conversation_state()`，从 JSON 文件恢复
- **A-Mem**：无 resume，实例为纯内存
- **LightMem**：无 resume，实例为纯内存 + Qdrant 文件

### 6.2 解耦可行性

不改 `add(list[Conversation])` 接口的前提下，可通过标准化 `save_state`/`load_state`
协议让 runner 统一控制状态持久化，代价是丢失 turn 级精度（crash 后整 conversation
重加）。

LightMem 额外难点：`add_memory()` 内部有缓冲，大部分调用不触发持久化，runner 无法
在调用层面判断"是否已真正写入"。
