# LongMemEval benchmark frozen-v1

冻结日期：2026-07-10
冻结范围：Phase 1 LongMemEval conversation-QA benchmark 侧（B2）
状态：通过架构师验收；未调用真实 API

## 1. 冻结结论

LongMemEval 已具备可复验的官方来源身份、真实数据映射、公私边界、
benchmark-owned smoke/resume/prompt/metric 契约，以及一条 method-neutral
离线注册链路。它现在可以作为后续 Method Track 的稳定测量仪器。

本结论不表示任何真实 method 的 LongMemEval 效果、效率、接口保真、
provenance 已通过；也不授权真实 smoke/full API 运行。

## 2. 来源锁

- 官方仓库：`https://github.com/xiaowu0162/LongMemEval`（MIT）；论文 arXiv
  2410.10813（ICLR 2025）
- 官方数据：HuggingFace `xiaowu0162/longmemeval-cleaned`；`_cleaned` 是
  2025/09 官方重清洗版，**替代原始发布**（README 一手引文）
- 本地快照：`third_party/benchmarks/LongMemEval-main/`——**无独立 git 身份，
  官方 commit 来源待溯**（离线不可验，需联网 read-only clone 时补）
- `s_cleaned` 277,383,467 B，SHA-256 `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`
- `m_cleaned` 2,737,100,077 B，SHA-256 `9d79e5524794a2e6900a3aa9cb7d9152c5a3e8319c9a87c25494ba1eacee495f`
- 逐文件身份：[longmemeval-source-lock.json](longmemeval-source-lock.json)

## 3. 数据与映射

现场剖面（`_s` 全量、`_m` 流式，详见
[longmemeval-b2-audit.md](longmemeval-b2-audit.md)）：500 instance /
23,867 session / 246,750 turn / 30 abstention / has_answer 键 10,960 其中
True 896 / 非严格交替 session 1,947 / 奇数 session 1,940。

- **1 instance = 1 conversation = 1 question**；隔离空间 = instance
- turn 无时间戳，继承 session `haystack_dates`
- 公开 turn id `{session_id}:t{raw_index}`（0 基）；官方 corpus_id
  `{original_session_id}_{raw_index+1}` 只作对照记录
- 异常 role session（约 8%）原样保留，orphan/dangling 由框架聚合层标记
- 私有字段 `answer`/`answer_session_ids`/`has_answer` 绝不进公开对象；
  gold 双粒度 evidence 经 `GoldAnswerInfo.evidence+metadata` 随 private
  label 序列化（不新增 artifact 通路）

## 4. Smoke 与 resume

- `LONGMEMEVAL_SMOKE_POLICY`：轴 `rounds`，默认 1 instance × 1 round
  （2 turns）× 1 question；选择不读 evidence；答对不属于 smoke 成功条件；
  其他裁剪轴 fail-fast；实测形态 1 session/2 turns（原始 550 turns）
- `LONGMEMEVAL_RESUME_POLICY`：smoke 禁 resume/retry-failed；formal 为
  conversation(=instance) 级 checkpoint、completed question 跳过、answer
  失败复用 saved retrieval、evaluation artifact-only

## 5. Answer 与 metric

- unified answer：官方非-CoT 模板**逐字**（程序化对比官方源文件字符串），
  `formatted_memory` 原样代入、不截断；`Current Date`=公开 question_date；
  LongMemEval 下所有 method 固定 `gpt-4o-mini`/role=user/temperature=0/
  `max_tokens=500`（旧 per-method 分叉 4096/2000+top_p=0.8 已消灭）
- `longmemeval-judge`（主指标）：与官方 `get_anscheck_prompt` **直接 import
  对比输出，7/7 逐字 MATCH**（5 套 task 模板 + `_abs` abstention 路由）；
  0/10/`'yes' in lower()`；per-question_type 由通用 category_breakdown 分报
- `f1`：framework 补充指标（零特判、`framework_supplementary`），非官方
  口径，报告须与 judge 分开标注
