---
id: ws02.5
parent: ws02
status: open（P0，5×5 真实 smoke 的前置门；2026-07-08 用户提出）
created: 2026-07-08
---
# ws02.5 Method 接口保真审计（5×5 smoke 前置门）

## 为什么有这个 workstream（第一手发现，别只当 MemoryOS 个例）

2026-07-08 用户提出核心问题：**method adapter 注入/检索记忆时，用的是 method
官方仓库里的哪种接口？** 很多 method 仓库同时有两类：

- **通用产品接口**（`pip install` 得到的那套，benchmark 无关）——例：
  `MemoryOS-main/memoryos-pypi/`（`memoryos.py`/`retriever.py`/`updater.py`）。
- **某 benchmark 专用的评测实现**（为跑某篇论文的某 benchmark 写的独立副本，
  常自带该 benchmark 数据 + 打分）——例：`MemoryOS-main/eval/`
  （`main_loco_parse.py` + 烤进的 `locomo10.json` + `evalution_loco.py`，是
  LoCoMo 专用引擎副本，与 pypi 是**两套独立代码**，非同一份）。

**第一手证据（MemoryOS，一个例子而已）**：现有
`src/memory_benchmark/methods/memoryos_adapter.py:3` docstring 自述"包装 MemoryOS
官方 `eval/` 目录中的 LoCoMo 评测实现"。即我们现在用的是 **LoCoMo 主场版引擎**，
不是通用 pypi。**用户明确：不要过拟合 MemoryOS——5 个（未来 10 个）method 全部
都要查**，其他 method 仓库有没有类似的 benchmark 专用目录尚未核实。

## 裁决（架构师，用户认可）：一律用通用产品接口

**所有 method 跨全部 benchmark 统一用通用产品接口注入/检索，不用任何 benchmark
专用评测实现。** 三条理由：

1. **公平/可比**：benchmark 专用实现可能带该 benchmark 的调参/prompt，用它 →
   该 method 在该 benchmark 有主场优势，分数与它在别的 benchmark 上不可比。
   跨 benchmark 比较必须同一个接口跑遍 5 个 benchmark。
2. **代表性**：通用产品是真实用户 `pip install` 得到的东西，才代表"这个 method"
   的真实水平。
3. **benchmark 专用目录恰是我们框架要替换的部分**：它自带数据加载 + 打分，
   而数据加载和打分是**我们框架的活**。benchmark 专用目录只作**只读参考**
   （看作者官方用法/参数：top_k、各记忆层容量、注入格式），然后把通用引擎按
   官方参数配好。

## 审计范围（每个 method 逐项，产出下方接口文档）

对 Mem0 / MemoryOS / A-Mem / LightMem / SimpleMem（未来 +MemOS/Letta/Cognee/
LangMem/Supermemory）逐个核：

- **(a) 接口保真**：adapter 现在调的是通用产品接口还是 benchmark 专用实现？
  仓库里有没有 benchmark 专用目录（如 `eval/`、`experiments/`）？若 adapter 用了
  专用实现 → 评估迁移成本（diff 专用 vs 通用引擎：是"算法不同的 fork"要重写，
  还是"同引擎不同配置"改指向+对齐参数即可）。
- **(b) 注入保真**：ingest 是否按 method 官方用法注入（粒度、格式、是否触发
  method 的记忆构建/更新流程）。
- **(c) 检索完整**：retrieve 回来的 `formatted_memory` 是否覆盖 method 核心
  算法的**全部记忆层**——例 MemoryOS 短期+中期+长期(个性化)都要回；Mem0 的
  记忆；A-Mem 的 note+link；LightMem；SimpleMem 窗口。**不完整 = smoke 跑通但
  产出垃圾 = 成本表和全量全失真**。
- **(d) 原生无 retrieve 接口的情况**：确有 add-only 的 method 原生无独立 retrieve
  API，此时 adapter 层必须封装出一个返回完整 `formatted_memory` 的 retrieve，
  且封装忠于 method 内部检索逻辑（不自造检索算法）。
- **(e) formatted_memory 落盘**：每次检索内容记进 artifact（conversation-QA
  路径已有 `prediction.py:2624`，须确认 operation_level 路径也记、且完整）。

## 交付物：Method 接口文档（注入 + 检索，5→10）

产出一份 `docs/reference/method-interface-inventory.md`（或扩充既有同名文件），
每个 method 一节，含：注入 API（函数签名 + 粒度 + 官方参数）、检索 API（函数
签名 + 返回的记忆层 + top_k）、`formatted_memory` 拼装口径、通用 vs 专用接口
裁定与证据行号。这是"下一任架构师/actor 快速上手"的关键文档。

## 与 5×5 smoke 的关系（门）

**这是 5×5 真实 smoke 的前置门**：接口不保真、记忆不完整时跑 smoke 是浪费预算
（数字不可信）。顺序：5 个 adapter 完工 → 本审计 → 5×5 smoke → 成本表。
不阻塞 fake 全链路（fake 不烧 API，可继续）。

## 当前断点

