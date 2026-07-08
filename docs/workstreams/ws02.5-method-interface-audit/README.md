---
id: ws02.5
parent: ws02
status: open（P0，5×5 真实 smoke 的前置门；2026-07-08 用户提出）
created: 2026-07-08
---
# ws02.5 Method 接口保真审计（5×5 smoke 前置门）

## 为什么有这个 workstream（第一手发现，别只当 MemoryOS 个例）

2026-07-08 用户提出核心问题：**method adapter 注入/检索记忆时，用的是 method
官方仓库里的哪种接口？** 很多 method 仓库同时有两类：

- **通用产品接口**（`pip install` 得到的那套，benchmark 无关）——例：
  `MemoryOS-main/memoryos-pypi/`（`memoryos.py`/`retriever.py`/`updater.py`）。
- **某 benchmark 专用的评测实现**（为跑某篇论文的某 benchmark 写的独立副本，
  常自带该 benchmark 数据 + 打分）——例：`MemoryOS-main/eval/`
  （`main_loco_parse.py` + 烤进的 `locomo10.json` + `evalution_loco.py`，是
  LoCoMo 专用引擎副本，与 pypi 是**两套独立代码**，非同一份）。

**第一手证据（MemoryOS，一个例子而已）**：现有
`src/memory_benchmark/methods/memoryos_adapter.py:3` docstring 自述"包装 MemoryOS
官方 `eval/` 目录中的 LoCoMo 评测实现"。即我们现在用的是 **LoCoMo 主场版引擎**，
不是通用 pypi。**用户明确：不要过拟合 MemoryOS——5 个（未来 10 个）method 全部
都要查**，其他 method 仓库有没有类似的 benchmark 专用目录尚未核实。

## 裁决（架构师，用户认可）：一律用通用产品接口

**所有 method 跨全部 benchmark 统一用通用产品接口注入/检索，不用任何 benchmark
专用评测实现。** 三条理由：

1. **公平/可比**：benchmark 专用实现可能带该 benchmark 的调参/prompt，用它 →
   该 method 在该 benchmark 有主场优势，分数与它在别的 benchmark 上不可比。
   跨 benchmark 比较必须同一个接口跑遍 5 个 benchmark。
2. **代表性**：通用产品是真实用户 `pip install` 得到的东西，才代表"这个 method"
   的真实水平。
3. **benchmark 专用目录恰是我们框架要替换的部分**：它自带数据加载 + 打分，
   而数据加载和打分是**我们框架的活**。benchmark 专用目录只作**只读参考**
   （看作者官方用法/参数：top_k、各记忆层容量、注入格式），然后把通用引擎按
   官方参数配好。

## 审计范围（每个 method 逐项，产出下方接口文档）

对 Mem0 / MemoryOS / A-Mem / LightMem / SimpleMem（未来 +MemOS/Letta/Cognee/
LangMem/Supermemory）逐个核：

- **(a) 接口保真**：adapter 现在调的是通用产品接口还是 benchmark 专用实现？
  仓库里有没有 benchmark 专用目录（如 `eval/`、`experiments/`）？若 adapter 用了
  专用实现 → 评估迁移成本（diff 专用 vs 通用引擎：是"算法不同的 fork"要重写，
  还是"同引擎不同配置"改指向+对齐参数即可）。
- **(b) 注入保真**：ingest 是否按 method 官方用法注入（粒度、格式、是否触发
  method 的记忆构建/更新流程）。
- **(c) 检索完整**：retrieve 回来的 `formatted_memory` 是否覆盖 method 核心
  算法的**全部记忆层**——例 MemoryOS 短期+中期+长期(个性化)都要回；Mem0 的
  记忆；A-Mem 的 note+link；LightMem；SimpleMem 窗口。**不完整 = smoke 跑通但
  产出垃圾 = 成本表和全量全失真**。
- **(d) 原生无 retrieve 接口的情况**：确有 add-only 的 method 原生无独立 retrieve
  API，此时 adapter 层必须封装出一个返回完整 `formatted_memory` 的 retrieve，
  且封装忠于 method 内部检索逻辑（不自造检索算法）。
- **(e) formatted_memory 落盘**：每次检索内容记进 artifact（conversation-QA
  路径已有 `prediction.py:2624`，须确认 operation_level 路径也记、且完整）。

