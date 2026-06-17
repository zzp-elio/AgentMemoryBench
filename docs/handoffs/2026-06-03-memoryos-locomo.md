# 2026-06-03 MemoryOS LoCoMo Handoff

## 用户目标

先接入 `third_party/methods/MemoryOS-main`，在 LoCoMo 上按 MemoryOS 论文和官方代码中的官方配置跑 F1。当前只跑官方 F1，不跑 LLM judge。

## 强约束

- 必须先核验 MemoryOS 论文和官方代码里的 LoCoMo 实验配置。
- 必须使用和官方配置一致的模型、prompt、参数、数据处理和评测方式。
- 如果本地缺少官方配置依赖的模型、API、数据、脚本或运行资源，必须向用户明确报告。
- 不能擅自换成近似配置，也不能为了跑通而降低配置。
- 当前框架仍然只使用 conversation-QA v2：`BaseMemorySystem.add(list[Conversation])` 和 `get_answer(Question)`。
- LoCoMo 本轮只计算 F1，不跑 LLM judge。

## 当前项目基线

- conversation-QA v2 Phase 1 已完成。
- LoCoMo adapter 可读取单样本：`locomo conv-26 19 152`。
- LongMemEval adapter 可读取单样本：`longmemeval e47becba 53 1`。
- `uv run python -m unittest discover -s tests -v` -> 69 tests OK。

## 当前任务计划

1. 读取 MemoryOS 论文，提取 LoCoMo 实验设置。
2. 读取 MemoryOS 官方代码，定位 LoCoMo benchmark 脚本、method API、配置文件和依赖。
3. 核对本地 `models/`、`.env`、benchmark 数据和 Python 依赖是否满足。
4. 形成接入设计，先和用户确认，再实现 wrapper 和测试。

## 已定位的 MemoryOS 关键文件

- `third_party/methods/MemoryOS-main/Paper-MemoryOS.pdf`
- `third_party/methods/MemoryOS-main/README.md`
- `third_party/methods/MemoryOS-main/readme_cn.md`
- `third_party/methods/MemoryOS-main/eval/evalution_loco.py`
- `third_party/methods/MemoryOS-main/eval/main_loco_parse.py`
- `third_party/methods/MemoryOS-main/eval/locomo10.json`
- `third_party/methods/MemoryOS-main/memoryos-chromadb/requirements.txt`
- `third_party/methods/MemoryOS-main/memoryos-pypi/requirements.txt`

## 已派发的只读 subagent

- `019e8cca-2e62-7001-a29e-fc0d6ca1c5a4` / Maxwell：读取 MemoryOS 论文、README 和文档，提取 LoCoMo 实验配置、metric、模型和缺失资源。
- `019e8cca-6242-76e3-9162-343ef8019ff1` / Kepler：读取 MemoryOS 代码和 LoCoMo eval 脚本，判断如何适配当前 `BaseMemorySystem`，并列出依赖和阻塞点。

如果新窗口无法等待这两个 subagent，直接重新做本地只读核验即可，不要依赖未返回结果。

## 当前状态

已完成只读调查的第一轮核心事实核验，尚未实现 MemoryOS wrapper，尚未运行 MemoryOS。

## 压缩恢复判断

本文件已经足够支持上下文压缩恢复：新窗口能从这里知道用户目标、禁止事项、当前框架基线、MemoryOS 关键文件和下一步。继续推进时仍要把每个重要发现追加到本文件。

## 已确认事实

### 论文配置

- MemoryOS 论文在 LoCoMo 上报告 `GPT-4o-mini` 和 `Qwen2.5-3B` 两组结果。
- 用户当前要求只跑 `GPT-4o-mini` 的官方 F1，不跑 LLM judge，也不跑 BLEU-1。
- 论文中的 LoCoMo 指标是 standard F1 和 BLEU-1。
- 论文 Table 2 中 `GPT-4o-mini / Ours`:
  - Single Hop: F1 35.27, BLEU-1 25.22
  - Multi Hop: F1 41.15, BLEU-1 30.76
  - Temporal: F1 20.02, BLEU-1 16.52
  - Open Domain: F1 48.62, BLEU-1 42.99
- 论文实现细节：
  - STM dialogue page queue length = 7
  - MTM max segment length = 200
  - User KB / Agent Traits capacity = 100
  - heat threshold tau = 5
  - retrieval top-m segments = 5
  - LoCoMo retrieved dialogue page top-k = 10
  - similarity threshold theta = 0.6
  - time constant mu = 1e+7
  - alpha / beta / gamma = 1

### 开源 eval 配置

- README 的复现命令只有：
  - `cd eval`
  - 在代码中配置 API key 和其他设置
  - `python3 main_loco_parse.py`
  - `python3 evalution_loco.py`
- `eval/main_loco_parse.py` 没有使用通用 `memoryos-pypi/Memoryos` 类，而是直接使用 eval 目录下的 `ShortTermMemory / MidTermMemory / LongTermMemory / DynamicUpdate / RetrievalAndAnswer`。
- `eval/locomo10.json` 与 `benchmarks/locomo-main/data/locomo10.json` 哈希一致。
- `eval/main_loco_parse.py` 会处理完整 10 个 LoCoMo sample，并写出 `all_loco_results.json`。
- 开源 eval 代码硬编码：
  - LLM: `gpt-4o-mini`
  - final answer temperature = 0.7, max_tokens = 2000
  - continuity detection temperature = 0.0, max_tokens = 10
  - meta-summary temperature = 0.3, max_tokens = 100
  - embedding default = `SentenceTransformer("all-MiniLM-L6-v2")`
  - vector search = `faiss.IndexFlatIP`
  - heat threshold = 5.0
  - `ShortTermMemory(max_capacity=1)`
  - `MidTermMemory(max_capacity=2000)`
  - `DynamicUpdate(... topic_similarity_threshold=0.6)`
  - `RetrievalAndAnswer(... queue_capacity=10)`
  - retrieve thresholds: segment/page/knowledge all = 0.1
- 论文和开源 eval 代码存在显著差异：
  - 论文 STM queue length = 7，但 eval 脚本使用 short-term max_capacity = 1。
  - 论文 MTM max segment length = 200，但 eval 脚本使用 mid-term max_capacity = 2000。

### F1 scorer 差异

- MemoryOS 官方 `eval/evalution_loco.py` 使用自定义 set-token F1：
  - lowercase
  - regex `\b\w+\b`
  - prediction/reference tokens 转成 set
  - 用 set overlap 计算 precision/recall/F1
  - 按 category 打印平均 F1
- 当前项目的 `memory_benchmark/evaluators/locomo_f1.py` 是常见 QA F1：
  - 去标点
  - 去英文冠词
  - Counter 多重 token overlap
- 因此如果跑 MemoryOS 官方 F1，不能直接复用当前 `LoCoMoF1Evaluator`，需要单独实现 MemoryOS 官方 set-token F1。

### 本地资源核验

