---
audit: SimpleMem
workstream: ws02.5
mode: 只读审计（不改 src/ 与 tests/，不改 third_party/）
auditor: actor（新人，WorkBuddy/GLM-5.2；原误标 Claude Sonnet 已更正）
date: 2026-07-08
adapter_file: src/memory_benchmark/methods/simplemem_adapter.py（小写）
vendored_root: third_party/methods/SimpleMem/
---

# SimpleMem 接口保真审计

> 本报告由 actor 按 ws02.5 README 的 (a)-(e) 清单逐条核对，一手源为
> `third_party/methods/SimpleMem/` 仓库代码 + 官方 README。仅产出本文件，
> 不碰 `src/`、`tests/`、`third_party/`。可与其它 method 审计并行。

## 0. 结论速览

| 维度 | 结论 | 一句话 |
|:--|:--|:--|
| 接口保真 | ✅ 通过 | adapter 调通用产品 text backend（`main.SimpleMemSystem`），非 benchmark 专用实现 |
| 记忆完整（记忆层） | ✅ 通过 | SimpleMem 只有一层记忆（MemoryEntry 单表），retrieve 回全部命中，无漏层 |
| formatted_memory 字段 | ⚠️ 部分缺失 | adapter 的 formatted_memory 只取 2/6 字段，缺 Symbolic 层 4 字段；native 口径靠 prompt_messages 补全 |
| 能否剥离纯检索 | ✅ 可剥离 | hybrid_retriever 独立于 ask()，官方评测本身就这么调，adapter 已正确剥离 |
| 迁移成本 | 零迁移 | adapter 已在通用产品接口上，无需从 benchmark 专用迁回（与 MemoryOS 情形不同）|

**与 MemoryOS 的关键差异**：MemoryOS 的 `eval/` 是与 pypi **两套独立代码**的 fork；
而 SimpleMem 的 `test_locomo10.py` 是「通用引擎 + 评测壳」——它 `from main import
SimpleMemSystem`（test_locomo10.py:22），用的就是通用产品引擎，不是另一套算法。
因此 SimpleMem 不存在 MemoryOS 那样的迁移工程。

---

## 1. 仓库版本/目录、README 第一手、benchmark 专用目录、多版本算法一致性

### 1.1 仓库目录结构（一手）

`third_party/methods/SimpleMem/` 顶层（`ls -la` 实测）：

| 目录/文件 | 性质 | 说明 |
|:--|:--|:--|
| `main.py` | **通用产品入口** | `SimpleMemSystem` 类，text backend 主入口（263 行）|
| `simplemem/` | **通用产品包** | 含 `core/`（核心算法）、`text/system.py`（=main.py）、`router.py`（AutoMemory auto-routing）、`evolver/`、`multimodal/`、`integrations/` |
| `simplemem/core/` | **核心算法** | `memory_builder.py`（注入/压缩）、`hybrid_retriever.py`（检索）、`answer_generator.py`（答题）、`database/vector_store.py`（存储）、`models/memory_entry.py`（记忆单元）、`settings.py`（参数）、`utils/{llm_client,embedding}.py` |
| `test_locomo10.py` | **LoCoMo 专用评测** | 自带数据加载 + 打分（BLEU/METEOR/ROUGE/BERTScore + 可选 LLM judge），**但调通用引擎**（见 1.3）|
| `test_ref/` | 数据 + 夹带代码 | `locomo10.json`（烤进数据）、`load_dataset.py`（LoCoMo 数据结构共享工具）、`test_advanced.py`（**夹带的 A-Mem 代码**，见 1.4）、`utils.py`（打分聚合）|
| `cross/` | **另一产品**（跨会话）| SimpleMem-Cross，async-first，SQLite+LanceDB，独立 `orchestrator.py`/`session_manager.py` |
| `EvolveMem/` | **另一方法**（自演化）| Extending SimpleMem with self-evolving retrieval，独立 `evolvemem/retriever.py`/`multi_retriever.py`/`policy.py` 等 |
| `OmniSimpleMem/` | **另一方法**（多模态）| Extending SimpleMem to multimodal，独立 `omni_memory/` + `benchmarks/` |
| `MCP/` | **服务层** | MCP server，把 text 引擎包成对外服务 |
| `examples/`、`tests/`、`scripts/`、`docs/`、`fig/` | 辅助 | quickstart、vector_store 单测、docker 脚本、文档、图 |

### 1.2 README 第一手（`README.md`）

