---
audit: LightMem
workstream: ws02.5
status: 完成（只读审计，未改 src/ 与 tests/）
auditor: actor（Claude Sonnet 4.8，2026-07-08）
method_class: 学术型（ICLR 2026）
one_line: LightMem 仓库为单仓库单核心算法，adapter 已用通用产品 `LightMemory`；注入保真高、原生 retrieve 不耦合答题；唯一偏离点是 LoCoMo 路径绕过官方 `retrieve()` 自复刻 combined cosine（算法等价，为拿 payload 做 speaker 分组）。
---

# LightMem 接口保真审计报告

> 本报告为【只读审计】，仅新增本文件，未修改 `src/`、`tests/`、`third_party/`。
> 证据来源：① LightMem 官方仓库源码 + README（第一手）② 我们 adapter 代码。
> 所有行号对齐仓库当前 HEAD。

## 结论速览

| 维度 | 结论 | 风险 |
| :--- | :--- | :--- |
| 接口保真（通用 vs 专用） | adapter 主体调通用产品 `LightMemory`；LongMemEval 路径用官方 `retrieve()`；LoCoMo 路径**绕过**官方 `retrieve()` 自复刻 combined cosine（算法等价） | 低（算法一致，仅实现路径偏离） |
| 注入保真 | adapter ingest 配置与官方 `add_locomo.py` 完全对齐（`extract_threshold=0.1`、`force_segment/force_extract` 末批、`offline_update score_threshold=0.9`、不调 `summarize` 对应 LightMem 模式） | 无 |
| 检索完整（记忆层覆盖） | 两条路径均查主记忆库 `embedding_retriever`；summary 层未启用（不调 `summarize()`，与官方 LightMem 模式一致，不算漏） | 无 |
| 原生 retrieve 是否耦合答题 | **不耦合**——`LightMemory.retrieve()` 独立返回 `list[str]`，无 answer/chat 方法，剥离无困难 | 无 |
| 迁移成本 | 低-中：无算法 fork；唯一工作是 LoCoMo 路径是否改回官方 `retrieve()`（受限于官方 retrieve 丢 payload，需架构师裁定） | — |

---

## Q1 仓库版本/目录 + benchmark 专用目录

### 仓库定位（README 第一手）

LightMem 仓库为 `zjunlp/LightMem`（ICLR 2026，`third_party/methods/LightMem/`）。README:60-69 明确：**单仓库托管 4 个 method**——LightMem（主）、FluxMem、EM²Mem、StructMem，共享同一套代码：

| Method | 代码位置 | 是否本审计对象 |
| :--- | :--- | :--- |
| **LightMem** | `src/lightmem/`（核心 `memory/lightmem.py` 的 `LightMemory` 类） | ✅ 本审计对象 |
| FluxMem | `src/fluxmem/`（`agent.py` + `graph/` + `retrieval/` + `stages/`） | ✗ 独立 method |
| EM²Mem | `src/em2mem/`（多模态记忆，含 vendored VLM2Vec） | ✗ 独立 method |
| StructMem | 复用 `src/lightmem/`，由 `extraction_mode="event"` + `summarize()` 触发 | ✗ LightMem 的配置变体 |

**关键：与 MemoryOS 不同，LightMem 没有 pypi/eval/mcp 多版本 fork。** 核心算法只有一套（`src/lightmem/memory/lightmem.py`，877 行，单一 `LightMemory` 类）。`mcp/server.py` 是服务封装层（非另一套引擎）；`src/fluxmem`、`src/em2mem` 是同仓库的**其他 method**，不是 LightMem 的变体。

### benchmark 专用评测目录（存在，三个）

仓库有明确的 benchmark 专用评测目录 `experiments/`，每个子目录自带数据加载 + 检索 + QA + judge：