- `.env` 通过 `memory_benchmark.config.settings.load_settings()` 可读到 `OPENAI_KEY` 和 `BASE_URL`，模型配置为 `gpt-4o-mini`。不要打印 secret。
- 当前 `uv` 环境已经有 `openai`、`python-dotenv`、`rich`、`numpy`。
- 当前 `uv` 环境缺少：
  - `sentence_transformers`
  - `faiss`
  - `tiktoken`
  - `FlagEmbedding`
  - `chromadb`
  - `transformers`
- `models/BAAI/bge-m3` 存在，但开源 LoCoMo eval 默认需要 `all-MiniLM-L6-v2`；本地没有发现 `all-MiniLM-L6-v2` 模型目录。
- `models/nltk` 存在，但 MemoryOS LoCoMo eval 当前不依赖它。
- MemoryOS eval 代码本身不读取 `.env`，而是硬编码空 API key 和固定 base_url。要在本项目里运行，必须做 wrapper/配置注入，不能直接调用原脚本原样运行。

## 当前 blocker / 必须向用户确认的问题

1. **论文配置 vs 开源 eval 配置冲突**：用户已确认实验设置以论文里说的为准，而不是照搬开源 eval 脚本里冲突的容量参数。
2. **缺少依赖**：要运行 eval 版本至少需要补 `sentence-transformers`、`faiss`、`tiktoken`；如果使用本地 `bge-m3` 或 PyPI/chromadb 版本还需要 `FlagEmbedding`、`transformers`、`chromadb` 等。
3. **缺少 MiniLM 本地模型**：用户已确认如果代码仓库默认 `all-MiniLM-L6-v2` 且论文未明确 embedding 模型，则使用 `sentence-transformers/all-MiniLM-L6-v2`，通过 `sentence-transformers` 自动下载到本地缓存。若结果不理想，后续再用本地 `models/BAAI/bge-m3` 跑一遍对照。
4. **category 5 是否参与**：LoCoMo 原始数据有 category 1-5；论文 Table 2 只报告 1-4，当前项目 LoCoMo adapter 也跳过 category 5。开源 eval 脚本会遍历 category 5。推荐为了复现论文表格，只聚合 1-4，但可保留 category 5 输出为附加诊断。

## 推荐接入方向

- 不直接改 MemoryOS 原仓库代码。
- 在本项目中新增 MemoryOS eval-style wrapper，尽量复用 `eval/` 下的官方模块和 prompt：
  - `add(list[Conversation])`: 将 conversation 按 LoCoMo 官方 `process_conversation()` 逻辑转为 `user_input / agent_response / timestamp` 页面，写入 eval memory modules。
  - `get_answer(Question)`: 按 `eval/main_loco_parse.py` 的检索参数和 `generate_system_response_with_meta()` prompt 生成答案。
  - 每个 `conversation_id` 独立一套 MemoryOS 状态目录，保证不用 reset 也不会串样本。
- 新增 LoCoMo 官方 F1 evaluator，严格复刻 `benchmarks/locomo-main/task_eval/evaluation.py` 的 QA F1，而不是 MemoryOS `eval/evalution_loco.py` 的 set-token F1。
- 先做 `limit=1` smoke，不直接全量 10 个 sample，因为 full LoCoMo 会有大量 LLM 调用。

## 用户最新决策

- MemoryOS 实验设置以论文中描述为准。
- F1 使用 LoCoMo 论文/官方仓库里的 F1。
- 不修改 MemoryOS 原始仓库。
- 缺少依赖用 `uv` 安装。
- embedding 使用 `sentence-transformers/all-MiniLM-L6-v2`；若结果不理想，后续再用 `models/BAAI/bge-m3` 对照。

## LoCoMo 官方 F1 核验

- LoCoMo README 没有详细写 F1 公式，但官方代码在 `benchmarks/locomo-main/task_eval/evaluation.py`。
- `normalize_answer()`:
  - 先删除逗号
  - 小写
  - 去 `string.punctuation`
  - 去英文冠词/连接词 `a|an|the|and`
  - 压缩空白
- `f1_score()`:
  - 对 normalized prediction/gold 按空白切词
  - 对每个 token 做 Porter stemming
  - 用 `Counter(prediction_tokens) & Counter(ground_truth_tokens)` 计算 overlap
  - 按 precision/recall/F1 返回
- `f1()`:
  - 对 prediction 和 ground truth 都按英文逗号拆成多个子答案
  - 对每个 gold 子答案取所有 prediction 子答案中的最大 `f1_score`
  - 再对 gold 子答案求均值
- `eval_question_answering()`:
  - category 2/3/4 使用 `f1_score`
  - category 1 使用 `f1`
  - category 5 是 adversarial，不属于论文 Table 2 的四类报告范围

## 依赖和模型核验结果

已执行：

```bash
uv add sentence-transformers faiss-cpu tiktoken regex
```

说明：

- 使用 `faiss-cpu`，因为 MemoryOS eval 代码只依赖 `faiss.IndexFlatIP`，CPU 包提供同一接口；本地第一阶段不复现 8 H20 GPU 硬件环境。
- `uv run python` import smoke 已通过：
  - `sentence_transformers 5.5.1`
  - `faiss 1.14.2`
  - `tiktoken 0.13.0`
  - `regex 2026.5.9`
  - `transformers 5.9.0`
  - `torch 2.12.0`
- 已成功加载并编码 `sentence-transformers/all-MiniLM-L6-v2`，输出 shape 为 `(1, 384)`。
- 加载模型时出现 Hugging Face 未认证请求 warning，但模型下载/缓存成功；当前不是 blocker。

## 2026-06-03 额度不足紧急交接

用户提示当前 5h 额度只剩约 10%，本轮必须优先保证后续窗口能无缝继续。当前状态如下。

### 已完成的代码变更

1. `pyproject.toml` / `uv.lock`
   - 已通过 `uv add sentence-transformers faiss-cpu tiktoken regex` 安装 MemoryOS-LoCoMo 所需基础依赖。
   - 已验证 import smoke：
     - `sentence_transformers 5.5.1`
     - `faiss 1.14.2`
     - `tiktoken 0.13.0`
     - `regex 2026.5.9`
     - `transformers 5.9.0`
     - `torch 2.12.0`
   - 已验证 `SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")` 能加载并 encode，输出 shape `(1, 384)`。

2. `memory_benchmark/evaluators/locomo_f1.py`
   - 已从旧的通用 QA F1 改成 LoCoMo 官方 QA F1。
   - 逻辑依据：`benchmarks/locomo-main/task_eval/evaluation.py`。
   - 当前实现：
     - normalization: 小写、去逗号、去 `string.punctuation`、去 `a|an|the|and`、压缩空白。
     - token: Porter stemming。
     - category `1`: 按逗号拆多答案，逐个 gold 子答案取 prediction 子答案中的最大 F1，再求均值。
     - category `2/3/4`: 普通 Counter overlap F1。
     - category `5`: adversarial 拒答规则，包含 `no information available` 或 `not mentioned` 得 1，否则得 0。
   - 已通过：
     ```bash
     uv run python -m unittest tests/test_locomo_answer_metrics.py -v
     ```
     结果：9 tests OK。

