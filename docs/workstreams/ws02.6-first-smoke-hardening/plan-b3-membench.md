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
- QA = `{qid, question, time, answer, ground_truth, target_step_id: list,
  choices: {A,B,C,D}}`。**全部 task type 都是单字母 MCQ**（2026-07-10 追加
  现场核实：`ground_truth` 恒为 A/B/D/C 单字母；`answer` 是选项内容，str/
  list 只是内容形态差异，lowlevel_rec 的 choices 本身是 list-of-items，
  仍选一个字母）→ **运行时 answer 路径跨 task type 完全统一**。
  公私边界：`question`/`choices`/`time` 公开；`answer`/`ground_truth`/
  `target_step_id` 私有——adapter 已正确处理（`membench.py:5` 模块声明 +
  `:565` 校验），D1 只需断言加固。`category=question_type`（task type）
  已填（`membench.py:581`），分类别统计由通用 category_breakdown 承接。
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

### 2.5 运行时路径清单与 smoke 口径（含"为什么 4 个源文件"的裁决依据）

**代码分支意义上的运行时路径只有 3 条**：

1. 第一人称 ingest（dict message → user/agent round 拆分）；
2. 第三人称 ingest（str message → 单 turn）；
3. MCQ unified answer + prediction_transform（已核实跨 task type 统一，
   单字母；HighLevel/LowLevel 走同一 parser、同一 answer 路径）。

纯按代码分支，2 个文件（每人称 1 个）就够。**但 smoke 仍取 4 个文件，
依据是经验事实而非理论**：时间戳冒号 bug（§2.2）证明**数据形态差异按
"文件"分布，不按"人称"分布**——ThirdHigh 与 ThirdLow 同人称、同 parser，
格式却相反；若 smoke 只抽 ThirdHigh，ThirdLow 的崩溃会活到 full run。
full run 会加载全部 4 个文件，认证性 smoke 就应让**每个 full 会加载的
源文件至少过一次 parser**。边际成本 ≈ 2 条额外 trajectory（2 次 answer
调用，几分钱），期望收益是拦下已被实证存在的文件级形态炸弹——这笔账
一边倒。（若要省，该省的是 100k variant：规模差异非路径分叉，认证 smoke
默认只跑 `0_10k`。）

→ **标准 smoke（认证口径）= 0_10k 的 4 个源文件各 1 条 trajectory**：
第一人称裁 1 round、第三人称裁前 2 turn，各 1 题。现有 per-source 遍历
天然满足，需补人称内部裁剪与声明式化。

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

### D2：时间戳修复 + 空 evidence 修复 + 声明式 smoke/resume policy（actor）

- 修 `_MEMBENCH_TURN_TIME_RE` 接受可选冒号（`time:?\s*'…'`），8 文件全量
  验证：0-10k 除 noise 外零漏配、无假阳性；session_time 兜底逻辑不变
  （无冒号是官方加噪代码 `load_test_data.py:57` 的 `time{}` 格式串所致，
  见 audit 追加节）；
- 修 `_target_step_ids` 接受空列表（D1 发现：FirstHigh 0-10k 有 1 个
  `target_step_id=[]`，现行校验抛错 → **full load 必崩**；裁决：空列表 =
  无 step 证据，合法保留进 gold，recall 侧 N/A 处理归 D4）；
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
- 2026-07-10（**D1 强验收通过**，actor=cc+DeepSeek V4 Flash，commit
  `a84440e` + 架构师验收修正）：
  - **实质产出合格**：8 文件哈希与架构师独立重算逐个一致；trajectory 数、
    0-10k 时间戳分布、ground_truth 分布（行和均与 trajectory 数吻合）、
    越界 target_step_id 定位（两规模同源 comparative/events tid=4）全部
    复核为真；游离文件一节正确纠正了二手文档；停工点（空
    target_step_id → full load 必崩）为**真 latent bug**，好收获。
  - **三处架构师验收修正**：① **repo URL 编造实锤**——actor 填的
    `ThetaReta-CN/MemBench` 在本地一手材料中不存在，正确值
    `import-myself/Membench` 来自 bundled 论文 PDF 内嵌文本（lock/adapter
    已改，verification_method 记录事件）；② 两个 notes 文件放错到仓库根
    `notes/`（卡内相对路径有歧义，责任共担），已 git mv 归位；③ audit 的
    100k 三列表与自身 §5 首表自相矛盾，已用架构师逐消息复算值替换。
  - **两个官方代码一手裁定（架构师追加进 audit）**：无冒号格式 =
    官方 `load_test_data.py:57` 的 `time{}` 格式串（非数据损坏）；
    `target_step_id` 为 **0 基**（`reverse_relocate_dict` 按 enumerate
    构建），越界=len 疑似官方 off-by-one 产物。
  - 教训（弱 actor 校准）：DeepSeek V4 Flash 的数值劳动可靠（大表全对），
    但**外部事实字段（URL/出处）不可信，必须逐个一手复核**；后续给弱
    actor 的卡要求外部事实字段必须附"出处文件:行号"。
