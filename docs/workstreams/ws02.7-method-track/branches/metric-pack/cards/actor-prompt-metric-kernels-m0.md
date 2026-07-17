# Actor 卡：通用 Metric Kernel + Answer Metric Pack M0

> **给当前 actor 的执行指令：你就是用户已选中的执行者。** 本卡被发送到当前 actor
> 会话即代表用户已经完成选择与授权，请直接施工；不要再选择、派发或等待另一个 actor。
> 本卡是可整份复制的自包含 prompt，单批上限 5h，零真实 API。actor 可自行决定是否使用
> subagent；subagent 不得扩大 scope，发生实质使用时须在完成报告披露，主 actor 对最终 diff
> 和报告负责。

## 0. 这张卡解决什么

用户对“通用指标”的裁决是：**公式实现不绑定 benchmark/method，但启用资格必须尊重任务
语义**。当前代码已有两层正确公共基座：

- `gold_evidence_groups.py::group_recall_score()` 已实现 benchmark-agnostic group any-of Recall；
- `retrieval_evidence.py` 已统一逐题 semantic provenance、granularity、stable-ranking 资格门及
  retrieval artifact 强校验。

因此本卡不是重写 Recall，也不是把四个 benchmark evaluator 合成一个万能类。目标分两步：

1. 抽出剩余真正公共的 top-k source-id 投影 + Recall@k 纯结果内核，让四个 Recall evaluator
   调同一公式入口，同时保持各自 gold view、empty-gold、abstention/no-target、category、tier、
   summary 字段与输出语义不变；
2. 新增 artifact-only `normalized-em` 与 directional `substring-em`，与现有通用
   token-F1 共用一个版本化 normalizer；同时从 registry 移除 BEAM 的通用 F1 启用资格。

本卡完成后，已有 prediction run 只要保留标准 answer artifacts，就能重新 `evaluate` 新答案
指标，不重跑 method。Retrieval 指标仍要求 v1 answer-prompt/gold/evidence artifacts。

## 1. 上工顺序与 git 隔离

只按顺序读：

1. `AGENTS.md`；
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊；
3. 本支线 `README.md` 与本卡全文；
4. `docs/reference/actor-handbook.md` §0-§4；
5. `docs/reference/metric-extension-plan.md` §1-§5，尤其 §2.1；
6. `../../retrieval-metrics/notes/retrieval-evidence-m1-implementation.md` §1-§3、§7；
7. 本卡允许清单内生产代码和测试。

从届时最新 main 自建隔离 worktree。路径/分支已存在就停工，不删、不复用：

```bash
git -C /Users/wz/Desktop/memoryBenchmark worktree add /Users/wz/Desktop/mb-actor-metric-pack-m0 -b actor/metric-pack-m0 main
cd /Users/wz/Desktop/mb-actor-metric-pack-m0
uv sync
```

开工记录 `git rev-parse --short HEAD`，并确认 main 已包含 RetrievalEvidence M1、Gold v1 与当前
LightMem caption v6 链；若 `e10110f`、`6d68a51` 或 `65f5805` 不是 HEAD 祖先，停工报告。

## 2. Recall@k 公共内核裁决

新增 `src/memory_benchmark/evaluators/retrieval_metrics.py`（名称可按同目录风格微调，但只能有
一个公共实现）。它不得 import benchmark adapter、method adapter 或读取 benchmark/method 名。

公共入口接受：

- 非空 `tuple[GoldEvidenceGroup, ...]`；
- 已经 `validated_retrieval_fields()` 校验后的有序 `retrieved_items` 与正整数
  `top_k`；
- 可选纯 `source_id_projector(str) -> str`，默认 identity，用于调用方显式把 turn id
  投影为 session id。

它返回不可变的结构化结果，至少包含：`score`、`hit_count`、`gold_unit_count`、
稳定去重后的 top-k `source_ids` 和 requested `top_k`。固定语义：

1. 只消费 `retrieved_items[:top_k]`，每项 `source_turn_ids` 按原序展开；重复 source id
   不重复计命中，multi-child gold group 命中任一 child 只计一个 official unit；
2. unmatched group 永远 miss 且保留在分母；
3. 空 `retrieved_items` 合法，非空 gold 时 score=0；空 gold 不在公共内核自行决定
   0/1/N/A，必须拒绝，由 benchmark 壳层先执行自己的政策；
4. 复用现有 `group_is_hit/group_recall_score`，或把它们无损迁入公共模块并保留兼容
   re-export；禁止出现第二份公式；
