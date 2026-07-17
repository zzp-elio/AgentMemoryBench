# 通用 Metric Kernel + Answer Metric Pack M0 实现记录

> 施工 actor：Claude Code（本会话系统提示自报模型 = Opus 4.8，
> `claude-opus-4-8`；未跨模型切换、未使用 subagent、零真实 API）。
> 起点 worktree = `/Users/wz/Desktop/mb-actor-metric-pack-m0`，
> branch = `actor/metric-pack-m0`，从主树 `main` HEAD `568b95d` 自建隔离
> worktree（`e10110f` / `6d68a51` / `65f5805` 均为 HEAD 祖先，已核）。
> 按 `cards/actor-prompt-metric-kernels-m0.md` 全卡施工。

## 1. 做了什么

### 1.1 Recall@k 公共内核（新增 `evaluators/retrieval_metrics.py`）

benchmark/method 无关的单一 Recall@k 纯结果内核，不 import benchmark/method
adapter，也不读取 benchmark/method 名：

- `recall_at_k(groups, retrieved_items, top_k, *, source_id_projector=identity_source_id)`
  返回不可变 `RecallAtKResult(score, hit_count, gold_unit_count, source_ids,
  requested_top_k)`。固定语义：只消费 `retrieved_items[:top_k]`、`source_turn_ids`
  按原序展开、投影后稳定去重；重复 source id 不重复命中；multi-child group 命中
  任一 child 只计一个 official unit；unmatched group 永远 miss 但保留在分母；空
  `retrieved_items` 合法（非空 gold 时 score=0）；空 gold groups 一律 fail-fast，
  交由 benchmark 壳层先按官方政策处理。
- recall 比值复用 `gold_evidence_groups.group_recall_score`，命中判定复用
  `group_is_hit`，**不出现第二份 recall 公式**（`hit_count` 只是用同一
  `group_is_hit` 数出的分子，除法只在 `group_recall_score` 内发生一次）。
- `top_k_source_ids(...)` 与可选纯 `source_id_projector` 让调用方显式把 turn id
  投影到 session id 空间；默认 identity。projector 只变换公开 source-id 字符串。

四个 recall evaluator 迁移为调用同一入口，各自壳层保留原有语义、字段与数字：

- `locomo_recall.py`：删本地 `_source_turn_ids`；空 evidence 官方 score=1、
  `_session_prefix` session projector、`gold_unit_count`、empty/non-empty 计数与
  category 聚合不变。
- `longmemeval_recall.py`：删本地 `_source_ids`；`_abs`/canonical no-target
  剔除、419 分母披露、`_public_session_id` projector、`retrieved_source_ids`
  （改用 `sorted(recall_result.source_ids)`，值不变）不变。
- `membench_recall.py`：删本地 `_source_turn_ids`；empty-gold N/A、越界诊断、
  turn-only 与 `retrieved_source_turn_ids` 不变。
- `beam_recall.py`：删内联 source-id 推导；empty-gold N/A、unmatched/ambiguous
  计数、turn-only 与 `retrieved_source_turn_ids` 不变。

LongMemEval rank/NDCG 未迁移（卡明确不动）；`group_first_hit_rank` 仍留在
`gold_evidence_groups.py`。四个 recall evaluator 迁移前后 `84 passed`（本
worktree 补 gitignored `data/` 只读软链后）。

### 1.2 Answer Metric Pack M0

- 新增 `evaluators/answer_text.py`：把 `f1.py::normalize_answer` 迁为**唯一**
  实现（answer-text-v1），语义逐字保持（None→""、小写、去
  `string.punctuation`、删 `a/an/the/and` 完整 token、折叠空白）。新增
  `ANSWER_TEXT_PACK_VERSION="answer-text-v1"` 与 `normalized_tokens()`。
  `f1.py` 改为 `from .answer_text import normalize_answer` re-export，旧
  `from ...f1 import normalize_answer` 仍可用。
- `F1Evaluator` 改用公共 normalizer；计分数字零变化，score details 新增
  `metric_tier="framework_supplementary"`、`metric_pack_version="answer-text-v1"`
  （`strategy="standard_token_f1"` 与既有字段保留）。`LoCoMoF1Evaluator` 未动
  （官方 parity，保留自身 stemming/category）。
- 新增 `evaluators/answer_metrics.py`：
  - `NormalizedExactMatchEvaluator`（CLI `normalized-em` / metric
    `normalized_em`）：两侧 answer-text-v1 后精确相等记 1，否则 0；归一化 gold
    为空固定 0，details `empty_normalized_gold=true`，不产生空对空虚假满分。
  - `SubstringExactMatchEvaluator`（CLI `substring-em` / metric
    `substring_em`）：方向固定 `gold_in_prediction` = 归一化 gold 是归一化预测的
    **连续 token 子序列**；用 token 边界避免 `cat` 命中 `concatenate`；归一化
    gold 为空固定 0；details 记 `direction` 与两侧 tokens。
  两个 evaluator 都是 answer-level `evaluate(question, answer, gold)`，经既有
  `run_artifact_evaluation()` answer-level 路径离线复算，不构造 method、不
  retrieve、不读 `.env`。

