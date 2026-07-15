# LightMem 缺失 source timestamp 兼容性裁决

> 日期：2026-07-15。裁决者：GPT-5 架构师。
> 性质：vendored LightMem 全调用链审读 + 本地 Qdrant null payload 探针；零真实 API。

## 1. 判词

**允许为 `online_soft` 增加“缺失时间原样保持 None”的输入兼容扩展；不允许用同一扩展
运行任何依赖时间排序/窗口的 consolidated profile。**

这不是删除一行校验那么简单，但按下述边界实现时，不改变已有非空 timestamp 输入的算法
行为，也不改变 online-soft 的抽取、embedding、direct insert 与向量相关性检索核心。它属于
benchmark input compatibility extension，结果必须披露为 framework-extended compatibility，
不能声称缺失时间输入具备 upstream native parity。

## 2. 为什么不能只让 normalizer 接受 None

1. `memory/lightmem.py:82-100` 当前要求每条 message 有非空 `time_stamp`，随后解析出
   `session_time`、ISO `time_stamp` 与 `weekday`。
2. `memory/utils.py:68-112` 的 `assign_sequence_numbers_with_timestamps()` 再按
   `session_time` 分组、正则清洗和 `datetime` 解析；直接放入 None 会在这里再次失败。
3. `memory/utils.py:325-347` 把 timestamp 转 float。现有异常兜底会同时把 speaker 与
   `source_external_id` 清空；若只让前两层“别报错”，会静默破坏 lineage。
4. `construct_update_queue_all_entries()`、summary/window helpers 与 supplementary retrieval
   大量按 `float_time_stamp` 过滤、排序和构造时间窗。None 不能进入这些路径。

所以最小正确改动至少要同时处理 normalizer、sequence assignment、MemoryEntry 构造和
adapter lifecycle gate；“把 if not raw_ts 删掉”会得到迟发异常或更危险的静默 provenance
丢失。

## 3. 为什么 online-soft 可以保留 None

- memory-manager prompt builder 只在 `time_stamp` 与 `weekday` 都非空时添加时间前缀；缺失
  时自然使用原 content，不需要造时间。
- topic/short-memory buffer 的主控制流不按 timestamp 排序。
- Phase 1 `online_soft` 映射到 `offline_update(memory_entries)` 的 direct insert；该路径把
  memory embedding 与 payload 写入向量库，不调用全库时间队列/窗口。
- `retrieve()` 的主检索是 query embedding + vector search，相关性顺序不依赖
  `float_time_stamp`；时间只用于返回文本展示。
- 本地 `QdrantClient(':memory:')` 探针已验证 payload 的 `time_stamp=None`、
  `float_time_stamp=None`、`weekday=None` 可以原样写入和读回。

因此，对缺失 source time 的 message，保留 None 并省略 prompt 时间前缀，比跳过 message、
使用 question/兄弟 turn/墙钟时间更接近 LightMem online-soft 的算法本体。

## 4. 必须锁死的实现边界

1. 新增显式 manifest/config 字段 `missing_timestamp_policy`，仅允许：
   - `preserve_none`：只与 `lifecycle_profile="online_soft"` 组合；
   - `require`：缺失时在 backend 创建、API 或 mutation 前 fail-fast。
2. Phase 1 主 TOML 显式声明 `preserve_none`；不能靠 dataclass 默认暗中启用。
3. `locomo_offline_consolidated` 必须绑定 `require`，且任何实际缺失仍在写入前失败。
4. None message 在 normalized message、MemoryEntry、vector payload 中保持
   `time_stamp=None`、`float_time_stamp=None`；weekday 使用空值，不生成 sentinel。
5. 保留原消息顺序、speaker、role、content、external id 与 lineage；缺 timestamp 不能触发
   现有“大 catch 一并清空其它字段”的路径。
6. timestamped 输入的解析、500ms offset、prompt 前缀、payload 和 retrieval 文本保持现状。
7. online-soft retrieval 输出不得出现字面量 `None None`；缺失时间只是不显示时间标签。
8. adapter version 升级，policy 进入 manifest/resume identity。
9. 不跳过官方 noise，不删除 content 中的 place/time，不实现 benchmark-name 特判或
   method × variant 白名单。

## 5. 对算法核心红线的判断

以下做法会触碰核心，禁止：

- 为 None message 生成人造 epoch、step-based datetime、兄弟 turn time 或 ingestion wall clock；
- 让 None 进入 consolidated/summary 的时间排序、过滤或窗口，再另造排序规则；
- 为跑通而跳过无时间 noise；
- 改变已有 timestamped 输入的 offset、事件重建或向量检索顺序。

按 §4 做新增 None 分支，则已有官方支持域完全不变；新输入域只关闭不存在的时间前缀和
时间 payload，不介入向量相关性。这一窄扩展不判为算法核心修改，但必须作为 vendored
benchmark extension 留痕。

## 6. 顺序

MemBench Phase A 强验收并恢复 benchmark 语义后，执行配套 Phase B 卡。Phase B 通过前，
`LightMem × MemBench 100k` 仍暂停；通过后可进入免费 dry-run/smoke 门，但报告必须携带
`missing_timestamp_policy=preserve_none` 与 framework-extended 声明。RetrievalEvidence M0
继续等待本卡稳定，避免同时修改 LightMem manifest/provenance 面。
