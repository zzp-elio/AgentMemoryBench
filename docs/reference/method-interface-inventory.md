# Method 原生接口清单

更新日期：2026-07-09（ws02.5 接口保真审计交付物，架构师签发）

本文是 ws02.5「Method 接口保真审计」workstream 的交付物，记录 Phase 1 五个
method（Mem0 / MemoryOS / A-Mem / LightMem / SimpleMem）注入与检索所用的
**通用产品接口**、注入/检索 API、`formatted_memory` 拼装口径，以及第三方仓库与本
项目 adapter 的证据行号。事实来源：4 份 `audit-*.md` + ws02.5 README 验收表 +
MemoryOS 迁移 plan/断点；本文引用的每个行号均经 grep 第一手复核（2026-07-09）。

ws02.5 裁决（用户认可）：**所有 method 跨全部 benchmark 统一用通用产品接口注入/
检索，不用任何 benchmark 专用评测实现。** 三条理由：① 公平/可比（专用实现可能带
该 benchmark 的调参/prompt → 主场优势）；② 代表性（通用产品是真实用户 `pip install`
得到的东西）；③ benchmark 专用目录自带数据加载+打分，恰是框架要替换的部分，只作
只读参考（看作者官方用法/参数）。

总账：Mem0 一开始就对（零迁移）；SimpleMem 接口对但 formatted_memory 曾缺字段
（P0 已补全 6 字段，commit 3e177c3）；LightMem 一条路径曾自复刻 benchmark 专用检索
（P1 已统一走官方 `embedding_retriever.search`，commit 63ccba2）；A-Mem 用论文复现包
引擎（benchmark 无关，无公平问题，保持现状）；MemoryOS 曾用 eval/ LoCoMo 主场副本
（P1 已迁 memoryos-pypi，commit c73d4d5）。**只有 MemoryOS 是真"主场优势"问题，其余
是不同程度的清理/补全。** 全量回归 `uv run pytest -q -m "not api"` = 804 passed
（MemoryOS 迁移后基线；旧 892 中 ~140 eval-专属测试被 51 pypi 测试合理替代）。

每个 method 节按以下 5 项记录：

1. **通用产品接口与版本裁定**：用的哪套接口（仓库路径 + 版本裁定）。
2. **注入 API**：函数签名 + 粒度（turn/pair/session）+ 官方参数 + 是否触发 LLM。
3. **检索 API**：函数签名 + 返回哪些记忆层 + top_k；若从耦合方法剥离（MemoryOS 从
   `get_response` 剥），写明剥离口径 + 保留了哪些算法机制。
4. **formatted_memory 拼装口径**：覆盖哪几层。
5. **证据行号**：第三方仓库 + adapter。

强规则（沿用）：

- 新 method 接入目标是 memory-module interface（`MemoryProvider.ingest(unit)` +
  `retrieve(RetrievalQuery) -> RetrievalResult`），不再强制实现 `get_answer(question)`。
- adapter 必须实现 method 的官方写入和检索逻辑，并在 `retrieve(question)` 中返回
  完整 `AnswerPromptResult.prompt_messages`（主线 unified 口径由框架 reader 答题）。
- 如果第三方原始仓库没有统一 retrieve 接口，adapter 必须用其官方内部检索逻辑包装出
  `retrieve()`，不自造检索算法。
- `gpt-4o-mini` 是当前阶段唯一真实 LLM 模型选择；不要使用 `gpt-4o`、GPT-5 或其他
  模型，除非用户后续明确改口。
- gold answer、evidence、judge label、LongMemEval `answer_session_ids` 等私有字段
  不能进入 method public input。
- 新 method 未完成本清单记录前，不得启动真实 API smoke。

---

## Mem0

### 1. 通用产品接口与版本裁定

用通用产品包 `mem0`（`pip install mem0ai` 得到的那套），进程内调用。版本裁定：
**维持 vendored `mem0/` 包（V3 算法），零迁移**。

- 仓库 `third_party/methods/mem0-main/` 顶层有三类代码：
  - `mem0/` 包（通用产品，V3 本地算法）——adapter 用的就是它。
  - `evaluation/`（老论文评测，调 **Mem0 Cloud API** v2，非本地算法 fork）。
  - `memory-benchmarks/`（新评测套件，独立仓库，走 HTTP server，算法本体仍是 `mem0/`
    包）。
- 核心算法只有一份本地实现（`mem0/memory/main.py` 的 V3：ADD-only + entity linking +
  multi-signal 检索）。adapter 完全合规于 ws02.5 裁决，与 MemoryOS 包 eval/ 专用引擎
  的情形根本不同——Mem0 这边无需迁移。

### 2. 注入 API

`Memory.add(messages, *, user_id=None, agent_id=None, run_id=None, metadata=None,
infer=True, memory_type=None, prompt=None)`（`mem0/memory/main.py:573`）。

- **粒度**：Mem0 不强制粒度，由调用方传 messages 长度决定。adapter `consume_granularity`
  按 benchmark：LoCoMo 用 turn 级（逐 turn，`ingestion_chunk_size=1`），LongMemEval/
  HaluMem 用 pair 级（user+assistant 两 turn 批次）或 session 级（registry 按 benchmark
  profile 实例级设）。
- **官方参数**：`infer=True` 触发 V3 LLM 提取（`main.py:699` PHASED BATCH PIPELINE：
  context→existing retrieval→ADDITIVE_EXTRACTION_PROMPT 单次提取→batch embed→hash
  dedup→entity link）；`infer=False` 直接存 raw。`prompt` 注入自定义提取 prompt（adapter
  用它注入时间感知）。隔离用 `user_id`/`agent_id`/`run_id` 三选一（`main.py:1193` 强制
  至少一个）。
- **是否触发 LLM**：**是**（`infer=True` 时）。V3 是 single-pass ADD-only（无 UPDATE/
  DELETE，记忆累积不覆盖）+ entity linking（`_upsert_entity` `main.py:413`，写入
  `entity_store.linked_memory_ids`）。adapter 用 `infer=self.config.infer`（默认 True）
  + `prompt=self._observation_time_prompt(...)`。

