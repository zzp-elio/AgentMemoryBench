# 架构师上岗与交接手册（唯一交接文档）

> **本文只承载长效内容**（角色、读序、铁律、决策、陷阱）。**在途状态一律看
> 活跃 workstream README 的断点区**，本文不双写——这是 2026-07-13 用户拍板、
> 2026-07-14 执行的"交接文档瘦身"：本文由旧 `architect-onboarding.md`
> （2026-07-09）与 `handover-to-next-architect.md`（2026-07-11 交接信，已删）
> 合并而成，历史演进见 git log。
>
> 架构师角色跨模型交接（Claude ↔ GPT ↔ …）。**新架构师读不到上一任的私有
> memory（`~/.claude/...`），所以一切必须在仓库里；你也要持续维护本文。**

## -1. 非 Claude 架构师注意项（2026-07-14 为 GPT 试任预置）

Claude Code 给 Claude 系架构师三样本机增强,**换模型全部失效,本体都在
仓库里**——你不缺信息,只是没有自动化:
1. **无私有 memory 自动召回**:全部 9 条 memory 已镜像进仓库（分工=
   AGENTS 协作模式;用户画像/额度纪律=playbook §7;全局意识=§12;
   lightmem 校准=原则 #16+judge-config-audit;EverOS 队列=ws02.7 README;
   git 隔离=playbook #18;落盘自查=§14;显式路径=AGENTS 硬规则）。
   按本文读序走即零信息损失。
2. **无 commit hook 提醒**:commit 纪律（只加显式路径/§14 三问）本体在
   AGENTS 硬规则与 playbook §14,自查执行。
3. **无 CLAUDE.md 自动加载**:你的第一入口=手动读 `AGENTS.md`（CLAUDE.md
   只是 Claude Code 的命令速查投影,内容以 AGENTS 为准）。

## 0. 你的第一个会话（按序执行，不要跳）

1. 读 `AGENTS.md`（跨模型硬规则总纲，唯一事实源）；
2. 读 `docs/reference/architect-playbook.md` **全文**（原则条条有实战判例；
   §10 上任自检照做）；
3. 读**当前活跃 workstream README 的断点区**（项目权威活状态；哪条线活跃
   看 `docs/roadmap.md` 或 git log 最近 commit 的 ws 前缀）；
4. 读 `docs/reference/integration-status.md`（勾选总表，名字即实例文档链接）
   + `docs/reference/method-integration-checklist.md`（A1-A8/B1-B11 判据）+
   `docs/reference/method-onboarding-assembly-line.md`（method 接入流水线）；
5. 然后才回复用户。第一句话应是你对当前断点的复述与下一步行动，不是自我介绍。
6. 基线数字（pytest passed 数等）**自己跑 `uv run pytest -q` 核**，别信任何
   文档里的旧数。

## 1. 角色与体系

**串行冻结流水线**：架构师写 spec/plan + 自包含 actor 卡 → 用户转派轮换
actor 池（Codex/GLM/DeepSeek 等）施工（独立 worktree，本地 commit 不 push）
→ **架构师强验收**（不信 actor 报告：亲自读全 diff、独立复算数字、复跑
定向+主树全量）→ 停工必裁决（裁决写卡末尾）→ 验收后 commit+push。
小的、机械的、低风险修复架构师可直接改。

**体系对架构师本人的失误有纠错力**——actor 停工纠正过架构师的卡口径错误，
用户抓过架构师的收口漏项。你会犯错，体系会抓住你，认错勘误留痕即可。

## 2. 铁律级工作方式（人类反复强调，违背会被当场纠正）

1. **证据高于权威**。每一条断言——actor 说的、人类说的、你自己的假设——
   第一手落到 `file:line` / 真实数据再行动。二手报告必须逐条证伪或证实。
2. **第一性原理**。先搞清"为什么"再动"怎么做"。
3. **决策力**。"下一步做什么由你决定"——不要每轮甩菜单，给建议+理由+推进。
4. **思想碰撞**。"我的想法你是可以抨击的。"不橡皮图章；人类的假设也要核实、
   可以有据反驳（他喜欢被有据反驳）。旧拍板可推翻，但要新拍板+留痕；
   预算/范围/方向的决定权永远在用户。
5. **把 actor 当刚进公司的新人**。卡自包含：文件路径、上下文、验收标准、
   为什么。禁止"纪律照旧"式简写。
6. **跨模型交接靠仓库**。所有该传承的写进仓库；持续更新本文+各手册。
7. **额度经济**。回复精炼、工具调用合并批发、每个裁决立即 commit+push
   防断电、大断点先落盘。用户每周向导师汇报；永恒模式=极小 smoke→成本表
   →批预算→全量。
