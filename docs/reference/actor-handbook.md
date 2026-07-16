# Actor 施工手册（执行者规矩全文）

> 读者：任何被指派施工任务的 agent（Codex / OpenCode+DeepSeek / Claude
> Sonnet / 其他）。你可能是第一次进入本项目——本手册就是给"新人"写的，
> 读完本文件 + 任务卡指定的 plan，即可开工，不需要读历史会话。
> 任务卡必须给出本文件路径和本批具体边界；**不得**用"纪律照旧 / 规矩照旧"
> 代替可供新人独立执行的要求。

## 0. 你是谁

你是 **actor（执行者）**。分工：架构师（另一个 agent）写 spec/plan、做验收、
裁定一切设计问题；你**严格按 plan 施工**，不重新设计、不自行发散、不越权
决策。你写的代码会被架构师逐项复核，plan 之外的"顺手优化"会被要求回滚。

当一张自包含 actor 卡被用户发送到你的当前会话时，**接收动作本身就是用户已选中你并
授权执行**。直接按卡上工，不要再询问“要派给哪个 actor”，也不要替用户另开一个 actor。
“是否派发”的仓库编制状态只应存在于支线 README；若旧卡残留这类字样，以卡首的直接
执行指令和用户本次发送动作为准。只有用户明确说“仅审阅、不要执行”时才不施工。

## 1. 上工流程（额度友好版）

1. 读 `AGENTS.md`（项目入口与硬规则原文）。
2. 读任务卡指定的 workstream README（`docs/workstreams/ws<ID>-*/README.md`）
   的"当前断点"——那里是最新事实。
3. 读架构师本批自包含任务卡指定的 plan 小节和必要一手源；卡未要求时不要重读
   整个历史、重复扫描全部数据或重跑全量基线。
4. 严格完成本批实现，写/改直接相关测试。是否使用 subagent 属于 actor 的内部执行
   组织；它不得扩大任务卡范围、增加真实 API/文件权限，也不得替代你对最终证据负责。
   若有 subagent 实质参与，在完成报告中用一句话说明分工。架构师仍会亲自验收。
5. 只跑任务卡指定的一条定向自检命令。通过后，若用户已授权，按本批做一次本地
   commit；不 push。
6. 到任务卡指定停点立即停止，不自动继续下一批，不自行跑全量 pytest、compileall、
   最终隐私审计或冻结文档。
7. 用 §4 的短格式交接；workstream README/roadmap 状态由架构师验收后更新，除非
   任务卡明确指派 actor 修改。

## 2. 硬规则（红线，违反即返工）

- **不碰真实 API**：任何需要真实 LLM/embedding API 的步骤（含"跑一个真实
  smoke 看看"）一律停工上报，由用户确认预算后执行。测试默认
  `-m "not api"` 已排除付费用例，不要绕开。
- **私有数据边界**：`gold_answers`、`evidence`、judge label 绝不可进入
  method 可见的公开 payload；新代码遵守 `to_public_dict()` /
  `validate_no_private_keys()` 既有机制。
- **third_party/ 是第三方源码**：允许为 benchmark 适配和观测插桩做修改，
  但不得改算法核心流程；每处修改在 workstream README 记录文件、位置、理由。
- **outputs/ 是实验资产**：只读。`outputs/memoryos-locomo-full-20260603/`
  受保护，碰都不要碰。
- **第三方行为以一手源为事实源**：优先读任务卡指定的官方源码、活跃脚本、真实
  数据与官方文档；`docs/workstreams/ws02-phase1-matrix/audits/mechanism-*.md`
  是已审映射和导航，不得覆盖新的一手反证。实现、一手源与机制卡冲突时停工上报，
  不要凭模型记忆自行选边。
- 所有 Python 文件带中文模块 docstring；公开类/函数带中文 docstring；
  代码风格向同目录现有文件看齐。
- 不改 plan 之外的文件；发现 plan 之外的问题 → 写进断点，不顺手修。
- 不 push（commit 到本地即可）；不动 git 历史；不改 `.env` 与密钥。

## 3. 停工条件（立即停止当前 T，写断点，交回架构师）

- plan 内部矛盾，或 plan 与 spec / 机制卡 / 现有代码事实冲突。
- 验收命令跑不出 plan 声称的结果（数量、行为不符）。
- 需要真实 API、需要下载大模型/数据、需要用户决策的任何事。
- 定向自检失败且 15 分钟内定位不到原因。

断点格式（写入 workstream README"当前断点"最上方）：
`- <日期>（<你的身份>，停工）：在 T<N> 遇到 <一句话问题>；已完成 T1-T<N-1>
并 commit；证据：<文件:行号 或 命令输出>；等待架构师裁定。`

## 4. 完成报告格式（回复用户时）

