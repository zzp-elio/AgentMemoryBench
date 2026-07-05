# Cognee 机制深读卡片

完成时间：2026-07-05 21:22 CST

## 1. 写入后内部发生什么

事实：

- Cognee 对外暴露两层入口：V1 `add/delete/cognify/search`，以及 V2 memory-oriented `remember/recall/improve/forget`。本轮审计以 MemoryData 实际使用的 V1 路径为准。证据：`third_party/methods/cognee/cognee/__init__.py:18-31`、`third_party/methods/cognee/cognee/__init__.py:52-68`。
- `add()` 只是第一步 raw ingestion：接受文本、文件路径、URL、二进制流或列表，把内容解析、抽取为文本，存入指定 dataset，并记录元数据与权限；文档明确下一步要调用 `cognify()`。证据：`third_party/methods/cognee/cognee/api/v1/add/add.py:25-49`、`third_party/methods/cognee/cognee/api/v1/add/add.py:50-85`、`third_party/methods/cognee/cognee/api/v1/add/add.py:118-134`。
- `add()` 本地路径会先 `setup()`，解析/创建授权 dataset，然后运行 `add_pipeline`，任务包括 `resolve_data_directories` 与 `ingest_data`；运行前会重置该 dataset 的 add/cognify pipeline 状态。证据：`third_party/methods/cognee/cognee/api/v1/add/add.py:209-227`、`third_party/methods/cognee/cognee/api/v1/add/add.py:251-271`。
- `ingest_data()` 会把输入统一成列表，查找或创建 dataset，保存原始内容到 storage，抽取/记录原始与文本文件 metadata、content_hash、loader、owner、tenant、node_set，并把 Data 关联到 dataset。证据：`third_party/methods/cognee/cognee/tasks/ingestion/ingest_data.py:27-35`、`third_party/methods/cognee/cognee/tasks/ingestion/ingest_data.py:57-80`、`third_party/methods/cognee/cognee/tasks/ingestion/ingest_data.py:93-158`、`third_party/methods/cognee/cognee/tasks/ingestion/ingest_data.py:170-249`。
- `cognify()` 才把已 ingest 的 dataset 转为知识图谱/向量结构：文档列出的 pipeline 是分类、chunk、实体抽取、关系识别、图构建、摘要。证据：`third_party/methods/cognee/cognee/api/v1/cognify/cognify.py:43-60`、`third_party/methods/cognee/cognee/api/v1/cognify/cognify.py:62-91`。
- 默认 `cognify` tasks 依次是 `classify_documents`、`extract_chunks_from_documents`、`extract_graph_and_summarize`、`add_data_points`、`extract_dlt_fk_edges`；其中 graph/summarize 阶段会对 chunks 并行执行 graph extraction 与 summarization。证据：`third_party/methods/cognee/cognee/api/v1/cognify/cognify.py:290-353`、`third_party/methods/cognee/cognee/tasks/graph/extract_graph_and_summarize.py:12-37`。
- `add_data_points()` 把 DataPoint 转成 nodes/edges、去重、补默认 edge properties，再写 graph engine 和 vector engine；非 hybrid engine 会分别写 graph nodes/edges 和 index data points / graph edges。证据：`third_party/methods/cognee/cognee/tasks/storage/add_data_points.py:30-46`、`third_party/methods/cognee/cognee/tasks/storage/add_data_points.py:64-92`、`third_party/methods/cognee/cognee/tasks/storage/add_data_points.py:129-165`。

推断/含义：

- Cognee 的写入完成边界不能只看 `add()` 成功。对 benchmark 来说，数据“可检索”至少要等对应 dataset 的 `cognify()` blocking 返回；如果使用 `run_in_background=True`，还要基于 pipeline run status 另行等待。

## 2. 原生 ingest 形态

事实：

