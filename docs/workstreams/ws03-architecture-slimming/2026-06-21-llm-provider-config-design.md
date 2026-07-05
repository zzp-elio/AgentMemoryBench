# LLM Provider 与 Prompt 配置设计

日期：2026-06-21

## 背景

Retrieve-first 主协议把 method 的职责收敛为：

```text
add(conversation)
retrieve(question) -> formatted_context
```

最终 answer 不再由 method adapter 生成，而由 framework reader 统一完成：

```text
Question + RetrievalResult.formatted_context + AnswerPromptTemplate
    -> Answer LLM
    -> AnswerResult
```

这意味着 LLM 调用会从各个 method adapter 中逐步上移到框架层。与此同时，当前框架里已经
有多处 LLM 或模型调用：

- framework answer LLM。
- LLM judge。
- 内置 method 的 memory build、query rewrite、retrieval-stage LLM、answer 兼容路径。
- embedding model/API。
- 未来可能出现的 reranker、compressor、retrieval relevance evaluator。

用户明确希望：凡是框架可控的 LLM 调用，都应逐步支持灵活配置，包括 OpenAI-compatible
接口、Claude/Anthropic、Gemini、本地开源模型等。Phase 1 真实实验仍统一默认
`gpt-4o-mini`，但架构上不能继续把模型、base URL、timeout、retry、prompt 写死。

## 参考结论

本设计参考了本地资料：

- `第三方框架参考/supermemoryai-memorybench.md`
- `第三方框架参考/supermemoryai讨论.md`
- `第三方框架参考/EVALUATION_ARCHITECTURE.md`

对我们有价值的点：

- provider/method 只负责 ingest/search，统一 answer phase 负责 prompt 和 answer LLM。
- `formatted_context` 优先进入 answer stage，而不是强制 answer stage 理解 raw search
  results。
- answer phase 同时构造 base prompt 和带 memory context 的 prompt，可用于估算
  memory context token 开销。
- answer prompt 和 judge prompt 应支持 profile 或文件覆盖。
- config 应支持环境变量展开，避免 secret 写入配置文件。

不能照抄的点：

- supermemoryai MemoryBench 按 question 生成 `containerTag` 隔离 memory；我们必须按
  `conversation_id` 隔离，因为 LoCoMo/LongMemEval 的 QA 基于同一个 conversation 历史。
- 当前主线不做 retrieval recall/relevance evaluator；不引入 LLM relevance judge 作为主指标。
- EverOS 类设计保留 `adapter.answer()`；我们的新主协议不再要求新 method 实现 answer。

## 设计目标

- 建立框架内部统一 `LLMClient` 协议。
- 建立标准 `LLMResponse`，供 answer reader、LLM judge、内置 method 白盒插桩和
  efficiency observation 使用。
- 第一批只实现 `openai_compatible` provider；它覆盖 OpenAI、本地/远程兼容网关、
  ohmygpt、DeepSeek 兼容接口、vLLM/Ollama/LM Studio 这类本地 OpenAI-compatible server。
- 为 Anthropic/Claude、Gemini、进程内 Hugging Face Transformers 预留 provider 边界。
- 支持 answer LLM、judge LLM、内置 method internal LLM 走统一配置结构。
- 支持 prompt profile 和 prompt file，并把 prompt profile/file fingerprint 写入 manifest。
- 不要求用户自定义黑盒 method 使用框架 LLM client；用户自定义 method 只需实现
  `add()` / `retrieve()`。

## 非目标

- 不在当前 Task 6 立即实现 Anthropic、Gemini 或进程内 Hugging Face provider。
- 不在 Phase 1 引入 retrieval relevance LLM metric。
- 不把原 SDK response 对象直接写入标准 artifact。
- 不强制所有第三方 method 的内部 LLM 立即迁移到统一 client；内置 method 逐步迁移。
- 不改变当前已验证实验的默认模型选择；Phase 1 真实调用仍默认 `gpt-4o-mini`。

## Provider 分层

### 第一层：OpenAI-compatible

第一版只实现：

```text
provider = "openai_compatible"
```

它使用 OpenAI Python SDK，并通过配置支持：

- `api_key` 或 `api_key_env`
- `base_url` 或 `base_url_env`
- `model`
- `temperature`
- `top_p`
- `max_output_tokens`
- `timeout_seconds`
- `max_retries`
- `extra_body`
- `extra_headers`

该层同时覆盖：

- OpenAI 官方 API。
- ohmygpt 等 OpenAI-compatible 中转服务。
- DeepSeek 等 OpenAI-compatible 服务。
- 本地 OpenAI-compatible server，如 vLLM、Ollama、LM Studio、llama.cpp server。

