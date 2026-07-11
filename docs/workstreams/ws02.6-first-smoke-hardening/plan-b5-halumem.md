# HaluMem B5 施工计划（额度友好版）

> 2026-07-11 架构师（Fable 5）起草。协作方式沿用 B2-B4。硬规矩全程有效：
> 外部事实附"出处文件:行号"（查不到写"来源待溯"，禁止编造）；负空间需求
> 附测试函数名清单；evaluator 契约测试 fixture 必须经真实序列化函数；
> **metric parity 审计必须核实际调用点**（签名默认值不作数）。

## 1. 目标和不变边界

把 HaluMem 整治为有官方来源锁、真实数据契约、官方三阶段（提取/更新/QA）
metric parity、**三操作路径覆盖 smoke** 和 conversation 级 resume 的
`frozen-v1` benchmark（B5，串行最后一个）。

不变边界：不调真实 API、不跑 full、私有 gold 不进公开对象、smoke 不为
答对选数据、真实 LLM 仍 gpt-4o-mini、actor 不自行宣布 frozen、**不改
operation-level runner 的交错语义**（官方 `eval_memzero.py:148-256` 已
一手核实不可 2-phase，#6 时代已按此实现并接效率观测）。

## 2. 一手事实基线（架构师 2026-07-11 现场取证 + #6 时代存量）

### 2.1 数据形态（`data/halumem/HaluMem-{Medium,Long}.jsonl`）

- Medium：20 user（=conversation），1,387 session，3,467 题；user 字段
  `{uuid, persona_info, sessions, token_cost, total_dialogue_token_length,
  total_question_count}`。
- session 字段：`dialogue / dialogue_token_length / dialogue_turn_num /
  start_time / end_time / memory_points(_count) / question(s)(_count)`；
  **491/1,387 个 session 无 `questions` 键**（缺键 ≠ 空列表，健壮读取）。
- **dialogue turn 带 `timestamp`**（+role/content/dialogue_turn）；session
  有 start/end_time——时间戳三层齐全。
- memory_points 字段：`memory_content / memory_type / is_update /
  original_memories / importance / index / event_source(部分) /
  memory_source / timestamp`。**【勘误 2026-07-11，actor 二次停工纠正
  架构师探针 bug】`is_update` 是字符串 "True"/"False"（truthy 判断必错，
  字符串 "False" 为真）**；首 session 15 个点实为全 "False"；全库
  "True" 共 6,244 条（Medium 3,122）且全部带非空 original_memories，
  官方探针要求二者同时成立（`eval_memzero.py:210-222`）——Q1 已判定。
- questions 字段：`{question, answer, evidence, difficulty,
  question_type}`；**【勘误 2026-07-11】`evidence` 是原生 list**
  （架构师此前"字符串"结论是 str() 打印伪影；全库 6,934 条全 list，
  Medium 828 空/2,639 非空）——Q2 剩余部分：非空 list 装什么、能否作
  recall gold（H1 完成 audit 时落档）。
- question_type 6 类：Memory Boundary 828 / Basic Fact Recall 746 /
  Memory Conflict 769 / Generalization & Application 746 / Multi-hop
  Inference 198 / Dynamic Update 180（category 分报维度）。
- Long variant 剖面待 H1（流式，规模未探）。

### 2.2 官方评测契约（入口）

- **交错语义（#6 已一手核实）**：`eval/eval_memzero.py:148-256`
  `process_user`——ingest session → 提取评测 → 更新探针 → 该 session 的
  QA → 下一 session；记忆累积；**不可重构为先全 ingest 再全 QA**。
- 官方 QA prompt `PROMPT_MEMZERO`（`eval/prompts.py:1-37`）=
  `{context}`（`{timestamp}: {memory}` 列表，`eval_memzero.py:125`）+
  `{question}`；**无 question-time 槽**（时间推理靠记忆时间戳，prompt
  内含相对时间换算指令）。
- ⚠️ 官方 eval 是**按 method 分脚本**（memzero/memos/memobase/
  supermemory/zep 各一份 + 各自 prompt）——unified prompt 的 canonical
  选择依据 = H1 强制判定 Q3（跨 5 脚本比对 QA prompt 是否同构；ws02.2
  当时的选择要重新核证）。
