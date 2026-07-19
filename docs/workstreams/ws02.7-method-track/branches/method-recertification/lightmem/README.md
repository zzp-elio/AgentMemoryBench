# LightMem 重认证子线

LightMem 是 method-recertification 的第一家。历史 frozen 证据保留，但以当前 main
重新抽锚；本目录只收 LightMem 的 gap matrix、验收 note 和后续卡，不把共享 benchmark
问题平铺到父目录。

## 当前依赖

1. Track identity M0 已关闭；
2. `input-role-semantics` 的 gold schema M0 已经 R1 强验收并合入；
3. [LightMem role-complete profile 卡](cards/actor-prompt-lightmem-hybrid-role-profile.md)
   首轮与 Codex R1 已合入：五格 unified 主 build 固定 hybrid，canonical role 严格读取，
   pair candidate lineage 全有或全无；LoCoMo prompt 只认构造期 identity，HaluMem 保持
   session-level 单次 `add_memory()` 调用边界；
4. MemBench canonical role 已以 `ce1a9a8` + `d852fff` + `68b674b` 强验收关闭；
5. RetrievalEvidence M1 已以 `5d8fce3` + `e10110f` 强验收关闭；
6. LongMemEval 新发现曾把 B4 局部重开：官方 author harness 会裁掉异形 role turn，framework
   hybrid 会用 placeholder 保留；placeholder 虽不进 extraction 文本，仍参与 upstream
   session→turn 500ms timestamp/sequence 分配；cleaned JSON 有 `HH:MM`，但官方已裁问题标注
   的可靠精度只到 date，同日 raw clock 错序不代表 as-of cutoff，question 语义上位于 final
   conversation 之后；实现仍只传 dataset raw timestamp，不另造 corrected timestamp，数据也
   不作清洗；
7. [LongMemEval 输入异形与 timestamp 审计](notes/lightmem-longmemeval-input-time-audit.md)
   已经 Opus 4.8 主体 + 架构师 R1 强验收关闭：500ms 只作用于 repeated raw timestamp key；
   placeholder 保 lineage/speaker 但影响 method-derived slot time；raw question time 不作 cutoff。
   无需时间代码修复卡。B9/B10 已按当前 smoke identity 离线收口，效果配置迁移留到首个效果 full；
8. [LoCoMo smoke 配置离线预检](notes/lightmem-locomo-smoke-config-preflight.md) 抓到的 1,226-turn
   caption 缺口已由 Opus 4.8 主体 `ea08431` + Codex R1 `9f5ef69` 强验收关闭，主线
   `78196bc` + `65f5805`；B2/B4 已 retested。caption-bearing turn 只在 method 边界渲染共享
   wrapper，无有效 caption 时保留原文 bytes。LoCoMo 最新 build 的单 worker 与真实双 worker
   两次 run 已由用户执行，架构师完成 artifact、Recall group、Qdrant lineage、效率与隔离开箱
   验货；当时 B11 关闭并恢复为 `method-frozen-v2`。v7 随后改变所有 benchmark 共用的
   public readout 与 embedding observation，故这些 run 现在只作 v6 历史证据；LoCoMo 的
   current-v7 B4/B7/B11 已重新打开。完整历史判词见
   [frozen-v2 note](notes/lightmem-frozen-v2.md)，命令模板与修正后的 state/log 判据见
   [B11 command pack](notes/lightmem-locomo-b11-command-pack.md)。
9. 用户于 2026-07-18 明确要求离开 LightMem 前继续逐格压实 LongMemEval，故父线“下一家
   Mem0”暂缓。既有输入异形/time 大审计不重复；
   [latest-main B11 差量预检卡](cards/actor-prompt-lightmem-longmemeval-latest-main-preflight.md)，
   已由 Opus 4.8 `67715dd` + Codex R1 `346f1c4` 强验收关闭，主线 `9bf1c78` + `b2d7c9c`。
   current v6 的 canonical role/pair/hybrid/time/query/metric 全链具备 registered cropped
   B11 smoke 条件；这不等于 full/effect/cost calibration 已过。六类公开异常 shape 已由
   production path + fake backend 离线实证，不再用完整异常 qid 重复烧 API。registered 默认
   smoke 为 1 conversation × 1 round × 1 question；真实成本只从完整实验单元的运行时效率
   产物外推，不从 pair/add_memory 数猜。用户随后完成 W1 注册默认规模与 W2=2 conversations ×
   2 workers 的真实 B11，机器验货均 PASS；架构师已亲读 artifacts。pipeline、隐私、逐题 N/A、
   judge 与 worker 隔离成立，但 v6 暴露公共 readout 丢失 ISO 时分、embedding call 未观测以及
   legacy metadata 与 v1 evidence 粒度冲突，故本格降为 `B11_ARTIFACT_REPAIR_PENDING`，不能写
   `REAL_SMOKE_PASSED`。完整命令与开箱判词见
   [单/双 worker 全 evaluator 命令包](notes/lightmem-longmemeval-b11-command-pack.md)。
