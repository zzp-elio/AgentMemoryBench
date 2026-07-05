---
id: ws03
parent: null
status: open
created: 2026-07-05
---
# ws03 架构减重（registry / legacy 接口 / CLI / LLM 配置）

## 目标

retrieve-first 主路径稳定后，清除迁移期留下的重复机制：capability 推理、
legacy 基类、legacy CLI、分散的 LLM 配置。完成判据：新 method 兼容性由
`BaseMemoryProvider` 继承关系表达；legacy 负担删除或明确降级；
统一 `LLMRuntimeConfig` 落地且 manifest/model inventory 不回退。

## 当前断点

- 2026-07-05：仅有两份已对齐方向的设计 spec（见本目录），未开始实施。
  实施前需架构师把 spec 细化为带验收命令的 plan。

## 设计文档

- [2026-06-21-registry-capability-simplification-design.md](2026-06-21-registry-capability-simplification-design.md)
- [2026-06-21-llm-provider-config-design.md](2026-06-21-llm-provider-config-design.md)

## 任务清单

- [ ] 弱化 `MethodCapability` 推理，conversation-QA 兼容性收敛到
  `BaseMemoryProvider` 继承关系；保留轻量 registry（名称 → factory/config/
  source identity 映射），不回退分散 `if/else`。
- [ ] 清理或降级 `BaseResumableMemorySystem`、`BaseMemoryRetriever`、
  `add_from_turn()` 与历史 turn-level resume 文档/测试；`BaseMemorySystem`
  暂保留为后备兼容接口。删除前必须证明四个内置 method、fake/offline 测试和
  artifact-only evaluation 不依赖旧主路径。
- [ ] Legacy CLI 分阶段清理（节奏已定）：四 method 的 LoCoMo/LongMemEval v2
  smoke 稳定后加 deprecated warning → 至少一次 v2 formal 小规模 run 后从 README
  示例移除旧写法 → 对外发布前决定是否彻底删除旧参数。
- [ ] `OpenAISettings` 迁移到统一 `LLMRuntimeConfig` / `LLMResponse`；
  第一版仍只实现 OpenAI-compatible provider。
- [ ] 减重 evaluator registry：F1 / LLM judge 统一为 metric profile +
  prompt profile，不为每个 benchmark 复制 evaluator 类。
- [ ] prediction artifact 瘦身长期兼容：旧 artifact 回读策略、更多
  conversation-level metadata key、evaluator 是否引用 `conversation_prompts.jsonl`。
- [ ] evaluator category 汇总里 `correct_count` 是否更名
  `perfect_match_count`（防止 F1 连续指标被误读为 accuracy）。
- [ ] 评估可选 `--method-file` 单文件快速测试入口（method 接入轻量化遗留项）。

## 决策记录

- 2026-06-21 用户：保留轻量 registry；capability 枚举与 legacy 基类属迁移期负担。
- 2026-06-22 用户：`retrieve()` 主输出为 `AnswerPromptResult.prompt_messages`；
  `answer_prompt` 仅兼容视图。
- 2026-06-24 用户：普通用户接入只要求 `add + retrieve`；TOML/source identity/
  深度插桩属框架开发者白盒路径（已实现，本 ws 不重复）。
