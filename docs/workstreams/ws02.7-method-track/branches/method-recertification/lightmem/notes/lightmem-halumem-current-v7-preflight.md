# LightMem × HaluMem current-v7 差量预检（source-locked，零 API）

> 卡：`branches/method-recertification/lightmem/cards/actor-prompt-lightmem-halumem-current-v7-preflight.md`
> 执行：Claude Code / Opus 4.8 actor，独立 worktree
> `/Users/wz/Desktop/mb-actor-lightmem-halumem-preflight`（branch
> `actor/lightmem-halumem-current-v7-preflight`，base `3bbfd4a`）。
> 零真实 API / 零真实 smoke / 零生产代码改动；只新增本 note。
> 总判词见 §8。

## 0. Baseline / source-lock / current identity

| 项 | 值 | 来源 |
|---|---|---|
| worktree base HEAD | `3bbfd4a`（`docs(method-track): record longmemeval acceptance gate`） | `git rev-parse` |
| HaluMem-Medium.jsonl | sha256 `486fbc130a5c8781a2af27ffa508a1d7855245137aa449c193ac4d29c45634e7` / `33511525` bytes | 本轮重算 = frozen lock 逐字一致 |
| HaluMem-Long.jsonl | sha256 `dfdbed570b402b7b8c17e0d7808fc6f3ae7a53b6144f18feb16bbdd3f55cb0c9` / `106535674` bytes | 本轮重算 = frozen lock 逐字一致 |
| source lock | `ws02.6/notes/halumem-source-lock.json` | 未漂移 → 继承 §1 census |
| adapter version | `LIGHTMEM_ADAPTER_VERSION = conversation-qa-v7`（probe 实读） | `lightmem_adapter.py` |
| consume granularity | `_lightmem_consume_granularity("halumem") → "session"` | `registry.py:214-223` |
| session report | `session_memory_report = context.benchmark_name == "halumem"` | `registry.py:451`；`_build_lightmem_system` |
| registration | task_families={CONVERSATION_QA}、caps={CONVERSATION_ADD, MEMORY_RETRIEVAL}、`consume_granularity_resolver=_lightmem_consume_granularity`、`retrieval_evidence_contract_version="v1"` | `registry.py:1047-1080` |

**gitignored 资产处置**：`data/`、`models/`、`third_party/benchmarks/` 三处
`.gitignore` 目录规则未匹配到软链文件（trailing-slash 只匹配目录），故它们以 `??`
出现；全程只显式 `git add` 本 note，从不 `git add -A`，软链不入库、不改、不暂存。

**current config identity（`configs/methods/lightmem.toml [smoke]` → `LightMemConfig`
→ `build_backend_config`）**：

| 字段 | smoke 值 | 备注 |
|---|---|---|
| llm_model | `gpt-4o-mini` | Phase 1 统一 |
| embedding_model_path / dims / device / distance | `models/all-MiniLM-L6-v2` / `384` / `cpu` / Qdrant `COSINE` | dims 取 dataclass 默认 384（TOML 未覆盖）；COSINE 为 vendored `qdrant.py:65` 默认 |
| retrieve_limit | `60` | 底层 `embedding_retriever.search(limit=retrieve_limit)` |
| extract_threshold / compression_rate / stm_threshold | `0.5` / `0.7` / `512` | ws02.5 归一化 repo 默认 |
| topic_segment / text_summary / pre_compress | `true` / `true` / `true` | |
| extraction_mode | `flat` | dataclass 默认（TOML 未设） |
| api_timeout_seconds / api_max_retries | `60.0` / `8` | `_inject_api_retry_timeout` |
| max_workers | `1` | operation-level 硬门 |
| lifecycle_profile | `online_soft`（TOML 显式；dataclass 默认亦 online_soft） | 论文 soft update = direct insert |
| missing_timestamp_policy | `preserve_none`（TOML 显式；dataclass 默认 `require`） | 仅允许与 online_soft 组合（校验 `lightmem_adapter.py:253-254`） |
| messages_use | `hybrid`（TOML 显式；dataclass 默认 `user_only`） | probe 证 `build_backend_config['messages_use']='hybrid'` |
| backend `update` | `offline`（固定） | probe 证 `build_backend_config['update']='offline'` |

