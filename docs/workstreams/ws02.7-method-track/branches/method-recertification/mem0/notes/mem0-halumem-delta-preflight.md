# Mem0 × HaluMem current-main 差量预检

日期：2026-07-19
执行者：Claude Sonnet 5（本会话系统提示自报模型；未跨模型切换）
worktree：`/Users/wz/Desktop/mb-actor-mem0-halumem`，branch
`actor/mem0-halumem-delta-preflight`，起点 `6643e56`（main）。
真实 API：0；third_party 未改动；只读 current-main 源码 + 一个不提交的零 API 探针脚本
（构造与完整 stdout 见 §2，脚本本身未 commit）。

## 0. 判词

**`READY_FOR_JOINT_RULING`**，附两项声明缺口（§6），均不推翻本卡 §4 的八条锁死事实。

## 1. current-main 承重链定位（一手源）

| 组件 | 位置 | 关键行为 |
| --- | --- | --- |
| granularity | `methods/registry.py:202-211` `_mem0_consume_granularity` | `benchmark_name in {"longmemeval","halumem"}` → `"session"` |
| session report 开关 | `methods/registry.py:251-253` `_build_mem0_system` | `session_memory_report=context.benchmark_name == "halumem"` |
| session ingest | `methods/mem0_adapter.py:572-617` `_ingest_native_session` | `session_memory_report=True` 时 `chunks=[turns]`（整 session 一个 chunk），否则按位置两两切块（LongMemEval 路径，不适用本格） |
| session 报告 | `methods/mem0_adapter.py:619-635` `end_session` | 从 `_session_report_memories.pop((isolation_key, session_id), [])` 弹出并清空；不调用任何 Mem0 delete API |
| add 结果解析 | `methods/mem0_adapter.py:1725-1736` `_memory_ids_from_add_result`、`:1833-1849` `_memory_texts_from_add_result` | 两个独立、宽严不同的解析器（见 §2 探针 8） |
| provenance | `methods/mem0_adapter.py:1703-1723` `_add_with_provenance` | 每次 add 后把返回的 memory id → `{isolation_key, source_turn_ids}` 写入 sidecar；`source_turn_ids` = 本次 chunk 内全部 turn id（session 粒度即整 session） |
| 事件分组 | `runners/event_stream.py:156-162` `_aggregate_sessions`、`:210-228` `_group_by_session` | 按连续 `session_id` 分组，一个 session 恰产出一个 `SessionBatch` |
| operation-level 交错 | `runners/operation_level.py:226-334` `_run_operation_conversation`、`:337-401` `_ingest_and_probe_session` | 每 session：先 `build_turn_events` 按 `session_id` 过滤（双重保证不跨 session 混批）→ `aggregator.aggregate` → `provider.ingest(SessionBatch)` → `provider.end_session()` → （非 generated session）update probe（逐 `is_update=="True"` 且非空 `original_memories` 的 memory point）→ 该 session 的 QA → 下一 session |
| 单 worker 强制 | `runners/operation_level.py:105-108`；`cli/run_prediction.py:690-703` | 两层 fail-fast：runner 内部 `policy.max_workers != 1` 拒绝；CLI 在构造 provider 前对 `operation_level` benchmark 额外拒绝 `use_isolated_worker_instances`（即 `max_workers>1`） |
| resume/clean | `runners/operation_level.py:146,167-199`；`cli/run_prediction.py:681,721-746` | conversation 级 `conversation_status` 完成标记；**`run_operation_level_predictions()` 签名不含 `clean_failed_ingest_conversation` 参数**，CLI 计算出该 hook 后只传给 `run_predictions()`（标准路径），未传给 operation-level 调用（见 §6.2） |
| retrieve | `methods/mem0_adapter.py:979-1076` `_retrieve_native` | `Memory.search(..., top_k=self.config.top_k, filters={"run_id": query.isolation_key})`；**未读取 `query.top_k`**（见 §6.1） |
| TOML | `configs/methods/mem0.toml` | smoke: `max_workers=1`；official_full: `max_workers=10`（HaluMem 必须显式覆盖为 1，否则撞上表中两层 fail-fast） |
| evaluator | `evaluators/registry.py:276-345` | `halumem-extraction/-update/-qa` 三个 LLM judge（`requires_api=True`）+ `halumem-memory-type`（无 API，合成）+ `f1/normalized-em/substring-em` 对 halumem 同样注册 |
| 私有边界 | `methods/mem0_adapter.py` 全文 grep | 不出现 `private_metadata`/`memory_points`/`gold_answer`；唯一 `evidence` 引用是框架自身 `RetrievalEvidence`（公开 provenance），与 HaluMem 私有 evidence 无关 |

