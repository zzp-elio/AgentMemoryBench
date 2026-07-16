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
4. MemoryOS Phase 1 暂继续使用 `memoryos-pypi`。`memoryos-chromadb` 在核心文件均有 diff，
   等价性审计前只作 storage variant 候选。
5. unified embedding 的旧“全局统一”口径与“产品 repo 默认”发生冲突：Mem0 当前 shared
   MiniLM 明确不同于产品默认 `text-embedding-3-small`。不得先改配置；先做三家 build-axis
   取证，再由架构师裁 product-default 主轨与 controlled-embedding ablation 的身份/重跑面。

## 依赖与当前动作

- 长效政策：[`dual-track-config-policy.md`](../../../../reference/dual-track-config-policy.md)
- 已有 MemoryOS eval/pypi 证据：[`m1-memoryos-evidence.md`](../../notes/m1-memoryos-evidence.md)
- 已有 LightMem 三岔证据：[`lightmem-native-config-threeway.md`](../../notes/lightmem-native-config-threeway.md)
- 已有 Mem0 mutation/调用链证据：[`mem0-provenance-validity-audit.md`](../retrieval-metrics/notes/mem0-provenance-validity-audit.md)
- 当前 actor 卡：[`actor-prompt-integrated-method-dual-track-identity-audit.md`](cards/actor-prompt-integrated-method-dual-track-identity-audit.md)

**状态：需要用户派发；推荐 Fable 5。**这是三家 method × 多代码形态的高难度 docs-only
一手审计。退出条件：actor note 回卡后，架构师抽锚、裁 embedding 主轨/ablation 身份，并
更新 B10 与受影响 method 的复证范围。未完成前不改现有 embedding 配置、不跑付费 smoke。
