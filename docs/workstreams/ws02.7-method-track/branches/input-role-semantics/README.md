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
2. evidence-unit 通用契约高判断审计卡：
   [`cards/actor-prompt-evidence-unit-contract-audit.md`](cards/actor-prompt-evidence-unit-contract-audit.md)
3. actor 回卡后，架构师裁定最小协议；再按依赖顺序起草：
   - MemBench FirstAgent canonical role + step-qrel 施工卡；
   - LightMem role-complete build profile 施工卡；
   - RetrievalEvidence M1 evaluator 消费卡。

## 当前状态

**只有 evidence-unit contract docs-only 审计可以派发。**生产代码尚未授权施工；
MemBench benchmark adapter 定点解冻，LightMem B2/B4/B5/B9/B10/B11 暂停。零真实 API。
权威实时断点仍只写父 workstream `../../README.md`。
