# M5 Mem0 frozen 前三项取证审计

> 取证日期：2026-07-14。纯只读审计；未调用真实 API，未修改生产代码、测试或
> `third_party/`。

## 1. B8+ 外部调用韧性清单

### 1.1 网络调用点

| 调用点 | 用途与实际参数链 | timeout / retry | 最终失败后的 state 语义 | 判定 |
|---|---|---|---|---|
| Mem0 内部 OpenAI-compatible Chat Completions：`third_party/methods/mem0-main/mem0/llms/openai.py:84-140` | extraction/update。profile 的 `api_timeout_seconds=60.0`、`api_max_retries=8` 在 `configs/methods/mem0.toml:10-21,23-34` 进入 `Mem0Config`（`src/memory_benchmark/methods/mem0_adapter.py:84-115`）；backend 先按 `:416-440` 构造，再由 adapter 对实际 `memory.llm.client` 执行 `with_options(timeout=60,max_retries=8)`（`:1175-1204`）。所以不是只停留在配置层。 | **60 秒 / OpenAI SDK 8 次重试**，实际注入链见左列。 | 单个 conversation 的多次 `Memory.add` 不是事务；最终失败可能留下 vectors、recent messages 或 sidecar 的部分状态。runner 持久化 `failed_ingest, ingested=false`（`runners/prediction.py:1958-1979`），显式 retry 前先调用 clean hook（`:737-794`）。Mem0 hook 删除该 run_id 的 vectors、同 scope messages、sidecar 与 namespace（`mem0_adapter.py:1735-1751`；挂接 `methods/registry.py:582-602,780-801`）。测试 `test_mem0_clean_removes_vectors_messages_and_failed_attempt_context` 与 `test_mem0_registry_clean_hook_reconstructs_v3_isolation_key` 锚定清理语义（`tests/test_mem0_adapter.py:997-1066`）。 | timeout/retry 齐；**失败后不是立即回滚**，而是隔离为 failed_ingest，retry 前清理后再写。 |
| 框架主协议 answer reader Chat Completions：`src/memory_benchmark/readers/answer.py:262-279` | v3 prediction 使用 `FrameworkAnswerReader`，由 `cli/run_prediction.py:580-603` 构造；native bundle 或 benchmark profile 提供 `AnswerLLMSettings`（`:420-449`）。client 构造把 settings 的 timeout/retry 传给 SDK（`readers/answer.py:198-228`、`config/settings.py:147-200`）。 | **60 秒 / OpenAI SDK 8 次重试**；默认常量在 `config/settings.py:15-20,166-167`，native bundle 未覆盖这两个字段。 | answer 发生在 ingest/retrieve 之后，不写 method state。失败记录为 `failed_answer`，恢复只补未完成 answer、不重复 ingest；测试 `test_failed_answer_resume_does_not_reingest`（`tests/test_prediction_runner.py:2223-2285`）。 | 齐全。 |
| Mem0 adapter 兼容 `get_answer()` reader：`src/memory_benchmark/methods/mem0_adapter.py:1080-1091` | legacy/直接 adapter 路径。`OpenAI(**settings.to_client_kwargs())` 在 `mem0_adapter.py:351-355`，`OpenAISettings.to_client_kwargs` 实际传 `timeout` 与 `max_retries`（`config/settings.py:109-126`）。 | **60 秒 / OpenAI SDK 8 次重试**，默认值 `config/settings.py:15-20,103-107`。 | 只读检索后答题；失败不写 Mem0 method state。 | 齐全；v3 主线使用上一行 framework reader。 |
| SentenceTransformer 模型缓存填充：`third_party/methods/mem0-main/mem0/embeddings/huggingface.py:15-27` | 当前 profile 明确 `embedding_provider="huggingface"`、模型 `sentence-transformers/all-MiniLM-L6-v2`（`configs/methods/mem0.toml:10-14,23-27`）；adapter 不传 `huggingface_base_url`，因此运行 `SentenceTransformer(model_id)`，编码本身本地执行（vendored `huggingface.py:29-44`）。若本地 Hugging Face cache 未命中，构造器可能联网下载模型；配置不是 `local_files_only=True`，也未指向项目 `models/`。 | **项目未显式配置下载 timeout/retry**；底层 Hugging Face Hub 自身策略不构成本项目锁定口径。 | backend 构造发生在 conversation ingest 前（`mem0_adapter.py:341-350`）；dense 模型下载/加载失败会阻止 backend 初始化，不产生半写 conversation。 | **B8+ 缺口：首次运行仍可能联网，且无项目级 timeout/retry/offline fail-fast。**缓存命中后的 embedding 是本地零网络。 |
| FastEmbed `Qdrant/bm25` 缓存填充：`third_party/methods/mem0-main/mem0/vector_stores/qdrant.py:88-107` | 本地 Qdrant collection 启用 BM25；首次 add/search 懒构造 `SparseTextEmbedding(model_name="Qdrant/bm25")`，缓存未命中时可能联网。插入调用链为 vendored `qdrant.py:188-205`，查询为 `:415-443`。 | **项目未显式配置下载 timeout/retry**。构造异常被 `except Exception` 捕获并将 encoder 置为 False（`:95-101`）。 | dense vector 继续写入；BM25 被永久降级为不可用，查询返回 None/走其余检索路径（`:103-107,425-443`）。不产生因下载失败导致的半写异常，但只有 warning/debug，run identity 不记录这次语义降级。 | **B8+ 缺口：潜在网络 + 未锁 timeout/retry；失败语义是继续运行并静默失去 sparse 召回。** |

