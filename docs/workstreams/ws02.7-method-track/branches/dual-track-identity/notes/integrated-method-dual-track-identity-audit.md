# 三家已接 method 的双轨实现身份与 build-axis 审计

> 取证日：2026-07-16。actor：Fable 5（Claude Code）。派工卡：
> `../cards/actor-prompt-integrated-method-dual-track-identity-audit.md`。
> docs-only、零真实 API、零联网、零下载；全部结论来自 vendored 一手源码与本仓库
> 框架代码的静态读码。经卡内明确授权，本卡实质使用了 3 个并行只读 subagent
> （Mem0/MemoryOS=Opus 4.8，LightMem=Sonnet 5）分包一手取证；所有承重锚点均由
> 主 actor（Fable 5）复核，矛盾整合与本文全部结论由主 actor 负责。
> 本卡只补事实与实施影响，不重新裁定 embedding 主轨政策。
>
> 配置值身份标注约定（全文沿用）：**(i)**=函数签名/dataclass 默认；
> **(ii)**=README/demo/YAML 示例覆盖；**(iii)**=实际 CLI/脚本入口默认；
> **(iv)**=调用点显式传值。
>
> **架构师强验收勘误（2026-07-16）：**主体结论接受；两处文字由架构师抽锚后修正：
> ① OpenAI 托管 embedding 只能锁 provider/model/API 接口身份，不能锁服务端权重 revision，
> 因而不得称“权重级可复现”；② 原 E6 把已经正确落地的 MemoryOS native
> `max_tokens=2000` 误列为待勘误，现删除。LightMem P1 的后续裁决见同目录
> `product-default-embedding-ruling.md`，不回写 actor 当时的停点历史。

## 0. 结论摘要

1. **Mem0**：官方 `memory-benchmarks` harness 默认 backend=`oss`，经本地 FastAPI
   server 调 `Memory.from_config` → 与通用产品**同一** `Memory.add/search` core
   （`memory-benchmarks/docker/mem0/main.py:145`）→ **`CONFIG_EQUIVALENT`**；
   但存在 `cloud` backend 打 `api.mem0.ai` 闭源远端（**`ALGORITHM_VARIANT`**，
   默认不启用）。产品默认 embedding = `openai/text-embedding-3-small/1536/COSINE`
   （**(i)**，`mem0/embeddings/openai.py:15,19`），远端计费、接口公开、与算法
   无硬耦合，可作单一 profile 跨五 benchmark 固定；但服务端权重 revision 由 provider
   管理，只能按 provider/model/endpoint/run time 记录，不得声称权重级 pin。harness answer/judge 默认
   **gpt-5**（`benchmarks/locomo/run.py:682-683`）→ **`FRAMEWORK_MODEL_OVERRIDE /
   PARTIAL_NATIVE`**。产品默认 build LLM 是 **gpt-5-mini**（`mem0/llms/openai.py:39`
   **(i)**），当前 gpt-4o-mini 是框架全局锁 override，不是产品默认。
2. **LightMem**：两个官方 experiments 目录均 `from lightmem.memory.lightmem import
   LightMemory`（`experiments/locomo/add_locomo.py:8`、
   `experiments/longmemeval/run_lightmem_gpt.py:6`），ingest/update 无算法副本 →
   ingest 面 **`CONFIG_EQUIVALENT`**；但 LoCoMo 官方检索走 harness 本地
   `VectorRetriever`（get_all + 手算 cosine，`experiments/locomo/search_locomo.py:17`），
   不调 core `retrieve()`，检索面是 harness-local 变体。**产品 schema 层没有可运行的
   默认 embedding**（顶层 `text_embedder=None`，`src/lightmem/configs/base.py:65`）；
   最近似锚是 HF backend 内部 fallback `"all-MiniLM-L6-v2"`
   （`src/lightmem/factory/text_embedder/huggingface.py:16`）+ paper/experiments
   一致使用 MiniLM——**pinned product default 需架构师裁定**（停点 P1）。
3. **MemoryOS**：`memoryos-pypi` 与 `memoryos-chromadb` 构造签名默认**逐参数相同**
   （含 `embedding_model_name="all-MiniLM-L6-v2"`、`llm_model="gpt-4o-mini"`，
   pypi `memoryos.py:35-42` vs chromadb `memoryos.py:38-45`，主 actor 亲核），但
   **chromadb 是 copy-then-fork 的 `ALGORITHM_VARIANT`，不是 storage backend
   variant**（检索 query 重新引入 LLM 抽词、top-k 截断+clamp 打分、合并
   `N_visit+=1`、LTM 护栏丢失、atexit 持久化时序、capacity 死参数，见 §4）；
   `eval/` 维持 m1 结论亦为 `ALGORITHM_VARIANT`。产品默认 embedding = 签名默认
   `all-MiniLM-L6-v2`（本地、免费）——**与当前框架 TOML 的模型身份一致**（仅
   `sentence-transformers/` 前缀写法差异），MemoryOS 迁移 product-default 主轨
   **不需要重建 memory**。native 只能 readout-native + `judge=framework_fallback`
   = PARTIAL_NATIVE（官方无 LLM judge，token-set F1）。
4. **审计 D（框架侧，主 actor 一手）**：当前 `config_track=native` **确实会把
   partial-native 过度标成 full-native**——manifest 只有裸字符串
   `config_track="native"`（`cli/run_prediction.py:1577-1578`），bundle 的
   `embedding_ref/hyperparam_ref` 从未被应用也从未落 manifest；实证 native run
   manifest（`outputs/runs/mem0/locomo/smoke/native/mem0-locomo-native-s1/
   manifest.json`）build 仍是框架 MiniLM。judge fallback（MemoryOS
   `judge_profile=None` → 框架 judge，`cli/commands.py:213-226`）无任何
   `framework_fallback` 标记。三家现有 native run 全部实际为
   **readout-only native on controlled build**。
5. **迁移面**：仅 Mem0 的 product-default 迁移改变 build 轴（MiniLM/384/本地 →
   text-embedding-3-small/1536/远端），必须重建 memory 并重开 B8+/B11；
   MemoryOS 为零重建；LightMem 待 P1 裁定（若裁 MiniLM 则零重建）。既有 unified
   产物全部保留、docs 侧重标 `controlled_embedding_v1`，不改 outputs 文件。

