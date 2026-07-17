# Actor 卡：RetrievalEvidence M1（五个 evaluator 逐题资格消费）

> **给当前 actor 的执行指令：你就是用户已选中的执行者。** 本卡被发送到当前 actor
> 会话即代表用户已经完成选择与授权，请直接施工；不要再选择、派发或等待另一个 actor。
> 本卡就是可整份复制的自包含 prompt，单批上限 5h，零真实 API。actor 是否使用自己的
> subagent 由 actor 自行组织；subagent 不得扩大本卡范围，发生实质使用时须在完成报告披露。

## 0. 目标与已关闭的前置

目标：让五个 retrieval evaluator 不再用 run 级旧字段
`manifest.method.provenance_granularity` 猜整批资格，而是严格消费每条 answer artifact 的
`retrieval_evidence`，逐题导出 `valid / n_a / pending`。Recall 只要求 semantic
provenance；LongMemEval rank 还要求 stable ranking。不可评题不记 0、不进 scored
denominator，reason code 原样留档。

以下前置已经关闭，**本卡只消费，不重做**：

- RetrievalEvidence v1 M0：主线 `352ed3c` + `6b4fd4e` + `afd4040` + `c879343`；
- Gold Evidence Group v1：主线 `afb57f3` + `6d68a51`；
- LME `_abs`/no-target 官方主路径分母 419：已由 Gold M0 关闭；
- MemBench FirstAgent canonical pair split：主线 `ce1a9a8` + `d852fff` + `68b674b`。

不要改这些 schema、adapter 或 benchmark canonical 结果。当前三家已盖 v1 的 provider
`stable_ranking` 都仍是 `pending`；因此真实旧/新 run 的 LongMemEval rank 在 M1 后应诚实
输出 pending，而不是为了保留分数跳过 rank 门。

## 1. 上工、最小读序与 git 隔离

按顺序只读：

1. `AGENTS.md`；
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊；
3. 本卡全文；
4. `docs/reference/actor-handbook.md` §0-§4；
5. `../notes/retrieval-metric-eligibility-ruling.md` §1、§3、§5、§7；
6. `../notes/retrieval-evidence-contract-m0.md` §1-§3、§6、§9；
7. `../../input-role-semantics/notes/membench-canonical-split-implementation.md` §6-§8；
8. 现有五个 evaluator、`gold_evidence_groups.py` 与对应六个测试文件。

从届时最新 `main` 自建独立 worktree。路径或分支已存在就停工，不删除、不复用：

```bash
git -C /Users/wz/Desktop/memoryBenchmark worktree add \
  /Users/wz/Desktop/mb-actor-retrieval-evidence-m1 \
  -b actor/retrieval-evidence-m1 main
cd /Users/wz/Desktop/mb-actor-retrieval-evidence-m1
uv sync
```

开工先核实 `git merge-base --is-ancestor 68b674b HEAD` 成功；否则停工，说明基线缺哪个
前置，不要在本卡补前置。

## 2. 已裁共享资格语义

新增 evaluator-private 共享 helper：
`src/memory_benchmark/evaluators/retrieval_evidence.py`。最终内部类型/函数名可按同目录风格
微调，但必须单源实现以下行为，五个 evaluator 不得各复制一份宽松 parser。

### 2.1 两道版本门先于任何能力分支

每个 evaluator 进入后按固定顺序：

1. `require_manifest_gold_evidence_contract_v1(manifest)`；
2. 新 helper 要求 `manifest["method"]["retrieval_evidence_contract_version"] == "v1"`。

缺 method、缺 version、旧 artifact 或未知 version 一律 `ConfigurationError`。该门必须发生
在旧 `provenance_granularity=none/undeclared`、benchmark `_abs`/no-target/empty-gold 与
逐题 N/A 之前；不能让旧 artifact 因“反正不可评”绕过身份门。

### 2.2 逐题 artifact 严格解析

在进入 benchmark-specific 排除或计分循环前，先对**全部** answer records 的
`retrieval_evidence` 做 preflight：

- key 缺失、值为 `null`、非 object、缺字段、字段类型错误、未知 status、非法 reason
  组合或非法 granularity，统一转成带 question id 的 `ConfigurationError`；
- 用 `EvidenceAssertion` / `RetrievalEvidence` 的 v1 构造器复用协议运行期校验，不另写
  一套漂移规则；raw object 只能有
  `semantic_provenance/provenance_granularity/stable_ranking`，两个 assertion 只能有
  `status/reason_code/reason`，未知 key 也 fail-fast；
- preflight 后才允许 `_abs`、official no-target、BEAM/MemBench empty gold 等 benchmark
  规则把题目排除，防止坏 evidence 藏在不计分题里。

