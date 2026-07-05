# 2026-06-18 A-Mem Conversation State Persistence 交接

## 本轮目标

为 A-Mem 增加 conversation-level method state 持久化，支撑进程重启后的 resume。
用户明确要求：不要影响 A-Mem 核心算法流程。

## 已完成

- 新增设计：
  `docs/superpowers/specs/2026-06-18-amem-conversation-state-persistence-design.md`
- 新增计划：
  `docs/superpowers/plans/2026-06-18-amem-conversation-state-persistence.md`
- `src/memory_benchmark/methods/amem_adapter.py`
  - `AMem.__init__()` 增加 `storage_root`。
  - `add()` 在每个 conversation 完整写入后保存状态。
  - 新增 `load_existing_conversation_state(conversation)`。
  - 每个 conversation 状态目录包含：
    - `memories.pkl`
    - `retriever.pkl`
    - `retriever_embeddings.npy`
    - `state_manifest.json`
  - manifest 记录 schema、conversation id、adapter version、source SHA、profile、
    turn_count 和文件 SHA-256。
  - 加载时强校验 manifest、source/profile/checksum。
  - 通过官方 retriever `save(...)` / `load(...)` 保存和恢复检索器状态。
  - 不修改 `third_party/methods/A-mem/`。
- `src/memory_benchmark/methods/registry.py`
  - A-Mem factory 传入 `context.storage_root`。
  - 对 `context.completed_conversations` 调
    `system.load_existing_conversation_state(conversation)`。
- `tests/test_amem_adapter.py`
  - 增加保存状态文件测试。
  - 增加新实例加载后直接回答测试。
  - 增加 manifest profile mismatch 拒绝加载测试。
  - 所有会写状态的 fake 测试都改为使用 `tmp_path`，避免污染项目 `outputs/`。
- `tests/test_amem_registered_prediction.py`
  - 增加 registry factory 加载 completed conversations 的测试。
- 文档更新：
  - `AGENTS.md`
  - `docs/current-roadmap.md`
  - `docs/method-interface-inventory.md`
  - `docs/method-resource-parameter-audit.md`

## 当前语义

- A-Mem 支持 conversation-level resume。
- A-Mem 不支持 turn-level resume。
- 如果某个 conversation 写入中途崩溃，该 conversation 下次从头重写。
- 如果某个 conversation 已完成写入且 manifest 校验通过，resume 会加载状态并跳过重新
  add。
- question-level resume 仍由 runner 的 `method_predictions.jsonl` 处理。

## 2026-06-18 追加：LightMem Resume 补齐

用户要求四个 method 都具备写入记忆 conversation 级 resume 和问问题 resume。检查后发现
LightMem 存在一个缺口：completed conversation 被 runner 跳过 `add()` 后，若还有未回答
question，`get_answer()` 需要 `_backends[conversation_id]`，但新进程中该 backend 尚未
重建。

已补齐：

- `src/memory_benchmark/methods/lightmem_adapter.py`
  - 新增 `load_existing_conversation_state(conversation)`。
  - 方法只重建 backend 和 `_conversation_metadata`，不调用 `add_memory()`。
- `src/memory_benchmark/methods/registry.py`
  - LightMem factory 对 `context.completed_conversations` 调上述加载方法。
- `tests/test_lightmem_adapter.py`
  - 新增 completed conversation 恢复后直接回答测试。
- `tests/test_amem_lightmem_registry.py`
  - 新增 LightMem factory 加载 completed conversations 测试。

当前四个 method resume 状态：

| Method | 写入记忆 resume | 问问题 resume |
| --- | --- | --- |
| Mem0 | LoCoMo turn-level；LongMemEval conversation-level | `method_predictions.jsonl` |
| MemoryOS | conversation-level，恢复 JSON state | `method_predictions.jsonl` |
| A-Mem | conversation-level，恢复 memories/retriever/manifest | `method_predictions.jsonl` |
| LightMem | conversation-level，重建 backend | `method_predictions.jsonl` |

## 已验证

```bash
uv run pytest tests/test_amem_adapter.py -q
# 12 passed, 1 warning

uv run pytest tests/test_amem_registered_prediction.py tests/test_method_registry.py tests/test_config_profiles.py -q
# 22 passed

uv run pytest tests/test_amem_adapter.py tests/test_amem_registered_prediction.py tests/test_amem_lightmem_registry.py tests/test_cost_calibration_smoke.py tests/test_main_cli.py tests/test_method_registry.py tests/test_config_profiles.py -q
# 67 passed, 1 warning

uv run pytest tests/test_documentation_standards.py -q
# 5 passed

uv run python -m compileall -q src/memory_benchmark tests
# exit 0

git diff --check
# exit 0
```

追加 LightMem focused 验证：

```bash
uv run pytest tests/test_lightmem_adapter.py -q
# 16 passed, 1 warning

uv run pytest tests/test_amem_lightmem_registry.py -q
# 5 passed
```

本轮未执行真实 API。

## 未做

- 未执行真实 API。
- 未做 A-Mem turn-level resume。
- 未对 category 5 adversarial 放开 public-input 限制。
