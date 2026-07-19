---
id: ws02.7
parent: ws02
status: in-progress（LightMem LoCoMo/LME/MemBench current-v7 已通过；MemBench 100k 旁路关闭；BEAM 已到 B11 命令门；HaluMem 差量预检待派；Mem0 暂缓）
created: 2026-07-12
---
# ws02.7 Method Track M0（method 侧解冻后逐个接入）

benchmark 侧五家 frozen-v1 + B6 横向总验收完成（ws02.6，2026-07-12），
method 侧解冻。本 workstream 按 `docs/reference/method-integration-checklist.md`
的 B1-B11 标准，逐个 method 审查 + TOML/builder 配置接入 + 极小 smoke。

活跃支线及依赖顺序统一从 [`branches/README.md`](branches/README.md) 进入；不要再从根目录
文件名猜哪张卡先做。

**接入顺序（用户 2026-07-12 拍板）**：LightMem 首（外部校准器，原则 #16）
→ 其余按 method-interface-inventory 排 → **EverOS 最后**。

## Codex 恢复胶囊（热层；每次原地更新，禁止继续堆历史）

> 当前 `gpt-5.6-sol` model catalog 硬上限为 272K，明显小于 Claude Code 的约 1M；
> 压缩后不得声称保留
> 原始对话。恢复只读本节 + `git status --short` + `git log -5 --oneline`，再按链接
> 定点读一份 note/判据；不要从下方历史断点全文重建。

- **最近实质链**：`bfe69f1`（MemoryOS M2 验收）→ `0333c7a`（LightMem 取证）→
  `ac24f63`（semantic provenance 改判）→ `653c1ff`（Mem0 文档锚）→ `eed497b`
  （compact/metric 资格门）→ `dc15304`（Mem0 ADD-only audit）→ `c36b171`
  （retrieval eligibility audit）→ `5fc0345`（资格裁决）→ `025a141`（LightMem
  online-soft 裁决）→ `825132f`（online-soft 实现强验收）→ `2e6b4d7`（MemBench 时间
  Phase A 强验收）→ `ff91aa3`（缺失时间兼容裁决）→ `915f73c`（Phase B 主体）→
  `3968373`（explicit-None R1）→ `352ed3c`（RetrievalEvidence M0 主体）→ `6b4fd4e`
  （status R1）→ `afd4040`（不可哈希 status hardening）→ `c879343`（preflight/resume
  身份对称）→ `da81b0f`/`b875879`（MemoryOS manifest fixture 对齐）→ `212d21f`
  （M0 最终验收文档）→ `4a0533f`（双轨身份审计）→ `7752dab`（Mem0 effective-time
  单次渲染）→ `dcd3e7b`（Track identity M0 首轮）→ `d6fd56f`（R1 真实性收紧）→
  `d032d45`（R2 registration 单事实源）→ `afb57f3`/`6d68a51`（Gold Evidence Group
  M0 + R1）→ `d86b22a`/`d1c18c4`（LightMem hybrid + R1）→ `2e78c55`（双卡合流
  fixture v1）→ `4c4bb0c`（TOML/builder 政策 + MemBench 卡）→ `ce1a9a8`/
  `d852fff`/`68b674b`（MemBench canonical split + 架构师 R1/R2）→ `5d8fce3`/
  `e10110f`（RetrievalEvidence M1 + 契约收敛 R1）→ `78196bc`/`65f5805`
  （LightMem caption v6 + 无 caption bytes R1）→ `68bb7f9`（retrieval summary v2）→
  `d11d749`/`2f21291`（LightMem readout/embedding v7 + R1）→ `6ba4060`/
  `cdbf570`/`fbf84af`/`44e2968`（MemBench 异常审计 + pair/manifest R1-R3）→
  `9bd2ab0`（MemBench source-filter CLI R1）→ `de40d63`（BEAM pair 差量）→
  `ca64f4c`（BEAM 异常账）→ `6f48ee3`（MemBench source-subset registration R2）。准确
  commit/upstream 状态始终以紧邻执行的 `git status`/`git log` 为准，胶囊不自指自己的
  hash。本轮主树全量门=`1590 passed, 3 deselected, 2 warnings, 29 subtests passed
  in 160.06s`；标准 `src+tests` compileall exit 0。隔离工作树补齐 gitignored benchmark/
  model 资产后才跑该门，不能把缺资产失败混成代码回归。
- **MemoryOS**：M2 已正式强验收通过；主树定向 `6 passed in 2.71s`，全量
  `1176 passed, 3 deselected, 2 warnings, 4 subtests passed in 142.46s`。PyPI/ChromaDB/eval
  身份裁决与 Track identity M0 已关闭；当前按逐 method 串行顺序排在 LightMem、Mem0 后，
  到站后进入五格真实 smoke。未获用户预算/规模/run_id 确认，禁止 API。
- **LightMem lifecycle 现行裁决**：论文第 5/7/8 页与官方脚本复证，paper online soft
  是“抽取后直接 LTM insert”，在 vendored 代码中反而由
  `update="offline" → offline_update(memory_entries)` 实现；`online_update()` 空壳只是
  命名债。**五格 Phase 1 主 profile 改判统一 `online_soft`**，LoCoMo 全库
  consolidation 另名补充轨；Claude Sonnet 5 actor `19a0934` 已经架构师 full diff +
  `78 passed, 1 warning in 8.10s` 强验收，合入主线 `825132f`。`3e2d957` 仍不合入；
  post-update provenance Recall/NDCG 仍 N/A。裁决=`branches/lightmem-lifecycle/notes/
  lightmem-update-lifecycle-ruling.md`。
- **指标资格/top-k**：两张 docs-only audit 已由 Sonnet 5 回卡并经架构师强验收合入。
  Mem0 mutation=ADD-only，但 sidecar 是批归属：LoCoMo/MemBench=turn、LME=session、
  BEAM recall=N/A。Gold Evidence Group M0 已把五个 retrieval evaluator 从扁平 qrel 迁到
  evaluator-private group view：LME abstention/no-user-target 现按官方主路径剔除，turn 主分母
  锁为 419；top_k=10 挡死官方 k30/50 的问题仍未修。
  架构采用逐题 `RetrievalEvidence` + evaluator requirement 两层，不建手写笛卡尔积表。
  裁决=`branches/retrieval-metrics/notes/retrieval-metric-eligibility-ruling.md`；
  **RetrievalEvidence M0 已强验收合入**：Mem0/LightMem/MemoryOS 每题 artifact 陈述
  semantic provenance + granularity + stable ranking，manifest contract v1 严格参与 resume；
  无契约的 A-Mem/SimpleMem 不盖章。**M1 已以 `5d8fce3` + `e10110f` 强验收关闭**：五个
  evaluator 严格消费逐题资格，Recall 与 rank 分离要求，benchmark-policy 排除不污染
  provider status，LongMemEval 只披露 query depth 实际覆盖的 k；probe 与旧手工 fixture
  也已闭合 v1。当前不再重复改 qrel group、LME 419 分母或把 pending 排名硬算成分数。
- **元学习/过时文档整改**：actor 卡整份即 prompt，禁止卡尾重复 wrapper；不默认要求
  reviewer subagent，也不一刀切禁止 actor 内部 subagent。compact 与冷启动彻底分离：
  AGENTS 中“compact 后重读 onboarding”旧句已删，只走四步热恢复。待派/暂停属于支线
  README，不得混进施工 prompt；用户把卡发送给某 actor 就是已完成选择与授权。
- **时间/B4 现行裁决**：MemBench 原 message 的 place/time 原样保留，支持 typed timestamp
  的 method 另收 `turn_time → session_time → None`；这不是正文重复。Mem0 这类 content-only
  method 每条 message 也只折入这一个 effective timestamp。MiniMax M3 交付已由架构师
  full diff + `61 passed` + 五 benchmark 扩展 `170 passed` 强验收，主线 `7752dab`；
  MemBench 原文已含时间时不再加 header，无时间 noise 保持 None，绝不用 QA/question time、
  兄弟 turn、首个有时 turn、wall clock 或 synthetic time。B4 离线门关闭，三格内容抽查并入
  后续五格主配置 B11，不单独重复烧历史 build。
- **Method TOML/answer builder 现行裁决（2026-07-17）**：不再把 method 配置硬编码成
  `unified/native` 两条流水线。每个 method 一个 TOML；`smoke`/`official_full` 是跨五
  benchmark 固定的主 section，作者确实跑过且有一手参数时才增加稀疏
  `author_<benchmark>`。CLI 只选择 section，不逐项传参或按 benchmark 暗切。
  `answer_builder="benchmark"` 选 benchmark 统一的**完整构造器**；作者 section 选 method
  官方完整 builder，必须填好全部公开变量并产出可直接调用 LLM 的 `PromptMessage[]`，不能把
  模板文件冒充 parity。现行政策=`docs/reference/method-toml-and-answer-builder-policy.md`；
  实施支线=`branches/method-config-profiles/README.md`（scheduled，尚未写卡）；
  旧 `config_track`/TrackIdentity 只作已有产物兼容。5×10 主 smoke 不等待参数调优；首个作者
  校准或真实效果 full run 前完成 loader/builder/manifest 迁移。embedding 是普通 TOML 字段，
  最终主表取共同还是产品默认留到效果实验前逐 method 裁定；当前 smoke 保持已验收配置。
- **指标现行裁决**：LoCoMo canonical answer 仍是 32-token 单一 prediction，各答案指标共用它；
  Precision/F1@k 在 relevance gold 未证明穷尽时 N/A。artifact-only 新指标走独立 metric-pack，
  不整体解冻 benchmark core；M1 后先消费 `docs/reference/metric-extension-plan.md` 的
  normalized EM + directional substring EM。“通用”现明确为公式内核不读取 benchmark/method，
  不代表所有 task 都启用：现有 Recall 已共享 group 公式与资格门，剩余 top-k/结果骨架收敛；
  F1 对 BEAM 的过宽注册一并在 Metric Pack M0 修正。Opus 4.8 `760f251` + `2f8a1e1` 已由架构师
  full diff、R1 `44 passed`、主树全量 `1524 passed, 3 deselected, 2 warnings, 29 subtests passed`
  强验收，以 `3bc9019` + `54a360e` 合入；两条 LightMem LoCoMo v6 run 已零 API 追加 normalized
  EM/substring EM，均为 lexical 0 分且逐题原因可审计。Fable 5
  三家 product-default/variant 审计继续
  作为既有 build identity 的历史证据；MemoryOS ChromaDB 仍是 reproduction variant，不能用
  TOML profile 掩盖算法分叉。
- **Codex hook/下一动作**：项目 `.codex/hooks.json` 已获用户信任，compact 自举与 commit
  提醒可用；恢复是后台动作，不自动向用户播报机械台词。Track identity M0 已经 R1/R2
  强验收关闭：新 registered run 统一盖 typed v1 identity，旧缺 v1 不得 resume，evaluate
  严格消费，fake registration 也须显式声明 pending、不得回查另一张全局表猜身份。当前唯一
  method 主线已转入 `branches/method-recertification/`。Fable evidence-unit 审计已验收并由
  架构师纠正 BEAM 全量结论：LME canonical 分母=419，BEAM 1M 当前为 41 个含歧义题/198
  个歧义原子；采用强类型 evaluator-private gold group。LightMem unified 五格固定 hybrid，
  但 extraction source_id 是 pair index，assistant 可见性不自动证明 turn-level exact lineage。
  Gold M0 与 LightMem hybrid 首轮均经 full diff 驳回后由 Codex R1 收口。Gold group 现按
  官方 unit 计分，BEAM 重复 raw id 为 multi-child any-of，LME 主 turn 分母 419。MemBench
  canonical split 也已关闭：一个 dict step 变为真实 user/assistant 两 turn，但仍由一个
  private any-of group 计一次；LightMem 两 pair 同批抽取没有跨 step lineage union。
  RetrievalEvidence M1 已关闭。LightMem 的 LongMemEval input-time
  审计也已由 Opus 4.8 主体 + 架构师 R1 强验收：S/M 每个 retained turn 恰一次，官方
  user_only 会丢 2,020/20,283 raw turn（含 3+3 assistant target），unified hybrid 全保留。
  cleaned JSON 的同日 question clock 错序按 OWNER 解释只作 raw artifact；实现原样传 dataset
  timestamp、完整 history 不截断，retrieve 明确 `filters=None`。LightMem 的 500ms 只在相同
  raw timestamp key 内递增，distinct turn timestamp 保持原值；placeholder 保 lineage/speaker，
  但会影响 method-derived slot time，必须在 report 披露。**2026-07-17 LoCoMo B11 前预检又抓到
  caption 在 LightMem 注入边界确定性丢失：canonical adapter 已保留原文与结构化 `ImageRef`，
  事件流也有 `turn_images`，LightMem 却只恢复 `original_content`；全量 1,226
  个 caption turn 不可见，而默认 1-round smoke 的 D1:1/D1:2 恰好无图片。**该缺口现已由
  `78196bc` + `65f5805` 强验收关闭：caption-bearing turn 统一共享 wrapper，无有效 caption
  保留原文 bytes，B2/B4 retested。用户随后完成最新 v6 单/双 worker 两组真实 run；架构师已从
  checkpoint、artifact、private gold group、Qdrant lineage、效率与 state 隔离逐层验货，B11
  关闭并形成 `lightmem-frozen-v2.md`。
  LoCoMo 异常终检又把稳定账补齐：16 个 date-only key/140 个 odd session 已由 canonical 层吸收；
  9 个 turn-unmatched gold unit、1 个重复 occurrence 与 4 道 empty-evidence QA 只走
  evaluator-private 通道，不要求 LightMem 特判。caption 卡已关闭，不再重复派发。
  B9/B10 效果配置迁移仍按既有政策不阻塞 smoke，但首个效果 full/author calibration 前必须完成。
  v6 开箱抓到的 product readout、embedding observation、metadata/evidence 与 summary 四处
  缺口已经 summary v2=`68bb7f9`、LightMem v7=`d11d749` + `2f21291` 关闭；用户又于
  2026-07-19 完成 LME/LoCoMo current-v7 各 W1/W2 四组真实 run。架构师亲读 manifest、
  prediction/answer、全部 evaluator、raw/overall efficiency 与 worker Qdrant state；修正版机器
  验货为 LME ISO hit=2、LoCoMo ISO hit=16，build embedding calls=2/28。原模板把每个
  conversation 必须有 build embedding 写成过强断言；LME W1 0 LTM 时合法 0 build，R1 已改为
  actual-call-aware 判据并落盘。LoCoMo/LME 恢复 current-v7 `REAL_SMOKE_PASSED`。MemBench 全量
  异常审计与 OWNER `docs/survey/异常情况/membench.md` 已由架构师逐锚交叉；发现的
  registered `turn` 错配已修为 `pair`，具体 `consume_granularity` 已进 strict
  manifest/resume identity，question time 只进官方 answer builder。用户随后完成 MemBench
  current-v7 W1/W2；R1 验货按生产 storage-safe name+hash 修正后全绿：25 ISO hit、9 条
  FirstAgent 双 child lineage、16 条 ThirdAgent singleton lineage、25 次 build embedding，
  双 worker 物理隔离成立。本格现为 `REAL_SMOKE_PASSED`。100k 不重跑整套 W1/W2，只留
  FirstHigh+ThirdHigh 单 worker missing-time 真实哨兵；用户已批准规模/run id。R0 因
  MemBench 专属 source 旗标的 CLI 正向门缺失而在 API 前中止，`9bd2ab0` 修复；R1 随后又被
  registration 的 variant 四源硬等式拦截。`6f48ee3` 没有删除 source lock，而是要求 smoke
  选择为 concrete variant 内的有序非空子集、adapter 返回与 fingerprint 精确一致，full 少源
  继续 fail-fast；真实 registry→runner→artifact 两源离线回归已经穿过该门。两次失败都只有
  terminal log、零 API/零 method state，命令包保留各自非破坏性归档流程。BEAM 的 `turn→pair`
  差量已由 Opus 4.8 回卡、架构师逐 diff 与
  `330 passed` 强验收，主线 `de40d63`；source-locked 异常账复核确认标准三 split role 干净、
  10M 两处 dangling user/一处 content 错位/一格全缺时/5 次跨 session anchor 回退，均不需
  猜修数据。BEAM 现到 100K+10M B11 命令门。MemBench 100k 缺时真实哨兵以合法
  zero-extraction + local-Qdrant null-write 两层关闭，无需重烧。LongMemEval 稳定异常账已集成；
  架构师 R1 订正 S/M 124 题 evidence-id 仅顺序不同、集合相同。HaluMem current-v7 差量预检卡
  已形成，等待用户派发；故 LightMem 整体仍不 frozen。
  Mem0 → MemoryOS → A-Mem → SimpleMem 顺延；Metric
  Pack M0 已关闭，不反向解冻 LightMem build。格子“安全感”继续由一 method 一份、五 benchmark
  分章的 living dossier 承载，禁止一份总绿灯代裁。
