---
id: ws02.6
doc: spec
status: approved
created: 2026-07-10
---
# ws02.6 实验可信度门设计

> 2026-07-10 用户批准本设计，并要求从 LoCoMo 开始逐个 benchmark 慢速整治。
> 首张执行卡为 [plan-b0-b1-locomo.md](plan-b0-b1-locomo.md)。

## 1. 背景与问题定义

本项目此前推进过快，把“代码能执行”“测试全绿”“真实 run 生成了目录”和
“实验结果可信”混在了一起。2026-07-10 新任架构师第一手复核得到：

- `uv run pytest -q` 实测为 `807 passed, 3 deselected, 2 warnings`，但测试同时
  包含现行契约、兼容行为和已经决定废弃的历史行为，不能单独充当黄金标准；
- `uv run python -m compileall -q src/memory_benchmark tests` 通过，只证明语法与
  导入层面没有显式错误；
- 2026-07-09 的真实实验资产中共有 16 个带 manifest 的新 run，10 个有最终
  summary、6 个没有；HaluMem 四格均无 summary，BEAM 与 A-Mem 没有进入这批
  真实尝试；
- 已完成的 LoCoMo / LongMemEval run 仍使用 `native` prompt，而当前实验主线要求
  `unified`；
- LoCoMo / LongMemEval 尚未注册 unified prompt builder，answer LLM 配置仍按
  `(method, benchmark)` 分叉；
- SimpleMem 的真实效率 observation 中，method 内部 LLM token 大量来自
  `tokenizer_estimate`，现行 wrapper 也明确丢弃 API usage；
- roadmap、ws02、ws02.6、method interface inventory、onboarding 与代码之间存在
  多处状态和政策漂移。

因此，ws02.6 从“修掉首次 smoke 暴露的几个阻断”升级为 Phase 1 的
**实验可信度门**。在本门通过前，不得把“25 格已解阻”写成“25 格已验证”，也
不得用现有 smoke 结果申请全量实验预算。

## 2. 目标

本 workstream 要回答五个问题：

1. 现行四步主线是否真的由代码完整执行：`ingest → retrieve → framework answer → metric`？
2. 同一 benchmark 下是否只有 method 的记忆质量在变化，prompt、answer LLM 与
   evaluator 是否 method 无关？
3. 每个 method 是否忠实使用官方通用产品接口，必要的特殊处理是否有一手证据？
4. 每个 benchmark 是否忠实使用官方数据、执行顺序、answer/judge prompt 与 metric？
5. 测试与效率 observation 是否足以支持“可运行、可比较、可审计”的结论？

完成后输出：

- 一份可审计的 5×5 离线契约矩阵；
- 一份真实 run 事实总账；
- 五个现有 method 的接口/特殊处理/效率观测复核结论；
- 五个 benchmark 的数据流/prompt/evaluator 复核结论；
- 一份测试分类清单与缺失契约测试清单；
- 一个经用户批准后可执行的最小真实校准方案。

## 3. 当前冻结边界

本 spec 获批并完成对应 plan 前，执行以下冻结：

- 不新增 method adapter；
- 不新增 benchmark adapter；
- 不运行新的真实 API smoke；
- 不启动 full run；
- 不为追求测试数而批量删除或改写 tests；
- 不做与可信度门无关的架构重构；
- 不把旧 run 的成功状态外推到未运行格子。

允许的工作只有：只读核查、离线 fake/contract test、文档纠偏，以及经批准 plan
覆盖的可信度修复。

## 4. 事实源与证据等级

结论按以下优先级取证：

1. benchmark / method 官方仓库源码与真实数据；
2. 本框架当前代码、运行时 manifest、artifact、checkpoint、summary；
3. 可复现的离线契约测试与架构师亲自复跑输出；
4. workstream spec、审计卡和参考文档；
5. actor 报告、历史会话与测试名称。

低等级事实源与高等级事实源冲突时，以高等级为准，并更新产生漂移的文档或测试。
“某测试通过”只证明该测试写下的断言成立，不自动证明断言符合现行实验协议。

## 5. 三类结论必须分开

每个 method × benchmark 格子必须分别记录：

