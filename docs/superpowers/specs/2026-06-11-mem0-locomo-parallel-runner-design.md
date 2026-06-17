# Mem0-LoCoMo Parallel Generic Runner Design

状态：已确认，进入实施  
日期：2026-06-11

## 目标

使用本地 OSS Mem0 源码在 LoCoMo 上先完成小样本回复生成，并把现有
MemoryOS-LoCoMo 垂直 runner 中可复用的实验能力提炼为通用 conversation + QA runner。
小样本稳定后才批准全量回复生成；metric 从已落盘回复离线计算，不属于当前实施范围。

本阶段不接 Mem0 Platform API，不恢复 retrieval recall，不实现异步 API，不改变 core
公开接口。

## 架构方向

```text
BenchmarkAdapter
  -> Dataset
  -> GenericConversationQARunner
       ├── MemorySystemFactory
       ├── ConversationExecutor
       ├── ArtifactCoordinator
       └── RunPolicy
```

### GenericConversationQARunner

负责 benchmark/method 无关能力：

- dataset 校验和 fingerprint
- public/private artifact 构建
- run manifest 和脱敏配置
- checkpoint/resume
- conversation 调度
- 进度、日志、失败状态
- prediction summary 聚合

runner 不读取 Mem0 或 MemoryOS 内部对象，不按 method 名写条件分支。

### MemorySystemFactory

每个 conversation worker 通过 factory 获得 method 执行上下文。这样 runner 不假定一个
method 实例是否线程安全，也不把 storage namespace 规则写死。

第一版采用一个共享 Mem0 OSS `Memory` 实例：

- 本地 Qdrant client、embedding model 和 SQLite history 由实例共享。
- `run_id=conversation_id` 提供 conversation namespace。
- smoke 初始 `max_workers=1`，通过 conversation 隔离测试后再试 `2`。
- full profile 采用官方 benchmark 默认 `max_workers=10`，但必须先通过并发隔离和
  backend 稳定性验证；否则不得启动全量实验。
- 并发隔离测试失败时必须降级到串行，不得用锁掩盖数据串写。

### Method-specific lifecycle hook

MemoryOS resume 需要 attach 已有 JSON 状态；Mem0 resume 可能只需重新构造客户端并按
namespace 查询已有向量。通用 runner 不应认识这些差异。

可通过小型 method lifecycle 协议表达：

```text
prepare_conversation(conversation, resume_state)
execute add/get_answer through BaseMemorySystem
describe_reusable_state()
```

该 hook 是 runner 内部扩展点，不修改 `BaseMemorySystem` 公共接口。只有证明必要后才增加，
避免先做过度抽象。

## 并行模型

第一层并行单位是 conversation：

```text
worker(conversation):
  build public conversation
  -> method.add([conversation])
  -> answer selected questions
  -> return immutable result batch
```

协调层负责：

- 按 `max_workers` 提交 conversation。
- 接收完成结果。
- 单线程写 predictions、private labels、status 和 progress。
- worker 失败时记录 conversation/question id，并决定停止或继续。

同一 conversation 的 question 第一版保持串行。原因：

- Mem0 的 retrieval/LLM client 和本地存储线程安全尚未验证。
- conversation 级并行已能显著降低总时长。
- 串行 question 更容易精确 resume 和定位失败。

后续只有在实测瓶颈明确且 method 声明支持时，才增加 question 并行。

## 小量真实 Smoke

真实 API smoke 必须显式启用，默认 pytest 不运行。第一版限制为一个真实 LoCoMo
conversation 的少量历史和一道 evidence 完全落在该历史片段内的问题。

evidence 只用于测试夹具选择，不能进入 method public input。该 smoke 只证明：

- 本地 OSS Mem0 能构造。
- add 使用真实 Mem0 算法。
- search 只命中当前 conversation namespace。
- fixed reader 能返回答案。
- adapter 能归一化结果。

该结果不报告为正式 LoCoMo F1，也不能与论文全量结果比较。

## Mem0 Adapter

`Mem0` 对外实现：

```python
add(conversations: list[Conversation]) -> AddResult
get_answer(question: Question) -> AnswerResult
```

内部职责：

- 从 `third_party/methods/mem0-main` 加载 OSS `Memory`。
- 将 Conversation/Turn 转成 Mem0 message。
- 使用 conversation 相关 namespace 隔离存储与检索。
- 调用 Mem0 search 获取记忆。
- 使用固定 reader prompt 和 OpenAI-compatible client 生成最终答案。
- 将 Mem0 原始 add/search 响应归一化为项目实体和安全 metadata。

