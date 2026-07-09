---
id: ws02.6
parent: ws02
status: in-progress（2026-07-09 起；Phase A 机械修复推进中）
created: 2026-07-09
---
# ws02.6 首次真实 smoke 加固（跑通 + 可信双门）

## 为什么有这个 workstream（第一手发现）

2026-07-09 用户第一次真跑 5×5 smoke（用注册 method + 位置参数 `smoke` 形式），
一次性暴露了一批只有真跑才会现形的 bug。ws02.5 关闭的是"接口保真"前置门，本
workstream 关闭的是"**能跑通 + 数字可信**"两道门。核心教训（写进
`docs/reference/architect-playbook.md`）：**很多漏洞从实验结果里都看不出来，只有真
跑 + 逐条第一手核代码才现形——二手结论（cc/opencode/deepseek）必须证伪/证实，不
照单全收。**

## 锁定决策（用户拍板 + 架构师裁决，2026-07-09）

1. **输出布局**：位置参数 `smoke/formal` 是唯一正规入口 → 分层
   `outputs/runs/{method}/{benchmark}/{mode}/{run_id}`。**废弃 `--profile` 旗标**
   （用户同意）。Phase A 已先把 legacy `--profile` 也改成 hierarchical（杜绝扁平
   散落）；旗标彻底删除另起 actor 卡（涉及 legacy-only 组合的测试删改）。
2. **answer LLM prompt 默认 unified**（用户拍板第 3 点）。理由：**记忆模块的职责
   是返回记忆，不是自己拼 answer prompt**；unified = benchmark 官方 prompt = 同一
   把尺子，跨 method 才可比。**native 保留为可选对照**（`--prompt-track native`）。
3. **answer LLM 模型+配置：同一 benchmark 下所有 method 必须一致**（用户强调）。
   → `resolve_answer_llm_settings` 现在按 `(method, benchmark)` 返回不同
   temperature/max_tokens/role，**这是公平性 bug**，改为按 benchmark 归一（与
   unified prompt 同源，Phase B）。
4. **smoke 裁剪轴**（用户拍板第 2 点）：隔离空间可裁（locomo=conversation、
   membench=tid）；隔离空间内部——**对话流（第一人称）裁 round，membench 第三人称
   裁 turn**。membench 还要能选跑哪几个源文件（`--membench-sources`，不用
   `1/12/13` 拼字符串）。
5. **smoke 只看跑通、不看答对**：不为"不可回答 smoke""跨 session/round 越界"等
   极端边界写重兜底，越界就 clamp + warning，不崩即可。重兜底留给 full。
6. **turn-level resume 废弃**（架构师赞成）：状态机复杂、只个别 method 支持、smoke
   不需要、full 用 conversation 级 resume 已够。ws03 正式移除，先标 deprecated。
7. **网络兜底统一**：框架 client 与 answer LLM 统一 `60s / 8 次`。
8. **注入粒度跟随 method 原生接口**：拆分（session→pair/turn）由框架
   GranularityAggregator 做，不由 adapter 私拆；异常 session（assistant 先说/连续
   同角色/落单）打 `orphan`/`dangling` 标记但**不丢弃**（否则丢 haystack 干扰信息）。

## 逐条核对（一手证据，标注真伪）

| # | 问题 | 结论 | 根因 | 归属 |
|---|------|------|------|------|
| 1 | 结果扁平存放 | 真（历史遗留双入口）：legacy `--profile`→flat，位置参→hierarchical | `cli/main.py:496` vs `:563` | ✅Phase A |
| 2 | BEAM 直接崩 | 真：指纹把目录当文件 open | `storage/fingerprint.py:75` | ✅Phase A |
| 3 | halumem 4 method 全崩 "active scope" | 真且更重：`operation_level.py` 根本没接效率 collector/scope，provider 仍记录→崩 = **halumem 零效率数据** | `runners/operation_level.py:49`（无 scope） | Phase B |
| 4 | lightmem×membench 崩 | 真，membench adapter 的锅：把 `turn_time/session_time` 全塞 None，但数据每 turn 尾有 `(place…; time…)` | `benchmark_adapters/membench.py:523/466`；`lightmem_adapter.py:1418` | Phase B |
| 5 | locomo/longmemeval 走 native 不走 unified | 真：registry 只给 membench/halumem/beam 设 unified | `benchmark_adapters/registry.py:231,509-538` | Phase B |
| 6 | 网络重试不一致 | 真：框架 30s/2，answer 60s/8 | `config/settings.py:19-22` | ✅Phase A |
| 7 | "LLM 调用次数未聚合" | **❌ opencode 错**：`aggregate_efficiency` 有 `call_count`（stage×model + by-conv + by-question） | `analysis/efficiency.py:48,138,278,290` | 无需改 |
| 8 | lancedb 没进依赖 | 真：opencode 只 `uv pip install`，没进 pyproject | `pyproject.toml` | ✅Phase A |
| 9 | protocol_version typo 静默通过 | 真：`_validate_protocol_version` 无 else 分支 | `runners/prediction.py:1249` | ✅Phase A |
| 10 | answer LLM 各 method 不一致 | 真（公平性 bug）：按 (method,benchmark) 返回不同参数 | `config/settings.py:242-287` | Phase B（并入 unified） |
| 11 | sentinel 泄漏给 answer LLM | 真但**latent**：只在 LegacyProviderBridge 触发，5 个 method 全是 v3，当前不触发 | `core/provider_bridge.py:83` | Phase B |

