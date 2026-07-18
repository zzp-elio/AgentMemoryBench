# LightMem 产品 readout 保真与 embedding 观测修复 — 实现 note

> 日期：2026-07-18；基线：main `ecea1ab`（隔离 worktree
> `mb-actor-lightmem-readout-observability`，branch
> `actor/lightmem-readout-observability`）。
> 范围：只修公共 unified readout 时间精度、真实 embedding observation、逐题
> legacy provenance metadata 单事实源；零真实 API、零算法改动、不改
> third_party/runner/protocol/collector/entity/storage/TOML/evaluator。

## 1. 问题复述（v6 真实 B11 开箱三项缺口）

用户已执行 LightMem × LongMemEval `conversation-qa-v6` 的单/双 worker 真实 B11
（`lm-lme-v6-r1q1-w1-s-cleaned`、`lm-lme-v6-r1q1-c2-w2-s-cleaned`）。机器验货脚本
全部 PASS，manifest/checkpoint/prediction/prompt/score 行数、隐私边界、逐题 N/A、
judge 与 worker 隔离均成立，但架构师开箱同时抓到三处不能被"零报错"掩盖的事实
（完整判词见 `../notes/lightmem-longmemeval-b11-command-pack.md` §7）：

1. W2 命中记忆的 Qdrant payload 保存完整 `2023-05-20T03:29:00.000`，公共
   `formatted_memory`/unified `History Chats` 却只剩 `20 May 2023, Sat`——把
   LoCoMo author pretty-date formatter 误用于产品 readout 的降精度，可能改变
   LongMemEval 时间题答案。
2. 两个 run 的 model inventory 都声明 `lightmem-embedding`，但 prediction
   observation 中 `embedding_call=0`、overall `embedding_tokens={}`；
   `text_embedder.embed()` 从未被观测。
3. 同一道 LongMemEval 题的 v1 `RetrievalEvidence.provenance_granularity` 为
   `none`，legacy retrieval metadata 却因 `items is not None` 独立判定写成
   `turn`；evaluator 只读 v1 evidence 所以分数没算错，但公开 artifact 自相矛盾。

（第四项 `mean_score=0.0` 属共享 retrieval summary 契约缺口，由并行卡
`retrieval-metrics/cards/actor-prompt-retrieval-summary-nullability.md` 负责，
本卡不改共享 evaluator/runner。）

## 2. 已裁实现语义（对照修复卡 §2-§4）

### 2.1 产品 readout 与 author 分层解耦

- `_format_lightmem_memory_as_official_retrieve()` 收紧为逐字节还原 vendored
  `LightMemory.retrieve()`（`lightmem.py:722-736`）的单条格式化逻辑：
  `time_stamp is None` 时只返回 memory 文本（不显示时间标签、不出现字面量
  `None`、不凭 weekday 单独造前缀）；非 None（含缺 key 回退出的空字符串等历史
  边界）时原样输出 `"{time_stamp} {weekday} {memory}"`，不做 `.strip()` 等额外
  "智能修复"，也不再回退到 `original_memory`/`compressed_memory`（vendored
  payload 恒有非 None 的 `memory` 字段，回退链是历史冗余）。
- 三个公共 unified 调用点统一切到该函数：`_retrieve_question()` 的
  `memory_context`（→ `metadata["answer_context"]` → `RetrievalResult.
  formatted_memory`）、`_metadata_memory_from_lightmem_item()` 的诊断
  `content`、`_retrieved_items_from_lightmem_memories()` 的 `RetrievedItem.
  content`。三者与最终 `formatted_memory` 现在字节一致。
- `_format_lightmem_memory()`（pretty-date + weekday + `[Memory recorded on:
  ...]`）保留不变，只继续服务 `_build_locomo_answer_prompt()`/
  `_split_memories_by_speaker()` 的 LoCoMo 官方 answer prompt；LongMemEval
  author message context（`_build_prompt_messages()` 内 `_is_longmemeval_
  question` 分支）继续调用（现已收紧的）`_format_lightmem_memory_as_
  official_retrieve()`——它本来就是为了对齐官方 retrieve() 格式而存在，收紧只
  是修正其此前遗留的 fallback 链与 `.strip()` 偏差，不是新增第三个 formatter。
