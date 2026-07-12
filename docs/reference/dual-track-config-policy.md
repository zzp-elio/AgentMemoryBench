# 双轨配置政策（unified / native）

> 长效参考文档。2026-07-12 由架构师（Opus 4.8）与用户（zzp）碰撞后成文；
> 老师 2026-07-12 拍板"每个 method 既能用框架配置跑、也能用它自己的配置跑"。
> 本文是双轨的**唯一政策事实源**；`method-integration-checklist.md` B10 引用本文，
> 各 method 的 ws02.x plan 只记"逐格应用结果"，不重述政策。

## 0. 两轨定义

| 轨 | 别名 | 目的 | 配置来源 |
|----|------|------|----------|
| **unified**（轨1） | 框架配置轨 | method 之间**公平横向对比**（同一把尺子量所有 method） | 框架统一的 answer/judge/embedding + **method 自己的 repo 默认超参** |
| **native**（轨2） | 论文复现轨 | 复现该 method **paper 报告的数字**（对齐论文，做校准） | method 官方复现实验的 answer/judge/embedding/超参 |

**公平 ≠ 超参也相同**。unified 的"公平"指**读出层**（answer LLM/prompt、judge
LLM/prompt、embedding）对所有 method 一致；method 的**内部超参**（top_k、chunk、
summary 开关…）无法归一，各 method 用自己的 repo 默认即可。所以
unified = { 全局共享读出层 } × { 各 method 的 repo 默认内部超参 }。

## 1. 双轨"归根结底是不是 toml 的修改"？——是声明层，不是全部

用户判断"双轨归根结底是 toml 的修改"**对了一半，且错的那一半正是工程量所在**。

- **TOML 能收敛的**：选哪个 embedding、选哪个 answer LLM+参数、选哪个 judge
  LLM+参数、选哪个 answer/judge prompt profile（按**名字**引用）、选哪套内部超参。
  这些是**声明/选择**，确实收敛到一个可一键切换的 TOML bundle。
- **TOML 收敛不了、必须写代码 + parity 锁的**：
  1. **native prompt 本身是代码资产**（builder 函数），不是配置字符串。TOML 只能
     按名字**引用**它，内容得先一手抄进框架 + 逐字 parity 测试（M0-1 卡 Task 2
     就是在造这个资产）。
  2. **judge 语义是代码**：locomo 的 cat5 跳过、longmemeval 的 abstention 门控，
     是 evaluator 里的分支逻辑，TOML 选得中 profile、实现不了语义。
  3. **track 感知的 run_id / artifact 路由是 runner 代码**：
     `{method}/{benchmark}/{mode}/{track}/{run_id}`，让两轨产物不互撞、可分别 resume。
  4. **有些超参藏在 method 库内部**，TOML 够不着，要 adapter 把它暴露成旋钮才可控。

**正确心智模型**：`profile = 代码资产（prompt/judge 语义/超参暴露）+ TOML 绑定`。
TOML 是最后一公里的**绑定**，不是全程。每条 native 轨 = 一次性的"抽取代码资产 +
parity 锁 + run_id 路由"工程，之后才是 TOML 一键切换。

## 2. 配置差异的完整轴清单 + build/readout 二分（成本关键）

两轨之间**能**不同的轴（用户列了 3 条，实为 7 条）：

| # | 轴 | 类型 | 影响面 |
|---|-----|------|--------|
| 1 | answer LLM（model+temp+max_tokens+top_p） | 配置 | **readout** |
| 2 | answer prompt | **代码资产** | **readout** |
| 3 | judge LLM（model+参数） | 配置 | **readout** |
| 4 | judge prompt | **代码资产** | **readout** |
| 5 | judge 语义（cat5 跳过 / abstention 门控） | **代码** | **readout** |
| 6 | embedding model | 配置 | **build** |
| 7 | method 内部超参（top_k/chunk/summary 开关…） | 配置（部分藏库内） | **build**（多数） |

**build-affecting vs readout-affecting 二分是成本命门**：
- **readout 轴（1-5）**：只影响"取回记忆后如何生成答案/如何判分"。改这些**不用重建
  记忆**——同一份记忆库跑两次 readout 即可。**便宜**。
- **build 轴（6-7）**：影响"记忆怎么建、怎么存、怎么检索"。改这些**必须重建记忆**，
  两轨各建一份 → **构建成本 ×2**。**贵**。

