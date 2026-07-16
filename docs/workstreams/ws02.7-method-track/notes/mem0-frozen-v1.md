# Mem0 method-frozen-v1 冻结记录

> 冻结日 2026-07-14(Fable 5)。**冻结语义**:自本记录起,改
> `mem0_adapter.py` / `mem0_native_prompts.py` / registry 的 mem0 注册行 /
> 两个已批 third_party 最小 diff,须在 ws02.7 README 断点区写解冻理由,
> 并重跑受影响格的 smoke。B1-B11 勾选终态见
> `docs/reference/integration-status.md`,逐项证据见
> `docs/reference/integration/mem0.md` 与 M1-M5 notes。
>
> **2026-07-15 后续勘误（不撤销 method 冻结）：**ADD-only 负空间审计证明当前生产
> memory mutation 仅新增 immutable id，但 sidecar 记录的是 ingest 批归属，不是每条
> 抽取 fact 的无损 turn 归因。LoCoMo/MemBench 保持 turn；LongMemEval 仅 session；
> BEAM turn Recall=N/A。既有受影响 retrieval metric 数字撤销为可信指标声明，其他
> answer/judge/F1/成本与 B1-B4/B6-B10 证据继续有效。现行裁决见
> `../branches/retrieval-metrics/notes/retrieval-metric-eligibility-ruling.md`。
>
> **2026-07-16 B4 局部重开：**MemBench 原 message 已内嵌 place/time，但
> `_turn_to_message()` 又前置 `[Turn time]`，形成同一 content 的重复时间；该 helper 在
> turn/session 同时有值时也双前置，未遵守 `turn_time → session_time → None` fallback。
> 原文 + typed channel 仍是正确 additive 设计；content-only message 则只应出现一个
> effective timestamp。冻结不整体作废，只重开 Mem0 的 MemBench/BEAM/HaluMem B4/B11
> 输入形态；修复后局部复证三格，LoCoMo/LongMemEval session-only 字节和既有 add-only
> 证据保留。裁决见 `../branches/membench-time-semantics/notes/
> membench-100k-time-ruling.md` §7。

## 1. 冻结时点的证据面(13 格 predict + 全指标)

- **unified 六格**:locomo / lme(s-cleaned) / membench(0-10k) /
  beam(100k) / beam(10m) / halumem(medium),run id `mem0-*-unified-s2*`
  (10m 架构师跑,余用户跑)。
- **par2 四格**:membench / locomo / lme / beam-100k(workers=2,
  per-worker sidecar 分立=物理隔离实弹);halumem ⑤=N/A(op-level 单
  worker 判例);10m 由 100k 覆盖(并行面与数据结构正交)。
- **native 三格**:locomo / lme / beam-100k(M4 bundle,prompt_track=
  native 实弹,BEAM 官方 builder 接入)。⑤轨别口径=unified 执行、native
  正交性声明覆盖(checklist B11⑤,2026-07-14 裁决)。
- **指标数字(smoke 只验管道,不看答对率)**:membench choice/source
  0.5、**membench-recall 0.167(全框架首个非零 recall)**;locomo f1 0.4
  /judge 0.0;lme recall/rank/judge 0.0(0.1 门槛空检索=官方声明语义);
  beam-100k f1 0.1/rubric 0.0、**beam-10m f1 0.4/rubric 0.1**(10m=
  beam 首个非空检索格);halumem extraction f1 **0.0192(mem0 非零抽取
  首秀)**/update 1/7/qa 1.0/memory-type 0.095;native 格免费六项落盘
  (locomo f1 0.014/beam f1 0.16/recall 类与 unified 同姿势)。
- 主树基线 **1164 passed**(2026-07-14,含 M3/M4/M0-13 全部测试)。

## 2. 方法身份要点(一手锚见各 note)

- 隔离形态=**worker 间物理、worker 内逻辑**(run_id namespacing=官方
  姿势=方法身份,M1 §3);clean 三件套=delete_all+批准 diff
  `SQLiteManager.delete_messages(session_scope)`+sidecar 清除。
- provenance sidecar：原生 id → ingest 批 source ids(M2),检索命中缺映射
  **fail-fast**——13 格全程未绊。它在单 turn 批是 turn semantic provenance；在
  LongMemEval 两 turn chunk 只安全向上聚合为 session，在 BEAM pair 不足以算 turn Recall。
