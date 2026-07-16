# 双轨实现身份与 build-axis 支线

## 目的

把 `unified/native` 从一个含糊布尔值拆成可审计的 implementation/build/retrieval/
answer/judge/metric 六轴；核清通用产品代码、benchmark eval harness 与 paper 配置到底是
同一算法的配置差，还是不同 reproduction variant。

## 当前裁决

1. Phase 1 unified 的算法底座必须是通用 OSS 产品接口；benchmark eval 目录只作 prompt/
   配置/调用序列证据。
2. eval 与产品 core 算法等价、差异可配置时，才允许进入同一 method 的 native track；若
   update/retrieval/storage 流程分叉，另列 `reproduction_variant`。
3. native 逐格记录六轴 coverage；官方无 judge 时可用 framework fallback，但不得称
   full-native。MemoryOS 当前只完成 readout-native answer。
4. MemoryOS Phase 1 继续使用 `memoryos-pypi`。一手审计已确认 `memoryos-chromadb` 同时改变
   检索、合并、heat/LTM、持久化与异常语义，裁为 `reproduction_variant:memoryos-chromadb`，
   不是普通 storage variant，也不进入当前 smoke 主线。
5. **2026-07-16 新政策已裁定**：unified 主轨使用每个 method 在 vendored 版本上的 pinned
   product-default；无 runnable default 时按已裁证据链锁 `product_canonical_required_config`。
   同一 method 跨五 benchmark 固定一套；2026-07-09 已执行的 shared
   MiniLM 政策在当时有效，现有配置/结果保留并改身份为 `controlled_embedding_v1` 补充消融。
   不按新偏好篡改旧实验史，也不把 controlled override 冒充 repo default。

## 依赖与当前动作

- 长效政策：[`dual-track-config-policy.md`](../../../../reference/dual-track-config-policy.md)
- 已有 MemoryOS eval/pypi 证据：[`m1-memoryos-evidence.md`](../../notes/m1-memoryos-evidence.md)
- 已有 LightMem 三岔证据：[`lightmem-native-config-threeway.md`](../../notes/lightmem-native-config-threeway.md)
- 已有 Mem0 mutation/调用链证据：[`mem0-provenance-validity-audit.md`](../retrieval-metrics/notes/mem0-provenance-validity-audit.md)
- Fable 5 一手审计（已验收并保留架构师订正）：
  [`integrated-method-dual-track-identity-audit.md`](notes/integrated-method-dual-track-identity-audit.md)
- 现行 embedding/variant 裁决：
  [`product-default-embedding-ruling.md`](notes/product-default-embedding-ruling.md)
- 下一张施工卡：
  [`actor-prompt-track-identity-contract-m0.md`](cards/actor-prompt-track-identity-contract-m0.md)

**状态：M0 首轮未通过，Codex R1 施工中。**混合 actor 首轮 `81f2708` 的定向
`282 passed` 可复现，但把当前 `memoryos-pypi` 错盖成未接入的 ChromaDB reproduction
variant；运行时校验还接受互相矛盾的字段，evaluate/resume 强反例与 note 声明不一致。
用户已明确授权架构师在 Codex 内启动一个 subagent，于原 worktree 追加 follow-up commit，
不 amend、不 push。R1 仍不切 embedding、不重建记忆、不调用 API；通过强验收后才进入
逐 method 重认证。
