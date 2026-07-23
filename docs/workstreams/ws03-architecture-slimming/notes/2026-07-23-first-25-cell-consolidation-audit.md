# 首批 25 格里程碑收口与架构减重审计（2026-07-23）

> **后续改判（同日）：**本文完成的事实收口与遗留分类仍有效；“收口后立即
> MemOS”的顺序已被
> [结构归一 M0 裁决](2026-07-23-structural-normalization-m0-ruling.md)
> supersede。现行顺序是：零语义变化的 metric/evaluator/prompt/文档结构归一 M0
> → MemOS。M0 不扩大到 runner/registry/legacy protocol 重写。

## 0. 架构师判词

**先做一次有边界的里程碑收口；后续顺序以顶部改判链接为准。**

理由：

1. 5 benchmark × 首批 5 method 已形成第一块完整、可回归的行为基线，正适合清掉
   会误导下一阶段的临时文字，并把结构债分类。
2. 尚有 5 个 method adapter 未接入。此时大改 registry、runner、legacy bridge 或
   tests 布局，容易在接口样本尚未齐全时抽出错误的“通用”抽象。
3. 继续无视遗留也不合理。因此本批只做**事实收口、引用盘点和安全清理**；行为性
   删除留在 ws03 分批实施，每批都以当前 25 格回归为守恒门。

下一主线顺序：

1. 本 note、四份根目录临时 Markdown 清理与文档门；
2. 结构归一 M0（不改评测语义）；
3. ws02.7 接入 MemOS；
4. 每冻结一家 method，追加一次“新增兼容债”差量盘点；
5. 10 家 method 接口样本齐全后，在昂贵 full run 之前继续实施 ws03 的深层减重；
6. ws05 成本 pilot 与全量预算申请随后推进。

## 1. 盘点范围与读数

本批只读盘点了 Git、源码、测试、文档和本地资产目录；未删除 data、models、
outputs、third-party 仓库或实验资产。

### 1.1 “工作目录大”不等于“Git 仓库大”

2026-07-23 本机读数：

| 范围 | 约占用 |
| --- | ---: |
| `third_party/` | 9.7 GiB |
| `models/` | 7.0 GiB |
| `data/` | 5.7 GiB |
| `outputs/` | 1.1 GiB |
| `docs/` | 6.9 MiB |
| `src/` | 3.8 MiB |
| `tests/` | 9.2 MiB |
| `.git/` | 77 MiB |

Git 跟踪约 2,944 个文件、约 77 MiB；对象 pack 约 36.86 MiB。工作目录的大头是
gitignored 的数据、模型、官方 benchmark/method 仓库及实验产物，并没有被整体推到
GitHub。不能为了“看起来瘦”删除复现所需的一手资产。

### 1.2 可再生本地垃圾

读数还发现约 1,799 个 cache 目录（约 235 MiB）和 37 个 `.DS_Store`（约
360 KiB）。它们可以由单独的本地 housekeeping 命令清理，但：

- 不属于架构债；
- 不进入 Git；
- 本批未获授权去碰其它本地资产，因此不在本批删除。

## 2. 四份根目录临时 Markdown 的吸收账

本批授权删除：

- `method接口特殊情况.md`
- `t.md`
- `方法参数总结.md`
- `项目细节.md`

处理原则不是把 494 行原文搬进另一份“大杂烩”，而是按“稳定结论去权威页、施工
证据留 workstream、过时推论显式淘汰”收口。

| 临时材料 | 可保留的精华 | 当前权威落点 | 不再继承的内容 |
| --- | --- | --- | --- |
| method 接口特殊情况 | role/content/time/image 的 method-specific 映射必须逐家核实；A-Mem 无 role、SimpleMem 有 speaker/time、MemoryOS 有 pair 约束 | `docs/reference/integration/{amem,simplemem,memoryos,mem0,lightmem}.md` 与 `method-integration-checklist.md` B4/B5 | LightMem/Mem0 placeholder 等未闭合猜测；旧版本接口概括 |
| `t.md` | Mem0 五格差量、HaluMem resume 修复、首批 5 method 的时间目标与强验收纪律 | ws02.7 README、Mem0 frozen note、对应 implementation notes | actor 原始回报的重复副本；把 prompt 描述误推成 pair 硬约束；已被后续裁决取代的临时判词 |
| 方法参数总结 | 参数必须由 TOML 显式选择；主表用跨 benchmark 固定 section，作者配置只做稀疏校准；answer 选择完整 builder 而非模板名 | `docs/reference/method-toml-and-answer-builder-policy.md` 与 checklist B10 | `native/unified` 硬双轨；旧 A-Mem 路径 `third_party/A-mem`；把 demo/default/论文参数混称为同一身份 |
| 项目细节 | efficiency、timeout/retry、smoke 裁剪、resume、隔离、formatted memory、retrieval evidence 都必须进入 B1-B11 | `docs/reference/method-integration-checklist.md`、各 method integration page、architect playbook §14 | 旧 30s/2 次重试、bridge sentinel 会进入 answer、items 一律缺失、HaluMem 未串行等已修复描述 |

### 2.1 已稳定继承的共同原则

1. 数据集有可信 turn time 时传 turn time；只有 session time 时可按已声明政策回落；
   缺失时间保持 `None`，不造 wall clock。
2. 原始 content 中的 place/time 不因抽取结构化字段而删除；不支持独立时间字段的
   method 才用明确、单次的文本渲染。
