---
audit: Mem0
workstream: ws02.5
auditor: actor（GLM-5.2，只读审计）
date: 2026-07-08
mode: 只读审计（不碰 src/ tests/ third_party/，仅产出本文件）
status: 完成
---

# Mem0 接口保真审计报告

> 本报告逐条回答任务卡五问。证据一律一手源：`third_party/methods/mem0-main/`
> 仓库代码 + README + 我们的 adapter 行号。adapter 真实文件名为
> `src/memory_benchmark/methods/mem0_adapter.py`（非 `Mem0_adapter.py`）。

## 结论速览

| 维度 | 结论 | 一句话 |
| --- | --- | --- |
| 接口保真 (a) | ✅ 合规 | adapter 调通用产品 `Memory` 类（进程内 `from_config`），非 Cloud API、非 evaluation/ 副本、非 HTTP server |
| 注入保真 (b) | ✅ 合规 | `Memory.add(messages, run_id=, infer=True, prompt=)` 逐 turn/pair 注入，run_id 做 conversation 隔离，触发 V3 ADD-only 提取 |
| 检索完整 (c) | ✅ 完整 | `Memory.search` → `_search_vector_store` 三信号融合（semantic+BM25+entity boost）全启用；Mem0 本就单一记忆层，无短/中/长期分层，无漏层 |
| 无 retrieve 耦合 (d) | ✅ 天然分离 | `Memory` 类**无** answer/get_response 方法；search 是纯检索返回记忆列表，答题由 adapter 拼 prompt + framework LLM 完成。与 MemoryOS（get_response 耦合）根本不同，**无需剥离** |
| 迁移成本 | ✅ 零迁移 | adapter 已在用通用产品接口，无算法 fork、无专用引擎要换。唯一可议项是 answer prompt 来源（见发现点 F1） |

## Q1 仓库版本/目录 + benchmark 专用目录

`third_party/methods/mem0-main/`（upstream `mem0ai/mem0`，MANIFEST.md:8）顶层有三类
代码，**第一手对比**如下：

### 1. 通用产品 Python 包 `mem0/`（`pip install mem0ai` 得到的那套）

- `mem0/__init__.py:9` 导出 `from mem0.memory.main import Memory` —— 这就是通用产品入口。
- 核心算法在 `mem0/memory/main.py`（137KB）：`Memory.add`（main.py:573）、
  `Memory.search`（main.py:1126）、V3 PHASED BATCH PIPELINE（main.py:699）、
  `_search_vector_store` 三信号融合（main.py:1343）。
- README.md:201-223 的 Basic Usage 正是用它：`from mem0 import Memory; memory = Memory();
  memory.search(...); memory.add(messages, user_id=...)`。

### 2. 老论文评测 `evaluation/`（arXiv 2504.19413，**benchmark 专用**）

- `evaluation/README.md:6` 自述"code and dataset for our paper"。
- 自带 LoCoMo 数据集（`dataset/locomo10.json`，README:29-31）、自有 answer prompt
  （`prompts.py` 的 `ANSWER_PROMPT`/`ANSWER_PROMPT_GRAPH`，被 search.py:10 引用）、
  自有打分（`evals.py` BLEU+F1+LLM judge）。
- **关键：`evaluation/src/memzero/` 不是算法 fork，而是调 Mem0 Cloud API 的客户端**。
  - `add.py:10` `from mem0 import MemoryClient`（注意是 `MemoryClient` 不是 `Memory`）。
  - `add.py:47-51` `MemoryClient(api_key=MEM0_API_KEY, org_id=, project_id=)` ——
    这是 **Mem0 Cloud 平台 HTTP 客户端**，算法在云端服务端。
  - `add.py:70` `self.mem0_client.add(message, user_id=, version="v2", ...)` ——
    用的是云端 **v2** 算法。
  - `search.py:13,20-24` 同样 `MemoryClient`，`search.py:44-55` 调
    `mem0_client.search(query, user_id=, top_k=, filter_memories=, enable_graph=)`。
- 结论：`evaluation/` 的 Mem0 部分不含本地算法，它把算法外包给 Mem0 Cloud
  （v2）。与 `mem0/` 包（v3 本地算法）是**版本差异 + 部署差异**，非 fork 关系。
  老 README 命令 `make run-mem0-add` 走的是 Cloud API。

