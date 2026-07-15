# LightMem online-soft 主 profile 施工记录

> 施工者：Claude Sonnet 5（actor 池，本次会话按系统提示核实模型身份）。
> 日期：2026-07-15。任务卡：`../cards/actor-prompt-lightmem-online-soft-profile.md`。
> 裁决依据：`lightmem-update-lifecycle-ruling.md`。零真实 API，未 push。

## 1. 最终字段名

- `LightMemConfig.lifecycle_profile: str = "online_soft"`。合法值只有
  `LIGHTMEM_LIFECYCLE_PROFILES = ("online_soft", "locomo_offline_consolidated")`
  （`lightmem_adapter.py`），非法值在 `LightMemConfig.__post_init__` fail-fast。
- `LightMem.__init__(..., benchmark_name: str | None = None)`：与 Mem0/MemoryOS
  同款归一化（`.strip().lower()`，空/非 str 归 `None`）。
- `LightMem._validate_lifecycle_profile_benchmark_identity()`：构造期校验，
  `lifecycle_profile="locomo_offline_consolidated"` 且 `benchmark_name != "locomo"`
  时抛 `ConfigurationError`，在任何 `add()`/`ingest()` 调用之前。
- `LightMem._should_run_locomo_offline_consolidation() -> bool`：legacy `add()`
  与 v3 `end_conversation()` 共用的唯一判定点，返回
  `self.config.lifecycle_profile == "locomo_offline_consolidated"`（身份已在构造期
  验证，这里不重复判断，避免两处条件漂移）。
- `LIGHTMEM_ADAPTER_VERSION`: `"conversation-qa-v1"` → `"conversation-qa-v2"`。
- registry `_build_lightmem_system` 新增 `benchmark_name=context.benchmark_name`
  透传给 `LightMem(...)`。

## 2. 改动文件

- `src/memory_benchmark/methods/lightmem_adapter.py`：
  - `LightMemConfig` 加 `lifecycle_profile` 字段 + 校验；`LIGHTMEM_ADAPTER_VERSION`
    升级；新增 `LIGHTMEM_LIFECYCLE_PROFILES` 常量。
  - `LightMem.__init__` 加 `benchmark_name` 参数 + 构造期身份校验。
  - `add()`、`end_conversation()` 的全库 mutation 触发点从
    `_is_locomo_conversation(conversation)` / `self._is_native_locomo(namespace)`
    （数据形态启发式）改为统一调用 `_should_run_locomo_offline_consolidation()`
    （显式 profile + 已验证身份）。`_is_locomo_conversation`/`_is_native_locomo`
    本身未删除，仍用于选择 LoCoMo `METADATA_GENERATE_PROMPT`（与 consolidation
    触发无关的独立用途）。
- `src/memory_benchmark/methods/registry.py`：`_build_lightmem_system` 透传
  `benchmark_name=context.benchmark_name`。
- `configs/methods/lightmem.toml`：`[smoke]`、`[official_full]` 都显式加
  `lifecycle_profile = "online_soft"`，不依赖 dataclass 默认；补充说明注释。
- `tests/test_lightmem_adapter.py`：见 §4。
- `docs/reference/integration/lightmem.md`：更新"关键机理"段、B2 offline
  consolidation 覆盖面段、B6 段的过时"目标/待施工"表述为已实现现状；未改动顶部
  `method-frozen-v1 暂停` 状态行（该行"代码切换卡尚未强验收合入"在架构师验收前
  仍准确，验收状态由架构师裁定，不由 actor 自行翻转）。
- 本文件（新建）。

## 3. bridge / native 调用序列（equivalence 测试实测）

- **online_soft（默认）**：`add()`（legacy bridge）与 `ingest()+end_conversation()`
  （v3 native）在 LoCoMo 四 turn 场景下调用序列完全一致：4 次 `add_memory`
  （前 3 次 `force_segment=force_extract=False`，第 4 次 `True`）→ 检索时
  `embed_query` → `search`。序列中**不出现** `construct_update`/`offline_update`。
