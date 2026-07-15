# Retrieval metric 资格与 provenance 架构裁决

> 日期：2026-07-15
> 裁决者：GPT-5 架构师
> 取证底：`mem0-provenance-validity-audit.md`、
> `retrieval-metric-eligibility-audit.md`、`lightmem-offline-recall-ruling.md`
> 状态：**裁决已生效；代码门尚未施工。**在下述 artifact contract 与 evaluator 门合入前，
> 不得把现有静态 `provenance_granularity="turn"` 当成跨 benchmark、跨 metric 的资格章。

## 1. 一句话裁决

**指标资格采用“provider 陈述运行时检索事实，evaluator 按 metric 要求判资格”的两层
模型；不建立手写 method × benchmark × metric 白名单。**Recall 需要当前检索条目的
semantic evidence provenance；NDCG 在此之上还需要真实保序和足够 evaluation depth。
任一条件缺失就输出带 reason code 的 `n_a` 或 `pending`，不为了填满矩阵改 method 算法。

## 2. 两份 actor 回卡的验收与勘误

### 2.1 Mem0 audit

Sonnet 5 commit `30f22dc`（主线 `dc15304`）通过强验收：commit 基点、单文件改动、
负空间搜索和 registry→adapter→vendored `Memory.add()` 控制流均可复证。当前生产配置
唯一可达的 memory mutation 是新增 immutable memory id；duplicate/空抽取只 skip，
`delete_all(run_id)` 只用于失败 namespace 重试前清理。

但任务卡给出的三选一标签 `ADD_ONLY_PROVEN` 把两件事合并了，属于**架构师卡口径过宽**：

- 已证明：`ADD_ONLY_MUTATION_PROVEN`——现路径不会把旧 memory 文本改写/删除后继续沿用
  旧 sidecar；
- 未普遍证明：每条抽取 fact 对 ingest 批内每个 turn 都有 semantic evidence 关系。

sidecar 实际记录的是 add 批次的 `source_turn_ids`。单 turn 批可作为 turn provenance；
pair/session 批的 id 并集只是批归属，不能自动喂 turn-level Recall。actor 在 note §6
主动暴露了这一点，交付无需返工，最终语义由本裁决收紧。

### 2.2 Framework metric audit

Sonnet 5 commit `0f8b382`（主线 `c36b171`）通过强验收。架构师逐项回读了 5 个 evaluator、
runner、LongMemEval 官方 `eval_utils.py`/`run_retrieval.py`，并只读扫描两份 cleaned 数据：
每份 500 题，均有 30 道 `_abs` 与 21 道无目标 user turn 的题。官方把后者整题剔除；
框架当前却把空 gold 的 recall/NDCG 全记 1.0 并留在分母，是真实 metric bug，不是
文档措辞差异。

`RetrievalQuery.top_k=10` 同时充当 answer 请求宽度和 evaluation depth 也已复证；
LongMemEval 官方 `k=30/50` 因 evaluator 按该字段过滤而必然缺失，即使 artifact 物理保存
60 个 item 也无效。

## 3. 两层资格契约

### 3.1 Provider/runtime 事实层

新增逐次 `RetrievalResult` 级 `RetrievalEvidence`，只陈述 method 实际能证明的事实，不
直接写某个 metric 是否及格：

1. `semantic_provenance`：`valid | n_a | pending`；
2. `provenance_granularity`：`turn | session | none`；只有 semantic provenance 为
   `valid` 时才允许 turn/session；
3. `stable_ranking`：`valid | n_a | pending`，表示 `RetrievedItem` 列表是否就是 method
   实际检索名次，未被 set 化或展示层二次重排；
4. 每个非 `valid` assertion 必须带稳定 `reason_code` 和可读 `reason`。

这是**逐题实际值**：空检索但映射机制完整仍可声明 provenance valid，表示真实 0 hit；
某次命中缺 lineage 则是 n_a，不能把空 `retrieved_items=[]` 偷换成 0 分。manifest 只保存
schema/version 与能力上限，用于 resume/isolated worker 交叉校验；不能覆盖逐题事实。

### 3.2 Evaluator requirement 层

- Recall：要求 semantic provenance=`valid`，且 granularity 能与该 benchmark 的 gold
  单位合法比较；不要求 stable ranking。
- NDCG/rank：在 Recall 条件之上要求 stable ranking=`valid`，并逐个 k 检查实际
  evaluation depth；Recall valid 不推出 NDCG valid。
- `n_a` 是确定不可无损获得；`pending` 是尚未完成一手审计。二者都不计 0 分，也不进
  scored denominator；summary 保留 reason code 与数量。
- `source_turn_ids/item` 与 unique-source 数作为 item 宽度审计统计，不冒充资格判定；
  未做 source/token budget 归一化前，Recall@k 仍是 method-native item 辅助指标。

### 3.3 对三个候选的裁决

