# LightMem × LongMemEval latest-main B11 差量预检

> 预检 actor 交付（零 API、只读离线；只新增本 note，不改生产代码）。目标不是重做
> S/M 大扫描，而是核对 **current main 的 canonical role → TurnPair → LightMem hybrid
> message → retrieve/readout → metric eligibility** 是否具备一次最小付费 B11 smoke 的
> 条件。稳定摘要由架构师强验收后回填 survey/integration。

## 1. baseline / source / config identity

| 项 | 值 |
|---|---|
| 预检日期 | 2026-07-18 |
| worktree | `/Users/wz/Desktop/mb-actor-lightmem-lme-preflight`（branch `actor/lightmem-lme-preflight`） |
| 基线 HEAD | `44095e2`（`docs(lightmem): issue longmemeval latest-main preflight`；开工 `git status --short` 仅 gitignored `data/`、`models/`、`third_party/benchmarks/` 软链） |
| 执行模型 | Claude Opus 4.8（`claude-opus-4-8`，本会话系统提示） |
| LightMem adapter 版本 | `conversation-qa-v6`（`LIGHTMEM_ADAPTER_VERSION`，较 time-audit 时的 v5 已过 caption v6 重建） |
| reader prompt 版本 | `lightmem-reader-v1` |
| LightMem vendored `source_sha256` | `74be165faac06d5891e598e6d869f70220dfc4a90363b84bb44c0571fa8a5a35`（7 文件，`build_lightmem_source_identity()`）——**与 time-audit 基线 `914a198` 完全一致，vendored 源码零漂移** |
| S 数据 | `data/longmemeval/longmemeval_s_cleaned.json`（软链至主工作区，500 instance） |
| 主 profile | `configs/methods/lightmem.toml [smoke]`，经 `load_typed_profile(...)` 强类型加载核对 |
| registry 注入 | `consume_granularity="pair"`、`benchmark_name="longmemeval"`、`session_memory_report=False`（`methods/registry.py:_build_lightmem_system`:399-407） |
| 检索契约 | `prompt_track="unified"` + `build_longmemeval_unified_answer_prompt` + `gold_evidence_contract_version="v1"`（`benchmark_adapters/registry.py`:633-647） |

一手扫描/探针脚本 `lme_preflight_probe.py`（六类输入逐层探针）与 `lme_candidate_scan.py`
（S 公开 shape/规模扫描）按卡 §1/§9 为 Claude Code 会话专属 scratchpad 临时产物、**不入库**。
它们对 Codex 架构师（GPT-5.6 sol）不可见，故本 note 自包含：探针构造用 §3 列的 production
入口 + fake backend 完整描述，**关键 stdout 已逐字抄录进 §3（六类探针全量输出）与 §9（候选
扫描全量输出）**，架构师可只凭本 note + 引用的一手源码行号自写探针复验，无需访问 scratchpad。

## 2. 已验收旧事实与本轮差量范围

以下八条经 Opus 4.8 主体 + 架构师 R1 强验收（`lightmem-longmemeval-input-time-audit.md`
§1/§2/§4/§6/§8），本轮只核对 current main 是否仍与之相符，**不重跑 M 全量、不重扫 2.5GB、
不重争 500ms 算法**：

1. S/M raw turn `246,750 / 2,446,993`、blank `12 / 295`；跳过 blank 后每个 retained
   canonical turn 恰进一个 pair 一次；
2. assistant-first / pure-assistant / 同 role 连续 / 奇数 turn 均 benchmark-native shape，
   canonical role 只读结构化 `role`；
3. 相邻 `user→assistant` = real-real pair；孤立 user 补 empty assistant placeholder；
   孤立 assistant 补 empty user placeholder；不跨 session 配对；
4. placeholder 非 public turn、无新 source id，从 extraction 文本/token 计数过滤，但占
   pair/sequence slot；
5. LME turn 无独立时间，继承 session raw time；相同 raw time 的 slot 产生 500ms
   method-derived tie-break；不改 raw、不合成 corrected time；
6. `question_date` 同日分钟错序不作 as-of cutoff；retrieve 保持 `filters=None`，完整
   history；