3. `tests/test_locomo_answer_metrics.py`
   - 已改成 LoCoMo 官方 F1 的测试。
   - 已执行 TDD：先看到 RED，再实现 evaluator，最后 GREEN。

4. `tests/test_memoryos_adapter.py`
   - 已新增 MemoryOS adapter 的 RED 测试文件，但尚未运行到 GREEN。
   - 这个测试当前导入尚未创建的 `memory_benchmark.methods.memoryos_adapter.MemoryOS` 和 `MemoryOSPaperConfig`。
   - 因此现在如果运行全量 unittest，预计会因为 `memoryos_adapter.py` 缺失而失败。
   - 这是正常 RED 状态，不是项目已有功能回归。

### 还没有完成的代码

尚未创建：

- `memory_benchmark/methods/memoryos_adapter.py`

尚未实现：

- `MemoryOSPaperConfig`
- `MemoryOS`
- MemoryOS eval 模块的安全导入和配置注入。
- 每个 `conversation_id` 独立 MemoryOS 状态目录。
- `BaseMemorySystem.add(list[Conversation]) -> AddResult`
- `BaseMemorySystem.get_answer(Question) -> AnswerResult`
- 真实 LoCoMo `limit=1` smoke runner / test。

### 下一窗口必须先做的事情

1. 先读本文件和 `AGENTS.md`。
2. 运行一个 targeted RED，确认当前 MemoryOS adapter 测试失败原因是缺模块：
   ```bash
   uv run python -m unittest tests/test_memoryos_adapter.py -v
   ```
   预期：`ModuleNotFoundError` 或 import error，说明 RED 测试已经就位。
3. 创建 `memory_benchmark/methods/memoryos_adapter.py`，顶部必须有中文模块说明。
4. 最小实现先满足 `tests/test_memoryos_adapter.py`，不要先接真实 LLM。
5. 再运行：
   ```bash
   uv run python -m unittest tests/test_memoryos_adapter.py tests/test_locomo_answer_metrics.py -v
   ```
6. 通过后再实现真实 LLM smoke，不要一开始跑完整 LoCoMo。

### MemoryOS wrapper 设计要点

实现文件建议：`memory_benchmark/methods/memoryos_adapter.py`

必须遵守：

- 不修改 `third_party/methods/MemoryOS-main` 原始仓库。
- 不调用 `memoryos-pypi/Memoryos.get_response()`，因为它会把 benchmark question 和 generated answer 追加写回 memory，污染评测记忆。
- 使用 `MemoryOS-main/eval/` 下的官方 eval 模块/逻辑作为基础，但通过本项目 wrapper 注入 `.env` 配置和论文参数。
- 每个 `conversation_id` 独立一套 memory 状态，不使用 reset。
- method public input 只能是 public `Conversation` / `Question`，不能传 gold/evidence。

推荐 dataclass：

```python
@dataclass(frozen=True)
class MemoryOSPaperConfig:
    llm_model: str = "gpt-4o-mini"
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    short_term_capacity: int = 7
    mid_term_capacity: int = 200
    long_term_knowledge_capacity: int = 100
    heat_threshold: float = 5.0
    topic_similarity_threshold: float = 0.6
    retrieval_top_m_segments: int = 5
    retrieval_queue_capacity: int = 10
    segment_threshold: float = 0.1
    page_threshold: float = 0.1
    knowledge_threshold: float = 0.1
```

说明：

- `retrieval_queue_capacity=10` 与论文 LoCoMo top-k pages=10 对齐。
- `retrieval_top_m_segments=5` 是论文设置；MemoryOS eval 源码里 `MidTermMemory.search_sessions_by_summary(... top_k=5)` 默认正好是 5。
- `segment/page/knowledge_threshold=0.1` 来自 MemoryOS 开源 eval 脚本；论文只明确 similarity threshold theta=0.6，未明确这三个 retrieve filter threshold。先保留官方 eval 脚本值，并在 wrapper metadata 中记录。

### eval 模块导入/注入注意事项

MemoryOS eval 目录源码是普通脚本风格，存在这些坑：

- `eval/utils.py` 全局 `gpt_client = OpenAI(api_key='', base_url='https://cn2us02.opapi.win/v1')`。
- `OpenAIClient.chat_completion()` 实际调用的是全局 `gpt_client`，而不是实例字段。
- `eval/mid_term_memory.py` 也有全局 `client = OpenAIClient(api_key='', base_url=...)`，`add_session()` 里调用 `llm_extract_keywords(summary, client=client)`，会用空 key。
- `eval/utils.py:get_embedding(text, model_name="all-MiniLM-L6-v2")` 每次新建 `SentenceTransformer(model_name)`，全量跑会很慢。

因此 wrapper 需要在本项目侧做安全注入：

- 导入 eval 模块前，把 eval 目录临时加入 `sys.path`。
- 使用 `importlib` 加载模块时避免污染全局路径太久。
- 初始化 wrapper 时，用 `load_settings()` 读 `.env`，构造 OpenAI client，并覆盖 eval utils 中的全局 `gpt_client`。
- 覆盖或包装 eval `get_embedding()`，使用缓存后的 `SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")`，避免每次重新加载模型。
- 如果不想第一版 monkeypatch 太多，至少必须修正全局 OpenAI client，否则真实调用会用空 key。

### conversation -> MemoryOS page 转换规则

以 LoCoMo / MemoryOS eval 的 `process_conversation()` 为准：

- `conversation.metadata["speaker_a"]` 作为 user/speaker_a。
- `conversation.metadata["speaker_b"]` 作为 assistant/speaker_b。
- 遍历 sessions 和 turns。
- speaker_a turn 转成新 page 的 `user_input`。
- speaker_b turn 填入最近一个 page 的 `agent_response`。
- timestamp 使用 `Session.session_time`。
- 如果 turn 有图片 caption，Phase 1 文本跑通时可把 caption 追加到 content，例如：
  - `"{content} (image description: {caption})"`
- 一个 round 应是 speaker_a + speaker_b 两个 turn；若 speaker_b 缺失，page 的 `agent_response` 可以为空，但后续 MemoryOS eval 的 `bulk_evict_and_update_mid_term()` 会跳过 user/agent 不完整的 page。

### 真实 smoke 的建议顺序

先不要跑完整 10 个 LoCoMo sample。

建议步骤：

1. 单元测试通过后，跑只 add 不 answer 的 smoke：
   - 加载 `LoCoMoAdapter(limit=1)`。
   - `MemoryOS.add([conversation])`。
   - 检查状态文件存在、short/mid/long json 可读。
2. 再跑单 question answer：
   - 只取 `conversation.questions[0]`。
   - 调 `get_answer()`。
   - 用 `LoCoMoF1Evaluator` 评分。
3. 最后再考虑 `limit=1` 全部 questions。

### 当前不应做的事

- 不要恢复 PrefEval。
- 不要改 MemoryOS 原始仓库。
- 不要直接运行 `MemoryOS-main/eval/main_loco_parse.py`，因为它不读 `.env`，且配置与论文冲突。
- 不要运行全量 LoCoMo，直到单 question smoke 稳定。
- 不要把 MemoryOS 官方 `evalution_loco.py` 的 set-F1 当作最终 F1；用户已明确要求 LoCoMo 论文 F1，官方核验结果在上文。