manifest/resume 身份：operation-level `_method_manifest_with_protocol` 以
`system.consume_granularity` 补 `consume_granularity`（HaluMem="session"），
`_validate_consume_granularity` 与实例交叉校验；`_manifests_match_for_resume` 精确比较，
旧 turn/pair manifest 不能 resume 为 session（`prediction.py:1362-1384`,
`operation_level.py:795`）。

## 1. 继承 benchmark 事实（不重跑 census）

source hash/字节逐字命中 frozen lock，故按卡 §3 直接继承，未流式全扫 Medium/Long、
未重算规模/角色/时间/memory-point 分布：

1. Medium=20 user / 1,387 session / 60,146 turn / 3,467 题；Long 额外 1,030 个
   generated-QA session（总题数同 3,467）。
2. 对话全库严格 `user→assistant` 交替；turn timestamp 与 session start/end 三层齐全。
3. 491 普通 session 缺 `questions` 键；1,030 generated session 有空 questions、无
   memory_points，只 ingest。
4. `is_update` 是字符串 `"True"/"False"`；更新点须带非空 `original_memories`。
5. `evidence` = `{memory_content,memory_type}` list，无 turn id → HaluMem retrieval
   Recall/NDCG N/A。
6. operation 顺序：每 session ingest → session memory report → update probes → QA。
7. smoke 固定形状：Medium 首 conversation，4 session × 每 session 前 2 turn × 1 QA；
   operation-level 单 worker，smoke resume 禁用。
8. 官方 answer builder 无 question-time 槽。

来源：`ws02.6/notes/halumem-frozen-v1.md`、`docs/survey/datasets/halumem.md`、
`docs/survey/workflows/halumem.md`、`halumem-source-lock.json`。

## 2. 本批 method 差量（LightMem × HaluMem current-v7）

自 2026-07-14 历史 smoke（`lm-halumem-unified-s2`）以来发生、需要在本卡逐层证明的 method 侧变化：

- **hybrid role**（v4）：`messages_use="hybrid"`，user+assistant 都进抽取。
- **online-soft**（`825132f`）：`lifecycle_profile="online_soft"`，HaluMem 路径不跑全库
  consolidation。
- **公共 readout v7**（`d11d749`）：由 `[Memory recorded on: 15 December 2025, Mon]`
  改为官方 retrieve 格式 `{time_stamp} {weekday} {memory}`（完整 ISO）；`time_stamp is
  None` 只出 memory 文本。**这是 HaluMem 格最主要的 current-v7 差量**。
- **embedding observation v7**（`d11d749`）：`text_embedder.embed` 透明 observer。
- **legacy provenance 单事实源 v7**：`metadata["provenance_granularity"]` 与
  `RetrievalResult.evidence` 读同一个 `RetrievalEvidence`。
- **RetrievalEvidence 逐题矩阵**（M0/M1）：HaluMem 恒 `n_a`。
- session capture 契约（`_capture_inserted_memories`）、registered
  `consume_granularity="session"` 参与 strict manifest/resume。

## 3. Medium fixed-smoke 生产链逐层映射

用 production adapter/aggregator/operation-level runner + fake LightMem backend
（复用 `tests/test_lightmem_adapter.py` 的 `SessionCaptureFakeLightMemoryBackend` /
`FakeLightMemoryBackend`）零 API 驱动。探针脚本构造与逐层断言如下，stdout 逐字见 §3.1：

