# Method TOML 配置与 answer prompt 构造政策

> **现行长期政策（2026-07-17，用户与 GPT-5.6 架构师对齐）。**本文取代
> `dual-track-config-policy.md` 作为 method 参数选择与 answer prompt 构造的事实源。
> 旧 `config_track=unified/native` 实现和既有产物继续如实保留历史身份，但不再代表目标
> 配置模型。

## 0. 一句话裁决

每个 method 只维护一个 TOML 文件；主配置跨五个 benchmark 固定，作者实际跑过的
benchmark 可以增加少量 `author_<benchmark>` section。CLI 只选择 section，不逐项传
超参数，也不根据 benchmark 暗中自动切换。answer 配置选择的是**完整 prompt builder**，
不是一份尚未填变量的模板文件。

## 1. TOML 结构

目标结构如下；具体字段由各 method 的强类型 config 决定：

```toml
[smoke]
# 5×10 极小流通验证。method 算法参数原则上与 official_full 相同；只允许缩小
# 数据范围、问题数、并发或其他不改变 method 行为的运行规模。

[official_full]
# Phase 1 主配置：同一个 method 跨 LoCoMo、LongMemEval、HaluMem、BEAM、MemBench
# 使用同一套 method 超参数。
answer_builder = "benchmark"

[author_locomo]
# 只有作者确实在 LoCoMo 跑过且参数有一手证据时才存在。
answer_builder = "<method>_locomo_official"

[author_longmemeval]
# 只有作者确实在 LongMemEval 跑过且参数有一手证据时才存在。
answer_builder = "<method>_longmemeval_official"
```

规则：

1. “跨五个 benchmark 固定”指**同一 method** 的主配置固定，不要求十个 method 使用
   相同的内部数值。
2. `smoke` 不为省钱篡改算法参数；成本只靠数据、conversation/question/turn 范围和并发
   缩小。若确有无法避免的 smoke-only 行为差异，必须进 manifest 并单独披露。
3. `author_<benchmark>` 是稀疏的作者复现配置，不是主表默认，也不因为当前 benchmark
   同名就自动启用。作者没有跑过的格子不编造 section、不代替作者调参。
4. 每个 section 写完整、可独立解析的参数。当前阶段不引入继承或多层 merge，少量重复优于
   隐藏覆盖关系。
5. embedding model、dimension、normalization、retrieval depth、chunk、update、summary 等
   都是普通 TOML 字段，不再为它们发明另一条全局轨。共同 embedding 还是产品默认 embedding
   的最终主表选择，留到真实效果实验前逐 method 裁定；5×10 smoke 沿用当前已验收配置。

## 2. 运行选择

- 超参数值只写在 TOML；CLI 不提供几十个逐项覆盖参数。
- CLI 保留一个必要选择器，例如 `--profile official-full` 或
  `--profile author-locomo`。它只选择 TOML section，不携带配置值。
- 禁止看到 `benchmark=locomo` 就自动切到 `author_locomo`；主表在 LoCoMo 上仍使用
  `official_full`，只有显式作者校准 run 才选择 `author_locomo`。
- 禁止运行前手改同一个 section 再复用旧 run_id。manifest 必须记录 section 名、解析后的
  完整公开配置与足以阻断错误 resume 的身份。

## 3. answer prompt：选择 builder，不是选择模板

静态 prompt template 只是 builder 的一个素材。真正的实验资产是完整构造过程：

```text
TOML 选择 answer_builder
  → builder 读取公开 Question + RetrievalResult
  → 取得并校验官方要求的全部变量
  → 完成格式化、角色与消息顺序
  → 产出可直接交给 answer LLM 的 AnswerPromptResult.prompt_messages
```

### 3.1 主配置

`answer_builder = "benchmark"` 表示使用当前 benchmark 注册的统一 builder。同一 benchmark
下所有 method 共用该 builder。它可以填入 `formatted_memory`、question、question time、
category、choices 等公开变量，但不得读取 method 私有实现或 gold。

### 3.2 作者配置

`answer_builder = "<method>_<benchmark>_official"` 表示复现 method 官方 harness 的完整
answer 构造。官方模板若需要 speaker 分组、日期、检索条目、摘要、system/user 多消息或其他
变量，builder 必须逐项从正确的公开来源取得并填好；不能把模板文件本身冒充“prompt parity”。

作者 builder 必须同时满足：

1. **变量来源正确**：每个占位变量有公开字段或 method 检索输出锚，不拿 question time
   替 source time，也不拿任意 metadata 猜值。
