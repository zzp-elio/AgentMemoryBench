---
id: ws02
doc: plan (Track A)
status: approved
created: 2026-07-05
---
# ws02 Track A 实施计划：6 个新 method 可行性审计

执行者：Codex。目标：为 MemOS、SimpleMem、LangMem、Cognee、Letta、Supermemory
各产出一份审计卡片，支撑接入顺序决策。**本 plan 全程零 API 成本、零主环境污染。**

## 施工纪律

1. 逐 method 顺序执行（按上面列出的顺序，从轻到重），每完成一个立即勾选并
   在卡片路径后追记完成时间。
2. **禁止调用任何真实 LLM/embedding API**；禁止填写或复制任何 API key。
3. **禁止 `uv add` / 修改 `pyproject.toml`**：依赖试装一律在
   `/tmp` 下的一次性 venv 进行（`python -m venv /tmp/audit-<method>` 或
   `uv venv`），审计结束可删；主环境 `.venv` 不动。
4. 只读 `third_party/methods/<dir>` 源码，不修改其中任何文件。
5. 遇到无法判定的问题（如必须付费/必须云服务才能验证），在卡片"未确认项"
   如实记录，不猜测、不停工。

## 审计卡片格式

每个 method 写 `docs/workstreams/ws02-phase1-matrix/audits/<method>.md`，
固定 7 节（信息不明时写"未确认 + 原因"，不留空）：

1. **来源与形态**：upstream、版本（MANIFEST.md 的 hash）、交付形态
   （pip 库 / 需常驻 server / 需外部服务如 Docker、Postgres、向量库）。
2. **安装可行性**：一次性 venv 中 `pip install` 或本地源码安装的实测结果
   （依赖冲突、Python 版本要求、平台问题照抄报错关键行）。
3. **LLM/embedding 配置面**：内部调用哪些模型；能否配置成
   OpenAI-compatible base_url + `gpt-4o-mini`（我们经 ohmygpt 转发）；
   本地 embedding 是否可用；找不到配置入口时给出源码文件:行号证据。
4. **接口映射（协议中立口径）**：先记录该 method 官方写入/检索 API 的
   **原生粒度与签名**（逐 turn？逐 message pair？整段文本？chunk？是否需要
   时间戳/角色/会话边界信号？），再分别评估映射到 `add(conversation)` 和
   `add_turn(role, content, time, metadata)` 两种候选协议的负担；
   会话/用户隔离机制照常记录。注意：核心协议正在 Track 0 重评估中，
   不要把现有 `BaseMemoryProvider` 当作唯一目标。
5. **可插桩性**：token/latency 能否从 response usage 或 wrapper 层拿到；
   是否有绕过我们观测的内部并发/缓存。
6. **风险与工作量分级**：接入难度 S/M/L（S=纯库、配置即用；M=需适配层或
   轻改配置注入；L=需常驻服务/复杂状态/能力缺口），并列出 top 风险。
7. **未确认项**：需要架构师或用户决策的问题清单。

Supermemory 额外要求：明确 local OSS（self-host）版本提供哪些 API，
与 Enterprise 云版能力差异；若 local 版缺少 Phase 1 必需的写入/检索/
provenance 能力，逐条记录 gap（用户已定：不满足时回来讨论，不擅自换 method）。

## 任务清单

- [ ] MemOS 审计卡片
- [ ] SimpleMem 审计卡片
- [ ] LangMem 审计卡片
- [ ] Cognee 审计卡片
- [ ] Letta 审计卡片
- [ ] Supermemory 审计卡片（含 local OSS 能力边界专项）
- [ ] 汇总表：`audits/summary.md` —— 6 method × （形态 / 安装 / LLM 配置 /
  接口映射 / 插桩 / 难度分级）一览 + 建议接入顺序（从 S 到 L）
- [ ] 更新 ws02 README"当前断点"，通知架构师审查

## 验收

- `ls docs/workstreams/ws02-phase1-matrix/audits/*.md | wc -l` = 7（6 卡片 + summary）。
- 每张卡片 7 节齐全，安装结论有实测命令输出佐证（贴关键行）。
- `git status --short` 中主环境无 `pyproject.toml` / `uv.lock` / `.venv` 变更。
- 全程无 API 调用记录。
