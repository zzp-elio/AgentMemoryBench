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

**你的第一件正事 = B6 横向总验收**（架构师亲自做 plan，工作项已全部
立项在 ws02.6 README 断点区 2026-07-11 条目）：
1. 论文指标覆盖两缺口：`longmemeval-ndcg@k`+`recall_all`（官方
   eval_utils.py:12-29，artifact-only 可算）、membench 源文件维度
   聚合（first/third × high/low 四格）；
2. judge 配置双轨：longmemeval 官方/lightmem 可选 profile（先一手核
   现状是哪套）；locomo 保持 lightmem（无官方 judge）；
3. "匹配键=公开 id 空间"升跨 benchmark 通用契约写进 spec；
4. 五套契约互不矛盾的横向复核（quirks 表逐行过）。
B6 过后 method 侧解冻（M0；EverOS 替 cognee，排最后）。

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
