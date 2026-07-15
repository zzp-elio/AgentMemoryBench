# Actor 任务级表现账本

> 目的：帮助用户与架构师按真实交付选择 actor；记录的是“某模型在某张卡上的执行”，
> 不是脱离任务难度、提示质量和 reasoning 档位的永久模型排名。

## 评分规则

每次只在架构师读完 full diff、独立复跑后评分，总分 10：

- 契约正确性与完整性：4 分；
- 测试与证据质量：2 分；
- scope / git / 预算纪律：2 分；
- 主动判断与交接质量：2 分。

同时记录 `accepted / rework / rejected`。若架构师给错卡、后续改判导致实现不合入，必须
把“actor 是否忠实执行”和“方案最终是否采用”分开，不能把架构错误扣到 actor 头上。
同一模型累计至少 3 个已验收样本后才做聚合比较；运行时长只作背景，不直接奖惩。

## 任务记录

| 日期 | actor / 设置 | 任务 | actor commit → main | 架构师证据 | 分数 | 裁定 |
|---|---|---|---|---|---:|---|
| 2026-07-15 | Claude Sonnet 5；reasoning=max；约 20min（用户提供） | LightMem paper online-soft 主 profile | `19a0934` → `825132f` | actor `78 passed, 1 warning in 5.84s`；架构师定向 `78 passed, 1 warning in 8.10s`；主树 `1191 passed` | **9.7** | accepted |
| 2026-07-15 | Claude Code / Opus 4.8；reasoning/时长未提供 | MemBench 时间语义 Phase A | `0fbf8e1` → `2e6b4d7` | actor `31 passed in 3.70s`；架构师定向 `31 passed in 3.68s`；主树 `1193 passed` | **9.7** | accepted |
| 2026-07-15 | Claude Code / Opus 4.8；reasoning/时长未提供 | LightMem missing-time Phase B + R1 | `e1cfb75` + `0d6bf9f` → `915f73c` + `3968373` | actor R1 `91 passed, 1 warning in 7.27s`；架构师定向 `91 passed, 1 warning in 6.32s`；主树 `1206 passed` | **9.0** | accepted after rework |
| 2026-07-15 | Claude Code / Opus 4.8；约 30min（用户提供）；reasoning 未提供 | RetrievalEvidence M0 + R1 | `5fd5ac1` + `1999f56` → `352ed3c` + `6b4fd4e` | actor R1 `34 passed in 0.05s`；架构师 R1 `34 passed`；M0 七文件 `307 passed`；主树 `1235 passed` | **9.1** | accepted after architect hardening |

### 2026-07-15：LightMem online-soft

- 正确性 3.9/4：profile、benchmark identity、双路径 gate、backend
  `update="offline"`、manifest/version 均与卡一致；resume 拒绝由 version + 全 manifest
  比较间接闭合，未另造 runner 特判。
- 证据 1.8/2：必测反例齐，warning 来源判断准确；implementation note 记录了首轮失败与
  修复后的真实尾行。lifecycle 已进入 manifest 且复用通用 resume compare 闭合，但本卡
  未新增一条“旧 lifecycle manifest 必须拒绝 resume”的专门强反例，故保留 0.2 分证据余量。
- 纪律 2/2：只改允许的 6 文件，显式 add，clean worktree，零 API、零 push。
- 判断 2/2：发现 threaded usage 测试隐式依赖旧默认值，正确改成显式
  `locomo_offline_consolidated`，没有删除覆盖或扩大生产范围。
- 总评：高质量交付；最有价值的不只是测试绿，而是识别“默认值切换会暴露隐式测试语义”
  并给出最小、语义正确的修复。

### 2026-07-15：MemBench 时间语义 Phase A

- 正确性 4/4：只删除伪 session fallback；逐 turn parsing、place/time 原文、无时 noise、
  question time 单向流与两种 message shape 全部符合裁决。
- 证据 2/2：强反例让 message time 与 QA.time 故意分离，并直接检查 event metadata；
  架构师复跑与主树全量均通过。
