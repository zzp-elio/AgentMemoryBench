# Method / Benchmark 接入标准清单（Definition of Done）

> 创建 2026-07-12（用户提议：接入一个 method/benchmark 到底要做完哪些
> 审查才算"真的接入完成"，需要一份清晰标准）。本文是**可复用的接入
> 完成判据**，跨模型有效。每一项都要有**一手证据**（`third_party/` 源码
> `文件:行号` 或 `data/` 真实数据）；查不到写"来源待溯"，禁止编造
> （playbook 原则 #4/#11）。benchmark 侧五家已按此隐式走完并 frozen-v1，
> 本文把它显式化，并新增 method 侧标准。

## A. Benchmark 接入完成判据（已由五家 frozen-v1 验证的模板）

一个 benchmark 达到 `frozen-v1` = 以下全部有一手锚 + 架构师验收：

1. **来源锁**：官方 repo/commit（拿不到写"来源待溯"）、license、数据文件
   逐一 SHA-256（架构师独立重算）、只从 `data/` 加载。
2. **数据契约**：全量剖面（conv/session/turn/question 计数、异常形态、
   字段结构）用脚本实测，不猜。
3. **公私边界**：gold/evidence/judge label 进全局私有键黑名单
   （`core/validators.py`），公开对象泄漏扫描 CLEAN。
4. **canonical 映射**：公开 id 空间定义；官方原始 id 只作对照留 metadata
   （通用契约 GC-1，见 spec）。
5. **prompt/metric parity**：answer/judge prompt 官方有就逐字用（运行时
   AST/程序化核）；论文报告的指标必须覆盖；每类问题分开报告。
6. **smoke/resume policy**：benchmark-shaped 裁剪轴、声明式 policy、
   验收口径 = 运行时路径调用 ≥1（原则 #13）；resume/smoke 是**框架**职责。
7. **artifact/efficiency schema**：口径与其余 benchmark 一致、可汇总不混粒度。
8. **冻结门**：全量 pytest + compileall + 真实数据抽查 + 泄漏 CLEAN +
   零真实 API → 写 `notes/<b>-frozen-v1.md`（含 known limitations）。

## B. Method 接入完成判据（M0 标准，本文新增）

一个 method 达到 `method-frozen-v1` = 以下全部有一手锚 + 架构师验收。
**逐 method、逐项过；每项写明"支持/不支持/N/A + 一手出处"**。

### B1. 来源锁与接口选择
- 官方 repo/commit（拿不到写"来源待溯"）、license、vendored 路径。
- **产品接口选择**：用哪个 ingest/retrieve 接口，**为什么不用**它的
  chat/ask/eval 专用入口（公平性——只测记忆质量，见 AGENTS 运行主线）。
  附官方源码 `文件:行号`。

### B2. 注入粒度（consume_granularity）
- method 原生接口支持的注入单元：turn / pair / session(list) / conversation。
- **HaluMem 特例**：能否按 session 一次注入并返回该次产出的 memory
  points？能（且接口收 list）→ 可 session 级；只能 turn/pair → 记为
  gap。一手核接口签名。

### B3. 隔离方式（物理 vs 逻辑）
- **物理隔离** = 每隔离空间独占存储（独立 collection/路径/DB）；
  **逻辑隔离** = 共享存储按 namespace 键分区。
- **判据**：method 原生给不给可靠 namespace → 给且过滤可信=逻辑（省资源、
  利并行）；不给或存疑=物理（安全兜底）。附一手证据 + 说明 clean-retry
  怎么做（reset 干净度）。**带着"未来并行安全"一起定**。

### B4. formatted_memory 完整性（含时间戳）
- 检索返回是否覆盖官方全部有效记忆层 + 时间/地点字段。
- **时间戳规则**：能单独传/取时间戳就结构化带；不能就折进 content；只要
  检索**能拿回**时间戳，formatted_memory 就必须带；拿不回则记 gap。前提
  是 benchmark dataset 有时间戳。
- 禁止 `str(context)` 这种不可审计的塞法（A-Mem 判例）。

