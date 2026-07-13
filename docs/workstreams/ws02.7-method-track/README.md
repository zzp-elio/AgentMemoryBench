---
id: ws02.7
parent: ws02
status: in-progress（Method Track M0 启动；benchmark 侧五家已 frozen-v1 + B6 完成）
created: 2026-07-12
---
# ws02.7 Method Track M0（method 侧解冻后逐个接入）

benchmark 侧五家 frozen-v1 + B6 横向总验收完成（ws02.6，2026-07-12），
method 侧解冻。本 workstream 按 `docs/reference/method-integration-checklist.md`
的 B1-B11 标准，逐个 method 审查 + 双轨接入 + 极小 smoke。

**接入顺序（用户 2026-07-12 拍板）**：LightMem 首（外部校准器，原则 #16）
→ 其余按 method-interface-inventory 排 → **EverOS 最后**。

## 当前断点（2026-07-13）

- 2026-07-13（**推进策略拍板 + native smoke 实锤 + 三份新政策/卡**，Fable 5）：
  ① **用户拍板：method 深耕制**——一个 method 查透 + 5 benchmark 全 smoke 通才进
  下一个（暂不并行开其他 method 的卡）。② **locomo native smoke 产物级验收通过**
  （读出分叉实锤：官方 ANSWER_PROMPT 透传 + `lightmem_locomo_paper_native_judge_v1`
  judge；M0-1c 新路径 `smoke/native/` 首战成功）→ **locomo 格双轨全通**。
  ③ **checklist 升级**：B3 逻辑隔离四项等效判据（写入分区/检索过滤/单空间删除/
  并行安全，任一证不了→物理兜底）；新增 **B5+ 无损改造评估**（导师建议：能力缺口
  三态裁决，改造经实验验证后可提 upstream PR）。④ **指标扩展计划成文**
  `docs/reference/metric-extension-plan.md`（分层纪律 metric_tier + 盘点→匹配两步走；
  LoCoMo BLEU-1 是官方非 QA 面，加 BLEU 属 supplementary 不得称官方口径）。
  ⑤ **注册面缺口一手**：LightMem task_families 只有 CONVERSATION_QA
  （registry.py:770）→ HaluMem 现进不去，待 B5+ 评估。⑥ **两卡开出**：
  [M0-3 LightMem API 契约详解](actor-prompt-m0-3-lightmem-api-contract.md)（参数/
  返回值/自定义类逐字段，顺带取 memory_point 与 source id 两个能力证据）、
  [MX-1 指标盘点](actor-prompt-metric-inventory.md)。**下一步：用户跑 longmemeval
  双轨 smoke；两卡回来后架构师做 HaluMem 改造裁决 + 指标匹配矩阵。**
- 2026-07-13（**M0-1c + M0.2 双卡验收 + 空库悬案关闭 + build 分叉裁决**，Fable 5 强验收）：
  ① **worktree 并行首战成功**（两 actor=codex+GPT-5.6，独立 worktree/分支，零冲突；
  合并=ff + cherry-pick 保线性）。② **M0-1c 通过**（`d014152`+`7879bb8`）：新布局
  `…/{mode}/{track}/{run_id}` 生效、旧布局仅可 evaluate 不可 resume、ambiguity 测试
  钉死、unified manifest 字节纪律保持；架构师独立复跑 **1112 passed** + compileall。
  ③ **M0.2 通过**（`8bfa404` → cherry-pick `f8344be`）：三方取证表全锚，抽锚 3 处
  一致；**架构师裁决：LightMem build 轴两轨分叉实锤**（extract 0.5 vs 0.1 等）→
  两个 native 格记忆不可复用、**构建成本 ×2**；native 源=复现目录 README reported
  命令，paper 网格出入留痕不标 DISPUTED（R0 不达标再升级）；"来源待溯"5 项=repo
  schema 无 readout 配置的结构性事实，正当。④ **空库悬案关闭**（用户跑 diag-log1）：
  1 round 抽取 2 条记忆、检索命中、sentinel=0——管道功能完整，旧空库判为抽取 LLM
  单次返 0 波动。⑤ 已知限制登记：LightMem 内部 INFO 诊断不落盘（连自家日志 0 字节）。
  **下一步：native 轨 smoke（lightmem×locomo `--config-track native`）→ cost-probe
  （整条 conversation）→ method-frozen-v1；并行可派其余 method 的 M0.1 审查取证卡。**