- **locomo_offline_consolidated（显式，且 `benchmark_name="locomo"`）**：序列尾部
  变为 `..., construct_update, offline_update, embed_query, search`；
  `offline_update` 调用参数保持既有 `score_threshold=0.8`（TOML repo 默认）不变。
- 两种 profile 下 `build_backend_config()` 产出的 backend config 均保持
  `update="offline"`（新增定向测试锁定，见 §1 术语裁决：改成 `update="online"`
  会命中官方空壳，导致 memory 不入库）。

## 4. 测试改动清单（`tests/test_lightmem_adapter.py`）

新增：

- `test_lightmem_config_rejects_invalid_lifecycle_profile`
- `test_lightmem_config_accepts_valid_lifecycle_profiles`（parametrize 两个合法值）
- `test_lightmem_config_manifest_includes_lifecycle_profile_and_adapter_version_v2`
- `test_lightmem_toml_profiles_declare_online_soft_lifecycle_explicitly`（真实读取
  `configs/methods/lightmem.toml` 的 smoke/official_full 两个 section）
- `test_lightmem_backend_config_always_uses_offline_update_regardless_of_lifecycle_profile`
  （parametrize 两个合法值）
- `test_lightmem_locomo_add_offline_consolidated_runs_official_offline_update_after_all_turns`
- `test_lightmem_locomo_offline_consolidated_requires_explicit_locomo_benchmark_identity`
- `test_native_lightmem_locomo_offline_consolidated_matches_bridge_force_and_update_sequence`

重命名/重写（旧行为断言未删除，改由上面的显式 `locomo_offline_consolidated`
测试承接）：

- `test_lightmem_locomo_add_runs_official_offline_update_after_all_turns`
  → `test_lightmem_locomo_add_online_soft_skips_offline_update`（默认 profile
  现断言不触发 update）。
- `test_native_lightmem_locomo_matches_bridge_force_and_update_sequence`
  → `test_native_lightmem_locomo_matches_bridge_online_soft_force_sequence`
  （默认 profile 现断言序列尾部不含 update，只有 `embed_query`/`search`）。

修复（施工中发现的既有测试隐式依赖，非任务卡枚举项，但为本次改动的直接回归，
按 actor 纪律就地修复而非停工）：

- `test_lightmem_buffers_threaded_offline_update_manager_usage`：该测试用
  `ThreadedUpdateFakeLightMemoryBackend.offline_update_all_entries` 模拟线程池内
  memory manager 调用，验证跨线程 usage 缓冲/回填机制；这条路径现在只在
  `locomo_offline_consolidated` 下触发，故显式加上该 profile 与
  `benchmark_name="locomo"`，其余断言（3 条 LLM record、token 数）不变。

扩展（非新增/重命名，追加断言）：

- `test_lightmem_registry_specializes_consume_granularity_by_benchmark`：新增
  `locomo.benchmark_name == "locomo"` / `longmemeval.benchmark_name ==
  "longmemeval"` / `halumem.benchmark_name == "halumem"` 三条断言，锁 registry
  factory 透传身份。

未改动、按任务卡要求保持覆盖不退化：HaluMem session capture、LongMemEval pair、
BEAM/MemBench turn 的既有定向测试（均已在自检整体通过中覆盖）。

## 5. 定向自检真实尾行

```
uv run pytest -q tests/test_lightmem_adapter.py tests/test_amem_lightmem_registry.py tests/test_method_registry.py
78 passed, 1 warning in 5.84s
```

（warning 为第三方 vendored 代码的 `PydanticDeprecatedSince20`，与本次改动无关，
非本次引入。）

第一次运行曾在 `test_lightmem_buffers_threaded_offline_update_manager_usage`
失败（`1 failed, 77 passed`），定位后按 §4"修复"条目就地修正并重跑，上方为
重跑后的干净尾行。

## 6. 偏差与停工点

无停工。与任务卡的唯一偏差：额外修复了 1 个任务卡未枚举、但因本次行为切换而
回归的既有测试（`test_lightmem_buffers_threaded_offline_update_manager_usage`，
详见 §4"修复"），未触碰其覆盖的生产逻辑，只调整其构造参数以匹配显式
`locomo_offline_consolidated` 语境。未使用 subagent，全部改动由本 actor 直接执行。
