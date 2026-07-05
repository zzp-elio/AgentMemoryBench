# 未来想法备忘

更新日期：2026-06-20

本文件记录当前不进入主线开发、但可能成为项目特色能力的想法。这里的内容不作为短期
commitment；进入实施前必须重新讨论、写 spec 和验收标准。

## 实验监控 AI

想法：

- 做一个能读取 `outputs/<run_id>/checkpoints/progress.json`、`logs/events.jsonl`、
  `summaries/summary.json` 和 efficiency summary 的实验监控 agent。
- 用户可以用自然语言询问“现在实验跑到哪里了”“哪个 worker 卡住了”“当前 token 成本
  大概是多少”“有没有异常 warning”。
- 后期可以接入手机端通知或 IM：微信、飞书、Telegram 等。
- 也可以调研 Hermes、OpenClaw 等现成 agent/skill 框架是否适合作为入口。

当前状态：

- 只是长期方向，不进入 Phase 1。
- 前置条件是标准 artifact、progress、events 和 efficiency summary 稳定。

## 新 Method 接入 Skill

想法：

- 项目成熟后重做一份“新 memory method 接入 skill”。
- 用户提供第三方 method 仓库后，agent 按固定流程读取 README、论文、实验脚本和原生接口，
  自动补 `docs/method-interface-inventory.md`、adapter skeleton、config profile 和测试。
- 接入完成后自动跑 contract 测试、resume 测试、并行 smoke 测试和最小真实 API smoke。

当前状态：

- 旧版接入 skill 质量不够，暂不使用。
- 必须等当前四个官方 method 的 adapter 契约、resume、observability 和 smoke 流程稳定后再做。

## Worker 级实时进度展示

想法：

- 在多 worker prediction 时，终端不仅展示 run/conversation/question 总进度，也展示每个
  worker 当前状态：worker id、conversation id、当前阶段（add/retrieve/answer/evaluate）、
  已处理 turn/round 数、问题数和最近更新时间。
- 如果 method adapter 能精确上报 turn/round progress，就展示精确值；如果不能，就用
  conversation 总 turns 与阶段状态给出估计进度，并明确标注为 estimated。
- 该信息应同时写入 `checkpoints/progress.json` 或独立 worker progress artifact，避免只在
  Rich 终端里可见。

当前状态：

- 只是 UX 增强，不进入当前 P0。
- 前置条件是先稳定现有 isolated worker、stdout/warning 捕获和 retrieve-first 架构方向。