## 2026-06-03 继续执行后的最新状态

用户 5h 额度恢复后继续从 RED 测试推进。当前已经完成 MemoryOS wrapper 基础层。

### 新增/修改文件

- 新增 `memory_benchmark/methods/memoryos_adapter.py`
  - 顶部有中文模块说明。
  - 新增 `MemoryOSPaperConfig`，集中保存论文配置。
  - 新增 `MemoryOSConversationState`，保存每个 `conversation_id` 独立的 MemoryOS eval 状态。
  - 新增 `MemoryOS(BaseMemorySystem)`，实现：
    - `add(list[Conversation]) -> AddResult`
    - `get_answer(Question) -> AnswerResult`
    - `conversation_to_memory_pages(Conversation) -> list[dict]`
    - `get_debug_state(conversation_id)`
  - 不修改 MemoryOS 原始仓库。
  - 加载 `MemoryOS-main/eval/` 时处理官方 `OpenAI(api_key="")` 的导入问题：临时用占位 key 完成 import，随后注入 `.env` 配置中的真实 OpenAI-compatible client。
  - patch eval 模块：
    - `utils.gpt_client` 替换为真实 client。
    - `mid_term_memory.client` 替换为真实 client。
    - `main_loco_parse.H_THRESHOLD` 替换为论文 heat threshold。
    - `mid_term_memory.compute_segment_heat` 替换为论文默认 alpha/beta/gamma = 1 的计算。
    - `utils/mid_term_memory/long_term_memory.get_embedding` 替换为本项目缓存版 `SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")`。
  - 默认屏蔽 MemoryOS 官方脚本里的 `print()` 输出，避免库代码污染终端。

- 修改 `memory_benchmark/methods/__init__.py`
  - 导出 `MemoryOS` 和 `MemoryOSPaperConfig`。

- 新增 `tests/test_memoryos_adapter.py`
  - 覆盖无真实 LLM 的 wrapper 基础行为：
    - 论文默认配置。
    - conversation -> MemoryOS QA page 转换。
    - add 写入公开 page，不写 gold/evidence。
    - get_answer 在 conversation 未 add 时抛 `ConfigurationError`。

- 修改 `memory_benchmark/evaluators/locomo_f1.py`
  - 已改成 LoCoMo 官方 QA F1。

- 修改 `tests/test_locomo_answer_metrics.py`
  - 已覆盖 LoCoMo 官方 QA F1 的 category 1/2/3/4/5 行为。

### 已完成验证

已执行并通过：

```bash
uv run python -m unittest tests/test_memoryos_adapter.py -v
```

结果：4 tests OK。

已执行并通过：

```bash
uv run python -m unittest tests/test_memoryos_adapter.py tests/test_locomo_answer_metrics.py -v
```

结果：13 tests OK。

已执行并通过：

```bash
uv run python -m unittest tests/test_documentation_standards.py -v
```

结果：4 tests OK。

已执行并通过：

```bash
uv run python -m unittest discover -s tests -v
```

结果：76 tests OK。

### 重要实现细节

- `MemoryOSPaperConfig` 默认配置：
  - `llm_model="gpt-4o-mini"`
  - `embedding_model_name="sentence-transformers/all-MiniLM-L6-v2"`
  - `short_term_capacity=7`
  - `mid_term_capacity=200`
  - `long_term_knowledge_capacity=100`
  - `heat_threshold=5.0`
  - `topic_similarity_threshold=0.6`
  - `retrieval_top_m_segments=5`
  - `retrieval_queue_capacity=10`
  - `segment_threshold/page_threshold/knowledge_threshold=0.1`，这些来自 MemoryOS 开源 eval 脚本，因为论文未明确这三个 filter threshold。

- `MemoryOS.get_answer()` 当前会调用真实 LLM：
  - 先用 MemoryOS eval retrieval 检索。
  - 再调用 `main_loco_parse.generate_system_response_with_meta()` 的官方 prompt 生成答案。
  - 不会像 `memoryos-pypi/Memoryos.get_response()` 那样把 benchmark question/answer 写回 memory。

- 当前 `MemoryOS.add()` 如果使用论文默认 `short_term_capacity=7` 加载完整 LoCoMo conversation，会触发 MemoryOS eval 的多次 LLM 调用和 embedding 计算。不要直接全量跑。

### 下一步建议

1. 先做真实 API 的极小 synthetic smoke：
   - 用 `build_small_conversation()` 类似结构。
   - `MemoryOS.add([conversation])` 不触发 mid-term update。
   - `MemoryOS.get_answer(question)` 只调用一次最终回答 LLM。
   - 用 `LoCoMoF1Evaluator` 评分。
2. 再做 LoCoMo `limit=1` 的 add-only smoke，但临时 config 设置较大的 `short_term_capacity`，避免一开始触发大量 LLM 更新；这个只验证真实 LoCoMo adapter 到 MemoryOS page 的转换和状态写入。
3. 最后才做论文默认 config 下的 LoCoMo 单 question smoke；这一步会产生多次 LLM 调用，应单独告知用户。

### 已完成 smoke

1. 真实 API 极小 synthetic smoke 已通过。

执行逻辑：

- 使用 `tests.test_memoryos_adapter.build_small_conversation()` 构造两轮短对话。
- `MemoryOS.add([conversation])` 不触发 mid-term update。
- `MemoryOS.get_answer(question)` 调用一次真实 `gpt-4o-mini`。
- `LoCoMoF1Evaluator` 评分。

输出：

```text
question_id conv-test:q1
answer Seattle
f1 1.0
```

2. LoCoMo 第一条样本 add-only smoke 已通过。

执行逻辑：

- `LoCoMoAdapter(Path.cwd()).load(limit=1)`。
- 使用 `MemoryOSPaperConfig(short_term_capacity=10_000)` 临时避免 LLM 更新。
- 只调用 `MemoryOS.add([conversation])`，不调用 `get_answer()`。

输出：

```text
conversation_id conv-26
sessions 19
questions 152
pages 214
added_ids ['conv-26']
short_memory_count 214
```

注意：这个 add-only smoke 不是论文默认配置，只用于验证真实 LoCoMo adapter 到 MemoryOS page 写入链路。论文默认配置下 `short_term_capacity=7`，会触发大量 MemoryOS 更新调用。

### 论文默认配置下的运行成本风险

`conv-26` 已确认会被转换为 214 个 MemoryOS page。若使用论文默认
`short_term_capacity=7`，`add()` 阶段大约会触发 208 批 short-term -> mid-term
更新。每批更新内部包含连续性判断、meta-summary、多主题摘要、关键词抽取、用户画像/
知识更新检查等多处 LLM 调用。因此：

- 不要直接用论文默认配置跑完整 `conv-26` 全部 152 个问题。
- 即使只跑 `conv-26` 的 1 个问题，`add()` 阶段也会先消耗大量 LLM 调用。
- 下一步应该先实现带成本保护的 smoke 入口，例如明确打印 page 数、预计批次数和 question 数，并要求用户确认后再运行论文默认配置。

