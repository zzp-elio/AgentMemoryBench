# Mem0 接入实例（B1-B11 逐项）

> 判据模板：`../method-integration-checklist.md` §B；勾选总表：`../integration-status.md`。
> 状态：**adapter 已落地（ws02.5 前），B1-B11 未正式过**——本文"已知事实"来自
> 2026-07-13 架构师代码取证，是**预填**，不等于验收通过；各项要在 Mem0 的 M 阶段
> 一手锚 third_party 源码 + 架构师验收后才置 ✅。

- adapter：`src/memory_benchmark/methods/mem0_adapter.py`（1,840 行）
- 算法源：vendored `third_party/methods/mem0-main`（官方 `Memory` 类）
- native 格：**locomo、longmemeval、beam**（来源=`memory-benchmarks` 当前 eval
  harness；老论文已进化不可复现，走 policy §4 case 3，**不看老论文**）

## 0. 接口调用面（黑盒拆解，预填）

| 框架钩子 | adapter 行为 | 落到 Mem0 官方接口 |
|---|---|---|
| `ingest(TurnEvent)` | consume_granularity="turn"（adapter:278）；speaker→user/assistant 交替角色映射（:486-491） | `Memory.add([message], run_id=isolation_key, metadata=…, infer=config.infer, prompt=observation_time_prompt)`（adapter:493） |
| `ingest(SessionBatch)` | turns 按 2 个一组切 chunk（:554-556） | 同上逐 chunk `Memory.add()`（:556） |
| `end_session` | HaluMem 用：返回本 session `add().results` 产出的记忆（adapter:575-592，`SessionMemoryReport`） | 无额外调用（复用 add 返回值） |
| `end_conversation` | —（无钩子；Mem0 add 即建，无缓冲） | — |
| `retrieve(query)` | 公开 Question 路径 :886/:892；v3 `_retrieve_native` :966/:972 | `Memory.search(...)` |

## B1-B11 逐项（全部 ⬜ 待 M 阶段，下面只记已知事实/风险）

- **B1**：⬜。接口选择已避开 chat 入口（直接 Memory.add/search）；官方 repo/commit/
  license 锁定待做。
- **B2**：⬜。turn 为主 + session batch 切 2-chunk；**HaluMem memory_point 管道已具备**
  （end_session 返回 add().results，:575）——这是五 method 中唯一现成的 session 级
  memory 报告通路，M 阶段核 results 结构是否满足 HaluMem 探针需要。
- **B3**：⬜ **逻辑隔离**（唯一一家）：共享 Qdrant collection `"mem0"`（adapter:406），
  按 `run_id=isolation_key` 分区（:596-599 namespace 登记）。M 阶段必核：官方 search
  的 run_id 过滤是否可信（third_party 一手锚）；**并行安全性依赖这个过滤**。
- **B4**：⬜。add 时带 observation_time prompt + session_time（:493-499），检索侧时间戳
  能否拿回待核。
- **B5**：`provenance_granularity="none"`（adapter:279）→ recall/ndcg 预计 N/A；M 阶段
  确认 search 返回结构确实无 source id 后正式定。
- **B6**：⬜。初判**无 flush 需求**（add 即抽取写入，无 offline 缓冲），M 阶段锚官方
  add 实现确认无异步/批处理尾巴。
- **B7**：⬜。adapter 内有 OpenAI usage 包装（:23 import OpenAI），三角色观测完整性待审。
- **B8**：⬜ **发现缺口（2026-07-13）**：registry 的 mem0 注册块**没挂
  `clean_failed_ingest_state`**（registry.py:739 起；A-Mem/LightMem/MemoryOS/SimpleMem
  四家都有，:736/:796/:827/:858）——而 checklist B8 恰以 Mem0 举例。逻辑隔离下失败
  重试如何清掉半写入的 run_id 分区，M 阶段必须补钩子或论证不需要并勘误 checklist。
- **B9**：⬜。`infer` 开关、embedding 维度（:88 embedding_dimensions 注释）等口径待声明。
- **B10**：⬜。native 3 格全走 `memory-benchmarks` 当前 harness；reproduce-vs-paper
  检查按 policy §5（预期结论：paper 已被 repo 取代，显式记录）。
- **B11**：⬜。

## 特殊情况
1. 逻辑隔离 + 无 clean-retry 钩子是当前最大风险组合（B3×B8），M 阶段第一优先。
2. Mem0 是 native 格最多的 method（3 格），双轨工作量最大。