### 3. 检索 API

`Memory.search(query, *, top_k=20, filters=None, threshold=0.1, rerank=False, **kwargs)`
（`mem0/memory/main.py:1126`）。

- **返回记忆层**：**只有一层** —— vector store 里的 extracted memories
  （`MemoryItem{id,memory,hash,created_at,updated_at,score}`）。Mem0 没有 MemoryOS 那种
  短/中/长期分层；"Multi-Level Memory"（README:78）指 user/session/agent 三个隔离维度，
  不是记忆层级。`entity_store` 是 entity linking 的辅助索引，其贡献折进每条 memory 的
  `score`，不作为独立层返回。
- **top_k**：官方默认 20（`main.py:1130`）；memory-benchmarks 官方评测默认 200；adapter
  用 `top_k=200`（与官方评测口径一致）。
- **检索内部 `_search_vector_store`（`main.py:1343`）三信号融合**：① Semantic
  （vector_store.search，over-fetch `max(limit*4,60)`）；② BM25 keyword
  （`keyword_search`+`normalize_bm25`）；③ Entity boost（`_compute_entity_boosts`，从
  `entity_store` 查 query 实体，按 `linked_memory_ids` 加权）。三信号融合取 top_k。
- **耦合评估**：`Memory` 类**没有** `answer`/`get_response`/`generate` 方法（search 是
  纯检索，返回记忆列表）。检索与答题天然分离，**无需剥离**（与 MemoryOS 根本不同）。
  注：`Memory` 有 `chat()`（`main.py:1791`），但 adapter 没用它。

### 4. formatted_memory 拼装口径

adapter `retrieve` 调 `self._memory.search` 拿 `memories` → `_memory_context_text`
（`mem0_adapter.py:1639`）拼成 `formatted_memory` 文本；空则回退
`"(No relevant memories found)"`。覆盖：**单一记忆层**（vector store extracted memories
全量，三信号 boosting 已折进 score）。`RetrievalResult.items` 逐条带
content/score/timestamp 完整落盘。entity_store 默认懒加载启用，adapter 还主动预热
（`_prewarm_entity_store` `mem0_adapter.py:1105`）确保 worker 并发前就绪。

> graph relations（Mem0+）：本地 `Memory.search` 不返回 relations，需配 `graph_store`
> （adapter 未配）+ 走 Cloud API。memory-benchmarks 官方 OSS 默认也是 vector+entity 不含
> graph。**不算漏层**；若后续纳入是新增能力而非补漏。

### 5. 证据行号

| 事实 | 证据 |
| --- | --- |
| 通用产品入口 | `mem0/__init__.py:9` `from mem0.memory.main import ... Memory` |
| `Memory.from_config` | `mem0/memory/main.py:535` |
| `Memory.add` 签名 | `mem0/memory/main.py:573` |
| V3 提取 pipeline | `mem0/memory/main.py:699`（ADD-only + entity link） |
| `Memory.search` 签名 | `mem0/memory/main.py:1126` |
| `_search_vector_store` 三信号融合 | `mem0/memory/main.py:1343` |
| adapter 导入通用 Memory | `mem0_adapter.py:1081`（`importlib.import_module("mem0")`） |
| adapter `from_config` 构造 | `mem0_adapter.py:1098` |
| adapter `build_backend_config`（无 graph_store） | `mem0_adapter.py:354` |
| adapter ingest | `mem0_adapter.py:455` |
| adapter add 调用 | `mem0_adapter.py:483,506,546,773,827` |
| adapter retrieve | `mem0_adapter.py:846` |
| adapter search 调用 | `mem0_adapter.py:876,882,956,962` |
| adapter `top_k=200` | `mem0_adapter.py:157,175` |
| adapter `consume_granularity="turn"` | `mem0_adapter.py:272` |
| formatted_memory 拼装 `_memory_context_text` | `mem0_adapter.py:1639` |
| entity_store 预热 | `mem0_adapter.py:1105` |
| answer prompt 来自 memory-benchmarks | `mem0_adapter.py:69,1599,1630` |

---

## MemoryOS

### 1. 通用产品接口与版本裁定

用通用产品引擎 `memoryos-pypi`（`pip install memoryos` 得到的那套），**已从 eval/
LoCoMo 主场副本迁出**（ws02.5 P1，commit c73d4d5）。

- 仓库 `third_party/methods/MemoryOS-main/` 有四个变体：
  - `memoryos-pypi/`（通用产品，文件式存储）——**adapter 现用**。
  - `memoryos-chromadb/`（同算法，存储后端换 ChromaDB，多一个 `storage_provider.py`）。
  - `memoryos-mcp/`（MCP server 服务层，非另一套引擎）。
  - `eval/`（LoCoMo 专用评测副本，自带数据+打分，与 pypi 是两套独立代码）——**旧
    adapter 包的就是它，已迁走**。
- 版本裁定（架构师第一手，用户认可）：**用 pypi，不用 mcp/chromadb/eval**。理由：① mcp
  是协议层，进程内调库无需起服务；② chromadb 同算法但多向量库依赖，pypi 文件式存储
  更适合每 conversation 小隔离空间（删目录即 clean-retry）；③ pypi 最具代表性；④ 依赖
  最少最可复现。核心算法在 pypi 与 chromadb 间一致。

### 2. 注入 API

`Memoryos.add_memory(user_input: str, agent_response: str, timestamp: str = None,
meta_data: dict = None)`（`memoryos.py:226`）。

- **粒度**：QA pair（user turn + assistant turn），一次一个 user-agent 交换对。adapter
  `consume_granularity` 按 benchmark：LongMemEval→`pair`，LoCoMo→`session`（registry 按
  benchmark profile 实例级设；LoCoMo role=speaker 名，pair 聚合按 `role=="user"` 锚失效，
  故整 session 投递，adapter 内部 `conversation_to_memory_pages` 按 speaker 配对）。
