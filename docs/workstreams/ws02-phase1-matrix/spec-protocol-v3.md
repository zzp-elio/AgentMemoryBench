---
id: ws02
doc: spec (protocol v3, final)
status: draft
created: 2026-07-06
---
# 核心协议 v3 设计（最终版，待用户批准）

作者：Claude（架构师）。取代候选方案 A（[spec-protocol-v2.md](spec-protocol-v2.md)，
其用户决策与 R1-R3 已并入本文）。依据：
[接口能力双向矩阵](track0-interface-capability-matrix.md)（15 卡交叉）、
[五框架对比](track0-framework-comparison.md)、ws02 README 决策记录（2026-07-05/06
全部轮次）。**本 spec 获用户批准后 Track B/C 解冻。**

## 1. 数据模型（三层同构，用户 2026-07-06 统一观）

```text
IsolationUnit（隔离空间：conversation / sample-tid / uuid-user，由 benchmark adapter 声明）
  └── Session（带 time；无 session 概念的 benchmark 视为单 session）
        └── TurnEvent（顺序事件）
```

```python
@dataclass(frozen=True)
class TurnEvent:
    """规范事件流的最小单元；框架驱动迭代，method 只消费。"""
    role: str                  # user / assistant / 说话者名 / observer（MemBench 第三人称单角色流）
    speaker_name: str | None
    content: str               # 文本；LoCoMo 图片按定案拼 caption：`原文 (image description: ...)`
    timestamp: str | None      # 原始字符串，不估算；session time 由框架继承填充
    isolation_key: str         # 显式隔离键（框架发放，见 R5）
    session_id: str | None
    turn_id: str               # benchmark 内稳定 id（dia_id / step_id / 顺序号）
    metadata: dict             # 公开字段 only；永不含 gold/evidence/persona_info
```

多模态扩展位：Phase 1 content 为纯文本（caption 拼接口径）；未来多模态把
content 升级为结构化 parts（文本+图像引用），TurnEvent 其余字段不变。
agentic task family（MemoryArena 类）不进本协议，届时另立 task family。

## 2. Provider 协议 v3

```python
class BaseMemoryProvider(ABC):
    """记忆系统统一接入协议。写入=框架按声明粒度投递；检索=只检索不作答。"""

    # ---- 声明（registration/类属性）----
    consume_granularity: Literal["turn", "pair", "session", "conversation"]
    supports_session_memory_report: bool = False   # HaluMem extraction 用
    supports_provenance: bool = False              # evidence recall 用

    # ---- 生命周期 ----
    def prepare(self, run_context: ProviderRunContext) -> None: ...
        # state_dir、isolation_key 全集预告、run_id；默认 no-op
    def cleanup(self) -> None: ...

    # ---- 写入（method 只实现与声明粒度对应的一个方法）----
    def ingest_turn(self, turn: TurnEvent) -> None: ...
    def ingest_pair(self, pair: TurnPair) -> None: ...            # user+assistant 对
    def ingest_session(self, session: SessionBatch) -> SessionMemoryReport | None: ...
    def ingest_conversation(self, unit: ConversationBatch) -> None: ...

    # ---- 边界钩子 ----
    def end_session(self, ref: SessionRef) -> SessionMemoryReport | None: ...
        # turn/pair 粒度 method 在此报告本 session 新增记忆（可选能力）；
        # session 粒度 method 可在 ingest_session 返回值直接报告，二者取先到者
    def end_conversation(self, ref: UnitRef) -> None: ...
        # 完成屏障（R3）：返回即记忆可检索。SimpleMem finalize、LightMem 末批
        # flush + LoCoMo post-build update、Cognee cognify、Supermemory/MemOS
        # 异步轮询全部挂此钩子；超时按 failed_ingest。

    # ---- 检索 ----
    def retrieve(self, query: RetrievalQuery) -> RetrievalResult: ...
```

```python
@dataclass(frozen=True)
class RetrievalQuery:
    """检索输入。query 不总是'问题'（HaluMem update 用 gold memory 文本作 query）。"""
    query_text: str
    isolation_key: str
    question_time: str | None      # 一等字段（LME/MemBench/BEAM 需要）
    top_k: int                     # per-benchmark profile 控制（HaluMem update=10/QA=20 先例）
    purpose: Literal["qa", "memory_update_probe", "extraction_probe"]
    source_question: Question | None   # purpose=qa 时携带（category 等公开 metadata）

@dataclass(frozen=True)
class RetrievalResult:
    formatted_memory: str                    # 必需：规范化记忆（unified 口径唯一输入）
    prompt_messages: list[PromptMessage] | None   # 可选：method-native 口径完整 prompt
    items: list[RetrievedItem] | None        # 可选：结构化条目（id/score/timestamp/
                                             # source_turn_ids），支撑 evidence recall
    metadata: dict                           # 调试/prompt profile/原始检索信息
```

formatted_memory 规范：条目式文本，每条尽量带时间前缀（`[time] content`），
外层由框架包 `<memory>` 标签注入 unified prompt；method 不得在其中夹带指令。

## 3. 行为规则（R1-R6）

- **R1 检索纯度**：`retrieve()` 内禁止调用 answer LLM 作答；检索服务型 LLM
  （A-Mem query keywords、SimpleMem planning/reflection、MemOS tree fine）允许
  并计入 retrieval 成本。有内置 QA 入口的 method（MemOS chat、Letta
  send_message、SimpleMem ask、Cognee GRAPH_COMPLETION）一律从检索层接入。