- `longmemeval-recall`：conditional——method 声明 turn/session provenance
  即按该粒度评（匹配键=公开 id 空间），未声明 N/A，声明缺来源 fail-fast；
  abstention 题 N/A 并单独计数

## 6. 实现与验收证据

Actor commits（C1 cc+GLM-5.2；C2 cc+GLM-5.2；C3-C5 codex+GPT-5.6）：

- `dda4487` C1 source lock + 数据剖面（架构师直修：2.7GB 分块流式哈希）
- `c3c5264` C2 声明式 smoke/resume policy
- `7a34087` C3 unified prompt + answer 配置归一
- `75eecda` C4 judge parity + f1 + 双粒度 recall（含停工裁决后的 adapter
  定向解冻：gold 三字段）
- `75115f2` C5 离线全链路 probe workflow

架构师验收（全部亲自复跑）：

```text
C1 定向 20 passed；C2 定向 157 passed；C3 定向 132 passed（模板程序化逐字
校验）；C4 定向 91 passed + judge 7/7 verbatim + 全量 922 passed；
C5 精确复验 4 passed in 3.15s
冻结门全量回归：923 passed, 3 deselected, 2 warnings, 4 subtests passed
compileall：exit 0
真实数据抽查：abstention（有 session evidence、turn gold 空、语义自洽）、
assistant-first / 纯 assistant / 奇数 session（raw=kept 零丢弃）、
`_m` 流式加载 1 instance（482 session/5057 turn，哈希对 lock）
公开对象泄漏扫描：CLEAN（has_answer/evidence_* /answer_session_ids 零出现）
全程零真实 API
```

过程中的两次架构师勘误（原则：错误归属清晰）：plan 初稿异常 role 总数
1,946 算术错（实为 1,947，actor 实测正确）；C4 卡初稿把官方 corpus_id 当
匹配键（未核公开 turn id 格式，裁决改为公开 id 空间匹配）。一次停工裁决
（turn gold 通路）见 [actor-prompt-c4.md](../actor-prompt-c4.md) 末尾。

## 7. 已知限制与解冻规则

1. **judge 模型偏差**：官方报告用 `gpt-4o-2024-08-06`
   （`print_qa_metrics.py:16` 锁定），本项目按统一基座用 `gpt-4o-mini`；
   真实运行报告必须声明该偏差，与论文数字对比时不可直接对齐。
2. `_m`（2.7GB）只做数据剖面 + 单 instance 流式验证，未做全链路；full
   运行前需单独评估成本。
3. ~~官方 retrieval 扩展口径（recall_all/ndcg_any/k 档位）未纳入~~
   **已由 B6.1 加法补齐（2026-07-12）**：`longmemeval-retrieval-rank`
   evaluator 覆盖官方 k=[1,3,5,10,30,50] 的 recall_any/recall_all/
   ndcg_any（公式与官方 eval_utils.py:4-29 经 3000 例复算零失配）；
   artifact 仅 top_k 条 → k>top_k 跳过不报、turn2session 视图不可算
   （官方 effective_k 越界扩张需全 corpus）。**建模决定（登记）**：
   method 返回的 memory item 可携多个 source_turn_ids，`_ranked_source_ids`
   按 rank 顺序 expand 并去重、再 `[:k]` 截断到 k 个公开 id（非 k 个
   item）——这是 artifact-only + method-neutral 下的合理口径，与
   `longmemeval-recall` 的 source-id 并集口径同源；formula 本身与官方
   数值精确等价（GC-1 公开 id 空间匹配）。conditional recall
   （单一 requested-k）仍保留，两指标并存不冲突。
4. 本地快照官方 commit 来源待溯（需联网时补进 source-lock）。
5. 真实 API 成本、效率观测完整性和回答效果尚未测量。
6. 若官方源码/数据、prompt、metric 或公私边界有新一手证据推翻本记录，必须
   版本化为 `frozen-v2`（或撤销冻结），写影响分析并重跑本页验收门；不得在
   method adapter 内悄悄加 LongMemEval 专用补丁。