### 2.3 evaluator 派生资格，不建 method 白名单

共享 helper 由逐题 `RetrievalEvidence` 派生一个 evaluator-internal decision；至少保留：
`status`、`reason_code`、`reason`、`provenance_granularity`。固定优先级：

1. `semantic_provenance.status != valid`：原样传播其 `n_a|pending` 与 reason；
2. semantic valid，但 granularity 不在本 evaluator 允许集合：导出
   `n_a / gold_granularity_mismatch`，不是 `ConfigurationError`；
3. Recall 到此即 valid，**不看 stable_ranking**；
4. rank/NDCG 再检查 `stable_ranking`：非 valid 时原样传播其 `n_a|pending` 与 reason；
5. 全部满足才 valid。

允许粒度由 evaluator 的 gold view 公开声明，不得出现 method 名或
method×benchmark×metric 表：

- LoCoMo recall：`turn | session`；
- LongMemEval recall/rank：`turn | session`；
- MemBench recall：只 `turn`；
- BEAM recall：只 `turn`。session 在后两者统一导出结构化 N/A，不再一个优雅降级、
  一个抛“unknown granularity”。

旧 manifest `provenance_granularity` 可保留为历史审计字段，但**不得参与资格、选择 group
view 或 fail-fast**。测试要故意让它与逐题 evidence 冲突，证明逐题 v1 是唯一资格事实源。

## 3. 五个 evaluator 的逐题输出

迁移：

- `locomo_recall.py`；
- `longmemeval_recall.py`；
- `longmemeval_retrieval_rank.py`；
- `membench_recall.py`；
- `beam_recall.py`。

每个非 benchmark-policy 排除题：

- decision valid：按其**逐题** granularity 选择现有 Gold Evidence Group view，执行现有
  group 公式；只在此分支校验 `retrieval_query_top_k`、`retrieved_items` 与 top-k items
  的非空 `source_turn_ids`。真实 `retrieved_items=[]` 是 valid 0-hit，不是 lineage 缺失；
- decision n_a：`score=None`、`status="n/a"`，写
  `retrieval_evidence_status="n_a"`、`reason_code`、`reason`、granularity，不进分母；
- decision pending：`score=None`、`status="pending"`，同样写 exact reason，不进分母；
- benchmark 官方排除（LME `_abs`/no-target、BEAM/MemBench empty gold 等）保留现有政策与
  计数，并加 `exclusion_source="benchmark_policy"`；它不是 provider N/A。

每个 summary 至少新增并真实聚合：

- `retrieval_evidence_status_counts`：只统计有可评分 gold 的题，键为
  `valid/n_a/pending`；
- `retrieval_evidence_reason_code_counts`：只统计 n_a/pending；
- `scored_question_count`；
- `metric_tier="framework_supplementary"`。

summary 的 `status`：至少一题 scored → `ok`；零 scored 且至少一题 pending →
`pending`；否则 → `n/a`。现有 `total_questions`/mean 继续只反映 scored denominator。
已有 abstention、no-target、empty/unmatched、category、top-k distribution 等字段不得丢。

### 3.1 metric tier 裁决

五个 retrieval evaluator 本批统一标
`metric_tier="framework_supplementary"`。理由：即使 LoCoMo/LongMemEval 的局部公式与官方
一致，本框架衡量的是异构 method-native memory item 上附着的 canonical source group，且
LongMemEval 目前只请求 depth=10，完整 run 不能与论文检索数字直接等号。保留
`official_source`/`official_sources`，LongMemEval rank 可另写
`formula_parity_at_available_k=true`，但不能用 `official_parity` 掩盖 item/depth 差异。

## 4. LongMemEval rank 与 k coverage

本卡**不**改 `RetrievalQuery.top_k=10`，不新增第二次 retrieve，也不让 evaluator 调 method。

- semantic provenance 与 granularity 先过门，再要求 `stable_ranking=valid`；当前三家真实
  provider 都是 pending，故其 rank 题应 pending、不产指标；
- 合成 `stable_ranking=valid` artifact 用来锁现有公式；只有
  `k <= retrieval_query_top_k` 才参与；30/50 在 query depth=10 时必须继续显式 unavailable；
- summary 保留 `skipped_k_above_top_k`，新增稳定 reason code
  `evaluation_depth_not_requested`（字段命名可沿现有 summary 风格），不得把物理多存的 items
  或缺失名次当 k=30/50 官方结果；
- 每个 k 的 denominator 只含“该题逐题资格 valid 且 query depth 覆盖该 k”的题；
  n_a/pending/benchmark-excluded 题均不参加；
