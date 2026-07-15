# RetrievalEvidence M0 实现记录（协议与 artifact plumbing）

> 日期：2026-07-15
> 执行者：Claude Opus 4.8（actor）
> 卡：`../cards/actor-prompt-retrieval-evidence-contract-m0.md`（本会话直接收卡的
> 自包含 prompt）
> 裁决底：`retrieval-metric-eligibility-ruling.md` §3-§4；
> `../../lightmem-lifecycle/notes/lightmem-update-lifecycle-ruling.md` §5。
> 范围：只做 M0 plumbing——协议实体 + artifact/manifest 落盘 + 三家 adapter 逐题事实。
> **不切 evaluator、不改 LongMemEval 分母、不动 `RetrievalQuery.top_k=10`。**

## 1. 数据模型（最终命名）

`src/memory_benchmark/core/provider_protocol.py` 新增并在 `__all__` 公开导出：

- `RetrievalEvidenceStatus = Literal["valid", "n_a", "pending"]`；
- `EvidenceAssertion(status, reason_code, reason)`：frozen dataclass。
  - `status="valid"` → `reason_code`/`reason` 必须都为 None；
  - `status="n_a"|"pending"` → `reason_code`/`reason` 必须都是非空字符串；
- `RetrievalEvidence(semantic_provenance, provenance_granularity, stable_ranking)`：
  frozen dataclass。
  - `semantic_provenance.status == "valid"` → `provenance_granularity` 只能是
    `turn|session`；
  - 非 valid → `provenance_granularity` 必须为 `none`。

`RetrievalResult` 新增 `evidence: RetrievalEvidence | None = None`。None 只为旧自定义
provider / 旧测试兼容，三家注册 method 生产返回值均非 None。

未新增 `metric_name`、benchmark 白名单或 evaluator 判定字段——provider 只陈述运行时事实。
`reason` 是公开字段，随 artifact 记录整体走既有 `validate_no_private_keys`（其键
`status/reason_code/reason/semantic_provenance/provenance_granularity/stable_ranking`
均不在私有键黑名单）。

## 2. Artifact 与 manifest plumbing

### 2.1 逐题 artifact

两条 runner 的 answer prompt 记录都新增顶层 `retrieval_evidence`：

- prediction：`runners/prediction.py::_answer_question_retrieve_first` 经新 helper
  `_retrieval_evidence_payload()`，有 evidence 时 `dataclasses.asdict()` 原样序列化，
  无 evidence 时写 `null`。现有 `retrieved_items`/`retrieval_query_top_k` 未改。
- operation-level：`runners/operation_level.py::_answer_prompt_record` 同规则，只加
  evidence，未发明 `retrieval_query_top_k`。

**不偷读旧 manifest 拼假逐题值**：provider 未返回 evidence 就如实写 None。

### 2.2 Contract version = resume 身份

`MethodRegistration` 新增可选静态字段
`retrieval_evidence_contract_version: str | None = None`；Mem0/LightMem/MemoryOS 显式
写 `"v1"`，A-Mem/SimpleMem 保持 None。

- prediction 路径：`run_predictions` 经新 helper
  `resolve_registered_factory_retrieval_evidence_contract_version(system_factory)`
  按 factory 身份解析（与 provenance_granularity 同构），传入
  `_method_manifest_with_protocol`；isolated worker 根进程不构造真实 method 也能盖章。
- operation-level 路径：`cli/run_prediction.py` 只对 operation-level 调用透传
  `getattr(method_registration, "retrieval_evidence_contract_version", None)`；
  `run_operation_level_predictions` 新增同名参数并转交 `_method_manifest_with_protocol`。

**该 version 未加入 `_manifests_match_for_resume` 的"任一侧缺失就双删"兼容键集合**
（`protocol_version/prompt_track/profile/provenance_granularity`）。因此旧 run 缺 version
与新 v1 run 严格 `==` 不等 → resume mismatch，避免同一 artifact 混入有/无逐题 contract
的记录。

## 3. 三家 adapter 的逐题事实

三家 `stable_ranking` 一律 `pending`（`ranking_fidelity_not_audited`），逐 method rank
审计未完成前不得因"看起来有序"改 valid。resource benchmark 身份一律取注册显式注入的
`self.benchmark_name`，不从数据形态/source_path/问题时间猜。

### 3.1 Mem0（`_build_retrieval_evidence`）

| benchmark_name | semantic_provenance | granularity |
|---|---|---|
| locomo / membench | valid | turn |
| longmemeval / halumem | valid | session |
| beam | n_a `ingest_batch_coarser_than_gold` | none |
| 缺失/未知 | pending `benchmark_identity_missing` | none |

sidecar 缺映射仍在 `_source_turn_ids_for_memory` fail-fast；空检索/真实 0 hit 仍返回
上述 valid contract。

### 3.2 LightMem（`_build_retrieval_evidence(items)`）

资格同时取决于实际 lifecycle 与逐题 `items`：

- benchmark 身份不在 `{locomo,longmemeval,halumem,beam,membench}` → pending
  `benchmark_identity_missing` + none；
- `lifecycle_profile="locomo_offline_consolidated"`（构造期已校验 benchmark=locomo）→
  恒为 n_a `semantic_mapping_unavailable_after_mutation` + none，即使 items 完整；
- `lifecycle_profile="online_soft"`：`items is not None`（含 `items=()` 真实 0 hit）→
  valid + turn；`items is None`（本次 lineage 不可用）→ n_a
  `retrieval_hit_lineage_incomplete` + none。

未改 LightMem lifecycle/update/insert/merge 算法；`items=()` 与 `None` 语义严格区分。

### 3.3 MemoryOS（`_build_retrieval_evidence`）