- README:132-138 明确：仓库是**统一 `simplemem` 包**，含三个「支柱」：
  SimpleMem（text，2026-01-05 论文 arXiv:2601.02553）、Omni-SimpleMem（多模态，v2.0）、
  EvolveMem（自演化检索，v3.0）；外加 cross（跨会话，2026-02-09）、MCP server（2026-01-14）。
- README:169-175 推荐通用入口：`from simplemem import SimpleMem`（auto-routing，text 模式自动选）。
- README:471-502「Reproduce Paper Results」：text 支柱用 `python test_locomo10.py`（LoCoMo），
  EvolveMem 用 `EvolveMem/run_benchmark.py locomo/membench`，OmniSimpleMem 用
  `OmniSimpleMem/benchmarks/locomo/run_locomo.py`——**每个支柱有各自的 benchmark runner**。

**判定**：仓库里有多个「支柱/产品」，但它们是**不同的方法/产品**（自演化、多模态、跨会话），
不是 SimpleMem text 核心算法的「版本变体」。SimpleMem text 核心算法只有一套
（`main.py` = `simplemem/text/system.py`，见 1.5）。

### 1.3 benchmark 专用评测目录：有，但调通用引擎

**`test_locomo10.py` 是 LoCoMo 专用评测**（自带数据 + 打分）：
- 数据烤进：test_locomo10.py:1036 默认 `--dataset test_ref/locomo10.json`。
- 打分自带：test_locomo10.py:15-20 import `bleu/meteor/rouge/bert_score`；
  test_locomo10.py:265-313 定义 `calculate_rouge/bleu/bert/meteor_scores`；
  test_locomo10.py:492 `calculate_metrics()` 聚合；可选 `--llm-judge`（test_locomo10.py:1044）。

**但引擎是通用产品**（关键证据）：
- test_locomo10.py:22 `from main import SimpleMemSystem` —— import 通用产品入口。
- test_locomo10.py:1054 `system = SimpleMemSystem(clear_db=True)` —— 用通用引擎 + config.py 默认参数。
- test_locomo10.py:877-890 评测流程：`contexts = self.system.hybrid_retriever.retrieve(...)`
  → `answer = self.system.answer_generator.generate_answer(question, contexts)` ——
  **官方评测本身就绕开 `ask()`，直接调 `hybrid_retriever.retrieve()` + `answer_generator.generate_answer()`**。

即 test_locomo10.py = 「通用引擎 SimpleMemSystem + LoCoMo 数据加载 + 打分壳」，
**不是独立 fork 的另一套算法**。这正是它与 MemoryOS `eval/`（独立 fork）的根本区别。

### 1.4 test_ref/test_advanced.py 是夹带的 A-Mem 代码（与 SimpleMem 无关）

- test_ref/test_advanced.py:1 `from memory_layer import LLMController, AgenticMemorySystem` ——
  这是 **A-Mem**（AgenticMemorySystem）的代码，不是 SimpleMem。
- test_ref/test_advanced.py:38 `advancedMemAgent` 用 `AgenticMemorySystem.add_note()` /
  `retrieve_memory()` —— A-Mem 接口。
- 判定：`test_ref/test_advanced.py` 是仓库作者做对比实验时夹带的**别的 method（A-Mem）的参考代码**，
  与 SimpleMem text 核心算法无关。adapter 完全没碰它（见第 2 节 import 证据）。

### 1.5 多版本核心算法一致性：只有一套 text 核心

实测 `diff main.py simplemem/text/system.py`：

```
12a13
>
```

**仅 1 行空行差异**——`main.py` 与 `simplemem/text/system.py` 是同一个 `SimpleMemSystem` 类，
都 import `simplemem.core.{memory_builder, hybrid_retriever, answer_generator,
vector_store, settings, models.memory_entry, utils.llm_client, utils.embedding}`。
`main.py` 是仓库根的便捷入口，`simplemem/text/system.py` 是包内正式版本，
`simplemem/router.py:221-226` 把它注册为 text backend（`module_path="simplemem.text.system",
class_name="SimpleMemSystem"`）。

EvolveMem / OmniSimpleMem / cross 各有独立的核心引擎目录（`EvolveMem/evolvemem/`、
`OmniSimpleMem/omni_memory/`、`cross/{orchestrator,storage_*}.py`），README 都明确
「Extending SimpleMem」——是 SimpleMem 的**扩展方法**，不是 text 核心的版本变体。
本审计只针对 text 核心（Phase 1 的 SimpleMem method）。

