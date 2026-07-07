---
id: ws02.4
parent: ws02
doc: spec+plan（小型 method 接入合订本）
status: approved (2026-07-07 用户批准；text-only 裁定获认可；Qwen3 emb 已下载)
created: 2026-07-07
---
# ws02.4 SimpleMem Adapter 设计与实施（合订本，已批准）

作者：Claude（架构师）。依据：
[mechanism-simplemem.md](../ws02-phase1-matrix/audits/mechanism-simplemem.md)
（全部机制事实引自该卡）、协议 v3、Track A 审计（难度 M，接入顺序第 1）。
小型 method 接入采用 spec+plan 合订：spec 部分定口径，plan 部分给 task；
用户一次批准即可开工。

## SPEC 部分

### S1 范围与形态

- 接入 **SimpleMemSystem text backend**（机制卡 §6 待决项裁定：不用 auto
  router/EvolveMem/Omni——text path 是 MemoryData 实证口径且无多模态依赖）。
- 目标格子：SimpleMem × LoCoMo、SimpleMem × LongMemEval（既有 benchmark，
  无需新 runner 能力）。
- LLM：官方默认 `gpt-4.1-mini` **显式覆盖为 `gpt-4o-mini`**（项目硬规则），
  经 OpenAI-compatible base_url（ohmygpt）；算法参数保持官方默认
  `WINDOW_SIZE=40 / OVERLAP_SIZE=2 / SEMANTIC_TOP_K=25 / KEYWORD_TOP_K=5 /
  STRUCTURED_TOP_K=5`（机制卡 §4 settings.py:12-40），profile 名
  `official-text-v1`（official=method 官方口径，基座统一按项目规则标注）。
- Embedding：官方默认 `Qwen/Qwen3-Embedding-0.6B` 本地模型——**新增
  `models/Qwen3-Embedding-0.6B` 本地资源前置**（用户需下载，同 LightMem
  models 先例）；adapter 构造前强校验本地路径存在。

### S2 协议 v3 映射

- `consume_granularity="turn"`：`ingest(TurnEvent)` →
  `add_dialogue(speaker=event.speaker_name or role, content=event.content,
  timestamp=转换后时间)`；SimpleMem 内部 window buffer 自行攒批（机制卡 §1）。
- 时间转换：benchmark 原始时间字符串 → ISO（LoCoMo `1:56 pm on 8 May, 2023`
  类格式转换器 + 单测；不可解析时传 None，不猜测）。
- **`end_conversation` → `finalize()`**（残窗抽取；机制卡 §1 finalize 语义），
  finalize 成功返回才算写入完成（R3）。
- `retrieve(RetrievalQuery)`：**绕开 `ask()`**（R1），直接
  `hybrid_retriever.retrieve(query_text)`（planning/reflection 属检索服务型
  LLM，允许并计入 retrieval 成本）；`formatted_memory` = 命中 MemoryEntry 的
  `lossless_restatement` 按 `[timestamp] text` 逐条拼接；`prompt_messages` =
  复刻官方 `AnswerGenerator` prompt 模板（机制卡 §3 answer_generator.py:22-83，
  native 口径，reader 执行 LLM——不调 SimpleMem 自己的 AnswerGenerator）。
- 能力声明：`session_memory_report=False`；`provenance_granularity="none"`
  （MemoryEntry 是 LLM 压缩产物无 turn 锚点，机制卡 §5；不做 sidecar，
  用户占位原则）。
- 隔离与状态：每 isolation_key 独立 LanceDB path/table（state_dir 下）；
  clean retry hook = 删除该 conversation 的 LanceDB 目录后整段重放；
  **buffer 未 finalize 即中断 → 状态不完整，resume 必须整段重 ingest**
  （fail_ingest 语义，机制卡 §4"finalize 前退出 buffer 丢失"）。
- 并行：isolated worker 路径（不共享实例）；`allow_smoke_worker_override=True`。
- 效率观测：builder/retrieval LLM 经 LLMClient 包裹记录 usage（A-Mem wrapper
  先例）；本地 embedding 不产生 API observation；source identity 覆盖
  simplemem 核心源码文件 + 本项目 wrapper。

### S3 未确认项

- Qwen3-Embedding-0.6B 下载由用户执行（下载方式写入 plan T1 验收注记）。
- text-only 依赖集能否不装 multimodal/EvolveMem extras（Track A 卡片 §6 风险）
  ——T1 实测，装不干净则停工上报。

## PLAN 部分（Codex 执行）

纪律：ws 系列全部照旧；基线 771 不得跌破；机制卡是第三方行为唯一事实源，
与实现冲突时停工。

- [ ] **T1 依赖与配置**：uv 隔离验证 simplemem text 路径依赖集；
  `configs/methods/simplemem.toml` + 强类型 config（LLM/embedding 路径/
  窗口参数/timeout/retry）；本地模型路径强校验；registry 骨架 +
  source identity。验收：config/registry focused 测试全绿；依赖实测输出留档。
- [ ] **T2 写入链路**：`ingest(TurnEvent)` + 时间转换器 + `end_conversation→
  finalize()`；fake SimpleMemSystem 记录调用序列，断言逐 turn add_dialogue
  顺序、timestamp 转换、finalize 恰在末尾一次。验收：adapter ingest focused
  全绿。
- [ ] **T3 检索链路**：retrieve 绕开 ask、formatted_memory 拼接规则、
  native prompt_messages 复刻 AnswerGenerator 模板（文本摘录注行号）。
  验收：retrieve focused + prompt 结构断言全绿。
- [ ] **T4 状态/retry/观测**：LanceDB per-isolation 目录、clean retry hook、
  fail_ingest 语义测试（模拟 finalize 前中断→retry 整段重放）、LLM usage
  observation 接线。验收：状态与观测 focused 全绿。
- [ ] **T5 registered fake 全链路**：LoCoMo + LongMemEval fake smoke 各一，
  artifact/manifest（protocol_version=v3, prompt_track=native）齐全。
  验收：端到端测试全绿；`uv run pytest -q` ≥771；compileall 通过。
- [ ] **T6 收尾**：method-interface-inventory 增 SimpleMem 节、ws02 README
  矩阵表更新、本 README 勾选与断点。验收：git status 干净。

## 明确不做

不接 multimodal/EvolveMem/Omni；不做真实 API smoke（待用户预算）；
不实现 unified prompt（等 LoCoMo/LME unified profile 任务）；不做 provenance
sidecar。
