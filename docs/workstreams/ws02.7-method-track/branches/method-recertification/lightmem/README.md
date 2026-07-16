# LightMem 重认证子线

LightMem 是 method-recertification 的第一家。历史 frozen 证据保留，但以当前 main
重新抽锚；本目录只收 LightMem 的 gap matrix、验收 note 和后续卡，不把共享 benchmark
问题平铺到父目录。

## 当前依赖

1. Track identity M0 已关闭；
2. `input-role-semantics` 的 evidence-unit 审计已裁，gold schema M0 正待派；
3. [LightMem role-complete profile 卡](cards/actor-prompt-lightmem-hybrid-role-profile.md)
   与 [gold M0 卡](../../input-role-semantics/cards/actor-prompt-gold-evidence-contract-m0.md)
   文件正交，可以并行施工；
4. gold M0 验收后再拆 MemBench canonical role，之后 RetrievalEvidence M1 消费新契约；
5. 最后才进入 B11 五格付费 smoke（须用户批准预算/规模/run_id）。

LightMem unified 主 profile 固定 `messages_use="hybrid"`；LongMemEval Table 2 的
`user_only` 只作 reproduction profile。hybrid 卡只关闭 role/content 可见性与诚实的
pair-candidate 观测，不提前宣布 LME/BEAM turn Recall 有资格。

当前 gap matrix：
[`notes/lightmem-b1-b11-gap-matrix.md`](notes/lightmem-b1-b11-gap-matrix.md)。
