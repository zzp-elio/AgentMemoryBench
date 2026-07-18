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

### B4. 输入可见性 + formatted_memory 完整性（含时间/地点）
- **输入可见性门**：字段写进 storage metadata，不等于 method 的 extraction/build
  算法实际看见了它。必须沿官方调用链核实 typed timestamp/place 是否进入算法 prompt、
  排序或更新逻辑；若 method 没有独立字段，或独立字段只落库而不被算法消费，就在 adapter
  边界把数据集公开时间/地点用稳定格式折进 content。禁止只凭 API 签名或 metadata 落库
  断言“已支持时间”。Mem0 OSS 的 `Memory.add()` 判例：extraction 读取 parsed messages，
  metadata 主要用于持久化。
- **时间 fallback 顺序**：有真实 `turn_time` 就用 turn；turn 缺失且 benchmark 确有真实
  `session_time` 才用 session；两者都缺失就保持 None/省略。question time、兄弟 turn、运行
  墙钟和人造序号永不进入 source-time fallback。
- **两类 method 分流**：① method 真正消费独立 timestamp：原 content 原样传入，同时把上述
  effective timestamp 送 typed 参数；② method 不消费独立 timestamp：若原 content 尚未含
  source time，才用单一稳定 header 折进 content；若原文已经内嵌同一时间事实，禁止再拼一份
  `[Turn time]`。metadata-only 且算法不读不算第三种“已支持”。
- **原文无损规则**：benchmark 原 content 已含 place/time 时必须逐字保留；结构化字段是
  additive，不得以“已经拆字段”为由从 content 删除。缺失则保持缺失。原 content + typed
  channel 是两个不同接口通道，不叫正文重复；同一 content 内再次前置相同时间才是应避免的
  文本重复。MemBench adapter 应以公开 metadata 标记“source time 已嵌在 content”，让 Mem0
  等 content-only renderer 通用去重，禁止在 method 内写 benchmark 名特判。
- 检索返回是否覆盖官方全部有效记忆层 + 时间/地点字段。
- **取回规则**：能单独传/取时间戳就结构化带；不能就折进 content；只要检索**能拿回**
  时间戳，formatted_memory 就必须带；拿不回则记 gap。前提是 benchmark dataset 有时间戳。
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
- **校验当前条目，不只校验初次 insert**：method 若会 summary/merge/update，
  `source_turn_ids` 必须表示当前 retrieved item 实际承载 evidence 的语义来源。只保留
  初始 id 不行；把所有变换输入 id 求并也不行——后者只证明“参与过生成”，无法证明
  输出仍保留相应事实（2026-07-15 LightMem 二次判例）。官方不提供无损 output-to-source
  mapping 时，该 method × benchmark × provenance metric 应 N/A。
- `consume_granularity` 是投递批次，`provenance_granularity` 是来源分辨率，二者
  不要求相等；强绑会错杀 conversation-ingest/turn-provenance 等合法实现。
- top-k item 可能是 fact/summary/session/chunk。允许一个 item 有多个 source ids，
  禁为通过校验伪装成单来源；同时在报告记录 top-k unique source 数与
  `source ids/item` 分布。未做 source/token-budget 归一化前，Recall@k 只作
  method-native item 辅助指标，不单独作跨 method headline 排名。
- **NDCG/检索排名另有资格门**：除 semantic provenance 外，还必须保存 method 实际
  返回的稳定有序列表、足够的 evaluation depth 与可解释 rank；不能拿无序集合、二次
  排序后的展示列表或 answer 截断深度冒充官方 top-k。资格按 method × benchmark ×
  metric 独立声明 valid/N/A/pending，禁止要求每个 method 填满所有指标。
