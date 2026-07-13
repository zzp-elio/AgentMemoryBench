# HaluMem 接入实例（A1-A8 逐项）

> 判据模板：`../method-integration-checklist.md` §A；勾选总表：`../integration-status.md`。
> **frozen-v1（2026-07-11）**；证据主库 =
> `docs/workstreams/ws02.6-first-smoke-hardening/notes/halumem-frozen-v1.md`。
> **唯一 operation-level benchmark**（提取/更新/QA 三操作交错评测）。

## A1-A8 逐项

- **A1 来源锁 ✅**：repo `MemTensor/HaluMem`（arXiv 2511.03506，CC-BY-NC-ND-4.0）；
  Medium/Long 双 jsonl SHA-256 已锁；官方 commit 待溯。
- **A2 数据契约 ✅**：Medium 20 user/1,387 session/60,146 turn/3,467 题；Long
  2,417 session/107,032 turn（多出的 1,030 个 generated session 只 ingest 不评测，
  官方同款 evaluation.py:51-52）；491 session 无 questions 键（缺键≠空列表）；
  `is_update` 是**字符串** "True"/"False"（truthy 判断必错——探针 bug 判例）。
- **A3 公私边界 ✅**：memory_points/questions gold 全私有；e2e 三层扫描 CLEAN。
- **A4 canonical/GC-1 ✅**：evidence = `{memory_content, memory_type}` **无 turn id**
  （官方用途=QA judge 的 Key Memory Points，不是 retrieval gold）。
- **A5 prompt/metric parity ✅**：answer = PROMPT_MEMZERO **逐字**（2,104 字符；
  PROMPT_MEMOBASE 是官方死代码）；四套官方 judge prompt 逐字 + AST parity；论文
  12 项主指标全实现；**官方路由语义**：update 检索空→归 integrity（H5 揪出的
  parity bug 已修）；`halumem-memory-type` 合成指标复刻官方共享分母。
- **A6 smoke/resume ✅**：**固定形状零旋钮**（用户拍板）：首 conv 4 session × 2 turn
  × QA 1 题；验收口径=三操作运行时调用各 ≥1（update 桶空合法）；一切通用裁剪
  fail-fast；formal conversation 级 checkpoint。
- **A7 artifact/efficiency ✅**：memory-type 合成指标读两份上游 scores artifact，
  缺失 fail-fast。
- **A8 冻结门 ✅**：全量 1058 passed 时点通过。

## 对 method 接入的含义（method 侧最特殊的 benchmark）

1. **retrieval recall = N/A 永久声明**（evidence 无 turn id，禁文本相似度造 gold
   映射——H4 裁决）；对所有 method 无 recall。
2. **需要 memory_point 报告能力**（B2 特例）：提取/更新探针要求 method 在 session
   边界报告"本 session 产出了哪些记忆"。当前唯一现成通路 = Mem0 的 `end_session`
   →`SessionMemoryReport`（mem0 实例 §0）；LightMem/其他家待核 add 返回值。
   **没有该能力的 method 在 HaluMem 的提取/更新阶段怎么处理，是每个 M 阶段必答题**。
   **官方 harness 喂法全景已取证（M0-5，2026-07-13）**：六 wrapper 全 session 级
   批量注入；收集口径三型 = add 返回（Mem0/MemOS）、事后按 id/上下文读取
   （Supermemory/Zep）、**force flush + 时间窗 DB 增量**（Memobase）；收集不完整
   的官方先例 = Zep 照跑但声明指标不准。全表
   `ws02.7/notes/m0-5-halumem-harness-feeding.md`——"无原生能力 method"的适配
   姿势从此有官方对齐锚，LightMem 方案裁决见 lightmem.md B2（已判公平）。
3. **native 格：全员无**（HaluMem 全 method 单轨 collapse，官方五脚本的 prompt 分叉
   已被统一 MEMZERO 严格语义取代；与官方 MemOS/Supermemory 数字对比须声明宽松
   prompt 偏差，冻结记录 §7.2）。
4. update 探针双条件耦合（is_update="True" ⟺ 非空 original_memories，全库无反例）。
5. 时间三层齐全（turn/session start/end）→ B4 时间戳注入在此 benchmark 有完整素材。