- **用户派工边界**：架构师只写卡；由用户在 Sonnet 5/GLM-5.2/MiniMax/Codex 等池中
  选择。除非用户明确要求，禁止自动启动 Codex subagent。

## 当前断点（2026-07-19）

- 2026-07-19（**MemBench 100k 缺时旁路已关闭；LongMemEval 稳定异常账强验收并带 R1 集成；
  HaluMem current-v7 差量卡待用户派发**，GPT-5.6 sol 架构师）：真实 run
  `lm-membench-v7-none100k-fh-th-r1q1-w1-100k` 的两个官方 no-time distractor 均实际进入
  memory-build LLM 并合法产出 0 LTM；首版机器门错误要求每个 conversation 必须有 Qdrant point。
  R3 改为 actual-call-aware：真实 run 承担 normalizer/extraction/zero-hit，新增确定性
  local-Qdrant 强反例承担 null timestamp insert/readout，现有产物机器门 PASS，裁决=
  `100K_MISSING_TIME_SENTINEL_PASSED_ZERO_EXTRACTION`，不再调用 API。LongMemEval actor
  `6591db1` 的 source hash、duplicate session/role 草稿降格与 current 处置成立；架构师逐题
  比较抓到 S/M 124 题 `answer_session_ids` 只是 same-set reordered，已在 audit R1 与稳定页订正，
  无生产修复。过重卡重复 census 的责任归架构师并写入 playbook。下一条可并行线只派
  `actor-prompt-lightmem-halumem-current-v7-preflight.md`：复用 frozen-v1，不重扫 Medium/Long，
  只核 current-v7 session capture/online-soft/operation-level/readout/evidence 差量；真实 B11
  命令等 READY 回卡后再给。BEAM 100K+10M B11 仍可独立推进，但未经用户再次确认命令/预算不调用。

- 2026-07-19（**100k 哨兵连续两次被零 API 预检门拦截，source-subset R2 已端到端修复；
  LongMemEval 稳定异常账承认 pending 并形成审计卡**，GPT-5.6 sol 架构师）：用户批准
  `lm-membench-v7-none100k-fh-th-r1q1-w1` 后，R0 因 CLI 漏传 `is_membench=True` 被挡，
  `9bd2ab0` 修复；R1 随即因 registration 仍要求 prepared paths 等于 variant 四源全集，被
  `prepared source_relative_paths do not match variant '100k'` 挡住。第二次仍发生在 provider/API/
  backend 构造前，目录也只有 terminal log。架构师承担上一轮正例只 mock 到 command service、
  没穿过第一个真实 consumer 的验收遗漏；`6f48ee3` 新增 registration source resolver 契约：
  smoke 只能选择 source-locked 有序非空子集，adapter 必须精确匹配，full 少源仍 fail-fast；
  registered offline prediction 实际跑过 100k 两源 registry→runner→artifact/fingerprint，得到
  2 conversations/2 questions/4 turns。扩大门=`220 passed`，主树全量=`1590 passed,
  3 deselected, 2 warnings, 29 subtests passed`，compileall exit 0。命令包 §0.1 给第二次现场的
  非破坏性归档；push 后用户从 §2 原身份重跑。LongMemEval 方面，用户指出得对：现有
  `docs/survey/异常情况/longmemeval.md` 是未跟踪 OpenCode 草稿，索引仍为 pending。已新增
  source-locked S/M R1 审计卡，要求逐条证伪草稿并对表 canonical/evaluator-private/LightMem；
  推荐 Sonnet 5 exhigh，回卡后由架构师强验收并集成稳定页。BEAM actor `ff8dfc5` 经架构师
  full diff、独立定向 `330 passed, 1 warning` 后线性
  合入 `de40d63`：唯一生产变化是 LightMem resolver 把 BEAM 加入 `pair`，manifest/resume
  自动失效旧 `turn` run，adapter v7 不 bump，RetrievalEvidence 仍 N/A。五个 Arrow shard
  hash 与 source lock 一致；独立 census 纠正 Sonnet 草稿：标准三 split 790 sessions/118,420
  turns role 全干净；10M 是 77,569 groups/208,696 messages，两处 dangling follow-up，第二处
  下一 assistant 明显答错槽；不是“2 次”而是 **5 次**相邻 session anchor 回退，另有一个全缺时
  session。详细位置与不猜修裁决见 `docs/survey/异常情况/beam.md`。合流定向门=`428 passed,
  1 warning`，主树全量=`1588 passed, 3 deselected, 2 warnings, 29 subtests passed`，compileall
  exit 0。push 后用户先按 100k 命令包续跑；BEAM 另给 100K+10M 两个独立 run 的 B11 命令，
  不混 variant。

- 2026-07-19（**历史派卡前断点，已由上条 superseded：MemBench 100k 只补缺时旁路哨兵；BEAM pair 差量修复可并行派发；后续 method
  启用 benchmark 稳定层摊销**，GPT-5.6 sol 架构师）：production adapter 现场确认 100k
  FirstHigh/ThirdHigh 各首条在 1 round 裁剪下共有 4 个真实 turn，全部
  `turn_time=None/session_time=None`；最小哨兵固定 2 conversations × 1 question × 1 worker，
  不重复 0_10k 已验收的 W1/W2 并发/隔离。命令包已拟定，真实 API 仍等用户明确批准规模与
  `lm-membench-v7-none100k-fh-th-r1q1-w1`。该旁路线不降低现有 MemBench
  `REAL_SMOKE_PASSED`，也不阻塞 BEAM。BEAM benchmark frozen 事实直接复用；current
  LightMem resolver 落到 `turn`，会把正常 user→assistant 拆成两个人工 pair，故已形成只改
  registration/tests/integration note 的零 API R1 卡，回卡强验收后才生成 100k+10m B11 命令。
  从本格起，后续 method 只核 source lock + method-specific 差量；只有 source/共享契约变版或
  新一手反证才重开 benchmark census。

- 2026-07-19（**LightMem × MemBench current-v7 单/双 worker B11 强验收通过；下一格转
  BEAM 预检**，GPT-5.6 sol 架构师）：用户执行 W1/W2 各四源 4 conversations；predict、
  choice/source/recall evaluator 均无运行错误。R0 机器验货把 Qdrant 的 64 字符可读前缀误当
  完整 conversation identity，FirstHigh 的 `-0` 被合法截断后匹配失败；R1 改用生产
  `_storage_safe_collection_name(default_isolation_key(...))` 的完整 name+SHA-1 映射，现有 run
  无需重烧 API。修正版验货：W1 12、W2 13 条 LTM；8/8 query embedding、25/25 build
  embedding 对齐；25 个完整 ISO readout；FirstAgent 双 child lineage=9、ThirdAgent singleton
  lineage=16；W2 四个 conversation 分别且唯一落到 worker 0/1。W2 一条 `invalid_choice` 是
  smoke 只保留 step 1、而 gold 在 step 119 时模型诚实拒答，parser 正确记 0 分，不是
  builder/并发故障。两轮 choice/source=0.5、Recall=1/6，只作 artifact 证据，不作效果结论。
  本格升为 `REAL_SMOKE_PASSED`；完整原始输出与边界见
  `branches/method-recertification/lightmem/notes/lightmem-membench-b11-command-pack.md` §7。
  LightMem 还缺 BEAM/HaluMem，整体仍不 frozen。

- 2026-07-19（**LightMem × MemBench 四层离线门与 pair 投递已强验收；当前
  `READY_FOR_B11_SMOKE`；等用户批真实预算/run id**，GPT-5.6 sol 架构师）：Sonnet 5
  预检揭示 registered path 实际为 `turn`，但违反原卡停工门、误判局部 id 隔离、
  漏 39 处 source-step 时钟倒序，且把可修接线误报成必须付费 sentinel 的 BLOCKED。架构师
  独立重算确认 4,260 trajectories / 452,245 source steps / 767,075 canonical turns，
  100k no-time=258,000/307,738 source steps、倒序 39、OOB 2、empty target 1。Codex
  R1/R2 `cdbf570` + `fbf84af` 将 LightMem × MemBench 改为 `pair`：FirstAgent 一个官方
  step 一次双边 `add_memory()`，ThirdAgent singleton 各自补 placeholder；place/time 原文
  不删，typed time 只读自身，no-time 为 None，`QA.time` 只进官方 answer prompt。
  公开 `method.consume_granularity` 现与 factory 共用 resolver，与实例交叉校验，严格参与
  resume。首次主树全量抓到 9 个旧 fake 未镜像新契约，R3 `44e2968` 仅修 fixture，
  生产零改；原 9 失败已复跑 `9 passed`，最终主树全量=`1579 passed, 3 deselected,
  2 warnings, 29 subtests passed in 144.49s`，compileall exit 0。稳定异常账、安全 dossier
  与手册已回填。
  下一步不是再发零 API 审计，而是在用户确认规模/预算/run id 后执行 MemBench
  真实单/双 worker B11；在 artifact 开箱前不得写 `REAL_SMOKE_PASSED`。

- 2026-07-19（**LightMem LME/LoCoMo current-v7 四组真实 run 强验收通过；MemBench 零 API
  actor 在途；Mem0 继续暂缓**，GPT-5.6 sol 架构师）：四组 predict/evaluate/judge 均完成，
  terminal logs 无 traceback/error/timeout，manifest/行数/checkpoint/worker state 全对。LME W1
  为 0 LTM/0 build embedding 的合法 zero-hit，原验货模板因此误报；W2 另一个 conversation
  落库 2 条并有 2 次 build embedding，observer 有效。actual-call-aware R1 全验货 PASS：
  LME/LoCoMo ISO items=2/16，build calls=2/28；LME retrieval summary v2 全 N/A 可空，LoCoMo
  Recall 正常，caption `D1:5` lineage 与双 worker 隔离成立。命令、误判原因、修正版输出与开箱
  证据已回填 `branches/method-recertification/lightmem/notes/
  lightmem-v7-readout-observability-b11-command-pack.md` §9。两格升为 `REAL_SMOKE_PASSED`，不外推
  full/效果/成本/resume，也不恢复 method frozen。MemBench 卡已由用户派发，当前等待回卡；
  回卡后把 actor note 与 OWNER/OpenCode 的 `docs/survey/异常情况/membench.md` 逐个 source anchor、
  count、production path 和 evaluator-private 边界交叉验收，再裁是否发真实 MemBench smoke。

- 2026-07-19（**历史执行前断点，已由上条 superseded：LightMem v7 四个受影响格真实 run 已获批；与 MemBench 零 API 预检双线并行；
  Mem0 继续暂缓**，GPT-5.6 sol 架构师）：用户已批准 LongMemEval S-cleaned W1/W2 与 LoCoMo
  3-round W1/W2 的预算、规模、run id。完整 predict/evaluate/judge/机器验货命令已落
  `branches/method-recertification/lightmem/notes/
  lightmem-v7-readout-observability-b11-command-pack.md`；四个 predict 外部串行，W2 内部双 worker，
  重点验证 v7 完整 ISO readout、逐题 metadata 单事实源、build/retrieval embedding observation、
  summary v2、caption lineage 与 state 隔离。并行只开放一张不改代码、不调用 API 的
  `branches/method-recertification/lightmem/cards/
  actor-prompt-lightmem-membench-anomaly-coverage-preflight.md`，由用户派发外部 actor；该卡把
  MemBench 异常分为 source-lock census、production-path 强反例、真实 backend sentinel 与
  evaluator-private 四层。两线均回卡/回结果并经架构师开箱前，LoCoMo/LME 不恢复 current-v7
  passed，MemBench 也不提前开真实 smoke。

- 2026-07-18（**历史预算前断点，已由上条 superseded：LightMem × LongMemEval 两张零 API 修复已强验收；v7 真实 B11 待预算门；
  Mem0 继续暂缓**，GPT-5.6 sol 架构师）：summary actor `8a81723` 合入主线 `68bb7f9`；
  LightMem actor `8f6f883` 首轮被 zero-hit/observer 透明性强反例驳回，Codex medium R1
  `1a07938` 关闭后合入 `d11d749` + `2f21291`。架构师独立门=summary 149、LightMem 204、
  合流 325、主树全量 1557、compileall exit 0；真实 v6 W1/W2 零 API 重评为 total=1/2、
  mean=null。当前仍为 `B11_ARTIFACT_REPAIR_PENDING`：代码已修，缺的是 v7 真实 artifact 对完整
  ISO readout、zero-hit 双源一致与 build/retrieval embedding observation 的证明。未经用户重新
  确认预算、规模与 run_id，不调用真实 API，也不并行启动下一 method。LongMemEval v7 通过后，
  还须补 LoCoMo v7 的公共 readout/B7/B11 最小复验；v6 LoCoMo run 只作历史证据。

- 2026-07-18（**历史修复前断点，已由上条 superseded：LightMem × LongMemEval v6 B11 已执行并开箱；两张零 API 修复卡可并行派发；
  Mem0 继续暂缓**，GPT-5 架构师）：实际 run=`lm-lme-v6-r1q1-w1-s-cleaned` 与
  `lm-lme-v6-r1q1-c2-w2-s-cleaned`，机器验货均 PASS。架构师亲读 manifest、prompt、retrieved
  payload、score/summary、efficiency 与 worker state 后裁定：主接线/隐私/N/A/隔离有效，但
  Qdrant 的完整 `2023-05-20T03:29:00.000` 被 unified readout 降为 `20 May 2023, Sat`；声明的
  `lightmem-embedding` 没有任何 `embedding_call`；逐题 v1 granularity=`none` 与 legacy
  metadata=`turn` 冲突；全 N/A retrieval summary 错写 `total_questions=0,mean_score=0.0`。
  当前格子=`B11_ARTIFACT_REPAIR_PENDING`。并行卡分别为
  `branches/method-recertification/lightmem/cards/actor-prompt-lightmem-readout-observability-repair.md`
  与 `branches/retrieval-metrics/cards/actor-prompt-retrieval-summary-nullability.md`；两卡无 production
  文件交叉、均禁真实 API。回卡后由架构师 full diff + 定向强验收 + 线性合入，再裁最小 v7
  重跑；此前禁止继续付费，也不把 v6 artifact 写成 `REAL_SMOKE_PASSED`。

- 2026-07-18（**历史执行前断点，已由上条 superseded：LightMem × LongMemEval B11 预算已批；
  单/双 worker 全 evaluator 命令已发；
  等待 OWNER 执行与架构师开箱验货**，GPT-5 架构师）：W1 故意沿用 registered 默认
  `1 conversation × 1 round × 1 question × 1 worker`；W2 只显式覆盖为
  `2 conversations × 2 workers`，round/question 继续走默认。两次 predict 严格串行；每次随后
  跑 token-F1、normalized EM、substring EM、LongMemEval Recall/rank 资格壳与 compact judge。
  Recall/rank 对本格的预期是成功写 `score=None/status=n/a/pair_source_id_not_turn_exact`，不是
  伪分数。LongMemEval multi-variant CLI 用 `s_cleaned`，artifact child run id 自动追加
  `-s-cleaned`；两组实际 run id、日志搬运与零 API 机器验货均固化在
  `branches/method-recertification/lightmem/notes/lightmem-longmemeval-b11-command-pack.md`。
  在真实 artifacts 回收前，本格仍为 `READY_FOR_B11_SMOKE`，不得提前写 passed/frozen。

- 2026-07-18（**历史执行前断点，已由最新开箱条目 superseded：建立每 method 一份五格安全
  说明；LightMem 前两格已落盘；下一步仍是 LME
  B11 预算门**，GPT-5 架构师）：用户要求把“为什么敢跑、异常如何处理”从聊天变成可复查
  资产。现裁为约 10 份 method dossier、每份五 benchmark 分章，不制造 50 份散落顶层文档；
  规则已写入 method checklist。首份=`branches/method-recertification/lightmem/notes/
  lightmem-five-benchmark-safety-dossier.md`：LoCoMo 明确到 `REAL_SMOKE_PASSED`，LongMemEval
  只到 `READY_FOR_B11_SMOKE`，其余三格保持 pending，禁止总绿灯。current-main 合并复跑
  LoCoMo/LME 承重集=`272 passed, 1 warning in 80.79s`，文档门通过，零真实 API。该文档工作
  不改变实验状态；下一动作仍是用户批准预算/规模/run_id 后执行 LME 单/双 worker B11。

- 2026-07-18（**历史预检断点，已由最新开箱条目 superseded：LightMem × LongMemEval
  latest-main 预检 + R1 强验收；B11 待用户批准真实 API；
  Mem0 暂缓**，GPT-5 架构师）：Opus 4.8 `67715dd` 已把临时 Claude scratchpad 的六类探针构造与
  stdout 全量补入仓库 note，跨模型证据自包含；架构师 full diff、current source 对表与 dummy-key
  八文件独立复跑=`219 passed, 1 warning in 84.60s`，核心 role/pair/hybrid/time/query/readout/
  metric 链成立。首轮 B11 建议混淆 smoke、full 与成本，并误把约 200 pair 写成约 200 次 extraction
  LLM；Codex medium 按用户授权线性 R1 `346f1c4`，已改为：registered smoke 默认 1 conversation ×
  1 round × 1 question，只作接线验证；正式 full 保留完整 history；成本必须由首条完整实验单元的
  真实 API/token/wall-time/efficiency 观测外推。R1 文档门=`5 passed in 0.91s`。主线
  `9bf1c78` + `b2d7c9c`；证据=`branches/method-recertification/lightmem/notes/
  lightmem-longmemeval-latest-main-preflight.md`。下一步是用户批准预算、规模、run_id 后给出 B11
  单/双 worker 命令；在此之前零 API。六类异常已离线实证，不为重复覆盖另烧完整异常 qid。