7. Phase 1 主 build = `messages_use="hybrid" + lifecycle_profile="online_soft"`；官方
   `user_only` 只作 future reproduction；
8. LME pair candidate ids 不能证明事实来自哪个 child，故 semantic evidence 必须
   `n_a/pair_source_id_not_turn_exact`，rank 不硬算。

**本轮差量结论：current main（`44095e2`，adapter v6）一手源码与上述八条全部一致，无冲突、
无停工触发。** 逐承重点核对见 §3–§6。

## 3. 六类输入逐层映射表（production adapter + event stream + v3 ingest + fake backend）

探针链路：raw LME instance → `LongMemEvalAdapter._conversation_from_instance()`（canonical）
→ `build_turn_events()` → `GranularityAggregator("pair")`（`_aggregate_pairs`）→
`LightMem.ingest(TurnPair)` → `_native_pair_batch` → `_normalize_session_to_pairs` →
`_write_native_batch`/`end_conversation`（fake backend 记录 `add_memory` 序列）。
session_time 固定 `2023/05/20 (Sat) 00:44`；每条 raw 打私有 `has_answer/answer/
answer_session_ids` 反例，全链断言无泄漏。零 LLM/embedding。

| # | raw roles | canonical Turn（id / normalized_role） | TurnPair（kind） | LightMem [user, assistant] message | add_memory batch 边界 |
|---|---|---|---|---|---|
| 1 | `user→assistant` | t0 user / t1 assistant | 1× real-real | `[REAL user t0, REAL asst t1]`，两 slot `src_ids=[t0,t1]` | 1 batch，`force_seg/extract=True` |
| 2 | `assistant→user→assistant` | t0 asst / t1 user / t2 asst | orphan(t0) + real-real(t1,t2) | b0 `[PH user(t0), REAL asst t0]`；b1 `[REAL user t1, REAL asst t2]` | 2 batch，seq `[False, True]` |
| 3 | `user→user` | t0 user / t1 user | dangling(t0) + dangling(t1) | b0 `[REAL user t0, PH asst(t0)]`；b1 `[REAL user t1, PH asst(t1)]` | 2 batch，`[False, True]` |
| 4 | `assistant→assistant` | t0 asst / t1 asst | orphan(t0) + orphan(t1) | b0 `[PH user(t0), REAL asst t0]`；b1 `[PH user(t1), REAL asst t1]` | 2 batch，`[False, True]` |
| 5 | 单 `user` | t0 user | dangling(t0) | `[REAL user t0, PH asst(t0)]` | 1 batch，`True` |
| 6 | 单 `assistant` | t0 asst | orphan(t0) | `[PH user(t0), REAL asst t0]` | 1 batch，`True` |

锁死的不变量（全部探针实测通过，`ALL PROBES PASSED`）：

- **真实 turn 顺序/次数/content bytes/canonical turn id 不变**：每类 real message content
  集合 == raw 非 blank content 集合（`real_once` 断言），canonical id 恒为 `sess:tN`；
- **speaker 来自结构化 role**：canonical `normalized_role` ∈ {user, assistant}，
  `_canonical_role` 明确拒绝从 metadata/speaker 回退（`lightmem_adapter.py:564-574`）；
  message `speaker_id/speaker_name` = `turn.speaker`（LME 即 user/assistant）；
- **external_id + 同一 candidate list**：每 real message 有 `external_id=turn_id`；pair 两侧
  `source_external_ids` 为同一去重 candidate list（real-real 为 `[t0,t1]`，单侧为 `[tN]`，
  `_stamp_pair_ids`）；
- **placeholder 严格 boolean marker**：`content=""` + `memory_benchmark_structural_placeholder=True`
  才被过滤；镜像同 pair 真实 child 的 time/speaker/external_id/source_external_ids；
- **hybrid 抽取文本**：real user/assistant 各恰一次进 message dict、placeholder 携 marker——
  vendored `concatenate_messages`（openai.py:298 按 messages_use 过滤 role + 排除 marker）与
  token 计数（short_term_memory.py:23）据此排除 placeholder，是 §2.4/F4 已验收事实，本轮在
  message-dict 边界复证 marker/content 前提成立；