- **官方参数**：构造 `Memoryos(user_id, openai_api_key, data_storage_path,
  assistant_id, short_term_capacity=10, mid_term_capacity=2000,
  long_term_knowledge_capacity=100, retrieval_queue_capacity=7,
  mid_term_heat_threshold=5.0, mid_term_similarity_threshold=0.6, llm_model="gpt-4o-mini",
  embedding_model_name="all-MiniLM-L6-v2")`（`memoryos.py:29-44`）。adapter 用 **pypi 官方
  默认**（10/2000/100/7/5.0/0.6），不再用旧 eval/ LoCoMo 调参（旧 7/200 等）。存储：
  `data_storage_path/users/<user_id>/{short_term,mid_term,long_term_user}.json` +
  `assistants/<assistant_id>/long_term_assistant.json`（`memoryos.py:71-84`），天然文件式
  物理隔离 → 每 conversation 一个目录 = clean-retry 删目录。
- **是否触发 LLM**：**是（LLM-heavy）**。`add_memory` 满 STM 时触发
  `updater.process_short_term_to_mid_term`（LLM：summarize/continuity/meta_info）+
  `_trigger_profile_and_knowledge_update_if_needed`（`memoryos.py:126`，LLM：profile/
  knowledge 抽取）。真实 smoke 有 API 成本；fake 测试须 stub `backend.client.chat_completion`。
- **orphan/dangling 容错**：dangling user（second=None, role=user）→
  `agent_response=""`；orphan assistant（second=None, role≠user）→ `user_input=""`。空串
  容错已第一手验证通过，注入不丢。

### 3. 检索 API

pypi **无独立公开 retrieve**；检索埋在 `get_response`（`memoryos.py:252-348`）里。
adapter 从 `get_response` **剥离出纯检索**（ws02.5 核心难点）。

- **剥离口径**：adapter `retrieve`（`memoryos_adapter.py:746`）复刻 `get_response`
  **步骤 1-7**（纯检索+组装），**跳过步骤 8-9 答题 LLM 与步骤 10 `add_memory` 写副作用**：
  - step1（`memoryos.py:259`）`retriever.retrieve_context(user_query, user_id)` →
    `retrieved_pages`(中期) + `retrieved_user_knowledge` + `retrieved_assistant_knowledge`。
    adapter `_retrieve_context`（`memoryos_adapter.py:781`）封装此步。
  - step2（`:269`）`short_term_memory.get_all()` → 短期 history。
  - step3（`:276-279`）中期 pages 组装成 `retrieval_text`。
  - step4（`:282`）`user_long_term_memory.get_raw_user_profile(user_id)` → 长期 profile。
  - step5（`:287-293`）长期 user knowledge 组装。
  - step6（`:297-302`）长期 assistant knowledge 组装。
  - step8-9（`:314-343`）答题 LLM ——**跳过**。
  - step10（`:346`）`add_memory` 写副作用 ——**跳过**。
- **返回记忆层**：覆盖**全部 5 层**——短期 history + 中期 retrieved_pages + 长期 profile
  + 长期 user_knowledge + 长期 assistant_knowledge。漏任何一层 = 记忆不完整 = 数字失真。
- **top_k**：pypi retrieve_context 内部按 `mid_term_capacity`/`retrieval_queue_capacity`
  等容量参数截断，无显式 top_k 参数。
- **保留的算法机制（关键）**：`retrieve_context` 内部 `search_sessions` 会更新 mid_term
  访问统计（`N_visit`/`last_visit_time`/`R_recency`）并 save（驱动中→长晋升，LFU/heat）。
  这是 **MemoryOS 检索算法固有行为**（作者自己的 eval `search_sessions_by_summary`
  `eval/mid_term_memory.py:236-238` 就这么做），**必须保留**（压掉就不是 MemoryOS）。
  契约只锁"不写新内容污染"（step-10 `add_memory` + short_term/profile/knowledge 内容
  不变），mid_term 访问统计/heat 变化如实发生、不断言。

### 4. formatted_memory 拼装口径

`_assemble_memoryos_formatted_memory`（`memoryos_adapter.py:1220`）忠实复刻官方
`get_response`（`memoryos.py:268-302`）的文本拼装，覆盖**全部 5 层**：短期 history_text
（`:1244-1251`，复刻 `:269-273`）+ 中期 retrieval_text（`:1253-1261`，复刻 `:276-279`）
+ 长期 profile + user_knowledge background（`:1263-1280`，复刻 `:282-293`）+ 长期
assistant_knowledge（`:1282-1296`，复刻 `:297-302`）。各层文本 `"\n\n".join` 拼成
formatted_memory。`_build_memoryos_prompt_messages`（`:1302`）构造 unified reader 用的
prompt messages。

### 5. 证据行号

| 事实 | 证据 |
| --- | --- |
| `Memoryos` 构造 + 官方默认参数 | `memoryos-pypi/memoryos.py:29-44` |
| 存储路径（文件式隔离） | `memoryos-pypi/memoryos.py:71-84` |
| `add_memory` 签名 | `memoryos-pypi/memoryos.py:226` |
| `_trigger_profile_and_knowledge_update_if_needed` | `memoryos-pypi/memoryos.py:126` |
| `get_response`（检索埋此） | `memoryos-pypi/memoryos.py:252-348` |
| step1 retrieve_context | `memoryos-pypi/memoryos.py:259` |
| step2 短期 get_all | `memoryos-pypi/memoryos.py:269` |
| step3 中期 pages 组装 | `memoryos-pypi/memoryos.py:276-279` |
| step4 长期 profile | `memoryos-pypi/memoryos.py:282` |
| step5 长期 user knowledge | `memoryos-pypi/memoryos.py:287-293` |
| step6 长期 assistant knowledge | `memoryos-pypi/memoryos.py:297-302` |
| step10 add_memory 写副作用（跳过） | `memoryos-pypi/memoryos.py:346` |
| 检索固有 heat 更新（保留） | `eval/mid_term_memory.py:236-238,265` |
| adapter pypi 包加载 spec_from_file_location | `memoryos_adapter.py:274` |
| adapter `build_memoryos_source_identity` | `memoryos_adapter.py:301` |
| adapter ingest（pair/session 分发） | `memoryos_adapter.py:634` |
| adapter add_memory 调用 | `memoryos_adapter.py:564,668,692` |
| adapter retrieve（剥离） | `memoryos_adapter.py:746` |
| adapter `_retrieve_context`（step1） | `memoryos_adapter.py:781` |
| adapter `_assemble_memoryos_formatted_memory`（全层） | `memoryos_adapter.py:1220` |
| adapter `_build_memoryos_prompt_messages` | `memoryos_adapter.py:1302` |