| 目录 | benchmark | 关键文件 | 自带能力 |
| :--- | :--- | :--- | :--- |
| `experiments/locomo/` | LoCoMo | `add_locomo.py`(703行) `search_locomo.py`(845行) `retrievers.py` `llm_judge.py` `prompts.py`(557行) | 建记忆 + combined/per-speaker 检索 + QA + LLM judge，含 `--enable-summary`(StructMem 模式) |
| `experiments/longmemeval/` | LongMemEval | `run_lightmem_gpt.py`(213行) `run_lightmem_qwen.py`(233行) `offline_update.py` | 完整评测 pipeline（构造+RAG+QA+judge） |
| `experiments/egolife/` | EgoLife（多模态） | `eval/eval.py` `preprocess/` `scripts/*.sh` | 多模态记忆评测 |

README:73-81 把这三个目录列为"Reproduction Scripts"；README:170-173 Quick Start 直接让用户 `cd experiments && python run_lightmem_qwen.py`——即官方推荐路径本身就走 benchmark 专用脚本。

另有 `src/lightmem/memory_toolkits/`（README:87、`memory_toolkits/readme.md`）是 **baseline 对比框架**（对比 A-MEM/Mem0/LangMem/FullContext/NaiveRAG 等），三阶段 `memory_construction → memory_search → memory_evaluation`。**注意：LightMem 自身不在该框架的 baseline 列表里**（它是被对比的对象），所以该框架不构成 LightMem 的"另一套实现"。

### 多版本算法一致性

**不适用（无多版本）**。LightMem 核心算法单一（`lightmem.py`）。`experiments/` 下的脚本调用的就是 `src/lightmem/memory/lightmem.py` 的 `LightMemory` 类（`add_locomo.py:8` `from lightmem.memory.lightmem import LightMemory`、`add_locomo.py:230` `LightMemory.from_config(config)`）——benchmark 专用脚本与通用产品**共用同一引擎**，差异只在数据加载/检索封装/打分逻辑（这些恰是我们框架要替换的）。这点与 MemoryOS（eval/ 与 pypi 是两套独立代码）有本质区别。

---

## Q2 adapter 调的是通用产品接口还是 benchmark 专用实现

### 真实 adapter 文件名

任务卡写的 `lightMem_adapter.py` 实际为 **`lightmem_adapter.py`**（全小写）。确认：`src/memory_benchmark/methods/` 下文件名 `lightmem_adapter.py`（1692 行）。

### 主体调用：通用产品 `LightMemory`（符合 ws02.5 裁决）

adapter docstring（`lightmem_adapter.py:1-5`）自述"包装 `third_party/methods/LightMem/` 中的官方 LightMemory，不重写核心记忆算法"。证据链：

| 步骤 | adapter 行号 | 调用 | 对应官方 |
| :--- | :--- | :--- | :--- |
| 导入类 | `:216-239` `import_lightmem_classes()` → `importlib.import_module("lightmem.memory.lightmem")` → `{"LightMemory": module.LightMemory}` | 导入通用产品 `LightMemory` | `src/lightmem/memory/lightmem.py:107` |
| 构造 backend | `:834` `lightmemory_cls = classes["LightMemory"]`；`:842` `backend = ... lightmemory_cls.from_config(backend_config)` | `LightMemory.from_config()` | `lightmem.py:195` |
| 注入 | `:482-485` `backend.add_memory(messages, force_segment=..., force_extract=...)` | 官方 `add_memory()` | `lightmem.py:204` |
| offline update | `:1012-1016` `backend.construct_update_queue_all_entries()` + `backend.offline_update_all_entries(score_threshold=0.9)` | 官方 update | `lightmem.py:457,539` |

### 检索路径分叉：LongMemEval 走官方，LoCoMo 走复刻（关键偏离点）

adapter 的 `retrieve()`（`:682-752`）按 benchmark 分两条路径：

1. **LongMemEval 路径**（`:695-709`）：`backend.retrieve(question.text, limit=self.config.retrieve_limit, filters=None)` —— **直接调官方 `LightMemory.retrieve()`** ✅ 完全符合通用产品优先裁决。