- **不跨 session 配对**：`TurnPair.__post_init__` 强制两 turn 同 `session_id`
  （provider_protocol.py:77-78），`_group_by_session` 按连续 session_id 分组
  （event_stream.py:210-228），末 user 与下一 session 首 assistant 不能成 real-real；
- **私有边界零泄漏**：`has_answer/answer/answer_session_ids/gold` 从 canonical Turn.metadata
  （`PRIVATE_MESSAGE_KEYS` 过滤，longmemeval.py:50-62/659-675）、TurnEvent、message dict 全程
  缺席；gold 只在 `conversation.gold_answers`（探针逐层 `assert tok not in blob`）。

### 六类探针逐字 stdout（`OPENAI_KEY=dummy BASE_URL=http://127.0.0.1:9 uv run python lme_preflight_probe.py`，零 API）

```text
SHAPE 1_normal_user_assistant  raw_roles=['user', 'assistant']  session_time='2023/05/20 (Sat) 00:44'
  canonical session_id=sess_A session_time='2023/05/20 (Sat) 00:44'
    Turn(id=sess_A:t0 speaker='user' normalized_role='user' content='user-content-0' turn_time=None meta_keys=[])
    Turn(id=sess_A:t1 speaker='assistant' normalized_role='assistant' content='assistant-content-1' turn_time=None meta_keys=[])
  TurnPairs (1):
    pair_index=0 kind=real-real first.role=user second.role=assistant session_id=sess_A
  add_memory batches (1):
    batch#0 force_segment=True force_extract=True :: [REAL role=user content='user-content-0' ext_id=sess_A:t0 src_ids=['sess_A:t0', 'sess_A:t1'] time='2023/05/20 (Sat) 00:44'] [REAL role=assistant content='assistant-content-1' ext_id=sess_A:t1 src_ids=['sess_A:t0', 'sess_A:t1'] time='2023/05/20 (Sat) 00:44']
  INVARIANTS OK: real_once=['assistant-content-1', 'user-content-0'] force_extract_seq=[True]
SHAPE 2_assistant_first  raw_roles=['assistant', 'user', 'assistant']  session_time='2023/05/20 (Sat) 00:44'
  canonical session_id=sess_A session_time='2023/05/20 (Sat) 00:44'
    Turn(id=sess_A:t0 speaker='assistant' normalized_role='assistant' content='assistant-content-0' turn_time=None meta_keys=[])
    Turn(id=sess_A:t1 speaker='user' normalized_role='user' content='user-content-1' turn_time=None meta_keys=[])
    Turn(id=sess_A:t2 speaker='assistant' normalized_role='assistant' content='assistant-content-2' turn_time=None meta_keys=[])
  TurnPairs (2):
    pair_index=0 kind=orphan first.role=assistant second.role=None session_id=sess_A
    pair_index=1 kind=real-real first.role=user second.role=assistant session_id=sess_A
  add_memory batches (2):
    batch#0 force_segment=False force_extract=False :: [PLACEHOLDER role=user content='' ext_id=sess_A:t0 src_ids=['sess_A:t0'] time='2023/05/20 (Sat) 00:44'] [REAL role=assistant content='assistant-content-0' ext_id=sess_A:t0 src_ids=['sess_A:t0'] time='2023/05/20 (Sat) 00:44']
    batch#1 force_segment=True force_extract=True :: [REAL role=user content='user-content-1' ext_id=sess_A:t1 src_ids=['sess_A:t1', 'sess_A:t2'] time='2023/05/20 (Sat) 00:44'] [REAL role=assistant content='assistant-content-2' ext_id=sess_A:t2 src_ids=['sess_A:t1', 'sess_A:t2'] time='2023/05/20 (Sat) 00:44']
  INVARIANTS OK: real_once=['assistant-content-0', 'assistant-content-2', 'user-content-1'] force_extract_seq=[False, True]
SHAPE 3_user_user  raw_roles=['user', 'user']  session_time='2023/05/20 (Sat) 00:44'
  canonical session_id=sess_A session_time='2023/05/20 (Sat) 00:44'
    Turn(id=sess_A:t0 speaker='user' normalized_role='user' content='user-content-0' turn_time=None meta_keys=[])
    Turn(id=sess_A:t1 speaker='user' normalized_role='user' content='user-content-1' turn_time=None meta_keys=[])
  TurnPairs (2):
    pair_index=0 kind=dangling first.role=user second.role=None session_id=sess_A
    pair_index=1 kind=dangling first.role=user second.role=None session_id=sess_A
  add_memory batches (2):
    batch#0 force_segment=False force_extract=False :: [REAL role=user content='user-content-0' ext_id=sess_A:t0 src_ids=['sess_A:t0'] time='2023/05/20 (Sat) 00:44'] [PLACEHOLDER role=assistant content='' ext_id=sess_A:t0 src_ids=['sess_A:t0'] time='2023/05/20 (Sat) 00:44']
    batch#1 force_segment=True force_extract=True :: [REAL role=user content='user-content-1' ext_id=sess_A:t1 src_ids=['sess_A:t1'] time='2023/05/20 (Sat) 00:44'] [PLACEHOLDER role=assistant content='' ext_id=sess_A:t1 src_ids=['sess_A:t1'] time='2023/05/20 (Sat) 00:44']
  INVARIANTS OK: real_once=['user-content-0', 'user-content-1'] force_extract_seq=[False, True]
SHAPE 4_assistant_assistant  raw_roles=['assistant', 'assistant']  session_time='2023/05/20 (Sat) 00:44'
  canonical session_id=sess_A session_time='2023/05/20 (Sat) 00:44'
    Turn(id=sess_A:t0 speaker='assistant' normalized_role='assistant' content='assistant-content-0' turn_time=None meta_keys=[])
    Turn(id=sess_A:t1 speaker='assistant' normalized_role='assistant' content='assistant-content-1' turn_time=None meta_keys=[])
  TurnPairs (2):
    pair_index=0 kind=orphan first.role=assistant second.role=None session_id=sess_A
    pair_index=1 kind=orphan first.role=assistant second.role=None session_id=sess_A
  add_memory batches (2):
    batch#0 force_segment=False force_extract=False :: [PLACEHOLDER role=user content='' ext_id=sess_A:t0 src_ids=['sess_A:t0'] time='2023/05/20 (Sat) 00:44'] [REAL role=assistant content='assistant-content-0' ext_id=sess_A:t0 src_ids=['sess_A:t0'] time='2023/05/20 (Sat) 00:44']
    batch#1 force_segment=True force_extract=True :: [PLACEHOLDER role=user content='' ext_id=sess_A:t1 src_ids=['sess_A:t1'] time='2023/05/20 (Sat) 00:44'] [REAL role=assistant content='assistant-content-1' ext_id=sess_A:t1 src_ids=['sess_A:t1'] time='2023/05/20 (Sat) 00:44']
  INVARIANTS OK: real_once=['assistant-content-0', 'assistant-content-1'] force_extract_seq=[False, True]
SHAPE 5_single_user  raw_roles=['user']  session_time='2023/05/20 (Sat) 00:44'
  canonical session_id=sess_A session_time='2023/05/20 (Sat) 00:44'
    Turn(id=sess_A:t0 speaker='user' normalized_role='user' content='user-content-0' turn_time=None meta_keys=[])
  TurnPairs (1):
    pair_index=0 kind=dangling first.role=user second.role=None session_id=sess_A
  add_memory batches (1):
    batch#0 force_segment=True force_extract=True :: [REAL role=user content='user-content-0' ext_id=sess_A:t0 src_ids=['sess_A:t0'] time='2023/05/20 (Sat) 00:44'] [PLACEHOLDER role=assistant content='' ext_id=sess_A:t0 src_ids=['sess_A:t0'] time='2023/05/20 (Sat) 00:44']
  INVARIANTS OK: real_once=['user-content-0'] force_extract_seq=[True]
SHAPE 6_single_assistant  raw_roles=['assistant']  session_time='2023/05/20 (Sat) 00:44'
  canonical session_id=sess_A session_time='2023/05/20 (Sat) 00:44'
    Turn(id=sess_A:t0 speaker='assistant' normalized_role='assistant' content='assistant-content-0' turn_time=None meta_keys=[])
  TurnPairs (1):
    pair_index=0 kind=orphan first.role=assistant second.role=None session_id=sess_A
  add_memory batches (1):
    batch#0 force_segment=True force_extract=True :: [PLACEHOLDER role=user content='' ext_id=sess_A:t0 src_ids=['sess_A:t0'] time='2023/05/20 (Sat) 00:44'] [REAL role=assistant content='assistant-content-0' ext_id=sess_A:t0 src_ids=['sess_A:t0'] time='2023/05/20 (Sat) 00:44']
  INVARIANTS OK: real_once=['assistant-content-0'] force_extract_seq=[True]
backend_config messages_use='hybrid' embedding_dims=384 update=offline

ALL PROBES PASSED
```