### B5. provenance 能力
- retrieve 能否返回 source id（turn/session/step）→ 决定 recall/ndcg 类
  指标是否 N/A。一手核 retrieve 返回结构。`items=None`/`provenance="none"`
  要如实表达 method 能力，不假装有。

### B6. flush / finalize 时机（correctness 关键）
- 检索前是否需要显式 flush（end_session/end_conversation）记忆才建成？
  （LightMem `update="offline"` 判例：不 flush 检索到空记忆。）确认框架
  钩子接对。

### B7. 效率插桩（api_usage 优先）
- 记忆构建/检索/answer 三阶段 LLM+embedding 调用都可观测。
- **token 必须 api_usage，只有接口确不暴露才 tokenizer_estimate**，并记
  缺口与拦截层。
- **method 原生返回的效率指标**（如 LightMem add_memory 返回 token/
  api_call_nums）→ 作为我们插桩的交叉参照留档。

### B8. 检索副作用 / clean-retry
- 区分"污染"（eval 探测内容写进记忆，必须防）vs"算法固有状态变化"
  （MemoryOS heat/N_visit，必须保留）——判据 = 回 method 官方 eval 看
  作者意图（playbook §4.5.7）。失败态清理（Mem0 clean_failed_ingest_state）。

### B9. 模型口径
- method 内部构建 LLM（第三个模型角色，独立于框架 answer/judge）跨 method
  一致或显式声明差异。embedding 模型：unified 轨用统一 embedding；native
  轨用 method paper embedding（见 B10）。

### B10. 双配置轨（unified + native，老师 2026-07-12 敲定）
> **完整政策见 `docs/reference/dual-track-config-policy.md`**；本项是接入时的核对清单。
- **unified 轨**：框架统一 embedding+answer+judge + method **repo 默认超参**（非 paper、
  非 per-benchmark 调参）。所有兼容格子都有。
- **native 轨**：method 官方复现实验配置。**仅 native 格存在**（矩阵见 ws02.7 README）；
  **无官方实验的格 = 单轨 native≡unified，不重复跑**（policy §6 collapse 规则）。
- **差异 7 轴，分 build/readout**（policy §2）：readout（answer/judge 的 LLM+prompt+语义）
  改了**记忆可复用**；build（embedding + 内部超参）改了**必须重建、成本 ×2**。**记忆复用
  是有条件的**（两轨 build 轴全同才成立），不默认。
- **reproduce-vs-paper 一致性检查**（policy §5，逐 native 格必做）：取证 paper / repo 复现
  目录 / repo 默认三份配置并对比；失配且无作者指引 → 标 native=DISPUTED、留痕、不阻塞接入
  （同 recall=N/A 冻结限制法）。
- **算法代码单一化**（policy §7）：多仓库 method（复现版/通用版/产品版）选**一份**代码
  （优先复现版），两轨只换配置不换算法实现。
- 实现 = TOML config-track 捆绑 + track-aware run_id `{method}/{benchmark}/{mode}/{track}/
  {run_id}`；native prompt/judge 从 method 仓库一手抄成注册 profile + parity 锁。

### B11. smoke（两轨）+ 冻结
- unified 轨所有格子 smoke；native 轨仅有配置的格子 smoke。验收口径 =
  flow-through 跑通（不看答对）。
- 冻结门：全量 pytest + compileall + 真实极小 smoke 跑通 + 效率观测落地 +
  成本观测 → 写 `notes/<method>-frozen-v1.md`。

## C. 通用铁律（两侧都适用）
- 一手证据 `文件:行号`，查不到写"来源待溯"，禁编造（#4/#11）。
- fixture 经真实序列化函数构造（D4/D5 判例）。
- 不改 third_party 算法核心，只做适配/观测插桩并留档。
- 冻结后推翻走版本化（frozen-v2）+ 影响分析 + 重跑，不在 adapter 内打
  格子专用补丁。
- resume/smoke/隔离清理是**框架**职责，不是 adapter。