已新增 `MemoryOS.estimate_add_workload(conversation, config)` 用于运行前估算。测试已通过。

对 LoCoMo 第一条样本 `conv-26` 的论文默认配置估算结果：

```text
conversation_id conv-26
page_count 214
short_term_capacity 7
update_batch_count 208
remaining_short_term_pages 6
will_trigger_updates True
```

## 2026-06-03 上下文压缩前续接记录

用户 5h 额度恢复，但提示上下文即将压缩。本窗口恢复后已重新读取：

- `AGENTS.md`
- `docs/handoffs/2026-06-03-memoryos-locomo.md`
- `memory_benchmark/methods/memoryos_adapter.py`
- `tests/test_memoryos_adapter.py`
- `memory_benchmark/runners/conversation_qa.py`
- `memory_benchmark/utils/run_logger.py`

当前确认：

- MemoryOS wrapper 已存在，不再是 RED 缺文件状态。
- `MemoryOS.estimate_add_workload()` 已可用于运行前估算。
- LoCoMo `conv-26` 在论文默认配置下会触发约 208 批 MemoryOS 更新，不能无保护地直接运行。

下一步实现目标：

1. 先写测试，再新增一个 MemoryOS-LoCoMo smoke 入口。
2. 默认行为只做 workload 估算，不触发真实 MemoryOS `add()`。
3. 支持 add-only 模式，使用大 STM capacity 避免 LLM 更新，只验证 LoCoMo 数据到 MemoryOS page 写入链路。
4. 只有显式传入确认参数时，才允许使用论文默认 `short_term_capacity=7` 触发真实更新。
5. 日志应写入 `outputs/<run_id>/logs/`，并使用现有 `RunLogger`。

如果本文件后续成为压缩恢复入口，应从上述 smoke 入口继续，不要直接启动完整 LoCoMo 实验。

## 2026-06-03 subagent review 修正记录

收到 MemoryOS adapter / LoCoMo F1 的代码审查后，已核验并修复以下问题：

- `MemoryOS.estimate_add_workload()` 原先按整批清空估算，错误地把 `conv-26`
  估为 30 批；官方 `bulk_evict_and_update_mid_term()` 满队列后通常只弹出一页，
  正确估算是 `214 - 7 + 1 = 208` 批。
- `MemoryOS` 默认 `storage_root` 原先固定为 `outputs/memoryos`，新实例可能读取
  旧 JSON 状态；现在默认写入 `outputs/memoryos/run-<uuid>`。
- 调用方只传 `openai_api_key` 时，`openai_base_url` 现在会从配置层补齐。
- MemoryOS eval 脚本的 bare module import 已做实例级隔离，避免多个实例共享
  被 monkeypatch 的 `utils` / `mid_term_memory` 等模块。
- LoCoMo category 3 F1 已补齐官方规则：gold answer 先按分号截断再评分。
- MemoryOS private leakage 测试已强化为检查 `answer` / `gold_answer` / `evidence`
  等私有字段，而不是检查公开内容字符串。

已通过聚焦验证：

```bash
uv run python -m unittest tests/test_memoryos_adapter.py tests/test_locomo_answer_metrics.py -v
```

结果：19 tests OK。

## 2026-06-03 MemoryOS-LoCoMo smoke runner

已新增：

- `memory_benchmark/runners/memoryos_locomo_smoke.py`
- `tests/test_memoryos_locomo_smoke.py`

runner 行为：

- `mode="estimate"` 是默认模式，只加载 LoCoMo 第一条样本并估算论文默认配置的成本；
  不实例化 MemoryOS，不调用 LLM。
- `mode="add-only"` 默认使用 safe config，把 STM capacity 设置为 `page_count + 1`，
  只验证真实 LoCoMo conversation 写入 MemoryOS 状态，不触发 MemoryOS 更新。
- `mode="add-only", use_paper_config=True` 会使用论文默认 `short_term_capacity=7`；
  如果会触发更新且没有 `confirm_expensive=True`，runner 会抛 `ConfigurationError`。
- 日志写入 `outputs/<run_id>/logs/run.log` 和 `events.jsonl`。

已通过聚焦验证：

```bash
uv run python -m unittest tests/test_memoryos_adapter.py tests/test_locomo_answer_metrics.py tests/test_memoryos_locomo_smoke.py tests/test_documentation_standards.py -v
```

结果：26 tests OK。

已完成真实 runner smoke：

```text
estimate:
  run_id manual-memoryos-estimate
  conversation_id conv-26
  page_count 214
  question_count 152
  short_term_capacity 7
  update_batch_count 208
  remaining_short_term_pages 6
  will_trigger_updates True
  add_executed False
  log_dir outputs/manual-memoryos-estimate/logs

safe add-only:
  run_id manual-memoryos-add-only
  conversation_id conv-26
  page_count 214
  question_count 152
  short_term_capacity 215
  update_batch_count 0
  remaining_short_term_pages 214
  will_trigger_updates False
  add_executed True
  added_conversation_ids ['conv-26']
  log_dir outputs/manual-memoryos-add-only/logs
```

最终全量验证：

```bash
uv run python -m unittest discover -s tests -v
```

结果：85 tests OK。注意：全量测试包含 `tests/test_API.py`，会读取 `.env` 并发起一次
最小 OpenAI-compatible API 调用。

下一步如果继续 MemoryOS：

1. 不要直接跑完整 LoCoMo。
2. 先决定是否接受 paper-default add 阶段约 208 批 LLM 更新的成本。
3. 如果用户确认，再新增 `answer-one` 或正式 runner 参数，先只跑 `conv-26` 的 1 个问题并计算 LoCoMo F1。
4. 继续注意 review 中仍未完全处理的配置语义：`mid_term_capacity=200` 是对论文 “MTM max segment length=200” 的适配解释，官方代码的 `MidTermMemory(max_capacity=...)` 实际更像存储 session 数量。

## 2026-06-03 全量测试与隔离验证

用户要求做全量测试并强调按 `conversation_id` 隔离。已完成两类全量验证：

1. 仓库测试：

```bash
uv run python -m unittest discover -s tests -v
```

结果：85 tests OK。该命令包含一次 `.env` API smoke。

2. LoCoMo 全量 safe add-only 隔离验证：

- 加载 LoCoMo 全部 10 个 conversation。
- 设置 `short_term_capacity = max_pages + 1 = 356`，避免触发 MemoryOS 更新和 LLM 调用。
- 一次性调用 `MemoryOS.add(dataset.conversations)`。
- 验证每个 conversation 都写入独立状态目录，且各自 STM page 数等于转换后的 page 数。

输出摘要：

