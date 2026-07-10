# LongMemEval B2 施工计划（额度友好版）

> 2026-07-10 架构师（Fable 5，接任 GPT-5.6）基于一手取证起草。协作方式沿用
> [plan-b0-b1-locomo.md](plan-b0-b1-locomo.md) §2：**actor 只施工 + 一次定向自检
> + 本地 commit 不 push；架构师负责 diff 审读、验收复跑、全量回归和冻结。**
> 每批必须等架构师验收后才派下一批。

## 1. 目标和不变边界

把 LongMemEval 整治为有官方来源锁、真实数据契约、官方 unified answer prompt、
官方 judge parity、极小 round 级 smoke 和 conversation 级 resume 的
`frozen-v1` benchmark（B2，串行序列中的第二个）。

不变边界：

- 不调用真实 API，不运行 full；
- 不改真实 method adapter 或第三方算法核心；
- 不开始 MemBench（B3）；
- 不把 answer / `answer_session_ids` / turn 级 `has_answer` 交给 provider；
- 不为 smoke 答对而挑选 history/question；
- 当前所有真实 LLM 仍为 `gpt-4o-mini`；
- actor 不自行宣布 `frozen-v1`。

## 2. 一手事实基线（架构师 2026-07-10 现场取证，勿凭记忆推翻）

### 2.1 数据形态（现场全量扫描 `longmemeval_s_cleaned.json`）

- 顶层是 **500 个独立 evaluation instance**，每个 = 1 个 question + 自带
  haystack。**没有跨 instance 共享的对话**：隔离空间 = instance
  （conversation_id ↔ question_id 一一对应，1 conversation 只有 1 question）。
- `_s` 变体每题约 53 个 session（文件 277MB）；`_m` 每题约 482 个 session
  （文件 **2.7GB**，任何全量扫描都必须流式，adapter 已用 ijson）。
- instance 字段：`question_id / question_type / question / question_date /
  answer / answer_session_ids / haystack_dates / haystack_session_ids /
  haystack_sessions`。
- **时间戳只有 session 级**（`haystack_dates` 与 session 一一对应，格式
  `2023/05/30 (Tue) 23:40`）；turn 只有 `role`+`content`（evidence session 内
  的 turn 多一个 `has_answer`）。turn 时间继承 session 时间（同 LoCoMo 先例）。
- question_type 6 类：multi-session 133 / temporal-reasoning 133 /
  knowledge-update 78 / single-session-user 70 / single-session-assistant 56 /
  single-session-preference 30。
- **30 道 abstention 题**：`question_id` 带 `_abs` 后缀，官方 judge 用专门
  模板判"是否正确识别为不可回答"。
- **异常 role 序列真实存在（约 8% session）**：23,867 个 session 中
  **1,947** 个非严格 user-first 交替（C1 验收更正：架构师初稿写 1,946 是
  算术错，23,867−21,920=1,947，actor 实测正确；子分类边界依定义而异，以
  [longmemeval-b2-audit.md](notes/longmemeval-b2-audit.md) 为准）；1,940 个
  奇数长度 session。
  → 走既定 orphan/dangling 标记决策，**不丢弃**（haystack 干扰是任务语义）。
- **私有字段**：`answer`、`answer_session_ids`（session 级 evidence）、turn 级
  `has_answer`（10,960 turns 带此键，896 True）。官方 generation 代码自己也在
  进 prompt 前 pop 掉 `has_answer`（`run_generation.py:182-183`），公私边界与
  官方一致。adapter 的 `PRIVATE_MESSAGE_KEYS` 已含这三者（`longmemeval.py:47`）。

### 2.2 官方 answer 契约（`src/generation/run_generation.py`）

- 非 CoT、无 fact-expansion 的主模板（`run_generation.py:57`）：
  `"I will give you several history chats between you and a user. Please answer
  the question based on the relevant chat history.\n\n\nHistory Chats:\n\n{}\n\n
  Current Date: {}\nQuestion: {}\nAnswer:"`
  （占位依次为 history、`question_date`、question。）
- 调用参数（`run_generation.py:360-368`）：role=user、n=1、temperature=0、
  `max_tokens=500`（非 CoT 默认 gen_length）。