- 2026-07-13（**两张 actor 卡开出待派发**，Fable 5）：用户明确"actor 充裕、架构师
  额度珍贵，能下放的下放"。开卡：
  [M0-1c track-aware 路径层](actor-prompt-m0-1c-track-paths.md)（实现+测试，裁决已
  写死：新布局 `…/{mode}/{track}/{run_id}`、不迁移旧目录、evaluate 靠 `**` glob 兼容
  两布局、unified manifest 字节纪律不变）、
  [M0.2 LightMem native 配置三方取证](actor-prompt-m0-2-lightmem-config-threeway.md)
  （纯 notes 取证卡：paper(vendored lightmem.pdf)/experiments 目录/configs 默认/我们
  现用四列 × 7 轴，失配只陈述不裁决）。**并行前提 = per-actor 独立 worktree+分支**
  （playbook #18；worktree 命令已交用户）。空库诊断命令（predict-only + 读
  method.log，evaluate 非必需省 judge 钱）已交用户，等批预算执行。
- 2026-07-13（**实例化二次拍板补全：逐实体实例文档落盘**，Fable 5 回任执行）：用户
  指出 `integration-status.md` 总表不够——每个 method/benchmark 还要各一份按 checklist
  逐项展开的实例文档，尤其要拆开 method 接口调用黑盒。→ 新建
  `docs/reference/integration/` **11 份**（lightmem/mem0/memoryos/amem/simplemem/
  everos + locomo/longmemeval/membench/halumem/beam）：method 侧每份含**接口调用面
  表**（框架钩子→adapter 行为→third_party 调用，带行号锚）+ B1-B11 逐项（LightMem
  按 M0 实况勾选；其余四家为"代码取证预填"显式标注非验收结论）；benchmark 侧每份
  = A1-A8 锚点索引 + **"对 method 接入的含义"**节。总表改三层结构索引。**取证两个
  横向发现**：五 adapter 全 provenance=none（recall 类指标全员 N/A）；Mem0 未挂
  `clean_failed_ingest_state` 且唯一逻辑隔离（B3×B8 风险，checklist B8 例子待勘误）。
  下一步不变：空库诊断重跑（等用户批预算）→ M0-1c → M0.2 → 成本探针。
- 2026-07-13（**卡 X + 卡 Y 验收通过 + 今日收尾**，Opus 4.8 强验收）：两卡由用户派
  cc+GLM5.2 并行跑，**两 agent 在同一 git 树打架**烧光额度中断、中途换 DeepSeek 续，
  但最终 git 树线性干净（3 commit 未坏）。架构师一手复核：cd86c81(卡X)/5438064+feaa161(卡Y)
  齐、无冲突标记、**独立复跑 1106 passed 0 fail**（actor 报的"20 failed"是其环境缺 `datasets`
  模块的 BEAM 环境性失败，我环境 datasets=5.0.0 全绿，非回归）。**卡 X**：5 旧别名删净
  （calibrate 自有 flag 保留、已文档化）、smoke 默认问题帽=1、formal 仍 None。**卡 Y**：
  `method_log_scope` 上下文管理器 run 起挂 run 止摘（无泄漏）、第三方 INFO 降噪保 WARNING、
  已包裹 prediction+operation_level 两 runner。**均接受、待 push。事故记 playbook #18
  （多 actor 默认串行派、要并行须 git 隔离、收尾必一手复核 git）。** 新建
  [integration-status.md](../../reference/integration-status.md)（接入状态实例化落表）。