- 2026-07-18（**历史断点，已被上方预检 + R1 强验收取代**，GPT-5
  架构师）：用户指定 LoCoMo 后继续压实 LightMem 的 LongMemEval 格。既有 Opus 4.8 输入异形/
  timestamp 审计已覆盖 S/M exact count、placeholder、500ms 与 no-cutoff，不再重复烧 actor；
  本批只核 current v6 的 canonical role → TurnPair → hybrid add_memory → retrieve/readout → metric
  eligibility。自包含 docs-only 卡=`branches/method-recertification/lightmem/cards/
  actor-prompt-lightmem-longmemeval-latest-main-preflight.md`；回卡强验收前零 API，不写付费命令。

- 2026-07-17（**Metric Pack M0 强验收关闭；legacy LightMem native 不重复烧过渡 run；下一家
  Mem0**，GPT-5 架构师）：Opus 4.8 首轮 `760f251` 与 R1 `2f8a1e1` 已线性合入主线
  `3bc9019` + `54a360e`；R1 定向=`44 passed in 2.33s`，全量=`1524 passed, 3 deselected,
  2 warnings, 29 subtests passed in 166.45s`，compileall exit 0。两条既有 LightMem LoCoMo v6
  run 已 artifact-only 追加 normalized EM/substring EM，零 API/零 method 重跑；逐题 0 分来自日期
  lexical 表达不匹配，不是接线失败。源码复核确认 legacy `config_track=native` 可运行 LightMem
  LoCoMo/LME 官方 answer/judge readout，但身份严格为 `readout_only`、不覆盖 build；因历史 smoke
  已有且新 TOML/builder 政策将取代该入口，本轮不重复付费运行。首次作者校准前再关闭
  `branches/method-config-profiles/` 实施门。

- 2026-07-17（**LightMem method-frozen-v2；Metric Pack M0 主体成立、R1 待派发；下一家 Mem0**，
  GPT-5 架构师）：用户完成 `lm-locomo-v6-r3q1-w1` 与
  `lm-locomo-v6-r3q1-c2-w2`。两组 prediction=1/1、2/2；当时四项适用 metric 全落盘；三题
  Recall@10 由架构师从 top-k public source ids 与 private gold groups 独立重算均为 1；双 worker
  分别只承载 conv-26/conv-30；caption-bearing D1:5 在两次 conv-26 LTM lineage 中可见。terminal
  tee 缺双 worker 最终 JSON，但 run 内 log/event/checkpoint 均 completed，裁为显示缺口。六份 log
  已归入各 run `logs/`，旧 command pack 的单 worker state 断言已纠正。LightMem 正式恢复
  `method-frozen-v2`，证据=`branches/method-recertification/lightmem/notes/lightmem-frozen-v2.md`。
  Opus 4.8 Metric Pack `760f251` 定向复跑 `159 passed`、compileall exit 0，Recall 迁移/registry/
  EM 公式主体通过；未合入原因仅为 `substring_em` details 缺
  `normalized_prediction/normalized_gold`。R1 卡=
  `branches/metric-pack/cards/actor-prompt-metric-kernels-m0-r1.md`；修完后架构师补资产全量并合入，
  再对两条既有 run 只追加离线 EM/substring evaluate，不重跑 method。

- 2026-07-17（**LightMem caption v6 + R1 强验收；B2/B4 关闭，B11 待预算/run_id**，GPT-5
  架构师）：Opus 4.8 `ea08431` 的核心修复成立：v3 从 `turn_images` 恢复 `ImageRef`，legacy/v3
  caption-bearing real message 共用共享 wrapper，adapter v5→v6 强制重建。架构师 full diff
  发现首轮会把无有效 caption 的普通正文 `.strip()`；Codex `gpt-5.6-sol`/medium 以线性
  `9f5ef69` 增加强反例并恢复原文字节保真，主线为 `78196bc` + `65f5805`。dummy key + invalid
  base URL 主树定向=`154 passed, 1 warning in 9.10s`；真实 `conv-26/D1:5` 离线探针确认
  legacy=v3、共享 wrapper 恰一次、旧 wrapper/query/URL 零泄漏、空 assistant/speaker/time/lineage
  不变；全量=`1500 passed, 3 deselected, 2 warnings, 29 subtests passed in 143.47s`，compileall
  exit 0。B2/B4 caption 门据此 retested；B11 仍未运行。用户只批准了 **3 rounds / 1 question**
  的规模，预算与 `run_id` 尚未批准，禁止调用 API。完整证据=`branches/method-recertification/
  lightmem/notes/lightmem-locomo-image-caption-implementation.md`。

- 2026-07-17（**历史断点，已被上方 caption v6 强验收取代**，GPT-5 架构师）：当前 `[smoke]`
  确认为 MiniLM/384/cosine、hybrid、online-soft、
  combined top-60；LoCoMo 每个 named-speaker utterance 仍由 framework turn 粒度消费，再独立
  生成 `[real user, empty assistant]` backend pair。全量复算 272 session/5,882 turn，0 坏时间、
  0 speaker 映射失败、0 重复 id、0 空文本；hybrid 与官方 user_only 在 LoCoMo extraction prompt/
  token 严格等价。新反证是 `_turn_from_event()` 丢弃 `turn_images`，首个 caption turn D1:5 的
  caption 到 LightMem content 消失；全量影响 1,226 turn，且 1-round smoke 不覆盖。现 B2/B4
  定点 pending、B11 暂停；canonical LoCoMo adapter 继续保留 raw content + structured caption，
  文本 wrapper 只在 method 注入边界渲染一次。证据=`branches/method-recertification/lightmem/notes/
  lightmem-locomo-smoke-config-preflight.md`，自包含修复卡=`.../cards/
  actor-prompt-lightmem-locomo-image-caption.md`。零 API 定向=`51 passed, 103 deselected, 1 warning`
  + `11 passed`。下一步只修 caption + v5→v6 重建门，不重扫 LoCoMo benchmark 异常、不提前做
  效果参数 TOML 迁移。用户已批准修复后的 B11 规模为 **3 rounds / 1 question**；预算与
  `run_id` 未批准，禁止提前调用 API。

- 2026-07-17（**LightMem LongMemEval input-time 审计经 R1 强验收；B4 关闭**，GPT-5
  架构师）：Opus 4.8 基于旧卡 `914a198` 交付 `0b1ca2e`，363 行主体计数与机制图扎实，架构师
  复跑文档门 `5 passed in 0.85s` 并独立复算 q<latest same-day=`76/118`、max slot=132、跨
  minute=`2/7`、跨 hour/day=`0/0`。首轮因未收到中途 OWNER 增补而误写 public unresolved；
  另把“固定 pair 结构不再额外拉宽”过度概括成 placeholder 对 derived time 零影响，并漏查
  query cutoff。R1 已逐项订正：OWNER 公开裁决有效；raw timestamp 原样传且 retrieve
  `filters=None`；placeholder 保 lineage/speaker，但连续同 role 会相对 canonical real-turn
  adjacency 多占 500ms，assistant-first fact time 锚到 pair base。官方 LightMem
  `main@4372c8e` 与 vendored 零 API 探针又确认：500ms 只作用于 repeated raw timestamp key，
  distinct per-turn timestamp 两层均保持。最终 B2/B4/B5 retested，无代码修复卡；稳定摘要已
  回填 survey/integration，完整证据=`branches/method-recertification/lightmem/notes/
  lightmem-longmemeval-input-time-audit.md`。下一动作是 B11 五格 smoke 预算/命令。

- 2026-07-17（**RetrievalEvidence M1 + R1 已强验收；下一步回到 LightMem 重认证**，GPT-5
  架构师）：Sonnet 5 首轮 `b6c4b32` 完成严格 v1 parser、逐题 eligibility 与五 evaluator
  主体，卡内 `87 passed`；架构师复现其主动披露的 probe/旧 fixture 缺口为
  `6 failed, 147 passed, 1 warning`，并进一步抓到 benchmark-policy 排除晚于 provider
  decision、status count 污染、mixed granularity 误报及五份 artifact 校验漂移。按用户既有
  授权由 Codex `gpt-5.6-sol`/medium 在线性 R1 收敛：probe 只为自身确定性 turn/rank 盖章，
  五家共用严格 retrieval field helper，LME canonical no-target 保持 419，排除题不进入
  evidence counts。架构师定向=`270 passed, 1 warning in 13.95s`；首次全量的 9 个 SimpleMem
  失败均由不合法子目录软链/缺模型资产造成，改用 worktree 内真实源码副本 + 只读 model root
  后全量=`1486 passed, 3 deselected, 2 warnings, 29 subtests passed in 127.77s`，compileall
  exit 0。主线=`5d8fce3` + `e10110f`；R1 卡、身份冲突说明、手册与 actor 账本随验收文档
  一并落盘。下一步不再扩 M1，而是定点更新 LightMem gap matrix 并做 B11 前离线对表，零真实 API。

- 2026-07-17（**历史断点，已被上方 RetrievalEvidence M1 强验收取代**，GPT-5
  架构师）：Sonnet 5 首轮 `a6c8f55` 的生产语义经 full diff 复核成立，无为过测放宽：
  FirstAgent 每个 dict step 拆为 `n:user`/`n:assistant`，每侧原文、role 与自身时间独立，
  private gold 仍按一个 pair-step group 计一次，smoke 按 source step 裁剪而不切半 pair。
  架构师发现首轮缺少精确 `1/3` evaluator、四源 smoke、event round-trip、跨 pair batch
  lineage 与 nested helper docstring 门；Codex 5.6 sol/medium 线性追加 `0fb849c` +
  `c40589c`。主线合入为 `ce1a9a8` + `d852fff` + `68b674b`。全量扫描 8 个官方文件：
  4,260 trajectories、452,245 source steps、767,075 canonical turns，step→child 映射
  0 缺陷；LightMem 同批两 pair 的 source id 分别只映射各自 pair。最终六文件定向
  `269 passed, 1 warning`，全量 `1441 passed, 3 deselected, 2 warnings, 29 subtests`
  （358.28s），compileall exit 0，零真实 API。下一门不重改 gold group、MemBench
  canonical 或 LME 419 分母，只做 RetrievalEvidence M1。自包含卡=
  `branches/retrieval-metrics/cards/actor-prompt-retrieval-evidence-m1.md`；推荐 Sonnet 5，
  独立 worktree，不与其他代码卡并行追同一 evaluator。

- 2026-07-17（**历史断点，已被上方 MemBench 强验收取代；当时卡待派**，GPT-5
  架构师）：依赖复核确认 RetrievalEvidence M1 必须消费 split 后的最终 turn/group 与
  LightMem 逐题 evidence，若现在并行会同时修改 evaluator fixture 并制造跨卡追赶。自包含卡=
  `branches/input-role-semantics/cards/actor-prompt-membench-canonical-split.md`；它拆 FirstAgent
  user/agent、保持 pair-step 单分母、按源 step 做 smoke 裁剪，并删除已过时的
  `membench_canonical_split_pending`。推荐 Sonnet 5，隔离 worktree=
  `/Users/wz/Desktop/mb-actor-membench-canonical-split`；零真实 API、不 push。回卡后架构师先
  full diff + 定向/全量强验收，再写 M1 卡。

- 2026-07-17（**TOML method profile + 完整 answer builder 政策落盘；实施已排期、未派卡**，
  GPT-5 架构师）：用户纠正全局 `native/unified` 双轨过重，并进一步纠正“选择 prompt 模板”
  的表述：作者 answer parity 的对象是填完 speaker/time/question/formatted memory/检索条目等
  全部变量、可直接调用 LLM 的最终 messages。现行裁决写入
  `docs/reference/method-toml-and-answer-builder-policy.md`，旧双轨政策明确 superseded；
  实施消费者落在 `branches/method-config-profiles/README.md`，
  checklist B9-B11、AGENTS、onboarding、playbook 与 dual-track 历史支线入口同步更新。
  当前不改代码、不调参、不调用 API。原先排在它前面的 MemBench split 与 RetrievalEvidence
  M1 均已关闭；现回到 LightMem B1-B11 离线对表与五格 smoke。旧 `config_track` 迁移与
  author section/builder 接线仍在首个作者校准或真实效果 full run 前完成。

- 2026-07-16（**Gold Evidence Group M0 + LightMem hybrid 双线强验收完成；下一门
  MemBench canonical split**，GPT-5 架构师）：Gold 首轮 `9d06659` 经 Opus 4.8 →
  DeepSeek V4 Pro 接力完成，但架构师反例抓到 NDCG ideal 删除 unmatched、两个 singleton
  冒充 multi-child、旧 manifest 被 method N/A 短路和 MemBench 合成 id fixture；Codex R1
  `6ea644f` 关闭，主线以无虚假 Opus-only trailer 的 `afb57f3` + `6d68a51` 重建，并以
  `af7157a` 勘误 note。LightMem 首轮 `2463ddb` 抓到 partial lineage、marker truthiness、
  role fallback、source-path prompt 猜测与 HaluMem session→pair 调用漂移；Codex R1
  `011c265` 关闭，主线为 `d86b22a` + `d1c18c4`。两线合流首次得到
  `1 failed, 587 passed`，正确暴露一个旧 LoCoMo fixture；`2e78c55` 只把 fixture 升到
  Gold v1，未放宽生产门。最终定向并集 `588 passed, 1 warning, 29 subtests`，主树全量
  `1435 passed, 3 deselected, 2 warnings, 29 subtests passed in 144.51s`；compile 门通过，
  零真实 API。下一门只做 MemBench FirstAgent pair 拆分与 gold-group 对齐。

- 2026-07-16（**Fable evidence-unit 回卡强验收完成；gold M0 与 LightMem hybrid 可并行**，
  GPT-5 架构师）：Fable 5 `0e38358` docs-only 审计由架构师复跑 `5 passed in 0.78s` 并合入
  `8e108e4`；核心 gold-group 方案采纳，但 actor 的“BEAM conversation 内 id 唯一/歧义恒 0”
  被全量 Arrow + adapter 重扫推翻，现行数字为 1M 四个异常 conversation、41 个含歧义题、
  198 个逐题歧义原子，10M 另有 1 个 unmatched。LME 两官方聚合路径裁定主
  `run_retrieval.py` 的 419 为 parity canonical，470 仅披露为辅助脚本冲突。私有 schema
  进一步收紧为 `GoldEvidenceGroup(unit_id, child_ids, mapping_status)` + 多 view
  `GoldEvidenceGroupSet`，version 属 benchmark policy，不属 method。LightMem PR #72 仍是
  open docs-only；源码继续证明 extraction `source_id` 是 pair index、后续固定读 user slot。
  因此 unified 主 build 采用 hybrid + role-slot placeholder，但 LME turn/BEAM message
  provenance 不得因“内容可见”冒充 exact。两张自包含卡待用户并行派发；MemBench split
  必须等 gold M0 验收，零真实 API。

- 2026-07-16（**历史断点，已被上方 Fable 回卡强验收取代；当时审计待派**，GPT-5
  架构师）：OpenCode + DeepSeek V4 Flash 提供的两条
  线索经架构师独立读源码和真实数据复核。① LightMem `messages_use=user_only` 确实把
  assistant 排除在 extraction prompt 外；官方 collaborator 也确认 LongMemEval Table 2 初版
  就是 user-only。裁决：它是可复现但受限的 reproduction profile，不是 role-complete unified
  主轨；unified 五格改用显式 `hybrid`，并披露 segmentation 仍 user-anchored，不修改算法核心。
  ② MemBench FirstAgent 把 `{user, agent}` 拼成伪 user turn 违反 canonical `Turn` 契约，须拆；
  但 `target_step_id` 仍指 pair-step，必须先裁 gold evidence unit，不能让 Recall 分母翻倍。
  ③ BEAM 100K/500K/1M 全部 session 都是 first-turn anchor；10M 为 999 first-only + 1 none，
  当前 `turn_time → session_time → None` 正确，不解冻时间门。LightMem gap matrix 现为
  B1/B3/B6/B7/B8/B8+ revalidated，其余定点 pending。旧 M0-4 “role 变化非 blocker”已加
  superseded banner。当前只允许派 Fable docs-only 卡；零生产代码、零真实 API。

