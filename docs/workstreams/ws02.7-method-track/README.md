---
id: ws02.7
parent: ws02
status: in-progress（首批 5 method frozen；结构归一 M0 后接 MemOS）
created: 2026-07-12
---
# ws02.7 Method Track M0

本 workstream 在五个 benchmark frozen-v1 的稳定层上，按
[`method-integration-checklist.md`](../../reference/method-integration-checklist.md)
B1-B11 逐家接入 10 个 method。活跃支线统一从
[`branches/README.md`](branches/README.md) 进入；不要从历史文件名猜当前动作。

完整历史账已归档到
[`2026-07-23-ws02.7-method-track-full-ledger.md`](../../archive/status/2026-07-23-ws02.7-method-track-full-ledger.md)。
该档只供定点追溯，不参与日常恢复。

## Codex 恢复胶囊（热层）

压缩后只执行：

1. `git status --short`
2. `git log -5 --oneline`
3. 读取本节
4. 读取“当前动作”链接的一份 ruling/note

禁止为恢复全局而全文读取历史账、全部 workstream 或两本经验手册。若本节与 Git
冲突，以 Git 和最新 ruling 为准。

- **稳定基线（2026-07-23）**：5 benchmark × 首批 5 method 的真实 smoke 与
  B1-B11 已关闭。A-Mem 目录归一后无 API 全量门：
  `1680 passed, 3 deselected, 1 warning, 29 subtests passed in 132.13s`；
  compileall exit 0。唯一 warning 是既有 vendored LightMem Pydantic deprecation。
- **当前动作**：先执行 ws03
  [结构归一 M0](../ws03-architecture-slimming/notes/2026-07-23-structural-normalization-m0-ruling.md)，
  只做文档热/冷分层、retrieval evaluator 共壳与 prompt ownership 归位，零评测语义变化；
  M0 全量门后接入 **MemOS**。
- **不可顺手重开**：benchmark raw/canonical/gold 调查、已冻结 25 格、旧
  `config_track` 兼容、legacy bridge/resume、BLEU/ROUGE/Precision 新公式。
- **恢复当前结构任务只读**：上方 M0 ruling；需要追溯某家 method 才读下表对应 frozen note。
- **派工边界**：actor 卡由架构师写成自包含 prompt，用户选择跨模型 actor；除非用户明确
  要求，不自动启动 Codex subagent。

## 当前里程碑

| Method | 状态 | 权威冻结记录 | 关键资格边界 |
| --- | --- | --- | --- |
| LightMem | `method-frozen-v3` | [frozen-v3](branches/method-recertification/lightmem/notes/lightmem-frozen-v3.md) | online-soft；pair lineage 资格按 benchmark；forced flush 已修 |
| Mem0 | `method-frozen-v2` | [frozen-v2](branches/method-recertification/mem0/notes/mem0-frozen-v2.md) | V3 singleton 合法；LoCoMo speaker 映射；turn/session provenance 分格 |
| MemoryOS | `method-frozen-v1` | [frozen-v1](branches/method-recertification/memoryos/notes/memoryos-frozen-v1.md) | STM + ranked MTM Recall；HaluMem extraction N/A |
| A-Mem | `method-frozen-v1` | [frozen-v1](branches/method-recertification/amem/notes/amem-frozen-v1.md) | evolution 后 current memory；Recall/Precision/NDCG N/A |
| SimpleMem | `method-frozen-v1` | [frozen-v1](branches/method-recertification/simplemem/notes/simplemem-frozen-v1.md) | 合成 MemoryEntry；provenance N/A；build 串行 |

未接入：MemOS、Letta/MemGPT、EverOS、LangMem、Supermemory。EverOS 仍排最后。

## 现行长期裁决

### 数据与输入

- benchmark 稳定事实从 `docs/survey/` 与五家 frozen note 复用；只有 source lock/
  official asset 变化或新一手反证才重开 census。
- role/content/time/place/image 必须沿 canonical event → method ingest → backend
  payload 一手验证；不从 prompt 文案反推接口硬约束。
- placeholder 只有 method 的真实结构约束需要时才允许；不得制造非空假回复。
- typed timestamp 用 `turn → session → None` 的已声明回落；question time、兄弟 turn、
  wall clock 不得补进 source time。

### Method 与配置

- 主路径是 v3 `ingest + retrieve → framework reader`；新 method 不扩展 legacy API。
- 每个 method 一个 TOML；`smoke`/`official_full` 是跨五 benchmark 固定主 section；
  有一手证据时才增加稀疏 `author_<benchmark>`。
- 主 answer builder 归 benchmark；作者 builder 是完整 `PromptMessage[]` 构造，
  不是模板文件名。旧 `unified/native` 只作历史产物兼容。
- method × benchmark × metric 独立判 `valid/N/A/pending`。变换输入 lineage
  不等于当前 memory 的 semantic provenance。

### Metric 与 artifact

- Gold Evidence Group、RetrievalEvidence、N/A/null 与 stable-ranking 资格均已进入
  artifact；不得回退 run 级静态猜测。
- Recall 公式内核通用，benchmark 壳保留 gold view、empty/no-target/abstention 和
  official parity。当前结构归一只迁职责，不改公式、分母或启用面。
- 新答案/检索指标属于 metric-pack；已有 artifact 字段足够时离线复算，不反向重烧
  method build。LLM judge 仍需单独预算批准。

## 当前动作与关闭门

1. **ws03 M0-A**：本 README 与经验手册热/冷分层；
2. **ws03 M0-B**：pure metric 归位、retrieval evaluator 共壳；
3. **ws03 M0-C**：benchmark/author prompt ownership；
4. 定向测试、文档门、compileall、无 API 全量 pytest；
5. 回到本 workstream 接入 MemOS。

M0 红线：零真实 API、零 third-party 算法改动、零 metric/prompt/artifact 语义变化；
旧 import path 在迁移期保留薄兼容层。

## 稳定入口

- [活跃支线索引](branches/README.md)
- [method 重认证总入口](branches/method-recertification/README.md)
- [Method TOML 与 answer builder 政策](../../reference/method-toml-and-answer-builder-policy.md)
- [Method 接入清单 B1-B11](../../reference/method-integration-checklist.md)
- [指标扩展计划](../../reference/metric-extension-plan.md)
- [结构归一 M0 裁决](../ws03-architecture-slimming/notes/2026-07-23-structural-normalization-m0-ruling.md)
- [截至 2026-07-23 的完整历史账](../../archive/status/2026-07-23-ws02.7-method-track-full-ledger.md)

## 里程碑

- [x] 五个 benchmark frozen-v1
- [x] 首批 5 method × 5 benchmark 真实 smoke 与 B1-B11
- [ ] 结构归一 M0
- [ ] MemOS
- [ ] Letta/MemGPT
- [ ] LangMem
- [ ] Supermemory
- [ ] EverOS（最后）