### 1.2 明确不联网的状态组件

| 组件 | 一手锚 | 结论 |
|---|---|---|
| Qdrant vector store | adapter 只给 `path`，不传 host/url（`mem0_adapter.py:431-437`）；vendored Qdrant 在无 host/url 时构造 `QdrantClient(path=...)` 并标记 local（`third_party/methods/mem0-main/mem0/vector_stores/qdrant.py:57-76`） | 数据库操作本地；**不含上一表 BM25 模型缓存填充**。 |
| Mem0 history/recent messages | adapter 设置本地 `history.db`（`mem0_adapter.py:439`）；`SQLiteManager` 用 `sqlite3.connect(path)`（`third_party/methods/mem0-main/mem0/memory/storage.py:11-18`） | 本地零网络。 |
| Mem0 telemetry | backend 构造前设置 `MEM0_TELEMETRY=False`（`mem0_adapter.py:1124-1128`） | 本框架运行不发送 Mem0 telemetry。 |

**B8+ 硬答案：**真正业务 API 两点（extraction/update LLM、answer LLM）均有
60 秒 timeout + 8 次 SDK retry；ingest 失败不是事务回滚，而是 namespace 隔离并在
显式 retry 前完整清理。两个模型首次缓存填充点（SentenceTransformer、FastEmbed
BM25）没有项目级网络韧性配置，其中 BM25 失败还会继续运行并降级检索语义，均应列为
frozen 前缺口。

## 2. B7 native 注入 token 审计

### 2.1 共同计量链

native v3 检索先对同一 `memories` 同时构造：

1. 计量串 `injected_memory_text = _memory_context_text(memories)`；
2. 实际 `prompt_messages = _reader_messages(question, memories)`；
3. 对计量串用 reader tokenizer 计数并写
   `injected_memory_context_tokens`。

三步在 `src/memory_benchmark/methods/mem0_adapter.py:1013-1024`。计量串逐条输出
`- {ISO timestamp}: {memory}`，无时间则 `- {memory}`（`:1898-1911`）。政策要求
native builder 有截断、改写或重排时，统计跟随实际嵌入段（
`docs/reference/efficiency-injected-tokens-policy.md:18-27`）。

### 2.2 三格对照

| native 格 | builder 接线 | 实际嵌入的 memory 段 | 与计量串关系 | 判定 |
|---|---|---|---|---|
| LoCoMo | adapter `mem0_adapter.py:1829-1853`；官方 builder `third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/prompts.py:143-195` | 同一结果先取前 200、按 `created_at` 排序，加固定说明；每条为 `({human date}) {memory}`，无时间为 `(unknown date) {memory}`（官方 `:167-182`）。当前 method `top_k=20`（`configs/methods/mem0.toml:16,29`），所以 200 上限不再丢条目。 | **memory 内容集合相同**；顺序、日期格式、unknown-date 文本和说明不同。计量串统计 ISO 前缀，不统计实际 human-date/unknown-date 排版。 | **不满足 token 级载荷≡嵌入。**无漏 memory 内容，但统计的是另一种序列化。 |
| LongMemEval | adapter `mem0_adapter.py:1855-1877`；官方 builder `memory-benchmarks/benchmarks/longmemeval/prompts.py:210-258` | 同一结果按连续日期分组；每个日期只写一次 `--- {human date} ---`，每条 memory 写 `- {memory}`（官方 `:228-245`）。 | **内容集合相同**；计量串为每条重复 ISO timestamp，实际 prompt 对同日期分组且用 human date。 | **不满足 token 级载荷≡嵌入；同日多条时通常会多计重复 timestamp。** |
| BEAM | adapter `mem0_adapter.py:1879-1896`；官方 builder `memory-benchmarks/benchmarks/beam/prompts.py:104-158` | 同一结果按时间排序并编号；有时间为 `N. [YYYY-MM-DD] {memory}`，无时间为 `N. {memory}`（官方 `:117-137`）。 | **内容集合相同**；计量串使用 bullet、完整 timestamp 和冒号，实际使用 rank 与截断日期。 | **不满足 token 级载荷≡嵌入。**无漏 memory 内容，但日期与编号 token 失配。 |

