# 文档治理与任务树重构设计（Docs Governance Restructure）

- 日期：2026-07-05
- 作者：Claude Code（架构师）
- 状态：draft（待用户批准）
- 执行者：Codex（按本 spec 派生的 plan 施工）

## 1. 背景与问题诊断

项目由 Codex 推进一个月后，代码质量和文档纪律整体良好（spec/plan/handoff/回归测试
习惯已建立），但文档**组织方式**存在结构性问题。2026-07-05 用户决定切换协作模式：
Claude Code 充当架构师（写 spec/plan、审查验收、把控方向与结构），Codex 充当执行者。
本 spec 是新模式下的第一个整治任务。

基于 2026-07-05 全库盘点的证据：

### 1.1 任务分支关系扁平化（核心痛点）

- `docs/archive/specs/` 24 份、`docs/archive/plans/` 22 份、
  `docs/archive/handoffs/` 60 份，全部按日期扁平堆放。主线任务派生分支、分支再派生分支
  （如 retrieve-first 主线派生出 prompt-messages 修订、answer-llm-settings、
  isolated-worker 修复等），但文件系统里看不出任何父子关系。
- 单是 retrieve-first 一条线就有 1 spec + 1 plan + 16 份 task handoff 散落在
  扁平目录中，与其他任务线的文件交错排列。
- `docs/current-roadmap.md` 的 Phase 编号（E/F/G/H/H.5/H.6/I/J/K/L/S）是时间顺序
  而非层级结构；多个 Phase 同时标注"当前"；H.5/H.6 这类插号正是分支任务没有
  独立挂载点、只能挤进线性编号的症状。

### 1.2 状态同步负担过重（四处同步）

当前规则要求每完成一个任务同步四处：`docs/current-roadmap.md` 勾选、
`AGENTS.md` 追加、`docs/task-ledger.md` 裁定、最新 handoff。后果：

- `AGENTS.md` 已膨胀到 70KB / 889 行。名义是"入口导航"，实际变成 append-only
  流水账，与 roadmap/ledger 大量重复，新上下文读入即消耗约 3 万 token。
- `docs/task-ledger.md` 作为扁平大表被迫承担"任务树"的职能（用文字描述哪个文档
  被哪个覆盖），这正是目录结构缺失层级的补偿机制。
- 同一事实写四遍，必然漂移；ledger 里已出现多处"旧文档说已修，实际状态以本表
  为准"的纠偏条目。

### 1.3 docs/ 目录语义混杂

`docs/` 下并存四类性质完全不同的内容，没有分区：

- **长期参考**：architecture.md、data-model.md、method-interface-inventory.md
  （另有近似重复的 method-interface.md）、custom-method-onboarding.md 等。
- **过程文档**：superpowers/specs、superpowers/plans、handoffs、opencode-suggestions。
- **状态文档**：current-roadmap.md、task-ledger.md。
- **调研资料**：benchmark-survey/、调研资料/（Obsidian vault）、
  dataset_structures/、evaluation_workflows/。

命名语言混杂（`docs/调研资料/`、`opencode/旧文档/`），部分改名以
"delete + untracked"形式悬在 git 工作区。

### 1.4 tests/ 扁平

52 个测试文件约 25k 行扁平放在 `tests/`，最大单文件 3019 行
（test_prediction_runner.py）。roadmap Phase L 已有"按 unit/integration/api/contract
分组"的遗留意向，未执行。

### 1.5 git 卫生

- 全仓库只有 15 个 commit，最近一次后又积压了约两周的改动未提交。
- `third_party/methods/` 新增 6 个未跟踪的 vendored 仓库，其中
  letta 309M、supermemory 274M、cognee 280M、SimpleMem 113M、MemOS 86M，
  不做策略决定就无法提交。

## 2. 目标与非目标

### 目标

1. 建立**任务树（workstream）模型**：任何任务的父子派生关系在目录和 ID 上直接可见。
2. 状态同步从"四处"收敛到"两处"：workstream 状态页 + roadmap 一行。
3. `docs/` 按"参考 / 过程 / 状态 / 调研 / 归档"分区，命名统一英文 kebab-case。
4. `AGENTS.md` 重写为 ≤100 行的静态入口（规则 + 导航），不再承担日志职能。
5. git 工作区收干净，恢复小步提交节奏。
6. 固化 Claude（架构师）/ Codex（执行者）协作流程为书面规则。

### 非目标

- 不修改任何 `src/`、`tests/` 代码逻辑（tests 目录重组是后续独立 workstream）。
- 不改变 superpowers 插件本身的使用方式，只改变产物的存放位置约定。
- 不动 `outputs/`（含受保护实验资产）、`data/`、`models/`、`third_party/benchmarks/`。
- 不重写历史文档内容；历史文档原样归档（`git mv` 保留历史），只改位置和索引。