```
raw HaluMem session (user→assistant, private memory_points)
  └ benchmark_adapters/halumem.py:_session_from_raw
      → canonical Session/Turn（public content/role/time；memory_points 入 private_metadata）
  └ runners/event_stream.py:build_turn_events → 携 original_content/turn_time/
      session_time/turn_metadata/turn_images/normalized_role 的 TurnEvent 流
  └ runners/operation_level.py:_ingest_and_probe_session
      → 按 session_id 过滤事件 → GranularityAggregator("session")._aggregate_sessions
      → 每 session 恰一个 SessionBatch（UnitRef/SessionRef 信号被跳过）
  └ methods/lightmem_adapter.py:ingest → isinstance SessionBatch → _ingest_halumem_session
      → _native_session_messages → _normalize_session_to_pairs（非 locomo 分支：
        读 canonical normalized_role，user→assistant 成 pair）→ flat message list
      → 单次 backend.add_memory(messages, force_segment=True, force_extract=True)
        （在 _capture_inserted_memories 只读旁听 embedding_retriever.insert 内）
      → 本 session 增量 memories 存 _session_report_memories[(iso_key, session_id)]
  └ provider.end_session(SessionRef) → SessionMemoryReport(capture_status ok/empty)
  └ update probe：provider.retrieve(RetrievalQuery(query_text=memory_point.memory_content,
        top_k=10, purpose="memory_update_probe")) → _retrieve_native
      → _retrieve_with_payload(text_embedder.embed(query) + embedding_retriever.search(
        filters=None, return_full=True)) → formatted_memory + evidence(n_a)
  └ QA：provider.retrieve(RetrievalQuery(query_text=question.text, top_k=20,
        purpose="qa")) → unified answer builder（本卡不跑 answer LLM）
```

关键不变量逐条命中（§3.1 stdout 对应）：

1. **每 session 恰一次 `add_memory`**（`n_add_memory=2` 对应 2 个 session；单异形
   session `n_add_memory=1`），两 flag 均 `force_segment=True, force_extract=True`。
2. **role/content/order/external_id/time 各恰一次、不跨 session**：add_memory[0] 只含
   session-a 两 turn，add_memory[1] 只含 session-b 两 turn，external_id 顺序
   `[session-a:t1, session-a:t2]` / `[session-b:t1, session-b:t2]`。
3. **hybrid**：`build_backend_config['messages_use']='hybrid'`（§3.1 CHAIN F），user 与
   assistant 都在 message list；正常 HaluMem 数据不产 placeholder。
4. **force flush ≠ 全库 consolidation**：`online_soft` 下
   `construct_update_queue_all_entries calls=[]`、`offline_update_all_entries calls=[]`
   （end_conversation 后仍空；HaluMem 路径 `_should_run_locomo_offline_consolidation()`
   要求 `benchmark_name=="locomo"`，此处 False）。
5. **capture 只旁听本 session 实插**：session 报告增量非累计
   （session-a→`['session-memory-1']`，session-b→`['session-memory-2']`）；observer 只在
   `original_insert(...)` 成功后读 `payload["memory"]`，不改参数/返回；`with` 退出后
   `'insert' in retriever.__dict__ = False`（monkeypatch 已还原）。
6. **空抽取如实 empty**（CHAIN C）：`memories=[]`、`capture_status='empty'`、
   `captured_memory_count=0`，不造记忆；capture 路径缺失时
   `_capture_inserted_memories` 对缺 `embedding_retriever.insert` fail-fast
   （`lightmem_adapter.py:904-907`）。
7. **update probe / QA 只读在线状态**：retrieve 底层固定 `filters=None`
   （`lightmem_adapter.py:1051-1056`）；update probe 只把 `memory_content` 作 query_text
   （§3.1 `query_text='Alice lives in Boston now.'`），未把 memory point、answer、
   evidence、original_memories 传给 method。
8. **HaluMem evidence 恒 n_a**：update-probe 与 QA 两条 retrieve 的
   `evidence.status=n_a / reason=halumem_no_turn_qrel / provenance_granularity=none`，
   legacy `metadata["provenance_granularity"]=none` 与之同源。
