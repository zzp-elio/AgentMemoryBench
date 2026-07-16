# LightMem hybrid role profile 施工记录

> 日期：2026-07-16。Actor：OpenCode + qwen3.7-max。
> 基线：main `ea8cb85`。分支：`actor/lightmem-hybrid-role-profile`。
> 定向自检：`112 passed, 1 warning in 6.01s`。

## 1. 变更摘要

把 Phase 1 五 benchmark 的 unified 主 build 从硬编码 `messages_use="user_only"` 改为
显式 `hybrid`，用通用 role-slot normalizer 保留真实 role、只补结构占位，并把 pair
候选 child ids 作为纯观测链路传到底层 payload。不改 LightMem 抽取/分段/embedding/
update/retrieval 算法核心，不改 benchmark adapter。

## 2. 文件变更清单

### 框架代码

| 文件 | 变更 |
|---|---|
| `configs/methods/lightmem.toml` | 两 profile 显式声明 `messages_use = "hybrid"` |
| `src/memory_benchmark/methods/lightmem_adapter.py` | `LightMemConfig` 新增 `messages_use` 强校验；`LIGHTMEM_ADAPTER_VERSION` 升至 `conversation-qa-v4`；`build_backend_config` 从 config 读取；通用 `_normalize_session_to_pairs` 替换旧 LME/LoCoMo 分流；`_build_retrieval_evidence` 逐 benchmark 诚实矩阵；`_retrieved_items_from_lightmem_memories` 只信任 plural `source_external_ids` |

### third_party（vendored，仅过滤框架 marker / 增加观测 lineage）

| 文件 | 函数 | 理由 |
|---|---|---|
| `third_party/methods/LightMem/src/lightmem/factory/memory_buffer/short_term_memory.py` | `ShortMemBufferManager._count_tokens()` | 跳过 `memory_benchmark_structural_placeholder=True` 的 slot，使 hybrid 下 LoCoMo token count 与 user_only 严格相等 |
| `third_party/methods/LightMem/src/lightmem/factory/memory_manager/openai.py` | `OpenaiManager._extract_with_prompt()` 内 `concatenate_messages()` | 同上 marker 过滤，使 extraction prompt 字节严格相等 |
| `third_party/methods/LightMem/src/lightmem/memory/utils.py` | `MemoryEntry` 新增 `source_external_ids` 字段；`assign_sequence_numbers_with_timestamps` 收集 plural 并行数组；`convert_extraction_results_to_memory_entries` / `_create_memory_entry_from_fact` 传递 plural | pair candidate ids 穿过抽取管线到 MemoryEntry |
| `third_party/methods/LightMem/src/lightmem/memory/lightmem.py` | `add_memory` 解包 7 元组；`offline_update` 条件写 plural payload | 初始 insert 写入 plural 供 adapter v4 检索读取 |

以上 third_party 改动只过滤框架 marker / 增加观测 lineage，不改算法核心流程。

### 测试

| 文件 | 变更 |
|---|---|
| `tests/test_lightmem_adapter.py` | 版本 v3→v4；TOML 检查 messages_use；sequence assignment 7 元组；bridge 测试加 `benchmark_name`；fake retriever payload 加 plural；新增 config/normalizer/evidence 强反例 |
| `tests/test_amem_lightmem_registry.py` | 无变更 |
| `tests/test_method_registry.py` | 无变更 |
| `tests/test_lightmem_registered_prediction.py` | 无变更 |

## 3. 关键设计决策

### 3.1 通用 role-slot normalizer

- LoCoMo（`benchmark_name == "locomo"`）：每条真实 utterance → `[real user, placeholder assistant]`；两 slot 同 speaker/time；placeholder 带 marker。
- 其余四家：读 `normalized_role`（只接受 user/assistant）；正常 pair 直接成对；user-user/dangling user 补 placeholder assistant；orphan assistant 补 placeholder user；不前瞻消费下一 turn。
- 缺 benchmark identity 且遇到非 user/assistant role 时 fail-fast。

### 3.2 placeholder 对算法输入的处理

只在两处 vendored 观测边界跳过 marker=True 的 slot：
1. `ShortMemBufferManager._count_tokens()`：placeholder 不计 content/分隔符。
2. `OpenaiManager` 的 `concatenate_messages()`：placeholder 不渲染 extraction 行。

不按 `content==""` 跳过；真实空 message 与结构 placeholder 语义不同。

### 3.3 pair candidate lineage

- normalizer 为每个 pair 计算稳定去重的 `source_external_ids`；两 slot 携带同一集合。
- `MemoryEntry` 新增 `source_external_ids: list[str]`；只有集合恰好一个 id 时保留 legacy singular。
- adapter v4 检索只信任合法、非空、稳定去重的 plural 并形成 `RetrievedItem.source_turn_ids` tuple。

### 3.4 RetrievalEvidence 逐 benchmark 矩阵

| benchmark | status | granularity |
|---|---|---|
| LoCoMo + online_soft + items 可用 | valid | turn |
| LoCoMo + items=None | n_a | none |
| MemBench | pending | none |
| LongMemEval | n_a | none |
| BEAM | n_a | none |
| HaluMem | n_a | none |
| identity 缺失 | pending | none |
| consolidated | n_a | none |

## 4. 停工/偏差

无停工。一处偏差：卡内 §2.2 要求 orphan assistant 与下一 user 配对，但 native pair 路径无法前瞻下一 turn，改为 orphan assistant 补 placeholder user（不消费下一 turn），保证 bridge/native 等价。