- 2026-07-13（**首次真实 flow-through smoke + LightMem offline 一手核 + 前置两卡派发**，Opus 4.8）：
  - **用户跑通首个真实 smoke**：`predict lightmem×locomo unified`（1 conv/1 round/1 question）
    + `evaluate locomo-judge` 全流程无崩，answers=1/1、judge mean=0.0（空记忆下瞎答，符合 smoke
    只验管道不看答对率）。产物在 `outputs/runs/lightmem/locomo/smoke/lm-locomo-unified-flowthrough/`。
  - **LightMem update 模式一手定论**：core `online_update()` 是**空壳 `return None`**
    （lightmem.py:394-395），`offline_update()` 才真持久化；**adapter 已用 offline**（:461）。
    → 用户"只用 offline"正确,且是唯一可用模式,无需动作。
  - **空库诊断（`No entries found...`）——纠正架构师草率结论**：非"数据少按阈值不生成"。
    force_segment/force_extract **已接且触发**（adapter last-batch:491-494、end_conversation:563/579-580；
    core:209-239）。空库只剩两因:segmenter 切出空 buffer(core short_term_memory.py:51 需 buffer 非空)
    或抽取返回 0。**静态代码判不了,因诊断 INFO 日志(“Created N MemoryEntry objects”等)没落盘**
    → 由**卡 Y** 落地后重跑读日志定论。
  - **两张前置卡派发**（cost-safety，服务 5×10 真实 smoke）:
    [卡 X CLI 别名去重 + smoke 默认问题帽=1](../ws04-terminal-observability/actor-prompt-cli-dedup.md)、
    [卡 Y per-run 日志落盘](../ws04-terminal-observability/actor-prompt-per-run-logfile.md)。与 M0-1c 不撞。
  - **measure-first 计划敲定（用户）**：① 先 5×10 全用极小 flow-through（1 conv/1 round/**1 question**）
    跑通=验管道(≠验记忆构建,build 在整条 conversation 阶段才真跑);② 再**逐格(method×benchmark)**
    跑一整条 conversation/instance 估成本,外推倍数按 benchmark(locomo×10、longmemeval×500);
    ③ 外推"区间 vs 点值"、如何选中位隔离空间,**待真正预算时按每隔离空间 token 数再定**（用户）。

## 当前断点（2026-07-12）

- 2026-07-12（**M0-1b + M0-eff 双卡验收通过**，Opus 4.8 强验收；含防作弊专查）：
  两 actor 并行交付、文件不重叠、**独立复跑全量 1093 passed + 3 deselected**（只升不降）。
  - **M0-1b（Actor A，config-track 机制）**：用户特别要求查"是否作弊式过测"——**结论：无作弊、第一性原理**。
    证据：① 22 处删除全是合法（longmemeval pass-through 重写 + prompt_track/answer-settings
    重构接 config_track），**零删断言、零 skip/xfail/assert True**；② unified 全程零回归——
    native 分支全部 gated 在 `config_track_bundle is not None`，unified 走原路且 manifest **不加**
    config_track 字段（既有 run 身份字节不变、resume 兼容）；③ cat5 跳过靠 evaluator 构造参数
    `_skipped_categories`（unified=空集→不跳）门控，不泄漏；④ 我此前发现的 longmemeval fidelity
    gap **已闭合**——端到端测试驱动真实 adapter retrieve→native builder，断言官方 formatter
    串在、reader-layout `formatted_memory` 不在；⑤ 被改的已验收 parity 测试是**加强**（sentinel
    formatted_memory 反证不被使用），非削弱。commits f502791/6010f77/0d93e60/2a24cd9/b26fd7c。
  - **M0-eff（Actor B，per-run 成本报告）**：`run_cost_report.py` 合并 prediction+全部 evaluator
    效率 store，`complete = cost.complete AND not missing_stores`（fail-loud，不把未采集角色当 0）+
    stage 拆分 + token-source 混比置信 + config_track 优雅降级；`cost.py` 纯加法（零删除、不改
    既有 `calculate_cost`）；ohmygpt.toml 用占位+来源待溯（未编造）。commits 890440e/788ffba/1218415/6c89476。
  - **架构师两处收尾**：① 填 ohmygpt gpt-4o-mini 实价 0.165/0.66 per-M（用户 2026-07-12 提供）；
    ② 直修 Actor B 一处脆测（`test_load_ohmygpt_pricing...` 硬 pin 占位 0.0，我填实价后暴露）→
    改断言"契约"（正价+本地跳过）而非具体价数。
  - **下一步**：M0-1c（track-aware 路径层）+ measure-first 真实 unified smoke（待用户确认预算/run_id）。
- 2026-07-12（**双卡并行派发**）：**M0-1b 已派**（用户，config-track 运行时机制，
  core-pipeline serial-freeze，架构师验收后才动下游）。**M0-eff 卡已开**
  [`actor-prompt-m0-eff-cost-report.md`](actor-prompt-m0-eff-cost-report.md)——per-run
  成本报告原语（合并两效率 store + ohmygpt 计价，价格用户后填），**离线、与 M0-1b
  文件不重叠**，可并行派第二 actor。效率**采集层审计无缺口**
  （[notes/lightmem-efficiency-audit.md](notes/lightmem-efficiency-audit.md)）。
  5×10 成本表仍归 ws05；本卡只做单元格来源原语。
- 2026-07-12（**M0-1 Task2-4 验收通过**，Opus 4.8 强验收）：actor（Codex/
  GPT-5.6）交 `lightmem_native_prompts.py` + `test_lightmem_native_prompts.py`
  （commits c57cabe/2ca91d4/6fcf1f0）。**独立复跑 41 passed**；scope 干净（零
  third_party/adapter/算法/现有 judge/unified 改动）；parity 测试运行时 AST 读真源
  逐字比对（非硬编码），locomo ANSWER_PROMPT/ACCURACY_PROMPT、longmemeval
  system+user、answer 参数 (0/2000/0.8)、longmemeval judge 复用现有 evaluator、
  cat5 跳过、负空间断言全部核实无编造。**接受。**
  **一处 fidelity 发现（架构师 owns，我卡欠规格，折进 M0-1b 不重派）**：longmemeval
  native builder 从 `formatted_memory` 重建，而 `formatted_memory` 走
  `_format_lightmem_memory`（reader 布局 `:1532`），官方 longmemeval 用
  `_format_lightmem_memory_as_official_retrieve`（`:1572`，docstring 明写对齐
  `run_lightmem_gpt.py:186`）→ 运行时会与官方分叉；locomo builder 靠透传 adapter
  `prompt_messages` 已规避。**M0-1b 修**：两个 native builder 都透传 adapter
  `prompt_messages`（native 单一真源）+ 端到端 parity 测试。
- 2026-07-12（**架构师裁 Task1 + 双轨政策成文 + 杂项**，Opus 4.8）：
  ① **Task1 裁决**——native locomo answer=`ANSWER_PROMPT`（标准），StructMem 不接
  （一手核 `experiments/locomo/readme.md`：`--enable-summary` 改 build+检索+embedding
  三处、非纯 answer；paper headline 数字是 summary OFF）。actor 卡 Task1 已改成"已裁决
  直接照用"，**可派新 actor 续 Task2-4**。② **双轨政策落盘**
  [`docs/reference/dual-track-config-policy.md`](../../reference/dual-track-config-policy.md)
  （7 轴 build/readout 二分、native 配置来源决策树、reproduce-vs-paper 一致性检查、
  single-track collapse、算法代码单一化）；checklist B10 与本 plan §3 已引用。
  ③ **改正记忆复用口径**：非无条件，仅两轨 build 轴全同才复用。④ **A-Mem 双仓库一手核**：
  `third_party/methods/A-mem`=复现版（adapter 接的这份，对）、`third_party/A-mem`=通用库版
  （adapter 未用），M 阶段再定通用版去留（policy §7）。⑤ GitHub 用户名 buctzzp→zzp-elio，
  active 文件已改（README/scripts），archive 保留历史。⑥ 运行时 config-track 机制拆成
  **M0-1b**（架构师设计后派，不丢欠规格机制给 actor）。
- 2026-07-12（Codex / GPT-5.6，M0-1 Task 1 停工）：LightMem LoCoMo 的
  `ANSWER_PROMPT` 与 `ANSWER_PROMPT_StructMem` **都是实际可达的活跃分支**，
  任务卡要求交回架构师裁定，不能由 actor 自选。证据：
  `search_locomo.py:258-280` 在 `enable_summary=True` 时格式化 StructMem
  prompt，在 False 时格式化标准 prompt；`process_sample` 将该配置原样传入
  builder（`:441-447`）；CLI 暴露 `--enable-summary` 的 `store_true` 开关，
  默认 False（`:566-570`），并据此选择带 summary 的 entry loader
  （`:616-620`）。候选方案：A. native locomo 默认 profile 锁官方 CLI 默认
  `ANSWER_PROMPT`，StructMem 另列可选 native 子 profile；B. native locomo
  选 StructMem，但这还要求同时定义 summary retrieval/`session_summaries`
  输入契约，已超出本卡纯 answer profile 范围。等待架构师裁定后再做 Task 2-4；
  当前零生产代码改动、未运行自检、未提交。
- 2026-07-12（**M0 立项 + LightMem M0.1 审查完成 + 首 actor 卡开**）：
  ① 标准清单落盘 `docs/reference/method-integration-checklist.md`
  （benchmark A1-A8 + method B1-B11 的 Definition of Done）。
  ② **一手核实 native 配置矩阵**（更正架构师此前先验错误——见下表，
  Mem0/SimpleMem 都被漏报）。③ LightMem M0.1 审查完成
  [notes/lightmem-m0-audit.md](notes/lightmem-m0-audit.md)：物理隔离/
  offline flush/provenance=none/api_usage 已做/native={locomo,longmemeval}
  全部一手锚，零阻塞。④ 双 embedding 省钱想法**否决**（method 内部
  embedding 无法分叉、检索耦合构建会分叉文本，见 plan §3）。⑤ 首 actor
  卡 [actor-prompt-m0-lightmem-config.md](actor-prompt-m0-lightmem-config.md)
  = config-track 机制 + LightMem locomo native profile（离线实现+测试）。
  **下一步：用户派发 actor 卡 → 架构师验收 → 架构师跑真实 unified smoke
  （measure-first：先 LightMem×LoCoMo 一个，读成本，再铺开）。**

## 一手 native 配置矩阵（2026-07-12 架构师逐仓库核实）

| method | locomo | longmemeval | beam | membench | halumem |
|--------|:--:|:--:|:--:|:--:|:--:|
| Mem0 | ✓ | ✓ | ✓ | – | – |
| MemoryOS | ✓ | – | – | – | – |
| A-Mem | ✓ | – | – | – | – |
| LightMem | ✓ | ✓ | – | – | – |
| SimpleMem | ✓ | ✓ | – | ✓ | – |
| MemOS | ✓ | ✓ | – | – | – |
| EverOS | ✓ | – | – | – | – |
| Letta/LangMem/Supermemory | 未见 | 未见 | 未见 | 未见 | 未见 |

证据出处见 plan §2。**边界**：Letta/LangMem/Supermemory 是工程产品，
grep 目录/py 未见 academic 实验配置，各自 M0 时深挖确认；"有实验目录"
≠"能完整抽出 native config"，逐格抽取 + 架构师验收才算数。native 轨
只在 ✓ 格存在；unified 轨所有格都要。

## 里程碑

- **M0.1** 逐 method 接口审查（架构师一手）→ audit note。
- **M0.2** 双轨接入（config-track 机制 + native profile 抽取，actor 实现）。
- **M0.3** 极小 unified smoke（架构师跑真实 API，measure-first）→ 成本观测。
- **M0.4** native 轨 smoke（有配置的格子）+ method-frozen-v1。
- 之后：I0 离线矩阵 → R0 真实校准（lightmem 论文对齐，见
  ws02.6 judge-config-audit §6；用户批预算）。
