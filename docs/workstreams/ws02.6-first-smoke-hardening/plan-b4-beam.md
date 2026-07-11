# BEAM B4 施工计划（额度友好版）

> 2026-07-11 架构师（Fable 5）基于一手取证起草。协作方式沿用 B2/B3：actor
> 只施工 + 一次定向自检 + 本地 commit 不 push；架构师逐批强验收、全量回归、
> 冻结。硬规矩全程有效：外部事实附"出处文件:行号"；负空间需求附测试函数名
> 清单；evaluator 契约测试 fixture 必须经真实序列化函数。

## 1. 目标和不变边界

把 BEAM 整治为有官方来源锁、真实数据契约（**含 10M 特殊结构的接纳**）、
官方 answer/rubric-judge parity、双结构路径覆盖 smoke 和 conversation 级
resume 的 `frozen-v1` benchmark（B4，串行第四）。

不变边界：不调真实 API、不跑 full、不开始 HaluMem（B5）、私有 gold 不进
公开对象、smoke 不为答对选数据、真实 LLM 仍 `gpt-4o-mini`、actor 不自行
宣布 frozen。

## 2. 一手事实基线（架构师 2026-07-11 现场取证）

### 2.1 数据形态（HuggingFace arrow，`load_from_disk`）

- 两个数据集目录：`data/BEAM/beam_dataset/`（splits 100K=20 / 500K=35 /
  1M=35 conv）+ `data/BEAM/beam_10M_dataset/`（10M=10 conv）。共 100 conv
  × 每 conv 10 类 × 2 题 = **2,000 questions**（对上论文）。
- record 字段：`conversation_id / conversation_seed{category,theme,title,
  subtopics} / narratives / user_profile / conversation_plan /
  user_questions[{messages,time_anchor}] / chat / probing_questions`。
- **`probing_questions` 是 Python 字面量串，必须 `ast.literal_eval`**
  （官方 README 顶部 `import ast` 即此意；json.loads 会炸——现场验证）。
- chat = list[session] of list[turn]；turn =
  `{content, id, index("s,t"), question_type, role, time_anchor}`——
  **turn 有 time_anchor**（如 `March-15-2024`）；100K 首条 3 sessions ×
  ~60 turns。
- **10M 特殊结构（用户先验核实为真）**：100K/500K/1M 同构单 plan；10M
  record 额外带 `plans` 数组 ×10，每个 plan 有**自己的**
  chat/conversation_plan/conversation_seed/narratives/user_profile/
  user_questions/plan_id。⚠️ 10M 顶层也有 chat/user_questions——顶层与
  plans 的消费关系必须从官方 `ten_milion_pipeline.py` /
  `answer_generation.py` 一手判定（E1 强制问题 Q1，勿猜）。
- license CC-BY-SA-4.0（dataset README yaml 头）；官方仓库
  `third_party/benchmarks/BEAM/`（LICENSE 文件存在，E1 一手抄）。

### 2.2 问题taxonomy 与公私边界（现场解析首条 100K）

10 类 × 每类 2 题：abstention / contradiction_resolution / event_ordering /
information_extraction / instruction_following / knowledge_update /
multi_session_reasoning / preference_following / summarization /
temporal_reasoning。

- 每题必有：`question` + `rubric`（list，judge 逐条打分）+ `difficulty`；
- gold 字段**按类型异构**：`answer` / `ideal_response` / `ideal_summary` /
  `expected_compliance` / `compliance_indicators` / `non_compliance_signs` /
  `why_unanswerable` / `key_facts_tested`…——**私有键黑名单必须按 E1 的
  全类型字段清单逐一列全**，不能只挡 answer；
- `source_chat_ids`（除 abstention 外普遍存在）= chat turn id 级
  evidence，是 recall 的天然 gold（id 空间与公开 turn id 的对应关系 =
  E1 强制问题 Q2，吸取 B3 off-by-one 教训）；
- 公开：`question`、类型（→ `category`，adapter 已填 `ability`，
  `beam.py:354`）、difficulty（待 E1 确认无泄漏语义）。probing question
  本身**无 time_anchor**（问题在对话结束后问），temporal_reasoning 的
  时间信息在 gold 里。

### 2.3 官方评测契约（入口已定位，E3/E4 逐字抄）

- 官方 answer 生成：`src/answer_probing_questions/answer_generation.py`
  （E3 逐字抄模板；存在 `chat_trunecated.json` 截断机制，语义 E1 确认）。