- 不改已经锁定的 LME `_abs` + no-target 419 口径，不把无目标题重新记 0 或 1。

## 5. 必测强反例

至少覆盖以下会在旧实现失败的门：

1. manifest 缺/错 retrieval evidence v1 时，在旧静态 provenance=N/A、`_abs` 或 empty gold
   情况下仍先 fail-fast；
2. 全部 answer records 先 preflight：不计分题里的 missing/null/非法/多余 key evidence 也拒绝；
3. 同一 run 混合 valid、n_a、pending：只 valid 入 mean，exact reason code/count 保留；
4. 旧 manifest granularity 故意写 `none` 或与逐题值相反，逐题 v1 仍决定 group view/资格；
5. 四个 Recall 路径在 stable ranking=pending 时仍正常计分；
6. LongMemEval rank 在 semantic valid + ranking pending 时不计分且 summary=pending；ranking
   n_a 与 pending 不混写；synthetic ranking valid 才算公式；
7. MemBench/BEAM 收到 semantic valid(session) 时都导出
   `gold_granularity_mismatch` N/A，不抛 unknown；
8. valid + `retrieved_items=[]` 是 0 hit；valid + 非空 top-k item 缺/空 source ids 才
   fail-fast；n_a/pending 不因 items 没 lineage 被二次报错；
9. MemBench 3 个 2-child group 命中任一 child 仍严格 `1/3`，不得回退 child 分母；
10. LME rank query top_k=10 只出 1/3/5/10，30/50 标 unavailable；不同题 top_k 混合时
    每个 k denominator 独立；
11. 五个 payload/score record 的 metric tier 均为 `framework_supplementary`；
12. 所有新增/修改 Python 模块、类、函数、测试函数与 nested helper 都有准确中文
    docstring；显式跑文档标准门。

## 6. 允许修改的文件

- 新建 `src/memory_benchmark/evaluators/retrieval_evidence.py`；
- `src/memory_benchmark/evaluators/{locomo_recall,longmemeval_recall,
  longmemeval_retrieval_rank,membench_recall,beam_recall}.py`；
- `tests/test_{locomo_retrieval_recall,longmemeval_retrieval_recall,
  longmemeval_retrieval_rank,membench_retrieval_recall,beam_recall}.py`；
- 新建 `docs/workstreams/ws02.7-method-track/branches/retrieval-metrics/notes/
  retrieval-evidence-m1-implementation.md`。

`tests/test_documentation_standards.py` 只运行，不修改。若必须改上述以外文件才能完成，立即
停工并报告最小冲突，不自行扩表。

## 7. 明确不做

- 不改 provider protocol/M0 schema、runner、artifact writer、manifest/resume、registry；
- 不改任何 method adapter/TOML/third_party；不做 stable-rank method 审计；
- 不改 Gold Evidence Group entity/parser、五家 benchmark adapter/canonical id；
- 不重修 LME 419 分母，不改 answer context，不把 top_k 提到 50，不二次 retrieve；
- 不新增 method×benchmark 白名单或 benchmark 专用 runner；
- 不跑真实 API、不下载数据/模型、不更新父 README/status/frozen note、不 push。

## 8. 停工条件

- 当前 main 缺 §0 任一前置 commit 或现行字段与 M0/v1 契约冲突；
- operation-level artifact 被这五个 evaluator 实际消费且缺
  `retrieval_query_top_k`，导致本卡不能只改 evaluator；
- 合法逐题 granularity 找不到已验收的 Gold v1 view；
- 必须改 provider/runner 才能区分 n_a 与 pending 或才能保留 reason；
- 一手官方代码证明本卡保留的 LME 419、LoCoMo empty gold 或其他 benchmark 排除政策错误；
- 定向测试失败且 15 分钟内无法定位；
- 发现允许清单外已有用户改动与本卡冲突。

## 9. 唯一定向自检、commit 与完成报告

只跑一次以下直接相关门（定位单测可在失败时跑；完成报告必须如实区分）：

```bash
uv run pytest -q \
  tests/test_locomo_retrieval_recall.py \
  tests/test_longmemeval_retrieval_recall.py \
  tests/test_longmemeval_retrieval_rank.py \
  tests/test_membench_retrieval_recall.py \
  tests/test_beam_recall.py \
  tests/test_documentation_standards.py
git diff --check
```

提交前：只 `git add` 上述显式路径，禁止 `-A`/`.`；过目 `git status --short`；本地 commit，
不 push。完成报告按 `actor-handbook.md` §4 原样给：

1. commit hash；
2. 定向测试尾行原文与 `git diff --check`；
3. 实际改动文件；
4. 偏差/停工点；
5. subagent 使用与模型/入口切换情况。
