---
id: ws02.6
parent: ws02
status: in-progress（LoCoMo、LongMemEval、MemBench、BEAM 已 frozen-v1；B5 HaluMem 未开工）
created: 2026-07-09
---
# ws02.6 首次真实 smoke 加固（跑通 + 可信双门）

## 当前冻结与设计断点（2026-07-11）

- 2026-07-11（H1 Q3 停工 → **架构师已裁决**，actor=codex+GPT-5.6）：官方
  五脚本 QA prompt 异构，实际语义两族——严格记忆族 3/5（MEMZERO×2+ZEP）
  vs 宽松族 2/5（MEMOS 允许 world knowledge，`prompts.py:89`）；架构师
  另实锤 `PROMPT_MEMOBASE` 是**死代码**（memobase 脚本 import MEMZERO，
  跨 benchmark 第三个死代码案例）。**裁决：canonical = PROMPT_MEMZERO
  逐字**——多数派语义 + 幻觉评测主旨（只依据记忆是幻觉可判定的前提，
  world knowledge 放宽与测量目标自相矛盾）+ 公平性；与官方 MemOS/
  Supermemory 数字的 prompt 偏差进冻结声明。裁决全文见
  [actor-prompt-h1.md](actor-prompt-h1.md) 末尾，actor 复工。
- 2026-07-11（**BEAM `frozen-v1`，B4 完成**）：E1-E5 五批（codex+GPT-5.6
  ×4、cc+MiniMax M3 ×1）+ 架构师逐批强验收；三次停工全部停对（Q2 反例、
  预埋断点、E4 卡口径错——那次纠正的是架构师）。B4 战果：10M 异构 variant
  接纳（plan-dict 展开）、evidence 三形态 + `'--'` + 重复 id 官方数据
  异常全裁决、官方有效评测面判定（零嵌入零 BLEU，event_ordering 走 LLM
  对齐）、int 截断实锤 → float+official_int 双轨、官方 commit 首次可锁。
  冻结门：**1025 passed** + compileall + 真实数据验证 + 泄漏 CLEAN +
  零真实 API。冻结记录 [beam-frozen-v1.md](notes/beam-frozen-v1.md)。
- 2026-07-11（**论文指标覆盖，用户新要求，对 5 benchmark 生效**）：各
  benchmark 论文报告的指标必须覆盖；扩展指标可做但不许乱做（如 NDCG
  需逐项相关性可定义才行）。盘点：LoCoMo（F1+recall ✅）、BEAM（10 类
  rubric 双轨 ✅）、HaluMem（B5 模板项）；**两个缺口立项**：
  ① `longmemeval-ndcg@k` + `recall_all`（官方 `eval_utils.py:12-29`
  一手实锤，ranked items 已在 artifact，artifact-only 可算）；
  ② membench **源文件维度聚合**（论文按 Factual/Reflective ×
  First/Third 报 = first_high/first_low/third_high/third_low 四格，
  conversation_id 前缀天然携带该维度，聚合即可）。两项均为**加法**
  （新 evaluator/summary 维度），不触发 frozen-v2；排 B5 后的 F 批或
  并入 B6 横向验收，spec §9 验收标准同步补条目。

- 2026-07-11（E4 停工 → **架构师已裁决**，actor=codex+GPT-5.6）：actor
  开工核证发现 event_ordering 实际走 `align_type="llm"`（成对
  `llm_equivalence`），与 E4 卡的 semantic/all-MiniLM 口径冲突——**卡是
  架构师错**（读签名默认值没读实际调用点）。架构师随后核完全部辅助函数
  调用链：**官方有效评测面 = 9 类纯 rubric judge + event_ordering 的
  judge+τ×F1（LLM alignment）；嵌入/BLEU/ROUGE/fact-level 全部是分发链
  之外的死代码**。裁决：alignment 跟官方实际 LLM 路径（semantic 作废）；
  extract_facts 死代码 quirk 留档，有效行为=split("\n")；int 截断实锤
  （prompt 定义 0.5 档）→ 主分 float 已声明偏差 + 并报官方 parity int
  聚合；**方法论规矩第二次被证明：parity 审计必须核实际调用点**。裁决
  全文见 [actor-prompt-e4.md](actor-prompt-e4.md) 末尾，actor 复工。
