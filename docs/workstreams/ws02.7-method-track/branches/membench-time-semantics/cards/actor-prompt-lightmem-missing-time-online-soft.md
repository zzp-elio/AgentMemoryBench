# Actor 卡：LightMem online-soft 缺失时间兼容 Phase B

> **历史卡，禁止重复执行。** Opus 4.8 已完成首轮 commit `e1cfb75`；架构师验收发现
> explicit-None 边界与类型契约仍需收紧，后续只执行同目录
> `actor-prompt-lightmem-missing-time-online-soft-r1.md`。本卡保留为原始施工契约。

## 0. 上工与隔离

按顺序只读以下最小集合：

1. `AGENTS.md`；
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊；
3. 本卡全文；
4. `docs/reference/actor-handbook.md` §0-§4、§6-§8；
5. `docs/workstreams/ws02.7-method-track/branches/membench-time-semantics/notes/
   lightmem-missing-time-compatibility-ruling.md` 全文；
6. vendored `lightmem/memory/lightmem.py::MessageNormalizer.normalize_messages`、
   `LightMemory.add_memory`、`offline_update`、`retrieve`；
7. vendored `lightmem/memory/utils.py::assign_sequence_numbers_with_timestamps`、
   `_create_memory_entry_from_fact`；
8. `src/memory_benchmark/methods/lightmem_adapter.py` 的 config/manifest、batch 转换、
   lifecycle gate、`_turn_timestamp`；
9. `tests/test_lightmem_adapter.py` 中 lifecycle、manifest、timestamp、lineage 测试。

从届时 `main` 新建；路径/分支已存在就停工，不删、不复用：

```bash
git -C /Users/wz/Desktop/memoryBenchmark worktree add \
  /Users/wz/Desktop/mb-actor-lightmem-missing-time \
  -b actor/lightmem-missing-time-online-soft main
cd /Users/wz/Desktop/mb-actor-lightmem-missing-time
uv sync
```

允许修改：

- `third_party/methods/LightMem/src/lightmem/memory/lightmem.py`；
- `third_party/methods/LightMem/src/lightmem/memory/utils.py`；
- `src/memory_benchmark/methods/lightmem_adapter.py`；
- `configs/methods/lightmem.toml`；
- `tests/test_lightmem_adapter.py`；
- `tests/test_amem_lightmem_registry.py`、`tests/test_method_registry.py`（仅若 manifest/config
  真实链要求同步；无实际变化就不 add）；
- 新建 `docs/workstreams/ws02.7-method-track/branches/membench-time-semantics/notes/
  lightmem-missing-time-online-soft-implementation.md`。

禁止修改 MemBench adapter、其它 method、registry 生产代码、runner、evaluator、provider
协议、其它第三方文件、README/status/reference 文档、outputs。真实调用链迫使超出清单就停工。

## 1. 已裁契约

新增 `LightMemConfig.missing_timestamp_policy`，只允许：

- `preserve_none`：只允许与 `lifecycle_profile="online_soft"` 组合；
- `require`：缺失 source timestamp 时在 backend 创建、LLM/API、向量写入前 fail-fast。

`configs/methods/lightmem.toml` 的 smoke 与 official_full 都必须显式写
`missing_timestamp_policy = "preserve_none"`。字段进入 `to_manifest()`；
`LIGHTMEM_ADAPTER_VERSION` 从 v2 升 v3，锁住 resume identity。

`locomo_offline_consolidated` 必须显式组合 `require`。构造期拒绝
`locomo_offline_consolidated + preserve_none`；即使 policy=require，实际缺失也必须在任何
backend 创建/写入前拒绝。

不得根据 `benchmark_name == "membench"` 开特判。policy 是 method/profile 能力，实际值由
输入决定；timestamped 的 LoCoMo/LongMemEval/HaluMem/BEAM/MemBench 路径都继续走原逻辑。

## 2. vendored None 语义

### 2.1 MessageNormalizer

`preserve_none` 输入由 adapter 传入含 `time_stamp=None` 的 dict。normalizer 对这一项：

- 深复制并保留 role/content/speaker/external_id；
- 写 `session_time=None`、`time_stamp=None`、weekday 空值；
- 不更新 `last_timestamp_map`，不生成 offset/sentinel/wall clock；
- 非空 timestamp 的既有解析与 offset 行为不得改变。

vendored normalizer 只负责“None 能被无损表示”，不需要知道 framework policy；
`require/preserve_none` 的门统一由 adapter 在调用 backend 前执行。不要把 policy 参数扩散进
upstream backend config，不使用全局变量，也不写 benchmark 特判。

### 2.2 sequence / MemoryEntry / lineage