## 2. 八类 stateful 零 API 探针

不使用无状态 fake（每次 add 直接回显固定结果）。自建 `StatefulFakeMemoryBackend`：
按 `run_id` 维护真实累积的内存 store，`add()` 可脚本化指定返回值（用于制造零抽取/非标准
item），`search()` 从累积 store 读取。脚本路径（未提交）：
`/private/tmp/.../scratchpad/mem0_halumem_probe.py`，通过
`uv run python <script>` 在本 worktree 内执行，驱动方式与
`operation_level.py::_ingest_and_probe_session` 完全一致（先按 `session_id` 过滤
`build_turn_events`，再喂 `GranularityAggregator("session")`，保证 SessionBatch 只含该
session 的 turn）。以下为构造要点 + 关键真实 stdout（逐字摘录）。

### 探针 1+5：单 session 两 turn，一次 add；同 session 内 role/时间

```python
Session("session-a", session_time="Sep 01, 2025, 09:00:00", turns=[
    Turn("Alice", "I moved to Berlin last month.", turn_time="Sep 01, 2025, 10:00:00"),
    Turn("Bob", "That is exciting, how do you like it?", turn_time="Sep 01, 2025, 10:00:05"),
])
```

stdout：

```text
add_calls count: 1
call0.run_id: halumem-run_halu-user-p1
call0.messages: [{"role": "user", "content": "[Turn time: Sep 01, 2025, 10:00:00] Alice: I moved to Berlin last month."}, {"role": "assistant", "content": "[Turn time: Sep 01, 2025, 10:00:05] Bob: That is exciting, how do you like it?"}]
PASS: exactly one add(); role alternation user/assistant; per-turn time header
```

canonical Session → SessionBatch → **恰一次** `Memory.add()`，两条消息 role 严格
`user/assistant` 交替（首个说话人=user，第二个=assistant，与 survey 卡「全库严格
user/assistant 交替」一致），每条消息独立渲染自己的 turn-time header。

### 探针 2+4：连续两 session，各非空不同结果，长期 store 最终同时存在

```text
report_a.memories: ['[Turn time: Sep 01, 2025, 10:00:00] Alice: My dog is named Comet.', ...]
report_b.memories: ['[Turn time: Sep 02, 2025, 10:00:00] Alice: I adopted a second dog named Nova.', ...]
final store size (both sessions): 4
post-both-sessions search() returns: ['... Comet ...', '... Comet is a great name.', '... Nova ...', '... Two dogs now, nice.']
PASS: distinct non-empty per-session reports; long-term store holds both sessions simultaneously
```

`report_a.memories` 与 `report_b.memories` 互不相交（非累计），累计 store（探针后台的
真实 per-run_id bucket）在两个 session 之后同时持有 4 条（2+2），`retrieve()` 之后同时能
搜到 Comet（session-a）与 Nova（session-b）——`end_session()` 只清 staging、不删除长期
memory 的锁死事实成立。

### 探针 3：s1 非空、s2 零抽取

脚本第二次 `add()` 调用返回 `{"results": []}`（模拟 Mem0 判定该 session 无新事实，
合法行为，非框架故障）：