## 1. 三家 implementation identity 表（审计 A）

### 1.1 Mem0

| 字段 | 事实 |
|---|---|
| Phase 1 通用产品实现 | 进程内 `mem0.Memory`：adapter `importlib.import_module("mem0")` → `Memory.from_config(...)`（`src/memory_benchmark/methods/mem0_adapter.py:1153` 区段，经 `build_backend_config` `:398-448`）；ingest=`Memory.add`（`third_party/methods/mem0-main/mem0/memory/main.py:573`），retrieve=`Memory.search`（`main.py:1126`）。adapter 对 `self._memory` 仅 `search/add/delete_all` 三类调用（复核既有 ADD-only 审计 §5，仍成立）。 |
| 官方 benchmark harness | **不直接 import core**：`benchmarks/` 入口经 REST 客户端 `Mem0Client`（`memory-benchmarks/benchmarks/common/mem0_client.py`）。`oss` backend（默认，`benchmarks/locomo/run.py:712` **(iii)**）：`POST /memories`、`/search`（`mem0_client.py:159,269`）→ 本地 FastAPI `docker/mem0/main.py:222` `mem.add` / `:246` `mem.search`，`mem` 来自 `Memory.from_config(config)`（`main.py:145`，同包 `from mem0 import Memory` `main.py:142`）。`cloud` backend：`POST {api.mem0.ai}/v3/memories(/search)/`（`mem0_client.py:182-235,330`），远端闭源实现，响应含 UPDATE 事件解析（`mem0_client.py:437-439`）。ingest 调用点 `benchmarks/locomo/run.py:340`，retrieve `run.py:417`。 |
| core reuse | oss=import **同一 core**；cloud=远端异实现。 |
| material differences（oss vs 产品/框架） | 传输层 HTTP+容器 Qdrant vs 进程内本地 Qdrant；build LLM：harness YAML gpt-4o-mini **(ii)**（`memory-benchmarks/.../configs/openai.yaml:10-11`，temp 0.1，与 adapter 调用点显式 temp 0.1 `mem0_adapter.py:431` 一致）vs 产品签名默认 gpt-5-mini **(i)**；embedder：harness openai/text-embedding-3-small/1536 **(ii)** vs 框架 MiniLM/384 **(iv)**；top_k：harness 入口默认 200 **(iii)**（`run.py:687,963`）vs 产品签名默认 20 **(i)**（`main.py:1130`）=框架 TOML 值 **(iv)**；chunk：harness LoCoMo=1 msg（`locomo/run.py:88`）、LongMemEval=2-turn pair（`longmemeval/run.py:96`）；timestamp：harness client 发 `timestamp=session_epoch`（`run.py:340`）但 **oss server `AddRequest` 无该字段、`main.py:203-226` 不转发 → oss 路径时间被丢弃**（cloud 才生效），框架改用 `prompt` 扩展点注入 session 时间（`mem0_adapter.py:1582-1590` 区段）。 |
| classification | 默认路径（oss）= **`CONFIG_EQUIVALENT`**；cloud 路径 = **`ALGORITHM_VARIANT`**（远端闭源，不得混入 native track）。 |
| native 可否只换配置 | **yes（限 oss 口径）**——harness 与产品同一 `Memory.add/search` core，差异全部可配置（embedder/top_k/answer/judge/prompt 包装）；锚：`docker/mem0/main.py:142-145`。cloud 口径 no。 |

### 1.2 LightMem

| 字段 | 事实 |
|---|---|
| Phase 1 通用产品实现 | adapter `sys.path.insert` vendored src 后 `importlib.import_module("lightmem.memory.lightmem")`（`src/memory_benchmark/methods/lightmem_adapter.py:312-315`），`LightMemory.from_config(backend_config)`（`:1140`）；ingest=`backend.add_memory(...)`（`:804`）；retrieve=`text_embedder.embed()` + `embedding_retriever.search()`（Qdrant ANN，`:1316-1375`）。 |
| 官方 benchmark harness | LoCoMo：`add_locomo.py:8` `from lightmem.memory.lightmem import LightMemory`，构造 `LightMemory.from_config`（`add_locomo.py:230`），ingest `add_memory`（`:332-337`），同脚本 ingest 后 `construct_update_queue_all_entries()` + `offline_update_all_entries(score_threshold=0.9)`（`:446-447` **(iv)**）；检索在 `search_locomo.py` 用 **harness 本地** `VectorRetriever`（`search_locomo.py:17` import 本地 `retrievers.py`；get_all + 手算 cosine，`experiments/locomo/retrievers.py:111-132`），不调 core `retrieve()`。LongMemEval：`run_lightmem_gpt.py:6` 同 core import，构造 `:133`，ingest `:170-174`，检索直接调 core `lightmem.retrieve(question, limit=20)`（`:181` **(iv)**）；offline update 在独立 `offline_update.py:41`（score=0.8 **(iv)**），主脚本不跑。 |
| core reuse | ingest/update 两个 benchmark 均 import **同一 core**，experiments 目录无算法实现副本（`retrievers.py` 是检索辅助脚本，不改 core 写入/更新算法）。 |
| material differences | ① LoCoMo 官方检索路径是 harness-local 手算 cosine（brute-force get_all），框架与 LongMemEval 官方走 Qdrant 检索——小集合上功能等价，但排序实现不同源；② 两 benchmark 官方 update 时机/阈值互不相同（LoCoMo ingest 后立即全库 0.9；LongMemEval 检索前不 update、独立脚本 0.8）；③ LoCoMo 官方还有 per-speaker 检索模式（`search_locomo.py:74-160`），框架走 combined。 |
| classification | ingest/build 面 **`CONFIG_EQUIVALENT`**；LoCoMo 官方检索面为 harness-local 检索变体（近 `STORAGE_BACKEND_VARIANT` 性质：同库不同检索器），不构成 core fork。 |
| native 可否只换配置 | **yes（build/ingest 轴）**——同一 core，差异是配置与检索器包装；但 LoCoMo native 的"官方手算 cosine 检索"若要逐字复刻属于检索器代码资产，不是纯 TOML（锚：`search_locomo.py:17`、`retrievers.py:111-132`）。 |

