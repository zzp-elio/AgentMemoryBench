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

- 2026-07-08（架构师 Opus 4.8 建档）：记录 MemoryOS `eval/` vs `memoryos-pypi`
  第一手发现 + 全 method 审计裁决。**下一步**：逐 method 审计（可先抽查
  MemoryOS 出样例，再派 actor 按上方 (a)-(e) 清单逐个核 + 写接口文档）。尚未
  开工审计。

## 任务清单

- [x] 架构师建档 + 裁决（2026-07-08）
- [ ] 逐 method 接口审计（Mem0/MemoryOS/A-Mem/LightMem/SimpleMem）
- [ ] 产出 method 接口文档（注入 + 检索）
- [ ] 对用了 benchmark 专用实现的 adapter 评估并迁移到通用接口
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
