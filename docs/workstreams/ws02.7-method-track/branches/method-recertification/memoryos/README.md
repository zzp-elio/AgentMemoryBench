# MemoryOS current-main 五格重认证子线

MemoryOS 是 method-recertification 的第三家。LightMem 与 Mem0 已经把五个 source-locked
benchmark 的 schema、异常、canonical id、private gold group、prompt 与 evaluator 口径压实；
本子线只审 `memoryos-pypi` 产品接口的五格差量，不重新制造五份 benchmark census。

## 本轮锁死的架构裁决

1. **运行源**：Phase 1 主轨继续用
   `third_party/methods/MemoryOS-main/memoryos-pypi/` 的产品 `Memoryos`；`eval/` 只是一手
   LoCoMo 复现证据，ChromaDB fork 是另一个 algorithm variant，均不得暗换主轨。
2. **page 与 placeholder**：产品 `add_memory(user_input, agent_response, timestamp)` 的原生
   单元是一页 QA pair。缺失一侧时只能写空字符串 placeholder；不得编造“I get it”等非空
   回复，也不得从下一 session 借一条真实 turn 补配。每个真实 turn 恰好出现一次。
3. **LoCoMo 角色扮演映射**：复用官方 `speaker_a → user_input`、
   `speaker_b → agent_response`；ingest 正文不额外拼 speaker name，真实姓名由持久
   `speaker_map` 在 readout/native builder 恢复。只复用角色映射，不继承官方脚本把
   `processed[-1]` 跨 session 回填的潜在边界错误。
4. **图片**：有效 caption 统一用共享
   `[Sharing image that shows: {caption}]`；原文与多 caption 稳定保留，locator/query/private
   evidence 不进入 method。
5. **时间**：有 source timestamp 时必须进入 MemoryOS 的 typed `timestamp` 参数；正文已有
   place/time 时仍无损保留正文。缺失时间不得拿 question time、相邻 turn 或 wall clock 冒充
   source time。由于一页只有一个 timestamp，各卡必须实证本 benchmark 的一页两侧是否同值，
   不能靠猜测代裁。
6. **metric 资格逐格判**：`valid / N/A / pending` 都是合法结果。current shared-lifecycle
   实现把 exact source ids 随原生 page 从 STM 迁到 MTM；Recall 的可计分 view 是全部
   `always_on` STM + 前 k 个 `ranked` MTM，gold group 对 page 内一至两个 child turn 作
   any-of。profile/user knowledge/assistant knowledge 虽进入完整 product readout，但一律标成
   `non_evidence`，不伪造 turn lineage；stable ranking/NDCG 仍 pending。禁止为了填表格而
   过度盖章。
7. **HaluMem 不扭曲 method**：只有产品运行时能诚实给出“刚结束的当前 session 的 method
   memory”才启用 extraction；直接回显 raw input、返回累计全库或把跨 session summary 假装成
   当前 session 都不合格。extraction N/A 不妨碍分别审 update 与 QA。

## 架构师在 current main 已定位的四个必查反例

以下是任务卡的起点，不是让 actor 重复相信旧 note：

- session converter 的 `pages` 当前跨 session 共用，后一 session 的 orphan assistant 可能回填
  前一 session 的 dangling user；五格探针必须证明是否真实可达；
- MemBench 走 session ingest，而 converter 当前只取 `session_time`，可能忽略 canonical
  `turn_time`；空字符串又会被产品 `add_memory()` 换成 ingestion wall clock；
- `_build_retrieval_evidence()` 当前对五个 registered benchmark 一律写 `valid/turn`，但
  `_retrieved_items()` 只导出 `retrieved_pages`，与 formatted memory 的全层 readout 不等价；
- `MemoryOS` 当前未覆写 `end_session()`，operation runner 会把 HaluMem extraction 判为 N/A。

若 current source 已变化，actor 以一手源码为准并在 note 明确写出漂移；不得为了符合本段而
伪造结果。

## Shared lifecycle 实现与验收锚

- 架构师裁决与施工历史：
  [`notes/memoryos-shared-r1-implementation.md`](notes/memoryos-shared-r1-implementation.md)。
- 用户已批准的五格真实 smoke、8 个固定 run、全部 evaluator 与统一机器验货：
  [`notes/memoryos-v2-five-grid-b11-command-pack.md`](notes/memoryos-v2-five-grid-b11-command-pack.md)。