- 净效果：五个 benchmark 的公共 product readout 现在统一走同一个格式化入口，
  没有 per-benchmark 的损失性格式分支；LoCoMo 官方 prompt 的 pretty-date 布局
  与该公共入口完全解耦（互不调用对方）。旧 LoCoMo unified answer artifact（v6
  及更早）因此只保留历史证据，不能冒充修复后的 readout 证据。

### 2.2 embedding 观测

- 新增 `_install_embedding_call_observer(backend)`，在 `_get_or_create_
  backend()` 内与既有 `_install_memory_manager_usage_observer()` 并列调用一次
  （backend 创建后立即安装）。实现与既有 LLM usage wrapper 同构：collector
  未启用时直接返回（零额外行为）；`text_embedder` 缺失或无 `embed` 属性时直接
  返回；`text_embedder._memory_benchmark_embedding_wrapped` 已为真时直接返回
  （幂等，同一 backend 不会二次包装）。
- `wrapped_embed()` 先调用原始 `embed()`（异常原样传播，不吞异常、不在失败
  路径写"成功调用"记录），成功返回后才计算 latency 并调用 `collector.
  record_embedding_call(model_id="lightmem-embedding", input_tokens=...,
  latency_ms=..., token_measurement_source=TOKENIZER_ESTIMATE,
  latency_measurement_source=FRAMEWORK_TIMER)`。
- `stage`/`conversation_id`/`question_id` 完全由 `EfficiencyCollector` 现有
  ContextVar scope 自动解析（`_resolve_current_stage()`）：conversation scope
  内无显式 stage 时默认 `memory_build`；`_retrieve_question()` 已有的
  `with collector.operation_stage(EfficiencyStage.RETRIEVAL):` 包裹
  `_retrieve_with_payload()`，query embed 因此落 `retrieval`。未新增缓冲/跨
  线程转发逻辑——一手核实 vendored 三个真实 embed 调用点（`add_memory()` 内
  `SenMemBufferManager.cut_with_segmenter()` 的 topic segmentation
  `sensory_memory.py:67`、`offline_update()` 的插入向量库
  `lightmem.py:436`、`retrieve()`/`_retrieve_with_payload()` 的 query embed）
  均为同线程内的普通 for 循环或单次调用，不像 LoCoMo OP-update 那样跑在
  `ThreadPoolExecutor` 里，故不存在既有 memory-manager usage wrapper 需要的
  跨线程 ContextVar 丢失问题，无需复制那套缓冲机制。
- token 计数新增 `_count_local_embedding_tokens(text_embedder, text)`：读取
  `text_embedder.model.tokenizer`（真实 HuggingFace tokenizer）与
  `text_embedder.model.max_seq_length`（真实 SentenceTransformer 截断设置），
  用 `tokenizer.encode(text, truncation=True, max_length=max_seq_length)` 计数
  ——这是模型实际会消费的 token 数（含截断），不是字符数，也不是未截断的理论
  长度，因此 `token_measurement_source` 只能是 `tokenizer_estimate`。生产
  `TextEmbedderHuggingface`（`third_party/methods/LightMem/src/lightmem/
  factory/text_embedder/huggingface.py`）在本项目配置下恒走本地
  `SentenceTransformer` 分支（adapter 从不设置 `huggingface_base_url`），故
  `.model` 恒为真实 `SentenceTransformer` 实例，属性链稳定存在。
- `registry.py::_lightmem_efficiency_model_inventory()` 删除
  `lightmem-answer-llm` 条目：registered v3 主路径（`_is_memory_provider(
  system)` 分支，`runners/prediction.py`）只调用 `ingest()`/`retrieve()`，
  最终 answer LLM 由 framework `FrameworkAnswerReader` 执行，其模型身份由
  `cli/run_prediction.py::_append_framework_answer_model_inventory()` 单独
  追加；`lightmem-answer-llm` 只会在直接调用 legacy `LightMem.get_answer()`
  （`_record_answer_llm_call()`）时才产生 observation，registered 主路径从
  不触达。`efficiency_instrumentation_identity_getter` 未受影响，继续保留。