- 官方 metric（`src/evaluation/run_evaluation.py:49-77` 按 10 类分发到
  `compute_metrics.py` 的 `evaluate_*`）：
  - 主体：**rubric LLM judge**——逐条 rubric 打 0/1，`score/len(rubric)`
    浮点分（`compute_metrics.py:339-391` 等）；
  - **event_ordering 特殊**：语义匹配（sentence-transformers 嵌入，
    阈值 0.65）+ **Kendall τ_b 归一化 × F1** 的复合浮点分
    （`compute_metrics.py:270-308`）；
  - 另有 BLEU/ROUGE/semantic-similarity 工具函数（`:49-89`，何类使用
    E4 一手核）；
  - **evaluator 依赖嵌入模型**（`get_or_create_model`），模型名与我们
    统一基座（all-MiniLM）的关系 E4 核定并记录。
- 现有框架 `beam_rubric_judge.py`（364 行）自述"**统一用 float 修正官方
  int 截断 0.5 的 bug**"——这是一个已存在的主动偏差声明，E4 必须一手
  核证官方截断行为（文件:行号），确认后作为已声明偏差进冻结记录；
  证伪则改回。

### 2.4 现有框架缺口

| 项 | 现状 |
|---|---|
| **10M variant** | ❌ 未注册（`_VARIANT_DIR_MAP` 只有 100k/500k/1m，`beam.py:46-50`）；10M 的 plans 结构 adapter 不认识 |
| source lock / 数据剖面 | ❌ 无 |
| smoke/resume 声明式 policy | ❌ 无（prepare_beam_run 待审） |
| unified prompt | 已注册 builder（registry.py:668），**未做官方 parity 审计** |
| answer LLM 按 benchmark 归一 | ❌ 待查 settings 现状 |
| rubric judge | 已有 evaluator + category_breakdown，**未对官方 10 类 evaluate_* 逐一 parity 审计**；event_ordering 的 τ×F1 是否实现待查 |
| recall（source_chat_ids） | ❌ 无 |
| 目录指纹 | ✅ Phase A 已修（`storage/fingerprint.py` 目录聚合哈希） |

### 2.5 运行时路径清单与 smoke 口径（用户 2026-07-11 拍板 + 架构师依据）

运行时路径分叉：

1. **单 plan 结构加载**（100K/500K/1M 同构——100K 作代表，同 parser 同
   schema，规模差异非路径分叉）；
2. **10M plans 结构加载**（异构，独立数据目录 + plans 数组消费逻辑）；
3. rubric-judge 评估链（含 event_ordering 复合评分的 artifact 路径）。

→ **标准 smoke（认证口径）= 100k 取 1 conv + 10m 取 1 conv**（各裁
1 round + 1 question，选择只按公开顺序）。500k/1m 不进认证 smoke（与
100k 同 parser 同 schema；调试旋钮可选）。10M 单 conv 极大，smoke 切片
必须在 plans 消费方式判定（Q1）之后设计——若按 plan 顺序注入则裁"第 1
个 plan 的第 1 个 round"。

**每类问题指标分开报告**（用户重申，对 5 benchmark 全部生效）：BEAM 的
category=ability 已填，category_breakdown 通用承接；E5 全链路断言。

## 3. 施工批次

### E1：官方资产锁定 + 真实数据剖面 + 两个强制判定（actor）

- `notes/beam-source-lock.json`（对齐 B3 版式）：官方 repo/论文/LICENSE
  一手抄（repo URL 出处必须给文件:行号，README 无则查论文 PDF，再无则
  "来源待溯"，**禁止编造**——B3 判例）；两个 arrow 数据目录逐文件
  SHA-256 + 字节数（目录内全部 data-*.arrow/json 文件）；
- `notes/beam-e1-audit.md`：四 split 全量剖面（conv 数、per-conv session/
  turn 数分布、10 类 × 题数、rubric 条数分布、difficulty 分布、
  time_anchor 格式清单、**全类型 gold 字段清单**（私有键黑名单的依据）、
  `source_chat_ids` 空缺统计（abstention 是否恒无）；10M 的 plans 剖面
  （每 plan chat 规模、顶层 chat 与 plans[].chat 的关系实测）；
- **强制判定 Q1（10M 消费方式）**：从 `ten_milion_pipeline.py` +
  `answer_generation.py` 一手判定官方评测把 10M 的哪份 chat 喂给被测系统
  （顶层 chat？plans 逐个拼接？probing_questions 针对全局还是 per-plan？）
  ——写清 文件:行号 证据链；判定不了就停工；
- **强制判定 Q2（evidence id 空间）**：`source_chat_ids` 的值对应 chat
  turn 的哪个字段（`id`？`index`？0/1 基？跨 session 唯一性？）——全量
  验证 source_chat_ids ⊆ 对应字段值域，给出反例统计；