opencode 其余待核项（A-Mem `str(context)`、token 双来源、items=None、Mem0 无
`clean_failed_ingest_state`、框架级 ingest/retrieve 重试）**尚未逐一验证，不采信**，
放进 Phase B 审计卡逐条证伪/证实。

## 效率指标现状（一手，回答用户"是否完善"）

**已落地 4 类原始 observation（`observability/efficiency/entities.py`）**，覆盖用户
要的三大类：① 记忆构建延迟（`ConversationEfficiencyObservation`）+ memory_build
阶段 token；② 检索延迟 + `injected_memory_context_tokens`（=formatted_memory
token）；③ 每次 LLM 调用一条 `LLMCallObservation`（次数可聚合）。
`MeasurementSource` 已区分 `API_USAGE`/`TOKENIZER_ESTIMATE`——**"能拿 api_usage
就不估计"这条规则 schema 已支持**。

**两个洞**：
- **洞 A（已确认）**：halumem operation-level runner 零效率观测（见 #3）。
- **洞 B（待逐 adapter 审计）**：method 内部 LLM 调用（记忆构建那步）由第三方库自己
  发请求，要拿真实 api_usage 必须 adapter 拦截响应——每个 method 实现不同，很可能
  有的只填了 tiktoken 估算。Phase B 核心审计卡。

## 计划分期

**Phase A — 解阻断 + 机械修复（架构师直接改）**
- [x] BEAM 指纹支持目录（walk+sorted hash） — `storage/fingerprint.py`
- [x] protocol_version fail-fast else 分支 — `runners/prediction.py`
- [x] 网络重试统一 60s/8 — `config/settings.py`
- [x] lancedb 进 pyproject（0.34.0 floor） — `pyproject.toml`
- [x] legacy `--profile` 输出改 hierarchical（footgun 消除） — `cli/main.py`
- [ ] `--profile` 旗标彻底删除（actor 卡：删/改 legacy-only 测试）

**Phase B — 可信度门（actor 卡，架构师写 spec + 验收）**
- [ ] halumem operation-level runner 接效率观测（补 halumem 效率数据）
- [x] membench adapter 解析 `(place; time)`→`turn_time`（不改 text，双写；session_time
  兜底取首个带时间戳 turn）— 架构师直接改，解掉 lightmem×membench 阻断
- [ ] locomo/longmemeval 补 unified_prompt_builder（官方模板）+ 默认 unified
- [ ] answer LLM 配置按 benchmark 归一（跨 method 一致）
- [ ] 效率完备性逐 adapter 审计（api_usage vs 估计）+ formatted_memory 一致性
- [ ] membench 裁剪重设计（`--membench-sources` + 第三人称 `--turns`）
- [ ] sentinel 泄漏改中性占位

**Phase C — 面向 full 的健壮性（不阻塞 smoke）**
- [ ] A-Mem 迁移到通用版 `third_party/A-mem`（正式迁移，像 MemoryOS）
- [ ] resume 两模式落文档 + turn-level resume 标 deprecated（ws03 移除）
- [ ] Mem0 `clean_failed_ingest_state`、框架级 ingest/retrieve 重试（逐条先核）

## #6 halumem 效率 runner —— 第一性原理实现设计（2026-07-09 已定，待施工）

**第一性原理**：效率指标是 benchmark 无关的同一套；halumem 崩+无数据的根因是它走
独立 `operation_level.py`，整套 scope/observation 机制没接。正解 = 让 operation-level
runner 参与**和标准 runner 完全相同**的 scope/observation 机制，而不是绕过或特殊化。