## 3. 任务树模型（核心设计）

### 3.1 Workstream 定义

一个 workstream = 一条目标一致的任务线，拥有稳定 ID：`ws<NN>[.<M>...]-<kebab-name>`。

- 主线任务：`ws03-phase1-matrix`
- 一级分支：`ws03.1-halumem-adapter`（ID 前缀即父任务，排序天然聚簇）
- 二级分支：`ws03.1.1-halumem-judge-prompt`

**派生规则**：执行中冒出的新问题，先判断规模——

- 一次会话内能修完的小问题：不建 workstream，记入当前 workstream 状态页的
  任务清单即可。
- 需要独立 spec/plan 的：建子 workstream，ID 挂在父任务下；
  父 workstream 状态页登记子任务链接。
- 子任务膨胀到与父任务目标脱钩时：升格为新的顶级 workstream，
  原位置留一行迁移指针。

### 3.2 目录结构

物理上一级扁平（避免深层嵌套路径爆炸），逻辑层级由 ID 表达：

```text
docs/
  README.md                        # 文档地图：什么内容放哪、怎么找（≤60 行）
  roadmap.md                       # 唯一方向文档：Phase 1 目标 + workstream 索引表 + 全局约束
  reference/                       # 长期参考（随代码演进更新，无生命周期状态）
    architecture.md
    data-model.md
    method-interface-inventory.md
    custom-method-onboarding.md
    huggingface-datasets.md
    ...
  workstreams/
    ws01-docs-governance/          # 本整治任务自身即第一个 workstream
      README.md                    # 状态页（见 3.3）
      spec.md                      # 即本文档（迁移时 git mv 至此）
      plan.md
      notes/                       # 审查记录、会话交接（原 handoff 职能，作用域限本线）
    ws02-git-hygiene/
    ws03-phase1-matrix/
    ws03.1-.../
  survey/                          # benchmark-survey/ + dataset_structures/ + evaluation_workflows/ 合并
    benchmarks/                    # 7 份调研卡片 + README 模板 + meeting brief
    datasets/                      # dataset_structures 迁入
    workflows/                     # evaluation_workflows 迁入
  archive/                         # 已关闭/被覆盖的历史文档，只读
    specs/  plans/  handoffs/  opencode/  status/
```

说明：

- 旧 superpowers 文档产物目录退役。superpowers 工作流照常使用，但 spec/plan 产物
  写入对应 workstream 目录（`spec.md` / `plan.md`；同一 workstream 多份时加
  日期前缀）。
- `docs/调研资料/`（Obsidian vault，用户个人调研笔记）默认保留原位并在
  docs/README.md 登记性质；是否改名/迁移由用户决定（见 §9）。
- `opencode/` 保留为 OpenCode 通道目录，但 `旧文档/` 更名 `archive/`，
  索引规则不变。

### 3.3 Workstream 状态页（README.md）

每个 workstream 的 README.md 是**该任务线唯一的状态事实源**，固定结构：

```markdown
---
id: ws03.1
parent: ws03
status: in-progress          # draft | approved | in-progress | done | superseded
created: 2026-07-05
---
# ws03.1 HaluMem Adapter

## 目标
一句话目标 + 完成判据。

## 当前断点
恢复工作时从这里读起（替代散落的 handoff 断点）。

## 任务清单
- [x] 已完成任务（附验收证据：测试命令 + 结果）
- [ ] 待办任务

## 子任务
- [ws03.1.1-halumem-judge-prompt](../ws03.1.1-halumem-judge-prompt/) — status

## 决策记录
日期 + 用户拍板的关键决策，一行一条。
```

### 3.4 状态同步规则（替代四处同步）

任务状态只写两处：

1. 本 workstream 的 README.md（任务清单勾选、断点更新、验收证据）。
2. `docs/roadmap.md` 的 workstream 索引表——仅当 workstream 整体状态变化时
   更新那一行（新建/完成/搁置）。

`AGENTS.md` 不再逐任务更新；`docs/task-ledger.md` 完成历史使命后归档，
其"裁定"职能由各 workstream README 的状态页取代。

## 4. AGENTS.md 重写

重写为 ≤100 行静态入口，内容仅限：

1. 项目一句话定位 + Phase 1 目标（5 benchmark × 10 method）。
2. 不变的硬规则（摘自现有约束）：third_party 不改核心算法、私有数据边界、
   API 调用需显式确认、中文 docstring、受保护实验资产、不自动 commit 等。
3. 协作模式：Claude=架构师 / Codex=执行者 / OpenCode=额度空档通道，
   以及各自的产出与验收规则（见 §5）。
4. 导航：`docs/README.md` → `docs/roadmap.md` → 对应 workstream README。
5. 文档写作规则：新任务如何建 workstream、状态只写两处。

