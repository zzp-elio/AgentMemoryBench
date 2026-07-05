# 2026-06-20 01:00 UTC — A-Mem / LightMem API retry/timeout 兜底修复

## 1. 读了哪些文件

- `src/memory_benchmark/methods/amem_adapter.py`：AMemConfig (line 60-119)、`_ensure_openai_base_url()` (line 537-557)、`_create_openai_compatible_client()` (line 865-874)
- `src/memory_benchmark/methods/lightmem_adapter.py`：LightMemConfig (line 79-139)、`_create_official_backend()` (line 558-575)、`_get_or_create_backend()` (line 541-556)、`__init__()` (line 264-311)
- `configs/methods/amem.toml`：smoke/official_full profile
- `configs/methods/lightmem.toml`：smoke/official_full profile
- `configs/methods/mem0.toml`：对照 reference（已有 api_timeout_seconds=60.0, api_max_retries=8）
- `configs/methods/memoryos.toml`：对照 reference（已有 api_timeout_seconds=120, api_max_retries=8）
- `tests/test_amem_adapter.py`：`test_amem_replaces_official_openai_client_when_base_url_is_configured` (line 493-560)

## 2. 根因

**之前审计结论**：MemoryOS 和 Mem0 的 OpenAI client 已注入 timeout + retry，但 A-Mem 和 LightMem 缺少：

- **A-Mem**：`_create_openai_compatible_client()` 只创建 `OpenAI(api_key=api_key, base_url=base_url)`，无 `timeout`/`max_retries`。AMemConfig 没有对应配置字段。网络故障时 client 默认 timeout=None（无限等待），重试也仅依赖 vendored `@retry_llm_call(max_retries=2)` 硬编码。

- **LightMem**：vendor 的 `OpenaiManager.__init__()` 创建 `httpx.Client(verify=False)` 和 `OpenAI(api_key=..., base_url=..., http_client=http_client)`，均无显式 timeout/max_retries。LightMemConfig 无对应字段。

## 3. 修改了哪些文件，每个文件改了什么

### 文件 1: `src/memory_benchmark/methods/amem_adapter.py`

**3a. AMemConfig** — 新增 2 个字段，放在无默认值的 `max_workers` 之后：

```python
api_timeout_seconds: float = 60.0
api_max_retries: int = 8
```

`__post_init__` 新增校验：
```python
if self.api_timeout_seconds <= 0:
    raise ConfigurationError("A-Mem api_timeout_seconds must be positive")
if self.api_max_retries < 0:
    raise ConfigurationError("A-Mem api_max_retries cannot be negative")
```

**3b. `_create_openai_compatible_client()`** — 新增 `timeout` 和 `max_retries` 参数：

旧签名：`(api_key, base_url) -> OpenAI(api_key=api_key, base_url=base_url)`

新签名：`(api_key, base_url, timeout, max_retries) -> OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=max_retries)`

**3c. `_ensure_openai_base_url()`** — 调用时传入 config 值：

```python
llm.client = _create_openai_compatible_client(
    api_key=self._openai_api_key,
    base_url=self._openai_base_url,
    timeout=self.config.api_timeout_seconds,
    max_retries=self.config.api_max_retries,
)
```

### 文件 2: `src/memory_benchmark/methods/lightmem_adapter.py`

**3d. LightMemConfig** — 新增 2 个字段，放在 `max_workers` 之后：

```python
api_timeout_seconds: float = 60.0
api_max_retries: int = 8
```

`__post_init__` 新增校验：
```python
if self.api_timeout_seconds <= 0:
    raise ConfigurationError("LightMem api_timeout_seconds must be positive")
if self.api_max_retries < 0:
    raise ConfigurationError("LightMem api_max_retries cannot be negative")
```

**3e. `_create_official_backend()`** — backend 构造完成后调用新方法注入 timeout/retry：

```python
backend = self._suppress_stdout_if_needed(lightmemory_cls.from_config, backend_config)
self._inject_api_retry_timeout(backend, conversation_id)
return backend
```