- adapter dataset metadata 补 source identity + 实际计数（大文件分块流式，
  arrow 目录哈希复用 `storage/fingerprint.py` 目录聚合模式）。

自检：`uv run pytest -q tests/test_beam_conversation_adapter.py`
（文件名以实际存在者为准，无则该批只交 notes + metadata 改动的定向测试）

### E2：10M variant 接纳 + 声明式 smoke/resume policy（actor，待 E1 两判定后架构师补充口径）

- adapter 注册 `10m` variant（独立数据目录 `beam_10M_dataset`，plans
  结构按 Q1 判定消费）；canonical 映射保持 conversation→session→turn；
- `BEAM_SMOKE_POLICY`/`BEAM_RESUME_POLICY` 声明式化（对齐 B3 模式）：
  标准 smoke = §2.5 双结构各 1 conv × 1 round × 1 题；smoke 禁
  resume/retry-failed；formal 为 conversation 级；未接线裁剪轴 fail-fast；
- 私有键黑名单按 E1 全类型字段清单补全 + 公开对象泄漏反例断言。

### E3：unified prompt 官方 parity + answer 归一（actor）

- 现有 `build_beam_unified_answer_prompt` 对官方 `answer_generation.py`
  模板逐字审计（formatted_memory 原样代入、question 槽位、官方截断机制
  不进框架——记忆长度是 method 责任，B2 先例）；
- answer LLM 配置按 benchmark 归一（官方参数从 `llms_config.json` /
  generation 调用一手抄；不可考项按 ws02.6 规则用 API 默认并如实标注）。

### E4：metric——rubric judge 10 类 parity + event_ordering 复合分 + conditional recall（actor）

- `beam_rubric_judge` 对官方 10 个 `evaluate_*` 逐一 parity 审计（judge
  prompt 逐字、score 聚合公式、**int 截断偏差一手核证**——确认则留
  已声明偏差 + 冻结记录，证伪则改回官方行为）；
- event_ordering：官方 τ_b 归一化 × F1（嵌入阈值 0.65）复合分的实现/
  审计；嵌入模型名与统一基座关系核定；evaluator 的 requires_api 与
  嵌入依赖如实声明；
- 新增 `beam-recall`（conditional，按 Q2 判定的 id 空间做匹配键；
  abstention 无 evidence → N/A + 计数；未声明 → N/A）；
- category_breakdown 按 10 类分报断言；`f1` 对 BEAM 的适用性裁定
  （自由文本答案，可作补充指标——按注册面现状断言或补入）。

### E5：离线全链路（actor，禁改生产代码）

- `tests/test_beam_registered_prediction.py`（平移 B3 D5）：标准 smoke
  双结构口径（100k 1 conv + 10m 1 conv），断言两条结构路径都真实执行、
  rubric judge(fake client)+recall artifact 评估、category_breakdown、
  三层 privacy 扫描（重点：rubric/ideal_*/source_chat_ids 零泄漏）；
- 复跑三条既有 resume 契约测试。

### 架构师最终冻结（不派 actor）

survey 三卡契约化、`notes/beam-frozen-v1.md`（已知偏差至少含：judge 模型
基座、int 截断裁定结果、嵌入模型、10M 消费方式判定）、真实数据抽查、
全量 pytest + compileall、零真实 API、零泄漏，然后 README/roadmap 标
frozen-v1，才写 B5 plan。

## 4. 当前断点

- 2026-07-11：plan 起草完成（§2 一手取证：10M plans 结构实探、10 类
  taxonomy 全解析、官方 metric 分发链定位、probing_questions 须
  ast.literal_eval、10M variant 未注册缺口）。用户拍板：变体全接纳；
  smoke 覆盖 100k + 10m；每类指标分开报告。
- 2026-07-11（E1 Q2 停工 → 架构师裁决，actor=codex+GPT-5.6）：actor 三项
  声明独立复核全真（1 基索引换算后）。架构师全量重扫权威数字：evidence
  原子 10,534 个、**三种形态**（平铺/嵌套分组/带标签 dict——actor 的
  1,335 计数未下钻 dict）、非法原子恰 1 个 `'--'`（10M 位置 5 EO 题 0）、
  1M 位置 4/25/32/33 turn id 跨 session 重复（150/424/206/940）；另修正
  一个形态事实：**10M 顶层 chat = list[dict]（10 个 plan 字典）**，与
  单 plan 变体不同构。裁决（B2/B3 先例第三次适用）：匹配键=公开
  turn-id 空间（现行位置复合键）；raw id → 全部匹配位置（any-match，
  歧义计数）；`'--'` 不进匹配键、unmatched 计数；三形态打平匹配、结构
  语义归 metric 层。全文见 [actor-prompt-e1.md](actor-prompt-e1.md)
  末尾裁决块。**E1 复工中**。
