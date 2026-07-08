---
id: ws02.3
parent: ws02
status: spec-approved（D6 已决，待架构师写 plan）
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
  list[session]、content 带 `->->` 尾标记。
- 2026-07-08（用户拍板 D6）：**D6 已决**——用户认可"v1 先做统一 rubric judge、
  event_ordering 的 kendall-tau 排序分 defer 到 v2"，但明确要求"别忘记后续
  加上"，故排序分是**承诺项（committed follow-up），非可选**。D6 是 BEAM 唯一
  开放决策点，拍板即等于 spec 实质定案 → **plan 解锁**。下一步：架构师写
  BEAM plan（含 kendall-tau 作为有触发条件的独立 backlog task + README 长期挂账）。

## 任务清单

- [x] 架构师起草 spec（2026-07-08，第一手核对）
- [x] 用户批准 spec（2026-07-08，D6 拍板；D1-D5 架构师已定）
- [ ] 架构师写实施 plan
- [ ] actor 施工 + fake 全链路
- [ ] 架构师验收
- [ ] 极小真实 smoke（待用户确认预算）

## 决策点（详见 spec.md §5）

- D1 int→float 修正（架构师定，沿用 Fable 5 + mem0 先例）；answer prompt 源
  plan 第一手确定。
- D2 smoke=100k + turn 截断（flow-through 即可）。D3 10m 缓做。
- D4 user_profile 等不注入。D5 judge=gpt-4o-mini。
- **D6（已决）** event_ordering 的 kendall-tau 排序分 v1 defer、v2 承诺补上
  （用户 2026-07-08 拍板："同意推荐，但别忘记后续把 kendall-tau 排序加上"）。
  v1 仅做 event_ordering 的 rubric llm_judge_score。

## 长期挂账（承诺项，勿当可选砍掉）

- **kendall-tau event_ordering 排序分**：BEAM plan 写完后，作为一条独立 backlog
  task 挂在这里；触发条件 = BEAM v1 smoke 跑通。见 spec.md §S4.1 + D6。
