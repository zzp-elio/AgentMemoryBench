# Mem0 接入实例（B1-B11 逐项）

> 判据模板：`../method-integration-checklist.md` §B；勾选总表：`../integration-status.md`。
> 状态：**method-frozen-v1 局部重开（2026-07-16：product-default build 与 B10 build 轴）**。
> source-time B4 离线修复已验收；冻结证据与九项声明缺口见
> `../../workstreams/ws02.7-method-track/notes/mem0-frozen-v1.md`；下列 B1-B11 是现行
> 结论，不再把 2026-07-13 的预填风险冒充当前状态。2026-07-15 ADD-only/provenance
> 负空间审计已由架构师验收：memory mutation 仅 ADD；同时确认 sidecar 是 ingest 批
> 归属，不自动等于 fact-level turn provenance。现行逐格裁决见
> `../../workstreams/ws02.7-method-track/branches/retrieval-metrics/notes/
> retrieval-metric-eligibility-ruling.md`。

- adapter：`src/memory_benchmark/methods/mem0_adapter.py`
- 算法源：vendored `third_party/methods/mem0-main`（官方 `Memory` 类）
- native 格：**locomo、longmemeval、beam**（来源=`memory-benchmarks` 当前 eval
  harness；旧论文 LoCoMo 的双 user_id/正反 role/双路检索是独立 implementation
  variant，不是可由 `author_locomo` TOML 单独表达的“配置校准”，不替代当前产品路径）

## 0. 接口调用面

| 框架钩子 | adapter 行为 | 落到 Mem0 官方接口 |
|---|---|---|
| `ingest(TurnEvent)` | `consume_granularity="turn"`；`_ingest_native_turn` 经 `_resolve_speaker_roles` 解析 speaker→role：LoCoMo（`benchmark_name=="locomo"`）用公开 `speaker_a`/`speaker_b` conversation metadata 显式映射，不按首现推断，缺字段/空白/相同/未声明第三方均 fail-fast；其余 benchmark 保持跨调用累积的首现映射（既有兼容边界） | `_add_with_provenance` → `Memory.add([message], run_id=isolation_key, metadata=…, infer=…, prompt=…)` |
| `ingest(SessionBatch)` | `_ingest_native_session`：常规 session 按位置两两切块；HaluMem `session_memory_report` 路径整 session 单次 add | 同上逐 chunk/session 调 `Memory.add()` |
| `end_session` | HaluMem 用：返回本 session `add().results` 产出的 `SessionMemoryReport` | 无额外官方调用（复用 add 返回值） |
| `end_conversation` | —（无钩子；Mem0 add 即建，无缓冲） | — |
| `retrieve(query)` | `retrieve` 处理公开 Question；`_retrieve_native` 处理 v3 `RetrievalQuery` | `Memory.search(..., filters={"run_id": isolation_key}, top_k=…)` |

HaluMem update 的 `top_k=10` 只对 Mem0 原生接口有直接含义：`_retrieve_native()` 现在只在
`purpose="memory_update_probe"` 时把 `RetrievalQuery.top_k` 忠实传给 `Memory.search()`
（五格输入/readout 保真 R1 已实现）；普通 QA/其他 benchmark 仍用 TOML product profile 的
`self.config.top_k`。`RetrievalResult.metadata` 同步区分 `top_k`（本次实际值）/
`configured_top_k`（profile 默认值）/`top_k_source`（`"query_top_k"` 或 `"config_top_k"`）。
该行为不能外推为 HaluMem shared scorer 对所有 method 强制 10 条。

## R1 五格输入/readout 保真修复（本卡）

联合裁决 `branches/method-recertification/mem0/notes/mem0-joint-ruling.md` 定位的五个
输入/readout 保真缺口已由本卡关闭，完整证据见
`branches/method-recertification/mem0/notes/mem0-input-readout-r1-implementation.md`：

1. **LoCoMo 显式 speaker 映射**：不再按 speaker 首次出现顺序猜 user/assistant（该算法在
   source-locked `locomo10.json` 10 个 conversation 中会把 6 个的角色整体反转），改用
   `Conversation.metadata["speaker_a"/"speaker_b"]` 固定映射，legacy `add()` 与 v3 event
   ingest 共用同一对 helper（`_build_locomo_speaker_roles` / `_require_declared_locomo_speakers`）。