- **拒绝候选 1（继续扩静态 method 字段）**：不能表达同 benchmark 内 post-update 和
  逐题缺 lineage，也仍把 Recall/NDCG 锁在一个标量上。
- **采用候选 2 的修订版（实例/逐次 capability bundle）**：与
  `consume_granularity` 的实例化模式一致，又能承载 LightMem 已经计算但未接通的逐题
  provenance 信号。
- **拒绝候选 3 作为权威源（独立 eligibility 白名单）**：它会成为与代码行为脱节的
  第二事实源，并随 10×5×metric 增长成手写笛卡尔积。evaluator 可以有通用 requirements，
  但不能维护“Mem0×BEAM×Recall=N/A”一类人工名单；该事实应由 provider runtime contract
  给出，再由 evaluator 通用判据导出。

## 4. 当前 method × benchmark 立即生效的资格裁决

| method/cell | semantic provenance 裁决 | Recall | NDCG/rank |
|---|---|---|---|
| Mem0 × LoCoMo | 单 turn add，immutable id→sidecar turn id | valid(turn) | pending：尚未独立验真实保序/depth |
| Mem0 × MemBench | 单 turn add，同上 | valid(turn) | benchmark 当前无该 rank 指标 |
| Mem0 × LongMemEval | session 内位置两 turn chunk；批内 turn 并集不能冒充 fact-turn，但都属于同一公开 session | valid(session)，不得报 turn-level | pending：保序未审；k30/50 亦缺 |
| Mem0 × BEAM | pair add 的两个 turn id 都挂到每条抽取 memory，可能命中未被该 memory 承载的 gold turn | n_a(turn metric) | N/A |
| Mem0 × HaluMem | whole-session batch 可作 session 容器归属；官方无 retrieval recall | benchmark N/A | benchmark N/A |
| LightMem × LoCoMo 主线 | post-build merge/update 后无 output-to-source semantic mapping | n_a | n_a |
| LightMem × 其余四格 | 不跑 LoCoMo post-build consolidation；初始 source id 透传未被本轮否定 | 维持既有声明，逐题缺 lineage 时 n_a | pending，须另验保序/depth |
| MemoryOS | 本轮未重审 M2 page sidecar，既有 turn provenance 不作废 | 维持既有声明 | pending，须另验保序/depth |

因此 Mem0 的 ADD-only 审计**不要求撤销整个 frozen-v1**；冻结状态改为携带一项明确
勘误：BEAM provenance recall 作废，LongMemEval 只能报 session 口径，直至新 contract
使 artifact 可复证。answer/F1/judge/成本、隔离与 add-only 结论均不受影响。

## 5. LongMemEval rank 的即时正确性门

1. `_abs` 与无目标 turn 两类都按官方剔除，不进任何 k 的 denominator；后者记录
   `status="n/a"`、`reason_code="official_no_target"`，不能记 0 或 1。
2. 现阶段只可声明实际覆盖的 k≤10；`30/50` 必须显式列为 unavailable，不能把整个
   evaluator 写成“官方全 k parity”。每个可用 k 的公式仍可标 official parity。
3. 不把 runner 字面量从 10 粗暴改成 50：这会改变 answer context；也不额外调用第二次
   retrieve：状态型 method 可能因此改变内部状态并增加成本。answer depth 与 evaluation
   depth 必须经协议显式拆分后再补 30/50。

## 6. LightMem “online soft update”裁决

当前术语必须纠正：

- `LightMemory.online_update()` 的实现是 `return None`；把配置改成 `update="online"`
  会让抽取出的 memory 不进入向量库，不是“温和插入”。
- 五个 benchmark 的初次 fact 持久化都使用 `update="offline"`，此处的
  `offline_update(memory_entries)` 实际只是 embed+insert。
- 只有 LoCoMo 主线在 conversation 结束后额外调用
  `construct_update_queue_all_entries()` + `offline_update_all_entries()` 做全库
  merge/delete/update；其余四格省略的是这一步，而不是改成 online 模式。

**主线继续保留 LoCoMo post-update。**官方 reproduction README 报告数字明确检索
`qdrant_post_update`，为了让 Recall 可算而改成 pre-update 会改变被测算法/profile，因果
方向倒置。若未来需要研究 consolidation 的收益，可单列
`lightmem-locomo-pre-update-ablation`，明确非 Phase 1 headline、不得与官方主线混报；
当前不为该 ablation 花真实 API 预算。

## 7. 施工顺序

1. M0：接通 `RetrievalEvidence` 协议、artifact 与三家已声明 provenance 的 adapter；
   evaluator 暂不切换。
2. 架构师强验收 M0 后再派 M1：五个 retrieval evaluator 改读逐题 contract，同时修
   LongMemEval no-target 分母、metric tier 与 k coverage。
3. M1 合入前，LightMem B5/B11、Mem0 的受影响 provenance metric 均不得重新盖章；
   不跑真实 API 来绕过结构门。