2. **LoCoMo 路径**（`:710-716` → `:1018-1068` `_retrieve_locomo_memories`）：**绕过官方 `retrieve()`**，用 backend 官方组件手算：
   - `:1044` `entries = embedding_retriever.get_all(with_vectors=True, with_payload=True)` 拿全量
   - `:1045` `query_vector = text_embedder.embed(question.text)`
   - `:1052` `score = _cosine_similarity(query_vector, vector)` 逐条算
   - `:1067-1068` sort desc + `[:retrieve_limit]`
   - 注释 `:1023` 自述"复刻 LightMem LoCoMo `search_locomo.py` 的 combined vector search"。

**偏离原因**（`:1483-1485` 注释）：官方 `LightMemory.retrieve()` 只返回 `list[str]`（格式化字符串，`lightmem.py:693-701`），**丢弃 payload**；而 LoCoMo 官方 `search_locomo.py` 的 combined/per-speaker 模式需 payload 的 `speaker_name` 做 speaker 分组（`search_locomo.py:74-128` `retrieve_by_speaker`）。adapter 为复现 LoCoMo 官方 speaker 分组，选择复刻而非调官方 retrieve。

### 关于 `:249-257` 的 experiments 文件清单

`build_lightmem_source_identity()` 列了 `experiments/locomo/add_locomo.py` 等文件，**仅用于计算源码 SHA256 身份指纹**（`:264-280`），**不 import、不调用**这些 benchmark 专用脚本。adapter 实际调用的 LoCoMo prompt 通过 `_load_lightmem_locomo_prompt()`（`:1448-1473`）从 `experiments/locomo/prompts.py` 读取常量字符串——这是 prompt 复用（属 ws02.5 "benchmark 专用目录只作只读参考"的允许范围），非算法调用。

### 小结

adapter **未使用** benchmark 专用评测实现（`experiments/` 下的 add_locomo.py/search_locomo.py 评测 pipeline 未被调用）。主体（注入、update、LongMemEval 检索）走通用产品 `LightMemory`。**唯一偏离**：LoCoMo 检索路径自复刻 combined cosine，但用官方 backend 组件，算法与官方 `VectorRetriever.retrieve` 等价（见 Q4 详证）。

> **P1 修复（2026-07-08，commit `63ccba2`）**：上述偏离已消除。LoCoMo 路径
> `_retrieve_locomo_memories`（get_all+手算 cosine 自复刻）改为 `_retrieve_with_payload`
> 调官方 `embedding_retriever.search(return_full=True)` 拿带 payload 结果；retrieve()
> LongMemEval/LoCoMo 两路径统一返回 `list[dict]`（F1 解决）；LongMemEval answer
> prompt 用新增 `_format_lightmem_memory_as_official_retrieve` 还原官方 retrieve
> `'{ts} {wd} {mem}'` 格式（不偏离 run_lightmem_gpt.py:186）；删 `_cosine_similarity`；
> retrieval_profile 统一 `lightmemory_retrieve`。Step1 gate 已核实自复刻 vs
> VectorRetriever 逐行等价（无主场优势）。focused 33 passed，全量 892 passed。

---

## Q3 原生注入/检索接口 + 耦合评估

### 注入接口 `add_memory`（`lightmem.py:204-257`）

```python
def add_memory(
    self,
    messages,                                    # dict 或 list[dict]，每条须含 time_stamp
    METADATA_GENERATE_PROMPT: Optional[Union[str, Dict[str, str]]] = None,
    *,
    force_segment: bool = False,                 # 强制 topic 分段
    force_extract: bool = False,                 # 强制记忆抽取（越过阈值）
    boundmem_tags: Optional[Any] = None,
) -> dict:
```

- **粒度**：message list（每条 dict 需含 `time_stamp` 字段，`MessageNormalizer:59-104` 强制要求）。官方 LoCoMo 用法是逐 turn 调一次（`add_locomo.py:332-336`），末 turn `force_segment=is_last_turn, force_extract=is_last_turn`。
- **官方参数**：`force_segment` / `force_extract` 在 buffer 未达阈值时强制触发分段/抽取；`METADATA_GENERATE_PROMPT` 可传自定义抽取 prompt（dict 形式支持 flat/event 多视角）。
- **触发的核心流程**（docstring `:213-257`）：normalize → 预压缩（llmlingua-2）→ topic 分段 → 短期 buffer 累积 → 抽取（metadata+summary）→ 写 `MemoryEntry` → 按 `update` 模式 online/offline 持久化。
- **adapter 用法**（`:473-485`）：逐 batch 调，`force_segment=force_extract=is_last_batch`，与官方 LoCoMo 末 turn 触发一致。

