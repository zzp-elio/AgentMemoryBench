# MemoryOS shared lifecycle/retrieval/HaluMem R1 implementation

日期：2026-07-20。入口：Codex GPT-5.6；未使用 subagent，未调用真实 API 或下载模型。

## 实现边界

- vendored `memoryos.py` 为显式 missing timestamp 增加窄兼容：普通省略参数仍取产品
  wall clock，adapter 显式传入 `None` 时不回填；`meta_data` 随 QA page 保存。
- `short_term.py` 不再把已存在的 `None` timestamp 改写；`updater.py` 迁移任一非空
  page，并原样保留 meta_data。没有改动 summary、continuity、merge 或 retrieval 算法。
- adapter R1 将 source turn ids 置入原生 page metadata；retrieval 只读取该原生字段，
  缺失 fail-fast。STM page 以 always_on、MTM page 以 ranked 导出；profile 和两类
  knowledge 只作 non_evidence product-memory view。
- shared retrieval helper 令 Recall 选择 `all(always_on) + first-k(ranked)`，没有把该
  规则写进任一 benchmark evaluator。MemoryOS adapter/source hash/observability wrapper
  均已变化，且 manifest adapter_version 升为 `conversation-qa-v2-shared-lifecycle`，旧
  state/run 因 identity 不匹配不能静默 resume。
- HaluMem operation runner 已消费 `RetrievalResult.items`；因此 update probe 现在获得
  以上完整结构化 product view，而非 formatted-memory 行拆分。memory_type 在全部
  extraction integrity 上游记录为 N/A 时返回清洁 N/A，不将 integrity 伪作 0。

## 离线验证

`uv run pytest -q tests/test_memoryos_adapter.py tests/test_halumem_evaluators.py tests/test_operation_level_runner.py tests/test_locomo_retrieval_recall.py -m 'not api'`

尾行：`132 passed in 7.40s`

另执行 `git diff --check`，通过。

## R1 follow-up（首轮 a3025d0 强验收驳回后）

- 首轮错误把 extraction N/A 当作 score JSONL 内的虚构行/`n_a`，而真实 evaluator 会写
  空 score records 与 summary `status="n/a"`；现改为严格读取
  `summary.halumem_extraction.json`，N/A 时 clean composite N/A，update-only 不再被误算。
- page timestamp 现先仅比较两个真实 turn time；任一真实值覆盖 session fallback，两个都
  缺失才使用 session，仍全缺才为 `None`。native event 路径同样从 metadata 区分 turn 与
  session time。
- real vendored capacity-crossing test 证明 user-only / assistant-only 均可迁移，保留
  原生 meta_data provenance；双空在 `add_memory` 入口拒绝。occurrence id 由 source ids
  哈希而来，不是 retrieval snapshot index。
- selection contract 允许的值收紧为 `always_on|ranked|non_evidence`；非法/空白/非字符串
  fail-fast，k=0 仍保留 always-on。operation-level update probe 测试锁定结构化 STM 与
  profile/two knowledge atoms，而非 formatted-memory 分行。

本轮验证：

`uv run pytest -x -q tests/test_memoryos_adapter.py tests/test_halumem_evaluators.py tests/test_operation_level_runner.py tests/test_locomo_retrieval_recall.py -m 'not api'`

尾行：`149 passed in 7.62s`

## R2 follow-up（R1 强验收收口）

- occurrence `item_id` 现为只由 canonical `source_turn_ids` 派生的
  `memoryos-page-<hash>`；STM/MTM 是 metadata layer，不再改变同一页的身份。
- capacity-crossing 改为分别令 user-only 与 assistant-only 真实迁入 MTM；双空及两侧
  纯空白均由 vendored `add_memory` 入口拒绝。
- 增加 adapter producer 测试：仅 STM 的 native retrieve 仍导出 always_on STM，且
  profile/user knowledge/assistant knowledge 为无 turn lineage 的 non_evidence 原子项；
  与 operation runner 的 items 消费测试共同形成生产链闭环。
- native TurnPair 与 converter 均锁定单侧真实 turn time 优先、双真实冲突 fail-fast；
  selector 对显式非 object metadata fail-fast，缺 metadata 仍是 legacy ranked。

本轮验证：

`uv run pytest -x -q tests/test_memoryos_adapter.py tests/test_halumem_evaluators.py tests/test_operation_level_runner.py tests/test_locomo_retrieval_recall.py -m 'not api'`

尾行：`154 passed in 9.83s`

R3：双空判定不再以 `str(None)` 代替缺失；`None`、空串与纯空白两侧均拒绝，单侧真实文本保持合法。

R4：真实 vendored backend 以固定 `get_timestamp` 锁定省略 timestamp 仍走上游 wall-clock，显式 `timestamp=None` 则保持 missing；两页均为完整非空 pair，未触发迁移或 API。

R5：main 无 API 全量门原始尾行：`2 failed, 1663 passed, 3 deselected, 2 warnings, 29 subtests passed in 149.88s`。真实 conv-26 converter 现为 215 页；旧 214 页算法跨 session 将 session_8 末尾 D8:39（Caroline, `No worries, Mel!...`）与 session_9 开头 D9:1（Melanie, `Hey Caroline, hope all's good!...`）错误配成一页。R1 的 `session_page_start` 使二者作为 user-only/assistant-only 两页各一次保留，因此更新两处旧总数断言并新增该边界语义断言；默认 STM capacity=10 下同一正确 workload 公式使 update batches 从 205 变为 206，并锁定 `pages - capacity + 1`；未改生产代码。

R5 定向验证：`uv run pytest -q tests/test_memoryos_locomo_smoke.py tests/test_memoryos_adapter.py -m 'not api'`；尾行：`80 passed in 7.61s`。测试临时只读链接 main 的忽略数据目录，运行后已移除。
