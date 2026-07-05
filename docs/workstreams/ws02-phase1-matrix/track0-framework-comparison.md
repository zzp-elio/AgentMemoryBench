# Track 0：五个集成框架接口对比卡片

更新日期：2026-07-06。作者：Claude（架构师）。来源：`第三方框架参考/` 下五个框架
的源码实读（文件:行号可溯），非 README 转述。

## 1. 一句话结论

五个框架**没有一个**把完整 Conversation 对象直接交给 method——全部由框架层把数据
拆成 message/chunk/document 级小单元再喂给 method，并显式传递隔离键和时间戳；
"写入完成边界钩子"（finalize / awaitIndexing / post_add）在四个框架中出现。
这有力支持用户 2026-07-05 的过拟合担忧：我们的 `add(conversation)` 把迭代责任
压给了 adapter，是少数派设计。

## 2. 各框架接口事实

### 2.1 EverOS / EverCore evaluation（架构最完整，另有中文架构文档）

- 位置：`EverOS-*/methods/EverCore/evaluation/`；根目录 `EVALUATION_ARCHITECTURE.md`
  是其可复刻中文架构说明（值得完整读）。
- 数据面：converter registry 把 LongMemEval/PersonaMem **统一转成 LoCoMo-style
  JSON** 作为通用中间格式，再进内部 `Dataset/Conversation/Message/QAPair`。
- method 面（`src/adapters/online_base.py`）：模板方法模式。基类 `add(conversations)`
  负责 conversation→message 列表转换、**双视角处理**（两个真人说话者时分别以
  speaker_a/speaker_b 视角各写一份记忆）、user_id 隔离（`{conv_id}_{speaker}`）、
  semaphore 并发；子类只实现 `_add_user_messages(conv, messages, speaker)` 和
  `_search_single_user(query, conv_id, user_id, top_k)`。
- 回答面：`search()` 返回 `SearchResult.formatted_context`（字符串 context），
  基类 `answer(query, context)` 用通用 prompt，子类可 override prompt——
  语义上等价于我们的 framework reader，但我们的 `prompt_messages` 保真度更高。