5. projector 只变换公开 source-id 空间，不读 metadata/gold answer，也不按字符串猜 benchmark。

迁移 `locomo_recall.py`、`longmemeval_recall.py`、`membench_recall.py`、
`beam_recall.py` 使用该入口。以下内容必须继续留在各自壳层：

- 选择 `(provenance_granularity, unit_kind)` gold view；
- LoCoMo empty evidence 官方 score=1；
- LongMemEval `_abs`、official no-target 与 canonical 419 分母；
- MemBench/BEAM empty-gold N/A、越界/歧义诊断；
- LoCoMo/LME 各自不同的 session-id projector；
- metric name、tier、official source、category breakdown 与已有 summary/record shape。

**禁止为了统一改变任何已有 metric 数字、分母、N/A/pending reason、top-k distribution 或
artifact key。** LongMemEval rank/NDCG 本卡不迁移；它已有共享 group-rank 原语，且
stable-ranking/depth 语义不同。

## 3. Answer Metric Pack M0

### 3.1 唯一 normalizer v1

新增公共 answer-text 模块（建议 `answer_text.py`），把现有
`f1.py::normalize_answer()` 迁为唯一实现；`f1.py` 必须兼容 re-export，现有 import
不得破坏。v1 语义逐字保持：

- `None -> ""`，其它值 `str()`；
- lowercase；
- 仅按 Python `string.punctuation` 去 ASCII 标点；
- 删除完整 token `a/an/the/and`；
- whitespace collapse。

不要加 stemming、Unicode normalization、中文分词、同义词或 category 特判。所有
supplementary answer metric 的 score details 写：

- `metric_tier="framework_supplementary"`；
- `metric_pack_version="answer-text-v1"`；
- normalized prediction/gold 与具体 strategy。

现有 `F1Evaluator` 改用公共 normalizer，并补上述稳定身份；计算数字必须零变化。
`LoCoMoF1Evaluator` 是官方 parity，保留自己的 stemming/category 逻辑，**不得**改成公共
supplementary normalizer。

### 3.2 `normalized-em`

新增 benchmark-agnostic evaluator，CLI 名 `normalized-em`，artifact metric name
`normalized_em`：两侧经 answer-text-v1 后精确相等记 1，否则 0。若 normalized gold 为空，
固定记 0 并在 details 标 `empty_normalized_gold=true`，不得产生空对空虚假满分。

### 3.3 directional `substring-em`

新增 benchmark-agnostic evaluator，CLI 名 `substring-em`，artifact metric name
`substring_em`。方向固定为 **normalized gold 是 normalized prediction 的连续 token
子序列**：

- gold=`Seattle`、prediction=`Alice moved to Seattle in 2023` → 1；
- 反方向 prediction=`Seattle`、gold=`Seattle in 2023` → 0；
- gold=`cat`、prediction=`concatenate` → 0，禁止裸字符误命中；
- normalized gold 为空 → 0；
- details 明写 `direction="gold_in_prediction"` 与两侧 tokens。

### 3.4 任务适用面

registry 中 `f1`、`normalized-em`、`substring-em` 都只启用：

```text
locomo, longmemeval, halumem
```

三者实现类本身不得读取 benchmark 名。BEAM 是 rubric/结构任务，MemBench 是 A-D MCQ，registry
必须拒绝这三项；MemBench 继续用 `membench-choice-accuracy`，BEAM 继续用 rubric judge。
移除 BEAM 的 `f1` 注册与 registered-prediction 流程断言，不删除 F1 纯公式测试，也不伪造
替代分数。

## 4. Artifact-only 与兼容边界

1. 两个新答案指标只消费既有 `public_questions.jsonl`、
   `method_predictions.jsonl`、`evaluator_private_labels.jsonl`、manifest；不得构造
   method、retrieve、answer client 或读取 `.env`。
2. 不改 prediction schema、run identity、resume、provider protocol、benchmark adapter 或
   answer prompt。新增 evaluator 后可以对旧的完整 answer artifacts 离线复算。
3. 新 score 文件沿用 `run_artifact_evaluation()` 与 category aggregation；不新增
   benchmark 专用 runner。
4. 本卡不实现 BLEU/ROUGE-L/Precision@k/retrieval-F1@k，不改 query top_k=10，不处理
   stable ranking。

## 5. 必测强反例

至少锁住：

1. Recall core：top-k 截断、重复 source id、一个 group 多 child、unmatched 分母、0 hit、session
   projector、空 groups 拒绝；公共模块 API 无 benchmark/method 身份参数；