9. **v7 官方 readout**：`_format_lightmem_memory_as_official_retrieve` full ISO →
   `'2025-12-15T10:00:00.000 Mon Alice lives in Boston.'`；`time_stamp=None` →
   `'Timeless fact.'`（无字面 None、无 weekday-only 前缀）；zero-hit → sentinel
   `'(No relevant memories found)'`。产品 readout **不再**出现历史
   `[Memory recorded on: ...]` wrapper（该 formatter 现仅供 LoCoMo author speaker 分组，
   `lightmem_adapter.py:2191-2224` docstring 明示不复用）。
10. **异形 session 不丢真实 turn**（CHAIN D，合成 assistant-first + 连续 user）：3 条
    真实 turn（`ASSISTANT-FIRST` / `USER-2` / `USER-3-CONSECUTIVE`）全部保留，仅补结构
    placeholder（marker `memory_benchmark_structural_placeholder`）；这是合成反例，不冒充
    数据实况——真实 HaluMem 严格交替，正常不产 placeholder。

### 3.1 fake probe stdout（逐字，零 API；dummy key + `http://127.0.0.1:9`）

探针入口：production `_ingest_and_probe_session` / `LightMem.ingest` /
`LightMem.retrieve` / `LightMem.build_backend_config` /
`_format_lightmem_memory_as_official_retrieve`；backend = 测试 fake（无真实
LLM/embedding/网络）。

```
======== CHAIN A: 生产 operation-level 交错流（2 正常 session + update probe） ========
provider.consume_granularity = session
provider.session_memory_report = True
provider.benchmark_name = halumem
LIGHTMEM_ADAPTER_VERSION = conversation-qa-v7
  session=session-a generated=False
  session=session-b generated=False

-- add_memory 调用次数与 force flags（每 session 恰一次）--
  n_add_memory = 2
  add_memory[0] kwargs={'force_segment': True, 'force_extract': True}
      role=user      ext_id=session-a:t1   time=2025-12-15T10:00:00 :: 'Alice moved to Boston.'
      role=assistant ext_id=session-a:t2   time=2025-12-15T10:00:05 :: 'Noted, Boston.'
  add_memory[1] kwargs={'force_segment': True, 'force_extract': True}
      role=user      ext_id=session-b:t1   time=2025-12-16T10:00:00 :: 'Alice adopted a dog.'
      role=assistant ext_id=session-b:t2   time=2025-12-16T10:00:05 :: 'A dog, great.'

-- session_memory_reports（增量、非累计）--
  session= session-a status= ok memories= ['session-memory-1'] capture_status= ok count= 1
  session= session-b status= ok memories= ['session-memory-2'] capture_status= ok count= 1

-- update_probe_records（只把 memory_content 作 query，无 gold answer/evidence）--
  gold_index= 3 query_text= 'Alice lives in Boston now.'
     record keys = ['duration_ms', 'formatted_memory', 'gold_memory_index', 'memories_from_system', 'query_text', 'session_ref']
     formatted_memory[0:80] = '2026-01-01T00:00:00.000 Thu Alice likes jasmine tea.\n2026-01-01T00:00:01.000 Thu'

-- online_soft 未触发全库 consolidation（§5.4）--
  construct_update_queue_all_entries calls = []
  offline_update_all_entries        calls = []

-- insert observer 已还原（不残留 monkeypatch）--
  'insert' in retriever.__dict__ = False

======== CHAIN B: QA / update 检索 evidence（HaluMem 必为 n_a） ========
  purpose=memory_update_probe
     evidence.status         = n_a
     evidence.reason_code    = halumem_no_turn_qrel
     provenance_granularity  = none
     metadata.provenance     = none
     formatted_memory[0:90]  = '2026-01-01T00:00:00.000 Thu Alice likes jasmine tea.\n2026-01-01T00:00:01.000 Thu Bob remem'
  purpose=qa
     evidence.status         = n_a
     evidence.reason_code    = halumem_no_turn_qrel
     provenance_granularity  = none
     metadata.provenance     = none
     formatted_memory[0:90]  = '2026-01-01T00:00:00.000 Thu Alice likes jasmine tea.\n2026-01-01T00:00:01.000 Thu Bob remem'

======== CHAIN C: 空抽取如实 capture_status=empty（不造记忆） ========
  memories = []
  capture_status = empty
  captured_memory_count = 0

======== CHAIN D: synthetic 异形 session（assistant-first + 连续 user）不丢真实 turn ========
  n_add_memory = 1 (单 session 一次)
  real messages       = [('assistant', 'ASSISTANT-FIRST', 's1:t1'), ('user', 'USER-2', 's1:t2'), ('user', 'USER-3-CONSECUTIVE', 's1:t3')]
  placeholder messages= [('user', 's1:t1'), ('assistant', 's1:t2'), ('assistant', 's1:t3')]
  真实 turn 内容集合 = ['ASSISTANT-FIRST', 'USER-2', 'USER-3-CONSECUTIVE']

======== CHAIN E: v7 官方 readout 格式 + zero-hit sentinel ========
  full ISO -> '2025-12-15T10:00:00.000 Mon Alice lives in Boston.'
  None time-> 'Timeless fact.'
  zero-hit formatted_memory = '(No relevant memories found)'
  zero-hit evidence.status  = n_a reason= halumem_no_turn_qrel

======== CHAIN F: messages_use=hybrid 进入 backend config（两 role 都抽取） ========
  backend_config['messages_use'] = hybrid
  backend_config['update']       = offline

PROBE_DONE
```

