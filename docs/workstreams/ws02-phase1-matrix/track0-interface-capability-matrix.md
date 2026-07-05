# Track 0：接口能力双向矩阵（5 benchmark × 10 method）

更新日期：2026-07-06。作者：Claude（架构师）。
输入：5 张 benchmark 调研卡片 + 10 张 method 机制卡片（含 4 个已接入 method 的
形变记录）+ 五框架对比卡片。本文是最终协议 spec 的直接依据；所有条目可回溯到
对应卡片的 文件:行号 证据。

## 1. Benchmark 侧需求表

| | 自然层级 | 官方喂入粒度 | 必需边界/字段 | 查询形态 | 特殊接口需求 | 规模/成本量级 |
| --- | --- | --- | --- | --- | --- | --- |
| **LoCoMo** | conv→session→turn→QA | 逐 turn（各 method 官方 eval 一致：Mem0 CHUNK=1、A-Mem note、LightMem turn 批、MemoryOS QA-pair） | session_date_time 随 turn；dia_id；speaker；图片 caption | 每题 question+category（cat2 加日期提示） | 可选 RAG recall（dia_id 对齐）；cat5 需 reader-only 特殊 prompt（当前跳过） | 10 conv（369-689 turns）×1540 题 |
| **LongMemEval** | instance→haystack session→turn→1 QA | user+assistant pair（LightMem/Mem0 官方一致） | session date；**question_time 必须进 reader**；instance 级隔离 | 单题 + question_time；含 abstention | retrieval recall 需 session/turn id（Phase 1 不做） | 500 instance；S≈115k tokens/条，M≈1.5M/条 |
| **HaluMem** | **uuid-user→sessions**→turns + memory_points + QA | session dialogue（message list + session start_time） | **user 级跨 session 连续累积（不重置）**；session_id；reset_user | 三种 query：QA(top_k=20)、update（**gold memory 文本作 query**，top_k=10）、extraction | **session 级新增记忆必须可取**（get_dialogue_memory 等价物）；operation-level runner | Medium 1387 sessions/60k turns/3467 QA + 大量 judge |
| **BEAM** | conv→(plan)→batch→turn→message + 20 题 | 整 conv 建一次上下文/索引，20 题复用 | chat_size/batch/turn/message index（10M 加 plan 层）保留可回溯 | 每 conv 20 probing 题（10 能力类） | rubric judge、event-ordering metric（评分侧）；1M/10M 需 chunked/流式 ingest | 100 conv/2000 题；10M 均 7757 turns |
| **MemBench** | trajectory→message step→1 选择题 | 逐 step store（dict 或 str）；trajectory 前 reset | **tid 隔离**；1-based step_id；QA time | 选择题 question+time+choices | **retrieved_source_step_ids**（evidence recall）；capacity/efficiency 额外模式 | 0-10k 档 3400 traj/144k steps；100k 档 860 traj/308k steps |

## 2. Method 侧能力表

| | 原生 ingest 单位 | 需要的边界信号 | 检索 provenance | 写入完成判据 | 最舒服消费粒度 |
| --- | --- | --- | --- | --- | --- |
| **Mem0** | message list + namespace（官方 LoCoMo=turn、LME=pair） | namespace；无 flush | id/score/created_at/metadata（丰富，当前 adapter 裁掉了） | 同步，add 返回即可检索 | turn/pair |
| **MemoryOS** | QA pair（user_input, agent_response, ts） | STM 容量触发迁移；speaker 配对 | page/knowledge/profile 多路；**检索会改 heat（非只读）** | 同步 | pair |
| **A-Mem** | 单条 note（content, time） | 无 flush；持久化是 runner 边界 | index/timestamp/keywords；无直接 id/score | 同步（含多次写入 LLM） | turn/note |
| **LightMem** | turn/pair 批 + **末批 force flush** | **末批信号必需**；LoCoMo 还需 post-build offline update | Qdrant id/score/payload 丰富 | flush + offline update 后才可检索 | pair 批 + finalize + post-build 钩子 |
| **SimpleMem** | dialogue turn（speaker, content, ts） | **finalize() 必需**（窗口残留） | entry_id；无 score；LLM 压缩难反查 source（需 sidecar） | finalize 返回 | turn + finalize |
| **LangMem** | messages 批 → background manager 抽取 | namespace；无 flush | namespace/key/score/value/时间 | put/invoke 返回 | message 批（R2：走 store/manager，不走 agent） |
| **Supermemory** | raw document/session 串 + containerTag/customId | **异步管线：必须轮询 document+memory 双 done** | memory/chunk/similarity/docId | **异步**，awaitIndexing 等价物必需 | session/conversation 批 + 完成轮询 |
| **MemOS** | messages list（role/content/chat_time）+ user/session/cube | user_id+session_id 必填；tree 模式有 reorganizer 待 drain | memory_id/type/cube_id/sources（tree）；general 无 score | general 同步；tree 需等待 | session/messages 批 |
| **Cognee** | 自由文本/document → dataset | **cognify 是显式第二阶段**（等价 finalize） | chunks + source metadata（需 verbose 模式） | cognify blocking 返回 | document/dataset + finalize |
| **Letta** | archival passage（text/tags/created_at）per agent | agent_id 隔离；direct path 无 flush | id/timestamp/content/tags/relevance | 同步（direct path；R2 已裁定不走 agent loop） | fact/passage（session 摘要或逐 turn 文本均可） |

## 3. 交叉分析（六个决定性发现）