| 层级 | 含义 | 最低证据 |
| --- | --- | --- |
| 可启动 | CLI/preflight 能建立合法运行计划 | 真实 registry + 离线 preflight |
| 可运行 | 四步主线完成并写出必需 artifact | 真实 adapter/runner + API 边界 fake |
| 口径可信 | 接口、prompt、配置、metric、隐私、效率均符合协议 | 一手源码审计 + 契约测试 + artifact 审计 |

真实 API run 还需第四个层级“真实校准通过”。只有前三级全部通过，才允许申请
第四级预算。

## 6. 分阶段可信度门（单边稳定、严格串行）

本 workstream 不再同时整治 benchmark 与 method。先把 benchmark 作为“测量仪器”
逐个校准并冻结；五个 benchmark 全部通过总验收后，method 侧才解冻。同一时刻最多
有一个 benchmark 处于施工状态，前一个未验收，后一个不写 plan、不改代码。

### G0：事实与状态归一

- 读取而不修改现有 `outputs/`，建立 run 级事实总账；
- 区分 `未尝试 / preflight 失败 / ingest 失败 / prediction 完成 / evaluation 完成 /
  efficiency 完整 / 口径可信`；
- 纠正 roadmap、ws02、ws02.6、onboarding、CLAUDE.md、method inventory 中与代码或
  最新规则冲突的描述；
- 禁止用“阻断清零”代替“矩阵验证完成”。

G0 只做事实归一，不夹带任何 benchmark 或 method 行为修复。

### Benchmark Track B0：统一审计模板与中性探针

benchmark 整治不能依赖某个真实 method，否则 benchmark 契约会被该 method 的能力
反向塑形。B0 先建立 method-neutral benchmark probe：

- 从现有 `MockMemoryProvider` 出发，但不把现状直接视为正确；
- 支持 turn/pair/session/conversation 四种消费粒度；
- 完整记录 ingest payload、生命周期钩子、retrieve query、调用顺序与公开字段；
- 对任意 query 返回可预测的 `formatted_memory`、items 与 provenance；
- 可产生受控 session report，供 HaluMem 等能力门验证；
- 不包含任何真实 method 算法、benchmark 专用答案或私有 label；
- answer/judge/embedding/LLM 均使用离线 fake，零真实 API。

该探针只校验 benchmark 向 v3 协议发出了什么、框架如何答题与计分，不代表任何
Phase 1 method 的实际效果或效率。

### 每个 benchmark 的固定整治模板

LoCoMo、LongMemEval、MemBench、BEAM、HaluMem 必须分别完成以下十项，不得以已有
调研卡或测试全绿代替：

1. **官方资产锁定**：官方仓库、commit/tag、论文版本、数据文件、variant、hash、
   license 与 evaluator 入口；
2. **彻底理解数据**：扫描真实数据的 isolation/session/turn/question 结构、字段类型、
   缺失值、异常 role 顺序、时间格式、规模分布和私有字段；
3. **官方流程复原**：逐行核对数据加载、写入顺序、提问时机、answer、judge、解析与
   聚合流程，明确哪些是 runner 条件、哪些是 scorer 条件；
4. **框架映射**：给出官方对象到 canonical Dataset/Conversation/Session/TurnEvent/
   Question 的字段级映射，以及标准 runner 或 operation-level runner 的选择理由；
5. **公私边界**：列出 method 可见字段与 evaluator-only 字段，构造泄漏反例并验证
   public artifact 扫描；
6. **prompt 与 metric**：冻结 unified answer prompt、judge prompt、prediction parser、
   metric 公式、分母、N/A 路由、聚合维度和浮点精度；
7. **smoke 设计**：从 benchmark 自然结构推导 conversation/session/round/turn/source/
   question 裁剪轴，验证裁剪不会改变 method 参数、跨 variant 混 run 或悄悄改变问题语义。
   **smoke = 最小路径覆盖切片**（2026-07-10 用户拍板）：先枚举该 benchmark 的
   **运行时路径清单**（runner/provider 交互与真实 API 调用形态的分叉，如
   membench 双人称、halumem 提取/更新/QA、多源文件加载），标准 smoke 必须
   全部覆盖；纯离线分支（metric 策略、judge 模板内容等）由契约测试覆盖，
   不计入路径清单。切片选择用确定性规则（如"最小前缀使各路径 ≥1 次"），
   只读公开结构，不许"假定"。**默认口径 = 唯一认证口径**：CLI 裁剪旋钮
   （--rounds 等）保留作调试用，但偏离 policy 默认值的 run 不构成
   "smoke 通过"认证（manifest 已记录声明值与实际值，偏离可审计）；