现 AGENTS.md 全文 `git mv` 至 `docs/archive/status/2026-07-04-agents-log.md`
留档，不删除任何历史信息。README.md 与 CLAUDE.md 中的路径引用同步更新。

## 5. 协作流程固化

写入 AGENTS.md 的正式流程：

```text
用户提需求
  → Claude 写 spec（workstream 目录下，status: draft → 用户批准 → approved）
  → Claude 写 plan（拆分为 Codex 可独立执行的 task，每个 task 必须含：
      改动范围、明确步骤、验收命令与期望输出，如 "uv run pytest tests/xxx -q 应 N passed"）
  → Codex 按 plan 施工，逐 task 勾选并附验收命令实际输出
  → Claude 审查：diff 对照 plan、跑回归、检查文档同步，出具审查记录（notes/）
  → 通过后小步 commit；workstream README 更新断点
```

补充规则：

- Codex 报告完成不等于任务完成；验收以 Claude 复跑的命令输出为准
  （此规则在旧 task-ledger 中已被反复验证）。
- plan 中不允许出现"酌情处理"类模糊指令；Codex 遇到 plan 未覆盖的情况，
  停下来记录到 workstream README 的"当前断点"，交回架构师，不自行发散。

## 6. 迁移计划概要（派生 plan 的骨架）

迁移拆为 4 个阶段，M1 完成后 M2/M3 可连续执行，M4 独立排期：

- **M1 git 收干净**（前置：§9 决策 1）
  按功能边界把当前脏工作区拆成小步 commit：文档更新、改名（用 git mv 归位
  delete+untracked 对）、新调研文档、vendored methods（按决策处理）。
  验收：`git status` 干净；`uv run pytest -q` 保持通过基线。
- **M2 目录迁移**
  建立 §3.2 骨架；按映射表迁移文档（active → workstream / reference / survey，
  closed/superseded → archive）。映射表由架构师在 plan 中逐文件给出，
  依据现 task-ledger 的文档状态索引。全部使用 `git mv`。
  验收：`docs/` 顶层只剩 §3.2 所列条目；全库 grep 旧路径引用清零
  （CLAUDE.md、README.md、tests/test_documentation_standards.py 等同步更新）。
- **M3 入口重写**
  重写 AGENTS.md（§4）、新建 docs/README.md 与 docs/roadmap.md
  （roadmap 由架构师起草：Phase 1 目标 + workstream 索引 + 现 roadmap 中
  仍 open 的任务收编为 workstream 或任务清单条目）。
  验收：AGENTS.md ≤100 行；三个入口互链正确；旧 roadmap/ledger 已归档。
- **M4 tests 重组**（独立 workstream，另写 spec）
  方向：按 src 分层镜像分组（core/adapters/methods/runners/evaluators/
  observability/storage/cli/analysis + api marker 目录），大文件按被测对象拆分。
  验收：重组前后 `uv run pytest -q` 通过数一致。

## 7. 顶层目录约定

已 gitignore 的本地目录（old/、tmp/、paper-make/、第三方框架参考/、
docs/调研资料/ 的 .obsidian）维持现状不入库；在 docs/README.md 的
"本地目录说明"一节登记各自性质，消除"这是不是垃圾"的判断成本。
`reports/` 中的图片文件建 `reports/assets/` 归位并规范文件名。

## 8. 验收标准（整治整体完成的判据）

1. 任意一个进行中的任务，从 `docs/roadmap.md` 出发 ≤2 跳可到达其状态页，
   且状态页能回答：目标、断点、父/子任务、验收证据。
2. 新窗口冷启动所需读入的入口文档（AGENTS.md + docs/README.md + roadmap.md）
   合计 ≤300 行。
3. `git status` 干净；`uv run pytest -q` 保持迁移前基线。
4. 全库无旧过程文档目录的存活引用（archive 内除外）。

## 9. 待用户决策

1. **vendored methods git 策略**（阻塞 M1）：新增 6 个 method 源码共约 1.1GB，
   不宜整仓入库。建议：`third_party/methods/` 中新增 6 个加入 .gitignore，
   建 `third_party/methods/MANIFEST.md` 锁定各仓库 upstream URL + commit hash，
   配下载脚本（与 third_party/benchmarks、HF data bundle 的既有处理方式一致）；
   已入库的 4 个（A-mem/LightMem/MemoryOS-main/mem0-main）维持跟踪不动。
   备选：全部 vendored methods 统一改为 manifest + 脚本管理（更一致，
   但会从 git 历史中移除已跟踪的 4 个，diff 较大）。
2. **task-ledger / handoffs 去留**：建议全部归档（历史信息不丢，职能由
   workstream 状态页承接）。备选：ledger 保留为只读裁定档案，新任务不再写入。
3. **docs/调研资料/（Obsidian vault）**：建议保留原位、登记说明；
   备选：改名 docs/research-notes/ 保持命名统一（Obsidian 链接需同步修）。