```text
report_a3.memories: ['[Turn time: Sep 01, 2025, 10:00:00] Alice: I got promoted at work today.', 'Congratulations!'...]
report_b3.memories: [] (scripted zero-extraction)
session-b operation_level record: {"session_ref": {...,"session_id": "session-b"}, "memories": [], "metadata": {"method": "mem0", "source": "mem0_add_results"}, "status": "ok"}
PASS: zero-extraction session recorded as legitimate empty report (status=ok, memories=[])
```

零抽取 session 走 `status="ok"` + `memories=[]`（不是 `status="n/a"`——`n/a` 只在
`provider.end_session` 本身不存在时出现，见 `_session_report_record` 分支）。这与
extraction evaluator 需要区分「本 session 没有新记忆」和「method 不支持 extraction」是
一致的。

### 探针 6：session time 有、turn time 无

```text
messages: [{"role": "user", "content": "[Session time: Sep 01, 2025, 09:00:00] Alice: No per-turn time on this one."}, {"role": "assistant", "content": "[Session time: Sep 01, 2025, 09:00:00] Bob: Same here."}]
PASS: turn_time absent -> single session-time fallback header, no double prefix
```

### 探针 7：source time 全无

```text
messages: [{"role": "user", "content": "Alice: Nothing has a timestamp here."}, {"role": "assistant", "content": "Bob: Confirmed."}]
PASS: no time anywhere -> no time header, no synthetic/wall-clock time injected
```

6/7 共同确认 `turn_time → session_time → None` 唯一渲染、无时间 noise、不回落到
QA/question/wall-clock 时间（B4 现行裁决在 HaluMem session 粒度下同样成立）。

### 探针 8：add 返回 ADD 结果外还含非标准/空 item

脚本第一次 `add()` 调用返回：

```python
[
    {"id": "m-good", "memory": "A real extracted fact.", "event": "ADD"},
    {"id": "m-missing-memory-key", "event": "ADD"},        # 无 memory 字段
    {"id": "m-blank-memory", "memory": "   ", "event": "ADD"},  # 空白 memory
    {"event": "ADD"},                                       # 无 id
    "not-a-dict-item",                                      # 非 dict
]
```

stdout：

```text
SessionMemoryReport.memories (text extraction): ['A real extracted fact.']
provenance memory_ids extracted (id-only boundary): ('m-good', 'm-missing-memory-key', 'm-blank-memory')
PASS (with declared asymmetry): text-extraction strict (needs id+non-blank memory, 1 of 5 scripted items survives); id-extraction only requires a truthy id (3 of 5 scripted items survive) -> m-missing-memory-key and m-blank-memory get provenance mappings but never appear in the public session report text
```

**真实发现（非阻断，记录留证）**：`_memory_texts_from_add_result`（喂 session
report / extraction evaluator）与 `_memory_ids_from_add_result`（喂 provenance
sidecar / retrieval evidence）是两个独立、宽严不同的解析器——前者要求
`id` 与非空白 `memory` 同时存在，后者只要求 `item.get("id")` 为真值。因此一个只有
`id`、没有（或空白）`memory` 文本的畸形 item：**不会**出现在公开 session report
（extraction evaluator 看不到它），但**会**被写入 provenance sidecar（若它对应的
memory id 之后出现在 search 结果里，`_source_turn_ids_for_memory` 仍能查到映射）。
真实 Mem0 `Memory.add()` 的 ADD 结果按 vendored 实现总是携带非空 `memory` 文本，
这条边界在生产路径下目前不可达，但两个解析器标准不一致本身是一个真实的代码事实，
留给共享实现卡判断是否需要统一。

## 3. session-report / 长期 store 分离（显式结论）

- `end_session()` 唯一动作是 `dict.pop(report_key, [])`——**没有**调用
  `self._memory.delete_all` 或任何 Mem0 delete/reset API；探针 2+4 的
  `final store size == 4` 与两次 `search()` 命中直接证明清 staging 不影响长期 store。