8. **resume 设计**：从官方最小原子步骤与框架 artifact 粒度推导 checkpoint 边界，验证
   中断后的重复 ingest/retrieve/judge 风险、幂等性、失败隔离、partial artifact 修复、
   question resume 与状态型 retrieve 的关系；smoke 是否禁用 resume、formal 支持哪些
   resume 模式必须逐 benchmark 明确，不套全局模板；
9. **artifact 与效率**：定义 prediction/private label/session report/update probe/
   efficiency/summary 的粒度、主键和可重算关系；区分 benchmark answer/judge 成本与
   method 成本，不让 probe 的假调用污染正式口径；
10. **离线全链路与冻结**：用真实数据极小切片 + 中性探针跑完整链路，覆盖正常与病态
    形状；架构师复跑全部验收后产出 `frozen-v1` 记录，才允许进入下一个 benchmark。

### Benchmark Track 串行顺序

| 阶段 | Benchmark | 选择理由 |
| --- | --- | --- |
| B1 | LoCoMo | 建立标准 conversation-QA、图片 caption、分类问题和基础 prompt/metric 基线 |
| B2 | LongMemEval | 在 B1 上增加多 session、时间、异常 role、官方 generation/judge 与 evidence session |
| B3 | MemBench | 增加第一/第三人称两种消息形态、多源文件、MCQ 与 round/turn/source 裁剪 |
| B4 | BEAM | 增加大目录 variant、能力分类、rubric judge、事件排序与浮点评分 |
| B5 | HaluMem | 最后处理最复杂的 per-session 交错、extraction/update/QA 与 operation-level resume |

顺序只因复杂度递增，不表示后一个 benchmark 重要性更低。B1-B5 每个 benchmark
各写独立 plan；不得提前写下一张 plan，也不得把五个 benchmark 放进同一 actor 队列。

### Benchmark Track B6：总验收与冻结规则

五个 benchmark 都达到 `frozen-v1` 后，架构师做一次横向总验收：

- **论文指标覆盖审计**（用户 2026-07-11 拍板，对 5 benchmark 生效）：
  逐 benchmark 对照论文报告的指标清单，未覆盖的立项补齐（加法式新
  evaluator/summary 维度，不触发 frozen-v2）；扩展指标允许但必须论证
  数学前提成立（判例：NDCG 需逐项相关性可定义）。已立项缺口：
  longmemeval-ndcg@k + recall_all（官方 eval_utils.py:12-29）、
  membench 源文件维度聚合（Factual/Reflective × First/Third 四格）；

- 五套 canonical 映射在 v3 协议上不互相矛盾；
- 标准 runner 与 operation-level runner 的边界清楚；
- 五套 prompt/evaluator 均 method 无关；
- smoke/resume 参数是 benchmark-shaped，CLI 传错轴会 fail-fast；
- artifact 与 efficiency schema 可以共同汇总但不混粒度；
- 文档、registry 与代码对五个 benchmark 的声明一致。

“冻结”不是永远不可修改。后续 method 审计若发现 benchmark 契约缺口，必须提交新的一手
证据、影响分析和版本号，重跑该 benchmark 全部契约测试；禁止在 method adapter 内悄悄
打格子专用补丁。

### Method Track M0：B6 通过前冻结

B6 通过后才对 Mem0、MemoryOS、A-Mem、LightMem、SimpleMem 逐个重新核查：

- 官方仓库版本、产品入口与候选接口；
- 为什么选择当前 ingest/retrieve 接口，为什么不选 chat/ask/eval 专用入口；
- 注入粒度、finalize/flush、异步完成、状态隔离、检索副作用与 clean retry；
- 由 method 原生接口或已冻结 benchmark 通用语义驱动的特殊处理及其官方源码证据；
  per-benchmark 差异优先落在声明式 profile 或 benchmark adapter 的通用规范化层，
  任何 method × benchmark 算法分支必须停工交架构师单独审查；