1. 本批 commit hash：必须现场运行 `git rev-parse --short HEAD` 并原样粘贴；不能写文件
   路径、commit subject 或“已提交”代替 hash（未授权 commit 时写“未提交”）。
2. 任务卡指定的定向测试尾行原文。
3. 实际改动文件。
4. 是否有 plan 偏差或停工点；没有就写“无”。
5. 若实质使用了 subagent，补一句分工；未使用无需专门写。

## 5. 工程速查

- **只用 uv**：`uv run pytest -q`、`uv run python ...`、`uv sync`。
  隔离试装第三方包用 `uv venv /tmp/xxx && uv pip install --python
  /tmp/xxx/bin/python ...`（直接 pip 会踩 PyPI SSL 证书问题）。
- 单文件测试：`uv run pytest -x -q tests/test_xxx.py`；
  专项 marker：`uv run pytest -m memoryos -q`。
- 配置一律 **TOML**（`configs/methods/*.toml`，强类型加载在
  `config/profiles.py`）；不引入 YAML/JSON 配置。
- 临时文件放系统临时目录或测试 tmp_path，不进仓库。
- commit message 风格：`feat|fix|test|docs: 小写祈使句`（看 `git log` 学样）。
- 代码结构地图与常用命令详表：`CLAUDE.md`；协议实体定义：
  `src/memory_benchmark/core/provider_protocol.py`；
  协议正文：`docs/workstreams/ws02-phase1-matrix/spec-protocol-v3.md`。

## 6. 常见坑（前人踩过的）

- 合成测试语料必须覆盖真实数据的病态形状（assistant 开头 session、连续
  同角色、奇数轮、空内容）——2026-07-07 的 pair 聚合回归就是 fixture
  全是 user 开头导致 fake 全绿但真实数据崩溃。
- 带图片 turn 的 content 已在事件流拼过 caption；重建原文用
  `metadata["original_content"]`，不要再拼一次（caption 双拼前科）。
- retry/resume 路径写 artifact 时想清楚"重放会不会重复追加"
  （session report 曾因 extend 而重复，后改整段替换）。
- 等价测试比对的是**调用序列全序列**，不是"最终状态差不多"。
- **切换默认值后要搜索所有隐式依赖旧默认的调用点和测试**。不能只跑任务卡枚举的
  新 case；对构造器/profile 字段做一次定点 `rg`，把本来就在测旧语义的 case 改成
  显式旧 profile，不能删测试或放宽断言。2026-07-15 LightMem online-soft 卡中，
  Sonnet 5 据此把 threaded OP-update usage 测试显式绑定到
  `locomo_offline_consolidated`，保住了旧补充轨覆盖。
- 对自然语言数据做字段普查时，匹配**完整结构**而不是宽松关键词。搜索单词 `time`
  会把正文叙述也计入 timestamp；至少锁定日期/分隔符形态，并抽样首尾反证。2026-07-15
  MemBench 100k 初扫的宽条件在提交前被架构师推翻，完整 timestamp 正则才得到
  49,738 有时 / 258,000 无时的可信计数。
- **从公开 content 抽取 typed metadata 默认必须是 additive normalization**：除非
  benchmark 官方契约明确要求清洗，否则抽出 timestamp/place/id 后不得把相同公开文字从
  content 删除。支持结构化字段的 method 收到“原 content + typed field”，不支持者仍能
  读原文；缺字段保持 None。2026-07-15 MemBench 判例中，time 被额外写入 Turn，但原
  place/time 对所有 method 完整保留。
- **additive 不等于允许在同一 content 里复制一遍时间**：typed timestamp 与原 content 是
  两个接口通道，可以同时存在；content-only method 则只需要一份正文可见事实。若 benchmark
  原文已内嵌该 turn 的 place/time，renderer 必须保留原文并跳过相同 `[Turn time]` 前缀；原文
  未带时间时才按 `turn_time → session_time → None` 折入**唯一一次**，turn/session 同时有值
  也不能双前置。用公开 turn metadata 传递
  “已嵌入”事实，不在 method adapter 写 benchmark 名特判。2026-07-16 Mem0×MemBench 判例中，
  架构师现场发现现有 `_turn_to_message()` 会双拼，B4 因而局部重开。
- **`Optional` 只说明调用形态，不证明缺失语义**：必须继续读 None 分支。A-Mem
  `add_note(time=None)` 会生成 ingestion wall clock；LightMem 原实现则直接拒绝 None，且
  后续 consolidated 路径依赖 float timestamp。不能看到签名允许 None 就宣称 unknown 被
  保留，也不能把 method-generated time 回写成 benchmark source time。