**B7 硬答案：三格均未多计 native 指令模板，也未漏检索 memory 正文；但三格都不满足
政策要求的“实际记忆段 token 等价”，因为统一 `_memory_context_text` 与官方 builder
各自的时间/分组/编号序列化不同。**本卡只取证，不修。

## 3. native run 的评测路由

### 3.1 路由锚表

| 场景 | 实际调用链 | 现状硬答案 |
|---|---|---|
| manifest 识别 native | `execute_evaluate` 读取 manifest；仅当 `method.config_track == "native"` 才按 method/benchmark 调 `resolve_config_track`（`src/memory_benchmark/cli/commands.py:173-191`）。Mem0 三格 bundle 注册在 `src/memory_benchmark/methods/config_track.py:55-83`。 | native manifest 会解析到 M4 bundle，不是完全忽略 config_track。 |
| `mem0 × locomo × native` + `locomo-judge` | evaluator 先从 `configs/evaluators/llm_judge.toml` 加载用户选择的 compact/detailed profile并创建默认 evaluator（`commands.py:193-212`）；随后唯一的 native 特化分支在 metric 名为 `locomo-judge` 时，用 bundle 的 `prompt_template`、`skipped_categories`、`profile_name` 重建 `LoCoMoJudgeEvaluator`（`:213-222`）。模型仍取 TOML profile 的 `profile.model`（`:201-218`），该文件两档均为 `gpt-4o-mini`（`configs/evaluators/llm_judge.toml:1-8`）。 | **使用 `MEM0_NATIVE_JUDGE_PROFILES["locomo"]` 的 prompt/category skip/profile 名；模型使用框架 evaluator profile 的 `gpt-4o-mini`。** |
| `mem0 × longmemeval/beam × native` 的付费 judge | native bundle 虽已解析，但 `commands.py:213` 的覆盖条件只认 `metric_name == "locomo-judge"`；其他 API evaluator 保留 `create_evaluator(...)` 的默认实例（`:200-212`）。 | **M4 的 LongMemEval/BEAM native judge profile 当前没有进入 evaluate 运行时；仍用各 benchmark 注册表默认 judge。** |
| 免费 evaluator（如 `locomo-f1`、`locomo-recall`、LME recall/rank） | registry 明确 `requires_api=False`（`src/memory_benchmark/evaluators/registry.py:312-320,342-360,392-400`）；命令直接 `create_evaluator`，不加载 profile、不读取 native bundle judge（`commands.py:223-229`）。artifact runner 只按 manifest 校验 benchmark 后读取标准 public/prediction/private artifacts（`src/memory_benchmark/runners/evaluation.py:56-108`）。 | **与 config_track 无关，native artifacts 照常可评；输入答案/检索结果当然仍来自该 native run。** |

**评测路由硬答案：**以题示 LoCoMo native run 为例，`locomo-judge` 的 prompt 来自
Mem0 native bundle，模型仍是框架 `gpt-4o-mini`；免费指标不分轨。LongMemEval 与
BEAM 的 native judge profile 目前只注册为资产，evaluate 分支尚未消费它们。

## 4. 施工报告

- worktree：`/Users/wz/Desktop/mb-actor-m5mem0`
- branch：`actor/m5-mem0-audit`
- 变更范围：仅本 note。
- 验证脚本：无；纯代码调用链取证，按卡不运行 pytest/compileall。
- 停工点：无，三节均在 30 分钟内锚定。