探针构造（可复现，全用 production 入口）：6 类 synthetic 单-session LME instance，每条 raw 打
`has_answer/answer/answer_session_ids` 私有反例；`LongMemEvalAdapter._conversation_from_instance()`
出 canonical → `build_turn_events()` → `GranularityAggregator("pair").aggregate()` →
`LightMem(config=smoke, backend_factory=lambda _cid: FakeBackend(), consume_granularity="pair",
benchmark_name="longmemeval")` 的 `ingest/end_session/end_conversation`；`FakeBackend.add_memory`
只记录 `(messages, kwargs)`，`text_embedder/embedding_retriever` 为 no-op fake，零 LLM/embedding。

## 4. time / query / readout 结论

1. **source time**：`_turn_timestamp`（`lightmem_adapter.py:1942-1980`）只 `turn.turn_time or
   session.session_time`。LME turn 无 turn_time（`_turn_from_event` 从 `original_turn_time`
   读，LME 为 None），故一律回落**本 session** raw time；无 question time / 相邻 session /
   首个有时 turn / wall clock 回填。探针 6 类 message `time_stamp` 全 = session_time。
2. **method-derived time**：两层 normalizer(per-pair, +500ms 跨 pair 重置) → force_extract 时
   `assign_sequence_numbers_with_timestamps` regroup 覆写，只在相同 raw session_time 组内
   base+i·500ms（§2.5/F5 已验收 vendored 机制，本轮不重跑）；placeholder 占派生 slot，不改
   source session_time。