### 3.1 最大公约数 = 带时间戳的顺序 turn/message 事件流

benchmark 侧五个全部可无损展开为顺序 turn/message 流（LoCoMo turn、LME pair、
HaluMem session 内 turns、BEAM message、MemBench step）。method 侧 6 个原生消费
细粒度（Mem0/A-Mem/LightMem/SimpleMem/MemoryOS/LangMem），4 个偏批量
（Supermemory/MemOS/Cognee/Letta）——但**批量型都能由框架把 turn 流缓冲聚合后
投递**（拼成 session 文本/document）；反方向（把整段 conversation 拆细）正是
现在四个 adapter 形变记录里的全部痛苦来源（Mem0 自拆 turn/pair、LightMem 自造
末批信号、MemoryOS 自配 QA pair、A-Mem 双层循环）。
**结论：细粒度事件为 canonical 流、框架向上聚合，方向确认。**

### 3.2 用户的"多粒度并存"猜想被证实为最优解

method 声明消费粒度（turn / pair / session 批 / conversation 批），框架按声明
聚合投递——这正是"1-2 个中间层"的第二层。第一层是 benchmark adapter 把原始
数据规范化为事件流（已有）。

### 3.3 边界钩子需要三层，且 end_session 必须能"交回记忆"

- `end_session`：HaluMem 的 Memory Extraction 评测**要求拿到"本 session 新增的
  记忆"**——所以该钩子不能只是通知，需要允许返回 session 新增 memories（或提供
  等价查询）。MemoryOS STM 迁移、LoCoMo session 时间边界也挂这里。
- `end_conversation`（写入完成屏障）：SimpleMem finalize、LightMem 末批 flush +
  offline update、Cognee cognify、Supermemory 轮询 done、MemBench/BEAM 的
  per-unit 构建边界，全部落位。R3（返回即可检索）覆盖同步/阶段/异步三型。
- `prepare/reset`：MemBench 每 trajectory reset、HaluMem reset_user。

### 3.4 隔离单位 ≠ conversation（重要修正）

三种隔离单位并存：conversation/instance（LoCoMo/LME/BEAM）、trajectory-tid
（MemBench）、**uuid-user 跨 session 连续累积（HaluMem——绝不能按 session 或
conversation 重置）**。协议的 isolation_key 必须由 benchmark adapter 声明
（= agent-memory-benchmark 的 unit_ids 设计），不能硬编码为 conversation_id。

### 3.5 检索：query 不总是"问题"，输出需要结构化条目

- HaluMem update 评测用 **gold memory 文本**作 query（runner 特殊 flow，query
  内容由 evaluator 侧提供但走同一 retrieve 通道）→ retrieve 的输入应是通用
  RetrievalQuery（含 query_text、question_time、top_k、purpose），Question 只是
  其一种来源。
- 输出双轨已定（formatted_memory + 可选 prompt_messages）；此外需要可选的
  **结构化条目列表**（id/score/timestamp/source ids）支撑 evidence recall
  （MemBench step_id、LME session id、LoCoMo dia_id）。provenance 能力
  method 间差异大（A-Mem/SimpleMem 弱，其余强）→ 作为可选能力声明，
  不支持则对应 metric 标 unsupported，不硬造。
- top_k 必须 per-benchmark-profile 可配（HaluMem update=10 / QA=20 的先例）。

### 3.6 三个跨领域硬约束再确认

question_time 是一等公民字段（LME/MemBench/BEAM 都要）；MemoryOS 检索有副作用
（改 heat）→ "检索只读"不能作为协议假设，resume 语义要考虑；BEAM 1M/10M 的
超长 ingest 需要框架内部 chunked/流式支持（对外接口不变）。

## 4. 给最终协议 spec 的结论清单

1. 写入主协议：框架驱动的 turn/message 级事件流 + method 声明消费粒度、框架
   聚合投递（턴/pair/session 批/conversation 批四档）。
2. 生命周期钩子：`prepare(unit)` / `end_session(...)→可返回新增记忆` /
   `end_conversation(...)＝完成屏障（R3）`。
3. 隔离：显式 isolation_key，由 benchmark adapter 按其隔离单位声明
   （conversation / tid / uuid-user）。
4. 检索：`retrieve(RetrievalQuery) → RetrievalResult{formatted_memory 必需,
   prompt_messages 可选（native 口径）, items 可选（provenance/evidence recall）}`。
5. answer 双口径（unified / method-native）与双 profile（official / custom）
   按 2026-07-06 决策执行；R1（method 不作答）不变。
6. 扩展性落点：多模态 = 事件 content 结构化（文本+图片 caption 已在 LoCoMo
   出现）；agentic task family（MemoryArena 类）= 独立 task family，不塞进本
   协议；HaluMem operation-level 与 MemBench capacity 是 runner 层新 flow，
   协议本身已留够钩子。

## 5. 未确认项

- MemoryOS 检索副作用（heat 变化）在"同一 run 内重复检索"时对结果的影响
  （resume 后重答问题是否改变 method 状态）——最终 spec 需给出口径。
- SimpleMem/A-Mem 的 provenance 弱能力是否值得 sidecar 补偿（MemoryData 的
  source map 先例），或直接标 unsupported——按 benchmark 需求逐个决定。
- BEAM 10M split 的 plan 层结构与 MemoryAgentBench chunk-stream（未进 Phase 1）
  对事件流模型的压力，留到各自 adapter spec 验证。