- 2026-07-11（**MemBench `frozen-v1`，B3 完成**）：D1-D5 五批 actor 施工
  （DeepSeek V4 Flash ×2、混合路由 ×1、MiniMax M3 ×2）+ 架构师逐批强
  验收。B3 战果：**3 个 latent bug 实锤修复**（第三人称无冒号时间戳
  19,285 条全漏配、空 target_step_id 令 full load 必崩、evidence 0/1 基
  off-by-one）+ 1 次编造纠正（repo URL）+ 1 次教科书级停工（recall 读
  键位 vs 生产序列化）。冻结门：**1000 passed** 全量 + compileall +
  真实数据抽查（+1 平移三态/str-list 两态/100k 加载/无冒号 turn_time
  e2e 非空）+ 公开泄漏扫描 CLEAN + 零真实 API。冻结记录
  [membench-frozen-v1.md](notes/membench-frozen-v1.md)，批次过程
  [plan-b3-membench.md](plan-b3-membench.md)。已知偏差两条（官方
  json_schema 结构化输出、answer 参数不可考）见冻结记录 §7。当前没有
  开放 actor 卡；下一步 B4 BEAM 由架构师先写 plan 再经用户确认派工。
- 2026-07-11（B4 plan 就绪 + E1 开卡）：[plan-b4-beam.md](plan-b4-beam.md)
  基于当日一手取证起草。核心事实：用户先验核实为真——100K/500K/1M 同构
  （20/35/35 conv），**10M 异构**（10 conv，各带 plans×10 每 plan 独立
  chat）且 **10M variant 未注册**（B4 最大新增项）；10 类问题 × 每类
  2 题 × 100 conv = 2,000 题对上论文；每题 rubric + source_chat_ids
  evidence + 按类异构 gold 字段；turn/user_questions 均带 time_anchor；
  `probing_questions` 须 ast.literal_eval；官方 metric = rubric LLM
  judge 浮点分 + event_ordering 的 Kendall τ×F1（嵌入阈值 0.65）；现有
  beam_rubric_judge 自述"修正官方 int 截断 bug"的主动偏差待 E4 核证。
  用户拍板：变体全接纳、smoke 覆盖 100k+10m、每类指标分开报。E1 卡含
  两个强制判定（10M 消费方式、evidence id 空间）。

- 2026-07-11（D5 停工 → **架构师已裁决并直修**）：actor（cc+MiniMax M3）
  在 D5 T0 对照真实生产 artifact，发现 D4 `membench-recall` 读
  `metadata["evidence"]`，但 `evaluator_private_label_record` 把
  `GoldAnswerInfo.evidence` 序列化在**顶层**（LoCoMo recall 读法正确，
  D4 错位模仿了 LongMemEval 的 metadata 键）；D4 的手写 fixture 把
  evidence 同时塞两处导致单测自洽假绿。三项证据架构师逐字复核为真——
  **同时暴露架构师 D4 验收盲区（没对生产序列化形状验）**。裁决 = 选项 a
  的架构师执行版：① `membench_recall.py` 改读顶层（+注释钉死键位出处）；
  ② fixture 改为**通过真实 `evaluator_private_label_record` 构造**，
  形状漂移结构性不可能（此法固化为 evaluator 契约测试通用规矩）；
  ③ D5 卡一字不改，actor 复工。停工质量：0 行越权代码、证据带
  文件:行号、三选一方案——教科书级。