### 3. 新评测套件 `memory-benchmarks/`（2026 April "New Memory Algorithm v3"，**独立仓库**）

- `memory-benchmarks/README.md:1-3` 明示是独立项目
  `mem0ai/memory-benchmarks`（`git clone` 而来），支持 LoCoMo / LongMemEval / BEAM。
- **走 HTTP，不直接调 Python 库**：
  `benchmarks/common/mem0_client.py:5-17` 的 `Mem0Client` 有 oss/cloud 两个后端，
  oss 默认连 `http://localhost:8888`（mem0_client.py:72），cloud 连
  `api.mem0.ai`（:70）。Ingest→Search→Evaluate 三阶段（README:91-99）。
- 即：memory-benchmarks 把 Mem0 当**服务**调（起 docker server / 调 cloud），
  算法本体仍是 `mem0/` 包，但经 HTTP 暴露。

### 多版本算法一致性

| 变体 | 算法来源 | 部署 | 版本 |
| --- | --- | --- | --- |
| `mem0/` 包 | 本地 main.py V3 pipeline | 进程内 | v3（ADD-only + entity linking + multi-signal） |
| `evaluation/` | Cloud 服务端 | HTTP API | v2（老论文，2025-04） |
| `memory-benchmarks/` | 经 OSS server 调 `mem0/` 包 | HTTP | v3（与 `mem0/` 同算法） |

**核心算法只有一份本地实现**（`mem0/memory/main.py` 的 V3）。`evaluation/` 用的是
云端 v2（老算法，README:45-63 说 v3 是 2026-04 才上的 +20~+27 分升级）；
`memory-benchmarks/` 与 `mem0/` 同算法、不同部署方式。

## Q2 adapter 调的是通用产品接口还是 benchmark 专用实现

**调的是通用产品接口**（`mem0/` 包的 `Memory` 类），进程内调用。证据链：

1. `_create_memory_backend`（adapter:1069-1102）：
   - adapter:1073-1078 把 vendored `mem0-main/` 根目录插进 `sys.path`。
   - adapter:1081 `mem0_module = importlib.import_module("mem0")` —— 导入通用产品包。
   - adapter:1087-1091 校验导入的模块确实来自 vendored 源（防误装 pip 版）。
   - adapter:1098 `return mem0_module.Memory.from_config(backend_config)` —— 用通用
     产品 `Memory` 类的官方工厂方法 `from_config`（main.py:535）构造。
2. `build_backend_config`（adapter:372-401）只配 `llm`/`embedder`/`vector_store`
   (qdrant)/`history_db_path`，是 `Memory.from_config` 的标准入参，**不含** Cloud
   API key、**不含** `graph_store`、**不连** evaluation/ 或 memory-benchmarks/。
3. 注入调用：adapter:483-489 / 506-515 / 546 / 773 / 827 全是
   `self._memory.add([...], run_id=, metadata=, infer=, prompt=)` —— 即
   `Memory.add`（main.py:573），不是 `MemoryClient.add`。
4. 检索调用：adapter:876-886 / 956-966 全是
   `self._memory.search(text, filters={"run_id": ...}, top_k=)` —— 即
   `Memory.search`（main.py:1126），不是 `MemoryClient.search`。

**结论：adapter 完全合规于 ws02.5 裁决**（一律用通用产品接口），与 MemoryOS
adapter 包 eval/ 专用引擎的情况**根本不同**——Mem0 这边无需迁移。

## Q3 原生注入/检索接口 + 耦合评估

### 注入接口 `Memory.add`（main.py:573-584）

```python
def add(self, messages, *, user_id=None, agent_id=None, run_id=None,
        metadata=None, infer=True, memory_type=None, prompt=None)
```

- **签名**：`messages` 为 str / dict / list[dict]（调用方决定粒度）；隔离用
  `user_id`/`agent_id`/`run_id` 三选一（main.py:1193 强制至少一个）。
- **粒度**：Mem0 不强制粒度，由调用方传 messages 长度决定。adapter 的
  `ingest_granularity`：LoCoMo 用 turn 级（`ingestion_chunk_size=1`，
  `_ingest_native_turn` adapter:472-489），LongMemEval 用 pair 级
  （`_ingest_native_pair` adapter:491-515，保持官方两 turn 批次）。
