# MemBench 时间语义支线

## 目的

区分 MemBench 的三种不同事实：message 文本内嵌时间、缺失的 message 时间、只属于
question 的 `QA.time`。本支线修复把首个 message 时间扩散成伪 session 时间的旧行为，
并为要求逐 message timestamp 的 method 建立诚实的 variant compatibility 边界。

## 现行裁决

1. `QA.time` 只属于 retrieval query / answer prompt，绝不回填 Turn 或 Session。
2. message 文本里真实存在的时间可以无损结构化成该 Turn 的 `turn_time`；所有 method
   收到的 content 仍完整保留原 place/time。抽取是 additive typed metadata，不是清洗。
3. message 没有内嵌时间时保持 `turn_time=None`；MemBench 没有原生 session 时间，故
   `session_time` 必须为 `None`，不得用兄弟 turn 的时间兜底。
4. 100k 无时间部分是官方主动插入的 noise，gold `target_step_id` 只重定位原始 evidence；
   缺时间是公开输入形状的一部分，不得“修复”噪声。
5. LightMem upstream 当前要求每条 message 有非空 `time_stamp`，但全链路审计确认
   online-soft 的向量相关性主路径可做 preserve-none 兼容扩展；consolidated/summary 的
   时间排序路径仍必须 require。Phase B 强验收前 `LightMem × MemBench 100k` 不得真实运行。
6. A-Mem 可接收 `time=None`，但 upstream 会生成 ingestion wall clock；这是 method-native
   创建时间，不是 source time，不能回流成 benchmark provenance。Phase B 必须区分这些
   不同的 optional 语义。

## 依赖顺序

权威当前动作看父级 `../../README.md`，本节只定义稳定先后关系：

1. Phase A 已由 Opus 4.8 完成，架构师 full diff + `31 passed in 3.68s` + 主树
   `1193 passed` 强验收，合入 `2e6b4d7`；MemBench benchmark frozen-v1 恢复。
2. 下一批执行 [`actor-prompt-lightmem-missing-time-online-soft.md`](cards/actor-prompt-lightmem-missing-time-online-soft.md)：
   只给 online-soft 增加 preserve-none 输入兼容，并把 consolidated profile 锁在 require。
3. Phase B 通过后再决定是否需要更通用的 input-requirement 协议；不预建 method × variant
   人工白名单，也不把 A-Mem method-generated wall clock 冒充 source time。
4. RetrievalEvidence M0 在 Phase B 强验收前继续暂停，避免同时修改 LightMem manifest、
   resume 与 provenance 面。

## 权威材料

- 数据与官方流程裁决：[`membench-100k-time-ruling.md`](notes/membench-100k-time-ruling.md)
- Phase A 实现记录：[`membench-time-semantics-phase-a-implementation.md`](notes/membench-time-semantics-phase-a-implementation.md)
- LightMem None 裁决：[`lightmem-missing-time-compatibility-ruling.md`](notes/lightmem-missing-time-compatibility-ruling.md)
- **待派 Phase B 卡**：[`actor-prompt-lightmem-missing-time-online-soft.md`](cards/actor-prompt-lightmem-missing-time-online-soft.md)
