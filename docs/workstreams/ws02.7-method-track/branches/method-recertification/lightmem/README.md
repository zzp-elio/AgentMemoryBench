# LightMem 重认证子线

LightMem 是 method-recertification 的第一家。历史 frozen 证据保留，但以当前 main
重新抽锚；本目录只收 LightMem 的 gap matrix、验收 note 和后续卡，不把共享 benchmark
问题平铺到父目录。

## 当前依赖

1. Track identity M0 已关闭；
2. `input-role-semantics` 支线先裁 MemBench step/turn evidence-unit 契约；
3. 再施工 MemBench canonical role 与 LightMem role-complete profile；
4. RetrievalEvidence M1 消费新契约；
5. 最后才进入 B11 五格付费 smoke（须用户批准预算/规模/run_id）。

当前 gap matrix：
[`notes/lightmem-b1-b11-gap-matrix.md`](notes/lightmem-b1-b11-gap-matrix.md)。
