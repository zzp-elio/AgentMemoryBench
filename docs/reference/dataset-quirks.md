# 数据集个性档案（Dataset Quirks Index）

创建：2026-07-11（用户提议：把各 dataset 的"个性"集中记录，防遗漏细节）

**安全哲学（先读这个）**：个性不靠这份文档保安全——每条个性都有三层锚：
① **冻结记录**（`ws02.6/notes/*-frozen-v1.md`，版本化，推翻须 frozen-v2）；
② **契约卡**（`docs/survey/{datasets,workflows}/`，现行行为）；
③ **回归测试**（真实数据钉死，全量 pytest 每次验收必跑）。本文档只是
跨 benchmark 的**索引**，方便一眼扫全；每条个性的最终事实源是它的锚点。
新发现的个性必须先加测试锚再登记本表。

统一约定（全 benchmark 生效）：turn 只有在数据源存在**真实 session-level 时间**时
才能继承 session 时间；统一 schema 为无 session 数据造出的包装 Session 不构成时间
来源。question time 若官方 prompt/query 需要则必须供给，但不得反向回填 message/turn
时间（见各表“时间”行）。每类问题指标分开报告（category_breakdown）；论文报告的
指标必须覆盖（spec B6 审计）。

## LoCoMo

| 个性 | 处理 | 锚 |
|---|---|---|
| 140/272 奇数 turn session | 保留不强配对 | frozen-v1 §3 |
| conv-26 的 16 个 date-only keys | 不构造 phantom session | frozen-v1 §3 |
| 4 个 empty-evidence QA | 官方 recall 特例记 1.0 + 单独计数 | locomo-recall |
| 图片 turn：caption 拼一次，URL 不下载 | adapter 契约 | A4 测试 |
| turn 无时间戳 | 继承 session 时间 | 契约卡 |
| cat1 多答案/cat3 分号截断/cat5 拒答短语 | locomo-f1 官方 parity 专属规则（勿当通用 F1） | locomo_f1.py |
| 时间：cat2 官方日期提示进 answer prompt | unified builder | A4 |

## LongMemEval

| 个性 | 处理 | 锚 |
|---|---|---|
| 1 instance = 1 question（500 独立 haystack） | 隔离空间=instance | frozen-v1 §3 |
| turn 无时间戳（只有 session date） | 继承；格式 `2023/05/30 (Tue) 23:40` | 契约卡 |
| ~8%（1,947）session 异常 role 序列 | orphan/dangling 标记不丢弃 | audit |
| 30 道 `_abs` abstention 题 | judge 专用模板路由；recall N/A | C4 测试 |
| `has_answer`/`answer_session_ids` 私有 | 全局黑名单；官方自己也 pop has_answer | validators |
| 重复 session id | 去重公开 id + original 留 metadata | adapter |
| **时间：`Current Date: {question_date}` 必须进 answer prompt** | unified builder；缺失记 warning | C3 测试 |
| gold 双粒度（session 官方字段 + turn has_answer） | evidence 公开空间映射 | C4 裁决 |

## MemBench

| 个性 | 处理 | 锚 |
|---|---|---|
| 双人称双形态：first=dict{user,agent}（1 round=1 turn）/ third=纯 str | 按人称裁剪 round/turn | D2 |
| **时间戳两种官方格式**：`time: '…'` 与 `time'…'`（加噪代码 `time{}` 格式串所致；ThirdLow 0-10k 19,285 条全无冒号） | 正则 `time:?\s*'…'` 兼容 | D2 测试 |
| **原生无任何 session 级时间字段**（trajectory 只有 tid/message_list/QA；单 tid 单 session） | `session_time=None`；统一 schema 的单 Session 只是包装，不得从首个有时 turn 派生 | membench-100k-time-ruling §4-§5 |
| **100k 是有时源 message + 无时 noise 混合流**：307,738 step 均无独立 time 字段；49,738 文本有完整 timestamp，258,000（83.84%）无 | 有完整 timestamp 才无损解析到该 `turn_time`；无则保持 None；禁止 session/question/墙钟/人造时间兜底 | membench-100k-time-ruling §2-§5 |
| 全 task type 单字母 MCQ（answer str/list 只是内容形态） | ground_truth 恒 A-D | audit §6 |
| 官方 step id 0 基 vs 公开 turn id 1 基 | evidence +1 平移到公开空间 | D4 |
| 越界 target_step_id 2 例 + 空 1 例（官方 off-by-one/缺失） | 合法保留；recall unmatched/N/A 计数 | D2/D4 |
| 官方 json_schema 强制单字母 vs 框架文本解析 | parse_failed 分开统计 | 冻结 §7 |
| 官方 prompt typo `your'conversation` | parity 保留不改 | D3 测试 |
| **时间：`(current time is {time})` 进 MCQ prompt** | `QA.time` 只公开供 query/prompt，绝不回填 ingest message | D3 + membench-100k-time-ruling §3 |
| answer LLM 参数官方不可考（benchutils 外部依赖） | 框架决定 + 如实标注 | 冻结 §7 |

## BEAM