已注册 benchmark → valid + turn；identity 缺失/未知 → pending
`benchmark_identity_missing` + none。page sidecar 缺失仍在 `_retrieved_items` fail-fast，
本卡未重审/改 page 映射算法。

## 4. 测试（定向自检覆盖）

- `test_provider_protocol.py`：三组非法组合 fail-fast + 合法值 `asdict()` 无私有键 +
  RetrievalResult 可选 evidence。
- `test_prediction_runner.py`：prediction artifact 写逐题 evidence（含 provider 无
  evidence → null）；三家注册项 v1 / A-Mem+SimpleMem None + factory 盖章；v1 与缺 version
  manifest 拒绝 resume。
- `test_operation_level_runner.py`：operation-level artifact 写逐题 evidence + manifest
  盖 v1；未传时不盖章。
- `test_halumem_registered_prediction.py`：registered operation-level manifest 写 v1。
- `test_mem0_adapter.py`：五 benchmark turn/session/n_a 矩阵 + BEAM reason code 精确 +
  stable_ranking pending。
- `test_lightmem_adapter.py`：online_soft `items=()` valid / `items=None` n_a；
  consolidated 即使 items 完整 n_a；缺 identity pending；stable_ranking pending。
- `test_memoryos_adapter.py`：已知 benchmark valid(turn)、未知 identity pending +
  stable_ranking pending。

## 5. 偏差与停工点

- 无停工点。允许清单内的测试文件全部真实存在，未创建同名空壳、未新增清单外测试文件。
- `src/memory_benchmark/core/__init__.py` 在允许清单内，但按既有约定（`RetrievalResult`
  等 provider_protocol 实体都不经 `core/__init__` 再导出，一律直接从
  `core.provider_protocol` 导入）**未修改**该文件，新实体同样只从 provider_protocol 导出。
  commit 的 `git add` 会包含该路径但无 diff。

## 6. 明确未做（留给 M1）

不改 5 个 retrieval evaluator、不修 LongMemEval empty-gold/no-target 分母、不动
`top_k=10`、不建 method×benchmark×metric 白名单、不删/重解释旧 `provenance_granularity`
字段、不改 LightMem lifecycle profile/TOML、零真实 API。

## 7. R1 补丁：runtime 拒绝非法 status

> follow-up commit（不 amend 首轮 `5fd5ac1`）

首轮 `EvidenceAssertion.__post_init__` 只靠 `Literal` 约束 status，静态类型检查不会在
runtime 拒绝非法值：`EvidenceAssertion(status="bogus", reason_code="x", reason="y")` 会
成功构造，而该 status 会进入公开 artifact 并成为后续 evaluator 契约输入，不能接受未定义
第四态。

R1 在语义分支之前显式校验 `status ∈ {valid, n_a, pending}`，非法值统一 `ValueError`
fail-fast。合法值集合 `_RETRIEVAL_EVIDENCE_STATUSES` 直接由 `get_args(
RetrievalEvidenceStatus)` 从 `Literal` 派生，避免与静态类型两处漂移。不正规化大小写/
空格/别名，不引入 enum/Pydantic，不改三种合法值现有 reason 规则；错误先指向非法
status，不误报 reason 缺失。

测试（`tests/test_provider_protocol.py`）：带完整 reason 的 `"bogus"` 强反例被拒；
空串/纯空格/错误大小写/`None`/非字符串也拒绝（证明非只特判 `"bogus"`）；缺 reason 的
非法 status 仍先报 status 非法；既有 valid/n_a/pending 用例不变。

## 8. 架构师强验收 hardening：不可哈希 status 也统一 ValueError

架构师复跑 R1 后追加反例发现：首轮 R1 直接执行
`self.status not in frozenset(...)`，list/dict 等不可哈希越界值会先泄漏 Python
`TypeError: unhashable type`，没有兑现“非法 status 统一 ValueError”的协议边界。

验收微修在集合 membership 前增加 `isinstance(self.status, str)` 短路；静态 annotation、
Literal 单源集合与三种合法值语义均不变。参数化测试补 `[]`/`{}`，要求两者与其他非法值
同样稳定抛 `ValueError`。该修复由架构师以独立 follow-up commit 留痕，不 amend actor 的
`5fd5ac1` / `1999f56` 历史。

## 9. 主树全量门：registered preflight / resume 身份对称性

合入首轮与 R1 后，主树第一次全量回归在
`test_locomo_registered_prediction_offline_probe_workflow` 暴露确定性回归：首次 run 进入
`run_predictions()` 后才补 `retrieval_evidence_contract_version="v1"` 并落盘；同一 registered
入口第二次 `resume=True` 却会先用 CLI 预构造、尚未带 v1 的 method manifest 做只读
preflight，因此拒绝自己刚生成的 run。该失败证明内部 `_manifests_match_for_resume` 单测与
runner 落盘测试不足以覆盖真实 registered service 的两阶段装配。

修复不放宽 strict resume，也不把 version 加进旧兼容删除键：
`cli/run_prediction.py::_build_method_manifest()` 新增可选 contract version，registered CLI
从同一 `MethodRegistration` 静态声明取值，在 preflight 前写入 child method manifest；随后
runner 的既有 `setdefault` 看到相同 v1，首次落盘与 resume 候选保持一致。custom method 与
未声明 contract 的 method 继续不写该字段。LoCoMo registered 端到端测试显式断言 manifest
v1，并以原有第二次 resume 成功锁住该边界。

修复后第二次主树全量已越过上述 resume 失败，随后由 MemoryOS registered 测试的整字典
旧期望报出唯一差异：生产 manifest 正确新增了
`retrieval_evidence_contract_version="v1"`，测试仍锁在 M0 前形状。该项属于输出契约测试
随公开 schema 演进的必要更新；预期字典补 v1，生产字段不撤回、不降级兼容。