3. role-aware prompt 不等于 pair-required API；placeholder 只有在接口结构硬要求时
   才允许，且不得制造 “I get it” 等假数据。
4. Recall/NDCG 资格由检索后**当前 memory 的语义与 lineage**决定，不因 sidecar 记录
   “曾参与生成”就强算。
5. 主配置、作者校准、embedding、answer builder 都由 TOML/manifest 声明；旧
   `config_track` 只承担历史产物兼容，不能继续扩展成隐式策略层。
6. smoke 负责接线、隔离、artifact、错误处理和观测，不用正确率掩盖 gold 缺席；
   真实效果、成本和 resume 另有 full/pilot 门。

## 3. 历史代码分类

### 3.1 活跃代码：禁止因名字旧而删除

| 组件 | 引用结论 | 裁决 |
| --- | --- | --- |
| `TurnIngestCheckpointStore` / `runners/ingest_resume.py` | prediction runner、CLI 与 tests 均直接使用 | **活跃**；保留 |
| `BaseResumableMemorySystem` / `add_from_turn()` | Mem0 与 prediction runner 的安全 turn resume 仍可达 | **活跃兼容面**；先迁移调用方再谈删除 |
| `LegacyProviderBridge` | `--method-class` 兼容路径、runner 与等价测试仍可达 | **兼容活跃**；不得直接删除 |
| `methods/config_track.py` | CLI、evaluate、manifest 回读和历史 run cost report 仍使用 | **产物兼容活跃**；TOML 迁移完成前保留 |
| `BRIDGE_EMPTY_MEMORY_SENTINEL` | legacy bridge 仍生成，生产 runner 已在 answer 前显式剥离 | **兼容活跃**；临时草稿所称“泄漏给 answer”已过时 |

### 3.2 已确认遗留，但本批不直接删除

`BaseMemoryRetriever` 在 `src/` 中只有定义、导出和说明，没有生产调用方；它是目前
最明确的 legacy 候选。不过它仍是公开导出符号，安全删除需要：

1. deprecated 说明与一轮引用扫描；
2. 删除/迁移对应 docs 与 tests；
3. 运行 core、CLI、registered prediction 和全量回归；
4. 明确是否需要兼容一个发布周期。

因此本批只把它列为 ws03 第一张实现卡候选，不在文档收口提交里混入行为改动。

### 3.3 结构债，不是“删文件”问题

当前最大的生产文件包括 `runners/prediction.py`（约 3.2k 行）和三家超过 2k 行的
adapter；最大的测试文件超过 6k 行。它们说明职责和测试布局需要拆分，但**行数本身
不是删除证据**。ws06 的 test restructure 仍为 P2；应在行为接口齐全后按模块边界拆，
不与 MemOS 接入并行改同一承重文件。

## 4. 本批安全清理边界

### 4.1 现在执行

- 把本 note 接入 ws03 README 与 roadmap；
- 删除四份已吸收的根目录临时 Markdown；
- 不改变任何 Python、TOML、第三方源码或实验产物；
- 运行文档标准门与 whitespace 门。

### 4.2 现在不执行

- 不删除 `data/`、`models/`、`outputs/` 或 `third_party/`；
- 不删除用户其它未跟踪文件；
- 不重排 `tests/`；
- 不删除 legacy bridge/resume/config-track；
- 不以“GitHub 已有历史”为理由重写历史或 force push。

`outputs/locomo完整的正确记录`、`outputs/other` 等大目录需要单独的实验资产保留策略：
先列 run identity、是否被报告引用、是否存在远端/冷备份，再决定归档，不能按磁盘大小直接删。

## 5. 公开 GitHub 边界

远端 `zzp-elio/AgentMemoryBench` 当前是 **PUBLIC**。因此所有 tracked workstream
README、actor card、implementation note、commit message 和删除历史都可被外部看到。

对可复现 benchmark 框架而言，公开稳定 spec、裁决、source identity 与验收证据是合理的，
也能证明方法不是靠临场特判跑通。但公开不应等于“所有工作台垃圾都上仓库”：

- **应公开**：稳定 spec/policy、可复现卡片、经过脱敏的审计证据、冻结判词；
- **可公开但应归档**：已关闭支线的施工 note/card，保留审计链但不占活跃导航；
- **不得公开**：API key、私有数据、个人信息、未脱敏终端输出、付费账户细节；
- **默认不跟踪**：聊天粘贴、跨模型 scratch、临时调查草稿、data/models/outputs。

Git 中“删除文件”不会抹去历史。如果未来需要对开发过程保密，正确办法是在写入前把远端改成
private 或另设私有开发仓，而不是事后删除 Markdown。若只担心导航噪声，使用 `docs/archive/`
和活跃 README 索引即可，不需要改写历史。

## 6. 下一次 ws03 实施触发器

本 note 的旧触发条件已由顶部结构归一 M0 改判收窄 supersede；M0 只治理
metric/evaluator/prompt/文档布局。以下条件继续约束 M0 之外的深层减重：

1. MemOS 接入暴露 legacy API 对新 method 的实际阻碍；
2. 首批 10 method adapter 全部具备接口样本；
3. 进入昂贵 full/pilot 前，需要冻结统一 manifest/CLI；
4. 一项遗留已满足“零生产引用 + 兼容期裁决 + 回归清单”三条件。

第一张候选卡只处理 `BaseMemoryRetriever` 的 deprecation/removal inventory，不与
registry、CLI、evaluator 和 tests 大搬家捆成一张卡。
