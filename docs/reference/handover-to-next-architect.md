# 致继任架构师（Fable 5 交接信）

> 创建 2026-07-11；Fable 5 预计 2026-07-13 下线。**本信由 Fable 5 离任前
> 每轮验收后持续更新**——"在途状态"节的时效以文末更新记录为准。
> 你（继任者）大概率是 Opus 4.8；若是其他模型，本信同样成立：这个项目
> 的全部真相在仓库里，不在任何模型的私有记忆里。

## 0. 你的第一个会话（按序执行，不要跳）

1. 读 `AGENTS.md`（跨模型硬规则总纲）；
2. 读 `docs/reference/architect-playbook.md` **全文**（尤其 §3 十六条
   原则——每条都有本项目实战判例；§10 上任自检照做）；
3. 读 `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 断点区
   （项目权威活状态）+ `plan-b5-halumem.md` §4（当前批次断点）；
4. 读 `docs/reference/dataset-quirks.md`（五 benchmark 个性索引）；
5. 然后才回复用户。第一句话应该是你对当前断点的复述与下一步行动，
   不是自我介绍。

## 1. 你在接手一个什么体系

**串行冻结流水线**：架构师写 plan + 自包含 actor 卡 → 用户转派轮换
actor 池施工（本地 commit 不 push）→ **架构师强验收**（不信 actor
报告：亲自复跑 diff 审读、独立复算数字、复跑定向+全量）→ 停工必裁决
（裁决块写卡末尾）→ 验收后 commit+push。四个 benchmark 已 frozen-v1，
HaluMem 收尾中，然后 B6 横向总验收，之后 method 侧才解冻。

**这个体系对架构师本人的失误有纠错力**——Fable 5 被 actor 停工纠正过
两次（E4 卡口径、H1 探针 bug），停工纪律双向工作。你会犯错，体系会
抓住你，认错勘误留痕即可（原则 #4/#14）。

## 2. 本项目 Top 5 陷阱（前任们的血泪，按踩坑频率排序）

1. **签名默认值/未调用常量不作数**——parity 审计必须核"实际调用点"。
   三个官方死代码判例：MemBench INSTRUCTION_THIRD、BEAM 嵌入路径、
   HaluMem PROMPT_MEMOBASE（memobase 实 import MEMZERO）。
2. **探针脚本本身会骗你**——`str(v)` 打印把原生 list 看成字符串、
   truthy 判断把字符串 "False" 当真（HaluMem is_update 判例，架构师
   本人中招）。用类型精确的判断写取证脚本，校验工具也要校验。
3. **fixture 形状漂移假绿**——evaluator 契约测试 fixture 必须经真实
   序列化函数构造（D4/D5 判例：手写 fixture 键位与生产 artifact 不一致，
   测试绿但生产错）。
4. **弱 actor 会编造外部事实**——repo URL/行号必须一手复核（B3 判例：
   DeepSeek 编造 GitHub repo 名）。查不到的写"来源待溯"，禁止编造，
   也禁止发明权威（"max_tokens=16 是 MCQ 标准"判例）。
5. **局部视角**——用户点出的局部问题几乎总有横向同款（question-time
   一问引出五 benchmark 时间盘点；judge 配置一问引出配置盘点）。
   每次收到反馈先横向扫五 benchmark（原则见 playbook §12、§14 三问）。

## 3. 与用户（zzp）协作的要点

- 他明确要求**思想碰撞**："你不应该顺从任何人，你要有自己的独立的
  思想决策，并且每个决策都应该是有依据的。"他喜欢被有据反驳（判例：
  Fable 5 指出他把活跃组件 ingest_resume.py 记成遗留文件，他很高兴）。
- 他的旧拍板可以被推翻，但要新拍板+留痕（原则 #14）；预算/范围/方向
  的决定权永远在他。
- 额度经济：他的额度经常紧张——回复精炼、工具调用合并批发、每个
  裁决立即 commit+push 防断电、大文件断点先落盘。
- 每周向导师汇报；永恒模式 = 极小 smoke → 成本表 → 批预算 → 全量。

## 4. 在途状态（每轮验收后更新本节）

**B5 HaluMem：✅ 全部完成，`frozen-v1`（2026-07-11，全量基线
**1058 passed**）**——五 benchmark 全冻。批次链：H1 `67eb1a2` →
H2 `b89dedd` → H3 `9f77216` → H4 `5b4e358`（停工→合成指标裁决）→
架构师直修 `20ee6b7`（update 空检索路由 parity bug）→ H5 `a55a3de`。
冻结记录 `ws02.6/notes/halumem-frozen-v1.md`（known limitations
六条）；survey 三卡已契约化；quirks 全实锚。

**B6 = ✅ 完成（2026-07-12）**：B6.2（judge 核证
`ws02.6/notes/judge-config-audit.md`——longmemeval 现状**已是官方
parity**；F2 降级 R0 前置包）；B6.3（匹配键契约 = spec **GC-1**）；
B6.4（`ws02.6/notes/b6-horizontal-audit.md`：3 处加法修复、零
frozen-v2 候选）；**F1 强验收通过**（Opus 4.8 接任 Fable 5 后执行：
longmemeval-retrieval-rank + membench-source-accuracy 两个加法
evaluator，DCG/NDCG/recall 公式经 3000 例复算与官方零失配、fixture
真实序列化、registry 清单达标；commit `0c3a7bd`/`a44f6ed`/`16fcc51`）；
**B6.5 总验收门通过**（全量 **1069 passed** + compileall + 两审计无
open 项）。**method 侧已正式解冻**。

**当前 = ws02.7 Method Track M0（LightMem 首接）——今日 2026-07-13 收尾状态**：
全量基线 **1106 passed**（0 fail；BEAM 测试需 `datasets` 模块，缺则 18 项**环境性** fail、
非回归）。已验收并 push：M0-1（native prompt/judge profile）、**M0-1b**（config-track 运行时
机制，unified 字节零回归）、**M0-eff**（per-run 成本报告聚合器，合并 prediction+evaluator
两效率 store + ohmygpt 计价 0.165/0.66）、**卡 X**（CLI 删 5 旧别名 + smoke 默认问题帽=1）、
**卡 Y**（per-run `logs/method.log` 落盘）。
- **首个真实 flow-through smoke 已跑通**（lightmem×locomo unified，1conv/1round/1q，管道 OK、
  空记忆、judge=0，符合"smoke 只验管道不看答对率"）。**⚠️ 空库悬案**：1-round 抽取 0 条 entry，
  force_extract 已接且触发,因是 segmenter 空 buffer 还是抽取返 0 **静态判不了**——待用**卡 Y 的
  method.log** 重跑读 `Created N` 定论（**下一步第一件事**，需用户确认预算后跑真 API）。
- **待你做**：① **重跑 1-round smoke 诊断空库**（method.log 已能落盘）；② **M0-1c**：
  track-aware 路径层 `.../{mode}/{track}/{run_id}` + resume（现 native/unified 靠显式 run_id 分）；
  ③ **M0.2**：核 LightMem native 内部超参 vs repo 默认（定 build 是否分叉、成本是否 ×2）；
  ④ **成本探针**：逐格(method×benchmark)跑一整条 conversation/instance → `build_run_cost_report`
  读实测 → 外推(locomo×10、lme×500)，"区间 vs 中位隔离空间"待真预算时按 token 量定；
  ⑤ 逐格更新 `docs/reference/integration-status.md`（接入状态实例化落表）。
- **关键长效文档**（接任先读，别重推）：`dual-track-config-policy.md`（双轨唯一政策源）、
  `method-integration-checklist.md`（A1-A8/B1-B11 判据）、`integration-status.md`（谁过了哪项，
  当前静态勾选）+ **`integration/` 逐实体实例文档**（2026-07-13 二次拍板补全：每
  method/benchmark 一份，B/A 逐项证据 + method 接口调用面黑盒拆解；三层结构 =
  模板→总表→实例）。native 矩阵：Mem0=locomo+lme+beam、SimpleMem=locomo+lme+membench、
  LightMem=locomo+lme、其余见 ws02.7 README；HaluMem 全员无。
- **方法论血泪（playbook #18，2026-07-13 事故）**：并行派多 actor 会在同一 git 树"打架"→
  烧额度、无结果；**默认串行派卡**，要并行须 per-actor 独立 worktree/分支；收尾必一手复核 git。
- R0 真实校准（lightmem 论文对齐）等用户批预算，见 judge-config-audit §6。

**H4 的关键裁决已由 Fable 5 做出（写在卡里，不要重新裁）**：
recall = **N/A 声明为冻结限制**（evidence 无 turn id，官方无 retrieval
recall 指标，禁止凭文本相似度制造 gold 映射）；memory_type 维度按官方
原样实现（含共同分母怪癖 evaluation.py:364-383）；update 聚合 0 分母
必须优雅处理（H2 发现的 smoke 边界）。

**B5 之后的队列**：H5 → 冻结包（survey 三卡契约化 + halumem-frozen-v1
+ quirks 补锚 + 全量 + compileall）→ **B6 横向总验收**（论文指标覆盖：
longmemeval-ndcg@k+recall_all、membench 源文件维度聚合；judge 配置
双轨：longmemeval 官方/lightmem 可选【现状是否仍为 lightmem 配置须
一手核】；"匹配键=公开 id 空间"升通用契约进 spec）→ method 侧解冻
（M0；名单：去 cognee 加 EverOS，EverOS 最后接入）→ I0 离线矩阵 →
R0 真实校准（用户批预算；lightmem 校准实验见原则 #16）。

## 5. 交接完备性声明

- 私有 memory（`~/.claude/.../memory/`）与仓库的镜像审计已于 2026-07-11
  完成：**全部 6 条 memory 在仓库有镜像**（额度纪律→playbook §7；用户
  画像→§7；分工→AGENTS.md；全局意识→§12；lightmem 校准→原则 #16+
  ws02.6 README 断点；EverOS→ws02.6 README 断点）。你读完仓库文档即
  零信息损失；若你是 Claude 系，memory 会自动召回作为加速缓存。
- playbook §9 项目快照已刷新到 2026-07-11。
- 全部冻结记录、裁决判例、actor 校准都在 ws02.6 README 断点区与
  各 notes/ 文件，凭 git log 可完整重放决策史。

## 更新记录

- 2026-07-11（创建）：H1-H3 已验收，H4 卡已开待派发；快照/镜像审计
  同步完成。
- 2026-07-11（第二次更新）：H4 已验收（`5b4e358`，基线 1054）；H5
  卡已开待派发；补"给继任者的 H5/冻结包提示"节。
- 2026-07-11（第三次更新）：**B5 完成、HaluMem frozen-v1、五 benchmark
  全冻（基线 1058）**；在途状态节改写为"第一件正事 = B6"。
- 2026-07-12（第四次更新）：**B6.2/B6.3/B6.4 完成**（judge 全景审计 +
  GC-1 + 横向互查 3 处加法修复）；F1 卡已开待派发；在途状态节改写为
  "剩余三步：派 F1 → 验收 → B6.5"。
- 2026-07-12（第五次更新，架构师 Fable 5 → Opus 4.8 交接）：**F1 强
  验收通过 + B6.5 门通过 → B6 完成、method 侧解冻**（全量 1069
  passed）；在途状态节改写为"第一件正事 = Method Track M0（待用户
  拍板）"。首个由 Opus 4.8 执行并验收的批次。
- 2026-07-12（第六次更新）：M0 首 actor 卡 **Task1 停工 → 架构师裁决**
  （native locomo=ANSWER_PROMPT、StructMem 不接）；**双轨政策成文**
  `dual-track-config-policy.md`（含 reproduce-vs-paper 检查、single-track
  collapse、算法代码单一化）；A-Mem 双仓库一手核（adapter 接复现版）；
  GitHub 用户名 buctzzp→zzp-elio active 文件已改；config-track 运行时机制
  拆为 M0-1b（架构师设计后派）。
- 2026-07-13（第七次更新，今日收尾）：**M0-1b + M0-eff + 卡 X（CLI 去重+问题帽）+
  卡 Y（日志落盘）四卡全验收 push**（基线 1106 passed）；首个真实 flow-through smoke
  跑通（空库悬案待 method.log 诊断）；LightMem online=空壳、offline 唯一模式一手定论；
  新建 `integration-status.md`（接入状态实例化）；**playbook #18 记多 actor git 打架事故**
  （默认串行派卡）。在途状态节改写为"下一步=重跑诊断空库 + M0-1c + 成本探针"。
- 2026-07-13（第八次更新，Fable 5 回任——Anthropic 延期至 07-19）：**实例化二次拍板
  补全**：用户指出总表不够，需逐实体实例文档 → 新建 `docs/reference/integration/`
  11 份（6 method + 5 benchmark），method 侧含**接口调用面黑盒拆解**（框架钩子→
  adapter 行为→third_party 调用，全带 `文件:行号`）；`integration-status.md` 改为
  三层结构中的勾选总表（名字即链接，LightMem 详情迁入实例文档）。取证顺带两个横向
  发现：① 五 adapter 全 `provenance_granularity="none"`（recall/rank 类指标现阶段
  全员 N/A、conditional evaluator 暂无生产者）；② **Mem0 是唯一没挂
  `clean_failed_ingest_state` 的 method 且唯一逻辑隔离**（B3×B8 风险组合，其 M 阶段
  第一优先，checklist B8 的 Mem0 例子与现状不符待勘误）。