- 2026-07-09（actor WorkBuddy/GLM-5.2，完成 config 归一化方案 B）：架构师裁定
  方案 B（参数进 TOML + adapter 从 config 读，src/ 改动授权，不碰 third_party）。
  一次整批做完 4 项，逐项 commit，基线 ≥804 全程不跌破。**交架构师复跑验收 +
  第一手核对**。
  - **T1 mem0**（commit `4d077bd`）：mem0.toml top_k 200→20、embedding
    text-embedding-3-small→sentence-transformers/all-MiniLM-L6-v2、dim 1536→384、
    加 embedding_provider=huggingface（两 section）；mem0_adapter.py Mem0Config 加
    embedding_provider 字段、smoke/official_full 默认值改 repo 默认、build_backend_config
    按 provider 派生（huggingface 不带 api_key/openai_base_url）。**验 Qdrant**：真实验证
    SentenceTransformer 384 维 + Qdrant 按 384 建表/检索正常（score=0.8593 命中）。
    focused 85 passed。
  - **T2 amem**（commit `2d80c6b`）：amem_adapter.py 停用硬编码
    AMEM_GPT4O_MINI_CATEGORY_K（改名 AMEM_PAPER_TABLE8_GPT4O_MINI_K 转注释留档），
    _retrieve_k_for_question 统一返回 config.retrieve_k（repo 默认 10）；amem.toml 不变
    （retrieve_k=10 已是 repo 默认）。paper Table8 值（cat1/2/5=40、cat3/4=50）转注释 +
    inventory 留档。focused 19 passed。
  - **T3 lightmem**（commit `8a7dada`）：lightmem.toml 加 extract_threshold=0.5
    （repo 默认 base.py:58）、offline_update_score_threshold=0.8（README/tutorial）两
    section；lightmem_adapter.py LightMemConfig 加两字段 + (0,1] 校验，:432/:1016 从
    config 读（不再硬编码 0.1/0.9）。focused 56 passed。
  - **T4 simplemem**（commit `0728500`）：simplemem.toml embedding_model_path
    Qwen3-0.6B→models/all-MiniLM-L6-v2、dim 1024→384（两 section）；provider 已是
    sentence-transformers-local（adapter:153）无需改；算法参数保持 repo 默认。
    adapter 错误提示通用化（去 Qwen3 硬编码）。**验 LanceDB**：all-MiniLM 本地加载 +
    384 维确认；LanceDB 真实建表需 simplemem 完整环境（lancedb 未在主 venv），留 smoke，
    但 Qdrant 384 建表已通过（同类向量库机制）。focused 40 passed。
  - **T5 token 落盘**：上轮核实已实现（injected_memory_context_tokens 各 adapter 上报 +
    collector + analysis + prediction.py:2610），无需新增。
  - **全量**：`uv run pytest -q -m "not api"` = **804 passed, 3 deselected, 2 warnings,
    4 subtests passed**；`compileall` exit 0。基线 804 全程不跌破。
  - **第一手 repo 默认值核实**：mem0 top_k=20（main.py:1020/1130 `top_k: int=20`）、
    amem retrieve_k=10（test_advanced_robust.py:348 default=10，底层 k=5 被覆盖不生效）、
    lightmem extract=0.5（base.py:58）/offline=0.8（README:325+notebook）、simplemem
    embedder all-MiniLM 384（本地 models/all-MiniLM-L6-v2）——全部属实。
  - **下一步**：架构师复跑 804 + 第一手核对（重点 embedder 维度切换后 Qdrant/LanceDB
    检索正常、repo 默认值属实、adapter provider 从 config 读无残留硬编码）。