### 第二层：原生云厂商 provider

后续 provider：

```text
provider = "anthropic"
provider = "gemini"
```

它们需要独立 adapter，因为 SDK 返回结构、usage 字段、错误类型、retry/timeout 参数、
system/user message 语义都不同。接口仍统一为 `LLMClient.generate(...) -> LLMResponse`。

### 第三层：进程内本地开源模型

后续 provider：

```text
provider = "local_hf"
```

它通过 Hugging Face Transformers 在当前 Python 进程内加载模型。该方向可做，但复杂度
明显更高：

- 模型加载时间和显存管理。
- device / dtype / quantization。
- chat template 差异。
- batch 与线程安全。
- 真实 token usage 统计。
- 长上下文和 OOM 风险。
- 本地模型版本、revision、路径和 tokenizer 复现。

因此 Phase 1 不做进程内 HF provider。若用户需要本地开源模型，优先建议使用本地
OpenAI-compatible server 暴露接口，然后走 `openai_compatible` provider。

## 标准数据结构

### LLMUsage

```python
@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    measurement_source: str = "api_usage"
    metadata: dict[str, Any] = field(default_factory=dict)
```

说明：

- 字段缺失时用 `None`，不能用 `0` 伪装。
- `measurement_source` 用于区分 `api_usage`、`tokenizer_estimate`、`method_native`、
  `unsupported`。
- `cached_input_tokens`、`reasoning_tokens` 只在 provider 返回时记录，不主动估算。

### LLMResponse

```python
@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    usage: LLMUsage | None = None
    request_id: str | None = None
    finish_reason: str | None = None
    latency_ms: float | None = None
    raw_response: Any | None = None
    raw_response_json: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

设计原则：

- `text` 是业务层唯一必须依赖的输出。
- `usage` 是 efficiency observation 的主要来源。
- `raw_response` 可以保留原 SDK 对象，方便开发者白盒 debug，但不默认写入 artifact。
- `raw_response_json` 是尽力转换和脱敏后的 JSON-safe 副本，只在 debug 或审计配置开启时写。
- 标准 artifact 只写结构化、脱敏、可 JSON 序列化字段，避免 SDK 对象污染产物。

### LLMClient

```python
class LLMClient(Protocol):
    provider_name: str
    model_name: str

    def generate(self, request: LLMRequest) -> LLMResponse:
        ...
```

`LLMRequest` 至少包含：

- `prompt` 或 `messages`
- `temperature`
- `top_p`
- `max_output_tokens`
- `stop`
- `metadata`

第一版可以先让 framework answer reader 使用 plain prompt；后续再统一升级为 message
request，避免一次性重构所有调用点。

## 配置结构

建议引入通用配置对象：

```python
@dataclass(frozen=True)
class LLMRuntimeConfig:
    role: str
    provider: str
    model: str
    api_key: str | None = None
    api_key_env: str | None = None
    base_url: str | None = None
    base_url_env: str | None = None
    temperature: float | None = 0.0
    top_p: float | None = None
    max_output_tokens: int | None = None
    timeout_seconds: float = 60.0
    max_retries: int = 8
    extra_body: dict[str, Any] = field(default_factory=dict)
    extra_headers: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
```

配置文件示例：

```toml
[llm.answer]
provider = "openai_compatible"
model = "gpt-4o-mini"
api_key_env = "OPENAI_KEY"
base_url_env = "BASE_URL"
temperature = 0.0
max_output_tokens = 512
timeout_seconds = 60
max_retries = 8

[llm.judge]
provider = "openai_compatible"
model = "gpt-4o-mini"
api_key_env = "OPENAI_KEY"
base_url_env = "BASE_URL"
temperature = 0.0
max_output_tokens = 256
timeout_seconds = 60
max_retries = 8

[llm.methods.mem0.memory_build]
provider = "openai_compatible"
model = "gpt-4o-mini"
api_key_env = "OPENAI_KEY"
base_url_env = "BASE_URL"
timeout_seconds = 60
max_retries = 8
```

本地 OpenAI-compatible 模型示例：

```toml
[llm.answer]
provider = "openai_compatible"
model = "qwen2.5-7b-instruct"
api_key = "local"
base_url = "http://localhost:8000/v1"
temperature = 0.0
max_output_tokens = 512
timeout_seconds = 120
max_retries = 2
```

## Prompt 配置

Prompt 与 LLM 分离：

```toml
[prompts.answer]
profile = "locomo_default"
file = "configs/prompts/answer/locomo_default.txt"

