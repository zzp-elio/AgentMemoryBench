# Method 资源与参数审计

更新日期：2026-06-17

本文记录 Phase 1 conversation + QA 实验前必须确认的 method 参数和本地资源。当前项目规则：
**smoke 只缩小 benchmark 数据规模，不降低 method 内部官方参数**。这样可以基于局部真实
运行结果估算全量成本；如果 smoke 修改检索深度、模型或压缩参数，局部成本就不再代表
正式实验。

## 通用规则

- smoke 与 official-full 使用同一套 method 算法参数；差异只来自 benchmark 采样范围、
  question 数量和 run_id。
- OpenAI-compatible answer/memory LLM 当前统一使用 `gpt-4o-mini`，除非用户明确决定更换。
- 本地模型必须在真实运行前存在；缺失时 adapter 应在调用第三方核心算法前抛
  `ConfigurationError`。
- 不用 `bge-m3` 替代论文/官方配置里的 `all-MiniLM-L6-v2`，除非另开一个明确的
  custom profile。
- 不在 prediction 阶段计算真实费用；prediction 只记录 token、latency、模型身份和
  observation，费用在实验后离线计算。

## 当前配置矩阵

| Method | 本地/外部资源 | 官方或论文参数 | 当前配置状态 | 运行前阻塞 |
| --- | --- | --- | --- | --- |
| MemoryOS | OpenAI-compatible API；`sentence-transformers/all-MiniLM-L6-v2` 可由 sentence-transformers 缓存/下载 | STM queue=7，MTM max segment=200，User KB/Agent Traits=100，heat threshold=5，retrieval top-m=5，LoCoMo dialogue page top-k=10 | `configs/methods/memoryos.toml` 的 smoke 与 official-full 已一致 | 无新增资源阻塞 |
| Mem0 | OpenAI-compatible API；API embedding `text-embedding-3-small` | OSS benchmark 默认 fact extraction `gpt-4o-mini`、embedding `text-embedding-3-small`；benchmark top-k 默认 200 | `configs/methods/mem0.toml` 的 smoke 与 official-full 均为 `top_k=200` | 需要确认 API 余额和小样本 run_id |
| A-Mem | OpenAI-compatible API；`all-MiniLM-L6-v2` 本地/缓存模型；`rank-bm25`、`litellm` 已安装 | 官方 robust 脚本默认 `retrieve_k=10`，LLM `gpt-4o-mini`，embedding `all-MiniLM-L6-v2` | `configs/methods/amem.toml` 的 smoke 与 official-full 均为 `retrieve_k=10` | 首次运行可能自动下载/加载 `all-MiniLM-L6-v2` |
| LightMem | OpenAI-compatible API；本地 `models/all-MiniLM-L6-v2`；本地 `models/llmlingua-2-bert-base-multilingual-cased-meetingbank` | LoCoMo reported setting 使用 combined retrieval，`total-limit=60`；README 要求 LLMLingua2 和 all-MiniLM-L6-v2 | `configs/methods/lightmem.toml` 的 smoke 与 official-full 均为 `retrieve_limit=60` | 本地模型已补齐；真实运行仍需用户确认 method、benchmark、样本规模和 run_id |

## LightMem 本地资源

当前 `models/` 下已有：

```text
models/BAAI/bge-m3
models/nltk
models/all-MiniLM-L6-v2
models/llmlingua-2-bert-base-multilingual-cased-meetingbank
```

LightMem 所需两个本地模型已下载到：

```text
models/all-MiniLM-L6-v2
models/llmlingua-2-bert-base-multilingual-cased-meetingbank
```

来源：

- `sentence-transformers/all-MiniLM-L6-v2`
- `microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank`

当前本地体积：

- `models/all-MiniLM-L6-v2`: 约 956M
- `models/llmlingua-2-bert-base-multilingual-cased-meetingbank`: 约 680M

Adapter 已增加资源前置校验：如果配置指向 `models/...` 或绝对路径但目录不存在，真实
LightMem backend 构造前会抛 `ConfigurationError`。fake/offline 测试不会要求这些模型存在。

## 下一步真实 smoke 建议

在确认 API 余额和 run_id 后，按以下顺序做极小真实 smoke：

1. Mem0 + LoCoMo：已有历史 smoke，但新规则下 `top_k=200`，建议重新跑 1 conversation、
   1 question。
2. MemoryOS + LoCoMo：参数已对齐，成本较高，先跑 1 conversation、1 question。
3. A-Mem + LoCoMo：先跑 1 conversation、1 question，观察 `all-MiniLM-L6-v2` 加载和 API
   调用记录。
4. LightMem + LoCoMo：本地模型已补齐，可在用户确认后跑 1 conversation、1 question。
5. LoCoMo 四个 method 均通过后，再对 LongMemEval-S 做同样极小 smoke。

每个 smoke 都必须写入标准 artifacts、logs、checkpoints 和 efficiency observations。不得把
smoke 的结果当作正式指标，只用于验证链路和估算成本。