- 2026-07-10（LongMemEval `frozen-v1`，B2 完成）：C1-C5 五批 actor 施工
  （cc+GLM-5.2 × 2、codex+GPT-5.6 × 3）+ 架构师逐批验收，一次停工裁决
  （turn gold 通路）、两次架构师勘误（role 计数算术错、匹配键 id 空间）。
  冻结门：**923 passed** 全量 + compileall + 真实数据抽查（abstention/
  异常 role/`_m` 流式）+ 公开泄漏扫描 CLEAN + 零真实 API。冻结记录见
  [longmemeval-frozen-v1.md](notes/longmemeval-frozen-v1.md)，批次过程见
  [plan-b2-longmemeval.md](plan-b2-longmemeval.md)。**已知偏差：judge 用
  gpt-4o-mini（论文 gpt-4o）**。当前没有开放 actor 卡；下一步 B3 MemBench
  由架构师先写 plan 再经用户确认派工。
- 2026-07-10（smoke 设计原则升级，用户拍板）：**smoke = 最小路径覆盖切片**
  ——先枚举 benchmark 的运行时路径清单（runner/provider 交互分叉），标准
  smoke 全覆盖；离线分支归契约测试。默认口径 = 唯一认证口径，CLI 旋钮只作
  调试。已写入 spec §6.7。B1/B2 用新尺回核：均单运行时路径，frozen-v1
  仍成立，不返工。
- 2026-07-10（B3 plan 就绪）：[plan-b3-membench.md](plan-b3-membench.md)
  基于当日一手取证起草，含一个**现场实锤的 latent bug**：第三人称
  LowLevel 数据 19,285 条消息时间格式无冒号（`time'…'`），#7 的正则
  （`membench.py:498`）全部漏配——官方数据两文件格式不一致，#7 只在第一
  人称上验证过。D1-D5 五批 + 冻结；**未派工，等用户确认**。

- 2026-07-10（架构师回任 Fable 5 + B2 plan 就绪）：接任第一手核查复现
  890 passed；GPT-5.6 验收修正经用户批准落盘（`2965037`）。用户拍板三项：
  ① 新增通用 `f1` evaluator、`locomo-f1` 保持官方 parity 原名；② 可复现性
  身份=内容，路径只作记录（已修，`b7599a9`，891 passed，playbook 原则 #12）；
  ③ 真实校准不急，smoke 跑通即可拿预算。B2 LongMemEval plan 已基于当日
  一手取证起草：[plan-b2-longmemeval.md](plan-b2-longmemeval.md)（数据形态/
  官方 answer+judge 契约/框架缺口全部现场核实），**未派工，等用户确认**。
- 2026-07-10（LoCoMo `frozen-v1`）：A6 actor commit `6f0039f` 只新增一条离线
  registry/probe 全链路；架构师复跑 `4 passed in 2.86s`，定向总验收
  `326 passed in 31.80s`，compileall 通过，全量回归在修正一条 2026-06 的旧
  MemoryOS/LoCoMo answer 参数断言后为
  `890 passed, 3 deselected, 2 warnings, 4 subtests passed in 143.70s`。冻结记录见
  [locomo-frozen-v1.md](notes/locomo-frozen-v1.md)。当前没有开放的 actor 卡；不得提前
  施工 LongMemEval，下一步先由架构师写 B2 plan/prompt 再交用户确认。
- 2026-07-10（A5 架构师验收）：actor commit `64d2651` 完成 LoCoMo artifact-level
  retrieval recall 与 auxiliary judge 身份；架构师补齐未声明 provenance=N/A、artifact
  question ID 对齐、空 source ids fail-fast 三个边界后，A5 定向复验
  `133 passed in 3.60s`。A5 已关闭；下一批唯一入口为
  [actor-prompt-a6.md](actor-prompt-a6.md)，只补一条离线注册链路并复用既有 resume 测试。
- 2026-07-10（A4 架构师验收）：actor commit `3c68c5d` 完成最小 smoke + LoCoMo
  unified answer；架构师修掉 evidence 派生的 public metadata 泄漏后复跑 A4 定向测试
  `139 passed in 25.32s`，并抽查真实 URL+caption/caption-only turn。A4 已关闭；下一批
  唯一入口为 [actor-prompt-a5.md](actor-prompt-a5.md)，只做离线 metric，不碰 A6。
