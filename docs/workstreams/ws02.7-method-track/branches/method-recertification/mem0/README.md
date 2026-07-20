# Mem0 current-main 重认证子线

Mem0 是 method-recertification 的第二家。LightMem 已经把五个 source-locked benchmark 的
schema、异常、canonical id、private gold group、prompt 与 metric 资格压实；本子线不再重做
benchmark census，只审 Mem0 产品接口与五格 method 差量。

## 第一波审计拓扑（已完成）

第一波只做六份互不写同一文件的离线审计：

| 卡 | 唯一问题 | 唯一交付 note |
|---|---|---|
| [Mem0 产品 messages/namespace/time 契约](cards/actor-prompt-mem0-core-message-contract-audit.md) | `Memory.add()` 是否要求 role 交替；`user_id/agent_id/run_id`、双 speaker namespace、时间与 batch 边界的真实语义 | `notes/mem0-core-message-contract-audit.md` |
| [Mem0 × LoCoMo 差量预检](cards/actor-prompt-mem0-locomo-delta-preflight.md) | named speakers、两代官方 harness、逐 turn add、caption 与 session time | `notes/mem0-locomo-delta-preflight.md` |
| [Mem0 × LongMemEval 差量预检](cards/actor-prompt-mem0-longmemeval-delta-preflight.md) | 异形 role、position-pair、session time、逐题隔离与 N/A/valid 边界 | `notes/mem0-longmemeval-delta-preflight.md` |
| [Mem0 × MemBench 差量预检](cards/actor-prompt-mem0-membench-delta-preflight.md) | FirstAgent 双 child、ThirdAgent singleton、原文 place/time、100k 缺时 | `notes/mem0-membench-delta-preflight.md` |
| [Mem0 × BEAM 差量预检](cards/actor-prompt-mem0-beam-delta-preflight.md) | pair 投递、10M dangling/错位/缺时、positional id 与 rubric | `notes/mem0-beam-delta-preflight.md` |
| [Mem0 × HaluMem 差量预检](cards/actor-prompt-mem0-halumem-delta-preflight.md) | 整 session add/result report、交错测评、当前 session extraction 与三类 metric | `notes/mem0-halumem-delta-preflight.md` |

六张卡已从 main `6643e56` 的隔离 worktree 回卡，架构师线性合入为
`40e82ac`、`74379e6`、`7d0aeb6`、`a3a84bc`、`e5139a0`、`73b4791`。benchmark 卡只记录
framework 实际交给 `Memory.add()` 的调用序列，不替核心卡裁 Mem0 内部是否接受该 shape；
核心卡也不代替五格检查 canonical 映射。六线联合裁决见
[`mem0-joint-ruling.md`](notes/mem0-joint-ruling.md)。

## 第二波双卡施工拓扑（已完成）

联合裁决确认 **Mem0 role-aware 但不要求 pair**，所以任何 benchmark 都不因本轮新增
placeholder；真实缺口拆成两张不写同一文件的卡，可并行施工：

| 卡 | 解决什么 | 强验收结果 |
|---|---|---|
| [Mem0 五格输入/readout R1](cards/actor-prompt-mem0-input-readout-r1.md) | LoCoMo 显式 speaker_a/b、caption wrapper、role-native 正文去重复前缀、MemBench generic readout、Mem0-native HaluMem update top-k、adapter v3 | 主体 `7fb3cd9` + 架构师真实 v2 resume 门 `e1b2c9c`；独立定向 76 passed |
| [HaluMem operation runner clean retry R1](cards/actor-prompt-halumem-operation-runner-clean-retry-r1.md) | 失败状态、clean retry 与 CLI 接线；不做错误的全 method top-10 截断 | 主体 `1bdfa98` + 架构师精确 stage/order trace `5d1f91e`；独立定向 73 passed |

这次从“一张共享实现卡”改为两张，不是把工作拆碎：第一张只改 Mem0 method build/readout/
原生检索请求 identity，第二张只改 method-neutral operation state machine，写集、失败域和验收门
均独立。强塞一张卡会
让 adapter 字节语义与 resume 状态机互相遮蔽，也无法安全并行。

## 合流门

1. ✅ 六份 note 已由架构师合流并形成联合 gap matrix；
2. ✅ 两张 R1 卡已 full diff、补齐两处 R1 强反例并独立复跑；
3. ✅ 四个 commit 线性合流；扩大定向 244 passed，主树全量 1637 passed + 29 subtests，
   compileall exit 0；adapter v3 旧 store 经真实 preflight 禁 resume；
4. **当前动作**：按五格生成最小真实 smoke 命令；未经用户逐格批准预算、规模和
   run id，不调用 API。

稳定 benchmark 事实入口：

- `docs/survey/异常情况/` 与 `docs/survey/{datasets,workflows}/`；
- `docs/workstreams/ws02.6-first-smoke-hardening/` 的 source locks / frozen notes；
- LightMem 五格安全说明只作“benchmark 已知事实”索引，不把 LightMem 的 method 行为套给 Mem0。

权威实时状态、commit/test 快照仍只写父级
`docs/workstreams/ws02.7-method-track/README.md`。