| 个性 | 处理 | 锚 |
|---|---|---|
| `probing_questions` 是 Python 字面量串 | 必须 ast.literal_eval | E1 |
| 10M 异构：顶层 chat=list[plan-dict]，官方按 plan 顺序消费 | 10m variant 展开；pN:sM session id | E2 测试 |
| evidence 三形态（平铺/嵌套分组/带标签 dict） | 打平匹配，结构语义归 metric | E1 裁决 |
| `'--'` 非法 gold 原子 1 个 + 1M 4 conv 重复 turn id（session 从 0 重启） | any-match + 歧义/unmatched 计数，不修数据 | E4 测试 |
| 官方评测死代码（extract_facts 被覆盖；嵌入/BLEU/ROUGE 零调用） | 只实现有效评测面 | E4 裁决 |
| 官方 judge int() 截断 0.5（prompt 明定 0.5 档） | 主分 float + official_int 双轨 | E4 |
| **时间：turn/user_questions 有 time_anchor，probing question 无；官方 answer prompt 无时间槽** | 不注入（parity） | E3 测试 |
| gold 字段按 10 类异构（rubric/ideal_*/compliance_*…） | 全局私有键黑名单 | E2 |

## HaluMem（frozen-v1，2026-07-11）

| 个性 | 处理 | 锚 |
|---|---|---|
| 唯一 operation-level benchmark（提取/更新/QA per-session 交错，不可 2-phase） | 独立 runner + scope_discriminator | test_halumem_registered_prediction 主链 e2e |
| dialogue turn 带 timestamp；session 有 start/end_time；全库严格 user/assistant 交替（0 异常） | turn 时间直取 | h1-audit §1 + H2 交替性全库统计 |
| **491/1,387 session 无 `questions` 键**（缺键 ≠ 空列表）；**Long generated session 的 questions 键存在但恒空、无 memory_points**（另一形态） | 健壮读取；两形态分别有锚 | H2 真实锚（s3 缺键）+ 冻结抽查 |
| **`is_update` 是字符串 "True"/"False"**（truthy 判断必错——架构师探针曾中招，actor 停工纠正）；官方更新探针要求 =="True" 且 original_memories 非空（全库 6,244 条 "True" 全满足耦合） | 字符串精确比较 | eval_memzero.py:210-222 |
| **时间：官方 QA prompt 无 question-time 槽**（`{context}+{question}`，时间推理靠记忆时间戳） | 不注入（parity） | eval/prompts.py:1-37 |
| questions 的 `evidence` 是原生 list（两 variant 各 828 空/2,639 非空，4,651 元素全为 `{memory_content, memory_type}`，**无 turn id → 不能作 turn-level recall gold**；官方用作 QA judge 的 Key Memory Points） | recall 契约 H4 裁决（memory-point 级 or N/A） | evaluation.py:178-185 + H1 audit §3 |
| 官方 QA prompt 按 method 分五脚本，canonical=PROMPT_MEMZERO（裁决）；PROMPT_MEMOBASE 死代码（memobase 实 import MEMZERO） | unified 统一 MEMZERO；MemOS/Supermemory 官方数字有宽松 prompt 偏差须声明 | H1 裁决块 + audit §4 |
| **Long 的 1,030 个 `is_generated_qa_session=True` session 官方评测端整体跳过**（只参与 ingest 不参与提取/更新/QA 评测；两 variant 题数同为 3,467、缺 questions 键同为 491） | 框架须复现同一跳过语义 | evaluation.py:51-52（H2/H5 待测试锚） |
| memory_type 聚合官方用 integrity+update 共同 `total_num` 作两项分母（怪但如实） | H4 处理或冻结为限制 | evaluation.py:364-383 |
| question_type 6 类（Memory Boundary 828 / Basic Fact Recall 746 / Memory Conflict 769 / Generalization 746 / Multi-hop 198 / Dynamic Update 180） | category 分报 | test_halumem_qa_breakdown_reports_all_six_official_question_types |
| smoke = 固定形状零旋钮（前缀 4 session × 每 session 2 turn × QA 1 题；首 conv s3 天然缺 questions 键+首个更新探针 session，四路径免费覆盖；20 user 前缀分布 4×18/2/5） | 固定规则硬裁剪，一切 CLI 裁剪参数 fail-fast；验收口径=运行时三操作调用≥1 而非聚合桶非空 | test_halumem_medium_real_data_smoke_prefix_anchor + e2e 主链 |
| 四套官方 judge prompt 逐字（2,568/4,891/2,259/3,834 字符）；memory_type 共享分母合成指标走 evaluate_run_artifacts 钩子 | 运行时 AST parity；上游缺失 fail-fast | test_halumem_judge_prompt_parity + test_halumem_memory_type_requires_both_upstream_artifacts |
| 更新检索可能返回空 → 官方语义路由回 integrity、不进 update 分母（曾有生产 bug：空检索被双计+分母虚增，H5 停工架构师直修） | update evaluator 跳过空检索 + skipped_empty_retrieval_count；0 分母 None+计数 | evaluation.py:59-70 + test_halumem_update_skips_empty_retrieval_per_official_routing |