- **资格不是手写白名单**（2026-07-15 裁决）：provider 在逐次 `RetrievalResult` 陈述
  semantic provenance 与 stable ranking 的 `valid/n_a/pending + reason` 事实，evaluator
  按本 metric 的通用 requirement 导出资格。禁止另建会与 runtime 漂移的
  method × benchmark × metric 人工矩阵；manifest 只存 schema/version 与能力上限，
  不能覆盖逐题实际值。实现门见 ws02.7
  `docs/workstreams/ws02.7-method-track/branches/retrieval-metrics/notes/
  retrieval-metric-eligibility-ruling.md`。

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
**判例库**：`ws02.7/notes/memorydata-recall-retrofit-survey.md`（MemoryData 框架
让各 method 支持 recall 的三条 adapter 层策略：①in-band 文本 header ②原生 id
映射 sidecar ③文本反查表；含反面判例——为指标绕过 method 核心管线不可取）。

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
- **注入记忆 token 跨 builder 口径**：见 `efficiency-injected-tokens-policy.md`
  （各 profile 都只记“记忆载荷 token”，模板开销不计入）。**作者 builder 审计项**：
  每个作者 prompt builder 核一次“统计的载荷 ≡ prompt_messages 实际嵌入的
  记忆段”（policy §2）。

### B8. 检索副作用 / clean-retry
- 区分"污染"（eval 探测内容写进记忆，必须防）vs"算法固有状态变化"
  （MemoryOS heat/N_visit，必须保留）——判据 = 回 method 官方 eval 看
  作者意图（playbook §4.5.7）。失败态清理（Mem0 clean_failed_ingest_state）。

### B8+. 外部调用韧性（超时/重试/失败兜底，用户 2026-07-14 新增）
- M-1 取证时列出该 method **全部 API/网络调用点**（抽取 LLM、embedding、
  向量库远端模式、reranker 等），逐点核：① 有超时（禁无限等待）；
  ② 有重试或明确失败语义；③ 失败**不留半写 state**（与 B8 clean-retry
  交叉：失败后可 clean+resume，不污染下一次）。
- 兜底优先用 method 自带配置（如 mem0 `api_timeout_seconds`/
  `api_max_retries` 走 TOML），method 无配置时在 adapter 边界包裹，
  禁改 third_party 核心。框架侧致命异常捕获+落日志见 ws02.6 #14b。
- 实例文档记"调用点 → 兜底方式"清单；无兜底的点=full 前必修项。

### B9. 模型口径
- method 内部构建 LLM（第三个模型角色，独立于框架 answer/judge）跨 method
  一致或显式声明差异。embedding 属 method build 参数，必须在 TOML 中明确 provider/model/
  revision/dimension/normalization/instruction/distance；它不再靠 `unified/native` 轨名表达。
- 同一 method 的 `smoke`/`official_full` 主配置跨五 benchmark 固定；共同 embedding 还是产品
  默认 embedding 的最终主表选择留到真实效果实验前裁定。当前 5×10 smoke 沿用已验收配置，
  不为追分临时换模型。
- 作者实验使用不同 embedding/build LLM 时，只写入有一手证据的 `author_<benchmark>`
  section；托管 embedding 只能锁 API 身份并声明 revision unpinned，不得伪造权重 revision。

### B10. TOML method profile + 完整 answer builder（2026-07-17 改判）
> **完整政策见 `docs/reference/method-toml-and-answer-builder-policy.md`**；旧
> `dual-track-config-policy.md` 只解释历史双轨产物。
- 每个 method 一个 TOML。`smoke` 与 `official_full` 是主 section，同一 method 跨五个
  benchmark 使用同一套算法参数；smoke 只缩运行规模。作者确实跑过且参数有一手证据时，
  才增加稀疏 `author_<benchmark>` section。
- CLI 只用 `--profile` 选择 section，禁止逐项传超参数、运行前手改同一 section，或根据
  benchmark 名暗中自动切到作者配置。manifest/resume 必须锁 section 与解析后的完整配置。
- embedding、chunk、top-k、update、summary 等都由 TOML 控制；第三方库里写死但确属配置的
  参数，adapter 须先暴露。若 update/retrieval/storage 算法实现分叉，则是另一 implementation，
  不能伪装成 TOML profile。