- 时间口径：旧句“add 侧只进 metadata”已勘误。OSS `add()` 无独立 timestamp 参数，
  phased extraction 实际读取 parsed messages；adapter `_turn_to_message()` 已把公开
  session/turn 时间内联为 `[Session time]`/`[Turn time]`，并另存 metadata。MemBench 原
  place/time 文本保持不删，无时间 noise 保持缺失。retrieve 侧再提升 payload 对话时间到
  `created_at` 槽（M3，官方 Cloud/论文 reader 语义）。官方 OSS server 丢弃独立 timestamp
  字段仍是 upstream issue 候选，但不应再被表述成当前抽取链“metadata-only”。
- 注入粒度：locomo/membench=turn；lme/halumem 由 registry 声明 session，lme 在 adapter
  内按位置两 turn chunk；BEAM=pair；halumem=整 session 单次 add。
- B8+ 韧性:业务两 API 点(抽取 LLM/answer LLM)60s timeout+8 retries
  实锚到客户端;ingest 失败=failed_ingest 隔离+显式 retry 前全清理
  (M5 §1)。

## 3. 声明缺口清单(frozen-v1 携带,九项)

1. **B1 快照上游 commit 不可溯**(用户压缩包下载,2026-07-14 拍板):
   版本锁以 source_identity content-hash 为准(package 2.0.4,
   sha256 debda89…,146 文件);**5×10 矩阵完工后 git clone 最新
   upstream 对比 drift**(提上日程,目的=看漂移/上游修复,不改版本锁)。
2. **native 效率计量违规待修(R0 前置包)**:三格 injected tokens 统计
   串序列化≠官方 builder 实际嵌入段(政策要求"统计跟随实际嵌入段",
   M5 §2 三格对照表);记忆正文集合无漏,失配仅在时间/分组/编号排版。
3. **lme/beam native judge profile 未被 evaluate 消费(R0 前置包)**:
   `commands.py:213` 只认 locomo-judge;M4 profile 已注册为资产。
4. **B8+ 两个模型下载点无项目级韧性**(SentenceTransformer/FastEmbed
   BM25 首次缓存填充,M5 §1);BM25 下载失败=静默降级 sparse 检索且
   run 不留痕。缓解=本机缓存已热;**新机器/full 前必须预热预检**。
5. 真实 resume 验证缓期至预算批复(离线测试已钉,LightMem 同款)。
6. **top_k=20 vs retrieval-rank k≤50**:@30/@50 为截断语义,full 前
   裁决(声明子集有效 vs top_k 提 50 留痕偏离)。
7. mem0 官方 **0.1 相关性门槛**:空检索=声明语义非缺陷(store 层验尸
   结案,threshold None→0.1,官方 harness 同姿势)。
8. halumem 五件套⑤=N/A(op-level runner 单 worker 硬校验)。
9. embedding >512 token 截断警告风险 full 前复查(MiniLM 序列上限,
   与 LightMem 同款风险面)。

### 3.1 冻结后新增的 metric 资格勘误

- BEAM provenance recall=N/A（pair 批 id 并集会产生 turn-level 假阳性）。
- LongMemEval 只允许 session provenance；rank 另待真实保序与 evaluation depth 门。
- runner 的 `top_k=10` 使官方 k30/50 必然缺失；不得把已有 artifact 条目数冒充已覆盖。
- 上述是 metric 输出资格勘误，不改变 Mem0 add-only 算法身份或要求重跑真实 API。

## 4. R0 前置包(mem0 份)

R0(论文数字校准)启动前须修:缺口 2(计量跟随实际段)+缺口 3(judge
路由泛化)+旧论文 LoCoMo 路径(gpt-4o-mini)校准配置注册。与 LightMem
的 R0 前置包(lightmem judge profile 降级件)同批施工。

## 5. 校准回填指针

流水线实测数字已回填 `method-onboarding-assembly-line.md` §五(mem0=
二号煎饼终账:架构师批处理回合约 10,超计划 ≤6 约六成;超额部分主要是
一次性资产——M0-11/M0-13 框架债、对表/时刻表/B8+ 机制、native bundle
样板、五个用户深度问答落档——后续 method 不重复付费)。