## 交付物：Method 接口文档（注入 + 检索，5→10）

产出一份 `docs/reference/method-interface-inventory.md`（或扩充既有同名文件），
每个 method 一节，含：注入 API（函数签名 + 粒度 + 官方参数）、检索 API（函数
签名 + 返回的记忆层 + top_k）、`formatted_memory` 拼装口径、通用 vs 专用接口
裁定与证据行号。这是"下一任架构师/actor 快速上手"的关键文档。

## 与 5×5 smoke 的关系（门）

**这是 5×5 真实 smoke 的前置门**：接口不保真、记忆不完整时跑 smoke 是浪费预算
（数字不可信）。顺序：5 个 adapter 完工 → 本审计 → 5×5 smoke → 成本表。
不阻塞 fake 全链路（fake 不烧 API，可继续）。

## 当前断点

- 2026-07-08（架构师 Opus 4.8 验收 P1 LightMem）：**通过**。本机复跑
  `uv run pytest -q -m "not api"` = **892 passed, 0 failed**。**第一手核实迁移
  忠实**：官方 `lightmem.py` `retrieve()`（:644-707）内部就是
  `text_embedder.embed(query)` → `embedding_retriever.search(return_full=True)`
  →（仅当传 `boundmem_tags` 才 `filter_by_tags`，默认不过滤）→ 格式化成
  `f"{time_stamp} {weekday} {memory}"`。所以 adapter 直接调 `search(return_full=
  True)`（:1035）① 用的是同一个官方 search 组件；② 默认参数下无隐藏过滤被跳过；
  ③ answer prompt 用 `_format_lightmem_memory_as_official_retrieve`（:1555）还原
  官方 `{ts} {wd} {mem}` 格式（对齐官方 :701），不偏离。两路径统一 list[dict]
  （F1 解决），删自复刻 `_cosine_similarity`。**Step1 等价 gate 我复核结构成立**
  （retrieve==search 包一层），数值等价采信 actor 记录的详细 diff（未独立重演
  cosine 数值）。**残留（非阻塞）**：若将来用到 `boundmem_tags`，adapter 须补
  `filter_by_tags`（当前 benchmark 不用）。**下一步**：MemoryOS eval→pypi（架构师
  写 plan 中）；接口文档汇总；P2 A-Mem 文档留痕。
- 2026-07-08（actor workbuddy+GLM5.2，完成 P1 迁移）：LightMem 统一 retrieve。
  Step1 gate 通过（自复刻 `_retrieve_locomo_memories` get_all+手算cosine vs
  官方 `VectorRetriever.retrieve` retrievers.py:111-132 逐行等价：候选集同
  qdrant.get_all、cosine 公式数学一致、排序截断一致，无主场优势）；Step2
  `_retrieve_locomo_memories`→`_retrieve_with_payload` 改调官方
  `embedding_retriever.search(return_full=True)` 拿带 payload 结果，retrieve()
  LongMemEval/LoCoMo 两路径统一返回 list[dict]（F1 解决），LongMemEval answer
  prompt 用新增 `_format_lightmem_memory_as_official_retrieve` 还原官方
  `'{ts} {wd} {mem}'` 格式（不偏离 run_lightmem_gpt.py:186），删
  `_cosine_similarity`，retrieval_profile 统一 `lightmemory_retrieve`。focused
  lightmem 33 passed，全量 892 passed（基线不跌破）。commit `63ccba2`。
  **下一步**：架构师复跑验收；P1 MemoryOS eval→pypi 待派。
- 2026-07-08（架构师 Opus 4.8 验收 P0）：**通过**。本机复跑 `uv run pytest -q
  -m "not api"` = **892 passed, 0 failed**（与 actor 一致）；第一手核对改动忠实：
  官方 `answer_generator.py:85-111` `_format_contexts` 确为 6 字段
  （Content/Time/Location/Persons/Related Entities/Topic）、**不含 keywords**，
  adapter `_format_simplemem_contexts` 逐行等价，actor 未画蛇添足加 keywords、
  且 dedup（unified 复用 native formatter，两口径一致）。**下一步**：LightMem
  P1（含 Step1 等价 gate）+ MemoryOS eval→pypi（架构师写 plan 中）。