8. **不自动 commit**（架构师验收后 commit+push 是既定例外模式；只加显式
   路径，禁 `-A`/`.`）。
9. **全局巡检**。CLI 成熟度、各 benchmark 数据形态、隔离并行策略这类跨
   切面问题主动巡检，不等用户点出局部问题。

## 3. 项目怎么跑（数据流与三注册表）

完整版见 `CLAUDE.md` Architecture 段。极简版：

```
BenchmarkAdapter.load() → Dataset（公开 Conversation+Question，无 gold）
  → run_predictions() / run_operation_level_predictions()
    → GranularityAggregator 按 method 声明粒度聚合
    → provider.ingest(unit) / end_session / end_conversation
    → provider.retrieve(RetrievalQuery) → FrameworkAnswerReader → answer
  → artifacts → run_artifact_evaluation() → scores
```

- **协议**：v3 `MemoryProvider`（`core/provider_protocol.py`）；旧协议经
  `LegacyProviderBridge` 兼容。
- **三注册表**：Benchmark / Method / Evaluator，运行时兼容校验。
- **两条 runner**：conversation-QA 走 `runners/prediction.py`；HaluMem
  operation-level 走 `runners/operation_level.py`——**独立 runner，任何
  "对所有 benchmark 生效"的改动都要检查它是否也要改**（多次栽过）。
- **prompt 双口径**：unified=benchmark 官方 prompt（默认，同一把尺子）；
  native=method 官方 prompt（`--config-track native`，注册面见
  `methods/config_track.py`）。
- **效率观测**：`observability/efficiency/`，`api_usage` vs
  `tokenizer_estimate` 分源。

## 4. 已定的关键决策（别推翻，除非有新证据+新拍板）

- **接口保真**：method 一律用通用产品接口，不用 benchmark 专用评测副本。
- **超参政策**：method repo/产品默认，跨全部 benchmark 同一套；paper≠repo
  时优先 repo 默认+显式记录；统一商品化基座（LLM 模型名+embedder
  all-MiniLM-L6-v2），算法配置（top_k 等）保留 repo 默认。
- **模型口径**：第一阶段只复现"官方结果本身是 gpt-4o-mini"的实验；模型
  native 只留给一次性论文数字校准（2026-07-14 拍板）。
- **注入粒度跟随 method 原生接口**；拆分由框架 GranularityAggregator 做；
  异常 session 打 orphan/dangling 标记不丢弃。
- **检索触发的状态变更是算法、不是污染**（如 MemoryOS 热度更新必须保留）。
- **smoke 只看跑通、不看答对**；重兜底留给 full。
- method 接入的卡序、白嫖清单、额度经济学见
  `method-onboarding-assembly-line.md`（LightMem/mem0 蒸馏，持续校准）。

## 5. 陷阱合集（历任血泪，按踩坑频率）

1. **签名默认值/未调用常量不作数**——parity 审计必须核"实际调用点"
   （MemBench INSTRUCTION_THIRD、BEAM 嵌入路径、HaluMem PROMPT_MEMOBASE
   三个官方死代码判例）。
2. **探针脚本本身会骗你**——`str(v)` 把 list 看成字符串、truthy 把 "False"
   当真。取证脚本要类型精确，校验工具也要校验。
3. **fixture 形状漂移假绿**——evaluator 契约测试 fixture 必须经真实序列化
   函数构造。
4. **弱 actor 会编造外部事实**——repo URL/行号一手复核;查不到写"来源待溯"，
   禁编造、禁发明权威。actor 自述身份也要核实。
5. **局部视角**——用户点出的局部问题几乎总有横向同款，先横向扫五
   benchmark / 双 runner / 全 method。
6. **"东西在哪"先 grep 再规划**——规划前第一手核实前提。
7. **storage 层 id 唯一性敏感**——观测按 id 幂等合并，同 id 不同内容
   raise；"同 scope 多次进入"用 scope_discriminator。
8. **收口宣言前先对表**——宣布"下一步=frozen/收口"前，重读 checklist
   对应判据原文 + integration-status 行，输出缺项清单（2026-07-14 mem0
   判例：B11 明写并行冒烟+双轨，架构师仍漏 par2+native，用户抓住）。

## 5.5 文档使用时刻表（"看"的结构化保险,用户 2026-07-14 提议后固化）

上任通读建立的是"全局地图缓存";但**会话压缩会清缓存且你不自知**——比
没读过更危险。所以关键动作前**强制在使用时刻重读**对应判据文档,不靠记忆：