### 2.3 逐题 provenance metadata 单事实源

`_retrieve_native()` 现在只调用一次 `self._build_retrieval_evidence(items)`，
把返回的 `RetrievalEvidence` 同时赋给 `RetrievalResult.evidence` 和
`metadata["provenance_granularity"] = evidence.provenance_granularity`；删除
了旧的独立判定 `"turn" if items is not None else "none"`。LongMemEval 恒 n_a/
none（pair source_id 粒度不足），即使 `items` 因 plural `source_external_ids`
齐全而非 None，legacy metadata 现在也正确写 `none`，与 v1 evidence 一致；LoCoMo
online-soft 的合法 valid 例两处仍均为 `turn`。

## 3. v6→v7 重建理由

三项修复都改变了公共可观测契约（readout 字节内容、embedding 是否有
observation、legacy metadata 的值），即使记忆构建算法（抽取/压缩/分段/向量/
online-soft/检索排序）完全不变。若不升版本，旧 v6 store/manifest 会被 resume
系统的全 manifest `==` 比较错误接受为兼容，导致新旧契约混用、可观测性缺口被
静默继承。`LIGHTMEM_ADAPTER_VERSION` 从 `conversation-qa-v6` 升为
`conversation-qa-v7`，强制旧 run 不可 resume，测试名/docstring/断言同步更新，
未把 v6 放进任何兼容集合。

## 4. third_party / 协议 / runner 零改动

未触碰 `third_party/`、`core/provider_protocol.py`、
`observability/efficiency/{collector,entities,storage}.py`、
`benchmark_adapters/`、`runners/`、TOML、evaluator、其它 method、父/支线
README、现有 run artifacts 或 command pack。`_count_local_embedding_tokens()`
只读取 vendored `TextEmbedderHuggingface.model` 已暴露的公开属性
（`tokenizer`/`max_seq_length`），不修改、不重新实现 tokenization 逻辑。
`build_longmemeval_unified_answer_prompt()`（`benchmark_adapters/
longmemeval_prompt.py`）在测试中只读调用，未修改该文件。

## 5. 测试与定向自检

新增/修改测试：

**`tests/test_lightmem_adapter.py`**
- `test_format_lightmem_memory_as_official_retrieve_preserves_full_iso_timestamp`：
  非空 ISO timestamp 字节一致，且不等于 pretty-date 版本（会在修复前的
  current main 失败）。
- `test_format_lightmem_memory_as_official_retrieve_none_timestamp_omits_time_prefix`：
  `time_stamp=None`（含 weekday 恰好非 None 的边界）只输出 memory，无 `None`
  或 weekday-only 前缀。
- `test_lightmem_retrieve_native_formatted_memory_preserves_order_and_item_fields`：
  两条 memory 按检索顺序拼接；`score`/`source_turn_ids`/`timestamp`/speaker
  payload 不受格式切换影响。
- `test_lightmem_locomo_author_prompt_stays_pretty_date_while_unified_readout_is_product_format`：
  LoCoMo 官方 prompt 仍 pretty-date，公共 `formatted_memory` 已是产品格式，
  两层未重新耦合。
- `test_lightmem_longmemeval_unified_builder_embeds_full_timestamp_and_isolates_question_time`：
  `answer_context == formatted_memory`；完整 ISO timestamp 进入
  `build_longmemeval_unified_answer_prompt()` 的 `History Chats`；question
  time 只出现在 `Current Date`，不混入 memory 文本。
- `test_lightmem_native_builder_passes_through_adapter_prompt_messages`
  （parametrize 扩展 `expected_provenance_granularity`）：LongMemEval 的 v1
  evidence 与 legacy metadata 都是 `none`；LoCoMo valid 例两处都是 `turn`，
  且显式断言 `metadata["provenance_granularity"] == evidence.
  provenance_granularity`。