**已第一手核实的两个硬约束**：
1. **必须保留 per-session 交错**（ingest→extraction→update-probe→该 session 的 QA→下一
   session）。官方 `eval/eval_memzero.py:168-256` 就是这个交错顺序，记忆累积、QA-after-
   session-N 只看 1..N。**不能重构成"先全 ingest 再全 QA"**——那会改变 halumem 的
   update/hallucination 语义（答案对错依赖 ingest 时序）。
2. **observation_id 会撞**。`storage.py:94-120` 按 id 幂等合并、**同 id 不同内容直接
   raise**；`_aggregate_observation_id` 用固定 `call_index=0`。per-session 开
   conversation_scope（同 conversation_id）→ 每 session 的 memory_build observation
   id 相同、latency 不同 → 致命冲突。LLM/embedding call 同理（每个 scope 的
   call_index 从 0 重置）。

**实现步骤**：

- **S1 collector 加 scope discriminator 原语（backward-compatible）**：
  `conversation_scope`/`question_scope`/`_scope` 加可选 `scope_discriminator: str|None=None`，
  存入 `_ScopeState`，在 `_build_observation_id` 里**仅当非 None 时**才塞进 payload
  （None 时 payload 不变 → 标准 runner 的 id 一字不改，无测试/resume 破坏）。
  operation-level 传 `session_id` → 每 session 的 id 唯一。conversation_id 字段保持
  干净（不塞 session），by-conversation 聚合仍按 conversation_id 求和（正确总量）。
- **S2 wire collector/store 进 operation-level runner**：
  `run_operation_level_predictions` 签名加 `efficiency_collector`、`model_inventory`、
  `instrumentation_identity`；`run_prediction.py:645` 的 dispatch 把它们传进去（标准路
  径 658-669 已有，照抄）。enabled 时建 `EfficiencyArtifactStore.for_prediction(paths)`
  + `write_model_inventory`。
- **S3 `_run_operation_conversation` 交错开 scope**（每个 provider 调用都要在某个 scope 内，
  否则 "requires active scope" 复现）：
  - 每 session：`with conversation_scope(conv_id, scope_discriminator=session_id)`：
    包住该 session 的 `ingest` + `end_session` + update-probe `retrieve`（默认 stage
    =memory_build），计时后 `record_memory_build_total_latency`。
  - 每 question：`with question_scope(conv_id, question_id)`：
    `operation_stage(RETRIEVAL)` 包 qa `retrieve` + `record_retrieval_result`
    （latency + injected_memory_context_tokens）；`operation_stage(ANSWER)` 包
    `generate_answer` + `record_answer_generation`。
  - `end_conversation`：包一层 `conversation_scope(conv_id, scope_discriminator="end")`
    并 record 一个 memory_build latency（捕获 flush 期可能的 LLM 调用）；`cleanup`
    是 teardown，留在 scope 外（若某 provider 在 cleanup 里 record，视为该 adapter 的 bug）。
  - 每个 scope 退出后把 `scope.records` 收集，`efficiency_store.merge_observations(...)`。
- **S4 测试**：operation-level 一条 conversation 多 session，断言：①不再崩；②产出
  per-session ConversationEfficiencyObservation（id 唯一）；③per-question
  QuestionEfficiencyObservation 带 retrieval/answer latency；④by-conversation 聚合
  latency = 各 session 之和。用 fake provider（可控 record）避免真实 API。

**注意**：injected_memory_context_tokens 的口径要和标准 runner 一致（用同一
`_count_answer_context_tokens` 或 adapter 上报），避免 halumem 与其它 benchmark 的
token 口径不一致——这条并进 Phase B #10 效率完备性审计一起验。

## 项目细节.md 全量映射（确保一条不落，用户 2026-07-09 强调）

用户在 `项目细节.md` 列的 17 条 + 跨消息的要求，逐条归位（**不遗漏**）：