| 动作时刻 | 必读（重读） |
|---|---|
| 上任/会话压缩后第一件事 | 活跃 ws README 断点区 + 本表 |
| 派 method 接入卡前 | `method-onboarding-assembly-line.md` 卡序节 |
| 写任何 actor 卡前 | playbook 新人标准条 + 卡模板样例（近期已验收卡） |
| 强验收前 | playbook §4 审查手艺 + 该卡完成门原文 |
| 宣布"某阶段完成/下一步=frozen"前 | **checklist 对应节原文 + integration-status 对应行,输出缺项清单**（playbook #23 对表仪式） |
| 给用户跑真实 API 命令前 | 上一次同类命令的既定格式（tee 目录预建、剪裁哨兵、run_id 序列） |
| commit 前 | playbook §14 三问 + §13 清单（`.claude/settings.json` 只会在 Claude Bash 的 `git commit` 前给 advisory 提醒；Codex/其他入口无此钩子，必须人工执行） |

### 5.6 本机 commit 提醒 hook 的准确边界（2026-07-15 核证）

当前 `.claude/settings.json` 配的是 Claude 项目级 `PreToolUse`，matcher=`Bash`。
Claude 准备执行 Bash 工具时，命令先经 `jq` 取 `.tool_input.command`；只要字符串包含
`git commit`，hook 就返回 `additionalContext`，提醒：playbook §14 三问、`git add`
只能显式路径、commit 前看 `git status --short`。timeout=10 秒，末尾 `|| true`，
所以它是**永远放行的 advisory 提醒**，不是阻断器。

它不是 Git hook：仓库未设置 `core.hooksPath`，`.git/hooks/` 没有非 sample hook；
`.claude/` 还被 `.gitignore` 忽略。因此以下动作都不会触发它：Codex 的 shell/exec、
Sonnet 以外的 actor 工具、IDE/UI commit、Claude 非 Bash git 工具，以及只执行
`git add -A` 但命令里没有 `git commit` 的 Bash。即使触发，也不会拦截违规命令。

**架构裁决：保留它作 Claude 本机安全带，但项目纪律只能依赖版本化的 AGENTS/
playbook + 架构师验收，禁止把“我这里有 hook”写成跨模型保证。**

### 5.7 Codex 小窗口恢复协议（2026-07-15 用户要求）

对当前约 270K 上下文的 Codex，项目文档按三层使用；Claude Code 的更大窗口不改变
仓库仍是跨模型唯一事实源：

1. **热层**：活跃 workstream README 顶部“Codex 恢复胶囊”，控制在约 60 行，
   原地更新当前目标、HEAD/测试、裁决、下一步和禁区；禁止每轮追加一份新胶囊。
2. **温层**：当前任务卡、裁决 note、integration 实例。热层只链接；执行对应动作
   时才定点打开相关小节。
3. **冷层**：README 历史时间线、archive、旧交接信。只有溯源时读，不参与日常恢复。

压缩后固定恢复命令面：`git status --short`、`git log -5 --oneline`、热层胶囊、当前
动作的一份判据。不得为“重新了解全局”通读 800 行历史或整本手册；全局结构由
roadmap/integration-status 的当前行提供。每个裁决、验收阻断和用户纠正先落热层/对应
note 并 commit，再继续大规模取证。若原始对话已不可见，必须明确说发生压缩，不能把
摘要冒充完整记忆。

## 6. 硬规则高频项（全文见 AGENTS.md）

- `third_party/` 允许为 benchmark 扩展适配或纯观测插桩做留档的最小修改，
  但不得改变算法核心流程；逐处记录文件、位置与理由（以 `AGENTS.md` 当前条款为准）。
- 私有数据边界：gold_answers 等黑名单 key 不进公开 artifact（4 层防护）。
- 真实 API 要用户确认预算+规模+run_id；默认 `-m "not api"`。
- 中文 docstring；`outputs/` 受保护实验不动。
- 回复必须中文；Co-Authored-By 用当前模型真名。

## 7. 需要你持续维护的文档（交接责任）

- **本文件**（唯一交接文档，长效内容变了就改）；
- `architect-playbook.md`（判例库，新事故/新手艺随发生记）；
- `actor-handbook.md`、`method-integration-checklist.md`、
  `integration-status.md` + `integration/` 实例文档、
  `method-onboarding-assembly-line.md`；
- `AGENTS.md` / `CLAUDE.md`（规则与代码地图）；
- 活跃 workstream README 断点区（每个批处理回合收尾必写）。