- `add()` 原生签名包含 `data`、`dataset_name`、`user`、`node_set`、`vector_db_config`、`graph_db_config`、`dataset_id`、`preferred_loaders`、`incremental_loading`、`data_per_batch`、`importance_weight`、`run_in_background`、`llm_config`、`embedding_config`。证据：`third_party/methods/cognee/cognee/api/v1/add/add.py:25-49`。
- 原生输入单位不是 message schema，而是自由文本/文档/文件/URL/列表；dataset 与 user 是主要组织边界，`node_set` 可作为图组织和访问控制分组。证据：`third_party/methods/cognee/cognee/api/v1/add/add.py:62-78`、`third_party/methods/cognee/cognee/api/v1/add/add.py:86-106`。
- `cognify()` 的原生边界是 dataset：`datasets` 可为单个名称、多个名称、UUID 列表或 None；`chunk_size`、`chunker`、`graph_model`、`custom_prompt` 决定 chunk 与 graph extraction 行为。证据：`third_party/methods/cognee/cognee/api/v1/cognify/cognify.py:98-125`。
- MemoryData 配置为 Cognee 提供 OpenAI-compatible LLM/embedding endpoint、embedding model、chunk size，并设置 `cognee_skip_connection_test: true`。证据：`第三方框架参考/MemoryData/config/topological_cognee.yaml:1-10`、`第三方框架参考/MemoryData/config/topological_cognee.yaml:13-33`。
- MemoryData 初始化时把 Cognee 的 system/data/cache 目录隔离到方法目录下，设置 `COGNEE_SKIP_CONNECTION_TEST`，并通过 `cognee.config` 设置 system root、data root、cache root。证据：`第三方框架参考/MemoryData/utils/agent.py:1968-1996`。
- MemoryData ingest 时按 context 构造 `dataset_name = default_dataset_<sub_dataset>_context_<context_id>`，把 benchmark context 渲染成一个 `formatted_message` 后调用 `cognee.add(formatted_message, dataset_name=dataset_name)`，并把 dataset 标记为 pending。证据：`第三方框架参考/MemoryData/utils/agent.py:2857-2877`。

推断/含义：

- Cognee 原生最舒服的 ingest 粒度是 document/chunk/dataset，而不是 turn-level chat message。若希望保留 speaker、turn_id、timestamp，需要 adapter 把这些字段编码进文本、metadata/DataItem，或通过 dataset/node_set 做额外分组。

## 3. 检索机制

事实：

- `search()` 原生签名包含 `query_text`、`query_type`、`datasets`/`dataset_ids`、`top_k`、`only_context`、`session_id`、graph search 参数、`include_references`、`llm_config`、`embedding_config`；默认 `query_type` 是 `GRAPH_COMPLETION`。证据：`third_party/methods/cognee/cognee/api/v1/search/search.py:31-58`。
- 搜索文档明确区分类型：`GRAPH_COMPLETION`/`RAG_COMPLETION` 返回 LLM response，`CHUNKS` 返回语义匹配的 raw text segments，`CHUNKS` 是最快的 pure vector similarity，不调 LLM。证据：`third_party/methods/cognee/cognee/api/v1/search/search.py:92-108`、`third_party/methods/cognee/cognee/api/v1/search/search.py:175-204`。
- `SearchType` enum 包含 `SUMMARIES`、`CHUNKS`、`RAG_COMPLETION`、`HYBRID_COMPLETION`、多种 graph completion、`CYPHER`、`NATURAL_LANGUAGE`、`TEMPORAL`、`CHUNKS_LEXICAL`、`AGENTIC_COMPLETION` 等。证据：`third_party/methods/cognee/cognee/modules/search/types/SearchType.py:4-21`。
- retriever registry 把 `SearchType.CHUNKS` 映射到 `ChunksRetriever`，把 `RAG_COMPLETION` 映射到 `CompletionRetriever`，把 `GRAPH_COMPLETION` 映射到 `GraphCompletionRetriever`，graph/RAG 系列可带 system prompt、response model、references、session 等参数。证据：`third_party/methods/cognee/cognee/modules/search/methods/get_search_type_retriever_instance.py:77-160`。
- search 会先按 user/dataset 权限解析授权 dataset，再在 dataset context 中调用 `get_retriever_output()`；若图为空但 dataset 有数据，会 warning 提醒需要先 run cognify。证据：`third_party/methods/cognee/cognee/modules/search/methods/search.py:153-210`、`third_party/methods/cognee/cognee/modules/search/methods/search.py:241-313`。
- 非 access-control 模式下，backward compatible 返回会取 `search_result.result`；若单 dataset 的结果本身是 list，会展开为该 list。verbose 模式才返回 text/context/objects 三类字段。证据：`third_party/methods/cognee/cognee/modules/search/methods/search.py:385-433`。
- MemoryData query 阶段若 dataset pending，会先 `cognee.cognify(datasets=[dataset_name], chunk_size=self.chunk_size)`，随后调用 `cognee.search(query_text=message, query_type=self.cognee_search_type, top_k=self.retrieve_num, datasets=[dataset_name], only_context=True)`，再 flatten/clean retrieved contexts 并交给统一 answer prompt。证据：`第三方框架参考/MemoryData/utils/agent.py:2879-2909`。