- history 由 session 块拼成 `### Session {i}: / Session Date: {date} /
  Session Content:`，按日期排序；官方从 API response 读真实 usage token
  （`run_generation.py:372`，api_usage 先例）。

### 2.3 官方 judge 契约（`src/evaluation/evaluate_qa.py`）

- `get_anscheck_prompt(task, q, ans, hyp, abstention)`（`evaluate_qa.py:24-43`）
  共 **5 套模板**：
  - single-session-user / single-session-assistant / multi-session 共用一套；
  - temporal-reasoning 单独一套（**容忍天数 off-by-one**）；
  - knowledge-update 单独一套（旧信息+更新答案也算对）；
  - single-session-preference 用 **rubric** 措辞；
  - abstention（`'_abs' in question_id`，`evaluate_qa.py:101`）单独一套。
- judge 调用：role=user、n=1、temperature=0、`max_tokens=10`；
  label = `'yes' in response.lower()`（`evaluate_qa.py:113`）。
- metric = accuracy，**总体 + 按 question_type 分报**（`evaluate_qa.py:130-132`）。
  官方 metric model zoo 含 gpt-4o 与 gpt-4o-mini；论文报告用 gpt-4o，本项目
  按统一基座用 gpt-4o-mini，**差异必须写进冻结记录**。

### 2.4 现有框架缺口（对照 LoCoMo frozen-v1 的完成面）

| 项 | LoCoMo（已冻结） | LongMemEval 现状 |
|---|---|---|
| source lock | ✅ notes/locomo-source-lock.json | ❌ 无 |
| 注册 prompt_track | `unified` + builder（registry.py:556-557） | ❌ 均未设置（registry.py:558-568），实跑走 native |
| answer LLM 按 benchmark 归一 | ✅ 0/32/1 role=user | ❌ 仍按 (method,benchmark) 分叉 |
| smoke/resume 声明式 policy | ✅ LOCOMO_SMOKE_POLICY / RESUME_POLICY | ❌ 只有旧 `_build_longmemeval_smoke_dataset`（registry.py:87，round 裁剪逻辑可复用但未声明式化） |
| metric | locomo-f1（官方 parity）+ conditional recall | longmemeval-judge 已存在但**未对官方 5 模板做 parity 审计**；无 recall；无通用 f1 |
| 离线全链路测试 | ✅ test_locomo_registered_prediction.py | ❌ 无 |

### 2.5 本轮已定的新决策（用户 2026-07-10 拍板）

1. **通用 `f1` evaluator 新增**：标准 token-F1、零 benchmark 特判，作为跨
   benchmark 补充口径；`locomo-f1` 保持原名（官方 parity scorer 不改名）。
   通用 f1 在 LongMemEval 上是**非官方补充指标**，主指标是 judge accuracy，
   artifact/报告中两者必须分开标注。
2. **分类别统计**：框架 `category_breakdown`（evaluation.py:219）已通用；
   adapter 已把 question_type 填进 category（longmemeval.py:184）——B2 只需
   测试断言，不需要新代码。
3. **resume 一律 conversation 级**（这里 conversation = instance）；smoke 禁
   resume。
4. **可复现性身份 = 内容**：路径不进身份哈希（已全局修复，commit `b7599a9`）。

## 3. 施工批次

### C1：官方资产锁定 + 真实数据剖面（actor）

范围：

- 新建 `notes/longmemeval-source-lock.json`（对齐 locomo-source-lock.json 结构）：
  官方仓库 `https://github.com/xiaowu0162/LongMemEval`、本地快照
  `third_party/benchmarks/LongMemEval-main/`、两个 cleaned 数据文件的现场
  SHA-256、论文 PDF 现场哈希（不声称与官方路径字节一致）、license；
  ⚠️ 需核实本地 cleaned 变体与官方发布数据（HuggingFace）的对应关系与出处，
  查不到一手对应就在 lock 里如实写"来源待溯"，不许编造。
- 新建 `notes/longmemeval-b2-audit.md`：两个变体的现场计数（instance/session/
  turn/question_type/abstention/异常 role 分布），`_m` 用流式扫描；