- 2026-07-09（actor WorkBuddy/GLM-5.2，**停工**）：config 归一化写任务开工即遇
  **系统性 plan-vs-事实冲突**——5 个子任务里 3 个的 paper 对齐值在 **adapter
  硬编码、不在 toml**，按定稿"改 toml 不改 adapter"完不成归一化。**未 commit**
  （未改任何文件，仅做第一手核实）。基线 `uv run pytest -q -m "not api"` =
  **804 passed, 3 deselected, 2 warnings, 4 subtests passed**（本机已跑）。
  等待架构师裁定执行方式（见末尾"待裁定"）。第一手核实如下：

  **【T1 mem0】top_k 可改 toml；embedding 必须改 adapter（provider 冲突）**
  - top_k：toml 现值 200，repo 默认 20（`mem0/memory/main.py:1020/1130` 均
    `top_k: int = 20`，`tests/test_main.py:114` 注释"top_k default is now 20"，
    `skills/mem0/SKILL.md:141` v3 defaults top_k=20）。**改 toml 即可，无冲突**。
  - embedding：toml 现值 `text-embedding-3-small`/1536，要换 `all-MiniLM-L6-v2`/384。
    但 `mem0_adapter.py:383-390` embedder 配置 **`"provider": "openai"` 硬编码**：
    `"embedder": {"provider": "openai", "config": {"model": config.embedding_model,
    "embedding_dims": config.embedding_dimensions, "api_key": ...}}`。若只改 toml
    model 名为 all-MiniLM 而 provider 仍 openai → mem0 会用 OpenAI API 调
    "sentence-transformers/all-MiniLM-L6-v2" → model not found 崩。**换 MiniLM
    必须同时改 adapter provider openai→huggingface**（参考 lightmem_adapter.py:418
    `"model_name": "huggingface"`）。config profile 无 embedding_provider 字段，
    provider 仅在 adapter 硬编码。→ 与定稿"不改 adapter"冲突。

  **【T2 amem】repo 默认=10 已在 toml；paper Table8 值在 adapter 硬编码映射**
  - 第一手定 repo 默认：**10**。证据：`test_advanced_robust.py:348`
    `parser.add_argument("--retrieve_k", type=int, default=10)`、`:176`
    `retrieve_k: int = 10`、README:112 `default: 10`。底层
    `memory_layer_robust.py:430` `find_related_memories_raw(query, k: int = 5)`
    的 5 是方法签名默认，但被上层 `test_advanced_robust.py:112`
    `retrieve_memory(keywords, k=self.retrieve_k)`（=10）覆盖、不生效。→ repo 默认=10。
  - 当前 amem.toml `retrieve_k=10` **已是 repo 默认**（仅作 fallback）。
  - 但 paper Table8 的 per-category k 在 **adapter 硬编码映射**
    `AMEM_GPT4O_MINI_CATEGORY_K = {"1":40,"2":40,"3":50,"4":50,"5":40}`
    （amem_adapter.py:77-83），`_retrieve_k_for_question`（:926-936）当 question
    有 category 命中映射时用 paper 值（40/50），否则 fallback 到 toml retrieve_k。
    → "从 paper Table8 → repo 默认"需改 adapter 去掉/绕过该映射，改 toml 无效
   （toml 已是 repo 默认 10）。→ 与定稿"改 toml 不改 adapter"冲突。

  **【T3 lightmem】两参数均在 adapter 硬编码、不在 toml**
  - `extract_threshold=0.1`：`lightmem_adapter.py:415` 硬编码（传给 LightMemory
    构造 dict）。repo 默认 0.5（`configs/base.py:58` `default=0.5`、PKG-INFO:601
    表 `extract_threshold | 0.5`）。lightmem.toml **无此字段**。
  - `offline_update score_threshold=0.9`：`lightmem_adapter.py:999`
    `backend.offline_update_all_entries, score_threshold=0.9` 硬编码。third_party
    函数签名默认 0.9（`lightmem.py:539` `score_threshold: float = 0.9`），但官方
    README/tutorial 用 0.8（PKG-INFO:417、notebook 2840/13740
    `offline_update_all_entries(score_threshold=0.8)`）。lightmem.toml **无此字段**。
  - config profile 无 extract_threshold/score_threshold 字段（grep
    src/memory_benchmark/config 无匹配）。→ 改 toml 无法完成；必须改 adapter
    硬编码值（0.1→0.5、0.9→0.8）或加 toml 字段+改 adapter 从 config 读。→ 与
    定稿"改 toml 不改 adapter"冲突。

  **【T4 simplemem】无冲突，改 toml 即可**
  - toml 现值 `models/Qwen3-Embedding-0.6B`/1024，要换 `all-MiniLM-L6-v2`/384。
    `simplemem_adapter.py:153` `"embedding_provider": "sentence-transformers-local"`
    （已是本地 provider，非 openai 硬编码），`:297-298` 从 config 读
    EMBEDDING_MODEL/EMBEDDING_DIMENSION。改 toml model_path+dimension，provider
    不变，应能工作。**唯一完全无冲突的 embedding 归一化**。

  **【T5 框架 token 落盘】已实现，无需新增**
  - `injected_memory_context_tokens` 字段已在 `observability/efficiency/entities.py:157`
    定义；各 adapter retrieve 时上报（mem0:894/973、lightmem:711、memoryos:792、
    amem:486）；collector 记录（collector.py:53/179/190）；analysis 汇总
    （efficiency.py:80/126-128）；answer 路径 prediction.py:2610 也记
    (`_count_answer_context_tokens`)。→ formatted_memory token 数已落盘，T5 无需改动。

  **【冲突性质】** 定稿"归一化是改 TOML（不是改 adapter 传参、不改 third_party），
  低风险"基于"paper 对齐值就在 TOML"前提（举的例子 mem0.toml:6 top_k=200、
  simplemem.toml:6 Qwen3-1024 确实在 toml）。但第一手核实：mem0-embedding 的
  provider 在 adapter 硬编码、amem/lightmem 的 paper 值在 adapter 硬编码，均不在
  toml。3/5 子任务改 toml 完不成归一化。

  **【待裁定】** 这 3 个冲突子任务的执行方式（actor 不擅自扩大改动范围，停工等裁）：
  - 方案 A：授权改 adapter（mem0 改 provider openai→huggingface；amem 去掉
    AMEM_GPT4O_MINI_CATEGORY_K 映射统一用 retrieve_k=10；lightmem 改两处硬编码值）。
    最直接，但定稿"不改 adapter"需架构师显式放宽。
  - 方案 B：加 toml 字段 + 改 adapter 从 config 读（lightmem 加 extract_threshold/
    offline_update_score_threshold；mem0 加 embedding_provider；amem 加开关控制是否
    用 per-category 映射）。更"配置化"，但改动更大、需改 config dataclass。
  - 方案 C：架构师重判 amem（toml retrieve_k=10 已是 repo 默认，是否接受 per-category
    映射保留=接受 paper 对齐作主配置？）。
  无冲突的 T1-mem0-top_k、T4-simplemem、T5 是否先做？一并等裁。