### 1.3 MemoryOS

三份代码形态（`memoryos-pypi` / `memoryos-chromadb` / `eval/`）**各自持有完整源码
副本、互不 import 共享 core**（chromadb 是从 pypi 同源文件复制后改写：相对导入指向
本目录 `.storage_provider`/`.utils`，多出 `storage_provider.py`）。分类逐对：

| 字段 | 事实 |
|---|---|
| Phase 1 通用产品实现 | adapter 只 wire `memoryos-pypi`（`src/memory_benchmark/methods/memoryos_adapter.py:94,264-313`）：`Memoryos` 构造 → ingest=`add_memory`（pypi `memoryos.py:226-250`）→ 检索复刻 `get_response` 步骤 1-7（`memoryos_adapter.py:745-767` 区段，不调完整 `get_response`）。chromadb/eval 均未接入。 |
| 官方 benchmark harness | `eval/main_loco_parse.py` 手工组合 `ShortTermMemory/DynamicUpdate/RetrievalAndAnswer`（`:248-252`），STM=1、queue=10、heat α/β/γ=.8/.8/.0001、检索 query 时 LLM 抽词——与 pypi 的算法差异已由 m1 note 钉死，本卡抽核仍成立。 |
| core reuse | copy-then-fork ×2：pypi↔chromadb、pypi↔eval 均为同源复制后分叉，无共享 import。 |
| material differences（pypi↔chromadb，一手复核） | ① 检索 query 时 LLM 关键词抽取：chromadb 有（`memoryos-chromadb/mid_term.py:290`），pypi 明确删除（`memoryos-pypi/mid_term.py:292` `query_keywords = set()  # Keywords extraction removed`）；② add 时 chromadb 对 summary+每 page 各多一次关键词 LLM（`memoryos-chromadb/mid_term.py:105,137`）；③ page 检索 pypi 全量内存打分全数返回（`memoryos-pypi/mid_term.py:334-342`）vs chromadb ChromaDB top_k=20 硬截断 + `max(0.0, 1-distance)` clamp（`memoryos-chromadb/mid_term.py:319`、`storage_provider.py:38-40,202-225`）；④ session 合并候选 pypi 全扫 vs chromadb 只扫 ChromaDB top-5（两版 `mid_term.py:206` 对照）；⑤ 合并副作用：chromadb `N_visit += 1`（`memoryos-chromadb/mid_term.py:264`），pypi 不加（`memoryos-pypi/mid_term.py:271-273`，主 actor 逐行核对）；⑥ heat 触发 LTM 更新函数不同、chromadb 丢 pypi 的 30 字符护栏与逐行拆分（chromadb `memoryos.py:172-226` vs pypi `memoryos.py:154-215`）；⑦ 持久化时序：pypi 每操作落盘（`mid_term.py` `self.save()`）vs chromadb 元数据内存态 + `atexit` flush（`memoryos-chromadb/memoryos.py:81,132-135`、`storage_provider.py:74-80`，主 actor 亲核）；⑧ chromadb `long_term_knowledge_capacity` 是死参数——构造收下但不透传给 `LongTermMemory`（chromadb `memoryos.py:95-112` 无 capacity 实参 vs pypi `memoryos.py:97,105` 正常透传，主 actor 亲核）；⑨ ChromaDB 查询异常静默 `return []`（`storage_provider.py:195-197,226-228`），pypi 无此吞咽。 |
| classification | pypi↔chromadb = **`ALGORITHM_VARIANT`**（不是 `STORAGE_BACKEND_VARIANT`：存储替换之外，检索打分、合并、heat 演化、LTM 写入语义、持久化时序全部分叉）；pypi↔eval = **`ALGORITHM_VARIANT`**（既有 m1 结论维持）；chromadb↔eval = 独立实现（都 query 时抽词，但 heat 常量、STM、存储均不同）。 |
| native 可否只换配置 | **no**（chromadb 与 eval 都不能作为 pypi 的 config-track native：算法分叉，须按政策另列 `reproduction_variant` 或 storage-variant 候选重新过门）；eval 的 answer prompt/参数资产可继续作 readout-native 配置源（同 m1 结论）。 |

## 2. 三家 build-axis 三方表（审计 B）

### 2.1 Mem0

