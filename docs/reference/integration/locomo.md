# LoCoMo 接入实例（A1-A8 逐项）

> 判据模板：`../method-integration-checklist.md` §A；勾选总表：`../integration-status.md`。
> **frozen-v1（2026-07-10）**；证据主库 =
> `docs/workstreams/ws02.6-first-smoke-hardening/notes/locomo-frozen-v1.md`（下称"冻结记录"）。
> 本文 = A1-A8 逐项索引 + 对 method 接入的含义，不复制冻结记录全文。

## A1-A8 逐项

- **A1 来源锁 ✅**：repo `snap-research/locomo` @ `3eb6f2c`；CC BY-NC 4.0；
  `data/locomo/locomo10.json` SHA-256 `79fa87e9…`；逐文件
  `ws02.6/notes/locomo-source-lock.json`。已知瑕疵：bundled PDF 与 README 链接路径
  字节关系未确认（冻结记录 §2）。
- **A2 数据契约 ✅**：10 conv / 272 session / 5,882 turn / 1,986 QA；cat5 排除后
  1,540 题；140 个 odd-turn session 保留；conv-26 16 个 date-only key 不造 phantom
  session；4 个 empty-evidence QA 保留（冻结记录 §3）。
- **A3 公私边界 ✅**：answer/evidence/event summary/judge label evaluator-only；
  泄漏扫描 CLEAN。
- **A4 canonical/GC-1 ✅**：`dia_id` → 公开 turn id/provenance key；speaker 保留人名。
- **A5 prompt/metric parity ✅**：官方 short-phrase QA 模板 + cat2 日期提示；
  `locomo-f1` 官方 scorer parity；**`locomo-judge` 是 lightmem 衍生
  （`framework_auxiliary_lightmem_reference_v1`，7 处文本偏差），非官方主指标**；
  native 轨另有逐字版（M0-1 注册，见 LightMem 实例）。BLEU-1 不接。
- **A6 smoke/resume ✅**：默认 smoke = 1 conv × 1 round(2 turns) × 1 题
  （`LOCOMO_SMOKE_POLICY.default_history_limit=1`）；formal conversation 级
  checkpoint；answer 失败复用 saved retrieval。
- **A7 artifact/efficiency ✅**：manifest/prompts/predictions/private labels 全套；
  provenance granularity 进 method manifest。
- **A8 冻结门 ✅**：全量 890 passed 时点通过（冻结记录 §7）。

## 对 method 接入的含义（接每个 method 前读这节）

1. **speaker=人名不是 user/assistant** → 以 role=="user" 锚定的 pair 聚合会失效；
   MemoryOS 已为此走 session batch + adapter 内配对（memoryos 实例 §0），新 method
   同坑先查。
2. **turn 无独立时间，继承 session time** → adapter 时间戳注入按 session 粒度取。
3. recall（`locomo-recall`）是 conditional：provenance=none 的 method（当前全部）
  一律 N/A，不是 bug。
4. cat5 仍排除（Phase 1）；category 分布不均（cat4 占 841/1986），breakdown 必看。
5. answer 口径全 method 固定 gpt-4o-mini/temp0/max_tokens=32/top_p=1（unified 轨）。
6. **native 格**（双轨）：Mem0 / MemoryOS / A-Mem / LightMem / SimpleMem / MemOS /
   EverOS 都在 locomo 有 native 配置——locomo 是双轨最密集的 benchmark，逐格过
   policy §5 检查。