- 2026-07-16（**Track identity M0 R1/R2 强验收完成；下一站 LightMem 重认证**，GPT-5
  架构师）：首轮 `81f2708` 经 full diff 驳回后，用户授权 Codex subagent 在原 worktree
  线性追加 `cba25a8`；架构师独立复跑 R1 八文件 `416 passed, 1 warning` 并用五家真实
  TOML/六个非法对象探针复核。首次主树全量又抓到 fake registration 错回查全局 registry，
  尾行 `4 failed, 1302 passed`；R2 `2beda2d` 删除猜测 fallback，要求当前 registration
  显式声明 build identity，并锁 factory/outputs 前 fail-fast。三批线性合入主线为
  `dcd3e7b` + `d6fd56f` + `d032d45`；原四失败 + 新反例 `5 passed`，最终全量
  **`1307 passed, 3 deselected, 2 warnings, 4 subtests passed in 142.51s`**，compileall exit 0。
  M0 不切 embedding、不调用 API；LightMem/MemoryOS B10 truthful readout-only 身份门关闭，
  Mem0 仍因 product-default OpenAI build 未迁移而保持部分完成。下一动作不是盲跑 smoke，
  而是先产出 LightMem 当前 commit 的 B1-B11 revalidated/retested/N/A/pending gap matrix。

- 2026-07-16（**历史断点，已被上方 R1/R2 最终验收取代；当时首轮未通过**，GPT-5 架构师）：
  混合入口先后经历 CC+GLM-5.2 崩溃、用户切 MiniMax M3、会话压缩，最终首轮 commit
  `81f2708`；无法核实唯一模型而未写 Co-Authored-By 是正确做法，但 actor 报告的 author
  email 与 `git show` 实盘仍不一致。架构师复现卡内 `282 passed, 1 warning`，full diff 与
  现场反例判定不合入：当前 PyPI MemoryOS 被错误标成 ChromaDB reproduction variant；
  build override/history/pending revision 非法组合仍可构造；manifest 可出现 top=v1、inner=bogus；
  commands/evaluate 和 strict resume 强反例在 note 中宣称完成、实盘却没有。用户明确授权
  架构师启动一个 Codex subagent，在同一 branch/worktree 追加 R1，不 amend、不 push。
  同轮用户纠正 actor 经济学：Fable 只给高判断密度任务，不给纯繁琐大活。共享修复完成后
  从 LightMem 起逐 method 重走 B1-B11，旧证据逐项 revalidate/retest，不盲目全删重跑。

- 2026-07-16（**历史断点，已被上方 M0 R1/R2 验收取代；当时 track identity M0 待派**，
  GPT-5 架构师）：Fable 5 `82ffd8c` docs-only 审计经逐锚复核与文档标准门合入 `4a0533f`；
  架构师订正两处：托管 OpenAI embedding 只可称 API identity 公开、revision
  `provider_managed_unpinned`，不能称权重级可复现；MemoryOS native `max_tokens=2000`
  已在源码落地，不是待修项。架构裁决：Mem0 迁 OpenAI text-embedding-3-small/1536 须重建；
  LightMem 以 `product_canonical_required_config_v1` 锁 local MiniLM/384 且零重建；MemoryOS
  PyPI 默认 MiniLM/384 零重建，ChromaDB 是 reproduction variant。MiniMax M3 `6af75a3`
  的 effective-time 实现经 full diff、定向 `61 passed`、五 benchmark 扩展 `170 passed`
  验收；因 actor commit 错写 Sonnet 4.6 trailer，架构师未保留虚假身份，以主线 `7752dab`
  重建提交。最终 `1243 passed, 3 deselected, 2 warnings, 4 subtests passed in 132.54s`，
  compileall exit 0。下一张唯一施工卡为 track identity M0；零真实 API。

- 2026-07-16（**embedding 新政策落盘；Mem0 B4 + 三家身份审计两卡待并行派发**，GPT-5
  架构师）：
  用户纠正“原文 + typed timestamp”不等于要求正文双拼；源码复核确认 MemBench adapter
  无损保留 place/time 并抽取 turn time，但 Mem0 `_turn_to_message()` 又前置同一
  `[Turn time]`；同时 `_turn_to_message()` 在 turn/session 并存时会双前置，与用户明确的
  `turn_time → session_time → None` fallback 不一致。裁决为 typed method 保留原文+typed
  双通道、content-only method 每条正文只出现一个 effective timestamp；不按 benchmark 名
  特判，以公开 turn metadata 标记原文已嵌 source time。Mem0 局部重开 MemBench/BEAM/
  HaluMem B4/B11 输入形态，LoCoMo/LongMemEval 与其余证据保留。另撤销“native 是一个全套布尔值”和“多仓库优先复现版”
  的旧政策：unified 主 identity 是通用 OSS 产品实现；native 只容纳同算法的官方配置，
  eval fork 另列 reproduction variant；MemoryOS 当前只 readout-native，PyPI 暂为 canonical，
  ChromaDB 等价性待审。另经用户授权作出新政策变更：unified embedding 主轨采用每家 pinned
  product default，同一 method 跨 benchmark 固定；2026-07-09 shared MiniLM 决策在当时有效，
  既有配置/结果不删除，改标 `controlled_embedding_v1`。Fable 卡只查精确默认、算法身份与
  重跑面，不替架构师二次裁政策。两张自包含卡使用独立 worktree/branch，可并行派发；零真实
  API。

- 2026-07-15（**RetrievalEvidence M0 强验收完成；M1 解锁、尚未派发**，GPT-5 架构师）：
  Opus 4.8 首轮/R1 `5fd5ac1` + `1999f56` 线性合入为 `352ed3c` + `6b4fd4e`；架构师复现
  R1 `34 passed` 后发现 list/dict 会从 frozenset membership 泄漏 `TypeError`，以独立
  `afd4040` 加字符串短路和反例，M0 七文件套件 `307 passed, 1 warning in 16.09s`。第一次
  主树全量进一步抓到 registered CLI preflight 尚未盖 v1、会拒绝自己刚落盘的 resume run；
  `c879343` 在 preflight 前从 `MethodRegistration` 写同一 contract identity，保留严格
  mismatch。第二次全量越过 resume 后，MemoryOS 整字典旧期望正确暴露 schema 演进，测试
  补 v1 而生产字段不撤回。最终主树
  **`1235 passed, 3 deselected, 2 warnings, 4 subtests passed in 142.03s`**，compileall exit 0。
  M0 现完整覆盖协议→provider→artifact→manifest→registered preflight/resume；M1 才改五个
  evaluator、LongMemEval no-target 分母和 top-k depth。零真实 API。

- 2026-07-15（**历史断点，已被上方 M0 强验收取代；当时极小 R1 待派**，GPT-5
  架构师）：Opus 4.8 首轮 `5fd5ac1` 共 16 文件、844+/3-；协议、两条 artifact、strict
  resume version 与 Mem0/LightMem/MemoryOS 逐题矩阵均按卡落地。actor 首跑的两项 HaluMem
  失败确为隔离 worktree 缺 gitignored data；架构师补齐 data 后不是做 `295+2` 推断，而是
  重跑原七文件整套，现场 `297 passed, 1 warning in 12.35s`。full diff 另抓到
  `EvidenceAssertion(status="bogus", reason_code="x", reason="y")` 会成功构造：Literal 不做
  runtime 校验，未定义状态可能进入 artifact/evaluator。故 `5fd5ac1` 暂不 cherry-pick；
  极小返工卡=`branches/retrieval-metrics/cards/
  actor-prompt-retrieval-evidence-contract-m0-r1.md`，只补 status fail-fast + 强反例 + note，
  follow-up 不 amend。另复核 Mem0 输入链：时间已内联 messages 且 MemBench 原 place/time
  保留；两处 metadata-only 过时文档已进入本轮勘误。零真实 API。

- 2026-07-15（**LightMem preserve-none Phase B 强验收通过；RetrievalEvidence M0
  解锁待用户派发**，GPT-5 架构师）：Opus 4.8 首轮 `e1cfb75` + R1 `0d6bf9f` 已逐行
  审读；R1 独立定向 `91 passed, 1 warning in 6.32s`。线性合入主线为 `915f73c` +
  `3968373`，保留首轮/R1 审计链；主树全量
  `1206 passed, 3 deselected, 2 warnings, 4 subtests passed in 142.81s`，compileall exit 0。
  最终契约：只有显式双 None 进入 online-soft preserve 分支，缺键/无 fallback 空串仍拒绝；
  `MemoryEntry` 三个时间字段类型与真实 None 一致；consolidated 继续 require。MemBench 100k
  结果必须声明 framework-extended missing-time compatibility，不冒充 upstream parity。
  Phase B 关闭后，下一卡=`branches/retrieval-metrics/cards/
  actor-prompt-retrieval-evidence-contract-m0.md`；只由用户选择跨模型 actor 派发，M1 不得
  抢跑。零真实 API。

- 2026-07-15（**历史断点，已被上方 Phase B 强验收取代；首轮未通过、R1 当时待派**，GPT-5
  架构师）：Opus 4.8 首轮 commit `e1cfb75`，worktree clean、允许清单与 diff-check 通过；
  架构师独立复跑为 `87 passed, 1 warning in 7.07s`，但 full diff 发现现有测试未覆盖的
  三项契约缺口：① normalizer 用 `msg.get()`，把“缺键”误当 explicit None 放行；
  ② adapter 的 falsey 分支会把无可用 fallback 的空字符串洗成 None；③ `MemoryEntry`
  已存 None，annotation 仍声明 `str/float/str`。因此 `e1cfb75` **未 cherry-pick**，不因
  测试全绿降格放行。极小返工卡=`branches/membench-time-semantics/cards/
  actor-prompt-lightmem-missing-time-online-soft-r1.md`，继续原 worktree、只补 follow-up
  commit；RetrievalEvidence M0 继续暂停。另确认 Opus 此前“未看到请求”的根因是旧卡把
  “待用户选择 actor”调度状态写进了可复制 prompt，已把规则改为：调度状态只在 README，
  actor 收卡即派发完成。零真实 API。

- 2026-07-15（**MemBench Phase A 强验收通过并恢复 frozen-v1；LightMem preserve-none
  Phase B 卡待派**，GPT-5 架构师）：① Opus 4.8 实际 commit `0fbf8e1`（actor 回报漏写
  hash，架构师以 git log 找回）full diff/允许清单通过；架构师定向
  `31 passed in 3.68s`，合入 `2e6b4d7`；主树
  `1193 passed, 3 deselected, 2 warnings, 4 subtests passed in 144.68s`，compileall exit 0。
  MemBench A2/A8 与 frozen-v1 恢复。② LightMem 一手调用链裁决：只删 normalizer 校验会在
  sequence datetime parsing 再失败，且现有 catch 会连带抹掉 speaker/external id；
  consolidated/summary 大量依赖 float timestamp，不能接 None。online-soft 主线则只做抽取、
  direct insert 与 vector similarity retrieve，本地 Qdrant probe 也确认 null payload 可写，
  故允许显式 `missing_timestamp_policy=preserve_none` 的窄兼容扩展；timestamped 行为不变，
  禁 synthetic time，结果标 framework-extended。③ Phase B 卡=
  `branches/membench-time-semantics/cards/actor-prompt-lightmem-missing-time-online-soft.md`；
  RetrievalEvidence M0 继续暂停。零真实 API。

- 2026-07-15（**历史断点，已被上方 Phase A 强验收取代**；LightMem online-soft
  强验收通过；MemBench 100k 时间语义重开；新卡待
  用户派发**，GPT-5 架构师）：① Claude Sonnet 5 `19a0934` full diff 与允许清单通过，
  架构师复跑 `78 passed, 1 warning in 8.10s`，cherry-pick 为 `825132f`；五格默认
  `online_soft`，LoCoMo consolidated 显式补充轨，backend 仍锁 `update="offline"`，
  lifecycle/adapter v2 进入 manifest；主树全量 `1191 passed, 3 deselected, 2 warnings,
  4 subtests passed in 142.37s`，compileall exit 0。actor 任务级评分 9.7/10，账本=
  `docs/reference/actor-performance-ledger.md`。② 用户指出 MemBench 100k message 无独立
  time，官方四源实扫：307,738 step 独立 time 字段为 0；49,738 文本有完整 timestamp，
  258,000（83.84%）无。当前未把 `QA.time` 直接写进 message，但把首个有时 turn 派生为
  session_time 并扩散给无时 noise，裁为同级伪造。③ 新裁：内嵌时间只结构化给本 turn；
  原 place/time content 对所有 method 完整保留；官方无时 noise 不过滤并保持 None；MemBench
  session_time=None；QA.time 只进 query/prompt。`None` 兼容性按 method 实现裁：LightMem
  明确拒绝，A-Mem 接受但生成 method-native ingestion wall clock，后者不得冒充 source
  time。**当时** MemBench frozen-v1 暂停，LightMem × 100k 在通用输入预检前不得真实运行；
  该状态现已由上方 Phase A 验收与 preserve-none Phase B 裁决取代。④ Phase A 自包含卡=
  `branches/membench-time-semantics/cards/actor-prompt-membench-time-semantics-phase-a.md`；
  RetrievalEvidence M0 因后续 registry/LightMem Phase B 可能重叠继续暂停。零真实 API。

- 2026-07-15（**LightMem paper online-soft 改判；活跃支线分层；新卡待用户派发**，GPT-5
  架构师）：① 用户纠正“online soft”是论文行为而非代码 enum，架构师亲读官方 PDF：
  §3.3 定义 direct insert；LME 表 2 成对报告 online-soft/OP-update；LoCoMo 表 3 只报
  post-update headline，但官方脚本保存 pre/post 两态。② 代码映射复证：
  `offline_update(memory_entries)`=embed+insert，`online_update()`=空壳，
  `offline_update_all_entries()` 才会 update/delete。撤销下方历史断点中“主线必须
  post-update”的第④项；现裁五格主 profile=`online_soft`，LoCoMo consolidated=补充轨。
  ③ 当前代码尚未切换，先派 `branches/lightmem-lifecycle/cards/
  actor-prompt-lightmem-online-soft-profile.md`；RetrievalEvidence M0 暂停并改为依赖实际
  lifecycle。④ 两条活跃支线收进 `branches/{lightmem-lifecycle,retrieval-metrics}`，并把
  “卡必须醒目标明派/不派 + 白话解释”和支线目录门写入 AGENTS/playbook。零真实 API。

- 2026-07-15（**两份 retrieval audit 强验收通过；资格架构裁定并派 M0 卡**，GPT-5
  架构师）：① Sonnet 5 Mem0 audit `30f22dc` 合入为 `dc15304`；控制流复证当前生产
  `Memory.add()` 只产 ADD，但架构师纠正自己任务卡的过宽标签：ADD-only mutation 不等于
  fact-level semantic provenance。Mem0 逐格收紧为 LoCoMo/MemBench=turn、LME=session、
  BEAM turn Recall=N/A，method frozen-v1 保留并携 metric 勘误。② Sonnet 5 framework
  audit `0f8b382` 合入为 `c36b171`；架构师回读官方源码并只读计数两份 500 题 cleaned
  数据，均为 30 `_abs` + 21 无目标题，确认框架把官方应剔除的后者记 1 分；同时确认
  k30/50 被 query top_k=10 硬挡。③ 架构裁决=provider 逐题陈述 semantic provenance/
  stable ranking 事实，evaluator 按 metric requirement 推导 valid/n_a/pending；拒绝静态
  method 字段扩张和独立人工 eligibility 白名单。④ LightMem 不切 `online`（函数空壳）；
  LoCoMo 主线保留官方 post-update，pre-update 仅允许另名 ablation。⑤ 用户指出卡尾重复
  prompt 与 subagent 禁令过度，已同步 AGENTS/onboarding/两本手册并修正两张历史卡；
  新 M0 卡自身即 prompt、待用户派发，M1 依赖 M0 强验收后再写/派。**本条④及“M0 现在
  派发”的时序已被上方最新 lifecycle 断点撤销；保留这里只作历史留痕。**

- 2026-07-15（**Codex 压缩自举 hook 落地；LightMem lineage 修复拒绝合入；两张横向
  审计卡待用户派发**，GPT-5 架构师）：① 官方 Codex manual 与本机 catalog 核证
  hooks=stable，当前模型 max context=272,000；配置不能扩大硬上限。新增版本化
  `.codex/hooks.json`：`SessionStart(compact)` 注入四步恢复门，Bash `git commit`
  注入显式暂存提醒；不自动倾倒聊天或修改文档，首次加载须用户 `/hooks` 信任。
  hook/文档定向 `10 passed`，主树全量 `1181 passed, 3 deselected, 2 warnings,
  4 subtests passed in 161.04s`，compileall/diff-check 通过；同时修复
  `docs/archive/logs/README.md` 被全局 `logs/` 规则误忽略、导致 clean worktree 文档
  标准假红的基线可移植性缺口。
  ② Sonnet 5 `3e2d957` 全 diff 审读、定向复跑 `57 passed, 1 warning in 7.05s`；实现
  忠实但 transformation-input union 会制造 semantic provenance 假阳性，故不
  cherry-pick，LoCoMo post-update Recall/NDCG 改 N/A。③ Mem0 当前 phased add 源码
  初读呈 ADD-only；架构师撤回“看到 CRUD API 即认为 mutation 可达”的过早断言，交
  `branches/retrieval-metrics/cards/actor-prompt-mem0-provenance-validity-audit.md` 做负空间
  证明。④ LME NDCG 顺序/depth 与 per-cell valid/N/A/pending 交
  `branches/retrieval-metrics/cards/actor-prompt-retrieval-metric-eligibility-audit.md`
  做框架契约审计；两卡均 docs-only、可并行、只由用户派 actor。

