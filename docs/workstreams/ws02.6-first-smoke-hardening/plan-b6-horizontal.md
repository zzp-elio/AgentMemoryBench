# B6 横向总验收施工计划

> 2026-07-11 架构师（Fable 5）起草，执行预定 2026-07-12。前置：五
> benchmark 全部 frozen-v1（B5 完，全量基线 **1058 passed**）。B6 过
> 后 method 侧解冻（Method Track M0）。硬规矩全程有效（实际调用点、
> fixture 真实序列化、出处行号、负空间测试清单、数字可复算）。

## 0. 性质与分工

B6 = 横向收口，两类工作：**B6.1/B6.2 是 actor 批次**（加法型新
evaluator/配置，各一张卡）；**B6.3/B6.4/B6.5 是架构师亲自**（契约
提升、横向互查、总验收门）。全部为**加法或文档**，不触碰任何
frozen 行为——任何项若发现需要改冻结行为，立即停工走 frozen-v2
影响分析，不许静默改。

## 1. B6.1 论文指标两缺口（actor 卡 F1）

已立项（2026-07-11，README 断点区），均为加法不触发 frozen-v2：

- **longmemeval-ndcg@k + recall_all**：官方
  `third_party/benchmarks/LongMemEval-main/src/retrieval/eval_utils.py:12-29`
  （**2026-07-12 勘误：原写 `src/evaluation/` 是路径笔误，行号无误**，
  现场复核已完成）；ranked items 已在 prediction artifact，artifact-only
  可算（照 `evaluate_run_artifacts` 钩子模式，halumem-memory-type
  是最新先例）；k 官方口径 = `[1,3,5,10,30,50]`（`run_retrieval.py:316`），
  指标名逐字 `recall_any@k/recall_all@k/ndcg_any@k`（:318-321）；
  abstention 题官方排除不计（`run_retrieval.py:389-408`，与既有 C4
  N/A 裁决语义一致）。**F1 卡已开：`actor-prompt-f1.md`**（含 k>top_k
  跳过裁定、ideal DCG 免 corpus 等价推导、turn2session 不可算裁定）。
- **membench 源文件维度聚合**：论文按 Factual/Reflective ×
  First/Third 报四格（first_high/first_low/third_high/third_low）；
  conversation_id 前两段即两维（`membench.py:817-832` +
  `_source_profile_from_path` :797-815）。**落点已裁（2026-07-12）：
  合成指标 `membench-source-accuracy` 走 evaluate_run_artifacts 钩子**
  ——原"倾向 summary 维度扩展"作废，因通用 summary 由
  `runners/evaluation.py:192-221` 生成，塞 membench 专属前缀解析进
  通用 runner 违"个性显式声明"红线；per-question evaluator 又无 run
  级 summary 出口。合成钩子是既有机制（halumem-memory-type 先例）。
- 自检：定向 + `tests/test_evaluator_registry.py`（B5 H4 教训：新
  metric 必撞全量清单断言）+ 全量。
- 验收：架构师对官方 eval_utils 逐行核公式（ndcg 的 log 底、gain
  定义、recall_all 分母）；数字抽验用合成 fixture 手算对照。

## 2. B6.2 judge 配置双轨（先架构师核证，再决定是否开 actor 卡 F2）

- **第一步（架构师一手核，不可跳）**：longmemeval judge 现状——
  现行 prompt/参数是 lightmem 配置还是官方？比对对象：
  `third_party/benchmarks/LongMemEval-main` 的官方 judge prompt vs
  `third_party/methods/LightMem` 的 judge 配置 vs 框架
  `evaluators/` 现行实现 + `configs/evaluators/llm_judge.toml`。
  三方一手比对后落一页 `notes/judge-config-audit.md`（五 benchmark
  judge 配置全景表：来源/prompt 出处/参数/与官方偏差）。
