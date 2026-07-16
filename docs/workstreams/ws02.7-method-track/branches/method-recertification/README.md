# Method 逐项重认证支线

## 目的

共享协议、lifecycle、时间、provenance、metric eligibility 与 track identity 在首轮
method-frozen 后发生了实质变化。旧证据不删除，但不能靠历史 ✅ 惯性宣布当前版本仍冻结；
本支线按**当前主线 commit**逐 method 重走 B1-B11，做到“慢就是快”：一次只压实一家，
前一家没有完成对表与强验收，后一家不施工。

## 重认证不是盲目从零重跑

每个 B 项必须落入四种状态之一：

1. `revalidated`：相关源码/配置/契约未变，旧一手证据已在当前 commit 重新抽锚；
2. `retested`：改动面或风险面已用当前代码定向/全量/产物重新验证；
3. `N/A`：method × benchmark × metric 不具备诚实资格，写明原因；
4. `pending`：仍依赖预算、上游资产或共享框架门，不用假 ✅ 填格。

只有受改动影响的 build/smoke 才重烧；字节与身份均未变的资产不为“重新开始”重复付费。
每家最后仍执行 checklist B11 对表仪式，更新 integration 实例页、总表与 frozen note。

## 串行顺序与门

1. 共享门 Track identity M0 已于 2026-07-16 通过 R1/R2 强验收关闭；现在把
   RetrievalEvidence M1 作为 LightMem 重认证所需 evaluator 资格门收口。
2. **LightMem 第一家**：重点重验 online-soft 主 profile、missing-time 扩展、逐题 evidence、
   canonical-required MiniLM build identity、五 benchmark B4/B5/B6/B9/B10/B11。
3. **Mem0 第二家**：把 source-time、ADD-only/provenance、truthful identity 与
   product-default OpenAI embedding 迁移放在同一认证链；真实重建仍须用户批预算。
4. **MemoryOS 第三家**：PyPI product identity、speaker/provenance sidecar、降级审计、
   readout-native 与五格 smoke 一次收口；ChromaDB variant 不混入主轨。
5. **A-Mem → SimpleMem**：各自补全 product/reproduction identity 后重走 B1-B11。
6. 现有五家压实后，再接 MemOS、Letta/MemGPT、LangMem、Supermemory；EverOS 最后。

## 当前状态

**LightMem 已成为唯一 active method，但尚未派施工卡。**架构师先在当前主线 commit 上重读
checklist、`integration/lightmem.md` 与 lifecycle/retrieval-evidence 裁决，产出 B1-B11 的
`revalidated / retested / N/A / pending` gap matrix；只有矩阵确认确有 actor 施工项后才写卡并
醒目标注给用户派发。此阶段不并行推进 Mem0/MemoryOS，也不调用真实 API。权威实时动作仍看
父级 `../../README.md` 恢复胶囊与最新断点。