2. **共享 caption wrapper**：`_turn_to_message()` 改用 `methods/image_text.py::turn_text_with_images()`
   渲染正文+caption，caption 统一 `[Sharing image that shows: …]`，不再裸拼、不泄漏
   query/URL/path。
3. **role-native content 去重复前缀**：turn 携带当前 adapter 支持的有效 `normalized_role`
   （LongMemEval/MemBench/BEAM/HaluMem）时，content 不再额外前置 `turn.speaker:`——避免
   Mem0 `parse_messages()` 在已结构化的 role 之上再看到一遍重复文本；无有效 role 的具名
   speaker（LoCoMo）content 仍前置真实 speaker 名。
4. **native sanity readout 身份收紧**：`_reader_prompt_kind()` 现在只要 `benchmark_name`
   显式存在但不在 `{locomo, longmemeval, beam}`（即 MemBench、HaluMem）就直接返回
   `generic`，不再被 `question_time`/`category` 巧合带偏成 longmemeval/locomo；只有
   `benchmark_name is None` 的旧版兼容调用保留原启发式。
5. **HaluMem update top-k 透传**：见上段。

`MEM0_ADAPTER_VERSION` 从 `conversation-qa-v2` 升为 `conversation-qa-v3`（五格输入 build
bytes 已改变，旧 v2 memory state 不可 resume）。以上修复只改变进入 extraction/embedding 的
message role/content 与检索请求 top-k，不改 Mem0 V3 extraction/update/dedup/vector search
算法本身，不改 benchmark canonical 数据、granularity 或 metric。

## B1-B11 当前结论

- **B1 ✅ 来源/接口**：使用 vendored OSS `Memory.add/search`；上游压缩包无可追 commit，
  以 package 2.0.4 + 146 文件 content hash 锁定，并把 5×10 后 upstream drift 对比列为
  声明缺口。
- **B2 ✅ 注入粒度**：LoCoMo/MemBench=turn，BEAM=pair，LongMemEval/HaluMem=
  framework session；LongMemEval 在 adapter 内按位置两 turn chunk，HaluMem 整 session。
  HaluMem 的 memory-point 复用 `end_session` 返回的 `add().results`。
- **B3 ✅ 混合隔离**：worker 间独立 backend 物理隔离，worker 内按官方 `run_id`
  namespacing 逻辑隔离；四格 par2 smoke 已实证。
- **B4 ✅ 输入可见性+formatted_memory 时间（effective time 单次渲染已验收）**：OSS `Memory.add()` 没有独立 timestamp
  参数，且 phased extraction 从 parsed messages 而非 storage metadata 读取新对话；因此
  adapter 的 `_turn_to_message()` 把公开 session/turn 时间渲染成 `[Session time: …]` /
  `[Turn time: …]`，同时仍把时间写 metadata 供持久化与检索。2026-07-16 现场复核确认
  MemBench 原 content 已带 place/time 时仍会再前置相同 `[Turn time]`；且普通 turn/session
  同时有值时会同时前置两行，未遵守 `turn_time → session_time → None` fallback。前者不是
  additive typed channel，而是同一 content 双拼；后者给 content-only method 额外输入两份
  时间。裁决为原文不删、typed time 仍保留，但每条 Mem0 message 只渲染一个 effective
  timestamp：turn 优先、session 仅 fallback、原文已嵌 effective turn time 则不再加 header；
  无时间 noise 不补时间。该实现由 MiniMax M3 actor `6af75a3` 交付，架构师 full diff、
  定向 `61 passed` 与五 benchmark 扩展 `170 passed` 后以主线 `7752dab` 合入；commit 中错误的
  Sonnet trailer 未被保留。retrieve 侧再把
  payload 对话时间提升到 `created_at` 槽供官方 reader 使用。server 丢弃独立 timestamp
  字段仍是 upstream 缺口，但不等于当前 extraction 看不见 adapter 已内联的公开时间。