| 轴 | (1) 产品无覆盖真默认 | (2) 框架 unified 实际 | (3) 官方 harness 实际 |
|---|---|---|---|
| implementation variant | 进程内 `Memory` V3 additive pipeline（`main.py:699-971`）**(i)** | 同 core **(iv)** | oss=同 core via HTTP server **(iii)**；cloud=远端 V3 **(iii)** |
| storage backend | Qdrant（provider 默认 `vector_stores/configs.py:7-9` **(i)**；本地 path/collection 默认 `configs/vector_stores/qdrant.py:11-16` **(i)**） | Qdrant，调用点显式 path=`<state>/qdrant`、collection=`mem0`、dims=384（`mem0_adapter.py:440-447` **(iv)**） | Qdrant 容器（`docker/mem0/main.py:80-103` **(iii)**） |
| embedding provider/model/dim | openai（`embeddings/configs.py:9` **(i)**）/ text-embedding-3-small（`embeddings/openai.py:15` **(i)**）/ 1536（`openai.py:19` **(i)**；默认不向 API 发 dimensions 参数，`openai.py:17` `_pass_dimensions_to_api`） | huggingface / sentence-transformers/all-MiniLM-L6-v2 / 384（`configs/methods/mem0.toml:12-14` **(iv)**） | openai / text-embedding-3-small / 1536（`configs/openai.yaml:14-16` **(ii)**；server env fallback `main.py:112` **(iii)**） |
| revision | 无权重 pin（OpenAI 托管；model id 只锁接口身份，服务端 revision 由 provider 管理）**(i)** | HF repo id 无 revision pin（SOURCE_UNDETERMINED，见 §7） | 同产品 **(ii)** |
| normalization | 无显式归一化（`openai.py` embed 仅换行清洗）**(i)** | SentenceTransformer encode 未显式 normalize（`mem0/embeddings/huggingface.py:44`；模型内建与否 SOURCE_UNDETERMINED） | 同产品 **(i)** |
| instruction/prefix | 无（`memory_action` 参数存在但 openai embedder 不消费）**(i)** | 无 **(i)** | 无 **(i)** |
| distance | Qdrant COSINE（`vector_stores/qdrant.py:120,146` **(i)**） | 同 **(i)** | 同 **(i)** |
| 远端/费用 | LLM+embedder 远端按 token 计费；Qdrant 本地 **(i)** | LLM 远端；embedder 本地免费 **(iv)** | LLM+embedder 远端计费 **(ii/iii)** |
| build LLM | **gpt-5-mini**（`llms/openai.py:39` **(i)**） | gpt-4o-mini（`mem0.toml:11` **(iv)**，temp 0.1 调用点显式 `mem0_adapter.py:431` **(iv)**） | gpt-4o-mini, temp 0.1（`configs/openai.yaml:10-11` **(ii)**） |
| extraction prompt | `ADDITIVE_EXTRACTION_PROMPT`（`main.py:725` **(i)**） | 同 core + `prompt` 扩展点追加 session 时间锚（`mem0_adapter.py:1582-1590` **(iv)**） | 同 core（oss）**(i)** |
| update lifecycle | infer=True 默认（`main.py:581` **(i)**）；V3 pipeline **ADD-only + hash 去重**（`main.py:699-863`，history 全 "ADD"）；UPDATE/DELETE 仅存在于手动 API 与 cloud | infer=true（`mem0.toml:19` **(iv)**），同 ADD-only | oss 同 ADD-only；cloud 含 UPDATE 事件（`mem0_client.py:437-439`） |
| chunk/segment | core 不切分（调用方决定）**(i)** | ingestion_chunk_size=1（`mem0.toml:18` **(iv)**）+ registry 粒度（LoCoMo/MemBench=turn、BEAM=pair、LME/HaluMem=session 内切块） | LoCoMo=1 msg（`locomo/run.py:88`）、LME=2-turn pair（`longmemeval/run.py:96`）**(iii)** |
| retrieval top-k / threshold | 20 / 0.1（`main.py:1130,1132` **(i)**）；rerank=False（`:1133` **(i)**） | 20（`mem0.toml:16` **(iv)**）/ 未覆盖→0.1 **(i)** | **200**（`run.py:687,963` **(iii)**），cutoffs 10/20/50/200；threshold 未传→0.1 **(i)** |
| summary/consolidation | 无 **(i)** | 无 | 无 |
| 并发 | N/A（core 单调用） | smoke=1 / full=10（`mem0.toml:17,30` **(iv)**） | max_workers=10、rpm=200（`run.py:689,711` **(iii)**） |
| answer model/decoding | —（core 无 answer） | 框架锁 gpt-4o-mini；native bundle temp 0.0/max_tokens 4096/top_p None（`mem0_native_prompts.py:689-692`） | **gpt-5**（`locomo/run.py:682`、`longmemeval/run.py:943` **(iii)**）→ `FRAMEWORK_MODEL_OVERRIDE / PARTIAL_NATIVE` |
| judge model/prompt/metric | — | gpt-4o-mini judge；native judge profile temp 0.0/max_tokens 4096/n 1（`mem0_native_prompts.py:718-742`） | **gpt-5**（`run.py:683,947` **(iii)**）；binary CORRECT/WRONG + PARTIAL CREDIT 语义（`locomo/prompts.py:203,222`）→ 同上 PARTIAL_NATIVE |
| answer prompt parity | — | `MEM0_NATIVE_ANSWER_PROFILES` | 关键段 parity 命中（`locomo/prompts.py:42-45` "SCAN ALL MEMORIES / ENTITY VERIFICATION" 同段）；judge prompt 逐字全文 parity 未跑（§7） |

### 2.2 LightMem

paper / 复现目录 / repo 默认 / 框架四列全表已有一手 note
（[`lightmem-native-config-threeway.md`](../../../notes/lightmem-native-config-threeway.md)，
本卡抽核未发现失效锚点），此处只列本卡增量与身份标注修正：

| 轴 | (1) 产品无覆盖真默认 | (2) 框架 unified 实际 | (3) 官方 harness 实际 |
|---|---|---|---|
| implementation variant | `LightMemory`（`src/lightmem/memory/lightmem.py`）**(i)** | 同 core（`lightmem_adapter.py:312-315,1140` **(iv)**） | 同 core import；LoCoMo 检索是 harness-local `VectorRetriever` **(iii)** |
| embedding | **无可运行顶层默认**：`text_embedder=None`（`configs/base.py:65` **(i)**）；`index_strategy=embedding/hybrid` 且未配置时 `TextEmbedderFactory.from_config(None)` 直接 AttributeError fail-fast（`memory/lightmem.py:195-197` + `factory` 链）。HF backend 内部 fallback `"all-MiniLM-L6-v2"`（`factory/text_embedder/huggingface.py:16` **(i)，backend 层**） | 本地路径 `models/all-MiniLM-L6-v2`、384、CPU（`configs/methods/lightmem.toml:21` **(iv)**） | LoCoMo add 脚本是占位符 `/path/to/embedding-model`（`add_locomo.py:37` **(iii)，不可直接运行**）；LME gpt 脚本 Hub 名 `all-MiniLM-L6-v2`（`run_lightmem_gpt.py:117` **(iii)**，无 revision pin，首次需联网） |
| normalization/distance | encode 未显式 normalize（`huggingface.py:52`）；Qdrant `create_col` 默认 COSINE（`factory/retriever/embeddingretriever/qdrant.py:65` **(i)**）；dims 进 collection 后不可变（`qdrant.py:63,83`） | 同 core | LoCoMo harness 手算 cosine（`retrievers.py:111-132`）；`retrievers.py:26` 硬编码 dims=384 |
| update 时机/阈值 | mode=offline、score=0.9（`memory/lightmem.py:539-550,644-659` **(i)**） | online_soft 主 profile：无全库 update（`lightmem.toml:35` **(iv)**，裁决见 lightmem-lifecycle 支线） | LoCoMo：ingest 后立即全库 0.9（`add_locomo.py:446-447` **(iv)**）；LME：独立脚本 0.8（`offline_update.py:41` **(iv)**），主检索脚本不 update |
| retrieval | core `retrieve` default limit=10 **(i)** | limit=60 combined（`lightmem.toml:23` **(iv)**） | LoCoMo combined limit=60（readme 报告值）另有 per-speaker 模式；LME core retrieve limit=20（`run_lightmem_gpt.py:181` **(iv)**） |
| answer/judge | schema 不含 answer/judge client（`configs/base.py:16-123`，五项"来源待溯"沿用 threeway note 结论） | native bundle：answer temp 0.0/2000/0.8（`lightmem_native_prompts.py:131-135`），judge 官方 parity | GPT 脚本 answer/judge=gpt-4o-mini；**qwen 脚本 answer=qwen-plus、judge=deepseek-chat**（`run_lightmem_qwen.py:15,10` **(iii)**）→ 该口径 `FRAMEWORK_MODEL_OVERRIDE / PARTIAL_NATIVE` |