---

## 2. adapter 调的是通用产品接口还是 benchmark 专用实现（行号证据）

### 2.1 adapter 真实文件名

任务卡说「若实际文件名不是 simpleMem_adapter.py，先用 ls/grep 确认」。
实测 `ls src/memory_benchmark/methods/ | grep -i simple`：
**`simplemem_adapter.py`（全小写）**，28464 字节。报告全文以 `simplemem_adapter.py` 为准。

### 2.2 调用口径证据（adapter 调通用产品接口）

| adapter 行号 | 代码 | 证据含义 |
|:--|:--|:--|
| `simplemem_adapter.py:285` | `from main import SimpleMemSystem` | import **通用产品 text backend 入口**（= `simplemem.text.system.SimpleMemSystem`，见 1.5）|
| `simplemem_adapter.py:286` | `from simplemem.core.settings import settings as simplemem_settings` | import 通用产品 settings |
| `simplemem_adapter.py:197-201` | `system.add_dialogue(speaker=..., content=..., timestamp=...)` | 调通用产品注入 API（main.py:111）|
| `simplemem_adapter.py:219` | `system.finalize()` | 调通用产品 finalize（main.py:138）|
| `simplemem_adapter.py:227` | `system.hybrid_retriever.retrieve(query.query_text)` | 调通用产品检索 API（hybrid_retriever.py:58），**绕开 ask()** |
| `simplemem_adapter.py:279-331` | `_create_official_system()` 构造 `SimpleMemSystem(...)` + 注入 `simplemem_settings` | 用通用产品构造方式 |

**adapter 没有触碰的（证据：source_identity required_files 清单）**：
- `simplemem_adapter.py:657-669` 的 `required_files` 列的是：
  `main.py` + `simplemem/core/{memory_builder,hybrid_retriever,answer_generator,settings,
  utils/llm_client,utils/embedding,database/vector_store,models/memory_entry}.py` + `README.md` + `setup.py`。
- **不含** `test_locomo10.py` / `test_ref/` / `EvolveMem/` / `OmniSimpleMem/` / `cross/` / `MCP/`。
- import 链（adapter:285-286）也只引 `main` + `simplemem.core.settings`，无任何 benchmark 评测模块。

**判定**：adapter 调的是**通用产品接口**，不是 benchmark 专用实现。符合 ws02.5 README
裁决「一律用通用产品接口」。✅

---

## 3. SimpleMem 原生【注入】与【检索】接口（签名/粒度/官方参数/记忆层/top_k）

### 3.1 注入接口

**`SimpleMemSystem.add_dialogue(speaker, content, timestamp=None)`**
- 签名：`main.py:111-127`（= `simplemem/text/system.py:111-127`）
- 粒度：**per-dialogue（turn）**。每次调加一条 Dialogue 进 `memory_builder.dialogue_buffer`
  （memory_builder.py:52-66）；当 buffer 达 `window_size` 时自动触发 `process_window()`
  （memory_builder.py:65）→ LLM 压缩成 MemoryEntry → 存 vector_store。
- `finalize()`（main.py:138-143）：处理残余 buffer（`process_remaining()`，memory_builder.py:157-168）。
- 官方参数（settings.py:12-40）：
  - `WINDOW_SIZE=40`（滑窗大小）、`OVERLAP_SIZE=2`（重叠，step=window-overlap=38）
  - `ENABLE_PARALLEL_PROCESSING=True`、`MAX_PARALLEL_WORKERS=16`
  - `LLM_MODEL="gpt-4.1-mini"`、`EMBEDDING_MODEL="Qwen/Qwen3-Embedding-0.6B"`、`EMBEDDING_DIMENSION=1024`
- adapter 对齐：`consume_granularity="turn"`（simplemem_adapter.py:161）✓；
  `SimpleMemConfig`（simplemem_adapter.py:77-98）完整覆盖 window_size/overlap_size/
  enable_parallel_processing/max_workers 等官方参数，并在 `_create_official_system`
  （simplemem_adapter.py:294-316）逐项写入 `simplemem_settings`。

### 3.2 检索接口

