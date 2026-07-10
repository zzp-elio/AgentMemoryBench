# MemBench Dataset 结构卡（现行契约）

更新日期：2026-07-11（B3 `frozen-v1`；现场剖面全量数字见
`docs/workstreams/ws02.6-first-smoke-hardening/notes/membench-b3-audit.md`，
逐文件身份见同目录 `membench-source-lock.json`）

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

adapter 正则 `time:?\s*'…'` 兼容两态（`membench.py`），无后缀 → turn_time
None，session_time 兜底取首个带时间戳 turn。

## 4. id 约定与 evidence

- 公开 turn id = `str(step_index + 1)`（**1 基**）；官方 `target_step_id`
  为 **0 基**（`load_test_data.py` 的 reverse_relocate_dict 按 enumerate
  构建）。
- `GoldAnswerInfo.evidence` = **公开 turn-id 空间**（`str(step_id+1)`，
  匹配键）；官方 0 基原值保留在 `metadata["target_step_id"]`（对照记录）。
  evidence 随 private label 序列化在**顶层**（`evaluator_private_label_record`），
  metadata 只存对照记录——evaluator 读键位以此为准。
- 已知官方数据异常（全库现场量化）：越界 target_step_id 2 例
  （两规模同源 comparative/events tid=4，=len 疑似官方 off-by-one）；空
  target_step_id 1 例（0-10k FirstHigh highlevel_rec/movie tid=25）。
  adapter 均合法保留（越界映射为不存在的 turn id、空为 empty evidence），
  recall 侧分别记 unmatched-gold / N/A。
