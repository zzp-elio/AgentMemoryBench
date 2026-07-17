# RetrievalEvidence M1 实现记录（evaluator 逐题资格消费）

> 施工 actor：Claude Sonnet 5（Claude Code，本会话系统提示自报模型确认，未跨
> 模型切换）。基线：主树 `main` HEAD `1e227c3`（已核实
> `git merge-base --is-ancestor 68b674b HEAD` 成功）。worktree=
> `/Users/wz/Desktop/mb-actor-retrieval-evidence-m1`，branch=
> `actor/retrieval-evidence-m1`。按
> `cards/actor-prompt-retrieval-evidence-m1.md` 全卡施工。

## 1. 做了什么

1. **新增共享私有 helper**
   `src/memory_benchmark/evaluators/retrieval_evidence.py`：
   - `require_manifest_retrieval_evidence_contract_v1(manifest)`：manifest
     `method.retrieval_evidence_contract_version` 严格等于 `"v1"`，缺
     `method`/缺 version/未知 version 一律 `ConfigurationError`；与既有
     `require_manifest_gold_evidence_contract_v1` 各自独立调用，两道版本门
     都发生在任何能力分支之前。
   - `parse_retrieval_evidence(raw, question_id)`：对单条 answer prompt 的
     `retrieval_evidence` 做严格 preflight——key 缺失/值为 null、非
     object、缺字段、多余字段统一 `ConfigurationError`；随后复用
     `EvidenceAssertion`/`RetrievalEvidence` 协议构造器的运行期校验解析
     `status`/`reason_code`/`reason`/`provenance_granularity` 的合法组合，
     不另写一套可能与协议漂移的规则。
   - `RetrievalEligibilityDecision` + `decide_retrieval_eligibility(evidence,
     *, allowed_granularities, requires_stable_ranking)`：固定优先级——
     semantic provenance 非 valid 原样传播；valid 但 granularity 不在允许
     集合记 `n_a`/`gold_granularity_mismatch`；不要求 stable ranking 时到此
     即 valid（Recall 路径）；要求时再检查 stable_ranking 是否 valid（rank
     路径）。不建 method×benchmark×metric 白名单。
   - `display_status`/`summary_status`：把内部 status 映射为 record 惯用的
     `"n/a"`/`"pending"` 展示态，并按 scored/pending 数量计算 summary 三态
     （`ok`/`pending`/`n/a`）。
   - `summary_provenance_granularity(decisions)`：为仍在读取 summary 顶层
     `provenance_granularity` 标量的存量消费者（见 §4）保留一个"本 run 内
     valid 裁决共享的代表粒度"，不再驱动任何计分分支。

2. **五个 evaluator 迁移**为消费逐题裁决（`locomo_recall.py` /
   `longmemeval_recall.py` / `longmemeval_retrieval_rank.py` /
   `membench_recall.py` / `beam_recall.py`）：
   - 入口统一先后调用 `require_manifest_gold_evidence_contract_v1` +
     `require_manifest_retrieval_evidence_contract_v1`，再对**全部** answer
     records 做 `parse_retrieval_evidence` + `decide_retrieval_eligibility`
     preflight（即将被 `_abs`/no-target/empty-gold 剔除的题也不例外）。
   - 旧 run 级 `manifest["method"]["provenance_granularity"]` 字段保留在
     manifest 中（未删除写入逻辑，属于 runner 侧字段），但五个 evaluator
     都不再读取它做任何判定——只作历史审计。
   - `decision.status != "valid"` 时写独立的逐题 n_a/pending record
     （`score=None`、`status`、`retrieval_evidence_status`、`reason_code`、
     `reason`），不进分母；`decision.status == "valid"` 时才用
     `decision.provenance_granularity` 选择 Gold Evidence Group view，执行
     各 benchmark 既有公式（LoCoMo 空 evidence 记 1.0 的官方行为、LongMemEval
     no-target 剔除、MemBench/BEAM out-of-bounds/ambiguous 诊断均未改）。
   - LongMemEval rank 额外要求 `stable_ranking=valid`
     （`requires_stable_ranking=True`）；每个 k 的 participating 分母只在
     decision valid 分支内累积，n_a/pending 题不参与任何 k。新增
     `skipped_k_above_top_k_reason_code="evaluation_depth_not_requested"`。
   - MemBench/BEAM 的 `allowed_granularities` 收窄为 `{"turn"}`；原本各自
     手写的"session 没有结构"专用分支统一替换为共享的
     `gold_granularity_mismatch` N/A。
   - 移除了原本按 manifest 单值分支返回整跑 N/A 的 `_na_payload`/
     `_method_provenance_granularity`：改为 `answer_prompts` 为空时自然产出
     `total_questions=0`、`score_records=[]`、`summary.status="n/a"`，不再
     需要专门的整跑 N/A 分支。
   - `summary` 新增 `scored_question_count`、
     `retrieval_evidence_status_counts`（只统计 `_abs` 等 granularity 无关
     benchmark policy 剔除之外的题）、`retrieval_evidence_reason_code_counts`
     （只统计 n_a/pending）、`metric_tier="framework_supplementary"`；rank
     另加 `formula_parity_at_available_k=true`。