推断/含义：

- retrieve-first 接入应优先使用 `SearchType.CHUNKS` 或其他 `only_context` retrieval 形态，并禁止使用默认 `GRAPH_COMPLETION` 作为答案来源。否则 Cognee 自己的 LLM answer 会和 framework reader 混在一起。

## 4. 状态与边界行为

事实：

- Cognee 包依赖默认包含 SQLite async、LanceDB、Ladybug、FastAPI、fakeredis 等；optional extras 才引入 Neo4j、Postgres、fastembed、ollama、scraping 等。证据：`third_party/methods/cognee/pyproject.toml:22-69`、`third_party/methods/cognee/pyproject.toml:91-157`。
- `LLMConfig` 默认 provider/model 是 `openai` / `openai/gpt-5-mini`，并支持 endpoint、api key、temperature、streaming、max completion tokens、fallback、`llm_args` 等字段。证据：`third_party/methods/cognee/cognee/infrastructure/llm/config.py:42-88`。
- `EmbeddingConfig` 默认 provider/model 是 `openai` / `openai/text-embedding-3-large`，会尝试解析 embedding dimensions，解析失败则 fallback 到 3072，并支持 endpoint/api key/batch size。证据：`third_party/methods/cognee/cognee/infrastructure/databases/vector/embeddings/config.py:62-84`、`third_party/methods/cognee/cognee/infrastructure/databases/vector/embeddings/config.py:86-107`。
- MemoryData 会把 LLM provider/model/api_key/endpoint、Qwen3 `enable_thinking=False`、streaming 参数、embedding provider/model/dimensions/endpoint/api key 写入 Cognee config；还可配置 vector DB/graph provider。证据：`第三方框架参考/MemoryData/utils/agent.py:1998-2040`、`第三方框架参考/MemoryData/utils/agent.py:2059-2075`。
- `add()` 和 `cognify()` 都支持 `run_in_background`；blocking 模式等待 pipeline 完成，background 模式返回 pipeline run info，需要用 pipeline id 监控。证据：`third_party/methods/cognee/cognee/api/v1/add/add.py:105-116`、`third_party/methods/cognee/cognee/api/v1/cognify/cognify.py:117-135`。
- `cognify()` 开始前会 `run_migrations_and_block(datasets, user)`，然后按 background/blocking executor 执行 `cognify_pipeline`。证据：`third_party/methods/cognee/cognee/api/v1/cognify/cognify.py:214-221`、`third_party/methods/cognee/cognee/api/v1/cognify/cognify.py:261-287`。
- MemoryData 的 clean retry 会删除 Cognee 的 `.data_storage/data`、`.cognee_system/databases`、`.cognee_cache`。证据：`第三方框架参考/MemoryData/utils/initialization.py:588-598`。