**3f. 新增 `_inject_api_retry_timeout()`** — 对 vendored memory manager 的 OpenAI client 调 `with_options()`：

```python
def _inject_api_retry_timeout(self, backend, conversation_id):
    manager = getattr(backend, "manager", None)
    if manager is None or not hasattr(manager, "client"):
        return
    client = manager.client
    with_options = getattr(client, "with_options", None)
    if not callable(with_options):
        return
    manager.client = with_options(
        timeout=self.config.api_timeout_seconds,
        max_retries=self.config.api_max_retries,
    )
```

不修改第三方源码，只对已构造的 client 注入网络参数（与 Mem0 的 `_configure_backend_openai_clients()` 同模式）。

### 文件 3: `configs/methods/amem.toml`

smoke 和 official_full 均新增：
```toml
api_timeout_seconds = 60.0
api_max_retries = 8
```

### 文件 4: `configs/methods/lightmem.toml`

smoke 和 official_full 均新增：
```toml
api_timeout_seconds = 60.0
api_max_retries = 8
```

### 文件 5: `tests/test_amem_adapter.py`

`test_amem_replaces_official_openai_client_when_base_url_is_configured`：

- mk monkeypatch lambda 签名从 `lambda api_key, base_url:` 改为 `lambda api_key, base_url, timeout, max_retries:`
- 断言中的字典增加 `"timeout": 60.0, "max_retries": 8`

## 4. 跑了哪些测试，完整结果

```bash
# focused
uv run pytest tests/test_amem_adapter.py tests/test_lightmem_adapter.py \
  tests/test_method_registry.py tests/test_config_profiles.py \
  tests/test_documentation_standards.py -q
# 59 passed, 2 warnings

# 宽回归
uv run pytest tests/test_amem_adapter.py tests/test_lightmem_adapter.py \
  tests/test_amem_lightmem_registry.py tests/test_amem_registered_prediction.py \
  tests/test_lightmem_registered_prediction.py tests/test_method_registry.py \
  tests/test_config_profiles.py tests/test_prediction_runner.py \
  tests/test_main_cli.py tests/test_cost_calibration_smoke.py \
  tests/test_documentation_standards.py -q
# 157 passed, 2 warnings

# compileall
uv run python -m compileall -q src/memory_benchmark tests
# exit 0

# git diff --check
# exit 0
```

未执行真实 API smoke — timeout/retry 在真实断网场景的行为需后续真实 API smoke 验证。

## 5. 已知风险或未解决问题

1. **A-Mem 的 vendored `@retry_llm_call` 仍存在**：hardcoded `max_retries=2`，捕获 `Exception`（过宽，包含 ValueError/TypeError 等非网络错误）。我们的 `with_options()` 加了 SDK 级别的 retry=8，现在实际是 SDK 先做 8 次网络重试，如果 8 次都失败抛异常，再由 `@retry_llm_call` 再重试 2 次。效果上 A-Mem 比 Mem0 多了额外的非网络错误重试。暂不处理，因为没有副作用。
2. **LightMem `with_options()` 会创建新 httpx.Client**：OpenAI SDK 的 `with_options()` 会重建 httpx.Client，可能丢失 vendored `OpenaiManager` 中 `verify=False` 的设置。在标准 ohmygpt 代理环境下这是正确行为（应该验证 SSL），但若 ohmygpt 证书特殊可能需额外排查。
3. **未执行真实 API 断网测试**：修复后未模拟 SSL 断连场景验证重试实际发生。建议后续用极小 smoke 验证（断网 / 限流场景），或在下次 full 实验中观察 `APIConnectionError` 是否被正确重试。

## 6. 卡点与下一步建议

**无卡点。** 修复完成，建议：

1. 等 Mem0 full-v4 跑完后，将 A-Mem 和 LightMem 的 API retry/timeout 在 task-ledger 中标记为 closed
2. 下次计划跑 full 实验时，考虑是否顺便跑一个故意短 timeout 的 smoke 验证重试链路
3. vendored `@retry_llm_call` 的宽泛异常捕获可长期负债