## 2. `summary["provenance_granularity"]` 兼容性说明（非卡内要求，见 §5 偏差）

卡内设计已把资格判定完全下放到逐题 `retrieval_evidence`，`summary` 顶层
不再需要单一 granularity 值。但施工前扫描发现三个**允许清单外**的既有测试
直接断言 `recall_payload["provenance_granularity"] == "turn"`（真实
registered pipeline 输出）：`tests/test_longmemeval_registered_prediction.py`、
`tests/test_membench_registered_prediction.py`、
`tests/test_beam_registered_prediction.py`。为避免破坏这三个文件，`summary`
保留了 `provenance_granularity` 字段，但语义改为「本 run 内 valid 裁决共享的
代表粒度」（`summary_provenance_granularity`）——真实生产场景下同一
(method, benchmark) 组合的 valid 裁决 granularity 恒定，因此该字段对这三个
文件的断言值不变；它不再参与任何评分分支或 gold view 选择。LoCoMo 与
LongMemEval rank 的 summary 也统一保留该字段以保持五个 evaluator 结构对称，
但目前没有已知外部消费者依赖这两处的值。

## 3. 定向自检（唯一一次，原样输出）

```
uv run pytest -q \
  tests/test_locomo_retrieval_recall.py \
  tests/test_longmemeval_retrieval_recall.py \
  tests/test_longmemeval_retrieval_rank.py \
  tests/test_membench_retrieval_recall.py \
  tests/test_beam_recall.py \
  tests/test_documentation_standards.py
```

尾行：`87 passed in 3.11s`。`git diff --check` 无输出（exit 0）。

## 4. §5 强反例覆盖清单（逐条对应到具体测试）

1. manifest 缺/错 v1 时在旧路径前 fail-fast：
   `test_missing_retrieval_evidence_contract_version_fails_fast`（locomo/
   longmemeval_rank/membench/beam 各一份，locomo 额外带旧
   `provenance_granularity="none"` 佐证顺序）、
   `test_unknown_retrieval_evidence_contract_version_fails_fast`（locomo）、
   `test_missing_retrieval_evidence_contract_version_fails_fast_before_abstention`
   （longmemeval recall，manifest 缺版本 + 存在 `_abs` 题）。
2. 全部 answer records 先 preflight（含不计分题）：
   `test_missing_retrieval_evidence_key_fails_fast_at_preflight`、
   `test_null_retrieval_evidence_fails_fast_at_preflight`、
   `test_retrieval_evidence_with_extra_key_fails_fast_at_preflight`、
   `test_retrieval_evidence_with_missing_required_key_fails_fast_at_preflight`、
   `test_retrieval_evidence_with_illegal_status_fails_fast_at_preflight`、
   `test_retrieval_evidence_preflight_runs_before_scoring_for_every_record`
   （locomo）；
   `test_null_retrieval_evidence_on_abstention_question_still_fails_fast_at_preflight`
   （longmemeval recall，即将被 `_abs` 剔除的题也不例外）。
3. 混合 valid/n_a/pending：`test_mixed_valid_na_pending_questions_in_one_run`
   （locomo）。