- adapter `load_dataset` 的 dataset metadata 补 source identity + 实际计数
  （对齐 LoCoMo T1 做法）。

Actor 自检：

```bash
uv run pytest -q tests/test_longmemeval_conversation_adapter.py
```

### C2：benchmark-owned smoke/resume policy（actor）

范围：

- 声明 `LONGMEMEVAL_SMOKE_POLICY`/`LONGMEMEVAL_RESUME_POLICY`（对齐 T3 的
  LoCoMo 模式），旧 `_build_longmemeval_smoke_dataset` 的 round 裁剪逻辑迁入
  policy 路径；
- 默认 smoke：**第 1 个 instance、第 1 个 haystack session 的前 1 个
  round（2 turns）、该 instance 唯一的 question**。选择只按公开顺序，不读
  `answer_session_ids`/`has_answer`；答对与否不属于 smoke 成功条件；
- 奇数/assistant-first session 的 round 裁剪按"前 2 个 turn"预算截断即可，
  不强配对（orphan/dangling 标记由框架聚合层打）；
- smoke 禁 resume/retry-failed；formal 为 conversation(=instance) 级 resume；
- 未接线的裁剪轴对 longmemeval fail-fast（同 T3）。

Actor 自检：

```bash
uv run pytest -q tests/test_longmemeval_conversation_adapter.py \
  tests/test_benchmark_registry.py tests/test_main_cli.py \
  tests/test_prediction_cli.py
```

### C3：unified answer prompt + answer LLM 归一（actor）

范围：

- 新建 `benchmark_adapters/longmemeval_prompt.py`：
  `build_longmemeval_unified_answer_prompt(formatted_memory, question, ...)`
  使用 §2.2 官方非-CoT 模板；**History Chats 槽位 = provider 的
  `formatted_memory` 原样代入**（框架不重排、不截断、不二次拼 session 头；
  超长按既定规则 clamp + warning，不崩）；`Current Date` = 公开
  `question_date`（C1 需确认它在公开 Question metadata 中，缺则补入——它是
  官方 prompt 的一部分，不是 evidence）；
- registry 注册 `prompt_track="unified"` + builder；native 保留可选对照；
- answer LLM 配置按 benchmark 归一：LongMemEval 下所有 method 固定
  `gpt-4o-mini`、role=user、temperature=0、`max_tokens=500`、n=1
  （`config/settings.py` 的 (method,benchmark) 分叉对 longmemeval 收敛为
  benchmark 单键，做法对齐 LoCoMo A4）；
- 不改其他 benchmark 的 answer 设置。

Actor 自检：

```bash
uv run pytest -q tests/test_prediction_cli.py tests/test_benchmark_registry.py \
  tests/test_config_profiles.py tests/test_longmemeval_conversation_adapter.py
```

### C4：metric——judge parity 审计 + 通用 f1 + conditional recall（actor）

范围：

- **longmemeval-judge 对官方 parity 审计**：5 套模板逐字对照
  `evaluate_qa.py:24-43`；abstention 由 `_abs` 后缀路由；judge 参数
  temperature=0/max_tokens=10/role=user；label 解析 `'yes' in lower()`；
  按 question_type 分报由通用 category_breakdown 承接（加断言）。parity 已
  满足的部分不重写；
- **新增通用 `f1` evaluator**（`evaluators/f1.py`）：标准 token-F1
  （normalize：小写/去标点/去冠词/空白压缩；不做 stemming、不做任何
  benchmark 特判——LoCoMo 官方的 stemming/multi-answer/adversarial 规则留在
  `locomo-f1` 里不动）；registry `cli_name="f1"`、`metric_name="f1"`、
  supported_benchmarks = 全部 conversation-QA 减 membench（MCQ，B3 再议）；
  结果 details 标注 `framework_supplementary`（非官方口径）；