2. 四个 Recall evaluator 迁移前后代表 fixture 的 score records/summary 关键字段与数字不变，
   尤其 LoCoMo empty=1、LME 419 排除、MemBench `1/3`、BEAM multi-child any-of；
3. normalized EM：大小写/标点/article/and/空白归一化；partial 不得满分；normalized empty gold
   不得满分；
4. substring：方向反例、token boundary、连续 token、多余预测上下文、空 gold；
5. F1 数字零变化且 details 带 pack identity；`normalize_answer` 旧 import 仍可用；
6. registry 三项只允许 locomo/longmemeval/halumem，BEAM/MemBench 均 fail-fast；
7. 用最小 fake run 证明两个新 metric 经 `run_artifact_evaluation()` 写 score/summary，
   且不触发 OpenAI settings/client；已有 prediction artifact 不需重跑；
8. 所有新增/修改 Python 模块、类、函数、测试函数与 nested helper 有准确中文 docstring。

不得靠删除旧断言、放宽 parser、`pytest.skip/xfail`、硬编码 fixture 分数或捕获异常后返回 0
来过测。

## 6. 允许修改文件

生产代码：

```text
src/memory_benchmark/evaluators/__init__.py
src/memory_benchmark/evaluators/answer_text.py
src/memory_benchmark/evaluators/answer_metrics.py
src/memory_benchmark/evaluators/f1.py
src/memory_benchmark/evaluators/retrieval_metrics.py
src/memory_benchmark/evaluators/gold_evidence_groups.py
src/memory_benchmark/evaluators/registry.py
src/memory_benchmark/evaluators/locomo_recall.py
src/memory_benchmark/evaluators/longmemeval_recall.py
src/memory_benchmark/evaluators/membench_recall.py
src/memory_benchmark/evaluators/beam_recall.py
```

其中三个新文件可按同目录风格拆分，但不得在允许清单外另造生产模块。

测试：

```text
tests/test_answer_f1.py
tests/test_answer_metric_pack.py
tests/test_retrieval_metric_kernel.py
tests/test_evaluator_registry.py
tests/test_artifact_evaluation_runner.py
tests/test_locomo_retrieval_recall.py
tests/test_longmemeval_retrieval_recall.py
tests/test_membench_retrieval_recall.py
tests/test_beam_recall.py
tests/test_beam_registered_prediction.py
```

施工记录：

```text
docs/workstreams/ws02.7-method-track/branches/metric-pack/notes/metric-kernels-m0-implementation.md
```

`tests/test_documentation_standards.py` 只运行、不修改。若必须修改 runner、provider、benchmark/
method adapter、TOML、third_party、其它测试或父 README 才能完成，立即停工报告最小冲突，不扩表。

## 7. 明确不做与停工条件

不做：真实 API、下载数据/模型、全量回归、compileall、参数调优、LightMem smoke、Precision
穷尽性审计、BLEU/ROUGE、NDCG/rank、父状态/frozen 更新或 push。

以下任一发生就停工：

- 共享 Recall core 必须接收 benchmark 名才能保持现有数字；
- 任一现有 Recall fixture 数字/分母/record shape 必须改变；
- HaluMem 标准 answer artifacts 不能被通用 artifact runner 读取；
- 新 metric 需要 gold 泄漏到 method、改 prediction schema 或重跑 method；
- 允许清单外存在冲突用户改动；
- 定向测试失败且 15 分钟内无法定位。

## 8. 唯一定向自检、commit 与报告

只跑一次最终相关门；失败定位可跑单测，但报告必须区分：

```bash
uv run pytest -q tests/test_answer_f1.py tests/test_answer_metric_pack.py tests/test_retrieval_metric_kernel.py tests/test_evaluator_registry.py tests/test_artifact_evaluation_runner.py tests/test_locomo_retrieval_recall.py tests/test_longmemeval_retrieval_recall.py tests/test_membench_retrieval_recall.py tests/test_beam_recall.py tests/test_beam_registered_prediction.py tests/test_documentation_standards.py
git diff --check
```

提交前只显式 `git add` 允许路径，禁止 `-A`/`.`；add 前后查看
`git status --short`；本地单 commit，不 amend、不 push。建议 commit：
`feat(metrics): add reusable answer metric pack`。

完成报告按 actor-handbook §4 原样给：

1. commit hash；
2. 定向测试尾行原文与 `git diff --check`；
3. 实际改动文件；
4. 偏差/停工点；
5. subagent 使用与模型/入口切换情况。

到此停止，等待架构师强验收。