3. **retrieve**：`_retrieve_with_payload`（:1600-1638）固定
   `embedding_retriever.search(query_vector=embed(question.text), limit=retrieve_limit,
   filters=None, return_full=True)`。question time 不进检索，只经
   `build_longmemeval_unified_answer_prompt` 填入 `Current Date:` 行（longmemeval_prompt.py:39-44），
   不成为 memory 可见性过滤。
4. **unified answer**：`_retrieve_native`（:1219-1250）返回非空 `formatted_memory`
   （= `answer_context`）+ `prompt_messages` + `items` + `evidence`；framework reader 的
   `build_longmemeval_unified_answer_prompt(question, retrieval_result)` 拿到 formatted memory +
   question.text + question.question_time，产出官方 non-CoT 模板的
   `PromptMessage[role=user]`（可直接调 answer LLM）；question_time 缺失记 `question_date_warning`。
5. **legacy native**：`config_track` 的 `TrackIdentity` 强校验 `build_override_applied` 恒为
   False（:452-453 抛错），native readout 必须 `native_scope="readout_only"`（:458-460）；本轮
   smoke 走 unified track，legacy LoCoMo/LME native bundle 仅作 readout-only 兼容，不建议本轮
   付费双跑。

## 5. config / lifecycle 对表（TOML → 强类型 config → factory，逐项 load 核对，非抄旧文档）

`load_typed_profile('configs/methods/lightmem.toml', 'smoke', LightMemConfig)` 实测：