推断/含义：

- Clean retry 最稳妥的边界是独立 Cognee system/data/cache 目录加独立 dataset name；仅清 dataset 不一定覆盖 relational/vector/graph/cache 全部状态。完成判据应以 `cognify` blocking 返回或 pipeline status 完成为准。

## 5. 对协议设计的含义

事实：

- Cognee 官方工作流是 `add` raw data -> `cognify` graph/chunks/embeddings -> `search`，不是一边追加 message 一边立即检索。证据：`third_party/methods/cognee/cognee/api/v1/add/add.py:118-134`、`third_party/methods/cognee/cognee/api/v1/cognify/cognify.py:137-166`。
- `extract_chunks_from_documents()` 以 document 为单位读 chunks，更新 document token_count；这表明 chunk 是 cognify 内部从 document/text 中派生，而非原生要求调用方逐 turn 传入。证据：`third_party/methods/cognee/cognee/tasks/documents/extract_chunks_from_documents.py:30-60`。
- MemoryData 的实际适配把每个 benchmark context 放进一个 dataset，延迟到查询前一次性 cognify，再检索 chunks/context 并由外层 reader 作答。证据：`第三方框架参考/MemoryData/utils/agent.py:2863-2873`、`第三方框架参考/MemoryData/utils/agent.py:2879-2909`。
- search 返回结构取决于 access-control/verbose/query type；非 verbose 的默认兼容路径可能只保留 `result`，因此条目级 provenance 需要 adapter 主动选择 verbose/include_references 或解析原始 SearchResultPayload。证据：`third_party/methods/cognee/cognee/modules/search/methods/search.py:385-433`、`third_party/methods/cognee/cognee/api/v1/search/search.py:55-58`。

推断/含义：

- Cognee 最自然的消费粒度是 document/session/context dataset。协议若只提供 `add(conversation)` 可以跑通，但会把 turn/source/time 保真压力推给文本模板；若协议提供 `finalize(context_id)` 或 `flush(dataset)` 信号，Cognee 可以在该边界执行 `cognify`。
- 若 benchmark 需要公平 retrieve-first，Cognee adapter 应把 `query_type` 明确设为 `CHUNKS`，设置 `only_context=True`，并把返回的 chunk 文本、dataset、source metadata 一起交给统一 reader。

## 6. 未确认项

- 本轮未进行真实 `add/cognify/search` smoke，因为 `cognify` 和 graph completion 路径会触发 LLM/embedding；只完成 uv 隔离安装与源码审计。证据：`third_party/methods/cognee/cognee/api/v1/cognify/cognify.py:69-73`、`docs/workstreams/ws02-phase1-matrix/plan-track-a2-method-mechanism.md:14-23`。
- `SearchType.CHUNKS` 的具体返回对象中哪些字段在当前配置下可作为 source id、score、chunk id，需要后续用 fake/local embedding 或受控小样本实测；本卡只确认官方文档声称可返回 text passages with source metadata。证据：`third_party/methods/cognee/cognee/api/v1/search/search.py:104-108`、`third_party/methods/cognee/cognee/api/v1/search/search.py:175-183`。
- V2 `remember/recall` 的 session memory/cache 语义未深挖，因为 MemoryData 实际集成使用 V1 `add/cognify/search`。证据：`third_party/methods/cognee/cognee/__init__.py:52-68`、`第三方框架参考/MemoryData/utils/agent.py:2857-2909`。
- MemoryData 的 Cognee 目录清理路径是相对 `./methods/cognee/source/cognee/...`，而初始化路径来自 `self.method_dir`；两者在不同工作目录下是否完全一致，需要接入时实测。证据：`第三方框架参考/MemoryData/utils/agent.py:1968-1996`、`第三方框架参考/MemoryData/utils/initialization.py:588-598`。