---

## A-Mem

### 1. 通用产品接口与版本裁定

用 vendored 论文复现包引擎 `RobustAgenticMemorySystem`（`third_party/methods/A-mem/`），
**非**官方产品库 `A-mem-sys`（`pip install`）。版本裁定：**保持现状（复现包），暂不迁
产品库**（ws02.5 P2，架构师裁定）。

- `A-mem/README.md:3-5` 自述"本仓库为复现论文，用请去 A-mem-sys"。但**关键区别**：复现
  引擎 **benchmark 无关**——记忆引擎 prompt（`llm_text_parsers.py` 5 个常量）全是通用
  A-Mem 算法 prompt，无任何 LoCoMo 逻辑；LoCoMo 专用件（`load_dataset.py`/`test_advanced_
  robust.py`/`utils.py`/`data/locomo10.json`）只服务数据加载+QA+打分，与记忆引擎解耦，
  adapter 全没碰。→ **无 MemoryOS 那种主场优势问题**。
- 与 MemoryOS 情形本质不同：MemoryOS 同仓库内有 pypi（产品）vs eval（专用）两套副本；
  A-Mem 仓库内只有一套引擎，产品库在另一个仓库。维持现状论据：① 引擎 benchmark 无关、
  retrieve 独立、formatted_memory 完整；② SimpleEmbeddingRetriever 无外部依赖，每
  conversation 一个目录 = 最简物理隔离；③ 迁 A-mem-sys 需换引擎（list[dict] vs str）+
  引入 ChromaDB + 重写 formatted_memory + 风险丢 link 邻域。低优先 follow-up：核 A-mem-sys
  产品算法是否有别。
- 用 **robust 版**（非 standard）：README:89 推荐 robust（"works with any LLM backend"）；
  standard 依赖 `response_format` JSON schema 限 OpenAI，robust 改纯文本+section-marker
  解析+retry+降级适配任意 OpenAI-compatible backend。两版**算法等价**（robust 建立在
  standard 之上，`memory_layer_robust.py:24` `from memory_layer import ...`）。

### 2. 注入 API

`RobustAgenticMemorySystem.add_note(content: str, time: str = None, **kwargs) -> str`
（`memory_layer_robust.py:377`）。

- **粒度**：单条 turn（adapter 按 turn 逐条调，`consume_granularity="turn"`，无 batch）。
  adapter ingest（`amem_adapter.py:339`）→ `_call_runtime_add`（`:834`）→
  `runtime.add_note(content, time=timestamp)`（`:841`），content=`f"Speaker {turn.speaker}
  says: {turn.content}"`。
- **官方参数**：`time`（注入时间戳，必传以保留 session 时间）；`**kwargs` 可预填
  keywords/context/tags（默认全由 LLM 抽取）。
- **是否触发 LLM**：**是**。`add_note` 触发：① `analyze_content()`（LLM 抽
  keywords/context/tags，失败 heuristic 降级）；② `process_memory`（`:463`）：先
  `find_related_memories(content, k=5)` 找邻居 → **3 次顺序** LLM call（evolution decision
  / strengthen / update neighbors）→ strengthen 时 `note.links.extend(...)` 建链；③ 存
  `self.memories[note.id]` + `retriever.add_documents(content+context+keywords+tags)`；
  ④ 每 `evo_threshold`（默认 100）触发 `consolidate_memories()`（重建 retriever）。

### 3. 检索 API

`find_related_memories_raw(query: str, k: int = 5) -> str`（`memory_layer_robust.py:430`）。

- **返回记忆层**：A-Mem 是**单层 note 集合**（非多层）。返回拼好的 str，含：
  - 主 memory（每条）：`talk start time` + `memory content` + `memory context` +
    `memory keywords` + `memory tags`（`:440-446`）。
  - **links 邻域 memory**（每个 note 的 `note.links` 邻居，`:447-458`）：同字段，每个主
    memory 最多扩展 k 个邻居。→ **note + link 核心全覆盖**，无漏层。
- **top_k**：官方脚本默认 `k=10`（`test_advanced_robust.py:348`），论文 Table 8 有
  per-category k。adapter 用论文 Table 8 的 GPT-4o-mini per-category k
  `AMEM_GPT4O_MINI_CATEGORY_K={1:40,2:40,3:50,4:50,5:40}`（`amem_adapter.py:77`，
  `_retrieve_k_for_question` `:929-936`），比官方脚本固定 k=10 更细；非 LoCoMo/无 category
  回退 profile `retrieve_k`。
- **耦合评估**：`find_related_memories_raw` 是**独立纯检索 API**，返回 str 不调答题 LLM，
  检索与答题**天然分离**（与 MemoryOS 根本不同，无需剥离）。retrieve 内部先
  `_generate_query_keywords`（`amem_adapter.py:896`，LLM 把 question 改写为 keywords）再
  检索——这是 A-Mem 官方 robust QA 流程（`test_advanced_robust.py:96-107` 的
  `generate_query_llm`→`retrieve_memory`），属检索一部分（query 改写），keyword prompt 逐
  字复刻官方，**不是答题耦合**。
- **隐私边界**：category 5（adversarial）官方 prompt 需 gold answer 构造二选一，adapter
  按 public-input 规则显式拒绝（`amem_adapter.py:444-449`）。