| 字段 | smoke 值 | 备注 |
|---|---|---|
| `llm_model` | `gpt-4o-mini` | memory manager + reader |
| embedding | `models/all-MiniLM-L6-v2`，`embedding_dimensions=384`，`embedding_device=cpu` | Qdrant on-disk，distance=cosine（§frozen 已验收 MiniLM/384/cosine） |
| `retrieve_limit` | 60 | 进 `search(limit=...)` |
| `extract_threshold` | 0.5 | repo 默认（归一化后） |
| `pre_compress` / `compression_rate` | True / 0.7 | LLMLingua-2 official-mini |
| `stm_threshold` / `topic_segment` / `text_summary` | 512 / True / True | 512 为 vendored 硬编码强绑定 |
| `offline_update_score_threshold` | 0.8 | 仅 consolidated 轨用 |
| `messages_use` | `hybrid` | backend_config 透传实测 `messages_use='hybrid'`（dataclass 默认 `user_only`，TOML 显式覆盖） |
| `lifecycle_profile` | `online_soft` | direct insert，无全库 consolidation |
| `missing_timestamp_policy` | `preserve_none` | 仅与 online_soft 合法组合 |
| `api_timeout_seconds` / `api_max_retries` | 60.0 / 8 | |
| `max_workers` | 1（smoke）/ 10（official_full） | runner 建议并发 |
| adapter / protocol / source identity | `conversation-qa-v6` / v3 pair / sha256 `74be165…`（7 文件） | 见 §1 |

**online_soft 主 profile 不触发全库 consolidation**：`_should_run_locomo_offline_consolidation()`
（:981-991）恒为 False（仅 `locomo_offline_consolidated` 返回 True）；`construct_update_queue_
all_entries` / `offline_update_all_entries` 的唯一入口 `_run_locomo_offline_update`（:1581-1596）
在 legacy `add()`（:812）与 v3 `end_conversation()`（:977）两处都被该门挡住。`end_conversation`
只对最后一批 `force_segment/force_extract=True` 做 direct insert（探针 force_extract 序列末位
才为 True），**不是全库 offline consolidation**。fake backend 未实现 consolidation 方法且探针零
调用，佐证未触发。

## 6. evaluator 资格矩阵（current registry，`supported_benchmarks ∋ "longmemeval"`）

| evaluator（cli_name） | metric | requires_api | 类别 | LightMem×LME 资格 |
|---|---|---|---|---|
| `longmemeval-judge` | `longmemeval_judge_accuracy` | **True** | 付费官方 parity judge | 需预算，本轮不跑 |
| `f1` | token-F1 | False | artifact-only answer | 可评（消费同一条 prediction） |
| `normalized-em` | normalized EM | False | artifact-only answer | 可评 |
| `substring-em` | directional substring EM | False | artifact-only answer | 可评 |
| `longmemeval-recall` | `longmemeval_recall` | False | artifact-only retrieval | **诚实 N/A** |
| `longmemeval-retrieval-rank` | `longmemeval_retrieval_rank` | False | artifact-only retrieval | **诚实 N/A**（+ stable_ranking pending） |

当前 LongMemEval unified answer 设置是 `temperature=0.0`、`max_tokens=500`、`top_p=None`
（`config/settings.py:260-271`）；32-token 是 LoCoMo 的配置，不能挪到本格。上表三个
artifact-only answer metric 都消费同一条已落盘 prediction，不各自重新生成答案。

**N/A 被正确消费、不产伪分**（源码核证）：LightMem `_build_retrieval_evidence`
（:1319-1328）对 longmemeval 恒发 `semantic=n_a / pair_source_id_not_turn_exact`、
`granularity=none`、`stable_ranking=pending`。recall/rank evaluator 对**有 canonical turn target**
的题走 `decide_retrieval_eligibility`（retrieval_evidence.py:224-230：semantic 非 valid 直接原样
传播），得 `decision.status="n_a"` → 写 `score=None`、`status="n/a"`、`reason_code=
pair_source_id_not_turn_exact` 的逐题 record（longmemeval_recall.py:144-161、
longmemeval_retrieval_rank.py:140-152），**不报错、不 0 分、不回落 run 级**；`_abs` 与官方
no-target 另按 `benchmark_policy` 剔除，与 provider evidence 分开计数；summary
`summary_status(scored=0, pending=0)="n/a"`。rank 额外的 top_k=10 vs 官方 k30/50 深度缺口与
stable-ranking pending 仍是既有未修项，不因本轮改动。

