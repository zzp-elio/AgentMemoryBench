# 双轨配置政策（unified / native；历史政策）

> **Superseded（2026-07-17）：**本文保留 2026-07-12 至 2026-07-16 的双轨设计史、
> build/readout 成本分析和既有产物解释，不再是新运行的配置政策。现行事实源是
> [`method-toml-and-answer-builder-policy.md`](method-toml-and-answer-builder-policy.md)：
> 每个 method 一个 TOML、主 section 跨五 benchmark 固定、作者配置用稀疏
> `author_<benchmark>` section；TOML 选择的是完整 answer builder，不是未填变量的模板。
> 当前 `config_track` 与旧 track-aware outputs 只作兼容和历史审计，禁止把本文继续复制成
> 新 method 的双流水线模板。

> 本文最初由架构师（Opus 4.8）与用户（zzp）于 2026-07-12 碰撞后成文；当时的拍板是
> “每个 method 既能用框架配置跑，也能用自己的配置跑”。2026-07-17 的新裁决保留这一
> 可配置目标，但把实现从全局 `unified/native` 双轨收敛为 TOML section + answer builder。

## 0. 两轨定义

| 轨 | 别名 | 目的 | 配置来源 |
|----|------|------|----------|
| **unified**（轨1） | 产品公平轨 | method 之间**公平横向对比**（同一 benchmark 读出尺子） | 通用 OSS 产品实现 + pinned product-default build + benchmark-scoped method-neutral answer/judge；官方资产优先，缺失 fallback 必须标 tier/source |
| **native**（轨2） | 官方配置校准轨 | 在**同一产品算法实现**可表达的范围内对齐 method 官方实验配置 | method 官方实验的 build/readout 配置；覆盖不全就明确 partial-native |

**公平 ≠ 所有 build 组件也相同**。unified 的硬公平面是 method 外部的 answer/judge
LLM、prompt 与 metric 语义；embedding、build LLM、update/retrieval 超参都属于 method
如何建库和检索，不能再误称 readout。

> **2026-07-16 embedding 新裁决（用户授权架构师作判断）：**unified 主轨采用每个 method
> 在当前 vendored 版本上的 **pinned product-default embedding**，同一 method 跨全部 benchmark
> 固定一套，不做 benchmark-specific tuning。2026-07-09 的 shared `all-MiniLM-L6-v2` 是当时
> 明确执行且有效的控制变量政策，不倒写为“早已过时”；从本裁决起，其既有配置/产物保留并
> 标作 `controlled_embedding_v1` 补充消融。理由是 embedding 参与抽取、合并、索引与排序，
> 属于 method 能力本体；强制同一 backbone 会对不同架构造成不对称改造，也无法自然覆盖十家
> 异构 method。common embedding 仍有因果控制价值，但不是产品公平主估计量。

产品默认必须锁 provider/model/revision/dimension/normalization/instruction/distance 等身份；若
默认依赖托管服务，只能声明 provider/model API 身份与 `provider_managed_unpinned` revision，
不得把接口公开误写成权重级可复现。替换会触碰算法核心时，不得静默找近似替代，须停工裁定。
全局 `gpt-4o-mini` 仍是 Phase 1 明示的 build/readout LLM override，不受 embedding 改判影响。

若产品顶层故意没有可运行零配置默认，按“可运行构造默认 → 官方通用 quickstart 唯一配置 →
backend 内部缺省与官方 experiments/paper 同轴共识”的顺序操作化；只有后一层证据闭合时才可
盖 `product_canonical_required_config`，不能再称 `repo_default`。LightMem 是首个判例：
`text_embedder=None` 不可运行，现行 canonical 是 local HF `all-MiniLM-L6-v2`，与当前 build
字节重合，故无需重建但必须修正 manifest identity。完整裁决见 ws02.7
`branches/dual-track-identity/notes/product-default-embedding-ruling.md`。

> **2026-07-16 纠偏：**旧版 §7 写“多仓库优先复现版，两轨都跑在它上”，与项目
> “通用产品接口”主线冲突，现已撤销。复现目录若改变算法流程，属于另一个
> `reproduction_variant`，不是同一 method 的 native 配置。

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

两轨/变体之间必须显式对表的轴（原 7 条扩成 9 条）：

| # | 轴 | 类型 | 影响面 |
|---|-----|------|--------|
| 1 | answer LLM（model+temp+max_tokens+top_p） | 配置 | **readout** |
| 2 | answer prompt | **代码资产** | **readout** |
| 3 | judge LLM（model+参数） | 配置 | **readout** |
| 4 | judge prompt | **代码资产** | **readout** |
| 5 | judge 语义（cat5 跳过 / abstention 门控） | **代码** | **readout** |
| 6 | embedding model | 配置 | **build** |
| 7 | method 内部超参（top_k/chunk/summary 开关…） | 配置（部分藏库内） | **build**（多数） |
| 8 | storage backend / 持久化语义 | 实现或配置 | **build** |
| 9 | algorithm implementation（通用产品 vs eval fork） | **实现身份** | **variant**，不得藏在 config-track |

