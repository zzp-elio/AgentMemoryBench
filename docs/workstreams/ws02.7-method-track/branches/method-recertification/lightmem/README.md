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
   验货；B11 已关闭，LightMem 恢复为 `method-frozen-v2`。完整判词见
   [frozen-v2 note](notes/lightmem-frozen-v2.md)，命令模板与修正后的 state/log 判据见
   [B11 command pack](notes/lightmem-locomo-b11-command-pack.md)。
9. 用户于 2026-07-18 明确要求离开 LightMem 前继续逐格压实 LongMemEval，故父线“下一家
   Mem0”暂缓。既有输入异形/time 大审计不重复；
   [latest-main B11 差量预检卡](cards/actor-prompt-lightmem-longmemeval-latest-main-preflight.md)，
   已由 Opus 4.8 `67715dd` + Codex R1 `346f1c4` 强验收关闭，主线 `9bf1c78` + `b2d7c9c`。
   current v6 的 canonical role/pair/hybrid/time/query/readout/metric 全链具备 registered cropped
   B11 smoke 条件；这不等于 full/effect/cost calibration 已过。六类公开异常 shape 已由
   production path + fake backend 离线实证，不再用完整异常 qid 重复烧 API。registered 默认
   smoke 为 1 conversation × 1 round × 1 question；真实成本只从完整实验单元的运行时效率
   产物外推，不从 pair/add_memory 数猜。当前只等待用户批准 B11 预算、规模与 run_id。
10. 用户要求把“为什么敢跑、异常如何处理”变成可长期复查的安全说明，而不是留在聊天。
    [LightMem 五 benchmark 格子安全说明](notes/lightmem-five-benchmark-safety-dossier.md) 采用
    一 method 一 dossier、五 benchmark 分章：LoCoMo 已写到真实 smoke passed，LongMemEval
    写到 ready-for-smoke；MemBench/BEAM/HaluMem 到站后逐格补，不用一份总绿灯掩盖未验章节。

LightMem unified 主 profile 固定 `messages_use="hybrid"`；LongMemEval Table 2 的
`user_only` 只作 reproduction profile。hybrid 卡只关闭 role/content 可见性与诚实的
pair-candidate 观测，不提前宣布 LME/BEAM turn Recall 有资格。

首轮绿测不等于一次通过：架构师抓到 mixed-invalid lineage 被截成部分真相、字符串 marker
被 truthiness 过滤、metadata/speaker role fallback、source-path prompt 猜测和 HaluMem
session→pair 调用边界漂移；R1 均已用会在首轮失败的强反例关闭。最终验收数字与主线 hash
只看父 workstream README。

当前 gap matrix：
[`notes/lightmem-b1-b11-gap-matrix.md`](notes/lightmem-b1-b11-gap-matrix.md)。