- `_session_report_memories[report_key]` 在每次 `_ingest_native_session` 开头被
  重新赋值为 `[]`（`mem0_adapter.py:593-594`），`report_key=(isolation_key, session_id)`
  在同一 conversation 内对不同 session 互不冲突，因此 report 是**本次 add 的增量**，不是
  跨 session 累计 list，也不是全库 `search()` 结果（`end_session` 完全不调用
  `Memory.search`）。

## 4. evaluator/readout/identity 对表

复用 `lightmem-halumem-metric-breakdown-r1.md` 的公式与官方分母（该文档明确「对所有
method 生效，不是 LightMem 专属公式」）；本节只核对 current source 字段名与 Mem0 是否
方法中立地走同一条链——确认无 Mem0 专属分支。

| 类别 | 字段 | 来源 | 备注 |
| --- | --- | --- | --- |
| Extraction | `recall/weighted_recall/target_accuracy/weighted_accuracy/interference_accuracy(all/valid)` + `memory_extraction_f1` | `evaluators/halumem_extraction.py`（`halumem-extraction`，`requires_api=True`） | 消费 `session_memory_reports.jsonl`（本卡 §2 已证：Mem0 每 session 写入的是本 session 增量，字段满足官方 evaluator 对「本 session 新增记忆」的假设） |
| Update | `correct/hallucination/omission_update_memory_ratio` + 官方 `Other` | `evaluators/halumem_update.py`（`halumem-update`） | 消费 `update_probe_results.jsonl`；对每个 `is_update=="True"` 且非空 `original_memories` 的 gold point 调用 `provider.retrieve(purpose="memory_update_probe", top_k=10)`——Mem0 侧实际发出的 `top_k` 见 §6.1 |
| QA | overall `correct/hallucination/omission_qa_ratio` + 六类 `question_type` 的 `(all/valid)` 三比率 + `qa_valid_num/qa_num` | `evaluators/halumem_qa.py`（`halumem-qa`）：`category_breakdown_tier="framework_supplementary"` | 六类 question_type（Memory Boundary/Basic Fact Recall/Memory Conflict/Generalization & Application/Multi-hop Inference/Dynamic Update）已逐类实现，字段名与 R1 note 一致（本轮 grep 重新核对，未漂移） |
| Memory type | `halumem_memory_type`（Event/Persona/Relationship，共享分母 `memory_integrity_acc + memory_update_acc`） | `evaluators/halumem_memory_type.py`（`halumem-memory-type`，`requires_api=False`） | 合成指标，读 extraction+update 两份 scores artifact，零 judge 调用；Mem0 与其余 method 走同一份 artifact 契约，无特判 |
| 通用 answer metric | `f1` / `normalized_em` / `substring_em` | `evaluators/registry.py:316-345` | 三者 `supported_benchmarks` 都含 `halumem`，对 `method_predictions.jsonl` 里的 QA 文本回答直接计分，公式内核不读 method 名——Mem0 无需额外接入即天然可用 |
| Retrieval Recall/NDCG | 无注册 | `evaluators/registry.py` 全表 | HaluMem 不出现在任何 retrieval evaluator 的 `supported_benchmarks` 里——「turn qrel 缺失→N/A」是注册表硬事实，不是文档承诺 |
| judge model/token/scope | 三个 LLM judge 均实现 `evaluate_run_artifacts`，走 `runners/evaluation.py:232-316` `_run_artifact_level_evaluation` 共享路径 | 与 BEAM 共用同一份 `174bd46` 修复：`efficiency_collector` 启用时强制返回 runner-internal `efficiency_observations`，写入 metric 专属 `EfficiencyArtifactStore`，不泄漏进 score/summary | Mem0 不改变这条链，evaluator 层完全 method 中立 |

### retrieve / readout / manifest / resume / clean-failed-ingest