**build-affecting vs readout-affecting 二分是成本命门**：
- **readout 轴（1-5）**：只影响"取回记忆后如何生成答案/如何判分"。改这些**不用重建
  记忆**——同一份记忆库跑两次 readout 即可。**便宜**。
- **build 轴（6-7）**：影响"记忆怎么建、怎么存、怎么检索"。改这些**必须重建记忆**，
  两轨各建一份 → **构建成本 ×2**。**贵**。

**推论（改正此前口径）**：此前架构师说"native 只重跑 answer+judge、记忆能复用"
**只在 build 轴两轨相同时成立**。一旦 native 的 embedding 或内部超参 ≠ unified
的 repo 默认，记忆无法复用，是两次完整构建。**记忆复用是有条件的，不是默认的。**
逐 method 在 M 阶段核 build 轴是否分叉，再定成本。

### 2.1 native 是 coverage vector，不是一个万能布尔值

每个 native 格至少记录六轴：`implementation/build/retrieval/answer/judge/metric`。推荐拆成
两个正交身份：`native_scope = none | readout_only | build_and_readout`，以及
`implementation_variant = product | reproduction:<name>`；并为缺失轴记录 fallback：

- 官方只有 answer prompt/参数 → `readout_only`；
- 官方无 LLM judge → 可以消费 framework judge，但 manifest/报告必须写
  `judge=framework_fallback`，不能称 full-native；
- eval 目录改变 update/retrieval/storage 算法 → `implementation_variant=reproduction:<name>`，
  与产品轨使用不同 variant identity、输出目录和报告栏，不能只切 `config_track=native`；
- 单轨格没有可区分的官方资产 → collapse，不重复跑。

其中 `answer` 与 `judge` 轴都必须再拆成 `model + decoding params + prompt + output/parse
semantics`。项目硬规则把所有真实 LLM 锁为 `gpt-4o-mini`；官方实验若用别的 model，Phase 1
只能记 `model=framework_override`，其余参数/prompt 即使 parity 也只是 partial-native，不能
把分数称作论文模型复现。未来若用户明确解锁模型，再用新 run identity 补完整 native。

MemoryOS 当前已经是明确判例：LoCoMo 有 native answer prompt/参数、没有 native LLM judge，
build profile 尚未接入，因此只可称 **readout-native**。

## 3. 轨1（unified）配置来源政策

- **answer/judge = benchmark-scoped、method-neutral 的框架统一配置**。来源优先级是 benchmark
  官方资产 → 明确标注的 framework supplementary；“同一 benchmark 同一套”不等于把 fallback
  冒充官方。LoCoMo 没有官方 LLM judge，当前 `locomo-judge` 使用 LightMem prompt 参考并标
  `framework_auxiliary`，它可横向统一使用，但不是 LoCoMo official parity。
- **method 实现 = 通用 OSS 产品接口**，不用 benchmark eval 专用算法副本。
- **embedding/内部超参 = 官方产品 repo 默认主轨**（**非** paper、**非** benchmark 专用调参，
  同一 method 跨全部 benchmark 同一套）。embedding 必须按上方新裁决盖精确 build identity；
  shared `all-MiniLM-L6-v2` 只在兼容 method 上作为 `controlled_embedding_v1` 补充轨，不要求
  强铺 5×10。build LLM 的全局模型名 `gpt-4o-mini` 是 Phase 1 显式 override，不冒充产品默认。
- **产品默认要操作化**：优先“不加特殊 flag、开箱即用”的可运行默认；某项能力被产品
  明确设为必填时，按上方 canonical-required 证据链处理，不能为了填字段臆造 repo default。
  LightMem 的 `--enable-summary` `store_true` 默认 False 仍是可选超参默认判例，但 embedding
  顶层 `None` 是必填缺口，两者不能混为一谈。
- **现有实现不因政策文字自动合规**：Mem0 当前 unified 显式换成 shared MiniLM，而其
  通用 OSS 默认已知为 `text-embedding-3-small`；当前结果保留为 controlled 身份，主轨迁移
  已定。2026-07-16 三家 build-axis 审计与架构裁决已核实精确默认、实现等价性、manifest
  缺口与重建/复证范围；truthful track identity M0 已由 R1/R2 关闭，下一门按 method
  重认证顺序单独迁 Mem0，不把身份落盘误当 build 已切换，也不提前重烧实验。
- **全局模型锁优先于 native 口号**：当前真实调用只能是 `gpt-4o-mini`。若官方 harness
  使用 GPT-5/Qwen/Claude 等，只抽取其可复用 prompt/decoding/metric 资产并在 coverage 中
  标模型 override；不得为追论文数字绕过 AGENTS 硬规则。

## 4. 轨2（native）配置来源决策树

对每个 `method × benchmark` 的 native 格，按优先级定配置来源：

1. **method 官方有该 benchmark 的复现/eval 目录** → 先判断它是否调用与通用产品相同的
   algorithm implementation。相同核心、差异可配置 → 可作为 native 配置源；fork 了 update/
   retrieval/storage → 只能作 `reproduction_variant`。SimpleMem evolver、MemoryOS eval、
   mem0 memory-benchmarks 都必须先过此门，不能仅因目录名叫 eval 就归 native。
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

