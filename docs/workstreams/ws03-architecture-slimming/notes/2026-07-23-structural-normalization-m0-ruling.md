# 结构归一 M0 裁决：metric / evaluator / prompt / 文档（2026-07-23）

## 0. 改判

首批 25 格收口后的下一步由“立即接入 MemOS”改为：

> **先完成一次零评测语义变化的结构归一 M0，再接入 MemOS。**

本改判来自用户对“清理”的准确纠正：目标不是只删过时文件，而是在后五家
method 继续复制现有布局前，收敛通用内核、显式保留 benchmark 个性、统一 prompt
所有权，并把文档拆成热层索引与冷层案例。可维护性是正确性的一部分；同一公式、
同一 preflight 或同一 prompt 身份分散多份，迟早产生漂移。

本批不扩大为 runner/registry/legacy protocol 重写。M0 是有边界的结构迁移，不是
“顺便重做框架”。

## 1. 一手现状

### 1.1 Metric 与 evaluator

- `src/memory_benchmark/metrics/` 目前只有 5 行入口说明，既定的纯 metric 层尚未真正承载实现。
- 真正 benchmark/method 无关的 Recall 内核已经在
  `evaluators/retrieval_metrics.py`（174 行），说明公式去耦方向成立。
- LoCoMo、LongMemEval、MemBench、BEAM 四个 recall evaluator 分别约
  312/349/310/260 行，仍重复：
  - 三份 artifact 读取与 question-id 对齐；
  - RetrievalEvidence contract preflight；
  - valid/N/A/pending 逐题分支；
  - top-k 分布、status counts、nullable mean 与 summary 拼装。
- 四家真正不能抹平的是 gold unit/view、空 gold/abstention/no-target 政策、
  source-id projection、official/supplementary tier 与诊断字段。

所以用户判断“Recall 公式通用”是对的；但“benchmark-specific 代码应归零”不对。
正确结构是**一个通用计算/编排引擎 + 四份很薄的 benchmark policy**，而不是四套
完整 evaluator，也不是一个塞满 `if benchmark == ...` 的万能文件。

### 1.2 Prompt

现有 prompt/builder 至少散在：

- `benchmark_adapters/locomo_prompt.py`、`longmemeval_prompt.py`；
- MemBench、BEAM、HaluMem adapter 内联的 unified answer prompt；
- `evaluators/halumem_prompts.py`、LoCoMo/BEAM judge 内联 prompt；
- `methods/lightmem_native_prompts.py`（290 行）、
  `mem0_native_prompts.py`（757 行）、`memoryos_native_prompts.py`（124 行）。

这既混淆“benchmark 主表 prompt”和“method 作者校准 prompt”，也让新增 method
继续复制旧 `native` 命名。现行 TOML 政策已经裁定：主表 prompt 归 benchmark，
method 专属 prompt 只属于稀疏 author calibration；目录应表达这个所有权。

### 1.3 文档

2026-07-23 行数：

| 文件 | 行数 | 裁决 |
| --- | ---: | --- |
| `AGENTS.md` | 162 | 静态入口，体量合理，不为追求短而删硬规则 |
| `architect-onboarding.md` | 220 | 可小幅去重，但不是首要问题 |
| `architect-playbook.md` | 980 | 核心原则与详细案例混写，应拆热层/案例层 |
| `actor-handbook.md` | 255 | 当前可接受；案例继续增长时再外移 |
| ws02.7 `README.md` | 1,798 | **紧急结构债**；热恢复入口被历史压垮 |
| 根 `README.md` | 610 | 用户指南与开发参考混写，后续拆 guides，不阻塞 M0 承重代码 |

“凝练”不能删除判例。目标是**短入口 + 稳定索引 + 完整冷层**，而不是把历史经验
摘要到失去反例、证据射程和改判原因。

## 2. 目标结构

### 2.1 Pure metric 层

```text
src/memory_benchmark/metrics/
├── text.py          # normalization、EM、substring、token-F1 等纯函数
├── retrieval.py     # Recall/Precision/F1@k、top-k source diagnostics
└── ranking.py       # DCG/NDCG 等纯排序内核
```

规则：

1. 不读取 artifact、manifest、benchmark 名或 method 名；
2. 输入输出为明确的数据结构；
3. 同一公式只存在一个版本化实现；
4. “实现存在”不等于“所有 benchmark 都启用”。

### 2.2 Evaluator 层

```text
src/memory_benchmark/evaluators/
├── common/
│   ├── artifact.py   # 读盘、ID 对齐、通用 summary
│   ├── retrieval.py  # GenericRetrievalEvaluator + profile protocol
│   └── judge.py      # 通用 judge 调用/观测壳
├── benchmarks/
│   ├── locomo.py
│   ├── longmemeval.py
│   ├── membench.py
│   ├── beam.py
│   └── halumem.py
└── registry.py
```