**推论（改正此前口径）**：此前架构师说"native 只重跑 answer+judge、记忆能复用"
**只在 build 轴两轨相同时成立**。一旦 native 的 embedding 或内部超参 ≠ unified
的 repo 默认，记忆无法复用，是两次完整构建。**记忆复用是有条件的，不是默认的。**
逐 method 在 M 阶段核 build 轴是否分叉，再定成本。

## 3. 轨1（unified）配置来源政策

- **answer/judge/embedding = 框架统一配置**（method-neutral，所有 method 同一套）。
- **method 内部超参 = 官方 repo 默认**（**非** paper、**非** benchmark 专用调参、
  跨全部 benchmark 同一套）。这是 ws02.5 已锁政策，见 `docs/roadmap.md` 全局约束
  与 `ws02.5-method-interface-audit/README.md` "超参数政策"。用户 2026-07-12 的
  "轨1 走 repo 默认超参"判断与既有锁定**一致**，非新决定。
- **"repo 默认"要操作化**：= "不加任何特殊 flag、开箱即用"的那套。它本身要一次
  **每-method 小审计**——LightMem 的 `--enable-summary` `store_true` 默认 False
  就是判例（Task 1 的核查本质是"repo 默认到底是哪套"）。

## 4. 轨2（native）配置来源决策树

对每个 `method × benchmark` 的 native 格，按优先级定配置来源：

1. **method 官方有该 benchmark 的复现/eval 目录** → 那就是 native 源
   （SimpleMem/simplemem/evolver、MemoryOS-main/eval、mem0-main/memory-benchmarks
   均属此类）。**但必须过 §5 的一致性检查。**
2. **复现目录与 paper 冲突，且作者有明确指引** → follow 作者（MemoryOS：作者在
   GitHub issue 回应"推荐用论文超参" → MemoryOS native 用论文超参；记录 issue 链接）。
3. **复现目录与 paper 冲突，且 method 已明显进化过 paper（paper 数字已不可复现）**
   → 用 repo 当前的 eval/benchmarks 目录配置（作者当前背书的），显式记录"paper 已
   被 repo 取代、原论文数字不追求复现"。mem0（早期论文已进化）、memgpt→letta（已
   改名重构）属此类：用 `mem0-main/memory-benchmarks` 当前 eval harness，**不看老论文**。
4. **该 benchmark 根本没有专用配置目录** → **native ≡ unified，单轨**（见 §6），
   不臆造 native。

**触发点是"可复现性"，不是"论文新旧"**。老 ≠ 一定弃 paper；关键是"当前 vendored
代码 + 任一配置能否复现 paper 报告的数字"。判据落到证据，不落到年份。

## 5. reproduce-vs-paper 三方一致性检查（新增审计项，进 B10）

method 侧的"官方死代码"同款陷阱：benchmark 侧我们学到"签名默认 ≠ 实际调用点"；
method 侧的三方发散是 **paper 声明 / repo 复现目录 / repo 默认** 三者可能都不一样。

**对每个 native 格，取证并对比三份配置**：
- (a) **paper 报告的配置**（超参、backbone、judge、embedding）；
- (b) **repo 复现目录的配置**；
- (c) **repo 默认配置**（= unified 用的那套）。

**失配处理（原则化，不逐格拍脑袋）**：
- native 的权威 = "**实际能复现 paper 报告数字的那套**"。
- (b)==(a)：直接用，记录一致。
- (b)≠(a) 且**有作者指引** → follow 作者，记录来源（MemoryOS 判例）。
- (b)≠(a) 且**无作者指引** → 该格标 **native=DISPUTED**：两份配置都记下、选**最可能
  复现 paper 数字**的一份（通常是 paper，因为那是被声明的数字）先行，标"待 R 阶段
  真实校准裁决"。**不阻塞接入**（同 recall=N/A 的冻结限制处理法），但把分歧显式留痕。
- **禁止编造裁决、禁止发明权威**（"paper 永远对"不普适——有时 repo 修了 paper 的 bug）。
  证据驱动、逐格、留痕。

## 6. single-track collapse 规则（省钱 + 防臆造）

> **一个 `method × benchmark` 格是"双轨"，当且仅当该 method 官方在该 benchmark
> 上跑过、且有可区分的配置。否则是"单轨"：native ≡ unified，只跑一次，不重复。**

- 跑量因此是：**unified 铺满**（method 兼容的所有格）+ **native 只在稀疏的 native 格**。
- native 矩阵本就稀疏（见 ws02.7 README）：A-Mem 只有 locomo 双轨、其余单轨；
  LightMem 只有 locomo+longmemeval 双轨、其余单轨；HaluMem 全员单轨。
