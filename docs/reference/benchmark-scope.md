# Benchmark 范围

长期可支持多个 task family，当前只实现 conversation + QA。

具体数据结构定义请看 `docs/dataset_structures/`，评测流程参考请看
`docs/evaluation_workflows/`。当前运行时数据放在 `data/`，官方 benchmark 仓库与源码参考
放在 `third_party/benchmarks/`。

## Phase 1

Phase 1 只做纯文本闭环：

1. 先以 LoCoMo 打通各个 method。
2. 再接入 LongMemEval。

这两个 benchmark 都可以表达为：

```text
conversation history -> question -> answer-level score
```

## 暂缓范围

HaluMem、MemBench、Mem-Gallery 不在 Phase 1 主线中。能自然适配为 conversation + QA
的版本或切片可后续接入；不能自然适配的内容必须等真实需求出现后，再归入新的 task
family，不能硬塞进当前数据模型。

多模态字段已在 core 中预留，但 Phase 1 不主动处理图片。

## 已移除范围

偏好遵循类 benchmark 与当前主线差异过大，已经从当前项目范围移除。后续不要恢复它的原始仓库、adapter、测试或文档。

## 指标范围

当前已实现 answer-level 质量评测：

- LoCoMo: token F1，可选 LLM judge accuracy。
- LongMemEval: LLM judge accuracy。

不做 retrieval recall。后续只优先增加：

- Retrieval Latency。
- Memory Context Tokens。
- Memory Update Cost：update latency、LLM tokens、embedding tokens。

这些效率指标当前只完成架构定义，尚未实现。

## 数据位置

adapter 使用默认路径，并允许用户覆盖本地数据路径。大型 benchmark 数据不会进入 Python
安装包。自动下载、注册和校验工具等项目成熟后再设计。