- **第二步已裁决（2026-07-12，见 audit §5）：F2 不在 B6 开卡，降级
  为 R0 校准实验前置包**。核证结论：longmemeval 框架 judge **现状
  已是官方 parity**（逐字+参数双测试锚），lightmem 的 longmemeval
  judge prompt 与官方逐字相同，双轨实质差异只有调用参数/解析函数/
  abstention gate 三处（audit §2 差异表）；locomo 框架 judge 系
  lightmem 衍生但有 7 类文本偏差（audit §3，auxiliary tier 无 parity
  义务，冻结不动）。lightmem profile 唯一消费者是 R0 校准实验（预算
  未批、零真实 API 下无法验证），放 R0 前置一次做对。
- **lightmem 校准实验计划**（文档项，落 audit 附录）：R0 预算批准
  后，用 lightmem 的 judge+answer 配置跑 locomo/longmemeval 全量，
  对齐 lightmem 论文中 A-mem/MemoryOS/Mem0 数字 = 框架外部校准；
  之后切统一公平配置。

## 3. B6.3 "匹配键=公开 id 空间"升通用契约（架构师，文档+spec）

三次独立适用（longmemeval C4、membench D4/D5、beam E1）已证其跨
benchmark 性质：**recall 匹配一律在 method 能返回的公开 turn-id
空间进行；官方原始 id 只作对照留 GoldAnswerInfo.metadata；私有通路
= evidence 顶层 + metadata**。写进 `ws02.6/spec.md` 通用契约节 +
`docs/reference/architect-playbook.md` §3 若够格。HaluMem 的
recall N/A 是该契约的边界案例（无公开可匹配 id → N/A 而非造映射），
一并写入。

## 4. B6.4 五套契约横向互查（架构师亲自，B6 的本体）

逐项过、结论落 `notes/b6-horizontal-audit.md`：

1. **quirks 表逐行核锚**：每行的锚（测试/冻结记录/契约卡）现存且
   断言仍绿（抽跑）；
2. **五冻结记录互不矛盾**：smoke 认证口径（各家形状与"运行时调用"
   口径）、resume 三契约、prompt parity 方法（运行时读官方文件）、
   answer 归一五行表（locomo 0/32/1、longmemeval 0/500、membench
   0/None、beam 0/None、halumem None/None+API 默认）——横向一张表；
3. **question-time 盘点复核**（用户点名过的横向面）：locomo cat2
   日期提示/longmemeval Current Date/membench current time/beam 无
   时间槽/halumem 无 question-time 槽——五行表+各自测试锚；
4. **全局私有键黑名单**（core/validators.py PRIVATE_KEY_NAMES）对
   五家 gold 字段的覆盖抽验；
5. **每类分开报告（category_breakdown）五家全生效**的断言清单；
6. 发现的任何不一致：能加法修的加法修，触冻结行为的登记
   frozen-v2 候选交用户。

## 5. B6.5 总验收门（架构师）

全量 pytest + compileall + 上述 audit 无 open 项 → ws02.6 README
标"B6 完成、method 侧解冻"、roadmap 翻状态、交接信更新 → **Method
Track M0 开工**（首件事：M0 计划里对照
`docs/reference/method-interface-inventory.md` 排 method 接入序列，
EverOS 最后；真实 API 校准 R0 等用户预算）。

## 6. 当前断点

- 2026-07-12（Fable 5）：**B6.2 收口**——`notes/judge-config-audit.md`
  落盘（longmemeval 现状=官方 parity 实锤；五家全景表；F2 降级 R0
  前置包裁决）；**F1 卡已开待派发**（`actor-prompt-f1.md`，两个新
  evaluator 均加法）；§1 路径笔误勘误、membench 落点改裁合成指标。
  下一步：用户派发 F1 → actor 施工期间架构师做 B6.3 + B6.4。
- 2026-07-11：plan 起草完成（Fable 5 额度 12% 时落盘）。执行顺序
  建议：B6.2 第一步（核证，轻）→ B6.1 卡派发（actor 施工期间）→
  B6.3/B6.4（架构师并行做）→ F 批验收 → B6.5。
- 执行者：Fable 5（若 2026-07-12 仍在线）或继任架构师（读
  `docs/reference/handover-to-next-architect.md` 后按本 plan 执行）。