- smoke 时：native 格两套都 smoke；单轨格只 smoke 一次（unified）。

## 7. 算法代码单一化原则（多仓库 method）

有些 method 官方放了**多个仓库/版本**（复现版 / 通用库版 / 商业产品版）。

> **method 的算法代码（实现）每 method 固定一份；双轨只换配置，绝不换算法实现。**
> 否则"双轨"退化成"两个不同的 method"，对比失去意义。

- 选哪一份代码：**优先复现/benchmark harness 版**（native 保真要求它），两轨都跑在它上。
- **A-Mem 判例**（已一手核实，纠正用户口径的方向）：
  - `third_party/methods/A-mem` = **复现版**（README: "specifically designed to
    reproduce the results presented in our paper"，含 `memory_layer_robust.py` +
    `run_all_experiments.sh` + 论文 PDF）。**adapter 已接这份**（`amem_adapter.py:3`、
    `AMEM_METHOD_DIRECTORY="A-mem"`、import `memory_layer_robust`）——**接对了**。
  - `third_party/A-mem`（顶层，2026-07-09 新加，untracked）= **通用库版**（README 指
    引你去别处复现，含 `agentic_memory/` 包）。**adapter 未用**，对本项目冗余。
  - A-Mem 整治（M 阶段）待办：① 确认复现版 `memory_layer_robust.py` 与通用版
    `agentic_memory/` 是否同一核心算法（若分叉，则"哪份是 A-Mem"以复现版为准）；
    ② A-Mem 只有 **locomo 双轨**，其余 benchmark 单轨；③ 顶层 `third_party/A-mem`
    是否保留为参考 or 移除，由用户定（架构师不擅自删非自建文件）。

## 8. 与现有机制的关系

- **benchmark 级 `prompt_track`（run_prediction.py，默认 "native"）与本文的 method
  级 config-track 正交**，别混：前者管"answer prompt 用 benchmark 注册的 unified
  builder 还是 provider 自己的 prompt_messages"；后者管"整条读出+构建配置走框架轨
  还是 method paper 轨"。运行时机制设计要显式区分二者（架构师待办，M0-2 前）。
- **run_id 命名**：`{method}/{benchmark}/{mode}/{track}/{run_id}`，track ∈
  {unified, native}，从一开始就进命名空间，两轨产物物理隔离、可分别 resume。

## 9. 逐 method 应用表（占位；逐格在各 M 阶段一手抽取 + 架构师验收才算数）

| method | native 格 | native 配置来源 | 已知关键点 |
|--------|-----------|-----------------|-----------|
| LightMem | locomo, longmemeval | 官方 experiments 目录 | locomo headline=LightMem 模式（summary OFF）→ answer=`ANSWER_PROMPT`；StructMem 是**另一实验**（换 build+检索+embedding），非 headline，暂不接（§见 ws02.7 Task1 裁决） |
| A-Mem | locomo | 复现版仓库 | 见 §7；只 locomo 双轨 |
| MemoryOS | locomo | eval 目录**但用论文超参** | 作者 issue 指引用论文超参（§4 case 2）；eval 目录与论文失配需 §5 取证 |
| mem0 | locomo, longmemeval, beam | `memory-benchmarks` 当前 eval | 老论文已进化，走当前 harness 不看老论文（§4 case 3） |
| SimpleMem | locomo, longmemeval, membench | `simplemem/evolver` 等 | 逐格 M 阶段核 |
| MemOS | locomo, longmemeval | 待 M 阶段一手 | — |
| EverOS | locomo | 待 M 阶段一手（排最后） | — |
| Letta/LangMem/Supermemory | 未见 academic 配置 | 大概率全单轨 | M 阶段深挖确认；工程产品走通用版本 |

（native 格来源 = ws02.7 README 一手矩阵；本表随各 M 阶段验收更新。）

## 10. 判例锚（写死，供继任者重放）

- **LightMem `--enable-summary`**：build+检索+embedding 三处都变（不是纯 answer
  prompt 开关）；paper headline locomo 数字是 summary OFF；证据
  `experiments/locomo/readme.md:49-97`（LightMem 模式为 reported）、`:183-196`
  （StructMem 是独立小 ablation，换 text-embedding-3-small）。
- **A-Mem 双仓库**：复现版在 `third_party/methods/A-mem`（adapter 接的这份），
  通用版在 `third_party/A-mem`；README note 是区分二者的判据。
- **MemoryOS eval≠paper**：作者 GitHub 回应推荐论文超参 → native 用论文超参。