> 注：`_retrieve_native` metadata 里 `provenance_granularity` 可能因 items 非空标为
> `"turn"`（:1243），但**evaluator 只消费逐题 `retrieval_evidence`（M1 起旧 run 级 manifest
> 字段不参与资格判定），不消费该 metadata**，故不影响 N/A 结论。

## 7. 现存测试覆盖与临时 probe 输出

- **现存测试**已覆盖 v3 `TurnPair → ingest → pending → flush` 与 placeholder/preserve-none/
  identity 反例（`tests/test_lightmem_adapter.py`：native ingest 路径、preserve_none 双路径、
  require fail-fast、benchmark identity 反例；`tests/test_longmemeval_*`：canonical 转换、prompt、
  registered prediction、recall/rank）。§9 定向测试全绿。
- **临时 probe**（scratchpad，未提交，对 Codex 架构师不可见）`lme_preflight_probe.py` 补证
  六类 raw shape 的 `TurnPair → ingest → pending batch → final flush` 完整链路（现存单测未逐类
  枚举六 shape 的 batch 边界与 src_ids 不变量）：**全量逐字 stdout 见 §3**（`ALL PROBES PASSED`，
  force_extract 仅末批 True，私有 token 零泄漏，backend_config `messages_use='hybrid'`、
  `embedding_dims=384`）。架构师复验无需 scratchpad——§3 已给探针构造 + 完整输出，可自写等价探针。

## 8. 总判词

```text
READY_FOR_B11_SMOKE
```

current main（`44095e2`，adapter `conversation-qa-v6`，vendored sha256 `74be165…` 未漂移）的
canonical role → TurnPair → hybrid add_memory → retrieve(`filters=None`) → unified readout →
metric eligibility 全链与 §2 已验收八事实一致，六类输入逐层实证无丢失/重复/跨 session 配对/
role 猜测，私有边界零泄漏，online_soft 不暗跑全库 consolidation，retrieval evaluator 对
LightMem 诚实 N/A。**本判词仅表示 registered round-cropped pipeline smoke 已具备执行条件**；
它不表示 full/effect run、成本校准或效果结论已完成。六类异常 shape 已经 production path +
fake backend 离线实证，无需为了重复验证这些 shape 而额外选择真实异常 qid 做付费 smoke。
无代码修复卡输入。

## 9. B11 smoke 边界与公开 shape 扫描（零 gold 选择，命令由架构师回卡后写）

- variant：**S**（`longmemeval_s_cleaned.json`，500 instance）。
- **smoke 与 full 分开**：正式效果/full run 必须保留每个 instance 的完整 history；B11 smoke
  只验证 ingest → retrieve → answer → artifact/evaluate 接线，允许按注册 policy 裁剪，且不作
  效果声明。`_build_longmemeval_smoke_dataset()` 按完整双-turn round 截取 history；
  `LONGMEMEVAL_SMOKE_POLICY` 默认 1 conversation × 1 round × 1 question
  （`benchmark_adapters/registry.py:94-162,259-274`）。因此“单题无法裁小”与“最小 smoke 必须
  约 400 turn/200 pair”均不成立。
- **本 note 不做成本估算**：下表的 pair/add_memory 数只描述完整 instance 的公开输入形状，
  不能换算 extraction LLM/API 调用数。实际 extraction 受 segment、short-memory buffer 与末批
  `force_extract` 等运行时门控制。未来 full 成本只能从一条**完整实验单元**的真实
  efficiency/API-call/token/wall-time 观测出发，再按用户批准规模外推；不能从 pair 数推算。
- 当前 CLI/prepare 是 first-N conversation + round crop，不能直接指定任意 question id。
  下列 qid 仅是公开 shape/规模扫描参考，**不是当前可直接执行的 smoke 候选**；本批不新增
  selector，也不要求为 smoke 新增 selector。

下表只按公开 role/blank shape 与 turn 数整理，**未看 answer/evidence**（pair 数为非-blank
role 序列复算的形状统计）：