**`HybridRetriever.retrieve(query, enable_reflection=None) -> List[MemoryEntry]`**
- 签名：`hybrid_retriever.py:58`
- 返回：**扁平 `List[MemoryEntry]`**（三视图检索结果合并去重，可选 reflection 补充）
- 内部流程（hybrid_retriever.py:75-127）：
  1. `_analyze_information_requirements`（planning，LLM 分析信息需求）
  2. `_generate_targeted_queries`（生成 1-4 个目标查询）
  3. 三视图并行检索：
     - **Semantic**（`_semantic_search`，hybrid_retriever.py:241-246）：向量相似度，top_k=`SEMANTIC_TOP_K`
     - **Lexical**（`_keyword_search`，hybrid_retriever.py:248-262）：BM25（Tantivy FTS），top_k=`KEYWORD_TOP_K`
     - **Symbolic**（`_structured_search`，hybrid_retriever.py:264-290）：metadata 过滤（persons/location/entities/timestamp_range），top_k=`STRUCTURED_TOP_K`
  4. `_merge_and_deduplicate_entries`（按 entry_id 去重，hybrid_retriever.py:409-421）
  5. 可选 `_retrieve_with_intelligent_reflection`（reflection 轮，max_reflection_rounds 默认 2）
- 官方 top_k（settings.py:28-30）：`SEMANTIC_TOP_K=25`、`KEYWORD_TOP_K=5`、`STRUCTURED_TOP_K=5`。
  adapter 对齐：`SimpleMemConfig.semantic/keyword/structured_top_k`（simplemem_adapter.py:86-88）→
  写入 settings（simplemem_adapter.py:312-314）。

### 3.3 retrieve 与答题的耦合点 + 能否剥离

**耦合点**：`SimpleMemSystem.ask(question)`（main.py:145-169）把检索与答题串起来：
```python
contexts = self.hybrid_retriever.retrieve(question)          # main.py:160
answer = self.answer_generator.generate_answer(question, contexts)  # main.py:163
```
`ask()` 是 retrieve + generate_answer 的便捷封装。

**能否剥离：能，且官方评测本身就这么做**：
- `hybrid_retriever` 是 `SimpleMemSystem` 的**独立属性**（main.py:94-102 实例化），
  `retrieve()` 是独立方法，返回纯 `List[MemoryEntry]`，**不调 answer LLM**。
- 官方评测 test_locomo10.py:877-890 就直接调 `system.hybrid_retriever.retrieve()` +
  `system.answer_generator.generate_answer()`，绕开 `ask()`。
- adapter 完全沿用此剥离方式：simplemem_adapter.py:224 注释「绕开 `ask()`，直接调用
  SimpleMem hybrid retriever」，simplemem_adapter.py:227 `system.hybrid_retriever.retrieve(...)`。

**判定**：剥离干净，无需自造检索算法。adapter 的 retrieve 忠于 SimpleMem 内部检索逻辑
（直接调官方 `HybridRetriever.retrieve`）。✅

> 附注（非阻塞，仅记录）：官方评测对 adversarial（category=5）问题用
> `enable_reflection=False`（test_locomo10.py:877），其余用默认。adapter:227 不传
> `enable_reflection`，全部用全局默认（`ENABLE_REFLECTION=True`）。这是 per-question
> 行为差异，不影响「接口保真」结论；若要严格对齐官方评测行为可后续按 category 区分。

---

## 4. formatted_memory 是否覆盖 SimpleMem 核心算法的全部记忆层

### 4.1 SimpleMem 的「记忆层」= 单一 MemoryEntry（无短/中/长多层）

**关键澄清**：SimpleMem 不像 MemoryOS 有短/中/长三层独立记忆存储。SimpleMem 只有
**一种记忆单元 `MemoryEntry`**，存在**单个 LanceDB table**（vector_store.py:53-72
`_init_table` 只建一个 table，schema 见 vector_store.py:55-65）。

`MemoryEntry`（memory_entry.py:13-67）的 6 个内容字段：
| 字段 | 索引视图 | 含义 |
|:--|:--|:--|
| `lossless_restatement` (str) | Semantic | 自包含事实句（消解共指+绝对时间）|
| `keywords` (List[str]) | Lexical | BM25 关键词 |
| `timestamp` (str?) | Symbolic | ISO 8601 时间 |
| `location` (str?) | Symbolic | 地点 |
| `persons` (List[str]) | Symbolic | 人名 |
| `entities` (List[str]) | Symbolic | 实体（公司/产品等）|
| `topic` (str?) | Symbolic | 主题 |

「三视图」（Semantic/Lexical/Symbolic）是**同一 MemoryEntry 的三种检索索引方式**
（vector_store.py:1-7 docstring 明示），不是三个独立记忆层。