- 2026-07-08（actor **WorkBuddy/GLM-5.2**，完成 P0 修复；**身份更正**：此前 actor
  自标"Claude Sonnet"有误——实际由 GLM-5.2 驱动、产品层 WorkBuddy，架构师照搬其
  自标未核实，一并纠正。SimpleMem 审计 + P0 写任务均为同一 WorkBuddy/GLM-5.2）：
  SimpleMem F1——
  `_format_simplemem_memory` 改为复用 `_format_simplemem_contexts`，覆盖官方
  `AnswerGenerator._format_contexts` 全部 6 字段（lossless_restatement+timestamp
  +location+persons+entities+topic），unified/native 同口径不丢 Symbolic 层；
  改 `test_simplemem_adapter.py` 旧格式断言 + 新增 Symbolic 字段覆盖测试。
  focused 13 passed，全量 892 passed（基线 891 +1）。commit `3e177c3`。**下一步**：
  架构师复跑验收；P1 MemoryOS eval→pypi / P1 LightMem 统一 retrieve 待派。
- 2026-07-08（架构师 Opus 4.8 建档）：记录 MemoryOS `eval/` vs `memoryos-pypi`
  第一手发现 + 全 method 审计裁决。**下一步**：逐 method 审计（可先抽查
  MemoryOS 出样例，再派 actor 按上方 (a)-(e) 清单逐个核 + 写接口文档）。尚未
  开工审计。

## 任务清单

- [x] 架构师建档 + 裁决（2026-07-08）
- [x] 逐 method 接口审计（2026-07-08，Mem0/A-Mem/LightMem/SimpleMem by workbuddy+GLM5.2；MemoryOS by 架构师）+ 架构师验收裁定（见上表）
- [ ] 产出 method 接口文档（注入 + 检索）— 可由 4 份 audit-*.md 汇总
- [ ] 迁移/修复（写任务串行）：[x] P0 SimpleMem 补字段（2026-07-08，commit 3e177c3）/ [ ] P1 MemoryOS eval→pypi / [x] P1 LightMem 统一 retrieve（2026-07-08，commit 63ccba2）/ [ ] P2 A-Mem 文档留痕
- [ ] formatted_memory 全路径完整落盘核对

## MemoryOS 版本裁定（架构师第一手，2026-07-08）

第一手对比 `third_party/methods/MemoryOS-main/` 各版本目录 + README：

- **核心算法在 pypi 与 chromadb 之间一致**：两者核心文件完全相同（`short_term.py`
  / `mid_term.py` / `long_term.py` / `memoryos.py` / `retriever.py` / `updater.py`
  / `prompts.py`），`memoryos-chromadb` 只多一个 `storage_provider.py`（把存储
  后端换成 ChromaDB 向量库）。**同算法、不同存储后端。**
- **mcp 不是另一套引擎**：`memoryos-mcp/` 只有 `server_new.py`——把引擎包成
  MCP Server 对外暴露的**服务层**，供 agent 客户端调用。
- **eval/ 是第三个变体**（研究评测代码，自带 LoCoMo 数据），我们现在的 adapter
  包的就是它（LoCoMo 主场版，本 workstream 要迁走）。

**裁定：用 `memoryos-pypi`（通用产品），不用 mcp / chromadb / eval。四条理由**
（此裁定与用户初步倾向的 chromadb/mcp 不同，架构师据第一手给出）：

1. **mcp 排除**：server/协议层，为 agent 客户端集成而设；我们框架在进程内把
   method 当 Python 库调，用 MCP 要起服务 + 协议往返，纯增复杂度、搅乱隔离/resume。
2. **chromadb 排除（留作后备）**：同算法但多 ChromaDB 依赖 + 需跑向量库；而我们
   每个 conversation 是**小的物理隔离存储**，pypi 的文件式存储（短/中/长期 JSON
   + 内存 FAISS）更适合——**每 conversation 一个目录 = 最简物理隔离 + 删目录即
   clean-retry**。ChromaDB 的可扩展持久向量库是生产规模优点，对我们的小隔离空间
   是过度设计。将来若要逻辑隔离的 scoped-delete，再回头考虑 chromadb。
3. **pypi 最具代表性**：`pip install memoryos` 得到的就是它，符合本 workstream
   "用通用产品接口"的公平原则。