- 2026-07-15（**MemoryOS M2 强验收通过；LightMem B5/B11 因 lineage 缺口重开**，
  GPT-5 架构师）：① MemoryOS 三行返工 `4b75e1a` 审读后 cherry-pick 为
  `bfe69f1`，主树定向 `6 passed in 2.71s`、全量
  **`1176 passed, 3 deselected, 2 warnings, 4 subtests passed in 142.46s`**；M2
  正式接受，下一门=用户授权的五格真实 smoke，未确认预算/规模/run_id 前不调用
  API。② Sonnet 5 LightMem 审计 `017ebe4` 合入为 `0333c7a`；架构师回读官方
  `UPDATE_PROMPT`、update 写点、本框架 evaluator 与 MemoryData 后裁决：LoCoMo
  post-update 的 memory 可整合 candidate 文本，但现 payload 只保留 target 单一
  `source_external_id`，既有 Recall@10 可机械计算却不是完整 turn lineage，故
  `lm-locomo-unified-prov1` recall=0.0 的**可信指标声明作废**，LightMem frozen-v1
  暂停于 B5/B11。其他 answer/F1/成本证据及不跑该 merge 阶段的四 benchmark 不随之
  作废。③ 当时批准 metadata-only plural lineage 修复，严禁重算 embedding 或改变
  update/delete；卡=`branches/lightmem-lifecycle/cards/actor-prompt-lightmem-lineage-repair.md`，
  仍由用户选择跨模型
  actor 派发；**该批准已被本页最新断点的二次裁决撤销**。④ 粒度裁决：
  `consume_granularity` 不应与 provenance 强绑；当前门
  只强校验结构、漏了变换后语义完整性。Recall@k 先作为 method-native item 辅助
  指标，未补 source/token-budget 归一化前不单独作跨 method headline。完整裁决见
  `branches/lightmem-lifecycle/notes/lightmem-update-lifecycle-ruling.md`。

- 2026-07-15（**M2 合入后全量回归阻断 + 两卡待用户跨模型派发**，GPT-5
  架构师）：M2 `97e7c18` 已经逐行审查并 cherry-pick 为主线 `e2fff4b`；定向
  `146 passed in 15.03s`、compileall exit 0，但合入后主树全量为
  **`2 failed, 1174 passed, 3 deselected, 2 warnings, 4 subtests passed in
  134.21s`**，故 M2 **尚未通过**。两项失败同源：registry 正确新增
  `benchmark_name`，`tests/test_memoryos_registered_prediction.py` 的
  `_FakeMemoryOS` 未镜像该 factory 契约。已写极小返工卡
  `actor-prompt-m2-memoryos-regression-fix.md`，生产接口不回退，只同步测试替身并
  补注入断言。LightMem offline update × Recall@k 纯取证卡仍为
  `branches/lightmem-lifecycle/cards/actor-prompt-lightmem-offline-recall-audit.md`。
  **两卡都只交给用户，由用户按
  Sonnet 5 / GLM-5.2 / MiniMax / Codex 等额度与能力选择 actor；架构师不得默认
  自行启动 Codex subagent。**本轮曾误启动一个 Codex LightMem 子 agent，用户纠正
  后已立即中止，并清除其 clean worktree/空分支，无交付被采用。

- 2026-07-15（**GPT-5 架构师试任恢复 + M2 强验收进行中 + LightMem
  Recall@k 语义审计派卡**）：会话已发生压缩，架构师按 onboarding/本断点/git
  事实重建；MemoryOS M2 actor 回卡 `97e7c18`，独立定向复跑为
  `146 passed in 15.03s`、compileall exit 0，尚未因测试绿而接受，正在逐行核
  R1-R7 与主树全量门。用户新提出 LightMem LoCoMo offline update 后发生合并/
  删除时 Recall@k 是否仍成立，以及现有输入/来源粒度强校验是否合理；架构师保留
  最终裁决，已按额度经济拆出纯取证卡
  `branches/lightmem-lifecycle/cards/actor-prompt-lightmem-offline-recall-audit.md`，要求
  actor 对照官方 LightMem、
  本框架 evaluator 与本地 MemoryData，只交一手证据和候选风险，不改代码、不代裁。
  同轮还确认 `.claude/settings.json` 的 commit 纪律 hook 是 Claude Bash
  `PreToolUse` 提醒而非 Git/Codex 阻断钩子；跨模型持久规则仍必须落仓库文档。

- 2026-07-14（**R7 改判:image 框架统一(用户三次对峙胜出),M2 卡
  终稿待派**，Fable 5,周额度剩 10%）：**R7 v2**=image→文本是**数据
  表示问题非喂法问题**,框架级统一、同一把尺子(与 unified prompt 同
  哲学);击穿点=用户论点"多数 method 无 locomo image 官方姿势可抄,
  框架默认不可避免→默认取语义最优"。统一格式=
  `[Sharing image that shows: {caption}]`(恰=mem0 官方 blip-only 分支
  原文,mem0 零偏差;"sharing"语义准确表达对话中图片分享行为);
  query 全局禁用不变。落地=新共享 helper `methods/image_text.py`,
  memoryos M2 用之(与官方 eval `(image description:...)` 的偏差声明);
  mem0/lightmem 解冻件后续用同一 helper。**前一条记录中"各家抄各家
  官方"的 R7 v1 作废**。M2 卡终稿=R1 v2+R7 v2+R2-R6,待用户派发。
- 2026-07-14（**R1 二次修订(用户方案胜出)+ R7 image 裁决,M2 卡定稿
  待派**，Fable 5,周额度剩 11%）：① **R1 推翻重裁**:用户提出"ingest
  裸文本+检索出口身份映射"方案,架构师逐段核 `main_loco_parse.py`
  证实=**官方 eval 姿势的忠实迁移**(ingest :159-200 裸文本+槽位配对;
  出口 :88-96 拼 `{speaker_a}: {user_input}...`;**profile/knowledge 段
  官方用三正则回写身份** :105-113——user→speaker_a/assistant→speaker_b/
  I→speaker_b,金子级发现照抄)。旧 R1(content 前缀)作废:前缀会进
  抽取/摘要/embedding 改变方法内部行为,官方槽位方案无须发明。新增
  要求:speaker_map 随 state 持久化(并入 sidecar),resume 缺失
  fail-fast。② **R7 image 裁决(用户提案)**:各 method 抄各自官方
  姿势(memoryos=`(image description: {caption})`),框架不发明统一
  格式;**query 字段全局禁用**(数据构造副产物非对话内容);
  **mem0 image 现状=B2 缺口登记**(裸拼 caption,官方有 `[Sharing
  image that shows: {blip}]` 包装)→ mem0 解冻件待办(改+locomo 格
  重跑);lightmem image 官方姿势待核=登记。③ M2 卡定稿
  (R1 修订版+R7 内嵌),**用户尚未派发,下一动作=派卡→回卡强验收**。
- 2026-07-14（**M2-memoryos 裁决 R1-R6 + 施工卡写就**，Fable 5,用户 5h
  额度剩 10%,单批处理收束）：① **R1 speaker 内化**:维持 session 粒度
  adapter 自配(官方同构;框架不做通用 speaker 配对的理由=配对规则是
  method 身份,memoryos 官方是回填式非严格交替,框架强加一种语义反而
  失真)+**两侧 content 加 `{speaker}: {text}` 前缀**(mem0 官方同款;
  unified 无角色扮演,身份必须数据层内化);native 轨随之偏离官方裸文本,
  声明之。**用户"只喂 user 侧+改闸口"方案驳回**(third_party 算法红线+
  assistant KB 恒空+两人画像混一)。② **R2 unified prompt 不动**(同一
  把尺子;角色扮演只进 native 资产)。③ **R3 超参**:unified=pypi 默认
  不动;native LoCoMo bundle=paper 值(作者 issue paper 优先;MTM 语义
  歧义与 filter 阈值标 DISPUTED+注释);**澄清用户"直接改 eval/ 参数"
  提议:eval/ 不被运行(native 跑 adapter+pypi 引擎),bundle 配置即
  "用论文参数"的落地点,third_party 保持零 diff**。④ R4=provenance
  升 turn(page 文本反查 sidecar,mem0 M2 样板);R5=embedding 降级
  可审计标记;R6=native bundle 并入本卡(角色扮演 system 逐字资产化;
  **judge=无→native 评测=免费 f1**;identity 显式配置判例复用)。
  ⑤ **M2-memoryos 施工卡写就待派**(`actor-prompt-m2-memoryos-adapter.md`,
  裁决块内嵌);A-mem 前瞻已知:官方姿势=`Speaker {X} says : {text}`
  content 内化(用户一手核),其 M 阶段照抄自家姿势即可。
- 2026-07-14（**M1-memoryos 验收合入 + 三项用户疑问硬答案落档**，
  Fable 5）：① **M1 note 验收合入**（2785f00→160e38b,七节全锚质量高:
  eval/ vs pypi 八维代码差距、超参三岔口表(STM 7/1/10 三岔、queue
  10/10/7 pypi 失配、eval α/β/γ 失配论文、filter 阈值 DISPUTED)、
  官方 LoCoMo native 面=单格+answer gpt-4o-mini/0.7/2000+**无 judge=
  本地 token-set F1(native 格评测免费!)**、B5+ page 文本反查三步落点、
  B8+ gap=embedding 下载韧性+**retrieve embedding 异常静默降级空列表
  无 manifest 痕(比 mem0 BM25 降级更重,M2 须给可审计信号)**）。
  ② **缺时间戳答复(用户忘了当初处理)**:dataset-quirks.md 统一约定=
  **turn 无时间→session 时间兜底**;membench 原生无 session 级时间→
  100% 派生自首个带时间 turn,noise 消息 72-96% 无时间→兜底,
  2026-07-11 全量扫描证实**零时间戳 trajectory=0 兜底永不落空**;
  beam probing question 无时间=官方 prompt 无时间槽,parity 不注入——
  即"不传"只发生在官方本来就不用的位置。**本项 MemBench 裁决已被本页最上方
  2026-07-15 100k 重审推翻：可回填不等于语义真实，伪 Session 没有继承资格。**
  ③ **locomo speaker A/B 三家
  姿势硬答案(用户尖锐问)**:mem0=role 仅 API 结构标记(首现=user 交替),
  **身份保留在 content 前缀 `{speaker}: `**(adapter:1391-1421,官方
  harness 同款)零丢失;lightmem=speaker 字段全程透传+检索侧
  `_retrieved_speaker` 分组;memoryos=官方硬编码 user_input/
  agent_response 二元,adapter 镜像官方 eval 姿势(speaker_a→user 侧,
  unknown fail-fast,adapter:1049-1072),**官方 eval answer prompt 的
  角色扮演(system 定义 speaker 角色)已锚**(main_loco_parse.py:83-142),
  M2 native 资产化逐字含之。④ **畸形对话形态答复**:框架 pair 聚合
  orphan/dangling 标记不丢弃(v3 协议);memoryos 现状=lme 用 pair、
  locomo 用 session 粒度 adapter 内自配(与官方"speaker_a 开 page 另
  speaker 回填"同构且 session 边界更严,M1 §3)。⑤ 下一步=M2-memoryos
  裁决+施工卡(裁决方向预告:超参维持 pypi 默认+DISPUTED 标记落 status;
  native LoCoMo 单格资产化;B5+ sidecar;降级信号可审计化)。
- 2026-07-14（**跨模型可移植审计 + memoryos M-1 取证卡写就（三号煎饼
  起步）**，Fable 5）：① 用户拍板:暂不交接,但可能先让 GPT5.6 sol 试任
  架构师 → **`.claude` 专属内容内化审计**:9 条私有 memory 逐条核镜像
  (8 条已有仓库锚,**1 条真洞=commit 显式路径纪律只在 memory/本机 hook/
  onboarding,AGENTS 与 playbook 均无**)→ 补 AGENTS 硬规则(含事故背景
  +"其他模型架构师无 hook,纪律以文档为准")；这是当时事实，现已由版本化 Codex
  hook 补齐；onboarding 新增 **§-1 非
  Claude 架构师注意项**(无 memory 召回/无 commit hook/无 CLAUDE.md
  自动加载的三项替代路径)。② **M1-memoryos 取证卡写就待派**:纯取证
  七节(eval/ 代码副本差距/超参三岔口/粒度/隔离 clean/检索副作用+B5+
  落点/B8+ 调用点清单(新模板节)/native 预研),格式标杆=m1-mem0;
  架构师预锚:adapter 已接 memoryos-pypi(ws02.5 迁移)、TOML=pypi 默认
  且与 eval/ 调参不同(注释自述)、受保护 outputs 提醒进卡。③ 下一步:
  用户派 M1-memoryos → 回卡验收+裁决 → M2 施工卡(含 native bundle,
  新模板);mem0 已 🧊,其待办只剩 R0 前置包+upstream drift 对比
  (都在日程,不阻塞)。
- 2026-07-14（**🧊 mem0 method-frozen-v1（二号煎饼收官）+ M5 验收 +
  四项裁决 + B1 用户拍板**，Fable 5）：① **M5 验收合入**（3772b73→
  1ae7e2b,纯 note,三节锚表全一手复核质量高）。② **四项裁决**：
  (a) B7 native 计量=**政策违规确认**（政策原文"统计跟随实际嵌入段",
  M5 三格对照=序列化失配、正文集合无漏）→ 不阻塞 frozen,**进 R0
  前置包**(native 效率数字唯一消费方=R0 校准);(b) lme/beam native
  judge 路由缺口(commands.py:213 只认 locomo-judge)→ 同进 R0 前置包;
  (c) B8+ 两下载点(SentenceTransformer/FastEmbed BM25 首次缓存,BM25
  失败静默降级)→ 声明+新机器/full 前预热预检;(d) **B1 用户拍板**:
  commit 号不可溯(压缩包下载),content-hash 为准,**5×10 完工后 git
  clone 最新 upstream 对比 drift(提上日程,进待办堆;不改版本锁)**。
  ③ **native 三格免费评六项落盘**(架构师跑,locomo f1 0.014/beam f1
  0.16/recall 类与 unified 同姿势;五件套②对 native 格闭环=免费面)。
  ④ **`notes/mem0-frozen-v1.md` 落档**:13 格证据面+方法身份要点+
  **九项声明缺口**+R0 前置包(mem0 份)+校准回填指针;status 行 mem0
  全绿 **frozen=v1**。⑤ **assembly-line 终账回填**:实际 ≈10 回合
  (超计划六成,半数为一次性资产),**memoryos 边际预期 5-6 回合**,
  两条教训入模板(M-1 自带 B8+ 节/native bundle 并入 M-2)。⑥ 下一步=
  **架构师转移**:建议 Fable 5 余量做交接刷新,继任者(人选用户裁量,
  架构师建议 Opus 4.8 见 playbook §9.5+断点区)从 memoryos M-1 起步;
  memoryos 考点已预告(eval/ 代码副本嫁接+超参三岔口)。
- 2026-07-14（**mem0 对表缺项清单（对表仪式首次正式执行）+ M5 取证卡
  派发**，Fable 5）：① **对表输出（frozen 前置件,B11 冻结门仪式）**——
  重读 checklist B 项原文+status 行后的缺项清单:
  (a) B1 快照上游 commit 来源:用户提供 or frozen note 声明
  content-hash 为准(仍待用户一句话);(b) B7 native 注入 token 审计
  (三格 native builder 落地后现在可查)→ **M5 卡**;(c) B8+ 韧性
  清单未列 → **M5 卡**;(d) native 格评测路由(judge profile 走 bundle
  还是注册默认)事实待锚 → **M5 卡**,取证后架构师裁口径;
  (e) frozen 声明项预登记:真实 resume 缓期(LightMem 同款)/top_k=20
  vs @k≤50 截断(full 前裁)/transformers>512 警告(full 前复查)/检索缺
  sidecar 映射 fail-fast 观察项(六格+par2×4+native×3 全程未绊,转正式
  声明)。② **M5-mem0 纯取证卡写就待派**(零生产代码,三节锚表:B8+
  调用点韧性/B7 token 审计/评测路由;embedding 已初核=本地 huggingface
  零网络)。③ **native 参数口径确认(用户问)**:native=作者**复现目录**
  的 repo 默认(mem0=memory-benchmarks/ 目录),非产品 repo 默认、非
  paper 正文;三者失配走 dual-track-config-policy §5 检查,失配无作者
  指引标 DISPUTED。**memoryos 前瞻(用户考题)**:其复现目录 eval/ 是
  **改过代码的专用评测副本**(非纯参数目录)——ws02.5 接口保真裁决=
  代码必须 pypi 产品版,故 memoryos 的 native 只能是"eval/ 超参嫁接
  产品版接口",嫁接等价性=memoryos M-1 取证核心考点(assembly-line
  预告的"超参三岔口"坑,paper/eval/repo default 三份配置对比必做)。
  ④ M5 回卡验收后:frozen note(含对表清单终态+assembly-line 校准
  回填)→ mem0 收官 → 架构师转移窗口。