### 4. formatted_memory 拼装口径

adapter `formatted_memory = str(runtime.find_related_memories_raw(query_keywords, k))`
（`amem_adapter.py:460,469,474`，`str(context)` 未裁剪/重排）。覆盖：**单层 note + link
邻域**——主 memory（timestamp+content+context+keywords+tags）+ links 邻域 memory（同 5
字段）。与官方 `find_related_memories_raw` 输出字段逐字一致。未进 formatted_memory 的
`importance_score`/`retrieval_count`/`last_accessed`/`evolution_history`/`category` 是
内部统计/元数据，官方本就不拼，adapter 对齐。

### 5. 证据行号

| 事实 | 证据 |
| --- | --- |
| README 自述复现包，指向 A-mem-sys | `A-mem/README.md:3-5` |
| README 推荐 robust | `A-mem/README.md:89` |
| `RobustMemoryNote` 字段集 | `memory_layer_robust.py:273` |
| `RobustAgenticMemorySystem` | `memory_layer_robust.py:352` |
| `add_note` 签名 | `memory_layer_robust.py:377` |
| `find_related_memories_raw`（主+邻域，返 str） | `memory_layer_robust.py:430` |
| `process_memory`（3 次顺序 LLM call） | `memory_layer_robust.py:463` |
| 5 个通用 prompt（benchmark 无关） | `llm_text_parsers.py:128,143,164,180,204` |
| adapter `AMEM_GPT4O_MINI_CATEGORY_K` | `amem_adapter.py:77` |
| adapter `import_amem_robust_classes` | `amem_adapter.py:191` |
| adapter `consume_granularity="turn"` | `amem_adapter.py:232` |
| adapter ingest | `amem_adapter.py:339` |
| adapter `_call_runtime_add`→`add_note` | `amem_adapter.py:834,841` |
| adapter retrieve | `amem_adapter.py:434` |
| adapter `find_related_memories_raw` 调用 | `amem_adapter.py:460,469` |
| adapter `str(context)` formatted_memory | `amem_adapter.py:474` |
| adapter `_create_official_runtime` | `amem_adapter.py:709` |
| adapter `_generate_query_keywords` | `amem_adapter.py:896` |
| adapter `_retrieve_k_for_question`（category k） | `amem_adapter.py:929-936` |
| adapter category 5 拒绝（隐私边界） | `amem_adapter.py:444-449` |

---

## LightMem

### 1. 通用产品接口与版本裁定

