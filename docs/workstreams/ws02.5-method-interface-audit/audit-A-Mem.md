---
audit: A-Mem
workstream: ws02.5
auditor: actor（GLM-5.2，只读审计）
date: 2026-07-08
mode: 只读审计（不碰 src/ tests/ third_party/，仅产出本文件）
status: 完成
---

# A-Mem 接口保真审计报告

> 本报告逐条回答任务卡五问。证据一律一手源：`third_party/methods/A-mem/`
> 仓库代码 + README + A-mem-sys 官方仓库 README（交叉验证）+ 我们的 adapter
> 行号。adapter 真实文件名为 `src/memory_benchmark/methods/amem_adapter.py`
> （无连字符，与任务卡假设一致）。

## 结论速览

| 维度 | 结论 | 一句话 |
| --- | --- | --- |
| 接口保真 (a) | ⚠️ 需架构师裁定 | adapter 调的是 vendored 实验复现包引擎 `RobustAgenticMemorySystem`（记忆引擎本身 benchmark 无关），**不是**官方产品库 A-mem-sys 的 `AgenticMemorySystem`。两库 API/存储/检索形态不同。但 adapter 没碰任何 LoCoMo 专用评测代码 |
| 注入保真 (b) | ✅ 合规 | `add_note(content, time, **kwargs)` 逐 turn 注入，格式忠于官方 test_advanced_robust.py，触发 analyze→process_memory 演化→retriever 索引全流程 |
| 检索完整 (c) | ✅ 完整 | `find_related_memories_raw(query, k)` 返回含 **主 memory（timestamp+content+context+keywords+tags）+ links 邻域 memory** 的 str。A-Mem 单层 note，note+link 核心全覆盖，无漏层 |
| 无 retrieve 耦合 (d) | ✅ 天然分离 | `find_related_memories_raw` 是独立纯检索 API，返回 str 不调答题 LLM。retrieve 与 answer 在 adapter 也分离。与 MemoryOS（get_response 耦合）根本不同，**无需剥离** |
| 迁移成本 | 中-高（仅当架构师要求迁 A-mem-sys） | 若维持现状=零迁移；若迁官方产品库 A-mem-sys=换引擎（list[dict] vs str）+ 引入 ChromaDB + 重写 formatted_memory 拼装 + 核验 search_agentic 是否保 link 邻域。非"同引擎改配置" |

> **核心裁决请求**：vendored `RobustAgenticMemorySystem` 来自论文作者官方复现仓库
> `WujiangXu/AgenticMemory`（README:3-5 自述"specifically designed to reproduce the
> results presented in our paper"），其记忆引擎 benchmark 无关、retrieve 独立、
> formatted_memory 完整。是否可视同 ws02.5 裁决所言"通用产品接口"？与 MemoryOS
> 情形不同（MemoryOS 同仓库内有 pypi 产品 vs eval 专用两套副本），A-Mem 的官方
> 产品库在**另一个仓库** `WujiangXu/A-mem-sys`（`pip install`）。详见 Q2/Q5。

---

## Q1 仓库版本/目录 + benchmark 专用评测 + 多版本算法一致性

`third_party/methods/A-mem/`（upstream `WujiangXu/AgenticMemory`）是**单一扁平
仓库**，不像 MemoryOS 那样分 `memoryos-pypi/`/`eval/`/`memoryos-chromadb/`/`memoryos-mcp/`
多个版本子目录。顶层结构（`find . -maxdepth 2`）：