### 2.3 MemoryOS

| 轴 | (1) pypi 无覆盖真默认 | (2) 框架 TOML/adapter 实际 | (3) 官方 eval/ 实际 |
|---|---|---|---|
| implementation variant | pypi `Memoryos` 统一类 **(i)** | pypi（`memoryos_adapter.py:94,264` **(iii/iv)**） | 脚本手工组合 **(iii)**（`eval/main_loco_parse.py:248-252`） |
| storage backend | JSON+faiss 本地 **(i)** | 同 **(iv)** | 同 **(iii)**（chromadb 版=ChromaDB，未接入） |
| embedding provider/model | SentenceTransformer / 裸名 `all-MiniLM-L6-v2`（`memoryos-pypi/memoryos.py:42` **(i)**） | `sentence-transformers/all-MiniLM-L6-v2`（`configs/methods/memoryos.toml:8,31` **(iv)**，限定名=裸名同模型） | `all-MiniLM-L6-v2`（`eval/utils.py:17` **(iii)**） |
| dimension | 384（模型固有）**(i)** | 384 **(iv)** | 384 **(iii)**；README demo bge-m3=1024 属 **(ii)** 覆盖 |
| normalization/instruction/distance | encode 不传 normalize、无 instruction；调用方外部 L2 归一 + faiss 内积（`memoryos-pypi/utils.py:194-197,220-225` **(i)**） | 同 core **(iv)** | 同族；eval 每次 `SentenceTransformer(model_name)` 重建无缓存（`eval/utils.py:17-19` **(iii)**） |
| 本地/远端 | embedding 本地免费；首跑 HF cache miss 需联网下载，无 `local_files_only`/timeout（`utils.py:176-181`，与 m1 note B8+ gap 一致）**(i)** | 同 **(iv)** | 同 **(iii)** |
| build LLM | gpt-4o-mini（`memoryos.py:41` **(i)**——产品签名默认恰为项目全局锁，无 override） | gpt-4o-mini（`memoryos.toml:7` **(iv)**） | gpt-4o-mini（`eval/main_loco_parse.py:156` **(iii)**） |
| update lifecycle | STM 满→MTM；heat≥5→profile/knowledge **(i)** | 同 pypi **(iv)** | STM=1 使几乎每对即迁移 **(iii)** |
| chunk/超参 | STM=10/MTM=2000/queue=7（`memoryos.py:35-38` **(i)**） | 10/2000/7（`memoryos.toml:9-12` **(iv)**） | STM=1/MTM=2000/queue=10（`main_loco_parse.py:248-252` **(iv)**） |
| retrieval 阈值 | seg=.1/page=.1/knowledge=.01/sessions=5（签名+`retriever.py:92-99` **(i)**） | 同签名默认 **(iv)**（`memoryos.toml:15-18`） | seg=.1/page=.1/knowledge=**.1**/queue=10 **(iv)**（`main_loco_parse.py:272-276`）——knowledge 阈值三方分叉 |
| 并发 | retrieve 三路 ThreadPool（`retriever.py:110` **(i)**） | 同 + 框架 max_workers 1/10 **(iv)** | 单线程 **(iii)** |
| answer model/decoding | `get_response` gpt-4o-mini/temp .7/max_tokens **1500**（`memoryos.py:338-343` **(i)**） | 不调 `get_response`；框架 reader 答题 **(iv)** | gpt-4o-mini/temp .7/max_tokens **2000**（`main_loco_parse.py:156` **(iii)**） |
| judge | 无 **(i)** | 框架 judge（fallback，无落盘标记，见 §5.1） | **无 LLM judge**：本地 token-set F1（`eval/evalution_loco.py`）→ native 只能 readout-native + `judge=framework_fallback` = **PARTIAL_NATIVE** |

## 3. 三家 product-default 精确身份与跨五 benchmark 可用性

| | Mem0 | LightMem | MemoryOS |
|---|---|---|---|
| provider/model | openai / text-embedding-3-small（`mem0/embeddings/openai.py:15`、`embeddings/configs.py:9`，均 **(i)**） | **SOURCE_UNDETERMINED（停点 P1）**：顶层无默认（`configs/base.py:65`）；候选锚=HF backend fallback `all-MiniLM-L6-v2`（`huggingface.py:16`）+ paper/experiments 一致 MiniLM | 本地 SentenceTransformer / `all-MiniLM-L6-v2`（构造签名默认 `memoryos-pypi/memoryos.py:42` **(i)**） |
| dimension | 1536（`openai.py:19`；默认不发 dimensions 参数） | 384（模型固有；`retrievers.py:26` 亦硬编码 384） | 384（模型固有） |
| revision 可锁定性 | OpenAI 托管，model id 即身份，无 revision 概念；可锁定到 vendored 2.0.4 的默认解析逻辑 | 代码无 `revision=` 参数；本地目录可 hash 锁定，Hub 名不锁 | 同左：无 revision 参数；可用本地模型目录 hash 锁定 |
| normalization | 无显式归一化 | encode 未显式 normalize（`huggingface.py:52`） | encode 不传 normalize；调用方外部 L2 归一（`memoryos-pypi/utils.py:220-225`） |
| instruction/prefix | 无 | 无 | 无（`utils.py:176-181,194-197`） |
| distance | Qdrant COSINE（`vector_stores/qdrant.py:120,146`） | Qdrant COSINE（`qdrant.py:65`） | faiss 内积 on 归一化向量（≈cosine） |
| 远端/费用 | **远端、按 token 计费、公开可访问**（api.openai.com） | 本地免费（本地路径时零联网；Hub 名首次下载需联网） | 本地免费（首次 cache miss 可能联网下载，已在 m1 note B8+ 记 gap） |
| 与算法硬耦合 | 无：embedder 经 EmbedderFactory 纯配置注入，pipeline 只调 `embed/embed_batch`（`main.py:685,708,773`） | 中度：Qdrant collection 维度建库后不可变、COSINE 写死；换 provider 需重建库但不改核心流程 | 无 benchmark 相关分支；embedding 由 utils 单点封装，模型可换（维度随模型自适应，`utils.py:220-225` 外部归一化与模型无关） |
| 跨五 benchmark 单一 profile 可用性 | **可**：模型 id 稳定、benchmark 无关；唯一约束是远端计费成本须进预算表 | 待 P1 裁定后可（MiniLM 本地对五家无差别） | **可**（当前 TOML 已是同名模型跨五家固定） |