### 检索接口 `retrieve`（`lightmem.py:644-707`）

```python
def retrieve(
    self,
    query: str,
    limit: int = 10,
    filters: Optional[dict] = None,
    *,
    boundmem_tags: Optional[Any] = None,
    boundmem_drop_untagged: bool = False,
) -> list[str]:                                  # 返回格式化字符串列表
```

- **检索层**：只查 `self.embedding_retriever`（主记忆库，`:675-680` `embedding_retriever.search(query_vector, limit, filters, return_full=True)`）。**不查 `summary_retriever`**（summary 层独立，仅 `summarize()` 写入，见下）。
- **返回**：`list[str]`，每条格式 `"{time_stamp} {weekday} {memory}"`（`:693-701`）。**丢弃 payload**（speaker_name、id、score 等），这是 LoCoMo 路径复刻的根因（Q2）。
- **top_k**：`limit` 参数，默认 10；adapter 用 `config.retrieve_limit`。
- **无 answer/chat 方法**：`LightMemory` 类无 `answer`/`chat`/`get_response`/`generate` 方法（grep `def (answer|chat|get_response)` 在 lightmem.py 无匹配）。检索与答题**完全解耦**。

### 耦合评估：原生 retrieve 与答题**无耦合**

LightMem 原生 `retrieve()` 是纯检索，返回 `list[str]`，不调任何 LLM 答题、不拼 answer prompt。**剥离出纯检索（返回 formatted_memory）零困难**——adapter 的 `_retrieve_native()`（`:754-781`）已是这么做的：调 `retrieve()` → 拼成 `formatted_memory` 字符串返回 `RetrievalResult`，不生成 answer。

（对比：MemoryOS 的 `get_response` 把 retrieve 与答题耦合，需"忠实抽出 formatted_memory"是难点；LightMem 无此问题。）

### 附属：summarize（`lightmem.py:750-877`）与 summary 记忆层

- `summarize()` 把主记忆库按时间窗聚合，生成摘要存入**独立的 `summary_retriever`** 库（`:848-855` `store_summary(... summary_retriever=self.summary_retriever ...)`）。
- `summarize()` 需配置 `summary_retriever`，否则 `:778-779` 抛 `ValueError("Summarization not enabled...")`。
- **官方 retrieve 不查 summary 层**——summary 仅在 benchmark 专用脚本 `search_locomo.py:163-186` 的 `retrieve_summaries()` + `--enable-summary`（StructMem 模式）下被额外检索。LightMem 模式（不带 summary）不涉及 summary 层。

---

## Q4 formatted_memory 是否覆盖全部记忆层

### LightMem 的记忆层结构

| 记忆层 | 存储 | 写入 | 检索 |
| :--- | :--- | :--- | :--- |
| **主记忆库** | `embedding_retriever`（Qdrant，offline_update 合并后） | `add_memory()` + `offline_update_all_entries()` | `retrieve()` 查此层 |
| **摘要库** | `summary_retriever`（独立 Qdrant collection） | `summarize()` | `retrieve()` **不查**；仅 benchmark 脚本 `retrieve_summaries()` 查 |
| **短期 buffer** | 进程内 `shortmem_buffer_manager`/`senmem_buffer_manager`（512 tokens） | `add_memory()` 累积 | retrieve 不查（服务于 add 时的 topic 分段） |

### adapter 的覆盖情况

- **主记忆库**：✅ 两条 retrieve 路径均覆盖。
  - LongMemEval 路径 `backend.retrieve()` → 内部查 `embedding_retriever`（`lightmem.py:675`）。
  - LoCoMo 路径 `embedding_retriever.get_all()` + cosine（`:1044-1068`）→ 查 `embedding_retriever`。
