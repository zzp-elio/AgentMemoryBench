---
id: ws02.3
parent: ws02
status: spec-draft（待用户批准，尤其 D6）
created: 2026-07-08
---
# ws02.3 BEAM Adapter（Phase 1 第三个新 benchmark，conversation-QA + rubric judge）

## 目标

接入 BEAM（超长 conversation + 10 类记忆能力 probing questions），为 5×10 矩阵
打开第五列（最后一个 benchmark）。完成判据见 [spec.md](spec.md) §8。

## 当前断点

- 2026-07-08（架构师 Opus 4.8）：**spec draft 已产出**（[spec.md](spec.md)），
  全部结论**第一手核对**（官方仓库 + 真实 arrow 数据 + 三份 survey 卡）。关键
  结论：① BEAM 是 **conversation-QA 家族**，复用现有 runner，无需 operation-level
  （比 HaluMem 简单）；② 工作量在 evaluator——rubric-nugget LLM judge + 10
  ability 聚合 + **必修官方 int 截断 0.5 的 bug**（compute_metrics.py 9 处 int()
  vs event_ordering 1 处 float()，judge prompt 明写 0/0.5/1）；③ 第一手 gotcha：
  `probing_questions` 是 Python-repr 字符串须 `ast.literal_eval`、`chat` 是
  list[session]、content 带 `->->` 尾标记。**待用户批准**（尤其 D6：
  event_ordering 的 kendall-tau 排序分是否 v1 纳入，架构师推荐先做统一 rubric
  judge、排序分作增强项）后写 plan。

## 任务清单

- [x] 架构师起草 spec（2026-07-08，第一手核对）
- [ ] 用户批准 spec（尤其 D6）
- [ ] 架构师写实施 plan
- [ ] actor 施工 + fake 全链路
- [ ] 架构师验收
- [ ] 极小真实 smoke（待用户确认预算）

## 决策点（详见 spec.md §5）

- D1 int→float 修正（架构师定，沿用 Fable 5 + mem0 先例）；answer prompt 源
  plan 第一手确定。
- D2 smoke=100k + turn 截断（flow-through 即可）。D3 10m 缓做。
- D4 user_profile 等不注入。D5 judge=gpt-4o-mini。
- **D6（待用户）** event_ordering 排序分 v1 是否纳入——架构师推荐先统一 rubric
  judge、排序分作标注增强项，不阻塞列点亮。