4. **依赖最少、最可复现。**

**迁移前必做（写任务、串行占据，非本裁定范围）**：pypi 引擎与现 adapter 包的
eval/ 引擎是两套代码——先 diff 两者算法差异 + 确认 pypi `Memoryos` 的 add/
retrieve 签名（进接口文档）。本裁定只定"用哪个版本"，迁移工程另派。

## 四 method 审计验收 + 架构师逐条裁定（2026-07-08）

actor = workbuddy+GLM5.2（四开会话并行）。**架构师逐份回第一手核对引用行号**
（不因详尽就信）。审计原文见同目录 `audit-<method>.md`。

| method | 审计结论 | 架构师验收 | 裁定 |
|---|---|---|---|
| **Mem0** | 通用 `Memory` 类，纯 search，零迁移 | 结论对（adapter 用 `search()` :876/882 + `add()`）；**但 actor 论据"Memory 无 answer 方法"有误**——Memory **有** `chat()`（`mem0-main/.../main.py:1791`），只是 adapter 没用它 | **不动**（合规） |
| **LightMem** | LoCoMo 路径自复刻 benchmark 专用检索，LongMemEval 用官方 retrieve | 属实（adapter:1018 docstring 自认"复刻 `search_locomo.py` combined vector search"） | **迁移**：统一走官方 `retrieve()`（扩展其返回 payload 以支持 speaker 分组），消除 benchmark 专用借用 + 解决 F1（两路径返回类型不一）。迁移前先 diff 确认 actor 声称的"逐行等价"（等价=清理；不等价=纠错） |
| **A-Mem** | 用论文复现包 `RobustAgenticMemorySystem`，非产品库 `A-mem-sys` | 属实（`A-mem/README:3-5` 明写"本仓库为复现论文，用请去 A-mem-sys"）；**关键区别**：复现引擎 **benchmark 无关**（无 LoCoMo 调优，adapter 没碰 LoCoMo 专用文件）→ **无 MemoryOS 那种主场优势问题** | **暂保持现状**：复现引擎忠于 A-Mem 算法、无公平问题、迁 A-mem-sys 成本中高（换引擎 + ChromaDB 依赖）。文档记明"用 A-Mem 论文复现包"；低优先 follow-up：核 A-mem-sys 产品算法是否有别 |
| **SimpleMem** | 接口合规；F1：formatted_memory 只拼 2/6 字段 | F1 属实（`_format_simplemem_memory` 只取 `timestamp`+`lossless_restatement`，丢 Symbolic 层 location/persons/entities/topic） | **修**：unified 主线口径下会丢记忆 → formatted_memory 补全 6 字段（小改，高优先） |
| **MemoryOS** | （架构师自审，见上节） | — | **迁移** eval/ → pypi |

**迁移/修复清单（写任务，串行占据；按优先级）**：

- **P0** SimpleMem：formatted_memory 补 4 个 Symbolic 字段（unified 主线必需，小改）。
- **P1** MemoryOS：eval/ → pypi（大，先 diff 两引擎）。
- **P1** LightMem：LoCoMo 统一走官方 retrieve（先验"逐行等价"）+ 统一两路径返回类型（F1）。
- **P2** A-Mem：保持现状 + 文档留痕；低优先核 A-mem-sys 产品。
- Mem0：不动。

**接口保真总账**：5 个 method 中 Mem0 一开始就对；SimpleMem 接口对但 formatted_memory
不全；LightMem 一条路径有 benchmark 专用借用；A-Mem 用复现包但无公平问题；
MemoryOS 用 LoCoMo 主场副本要迁。**只有 MemoryOS 是真"主场优势"问题**，其余是
不同程度的清理/补全。

**Actor 表现评估（workbuddy+GLM5.2）**：审计能力强——详尽、行号翔实、能区分
微妙点（A-Mem 复现引擎 benchmark 无关 vs MemoryOS eval/ 耦合；SimpleMem 三视图
≠ 三记忆层）、抓出真 gap（SimpleMem F1、LightMem 偏离）。**扣分项**：Mem0"无
answer 方法"论据说过头（结论对、证据错）。**结论**：可承接写任务（如迁移工程），
但与所有 actor 一样需架构师严格 review。