benchmark policy 只声明：

- gold group view 与允许 provenance granularity；
- official exclusion/empty-gold 规则；
- source-id projector；
- metric tier、官方来源与 benchmark-specific details。

第一批只迁 retrieval recall orchestration；LoCoMo official F1、BEAM rubric、
HaluMem extraction/update/QA 等独特评分不因目录目标被强行通用化。

### 2.3 Prompt / builder 层

```text
src/memory_benchmark/prompts/
├── benchmarks/
│   ├── locomo.py
│   ├── longmemeval.py
│   ├── membench.py
│   ├── beam.py
│   └── halumem.py
└── author/
    ├── lightmem.py
    ├── mem0.py
    └── memoryos.py
```

- `benchmarks/` 保存主表统一 answer builder、benchmark judge prompt 与一手来源。
- `author/` 只保存 method 作者确实存在的校准 builder/prompt；新路径不再使用含混的
  `native` 命名。
- 模板和完成变量填充的 builder 归同一 ownership package；不能只移动字符串、把
  构造逻辑继续散在 adapter。
- method 内部的 extraction/update/build prompt 属产品算法，不迁入 framework prompt
  包；vendored upstream prompt 更不复制。
- 旧 import path 先保留薄 re-export shim，待旧 `config_track` 兼容面退出后再删除。

## 3. 文档热层/冷层

### 3.1 保留热层

- `AGENTS.md`：静态入口、硬规则、导航，维持约 200 行以内；
- `architect-onboarding.md`：首次上岗读序与恢复方式；
- `architect-playbook.md`：核心原则索引和常用手艺，目标约 250 行；
- ws02.7 README：当前状态、最近验收、下一动作、权威链接，目标约 200 行；
- Codex 恢复胶囊：目标不超过约 100 行，只留最近状态，不列数十个历史 commit。

### 3.2 迁入冷层

- playbook 详细判例迁到 `docs/reference/playbooks/architect-casebook/`，按主题分文件；
- ws02.7 已 superseded 的断点迁到 `docs/archive/status/` 或既有 branch notes；
- 根 README 的 CLI/config/artifact/development 细节逐步迁到 `docs/guides/`。

迁移要求：

1. 不删反例、改判原因和一手锚；
2. 原文件保留对应 heading 和跳转，尽量维持旧 anchor；
3. 索引说明“什么时候读哪一层”，避免冷层再次被默认全读；
4. 文档标准测试之外增加链接/anchor 检查。

## 4. M0 实施批次

### A. 文档热/冷分层（docs-only）

先缩 ws02.7 恢复胶囊和当前断点；再把 playbook 案例外移。AGENTS 与 actor handbook
只去明确重复，不按行数硬砍。

### B. Retrieval evaluator 共壳

把 pure kernel 迁入 `metrics/`，抽 artifact preflight/逐题资格/summary 共壳，
四家 recall 变成 policy 注册。先以现有测试和固定 artifact fixture 锁住迁移前输出，
迁移后要求 score records/summary 语义等价。

### C. Prompt ownership 归位

建立 `prompts/benchmarks` 与 `prompts/author`，迁移六个现有独立 prompt 文件及
adapter/evaluator 中的框架 prompt；旧路径保留 shim。最终比较完整
`PromptMessage[]`、profile/source identity 和 manifest，不只比较模板常量。

### D. 合流门

- 零真实 API、零 third-party 算法改动；
- 每批只做一种职责迁移，不在 move commit 中改公式/prompt 文本；
- import compatibility、artifact schema、registry metric 名和 output bytes 受测试保护；
- 定向测试 + 文档门 + compileall + 无 API 全量 pytest；
- M0 关闭后才让 MemOS 按新结构接入，避免再添旧布局。

## 5. 明确非目标

- 不在 M0 删除 `LegacyProviderBridge`、resume、`config_track`；
- 不把所有 benchmark metric 合成一个类；
- 不把 HaluMem/BEAM 等官方独特 scorer 改写成“通用 Recall/F1”；
- 不顺手实现 BLEU-1、ROUGE-L、Precision@k 等新公式；
- 不改变已冻结 25 格的 metric 资格、分母、N/A、prompt 或 artifact；
- 不用“文件更少/行数更少”代替行为等价验收。

## 6. 下一动作

先写三张相互有明确依赖的自包含 actor 卡：A（文档分层）先行；B（retrieval
共壳）与 C（prompt 归位）在 A 后可用独立 worktree 并行，架构师串行强验收并在
合流后跑全量门。任务卡写入仓库后仍由用户选择跨模型 actor 派发。
