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