10. 用户要求把“为什么敢跑、异常如何处理”变成可长期复查的安全说明，而不是留在聊天。
    [LightMem 五 benchmark 格子安全说明](notes/lightmem-five-benchmark-safety-dossier.md) 采用
    一 method 一 dossier、五 benchmark 分章：LoCoMo v6 是历史 real-smoke-passed、current v7
    已重开；LongMemEval 已随 v6 实跑更新为 artifact repair pending；MemBench/BEAM/HaluMem 到站后逐格补，不用
    一份总绿灯掩盖未验章节。
11. v6 真实 B11 的两个修复面已经拆成互不踩文件的并行卡并完成强验收：
    [LightMem 产品 readout/embedding 观测卡](cards/actor-prompt-lightmem-readout-observability-repair.md)
    只改 method/registry/tests，把公共 readout 恢复为产品接口的完整时间并补真实 embedding
    observation；[retrieval summary v2 卡](../../retrieval-metrics/cards/actor-prompt-retrieval-summary-nullability.md)
    只改共享 evaluator/runner，使全 N/A 的 `mean_score/total_questions` 不再伪装成 0 分/0 题。
    summary 主体 `8a81723` 合入主线 `68bb7f9`；LightMem 主体 `8f6f883` 被架构师以 zero-hit
    双源与 observer 透明性强反例驳回，Codex R1 `1a07938` 关闭后合入主线
    `d11d749` + `2f21291`。两卡合流定向 325、主树全量 1557、compileall exit 0；真实 v6
    W1/W2 零 API 重评已正确写 total=1/2、mean=null。该批当时把真实 v7 B11 artifact 复验留作
    最近门；现已由下条四-run 验收关闭。之后仍须按本 dossier 逐格压实 MemBench、BEAM、
    HaluMem，五格全部关闭后才能宣称当前 adapter frozen。
12. 用户于 2026-07-19 批准 LongMemEval/LoCoMo current-v7 的真实 API 预算、规模与 run id。
    [v7 受影响格 B11 命令包](notes/lightmem-v7-readout-observability-b11-command-pack.md) 固定四个
    串行 predict：LME W1/W2 与 LoCoMo W1/W2；每格随后执行全部当前适用 evaluator 和零 API
    机器验货。命令包只重验完整 ISO product readout、逐题 metadata 单事实源、build/retrieval
    embedding observation、retrieval summary v2、caption lineage 与 worker state。四组 run 已
    全部执行，架构师已亲读 artifact、terminal log 与 Qdrant state；原机器验货脚本把“每个
    conversation 均须 build embedding”写成过强断言，LongMemEval W1 因 0 LTM 合法误报。
    R1 改为 actual-call-aware 判据后全验货通过：LME ISO hit=2、LoCoMo ISO hit=16、build
    calls 分别 2/28。两格现为 current-v7 `REAL_SMOKE_PASSED`，但不代表 full/效果/成本/
    resume，也不使整个 method frozen。
13. 同期只开放一条不改代码、零 API 的下一格准备线：
    [LightMem × MemBench 分层异常覆盖预检卡](cards/actor-prompt-lightmem-membench-anomaly-coverage-preflight.md)。
    它一次性核对两个 variant/四类 source 的 source-lock census、production-path 强反例、
    evaluator-private 异常与真实 sentinel 必要性；不会与四个 v7 run 写同一文件或 state。用户
    已派发外部 actor，当前执行中；回卡后须与 OWNER 新增的
    `docs/survey/异常情况/membench.md` 逐锚交叉验收，不能把任一方摘要直接当事实。回卡强验收前
    不得据历史 smoke 宣称 MemBench 格通过。

LightMem unified 主 profile 固定 `messages_use="hybrid"`；LongMemEval Table 2 的
`user_only` 只作 reproduction profile。hybrid 卡只关闭 role/content 可见性与诚实的
pair-candidate 观测，不提前宣布 LME/BEAM turn Recall 有资格。

首轮绿测不等于一次通过：架构师抓到 mixed-invalid lineage 被截成部分真相、字符串 marker
被 truthiness 过滤、metadata/speaker role fallback、source-path prompt 猜测和 HaluMem
session→pair 调用边界漂移；R1 均已用会在首轮失败的强反例关闭。最终验收数字与主线 hash
只看父 workstream README。

当前 gap matrix：
[`notes/lightmem-b1-b11-gap-matrix.md`](notes/lightmem-b1-b11-gap-matrix.md)。