- **retrieve**：`_retrieve_native` 对 `purpose="qa"` 与 `purpose="memory_update_probe"`
  走同一段代码，均用 `filters={"run_id": isolation_key}` 做 namespace 隔离，`top_k` 固定取
  `self.config.top_k`（**不读 `RetrievalQuery.top_k`**，见 §6.1）。`formatted_memory` 用
  `"- " + memory` 逐行拼接（`operation_level._memories_from_retrieval` 优先取
  `retrieval.items`）。
- **readout**：`RetrievedItem.source_turn_ids` 来自 provenance sidecar（session 粒度批
  id），`RetrievalEvidence.provenance_granularity == "session"`、
  `semantic_provenance.status == "valid"`（既有测试
  `test_mem0_retrieval_evidence_matrix_across_benchmarks` 覆盖，本轮未改）。
- **manifest**：`operation_level.py:113-133` 通过 `_method_manifest_with_protocol` 写入
  `protocol_version`/`provenance_granularity`/`retrieval_evidence_contract_version`；
  `_build_operation_manifest` 写入 dataset/policy/benchmark_variant/run_scope/source_paths，
  与标准 runner 的 resume 身份口径一致（同属 `docs/reference/method-toml-and-answer-builder-policy.md`
  与 manifest 精确 `==` 比较契约，未见 operation-level 专属放宽）。
- **run_id 隔离**：`isolation_key = default_isolation_key(run_id, conversation_id)`
  （`operation_level.py:251`），Mem0 侧同时有 worker 间物理隔离（不同 `storage_root`）与
  worker 内 `run_id` 逻辑隔离（Qdrant `filters`），HaluMem 因 §1 表中「单 worker 强制」而
  只触发逻辑隔离分支，物理隔离分支不适用（无需担心 B3 的 worker 隔离结论在这里失效）。
- **resume/clean-failed-ingest**：见 §6.2，真实缺口。

## 5. Privacy / identity 对表

- `mem0_adapter.py` 全文不出现 `private_metadata`/`memory_points`/`gold_answer`；唯一
  ingest 输入是 `benchmark_adapters/halumem.py` 产出的公开 `Conversation`（`Session.turns`
  只含 `dialogue` 派生的公开 `Turn`），私有 `memory_points`/`questions[].evidence`/
  `persona_info` 停留在 `Session.private_metadata`，只由 `operation_level.py`
  （runner 层，非 method 层）读取用于构造 update probe 的**查询文本**
  （`memory_point["memory_content"]`）——查询文本本身是 gold memory 的内容改写，但它是
  作为 **query**（用于测试 Mem0 是否已经检索到等价语义）传给 `provider.retrieve()`，不是
  作为可持久化的 payload 传给 `add()`；Mem0 侧收到的仍是普通 `RetrievalQuery.query_text`，
  与其余 purpose="qa" 查询走同一条代码路径，不构成私有数据落库。
- QA 私有 `answer`/`evidence` 全程不经过 `mem0_adapter.py`——`_answer_operation_question`
  只把公开 `Question`（`_make_public_question` + `validate_no_private_keys`）交给
  `provider.retrieve()`，method 侧无从得知 gold。
- `run_id`/namespace 与 identity：见 §4 末尾。当前 vendored source 身份、B1-B11 声明缺口
  沿用 `docs/reference/integration/mem0.md`，本轮未发现需要新增缺口的身份类问题。

## 6. 真实发现的声明缺口（不阻断本卡判词，交联合裁决/共享实现卡）

### 6.1 update-probe `top_k=10` 契约未被 Mem0 adapter 遵守

`RetrievalQuery.top_k` 是协议字段（`core/provider_protocol.py:222`，`__post_init__`
校验 `top_k > 0`），`operation_level.py:389` 对 update probe 显式传入官方
`top_k=10`（对齐 survey 卡 §2「以新 memory_content 为 query、top_k=10 检索」）。但
`Mem0._retrieve_native`（`mem0_adapter.py:1015/1021`）实际调用
`self._memory.search(..., top_k=self.config.top_k, ...)`，完全不读 `query.top_k`。
探针 9（脚本内「Update-probe top_k pass-through check」段）实测：