- **摘要库**：⚠️ 未覆盖——但 adapter **不调 `summarize()`**（grep 全文件无 `.summarize(` 调用），故 summary 库始终为空，"不查"不构成漏。adapter 配了 `summary_retriever`（`:435-443`）仅为满足 `LightMemory.__init__` 的组件初始化，未启用 summary 生成。**这与官方 LightMem 模式一致**（README:49-51、`search_locomo.py:741` `"method": "structmem" if args.enable_summary else "lightmem"`——LightMem 主结果不带 summary，StructMem 才带）。
- **短期 buffer**：进程内临时态，retrieve 时不查，符合官方设计。

### 结论：记忆层覆盖完整

adapter 的 `formatted_memory` 覆盖 LightMem 核心记忆层（主记忆库）完整。summary 层因未启用 summarize 而不涉及（与官方 LightMem 模式口径一致，非缺陷）。formatted_memory 拼装（`:717-719` `\n.join(_format_lightmem_memory(memory) ...)`）与官方 `format_related_memories`（`retrievers.py:143-160`）格式一致：`[Memory recorded on: {date}, {weekday}]\n{memory}`（adapter `:1539-1542`）。

### LoCoMo 复刻检索的算法等价性证明

adapter `_retrieve_locomo_memories`（`:1044-1068`）与官方 `VectorRetriever.retrieve`（`retrievers.py:111-132`）逐项对比：

| 步骤 | 官方 `VectorRetriever.retrieve` | adapter `_retrieve_locomo_memories` | 一致 |
| :--- | :--- | :--- | :--- |
| query 向量 | `self.embedder.embed(query_text)` (`:113`) | `text_embedder.embed(question.text)` (`:1045`) | ✅ |
| 候选加载 | `QdrantEntryLoader.load_entries` (`:47-51`) | `embedding_retriever.get_all(with_vectors=True)` (`:1044`) | ✅ 同一 Qdrant |
| 评分 | `self._cosine_similarity(query_vector, vec)` (`:125`) | `_cosine_similarity(query_vector, vector)` (`:1052`) | ✅ 同算法 |
| 排序 | `results.sort(key=score, reverse=True)` (`:131`) | `retrieved.sort(key=score, reverse=True)` (`:1067`) | ✅ |
| 截断 | `results[:limit]` (`:132`) | `retrieved[:retrieve_limit]` (`:1068`) | ✅ |
| 返回结构 | `{'id','score','payload','source':'vector'}` (`:126`) | 同 + `_retrieved_speaker` (`:1053-1065`) | ✅（多 speaker 字段） |

cosine 实现：官方用 numpy（`retrievers.py:134-141`），adapter 用纯 Python（`:1559-1571`）——**数值结果一致**（标准 cosine 公式）。adapter 多出的 `_retrieved_speaker` 字段用于后续 speaker 分组（`:1491-1496`），不改变检索结果集。

**结论：LoCoMo 复刻检索与官方 combined 检索算法完全等价**，仅实现路径不同（adapter 直调 `embedding_retriever.get_all`，官方经 `QdrantEntryLoader` 带 SQLite fallback）。复刻动机是拿 payload 做 speaker 分组（官方 `retrieve()` 丢 payload）。

---

## Q5 建议：版本/接口/迁移成本

### 版本建议：维持通用产品 `LightMemory`（无需迁移版本）

LightMem 无多版本 fork，核心算法单一。adapter 现用的 `src/lightmem/memory/lightmem.py` 的 `LightMemory` 类就是通用产品接口（README:213-296 的 Quick Start 示例即此类）。**无版本迁移问题**——这与 MemoryOS（需从 eval/ 迁到 pypi）不同。

### 接口建议：通用产品优先（基本符合，一处待裁定）

adapter 主体已符合 ws02.5 裁决（通用产品优先）。**唯一待裁定点**：LoCoMo 路径的 `_retrieve_locomo_memories` 是否改回官方 `backend.retrieve()`？

