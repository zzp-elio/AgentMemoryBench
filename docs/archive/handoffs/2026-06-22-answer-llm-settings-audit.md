# 2026-06-22 Answer LLM 参数审计交接

时间：2026-06-22

## 用户最新问题

用户确认四个 method adapter 已迁移到：

```text
add(conversation)
retrieve(question) -> AnswerPromptResult.answer_prompt
framework answer LLM(answer_prompt) -> answer
```

随后提出关键问题：

1. 旧链路直接走各 method 的 `get_answer()`，answer LLM 参数隐藏在 method 内部。
2. 新链路把 answer prompt 与 answer LLM 剥离后，必须知道每个 method 官方 answer LLM 的
   `temperature`、`max_tokens`、`top_p` 等参数。
3. 需要确认各 method 内部 API/network retry/timeout 兜底机制是否仍然存在。
4. 上下文即将压缩，因此需要写交接。

## 已完成审计

审计结果已写入：

- `docs/method-resource-parameter-audit.md`
- `docs/task-ledger.md`
- `docs/current-roadmap.md`

验证：

```bash
uv run pytest tests/test_documentation_standards.py -q
git diff --check
```

结果：

- 文档规范：`5 passed`
- `git diff --check`: exit 0

## Mem0 LoCoMo / LongMemEval answer LLM 参数确认

事实来源：

- `third_party/methods/mem0-main/memory-benchmarks/benchmarks/common/llm_client.py`
- `third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/run.py`
- `third_party/methods/mem0-main/memory-benchmarks/benchmarks/longmemeval/run.py`

官方 `LLMClient.generate()` 默认签名：

```python
async def generate(
    self,
    system: str,
    user: str,
    temperature: float = 0,
    max_tokens: int = 4096,
) -> str:
    ...
```

LoCoMo 调用：

```python
generated_answer = await answerer.generate(system="", user=gen_prompt)
```

LongMemEval 调用：

```python
generated_answer = await answerer.generate(system="", user=gen_prompt)
```

因此：

- Mem0 LoCoMo answer LLM：`temperature=0`, `max_tokens=4096`
- Mem0 LongMemEval answer LLM：`temperature=0`, `max_tokens=4096`
- `system=""`
- 官方代码未显式设置 `top_p`、`stop`、`response_format`
- OpenAI-compatible provider 会把 `max_tokens` 传给 chat completions；gpt-5/o-series 才切换为
  `max_completion_tokens`，但本项目阶段一固定 `gpt-4o-mini`

结论：Mem0 两个 benchmark 的 answer LLM 参数一致。没有发现额外 benchmark-specific answer
采样参数。

## 四个 method 官方 answer LLM 参数总表

| Method / Benchmark | 官方 answer LLM 参数 |
| --- | --- |
| Mem0 LoCoMo | `temperature=0`, `max_tokens=4096`, `system=""`; `top_p` 未设置 |
| Mem0 LongMemEval | `temperature=0`, `max_tokens=4096`, `system=""`; `top_p` 未设置 |
| A-Mem LoCoMo category 1/2/3/4 | `temperature=0.7`, `max_tokens=1000`; `top_p` 未设置 |
| A-Mem LoCoMo category 5 | `temperature_c5=0.5`, `max_tokens=1000`，但需要 gold answer 构造候选项，当前按 public-input 规则不跑 |
| LightMem LoCoMo | `temperature=0.0`; `max_tokens`、`top_p` 未设置；官方把完整 prompt 作为 `system` message 发送 |
| LightMem LongMemEval | `temperature=0.0`, `top_p=0.8`, `max_tokens=2000` |
| MemoryOS LoCoMo | `temperature=0.7`, `max_tokens=2000`; `top_p` 未设置 |

这张表已足够进入下一步实现显式配置。对未设置字段的处理规则应是：

- 在配置 / manifest 中记录为 `null` 或 `not_set`。
- 不要把未设置字段擅自补成 OpenAI 默认值并声称是官方参数。
- 如果框架实现需要传参，只传官方显式参数；未设置的字段不传。

## API / Network 兜底状态

四个 method 内部 OpenAI-compatible API/network 兜底仍在：

| Method | 兜底状态 |
| --- | --- |
| Mem0 | `api_timeout_seconds=60.0`, `api_max_retries=8`；adapter 对 vendored Mem0 LLM 和 embedding client 调 `with_options(timeout=..., max_retries=...)` |
| A-Mem | `api_timeout_seconds=60.0`, `api_max_retries=8`；adapter 替换官方 robust OpenAI client，显式带 `base_url`、timeout、max_retries |
| LightMem | `api_timeout_seconds=60.0`, `api_max_retries=8`；adapter 对 LightMem memory manager client 调 `with_options(timeout=..., max_retries=...)` |
| MemoryOS | `api_timeout_seconds=120`, `api_max_retries=8`，并有 `api_retry_wait_seconds=5`、指数退避和 `api_retry_max_wait_seconds=60`；adapter 使用自己的 `_chat_completion_with_retry()` |

framework answer LLM 当前也有基础兜底：

- `timeout_seconds=30.0`
- `max_retries=2`

但它还没有和 method official answer 参数统一建模。

## 当前缺口

当前 framework answer LLM client 只显式配置：

- API key
- base URL
- model=`gpt-4o-mini`
- timeout
- max_retries

尚未显式配置：

- `temperature`
- `max_tokens`
- `top_p`
- message role（LightMem LoCoMo 官方把完整 prompt 作为 `system` message，当前框架统一作为 `user`）

因此：

- 可以做极小 smoke 验证链路是否能跑通。
- 不建议在补齐 `AnswerLLMSettings` 前跑正式 full 并声称完全对齐官方 answer LLM 参数。

## 下一步建议

优先实现 `AnswerLLMSettings` 或等价配置，而不是马上启动 full：

1. 新增配置结构，字段至少包括：
   - `model`
   - `temperature: float | None`
   - `max_tokens: int | None`
   - `top_p: float | None`
   - `message_role: Literal["user", "system"]`
   - `timeout_seconds`
   - `max_retries`
2. 在 method profile 或 registry 中给四个 method/benchmark 组合设置默认 answer LLM 参数：
   - Mem0 LoCoMo/LongMemEval: temp 0, max_tokens 4096, role user
   - A-Mem LoCoMo: temp 0.7, max_tokens 1000, role user
   - LightMem LoCoMo: temp 0.0, role system, max_tokens/top_p 不传
   - LightMem LongMemEval: temp 0.0, top_p 0.8, max_tokens 2000, role user
   - MemoryOS LoCoMo: temp 0.7, max_tokens 2000, role should follow reconstructed official messages if possible
3. `OpenAICompatibleAnswerLLMClient` 按 `None` 规则只传已显式配置字段。
4. manifest / model inventory / efficiency observation 中记录最终 answer LLM 参数。
5. focused tests 先覆盖参数透传和 `None` 不传。

## 恢复时不要做

- 不要启动 full 实验。
- 不要在未实现显式 answer LLM 参数前宣称 retrieve-first full 可复现官方配置。
- 不要移除四个 method 内部已有 retry/timeout 注入。
- 不要把未设置的官方字段填成猜测值。