- 2026-07-11（**E1 强验收通过**，actor=codex+GPT-5.6，commit `56ee346` +
  架构师补强 ×1 + 收编 ×1）：
  - **lock 质量历来最高**：repo URL 一手来源 `.git/config`（README 也
    核过）、三层 license 结构化（code MIT/dataset CC-BY-SA-4.0/论文
    CC-BY-4.0 全带文件:行号）、17 文件哈希（架构师抽验 2 个一致）、
    HF revision 如实"来源待溯"。**架构师补强**：快照自带 .git → 补锁
    `local_snapshot_commit=3e12035`（五 benchmark 首个可锁代码 commit）。
  - **audit 超预期**：裁决权威数字全录；额外挖出重复 id 根因（后续
    session id 从 0 重启）与顶层/plans chat "content 相等但 id 序列
    不等"的实测。
  - **范围溢出收编**：actor 提前实现了 E2/E4 的 evidence 映射
    （`_map_evidence_turn_ids`）。架构师三案例验证后收编：正常题
    **内容级对照**（raw id 28 → `s1:t29`，1 基平移正确）、abstention
    空 evidence、重复 conv 歧义计数真实触发（8/3）。E2 卡已注明勿重做。
  - **数据源确认**（用户 2026-07-11 指令）：adapter 只加载
    `data/BEAM/`，third_party 仅作代码/prompt 事实源，未加载其数据——
    已合规，指令写进 E2 卡防回退。
  - 定向 50 passed 复现，**全量 1002 passed**。
- **E2 已开卡**：[actor-prompt-e2.md](actor-prompt-e2.md)（10M variant
  接纳 + 声明式 policy；含"跨 variant smoke 不支持则停工"的预设断点）。
- 2026-07-11（E2 预埋断点触发 → 架构师裁决）：actor 开工检查即停（23s，
  预期行为），四条证据属实（variant 单值贯穿 contracts:177/201、
  registry:565、run_prediction:437）。**裁决：认证语义 = "100k 与 10m
  两次独立 smoke 均通过"，不扩展 variant selector**——variant=独立数据集
  =独立 run 身份，混跑模糊身份；selector 子集扩展挡不住任何事故。policy
  保持单 run 语义，双结构认证定义落文档（frozen-v1），E5 用两次
  prepare/run 覆盖。裁决全文见 E2 卡末尾，actor 按此复工。
- 2026-07-11（**E2 验收通过，零架构师修正**，actor=codex+GPT-5.6，commit
  `1ba7bb3`）：4 variants 注册（含 10m）；10m 展开端到端实测（conv0 =
  100 sessions = 10 plans × 10、plan 顺序正确、session id `pN:sM` 全
  唯一、19,895 turns）；双结构 smoke 形态 100k `s1×2turns` /
  10m `p1:s1×2turns` 均带 policy metadata；私有键黑名单**全局**扩展
  （core/validators.py，BEAM 全类型 gold 字段 + 顺带加固 B2/B3 的
  evidence_turn_ids），全量回归证明零误伤；负空间测试 5 条真实。
  说明一处语义：smoke 数据集带全部 20 题，实际只答 1 题由 runner 的
  smoke 默认预算（question_limit_per_conversation=1）保证——E5 断言。
  定向 171 passed（含架构师此前验收测试合流），**全量 1007 passed**。
- 2026-07-11（**E3 验收通过，零架构师修正**，actor=codex+GPT-5.6，commit
  `08a1299`）：模板与官方 `answer_generation_for_rag` 架构师独立程序化
  比对**逐字一致**；settings 注释教科书级——temperature=0 有官方一手出处
  （`answer_generation.py:303-307` 显式传 0，架构师逐行核实）、
  role=user 依据 `long_term_memory_methods.py:639`（字符串 prompt =
  human message）、max_tokens/top_p API 默认并明写"框架决定，不冒充
  官方值"（D3 教训完全内化）；无 prediction transform 断言到位。
  定向 126 passed 复现，**全量 1017 passed**。
- **E4 已开卡**：[actor-prompt-e4.md](actor-prompt-e4.md)（B4 最重批：
  rubric judge 10 类 parity + event_ordering τ×F1 + conditional recall）。
- 全量基线：1000（B3 冻结门）→ 1002 → 1007 → E3 后 **1017**。