4. 旧 manifest granularity 不参与判定：
   `test_legacy_manifest_granularity_field_does_not_participate_in_eligibility`
   （非法值 `"paragraph"`）+
   `test_legacy_manifest_granularity_field_opposite_legal_value_still_ignored`
   （合法但相反的值 `"session"` vs 逐题 `"turn"`，锁定真实计分结果而非仅锁
   fail-fast 与否）（均 locomo）。
5. 四个 Recall 路径 stable_ranking=pending 仍计分：
   `test_stable_ranking_pending_does_not_block_recall_scoring`（locomo /
   longmemeval_recall / membench / beam 各一份）。
6. LongMemEval rank pending 不计分且 summary=pending、n_a 与 pending 不混写、
   synthetic valid 才算公式：
   `test_stable_ranking_pending_blocks_scoring_and_reports_pending_status`、
   `test_stable_ranking_na_is_distinct_from_pending`、
   `test_synthetic_stable_ranking_valid_locks_formula`。
7. MemBench/BEAM session decision → `gold_granularity_mismatch` N/A：
   `test_session_decision_is_gold_granularity_mismatch_na`（两文件各一份）。
8. valid + 空 `retrieved_items` 是 0 hit、valid + 非空 item 缺/空
   source_turn_ids 才 fail-fast、n_a/pending 不二次校验 items：
   `test_valid_decision_with_empty_retrieved_items_list_is_zero_hit_not_fail_fast`、
   `test_declared_turn_provenance_empty_source_turn_ids_fails_fast`、
   `test_na_decision_does_not_re_validate_retrieved_items_lineage`（均
   locomo）。
9. MemBench 3 个 2-child group 严格 1/3：
   `test_multi_child_pair_group_any_of_hit_on_either_side_counts_once`（沿用
   MemBench canonical split 卡已验收的生产语义，仅补上逐题 evidence 包装）。
10. LME rank top_k=10 只出 1/3/5/10、30/50 unavailable，且每题 top_k 混合时
    denominator 独立：
    `test_query_top_k_10_yields_exactly_1_3_5_10_and_marks_30_50_unavailable`、
    `test_per_k_denominator_only_counts_valid_questions_covering_that_k`。
11. 五个 evaluator summary 均含 `metric_tier="framework_supplementary"`：
    每个测试文件各有一个 `test_summary_reports_*`/`test_summary_has_*`。
12. 中文 docstring 全覆盖：定向自检包含
    `tests/test_documentation_standards.py`，本次改动的全部新增/修改模块、
    类、函数、测试函数与 nested helper 均通过该门（含
    `_decisions_by_question_id`、`_pair_private_label` 等 nested helper）。

## 5. 偏差：已识别但未修复的允许清单外集合回归（未停工，已完整披露）

**发现**：卡 §2.1 明确要求"缺 method、缺 version、旧 artifact 或未知
version 一律 `ConfigurationError`……不能让旧 artifact 因'反正不可评'绕过
身份门"，且该门必须先于逐题 N/A。施工前扫描确认这是刻意设计（卡文原话
预判了这个场景），因此严格按字面实现，未做任何放宽。

按此实现后，`src/memory_benchmark/audit/benchmark_probe.py` 的
`BenchmarkProbeProvider.retrieve()`（多个 registered-prediction 集成测试
common 用它冒充 mem0 method）本身**不**设置 `RetrievalResult.evidence`；但
它常被 monkeypatch 进 `"mem0"` 注册表槽位，而
`retrieval_evidence_contract_version="v1"` 是**注册级**静态声明（M0 设计：
"无实例回退"），因此这类 run 的 manifest 仍会被盖上 v1 章，日 answer prompt
的 `retrieval_evidence` 却是 `null`——命中本卡 §2.2 preflight 的
"值为 null" 强制 fail-fast 规则。

**实测影响**（本卡开工前先记录的迁移前基线 vs 全部五个 evaluator 迁移完成
后的复跑，隔离 worktree 补齐 gitignored `data/` 只读软链后运行；非本卡定向
自检范围，纯为诊断本节风险而额外执行的一次性确认）：