```text
conversation_count 10
question_count 1540
max_pages 355
safe_short_term_capacity 356
added_count 10
state_dir_count 10
all_short_counts_match_pages True
total_paper_update_batches 2958
page_counts {
  'conv-26': 214,
  'conv-30': 189,
  'conv-41': 341,
  'conv-42': 322,
  'conv-43': 349,
  'conv-44': 344,
  'conv-47': 355,
  'conv-48': 348,
  'conv-49': 263,
  'conv-50': 293
}
paper_update_batches {
  'conv-26': 208,
  'conv-30': 183,
  'conv-41': 335,
  'conv-42': 316,
  'conv-43': 343,
  'conv-44': 338,
  'conv-47': 349,
  'conv-48': 342,
  'conv-49': 257,
  'conv-50': 287
}
```

写入目录：

```text
outputs/manual-memoryos-full-safe-add-only/memoryos_state/conv-26
outputs/manual-memoryos-full-safe-add-only/memoryos_state/conv-30
outputs/manual-memoryos-full-safe-add-only/memoryos_state/conv-41
outputs/manual-memoryos-full-safe-add-only/memoryos_state/conv-42
outputs/manual-memoryos-full-safe-add-only/memoryos_state/conv-43
outputs/manual-memoryos-full-safe-add-only/memoryos_state/conv-44
outputs/manual-memoryos-full-safe-add-only/memoryos_state/conv-47
outputs/manual-memoryos-full-safe-add-only/memoryos_state/conv-48
outputs/manual-memoryos-full-safe-add-only/memoryos_state/conv-49
outputs/manual-memoryos-full-safe-add-only/memoryos_state/conv-50
```

重要边界：

- 这不是 paper-default 正式 QA 实验，因为 safe add-only 避免了 MemoryOS 更新和回答生成。
- 如果严格使用 paper-default `short_term_capacity=7`，仅 LoCoMo 全量 add 阶段就预计触发 2958 批 MemoryOS 更新，还没开始 1540 个问题的回答生成。
- 当前隔离策略是：同一个 wrapper 内部为每个 `conversation_id` 创建独立
  `MemoryOSConversationState`，并使用 `storage_root/<conversation_id>/short_term.json`、
  `mid_term.json`、`long_term.json` 分别保存短中长期状态；`get_answer(question)` 只根据
  `question.conversation_id` 选择对应状态检索和回答。

## 2026-06-03 正式 LoCoMo 全量 F1 runner 准备

用户明确确认预算足够，要求使用 `.env` 中的 API key/base URL 和 `gpt-4o-mini`
跑完整 LoCoMo，并计算 F1。

已新增：

- `memory_benchmark/runners/memoryos_locomo_full.py`
- `tests/test_memoryos_locomo_full_runner.py`

新增能力：

- 按 `conversation_id` 逐个 add，MemoryOS 状态写入
  `outputs/<run_id>/memoryos_state/<conversation_id>/`。
- 逐题写入：
  - `outputs/<run_id>/predictions.jsonl`
  - `outputs/<run_id>/scores.jsonl`
  - `outputs/<run_id>/summary.json`
  - `outputs/<run_id>/conversation_status.json`
- `resume=True` 时：
  - 已完成 question 不重复回答。
  - 已 add 的 conversation 使用 `load_existing_conversation_state()` attach 状态，
    不重复写入历史对话。
- 输出整体 F1、按 category F1 和各 category 题数。
- 为避免保存超大 prompt，prediction metadata 会移除 `system_prompt` / `user_prompt`，
  只保留检索数量等摘要。

已新增 MemoryOS wrapper 能力：

- `MemoryOS.load_existing_conversation_state(conversation)`，用于恢复已 add 的
  conversation 状态；至少要求 `short_term.json` 存在，避免 attach 未完成 add 的坏状态。

已通过验证：

```bash
uv run python -m unittest discover -s tests -v
```

结果：89 tests OK。

即将启动正式运行：

```python
run_memoryos_locomo_full(
    project_root=Path.cwd(),
    run_id="memoryos-locomo-full-20260603",
    resume=True,
    confirm_expensive=True,
)
```

## 2026-06-03 正式 LoCoMo 全量 F1 运行中

已启动真实运行：

```text
run_id memoryos-locomo-full-20260603
runner memory_benchmark.runners.memoryos_locomo_full.run_memoryos_locomo_full
resume True
confirm_expensive True
model gpt-4o-mini
api/base_url 来自 .env
```

启动命令等价于：

```python
run_memoryos_locomo_full(
    project_root=Path.cwd(),
    run_id="memoryos-locomo-full-20260603",
    resume=True,
    confirm_expensive=True,
)
```

当前观察到：

- 进程已进入 `conv-26` 的 MemoryOS add/update 阶段。
- `outputs/memoryos-locomo-full-20260603/memoryos_state/conv-26/` 下已有：
  - `short_term.json`
  - `mid_term.json`
  - `long_term.json`
- 尚未出现 `conversation_status.json`，说明 `conv-26` add 尚未完整完成，还没有开始答题。
- `predictions.jsonl` / `scores.jsonl` 当前仍为空。

后续进度观察：

- 22:47 CST 左右，`conv-26` 仍在 add 阶段。
- `mid_term.json` 中约有 `mid_pages=56`，`short_term.json` 中 `short_pages=6`。
- `long_term.json` 中长期知识和 assistant knowledge 已开始增长。
- 尚未出现 `conversation_status.json`，因此如果此时中断，恢复时会重新 add `conv-26`，
  并删除未 checkpoint 的部分状态目录以避免重复污染。

如果中断后恢复：

1. 先检查 `outputs/memoryos-locomo-full-20260603/conversation_status.json`。
2. 如果某个 conversation 已标记 `"added"`，runner 会 attach 已有状态并跳过已完成 question。
3. 如果当前 conversation 还没有 `"added"` checkpoint，runner 会删除该 conversation 的部分状态目录后重新 add，避免部分状态重复污染。
4. 继续运行同一个 `run_id`，保持 `resume=True` 和 `confirm_expensive=True`。

## 2026-06-04 正式运行网络超时断点

用户运行全量 MemoryOS-LoCoMo 一晚后中途失败。附件栈显示根因是网络/API 超时：

```text
httpcore.ConnectTimeout: _ssl.c:983: The handshake operation timed out
httpx.ConnectTimeout: _ssl.c:983: The handshake operation timed out
openai.APITimeoutError: Request timed out
```

失败位置：

```text
run_memoryos_locomo_full
  -> system.get_answer(public_question)
  -> state.retrieval_system.retrieve(...)
  -> mid_term_memory.search_sessions_by_summary(...)
  -> llm_extract_keywords(query, client)
  -> gpt_generate_answer(...)
  -> client.chat_completion(...)
```

结论：

- 这是 OpenAI-compatible API 调用在 TLS handshake 阶段超时，不是数据结构、F1 evaluator 或 checkpoint 逻辑错误。
- runner 级断点续跑是有效的：已有 question 会根据 `scores.jsonl` 跳过，已完成 add 的 conversation 会根据 `conversation_status.json` attach 已有 MemoryOS 状态。
- 当前缺口是单次 MemoryOS 官方 eval LLM 调用没有足够稳健的本项目侧重试兜底；需要在 wrapper 中补充 timeout + retry。

当前输出状态：