- `formatted_memory` 是否覆盖官方检索返回的全部有效记忆层与时间/地点等字段；
- provenance 能力与 `items=None` 是否真实表达 method 能力；
- LLM/embedding 模型、repo 默认超参、项目统一基座与差异留痕；
- 记忆构建、检索、answer 三阶段的 LLM/embedding 调用是否都能观测；
- 能取 API usage 时必须使用 `api_usage`；只有接口确实不暴露 usage 时才允许
  `tokenizer_estimate`，且必须记录缺口与拦截层选择；
- 如需修改 `third_party/`，只能做适配或纯观测插桩，不能改变算法核心，并在
  workstream 记录文件、位置、理由与等价性证据。

method 也必须一个一个审计；具体顺序在 B6 后依据五个冻结 benchmark 的能力要求另写
设计，不在本阶段提前锁死。

### Integration Track I0：5×5 离线契约矩阵

只有 Benchmark Track 与五个现有 method 审计均完成后，才运行 25 格离线矩阵：

- 使用真实 benchmark registry、adapter、裁剪与已冻结 prompt/evaluator；
- 使用真实 method registry 与 adapter；
- method 内部 LLM、embedding、远程服务只在最底层 API 边界替换为可观测 fake；
- 使用真实数据极小切片，不用只有理想交替对话的纯手写语料；
- 每格验证 ingest 粒度、retrieve 输出、unified answer、artifact、隐私与效率 schema；
- 不可行格记录明确 capability gap，不用占位实现硬凑通过。

该矩阵只证明主线连通与协议一致，不证明答案质量，也不替代真实 API 校准。

### Test Track T0：测试证据分类

现有测试不得按“老/新”粗暴二分。每个 benchmark 在自身冻结时先处理直接相关测试，
全局测试再归入：

- `KEEP-CONTRACT`：直接保护现行公开协议、隐私、metric、artifact、resume 不变量；
- `KEEP-COMPAT`：只保护仍承诺支持的 legacy/兼容路径；
- `REWRITE`：测试目标仍有价值，但断言锁定旧行为或 fake 绕过真实 registry；
- `DELETE`：临时占位、归档命名等已无产品意义的断言；
- `MISSING`：现行主线存在但没有契约测试。

先补 `MISSING` 并改 `REWRITE`，再由 ws06 做目录与大文件重组。测试数量不作为
验收目标；验收看现行契约覆盖和反例是否能被抓住。

### Real-API Track R0：真实校准门

G0、B0-B6、Method Track、I0 与 T0 全部通过后，架构师提交一格最小真实校准方案，
列明 method × benchmark、数据规模与裁剪轴、answer/judge 调用数上界、预计 token/费用、
run_id、成功/失败判据与停止条件。

只有用户显式批准预算、规模与 run_id 后才执行。单格通过后再决定是否铺开矩阵，
不预先承诺批量真实 run。

## 7. 今后新 method 的慢速接入门

任何新 method 必须按顺序通过以下门，禁止边读仓库边直接写 adapter：

1. **仓库身份门**：锁定官方仓库、commit/tag、许可证、安装方式与本地可用版本；
2. **接口发现门**：枚举官方暴露的产品接口、eval 专用接口、agent/chat 接口，逐个
   写出输入、输出、副作用与适用场景；
3. **接口选择门**：选择通用 memory-module ingest/retrieve 面，并用源码解释为何
   选择、为何排除其他入口；
4. **特殊处理门**：明确粒度聚合、时间格式、flush/await、隔离、检索写副作用、
   provenance 与失败清理；允许有一手证据的声明式 benchmark profile 特化，但
   method × benchmark 专用算法逻辑或专用 runner 是停工信号；
5. **配置门**：repo 默认、paper 值、benchmark 调参和项目统一基座分栏记录，不混用；
6. **效率设计门**：在写 adapter 前画出全部 LLM/embedding 调用点，决定如何获得
   API usage、latency 与调用次数；无法获得 usage 必须先记录原因，不能默认为估计；
7. **协议映射门**：形成 v3 ingest/retrieve/lifecycle/manifest 映射与公私边界表；
8. **离线验收门**：API 边界 fake + 真实数据病态形状 + 调用序列等价测试；
9. **真实校准门**：用户批准单格最小预算后才运行。

