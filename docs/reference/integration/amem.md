# A-Mem 接入实例（B1-B11 逐项）

> 判据模板：`../method-integration-checklist.md` §B；勾选总表：`../integration-status.md`。
> 状态：**adapter 已落地，B1-B11 未正式过**——"已知事实"为 2026-07-13 架构师代码
> 取证预填，非验收结论。

- adapter：`src/memory_benchmark/methods/amem_adapter.py`（1,273 行）
- 算法源：vendored `third_party/methods/A-mem`（**复现版**，`memory_layer_robust.py`
  的 `RobustAgenticMemorySystem`，adapter:226）。顶层 `third_party/A-mem` 是**通用库版**，
  adapter 未用（双仓库判例：`../dual-track-config-policy.md` §7/§10）。
- native 格：**locomo**（唯一格）

## 0. 接口调用面（黑盒拆解，预填）

| 框架钩子 | adapter 行为 | 落到 A-Mem 官方接口 |
|---|---|---|
| `ingest(TurnEvent)` | consume_granularity="turn"（adapter:238）；per-conversation runtime 惰性创建（:314-322） | `runtime.add_note(content, time=timestamp)`（adapter:847，带 stdout 抑制） |
| `end_conversation` | **持久化**（非记忆构建）：`_save_conversation_state`（adapter:368-385） | pickle `runtime.memories`（:325 对应加载）+ `retriever.save/load`（:619/:332，`retriever.pkl`） |
| `retrieve(query)` | 问题文本转关键词查询（:910） | `runtime.find_related_memories_raw(keywords)`（adapter:466/:475） |
| clean-retry | registry `_clean_amem_failed_ingest_state`（registry.py:736） | 删 per-conversation state_dir |

## B1-B11 逐项（全部 ⬜ 待 M 阶段，下面只记已知事实/风险）

- **B1**：⬜。复现版仓库已选定并接对（政策 §7 一手核）；repo/commit/license 锁待做。
  OpenAI chat namespace 有透明包装用于 usage 观测（adapter:1169-1203）。
- **B2**：⬜。turn 单一粒度；add_note 无批量接口的已知通路，HaluMem memory_point
  预计 gap，待核。
- **B3**：⬜ **物理隔离**：per-conversation `RobustAgenticMemorySystem` 实例 +
  独立 state_dir（:314-322）+ pickle/retriever.pkl 持久化。恢复失败显式报错（:329）。
- **B4**：⬜ **有前科**：checklist B4 的"禁止 `str(context)` 不可审计塞法"判例主角
  就是 A-Mem——M 阶段必须核现 formatted_memory 构造是否已是结构化拼装 + 时间戳回带。
- **B5**：`provenance_granularity="none"`（adapter:239）→ recall/ndcg 预计 N/A。
  **B5+ 初判（2026-07-13 MemoryData 判例）：可无损改造**——note content 近 verbatim
  保存，可走 in-band header 或（更干净）adapter 侧 note id→source_ids 映射。见
  `ws02.7/notes/memorydata-recall-retrofit-survey.md` 策略①及其 embedding 污染注意。
- **B6**：⬜。end_conversation 只做持久化；add_note 是否同步完成 evolution/链接
  （无异步尾巴）待官方源码锚。
- **B7**：⬜。usage 经 chat.completions 包装拦截（:1187-1203），embedding 观测待审。
- **B8**：⬜。检索 find_related_memories_raw 是否触发 memory evolution（A-Mem 的
  卖点机制）**必须核**——若触发，属"算法固有状态变化"保留，但要留档声明。
- **B9**：⬜。内部 LLM（notes 构造/evolution）模型口径待声明。
- **B10**：⬜。native=locomo，来源=复现版仓库 `run_all_experiments.sh` 附近配置；
  reproduce-vs-paper 按 policy §5。
- **B11**：⬜。

## 特殊情况（M 阶段待办，policy §7 已登记）
1. 核 `memory_layer_robust.py`（复现版）与 `agentic_memory/`（通用版）是否同一核心
   算法；分叉则以复现版为准。
2. 顶层 `third_party/A-mem` 去留由用户定（架构师不擅自删非自建文件）。
3. pickle 持久化的跨版本兼容性（resume 场景）值得一个定向测试。