## 4. MemoryOS pypi / ChromaDB 专项（审计 C）

逐项回答卡内 §5：

1. **公开构造 / `add_memory` / 纯检索是否同形**：构造签名逐参数同形（pypi
   `memoryos.py:29-43` ≡ chromadb `memoryos.py:32-46`，主 actor 双侧亲核，含
   `embedding_model_name="all-MiniLM-L6-v2"`、`llm_model="gpt-4o-mini"`、
   STM=10/MTM=2000/LTM=100/queue=7/heat=5.0/sim=0.6 全部相同）；
   `add_memory(user_input, agent_response, timestamp, meta_data)` 同形且 STM 满载
   前置迁移逻辑同序（chromadb `memoryos.py:236-260` ≡ pypi `:226-250`，chromadb
   qa_pair 多塞 `user_id` 字段）。**纯检索不同形**：Retriever 构造参数名变
   （`long_term_memory` → `user_long_term_memory`，两版 `retriever.py:19-28`），
   返回 item schema 不同——chromadb 知识条目 `{id,text,similarity,timestamp}` vs
   pypi `{knowledge,timestamp,embedding}`，且 chromadb prompt 只读 `['text']`。
2. **STM 迁移 / MTM 构造 / heat / LTM 是否同序**：STM→MTM 迁移同序（两版
   `updater.py:100-158` 逐行等价）；heat 常量同（两版 `mid_term.py:21-24`
   α=β=γ=1、tau=24）但**触发副作用分叉**（chromadb 合并 `N_visit+=1`，
   `mid_term.py:264`；pypi 不加）；MTM 构造分叉（chromadb add 时 summary+每 page
   各多一次关键词 LLM，`mid_term.py:105,137`；pypi page_keywords=[]，
   `mid_term.py:141-142`）；heat 触发 LTM 更新分叉（函数不同、chromadb 丢 30 字符
   护栏与逐行拆分、只标 `unanalyzed_pages`，chromadb `memoryos.py:172-226` vs
   pypi `:154-215`）。
3. **是否只换 persistence**：**否**。除 ChromaDB 存储外同时改变：检索打分语义
   （clamp cosine vs 可负内积）、top-k 截断（20）、合并候选面（top-5 vs 全扫）、
   id 生成（`generate_id` = text+uuid8 随机后缀不去重，`storage_provider.py:290`、
   `utils.py:90-91`）、异常降级（静默 `return []`）、持久化时序（atexit flush vs
   逐操作落盘）。完整清单见 §1.3 material differences ①-⑨。
4. **两者 repo defaults 是否相同**：构造签名默认逐参数相同；但两个隐藏差异——
   (a) chromadb `long_term_knowledge_capacity` 是**死参数**（收下不透传，默认 100
   数值巧合一致，设 ≠100 时被忽略；主 actor 亲核 chromadb `memoryos.py:95-112` vs
   pypi `:97,105`）；(b) chromadb 多一个 `distance_function="cosine"` 轴
   （`storage_provider.py:17`），pypi 无。
5. **框架 sidecar exact page provenance 可否原样迁移**：**部分可以**。sidecar 键=
   逐字 `{user_input, agent_response}`（`memoryos_adapter.py:1828-1839` 区段），
   chromadb `search_mid_term_pages` 返回保留 `page_id/user_input/agent_response`
   （`storage_provider.py:218-224`）→ 正文反查键可无损重建；**但该返回结构丢
   `timestamp`**（pypi 返回完整 page 对象含 timestamp），formatted_memory 的中期
   page 时间与 `RetrievedItem` 时间通道需 adapter 反查补齐——B4 gap。
6. **作为 storage variant 接入最少重开的门**：**B3/B4/B5/B6/B8/B11 全部六门**——
   B3（collection 按 user_id 命名 + PersistentClient 文件锁 + atexit 元数据落盘，
   clean-retry/reset 干净度重证）；B4（检索丢 mid-term page timestamp，硬门）；
   B5（ChromaDB `_safe_metadata` 处理后需重证正文逐字一致，
   `storage_provider.py:54-55,159-163`）；B6（**硬门**：元数据只在 atexit
   `save_all_metadata` 落盘，`mid_term.save()` 只写内存 dict
   （`memoryos-chromadb/mid_term.py:356-360`），向量 auto-persist 与元数据不同步，
   崩溃即错位）；B8（`N_visit+=1`、clamp、静默异常改变检索副作用语义）；
   B11（build 侧算法变——额外 LLM 抽词、持久化时序——五件套+并行冒烟全部重跑）。

结论：`memoryos-chromadb` 按证据只能分类 **`ALGORITHM_VARIANT`**；若未来接入应按
政策走 `reproduction_variant`/独立 variant 身份 + 全六门重开，不能以
`STORAGE_BACKEND_VARIANT` 口径低成本换入。是否接入由架构师定，本卡不代选主实现；
Phase 1 canonical 继续 pypi 与既有裁决一致。