## 4. session capture/flush、online-soft、retrieve/readout/observer 结论

- **session capture/flush**：每 canonical session 一次 `add_memory(force=True)`，
  `_capture_inserted_memories` 只读旁听本次 insert，报告增量非累计、空即 empty、缺路径
  fail-fast。§3.1 CHAIN A/C 实证。
- **online-soft**：HaluMem 全程无 `construct_update_queue_all_entries` /
  `offline_update_all_entries`（§3.1）；这是 benchmark 交错结构约束下所有 method 的共同
  在线姿态（B2 姿态声明），非缺陷。
- **retrieve**：update-probe/QA 都走 `_retrieve_native`，`filters=None`，只读当前在线状态；
  query 只承载公开文本；evidence 恒 n_a。
- **readout**：current-v7 官方 `{time_stamp} {weekday} {memory}`，完整 ISO；None-time
  只出 memory；zero-hit 明确 sentinel。历史 `[Memory recorded on: ...]` 已 supersede。
- **observer 共存**：`_install_embedding_call_observer` 包 `text_embedder.embed`（每
  backend 一次，`_get_or_create_backend:1414`），`_capture_inserted_memories` 包
  `embedding_retriever.insert`（每 session、退出即还原）。两者包不同对象/方法，互不吞掉；
  embedding observer 观测失败吞异常、绝不改算法返回（`lightmem_adapter.py:1540-1544`）。

## 5. public / private 负空间检查

- **public `Session.metadata`** 仅 `{"is_generated_qa_session": bool}`
  （`halumem.py:387-391`）。
- **`Session.private_metadata`** 含 `memory_points`(deepcopy)、persona_info、raw times、
  source ids（`halumem.py:392-404`）——不进 public 事件流。
- **public `Question`** 仅 `{question_id, conversation_id, text, metadata={}}`；无 answer /
  evidence / question_type / question_time（`halumem.py:464-471`）。
- **`GoldAnswerInfo`** 持 answer、evidence、raw_evidence、difficulty、question_type、
  memory_points、persona；`gold_evidence_contract_version="v1"` 且
  `evidence_group_sets=()`（零 qrel view，`halumem.py:472-491`）。