- **官方参数**：`infer=True` 触发 V3 LLM 提取（main.py:699 PHASED BATCH PIPELINE：
  context→existing retrieval→ADDITIVE_EXTRACTION_PROMPT 单次提取→batch embed→
  hash dedup→entity link）；`infer=False` 直接存 raw。`prompt` 是自定义提取 prompt
  （注入 `self.custom_instructions`，main.py:729）。adapter 用
  `infer=self.config.infer`（默认 True）+ `prompt=self._observation_time_prompt(...)`
  注入时间感知（adapter:488），符合官方用法。
- **返回**：`{"results": [{"id","memory","event","..."}]}`（main.py:660）。
- **记忆构建/更新流程**：V3 是 single-pass ADD-only（README:57，无 UPDATE/DELETE，
  记忆累积不覆盖）+ entity linking（`_upsert_entity` main.py:413-448，写入
  `entity_store` 的 `linked_memory_ids`）。

### 检索接口 `Memory.search`（main.py:1126-1135）

```python
def search(self, query, *, top_k=20, filters=None, threshold=0.1, rerank=False, **kwargs)
```

- **签名**：`query` 字符串；`filters` 必含 user_id/agent_id/run_id 之一
  （main.py:1193-1197）；返回 `{"results": [{"id","memory","score",...}]}`（main.py:1237）。
- **返回的记忆层**：**只有一层** —— vector store 里的 extracted memories
  （`MemoryItem{id,memory,hash,created_at,updated_at,score}`，main.py:1417-1424）。
  Mem0 **没有** MemoryOS 那种短/中/长期分层；"Multi-Level Memory"（README:78）指的是
  user/session/agent 三个**隔离维度**（靠 user_id/agent_id/run_id），不是记忆层级。
- **top_k**：官方默认 20（main.py:1130）；memory-benchmarks 官方评测默认 200
  （memory-benchmarks/README.md:113）；adapter 用 `top_k=200`（adapter:157,175），
  与官方评测口径一致。
- **检索内部（`_search_vector_store` main.py:1343-1438）三信号融合**：
  1. Semantic：vector_store.search，over-fetch `max(limit*4, 60)`（main.py:1356-1359）
  2. BM25 keyword：vector_store.keyword_search + normalize_bm25（main.py:1362-1374）
  3. Entity boost：`_compute_entity_boosts`（main.py:1440-1499），从 `entity_store`
     查 query 实体（threshold≥0.5，main.py:1478），按 `linked_memory_ids` 加权
     （spread-attenuated，main.py:1488）。
  4. `score_and_rank` 融合三信号取 top_k（main.py:1392-1398）。

### 耦合评估：原生 retrieve 与答题**无耦合**

- `Memory` 类**没有** `answer`/`get_response`/`generate` 方法（grep 整个 main.py 的
  公开方法只有 add/search/get_all/get_all/update/delete/reset 等，main.py:573/1126/
  1016/1501/1524）。search 是**纯检索**，返回记忆列表，**不生成答案**。
- README.md:208-223 的 Basic Usage 印证：调用方自己 `memory.search` → 自己拼
  system_prompt → 自己调 `openai_client.chat.completions.create`。检索与答题在
  Mem0 设计上就是分离的。
- **与 MemoryOS 根本不同**：MemoryOS `get_response` 把检索+答题耦合在一个方法里
  （需"忠实剥离 formatted_memory"），而 Mem0 的 `search` 直接返回记忆，adapter 拿来
  拼 prompt 即可——**天然已剥离，无需克服**。
- adapter 实现印证：retrieve（adapter:846-1010）调 `self._memory.search` 拿
  `memories` → `_memory_context_text` 拼 `formatted_memory`（adapter:968,980-982,
  1638+）→ `_reader_messages` 拼答题 prompt（adapter:969,985）交给 framework answer
  LLM。检索与答题在 adapter 层也是分离的。

## Q4 formatted_memory 是否覆盖全部记忆层

**覆盖完整**。理由：