| 项目细节# | 内容 | 归位 | 状态 |
|-----------|------|------|------|
| 1 | 效率指标 3 类（构建延迟+token/检索延迟+token/LLM 次数）+ token 必须 api_usage 非估计 | #6（halumem）+ #10（逐 adapter api_usage 审计） | S1 done，余待做 |
| 2 | answer LLM prompt 默认 unified | #8 | 待做（决策已定：默认 unified，native 可选） |
| 3 | smoke 裁剪：隔离空间可裁 + 内部 round(第一人称)/turn(第三人称)；**halumem 改主意：不再单独 session 级裁剪**（不裁也能跑 extraction 算指标，smoke 只看跑通）；membench 要能选跑哪几个源文件 | #11 + halumem 裁剪重审 | 待做 |
| 4 | 网络兜底：所有 API 调用处都要有超时兜底 + 统一 | Phase A 重试常量统一（done）+ #13 框架级 ingest/retrieve 重试 | 部分 done |
| 5 | formatted_memory 一致性（时间戳/地点等附带信息公平）+ A-Mem str(context) 不可审计 + token 双来源 + items=None | #10 | 待做（逐条证伪/证实 opencode） |
| 6 | **max_workers 默认 1（smoke+full 都是），不设上限，CLI 可覆盖**；配置文件只放 method 可调超参 | 新增 #14a（config/CLI） | **新捕获**，待做 |
| 7 | resume：smoke 不 resume；full 两模式（全量 / 最大隔离空间数）；failed 默认不重试除 `--retry-failed`；turn-level resume 废弃 | #12 + turn-level deprecate | 待做（落文档设计） |
| 8 | 并行：当前隔离空间级并行，未启并发 | 现状确认 | 无需改 |
| 9 | CLI v2（smoke/official-full 互斥等边界） | 已落地 | done |
| 10 | **异常处理：致命异常要捕获详细信息 + 写日志便于 debug** | 新增 #14b（可观测性/异常） | **新捕获**，待做 |
| 11 | 每个 turn 有自己时间戳，无则用 session | #7（membench 已做）+ 通用原则 | membench done |
| 12 | sentinel 泄漏 + LLM 次数已聚合(opencode 错) + smoke_round_limit 对非 locomo 语义 | sentinel→Phase B；LLM 次数已澄清；round_limit→#11 | 部分澄清 |
| 13 | longmemeval 异常 session（顺序倒/连续同 role/单 role）+ memoryos-pypi pair 注入 | 决策 #8（orphan/dangling 标记不丢，框架拆分） | 待做 |
| 14 | **recall@k 等检索级指标：需 method 返回 evidence（turn/session/step id）** | 新增 #14c（需 method 侧支持，较大，可能独立 workstream） | **新捕获**，待评估 |
| 15 | 注入粒度跟随 method 原生接口，拆分由框架做 | 决策 #8 | 待做 |
| 16 | membench 第三人称若 method 原生不支持 turn 级注入怎么办 | 并入 #15/决策 #8 | 待评估 |
| 17 | 其它细节实验中碰壁再补 | 持续 | — |

**新捕获的 #14a/b/c（之前计划遗漏，现补入）**：
- **#14a**：`max_workers` 默认 1（smoke+full），无上限，CLI `--workers`/`--smoke-max-workers`
  覆盖；配置文件只放 method 可调超参。（Phase B/C，需核实现状 CLI 是否已支持覆盖。）
- **#14b**：致命异常统一捕获详细信息（traceback + 上下文）并落 run 日志。（Phase C 可观测性。）
- **#14c**：retrieval-level 指标（recall@k）需 method 在 retrieve 时返回 evidence
  （turn/session/step id，各 benchmark 口径不同）。**依赖 method 侧支持**，是较大能力项，
  可能独立 workstream；先记账，评估后再排期。

## 未来：新 method/benchmark 接入检测流程（用户提议）

用户提议做一个可自动运行的"接入体检"（可用 LLM 跑）：新 method/benchmark 接入后
自动检测潜在漏洞，例如**检测 method 的 token 记录是否用了 api_usage 而非估计**、
formatted_memory 是否可审计、注入粒度是否与原生接口一致等。记入 ws06 或独立
workstream，作为"施工规范"的可执行版。

## 进度日志

- **2026-07-09**：建 workstream。Phase A 落 5 项（BEAM 指纹目录、protocol fail-fast、
  重试统一、lancedb 入依赖、legacy `--profile`→hierarchical），commit `d8200e4`，
  804 passed。
- **2026-07-09**：Phase B 先解剩余阻断 #7——membench adapter 内嵌时间戳解析
  （`benchmark_adapters/membench.py:_membench_turn_time` + session_time 兜底），
  加回归测试 `test_membench_extracts_embedded_turn_time_and_session_fallback`，
  commit `33422a6`，805 passed。
- **2026-07-09**：#6 第一性原理调查完成（核实官方 eval 交错语义不可 2-phase、
  storage 层 id 冲突约束），实现设计定稿写入本文档。落 **S1**（collector scope
  discriminator 原语，backward-compatible，`observability/efficiency/collector.py`
  + 单测）。剩 S2/S3/S4（operation-level runner 接线 + 交错 scope + 测试）下轮做，
  作为 #6 的第二个连贯 commit。