```text
RetrievalQuery.top_k requested by operation_level runner: 10
actual Memory.search(top_k=...) sent by Mem0 adapter: 20
Mem0Config.smoke().top_k: 20
GAP CONFIRMED: query.top_k is not honoured by Mem0 adapter; config.top_k always wins
```

现有测试（`tests/test_mem0_adapter.py` 多处 `top_k=20` 断言，含逐题
`retrieval.metadata["top_k"] == config.top_k`）实际上是把这个（可能非预期的）行为当
基线在测，没有任何用例断言 `query.top_k` 会被采用——**测试盲点**，不是回归。是否需要让
Mem0 adapter 采用 `query.top_k`（影响 QA 的 `top_k=20` 是否也要改由调用方决定）留给
共享实现卡与架构师裁定；HaluMem update probe 在当前实现下实际检索窗口比官方宽（20 而非
10），偏宽通常不会漏检，但不是官方口径的精确复现。

### 6.2 operation-level runner 未接入 Mem0 的 clean-failed-ingest hook

`cli/run_prediction.py:681-684` 为标准路径构造 `clean_failed_ingest_conversation`，
但只在 `else` 分支（`run_predictions()`，:748-780）传入；`run_operation_level_predictions()`
（:721-746）调用点、以及该函数自身签名（`operation_level.py:64-82`）**都没有**
`clean_failed_ingest_conversation` 参数。`_clean_mem0_failed_ingest_state`
（`registry.py:640-655`）因此对 HaluMem operation-level 路径完全不可达。

推论链（未做真实故障复现，纯代码路径分析）：一个 conversation 在
`_run_operation_conversation` 中途抛异常（比如 session 3 时 API 超时）→
`conversation_status[...] = {"status": "completed"}` 不会执行（该赋值在
`_run_operation_conversation` **返回之后**才发生，`operation_level.py:187-191`）→
resume 时 `state.get("status") == "completed"` 为 False → 该 conversation 从 session-1
整段重新 `_run_operation_conversation`，重新对已经成功 add 过的 session（如 1、2）再次调用
`provider.ingest(SessionBatch)`。由于没有 clean hook 清空该 `isolation_key` 的 Mem0
namespace，且 Mem0 是 ADD-only（无框架层去重），存在对已成功 session 重复 `Memory.add()`
的结构性风险。真实是否产生重复长期记忆取决于 Mem0 内部 embedding 相似度判定（未在本卡
验证，需要真实 API，超出零 API 范围），但**框架层没有任何机制阻止重复 add 被提交**这一点
是确定的代码事实。

现有测试 `test_operation_level_resume_skips_completed_user`（`test_operation_level_runner.py`）
与 `test_halumem_operation_resume_skips_completed_and_runs_pending_user`
（`test_halumem_registered_prediction.py`）只覆盖「已完成的 conversation 被跳过」，**没有**
覆盖「部分完成后失败、resume 重跑该 conversation」的场景——测试盲点。

**两处缺口均只影响「重试/resume-after-failure」这一操作条件，不影响本卡 §0 主张的单趟
正常路径**（session 边界、report 增量、时间、隐私等八项锁死事实在 §2 探针下全部成立）。
是否需要给 operation-level runner 补 clean-failed-ingest 参数、是否需要 Mem0 adapter 采用
`query.top_k`，两者都建议交给合流后的共享实现卡统一处理（若采纳，会同时影响
LongMemEval，因为它与 HaluMem 共享 `_retrieve_native`）。

## 7. Medium 最小 W1 smoke shape（不估算 API 次数、不运行 API）

