# LightMem 重认证子线

LightMem 是 method-recertification 的第一家。历史 frozen 证据保留，但以当前 main
重新抽锚；本目录只收 LightMem 的 gap matrix、验收 note 和后续卡，不把共享 benchmark
问题平铺到父目录。

## 当前依赖

1. Track identity M0 已关闭；
2. `input-role-semantics` 的 gold schema M0 已经 R1 强验收并合入；
3. [LightMem role-complete profile 卡](cards/actor-prompt-lightmem-hybrid-role-profile.md)
   首轮与 Codex R1 已合入：五格 unified 主 build 固定 hybrid，canonical role 严格读取，
   pair candidate lineage 全有或全无；LoCoMo prompt 只认构造期 identity，HaluMem 保持
   session-level 单次 `add_memory()` 调用边界；
4. MemBench canonical role 已以 `ce1a9a8` + `d852fff` + `68b674b` 强验收关闭；
5. RetrievalEvidence M1 已以 `5d8fce3` + `e10110f` 强验收关闭；
6. LongMemEval 新发现把 B4 局部重开：官方 author harness 会裁掉异常 role turn，framework
   hybrid 会用 placeholder 保留；placeholder 虽不进 extraction 文本，仍参与 upstream
   timestamp/sequence 分配；
7. [LongMemEval 输入异常与 timestamp 审计卡](cards/actor-prompt-lightmem-longmemeval-input-time-audit.md)
   已准备，**待用户派发**。审计关闭后继续按最新 main 重验 gap matrix；最后才进入 B11 五格
   付费 smoke（须用户批准预算/规模/run_id）。

LightMem unified 主 profile 固定 `messages_use="hybrid"`；LongMemEval Table 2 的
`user_only` 只作 reproduction profile。hybrid 卡只关闭 role/content 可见性与诚实的
pair-candidate 观测，不提前宣布 LME/BEAM turn Recall 有资格。

首轮绿测不等于一次通过：架构师抓到 mixed-invalid lineage 被截成部分真相、字符串 marker
被 truthiness 过滤、metadata/speaker role fallback、source-path prompt 猜测和 HaluMem
session→pair 调用边界漂移；R1 均已用会在首轮失败的强反例关闭。最终验收数字与主线 hash
只看父 workstream README。

当前 gap matrix：
[`notes/lightmem-b1-b11-gap-matrix.md`](notes/lightmem-b1-b11-gap-matrix.md)。
