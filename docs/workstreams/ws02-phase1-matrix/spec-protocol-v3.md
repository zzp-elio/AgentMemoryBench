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

框架定位（2026-07-06 与用户确认）：本框架是对三层参考资产"取其精华去其糟粕"
的综合——5 个第三方集成框架（结构设计）、10 个 method 官方仓库含其测评代码
（如 `third_party/methods/LightMem/experiments/`、mem0 memory-benchmarks，
是 prompt/参数/粒度的第一手证据）、5 个 benchmark 官方仓库（评测流程与
metric）；在此之上叠加参考框架均不具备的四件资产：retrieve-first 双口径、
审计级成本观测、公私数据边界、可复现工程。2026-07-06 修订：按用户反馈完成
接口减重（单一 ingest）、prompt 三级来源、provenance 分级、显式能力声明。

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
    """记忆系统统一接入协议。写入=框架按声明粒度投递；检索=只检索不作答。

    必须实现的抽象方法只有两个：ingest() 和 retrieve()。
    生命周期与边界钩子默认 no-op，按需覆写（每个 method 实际需要的钩子 ≤2 个）。
    """

    # ---- 声明（类属性，进 registration/manifest）----
    consume_granularity: Literal["turn", "pair", "session", "conversation"]
    session_memory_report: bool = False            # HaluMem extraction 用；显式声明 +
                                                   # 运行时强校验（见 §5）
    provenance_granularity: Literal["none", "session", "turn"] = "none"

    # ---- 生命周期（默认 no-op）----
    def prepare(self, run_context: ProviderRunContext) -> None: ...
        # 开工准备：state_dir、isolation_key 全集预告、数据库/服务连接
    def cleanup(self) -> None: ...

    # ---- 写入（唯一抽象写入方法）----
    @abstractmethod
    def ingest(self, unit: IngestUnit) -> IngestResult | None: ...
        # unit 的具体类型与 consume_granularity 一一对应：
        #   turn -> TurnEvent | pair -> TurnPair | session -> SessionBatch |
        #   conversation -> ConversationBatch
        # 框架内部的规范表示永远是 turn 级事件流（"message 流"）；声明粒度只决定
        # 框架把流打包投递的形状。method 永远不迭代数据集。
        # session/conversation 粒度 method 经 IngestResult.session_memories
        # 报告本 session 新增记忆（HaluMem）。

    # ---- 边界钩子（默认 no-op，按需覆写）----
    def end_session(self, ref: SessionRef) -> SessionMemoryReport | None: ...
        # 仅对 turn/pair 粒度 method 有意义（它们没有 session 级调用点，靠此钩子
        # 感知 session 边界并报告新增记忆）；session/conversation 粒度 method
        # 无需实现——不存在与 ingest 返回值的重复。
    def end_conversation(self, ref: UnitRef) -> None: ...
        # 收尾/完成屏障（R3）：返回即记忆可检索。只有需要收尾的 method 覆写：
        # SimpleMem finalize、LightMem 末批 flush + LoCoMo post-build update、
        # Cognee cognify、Supermemory/MemOS 异步轮询；超时按 failed_ingest。
        # Mem0/A-Mem/LangMem/Letta 等同步型完全不用写。

    # ---- 检索（唯一抽象检索方法）----
    @abstractmethod
    def retrieve(self, query: RetrievalQuery) -> RetrievalResult: ...