```text
run_dir outputs/memoryos-locomo-full-20260603
completed_questions 665 / 1540
predictions.jsonl 665 lines
scores.jsonl 665 lines
completed_conversations 5 / 10
conversation_status {
  "conv-26": "added",
  "conv-30": "added",
  "conv-41": "added",
  "conv-42": "added",
  "conv-43": "added"
}
overall_f1_partial 0.43659158297973283
f1_by_category_partial {
  "1": 0.37624289371384473,
  "2": 0.414849644657337,
  "3": 0.17441499636679222,
  "4": 0.5114245401082222
}
count_by_category_partial {
  "1": 142,
  "2": 156,
  "3": 46,
  "4": 321
}
```

恢复命令仍然使用同一个 `run_id`：

```bash
cd /Users/wz/Desktop/memoryBenchmark
uv run python -u - <<'PY'
from pathlib import Path
from memory_benchmark.runners.memoryos_locomo_full import run_memoryos_locomo_full

summary = run_memoryos_locomo_full(
    project_root=Path.cwd(),
    run_id="memoryos-locomo-full-20260603",
    resume=True,
    confirm_expensive=True,
)
print(summary.to_dict())
PY
```

恢复预期：

- `conv-26`、`conv-30`、`conv-41`、`conv-42`、`conv-43` 会 attach 已有状态，不重新 add。
- 已写入 `scores.jsonl` 的 665 个问题会跳过。
- runner 会从第 666 个未完成问题继续。

下一步补丁：

1. 在 `MemoryOSPaperConfig` 中加入本项目侧 API timeout/retry 配置。
2. 在 `MemoryOS` wrapper 中替换官方 `OpenAIClient.chat_completion` 为带重试的实现。
3. 同时配置 OpenAI SDK client 的 `timeout` 和 `max_retries`。
4. 捕获 `openai.APITimeoutError`、`openai.APIConnectionError` 以及常见 `httpx/httpcore` timeout/connect 异常。
5. 每次重试写入日志，但不能打印 API key。
6. 用单元测试模拟第一次超时、第二次成功，以及重试耗尽后抛错。

## 2026-06-04 MemoryOS API 重试兜底已实现

已完成 TDD 补丁：

- 先在 `tests/test_memoryos_adapter.py` 增加两个失败测试：
  - 第一次 `openai.APITimeoutError`、第二次成功时，应等待后重试并返回成功内容。
  - 连续超时且超过 retry budget 时，应抛出最后一次 `openai.APITimeoutError`。
- 红灯验证：

```text
uv run python -m unittest tests/test_memoryos_adapter.py -v
FAILED: MemoryOSPaperConfig.__init__() got an unexpected keyword argument 'api_timeout_seconds'
```

已实现：

- `MemoryOSPaperConfig` 新增：
  - `api_timeout_seconds=120.0`
  - `api_max_retries=8`
  - `api_retry_wait_seconds=5.0`
  - `api_retry_backoff_multiplier=2.0`
  - `api_retry_max_wait_seconds=60.0`
- `MemoryOS._patch_eval_modules()` 中创建 OpenAI SDK client 时：
  - 注入 `timeout=self.config.api_timeout_seconds`
  - 设置 `max_retries=0`，避免 SDK 隐藏重试和 wrapper 显式重试双重嵌套。
- 用 `MemoryOS._chat_completion_with_retry()` 替换官方 eval 的
  `OpenAIClient.chat_completion`。
- 重试捕获范围：
  - `openai.APITimeoutError`
  - `openai.APIConnectionError`
  - `httpx.TimeoutException`
  - `httpx.ConnectError`
  - `httpcore.TimeoutException`
  - `httpcore.ConnectError`
  - Python 内置 `TimeoutError` / `ConnectionError`
- 每次重试写入 logger warning，不记录 API key。

绿色验证：

```text
uv run python -m unittest tests/test_memoryos_adapter.py -v
Ran 13 tests in 4.784s
OK
```

聚焦 runner / 文档验证：

```text
uv run python -m unittest tests/test_memoryos_adapter.py tests/test_memoryos_locomo_full_runner.py tests/test_documentation_standards.py -v
Ran 19 tests in 3.979s
OK
```

全量验证：

```text
uv run python -m unittest discover -s tests -v
Ran 91 tests in 21.760s
OK
```

全量测试包含一次 `.env` OpenAI-compatible API smoke，本次也通过。

恢复全量运行仍使用同一个命令和同一个 `run_id`。补丁生效后，如果再次遇到类似
TLS handshake timeout，单次 MemoryOS LLM 调用会最多尝试 9 次；如果全部失败，
runner 仍会保留已有 JSONL/checkpoint，下次继续 resume。

## 2026-06-04 删除 MemoryOS 未使用生成参数字段

用户确认 `final_answer_temperature` / `final_answer_max_tokens` 不应暴露在 wrapper
配置里，因为 MemoryOS 官方 eval 代码已经在各个调用点内置 temperature 和 max_tokens。

已完成：

- 从 `MemoryOSPaperConfig` 删除 `final_answer_temperature`。
- 从 `MemoryOSPaperConfig` 删除 `final_answer_max_tokens`。
- 从 `memoryos_locomo_smoke.py` 的 safe config 复制逻辑中删除这两个字段。
- 增加测试 `test_config_does_not_expose_unused_generation_parameters`，防止未来重新暴露。

验证：

```text
uv run python -m unittest tests/test_memoryos_adapter.py tests/test_memoryos_locomo_smoke.py tests/test_memoryos_locomo_full_runner.py -v
Ran 19 tests in 3.767s
OK
```

行为影响：

- 不改变当前 MemoryOS-LoCoMo 正式运行的算法行为。
- 不影响 `memoryos-locomo-full-20260603` 断点续跑。
- 只是清理误导性配置字段，避免误以为 wrapper 可以控制 MemoryOS 官方生成温度和输出长度。

## 2026-06-04 输出目录最新进度快照

用户提示上下文即将压缩，已只读检查：

```text
outputs/memoryos-locomo-full-20260603
```

当前文件状态：

```text
conversation_status.json mtime Jun 4 06:32 UTC
predictions.jsonl       762 lines, mtime Jun 4 14:35 CST
scores.jsonl            762 lines, mtime Jun 4 14:35 CST
summary.json            mtime Jun 4 14:35 CST
memoryos_state/         contains conv-26, conv-30, conv-41, conv-42, conv-43, conv-44
```

`summary.json` 当前内容摘要：

```text
run_id memoryos-locomo-full-20260603
total_conversations 10
completed_conversations 5
total_questions 1540
completed_questions 762
overall_f1 0.45277580242209187
f1_by_category {
  "1": 0.37624289371384473,
  "2": 0.414849644657337,
  "3": 0.17441499636679222,
  "4": 0.5235622874135193
}
count_by_category {
  "1": 142,
  "2": 156,
  "3": 46,
  "4": 418
}
```

`conversation_status.json` 当前仍只有 5 个 completed add checkpoint：

```json
{
  "conv-26": "added",
  "conv-30": "added",
  "conv-41": "added",
  "conv-42": "added",
  "conv-43": "added"
}
```

