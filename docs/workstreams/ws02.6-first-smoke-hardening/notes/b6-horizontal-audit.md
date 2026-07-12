# B6 五套契约横向互查（B6.4，2026-07-12 架构师亲自）

> 对象：五份 frozen-v1 记录 + quirks 索引 + 代码/测试实况。方法：逐项
> 一手核对（文件:行号），发现的不一致按"加法修 / frozen-v2 候选"分流。
> 结论先行：**六项互查全部完成，3 处加法修复，零 frozen-v2 候选**，
> 全量回归 1058 passed + compileall 通过（修复后复跑）。

## 1. quirks 表逐行核锚

- 具名测试锚全部存在（`test_halumem_qa_breakdown_reports_all_six_official_question_types`、
  `test_halumem_medium_real_data_smoke_prefix_anchor`、
  `test_halumem_judge_prompt_parity`、
  `test_halumem_memory_type_requires_both_upstream_artifacts`、
  `test_halumem_update_skips_empty_retrieval_per_official_routing`、
  `test_membench_extracts_embedded_turn_time_and_session_fallback` 等
  grep 实存）；批次代号锚（A4/C3/C4/D2-D5/E1-E4）对应冻结记录与卡均在
  `notes/` 与 workstream 目录。
- 抽跑：7 文件锚电池 77 passed；全量 1058 passed（修复后）。
- **发现一处描述不准（已修成真）**：LongMemEval 行 `has_answer` 的
  处理写"全局黑名单"，实际此前只在 adapter 本地私钥集
  （`longmemeval.py:57`），全局 `PRIVATE_KEY_NAMES` 缺失——已加法补进
  全局清单（见 §4），quirks 行现为准确描述。

## 2. 五冻结记录横向一致性

**smoke 认证口径**（无矛盾；共同不变量 = 选择不读 gold、答对不属于
成功条件、smoke 禁 resume/retry-failed）：

| benchmark | 认证形状 | 特殊口径 |
| --- | --- | --- |
| LoCoMo | 1 conv × 1 round(2 turns) × 1 题 | — |
| LongMemEval | 1 instance × 1 round × 1 题 | 隔离空间=instance |
| MemBench | 0_10k 4 源各 1 tid × 各 1 题 | 路径覆盖原则（双人称双格式） |
| BEAM | 100k + 10m 双结构各 1 conv × 1 round × 1 题 | variant=独立 run 身份 |
| HaluMem | 固定形状 4 session × 2 turn × 1 题，零旋钮 | 验收口径=三操作运行时调用≥1（原则 #13） |

**resume 契约**：五家全部 conversation 级 checkpoint + question 级
answer checkpoint/completed 跳过 + evaluation artifact-only；HaluMem
附加 operation-level 交错语义（官方顺序不可 2-phase）。互不矛盾。

**prompt parity 方法两代并存（登记，非矛盾）**：早期
locomo/longmemeval 用"程序化逐字对比官方字符串"（C3：直接 import 官方
函数对比输出），后期 membench/beam/halumem 用"运行时读官方文件/AST
断言"。两代都锚定官方一手源，效力等价；方法统一归 ws03 evaluator
通用化时顺带（原则 #15：冻结期不动，只登记）。

**answer 归一五行表**（代码现场核证 `config/settings.py:245-318`，与
五份冻结记录、plan-b6 §4 预期完全一致；role 全部 user、model 全部
gpt-4o-mini）：

| benchmark | temperature | max_tokens | top_p | 出处性质 |
| --- | --- | --- | --- | --- |
| locomo | 0.0 | 32 | 1.0 | 官方（gpt_utils.py:283-289） |
| longmemeval | 0.0 | 500 | None | 官方（run_generation.py:360-368） |
| membench | 0.0 | None | None | 框架决定（官方 benchutils 不可考，已标注） |
| beam | 0.0 | None | None | temp 官方（answer_generation.py:303-307），余框架决定 |
| halumem | None | None | None | API 默认（官方 llms.py:25-31 环境变量 gate，已标注） |

## 3. question-time 盘点复核（五行表，全有锚）

| benchmark | question-time 处理 | 锚 |
| --- | --- | --- |
| LoCoMo | cat2 官方日期提示进 answer prompt | A4 测试（quirks 行） |
| LongMemEval | `Current Date: {question_date}` 必须进 prompt | `test_longmemeval_registered_prediction.py`（断言 prompt 含 `Current Date: {question_time}`，本次互查现场目验） |
| MemBench | `(current time is {time})` 进 MCQ prompt | D3 测试 |
| BEAM | 官方 answer prompt 无时间槽 → 不注入（parity） | E3 测试 |
| HaluMem | 官方 QA prompt 无 question-time 槽 → 不注入 | eval/prompts.py:1-37 + H3 parity 测试 |

## 4. 全局私有键黑名单覆盖抽验（发现 3 缺口，已加法补齐）

逐 benchmark gold 字段对照 `core/validators.py PRIVATE_KEY_NAMES`：

- LoCoMo：answer/evidence/judge_label ✓
- LongMemEval：answer/answer_session_ids ✓；**`has_answer` 缺失 →
  已补**（此前仅 adapter 本地集 longmemeval.py:57 兜底）
- MemBench：answer/ground_truth/target_step_id ✓
- BEAM：rubric/ideal_*/compliance_indicators/source_chat_ids 等 10 类 ✓
  （E2 加固时已入全局）
- HaluMem：answer/evidence ✓；**`memory_points`（Session.private_metadata
  通道，halumem.py:392-402）与 `session_memory_points`
  （GoldAnswerInfo.metadata，halumem.py:484）缺失 → 已补**

三键加入后全量 1058 passed = **无任何公开对象携带这些键**（无既存
泄漏，此修复纯属第 3 层防护补强）。

## 5. category_breakdown 五家全生效断言清单

| benchmark | 端到端锚（summary 含 category_breakdown） |
| --- | --- |
| LoCoMo | `test_locomo_registered_prediction.py`（**本次加法补锚**：f1 summary breakdown 断言） |
| LongMemEval | `test_longmemeval_registered_prediction.py`（**本次加法补锚**：f1 summary breakdown 断言） |
| MemBench | `test_membench_registered_prediction.py`（task_type 两类分组断言） |
| BEAM | `test_beam_registered_prediction.py` + `test_beam_rubric_judge.py` |
| HaluMem | `test_halumem_registered_prediction.py` + `test_halumem_evaluators.py`（六 question_type） |

补锚前 locomo/longmemeval 的链路两环各有测试（adapter 设 category +
通用 breakdown 单测），但缺端到端直接锚——与其余三家不对齐，现已对齐。

## 6. 不一致处置汇总

**加法修复（3 处，架构师直修，全量 1058 复跑通过）**：
① locomo 端到端 breakdown 锚；② longmemeval 端到端 breakdown 锚；
③ 全局黑名单补 has_answer/memory_points/session_memory_points。

**登记不动（非行为项）**：prompt parity 两代方法统一 → ws03；locomo
judge 非逐字 lightmem 偏差 + lightmem profile → R0 前置包（见
judge-config-audit.md §3/§5）。

**frozen-v2 候选：零。**

**B6.3 附记**：匹配键契约已升格为 spec 通用契约 GC-1（spec.md B6 节
后新增）；架构师裁定**不进 playbook §3**——它是域契约不是架构师手艺，
落 spec + quirks 锚即可，playbook 原则以工作方法为限。