- **R2 agent-native 接入面**：LangMem/Letta 绕过 agent 自主决策层，直接驱动
  memory/store API；method 卡片注明口径。
- **R3 写入完成判据**：`end_conversation()` 返回 = 记忆可检索；异步型在钩子内
  轮询（Supermemory 需 document+memory 双 done），超时 fail 为 failed_ingest。
- **R4 检索副作用口径**（2026-07-06 用户认同）：检索改变 method 状态（MemoryOS
  heat）接受为官方行为并在 method 卡片注明；resume 绝不重新检索已答问题
  （现状已保证）；同一 run 内问题顺序固定，保证可复现。
- **R5 隔离 = 并置持久化**：框架管政策（benchmark adapter 声明隔离单位，框架
  发放 isolation_key + 独立状态根），adapter 管机制（键 → namespace/
  containerTag/collection/agent_id/dataset）。**不做逐边界 reset**；每个
  IsolationUnit 状态永久并置留存；reset 仅用于失败 unit 的 clean retry。
- **R6 并行不变量**：并行只是提效手段，任何并行执行的实验结果必须与串行一致；
  违反即 bug。（工程实现属未来工程专项，本 spec 只锁不变量。）

## 4. Answer 层：双口径 × 双 profile

- **unified 口径**（公平比较）：框架统一 answer prompt，输入 = formatted_memory
  + question（+question_time 等 benchmark 字段）。**prompt 来源采用该 benchmark
  官方 reader prompt**（LoCoMo 官方 GPT answer prompt、LongMemEval 官方
  generation prompt、MemBench INSTRUCTION、HaluMem QA prompt、BEAM long-context
  prompt）——不自造 prompt，消除任意性【决策点 A，见 §7】。跨 method 统一、
  跨 benchmark 各一套。
- **method-native 口径**（复现论证）：method 返回 prompt_messages，保留论文
  原生 prompt 工程。
- 双口径结果并列展示；分差本身量化"prompt 工程贡献"。
- **official / custom profile**：official 锚定 method 论文超参与基座配置，
  允许多变体（official-<variant>）；custom 自由调参与换基座。manifest 强制
  标注 `prompt_track`（unified/native）与 `profile`（official-*/custom-*），
  artifact 永不混淆。当前阶段真实调用统一 gpt-4o-mini；与 method 论文基座不同
  时报告须注明"official-protocol, unified-base-LLM"。

## 5. 能力声明与占位规范

- `supports_provenance=False` → 该 method 在 evidence recall 类指标（MemBench
  recall、LME retrieval recall）的结果格为 **N/A（capability: unsupported）**，
  不硬造、不 sidecar 强补（用户 2026-07-06 定案）。
- `supports_session_memory_report=False` → HaluMem Memory Extraction 指标占位。
- 占位符统一写入结果矩阵并在汇报材料脚注说明。

## 6. 迁移方案（三阶段，均为 Codex plan 粒度）

- **M-A 协议落地**：新实体（TurnEvent/RetrievalQuery/RetrievalResult 等）、
  runner 事件流驱动与粒度聚合层、`add(conversation)` 兼容桥（旧 4 adapter 零
  改动跑通）、MockMemoryProvider v3、红绿测试。验收：`uv run pytest -q`
  ≥709 passed；桥接下四 method fake smoke artifact 与现状语义一致。
- **M-B 内置 adapter 原生化**（每个独立小任务 + 等价性验证）：
  Mem0（turn/pair，官方粒度即协议粒度，最易）→ LightMem（pair 批 +
  end_conversation 挂 flush/offline update）→ A-Mem（turn）→ MemoryOS（pair）。
  每步：fake/offline 桥接 vs 原生 artifact 等价；形变记录中被迫代码逐条消除。
- **M-C Track B/C 解冻**：新 benchmark adapter（MemBench→HaluMem→BEAM）与新
  method adapter 直接按 v3 接入；HaluMem operation-level flow、MemBench
  capacity 模式在各自 adapter spec 中设计（协议钩子已留够）。

## 7. 遗留决策点（批准本 spec 时一并裁定或明确延后）

- **A. unified prompt 来源 = benchmark 官方 reader prompt**（§4，架构师推荐）。
- **B. MemBench Observation 子集 prompt 口径**：官方 active path 用
  INSTRUCTION_FIRST（推荐，忠实代码），语义更优的 INSTRUCTION_THIRD 存在但
  非 active——建议按 active path，adapter spec 时可复议。
- **C. BEAM scorer 论文（允许 0.5）vs 代码（int 截断）不一致 + judge prompt
  `<question>` 疑似未替换 bug**：建议默认复刻代码（可复现优先），标注差异；
  adapter spec 时终裁。

## 8. 非目标

resume/并行/兜底/日志/终端等工程优化（未来独立工程专项 workstream）；
agentic task family；多模态执行；`--method-class` 用户轻量路径迁移（用户接入
非当前主线，v3 稳定后再迁）；BaseMemorySystem legacy 清理（ws03）。

## 9. 验收标准（整个 v3 落地完成的判据）

1. M-A/M-B 全部通过各自验收；全量回归 ≥ 709 passed 基线。
2. 四个内置 method 在 LoCoMo + LongMemEval 极小真实 smoke 下，native 口径结果
   与迁移前一致（同 run 规模对比），unified 口径可运行并产出双口径对照表。
3. 形变记录复查：四张机制卡第 7 节所列"被整段输入逼出的代码"在原生化后消除
   或有明确保留理由。
4. manifest/artifact 含 prompt_track 与 profile 标注且回读校验通过。
