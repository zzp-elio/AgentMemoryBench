# MemBench B3 施工计划（额度友好版）

> 2026-07-10 架构师（Fable 5）基于一手取证起草。协作方式沿用 B2：actor 只
> 施工 + 一次定向自检 + 本地 commit 不 push；架构师逐批验收、全量回归、冻结。
> 本 plan 首次应用 **smoke = 最小路径覆盖切片** 原则（spec §6.7，用户
> 2026-07-10 拍板）。

## 1. 目标和不变边界

把 MemBench 整治为有官方来源锁、真实数据契约、官方 MCQ prompt/metric parity、
**双人称路径覆盖 smoke**、命名源选择轴和 conversation 级 resume 的
`frozen-v1` benchmark（B3，串行序列第三个）。

不变边界：

- 不调用真实 API，不运行 full；
- 不改真实 method adapter 或第三方算法核心；
- 不开始 BEAM（B4）；
- 不把 `answer`/`target_step_id` 交给 provider；
- 不为 smoke 答对而挑选数据；
- 当前所有真实 LLM 仍为 `gpt-4o-mini`；
- actor 不自行宣布 `frozen-v1`。

## 2. 一手事实基线（架构师 2026-07-10 现场取证）

### 2.1 数据形态

- 数据根：`data/membench/Membenchdata/data2test/{0-10k,100k}/`，每规模 4 个
  正式文件 = **视角 × 记忆类型**（FirstAgent/ThirdAgent ×
  HighLevel/LowLevel）。variant `0_10k`（默认）/`100k` 已注册
  （`membench.py:52`）。
- 顶层结构 `{task_type: {sub_key: [trajectory]}}`；trajectory =
  `{tid, message_list, QA}`；隔离空间 = trajectory（tid）。
- **双人称 message 形态（现场抽验）**：第一人称 message 是
  `{user, agent}` dict（天然一个 round）；第三人称 message 是**纯字符串**
  （一条 = 一个 turn）。→ 用户既定决策：第一人称裁 round、第三人称裁 turn。
- QA = `{qid, question, answer, target_step_id: list, choices: {A,B,C,D}}`
  ——**MCQ**；`question`+`choices` 公开，`answer`+`target_step_id` 私有
  （target_step_id 即 step 级 evidence，是 recall 的天然 gold）。
- `data2test/数据集结构说明.md` 是较完整的二手剖面（声称全量遍历：8 文件、
  700/900/400/1400 + 140/360/80/280 条 trajectory、answer 有 str/list 两态、
  1 个越界 target_step_id、100k noise message 无时间后缀、根目录 1 个游离
  文件不属正式结构）——**D1 必须逐项一手复核，不照单采信**。

### 2.2 已实锤的 latent bug：时间戳格式不一致（本日现场量化）

`_MEMBENCH_TURN_TIME_RE = r"time:\s*'…'"`（`membench.py:498`，#7 修复）只匹配
带冒号格式。现场全量扫描 0-10k 第三人称两文件：

- `ThirdAgentDataLowLevel`：**19,285/19,285 条全部是 `time'…'` 无冒号** → 解析
  全返 None；
- `ThirdAgentDataHighLevel`：5,302/5,302 条全部有冒号。

即**官方数据自身格式不一致**，#7 只在第一人称数据上验证过。后果：第三人称
LowLevel 的 turn_time 全空，lightmem×membench 在该象限会复现 "requires
turn_time" 崩溃或静默丢全部时间。D2 修正则为 `time:?\s*'…'` 并全 8 文件
验证零漏配。

### 2.3 官方 answer/metric 契约（入口已定位，D3/D4 逐字抄）

- 官方 MCQ answer prompt：`third_party/benchmarks/Membench-main/benchmark/
  MembenchAgent.py:13-29`，两套模板（带/不带 memory 槽位），格式
  `A./B./C./D. {choice}` + "Please output the correct option … only one
  corresponding letter"；`observation` 含 `question/time/choices`。
- metric = choice accuracy（现有 `membench-choice-accuracy` +
  `normalize_membench_choice_prediction` prediction_transform，D4 对官方
  parity 审计）。
- **f1 不适用**（MCQ，用户拍板），确认注册面保持排除。

### 2.4 现有框架状态（对照冻结完成面）

| 项 | 现状 |
|---|---|
| unified prompt | 已注册 `build_membench_unified_answer_prompt` + `prediction_transform`（registry.py），**未做官方 parity 审计** |
| smoke | `_build_membench_smoke_dataset`（membench.py:359）已按源文件遍历（per_source_limit）——路径覆盖底子好；但无声明式 policy、无命名源选择轴、trajectory 内部未按人称裁 round/turn |
| resume policy | ❌ 未声明式化 |
| source lock / 数据剖面 | ❌ 无 |
| answer LLM 按 benchmark 归一 | ❌ 待查 settings.py 现状后归一 |
| recall（target_step_id evidence） | ❌ 无；conditional 契约可从 locomo/longmemeval 平移 |

### 2.5 本 benchmark 的运行时路径清单（smoke 必须全覆盖）

1. 第一人称 ingest（dict message → user/agent round 拆分）；
2. 第三人称 ingest（str message → 单 turn，含**无冒号时间格式**）；
3. HighLevel 与 LowLevel 源文件加载（两种任务结构）；
4. MCQ unified answer + prediction_transform（一次真实形态的选项解析）；
5. （100k variant 的 noise-heavy 形态属规模差异，非路径分叉，smoke 不覆盖，
   D1 剖面记录即可。）

