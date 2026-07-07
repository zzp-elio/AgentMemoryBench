---
id: ws02.2
parent: ws02
status: plan-ready（spec approved，待 actor 施工）
created: 2026-07-08
---
# ws02.2 HaluMem Adapter（Phase 1 第二个新 benchmark，operation-level）

## 目标

按协议 v3 接入 HaluMem full operation-level（抽取 + 更新 + QA 三段），为 5×10
矩阵打开第四列，点亮项目北极星"能力维度"轴的最高分辨率。完成判据见
[spec.md](spec.md) §9。

## 当前断点

- 2026-07-08（架构师 Opus 4.8 裁定，解 Codex 停工 + smoke 定案）：**R1** Codex
  停工正确——extraction/update 评测是 session 级（`evaluation.py:54-95` 遍历每
  session 的 memory_points，与 question 无关），491 个无 question 的 memory
  session 会漏。裁定加 **session 级 evaluator-private gold artifact**（memory_points
  + dialogue），T3 补写、T4 读（plan R1）。**R2** 用户提案"CLI 控 session 数 +
  smoke 覆盖三模式"采纳：加 `smoke_session_limit`+`--sessions`（替换 turn_limit
  复用）；**第一手数据修正**：update 模式最早在第 4 个 session、覆盖三模式最小
  前缀=5，故 `--sessions≥5`（架构师上轮"2 sessions"错、会漏 update）。详见
  plan"架构师裁定第二轮"。下一批：T3 补 R1 artifact + R2 CLI session 控制 + T4
  三 evaluator + T5。
- 2026-07-08（Codex，停工）：在 T4 三 evaluator 开工前遇到 plan 未覆盖的
  artifact 事实缺口；已完成并 commit 到 T3，T4/T5 未提交。证据：真实数据实测
  `HaluMem-Medium.jsonl {'total_sessions': 1387, 'generated': 0,
  'memory_sessions': 1387, 'memory_sessions_without_questions': 491}`，
  `HaluMem-Long.jsonl {'total_sessions': 2417, 'generated': 1030,
  'memory_sessions': 1387, 'memory_sessions_without_questions': 491}`。官方
  `evaluation.py:54-95` 对每个 session 的 `memory_points` 与
  `extracted_memories` 做 extraction/integrity+accuracy 输入；但当前 T3
  artifacts 只写 question 级 `evaluator_private_labels.jsonl`，无 question 的
  491 个 memory session 无法从 artifacts 还原 gold memory_points/dialogue。
  当前 `operation_level.py:349-369` 的 `session_memory_reports.jsonl` 仅写
  provider report metadata，不写 evaluator-private session gold。若继续做 T4，
  extraction 分母会漏掉 491 个 session；是否新增 evaluator-private session
  artifact、或允许 session report metadata 携带私有 gold，需要架构师裁定。