- **B5 ✅/N/A 逐格 provenance**：原生 memory id→持久 sidecar source ids；命中缺映射
  fail-fast，旧 state 不静默回落。LoCoMo/MemBench=valid(turn)；LongMemEval 只能安全
  声明 valid(session)，不得冒充 turn；BEAM pair 的批 id 并集不能证明每条 fact 同时承载
  两个 turn，turn Recall=N/A；HaluMem 官方无 retrieval recall。
- **B6 ✅ no-op flush**：`add()` 同步抽取并写入，无 conversation 尾部缓冲。
- **B7 ✅ api_usage（带声明缺口）**：build/answer/judge 观测已贯通；三格 native
  injected-token 计量尚未完全跟随官方实际嵌入段，列入 R0 前置包。
- **B8 ✅ 副作用/韧性**：失败清理为 `delete_all(run_id)` + 批准的 third_party
  `SQLiteManager.delete_messages(session_scope)` 最小 diff + sidecar 清除；两类业务 API
  点有 timeout/retry。operation-level runner 现与标准 runner 共用 clean-failed-ingest
  状态机：失败原子写 `failed_ingest` 及精确 stage，默认 resume 跳过，显式 retry 无 hook
  fail-closed、有 hook 则先清 namespace 恰一次再从 session 1 重建；partial operation
  artifacts 不落盘。首次模型下载仍需新机器预热预检。
- **B9 🟡 当前 smoke 配置已声明；性能主配置待裁**：2026-07-09 shared MiniLM 配置/产物与
  2026-07-16 product-default 审计都保留为真实历史。现行政策把 embedding 作为 TOML 普通
  build 字段：5×10 smoke 保持当前 MiniLM，不提前烧 OpenAI embedding；真实效果实验前再裁
  `official_full` 是否采用 `text-embedding-3-small`/1536/Qdrant cosine。若切换，托管权重
  revision 只能声明 `provider_managed_unpinned`，并须全量重建、重开 B8+/B11、由用户确认
  预算/规模/run_id。官方 0.1 相关性门槛导致空检索仍属于方法语义，不当作框架故障。
- **B10 🟡 truthful v1 已落，TOML/builder 迁移待性能阶段**：旧 native 注册 LoCoMo、LongMemEval、
  BEAM；当前真实覆盖仅 readout，embedding/build override 未生效。新 manifest 已声明
  `native_scope=readout_only`、current controlled MiniLM 与 answer/judge
  `framework_model_override`，不再由裸 `config_track=native` 暗示 full-native。首个作者校准
  run 前须把有证据的 LoCoMo/LongMemEval/BEAM 设置改由 `author_<benchmark>` TOML section
  选择完整 answer builder；旧 judge 路由泛化和论文校准仍属于前置包。
- **B11 🟡 离线代码门关闭；新五格主 smoke 待复证**：13 格历史 predict、免费/付费指标与既定
  并行门保留，但旧 build 不能替代 adapter v3。既有 BEAM provenance recall 与 LongMemEval
  turn-level/rank 数字不再作可信指标声明；RetrievalEvidence M1 已严格消费逐题资格。
  input/readout v3 与 operation clean retry 经扩大定向 244 passed、主树全量 1637 passed +
  29 subtests、compileall exit 0 强验收。下一步五格真实 smoke 必须抽查新 message bytes、
  retrieval evidence、HaluMem extraction/update/QA 与失败恢复身份；完成 artifact 开箱前不恢复 frozen。

## 特殊情况
1. Mem0 是当前唯一混合隔离方法，不能把 worker 内逻辑隔离误写成全局纯逻辑隔离。
2. `method-frozen-v1` 允许携带声明缺口，不等于这些缺口消失；解冻边界和 R0 前置包以
   frozen note §3-§4 为准。
3. `ADD_ONLY_MUTATION_PROVEN` 只回答旧 memory 是否被改写/删除；它不替代 semantic
   provenance 审计。任务卡旧标签 `ADD_ONLY_PROVEN` 的过宽语义以现行 ruling 为准。
4. 论文 LoCoMo 双库不是“更保险的单库”：它把每个 turn 写两次，绑定只抽 user 的 v2 custom
   instruction，再分别检索并融合两份记忆；迁入当前 V3 会同时改变存储量、抽取调用、namespace、
   检索融合、成本和 provenance。若未来复现，必须以独立 implementation identity 建模。