```

**为什么不是四个 ingest 方法**（2026-07-06 用户质疑后减重）：接口面收敛为
`ingest + retrieve` 两个必选方法；粒度差异走载荷类型而非方法名。一个最简
adapter（如 A-Mem）只需 `consume_granularity="turn"` + 实现 `ingest`（内部一行
`add_note`）+ `retrieve`，不写任何钩子。

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
  + question（+question_time 等 benchmark 字段）。**prompt 来源三级策略**
  （2026-07-06 用户定案，answer prompt 与 judge prompt 同规则）：
  1. benchmark 官方有 → 直接用（LongMemEval generation prompt、LoCoMo 官方
     answer prompt、MemBench INSTRUCTION、HaluMem QA prompt、BEAM prompt；
     judge 侧 LongMemEval/HaluMem/BEAM 有官方 judge）；
  2. benchmark 官方没有 → 参考各 method 官方仓库的该 benchmark 测评代码
     （如 mem0 memory-benchmarks、LightMem experiments）与第三方框架的做法
     （如 LoCoMo 无官方 QA judge，现行 LightMem-style judge 即此级来源）；
  3. 取其精华后由架构师设计本框架版本，spec 中记录来源与取舍理由，
     经用户批准后冻结为该 benchmark 的 unified prompt profile。
  跨 method 统一、跨 benchmark 各一套。
- **method-native 口径**（复现论证）：method 返回 prompt_messages，保留论文
  原生 prompt 工程。
- 双口径结果并列展示；分差本身量化"prompt 工程贡献"。
- **official / custom profile**：official 锚定 method 论文超参与基座配置，
  允许多变体（official-<variant>）；custom 自由调参与换基座。manifest 强制
  标注 `prompt_track`（unified/native）与 `profile`（official-*/custom-*），
  artifact 永不混淆。当前阶段真实调用统一 gpt-4o-mini；与 method 论文基座不同
  时报告须注明"official-protocol, unified-base-LLM"。

## 5. 能力声明与占位规范

- **显式声明 + 运行时强校验**（2026-07-06 用户问"显式还是隐式"，架构师裁定
  显式，理由）：(a) runner 要在**运行前**决定某指标是否可评（成本预估、结果
  矩阵占位、manifest 记录），隐式要等运行时才知道；(b) 隐式的返回值判断有
  歧义——`None` 分不清"不支持"和"这个 session 恰好没抽出记忆"（空列表 vs None
  是经典 bug 源）；(c) 沿用本框架既有先例：声明支持却漏报 → 运行时报错
  fail-fast，不允许静默降级（efficiency retrieval contract 已用此模式）。
- **provenance 分级解决"证据粒度不一"问题**（2026-07-06 用户提出）：
  统一按**最细粒度（turn 级 `source_turn_ids`）记录**——method 写入时收到过
  每个 turn 的稳定 id（dia_id/step_id/顺序号），检索命中条目回报这些 id；
  框架掌握 `turn_id → session_id` 层级映射（规范事件流自带），**任何更粗粒度
  的 recall 都由框架向上聚合得出**（LME session recall、MemBench step recall、
  LoCoMo dia_id recall 全覆盖）。method 只能报 session 级的（如 Supermemory
  按 session 建 document）→ 声明 `provenance_granularity="session"`，则
  turn 级指标 N/A、session 级可评。声明 `"none"` → 全部 evidence recall 指标
  N/A（capability: unsupported），不硬造、不 sidecar 强补（用户定案）。
- `session_memory_report=False` → HaluMem Memory Extraction 指标占位。
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

## 7. 决策点（2026-07-06 全部定案）

- **A. unified prompt 来源 = 三级策略**（见 §4）：benchmark 官方 → method
  官方测评代码/第三方框架参考 → 架构师综合设计并冻结。用户已确认。
- **B. MemBench Observation 子集 prompt 口径 = INSTRUCTION_FIRST**（忠实官方
  active code path）。用户已确认。
- **C. BEAM scorer = 按论文语义修正（允许 0.5 半分）**：官方代码的 int 截断
  认定为 bug（GitHub 已有 issue 无回应）；mem0 memory-benchmarks 的 BEAM 实现
  是修正先例（judge 输出 `0.0/0.5/1.0`、浮点均值 + `pass_threshold=0.5`、
  自研 rubric judge prompt 顺带消除官方 `<question>` 未替换问题，见
  `third_party/methods/mem0-main/memory-benchmarks/benchmarks/beam/prompts.py:99`、
  `benchmarks/common/metrics.py:25`）。结果须标注与官方代码的差异。用户已确认
  该问题为 bug。

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
