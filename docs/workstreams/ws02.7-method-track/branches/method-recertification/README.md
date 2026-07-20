# Method 逐项重认证支线

## 目的

共享协议、lifecycle、时间、provenance、metric eligibility 与 track identity 在首轮
method-frozen 后发生了实质变化。旧证据不删除，但不能靠历史 ✅ 惯性宣布当前版本仍冻结；
本支线按**当前主线 commit**逐 method 重走 B1-B11，做到“慢就是快”：一次只压实一家，
前一家没有完成对表与强验收，后一家不施工。

## 重认证不是盲目从零重跑

每个 B 项必须落入四种状态之一：

1. `revalidated`：相关源码/配置/契约未变，旧一手证据已在当前 commit 重新抽锚；
2. `retested`：改动面或风险面已用当前代码定向/全量/产物重新验证；
3. `N/A`：method × benchmark × metric 不具备诚实资格，写明原因；
4. `pending`：仍依赖预算、上游资产或共享框架门，不用假 ✅ 填格。

只有受改动影响的 build/smoke 才重烧；字节与身份均未变的资产不为“重新开始”重复付费。
每家最后仍执行 checklist B11 对表仪式，更新 integration 实例页、总表与 frozen note。

## LightMem 首家摊销规则：后续 method 只验差量

LightMem 是 method 重认证的第一家，也承担五个 benchmark 的“探路/校准”成本。它逐格压实后，
下一个 method **不得再从零重做同一份 benchmark 调查**。证据按两层复用：

1. **benchmark 稳定层只验 source lock 是否漂移**：raw schema、已知异常与真实位置、canonical
   public id、Gold Evidence Group、私有字段边界、官方 answer/judge prompt、metric 分母、smoke
   裁剪轴、variant 关系等，统一复用 `docs/survey/`、benchmark frozen note 与 shared tests；
2. **method × benchmark 差量层才是每家责任**：该 method 的 ingest 粒度、role/content/time/image
   渲染、lifecycle、隔离/flush、product retrieve/readout、provenance/ranking 资格、运行 identity 与
   backend 特有异常。

后续 method 仍须逐格执行最小真实 smoke，因为 backend、state、并发、flush、readout 与观测不能
由 LightMem 代证；但 smoke 只覆盖该 method 尚未证明的 runtime 性质，不为“仪式完整”重复烧
LightMem 已关闭的异常样本。只有三类触发器允许重开 benchmark 稳定层：**source lock/官方资产
变化、shared canonical/evaluator/prompt contract 版本变化、出现能推翻旧判词的新一手反证**。
任务卡必须列“复用事实”和“本卡差量”，禁止把旧 census 换个文件名再做一遍。

## 串行顺序与门

1. 共享门 Track identity M0、canonical turn / Gold Evidence Group 与 RetrievalEvidence
   M1 均已强验收关闭；M1 主线为 `5d8fce3` + `e10110f`。
2. **LightMem 第一家**：重点重验 online-soft 主 profile、missing-time 扩展、逐题 evidence、
   canonical-required MiniLM build identity、五 benchmark B4/B5/B6/B9/B10/B11。
3. **Mem0 第二家（已完成）**：current-v3 已关闭 source-time、caption、role、provenance、
   truthful identity、operation clean retry 与五格真实 B11，冻结为 `method-frozen-v2`。
   product-default OpenAI embedding 属效果阶段，若切换须用户批预算并全量重建，不阻塞 smoke。
4. **MemoryOS 第三家**：PyPI product identity、speaker/provenance sidecar、降级审计、
   readout-native 与五格 smoke 一次收口；ChromaDB variant 不混入主轨。五格差量拓扑统一从
   [`memoryos/README.md`](memoryos/README.md) 进入。
5. **A-Mem → SimpleMem**：各自补全 product/reproduction identity 后重走 B1-B11。
6. 现有五家压实后，再接 MemOS、Letta/MemGPT、LangMem、Supermemory；EverOS 最后。

## 当前状态

LightMem current-v7 已冻结为 `method-frozen-v3`；Mem0 current-v3 的 8 个真实 run、全部适用
metric/judge、worker state 与 artifact 开箱也已关闭，冻结为 `method-frozen-v2`。**MemoryOS 现为
唯一 active method**：复用前两家已压实的 benchmark 稳定层，只做其 PyPI product identity、
forced-pair/session 映射、readout/provenance 与五格 runtime 差量，不再重做 dataset census。
权威实时动作仍看父级 `../../README.md` 恢复胶囊与最新断点。