用通用产品 `LightMemory` 类（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py`），
**P1 已统一检索走官方组件**（commit 63ccba2）。

- LightMem 仓库为单仓库单核心算法（`LightMemory` 类），**无 pypi/eval/mcp 多版本 fork**
  （与 MemoryOS 不同）。`mcp/server.py` 是服务封装层非另一套引擎；`src/fluxmem`/`src/em2mem`
  是同仓库的**其他 method**，非 LightMem 变体。
- 仓库有 benchmark 专用评测目录 `experiments/`（locomo/longmemeval/egolife，各自带数据+
  检索+QA+judge），但它们调用的就是通用产品 `LightMemory` 类（`add_locomo.py:8`
  `from lightmem.memory.lightmem import LightMemory`）——benchmark 专用脚本与通用产品
  **共用同一引擎**，差异只在数据加载/检索封装/打分（这些是框架要替换的）。
- P1 修复前：LoCoMo 路径曾自复刻 `search_locomo.py` 的 combined cosine（get_all+手算
  cosine）以拿 payload 做 speaker 分组。P1 后：统一调官方 `embedding_retriever.search
  (return_full=True)` 拿带 payload 结果，两路径统一返回 `list[dict]`，删自复刻
  `_cosine_similarity`。Step1 等价 gate 已核实自复刻 vs 官方 `VectorRetriever.retrieve`
  逐行等价（无主场优势）。

### 2. 注入 API

`LightMemory.add_memory(messages, METADATA_GENERATE_PROMPT=None, *, force_segment=False,
force_extract=False, boundmem_tags=None) -> dict`（`lightmem.py:204`）。

- **粒度**：message list（每条 dict 需含 `time_stamp` 字段，`MessageNormalizer` 强制要求）。
  官方 LoCoMo 用法是逐 turn 调一次（`add_locomo.py:332-336`），末 turn
  `force_segment=is_last, force_extract=is_last`。adapter `consume_granularity` 按
  benchmark：LoCoMo→turn，LongMemEval→pair（registry 实例级设）。adapter 用一拍缓冲保证
  最后一批 `force_segment=True, force_extract=True`。
- **官方参数**：`force_segment`/`force_extract` 在 buffer 未达阈值时强制触发分段/抽取；
  `METADATA_GENERATE_PROMPT` 可传自定义抽取 prompt（LoCoMo profile 传官方抽取 prompt）。
- **是否触发 LLM**：**是**。`add_memory` 触发：normalize → 预压缩（LLMLingua-2）→ topic
  分段 → 短期 buffer 累积 → 抽取（metadata+summary，LLM）→ 写 `MemoryEntry` → 按 update
  模式 online/offline 持久化。`end_conversation` 执行
  `construct_update_queue_all_entries()` + `offline_update_all_entries(score_threshold=0.9)`
  （与官方 LoCoMo `add_locomo.py:446-447` 一致）。

### 3. 检索 API

`LightMemory.retrieve(query, limit=10, filters=None, *, boundmem_tags=None,
boundmem_drop_untagged=False) -> list[str]`（`lightmem.py:644`）。

- **返回记忆层**：只查 `self.embedding_retriever`（主记忆库，`:675-680`
  `embedding_retriever.search(query_vector, limit, filters, return_full=True)`）。返回
  `list[str]`，每条 `"{time_stamp} {weekday} {memory}"`（`:693-701`），**丢弃 payload**
  （speaker_name/id/score 等）。**不查 `summary_retriever`**（summary 层独立，仅 `summarize()`
  写入，adapter 不调 → summary 库始终为空，不构成漏，与官方 LightMem 模式一致）。
- **top_k**：`limit` 参数，默认 10；adapter 用 `config.retrieve_limit`。
- **adapter 检索路径（P1 后统一）**：`_retrieve_with_payload`（`lightmem_adapter.py:1002`）
  调官方 `embedding_retriever.search(query_vector, limit, filters=None, return_full=True)`
  （`:1035`）拿带 payload 结果（保留官方 retrieve 会丢的 payload，供 LoCoMo speaker 分组
  与统一 formatted_memory）。LongMemEval 与 LoCoMo 两路径统一调用此方法，消除原 LoCoMo
  自复刻。`retrieve`（`:682`）内 `memories = self._retrieve_with_payload(backend, question)`
  （`:698,700`）。
- **耦合评估**：`LightMemory` 类**无** `answer`/`chat`/`get_response` 方法，`retrieve` 是
  纯检索返回 `list[str]`/`list[dict]`，不调答题 LLM。检索与答题**完全解耦**，剥离零困难
  （与 MemoryOS 根本不同）。

### 4. formatted_memory 拼装口径

adapter `retrieve` 把 `_retrieve_with_payload` 返回的 memories 拼成
`memory_context = "\n".join(_format_lightmem_memory(memory) ...)`（`lightmem_adapter.py:701-703`），
作为 `AnswerPromptResult.metadata["answer_context"]`；`_retrieve_native`（`:738`）的
`formatted_memory` 取此 `answer_context`（`:756-762`）。

- `_format_lightmem_memory`（`lightmem_adapter.py:1515`）：格式
  `[Memory recorded on: {date}{, weekday}]\n{memory_text}`，对齐官方
  `format_related_memories`（`experiments/locomo/retrievers.py:143-160`）。从带 payload 的
  retrieval dict 中还原 time_stamp/weekday/memory。
- 覆盖记忆层：**仅主记忆库**（embedding_retriever）。summary 层因未启用 `summarize()` 而
  不涉及（与官方 LightMem 模式一致，非缺陷）。
- LongMemEval 路径的 `prompt_messages` 另用 `_format_lightmem_memory_as_official_retrieve`
  （`:1555`，格式 `"{time_stamp} {weekday} {memory_text}"`，对齐官方 retrieve list[str]
  格式 `lightmem.py:693-701`，`_build_prompt_messages` `:1214` LongMemEval 分支 `:1222-1223`），
  使 answer prompt 呈现与官方 `run_lightmem_gpt.py:186` 一致——这是 prompt 格式，formatted_memory
  统一用 `_format_lightmem_memory`。

### 5. 证据行号

| 事实 | 证据 |
| --- | --- |
| `LightMemory` 类 | `src/lightmem/memory/lightmem.py:107` |
| `from_config` | `src/lightmem/memory/lightmem.py:195` |
| `add_memory` 签名 | `src/lightmem/memory/lightmem.py:204` |
| `retrieve` 签名（返 list[str]，丢 payload） | `src/lightmem/memory/lightmem.py:644` |
| retrieve 内部查 embedding_retriever | `src/lightmem/memory/lightmem.py:675-680` |
| retrieve 返回格式 `"{ts} {wd} {mem}"` | `src/lightmem/memory/lightmem.py:693-701` |
| `summarize`（需 summary_retriever，adapter 不调） | `src/lightmem/memory/lightmem.py:750` |
| LoCoMo 官方配置（extract_threshold=0.1 等） | `experiments/locomo/add_locomo.py:159-227` |
| LoCoMo 官方 offline_update score_threshold=0.9 | `experiments/locomo/add_locomo.py:446-447` |
| `VectorRetriever.retrieve`（等价 gate 已核） | `experiments/locomo/retrievers.py:111-132` |
| `format_related_memories`（格式化口径） | `experiments/locomo/retrievers.py:143-160` |
| adapter ingest | `lightmem_adapter.py:515` |
| adapter retrieve | `lightmem_adapter.py:682` |
| adapter `_retrieve_with_payload`（P1 统一） | `lightmem_adapter.py:1002` |
| adapter `embedding_retriever.search` | `lightmem_adapter.py:1035` |
| adapter memory_context 拼装 | `lightmem_adapter.py:701-703` |
| adapter `_format_lightmem_memory`（formatted_memory） | `lightmem_adapter.py:1515` |
| adapter `_format_lightmem_memory_as_official_retrieve` | `lightmem_adapter.py:1555` |
| adapter LongMemEval prompt 分支 | `lightmem_adapter.py:1222-1223` |
| adapter `_retrieve_native` formatted_memory 取 answer_context | `lightmem_adapter.py:756-762` |

---

## SimpleMem

### 1. 通用产品接口与版本裁定

用通用产品 text backend `SimpleMemSystem`（`third_party/methods/SimpleMem/main.py` =
`simplemem/text/system.py`，diff 仅 1 空行），**零迁移**。

- 仓库顶层有多个"支柱/产品"（SimpleMem text / OmniSimpleMem 多模态 / EvolveMem 自演化 /
  cross 跨会话 / MCP server），但它们是**不同的方法/产品**，不是 SimpleMem text 核心算法
  的版本变体。SimpleMem text 核心算法只有一套。
- `test_locomo10.py` 是 LoCoMo 专用评测（自带数据+打分），**但 `from main import
  SimpleMemSystem`（test_locomo10.py:22）调通用引擎**——官方评测本身就绕开 `ask()` 直接调
  `hybrid_retriever.retrieve()` + `answer_generator.generate_answer()`。即 test_locomo10.py
  = 「通用引擎 + LoCoMo 数据加载 + 打分壳」，**不是独立 fork**（与 MemoryOS eval/ 根本
  区别）。adapter 完全没碰 `test_locomo10.py`/`test_ref/`/`EvolveMem/`/`OmniSimpleMem/`。
- `test_ref/test_advanced.py` 是夹带的 **A-Mem** 代码（`from memory_layer import
  AgenticMemorySystem`），与 SimpleMem 无关。

### 2. 注入 API

`SimpleMemSystem.add_dialogue(speaker: str, content: str, timestamp: Optional[str] = None)`
（`main.py:111`）。

- **粒度**：per-dialogue（turn）。每次调加一条 Dialogue 进 `memory_builder.dialogue_buffer`；
  buffer 达 `WINDOW_SIZE` 时自动触发 `process_window()`（LLM 压缩成 MemoryEntry → 存
  vector_store）。`finalize()`（`main.py:138`）处理残余 buffer（`process_remaining()`）。
  adapter `consume_granularity="turn"`，ingest（`simplemem_adapter.py:188`）逐 turn 调
  `system.add_dialogue(...)`（`:197`），`end_conversation` 调 `system.finalize()`（`:219`）。
- **官方参数**（`simplemem/core/settings.py:12-40`）：`WINDOW_SIZE=40`、`OVERLAP_SIZE=2`
  （step=window-overlap=38）、`SEMANTIC_TOP_K=25`、`KEYWORD_TOP_K=5`、`STRUCTURED_TOP_K=5`、
  `LLM_MODEL="gpt-4.1-mini"`、`EMBEDDING_MODEL="Qwen/Qwen3-Embedding-0.6B"`、
  `EMBEDDING_DIMENSION=1024`、`ENABLE_PARALLEL_PROCESSING=True`、`MAX_PARALLEL_WORKERS=16`。
  adapter `SimpleMemConfig` 完整覆盖并在 `_create_official_system` 逐项写入
  `simplemem_settings`。
- **是否触发 LLM**：**是**。`add_dialogue` 攒窗口，window 满 `process_window` 触发 LLM 压缩
  成 MemoryEntry（自包含事实句+keywords+timestamp+location+persons+entities+topic）。
  `finalize` 处理残余窗口。finalize 前进程中断会丢 buffer，retry 必须删 isolation 目录整段
  重放。

### 3. 检索 API

`HybridRetriever.retrieve(query: str, enable_reflection: Optional[bool] = None) ->
List[MemoryEntry]`（`simplemem/core/hybrid_retriever.py:58`）。

- **返回记忆层**：扁平 `List[MemoryEntry]`（三视图检索结果合并去重，可选 reflection 补充）。
  SimpleMem 只有**一种记忆单元 `MemoryEntry`** 存在**单个 LanceDB table**，无短/中/长多层。
  「三视图」（Semantic/Lexical/Symbolic）是同一 MemoryEntry 的三种检索索引方式，不是三个
  独立记忆层。
- **检索内部（`hybrid_retriever.py:75-127`）**：① `_analyze_information_requirements`
  （planning，LLM 分析信息需求）；② `_generate_targeted_queries`（生成 1-4 个目标查询）；
  ③ 三视图并行检索——Semantic（`_semantic_search` `:241`，向量相似度，top_k=SEMANTIC_TOP_K）、
  Lexical（`_keyword_search` `:248`，BM25 Tantivy FTS，top_k=KEYWORD_TOP_K）、Symbolic
  （`_structured_search` `:264`，metadata 过滤 persons/location/entities/timestamp_range，
  top_k=STRUCTURED_TOP_K）；④ `_merge_and_deduplicate_entries`（`:409`，按 entry_id 去重）；
  ⑤ 可选 reflection 轮（`MAX_REFLECTION_ROUNDS=2`）。
- **top_k**：三视图各自的 SEMANTIC/KEYWORD/STRUCTURED_TOP_K（25/5/5），合并去重后无统一
  top_k。
- **耦合评估**：`SimpleMemSystem.ask(question)`（`main.py:145`）把检索+答题串起来（`retrieve`
  + `generate_answer`），但 `hybrid_retriever` 是独立属性，`retrieve` 是独立方法返回纯
  `List[MemoryEntry]` 不调 answer LLM。**官方评测本身绕开 `ask()` 直接调
  `hybrid_retriever.retrieve()`**（test_locomo10.py:877-890），adapter 沿用此剥离方式
  （`simplemem_adapter.py:227` `system.hybrid_retriever.retrieve(...)`，注释 `:224` "绕开
  ask()"）。剥离干净，无需自造检索算法。

### 4. formatted_memory 拼装口径

adapter `retrieve`（`simplemem_adapter.py:223`）调 `hybrid_retriever.retrieve` 后：
`context_str = _format_simplemem_contexts(contexts)`（`:228`）+ `formatted_memory =
_format_simplemem_memory(contexts)`（`:229`）。

- **P0 修复后（commit 3e177c3）**：`_format_simplemem_memory`（`:467`）改为**复用**
  `_format_simplemem_contexts`（`:484`），覆盖 MemoryEntry **全部 6 字段**
  （Content=lossless_restatement / Time=timestamp / Location / Persons / Related Entities /
  Topic），逐行复刻官方 `AnswerGenerator._format_contexts`
  （`simplemem/core/answer_generator.py:85`）。**不再只取 2/6 字段**，unified 口径下不丢
  Symbolic 层（location/persons/entities/topic）。官方 `_format_contexts` 不含 keywords
  （Lexical 层不进 answer context），adapter 与官方一致。
- 覆盖记忆层：**单一 MemoryEntry 列表**全字段（三视图命中合并去重）。unified 与 native
  口径看到一致的记忆——只有"记忆质量"在变，不因口径不同漏字段。

### 5. 证据行号

| 事实 | 证据 |
| --- | --- |
| `SimpleMemSystem` 类（= text backend） | `main.py:16` |
| `add_dialogue` 签名 | `main.py:111` |
| `finalize` | `main.py:138` |
| `ask`（retrieve+generate_answer 耦合，adapter 绕开） | `main.py:145` |
| 官方评测绕开 ask 直接调 hybrid_retriever | `test_locomo10.py:877-890` |
| 官方评测 `from main import SimpleMemSystem` | `test_locomo10.py:22` |
| `HybridRetriever.retrieve` 签名 | `simplemem/core/hybrid_retriever.py:58` |
| 三视图 `_semantic_search`/`_keyword_search`/`_structured_search` | `hybrid_retriever.py:241,248,264` |
| `_merge_and_deduplicate_entries` | `hybrid_retriever.py:409` |
| 官方 `_format_contexts`（6 字段） | `simplemem/core/answer_generator.py:85` |
| 官方默认参数（WINDOW_SIZE=40 等） | `simplemem/core/settings.py:12-40` |
| adapter ingest | `simplemem_adapter.py:188` |
| adapter `add_dialogue` 调用 | `simplemem_adapter.py:197` |
| adapter `finalize` 调用 | `simplemem_adapter.py:219` |
| adapter retrieve（绕开 ask） | `simplemem_adapter.py:223` |
| adapter `hybrid_retriever.retrieve` 调用 | `simplemem_adapter.py:227` |
| adapter `_format_simplemem_memory`（P0 后复用 6 字段） | `simplemem_adapter.py:467` |
| adapter `_format_simplemem_contexts`（复刻官方） | `simplemem_adapter.py:484` |
| adapter `_build_simplemem_answer_prompt` | `simplemem_adapter.py:512` |

---

## HaluMem operation-level 接入状态

HaluMem 在 ws02.2 采用 full operation-level runner，不是普通 conversation-QA
runner。runner 对每个 user 按 session 顺序执行：

```text
ingest(session) -> end_session(extraction report) -> update probes -> QA
```

当前实现状态（2026-07-08）：

- benchmark adapter 已支持 Medium / Long variant、每 user 前 M 个完整 session 的
  smoke 裁剪，CLI 使用 HaluMem 专用 `--sessions`，最小 smoke 为 `--sessions 1`。
- operation-level runner 写公开 input/output artifacts，并新增
  `evaluator_private_session_labels.jsonl` 承载 session 级 gold memory_points +
  dialogue；gold 不进入 method 或 provider report metadata。
- 三个 evaluator 已注册：`halumem-extraction`、`halumem-update`、`halumem-qa`。
  extraction/update 读 session 私有 artifact，QA 读 question 私有 labels。
- Mem0 在 HaluMem 下声明 `consume_granularity=session` 和
  `session_memory_report=True`，可产出 session 增量 extraction report。
- SimpleMem、MemoryOS、A-Mem、LightMem 不提供干净 session 增量 extraction report；
  HaluMem extraction 对这些 method 记 N/A，update + QA 仍按 v3 retrieve 路径运行。
- fake registered 全链路已通过，真实 API smoke 仍需用户确认预算、规模和 run_id。

## Resume 策略分层

该分层吸收 `docs/archive/opencode-suggestions/method-resume-feasibility-analysis.md` 中经源码核验后
可采纳的部分。原则是只在 method 的最小写入单元"完成即持久化"时使用 turn 级 resume；
否则退回 conversation 级，避免 checkpoint 记录的进度和 method 实际持久化状态不一致。

| Method | 当前 resume 级别 | 依据 | 后续任务 |
| --- | --- | --- | --- |
| Mem0 | conversation 级 | 用户 2026-06-19/20 已决定暂时抛弃 turn-level resume；LoCoMo 虽然内部仍按官方 `CHUNK_SIZE=1` 调用，但 runner 不再暴露 turn checkpoint | 不做 turn 级 resume；LoCoMo / LongMemEval 均使用 conversation status |
| MemoryOS | conversation 级 | 官方 LoCoMo eval 以 dialogue page / QA pair 写入，状态落到独立 JSON 目录；当前 adapter 通过 conversation state 目录恢复 | 后续并行时优先做进程隔离，不强行降到 turn 级 |
| A-Mem | conversation 级 | 官方 robust runtime 主要是内存 dict + retriever；当前 wrapper 在 conversation 完成后保存 `memories.pkl`、官方 retriever cache/embeddings 和强校验 manifest | 不做 turn 级 resume；resume 时 registry 对 completed conversations 调 `load_existing_conversation_state()` |
| LightMem | conversation 级 | `add_memory()` 中间调用可能只进入 buffer，只有 force extraction/offline update 后才具备完整持久化语义；resume 时按同一 `storage_root+conversation_id` 重建 backend | 不做 turn 级 resume；LoCoMo `add()` 返回后已执行 offline update，可作为 conversation 完成点；registry 会对 completed conversations 调 `load_existing_conversation_state()` |
| SimpleMem | conversation 级 | `add_dialogue()` 先进入内存 buffer，完整窗口或 `finalize()` 后才写入 LanceDB；finalize 前中断无法从 LanceDB 恢复残余 buffer | 不做 turn 级 resume；failed_ingest clean retry 删除对应 isolation 目录后整段重放 |

question 级 resume 当前由 runner 统一基于 `method_predictions.jsonl` 处理。retrieve-first
迁移后应拆为 retrieval artifact 和 answer artifact：retrieve completed / answer pending
时，resume 应复用已保存的 retrieval result。

## 四个 method 的当前 resume 状态

| Method | 写入记忆 resume | 问问题 resume |
| --- | --- | --- |
| Mem0 | LoCoMo / LongMemEval 均为 conversation-level | 统一基于 `method_predictions.jsonl`、`conversation_status.json` 和 question status；历史 turn-level resume 已禁用 |
| MemoryOS | conversation-level；恢复已有 JSON state 目录 | 统一基于 `method_predictions.jsonl` 和 question status |
| A-Mem | conversation-level；恢复 `memories.pkl`、retriever cache/embeddings 和 manifest | 统一基于 `method_predictions.jsonl` 和 question status |
| LightMem | conversation-level；按同一状态目录重建 LightMemory backend | 统一基于 `method_predictions.jsonl` 和 question status |
| SimpleMem | conversation-level；finalize 前失败通过 clean retry 删除 isolation LanceDB 后整段重放 | 统一基于 `method_predictions.jsonl` 和 question status |
