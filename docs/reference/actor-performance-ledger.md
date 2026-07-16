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
| 2026-07-16 | Fable 5；约 10min；授权 3 个只读 subagent（用户提供） | 三家 dual-track/build identity 一手审计 | `82ffd8c` → `4a0533f` | actor/架构师 docs `5 passed`；架构师逐锚复核；主树 `1243 passed` | **9.2** | accepted with architect corrections |
| 2026-07-16 | Claude Code / MiniMax M3；时长/reasoning 未提供 | Mem0 source-time 单次渲染 | `6af75a3` → `7752dab`（重建 commit identity） | actor/架构师 `61 passed`；架构师五 benchmark 扩展 `170 passed`；主树 `1243 passed` | **9.3** | accepted |
| 2026-07-16 | 混合入口：CC+GLM-5.2 → MiniMax M3；中途崩溃/压缩；唯一模型归因不可核 | Track identity M0 首轮 | `81f2708` → `dcd3e7b`（须 R1/R2 收口） | actor `282 passed`；架构师 full diff 抓 MemoryOS 假身份、双事实源、evaluate/resume 缺口 | **6.0** | rework；不计入任何模型聚合 |
| 2026-07-16 | Codex subagent；用户指定 5.6 sol/medium，平台细分档位未独立核实 | Track identity M0 R1 + R2 | `cba25a8` + `2beda2d` → `d6fd56f` + `d032d45` | R1 `416 passed`；首次主树全量 `4 failed/1302 passed`；R2 定点 `5 passed`；最终主树 `1307 passed` | **9.2** | accepted after full-suite rework |
| 2026-07-16 | Fable 5；约 10min；授权并使用 3 个 Opus 只读 subagent；约耗 Claude 5h 窗口 50%（用户提供） | 五 benchmark gold evidence-unit 高判断审计 | `0e38358` → `8e108e4` | actor/架构师 docs `5 passed`；架构师重算 LME 419，并推翻 BEAM singleton 全量结论 | **8.6** | accepted with material architect correction |

### 未评分发现记录

- **2026-07-16，OpenCode + DeepSeek V4 Flash，LightMem/MemBench role 线索**：准确找到
  `messages_use="user_only"` 的 extraction 过滤链与 MemBench FirstAgent 拼接点，属于会改变
  B4/B11 的高价值发现。两处外推需架构师收紧：没有证据证明官方模板是误复制；HaluMem
  assistant 内容是否应作为 memory gold 也不能仅凭直觉决定。因本轮没有正式 actor 卡、
  commit/diff 与可复跑自检，不给 10 分制分数，记录为“发现敏锐，结论边界需复核”。

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

### 2026-07-16：Fable 5 dual-track/build identity 审计

- 正确性 3.5/4：三家 generic/eval/variant、build/readout 分轴和 manifest 过度声明的核心结论
  均成立；但把 Mem0 托管 embedding 写成“公开可复现”混淆了 API 身份与权重 revision，且把
  MemoryOS 已落地的 `max_tokens=2000` 误列为待修项。架构师在原 note 追加订正，不抹历史。
- 证据 1.9/2：三家承重锚与框架 manifest 链覆盖很强，3 个 subagent 分包后由主 actor 逐锚
  复核；架构师现场复证均能重放。两处错误都属于结论措辞/现状归类，故保留 0.1。
- 纪律 2/2：只改唯一 note、显式 add、零 API、零 push；subagent 使用与分工完整披露。
- 判断/交接 1.8/2：准确抓到 LightMem 顶层无 runnable default、MemoryOS ChromaDB 是算法
  variant、三家 native 都只是 readout-only。一次动用 3 个 subagent 的额度很高，但卡明确
  授权且任务本身横跨三家，运行成本只记录、不直接扣分；两处可由主 actor 终审抓出的误判扣 0.2。
- 总评：适合极重的跨仓一手审计与综合裁决输入；产物不能免除架构师逐锚验收。

### 2026-07-16：Fable 5 gold evidence-unit 审计

- 正确性 3.4/4：准确识别五家不同 gold unit，提出 evaluator-private any-of group，并钉住
  MemBench pair-step、LME user-only 双粒度、HaluMem 无 turn qrel；主方案被采用。material
  error 是把 BEAM raw id 写成 conversation 内唯一、歧义实测恒 0；架构师全量重扫确认
  1M 四个 conversation 重启，当前 adapter 为 41 题/198 个歧义原子。
- 证据 1.5/2：官方 scorer/数据/schema/框架链覆盖很广，LME 419/470 冲突也完整保留；但
  报告声称主 actor 亲自复核 BEAM 唯一性，仍与既有 survey 及全量事实相反，说明 subagent
  汇总后的分布性 claim 没有做最后一轮跨 variant 对表。