→ 标准 smoke = **每个源文件各 1 条 trajectory**（4 条）：第一人称裁 1
round、第三人称裁前 2 turn，各 1 题。现有 per-source 遍历天然满足，需补
人称内部裁剪与声明式化。

## 3. 施工批次

### D1：官方资产锁定 + 真实数据剖面（actor）

- `notes/membench-source-lock.json`：官方仓库/论文/license 从
  `Membench-main/README.md` + LICENSE 一手抄；8 个正式数据文件 + 游离文件
  现场 SHA-256；`data2test` 与官方 `MemData/` 的对应关系一手判断，查不到
  写"来源待溯"；
- `notes/membench-b3-audit.md`：8 文件全量剖面复核 `数据集结构说明.md` 逐项
  数字（trajectory 数/task_type 分布/answer str-list 两态/越界
  target_step_id/时间格式分布含 §2.2 的无冒号统计/100k 无后缀 noise 占比），
  不一致如实记录停工上报；
- adapter dataset metadata 补 source identity + 实际计数（对齐 B2 C1 做法，
  大文件分块流式哈希）。

自检：`uv run pytest -q tests/test_membench_conversation_adapter.py`

### D2：时间戳修复 + 声明式 smoke/resume policy（actor）

- 修 `_MEMBENCH_TURN_TIME_RE` 接受可选冒号（`time:?\s*'…'`），8 文件全量
  验证：0-10k 除 noise 外零漏配、无假阳性；session_time 兜底逻辑不变；
- `MEMBENCH_SMOKE_POLICY`/`MEMBENCH_RESUME_POLICY` 声明式化（对齐 B2 C2）：
  smoke = 每源文件 1 trajectory（§2.5 路径覆盖），第一人称 1 round/第三
  人称 2 turns，各 1 题；选择只按公开顺序不读 answer/target_step_id；
- **命名源选择轴 `--membench-sources`**：值域
  `first_high,first_low,third_high,third_low`（逗号分隔，替换掉数字拼串），
  只对 membench 接线，其他 benchmark fail-fast（对齐既有轴校验模式）；
  该轴属调试旋钮，默认（全 4 源）才是认证口径；
- smoke 禁 resume/retry-failed；formal 为 conversation(=tid) 级 resume。

自检：`uv run pytest -q tests/test_membench_conversation_adapter.py
tests/test_benchmark_registry.py tests/test_main_cli.py tests/test_prediction_cli.py`

### D3：unified prompt 官方 parity + answer 归一（actor）

- 现有 `build_membench_unified_answer_prompt` 对
  `MembenchAgent.py:13-29` 官方模板**逐字审计**（memory 槽位 =
  formatted_memory 原样、question/time/choices 映射、"only one
  corresponding letter" 指令）；一致不重写，偏差逐处修正 + 逐字断言；
- answer LLM 配置按 benchmark 归一（temperature/max_tokens/role 从官方
  agent 调用一手抄，官方未显式设的项用 API 默认并记录）；
- 不改其他 benchmark。

自检：`uv run pytest -q tests/test_prediction_cli.py
tests/test_benchmark_registry.py tests/test_config_profiles.py
tests/test_membench_unified_prompt.py`（无此文件则新建）

### D4：metric parity + conditional recall（actor）

- `membench-choice-accuracy` + `normalize_membench_choice_prediction` 对官方
  判定逻辑 parity 审计（选项解析、大小写/空白容差按官方
  `remove_space_and_ent` 语义）；按 task_type 分报走通用
  category_breakdown（断言）；
- 新增 `membench-recall`（conditional，平移 longmemeval_recall 契约）：gold
  = 私有 `target_step_id` 映射到公开 turn-id 空间（step→turn 映射由
  adapter 在 GoldAnswerInfo.metadata 提供，官方 step id 作对照记录；越界
  step id 记 N/A + 单独计数，不崩）；method 声明 turn provenance 即评，
  未声明 N/A；
- f1 注册面确认排除 membench（断言）。

自检：`uv run pytest -q tests/test_membench_choice_accuracy.py
tests/test_membench_retrieval_recall.py tests/test_evaluator_registry.py
tests/test_artifact_evaluation_runner.py`

### D5：离线全链路（actor，禁改生产代码）

- 新建 `tests/test_membench_registered_prediction.py`（平移 B2 C5）：真实
  registry + 真实 0-10k 数据 + B0 probe + fake reader，跑标准 smoke 口径
  （4 源各 1 trajectory），断言：**双人称路径都被执行**（第一人称 round
  拆分 + 第三人称含无冒号时间的 turn_time 非空）、MCQ prompt 含 choices、
  prediction_transform 生效、choice-accuracy + recall artifact 评估、
  公开 artifact 无 `answer`/`target_step_id` 泄漏；
- 复跑三条既有 resume 契约测试（同 B2 C5 命令尾）。

### 架构师最终冻结（不派 actor）

survey 三卡现行契约化、`notes/membench-frozen-v1.md`、真实数据抽查
（无冒号时间 turn、str/list answer、越界 target_step_id、100k 流式 1 条）、
全量 pytest + compileall、零真实 API、零泄漏，然后 README/roadmap 标
frozen-v1，才写 B4 plan。

## 4. 当前断点

- 2026-07-10：plan 起草完成（§2 全部一手取证，含时间戳 latent bug 实锤）。
- **尚未派工**：等用户确认后开 D1 卡。
- 全量基线：923 passed（B2 冻结门）。