- **runner 侧**：QA 用 `_make_public_question` + `validate_no_private_keys(question.to_dict())`
  （`operation_level.py:290-291`）；`_answer_prompt_record` 末尾 `validate_no_private_keys`
  （`operation_level.py:624`）。
- **update_probe_record**（§3.1 record keys）只含 `session_ref/gold_memory_index/query_text/
  formatted_memory/memories_from_system/duration_ms`；gold answer、evidence、
  original_memories 不落该 record，method 也从未收到它们。update 点筛选
  `is_update != "False"` 且 `original_memories` 非空（`operation_level.py:530-548`）——
  §3.1 中 index 4（`is_update="False"`）被正确跳过，只 index 3 触发 probe。

## 6. evaluator / 依赖顺序 / N/A / workers-resume 矩阵

| evaluator | requires_api | 触发 / 依赖 | current 判据 |
|---|---|---|---|
| halumem-extraction | True(judge) | session_memory_reports（`read_required_jsonl` 缺即 fail-fast）；`status=="ok"` 才评，全非 ok → **N/A**；空抽取 → integrity `0/"empty extracted memories"` | `halumem_extraction.py:48-71,133` |
| halumem-update | True(judge) | 空 `memories_from_system` → `skipped_empty_retrieval_count`，归 integrity、**不进 update 分母** | `halumem_update.py:41-68` |
| halumem-qa | True(judge) | PROMPT_MEMZERO 逐字（frozen） | registry `requires_api=True` |
| halumem-memory-type | **False** | 读 `halumem_extraction`+`halumem_update` 两份 scores artifact，**缺即 fail-fast**（"requires prior … evaluation artifacts"）；零 judge 调用 | `halumem_memory_type.py:28-37` |
| f1 / normalized-em / substring-em | False | QA answer artifact-only | registry `supported_benchmarks⊇{halumem}` |
| retrieval Recall/NDCG | — | **无 halumem-recall/ndcg evaluator 注册** | registry 全表无 halumem recall 项 |

- **依赖顺序**：真实 B11 时 extraction→update→qa 判 judge 各自跑；memory-type 必须在
  extraction+update artifacts 已存在后跑（artifact-only，抢跑即 fail-fast）。本卡不调用
  任何 evaluator。
- **workers/resume**：`run_operation_level_predictions` 入口 `max_workers != 1 → raise`
  （`operation_level.py:105-108`）；resume 为 conversation 级 checkpoint
  （`conversation_status`，`operation_level.py:170-171,187-191`），manifest 精确匹配
  （`_manifests_match_for_resume`，含 `method.consume_granularity=session`）；smoke resume
  禁用（frozen）。
- **generated session**：`_ingest_and_probe_session` 对 generated 只 ingest + end_session
  后 `return True`（报告被丢弃、不记 session report、不跑 update probe），caller
  `if generated: continue` 跳过 QA（`operation_level.py:372-374,286-287`）。current 代码
  会对 generated session 也调一次 `end_session`（结果丢弃），属无害；Medium smoke 首
  conversation 无 generated session，该分支只在 Long 出现。

## 7. 现有测试覆盖 与 真实 B11 尚缺的 runtime 证据

**已被现有测试锚死（无需真实 API）**：

- `test_lightmem_adapter.py::test_lightmem_halumem_session_reports_are_incremental_and_
  force_flushed`：2 session→2 add_memory、force flags、逐 session message/external_id、
  增量报告、observer 还原。
- `…::test_lightmem_halumem_empty_capture_is_reported_without_fabrication`：空抽取 empty。
- `…::test_lightmem_end_session_is_inactive_outside_halumem`：非 HaluMem end_session no-op。
- `test_halumem_registered_prediction.py`：三操作交错 e2e / privacy / resume / generated
  跳过。
- `test_halumem_evaluators.py`：聚合 / 0 分母 / 空检索路由 / 合成指标依赖。
- `test_halumem_adapter.py`（真实 Medium 前缀锚 4×18/2/5）、`test_halumem_unified_prompt.py`
  （MEMZERO parity）、`test_method_registry.py`（registration 身份）。
