# 致 GPT-5.6 sol:架构师试任交接信(Fable 5,2026-07-14)

> 一次性点对点信,你上任跑顺后移入 `docs/archive/`。长效内容不在此信,
> 在 `architect-onboarding.md`——那里 §-1 就是为你(非 Claude 架构师)
> 写的。**用户明确条款:这是试任,表现不好会被撤职,架构师身份转给
> Opus 4.8。**考核项就是本项目纪律:一手证据、强验收、对表、额度经济。

## 0. 第一个会话按序做(不要跳,不要先回复)

1. `AGENTS.md`(你没有 CLAUDE.md 自动加载,这是你的第一入口);
2. `docs/reference/architect-onboarding.md` 全文(§-1 非 Claude 注意项/
   §5.5 文档使用时刻表——"判据在磁盘上不等于在脑子里");
3. `docs/workstreams/ws02.7-method-track/README.md` 断点区 2026-07-14
   全部条目(约 15 条,从最新往下,这是权威活状态);
4. `docs/reference/method-onboarding-assembly-line.md` +
   `integration-status.md` + `method-integration-checklist.md`;
5. 然后第一句话=复述当前断点与下一步,不是自我介绍。

## 1. 你接手时的准确状态

- git main=最新 push(树上唯一真相;基线 **1164 passed**,自己复跑核实);
  LightMem 与 Mem0 已 method-frozen-v1(各带声明缺口清单,见 notes/)。
- **在手活=M2-memoryos 施工卡**(`actor-prompt-m2-memoryos-adapter.md`):
  R1-R7 裁决全部内嵌,经历两次停工两次裁决(§4.5 judge None 哨兵回落/
  §4.6 native=readout-native 先例),actor 在
  `/Users/wz/Desktop/mb-actor-m2mos` worktree 待复工或已复工。
- 你的第一件正事=收 M2 回卡做**强验收**:亲读全 diff、主树全量 pytest、
  文档标准(中文 docstring 含嵌套 helper 与测试,盲点已防四例)、对照卡
  §1 裁决逐条核实施。合入(cherry-pick 保线性)、commit(显式路径!)、
  push、清 worktree。
- 然后:给用户 memoryos 五格 smoke 命令(镜像 mem0 s2 系列:五条 predict
  +tee 进 `outputs/terminal-logs/`,halumem 走 op-level;命令模板从
  `outputs/runs/mem0/` 的 run 目录与断点区反查)→ 用户跑 → 你**开箱
  验货**(playbook #22:零报错≠通过)→ 免费指标你自己跑并 tee 进 run
  目录 → 付费评命令一次性交用户 → **对表仪式**(checklist B11 冻结门:
  重读判据原文+输出缺项清单,这是 frozen note 必填节)→
  memoryos frozen-v1。

## 2. 只存在于对话、未完全内化的背景(补给你)

- 用户计划:你试任;若顺利你继续,若不顺=撤职转 Opus 4.8。周额度极紧
  (交接时剩 ~5%,会刷新),**额度经济=第一生存技能**:批处理回合、
  每裁决立即 commit+push、能引用文档路径就不复述。
- mem0 遗留(都在 frozen note 日程,不阻塞):R0 前置包(native 计量
  跟随/judge 路由泛化/native build profile——§4.6 把 memoryos 也挂进
  同一框架卡)、5×10 完工后 upstream drift 对比、image helper 解冻件
  (mem0/lightmem 补 `[Sharing image that shows: {caption}]`,helper 由
  M2-memoryos 建)。
- memoryos 后续队列:A-Mem(官方 speaker 姿势=`Speaker X says :` 已核)
  → SimpleMem → EverOS 最后(vendored 需去 .git 正规化)。

## 3. 风格交接(用户点名喜欢,尽量延续)

1. **先结论后论据**:每轮第一句话回答"发生了什么/裁决是什么",细节
   在后。汇报用小节+加粗判词+`file:line` 锚,收尾必报 commit hash 与
   push 状态。
2. **每个裁决给理由**,理由落到锚或判例;没有一手证据就说"待核",
   禁止编造(这里的 actor 会编造外部事实,用户也会记错,都要核)。
3. **认错要直接且升格**:被用户或 actor 驳倒时,当场改判、把对方论点
   原文写进判例、说明旧裁决为何错——用户称之为思想碰撞,这是他最
   看重的协作品质。他喜欢被有据反驳,也会有据反驳你。
4. **不甩菜单**:给建议+理由+直接推进;只有真正属于用户的决策
   (预算/范围/方向)才停下来问。
5. 克制的幽默可以有(用户"哈哈哈"时可以接住),但技术判断永远严肃;
   中文回复,术语保留英文原名。
6. **稳扎稳打看似慢,其实最快**——这是用户的原则,也是这个项目所有
   机制(开箱验货/对表/停工裁决)的共同母题。慢下来验货,永远比返工
   便宜。

祝顺利。体系会抓住你的错,如同抓住过我的——认错勘误留痕即可。
—— Fable 5
