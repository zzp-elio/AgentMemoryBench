# Actor 卡：LightMem unified-hybrid role profile（五格 role 无损 + 诚实 lineage）

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**你是施工 actor，不是架构师；按本卡裁决实现，遇到停工条件交回。

## 0. 这张卡解决什么

当前 LightMem backend 硬编码 `messages_use="user_only"`，adapter 又把除 LongMemEval 外的
turn 全包装成 user，导致真实 assistant 内容不进 extraction prompt。直接改成 `hybrid` 也
不够：空 slot 会进入 prompt/token 计数，assistant-only pair 的 fact 又会因官方
`source_id * 2` 固定读取 user slot 而产生假 lineage。

本卡把 Phase 1 五 benchmark 的 **unified 主 build** 改为显式 `hybrid`，用通用 role-slot
normalizer 保留真实 role、只补结构占位，并把 pair 候选 child ids 作为纯观测链路传到底层
payload。它不改 LightMem 抽取/分段/embedding/update/retrieval 算法，不改 benchmark adapter，
也不强迫 LME/BEAM 获得不成立的 Recall 资格。

## 1. 隔离环境与必读顺序

- worktree：`/Users/wz/Desktop/mb-actor-lightmem-hybrid-role`
- branch：`actor/lightmem-hybrid-role-profile`
- 基线：用户创建 worktree 时的 main HEAD；先现场记录 `git rev-parse --short HEAD`

只按顺序读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与最新断点
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/README.md`
4. `docs/workstreams/ws02.7-method-track/branches/input-role-semantics/notes/
   lightmem-messages-membench-beam-role-audit.md` 的 §2、§3、§6、§7、§9、§10
5. `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/
   lightmem-b1-b11-gap-matrix.md`
6. `docs/reference/actor-handbook.md`
7. 本卡点名的 adapter、vendored 五个函数和测试；不要重扫全部历史

## 2. 已裁 profile 与边界

### 2.1 配置/身份

- `LightMemConfig` 新增强校验 `messages_use`，只接受严格
  `user_only/assistant_only/hybrid`。dataclass 默认保持 `user_only`，避免直接构造时暗中改变
  reproduction；`configs/methods/lightmem.toml` 的 `smoke` 与 `official_full` **都显式写
  `messages_use="hybrid"`**，这两格才是 Phase 1 unified 主 build。
- backend config 必须从 `config.messages_use` 读取，禁止继续硬编码。
- `LIGHTMEM_ADAPTER_VERSION` 从 `conversation-qa-v3` 升为 `conversation-qa-v4`；config
  manifest 原样含 `messages_use`，因此 user_only/hybrid 与 v3/v4 都不能 resume/collapse。
- LongMemEval Table 2 的 `user_only` 是独立 reproduction profile；本卡不新建付费 TOML、不
  跑复现实验，只保留可显式构造能力。GitHub PR #72 仍是 open docs-only，不冒充 merged
  upstream contract。
- 顺手删除 `LightMemConfig` 中当前重复声明的第二个 `missing_timestamp_policy` 字段；值、
  默认与行为不得改变。

### 2.2 通用 role-slot normalizer

LoCoMo 继续按官方 named-speaker 姿势：每条真实 utterance 放 user slot + 一个 empty
assistant slot；两 slot 都保留同一个真实 speaker/time。其余四家读取 canonical
`normalized_role`，只接受 user/assistant，并按原始顺序生成：

- 相邻真实 `user → assistant`：同一 pair，两个真实 role/content 都保留；
- user 后仍是 user、末尾 dangling user：先输出 `[real user, placeholder assistant]`；
- assistant-first、assistant 后仍是 assistant：输出 `[placeholder user, real assistant]`；
- 单 role session、空 content 的**真实** message 不能被当 placeholder；marker 才是唯一依据；
- 任何真实 turn 恰好出现一次，顺序不变，不丢、不复制、不 role-launder；placeholder 不制造
  public turn id。

必须使用显式内部 marker `memory_benchmark_structural_placeholder=True`。placeholder 的
`content=""`，为通过官方 normalizer 与 user-anchor 取值，可镜像同 pair 真实 child 的
timestamp/speaker；它的 real-child-id set 也镜像该 pair，但 marker 保证它不是独立来源。
LoCoMo 选择只由构造期 `benchmark_name=="locomo"`，其它四家走通用 role；禁止靠 source
path、问题文本或文件名猜 benchmark。缺 benchmark identity 且遇到非 user/assistant role 时
fail-fast，不静默当 user。

### 2.3 placeholder 对算法输入的处理

只在两处 vendored 观测边界跳过 marker=True 的 slot：

1. `ShortMemBufferManager._count_tokens()`：placeholder 不计 content/分隔符，真实 assistant
   在 hybrid 下正常计数；
2. `OpenAIMemoryManager.concatenate_messages()`（现为 nested helper）：placeholder 不渲染
   extraction 行，真实 assistant 在 hybrid 下正常渲染。

不要按 `content==""` 跳过；真实空 message 与结构 placeholder 语义不同。不要修改
`SenMemBufferManager` 的 user-anchored boundary、segmenter、compressor、抽取 system prompt、
`source_id` 编号或 LLM 输出 parser。assistant-only pair 的 boundary 仍不完全对称，作为
upstream limitation 写入 note/integration，不“顺手修算法”。

修复后必须证明：LoCoMo 同一批次下 `hybrid` 与 `user_only` 的 **extraction user prompt 和
short-memory token count 字节/整数严格相同**；这只证明 deterministic input parity，不声称
LLM 随机输出或整套五格等价。

### 2.4 pair candidate lineage（纯观测，不冒充精确来源）

官方 extraction 展示 `sequence_number // 2`，fact 的 `source_id` 是 pair index；后续固定
`source_id * 2` 读 user slot。为避免把 assistant fact 假记成空/user turn：