- **若改回官方 `retrieve()`**：接口最纯净，但丢失 payload → 无法做 speaker 分组 → 无法复现 LoCoMo 官方 prompt 的双 speaker 区域结构（`search_locomo.py:207-257` `build_prompt_with_speaker_memories`）。这会改变 reader prompt 的输入形态，可能影响 LoCoMo 分数。
- **若保持复刻**：算法与官方等价（Q4 已证），且能拿 payload 做 speaker 分组，忠实复现 LoCoMo 官方检索-答题流程。代价是 adapter 多一段自维护检索代码。

**审计员倾向**：保持复刻。理由——官方 `retrieve()` 返回 `list[str]` 丢 payload 是 API 设计局限（非 adapter 短板）；复刻用的是官方 backend 组件（`text_embedder`/`embedding_retriever`），非自造检索算法；算法与官方 `VectorRetriever` 逐行等价。改回官方 retrieve 反而会破坏 LoCoMo speaker 分组的保真度。**最终由架构师裁定**（涉及"接口纯净" vs "speaker 分组保真"的取舍）。

### 迁移成本：低-中

- **无算法 fork 要重写**：LightMem 单一引擎，adapter 已在用。
- **无版本切换**：不涉及 MemoryOS 那种 eval→pypi 的引擎迁移。
- **唯一工作量**（若架构师裁定 LoCoMo 改回官方 retrieve）：改 `_retrieve_locomo_memories` 一个方法 + 调整 speaker 分组逻辑（可能需官方 retrieve 增加 payload 返回，或放弃 speaker 分组）。属"同引擎改检索路径"，非"算法重写"。预估 < 1 个任务卡。
- **配置无需改**：adapter 配置（`:382-455`）已与官方 `add_locomo.py` 完全对齐（`extract_threshold=0.1`、`pre_compress=True`、`topic_segment=True`、`messages_use="user_only"`、`metadata_generate=True`、`text_summary=True`、`index/retrieve_strategy="embedding"`、`offline_update score_threshold=0.9`、`extraction_mode` 默认 flat）。

---

## 发现点（plan 之外，只报告不处置）

### F1 LongMemEval 与 LoCoMo 检索路径不一致（待架构师确认是否刻意）

adapter 对 LongMemEval 用官方 `retrieve()`（返回 `list[str]`），对 LoCoMo 用复刻 combined cosine（返回 `list[dict]` 带 payload）。两条路径返回类型不同，`_format_lightmem_memory`（`:1519-1548`）做了双格式兼容。差异根因是 LoCoMo 需 speaker 分组而 LongMemEval 不需。这是**有意的 benchmark 适配**还是应统一为单一路径，待架构师确认。若统一，建议以"官方 `retrieve()` + 扩展 payload 返回"为长期方向（需改 vendored lightmem.py 的 retrieve，属 third_party 改动，需走 workstream 记录）。

### F2 adapter 配置 `extract_threshold=0.1` 而非 README 默认 0.5

adapter `:415` `"extract_threshold": 0.1`，README:509 默认 0.5。经核对 `add_locomo.py:192` 官方 LoCoMo 脚本也用 0.1——**adapter 与官方 LoCoMo 一致**，是 LoCoMo 专用参数（更激进抽取）。非缺陷，记录以备架构师知晓：此参数随 benchmark 变（LongMemEval 可能不同），未来跨 benchmark 统一配置时需注意。

### F3 vendored LightMem 含完整 VLM2Vec 子模块（体积大）

`src/em2mem/embedding/VLM2Vec/` 含大量多模态训练/评测代码（约 200+ 文件）。LightMem（纯文本记忆）不依赖它，仅 EM²Mem 用。当前不影响 adapter，但提示：vendored 仓库体积远超 LightMem 本身所需，未来若要精简可考虑浅克隆或 sparse-checkout（非本审计范围）。

### F4 StructMem 模式未纳入 adapter（潜在扩展点）