### 1.3 registry 收窄启用面

- `f1` supported_benchmarks 从 `{beam, halumem, locomo, longmemeval}` 收窄为
  `{halumem, locomo, longmemeval}`（移除 BEAM——rubric 任务不启用通用 token-F1；
  MemBench 本就未在内）。
- 新增 `normalized-em` / `substring-em` 注册，supported_benchmarks 同为
  `{halumem, locomo, longmemeval}`，均离线、无 profile。三者实现类都不读 benchmark
  名，BEAM/MemBench 由 registry `create_evaluator` fail-fast。
- `evaluators/__init__.py` 导出两个新 evaluator 与 `ANSWER_TEXT_PACK_VERSION`/
  `normalized_tokens`。
- 移除 `tests/test_beam_registered_prediction.py` 的 `f1` registered-prediction
  流程断言与 `F1Evaluator` import（不删 F1 纯公式测试，不伪造替代分数），并同步
  该文件两处 docstring 中的 f1 描述。

## 2. §5 强反例覆盖

1. Recall core（`tests/test_retrieval_metric_kernel.py`）：top-k 截断、重复
   source id 去重、multi-child any-of、unmatched 分母、0 hit、session projector、
   `top_k_source_ids` 稳定去重、空 groups 拒绝、公共 API 无 benchmark/method 参数
   与 adapter import。
2. 四个 recall evaluator 迁移前后代表 fixture 数字/summary 不变：沿用既有
   `tests/test_{locomo,longmemeval,membench}_retrieval_recall.py`、
   `test_beam_recall.py`（LoCoMo empty=1、LME 419、MemBench 1/3、BEAM multi-child
   any-of 均由既有断言锁住，未改动这些数字）。
3. normalized EM（`tests/test_answer_metric_pack.py`）：大小写/标点/article/and/
   空白归一化、partial 不满分、归一化空 gold 不满分。
4. substring（同文件）：方向反例、token boundary（`cat`/`concatenate`）、连续
   token、多余预测上下文、空 gold。
5. F1 数字零变化 + pack identity + 旧 import 兼容（`tests/test_answer_f1.py`）。
6. registry 三项只允许 locomo/longmemeval/halumem，BEAM/MemBench fail-fast
   （`tests/test_evaluator_registry.py`）。
7. 最小 fake run 证明两个新 metric 经 `run_artifact_evaluation()` 写 score/
   summary、不读 `.env`、不重跑 method（`tests/test_answer_metric_pack.py`）。
8. 中文 docstring 全覆盖：定向自检含 `tests/test_documentation_standards.py`，
   全部新增/修改模块、类、函数、测试函数与 nested helper 通过。

## 3. 定向自检（唯一一次，原样输出）

```
uv run pytest -q tests/test_answer_f1.py tests/test_answer_metric_pack.py \
  tests/test_retrieval_metric_kernel.py tests/test_evaluator_registry.py \
  tests/test_artifact_evaluation_runner.py tests/test_locomo_retrieval_recall.py \
  tests/test_longmemeval_retrieval_recall.py tests/test_membench_retrieval_recall.py \
  tests/test_beam_recall.py tests/test_beam_registered_prediction.py \
  tests/test_documentation_standards.py
```

尾行：`159 passed in 20.74s`。`git diff --check` 无输出（exit 0）。

隔离 worktree 缺 gitignored `data/`：按 RetrievalEvidence M1 note 先例建立指向
主树 `data/` 的只读软链（`test_artifact_evaluation_runner.py` 的 longmemeval_s
smoke 与 `test_beam_registered_prediction.py` 的 100k/10m arrow 数据依赖它）。软链
未 `git add`（`git status --short` 显示为独立 `?? data`），不纳入本次 commit 的
显式路径。

## 4. 允许文件改动核对

生产（全部在卡 §6 允许列表内）：新增
`evaluators/{retrieval_metrics,answer_text,answer_metrics}.py`；修改
`evaluators/{__init__,f1,registry,locomo_recall,longmemeval_recall,
membench_recall,beam_recall}.py`。`gold_evidence_groups.py` 未改动（内核直接复用
其现有 `group_is_hit`/`group_recall_score`，无需迁移或 re-export）。

测试：新增 `tests/test_{retrieval_metric_kernel,answer_metric_pack}.py`；修改
`tests/test_{answer_f1,evaluator_registry,beam_registered_prediction}.py`；本 note。
`tests/test_documentation_standards.py` 只运行未改。四个 recall 测试与
`test_artifact_evaluation_runner.py` 未改（既有断言直接锁住迁移等价性）。

## 5. 偏差 / 停工点

无。卡内工作 100% 完成，定向自检干净通过，未触碰允许清单外文件。

## 6. subagent 使用

全程未使用 subagent，全部由主 actor 会话直接施工。
