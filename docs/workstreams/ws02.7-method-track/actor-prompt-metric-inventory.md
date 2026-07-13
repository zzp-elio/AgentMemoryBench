# Actor 卡 MX-1：指标盘点（指标扩展计划第一步）

> 派发日 2026-07-13。自包含卡。**纯取证卡：唯一交付物 =
> `docs/workstreams/ws02.7-method-track/notes/metric-inventory.md`**；禁改代码；
> 禁真实 API。背景与匹配规则见 `docs/reference/metric-extension-plan.md`
> （先读它，本卡只做它的 §2 第一步"盘点"，**不做匹配裁决**）。

## 0. Git 纪律
独立 worktree + 分支 `actor/mx-1-metric-inventory`（用户已建）。只 commit 本分支、
禁 push、禁碰其他分支。

## 1. 三张盘点表

**表 A：框架已注册 evaluator 面**（一手 = `src/memory_benchmark/evaluators/registry.py`
及各 evaluator 模块）：每行 = metric 名 / supported_benchmarks / requires_api /
metric_tier（从代码或 score artifact 字段找实际 tier 值）/ 一句话语义 / 实现文件:行号。

**表 B：五 benchmark 官方指标面**（一手 = 五份
`docs/workstreams/ws02.6-first-smoke-hardening/notes/<b>-frozen-v1.md` §5 +
必要时回查 third_party 官方 eval 代码）：每行 = benchmark / 官方指标 / 我们是否
已实现（对应表 A 行）/ 官方死代码不接名单（frozen note 已核证的照抄，别重查）。

**表 C：通用候选池现状**：EM / token-F1 / BLEU / ROUGE-L / LLM-judge（binary、
rubric 两型）/ recall@k / NDCG@k / abstention 口径 / parse_failed 率——每行 =
指标 / 框架内是否已有实现或近亲（指到表 A）/ 若无，实现依赖（如 BLEU 需不需要
新第三方依赖，查 `pyproject.toml` 现有依赖一手确认）。

## 2. 硬规则
- 全部离线；每格带锚（frozen note 小节号 / 代码 文件:行号）；查不到写"来源待溯"。
- **不写任何"建议加 X 指标"**——匹配与取舍是架构师裁决（plan §2 第二步）。
- 五 benchmark 的答案形态（短语 QA/MCQ/rubric/操作级）在表 B 加一列如实标注。

## 3. 停工条件
- 发现 evaluator 注册面与 frozen note 记载矛盾（例如某官方指标 frozen note 说
  已实现但 registry 里没有）→ 停工，把矛盾清单写进施工报告。

## 施工报告（actor 填写）
（待填）
