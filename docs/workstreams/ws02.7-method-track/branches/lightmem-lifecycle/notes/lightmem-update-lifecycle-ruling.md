# LightMem update lifecycle × retrieval metric 架构裁决

> 日期：2026-07-15
> 裁决者：GPT-5 架构师
> 一手证据：`third_party/methods/LightMem/lightmem.pdf` 第 5、7、8 页；
> `experiments/longmemeval/{run_lightmem_gpt.py,offline_update.py}`；
> `experiments/locomo/{add_locomo.py,search_locomo.py,readme.md}`；
> `src/lightmem/memory/lightmem.py`。
> 既有审计：`lightmem-offline-recall-validity-audit.md`（Claude Sonnet 5）。
> 状态：**裁决生效；代码尚待 actor 卡施工。零真实 API。**

## 1. 一句话裁决

**Phase 1 五个 benchmark 的 LightMem 主 profile 统一采用论文原生的
`online_soft`：完成预压缩、topic segmentation、抽取与直接 LTM insert，但不执行
全库 offline consolidation。LoCoMo 的 post-build consolidation 保留为明确另名的
`locomo_offline_consolidated` 补充轨，后续有价值再补，不与主 profile 混报。**

这不是为了“点亮 Recall”而删算法：online soft 本来就是论文定义、LongMemEval 表 2
正式报告的 LightMem 模式，也是 LoCoMo 官方脚本主动保存的 pre-update 状态。采用它的
主因是五格共享同一生命周期、适配 HaluMem 的增量时序，并把不透明的睡眠期改写从主
cross-benchmark 比较中隔离；provenance 可审计只是随之得到的正确后果。

## 2. 论文原文证明了什么

### 2.1 算法定义

论文第 5 页 §3.3 把两个阶段写得很清楚：

1. **Soft Updating at Test Time**：memory entry 到达时直接插入 LTM；
2. **Offline Parallel Update**：等全部 entry 插入或触发器到达后，建立 update queue，
   再并行执行 update。

因此 online soft 不是 `online_update()` 这个函数名所代表的东西，而是一种**直接插入、
推迟全库整合**的算法生命周期。

### 2.2 实验不是“offline 独占”

- LongMemEval 表 2（论文第 7 页）明确说明：每组 `r/th` 有两行，第一行是
  **online soft update**，第二行 `OP-update` 是 offline update。两者都有 ACC；offline
  并不单调更好，例如 GPT `r=0.6, th=256` 从 67.78 降到 65.39。
- LoCoMo 表 3（第 8 页）为节省篇幅把 update 前后合并成一行，**只把 post-update ACC
  作为论文表内数字**。这证明 post-update 是 LoCoMo 的 paper headline，但不能反推
  pre-update 不是官方模式。
- LoCoMo 构建脚本先生成 `qdrant_pre_update` 备份，再在
  `qdrant_post_update` 上整合；`search_locomo.py` 自身默认 pre-update，而 README 报告
  命令显式选 post-update。官方仓库同时保留两种时点，命名/默认存在漂移，实验声明必须
  显式写 profile，不能靠目录默认猜。

## 3. 论文术语到代码的真实映射

| 语义 | vendored 入口 | 实际行为 | 项目命名 |
|---|---|---|---|
| online soft update | `add_memory()` → 配置值 `update="offline"` → `offline_update(memory_entries)` | 对新 fact 做 embedding 并 insert；不改旧 entry | `online_soft` |
| 名为 online 的空壳 | `online_update(memory_entries)` | `return None`，不持久化 | 禁止作为 profile |
| offline parallel update | `construct_update_queue_all_entries()` + `offline_update_all_entries()` | LLM 决定 update/delete；会改写或删除旧 entry | `locomo_offline_consolidated` |

所以项目实现 `online_soft` 时**必须继续给上游 backend 传 `update="offline"`**。把它改成
`update="online"` 会让 memory 根本不入库；正确改动是停止额外调用全库 consolidation，
不是按函数名换配置值。

当前 adapter 已经让 LongMemEval、BEAM、MemBench、HaluMem 走 direct insert only；只有
LoCoMo 在 conversation 末尾额外运行全库 consolidation。施工的实质是把 LoCoMo 主线
也切到同一 paper-online-soft 时点，并保留显式 opt-in 的旧补充轨。

## 4. 为什么主 profile 统一 online soft

1. **原生性**：论文正式定义并在 LongMemEval 报分，不是本项目自创的 direct-ingest
   baseline；它仍完整运行 LightMem 的 compression、topic segmentation、STM extraction
   和 LTM indexing。
