# LightMem lifecycle 支线

## 目的

厘清论文的 online soft update、vendored 函数命名和本框架生命周期，避免按
`online_update()` / `offline_update()` 字面名误判算法。现行裁决：五格主 profile 统一
`online_soft`；LoCoMo post-build consolidation 是另名补充轨。

## 依赖顺序

权威当前动作看父级 `../../README.md`，本节只定义稳定先后关系：

1. [`actor-prompt-lightmem-online-soft-profile.md`](cards/actor-prompt-lightmem-online-soft-profile.md)
   已由 Claude Sonnet 5 完成（actor `19a0934`），架构师 full diff + 定向复跑后合入主线
   `825132f`。
2. lifecycle 前置门已关闭；实现记录见
   [`lightmem-online-soft-profile-implementation.md`](notes/lightmem-online-soft-profile-implementation.md)。
3. RetrievalEvidence M0 原 lifecycle 依赖已满足，但新发现的 MemBench 100k 时间语义门
   先行，依赖见相邻 `membench-time-semantics` 支线。
4. 真实 API run 仍需用户另行确认预算、规模和 run_id。

## 权威材料

- 现行裁决：[`lightmem-update-lifecycle-ruling.md`](notes/lightmem-update-lifecycle-ruling.md)
- 已验收实现：[`lightmem-online-soft-profile-implementation.md`](notes/lightmem-online-soft-profile-implementation.md)
- 一手审计：[`lightmem-offline-recall-validity-audit.md`](notes/lightmem-offline-recall-validity-audit.md)
- 已终止旧方案：[`actor-prompt-lightmem-lineage-repair.md`](cards/actor-prompt-lightmem-lineage-repair.md)
- 初始取证卡：[`actor-prompt-lightmem-offline-recall-audit.md`](cards/actor-prompt-lightmem-offline-recall-audit.md)

旧 plural lineage actor commit `3e2d957` 不合入。该实现保存 transformation input union，
不能证明 update 后文本仍承载所有 source fact。
