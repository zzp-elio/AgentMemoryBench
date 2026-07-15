# LightMem online-soft 缺失时间兼容 Phase B 实现记录

> 日期：2026-07-15。执行者：Claude Code（Opus 4.8）actor 会话。
> 性质：按 `lightmem-missing-time-compatibility-ruling.md` 的裁定，为 online-soft 增加
> “缺失 source timestamp 原样保持 None”的输入兼容扩展；零真实 API、零模型下载。
> 分支 `actor/lightmem-missing-time-online-soft`，worktree
> `/Users/wz/Desktop/mb-actor-lightmem-missing-time`。

## 1. 已裁契约落地

- 新增 `LightMemConfig.missing_timestamp_policy`，取值只允许 `preserve_none` / `require`。
  默认取严格值 `require`（避免 dataclass 默认暗中启用 preserve_none），构造期校验：
  - 非法取值 → `ConfigurationError`；
  - `preserve_none` 只允许与 `lifecycle_profile="online_soft"` 组合，
    `preserve_none + locomo_offline_consolidated` 在构造期即被拒绝。
- 字段进入 `to_manifest()`（`asdict(self)` 自动携带）；`LIGHTMEM_ADAPTER_VERSION`
  由 `conversation-qa-v2` 升为 `conversation-qa-v3`，锁死 resume identity——旧 v2
  manifest 由既有全 manifest `==` 比较拒绝续跑。
- `configs/methods/lightmem.toml` 的 `[smoke]` 与 `[official_full]` 都显式写
  `missing_timestamp_policy = "preserve_none"`，不依赖默认。
- 未引入任何 `benchmark_name == "membench"` 特判；policy 是 method/profile 能力，实际是否
  触发由输入 timestamp 是否缺失决定。timestamped 的 LoCoMo/LongMemEval/HaluMem/BEAM/
  MemBench 路径继续走原逻辑。

## 2. 第三方（vendored）改动清单与定性

允许修改范围内的 vendored 文件与函数，均属“缺失输入兼容”，不改核心算法流程：

1. `third_party/methods/LightMem/src/lightmem/memory/lightmem.py`
   - `MessageNormalizer.normalize_messages`：新增 `time_stamp is None` 分支，深复制并令
     `session_time`/`time_stamp`/`weekday` 为 None，不生成 offset/sentinel/墙钟，不更新
     `last_timestamp_map`。空字符串等非法值仍按原逻辑报错。normalizer 不感知 framework
     policy，只保证 None 能被无损表示。**非空 timestamp 分支一字未改。**
   - `LightMemory.retrieve`：格式化循环新增 `time_stamp is None` 分支，只输出 memory 文本，
     避免字面量 `"None None"`。**非空 timestamp 的 `f"{time_stamp} {weekday} {memory}"`
     格式保持不变。**
2. `third_party/methods/LightMem/src/lightmem/memory/utils.py`
   - `assign_sequence_numbers_with_timestamps`：None session 分组跳过 datetime 解析与
     `time_stamp` 覆写（`if sess_time is None: continue`），但下方第二个循环仍按原
     `extract_list` 顺序为其分配 `sequence_number` 并追加 timestamps/weekday/speaker/
     external_ids 五条并行数组，索引对齐不变。
   - `_create_memory_entry_from_fact`：把 weekday/speaker/external_id 的读取移到 timestamp
     转换之前，并对 `time_stamp is None` 单独分支（`float_time_stamp=None`），使缺失时间
     不再触发原“宽 catch 一并清空 speaker/topic/external_id”的兜底。真正的 IndexError/
     ValueError 仍落入原兜底。

为何不是核心流程变更：online-soft（Phase 1 主 profile）在 vendored 层由
`update="offline" → offline_update(memory_entries)` 的 direct insert 实现——只 embed + 写
payload，不调用 `construct_update_queue_all_entries` / `offline_update_all_entries` /
summary/window。缺失时间的 None 分支只关闭“不存在的时间前缀 + 时间 payload”，不介入
embedding、direct insert 或向量相关性检索顺序。裁决 §3/§5 已确认这属窄扩展。

## 3. timestamped 路径不变的证据

- 定向测试 `test_lightmem_turn_timestamp_adapts_month_name_dates_without_mutating_source`、
  `test_lightmem_month_name_timestamp_is_accepted_by_official_normalizer`、
  `test_lightmem_normalizer_preserves_none_alongside_timestamped_message`（混合用例第 0 条）
  共同验证非空 timestamp 的 ISO/weekday/offset/session_time 输出与既有一致。
- `test_lightmem_vendored_retrieve_omits_time_label_for_null_payload` 第二条断言 timestamped
  payload 仍格式化为 `"2023-05-20T00:00:00.000 Sat timed memory"`。
- LoCoMo/LongMemEval/HaluMem 既有 adapter 测试与 `test_method_registry.py`、
  `test_amem_lightmem_registry.py` 全绿，无退化。

## 4. online / consolidated 边界

- 缺失时间只允许进入 online-soft direct insert + 向量相似度 retrieve。
- `require` gate 挡在 backend 创建前：legacy `add()` 已改为“先纯 batch 预检再创建 backend”
  （不改成功路径 add_memory 调用序列）；native `ingest()` 本就先建 batch 再建 backend；
  HaluMem session 也改为先构造消息再建 backend。三者在缺失输入 + require 下都于 backend
  工厂计数为 0 时 fail-fast（`test_lightmem_require_policy_fails_before_backend_creation`）。
