# SimpleMem text v2 实现记录

> 状态：离线实现、真实 B11 与冻结门均通过；最终验收见
> [`simplemem-frozen-v1.md`](simplemem-frozen-v1.md)。

## 1. 产品算法与接口

Phase 1 直接调用 text product 的 `add_dialogue(speaker, content, timestamp)`、`finalize()` 与
`hybrid_retriever.retrieve(query)`；不调用产品答题器。产品 buffer 达到 window_size 后由 LLM
把一组 dialogue **重新合成为**若干 MemoryEntry（`memory_builder.py:132-215`），不是一条
turn 对应一条 memory。

## 2. 五格公开输入映射

- 每个 canonical turn 独立传入；speaker 直接取 LoCoMo speaker name，其他 benchmark 取
  canonical user/assistant。接口不要求交替，不需要 placeholder。
- content 原样保留并通过共享 helper 添加图片 caption；MemBench 原 place/time 尾注不删。
- typed timestamp 严格按 `turn_time → 当前 session_time → None`。adapter 支持 ISO、
  LongMemEval、BEAM、LoCoMo 与 MemBench 已审计格式；非空但未知格式 fail-fast，None 原样进入。
- formatted_memory 显式回带产品可取出的 timestamp/location/persons/entities/topic，不用
  `str(context)` 隐式塞入。

## 3. 指标资格裁决

MemoryEntry 是语义融合结果，产品没有 output-to-source-membership；仅知道哪些 dialogue
进入过生成 prompt，不能证明最终条目仍承载每个 source fact。因此
`provenance=none`，LoCoMo/LongMemEval/MemBench/BEAM 的 Recall/NDCG 一律诚实 N/A。

hybrid retriever 会并行执行多条生成查询，用 `as_completed()` 收结果，再与 keyword/structured
结果去重（`hybrid_retriever.py:559-641`）；没有跨通道统一 score 或全局 rerank。当前列表能供
answer reader 使用，但不能宣称稳定排名，故 `stable_ranking=pending`，不是 valid。

## 4. HaluMem session extraction

HaluMem 每个 session 结束时调用产品 `finalize()`，把尚未满 40 条的当前 buffer 合成为产品
MemoryEntry；adapter 只上报本 session 新增的 entry id。为避免产品的
`previous_entries` 把上一 session 的生成结果带进下一 session extraction prompt，session
报告后只清空该 extraction-context 缓存；LanceDB 中的既有长期记忆不删除，update/QA 仍能检索
完整 conversation 历史。该边界不改生成算法，只把 benchmark 的真实 session 边界映射到产品
已有 finalize 入口。

## 5. transport、隔离与 build identity

- 每 conversation 独占 state dir、LanceDB 与 product system，W2 无共享写状态。
- 产品 OpenAI client 强制使用项目 endpoint/timeout、SDK retry=0；产品自己的显式 retry loop
  以 `api_max_retries + 1` 次总尝试实现“首次 + N 次重试”的框架语义。
- embedding observer 包装真实 `EmbeddingModel.encode`，不是估算伪调用。
- 当前主 profile 固定项目 controlled MiniLM：`models/all-MiniLM-L6-v2`、384 维、模型内部 L2
  normalize、LanceDB L2。SimpleMem 官方默认 Qwen3 embedding 属产品/效果阶段差异，不能把
  当前 smoke 冒充 paper/product-default parity；manifest 写
  `controlled_embedding_v1/local_unpinned`。

## 6. 离线验收

与 A-Mem 共用同一批回归门：最终主树
`1679 passed, 3 deselected, 1 warning, 29 subtests passed in 130.50s`，compileall exit 0，
`git diff --check` clean。强反例覆盖五种时间格式、未知格式、caption、speaker、None、
session delta、跨 session extraction context、provenance N/A、ranking pending、真实 embedding
observer、endpoint/timeout 与产品 retry 映射。

## 7. 首轮真实 import 断点

首个 LoCoMo 真实 smoke 在任何产品/API 调用前 fail-fast：
`ModuleNotFoundError: dateparser`。根因是主项目依赖表漏收官方 text product 已声明的
`dateparser`；此前测试全部注入 fake `system_factory`，没有执行官方 `main.py` 顶层
import。

主项目现显式声明 `dateparser>=1.2.2` 并更新 `uv.lock`；新增隔离 subprocess 强反例，
真实导入 `SimpleMemSystem`。失败 run
`simplemem-locomo-v2-r3q1-w1` 保留为 aborted 诊断资产，不进入 B11 roster。

## 8. 首轮真实 keyword 断点

依赖修复后的 LoCoMo 哨兵完成了 prediction，但开箱发现产品仍调用
`create_fts_index(use_tantivy=True)`。LanceDB 0.34 已删除该旧 backend：建索引异常被
产品吞掉，随后 keyword search 再次吞异常并退化为 0 hit。该 run 因而也不进入 B11 roster。

vendored text product 只作版本兼容：改用 LanceDB native FTS，保留 `en_stem` tokenizer、
索引列、BM25 查询与 top-k，不改 multi-view retrieval 算法。由于 SimpleMem repo 按项目规则
local-only，兼容 diff 作为可追踪的
`scripts/patches/simplemem-product-compat.patch` 由
`scripts/fetch_third_party_methods.sh` 在固定 upstream commit 后幂等应用；不是只留在本机
worktree。零 API subprocess 门先用 `git apply --reverse --check` 验证当前 vendored bytes
确由该 patch 可重建，再用真实 LanceDB 写入一条 MemoryEntry，断言 native FTS 建成且 keyword
query 命中。

同一哨兵还暴露 retrieval `ThreadPoolExecutor` 不自动继承 ContextVar：semantic retrieval
真实执行但 embedding observation 丢失。vendored 兼容层只在 retrieval submit 时用独立
`copy_context().run(...)` 传播当前 scope；任务集合、worker 数、`as_completed` 顺序与
算法返回值均不变。subprocess 强反例断言两个并发 query 都能读取调用线程的 scope。

官方另有 `add_dialogues_parallel()`：多个新窗口同时执行时只看到提交前同一份
`previous_entries`，不等价于顺序的“重叠窗口 + 上一窗口生成记忆”链。当前 adapter 逐 turn
调用 `add_dialogue()`，达到窗口阈值时走同步 `process_window()`，该 batch-parallel build
路径不可达；主 TOML 与 `SimpleMemConfig` 默认值仍显式锁为
`enable_parallel_processing=false`，防止 manifest 误导或未来入口漂移。检索的
multi-query parallelism 是论文 Stage 3 的独立能力，继续启用。这里不修改、不背书产品
batch-parallel build，也不把它写成当前 build 的实际并行能力。该哨兵同样仅作诊断资产。

## 9. 真实 B11 收口

2026-07-23 完成 11 个正式真实 run：LoCoMo、LongMemEval、MemBench 各 W1/W2，
BEAM 100K/10M 各 W1/W2，HaluMem Medium 固定 W1。统一机器门逐 run 复核 completed
checkpoint、W2 物理 worker state、LanceDB row、source/build identity、适用 evaluator、
N/A/pending 传播与效率 observation。

HaluMem 四个 session 分别上报 2/2/2/3 条新合成 memory，长期 LanceDB 累计 9 条；
7 个 update probe 均检索这 9 条当前长期记忆。judge observation 精确为
`extraction=114 / update=7 / QA=1`，总计 122；Event/Persona/Relationship memory type
和 `Memory Boundary` QA type 均单独落盘。完整 roster、机器门与失效触发器见冻结记录。
