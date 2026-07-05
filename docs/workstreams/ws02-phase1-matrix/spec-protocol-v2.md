---
id: ws02
doc: spec (protocol v2, candidate A)
status: on-hold
created: 2026-07-06
---
# 核心协议 v2 设计：turn 级写入 + 分层边界钩子（候选方案 A，缓行中）

作者：Claude（架构师）。状态：**on-hold（2026-07-06 用户决定缓行）**——本文档
降级为**候选方案 A**，不进入批准流程。用户口径：不急于定 add 粒度
（`add_session` 或多粒度并存都可能更优）；必须先完成 10 method 机制深读 +
5 benchmark 测评机制萃取，再设计最终接口。新增硬性设计约束：

1. benchmark 形态与 method 形态之间预期需要**一到两个中间层**统一，接口设计
   要显式回答"中间层是什么、归一到什么表示"。
2. **可扩展性**：未来要接入多模态 benchmark/method 和 agent-task memory
   benchmark（MemoryArena 类，调研卡片已建议独立 `agentic-memory-environment`
   task family），协议不能把"文本对话 QA"写死为唯一形态。
3. 多种写入粒度并存（method 声明消费粒度、框架聚合投递）是候选方向之一。
4. **（2026-07-06 新增）retrieve 侧双轨输出**：`retrieve()` 必须返回规范化
   记忆 `formatted_memory`（unified 公平口径的唯一输入，框架统一 answer
   prompt），并可选返回 `prompt_messages`（method-native 复现口径）。两种
   口径的实验结果都进最终报告。`AnswerPromptResult` 将相应演进，
   `metadata["answer_context"]` 是 formatted_memory 的雏形。

以下原文保留作为候选方案 A 的完整论证；其中 §2 的用户决策（双视角不内建、
显式隔离键、并发不变量）和 §3.3 的 R1-R3 行为规则**不受缓行影响，继续有效**——
它们与粒度选择正交。

## 1. 背景与证据

现有 `BaseMemoryProvider.add(conversation) + retrieve(question)` 从
LoCoMo+LongMemEval+4 method 归纳而来，存在过拟合风险（用户 2026-07-05 提出）。
两路独立调研证实了该担忧：

- **五框架对比**（[track0-framework-comparison.md](track0-framework-comparison.md)）：
  无一框架把完整 Conversation 交给 method；写入粒度为 chunk/message/document；
  边界钩子（finalize/awaitIndexing/post_add）在 4/5 框架存在；隔离键全部显式。
- **六 method 审计**（[audits/summary.md](audits/summary.md)）：SimpleMem 原生
  `add_dialogue + finalize`、Supermemory 原生按 turn 追加 + containerTag、
  LangMem namespace store、Cognee add+cognify 多阶段、MemOS/Letta 有显式运行态
  边界——多数新 method 不贴合"一次给整段 conversation"。

## 2. 已定决策输入（2026-07-06 用户拍板）

1. **双视角写入不内建**，保持各 method 论文官方口径；记为 future 选项。
2. **隔离键升级为显式参数**，随写入/检索传递（服务型 method 必需）。
3. **并发机制维持现状**（内置 method 由 registry 声明；用户接入路径的并发
   守卫降级为后续事项）。**不变量：并行只是提效手段，任何并行执行的实验结果
   必须与串行一致**；违反即 bug。
4. retrieve-first 保留：`retrieve() -> AnswerPromptResult.prompt_messages`
   是我们优于全部参考框架的长板，不动。

## 3. 协议定义

### 3.1 新实体

```python
@dataclass(frozen=True)
class TurnEvent:
    """单个对话回合的写入事件（框架驱动迭代，method 只消费）。"""
    role: str                 # user / assistant / 真实说话者名
    content: str
    timestamp: str | None     # 原始 benchmark 时间字符串，不做估算
    conversation_id: str
    session_id: str | None    # 无 session 概念的 benchmark 为 None
    turn_id: str              # benchmark 内稳定 id（evidence/provenance 用）
    isolation_key: str        # 显式隔离键，默认 f"{run_id}_{conversation_id}"
    metadata: dict            # speaker 名、多模态占位等公开字段；绝不含私有标签
```

### 3.2 BaseMemoryProvider v2