每个新 method 的 spec 必须包含上述九项；缺一项不得写实现 plan。

## 8. 今后新 benchmark 的慢速接入门

任何新 benchmark 必须按顺序通过，且同一时刻只接入一个：

1. 锁定官方仓库、数据版本、论文版本与 evaluator 入口；
2. 扫描真实数据形态与异常分布，不只读调研卡；
3. 确定 task family、隔离单位、session/turn 语义、执行顺序与 runner 需求；
4. 第一手抄清 answer/judge prompt、解析器、metric 公式、分母与聚合；
5. 设计 public/private 字段投影，证明 method 不可接触 gold/evidence/judge label；
6. 设计 benchmark-shaped smoke 裁剪轴、越界行为和问题保留策略；
7. 从官方原子步骤与 artifact 粒度设计 resume：checkpoint 边界、幂等性、失败隔离、
   partial artifact 修复和状态型 retrieve 是否可重放；
8. 设计 answer/judge 的调用次数、token usage、latency 与效率 artifact 口径；
9. 证明能复用通用 runner；确需新 runner 时只能按 task-family 建，不能建
   method × benchmark 专用 runner；
10. 用真实数据切片 + method-neutral probe 完成 adapter/evaluator/runner 离线全链路；
11. 架构师验收并冻结该 benchmark 后，才允许开始下一个 benchmark；
12. 用户批准单格最小预算后才运行真实校准。

每个新 benchmark 的 spec 必须包含上述十二项；缺一项不得写实现 plan。

## 9. 验收标准

ws02.6 可信度门完成必须同时满足：

1. 事实总账覆盖当前所有相关真实 run，状态可由 artifact 重算；
2. LoCoMo→LongMemEval→MemBench→BEAM→HaluMem 严格串行完成，五个 benchmark
   各有完整审计包、独立验收记录和 `frozen-v1` 状态；
3. 每个 benchmark 的数据映射、官方流程、公私边界、prompt/metric、smoke、resume、
   artifact 与效率口径均有官方源码/真实数据的文件:行号证据；
4. B6 横向总验收通过，文档、registry、CLI 与代码对五个 benchmark 的声明无已知冲突；
5. LoCoMo 与 LongMemEval 已补官方 unified prompt，五个 benchmark 默认均为 unified；
6. answer LLM 配置按 benchmark 归一，同 benchmark 跨 method 字节级一致；
7. B6 后才完成五个 method 的一手接口与效率审计；
8. 25 格离线契约矩阵全部达到“可运行”，或明确记录不可行 capability gap；
9. 效率 observation 对每个实际 LLM/embedding 调用给出调用数、阶段、token 来源与
   latency；API usage 可得时不存在 tokenizer 估计替代；
10. public artifact 私有 key 扫描为零泄漏；
11. 测试完成 KEEP/COMPAT/REWRITE/DELETE/MISSING 分类，新增主线契约测试能抓住
   当前已知的 unified/config/efficiency 缺口；
12. 架构师亲自复跑每个 benchmark 与最终矩阵的离线验收命令并记录真实输出；
13. 尚未运行新的真实 API，除非用户另行批准 R0 的预算、规模和 run_id。

## 10. 非目标

- 本 workstream 不新增 Phase 1 之外的 method 或 benchmark；
- 不追求提升答案分数；
- 不进行 full run；
- 不以代码行数或测试数量为成功指标；
- 不顺手完成 ws03 的全部架构减重或 ws06 的目录重排；
- 不修改第三方算法核心。

## 11. 已锁定决策

- 主实验口径为 unified，native 只作 sanity 对照；
- 当前所有真实 LLM 仍统一 `gpt-4o-mini`；
- method 一律使用通用产品接口，不使用 benchmark 专用评测副本；
- prompt 与 evaluator 均以 benchmark 官方来源优先，且 method 无关；
- smoke 只缩数据规模，不缩 method 参数；
- 真实 API 继续由用户掌握预算、规模与 run_id 批准权；
- 以后 method/benchmark 接入采用本 spec 的慢速门禁，不再以里程碑速度压过证据质量。