- normalizer 为每个 pair 计算按真实 turn 顺序稳定去重的 `source_external_ids`；placeholder
  不增加 id。一个真实 utterance→1 id，正常 pair→2 ids；同一集合放到两个 slot，穿过
  `MessageNormalizer`/compression/sequence assignment；
- `MemoryEntry` 新增 `source_external_ids: list[str]`（default_factory），转换时从 pair 观测字段
  写入；只有集合恰好一个 id 时可同时保留 legacy singular `source_external_id`，两个 id 时
  singular 必须为 None/不写，不能把 user id 冒充 exact；
- initial `offline_update(memory_entries)` 的 Qdrant payload 条件写 plural；adapter v4 检索只
  信任合法、非空、稳定去重的 plural 并形成 `RetrievedItem.source_turn_ids` tuple。v3/旧 store
  缺 plural 要 fail-fast/回落无 provenance，不能静默读 singular；version bump 已要求重建；
- **不要合入或复刻旧 `3e2d957` 的 all-entry merge/delete lineage union。**本卡主 profile 是
  online-soft；`locomo_offline_consolidated` 继续恒 N/A，不动 update/delete 算法。

这些 ids 只证明 pair 是 extraction input。`RetrievalEvidence` 逐 benchmark 改为诚实矩阵：

| benchmark/profile | semantic_provenance | granularity | 理由 |
|---|---|---|---|
| LoCoMo + online_soft + items 可用（含空 tuple） | valid | turn | 每 pair 仅一个真实 utterance |
| MemBench + online_soft | pending | none | 等 canonical split + pair-step gold group/M1 |
| LongMemEval + online_soft | n_a | none | pair source_id 不能证明具体 user/assistant turn；session view 留 M1 |
| BEAM + online_soft | n_a | none | 官方 gold 是单 message，pair candidates 过粗 |
| HaluMem + online_soft | n_a | none | memory-point gold 无 turn qrel |
| identity 缺失/未知 | pending | none | 不猜 benchmark |
| locomo_offline_consolidated | n_a | none | mutation 后无 output-to-source semantic map |

stable_ranking 继续 pending。本卡不得把 pair 的每个 child 都宣称 valid，不得改 evaluator。

## 3. 实施顺序

1. 先写 config/TOML/version 与非法值强反例。
2. 写纯 role normalizer 测试，再替换“LME vs else=LoCoMo”的旧分流；先证明消息全序列。
3. 在 token/render 两处加 marker 过滤并锁 LoCoMo 严格 parity。
4. 打通 plural lineage 的 message→MemoryEntry→payload→RetrievedItem，最后收紧 evidence 矩阵。
5. 更新 integration + implementation note；只跑一次定向测试；diff-check、显式 add、commit。

## 4. 允许修改文件

