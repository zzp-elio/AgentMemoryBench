# MemBench Dataset 结构卡（现行契约）

更新日期：2026-07-16（canonical role/evidence-unit 定点解冻；现场剖面全量数字见
`docs/workstreams/ws02.6-first-smoke-hardening/notes/membench-b3-audit.md`，
逐文件身份见同目录 `membench-source-lock.json`；现行裁决见
[gold evidence unit 审计](../../workstreams/ws02.7-method-track/branches/input-role-semantics/notes/evidence-unit-contract-audit.md)）

## 1. 顶层结构

数据根 `data/membench/Membenchdata/data2test/{0-10k,100k}/`，每规模 4 个
正式文件 = **视角 × 记忆类型**：

| 文件 | 视角 | message 形态 | trajectory 数（0-10k/100k） |
|---|---|---|---:|
| FirstAgentDataHighLevel | 第一人称 | dict `{user, agent}` | 700 / 140 |
| FirstAgentDataLowLevel | 第一人称 | dict `{user, agent}` | 900 / 360 |
| ThirdAgentDataHighLevel | 第三人称 | 纯字符串 | 400 / 80 |
| ThirdAgentDataLowLevel | 第三人称 | 纯字符串 | 1,400 / 280 |

文件内层级 `{task_type: {sub_key: [trajectory]}}`；trajectory =
`{tid, message_list, QA}`；**隔离空间 = trajectory（tid）**，每条恰 1 个
question。variant `0_10k`（默认认证口径）/`100k`（noise 拉长版，最大单文件
227MB）。

## 2. QA 与公私边界

QA = `{qid, question, time, answer, ground_truth, target_step_id, choices}`。
**全部 task type 都是单字母 MCQ**（`ground_truth` 恒 A-D；`answer` 是选项
内容，str/list 只是内容形态——lowlevel_rec 的选项本身是条目列表）。

- 公开：`question`、`choices`（同时进 `Question.options`）、`time`
  （→ `question_time`）、task_type（→ `category`，通用 category_breakdown
  按此分报）
- 私有（只进 `GoldAnswerInfo`）：`answer`、`ground_truth`、
  `target_step_id`

## 3. 时间戳（两个官方生成器造成的形态）

step 文本尾部内嵌 `(place: …; time…)`，**存在两种官方格式**：

- 带冒号 `time: '2024-10-01 08:00'`（原始文本自带）
- 无冒号 `time'2024-10-01 08:00'`（官方加噪代码
  `load_test_data.py:57` 的 `time{}` 格式串所致）——0-10k ThirdLow 全部
  19,285 条均为此形态；100k 各文件混布且大量 noise message 无时间后缀

adapter 正则 `time:?\s*'…'` 兼容两态（`membench.py`）。原文中的 place/time 不删除；
每条 canonical utterance 只从自身 content 抽 `turn_time`，无后缀 noise → None；
**session_time 保持 None，不取兄弟 utterance 或首个有时 step 冒充 session 时间。**

## 4. id 约定与 evidence

- 官方 `target_step_id` 为 **0 基 pair/string step id**（`load_test_data.py` 的
  reverse_relocate_dict 按 enumerate 构建）。FirstAgent 一个 step 含 user+agent 两条
  utterance，canonical 修复后各有独立 child turn id；ThirdAgent 一个 string step 仍只有
  一个 child。
- evaluator 私有 `evidence_groups` 把每个官方 step 映射到 child turn ids：FirstAgent 为
  `{user_child, assistant_child}` any-of group，ThirdAgent 为单元素 group。每个 group 只计
  一个 gold unit，分母按官方 `len(set(target_step_id))`，不得因 role 拆分翻倍。
  原 0 基 target 与 group 都只随 private label 序列化，绝不进入 method/public artifact。
- 已知官方数据异常（全库现场量化）：越界 target_step_id 2 例
  （两规模同源 comparative/events tid=4，=len 疑似官方 off-by-one）；空
  target_step_id 1 例（0-10k FirstHigh highlevel_rec/movie tid=25）。
  adapter 必须合法保留并显式计数；越界映射为 unmatched group，空 target 记 N/A，不能
  按旧 evaluator 静默记 1.0。