按 workflows 冻结卡 §4「固定形状零旋钮 smoke」：首 conversation、4 session × 2 turn、
1 题；HaluMem CLI 对 smoke 裁剪参数一律 fail-fast，不可自定义更小规模。结合本卡 §1/§2
结论，该 smoke 下 Mem0 侧结构性可预期：

- 4 次 `Memory.add()`（每 session 恰一次，session_memory_report=True 强制整 session
  单 chunk）；
- 4 条 `session_memory_reports.jsonl` 记录（`status` 全部应为 `"ok"`，内容因真实 API
  抽取结果而异，可能为空列表——空列表本身不代表故障，见探针 3）；
- 0~4 条 `update_probe_results.jsonl` 记录（取决于前 3 个 session 的 gold
  `memory_points` 里有多少条 `is_update=="True"` 且非空 `original_memories`；第 4
  session 之后没有再下一 session 触发它自己的 update probe，因为 update probe 发生在
  **本 session ingest 之后、下一步 QA 之前**，若首个 conversation 的第 4 session 恰好
  没有 gold memory_points 或该题落在最后一个 session，可能为 0 或非 0，需真实数据确认，
  本卡不做该项估算）；
- update probe 每次调用 `provider.retrieve(top_k=10, purpose="memory_update_probe")`，
  但 Mem0 实际执行的是 `top_k=20`（§6.1）；
- 1 次 QA `provider.retrieve(top_k=20, purpose="qa")` + 1 次框架 answer LLM 调用；
- `max_workers` 必须显式为 1（`mem0.toml` 的 `official_full` 默认 10 会被两层
  fail-fast 拒绝，需按 smoke_max_workers 或 smoke profile 显式覆盖）。

不给出真实 LLM/embedding 调用次数、token 或成本估算——结构操作数不能换算成 API 调用数
（actor-handbook §6 纪律），真实 pilot 才能给出该数字。

## 8. 判词与依据

`READY_FOR_JOINT_RULING`。

依据：
1. 卡 §4 全部八条锁死事实均由零 API stateful 探针（真实累积 store、脚本化零抽取/畸形
   item、逐层 trace）直接验证成立，无一条被生产源码推翻；
2. 卡 §2 稳定 benchmark/evaluator 事实（operation-level 顺序、extraction 对象、update
   路由、六项/C-H-O/三种 memory type、Recall N/A）经本轮 registry/evaluator 源码复核，
   Mem0 未引入任何专属分支或特判，方法中立性成立；
3. 隐私边界、run_id 隔离、manifest 身份链均确认无 Mem0 专属泄漏或身份缺口；
4. 两项新发现（§6.1 update-probe top_k 未被采用、§6.2 operation-level 未接
   clean-failed-ingest）是真实代码缺口，但只影响「精确复现官方 top_k=10」与
   「resume-after-failure 的幂等性」两个非本卡核心主张的维度，不构成对 §0/§4 判词的
   推翻，按仓库既有「声明缺口」idiom（如 `integration/mem0.md` B7/B9 的 🟡 标记）处理，
   随笔记交联合裁决决定是否需要共享实现卡跟进。

不授权真实 smoke；本卡不改动生产代码、不改动其他文件。

## 9. 架构师联合验收升格（2026-07-19）

本 note 的 `READY_FOR_JOINT_RULING` 只表示审计完成，不表示 HaluMem 可直接 smoke。联合裁决
把 §6 两项从“单趟不阻塞”升格为 **Mem0 frozen 前必须关闭**：

- update scorer 的输入必须由共享 operation runner 截成有序 top-10；不改 Mem0 TOML 的产品
  retrieval depth，也不谎称 provider 底层只检索 10；
- operation runner 必须接入标准 clean-failed-ingest 契约，失败写 `failed_ingest`，显式 retry
  有 hook 才先清理重跑，无 hook fail-closed。

完整理由和允许改动范围见同目录 `mem0-joint-ruling.md`；不得只拿本 note 的单趟正常探针跳过
这两道操作正确性门。
