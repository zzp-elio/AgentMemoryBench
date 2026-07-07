---
id: ws02.2
parent: ws02
status: plan-ready（spec approved，待 actor 施工）
created: 2026-07-08
---
# ws02.2 HaluMem Adapter（Phase 1 第二个新 benchmark，operation-level）

## 目标

按协议 v3 接入 HaluMem full operation-level（抽取 + 更新 + QA 三段），为 5×10
矩阵打开第四列，点亮项目北极星"能力维度"轴的最高分辨率。完成判据见
[spec.md](spec.md) §9。

## 当前断点

- 2026-07-08（架构师 Opus 4.8）：**spec approved + plan ready，待 actor 施工**。
  用户评审定案三点：① D1 批准（遵循 HaluMem 官方 gold-as-query）；② 定调
  **弃用 `TaskFamily/MethodCapability/validate_compatibility` enum 门控，改
  "接口即契约"**（S6 重写：谁覆写 `end_session` 返回增量报告谁就有 extraction
  能力；架构师加 preflight 内省一条工程约束以保预算安全）；③ 用户"注意三种
  触发时机"点出 spec 两处错误已修（`is_generated_qa_session` 跳过全部三段、
  extraction 增量 vs update/QA 累积）。D4 取证：Mem0 `add()` 返回增量→可提供
  extraction 报告；SimpleMem 窗口抽取粒度≠session→N/A。plan 见
  [plan.md](plan.md)（T1-T7，最大 plan，允许跨 actor 会话接力）。
- 2026-07-08（架构师 Opus 4.8）：spec draft 产出，关键结论协议 v3 零改动即可
  承载 operation-level（推翻调研卡 2026-06-29"需扩协议"旧判断）。

## 任务清单

- [x] 用户定范围：Full operation-level（2026-07-08）
- [x] 架构师起草 spec（2026-07-08）
- [x] 用户批准 spec（2026-07-08，D1 接受官方做法 + S6 改接口即契约）
- [x] 架构师写实施 plan（[plan.md](plan.md)，T1-T7）
- [ ] actor 施工 + fake 全链路
- [ ] 架构师验收
- [ ] 极小真实 smoke（待用户确认预算）

## 决策点（详见 spec.md §7，均已定案）

- **D1（用户批准）**：update 探针 gold-as-query 遵循 HaluMem 官方；兜底 =
  plan T3"update 探针无写副作用"契约测试。
- **S6（用户定调）**：弃用 enum 门控，接口即契约 + preflight 内省。旧
  `capabilities.py` enum + 冗余 `session_memory_report` bool 标为 ws03 减重候选。
- D2-D5 架构师裁定：judge=gpt-4o-mini（标注非严格复现）、smoke=medium、
  extraction 能力逐 method 按机制卡（T5：Mem0 可 / SimpleMem N/A / 余核实）、
  persona_info 不注入。