- 2026-07-14（**native 三格 smoke 通过（B10 收口）+ ⑤轨别口径裁决 +
  额度战略（剩 25%,架构师转移临近）**，Fable 5）：① **native 三格开箱
  全绿**（用户跑,各 1/1）：manifest `prompt_track=native`;prompt_messages
  =各自官方模板（BEAM 格=M4 刚接的官方 builder 实弹生效）;items=0 与
  unified s2 姿势一致（同切片同 0.1 门槛,非回归）;双口径并存落盘
  （answer_prompt unified 版同存,供对照）。**native 语义答复（用户问）**：
  native 改三样=answer prompt（官方模板）+ answer 采样配置
  （temperature 0.0/max_tokens 4096/top_p None,官方 harness 值,对照
  unified 的 benchmark 统一配置）+ judge prompt/采样;**不改**模型名
  （统一 gpt-4o-mini,R3）与 ingest/检索/embedding 运行时（embedding_ref
  仅声明引用,build 侧仍统一=LightMem 同款已声明缺口）。② **⑤并行轨别
  口径裁决**（用户问 native 要不要 par2——该架构师主动想到,记自省）：
  ⑤在 unified 轨执行,native 由正交性声明覆盖（track 只切 answer 阶段,
  锚已入 checklist B11⑤;失效条件=native build 侧运行时切换落地时必补）。
  ③ **mem0 B10 收口**;B11 predict 面全齐（unified 六格+par2 四格+
  native 三格）。frozen 前剩:对表缺项清单（B1 快照来源/B7 效率审计项/
  B8+ 韧性清单/native 格评测口径裁决）→ frozen note+assembly-line 回填
  （校准诚实结论:mem0 实耗超 4% 预算模型,但含大量一次性资产——
  M0-11/13 框架债、B8+/对表/时刻表机制、native bundle 样板,后续 method
  不重复付费）。④ **额度战略**：周额度剩 25%,9 method 不现实,架构师
  转移临近;建议=Fable 5 用余量收 mem0 frozen+刷新交接,继任者从
  memoryos 起步(人选裁量权在用户,架构师建议见断点区本条时点的会话)。
- 2026-07-14（**par2 三格全绿（B11⑤ 收口）+ M4 复工验收合入 + 防线分层
  答复**，Fable 5）：① **locomo/lme/beam-100k par2 开箱全绿**（用户跑,
  各 2/2;workers=2+provenance 章+双 worker sidecar 三格齐）——**B11⑤
  并行冒烟四格全齐**（membench/locomo/lme/beam-100k;halumem N/A 判例;
  10m 由 100k 覆盖声明）。插曲:用户忘贴三条结果,架构师直接读 tee 日志
  完成开箱=**tee 纪律的结构性价值现场证明**（防线不靠人记性）。
  ② **M4 复工验收合入**（082aa00+3c00a0c cherry-pick → e9adeeb/181328d）:
  identity 显式优先+启发式回落零回归;`_mem0_bundle` 三格注册,模型统一
  （R3）,judge parity 测试锁**实际调用 builder**（陷阱#1 意识内化）;
  BEAM builder `top_k=None` 疑点架构师核官方源结案（builder 内 top_k 只做
  切片不进文本,框架检索已截,None=正确）;文档标准盲点第四例又未出现。
  reader v3→v4。unified 字节不变有测试钉死。③ **native 三格 smoke 命令
  交用户**（mem0-{locomo,lme,beam}-native-s1）;跑通后 B10 收口,然后
  对表输出缺项清单→frozen note。④ **"用户不能提醒一辈子"答复落档**:
  防线分层=**产物驱动**（对表输出是 frozen note 必要组成,不填不成文）>
  时刻表（使用时重读）> 用户抓漏（最后防线,不该是常用防线）;错误代价
  分级=流程漏项（漏跑一格）天然可逆、补跑即愈,会让项目"完蛋"的数据
  正确性错误已全部压在代码级硬校验上（私有数据 4 层/manifest 严格比对/
  fail-fast/parity 锁）——体系设计目标从来不是"架构师不犯错",是"可逆
  错误廉价暴露、不可逆错误结构性拦截"。
- 2026-07-14（**par2 通过（M0-10 挂账清）+ M4 停工裁决（方案 A 扩卡）+
  时刻表机制**，Fable 5）：① **membench par2 开箱全绿**（用户跑,4/4,
  两 worker 各自加载模型=真并行）：manifest `max_workers=2` + provenance=
  turn 章 = **M0-10 的 workers>1 manifest 抽查挂账清账**;sidecar 按
  worker_0/worker_1 分立=worker 间物理隔离实弹验证;items/时间戳与 s2
  单 worker 完全一致。**B11⑤ 并行冒烟剩余**:locomo/lme/beam-100k 三条
  par2 命令已交用户（各带 `--conversations 2` 防单 conv 空转,2026-07-13
  判例）;10m 声明由 100k 覆盖（同 runner 同隔离机制,10m 数据结构差异在
  ingest 层,与并行正交）;halumem ⑤=N/A（既定判例）。② **M4 停工裁决**：
  actor 教科书级停工（BEAM 落 adapter generic reader 而非官方 prompt,
  五步证据链架构师一手复核属实,adapter:1771-1775 只有 locomo/lme 分支)
  → **采纳方案 A**：扩允许 mem0_adapter.py;**benchmark identity=显式
  配置禁扩启发式**（镜像 halumem `session_memory_report` 先例,factory 传
  `context.benchmark_name`,显式优先+无值回落旧启发式零回归）;BEAM 官方
  builder 接入;reader v3→v4;unified 字节不变测试钉死。裁决块=卡 §5,
  原 worktree 续工。③ **top_k vs NDCG@k 前置冲突登记**：lme
  retrieval-rank k∈[1,3,5,10,30,50]（官方全集）,而 mem0 repo 默认
  top_k=20 → @30/@50 是截断语义（gold 落在 21+ 位则必 miss）。full 前
  须裁决：a) 声明 k≤top_k 子集有效;b) top_k 提至 ≥50 并留痕偏离 repo
  默认（可做对照）。LightMem 及后续 method 接入时同项必查（进 B8+/@k
  取证面）。④ **"看"的机制升级（用户提议碰撞后固化）**：上任通读=全局
  地图缓存,但**会话压缩清缓存且不自知**——onboarding 新增 §5.5
  **文档使用时刻表**（七个动作时刻 × 必重读文档,含压缩后第一件事=断点区
  +时刻表本身）;"缓存"与"使用时重读"分层,后者才是保险。⑤ 交接质量
  改进持续项：瘦身试运行判据=下一任纯靠文档链 5 分钟上手,届时实测。
- 2026-07-14（**用户三连抓漏（对表失守/交接双源/韧性判据缺失）+ 付费评
  全落盘 = mem0 全指标齐**，Fable 5）：① **收口漏项认账**：checklist B11
  白纸黑字"两轨 smoke + ⑤并行冒烟",架构师宣布"付费评完=frozen 专场"时
  漏 par2+native 三格,被用户抓住——**playbook #23（收口宣言前先对表）+
  checklist B11 冻结门"对表仪式"固化**;par2 命令交用户（membench 4 conv
  天然多对话,workers=2,兼 M0-10 的 workers>1 manifest 抽查挂账）;
  native 三格=真施工缺口（`config_track.py` `_NATIVE_CONFIG_TRACK_BUNDLES`
  只有 lightmem 条目,mem0 走 native 会 fail-fast;adapter prompt_messages
  已供货 mem0_adapter.py:943,1023）→ **M4-mem0 卡写就待派**（模型不
  native,只 prompt/超参引用,R3 拍板原样）。② **付费评读数**：
  locomo-judge 0.0(n=1,零抽取格)、lme-judge 0.0(0.1 门槛)、beam-rubric
  100k 0.0 / 10m 0.1;halumem extraction f1 **0.0192**（recall(all)
  0.0097,**mem0 非零抽取首秀** vs lightmem 0.0）、update **1/7**
  (lightmem 0/7)、qa 1.0、memory-type 0.095（架构师跑,依赖序后评）。
  **extraction 分母 106 vs lightmem 108 结案**：gold=103、interference=2、
  update_routed=7 两家全同,差在 target 配对数（mem0 1/lightmem 3）=
  accuracy 侧分母 method 依赖,官方结构使然非 bug。③ **tee 事故**：
  halumem 三份付费日志因 run 目录 terminal-logs/ 不存在而静默丢失
  （evaluate 本体与分数 artifacts 无损）——已 mkdir+按用户终端粘贴回填
  并加注;纪律并入 #23（评测命令预包 mkdir）。④ **交接文档合并**（用户
  点破双源）：handover-to-next-architect.md 并入 architect-onboarding.md
  后删除（执行 2026-07-13 既定瘦身:只承载长效内容,在途状态只看 ws
  断点区）,AGENTS.md/playbook §9.5 引用同步。⑤ **checklist B8+ 外部
  调用韧性判据新增**（用户提议）：全调用点清单+超时+重试+失败不留半写
  state;mem0 现状 api_timeout_seconds=60/api_max_retries=8 已走 TOML,
  完整清单挂 B8+ 待列。⑥ **NDCG 答复**：框架 NDCG 只有 lme
  retrieval-rank（官方口径,已评 0.0）;其余四家官方无 NDCG,免费指标已
  全覆盖无漏。⑦ 下一步：par2（用户跑）→ M4 派发施工 → native 三格
  smoke（用户跑）→ **对表输出缺项清单** → mem0 frozen note。
