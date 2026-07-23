# 架构经验检索索引

本目录是架构师经验的冷层。热入口是
[`../../architect-playbook.md`](../../architect-playbook.md)；截至 2026-07-23 的完整旧案例在
[`casebook-through-2026-07-23.md`](casebook-through-2026-07-23.md)。

## 为什么不再每次全文读取

经验库会持续增长。每次全量读取会同时造成：

1. 与当前任务无关的规则进入上下文，增加错误联想；
2. 热状态被历史判例挤出窗口；
3. 新旧裁决混在一起，模型容易把 superseded 结论当现行政策；
4. 每次恢复成本随项目年龄线性增长。

正确模式是“热规则常驻 + 任务标签检索 + 一到两条案例定点阅读”，与代码检索、
RAG 和 skill routing 同理。

## 检索流程

1. 先读热入口，确认当前动作属于哪一类；
2. 从下表选择 2-4 个关键词；
3. 用 `rg -n '<关键词1>|<关键词2>'` 搜本目录；
4. 只读命中的一到两段案例及其直接引用；
5. 若案例与当前 Git/政策冲突，以最新 ruling + Git 为准；
6. 新经验先写成独立 case card，再更新本索引；不得继续把整段追加回热入口。

## 任务路由

| 当前任务 | 检索关键词 | 首选冷层 |
| --- | --- | --- |
| 写 actor 卡、并行派工 | `新人标准|worktree|并行上限|派发权|任务卡就是 prompt` | 旧案例库原则 18/20/21/24/25/27 |
| 强验收、迁移等价性 | `三层审查|等价性|fake 测试|强反例|全量门` | 旧案例库 §4、§14.2/14.3 |
| benchmark/method 一手取证 | `第一手源|能力断言|source lock|复用 benchmark 真相` | 原则 11、§14.5 |
| role/time/place/image 输入 | `placeholder|role-aware|metadata|effective timestamp|caption` | 原则 26/28、§14.6 |
| metric/Recall/NDCG | `资格|gold group|粒度|ranking depth|分母` | 原则 15、§14.7/14.9/14.13 |
| prompt/TOML/作者校准 | `完整 builder|native/unified|author_|PromptMessage` | 原则 17/31、§14.13 |
| manifest/resume/identity | `preflight|strict identity|resume|字段缺席|null` | 原则 12/29/32、§14.8 |
| smoke/成本/真实 API | `开箱验货|成本 pilot|tee|调用发生|actual observation` | 原则 13/19/22/33 |
| Git/目录/第三方仓库 | `显式路径|worktree|source identity|独立 upstream` | 原则 8/18、§14.10/14.11 |
| 文档/压缩/经验检索 | `热层|冷层|消费者|触发器|退出条件|结构治理` | 原则 30、§14.12/14.13 |

## 新 case card 规范

未来新增经验写入 `cases/<yyyy-mm-dd>-<slug>.md`，最少包含：

```yaml
---
id: architect-case-<slug>
date: YYYY-MM-DD
triggers: [任务标签]
supersedes: []
---
```

正文固定回答：

1. 观察到了什么；
2. 原裁决为何不够；
3. 新裁决及适用边界；
4. 一手证据/commit/note；
5. 什么触发它被重读；
6. 什么证据会使它退出或被 supersede。

一条 case 只表达一个可复用经验。执行流水账仍留在 workstream note，不复制进案例库。
