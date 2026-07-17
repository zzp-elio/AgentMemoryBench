# 输入 role 与 evidence unit 语义支线

## 范围

本支线处理 2026-07-16 在 LightMem 重认证前置审计中暴露的两个共享契约问题：

1. benchmark 原始容器不一定等于 canonical `Turn`。MemBench FirstAgent 的一个
   `message_list` step 同时含 user/agent 两条发言，不能继续拼成一个伪 user turn；
2. benchmark 的 gold evidence unit 不一定等于 canonical turn。MemBench
   `target_step_id` 指向 pair 级 step，拆成两条发言后不能机械把 Recall 分母翻倍。

LightMem 的 `messages_use` 是最先暴露问题的 method 配置，但本支线不写
method×benchmark 专用 runner，也不把 benchmark canonical 修复藏进 LightMem adapter。

## 文档索引与依赖顺序

1. 架构师一手审计与现行裁决：
   [`notes/lightmem-messages-membench-beam-role-audit.md`](notes/lightmem-messages-membench-beam-role-audit.md)
2. evidence-unit 通用契约高判断审计卡与架构师纠错：
   [`cards/actor-prompt-evidence-unit-contract-audit.md`](cards/actor-prompt-evidence-unit-contract-audit.md)
   → [`notes/evidence-unit-contract-audit.md`](notes/evidence-unit-contract-audit.md)
3. 当前依赖顺序：
   - [gold evidence 私有 schema/manifest M0](cards/actor-prompt-gold-evidence-contract-m0.md)
     已完成并经架构师 R1 强验收；
   - [MemBench FirstAgent canonical pair split](cards/actor-prompt-membench-canonical-split.md)
     已由架构师裁定并写成自包含卡；当前只派这一张，保持一个官方 pair-step 对应一个
     multi-child gold group；
   - [LightMem role-complete build profile](../method-recertification/lightmem/cards/actor-prompt-lightmem-hybrid-role-profile.md)
     已与 M0 合流并完成 hybrid/pair-lineage R1；
   - MemBench split 验收后再做 RetrievalEvidence M1 的逐题资格消费。

## 当前状态

Fable docs-only 审计已由架构师强验收并纠正 BEAM 全量统计：1M 当前为 41 个含歧义题、
198 个歧义 gold 原子；LME canonical 分母裁为 419。Gold Evidence Group M0 首轮经
Opus 4.8 → DeepSeek V4 Pro 接力完成，架构师强验收发现 singleton 冒充 multi-child、
unmatched 被移出 NDCG ideal 分母、identity gate 被 N/A 短路等 false-green；Codex R1
关闭后已合入主线。MemBench canonical split 已解锁并写卡，等待用户交给外部 actor 施工；
零真实 API。该卡验收前不并行派 RetrievalEvidence M1，避免同时追同一 evaluator/fixture。
权威实时断点仍只写父 workstream `../../README.md`。