**记忆层覆盖判定**：`hybrid_retriever.retrieve()` 返回的是三视图合并去重后的
`List[MemoryEntry]`（全部命中），**无漏记忆层**——SimpleMem 本来就只有一层。
✅

### 4.2 adapter formatted_memory 的字段覆盖（⚠️ 部分缺失）

adapter 有两个格式化函数：

| 函数 | 位置 | 取的字段 | 用途 |
|:--|:--|:--|:--|
| `_format_simplemem_memory` | simplemem_adapter.py:467-478 | **仅 `lossless_restatement` + `timestamp`（2/6）** | 拼 `formatted_memory`（RetrievalResult.formatted_memory）|
| `_format_simplemem_contexts` | simplemem_adapter.py:481-506 | **全部 6 字段**（Content/Time/Location/Persons/Related Entities/Topic）| 拼 `context_str`，放进 `prompt_messages` user prompt |

`_format_simplemem_memory`（simplemem_adapter.py:467-478）实际逻辑：
```python
for context in contexts:
    timestamp = _optional_context_text(context, "timestamp") or "unknown"
    lines.append(f"[{timestamp}] {_required_context_text(context, 'lossless_restatement')}")
```
**丢了 `location` / `persons` / `entities` / `topic` 4 个 Symbolic 层字段。**

对比官方 `AnswerGenerator._format_contexts`（answer_generator.py:85-111）：取全部 6 字段。
adapter 的 `_format_simplemem_contexts`（simplemem_adapter.py:481-506）逐行复刻官方，**完整**。

**影响分析**：
- adapter 当前 `prompt_track="native"`（simplemem_adapter.py:248），框架走
  `prompt_messages`（含完整 6 字段的 `_format_simplemem_contexts`）→ **native 口径下记忆完整**。
- 但若框架切到 **unified 口径**（用框架自带 answer prompt + `formatted_memory`），
  `formatted_memory` 只有 2 字段 → **会丢 Symbolic 层 4 字段信息**，answer LLM 看不到
  location/persons/entities/topic 等结构化上下文。

**判定**：
- 记忆层（MemoryEntry 列表）完整无漏 ✅
- formatted_memory 字段不完整 ⚠️（缺 Symbolic 层 4 字段），unified 口径下有信息损失风险

> 这是字段级缺失，不是记忆层缺失。按 AGENTS.md「运行主线」unified 口径（用框架自带
> answer prompt + formatted_memory）的要求，建议把 `_format_simplemem_memory` 补全为
> 6 字段格式（或直接复用 `_format_simplemem_contexts` 的输出）。**此为改进建议，非本次
> 只读审计的修改范围**——记录交架构师裁定。

---

## 5. 建议：版本/接口选择 + 迁移成本

### 5.1 版本/接口建议

**继续用 `main.SimpleMemSystem`（= `simplemem.text.system.SimpleMemSystem`，通用产品 text backend）。**

理由：
1. `main.py` 与 `simplemem/text/system.py` 是同一个类（1.5 节 diff 仅 1 空行），
   都是通用产品 text backend。adapter 已用此入口（simplemem_adapter.py:285）。
2. 官方评测 test_locomo10.py 也用此入口（test_locomo10.py:22, 1054）——
   「通用产品」与「官方评测所用引擎」是同一份，无主场优势问题。
3. README 推荐的 `from simplemem import SimpleMem`（router.AutoMemory）只是
   auto-routing 包装器，text 模式下转发给 `simplemem.text.system.SimpleMemSystem`
   （router.py:312-332）。adapter 直接用 `main.SimpleMemSystem` 等价且更直接
   （跳过 router，少一层间接，便于 isolation 隔离与 LLM usage 观测插桩）。
4. 不用 `cross/`（跨会话产品，不同方法）、`EvolveMem/`（自演化，不同方法）、
   `OmniSimpleMem/`（多模态，不同方法）、`MCP/`（服务层，进程外往返增复杂度）——
   这些都不是 SimpleMem text 核心，Phase 1 的 SimpleMem method 指 text 核心。

### 5.2 迁移成本：零迁移

**adapter 已在通用产品接口上，无需从 benchmark 专用迁回。**

与 MemoryOS 的对比（ws02.5 README 的 MemoryOS 版本裁定）：
- MemoryOS：adapter 原包 `eval/`（LoCoMo 主场 fork，与 pypi 是两套独立代码）→
  需 diff 两者算法差异、迁到 pypi、重新对齐 add/retrieve 签名 → **有迁移工程**。