按 LoCoMo conversation 统计的已完成 question 数：

```text
conv-26 152 / 152
conv-30  81 /  81
conv-41 152 / 152
conv-42 199 / 199
conv-43 178 / 178
conv-44   0 / 123
conv-47   0 / 150
conv-48   0 / 191
conv-49   0 / 156
conv-50   0 / 158
```

最近一条分数记录：

```text
conversation_id conv-43
question_id conv-43:q177
category 4
prediction Barcelona
gold Barcelona
f1 1.0
```

当前 MemoryOS state 目录统计：

```text
conv-26 short_pages=6 mid_sessions=111 mid_pages=346 knowledge=102 assistant_knowledge=16 profiles=1
conv-30 short_pages=6 mid_sessions=90  mid_pages=286 knowledge=102 assistant_knowledge=23 profiles=1
conv-41 short_pages=6 mid_sessions=168 mid_pages=535 knowledge=104 assistant_knowledge=26 profiles=1
conv-42 short_pages=6 mid_sessions=166 mid_pages=476 knowledge=102 assistant_knowledge=33 profiles=1
conv-43 short_pages=6 mid_sessions=189 mid_pages=532 knowledge=103 assistant_knowledge=34 profiles=1
conv-44 short_pages=6 mid_sessions=33  mid_pages=84  knowledge=35  assistant_knowledge=3  profiles=1
```

解释：

- `conv-26` 到 `conv-43` 已完成 add 和全部 QA。
- `conv-44` 已出现状态目录，但没有写入 `conversation_status.json`。
- 这表示当前运行很可能正在 `conv-44` add 阶段，或者曾在 `conv-44` add 阶段中断。
- 如果此时中断并 resume，runner 会因为 `conv-44` 没有 `"added"` checkpoint 而删除
  `memoryos_state/conv-44` 并重新 add，避免部分状态重复污染。
- `short_term.json` 中保留 6 条是正常现象：STM capacity=7，但官方 MemoryOS 在满 7 条时
  立即 FIFO 淘汰 1 条到 MTM，因此稳定落盘常见为 6 条。

继续运行命令保持不变：

```bash
cd /Users/wz/Desktop/memoryBenchmark
uv run python -u - <<'PY'
from pathlib import Path
from memory_benchmark.runners.memoryos_locomo_full import run_memoryos_locomo_full

summary = run_memoryos_locomo_full(
    project_root=Path.cwd(),
    run_id="memoryos-locomo-full-20260603",
    resume=True,
    confirm_expensive=True,
)
print(summary.to_dict())
PY
```

下一窗口恢复时，如果用户问“现在到哪了”，优先读：

1. `outputs/memoryos-locomo-full-20260603/summary.json`
2. `outputs/memoryos-locomo-full-20260603/conversation_status.json`
3. `wc -l outputs/memoryos-locomo-full-20260603/{predictions.jsonl,scores.jsonl}`
4. `tail -n 5 outputs/memoryos-locomo-full-20260603/scores.jsonl`

## 2026-06-05 MemoryOS-LoCoMo 全量 F1 实验完成

用户反馈 MemoryOS 在 LoCoMo 上的全量实验已经跑完。已只读核对输出目录：

```text
outputs/memoryos-locomo-full-20260603
```

最终 summary：

```json
{
  "run_id": "memoryos-locomo-full-20260603",
  "dataset_name": "locomo",
  "total_conversations": 10,
  "completed_conversations": 10,
  "total_questions": 1540,
  "completed_questions": 1540,
  "overall_f1": 0.4535399748307862,
  "f1_by_category": {
    "1": 0.3723542664738351,
    "2": 0.4125847499679276,
    "3": 0.2590717258785286,
    "4": 0.5185934217238356
  },
  "count_by_category": {
    "1": 282,
    "2": 321,
    "3": 96,
    "4": 841
  }
}
```

文件核对：

```text
predictions.jsonl 1540 lines
scores.jsonl      1540 lines
conversation_status.json contains 10 added conversations:
  conv-26, conv-30, conv-41, conv-42, conv-43,
  conv-44, conv-47, conv-48, conv-49, conv-50
memoryos_state contains 10 conversation state directories
```

LoCoMo category 数字映射：

依据：

- `benchmarks/locomo-main/task_eval/evaluation.py`
  - category 1 使用 multi-hop 的 comma-split partial F1。
  - category 2/3/4 使用普通 F1。
  - category 3 评分前会截断 gold answer 分号后的解释。
  - category 5 是 adversarial special score。
- `benchmarks/locomo-main/task_eval/hf_llm_utils.py`
  - category 2 会给 prompt 增加日期提示，因此是 temporal。
- `benchmarks/locomo-main/task_eval/evaluation_stats.py`
  - 官方打印顺序是 `[4, 1, 2, 3, 5]`。
- `benchmarks/locomo-main/locomo.md`
  - 明确记录映射为 4/1/2/3/5 对应 Single-hop/Multi-hop/Temporal/Open-domain/Adversarial。

当前项目采用的映射：

```text
category 4 = Single-hop
category 1 = Multi-hop
category 2 = Temporal
category 3 = Open-domain knowledge
category 5 = Adversarial
```

本次实验跳过 category 5，因为 MemoryOS 论文 Table 2 只报告前四类，当前 Phase 1
也不做 adversarial。

按论文表格类别名称重排后的本次结果：

```text
Single-hop            category 4  F1 0.5185934217238356  = 51.86  count 841
Multi-hop             category 1  F1 0.3723542664738351  = 37.24  count 282
Temporal              category 2  F1 0.4125847499679276  = 41.26  count 321
Open-domain knowledge category 3  F1 0.2590717258785286  = 25.91  count 96
```

聚合说明：

- `overall_f1=0.4535399748307862` 是 1540 道公开 QA 的 micro average。
- 四类 macro average 为 `0.39065104101103176`，即 `39.07`。
- 论文 Table 2 主要报告每类 F1 / BLEU-1；当前项目只实现并运行 F1，未运行 BLEU-1。

实验表述建议：

```text
MemoryOS official eval algorithm + paper-priority parameters + LoCoMo official QA F1.
```

中文表述：

```text
基于 MemoryOS 原仓库 LoCoMo eval 算法、按论文参数优先对齐，并使用 LoCoMo 官方 QA F1 的复现实验。
```

重要 caveat：

- 这是 paper-aligned reproduction，不是 bitwise exact reproduction。
- LLM API 后端、base URL、模型版本、网络重试和非确定性生成可能导致数值与论文表格有波动。
- 当前 `summary.json` 的 `f1_by_category` key 是原始数字 category，不是论文列名；写论文/报告时必须按上面的映射重排。

下一步建议：

1. 生成一个正式结果报告文件，包含最终 F1、类别映射、运行配置和 caveat。
2. 如需和 MemoryOS 论文 Table 2 对照，使用按类别名称重排后的结果，不要直接按数字 1/2/3/4 顺序解读。
3. 后续如果继续 method 对比，保持同一 LoCoMo adapter、同一 F1 evaluator、同一 category 5 跳过规则。