- 2026-07-09（架构师 Opus 4.8 验收 P1 MemoryOS）：**通过**。本机复跑
  `uv run pytest -q -m "not api"` = **804 passed, 0 failed**。第一手核对：
  **T3 剥离全 5 层 ✅**——`_assemble_memoryos_formatted_memory`（memoryos_adapter
  .py:1220）忠实复刻官方 `get_response`（memoryos.py:268-302），覆盖 短期
  history + 中期 retrieved_pages + 长期 profile + user_knowledge +
  assistant_knowledge；**无污染写 ✅**——retrieve 跳过 step-10 `add_memory`。
  **三个待裁定的裁决**：
  - **① LoCoMo→session、LongMemEval→pair 粒度特化 = 采纳**。第一手成立：LoCoMo
    `normalized_role=None`（role=speaker 名），pair 按 `role=="user"` 锚失效；
    与既有 LightMem/A-Mem 按 benchmark 设粒度的模式一致。
  - **② 检索触发 mid_term heat/`N_visit` 更新 = 保留（actor 做对了，架构师
    plan 那句"记忆状态不变"是错的、已更正）**。用户点破 + 第一手证实：这是
    MemoryOS 算法机制，作者自己的 eval `search_sessions_by_summary`
    （`eval/mid_term_memory.py:236-237` `N_visit+=1`/`last_visit_time`、`:265
    rebuild_heap`）就这么做。**契约只锁"不写新内容污染"，不锁 heat 变化**。
    plan-memoryos-migration.md 的 T3 + §3 已更正。
  - **③ 804 vs 892（-88）= 接受**。旧 test_memoryos_adapter.py eval-专属测试
    （~140）被 pypi 测试（51）合理替代（892-140+51+1=804），非功能 regression；
    但 pypi 路径测试数（51）后续写接口文档时复核是否有覆盖缺口。
  **下一步**：接口文档汇总（5 method）；P2 A-Mem 文档留痕；然后 5×5 真实 smoke
  （待预算）。**ws02.5 迁移/修复清单已全清（P0+3×P1+Mem0 不动）。**