- 三阶段 metric（提取/更新/QA 的 judge prompt、聚合公式、幻觉/遗漏率
  口径）：H1 按"实际调用点"纪律逐一入册（论文指标覆盖新规矩下的
  一手清单），H4 做 parity 审计。

### 2.3 现有框架状态（存量较厚，B5 以审计为主）

- operation-level runner（唯一使用者）+ 效率观测 S1-S4（#6，807 时代
  验收，`test_halumem_operation_level_records_efficiency_observations`）；
- registry：`operation_level=True`、`prompt_track="unified"` + builder、
  variants（default medium）；
- ws02.2 时代的 adapter + evaluator 面（`halumem_common.py` 等）——
  **当时的验收标准低于现行冻结标准**，H4 全面 parity 复审；
- 缺：source lock、剖面、声明式 smoke/resume policy、论文指标覆盖清单、
  三操作路径覆盖 e2e。

### 2.4 运行时路径清单与 smoke 口径（用户拍板 2026-07-11）

运行时路径：① session ingest+提取探针；② 更新探针；③ QA 问答
（+operation-level runner 本身的 scope 机制）。

**标准 smoke = 首 conversation 的最小 session 前缀，使三操作各 ≥1 次**
（更新操作按官方语义 `is_update=="True"` 且 original_memories 非空）；
**【勘误 2026-07-11】正确语义下 Medium 前缀分布 = 4×18/2×1/5×1**（首
conversation 前缀=4，架构师此前"19/20 前缀=1"是 truthy 探针 bug 的产物），
规则确定性兜底数据变化——smoke 规模仍极小（≈4 个 session）。**不伪造探针**（伪造走自控形状，
恰好绕开真实数据怪癖——B 线全部 bug 都藏在怪癖里）。session 内部不裁
turn（用户既定：不裁也能跑通提取，smoke 只看跑通）；QA 由 runner smoke
预算裁 1 题。smoke 禁 resume；formal 为 conversation 级。

## 3. 施工批次

### H1：来源锁 + 剖面 + 三强制判定 + 论文指标清单（actor）

- `notes/halumem-source-lock.json`：官方 repo/论文（arXiv）/license 一手
  抄（README/PDF；查不到"来源待溯"）；两个 jsonl 现场 SHA-256+字节；
  快照 git 身份有则锁 commit（BEAM 判例）；
- `notes/halumem-h1-audit.md`：双 variant 全量剖面（Medium 全量/Long
  流式）：user/session/turn/题数、question_type 分布、缺 `questions` 键
  统计、memory_points 字段/类型/is_update 分布、时间戳三层格式清单、
  evidence 形态全量统计；附可复算脚本；
- **Q1（is_update 语义）**：从官方 eval 对 memory_points 的实际消费代码
  一手判定 is_update 含义（更新探针以什么为输入、首 session 全 update
  是否正常）；带 文件:行号；判不了停工；
- **Q2（evidence 形态）**：字符串是何字面量、非空时引用什么对象、是否
  可作 retrieval recall 的 gold（决定 H4 recall 契约有无/形态）；
- **Q3（canonical QA prompt）**：跨 5 个官方 eval 脚本比对 QA prompt，
  判定 unified 应采用哪份及理由（同构则任取并记录，异构则停工交裁决）；
- **论文指标清单**：从 eval 代码实际调用点 + 论文抄录三阶段全部指标
  （名称/公式/分母/聚合维度），标出现有 evaluator 已覆盖/缺口——
  论文指标覆盖审计（spec B6）在 B5 的落地；
- adapter dataset metadata 补 source identity + 实际计数。

自检：`uv run pytest -q tests/ -k halumem`（按实际文件调整并报告）。
commit message：`feat(ws02.6): lock HaluMem source identity + real data audit`

### H2：声明式 smoke/resume policy（actor，待 H1 验收）

三操作最小前缀 smoke（§2.4）+ 声明式 policy 对齐 B2-B4 模式 + 未接线
裁剪轴 fail-fast + smoke 禁 resume/formal conversation 级。

### H3：unified prompt parity + answer 归一（actor）