## 5. controlled 旧产物保留与 product-default 复证 / manifest 影响（审计 D，主 actor 一手）

### 5.1 run identity / manifest 现状

- config_track 进输出路径：`cli/run_prediction.py:1345`（`mode/track` 段），合法值
  校验 `:1332-1334`。
- manifest 只记裸字符串：`_build_method_manifest`（`cli/run_prediction.py:1557-1585`）
  仅在 native 时写 `config_track="native"`（`:494`、`:1577-1578`）；unified run 无
  显式 track 字段（缺席=unified）。
- `ConfigTrackBundle.embedding_ref` / `hyperparam_ref`
  （`methods/config_track.py:53-54,72-73,86-87`）**从未被运行时应用、也从未写进
  manifest**（全 src 检索仅 config_track.py 自身命中）；native bundle 真正生效的
  只有 `answer_llm_settings` 与 `judge_profile`。
- 实证：native run manifest
  `outputs/runs/mem0/locomo/smoke/native/mem0-locomo-native-s1/manifest.json` 显示
  `config_track=native` 且 `method.config.embedding_provider=huggingface`、
  `embedding_model=sentence-transformers/all-MiniLM-L6-v2`、dim 384、
  `vector_store_provider=qdrant`；`answer_reader.answer_parameters` 确为 bundle 值
  （temp 0.0/max_tokens 4096/top_p None，与 `mem0_native_prompts.py:689-692` 对上）。
  即 **native 覆盖只落在 readout，build 仍是 controlled MiniLM**。
- judge fallback 无痕：`cli/commands.py:213-226`——`judge_profile=None`（MemoryOS）
  时静默用框架 judge，无 `judge=framework_fallback` 落盘。
- **特查结论：current `config_track=native` 会把 partial-native 过度标成
  full-native**。三家现 native 格全部实际为 readout-only（mem0/lightmem 的
  embedding_ref 只是文档字符串；memoryos 明写
  `build-profile-not-yet-wired`，`config_track.py:86`），且 Mem0 官方 harness
  answer/judge=gpt-5、LightMem qwen 口径 judge=deepseek-chat 均被框架锁改为
  gpt-4o-mini——manifest 里没有任何字段表达这两层降级。

### 5.2 既有产物盘点与保留/重标建议

主树 `outputs/runs/` 共 57 个 manifest（只读盘点，未改动）。三家相关：

- **unified 产物**（保留，docs 侧重标 `controlled_embedding_v1`，不改 outputs
  文件——outputs 受保护且 manifest 参与 resume 指纹）：2026-07-09 系列
  `locomo/membench/halumem/longmemeval` per-method smoke（旧 layout 无 track 段）；
  新 layout `smoke/unified/` 系列（mem0 五 benchmark s1/s2/par2；lightmem 同型
  含 beam 100k/10m）；`lightmem/longmemeval/s-cleaned/formal/
  ...-official_full-{1b2cf0d9,3e04bd62}`。
- **native 产物**（保留，但必须重标 `partial_native(readout_only) +
  controlled_embedding_v1 build`，不能充当 product-default native 证据）：
  `mem0-locomo-native-s1`、`mem0-lme-native-s1-s-cleaned`、
  `mem0-beam-native-s1-100k`、`lm-locomo-native-smoke1`、
  `lm-lme-native-smoke1-s-cleaned`。
- MemoryOS：当前无 native run；unified smoke 产物按上述 controlled 口径保留。
  注意 MemoryOS（及待裁的 LightMem）controlled 值与 product-default 值**重合**
  （同一 MiniLM），这批产物在事实上同时满足两个身份——建议架构师允许
  双重标注（`controlled_embedding_v1` = `product_default` coincident），
  避免为纯标签差异重烧 API；这是建议，不是裁决。

### 5.3 迁移/复证面（不含预算数字）

| | Mem0 | LightMem | MemoryOS |
|---|---|---|---|
| 是否必须重建 memory | **是**：embedding provider/model/dim/费用路径全变（本地 MiniLM/384 → 远端 text-embedding-3-small/1536） | 待 P1：若裁 MiniLM 为 pinned default → **否**（现 build 即是）；若裁 openai 系 → 是 | **否**：签名默认与现 TOML 同一模型身份 |
| 最小实现改动面 | TOML 三键（provider/model/dims）+ `.env` 已有 OpenAI key；adapter openai embedder 分支已存在（`mem0_adapter.py:422-424`），从未被配置走过 → 需定向测试激活 | 待裁；若 MiniLM 则仅身份标注 | 仅身份标注（TOML 值不变；`sentence-transformers/` 前缀与裸名的等价性建议在 manifest 身份里显式记录） |
| readout 重跑 vs 全链路重跑 | build+retrieve+answer+metric 全重跑（build 轴变化，B10 二分推论） | 待裁；MiniLM 口径下零重跑 | 零重跑（分数不变，只补身份） |
| 必须重开的门 | B8+（新增远端 embedding 网络/费用面，需 timeout/retry/降级语义取证——openai embedder 分支此前未审）、B11（两轨 smoke 重跑）；RetrievalEvidence 逐题 artifact 在新 build 复产；B3（run_id 过滤逻辑不随 embedder 变）、B4（embedding 不改 content 渲染）、B5/ADD-only 结论（embedding 无关）可继承结论但 smoke 证据要新 run 佐证 | 待裁 | 无需重开；仅文档/manifest 勘误 |
| resume 影响 | 新增 manifest 身份字段后，旧 run_id 因 manifest 精确 `==` 比较不可 resume（旧 smoke 均已完成，可接受，迁移卡须写明） | 同左 | 同左 |

### 5.4 manifest 最少新增静态 identity 字段建议

- `embedding_track ∈ {product_default, controlled_embedding_v1, benchmark_native,
  reproduction_variant}`；
- `embedding_provider / embedding_model / embedding_revision（或本地模型目录
  sha256）/ embedding_dimension / embedding_normalization / embedding_instruction /
  embedding_distance`（三家 TOML 现有字段形态不一致：mem0=provider+model+dims、
  lightmem=embedding_model_path、memoryos=embedding_model_name，均无
  normalization/instruction/distance——归一字段名后由 adapter 静态填值）；