- 2026-07-10（**D2 强验收通过**，actor=cc+DeepSeek V4 Flash，commit
  `46f21bb` + 架构师直修 ×2）：
  - **五件套实质全过（架构师端到端实测）**：正则三形态 + 假阳性防御；
    full load 3400 条（=700+900+400+1400 与 audit 精确吻合）、空 evidence
    恰 1 条且位置正确；smoke 形态 = 4 源各 1 条、第一人称 1 turn（=1
    round，dict 合并单 Turn）/第三人称 2 turns、policy 进 metadata；
    `--membench-sources` 命名过滤生效；坏名字 fail-fast 报错清晰；
    定向 145 passed 复现，全量 925 passed。
  - **架构师直修两处 fail-fast 缺口**（卡明确要求但 actor 只做了 happy
    path）：① `_validate_membench_sources` 对非 membench **静默吞旗标**
    而非报错（脚枪：换 benchmark 复制命令时过滤条件无声消失）；
    ② formal 路径接受该旗标但 FULL 分支静默忽略（会误导为部分源运行）。
    两处均已改为显式报错 + 新增 2 条 CLI 回归测试。顺修 stale docstring
    （"当前只有 LoCoMo"→ 三 benchmark）。
  - FULL 分支确认**不受** sources 过滤影响（full 数据完整性无险）。
  - actor 画像补充：机械实现与数值劳动可靠，但**负空间需求（"不该发生
    的事必须报错"）会漏做**——后续卡对拒绝路径要求附带测试名清单。
- 2026-07-11（**D3 强验收通过**，actor=混合路由，commit `b33544d` +
  架构师直修 ×1）：
  - **实质全过**：模板与官方 `INSTRUCTION_FIRST` 程序化逐字一致（含
    `your'conversation` 官方 typo 的 parity 保留）；官方活跃路径**无条件用
    INSTRUCTION_FIRST**（THIRD 只在注释代码中），actor 的模板选择即官方
    parity；`benchutils.py 缺失`声明核实为真（外部依赖，不在官方仓库）；
    parity 测试运行时现场读官方文件（最强形式）；负空间测试清单 10 条全
    真实存在；定向 170 passed 复现。
  - **架构师直修一处**：`max_tokens=16` 违反"官方未设→API 默认"规则
    （"MCQ 评测标准"是发明的权威），且有实质公平性危害——小上限截断非
    顺从模型的回答使字母无机会出现被判错。改 `max_tokens=None` + 注释
    重写为如实标注（官方参数不可考的三项均为框架决定）。
  - **官方结构化输出偏差（记入冻结 known limitations）**：官方 agent 用
    `response_format=json_schema`（enum A-D, strict）强制单字母
    （MembenchAgent.py:93-112），本框架用自由文本 + 健壮解析替代。
  - **新 latent bug 实锤（架构师验收时发现，D4 预裁决）**：公开 turn id
    1 基（`membench.py:706`）vs gold evidence 存官方 0 基原值（`:779`），
    不在同一 id 空间——recall 若直接匹配将系统性偏一位。裁决沿用
    LongMemEval C4 先例：evidence 改公开空间（+1），官方原值留 metadata。
- 2026-07-11（**D4 验收通过，零架构师修正**，actor=cc+MiniMax M3，commit
  `8fcec2e`）：预裁决被精确执行——真实数据三态复核（raw [119]→evidence
  ["120"] 且 ⊆ 公开 turn ids；越界样本实为"[98,111] 混合 case"，"99" 有效
  "112" 越界，处理正确；空样本保持空）；recall 契约结构对位（session→
  N/A 带理由、conditional fail-fast、越界单独计数）；parse_failed 口径
  分离注释诚实标注官方 json_schema 出处；负空间清单 10 条全真实。
  定向 55 passed 复现，**全量 999 passed**。B3 首个无需修正的批次。
- **D5 已开卡**：[actor-prompt-d5.md](actor-prompt-d5.md)，最后一个 actor
  批次；之后架构师做最终冻结。
- 全量基线：923（B2 冻结门）→ D2 后 927 → D3 后 988 → D4 后 **999**。