LightMem 仓库的 StructMem（`extraction_mode="event"` + `summarize()` + summary 检索）是 ACL 2026 的独立 method，README:183-195 显示 StructMem 在 LoCoMo 上分数更高（event+summary 的 Temp 维度 81.62 vs flat 的 78.50）。Phase 1 method 清单里 LightMem 与 StructMem 是否视作同一 method 的两种配置，还是分别接入，待架构师明确（本审计仅覆盖 LightMem 模式）。

---

## 证据索引（行号速查）

### 第三方仓库（`third_party/methods/LightMem/`）

| 证据 | 位置 |
| :--- | :--- |
| 4 method 导航表 | `README.md:60-69` |
| benchmark 复现脚本表 | `README.md:73-81` |
| 通用接口 Quick Start（add_memory/retrieve/summarize） | `README.md:213-338` |
| `LightMemory` 类定义 | `src/lightmem/memory/lightmem.py:107` |
| `from_config` | `src/lightmem/memory/lightmem.py:195` |
| `add_memory` 签名 + docstring | `src/lightmem/memory/lightmem.py:204-257` |
| `retrieve` 签名（独立，不耦合答题） | `src/lightmem/memory/lightmem.py:644-652` |
| `retrieve` 实现（只查 embedding_retriever，返回 list[str]） | `src/lightmem/memory/lightmem.py:672-707` |
| `summarize` 签名（需 summary_retriever） | `src/lightmem/memory/lightmem.py:750-759` |
| summary 存独立 summary_retriever | `src/lightmem/memory/lightmem.py:848-855` |
| `construct_update_queue_all_entries` / `offline_update_all_entries` | `src/lightmem/memory/lightmem.py:457,539` |
| LoCoMo 官方配置（extract_threshold=0.1 等） | `experiments/locomo/add_locomo.py:159-227` |
| LoCoMo 官方 add_memory 调用（末 turn force） | `experiments/locomo/add_locomo.py:332-336` |
| LoCoMo 官方 offline_update（score_threshold=0.9） | `experiments/locomo/add_locomo.py:446-447` |
| LoCoMo 官方 summarize（仅 enable_summary） | `experiments/locomo/add_locomo.py:400-403` |
| LoCoMo combined 检索 + summary 检索 | `experiments/locomo/search_locomo.py:129,163` |
| LoCoMo 检索+prompt 耦合（build_prompt_with_speaker_memories） | `experiments/locomo/search_locomo.py:207-257` |
| `VectorRetriever.retrieve`（全量 cosine） | `experiments/locomo/retrievers.py:111-132` |
| `format_related_memories`（格式化口径） | `experiments/locomo/retrievers.py:143-160` |
| baseline 对比框架（非 LightMem 本身） | `src/lightmem/memory_toolkits/readme.md` |

### adapter（`src/memory_benchmark/methods/lightmem_adapter.py`）

| 证据 | 位置 |
| :--- | :--- |
| docstring（包装官方、不重写算法） | `:1-5` |
| 导入官方 `LightMemory` | `:216-239` |
| source identity（experiments 文件仅做哈希） | `:249-280` |
| config 构造（与官方 add_locomo.py 对齐） | `:382-455` |
| 配置 summary_retriever（未启用 summarize） | `:435-443` |
| `add()` 调 `backend.add_memory` + LoCoMo offline_update | `:457-490` |
| `force_segment/force_extract = is_last_batch` | `:476-477` |
| retrieve 分叉（LongMemEval 官方 / LoCoMo 复刻） | `:695-716` |
| LongMemEval 路径 `backend.retrieve()` | `:699-709` |
| `_retrieve_native`（v3 纯检索，不答题） | `:754-781` |
| offline_update `score_threshold=0.9` | `:1012-1016` |
| `_retrieve_locomo_memories`（复刻 combined cosine） | `:1018-1068` |
| 复刻原因（官方 retrieve 丢 payload） | `:1483-1485` |
| `_format_lightmem_memory`（与官方格式一致） | `:1519-1548` |
| `_cosine_similarity`（与官方 VectorRetriever 等价） | `:1559-1571` |
| 无 `summarize()` 调用（grep 全文件确认） | — |