```
uv run pytest -q \
  tests/test_beam_registered_prediction.py \
  tests/test_evaluator_registry.py \
  tests/test_lightmem_adapter.py \
  tests/test_locomo_registered_prediction.py \
  tests/test_longmemeval_registered_prediction.py \
  tests/test_membench_registered_prediction.py
```

迁移前：`6 passed`（含 data 软链后）。迁移后新增 6 项失败，全部同一根因
（`ConfigurationError: ... retrieval_evidence is missing or null`）：

- `tests/test_beam_registered_prediction.py::test_beam_registered_prediction_offline_probe_workflow_100k`
- `tests/test_beam_registered_prediction.py::test_beam_registered_prediction_offline_probe_workflow_10m`
- `tests/test_lightmem_adapter.py::test_lightmem_local_retrieval_provenance_scores_locomo_recall`
  （该测试手工构造的 manifest 从未声明
  `retrieval_evidence_contract_version`，且 answer prompt 里也不含
  `retrieval_evidence` key，是同一根因的另一种触发路径：完全预
  M0 的手写 manifest，而非 registry 派生）
- `tests/test_locomo_registered_prediction.py::test_locomo_registered_prediction_offline_probe_workflow`
- `tests/test_longmemeval_registered_prediction.py::test_longmemeval_registered_prediction_offline_probe_workflow`
- `tests/test_membench_registered_prediction.py::test_membench_registered_prediction_offline_probe_workflow`

`tests/test_evaluator_registry.py` 不受影响（只测 registry 装配，不调用
`evaluate_run_artifacts`）。

**为何未修复**：全部 6 个失败点都在卡 §6 允许清单之外
（`benchmark_probe.py` 是生产源码但不在清单；四个
`test_*_registered_prediction.py` 与 `test_lightmem_adapter.py` 都是测试
文件但同样不在清单）。卡 §6 明确要求"若必须改上述以外文件才能完成，立即
停工并报告最小冲突，不自行扩表"；因为这五个 evaluator + helper + 六个允许
测试文件本身的迁移**不需要**改动这些文件即可完整完成（本卡目标已 100%
达成，定向自检干净通过），所以没有整体停工——而是按 actor-handbook 好行为
判例（"识破 plan 有事实缺口，按任务实质完成 + 上报，不硬编绕过"）继续完成
卡内工作，把这个允许清单外的、影响面明确有限的回归完整记录在此，交架构师
裁定后续动作。可能的修复方向（本卡未做，留给架构师选择）：
(a) 给 `BenchmarkProbeProvider.retrieve()` 补一个可选的合成
`RetrievalEvidence`（贴近 Mem0 语义），(b) 给受影响的
`_ProbeAsMem0`/手写 manifest 测试补齐 `retrieval_evidence_contract_version`
与逐题 `retrieval_evidence`，(c) 判定这些测试本就该在 M1 后更新、按小范围
补丁处理。三者都需要修改本卡允许清单外的文件，因此本卡不擅自选择。

## 6. 允许文件改动清单核对

全部改动落在卡 §6 允许列表内：新建
`src/memory_benchmark/evaluators/retrieval_evidence.py`；
`src/memory_benchmark/evaluators/{locomo_recall,longmemeval_recall,
longmemeval_retrieval_rank,membench_recall,beam_recall}.py`；
`tests/test_{locomo_retrieval_recall,longmemeval_retrieval_recall,
longmemeval_retrieval_rank,membench_retrieval_recall,beam_recall}.py`；本
note 文件本身。未触碰清单外任何生产文件、父/支线 README、survey、policy、
其它 method、Gold Evidence Group entity/parser、runner/manifest/artifact
writer、registry、third_party、data、outputs、TOML 或 roadmap。隔离
worktree 缺 gitignored `data/`，按既有先例建立了指向主树 `data/` 的只读
软链后用于本节的一次性诊断复核；软链未被 `git add`（`git status --short`
显示为独立 `?? data` 未跟踪项，未纳入本次 commit 的显式路径列表）。

## 7. subagent 使用

本卡全程未使用 subagent，全部由主 actor 会话直接施工。
