# LongMemEval Dataset 结构卡（现行契约）

更新日期：2026-07-16（retrieval gold/分母定点解冻；现场剖面全量数字见
`docs/workstreams/ws02.6-first-smoke-hardening/notes/longmemeval-b2-audit.md`，
逐文件身份见同目录 `longmemeval-source-lock.json`）

## 1. 顶层结构

数据文件是一个 JSON list，含 **500 个互相独立的 evaluation instance**。
**1 instance = 1 question + 一整段专属 haystack 对话史**；隔离空间 =
instance，`conversation_id = question_id`。

```text
instance
├── question_id          # 公开；`_abs` 后缀 = abstention 题（30 道）
├── question_type        # 公开；6 类，映射 Question.category
├── question             # 公开
├── question_date        # 公开；映射 Question.question_time（官方 prompt 的 Current Date）
├── answer               # 私有（gold）
├── answer_session_ids   # 私有（session 级 evidence）
├── haystack_session_ids # 公开；与 dates/sessions 按 index 严格对齐
├── haystack_dates       # 公开；session 级时间（格式 `2023/05/30 (Tue) 23:40`）
└── haystack_sessions    # 公开；list[list[turn]]
```

turn 只有 `role`（user/assistant）+ `content`；evidence session 内的 turn 另有
私有 `has_answer` 标记。**turn 无时间戳，继承 session 时间。**

## 2. 两个 variant 的现场剖面（`_s` 全量 / `_m` 流式）

| 指标 | `s_cleaned`（277MB） | `m_cleaned`（**2.7GB**） |
|---|---:|---:|
| instance | 500 | 500 |
| session 总数 | 23,867 | ~482/题 |
| turn 总数 | 246,750 | ~5,000+/题 |
| abstention（`_abs`） | 30 | 30 |
| `has_answer` 键出现 / True | 10,960 / 896 | 同分布 |
| 非严格 user-first 交替 session | **1,947（约 8%）** | 同类分布 |
| 奇数长度 session | 1,940 | 同类分布 |

- question_type 分布（两 variant 相同）：multi-session 133 /
  temporal-reasoning 133 / knowledge-update 78 / single-session-user 70 /
  single-session-assistant 56 / single-session-preference 30。
- 异常 role 形态真实存在（assistant 先说 / 纯 assistant / 连续同 role /
  连续 user）——**原样保留注入，orphan/dangling 标记由框架聚合层打，不丢弃**
  （haystack 干扰是任务语义）。
- `_m` 的任何扫描/加载必须 ijson 流式，禁止一次性 `json.load`/`read_bytes`。
- `oracle` 变体官方存在，本框架不注册。
- retrieval 主路径只把 **user-role** `has_answer=True` turn 建入 corpus/gold。S cleaned
  重算：`_abs=30`、non-abs no-user-target=51、assistant-side true turn=54、任意 role
  都无目标=21（且全属 abs）；主路径有效分母=419。

## 3. 框架映射与 id 约定

adapter：`src/memory_benchmark/benchmark_adapters/longmemeval.py`。

- 公开 turn id = `{session_id}:t{raw_index}`（0 基原始序号，跳过的空 turn
  不改后续序号）；session id 重复时去重为公开唯一 id，原始 id 存
  session metadata `original_session_id`。
- 官方 corpus_id 别名 = `{original_session_id}_{raw_index+1}`（1 基，
  `run_generation.py:79` 约定）——只作对照记录，不作匹配键。
- gold（`GoldAnswerInfo`，evaluator 私有，随 private label 序列化）：
  - `evidence` = 官方 `answer_session_ids` 原样；
  - `metadata.evidence_session_public_ids` = session 级匹配键（公开 id 空间）；
  - `metadata.evidence_turn_ids` / `evidence_groups` = turn 级匹配键（**仅 user-role
    `has_answer=True`**，公开 id 空间）；
  - `metadata.evidence_turn_corpus_ids` = 官方别名（仅记录）。
- official retrieval 主路径剔除全部 `_abs` 题，并额外剔除 51 个 non-abs
  no-user-target 题；`print_retrieval_metrics.py` 只剔 abs 得 470，作为官方辅助脚本矛盾
  披露，不作为 canonical parity。
- 公私边界：`answer`/`answer_session_ids`/`has_answer` 绝不进公开对象；
  官方 generation 自己也在进 prompt 前 pop `has_answer`
  （`run_generation.py:182`）。公开泄漏扫描为冻结验收项。
- dataset metadata 带 source identity（repo/paper/HF/license/全文件
  `source_sha256` 分块流式现算）与实际加载计数。

当前 adapter 仍会把 assistant-side `has_answer=True` 收进 turn gold；这是待 ws02.7 M1
修复的已知偏差，不得用旧 frozen 文字宣布 retrieval parity。