1. **Mem0 是单一记忆层架构**。核心记忆 = vector store 里的 extracted memories
   （facts）。`entity_store` 是 entity linking 的**辅助索引**（存 entity→
   linked_memory_ids，main.py:442-448），用于 search 阶段的 retrieval boosting
   （main.py:1476-1494），**不作为独立记忆层返回**——`search` 返回的 results
   只含 vector memories（main.py:1410-1438），entity 的贡献已折进每条 memory 的
   `score`。
2. **adapter 的 search 走的就是 `_search_vector_store`**（adapter 调 `Memory.search`
   → main.py:1227 `self._search_vector_store`），三信号（semantic+BM25+entity boost）
   **全部自动启用**，adapter 无需额外配置即可获得 entity boosting。
3. **entity_store 默认启用**：它是懒加载（main.py:358 `_entity_store=None`，
   main.py:390-411 property 首次访问即创建），复用 vector_store 的 qdrant provider
   （main.py:408-410），collection 名加 `_entities` 后缀（main.py:394）。adapter 还
   **主动预热**（`_prewarm_entity_store` adapter:1104-1108），确保 worker 并发前
   entity_store 就绪。→ entity linking 这条"记忆层"adapter 完整覆盖。
4. **formatted_memory 拼装**（adapter:980-982, 1638+）：`_memory_context_text` 把
   `search` 返回的全部 memories 拼成文本；空则回退 `"(No relevant memories found)"`
   （adapter:981）。RetrievalResult.items（adapter:986-994）逐条带
   content/score/timestamp，完整落盘。

### 关于 graph relations（Mem0+）

- Mem0 有 vector-only（Mem0）和 vector+graph（Mem0+）两变体。`evaluation/` 的
  `is_graph=True` 路径（search.py:42-51,84-87）会返回额外的 `relations`
  （source/relationship/target）——但那是 **Cloud API 的 `enable_graph=True`** 行为。
- 本地 `Memory` 类的 `search`（main.py:1126）**没有 `enable_graph` 参数**，返回值
  也只有 `{"results": [...]}`，**不返回 graph relations**。本地 graph 需配
  `graph_store`（adapter 的 `build_backend_config` 未配，adapter:372-401）。
- **判定：不算漏层**。① memory-benchmarks 官方 OSS 默认配置就是 vector + entity，
  不含 graph（memory-benchmarks/README.md 的 OSS 路径走 server，server 默认
  `gpt-4o-mini` 抽取 + `text-embedding-3-small` 向量，未提 graph）；② Mem0+ graph
  是可选增强，不是 v3 核心算法必需层（README:60 的 multi-signal 是
  semantic+BM25+entity，不含 graph）；③ 即使想用 graph，本地 `Memory.search` 也不
  返回 relations，需走 Cloud API，与"通用产品本地接口"裁决冲突。若架构师后续要
  纳入 Mem0+ graph，是**新增能力**而非"补漏层"。

## Q5 建议：版本/接口/迁移成本

### 建议：维持现状（零迁移）

- **版本**：继续用 vendored `mem0/` 包（通用产品，V3 算法）。不要切到
  `evaluation/`（Cloud v2 老算法）也不要切到 `memory-benchmarks/`（HTTP 服务层，
  非进程内库）。
- **接口**：继续用 `Memory.from_config` + `add` + `search` 进程内调用。这与
  ws02.5 裁决、与"每 conversation 物理隔离存储（删目录即 clean-retry）"的项目
  惯例一致，无需起 HTTP server。
- **迁移成本：零**。adapter 已在用通用产品接口，无算法 fork 要重写、无专用引擎
  要换指向。这是 Mem0 相对 MemoryOS 的**省事之处**——MemoryOS adapter 要从 eval/
  迁到 pypi，Mem0 这边一开始就对了。
- **配置对齐核对（已对齐，无需动）**：
  - `top_k=200`（adapter:157,175）= memory-benchmarks 官方默认（README:113）✓
  - `infer=True`（adapter:160,178）= 触发 V3 LLM 提取 ✓
  - `extraction_model=gpt-4o-mini` / `embedding=text-embedding-3-small`
    （adapter:153-154,171-172）= memory-benchmarks OSS 默认（README:77,123）✓
  - `ingestion_chunk_size=1`（逐 turn）= LoCoMo 官方粒度；LongMemEval 用 pair
    级（adapter:491-515）= 官方两 turn 批次 ✓
  - entity_store 懒加载默认启用 + adapter 预热 ✓

