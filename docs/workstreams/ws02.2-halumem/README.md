---
id: ws02.2
parent: ws02
status: spec-draft（待用户批准 D1）
created: 2026-07-08
---
# ws02.2 HaluMem Adapter（Phase 1 第二个新 benchmark，operation-level）

## 目标

按协议 v3 接入 HaluMem full operation-level（抽取 + 更新 + QA 三段），为 5×10
矩阵打开第四列，点亮项目北极星"能力维度"轴的最高分辨率。完成判据见
[spec.md](spec.md) §9。

## 当前断点

- 2026-07-08（架构师 Opus 4.8）：**spec draft 已产出**（[spec.md](spec.md)）。
  关键结论：协议 v3 **零实体改动**即可承载 operation-level（首任架构师已埋好
  `extraction_probe`/`memory_update_probe`/`SessionMemoryReport`/
  `session_memory_report` 扩展位），推翻调研卡 2026-06-29"需扩协议"的旧判断。
  真实工作量 = adapter + operation-level runner（唯一新 runner 能力，按
  task-family 分派非专用 runner）+ 3 个 judge evaluator + 能力门控。
  **待用户批准决策点 D1**（update 探针 gold-as-query 隐私政策）后转 approved
  并写 plan。

## 任务清单

- [x] 用户定范围：Full operation-level（2026-07-08）
- [x] 架构师起草 spec（2026-07-08）
- [ ] 用户批准 spec（待 D1 拍板）
- [ ] 架构师写实施 plan
- [ ] actor 施工 + fake 全链路
- [ ] 架构师验收
- [ ] 极小真实 smoke（待用户确认预算）

## 决策点（详见 spec.md §7）

- **D1（待用户）**：update 探针用 gold memory_content 作 query，method 会看到
  gold 派生文本。架构师推荐接受此受控例外（官方即如此、通道受限可审计、不污染
  QA）；风险是需在 plan 加"update 探针不得触发写入副作用"契约校验。
- D2-D5 架构师已裁定（judge=gpt-4o-mini 标注非严格复现、smoke=medium、
  extraction 门控逐 method 按机制卡在 plan 裁定、persona_info 不注入）。