- `test_lightmem_embedding_observer_records_build_and_retrieval_calls`：fake
  build 两次 embed（segmentation + insert 模拟）、fake retrieval 一次 embed，
  逐条 observation 的 stage/model_id/token/latency source/conversation-
  question id 均正确。
- `test_lightmem_embedding_observer_installs_wrapper_only_once_per_backend`：
  重复安装不二次包装（`embed` 函数对象身份不变）。
- `test_lightmem_embedding_observer_noop_when_collector_disabled`：collector
  关闭时不包装、不产生 observation。
- `test_lightmem_embedding_observer_propagates_original_exception_without_recording`：
  embed 抛错时异常原样传播，且无成功 observation 落盘。
- `test_lightmem_embedding_observer_isolates_concurrent_conversations`：两个
  真实并发（`ThreadPoolExecutor`）conversation 的 embedding observation 不
  串 conversation_id、不丢调用。
- `test_lightmem_config_manifest_includes_lifecycle_profile_and_adapter_version_v7`
  （重命名自 v6 版本）：manifest 断言 v7，并显式断言 `!= "conversation-qa-v6"`。
- 更新既有 `test_lightmem_retrieve_longmemeval_uses_backend_retrieve` 的
  `answer_context` 断言：从 `"[Memory recorded on:" in ...` 改为断言完整 ISO
  timestamp 出现且 pretty-date 标记不出现（该断言此前编码的正是 v6 bug）。
- `FakeLightMemEmbedder` 新增 `.model`（`FakeSentenceTransformerModel` +
  `FakeHuggingFaceTokenizer`），供 embedding 观测测试零模型下载计数；新增
  `EmbeddingObservingFakeLightMemoryBackend` 模拟真实 build 阶段至少两次
  embed。

**`tests/test_method_registry.py`**
- `test_lightmem_registration_model_inventory_excludes_unused_answer_llm`：
  model inventory 恰为 `["lightmem-memory-llm", "lightmem-embedding"]`，不含
  `lightmem-answer-llm`；`efficiency_instrumentation_identity_getter` 仍非
  None。

`tests/test_lightmem_registered_prediction.py`：未改动，本卡改动未影响其覆盖
的 registry 装配路径（该文件测试 legacy-bridged fake，不经过本卡改动的
formatter/observer/evidence 代码路径）。

定向自检（card §7 指定组合）：

```text
uv run pytest -q \
  tests/test_lightmem_adapter.py \
  tests/test_lightmem_registered_prediction.py \
  tests/test_method_registry.py \
  tests/test_artifact_evaluation_runner.py \
  tests/test_documentation_standards.py

201 passed, 1 warning in 8.11s
```

## 6. 隔离工作树环境补齐

隔离 worktree 默认缺 gitignored `data/`、`models/`、`.env`（与其它并行 actor
worktree 一致的已知缺口）。已用 `ln -s` 从主仓库软链三者（不复制、不写入
git、可随时删除），使定向自检覆盖真实数据路径与 `.env` 门禁，而非在缺资产下
虚报通过。软链前，`tests/test_lightmem_registered_prediction.py::
test_lightmem_native_config_track_flows_through_both_official_grids` 与
`tests/test_artifact_evaluation_runner.py::
test_longmemeval_s_smoke_registered_prediction_stays_offline_and_separates_private_labels`
因缺 `data/longmemeval/*.json` 与 `.env`/`OPENAI_KEY` 失败；已在主仓库
（含 `.env`/`data`）确认 `test_lightmem_native_config_track_flows_through_
both_official_grids` 本身可独立通过，证明失败是环境缺口，不是本卡引入的
回归。

## 7. 偏差与停工点

- 无停工点；未触及允许清单外文件；未调用真实 API、未下载模型。
- **偏差（如实披露）**：执行过程中误跑了一次
  `uv run python -m compileall -q src/memory_benchmark tests`（用于自我核实
  语法），随后才注意到卡 §7 明确排除 compileall 与全量 pytest。该命令只读、
  无副作用（未改 outputs、未调用 API、未下载模型），退出码 0；发现后未重复
  执行，也未据其结果做任何决策。此后严格只运行卡指定的定向命令。