- 2026-07-08（actor WorkBuddy/GLM-5.2，完成 P1 迁移）：MemoryOS eval→pypi。
  T1 pypi 引擎命名包加载（`memoryos_pypi_vendor`，importlib spec_from_file_location；
  目录名含连字符无法作包名）+ per-conversation 物理隔离（独立 Memoryos 实例，
  user_id+data_storage_path）+ `build_memoryos_source_identity` 改 hash
  memoryos-pypi/*.py（12 文件）；T2 `add_memory` pair/session 粒度（registry 按
  benchmark 设：LongMemEval→pair，LoCoMo→session；LoCoMo role=speaker 名，pair
  聚合按 role=="user" 锚失效，与 LightMem/A-Mem 既有模式一致）+ orphan/dangling
  空串容错（第一手验证通过）；T3 retrieve 剥离 `get_response` 步骤 1-7 全层
  formatted_memory（短期 history + 中期 retrieved_pages + 长期 profile +
  user_knowledge + assistant_knowledge）+ 无写副作用测试锁（`add_memory` 未被调
  + 记忆内容前后不变）；T4 pypi 官方默认参数（10/2000/7/5.0）+ 字段改名
  （heat_threshold→mid_term_heat_threshold 等）+ runner/TOML 同步；T5 focused
  51 passed + 受影响测试修复（registered_prediction/official_smoke_profiles/
  config_profiles/locomo_smoke/locomo_full_runner/documentation）；T6
  method-interface-inventory.md MemoryOS 节更新。全量 `uv run pytest -q -m "not api"`
  = **804 passed, 0 failed, 3 deselected, 4 subtests passed**（compileall OK）。
  commit `c73d4d5`。**804 vs 892 差 88**：旧 test_memoryos_adapter.py eval-专属
  测试（~140 含 parametrize）被 pypi 测试（51）合理替代（892-140+51+1=804），
  非功能 regression。**待架构师裁定**：①804<892 测试数下降是否接受（迁移本质
  替换 eval→pypi，旧 eval 测试不再适用）；②`retrieve_context` 内部
  `search_sessions` 会更新 mid_term 访问统计（N_visit/last_visit_time/H_segment）
  并 save——MemoryOS 检索算法固有行为（LFU/heat），非 add_memory 写副作用，不改
  third_party 无法消除；T3 测试锁按"add_memory 未调 + 记忆**内容**不变"验收，
  mid_term 访问统计变化如实记录未断言。**下一步**：架构师复跑验收 + 第一手核对
  （重点 T3 剥离是否全层 + 零写副作用、T1 隔离）。
- 2026-07-08（架构师 Opus 4.8 验收 P1 LightMem）：**通过**。本机复跑
  `uv run pytest -q -m "not api"` = **892 passed, 0 failed**。**第一手核实迁移
  忠实**：官方 `lightmem.py` `retrieve()`（:644-707）内部就是
  `text_embedder.embed(query)` → `embedding_retriever.search(return_full=True)`
  →（仅当传 `boundmem_tags` 才 `filter_by_tags`，默认不过滤）→ 格式化成
  `f"{time_stamp} {weekday} {memory}"`。所以 adapter 直接调 `search(return_full=
  True)`（:1035）① 用的是同一个官方 search 组件；② 默认参数下无隐藏过滤被跳过；
  ③ answer prompt 用 `_format_lightmem_memory_as_official_retrieve`（:1555）还原
  官方 `{ts} {wd} {mem}` 格式（对齐官方 :701），不偏离。两路径统一 list[dict]
  （F1 解决），删自复刻 `_cosine_similarity`。**Step1 等价 gate 我复核结构成立**
  （retrieve==search 包一层），数值等价采信 actor 记录的详细 diff（未独立重演
  cosine 数值）。**残留（非阻塞）**：若将来用到 `boundmem_tags`，adapter 须补
  `filter_by_tags`（当前 benchmark 不用）。**下一步**：MemoryOS eval→pypi 迁移
  ——**plan 已产出** [plan-memoryos-migration.md](plan-memoryos-migration.md)
  （架构师第一手：pypi Memoryos 文件式隔离 + add_memory pair 注入 + **从
  get_response 剥离纯检索、全层 formatted_memory、无写副作用**），待派 actor
  （写任务串行）；接口文档汇总；P2 A-Mem 文档留痕。
- 2026-07-08（actor workbuddy+GLM5.2，完成 P1 迁移）：LightMem 统一 retrieve。
  Step1 gate 通过（自复刻 `_retrieve_locomo_memories` get_all+手算cosine vs
  官方 `VectorRetriever.retrieve` retrievers.py:111-132 逐行等价：候选集同
  qdrant.get_all、cosine 公式数学一致、排序截断一致，无主场优势）；Step2
  `_retrieve_locomo_memories`→`_retrieve_with_payload` 改调官方
  `embedding_retriever.search(return_full=True)` 拿带 payload 结果，retrieve()
  LongMemEval/LoCoMo 两路径统一返回 list[dict]（F1 解决），LongMemEval answer
  prompt 用新增 `_format_lightmem_memory_as_official_retrieve` 还原官方
  `'{ts} {wd} {mem}'` 格式（不偏离 run_lightmem_gpt.py:186），删
  `_cosine_similarity`，retrieval_profile 统一 `lightmemory_retrieve`。focused
  lightmem 33 passed，全量 892 passed（基线不跌破）。commit `63ccba2`。
  **下一步**：架构师复跑验收；P1 MemoryOS eval→pypi 待派。
- 2026-07-08（架构师 Opus 4.8 验收 P0）：**通过**。本机复跑 `uv run pytest -q
  -m "not api"` = **892 passed, 0 failed**（与 actor 一致）；第一手核对改动忠实：
  官方 `answer_generator.py:85-111` `_format_contexts` 确为 6 字段
  （Content/Time/Location/Persons/Related Entities/Topic）、**不含 keywords**，
  adapter `_format_simplemem_contexts` 逐行等价，actor 未画蛇添足加 keywords、
  且 dedup（unified 复用 native formatter，两口径一致）。**下一步**：LightMem
  P1（含 Step1 等价 gate）+ MemoryOS eval→pypi（架构师写 plan 中）。
- 2026-07-08（actor **WorkBuddy/GLM-5.2**，完成 P0 修复；**身份更正**：此前 actor
  自标"Claude Sonnet"有误——实际由 GLM-5.2 驱动、产品层 WorkBuddy，架构师照搬其
  自标未核实，一并纠正。SimpleMem 审计 + P0 写任务均为同一 WorkBuddy/GLM-5.2）：
  SimpleMem F1——
  `_format_simplemem_memory` 改为复用 `_format_simplemem_contexts`，覆盖官方
  `AnswerGenerator._format_contexts` 全部 6 字段（lossless_restatement+timestamp
  +location+persons+entities+topic），unified/native 同口径不丢 Symbolic 层；
  改 `test_simplemem_adapter.py` 旧格式断言 + 新增 Symbolic 字段覆盖测试。
  focused 13 passed，全量 892 passed（基线 891 +1）。commit `3e177c3`。**下一步**：
  架构师复跑验收；P1 MemoryOS eval→pypi / P1 LightMem 统一 retrieve 待派。
- 2026-07-08（架构师 Opus 4.8 建档）：记录 MemoryOS `eval/` vs `memoryos-pypi`
  第一手发现 + 全 method 审计裁决。**下一步**：逐 method 审计（可先抽查
  MemoryOS 出样例，再派 actor 按上方 (a)-(e) 清单逐个核 + 写接口文档）。尚未
  开工审计。

## 任务清单

- [x] 架构师建档 + 裁决（2026-07-08）
- [x] 逐 method 接口审计（2026-07-08，Mem0/A-Mem/LightMem/SimpleMem by workbuddy+GLM5.2；MemoryOS by 架构师）+ 架构师验收裁定（见上表）
- [x] 产出 method 接口文档（`docs/reference/method-interface-inventory.md`，
  2026-07-09，WorkBuddy/GLM-5.2 汇总 5 method；架构师验收：抽查 mem0 add:573/
  search:1126、A-Mem add_note:377、SimpleMem retrieve:58 行号全属实）。**待补**：
  每 method 加一个 **hyperparameters 字段**（官方默认值 + paper-vs-repo 差异 +
  用哪个，见下方"超参数政策"）。
- [ ] 迁移/修复（写任务串行）：[x] P0 SimpleMem 补字段（2026-07-08，commit 3e177c3）/ [x] P1 MemoryOS eval→pypi（2026-07-08，commit c73d4d5）/ [x] P1 LightMem 统一 retrieve（2026-07-08，commit 63ccba2）/ [ ] P2 A-Mem 文档留痕
- [ ] formatted_memory 全路径完整落盘核对

## 超参数政策（架构师裁定，2026-07-09 用户提问后固化）

- **一律用 method 官方【仓库/产品默认】超参数**（通用产品的默认配置，**不是**
  benchmark 专用配置如 eval/ 的调参），跨全部 benchmark 同一套、不 per-benchmark
  调优（调优 = 主场优势，同 ws02.5 接口原则）。实验声明"超参数 = method 官方默认
  + vendored commit"即可。对齐 roadmap 全局约束"用官方 method 参数，成本只靠数据
  规模裁剪、不降 top_k"。
- **paper 声明 ≠ repo 默认 时：优先 repo 默认**。理由：① 代表性（repo 是真实
  用户 `pip install` 得到的）；② 可复现（repo 默认是可钉到 commit 的具体值，
  paper 常不全/含糊）；③ repo 常比 paper 新（作者发表后调过）。**但必须显式
  记录差异**（inventory 的 hyperparameters 字段：repo 默认值 / paper 值 / 用哪个
  / 为何）。例外：repo 默认明显是占位/bug 而 paper 值才是意图 → 用 paper + 留痕。
- **借鉴资料**：① method README（第一手,常写推荐默认）；② 既有 memory benchmark
  的配置（`third_party` 里 mem0 memory-benchmarks、LoCoMo/LongMemEval 官方 harness）
  ——但注意它们常是 benchmark 调参，只借来"理解参数含义"，不照搬其调优值；③ 我们
  目标不是复现各 method 论文数（那是它们自己 benchmark 上的），而是 OUR 5 benchmark
  上的公平横比 → 代表性优先。

### 既有 paper 对齐的处置裁定（2026-07-09，用户揭示 + 架构师裁定）

**背景（用户 2026-07-09 揭示）**：4 个既有 method 的 adapter 里，Codex 曾为
**复现各 method 论文/官方评测数据**做过超参数"对齐"（adapter 传参，**未改
third_party 硬编码**，第一手证实 third_party git 干净、`top_k=200` 在
`mem0_adapter.py:157/175`）。actor 审计发现的 4 处差异即此：Mem0 top_k
20→200、A-Mem k repo 5/10→paper Table8、LightMem extract 0.5→0.1 / offline
0.8→0.9。

**裁定：5×5 矩阵改回 repo 默认（recommend，需用户确认研究框架）**：

- **决定性理由**：MemoryOS 迁移（commit c73d4d5）**已经**把它改回 pypi repo
  默认（弃 eval/ 的 7/200）。所以现在 5 个 method **不一致**了——MemoryOS=repo
  默认，其余 3 个=paper 对齐。**不一致 = 不公平横比**。要么全 repo 默认、要么
  全 paper 对齐；按超参数政策（代表性/可比/repo 优先）+ MemoryOS 已是 repo
  默认 → **全部统一到 repo 默认**。
- **paper 对齐值不删、转为"论文复现验证配置"留档**（inventory hyperparameters
  字段已记 repo/paper 两值）——它是"我们 harness 能复现论文数"的验证证据，对
  导师汇报有价值，只是**不作 5×5 矩阵的默认配置**。
- **LLM/embedder 例外**：全项目统一 `gpt-4o-mini`（Mem0 repo gpt-5-mini /
  SimpleMem gpt-4.1-mini / A-Mem backend 等差异）是**刻意的公平选择**（比的是
  记忆质量不是 LLM 质量）+ 成本，**保持统一、不回退**，留痕即可。embedder 暂
  保持各 method repo 默认（与算法耦合），是否统一另议。
- **⚠ 需用户确认的研究框架点**：若你要"复现论文数"作为对导师的**主叙事**，则
  反过来（矩阵用 paper 对齐、repo 默认作旁证）。我按 roadmap 既定目标（公平
  5×10 smoke 矩阵 → 成本表）**推荐前者（矩阵=repo 默认）**，你拍。

### 定稿（2026-07-09 用户确认，config 归一化政策）

一条原则：**统一"通用基座"，保留"算法配置"**（判据：这配置是 method 的贡献本身，
还是底下可替换的通用零件？）。

- **通用基座 → 统一（刻意的公平选择，非 repo 默认，留痕）**：
  - **LLM：只统一"模型名" `gpt-4o-mini`**。**method 内部 LLM 的算法参数（温度等）
    不改、保持 repo 默认**（那是算法的一部分）；**框架的 answer LLM 配置全统一**
    （模型+参数，那是我们的）。
  - **embedder：统一到 `all-MiniLM-L6-v2`**（5 个里 3 个本来就是；只需改 Mem0
    `text-embedding-3-small`→MiniLM、SimpleMem `Qwen3-0.6B`→MiniLM，**逐个验维度**：
    Mem0 1536→384、SimpleMem 1024→384，向量库 dim 要跟着改）。
- **算法配置 → repo 默认，不统一**：top_k / 各记忆层容量 / heat 阈值 / window 等。
  **top_k 不统一**（跨 method 语义不同：MemoryOS retrieval_queue ≠ Mem0 search top_k
  ≠ A-Mem per-category k，强统一是伪对齐 + 破坏机制）。**上下文预算公平靠透明化**：
  记录每次 `formatted_memory` 的 token 数（context-budget 差可见/可分析），不用
  统一 top_k 去掩盖。
- **落地位置 = `configs/methods/*.toml`**（用户定：TOML 存 method 可调超参 + 框架
  参数）。**MemoryOS 的 TOML 已是归一化标杆**（gpt-4o-mini + all-MiniLM + pypi
  默认）。
- **⚠ 架构师定稿修正（2026-07-09，actor 停工上报 + 第一手证实）**：我原定稿说
  "归一化是改 TOML、不改 adapter"——**错了**，前提（对齐值都在 TOML）不成立。
  第一手核实：**3/5 的对齐值硬编码在 adapter，不在 TOML**——mem0 embedder
  `"provider":"openai"` 硬编码（`mem0_adapter.py:384`，换 MiniLM 不改 provider →
  OpenAI API 崩）、amem paper Table8 per-category k 映射硬编码
  （`amem_adapter.py:77-83 AMEM_GPT4O_MINI_CATEGORY_K`）、lightmem `extract 0.1`
  （`:415`）/`offline 0.9`（`:999`）硬编码。**真约束是"不改 third_party"，adapter
  （我们自己的 src/）本就该改**。amem repo 默认 = **10**（`test_advanced_robust
  .py:348`/`README:112` --retrieve_k default=10；`memory_layer_robust.py:430`
  签名 k=5 被 retrieve_k=10 覆盖不生效）。token 落盘**已实现**
  （`injected_memory_context_tokens`，prediction.py:2610），无需新增。
- **裁定：走方案 B（参数进 TOML + adapter 从 config 读）**，理由：符合用户"TOML
  存 method 可调超参"的明确意图 + 完成归一化 + 未来改参只动 TOML（不再改码）。
- **config 归一化写任务清单（一个写任务，方案 B；adapter 改动已授权，仍不碰
  third_party）**：① mem0：TOML `top_k 200→20`、embedder→all-MiniLM(dim 384)
  并加 `embedding_provider`（或按 model 派生），adapter `:384` 从 config 读
  provider（本地模型走 huggingface/sentence_transformers，不再硬编码 openai）；
  ② amem：adapter 停用硬编码 `AMEM_GPT4O_MINI_CATEGORY_K`，改用 config
  `retrieve_k=10`（TOML 已是）统一各 category；paper Table8 值转注释/inventory
  留档；③ lightmem：`extract_threshold`/`offline score_threshold` 移进 TOML
  （repo 默认 0.5/0.8），adapter `:415/:999` 从 config 读；④ simplemem：TOML
  embedder→all-MiniLM(dim 1024→384)，provider 已本地无需改。**每项验维度切换后
  向量库建表 + 检索不崩、基线 ≥804 不跌破。一次整批做，别留半改 TOML。** paper
  对齐值全部转入 inventory hyperparameters 字段留档（已记）。

## MemoryOS 版本裁定（架构师第一手，2026-07-08）

第一手对比 `third_party/methods/MemoryOS-main/` 各版本目录 + README：

- **核心算法在 pypi 与 chromadb 之间一致**：两者核心文件完全相同（`short_term.py`
  / `mid_term.py` / `long_term.py` / `memoryos.py` / `retriever.py` / `updater.py`
  / `prompts.py`），`memoryos-chromadb` 只多一个 `storage_provider.py`（把存储
  后端换成 ChromaDB 向量库）。**同算法、不同存储后端。**
- **mcp 不是另一套引擎**：`memoryos-mcp/` 只有 `server_new.py`——把引擎包成
  MCP Server 对外暴露的**服务层**，供 agent 客户端调用。
- **eval/ 是第三个变体**（研究评测代码，自带 LoCoMo 数据），我们现在的 adapter
  包的就是它（LoCoMo 主场版，本 workstream 要迁走）。

**裁定：用 `memoryos-pypi`（通用产品），不用 mcp / chromadb / eval。四条理由**
（此裁定与用户初步倾向的 chromadb/mcp 不同，架构师据第一手给出）：

1. **mcp 排除**：server/协议层，为 agent 客户端集成而设；我们框架在进程内把
   method 当 Python 库调，用 MCP 要起服务 + 协议往返，纯增复杂度、搅乱隔离/resume。
2. **chromadb 排除（留作后备）**：同算法但多 ChromaDB 依赖 + 需跑向量库；而我们
   每个 conversation 是**小的物理隔离存储**，pypi 的文件式存储（短/中/长期 JSON
   + 内存 FAISS）更适合——**每 conversation 一个目录 = 最简物理隔离 + 删目录即
   clean-retry**。ChromaDB 的可扩展持久向量库是生产规模优点，对我们的小隔离空间
   是过度设计。将来若要逻辑隔离的 scoped-delete，再回头考虑 chromadb。
3. **pypi 最具代表性**：`pip install memoryos` 得到的就是它，符合本 workstream
   "用通用产品接口"的公平原则。
4. **依赖最少、最可复现。**

**迁移前必做（写任务、串行占据，非本裁定范围）**：pypi 引擎与现 adapter 包的
eval/ 引擎是两套代码——先 diff 两者算法差异 + 确认 pypi `Memoryos` 的 add/
retrieve 签名（进接口文档）。本裁定只定"用哪个版本"，迁移工程另派。

## 四 method 审计验收 + 架构师逐条裁定（2026-07-08）

actor = workbuddy+GLM5.2（四开会话并行）。**架构师逐份回第一手核对引用行号**
（不因详尽就信）。审计原文见同目录 `audit-<method>.md`。

| method | 审计结论 | 架构师验收 | 裁定 |
|---|---|---|---|
| **Mem0** | 通用 `Memory` 类，纯 search，零迁移 | 结论对（adapter 用 `search()` :876/882 + `add()`）；**但 actor 论据"Memory 无 answer 方法"有误**——Memory **有** `chat()`（`mem0-main/.../main.py:1791`），只是 adapter 没用它 | **不动**（合规） |
| **LightMem** | LoCoMo 路径自复刻 benchmark 专用检索，LongMemEval 用官方 retrieve | 属实（adapter:1018 docstring 自认"复刻 `search_locomo.py` combined vector search"） | **迁移**：统一走官方 `retrieve()`（扩展其返回 payload 以支持 speaker 分组），消除 benchmark 专用借用 + 解决 F1（两路径返回类型不一）。迁移前先 diff 确认 actor 声称的"逐行等价"（等价=清理；不等价=纠错） |
| **A-Mem** | 用论文复现包 `RobustAgenticMemorySystem`，非产品库 `A-mem-sys` | 属实（`A-mem/README:3-5` 明写"本仓库为复现论文，用请去 A-mem-sys"）；**关键区别**：复现引擎 **benchmark 无关**（无 LoCoMo 调优，adapter 没碰 LoCoMo 专用文件）→ **无 MemoryOS 那种主场优势问题** | **暂保持现状**：复现引擎忠于 A-Mem 算法、无公平问题、迁 A-mem-sys 成本中高（换引擎 + ChromaDB 依赖）。文档记明"用 A-Mem 论文复现包"；低优先 follow-up：核 A-mem-sys 产品算法是否有别 |
| **SimpleMem** | 接口合规；F1：formatted_memory 只拼 2/6 字段 | F1 属实（`_format_simplemem_memory` 只取 `timestamp`+`lossless_restatement`，丢 Symbolic 层 location/persons/entities/topic） | **修**：unified 主线口径下会丢记忆 → formatted_memory 补全 6 字段（小改，高优先） |
| **MemoryOS** | （架构师自审，见上节） | — | **迁移** eval/ → pypi |

**迁移/修复清单（写任务，串行占据；按优先级）**：

- **P0** SimpleMem：formatted_memory 补 4 个 Symbolic 字段（unified 主线必需，小改）。
- **P1** MemoryOS：eval/ → pypi（大，先 diff 两引擎）。
- **P1** LightMem：LoCoMo 统一走官方 retrieve（先验"逐行等价"）+ 统一两路径返回类型（F1）。
- **P2** A-Mem：保持现状 + 文档留痕；低优先核 A-mem-sys 产品。
- Mem0：不动。

**接口保真总账**：5 个 method 中 Mem0 一开始就对；SimpleMem 接口对但 formatted_memory
不全；LightMem 一条路径有 benchmark 专用借用；A-Mem 用复现包但无公平问题；
MemoryOS 用 LoCoMo 主场副本要迁。**只有 MemoryOS 是真"主场优势"问题**，其余是
不同程度的清理/补全。

**Actor 表现评估（workbuddy+GLM5.2）**：审计能力强——详尽、行号翔实、能区分
微妙点（A-Mem 复现引擎 benchmark 无关 vs MemoryOS eval/ 耦合；SimpleMem 三视图
≠ 三记忆层）、抓出真 gap（SimpleMem F1、LightMem 偏离）。**扣分项**：Mem0"无
answer 方法"论据说过头（结论对、证据错）。**结论**：可承接写任务（如迁移工程），
但与所有 actor 一样需架构师严格 review。
