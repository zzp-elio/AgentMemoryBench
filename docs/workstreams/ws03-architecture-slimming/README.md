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

## 项目结构整治优化（2026-07-11 用户立项扩充；前置条件 = ws02.6 B6 五
benchmark 全部 frozen 后，行为被全量测试锁死才允许动结构）

- [ ] **evaluator 通用化**：recall 类抽公共骨架（公开 id 空间匹配、
  any-match、unmatched/歧义计数），llm judge 抽公共调用壳（模型/重试/
  解析）；**红线：各 benchmark 的 gold 形态差异与官方 parity 规则必须
  保持显式声明**（longmemeval 双粒度/membench +1 平移/beam 三形态打平/
  halumem 无 turn id——B 线教训：个性被通用代码吞掉 = bug 温床），
  通用骨架 + benchmark 声明差异，行为以现有全量测试逐一守恒验证。
- [ ] **拆开 answer depth 与 evaluation ranking depth**（2026-07-15 LightMem
  审计）：当前 `RetrievalQuery.top_k=10` 全局硬编码，同时被当成 evaluator 可算的
  最大 k；LongMemEval 官方 k=30/50 因而在真实通用 run 必然跳过，即便某 method 已
  保存 60 项。设计 benchmark-required ranking depth 与 method-native answer context
  depth 两个字段/视图，保证扩深排名观测不偷偷改变 answer prompt。
- [ ] **Recall@k 粒度诊断与公平伴随指标**：保留 method-native item recall，但统一
  报 top-k unique source 数、`source ids/item` 与 payload token；研究 source-budget/
  token-budget recall。未完成前禁止用单一 item Recall@k 作跨 method headline 排名。
- [ ] **method × benchmark × metric 资格声明**（2026-07-15 LightMem 二次裁决）：
  将当前 registry 静态 `provenance_granularity` 拆为可按 benchmark/metric 表达的
  valid/N/A/pending capability，并带机器可读 reason。区分 semantic evidence
  provenance 与 transformation-input lineage；NDCG 另校验稳定顺序和 evaluation
  depth。先做 docs-only 契约审计，不在单个 adapter 里打 LoCoMo 特判。
- [ ] **目录分层**：benchmark 专属指标归 per-benchmark 子目录，通用
  指标（f1/recall 骨架/judge 壳）归 common；prompt 资产统一存放布局
  （locomo/longmemeval 独立 prompt 文件 vs 其他内联的组织不一致，
  E3 时用户已点出）。
- [ ] **历史遗留盘点**（先盘点分类再动手，每项以"引用扫描 + 测试通过"
  为证据，不凭印象）：已确认遗留 = `BaseMemoryRetriever`（本 ws 既有）、
  `--profile` 残留；**待核** = `runners/ingest_resume.py`（用户 2026-07-11
  点名疑似遗留，但 CLAUDE.md 载明其为 resume 系统活跃组件
  ——TurnIngestCheckpointStore——须引用扫描裁定，不得凭印象删）；
  盘点产出三列清单：活跃/疑似/确认遗留。
- [ ] **长期健壮性排查**（第一性原理：项目连续运行 3-12 个月不腐坏）：
  ① **wall-clock 泄漏扫描**——`datetime.now()/today()` 是否参与任何
  评测语义（question time、相对时间换算、resume 判定），只允许出现在
  观测性时间戳；② **judge/answer 模型指纹**——manifest 是否钉死模型名
  +版本，模型漂移（gpt-4o-mini 升级/退役）是评测框架最大外部风险，
  结果必须可追溯到模型指纹；③ 依赖锁完整性（uv.lock + vendored
  third_party）；④ 绝对路径/主机名假设（原则 #12 身份=内容已治理
  一处，扫残余）。

## 决策记录

- 2026-06-21 用户：保留轻量 registry；capability 枚举与 legacy 基类属迁移期负担。
- 2026-06-22 用户：`retrieve()` 主输出为 `AnswerPromptResult.prompt_messages`；
  `answer_prompt` 仅兼容视图。
- 2026-06-24 用户：普通用户接入只要求 `add + retrieve`；TOML/source identity/
  深度插桩属框架开发者白盒路径（已实现，本 ws 不重复）。