| 角色 | 公开 question_id | #session | retained turn | 预计 add pair | 公开 shape |
|---|---|---:|---:|---:|---|
| 普通 user→assistant | `6613b389` | 41 | 452 | ~226 | 全 normal-user-first，偶数 |
| 公开结构异常 | `852ce960` | 39 | 396 | ~199 | 含 assistant-first + pure-assistant + 2 odd session |

`6613b389` 与 `852ce960` 只能作为 full/formal 规划时的公开 shape 参考；后者确实同时包含
assistant-first、pure-assistant 与奇数 turn，但六类形状已由 §3 离线探针覆盖，不能据此要求
一次额外的真实异常 qid 付费验证。B11 的实际题数、round 裁剪、worker 与 `run_id` 由架构师
按注册 smoke policy 和用户预算另行给出；本 note 不写命令、不展示 gold。

公开 shape 扫描逐字 stdout（`uv run python lme_candidate_scan.py`；`retained`=非 blank turn，
`pairs`=按非 blank role 序列复刻 `_aggregate_pairs` 状态机的估计值；`_abs` 已剔除，全程只读
公开 role/blank，未读 answer/evidence）：

```text
total_instances=500  clean=12  anomalous=458

== cheapest CLEAN (normal user->assistant only) ==
{'qid': '6613b389', 'abs': False, 'n_sessions': 41, 'retained': 452, 'pairs': 226, 'shapes': ['normal-user-first'], 'odd_sessions': 0, 'anomaly': False}
{'qid': '6e984302', 'abs': False, 'n_sessions': 43, 'retained': 460, 'pairs': 230, 'shapes': ['normal-user-first'], 'odd_sessions': 0, 'anomaly': False}
{'qid': '54026fce', 'abs': False, 'n_sessions': 49, 'retained': 472, 'pairs': 236, 'shapes': ['normal-user-first'], 'odd_sessions': 0, 'anomaly': False}
{'qid': 'd596882b', 'abs': False, 'n_sessions': 44, 'retained': 474, 'pairs': 237, 'shapes': ['normal-user-first'], 'odd_sessions': 0, 'anomaly': False}
{'qid': '9ee3ecd6', 'abs': False, 'n_sessions': 50, 'retained': 476, 'pairs': 238, 'shapes': ['normal-user-first'], 'odd_sessions': 0, 'anomaly': False}

== cheapest ANOMALOUS (assistant-first / consecutive / pure-assistant) ==
{'qid': '852ce960', 'abs': False, 'n_sessions': 39, 'retained': 396, 'pairs': 199, 'shapes': ['assistant-first', 'normal-user-first', 'pure-assistant'], 'odd_sessions': 2, 'anomaly': True}
{'qid': 'ba358f49', 'abs': False, 'n_sessions': 41, 'retained': 409, 'pairs': 205, 'shapes': ['assistant-first', 'normal-user-first'], 'odd_sessions': 1, 'anomaly': True}
{'qid': '6a1eabeb', 'abs': False, 'n_sessions': 40, 'retained': 413, 'pairs': 208, 'shapes': ['assistant-first', 'normal-user-first'], 'odd_sessions': 3, 'anomaly': True}
{'qid': '5a7937c8', 'abs': False, 'n_sessions': 42, 'retained': 419, 'pairs': 210, 'shapes': ['assistant-first', 'normal-user-first'], 'odd_sessions': 1, 'anomaly': True}
{'qid': '5831f84d', 'abs': False, 'n_sessions': 40, 'retained': 422, 'pairs': 213, 'shapes': ['assistant-first', 'normal-user-first', 'pure-assistant'], 'odd_sessions': 4, 'anomaly': True}
```

（总数 500 中有 30 个 `_abs` instance 被该候选分类排除；其余 470 个 non-abstention =
`clean=12 + anomalous=458`。`clean` 指全 session 严格 normal-user-first 且偶数的 instance；
其余 458 题含至少一个公开异形 session，佐证 §2.2 异形是 benchmark-native 常态。扫描只按
公开 shape + turn 数，未用 private answer/evidence 挑“易命中”题。）