2. **缺失 fail-fast**：必需变量缺失、类型错误或空白时在 answer API 前失败；不补空串、
   synthetic value 或静默省略。
3. **最终消息 parity**：验收最终 `PromptMessage[]` 的条数、role、顺序、内容、格式和必要的
   decoding 参数，而不只比较模板文本。
4. **隐私边界**：builder 只能消费公开 question、时间、选择项、method 检索结果及公开
   metadata；gold answer、gold evidence、judge label 永不可达。
5. **可审计 artifact**：最终构造好的 messages 与 builder 身份进入公开 answer artifact/
   manifest；不能只记录一个模板文件名。

`answer_builder` **不选择 judge**。主配置与作者校准都继续使用当前 benchmark 注册的统一
evaluator/judge LLM、prompt 与计分语义；不能因选了 method 官方 answer builder 就暗换 judge。
若未来确需复现 method harness 的专属 judge，只能另立带身份与指标 tier 的补充研究卡，经用户
拍板后实施，不能借 `author_<benchmark>` 默默带入。

现有代码中，benchmark unified builder 已直接返回 `AnswerPromptResult`；部分 method 官方路径
则由 adapter 在 retrieve 阶段提前构造 `prompt_messages`，后层 builder 只做验证/透传。后者
验收时必须沿调用链检查“变量产生 → 格式化 → 最终 messages”，不能只审最后一个函数。

### 3.3 Prompt 资产的代码所有权

prompt 目录按“谁定义实验口径”分层，而不是按“当前由哪个 adapter/evaluator 调用”分层：

- `src/memory_benchmark/prompts/benchmarks/`：五家主表 answer builder、
  benchmark judge prompt 与官方来源；不得 import `methods/` 或 `prompts/author/`；
- `src/memory_benchmark/prompts/author/`：LightMem、Mem0、MemoryOS 等作者校准
  builder/prompt；只服务显式 author profile；
- method 产品内部的 extraction/update/build prompt 仍归 method/vendored 实现，
  不复制进 framework prompt 包。

旧 `benchmark_adapters/*_prompt.py`、`evaluators/halumem_prompts.py` 与
`methods/*_native_prompts.py` 在迁移期仅保留薄 re-export shim，保证旧扩展和历史测试
可导入；新代码必须引用 canonical prompt package。是否删除 shim 与旧 `config_track`
退出一并裁定，不能让兼容层继续承载新内容。

## 4. TOML 的边界

TOML 负责**保存数值与选择实现**；代码只负责两类不可避免的工作：

1. 把第三方库里原先写死、但确属可配置的参数暴露给强类型 config；
2. 实现并注册需要逻辑构造的 answer builder。

如果两个官方目录改变了 update/retrieval/storage 等算法流程，它们是不同 implementation，
不能靠 TOML section 或旧 `native` 名称伪装成同一个 method 的参数差。

## 5. 与旧 `config_track` 的关系

- 当前 `config_track=unified/native`、track-aware 输出目录和 `TrackIdentity v1` 已存在，旧产物
  不改写、不假装来自新政策。
- `TrackIdentity v1` 中已经落盘的 implementation/build/readout 事实仍有审计价值；目标是让
  manifest 如实记录最终 TOML 与 builder，而不是删除身份校验。
- 新运行模型不再强铺两条流水线：5×10 主 smoke 只要求 `smoke` 主配置；作者配置仅在确有
  复现价值、预算和一手参数时另跑。
- 迁移完成前，旧 `config_track` 是兼容实现，不是新增 method 应继续复制的架构模板。

## 6. 实施日程

1. **现在已完成**：政策落盘；不改既有实验史，不触发真实 API。
2. **当前主线不变**：先完成 MemBench FirstAgent canonical pair split，再完成
   RetrievalEvidence M1；5×10 主 smoke 不等待作者参数调优。
3. **首个作者校准 run 或真实效果 full run 之前**：
   - loader/registry 接受有一手证据的 `author_<benchmark>` section；
   - 把仍写死在 adapter/third_party 接缝、但确属配置的参数暴露进 TOML；
   - 用 TOML 的 `answer_builder` 选择 benchmark builder 或作者完整 builder；
   - manifest/resume 锁住 section、解析后配置、builder 与最终 answer 调用参数；
   - 移除新路径对全局 `config_track=unified/native` 分支的依赖，保留旧产物只读兼容。
4. **逐 method 到性能阶段时**：再裁 `official_full` 的最终参数；作者跑过的 benchmark 才补
   对应 author section。Phase 1 不做五个 benchmark 各自 sweep，也不追求 smoke 分数最优。