- SimpleMem：adapter 已包 `main.SimpleMemSystem`（通用产品），test_locomo10.py 也用它
  → **无 fork 问题，无迁移**。

唯一可做的「对齐」是参数对齐（adapter 已做：simplemem_adapter.py:294-316 把
`SimpleMemConfig` 逐项写入 `simplemem_settings`，覆盖 WINDOW_SIZE/OVERLAP_SIZE/
三 top_k/planning/reflection/parallel 全部官方参数）。

### 5.3 非阻塞改进点（交架构师，不在本次只读审计范围）

1. **formatted_memory 字段补全**（第 4 节）：把 `_format_simplemem_memory` 补全为 6 字段，
   避免 unified 口径丢 Symbolic 层信息。
2. **reflection per-question 对齐**（3.3 附注）：若要严格复刻官方评测，按 category=5
   关 reflection；否则保持现状（全部默认 reflection）也可接受。

---

## 附：证据索引（文件:行号 速查）

### 第三方仓库（`third_party/methods/SimpleMem/`）
- `README.md:132-138` 三支柱定义；`README.md:169-175` 通用入口；`README.md:471-502` 各支柱 benchmark runner
- `main.py:16-24` SimpleMemSystem 类与三阶段 pipeline；`main.py:111-127` add_dialogue；`main.py:138-143` finalize；`main.py:145-169` ask()（retrieve+generate_answer 耦合）；`main.py:94-106` hybrid_retriever/answer_generator 实例化
- `simplemem/text/system.py` = `main.py`（diff 仅 1 空行）
- `simplemem/__init__.py:21` `from simplemem.router import AutoMemory as SimpleMem`
- `simplemem/router.py:221-226` text backend 注册；`router.py:312-332` AutoMemory 转发 text API
- `simplemem/core/memory_entry.py:13-67` MemoryEntry（6 字段，单一记忆单元）
- `simplemem/core/memory_builder.py:52-66` add_dialogue/buffer；`memory_builder.py:132-155` process_window；`memory_builder.py:157-168` process_remaining
- `simplemem/core/hybrid_retriever.py:58-73` retrieve 签名；`hybrid_retriever.py:75-127` planning+三视图+reflection 流程；`hybrid_retriever.py:241-290` 三视图检索；`hybrid_retriever.py:409-421` 去重
- `simplemem/core/answer_generator.py:22-83` generate_answer；`answer_generator.py:85-111` _format_contexts（6 字段）；`answer_generator.py:113-153` _build_answer_prompt
- `simplemem/core/database/vector_store.py:1-7` 三视图索引 docstring；`vector_store.py:53-72` 单 table schema
- `simplemem/core/settings.py:12-40` 官方默认参数
- `test_locomo10.py:15-20` 打分 import；`test_locomo10.py:22` `from main import SimpleMemSystem`；`test_locomo10.py:265-313` 打分函数；`test_locomo10.py:492` calculate_metrics；`test_locomo10.py:877-890` 评测绕开 ask() 直接调 hybrid_retriever+answer_generator；`test_locomo10.py:1036` 默认数据 test_ref/locomo10.json；`test_locomo10.py:1054` `SimpleMemSystem(clear_db=True)`
- `test_ref/test_advanced.py:1` `from memory_layer import AgenticMemorySystem`（夹带的 A-Mem 代码）

### 我们的 adapter（`src/memory_benchmark/methods/simplemem_adapter.py`）
- `:161` consume_granularity="turn"
- `:197-201` ingest 调 add_dialogue
- `:219` end_conversation 调 finalize
- `:223-252` retrieve 实现（绕开 ask，调 hybrid_retriever.retrieve）
- `:227` `system.hybrid_retriever.retrieve(query.query_text)`
- `:248` prompt_track="native"
- `:279-331` _create_official_system（通用产品构造 + 参数注入）
- `:285-286` import main.SimpleMemSystem + simplemem.core.settings
- `:294-316` 把 SimpleMemConfig 写入 simplemem_settings（参数对齐）
- `:467-478` _format_simplemem_memory（仅 2/6 字段，formatted_memory）
- `:481-506` _format_simplemem_contexts（6 字段，复刻官方 _format_contexts，进 prompt_messages）
- `:509-548` _build_simplemem_answer_prompt（复刻官方 _build_answer_prompt）
- `:657-669` source_identity required_files（仅 main+core，无 benchmark 评测模块）
