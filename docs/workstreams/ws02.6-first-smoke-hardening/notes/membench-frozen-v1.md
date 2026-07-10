# MemBench benchmark frozen-v1

冻结日期：2026-07-11
冻结范围：Phase 1 MemBench trajectory-MCQ benchmark 侧（B3）
状态：通过架构师验收；未调用真实 API

## 1. 冻结结论

MemBench 已具备可复验的官方来源身份、真实数据契约（含双人称双格式的完整
剖面）、官方 MCQ prompt parity、声明式路径覆盖 smoke/resume policy、
conditional recall，以及一条 method-neutral 离线注册链路。可作为 Method
Track 的稳定测量仪器。

本结论不表示任何真实 method 的 MemBench 效果、效率、provenance 已通过；
也不授权真实 smoke/full API 运行。

## 2. 来源锁

- 官方仓库：`https://github.com/import-myself/Membench`（**一手来源 =
  bundled 论文 PDF 内嵌文本**；本地 README 无 repo 自引用。actor 初版
  填写的 ThetaReta-CN/MemBench 属编造，验收纠正，事件记录在 lock 的
  verification_method）
- 论文：arXiv 2506.21605；license：MIT（README badge 声明，仓库内无
  LICENSE 文件，如实记录）
- 本地快照：`third_party/benchmarks/Membench-main/`，无独立 git 身份，
  官方 commit 来源待溯
- 8 个正式数据文件 + bundled PDF 逐文件 SHA-256：
  [membench-source-lock.json](membench-source-lock.json)（架构师独立重算
  复核一致）；`data2test` 是官方 `MemData/` 经加噪采样的衍生物，确切采样
  参数离线不可反推（如实记录）

## 3. 数据与映射

现场全量剖面（8 文件，[membench-b3-audit.md](membench-b3-audit.md)）：
trajectory 700/900/400/1,400（0-10k）+ 140/360/80/280（100k）；**全部
task type 均为单字母 MCQ**（ground_truth 恒 A-D，分布均衡且行和=trajectory
数）；answer str/list 两态只是选项内容形态。

- 隔离空间 = trajectory（tid），1 trajectory = 1 conversation = 1 question
- 第一人称 1 dict message = 1 turn；第三人称 1 str = 1 turn；公开 turn
  id = `str(step_index+1)`（1 基）
- **时间戳两种官方格式**：带冒号（原始文本）与无冒号（官方加噪
  `load_test_data.py:57` 的 `time{}` 格式串）；0-10k ThirdLow 19,285 条
  全部无冒号——正则 `time:?\s*'…'` 兼容两态（D2 修复 + e2e 断言）
- **官方 target_step_id 为 0 基**（reverse_relocate_dict 按 enumerate
  构建）；gold `evidence` 已平移到公开 turn-id 空间（+1），官方原值留
  `metadata["target_step_id"]` 对照；evidence 随 private label 序列化在
  **顶层**（evaluator 读键位以 `evaluator_private_label_record` 为准，
  D5 停工裁决）
- 官方数据异常（合法保留）：越界 target_step_id 2 例（两规模同源
  comparative/events tid=4，=len 疑似官方 off-by-one）；空 target_step_id
  1 例（FirstHigh highlevel_rec/movie tid=25，曾令 full load 必崩，D2 修）
- 私有字段 `answer`/`ground_truth`/`target_step_id` 绝不进公开对象
  （公开泄漏扫描为验收项）

## 4. Smoke 与 resume

- `MEMBENCH_SMOKE_POLICY`：**标准 smoke = 0_10k 4 个源文件各 1 条
  trajectory**（第一人称 1 round=1 turn / 第三人称 2 turns，各 1 题）。
  依据 = 路径覆盖原则（spec §6.7）+ 冒号 bug 实证"形态差异按文件分布"；
  选择只按公开顺序不读 gold
- `--membench-sources`（first_high/first_low/third_high/third_low）=
  调试旋钮非认证口径；非 membench 传入 fail-fast；formal 传入 fail-fast；
  FULL 加载永远全量 4 源