按 Q3 判定的 canonical prompt 逐字 parity（运行时读官方文件断言）；
answer LLM 配置一手抄/不可考项 API 默认如实标注；formatted_memory 原样
（官方 `{timestamp}: {memory}` 的排版属 method 的 formatted_memory 责任
还是框架拼装 = H3 内小裁定，倾向前者，停工点预留）。

### H4：三阶段 metric parity + recall 契约 +分类别断言（actor，B5 最重批）

提取/更新/QA 三阶段官方 judge prompt 逐字 + 聚合公式 parity（实际调用
点纪律）；幻觉/遗漏率等论文指标补齐；per-question_type breakdown 断言；
recall 契约按 Q2 结果裁定（无可用 evidence 则 N/A 记录并入冻结限制）；
fixture 经真实序列化函数。

### H5：三操作离线全链路（actor，禁改生产代码）

真实 registry + Medium 切片 + probe + fake judge/answer：断言三操作路径
都真实执行（提取探针/更新探针/QA 各 ≥1 次调用记录）、operation-level
效率观测存在、category_breakdown、三层 privacy 扫描（memory_points/
answer/evidence 零泄漏）、复跑三条 resume 契约。

### 架构师最终冻结

survey 三卡契约化、`notes/halumem-frozen-v1.md`、真实数据抽查（缺
questions 键 session、Long 流式 1 条、is_update 边界）、全量 +
compileall、dataset-quirks.md 补 HaluMem 锚点，然后 README/roadmap 标
frozen-v1 → **B6 横向总验收**。

## 4. 当前断点

- 2026-07-11：plan 起草完成；H1 历经两次停工（Q3 prompt 裁决 =
  PROMPT_MEMZERO；架构师探针 bug 勘误 = evidence 原生 list /
  is_update 字符串布尔 / smoke 前缀 4×18/2/5）。
- **H1 actor 已交付、待架构师强验收**：commit `67eb1a2`
  （codex+GPT-5.6，自检 24 passed），改动 =
  notes/halumem-source-lock.json + notes/halumem-h1-audit.md +
  adapter metadata + tests/test_halumem_adapter.py。actor 报告要点：
  Q1 落档（=="True"+original_memories 非空，eval_memzero.py:210-222）；
  Q2 = evidence 元素 {memory_content, memory_type}，4,651 条全匹配同
  user memory point，**无 turn id → 不能作 turn-level recall gold**，
  官方用于 QA Key Memory Points（evaluation.py:176-185）→ H4 需裁决
  recall 契约形态（memory-point 级 or N/A）；Q3 = 现有常量与官方
  MEMZERO 2,104 字符逐字一致（H3 将很轻）；论文指标 12/12 已有实现
  但 **12 项全部存在 judge prompt 缩写偏差（H4 修正）**，memory-type
  附加维度未完整覆盖；快照无 .git，commit 来源待溯（合规）。
- **H1 架构师强验收通过（2026-07-11）**：① lock 五字段一手复核为真
  （URL/arXiv/HF/license 与 README 现场一致；SHA-256+字节数架构师独立
  重算吻合；无 .git"来源待溯"合规）——仅 paper title 误用 README h1
  宣传副标题而非 bibtex 正式标题，架构师已修（lock 加 title_note）；
  ② audit 全部关键数字架构师独立脚本复算完全一致（两 variant 各
  3,467 题/491 缺键/evidence 4,651 元素全 `{memory_content,memory_type}`
  /3,354 同 session+1,297 前序=4,651、future/unmatched 0/is_update
  "True" 6,244）；③ Q1 路由（evaluation.py:59-70）、Q2 evidence 用途
  （evaluation.py:178-185）、memory_type 共同分母
  （evaluation.py:364-383）、Q3 五调用点+MEMOS 宽松条款（prompts.py:90）
  全部一手核证；④ 定向 24 passed、全量 **1025 passed**（与 B4 基线
  持平——H1 只在既有测试内加断言）；⑤ 验收新发现：
  **`is_generated_qa_session` session 官方评测端整体 continue 跳过
  （evaluation.py:51-52）**，Long 的 1,030 个生成 session 只 ingest
  不评测——已登记 quirks，H2/H5 须落测试锚。actor（codex+GPT-5.6）
  本批零缺陷交付。
- 当前断点：**H2 卡已开**（`actor-prompt-h2.md`），待 actor 施工。
- 全量基线：**1025 passed**。