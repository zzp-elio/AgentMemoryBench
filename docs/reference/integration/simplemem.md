# SimpleMem 接入实例（B1-B11 逐项）

> 判据模板：`../method-integration-checklist.md` §B；勾选总表：`../integration-status.md`。
> 状态：**adapter 已落地（协议 v3 原生，五家中最新），B1-B11 未正式过**——"已知事实"
> 为 2026-07-13 架构师代码取证预填，非验收结论。

- adapter：`src/memory_benchmark/methods/simplemem_adapter.py`（772 行，唯一直写
  v3 `MemoryProvider` 的 adapter，无 Legacy 桥）
- 算法源：vendored `third_party/methods/SimpleMem`（text backend）
- native 格：**locomo、longmemeval、membench**（`simplemem/evolver` 等目录，逐格
  M 阶段核）

## 0. 接口调用面（黑盒拆解，预填）

| 框架钩子 | adapter 行为 | 落到 SimpleMem 官方接口 |
|---|---|---|
| `ingest(TurnEvent)` | consume_granularity="turn"（adapter:161）；per-isolation_key system 惰性创建（:184-186 dict） | `system.add_dialogue(speaker, content, timestamp)`（adapter:198-203） |
| `end_conversation` | 幂等守卫后 finalize（adapter:211-222，`_finalized_isolation_keys`） | `system.finalize()` **处理残余窗口**（B6 关键，已接） |
| `retrieve(query)` | **绕开 `ask()`** 直连检索器（adapter:227 起） | `system.hybrid_retriever.retrieve(query_text)`；retrieval_path 记录进 metadata（:250） |
| clean-retry | `clean_simplemem_conversation_state`（adapter:446）+ registry `_clean_simplemem_failed_ingest_state`（registry.py:858） | 删 per-isolation state dir |

## B1-B11 逐项（全部 ⬜ 待 M 阶段，下面只记已知事实/风险）

- **B1**：⬜。绕开 ask() 只用 add_dialogue+hybrid_retriever（公平性设计已落地）；
  repo/commit/license 锁待做。**文档滞后**：模块 docstring 仍自述"T1 骨架、后续补齐"
  （adapter:1-5），实际 ingest/retrieve 已是真实调用——M 阶段顺手修正 docstring。
- **B2**：⬜。turn 单一粒度（且 ingest 显式拒收非 TurnEvent，:191-193 fail-fast）；
  HaluMem memory_point 预计 gap。
- **B3**：⬜ **物理隔离**：per-isolation_key `SimpleMemSystem` + 独立 state dir
  （`_systems_by_isolation_key` / `_state_dirs_by_isolation_key`，:184-186）。
- **B4**：⬜。timestamp 经 `parse_simplemem_timestamp` 规整后入 add_dialogue（:197）；
  检索侧 `_format_simplemem_contexts/_format_simplemem_memory` 双格式化（:228-229），
  时间戳回带待核。
- **B5**：`provenance_granularity="none"`（adapter:163）→ recall/ndcg 预计 N/A。
  注意 native 格含 membench/locomo（recall 类 conditional evaluator 存在的 benchmark），
  确认 none 后这些格 recall=N/A 要在报告显式标。**B5+ 初判（2026-07-13 MemoryData
  判例）：可无损改造**——dialogue content 保存原文，同 A-Mem 走策略①或 id 映射。
  见 `ws02.7/notes/memorydata-recall-retrofit-survey.md`。
- **B6**：⬜ 初判**已接对**：滑窗设计下 finalize() 处理残余窗口，end_conversation
  已挂且幂等。M 阶段锚官方 finalize 实现确认语义。
- **B7**：⬜。配置强校验含 api_timeout/retries（:123-125）；usage 观测路径待审。
- **B8**：⬜。hybrid_retriever.retrieve 预期只读，待锚。clean-retry 钩子已挂。
- **B9**：⬜。llm_model/embedding_model_path 均强制显式（:103-105 fail-fast），
  embedding 是本地路径模型——M 阶段须分别盖章产品默认、Phase 1 framework override 与
  native 配置；不得再用“unified 一律统一 embedding”一句话掩盖 build identity。
- **B10**：⬜。native 3 格（locomo/longmemeval/membench）来源逐格取证；
  reproduce-vs-paper 按 policy §5。
- **B11**：⬜。

## 特殊情况
1. 唯一 v3 原生 adapter，可作后续新 method（MemOS/Letta/EverOS…）的参考实现形态。
2. answer_generator.py 的官方 answer 通路被有意绕开（常量引用 adapter:67 留档）——
   M 阶段 B1 里把"为什么不用 ask()/answer_generator"的官方行号锚补全。