- 纪律 2/2：唯一 docs note、显式 add、clean worktree、零 API/零 push；3 个 subagent 的
  分工和模型完整披露，没有扩大文件范围。
- 判断/交接 1.7/2：方案 1 明显优于 pair 全局化、分隔符编码与 adapter 私有映射，且主动
  把 LME 双官方路径交回架构师而未伪造一致性。BEAM 误判会改变 schema 表达力，故判断项
  扣 0.3。总分 **8.6**；高额度投入与高判断任务匹配，但再次说明 Fable 适合产出强裁决
  输入，不应省掉架构师的全量反证。Fable 当前只有两份正式样本（9.2、8.6），未满三份，
  暂不做聚合模型排名。

### 2026-07-16：MiniMax M3 Mem0 source-time 单次渲染

- 正确性 4/4：严格实现 `turn_time → session_time → None`，marker 仅认 JSON `true`，保留
  MemBench 原 place/time，缺时 noise 不造时间；legacy/v3 与 event-stream 均闭合。
- 证据 2/2：actor 61 项、架构师同套 61 项与五 benchmark 扩展 170 项均绿；最终全量
  `1243 passed, 3 deselected, 2 warnings, 4 subtests passed`、compileall exit 0。
- 纪律 1.5/2：允许清单、显式 add、data 软链、零 API/零 push 都正确；但 commit 错写
  `Co-Authored-By: Claude Sonnet 4.6`，违反模型身份也须核实的硬规则。架构师用
  `cherry-pick --no-commit` 重建 `7752dab`，未保留虚假 trailer。
- 判断/交接 1.8/2：正确识别 first-person 拼接后同一时间字面量自然出现两次，测试锁的是
  renderer 不再生成第三份，而非机械把次数降到一；实现说明清楚。错误身份 trailer 扣 0.2。
- 总评：代码与反例质量非常高，身份纪律是唯一明显短板；这是 MiniMax M3 首个已验收样本，
  暂不据单样本做模型总排名。

### 2026-07-16：混合入口 Track identity M0 首轮

- 正确性 1.9/4：typed identity、manifest 落盘和三家大体矩阵已搭出，但把当前
  `memoryos-pypi` 错盖成 ChromaDB reproduction，build 分类在 registry/config-track 双写并已
  漂移；卡明写的 evaluate 消费没有实现。`judge_model_source` 是架构师原卡漏轴，不扣 actor。
- 证据 1.2/2：`282 passed` 可复现，但强反例未覆盖 bool/非法 pending/top-inner version，note
  又把未完成的 evaluate/resume 写成已完成，测试绿不能支撑完成声明。
- 纪律 1.8/2：允许文件、未 push、无猜测 Co-Authored-By 是对的；但完成报告所称 author email
  与 `git show` 不一致，身份审计仍需扣分。
- 判断/交接 1.1/2：报告主动披露 evaluate 裁剪偏差和混合模型冲突有价值；然而核心假身份与
  note/实盘矛盾本应在自检发现。总分 **6.0**，须 R1/R2；因 GLM/MiniMax/入口贡献无法分段
  独立核实，绝不把该分数归到某一个模型，也不能据一次崩溃推断 GLM 的代码质量。

### 2026-07-16：Codex Track identity M0 R1/R2

- 正确性 3.8/4：修回 MemoryOS product + external-L2/FAISS-IP，拆除 build 双事实源，补齐
  answer/judge model 双轴、strict parser、evaluate consumer 与 registered resume；R2 再删除
  fake registration 回查全局表的猜测 fallback。
- 证据 1.6/2：R1 八文件 `416 passed`、字段全变 resume 参数化与真实 MemoryOS
  first-run→resume 很强；但定向清单未覆盖 artifact-runner fakes，首次主树全量仍有 4 个回归，
  故不满分。R2 后原失败 + 新反例 5 项与最终全量 1307 项通过。
- 纪律 2/2：始终在原隔离 worktree 线性 follow-up，不 amend、不 push、零 API/下载；第一次
  subagent 回合异常中断后保留 WIP，由接力会话继续，没有 reset 或丢失用户现场。
- 判断/交接 1.8/2：单 registration producer、old artifact-only evaluate、pending fake 声明与
  factory/outputs 前 fail-fast 均是正确边界；最后一公里依赖全量才发现，保留 0.2。
- 总评 **9.2**，accepted after full-suite rework。这是 Codex actor 的单个任务级样本，不与
  架构师本人的工作混算，也不足以形成永久模型排名。
