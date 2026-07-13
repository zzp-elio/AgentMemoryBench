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
- **逻辑隔离合格 = 与物理隔离全效等价，四项逐一取证**（用户 2026-07-13 细化）：
  ① **写入分区**：add 带 namespace 且落库可查证；② **检索过滤**：retrieve 严格按
  namespace 过滤、零跨空间泄漏（官方过滤实现一手锚，不信文档）；③ **单空间删除**：
  能只删一个隔离空间（clean-retry/resume 复建的前提）；④ **并行安全**：多空间并发
  读写无竞态。**任一项证不了 → 判物理隔离兜底**。判例：Mem0 是当前唯一逻辑隔离
  候选，且缺 clean-retry 钩子（③ 存疑），见其实例文档 B8。

### B4. formatted_memory 完整性（含时间戳）
- 检索返回是否覆盖官方全部有效记忆层 + 时间/地点字段。
- **时间戳规则**：能单独传/取时间戳就结构化带；不能就折进 content；只要
  检索**能拿回**时间戳，formatted_memory 就必须带；拿不回则记 gap。前提
  是 benchmark dataset 有时间戳。
- 禁止 `str(context)` 这种不可审计的塞法（A-Mem 判例）。
- **get_answer 型接口的拆分流程覆盖**（用户 2026-07-13 固化）：method 官方
  只有 `get_answer/ask/get_response` 一体化入口、没有独立 retrieve 时，我们
  拆出的纯检索必须**复刻官方 answer 流程实际检索的全部层，一层不漏**
  ——"它 answer 前 retrieve 什么，我们就 retrieve 什么"（判例：MemoryOS
  复刻 get_response 步骤 1-7 短/中/长期+双 knowledge 全层、只跳答题与写
  副作用）。逐层对照官方源码行号留档。

### B5. provenance 能力
- retrieve 能否返回 source id（turn/session/step）→ 决定 recall/ndcg 类
  指标是否 N/A。一手核 retrieve 返回结构。`items=None`/`provenance="none"`
  要如实表达 method 能力，不假装有。

### B5+. 能力缺口的无损改造评估（2026-07-13 新增，导师建议）
B2/B5 及 HaluMem memory_point 这类**能力缺口**（method 接口不支持某 benchmark 的
某类指标/流程）不是终点，逐缺口做**无损改造可行性评估**，三态结论：
- **直接支持**：接口已够，正常接。
- **可无损改造**：不动算法核心机制、只做"多一个字段/透传/包装"级别的改动即可支持
  （例：retrieve 结果透传内部已有的条目 id → recall@k 可算；add 返回值透传本次产出
  条目 → HaluMem memory_point 可评；MemoryOS pair 粒度对 MemBench 第三人称的
  投递改造）。改造实现在 **adapter/包装层优先**；确需动 third_party 时走"最小
  diff + 留档 + 不碰核心算法"审批（架构师裁决）。
- **不可改造**：诚实记 N/A（如 HaluMem recall 判例），不硬造。
评估证据与结论写进该 method 的 `integration/<m>.md` 实例文档。**改造经真实实验
验证有效后，可向 method 官方仓库提 upstream PR**（贡献者收益，用户 2026-07-13
提议）；PR 门槛 = 我们自己的实验数据先证明改造不劣化原行为。

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
- **注入记忆 token 双轨口径**：见 `efficiency-injected-tokens-policy.md`
  （两轨统一记"记忆载荷 token"，native 模板开销不计入）。**native 审计项**：
  每个 native prompt builder 核一次"统计的载荷 ≡ prompt_messages 实际嵌入的
  记忆段"（policy §2）。

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
- unified 轨所有格子 smoke；native 轨仅有配置的格子 smoke。
- **smoke 认证口径（用户 2026-07-13 扩充，五件套）**——仍不看答对率，但：
  ① predict flow-through 成功；② 该格**全部适用指标**的 evaluate 成功；
  ③ 效率观测落盘且可读（injected tokens / api_usage / latency 三类都在）；
  ④ **formatted_memory 内容抽查**：时间戳等应带字段确实带上（B4 口径）；
  空记忆哨兵是合法结果但要留痕原因（极小输入抽取 0 条属方法行为）；
  ⑤ **并行冒烟**：workers>1 跑一次不崩（隔离等效性的最低验证）。
- **resume 测试缓期**（用户 2026-07-13 拍板）：resume 仅 formal/full 支持，
  真实测试烧钱 → 离线测试先行（已有），真实 resume 验证等预算批复后随
  cost-probe/全量一起做，不阻塞 method-frozen-v1（作为已声明缺口记录）。
- 冻结门：全量 pytest + compileall + 上述五件套 smoke + 成本观测 →
  写 `notes/<method>-frozen-v1.md`。

## C. 通用铁律（两侧都适用）
- 一手证据 `文件:行号`，查不到写"来源待溯"，禁编造（#4/#11）。
- fixture 经真实序列化函数构造（D4/D5 判例）。
- 不改 third_party 算法核心，只做适配/观测插桩并留档。
- 冻结后推翻走版本化（frozen-v2）+ 影响分析 + 重跑，不在 adapter 内打
  格子专用补丁。
- resume/smoke/隔离清理是**框架**职责，不是 adapter。