- 2026-07-08（架构师 Opus 4.8 验收 T1 re-touch + T3）：**通过**。本机复跑
  `test_operation_level_runner.py`+`test_halumem_adapter.py`=10 passed，全量
  831。第一手核对（读 `evaluation.py` scorer 逐行）确认 runner 语义全对：update
  探针条件（`operation_level.py:328-347`，runner 端 `is_update!="False" 且
  original_memories）、三段驱动 + 累积状态（测试 `update_write_counts==
  [(1,1),(3,3)]` 同时锁死无写副作用 + 累积）、`is_generated_qa_session` 跳过
  三段、extraction N/A、resume 均覆盖。Codex "计划外发现"（operation-level 跳过
  generic preflight + CLI 分派 + 约束 max_workers=1）经查正确。**架构师第一手
  新发现**（趁 T4 未建补进 plan）：`evaluation.py:58-70` **integrity/update
  互斥路由**——成功探测的 update 点从 recall 分母剔除；已把 evaluation.py 逐行
  聚合口径（0.5 因子、FMR、F1、dialogue_str 格式、排除 interference）钉进
  plan T4 补充块。数据核对：`is_generated_qa_session` 仅 Long（Medium=0/
  Long=1030）、`is_update` 仅 True/False——用户四点理解全部第一手证实。
  下一批：T4 三 evaluator。
- 2026-07-07（Codex）：完成架构师验收发现的 T1 re-touch（F1 evidence 改存
  memory_content；F2 smoke 支持每 user 前 M 个完整 session，复用
  `smoke_turn_limit`）并提交；继续完成 T3 operation-level runner（新
  `runners/operation_level.py`，按 spec S4.2 逐 session 执行 extraction →
  update → QA，generated session 只 ingest/end_session 不落三段 artifact，
  update probe 无写副作用，conversation 级 resume skip）。验收输出已追记到
  [plan.md](plan.md)：T1 re-touch focused `7 passed`、全量
  `828 passed, 3 deselected, 2 warnings, 6 subtests passed in 101.26s
  (0:01:41)`；T3 focused `3 passed`、全量 `831 passed, 3 deselected, 2
  warnings, 6 subtests passed in 102.16s (0:01:42)`。下一步：停在 T4/T5
  前，交架构师验收 operation-level runner 与 artifact 口径。
- 2026-07-08（架构师 Opus 4.8 验收）：**T1/T2 验收通过**（本机复跑
  `tests/test_halumem_adapter.py` + `test_benchmark_registry.py` = 42 passed，
  全量 827 passed）。验收以第一手源核对（HaluMem 官方仓库 `eval_memzero.py`/
  `eval_tools.py` + 真实数据 + `docs/survey` 三份 HaluMem 卡全读）——查出**两处
  架构师 plan 失误**（非 Codex，Codex 防御性保留 raw_evidence 反而救了场）：
  **F1** evidence 应存 memory_content 非 index（且可跨 session）；**F2** smoke
  口径只裁 user 不裁 session，1 user≈65 sessions 太大，须支持每 user 前 M
  整 session 截断。两项已写进 plan（T1 findings 块）并入下一批 re-touch。
  Codex 还正确点出 plan"机制卡是唯一事实源"对 benchmark 任务不精确，已修
  （按任务类型区分第一手源）。下一批：re-touch T1（F1+F2）+ T3
  operation-level runner。
- 2026-07-07（Codex）：按用户要求只完成 T1/T2 后停工交架构师验收。T1
  HaluMem adapter 已提交 `fa3d5e5`；T2 benchmark registration +
  `operation_level` 分派声明与本断点记录在本提交内；验收输出已追记到
  [plan.md](plan.md) 对应 task 下。基线不跌破：T1 全量回归
  `825 passed, 3 deselected, 2 warnings, 6 subtests passed in 104.61s
  (0:01:44)`，T2 全量回归 `827 passed, 3 deselected, 2 warnings, 6
  subtests passed in 104.60s (0:01:44)`。下一步：架构师验收 T1/T2，
  通过后再放行 T3 operation-level runner。
- 2026-07-08（架构师 Opus 4.8）：**spec approved + plan ready，待 actor 施工**。
  用户评审定案三点：① D1 批准（遵循 HaluMem 官方 gold-as-query）；② 定调
  **弃用 `TaskFamily/MethodCapability/validate_compatibility` enum 门控，改
  "接口即契约"**（S6 重写：谁覆写 `end_session` 返回增量报告谁就有 extraction
  能力；架构师加 preflight 内省一条工程约束以保预算安全）；③ 用户"注意三种
  触发时机"点出 spec 两处错误已修（`is_generated_qa_session` 跳过全部三段、
  extraction 增量 vs update/QA 累积）。D4 取证：Mem0 `add()` 返回增量→可提供
  extraction 报告；SimpleMem 窗口抽取粒度≠session→N/A。plan 见
  [plan.md](plan.md)（T1-T7，最大 plan，允许跨 actor 会话接力）。
- 2026-07-08（架构师 Opus 4.8）：spec draft 产出，关键结论协议 v3 零改动即可
  承载 operation-level（推翻调研卡 2026-06-29"需扩协议"旧判断）。

## 任务清单

- [x] 用户定范围：Full operation-level（2026-07-08）
- [x] 架构师起草 spec（2026-07-08）
- [x] 用户批准 spec（2026-07-08，D1 接受官方做法 + S6 改接口即契约）
- [x] 架构师写实施 plan（[plan.md](plan.md)，T1-T7）
- [ ] actor 施工 + fake 全链路
- [ ] 架构师验收
- [ ] 极小真实 smoke（待用户确认预算）

## 决策点（详见 spec.md §7，均已定案）

- **D1（用户批准）**：update 探针 gold-as-query 遵循 HaluMem 官方；兜底 =
  plan T3"update 探针无写副作用"契约测试。
- **S6（用户定调）**：弃用 enum 门控，接口即契约 + preflight 内省。旧
  `capabilities.py` enum + 冗余 `session_memory_report` bool 标为 ws03 减重候选。
- D2-D5 架构师裁定：judge=gpt-4o-mini（标注非严格复现）、smoke=medium、
  extraction 能力逐 method 按机制卡（T5：Mem0 可 / SimpleMem N/A / 余核实）、
  persona_info 不注入。