2. **跨 benchmark 一致性**：五格都能在“新 entry 已可检索、睡眠期整合尚未触发”的同一
   生命周期截面比较；不再因为 LoCoMo 有静态 build 尾点，就让它独享一次额外算法阶段。
3. **增量语义正确**：HaluMem 的 session 注入与 QA 交替，逐 session 做全库整合会造成
   反复改写和近似二次成本；online soft 与论文所说的低延迟 test-time 路径一致。
4. **结果不偷换**：所有 run/manifest/report 必须标 `online_soft`。后续补
   `locomo_offline_consolidated` 时使用独立 run_id 和 resume identity，只能横向看
   consolidation 的增益/代价，不能拿 post-update 数字冒充 online-soft。

论文 LoCoMo headline 仍有复现价值，因此不是永久删除 offline；只是 Phase 1 不必为了
复现单篇论文的一个表内时点，让跨五 benchmark 主矩阵承担不可审计的 mutation。

## 5. Recall/NDCG 的资格边界

### 5.1 online soft 让 Recall 成为“可审”，不等于“自动有效”

direct insert 后，当前 payload 的 `memory`、embedding 与抽取阶段给出的
`source_external_id` 没有再经历 merge/delete/update，消除了旧 LoCoMo post-update 的
两类假映射：candidate 文本进入 target 却无 candidate id，以及 target 文本被改写却仍
保留旧 id。

但逐题仍须满足：

- 检索命中都带合法 `source_external_id`；任一 hit 缺失时整题 provenance 记 `n_a`，
  不把部分 lineage 当完整 lineage；
- source id 是抽取 prompt 对当前 fact 的语义锚，而不只是 ingest batch 的 id 并集；
- 空命中 `items=()` 可保持 provenance capability valid，表示真实 0 hit；`items=None`
  才表示本次映射不可用。

LightMem 官方 prompt 明确要求每条 fact 返回 `source_id`，项目观测 sidecar 把它映射到
公开 turn id；因此 online-soft 下有一条可审计的 fact→turn 链。它仍属于
method-native item Recall：不同 method 的一个 item 覆盖宽度不同，报告必须同时披露
unique source 数与 `source_turn_ids/item` 分布，不能把 Recall@k 单独当 headline。

### 5.2 NDCG/rank 仍是 pending

online soft 只解决 semantic provenance 的 mutation 风险，不证明 adapter 返回顺序完全
等于 method rank，也不解决 runner `top_k=10` 挡住 LongMemEval k=30/50 的问题。正式
rank 审计与 answer/evaluation depth 拆分前，NDCG/rank 仍为 `pending` 或 depth-specific
unavailable，不能由 Recall valid 推导出来。

### 5.3 HaluMem

HaluMem 继续按 session 整批调用 LightMem，并在 session 末 force segment/extract，旁听
本次成功插入的 memory 作为 `session_memory_report`。这是 online-soft 的自然姿态；
HaluMem 当前没有 provenance Recall/NDCG，不能因为 session capture 可用就强造指标。

## 6. 已撤销方案与保留结论

- Sonnet 5 commit `3e2d957` 忠实实现了旧卡的 plural input-lineage union，架构师复跑
  `57 passed, 1 warning`；但用户指出“输入 id 并集不证明新 memory 仍承载各 source
  fact”，反例成立，commit **不合入**。若未来保存该并集，只能叫
  transformation-input lineage，不得喂 Recall/NDCG。
- post-update profile 仍无法从官方输出无损恢复 semantic mapping，所以它的
  provenance Recall/NDCG 保持结构化 `n_a`；answer/judge/F1/成本仍可评。
- MemoryData 的 direct 模式绕过 LightMem `add_memory()`、直接写原文 chunk，只能参考
  sidecar 手艺，不能作为 LightMem online-soft 的算法或数字校准。
- `consume_granularity`、`provenance_granularity`、retrieval item granularity 继续分离；
  不把 Recall 与输入粒度强制相等。

## 7. 施工与依赖顺序

1. 先派 `../cards/actor-prompt-lightmem-online-soft-profile.md`：把 profile 变成显式配置、
   LoCoMo 主线停止全库整合、manifest/resume 盖新身份；零真实 API。
2. 架构师强验收并合入后，才解锁
   `../../retrieval-metrics/cards/actor-prompt-retrieval-evidence-contract-m0.md`；M0 按
   **实际 lifecycle profile + 逐题 items** 陈述 provenance，不再把 LoCoMo 静态写死 N/A。
3. M0 强验收后才派 evaluator M1。真实 LightMem 五格 run 继续等用户明确预算、规模和
   run_id；本裁决本身不授权 API。