- B1-B11 最终对表与声明缺口：
  [`notes/memoryos-frozen-v1.md`](notes/memoryos-frozen-v1.md)。
- main 线性提交：`6602aab` → `4300591` → `c5e7541` → `1207083` → `ef3b4f2` →
  `dcc5fd6`。保留首轮被强验收驳回及 R1-R5 修正历史，不以最终绿测抹掉错误路径。
- 当前已锁：session 边界不跨配、单侧页跨 capacity 不丢、双空拒绝、timestamp
  omitted/explicit-None 分流、STM/MTM occurrence identity、完整 HaluMem update product view、
  extraction N/A → memory_type N/A。
- 验收门：Terra 核心四文件 `158 passed`；架构师独立共享注册/metric 回归 `165 passed`、
  R5 定向 `80 passed`；main 无 API 全量
  `1666 passed, 3 deselected, 2 warnings, 29 subtests passed in 145.12s`；compileall exit 0。
- 用户已完成 8 个真实 run；HaluMem judge preview=`extraction=0 update=7 qa=1`。首轮机器门
  错把 BEAM abstention 的 `null/n_a` 当失败，R1 按 benchmark-policy 改为明确验 N/A 后复用
  既有 artifacts 8/8 PASS。current product build 已冻结为 `method-frozen-v1`；未扩大 smoke、
  未转 full、未为制造数值 Recall 重烧 API。

## 第一波五卡拓扑（历史取证入口）

五张卡只新增各自 note，不同时修改 adapter/tests/config，因此可在独立 worktree 并行：

| 卡 | 核心问题 | 唯一交付 |
|---|---|---|
| [MemoryOS × LoCoMo](cards/actor-prompt-memoryos-locomo-current-main-preflight.md) | 官方角色映射、session 边界、caption、speaker readout 与 Recall 资格 | `notes/memoryos-locomo-current-main-preflight.md` |
| [MemoryOS × LongMemEval](cards/actor-prompt-memoryos-longmemeval-current-main-preflight.md) | role 异形、pair/placeholder、source time、全层 readout 与 session/turn qrel | `notes/memoryos-longmemeval-current-main-preflight.md` |
| [MemoryOS × MemBench](cards/actor-prompt-memoryos-membench-current-main-preflight.md) | First/ThirdAgent、typed turn time、100k 缺时、place/time 无损与 Recall | `notes/memoryos-membench-current-main-preflight.md` |
| [MemoryOS × BEAM](cards/actor-prompt-memoryos-beam-current-main-preflight.md) | 标准 pair、10M orphan/错位/缺时、id、rubric 与 Recall | `notes/memoryos-beam-current-main-preflight.md` |
| [MemoryOS × HaluMem](cards/actor-prompt-memoryos-halumem-current-main-preflight.md) | session-local extraction、交错 update/QA、四类 evaluator 与运行时副作用 | `notes/memoryos-halumem-current-main-preflight.md` |

每张卡的唯一判词只能是 `READY_FOR_B11`、`READY_FOR_B11_WITH_NA(...)` 或
`NEEDS_CODE(<最小缺口>)`。第一波不是付费 smoke 授权；五份回卡经架构师 full diff 与抽锚后，
共性缺口最多收敛成一张联合实现卡，避免五个 actor 争改同一 adapter。

该拓扑现在只保留为 benchmark 差量取证导航；共享缺口已由上节实现关闭。实时状态与下一动作
仍只看父 workstream README，不要再把五张卡误读成待并行施工队列。

## 合流门

1. 五份 note 当前主线抽锚、结论互不矛盾；
2. 架构师形成一份五格 gap matrix，逐格裁 placeholder/time/readout/metric；
3. 如需代码，只发一张共享 adapter 修复卡；纯 benchmark 测试可按不重叠文件并行补；
4. 定向回归、全量门、五格最小真实 smoke、artifact/state/worker 开箱；
5. B1-B11 对表后才写 frozen note。N/A metric 不阻塞 method 冻结，虚假 valid 会阻塞。

上述五门现均已关闭；本子线进入只读冻结状态。后续仅在 frozen note 的失效触发器命中时局部
解冻，主线转入 A-Mem。

权威实时 commit/test/派卡状态仍只写父级
`docs/workstreams/ws02.7-method-track/README.md`；本页只维护本子线结构与稳定依赖。