`assign_sequence_numbers_with_timestamps()` 必须跳过 None session group 的 datetime parsing，
但仍按原 extract_list 顺序分配 sequence_number。timestamps/weekday/speaker/external_ids 五条
并行数组长度与索引必须继续对齐。

`_create_memory_entry_from_fact()` 遇到 timestamp None 时只令
`time_stamp=None`、`float_time_stamp=None`；不得连带清空 speaker、topic 或
`source_external_id`。不要用宽 catch 把独立字段绑在 timestamp 成败上。

direct insert payload 保留 null。online-soft `retrieve()` 输出不得出现字面量
`"None None"`；缺时间时只返回 memory 文本/已有 speaker 信息。非空时间的返回格式不变。

### 2.3 lifecycle 红线

缺失时间只准进入 online-soft direct insert + vector similarity retrieve。禁止改造
construct-update-queue、offline-update-all、summary/window、historical filter 或排序函数来
“兼容” None；这些路径必须由 require gate 挡住。

## 3. adapter 双路径

legacy `add()` 与 v3 `ingest()` 都必须遵守同一 policy：

- preserve_none：`Turn.turn_time or Session.session_time` 缓解后仍为空，就把 None 原样传给
  patched backend；content（含 place/time 或无时间 noise）完整保留；
- require：在 backend 创建或任何实际调用前抛 `ConfigurationError`，错误带 turn id；
- bridge/native 对同一输入产生等价 message batch。

注意 legacy `add()` 当前先创建 backend 再转换 batch；若要满足 require 的“创建前失败”，先
完成纯 batch/preflight，再创建 backend。不得因此改变成功路径的 add_memory 调用序列。

## 4. 必测强反例

至少覆盖：

1. real `MessageNormalizer` 混合一个 timestamped message 与一个 None message：前者输出完全
   保持既有 ISO/weekday，后者三个时间字段为空且 content/external_id 不变；
2. sequence helper 混合时/无时消息：顺序和五条并行数组对齐，不解析 None；
3. missing-time fact 转 `MemoryEntry` 后 timestamp/float 为 None，但 speaker、topic、
   `source_external_id` 完整；
4. 本地 Qdrant 或项目 fake retriever direct insert 接受 null payload，向量 retrieve 仍按
   score 返回；格式化结果不含字面量 `None None`；
5. online_soft 的 MemBench-like bridge 与 native 输入：无时间 noise 不过滤，完整 content
   + `time_stamp=None` 到 backend，零 synthetic time；
6. `missing_timestamp_policy=require` 的 legacy/native 缺失输入都在 backend factory 计数仍为
   0 时 fail-fast；
7. `locomo_offline_consolidated + preserve_none` 构造期拒绝；require + 完整 timestamp 继续
   保留原 force/update 次序；
8. LoCoMo、LongMemEval、HaluMem 与现有 timestamped MemBench 测试不退化；
9. TOML 两 profile 显式 preserve_none；manifest 含 policy + adapter v3，旧 manifest resume
   由既有全 manifest 比较拒绝。

测试不得调用真实 LLM、下载模型或扫描完整 100k 数据。fixture 要让 content 中可能有 place，
但无时间 noise 的 timestamp 确为 None。

## 5. 第三方改动记录

implementation note 必须列出 vendored 文件/函数、为何属于缺失输入兼容而非核心流程变更、
timestamped 路径不变证据、online/consolidated 边界、lineage 强反例、定向测试真实尾行和偏差。
明确标注：MemBench 100k 结果属于 framework-extended missing-time compatibility，不是 upstream
对 None 的 native parity。

所有新增/修改 Python 模块、类、函数、嵌套 helper 与测试函数带中文 docstring。

## 6. 停工条件

- Qdrant 实际不接受 null payload，或 online-soft vector retrieve 必须按时间过滤/排序；
- None 支持迫使修改 consolidated/summary 的时间算法；
- 不能在保留 speaker/external_id 的同时让 missing timestamp 通过；
- 必须引入 synthetic time、跳过 noise、benchmark-name 特判或允许清单外生产文件；
- 定向测试失败且 20 分钟内无法定位。

命中后写 note、提交可审证据并停止，不自行扩 scope。

## 7. 唯一自检、commit 与回报

只跑一次：

```bash
uv run pytest -q \
  tests/test_lightmem_adapter.py \
  tests/test_amem_lightmem_registry.py \
  tests/test_method_registry.py
```

通过后执行 `git diff --check`、`git status --short`，只显式 add 实际修改路径，禁止
`git add -A`/`.`。commit message：

```text
fix(lightmem): preserve missing timestamps online
```

不 push。按 actor-handbook §4 回报：

1. `git rev-parse --short HEAD` 的真实 commit hash（不能写路径或只写 subject）；
2. 定向测试尾行原文；
3. 实际改动文件；
4. 偏差/停工点；
5. 若使用 subagent，简述分工。
