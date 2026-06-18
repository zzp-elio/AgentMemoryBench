# 2026-06-17 LightMem LoCoMo 专门化交接

## 交接时间

2026-06-17 23:32 CST 左右。用户提醒 5h 额度剩余约 8%，因此在当前切片完成后暂停并写交接。

## 用户最新决策

- LightMem + LoCoMo 需要专门化，使用 LightMem 自己的
  `third_party/methods/LightMem/experiments/locomo/search_locomo.py` 逻辑。
- LightMem + LongMemEval 保持更通用的官方 `run_lightmem_gpt.py` 路径，即
  `LightMemory.retrieve(item["question"], limit=20)` 加 LongMemEval reader prompt。
- 不启动真实 API；当前只做 adapter 代码和离线测试。

## 本轮已完成代码

修改文件：

- `src/memory_benchmark/methods/lightmem_adapter.py`
- `tests/test_lightmem_adapter.py`
- `AGENTS.md`

### LightMem LoCoMo 写入

`LightMem.add()` 在 LoCoMo conversation 写入全部 turn 后，会自动执行官方
`add_locomo.py` 的 post-build offline update：

```python
construct_update_queue_all_entries()
offline_update_all_entries(score_threshold=0.9)
```

这符合 runner 视角的语义：`add()` 返回后，该 conversation 的记忆应处于可检索状态。

### LightMem LoCoMo 回答检索

`LightMem.get_answer()` 现在按 benchmark 来源分支：

- LongMemEval：继续调用 `backend.retrieve(question.text, limit=config.retrieve_limit, filters=None)`。
- LoCoMo：不再调用 `backend.retrieve()`，改为复刻 `search_locomo.py` 的 combined vector retrieval：
  - 从 `backend.embedding_retriever.get_all(with_vectors=True, with_payload=True)` 读取 Qdrant entries。
  - 用 `backend.text_embedder.embed(question.text)` 生成 query embedding。
  - 对 entry vectors 计算 cosine similarity。
  - 按 score 降序取 `config.retrieve_limit`；LoCoMo official-mini 当前为 60。
  - 从 payload 读取 `speaker_name`，写入 `_retrieved_speaker`，供 speaker-organized prompt 使用。
  - memory 格式改为官方 `format_related_memories()` 风格：
    `[Memory recorded on: 01 January 2026, Thu]\n{memory}`。

已核实官方 LightMem `Qdrant.get_all()` 返回 `p.model_dump()` 后的 dict list，因此当前实现按
dict 读取 `id/vector/payload` 与官方 `experiments/locomo/retrievers.py` 一致。

### 测试覆盖

新增/更新 fake tests 覆盖：

- LoCoMo `add()` 后执行 `construct_update_queue_all_entries()`。
- LoCoMo `add()` 后执行 `offline_update_all_entries(score_threshold=0.9)`。
- LoCoMo `get_answer()` 使用 Qdrant payload/vector search，不调用 `backend.retrieve()`。
- LoCoMo prompt 包含 Alice/Bob speaker memory sections。
- LongMemEval 仍然不执行 LoCoMo offline update，继续走通用 retrieve path。

已执行：

```bash
uv run pytest tests/test_lightmem_adapter.py -q
```

结果：

```text
15 passed, 1 warning
```

warning 来自第三方 LightMem 的 Pydantic deprecated class config，不是本项目失败。

## 2026-06-18 续跑更新

已完成交接中列出的文档同步：

- `docs/current-roadmap.md`
- `docs/method-resource-parameter-audit.md`
- `docs/method-interface-inventory.md`
- `docs/superpowers/plans/2026-06-17-method-official-profile-alignment.md`
- `AGENTS.md`

已把 stale 结论改为当前事实：

- LoCoMo `search_locomo.py` 风格 Qdrant payload/vector 检索已实现。
- LoCoMo `add()` 后的 `construct_update_queue_all_entries()` 和
  `offline_update_all_entries(score_threshold=0.9)` 已实现。
- LongMemEval OP-update 仍是未实现的 future profile；当前 LongMemEval 保持
  `LightMemory.retrieve()` online 路径。

续跑验证：

```bash
uv run pytest tests/test_lightmem_adapter.py tests/test_lightmem_registered_prediction.py tests/test_amem_lightmem_registry.py tests/test_cost_calibration_smoke.py tests/test_main_cli.py -q
```

结果：`49 passed, 1 warning`。

```bash
uv run pytest tests/test_documentation_standards.py -q
```

结果：`5 passed`。

```bash
uv run python -m compileall -q src/memory_benchmark tests
```

结果：exit 0。

补充 A-Mem focused 回归：

```bash
uv run pytest tests/test_amem_adapter.py tests/test_amem_registered_prediction.py tests/test_amem_lightmem_registry.py tests/test_cost_calibration_smoke.py tests/test_main_cli.py -q
```

结果：`43 passed, 1 warning`。

未执行真实 API。

## 当前未完成事项

下一窗口恢复后不要重复大范围扫描历史文档，直接做下面事项：

1. 视用户确认再决定是否提交本轮改动。当前未自动 commit。
2. 若要进入真实 API smoke，必须先确认 API 预算、样本规模和正式 run_id。
3. LongMemEval OP-update 如需支持，应作为独立 future profile 另行设计，不要混入当前
   online `official-mini` 路径。

## 当前风险与注意

- 未执行真实 API smoke，因此只能说 LightMem LoCoMo 官方搜索路径已经离线对齐，不能说真实
  Table 3 复现已完成。
- LoCoMo 专门化只针对 LightMem；不要把这个 Qdrant payload search 逻辑挪到其他 method。
- LongMemEval 保持 `LightMemory.retrieve()` 路径；不要把 LoCoMo `search_locomo.py` 逻辑套到 LongMemEval。
- OP-update 在 LightMem 论文 Table 2 中对应 LongMemEval offline parallel update，目前仍未实现为独立 profile。
- 工作区还有 A-Mem 相关未提交改动和用户/历史 docs 删除，不要误 revert。

## 工作区状态提示

本轮开始前已有未提交改动：

- A-Mem adapter 和测试相关改动。
- 若干旧 docs 删除。
- `docs/handoffs/2026-06-17-amem-red-tests-handoff.md`。
- `docs/method-native-interface-inventory-opencode-deepseekV4pro.md`。

本轮新增/修改主要是 LightMem adapter、LightMem tests、AGENTS 和本 handoff。