- 评测面：answer-level only，不算 retrieval recall。配置全部 YAML 驱动
  （config/datasets/*、config/systems/*、prompts.yaml）。

### 2.2 MemoryData（对我们价值最大：20 method × 多 benchmark 矩阵）

- 位置：`MemoryData/`；methods/ 下 20 个方法（**含我们 Phase 1 全部 10 个**：
  MemOS、simplemem、letta、cognee、lightmem、mem0、memoryos、a_mem、zep、everos…），
  benchmark/ 含 locomo、longbench、membench、memoryagentbench。
- method 面：每方法一个薄 adapter，签名高度统一：
  `add_chunk(content: str, timestamp=None, [role/source_ids])` + `retrieve(question)`
  + 部分有 `finalize()`（如 SimpleMemAdapter，写入结束触发离线整理）。
  证据：`methods/memoryos/memoryos_adapter.py:70,73`、
  `methods/simplemem/simplemem_adapter.py:153,156`。
- 驱动面：中央 `utils/agent.py`（约 3400 行）按 method 分支循环喂 chunk
  （2938/2989/3159/3208/3260/3299 行等）——迭代责任在框架不在 adapter，但中央
  agent.py 本身是巨型 if/else，是**反面教材**（我们应保持 registry 分发）。
- memtree 的 `add_chunk(..., source_ids=...)` 说明 chunk 级写入可携带
  evidence 溯源 id。
- vendor 方式：methods/<name>/source/ 同样整仓 vendor（和我们一样重）。

### 2.3 agent-memory-benchmark（接口设计最精致）

- method 面（`src/memory_bench/memory/base.py`）：`MemoryProvider(ABC)`：
  - 类属性声明：`name/kind(local|cloud)/provider/variant/concurrency`
    （**每个 provider 自己声明并发安全度**，替代我们的
    `--allow-unsafe-custom-parallel` 全局开关思路）。
  - 生命周期钩子：`initialize()` / `cleanup()` /
    `prepare(store_dir, unit_ids, reset)`——框架把**状态目录和全部隔离单元
    提前告知** provider。
  - `ingest(documents: list[Document])`：Document 级（benchmark 无关的扁平
    文档 + user_id），带 async 变体。
  - `retrieve(query, k, user_id, query_timestamp) -> (docs, raw_response)`：
    显式 user_id 作用域 + **查询时间戳**（对应我们 LongMemEval question_time）
    + 原始响应留档（provenance）。
  - `retrieve_by_steps(steps, ...)`：按 step/turn id 检索——正是 MemBench
    evidence recall 需要的能力，作为可选方法默认回退普通 retrieve。

### 2.4 memorybench（supermemory 出品，TypeScript）

- method 面（`src/types/provider.ts`）：`Provider` 接口：
  `initialize(config)`、`ingest(sessions: UnifiedSession[], {containerTag})`、
  **`awaitIndexing(result, containerTag, onProgress)`**（云端异步索引的完成
  屏障——Supermemory/Zep 这类云服务写入后索引未就绪，直接查会拿到空结果）、
  `search(query, {containerTag, limit})`、`clear(containerTag)`。
- containerTag = 隔离键；per-provider prompts 和 concurrency 配置。
- 对 Track A 的 Supermemory 审计直接有用：这是 supermemory 官方自己的评测框架。

### 2.5 MemEval（DX 最简）

- method 面（`src/agents_memory/systems/_template.py`）：单文件函数式模板——
  `run(conv, llm_model, ...)`：三段式注释（INGEST / ANSWER / EVALUATE），
  新方法接入 = 复制一个文件填三段。无 resume/观测等重机制。
- 启示：给"普通用户接入"路径一个 `--method-file` 单文件模板（我们 ws03 的
  遗留项）有成熟先例。

## 3. 横向对照表

| 维度 | 我们(现状) | EverOS | MemoryData | agent-memory-bench | memorybench | MemEval |
| --- | --- | --- | --- | --- | --- | --- |
| 写入粒度 | 整个 Conversation | message 列表/用户 | **chunk/message** | Document 批 | session 批 | conversation |
| 迭代责任 | adapter | 框架 | 框架 | 框架 | 框架 | adapter |
| 边界钩子 | 无 | post_add/wait | **finalize()** | prepare/cleanup | **awaitIndexing** | 无 |
| 隔离键 | 隐式(状态目录) | user_id 显式 | conv 内隐式 | **user_id+unit_ids** | containerTag | conv 内隐式 |
| 时间戳传递 | Conversation 内 | message 字段 | add_chunk 参数 | ingest+query 两侧 | session 内 | conv 内 |
| 检索输出 | prompt_messages | context 字符串 | context/entries | (docs, raw) | 原始列表 | 自由 |
| evidence 检索 | 无 | 无 | source_ids 可带 | **retrieve_by_steps** | 无 | 无 |
| 并发声明 | registry 字段 | config | 无 | **provider 类属性** | provider 配置 | 无 |
| 双视角写入 | 无(method 自理) | **基类内建** | 无 | 无 | 无 | 无 |

## 4. 对我们协议的启示（v2 草案，待写正式 spec）

综合证据，建议协议朝"**细粒度写入 + 分层边界钩子**"演进（用户 2026-07-05
猜想的第三候选），同时保留我们优于所有参考框架的 `AnswerPromptResult.prompt_messages`：

```python
class BaseMemoryProvider(ABC):
    # 生命周期（参考 agent-memory-benchmark）
    def prepare(self, run_context) -> None: ...        # 可选：state dir、隔离单元预告
    def cleanup(self) -> None: ...                     # 可选
    # 写入主协议（参考 MemoryData / EverOS）
    @abstractmethod
    def add_turn(self, turn) -> None: ...              # role/speaker、content、time、
                                                       # metadata{conversation_id, session_id, turn_id}
    def end_session(self, session_meta) -> None: ...   # 可选边界钩子：LightMem offline
                                                       # update、HaluMem session extraction
    def end_conversation(self, conv_meta) -> None: ... # 可选：finalize/awaitIndexing 等价物
    # 检索主协议（保留现状，是我们的长板）
    @abstractmethod
    def retrieve(self, question) -> AnswerPromptResult: ...
    def retrieve_by_evidence_ids(self, ids, question) -> ...:  # 可选：MemBench recall
```

- 框架负责迭代（runner 从 Conversation 驱动 add_turn 循环），adapter 负担显著
  下降；turn 级 resume checkpoint 变得自然。
- 兼容：旧 `add(conversation)` 可由默认实现桥接（缓冲 turns，
  `end_conversation` 时调用旧 add），4 个现有 adapter 迁移压力可控。
- chunk-stream benchmark（MemoryAgentBench）映射为"turn=chunk"；
  HaluMem session 级操作挂 `end_session`；MemBench evidence recall 挂
  `retrieve_by_evidence_ids`。
- 待定问题（正式 spec 前需用户讨论）：① 双视角写入是否学 EverOS 内建到框架
  （影响 LoCoMo 类两真人对话的公平性口径）；② 隔离键是否从隐式状态目录升级为
  显式 user_id/container 参数；③ provider 并发声明是否移到类属性。

## 5. 未确认项

- MemoryData / agent-memory-benchmark 的 resume 与成本观测机制未细读（初判弱于
  我们，暂无借鉴优先级）。
- EverOS 双视角写入对各 method 分数的实际影响未验证（论文级口径问题）。
- memorybench UnifiedSession 具体字段未展开（TS types/unified.ts 可后续补）。
- 各框架 judge/metric 层只扫了目录，未逐个对照（answer-level 为主的判断基于
  EverOS 文档自述与 amb judge.py 存在性）。