- `implementation_variant ∈ {product, reproduction:<name>}`；
- `native_scope ∈ {none, readout_only, build_and_readout}`（替代裸
  `config_track` 布尔语义）；
- `judge_source ∈ {official_parity, framework_fallback}` 与
  `answer_model_override / judge_model_override`（官方非 gpt-4o-mini 时标
  `FRAMEWORK_MODEL_OVERRIDE`）。

## 6. 需要架构师勘误的文字清单（只列不改）

| # | 位置 | 问题 |
|---|---|---|
| E1 | `src/memory_benchmark/methods/mem0_adapter.py:108`（另 `:164` 同类表述） | docstring 称 infer=True 启用"ADD/UPDATE/DELETE 算法"；vendored 2.0.4 的 `_add_to_vector_store` 是 additive ADD-only + hash 去重（`main.py:699-863`），ingest 无 UPDATE/DELETE。 |
| E2 | `src/memory_benchmark/methods/config_track.py:53` | `embedding_ref="lightmem.repo_default.all-MiniLM-L6-v2"` 名不副实：repo schema 顶层默认是 `None`（`configs/base.py:65`），MiniLM 是 backend 层 fallback（`huggingface.py:16`）+ experiments 实配，不是 repo 顶层默认。`:54` `hyperparam_ref="lightmem.repo_default"` 承接同一混淆。 |
| E3 | `configs/methods/mem0.toml:5-7` 注释 | "top_k=20 为 mem0 官方默认"（签名默认属实，`main.py:1130`）但未点明 memory-benchmarks 入口默认是 200（`run.py:687,963`），而 `config_track.py:73` `hyperparam_ref="mem0.memory-benchmarks.repo_default"` 恰指向 harness 口径——两处并读会自相矛盾，建议注释区分"产品签名默认 20 / harness 入口默认 200"。 |
| E4 | `src/memory_benchmark/methods/config_track.py:91-101` + manifest 链 | native bundle 的 `embedding_ref/hyperparam_ref` 是纯文档字符串、不生效也不落盘；配合裸 `config_track=native` 造成 §5.1 的过度标注。建议按 §5.4 字段化。 |
| E5 | `configs/methods/memoryos.toml:3` 注释 | "参数取 memoryos-pypi 官方默认（memoryos.py:30-44）"——`embedding_model_name` 实填限定名 `sentence-transformers/all-MiniLM-L6-v2`，签名字面默认是裸名 `all-MiniLM-L6-v2`（`memoryos.py:42`）；解析同模型但文本非逐字默认，建议注释补一句"限定名=裸名同模型"，并在 manifest 身份中显式记录该等价。 |
| E6 | `docs/workstreams/ws02.7-method-track/notes/m1-memoryos-evidence.md`（机械 diff 段） | chromadb 此前只有机械 diff 记录；本卡升级为 `ALGORITHM_VARIANT`（query-time LLM 抽词回归、持久化时序变更、heat-LTM 护栏丢失、capacity 死参数），建议 m1 note 增补指针到本文 §4，防后续误当纯 storage variant 接入。 |

## 7. 来源待溯 / 停工点

- **P1（停点，LightMem）**：pinned product-default embedding 无顶层可运行默认；
  候选锚 = `huggingface.py:16` backend fallback vs paper/experiments 一致 MiniLM。
  需架构师裁定锁定值与引用命名；本卡不代裁。
- **S1**：HF 模型（三家全部本地 MiniLM 路径/裸名）无 `revision=` 参数；本地目录可
  hash 锁定，Hub 名不锁 → 建议 manifest 记本地模型目录 hash（§5.4）。
- **S2**：MiniLM encode 是否模型内建 L2 normalize 静态不可判（禁联网核对模型卡）
  → SOURCE_UNDETERMINED；不影响本卡结论（cosine 度量下等价）。
- **S3**：Mem0 native judge prompt 逐字全文 parity 未跑（仅关键段抽查命中）；
  若架构师要 100% parity 结论需另做逐字比对。
- **S4**：Mem0 memory-benchmarks 的 cloud backend 是否曾被本项目任何 run 使用——
  静态不可判（默认 oss；本项目 adapter 不经 harness），仅作口径警示。
- **S5**：LoCoMo 官方 per-speaker vs combined 检索模式对应 paper 数字的归属未在
  vendored 资产中明示（readme 报告 combined limit=60）；框架现走 combined，
  native 复刻若追 per-speaker 需架构师定。
- **S6（MemoryOS）**：eval 的 faiss index 类型未逐行展开（"eval 距离=IP"按同族
  推断）→ SOURCE_UNDETERMINED；paper 超参（STM=7、MTM=200 等）沿用 m1 note 的
  PDF 页码锚，本卡未重开 PDF。
- **S7（MemoryOS）**：chromadb clamp cosine 与 pypi 可负内积在阈值 0.1 过滤下的
  数值等价度未做运行实证（纯静态卡）；chromadb capacity 死参数的运行时后果同为
  静态结论。
- **S8**：MemoryOS/LightMem 的 vendored 依赖 pin 不对称：pypi
  `requirements.txt` 锁 `sentence-transformers==5.0.0`，chromadb 未锁；
  manifest 身份建议一并记录 sentence-transformers 库版本。

## 8. 施工报告

- worktree：`/Users/wz/Desktop/mb-actor-dual-track-audit`；
  branch：`actor/dual-track-identity-audit`。
- 改动：仅本 note。
- 分工：3 个只读 subagent 并行一手取证（Mem0=Opus 4.8、MemoryOS=Opus 4.8、
  LightMem=Sonnet 5）；主 actor（Fable 5）负责框架侧审计 D 全部一手取证、
  subagent 承重锚点逐个复核（mem0 embeddings/llms 默认、docker server 同 core、
  gpt-5 入口默认、LightMem backend fallback / core import / 本地 VectorRetriever、
  MemoryOS 双版构造签名、adapter vector_store 与 openai embedder 分支）、矛盾
  整合与本文全部结论。
- 自检：`uv run pytest -q tests/test_documentation_standards.py` + `git diff --check`
  （尾行见完成报告）。
- 偏差/停工点：P1（LightMem product-default 需架构师裁定）；其余见 §7。