已确认语义：

- 每个 `conversation_id` 对应一个 Mem0 逻辑 namespace。
- conversation 的全部 turn 按原始顺序写入同一 namespace。
- `get_answer()` 只检索 `question.conversation_id` 对应的 namespace。
- speaker 名称保留在消息 content 和 metadata 中，避免 `user`/`assistant` role 映射丢失
  人物身份。
- adapter 不硬编码 LoCoMo，不采用官方 evaluation 脚本中的双 speaker namespace。

这样评测的是统一框架下的 Mem0 算法，而不是复刻 Mem0 自带 benchmark wrapper。

## 版本固定

当前本地源码版本为 `mem0ai 2.0.4`，但 Mem0 根目录没有 git metadata。实验 manifest
必须记录：

- package version
- deterministic source tree hash
- adapter implementation version
- vector store provider/config
- embedder provider/model
- LLM provider/model
- reader prompt version
- Mem0 top-k
- concurrency policy

参数事实来源优先级：

1. 当前 `mem0ai/memory-benchmarks` 官方仓库的 OSS benchmark 配置。
2. 当前 vendored Mem0 源码的兼容接口与默认值。
3. Mem0 论文只用于解释算法，不覆盖更新更及时的官方 benchmark 配置。

官方 benchmark 配置已经明确：

- memory extraction LLM：`gpt-4o-mini`
- embedding：`text-embedding-3-small`，1536 维
- vector store：Qdrant
- ingestion chunk：每个 turn 一个 chunk（`CHUNK_SIZE = 1`）
- full retrieval：`top_k=200`
- full conversation workers：`10`
- `infer=True`

因此此前计划的本地 `bge-m3` 不再用于 Mem0 官方配置实验。OpenAI key、base URL 由项目
配置层注入 LLM 和 embedder；secret 不进入日志和 manifest。

官方 `memory-benchmarks` 的 Docker requirements 指向已经不存在的
`feat/v3-pipeline` 分支，不能原样安装。我们只参考其参数和数据流，adapter 直接调用
vendored Mem0 `Memory`，并用 contract test 检查当前源码接口。

## 运行 Profile

### Smoke profile

目的仅为低成本验证链路，不作为正式实验结果：

- 1 个 LoCoMo conversation
- 少量连续 turn
- 1 个公开 question
- `max_workers=1`
- 较小 retrieval top-k，默认 `10`
- extraction 与 embedding 仍使用官方模型
- 只生成并保存 answer，不运行 F1 或 LLM judge
- 必须显式确认真实 API 调用

### Official full profile

全量运行前必须由用户再次确认成本：

- LoCoMo 全部 conversation 和公开问题
- 每个 turn 独立调用 Mem0 add
- `gpt-4o-mini` extraction
- `text-embedding-3-small` embedding
- Qdrant
- `infer=True`
- retrieval `top_k=200`
- conversation `max_workers=10`
- 只生成和保存 answer

如果当前 vendored Mem0 源码与官方 benchmark 配置存在不可兼容项，runner 必须在启动前
报错，不能静默替换参数。回答模型属于框架 reader 配置，必须单独记录，不能伪装成
Mem0 内部参数。

升级只跟随明确 release/tag。新版本先在临时目录通过 contract tests 和 LoCoMo 单样本回归，
再替换当前固定版本；禁止自动跟踪 upstream main。

## 错误处理

- namespace 冲突、conversation/question 不匹配、private 字段泄漏立即抛领域异常。
- worker 异常必须记录 stage、conversation_id 和当前 question_id。
- artifact 写入只在协调层进行，并使用现有原子写和 JSONL 恢复工具。
- resume 时必须校验 dataset fingerprint、method config 和 source tree hash。
- source hash 或 method config 不匹配时拒绝复用旧状态。

## 测试层次

1. Mem0 source/version/hash contract。
2. message 与单 conversation namespace 转换。
3. add/search response normalization。
4. conversation 隔离。
5. fake backend 下的通用 prediction runner、无共享写竞争和 resume。
6. LoCoMo 单 conversation、少量 question 的真实 OSS smoke。
7. `max_workers=2` 的两个 conversation 并发隔离测试。
8. 单样本和并发稳定后再批准 official full 回复生成。

## 明确不做

- 不新增 `mem0_locomo_full.py`。
- 不直接运行 Mem0 官方托管版 evaluation 脚本。
- 不修改第三方 Mem0 源码。
- 不自动升级 Mem0。
- 不在第一版并行同一 conversation 内的问题。
- 不把 Mem0 原始响应结构暴露给 runner 或 evaluator。