## 发现点（plan 之外，只报告不处置）

### F1 answer prompt 来自 memory-benchmarks 评测套件（待架构师裁定 prompt 归属）

- adapter 的 answer prompt **复用 `memory-benchmarks/benchmarks/{locomo,longmemeval}/prompts.py`
  的 `get_answer_generation_prompt`**：
  - adapter:1595-1598 `_build_mem0_locomo_prompt` →
    `_load_mem0_benchmark_prompt_module(path_settings, "locomo")` →
    `prompt_module.get_answer_generation_prompt(...)`。
  - adapter:1626-1629 `_build_mem0_longmemeval_prompt` 同理。
  - adapter:69 `MEM0_READER_PROMPT_VERSION = "mem0-memory-benchmarks-reader-v2"` 印证。
- **这超出 ws02.5（接口保真：注入/检索用通用产品还是专用）范围**，属于 AGENTS.md
  的 prompt 来源政策。记忆注入/检索用的是通用产品 `Memory.add/search`（合规），
  但 answer prompt 用的是 Mem0 **官方评测套件**的 prompt，而非框架 unified 的
  per-benchmark prompt。
- **潜在冲突**：AGENTS.md 运行主线③要求"框架自带 answer prompt（unified 口径）"，
  红线要求"answer/judge prompt per-benchmark、method 无关"。若其他 method（如
  A-Mem）在 LoCoMo 上用不同 prompt，则 Mem0 与之 answer prompt 不一致，违反红线。
- **但**：memory-benchmarks 的 prompt 是 Mem0 官方跑该 benchmark 的 prompt，也可
  视"benchmark 官方仓库有就先用"（AGENTS.md prompt 政策）的合规来源——取决于把它
  归类为"benchmark 官方 prompt"还是"method 专属 prompt"。**交架构师裁定**：是把
  memory-benchmarks 的 LoCoMo/LongMemEval prompt 收为框架 unified prompt（所有
  method 共用），还是另起框架自研 per-benchmark prompt。本审计不动手。

### F2 `_prewarm_entity_store` 暗示 vendored Mem0 2.0.4 的懒加载有线程安全隐患

- adapter:1104-1108 注释明示"vendored Mem0 2.0.4 的 `entity_store` 属性采用无锁
  懒加载"，故 adapter 在 worker 并发前单线程预热。这是 adapter 对第三方缺陷的
  **合理规避**，非 adapter bug。若将来升级 vendored Mem0 版本，需复核该隐患是否
  已被上游修复。只记录，不处置。

## 证据索引（行号速查）

| 事实 | 证据 |
| --- | --- |
| 通用产品入口 | `mem0/__init__.py:9` `from mem0.memory.main import Memory` |
| `Memory.add` 签名 | `mem0/memory/main.py:573-584` |
| V3 提取 pipeline | `mem0/memory/main.py:699-818`（ADD-only + entity link） |
| `Memory.search` 签名 | `mem0/memory/main.py:1126-1135` |
| search 三信号融合 | `mem0/memory/main.py:1343-1438`（semantic+BM25+entity） |
| entity_store 懒加载 | `mem0/memory/main.py:358,390-411` |
| entity boosting | `mem0/memory/main.py:1440-1499` |
| evaluation 调 Cloud API | `evaluation/src/memzero/add.py:10,47-51,70`；`search.py:13,20-24,44-55` |
| memory-benchmarks 走 HTTP | `memory-benchmarks/benchmarks/common/mem0_client.py:5-17,70-72` |
| adapter 导入通用 Memory | `mem0_adapter.py:1081,1098` |
| adapter add 调用 | `mem0_adapter.py:483-489,506-515,546,773,827` |
| adapter search 调用 | `mem0_adapter.py:876-886,956-966` |
| formatted_memory 拼装 | `mem0_adapter.py:968,980-982,1638+` |
| build_backend_config | `mem0_adapter.py:372-401`（无 graph_store） |
| 默认 top_k=200 | `mem0_adapter.py:157,175` |
| entity_store 预热 | `mem0_adapter.py:1104-1108` |
| answer prompt 来源 | `mem0_adapter.py:69,1595-1598,1626-1629` |