- 2026-07-10（额度纠偏）：actor 已完成 T1-T3（`1341cb1`、`edefd9a`、`7600076`）
  后按用户要求暂停。架构师完成关键 diff 审读、两处 T3 直修与定向复验
  （`254 passed in 31.48s`），T1-T3 已验收，不再交 actor 重跑。原 10-task 重型 plan
  已改为额度友好 v2：剩余只分 A4/A5/A6 三批，每批一个 5h 窗口内完成；actor 只施工
  + 一次定向自检，架构师负责验收/全量/冻结。下一批唯一入口是
  [actor-prompt-a4.md](actor-prompt-a4.md)。
- 2026-07-10（新任架构师 GPT-5）：完成接任第一手核查：`uv run pytest -q`
  实测 `807 passed, 3 deselected, 2 warnings`，compileall 通过；测试被确认是
  “现行契约 + 兼容行为 + 历史断言”的混合证据，不能单独作为黄金标准。
- 只读核查 2026-07-09 真实实验资产：16 个带 manifest 的新 run 中 10 个有最终
  summary、6 个没有；HaluMem 四格均无 summary，BEAM/A-Mem 未进入这批真实尝试；
  已完成 LoCoMo/LongMemEval 仍为 native prompt。因此本文原“25 格阻断全部清零”
  只保留“已修复已知代码阻断”的含义，不代表 25 格已经验证。
- 用户批准“放慢脚步”：未来 method/benchmark 必须先完成官方仓库一手审计、接口
  选择与排除理由、特殊处理、效率观测设计、真实数据离线契约验证，再允许写实现
  plan 或申请真实 API。
- 用户进一步批准“先稳定一边”：先把五个 benchmark 当作测量仪器，按
  **LoCoMo → LongMemEval → MemBench → BEAM → HaluMem** 严格串行整治；每个都要
  彻底核清官方资产、真实数据、执行流程、公私边界、prompt/metric、smoke、resume、
  artifact 与效率口径并经架构师冻结，前一个未验收，后一个不开工。五个全部冻结
  后 method 侧才解冻。
- 当前冻结：不新增 method/benchmark，不运行新真实 API smoke，不启动 full，不批量
  重写 tests。正式设计 [spec.md](spec.md) 已于 2026-07-10 获用户批准；LoCoMo B0+B1
  已按 [plan](plan-b0-b1-locomo.md) 达到 `frozen-v1`。B2 LongMemEval 尚未写 plan，也
  未向 actor 派工。

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
- [x] halumem operation-level runner 接效率观测（S1 discriminator 原语 + S2 wiring +
  S3 交错 scope + S4 测试）— 架构师直接做，25 格阻断清零，807 passed
- [x] membench adapter 解析 `(place; time)`→`turn_time`（不改 text，双写；session_time
  兜底取首个带时间戳 turn）— 架构师直接改，解掉 lightmem×membench 阻断
- [x] LoCoMo 补 unified_prompt_builder（官方模板）+ 默认 unified；LongMemEval 待 B2
- [x] LoCoMo answer LLM 配置按 benchmark 归一（跨 method 一致）；其他 benchmark 待各卡
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
  + 单测）。
- **2026-07-09**：#6 **S2–S4 完成**——`operation_level.py` 接 efficiency_collector/
  model_inventory/instrumentation_identity + 建 EfficiencyArtifactStore；
  `_run_operation_conversation` 拆出 `_ingest_and_probe_session`/
  `_answer_operation_question`，per-session conversation_scope（discriminator=session_id）
  + per-question question_scope，效率口径对齐标准 runner 的
  `_answer_question_retrieve_first`（api_usage 优先）；`run_prediction.py` dispatch 传参；
  加 `test_halumem_operation_level_records_efficiency_observations`。**807 passed，
  25 格 smoke 阻断全部清零**。
- **2026-07-09**：架构师角色交接 Claude→GPT-5.6，写
  `docs/reference/architect-onboarding.md`（跨模型冷启动上岗手册）。
