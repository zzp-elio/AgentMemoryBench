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
5. LightMem 官方输入要求每条 message 有非空 `time_stamp`，传 `None` 也会 raise。100k
   有大量无时间 noise，故在
   通用 fail-fast input-requirement 门落地前，`LightMem × MemBench 100k` 不得真实运行；
   不用 question time、首条时间、墙钟或人造递增时间填格。
6. A-Mem 可接收 `time=None`，但 upstream 会生成 ingestion wall clock；这是 method-native
   创建时间，不是 source time，不能回流成 benchmark provenance。Phase B 必须区分这些
   不同的 optional 语义。

## 依赖顺序

权威当前动作看父级 `../../README.md`，本节只定义稳定先后关系：

1. 先执行 [`actor-prompt-membench-time-semantics-phase-a.md`](cards/actor-prompt-membench-time-semantics-phase-a.md)，
   只修 benchmark 公共数据语义与回归测试。
2. actor 回卡后由架构师读全 diff、复跑并合入，恢复 MemBench benchmark frozen 门。
3. 再由架构师设计 Phase B：method-neutral 的输入需求预检，使 timestamp-required method
   在任何 API/写入前按实际 dataset shape fail-fast，并区分 unknown-preserving 与
   method-generated ingestion time；不建 method × variant 人工白名单。
4. RetrievalEvidence M0 在 Phase A 强验收、Phase B 边界裁定前继续暂停，避免两张卡
   同时改 registry/LightMem 契约。

## 权威材料

- 数据与官方流程裁决：[`membench-100k-time-ruling.md`](notes/membench-100k-time-ruling.md)
- Phase A 施工卡：[`actor-prompt-membench-time-semantics-phase-a.md`](cards/actor-prompt-membench-time-semantics-phase-a.md)