- `locomo_offline_consolidated` 仍强制 `require`（构造期拒绝 preserve_none 组合），全库
  update/delete 整合的 force/update 次序由既有
  `test_lightmem_locomo_add_offline_consolidated_runs_official_offline_update_after_all_turns`
  保证（现以默认 require + 完整 timestamp 运行，行为不变）。

## 5. lineage 强反例

- `test_lightmem_memory_entry_from_missing_time_keeps_lineage`：timestamp None → MemoryEntry
  的 `time_stamp`/`float_time_stamp` 为 None，但 `speaker_id="B"`、`speaker_name="Bob"`、
  `topic_id=7`、`source_external_id="e2"` 完整。
- `test_lightmem_sequence_assignment_keeps_none_group_aligned`：混合时/无时消息顺序与五条
  并行数组对齐（sequence 0/1、weekday `["Sat", None]`、speaker `["A","B"]`、
  external `["e1","e2"]`），None 不被解析。
- `test_lightmem_online_soft_preserve_none_passes_missing_time_to_backend`：bridge 与 native
  两路都把无时间 noise 的完整 content + `time_stamp=None` 送达 backend，零 synthetic time。

## 6. 定向测试真实尾行

`uv run pytest -q tests/test_lightmem_adapter.py tests/test_amem_lightmem_registry.py
tests/test_method_registry.py`：

```
87 passed, 1 warning in 5.72s
```

（唯一 warning 是 vendored Pydantic V2 class-based config Deprecation，与本卡无关。）

## 7. 偏差与声明

- 无 plan 偏差、无停工点。
- 明确声明：**MemBench 100k 上 LightMem online-soft 的缺失时间结果属于
  framework-extended missing-time compatibility，不是 upstream LightMem 对 None 的
  native parity**。报告披露必须携带 `missing_timestamp_policy=preserve_none` 与
  framework-extended 声明。
- 未使用 subagent。

## 8. 架构师 R1 验收返工

架构师复核 `e1cfb75` 后指出三处边界未锁实，本轮（follow-up commit，不 amend）修复，不重做
Phase B、不改 online-soft 算法：

1. **R1-1 只扩展 explicit None**：首轮 `normalize_messages` 用 `msg.get("time_stamp")`
   把“缺 `time_stamp` 键”和“显式 `None`”混成同一状态，等于把缺键也当缺失时间。改为
   `"time_stamp" in msg and raw_ts is None` 才走 preserve 分支；缺键与空字符串继续落
   `if not raw_ts: raise`，保持 upstream 拒绝语义。同步订正 docstring（只接受
   dict/list[dict]，str 是拒绝而非“不推荐接受”）与 else 分支错误信息。修复位置：
   `lightmem.py::MessageNormalizer.normalize_messages`。
2. **R1-2 adapter 不洗空串**：首轮 `_turn_timestamp` 的 `preserve_none` 只判
   `not raw_timestamp`，会把 `turn_time=""`/`session_time=""` 这类非法空串（无可用非空
   fallback）静默正规化成 None。改为 preserve_none 仅在 `turn.turn_time is None and
   session.session_time is None` 时返回 None；出现空串且无非空 fallback 时无论 policy 都
   抛 `ConfigurationError`。既有优先级（非空 turn 优先、否则非空 session）与 require 行为
   不变。修复位置：`lightmem_adapter.py::_turn_timestamp`。
3. **R1-3 类型说真话**：`MemoryEntry` 在缺失时间时真实存 None，但 annotation 仍是
   `str`/`float`。改为 `time_stamp: Optional[str]`、`float_time_stamp: Optional[float]`、
   `weekday: Optional[str]`，默认值保持原样（不改未显式传参的 runtime 行为），未重排
   import 或改其它字段。修复位置：`utils.py::MemoryEntry`。

新增强反例：normalizer 缺键/空串分别 raise；`_turn_timestamp` preserve_none 双 None→None、
含空串无 fallback→raise、空 turn+合法 session→回落 session；`get_type_hints(MemoryEntry)`
断言三字段 Optional。既有 missing-time lineage 测试保留，证明 runtime 仍存 None 与 source id。

R1 定向测试尾行（`uv run pytest -q tests/test_lightmem_adapter.py
tests/test_amem_lightmem_registry.py tests/test_method_registry.py`）：

```
91 passed, 1 warning in 7.27s
```

首轮 §6 的历史尾行不改写。

## 9. 架构师最终强验收

- R1 full diff 与允许清单通过；架构师独立定向：`91 passed, 1 warning in 6.32s`。
- 首轮/R1 保持两个 commit 线性合入：`e1cfb75` → 主线 `915f73c`，`0d6bf9f` → 主线
  `3968373`，不 squash、不 amend，保留返工审计链。
- 合入后主树全量：`1206 passed, 3 deselected, 2 warnings, 4 subtests passed in 142.81s`。
- `uv run python -m compileall -q src/memory_benchmark tests`：exit 0。
- 裁决：Phase B 接受；MemBench 100k × LightMem 可进入后续免费 dry-run/smoke 门，结果仍须
  标注 framework-extended missing-time compatibility，不得称 upstream native parity。