```python
class BaseMemoryProvider(ABC):
    # —— 生命周期（可选，默认 no-op）——
    def prepare(self, run_context: ProviderRunContext) -> None: ...
        # run_context: state_dir、isolation_key 全集预告、run_id
    def cleanup(self) -> None: ...

    # —— 写入主协议 ——
    @abstractmethod
    def add_turn(self, turn: TurnEvent) -> None: ...
    def end_session(self, session_id: str, conversation_id: str) -> None: ...
        # 可选钩子：session 边界（HaluMem session 级操作、按 session 批量整理）
    def end_conversation(self, conversation_id: str) -> None: ...
        # 可选钩子：写入完成屏障（LightMem offline update、SimpleMem finalize、
        # Supermemory/云服务 awaitIndexing 语义）。返回前必须保证记忆可检索。

    # —— 检索主协议（不变）——
    @abstractmethod
    def retrieve(self, question: Question) -> AnswerPromptResult: ...
    def retrieve_by_evidence_ids(
        self, turn_ids: list[str], question: Question
    ) -> RetrievedEvidence | None: ...
        # 可选：MemBench 类 evidence recall；默认返回 None 表示不支持
```

框架（runner）负责：从 Conversation 展开 TurnEvent 循环、按正确顺序调用
end_session/end_conversation、传递显式 isolation_key、维持 conversation 级
并行隔离与 resume。adapter 不再自己迭代数据。

### 3.3 行为规则（裁定 Track A 未决问题）

- **R1 检索纯度**：`retrieve()` 内部**禁止调用 answer LLM 作答**；有内置 QA/chat
  入口的 method（MemOS chat、Letta send_message）必须从其 memory/检索层接入。
  method 内部为检索服务的 LLM 调用（如 A-Mem query keyword）不受限。
- **R2 agent-native 接入面**：LangMem/Letta 类 agent 内生记忆系统，**允许且要求
  绕过 agent 自主决策层**，直接驱动其 memory/store API。理由：本框架评测的是
  记忆系统而非 agent 脚手架；参考框架（memorybench/agent-memory-benchmark）
  同样按 ingest/search 服务对待 provider。每个此类 method 的卡片必须显式记录
  "接入面 = memory API，非官方 agent loop"作为口径说明。
- **R3 异步写入完成判据**：有后台处理的 method（Supermemory extraction、
  Cognee cognify、MemOS scheduler），`end_conversation()` 返回即视为写入完成；
  adapter 在该钩子内轮询/等待，超时按 failed_ingest 处理。禁止"add 返回但
  索引未就绪就进入提问"。

## 4. 兼容与迁移

- **兼容桥**：提供 `add(conversation)` 默认实现——框架仍走 add_turn 循环，
  桥接层缓冲 turns 并在 end_conversation 时调用旧 `add()`。四个内置 adapter
  第一步经桥零改动运行，回归必须保持 709 基线。
- **原生化顺序**（第二步，逐个小任务）：Mem0（官方 CHUNK_SIZE=1/2 本就是
  turn/pair 粒度，最容易）→ LightMem（offline update 挂 end_conversation）→
  A-Mem → MemoryOS。每迁移一个跑 fake/offline 等价性验证：桥接路径与原生
  路径产出 artifact 语义一致。
- **runner**：ingestion 循环移入 runner；conversation 级 resume 语义不变；
  turn 级 checkpoint 与 v2 天然对齐，但 Phase 1 默认粒度仍是 conversation 级，
  不重启 turn-level resume 主线。
- **不受影响**：evaluation 引擎、artifact 格式、efficiency observation 的
  conversation/question scope、CLI、manifest 主结构（新增 protocol_version 字段）。
- **旧接口处置**：`BaseMemorySystem` 兼容路径维持现状（ws03 范围）；
  `--method-class` 用户路径待 v2 稳定后再迁（非主线）。

## 5. 非目标

- 不内建双视角写入；不做多 provider LLM；不改评测/metric 层；
  不在本 spec 内接入任何新 benchmark/method（那是 Track B/C）。

## 6. 实施分期与验收

- **P1 协议落地**：TurnEvent/钩子/兼容桥/runner 循环 + MockMemoryProvider v2
  + 红绿测试。验收：`uv run pytest -q` ≥709 passed；桥接下四内置 method
  fake smoke artifact 与现状一致。
- **P2 内置 adapter 原生化**：按上述顺序逐个迁移+等价性验证。验收：每个
  method 迁移后 focused 回归通过，LoCoMo/LongMemEval 极小真实 smoke 各一次
  （待用户确认预算后）。
- **P3 新 method 直接以 v2 接入**（回到 Track B/C）。

## 7. 风险与未确认项

- 本机 `/tmp` venv PyPI SSL 证书失败（Track A 全部安装实测被此阻断）——
  环境问题需在 Track C smoke 前解决，与协议无关但阻塞后续验证。
- MemoryAgentBench chunk-stream 映射为 turn=chunk 的语义损耗待其 adapter
  spec 时确认。
- `retrieve_by_evidence_ids` 的返回结构在 MemBench adapter spec 时再定稿，
  本 spec 只保留占位签名。