- smoke 禁 resume/retry-failed；formal 为 conversation(=tid) 级
  checkpoint、question 级 answer checkpoint、reuse_saved_retrieval、
  evaluation_artifact_only

## 5. Answer 与 metric

- unified MCQ prompt：官方 `INSTRUCTION_FIRST` **逐字**（含官方 typo
  `your'conversation`，parity 保留；官方活跃路径无条件用 FIRST，THIRD 只
  在注释代码中）；`{memory}`=formatted_memory 原样；parity 测试运行时
  现场读官方文件
- answer LLM：跨 method 固定 `gpt-4o-mini`/role=user/temperature=0/
  `max_tokens=None`——**官方参数不可考**（answer LLM 封装在外部依赖
  benchutils，不在官方仓库），取值为框架决定并如实标注
- `membench-choice-accuracy`（主指标）：解析成功 → 与 ground_truth 字母
  精确比较；解析失败 → 判错 + `parse_failed=true` 分开统计；按 task_type
  分报由通用 category_breakdown 承接
- `membench-recall`（conditional）：turn provenance 按公开 id 空间匹配；
  session 粒度 → N/A（单 session 无结构可召回）；未声明 → N/A；越界
  gold 记 unmatched + `out_of_bounds_gold_total`；空 evidence → N/A + 计数
- `f1` 不适用（MCQ），注册面排除（断言锁定）

## 6. 实现与验收证据

Actor commits（D1/D2 cc+DeepSeek V4 Flash；D3 混合路由；D4/D5
cc+MiniMax M3）：

- `a84440e` D1 source lock + 数据剖面（验收修正：repo URL 编造纠正、
  notes 归位、audit 100k 表内矛盾修正；架构师追加官方代码两裁定）
- `46f21bb` D2 时间戳/空 evidence 修复 + 声明式 policy + 命名源轴
  （验收修正：两处 fail-fast 缺口）
- `b33544d` D3 unified prompt parity + answer 归一（验收修正：
  max_tokens 16→None；验收发现 evidence 空间 off-by-one → D4 预裁决）
- `8fcec2e` D4 choice-accuracy parity + 公开空间 evidence + conditional
  recall（零修正）
- `13d0cd8` D5 离线全链路（前置一次教科书级停工：recall 读键位与生产
  序列化不符，架构师直修 `a7055fe` 并固化"evaluator 契约测试 fixture
  必须经真实序列化函数"规矩）

架构师验收（全部亲自复跑）：

```text
D1 定向 8 passed（修正后）；D2 定向 145 + 全量 927；D3 定向 170 +
全量 988；D4 定向 55 + 全量 999；D5 精确复验 4 passed
冻结门全量回归：见 README 断点（含 compileall exit 0）
真实数据抽查：+1 平移三态（正常/越界混合/空）、str/list answer 两态、
100k limit=1 加载 1.4s、第三人称无冒号 turn_time 端到端非空
公开对象泄漏扫描：CLEAN（answer/ground_truth/target_step_id 零出现）
全程零真实 API
```

## 7. 已知限制与解冻规则

1. **官方结构化输出偏差**：官方用 `response_format=json_schema`
   （enum A-D, strict）强制单字母；本框架用自由文本 + 健壮解析替代，
   解析失败以 `parse_failed` 分开统计。真实运行报告须声明。
2. **answer LLM 参数不可考**（benchutils 外部依赖）：temperature=0/
   max_tokens=None 为框架决定，与论文数字对比时不可声称参数对齐。
3. 官方 capacity / memory-efficiency 维度未纳入 Phase 1。
4. `100k` variant 只做数据剖面 + limit=1 加载验证，未做全链路。
5. 本地快照官方 commit 来源待溯；`data2test` 与 `MemData/` 的确切采样
   参数离线不可反推。
6. 若官方源码/数据、prompt、metric 或公私边界有新一手证据推翻本记录，
   必须版本化为 `frozen-v2`（或撤销冻结），写影响分析并重跑本页验收门；
   不得在 method adapter 内悄悄加 MemBench 专用补丁。