- 纪律 2/2：生产只改一处，三文件均在允许清单；data 软链只为 worktree 真实数据测试，
  未暂存、未 push、零 API。
- 判断/交接 1.7/2：正确判断 runner 与两个允许测试文件无需改，并如实披露首次缺 data；
  但完成报告第 1 项把 note 路径写在“Commit hash”后，漏掉真实 hash，架构师只能从 git log
  找回 `0fbf8e1`。代码质量不扣，交接可执行性扣 0.3。
- 总评：实现与测试均很扎实；和 Sonnet 5 同分不代表任务难度相同，累计满三个已验收样本
  前不做模型总排名。

### 2026-07-15：LightMem missing-time Phase B + R1

- 正确性 3.6/4：config/manifest、backend 前 fail-fast、online/consolidated 边界、None
  direct insert 与 lineage 主体均正确；首轮遗漏“缺键 ≠ explicit None”、空串不能洗成 None、
  `MemoryEntry` optional annotation 三道边界，R1 后完整关闭。
- 证据 1.6/2：首轮已有 87 项并覆盖 real normalizer、sequence、lineage、双接口和 retrieve；
  但这些测试没能抓住输入域被额外放宽。R1 新增四组会在首轮真实失败的反例，最终 91 项。
- 纪律 2/2：两次均严格在允许清单，follow-up 不 amend，clean worktree，零 API、零 push；
  未使用 subagent。
- 判断/交接 1.8/2：两次报告结构清楚，R1 对三项裁决逐条精确落地；首轮未主动发现类型与
  explicit-None 边界，保留 0.2。旧卡把“待派”状态写进 prompt 导致 Opus 先询问意图，
  根因属于架构师卡设计，**不扣 actor 分**。
- 总评：最终交付可接受且返工质量高；9.0 反映“核心方向一次正确、边界需架构师抓一次”。
  当时 Opus 4.8 只有两份已验收样本，尚不做跨模型累计排名。

### 2026-07-15：RetrievalEvidence M0 + R1

- 正确性 3.6/4：协议、三家 adapter 运行时盖章、逐题 artifact、严格 manifest identity 与
  resume 主体均正确；首轮把未知 status 当成普通 non-valid，R1 又让 list/dict 从
  `frozenset` membership 泄漏 `TypeError`，架构师以 `afd4040` 收紧为统一 `ValueError`。
  registered CLI preflight 未提前盖 v1 的问题由全量回归才暴露，并以 `c879343` 修复；原卡
  没把该 CLI 文件与“首跑→续跑”强反例纳入范围，这部分是架构师设计责任，不全扣 actor。
- 证据 1.6/2：actor 大范围 fake/registered 测试覆盖三家 method 与 artifact；R1 的非法值
  矩阵也能抓住首轮漏洞。但缺不可哈希输入，且内部 manifest matcher 测试没有证明真实 CLI
  preflight 与最终 runner 对称。架构师最终七文件 `307 passed, 1 warning`、全量
  `1235 passed, 3 deselected, 2 warnings, 4 subtests passed`、compileall exit 0。
- 纪律 2/2：两层 commit 均在隔离 worktree，follow-up 不 amend、不 push、零 API；允许清单
  与显式 add 纪律清楚，未使用 subagent。
- 判断/交接 1.9/2：用 `get_args(RetrievalEvidenceStatus)` 单源派生运行时集合是好判断；报告
  清楚区分环境缺 data 与真实回归，并主动说明 `_UnusedRootSystem`/resume 身份边界。最后两处
  契约缝隙仍需架构师收口，保留 0.1。
- 总评：这是重卡，约 30 分钟属合理投入；主体质量高，强验收抓到的主要是跨层最后一公里。
  Opus 4.8 现有三份已验收样本为 9.7、9.0、9.1，简单均值 **9.27**。当前画像是“大范围
  实现与交接稳定，边界契约仍值得架构师重点反证”；任务难度不同，不据此做绝对模型排名。