- 本卡 §3.1 探针补充：生产 operation-level runner + v7 readout/evidence/observer 的零 API
  逐层证据（现有测试未逐字打印 v7 官方 readout 与 hybrid backend config 的组合形态）。

**真实 B11 仍缺、只能由付费 smoke 提供的 runtime 证据**：

1. 真实 gpt-4o-mini 抽取在固定 Medium smoke 上产出的真实 session_memory_reports（哪些
   session capture_status=ok / empty，非 fake `session-memory-N`）。
2. 真实本地 all-MiniLM embedding 的 `EmbeddingCallObservation`（build/retrieval 两阶段真实
   token/latency），及与真实 add_memory/insert 次数的对齐。
3. 三 judge（extraction/update/qa）在真实 artifacts 上的运行时聚合、空检索 integrity 路由
   实际计数、memory-type 合成分母，与依赖顺序执行的落盘一致性。
4. 真实 Qdrant per-conversation collection 物理隔离与 clean-retry。
5. answer LLM（本卡零 API 未跑）在 unified MEMZERO prompt 上的端到端产物。

以上均需用户批准预算/规模/run_id 后由 §8 建议的固定 smoke 执行；本卡不估算 API 次数、不写
命令、不建 outputs。

## 8. 总判词

current main 的 LightMem × HaluMem 差量链在 source-locked、零 API 前提下逐层自洽：
registered session ingest + session report、单次 force-flush add_memory、增量 capture、
online-soft 不跑全库 consolidation、`filters=None` 只读检索、HaluMem evidence 恒 n_a、
v7 官方 ISO readout + zero-hit sentinel、public/private 负空间干净、evaluator 依赖顺序与
workers/resume 门齐备。未命中任何卡 §9 停工条件（source hash 一致、无承重事实被推翻、
registered 确为 session ingest+report、真实 turn 无丢失/重复/跨 session、capture 未冒充
增量、online-soft 未暗跑 consolidation、私有数据未泄漏、retrieval evidence 无数值资格、
observer 与 runner 共存）。

```
READY_FOR_HALUMEM_B11_COMMAND
```

建议真实 smoke 沿用冻结的 Medium `1 conversation / 4 sessions × 每 session 前 2 turns /
1 QA / workers=1` 固定形状；evaluator 按 extraction → update → qa（judge）→ memory-type
（artifact-only，最后）依赖顺序执行，retrieval Recall/NDCG 保持 N/A。命令、预算与 run_id
由架构师在用户批准后生成。

## 9. 架构师强验收与新增共享前置门

2026-07-19，GPT-5.6 sol 架构师在 main 独立完成：

- `git show` 确认 actor commit 仅新增本 note；
- 现场 `shasum -a 256` / `wc -c` 复算 Medium/Long，hash 与字节数逐字命中 §0；
- 按卡同一承重命令复跑：`230 passed, 1 warning in 8.17s`；
- 文档标准门：`5 passed in 0.86s`；`git diff --check` clean。

因此 actor 对 **LightMem × HaluMem method/current-v7 差量**的
`READY_FOR_HALUMEM_B11_COMMAND` 判词被接受，没有生产返工。

但 BEAM 真实 B11 开箱同时发现一个本 note §6 未覆盖的共享 runner 缺口：
`_run_artifact_level_evaluation()` 不建立 evaluator `EfficiencyCollector/judge_scope`，也不写
metric 专属 model inventory/observations。HaluMem extraction/update/qa 都继承
`supports_efficiency_observability=True` 且走这条 artifact-level 路径；若现在执行，judge 会出分，
但 token/cost artifact 缺失，无法通过 checklist B7/B11。

这不推翻本 note 的 method READY，只把发命令的顺序收紧为：

```text
共享 artifact-level judge observability R1
→ BEAM 既有 run judge-only 补观测
→ HaluMem Medium W1 首次真实 B11
```

