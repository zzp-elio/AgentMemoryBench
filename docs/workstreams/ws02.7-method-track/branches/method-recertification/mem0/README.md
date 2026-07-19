# Mem0 current-main 重认证子线

Mem0 是 method-recertification 的第二家。LightMem 已经把五个 source-locked benchmark 的
schema、异常、canonical id、private gold group、prompt 与 metric 资格压实；本子线不再重做
benchmark census，只审 Mem0 产品接口与五格 method 差量。

## 本轮并行拓扑

第一波只做六份互不写同一文件的离线审计：

| 卡 | 唯一问题 | 唯一交付 note |
|---|---|---|
| [Mem0 产品 messages/namespace/time 契约](cards/actor-prompt-mem0-core-message-contract-audit.md) | `Memory.add()` 是否要求 role 交替；`user_id/agent_id/run_id`、双 speaker namespace、时间与 batch 边界的真实语义 | `notes/mem0-core-message-contract-audit.md` |
| [Mem0 × LoCoMo 差量预检](cards/actor-prompt-mem0-locomo-delta-preflight.md) | named speakers、两代官方 harness、逐 turn add、caption 与 session time | `notes/mem0-locomo-delta-preflight.md` |
| [Mem0 × LongMemEval 差量预检](cards/actor-prompt-mem0-longmemeval-delta-preflight.md) | 异形 role、position-pair、session time、逐题隔离与 N/A/valid 边界 | `notes/mem0-longmemeval-delta-preflight.md` |
| [Mem0 × MemBench 差量预检](cards/actor-prompt-mem0-membench-delta-preflight.md) | FirstAgent 双 child、ThirdAgent singleton、原文 place/time、100k 缺时 | `notes/mem0-membench-delta-preflight.md` |
| [Mem0 × BEAM 差量预检](cards/actor-prompt-mem0-beam-delta-preflight.md) | pair 投递、10M dangling/错位/缺时、positional id 与 rubric | `notes/mem0-beam-delta-preflight.md` |
| [Mem0 × HaluMem 差量预检](cards/actor-prompt-mem0-halumem-delta-preflight.md) | 整 session add/result report、交错测评、当前 session extraction 与三类 metric | `notes/mem0-halumem-delta-preflight.md` |

六张卡可以从同一 main 基线在六个隔离 worktree 并行执行，因为都只新增各自 note。benchmark
卡只记录 framework 实际交给 `Memory.add()` 的调用序列，不替核心卡裁 Mem0 内部是否接受该
shape；核心卡也不代替五格检查 canonical 映射。架构师必须等六份证据汇合后作一次联合裁决。

## 合流门

1. 六份 note 由架构师 full diff、抽锚与文档门强验收；
2. 形成一份跨五格 gap matrix，明确哪些是现成能力、N/A、文档漂移或真实代码缺口；
3. 如需生产修改，只发**一张**共享实现卡统一改 `mem0_adapter.py` / registry / tests，禁止五个
   actor 分别改共享 adapter；
4. 定向与全量门关闭后，再按五格生成最小真实 smoke 命令；未经用户逐格批准预算、规模和
   run id，不调用 API。

稳定 benchmark 事实入口：

- `docs/survey/异常情况/` 与 `docs/survey/{datasets,workflows}/`；
- `docs/workstreams/ws02.6-first-smoke-hardening/` 的 source locks / frozen notes；
- LightMem 五格安全说明只作“benchmark 已知事实”索引，不把 LightMem 的 method 行为套给 Mem0。

权威实时状态、commit/test 快照仍只写父级
`docs/workstreams/ws02.7-method-track/README.md`。