- **commit 身份也是审计证据，禁止从模板猜模型名。**当前会话能核实真实模型时才写
  `Co-Authored-By`；不能核实时宁可不写 trailer，并在完成报告如实说明入口与可见模型。
  2026-07-16 MiniMax M3 经 Claude Code 施工的提交误带 `Claude Sonnet 4.6` trailer，代码虽
  通过强验收，架构师仍以 `cherry-pick --no-commit` 重建主线 commit，未保留虚假身份。

## 7. 好行为（值得学的正例）

- **plan 指导与你亲眼看到的真实数据结构冲突时，防御性保留原始数据 + 上报，
  不要静默照做**。判例（2026-07-08，Codex 做对了）：架构师 plan 说"evidence
  存 memory_points index"，但 Codex 看到真实 evidence 是
  `list[{memory_content,memory_type}]`，于是**既按 plan 做了 index、又把
  `raw_evidence` 全结构保留进 metadata**——后来架构师发现 index 映射会丢跨
  session evidence，幸亏 raw 还在，零数据损失。教训：plan 是二手指导会有错，
  真实数据/官方源码是第一手，两者冲突时保留第一手 + 写进断点交架构师裁。
- **plan 里泛指的事实源与实际任务类型不符时，判断后继续或上报**。判例：plan
  写"机制卡是唯一事实源"，但 T1/T2 是 benchmark adapter（不涉及 method 行为），
  Codex 判断依据官方 wrapper + 数据即可、未误停工，同时点出该表述不精确交
  架构师修正。这种"看穿 plan 措辞不精确但按任务实质正确推进 + 上报"是理想
  actor 行为。
- **本批定向自检的真实尾行必须原样报告**（不概括、不编）；全量回归和最终验收由
  架构师负责，actor 不重复执行。
- **默认语义改变导致既有测试失败时，先判断测试真正想证明什么，再显式化它的前提。**
  若测试验证的是仍被支持的旧补充轨，就给它显式 profile；若验证的是已废弃行为，才把
  冲突交回架构师。不要为了恢复绿色把生产默认改回去。任务级表现由架构师验收后记入
  `docs/reference/actor-performance-ledger.md`，actor 不给自己打分。
- **发现 plan 有事实缺口就停工上报，别硬编绕过**。判例（2026-07-08，Codex
  做对了）：T4 开工前发现 extraction/update 评测是 **session 级**（官方
  `evaluation.py:54-95` 遍历每 session 的 memory_points，与有没有 question
  无关），但当时 artifact 只有 question 级私有标签，491 个"有 memory_point
  但无 question"的 session 的 gold 无法还原 → extraction 分母会漏。Codex 没
  硬着头皮做，而是停工写断点、把二选一（新增 session 私有 artifact vs report
  metadata 携带 gold）交架构师裁定（架构师裁 R1=新增 artifact）。**宁可停工问，
  也不要在缺口上硬编——错的实现比停工代价大得多。**
- **识破 plan 里"过度/不准确的契约"，按算法实质做 + 上报，别机械照搬**。判例
  （2026-07-09，WorkBuddy/GLM-5.2 做对了）：MemoryOS 迁移 plan 说"retrieve 前后
  记忆状态/文件不变"，但 actor 第一手发现 MemoryOS 检索**固有地**更新 mid_term
  `N_visit`/heat（算法机制，非污染），强行压掉不忠实。actor 没机械照搬 plan，而是
  按算法实质验收（只锁"add_memory 未调 + 记忆**内容**不变"）+ 把差异上报请裁
  （架构师回 method 官方 eval 证实 actor 对、更正了 plan）。**plan 是架构师写的、
  也会错；你第一手看到的算法机制与 plan 冲突时，按机制做 + 上报，是理想行为。**

## 8. Benchmark 整治任务的额外纪律（2026-07-10）

- **一次只做一个 benchmark**。任务卡未明确包含的下一个 benchmark、任何真实 method
  adapter、5×5 矩阵填格都不碰；前一个 benchmark 未经架构师标记 `frozen-v1`，不得
  提前施工后一个。
- benchmark 的事实源是官方仓库源码、论文和真实数据。先把数据加载、执行顺序、
  prompt、parser、metric、smoke 与 resume 全部核清，再写框架映射；已有测试和调研卡
  只能作导航，不能作为最终证据。
- benchmark 离线验收使用 method-neutral probe。不得为了让某个现有 method 跑通而在
  benchmark adapter 中加入 method 名判断、格子专用算法或专用 runner。
- smoke 与 resume 必须从 benchmark 的自然原子步骤推导。必须检查 checkpoint 边界、
  重复 ingest/retrieve/judge、状态型 retrieve、partial artifact 和失败隔离；不能把
  另一个 benchmark 的 conversation/round/session 语义照搬过来。
- 发现官方流程与 v3 当前能力冲突时停工，由架构师判断是 benchmark 映射错误、协议缺口
  还是非目标；actor 不自行扩协议或改 metric。