共享修复见 `../../../evaluator-observability/README.md`；禁止把它写成 HaluMem 或 LightMem 特判。

## 10. 架构师 R2 改判：真实 sensory buffer 推翻 READY

2026-07-19，用户在 BEAM judge observation 补写通过后，特别提醒 HaluMem 不是“先完整建库再
统一评估”，而是每个 session 灌入后立即执行 extraction/update/QA；其中 extraction 的候选只能
来自当前 session。架构师因此没有直接发付费命令，而是把 §3.1 的 fake backend 证据下沉到
vendored `SenMemBufferManager` 与 `LightMemory.add_memory()` 真实状态机，得到两个会推翻
§8/§9 READY 的确定性反例。

### 10.1 force flush 没有清掉已经输出的 current buffer

`sensory_memory.py:98-110` 先按 `2 * boundary` 输出 segment；`force_segment=True` 时又把 remaining
tail 全部加入 `segments`，但随后把 `start_idx` 错写成 `len(boundaries)`。后者是 boundary 个数，
不是已输出 message 数。用真实 manager + 确定性 fake tokenizer/segmenter/embedder 的零 API
探针现场得到：

```text
session1_segments= [[('user', 'u1'), ('assistant', 'a1')],
                    [('user', 'u2'), ('assistant', 'a2')]]
after_session1_buffer= [('assistant', 'a1'), ('user', 'u2'), ('assistant', 'a2')]
token_count= 1
session2_error= IndexError list index out of range
```

这说明“observer 只记录本次 insert”并不足以证明 session 增量：如果本次 extraction 的输入已经
混入 sensory residual，observer 会忠实记录一份跨 session 的错误结果。

### 10.2 forced tail 覆盖同次调用已自动切出的 prefix

`lightmem.py:332-335` 先令 `all_segments = add_messages(...)`，但 force 分支又把它赋值为
`cut_with_segmenter(...)`，而不是保留 automatic segments 后追加 forced tail。以 fake sensory
manager 固定返回 `AUTO` 与 `TAIL`、真实 `LightMemory.add_memory()` 驱动 fake short-memory，
现场输出为：

```text
shortmem_received= [[{'role': 'user', 'content': 'TAIL'}]]
```

即本 session 较早越过 threshold 时已经切出的 prefix 没有进入 extraction。Medium 文件自带的
`dialogue_token_length` 字段中，1,387 个 session 有 1,347 个大于 512；这不是 LightMem 压缩后
token 数的等价替代，不能据此计算 API 成本，但足以说明 full-session threshold 路径不是可以
忽略的理论角落。

### 10.3 旧预检为何漏过、当前裁决

旧 §3.1 的 `SessionCaptureFakeLightMemoryBackend` 直接在每次 add 伪造一条 insert，验证了 adapter
的 call/capture/report 边界，却完全没有执行 sensory/short-memory 状态机；既有官方 preprocessing
test 又只覆盖 `propose_cut() -> []` 的 clean branch。架构师此前接受 READY 属验收盲点，现以
真实 core 反例勘误，不拿 smoke 的 `2 turns/session` 恰好通常不触发 boundary 当作通关依据。

三项 HaluMem metric 的**语义资格不变**：LightMem 可提供 session extraction report、在线累计
状态上的 update probe、以及每 session 后即时 QA；memory-type 仍是 extraction/update artifact
上的派生指标，retrieval Recall/NDCG 仍 N/A。但在修复并强验收前，extraction 的“当前 session
完整且仅当前 session”不变量不成立，因此付费 B11 暂停，§8 与 §9 的 READY 被 supersede：

```text
BLOCKED_SESSION_FLUSH_INTEGRITY
```

最小修复卡：
`../cards/actor-prompt-lightmem-halumem-session-boundary-r1.md`。修复不得调 segmentation 参数或
metric；只收敛 forced flush bookkeeping、automatic+tail segment 合并、真实 source identity 与
强反例。