```
A-mem/
├── README.md              # 第一手说明（见下）
├── memory_layer.py        # 41KB，standard 引擎：AgenticMemorySystem / MemoryNote（JSON schema 依赖）
├── memory_layer_robust.py # 22KB，robust 引擎：RobustAgenticMemorySystem / RobustMemoryNote（纯文本+解析+retry）
├── llm_text_parsers.py    # 18KB，robust 版的 prompt 常量 + 解析函数
├── load_dataset.py        #  9KB，LoCoMo 专用数据加载（LoCoMoSample/EventSummary/Observation）
├── test_advanced.py       # 19KB，original 评测脚本（需 JSON schema）
├── test_advanced_robust.py# 15KB，robust 评测脚本（推荐，openai/vllm/ollama）
├── utils.py               #  8KB，calculate_metrics / aggregate_metrics（LoCoMo 打分）
├── run_all_experiments.sh #  7 模型跑 LoCoMo
├── run_k_sweep.sh         # k 超参扫描
├── data/locomo10.json     # ⚠️ 自带 LoCoMo 10 样本子集
├── Figure/                # 论文图
└── A-mem.pdf              # 论文 PDF
```

### README 第一手定性（关键）

`README.md:3-5` 原文：

> **Note:** This repository is specifically designed to reproduce the results
> presented in our paper. If you want to use the A-Mem system in building your
> agents, please refer to our official implementation at:
> [A-mem-sys](https://github.com/WujiangXu/A-mem-sys)

即：**本仓库自述是"论文复现实验包"**，官方产品实现在另一个仓库 `A-mem-sys`。
`README.md:82-109` 的运行方式就是 `python test_advanced[_robust].py --dataset
data/locomo10.json`，整套设施围绕 LoCoMo 跑分。

### 有没有 benchmark 专用评测目录？

**没有独立子目录**，但整个仓库自带 LoCoMo 跑分设施（散落在顶层）：

- `data/locomo10.json`：LoCoMo 10 样本（私有数据，adapter 不碰）。
- `load_dataset.py:41-57`：`EventSummary`/`Observation`/`LoCoMoSample` 是 **LoCoMo
  专用数据结构**；`parse_session`/`parse_conversation` 全 LoCoMo schema。
- `test_advanced_robust.py:109-153`：`answer_question` 含 **LoCoMo per-category
  answer prompt**（category 2 用 date prompt、category 5 用 adversarial 二选一、
  其余 short phrase）。
- `utils.py`：BLEU/F1/ROUGE 等 LoCoMo 打分。
- `run_all_experiments.sh:18,91`：`DATASET="data/locomo10.json"`，调
  `test_advanced_robust.py`。

**但关键**：这些 LoCoMo 专用件**只服务于数据加载+QA+打分**，与 A-Mem 的**记忆
引擎**（`memory_layer*.py` + `llm_text_parsers.py`）解耦。记忆引擎是 benchmark
无关的通用算法（见下"prompt 无关性"）。

### 两版 memory layer 核心算法一致性（diff）

`memory_layer_robust.py:1-11` docstring 自述"drop-in replacement for
memory_layer.py"，且 `memory_layer_robust.py:24` 直接
`from memory_layer import SimpleEmbeddingRetriever, simple_tokenize`——**robust
不是独立 fork，建立在 standard 之上**，只替换 LLM 调用层。

逐项 diff（行号 = 各自文件）：

| 维度 | standard `memory_layer.py` | robust `memory_layer_robust.py` | 一致性 |
| --- | --- | --- | --- |
| `add_note` 签名 | `add_note(content, time=None, **kwargs)->str` (714) | `add_note(content, time=None, **kwargs)->str` (377) | ✅ 一致 |
| `add_note` 算法 | note→process_memory→存memories→retriever.add_documents(content+context+keywords+tags)→evo阈值consolidate (714-727) | 完全相同 (377-397) | ✅ 一致 |
| `process_memory` | find_related_memories(k=5)→**1 次** LLM call(evolution_system_prompt+JSON schema)→解析 JSON→strengthen/update (753-857) | find_related_memories(k=5)→**3 次顺序** plain-text LLM call(evolution decision/strengthen/update，条件跳过)→解析 (463-540) | ✅ 算法等价，LLM 调用粒度不同 |
| `find_related_memories` | 返回 `(memory_str, indices)`，字段 timestamp/content/context/keywords/tags (859-875) | 返回 `(memory_str, indices)`，字段相同 (411-428) | ✅ 一致 |
| `find_related_memories_raw` | 返回 str，主memory+links邻域，字段同上 (877-898) | 返回 str，主memory+links邻域，字段相同 (430-459) | ✅ 一致 |
| `MemoryNote` 字段集 | content/id/keywords/links/importance_score/retrieval_count/timestamp/last_accessed/context/evolution_history/category/tags (261-305) | 完全相同 (273-315) | ✅ 一致 |
| 检索器 | `SimpleEmbeddingRetriever` (554-665，numpy 余弦相似度) | **复用 standard 的**（import，:367） | ✅ 完全复用 |
| LLM controller | `LLMController`（4 backend，`get_completion`带 `response_format` JSON schema） | `RobustLLMController`（4 backend，`get_completion`纯文本+section-marker 解析+retry+降级+connectivity check） | ⚠️ 调用方式不同 |
| analyze_content prompt | 内联 JSON-schema prompt (308-401) | 抽到 `llm_text_parsers.py` 的 `ANALYZE_CONTENT_PROMPT` (llm_text_parsers.py:128) | ✅ 语义等价 |

**结论：两版算法一致**。robust 是 standard 的"工程鲁棒版"（去 JSON schema 依赖
→适配任意 backend；retry+降级→抗瞬态失败；结构化日志），**算法核心（note 构建→
演化→retriever 检索→links 邻域扩展）完全相同**。README:89 也推荐 robust
（"recommended, works with any LLM backend"）。

### 记忆引擎 prompt 的 benchmark 无关性（关键证据）

`llm_text_parsers.py` 5 个 prompt 常量全部为通用 A-Mem 算法 prompt，**无任何
LoCoMo 逻辑**：

- `ANALYZE_CONTENT_PROMPT` (llm_text_parsers.py:128-131)：通用 keywords/context/tags 抽取。
- `EVOLUTION_DECISION_PROMPT` (:143)：通用记忆演化决策。
- `STRENGTHEN_DETAILS_PROMPT` (:164)：通用 link 强化。
- `UPDATE_NEIGHBORS_PROMPT` (:180)：通用邻居 context/tags 更新。
- `FOCUSED_KEYWORDS_PROMPT` (:204)：通用关键词提取（空 keywords 时的 fallback）。

→ vendored 引擎的记忆构建/演化是 benchmark 无关的。LoCoMo 专用仅限
load_dataset/test_advanced_robust/utils，adapter 全没碰。

---

## Q2 adapter 调的是通用产品接口还是 benchmark 专用实现？

### adapter 真实文件名

`src/memory_benchmark/methods/amem_adapter.py`（无连字符，已用 `ls`+`grep` 确认，
src 下唯一含 amem/a-mem 的 adapter）。

### adapter 调的接口（行号证据）

adapter docstring（amem_adapter.py:1-5）自述"包装 `third_party/methods/A-mem/`
中的官方 robust memory layer……不重写 A-Mem 的记忆算法"。

- `import_amem_robust_classes()`（amem_adapter.py:191-226）：`importlib.import_module("memory_layer_robust")` (218)，导出 `RobustAgenticMemorySystem` + `RobustLLMController` (219-222)。
- `_create_official_runtime()`（amem_adapter.py:709-738）：构造
  `RobustAgenticMemorySystem(model_name=embedding, llm_backend="openai", llm_model=...,
  api_key=..., api_base=..., check_connection=False)` (725-732)。
- ingest → `_call_runtime_add()`（amem_adapter.py:834-841）→
  `runtime.add_note(content, time=timestamp)`，content=`f"Speaker {turn.speaker} says: {turn.content}"`。
- retrieve（amem_adapter.py:434-505）→ `_generate_query_keywords()` (456-465)
  + `runtime.find_related_memories_raw(query_keywords, k=retrieve_k)` (460/469)
  → `str(context)` (474)。

### 调的是通用产品接口还是 benchmark 专用实现？

**判断：adapter 调的是 vendored 实验包的通用记忆引擎（benchmark 无关），不是
LoCoMo 专用评测代码。** 但有一个**关键 caveat**：

README:3-5 明确本仓库是"论文复现实验包"，官方产品库在**另一个仓库**
`WujiangXu/A-mem-sys`（`pip install`）。WebFetch 该仓库 README 交叉确认，**产品
库 API 与我们 vendored 的实验包引擎不同**：

| 维度 | 产品库 `A-mem-sys`（pip install） | 实验包 `AgenticMemory`（我们 vendored） |
| --- | --- | --- |
| 入口 | `from agentic_memory.memory_system import AgenticMemorySystem` | `RobustAgenticMemorySystem`（sys.path import memory_layer_robust） |
| 注入 | `add_note(content, keywords=None, context=None, tags=None, timestamp=None)` | `add_note(content, time=None, **kwargs)`（time vs timestamp 命名差） |
| 检索 | `search(query, k)` / `search_agentic(query, k)` 返回 **list[dict]**（含 id/content/keywords/tags/score） | `find_related_memories_raw(query, k)` 返回 **str**（含主 memory+links 邻域文本拼接） |
| CRUD | `read(id)`/`update(id,...)`/`delete(id)` 齐全 | 仅 add + retrieve，无 read/update/delete |
| 存储后端 | **ChromaDB**（向量库） | **SimpleEmbeddingRetriever**（numpy 余弦相似度，无外部依赖） |
| 数据集 | 无 | 自带 `data/locomo10.json` |

→ 严格按 ws02.5"用通用产品接口"裁决，**adapter 现在用的不是产品库引擎，而是
实验复现包引擎**。这与 MemoryOS 情形**本质不同**：

- **MemoryOS**：同仓库内 pypi（产品）vs eval（LoCoMo 专用）两套代码副本，adapter
  包了 eval → 本 workstream 要迁 pypi。
- **A-Mem**：仓库内只有一套引擎（同时服务实验和通用使用），产品库在另一个仓库。
  adapter 用的引擎 benchmark 无关（见 Q1 prompt 无关性），但不是 `pip install` 得到的那套。

→ **此条交架构师裁定**：vendored 实验包引擎是否视同"通用产品接口"？（详见 Q5）

---

## Q3 原生注入/检索接口 + retrieve 是否耦合答题 + 能否剥离

### 注入接口

`RobustAgenticMemorySystem.add_note(content: str, time: str = None, **kwargs) -> str`
（memory_layer_robust.py:377-397）。

- **签名**：单条 turn 文本 + 可选 time + 可选预填元数据。
- **粒度**：单条 turn（adapter 按 turn 逐条调，amem_adapter.py:285/841）。无 batch。
- **官方参数**：`time`（注入时间戳，必传以保留 LoCoMo session 时间）；`**kwargs`
  可预填 keywords/context/tags（默认全由 LLM `analyze_content` 抽取）。
- **触发的内部流程**（memory_layer_robust.py:377-397）：
  1. `RobustMemoryNote(content, llm_controller, timestamp=time)` → `analyze_content()`
     （LLM 抽 keywords/context/tags，失败则 heuristic 降级，:317-345）。
  2. `process_memory(note)`（:463-540）：`find_related_memories(note.content, k=5)`
     找邻居 → 3 次顺序 LLM call（evolution decision / strengthen / update neighbors）
     → strengthen 时 `note.links.extend(strengthen["connections"])` 建链（:505）。
  3. 存 `self.memories[note.id]` + `retriever.add_documents(content+context+keywords+tags)`。
  4. 每 `evo_threshold`（默认 100）触发 `consolidate_memories()`（重建 retriever）。

### 检索接口

`find_related_memories_raw(query: str, k: int = 5) -> str`
（memory_layer_robust.py:430-459）。

- **签名**：query 文本 + k。
- **返回的记忆层**：A-Mem 是**单层 note 集合**（非多层）。返回拼好的 str，含：
  - 主 memory（每条）：`talk start time` + `memory content` + `memory context` +
    `memory keywords` + `memory tags`（:440-446）。
  - **links 邻域 memory**（每个 note 的 `note.links` 邻居，:447-458）：同字段，
    每个主 memory 最多扩展 k 个邻居（:456）。
- **top_k**：官方脚本默认 `k=10`（test_advanced_robust.py:348，README:112），但
  论文 Table 8 有 per-category k。adapter 用 `AMEM_GPT4O_MINI_CATEGORY_K`
  = {1:40, 2:40, 3:50, 4:50, 5:40}（amem_adapter.py:77-83，`_retrieve_k_for_question`
  :926-936）——比官方脚本固定 k=10 更细，取自论文调参，合理但比官方脚本激进。
  非 LoCoMo/无 category 时回退 profile 的 `retrieve_k`（:934-936）。

  另有 `find_related_memories(query, k=5) -> (str, indices)`（:411-428），供
  `process_memory` 内部找邻居用（不拼邻域，只返回主 memory 文本+索引）。

### retrieve 是否耦合答题？能否剥离？

**retrieve 与答题天然分离，无需剥离。**

- `find_related_memories_raw`（memory_layer_robust.py:430）是**独立纯检索 API**：
  返回 str，**不调答题 LLM**，不构造 answer prompt。
- 官方 QA 流程（test_advanced_robust.py:109-153 `answer_question`）：`generate_query_llm`
  → `retrieve_memory`（即 find_related_memories_raw）→ 拼用户 prompt →
  `llm.get_completion(user_prompt)`。检索与答题是**两步**。
- adapter 同构：`retrieve()`（amem_adapter.py:434）调 find_related_memories_raw 后
  **单独**构造 `answer_prompt`（:475-478）；`get_answer()`（:540-576）**单独**调
  reader LLM（`_call_answer_llm` :955-972）。
- adapter 还提供 v3 纯检索路径 `_retrieve_native()`（:507-538），返回
  `RetrievalResult(formatted_memory=..., prompt_messages=...)`，**不生成最终答案**，
  与官方 find_related_memories_raw 一致。

> 注：retrieve 内部先 `_generate_query_keywords()`（amem_adapter.py:896-924，LLM
> 把 question 改写为 keywords）再检索——这是 A-Mem 官方 robust QA 流程
> （test_advanced_robust.py:96-107,111-112 的 `generate_query_llm`→`retrieve_memory`），
> 属于检索的一部分（query 改写），**不是答题耦合**。keyword prompt 完全复刻官方
> （amem_adapter.py:909-914 vs test_advanced_robust.py:98-102，逐字一致）。

**与 MemoryOS 根本不同**：MemoryOS `get_response` 把检索+答题耦合在一个方法里，
"忠实抽出 formatted_memory"是难点；A-Mem 检索本就独立返回，**剥离零成本**。

---

## Q4 adapter retrieve 的 formatted_memory 是否覆盖 A-Mem 全部记忆层？

### A-Mem 的"记忆层"是什么

A-Mem 是**单层 note 集合**（非多层，不像 MemoryOS 短/中/长期）。每个
`RobustMemoryNote`（memory_layer_robust.py:273-315）字段：

`content` / `id` / `keywords` / `links` / `importance_score` / `retrieval_count` /
`timestamp` / `last_accessed` / `context` / `evolution_history` / `category` / `tags`。

A-Mem 算法的核心特性 = **note + link**（note 之间互相 link，检索时邻域扩展，
论文 Figure intro-b 的"interconnected knowledge networks"）。

### formatted_memory 覆盖核查

adapter `formatted_memory` = `str(runtime.find_related_memories_raw(query_keywords, k))`
（amem_adapter.py:460/469/474）。`find_related_memories_raw`（memory_layer_robust.py:430-459）
返回的 str 含：

- ✅ 主 memory：`timestamp` + `content` + `context` + `keywords` + `tags`（:440-446）
- ✅ links 邻域 memory：同 5 字段（:448-455，每个主 memory 最多 k 个邻居）

→ **note + link 核心全覆盖**，无漏层。

### 未进 formatted_memory 的字段（合理不漏）

- `importance_score` / `retrieval_count` / `last_accessed`：note 内部统计/访问
  计数，非"记忆内容"，不进检索文本合理。
- `evolution_history` / `category`：演化历史/分类标签，元数据性质，官方
  find_related_memories_raw 本就不拼（memory_layer_robust.py:440-455 与
  standard memory_layer.py:891-894 字段完全一致），adapter 与官方对齐。

**结论：formatted_memory 覆盖完整**，与官方 find_related_memories_raw 输出字段
逐字一致（adapter :474 `str(context)` 未做任何裁剪/重排）。

---

## Q5 建议：用哪个版本/接口 + 迁移成本

### 版本选择：robust（维持现状）

✅ **维持 robust**，理由：

1. README:89 明确推荐 robust（"recommended, works with any LLM backend"）。
2. standard 依赖 `response_format` JSON schema（memory_layer.py:339,759），限
   OpenAI 及少数支持严格 JSON 的 backend；robust 改纯文本+section-marker 解析
   +retry+降级（memory_layer_robust.py:1-11），适配任意 OpenAI-compatible backend，
   符合我们统一走 `gpt-4o-mini` 的口径。
3. 两版**算法等价**（Q1 diff 已证），换 robust 不损失算法保真度。

### 接口选择：三选一，交架构师裁定

**选项 A（维持现状，推荐）：vendored 实验包 `RobustAgenticMemorySystem`**
- 优点：① 记忆引擎 benchmark 无关（Q1 prompt 无关性已证）；② retrieve 独立、
  formatted_memory 覆盖 note+link 完整（Q3/Q4 已证）；③ 来自论文作者官方仓库，
  代表 A-Mem 在论文实验中的真实表现；④ SimpleEmbeddingRetriever 无外部依赖，
  每 conversation 一个目录 = 最简物理隔离（删目录即 clean-retry），与 MemoryOS
  pypi 裁定理由同构；⑤ adapter 已稳定，零迁移风险。
- 缺点：不是 `pip install` 得到的产品库；README:3-5 自述"复现实验包"。
- 裁定要点：实验包引擎是否视同 ws02.5"通用产品接口"？论据是"作者官方仓库 +
  benchmark 无关 + 算法忠于论文"，与 MemoryOS eval/（LoCoMo 专用引擎副本、
  自带数据+打分）性质不同——后者是 benchmark 专用，前者引擎通用。

**选项 B：迁官方产品库 `A-mem-sys`（拉进 third_party）**
- 优点：严格对标 ws02.5"pip install 通用产品"裁决精神。
- 缺点/成本：① API 不同——`search()`/`search_agentic()` 返回 **list[dict]**，
  需重写 formatted_memory 拼装（list[dict]→str）；② **引入 ChromaDB 依赖**
  （向量库），违背"每 conversation 小隔离存储"原则（与 MemoryOS 排除 chromadb
  同理）；③ **风险**：需核验 `search_agentic` 是否保 link 邻域——若产品库 search
  只返主 memory 不含邻域，会丢失 A-Mem 的 link 核心特性（formatted_memory 不完整）；
  ④ read/update/delete 可选接入，增加 adapter 面积。
- 成本定性：中-高，**换引擎+重写检索包装**，非"同引擎改配置"。

**选项 C（折中）：维持实验包引擎 + 报告标注"非产品库，是论文官方复现引擎"**
- 等同选项 A，但在接口文档显式标注来源，供后续复查。

**我的建议：选项 A（维持现状）**，并在接口文档注明来源。理由：vendored 引擎
已满足 ws02.5 审计的实质要件（benchmark 无关、retrieve 独立、记忆完整），且
迁移到 A-mem-sys 有丢失 link 邻域 + 引入 ChromaDB 的实质风险。但**最终由架构师
裁定**——若架构师坚持"必须 pip install 产品库"，则走选项 B（迁移工程另派）。

### 迁移成本矩阵

| 选项 | 算法 fork 重写？ | 同引擎改配置？ | 依赖变化 | formatted_memory 重写 | 风险 |
| --- | --- | --- | --- | --- | --- |
| A 维持 | 否 | 是（已就位） | 无 | 无 | 低 |
| B 迁 A-mem-sys | 否（同算法思想） | 否（换引擎） | +ChromaDB | 是（list[dict]→str） | 中（可能丢 link 邻域） |

---

## 断点 / 待架构师裁定

1. **【P1 裁决请求】vendored 实验包引擎 vs 产品库 A-mem-sys**：adapter 现用
   `RobustAgenticMemorySystem`（实验复现包，benchmark 无关），非 `pip install`
   产品库 `A-mem-sys` 的 `AgenticMemorySystem`。两库 API/存储/检索形态不同
   （见 Q2 表）。是否视同"通用产品接口"？我建议选项 A 维持（见 Q5），但需架构师定夺。

2. **【P2 小差异，不影响算法】注入格式空格**：官方 test_advanced_robust.py:243
   `"Speaker " + turn.speaker + "says : " + turn.text`（"Alicesays : hello"）vs
   adapter amem_adapter.py:839 `f"Speaker {turn.speaker} says: {turn.content}"`
   （"Alice says: hello"）。adapter 格式更规范，语义一致，无需改。

3. **【P2 retrieve_k 分 category**：adapter 用论文 Table 8 的 GPT-4o-mini per-category k
   （40/40/50/50/40，amem_adapter.py:77-83），比官方脚本固定 k=10 更细。这是论文调参，
   合理但比官方脚本激进；非 LoCoMo/无 category 回退 profile retrieve_k。仅供架构师知晓。

4. **【P2 category 5（adversarial）拒绝**：adapter 对 category 5 抛
   ConfigurationError（amem_adapter.py:444-449），因官方 c5 prompt 需 gold answer
   （test_advanced_robust.py:117-128 用 `qa.final_answer` 构造二选一），框架禁止
   gold 进 method。**正确的隐私边界处理**，但意味着 A-Mem official-mini profile
   不支持 c5。仅供架构师知晓。

5. **【P3 answer prompt 来源】adapter `_build_answer_prompt`（amem_adapter.py:843-872）
   抄自 test_advanced_robust.py 的 LoCoMo per-category answer prompt。按 ws02.5
   "prompt 来源政策"（answer/judge prompt 必须 per-benchmark、method 无关，benchmark
   官方仓库有就先用），需确认此 prompt 与 LoCoMo benchmark 官方仓库的 prompt 是否
   一致——本次只读审计（聚焦注入/检索接口）不展开，交架构师在 answer prompt 审计
   阶段核。adapter LongMemEval 走另一套 reader prompt（amem_adapter.py:846-857，
   `AMEM_LONGMEMEVAL_READER_PROMPT_VERSION`），亦同。

---

## 证据索引（文件:行号）

### 第三方仓库（`third_party/methods/A-mem/`）

- README.md:3-5 —— 自述"复现实验包"，指向 A-mem-sys 为产品库。
- README.md:82-109 —— 运行方式（test_advanced[_robust].py + locomo10.json）。
- README.md:89 —— 推荐 robust。
- README.md:112 —— `--retrieve_k` default 10。
- memory_layer.py:261-305 —— MemoryNote 字段集（standard）。
- memory_layer.py:554-665 —— SimpleEmbeddingRetriever（被 robust 复用）。
- memory_layer.py:666-727 —— AgenticMemorySystem.__init__ / add_note（standard）。
- memory_layer.py:753-857 —— process_memory（standard，1 次 JSON-schema LLM call）。
- memory_layer.py:859-875 —— find_related_memories（standard）。
- memory_layer.py:877-898 —— find_related_memories_raw（standard，主+邻域）。
- memory_layer_robust.py:1-11 —— docstring（drop-in replacement + 6 点差异）。
- memory_layer_robust.py:24 —— `from memory_layer import SimpleEmbeddingRetriever, simple_tokenize`。
- memory_layer_robust.py:243-266 —— RobustLLMController 工厂。
- memory_layer_robust.py:273-345 —— RobustMemoryNote + analyze_content。
- memory_layer_robust.py:352-373 —— RobustAgenticMemorySystem.__init__。
- memory_layer_robust.py:377-397 —— add_note（robust）。
- memory_layer_robust.py:411-428 —— find_related_memories（robust）。
- memory_layer_robust.py:430-459 —— **find_related_memories_raw（robust，主+邻域，返回 str）**。
- memory_layer_robust.py:463-540 —— process_memory（robust，3 次顺序 plain-text LLM call）。
- llm_text_parsers.py:128-131 —— ANALYZE_CONTENT_PROMPT（通用）。
- llm_text_parsers.py:143 —— EVOLUTION_DECISION_PROMPT（通用）。
- llm_text_parsers.py:164 —— STRENGTHEN_DETAILS_PROMPT（通用）。
- llm_text_parsers.py:180 —— UPDATE_NEIGHBORS_PROMPT（通用）。
- llm_text_parsers.py:204-206 —— FOCUSED_KEYWORDS_PROMPT（通用）。
- load_dataset.py:41-57 —— LoCoMo 专用数据结构（EventSummary/Observation/LoCoMoSample）。
- test_advanced_robust.py:53-107 —— RobustAdvancedMemAgent（generate_query_llm/retrieve_memory）。
- test_advanced_robust.py:96-107 —— generate_query_llm（keyword prompt，被 adapter 复刻）。
- test_advanced_robust.py:109-153 —— answer_question（LoCoMo per-category prompt）。
- test_advanced_robust.py:240-244 —— 注入格式 `"Speaker "+speaker+"says : "+text`。
- test_advanced_robust.py:348 —— `--retrieve_k` default 10。
- data/locomo10.json —— 自带 LoCoMo 10 样本（adapter 不碰）。

### 外部交叉验证

- github.com/WujiangXu/A-mem-sys README —— 产品库 `AgenticMemorySystem`，API
  search/search_agentic 返回 list[dict]，ChromaDB，有 read/update/delete，无数据集。

### 我们的 adapter（`src/memory_benchmark/methods/amem_adapter.py`）

- :1-5 —— docstring（包装官方 robust layer，不重写算法）。
- :54-83 —— 常量（AMEM_METHOD_DIRECTORY / AMEM_GPT4O_MINI_CATEGORY_K）。
- :191-226 —— import_amem_robust_classes（import memory_layer_robust）。
- :209,218 —— 检查 + import memory_layer_robust.py。
- :219-222 —— 导出 RobustAgenticMemorySystem / RobustLLMController。
- :339-360 —— ingest（v3，按 turn）。
- :434-505 —— retrieve（keyword 生成 + find_related_memories_raw + 拼 answer_prompt）。
- :444-449 —— category 5 adversarial 拒绝（隐私边界）。
- :456-465 / :469-472 —— 调 runtime.find_related_memories_raw(query_keywords, k)。
- :474 —— `str(context)` → memory_context（未裁剪）。
- :507-538 —— _retrieve_native（v3 纯检索路径，返 RetrievalResult）。
- :540-576 —— get_answer（单独调 reader LLM）。
- :709-738 —— _create_official_runtime（构造 RobustAgenticMemorySystem）。
- :77-83,926-936 —— retrieve_k 分 category（Table 8）。
- :834-841 —— _call_runtime_add（add_note，注入格式）。
- :843-872 —— _build_answer_prompt（LoCoMo per-category，抄自 test_advanced_robust）。
- :896-924 —— _generate_query_keywords（keyword prompt，逐字复刻官方）。