[prompts.judge]
profile = "locomo_compact"
file = "configs/prompts/judge/locomo_compact.txt"
```

answer prompt 必须至少包含：

```text
{question}
{memory_context}
```

可选占位符：

- `{question_time}`
- `{conversation_id}`
- `{category}`
- `{options}`

judge prompt 必须显式声明可用字段，不得让 prompt builder 默默注入 gold answer 到 method
阶段。gold answer 只允许 evaluator 使用。

Manifest 应记录：

- prompt profile。
- prompt file 相对路径。
- prompt file sha256。
- LLM provider/model/参数 safe dict。
- 不记录 API key。

## 与现有 Task 6 的关系

当前 Task 6 已部分实现：

- `OpenAICompatibleAnswerLLMClient(settings=OpenAISettings)`
- `load_answer_prompt_template(...)`
- CLI `--answer-prompt-file`
- CLI `--answer-prompt-profile`

这是合理的 Phase 1 小步实现，但长期应迁移为：

```text
OpenAISettings
  -> LLMRuntimeConfig(provider="openai_compatible", role="answer")
  -> OpenAICompatibleLLMClient
  -> LLMResponse
  -> FrameworkAnswerReader
```

短期允许先完成 Task 6 当前实现，避免打断 retrieve-first 主线；随后再专门做
LLM provider config migration。

## 与内置 Method 的关系

内置 method 是白盒 adapter，我们可以逐步把它们内部可控 LLM 调用迁移到统一 LLM client：

- Mem0：memory build LLM、answer 兼容路径、embedding API timeout/retry。
- MemoryOS：LLM client wrapper、retrieval-stage/answer-stage observer。
- A-Mem：query keyword generation、memory evolution / answer 兼容路径。
- LightMem：memory manager、OP-update、reader prompt。

迁移原则：

- 不改变第三方 method 的核心算法流程。
- 可替换 provider/client adapter，但必须保持 prompt、参数和调用位置可复现。
- 内置 method profile 允许用户覆盖 internal LLM provider/model/base_url/timeout/retry。
- 用户自定义 method 不强制使用框架 LLM client；只要实现 `add()`/`retrieve()` 即可。

## Artifact 与 Observability

标准 answer artifact 不直接保存完整 raw SDK response。

建议保存：

- `answer_model`
- `answer_provider`
- `answer_prompt_profile`
- `answer_prompt_file_sha256`
- `llm_usage`
- `finish_reason`
- `request_id`
- `latency_ms`
- `measurement_source`

debug 模式可额外保存脱敏后的 `raw_response_json`。默认不写 `raw_response`。

Efficiency observation 应优先从 `LLMResponse.usage` 读取；缺失时再由 tokenizer 估算，并明确
标注 `measurement_source="tokenizer_estimate"`。

## 错误处理

- 未知 provider：启动前 `ConfigurationError`。
- API key 缺失：启动前 `ConfigurationError`。
- prompt 缺少必要占位符：启动前 `ConfigurationError`。
- provider 不支持某参数：启动前或 client 构造时 fail closed，不静默忽略核心参数。
- usage 缺失：允许业务继续，但 observation 必须标注 unsupported 或 tokenizer estimate。
- raw response 不可序列化：不能影响 prediction，只跳过 raw JSON 或写 debug warning。

## 实施顺序建议

1. 当前 Task 6 先完成 OpenAI-compatible framework reader 接线。
2. 新增 `memory_benchmark.llms` 包，定义 `LLMRuntimeConfig`、`LLMRequest`、`LLMUsage`、
   `LLMResponse`、`LLMClient`。
3. 把 `OpenAICompatibleAnswerLLMClient` 收敛为通用 `OpenAICompatibleLLMClient`。
4. 让 `FrameworkAnswerReader` 消费 `LLMResponse`，不再只消费纯字符串。
5. 更新 answer/judge efficiency observation 从 `LLMResponse.usage` 读取。
6. 增加 TOML profile 和 CLI 参数覆盖。
7. 逐步迁移 LLM judge。
8. 逐步迁移内置 method 的白盒 LLM 调用。
9. 后续再实现 Anthropic/Gemini provider。
10. 本地进程内 HF provider 只在真实需求出现后实施。

## 风险

- 过早做多 provider 会拖慢 retrieve-first 主线。
  - 处理：第一版只做 OpenAI-compatible。
- raw SDK response 直接进入 artifact 会造成不可复现、不可序列化和 secret 风险。
  - 处理：标准字段稳定，raw 只作为 debug。
- 用户误以为自定义黑盒 method 必须使用框架 LLM。
  - 处理：文档明确自定义 method 只需 `add()`/`retrieve()`。
- 本地 HF provider 复杂度过高。
  - 处理：先支持 OpenAI-compatible local server。