> **一个 `method × benchmark` 格是同实现“双轨”，当且仅当该 method 官方在该 benchmark
> 上跑过、有可区分配置，且配置能落在同一 algorithm implementation。否则要么单轨 collapse，
> 要么另列 reproduction variant；两者都不能伪装成普通 native。**

- 跑量因此是：**unified 铺满**（method 兼容的所有格）+ **native 只在稀疏的 native 格**。
- native 矩阵本就稀疏（见 ws02.7 README）：A-Mem 只有 locomo 双轨、其余单轨；
  LightMem 只有 locomo+longmemeval 双轨、其余单轨；HaluMem 全员单轨。
- smoke 时：native 格两套都 smoke；单轨格只 smoke 一次（unified）。

## 7. 通用产品 identity 与复现 variant（多仓库 method）

有些 method 官方放了**多个仓库/版本**（复现版 / 通用库版 / 商业产品版）。

> **Phase 1 主 method identity 固定为通用 OSS 产品实现；双轨只换可配置资产，绝不暗换
> 算法实现。**否则“native”实际比较的是两个不同 variant。

- 选哪一份代码：**unified 优先通用产品版**，因为项目测的是用户真实可调用的产品接口，
  且同一实现要铺五 benchmark。benchmark harness 只作配置/prompt/调用序列证据；若它复用
  产品 core，可以抽取 native 配置；若它是 fork，则另建 `reproduction_variant` 身份，不能
  替换 unified 的底座。
- **A-Mem 双仓现状**（目录身份已一手核实，算法等价性尚未裁）：
  - `third_party/methods/A-mem` = **复现版**（README: "specifically designed to
    reproduce the results presented in our paper"，含 `memory_layer_robust.py` +
    `run_all_experiments.sh` + 论文 PDF）。**adapter 当前接这份**（`amem_adapter.py:3`、
    `AMEM_METHOD_DIRECTORY="A-mem"`、import `memory_layer_robust`）；这是待 M 阶段审计的现状，
    不能在通用版/复现版算法身份未核前预判为“接对了”。
  - `third_party/A-mem`（顶层，2026-07-09 新加，untracked）= **通用库版**（README 指
    引你去别处复现，含 `agentic_memory/` 包）。**adapter 未用**，对本项目冗余。
  - A-Mem 整治（M 阶段）待办：① 确认复现版 `memory_layer_robust.py` 与通用版
    `agentic_memory/` 是否同一核心算法（若分叉，通用版是 Phase 1 产品 identity，复现版
    另列 variant；现有 adapter 的迁移成本须先审计，不在文档里假装已完成）；
    ② A-Mem 只有 **locomo 双轨**，其余 benchmark 单轨；③ 顶层 `third_party/A-mem`
    是否保留为参考 or 移除，由用户定（架构师不擅自删非自建文件）。

## 8. 与现有机制的关系

- **benchmark 级 `prompt_track`（run_prediction.py，默认 "native"）与本文的 method
  级 config-track 正交**，别混：前者管"answer prompt 用 benchmark 注册的 unified
  builder 还是 provider 自己的 prompt_messages"；后者管"整条读出+构建配置走框架轨
  还是 method paper 轨"。运行时已分别保留 `prompt_track` 与 typed `track_identity`，后者再拆
  build/readout/judge/model source；两者不得重新合并成一个 native 布尔值。
- **run_id 命名**：`{method}/{benchmark}/{mode}/{track}/{run_id}`，track ∈
  {unified, native}，从一开始就进命名空间，两轨产物物理隔离、可分别 resume。

## 9. 逐 method 应用表（占位；逐格在各 M 阶段一手抽取 + 架构师验收才算数）

| method | native 格 | native 配置来源 | 已知关键点 |
|--------|-----------|-----------------|-----------|
| LightMem | locomo, longmemeval | 官方 experiments 目录 | ingest core 等价，但官方 LoCoMo retrieval 为 harness-local brute-force cosine；当前 native 只 readout，未来 wiring build 才重建；StructMem 是另一 variant，不接 |
| A-Mem | locomo | 复现版仓库（现状） | 见 §7；通用版/复现版算法身份待 A-Mem M 阶段审计，不能把现状反写成永久政策 |
| MemoryOS | locomo | eval answer 资产 + paper 超参候选 | 当前只 readout-native；eval 与 pypi 已有算法差异；PyPI 是 canonical，ChromaDB 是 reproduction variant |
| mem0 | locomo, longmemeval, beam | `memory-benchmarks` 当前 eval | oss harness 已证实调用同一 `Memory.add/search` core；current MiniLM 已盖 controlled identity，product-default OpenAI/1536 迁移待 Mem0 重认证阶段施工 |
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
- **MemoryOS pypi≠chromadb**：调用链审计已确认 ChromaDB 同时改变检索、合并、heat/LTM、
  持久化与异常语义；Phase 1 canonical 继续 `memoryos-pypi`，ChromaDB 明确列
  `reproduction_variant:memoryos-chromadb`，不是候选 storage variant。
