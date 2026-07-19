# BEAM Dataset 结构卡（现行契约）

更新日期：2026-07-16（evidence-group 复核；剖面全量数字见
`docs/workstreams/ws02.6-first-smoke-hardening/notes/beam-e1-audit.md`，
逐文件身份见同目录 `beam-source-lock.json`）

## 1. 顶层结构（HuggingFace arrow，`load_from_disk`，只从 `data/BEAM/` 加载）

- `data/BEAM/beam_dataset/`：splits 100K=20 / 500K=35 / 1M=35 conv
  （同构单 plan）；`data/BEAM/beam_10M_dataset/`：10M=10 conv（异构）。
  共 100 conv × 10 类 × 2 题 = **2,000 questions**。
- record：`conversation_id / conversation_seed{category,theme,title,
  subtopics} / narratives / user_profile / conversation_plan /
  user_questions[{messages,time_anchor}] / chat / probing_questions`。
- **`probing_questions` 是 Python 字面量串，必须 `ast.literal_eval`**
  （json.loads 会炸，现场验证）。
- 单 plan chat = `list[session[turn]]`；turn =
  `{content,id,index,question_type,role,time_anchor}`（turn 有时间锚，
  probing question 本身无时间锚）。
- **10M 异构**：record 额外带 `plans`×10（各含独立 chat 等）；**顶层
  `chat` = `list[dict]`（10 个 `{plan-N:…}`）**，官方按
  `chat[i]['plan-{i+1}']` 顺序消费（`ten_milion_pipeline.py:1436-1440`）
  ——adapter 的 `10m` variant 照此展开，session id `pN:sM` 全局唯一，
  plan 边界留 session metadata。

## 2. 问题 taxonomy 与公私边界

10 类 × 每类 2 题：abstention / contradiction_resolution /
event_ordering / information_extraction / instruction_following /
knowledge_update / multi_session_reasoning / preference_following /
summarization / temporal_reasoning。每题必有 `question` + `rubric` +
`difficulty`；gold 字段按类异构（answer/ideal_response/ideal_summary/
expected_compliance/why_unanswerable/…）。

- 公开：`question`、ability（→`category`，category_breakdown 按此
  分报）、difficulty
- 私有：全部 gold/rubric/evidence 字段——**已进全局私有键黑名单**
  （`core/validators.py`，E2 落地）

## 3. evidence 与 id 约定（E1 强制判定 + 裁决）

- `source_chat_ids` 原子 = turn 整数 `id`；**三种形态**：平铺 list /
  event_ordering 嵌套分组 / contradiction·knowledge_update·temporal 的
  带标签 dict 分组。全库 10,534 原子，非法原子恰 1 个 `'--'`（10M 位置
  5 EO 题 0）。
- **1M 位置 4/25/32/33 的 turn id 跨 session 重复**（150/424/206/940，
  根因：官方后续 session 的 id 从 0 重启）。
- 匹配键 = 公开 turn id `{session_id}:t{turn_index}`（1 基）；gold
  `metadata["evidence_turn_ids"]` = raw id → **全部**匹配位置（any-match
  + `ambiguous_gold_id_count`）；官方三形态原样留 metadata 对照；`'--'`
  不进匹配键、unmatched 计数。abstention 类恒无 evidence → recall N/A。
- 该 positional namespace 与“session 序号 + session 内 turn 序号”同构，已能抵抗 raw id
  重复、跳号与重启；不为换成更短的 `0:2` 格式重命名既有 public ids。raw id 一对多时，
  私有 qrel 用 multi-child any-of group 表达官方无法消歧的候选位置。
- 当前全量 adapter load：1M 有 41 个 `ambiguous_gold_id_count>0` 的题、逐题累计
  198 个歧义 raw-id 原子；10M 有 1 个 unmatched（`'--'`）。因此 evidence-group
  必须支持多 child any-of，不能把 BEAM 永久退化为单元素别名。
- 官方 `evaluation/` 完全不读取 `source_chat_ids`；BEAM Recall 是框架补充诊断，必须标
  `framework_supplementary`，不能称官方指标。
- 快照自带 `.git`：官方代码 commit 已锁 `3e12035`（五 benchmark 首个
  可锁 commit 的快照）。

## 4. 当前 release 的异常摘要

详细位置、原文例子、统计命令含义与统一处置见
[`异常情况/beam.md`](../异常情况/beam.md)。稳定摘要：

- 100K/500K/1M 共 790 sessions、118,420 turns，role 形状严格 user→assistant；但 1M
  四个 conversation 的 raw id 在后续 session 重启，现行 positional public id +
  private multi-child any-of group 已吸收。
- 10M 共 1,000 batches/sessions；只有两处 turn group 以 follow-up user 悬空并与下一组首
  user 相邻，其中 conversation 2 的下一 assistant 还存在明显主题错位。框架保留原文原序，
  不猜修数据；pair aggregator 以 dangling/new-pair 处理。
- 10M 有一个全缺 `time_anchor` session，另有 5 个相邻 session anchor 回退；source time
  原样保留，不跨 session 排序/修钟。
- 10M 有一个非法 `'--'` evidence 原子，按 unmatched 私有 qrel 留痕，不泄漏给 method。
