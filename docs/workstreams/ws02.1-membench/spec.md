---
id: ws02.1
parent: ws02
doc: spec
status: draft
created: 2026-07-07
---
# MemBench Adapter 设计（Phase 1 smoke 口径）

作者：Claude（架构师）。依据：
[MemBench 调研卡片](../../survey/benchmarks/MemBench.md)（字段/流程/成本证据
均引自该卡）、[协议 v3 spec](../ws02-phase1-matrix/spec-protocol-v3.md)
（approved）、用户定案（决策点 B：INSTRUCTION_FIRST；evidence recall 不强求；
QA/accuracy 子集先行）。**status: draft，待用户批准后拆 plan。**

## 1. Phase 1 范围

- **做**：multiple-choice accuracy 主指标（exact match，零 judge 成本）+
  question_type 维度聚合；trajectory 级隔离；0-10k 与 100k 两个 variant。
- **缓/不做**：evidence recall（provenance 声明 method 才有资格，metric 计算
  留待后续任务；本期只保证 turn_id 口径正确落盘）；capacity/efficiency 运行
  模式；根目录 20 条 `Emotion/Preference` 补充样本（排除，卡片 §2.2 定性为
  异常变体）。

## 2. 数据映射（MemBench → 统一模型）

### 2.1 隔离与层级

- IsolationUnit = **trajectory（tid）**；每条 trajectory 一个 `Conversation`。
- `conversation_id = f"{scenario}-{level}-{question_type}-{tid}"`
  （如 `first-high-highlevel-<tid>`）；tid 在文件内的全局唯一性未经验证
  （卡片 §7.3 同源风险），loader 必须做唯一性断言，冲突即 fail-fast。
- MemBench 无 session 概念 → 每 trajectory 单个 Session
  （`session_id="s1"`，session_time=None）。

### 2.2 message_list → TurnEvent

- 每个 step 一个 Turn，`turn_id = str(step_id)`，**step_id 从 1 开始**，与官方
  env `info["step_id"]` 口径对齐（卡片 §2.6；off-by-one 是 §7.3 已知风险，
  loader 单测必须用一条真实样本核对 `target_step_id` 指向的内容）。
- **Participation / FirstAgent**（dict step）：content 采用官方 store 文本形态
  `'user': {user}; 'agent': {agent}`（卡片 §3.2），role="user"，
  metadata 保留 `{"ps_user": ..., "ps_agent": ...}` 原文分字段；官方
  `{step}[|]` 前缀是其 CommonMemory 的 provenance hack，**不进 content**
  （我们的 provenance 走 turn_id）。
- **Observation / ThirdAgent**（string step）：content = 原字符串，
  role="user"（单方消息流，卡片 §2.5）。
- 时间：message 内嵌的 `(place/time...)` 文本不拆解，保持原样；
  TurnEvent.timestamp=None（数据无独立时间字段）。

### 2.3 QA → Question / 私有标签

- 公开：`question`、`time`（→ `Question.question_time`）、`choices`
  （→ `Question.metadata["choices"]`，A-D 完整文本）、`question_type`
  （→ `Question.category`）。
- 私有（只进 GoldAnswerInfo）：`ground_truth`（正确选项字母）、`answer`
  （答案文本）、`target_step_id`（gold evidence，落入 gold evidence 字段
  供未来 recall 用）。卡片 §2.3 边界表照抄执行。

## 3. Loader 与 variant

- 数据入口 `data/membench/Membenchdata/data2test/`；结构
  `question_type → scenario_or_role → [trajectory]`（卡片 §2.3）逐层展开。
- variant 机制复用 LongMemEval 先例：`membench_0_10k`（默认，4 文件
  3400 traj）与 `membench_100k`（4 文件 860 traj）；不合并 variant run。
- smoke 裁剪语义：按 trajectory 数截断（`--conversations N` 取每文件前 N 条，
  跨 question_type 均匀采样优先简单实现为顺序前 N），**不裁 message_list**
  （trajectory 本身短，0-10k 为 4-193 steps，整条跑）。

## 4. Reader 与 Evaluator

- **只有 unified 口径**：十个 method 均无 MemBench 官方 prompt（新 benchmark），
  prompt 三级来源命中第 1 级——采用官方 active path `INSTRUCTION_FIRST`
  （决策点 B 定案），framework reader 统一构造：instruction + formatted_memory
  + question + time + choices，输出选项字母。prompt 文本与选项拼接格式照抄
  官方 `MembenchAgent.py`（plan 中给出行号），不自造措辞。
- 答案解析：从 LLM 输出提取 A/B/C/D（大小写/带句号容错），解析失败记
  `invalid_choice` 并计错，不重试作答（成本可控，行为可复现）。
- **Evaluator：`membench_choice_accuracy`**——`prediction_letter ==
  ground_truth` 的 deterministic exact match，`requires_api=False`；
  复用既有 `category_breakdown` 机制按 question_type 聚合。无 LLM judge。

## 5. 协议 v3 对接与 method 兼容

- benchmark 侧只产出规范事件流；各 method 的消费粒度按 method×benchmark
  profile 实例级特化（spec v3 M-B 修订）。已知口径问题一条：OS 单角色流下
  positional pair 配对会错位（两条 user 消息成对）——**MemoryOS 等 pair 语义
  method 在 MemBench profile 下应特化为 turn 粒度**（user_input=step 文本、
  agent_response=""，与其 LoCoMo eval 的空 response 先例一致）；该口径在
  Track C 各 method 接入时逐个确认，本 spec 只锁 benchmark 侧形态。
- `RetrievalQuery`：`query_text=question`（不拼 choices——检索用问题本身；
  choices 只进 reader prompt）、`question_time=QA.time`、`purpose="qa"`、
  top_k 由 method profile 定。

## 6. 成本画像（smoke 决策用）

每 trajectory：`len(message_list)` 次 method 写入 + 1 次 retrieve + 1 次
reader LLM；judge 零成本。0-10k 极小 smoke（如 2 traj/文件 × 4 文件 = 8 格）
的 reader 调用仅 8 次，成本主要在 method 侧 ingest（卡片 §6.5）。

## 7. 验收标准（实施 plan 的总纲）

1. loader 单测：文件结构展开、tid 唯一性断言、step_id/target_step_id 对齐
   抽样核对、私有字段隔离（`validate_no_private_keys` 全绿）。
2. fake provider 走通 registered prediction → evaluation 全链路，
   `membench_choice_accuracy` 与 category_breakdown 正确。
3. 全量回归 ≥771 passed；`predict smoke` 支持 membench + variant 选择。
4. 真实极小 smoke（用户确认预算后）：1-2 method × 2 traj，交叉核对
   accuracy 与人工判定一致。

## 8. 未确认项

- tid 跨文件唯一性（loader 断言兜底）；target_step_id off-by-one（单测
  抽样核对）；`highlevel_rec`/`RecMultiSession` 等推荐类 question_type 是否
  全部纳入 Phase 1 聚合（默认纳入，只是 category 维度不同）——实施中若发现
  其评分口径特殊，停工上报。