- 2026-07-14（**s2 六格复证全绿 + BEAM 10m 首跑 + 免费评十一项落盘**，
  Fable 5）：① **五格 s2 开箱**（用户跑 predict）：manifest 五格全带
  provenance=turn 章（**含 halumem=M0-13 实弹复证 ✅**）、reader v3;
  membench 4/4 检索带对话时间 `2024-10-01 08:00` + timestamp_source=
  session_time + src_turns 命中 sidecar（**M3 实弹复证 ✅**）;locomo/lme/
  beam-100k/halumem 空检索姿势与 s1 一致（0.1 门槛/真零抽取判例不变）。
  **该 run 的 choice/provenance 历史产物仍保留，但 `timestamp_source=session_time`
  是派生伪 session 时间，已被最上方 2026-07-15 裁决作废，不再作为时间正确性证据。**
  ② **BEAM 10m 首跑**（用户点名 10m 数据结构不同,架构师亲跑+剪裁哨兵
  盯防：conversations=1 questions=1、sentinel=0）：**检索非空 items=2**、
  对话时间 `July-01-2024`（M0-6 月名产物）、src_turns 三段形态
  `p1:s1:t1`、sidecar 3 条映射——10m id 形态与 100k（`s1:t1`）不同但
  provenance 链全通。③ **免费评十一项**：membench 0.5/0.5/**0.167**、
  locomo f1 0.4/recall 0.0、lme recall/rank 0.0、beam-100k f1 0.1、
  **beam-10m f1 0.4**——与 s1 可比项逐项一致=M3 改动零扰动。
  **beam-recall 双 n=0 结案**：两格 smoke 首题均为 abstention 题
  （evidence=[]，evaluator 正确跳过 "no matchable gold evidence"），与
  检索空不空无关;s1 登记的 beam/lme 空检索计数语义差异待办**降级结案**
  （lme 题有 evidence 检索空→n=1 计 0 分;beam 题无 evidence→n=0 跳过;
  两 evaluator 行为各自正确,差异源于题目本身）。④ 付费评全套命令交
  用户（locomo-judge/lme-judge/beam-rubric-judge×2 + halumem 三件）;
  halumem-memory-type（免费,依赖 extraction+update）随后架构师跑;
  全套落盘后 mem0 frozen note 专场。
- 2026-07-14（**M3-mem0 + M0-13 验收合入（1153 passed）+ timestamp
  Platform-only 疑问结案**，Fable 5，批处理回合）：① **M3 ff 合入**
  （37640ef）：Phase A 硬答案=官方三套 benchmark 的 answer 上下文**全带
  时间**、读取字段均为 `created_at`（locomo 渲染 `(weekday, Month DD,
  YYYY)`/lme 按日期分组标题/beam `[YYYY-MM-DD]` 前缀）,其值=ingest 时
  显式传入的对话 epoch;修复=adapter 边界把 metadata 对话时间提升进
  created_at 槽（session_time→first_turn_time→turn_time→timestamp→
  created_at 回落链+timestamp_source 标记,墙钟另存 storage_created_at）,
  formatted_memory 取旧论文 `- {timestamp}: {memory}` 格式、无时间行为
  字节不变,reader prompt v2→v3。② **M0-13 cherry-pick 合入**（c5ba750）：
  op-level 复用 `_method_manifest_with_protocol` 盖章 +
  `_manifests_match_for_resume` 兼容旧 halumem run;真实复证挂账=下次
  halumem predict 后抽 manifest。**主树 1153 passed（基线+2）;文档标准
  盲点第四例未出现（两卡新函数全带中文 docstring,actor 已内化）。**
  ③ **timestamp 疑问结案（用户带 GPT 调查来问）**：GPT 方向正确且比其
  结论更彻底——OSS Python `Memory.add()` 无 timestamp 参数
  （mem0/memory/main.py:573 签名实锚）;**OSS REST server 的 MemoryCreate
  schema 也无该字段（server/main.py:178-187）→ 官方 harness OSS 模式发的
  timestamp 被 Pydantic 静默丢弃,真正消费它的只有 Cloud V3**
  （mem0_client.py:189-191 注释自证）——即官方 OSS 模式自己也丢对话时间,
  **登记 upstream issue 候选第 3 件**。我们的解=add 侧对话时间进
  metadata（OSS add 原生支持,M2 已在）+ M3 检索侧提升,零 third_party
  diff 达成官方 Cloud/论文语义,比官方 OSS 模式更完整。④ s2 五格
  predict 命令交用户（复证 M3 时间口径 + halumem manifest 盖章）;付费评
  按既定序推迟到 s2 后一次性做。⑤ assembly-line §五回填中期校准数
  （架构师批处理回合 5/计划 ≤6,意外 3 件均在缓冲带宽内）。
- 2026-07-14（**mem0 五格 predict 全通 + 开箱验收三发现 + 全框架首个非零
  recall**，Fable 5）：① 五格 predict 零报错,但**开箱验货**（playbook #22
  新原则,用户拍板"稳扎稳打"落档）查出三处:(a) **lme/beam 空检索结案=
  官方语义**——store 层验尸(sidecar 有记忆+qdrant 点在+run_id 匹配+自查
  filter 命中 score=1.0)→ 根因=mem0 `_search_vector_store` 把 threshold=
  None 强制回落 **0.1 相关性门槛**（main.py:1343-1346),官方 harness 同样
  不传 threshold=同姿势,声明性语义非缺陷;locomo 空=抽取真 0 条(sidecar
  空,诚实);(b) **B4 真缺陷**:formatted_memory 无对话时间,
  item.timestamp=实验墙钟 created_at,而 payload 里 session_time 明明在,
  规范化丢弃——**M3-mem0 卡写就**（先取证官方上下文时间口径再修,禁自造
  格式）;(c) **operation-level manifest 不盖 provenance 章**（M0-10 只修了
  generic 路径)——**M0-13 小卡写就**。② **免费评九项落盘**：
  **membench-recall=0.167(n=4)=全框架首个非零 recall,sidecar 首战即中**;
  membench choice/source 0.5;locomo f1 0.4/recall 0.0(n=1 真实);lme
  recall/rank 0.0(n=1);beam-recall n=0——**beam 与 lme evaluator 对
  "空检索问题"计数语义不一致(n=0 vs n=1),登记待查**。③ **UserWarning
  结案**：qdrant 本地模式 payload index 无效告警——replay 实证无索引时
  filter 仍正确生效(自查命中),纯性能层提示,零正确性影响,不动。
  ④ 日志全归位(9 份 evaluate 进 run 目录,5 份 predict 从 staging 搬入)。
  ⑤ 待办:M3+M0-13 可并行派(文件不相交);付费评命令交用户(locomo-judge/
  lme-judge/beam-rubric-judge×2 + halumem 三件+memory-type 后评)。
- 2026-07-14（**🧊 LightMem method-frozen-v1 + M2-mem0 验收合入（1151
  passed）**，Fable 5，批处理回合）：① **M2 通过 ff 合入**（559d7c9）：
  BEAM→pair、halumem→整 session 单次 add（判别键=session_memory_report
  旗）、clean hook 三件套（delete_all+新 third_party `delete_messages`+
  sidecar 清除,scope 格式 `run_id=<key>` 一手锚 `_build_session_scope`）、
  provenance sidecar（原子写+schema 校验+旧 state fail-fast）;**偏差接受
  并留观察项**：检索命中缺 sidecar 映射=fail-fast（严于 M1 §4 的逐项回落,
  真实 smoke 若绊住再放宽为回落+计数）。架构师补一行 docstring（worktree
  盲点第三例）→ 主树 **1151 passed**。upstream PR 素材第二件已备
  （m2 note §4）。② **LightMem 冻结**：B2/B4/B8/B11 收口（B8=检索纯读
  锚死 lightmem.py:648-710;B4 带 lme 无非零样本例外声明）,
  `notes/lightmem-frozen-v1.md` 落档（冻结语义+七项声明缺口）,status 总表
  LightMem 行全绿 method-frozen=**v1**;mem0 行同步（B1 🟡 upstream commit
  待溯）。③ **scope 命名答复（用户问为啥不是 conversation_scope）**：
  `session_scope` 是 mem0 messages 表自己的列名（storage.py schema）,
  第三方 diff 须随上游命名以利 PR;我们塞进去的值=isolation_key（=隔离
  空间级）,删的正是隔离空间,名与实的错位来自 mem0 的词汇表不是我们的。
  ④ 下一步:mem0 五格 smoke 命令交用户（`mem0-<bench>-unified-s1` 系列）。
- 2026-07-14（**M1-mem0 取证验收合入 + 六项裁决 + M2-mem0 施工卡写就**，
  Fable 5）：① M1 note 验收=流水线首张标准取证卡,质量标杆（七节硬答案+
  严格反证）。② **裁决 R1-R6**：native 注册面=locomo/lme/beam
  （memory-benchmarks harness;membench/halumem 无 native 格）;**当前
  harness answer/judge 默认 gpt-5→第一阶段不做其榜单校准复现,旧论文
  LoCoMo 路径（4o-mini）=未来校准候选**;B2 修 BEAM(turn→官方 2-turn
  chunk)+HaluMem(切块→整 session 一次 add),locomo/lme 已对齐不动;
  **B3=保留 worker 内逻辑隔离**（run_id namespacing 是官方复现自身姿势=
  方法身份,mem0 无本地大模型物理化收益小）,"清得干净"缺口走第二个
  B5+ third_party 最小 diff（SQLiteManager 增 `delete_messages(session_scope)`
  纯新增 API）+clean hook 挂接+污染场景测试;补生产 Qdrant 零 API 泄漏
  测试;并行维持 worker 间物理;history tombstone 声明无害;B5=id 映射
  sidecar 按 M1 §4 原案;B6=五格零 flush;**capability 枚举缺 session-report
  项=框架 backlog**（registry 无法静态拒绝,不阻运行,另立小卡）。
  ③ **M2-mem0 施工卡写就待派**（B2×2+B3 修复+B5 sidecar+测试,含批准的
  第二个 third_party diff）。④ **upstream 更新焦虑答复（用户问 mem0 官方
  repo 持续更新咋办）**：vendored 快照无嵌套 .git,source_identity=package
  version+文件列表+聚合 SHA-256（mem0_adapter.py:203-217）=内容寻址版本锁,
  上游更新与我们无关;**唯一遗留=快照的上游 commit 来源待溯**,请用户
  提供当初下载的 release/commit 号,提供不了则声明 content-hash 为准;
  接入顺序不因更新频率改变。
- 2026-07-14（**流水线文档落成 + M1-mem0 取证卡写就 + 额度战略**，Fable 5，
  用户周额度已用 54%）：① **`docs/reference/method-onboarding-assembly-line.md`
  新建**：LightMem M0 蒸馏——一次性资产白嫖清单（协议/provenance 链/
  halumem 样板/容忍变体/五件套判据/纪律件）、方法论泛化四则（B6=镜像官方
  复现脚本;B2=抄官方 wrapper 喂法;B9=模型统一;B3=逻辑隔离须过等价性
  三项）、标准卡序（M-1 取证→裁决→M-2 施工→验收→五格 smoke→frozen,
  架构师动作/method ≤6）、额度经济学（9×~4%+14% 缓冲;**mem0=二号煎饼
  校准 run,计量外推,超预算先报告不闷头烧**）。② **M1-mem0 取证卡待派**
  （零生产代码;核心=逻辑隔离等价性三项取证（用户点名,B8 clean-retry 缺口
  并案）+ B5 id-sidecar 落点 + halumem end_session 差距清单）。③ **halumem
  full 并行化设计裁决=继续缓行**：设计必要性取决于 cost-probe 的串行
  wall-clock 数字,full 本身在预算门后,预算批复前设计=可能白干的架构师
  额度。④ 用户战略拍板落档：**剩余 ~50% 周额度目标=接完其余 9 method**;
  frozen-v1 专场仍是 LightMem 收尾件（B2/B4/B8 🟡 收口）,可与 mem0 M-1
  并行推进（互不动同文件）。
- 2026-07-14（**🏁 LightMem 五格通关**（halumem ② 四指标收口）+ 三问答复
  落档，Fable 5）：① **通关达成**：halumem 四指标全落盘（extraction 0.0/108、
  update 0/7、qa **1.0**（Memory Boundary 题不知为不知=真金）、memory-type
  0.0/3;score 记录逐条核过=真实测量,judge 实读捕获记忆）,B11 smoke 半场
  五格全绿（详 lightmem.md B11 ⑧）。**下一件事=frozen-v1 note 专场**
  （B2/B4/B8 残留 🟡 收口核对 + 声明缺口清单：真实 resume 缓期/native build
  profile 未实现/halumem ⑤ N/A/op-level 并行化待设计）。② **@k 前缀答复
  （用户问）**：可行且已是现役做法——longmemeval-retrieval-rank 就是单次
  检索排序的离线前缀评（k∈[1,3,5,10,30,50]，3000 例官方零失配）;顺序不变
  是天然的（评测不重跑检索,只切一次落盘的有序 items）;**唯一预算前置=
  predict 时 top_k ≥ 未来最大 k**;真排序是前提,LLM 重组散文式记忆的
  method 对 @k = N/A（provenance items 为 ordered tuple 的原因）。
  ③ **smoke evaluate 精准性答复**：结构性保证——裁剪在 predict 前的
  Dataset 层,gold 与 prediction 是同一次裁剪的双生子同落 run 目录
  （private labels），evaluate artifact-only 按 id join,从不回原始数据集
  找子集。④ **命名瑕疵登记**：evaluate summary 的 total_questions/
  correct_count 对非 QA 指标是术语复用（extraction 的"question"=gold memory
  point,update 的=probe;correct_count=null=非二值指标）——cosmetic
  backlog（total_items 更贴切）,不动行为。⑤ **op-level 并行保障线**：
  halumem full 今天结构上只能串行（CLI+runner 双层硬校验）,不存在未冒烟
  并行进 full 的可能;将来立 op-level 并行化设计卡时,M0-12 固定 2-user
  形状复活为该设计的验收件;是否做,等 cost-probe 给出串行 wall-clock 再定。
- 2026-07-14（**M0-10 验收合入（1143 passed）+ M0-12 停工裁决（⑤=N/A）+
  halumem s2 流通 + 三项用户拍板落档**，Fable 5）：① **M0-10 通过 ff 合入**
  （e0af293）：MethodRegistration 加可选 provenance_granularity（LightMem=
  "turn"），并行协调路径按 system_factory 身份静态解析盖章，实例回退与
  fail-fast 保持;resume 兼容有测试钉死。实况修正：并行路径 system 实为
  `_UnusedRootSystem` sentinel 非字面 None，根因不变。**真实复证挂账：下一次
  任意 workers>1 predict 后 manifest 抽查**（lme par2 recall 假阴性平反同步）。
  ② **M0-12 停工裁决（卡 §5 已写）**：operation-level runner 设计上单
  worker（入口硬校验+串行循环）→ **halumem 五件套⑤=N/A（声明）**;
  operation-level 并行化=full 阶段前独立设计项。actor 停工 note=教科书级
  （1 分钟精准停工+完整证据链）。③ **halumem s2 predict 流通**（M0-11 解封
  后）：五件套①③④已验（详录 lightmem.md B11 ⑦），session report 真实数据
  首秀（s4 捕 3 条 ok/s1-s3 empty 如实）;**评测依赖序实锤：memory-type
  （免费合成指标）必须后于 halumem-extraction+update**——付费三项命令已交
  用户，跑完架构师补评 memory-type =通关线。④ **用户拍板×3 落档**：
  (a) native answer/judge **模型不 native**（第一阶段只复现官方结果本就是
  gpt-4o-mini 的实验;模型 native 留未来）;(b) hook 已装
  （`.claude/settings.json` PreToolUse/Bash：git commit 时注入 §14+显式路径
  提醒，管道实测双向通过）;(c) 派发经济学+actor"新人标准"入 playbook
  #20/#21。⑤ **隔离 id 映射裁决（用户提议序号别名）**：产物/checkpoint 层
  **不做映射**——原始 conversation_id 是 resume 键、跨 artifact join 键、
  provenance id 空间的载体,二套命名=对账事故温床;**展示层可加序号**
  （progress/summary 顺带 conversation_index），登记低优先 UX 项,不阻通关。
- 2026-07-14（**M0-11 验收合入（1139 passed）+ offline_update 覆盖面核证 +
  TOML 双轨归属核证 + playbook #20**，Fable 5）：① **M0-11 通过 ff 合入**
  （77ec269,actor 5min 交卡）：collector 容忍变体在 question scope 委托原
  严格方法（等价性测试逐字段断言）,五处机械替换,operation-level 回归测试
  真实走 update probe 路径。架构师补一行嵌套 helper 中文 docstring
  （文档标准测试不在 actor 定向范围,worktree 盲点又一例）→ **主树权威复跑
  1139 passed 全绿**;worktree/分支已清。**s1 现在解封,用户可重跑（换新
  run_id 避开残留 run 目录）**。② **offline_update 覆盖面核证（用户追问
  问出来的,结论=无缺口,姿态是官方镜像）**：locomo 官方主流程集成
  offline update（add_locomo.py:445-451,官方 0.9 论文值）,lme 官方主管线
  **不含**（run_lightmem_gpt.py=complete pipeline;offline_update.py=官方
  自称 utility script 演示件）→ 我们 locomo 跑/lme 不跑=镜像官方;
  membench/beam 无官方实验采 lme 轻姿态;已写进 lightmem.md B2。
  ③ **TOML 双轨归属核证**：configs/methods/lightmem.toml 头注释即证据
  （ws02.5 方案 B:extract 0.5/offline 0.8 = repo 默认,旧 paper 硬编码
  0.1/0.9 已弃用;retrieve_limit=60 是 LoCoMo 报告口径=混合,留档
  method-interface-inventory）;native bundle 显式声明
  hyperparam_ref="lightmem.repo_default"（config_track.py:45-46）→ 已跑的
  native run = 口径面 native + build 面 repo 默认,**声明过的缺口非疏漏**。
  ④ playbook **#20 派发经济学**落盘（用户叮嘱:必留=裁决/强验收/跨切面
  设计,其余写卡派出）。⑤ hook 机械化提案待用户拍板（commit 前 §14 三问
  提醒 hook,见会话讨论）。
- 2026-07-14（**halumem smoke 双失败取证 + M0-11/M0-12 双卡写就 + 双轨政策
  议程登记**，Fable 5，压缩后新会话）：① **s1 失败根因实锤（M0-11 卡待派，
  通关线阻塞项）**：halumem 走 operation-level runner，update probe 在
  conversation scope 内调 retrieve（operation_level.py:364-374），而 LightMem
  adapter `_retrieve_question` 无条件 `record_retrieval_result`（question-scope
  专用断言，adapter:844-851 → collector.py:437-441）→ 崩。**跨 method 通用
  陷阱**：amem:490/memoryos:790/mem0:902,981 同姿势,谁上 halumem 谁炸。裁决=
  collector 新增 scope 容忍变体 + 五处机械替换（卡 §2，runner 编排不动）。
  ② **par2 拒绝 = 固定形状 by design（用户设计正确）**；裁决=不开放自由裁剪，
  增加**第二个固定形状**（workers>1 → 恰好前 2 user，M0-12 卡写就,前置
  M0-11 合入）。③ **halumem × offline_update 姿态裁决已进 lightmem.md B2**：
  offline_update 只在 locomo 路径跑（adapter:512/:668 有 `_is_native_locomo`
  守卫）,halumem 不跑=在线姿态测量,声明语义非缺陷（逐 session 全库 update =
  O(n²) 且更失真）。④ **extraction 精准性复核（用户三问三答）**：捕获窗口=
  恰好一次 add_memory 调用（adapter:579-585）,两端 force 刷洗保证 buffer 空;
  session 超 buffer 阈值 → 该次调用内部自然多轮抽取仍在窗口内,不足 → force
  兜底,两向不多不少。⑤ **双轨政策议程登记（用户 2026-07-14 提出,待办勿忘）**：
  (a) native answer/judge **模型**是否 native（simplemem 论文用 gpt-4.1/4o）——
  架构师建议=模型统一、参数/prompt native,论文数字校准是第三种一次性用途
  （lightmem 校准先例）,**待用户拍板**; (b) simplemem native 范围=仓库有啥算
  啥（现状仅 locomo,默认 SimpleMem text 版）; (c) memoryos native=论文超参
  （作者说法）,adapter 现状待一手核对; (d) prompt 文件组织收敛
  （lightmem_native_prompts.py 在 methods/、judge prompt 在 evaluators/ 太平
  铺）→ 提议 `src/memory_benchmark/prompts/` 统一包,ws03 清理项; (e) evaluator
  可复用化（recall@k/llm-judge 去 per-benchmark 文件化）,ws03; (f) 根 README
  门面化更新,挂 LightMem 通关里程碑。⑥ **派发序**：M0-11 →合入→ 用户重跑
  s1 → M0-10（并行 manifest）→ M0-12 → par2 → halumem 五件套 → 通关。
- 2026-07-13（**M0-8 验收合入（1133 passed）+ lme ⑤ 收官 + M0-10 bug 卡**，
  Fable 5，用户额度 14%）：① **M0-8 通过**：SessionBatch ingest → 整 session
  一次 add_memory(force×2) → 只读旁听 `embedding_retriever.insert`（实例属性
  影子+finally 恢复）→ `end_session` pop 出 `SessionMemoryReport`（capture_status
  ok/empty 如实）；registry halumem 行 consume=session + session_memory_report
  旗。**精准性不变量**：每 session 末 force 刷洗 ⇒ buffer 永不跨 session ⇒
  捕获窗口=恰好本 session（不多不少），两 session 隔离有测试钉死。
  **halumem smoke 命令已交用户**（memory-type 免费架构师评；extraction/update/
  qa 付费）。② **lme par2 2/2 双 worker → lme 格⑤关闭**；f1 n=2 已评。
  ③ **发现框架 bug（M0-10 卡待派）**：workers>1 路径 manifest 不 stamp
  provenance_granularity（prediction.py:1209-1246 只在有 system 实例时写）→
  lme par2 的 recall n=0 是 manifest 缺键所致（artifacts 里 items 带合法
  source_turn_ids）；修复后需一次并行 run 复证。④ 日志已归档。
  **格局：locomo ✅ membench ✅ beam ✅ lme ✅ halumem 差 smoke 实跑 = 通关线。**
- 2026-07-13（**M0-9 验收合入（1130 passed）+ 架构师记录勘误**，Fable 5）：
  ① M0-9 结论核实为真：**M0-7b 当时已把两个消息构建器全部打上 external_id**
  （locomo 构建器 :1200,1208 + lme pair `_turn_to_role_message`:1263），v3
  turn/pair 复用这两个构建器 = 天然全覆盖；四个 recall 类 evaluator 契约
  逐家核查"确定对齐无 gap"。actor 因此**零生产代码改动**，只补测试（真实 id
  形态 "17"/"p1:s1:t1"/lme pair）+ 取证文档——纪律加分。② **勘误**：架构师
  此前断点与 integration-status 写"仅 locomo 路径附 id"是读 M0-7b diff 漏看
  后半截所致，已改正（status 页已更）；教训=验收读 diff 必须读完整,不许
  head 截断。③ **cost-probe 缓期（用户拍板）**：等 5 benchmark × 10 method
  全矩阵 smoke 跑通后再议。④ 下一步照序：用户跑 lme par2 → 派 M0-8。
- 2026-07-13（**通关冲刺：M0-8/M0-9 双卡写就，串行派发序定**，Fable 5，用户
  额度 23%）：目标=LightMem 五格通关。**派发序（两卡都动 adapter 必须串行）**：
  ① M0-9（小卡：external_id 铺开到 lme/membench/beam 注入路径 + 逐 benchmark
  recall evaluator 契约核查）→ 验收 → ② 用户跑 lme par2（`--conversations 2
  --workers 2`，一箭双雕：关 lme ⑤ + 点亮 lme provenance）→ ③ M0-8（halumem
  wrapper：session 注入+force 刷洗+只读捕获→SessionMemoryReport，方案已裁决，
  Phase C 必须钉死增量语义测试）→ 验收 → ④ halumem smoke 五件套 → 通关。
  **实验结果留档确认（用户关切）**：evaluate 是 artifact-only 设计——每 run 的
  predictions/answer_prompts(含 formatted_memory+retrieved_items+provenance)/
  private labels/answer_scores 全部落盘,未来接 BLEU 等新指标直接对旧 run 离线
  评,零 API 重跑;M0-7b 之后的 run 才带 provenance items（旧 run 无法回填）。
- 2026-07-13（**provenance 实验门通过 + beam 格五件套全齐（第三格）**，Fable 5）：
  ① **locomo-recall n=1 首次点亮**（lm-locomo-unified-prov1）：score=0.0 产物级
  核验=真实测量（source_turn_ids=[D1:2,D1:1,D1:2] vs evidence=[D1:3]，id 空间
  逐字对齐，检索未覆盖 D1:3）——**LightMem=首个 provenance 生产者**，upstream
  PR 素材+机制实证齐备；integration-status 横向事实已更新。② **beam ⑤ par2b
  2conv×2workers 2/2 通过** → beam 格五件套全齐；观察：par2b 终端/日志尾缺
  最终 JSON summary（artifacts 完整无损，疑 CLI 打印路径在 --conversations
  覆盖+workers 组合下的小 UX 问题，低优先待查）。③ 日志归档就位：三份 run 日志
  已入各自 run/terminal-logs/，staging 清空，失败残 log（datasets 事故一行）已
  核内容后删除。**格局：locomo ✅(+prov) membench ✅ beam ✅ lme 差⑤(随
  cost-probe) halumem 待 wrapper 施工。**
- 2026-07-13（**M0-7b 验收合入（首个 third_party diff 落地）+ datasets 依赖
  治本 + beam judge 双过**，Fable 5 强验收）：① **M0-7b 通过并 cherry-pick 合入**：
  external_id → `MemoryEntry.source_external_id`（可选默认 None，序列化条件写入
  仿 bam_tags）→ payload → `RetrievedItem.source_turn_ids`；平行列表与时间戳同
  循环构建保证索引一致；**all-or-nothing 语义**（任一命中缺 id 整次回落 none，
  不造部分 recall）；provenance_granularity="turn"；离线 locomo recall 合成验证
  n=1/score=1.0；**主树权威复跑 1128 passed**。当前只有 locomo 批次构建器附
  external_id（lme pair 等路径优雅回落 none，后续扩）。**真实 API 验证
  （locomo 新 predict → locomo-recall n>0）= upstream PR 前实验门,命令已交
  用户**。② **beam-rubric-judge 双 variant 0.1/0.1 落盘**（用户跑）→ beam 差
  ⑤（par2b 首跑因 datasets 被 uv sync 剪掉而失败——根因:从来不是声明依赖,
  beam.md 已知限制#7 的病根；已 `uv add datasets` 治本,命令重发）。
  ③ **tee 目录归属细化**（用户提议）：evaluate 日志直接进 run 目录,predict
  日志 staging→验收时架构师搬运（playbook #19 更新,beam 两份 judge 日志已
  归位示范）。④ 修复 lightmem.md B6 标题丢失（架构师前一日编辑事故,actor
  如实保留未越权修）。
- 2026-07-13（**BEAM smoke 双 variant 通过 + M0-7 停工裁决 + tee 日志纪律**，
  Fable 5）：① **BEAM smoke**：100k/10m predict 各 1/1、sentinel=0（用户跑）；
  免费评架构师跑完：100k f1=0.0 / 10m f1=0.4 / beam-recall 双双 n=0 条件 N/A
  正确 / par2 f1=0.4；效率+时间戳全绿——**100k 记忆时间戳 `15 March 2024` =
  M0-6 月名转换产物级端到端验证**。待办：beam-rubric-judge（付费,命令已给用户）；
  **⑤并行冒烟无效**（smoke 切片=1 conv,par2 第二个 worker 空转,架构师给命令时
  的失误）→ 补 `--conversations 2` 的 par2b。已知观察：transformers `531>512`
  截断警告（embedding 侧,产物无痕,全量前复查,tee 判例）。② **M0-7 Phase A
  正确停工**（sid 每 invocation 重置+buffer 跨调用）→ **裁决=方向 1 消息携带
  `external_id` 透传**（卡 §5 增补,边界 ≤~25 行,M0-7b 待派;上游 sid 多 batch
  不一致=issue 候选）。③ **playbook #19 tee 纪律**（用户提议:不再粘贴终端,
  命令预包 tee,架构师自读 outputs/terminal-logs/）+ #18 补 M0-6 actor 自发补
  资产judgment。**smoke 全局格局：locomo ✅ membench ✅ beam 差 judge+⑤(par2b)
  lme 差⑤ halumem 待 wrapper。**
- 2026-07-13（**M0-6 验收合入 → BEAM 解封 + M0-7 provenance 改造卡派出**，
  Fable 5 强验收）：① **M0-6 通过**：月名→ISO 通用转换（无 BEAM 分支名）、
  缺时 fail-fast 保持、真实数据扫过无单数日不造 fixture、测试直达官方
  normalizer；**主树权威复跑 1122 passed**（架构师在裸 worktree 复跑挂 73 个
  = gitignored 资产缺失假信号，判例入 playbook #18：代码卡权威测试门=合并后
  主树复跑，actor 只跑目标测试）。10m smoke 不触达全缺时 conv7/p1:s1、smoke
  切片最长 turn 694 tokens 无超长风险 → **BEAM 100k/10m 可进真实 smoke**
  （命令已交用户：两 variant 各一 run + 100k par2；beam-rubric-judge 付费=用户，
  f1/beam-recall 免费=架构师）；formal 缺时 session 政策仍待裁决。
  ② **B5+ recall@k 改造批准 + M0-7 卡派出**（LightMem source_id 透传，
  third_party 最小 diff 首例）：边界=可选字段默认 None（bam_tags 先例）、
  零行为变化可测表达、diff 留档做 upstream PR 素材；sid 语义取证前置；
  locomo-recall 契约对齐；无 API 测试链。真实 API 验证 = PR 前实验门。
  其余四家 adapter 层改造（策略②③①）仍按深耕制排 LightMem 之后。
- 2026-07-13（**membench 格五件套全齐（第二格）+ 逻辑隔离改造裁决=不做**，
  Fable 5）：用户跑 predict 两条（s1 4/4 + par2 4/4，sentinel=0，run_id 带
  `-0-10k` 后缀）；架构师跑免费五件套②③④：choice-accuracy 0.5 /
  source-accuracy 0.5 / recall n=0 条件 N/A 正确；效率三类齐（api_usage 实证、
  injected mean=108.25）；formatted_memory 4/4 带时间戳全真实记忆。
  **隔离裁决**（用户问）：membench 每 tid 一个物理隔离空间=是；LightMem 原生无
  namespace（MemoryEntry 字段表无此项、检索 filters=None）→ 逻辑隔离**不改造**
  （零评测能力收益+红线级存储改动；向量总量两种隔离相同，真实代价是 per-conv
  embedding 模型重载 ≈2s，full 若成瓶颈走 adapter 层 embedder 共享缓存，零
  third_party）。详见 lightmem.md B11⑤/B3 附带裁决。**当前格局：locomo ✅
  membench ✅ lme 差⑤ beam 卡 M0-6（未派）halumem 待 wrapper。**
- 2026-07-13（**M0-4/M0-5 双卡验收 + HaluMem "牵强"裁决落定 + M0-6 派发**，
  Fable 5 强验收）：两卡均 codex 自建 worktree（新规矩入 playbook #18：卡 §0 写
  自建命令模板，架构师验收核基点/范围/未 push 三项），ff+cherry-pick 线性合入。
  ① **M0-4 验收通过**（架构师独立复扫 BEAM 100K：90/5,732 非空 anchor、
  `April-02-2024` 格式，与 note 分毫不差；首扫 0 是架构师自己的嵌套形态错误，
  actor 对）——**MemBench 四源全绿可进真实 smoke**；**BEAM 两 variant 被
  `%B-%d-%Y` 时间格式确定性阻断**（官方 normalizer 只收 regex/ISO）+ 10m
  conv7/p1:s1 全无时间 + 33 万字符单 turn sensory buffer 无进展风险。
  ② **M0-5 验收通过**（78 锚抽验 2 处全中）→ **B2 "牵强"裁决落定（lightmem.md
  B2）：方案公平、采纳**——官方六 wrapper 全 session 级批量注入；Memobase 官方
  自己就是 force `flush(sync=True)`+时间窗 DB 增量（比我们更深）；Zep 先例=收集
  不完整照跑但声明指标不准（兜底政策官方背书）。halumem.md 同步。
  ③ **M0-6 卡已写待派**（BEAM 时间适配层施工 + smoke 切片风险核查，代码卡，
  缺时 fail-fast 保持、conv7 缺时政策 formal 前另裁）。④ **membench smoke 命令
  已交用户**（见 lightmem.md B11 进度更新后的当前格局：locomo 全齐、lme 差⑤、
  membench 待跑、beam 卡 M0-6、halumem 待 wrapper）。三指标全免费，predict
  用户跑、evaluate 架构师跑。
- 2026-07-13（**两卡待派发 + 框架差异化内核文档立档**，Fable 5）：用户重申
  "能派 actor 就派、架构师只做裁决/验收；一个 method 深耕不着急开下一个"。
  ① **M0-4 卡**（membench/beam × LightMem 离线兼容核查，纯取证零成本，产出
  `notes/m0-4-membench-beam-lightmem-compat.md`）与 **M0-5 卡**（HaluMem 官方
  harness 喂法取证，为 B2 "牵强"裁决供证，产出 `notes/m0-5-halumem-harness-feeding.md`）
  已写好待用户派发；**两卡零文件交集，可 worktree 并行**。M0-4 验收通过后架构师
  给 membench/beam 两格 smoke 命令（五件套口径，beam=100k+10m 两次 run）。
  ② **`docs/reference/framework-differentiators.md` 立档**（用户提议：论文/资金
  申请的"内核"）：D1 算法保真红线（MemoryData 绕管线判例）/ D2 评测元数据不进
  被测系统 / D3 效率不混算不重复计数（对方五处 prompt_tokens+estimate 重复计数
  实锚）/ D4 answer 口径统一 / D5 resume 工程 / D6 声明式能力矩阵；纪律=负面
  断言必须一手锚，判例组累积式。
- 2026-07-13（**MemoryData recall 改造判例取证**，Fable 5 压缩后续会话）：用户指路
  `第三方框架参考/MemoryData`（几乎全 method 支持 Recall@k）。架构师一手取证结论
  （全文 `notes/memorydata-recall-retrofit-survey.md`）：血缘 loader 侧 in-band
  header 标注 + 三条 adapter 侧回收策略（①in-band 文本解析=LightMem/A-Mem/
  SimpleMem；②原生 id 映射 sidecar=Mem0，LLM 改写不破坏；③文本反查表=MemoryOS），
  全部零 third_party 改动。**关键真相**：其 LightMem 格 `ingest_mode: direct`
  整条绕过抽取管线（verbatim chunk + offline_update）才换来 recall——真实管线下
  他们也没解决 provenance，且 vendored 源码 diff 证实上游抽取本就产出 fact 级
  source_id、构造 MemoryEntry 时丢弃（与 M0-3 一致）→ **维持原判：LightMem 走
  third_party 最小 diff（两处 ~5 行）+ 上游 PR 候选，差异化价值获判例佐证**；
  mem0/memoryos/amem/simplemem 四家初判"可无损改造"（策略②/③/①对应）。
  顺带发现待核：我们 vendored 的 LightMem 多出 bam_tags/BoundMem utils，与
  MemoryData 的副本版本分叉，PR 基准分支选择前需核 pristine 上游。已更新
  lightmem.md B5、checklist B5+ 判例库引用。
- 2026-07-13（**今日收官：locomo 格五件套全齐 + HaluMem 裁决判据 + 交接**，Fable 5，
  额度告警下收尾）：① **并行冒烟通过**（`lm-locomo-unified-par2`：2 conv ×
  workers=2，answers 2/2、judge 0.5 首个非零分）→ **locomo 格 = 首个五件套全齐
  格**；lme 格差 ⑤（低风险，随 cost-probe 顺带补）。② **HaluMem "牵强"质疑
  （用户）→ 裁决判据落档**（lightmem.md B2）：force=官方旋钮 + wrapper 只读不越
  红线，但使用节奏是否失真 → **前置取证 HaluMem 官方 harness 对无 session 概念
  method 的喂法**，同姿势=公平、做不到=N/A；裁决推迟到该格实施时。③ 交接更新 +
  handover 瘦身方向记录（见 handover 更新记录）。④ **五件套②补全**（用户点出遗漏
  ——smoke 要"全部适用指标"不只 judge）：架构师本地跑免费指标（requires_api=false
  零成本）：locomo=locomo-f1/f1/locomo-recall、lme 双轨=f1/recall/retrieval-rank；
  recall 类 n=0 = provenance=none 条件路径**正确**输出。**教训：开新认证口径的
  同一轮就该把免费部分自己跑完，不留给用户发现（§14 三问的"横向信号"没扫自己）。**
  **下一任第一件事：membench/beam
  × LightMem 离线兼容核查（不花钱）→ 给用户两格 smoke 命令；然后 B5+ 两项裁决
  （HaluMem 官方 harness 取证卡可派 actor）+ native build profile 实现。**
- 2026-07-13（**lme 双轨 smoke 收官 + 注入 token 双轨口径 + smoke 五件套新门**，Fable 5）：
  ① **lme judge 双轨 evaluate 通过** → locomo+lme 两格双轨 smoke 全通（旧口径）。
  **lme 空记忆真相**：memory_build 输出 7 token≈空抽取、injected_tokens=0 为真实零
  （1 round 任务型对话抽不出记忆点，合法；两轨 build 均 unified 配置故同空自洽）。
  ② **注入 token 双轨口径成文** `docs/reference/efficiency-injected-tokens-policy.md`
  （两轨统一记"记忆载荷 token"、native 模板开销不计入；四 run 实证 locomo 双轨
  同 68 / lme 双轨 0；native 有效性审计项进 B7）。③ **HaluMem 方案被用户纠偏后
  修正**：add_memory 不返回 entries 也无 session 概念 → 完整对齐 = session 级注入
  （messages list 天然支持）+ session 末 force 刷洗 + 包装捕获，语义代价留档
  （lightmem.md B2）。④ **checklist 三处升级**：B4 get_answer 拆分流程覆盖条款、
  B7 native 注入 token 审计项、**B11 smoke 五件套认证**（predict/全指标 evaluate/
  效率观测/formatted_memory 抽查/workers>1 并行冒烟）+ **resume 真实测试缓期至
  预算批复**（用户拍板）。⑤ **playbook §14 硬化**：commit 前强制过三问+§13 清单
  （用户第二次提醒判例 + "5h 压缩、磁盘唯一持久层"动机）。
  **下一步：locomo 并行冒烟（2conv×workers2，用户跑）→ membench/beam 离线兼容
  核查（架构师）→ B5+ 两项裁决落地方案。**
- 2026-07-13（**M0-3 + MX-1 双卡验收 + 两能力硬答案 + evaluate UX 修复**，Fable 5，
  基线 **1114 passed**）：① **M0-3 通过**（`9f6400e`）：LightMem 三接口契约逐参数/
  逐返回分支/MemoryEntry 逐字段落进 lightmem.md §0.5；**actor 教科书级停工纠错**：
  架构师 §0 原写"retrieve 落到 LightMemory.retrieve()"不准确——adapter 刻意复用其
  内部路径 `text_embedder.embed + embedding_retriever.search(return_full=True)` 保
  payload（一手核实后架构师已勘误 §0）。**两个能力硬答案**：add_memory 返回**无**
  memory entries（HaluMem memory_point 缺口实锤）；MemoryEntry **无** source_id
  字段（构造时丢弃，recall@k 缺口实锤）——两者均为"多一个字段"级 B5+ 改造候选
  （前者可 adapter 层包装 offline_update 零侵入；后者需 third_party 最小 diff =
  天然上游 PR 候选），裁决待排。② **MX-1 通过**（`6ff4d7c`→`e9e0319`）：三表全锚；
  小缺口：membench-recall 未标 metric_tier（台账）。③ **LoCoMo query 字段核证**
  （用户问）：生成期图片搜索关键词，官方 eval 不用，我们收 metadata 不进正文，
  无需特殊对待（locomo 实例文档 §7 落档）。④ **lme 双轨 predict 通**；evaluate
  因 multi-variant run_id 后缀（`…-s-cleaned`）查无而触发误导性报错 → **架构师直修**
  `_resolve_run_dir`：三布局全未命中 fail-fast + 相近 run id 提示（+2 测试）。
  ⑤ registry"减负/具体匹配"用户提议：架构师立场 = 不提前重构，LightMem 行打完后
  以能力矩阵落 integration-status，攒 2-3 个 method 真实行再定重构（见断点下方
  用户消息记录）。**下一步：用户跑 lme 两条 evaluate（用带后缀 run_id）→
  membench/beam 离线兼容核查 → B5+ 两项裁决。**
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

## 历史断点（2026-07-12；已被顶部当前断点覆盖）

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
