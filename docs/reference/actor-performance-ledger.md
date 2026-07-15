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