- `answer_builder="benchmark"` 选择 benchmark-scoped、method-neutral 的完整 builder；
  `answer_builder="<method>_<benchmark>_official"` 选择作者 harness 的完整构造流程。这里验收的
  是填完全部变量、可直接调用 answer LLM 的 `AnswerPromptResult.prompt_messages`，不是模板文本。
- 作者 builder 必查：变量来源逐项有锚；必需变量缺失 fail-fast；最终 message 数量/role/顺序/
  内容及 decoding 参数 parity；只消费公开 Question/RetrievalResult/公开 metadata，gold answer/
  evidence/judge label 不可达。
- answer/judge 主表仍由 benchmark 统一；作者 answer 配置是可选校准，不强铺 5×10。当前真实
  LLM 被项目硬锁 `gpt-4o-mini`，作者若使用别的 model 必须标 framework override，不得宣称
  paper-model parity。

### B11. 主配置 smoke + 冻结
- 5×10 主 smoke 只要求 `smoke` section；作者配置不属于冻结必填矩阵。首个作者校准 run 或
  真实效果 full run 前，再完成 author section、完整 builder 与旧 `config_track` 迁移。
- **格子安全说明采用“每 method 一份 living dossier、五 benchmark 分章”，不制造 50 份顶层
  文档**（2026-07-18 用户要求固化）。每格至少写：benchmark 特殊/异常、canonical 层处置、
  method 最终 payload、adapter 差分、私有边界、metric valid/N/A/pending、离线/真实 smoke
  状态、声明缺口与失效触发器；底层 audit/probe/run note 只链接，不整段复制。一个章节的绿灯
  不得替其余四格盖章。架构师宣布某格 ready 或 method frozen 前，必须更新该 method dossier；
  首个样板见 `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/
  lightmem-five-benchmark-safety-dossier.md`。
- **smoke 认证口径（用户 2026-07-13 扩充，五件套）**——仍不看答对率，但：
  ① predict flow-through 成功；② 该格**全部适用指标**的 evaluate 成功；
  ③ 效率观测落盘且可读（injected tokens / api_usage / latency 三类都在）；
  ④ **formatted_memory 内容抽查**：时间戳等应带字段确实带上（B4 口径）；
  空记忆哨兵是合法结果但要留痕原因（极小输入抽取 0 条属方法行为）；
  ⑤ **并行冒烟**：workers>1 跑一次不崩（隔离等效性的最低验证）。作者配置若只换 answer
  builder/decoding，可继承主配置的并行证据；若同时更改 build/ingest 参数，则必须另补并行
  smoke，不能凭 section 名继承。
- **resume 测试缓期**（用户 2026-07-13 拍板）：resume 仅 formal/full 支持，
  真实测试烧钱 → 离线测试先行（已有），真实 resume 验证等预算批复后随
  cost-probe/全量一起做，不阻塞 method-frozen-v1（作为已声明缺口记录）。
- 冻结门：全量 pytest + compileall + 上述五件套 smoke + 成本观测 →
  写 `notes/<method>-frozen-v1.md`。
- **对表仪式（2026-07-14 用户抓漏后固化，playbook #23）**：架构师宣布
  "下一步=frozen/收口"**之前**，必须重读本节判据原文 + integration-status
  对应行，逐项输出缺项清单（含：五格主 smoke、适用的作者配置、五件套×每格、并行冒烟、
  B8+ 韧性清单）——判据在磁盘上不等于在脑子里，对表是唯一保险。

## C. 通用铁律（两侧都适用）
- 一手证据 `文件:行号`，查不到写"来源待溯"，禁编造（#4/#11）。
- fixture 经真实序列化函数构造（D4/D5 判例）。
- 不改 third_party 算法核心，只做适配/观测插桩并留档。
- 冻结后推翻走版本化（frozen-v2）+ 影响分析 + 重跑，不在 adapter 内打
  格子专用补丁。
- resume/smoke/隔离清理是**框架**职责，不是 adapter。