- **新增 artifact-level `longmemeval-recall`**：复用 LoCoMo A5 的 conditional
  契约（provenance=none/未声明 → N/A；声明却缺来源 → fail-fast）。
  **benchmark 侧 session/turn 双粒度 gold evidence 都提供，测不测由 method
  的 provenance 声明决定**（用户 2026-07-10 拍板：benchmark 必须提供全，
  method 可以不测）：session 粒度 gold = 私有 `answer_session_ids`；turn
  粒度 gold = evidence session 内 `has_answer=True` 的 turn，turn id 采用
  官方 corpus_id 约定 `{session_id}_{turn_index+1}`（`run_generation.py:79`）；
  method 声明 turn provenance 按 turn 评，声明 session 按 session 评，
  均无 → N/A（与 LoCoMo 的 dia_id/D<n> 双粒度对称）；
- 不运行真实 judge API（judge evaluator 测试全用 fake client）。

Actor 自检：

```bash
uv run pytest -q tests/test_longmemeval_judge.py tests/test_answer_f1.py \
  tests/test_longmemeval_retrieval_recall.py tests/test_evaluator_registry.py \
  tests/test_artifact_evaluation_runner.py
```

### C5：一条离线全链路（actor）

范围（对齐 A6 模式）：

- 新建 `tests/test_longmemeval_registered_prediction.py`：真实 registry +
  真实 `_s` 数据切片 + B0 probe + fake answer reader，跑
  `1 instance × 1 round × 1 question` 的
  ingest → retrieve → unified answer → judge(fake)/f1/recall artifact
  evaluation 全链路；
- 断言 public questions / answer prompts / predictions 无私有键
  （`answer_session_ids`/`has_answer` 重点）；prediction 的 `answer` 用
  gold/evidence/judge 窄化扫描（A6 先例）；
- 复跑既有 conversation skip / saved retrieval reuse / smoke 禁 resume 三条
  generic 测试，不重写 resume 体系；必须改 generic runner 才能通过 → 停工。

Actor 自检：

```bash
uv run pytest -q tests/test_longmemeval_registered_prediction.py \
  tests/test_prediction_runner.py::test_resume_reuses_completed_retrieval_when_answer_failed \
  tests/test_prediction_runner.py::test_resume_skips_completed_conversations_and_questions \
  tests/test_main_cli.py::test_predict_smoke_rejects_resume_and_retry_failed
```

## 4. 架构师最终冻结（不派 actor）

C1-C5 全部验收后，架构师一次性完成：

1. 更新 LongMemEval benchmark/dataset/workflow 三张 survey 卡为现行契约；
2. 写 `notes/longmemeval-frozen-v1.md`（source、mapping、prompt、metric、
   smoke、resume、artifact、known limitations——至少含：judge 模型
   gpt-4o-mini vs 论文 gpt-4o 的差异、`_m` 变体未做全链路只做数据剖面）；
3. 定向总验收 + compileall + 一次全量 pytest；
4. 真实数据抽查：abstention 题、assistant-first session、纯 assistant
   session、奇数 session、`_m` 流式加载一条；
5. 确认零真实 API、public artifact 零私有泄漏；
6. 通过后 README 标 LongMemEval `frozen-v1`，才开始写 B3 MemBench plan。

## 5. 当前断点

- 2026-07-10：plan 起草完成，基于架构师当日一手取证（§2 全部现场核实）。
- 2026-07-10 用户裁决：recall evidence **benchmark 侧 session/turn 双粒度
  都提供**，method 声明什么粒度就测什么，均无则 N/A（C4 已更新）。
- 2026-07-10（C1 已验收，actor=cc+GLM-5.2，commit `dda4487`）：source-lock
  哈希/README 引文/私有边界架构师逐项一手复核为真；"来源待溯"（本地快照
  无 git 身份）处理诚实，留给架构师联网时补。架构师直修一处：`_m` 2.7GB
  的 `read_bytes()` 整读改分块流式哈希（口径不变仍是全文件，与 lock 可比；
  裁决：**不做前缀哈希模式**——部分哈希对身份无意义）。真实数据端到端
  复核：500 题/30 abstention/source_sha256 与 lock 一致/定向测试 20 passed。
  异常 role 总数勘误为 **1,947**（架构师初稿算术错，actor 实测正确）；
  子分类口径不统一裁定为非阻塞，以 audit 文档为准。
- **C2 已开卡**：[actor-prompt-c2.md](actor-prompt-c2.md)。C3 等 C2 验收。
- 全量基线：891 passed（commit `b7599a9` 后）。
