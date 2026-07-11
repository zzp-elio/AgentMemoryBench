# HaluMem 数据集契约卡（frozen-v1，2026-07-11）

> 本卡是现行数据契约的事实源之一，与
> `ws02.6/notes/halumem-frozen-v1.md`（冻结记录）、
> `ws02.6/notes/halumem-h1-audit.md`（全量剖面+可复算脚本）、
> `docs/reference/dataset-quirks.md`（个性索引）互为锚。
> 推翻任何条目须 frozen-v2 + 影响分析。旧调研版（2026-06 期）见
> git 历史。

## 1. 来源身份

`data/halumem/HaluMem-{Medium,Long}.jsonl`（SHA-256+字节数锁在
`notes/halumem-source-lock.json`）；官方 repo MemTensor/HaluMem、
arXiv 2511.03506、HF IAAR-Shanghai/HaluMem、CC-BY-NC-ND-4.0。
框架只从 `data/` 加载。

## 2. 结构与规模

一行 JSONL = 一个 user（=框架 conversation）：`uuid / persona_info /
sessions / token_cost / total_dialogue_token_length /
total_question_count`。

| variant | user | session | turn | 题 | 缺 questions 键 | generated session |
|---|---:|---:|---:|---:|---:|---:|
| Medium | 20 | 1,387 | 60,146 | 3,467 | 491 | 0 |
| Long | 20 | 2,417 | 107,032 | 3,467 | 491 | 1,030 |

## 3. 字段契约（全部有测试锚，锚见 quirks 表）

- **session**：`dialogue / start_time / end_time / memory_points /
  questions(可缺键)`；491 个普通 session **无 questions 键**（缺键 ≠
  空列表）；Long 的 1,030 个 `is_generated_qa_session=True` session
  **questions 键存在但恒空、无 memory_points**（两种不同形态，健壮
  读取都覆盖）——官方评测端整体跳过（evaluation.py:51-52），框架
  只 ingest。
- **turn**：`role/content/timestamp/dialogue_turn`；全库严格
  user/assistant 交替（0 异常）；时间格式 `%b %d, %Y, %H:%M:%S`
  三层齐全。
- **memory_points**：`memory_content / memory_type(Persona 9,116·
  Event 4,550·Relationship 1,282) / is_update / original_memories /
  importance / index / memory_source / timestamp`。
  **`is_update` 是字符串 "True"/"False"**（truthy 判断必错）；
  "True" 6,244 条全带非空 original_memories（官方更新探针双条件，
  eval_memzero.py:210-222，全库无反例）。
- **questions**：`question / answer / evidence / difficulty /
  question_type(六类：Memory Boundary 828·Basic Fact Recall 746·
  Memory Conflict 769·Generalization & Application 746·Multi-hop
  Inference 198·Dynamic Update 180)`。**evidence = 原生 list**，
  4,651 元素全为 `{memory_content, memory_type}`，**无 turn id**
  （3,354 同 session + 1,297 前序，无 future/unmatched）；官方用途 =
  QA judge 的 Key Memory Points（evaluation.py:178-185）→
  retrieval recall N/A。

## 4. 公私边界

`answer / evidence / memory_points / persona_info` 私有
（GoldAnswerInfo + session private_metadata）；公开对象只含
dialogue/时间/id/question 文本/question_type；e2e privacy 三层扫描
CLEAN。

## 5. 复算

剖面与断言的可复算脚本在 `notes/halumem-h1-audit.md` §6；字节身份
`shasum -a 256 data/halumem/HaluMem-{Medium,Long}.jsonl`。
