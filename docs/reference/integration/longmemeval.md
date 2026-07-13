# LongMemEval 接入实例（A1-A8 逐项）

> 判据模板：`../method-integration-checklist.md` §A；勾选总表：`../integration-status.md`。
> **frozen-v1（2026-07-10）**；证据主库 =
> `docs/workstreams/ws02.6-first-smoke-hardening/notes/longmemeval-frozen-v1.md`。

## A1-A8 逐项

- **A1 来源锁 ✅**：repo `xiaowu0162/LongMemEval`（MIT，arXiv 2410.10813）；数据 =
  HF `_cleaned` 2025/09 官方重清洗版（替代原始发布）；`s_cleaned`/`m_cleaned`
  SHA-256 已锁；**官方 commit 来源待溯**（快照无 .git）。
- **A2 数据契约 ✅**：500 instance / 23,867 session / 246,750 turn / 30 abstention；
  非严格交替 session 1,947、奇数 1,940 原样保留；`_m` 2.7GB 流式加载。
- **A3 公私边界 ✅**：`answer`/`answer_session_ids`/`has_answer` 绝不进公开对象；
  泄漏扫描 CLEAN。
- **A4 canonical/GC-1 ✅**：公开 turn id `{session_id}:t{raw_index}`（0 基）；官方
  corpus_id 只作对照 metadata（C4 停工裁决：匹配键=公开 id 空间）。
- **A5 prompt/metric parity ✅**：unified answer=官方非-CoT 模板**逐字**（程序化对比）；
  `longmemeval-judge` 主指标 = 官方 `get_anscheck_prompt` **7/7 逐字 MATCH**
  （含 `_abs` abstention 路由）；`f1` 只是 framework 补充；
  `longmemeval-retrieval-rank`（B6.1 加法）= 官方 NDCG/recall k∈[1,3,5,10,30,50]
  经 3000 例复算零失配。
- **A6 smoke/resume ✅**：1 instance × 1 round × 1 题（轴=rounds，其他轴 fail-fast）；
  formal instance 级 checkpoint。
- **A7 artifact/efficiency ✅**：gold 双粒度 evidence 走 private label 通路，无新增
  artifact 面。
- **A8 冻结门 ✅**：全量 923 passed 时点通过。

## 对 method 接入的含义

1. **1 instance = 1 conversation = 1 question**（隔离空间=instance）→ smoke 默认
   问题帽=1 的依据之一（卡 X）；per-instance 记忆库彻底独立，天然并行友好。
2. turn 无时间戳、继承 session `haystack_dates` → 时间推理题（temporal-reasoning
   question_type）对时间戳注入方式极敏感，B4 逐 method 核。
3. abstention 题（30 个）：judge 走 `_abs` 路由；recall 对 abstention N/A——method
   报告里这两类别弄混。
4. **已知偏差必声明**：官方 judge 用 `gpt-4o-2024-08-06`，框架统一 gpt-4o-mini
   （冻结记录 §7.1）；与论文对比数字时不可直接对齐（R0 校准阶段处理）。
5. `_m`（2.7GB）未做全链路，full 跑前单独评估成本。
6. **native 格**：Mem0 / LightMem / SimpleMem / MemOS（LightMem native answer 走
   prompt_messages 透传，见 lightmem 实例 B4）。
7. answer 口径 unified 轨固定 gpt-4o-mini/temp0/max_tokens=500。