```text
configs/methods/lightmem.toml
src/memory_benchmark/methods/lightmem_adapter.py
third_party/methods/LightMem/src/lightmem/factory/memory_manager/openai.py
third_party/methods/LightMem/src/lightmem/factory/memory_buffer/short_term_memory.py
third_party/methods/LightMem/src/lightmem/memory/utils.py
third_party/methods/LightMem/src/lightmem/memory/lightmem.py
tests/test_lightmem_adapter.py
tests/test_amem_lightmem_registry.py
tests/test_method_registry.py
tests/test_lightmem_registered_prediction.py
docs/reference/integration/lightmem.md
docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/
  lightmem-hybrid-role-profile-implementation.md
```

不要改 benchmark adapter、provider protocol、evaluator、registry 生产代码、sensory memory、
抽取 prompts、offline consolidation、其它 method、父/支线 README、survey、policy、outputs/
data/models。若必需文件不在清单，立即停工列路径和理由，不自行扩 scope。

## 5. 必测强反例

- config：三合法值；空白/大小写/未知/非字符串拒绝；TOML 两 profile=hybrid；manifest 含字段、
  adapter v4；v3/user_only 与 v4/hybrid resume 不兼容。
- role 全序列：正常 pair、assistant-first、user-user、assistant-assistant、dangling user、单
  assistant session、跨 session 边界、真实空 content、未知 role；输出中每个真实 turn 恰一次。
- MemBench ThirdAgent/user-only → 一个 real user + placeholder assistant；FirstAgent canonical
  尚未拆时不得在 LightMem 内解析拼接字符串或伪造 assistant。
- LoCoMo：named speaker/user slot 姿势不变；hybrid vs user_only extraction user prompt 严格
  相等、token count 相等；placeholder 行不存在；真实空 message 不因 content 为空被过滤。
- assistant 可见：hybrid prompt 包含真实 assistant，user_only 不含；token count 也按真实
  assistant 增加；system extraction prompt 原文零变化。
- lineage：单侧 pair plural=[唯一 id] 且 singular 可保留；双真实 pair plural=[user,assistant]
  且 singular 不冒充；assistant-only placeholder user 能把真实 assistant 的 time/speaker/group
  传到 entry；重复 id 稳定去重；缺失/空白/非字符串 plural 不能产出部分 provenance。
- payload/retrieve：真实 vendored `MemoryEntry` 插入写 plural，adapter 读 plural 返回 tuple；
  旧 singular-only store 不再被 v4 当 exact；consolidated 仍 N/A。
- RetrievalEvidence 矩阵逐格锁 status/reason/granularity，特别是 LME/BEAM 不得 valid、
  MemBench 必须 pending、LoCoMo `items=()` 仍 valid 而 `items=None` N/A。
- 既有 timestamp：显式 None、空串拒绝、turn→session fallback、timestamped 路径零退化；
  placeholder 不制造 wall clock/sentinel。

## 6. 唯一定向自检

```bash
uv run pytest -q \
  tests/test_lightmem_adapter.py \
  tests/test_amem_lightmem_registry.py \
  tests/test_method_registry.py \
  tests/test_lightmem_registered_prediction.py
```

本文件明确只用 fake runtime，不调用真实 API。不要跑全量、compileall、下载模型或付费 smoke；
架构师合入后负责全量门。

## 7. 停工条件

- official preprocessing 丢失 marker/plural，且不改清单外/算法核心无法无损保留；
- 某 Phase 1 benchmark 的 canonical role 不是 user/assistant，现行裁决无法表达；
- LoCoMo placeholder 过滤后 hybrid/user_only prompt 或 token 仍不等价且 15 分钟内无法解释；
- plural lineage 必须改变 extraction source_id/prompt/算法才能实现；
- 需要 benchmark adapter/evaluator、真实 API、模型下载、清单外文件；
- 定向测试失败且 15 分钟内无法定位。

停工时把最小复现、源码锚、已完成安全部分和二选一写入 implementation note；不要用 benchmark
名特判、假 external id、复制 assistant 到 user content 或放宽断言硬绕。

## 8. 提交纪律与完成报告

- `git diff --check`；add 前后各看 `git status --short`；只显式 add，禁 `-A`/`.`；本地单
  commit，不 amend、不 push。
- commit 建议：`fix(lightmem): preserve hybrid conversation roles`
- third_party 每处改动在 implementation note 列文件/函数/理由，并明确“只过滤框架 marker/
  增加观测 lineage，不改算法核心”。
- Co-Authored-By 只写可核实真实模型；混合/切换无法核实时不猜。
- 按 actor-handbook §4 回报：hash、测试尾行、实际文件、偏差/停工、subagent 分工与模型切换
  （如有）。到此停止，等待架构师强验收。
