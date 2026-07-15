# 框架差异化主张（论文 / 资金申请内核，判例累积式）

> 创建 2026-07-13（用户提议：把"我们框架优于同类框架的地方"记录下来，作为
> 写论文/申请资金时的强内核）。**纪律**：对他框架的每个负面陈述必须有一手锚
> （`文件:行号`），没锚就只写我们的正面主张、不做对比断言；判例随取证持续
> 累积，每条注明取证日期与出处 note。

## 一、核心主张（一句话版）

**我们测的是 method 的真实算法，在统一可比与论文可复现两个口径下，指标算不了
就诚实 N/A 或做经评估的无损改造——不为了凑指标扭曲被测系统。**

## 二、判例组 1：vs MemoryData（2026-07-13 取证，
详见 `ws02.7/notes/memorydata-recall-retrofit-survey.md`）

### D1. 算法保真红线：不为指标绕过 method 核心管线
- **他们**：LightMem 格用 `lightmem_ingest_mode: direct`
  （`config/hybrid_lightmem.yaml`）——不调 `add_memory`，adapter 手工构造
  verbatim chunk 直接 `offline_update`（`methods/lightmem/lightmem_adapter.py:144-192`），
  预压缩/主题分段/LLM 抽取整条核心管线被绕过。**得到了 Recall@k，代价是测的
  实为"qdrant RAG + LightMem 存储壳"**，其报告中的"LightMem"成绩与 LightMem
  算法脱钩。
- **我们**：LightMem 始终走真实抽取 + post-build update 管线。最初的 B5+ singular
  source-id 透传在 2026-07-15 被进一步审计出 merge 后血缘不完整，架构师当场撤销
  LoCoMo Recall@10 的可信声明并重开冻结，而不是因为“已经有非零 items”就放行。
  第一版 plural 输入 lineage 修复虽可零算法变化实现，但用户指出它不证明更新后文本
  仍承载各 source fact；架构师因此拒绝合入已通过测试的 `3e2d957`，把该格
  provenance Recall/NDCG 定为 N/A。这里的差异化不是“多算一个指标”，而是敢于承认
  method 能力边界。证据与裁决见
  `ws02.7/notes/lightmem-offline-recall-ruling.md`。

### D2. 评测元数据不进被测系统
- **他们**：把 `[LOCOMO_META chunk_id=… source_ids=…]` 血缘 header 直接拼进
  method 的存储文本（`benchmark/locomo/loader.py:145`、
  `utils/locomo_utils.py:44-49`）——评测侧元数据写入被测系统的记忆内容，且
  **随文本进 embedding 向量**，对检索相似度构成系统性微扰；answer 前虽有
  strip，存储与检索两层已被污染。
- **我们**：provenance 设计走 adapter 侧 id 映射/结构化通道（RetrievalResult
  items/provenance 字段），method 存储内容保持与生产使用一致；私有数据另有
  4 层边界（gold 不进公开对象、公开键黑名单扫描），评测信息对被测系统零注入。

### D3. 效率口径：api_usage 单一事实源，不混算不重复计数
- **他们**：`prompt_tokens + memory_retrieval_length` 直接相加上报
  （`utils/agent.py:2914,2964,3026,3135,3751` 五处）——检索记忆已在 prompt 内、
  `prompt_tokens`（api_usage）已含之，再加 tokenizer 估算的
  `memory_retrieval_length` = **同一段 token 计两遍，且 api_usage 与
  tokenizer_estimate 两种口径混加**。
- **我们**：token 一律 api_usage 优先，接口不暴露才 tokenizer_estimate 且逐处
  留档拦截层（checklist B7）；注入记忆 token 有独立双轨口径政策
  （`efficiency-injected-tokens-policy.md`），载荷与模板开销分离、native 轨有
  "统计载荷 ≡ prompt 实际嵌入段"审计项。

### D4. answer 口径统一 vs per-method 各写各的
- **他们**：每个 method handler 内嵌自己的 answer prompt 模板与生成参数
  （如 mem0/memoryos handler 各自的 memory_answer_prompt 覆盖链，
  `utils/agent.py:3043-3149,2984-3042`），method 间成绩差里混入 prompt 差异。
- **我们**：answer/judge 是框架角色，双轨显式分离——unified 轨全 method 同一
  prompt builder（可比性），native 轨逐字复刻官方复现配置且 parity 锁
  （可复现性；`dual-track-config-policy.md`）。单轨框架两头都不占：既不保证
  可比（模板不一），也不保证复现（非论文配置）。

### D5. 可恢复性与断点工程（正面主张为主）
- **我们**：manifest 字节级比对 + turn 级检查点状态机（in_flight 永不自动
  续跑）+ 原子写 + JSONL torn-tail 恢复，resume 是框架职责非 adapter 职责。
- **他们**做对的一点应记录：provenance sidecar 持久化 + 旧 state 缺 provenance
  时 fail-fast（`utils/agent.py:1004+`）——方向一致，我们的实现更系统化；
  该设计已吸收进我们 mem0 B5+ 改造方案。

### D6. 能力声明式兼容矩阵（正面主张）
- **我们**：三 registry 能力声明 + 运行时 validate_compatibility + conditional
  evaluator（能力缺失 → 显式 N/A 记录进报告），指标缺席是**被声明的事实**而
  非静默的 0 分或悄悄换实现。配套逐实体实例文档（integration/*.md，接口调用
  面 + 逐字段契约 + B1-B11 证据链），被测系统不是黑盒。

## 三、使用纪律

- 写论文/申请材料引用本档时，逐条回源验证锚点仍然成立（对方框架可能更新）。
- 新判例组（其他参考框架/官方 harness 对比）按"判例组 N"追加，同样先取证后
  落档；正面主张与对比断言分开写。
