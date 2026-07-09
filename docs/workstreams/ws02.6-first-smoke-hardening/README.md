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
- [ ] membench adapter 解析 `(place; time)`→`turn_time`（不改 text，双写）
- [ ] locomo/longmemeval 补 unified_prompt_builder（官方模板）+ 默认 unified
- [ ] answer LLM 配置按 benchmark 归一（跨 method 一致）
- [ ] 效率完备性逐 adapter 审计（api_usage vs 估计）+ formatted_memory 一致性
- [ ] membench 裁剪重设计（`--membench-sources` + 第三人称 `--turns`）
- [ ] sentinel 泄漏改中性占位

**Phase C — 面向 full 的健壮性（不阻塞 smoke）**
- [ ] A-Mem 迁移到通用版 `third_party/A-mem`（正式迁移，像 MemoryOS）
- [ ] resume 两模式落文档 + turn-level resume 标 deprecated（ws03 移除）
- [ ] Mem0 `clean_failed_ingest_state`、框架级 ingest/retrieve 重试（逐条先核）

## 未来：新 method/benchmark 接入检测流程（用户提议）

用户提议做一个可自动运行的"接入体检"（可用 LLM 跑）：新 method/benchmark 接入后
自动检测潜在漏洞，例如**检测 method 的 token 记录是否用了 api_usage 而非估计**、
formatted_memory 是否可审计、注入粒度是否与原生接口一致等。记入 ws06 或独立
workstream，作为"施工规范"的可执行版。

## 进度日志

- **2026-07-09**：建 workstream。Phase A 落 5 项（BEAM 指纹目录、protocol fail-fast、
  重试统一、lancedb 入依赖、legacy `--profile`→hierarchical）。CLI 测试 73 passed；
  full 回归见断点。Phase B/C spec 卡待写。
