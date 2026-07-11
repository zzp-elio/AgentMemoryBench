# 数据集个性档案（Dataset Quirks Index）

创建：2026-07-11（用户提议：把各 dataset 的"个性"集中记录，防遗漏细节）

**安全哲学（先读这个）**：个性不靠这份文档保安全——每条个性都有三层锚：
① **冻结记录**（`ws02.6/notes/*-frozen-v1.md`，版本化，推翻须 frozen-v2）；
② **契约卡**（`docs/survey/{datasets,workflows}/`，现行行为）；
③ **回归测试**（真实数据钉死，全量 pytest 每次验收必跑）。本文档只是
跨 benchmark 的**索引**，方便一眼扫全；每条个性的最终事实源是它的锚点。
新发现的个性必须先加测试锚再登记本表。

统一约定（全 benchmark 生效）：turn 无时间戳→session 时间兜底；question
time 若官方 prompt 需要则必须供给（见各表"时间"行）；每类问题指标分开
报告（category_breakdown）；论文报告的指标必须覆盖（spec B6 审计）。

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
| **原生无任何 session 级时间字段**（trajectory 只有 tid/message_list/QA；单 tid 单 session） | session_time 100% 派生自首个带时间戳 turn | membench.py:641 |
| **100k 大量 noise 消息无时间后缀（72-96%）** | turn_time=None → session_time 兜底；**全库零时间戳 trajectory 数=0（2026-07-11 全量扫描证实兜底永不落空）** | audit §5 + 本行扫描 |
| 全 task type 单字母 MCQ（answer str/list 只是内容形态） | ground_truth 恒 A-D | audit §6 |
| 官方 step id 0 基 vs 公开 turn id 1 基 | evidence +1 平移到公开空间 | D4 |
| 越界 target_step_id 2 例 + 空 1 例（官方 off-by-one/缺失） | 合法保留；recall unmatched/N/A 计数 | D2/D4 |
| 官方 json_schema 强制单字母 vs 框架文本解析 | parse_failed 分开统计 | 冻结 §7 |
| 官方 prompt typo `your'conversation` | parity 保留不改 | D3 测试 |
| **时间：`(current time is {time})` 进 MCQ prompt** | question_time 公开供给 | D3 |
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

## HaluMem（B5 施工中，随冻结补全）

| 个性 | 处理 | 锚 |
|---|---|---|
| 唯一 operation-level benchmark（提取/更新/QA per-session 交错，不可 2-phase） | 独立 runner + scope_discriminator | #6 / 官方 eval_memzero.py |
| dialogue turn 带 timestamp；session 有 start/end_time | turn 时间直取 | B5 待锚 |
| **491/1,387 session 无 `questions` 键**（缺键 ≠ 空列表） | 健壮读取 | B5 待锚 |
| 首 session 即有 is_update 标记点（15/15，语义待官方一手判定） | H1 强制判定 | B5 待锚 |
| **时间：官方 QA prompt 无 question-time 槽**（`{context}+{question}`，时间推理靠记忆时间戳） | 不注入（parity） | eval/prompts.py:1-37 |
| question_type 6 类（Memory Boundary 828 / Basic Fact Recall 746 / Memory Conflict 769 / Generalization 746 / Multi-hop 198 / Dynamic Update 180） | category 分报 | B5 待锚 |
| smoke 三操作覆盖：19/20 user 首 session 天然全覆盖 | 最小前缀规则（默认=1，不伪造） | B5 待锚 |
